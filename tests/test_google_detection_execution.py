"""Dataset scope, full-size preview and consented execution; all APIs mocked."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.exceptions import DeadlineExceeded
from rta.google_detection import plan_detection, run_detection, cached_result
from rta.translation import translation_eligible, TranslationEngine
from rta.translation_usage import GoogleTranslationUsage
from tests.test_google_detection import google_case, detected
from tests.test_review_workflow import app_for
from tests.test_translation import Offline
from tests.test_app import by_label, navigate

SAVED = json.loads(Path('tests/fixtures/language_detection/google_live_25.json').read_text())
CONSENT = 'I authorize this detection batch and its estimated cost.'


def test_107243_selected_cells_scope_and_250_pending_limit(tmp_path):
    case, _ = google_case(tmp_path)
    store, project, _ = case
    items = [{'dataset': 'master', 'original': row['name'], 'field_kind': 'account_name', 'status': 'Uncertain'}
             for row in SAVED['results']]
    items += [{'dataset': 'source', 'original': f'Fictional Business Account {i % 500}',
               'field_kind': 'account_name', 'status': 'Uncertain'} for i in range(107218)]
    assert len(items) == 107243
    engine = SimpleNamespace(store=store, project=project, records=lambda: items)
    master = plan_detection(engine, ['master'])
    assert master['unique_texts'] == master['requests'] == 25
    assert master['characters'] == 427
    both = plan_detection(engine, ['master', 'source'])
    assert both['unique_texts'] == both['pending_texts'] == 525
    assert both['requests'] == both['batch_size'] == 250
    assert both['remaining_after_batch'] == 275
    source = plan_detection(engine, ['source'])
    assert source['unique_texts'] == 500 and source['batch_size'] == 250
    assert len(set(both['uncached'])) == 250


def test_ui_execution_persists_progress_candidates_and_next_batch(tmp_path, monkeypatch):
    master = [{'Name': r['name'], 'Segment': 'Enterprise'} for r in SAVED['results']]
    source = [{'Name': f'Servicios de Construcción Aurora {i}', 'Segment': 'Commercial'} for i in range(300)]
    source += deepcopy(master[:5])
    case, engine = google_case(tmp_path, master, source)
    engine.detect({'master': ['Name'], 'source': ['Name']})
    store, project, _ = case
    before_payload = deepcopy(store.load(project))
    monkeypatch.setattr('rta.translation_ui.ArgosProvider', Offline)
    from google.cloud import translate_v3
    client = Mock()
    raw = {r['name']: r['raw'] for r in SAVED['results']}
    seen = []
    def detect(**kwargs):
        assert kwargs['retry'] is None
        text = kwargs['request']['content']
        assert text not in seen
        # Previous response must be committed before the next request dispatch.
        if seen:
            assert cached_result(store, project, seen[-1])
        seen.append(text)
        result = raw.get(text, {'language_code': 'es', 'confidence': 0.99})
        return detected(result['language_code'], result['confidence'])
    client.detect_language.side_effect = detect
    factory = Mock(return_value=client)
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', factory)
    app = app_for(case, monkeypatch)
    navigate(app, 'Translation Intelligence')
    assert any('325 names' in c.value for c in app.caption)
    assert any('250 names' in m.value and 'Estimated cost' in m.value for m in app.markdown)
    by_label(app.button, 'Detect Languages').click().run()
    assert app.error
    factory.assert_not_called()
    # Form edits remain client-side until the submit button is pressed.
    by_label(app.checkbox, CONSENT).check()
    factory.assert_not_called()  # Checking consent alone is not submission.
    by_label(app.button, 'Detect Languages').click().run()
    assert not app.exception
    assert client.detect_language.call_count == 250, ([e.value for e in app.error], by_label(app.checkbox, CONSENT).value)
    assert any('Languages detected: 250' in s.value for s in app.success)
    assert not by_label(app.checkbox, CONSENT).value  # New batch must reconsent.
    records = TranslationEngine(store, project).records()
    assert sum(translation_eligible(r) for r in records) >= 225
    assert all(not r['english'] for r in records)
    assert all(r['detection_provider'] == 'google' for r in records)
    review = app.dataframe[0].value
    assert set(review['English Translation']) == {''}
    first = set(seen)
    pending = plan_detection(engine, ['master', 'source'])
    assert pending['cached_texts'] == 250 and pending['pending_texts'] == 75 and pending['batch_size'] == 75
    assert not first.intersection(pending['uncached'])
    by_label(app.checkbox, CONSENT).check()
    by_label(app.button, 'Detect Languages').click().run()
    assert not app.exception and client.detect_language.call_count == 325
    report = GoogleTranslationUsage(store, project).summary()['operations']['detection']
    assert report['requests'] == 325 and report['confirmed_characters'] == sum(map(len, seen))
    assert by_label(app.button, 'Detect Languages').disabled
    assert client.detect_language.call_count == 325  # Cached-only repeat, zero requests.
    client.translate_text.assert_not_called()
    assert store.load(project)['results'] == before_payload['results']
    assert store.load(project)['master'] == before_payload['master']
    assert not store.audit(project)


def test_failure_progress_reports_confirmed_and_uncertain_usage(tmp_path):
    case, engine = google_case(tmp_path, [{'Name': 'Les Jardins de Provence'}], [{'Name': 'Servicios de Construcción'}])
    engine.detect({'master': ['Name'], 'source': ['Name']})
    client = Mock()
    client.detect_language.side_effect = [detected('fr'), DeadlineExceeded('private error')]
    progress = Mock()
    report = run_detection(engine, ['master', 'source'], consent=True, client=client, progress=progress)
    assert report['successful'] == report['failed'] == 1
    assert report['requests'] == 2
    assert report['confirmed_characters'] == len('Les Jardins de Provence')
    assert report['uncertain_characters'] == len('Servicios de Construcción')
    assert progress.call_count == 2 and progress.call_args.args == (1.0,)
    assert '1 successfully; 1 failed' in progress.call_args.kwargs['text']
    assert cached_result(case[0], case[1], 'Les Jardins de Provence')
