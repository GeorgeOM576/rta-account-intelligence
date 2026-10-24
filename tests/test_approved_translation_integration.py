"""Approved-name integration: no paid APIs, no translation/detection engine changes."""
from copy import deepcopy
from io import BytesIO
import json

import polars as pl
import pytest
from openpyxl import load_workbook

from rta.approved_names import ApprovedNames
from rta.export import result_row, workbook
from rta.models import Mapping, Result, INTELLIGENCE_PENDING, REVIEW_FILTERS
from rta.research import Researcher, ResearchSettings
from rta.review import final_value
from rta.storage import digest
from rta.translation import TranslationEngine
from rta.translation_matching import reconcile
from tests.test_core import Response, Transport
from tests.test_translation import make_workspace, MAPPING
from tests.test_app import navigate, by_label
from tests.test_review_workflow import app_for


def fixture(tmp_path, master, source):
    case = make_workspace(tmp_path, master, source)
    engine = TranslationEngine(case[0], case[1])
    engine.detect({'master': ['Name'], 'source': ['Name']})
    return case, engine


def approved(engine, dataset, english, row=0):
    entry = next(r for r in engine.records() if r['dataset'] == dataset and r['row_id'] == row)
    return engine.approve(entry, english, 'Name reviewer', True)


def match(case, engine):
    payload = case[0].load(case[1])
    return reconcile(pl.DataFrame(payload['master']), pl.DataFrame(payload['source']),
                     Mapping(**payload['mapping']), engine.records())[0]


@pytest.mark.parametrize('left,right,mt,st,basis', [
    ('The Gardens of Provence', 'The Gardens of Provence', '', '', 'Master Original ↔ Source Original'),
    ('Les Jardins de Provence', 'The Gardens of Provence', 'The Gardens of Provence', '', 'Master Translation ↔ Source Original'),
    ('The Gardens of Provence', 'Les Jardins de Provence', '', 'The Gardens of Provence', 'Master Original ↔ Source Translation'),
    ('Les Jardins de Provence', 'Jardines de Provenza', 'The Gardens of Provence', 'The Gardens of Provence', 'Master Translation ↔ Source Translation'),
])
def test_four_directions_display_and_export(tmp_path, left, right, mt, st, basis):
    case, engine = fixture(tmp_path, [{'Name': left, 'Segment': 'Verify'}], [{'Name': right, 'Segment': 'SMB'}])
    if mt:
        approved(engine, 'master', mt)
    if st:
        approved(engine, 'source', st)
    result = match(case, engine)[0]
    assert result.match_basis == basis and result.match_score == 100
    assert result.proposed == 'SMB' and result.status_label == INTELLIGENCE_PENDING
    assert final_value(result) == result.final == ''
    row = result_row(result)
    assert row['Original Account Name'] == row['Master Original Name'] == left
    assert row['Source Original Name'] == row['Matched Account Name'] == right
    assert row['Master Approved English Translation'] == mt
    assert row['Source Approved English Translation'] == st
    if mt or st:
        assert result.match_method == 'Exact — Approved Translation'
        assert result.identity_confidence != 'Reliable local match'
    payload = case[0].load(case[1])
    book = load_workbook(BytesIO(workbook([result], [], [], 1, engine.records(), payload)))
    sheet = book['Reconciliation Results']
    exported = dict(zip([c.value for c in sheet[1]], [c.value for c in sheet[2]]))
    assert exported['Match Basis'] == basis
    assert exported['Master Original Name'] == left
    assert exported['Master Approved English Translation'] == (mt or None)
    assert exported['Source Approved English Translation'] == (st or None)
    assert {'Research Recommendation', 'Research Evidence / Sources', 'Proposed Value', 'Final Value'} <= exported.keys()


@pytest.mark.parametrize('status', ['Translated — Review', 'Rejected Translation', 'Translation Needed', 'Uncertain'])
def test_nonapproved_context_never_reaches_matching_or_export(tmp_path, status):
    case, engine = fixture(tmp_path, [{'Name': 'Les Jardins de Provence', 'Segment': 'Verify'}],
                           [{'Name': 'The Gardens of Provence', 'Segment': 'SMB'}])
    records = engine.records()
    for r in records:
        if r['dataset'] == 'master':
            r.update(status=status, english='The Gardens of Provence')
    payload = case[0].load(case[1])
    r = reconcile(pl.DataFrame(payload['master']), pl.DataFrame(payload['source']), MAPPING, records)[0][0]
    assert not r.proposed
    assert not r.account_context['master']['approved_english']
    assert not result_row(r)['Approved English Translation']


def test_normalization_and_fuzzy_use_approved_variants(tmp_path):
    case, engine = fixture(tmp_path, [{'Name': 'Les Jardins de Provence', 'Segment': 'Verify'}],
                           [{'Name': 'THE GARDENS OF PROVENCE!', 'Segment': 'SMB'}])
    approved(engine, 'master', 'The Gardens of Provence')
    assert match(case, engine)[0].match_method == 'Normalized — Approved Translation'
    payload = case[0].load(case[1])
    payload['source'][0]['Name'] = 'The Garden of Provence'
    case[0].save(case[1], payload)
    r = match(case, engine)[0]
    assert r.match_method == 'Fuzzy — Approved Translation' and r.match_score > 80
    assert not r.proposed and not r.final
    assert r.candidates[0]['account'] == 'The Garden of Provence'


def test_generic_collisions_require_manual_review(tmp_path):
    case, engine = fixture(tmp_path,
        [{'Name': 'Compañía Nacional de Comercio', 'Segment': 'Verify'}],
        [{'Name': 'Société Nationale de Commerce', 'Segment': 'SMB'},
         {'Name': 'Nationale Handelsgesellschaft', 'Segment': 'Enterprise'}])
    approved(engine, 'master', 'National Trading Company')
    approved(engine, 'source', 'National Trading Company', 0)
    approved(engine, 'source', 'National Trading Company', 1)
    r = match(case, engine)[0]
    assert r.match_status == 'Duplicate conflict' and not r.proposed and not r.final
    assert len(r.candidates) == 2


def test_original_and_identifier_priority(tmp_path):
    case, engine = fixture(tmp_path,
        [{'Name': 'Les Jardins de Provence', 'Segment': 'Verify', 'Account ID': '0001'}],
        [{'Name': 'Different legal entity', 'Segment': 'Enterprise', 'Account ID': '0001'},
         {'Name': 'The Gardens of Provence', 'Segment': 'SMB', 'Account ID': '0002'}])
    approved(engine, 'master', 'The Gardens of Provence')
    payload = case[0].load(case[1])
    payload['mapping'] = vars(Mapping('Account ID', 'Account ID', 'Segment', 'Segment'))
    case[0].save(case[1], payload)
    r = match(case, engine)[0]
    assert r.match_status == 'Exact' and r.proposed == 'Enterprise'
    assert r.candidates[0]['source_row'] == 0
    assert r.account_context['master']['original_name'] == 'Les Jardins de Provence'
    # Account-name translations cannot override exact identifier evidence.
    payload['mapping'] = vars(MAPPING)
    payload['source'][0]['Name'] = 'Les Jardins de Provence'
    case[0].save(case[1], payload)
    r = match(case, engine)[0]
    assert r.match_status == 'Exact' and r.proposed == 'Enterprise'


def test_revision_and_original_validation_not_dataframe_position(tmp_path):
    case, engine = fixture(tmp_path, [{'Name': 'Les Jardins de Provence', 'Segment': 'Verify'}],
                           [{'Name': 'The Gardens of Provence', 'Segment': 'SMB'}])
    entry = approved(engine, 'master', 'The Gardens of Provence')
    payload = case[0].load(case[1])
    for stale in ({**entry, 'revision': 'older upload'}, {**entry, 'original': 'Another company'}):
        index = ApprovedNames(payload, MAPPING, [stale])
        assert not index.account('master', 0)['approved_english']
    changed = deepcopy(payload)
    changed['master'][0]['Name'] = 'Another company'
    assert not ApprovedNames(changed, MAPPING, [entry]).account('master', 0)['approved_english']


def test_workspace_isolation(tmp_path):
    case, engine = fixture(tmp_path, [{'Name': 'Les Jardins de Provence', 'Segment': 'Verify'}],
                           [{'Name': 'The Gardens of Provence', 'Segment': 'SMB'}])
    approved(engine, 'master', 'The Gardens of Provence')
    other, _ = case[0].create()
    payload = case[0].load(case[1]);payload['results'] = []
    case[0].save(other, payload)
    other_engine = TranslationEngine(case[0], other)
    assert not other_engine.records()
    assert not match((case[0], other, ''), other_engine)[0].account_context['master']['approved_english']


def test_approval_visible_immediately_in_real_reconciliation_page(tmp_path, monkeypatch):
    case, engine = fixture(tmp_path, [{'Name': 'Les Jardins de Provence', 'Segment': 'Verify'}],
                           [{'Name': 'The Gardens of Provence', 'Segment': 'SMB'}])
    app = app_for(case, monkeypatch)
    navigate(app, 'Run Reconciliation')
    by_label(app.button, 'Run automatic local matching').click().run()
    assert not case[0].load(case[1])['results'][0]['proposed']
    approved(engine, 'master', 'The Gardens of Provence')
    # Existing session, no reupload or cache reset, no optional matching toggle.
    app.run()
    table = app.dataframe[-1].value
    assert table['Master Approved English Translation'].iloc[0] == 'The Gardens of Provence'
    by_label(app.button, 'Run automatic local matching').click().run()
    assert not app.exception
    saved = Result(**case[0].load(case[1])['results'][0])
    assert saved.proposed == 'SMB' and saved.match_method == 'Exact — Approved Translation'
    assert not saved.final and len(REVIEW_FILTERS) == 6
    assert app.dataframe[-1].value['Master Approved English Translation'].iloc[0] == 'The Gardens of Provence'


def test_research_gets_both_names_but_translation_is_not_identity_proof(tmp_path):
    case, engine = fixture(tmp_path, [{'Name': 'Les Jardins de Provence', 'Segment': 'Verify', 'Country': 'FR'}],
                           [{'Name': 'The Gardens of Provence', 'Segment': 'SMB', 'Country': 'US'}])
    approved(engine, 'master', 'The Gardens of Provence')
    result = match(case, engine)[0]
    # An AI assertion based only on translated similarity is rejected by the actual grounding validator.
    finding = {'verified_facts': [{'subject': result.identifier, 'entity': 'The Gardens of Provence',
        'relationship': 'Direct', 'verified_names': [], 'quote': 'The Gardens of Provence offers garden supplies.',
        'evidence_urls': ['https://example.com/company'], 'inheritance_quote': '', 'confidence': 'High'}],
        'explanation': 'Name similarity suggests identity.'}
    transport = Transport([
        Response({'results': [{'url': 'https://example.com/company', 'content': 'The Gardens of Provence offers garden supplies.'}]}),
        Response({'choices': [{'message': {'content': json.dumps(finding)}}]})])
    researcher = Researcher(case[0], case[1], 'mock-t', 'mock-o', ResearchSettings(interval=0), transport, lambda _: None)
    key = researcher.cache_key(result, 'ctx')
    researcher.investigate(result, pl.DataFrame(case[0].load(case[1])['source']), MAPPING, 'ctx')
    query = transport.calls[0][1]['json']['query']
    assert 'Les Jardins de Provence' in query and 'The Gardens of Provence' in query
    prompt = json.loads(transport.calls[1][1]['json']['messages'][1]['content'])
    assert prompt['original_company_name'] == 'Les Jardins de Provence'
    assert prompt['approved_english_translation'] == 'The Gardens of Provence'
    assert prompt['account_context']['master']['fields']['Country'] == 'FR'
    assert prompt['account_context']['sources'][0]['fields']['Country'] == 'US'
    assert result.recommendation_status == 'Insufficient Evidence'
    assert result.proposed == result.local_proposed == 'SMB' and not result.ai_proposed and not result.final
    assert len(transport.calls) == 2  # one search and one AI call, unchanged budget
    # Revocation/correction changes the current context, never reuses this cache key.
    payload = case[0].load(case[1])
    ApprovedNames(payload, MAPPING, []).attach([result])
    assert researcher.cache_key(result, 'ctx') != key
    assert researcher.cached(result, 'ctx') is None
    assert not result.account_context['master']['approved_english']


def test_research_original_names_with_separate_identifiers(tmp_path):
    case, engine = fixture(tmp_path,
        [{'Name': 'Les Jardins de Provence', 'Segment': 'Verify', 'Account ID': 'M-001'}],
        [{'Name': 'The Gardens of Provence', 'Segment': 'SMB', 'Account ID': 'S-002'}])
    approved(engine, 'master', 'The Gardens of Provence')
    payload = case[0].load(case[1])
    mapping = Mapping('Account ID', 'Account ID', 'Segment', 'Segment')
    payload['mapping'] = vars(mapping);case[0].save(case[1], payload)
    r = match(case, engine)[0]
    assert r.proposed == 'SMB' and r.identifier == 'M-001'
    quote = 'Les Jardins de Provence is also known as The Gardens of Provence.'
    finding = {'verified_facts': [{'subject': 'Les Jardins de Provence', 'entity': 'The Gardens of Provence',
        'relationship': 'Direct', 'verified_names': [], 'quote': quote,
        'evidence_urls': ['https://example.com/legal'], 'inheritance_quote': '', 'confidence': 'High'}],
        'explanation': 'Explicit legal identity statement.'}
    transport = Transport([Response({'results': [{'url': 'https://example.com/legal', 'content': quote}]}),
        Response({'choices': [{'message': {'content': json.dumps(finding)}}]})])
    researcher = Researcher(case[0], case[1], 'mock-t', 'mock-o', ResearchSettings(interval=0), transport, lambda _: None)
    researcher.investigate(r, pl.DataFrame(payload['source']), mapping, 'ctx')
    assert r.recommendation_status == 'Proposed' and r.proposed == 'SMB' and not r.final
    assert r.recommended_source_account == 'S-002'  # identifier remains primary for review selection
    assert r.suggested_matches[0]['source_row'] == 0
    prompt = json.loads(transport.calls[1][1]['json']['messages'][1]['content'])
    assert prompt['company'] == 'Les Jardins de Provence'
    assert prompt['account_context']['master']['fields']['Account ID'] == 'M-001'


def test_master_translation_collision_same_value_still_unverified(tmp_path):
    case, engine = fixture(tmp_path,
        [{'Name': 'Compañía Nacional de Comercio', 'Segment': 'Verify'},
         {'Name': 'Société Nationale de Commerce', 'Segment': 'Verify'}],
        [{'Name': 'National Trading Company', 'Segment': 'SMB'}])
    approved(engine, 'master', 'National Trading Company', 0)
    approved(engine, 'master', 'National Trading Company', 1)
    results = match(case, engine)
    assert all(r.match_status == 'Duplicate identifier' and not r.final for r in results)
    assert all(r.identity_confidence != 'Reliable local match' for r in results)


def test_research_payload_source_approval_and_draft_exclusion(tmp_path):
    case, engine = fixture(tmp_path,
        [{'Name': 'The Gardens of Provence', 'Segment': 'Verify'}],
        [{'Name': 'Les Jardins de Provence', 'Segment': 'SMB'}])
    approved(engine, 'source', 'The Gardens of Provence')
    r = match(case, engine)[0]
    transport = Transport([Response({'results': []}), Response({'choices': [{'message': {'content': json.dumps(
        {'verified_facts': [], 'explanation': 'No evidence.'})}}]})])
    Researcher(case[0], case[1], 'mock-t', 'mock-o', ResearchSettings(interval=0), transport, lambda _: None).investigate(
        r, pl.DataFrame(case[0].load(case[1])['source']), MAPPING, 'ctx')
    prompt = json.loads(transport.calls[1][1]['json']['messages'][1]['content'])
    assert prompt['account_context']['sources'][0]['approved_english'] == 'The Gardens of Provence'
    payload = case[0].load(case[1])
    drafts = [{**entry, 'status': 'Translated — Review', 'english': 'CONFIDENTIAL UNAPPROVED DRAFT'} for entry in engine.records()]
    ApprovedNames(payload, MAPPING, drafts).attach([r])
    r.research_status = 'Not researched'
    # Even legacy provenance contains a formerly approved text, not current input.
    transport = Transport([Response({'results': []}), Response({'choices': [{'message': {'content': json.dumps(
        {'verified_facts': [], 'explanation': 'No evidence.'})}}]})])
    Researcher(case[0], case[1], 'mock-t', 'mock-o', ResearchSettings(interval=0), transport, lambda _: None).investigate(
        r, pl.DataFrame(payload['source']), MAPPING, 'ctx')
    sent = json.dumps(transport.calls[1][1]['json'])
    assert 'CONFIDENTIAL UNAPPROVED DRAFT' not in sent
    prompt = json.loads(transport.calls[1][1]['json']['messages'][1]['content'])
    assert not prompt['account_context']['sources'][0]['approved_english']


def test_new_approval_not_hidden_by_saved_insufficient_research(tmp_path, monkeypatch):
    case, engine = fixture(tmp_path, [{'Name': 'Les Jardins de Provence', 'Segment': 'Verify'}],
                           [{'Name': 'The Gardens of Provence', 'Segment': 'SMB'}])
    before = match(case, engine)[0]
    before.research_snapshot = {'finding': {'verified_facts': [], 'explanation': 'No evidence'}, 'source_context': 'ctx'}
    before.research_status = 'Insufficient Evidence'
    before.evidence = ['https://example.com/old']
    payload = case[0].load(case[1]);payload['results'] = [before.dict()];case[0].save(case[1], payload)
    approved(engine, 'master', 'The Gardens of Provence')
    app = app_for(case, monkeypatch)
    navigate(app, 'Run Reconciliation')
    by_label(app.button, 'Run automatic local matching').click().run()
    saved = Result(**case[0].load(case[1])['results'][0])
    assert saved.proposed == 'SMB' and saved.match_method == 'Exact — Approved Translation'
    assert saved.research_snapshot == before.research_snapshot and saved.evidence == before.evidence
    assert not saved.final


def test_human_decisions_survive_translation_rerun(tmp_path, monkeypatch):
    case, engine = fixture(tmp_path, [{'Name': 'Les Jardins de Provence', 'Segment': 'Verify'}],
                           [{'Name': 'The Gardens of Provence', 'Segment': 'SMB'}])
    payload = case[0].load(case[1]);payload['results'] = [match(case, engine)[0].dict()];case[0].save(case[1], payload)
    case[0].review(case[1], 0, 'Manual', 'Account reviewer', 'Independently verified', manual_value='Healthcare')
    original_audit = case[0].audit(case[1])
    approved(engine, 'master', 'The Gardens of Provence')
    app = app_for(case, monkeypatch)
    navigate(app, 'Run Reconciliation')
    by_label(app.button, 'Run automatic local matching').click().run()
    saved = Result(**case[0].load(case[1])['results'][0])
    assert final_value(saved) == 'Healthcare' and saved.decision == 'Manual'
    assert case[0].audit(case[1])[:len(original_audit)] == original_audit
    assert app.dataframe[-1].value['Master Approved English Translation'].iloc[0] == 'The Gardens of Provence'
