"""Organization-name eligibility is independent of paid consent and approval."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from rta.translation_providers import GoogleTranslationProvider
from tests.test_google_detection import google_case
from tests.test_google_translation import response
from tests.test_review_workflow import app_for
from tests.test_app import by_label, navigate
from tests.translation_workspace_helpers import seed_google, TRANSLATE_CONSENT


@pytest.fixture
def names(tmp_path):
    case, engine = google_case(tmp_path,
        [{'Name': 'Les Jardins de Provence'}], [{'Name': 'Servicios de Construcción'}])
    seed_google(engine, {'Les Jardins de Provence': 'fr', 'Servicios de Construcción': 'es'},
                {'master': ['Name'], 'source': ['Name']})
    return case, engine


@pytest.mark.parametrize('dataset', ['Master', 'Source', 'All'])
def test_fresh_page_checkbox_selection_translates_without_hidden_name_permission(names, monkeypatch, dataset):
    case, engine = names
    before = deepcopy(case[0].load(case[1]))
    client = Mock()
    client.translate_text.side_effect = lambda **kwargs: response(*[
        {'Les Jardins de Provence': 'Gardens of Provence',
         'Servicios de Construcción': 'Construction Services'}[text]
        for text in kwargs['request']['contents']])
    from google.cloud import translate_v3
    factory = Mock(return_value=client)
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    app = app_for(case, monkeypatch)
    # The obsolete checkbox used this key. It must have no effect, even if false.
    app.session_state[f'names_{case[1]}'] = False
    navigate(app, 'Translation Intelligence')
    factory.assert_not_called()
    assert not any('Allow drafts for organization-name' in c.label for c in app.checkbox)
    assert not by_label(app.button, 'Translate Selected').disabled
    by_label(app.selectbox, 'Translation dataset').set_value(dataset).run()
    count = 2 if dataset == 'All' else 1
    # Exercise actual table checkboxes, rather than the select-all convenience button.
    app.session_state[app.dataframe[0].key] = {
        'edited_rows': {i: {'Select': True} for i in range(count)}, 'added_rows': [], 'deleted_rows': []}
    app.run()
    assert not app.exception and not by_label(app.button, 'Translate Selected').disabled
    factory.assert_not_called()
    by_label(app.button, 'Translate Selected').click().run()
    assert app.error
    factory.assert_not_called()
    by_label(app.checkbox, TRANSLATE_CONSENT).check()
    by_label(app.button, 'Translate Selected').click().run()
    assert not app.exception
    drafts = [r for r in engine.records() if r['english']]
    assert len(drafts) == count and all(r['status'] == 'Translated — Review' for r in drafts)
    assert {r['dataset'] for r in drafts} == ({'master', 'source'} if dataset == 'All' else {dataset.lower()})
    assert all(not r.get('reviewer') and r['status'] != 'Approved Translation' for r in drafts)
    assert not by_label(app.button, 'Translate Selected').disabled  # Drafts are not retransmitted.
    assert not by_label(app.checkbox, TRANSLATE_CONSENT).value
    assert not case[0].audit(case[1])
    after = case[0].load(case[1])
    assert after['master'] == before['master'] and after['source'] == before['source']
    assert after['results'] == before['results'] == []
    client.detect_language.assert_not_called()


def test_engine_defaults_include_both_name_fields_without_authorizing_paid_calls(names):
    case, engine = names
    client = Mock()
    plan = engine.plan(['master', 'source'], GoogleTranslationProvider(client=client))
    assert plan['unique_texts'] == 2
    assert plan['eligibility']['name_permission_excluded_records'] == 0
    assert {code for _, code in plan['identities']} == {'fr', 'es'}
    with pytest.raises(ValueError, match='confirmation'):
        engine.process(['master', 'source'], GoogleTranslationProvider(client=client))
    client.translate_text.assert_not_called()
    client.translate_text.side_effect = lambda **kwargs: response(*['English draft' for _ in kwargs['request']['contents']])
    report = engine.process(['master', 'source'], GoogleTranslationProvider(consent=True, client=client))
    assert report['drafts'] == 2 and report['failed'] == 0
    assert all(r['status'] == 'Translated — Review' for r in engine.records())
    assert not case[0].audit(case[1]) and not case[0].load(case[1])['results']


def test_explicit_backend_opt_out_still_excludes_names(names):
    _, engine = names
    client = Mock()
    plan = engine.plan(['master', 'source'], GoogleTranslationProvider(client=client), allow_names=False)
    assert plan['unique_texts'] == 0
    assert plan['eligibility']['name_permission_excluded_records'] == 2
    client.translate_text.assert_not_called()
