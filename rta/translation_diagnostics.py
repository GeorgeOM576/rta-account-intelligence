"""Count-only action traces and bounded process-local completion receipts.

No uploaded text, exception messages, credentials, row payloads or tokens are
accepted by the logger. Set RTA_TRANSLATION_DIAGNOSTICS=0 to disable traces.
Receipts retain no translations; SQLite remains the source of truth.
"""
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import logging
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

LOADED_BUILD = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
logger = logging.getLogger('rta.translation.action')
logger.setLevel(logging.INFO)
if not any(getattr(h, '_rta_translation', False) for h in logger.handlers):
    handler = logging.StreamHandler()
    handler._rta_translation = True
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
_current = ContextVar('rta_translation_action', default=None)
_lock = RLock()
_receipts = OrderedDict()
_FIELDS = {'selected_rows', 'eligible_rows', 'excluded_rows', 'excluded_reasons',
           'authorized', 'names', 'characters', 'attempt', 'response_count', 'drafts',
           'failed', 'remaining', 'error_code', 'cache_hit', 'persisted', 'requests'}
_REASONS = {'english', 'missing_or_unsupported_language', 'existing_draft_or_approval',
            'excluded_field', 'rejected', 'other'}
_CODES = {'permission_denied', 'quota_exhausted', 'unavailable', 'timeout', 'invalid_argument',
          'authentication', 'provider_error', 'storage', 'validation', 'invalid_response',
          'protected_identifier_changed', 'interrupted', 'runtime'}
_STAGES = {'submission_received', 'provider_prepare', 'google_setup_failed', 'usage_reservation_failed',
           'google_request_attempted', 'google_request_exception', 'google_response_received',
           'usage_confirmation_failed', 'google_response_validated', 'backend_plan',
           'translation_cache_reused', 'translation_validation_failed', 'translation_record_persisted',
           'backend_completed', 'action_failed', 'action_interrupted', 'action_completed', 'table_refresh_completed'}


def event(stage, **values):
    if os.environ.get('RTA_TRANSLATION_DIAGNOSTICS', '1') == '0':
        return
    payload = {'event': 'rta_translation', 'stage': stage if stage in _STAGES else 'unknown_stage', 'action_id': _current.get()}
    for key, value in values.items():
        if key not in _FIELDS:
            continue
        if key == 'excluded_reasons' and isinstance(value, dict):
            payload[key] = {k: v for k, v in value.items() if k in _REASONS and isinstance(v, int)}
        elif key == 'error_code':
            payload[key] = value if value in _CODES else 'runtime'
        elif isinstance(value, (bool, int, float)):
            payload[key] = value
    # Logging must never interrupt a translation or leak a fallback repr.
    try:
        logger.info(json.dumps(payload, sort_keys=True))
    except Exception:
        pass


@contextmanager
def scope(action_id):
    token = _current.set(action_id)
    try:
        yield
    finally:
        _current.reset(token)


def error_code(error):
    import sqlite3
    if isinstance(error, sqlite3.Error):
        return 'storage'
    if isinstance(error, ValueError):
        return 'validation'
    from google.api_core import exceptions as g
    from google.auth.exceptions import GoogleAuthError
    for cls, code in [(g.PermissionDenied, 'permission_denied'), (g.ResourceExhausted, 'quota_exhausted'),
                      (g.ServiceUnavailable, 'unavailable'), (g.DeadlineExceeded, 'timeout'),
                      (g.InvalidArgument, 'invalid_argument'), (GoogleAuthError, 'authentication')]:
        if isinstance(error, cls):
            return code
    return 'provider_error'


def key(store, project):
    return str(Path(store.path).resolve()), project


def latest(store, project):
    with _lock:
        receipt = _receipts.get(key(store, project))
        return dict(receipt) if receipt else None


def begin(store, project, owner, affected, action_id=None):
    with _lock:
        k = key(store, project)
        if k in _receipts and _receipts[k]['status'] == 'running':
            return None
        receipt = {'id': action_id or uuid4().hex, 'owner': owner, 'status': 'running',
                   'affected': set(affected), 'message': 'Translation batch is processing. Please wait; no new batch was started.'}
        _receipts[k] = receipt
        _receipts.move_to_end(k)
        for old in list(_receipts):
            if len(_receipts) <= 128:
                break
            if _receipts[old]['status'] != 'running':
                del _receipts[old]
        return dict(receipt)


def finish(store, project, action_id, message, failed=False, persisted=False):
    with _lock:
        receipt = _receipts.get(key(store, project))
        if receipt and receipt['id'] == action_id:
            receipt.update(status='failed' if failed else 'completed', message=message, persisted=persisted)
