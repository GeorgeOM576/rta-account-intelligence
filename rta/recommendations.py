"""Validate AI findings against actual Source rows and saved, quoted evidence."""
from jsonschema import Draft202012Validator
import re
from .models import normalize, valid
from .relationships import mentions, same_identity_statement, POLICIES

INSUFFICIENT = 'Insufficient Evidence — Manual Review Required'
RELATIONSHIPS = ['Direct', 'Renamed', 'Acquired', 'Subsidiary', 'Fuzzy', 'Unknown']
PROPERTIES = {
    'source_row': {'type': ['integer', 'null']},
    'recommended_source_account': {'type': 'string'},
    'parent_company': {'type': 'string'},
    'proposed_value': {'type': 'string'},
    'relationship': {'type': 'string', 'enum': RELATIONSHIPS},
    'confidence': {'type': 'string', 'enum': ['High', 'Medium', 'Low']},
    'recommendation_status': {'type': 'string', 'enum': ['Proposed', 'Insufficient Evidence']},
    'explanation': {'type': 'string'},
    'reasoning': {'type': 'string'},
    'evidence_urls': {'type': 'array', 'items': {'type': 'string'}},
    'supporting_quote': {'type': 'string'},
    'identity_supported': {'type': 'boolean'},
    'inheritance_supported': {'type': 'boolean'},
    'inheritance_quote': {'type': 'string'},
}
SCHEMA = {'type': 'object', 'properties': PROPERTIES, 'required': list(PROPERTIES), 'additionalProperties': False}


def validate_recommendation(finding, evidence, source, mapping, candidate_ids, master_name='', policy=POLICIES[0]):
    """Schema success is necessary, never sufficient, for an actionable proposal."""
    Draft202012Validator(SCHEMA).validate(finding)
    available = {e['url']: e['content'] for e in evidence}
    urls = list(dict.fromkeys(u for u in finding['evidence_urls'] if u in available))
    recommendation = {'relationship': finding['relationship'], 'explanation': finding['explanation'][:3000],
        'parent_company': finding['parent_company'][:500], 'confidence': finding['confidence'],
        'reasoning': finding['reasoning'][:4000], 'evidence': urls, 'proposed': '', 'account': '',
        'recommendation_status': 'Insufficient Evidence'}

    def insufficient(reason):
        recommendation['confidence'] = 'Low'
        recommendation['reasoning'] = reason + (' ' + recommendation['reasoning'] if recommendation['reasoning'] else '')
        return recommendation

    if finding['parent_company'] and not any(
            normalize(finding['parent_company']) in normalize(text) for text in available.values()):
        recommendation['parent_company'] = ''
        return insufficient('The identified parent company is not present in the retrieved evidence.')

    if finding['recommendation_status'] != 'Proposed':
        return insufficient('No sufficiently supported Source mapping was established.')
    rows = source.to_dicts()
    index = finding['source_row']
    if type(index) is not int or index not in candidate_ids or not 0 <= index < len(rows):
        return insufficient('The recommended Source record is not an available candidate.')
    row = rows[index]
    name, value = str(row[mapping.source_id] or ''), str(row[mapping.source_value] or '')
    if finding['recommended_source_account'] != name:
        return insufficient('The recommended account does not match the selected Source row.')
    if not valid(value) or finding['proposed_value'] != value:
        return insufficient('The proposed value is not the exact valid value of the selected Source account.')
    values = {str(r[mapping.source_value] or '') for r in rows if normalize(r[mapping.source_id]) == normalize(name)}
    if len(values) != 1:
        return insufficient('Conflicting values exist for this Source identifier; manual investigation is required.')
    quote = finding['supporting_quote'].strip()
    if (not urls or len(urls) != len(set(finding['evidence_urls'])) or not quote
            or not any(quote in available[u] for u in urls)):
        return insufficient('Supporting citations or a verifiable evidence excerpt are missing.')
    if master_name and (not mentions(quote, master_name) or not mentions(quote, name)):
        return insufficient('The cited statement does not connect this Master company to the recommended Source entity. Name similarity is not proof.')
    if finding['relationship'] in ('Direct', 'Fuzzy', 'Renamed') and re.search(
            r'\b(similar|resembles|acquired|acquisition|parent|subsidiary)\b', quote, re.I):
        return insufficient('Corporate ownership or name similarity does not establish the same company identity.')
    if master_name and finding['relationship'] in ('Direct', 'Fuzzy') and not same_identity_statement(quote, master_name, name):
        return insufficient('The evidence lacks an explicit same-identity statement for these two companies.')
    if finding['confidence'] == 'Low' or finding['relationship'] == 'Unknown':
        return insufficient('Identity or mapping confidence is insufficient; similarity alone is not proof.')
    if finding['relationship'] in ('Subsidiary', 'Acquired'):
        if policy != POLICIES[0]:
            return insufficient('The organization policy permits same-entity mappings only.')
        if finding['relationship'] == 'Subsidiary' and normalize(finding['parent_company']) != normalize(name):
            return insufficient('The identified parent does not match the recommended Source account.')
        inheritance = finding['inheritance_quote'].strip()
        if (not finding['inheritance_supported'] or not inheritance or value.casefold() not in inheritance.casefold()
                or not any(inheritance in available[u] for u in urls)):
            return insufficient('Ownership alone does not support segment inheritance; account-specific field evidence is missing.')
    elif not finding['identity_supported']:
        return insufficient('The supplied evidence does not sufficiently establish the same company identity.')
    recommendation.update(proposed=value, account=name, recommendation_status='Proposed')
    return recommendation
