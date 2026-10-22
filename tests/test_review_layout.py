"""Table-first review layout uses the unchanged transactional review handlers."""
from copy import deepcopy

from tests.test_app import by_label, navigate
from tests.test_review_workflow import workspace, app_for
from tests.test_review_ux import large_review
from rta.models import REVIEW_FILTERS
from tests.workflow_display_helpers import csv_columns, backend_row


def walk(node):
    for child in getattr(node, 'children', {}).values():
        yield child
        yield from walk(child)


def table(app):
    return next(f.value for f in app.dataframe if 'Master Identifier' in f.value.columns)


def test_exact_section_order_and_default_collapsed_list(workspace, monkeypatch):
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Review & Approvals')
    nodes = list(walk(app.main))
    labels = ['**Reconciliation results**', '**Filter accounts by review status**', '**Bulk Decisions**',
              '**Account to Review**', '**Individual Decision**']
    locations = [next(i for i, n in enumerate(nodes) if isinstance(getattr(n, 'value', None), str) and n.value == label) for label in labels]
    assert locations == sorted(locations)
    frame_index = next(i for i, n in enumerate(nodes) if type(n).__name__ == 'Dataframe')
    assert locations[0] < frame_index < locations[1]
    dashboard = [i for i, n in enumerate(nodes) if type(n).__name__ == 'Metric'][:6]
    assert len(dashboard) == 6 and max(dashboard) < locations[0]
    assert by_label(app.button, 'Show Account List')
    assert not [c for c in app.checkbox if c.label.startswith('Select row')]
    assert len(app.dataframe) == 1
    assert by_label(app.selectbox, 'Review status').options == REVIEW_FILTERS
    assert list(table(app).columns) == csv_columns()
    assert {'Master Approved English Translation', 'Matched Source Original Name',
            'Final Value', 'Review Status', 'Evidence URL 1'} <= set(table(app).columns)
    hidden = backend_row(app, table(app).iloc[0]['Record ID'])
    assert 'Match Basis' in hidden and 'Research Evidence / Sources' in hidden


def test_hidden_list_filters_table_and_keeps_account_and_drafts(workspace, monkeypatch):
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Review & Approvals')
    selected = by_label(app.selectbox, 'Account to review').value
    by_label(app.text_area, 'Reviewer notes').set_value('Unsaved individual notes')
    by_label(app.text_input, 'Bulk reviewer name').set_value('Unsaved bulk reviewer')
    by_label(app.button, 'Show Account List').click().run()
    assert by_label(app.selectbox, 'Account to review').value == selected
    assert by_label(app.text_area, 'Reviewer notes').value == 'Unsaved individual notes'
    assert by_label(app.text_input, 'Bulk reviewer name').value == 'Unsaved bulk reviewer'
    by_label(app.button, 'Hide Account List').click().run()
    assert not [c for c in app.checkbox if c.label.startswith('Select row')]
    by_label(app.text_input, 'Search accounts').set_value('Summit').run()
    assert len(table(app)) == 1
    assert by_label(app.selectbox, 'Account to review').value == selected
    assert by_label(app.text_area, 'Reviewer notes').value == 'Unsaved individual notes'
    by_label(app.text_input, 'Search accounts').set_value('no-such-account-123').run()
    assert len(table(app)) == 0 and 'Final Value' in table(app).columns
    assert by_label(app.selectbox, 'Account to review').value == selected
    assert not workspace[0].audit(workspace[1])


def test_large_table_list_and_account_selector_are_bounded(large_review, monkeypatch):
    app = app_for(large_review, monkeypatch)
    navigate(app, 'Review & Approvals')
    assert len(table(app)) == 50
    assert len(by_label(app.selectbox, 'Account to review').options) <= 51
    current = by_label(app.selectbox, 'Account to review').value
    by_label(app.button, 'Show Account List').click().run()
    assert len([c for c in app.checkbox if c.label.startswith('Select row')]) == 50
    next(c for c in app.checkbox if c.label.startswith('Select row 1 ')).check().run()
    by_label(app.number_input, 'Selection page').set_value(3).run()
    assert len(table(app)) == 26
    assert len([c for c in app.checkbox if c.label.startswith('Select row')]) == 26
    assert by_label(app.selectbox, 'Account to review').value == current
    by_label(app.button, 'Hide Account List').click().run()
    by_label(app.number_input, 'Selection page').set_value(1).run()
    by_label(app.button, 'Show Account List').click().run()
    assert next(c for c in app.checkbox if c.label.startswith('Select row 1 ')).value
    by_label(app.selectbox, 'Review rows per page').set_value(100).run()
    assert len(table(app)) == 100
    assert len(by_label(app.selectbox, 'Account to review').options) <= 101


def test_cross_page_bulk_requires_explicit_scope_consent(large_review, monkeypatch):
    store, project, _ = large_review
    app = app_for(large_review, monkeypatch)
    navigate(app, 'Review & Approvals')
    by_label(app.checkbox, 'Select All filtered accounts').check().run()
    by_label(app.selectbox, 'Bulk decision').set_value('Reject')
    by_label(app.text_input, 'Bulk reviewer name').set_value('Reviewer')
    by_label(app.button, 'Save Review Decisions').click().run()
    assert any('Confirm including' in e.value for e in app.error)
    assert not store.audit(project)
    next(c for c in app.checkbox if c.label.startswith('I confirm including ')).check()
    by_label(app.button, 'Save Review Decisions').click().run()
    assert len(store.audit(project)) == 126
    assert all(r['decision'] == 'Reject' for r in store.load(project)['results'])


def test_provenance_and_source_json_hidden_but_data_retained(workspace, monkeypatch):
    store, project, _ = workspace
    payload = store.load(project)
    payload['results'][1]['translation_provenance'] = [{'direction': 'Original Master → Original Source',
        'master_field': 'Account', 'source_field': 'Company', 'translations': [], 'comparison_checks': []}]
    store.save(project, payload)
    before = deepcopy(store.load(project))
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Review & Approvals')
    by_label(app.radio, 'Top 3 Suggested Source Matches').set_value(0).run()
    assert not app.json
    assert not any('provenance' in e.label.lower() for e in app.expander)
    assert any('Selected Source account:' in m.value for m in app.markdown)
    assert store.load(project) == before
    assert not store.audit(project)


def test_bulk_confirmation_resets_when_selected_records_change(workspace, monkeypatch):
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Review & Approvals')
    by_label(app.button, 'Show Account List').click().run()
    by_label(app.checkbox, 'Select All filtered accounts').check().run()
    verification = 'I have verified the evidence and field value for every selected account.'
    by_label(app.checkbox, verification).check().run()
    assert by_label(app.checkbox, verification).value
    next(c for c in app.checkbox if c.label.startswith('Select row 1 ')).uncheck().run()
    assert not by_label(app.checkbox, verification).value
    assert any('Selected accounts: 9 of 10' in c.value for c in app.caption)
    assert not workspace[0].audit(workspace[1])


def test_individual_confirmation_resets_for_another_source_or_action(workspace, monkeypatch):
    app = app_for(workspace, monkeypatch)
    navigate(app, 'Review & Approvals')
    verification = 'I have verified the evidence and the field value for this specific account.'
    by_label(app.checkbox, verification).check().run()
    by_label(app.radio, 'Top 3 Suggested Source Matches').set_value(0).run()
    assert not by_label(app.checkbox, verification).value
    by_label(app.checkbox, verification).check().run()
    by_label(app.selectbox, 'Decision').set_value('Manual').run()
    assert not by_label(app.checkbox, verification).value
    assert not workspace[0].audit(workspace[1])
