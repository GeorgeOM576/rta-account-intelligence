# Google detection execution and UI workflow

## Root cause and evidence

Read-only inspection located a workspace with exactly **107,243 selected cells**:
25 Master Company name values and 53,609 Source rows with two account-name fields
(MSSales Account Name and CRM Account Name). Its Master genuinely contains the
same 25 fictional names as the earlier diagnostic. The application does not read
the diagnostic fixture or its output files to create a preview.

Using the current workspace records through a read-only adapter, the planner
produces:

| Detection scope | Total unique selected values | Eligible unique texts | Cached | Pending | Batch | Characters |
|---|---:|---:|---:|---:|---:|---:|
| Master only | 25 | 25 | 0 | 25 | 25 | 427 |
| Both | 53,269 | 52,052 | 0 | 52,052 | 250 | 5,169 |

The Both preview leaves 51,802 eligible values after the first batch. Counts are
from the inspected database snapshot and can change as the workspace changes.
Nonlinguistic, identifier, excluded-field and human-reviewed values do not enter
paid detection. Deduplication is exact text across both datasets/selected fields.

The 25/427 preview is therefore the exact result for **Master only**, not the
result for Both and not stale diagnostic injection. The active browser's radio
state cannot be read from SQLite; the evidence establishes the scope-dependent
reproduction, not proof of what that browser last selected. The prior interface
showed a combined current-cell count beside a scope-limited preview without
prominent scope/total/batch labels, which obscured this distinction.

The matching workspace has no Google usage records and no matching raw Google
cache. Its eligible current records remain pending. Selecting a consent checkbox
in a Streamlit form does not execute the request: the submit button must also be
pressed. There is no evidence of a dispatched request in that workspace. A
pre-dispatch setup failure would likewise have no submitted usage; the UI now
keeps explicit submission/error/result guidance visible. No live call was made
to investigate credentials or permissions.

A separate **verified batching defect** applied the limit to all eligible texts
before removing cached entries. After the first 250 were cached, subsequent runs
would revisit that prefix instead of advancing. The limit now applies to pending
uncached texts. Ordered dictionary deduplication and one workspace cache scan
replace list-membership scans and per-text SQLite lookups in the planner.

## Workflow changes

1. Current SQLite field selection feeds `engine.records()` for current upload
   revisions. Dataset scope filters Master/Source independently. No fixture path
   participates in production selection.
2. Preview separates all unique selected values, request-eligible unique texts,
   cached texts, pending texts, oversized texts, actual batch size and remaining
   work. The active dataset scope and selected field names are shown prominently.
   Costs/characters refer to the actual uncached batch, not all selected cells.
3. The primary **Detect languages with Google** button is directly below the
   cost preview and consent checkbox. Consent is explicitly keyed to workspace,
   current records, plan/scope/limit and usage assumptions. Checking consent
   alone sends nothing; changing the batch invalidates old consent.
4. Execution uses the same planner and requires consent at the UI and service
   boundaries. Progress reports processed values, successful detections and
   failures. The provider still disables retries.
5. Each successful response is committed immediately to the correct workspace's
   raw Google cache before dispatching the next value. Failures remain separate
   and can be retried only through another explicit batch action. Usage is
   reserved before dispatch and confirmed on response, including malformed
   responses. Batch usage counters track only this execution, avoiding monthly
   rollover or concurrent-request distortion from summary differences.
6. Current classifications are refreshed after execution using the saved/raw
   outcomes. Human corrections, approved translations and audit history remain
   protected. Streamlit reruns and reloads SQLite, producing current interface
   values/CSV and a summary of successes, failures, actual request attempts and
   confirmed/uncertain submitted characters. These are local usage observations,
   not Google billing. Cached-only execution sends zero requests.
7. Only confidently foreign or manually confirmed non-English records qualify
   as translation candidates. Undetected values and ambiguous Google suggestions
   remain language-review records. Detection does not create an English draft.
8. The interface now labels the review section **Language review and translation
   drafts**, labels empty drafts **No translation draft**, and displays candidate
   counts separately from generated drafts. A zero translation-run count can
   also reflect the preserved account-name draft opt-in, which remains off by
   default. Translation has separate paid consent and produces drafts for human
   approval; reconciliation and Final Value require their existing decisions.

Historical local records remain in their existing revisions. Current scope,
history counts, detection provider/source, raw Google code and confidence,
confirmed language and translation provider remain separately visible. The
existing stale-module restart guard remains active.

## Changed files

- `rta/google_detection.py`: scope totals, efficient unique/cache extraction,
  pending-first batch limiting, progress callback, per-execution usage counters.
- `rta/translation_ui.py`: prominent scope/count preview, primary submit action,
  explicit consent key, progress/results, pending/candidate/draft guidance.
- `tests/test_google_detection_execution.py`: full-size cell-count preview,
  real Streamlit mocked multi-batch workflow, immediate persistence and usage
  failure reporting.
- `docs/google-detection-execution.md`: this report.

No dependencies, classification thresholds, reconciliation rules, Final Value
rules or production workspace records were changed. No Google API calls were
made. Existing test assertions were retained.

## Testing the corrected interface

1. Restart Streamlit from this project using
   `.venv/bin/python -m streamlit run app.py`, and resume the affected workspace.
2. Open Translation Intelligence. Keep Google Cloud (primary) selected. Confirm
   Master Company name and the intended Source account-name fields are selected;
   leave identifiers and segments excluded.
3. Set **Datasets to detect = Both** and the maximum to 250. Check **Scope: Both**
   and the fields printed below it. For the inspected uncached snapshot, expect
   52,052 eligible texts, 250 requests and 5,169 characters. Master only correctly
   produces 25 requests and 427 characters. Current cache changes these figures.
4. Review cost and data scope. Check consent **and then press Detect languages
   with Google** only if you choose to authorize that live batch. This manual
   action makes paid calls; none were performed during implementation/testing.
5. Watch progress, then the success/failure/usage summary. Current Google codes
   and classifications should populate immediately. The next preview should
   show cached successes and the next pending batch. Each batch needs new
   confirmation. A cached-only repeat dispatches no requests.
6. Inspect **Language review and translation drafts**; use Translation status
   All to see confident English values that disappear from Flagged records.
   HARBOR HEALTH should show its actual Google result after detection, rather
   than being assigned a language before any request. Low-confidence results
   still correctly require manual language review.
7. To translate eligible account names, explicitly allow organization-name
   drafts, choose the translation provider, inspect its separate preview and
   consent, then run translation. Generated English drafts require translation
   approval; this does not approve account reconciliation or set Final Value.

## Validation

Focused suite: **34 passed** (new execution tests plus existing Google detection
and stale-export tests). Coverage includes a 107,243-cell preview with 25 Master
names, a real UI scope switch, consent rejection, 250 then 75 mocked requests,
no duplicate requests across repeats, success committed before the next request,
Google source/provider metadata, candidate generation without drafts, and
confirmed versus uncertain usage on a mocked timeout.

Complete regression suite: **376 passed, 0 failed, 0 errors in 71.84 seconds**,
including Streamlit application execution and real HTTP startup. Existing tests
and assertions were preserved. No live Google requests were made.
