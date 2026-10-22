"""Exercise widget protocol, real page handlers and canonical selection adapters."""
from copy import deepcopy
import pytest
from rta.selection_state import consume_editor
from tests.test_translation_multirow_refresh import setup, edit_selection, authorize
from tests.test_review_workflow import workspace, app_for
from tests.test_app import by_label, navigate


def test_editor_callback_deselect_and_retired_widget():
    view = {'key': 'editor', 'rows': [{'id': 1}], 'identities': ['stable'],
            'data': [{'Select': False}]}
    state = {'view': view, 'editor': {'edited_rows': {0: {'Select': True}}}}
    consume_editor(state, 'selection', 'view', 'editor', True)
    assert list(state['selection']) == ['stable']
    state['editor']['edited_rows'] = {}  # actual editor uncheck returns to baseline
    consume_editor(state, 'selection', 'view', 'editor', True)
    assert state['selection'] == {}
    state['editor']['edited_rows'] = {0: {'Select': True}}
    consume_editor(state, 'selection', 'view', 'retired', True)
    assert state['selection'] == {}


def test_five_pending_checks_survive_view_refresh_and_translate(tmp_path, monkeypatch):
    case, engine, app, client, _ = setup(tmp_path, monkeypatch)
    prefix = f'translation_workspace_{case[1]}'
    # Browser sends checks at the same time the view needs a new generation.
    app.session_state[app.dataframe[0].key] = {
        'edited_rows': {i: {'Select': True} for i in range(5)},
        'added_rows': [], 'deleted_rows': []}
    app.session_state[prefix + '_epoch'] = 1
    app.run()
    assert len(app.session_state[prefix + '_selection']) == 5
    authorize(app)
    assert len([r for r in engine.records() if r['english']]) == 5
    assert all(app.dataframe[0].value['English Translation'])
    calls = client.translate_text.call_count
    app.run()
    assert client.translate_text.call_count == calls == 1
    by_label(app.button, 'Clear selection').click().run()
    app.run()
    assert app.session_state[prefix + '_selection'] == {}


@pytest.mark.parametrize('action', ['Approve', 'Reject'])
def test_five_review_checks_enable_real_bulk_handler(workspace, monkeypatch, action):
    store, project, _ = workspace
    payload = store.load(project)
    # Fictional, valid local proposals: test selection rather than matching policy.
    for r in payload['results'][:5]:
        r.update(proposed='Enterprise', identity_confidence='Reliable local match',
                 recommendation_status='', decision='', final='')
    store.save(project, payload)
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Review & Approvals')
    by_label(app.button, 'Show Account List').click().run()
    for i in range(5):
        next(c for c in app.checkbox if c.label.startswith(f'Select row {i + 1} ·')).check().run()
        assert not by_label(app.button, 'Save Review Decisions').disabled
    assert any('Selected accounts: 5 of 10' in c.value for c in app.caption)
    # Checkbox changes and unrelated reruns retain all five stable IDs.
    app.run()
    next(c for c in app.checkbox if c.label.startswith('Select row 2 ·')).uncheck().run()
    assert any('Selected accounts: 4 of 10' in c.value for c in app.caption)
    next(c for c in app.checkbox if c.label.startswith('Select row 2 ·')).check().run()
    by_label(app.button, 'Hide Account List').click().run()
    by_label(app.button, 'Show Account List').click().run()
    assert sum(c.value for c in app.checkbox if c.label.startswith('Select row')) == 5
    assert not store.audit(project)
    by_label(app.selectbox, 'Bulk decision').set_value(action).run()
    by_label(app.text_input, 'Bulk reviewer name').set_value('Selection reviewer')
    by_label(app.checkbox, 'I have verified the evidence and field value for every selected account.').check()
    by_label(app.button, 'Save Review Decisions').click().run()
    assert not app.exception
    saved = store.load(project)['results']
    assert [r['row_id'] for r in saved if r['decision']] == list(range(5))
    assert len(store.audit(project)) == 5
    assert all(not r['final'] for r in saved[5:])
    if action == 'Reject':
        assert all(not r['final'] for r in saved)


def test_review_filter_clear_and_workspace_isolation(workspace, monkeypatch):
    store, project, token = workspace
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Review & Approvals')
    by_label(app.button, 'Show Account List').click().run()
    rows = [c for c in app.checkbox if c.label.startswith('Select row')]
    rows[0].check().run()
    first_name = store.load(project)['results'][0]['identifier']
    by_label(app.text_input, 'Search accounts').set_value(first_name).run()
    assert any('Selected accounts: 1 of 1' in c.value for c in app.caption)
    by_label(app.checkbox, 'Select All filtered accounts').uncheck().run()
    assert by_label(app.button, 'Save Review Decisions').disabled
    by_label(app.checkbox, 'Select All filtered accounts').check().run()
    second, second_token = store.create()
    store.save(second, deepcopy(store.load(project)))
    app.session_state['project'], app.session_state['token'] = second, second_token
    app.run()
    assert by_label(app.button, 'Save Review Decisions').disabled
    assert not store.audit(project) and not store.audit(second)
    app.session_state['project'], app.session_state['token'] = project, token
    app.run()
    assert not by_label(app.button, 'Save Review Decisions').disabled


def test_translation_workspace_selection_does_not_leak(tmp_path, monkeypatch):
    case, engine, app, client, _ = setup(tmp_path, monkeypatch)
    store, project, token = case
    edit_selection(app, range(5))
    second, second_token = store.create()
    store.save(second, deepcopy(store.load(project)))
    app.session_state['project'], app.session_state['token'] = second, second_token
    app.run()
    assert app.session_state[f'translation_workspace_{second}_selection'] == {}
    app.session_state['project'], app.session_state['token'] = project, token
    app.run()
    assert len(app.session_state[f'translation_workspace_{project}_selection']) == 5
    client.translate_text.assert_not_called()
