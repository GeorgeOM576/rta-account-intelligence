"""Exercise real Streamlit actions, including a rerun at a progress yield."""
from unittest.mock import Mock
import streamlit as st
from tests.test_organization_draft_defaults import names
from tests.test_review_workflow import app_for
from tests.test_app import by_label,navigate
from tests.translation_workspace_helpers import select_visible,TRANSLATE_CONSENT
from tests.test_google_translation import response


def test_google_responses_survive_rerun_after_completion_and_refresh_table(names,monkeypatch):
    case,engine=names
    from google.cloud import translate_v3
    client=Mock();client.translate_text.side_effect=lambda **kw:response(*['English company draft' for _ in kw['request']['contents']])
    factory=Mock(return_value=client)
    monkeypatch.setattr(translate_v3,'TranslationServiceClient',factory)
    app=app_for(case,monkeypatch);navigate(app,'Translation Intelligence')
    select_visible(app)
    interrupted=[]
    actual_finish=trace.finish
    def finish(*args,**kwargs):
        actual_finish(*args,**kwargs)
        if kwargs.get('persisted') and not interrupted:
            interrupted.append(True)
            st.rerun()
    monkeypatch.setattr(trace,'finish',finish)
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception
    assert client.translate_text.call_count==2 and interrupted
    drafts=[r for r in engine.records() if r['status']=='Translated — Review']
    assert len(drafts)==2, 'A queued rerun must not discard paid responses after the first saved row.'
    assert set(app.dataframe[0].value['English Translation'])=={'English company draft'}
    assert any('2 translation drafts' in m.value for m in app.success)
    app.run()
    assert client.translate_text.call_count==2
    assert not case[0].load(case[1])['results'] and not case[0].audit(case[1])


import json
import logging
import pytest
from google.cloud import translate_v3
from google.api_core.exceptions import PermissionDenied
from rta import translation_diagnostics as trace
from tests.test_google_detection import google_case,detected
from tests.translation_workspace_helpers import DETECT_CONSENT


def events(caplog):
    return [json.loads(r.message) for r in caplog.records if r.name=='rta.translation.action']


@pytest.mark.parametrize('mode',['success','denied','ineligible','unconsented'])
def test_real_streamlit_detection_selection_translation_and_count_only_trace(tmp_path,monkeypatch,caplog,mode):
    original='Les Jardins de Provence'
    case,engine=google_case(tmp_path,[{'Name':original}],[{'Name':'Cedar Labs'}])
    engine.detect({'master':['Name'],'source':['Name']})
    client=Mock()
    client.detect_language.side_effect=lambda **kw:detected('fr' if kw['request']['content']==original and mode!='ineligible' else 'en',.99)
    if mode=='denied':
        client.translate_text.side_effect=PermissionDenied('DO_NOT_LOG_TOKEN_OR_ACCOUNT')
    else:
        client.translate_text.return_value=translate_v3.TranslateTextResponse(
            translations=[translate_v3.Translation(translated_text='Gardens of Provence')])
    factory=Mock(return_value=client)
    monkeypatch.setattr(translate_v3,'TranslationServiceClient',factory)
    caplog.set_level(logging.INFO,logger=trace.logger.name)
    app=app_for(case,monkeypatch);navigate(app,'Translation Intelligence')
    by_label(app.checkbox,DETECT_CONSENT).check()
    by_label(app.button,'Detect Languages').click().run()
    assert not app.exception and client.detect_language.call_count==2
    by_label(app.selectbox,'Translation dataset').set_value('Master').run()
    # Use the actual main editor's selection column, rather than backend process().
    app.session_state[app.dataframe[0].key]={'edited_rows':{0:{'Select':True}},'added_rows':[],'deleted_rows':[]}
    app.run()
    if mode!='unconsented':by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception
    logged=events(caplog)
    submit=next(e for e in logged if e['stage']=='submission_received')
    assert submit['selected_rows']==1
    assert submit['eligible_rows']==(0 if mode=='ineligible' else 1)
    assert submit['authorized']==(mode!='unconsented')
    stages=[e['stage'] for e in logged]
    if mode in ('unconsented','ineligible'):
        client.translate_text.assert_not_called()
        assert 'google_request_attempted' not in stages
        assert app.error if mode=='unconsented' else app.warning
        if mode=='ineligible':assert submit['excluded_reasons']=={'english':1}
    else:
        assert client.translate_text.call_count==1
        assert 'google_request_attempted' in stages and 'table_refresh_completed' in stages
        assert {e['action_id'] for e in logged}=={submit['action_id']}
        item=next(r for r in engine.records() if r['dataset']=='master')
        if mode=='success':
            assert item['english']=='Gardens of Provence' and item['status']=='Translated — Review'
            assert app.dataframe[0].value.iloc[0]['English Translation']=='Gardens of Provence'
            assert app.dataframe[0].value.iloc[0]['Translation Status']=='Translated — Review'
            assert stages.index('google_response_received')<stages.index('translation_record_persisted')<stages.index('table_refresh_completed')
            assert next(e for e in logged if e['stage']=='action_completed')['drafts']==1
            assert app.success
        else:
            assert item['status']=='Failed' and not item['english'] and app.warning
            assert next(e for e in logged if e['stage']=='google_request_exception')['error_code']=='permission_denied'
    assert original not in caplog.text and 'Gardens of Provence' not in caplog.text
    assert 'DO_NOT_LOG_TOKEN_OR_ACCOUNT' not in caplog.text
    assert not case[0].load(case[1])['results'] and not case[0].audit(case[1])
    assert case[0].load(case[1])['master'][0]['Name']==original


def test_diagnostics_allowlist_and_disable_switch(caplog,monkeypatch):
    caplog.set_level(logging.INFO,logger=trace.logger.name)
    trace.event('submission_received',selected_rows=2,credentials='PRIVATE',account='SENSITIVE',
                excluded_reasons={'english':1,'SENSITIVE_ACCOUNT_NAME':5},error_code='PRIVATE_EXCEPTION')
    text=caplog.text
    assert 'PRIVATE' not in text and 'SENSITIVE' not in text
    assert events(caplog)[-1]['error_code']=='runtime'
    caplog.clear()
    monkeypatch.setenv('RTA_TRANSLATION_DIAGNOSTICS','0')
    trace.event('submission_received',selected_rows=1)
    assert not events(caplog)


def test_in_flight_workspace_guard_prevents_second_paid_batch(names,monkeypatch):
    case,engine=names
    from google.cloud import translate_v3
    factory=Mock(side_effect=AssertionError('Must not dispatch another paid batch'))
    monkeypatch.setattr(translate_v3,'TranslationServiceClient',factory)
    active=trace.begin(case[0],case[1],'another_browser',set())
    app=app_for(case,monkeypatch);navigate(app,'Translation Intelligence')
    select_visible(app)
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception and any('already processing' in m.value for m in app.warning)
    factory.assert_not_called()
    trace.finish(case[0],case[1],active['id'],'Finished')
    assert all(not r['english'] for r in engine.records())


def test_interruption_before_dispatch_releases_guard_and_does_not_authorize_retry(names,monkeypatch):
    case,engine=names
    client=Mock();client.translate_text.return_value=response('English draft')
    factory=Mock(return_value=client)
    monkeypatch.setattr(translate_v3,'TranslationServiceClient',factory)
    app=app_for(case,monkeypatch);navigate(app,'Translation Intelligence')
    select_visible(app)
    original=st.progress
    interrupted=[]
    def progress(*args,**kwargs):
        if not interrupted:
            interrupted.append(True)
            st.rerun()
        return original(*args,**kwargs)
    monkeypatch.setattr('rta.translation_ui.st.progress',progress)
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception and any('interrupted' in m.value for m in app.warning)
    factory.assert_not_called()
    assert trace.latest(case[0],case[1])['status']=='failed'
    assert not by_label(app.checkbox,TRANSLATE_CONSENT).value
    by_label(app.button,'Translate Selected').click().run()
    assert app.error
    factory.assert_not_called()
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception and client.translate_text.call_count==2
    assert all(r['status']=='Translated — Review' for r in engine.records())
