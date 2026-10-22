from .models import valid, normalize
from .storage import now


def suggestion_version(result, payload):
    from .storage import digest
    return digest({'source': payload.get('source'), 'mapping': payload.get('mapping'), 'record': result.dict()})


def source_suggestion(result, payload, source_row):
    """Resolve a Top 3 suggestion against the uploaded Source, never its cached value."""
    if type(source_row) is not int:
        raise ValueError('Choose an available suggested Source record.')
    candidate = next((c for c in result.candidates[:3] if c.get('source_row') == source_row), None)
    rows = payload.get('source', [])
    if candidate is None or not 0 <= source_row < len(rows):
        raise ValueError('The suggested Source record is no longer available. Reload this account.')
    mapping = payload['mapping']
    row = rows[source_row]
    name = '' if row[mapping['source_id']] is None else str(row[mapping['source_id']])
    value = '' if row[mapping['source_value']] is None else str(row[mapping['source_value']])
    if name != candidate.get('account'):
        raise ValueError('The suggested Source identity changed. Reload this account.')
    from .storage import digest
    return {'source_row': source_row, 'account': name, 'value': value,
            'similarity': candidate.get('similarity'),
            'dataset': digest({'source': rows, 'mapping': mapping})}


def validate_suggestion_approval(result, payload, selection):
    if not valid(selection['value']) or not normalize(selection['account']):
        raise ValueError('The selected Source record has no valid comparison value or identifier.')
    if result.recommendation_status == 'Insufficient Evidence':
        raise ValueError('Insufficient evidence. Investigate this account or use individual Manual review.')
    if result.recommendation_status == 'Proposed':
        reason = bulk_approval_error(result, payload)
        if reason:
            raise ValueError(reason)
    mapping = payload['mapping']
    values = {str(row[mapping['source_value']] or '') for row in payload['source']
              if normalize(row[mapping['source_id']]) == normalize(selection['account'])}
    if len(values) != 1:
        raise ValueError('Conflicting Source values require individual Manual investigation.')


def bulk_approval_error(result, payload):
    """Check evidence without changing the saved proposal or making provider calls."""
    from copy import deepcopy
    import polars as pl
    from .models import Mapping
    from .research import Researcher, ResearchSettings

    if not valid(result.proposed):
        return 'No valid proposed value; review this account individually.'
    if result.recommendation_status == 'Insufficient Evidence':
        return 'Insufficient evidence; review this account individually.'
    if result.recommendation_status == 'Proposed':
        checked = deepcopy(result)
        checked.decision, checked.review_status = '', 'Pending'
        settings = ResearchSettings(**payload.get('research_settings', {}))
        Researcher(None, '', settings=settings).evaluate_saved(
            checked, pl.DataFrame(payload['source'], infer_schema_length=None),
            Mapping(**payload['mapping']), payload.get('context', ''),
            snapshot=result.research_snapshot or {'source_context': None})
        if (checked.recommendation_status != 'Proposed' or
                checked.proposed != result.proposed or result.ai_proposed != result.proposed or
                checked.recommended_source_account != result.recommended_source_account):
            return 'Saved AI evidence does not support the current proposal.'
    elif result.identity_confidence != 'Reliable local match':
        return 'No reliable local match or supported AI recommendation; review individually.'
    return ''


def manual_options(source, column, candidates=()):
    """Distinct valid Source values, with suggested values first for easy review."""
    values = [c.get('value', '') for c in candidates] + source[column].to_list()
    options, seen = [], set()
    for value in values:
        text = str(value or '').strip()
        key = text.casefold()
        if valid(text) and key not in seen:
            options.append(text)
            seen.add(key)
    return options


def final_value(result):
    if not valid(result.final):
        return ''
    if result.decision in ('Approve', 'Approve proposal', 'Manual', 'Manual value', 'Retain original'):
        return result.final
    if (result.decision == 'Reject' and valid(result.verified_original) and
            normalize(result.final) == normalize(result.verified_original)):
        return result.verified_original
    return ''


def legacy_auto_finalized(result):
    """Flag retained legacy data for review; never invent or modify a decision."""
    return bool(not result.decision and valid(result.final) and (
        result.review_status == 'Verified unchanged' or
        (result.identity_confidence == 'Reliable local match' and
         normalize(result.final) in (normalize(result.proposed), normalize(result.original)))))


def decide(result, action, reviewer, notes='', manual_value='', source_value='', source_values=(), selected_source=None):
    if not reviewer.strip():
        raise ValueError('Enter a reviewer name.')
    action = {'Approve proposal': 'Approve', 'Manual value': 'Manual'}.get(action, action)
    custom = manual_value.strip()
    if action == 'Manual' and not custom and source_value and source_value not in source_values:
        raise ValueError('Choose a valid value from the uploaded Source file.')
    # Only retain independently saved verification; matching is not human approval.
    verified_original = result.verified_original
    choices = {'Approve': selected_source['value'] if selected_source else result.proposed, 'Retain original': result.original,
               'Manual': custom or source_value, 'Reject': verified_original, 'Pending': ''}
    if action not in choices:
        raise ValueError('Unknown review action.')
    value = choices[action]
    if action == 'Approve' and result.recommendation_status == 'Proposed' and result.proposed != result.ai_proposed:
        raise ValueError('The current proposal does not match the saved AI recommendation.')
    if action not in ('Reject', 'Pending') and not valid(value):
        raise ValueError('A final value must be a real value, not a placeholder.')
    before = result.dict()
    result.selected_source = dict(selected_source) if action == 'Approve' and selected_source else {}
    result.final = (value if action == 'Approve' else value.strip()) if valid(value) else ''
    if (action in ('Approve', 'Manual', 'Retain original') and valid(result.original)
            and normalize(result.final) == normalize(result.original)):
        verified_original = result.original
    result.verified_original = verified_original
    result.decision = action
    result.review_status = {'Reject': 'Rejected', 'Pending': 'Pending', 'Manual': 'Manually Verified'}.get(action, 'Approved')
    if result.recommendation_status == 'Proposed' and valid(result.ai_proposed):
        if action == 'Approve' and not selected_source:
            result.review_status = 'Approved — AI Recommendation'
        elif action == 'Reject':
            result.review_status = 'Rejected — AI Recommendation'
    if action == 'Approve' and selected_source:
        result.value_origin = 'reviewer-selected source'
    elif action == 'Manual':
        result.value_origin = 'custom entry' if custom else 'source dropdown'
    else:
        result.value_origin = ('AI recommendation' if action == 'Approve' and result.ai_proposed else
            'source proposal' if action == 'Approve' else 'verified original' if result.final else '')
    result.notes, result.reviewer, result.reviewed_at = notes.strip(), reviewer.strip(), now()
    return {'row_id': result.row_id, 'identifier': result.identifier, 'original': result.original,
            'proposed': result.proposed, 'approved_value': result.final, 'decision': action,
            'reviewer': result.reviewer, 'notes': result.notes, 'timestamp': result.reviewed_at,
            'evidence': result.evidence, 'previous_decision': before['decision'], 'previous_final': before['final'],
            'new_final': result.final, 'review_status': result.review_status, 'value_origin': result.value_origin,
            'ai_proposed': result.ai_proposed, 'ai_recommended_source_account': result.recommended_source_account,
            'ai_recommendation_status': result.recommendation_status, 'ai_reasoning': result.recommendation_reasoning,
            'research_explanation': result.explanation, 'research_timestamp': result.researched_at,
            'verified_facts': result.verified_facts, 'suggested_matches': result.suggested_matches,
            'mapping_policy': result.mapping_policy, 'selected_source': result.selected_source,
            'translation_provenance': result.translation_provenance,
            'previous_selected_source': before['selected_source']}
