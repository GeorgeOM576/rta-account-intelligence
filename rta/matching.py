from collections import defaultdict, Counter
import re
import polars as pl
from rapidfuzz import fuzz, process
from .models import Result, normalize, valid

UNRESOLVED_NOTE = 'Refer to suggested account options and similarity scores.'
CONFLICT_NOTE = 'Multiple source records detected. Manual review required.'
RELATION_NOTE = 'Potential corporate relationship identified. Field value requires verification.'


class Matcher:
    def __init__(self, source, mapping, aliases=None, relationships=None):
        for column in (mapping.source_id, mapping.source_value):
            if column not in source.columns:
                raise ValueError(f'Missing Source column: {column}')
        self.mapping = mapping
        source = source.with_columns(pl.col(mapping.source_id).cast(pl.Utf8))
        self.rows = source.to_dicts()
        self.aliases = {normalize(k): normalize(v) for k, v in (aliases or {}).items()}
        self.relationships = {normalize(k): normalize(v) for k, v in (relationships or {}).items()}
        self.exact, self.normal, self.blocks = defaultdict(list), defaultdict(list), defaultdict(set)
        for i, row in enumerate(self.rows):
            name = str(row[mapping.source_id] or '')
            key = normalize(name)
            if not key:
                continue
            self.exact[name].append(i)
            self.normal[key].append(i)
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
        for block in self.block_keys(name):
            posting = self.blocks.get(block, ())
            # Very common tokens/grams provide no useful blocking signal.
            # Skip them so generic names cannot turn this into Cartesian scoring.
            if len(posting) <= 2500:
                counts.update(posting)
        keys = [k for k, _ in counts.most_common(1200)]
        for i in priority:
            key = normalize(self.rows[i][self.mapping.source_id])
            if key not in keys:
                keys.append(key)
        # Small deterministic fallback pool still avoids a full source comparison.
        if len(keys) < 3:
            keys = list(dict.fromkeys(keys + list(self.normal)[:100]))
        ranked = process.extract(normalize(name), keys, scorer=fuzz.WRatio, limit=6)
        indices = list(dict.fromkeys(priority + [i for key, _, _ in ranked for i in self.normal[key]]))
        return [{'source_row': i, 'account': str(self.rows[i][self.mapping.source_id]),
                 'value': str(self.rows[i][self.mapping.source_value] or ''),
                 'similarity': round(fuzz.WRatio(normalize(name), normalize(self.rows[i][self.mapping.source_id])), 1)}
                for i in indices[:3]]

    def run(self, master):
        m = self.mapping
        for col in (m.master_id, m.master_value):
            if col not in master.columns:
                raise ValueError(f'Missing Master column: {col}')
        output = []
        master = master.with_columns(pl.col(m.master_id).cast(pl.Utf8))
        master_counts = Counter(normalize(x) for x in master[m.master_id].to_list())
        for number, row in enumerate(master.to_dicts()):
            name, original = str(row[m.master_id] or ''), str(row[m.master_value] or '')
            key = normalize(name)
            result = Result(number, name, original, notes=UNRESOLVED_NOTE)
            hits, stage = [], 'Unresolved'
            if key:
                for lookup, lookup_key, label in ((self.exact, name, 'Exact'), (self.normal, key, 'Normalized'),
                        (self.normal, self.aliases.get(key), 'Alias'), (self.normal, self.relationships.get(key), 'Relationship')):
                    if lookup_key and lookup.get(lookup_key):
                        hits, stage = lookup[lookup_key], label
                        break
                result.candidates = self.candidates(name, hits)
            if hits:
                # Include normalized collisions even when an exact spelling exists.
                collision = self.normal[normalize(self.rows[hits[0]][m.source_id])]
                values = {normalize(self.rows[i][m.source_value]) for i in collision}
                result.match_status = stage
                value = str(self.rows[hits[0]][m.source_value] or '')
                if len(values) > 1:
                    result.match_status, result.notes = 'Duplicate conflict', CONFLICT_NOTE
                elif len(collision) > 1 or master_counts[key] > 1:
                    result.match_status, result.notes = 'Duplicate identifier', CONFLICT_NOTE
                    result.proposed = value if valid(value) else ''
                elif stage == 'Relationship':
                    result.relationship, result.notes = 'Parent/subsidiary', RELATION_NOTE
                    result.proposed = value if valid(value) else ''
                else:
                    result.identity_confidence = 'Reliable local match'
                    result.proposed = value if valid(value) else ''
                    if valid(original) and valid(value) and normalize(original) == normalize(value):
                        result.notes = 'Local match proposed. Human approval required.'
                    else:
                        result.notes = 'Source value differs or is missing. Review required.'
            elif result.candidates:
                result.match_status = 'Fuzzy candidates'
            if not key:
                result.match_status = 'Missing identifier'
            output.append(result)
        return output
