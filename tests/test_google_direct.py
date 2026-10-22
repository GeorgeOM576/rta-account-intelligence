"""Google-authoritative policy with advisory review and human-only approvals."""
from copy import deepcopy
from io import StringIO
import csv
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rta.google_detection import interpret, GoogleDetectionProvider, raw_key
from rta.google_languages import supported_language
from rta.translation import TranslationEngine, translation_eligible
from rta.translation_providers import GoogleTranslationProvider
from rta.translation_usage import GoogleTranslationUsage
from rta.export import translation_csv
from tests.test_google_detection import google_case, detected
from tests.test_google_translation import response
from tests.test_review_workflow import app_for
from tests.test_translation import Offline
from tests.test_app import by_label, navigate


@pytest.mark.parametrize('code,score,expected,review', [
    ('en', .15, 'Not Required', True), ('en', .99, 'Not Required', False),
    ('fr', .2, 'Translation Needed', True), ('de', 0, 'Translation Needed', True),
    ('ja', .99, 'Translation Needed', False), ('zh-TW', .6, 'Translation Needed', True),
    ('mni-Mtei', None, 'Translation Needed', True),
])
def test_google_code_drives_classification_confidence_only_advises(code, score, expected, review):
    result = interpret('Global Müller Company GmbH', 'account_name', raw={'language_code': code, 'confidence': score})
    assert result['language'] == supported_language(code)
    assert result['status'] == expected
    assert result['google_language'] == code and result['google_confidence'] == score
    assert result['language_review_required'] == review
    assert translation_eligible(result) == (code != 'en')


@pytest.mark.parametrize('raw', [None, {}, {'failed': True}, {'language_code': ''},
    {'language_code': 'und', 'confidence': .99}, {'language_code': 'zz', 'confidence': .99},
    {'language_code': 'zxx', 'confidence': .99}, {'language_code': 'en', 'confidence': float('nan')},
    {'language_code': 'fr', 'confidence': 1.1}, {'language_code': 'fr', 'confidence': True},
    {'language_code': 'fr', 'confidence': .9, 'alternatives': [{'confidence': .8}]}, [],
])
def test_missing_unsupported_or_malformed_language_never_guessed_or_submitted(raw):
    result = interpret('Example Business', 'account_name', raw=raw)
    assert result['language'] == 'und' and result['status'] == 'Uncertain'
    assert not translation_eligible(result) and result['language_review_required']


def test_ambiguous_valid_alternatives_are_advice_not_a_gate():
    raw = {'language_code': 'es', 'confidence': .51,
           'alternatives': [{'language_code': 'pt', 'confidence': .49}]}
    result = interpret('Nova GmbH', 'account_name', raw=raw)
    assert result['language'] == 'es' and translation_eligible(result)
    assert result['language_review_required'] and 'competing' in result['language_review_reason']


def test_missing_sdk_confidence_still_retains_valid_code():
    client = Mock()
    client.detect_language.return_value = SimpleNamespace(languages=[SimpleNamespace(language_code='fr')])
    raw = GoogleDetectionProvider(consent=True, client=client).detect('Bonjour Société')
    assert raw['confidence'] is None
    assert translation_eligible(interpret('Bonjour Société', 'account_name', raw=raw))
    assert client.detect_language.call_args.kwargs['retry'] is None


def test_low_confidence_ui_consent_drafts_and_language_correction_regeneration(tmp_path, monkeypatch):
    original = 'Müller GmbH'
    case, engine = google_case(tmp_path, [{'Name': original}], [{'Name': 'Cedar Labs'}])
    store, project, _ = case
    engine.detect({'master': ['Name'], 'source': ['Name']})
    uploaded = deepcopy(store.load(project))
    from google.cloud import translate_v3
    client = Mock()
    client.detect_language.side_effect = lambda **kw: detected('de' if kw['request']['content'] == original else 'en', .25)
    client.translate_text.return_value = response('Mueller GmbH')
    factory = Mock(return_value=client)
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    monkeypatch.setattr('rta.translation_ui.ArgosProvider', Offline)
    app = app_for(case, monkeypatch)
    navigate(app, 'Translation Intelligence')
    assert not any(r.label == 'Translation provider' for r in app.radio)
    factory.assert_not_called()
    by_label(app.button, 'Detect Languages').click().run()
    factory.assert_not_called()
    by_label(app.checkbox, 'I authorize this detection batch and its estimated cost.').check()
    by_label(app.button, 'Detect Languages').click().run()
    assert not app.exception and client.detect_language.call_count == 2
    from tests.translation_workspace_helpers import select_visible
    select_visible(app)
    by_label(app.button, 'Translate Selected').click().run()
    client.translate_text.assert_not_called()
    by_label(app.checkbox, 'I authorize this translation batch, its estimated cost and retries.').check()
    by_label(app.button, 'Translate Selected').click().run()
    assert not app.exception and client.translate_text.call_count == 1
    items = engine.records()
    draft = next(r for r in items if r['dataset'] == 'master')
    assert draft['status'] == 'Translated — Review' and draft['language_review_required']
    assert next(r for r in items if r['dataset'] == 'source')['status'] == 'Not Required'
    assert not store.load(project)['results']
    rows = list(csv.DictReader(StringIO(translation_csv(items).decode('utf-8-sig'))))
    assert rows[0]['Language Review Recommended'] == 'True' and rows[0]['Google Confidence'] == '0.25'
    corrected = engine.confirm_language(draft, 'fr', 'Language reviewer', True)
    assert corrected['english'] == '' and corrected['draft_english'] == 'Mueller GmbH'
    with pytest.raises(ValueError, match='supported'):
        engine.confirm_language(corrected, 'zz', 'Language reviewer', True)
    with pytest.raises(ValueError, match='confirmation'):
        engine.process(['master'], GoogleTranslationProvider(client=client), allow_names=True)
    engine.process(['master'], GoogleTranslationProvider(consent=True, client=client), allow_names=True)
    current = next(r for r in engine.records() if r['dataset'] == 'master')
    assert current['language'] == 'fr' and current['status'] == 'Translated — Review'
    assert client.translate_text.call_args.kwargs['request']['source_language_code'] == 'fr'
    assert current['original'] == original
    assert store.load(project)['master'] == uploaded['master'] and not store.load(project)['results']
    engine.bulk_approve([current], 'Translator', True)
    approved = next(r for r in engine.records() if r['dataset'] == 'master')
    assert approved['status'] == 'Approved Translation'
    assert not store.load(project)['results'] and len(store.audit(project)) >= 2


def test_api_failures_and_unsupported_results_cannot_enter_paid_translation(tmp_path):
    case, engine = google_case(tmp_path)
    engine.detect({'master': ['Name'], 'source': []}, google_results={'Banco de México': {'language_code': 'zz', 'confidence': 1}})
    assert engine.plan(['master'], GoogleTranslationProvider(), True)['unique_texts'] == 0
    client = Mock()
    GoogleTranslationProvider(consent=True, client=client).prepare([('Example', 'zz'), ('Example', 'und')])
    client.translate_text.assert_not_called()
    assert GoogleTranslationUsage(case[0], case[1]).summary()['requests'] == 0
