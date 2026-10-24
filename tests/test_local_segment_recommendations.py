"""Deterministic regression fixtures, not the user's 50-account benchmark."""
from io import BytesIO
import polars as pl
import pytest
from openpyxl import load_workbook
from rta.models import Mapping
from rta.translation_matching import reconcile
from rta.storage import digest
from rta.export import workbook, result_row
from rta.review import decide, final_value, bulk_approval_error

M = Mapping('Name', 'Name', 'Segment', 'Segment')


def run(name, source_names, original='Verify', values=None, translation=None, status='Approved Translation'):
    master = pl.DataFrame({'Name': [name], 'Segment': [original]})
    source = pl.DataFrame({'Name': source_names, 'Segment': values or ['SMB'] * len(source_names)})
    records = []
    if translation:
        records = [dict(dataset='master', row_id=0, field='Name', original=name,
                        revision=digest(master.to_dicts()), english=translation, status=status)]
    return reconcile(master, source, M, records)[0][0]


@pytest.mark.parametrize('original', ['', 'Verify', 'Unmapped'])
def test_unresolved_local_segment(original):
    r = run('Sunshine Bakery', ['Sunshine Bakery'], original)
    assert r.proposed == 'SMB' and r.local_confidence == 'High'
    assert not r.final and not r.decision and not r.ai_proposed
    assert result_row(r)['Proposed Segment'] == 'SMB'
    decide(r, 'Approve', 'Reviewer')
    assert final_value(r) == 'SMB'


@pytest.mark.parametrize('name,translated,source', [
    ('Boulangerie du Soleil', 'Sunshine Bakery', 'Sunshine Bakery'),
    ('ООО Северный Ветер', 'Severny Veter LLC', 'Severny Veter LLC'),
    ('Casa de Moda Bella', 'Bella Fashion House', 'Bella Fashion House'),
])
def test_approved_multilingual_regressions(name, translated, source):
    r = run(name, [source], translation=translated)
    assert r.identifier == name and r.candidates[0]['account'] == source
    assert r.proposed == 'SMB' and r.local_confidence == 'Medium'
    assert r.translation_provenance[0]['translations']
    assert not r.final and not r.decision
    draft = run(name, [source], translation=translated, status='Translated — Review')
    assert not draft.proposed


def test_suffix_and_ambiguity():
    r = run('Sunshine Bakery, Inc.', ['Sunshine Bakery LLC'])
    assert r.match_status == 'Company suffix' and r.local_confidence == 'Medium'
    assert r.proposed == 'SMB' and not r.final
    ambiguous = run('Sunshine Bakery', ['Sunshine Bakery Inc', 'Sunshine Bakery LLC'])
    assert ambiguous.local_confidence == 'Low' and not ambiguous.proposed
    conflict = run('Sunshine Bakery', ['Sunshine Bakery', 'SUNSHINE BAKERY'], values=['SMB', 'Enterprise'])
    assert conflict.match_status == 'Duplicate conflict' and not conflict.proposed
    assert not run('Unrelated Observatory', ['Sunshine Bakery']).proposed


def test_existing_master_and_excel_approval_boundary():
    r = run('Sunshine Bakery', ['Sunshine Bakery'], original='Enterprise')
    assert r.original == 'Enterprise' and 'Conflict' in r.local_reason
    book = load_workbook(BytesIO(workbook([r], [], [], 1)))
    sheet = book['Reconciliation Results']
    row = dict(zip([c.value for c in sheet[1]], [c.value for c in sheet[2]]))
    assert row['Original Value'] == 'Enterprise' and row['Proposed Segment'] == 'SMB'
    assert row['Final Value'] is None
    decide(r, 'Retain original', 'Reviewer')
    assert final_value(r) == 'Enterprise'


def test_optional_insufficient_research_preserves_local_evidence():
    from rta.research import Researcher
    r = run('Boulangerie du Soleil', ['Sunshine Bakery'], translation='Sunshine Bakery')
    Researcher(None, '').evaluate_saved(r, pl.DataFrame({'Name': ['Sunshine Bakery'], 'Segment': ['SMB']}), M, 'ctx',
        snapshot={'source_context': 'ctx', 'finding': {'verified_facts': [], 'explanation': 'No external evidence.'},
                  'retrieved_evidence': []})
    assert r.recommendation_status == 'Insufficient Evidence'
    assert r.proposed == r.local_proposed == 'SMB' and not r.ai_proposed
    assert not r.final and not r.decision


def test_tentative_suffix_requires_individual_review():
    r = run('Sunshine Bakery Inc', ['Sunshine Bakery LLC'])
    assert bulk_approval_error(r, {})
    assert r.identity_confidence != 'Reliable local match'
