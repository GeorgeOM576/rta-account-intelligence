# Compact, table-first Review & Approvals

## Layout

The existing page now renders in this order:

1. Existing six dashboard KPI bubbles, using the unchanged summary calculations.
2. One main reconciliation results table, retaining all original columns.
3. Review-status filter, account search and a Show Account List / Hide Account List button.
4. Bulk Decisions.
5. Account to Review, including company name, current approved English name, status, Source suggestions and evidence.
6. Individual Decision.

The main table occupies a reserved Streamlit container directly below the KPIs. Its rows are filled using the current search/status/page selection, so filters below the table update it in the same render. Pagination controls sit with the table; the account list uses that same search, status and page. All six existing review statuses are unchanged.

The account list is collapsed by default and renders no row-selection widgets until opened. At most 25, 50 or 100 rows are rendered at once (default 50), in both the main table and the expanded list. The Account to review selector contains at most the current page plus the selected record. It never creates a dropdown with thousands of account options.

The selected account is keyed by persisted row ID and remains selected when the list is collapsed, the page changes or a filter excludes it. An explicit caption identifies an individually selected account outside the current filter. The bulk selection remains limited to its own current filter; it does not inherit this outside-filter account.

## State and approval safeguards

Individual and bulk handlers still call the existing `store.review()` and `store.bulk_review()` transactions with the same source/version checks, permissions, eligibility rules and audit recording. No reconciliation, translation, AI Research, review or persistence engine was rewritten.

Session-backed text widgets retain pending comments/reviewer input when the account list toggles or filters rerun the page. Only the explicit Save buttons submit decisions to SQLite. Field edits, selection, pagination and toggling do not save decisions or populate Final Value.

Individual confirmation keys include workspace, record ID, saved version, Source selection and decision. Bulk confirmation keys include the filtered selected record versions. Changing the relevant account, Source, action or batch invalidates the corresponding prior confirmation.

Existing cross-page Select All filtered accounts remains supported. The UI shows selected/filtered counts and explicitly reports selected accounts on other pages. Saving those records requires an additional confirmation naming the off-page count. Hidden rows are never added implicitly; filtered-out and unselected records are excluded from bulk requests. Existing overwrite confirmation is preserved.

Bulk decisions refresh the table/KPIs through the existing controlled rerun. Bulk warnings remain bounded inside their existing warning expander in the Bulk Decisions section. There is no automatic rerun loop or paid API action.

## Compact account details

The dedicated Translation match provenance expander/table has been removed. Provenance remains in saved results, matching dependencies, audit history and Excel exports, and existing table fields remain intact.

Selected/saved Source account information is rendered as readable company names instead of raw dictionaries/JSON. Matching suggestions and comparison-value previews retain their existing validation. Research facts and source links remain available in the collapsed Research, relationships & evidence section; its suggestions use a bounded readable summary rather than another account table.

## Actual Streamlit verification

[Captured layout proof](review-layout-proof.json) was extracted from the actual `app.py` Streamlit AppTest tree with live services blocked. It records the section order, unchanged KPI values, all main-table columns, the six status options, a collapsed account list, zero initial per-account checkbox widgets and no raw JSON/provenance panels.

Seven new UI regressions cover:

- Exact rendered section order, KPI position and one main table.
- Default collapse and all translation/result/evidence columns retained.
- Filter/search operation while hidden, including an empty table that retains its headers.
- Selected account and pending individual/bulk text surviving list toggles; individual notes survive filtering.
- Bounded pagination, row widgets and selector options, with selection surviving page/list changes.
- Explicit confirmation before cross-page bulk decisions.
- No raw Source JSON or provenance panel; original stored data/audit unaffected by navigation.
- Confirmation invalidation after selected-batch, Source or individual-decision changes.

Existing tests were updated only for intentional UI behavior: opening the now-collapsed list, explicitly confirming cross-page selection, and preserving the selected individual account when filtering. Their existing decision, audit, warning, export and Final Value assertions remain.

Focused review suite: **108 passed** before the last two added confirmation regressions. All **7 new layout/state tests passed**.

**Full regression suite: 528 passed in 138.97 seconds.** Both Streamlit startup checks passed: real application execution/import validation and local HTTP server health. No tests failed.

No live Google, OpenAI or Tavily calls were made. No new dependencies or database migrations were added. Existing workspace data was not deleted or reset.

## Files changed

- `app.py`
- `tests/test_review_layout.py` (new)
- `tests/test_bulk_review.py`
- `tests/test_review_ux.py`
- `tests/test_effective_proposals.py`
- `tests/test_translation_e2e.py`
- `docs/review-layout.md` (new)
- `docs/review-layout-proof.json` (new)
