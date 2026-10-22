"""Complete page boundary, mapping guards and approval-only display contract."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from tests.test_app import by_label, navigate
from tests.test_review_workflow import workspace, app_for
from tests.test_review_layout import walk
from tests.test_reconciliation_page_completion import assert_table
from tests.test_workflow_translation_display import block_live_services


def test_table_is_intended_end_of_complete_page(workspace, monkeypatch):
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Run Reconciliation')
    by_label(app.button, 'Run automatic local matching').click().run()
    assert_table(app, 10)
    assert list(walk(app.main))[-1] is app.dataframe[0]
    assert any('Reconciliation complete' in s.value for s in app.success)
    app.run()
    assert_table(app, 10)
    assert list(walk(app.main))[-1] is app.dataframe[0]


@pytest.mark.parametrize('bad', [None, {}, {'master_id':'Account'},
    {'master_id':'missing','source_id':'Company','master_value':'Segment','source_value':'Customer Segment'},
    {'master_id':'Account','source_id':'missing','master_value':'Segment','source_value':'Customer Segment'}])
def test_missing_or_stale_mapping_warns_and_cannot_run(workspace, monkeypatch, bad):
    store, project, _ = workspace
    payload = store.load(project)
    payload['mapping'] = bad
    store.save(project, payload)
    before = deepcopy(store.load(project))
    spy = Mock(side_effect=AssertionError('Invalid mapping must never reach engine'))
    monkeypatch.setattr('rta.translation_matching.reconcile', spy)
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Run Reconciliation')
    assert not app.exception
    assert any('Configure Reconciliation' in w.value for w in app.warning)
    assert not [b for b in app.button if b.label == 'Run automatic local matching']
    assert not app.success
    spy.assert_not_called()
    assert store.load(project) == before


def test_mapped_columns_and_full_backend_input_reach_engine(workspace, monkeypatch):
    import rta.translation_matching as matching
    spy = Mock(wraps=matching.reconcile)
    monkeypatch.setattr(matching, 'reconcile', spy)
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Run Reconciliation')
    by_label(app.button, 'Run automatic local matching').click().run()
    assert_table(app, 10)
    master, source, mapping, entries = spy.call_args.args
    assert master.columns == ['Account', 'Segment']
    assert source.columns == ['Company', 'Customer Segment']
    assert vars(mapping) == workspace[0].load(workspace[1])['mapping']
    assert 'Master Identifier' not in master.columns
    assert 'Master Approved English Translation' not in source.columns
    spy.assert_called_once()


def test_draft_blank_then_current_approval_visible_without_reupload(tmp_path, monkeypatch):
    from tests.test_approved_translation_integration import fixture
    from tests.translation_workspace_helpers import seed_google
    from tests.test_translation import Offline
    case, engine = fixture(tmp_path, [{'Name':'Les Jardins de Provence','Segment':'Verify'}],
                           [{'Name':'The Gardens of Provence','Segment':'SMB'}])
    seed_google(engine, {'Les Jardins de Provence':'fr','The Gardens of Provence':'en'})
    engine.process(['master'], Offline())
    entry = next(r for r in engine.records() if r['dataset']=='master')
    assert entry['english'] and entry['status'] == 'Translated — Review'
    app = app_for(case, monkeypatch)
    navigate(app, 'Run Reconciliation')
    by_label(app.button, 'Run automatic local matching').click().run()
    assert assert_table(app, 1).iloc[0]['Master Approved English Translation'] == ''
    engine.approve(entry, entry['english'], 'Reviewer', True)
    app.run()
    assert assert_table(app, 1).iloc[0]['Master Approved English Translation'] == entry['english']
    assert any('results are stale' in w.value for w in app.warning)
    by_label(app.button, 'Run automatic local matching').click().run()
    assert assert_table(app, 1).iloc[0]['Master Approved English Translation'] == entry['english']
    assert not any('results are stale' in w.value for w in app.warning)
    assert not case[0].load(case[1])['results'][0]['final']
