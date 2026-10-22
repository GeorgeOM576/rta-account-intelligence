# Multi-row translation and immediate table refresh

## Root causes

1. The editor's input DataFrame was rebuilt from the live selection dictionary.
   After a checkbox edit, the next render changed that checkbox in the input
   baseline as well. Changing the baseline during editing can reset the browser's
   delta state. The handler also treated every False value in the returned frame
   as an explicit deselection, so a partial/stale editor result could remove
   earlier selections and leave only the latest row. The first new regression
   demonstrates that the input baseline changed during checkbox-only reruns.
2. Successful SQLite writes were followed by replaying buffered Streamlit progress
   updates before reaching the controlled refresh. A failure in this post-commit UI
   work fell into error handling with the already-rendered old table still visible.
   Clear Selection caused another rerun and exposed the saved values. The second
   new regression reproduces **five committed drafts with an unchanged visible
   table** when the post-commit progress update raises; it failed before the fix.

Both reproduced failures are corrected without changing detection, Google requests,
translation quality, caching policy, consent rules or approval rules.

## Fix

- The editor now has an immutable, page-sized input snapshot for each generation.
  Its generation changes when filters, page, SQLite values or an explicit refresh
  changes. Leaving and returning to a page creates a fresh widget identity, preventing
  delayed edits from an older view being replayed into a different record order.
- Only explicit Select checkbox deltas are merged. Missing entries mean unchanged,
  not deselected. Positional editor messages are resolved against their immutable
  page snapshot and converted to stable dataset/revision/row/field IDs. Other pages
  and the other dataset remain selected. Review snapshots retain existing optimistic
  stale-record checks.
- The selected-record count is rendered after applying checkbox deltas, so it agrees
  with the cost preview and handler in the same rerun.
- After the existing engine returns from committed writes, the UI records its outcome
  and goes directly to one controlled `st.rerun()`. It does not replay fallible
  progress updates or perform a second local selection/epoch refresh first.
- On the next render, the existing completion receipt reconciles only affected
  selected snapshots, invalidates the current editor snapshot once and queries
  SQLite again. A fresh editor generation displays the committed English values
  and Translated — Review statuses. Other selections are retained for later batches
  or review. No Clear Selection, manual reload or navigation is needed.
- Search, dataset/status filters and valid page numbers are preserved. If the result
  set shrinks below the current page, the page is clamped to the closest valid page.
  A Translation Needed filter intentionally hides newly completed rows; choose All
  or Translated — Review to inspect those drafts. The filtered table updates to its
  correct new result set rather than retaining old rows.

The existing in-flight guard, completion receipt, explicit batch-scoped consent and
cache/deduplication remain in effect. Rerunning the page never starts another paid
request. Original names, approved translations, audit entries, workspace boundaries,
reconciliation and Final Value rules are unchanged.

## Batch behavior and outcome reporting

The limit applies to unique eligible text/language pairs, not the count of selected
cells. The cost-preview area now states selected records, records in this batch,
skipped records and records remaining beyond the limit. When a selection spans
multiple batches, compact Master/Source row references identify the current and
remaining batches.

Results report drafts generated, failures, cached/reused drafts, skipped records
and eligible unique names remaining. Cached/reused includes duplicate occurrences
sharing one draft. Existing drafts and approved translations are skipped. Failed
rows remain selected for an explicitly authorized retry; successful rows remain
selected with current snapshots for review, without being retransmitted.

With a limit of at least five unique names, five selected eligible unique names
produce five drafts in one batch. With a limit of two, the tested five-name selection
advances as **2 + 2 + 1**, requiring new authorization each time. The existing backend
continues to interleave selected Master and Source work fairly.

## Verification

Full command: `.venv/bin/python -m pytest -q`

**476 passed in 101.37 seconds**, including the real Streamlit HTTP startup and
application execution/import checks. No live paid Google API calls were made.

The ten new test cases cover:

- Immutable editor input during checkbox-only reruns.
- A failed post-commit UI progress update cannot block the table refresh.
- One selected record and five sequentially selected records through the real UI.
- Stable IDs, partial checkbox deltas, explicit deselection and Master/Source rows
  with the same positional row number.
- Batch membership, limit handling, reauthorization and 2 + 2 + 1 advancement.
- Existing approved translations and cached translations, with preserved audit history.
- Partial Google failures with immediately updated statuses and fresh retry consent.
- Selection across Master/Source, search, dataset filters and page two.
- Status-filtered results after completion, without Clear Selection.
- No duplicate requests on rerun and unchanged uploaded names and Final Values.

Existing interruption tests now inject a rerun after completion and before refresh,
ensuring receipt recovery is still exercised. The existing failure test now requires
that no post-commit progress calls occur, retaining its persistence, usage, consent
and failure-feedback assertions. The suite includes the previous cache, approval,
Excel/audit, 52,001-row query and reconciliation safeguards.

## Modified files

Production:

- `rta/translation_ui.py`: immutable editor generations, delta-based selection,
  current selection counts, batch membership/outcome captions and direct post-commit
  rerun with one receipt-driven refresh.
- `rta/translation_workspace.py`: stable-ID checkbox merging, compact batch row
  references and scoped reads of committed batch outcomes.

Tests:

- `tests/test_translation_multirow_refresh.py` (new): ten regression cases.
- `tests/test_translate_selected_execution.py`: assert no post-commit progress replay.
- `tests/test_translation_execution_trace.py`: inject a rerun at the new completion/
  refresh boundary and require that the interruption was actually exercised.

Documentation:

- `docs/translation-multirow-refresh.md` (this report).
- `docs/translation-workspace-ui.md`: link current selection/refresh behavior.
- `docs/translation-execution-diagnostics.md`: distinguish the earlier progress
  buffering fix from this direct-refresh correction.

**Unchanged:** `rta/google_detection.py`, `rta/translation.py`,
`rta/translation_providers.py`, reconciliation, review/approval and export engines.
No dependencies or database schema changes were required. Saved workspace data was
not deleted, reset or modified during development.

## Manual check

Restart Streamlit to load the changed UI/workspace modules and resume the existing
workspace. Keep existing Google detections. Use All or Translation Needed, select
five eligible company-name rows and verify the preview says five records in the
batch. Ensure Names per batch permits all five unique names; inspect the row
references if using a smaller limit. Authorize the displayed batch and translate.

Under All, the main table must immediately show five English drafts with
Translated — Review. Under Translation Needed, completed rows must immediately
leave that filtered view. No Clear Selection or manual refresh is required.
Manual browser acceptance on the user's live workspace remains separate from these
mock-only integration results.
