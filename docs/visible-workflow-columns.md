# Exact CSV schema for the three workflow tables

Source approved by the user: `Run Reconcillation (Updated)(in).csv`.
The header was read with Windows-1252 decoding. It contains exactly **31 unique column names**. Only its header is retained in the repository; no CSV customer rows were copied.

## Scope

Run Reconciliation, AI Research and Review & Approvals now use the same `rta.workflow_table.visible_table()` rendering projection. The payload sent to each main Streamlit table contains only these 31 columns in this order; additional backend fields are not merely hidden through a toolbar configuration.

Translation Intelligence, Export Results preview and Excel export retain their existing schemas. Matching, translation, research, review/approval handlers, stable record IDs, workspace isolation, audit history and Final Value guards were not changed. No database fields or internal result fields were deleted.

## Exact visible column order

1. Master Identifier
2. Master Approved English Translation
3. Matched Source Original Name
4. Master Original Value
5. Proposed Value
6. Final Value
7. Match Status
8. Review Status
9. Suggested Account 1
10. Similarity Score 1
11. Suggested Value 1
12. Suggested Account 2
13. Similarity Score 2
14. Suggested Value 2
15. Suggested Account 3
16. Similarity Score 3
17. Suggested Value 3
18. Research Status
19. Research Explanation
20. Evidence URL 1
21. Evidence URL 2
22. Reviewer Decision
23. Reviewer Notes
24. Reviewer
25. Reviewed At
26. Value Origin
27. Record ID
28. Parent Company
29. AI Proposed Value
30. AI Confidence
31. AI Recommendation Status

## Field mapping

`Master Original Value` uses the existing `Original Value` comparison-value field only in the display copy. It does not rename that backend/export field or substitute a company name. All other requested labels already exist in the full result projection. An unavailable requested field stays present with a blank value; empty filtered results retain all 31 headers.

The CSV intentionally omits translation status, matched Source approved translation, Match Basis, provenance and other internal fields. They remain in workspace results, current translation context, research inputs, approval validation and exports. Approved Master English Translation remains visible as required by the CSV.

Main-table projection is performed at the three render calls. Page layouts, filters, pagination, selection models, Source association, bulk and individual save calls, research authorization and API execution remain unchanged. Existing action code continues using complete Result objects rather than reduced display rows.

## Tests and proof

[Actual rendered main-table capture](visible-workflow-columns-proof.json) records the 31 column names and a fictional approved-translation row from each of the three actual `app.py` Streamlit AppTest pages. Live provider calls were blocked during capture.

Eight new regressions verify exact CSV/config agreement, correct alias mapping, blank unavailable columns, immutability of input rows, all three actual rendered tables, current approved translations, unchanged SQLite records/audit, retained hidden backend fields, full unchanged export/Excel schema, empty filtered results, and the unrestricted Translation Intelligence table.

Existing tests that formerly expected now-excluded fields in a visible table were adjusted to assert the new CSV schema and verify those hidden values independently against current backend state or full export. Existing approval, reconciliation, stale-result, research-context, audit and Final Value assertions remain.

Focused schema, translation integration and review-layout checks: **40 passed**.

**Full regression suite: 536 passed in 141.90 seconds.** Both Streamlit startup checks passed: actual app execution/import validation and a real local HTTP server health check. No tests failed.

No live Google, OpenAI or Tavily calls were made. No dependencies or database migrations were added. The application does not depend on the Downloads path at runtime; its shared schema and header-only regression fixture are included in the project.

## Files changed

- `app.py`
- `rta/workflow_table.py` (new shared rendering configuration)
- `tests/fixtures/reconciliation_table/visible_columns.csv` (new header-only fixture)
- `tests/test_visible_workflow_columns.py` (new)
- `tests/workflow_display_helpers.py` (new)
- `tests/test_reconciliation_translation_columns.py`
- `tests/test_workflow_translation_display.py`
- `tests/test_review_layout.py`
- `tests/test_approved_translation_integration.py`
- `docs/visible-workflow-columns.md` (new)
- `docs/visible-workflow-columns-proof.json` (new)

`rta/export.py`, all translation/reconciliation/research/approval engines and SQLite persistence code were not modified.
