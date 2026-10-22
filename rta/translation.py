"""Offline detection and project-scoped translation drafts, corrections and approvals.

Uploads are immutable. Each cell has its own review state; cache entries are drafts,
never approvals. External provider calls happen only in explicitly started batches.
"""
from collections import Counter
import hashlib
from pathlib import Path
import json
import re
from itertools import zip_longest

from .storage import digest, now
from .translation_diagnostics import event
from .google_languages import supported_language, LOADED_BUILD as GOOGLE_SUPPORT_BUILD
from .google_detection import provider_for, CLASSIFICATION_POLICY, GOOGLE_BUILD, google_runtime_info, OFFLINE_SOURCE, interpret, cached_result
from .language_detection import (detect_text, field_kind, vocabulary, VERSION, RULES_FINGERPRINT, runtime_info, ENGLISH, FOREIGN, AMBIGUOUS, EXCLUDED, FIELD_KINDS)

STATUSES = ['Not Required', 'Translation Needed', 'Translated — Review', 'Uncertain', 'Failed', 'Approved Translation', 'Excluded', 'Rejected Translation']
ACTIONABLE = {'Translation Needed', 'Failed'}
DATASETS = ('master', 'source')
POLICY = 'preserve-names-and-identifiers-v1'
LOADED_BUILD = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def detection_options(payload, dataset, field):
    settings = payload.get('language_detection_settings', {})
    kind = settings.get('field_types', {}).get(dataset, {}).get(field) or field_kind(field, payload.get('mapping'), dataset)
    enabled = field in settings.get('enabled_classifications', {}).get(dataset, [])
    words = vocabulary(settings.get('business_vocabulary'))
    provider = provider_for(payload)
    signature = digest([provider, CLASSIFICATION_POLICY if provider == 'google' else VERSION,
                        GOOGLE_BUILD if provider == 'google' else RULES_FINGERPRINT, RULES_FINGERPRINT, kind, enabled, words,
                        GOOGLE_SUPPORT_BUILD if provider == 'google' else 'offline'])
    return kind, enabled, words, signature


def default_fields(payload, dataset):
    return [field for field in payload.get(f'{dataset}_schema', {})
            if detection_options(payload, dataset, field)[0] in ('account_name', 'description', 'free_text')]


def translation_eligible(item):
    return (item['status'] in ACTIONABLE and not item.get('translation_excluded')
            and item['language'] not in ('und', 'en')
            and (item.get('detection_provider') != 'google' or supported_language(item['language']) is not None)
            and (item.get('language_confirmed') or item.get('detection_outcome') == FOREIGN))


def reviewed_translation(item):
    return bool(item['status'] == 'Approved Translation' or item.get('language_confirmed') or item.get('correction')
                or (item.get('reviewer') and item.get('reviewed_at'))
                or (item.get('language_reviewer') and item.get('language_reviewed_at')))


def revision(payload, dataset):
    if dataset not in DATASETS or dataset not in payload:
        raise ValueError('Choose an uploaded Master or Source dataset.')
    return digest(payload[dataset])



def cell_key(item):
    return item['dataset'], item['revision'], item['row_id'], item['field']


def cache_key(text, language, provider):
    return digest([text, language, 'en', provider.name, provider.model, POLICY])


def english_columns(fields, existing):
    used, names = set(existing), {}
    suffixes = ('', ' language', ' confirmed language', ' status', ' provider')
    for field in fields:
        name = f'{field} (English)'
        while any(name + suffix in used for suffix in suffixes):
            name += ' translation'
        used.update(name + suffix for suffix in suffixes)
        names[field] = name
    return names


class TranslationEngine:
    def __init__(self, store, project):
        self.store, self.project = store, project

    def select_detection_provider(self, provider, *, preserve_drafts=False):
        if provider not in ('google', 'offline'):
            raise ValueError('Choose Google or the explicit offline fallback.')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            payload = self._payload(db)
            payload['language_detection_provider'] = provider
            db.execute('UPDATE projects SET payload=? WHERE id=?', (json.dumps(payload), self.project))
        # Provider changes never send data; Google starts pending until consent.
        return self.detect(payload.get('translation_fields', {}), preserve_drafts=preserve_drafts)

    def configure_detection(self, settings):
        payload = self.store.load(self.project)
        for dataset in DATASETS:
            available = payload.get(f'{dataset}_schema', {})
            overrides = settings.get('field_types', {}).get(dataset, {})
            enabled = settings.get('enabled_classifications', {}).get(dataset, [])
            if any(f not in available or kind not in FIELD_KINDS for f, kind in overrides.items()) or any(f not in available for f in enabled):
                raise ValueError('Choose existing fields and supported detection types.')
        words = settings.get('business_vocabulary')
        if words is not None and (not isinstance(words, list) or any(not isinstance(w, str) for w in words)):
            raise ValueError('Business vocabulary must be a list of terms.')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._payload(db)
            current['language_detection_settings'] = settings
            db.execute('UPDATE projects SET payload=? WHERE id=?', (json.dumps(current), self.project))
        self.detect(current.get('translation_fields', {}))

    def records(self):
        payload = self.store.load(self.project)
        selected = payload.get('translation_fields', {})
        if not any(selected.get(d) for d in DATASETS):
            return []
        output = []
        with self.store.connect() as db:
            for dataset in DATASETS:
                if dataset not in payload:
                    continue
                rows = db.execute('SELECT payload FROM translations WHERE project=? AND dataset=? AND revision=? ORDER BY row_id,field',
                                  (self.project, dataset, revision(payload, dataset))).fetchall()
                output += [r for (raw,) in rows if (r := json.loads(raw))['field'] in selected.get(dataset, [])]
        # Upgrade automatic detections from older policies on the next read, while
        # preserving reviewed translations and manual language confirmations.
        if any(r.get('detection_policy') != detection_options(payload, r['dataset'], r['field'])[3] for r in output):
            return self.detect(selected, preserve_drafts=provider_for(payload) == 'google')
        if provider_for(payload) == 'google':
            from .google_detection import raw_key, decode_cached_result
            pending = {raw_key(text) for text in {r['original'] for r in output
                       if not r.get('google_language') and not r.get('translation_excluded')}}
            if pending:
                with self.store.connect() as db:
                    available = any(key in pending and decode_cached_result(raw) for key, raw in db.execute(
                        'SELECT key,payload FROM language_detection_cache WHERE project=?', (self.project,)))
                if available:
                    return self.detect(selected, preserve_drafts=True)
        return output

    def detect(self, fields, *, force=False, preserve_selection=False, google_results=None, texts=None, return_records=True, preserve_drafts=False, cells=None):
        """Scan both selected datasets equally, retaining existing per-cell reviews."""
        if force and runtime_info()['restart_required']:
            raise ValueError('Restart Streamlit to load the detector on disk before reanalysis.')
        payload = self.store.load(self.project)
        provider = provider_for(payload)
        if provider == 'google' and google_runtime_info()['restart_required']:
            raise ValueError('Restart Streamlit to load the current Google detection policy.')
        fields = {d: list(dict.fromkeys(fields.get(d, []))) for d in DATASETS}
        entries = []
        detected = {}
        analyzed_at = now()
        preserved_reviews = 0
        for dataset in DATASETS:
            rev = revision(payload, dataset)
            available = payload.get(f'{dataset}_schema', {}) or (payload[dataset][0] if payload[dataset] else {})
            if any(field not in available for field in fields[dataset]):
                raise ValueError('A selected translation field no longer exists.')
            generated = english_columns(fields[dataset], available)
            for row_id, row in enumerate(payload[dataset]):
                for field in fields[dataset]:
                    if cells is not None and (dataset, rev, row_id, field) not in cells:
                        continue
                    text = '' if row.get(field) is None else str(row[field])
                    if texts is not None and text not in texts:
                        continue
                    kind, enabled, words, signature = detection_options(payload, dataset, field)
                    key = digest([signature, text])
                    if key not in detected:
                        cached = None
                        # Google raw responses are authoritative. An older
                        # interpreted pending result must not mask a new raw cache.
                        if not force and provider != 'google':
                            with self.store.connect() as db:
                                cached = db.execute('SELECT payload FROM language_detection_cache WHERE project=? AND key=?',
                                                    (self.project, key)).fetchone()
                        if cached:
                            detected[key] = json.loads(cached[0])
                        else:
                            if provider == 'google':
                                raw = (google_results or {}).get(text) or cached_result(self.store, self.project, text)
                                detected[key] = interpret(text, kind, enabled, raw)
                            else:
                                detected[key] = {**(detect_text(text, kind, words, enabled, refresh=True) if force else detect_text(text, kind, words, enabled)),
                                                 'detection_provider': 'offline', 'detection_source': OFFLINE_SOURCE,
                                                 'google_language': '', 'google_confidence': None}
                            if provider == 'offline' or detected[key].get('google_language'):
                                with self.store.connect() as db:
                                    db.execute('INSERT OR REPLACE INTO language_detection_cache VALUES (?,?,?)',
                                               (self.project, key, json.dumps(detected[key])))
                    detection = detected[key]
                    entries.append({'dataset': dataset, 'revision': rev, 'row_id': row_id, 'field': field,
                        'original': text, 'english': '', 'english_field': generated[field], **detection,
                        'detected_language': detection['language'],
                        'field_kind': kind, 'detection_policy': signature,
                        'detection_version': CLASSIFICATION_POLICY if provider == 'google' else VERSION,
                        'detection_build': GOOGLE_BUILD if provider == 'google' else RULES_FINGERPRINT,
                        'detection_analyzed_at': analyzed_at,
                        'automatic_detection_outcome': detection['detection_outcome'], 'automatic_reason': detection['reason'],
                        'translation_excluded': kind == 'identifier' or (kind == 'classification' and not enabled),
                        'language_classification': detection.get('language_classification', detection['detection_outcome']),
                        'language_review_required': detection.get('language_review_required', detection['status'] == 'Uncertain'),
                        'language_review_reason': detection.get('language_review_reason', ''),
                        'provider': '', 'model': '', 'reviewer': '', 'reviewed_at': '', 'cache_hit': False})
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._payload(db)
            if any(revision(current, d) != revision(payload, d) for d in DATASETS):
                raise ValueError('Datasets changed during detection. Scan again.')
            if current.get('language_detection_settings') != payload.get('language_detection_settings'):
                raise ValueError('Detection settings changed. Scan again.')
            if provider_for(current) != provider:
                raise ValueError('Detection provider changed. Scan again.')
            for item in entries:
                saved = db.execute('SELECT payload FROM translations WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                                   (self.project, *cell_key(item))).fetchone()
                if saved:
                    previous = json.loads(saved[0])
                    if (not force and previous.get('detection_policy') == item['detection_policy'] and
                            (previous.get('google_language') or not item.get('google_language'))):
                        continue
                    metadata = ('field_kind', 'detection_policy', 'translation_excluded', 'detected_language', 'confidence',
                                'detector_language', 'detector_confidence', 'detection_version', 'detection_build',
                                'detection_analyzed_at', 'automatic_detection_outcome', 'automatic_reason',
                                'detection_provider', 'detection_source', 'google_language', 'google_confidence',
                                'language_classification', 'language_review_required', 'language_review_reason')
                    updated = {**previous, **{k: item[k] for k in metadata}}
                    updated.setdefault('detection_outcome', ENGLISH if previous['language'] == 'en' else
                                       AMBIGUOUS if previous['language'] == 'und' else FOREIGN)
                    keep_draft = preserve_drafts and previous['status'] == 'Translated — Review' and bool(previous.get('english'))
                    if reviewed_translation(previous) or keep_draft:
                        preserved_reviews += 1
                        if keep_draft and not previous.get('language_confirmed'):
                            conflict = item['language'] != previous['language'] or item['status'] == 'Uncertain'
                            updated['draft_language_review_required'] = conflict
                            if conflict:
                                updated.update(language_review_required=True,
                                    language_review_reason='Existing draft retained; confirm its source language before approval.')
                    else:
                        updated.update({k: item[k] for k in ('language', 'detected_language', 'confidence', 'detection_outcome', 'detector_language', 'detector_confidence', 'reason')})
                        if item['status'] != 'Translation Needed' or previous['status'] not in ('Translated — Review', 'Failed'):
                            updated['status'] = item['status']
                        if item['status'] != 'Translation Needed' and previous.get('english'):
                            updated.update(draft_english=previous['english'], english='', provider='', model='', cache_hit=False)
                        elif previous['language'] != item['language'] and previous.get('english'):
                            updated.update(draft_english=previous['english'], english='', provider='', model='', cache_hit=False,
                                           status=item['status'])
                    item = updated
                db.execute('INSERT OR REPLACE INTO translations VALUES (?,?,?,?,?,?)',
                           (self.project, *cell_key(item), json.dumps(item)))
            if not preserve_selection:
                current['translation_fields'] = fields
            if force:
                current['translation_detection_refresh'] = {'analyzed_at': analyzed_at, 'policy': CLASSIFICATION_POLICY if provider == 'google' else VERSION,
                    'build': GOOGLE_BUILD if provider == 'google' else RULES_FINGERPRINT,
                    'cells_analyzed': len(entries), 'unique_values_analyzed': len(detected),
                    'preserved_reviews': preserved_reviews, 'fields': fields,
                    'scope': 'Current dataset revisions; human review and decisions preserved.'}
            db.execute('UPDATE projects SET payload=? WHERE id=?', (json.dumps(current), self.project))
        return self.records() if return_records else None

    def reanalyse(self):
        """Recompute only this workspace's current values, including deselected
        stored fields. Bypass every detection cache without clearing any cache,
        changing selection, or touching older revisions or human decisions.
        """
        payload = self.store.load(self.project)
        fields = {d: list(payload.get('translation_fields', {}).get(d, [])) for d in DATASETS}
        with self.store.connect() as db:
            for dataset in DATASETS:
                if dataset not in payload:
                    continue
                existing = db.execute('SELECT DISTINCT field FROM translations WHERE project=? AND dataset=? AND revision=?',
                                      (self.project, dataset, revision(payload, dataset))).fetchall()
                available = payload.get(f'{dataset}_schema', {})
                fields[dataset] = list(dict.fromkeys(fields[dataset] + [field for (field,) in existing if field in available]))
        self.detect(fields, force=True, preserve_selection=True)
        return self.store.load(self.project)['translation_detection_refresh']

    def export_records(self):
        """Only current selected enabled cells, never audit/history/deselected fields."""
        return [item for item in self.records() if not item.get('translation_excluded') and item['status'] != 'Excluded']

    def detection_inventory(self, records=None):
        """Current selection versus retained history; no network or history edits."""
        payload = self.store.load(self.project)
        records = self.records() if records is None else records
        revisions = {d: revision(payload, d) for d in DATASETS if d in payload}
        historical = unselected = 0
        with self.store.connect() as db:
            groups = db.execute('SELECT dataset,revision,field,COUNT(*) FROM translations WHERE project=? GROUP BY dataset,revision,field',
                                (self.project,)).fetchall()
        for dataset, rev, field, count in groups:
            if rev != revisions.get(dataset):
                historical += count
            elif field not in payload.get('translation_fields', {}).get(dataset, []):
                unselected += count
        return {'current_selected': len(records), 'historical_revision': historical,
                'current_unselected': unselected,
                'excluded_selected': sum(bool(r.get('translation_excluded')) for r in records),
                'google_results': sum(bool(r.get('google_language')) for r in records),
                'google_pending': sum(r.get('detection_provider') == 'google' and not r.get('google_language')
                                      and not r.get('translation_excluded') for r in records)}

    def _payload(self, db):
        row = db.execute('SELECT payload FROM projects WHERE id=?', (self.project,)).fetchone()
        if not row:
            raise ValueError('Workspace not found.')
        return json.loads(row[0])

    def _commit_cell(self, expected, updated, event=None):
        self._commit_cells([(expected, updated, event)])

    def _commit_cells(self, changes):
        """Atomic optimistic review, including selected bulk operations."""
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            payload = self._payload(db)
            revisions = {d: revision(payload, d) for d in DATASETS}
            for expected, updated, event in changes:
                if revisions[expected['dataset']] != expected['revision'] or expected['field'] not in payload.get('translation_fields', {}).get(expected['dataset'], []):
                    raise ValueError('Dataset or selected fields changed. Scan again.')
                row = db.execute('SELECT payload FROM translations WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                                 (self.project, *cell_key(expected))).fetchone()
                if not row or json.loads(row[0]) != expected:
                    raise ValueError('This translation changed. Reload before saving.')
                db.execute('UPDATE translations SET payload=? WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                           (json.dumps(updated), self.project, *cell_key(expected)))
                if event:
                    db.execute('INSERT INTO audit(project,payload) VALUES (?,?)', (self.project, json.dumps(event)))

    def plan(self, datasets, provider, allow_names=True, limit=250, include_uncertain=False, selection=None):
        """Cache-aware draft eligibility; name permission never grants paid consent."""
        if not datasets or not set(datasets) <= set(DATASETS) or not 1 <= limit <= 5000:
            raise ValueError('Choose datasets and a limit from 1 to 5000 unique texts.')
        mapping = self.store.load(self.project).get('mapping', {})
        records = self.records() if selection is None else selection
        ordered = [r for pair in zip_longest(*[[r for r in records if r['dataset'] == d and d in datasets]
                   for d in DATASETS]) for r in pair if r is not None]
        identities = []
        selected_records = [r for r in records if r['dataset'] in datasets]
        diagnostics = {'detected_foreign_records': sum(
            r.get('automatic_detection_outcome', r.get('detection_outcome')) == FOREIGN or
            (bool(r.get('language_confirmed')) and r['language'] not in ('en', 'und')) for r in selected_records),
            'eligible_records': 0, 'name_permission_excluded_records': 0,
            'manual_review_records': sum(not r.get('translation_excluded') and
                (r.get('language_review_required') or r['status'] == 'Uncertain' or (r['language'] == 'und' and r['status'] in ACTIONABLE)) for r in selected_records),
            'blocked_language_records': sum(not r.get('translation_excluded') and
                (r['status'] == 'Uncertain' or (r['language'] == 'und' and r['status'] in ACTIONABLE)) for r in selected_records),
            'approved_records': sum(r['status'] == 'Approved Translation' for r in selected_records),
            'draft_review_records': sum(r['status'] == 'Translated — Review' for r in selected_records),
            'excluded_records': sum(bool(r.get('translation_excluded')) or r['status'] == 'Excluded' for r in selected_records)}
        seen = set()
        for r in ordered:
            name = r.get('field_kind') == 'account_name' or r['field'] == mapping.get(f"{r['dataset']}_id")
            identity = (r['original'], r['language'])
            if translation_eligible(r) and (selection is None or not r.get('english')):
                if name and not allow_names:
                    diagnostics['name_permission_excluded_records'] += 1
                else:
                    diagnostics['eligible_records'] += 1
                    if identity not in seen:
                        seen.add(identity)
                        identities.append(identity)
        diagnostics['eligible_unique_texts'] = len(identities)
        all_identities = list(identities)
        identities = identities[:limit]
        uncached = []
        with self.store.connect() as db:
            for text, code in identities:
                if not db.execute('SELECT 1 FROM translation_cache WHERE project=? AND key=?',
                                  (self.project, cache_key(text, code, provider))).fetchone():
                    uncached.append((text, code))
        characters = sum(len(text) for text, _ in uncached)
        return {'identities': identities, 'uncached': uncached, 'unique_texts': len(identities),
                'eligibility': diagnostics,
                'remaining_unique_texts': len(all_identities) - len(identities),
                'cached_texts': len(identities) - len(uncached), 'characters': characters,
                'total_characters': sum(len(text) for text, _ in identities),
                'estimated_usd': characters * getattr(provider, 'rate_per_million', 0) / 1_000_000}

    def process(self, datasets, provider, fallback=None, allow_names=True, limit=250, progress=None, include_uncertain=False, selection=None):
        if not set(datasets) <= set(DATASETS) or not datasets:
            raise ValueError('Choose Master, Source, or both.')
        if not 1 <= limit <= 5000:
            raise ValueError('Choose a batch limit from 1 to 5000 unique texts.')
        if selection is not None:
            # Validate the exact selected snapshots before any provider dispatch.
            self._commit_cells([(item, item, None) for item in selection])
        plan = self.plan(datasets, provider, allow_names, limit, include_uncertain, selection)
        event('backend_plan', eligible_rows=plan['eligibility']['eligible_records'], names=plan['unique_texts'])
        if hasattr(provider, 'prepare'):
            if hasattr(provider, 'bind_usage'):
                provider.bind_usage(self.store, self.project)
            provider.prepare(plan['uncached'])
        payload = self.store.load(self.project)
        mapping = payload.get('mapping', {})
        attempted, drafts, failed = {}, 0, 0
        selected_identities = set(plan['identities'])
        records = [r for r in (self.records() if selection is None else selection) if r['dataset'] in datasets and translation_eligible(r)
                   and (selection is None or not r.get('english'))
                   and (r['original'], r['language']) in selected_identities]
        # A shared batch limit must not starve Source behind a large Master dataset.
        records = [r for pair in zip_longest(*[[r for r in records if r['dataset'] == d] for d in DATASETS])
                   for r in pair if r is not None]
        seen = set()
        for number, item in enumerate(records):
            updated = dict(item)
            name_field = item.get('field_kind') == 'account_name' or item['field'] == mapping.get(f"{item['dataset']}_id")
            if name_field and not allow_names:
                # Draft permission is separate from language confidence.
                continue
            elif item['language'] in ('und', 'en'):
                updated.update(status='Uncertain', reason='Confirm the source language or enter a reviewed English value.')
            else:
                identity = (item['original'], item['language'])
                if identity not in attempted:
                    if len(attempted) >= limit:
                        continue
                    outcome = None
                    for selected in (provider, fallback):
                        if selected is None:
                            continue
                        key = cache_key(item['original'], item['language'], selected)
                        with self.store.connect() as db:
                            cached = db.execute('SELECT payload FROM translation_cache WHERE project=? AND key=?', (self.project, key)).fetchone()
                        try:
                            if cached:
                                event('translation_cache_reused', cache_hit=True)
                                outcome = {**json.loads(cached[0]), 'cache_hit': True}
                            else:
                                english = selected.translate(item['original'], item['language'])
                                if not isinstance(english, str) or not english.strip():
                                    raise ValueError('Empty translation.')
                                protected = re.findall(r'\b[\w.-]*\d[\w.-]*\b|\b(?:Inc|Ltd|LLC|GmbH|PLC)\b', item['original'])
                                if any(token not in english for token in protected):
                                    event('translation_validation_failed', error_code='protected_identifier_changed')
                                    raise ValueError('Protected identifier or legal suffix changed.')
                                outcome = {'english': english.strip(), 'provider': selected.name, 'model': selected.model,
                                           'status': 'Translated — Review', 'reason': '', 'cache_hit': False}
                                with self.store.connect() as db:
                                    db.execute('INSERT OR REPLACE INTO translation_cache VALUES (?,?,?)', (self.project, key, json.dumps(outcome)))
                            break
                        except (ValueError, RuntimeError, OSError):
                            outcome = None
                    attempted[identity] = outcome or {'status': 'Failed', 'reason': 'Translation unavailable or failed. Check models/limits, retry, or correct manually.'}
                updated.update(attempted[identity])
                if identity in seen and updated['status'] == 'Translated — Review':
                    updated['cache_hit'] = True
                seen.add(identity)
                drafts += updated['status'] == 'Translated — Review'
                failed += updated['status'] == 'Failed'
            self._commit_cell(item, updated)
            event('translation_record_persisted', drafts=int(updated['status'] == 'Translated — Review'),
                  failed=int(updated['status'] == 'Failed'), persisted=1)
            if progress:
                progress((number + 1) / max(1, len(records)))
        if selection is not None:
            with self.store.connect() as db:
                selection = [json.loads(row[0]) for item in selection if (row := db.execute(
                    'SELECT payload FROM translations WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                    (self.project, *cell_key(item))).fetchone())]
        remaining = self.plan(datasets, provider, allow_names, limit, include_uncertain, selection)
        event('backend_completed', drafts=drafts, failed=failed,
              remaining=remaining['eligibility']['eligible_unique_texts'])
        return {'drafts': drafts, 'failed': failed, 'unique_attempts': len(attempted),
                'remaining_unique_texts': remaining['eligibility']['eligible_unique_texts']}

    def confirm_language(self, expected, language, reviewer, confirmed):
        if not reviewer.strip() or not confirmed:
            raise ValueError('Enter a reviewer and explicitly confirm the source language.')
        if expected.get('detection_provider') == 'google':
            language = supported_language(language)
            if language is None:
                raise ValueError('Confirm a supported Google NMT source-language code; unsupported and und codes cannot be submitted.')
        if not language or not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]+)?', language) or language == 'und':
            raise ValueError('Confirm a known two or three letter language code; und is not a confirmed language.')
        if expected.get('translation_excluded'):
            raise ValueError('Enable this field for translation in detection settings first.')
        if expected['status'] == 'Approved Translation':
            raise ValueError('An approved translation must be corrected through translation review.')
        updated = {**expected, 'language': language, 'language_confirmed': True,
                   'language_reviewer': reviewer.strip(), 'language_reviewed_at': now(),
                   'status': 'Not Required' if language == 'en' else 'Translation Needed',
                   'detection_outcome': ENGLISH if language == 'en' else FOREIGN,
                   'reason': 'Source language explicitly confirmed by a reviewer.'}
        if expected.get('draft_language_review_required'):
            updated['draft_language_review_required'] = False
            if expected.get('english') and language == expected['language']:
                updated['status'] = 'Translated — Review'
        if language != expected['language'] or language == 'en':
            updated.update(draft_english=expected.get('english', ''), english='', provider='', model='', cache_hit=False)
        self._commit_cell(expected, updated, {'event_type': 'translation_language_review',
            'decision': 'Confirm source language', 'reviewer': reviewer.strip(), 'timestamp': updated['language_reviewed_at'],
            'dataset': expected['dataset'], 'row_id': expected['row_id'], 'field': expected['field'],
            'previous_translation': expected, 'translation': updated})
        return updated

    def approve(self, expected, english, reviewer, confirmed, language=None):
        if expected.get('translation_excluded'):
            raise ValueError('Enable this field for translation in detection settings first.')
        if not reviewer.strip() or not confirmed:
            raise ValueError('Enter a reviewer and confirm this translation, including proper names and identifiers.')
        if not isinstance(english, str) or not english.strip():
            raise ValueError('Enter the reviewed English translation.')
        if expected['status'] == 'Not Required' and (language in (None, 'en', 'und') or not any(c.isalpha() for c in expected['original'])):
            raise ValueError('This value does not require translation.')
        if language is not None and not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]+)?', language):
            raise ValueError('Use a two or three letter source-language code.')
        updated = {**expected, 'english': english.strip(), 'status': 'Approved Translation',
                   'reviewer': reviewer.strip(), 'reviewed_at': now(), 'reason': ''}
        if language:
            updated['language'] = language
            updated['language_confirmed'] = language != 'und'
            if expected.get('draft_language_review_required') and language != 'und':
                updated['draft_language_review_required'] = False
        if english.strip() != expected.get('english'):
            updated['correction'] = True
            updated.setdefault('draft_english', expected.get('english', ''))
        if not updated['provider']:
            updated.update(provider='Reviewer', model='manual')
        event = {'event_type': 'translation_review', 'dataset': expected['dataset'], 'row_id': expected['row_id'],
                 'field': expected['field'], 'decision': 'Approve translation', 'reviewer': updated['reviewer'],
                 'timestamp': updated['reviewed_at'], 'previous_translation': expected, 'translation': updated}
        self._commit_cell(expected, updated, event)
        return updated

    def mark_not_required(self, expected, reviewer, confirmed):
        if not reviewer.strip() or not confirmed:
            raise ValueError('Enter a reviewer and confirm this value needs no translation.')
        updated = {**expected, 'english': '', 'status': 'Not Required', 'reviewer': reviewer.strip(),
                   'reviewed_at': now(), 'reason': 'Reviewed: original should be preserved without translation.'}
        self._commit_cell(expected, updated, {'event_type': 'translation_review', 'decision': 'Translation not required',
            'dataset': expected['dataset'], 'row_id': expected['row_id'], 'field': expected['field'],
            'reviewer': reviewer.strip(), 'timestamp': updated['reviewed_at'],
            'previous_translation': expected, 'translation': updated})
        return updated

    def reject(self, expected, reviewer, confirmed):
        if not reviewer.strip() or not confirmed:
            raise ValueError('Enter a reviewer and explicitly confirm rejection of this draft.')
        if expected['status'] != 'Translated — Review' or expected.get('translation_excluded'):
            raise ValueError('Only an unapproved translation draft can be rejected.')
        updated = {**expected, 'status': 'Rejected Translation', 'draft_english': expected['english'],
                   'english': '', 'reviewer': reviewer.strip(), 'reviewed_at': now(),
                   'reason': 'Draft rejected by reviewer; correct manually or explicitly confirm language to requeue.'}
        self._commit_cell(expected, updated, {'event_type': 'translation_review', 'decision': 'Reject translation',
            'dataset': expected['dataset'], 'row_id': expected['row_id'], 'field': expected['field'],
            'reviewer': reviewer.strip(), 'timestamp': updated['reviewed_at'],
            'previous_translation': expected, 'translation': updated})
        return updated

    def bulk_approve(self, selected, reviewer, confirmed):
        if not selected or not reviewer.strip() or not confirmed:
            raise ValueError('Select drafts, enter a reviewer and explicitly confirm every selected translation.')
        changes, seen = [], set()
        for item in selected:
            if cell_key(item) in seen:
                raise ValueError('Select each translation once.')
            seen.add(cell_key(item))
            if (item['status'] != 'Translated — Review' or item.get('translation_excluded') or
                    item.get('draft_language_review_required') or
                    not item.get('english', '').strip() or item['language'] in ('en', 'und') or
                    not (item.get('language_confirmed') or item.get('detection_outcome') == FOREIGN)):
                raise ValueError('Bulk approval accepts only known-language, unapproved English drafts.')
            updated = {**item, 'status': 'Approved Translation', 'reviewer': reviewer.strip(),
                       'reviewed_at': now(), 'reason': ''}
            event = {'event_type': 'translation_review', 'decision': 'Approve translation (selected bulk)',
                     'dataset': item['dataset'], 'row_id': item['row_id'], 'field': item['field'],
                     'reviewer': reviewer.strip(), 'timestamp': updated['reviewed_at'],
                     'previous_translation': item, 'translation': updated}
            changes.append((item, updated, event))
        self._commit_cells(changes)
        return len(changes)

    def bulk_reject(self, selected, reviewer, confirmed):
        if not selected or not reviewer.strip() or not confirmed:
            raise ValueError('Select drafts, enter a reviewer and explicitly confirm the selected rejections.')
        changes, seen = [], set()
        for item in selected:
            if cell_key(item) in seen or item['status'] != 'Translated — Review':
                raise ValueError('Select each unapproved translation draft once.')
            seen.add(cell_key(item))
            updated = {**item, 'status': 'Rejected Translation', 'english': '',
                       'draft_english': item['english'], 'reviewer': reviewer.strip(), 'reviewed_at': now(),
                       'reason': 'Draft rejected by reviewer.'}
            event = {'event_type': 'translation_review', 'decision': 'Reject translation (selected bulk)',
                     'dataset': item['dataset'], 'row_id': item['row_id'], 'field': item['field'],
                     'reviewer': reviewer.strip(), 'timestamp': updated['reviewed_at'],
                     'previous_translation': item, 'translation': updated}
            changes.append((item, updated, event))
        self._commit_cells(changes)
        return len(changes)


def company_overview(records):
    """Unique exact company names; every duplicate cell must be covered."""
    groups = {}
    for item in records:
        if item.get('field_kind') == 'account_name' and item['original'].strip() and not item.get('translation_excluded'):
            groups.setdefault(item['original'], []).append(item)
    values = list(groups.values())
    total = len(values)
    english = sum(all(r['language'] == 'en' and r['status'] != 'Uncertain' for r in rows) for rows in values)
    foreign = [rows for rows in values if any(r['language'] not in ('en', 'und') and
               (r.get('language_confirmed') or r.get('detection_outcome') == FOREIGN) for r in rows)]
    detected = sum(all(r.get('google_language') or r.get('language_confirmed') or
                       r.get('detection_provider') == 'offline' or r['status'] == 'Not Required' for r in rows) for rows in values)
    approved = sum(all(r['status'] == 'Approved Translation' for r in rows) for rows in foreign)
    covered = sum(all(r.get('english') and r['status'] in ('Translated — Review', 'Approved Translation') for r in rows) for rows in foreign)
    pending = sum(any(r['status'] == 'Translated — Review' for r in rows) for rows in values)
    ambiguous = sum(any(r['status'] == 'Uncertain' or r.get('language_review_required') for r in rows) for rows in values)
    unprocessed = sum(any(r['status'] in ACTIONABLE or (r['status'] == 'Uncertain' and not r.get('google_language')
                     and not r.get('language_confirmed')) for r in rows) for rows in values)
    return {'Total unique company names': total, 'English names': english, 'Foreign-language names detected': len(foreign),
            'English translation drafts generated': sum(any(r.get('english') for r in rows) for rows in values),
            'Approved translations': approved, 'Pending translation review': pending,
            'Ambiguous names requiring manual language review': ambiguous,
            'Detection coverage (%)': round(100 * detected / total, 2) if total else 0.0,
            'Translation coverage (%)': round(100 * covered / len(foreign), 2) if foreign else 0.0,
            'Remaining undetected names': total - detected, 'Remaining untranslated foreign names': len(foreign) - covered,
            'Remaining unprocessed names': unprocessed}


def translation_metrics(records):
    output = []
    for label, entries in [(d.title(), [r for r in records if r['dataset'] == d]) for d in DATASETS] + [('Combined', records)]:
        counts = Counter(r['status'] for r in entries)
        flagged = [r for r in entries if r['status'] not in ('Not Required', 'Excluded') and not r.get('translation_excluded')]
        output.append({'Dataset': label, 'Selected cells': len(entries), 'Flagged cells': len(flagged),
                       'Unique flagged texts': len({r['original'] for r in flagged}),
                       ENGLISH: sum(r.get('detection_outcome') == ENGLISH and not r.get('translation_excluded') for r in entries),
                       FOREIGN: sum(r.get('detection_outcome') == FOREIGN and not r.get('translation_excluded') for r in entries),
                       AMBIGUOUS: sum(r.get('detection_outcome') == AMBIGUOUS and not r.get('translation_excluded') for r in entries),
                       'Excluded cells': sum(r.get('translation_excluded', False) for r in entries),
                       **{status: counts[status] for status in STATUSES}})
    return output


def translated_rows(payload, dataset, records):
    """Export-only columns; original records are never edited or merged into uploads."""
    rows = [dict(row) for row in payload.get(dataset, [])]
    fields = payload.get('translation_fields', {}).get(dataset, [])
    fields = [field for field in fields if detection_options(payload, dataset, field)[0] != 'identifier'
              and (detection_options(payload, dataset, field)[0] != 'classification'
                   or detection_options(payload, dataset, field)[1])]
    names = english_columns(fields, payload.get(f'{dataset}_schema', {}))
    for row in rows:
        for prefix in names.values():
            row.update({prefix: '', f'{prefix} language': '', f'{prefix} confirmed language': '',
                        f'{prefix} status': 'Not Analysed', f'{prefix} provider': ''})
    for item in records:
        if item['dataset'] == dataset and item['field'] in names:
            row = rows[item['row_id']]
            prefix = names[item['field']]
            row.update({prefix: item['english'], f'{prefix} language': item.get('detected_language', item['language']),
                        f'{prefix} confirmed language': item['language'],
                        f'{prefix} status': item['status'], f'{prefix} provider': item['provider']})
    return rows
