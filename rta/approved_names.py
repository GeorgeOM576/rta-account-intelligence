"""Current-revision approved account names, joined by the persisted cell identity."""
from .storage import digest
from .language_detection import field_kind


class ApprovedNames:
    def __init__(self, datasets, mapping, records=()):
        self.rows = {d: datasets.get(d, []) for d in ('master', 'source')}
        self.mapping = mapping
        self.source_selection_fingerprint = digest({'source': self.rows['source'], 'mapping': vars(mapping)})
        self.revisions = {d: digest(rows) for d, rows in self.rows.items()}
        self.approved = {}
        self.current = {}
        for entry in records:
            d, i, f = entry.get('dataset'), entry.get('row_id'), entry.get('field')
            rows = self.rows.get(d, [])
            if (entry.get('revision') == self.revisions.get(d)
                    and type(i) is int and 0 <= i < len(rows) and f in rows[i]
                    and str(rows[i][f] or '') == entry.get('original')):
                self.current[(d, i, f)] = entry
                if (entry.get('status') == 'Approved Translation' and str(entry.get('english', '')).strip()
                        and not entry.get('translation_excluded')):
                    self.approved[(d, i, f)] = entry
        self.fields = {}
        for d, rows in self.rows.items():
            identifier = getattr(mapping, f'{d}_id')
            names = [f for f in (rows[0] if rows else {}) if field_kind(f, vars(mapping), d) == 'account_name']
            self.fields[d] = identifier if identifier in names or not names else names[0]

    def account(self, dataset, row_id):
        rows = self.rows[dataset]
        if type(row_id) is not int or not 0 <= row_id < len(rows):
            return {}
        row, field = rows[row_id], self.fields[dataset]
        entry = self.approved.get((dataset, row_id, field), {})
        return {'record_id': digest([dataset, self.revisions[dataset], row_id, field]),
                'dataset': dataset, 'revision': self.revisions[dataset], 'row_id': row_id, 'field': field,
                'original_name': str(row.get(field) or ''), 'approved_english': entry.get('english', ''),
                'translation_status': self.current.get((dataset, row_id, field), {}).get('status', ''),
                'fields': dict(row)}

    def matching_signature(self):
        """Only matching inputs invalidate a run; draft/review-only edits do not."""
        return digest({'version': 3, 'revisions': self.revisions, 'mapping': vars(self.mapping),
                       'approved': sorted([list(key) + [entry['english']]
                                           for key, entry in self.approved.items()])})

    def variants(self, dataset, row_id):
        account = self.account(dataset, row_id)
        label = dataset.title()
        output = [(f'Original {label}', account.get('original_name', ''), None)]
        if account.get('approved_english'):
            output.append((f'Translated {label}', account['approved_english'],
                           self.approved[(dataset, row_id, account['field'])]))
        return output

    def matched_source(self, result):
        """Resolve an actual local/research/reviewer association, never a fuzzy fallback."""
        if result.selected_source:
            selected = result.selected_source
            if selected.get('dataset') != self.source_selection_fingerprint:
                return {}
            return self._source(selected)
        if result.recommendation_status == 'Proposed' and result.recommended_source_account:
            hits = [s for s in result.suggested_matches if s.get('mapping_supported') and
                    s.get('account') == result.recommended_source_account]
            if not hits:
                hits = [c for c in result.candidates if c.get('account') == result.recommended_source_account]
            return self._source(hits[0]) if len(hits) == 1 else {}
        if result.match_status in ('Exact', 'Normalized', 'Alias', 'Relationship', 'Company suffix', 'Name equivalent', 'Translation-assisted', 'Secondary validated') and result.candidates:
            return self._source(result.candidates[0])
        return {}

    def _source(self, candidate):
        account = self.account('source', candidate.get('source_row'))
        if account and str(account['fields'].get(self.mapping.source_id) or '') == candidate.get('account'):
            return account
        return {}

    def attach(self, results):
        """Refresh display/search context only; never change decisions or evidence."""
        for result in results:
            master = self.account('master', result.row_id)
            if not master or str(master['fields'].get(self.mapping.master_id) or '') != result.identifier:
                result.account_context = {}
                continue
            sources = [self.account('source', c.get('source_row')) for c in result.candidates[:3]]
            # Candidate identities must still correspond to this upload, not a historic position.
            sources = [s for s, c in zip(sources, result.candidates[:3]) if s and
                       str(s['fields'].get(self.mapping.source_id) or '') == c.get('account')]
            result.account_context = {'master': master, 'sources': sources,
                                      'source_name_field': self.fields['source'],
                                      'matched_source': self.matched_source(result)}
        return results


def approved_context_signature(context):
    """Compare approved research inputs without treating pending drafts as approved."""
    accounts = [context.get('master', {}), *context.get('sources', []), context.get('matched_source', {})]
    return digest(sorted({(a.get('record_id', ''), a['approved_english']) for a in accounts if a.get('approved_english')}))
