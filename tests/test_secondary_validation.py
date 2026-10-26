from copy import deepcopy
from io import BytesIO
import polars as pl
import pytest
from openpyxl import load_workbook
from rta.models import Mapping, Result
from rta.approved_names import ApprovedNames
from rta.translation_matching import reconcile
from rta.secondary_validation import SecondaryValidator, VALIDATED, REVIEW, CONFLICT, INSUFFICIENT, reevaluate_attached
from rta.storage import digest
from rta.review import decide, bulk_approval_error
from rta.export import workbook

M = Mapping('Name', 'Name', 'Segment', 'Segment')


def case(master_name='Western Data Labs', source_names=('Western Data Laboratories',), *,
         master_extra=None, source_extra=None, master_segment='Verify', records=()):
    master = [{'Name': master_name, 'Segment': master_segment, **(master_extra or {})}]
    source = [{'Name': name, 'Segment': 'Technology', **((source_extra or [{}] * len(source_names))[i])}
              for i, name in enumerate(source_names)]
    results, _ = reconcile(pl.DataFrame(master), pl.DataFrame(source), M, records)
    names = ApprovedNames({'master': master, 'source': source}, M, records)
    return results[0], SecondaryValidator(master, source, M, names), master, source


@pytest.mark.parametrize('left,right', [
    ('Western Data Labs', 'Western Data Laboratories'),
    ('Oak & Stone Construction', 'Oak and Stone Construction'),
    ('Evergreen Learning Centre', 'Evergreen Learning Center'),
    ('Horizon Education Svcs', 'Horizon Education Services'),
    ('Orchid Beauty Products', 'Orchid Beauty Product Co.'),
    ('Terra Nova Agri Co', 'Terra Nova Agriculture Company'),
])
def test_bounded_secondary_equivalences(left, right):
    r, _, _, _ = case(left, (right,))
    assert r.match_status == 'Secondary validated' and r.proposed == 'Technology'
    assert r.secondary_validation['status'] == VALIDATED and r.secondary_validation['evidence']
    assert r.account_context['matched_source']['original_name'] == right
    assert r.identifier == left and r.original == 'Verify' and not r.final and not r.decision
    assert bulk_approval_error(r, {})


@pytest.mark.parametrize('left,right', [
    ('North Harbor Labs', 'South Harbor Laboratories'),
    ('Greenfield Medical', 'Greenfield Medical Supplies'),
    ('Alpha Capital', 'Alpha Capital Partners'),
    ('Orchid Beauty', 'Orchid Beauty Product Co'),
    ('Silverline Auto Parts', 'Silverline Automotive Parts'),
    ('Westland Services', 'Eastland Services'),
    ('Basil and Birch Catering', 'Basil Birch Catering'),
])
def test_no_meaningful_word_deletion_or_semantic_guess(left, right):
    r, _, _, _ = case(left, (right,))
    assert not r.proposed and not r.account_context['matched_source']


def test_conflicting_identifiers_veto_even_exact_name():
    r, _, _, _ = case('Western Data', ('Western Data',), master_extra={'Tax ID': '001'}, source_extra=[{'Tax ID': '002'}])
    assert not r.proposed and r.secondary_validation['status'] == CONFLICT
    assert not r.account_context['matched_source'] and not r.final


def test_unique_identifier_can_support_name_variation():
    r, _, _, _ = case('Legacy Western Brand', ('Western Data Laboratories',), master_extra={'Registration Number': '0012'}, source_extra=[{'Registration Number': '0012'}])
    assert r.proposed == 'Technology' and r.secondary_validation['confidence'] == 'High'
    assert r.match_status == 'Secondary validated' and not r.final


def test_identifier_keeps_leading_zeros_and_field_scope():
    r, _, _, _ = case(master_extra={'Registration Number': '0012'}, source_extra=[{'Registration Number': '12'}])
    assert not r.proposed and r.secondary_validation['status'] == CONFLICT


def test_reused_identifier_requires_review():
    r, _, _, _ = case(source_names=('Western Data Laboratories', 'Different Corporation'),
        master_extra={'Registration Number': '0012'}, source_extra=[{'Registration Number': '0012'}, {'Registration Number': '0012'}])
    assert not r.proposed and r.secondary_validation['status'] == REVIEW


@pytest.mark.parametrize('left,right', [('https://western.example/about', 'www.western.example'),
                                       ('western.example', 'https://western.example')])
def test_uploaded_domains_support_name_equivalence(left, right):
    r, _, _, _ = case(master_extra={'Website': left}, source_extra=[{'Domain': right}])
    assert r.proposed == 'Technology' and not r.final
    assert any('domain' in x for x in r.secondary_validation['evidence'])


def test_conflicting_domains_and_shared_domain_are_not_identity_proof():
    r, _, _, _ = case(master_extra={'Website': 'western.example'}, source_extra=[{'Website': 'unrelated.example'}])
    assert not r.proposed and r.secondary_validation['status'] == CONFLICT
    r, _, _, _ = case('Legacy Western Brand', ('Different Entity',), master_extra={'Website': 'western.example'}, source_extra=[{'Website': 'western.example'}])
    assert not r.proposed and r.secondary_validation['status'] == REVIEW


def test_equivalent_sources_same_or_different_segments_do_not_resolve():
    r, _, _, _ = case(source_names=('Western Data Laboratories', 'Western Data Labs LLC'))
    assert not r.proposed and r.secondary_validation['status'] == REVIEW


def test_score_tie_cannot_promote_candidate():
    r, v, _, _ = case(source_names=('Western Data Laboratories', 'Western Data Solutions'))
    r.proposed = r.local_proposed = ''
    r.match_status = 'Fuzzy candidates'
    r.candidates[0]['similarity'] = r.candidates[1]['similarity'] = 90
    v.evaluate(r)
    assert not r.proposed and r.secondary_validation['status'] == REVIEW


def test_translation_collision_remains_unresolved():
    master = [{'Name': '未知の会社', 'Segment': 'Verify'}]
    source = [{'Name': 'Western Data Labs', 'Segment': 'Technology'}, {'Name': 'Western Data Laboratories', 'Segment': 'Retail'}]
    records = [{'dataset': 'master', 'row_id': 0, 'field': 'Name', 'revision': digest(master),
                'original': master[0]['Name'], 'english': 'Western Data Labs', 'status': 'Approved Translation'}]
    r = reconcile(pl.DataFrame(master), pl.DataFrame(source), M, records)[0][0]
    assert not r.proposed and r.secondary_validation['status'] == REVIEW
    assert not r.final


@pytest.mark.parametrize('decision', ['Approve', 'Reject', 'Manual', 'Retain original'])
def test_reviewed_results_are_byte_for_byte_preserved(decision):
    r, v, _, _ = case(master_segment='Retail')
    decide(r, decision, 'Reviewer', manual_value='Technology')
    before = r.dict()
    v.evaluate(r)
    assert r.dict() == before


def research_case():
    r, v, master, source = case('Western Brand', ('Western Holdings',))
    quote = 'Western Brand is the same company as Western Holdings.'
    finding = {'verified_facts': [{'subject': 'Western Brand', 'entity': 'Western Holdings',
        'relationship': 'Direct', 'verified_names': [], 'quote': quote,
        'evidence_urls': ['https://www.sec.gov/test/identity'], 'inheritance_quote': '', 'confidence': 'High'}],
        'explanation': 'Saved entity discovery.'}
    r.research_snapshot = {'source_context': v.context, 'finding': finding,
        'approved_name_context': deepcopy(r.account_context),
        'retrieved_evidence': [{'url': 'https://www.sec.gov/test/identity', 'content': quote}]}
    r.research_status = 'Completed'
    return r, v, source


def test_saved_grounded_authoritative_research_is_reused_offline(monkeypatch):
    import requests
    monkeypatch.setattr(requests.Session, 'post', lambda *a, **k: pytest.fail('No provider calls allowed'))
    r, v, _ = research_case()
    v.evaluate(r)
    assert r.proposed == 'Technology' and r.secondary_validation['status'] == VALIDATED
    assert any('Saved authoritative' in e for e in r.secondary_validation['evidence'])
    assert not r.final and not r.decision


@pytest.mark.parametrize('failure', ['summary', 'hallucinated_quote', 'unrelated_company', 'untrusted_source', 'stale_context', 'insufficient', 'failed'])
def test_unsupported_research_never_confirms(failure):
    r, v, _ = research_case()
    if failure == 'summary':
        r.research_snapshot = {}; r.explanation = 'These companies are definitely identical.'
    elif failure == 'hallucinated_quote':
        r.research_snapshot['retrieved_evidence'][0]['content'] = 'Western Holdings sells tools.'
    elif failure == 'unrelated_company':
        r.research_snapshot['finding']['verified_facts'][0]['subject'] = 'Unrelated Western Brand'
    elif failure == 'untrusted_source':
        r.research_snapshot['retrieved_evidence'][0]['url'] = 'https://random-blog.example/identity'
        r.research_snapshot['finding']['verified_facts'][0]['evidence_urls'] = ['https://random-blog.example/identity']
    elif failure == 'stale_context':
        r.research_snapshot['source_context'] = 'older-upload'
    elif failure == 'insufficient':
        r.research_status = 'Insufficient Evidence'; r.recommendation_status = 'Insufficient Evidence'
    else:
        r.research_status = 'Failed'
    v.evaluate(r)
    assert not r.proposed and r.secondary_validation['status'] == INSUFFICIENT


def test_research_callback_preserves_row_identity_and_review():
    r, _, source = research_case()
    r.row_id = 7
    reevaluate_attached(r, pl.DataFrame(source), M)
    assert r.row_id == 7 and r.proposed == 'Technology' and not r.final
    decide(r, 'Approve', 'Reviewer')
    before = r.dict()
    reevaluate_attached(r, pl.DataFrame(source), M)
    assert r.dict() == before


def test_conflicting_master_segment_and_excel_boundary():
    r, _, _, _ = case(master_segment='Retail')
    assert r.original == 'Retail' and r.proposed == 'Technology' and 'Conflict' in r.local_reason
    sh = load_workbook(BytesIO(workbook([r], [], [], 1)))['Reconciliation Results']
    row = dict(zip([c.value for c in sh[1]], [c.value for c in sh[2]]))
    assert row['Secondary Validation Status'] == VALIDATED
    assert row['Original Value'] == 'Retail' and row['Proposed Value'] == 'Technology' and row['Final Value'] is None


def test_revalidation_revokes_stale_secondary_proposal():
    r, v, _, _ = case()
    assert r.proposed
    v.source[0]['Name'] = 'Unrelated Account'
    v.evaluate(r)
    assert not r.proposed and r.secondary_validation['status'] == CONFLICT


def test_stale_master_or_segment_cannot_keep_a_pending_proposal():
    r, v, _, _ = case()
    v.master[0]['Name'] = 'Changed Master Identity'
    v.evaluate(r)
    assert not r.proposed and r.secondary_validation['status'] == CONFLICT
    r, v, _, _ = case('Western Data', ('Western Data',))
    v.source[0]['Segment'] = 'Different Segment'
    v.evaluate(r)
    assert not r.proposed and r.secondary_validation['status'] == CONFLICT


def test_actual_research_callback_is_offline_and_annotates_result(monkeypatch):
    import requests
    from rta.research import Researcher
    monkeypatch.setattr(requests.Session, 'post', lambda *a, **k: pytest.fail('No paid calls'))
    r, v, source = research_case()
    Researcher(None, '').evaluate_saved(r, pl.DataFrame(source), M, v.context, snapshot=r.research_snapshot)
    assert r.proposed == 'Technology' and r.secondary_validation['status'] == VALIDATED
    assert not r.final and not r.decision


def test_pending_legacy_final_is_never_rewritten():
    r, v, _, _ = case()
    r.final = 'Legacy raw final'
    v.evaluate(r)
    assert r.final == 'Legacy raw final' and not r.decision


def test_reconciliation_preserves_existing_human_decision():
    r, _, master, source = case()
    decide(r, 'Manual', 'Reviewer', 'Human evidence', manual_value='Reviewed Segment')
    before = (r.final, r.decision, r.reviewer, r.reviewed_at, r.notes)
    fresh, _ = reconcile(pl.DataFrame(master), pl.DataFrame(source), M, previous=[r])
    saved = fresh[0]
    assert (saved.final, saved.decision, saved.reviewer, saved.reviewed_at, saved.notes) == before
