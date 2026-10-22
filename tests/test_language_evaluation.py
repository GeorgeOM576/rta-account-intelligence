"""Offline Google-direct evaluation; historical heuristic results stay frozen."""
import json
from pathlib import Path
from unittest.mock import Mock

import rta.google_detection as production
from tests.fixtures.language_detection.company_evaluation.evaluate import build_cases, evaluate

ROOT = Path('tests/fixtures/language_detection/company_evaluation')


def test_representative_labels_are_explicit_and_uncertain_names_not_guessed():
    cases = build_cases()
    assert len(cases) == 149 and len({r['text'] for r in cases}) == len(cases)
    assert {'en', 'fr', 'es', 'de', 'pt', 'ar', 'zh', 'ja'} <= {r['expected_language'] for r in cases}
    assert all(r['expected_language'] is None for r in cases if r['expected_outcome'] == 'manual')
    assert all(r['label_basis'] and r['response_origin'] in ('synthetic', 'saved_live_google') for r in cases)
    assert cases == json.loads((ROOT / 'labelled_cases.json').read_text())


def test_saved_response_provenance_and_measured_subset():
    cases = [r for r in build_cases() if r['response_origin'] == 'saved_live_google']
    saved = json.loads(Path('tests/fixtures/language_detection/google_live_25.json').read_text())
    assert [(r['text'], r['raw']) for r in cases] == [(r['name'], r['raw']) for r in saved['results']]
    metrics = evaluate(cases)
    assert metrics['definitive_cases'] == metrics['correct'] == 23
    assert metrics['incorrect'] == 0 and metrics['recall'] == 1


def test_confidence_is_advisory_without_production_changes_or_google_calls(monkeypatch):
    from google.cloud import translate_v3
    blocked = Mock(side_effect=AssertionError('No paid APIs in diagnostic evaluation'))
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', blocked)
    baseline = evaluate(build_cases())
    for score in (0, .2, .80, .85, .899, .90, .95):
        result = production.interpret('Example Company GmbH', 'account_name', raw={'language_code': 'de', 'confidence': score})
        assert result['language'] == 'de' and result['status'] == 'Translation Needed'
        assert result['language_review_required'] == (score < .90)
        assert production.CONFIDENCE_THRESHOLD == .90  # Advisory threshold only.
    assert evaluate(build_cases()) == baseline
    blocked.assert_not_called()


def test_metrics_preserve_errors_instead_of_claiming_mock_google_accuracy():
    metrics = evaluate(build_cases())
    assert metrics['correct'] + metrics['incorrect'] + metrics['definitive_manual_reviews'] == metrics['definitive_cases']
    assert metrics['tp'] + metrics['fn'] == 95
    before = json.loads((ROOT / 'results.json').read_text())
    assert before['scenarios']['current_90']['potentially_unnecessary_manual_reviews'] == 5
    assert metrics['potentially_unnecessary_manual_reviews'] == 0
    assert metrics['incorrect'] == 8 and metrics['foreign_as_english'] == 5
    assert metrics['correct_language_foreign_recall'] < metrics['recall']
    assert metrics['ambiguity_retained'] + metrics['ambiguity_wrongly_automated'] == metrics['ambiguous_cases']
