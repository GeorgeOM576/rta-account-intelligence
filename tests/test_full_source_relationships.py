"""All Orchard/Clinisys statements here are synthetic fixtures, not real-world assertions."""
from io import BytesIO
import json
from pathlib import Path
import polars as pl
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from openpyxl import load_workbook

from rta.models import Mapping, Result
from rta.research import Researcher, ResearchSettings
from rta.relationships import POLICIES
from rta.storage import Store
from rta.export import workbook
from tests.test_core import Transport, Response
from tests.test_app import by_label, navigate

URL = 'https://example.com/synthetic-corporate-evidence'
MAPPING = Mapping('Account', 'Company', 'Segment', 'Value')


def fact(relationship='Acquired', quote='Clinisys acquired Orchard Systems.', **changes):
    value = {'subject': 'Orchard Systems', 'entity': 'Clinisys', 'relationship': relationship,
             'verified_names': [], 'quote': quote, 'evidence_urls': [URL],
             'inheritance_quote': '', 'confidence': 'High'}
    value.update(changes)
    return value


@pytest.fixture
def case(tmp_path):
    # Place the true related company after the old 25-record cutoff and every other row.
    names = ['Orchard Group', 'Orchard Services', 'Orchard Solutions'] + [f'Fixture Company {i}' for i in range(52996)] + ['Clinisys']
    source = pl.DataFrame({'Company': names, 'Value': ['Enterprise'] * (len(names)-1) + ['Healthcare']})
    r = Result(0, 'Orchard Systems', 'Unmapped', candidates=[
        {'source_row': i, 'account': names[i], 'value': 'Enterprise', 'similarity': score}
        for i, score in enumerate([99, 90, 85])])
    store = Store(tmp_path / 'full-source.sqlite3')
    project, token = store.create()
    return store, project, token, source, r


def run_research(case, facts, extra='', settings=None):
    store, project, _, source, r = case
    texts = [f['quote'] for f in facts] + [f['inheritance_quote'] for f in facts]
    texts += [a['quote'] for f in facts for a in f['verified_names']]
    content = ' '.join(texts + [extra])
    payload = {'verified_facts': facts, 'explanation': 'Synthetic cited relationship evidence.'}
    transport = Transport([Response({'results': [{'url': URL, 'content': content}]}),
                           Response({'choices': [{'message': {'content': json.dumps(payload)}}]})])
    researcher = Researcher(store, project, 'test-tavily', 'test-openai',
                            settings or ResearchSettings(interval=0), transport, lambda _: None)
    researcher.investigate(r, source, MAPPING, 'full-source-context')
    return researcher, transport


@pytest.mark.parametrize('kind,quote', [
    ('Parent', 'Orchard Systems is a subsidiary of Clinisys.'),
    ('Acquired', 'Clinisys acquired Orchard Systems.'),
    ('Merged', 'Orchard Systems merged with Clinisys.'),
    ('Subsidiary', 'Clinisys is a subsidiary of Orchard Systems.')])
def test_full_source_related_entity_mapping(case, kind, quote):
    r = case[-1]
    run_research(case, [fact(kind, quote, inheritance_quote='Orchard Systems and Clinisys share the Healthcare segment.')])
    assert r.research_status == 'Completed' and r.ai_proposed == 'Healthcare' and not r.final
    assert r.recommended_source_account == 'Clinisys' and r.relationship == kind
    assert r.suggested_matches[0]['source_row'] == 52999
    assert r.verified_facts[0]['entity'] == 'Clinisys'
    assert r.candidates[0]['account'] == 'Orchard Group'  # suggestions remain separate from facts


@pytest.mark.parametrize('kind,quote', [('Renamed', 'Orchard Systems was renamed Clinisys.'),
                                      ('Alias', 'Orchard Systems operates as Clinisys.')])
def test_renamed_or_alias_company_lookup_across_entire_source(case, kind, quote):
    run_research(case, [fact(kind, quote)])
    assert case[-1].ai_proposed == 'Healthcare' and case[-1].recommended_source_account == 'Clinisys'


def test_verified_alternate_name_is_looked_up_in_full_source(case):
    store, project, token, source, r = case
    source = source.with_columns(pl.when(pl.col('Company') == 'Clinisys').then(pl.lit('Clinisys Limited'))
                                 .otherwise(pl.col('Company')).alias('Company'))
    f = fact(inheritance_quote='Orchard Systems and Clinisys share the Healthcare segment.',
             verified_names=[{'name': 'Clinisys Limited', 'quote': 'Clinisys is also known as Clinisys Limited.', 'url': URL}])
    run_research((store, project, token, source, r), [f])
    assert r.recommended_source_account == 'Clinisys Limited' and r.ai_proposed == 'Healthcare'


@pytest.mark.parametrize('kind,quote', [('Acquired', 'Clinisys acquired Orchard Systems.'),
                                      ('Parent', 'Orchard Systems is a subsidiary of Clinisys.')])
def test_relationship_without_segment_inheritance_is_insufficient(case, kind, quote):
    run_research(case, [fact(kind, quote)])
    r = case[-1]
    assert r.ai_proposed == r.proposed == r.final == ''
    assert r.recommendation_status == 'Insufficient Evidence'
    assert r.suggested_matches[0]['account'] == 'Clinisys' and r.suggested_matches[0]['value'] == 'Healthcare'
    assert 'inheritance evidence is missing' in r.recommendation_reasoning
    assert len(r.verified_facts) == 1


@pytest.mark.parametrize('kind,quote', [
    ('Direct', 'Orchard Systems has a similar name to Orchard Group.'),
    ('Direct', 'Orchard Systems is independent of Orchard Group.'),
    ('Parent', 'Orchard Systems has a similar name to Orchard Group.'),
    ('Acquired', 'Orchard Group has not acquired Orchard Systems.')])
def test_unrelated_or_negated_similar_name_is_never_a_fact(case, kind, quote):
    run_research(case, [fact(kind, quote, entity='Orchard Group')])
    r = case[-1]
    assert not r.ai_proposed and not r.verified_facts and not r.final
    assert r.recommendation_status == 'Insufficient Evidence'


def test_organization_rules_and_cache_reevaluation_no_paid_calls(case):
    researcher, transport = run_research(case, [fact(inheritance_quote='Orchard Systems and Clinisys share the Healthcare segment.')])
    r = case[-1]
    assert r.ai_proposed == 'Healthcare'
    researcher.settings.relationship_policy = POLICIES[1]
    researcher.evaluate_saved(r, case[3], MAPPING, 'full-source-context')
    assert not r.ai_proposed and 'same-entity' in r.recommendation_reasoning
    researcher.settings.relationship_policy = POLICIES[0]
    researcher.evaluate_saved(r, case[3], MAPPING, 'full-source-context')
    assert r.ai_proposed == 'Healthcare' and len(transport.calls) == 2


def test_missing_related_entity_does_not_fall_back_to_orchard_group(case):
    store, project, token, source, r = case
    without_clinisys = source.filter(pl.col('Company') != 'Clinisys')
    run_research((store, project, token, without_clinisys, r), [fact()])
    assert not r.ai_proposed and 'not found in the Source' in r.recommendation_reasoning


def test_legacy_cached_parent_can_be_recovered_without_paid_calls(case):
    store, project, _, source, r = case
    quote = 'Clinisys acquired Orchard Systems.'
    inheritance = 'Orchard Systems and Clinisys share the Healthcare segment.'
    r.research_snapshot = {'source_context': 'full-source-context', 'timestamp': '2026-10-20T00:00:00+00:00',
        'source_candidates': list(r.candidates), 'retrieved_evidence': [{'url': URL, 'content': quote + ' ' + inheritance}],
        'finding': {'parent_company': 'Clinisys', 'recommended_source_account': 'Orchard Group',
            'relationship': 'Acquired', 'confidence': 'High', 'explanation': 'Named acquirer outside local suggestions.',
            'inheritance_supported': True, 'inheritance_quote': inheritance}}
    researcher = Researcher(store, project, transport=Transport([]))
    researcher.evaluate_saved(r, source, MAPPING, 'full-source-context')
    assert not researcher.transport.calls and r.ai_proposed == 'Healthcare'
    assert r.recommended_source_account == 'Clinisys'


def test_end_to_end_corporate_approval_reload_export_and_ui(case, monkeypatch):
    researcher, transport = run_research(case, [fact(inheritance_quote='Orchard Systems and Clinisys share the Healthcare segment.')])
    store, project, token, source, r = case
    payload = {'source': source.to_dicts(), 'source_schema': dict.fromkeys(source.columns, 'String'),
        'master': [{'Account': 'Orchard Systems', 'Segment': 'Unmapped'}],
        'master_schema': {'Account': 'String', 'Segment': 'String'}, 'mapping': vars(MAPPING),
        'results': [r.dict()], 'context': 'full-source-context'}
    store.save(project, payload)
    monkeypatch.setenv('RTA_DB_PATH', store.path)
    monkeypatch.setattr(st, 'secrets', {})
    app = AppTest.from_file(Path('app.py').resolve(), default_timeout=30)
    app.session_state['project'], app.session_state['token'] = project, token
    app.run()
    for page in ('AI Research', 'Review & Approvals'):
        navigate(app, page)
        for title in ('Verified Facts', 'Suggested Matches', 'Recommendation Decision'):
            assert any(title in m.value for m in app.markdown)
        assert not any('**Proposed Segment**' in m.value for m in app.markdown)
        assert by_label(app.metric, 'Intelligence Proposed Value').value == 'Healthcare'
    by_label(app.text_input, 'Reviewer name').set_value('Corporate Reviewer')
    by_label(app.checkbox, 'I have verified the evidence and the field value for this specific account.').check()
    by_label(app.button, 'Save review decision').click().run()
    assert not app.exception and by_label(app.metric, 'Final value').value == 'Healthcare'
    reopened = Store(store.path)
    saved = Result(**reopened.load(project)['results'][0])
    assert saved.review_status == 'Approved — AI Recommendation'
    researcher.evaluate_saved(saved, source, MAPPING, 'full-source-context')
    assert saved.final == 'Healthcare' and len(transport.calls) == 2
    book = load_workbook(BytesIO(workbook([saved], reopened.audit(project), [], source.height)))
    sheet = book['Reconciliation Results']
    exported = dict(zip([c.value for c in sheet[1]], [c.value for c in sheet[2]]))
    assert exported['AI Recommended Source Account'] == 'Clinisys'
    assert exported['Final Value'] == exported['AI Proposed Value'] == 'Healthcare'
    assert json.loads(exported['Verified Facts'])[0]['entity'] == 'Clinisys'
    assert exported['Reviewer Decision'] == 'Approve'
    assert reopened.audit(project)[0]['mapping_policy'] == POLICIES[0]
