"""Main-editor multi-selection, bounded execution and committed table refresh."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from google.cloud import translate_v3
from google.api_core.exceptions import PermissionDenied
from rta.translation_workspace import row_id
from tests.test_google_detection import google_case
from tests.test_google_translation import response
from tests.test_review_workflow import app_for
from tests.test_app import by_label,navigate
from tests.translation_workspace_helpers import seed_google,TRANSLATE_CONSENT

NAMES=['Les Jardins de Provence','Boulangerie du Soleil','Société des Transports',
       'Les Ateliers de la Lune','La Fabrique des Nuages']


def setup(tmp_path,monkeypatch,extra=0):
    master=[{'Name':text} for text in NAMES[:3]]
    source=[{'Name':text} for text in NAMES[3:]]+[{'Name':f'Fictional English Account {i}'} for i in range(extra)]
    case,engine=google_case(tmp_path,master,source)
    seed_google(engine,{**dict.fromkeys(NAMES,'fr'),**{r['Name']:'en' for r in source[2:]}},
                {'master':['Name'],'source':['Name']})
    client=Mock()
    client.translate_text.side_effect=lambda **kw:response(*['English: '+text for text in kw['request']['contents']])
    factory=Mock(return_value=client)
    monkeypatch.setattr(translate_v3,'TranslationServiceClient',factory)
    app=app_for(case,monkeypatch);navigate(app,'Translation Intelligence')
    return case,engine,app,client,factory


def edit_selection(app,positions):
    app.session_state[app.dataframe[0].key]={'edited_rows':{p:{'Select':True} for p in positions},
                                           'added_rows':[],'deleted_rows':[]}
    app.run()
    assert not app.exception


def authorize(app):
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception


def test_editor_input_is_immutable_during_checkbox_edits(tmp_path,monkeypatch):
    case,engine,app,client,factory=setup(tmp_path,monkeypatch)
    original=app.dataframe[0].value.copy(deep=True)
    edit_selection(app,[0])
    app.run()
    assert app.dataframe[0].value.equals(original), 'Changing the editor baseline resets client edit state.'
    assert len(app.session_state[f'translation_workspace_{case[1]}_selection'])==1
    factory.assert_not_called()


def test_post_commit_progress_error_cannot_prevent_refresh(tmp_path,monkeypatch):
    case,engine,app,client,factory=setup(tmp_path,monkeypatch)
    edit_selection(app,range(5))
    progress=Mock();progress.progress.side_effect=RuntimeError('stale frontend progress')
    monkeypatch.setattr('rta.translation_ui.st.progress',Mock(return_value=progress))
    authorize(app)
    assert len([r for r in engine.records() if r['english']])==5
    assert set(app.dataframe[0].value['Translation Status'])=={'Translated — Review'}
    assert all(app.dataframe[0].value['English Translation'])
    assert any('5 translation drafts' in m.value for m in app.success)
    progress.progress.assert_not_called()


@pytest.mark.parametrize('count',[1,5])
def test_sequential_checkbox_selection_translates_every_record_and_refreshes(tmp_path,monkeypatch,count):
    case,engine,app,client,factory=setup(tmp_path,monkeypatch)
    before=deepcopy(case[0].load(case[1]))
    baseline_key=app.dataframe[0].key
    for i in range(count):
        edit_selection(app,range(i+1))
        app.run()  # A plain rerun must not clear the accumulated selection.
        assert app.dataframe[0].key==baseline_key
        selected=app.session_state[f'translation_workspace_{case[1]}_selection']
        assert len(selected)==i+1
        assert set(selected)=={row_id(r) for r in engine.records()[:i+1]}
    factory.assert_not_called()
    by_label(app.button,'Translate Selected').click().run()
    assert app.error
    factory.assert_not_called()
    authorize(app)
    drafts=[r for r in engine.records() if r['status']=='Translated — Review']
    assert len(drafts)==count and client.translate_text.call_count==1
    assert len(client.translate_text.call_args.kwargs['request']['contents'])==count
    visible=app.dataframe[0].value
    assert (visible['Translation Status']=='Translated — Review').sum()==count
    assert visible['English Translation'].astype(bool).sum()==count
    assert app.dataframe[0].key!=baseline_key
    assert len(app.session_state[f'translation_workspace_{case[1]}_selection'])==count
    assert not by_label(app.checkbox,TRANSLATE_CONSENT).value
    assert any(f'{count} translation drafts' in msg.value for msg in app.success)
    for _ in range(2):app.run()
    assert client.translate_text.call_count==1
    assert case[0].load(case[1])['master']==before['master']
    assert case[0].load(case[1])['source']==before['source']
    assert not case[0].load(case[1])['results'] and not case[0].audit(case[1])


def test_partial_checkbox_deltas_preserve_stable_ids_across_datasets_and_pages(tmp_path,monkeypatch):
    from rta.translation_workspace import merge_selection
    case,engine,app,client,factory=setup(tmp_path,monkeypatch)
    rows=engine.records()
    selected={}
    for item in rows:
        selected=merge_selection(selected,[item],{'0':{'Select':True}})
    assert len(selected)==5
    assert row_id(rows[0])!=row_id(rows[3])  # Both have source row_id zero.
    selected=merge_selection(selected,[rows[3]],{0:{'Select':False}})
    assert row_id(rows[0]) in selected and row_id(rows[3]) not in selected
    assert len(selected)==4
    assert merge_selection(selected,[rows[0]],{0:{'English Translation':'Edited'}})==selected
    assert merge_selection(selected,[rows[0]],{99:{'Select':True},-1:{'Select':True}})==selected
    # Feed the editor state as partial deltas, not a full page selection snapshot.
    for i in range(5):edit_selection(app,[i])
    assert len(app.session_state[f'translation_workspace_{case[1]}_selection'])==5
    authorize(app)
    assert len([r for r in engine.records() if r['english']])==5
    assert client.translate_text.call_count==1


def test_batch_limit_reports_membership_and_advances_without_duplicates(tmp_path,monkeypatch):
    case,engine,app,client,factory=setup(tmp_path,monkeypatch)
    edit_selection(app,range(5))
    by_label(app.number_input,'Names per batch').set_value(2).run()
    assert any('2 in this batch' in c.value and '3 remaining' in c.value for c in app.caption)
    manifest=next(c.value for c in app.caption if c.value.startswith('This batch:'))
    assert 'Master · Name rows 1' in manifest and 'Source · Name rows 1' in manifest
    assert 'Remaining:' in manifest
    authorize(app)
    first=[r for r in engine.records() if r['english']]
    assert {(r['dataset'],r['row_id']) for r in first}=={('master',0),('source',0)}
    assert len(app.session_state[f'translation_workspace_{case[1]}_selection'])==5
    assert any('2 in this batch' in c.value and '1 remaining' in c.value for c in app.caption)
    by_label(app.button,'Translate Selected').click().run()
    assert app.error and client.translate_text.call_count==1
    authorize(app)
    assert len([r for r in engine.records() if r['english']])==4
    assert not by_label(app.checkbox,TRANSLATE_CONSENT).value
    authorize(app)
    assert len([r for r in engine.records() if r['english']])==5
    sent=[text for call in client.translate_text.call_args_list for text in call.kwargs['request']['contents']]
    assert len(sent)==len(set(sent))==5 and client.translate_text.call_count==3
    app.run();assert client.translate_text.call_count==3


def test_cached_and_approved_records_reported_and_preserved(tmp_path,monkeypatch):
    import json
    from rta.translation import cache_key,cell_key
    from rta.translation_providers import GoogleTranslationProvider
    case,engine,app,client,factory=setup(tmp_path,monkeypatch)
    records=engine.records()
    provider=GoogleTranslationProvider()
    with case[0].connect() as db:
        for text in (NAMES[0],NAMES[3]):
            cached={'english':'Cached '+text,'provider':provider.name,'model':provider.model,
                    'status':'Translated — Review','reason':'','cache_hit':False}
            db.execute('INSERT INTO translation_cache VALUES (?,?,?)',(case[1],cache_key(text,'fr',provider),json.dumps(cached)))
    approved=engine.approve(records[1],'Reviewed existing English','Reviewer',True,'fr')
    audit=case[0].audit(case[1])
    app.run();edit_selection(app,range(5));authorize(app)
    assert sum(r['status']=='Translated — Review' for r in engine.records())==4
    assert next(r for r in engine.records() if row_id(r)==row_id(approved))==approved
    assert any('2 cached/reused drafts; 1 skipped records' in m.value for m in app.success)
    assert client.translate_text.call_count==1
    assert len(client.translate_text.call_args.kwargs['request']['contents'])==2
    assert case[0].audit(case[1])==audit
    assert (app.dataframe[0].value['Translation Status']=='Approved Translation').sum()==1


def test_partial_failures_refresh_all_statuses_and_require_new_consent(tmp_path,monkeypatch):
    case,engine,app,client,factory=setup(tmp_path,monkeypatch)
    seed_google(engine,{**dict.fromkeys(NAMES[:3],'fr'),**dict.fromkeys(NAMES[3:],'de')})
    def translate(**kw):
        if kw['request']['source_language_code']=='de':raise PermissionDenied('private provider message')
        return response(*['English '+text for text in kw['request']['contents']])
    client.translate_text.side_effect=translate
    app.run();edit_selection(app,range(5));authorize(app)
    assert sum(r['status']=='Translated — Review' for r in engine.records())==3
    assert sum(r['status']=='Failed' for r in engine.records())==2
    visible=app.dataframe[0].value
    assert (visible['Translation Status']=='Translated — Review').sum()==3
    assert (visible['Translation Status']=='Failed').sum()==2
    assert any('3 translation drafts' in m.value and '2 failed' in m.value for m in app.warning)
    assert client.translate_text.call_count==2
    app.run();by_label(app.button,'Translate Selected').click().run()
    assert app.error and client.translate_text.call_count==2


def test_search_dataset_and_second_page_preserved_after_five_record_batch(tmp_path,monkeypatch):
    master=[{'Name':n} for n in NAMES[:3]]
    source=[{'Name':f'English Company {i}'} for i in range(30)]+[{'Name':n} for n in NAMES[3:]]
    case,engine=google_case(tmp_path,master,source)
    seed_google(engine,{**dict.fromkeys(NAMES,'fr'),**{r['Name']:'en' for r in source[:30]}},
                {'master':['Name'],'source':['Name']})
    client=Mock();client.translate_text.side_effect=lambda **kw:response(*['English '+text for text in kw['request']['contents']])
    monkeypatch.setattr(translate_v3,'TranslationServiceClient',Mock(return_value=client))
    app=app_for(case,monkeypatch);navigate(app,'Translation Intelligence')
    edit_selection(app,range(3))
    by_label(app.selectbox,'Translation dataset').set_value('Source').run()
    by_label(app.text_input,'Search accounts').set_value('e').run()
    by_label(app.number_input,'Translation page').set_value(2).run()
    edit_selection(app,[5,6])
    assert len(app.session_state[f'translation_workspace_{case[1]}_selection'])==5
    authorize(app)
    assert by_label(app.number_input,'Translation page').value==2
    assert by_label(app.text_input,'Search accounts').value=='e'
    assert by_label(app.selectbox,'Translation dataset').value=='Source'
    assert (app.dataframe[0].value['Translation Status']=='Translated — Review').sum()==2
    assert sum(r['status']=='Translated — Review' for r in engine.records())==5
    assert client.translate_text.call_count==1


def test_active_status_filter_requeries_and_hides_completed_rows_without_clear(tmp_path,monkeypatch):
    case,engine,app,client,factory=setup(tmp_path,monkeypatch)
    by_label(app.selectbox,'Translation status').set_value('Translation Needed').run()
    edit_selection(app,range(5));authorize(app)
    assert by_label(app.selectbox,'Translation status').value=='Translation Needed'
    assert len(app.dataframe[0].value)==0
    assert sum(r['status']=='Translated — Review' for r in engine.records())==5
    by_label(app.selectbox,'Translation status').set_value('All').run()
    assert set(app.dataframe[0].value['Translation Status'])=={'Translated — Review'}
    assert client.translate_text.call_count==1
