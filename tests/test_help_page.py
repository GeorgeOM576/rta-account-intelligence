"""Static guide navigation must neither load workspaces nor contact providers."""
from copy import deepcopy
from html import unescape
from pathlib import Path
from unittest.mock import Mock
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from google.cloud import translate_v3
from rta.help_ui import STEPS, SUBTITLE, MATCHES, REVIEWS
from rta.models import REVIEW_FILTERS
from tests.test_app import by_label, navigate
from tests.test_review_workflow import workspace, app_for

ROOT=Path(__file__).resolve().parents[1]


def assert_guide(app):
    assert not app.exception
    assert by_label(app.radio,'Workspace').options[:3]==['Dashboard','How to Use RTA','Upload Data']
    assert app.title[0].value=='How to Use RTA'
    text=unescape('\n'.join(x.value for x in app.markdown))
    assert SUBTITLE in text
    for _,title,_ in STEPS:assert title in text
    for title in ('Understanding the results','Helpful tips'):
        assert any(h.value==title for h in app.subheader)
    assert not app.dataframe and not app.json
    assert 'Proposed Value' in text and 'Final Value' in text
    assert not [b for b in app.button if 'paid' in b.label.lower()]


def test_new_empty_workspace_navigation_and_existing_pages(tmp_path,monkeypatch):
    monkeypatch.setenv('RTA_DB_PATH',str(tmp_path/'help.sqlite3'))
    app=AppTest.from_file(ROOT/'app.py',default_timeout=30).run()
    project=app.session_state['project']
    navigate(app,'How to Use RTA')
    assert_guide(app)
    for page in ['Upload Data','Configure Reconciliation','Translation Intelligence',
                 'Run Reconciliation','AI Research','Review & Approvals','Export Results','Settings','Dashboard']:
        navigate(app,page)
        assert app.session_state['project']==project
    navigate(app,'How to Use RTA')
    assert_guide(app)


def test_first_render_without_workspace_has_zero_database_or_api_calls(tmp_path,monkeypatch):
    original_radio=st.radio
    def help_default(label,options,**kwargs):
        if label=='Workspace':kwargs['index']=list(options).index('How to Use RTA')
        return original_radio(label,options,**kwargs)
    monkeypatch.setattr(st,'radio',help_default)
    forbidden=Mock(side_effect=AssertionError('Static guide must not access storage or providers'))
    monkeypatch.setattr('rta.storage.Store.__init__',forbidden)
    monkeypatch.setattr('sqlite3.connect',forbidden)
    monkeypatch.setattr(translate_v3,'TranslationServiceClient',forbidden)
    monkeypatch.setattr('rta.google_auth.translation_client',forbidden)
    monkeypatch.setattr('requests.sessions.Session.request',forbidden)
    path=tmp_path/'must-not-exist.sqlite3'
    monkeypatch.setenv('RTA_DB_PATH',str(path))
    app=AppTest.from_file(ROOT/'app.py',default_timeout=30).run()
    assert_guide(app)
    app.run()
    assert_guide(app)
    forbidden.assert_not_called()
    assert not path.exists()
    with pytest.raises(KeyError):app.session_state['project']


def test_guide_preserves_existing_workspace_and_pending_session_input(workspace,monkeypatch):
    store,project,_=workspace
    app=app_for(workspace,monkeypatch)
    before=deepcopy(store.load(project));audit=deepcopy(store.audit(project))
    app.session_state['translation_workspace_'+project+'_selection']={'stable-id':{'row_id':3}}
    app.session_state['reviewer_draft_help_test']='Pending reviewer text'
    by_label(app.radio,'Workspace').set_value('How to Use RTA')
    with monkeypatch.context() as blocked:
        forbidden=Mock(side_effect=AssertionError('Guide must not access workspace'))
        blocked.setattr('rta.storage.Store.__init__',forbidden)
        blocked.setattr('sqlite3.connect',forbidden)
        app.run();assert_guide(app)
        app.run();assert_guide(app)
        forbidden.assert_not_called()
    assert app.session_state['reviewer_draft_help_test']=='Pending reviewer text'
    assert app.session_state['translation_workspace_'+project+'_selection']=={'stable-id':{'row_id':3}}
    navigate(app,'Run Reconciliation')
    assert store.load(project)==before and store.audit(project)==audit
    assert app.session_state['project']==project


def test_guide_status_labels_and_reading_length_match_implementation():
    assert [name for name,_ in REVIEWS]==REVIEW_FILTERS[1:]
    labels=' / '.join(name for name,_ in MATCHES)
    for status in ['Exact','Normalized','Alias','Relationship','Translation-assisted',
                   'Fuzzy candidates','Duplicate identifier','Duplicate conflict','Missing identifier','Unresolved']:
        assert status in labels
    text=' '.join(body for _,_,body in STEPS)+' '.join(meaning for _,meaning in MATCHES+REVIEWS)
    assert len(text.split())<500
