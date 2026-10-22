"""Legacy 13-row export -> pending -> cached Google refresh through real UI."""
from copy import deepcopy
import csv
from io import StringIO
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from rta.google_detection import raw_key, interpret
from rta.translation import TranslationEngine
from rta.translation_usage import GoogleTranslationUsage
from rta.translation_runtime import stale_translation_modules
from tests.test_translation import make_workspace, Offline
from tests.test_review_workflow import app_for
from tests.test_app import by_label, navigate

SAVED = json.loads(Path('tests/fixtures/language_detection/google_live_25.json').read_text())


def test_legacy_thirteen_flagged_records_refresh_csv_and_persist(tmp_path, monkeypatch):
    names = [r['name'] for r in SAVED['results'][:6]]
    master = [{'Name': name, 'Customer Segment': 'Enterprise'} for name in names]
    source = deepcopy(master) + [{'Name': 'Global Tech Solutions', 'Customer Segment': 'Commercial'}]
    case = make_workspace(tmp_path, master, source)
    store, project, _ = case
    engine = TranslationEngine(store, project)
    engine.detect({'master': ['Name'], 'source': ['Customer Segment']})
    languages = dict(zip(names, ['vi', 'ca', 'en', 'nl', 'de', 'de']))
    with store.connect() as db:
        for item in engine.records():
            item.update(language=languages.get(item['original'], 'und'), status='Uncertain',
                        detected_language=languages.get(item['original'], 'und'),
                        translation_excluded=False, detection_policy='legacy-unversioned')
            db.execute('UPDATE translations SET payload=? WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                       (json.dumps(item), project, item['dataset'], item['revision'], item['row_id'], item['field']))
        historical = {**item, 'revision': 'previous-upload', 'language': 'vi', 'status': 'Uncertain'}
        db.execute('INSERT INTO translations VALUES (?,?,?,?,?,?)',
                   (project, historical['dataset'], historical['revision'], historical['row_id'], historical['field'], json.dumps(historical)))
    payload = store.load(project)
    payload.pop('language_detection_provider')
    store.save(project, payload)
    stale_session = deepcopy(payload)
    from google.cloud import translate_v3
    cloud = Mock(side_effect=AssertionError('Never make live Google requests'))
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', cloud)
    monkeypatch.setattr('rta.translation_ui.ArgosProvider', Offline)
    from rta.export import translation_csv
    app = app_for(case, monkeypatch)
    app.session_state['payload'] = stale_session
    navigate(app, 'Translation Intelligence')
    assert not app.exception
    assert set(app.dataframe[0].value['Detected Language']) == {'und'}
    assert len(app.dataframe[0].value) == 13
    assert set(app.dataframe[0].value['Original Company Name']) == set(names + ['Global Tech Solutions'])
    by_label(app.button, 'Detect Languages').click().run()
    assert app.error
    cloud.assert_not_called()
    assert store.load(project)['translation_fields']['source'] == ['Customer Segment', 'Name']
    # Preserve a manual language decision and an approved translation while
    # applying different automatic Google metadata from the cache.
    engine = TranslationEngine(store, project)
    manual = engine.confirm_language(next(r for r in engine.records() if r['dataset'] == 'master' and r['row_id'] == 0), 'fr', 'Language reviewer', True)
    approved = engine.approve(next(r for r in engine.records() if r['dataset'] == 'master' and r['row_id'] == 1),
                              'Human reviewed name', 'Translator', True, 'fr')
    before_audit = store.audit(project)
    with store.connect() as db:
        for row in SAVED['results']:
            if row['name'] in names + ['Global Tech Solutions']:
                db.execute('INSERT OR REPLACE INTO language_detection_cache VALUES (?,?,?)',
                           (project, raw_key(row['name']), json.dumps(row['raw'])))
    # A stale browser payload must not override SQLite or preserve old CSV bytes.
    app.session_state['payload'] = stale_session
    app.run()
    assert not app.exception
    rows = list(csv.DictReader(StringIO(translation_csv(engine.export_records()).decode('utf-8-sig'))))
    assert len(rows) == 13 and all(r['Google Detected Language'] == 'en' for r in rows)
    expected = {r['name']: interpret(r['name'], 'account_name', raw=r['raw'])['language'] for r in SAVED['results']}
    assert all(r['Detected Language'] == expected[r['Original text']] and r['Detection Provider'] == 'google' for r in rows)
    assert all(r['Record Scope'] == 'Current selected enabled field' and r['Field'] == 'Name' for r in rows)
    assert all(r['Translation Provider'] == (approved['provider'] if r['Dataset'] == 'Master' and r['Row'] == '2' else '')
               for r in rows)  # Detection never invents a translation provider.
    assert store.audit(project) == before_audit
    records = engine.records()
    assert next(r for r in records if r['dataset'] == 'master' and r['row_id'] == 0)['language'] == manual['language']
    assert next(r for r in records if r['dataset'] == 'master' and r['row_id'] == 1)['english'] == approved['english']
    assert engine.detection_inventory(records)['historical_revision'] == 1
    assert engine.detection_inventory(records)['excluded_selected'] == 7
    with store.connect() as db:
        assert json.loads(db.execute('SELECT payload FROM translations WHERE project=? AND revision=?',
                                    (project, 'previous-upload')).fetchone()[0]) == historical
    navigate(app, 'Dashboard')
    navigate(app, 'Translation Intelligence')
    assert list(csv.DictReader(StringIO(translation_csv(engine.export_records()).decode('utf-8-sig')))) == rows
    assert not store.load(project)['results']
    assert GoogleTranslationUsage(store, project).summary()['requests'] == 0
    cloud.assert_not_called()


def test_old_widgets_cannot_restore_external_provider_or_field_selection(tmp_path, monkeypatch):
    case = make_workspace(tmp_path)
    store, project, _ = case
    engine = TranslationEngine(store, project)
    engine.detect({'master': ['Name'], 'source': ['Segment']})
    monkeypatch.setattr('rta.translation_ui.ArgosProvider', Offline)
    from google.cloud import translate_v3
    cloud = Mock(side_effect=AssertionError('No API calls for external settings refresh'))
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', cloud)
    app = app_for(case, monkeypatch)
    navigate(app, 'Translation Intelligence')
    assert set(app.dataframe[0].value['Dataset']) == {'Master', 'Source'}
    assert store.load(project)['language_detection_provider'] == 'google'
    engine.select_detection_provider('google')
    engine.detect({'master': ['Name'], 'source': ['Name']})
    app.run()
    assert not app.exception
    assert set(app.dataframe[0].value['Dataset']) == {'Master', 'Source'}
    assert not any(r.label == 'Language detection provider' for r in app.radio)
    assert store.load(project)['translation_fields']['source'] == ['Name']
    assert store.load(project)['language_detection_provider'] == 'google'
    cloud.assert_not_called()


@pytest.mark.parametrize('module_name', ['translation', 'translation_ui', 'export', 'google_detection', 'google_languages', 'translation_providers', 'translation_diagnostics'])
def test_old_cached_module_blocks_export_until_restart(module_name, tmp_path, monkeypatch):
    import importlib
    module = importlib.import_module('rta.' + module_name)
    attribute = 'GOOGLE_BUILD' if module_name == 'google_detection' else 'LOADED_BUILD'
    monkeypatch.delattr(module, attribute)
    assert str(Path(module.__file__).resolve()) in stale_translation_modules()
    monkeypatch.setenv('RTA_DB_PATH', str(tmp_path / 'startup.sqlite3'))
    app = AppTest.from_file(Path('app.py').resolve()).run()
    assert not app.exception
    assert any('outdated Translation Intelligence modules' in e.value for e in app.error)
    assert not app.get('download_button')
