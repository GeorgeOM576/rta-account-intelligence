"""Table-first, Google-only translation workspace; human decisions stay separate."""
from pathlib import Path
import hashlib
from uuid import uuid4
import pandas as pd
import streamlit as st

from .selection_state import consume_editor
from .storage import digest
from .translation import TranslationEngine, STATUSES, DATASETS, translation_metrics, detection_options
from .translation_providers import GoogleTranslationProvider, ArgosProvider, OpenAIProvider
from .translation_workspace import TranslationWorkspace, row_id, selection_locations
from .google_detection import provider_for, cached_result
from .export import workbook
from .models import Result
from . import translation_diagnostics as trace

LOADED_BUILD = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def metrics(engine):
    records = engine.records()
    if records:
        st.markdown('**Translation Intelligence · Master, Source and combined**')
        rows = translation_metrics(records)
        if any(r.get('detection_provider') == 'google' for r in records):
            rows = [{key.replace('Confident English', 'English').replace('Confident Non-English', 'Non-English'): value
                     for key, value in row.items()} for row in rows]
        st.dataframe(rows, hide_index=True, width='stretch')



def translation_block_reason(selected, preview):
    if not selected:
        return 'Select at least one account.'
    if preview['unique_texts']:
        return ''
    reasons = []
    if any(r.get('english') for r in selected):
        reasons.append('Existing drafts and approved translations are not retransmitted; review them instead.')
    if any(r['language'] == 'en' for r in selected):
        reasons.append('English names do not need translation.')
    if preview['eligibility']['blocked_language_records']:
        reasons.append('Detect or confirm missing languages, including unsupported source languages, in individual review.')
    if preview['eligibility']['excluded_records']:
        reasons.append('Excluded fields are not eligible for translation.')
    if any(r['status'] == 'Rejected Translation' for r in selected):
        reasons.append('Rejected drafts need individual review or source-language confirmation before translating again.')
    return 'No selected rows are ready for translation. ' + ' '.join(reasons or ['Review their translation status and confirm a supported non-English source language.'])


def render(store, project, credential):
    engine = TranslationEngine(store, project)
    payload = store.load(project)
    # One-time preparation is cache-only. Preserve previously selected fields.
    fields = {}
    for d in DATASETS:
        names = [f for f in payload.get(f'{d}_schema', {}) if detection_options(payload, d, f)[0] == 'account_name']
        mapped = payload.get('mapping', {}).get(d + '_id')
        primary = [mapped] if mapped in names else names[:1]
        fields[d] = list(dict.fromkeys([*payload.get('translation_fields', {}).get(d, []), *primary]))
    if provider_for(payload) != 'google':
        engine.select_detection_provider('google', preserve_drafts=True)
        payload = store.load(project)
    if fields != payload.get('translation_fields', {}):
        engine.detect(fields, return_records=False, preserve_drafts=True)
    workspace = TranslationWorkspace(engine)
    prefix = f'translation_workspace_{project}'
    previous_view = st.session_state.get(prefix + '_editor_view')
    if previous_view and 'identities' not in previous_view:
        previous_view['identities'] = [row_id(r) for r in previous_view['rows']]
    consume_editor(st.session_state, prefix + '_selection', prefix + '_editor_view')
    epoch = st.session_state.get(prefix + '_epoch', 0)
    selections = dict(st.session_state.setdefault(prefix + '_selection', {}))
    owner = st.session_state.setdefault(prefix + '_action_owner', uuid4().hex)
    receipt = trace.latest(store, project)
    # A progress yield can rerun the script before its local refresh executes.
    # Recover only this browser's completed action, never another reviewer's edits.
    if (receipt and receipt['owner'] == owner and receipt['status'] != 'running' and
            st.session_state.get(prefix + '_synced_action') != receipt['id']):
        if receipt.get('persisted'):
            import json
            from .translation import cell_key
            with store.connect() as db:
                for key, old in list(selections.items()):
                    if key in receipt['affected']:
                        row = db.execute('SELECT payload FROM translations WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                                         (project, *cell_key(old))).fetchone()
                        if row:
                            selections[key] = json.loads(row[0])
        epoch += 1
        st.session_state[prefix + '_epoch'] = epoch
        st.session_state[prefix + '_selection'] = selections
        st.session_state.pop(prefix + '_editor_view', None)
        st.session_state[prefix + '_refresh_action'] = receipt['id']
        st.session_state[prefix + '_synced_action'] = receipt['id']
    valid = workspace.selected(selections)
    selections = {row_id(r): r for r in valid}
    st.session_state[prefix + '_selection'] = selections

    def refresh(message, affected=None, failed=False):
        # Update selected snapshots only for changes made by this UI action.
        with store.connect() as db:
            import json
            from .translation import cell_key
            for key, old in list(selections.items()):
                if affected is not None and key not in affected:
                    continue
                row = db.execute('SELECT payload FROM translations WHERE project=? AND dataset=? AND revision=? AND row_id=? AND field=?',
                                 (project, *cell_key(old))).fetchone()
                if row:
                    selections[key] = json.loads(row[0])
        st.session_state[prefix + '_selection'] = selections
        st.session_state[prefix + '_epoch'] = epoch + 1
        if message is not None:
            st.session_state[prefix + '_notice'] = {'message': message, 'failed': failed}
        st.session_state.pop(prefix + '_export', None)
        st.rerun()

    st.subheader('Account translations')
    st.caption('Original names remain unchanged. English translations are drafts until approved.')
    if receipt and receipt['status'] == 'running':
        st.info(receipt['message'])
    if (receipt and receipt['owner'] == owner and receipt['status'] != 'running' and
            st.session_state.get(prefix + '_shown_action') != receipt['id']):
        (st.warning if receipt['status'] == 'failed' else st.success)(receipt['message'])
        st.session_state[prefix + '_shown_action'] = receipt['id']
    notice = st.session_state.pop(prefix + '_notice', None)
    if notice:
        if isinstance(notice, dict):
            (st.warning if notice.get('failed') else st.success)(notice['message'])
        else:
            st.success(notice)
    left, middle, right = st.columns([2, 1, 1])
    search = left.text_input('Search accounts', key=prefix + '_search')
    dataset = middle.selectbox('Translation dataset', ['All', 'Master', 'Source'], key=prefix + '_dataset')
    status = right.selectbox('Translation status', ['All', *STATUSES], key=prefix + '_status')
    page_size = st.selectbox('Rows per page', [25, 50, 100], key=prefix + '_size')
    filter_key = digest([dataset, status, search, page_size, workspace.revisions])
    rows, total, _ = workspace.page(dataset, search, status, size=page_size)
    page_key = prefix + '_page_' + filter_key
    max_page = max(1, (total + page_size - 1) // page_size)
    if st.session_state.get(page_key, 1) > max_page:
        st.session_state[page_key] = max_page
    page = st.number_input('Translation page', min_value=1, max_value=max_page,
                           step=1, key=page_key)
    rows, total, page = workspace.page(dataset, search, status, page, page_size)
    # Upgrade only visible automatic metadata, using cached responses, never APIs.
    if any(r.get('detection_policy') != detection_options(workspace.payload, r['dataset'], r['field'])[3] or
           (not r.get('google_language') and cached_result(store, project, r['original'])) for r in rows):
        engine.detect(workspace.payload.get('translation_fields', {}), force=True,
                      texts={r['original'] for r in rows}, return_records=False, preserve_drafts=True)
        rows, total, page = workspace.page(dataset, search, status, page, page_size)
    selection_caption = st.empty()
    a, b, c = st.columns(3)
    if a.button('Select all visible rows', disabled=not rows):
        selections.update({row_id(r): r for r in rows})
        st.session_state[prefix + '_epoch'] = epoch + 1
        st.rerun()
    if b.button('Clear selection', disabled=not selections):
        st.session_state[prefix + '_selection'] = {}
        st.session_state[prefix + '_epoch'] = epoch + 1
        st.rerun()
    if c.button('Export to Excel'):
        current = store.load(project)
        st.session_state[prefix + '_export'] = workbook(
            [Result(**r) for r in current.get('results', [])], store.audit(project), current.get('conflicts', []),
            len(current.get('source', [])), translations=engine.export_records(), datasets=current)
    if prefix + '_export' in st.session_state:
        st.download_button('Download Excel', st.session_state[prefix + '_export'], 'rta-translations.xlsx',
                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    table_rows = [{'Select': row_id(r) in selections, 'Dataset': r['dataset'].title(),
        'Original Company Name': r['original'], 'Detected Language': r['language'] if r.get('language_confirmed') else r.get('detected_language', r['language']),
        'English Translation': r.get('english', ''), 'Translation Status': r['status'],
        'Review advice': ('Language confirmed by reviewer' if r.get('language_confirmed') else
                         r.get('language_review_reason', '') if r.get('language_review_required') else ''),
        'Individual action': 'None'} for r in rows]
    columns = ['Select', 'Dataset', 'Original Company Name', 'Detected Language', 'English Translation',
               'Translation Status', 'Review advice', 'Individual action']
    # Freeze the editor's input for its generation. Rebuilding its baseline with
    # selected=True on each checkbox edit resets browser deltas and loses rows.
    fingerprint = digest([filter_key, page, epoch, rows])
    view = st.session_state.get(prefix + '_editor_view')
    if not view or view['fingerprint'] != fingerprint:
        serial = st.session_state.get(prefix + '_editor_serial', 0) + 1
        st.session_state[prefix + '_editor_serial'] = serial
        view = {'fingerprint': fingerprint, 'key': prefix + f'_table_{serial}_' + fingerprint,
                'rows': rows, 'identities': [row_id(r) for r in rows], 'data': table_rows}
        st.session_state[prefix + '_editor_view'] = view
    editor_key = view['key']
    edited = st.data_editor(pd.DataFrame(view['data'], columns=columns), hide_index=True, width='stretch',
        disabled=['Dataset', 'Original Company Name', 'Detected Language', 'Translation Status', 'Review advice'],
        column_config={'Select': st.column_config.CheckboxColumn('Select'),
                       'Individual action': st.column_config.SelectboxColumn('Individual action', options=['None', 'Approve', 'Reject'])},
        key=editor_key, on_change=consume_editor,
        args=(st.session_state, prefix + '_selection', prefix + '_editor_view', editor_key, True))
    refreshed_action = st.session_state.pop(prefix + '_refresh_action', None)
    if refreshed_action:
        with trace.scope(refreshed_action):
            trace.event('table_refresh_completed')
    consume_editor(st.session_state, prefix + '_selection', prefix + '_editor_view', editor_key)
    selections = dict(st.session_state.get(prefix + '_selection', {}))
    selected = list(selections.values())
    selection_caption.caption(f'{total:,} accounts · Page {page} · {len(selected):,} selected across pages')

    st.subheader('Detect Languages')
    limit = st.number_input('Names per batch', min_value=1, max_value=5000, value=250, key=prefix + '_limit')
    detection_filters = dict(dataset=dataset, search=search, status=status, selection=selected if selected else None)
    plan = workspace.detection_plan(limit, **detection_filters)
    scope_label = 'selected' if selected else dataset if dataset != 'All' else 'Master and Source'
    st.caption(f"Detect languages for {plan['records_in_scope']:,} {scope_label} records · {plan['pending_texts']:,} unique names requiring detection · {plan['cached_texts']:,} already cached")
    if selected:
        st.caption('Only checked rows matching the current filters are included; hidden selections are excluded.')
    if not plan['batch_size']:
        if not plan['records_in_scope']:
            st.info('No checked accounts match the current filters.' if selected else 'No accounts match the current filters.')
        elif plan['unique_texts'] and plan['cached_texts'] == plan['unique_texts']:
            st.info('All eligible names in this scope are already cached. No Google requests are needed.')
        else:
            st.info('No uncached eligible names remain: records are reviewed, excluded or exceed the supported text length.')
    st.caption(f"{plan['total_unique_selected_texts'] - plan['pending_texts']:,} of {plan['total_unique_selected_texts']:,} names processed · {plan['pending_texts']:,} remaining")
    detection_scope = digest([workspace.revisions, plan, epoch, dataset, search, status, sorted(selections)])
    with st.form(prefix + '_detect_' + detection_scope):
        st.write(f"{plan['batch_size']:,} names · Estimated cost: ${plan['estimated_usd']:.6f} USD before credits")
        consent = st.checkbox('I authorize this detection batch and its estimated cost.')
        if st.form_submit_button('Detect Languages', disabled=not plan['batch_size'], type='primary'):
            try:
                progress = st.progress(0.0, text='Detecting languages…')
                report = workspace.run_detection(limit, consent,
                    lambda value, **kwargs: progress.progress(value, text=f"{round(value * plan['batch_size'])} of {plan['batch_size']} names processed"),
                    **detection_filters, preview=plan)
                refresh(f"Languages detected: {report['successful']:,}. Failed: {report['failed']:,}. Review the refreshed table.")
            except (ValueError, RuntimeError):
                st.error('Detection was not completed. Confirm this batch; if already confirmed, check Google access and retry.')

    st.subheader('Translate Selected Accounts')
    st.caption('Select account rows above. Unknown or unsupported languages need confirmation in Review and Approval. Existing drafts and approvals are preserved.')
    provider = GoogleTranslationProvider()
    preview = engine.plan(list(DATASETS), provider, allow_names=True, limit=limit, selection=selected)
    from .translation import translation_eligible
    eligible = [r for r in selected if translation_eligible(r) and not r.get('english')]
    identities = set(preview['identities'])
    batch = [r for r in eligible if (r['original'], r['language']) in identities]
    remaining = [r for r in eligible if (r['original'], r['language']) not in identities]
    skipped = len(selected) - len(eligible)
    translate_scope = digest([selected, preview, limit, epoch])
    # Keep the submit's identity stable when a browser sends selection/limit
    # edits with a click. Only consent is scoped to the exact preview.
    with st.form(prefix + '_translate'):
        st.write(f"{preview['unique_texts']:,} selected names · Estimated cost: ${preview['estimated_usd']:.6f} USD before credits (up to ${preview['estimated_usd'] * provider.max_attempts:.6f} with retries)")
        st.caption(f'{len(selected):,} selected records · {len(batch):,} in this batch · {skipped:,} skipped · {len(remaining):,} remaining after this batch.')
        if remaining:
            st.caption(f'This batch: {selection_locations(batch)}. Remaining: {selection_locations(remaining)}.')
        consent = st.checkbox('I authorize this translation batch, its estimated cost and retries.',
                              key=prefix + '_translate_consent_' + translate_scope)
        if st.form_submit_button('Translate Selected', type='primary', key=prefix + '_translate_submit'):
            action_id = uuid4().hex
            try:
                from collections import Counter
                from .translation import translation_eligible
                exclusions = Counter()
                for item in selected:
                    if translation_eligible(item) and not item.get('english'):
                        continue
                    reason_key = ('existing_draft_or_approval' if item.get('english') else
                                  'excluded_field' if item.get('translation_excluded') else
                                  'english' if item['language'] == 'en' else
                                  'missing_or_unsupported_language' if item['status'] == 'Uncertain' or item['language'] == 'und' else
                                  'rejected' if item['status'] == 'Rejected Translation' else 'other')
                    exclusions[reason_key] += 1
                with trace.scope(action_id):
                    trace.event('submission_received', selected_rows=len(selected),
                                eligible_rows=preview['eligibility']['eligible_records'],
                                excluded_rows=sum(exclusions.values()), excluded_reasons=dict(exclusions),
                                authorized=bool(consent))
                reason = translation_block_reason(selected, preview)
                if reason:
                    st.warning(reason)
                elif not consent:
                    st.error('Authorize this translation batch first. If the selection or cost preview changed, confirm the new batch and click Translate Selected again.')
                else:
                    affected = {row_id(r) for r in selected if translation_eligible(r) and not r.get('english') and
                                (r['original'], r['language']) in preview['identities']}
                    action = trace.begin(store, project, owner, affected, action_id)
                    if action is None:
                        st.warning('A translation batch is already processing. Please wait and refresh the table; no additional batch was started.')
                    else:
                        with trace.scope(action_id):
                            try:
                                st.progress(0.0, text=f'Generating drafts for {len(batch):,} selected accounts…')
                                # Streamlit progress is a cancellation/yield point.
                                # Persist ALL received responses before yielding again.
                                report = engine.process(list(DATASETS), GoogleTranslationProvider(consent=True), allow_names=True,
                                    limit=limit, selection=selected)
                            except Exception as error:
                                trace.event('action_failed', error_code=trace.error_code(error))
                                trace.finish(store, project, action_id,
                                    'Translation could not complete. Review the table and Google access before authorizing another batch.', failed=True)
                                raise
                            except BaseException:
                                trace.event('action_interrupted', error_code='interrupted')
                                trace.finish(store, project, action_id,
                                    'Translation was interrupted. Review the table before authorizing another batch; no automatic retry was made.', failed=True)
                                raise
                            message = f"{report['drafts']:,} translation drafts ready for review. {report['failed']:,} failed; {report['remaining_unique_texts']:,} selected names remaining."
                            committed = workspace.current(batch)
                            cached = sum(r['status'] == 'Translated — Review' and bool(r.get('cache_hit')) for r in committed)
                            message += f' {cached:,} cached/reused drafts; {skipped:,} skipped records.'
                            trace.finish(store, project, action_id, message, failed=bool(report['failed']), persisted=True)
                            trace.event('action_completed', drafts=report['drafts'], failed=report['failed'])
                        # No fallible UI/progress work between commit and rerun.
                        # The receipt handles selection reconciliation and creates
                        # exactly one fresh editor generation on the next render.
                        st.rerun()
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error('Translation could not complete. Check Google access and workspace storage. Some drafts may already be saved; refresh and review the table before authorizing another batch.')
    if not selected:
        st.info('Select at least one account.')
    elif not preview['unique_texts']:
        st.info(translation_block_reason(selected, preview))

    st.subheader('Review and Approval')
    st.caption('Use the table’s individual actions or review a row below. Bulk decisions affect only selected eligible drafts. Translation approval never sets Final Value.')
    if workspace.stale_selected:
        st.warning('Selected accounts changed in another session. Clear the selection and reselect after reviewing their updated values.')
    with st.form(prefix + '_decisions_' + digest([selected, rows, epoch])):
        reviewer = st.text_input('Translation reviewer', value=payload.get('reviewer_name', ''))
        confirmed = st.checkbox('I confirm the selected translation decisions and have verified the English names.')
        a, b, c = st.columns(3)
        apply_rows = a.form_submit_button('Apply individual actions and edits')
        approve = b.form_submit_button('Approve Selected', disabled=not selected)
        reject = c.form_submit_button('Reject Selected', disabled=not selected)
        if apply_rows or approve or reject:
            try:
                if not reviewer.strip() or not confirmed:
                    raise ValueError('Enter a reviewer and explicitly confirm the decisions.')
                if apply_rows:
                    # Build every change first; one atomic commit rejects stale rows.
                    changes = []
                    from .storage import now
                    for index, item in enumerate(rows):
                        value = edited.iloc[index]['English Translation']
                        english = value.strip() if isinstance(value, str) else ''
                        value = edited.iloc[index]['Individual action']
                        action = value if isinstance(value, str) else 'None'
                        if action not in ('None', 'Approve', 'Reject'):
                            raise ValueError('Choose a valid individual action.')
                        if english == item.get('english', '') and action == 'None':
                            continue
                        if item['status'] != 'Translated — Review' or not item.get('english'):
                            raise ValueError('Table edits and decisions accept only unapproved translation drafts. Use individual review for manual translations.')
                        from .language_detection import FOREIGN
                        from .google_languages import supported_language
                        if (item.get('translation_excluded') or item['language'] in ('en', 'und') or
                                supported_language(item['language']) is None or
                                not (item.get('language_confirmed') or item.get('detection_outcome') == FOREIGN)):
                            raise ValueError('Confirm a supported non-English source language before approving this draft.')
                        if not english:
                            raise ValueError('An English draft cannot be empty.')
                        if action == 'Approve' and item.get('draft_language_review_required'):
                            raise ValueError('Confirm this existing draft’s source language in individual review before approval.')
                        updated = {**item, 'english': english, 'correction': english != item['english'] or item.get('correction', False)}
                        if action == 'Approve':
                            updated.update(status='Approved Translation', reviewer=reviewer.strip(), reviewed_at=now())
                        elif action == 'Reject':
                            updated.update(status='Rejected Translation', draft_english=english, english='', reviewer=reviewer.strip(), reviewed_at=now())
                        changes.append((item, updated, {'event_type': 'translation_review', 'decision': action if action != 'None' else 'Correct draft',
                            'reviewer': reviewer.strip(), 'timestamp': now(), 'previous_translation': item, 'translation': updated}))
                    if not changes:
                        raise ValueError('Choose individual actions or edit draft translations in the table first.')
                    engine._commit_cells(changes)
                    count = len(changes)
                else:
                    eligible = [r for r in selected if r['status'] == 'Translated — Review' and r.get('english') and not r.get('translation_excluded')
                                and (not approve or not r.get('draft_language_review_required'))]
                    count = (engine.bulk_approve if approve else engine.bulk_reject)(eligible, reviewer, confirmed)
                affected = {row_id(r) for r, _, _ in changes} if apply_rows else {row_id(r) for r in eligible}
                refresh(f'Saved {count:,} translation decisions.', affected)
            except ValueError as error:
                st.error(str(error))
    if rows:
        index = st.selectbox('Translation to review', list(range(len(rows))),
            format_func=lambda i: f"{rows[i]['dataset'].title()} row {rows[i]['row_id'] + 1} · {rows[i]['field']} · {rows[i]['original'][:100]}",
            key=prefix + '_review_' + digest([filter_key, page]))
        item = rows[index]
        if item.get('english') and item['status'] != 'Approved Translation':
            st.caption('Changing the source language archives this draft. Select the account and translate again to generate a new draft.')
        with st.form(prefix + '_individual_' + digest(item)):
            english = st.text_area('Reviewed English translation', value=item.get('english', ''))
            language = st.text_input('Confirmed source-language code', value=item['language'])
            reviewer = st.text_input('Individual reviewer')
            confirmed = st.checkbox('I verified this translation preserves the correct entity, proper names, legal suffixes and identifiers.')
            a, b, c = st.columns(3)
            approve = a.form_submit_button('Approve translation')
            reject = b.form_submit_button('Reject translation draft', disabled=item['status'] != 'Translated — Review')
            language_save = c.form_submit_button('Save confirmed language', disabled=item['status'] == 'Approved Translation')
            if approve or reject or language_save:
                try:
                    if language_save:
                        if item.get('english') and language == item['language'] and not item.get('draft_language_review_required'):
                            raise ValueError('This draft already uses that language. Correct its English text or choose a different confirmed source language.')
                        engine.confirm_language(item, language, reviewer, confirmed)
                    elif reject:
                        engine.reject(item, reviewer, confirmed)
                    else:
                        from .google_languages import supported_language
                        if language in ('en', 'und') or supported_language(language) is None:
                            raise ValueError('Confirm a supported non-English source language before approving the translation.')
                        engine.approve(item, english, reviewer, confirmed, language)
                    refresh('Translation review saved.', {row_id(item)})
                except ValueError as error:
                    st.error(str(error))
