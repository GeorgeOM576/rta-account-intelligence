"""Keep tests independent of developer secrets and forbid unmocked provider HTTP."""
import pytest
import requests
import streamlit as st


@pytest.fixture(autouse=True)
def isolate_provider_secrets(monkeypatch):
    # Preserve configured research UI behavior with fictional keys. Offline/auth
    # tests explicitly replace these. Never read real developer/Cloud secrets.
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('TAVILY_API_KEY', raising=False)
    monkeypatch.setattr(st, 'secrets', {
        'OPENAI_API_KEY': 'fixture-openai-not-a-real-key',
        'TAVILY_API_KEY': 'fixture-tavily-not-a-real-key',
    })

    def forbidden(*args, **kwargs):
        raise AssertionError('Unmocked provider HTTP is forbidden in automated tests.')

    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
