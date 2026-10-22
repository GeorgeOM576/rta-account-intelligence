# Translation and Review selection synchronization

## Root causes

Translation Intelligence consumed editor checkbox patches only after computing a new editor generation from current database rows, filters and refresh epoch. A refresh could retire the widget holding pending selection edits before those edits reached the authoritative selected-record mapping. The old implementation also replayed cumulative checkbox patches unconditionally, with no callback or consumed-event tracking. Returning a checkbox to its original value can remove its patch entirely; this must be reconciled against the immutable baseline.

Review & Approve keyed both row widgets and selected IDs by search, status and the current filtered record list. Filtering created different selection buckets for the same accounts. Each rerun also assigned checkbox values from a previously captured selection set before rendering the widgets; bulk controls subsequently read that earlier set. These parallel representations could disagree with delivered widget values. Callbacks referred to script-level mutable scope variables instead of binding their selection scope and record IDs explicitly.

## Fix

`rta/selection_state.py` provides a shared authoritative mapping adapter. Checkbox callbacks bind the workspace selection key, stable record identity and widget key. Changes are idempotent; selected translation snapshots remain intact for optimistic review checks.

Translation captures pending edits before retiring an editor generation and also registers an immediate editor callback. Positions resolve only through that generation's frozen stable-ID manifest. Cumulative callbacks handle removed patches (deselection back to the baseline), ignore callbacks from retired widgets and do not replay consumed selection patches on text-only edits. Immutable editor input, batch-scoped authorization and the existing SQLite post-commit refresh remain in place. Existing browser views without the new identity manifest are upgraded safely.

Review uses one selection map per workspace and Master upload revision, with row widget keys independent of filters and pages. Widgets are initialized only when absent, and their returned values synchronize selection before bulk controls calculate eligibility. Select All updates both the mapping and native checkbox state. Filtering preserves checks, but only checked accounts in the current filter participate in the action; a caption explains excluded selections. Existing off-page confirmation, saved-decision overwrite checks, atomic stale-record protection and audit recording remain unchanged. Ineligible approval rows show counts and the existing backend eligibility reasons before submission.

The six review filters, page order, exact 31-column visible workflow schema, Translation Intelligence layout, engines, exports and Final Value rules are unchanged. No database migration or deletion is required. Restart Streamlit to load the updated translation module; no cache clearing or Clear Selection workaround is required.

## Verification

- Targeted selection, multirow translation, review layout and bulk review tests: **33 passed**.
- Complete regression suite: **542 passed in 166.83 seconds**.
- Full suite includes app import/execution checks and a real local Streamlit server HTTP health check.
- Five selected Master/Source translation rows survive editor regeneration, produce five persisted review drafts through one mocked request and appear immediately in the main table. An additional rerun makes no duplicate request.
- Five native Review checkboxes immediately enable bulk saving; explicit approval or rejection affects exactly those five records and creates five audit entries. Unselected records retain blank Final Values.
- Tests also cover rapid consecutive checkbox edits, deselection, hidden account lists, filtering, pagination, cached/existing drafts, partial failures, consent invalidation, clearing and workspace isolation.
- One existing filter test was updated to require preservation of its checked row instead of forgetting it after filtering; its assertions that only the filtered account is saved and audited remain intact.
- Translation interaction tests feed Streamlit's actual data-editor widget-state protocol because AppTest does not provide an editor cell-edit convenience API. They exercise the real page action, mocked provider, SQLite persistence and refreshed table. Native review checkbox tests use AppTest check/uncheck and button interactions.
- No live paid service calls were made.

## Files changed

- `app.py`
- `rta/translation_ui.py`
- `rta/selection_state.py` (new)
- `tests/test_selection_synchronization.py` (new)
- `tests/test_bulk_review.py`
- `docs/selection-state-fix.md` (new)

The checkout has no Git metadata, so a pre-edit backup of the two production files is retained at `/private/tmp/rta-selection-checkpoint/`. Existing workspace data and unrelated changes were preserved.
