# Translation Intelligence table workspace

> **Latest selection/refresh behavior:** [Multi-row translation fix](translation-multirow-refresh.md) freezes editor inputs, merges checkbox deltas by stable IDs and reruns directly after commit. Post-commit progress replay is retired. Validation: 476 tests passed; no live paid calls.

> **Latest execution fix:** [Post-response interruption diagnostics](translation-execution-diagnostics.md) addresses reruns during progress updates after Google responds. The earlier stable-form fix alone did not protect draft persistence. Validation: 466 tests passed; no live paid calls.

> **Current Translate Selected behavior:** [Silent-submit fix](translate-selected-execution-fix.md) stabilizes the form identity. The button now remains clickable to explain empty/ineligible selections, and changed previews require fresh consent instead of dropping the click. This supersedes older disabled-button descriptions below.

> **Organization-name draft eligibility:** Backend plan/process defaults now enable company-name drafts. The redesigned UI already passed this permission explicitly; the old checkbox/session state is not consulted. See the [follow-up investigation and 449-test validation](organization-name-draft-permission.md).

This supersedes older Translation Intelligence page instructions. Detection policy,
translation approval, account reconciliation and Final Value rules are unchanged.
No live Google calls were made while implementing or testing this page.

## Workflow

1. Open **Translation Intelligence** after uploading and mapping Master and Source.
   The first section is **Account translations**, including untranslated accounts.
   The page uses the mapped company-name field on each side, or the first inferred
   name field if the mapping is not a company-name field. Previously selected name
   fields remain available; saved classification-field settings and historical
   records are retained, but classification fields are not shown as company names.
2. Search original names or English translations, filter by dataset/status and
   choose 25, 50 or 100 rows per page. Search is literal and Unicode case-insensitive.
   Check individual rows or use **Select all visible rows**: this selects only the
   current filtered page, never every search result. Selections survive page/filter
   changes and are counted across pages. **Clear selection** clears them all.
3. Below the table, inspect the number of names and estimated cost, authorize the
   batch and press **Detect Languages**. Google Cloud Translation Advanced v3 is
   the only provider offered. Detection covers unprocessed unique company names
   from both datasets, without requiring reconciliation. **Names per batch** limits
   each detection/translation batch; repeat with new consent to advance processing.
4. Select accounts to translate, then separately authorize and press **Translate
   Selected**. Only selected eligible occurrences receive drafts. Duplicate names
   share cached drafts, including duplicates across datasets. A selected duplicate
   does not change an unselected occurrence. Existing drafts and approvals are not
   retransmitted. Low-confidence supported non-English Google results are eligible
   with review advice. English names are excluded. Unknown/unsupported languages
   require **Save confirmed language** in the individual review form first.
5. Review drafts in the main table. English edits and **Individual action** choices
   (Approve/Reject) are applied using **Apply individual actions and edits**, with a
   reviewer and explicit confirmation. Editable original names are never offered.
   Edits without an approval action remain drafts. To enter a manual translation,
   correct an approved translation, or confirm a language, use the individual review
   form. Apply table edits before changing pages or starting another action;
   unsaved cell edits are page-local. Changing an unapproved draft's source language archives the old draft;
   select the account and authorize translation again to generate its replacement.
   Saving the same language cannot silently requeue an existing draft.
6. **Approve Selected** / **Reject Selected** affect only selected eligible drafts.
   Both require a reviewer and explicit confirmation. Atomic stale-record checks
   roll back the entire decision batch if any affected snapshot changed. If this
   happens, clear/reselect rows after inspecting their updated values.
7. Actions persist in SQLite, refresh the table and retain valid selection and
   filters. Translation approval remains separate from account approval. Only
   approved translations may provide reconciliation evidence. No action here
   populates Final Value.
8. **Export to Excel** explicitly builds a full workbook; **Download Excel** retrieves
   it. Export covers both complete uploaded datasets, translated and untranslated
   records, translation details, approvals and audit history, regardless of the
   table's filters or page. Files are generated on demand rather than on every
   page rerun. Click Export again for a fresh file after external changes.

## Persistence, consent and compatibility

The visible monthly dashboard, credit tables, provider selectors, request logs,
eligibility diagnostics, technical detection settings and audit tables are removed.
Backend monthly estimates, confirmed/uncertain request accounting, workspace cache,
settings and audit history remain intact. Estimates shown by actions are USD before
credits; translation previews also show the retry upper estimate. They are local
estimates, not actual Google billing or a guaranteed free allowance.

Existing database columns and historical records are retained. No database reset
or schema migration is required. Opening a workspace switches an older offline
provider setting to Google and refreshes automatic metadata using caches only;
manual corrections, approvals and existing drafts are preserved. Drafts whose
source language is pending or conflicts with refreshed detection remain visible
and need explicit language confirmation before bulk approval. The table displays
current Google detection separately from the retained draft language; confirmed
languages are labelled as reviewer-confirmed in the review advice. A pending record can accept a
new raw Google cache response even when its detection-policy version is unchanged;
older interpreted pending entries cannot mask that response. No page load, table
edit, selection, filter, refresh or export makes a paid request.

After upgrading, restart Streamlit so the new UI and workspace module are loaded.
Resume the existing workspace; do not delete its database. Review cached results
in the table. For names with no Google result, use Detect Languages with explicit
batch authorization. Then select the desired rows and separately authorize Translate
Selected. Existing manually reviewed translations do not need to be regenerated.

## Implementation and performance

`TranslationWorkspace` restricts SQL queries to the workspace, current upload
revisions and current company-name fields. Counts, search and status/dataset
filters run in SQLite; page reads use LIMIT/OFFSET and deserialize at most 100
records. Stable selection identifiers include dataset, revision, row and field.
Detection planning reads a deduplicated projection rather than all translation
payloads. Batch application updates only the current batch's names. Selections
hold review snapshots so concurrent decisions are checked against what was selected.

The existing app still loads upload payloads for workspace navigation; initializing
new name fields and producing a complete Excel export remain proportional to dataset
size. Search scans the current scoped SQLite rows. Detection planning retains unique
names/cache keys in memory; it is not an editable full-dataset widget. These are
remaining scaling limits, rather than a claim of constant-memory end-to-end operation.
No new dependency installation is required; pandas is already supplied by Streamlit.

## Changed files

Production:

- `rta/translation_ui.py`: table-first layout, bounded editable table, selection,
  compact Google consent, selected processing, individual/bulk review, Excel action.
- `rta/translation_workspace.py` (new): scoped SQLite paging, Unicode search,
  stable identifiers, selection validation, deduplicated detection planning.
- `rta/translation.py`: optional selected-snapshot plans/processes, batch-scoped
  cached detection application, legacy-draft preservation with language review,
  cache refresh fix, atomic bulk rejection, reuse
  dataset revision hashes within atomic review transactions.
- `rta/translation_runtime.py`: stale module protection includes the workspace module.

Tests:

- `tests/test_translation_workspace.py` (new)
- `tests/translation_workspace_helpers.py` (new)
- `tests/test_company_translation.py`
- `tests/test_detection_refresh.py`
- `tests/test_google_detection.py`
- `tests/test_google_detection_execution.py`
- `tests/test_google_direct.py`
- `tests/test_google_translation.py`
- `tests/test_language_detection.py`
- `tests/test_stale_google_export.py`
- `tests/test_translation.py`
- `tests/test_translation_button.py`
- `tests/test_translation_e2e.py`
- `tests/test_translation_usage.py`

Documentation:

- `docs/translation-workspace-ui.md` (this report)
- `docs/translation-intelligence.md`
- `docs/google-direct-translation.md`

Existing UI tests now use the replacement controls; removed diagnostic panels are
asserted absent while their accounting/settings invariants remain tested through
backend APIs. The fictional Excel scenario retains import/mapping, reconciliation,
all six review filters, independent account decisions, full export and audit checks.
It now uses annotated mocked Google responses rather than an offline UI selector.

## Validation

Command: `.venv/bin/python -m pytest -q`

**444 passed in 79.01 seconds. No failed tests.** This includes both startup checks:
real Streamlit HTTP health and execution/import validation through AppTest.

The 15 new workspace test cases cover table-first ordering, absence of removed
panels/provider selectors, literal Unicode search, filters, paging, visible-only
selection, selection persistence, selected-only translation, cache reuse,
workspace isolation, stale pre-dispatch checks, atomic approval/rejection,
individual table corrections/decisions, immediate refresh, full Excel/audit
coverage, preserved legacy/current drafts, explicit language confirmation and
blank-cell approval rejection. The bounded-query test persists 52,001 SQLite rows
and verifies a 25-row page without invoking the unbounded engine record reader.
Existing mock detection tests additionally exercise 107,243 selected cells and
250-name batch advancement. Google network clients were mocked; no live paid
requests were made.

The complete fictional XLSX workflow still verifies independent datasets,
translation-aware matching only after human translation approval, pending account
proposals, all six reconciliation filters, individual account decisions, persisted
cache/usage, workspace isolation and original data preservation. Export assertions
cover translated and untranslated rows, both dataset sheets, review statuses and
audit snapshots.

Ready for manual browser acceptance testing. Restart Streamlit, resume the existing
workspace and follow the workflow above. Browser appearance and responsiveness on
real 52,000-name uploads remain to be confirmed manually; automated coverage
validates bounded SQLite pagination and Streamlit behavior, not a browser benchmark.
