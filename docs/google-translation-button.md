# Disabled Google translation button investigation

## Findings

The button's disabled condition is exactly `not preview['unique_texts']`. The
Google paid-authorization checkbox is checked independently at execution time;
it does not grant organization-name permission, confirm a language, or create an
eligible batch. A zero price does not independently disable the button.

Read-only inspection found the latest small workspace has **28 Translation
Needed records: 14 in Master and 14 in Source**. All are organization-name fields
and have confident foreign outcomes. An older large workspace is still pending
detection and has no Translation Needed records. No production workspace was
changed while investigating.

For the latest small workspace, the model therefore has 28 eligible cells before
name permission, but **zero eligible cells when Allow drafts for organization-name
fields is off**. Its 14 unique foreign names can form a batch only after that
separate permission is enabled. The active browser's permission, scope and
provider selections cannot be inferred from SQLite, so the investigation does
not assert which browser controls were checked. The new diagnostics calculate
and show those actual controls and resulting counts on every rerun.

The core eligibility/button condition is an intentional safeguard. The defect
was insufficient visibility into why the batch was empty, especially the
difference between name-draft permission and paid authorization, and between a
zero-cost empty batch and a zero-cost cached batch.

## Complete eligibility flow

1. `TranslationEngine.records()` reads current selected fields and upload
   revisions from SQLite; old policy records are refreshed safely as before.
   Detection persists confident foreign values as Translation Needed. Pending
   detection, low confidence and ambiguity do not become translation-ready.
2. The selected translation dataset scope filters Both, Master only or Source
   only independently of detection scope.
3. `translation_eligible` requires Translation Needed or Failed status, a known
   effective language other than English/und, an enabled field, and either a
   confident foreign outcome or explicit manual language confirmation.
4. Account-name fields and mapped identifier-name fields additionally require
   the organization-name draft permission. Paid API authorization cannot bypass
   this permission.
5. Original text plus source language is deduplicated across datasets, with
   Master/Source interleaving. The configured batch limit must be 1–5,000; the
   UI enforces a minimum of one. This task does not change translation batch
   semantics or provider execution.
6. Workspace/provider/model-scoped translation-cache lookups split the selected
   batch into cached and uncached unique texts. The estimate charges only
   uncached input characters. Fully cached eligible batches are enabled at $0:
   their cached values still enter Translated — Review and need human approval.
7. Approved translations and existing review drafts are not eligible for
   retransmission. A cache hit never approves another cell automatically.
8. Choosing Google Cloud Translation v3 displays its preview/form. Its submit
   button is disabled only if no eligible unique texts exist. When enabled,
   pressing it still requires explicit paid consent before provider preparation
   or API calls. Construction/preview never resolves ADC or makes a call.
9. SQLite remains authoritative on each Streamlit rerun; eligibility is freshly
   calculated from the current controls. The authorization checkbox now has an
   explicit workspace/batch key bound to records, scope, permission, provider
   plan, limit and usage assumptions. Changes invalidate previous paid consent.

## UI change

Immediately above **Translate flagged values with Google**, the form shows:

- Total detected foreign-language records (confident or manually confirmed).
- Eligible translation records after scope, status and name-permission checks.
- Cached translations in this batch, counted as unique texts.
- Records requiring manual language review.
- Records excluded specifically by organization-name permission.
- Uncached unique texts available in this batch.
- Already approved records, existing review drafts, excluded-field records,
  eligible unique texts before limiting, active scope/provider/limit and permission.

An empty batch displays a **Translation disabled** explanation listing all
applicable blockers, including name permission, manual/pending language review,
existing drafts/approvals, excluded fields or a scope with no confident foreign
records. Cached-only and payable eligible batches instead show distinct enabled
explanations. No eligibility or approval rule was relaxed.

## Changed files

- `rta/translation.py`: add eligibility diagnostics to the existing shared plan;
  use a set for exact text/language deduplication without changing ordering.
- `rta/translation_ui.py`: display diagnostics/reasons immediately above the
  button; explicitly key Google translation authorization to its current batch.
- `tests/test_translation_button.py`: disabled/permission, scope, pending/und,
  cached-only, approval preservation, no-consent execution and invalid-limit
  regression cases, all without real API calls.
- `docs/google-translation-button.md`: this report.

No dependencies, detection policy, account reconciliation or Final Value rules
changed. Database data, manual corrections, human translation approvals and
audit history were preserved. No live Google API calls were made.

## Manual test steps

1. Restart Streamlit with `.venv/bin/python -m streamlit run app.py`, resume the
   correct workspace and open Translation Intelligence.
2. Ensure Google detections have completed, or manually confirm ambiguous
   languages. Do not expect pending und values to be translated.
3. Set **Datasets to translate = Both** and **Translation provider = Google Cloud
   Translation v3**. Keep **Maximum unique Google texts** above zero.
4. Read the new eligibility block immediately above the button. If records are
   excluded by name permission, explicitly enable **Allow drafts for
   organization-name fields; I will verify proper names, legal suffixes and
   identifiers**. This alone sends no API requests.
5. Verify eligible counts and the cost preview update. Review language-review
   records manually rather than enabling ambiguous records automatically. For
   a cached-only batch, expect an enabled button and an explicit $0/no-requests
   explanation.
6. To authorize a translation run, check the separate Google authorization box
   for this batch and press the button. This would make paid calls for uncached
   texts; it was not done during implementation/testing. Review generated or
   cached English drafts and approve translations individually. Account
   reconciliation approval and Final Value remain separate decisions.

## Validation

New UI cases verify an initially disabled name batch remains disabled even when
the paid checkbox is checked; toggling name permission immediately enables the
eligible batch and resets stale paid consent. Changing scope to English-only
disables it again. Pending und records remain in manual review. A cached batch
is enabled at $0, reuses English drafts without constructing a Google client,
then becomes disabled while those drafts await review or after human approval.
Invalid zero/negative/oversized limits remain rejected. Production data was
inspected through read-only SQLite connections only.

Complete regression suite: **382 passed, 0 failed, 0 errors in 74.88 seconds**,
including Streamlit application execution and real HTTP startup. All six new
regression cases passed; existing assertions were retained. No live API calls
were made.
