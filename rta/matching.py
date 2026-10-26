from collections import defaultdict, Counter
import re
import polars as pl
from rapidfuzz import fuzz, process
from .models import Result, normalize, valid
from .name_normalization import name_keys, ranking_variant, equivalence_method
from .language_detection import field_kind

UNRESOLVED_NOTE = 'Refer to suggested account options and similarity scores.'
CONFLICT_NOTE = 'Multiple source records detected. Manual review required.'
RELATION_NOTE = 'Potential corporate relationship identified. Field value requires verification.'


def company_key(name):
    """Remove terminal legal forms only; retain meaningful company-name tokens."""
    tokens = re.findall(r'\w+', str(name).casefold())
    suffixes = {'inc', 'incorporated', 'llc', 'ltd', 'limited', 'corp', 'corporation', 'plc'}
    while len(tokens) > 1 and tokens[-1] in suffixes:
        tokens.pop()
    return normalize(' '.join(tokens))


def assess_local(result):
    """Qualify dataset evidence without changing human decisions or final values."""
    status = result.match_status
    result.local_confidence = ('High' if status in ('Exact', 'Normalized', 'Alias') else
                               'Medium' if status in ('Translation-assisted', 'Company suffix', 'Name equivalent') else 'Low')
    if result.local_confidence == 'Low':
        result.local_reason = 'Ambiguous, relationship-only, or weak name evidence; individual investigation required.'
        result.proposed = ''
    elif result.proposed:
        result.local_reason = ('Unique uploaded Source match. ' if result.local_confidence == 'High' else
                               'Tentative uploaded Source match; verify the entity before approval. ')
        if valid(result.original):
            if normalize(result.original) != normalize(result.proposed):
                result.local_reason += 'Conflict with the existing Master value; retain it unless a reviewer explicitly approves a change.'
            else:
                result.local_reason += 'Source agrees with the existing Master value.'
        else:
            result.local_reason += 'Master value is unresolved; Source supplies a valid value.'
        result.local_reason += ' Human approval required.'
    else:
        result.local_reason = 'Matched Source has no valid comparison value.'
    result.local_proposed = result.proposed
    return result


class Matcher:
    def __init__(self, source, mapping, aliases=None, relationships=None, *, company_names=None):
        for column in (mapping.source_id, mapping.source_value):
            if column not in source.columns:
                raise ValueError(f'Missing Source column: {column}')
        self.mapping = mapping
        source = source.with_columns(pl.col(mapping.source_id).cast(pl.Utf8))
        self.rows = source.to_dicts()
        self.aliases = {normalize(k): normalize(v) for k, v in (aliases or {}).items()}
        self.relationships = {normalize(k): normalize(v) for k, v in (relationships or {}).items()}
        self.company_names = company_names if company_names is not None else all(field_kind(getattr(mapping, f'{d}_id'), vars(mapping), d) == 'account_name'
                                 for d in ('master', 'source'))
        self.equivalents = defaultdict(set)
        self.company = defaultdict(list)
        self.exact, self.normal, self.blocks = defaultdict(list), defaultdict(list), defaultdict(set)
        for i, row in enumerate(self.rows):
            name = str(row[mapping.source_id] or '')
            key = normalize(name)
            if not key:
                continue
            self.exact[name].append(i)
            self.normal[key].append(i)
            self.company[company_key(name)].append(i)
            for method, equivalent in name_keys(name) if self.company_names else ():
                self.equivalents[equivalent].add(i)
            for block in self.block_keys(name):
                self.blocks[block].add(key)
        self.conflicts = []
        for key, indices in self.normal.items():
            if len(indices) > 1:
                conflicting = len({normalize(self.rows[i][mapping.source_value]) for i in indices}) > 1
                for i in indices:
                    self.conflicts.append({**self.rows[i], 'Conflict': conflicting, 'Normalized identifier': key})

    @staticmethod
    def block_keys(name):
        key = normalize(name)
        tokens = re.findall(r'\w+', str(name).casefold())
        return {key[:3], *('t:' + t for t in tokens if len(t) > 2),
                *('g:' + key[i:i+3] for i in range(max(0, len(key)-2)))}

    def candidates(self, name, priority):
        counts = Counter()
        for block in sorted(self.block_keys(name)):
            posting = self.blocks.get(block, ())
            # Very common tokens/grams provide no useful blocking signal.
            # Skip them so generic names cannot turn this into Cartesian scoring.
            if len(posting) <= 2500:
                counts.update(posting)
        keys = sorted(counts, key=lambda k: (-counts[k], self.normal[k][0]))[:1200]
        for i in priority:
            key = normalize(self.rows[i][self.mapping.source_id])
            if key not in keys:
                keys.append(key)
        # Small deterministic fallback pool still avoids a full source comparison.
        if len(keys) < 3:
            keys = list(dict.fromkeys(keys + list(self.normal)[:100]))
        ranked = sorted(process.extract(normalize(name), keys, scorer=fuzz.WRatio, limit=6),
                        key=lambda hit: (-hit[1], -fuzz.ratio(normalize(name), hit[0]), self.normal[hit[0]][0]))
        indices = list(dict.fromkeys(priority + [i for key, _, _ in ranked for i in self.normal[key]]))
        return [{'source_row': i, 'account': str(self.rows[i][self.mapping.source_id]),
                 'value': str(self.rows[i][self.mapping.source_value] or ''),
                 'similarity': round(fuzz.WRatio(normalize(name), normalize(self.rows[i][self.mapping.source_id])), 1)}
                for i in indices[:3]]

    def close_competitor(self, name, hits, candidates):
        target_keys = {k for _, k in name_keys(name)}
        for candidate in candidates:
            if candidate['source_row'] in hits:
                continue
            if any(fuzz.ratio(a, b) >= 96 for a in target_keys
                   for _, b in name_keys(candidate['account'])):
                return True
        return False

    def run(self, master):
        m = self.mapping
        for col in (m.master_id, m.master_value):
            if col not in master.columns:
                raise ValueError(f'Missing Master column: {col}')
        output = []
        master = master.with_columns(pl.col(m.master_id).cast(pl.Utf8))
        master_counts = Counter(normalize(x) for x in master[m.master_id].to_list())
        master_equivalents = defaultdict(set)
        for i, text in enumerate(master[m.master_id].to_list()):
            for _, equivalent in name_keys(text) if self.company_names else ():
                master_equivalents[equivalent].add(i)
        for number, row in enumerate(master.to_dicts()):
            name, original = str(row[m.master_id] or ''), str(row[m.master_value] or '')
            key = normalize(name)
            result = Result(number, name, original, notes=UNRESOLVED_NOTE)
            hits, stage = [], 'Unresolved'
            if key:
                for lookup, lookup_key, label in ((self.exact, name, 'Exact'), (self.normal, key, 'Normalized'),
                        (self.normal, self.aliases.get(key), 'Alias'), (self.normal, self.relationships.get(key), 'Relationship'),
                        (self.company, company_key(name), 'Company suffix')):
                    if lookup_key and lookup.get(lookup_key):
                        hits, stage = lookup[lookup_key], label
                        break
                if stage == 'Company suffix' and self.company_names:
                    hits = sorted(set(hits).union(*(self.equivalents.get(k, set()) for _, k in name_keys(name))))
                if not hits and self.company_names:
                    evidence = [(method, equivalent, self.equivalents.get(equivalent, set()))
                                for method, equivalent in name_keys(name)]
                    supported = [(method, equivalent, indices) for method, equivalent, indices in evidence if indices]
                    if supported:
                        # All deterministic variants must agree; never choose a convenient collision.
                        hits = sorted(set().union(*(indices for _, _, indices in supported)))
                        stage = 'Name equivalent'
                        result.match_method = equivalence_method(name, self.rows[hits[0]][m.source_id])
                        result.match_basis = 'Master Original ↔ Source Original'
                result.candidates = self.candidates(name, hits)
                romanized = ranking_variant(name) if self.company_names else ''
                if not hits and romanized:
                    ranked = self.candidates(romanized, [])
                    if ranked and (not result.candidates or ranked[0]['similarity'] > result.candidates[0]['similarity']):
                        result.candidates = ranked
                        result.match_method = 'Transliteration candidates'
                        for candidate in result.candidates:
                            candidate['match_basis'] = 'Cyrillic romanization — ranking only'
                            candidate['ranking_variant'] = romanized

            if hits:
                # Include normalized collisions even when an exact spelling exists.
                collision = sorted(set(hits) | set(self.normal[normalize(self.rows[hits[0]][m.source_id])]))
                values = {normalize(self.rows[i][m.source_value]) for i in collision}
                result.match_status = stage
                value = str(self.rows[hits[0]][m.source_value] or '')
                if len(values) > 1:
                    result.match_status, result.notes = 'Duplicate conflict', CONFLICT_NOTE
                elif (len(collision) > 1 or master_counts[key] > 1 or
                      (stage in ('Name equivalent', 'Company suffix') and any(len(master_equivalents[k]) > 1 for _, k in name_keys(name)))):
                    result.match_status, result.notes = 'Duplicate identifier', CONFLICT_NOTE
                    result.proposed = value if valid(value) else ''
                elif stage == 'Relationship':
                    result.relationship, result.notes = 'Parent/subsidiary', RELATION_NOTE
                    result.proposed = value if valid(value) else ''
                elif stage == 'Name equivalent' and self.close_competitor(name, hits, result.candidates):
                    result.match_status = 'Ambiguous candidates'
                    result.notes = 'A competing Source name is too similar; individual investigation required.'
                else:
                    result.identity_confidence = (f'{stage} — verification required' if stage in ('Company suffix', 'Name equivalent') else 'Reliable local match')
                    result.proposed = value if valid(value) else ''
                    if valid(original) and valid(value) and normalize(original) == normalize(value):
                        result.notes = 'Local match proposed. Human approval required.'
                    else:
                        result.notes = 'Source value differs or is missing. Review required.'
            elif result.candidates:
                result.match_status = 'Fuzzy candidates'
            if not key:
                result.match_status = 'Missing identifier'
            if result.match_method and result.match_status == 'Name equivalent':
                result.notes = f'{result.match_method} equivalence; human verification required.'
            output.append(assess_local(result))
        return output
