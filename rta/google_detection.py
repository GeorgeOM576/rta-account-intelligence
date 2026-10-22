"""Primary ADC-backed v3 language detection; network only after explicit consent.

Google's API detects one string per request. Raw responses are workspace-cached
separately from local results and field-policy interpretations. No credentials,
uploaded texts or response error bodies are written to usage records or logs.
"""
import math
import re
from itertools import zip_longest
import hashlib
from pathlib import Path

from .language_detection import ENGLISH, FOREIGN, AMBIGUOUS, EXCLUDED, runtime_info
from .google_languages import supported_language, LOADED_BUILD as GOOGLE_SUPPORT_BUILD
from .storage import digest
from .translation_usage import GoogleTranslationUsage, RATE_PER_MILLION

GOOGLE_POLICY = 'google-v3-field-aware-v1'
# Raw API responses remain reusable when only local interpretation changes.
CLASSIFICATION_POLICY = 'google-direct-v4'
GOOGLE_BUILD = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
GOOGLE_SOURCE = 'Google Cloud Translation Advanced v3'
OFFLINE_SOURCE = 'Local offline (explicit fallback)'
# Advisory only: neither this score nor competing alternatives block valid codes.
CONFIDENCE_THRESHOLD = 0.90


def provider_for(payload):
    return 'offline' if payload.get('language_detection_provider') == 'offline' else 'google'


def google_runtime_info():
    previous = runtime_info()
    disk = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {**previous, 'policy': CLASSIFICATION_POLICY, 'loaded_build': GOOGLE_BUILD, 'disk_build': disk,
            'module_path': str(Path(__file__).resolve()),
            'restart_required': previous['restart_required'] or disk != GOOGLE_BUILD or
                hashlib.sha256(Path(__file__).with_name('google_languages.py').read_bytes()).hexdigest() != GOOGLE_SUPPORT_BUILD}


def preflight(text, kind, enabled=False):
    """Structural exclusions only: never invoke langdetect for a Google batch."""
    if kind == 'identifier' or (kind == 'classification' and not enabled):
        return 'Field excluded from language detection and translation.'
    if not text.strip() or not any(c.isalpha() for c in text):
        return 'Blank or nonlinguistic value.'
    if kind == 'account_name':
        return ''  # Brands, abbreviations and legal names belong to Google.
    if re.match(r'^(https?://|www\.|[^\s]+@)', text, re.I):
        return 'URL or email address.'
    if (re.fullmatch(r'[A-Z0-9_./:-]*\d[A-Z0-9_./:-]*', text, re.I)
            or re.fullmatch(r'[A-Z]{2,6}', text)
            or re.fullmatch(r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}', text, re.I)):
        return 'Identifier, abbreviation or date.'
    return ''


def raw_key(text):
    return digest(['google-language-detection', GOOGLE_SOURCE, GOOGLE_POLICY, text])


def cached_result(store, project, text):
    with store.connect() as db:
        row = db.execute('SELECT payload FROM language_detection_cache WHERE project=? AND key=?',
                         (project, raw_key(text))).fetchone()
    if not row:
        return None
    return decode_cached_result(row[0])


def decode_cached_result(payload):
    import json
    try:
        value = json.loads(payload)
        if value.get('provider') != 'google' or value.get('policy') != GOOGLE_POLICY:
            return None
        candidates = [value, *value.get('alternatives', [])]
        if any(not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]+)?', entry['language_code']) or
               (entry.get('confidence') is not None and (isinstance(entry['confidence'], bool) or not math.isfinite(entry['confidence']) or not 0 <= entry['confidence'] <= 1)) for entry in candidates):
            return None
        return value
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def interpret(text, kind, enabled=False, raw=None):
    exclusion = preflight(text, kind, enabled)
    base = {'language': 'und', 'confidence': 0.0, 'status': 'Uncertain',
            'detection_outcome': AMBIGUOUS, 'detector_language': 'und', 'detector_confidence': 0.0,
            'google_language': '', 'google_confidence': None, 'detection_provider': 'google',
            'detection_source': 'Google detection pending — no API request made',
            'language_classification': 'Pending detection or manual language review',
            'language_review_required': True, 'language_review_reason': 'No valid Google language yet',
            'reason': 'Awaiting an explicitly confirmed Google detection batch or manual language review.'}
    if exclusion:
        return {**base, 'status': 'Excluded' if kind in ('classification', 'identifier') else 'Not Required',
                'language_review_required': False, 'language_review_reason': '', 'language_classification': 'Excluded / nonlinguistic',
                'detection_outcome': EXCLUDED, 'reason': exclusion, 'detection_source': 'Field/structural exclusion — no API request'}
    if raw is None:
        return base
    if not isinstance(raw, dict):
        return {**base, 'detection_source': 'Google returned an invalid detection result'}
    if raw.get('failed'):
        return {**base, 'detection_source': 'Google detection failed',
                'reason': 'Detection unavailable; retry in a separately confirmed batch or confirm language manually.'}
    # Validate even injected/raw cache inputs; malformed responses never guess.
    try:
        code = raw['language_code']
        confidence = raw.get('confidence')
        alternatives = raw.get('alternatives', [])
        if not isinstance(code, str) or not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]+)?', code):
            raise ValueError()
        for entry in [raw, *alternatives]:
            if not isinstance(entry.get('language_code'), str) or not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]+)?', entry['language_code']):
                raise ValueError()
            score = entry.get('confidence')
            if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1):
                raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        return {**base, 'detection_source': 'Google returned an invalid detection result',
                'reason': 'Invalid Google response; retry explicitly or confirm a supported language manually.'}
    result = {**base, 'google_language': code, 'google_confidence': confidence,
              'detector_language': code, 'detector_confidence': confidence,
              'detection_source': GOOGLE_SOURCE}
    language = supported_language(code)
    if language is None:
        return {**result, 'reason': 'Google language is unknown or not in the supported NMT snapshot; confirm a supported language manually.'}
    review = []
    if confidence is None or confidence < CONFIDENCE_THRESHOLD:
        review.append('Google confidence is low or unavailable')
    if alternatives and (confidence or 0) - max((entry.get('confidence') or 0 for entry in alternatives
            if entry.get('language_code', '').lower() != code.lower()), default=0) < .20:
        review.append('Google returned competing language suggestions')
    return {**result, 'language': language, 'confidence': confidence if confidence is not None else 0.0,
            'status': 'Not Required' if language == 'en' else 'Translation Needed',
            'detection_outcome': ENGLISH if language == 'en' else FOREIGN,
            'language_classification': 'English — No Translation Needed' if language == 'en' else 'Non-English — Translation Candidate',
            'language_review_required': bool(review), 'language_review_reason': '; '.join(review),
            'reason': ('; '.join(review) + '. Review recommended; valid non-English results remain eligible for authorized translation.') if review
                      else 'Google language accepted. English values need no translation; non-English drafts require human approval.'}


class GoogleDetectionProvider:
    name = GOOGLE_SOURCE
    max_attempts = 1  # timeouts/failures require a new explicitly confirmed run

    def __init__(self, *, consent=False, client=None, usage=None):
        self.consent, self.client, self.usage = consent, client, usage
        self.requests = 0
        self.confirmed_characters = 0
        self.uncertain_characters = 0

    def detect(self, text):
        if not self.consent:
            raise ValueError('Explicit confirmation is required before paid Google detection requests.')
        if not text.strip() or len(text) > 30000:
            raise ValueError('Detection input must contain 1–30,000 characters.')
        if self.client is None:
            try:
                from google.cloud import translate_v3
                from google.api_core.client_options import ClientOptions
                self.client = translate_v3.TranslationServiceClient(
                    client_options=ClientOptions(quota_project_id='rta-translation'))
            except Exception:
                raise ValueError('Google detection setup unavailable. Check ADC, dependencies, project and IAM permissions.') from None
        try:
            request_id = self.usage.start_request(len(text), operation='detection') if self.usage else None
        except Exception:
            raise RuntimeError('Cannot record detection usage. No further requests were sent.') from None
        try:
            self.requests += 1
            self.uncertain_characters += len(text)
            response = self.client.detect_language(request={
                'parent': 'projects/rta-translation/locations/global', 'content': text, 'mime_type': 'text/plain'},
                retry=None, timeout=30)
        except Exception:
            raise ValueError('Google detection failed; possible usage remains uncertain. Retry explicitly or review manually.') from None
        self.uncertain_characters -= len(text)
        self.confirmed_characters += len(text)
        try:
            if self.usage:
                self.usage.confirm_request(request_id)
        except Exception:
            # Bookkeeping failure stops the batch; never dispatch additional work.
            raise RuntimeError('Google responded, but usage confirmation failed. No further requests were sent.') from None
        try:
            languages = []
            for entry in response.languages:
                score = getattr(entry, 'confidence', None)
                if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))):
                    raise ValueError()
                languages.append({'language_code': entry.language_code, 'confidence': score})
            languages.sort(key=lambda entry: entry['confidence'] if entry['confidence'] is not None else -1, reverse=True)
            if not languages or any(not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]+)?', entry['language_code'])
                or (entry.get('confidence') is not None and (isinstance(entry['confidence'], bool) or not math.isfinite(entry['confidence']) or not 0 <= entry['confidence'] <= 1)) for entry in languages):
                raise ValueError()
            return {'provider': 'google', 'policy': GOOGLE_POLICY, **languages[0], 'alternatives': languages[1:]}
        except Exception:
            raise ValueError('Google returned an invalid detection result; confirm the language manually.') from None


def plan_detection(engine, datasets, limit=250):
    if not datasets or not set(datasets) <= {'master', 'source'} or not 1 <= limit <= 5000:
        raise ValueError('Choose datasets and a detection batch limit from 1 to 5000.')
    if provider_for(engine.store.load(engine.project)) != 'google':
        raise ValueError('Select Google as the detection provider first.')
    unique = {}
    selected_unique = set()
    records = engine.records()
    ordered = [item for pair in zip_longest(*[[r for r in records if r['dataset'] == dataset] for dataset in ('master', 'source')])
               for item in pair if item is not None]
    for item in ordered:
        from .translation import reviewed_translation
        if item['dataset'] not in datasets:
            continue
        selected_unique.add(item['original'])
        if reviewed_translation(item) or preflight(item['original'], item['field_kind'], not item.get('translation_excluded')):
            continue
        unique.setdefault(item['original'], None)
    # One workspace cache read; do not open SQLite once per selected text.
    keys = {raw_key(text): text for text in unique}
    cached = set()
    with engine.store.connect() as db:
        for key, payload in db.execute('SELECT key,payload FROM language_detection_cache WHERE project=?', (engine.project,)):
            if key in keys and decode_cached_result(payload):
                cached.add(keys[key])
    pending = [text for text in unique if text not in cached and len(text) <= 30000]
    uncached = pending[:limit]
    chars = sum(map(len, uncached))
    return {'unique_texts': len(unique), 'total_unique_selected_texts': len(selected_unique),
            'cached_texts': len(cached), 'pending_texts': len(pending), 'batch_size': len(uncached),
            'remaining_after_batch': len(pending) - len(uncached), 'datasets': list(datasets),
            'uncached': uncached, 'characters': chars, 'requests': len(uncached),
            'oversized_texts': sum(len(text) > 30000 for text in unique),
            'estimated_usd': chars * RATE_PER_MILLION / 1_000_000}


def run_detection(engine, datasets, *, consent=False, limit=250, client=None, progress=None, expected_plan=None):
    import json
    if not consent:
        raise ValueError('Explicit confirmation is required before processing a Google detection batch.')
    if google_runtime_info()['restart_required']:
        raise ValueError('Restart Streamlit to load the detection policy on disk before paid detection.')
    plan = plan_detection(engine, datasets, limit)
    if expected_plan is not None and any(value != expected_plan.get(key) for key, value in plan.items()):
        raise ValueError('Detection batch changed. Review the new preview and authorize it again.')
    usage = GoogleTranslationUsage(engine.store, engine.project)
    provider = GoogleDetectionProvider(consent=True, client=client, usage=usage)
    outcomes, failed = {}, 0
    successful = 0
    for index, text in enumerate(plan['uncached'], 1):
        try:
            raw = provider.detect(text)
        except ValueError:
            outcomes[text] = {'failed': True}
            failed += 1
            if progress:
                progress(index / plan['requests'], text=f'Detected {successful} successfully; {failed} failed · {index}/{plan["requests"]} values processed')
            continue
        outcomes[text] = raw
        try:
            with engine.store.connect() as db:
                db.execute('INSERT OR REPLACE INTO language_detection_cache VALUES (?,?,?)',
                           (engine.project, raw_key(text), json.dumps(raw)))
        except Exception:
            raise RuntimeError('Google responded, but the detection cache could not be saved. No further requests were sent.') from None
        successful += 1
        if progress:
            progress(index / plan['requests'], text=f'Detected {successful} successfully; {failed} failed · {index}/{plan["requests"]} values processed')
    # Apply raw results per field, preserving all reviewed human state. This reads
    # only cached Google responses for other fields; it makes no network calls.
    engine.detect(engine.store.load(engine.project).get('translation_fields', {}), force=True, google_results=outcomes)
    if progress and not plan['requests']:
        progress(1.0, text='Cached results refreshed; no Google requests needed.')
    return {**{k: v for k, v in plan.items() if k != 'uncached'}, 'planned_requests': plan['requests'],
            'requests': provider.requests, 'successful': successful, 'failed': failed,
            'confirmed_characters': provider.confirmed_characters,
            'uncertain_characters': provider.uncertain_characters}
