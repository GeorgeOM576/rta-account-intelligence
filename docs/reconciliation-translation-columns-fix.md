# Run Reconciliation: visible approved translations and current statuses

## Root cause and traced data flow

The previous integration did load current SQLite records into `ApprovedNames`, pass approvals to local reconciliation, and use `result_row()` directly in the Streamlit dataframe. There was no fixed dataframe column whitelist dropping translated values.

The serialization order was the visibility defect: **Master Approved English Translation was column 55 and Match Basis was column 59**. Streamlit initially displayed the original leading columns, leaving these additions far to the right. The two requested translation-status fields and the exact Matched Source Approved English Translation column did not exist at all. `ApprovedNames` only retained approved entries, so it could not supply pending/rejected status independently from approved text. Finally, current approval context refreshed on navigation but persisted matching results had no approval-input signature: newly displayed approvals could coexist with old matching evidence without a stale-run notice.

The new real-page regression test failed before the fix: its first six dataframe columns were the old Master Identifier / Original Value / Proposed Value / Final Value / Match Status / Review Status sequence.

## Changes

The first six reconciliation/Excel columns are now:

1. Master Identifier
2. Master Approved English Translation
3. Master Translation Status
4. Matched Source Approved English Translation
5. Matched Source Translation Status
6. Match Basis

Every existing result/export column is retained. The earlier approved-translation aliases remain for compatibility. Pending, rejected, undetected and untranslated records never supply approved English text; their actual current status appears separately when a current record exists. No status is inferred when no record exists.

SQLite joins still validate dataset, upload revision, persisted row ID, field and unchanged original text. Current status records are separate from the approval-only index consumed by matching and research. No translation draft text was added to research inputs.

The four existing original/approved name comparisons, identifier precedence, collision handling and human-review policy are unchanged. The matcher now annotates each actual suggested candidate with its name basis, exposed as Suggested Match Basis 1–3. Expanded collision rows without their own name-comparison evidence have blank suggestion bases. Legacy results with no recorded basis remain blank until rerun; display code never invents a translated basis from the mere presence of an approval.

A persisted matching-input signature covers current dataset revisions, column mapping and approved values. Changed approval inputs, or legacy results with no signature, show a warning requiring Run automatic local matching to refresh candidates and Match Basis. Current translations/statuses are already visible before rerunning. Rerunning preserves human decisions, research history and audit records; it does not populate Final Value. Draft-status changes alone do not invalidate matching, since drafts cannot participate.

AI Research still reloads current workspace approvals on each navigation. A regression test saves reconciliation without a translation, subsequently approves the name in SQLite, opens AI Research without rerunning reconciliation, and captures the current original/approved names at the real consent-controlled action boundary. Providers remain mocked and authorization controls are unchanged.

## Actual Streamlit table proof

[Captured dataframe](reconciliation-translation-table-proof.json) was extracted from the actual `app.py` Streamlit AppTest dataframe immediately after clicking Run automatic local matching. Google client creation and outbound provider POST calls were blocked during capture. The fictional records were approved through the existing engine approval method.

| Field | Actual rendered value |
|---|---|
| Master Identifier | Les Jardins de Provence |
| Master Approved English Translation | The Gardens of Provence |
| Master Translation Status | Approved Translation |
| Matched Source Approved English Translation | The Gardens of Provence |
| Matched Source Translation Status | Approved Translation |
| Match Basis | Master Translation ↔ Source Translation |
| Match Method | Exact — Approved Translation |
| Proposed Value | SMB |
| Final Value | blank |

The automated page test asserts these values and their leading column positions against `app.dataframe[-1].value`; this is not just a backend dictionary or workbook assertion. Another page test approves a translation through the existing Translation Intelligence form, navigates back, observes the current columns and stale notice, reruns matching, and observes the updated basis/proposal with the notice removed.

## Tests

- New table/status/staleness/approval/research/Excel tests: **11 passed**.
- Previous approved-name integration suite with the new rendered-table test: **21 passed**.
- **Full regression suite: 507 passed in 112.68 seconds.** Both Streamlit startup checks passed: application execution/import validation and real local HTTP server health. No tests failed.
- Existing Excel safety assertions now locate Final Value and Evidence URL 1 by header rather than the retired D/S column positions. Assertions still check pending Final Value suppression, approved Final Value, formula safety, hyperlinks and formatting.
- No live Google, OpenAI or Tavily calls were made. No dependencies were added.

## Files modified

- `app.py`
- `rta/approved_names.py`
- `rta/export.py`
- `rta/translation_matching.py`
- `tests/test_reconciliation_translation_columns.py` (new)
- `tests/test_core.py`
- `docs/reconciliation-translation-columns-fix.md` (new)
- `docs/reconciliation-translation-table-proof.json` (new)

## Refresh steps and compatibility

1. Stop and restart the existing Streamlit process from this project to load updated imported modules; browser refresh alone may retain old Python modules.
2. Resume the existing workspace and open Run Reconciliation. The requested columns lead the table, and current approved names/statuses load immediately.
3. If warned that results are stale, click Run automatic local matching. No upload, database reset or cache clearing is needed.

Existing human decisions remain authoritative; their recorded match evidence is historical and is not silently rewritten. For unresolved fuzzy rows, the displayed Matched Source fields describe the leading suggestion, not a verified entity. A browser attached to an independently running older installation is outside the AppTest proof; the tested server and app execute this project's updated files.

The Translation Intelligence UI, detection/translation providers, paid consent, six review filters, SQLite history and Final Value safeguards were not modified.
