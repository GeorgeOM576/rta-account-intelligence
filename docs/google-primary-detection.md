# RTA V3 — Google-primary detection transition

**Superseded classification policy:** see [Google-direct v4](google-direct-translation.md) for the current workflow. The transition history below is preserved; its confidence, script and name-based veto descriptions no longer govern Google classification.

October 21, 2026 (America/Toronto). **Implementation complete. No live Google API
calls. No commits, reverts, database deletion or global cache clears.**

## Phase 1 — State preserved before implementation

`git status`, `git diff`, `git diff --cached` and `git rev-parse` were attempted.
They reported that this folder is not a Git repository. There is no `.git` entry;
therefore a tracked/uncommitted inventory relative to HEAD is unavailable. No
repository was initialized and no unrelated changes were committed.

The previous stale-detection implementation was complete at handoff and had an
independently rerun baseline of **328 passing tests in 61.08 seconds**, including
real Streamlit startup. No incomplete code path or merge-conflict markers were
identified. The prior task's modified files, reconstructed from the session and
its report rather than Git, were:

- `rta/language_detection.py`.
- `rta/translation.py`.
- `rta/translation_ui.py`.
- `rta/export.py`.
- `app.py`.
- `tests/test_detection_refresh.py`.
- `docs/translation-intelligence.md`.
- `docs/stale-detection-refresh.md`.

These files and all other existing workspace changes were preserved before any
application edits in:

`checkpoints/before-google-detection-20261022T003646Z/workspace.tar.gz`

The UTC checkpoint timestamp corresponds to October 21 in Toronto. The private
checkpoint contains 67 files, a SHA-256 manifest and consistent SQLite backup.
Virtual environments, runtime bytecode/pytest caches and the checkpoint directory
itself were omitted; source, tests, fixtures, documentation, configuration, assets,
existing outputs and database contents were retained. The archive is mode 0600 in
a private directory. Do not share it: the database contains private workspace
resume-token hashes and uploaded data. Restoration was not performed.

The prior local-first design conflicted with the new default: uploads/reads ran
local inference automatically, and reanalysis assumed local rules. These call
sites now prepare Google-pending/cached records without network access. The
previous local implementation remains intact as an explicitly selected fallback.
The existing review, cache, isolation, reconciliation, usage and export architecture
was extended rather than replaced.

## Google detection behavior

- Default provider: **Google Cloud (primary)**. Existing workspaces without a
  detection-provider setting use this default.
- API: Advanced v3 `TranslationServiceClient.detect_language`, project/quota
  project `rta-translation`, parent `projects/rta-translation/locations/global`,
  MIME type `text/plain`. ADC is resolved only when an explicitly confirmed
  uncached request is about to execute. Production can use the hosting platform's
  secure ADC/workload identity or mounted service-account configuration.
- No API calls on import, upload, mapping, navigation, cache refresh or export.
  No silent local fallback when Google is unavailable.
- The Google API takes one text string per detection request. Batch processing
  deduplicates exact unique values across Master/Source and fields, interleaves
  datasets, applies a configurable batch limit and sends each uncached value once.
  Detection has a 30-second request timeout and **no automatic retries**. Failures
  require a new explicit batch confirmation or manual review.
- Default classification and identifier exclusions remain. Classification fields
  must be explicitly enabled and selected. Structural exclusions skip codes,
  all-uppercase abbreviations, dates, blanks, numeric values, URLs and emails.
- Stored/displayed Google fields are the API's code, confidence and detection
  source. The effective language can remain `und` for manual review while the
  Google suggestion and confidence remain visible separately.
- Confidence below 0.90, competing scores within 0.20, mixed/conflicting scripts,
  abbreviations, business vocabulary without context and legal suffixes route
  to manual review. Unicode-aware classification accepts reliable non-Latin
  results without whitespace word-count restrictions. Brief Latin proper names
  retain a limited-context safeguard. Legal names and suffixes are not rewritten.
  See [the saved-response comparison](google-classification-improvement.md).
- Sufficiently confident/contextual non-English results are candidates only.
  Organization-name draft permission and separate paid translation confirmation
  still apply. Machine translations enter **Translated — Review**; only approved
  English translations contribute to matching. Final Value requires its existing
  separate human account approval/manual verification.

The API method and ADC pattern follow Google's [v3 detection sample](https://docs.cloud.google.com/translate/docs/samples/translate-v3-detect-language).

## Cache, persistence and cost separation

Google raw detection results use a dedicated namespace inside the existing
workspace-scoped `language_detection_cache`. Keys include the Google provider,
raw-response format version and exact text. Field-policy interpretation keys
add provider, policy, rule builds, field kind, classification permission and
vocabulary. Local cache entries cannot satisfy a Google lookup. Old local rows
are relabelled as pending/cached Google analysis, never reported as Google API
results. Human-confirmed languages, manual corrections and approved translations
remain protected independently of automatic provider metadata.

Raw successful responses can be reinterpreted after a policy build change without
paying for the same text again. A new raw policy version has its own namespace;
any resulting paid work is visible in the preview and requires consent. Failed
or malformed responses are not treated as successful cached detections. Partial
successes are cached per request. A cache/usage persistence failure stops further
requests. Google error bodies, credentials and tokens are not logged or persisted.

The usage ledger receives an additive `operation` column. Existing rows migrate
as `translation`, preserving counts/history. New detection requests use
`operation='detection'`; translation requests retain `translation`. Each attempt
is written as uncertain before dispatch, and a returned response confirms
submission even if subsequent parsing fails. Set-up failures record zero API
attempts. Operation totals, costs and operation/month history are displayed
separately. Existing combined monthly progress, warning and allowance use both
operations without applying the allowance twice.

Explicit detection and later translation are separately counted operations.
The preview uses $20 per million input Unicode characters before credits and
shows incremental cost after the locally assumed remaining equivalent. These
are local estimates, not Google billing. The configurable 500,000-character
credit equivalent is shared across eligible usage in the billing account and may
already be consumed outside RTA. The app does not query available Google credits.
See [Google pricing](https://cloud.google.com/products/translate/pricing).

## Operator workflow after deployment

1. Restart Streamlit from this checkout, retaining the same `RTA_DB_PATH`. Resume
   the existing workspace with its private token if needed. No new workspace or
   database reset is required; the additive usage migration runs on initialization.
2. Open **Translation Intelligence**. **Language detection provider** defaults to
   **Google Cloud (primary)**. Confirm Master and Source account-name selections.
   Leave classification fields disabled unless deliberately needed.
3. Choose Both/Master/Source and the maximum unique detection texts. Inspect the
   uncached request count, characters, cache hits and detection cost preview.
4. Check **I authorize this Google language detection batch…**, then click
   **Detect languages with Google**. This approval authorizes only that detection
   batch. A cached refresh button makes no API calls and cannot manufacture a
   Google result when no response has been obtained.
5. Inspect Google language/confidence/source and effective language/outcome.
   Confirm ambiguous languages manually where appropriate. This creates an audit
   entry and does not approve a translation or a match.
6. If translation is wanted, authorize organization-name drafts, inspect its
   separate translation cost and explicitly authorize its paid batch. Review and
   approve individual translations before rerunning translation-aware matching.
7. Use the existing account review and Excel/CSV export workflows. Detected
   languages, confidence, sources and policy/build metadata are exported without
   credentials. Approved decisions and Final Values are retained.

To work without paid detection, deliberately choose **Local offline (explicit
fallback)**. Its scans and safe reanalysis remain available, clearly labelled
local, using their own cache namespace. Switching providers never authorizes
paid work and never silently overwrites a human review.

## Tests and accuracy comparison

Baseline before edits: **328 passed**, real startup included.

After implementation: **353 passed, 0 failed in 66.00 seconds**, real Streamlit
startup and application import/execution included. Twenty-five new Google
regressions cover consent, ADC/project request shape, cache/provider/workspace
isolation, no duplicate requests, classification exclusions, short/legal/mixed
script safeguards, low/invalid confidence, failures/uncertain usage, zero-attempt
setup errors, legacy usage migration, separate operation costs, shared allowance,
manual correction protection and complete mocked Google UI detection → translation
→ translation approval → reconciliation → account approval → Excel export.

No existing test assertion was removed or weakened. `make_workspace` now explicitly
selects offline detection because its existing tests target the retained local
policy. The original fictional offline end-to-end scenario explicitly selects
that fallback too. A separate new Google-primary UI test exercises the new default
with mocked detection and translation, preserving all six review filters and the
Final Value invariant. All existing reconciliation, AI, bulk review, pagination,
review and export tests remain in the complete passing suite.

The existing 68-case manually labelled set is used in two distinct ways:

| Evaluation | Foreign candidates | False foreign candidates | Precision | Recall |
| --- | ---: | ---: | ---: | ---: |
| Real retained local field-aware policy | 26 / 28 | 0 | 100% | 92.9% |
| Synthetic Google-response routing contract | 25 / 28 | 0 | 100% | 89.3% |

**The second row is NOT Google accuracy.** Google responses were fabricated directly
from the manual labels (known codes at 0.99; unknown at 0.4), not captured from Google.
It checks adapter/policy routing only. Banco Azul, Élan and Müller GmbH remain manual
under the Google field policy despite the synthetic confident foreign suggestions.
Real Google precision/recall cannot be measured while honoring the no-live-call
constraint. No claim is made that Google will correctly identify all reported
business names; a high foreign suggestion for a short/legal company name remains
manual rather than automatically translated.

Reproduce the comparison without network:

```sh
PYTHONPATH=. .venv/bin/python tests/fixtures/language_detection/evaluate_google_mock.py
.venv/bin/python -m pytest -q tests/test_google_detection.py
.venv/bin/python -m pytest -q
```

The synthetic comparison artifact is
`tests/fixtures/language_detection/google_mock_evaluation.json`. Original labels,
baseline v1 results, real local evaluation and fictional XLSX inputs are unchanged.

## Files changed in this transition

Existing application files:

- `rta/translation.py`: provider-aware pending/cached detection and protected metadata.
- `rta/translation_ui.py`: Google default, explicit fallback, detection consent/preview, Google confidence/source, operation usage/history.
- `rta/translation_usage.py`: separate detection/translation accounting with shared credit.
- `rta/storage.py`: additive, serialized usage-operation migration.
- `rta/export.py`: Google language/confidence/source CSV fields; Excel details already include record metadata.
- `app.py`: active-provider runtime information for export.

New implementation:

- `rta/google_detection.py`: ADC adapter, structural/field policy, cache namespace, plan/run orchestration and Google runtime fingerprint.

Tests and comparison artifacts:

- `tests/test_translation.py`: explicitly select offline in the existing local fixture; assertions unchanged.
- `tests/test_translation_e2e.py`: explicitly select offline in the original offline UI workflow; assertions unchanged.
- `tests/test_google_detection.py`: 25 new regressions and mocked Google UI workflow.
- `tests/fixtures/language_detection/evaluate_google_mock.py`: clearly marked synthetic comparison.
- `tests/fixtures/language_detection/google_mock_evaluation.json`: comparison output.

Documentation:

- `docs/translation-intelligence.md`: current-provider notice, preserving prior offline details.
- `docs/google-primary-detection.md`: this preservation, implementation and handoff report.

No requirements/dependency changes. The existing `google-cloud-translate>=3.28,<4`
SDK is used; `langdetect==1.0.9` remains installed only for explicit offline use.
Argos remains optional, and OpenAI/Tavily code and settings are untouched.

## Remaining limits

Live Google detection accuracy, confidence calibration, IAM/quota/billing behavior
and production hosting identity were not tested. No separate live-test permission
is requested or implied by completing this task. Future paid calls require their
own explicit confirmation. Browser layout/download interaction still warrants
manual acceptance testing. All new default/policy behavior and operation costs
were verified with mocked clients and temporary SQLite databases.
