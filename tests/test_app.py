"""Exercise actual Streamlit widgets through a complete offline workflow."""
from streamlit.testing.v1 import AppTest
from pathlib import Path
import streamlit as st


def by_label(elements, label):
    return next(e for e in elements if e.label == label)


def navigate(app, page):
    by_label(app.radio, 'Workspace').set_value(page).run()
    assert not app.exception


def test_offline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv('RTA_DB_PATH', str(tmp_path / 'app.sqlite3'))
    monkeypatch.delenv('TAVILY_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(st, 'secrets', {})
    app = AppTest.from_file(Path('app.py').resolve(), default_timeout=30).run()
    assert not app.exception
    navigate(app, 'Upload Data')
    by_label(app.button, 'Load synthetic example').click().run()
    assert not app.exception
    navigate(app, 'Configure Reconciliation')
    by_label(app.button, 'Save column mapping').click().run()
    assert not app.exception
    navigate(app, 'Run Reconciliation')
    by_label(app.button, 'Run automatic local matching').click().run()
    assert not app.exception
    results = app.session_state['payload']['results']
    assert len(results) == 10
    assert results[0]['proposed'] == 'Enterprise' and results[0]['final'] == ''
    assert results[1]['proposed'] == 'Healthcare' and not results[1]['final']
    assert results[3]['match_status'] == 'Duplicate conflict'
    navigate(app, 'AI Research')
    assert any('Offline mode' in w.value for w in app.warning)
    navigate(app, 'Review & Approvals')
    by_label(app.text_input, 'Reviewer name').set_value('Test reviewer')
    by_label(app.checkbox, 'I have verified the evidence and the field value for this specific account.').check()
    by_label(app.button, 'Save review decision').click().run()
    assert not app.exception
    reviewed = app.session_state['payload']['results'][1]
    assert reviewed['final'] == 'Healthcare' and reviewed['review_status'] == 'Approved'
    navigate(app, 'Run Reconciliation')
    by_label(app.button, 'Run automatic local matching').click().run()
    assert app.session_state['payload']['results'][1]['final'] == 'Healthcare'
    for page in ['Dashboard', 'Upload Data', 'Configure Reconciliation', 'Export Results', 'Settings']:
        navigate(app, page)
