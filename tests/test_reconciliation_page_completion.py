"""Actual matching click, committed result refresh and unchanged navigation."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from tests.test_app import by_label, navigate
from tests.test_review_workflow import workspace, app_for
from tests.workflow_display_helpers import csv_columns
from tests.test_workflow_translation_display import block_live_services


def assert_table(app, count):
    assert not app.exception
    frame = app.dataframe[0].value
    assert list(frame.columns) == csv_columns()
    assert len(frame) == count
    return frame


def test_matching_saved_and_render_survives_reruns(workspace, monkeypatch):
    import rta.translation_matching as matching
    store, project, _ = workspace
    payload = store.load(project)
    payload.pop('results')
    store.save(project, payload)
    spy = Mock(wraps=matching.reconcile)
    monkeypatch.setattr(matching, 'reconcile', spy)
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Run Reconciliation')
    by_label(app.button, 'Run automatic local matching').click().run()
    spy.assert_called_once()
    assert_table(app, 10)
    assert any('Reconciliation complete' in s.value for s in app.success)
    saved = store.load(project)
    assert saved['results'] == app.session_state['payload']['results']
    assert all('candidates' in r and 'account_context' in r for r in saved['results'])
    assert all(not r['final'] for r in saved['results'])
    app.run()
    assert_table(app, 10)
    spy.assert_called_once()
    by_label(app.text_input, 'Search account identifiers').set_value('no such fictional account').run()
    assert_table(app, 0)
    for page in ['AI Research', 'Review & Approvals', 'Export Results', 'Run Reconciliation']:
        navigate(app, page)
    assert_table(app, 10)
    assert store.load(project)['results'][1]['proposed'] == 'Healthcare'
    assert not store.load(project)['results'][1]['final']


def test_saved_reviewer_decision_is_immediately_rendered(workspace, monkeypatch):
    """Reproduce pre-save Result objects disagreeing with Store.save's merge."""
    import rta.translation_matching as matching
    store, project, _ = workspace
    real = matching.reconcile
    def match_and_review(*args, **kwargs):
        fresh = real(*args, **kwargs)
        # Another reviewer acts while matching is in progress. Store.save keeps it.
        store.review(project, 1, 'Approve', 'Concurrent reviewer', 'Verified')
        return fresh
    spy = Mock(side_effect=match_and_review)
    monkeypatch.setattr(matching, 'reconcile', spy)
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Run Reconciliation')
    by_label(app.button, 'Run automatic local matching').click().run()
    table = assert_table(app, 10)
    row = table[table['Record ID'] == 1].iloc[0]
    assert row['Final Value'] == 'Healthcare'
    assert row['Review Status'] == 'Approved'
    assert row['Reviewer'] == 'Concurrent reviewer'
    assert store.load(project)['results'] == app.session_state['payload']['results']
    assert any('Reconciliation complete' in s.value for s in app.success)
    spy.assert_called_once()
    app.run()
    spy.assert_called_once()


@pytest.mark.parametrize('failure', ['matching', 'save'])
def test_failed_matching_keeps_saved_table_and_navigation(workspace, monkeypatch, failure):
    store, project, _ = workspace
    before = deepcopy(store.load(project))
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Run Reconciliation')
    target = 'rta.translation_matching.reconcile' if failure == 'matching' else 'rta.storage.Store.save'
    monkeypatch.setattr(target, Mock(side_effect=RuntimeError('mock local failure')))
    by_label(app.button, 'Run automatic local matching').click().run()
    assert_table(app, 10)
    assert any('could not be completed' in e.value for e in app.error)
    assert store.load(project) == before
    navigate(app, 'Review & Approvals')
    assert_table(app, 10)


def test_approved_translations_keep_complete_page_and_backend_context(tmp_path, monkeypatch):
    from tests.test_workflow_translation_display import setup
    case, engine, app = setup(tmp_path, monkeypatch)
    table = assert_table(app, 1)
    assert table.iloc[0]['Master Approved English Translation'] == 'The Gardens of Provence'
    result = case[0].load(case[1])['results'][0]
    assert result['match_basis'] == 'Master Translation ↔ Source Translation'
    assert result['proposed'] == 'SMB' and not result['final']
    assert any('Reconciliation complete' in s.value for s in app.success)
    app.run()
    assert_table(app, 1)
