"""Streamlit entry point. Run with: streamlit run app.py"""
import json
import os
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
import polars as pl
import streamlit as st
from rta.models import Mapping, Result, AI_PENDING, MANUAL_REQUIRED, REVIEW_FILTERS, has_proposal
from rta.ingest import parse_file, identifier_stats
from rta.matching import Matcher
from rta.storage import Store, digest
from rta.research import Researcher, ResearchSettings, eligible
from rta.review import (manual_options, final_value, source_suggestion, suggestion_version,
                        validate_suggestion_approval, bulk_approval_error)
from rta.export import summary, result_row, workbook
from rta.selection_state import checkbox_changed, set_checked, select_group
from rta.workflow_table import visible_table
from rta.recommendations import INSUFFICIENT
from rta.relationships import POLICIES
from rta.ui import apply_brand, logo, header, status_badge, confidence_indicator, bulk_review_notice
from rta.translation import TranslationEngine, default_fields, revision
from rta.translation_matching import reconcile, retain_reviewed
from rta.approved_names import ApprovedNames, approved_context_signature
from rta.translation_ui import render as translation_section, metrics as translation_metrics_section
from rta.language_detection import runtime_info as detection_runtime_info
from rta.google_detection import provider_for, google_runtime_info
from rta.translation_runtime import stale_translation_modules

apply_brand()

with st.sidebar:
    logo(sidebar=True)
    st.caption('ACCOUNT INTELLIGENCE · MVP V3')
    with st.container(key='redthread_navigation'):
        page = st.radio('Workspace', ['Dashboard', 'How to Use RTA', 'Upload Data', 'Configure Reconciliation',
                'Translation Intelligence', 'Run Reconciliation', 'AI Research', 'Review & Approvals', 'Export Results', 'Settings'])

if page == 'How to Use RTA':
    # The static guide must not initialize or load a workspace/database.
    from rta.help_ui import render as render_help
    header()
    render_help()
    st.stop()

stale_modules = stale_translation_modules()
if stale_modules:
    st.error('Streamlit has outdated Translation Intelligence modules loaded. Stop and restart Streamlit from this project, '
             'then resume your workspace. Refreshing the browser alone does not reload cached Python modules. '
             'Exports are blocked until restart; existing data and reviews are preserved.')
    st.code('\n'.join(stale_modules))
    st.stop()


def credential(name):
    value = os.environ.get(name, '')
    if value:
        return value
    try:
        return str(st.secrets.get(name, ''))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return ''


store = Store(os.environ.get('RTA_DB_PATH', 'data/rta.sqlite3'))
if 'project' not in st.session_state:
    st.session_state.project, st.session_state.token = store.create()
    st.session_state.payload = {}


def save():
    store.save(st.session_state.project, st.session_state.payload)


def restore_results():
    return [Result(**r) for r in st.session_state.payload.get('results', [])]


def checkpoint(results):
    st.session_state.payload['results'] = [r.dict() for r in results]
    save()


with st.sidebar:
    st.divider()
    st.caption('Your workspace is isolated by a private resume token.')
    with st.expander('Save / resume workspace'):
        st.download_button('Download private resume token',
            json.dumps({'project': st.session_state.project, 'token': st.session_state.token}),
            'rta-resume-token.json', 'application/json')
        token_upload = st.file_uploader('Resume token', type=['json'])
        if st.button('Resume saved workspace'):
            try:
                identity = json.loads(token_upload.getvalue()) if token_upload else {}
                if not store.authenticate(identity.get('project', ''), identity.get('token', '')):
                    raise ValueError('Invalid token or workspace not found on this server.')
                st.session_state.project, st.session_state.token = identity['project'], identity['token']
                st.session_state.payload = store.load(identity['project'])
                st.rerun()
            except (ValueError, TypeError, KeyError):
                st.error('Invalid token or workspace not found on this server.')
    if st.button('Create new workspace'):
        st.session_state.project, st.session_state.token = store.create()
        st.session_state.payload = {}
        st.rerun()
    st.caption('Local SQLite · human approval required')

# SQLite is authoritative on every rerun, including navigation and export.
st.session_state.payload = store.load(st.session_state.project)
payload = st.session_state.payload
results = restore_results()
master = pl.DataFrame(payload['master'], schema={c: pl.String for c in payload['master_schema']}) if 'master' in payload else None
source = pl.DataFrame(payload['source'], schema={c: pl.String for c in payload['source_schema']}) if 'source' in payload else None
# Validate saved UI configuration before name hydration or local execution.
# Missing/stale columns must not become a generic matching failure or success.
mapping = None
mapping_error = 'Save your column mapping on Configure Reconciliation.'
if payload.get('mapping'):
    try:
        candidate_mapping = Mapping(**payload['mapping'])
    except TypeError:
        mapping_error = 'The saved column mapping is incomplete. Check Configure Reconciliation before running local matching.'
    else:
        missing_mapping_fields = [f'{dataset.title()} {kind}: {getattr(candidate_mapping, dataset + "_" + kind)}'
            for dataset, frame in [('master', master), ('source', source)] for kind in ('id', 'value')
            if frame is None or not isinstance(getattr(candidate_mapping, dataset + '_' + kind), str)
            or getattr(candidate_mapping, dataset + '_' + kind) not in frame.columns]
        if missing_mapping_fields:
            mapping_error = 'The saved mapping refers to unavailable columns (' + '; '.join(missing_mapping_fields) + '). Check Configure Reconciliation before running local matching.'
        else:
            mapping, mapping_error = candidate_mapping, ''
# Resolve approved SQLite records afresh on navigation, without copying draft text.
if mapping and master is not None and source is not None and page in ('Run Reconciliation', 'AI Research', 'Review & Approvals', 'Export Results'):
    approved_entries = TranslationEngine(store, st.session_state.project).records()
    current_names = ApprovedNames(payload, mapping, approved_entries)
    if page == 'Review & Approvals':
        # Current display context must not alter the persisted versions used by atomic review checks.
        review_display = current_names.attach([Result(**vars(r)) for r in results])
        review_display = {r.row_id: r for r in review_display}
    else:
        current_names.attach(results)
header()
st.subheader(page)


if results and mapping and master is not None and source is not None and page in ('AI Research', 'Review & Approvals', 'Export Results'):
    if payload.get('reconciliation_translation_signature') != current_names.matching_signature():
        st.warning('Reconciliation results are stale: approved translation inputs changed, or this run has no recorded translation snapshot. '
                   'Current translations are shown below. Run automatic local matching to refresh candidates and Match Basis. '
                   'Existing human decisions and audit history will be preserved.')
    if any(r.research_snapshot and approved_context_signature(r.research_snapshot.get('approved_name_context', {})) !=
           approved_context_signature(review_display[r.row_id].account_context if page == 'Review & Approvals' else r.account_context) for r in results):
        st.warning('Saved AI research used different approved translation inputs. Current names are shown; review saved evidence or explicitly authorize fresh research. '
                   'No research is run automatically, and existing human decisions are preserved.')


def datasets_ready():
    if master is None or source is None:
        st.info('Upload a Master and Source dataset to begin, or load the synthetic example on Upload Data.')
        return False
    return True


def results_ready():
    if not results:
        st.info('Run a reconciliation to populate this workspace.')
        return False
    return True


def research_sections(record, show_candidates=True, show_tables=True):
    st.markdown('**Verified Facts**')
    if record.verified_facts:
        for fact in record.verified_facts:
            st.write(f"{fact['subject']} → {fact['relationship']} → {fact['entity']}")
            st.text(fact['quote'])
            for i, url in enumerate(fact['evidence_urls'], 1):
                if urlparse(url).scheme in ('http', 'https'):
                    st.link_button(f"Fact evidence {i} · {fact['entity']}", url)
    else:
        st.caption('No independently grounded entity facts were saved. Similar names are suggestions only.')
    st.markdown('**Suggested Matches**')
    st.caption('Local similarity suggestions do not establish identity or corporate relationships.')
    if show_candidates:
        st.dataframe(record.candidates, hide_index=True, width='stretch')
    if record.suggested_matches:
        st.caption('Evidence-backed entities found across the entire Source file')
        if show_tables:
            st.dataframe(record.suggested_matches, hide_index=True, width='stretch')
        else:
            for suggestion in record.suggested_matches[:3]:
                st.write(f"{suggestion.get('account', '')} — {suggestion.get('value', '')}")
            if len(record.suggested_matches) > 3:
                st.caption(f'{len(record.suggested_matches)} evidence-backed suggestions are retained in the workspace and export.')
    if show_candidates:
        a, b, c = st.columns(3)
        a.metric('Original value', record.original or '—', border=True)
        b.metric('Intelligence Proposed Value', record.proposed if has_proposal(record) else '—', border=True)
        c.metric('Final value', final_value(record) or '—', border=True)
    st.markdown('**Recommendation Decision**')
    st.write(record.recommendation_status if record.recommendation_status != 'Insufficient Evidence' else INSUFFICIENT)
    st.write(record.recommendation_reasoning or 'No research recommendation is available yet.')
    if record.secondary_validation:
        st.caption('Secondary validation: ' + record.secondary_validation['status'])
        st.write(record.secondary_validation['reason'])
    st.caption(f"Organization mapping policy: {record.mapping_policy or POLICIES[0]} · Reviewer status: {record.status_label}")


def load_pair(master_bytes, master_name, source_bytes, source_name):
    first, second = parse_file(master_bytes, master_name), parse_file(source_bytes, source_name)
    payload.update(master=first.to_dicts(), source=second.to_dicts(),
                   master_schema={c: 'String' for c in first.columns},
                   source_schema={c: 'String' for c in second.columns},
                   master_name=master_name, source_name=source_name)
    save()
    TranslationEngine(store, st.session_state.project).detect({d: default_fields(payload, d) for d in ('master', 'source')})


if page == 'Dashboard':
    if results_ready():
        metrics = summary(results)
        metrics['Total Source Records'] = source.height
        items = list(metrics.items())
        for start in range(0, len(items), 4):
            for column, (label, value) in zip(st.columns(4), items[start:start+4]):
                column.metric(label, value, border=True)
        left, right = st.columns(2)
        with left:
            st.markdown('**Local matching distribution**')
            counts = Counter(r.match_status for r in results)
            st.bar_chart(pl.DataFrame({'Status': list(counts), 'Records': list(counts.values())}), x='Status', y='Records')
        with right:
            st.markdown('**Review progress**')
            completed = sum(r.status_label not in (AI_PENDING, MANUAL_REQUIRED) for r in results)
            st.progress(completed / len(results), text=f'{completed} of {len(results)} reviewed or verified')
            counts = Counter(r.research_status for r in results)
            st.dataframe([{'Research status': k, 'Records': v} for k, v in counts.items()], hide_index=True)
    else:
        st.markdown('Upload two datasets, map your columns, and run local matching. Investigate ambiguous accounts and approve corrections before export.')
    translation_metrics_section(TranslationEngine(store, st.session_state.project))

elif page == 'Upload Data':
    if results:
        st.info('This run is saved. Create a new workspace to use different files; existing decisions and audit history remain in this workspace.')
    else:
        left, right = st.columns(2)
        master_file = left.file_uploader('Master file', type=['csv', 'xlsx'])
        source_file = right.file_uploader('Source file', type=['csv', 'xlsx'])
        if st.button('Import uploaded datasets', type='primary', disabled=not (master_file and source_file)):
            try:
                load_pair(master_file.getvalue(), master_file.name, source_file.getvalue(), source_file.name)
                payload.pop('mapping', None)
                save()
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        if st.button('Load synthetic example'):
            load_pair(Path('samples/master.csv').read_bytes(), 'master.csv', Path('samples/source.csv').read_bytes(), 'source.csv')
            payload.pop('mapping', None)
            save()
            st.rerun()
    if datasets_ready():
        for title, frame, name, id_col in [('Master', master, payload['master_name'], mapping.master_id if mapping else None),
                                          ('Source', source, payload['source_name'], mapping.source_id if mapping else None)]:
            with st.expander(f'{title} · {name} · {frame.height:,} records · {frame.width} columns', expanded=True):
                st.write('Columns: ' + ', '.join(frame.columns))
                st.dataframe(frame.head(25), hide_index=True, width='stretch')
                st.dataframe([{'Column': c, 'Missing values': frame.select(pl.col(c).cast(pl.Utf8).fill_null('').str.strip_chars().eq('').sum()).item()}
                    for c in frame.columns], hide_index=True)
                if id_col:
                    st.write(identifier_stats(frame, id_col))
                else:
                    st.caption('Map identifiers to see duplicate statistics.')

elif page == 'Configure Reconciliation':
    if datasets_ready():
        if results:
            st.info('Configuration is locked for this saved run. Create a new workspace for a different mapping.')
            st.json(payload['mapping'])
        else:
            with st.form('mapping'):
                left, right = st.columns(2)
                mi = left.selectbox('Master identifier', master.columns, index=master.columns.index(mapping.master_id) if mapping else 0)
                si = right.selectbox('Source identifier', source.columns, index=source.columns.index(mapping.source_id) if mapping else 0)
                mv = left.selectbox('Master comparison field', master.columns, index=master.columns.index(mapping.master_value) if mapping else min(1, master.width-1))
                sv = right.selectbox('Source reference field', source.columns, index=source.columns.index(mapping.source_value) if mapping else min(1, source.width-1))
                st.caption('Exact, normalized, alias, duplicate, fuzzy and corporate relationship checks run automatically.')
                if st.form_submit_button('Save column mapping', type='primary'):
                    if mi == mv or si == sv:
                        st.error('Select a comparison field distinct from the identifier.')
                    else:
                        payload['mapping'] = vars(Mapping(mi, si, mv, sv))
                        save()
                        st.rerun()
        if mapping:
            left, right = st.columns(2)
            left.write({'Master': identifier_stats(master, mapping.master_id)})
            right.write({'Source': identifier_stats(source, mapping.source_id)})

elif page == 'Translation Intelligence':
    if datasets_ready():
        translation_section(store, st.session_state.project, credential)

elif page == 'Run Reconciliation':
    if datasets_ready():
        if not mapping:
            st.warning(mapping_error)
        else:
            st.write(f'{master.height:,} Master records → {source.height:,} Source records')
            st.caption('Approved Master and Source translations are included automatically as additional name evidence.')
            st.caption('Translation-assisted matches require entity/field verification and human approval. Only approved translations participate.')
            completion_key = f'local_matching_complete_{st.session_state.project}'
            if st.session_state.pop(completion_key, False):
                st.success('Reconciliation complete. Corrections remain pending until review.')
            if st.button('Run automatic local matching', type='primary'):
                try:
                    with st.spinner('Indexing identifiers and scoring blocked candidates…'):
                        entries = TranslationEngine(store, st.session_state.project).records()
                        fresh, conflicts = reconcile(master, source, mapping, entries,
                            aliases=payload.get('aliases'), relationships=payload.get('relationships'), previous=results)
                        # Preserve human decisions and research evidence without freezing unresolved candidates.
                        next_results = fresh
                        run_names = ApprovedNames(payload, mapping, entries)
                        run_names.attach(next_results)
                        next_payload = dict(payload,
                            reconciliation_translation_signature=run_names.matching_signature(),
                            use_approved_translations=True, conflicts=conflicts,
                            context=digest({'source': payload['source'], 'mapping': payload['mapping']}),
                            results=[r.dict() for r in next_results])
                        store.save(st.session_state.project, next_payload)
                except Exception:
                    st.error('Local matching could not be completed. Previously saved results are preserved. Retry; if the problem continues, check the application server.')
                else:
                    # Store.save can preserve newer reviewer decisions. Render its
                    # committed records through the normal SQLite load path above,
                    # never the pre-save objects or the display-only projection.
                    st.session_state[completion_key] = True
                    st.rerun()
            if results and payload.get('reconciliation_translation_signature') != current_names.matching_signature():
                st.warning('Reconciliation results are stale: approved translation inputs changed, or this run has no recorded translation snapshot. '
                           'Current translations are shown below. Run automatic local matching to refresh candidates and Match Basis. '
                           'Existing human decisions and audit history will be preserved.')
            if results:
                query = st.text_input('Search account identifiers')
                st.dataframe(visible_table(result_row(r) for r in results if query.casefold() in r.identifier.casefold()), hide_index=True, width='stretch')

elif page == 'AI Research':
    if results_ready():
        settings = ResearchSettings(**payload.get('research_settings', {}))
        researcher = Researcher(store, st.session_state.project, credential('TAVILY_API_KEY'), credential('OPENAI_API_KEY'), settings)
        pending = [r for r in results if eligible(r)]
        batch = pending[:settings.limit]
        misses = sum(not researcher.cached(r, payload['context']) for r in batch)
        st.write(f'{len(pending)} eligible accounts · next batch: {len(batch)} · {len(batch)-misses} cached findings')
        st.info(f'Estimated new requests: {misses} Tavily searches + {misses} OpenAI requests. '
                f'With retries, at most {misses * (settings.retries+1)} attempts per provider. '
                'This sends company identifiers and candidate account names/values to external providers.')
        st.caption('Reliable local matches and accounts with reviewer decisions are excluded. Every completed account is checkpointed automatically.')
        online = bool(researcher.tavily_key and researcher.openai_key)
        if not online:
            st.warning('Offline mode: API keys are missing. Local reconciliation, review and export remain available.')
            for r in pending:
                if not r.research_snapshot:
                    r.research_status = 'Unavailable (offline)'
            checkpoint(results)
        consent = st.checkbox('I authorize external research for this batch and the associated API charges.', disabled=not online)
        if st.button('Start / resume paid research', type='primary', disabled=not online or not consent or not batch):
            progress = st.progress(0, text='Starting research')
            for i, r in enumerate(batch):
                researcher.investigate(r, source, mapping, payload['context'])
                checkpoint(results)
                progress.progress((i+1)/len(batch), text=f'{i+1}/{len(batch)} accounts checkpointed')
            st.success('Batch saved. Remaining or failed accounts can be resumed.')
        # Research may have resolved a different Source during this action.
        current_names.attach(results)
        inspectable = [r for r in results if r.identity_confidence != 'Reliable local match']
        st.dataframe(visible_table(result_row(r) for r in inspectable), hide_index=True, width='stretch')
        if inspectable:
            by_id = {r.row_id: r for r in inspectable}
            inspected_id = st.selectbox('Inspect researched account', list(by_id),
                format_func=lambda i: f'Row {i+1} · {by_id[i].identifier}')
            inspected = by_id[inspected_id]
            research_sections(inspected)
            st.caption('Confidence is a qualitative AI evidence assessment, not a calibrated probability.')
            for index, url in enumerate(inspected.evidence):
                if urlparse(url).scheme in ('https', 'http'):
                    st.link_button(f'Research evidence {index+1}', url)
            locked = bool(inspected.decision)
            if st.button('Re-evaluate saved evidence (no API calls)', disabled=locked):
                researcher.evaluate_saved(inspected, source, mapping, payload['context'])
                checkpoint(results)
                st.rerun()
            st.caption('Local re-evaluation looks up saved verified entities across the entire Source under the current policy; '
                       'it does not ask an AI model for a new interpretation. Legacy findings without saved excerpts may be insufficient.')
            fresh_consent = st.checkbox('I authorize fresh paid web research and AI analysis for this selected account.', disabled=locked or not online)
            st.caption(f'Fresh research: 1 Tavily search + 1 AI request; up to {settings.retries+1} attempts each with retries.')
            if st.button('Run fresh paid research', disabled=locked or not online or not fresh_consent):
                with st.spinner('Researching selected account…'):
                    researcher.investigate(inspected, source, mapping, payload['context'], fresh=True)
                    checkpoint(results)
                st.rerun()

elif page == 'Review & Approvals':
    if results_ready():
        project = st.session_state.project
        filter_key, selected_key = f'review_filter_{project}', f'review_selected_{project}'
        saved_notice = st.session_state.pop('review_saved', None)
        if saved_notice and saved_notice['project'] == project:
            # Keep the saved row visible when its status no longer matches Pending.
            st.session_state[filter_key] = 'All'
            st.session_state[selected_key] = saved_notice['row_id']
            st.success('Review decision saved. Final Value, status, statistics and results are up to date.')
        metrics = summary(results)
        for column, label in zip(st.columns(4), ['Pending Approvals', 'Approved Corrections', 'Manually Verified', 'Unresolved Accounts']):
            column.metric(label, metrics[label], border=True)
        for column, label in zip(st.columns(2), [AI_PENDING, MANUAL_REQUIRED]):
            column.metric(label, metrics[label], border=True)
        st.caption('Workflow statuses describe the review stage; they do not establish evidence eligibility or change saved values.')
        if metrics['Legacy Automatically Finalized Matches']:
            st.info(f"{metrics['Legacy Automatically Finalized Matches']} legacy automatically finalized matches need human review. "
                    'Stored values are preserved; unapproved legacy finals are excluded from Final Value displays and exports. '
                    'Review and explicitly approve or manually verify each account before using its Final Value.')
        st.markdown('**Reconciliation results**')
        table_slot = st.empty()
        table_pagination = st.container()
        st.markdown('**Filter accounts by review status**')
        left, right = st.columns([2, 1])
        search = left.text_input('Search accounts')
        if st.session_state.get(filter_key) not in REVIEW_FILTERS:
            st.session_state[filter_key] = 'All'
        status = right.selectbox('Review status', REVIEW_FILTERS, key=filter_key)
        visible = [r for r in results if search.casefold() in r.identifier.casefold() and
                   (status == 'All' or r.status_label == status)]
        selection_scope = digest([project, search, status, [r.row_id for r in visible]])
        with table_pagination:
            left_page, right_page = st.columns(2)
            page_size = left_page.selectbox('Review rows per page', [25, 50, 100], index=1,
                                            key=f'review_page_size_{project}')
            page_count = max(1, (len(visible) + page_size - 1) // page_size)
            page_key = f'selection_page_{selection_scope}'
            st.session_state[page_key] = min(max(1, st.session_state.get(page_key, 1)), page_count)
            selection_page = right_page.number_input('Selection page', min_value=1, max_value=page_count,
                                                       step=1, key=page_key)
            st.caption(f'{len(visible):,} accounts · page {selection_page} of {page_count}')
        page_rows = visible[(selection_page - 1) * page_size:selection_page * page_size]
        table_slot.dataframe(visible_table(result_row(review_display[r.row_id]) for r in page_rows), hide_index=True, width='stretch')
        show_key = f'review_show_accounts_{project}'
        def toggle_account_list():
            st.session_state[show_key] = not st.session_state.get(show_key, False)
        st.button('Hide Account List' if st.session_state.get(show_key, False) else 'Show Account List',
                  key=f'review_toggle_accounts_{project}', on_click=toggle_account_list)
        if visible:
            # Canonical selection belongs to this workspace/upload, never a filter.
            record_scope = digest([project, revision(payload, 'master')])
            selection_key = f'bulk_selection_{record_scope}'
            row_keys = {r.row_id: f'bulk_row_{record_scope}_{r.row_id}' for r in results}
            selected_ids = set(st.session_state.get(selection_key, {})) & set(row_keys)
            all_key = f'bulk_all_{selection_scope}'
            st.session_state[all_key] = all(r.row_id in selected_ids for r in visible)

            def select_filtered_rows(state, key, items, widgets, widget):
                select_group(state, key, items, widgets, bool(state[widget]))

            if st.session_state.get(show_key, False):
                st.caption('Account list uses the search, status and page shown above.')
                for record in page_rows:
                    widget = row_keys[record.row_id]
                    if widget not in st.session_state:
                        st.session_state[widget] = record.row_id in selected_ids
                    checked = st.checkbox(f'Select row {record.row_id + 1} · {record.identifier or "Missing identifier"}',
                        key=widget, on_change=checkbox_changed,
                        args=(st.session_state, selection_key, record.row_id, record.row_id, widget))
                    set_checked(st.session_state, selection_key, record.row_id, record.row_id, checked)
            selected_ids = set(st.session_state.get(selection_key, {}))
            st.session_state[all_key] = all(r.row_id in selected_ids for r in visible)
            st.markdown('**Bulk Decisions**')
            bulk_review_notice(project)
            st.checkbox('Select All filtered accounts', key=all_key, on_change=select_filtered_rows,
                        args=(st.session_state, selection_key, {r.row_id: r.row_id for r in visible}, row_keys, all_key))
            selected_rows = [r for r in visible if r.row_id in selected_ids]
            st.caption(f'Selected accounts: {len(selected_rows)} of {len(visible)} filtered accounts')
            outside_filter = len(selected_ids - {r.row_id for r in visible})
            if outside_filter:
                st.caption(f'{outside_filter} checked accounts outside this filter are preserved and excluded from this bulk action.')
            page_ids = {r.row_id for r in page_rows}
            off_page = sum(r.row_id not in page_ids for r in selected_rows)
            if off_page:
                st.caption(f'{off_page} selected accounts are on other pages of this filter; they require explicit confirmation below.')
            # Any change to selection or saved versions invalidates prior confirmations.
            confirmation_scope = digest([selection_scope, [r.dict() for r in selected_rows]])
            with st.container(key=f'bulk_review_{confirmation_scope}'):
                bulk_action = st.selectbox('Bulk decision', ['Approve', 'Reject'], key=f'bulk_action_{project}_{confirmation_scope}')
                if selected_rows and bulk_action == 'Approve':
                    reasons = Counter(reason for r in selected_rows if (reason := bulk_approval_error(r, payload)))
                    if reasons:
                        st.warning(f'{len(selected_rows) - sum(reasons.values())} eligible for approval; ' + '; '.join(f'{count}: {reason}' for reason, count in reasons.items()))
                bulk_reviewer = st.text_input('Bulk reviewer name', value=payload.get('reviewer_name', ''), key=f'bulk_reviewer_{project}_{confirmation_scope}')
                bulk_notes = st.text_area('Bulk reviewer notes', key=f'bulk_notes_{project}_{confirmation_scope}')
                bulk_confirmed = st.checkbox('I have verified the evidence and field value for every selected account.', key=f'bulk_confirm_{project}_{confirmation_scope}')
                include_other_pages = st.checkbox(
                    f'I confirm including {off_page} selected accounts on other pages of this filter.', key=f'bulk_include_{project}_{confirmation_scope}') if off_page else True
                existing = [r for r in selected_rows if r.decision]
                overwrite = False
                if existing:
                    st.warning(f'{len(existing)} selected accounts have saved decisions. Saving will add a new audit entry for each overwritten decision.')
                    overwrite = st.checkbox('I confirm overwriting the existing saved decisions for these selected accounts.', key=f'bulk_overwrite_{project}_{confirmation_scope}')
                if st.button('Save Review Decisions', disabled=not selected_rows, key=f'bulk_save_{project}_{confirmation_scope}'):
                    try:
                        if not include_other_pages and bulk_reviewer.strip():
                            raise ValueError('Confirm including the selected accounts on other pages, or narrow the selection.')
                        versions = {r.row_id: digest(r.dict()) for r in existing} if overwrite else {}
                        saved, report = store.bulk_review(project, [r.row_id for r in selected_rows],
                            bulk_action, bulk_reviewer, bulk_notes, bulk_confirmed, versions)
                        st.session_state.payload = saved
                        operation_key = f'bulk_operation_{project}'
                        operation = st.session_state.get(operation_key, 0) + 1
                        st.session_state[operation_key] = operation
                        st.session_state[f'bulk_notice_{project}'] = {'report': report, 'operation': operation}
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
        if not visible:
            st.info('No accounts match these filters.')
            st.markdown('**Bulk Decisions**')
            st.caption('No filtered accounts are available for bulk decisions.')
        st.markdown('**Account to Review**')
        by_id = {r.row_id: r for r in results}
        if st.session_state.get(selected_key) not in by_id:
            choices = visible or results
            st.session_state[selected_key] = next((r.row_id for r in choices
                if r.status_label in (AI_PENDING, MANUAL_REQUIRED) and r.proposed != r.original), choices[0].row_id)
        selected_id = st.session_state[selected_key]
        account_ids = list(dict.fromkeys([r.row_id for r in page_rows] + [selected_id]))
        if selected_id not in {r.row_id for r in visible}:
            st.caption('The selected account is outside the current filter. Its individual review remains open; bulk decisions use only the current filter.')
        selected = st.selectbox('Account to review', account_ids,
            format_func=lambda i: f'Row {i+1} · {by_id[i].identifier or "Missing identifier"} · {by_id[i].match_status}', key=selected_key)
        if selected is not None:
            r = by_id[selected]
            with st.container(key='redthread_record'):
                st.markdown('**Account review**')
                status_badge(r.status_label)
                a, b, c = st.columns(3)
                a.metric('Original value', r.original or '—', border=True)
                b.metric('Intelligence Proposed Value', r.proposed if has_proposal(r) else '—', border=True)
                c.metric('Final value', final_value(r) or '—', border=True)
                confidence_indicator(r.ai_confidence)
                if r.local_confidence:
                    st.caption(f'Local match confidence: {r.local_confidence} · Method: {r.match_method or r.match_status}')
                    st.write(r.local_reason)
                if r.secondary_validation:
                    st.caption('Secondary validation: ' + r.secondary_validation['status'])
                    st.write(r.secondary_validation['reason'])
            st.write(f'**Identity:** {r.identity_confidence}')
            display = review_display[r.row_id].account_context
            master_name = display.get('master', {})
            st.write(f"**Original company name:** {master_name.get('original_name', r.identifier)}")
            st.write(f"**Approved English translation:** {master_name.get('approved_english') or '—'}")
            st.write(f"**Match basis:** {r.match_basis or 'No recorded comparison'}")
            if r.status_label == AI_PENDING:
                st.info(AI_PENDING)
            if r.recommendation_status == 'Proposed':
                if r.recommended_source_account:
                    st.write(f'AI Research supporting Source account: {r.recommended_source_account}')
                if r.parent_company:
                    st.write(f'Parent company: {r.parent_company}')
                st.write(r.recommendation_reasoning)
            elif r.recommendation_status == 'Insufficient Evidence':
                st.warning(INSUFFICIENT)
                st.write(r.recommendation_reasoning)
            st.caption('Similarity measures text resemblance; it does not prove company identity.')
            version = suggestion_version(r, payload)
            suggestion_key = f'suggestion_{project}_{r.row_id}_{version}'
            if st.session_state.get(f'active_suggestion_{project}') != suggestion_key:
                st.session_state[suggestion_key] = None
                st.session_state[f'active_suggestion_{project}'] = suggestion_key
            suggestions, suggestion_errors = {}, {}
            for i, candidate in enumerate(r.candidates[:3]):
                try:
                    suggestions[i] = source_suggestion(r, payload, candidate.get('source_row'))
                except ValueError as error:
                    suggestion_errors[i] = str(error)

            def suggestion_label(i):
                candidate = r.candidates[i]
                item = suggestions.get(i)
                value = (item['value'] or 'Missing value') if item else 'Unavailable Source record'
                return (f"{i + 1}. {item['account'] if item else candidate.get('account', '')} | "
                        f"Comparison value: {value} | Similarity: {candidate.get('similarity', '—')}")

            picked = st.radio('Top 3 Suggested Source Matches', list(range(min(3, len(r.candidates)))),
                              index=None, format_func=suggestion_label, key=suggestion_key,
                              help='Choose one Source record. Similarity is not proof; independently verify its identity and comparison value.') if r.candidates else None
            selected_suggestion = suggestions.get(picked)
            if picked is not None:
                def clear_suggestion():
                    st.session_state[suggestion_key] = None
                st.button('Clear suggested Source selection', on_click=clear_suggestion)
            if picked in suggestion_errors:
                st.warning(suggestion_errors[picked])
            if selected_suggestion:
                preview_error = ''
                try:
                    validate_suggestion_approval(r, payload, selected_suggestion)
                except ValueError as error:
                    preview_error = str(error)
                st.write(f"**Selected Source account:** {selected_suggestion['account']}")
                a, b = st.columns(2)
                a.metric('Selected Source comparison value', selected_suggestion['value'] or '—', border=True)
                b.metric('Final value preview', 'Blocked' if preview_error else selected_suggestion['value'], border=True)
                if preview_error:
                    st.warning(preview_error)
                st.caption('This preview applies to Approve after verification. Reject and Manual use their existing values.')
                if r.ai_proposed and selected_suggestion['value'] != r.ai_proposed:
                    st.warning('This Source value differs from the AI Proposed Value. Approval records your verified Source selection; the AI proposal remains unchanged.')
            if r.selected_source:
                st.write(f"**Saved selected Source account:** {r.selected_source.get('account', '')}")
            with st.expander('Research, relationships & evidence', expanded=False):
                research_sections(r, show_candidates=False, show_tables=False)
                st.write(f'{r.research_status} · {r.relationship or "No relationship established"}')
                st.write(r.explanation or 'No research findings yet.')
                for index, url in enumerate(r.evidence):
                    if urlparse(url).scheme in ('https', 'http'):
                        st.link_button(f'Open evidence {index+1}', url)
            if r.notes:
                st.info(r.notes.replace('AI Proposed — Pending Approval', AI_PENDING))
            st.markdown('**Individual Decision**')
            # Outside the form so choosing Manual immediately reveals its controls.
            action = st.selectbox('Decision', ['Approve', 'Reject', 'Manual', 'Retain original', 'Pending'],
                                  key=f'action_{project}_{r.row_id}')
            options = manual_options(source, mapping.source_value, r.candidates)
            with st.container(key=f'review_{project}_{r.row_id}_{version}_{picked}'):
                reviewer = st.text_input('Reviewer name', value=payload.get('reviewer_name', ''), key=f'review_name_{project}_{r.row_id}_{version}')
                manual, source_value = '', ''
                if action == 'Manual':
                    source_value = st.selectbox('Verified Source value', options, index=None,
                                                placeholder='Select a Source value')
                    manual = st.text_input('Custom verified value', key=f'review_custom_{project}_{r.row_id}_{version}', help='A nonblank custom entry takes precedence over the Source dropdown.')
                notes = st.text_area('Reviewer notes', value=r.notes, key=f'review_notes_{project}_{r.row_id}_{version}')
                confirmed = st.checkbox('I have verified the evidence and the field value for this specific account.', key=f'review_confirm_{project}_{r.row_id}_{version}_{picked}_{action}')
                if st.button('Save review decision', type='primary', key=f'review_save_{project}_{r.row_id}_{version}_{picked}_{action}'):
                    try:
                        if action not in ('Reject', 'Pending') and not confirmed:
                            raise ValueError('Confirm you have verified this account and field value.')
                        if action == 'Approve' and picked in suggestion_errors:
                            raise ValueError(suggestion_errors[picked])
                        saved = store.review(project, r.row_id, action, reviewer, notes, manual, source_value or '',
                            selected_source_row=selected_suggestion['source_row'] if action == 'Approve' and selected_suggestion else None,
                            selection_version=version, confirmed=confirmed)
                        st.session_state.payload = saved
                        st.session_state.pop(f'bulk_notice_{project}', None)
                        st.session_state.review_saved = {'project': project, 'row_id': r.row_id}
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))

elif page == 'Export Results':
    if datasets_ready():
        detection_runtime = google_runtime_info() if provider_for(payload) == 'google' else detection_runtime_info()
        if detection_runtime['restart_required']:
            st.error('Restart Streamlit to load the updated detector before exporting this workspace.')
            st.stop()
        st.caption(f"Detection policy: {detection_runtime['policy']} · Loaded build: {detection_runtime['loaded_build'][:12]}. "
                   'Translation exports use current selected enabled fields; historical records and excluded fields are omitted.')
        st.write('Download full account datasets, translation coverage, audit trail and any reconciliation results in a formatted workbook. '
                 'A reconciliation run is not required for translation export.')
        st.caption('Final Value requires a saved human approval or manual verification. Rejection retains an explicitly verified original where applicable. Pending proposals remain separate.')
        export_current = approved_entries if mapping else TranslationEngine(store, st.session_state.project).records()
        export_selected = [item for item in export_current if not item.get('translation_excluded') and item['status'] != 'Excluded']
        st.download_button('Download Excel report', workbook(results, store.audit(st.session_state.project),
                           payload.get('conflicts', []), source.height,
                           translations=export_selected, datasets=payload, current_translations=export_current),
                           'RTA_Account_Intelligence_V3.xlsx',
                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', type='primary')
        st.dataframe([result_row(r) for r in results], hide_index=True, width='stretch')

elif page == 'Settings':
    st.write('API keys are read from environment variables or Streamlit secrets. They are never stored in a workspace.')
    st.write({'Tavily configured': bool(credential('TAVILY_API_KEY')), 'OpenAI configured': bool(credential('OPENAI_API_KEY'))})
    settings = ResearchSettings(**payload.get('research_settings', {}))
    with st.form('settings'):
        model = st.text_input('OpenAI model', settings.model)
        limit = st.number_input('Maximum accounts per explicitly started batch', 1, 250, settings.limit)
        retries = st.number_input('Maximum retries per provider request', 0, 5, settings.retries)
        timeout = st.number_input('Request timeout (seconds)', 5, 120, settings.timeout)
        interval = st.number_input('Minimum seconds between requests', 0.5, 10.0, settings.interval)
        cache_days = st.number_input('Research cache lifetime (days)', 1, 365, settings.cache_days)
        tokens = st.number_input('Maximum AI output tokens per request', 200, 4000, settings.max_output_tokens)
        relationship_policy = st.selectbox('Corporate relationship mapping policy', POLICIES,
                                           index=POLICIES.index(settings.relationship_policy))
        st.caption('Evidence-backed inheritance requires explicit account-specific field evidence. '
                   'Same entity only forbids inheritance from separate legal entities. '
                   'Policy changes apply on explicit re-evaluation; saved reviewer decisions remain protected.')
        st.caption('Known mappings are optional JSON objects, for example {"Former Name": "Source Account"}. '
                   'Only enter independently verified aliases. Relationships always require review.')
        aliases = st.text_area('Verified alternate names / aliases', json.dumps(payload.get('aliases', {}), indent=2), disabled=bool(results))
        relationships = st.text_area('Known corporate relationships', json.dumps(payload.get('relationships', {}), indent=2), disabled=bool(results))
        if st.form_submit_button('Save settings'):
            try:
                a, rel = json.loads(aliases), json.loads(relationships)
                for obj in (a, rel):
                    if not isinstance(obj, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in obj.items()):
                        raise ValueError('Mappings must be JSON objects with string names.')
                if not model.strip():
                    raise ValueError('Enter an OpenAI model name.')
                payload.update(aliases=a, relationships=rel,
                    research_settings=vars(ResearchSettings(model.strip(), int(limit), int(retries), int(timeout),
                                                         float(interval), int(cache_days), int(tokens), relationship_policy)))
                save()
                st.success('Settings saved.')
            except (ValueError, TypeError) as error:
                st.error(str(error))
    st.caption('Download a private resume token from the sidebar to reopen this workspace after restarting. '
               'Anyone with that token can access its datasets and findings on this server.')
