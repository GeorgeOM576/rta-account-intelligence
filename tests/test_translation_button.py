"""Explain disabled Google translation without changing eligibility or consent."""
import json
from unittest.mock import Mock

import pytest

from rta.translation import cache_key, TranslationEngine
from rta.translation_providers import GoogleTranslationProvider
from rta.translation_usage import GoogleTranslationUsage
from tests.test_google_detection import google_case
from tests.test_translation import Offline
from tests.test_review_workflow import app_for
from tests.test_app import by_label, navigate

NAMES = 'Allow drafts for organization-name fields; I will verify proper names, legal suffixes and identifiers'
CONSENT = 'I authorize this translation batch, its estimated cost and retries.'
BUTTON = 'Translate Selected'
FRENCH = 'Les Jardins de Provence'
ENGLISH = 'Global Tech Solutions'


def setup_ui(tmp_path, monkeypatch, *, pending=False):
    case, engine = google_case(tmp_path, [{'Name': FRENCH, 'Segment': 'Enterprise'}],
                               [{'Name': ENGLISH, 'Segment': 'Commercial'}])
    engine.detect({'master': ['Name'], 'source': ['Name']}, google_results=None if pending else {
        FRENCH: {'language_code': 'fr', 'confidence': 0.99},
        ENGLISH: {'language_code': 'en', 'confidence': 0.99}})
    monkeypatch.setattr('rta.translation_ui.ArgosProvider', Offline)
    from google.cloud import translate_v3
    factory = Mock(side_effect=AssertionError('No live API calls'))
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    app = app_for(case, monkeypatch)
    navigate(app, 'Translation Intelligence')
    assert not app.exception
    return case, engine, app, factory


def test_selection_gates_execution_even_with_paid_checkbox_and_updates_immediately(tmp_path, monkeypatch):
    case, engine, app, factory = setup_ui(tmp_path, monkeypatch)
    assert engine.records()[0]['status'] == 'Translation Needed'
    assert not by_label(app.button, BUTTON).disabled
    by_label(app.checkbox, CONSENT).check()
    assert not by_label(app.button, BUTTON).disabled
    factory.assert_not_called()
    from tests.translation_workspace_helpers import select_visible
    select_visible(app)
    assert not by_label(app.button, BUTTON).disabled
    assert not by_label(app.checkbox, CONSENT).value
    by_label(app.button, BUTTON).click().run()
    assert any('Authorize' in e.value for e in app.error)
    factory.assert_not_called()
    by_label(app.button, 'Clear selection').click().run()
    assert not by_label(app.button, BUTTON).disabled
    assert not case[0].audit(case[1])


def test_pending_und_languages_are_explained_and_never_eligible(tmp_path, monkeypatch):
    case, engine, app, factory = setup_ui(tmp_path, monkeypatch, pending=True)
    from tests.translation_workspace_helpers import select_visible
    select_visible(app)
    assert not by_label(app.button, BUTTON).disabled
    assert any('Detect or confirm missing languages' in w.value for w in app.info)
    plan = engine.plan(['master', 'source'], GoogleTranslationProvider(), allow_names=True)
    assert plan['eligibility']['manual_review_records'] == 2
    assert plan['eligibility']['eligible_records'] == plan['unique_texts'] == 0
    factory.assert_not_called()


def test_zero_cost_cached_batch_remains_enabled_and_preserves_approval(tmp_path, monkeypatch):
    case, engine, app, factory = setup_ui(tmp_path, monkeypatch)
    store, project, _ = case
    provider = GoogleTranslationProvider()
    outcome = {'english': 'Gardens of Provence', 'provider': provider.name, 'model': provider.model,
               'status': 'Translated — Review', 'reason': '', 'cache_hit': False}
    with store.connect() as db:
        db.execute('INSERT INTO translation_cache VALUES (?,?,?)',
                   (project, cache_key(FRENCH, 'fr', provider), json.dumps(outcome)))
    from tests.translation_workspace_helpers import select_visible
    select_visible(app)
    assert not by_label(app.button, BUTTON).disabled
    plan = engine.plan(['master', 'source'], provider, allow_names=True)
    assert plan['cached_texts'] == 1 and not plan['uncached'] and plan['estimated_usd'] == 0
    by_label(app.checkbox, CONSENT).check()
    by_label(app.button, BUTTON).click().run()
    assert not app.exception and not by_label(app.button, BUTTON).disabled
    item = next(r for r in engine.records() if r['dataset'] == 'master')
    assert item['status'] == 'Translated — Review' and item['english'] == outcome['english']
    approved = engine.approve(item, outcome['english'], 'Human translator', True, 'fr')
    audit = store.audit(project)
    app.run()
    assert not by_label(app.button, BUTTON).disabled
    assert next(r for r in engine.records() if r['dataset'] == 'master')['english'] == approved['english']
    assert store.audit(project) == audit and not store.load(project)['results']
    assert GoogleTranslationUsage(store, project).summary()['requests'] == 0
    factory.assert_not_called()


@pytest.mark.parametrize('limit', [0, -1, 5001])
def test_invalid_batch_limits_rejected_without_calls(tmp_path, limit):
    _, engine = google_case(tmp_path)
    with pytest.raises(ValueError, match='limit from 1 to 5000'):
        engine.plan(['master', 'source'], GoogleTranslationProvider(), allow_names=True, limit=limit)
