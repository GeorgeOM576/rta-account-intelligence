# Approved translations across workflow pages

## Root causes

- AI Research constructed a separate account table without the shared translation projection.
- Review & Approvals used the shared result table but did not reload current SQLite translation context when navigating to the page.
- Export already used the common result projection, but needed the same explicit original-name columns and consistent current-state handling.
- The previous projection defaulted to the first suggested Source whenever a reviewer had not selected one. This incorrectly labeled fuzzy-only suggestions as matched accounts.

## Implementation

`rta.export.translation_columns()` supplies the shared leading columns to Run Reconciliation, AI Research, Review & Approvals and Export Results:

1. Master Identifier
2. Master Approved English Translation
3. Master Translation Status
4. Matched Source Approved English Translation
5. Matched Source Translation Status
6. Match Basis
7. Master Original Name
8. Matched Source Original Name

The existing first six Run Reconciliation columns retain their order. All previous result/export fields and AI table aliases remain. Proposed Value, Final Value, review status, recommendations, evidence and candidate columns remain separate from translation approvals.

All four pages use the same workspace-scoped SQLite record loader and `ApprovedNames` join. The join checks current upload revision, persisted row ID, field and original text. Only approved English text is projected into approved-value columns. Current status is loaded independently, so pending/rejected/revoked translations have the correct status and blank approved text. Page navigation reloads state; no cache reset or reupload is needed.

The review table uses shallow display copies enriched with current translations, avoiding a deep copy of saved research/audit structures. The persisted record versions used by individual/bulk approval checks remain untouched. No review, reconciliation, detection or translation engine was changed.

Matched Source columns now resolve an actual local match, supported research recommendation or explicit reviewer-selected Source record. They never fall back to an unrelated fuzzy candidate. Selected Source identities are validated against the current dataset/mapping fingerprint and original account. The shared loader computes that full dataset fingerprint once, reusing it for every reviewed row; a 100-row regression verifies this and rejects stale Source revisions. Ambiguous duplicate/conflict rows remain blank unless an explicit valid Source association exists. Candidate columns and their actual match bases remain available separately. Match Basis preserves the recorded reconciliation evidence: choosing a different Source through research or human review does not fabricate a new translation-based comparison. Existing Selected Source and AI Recommended Source fields identify those later decisions.

Reconciliation stale-input warnings also appear on the remaining workflow pages, with the existing instruction to rerun local matching safely. A separate notice identifies historical AI findings whose approved-name context differs from current inputs, even after local matching has been rerun. No notice triggers paid research or changes human decisions.

AI Research still receives current original and approved English names as context. Existing research consent, request budgets and approval controls are unchanged. Reliable local matches retain their existing exclusion from the main AI Research account table.

## Excel and current values

Export preview and workbook share the same projection and current SQLite input snapshot. The existing filtered `translations` export argument is preserved; an optional `current_translations` argument supplies status context from that same snapshot without reactivating excluded fields. All existing workbook fields, worksheets, formatting, audits and formula protections remain. The downloadable workbook is captured at the actual Streamlit download construction boundary in the integration test and compared against the rendered preview.

The Translation Details sheets continue to omit excluded fields. Current status context remains available for reconciliation display without making excluded fields active translation candidates.

## Real page proof

[Captured workflow tables and Excel values](workflow-translation-display-proof.json) contains values extracted from the actual `app.py` Streamlit AppTest tables, not isolated backend dictionaries. During capture, Google client creation and outbound provider POST requests were blocked.

Every workflow page and the workbook show:

| Field | Value |
|---|---|
| Master Original Name | Les Jardins de Provence |
| Master Approved English Translation | The Gardens of Provence |
| Master Translation Status | Approved Translation |
| Matched Source Original Name | Jardines de Provenza |
| Matched Source Approved English Translation | The Gardens of Provence |
| Matched Source Translation Status | Approved Translation |
| Match Basis | Master Translation ↔ Source Translation |
| Proposed Value | SMB |
| Final Value | blank |

## Verification

New workflow regression cases: **14** (including real-page rendering and the scaling check). Workflow display plus existing detection-refresh/export compatibility tests: **27 passed**. Final focused workflow, bulk-review and Source-selection checks: **51 passed**.

Coverage includes:

- Current approved Master and Source names on all four pages and the downloadable workbook.
- Original names, status values and Match Basis with identical shared column order.
- Pending/rejected translations remaining blank in approved-value columns.
- Unmatched fuzzy suggestions retaining candidate fields while matched-Source fields remain blank.
- Corrections and revocation appearing on subsequent navigation with stale-result notices.
- Workspace isolation, including deliberately copied stale display context.
- Manual verification and explicit Source approval, with unchanged atomic record-version checks.
- All six existing review filters and Final Value remaining blank until a human decision.
- A reviewer selecting a different Source account displays that account's own approved translation.
- Saved research context remaining visibly stale after a local matching rerun.
- Newly supported research Source associations appearing immediately after the consent-controlled mocked action.
- Excluded status visible in the reconciliation columns while excluded fields remain omitted from Translation Details.

**Full regression suite: 521 passed in 131.37 seconds.** Both Streamlit startup checks passed: actual app execution/import validation and a real local HTTP server health check. No tests failed.

No live Google, OpenAI or Tavily calls were made. No dependencies, database columns or migrations were added. Existing records and historical audit data were preserved.

## Files changed

- `app.py`
- `rta/approved_names.py`
- `rta/export.py`
- `tests/test_workflow_translation_display.py` (new)
- `tests/test_reconciliation_translation_columns.py` (unmatched Source expectations updated for the new explicit requirement)
- `docs/workflow-translation-display.md` (new)
- `docs/workflow-translation-display-proof.json` (new)

Restart the existing Streamlit process once to load the changed imported modules, resume the workspace, and open the workflow pages. No paid call occurs on page load. If existing results are stale, run local matching; it preserves existing human decisions and audit history.
