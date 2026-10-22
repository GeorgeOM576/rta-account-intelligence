"""Paid detection follows the table's SQL filters and authoritative cell IDs."""
import json
from unittest.mock import Mock
import pytest
from google.cloud import translate_v3
from rta.translation_workspace import TranslationWorkspace, row_id
from tests.test_google_detection import google_case, detected
from tests.test_app import navigate, by_label
from tests.test_review_workflow import app_for
from tests.translation_workspace_helpers import DETECT_CONSENT, seed_google
from tests.test_translation_multirow_refresh import edit_selection


def setup(tmp_path, monkeypatch, count=6):
    master = [{'Name':f'Société Atelier {i}', 'Segment':'Verify'} for i in range(count)]
    source = [{'Name':f'Servicios Empresa {i}', 'Segment':'SMB'} for i in range(count)]
    case, engine = google_case(tmp_path, master, source)
    engine.detect({'master':['Name'],'source':['Name']})
    client = Mock()
    client.detect_language.return_value = detected('fr')
    factory = Mock(return_value=client)
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    return case, engine, client, factory


def sent(client):
    return [call.kwargs['request']['content'] for call in client.detect_language.call_args_list]


def authorize(app):
    by_label(app.checkbox, DETECT_CONSENT).check()
    by_label(app.button, 'Detect Languages').click().run()
    assert not app.exception


@pytest.mark.parametrize('dataset', ['Master','Source','All'])
def test_dataset_scope_controls_actual_requests(tmp_path, monkeypatch, dataset):
    case, engine, client, factory = setup(tmp_path, monkeypatch)
    scope = TranslationWorkspace(engine)
    plan = scope.detection_plan(250, dataset=dataset)
    expected = {r['Name'] for d in ('master','source') if dataset in ('All',d.title())
                for r in case[0].load(case[1])[d]}
    assert plan['records_in_scope'] == len(expected)
    scope.run_detection(250, True, dataset=dataset, preview=plan)
    assert set(sent(client)) == expected
    assert len(sent(client)) == len(expected)


def test_five_selected_stable_ids_across_both_datasets(tmp_path, monkeypatch):
    case, engine, client, _ = setup(tmp_path, monkeypatch)
    records = engine.records()
    selected = records[:3] + records[-2:]
    scope = TranslationWorkspace(engine)
    plan = scope.detection_plan(250, selection=selected)
    scope.run_detection(250, True, selection=selected, preview=plan)
    assert set(sent(client)) == {r['original'] for r in selected}
    assert plan['records_in_scope'] == 5
    assert len({row_id(r) for r in selected}) == 5


def test_search_status_and_hidden_selection_intersection(tmp_path, monkeypatch):
    case, engine, client, _ = setup(tmp_path, monkeypatch)
    records = engine.records()
    master = next(r for r in records if r['dataset']=='master' and r['row_id']==1)
    source = next(r for r in records if r['dataset']=='source' and r['row_id']==1)
    scope = TranslationWorkspace(engine)
    options = dict(dataset='Master', search='Atelier 1', status=master['status'], selection=[master,source])
    plan = scope.detection_plan(250, **options)
    assert plan['records_in_scope'] == 1
    scope.run_detection(250, True, **options, preview=plan)
    assert sent(client) == [master['original']]
    assert scope.detection_plan(250, dataset='Master', search='Empresa')['batch_size'] == 0
    assert scope.detection_plan(250, dataset='Master', status='Approved Translation')['batch_size'] == 0
    assert scope.detection_plan(250, dataset='Master', selection=[source])['records_in_scope'] == 0


def test_cached_deduplicated_batches_and_changed_preview(tmp_path, monkeypatch):
    case, engine, client, factory = setup(tmp_path, monkeypatch)
    scope = TranslationWorkspace(engine)
    original = scope.detection_plan(2, dataset='Master')
    seed_google(engine, {'Société Atelier 0':'fr'})
    with pytest.raises(ValueError, match='batch changed'):
        scope.run_detection(2, True, dataset='Master', preview=original)
    factory.assert_not_called()
    preview = scope.detection_plan(2, dataset='Master')
    assert preview['cached_texts'] == 1
    assert preview['batch_size'] == 2 and preview['remaining_after_batch'] == 3
    with pytest.raises(ValueError, match='confirmation'):
        scope.run_detection(2, False, dataset='Master', preview=preview)
    factory.assert_not_called()
    scope.run_detection(2, True, dataset='Master', preview=preview)
    assert 'Société Atelier 0' not in sent(client)
    assert len(sent(client)) == 2


def test_paid_action_does_not_rewrite_unselected_duplicate_cells(tmp_path, monkeypatch):
    case, engine, client, _ = setup(tmp_path, monkeypatch)
    store, project, _ = case
    payload = store.load(project)
    payload['source'][0]['Name'] = payload['master'][0]['Name']
    store.save(project, payload)
    engine.detect({'master':['Name'],'source':['Name']})
    rows = engine.records()
    selected = [r for r in rows if r['dataset']=='master' and r['row_id']==0]
    def source_payload():
        with store.connect() as db:
            return db.execute("SELECT payload FROM translations WHERE project=? AND dataset='source' AND row_id=0 ORDER BY rowid DESC LIMIT 1", (project,)).fetchone()[0]
    before = source_payload()
    scope = TranslationWorkspace(engine)
    preview = scope.detection_plan(250, selection=selected)
    scope.run_detection(250, True, selection=selected, preview=preview)
    assert len(sent(client)) == 1
    assert source_payload() == before


def test_ui_master_filter_includes_all_pages_and_immediate_refresh(tmp_path, monkeypatch):
    case, engine, client, _ = setup(tmp_path, monkeypatch, count=30)
    app = app_for(case, monkeypatch)
    navigate(app, 'Translation Intelligence')
    by_label(app.selectbox, 'Translation dataset').set_value('Master').run()
    assert len(app.dataframe[0].value) == 25
    assert any('Detect languages for 30 Master records' in c.value for c in app.caption)
    authorize(app)
    assert len(sent(client)) == 30
    assert all(text.startswith('Société') for text in sent(client))
    assert set(app.dataframe[0].value['Detected Language']) == {'fr'}
    assert by_label(app.button, 'Detect Languages').disabled
    app.run()
    assert len(sent(client)) == 30


def test_ui_selection_consent_and_hidden_selections(tmp_path, monkeypatch):
    case, engine, client, factory = setup(tmp_path, monkeypatch)
    app = app_for(case, monkeypatch)
    navigate(app, 'Translation Intelligence')
    edit_selection(app, range(5))
    assert any('Detect languages for 5 selected records' in c.value for c in app.caption)
    by_label(app.checkbox, DETECT_CONSENT).check().run()
    by_label(app.text_input, 'Search accounts').set_value('Atelier 0').run()
    assert not by_label(app.checkbox, DETECT_CONSENT).value
    by_label(app.button, 'Detect Languages').click().run()
    factory.assert_not_called()
    assert app.error
    authorize(app)
    assert sent(client) == ['Société Atelier 0']
    by_label(app.selectbox, 'Translation dataset').set_value('Source').run()
    assert by_label(app.button, 'Detect Languages').disabled
    assert not app.exception


def test_ui_five_checks_send_five_names_only(tmp_path, monkeypatch):
    case, engine, client, _ = setup(tmp_path, monkeypatch)
    app = app_for(case, monkeypatch)
    navigate(app, 'Translation Intelligence')
    edit_selection(app, range(5))
    chosen = set(app.dataframe[0].value['Original Company Name'][:5])
    authorize(app)
    assert set(sent(client)) == chosen
    assert len(sent(client)) == 5


def test_duplicate_names_deduplicate_but_consent_tracks_exact_cell_ids(tmp_path, monkeypatch):
    case, engine, client, factory = setup(tmp_path, monkeypatch)
    store, project, _ = case
    payload = store.load(project)
    payload['source'][0]['Name'] = payload['master'][0]['Name']
    store.save(project, payload)
    engine.detect({'master':['Name'],'source':['Name']})
    rows = [r for r in engine.records() if r['row_id']==0]
    master = next(r for r in rows if r['dataset']=='master')
    source = next(r for r in rows if r['dataset']=='source')
    scope = TranslationWorkspace(engine)
    original = scope.detection_plan(250, selection=[master])
    with pytest.raises(ValueError, match='selection changed'):
        scope.run_detection(250, True, selection=[source], preview=original)
    factory.assert_not_called()
    preview = scope.detection_plan(250, selection=rows)
    assert preview['records_in_scope']==2 and preview['batch_size']==1
    scope.run_detection(250, True, selection=rows, preview=preview)
    assert sent(client)==[master['original']]
