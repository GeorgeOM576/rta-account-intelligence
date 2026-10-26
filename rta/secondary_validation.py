"""Offline corroboration of a ranked candidate; never approve or write final values."""
from collections import defaultdict
from functools import lru_cache
import re
from urllib.parse import urlparse

from .models import normalize, valid
from .name_normalization import name_keys, tokens
from .storage import digest

VALIDATED = 'Validated — Proposal Available'
REVIEW = 'Additional Review Required'
CONFLICT = 'Conflicting Evidence'
INSUFFICIENT = 'Insufficient Evidence'
# Bounded orthographic/inflection equivalents, not semantic business synonyms.
WORDS = {'centre': 'center', 'svcs': 'services', 'labs': 'laboratories',
         'agri': 'agriculture', 'properties': 'property', 'products': 'product',
         'pharmaceutical': 'pharmaceuticals'}
REGISTRIES = {'sec.gov', 'companieshouse.gov.uk',
              'find-and-update.company-information.service.gov.uk'}
SHARED_HOSTS = {'facebook.com', 'linkedin.com', 'twitter.com', 'x.com', 'google.com',
                'wix.com', 'squarespace.com', 'wordpress.com'}


def host(value):
    text = str(value or '').strip().lower()
    if not text or re.search(r'\s', text):
        return ''
    try:
        parsed = urlparse(text if '://' in text else 'https://' + text)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
            return ''
        result = (parsed.hostname or '').removeprefix('www.').rstrip('.')
    except ValueError:
        return ''
    if '.' not in result or any(result == h or result.endswith('.' + h) for h in SHARED_HOSTS):
        return ''
    return result


@lru_cache(maxsize=30000)
def secondary_keys(name):
    """Keep every meaningful token; '&' and the word 'and' share a separator."""
    # Do not remove 'and' indiscriminately: replace both spellings with the same token.
    text = re.sub(r'&', ' and ', str(name or ''))
    parts = tokens(text)
    if parts and parts[0] == 'ooo':
        parts = parts[1:]  # Uploaded approved romanization of a Russian legal form.
    if parts and parts[-1] == 'kk':
        parts = parts[:-1]  # Japanese company legal form; name remains untouched.
    parts = [WORDS.get(t, t) if t != 'and' else 'and' for t in parts]
    return frozenset(k for _, k in name_keys(' '.join(parts)) if k)


def identity_fields(row):
    values = {}
    for field, value in row.items():
        label = re.sub(r'[_-]+', ' ', field).strip().casefold()
        text = str(value or '').strip()
        if not valid(text):
            continue
        if re.search(r'\b(domain|website|web site|url)\b', label):
            domain = host(text)
            if domain:
                values['domain'] = domain
        elif re.search(r'\b(registration|tax|vat|company id|lei|duns|legal entity identifier)\b', label):
            # Compare only same-named identifier fields; retain leading zeros.
            values['id:' + label] = text.casefold()
    return values


class SecondaryValidator:
    def __init__(self, master, source, mapping, names, aliases=None):
        self.master, self.source, self.mapping, self.names = master, source, mapping, names
        self.aliases = {normalize(k): normalize(v) for k, v in (aliases or {}).items()}
        self.source_keys, self.master_keys = defaultdict(set), defaultdict(set)
        self.source_names = defaultdict(set)
        for i, row in enumerate(source):
            self.source_names[normalize(row[mapping.source_id])].add(i)
        self.source_identity = [identity_fields(row) for row in source]
        self.identity_index = defaultdict(set)
        for i, fields in enumerate(self.source_identity):
            for kind, value in fields.items():
                self.identity_index[(kind, value)].add(i)
        for dataset, rows, index in [('source', source, self.source_keys), ('master', master, self.master_keys)]:
            for i in range(len(rows)):
                for _, text, _ in names.variants(dataset, i):
                    for key in secondary_keys(text):
                        index[key].add(i)
        self.context = digest({'source': source, 'mapping': vars(mapping)})

    def evaluate(self, result):
        # Re-evaluation must not even edit annotations on a human-reviewed result.
        if result.decision or result.review_status.startswith(('Approved', 'Manually Verified')):
            return result
        def finish(status, reason, confidence='Low', evidence=(), candidate=None):
            if status == CONFLICT:
                result.proposed = result.local_proposed = result.ai_proposed = ''
                result.match_status = 'Conflicting evidence'
                result.identity_confidence = 'Unverified'
                result.local_confidence = 'Low'
                result.local_reason = reason
                if result.recommendation_status == 'Proposed':
                    result.recommendation_status = 'Insufficient Evidence'
            result.secondary_validation = {'status': status, 'confidence': confidence, 'reason': reason,
                'evidence': list(evidence), 'source_row': candidate.get('source_row') if candidate else None,
                'candidate': candidate.get('account', '') if candidate else '', 'input_signature': self.context}
            return result
        if not 0 <= result.row_id < len(self.master):
            return finish(CONFLICT, 'The original Master record is unavailable.')
        master_row = self.master[result.row_id]
        if str(master_row[self.mapping.master_id] or '') != result.identifier:
            return finish(CONFLICT, 'The result no longer corresponds to this Master record.')
        if not result.candidates:
            return finish(INSUFFICIENT, 'No Source candidate is available.')
        candidate = result.candidates[0]
        if result.ai_proposed and result.recommendation_status == 'Proposed':
            # Existing research may legitimately link a different Source than the fuzzy first choice.
            supported = [c for c in result.suggested_matches if c.get('mapping_supported') and
                         c.get('account') == result.recommended_source_account]
            if len(supported) == 1:
                candidate = supported[0]
        index = candidate.get('source_row')
        if (type(index) is not int or not 0 <= index < len(self.source) or
                str(self.source[index][self.mapping.source_id] or '') != candidate.get('account')):
            result.proposed = result.local_proposed = result.ai_proposed = ''
            result.match_status = 'Conflicting evidence'
            return finish(CONFLICT, 'The ranked Source identity is stale; rerun matching.')
        row = self.source[index]
        left, right = identity_fields(master_row), self.source_identity[index]
        conflicts = [kind for kind in left.keys() & right.keys() if left[kind] != right[kind]]
        reused_ids = [kind for kind in left.keys() & right.keys() if kind.startswith('id:') and
                      left[kind] == right[kind] and len(self.identity_index[(kind, left[kind])]) > 1]
        if reused_ids:
            result.proposed = result.local_proposed = result.ai_proposed = ''
            result.match_status = 'Ambiguous candidates'
            result.identity_confidence = 'Unverified'
            return finish(REVIEW, 'The uploaded identifier is shared by multiple Source records.', candidate=candidate)
        if conflicts:
            # A name match cannot override contradictory uploaded identity evidence.
            result.proposed = result.local_proposed = ''
            result.ai_proposed = ''
            if result.recommendation_status == 'Proposed':
                result.recommendation_status = 'Insufficient Evidence'
            result.match_status = 'Conflicting evidence'
            result.identity_confidence = 'Unverified'
            result.local_confidence = 'Low'
            result.local_reason = 'Uploaded identity fields contradict this candidate.'
            return finish(CONFLICT, 'Uploaded identity fields disagree: ' + ', '.join(sorted(conflicts)), candidate=candidate)
        if result.match_status in ('Company suffix', 'Name equivalent', 'Translation-assisted'):
            possible = set()
            for _, text, _ in self.names.variants('master', result.row_id):
                for key in secondary_keys(text):
                    possible.update(self.source_keys.get(key, ()))
            if len(possible) > 1:
                result.proposed = result.local_proposed = ''
                result.match_status = 'Ambiguous candidates'
                result.local_confidence = 'Low'
                return finish(REVIEW, 'Approved/normalized name variants identify competing Source entities.', candidate=candidate)
        if result.match_status == 'Secondary validated':
            result.proposed = result.local_proposed = ''
            result.match_status = 'Fuzzy candidates'
            result.identity_confidence = 'Unverified'
        if result.proposed:
            if result.proposed != str(row[self.mapping.source_value] or ''):
                return finish(CONFLICT, 'The proposed Segment no longer agrees with the actual Source record; rerun matching.', candidate=candidate)
            if result.ai_proposed and not self.research_evidence(result, index, left, right):
                return finish(REVIEW, 'The existing AI proposal requires its original research and approval checks; secondary authoritative corroboration is unavailable.', candidate=candidate)
            return finish(VALIDATED, 'Existing proposal retained; human approval is required.',
                          result.local_confidence or result.ai_confidence or 'Medium', candidate=candidate)
        if result.match_status in ('Duplicate conflict', 'Duplicate identifier', 'Ambiguous candidates', 'Relationship'):
            return finish(REVIEW, 'Competing identities, conflicting Source values or a corporate relationship require individual review.', candidate=candidate)
        value = str(row[self.mapping.source_value] or '')
        if not valid(value):
            return finish(INSUFFICIENT, 'The actual Source Segment is missing or unresolved.', candidate=candidate)
        # Include all Source collisions, not only the displayed three candidates.
        key = normalize(candidate['account'])
        same_name = self.source_names[key]
        if len(same_name) != 1:
            return finish(REVIEW, 'The Source identifier is not unique.', candidate=candidate)
        matched_keys = set()
        for _, text, _ in self.names.variants('master', result.row_id):
            matched_keys.update(secondary_keys(text) & set(self.source_keys))
        equivalent_hits = set().union(*(self.source_keys[k] for k in matched_keys)) if matched_keys else set()
        duplicate_master = any(len(self.master_keys[k]) > 1 for k in matched_keys)
        same_id = [kind for kind in left.keys() & right.keys()
                   if kind.startswith('id:') and left[kind] == right[kind] and
                   self.identity_index[(kind, left[kind])] == {index}]
        same_domain = (left.get('domain') and left.get('domain') == right.get('domain') and
                       self.identity_index[('domain', left['domain'])] == {index})
        evidence = []
        if same_id:
            evidence.append('Unique exact uploaded identifier: ' + ', '.join(sorted(same_id)))
        if same_domain:
            evidence.append('Unique exact uploaded website/domain')
        if equivalent_hits == {index} and not duplicate_master:
            evidence.append('Unique bounded name/approved-name equivalence; all meaningful business tokens retained')
        if self.aliases.get(normalize(result.identifier)) == key:
            evidence.append('Explicit workspace alias')
        # Near ties can veto name-only acceptance; score separation never creates evidence.
        first_score = candidate.get('similarity')
        runner = result.candidates[1] if len(result.candidates) > 1 else {}
        second_score = runner.get('similarity')
        gap = first_score - second_score if isinstance(first_score, (int, float)) and isinstance(second_score, (int, float)) else None
        if gap is not None and gap < 5 and not same_id:
            return finish(REVIEW, 'Competing candidates have insufficient score separation; similarity is not identity proof.', evidence=evidence, candidate=candidate)
        if len(equivalent_hits) > 1 or duplicate_master:
            return finish(REVIEW, 'Equivalent name variants identify multiple records.', evidence=evidence, candidate=candidate)
        research = self.research_evidence(result, index, left, right)
        evidence.extend(research)
        if not evidence:
            research_note = (' Saved research is absent, failed, insufficient, or lacks authoritative quoted identity evidence.'
                             if result.research_status != 'Not researched' else ' No saved authoritative identity evidence is available.')
            return finish(INSUFFICIENT, 'Name similarity and candidate ranking alone do not establish identity.' + research_note, candidate=candidate)
        # A domain by itself can be shared within a corporate group; require a name link too.
        domain_only = same_domain and not (same_id or equivalent_hits == {index} or research)
        if domain_only:
            return finish(REVIEW, 'A shared website alone does not establish the same legal entity.', evidence=evidence, candidate=candidate)
        result.proposed = result.local_proposed = value
        result.match_status = 'Secondary validated'
        result.match_method = 'Secondary — ' + ('Uploaded identifier' if same_id else 'Saved authoritative research' if research else 'Bounded name equivalence')
        result.match_basis = 'Master Original / Approved Name ↔ Source Original / Approved Name'
        result.identity_confidence = 'Secondary validated — individual verification required'
        result.local_confidence = 'High' if same_id else 'Medium'
        result.local_reason = '; '.join(evidence) + '. Human approval required.'
        if valid(result.original) and normalize(result.original) != normalize(value):
            result.local_reason += ' Conflict with valid Master Segment; retain original unless explicitly changed by a reviewer.'
        return finish(VALIDATED, result.local_reason, result.local_confidence, evidence, candidate)

    def research_evidence(self, result, index, left, right):
        """Revalidate saved excerpts; never infer verification from model prose or fetch URLs."""
        if result.research_status not in ('Completed', 'Cached') or result.recommendation_status == 'Insufficient Evidence':
            return []
        snapshot = result.research_snapshot
        if snapshot.get('source_context') != self.context or not snapshot.get('finding'):
            return []
        from .approved_names import approved_context_signature
        current = result.account_context
        if approved_context_signature(snapshot.get('approved_name_context', {})) != approved_context_signature(current):
            return []
        from .relationships import evaluate_entities, POLICIES, same_identity_statement
        from .recommendations import validate_recommendation
        from jsonschema import ValidationError
        import polars as pl
        finding = snapshot['finding']
        allowed_domains = {v for v in [left.get('domain'), right.get('domain')] if v} | REGISTRIES
        pages = [p for p in snapshot.get('retrieved_evidence', []) if p.get('content') and
                 host(p.get('url')) in allowed_domains]
        if not pages:
            return []
        company = self.names.account('master', result.row_id)['original_name']
        source_name = self.names.account('source', index)['original_name']
        # Both entities and a direct same-identity statement must occur in the saved text.
        pages = [p for p in pages if same_identity_statement(p['content'], company, source_name)]
        if not pages:
            return []
        try:
            if 'verified_facts' in finding:
                outcome = evaluate_entities(finding, pages, pl.DataFrame(self.source), self.mapping,
                    company, POLICIES[1], source_name_field=self.names.fields['source'])
            else:
                outcome = validate_recommendation(finding, pages, pl.DataFrame(self.source), self.mapping,
                    {index}, master_name=company, policy=POLICIES[1])
        except (ValidationError, ValueError, KeyError, TypeError, IndexError):
            return []
        if (outcome['recommendation_status'] == 'Proposed' and outcome['account'] == str(self.source[index][self.mapping.source_id] or '')
                and outcome['proposed'] == str(self.source[index][self.mapping.source_value] or '')):
            return ['Saved authoritative quoted same-identity evidence: ' + ', '.join(outcome['evidence'])]
        return []


def reevaluate_attached(result, source, mapping):
    """Research callback using current attached uploaded fields; no store or provider access."""
    from copy import deepcopy
    if result.decision:
        return result
    context = result.account_context
    master = context.get('master', {})
    if not master.get('fields'):
        return result
    rows = source.to_dicts()
    known = {a.get('row_id'): a for a in [*context.get('sources', []), context.get('matched_source', {})]
             if a and a.get('fields')}

    class CurrentNames:
        fields = {'master': master.get('field', mapping.master_id),
                  'source': context.get('source_name_field') or mapping.source_id}

        def account(self, dataset, row_id):
            if dataset == 'master':
                return master
            row = rows[row_id]
            account = known.get(row_id, {})
            # English is only reused from current attached ApprovedNames context.
            if account and account['fields'] == row:
                return account
            return {'original_name': str(row.get(self.fields['source']) or ''), 'fields': row}

        def variants(self, dataset, row_id):
            account = self.account(dataset, row_id)
            variants = [('Original ' + dataset.title(), account['original_name'], None)]
            if account.get('approved_english'):
                variants.append(('Translated ' + dataset.title(), account['approved_english'], account))
            return variants

    # A copied row avoids transient mutation of the caller's persisted row identity.
    working = deepcopy(result)
    working.row_id = 0
    validator = SecondaryValidator([master['fields']], rows, mapping, CurrentNames())
    validator.evaluate(working)
    for field in ('secondary_validation', 'proposed', 'local_proposed', 'match_status', 'match_method',
                  'match_basis', 'identity_confidence', 'local_confidence', 'local_reason',
                  'ai_proposed', 'recommendation_status'):
        setattr(result, field, getattr(working, field))
    # Refresh only the matched Source display association, preserving original fields/provenance.
    if result.match_status == 'Secondary validated':
        context['matched_source'] = CurrentNames().account('source', result.candidates[0]['source_row'])
    elif result.match_status == 'Conflicting evidence':
        context['matched_source'] = {}
    return result
