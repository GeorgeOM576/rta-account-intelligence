# RTA V3 — Translation Intelligence end-to-end test report

Date: October 21, 2026 (America/Toronto).

Result: **279 tests passed, 0 failed**, including the two new fictional end-to-end
scenarios, application import/execution checks and the real Streamlit HTTP health
check. No live Google API calls were made.

## Inputs and automation boundary

The committed fixture directory is
[`tests/fixtures/translation_intelligence`](../tests/fixtures/translation_intelligence/README.md).
It contains `fictional_master_accounts.xlsx`, `fictional_source_accounts.xlsx`,
`expected.json`, a reproducible `generate.py`, and scenario documentation.
Both Excel files contain 12 invented accounts, identifiers, segments and Trading
Name aliases. They include English, French, Spanish and German names, exact and
spelling-variant matches, and unrelated unmatched businesses. Master identifiers
start with `M-`, Source identifiers with `S-`; the UI mapping explicitly uses
Account Name for matching and Segment for comparison.

`tests/test_translation_e2e.py` executes real application code through Streamlit
AppTest. The uploader's return values are injected because AppTest does not
support browser file selection. The actual Import uploaded datasets button,
XLSX parser, mapping form, detection, Google provider adapter, SQLite persistence,
translation approvals, reconciliation, account review and Excel exporter run.
The Google SDK client factory is replaced with a mock before the app starts,
and ordinary HTTP requests are blocked in these scenarios. Credentials and live
Google services are neither needed nor consulted.

## Workflow results

| Check | Observed result |
| --- | --- |
| Import and mapping | Both actual XLSX inputs parsed into 12 rows; original uploaded values preserved; Account Name and Segment mapping saved through the UI. |
| Independent detection | Five Master and five Source names require translation; each dataset independently contains detected French, Spanish and German. |
| Ambiguous names | Two Master and three Source names remain Uncertain; excluded from the default Google batch. |
| Preflight cache and costs | Ten flagged cells reduce to nine unique uncached texts, totaling 258 Unicode characters. Base estimate $0.005160 before credits; $0 after assumed available credits at the default allowance. No API client is constructed during preview. |
| Consent | Submitting without confirmation shows an error and records no request. Organization-name draft permission is also required. |
| Mocked Google execution | Three language-grouped requests produce ten per-cell Translated — Review drafts; the duplicate French value is sent once. No live requests or actual charges. |
| Approval gate | Before translation approval, reconciliation is identical to the original-data baseline. Final Value remains blank. |
| Partial approval | Six one-sided translation matches work after their approvals; the French-to-Spanish pair remains unmatched until both translations are approved. |
| Approved translation matching | Eight approved cells produce seven Translation-assisted accounts: three translated Master → original Source, three original Master → translated Source, one translated Master → translated Source. |
| Proposal status | All proposals display Intelligence Proposed — Pending Approval. Translation never populates Final Value. |
| Original/fuzzy/unmatched behavior | Three original exact matches retain precedence; a spelling variant remains a fuzzy suggestion; the unmatched business receives no proposed value. |
| Cache reuse | Selecting Trading Name creates ten additional draft cells using nine persisted cache entries, with zero additional mocked requests or usage. Approvals do not transfer through the cache. |
| Account review | Account approval requires confirmation and saves Enterprise; rejection leaves Final Value blank; manual verification of the spelling variant saves SMB. |
| Six review filters | All, Intelligence Proposed — Pending Approval, Manual Review Required, Approved, Rejected, Manually Verified remain unchanged and return the expected accounts. |
| Persistence | A reconciliation rerun and a fresh Streamlit session retain the saved account decisions, translation state and usage. |
| Workspace isolation | A separate workspace has no shared translation approvals, audit events, cache entries or usage. Configuring a 1,000-character allowance in the first workspace leaves the second at 500,000. |
| Monthly accounting | Successful scenario records three simulated confirmed attempts, 258 confirmed characters and zero uncertain characters in the current local reporting month. Monthly history persists. |

The additional mocked failure scenario returns a timeout for the first German
request. Two cells become Failed, eight remain successful drafts, and 57 characters
remain uncertain. The other 201 characters are confirmed, across three attempts.
A fresh explicit confirmation retries only the failed German values in one
additional request. The report then shows 258 confirmed plus 57 uncertain
characters, four attempts, and no remaining failed cells. Previous uncertain
usage is preserved rather than silently subtracted.

The existing monthly tracker regression tests also cover month/year rollover,
reporting time zones, interrupted/uncertain attempts, transient retries, local
storage failures, warnings, configurable allowances and zero-allowance handling.

## Excel export verification

The actual Export Results page generated the workbook at
[`outputs/translation-intelligence-e2e/verified-fictional-results.xlsx`](../outputs/translation-intelligence-e2e/verified-fictional-results.xlsx).
A machine-readable summary is saved beside it as `verification.json`.
These generated outputs are intentionally ignored by Git; input fixtures are
explicitly allowed by narrow `.gitignore` exceptions.

Verified all eight sheets: Reconciliation Results, Summary, Audit Trail, Source
Conflicts, Translation Summary, Translation Details, Master Translations, and
Source Translations.

- Reconciliation Results contains 12 rows: eight pending proposals, one approved,
  one rejected, one manually verified, and one requiring manual review.
- Only the approved and manually verified rows contain Final Value. Pending,
  unmatched and rejected rows remain blank. Proposed Value remains separate.
- Translation Details contains 48 selected-cell records, including eight Approved
  Translation entries and twelve Translated — Review entries. Master/Source
  translation sheets retain original identifiers, names, segments and aliases,
  plus English values and their per-cell statuses.
- Translation provenance is present for the seven assisted accounts.
- Audit Trail contains eleven events: eight translation approvals and three
  account review decisions. Tests check reviewers, timestamps, previous/current
  translation status, and previous/new Final Values.
- All sheets retain frozen headers and Excel autofilters. The XML package contains
  neither the workspace resume token nor private-key/access-token markers.

## Defects and changes

No application business-logic defects were discovered or corrected. Production
application modules and the six review filters are unchanged. An initial new-test
failure was a test setup assumption: leaving Translation Intelligence causes
Streamlit's provider controls to return to defaults. The test now explicitly
reselects Google and organization-name permission before the next batch.

Files added or changed:

- `.gitignore`: allow the two small, fictional XLSX input files.
- `tests/test_translation_e2e.py`: complete UI workflow and timeout/retry scenario.
- `tests/fixtures/translation_intelligence/fictional_master_accounts.xlsx`.
- `tests/fixtures/translation_intelligence/fictional_source_accounts.xlsx`.
- `tests/fixtures/translation_intelligence/expected.json`.
- `tests/fixtures/translation_intelligence/generate.py`.
- `tests/fixtures/translation_intelligence/README.md`.
- `docs/translation-e2e-test-report.md`: this report.

No dependencies were added.

## Test execution

Targeted scenarios: **2 passed**.

Full regression suite: **279 passed, 0 failed in 55.92 seconds**. Both canonical
app import/execution and the real Streamlit HTTP health check passed. The initial
sandbox-only run had 278 passes and one environment failure because localhost
sockets were blocked; the complete rerun with localhost permission passed.
Google calls remained mocked throughout.

Reproduce the artifact-producing run with:

```sh
RTA_E2E_ARTIFACT_DIR=outputs/translation-intelligence-e2e .venv/bin/python -m pytest -q tests/test_translation_e2e.py
.venv/bin/python -m pytest -q
```

## Remaining limits and UAT readiness

Ready for manual user acceptance testing of the tested workflow. Streamlit
startup verification passed. Browser drag-and-drop/file selection, visual layout and
browser downloads still need hands-on checks; AppTest tests the uploader boundary
and generated Excel bytes. Mocked translations prove integration behavior, not
real translation quality or current Google IAM, quota, latency or billing state.
No mocked mode was added to the production interface.

The real language detector can label short business names Uncertain; those values
need reviewer inspection. A translation-assisted proposal remains evidence for
human review, not independent proof that two businesses are the same entity.
Monthly counts here are simulated local estimates, not actual Google billing.
The credit equivalent is configurable and assumes a share of a billing-account
credit that may also be consumed by other eligible usage outside this workspace.
