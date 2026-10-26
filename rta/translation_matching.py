"""Approved English variants supplement original matching, never identity verification."""
from collections import defaultdict
from rapidfuzz import fuzz

from .matching import Matcher, CONFLICT_NOTE, assess_local
from .models import normalize, valid
from .name_normalization import name_keys, equivalence_method
from .approved_names import ApprovedNames
import polars as pl


def reconcile(master, source, mapping, records=(), *, aliases=None, relationships=None, previous=()):
    engine = Matcher(source, mapping, aliases, relationships)
    results = engine.run(master)
    master_rows, source_rows = master.to_dicts(), source.to_dicts()
    names = ApprovedNames({'master': master_rows, 'source': source_rows}, mapping, records)
    approved = names.approved
    context_by_row = defaultdict(list)
    for (dataset, row_id, field), entry in approved.items():
        if field != (mapping.master_id if dataset == 'master' else mapping.source_id):
            context_by_row[(dataset, row_id)].append(entry)

    def comparison_checks(master_id, source_id):
        left = [('Original Master', master_rows[master_id][mapping.master_value])]
        right = [('Original Source', source_rows[source_id][mapping.source_value])]
        for dataset, row_id, field, target, label in [
            ('master', master_id, mapping.master_value, left, 'Translated Master'),
            ('source', source_id, mapping.source_value, right, 'Translated Source')]:
            entry = approved.get((dataset, row_id, field))
            if entry:
                target.append((label, entry['english']))
        return [{'direction': f'{a} → {b}', 'master_field': mapping.master_value,
                 'source_field': mapping.source_value, 'master_value': x, 'source_value': y,
                 'agrees': bool(valid(x) and valid(y) and normalize(x) == normalize(y))}
                for a, x in left for b, y in right]
    originals, translated = defaultdict(list), defaultdict(list)
    master_keys = defaultdict(set)
    master_variant_keys = defaultdict(set)
    for i, row in enumerate(engine.rows):
        key = normalize(names.account('source', i)['original_name'])
        if key:
            originals[key].append(i)
        entry = approved.get(('source', i, names.fields['source']))
        if entry and normalize(entry['english']):
            translated[normalize(entry['english'])].append(i)
    for i, row in enumerate(master_rows):
        for text in [names.account('master', i)['original_name'], approved.get(('master', i, names.fields['master']), {}).get('english')]:
            if normalize(text):
                master_keys[normalize(text)].add(i)
                for _, equivalent in name_keys(text):
                    master_variant_keys[equivalent].add(i)
    # Reuse the existing blocked fuzzy index for original and approved variants.
    supplementary = any(f == names.fields[d] for d, i, f in approved) or any(
        names.fields[d] != getattr(mapping, f'{d}_id') for d in ('master', 'source'))
    variant_rows, variant_refs = [], []
    for i in range(len(source_rows)) if supplementary else ():
        for label, text, entry in names.variants('source', i):
            variant_rows.append({mapping.source_id: text, mapping.source_value: source_rows[i][mapping.source_value]})
            variant_refs.append((i, label, text, entry))
    variant_engine = Matcher(pl.DataFrame(variant_rows), mapping, company_names=True) if variant_rows else None
    for result, row in zip(results, master_rows):
        result.match_method = result.match_method or result.match_status
        result.match_basis = ('Master Identifier ↔ Source Identifier' if any(
            names.fields[d] != getattr(mapping, f'{d}_id') for d in ('master', 'source')) else
            'Master Original ↔ Source Original')
        if result.match_method == 'Transliteration candidates':
            result.match_basis = 'Master Cyrillic romanization ↔ Source Original — ranking only'
        if not result.candidates:
            result.match_basis = ''
        for candidate in result.candidates:
            candidate['match_basis'] = result.match_basis
        result.match_score = (100.0 if result.match_status in ('Exact', 'Normalized') else
                              result.candidates[0]['similarity'] if result.candidates else None)
        # Original rules, including duplicate conflicts, always retain precedence.
        if result.match_status not in ('Fuzzy candidates', 'Unresolved', 'Name equivalent', 'Company suffix'):
            if result.candidates and result.match_status != 'Missing identifier':
                result.translation_provenance = [{'direction': 'Original Master → Original Source',
                    'master_field': mapping.master_id, 'source_field': mapping.source_id, 'translations': [],
                    'comparison_context': [dict(r) for r in context_by_row[('master', result.row_id)] +
                                           context_by_row[('source', result.candidates[0]['source_row'])]],
                    'comparison_checks': comparison_checks(result.row_id, result.candidates[0]['source_row'])}]
            continue
        original = normalize(names.account('master', result.row_id)['original_name'])
        master_entry = approved.get(('master', result.row_id, names.fields['master']))
        english = normalize(master_entry['english']) if master_entry else ''
        comparisons = [(original, originals, 'Original Master → Original Source', False, False),
                       (original, translated, 'Original Master → Translated Source', False, True),
                       (english, originals, 'Translated Master → Original Source', True, False),
                       (english, translated, 'Translated Master → Translated Source', True, True)]
        hits, provenance, duplicate_master = set(), [], False
        for key, index, direction, used_master, used_source in comparisons:
            if not key:
                continue
            for source_row in index.get(key, []):
                hits.add(source_row)
                duplicate_master |= len(master_keys[key]) > 1
                refs = []
                if used_master:
                    refs.append(dict(master_entry))
                if used_source:
                    refs.append(dict(approved[('source', source_row, names.fields['source'])]))
                # Retain other approved selected fields as context, not a replacement Source value.
                context = [dict(r) for r in context_by_row[('master', result.row_id)] + context_by_row[('source', source_row)]]
                provenance.append({'direction': direction, 'master_field': names.fields['master'],
                    'source_field': names.fields['source'], 'source_row': source_row, 'translations': refs,
                    'comparison_context': context, 'comparison_checks': comparison_checks(result.row_id, source_row)})
        normalization_ambiguous = False
        if not hits and supplementary:
            for left_label, text, left_entry in names.variants('master', result.row_id):
                supported = set()
                for method, equivalent in name_keys(text):
                    indices = variant_engine.equivalents.get(equivalent, ()) if variant_engine else ()
                    if indices:
                        supported.update(indices)
                if supported and variant_engine.close_competitor(text, supported, variant_engine.candidates(text, sorted(supported))):
                    normalization_ambiguous = True
                for variant_id in sorted(supported):
                    i, right_label, right_text, right_entry = variant_refs[variant_id]
                    if not (left_entry or right_entry) and names.fields['master'] == mapping.master_id and names.fields['source'] == mapping.source_id:
                        continue
                    hits.add(i)
                    duplicate_master |= any(len(master_variant_keys[k]) > 1 for _, k in name_keys(text))
                    provenance.append({'direction': f'{left_label} → {right_label}',
                        'master_field': names.fields['master'], 'source_field': names.fields['source'],
                        'source_row': i, 'translations': [dict(e) for e in (left_entry, right_entry) if e],
                        'normalization': equivalence_method(text, right_text), 'comparison_context': [],
                        'comparison_checks': comparison_checks(result.row_id, i)})
        if not hits and result.match_status in ('Name equivalent', 'Company suffix'):
            if result.candidates:
                result.translation_provenance = [{'direction': 'Original Master → Original Source',
                    'master_field': mapping.master_id, 'source_field': mapping.source_id,
                    'source_row': result.candidates[0]['source_row'], 'translations': [],
                    'normalization': result.match_method}]
            continue
        if hits and result.match_status in ('Name equivalent', 'Company suffix'):
            # Contradictory approved-name evidence must never silently replace the original match.
            hits.add(result.candidates[0]['source_row'])
        if not hits:
            if not supplementary:
                continue
            ranked = {}
            for left_label, text, entry in names.variants('master', result.row_id):
                for candidate in variant_engine.candidates(text, []) if variant_engine else []:
                    i, right_label, right_text, right_entry = variant_refs[candidate['source_row']]
                    score = candidate['similarity']
                    priority = (score, int(entry is None and right_entry is None))
                    if i not in ranked or priority > ranked[i][0]:
                        ranked[i] = (priority, {'source_row': i, 'account': str(source_rows[i][mapping.source_id]),
                            'value': str(source_rows[i][mapping.source_value] or ''), 'similarity': score,
                            'match_basis': basis(f'{left_label} → {right_label}')},
                            {'direction': f'{left_label} → {right_label}', 'master_field': names.fields['master'],
                             'source_field': names.fields['source'], 'source_row': i,
                             'translations': [dict(e) for e in (entry, right_entry) if e],
                             'comparison_context': [], 'comparison_checks': comparison_checks(result.row_id, i)})
            best = sorted(ranked.values(), key=lambda item: item[0], reverse=True)[:3]
            if best and (result.match_method != 'Transliteration candidates' or
                         best[0][1]['similarity'] > result.candidates[0]['similarity']):
                result.candidates = [b[1] for b in best]
                result.translation_provenance = [b[2] for b in best]
                result.match_method = 'Fuzzy — Approved Translation' if best[0][2]['translations'] else 'Fuzzy'
                result.match_basis = basis(best[0][2]['direction'])
                result.match_score = best[0][1]['similarity']
            continue
        # Include all collisions of the original Source identifier, not just the translated row.
        collision = set(hits)
        for i in hits:
            collision.update(engine.normal.get(normalize(engine.rows[i][mapping.source_id]), []))
        values = {normalize(engine.rows[i][mapping.source_value]) for i in collision}
        result.match_status = 'Translation-assisted'
        # Exact spelling wins over normalization; equivalent evidence favors originals.
        def strength(p):
            left = names.account('master', result.row_id)
            right = names.account('source', p['source_row'])
            a = left['approved_english'] if p['direction'].startswith('Translated') else left['original_name']
            b = right['approved_english'] if p['direction'].endswith('Translated Source') else right['original_name']
            return (a == b, not p['translations'])
        provenance.sort(key=strength, reverse=True)
        strongest = provenance[0]
        result.match_method = (strongest.get('normalization') or ('Exact' if strength(strongest)[0] else 'Normalized')) + (' — Approved Translation' if strongest['translations'] else '')
        result.match_basis = basis(strongest['direction'])
        result.match_score = 100.0
        result.identity_confidence = 'Translation-assisted — verification required'
        result.notes = 'Approved translations suggest a match. Independently verify the entity and Source field value before approval.'
        result.translation_provenance = provenance
        result.candidates = [{'source_row': i, 'account': str(engine.rows[i][mapping.source_id]),
            'value': str(engine.rows[i][mapping.source_value] or ''),
            'similarity': round(fuzz.WRatio(normalize(result.identifier), normalize(engine.rows[i][mapping.source_id])), 1),
            'match_basis': next((basis(p['direction']) for p in provenance if p['source_row'] == i), '')}
            for i in sorted(collision, key=lambda i: (i != strongest['source_row'], i))[:3]]
        value = str(engine.rows[min(hits)][mapping.source_value] or '')
        if len(values) > 1:
            result.match_status, result.notes = 'Duplicate conflict', CONFLICT_NOTE
        elif normalization_ambiguous:
            result.match_status = 'Ambiguous candidates'
            result.notes = 'Competing approved-name variants are too similar; individual investigation required.'
        else:
            result.proposed = value if valid(value) else ''
            if len(collision) > 1 or duplicate_master:
                result.match_status, result.notes = 'Duplicate identifier', CONFLICT_NOTE
        # No translation path sets final, verified_original, or reliable identity confidence.
    for result in results:
        assess_local(result)
    if previous:
        results = retain_reviewed(results, previous)
    names.attach(results)
    from .secondary_validation import SecondaryValidator
    validator = SecondaryValidator(master_rows, source_rows, mapping, names, aliases)
    for result in results:
        validator.evaluate(result)
    names.attach(results)
    return results, engine.conflicts


def basis(direction):
    return direction.replace('Original Master', 'Master Original').replace('Translated Master', 'Master Translation').replace('Original Source', 'Source Original').replace('Translated Source', 'Source Translation').replace(' → ', ' ↔ ')


def retain_reviewed(fresh, previous):
    """Keep human decisions/evidence-backed proposals; refresh unresolved local candidates."""
    saved = {r.row_id: r for r in previous}
    output = []
    for current in fresh:
        old = saved.get(current.row_id)
        if old and (old.decision or (old.research_snapshot and old.recommendation_status == 'Proposed' and old.ai_proposed)):
            output.append(old)
            continue
        if old and old.research_snapshot:
            # A past insufficient finding must not hide a newly approved name candidate.
            # Preserve its complete evidence/history without treating it as a new investigation.
            for field in ('research_snapshot', 'research_history', 'research_status', 'researched_at',
                          'research_cache_hit', 'explanation', 'evidence', 'verified_facts', 'suggested_matches',
                          'recommendation_status', 'recommendation_reasoning', 'recommended_source_account',
                          'ai_confidence', 'parent_company', 'mapping_policy'):
                setattr(current, field, getattr(old, field))
        output.append(current)
    return output
