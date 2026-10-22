"""Evidence-grounded entity discovery followed by complete indexed Source lookup."""
from collections import defaultdict
import re
from jsonschema import Draft202012Validator
from .models import normalize, valid

POLICIES = ['Evidence-backed inheritance', 'Same entity only']
KINDS = ['Direct', 'Renamed', 'Alias', 'Parent', 'Subsidiary', 'Acquired', 'Merged']
FACT_PROPERTIES = {
    'subject': {'type': 'string'}, 'entity': {'type': 'string'},
    'relationship': {'type': 'string', 'enum': KINDS},
    'verified_names': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
        'properties': {'name': {'type': 'string'}, 'quote': {'type': 'string'}, 'url': {'type': 'string'}},
        'required': ['name', 'quote', 'url']}},
    'quote': {'type': 'string'}, 'evidence_urls': {'type': 'array', 'items': {'type': 'string'}},
    'inheritance_quote': {'type': 'string'}, 'confidence': {'type': 'string', 'enum': ['High', 'Medium', 'Low']},
}
DISCOVERY_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'properties': {'verified_facts': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
        'properties': FACT_PROPERTIES, 'required': list(FACT_PROPERTIES)}}, 'explanation': {'type': 'string'}},
    'required': ['verified_facts', 'explanation']}


def mentions(text, name):
    """Token boundaries avoid treating a substring of an unrelated name as an entity."""
    tokens = re.findall(r'\w+', str(name).casefold())
    return bool(tokens and re.search(r'(?<!\w)' + r'\W*'.join(map(re.escape, tokens)) + r'(?!\w)', str(text).casefold()))


def same_identity_statement(text, first, second):
    if normalize(first) == normalize(second):
        return mentions(text, first)
    def pattern(name):
        return r'\W*'.join(map(re.escape, re.findall(r'\w+', name.casefold())))
    link = (r'(?:is(?: now)?|is also known as|is the same (?:company|entity) as|'
            r'(?:was )?renamed|formerly(?: known as)?|previously known as|operates as|trading as|also known as)')
    return any(re.search(r'(?<!\w)' + pattern(a) + r'\W+' + link + r'\W+' + pattern(b) + r'(?!\w)',
                         text.casefold()) for a, b in ((first, second), (second, first)))


MARKERS = {
    'Direct': r'\b(is|same|known as|operates? as|trading as)\b',
    'Renamed': r'\b(renamed|formerly|previously|name change|changed.{0,20}name)\b',
    'Alias': r'\b(alias|also known|trading as|doing business as|dba|operates? as)\b',
    'Parent': r'\b(parent|subsidiary|owned|owns|ownership)\b',
    'Subsidiary': r'\b(parent|subsidiary|owned|owns|ownership)\b',
    'Acquired': r'\b(acquired|acquisition|purchased|bought)\b',
    'Merged': r'\b(merged|merger|combined)\b',
}


def grounded_fact(fact, company, evidence):
    pages = {e['url']: e['content'] for e in evidence}
    urls = fact['evidence_urls']
    quote = fact['quote'].strip()
    if (normalize(fact['subject']) != normalize(company) or not quote or not urls
            or any(u not in pages for u in urls) or not any(quote in pages[u] for u in urls)
            or not mentions(quote, company) or not mentions(quote, fact['entity'])):
        return None
    if not (fact['relationship'] == 'Direct' and normalize(company) == normalize(fact['entity'])):
        if not re.search(MARKERS[fact['relationship']], quote, re.I):
            return None
    if fact['relationship'] == 'Direct' and re.search(r'\b(acquired|acquisition|parent|subsidiary|similar|resembles)\b', quote, re.I):
        return None
    if fact['relationship'] == 'Direct' and not same_identity_statement(quote, company, fact['entity']):
        return None
    # Negated or tentative statements cannot verify a relationship.
    if re.search(r'\b(not|no evidence|unrelated|rumou?r|possibly|might|may be|unconfirmed)\b', quote, re.I):
        return None
    names = [fact['entity']]
    verified_names = []
    for alias in fact['verified_names']:
        text, url, name = alias['quote'].strip(), alias['url'], alias['name']
        if (url in pages and text and text in pages[url] and mentions(text, name)
                and mentions(text, fact['entity']) and re.search(MARKERS['Alias'] + '|' + MARKERS['Renamed'], text, re.I)
                and not re.search(r'\b(not|unrelated|possibly|unconfirmed)\b', text, re.I)):
            names.append(name)
            verified_names.append(alias)
    return {**fact, 'verified_names': verified_names, 'lookup_names': list(dict.fromkeys(names))}


def legacy_parent_discovery(finding, evidence, company):
    """Recover a named parent overlooked by old candidate-limited cached research, offline."""
    parent = finding.get('parent_company', '')
    if (not parent or normalize(parent) == normalize(finding.get('recommended_source_account', ''))
            or finding.get('relationship') not in ('Subsidiary', 'Acquired')):
        return None
    relationship = 'Parent' if finding['relationship'] == 'Subsidiary' else 'Acquired'
    facts = []
    for page in evidence:
        for quote in re.split(r'(?<=[.!?])\s+', page['content']):
            if mentions(quote, company) and mentions(quote, parent) and re.search(MARKERS[relationship], quote, re.I):
                facts.append({'subject': company, 'entity': parent, 'relationship': relationship,
                    'verified_names': [], 'quote': quote, 'evidence_urls': [page['url']],
                    'inheritance_quote': finding.get('inheritance_quote', '') if finding.get('inheritance_supported') else '',
                    'confidence': finding.get('confidence', 'Low')})
    return {'verified_facts': facts, 'explanation': finding.get('explanation', '')} if facts else None


def evaluate_entities(finding, evidence, source, mapping, company, policy=POLICIES[0], *, source_name_field=None):
    Draft202012Validator(DISCOVERY_SCHEMA).validate(finding)
    rows = source.to_dicts()
    index = defaultdict(list)
    for i, row in enumerate(rows):
        key = normalize(row[mapping.source_id])
        if key:
            index[key].append(i)
        # Original company names supplement mapped IDs; translations are never lookup aliases.
        name_key = normalize(row.get(source_name_field)) if source_name_field else ''
        if name_key and name_key != key:
            index[name_key].append(i)
    facts = [f for raw in finding['verified_facts'] if (f := grounded_fact(raw, company, evidence))]
    suggestions, choices, missing = [], [], []
    evidence_urls = list(dict.fromkeys(u for f in facts for u in
        (f['evidence_urls'] + [a['url'] for a in f['verified_names']])))
    for fact in facts:
        hits = list(dict.fromkeys(i for name in fact['lookup_names'] for i in index.get(normalize(name), [])))
        if not hits:
            missing.append(f"Verified entity {fact['entity']} and its verified names were not found in the Source file.")
        for i in hits:
            row = rows[i]
            name, value = str(row[mapping.source_id] or ''), str(row[mapping.source_value] or '')
            related = fact['relationship'] not in ('Direct', 'Renamed', 'Alias')
            reason = ''
            conflicting = {str(rows[j][mapping.source_value] or '') for j in index[normalize(name)]}
            if len(conflicting) != 1:
                reason = 'Conflicting Source segments require manual investigation.'
            elif not valid(value):
                reason = 'The Source segment is missing or a placeholder.'
            elif fact['confidence'] == 'Low':
                reason = 'The relationship evidence has low confidence.'
            elif related:
                inheritance = fact['inheritance_quote'].strip()
                pages = {e['url']: e['content'] for e in evidence}
                if policy != POLICIES[0]:
                    reason = 'The organization policy permits same-entity mappings only.'
                elif (not inheritance or not any(inheritance in pages[u] for u in fact['evidence_urls'])
                        or not mentions(inheritance, company) or not mentions(inheritance, fact['entity'])
                        or not mentions(inheritance, value)
                        or not re.search(r'\b(share|shares|shared|same|both)\b', inheritance, re.I)
                        or re.search(r'\b(not|unconfirmed|might|possibly)\b', inheritance, re.I)):
                    reason = 'Verified corporate relationship found, but account-specific segment inheritance evidence is missing.'
            candidate = {'source_row': i, 'account': name, 'value': value, 'relationship': fact['relationship'],
                         'entity': fact['entity'], 'confidence': fact['confidence'],
                         'mapping_supported': not reason, 'reason': reason or 'Source value and evidence support this mapping.'}
            suggestions.append(candidate)
            if reason:
                missing.append(reason)
            else:
                rank = {'Direct': 0, 'Renamed': 1, 'Alias': 1}.get(fact['relationship'], 2)
                choices.append((rank, candidate, fact))
    outcome = {'relationship': facts[0]['relationship'] if facts else 'Unknown',
        'explanation': finding['explanation'][:3000], 'parent_company': next((f['entity'] for f in facts
            if f['relationship'] in ('Parent', 'Acquired')), ''), 'confidence': 'Low',
        'reasoning': ' '.join(dict.fromkeys(missing)) or 'No sufficiently supported company identity or corporate relationship was established.',
        'evidence': evidence_urls, 'proposed': '', 'account': '', 'recommendation_status': 'Insufficient Evidence',
        'verified_facts': facts, 'suggested_matches': suggestions, 'mapping_policy': policy}
    if choices:
        best = min(c[0] for c in choices)
        finalists = [c for c in choices if c[0] == best]
        if len({c[1]['value'] for c in finalists}) > 1:
            outcome['reasoning'] = 'Equally supported Source entities have conflicting segments. Manual investigation is required.'
        else:
            _, candidate, fact = finalists[0]
            outcome.update(relationship=fact['relationship'], confidence=fact['confidence'],
                proposed=candidate['value'], account=candidate['account'], recommendation_status='Proposed',
                reasoning=f"Matched verified {fact['relationship']} entity {candidate['account']} across the entire Source file. "
                + ('Account-specific evidence supports segment inheritance under the organization policy.'
                   if fact['relationship'] not in ('Direct', 'Renamed', 'Alias') else 'The verified identity supports its actual Source segment.'))
    return outcome
