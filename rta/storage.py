"""Project-scoped SQLite checkpoints, expiring research cache and immutable audit events."""
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .models import Result


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, token_hash TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS cache (project TEXT, key TEXT, expires REAL, payload TEXT,
                    PRIMARY KEY(project,key));
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, project TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS translations (
                    project TEXT, dataset TEXT, revision TEXT, row_id INTEGER, field TEXT, payload TEXT,
                    PRIMARY KEY(project,dataset,revision,row_id,field));
                CREATE TABLE IF NOT EXISTS translation_cache (
                    project TEXT, key TEXT, payload TEXT, PRIMARY KEY(project,key));
                CREATE TABLE IF NOT EXISTS language_detection_cache (
                    project TEXT, key TEXT, payload TEXT, PRIMARY KEY(project,key));
                CREATE TABLE IF NOT EXISTS google_translation_usage (
                    id INTEGER PRIMARY KEY, project TEXT NOT NULL, month TEXT NOT NULL,
                    submitted_at TEXT NOT NULL, characters INTEGER NOT NULL CHECK(characters > 0),
                    status TEXT NOT NULL CHECK(status IN ('confirmed', 'uncertain')));
                CREATE INDEX IF NOT EXISTS google_translation_usage_month
                    ON google_translation_usage(project, month);
                CREATE TABLE IF NOT EXISTS google_translation_usage_settings (
                    project TEXT PRIMARY KEY, allowance INTEGER NOT NULL CHECK(allowance >= 0));
            ''')
            db.execute('BEGIN IMMEDIATE')
            columns = {row[1] for row in db.execute('PRAGMA table_info(google_translation_usage)')}
            if 'operation' not in columns:
                db.execute("ALTER TABLE google_translation_usage ADD COLUMN operation TEXT NOT NULL DEFAULT 'translation'")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def create(self):
        project, token = secrets.token_urlsafe(16), secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT INTO projects VALUES (?,?,?)', (project, digest(token), '{}'))
        return project, token

    def authenticate(self, project, token):
        with self.connect() as db:
            row = db.execute('SELECT token_hash FROM projects WHERE id=?', (project,)).fetchone()
        return bool(row and secrets.compare_digest(row[0], digest(token)))

    def save(self, project, payload):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT payload FROM projects WHERE id=?', (project,)).fetchone()
            # Research checkpoints and stale sessions cannot overwrite reviewed records.
            saved = {r['row_id']: r for r in json.loads(current[0]).get('results', [])} if current else {}
            if 'results' in payload:
                payload['results'] = [saved.get(r['row_id'], r) if saved.get(r['row_id'], {}).get('decision')
                                      else r for r in payload['results']]
            db.execute('UPDATE projects SET payload=? WHERE id=?', (json.dumps(payload), project))

    def load(self, project):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM projects WHERE id=?', (project,)).fetchone()
        return json.loads(row[0]) if row else {}

    def get_cache(self, project, key):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM cache WHERE project=? AND key=? AND expires>?',
                             (project, key, datetime.now(timezone.utc).timestamp())).fetchone()
        return json.loads(row[0]) if row else None

    def put_cache(self, project, key, payload, ttl_days=30):
        expires = datetime.now(timezone.utc).timestamp() + ttl_days * 86400
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?,?)',
                       (project, key, expires, json.dumps(payload)))

    def audit(self, project):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM audit WHERE project=? ORDER BY id', (project,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def commit_review(self, project, payload, event):
        # Decision, checkpoint and audit event are committed in one transaction.
        with self.connect() as db:
            db.execute('INSERT INTO audit(project,payload) VALUES (?,?)', (project, json.dumps(event)))
            db.execute('UPDATE projects SET payload=? WHERE id=?', (json.dumps(payload), project))

    def review(self, project, row_id, action, reviewer, notes='', manual_value='', source_value='',
               selected_source_row=None, selection_version='', confirmed=False):
        """Validate and change one persisted row atomically, never a name-based selection."""
        from .review import (decide, manual_options, source_suggestion,
                             suggestion_version, validate_suggestion_approval)
        import polars as pl
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM projects WHERE id=?', (project,)).fetchone()
            if not row:
                raise ValueError('Workspace not found.')
            payload = json.loads(row[0])
            records = payload.get('results', [])
            index = next((i for i, r in enumerate(records) if r['row_id'] == row_id), None)
            if index is None:
                raise ValueError('The selected record no longer exists.')
            result = Result(**records[index])
            selection = None
            if action in ('Approve', 'Approve proposal') and selected_source_row is not None:
                if not confirmed:
                    raise ValueError('Confirm you have verified this selected Source account and field value.')
                if selection_version != suggestion_version(result, payload):
                    raise ValueError('The account or Source dataset changed. Reload and select the suggestion again.')
                selection = source_suggestion(result, payload, selected_source_row)
                validate_suggestion_approval(result, payload, selection)
            column = payload.get('mapping', {}).get('source_value')
            options = manual_options(pl.DataFrame(payload['source'], infer_schema_length=None), column, result.candidates) if column else []
            event = decide(result, action, reviewer, notes, manual_value, source_value, options, selection)
            records[index] = result.dict()
            payload['reviewer_name'] = reviewer.strip()
            db.execute('INSERT INTO audit(project,payload) VALUES (?,?)', (project, json.dumps(event)))
            db.execute('UPDATE projects SET payload=? WHERE id=?', (json.dumps(payload), project))
        return payload

    def bulk_review(self, project, row_ids, action, reviewer, notes='', confirmed=False,
                    overwrite_versions=None):
        """Review persisted row IDs with per-row validation and one atomic checkpoint."""
        from .review import decide, bulk_approval_error
        if action not in ('Approve', 'Reject'):
            raise ValueError('Bulk review supports only Approve and Reject.')
        if not reviewer.strip():
            raise ValueError('Enter a reviewer name.')
        if action == 'Approve' and not confirmed:
            raise ValueError('Confirm you have verified every selected account and field value.')
        selected = list(dict.fromkeys(row_ids))
        if not selected:
            raise ValueError('Select at least one account.')
        saved, skipped = [], []
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM projects WHERE id=?', (project,)).fetchone()
            if not row:
                raise ValueError('Workspace not found.')
            payload = json.loads(row[0])
            records = payload.get('results', [])
            by_id = {r['row_id']: i for i, r in enumerate(records)}
            # Confirm the exact saved versions shown in the UI, including concurrent edits.
            for row_id in selected:
                if row_id in by_id:
                    current = records[by_id[row_id]]
                    if current.get('decision') and (overwrite_versions or {}).get(row_id) != digest(Result(**current).dict()):
                        raise ValueError('Confirm overwriting existing saved decisions. Reload if a decision changed.')
            for row_id in selected:
                if row_id not in by_id:
                    skipped.append({'row_id': row_id, 'identifier': '', 'reason': 'Record no longer exists.'})
                    continue
                index = by_id[row_id]
                result = Result(**records[index])
                try:
                    if action == 'Approve':
                        reason = bulk_approval_error(result, payload)
                        if reason:
                            raise ValueError(reason)
                    event = decide(result, action, reviewer, notes)
                except ValueError as error:
                    skipped.append({'row_id': row_id, 'identifier': result.identifier, 'reason': str(error)})
                    continue
                records[index] = result.dict()
                db.execute('INSERT INTO audit(project,payload) VALUES (?,?)', (project, json.dumps(event)))
                saved.append(row_id)
            if saved:
                payload['reviewer_name'] = reviewer.strip()
                db.execute('UPDATE projects SET payload=? WHERE id=?', (json.dumps(payload), project))
        return payload, {'saved': saved, 'skipped': skipped}
