"""Paged company-name workspace. No provider requests occur in read paths."""
import json
import hashlib
from pathlib import Path
from .storage import digest
from .translation import DATASETS, cell_key, revision, detection_options
from .google_detection import plan_detection, run_detection

LOADED_BUILD = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def row_id(item):
    return digest(cell_key(item))


def merge_selection(selections, page_snapshot, changes):
    """Apply explicit checkbox deltas against the immutable page's stable IDs.

    Missing checkbox entries mean unchanged, never deselected. Positions are only
    the editor wire format; they never identify a record outside this snapshot.
    """
    output = dict(selections)
    for position, edits in changes.items():
        try:
            index = int(position)
        except (ValueError, TypeError):
            continue
        if isinstance(position, bool) or not 0 <= index < len(page_snapshot) or not isinstance(edits, dict):
            continue
        checked = edits.get('Select')
        if not isinstance(checked, bool):
            continue
        item = page_snapshot[index]
        key = row_id(item)
        if checked:
            output.setdefault(key, item)
        else:
            output.pop(key, None)
    return output


def selection_locations(records):
    """Compact row manifest for the authorized batch and remaining selection."""
    from itertools import groupby
    groups = {}
    for item in records:
        groups.setdefault((item['dataset'], item['field']), set()).add(item['row_id'] + 1)
    labels = []
    for (dataset, field), rows in sorted(groups.items()):
        runs = []
        for _, group in groupby(enumerate(sorted(rows)), lambda pair: pair[1] - pair[0]):
            values = [number for _, number in group]
            runs.append(str(values[0]) if len(values) == 1 else f'{values[0]}–{values[-1]}')
        labels.append(f'{dataset.title()} · {field} rows {", ".join(runs)}')
    return '; '.join(labels) or 'none'


class TranslationWorkspace:
    def __init__(self, engine):
        self.engine, self.store, self.project = engine, engine.store, engine.project
        self.payload = self.store.load(self.project)
        self.revisions = {d: revision(self.payload, d) for d in DATASETS}
        self.fields = {d: [f for f in self.payload.get('translation_fields', {}).get(d, [])
                          if detection_options(self.payload, d, f)[0] == 'account_name'] for d in DATASETS}

    def where(self, dataset='All', search='', status='All'):
        scopes, values = [], [self.project]
        for d in DATASETS:
            fields = self.fields[d]
            if fields and dataset in ('All', d.title()):
                scopes.append('(dataset=? AND revision=? AND field IN (' + ','.join('?' for _ in fields) + '))')
                values.extend([d, self.revisions[d], *fields])
        query = 'project=? AND (' + (' OR '.join(scopes) or '0') + ')'
        if search:
            query += " AND (instr(rta_casefold(json_extract(payload,'$.original')),?)>0 OR instr(rta_casefold(json_extract(payload,'$.english')),?)>0)"
            values.extend([search.casefold(), search.casefold()])
        if status != 'All':
            query += " AND json_extract(payload,'$.status')=?"
            values.append(status)
        return query, values

    def page(self, dataset='All', search='', status='All', page=1, size=25):
        if size not in (25, 50, 100):
            raise ValueError('Choose a page size of 25, 50 or 100.')
        where, values = self.where(dataset, search, status)
        with self.store.connect() as db:
            db.create_function('rta_casefold', 1, lambda value: (value or '').casefold(), deterministic=True)
            total = db.execute('SELECT count(*) FROM translations WHERE ' + where, values).fetchone()[0]
            page = max(1, min(page, max(1, (total + size - 1) // size)))
            rows = db.execute('SELECT payload FROM translations WHERE ' + where +
                              ' ORDER BY dataset,row_id,field LIMIT ? OFFSET ?',
                              [*values, size, (page - 1) * size]).fetchall()
        return [json.loads(row[0]) for row in rows], total, page

    def selected(self, snapshots):
        """Drop removed/re-uploaded rows; retain snapshots for optimistic decisions."""
        selected = []
        self.stale_selected = []
        with self.store.connect() as db:
            for key, item in snapshots.items():
                if (item['revision'] != self.revisions.get(item['dataset']) or
                        item['field'] not in self.fields.get(item['dataset'], [])):
                    continue
                row = db.execute('SELECT payload FROM translations WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                                 (self.project, *cell_key(item))).fetchone()
                if row:
                    selected.append(item)
                    if json.loads(row[0]) != item:
                        self.stale_selected.append(key)
        return selected

    def current(self, snapshots):
        """Read committed outcomes without replacing optimistic review snapshots."""
        output = []
        with self.store.connect() as db:
            for item in snapshots:
                row = db.execute('SELECT payload FROM translations WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                                 (self.project, *cell_key(item))).fetchone()
                if row:
                    output.append(json.loads(row[0]))
        return output

    def records(self):
        # Only the columns needed by detection planning; deduplicate in SQLite.
        where, values = self.where()
        projection = {key: f"json_extract(payload,'$.{key}')" for key in
                      ('original', 'field_kind', 'status', 'reviewer', 'reviewed_at',
                       'language_confirmed', 'correction', 'language_reviewer', 'language_reviewed_at', 'translation_excluded')}
        with self.store.connect() as db:
            rows = db.execute('SELECT DISTINCT dataset,' + ','.join(projection.values()) +
                              ' FROM translations WHERE ' + where + ' ORDER BY dataset', values).fetchall()
        return [dict(zip(['dataset', *projection], row)) for row in rows]

    def detect(self, fields, **kwargs):
        outcomes = kwargs.get('google_results', {})
        # Apply only this batch. Other current and historical records stay intact.
        return self.engine.detect(fields, **kwargs, texts=set(outcomes), return_records=False, preserve_drafts=True)

    def detection_plan(self, limit, *, dataset='All', search='', status='All', selection=None):
        scope = DetectionScope(self.engine, dataset, search, status, selection)
        plan = plan_detection(scope, list(DATASETS), limit)
        return {**plan, 'records_in_scope': len(scope.cells), 'scope_signature': scope.signature}


    def run_detection(self, limit, consent, progress=None, *, dataset='All', search='', status='All', selection=None, preview=None):
        current = TranslationWorkspace(self.engine)
        if current.revisions != self.revisions or current.fields != self.fields:
            raise ValueError('Selected datasets changed. Review a new detection preview.')
        scope = DetectionScope(self.engine, dataset, search, status, selection)
        scope.expected_signature = preview.get('scope_signature') if preview is not None else None
        return run_detection(scope, list(DATASETS), consent=consent, limit=limit,
                             progress=progress, expected_plan=preview)


class DetectionScope(TranslationWorkspace):
    """SQL table filters plus stable checked cell identities, across every page."""
    def __init__(self, engine, dataset, search, status, selection):
        super().__init__(engine)
        self.filters = (dataset, search, status)
        self.selection = selection
        self.expected_signature = None
        self.cells = set()

    def records(self):
        where, values = self.where(*self.filters)
        keys = ('original', 'field_kind', 'status', 'reviewer', 'reviewed_at',
                'language_confirmed', 'correction', 'language_reviewer',
                'language_reviewed_at', 'translation_excluded')
        with self.store.connect() as db:
            if self.selection is not None:
                db.execute('CREATE TEMP TABLE detection_selection(dataset, revision, row_id, field, PRIMARY KEY(dataset,revision,row_id,field))')
                db.executemany('INSERT OR IGNORE INTO detection_selection VALUES (?,?,?,?)',
                               [cell_key(item) for item in self.selection])
                where += ' AND EXISTS (SELECT 1 FROM detection_selection s WHERE s.dataset=translations.dataset AND s.revision=translations.revision AND s.row_id=translations.row_id AND s.field=translations.field)'
            db.create_function('rta_casefold', 1, lambda value: (value or '').casefold(), deterministic=True)
            rows = db.execute('SELECT dataset,revision,row_id,field,' +
                ','.join(f"json_extract(payload,'$.{key}')" for key in keys) +
                ' FROM translations WHERE ' + where + ' ORDER BY dataset,row_id,field', values).fetchall()
        self.cells = {tuple(row[:4]) for row in rows}
        self.signature = digest([self.filters, sorted(self.cells)])
        if self.expected_signature is not None and self.signature != self.expected_signature:
            raise ValueError('Detection selection changed. Review and authorize a new preview.')
        return [dict(zip(('dataset', 'revision', 'row_id', 'field', *keys), row)) for row in rows]

    def detect(self, fields, **kwargs):
        outcomes = kwargs.get('google_results', {})
        return self.engine.detect(fields, **kwargs, texts=set(outcomes), cells=self.cells,
                                  return_records=False, preserve_drafts=True, preserve_selection=True)
