"""Reproduce batched browser deltas that previously lost translation submits."""
from unittest.mock import Mock
import pytest
from tests.test_organization_draft_defaults import names
from tests.test_review_workflow import app_for
from tests.test_app import by_label,navigate
from tests.translation_workspace_helpers import select_visible,TRANSLATE_CONSENT


def ui(names, monkeypatch):
    from google.cloud import translate_v3
    factory=Mock(side_effect=AssertionError('No live API calls'))
    monkeypatch.setattr(translate_v3,'TranslationServiceClient',factory)
    app=app_for(names[0],monkeypatch)
    navigate(app,'Translation Intelligence')
    return app,factory


@pytest.mark.parametrize('change', ['selection','limit'])
def test_submit_is_not_silently_lost_when_batched_widget_changes_alter_preview(names,monkeypatch,change):
    app,factory=ui(names,monkeypatch)
    select_visible(app)
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    if change=='selection':
        # The checkbox edit and form submit arrive in one browser state update.
        app.session_state[app.dataframe[0].key]={'edited_rows':{1:{'Select':False}},'added_rows':[],'deleted_rows':[]}
    else:
        by_label(app.number_input,'Names per batch').set_value(1)
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception
    assert app.error, 'The changed preview must require reauthorization, not discard the button event.'
    factory.assert_not_called()


def test_no_selection_click_has_exact_feedback(names,monkeypatch):
    app,factory=ui(names,monkeypatch)
    assert not by_label(app.button,'Translate Selected').disabled
    by_label(app.button,'Translate Selected').click().run()
    assert any(m.value=='Select at least one account.' for m in app.warning)
    factory.assert_not_called()


def test_selection_survives_reruns_and_translates_after_changed_preview_reauthorization(names,monkeypatch):
    from tests.test_google_translation import response
    case,engine=names
    app,factory=ui(names,monkeypatch)
    select_visible(app)
    original=dict(app.session_state[f'translation_workspace_{case[1]}_selection'])
    for _ in range(3):
        app.run()
        assert app.session_state[f'translation_workspace_{case[1]}_selection']==original
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.number_input,'Names per batch').set_value(1)
    by_label(app.button,'Translate Selected').click().run()
    assert app.error
    factory.assert_not_called()
    client=Mock(); client.translate_text.return_value=response('English draft')
    factory.side_effect=None; factory.return_value=client
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception and client.translate_text.call_count==1
    assert any('1 translation drafts' in m.value for m in app.success)
    assert (app.dataframe[0].value['Translation Status']=='Translated — Review').sum()==1
    assert (app.dataframe[0].value['English Translation']=='English draft').sum()==1
    assert len(app.session_state[f'translation_workspace_{case[1]}_selection'])==2
    assert not by_label(app.checkbox,TRANSLATE_CONSENT).value
    assert len([r for r in engine.records() if r['english']])==1
    by_label(app.button,'Translate Selected').click().run()
    assert app.error and client.translate_text.call_count==1
    assert not case[0].load(case[1])['results'] and not case[0].audit(case[1])


def test_ineligible_selection_reports_english_and_missing_language_reasons(names,monkeypatch):
    from tests.translation_workspace_helpers import seed_google
    case,engine=names
    seed_google(engine,{'Les Jardins de Provence':'en','Servicios de Construcción':'und'})
    app,factory=ui(names,monkeypatch)
    select_visible(app)
    by_label(app.button,'Translate Selected').click().run()
    assert any('English names' in m.value and 'Detect or confirm missing languages' in m.value for m in app.warning)
    factory.assert_not_called()
    assert not any(r['english'] for r in engine.records())


def test_api_failures_persist_and_report_with_progress_and_fresh_consent(names,monkeypatch):
    from google.api_core.exceptions import PermissionDenied
    from rta.translation_usage import GoogleTranslationUsage
    case,engine=names
    app,factory=ui(names,monkeypatch)
    client=Mock(); client.translate_text.side_effect=PermissionDenied('private provider payload')
    factory.side_effect=None; factory.return_value=client
    progress=Mock()
    monkeypatch.setattr('rta.translation_ui.st.progress',Mock(return_value=progress))
    select_visible(app)
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception
    assert client.translate_text.call_count==2
    progress.progress.assert_not_called()  # Committed results go directly to a fresh table rerun.
    assert any('0 translation drafts' in m.value and '2 failed' in m.value for m in app.warning)
    assert set(app.dataframe[0].value['Translation Status'])=={'Failed'}
    assert all(r['status']=='Failed' and not r['english'] for r in engine.records())
    assert not by_label(app.checkbox,TRANSLATE_CONSENT).value
    by_label(app.button,'Translate Selected').click().run()
    assert app.error and client.translate_text.call_count==2
    usage=GoogleTranslationUsage(case[0],case[1]).summary()
    assert usage['requests']==2 and usage['uncertain_characters']>0
    assert 'private provider payload' not in str([m.value for m in [*app.error,*app.warning]])
    assert not case[0].audit(case[1])
    client.detect_language.assert_not_called()


def test_runtime_failure_is_visible_and_redacted(names,monkeypatch):
    app,factory=ui(names,monkeypatch)
    select_visible(app)
    monkeypatch.setattr('rta.translation_ui.TranslationEngine.process',Mock(side_effect=RuntimeError('private token')))
    by_label(app.checkbox,TRANSLATE_CONSENT).check()
    by_label(app.button,'Translate Selected').click().run()
    assert not app.exception
    assert any('Translation could not complete' in m.value for m in app.error)
    assert all('private token' not in m.value for m in app.error)
    factory.assert_not_called()
