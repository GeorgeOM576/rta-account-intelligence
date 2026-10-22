"""Foreign-only legal context: exact recoveries, unchanged English/ambiguity."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from rta.google_detection import interpret, raw_key, CLASSIFICATION_POLICY, CONFIDENCE_THRESHOLD
from rta.language_detection import FOREIGN, AMBIGUOUS
from rta.translation import TranslationEngine
from rta.translation_usage import GoogleTranslationUsage
from tests.fixtures.language_detection.company_evaluation.evaluate import build_cases, evaluate
from tests.test_google_detection import google_case

ROOT = Path('tests/fixtures/language_detection/company_evaluation')
RECOVERED = {
    'Les Ateliers du Rivage SAS': 'fr',
    'Servicios de Ingeniería Rivera SA': 'es',
    'Deutsche Werkstätten am Fluss GmbH': 'de',
    'Empresa de Energia Renovável Ltd': 'pt',
}


@pytest.mark.parametrize('text,language', RECOVERED.items())
def test_legal_suffix_does_not_override_google_or_create_confidence_gate(text, language):
    result = interpret(text, 'account_name', raw={'language_code': language, 'confidence': .99})
    assert result['detection_outcome'] == FOREIGN and result['language'] == language
    assert result['status'] == 'Translation Needed'
    for raw in ({'language_code': 'en', 'confidence': .99},
                {'language_code': language, 'confidence': .899},
                {'language_code': language, 'confidence': .99, 'alternatives': [{'language_code': 'en', 'confidence': .90}]}):
        current = interpret(text, 'account_name', raw=raw)
        assert current['language'] == raw['language_code']
        assert current['status'] == ('Not Required' if raw['language_code'] == 'en' else 'Translation Needed')
        assert current['language_review_required'] == (raw.get('confidence', 0) < .90 or bool(raw.get('alternatives')))



@pytest.mark.parametrize('text,language', [
    ('Müller GmbH', 'de'), ('Harbor Coastal Research LLC', 'en'),
    ('Toyota Motor Corporation', 'ja'), ('Samsung Electronics Ltd', 'en'),
    ('Data Studio GmbH', 'de'), ('Les Jardins 数据 SAS', 'fr'),
    ('Global International Research Corporation', 'en'), ('Élan', 'fr'),
])
def test_legal_names_brands_and_mixed_scripts_follow_google_language(text, language):
    result = interpret(text, 'account_name', raw={'language_code': language, 'confidence': .99})
    assert result['language'] == language and result['status'] == ('Not Required' if language == 'en' else 'Translation Needed')


def test_149_case_google_authority_retains_original_labels_and_raw_results(monkeypatch):
    from google.cloud import translate_v3
    factory = Mock(side_effect=AssertionError('No live APIs'))
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    cases = json.loads((ROOT / 'labelled_cases.json').read_text())
    assert cases == build_cases()
    current = evaluate(cases)
    for case, result in zip(cases, current['outputs'], strict=True):
        expected = case['raw']['language_code'].lower()
        if expected == 'zh-cn':
            expected = 'zh'
        assert result['actual_language'] == expected
        assert result['actual_outcome'] == ('english' if expected == 'en' else 'foreign')
    assert current['definitive_manual_reviews'] == 0
    assert current['incorrect'] == 8  # Expose wrong injected suggestions; never relabel ground truth.
    assert CONFIDENCE_THRESHOLD == .90  # Advisory only.
    factory.assert_not_called()


def test_cached_legal_refresh_preserves_human_corrections_approvals_audit_and_usage(tmp_path, monkeypatch):
    from google.cloud import translate_v3
    factory = Mock(side_effect=AssertionError('Cache reinterpretation must not call Google'))
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    names = list(RECOVERED)
    case, engine = google_case(tmp_path, [{'Name': text} for text in names], [{'Name': names[0]}])
    store, project, _ = case
    engine.detect({'master': ['Name'], 'source': ['Name']})
    manual = engine.confirm_language(next(r for r in engine.records() if r['dataset'] == 'source'), 'es', 'Language reviewer', True)
    approved = engine.approve(next(r for r in engine.records() if r['dataset'] == 'master' and r['row_id'] == 1),
                              'Human approved legal name SA', 'Reviewer', True, 'es')
    payload = deepcopy(store.load(project))
    audit = store.audit(project)
    usage = GoogleTranslationUsage(store, project).summary()
    records = engine.records()
    with store.connect() as db:
        for text, language in RECOVERED.items():
            raw = {'provider': 'google', 'policy': 'google-v3-field-aware-v1',
                   'language_code': language, 'confidence': .99, 'alternatives': []}
            db.execute('INSERT OR REPLACE INTO language_detection_cache VALUES (?,?,?)', (project, raw_key(text), json.dumps(raw)))
        for item in records:
            item.update(detection_policy='previous-v2-interpretation', detection_version='google-script-aware-v2')
            db.execute('UPDATE translations SET payload=? WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                       (json.dumps(item), project, item['dataset'], item['revision'], item['row_id'], item['field']))
    updated = TranslationEngine(store, project).records()
    assert all(r['detection_version'] == CLASSIFICATION_POLICY and r['automatic_detection_outcome'] == FOREIGN for r in updated)
    assert next(r for r in updated if r['dataset'] == 'source')['language'] == manual['language']
    approved_after = next(r for r in updated if r['dataset'] == 'master' and r['row_id'] == 1)
    assert approved_after['status'] == 'Approved Translation' and approved_after['english'] == approved['english']
    assert store.audit(project) == audit and GoogleTranslationUsage(store, project).summary() == usage
    assert store.load(project)['results'] == payload['results'] and store.load(project)['master'] == payload['master']
    factory.assert_not_called()
