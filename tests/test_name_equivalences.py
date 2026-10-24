"""Conservative equivalences and counterexamples: no live translation or research."""
import polars as pl
import pytest
from rta.matching import Matcher
from rta.models import Mapping
from rta.review import bulk_approval_error
from tests.test_local_segment_recommendations import run


@pytest.mark.parametrize('master,source,method', [
    ('Compañía del Sur', 'Compania del Sur', 'Diacritics'),
    ('MÜLLER MASCHINENBAU GMBH', 'Mueller Maschinenbau GmbH', 'German transliteration'),
    ('Sunrise Retail Co.', 'Sunrise Retail Company', 'Legal suffix'),
    ('Terra Verde Energia', 'Terra Verde Energia SA', 'Legal suffix'),
    ('Alpine Medical Devices', 'Alpine Medical Devices GmbH', 'Legal suffix'),
    ('East Coast Pharma', 'East Coast Pharmaceuticals', 'Business abbreviation'),
    ('Mercury Telecom', 'Mercury Telecommunications', 'Business abbreviation'),
    ('Horizon Edu Services', 'Horizon Education Services', 'Business abbreviation'),
    ('Bluebird Studio', 'Bluebird Studios', 'Singular/plural'),
    ('Prairie Farm Supply Co', 'Prairie Farm Supplies Company', 'Singular/plural'),
])
def test_unique_equivalence_is_tentative(master, source, method):
    r = run(master, [source])
    assert r.proposed == 'SMB' and r.local_confidence == 'Medium'
    assert r.match_method == method
    assert r.identifier == master and r.candidates[0]['account'] == source
    assert r.translation_provenance[0].get('normalization') == method
    assert not r.final and not r.decision
    assert bulk_approval_error(r, {})


@pytest.mark.parametrize('master,sources', [
    ('Café Horizon', ['Cafe Horizon LLC', 'Café Horizon GmbH']),
    ('Alpha Pharma', ['Alpha Pharmaceuticals Inc', 'Alpha Pharma LLC']),
    ('Bluebird Studio', ['Bluebird Studios Inc', 'Bluebird Studio LLC']),
    ('Müller Works', ['Mueller Works LLC', 'Muller Works Inc']),
    ('Sunrise Retail Co', ['Sunrise Retail Company LLC', 'Sunrise Retail GmbH']),
])
@pytest.mark.parametrize('values', [['SMB', 'SMB'], ['SMB', 'Enterprise']])
def test_transformed_collisions_abstain(master, sources, values):
    r = run(master, sources, values=values)
    assert r.local_confidence == 'Low' and not r.proposed and not r.final


@pytest.mark.parametrize('master,source', [
    ('Silver Oak Capital', 'Silveroak Capital Partners'),
    ('BrightPath Learning', 'Bright Path Learning Center'),
    ('Ocean View Hotels', 'Oceanview Hotels & Resorts'),
    ('Pacific Fresh Foods', 'Pacific Fresh Food Distribution'),
    ('North Harbor Pharma', 'South Harbor Pharmaceuticals'),
    ('Mercury Telecom', 'Mercury Telecom Equipment'),
    ('Acme 100 Pharma', 'Acme 101 Pharmaceuticals'),
    ('Trading Northern Energy', 'Northern Energy Trading'),
    ('Arctic Wind Power', 'Arctic Wind Energy'),
])
def test_meaningful_words_and_word_order_are_not_deleted(master, source):
    assert not run(master, [source]).proposed


def test_close_competitor_abstains():
    r = run('Northern Regional Pharma', ['Northern Regional Pharmaceuticals', 'Northern Regionals Pharmaceuticals'])
    assert r.match_status == 'Ambiguous candidates' and not r.proposed


def test_exact_identity_beats_weaker_normalization():
    r = run('Alpha Pharma', ['Alpha Pharmaceuticals', 'Alpha Pharma'], values=['Enterprise', 'SMB'])
    assert r.match_status == 'Exact' and r.proposed == 'SMB'
    assert r.candidates[0]['account'] == 'Alpha Pharma'


def test_cyrillic_is_ranking_only():
    r = run('ООО Северный Ветер', ['Golden Gate Consulting LLC', 'Severny Veter LLC'], translation='North Wind LLC')
    assert r.candidates[0]['account'] == 'Severny Veter LLC'
    assert r.match_method == 'Transliteration candidates'
    assert r.candidates[0]['ranking_variant'] == 'severnyy veter'
    assert not r.proposed and not r.final and not r.decision


def test_approved_translation_uses_equivalences_without_approving_itself():
    r = run('未知の会社', ['Horizon Education Services Ltd'], translation='Horizon Edu Services')
    assert r.proposed == 'SMB' and r.match_status == 'Translation-assisted'
    assert r.translation_provenance[0]['translations'][0]['english'] == 'Horizon Edu Services'
    assert not run('未知の会社', ['Horizon Education Services Ltd'], translation='Horizon Edu Services', status='Translated — Review').proposed


def test_conflicting_approved_and_original_evidence_abstains():
    r = run('Café Horizon', ['Cafe Horizon', 'Unrelated Trading'], translation='Unrelated Trading')
    assert r.local_confidence == 'Low' and not r.proposed


def test_name_equivalences_do_not_rewrite_identifiers():
    mapping = Mapping('Account ID', 'Source ID', 'Segment', 'Segment')
    m = pl.DataFrame({'Account ID': ['Pharma123'], 'Segment': ['Verify']})
    s = pl.DataFrame({'Source ID': ['Pharmaceuticals123'], 'Segment': ['SMB']})
    assert not Matcher(s, mapping).run(m)[0].proposed


def test_master_equivalence_collision_abstains():
    mapping = Mapping('Name', 'Name', 'Segment', 'Segment')
    m = pl.DataFrame({'Name': ['Café Horizon', 'Cafe Horizon LLC'], 'Segment': ['Verify', 'Verify']})
    s = pl.DataFrame({'Name': ['Cafe Horizon GmbH'], 'Segment': ['SMB']})
    assert all(not r.proposed for r in Matcher(s, mapping).run(m))


def test_approved_equivalence_has_close_competitor_guard():
    r = run('未知の会社', ['Northern Regional Pharmaceuticals', 'Northern Regionals Pharmaceuticals'],
            translation='Northern Regional Pharma')
    assert r.match_status == 'Ambiguous candidates' and not r.proposed


def test_conflicting_approved_name_and_suffix_abstain():
    r = run('Alpha Bakery Inc', ['Alpha Bakery LLC', 'Unrelated Trading'], translation='Unrelated Trading')
    assert r.local_confidence == 'Low' and not r.proposed
