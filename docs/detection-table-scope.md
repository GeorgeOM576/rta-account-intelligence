# Detect Languages respects table filters and checked rows

## Root cause

Translation Intelligence called `workspace.detection_plan(limit)` and `workspace.run_detection(limit, consent)` without any table state. Both helpers hardcoded Master and Source, and the planner read the full workspace. Table filtering and selection therefore affected the displayed rows but not the paid detection batch.

## Targeted change

The existing Google detection engine now receives a SQL-backed scope adapter:

- With checked rows, intersect their stable `(dataset, revision, row_id, field)` identities with the active dataset, search and status filters. Hidden selections are excluded. If all selected rows are hidden, the batch is empty; it does not fall back to detecting unselected rows.
- Without checked rows, include all records matching those same SQL table filters across every pagination page.
- Deduplicate names and reuse the existing workspace-isolated raw Google cache. Apply the existing batch limit after deduplication/cache lookup.
- Show scoped record count, unique pending names, cached names, estimated batch cost and the existing authorization checkbox. Explain empty filtered/selected/cached/ineligible batches.
- Bind the confirmation form to the filters, selected IDs, dataset revisions, cell manifest and exact preview. Revalidate both the scope and the actual plan before constructing the paid batch. Stale scopes/cache-dependent plans require new authorization.
- Persist detections only to scoped cells whose texts were processed. An optional cell restriction in the existing detection writer prevents a same-name row outside the scope from being updated by this action. Classification rules, providers, human-state preservation and translation processing remain unchanged.

The existing Translation Intelligence layout, translation-selection behavior, progress feedback, monthly accounting and consent remain. No Run Reconciliation, AI Research, Review & Approve, export or 31-column schema files were edited for this task. No live paid calls or workspace database modifications were performed during development/testing.

## Verification

Eleven new mocked regressions cover Master/Source/All requests, five checked IDs across datasets, search/status intersection, hidden selections, cache reuse, limits, stale previews, missing consent, cross-page filtering, immediate refresh, deduplication and stable-ID-bound authorization even when texts are identical.

Actual Streamlit tests verify:

- Master filter with 30 records over two pages sends exactly 30 Master names, including the five records beyond the visible first page. No Source-only names are sent.
- Five editor checks send exactly those five names.
- A filter change resets consent; clicking without reconfirming makes no request.
- A filtered selection includes only visible-scope checked records. Switching to Source while all checked rows belong to Master produces an empty disabled batch.
- Completed/cached batches make no duplicate request on rerun.

Existing targeted Google/workspace tests: **40 passed**. Scoped detection plus translation multirow/selection checks: **26 passed** before the final additional duplicate-ID regression.

Complete final suite: **565 passed; one startup check was blocked by sandbox localhost socket permissions** (189.88 seconds). Rerunning both startup tests with localhost permission: **2 passed** (3.25 seconds). Thus all **566 distinct tests** were verified, including the initially blocked HTTP startup check; no application regression remains.

## Files changed

- `rta/translation_ui.py`
- `rta/translation_workspace.py`
- `rta/google_detection.py`
- `rta/translation.py` (optional detection-cell scope only)
- `tests/test_detection_table_scope.py` (new)
- `docs/detection-table-scope.md` (new)

No new dependencies or database migrations. Pre-edit detection files are preserved at `/private/tmp/rta-detection-scope-checkpoint/`. Restart Streamlit to load the changed modules, select the intended filter or check rows, review the scope/cost summary and authorize that batch. No paid call occurs on page load or rerun.
