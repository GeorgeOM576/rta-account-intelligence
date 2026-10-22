# Google-first Translation Intelligence

> **Current interface:** [Table-first Translation Intelligence workspace](translation-workspace-ui.md) replaces older controls described below. The page offers Google-only detection, selected-row translation, paged review and compact per-batch consent. Monthly accounting and audit history remain in the backend and Excel exports.

Current workflow, October 22, 2026. Classification policy: **google-direct-v4**.

## Detection and eligibility

Google Cloud Translation Advanced v3 is the default detection provider, using
ADC and project/quota project `rta-translation`. Each unique selected company
name is detected independently of reconciliation. Original uploaded text is
preserved exactly; deduplication is by exact text within the workspace.

The effective language follows a valid, supported Google result:

- `en`: **English — No Translation Needed**.
- Supported non-English code: **Non-English — Translation Candidate**, persisted
  as Translation Needed, regardless of confidence or reconciliation matches.
- Missing/unknown/unsupported code, malformed response or API failure: effective
  language remains und and status Uncertain, pending detection/manual review.
  RTA never guesses or substitutes a different language from an alternative.

The former 0.90 score is **advisory only**. Low/unavailable confidence or close
Google alternatives set Language Review Recommended and Language Review Reason.
Those flags do not block a valid non-English result from an explicitly
authorized translation batch. English remains English even at a low score, with
review advice visible so the reviewer can correct it if necessary.

The Google path no longer uses legal suffixes, word/letter counts, business
vocabulary, brand/proper-name assumptions or script-conflict rules to override
valid results. Alphabetic company names such as IBM and F1 are no longer silently
excluded by abbreviation/identifier heuristics. Blank/nonlinguistic values,
identifier fields and disabled classification fields remain excluded. No local
detector is invoked as a Google fallback. The pre-existing offline mode remains
available only when explicitly selected, with its own unchanged local rules.

Support is validated against an offline snapshot of Google's published
[general NMT language list](https://docs.cloud.google.com/translate/docs/languages#nmt),
checked October 22, 2026. It avoids a hidden capabilities/API request at page load.
Unlisted codes stay pending/manual; update the snapshot when support changes.
Supported regional/script variants are preserved, notably traditional Chinese
zh-TW. Google's documented simplified Chinese aliases zh-CN/zh share the same
effective code zh. Other unknown variants are not guessed from their prefix.

## Separate paid actions and human approval

1. Select intended Master/Source company-name fields and detection dataset scope.
   Review unique/cached/pending counts, actual batch size, characters and cost.
2. Explicitly authorize and submit **Detect languages with Google**. Checking the
   checkbox alone is not submission. Progress and submitted usage are reported.
3. Google Cloud Translation v3 is now also the default translation provider.
   Allow organization-name drafts explicitly, choose the scope and inspect the
   separate translation preview. Language-review flags can overlap eligible
   records; missing/unsupported languages remain blocked.
4. Explicitly authorize and submit **Translate flagged values with Google**.
   Successful and cached English values enter **Translated — Review**. Detection
   and translation have separate consent. Neither action runs on page load.
5. Review and correct, reject, individually approve or explicitly bulk-approve
   selected English drafts. Proper names, brands, suffixes and identifiers must
   be verified; RTA does not replace official uploaded names.

The translation engine now executes exactly the text/language identities in its
preview/prepared batch. Expanded eligibility exposed an old ordering mismatch:
preview interleaved all current rows while execution interleaved eligible rows,
so the two could select different languages/texts at a batch boundary. Execution
is restricted to the planned identities, preventing unprepared requests/failures
and keeping cache use, batching and cost consent aligned.

Only approved English values can contribute to translation-aware reconciliation.
Account reconciliation approval is separate. **Final Value is never populated by
detection or translation.** All six account review filters, AI research/OpenAI
and Tavily paths are unchanged. No reconciliation run or match is needed to
translate or export complete account datasets.

## Correcting language and regenerating drafts

In translation review, enter a supported source-language code, a reviewer and
explicit confirmation, then **Save confirmed language**. When the language
changes, the previous English draft is retained as draft_english, current English
is cleared and the cell returns to Translation Needed. The next separately
authorized batch uses the corrected language and its distinct cache key. A
cached draft can be reused, but never inherits another cell's approval.

Unknown or unsupported manual source codes are rejected before API execution.
Approved translations retain the existing protection: correct them through
explicit translation review rather than automatic reanalysis/regeneration.
Original names and previous review snapshots remain in the audit trail.

## Persistence and migration

No schema migration, deletion or blanket cache clear is required. Raw Google
cache format/version stays `google-v3-field-aware-v1`, so existing workspace
responses can be reinterpreted without paid requests. Current interpretation
keys include the new policy/build and support-list build. Local results cannot
satisfy the Google raw cache.

New persisted metadata: language_classification, language_review_required and
language_review_reason. CSV/Excel include those values alongside raw Google code,
confidence/source, effective/confirmed language, English draft and review status.
Legacy internal outcome strings remain for stored-record compatibility; their
historical word “Confident” is not a v4 eligibility guarantee. The interface and
current CSV use advisory-aware labels.

On refresh, automatic metadata updates while manual language corrections,
approved translations, rejection decisions, reviewers and audit history remain
protected. If an unreviewed machine draft's effective source language changes,
its English text is retained as draft_english and removed from the current draft
until regenerated; it is not silently reused under a different language.
Historical upload revisions and historical cache entries are retained.

Restart Streamlit to load the new modules, resume the correct workspace, select
Google Cloud (primary), then choose **Refresh from cached Google detections
(no API calls)**. Valid cached low-confidence/previously vetoed names may now
become candidates. Uncached names stay pending until a separately authorized
detection batch. Previously explicit offline selections and browser provider
choices remain user-controlled; switch them to Google to use this policy.

The support-list module participates in stale-module checks. Streamlit blocks
stale exports until restart if loaded translation, detector or support-list
code differs from disk.

## Offline evaluation and limitations

The original 149 labels and captured/mock responses are unchanged. All previous
evaluation results are retained. The current replay is
[`results_google_direct.json`](../tests/fixtures/language_detection/company_evaluation/results_google_direct.json).

| Metric, 118 definitive cases | Previous v3 | Google-direct v4 |
|---|---:|---:|
| Correct effective language/routing | 75 | 110 |
| Incorrect effective language/routing | 3 | 8 |
| Blocking definitive manual classifications | 40 | 0 |
| Foreign candidate precision | 100% | 97.83% |
| Foreign candidate recall | 65.26% | 94.74% |
| Foreign names assigned English | 2 | 5 |

These are **policy-stress metrics, not Google production accuracy estimates**.
Most responses are synthetic and include deliberately wrong suggestions. The
direct policy necessarily propagates those valid-but-wrong suggestions; review
advice is not a substitute for human approval. Ground-truth labels were not
changed to conceal the tradeoff. All 31 labelled ambiguous cases have valid mock
codes and consequently receive Google's effective language, with advisory flags
where scores/alternatives warrant them, rather than a heuristic blocking outcome.
High-confidence Google mistakes cannot all be identified without further evidence.

The saved real-response subset remains **23/23 definitive language agreement**,
100% foreign precision and recall. Low-confidence and competing suggestions stay
visible in review and exports even when eligible. The broader corpus is not
independently native-speaker-adjudicated. Further real-world accuracy claims need
separate evaluation; no new live collection was made.

Other compatibility limits: support codes are a maintained offline snapshot;
processing remains synchronous and batch-triggered; protected suffix/identifier
validation can still reject a failed English translation; shared Google credit
estimates remain local assumptions, not actual billing or guaranteed quota.

## Files changed

Production:

- `rta/google_detection.py`: direct Google classification and advisory flags;
  retire custom language vetoes, retain validation/error/consent safeguards.
- `rta/google_languages.py` (new): documented NMT support snapshot/canonical codes.
- `rta/translation.py`: metadata persistence, supported-language validation,
  correction/draft invalidation, advisory diagnostics and exact prepared-batch use.
- `rta/translation_providers.py`: block invalid/unsupported/empty/English inputs
  before client construction; preserve batching/retries/usage for valid inputs.
- `rta/translation_ui.py`: Google translation default, direct/advisory guidance,
  classification/flag columns and compatible review filters.
- `rta/translation_runtime.py`: include the support-list module in restart checks.
- `rta/export.py`: classification/review advice in current CSV; Excel continues
  to include full current translation metadata and original account datasets.

Tests and fixtures:

- `tests/test_google_direct.py` (new): 23 mocked direct-policy/validation/UI cases.
- `tests/test_google_detection.py`, `tests/test_google_classification.py`,
  `tests/test_legal_suffix_detection.py`, `tests/test_language_evaluation.py`:
  update retired policy expectations to Google authority while retaining
  provenance, raw-confidence, consent, isolation and human-review checks.
- `tests/test_company_translation.py`: low-confidence name now receives a draft;
  preserve independent batches, rejection/correction, bulk approval and export.
- `tests/test_translation.py`: explicitly select the retained offline translator
  for the original offline workflow regression.
- `tests/test_translation_button.py`: update the explanatory copy assertions.
- `tests/test_stale_google_export.py`: support-list stale-module regression.
- `tests/fixtures/language_detection/company_evaluation/evaluate.py`: replay the
  fixed labels under v4, retain historical outputs and retire obsolete threshold
  experiments rather than silently relabelling them as current safeguards.
- `tests/fixtures/language_detection/company_evaluation/results_google_direct.json`
  (new): complete current replay and preserved v3 comparison.
- `tests/fixtures/language_detection/company_evaluation/interpret_v3.py.txt` (new):
  non-executable archival snapshot of the superseded classifier for reference.

Documentation:

- `docs/google-direct-translation.md` (new): this current workflow/report.
- `docs/translation-intelligence.md`, `docs/google-primary-detection.md`,
  `docs/company-name-translation.md`, `docs/language-detection-evaluation.md`:
  prominent links marking old heuristic descriptions as historical.

No dependency changes. No existing workspace data or historical detection
records were deleted. No live Google API calls were made.

## Validation

Focused checks: **95 passed** for updated engine/provider/review/evaluation tests,
then **101 passed** including the new Google-direct cases and existing execution,
stale-export, translation and consent workflows. Final complete regression suite:
**429 passed, 0 failed, 0 errors in 81.92 seconds**, including real Streamlit HTTP
startup and application execution. Tests cover valid English/non-English codes,
low/missing confidence, competing alternatives, unsupported/missing/malformed
responses, API failures and confirmed/uncertain usage, paid consent at both
stages, language correction/regeneration, batching/dedup/cache reuse, approved
matching only, review rejection/bulk approval, workspace isolation and full Excel
export. Tests enforcing retired heuristic gates were updated for the explicitly
requested new policy; approval/reconciliation/Final Value safeguards remain tested.
