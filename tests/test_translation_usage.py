"""Persistent accounting tests. All Google requests use injected mocks."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import sqlite3

import pytest
from google.api_core.exceptions import ServiceUnavailable, PermissionDenied, TooManyRequests, DeadlineExceeded

from rta.storage import Store
from rta.translation import TranslationEngine
from rta.translation_providers import GoogleTranslationProvider
from rta.translation_usage import GoogleTranslationUsage, DEFAULT_ALLOWANCE
from tests.test_translation import make_workspace, SPANISH, ENGLISH, Offline
from tests.test_google_translation import response


@pytest.fixture
def ledger(tmp_path):
    store = Store(tmp_path / 'usage.sqlite3')
    project, _ = store.create()
    clock = Mock(return_value=datetime(2026, 10, 21, 12, tzinfo=timezone.utc))
    return GoogleTranslationUsage(store, project, clock=clock)


def test_persistent_counts_costs_configuration_and_workspace_isolation(ledger):
    usage = ledger
    assert usage.summary()['allowance'] == DEFAULT_ALLOWANCE
    assert usage.summary()['progress'] == 0
    confirmed = usage.start_request(400_000)
    usage.confirm_request(confirmed)
    usage.start_request(200_000)
    report = usage.summary()
    assert report['confirmed_characters'] == 400_000
    assert report['uncertain_characters'] == 200_000
    assert report['total_characters'] == 600_000
    assert report['remaining_characters'] == 0
    assert report['requests'] == 2
    assert report['estimated_before_credits'] == 12
    assert report['estimated_after_credits'] == 2
    assert report['progress'] == 1
    assert report['warning']
    usage.set_allowance(700_000)
    reopened = GoogleTranslationUsage(Store(usage.store.path), usage.project, clock=usage.clock)
    assert reopened.summary()['remaining_characters'] == 100_000
    assert reopened.summary()['estimated_after_credits'] == 0
    assert reopened.history() == usage.history()
    other_project, _ = usage.store.create()
    other = GoogleTranslationUsage(usage.store, other_project, clock=usage.clock)
    assert other.summary()['requests'] == 0
    assert other.allowance() == DEFAULT_ALLOWANCE
    other.confirm_request(confirmed)
    assert other.history() == []
    assert usage.summary()['confirmed_characters'] == 400_000


def test_month_boundary_uses_toronto_calendar_and_preserves_history(ledger):
    usage = ledger
    # November 1 UTC is still October in Toronto until 04:00 UTC.
    usage.clock.return_value = datetime(2026, 11, 1, 3, 59, tzinfo=timezone.utc)
    request_id = usage.start_request(16)
    usage.clock.return_value = datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc)
    usage.confirm_request(request_id)  # response in new month belongs to dispatch month
    assert usage.summary()['month'] == '2026-11'
    assert usage.summary()['requests'] == 0
    assert usage.summary()['remaining_characters'] == DEFAULT_ALLOWANCE
    assert usage.summary('2026-10')['confirmed_characters'] == 16
    usage.start_request(20)
    assert [r['Month'] for r in usage.history()] == ['2026-11', '2026-10']
    usage.clock.return_value = datetime(2027, 1, 1, 5, tzinfo=timezone.utc)
    assert usage.summary()['month'] == '2027-01'
    assert usage.summary()['requests'] == 0
    assert len(usage.history()) == 2


@pytest.mark.parametrize('value', [-1, 2.5, True, '100'])
def test_invalid_allowance(ledger, value):
    with pytest.raises(ValueError):
        ledger.set_allowance(value)


def test_zero_allowance_threshold_and_batch_estimates(ledger):
    ledger.set_allowance(0)
    assert ledger.summary()['progress'] == 0
    ledger.start_request(10)
    assert ledger.summary()['progress'] == 1
    assert ledger.summary()['warning']
    assert ledger.summary()['estimated_after_credits'] == 0.0002
    ledger.set_allowance(1000)
    ledger.start_request(790)
    assert ledger.summary()['warning']
    costs = ledger.estimate_batch(300)
    assert costs['before_credits'] == pytest.approx(0.006)
    assert costs['after_credits'] == pytest.approx(0.002)
    assert costs['retry_before_credits'] == pytest.approx(0.018)
    assert costs['retry_after_credits'] == pytest.approx(0.014)


def test_default_warning_at_400000(ledger):
    ledger.start_request(399999)
    assert not ledger.summary()['warning']
    ledger.start_request(1)
    assert ledger.summary()['warning']
    assert ledger.summary()['progress'] == 0.8


def test_request_recorded_before_dispatch_and_no_text_stored(ledger):
    client = Mock()
    text = 'Bonjour 🌍 e\u0301'
    def translate(**kwargs):
        report = ledger.summary()
        assert report['requests'] == 1
        assert report['uncertain_characters'] == len(text)
        assert report['confirmed_characters'] == 0
        assert kwargs['retry'] is None
        return response('Hello world')
    client.translate_text.side_effect = translate
    provider = GoogleTranslationProvider(consent=True, client=client, usage=ledger)
    provider.prepare([(text, 'fr'), (text, 'fr')])
    assert ledger.summary()['confirmed_characters'] == len(text)
    assert ledger.summary()['uncertain_characters'] == 0
    assert provider.translate(text, 'fr') == 'Hello world'
    with ledger.store.connect() as db:
        rows = db.execute('SELECT * FROM google_translation_usage').fetchall()
    assert text not in repr(rows)
    assert 'Hello world' not in repr(rows)


@pytest.mark.parametrize('error,requests', [(DeadlineExceeded, 1), (PermissionDenied, 1),
                                           (ServiceUnavailable, 3), (TooManyRequests, 3)])
def test_failed_attempts_conservatively_count_uncertain_usage(ledger, error, requests):
    client = Mock()
    client.translate_text.side_effect = error('private text or secret token')
    provider = GoogleTranslationProvider(consent=True, client=client, sleep=Mock(), usage=ledger)
    provider.prepare([('Bonjour', 'fr')])
    assert client.translate_text.call_count == requests
    assert ledger.summary()['requests'] == requests
    assert ledger.summary()['confirmed_characters'] == 0
    assert ledger.summary()['uncertain_characters'] == requests * len('Bonjour')
    with pytest.raises(ValueError) as exception:
        provider.translate('Bonjour', 'fr')
    assert 'private' not in str(exception.value)


def test_retry_success_and_malformed_success_still_count(ledger):
    client = Mock()
    client.translate_text.side_effect = [ServiceUnavailable('private'), response('Hello')]
    provider = GoogleTranslationProvider(consent=True, client=client, sleep=Mock(), usage=ledger)
    provider.prepare([('Bonjour', 'fr')])
    assert ledger.summary()['confirmed_characters'] == 7
    assert ledger.summary()['uncertain_characters'] == 7
    assert ledger.summary()['requests'] == 2
    client.translate_text.side_effect = None
    client.translate_text.return_value = SimpleNamespace(translations=[])
    provider.prepare([('Bonjour', 'fr')])
    assert ledger.summary()['confirmed_characters'] == 14
    with pytest.raises(ValueError):
        provider.translate('Bonjour', 'fr')


def test_no_usage_for_no_consent_empty_or_rejected_values(ledger):
    client = Mock()
    provider = GoogleTranslationProvider(client=client, usage=ledger)
    with pytest.raises(ValueError):
        provider.prepare([('Bonjour', 'fr')])
    provider.consent = True
    provider.prepare([])
    provider.prepare([('English', 'en'), ('x' * 30001, 'fr'), ('', 'es')])
    client.translate_text.assert_not_called()
    assert ledger.summary()['requests'] == 0


def test_bookkeeping_failure_prevents_dispatch_or_further_calls(ledger, monkeypatch):
    client = Mock()
    client.translate_text.return_value = response('Hello')
    provider = GoogleTranslationProvider(consent=True, client=client, usage=ledger)
    with monkeypatch.context() as patch:
        patch.setattr(ledger, 'start_request', Mock(side_effect=sqlite3.OperationalError('private')))
        with pytest.raises(ValueError, match='Cannot record'):
            provider.prepare([('Bonjour', 'fr')])
    client.translate_text.assert_not_called()
    with monkeypatch.context() as patch:
        patch.setattr(ledger, 'confirm_request', Mock(side_effect=sqlite3.OperationalError('private')))
        with pytest.raises(ValueError, match='remains uncertain'):
            provider.prepare([('Bonjour', 'fr'), ('Hola', 'es')])
    assert client.translate_text.call_count == 1
    assert ledger.summary()['requests'] == 1
    assert ledger.summary()['uncertain_characters'] == len('Hola')


def test_engine_binds_workspace_and_cache_hits_do_not_add_usage(tmp_path):
    row = {'Name': 'Example Corporation', 'Segment': 'SMB', 'Description': SPANISH}
    store, project, _ = make_workspace(tmp_path, master=[row, row], source=[row])
    engine = TranslationEngine(store, project)
    engine.detect({'master': ['Description'], 'source': []})
    client = Mock()
    client.translate_text.return_value = response(ENGLISH)
    provider = GoogleTranslationProvider(consent=True, client=client)
    before = store.load(project)
    engine.process(['master', 'source'], provider)
    usage = GoogleTranslationUsage(store, project)
    assert usage.summary()['requests'] == 1
    assert usage.summary()['confirmed_characters'] == len(SPANISH)
    assert all(item['status'] == 'Translated — Review' for item in engine.records())
    assert store.load(project) == before
    # A newly selected duplicate cell must use the persisted cache, without usage.
    engine.detect({'master': ['Description'], 'source': ['Description']})
    engine.process(['source'], GoogleTranslationProvider(consent=True, client=client))
    assert usage.summary()['requests'] == 1
    assert client.translate_text.call_count == 1
    source_record = next(r for r in engine.records() if r['dataset'] == 'source')
    assert source_record['cache_hit']
    assert source_record['status'] == 'Translated — Review'


def test_usage_still_counted_when_translation_rejected_by_identifier_policy(tmp_path):
    row = {'Name': 'Example Corporation', 'Segment': 'SMB', 'Description': SPANISH + ' 12345'}
    store, project, _ = make_workspace(tmp_path, master=[row], source=[row])
    engine = TranslationEngine(store, project)
    engine.detect({'master': ['Description'], 'source': ['Description']})
    client = Mock()
    client.translate_text.return_value = response('An English draft missing the identifier')
    report = engine.process(['master', 'source'], GoogleTranslationProvider(consent=True, client=client))
    assert report['failed'] == 2
    usage = GoogleTranslationUsage(store, project).summary()
    assert usage['confirmed_characters'] == len(row['Description'])
    assert usage['requests'] == 1


def test_tracker_retained_without_visible_accounting_panels(tmp_path, monkeypatch):
    from tests.test_review_workflow import app_for
    from tests.test_app import by_label, navigate
    from tests.translation_workspace_helpers import seed_google, select_visible, TRANSLATE_CONSENT
    from rta.translation import TranslationEngine
    case = make_workspace(tmp_path)
    usage = GoogleTranslationUsage(case[0], case[1])
    usage.confirm_request(usage.start_request(400000))
    usage.start_request(100000)
    usage.set_allowance(0)
    assert usage.allowance() == 0 and len(usage.history()) == 1
    seed_google(TranslationEngine(case[0], case[1]), {'Banco de México': 'es', 'Bank of Mexico': 'en'},
                {'master': ['Name'], 'source': ['Name']})
    client = Mock(); client.translate_text.return_value = response('Bank of Mexico')
    monkeypatch.setattr('rta.translation_ui.GoogleTranslationProvider',
                        lambda **kwargs: GoogleTranslationProvider(client=client, **kwargs))
    app = app_for(case, monkeypatch); navigate(app, 'Translation Intelligence')
    assert not app.exception and not app.metric
    assert all(e.label == 'Save / resume workspace' for e in app.expander)
    assert usage.summary()['requests'] == 2
    assert usage.summary()['confirmed_characters'] == 400000
    assert usage.summary()['uncertain_characters'] == 100000
    select_visible(app)
    by_label(app.button, 'Translate Selected').click().run()
    client.translate_text.assert_not_called()
    assert usage.summary()['requests'] == 2
    by_label(app.checkbox, TRANSLATE_CONSENT).check()
    by_label(app.button, 'Translate Selected').click().run()
    assert not app.exception and client.translate_text.call_count == 1
    assert usage.summary()['requests'] == 3
