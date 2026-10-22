"""Replay saved, authorized Google results offline; no provider calls."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from rta.google_detection import (CLASSIFICATION_POLICY, GOOGLE_POLICY, interpret,
                                  cached_result, raw_key, plan_detection)
from rta.language_detection import ENGLISH, FOREIGN, AMBIGUOUS
from rta.translation import TranslationEngine
from rta.translation_usage import GoogleTranslationUsage
from tests.test_google_detection import google_case

FIXTURE = Path(__file__).parent / 'fixtures/language_detection/google_live_25.json'
SAVED = json.loads(FIXTURE.read_text())


def compare():
    rows = [{**row, 'after': interpret(row['name'], 'account_name', raw=row['raw'])}
            for row in SAVED['results']]
    definitive = [r for r in rows if r['expected_language'] != 'ambiguous']
    foreign = [r for r in definitive if r['expected_language'] != 'en']
    positive = [r for r in definitive if r['after']['detection_outcome'] == FOREIGN]
    return rows, {'definitive_cases': len(definitive),
                  'correct_automatic_before': SAVED['metrics']['rta_correct_language_and_routing'],
                  'correct_automatic_after': sum(r['after']['language'] == r['expected_language'] for r in definitive),
                  'foreign_candidates_before': 11, 'foreign_candidates_after': len(positive),
                  'foreign_recall_before': 11 / len(foreign),
                  'foreign_recall_after': len(positive) / len(foreign),
                  'foreign_false_positives': sum(r['expected_language'] == 'en' for r in positive)}


def test_saved_live_before_after_no_network(monkeypatch):
    from google.cloud import translate_v3
    client = Mock(side_effect=AssertionError('No live API'))
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', client)
    rows, metrics = compare()
    assert metrics == {'definitive_cases': 23, 'correct_automatic_before': 16,
                       'correct_automatic_after': 23, 'foreign_candidates_before': 11,
                       'foreign_candidates_after': 16, 'foreign_recall_before': 0.6875,
                       'foreign_recall_after': 1.0, 'foreign_false_positives': 0}
    assert all(r['after']['detection_outcome'] != FOREIGN for r in rows[:6])
    assert all(r['after']['language_review_required'] and r['after']['detection_outcome'] == FOREIGN
               for r in rows if r['expected_language'] == 'ambiguous')
    assert all(r['after']['google_language'] == r['google_language'] and
               r['after']['google_confidence'] == r['google_confidence'] for r in rows)
    client.assert_not_called()


@pytest.mark.parametrize('text,code', [
    ('株式会社あおぞら', 'ja'), ('上海智能技术', 'zh-CN'), ('한국기술', 'ko'),
    ('شركة الأفق', 'ar'), ('भारत उद्योग', 'hi'), ('อรุณเทคโนโลยี', 'th'),
    ('Արեւ Տեխնոլոգիա', 'hy'), ('თბილისი ტექნოლოგია', 'ka'),
])
def test_high_confidence_scripts_not_dependent_on_spaces(text, code):
    original = text
    result = interpret(text, 'account_name', raw={'language_code': code, 'confidence': 0.99})
    assert result['detection_outcome'] == FOREIGN
    assert result['language'] == code.split('-')[0]
    assert text == original


@pytest.mark.parametrize('text,code', [('北京科技', 'en'), ('شركة النور', 'ja'),
                                     ('東京商事 Labs', 'ja'), ('Hello 世界', 'en')])
def test_google_language_not_overridden_by_mixed_script_rules(text, code):
    result = interpret(text, 'account_name', raw={'language_code': code, 'confidence': 0.99})
    assert result['language'] == code and result['status'] == ('Not Required' if code == 'en' else 'Translation Needed')


def test_old_raw_cache_reused_new_policy_human_state_preserved(tmp_path, monkeypatch):
    from google.cloud import translate_v3
    cloud = Mock(side_effect=AssertionError('Reclassification must not call Google'))
    monkeypatch.setattr(translate_v3, 'TranslationServiceClient', cloud)
    names = ['株式会社さくら商事', '北京科技有限公司', 'Deutsche Maschinenfabrik']
    case, engine = google_case(tmp_path, [{'Name': text} for text in names], [{'Name': names[0]}])
    store, project, _ = case
    engine.detect({'master': ['Name'], 'source': ['Name']})
    manual = engine.confirm_language(next(r for r in engine.records() if r['dataset'] == 'source'), 'ja', 'Language reviewer', True)
    approved = engine.approve(next(r for r in engine.records() if r['dataset'] == 'master' and r['row_id'] == 1),
                              'Human approved name', 'Translator', True, 'zh')
    before_payload = deepcopy(store.load(project))
    before_audit = store.audit(project)
    usage = GoogleTranslationUsage(store, project).summary()
    with store.connect() as db:
        for row in SAVED['results']:
            if row['name'] in names:
                assert row['raw']['policy'] == GOOGLE_POLICY
                db.execute('INSERT OR REPLACE INTO language_detection_cache VALUES (?,?,?)',
                           (project, raw_key(row['name']), json.dumps(row['raw'])))
        for item in engine.records():
            item['detection_policy'] = 'old-classification-signature'
            db.execute('UPDATE translations SET payload=? WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                       (json.dumps(item), project, item['dataset'], item['revision'], item['row_id'], item['field']))
    # records() automatically refreshes old policy, using raw responses, not HTTP.
    engine = TranslationEngine(store, project)
    records = engine.records()
    for item in records:
        assert item['detection_version'] == CLASSIFICATION_POLICY
        assert item['automatic_detection_outcome'] == FOREIGN
        assert cached_result(store, project, item['original'])
    corrected = next(r for r in records if r['dataset'] == 'source')
    translated = next(r for r in records if r['dataset'] == 'master' and r['row_id'] == 1)
    assert corrected['language'] == manual['language'] and corrected['language_confirmed']
    assert translated['english'] == approved['english'] and translated['status'] == 'Approved Translation'
    assert store.audit(project) == before_audit
    assert store.load(project)['results'] == before_payload['results']
    assert store.load(project)['master'] == before_payload['master']
    assert plan_detection(engine, ['master', 'source'])['requests'] == 0
    assert GoogleTranslationUsage(store, project).summary() == usage
    cloud.assert_not_called()
