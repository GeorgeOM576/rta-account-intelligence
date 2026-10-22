"""Cloud secret and ADC authentication use mocked clients; no Google calls."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import traceback
import pytest
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from google.cloud import translate_v3
from google.oauth2 import service_account
from rta.google_auth import translation_client, SCOPES
from rta.google_detection import GoogleDetectionProvider
from rta.translation_providers import GoogleTranslationProvider
from tests.test_google_detection import detected
from tests.test_google_translation import response


@pytest.fixture
def auth(monkeypatch):
    # Deliberately invalid, non-secret material: credential parsing is mocked.
    info = {'type':'service_account','project_id':'rta-translation',
            'client_email':'fixture@example.invalid','private_key':'FAKE-KEY-MATERIAL',
            'token_uri':'https://oauth2.googleapis.com/token'}
    monkeypatch.setattr(st, 'secrets', {'gcp_service_account':info})
    credential = Mock(name='mock_credentials')
    parser = Mock(return_value=credential)
    monkeypatch.setattr(service_account.Credentials, 'from_service_account_info', parser)
    client = Mock()
    client.detect_language.return_value = detected('fr')
    client.translate_text.return_value = response('Hello world')
    factory = Mock(return_value=client)
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    return info, credential, parser, client, factory


def test_cloud_credentials_and_quota_project(auth):
    info, credential, parser, client, factory = auth
    before = deepcopy(info)
    assert translation_client() is client
    parser.assert_called_once_with(info, scopes=SCOPES)
    assert factory.call_args.kwargs['credentials'] is credential
    assert factory.call_args.kwargs['client_options'].quota_project_id == 'rta-translation'
    assert info == before
    client.detect_language.assert_not_called()
    client.translate_text.assert_not_called()


def test_local_adc_when_section_absent(auth, monkeypatch):
    _, _, parser, client, factory = auth
    monkeypatch.setattr(st, 'secrets', {'OPENAI_API_KEY':''})
    assert translation_client() is client
    parser.assert_not_called()
    assert 'credentials' not in factory.call_args.kwargs


@pytest.mark.parametrize('exception', [FileNotFoundError(),
    StreamlitSecretNotFoundError('No secrets', error_id='no-secrets-found')])
def test_missing_local_secrets_file_uses_adc(auth, monkeypatch, exception):
    _, _, parser, client, factory = auth
    monkeypatch.setattr(st, 'secrets', SimpleNamespace(get=Mock(side_effect=exception)))
    assert translation_client() is client
    parser.assert_not_called()
    assert 'credentials' not in factory.call_args.kwargs


@pytest.mark.parametrize('section', [{}, '', 'invalid', {'private_key':'invalid'}])
def test_invalid_configured_account_never_silently_falls_back(auth, monkeypatch, section):
    _, _, parser, _, factory = auth
    parser.side_effect = ValueError('PRIVATE-PARSER-DETAIL')
    monkeypatch.setattr(st, 'secrets', {'gcp_service_account':section})
    with pytest.raises(ValueError, match='Google authentication unavailable') as caught:
        translation_client()
    assert 'PRIVATE-PARSER-DETAIL' not in ''.join(traceback.format_exception(caught.value))
    factory.assert_not_called()


def test_malformed_secret_file_is_sanitized_and_does_not_use_adc(auth, monkeypatch):
    _, _, parser, _, factory = auth
    error = StreamlitSecretNotFoundError('PRIVATE-TOML-DETAIL', error_id='failed-parsing-secrets-file')
    monkeypatch.setattr(st, 'secrets', SimpleNamespace(get=Mock(side_effect=error)))
    with pytest.raises(ValueError) as caught:
        translation_client()
    assert 'PRIVATE-TOML-DETAIL' not in ''.join(traceback.format_exception(caught.value))
    parser.assert_not_called(); factory.assert_not_called()


def test_both_providers_use_shared_authenticated_client_after_consent(auth):
    _, credential, parser, client, factory = auth
    detection = GoogleDetectionProvider()
    translation = GoogleTranslationProvider()
    with pytest.raises(ValueError, match='confirmation'):
        detection.detect('Bonjour le monde')
    with pytest.raises(ValueError, match='confirmation'):
        translation.prepare([('Bonjour le monde','fr')])
    parser.assert_not_called(); factory.assert_not_called()
    detection.consent = True
    assert detection.detect('Bonjour le monde')['language_code'] == 'fr'
    translation.consent = True
    translation.prepare([('Bonjour le monde','fr')])
    assert translation.translate('Bonjour le monde','fr') == 'Hello world'
    assert parser.call_count == factory.call_count == 2
    assert all(call.kwargs['credentials'] is credential for call in factory.call_args_list)
    assert client.detect_language.call_count == client.translate_text.call_count == 1
    assert client.detect_language.call_args.kwargs['request']['parent'] == 'projects/rta-translation/locations/global'
    assert client.translate_text.call_args.kwargs['request']['target_language_code'] == 'en'


def test_invalid_credentials_never_reach_usage_ledger_or_leak_to_logs(auth, caplog):
    _, _, parser, client, factory = auth
    parser.side_effect = ValueError('FAKE-KEY-MATERIAL PRIVATE-PARSER-DETAIL')
    usage = Mock()
    for provider in [GoogleDetectionProvider(consent=True,usage=usage), GoogleTranslationProvider(consent=True,usage=usage)]:
        with pytest.raises(ValueError) as caught:
            if isinstance(provider,GoogleDetectionProvider):provider.detect('Bonjour')
            else:provider.prepare([('Bonjour','fr')])
        rendered = ''.join(traceback.format_exception(caught.value))
        assert 'PRIVATE-PARSER-DETAIL' not in rendered and 'FAKE-KEY-MATERIAL' not in rendered
    usage.start_request.assert_not_called()
    factory.assert_not_called()
    client.detect_language.assert_not_called();client.translate_text.assert_not_called()
    assert 'PRIVATE-PARSER-DETAIL' not in caplog.text and 'FAKE-KEY-MATERIAL' not in caplog.text


def test_adc_setup_failure_is_sanitized(auth,monkeypatch):
    _, _, parser, _, factory = auth
    monkeypatch.setattr(st,'secrets',{})
    factory.side_effect = RuntimeError('PRIVATE-ADC-DETAIL')
    with pytest.raises(ValueError) as caught:translation_client()
    assert 'PRIVATE-ADC-DETAIL' not in ''.join(traceback.format_exception(caught.value))
    parser.assert_not_called()


def test_secret_rotation_is_read_on_next_client(auth):
    info, _, parser, _, _ = auth
    translation_client()
    info['client_email']='rotated-fixture@example.invalid'
    translation_client()
    assert parser.call_count==2
    assert parser.call_args.args[0]['client_email']=='rotated-fixture@example.invalid'


def test_real_ui_cloud_detection_translation_and_sqlite_persistence(auth,tmp_path,monkeypatch,caplog):
    import json
    from tests.test_google_detection import google_case
    from tests.test_review_workflow import app_for
    from tests.test_app import navigate,by_label
    from tests.translation_workspace_helpers import DETECT_CONSENT,TRANSLATE_CONSENT
    info, credential, parser, client, factory = auth
    case,engine=google_case(tmp_path,[{'Name':'Bonjour le monde','Segment':'Verify'}],
                            [{'Name':'Cedar Labs','Segment':'SMB'}])
    engine.detect({'master':['Name'],'source':['Name']})
    app=app_for(case,monkeypatch)
    navigate(app,'Translation Intelligence')
    by_label(app.selectbox,'Translation dataset').set_value('Master').run()
    factory.assert_not_called()
    by_label(app.checkbox,DETECT_CONSENT).check()
    by_label(app.button,'Detect Languages').click().run()
    assert not app.exception
    assert list(app.dataframe[0].value['Detected Language'])==['fr']
    by_label(app.button,'Select all visible rows').click().run()
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception
    assert list(app.dataframe[0].value['English Translation'])==['Hello world']
    assert list(app.dataframe[0].value['Translation Status'])==['Translated — Review']
    assert factory.call_count==parser.call_count==2
    assert all(call.kwargs['credentials'] is credential for call in factory.call_args_list)
    app.run()
    assert client.detect_language.call_count==client.translate_text.call_count==1
    store,project,_=case
    with store.connect() as db:
        persisted='\n'.join(db.iterdump())
    assert info['private_key'] not in persisted and info['client_email'] not in persisted
    assert info['private_key'] not in caplog.text
    assert not store.load(project)['results']
    assert all(r['status']!='Approved Translation' for r in engine.records())
