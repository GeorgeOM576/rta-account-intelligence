from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import ServiceUnavailable, PermissionDenied, TooManyRequests

from rta.translation import TranslationEngine
from rta.translation_providers import GoogleTranslationProvider
from tests.test_translation import make_workspace, SPANISH, ENGLISH


def response(*values):
    return SimpleNamespace(translations=[SimpleNamespace(translated_text=v) for v in values])


def test_no_consent_no_calls():
    client = Mock()
    provider = GoogleTranslationProvider(client=client)
    with pytest.raises(ValueError, match='confirmation'):
        provider.prepare([('Bonjour', 'fr')])
    with pytest.raises(ValueError):
        provider.translate('Bonjour', 'fr')
    client.translate_text.assert_not_called()


def test_batching_and_sanitized_failures():
    client = Mock()
    client.translate_text.return_value = response(*(['Hello'] * 100))
    provider = GoogleTranslationProvider(consent=True, client=client)
    provider.prepare([(f'Bonjour {i}', 'fr') for i in range(200)])
    assert client.translate_text.call_count == 2
    for call in client.translate_text.call_args_list:
        request = call.kwargs['request']
        assert request['parent'] == 'projects/rta-translation/locations/global'
        assert request['target_language_code'] == 'en'
        assert request['mime_type'] == 'text/plain'
        assert call.kwargs['retry'] is None
    client.translate_text.reset_mock()
    client.translate_text.side_effect = PermissionDenied('secret credentials and provider text')
    provider.prepare([('Bonjour', 'fr')])
    assert client.translate_text.call_count == 1
    with pytest.raises(ValueError) as error:
        provider.translate('Bonjour', 'fr')
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('error', [ServiceUnavailable, TooManyRequests])
def test_bounded_retries(error):
    client, sleep = Mock(), Mock()
    client.translate_text.side_effect = [error('private'), error('private'), response('Hello')]
    provider = GoogleTranslationProvider(consent=True, client=client, sleep=sleep)
    provider.prepare([('Bonjour', 'fr')])
    assert provider.translate('Bonjour', 'fr') == 'Hello'
    assert client.translate_text.call_count == 3
    assert sleep.call_count == 2
    client.translate_text.side_effect = error('private')
    client.translate_text.reset_mock()
    provider.prepare([('Bonjour', 'fr')])
    assert client.translate_text.call_count == 3
    with pytest.raises(ValueError):
        provider.translate('Bonjour', 'fr')


def test_language_size_limits_and_partial_failure():
    client = Mock()
    client.translate_text.side_effect = [response('Hello'), PermissionDenied('private')]
    provider = GoogleTranslationProvider(consent=True, client=client)
    provider.prepare([('Bonjour', 'fr'), ('Hola', 'es'), ('x' * 30001, 'fr'), ('English', 'en')])
    assert client.translate_text.call_count == 2
    assert provider.translate('Hola', 'es') == 'Hello'
    for text, language in [('Bonjour', 'fr'), ('x' * 30001, 'fr'), ('English', 'en')]:
        with pytest.raises(ValueError):
            provider.translate(text, language)


def test_engine_preview_dedup_cache_and_review(tmp_path):
    row = {'Name': 'Example Corporation', 'Segment': 'SMB', 'Description': SPANISH}
    store, project, _ = make_workspace(tmp_path, master=[row, row], source=[row])
    engine = TranslationEngine(store, project)
    engine.detect({'master': ['Description'], 'source': ['Description']})
    before = store.load(project)
    client = Mock()
    client.translate_text.return_value = response(ENGLISH)
    provider = GoogleTranslationProvider(consent=True, client=client)
    plan = engine.plan(['master', 'source'], provider)
    assert plan['unique_texts'] == 1
    assert plan['characters'] == len(SPANISH)
    assert plan['estimated_usd'] == len(SPANISH) * 20 / 1_000_000
    assert engine.process(['master', 'source'], provider)['drafts'] == 3
    assert client.translate_text.call_count == 1
    assert all(r['status'] == 'Translated — Review' for r in engine.records())
    assert store.load(project) == before
    # New upload cells can reuse drafts; approval never propagates from cache.
    item = engine.records()[0]
    engine.approve(item, ENGLISH, 'Reviewer', True)
    with store.connect() as db:
        import json
        for item in engine.records()[1:]:
            updated = {**item, 'status': 'Failed', 'english': ''}
            db.execute('UPDATE translations SET payload=? WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                       (json.dumps(updated), project, item['dataset'], item['revision'], item['row_id'], item['field']))
    assert engine.plan(['master', 'source'], provider)['characters'] == 0
    engine.process(['master', 'source'], GoogleTranslationProvider(consent=True, client=client))
    assert client.translate_text.call_count == 1
    assert [r['status'] for r in engine.records()].count('Approved Translation') == 1


def test_adc_is_lazy_and_quota_project_explicit(monkeypatch):
    from google.cloud import translate_v3
    factory = Mock()
    factory.return_value.translate_text.return_value = response('Hello')
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    provider = GoogleTranslationProvider(consent=True)
    factory.assert_not_called()
    provider.prepare([('Bonjour', 'fr')])
    assert factory.call_args.kwargs['client_options'].quota_project_id == 'rta-translation'
    assert 'credentials' not in factory.call_args.kwargs


def test_google_ui_requires_confirmation(tmp_path, monkeypatch):
    from tests.test_review_workflow import app_for
    from tests.test_app import by_label, navigate
    from tests.translation_workspace_helpers import seed_google, select_visible, TRANSLATE_CONSENT
    case = make_workspace(tmp_path)
    engine = TranslationEngine(case[0], case[1])
    seed_google(engine, {'Banco de México': 'es', 'Bank of Mexico': 'en'}, {'master': ['Name'], 'source': ['Name']})
    client = Mock()
    client.translate_text.return_value = response('Bank of Mexico')
    monkeypatch.setattr('rta.translation_ui.GoogleTranslationProvider',
                        lambda **kwargs: GoogleTranslationProvider(client=client, **kwargs))
    app = app_for(case, monkeypatch)
    navigate(app, 'Translation Intelligence')
    select_visible(app)
    assert not app.exception
    assert any('Estimated cost' in c.value for c in app.markdown)
    by_label(app.button, 'Translate Selected').click().run()
    client.translate_text.assert_not_called()
    assert any('Authorize' in e.value for e in app.error)
    by_label(app.checkbox, TRANSLATE_CONSENT).check()
    by_label(app.button, 'Translate Selected').click().run()
    assert not app.exception and client.translate_text.call_count == 1
    assert engine.records()[0]['status'] == 'Translated — Review'
