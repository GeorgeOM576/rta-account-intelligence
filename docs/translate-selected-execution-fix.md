# Translate Selected: silent submit investigation and fix

> **Latest execution fix:** [Post-response interruption diagnostics](translation-execution-diagnostics.md) addresses reruns during progress updates after Google responds. The earlier stable-form fix alone did not protect draft persistence. Validation: 466 tests passed; no live paid calls.

## Reproduced root cause

The translation form was keyed with a digest of the complete selected-record
snapshots, cost preview, batch limit and UI epoch. Its submit button therefore
belonged to a different form whenever any of those inputs changed.

Streamlit processes incoming widget state before running the script. When a table
selection edit or batch-limit change arrived in the same update as a click on the
previously rendered Translate Selected button, the script computed a new form ID.
The incoming submit event belonged to the old form, so `form_submit_button()`
returned false. Its handler never reached progress creation, Google execution,
SQLite writes or the refresh notice. This reproduces the reported complete silence.

Two new regression cases reproduce this exact event ordering: selection + submit,
and batch-limit change + submit. Both failed before the fix because there was no
error, progress or success response. A third case verified that a disabled button
could not deliver the requested explanation for an empty selection. All three
passed after the fix. Previous tests had staged row selection as a separate completed
rerun before submitting; they did not cover changed preview and submit together.

The organization-name permission was not responsible. The UI already passes
`allow_names=True` to preview and execution. The engine defaults were enabled in
the preceding follow-up and remain enabled. The obsolete checkbox/session value
is not consulted, and tests continue to set it to False deliberately.

## Targeted changes

The translation form and submit now have stable workspace-specific identities.
Only the consent checkbox is keyed to the exact selected snapshots, preview, limit
and epoch. Thus a changed preview cannot silently discard the click, and permission
for an old batch cannot authorize a changed one. Instead the user sees a request
to confirm the new batch. Paid calls still require a matching explicit checkbox
and submit; page loads and reruns never authorize calls.

Translate Selected remains clickable so every click can respond:

- Empty selection: **Select at least one account.**
- Ineligible selection: explains English names, missing/unsupported languages,
  existing drafts/approvals, excluded fields or rejected drafts as applicable.
- Eligible without current consent: visible authorization request beside the
  existing names/cost preview; no provider dispatch.
- Authorized: the existing `TranslationEngine.process()` and
  `GoogleTranslationProvider` execution path runs unchanged. It validates selected
  snapshots before dispatch, reuses workspace caches, records usage, writes drafts
  to SQLite and refreshes the main table and selected snapshots.
- Completed batch: visible draft/failure/remaining counts; failures are warnings,
  rather than success-styled notices. Retry requires fresh consent.
- Runtime/storage failures: visible sanitized error explaining recovery; provider
  exception payloads and credentials are not displayed.

Selection state continues to use stable dataset/revision/row/field identifiers.
Rows are not cleared by the translation click. Explicit deselection affects only
that row; selections survive normal reruns and batch advancement. Stale selections
are still rejected by the existing optimistic database checks before paid dispatch.

No detection code, detection form, classification policy, translation provider,
Google request implementation, caching policy, approval logic, database schema,
reconciliation logic or Final Value logic was modified. Existing English drafts
are preserved and only selected eligible occurrences can change.

## Validation

Focused verification: **35 passed**. New tests cover batched-widget submit races,
empty/ineligible click feedback, selection persistence, reauthorization after a
preview changes, batch advancement, mocked permission failures, progress callbacks,
SQLite Failed/Translated — Review statuses, table refresh, usage accounting,
redacted runtime failures and no duplicate/unconsented dispatch.

Full verification: `.venv/bin/python -m pytest -q` — **456 passed in 86.25
seconds**, including the real localhost Streamlit HTTP health check and application
execution/import startup checks. No tests failed.
All Google calls use mocks; no live paid API calls were made. Existing user workspace
data was not edited during debugging.

## Files changed

- `rta/translation_ui.py`: stable translation form/submit identity, preview-scoped
  consent, visible click feedback and eligibility reasons, warning/error reporting.
- `tests/test_translate_selected_execution.py` (new): seven execution regressions.
- `tests/test_translation_button.py`: assert click feedback rather than a disabled
  button; retain eligibility, consent, cache and approval assertions.
- `tests/test_translation_workspace.py`: update button availability expectations;
  retain page/selection, stale checks, draft/approval and export assertions.
- `tests/test_organization_draft_defaults.py`: update button availability expectations;
  retain both-dataset translation without hidden toggles, consent and draft assertions.
- `tests/test_translation_e2e.py`: expect failed batch counts in a warning.
- `docs/translate-selected-execution-fix.md` (this report).
- `docs/translation-workspace-ui.md`: link current click/consent behavior.
- `docs/organization-name-draft-permission.md`: clarify the subsequent form-identity fix.

## Checking the corrected page

1. Restart Streamlit to load the updated UI module and resume the intended workspace.
2. Keep existing Google detection results. Select desired foreign-language rows in
   Master, Source or both. Selection is independent of the dataset/status filters;
   Select all visible rows selects only the current page.
3. Inspect the number of names and cost. Authorize the displayed batch, then click
   Translate Selected. If the selection/limit changed with the click, inspect the
   refreshed preview, authorize it and click again. The intervening click must show
   the authorization explanation and make zero paid calls.
4. Observe processing and the draft/failure summary. Successful rows show separate
   English text with status Translated — Review. Drafts remain unapproved and
   original names and Final Values remain unchanged.
5. Click with an empty or ineligible selection to verify explicit feedback. Review
   existing drafts instead of retransmitting them. Further batches need new consent.
