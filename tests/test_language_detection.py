"""Regression, quality evaluation and workspace policy tests; never use live APIs."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock

import polars as pl
import pytest

from rta.language_detection import (detect_text, raw_detection, _detect, field_kind, ENGLISH,
                                    FOREIGN, AMBIGUOUS, EXCLUDED, DEFAULT_BUSINESS_VOCABULARY)
from rta.storage import Store
from rta.models import Mapping
from rta.translation import TranslationEngine, default_fields, translation_metrics
from rta.translation_matching import reconcile
from rta.translation_providers import GoogleTranslationProvider
from rta.translation_usage import GoogleTranslationUsage
from tests.test_translation import make_workspace, Offline, SPANISH
from tests.test_app import by_label, navigate
from tests.test_review_workflow import app_for
from tests.fixtures.language_detection.evaluate import evaluate


@pytest.mark.parametrize('text', ['HARBOR HEALTH', 'Cedar Labs', 'Pioneer Data', 'Orchard Systems', 'Bluebird Studio', 'Summit Holdings'])
def test_reported_business_names_are_not_foreign_or_ambiguous(text):
    result = detect_text(text, 'account_name')
    assert result['language'] == 'en'
    assert result['status'] == 'Not Required'
    assert result['detection_outcome'] == ENGLISH


@pytest.mark.parametrize('text', ['Enterprise', 'Healthcare', 'Commercial'])
def test_reported_segment_values_are_excluded_by_default(text):
    result = detect_text(text, 'classification')
    assert result['status'] == 'Excluded'
    assert result['detection_outcome'] == EXCLUDED
    assert result['detector_language'] == 'und'  # detector not consulted


@pytest.mark.parametrize('text,language', [
    ('Les Ateliers de la Lune Violette', 'fr'), ('Banque des Petites Entreprises', 'fr'),
    ('Servicios del Río de Cristal', 'es'), ('Compañía de Productos Agrícolas', 'es'),
    ('Werkstätten am Silbernen Morgen', 'de'), ('Technische Lösungen für Unternehmen', 'de'),
    ('Société de Data Studio', 'fr'), ('Servicios financieros para Data Studio', 'es')])
def test_language_specific_evidence_survives_shared_business_terms(text, language):
    result = detect_text(text, 'account_name')
    assert result['status'] == 'Translation Needed'
    assert result['language'] == language
    assert result['detection_outcome'] == FOREIGN


@pytest.mark.parametrize('text', ['Acme', 'Orion', 'Café International', 'Müller GmbH', 'Data Studio', 'Commercial', 'Health', 'Microsoft Corporation'])
def test_proper_names_and_business_terms_alone_abstain(text):
    result = detect_text(text, 'account_name')
    assert result['language'] == 'und'
    assert result['status'] == 'Uncertain'
    assert result['detection_outcome'] == AMBIGUOUS


def test_field_types_are_different_policies_and_user_overridable(monkeypatch):
    assert field_kind('Customer Segment') == 'classification'
    assert field_kind('Account ID') == 'identifier'
    assert field_kind('Account Name') == 'account_name'
    assert field_kind('Company Description') == 'description'
    assert field_kind('Notes') == 'free_text'
    monkeypatch.setattr('rta.language_detection.raw_detection', lambda text: ('it', 0.999))
    text = 'Produciamo strumenti innovativi destinati alle piccole aziende'
    assert detect_text(text, 'account_name')['status'] == 'Uncertain'
    assert detect_text(text, 'description')['status'] == 'Translation Needed'
    assert detect_text(text, 'free_text')['status'] == 'Translation Needed'
    assert detect_text(text, 'classification')['status'] == 'Excluded'
    assert detect_text(text, 'classification', classification_enabled=True)['status'] == 'Uncertain'
    # Policy cache must not retain a mocked detector result in later tests.
    _detect.cache_clear()


def test_precision_recall_and_correct_language_codes():
    quality = evaluate()
    before, after = quality['baseline'], quality['current']
    assert after['cases'] == 68
    assert before['false_positives'] == 6 and after['false_positives'] == 0
    assert after['precision'] >= 0.95
    assert after['recall'] >= 0.90
    assert after['correct_foreign_language_codes'] >= before['correct_foreign_language_codes']
    assert all(after['foreign_by_language'][language] >= 7 for language in ('fr', 'es', 'de'))
    assert after['foreign_candidates'] >= 25  # explicitly reject an all-English/abstain solution
    assert after['missed_foreign_texts'] == ['Élan', 'Müller GmbH']


def test_classification_exclusion_defaults_and_explicit_enable(tmp_path):
    row = {'Name': 'Cedar Labs', 'Segment': 'Servicios financieros para empresas', 'Description': 'Enterprise'}
    store, project, _ = make_workspace(tmp_path, [row], [row])
    engine = TranslationEngine(store, project)
    payload = store.load(project)
    assert 'Segment' not in default_fields(payload, 'master')
    assert 'Name' in default_fields(payload, 'master')
    records = engine.detect({'master': ['Segment'], 'source': ['Segment']})
    assert all(r['status'] == 'Excluded' for r in records)
    assert translation_metrics(records)[2]['Excluded cells'] == 2
    assert translation_metrics(records)[2]['Flagged cells'] == 0
    engine.configure_detection({'enabled_classifications': {'master': ['Segment']}})
    records = engine.records()
    assert next(r for r in records if r['dataset'] == 'master')['status'] == 'Translation Needed'
    assert next(r for r in records if r['dataset'] == 'source')['status'] == 'Excluded'
    # Explicit per-workspace field type override is respected.
    engine.configure_detection({'field_types': {'master': {'Description': 'classification'}}})
    assert 'Description' not in default_fields(store.load(project), 'master')


def test_persistent_deduplicated_detection_cache_is_policy_and_workspace_scoped(tmp_path, monkeypatch):
    row = {'Name': 'Cedar Labs', 'Segment': 'Enterprise', 'Description': SPANISH}
    store, project, _ = make_workspace(tmp_path, [row] * 3, [row] * 2)
    engine = TranslationEngine(store, project)
    import rta.translation as module
    original = module.detect_text
    calls = Mock(side_effect=original)
    monkeypatch.setattr(module, 'detect_text', calls)
    fields = {'master': ['Name', 'Description'], 'source': ['Name', 'Description']}
    engine.detect(fields)
    assert calls.call_count == 2  # one per unique value/policy across both files
    calls.reset_mock()
    TranslationEngine(Store(store.path), project).detect(fields)
    calls.assert_not_called()
    engine.configure_detection({'business_vocabulary': list(DEFAULT_BUSINESS_VOCABULARY) + ['Cedar']})
    assert calls.call_count == 2
    other, _ = store.create()
    store.save(other, deepcopy(store.load(project)))
    calls.reset_mock()
    TranslationEngine(store, other).detect(fields)
    assert calls.call_count == 2  # persistent cache is not shared across workspaces
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM language_detection_cache WHERE project=?', (project,)).fetchone()[0] == 4


def test_custom_vocabulary_neutralizes_terms_without_proving_english(tmp_path):
    row = {'Name': 'Servicios Financieros', 'Segment': 'Enterprise', 'Description': ''}
    store, project, _ = make_workspace(tmp_path, [row], [row])
    engine = TranslationEngine(store, project)
    engine.detect({'master': ['Name'], 'source': ['Name']})
    assert all(r['language'] == 'es' for r in engine.records())
    engine.configure_detection({'business_vocabulary': ['Servicios', 'Financieros']})
    assert all(r['language'] == 'und' and r['status'] == 'Uncertain' for r in engine.records())
    assert detect_text('Data Studio', 'account_name', [])['status'] == 'Uncertain'


def test_unknown_never_reaches_google_even_with_legacy_include_uncertain(tmp_path):
    row = {'Name': 'Café International', 'Segment': 'Enterprise', 'Description': ''}
    store, project, _ = make_workspace(tmp_path, [row], [row])
    engine = TranslationEngine(store, project)
    engine.detect({'master': ['Name'], 'source': ['Name']})
    client = Mock()
    provider = GoogleTranslationProvider(consent=True, client=client)
    assert engine.plan(['master', 'source'], provider, allow_names=True, include_uncertain=True)['unique_texts'] == 0
    report = engine.process(['master', 'source'], provider, allow_names=True, include_uncertain=True)
    assert report['drafts'] == report['unique_attempts'] == 0
    client.translate_text.assert_not_called()
    assert GoogleTranslationUsage(store, project).summary()['requests'] == 0
    item = engine.records()[0]
    with pytest.raises(ValueError):
        engine.confirm_language(item, 'und', 'Reviewer', True)
    with pytest.raises(ValueError):
        engine.confirm_language(item, 'fr', 'Reviewer', False)
    confirmed = engine.confirm_language(item, 'fr', 'Language Reviewer', True)
    assert confirmed['status'] == 'Translation Needed' and confirmed['language_confirmed']
    assert confirmed['detected_language'] == 'und'
    assert engine.plan(['master'], provider, allow_names=True)['unique_texts'] == 1
    assert store.audit(project)[0]['event_type'] == 'translation_language_review'
    # This operation only authorizes a language; paid API consent remains separate.
    unconsented = GoogleTranslationProvider(client=client)
    with pytest.raises(ValueError, match='confirmation'):
        engine.process(['master'], unconsented, allow_names=True)
    client.translate_text.assert_not_called()
    updated = engine.confirm_language(confirmed, 'en', 'Language Reviewer', True)
    assert updated['status'] == 'Not Required'
    assert engine.plan(['master'], provider, allow_names=True)['unique_texts'] == 0


def test_old_automatic_false_positives_refresh_without_losing_reviews_or_usage(tmp_path):
    row = {'Name': 'HARBOR HEALTH', 'Segment': 'Enterprise', 'Description': SPANISH}
    store, project, _ = make_workspace(tmp_path, [row] * 3, [row])
    engine = TranslationEngine(store, project)
    engine.detect({'master': ['Name'], 'source': []})
    reviewed = engine.approve(engine.records()[1], 'Reviewer-approved original spelling', 'Reviewer', True, 'vi')
    manual = engine.confirm_language(engine.records()[2], 'fr', 'Language Reviewer', True)
    usage = GoogleTranslationUsage(store, project)
    usage.confirm_request(usage.start_request(12))
    # Simulate records written before this policy existed, including an unreviewed draft.
    with store.connect() as db:
        for item in engine.records():
            old = {**item}
            old.pop('detection_policy')
            if item['row_id'] == 0:
                old.update(language='vi', detected_language='vi', status='Translated — Review',
                           english='Wrong language draft', provider='Google', model='old', reviewer='', reviewed_at='')
            db.execute('UPDATE translations SET payload=? WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                       (json.dumps(old), project, old['dataset'], old['revision'], old['row_id'], old['field']))
    migrated = TranslationEngine(Store(store.path), project).records()
    assert migrated[0]['status'] == 'Not Required' and migrated[0]['language'] == 'en'
    assert migrated[0]['english'] == '' and migrated[0]['draft_english'] == 'Wrong language draft'
    assert migrated[1]['status'] == 'Approved Translation' and migrated[1]['english'] == reviewed['english']
    assert migrated[2]['language'] == manual['language'] and migrated[2]['language_confirmed']
    assert len(store.audit(project)) == 2
    assert usage.summary()['confirmed_characters'] == 12


def test_disabling_classification_cannot_supply_matching_context(tmp_path):
    store, project, _ = make_workspace(tmp_path)
    engine = TranslationEngine(store, project)
    engine.detect({'master': ['Name', 'Segment'], 'source': ['Name', 'Segment']})
    engine.configure_detection({'enabled_classifications': {'master': ['Segment']}})
    name = next(r for r in engine.records() if r['dataset'] == 'master' and r['field'] == 'Name')
    engine.approve(name, 'Bank of Mexico', 'Reviewer', True, 'es')
    segment = next(r for r in engine.records() if r['dataset'] == 'master' and r['field'] == 'Segment')
    engine.approve(segment, 'Enterprise', 'Reviewer', True, 'es')
    engine.configure_detection({})
    segment = next(r for r in engine.records() if r['dataset'] == 'master' and r['field'] == 'Segment')
    assert segment['status'] == 'Approved Translation' and segment['translation_excluded']
    payload = store.load(project)
    results, _ = reconcile(pl.DataFrame(payload['master']), pl.DataFrame(payload['source']),
                           Mapping(**payload['mapping']), engine.records())
    assert results[0].translation_provenance
    assert not any(p.get('comparison_context') for result in results for p in result.translation_provenance)


def test_manual_language_correction_ui_does_not_approve_or_call_google(tmp_path, monkeypatch):
    row = {'Name': 'Café International', 'Segment': 'Enterprise', 'Description': ''}
    case = make_workspace(tmp_path, [row], [row])
    store, project, _ = case
    monkeypatch.setattr('rta.translation_ui.ArgosProvider', Offline)
    from google.cloud import translate_v3
    factory = Mock(side_effect=AssertionError('Live API client forbidden'))
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    app = app_for(case, monkeypatch)
    navigate(app, 'Translation Intelligence')
    assert 'Segment' not in TranslationEngine(store, project).store.load(project)['translation_fields']['master']
    assert not any('Include uncertain detections' in c.label for c in app.checkbox)
    by_label(app.selectbox, 'Translation dataset').set_value('Master').run()
    by_label(app.selectbox, 'Translation status').set_value('Uncertain').run()
    by_label(app.text_input, 'Confirmed source-language code').set_value('fr')
    by_label(app.text_input, 'Individual reviewer').set_value('Language Reviewer')
    by_label(app.checkbox, 'I verified this translation preserves the correct entity, proper names, legal suffixes and identifiers.').check()
    by_label(app.button, 'Save confirmed language').click().run()
    assert not app.exception
    item = next(r for r in TranslationEngine(store, project).records() if r['dataset'] == 'master' and r['field'] == 'Name')
    assert item['status'] == 'Translation Needed' and item['language'] == 'fr'
    assert not item['english'] and not store.load(project)['results']
    factory.assert_not_called()
    assert GoogleTranslationUsage(store, project).summary()['requests'] == 0


def test_detection_settings_backend_remains_available_without_technical_ui(tmp_path, monkeypatch):
    row = {'Name': 'Cedar Labs', 'Segment': SPANISH, 'Description': ''}
    case = make_workspace(tmp_path, [row], [row])
    store, project, _ = case
    engine = TranslationEngine(store, project)
    engine.detect({'master': ['Name', 'Segment'], 'source': ['Name']})
    assert next(r for r in engine.records() if r['field'] == 'Segment')['status'] == 'Excluded'
    engine.configure_detection({'field_types': {'master': {'Description': 'classification'}},
        'enabled_classifications': {'master': ['Segment']},
        'business_vocabulary': [*DEFAULT_BUSINESS_VOCABULARY, 'Cedar']})
    segment = next(r for r in engine.records() if r['field'] == 'Segment')
    assert segment['status'] == 'Translation Needed' and not segment['translation_excluded']
    assert engine.plan(['master', 'source'], GoogleTranslationProvider())['identities'] == [(SPANISH, 'es')]
    from google.cloud import translate_v3
    factory = Mock(side_effect=AssertionError('Live API client forbidden'))
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    app = app_for(case, monkeypatch)
    navigate(app, 'Translation Intelligence')
    assert not app.exception and all(e.label == 'Save / resume workspace' for e in app.expander)
    assert 'Segment' not in set(app.dataframe[0].value['Original Company Name'])
    assert store.load(project)['language_detection_settings']['enabled_classifications']['master'] == ['Segment']
    factory.assert_not_called()
