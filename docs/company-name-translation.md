# Translate all selected foreign-language company names

**Current Google policy:** [Google-direct v4](google-direct-translation.md) accepts valid supported Google language codes. Low confidence and ambiguity are advisory and do not block non-English drafts. Historical descriptions of confidence-based exclusion below are superseded; independent translation, approval and full-export behavior remain applicable.

## Behavior and independence from reconciliation

Detection and translation operate on uploaded Master/Source values and selected
text fields. They never require a match, a recommendation, or a reconciliation
run. Every confidently foreign company name in those fields, including
Master-only, Source-only and unmatched names, can receive an English draft.
English, undetermined and unconfirmed ambiguous names are excluded. A reviewer
can explicitly confirm an ambiguous non-English source language and include it
in the next separately authorized batch.

The existing translation engine already had this independent behavior. This
change makes the workflow explicit, adds coverage and review tools, and removes
the reconciliation prerequisite from the Export Results page. Matching logic,
OpenAI/Tavily integrations and all six reconciliation review filters are unchanged.

Original uploaded names remain immutable. English values live in separate
translation records and export-only columns. Google drafts, including cached
drafts reused on another occurrence, initially enter **Translated — Review**.
Only approved translations are available to translation-aware reconciliation;
translation approval does not approve a reconciliation decision or set Final Value.

## Overview and actions

The new overview groups exact unique company names in selected account-name
fields across both datasets. It displays total names, English names, confident
or confirmed foreign names, names with English values, approved names, names
pending translation review, ambiguous/manual-review names, detection and
translation coverage, remaining undetected names, remaining untranslated foreign
names and remaining unprocessed names.

For duplicate names, coverage and approval require every selected occurrence to
be covered/approved. Individual approval is never inherited from the cache.
Detection coverage includes completed detection, manual confirmation and
structural exclusion outcomes; it is not a claim that every detection is
confident. Low-confidence results still appear separately in manual review.
Translation coverage measures draft-or-approved English values for known foreign
names, not approved reconciliation coverage. Blank names are excluded from the
company-name overview.

The interface has separate numbered sections:

1. **Detect Languages with Google**: current dataset/field scope, exact-value
   deduplication, workspace-scoped raw detection cache, cost preview, explicit
   consent and request progress. Google remains primary; confidence and Unicode
   script policy are unchanged.
2. **Translate Foreign-Language Names with Google**: organization-name draft
   permission, dataset scope, provider/batch limit, eligibility diagnostics,
   separate paid cost/consent, progress and completed/failed/remaining counts.
   The existing submit button label is retained for compatibility. Organization
   permission remains a separate explicit safeguard, not a match requirement.
3. **Review and Approve Translations**: manual language confirmation, individual
   approval/correction/rejection and selected bulk approval.

## Batches, cache and usage

Exact original text plus effective source language is deduplicated for
translation, with Master/Source interleaving. Provider/model/target/policy cache
keys remain workspace-isolated. Drafts and approvals leave the next batch's
eligibility set, so successful batches advance. Both pre-run remaining unique
names and post-run remaining eligible names are shown. Failures remain retryable
only through a newly authorized action; they are included conservatively in
usage as before. Cached-only batches need no Google request and still produce
review drafts, not automatic approvals.

Every paid detection and translation batch retains separate explicit consent.
No API call occurs on upload, page load, review or export. Monthly detection and
translation usage, uncertain submissions, configured allowance and shared-credit
estimates are unchanged. Those estimates are not actual Google billing or a
guaranteed project-specific free quota.

## Rejection and bulk approval

An individual unapproved draft can now be rejected. Its English value moves to
`draft_english`, current English is cleared, and status becomes **Rejected
Translation**. The audit event retains before/after snapshots. Rejected drafts
cannot contribute to matching or silently retry. A reviewer can correct and
approve an English value manually, or explicitly confirm its source language to
requeue it for a subsequent translation batch. Historical provider cache entries
remain intact; requeueing may therefore reuse a cached draft for human correction.

Bulk approval is restricted to explicitly selected drafts on the current page,
with a named reviewer and confirmation covering every selected English value,
proper name, legal suffix and identifier. It rejects unknown/English languages,
excluded fields, absent English values, non-drafts and duplicate selections.
SQLite validates each expected record, current upload revision and selected field
inside one transaction. If any record changed, the entire batch and its audit
events roll back. Approved translations and manual corrections are never replaced
by a bulk operation. Each approved cell has its own audit event.

## Full Excel export without reconciliation

Export Results is now available after dataset upload, even when reconciliation
results are empty. The workbook retains its existing sheet structure, including
both complete original account datasets with separate English/language/status/
provider columns. Missing current analysis is labelled Not Analysed in generated
translation columns. Disabled classification/identifier fields do not gain
translation columns. Original row values, names and suffixes are preserved.

Translation Details includes current selected enabled cells, both translated and
untranslated, with explicit columns **Original Company Name**, **Detected
Language**, **English Translation**, **Translation Status**, and **Translation
Provider**, alongside the existing technical and audit metadata. Confident
English and ambiguous rows are included, not filtered to translation candidates.
Historical revisions remain stored and are not confused with current coverage;
audit history retains review decisions. Empty reconciliation sheets do not
imply omitted account rows: Master Translations and Source Translations contain
the complete uploaded datasets.

## Files changed

- `app.py`: permit the existing full Excel export before reconciliation.
- `rta/translation.py`: overview, remaining-work reporting, atomic review helper,
  selected bulk approval, explicit draft rejection and export status defaults.
- `rta/translation_ui.py`: overview and separated actions, translation progress/
  remaining counts, selected bulk approval and individual draft rejection.
- `rta/export.py`: explicit business-facing translation columns and full
  translation export sheets even when current analysis is empty.
- `tests/test_company_translation.py`: five new mocked end-to-end/regression
  tests for independent processing, review safety, export and isolation.
- `docs/company-name-translation.md`: this report.

No dependency changes. Existing SQLite records were preserved; no migration,
database deletion, historical-row deletion or live Google calls were performed.

## Manual workflow

Restart Streamlit and resume the workspace. Upload/map the intended datasets and
select both company-name fields in Translation Intelligence. Reconciliation is
optional. Detect with Google in explicitly confirmed batches until coverage is
complete; review ambiguous names separately. Enable organization-name draft
permission, choose Both and Google Cloud Translation v3, then translate in
separately authorized batches. Review/correct/reject English drafts or explicitly
select and confirm a page of drafts for bulk approval. Export the full workbook
at any point from Export Results. Run translation-aware reconciliation later,
using only approved translations, if desired.

## Limitations

- Processing remains synchronous and user-triggered; there is no unattended
  paid run or automatic continuation into the next batch.
- Coverage concerns selected company-name fields. Choose every intended Master
  and Source name field; excluded/nonselected fields are not silently enabled.
- Native translation may preserve, transliterate or inadequately render a brand.
  Existing protected identifier/legal-suffix checks can fail a draft; human
  review remains required and original official names are never replaced.
- Ambiguous and rejected names require human action. Failed requests can remain
  in the eligible set; their reasons/usage should be reviewed before retrying.
- Bulk selection is page-scoped (50 displayed records), not an unreviewed
  approve-everything operation.

## Validation

Focused tests: **19 passed**, including the new company-name workflow and the
existing stale-detection/export regressions. New coverage verifies unmatched,
Master-only and Source-only companies, duplicate deduplication, English and
ambiguous exclusion, manual confirmation, cached draft reuse, 2/2/1 unique-text
batch progression, rejection/correction, selected UI approval, atomic rollback
on a stale selected cell, workspace isolation and complete Excel exports before
reconciliation. Google SDK responses are mocked throughout.

Complete regression suite: **387 passed, 0 failed, 0 errors in 77.69 seconds**.
This includes the real Streamlit server health/startup check, application
execution, existing review/export tests and all six reconciliation filters.
Existing test assertions were retained. No live API calls were made.
