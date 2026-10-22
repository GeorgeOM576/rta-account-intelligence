# Run Reconciliation committed-result refresh

## Investigation

Compared the current branch with `/private/tmp/rta-selection-checkpoint/app.py` (before the selection fix) and the archived `app.py` in `checkpoints/before-google-detection-20261022T003646Z/workspace.tar.gz`. The available versions all end the Run Reconciliation branch after its main table. No removed lower page sections or newly introduced early return were found. As clarified by the user, no dashboards, conflict sections or account-detail sections have been added.

Baseline app and reconciliation translation tests: 12 passed. A synthetic actual Streamlit click produced ten saved results, exactly 31 visible columns and no exception. Consequently, the user's complete incomplete/unresponsive-page symptom was not reproduced as a general failure, and there is no evidence that the 31-column cleanup itself caused an engine failure. The projection is used only at rendering; downstream code receives complete Result objects. Selection changes are confined to other page branches.

A concrete stale-render defect was reproduced against the pre-fix app: a reviewer approved a fictional record while local matching was executing. `Store.save()` correctly preserved the newer decision, but the handler continued rendering pre-save Result objects. The visible Final Value was blank while SQLite held `Healthcare`. The handler had no post-commit reload. Separately, matching/save exceptions were uncaught and could interrupt table rendering. The existing completion message was transient and needed to be carried across the new refresh rerun.

## Targeted fix

Only the Run Reconciliation action in `app.py` changed:

1. Call the existing reconciliation engine, including original names and approved translations.
2. Retain human decisions and research using the existing helper.
3. Build a separate save payload, preserving the previous session payload on failure.
4. Commit through the existing `Store.save`, retaining its concurrent reviewer safeguards.
5. Set a workspace-scoped one-use completion notice and perform one controlled Streamlit rerun.
6. The normal page-load path reloads SQLite, refreshes current approved-name context, renders the existing success message and displays the exact 31-column table.
7. On matching/save failure, display a concise error and continue rendering the previously saved results; no success notice is generated.

The button is not replayed on rerun. No new UI sections, visible columns, providers, matching policies, approval rules, exports or database migrations were introduced. Translation Intelligence and Review selection code were not modified. No paid calls were made.

## Regression evidence

Five new tests exercise the actual app and button path with blocked external services:

- Matching executes once, saves full results/internal candidate and translation context, and displays all 31 columns in CSV order.
- A newer reviewer decision preserved by SQLite appears immediately in the actual table and session payload. The engine is not called again on refresh.
- Matching failure preserves saved results, displays an error and permits downstream navigation.
- Save failure does the same without displaying uncommitted proposals.
- Approved Master and Source translations still produce translation-based matching, visible approved English text, pending proposals and blank unapproved Final Values.

Existing and new tests additionally verify search, ordinary reruns and navigation to AI Research, Review & Approvals, Export Results and back. No missing lower sections are presumed or invented.

**Complete suite: 547 passed in 166.57 seconds.** This includes the Translation Intelligence and review selection regressions, exact-column tests, actual app startup/import check and a real local Streamlit HTTP startup health check.

## Files changed

- `app.py`
- `tests/test_reconciliation_page_completion.py` (new)
- `docs/reconciliation-page-refresh-fix.md` (new)

The pre-edit app is preserved at `/private/tmp/rta-reconciliation-page-checkpoint/app.py`. Restart Streamlit to load the handler change, open Run Reconciliation and click Run automatic local matching. The saved table and completion message should appear without manual refresh. No reupload or cache clearing is required. Validation used fictional data and mocked services; the user's live browser/workspace was not directly observed.
