from io import BytesIO
import json
from pathlib import Path

import polars as pl
import pytest
import streamlit as st
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from rta.models import Mapping, Result
from rta.research import Researcher, ResearchSettings
from rta.recommendations import INSUFFICIENT
from rta.review import decide
from rta.export import workbook
from rta.storage import Store
from tests.test_core import Transport, Response
from tests.test_app import by_label, navigate


URL = 'https://example.com/company'
CONTENT = 'Old Alpha is Alpha. Old Alpha is a subsidiary of Alpha. Old Alpha and Alpha share Enterprise customer segment.'
M = Mapping('Account', 'Company', 'Segment', 'Value')


def finding(**updates):
    result = {'source_row': 0, 'recommended_source_account': 'Alpha', 'parent_company': '',
        'proposed_value': 'Enterprise', 'relationship': 'Direct', 'confidence': 'High',
        'recommendation_status': 'Proposed', 'explanation': 'Identity is established by the company evidence.',
        'reasoning': 'The verified Source identity has the Enterprise segment.', 'evidence_urls': [URL],
        'supporting_quote': 'Old Alpha is Alpha.', 'identity_supported': True,
        'inheritance_supported': False, 'inheritance_quote': ''}
    result.update(updates)
    return result


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / 'recommendations.sqlite3')
    project, token = store.create()
    source = pl.DataFrame({'Company': ['Alpha', 'Beta', 'Gamma'], 'Value': ['Enterprise', 'SMB', 'Public Sector']})
    candidates = [{'source_row': i, 'account': name, 'value': value, 'similarity': score}
                  for i, (name, value, score) in enumerate(zip(source['Company'], source['Value'], [71, 55, 40]))]
    record = Result(0, 'Old Alpha', 'Verify', candidates=candidates)
    return store, project, token, source, record


def research(setup, output=None):
    store, project, _, source, record = setup
    transport = Transport([Response({'results': [{'url': URL, 'content': CONTENT}]}),
        Response({'choices': [{'message': {'content': json.dumps(output if output is not None else finding())}}]})])
    researcher = Researcher(store, project, 'test-tavily', 'test-openai', ResearchSettings(interval=0), transport, lambda _: None)
    researcher.investigate(record, source, M, 'source-context')
    return researcher, transport


@pytest.mark.parametrize('relationship', ['Direct', 'Renamed', 'Fuzzy'])
def test_supported_identity_recommends_source_value(setup, relationship):
    research(setup, finding(relationship=relationship))
    r = setup[-1]
    assert r.ai_proposed == r.proposed == 'Enterprise' and r.final == ''
    assert r.recommended_source_account == 'Alpha'
    assert r.research_status == 'Completed' and r.recommendation_status == 'Proposed'
    assert r.ai_confidence == 'High' and r.researched_at and r.evidence == [URL]


def test_parent_inheritance_requires_explicit_value_support(setup):
    research(setup, finding(relationship='Subsidiary', parent_company='Alpha', identity_supported=False,
        inheritance_supported=True, inheritance_quote='Old Alpha and Alpha share Enterprise customer segment.'))
    r = setup[-1]
    assert r.proposed == 'Enterprise' and r.parent_company == 'Alpha'
    assert not r.final and 'verification' in r.notes.lower()


@pytest.mark.parametrize('updates', [
    {'relationship': 'Subsidiary', 'parent_company': 'Alpha'},
    {'relationship': 'Subsidiary', 'parent_company': 'Alpha', 'inheritance_supported': True, 'inheritance_quote': 'Invented Enterprise inheritance'},
    {'relationship': 'Subsidiary', 'parent_company': 'Unrelated parent', 'inheritance_supported': True, 'inheritance_quote': CONTENT},
    {'proposed_value': 'Invented Segment'}, {'recommended_source_account': 'Invented Source'},
    {'source_row': 999}, {'evidence_urls': ['https://invented.example']},
    {'supporting_quote': 'Invented evidence'}, {'identity_supported': False}, {'confidence': 'Low'},
    {'recommendation_status': 'Insufficient Evidence', 'proposed_value': '', 'source_row': None}])
def test_unsupported_mapping_is_insufficient(setup, updates):
    research(setup, finding(**updates))
    r = setup[-1]
    assert r.research_status == r.recommendation_status == 'Insufficient Evidence'
    assert r.proposed == r.ai_proposed == r.final == ''
    assert r.recommendation_reasoning and len(r.candidates) == 3
    assert INSUFFICIENT not in (r.proposed, r.final)


def test_prompt_includes_original_allowed_values_and_three_scores(setup):
    _, transport = research(setup)
    request = transport.calls[1][1]['json']
    context = json.loads(request['messages'][1]['content'])
    assert context['original_value'] == 'Verify'
    assert context['allowed_values'] == ['Enterprise', 'Public Sector', 'SMB']
    assert context['top_three_suggestions'] == setup[-1].candidates
    assert [c['similarity'] for c in context['top_three_suggestions']] == [71, 55, 40]
    assert request['response_format']['json_schema']['strict'] is True


def test_malformed_schema_is_technical_failure(setup):
    research(setup, {'source_row': '0', 'proposed_value': 'Enterprise'})
    r = setup[-1]
    assert r.research_status == 'Failed' and not r.proposed and not r.final


def test_cache_and_saved_evidence_revalidate_without_calls(setup):
    researcher, transport = research(setup)
    r = setup[-1]
    snapshot = r.research_snapshot
    r.research_status = 'Not researched'
    researcher.investigate(r, setup[3], M, 'source-context')
    assert r.research_cache_hit and r.proposed == 'Enterprise' and len(transport.calls) == 2
    researcher.evaluate_saved(r, setup[3], M, 'source-context', snapshot)
    assert r.proposed == 'Enterprise' and len(transport.calls) == 2
    changed = setup[3].with_columns(pl.lit('Different segment').alias('Value'))
    researcher.evaluate_saved(r, changed, M, 'source-context', snapshot)
    assert r.research_status == 'Insufficient Evidence' and not r.proposed and len(transport.calls) == 2


def test_legacy_saved_research_requires_no_paid_call(setup):
    store, project, _, source, r = setup
    r.research_status, r.explanation, r.evidence = 'Completed', 'Legacy ownership finding', [URL]
    researcher = Researcher(store, project, transport=Transport([]))
    researcher.evaluate_saved(r, source, M, 'source-context')
    assert not researcher.transport.calls and r.research_status == 'Insufficient Evidence'
    assert r.explanation == 'Legacy ownership finding' and r.evidence == [URL]


def test_fresh_research_bypasses_cache_only_when_explicit(setup):
    researcher, transport = research(setup)
    source, r = setup[3], setup[-1]
    original_snapshot = r.research_snapshot
    # Navigation/completed-record retry does not issue a second paid call.
    researcher.investigate(r, source, M, 'source-context')
    assert len(transport.calls) == 2
    fresh_transport = Transport([Response({'results': [{'url': URL, 'content': CONTENT}]}),
        Response({'choices': [{'message': {'content': json.dumps(finding(confidence='Medium'))}}]})])
    researcher.transport = fresh_transport
    researcher.investigate(r, source, M, 'source-context', fresh=True)
    assert len(fresh_transport.calls) == 2 and r.ai_confidence == 'Medium'
    assert r.research_history[-1]['snapshot'] == original_snapshot


@pytest.mark.parametrize('action,status,expected', [
    ('Approve', 'Approved — AI Recommendation', 'Enterprise'),
    ('Reject', 'Rejected — AI Recommendation', ''), ('Manual', 'Manually Verified', 'Custom verified')])
def test_review_ai_decisions_preserve_recommendation_and_export(setup, action, status, expected):
    researcher, transport = research(setup)
    store, project, _, source, r = setup
    store.save(project, {'source': source.to_dicts(), 'mapping': vars(M), 'results': [r.dict()]})
    store.review(project, 0, action, 'Reviewer', 'Evidence checked', manual_value='Custom verified')
    saved = Result(**store.load(project)['results'][0])
    assert saved.final == expected and saved.review_status == status
    assert saved.ai_proposed == 'Enterprise' and saved.explanation == r.explanation
    researcher.investigate(saved, source, M, 'source-context', fresh=True)
    researcher.evaluate_saved(saved, source, M, 'source-context')
    assert saved.final == expected and len(transport.calls) == 2
    sheet = load_workbook(BytesIO(workbook([saved], store.audit(project), [], source.height)))['Reconciliation Results']
    exported = dict(zip([c.value for c in sheet[1]], [c.value for c in sheet[2]]))
    assert exported['AI Proposed Value'] == 'Enterprise'
    assert (exported['Final Value'] or '') == expected and exported['Review Status'] == saved.status_label
    assert exported['Stored Review Status'] == status
    assert exported['Reviewer Decision'] == action
    assert store.audit(project)[0]['ai_proposed'] == 'Enterprise'


def test_source_conflicts_cannot_be_silently_selected(setup):
    store, project, token, source, r = setup
    conflicting = pl.concat([source, pl.DataFrame({'Company': ['Alpha'], 'Value': ['SMB']})])
    research((store, project, token, conflicting, r))
    assert r.research_status == 'Insufficient Evidence' and not r.proposed


def test_ai_recommendation_is_visible_and_approvable_in_ui(setup, monkeypatch):
    research(setup)
    store, project, token, source, r = setup
    store.save(project, {'source': source.to_dicts(), 'source_schema': dict.fromkeys(source.columns, 'String'),
        'master': [{'Account': 'Old Alpha', 'Segment': 'Verify'}],
        'master_schema': {'Account': 'String', 'Segment': 'String'}, 'mapping': vars(M),
        'results': [r.dict()], 'context': 'source-context'})
    monkeypatch.setenv('RTA_DB_PATH', store.path)
    monkeypatch.setattr(st, 'secrets', {})
    app = AppTest.from_file(Path('app.py').resolve(), default_timeout=30)
    app.session_state['project'], app.session_state['token'] = project, token
    app.run()
    navigate(app, 'AI Research')
    assert app.dataframe[0].value.iloc[0]['AI Proposed Value'] == 'Enterprise'
    by_label(app.button, 'Re-evaluate saved evidence (no API calls)').click().run()
    assert not app.exception
    navigate(app, 'Review & Approvals')
    assert any('Intelligence Proposed — Pending Approval' in x.value for x in app.info)
    assert by_label(app.metric, 'Intelligence Proposed Value').value == 'Enterprise'
    assert by_label(app.metric, 'Final value').value == '—'
    by_label(app.text_input, 'Reviewer name').set_value('UI Reviewer')
    by_label(app.checkbox, 'I have verified the evidence and the field value for this specific account.').check()
    by_label(app.button, 'Save review decision').click().run()
    assert not app.exception and by_label(app.metric, 'Final value').value == 'Enterprise'
    assert store.load(project)['results'][0]['review_status'] == 'Approved — AI Recommendation'
