from io import BytesIO

import polars as pl
import pytest
from openpyxl import load_workbook

from rta.export import workbook, summary, result_row
from rta.matching import Matcher
from rta.models import Mapping, Result, REVIEW_FILTERS, INTELLIGENCE_PENDING
from rta.review import final_value, legacy_auto_finalized
from rta.storage import Store
from tests.test_app import by_label, navigate
from tests.test_review_workflow import workspace, app_for
from tests.test_recommendations import setup, research


@pytest.mark.parametrize('master_name,source_name,aliases,stage', [
    ('Alpha', 'Alpha', {}, 'Exact'),
    (' ALPHA, Inc. ', 'Alpha Inc', {}, 'Normalized'),
    ('Old Alpha', 'Alpha', {'Old Alpha': 'Alpha'}, 'Alias'),
])
def test_local_matches_require_audited_human_approval(tmp_path, master_name, source_name, aliases, stage):
    mapping = Mapping('Account', 'Company', 'Segment', 'Value')
    master = pl.DataFrame({'Account': [master_name], 'Segment': ['Enterprise']})
    source = pl.DataFrame({'Company': [source_name], 'Value': ['Enterprise']})
    r = Matcher(source, mapping, aliases=aliases).run(master)[0]
    assert r.match_status == stage and r.proposed == r.original == 'Enterprise'
    assert r.status_label == INTELLIGENCE_PENDING
    assert r.final == r.verified_original == final_value(r) == ''
    store = Store(tmp_path / 'approval.sqlite3')
    project, _ = store.create()
    store.save(project, {'source': source.to_dicts(), 'mapping': vars(mapping), 'results': [r.dict()]})
    assert store.load(project)['results'][0]['final'] == '' and not store.audit(project)
    store.review(project, 0, 'Approve', 'Human reviewer', 'Identity and comparison value checked')
    reopened = Store(store.path)
    saved = Result(**reopened.load(project)['results'][0])
    assert saved.status_label == 'Approved' and saved.final == final_value(saved) == 'Enterprise'
    assert saved.match_status == stage and saved.proposed == saved.original == 'Enterprise'
    event = reopened.audit(project)[0]
    assert event['reviewer'] == 'Human reviewer' and event['previous_final'] == ''
    assert event['timestamp'] == saved.reviewed_at and event['approved_value'] == 'Enterprise'


def test_research_does_not_restore_final_from_verified_original(setup):
    r = setup[-1]
    r.verified_original = 'Enterprise'
    research(setup)
    assert r.proposed == r.ai_proposed == 'Enterprise'
    assert r.final == final_value(r) == '' and r.status_label == INTELLIGENCE_PENDING


@pytest.mark.parametrize('decision,raw,expected', [
    ('Approve', 'Approved — AI Recommendation', 'Approved'),
    ('Approve proposal', 'Approved', 'Approved'),
    ('Reject', 'Rejected — AI Recommendation', 'Rejected'),
    ('Manual', 'Manually Verified', 'Manually Verified'),
    ('Retain original', 'Approved', 'Manually Verified'),
    ('', 'Approved', INTELLIGENCE_PENDING),
    ('', 'Verified unchanged', INTELLIGENCE_PENDING),
])
def test_historical_classification_does_not_rewrite_stored_outcome(decision, raw, expected):
    r = Result(0, 'Account', 'Enterprise', proposed='Enterprise', final='Enterprise',
               review_status=raw, decision=decision)
    before = r.dict()
    assert r.status_label == expected
    assert result_row(r)['Review Status'] == expected
    assert result_row(r)['Stored Review Status'] == raw
    assert r.dict() == before
    if not decision:
        assert final_value(r) == ''


def test_legacy_automatic_finals_are_retained_but_not_presented_as_approved(workspace, monkeypatch):
    store, project, _ = workspace
    payload = store.load(project)
    legacy = payload['results'][0]
    legacy.update(final='Enterprise', verified_original='Enterprise', review_status='Verified unchanged')
    store.save(project, payload)
    before, audit = store.load(project), store.audit(project)
    r = Result(**before['results'][0])
    assert legacy_auto_finalized(r) and r.final == 'Enterprise' and final_value(r) == ''
    assert summary([r])['Legacy Automatically Finalized Matches'] == 1
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Review & Approvals')
    assert by_label(app.selectbox, 'Review status').options == [
        'All', 'Intelligence Proposed — Pending Approval', 'Manual Review Required',
        'Approved', 'Rejected', 'Manually Verified'] == REVIEW_FILTERS
    assert by_label(app.selectbox, 'Review status').value == 'All'
    by_label(app.selectbox, 'Account to review').set_value(0).run()
    assert by_label(app.metric, 'Final value').value == '—'
    assert any('legacy automatically finalized' in item.value for item in app.info)
    assert app.dataframe[-1].value.iloc[0]['Final Value'] == ''
    assert store.load(project) == before and store.audit(project) == audit
    sheet = load_workbook(BytesIO(workbook([r], audit, [], 10)))['Reconciliation Results']
    row = dict(zip([c.value for c in sheet[1]], [c.value for c in sheet[2]]))
    assert row['Final Value'] is None and row['Original Value'] == row['Proposed Value'] == 'Enterprise'
    assert row['Stored Review Status'] == 'Verified unchanged'
    assert row['Legacy Automatic Final Requires Review'] is True
    store.review(project, 0, 'Approve', 'Legacy reviewer', 'Reviewed now, not backdated')
    saved = Result(**Store(store.path).load(project)['results'][0])
    assert saved.status_label == 'Approved' and final_value(saved) == 'Enterprise'
    assert not legacy_auto_finalized(saved)
    assert store.audit(project)[0]['previous_final'] == 'Enterprise'
    assert store.audit(project)[0]['previous_decision'] == ''


def test_historical_approved_filter_requires_a_saved_decision(workspace, monkeypatch):
    store, project, _ = workspace
    payload = store.load(project)
    payload['results'][0].update(review_status='Approved', final='Enterprise')
    store.save(project, payload)
    store.review(project, 1, 'Approve', 'Reviewer')
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Review & Approvals')
    by_label(app.selectbox, 'Review status').set_value('Approved').run()
    assert list(app.dataframe[-1].value['Record ID']) == [1]
    assert list(app.dataframe[-1].value['Review Status']) == ['Approved']
