"""Mock-only setup and stable labels for the table-first UI."""
import json
from rta.google_detection import raw_key, GOOGLE_POLICY
from rta.translation import TranslationEngine
from tests.test_app import by_label

DETECT_CONSENT = 'I authorize this detection batch and its estimated cost.'
TRANSLATE_CONSENT = 'I authorize this translation batch, its estimated cost and retries.'
DECISION_CONSENT = 'I confirm the selected translation decisions and have verified the English names.'


def seed_google(engine, labels, fields=None):
    payload = engine.store.load(engine.project)
    payload['language_detection_provider'] = 'google'
    engine.store.save(engine.project, payload)
    with engine.store.connect() as db:
        for text, code in labels.items():
            raw = {'language_code': code, 'confidence': .99, 'provider': 'google', 'policy': GOOGLE_POLICY}
            db.execute('INSERT OR REPLACE INTO language_detection_cache VALUES (?,?,?)',
                       (engine.project, raw_key(text), json.dumps(raw)))
    engine.detect(fields or payload.get('translation_fields', {}), force=True)


def select_visible(app):
    by_label(app.button, 'Select all visible rows').click().run()
    assert not app.exception
