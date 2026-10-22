# Translation execution: post-response interruption and diagnostic trace

> **Latest selection/refresh behavior:** [Multi-row translation fix](translation-multirow-refresh.md) freezes editor inputs, merges checkbox deltas by stable IDs and reruns directly after commit. Post-commit progress replay is retired. Validation: 476 tests passed; no live paid calls.

## Exact failure reproduced

The prior stable-form fix did not cover a second failure after Google execution.
The existing provider prepares the Google batch first, keeping its returned values
in memory. The engine then caches and persists each selected cell and invokes its
progress callback. The redesigned UI passed `st.progress(...).progress()` into that
callback.

**The failing boundary was the first Streamlit progress update after the first cell
was persisted.** Streamlit progress is an execution-control yield point. A pending
rerun can raise its control exception there, abandoning the remaining in-memory
responses, the remaining row writes and the final success/table refresh code.

The new integration regression triggers `st.rerun()` at exactly that progress point.
Before the fix, two successful mocked Google responses resulted in **one persisted
draft** and no completion summary. After the fix, **both drafts persist**, the table
shows both English values and the outcome appears after the rerun, with no extra
Google request.

A read-only inspection of the most recently created populated saved workspace also
found four confirmed translation submissions (77 total characters), one translation
cache entry and one current draft. That supports a post-response failure rather
than an organization-name permission block. There are multiple saved workspaces;
this snapshot does not establish which workspace is active in the browser. No live
Google calls were made to reproduce or diagnose this issue, and no saved workspace
records were changed by the inspection. Confirmed local submissions are not a claim
about Google's actual billed charges.

## Execution path and observability

| Stage | Behavior and trace |
| --- | --- |
| Main-table selection | Stable dataset/revision/row/field snapshots; Master and Source remain independent |
| Button and form | Existing stable submit identity retained; `submission_received` logs selected/eligible/excluded counts and consent |
| Eligibility and names permission | Existing supported-language/status checks retained; organization-name drafts remain enabled by default |
| Authorization | Explicit consent for the exact preview remains mandatory; no request on load/rerun, or for blocked/unconsented selections |
| Provider preparation | `provider_prepare`; ADC/setup errors emit `google_setup_failed` with a safe category |
| Google request | `google_request_attempted`, names/characters and attempt count; each attempt still reserves usage first |
| Google outcome | `google_response_received`, `google_response_validated`, or `google_request_exception` with a safe category |
| Cache and persistence | `translation_cache_reused`, `translation_record_persisted`; protected-token failures are separately identified |
| Completion | `backend_completed` and `action_completed` report draft/failure counts before any subsequent Streamlit yield |
| Main-table refresh | `table_refresh_completed` confirms that the current SQLite values were rendered into the table |

All action stages share an opaque action ID. Logs contain counts, fixed reason
categories and outcomes only: no company names, English translations, field values,
workspace tokens, credentials, request dictionaries, raw exception messages or
tracebacks. Usage/accounting and audit data remain in their existing stores.

## Fix

The UI buffers backend progress callbacks in a plain Python list while the existing
engine/provider finishes persistence. It does not call Streamlit from inside that
persistence loop. Only after the backend has returned does it render the buffered
progress. The Google request shape, project, ADC authentication, batching, retries,
cache keys, eligibility and translation approval logic are unchanged.

A bounded, process-local completion receipt is recorded before those UI progress
yields. It holds counts/outcome text and stable affected-row identifiers, not
translations. If Streamlit reruns before the local refresh executes, the next
render reads SQLite, restores this browser's affected selections, displays the
outcome and refreshes the table. It does not overwrite another reviewer's selected
snapshots. Existing atomic stale-record checks remain in place.

The same receipt tracks an in-flight batch per database/workspace, preventing a
second paid batch from starting while one is processing. Interrupted pre-dispatch
actions release that guard, show a warning and require fresh consent. A rerun after
completion cannot automatically retry paid work. The guard is per server process,
not a distributed queue. Receipts are bounded to 128 completed workspace entries
and active actions, and survive Streamlit reruns, not server process exits. SQLite
remains the durable source of translation data. This does not guarantee recovery
of an unreceived response if the server process is forcibly terminated.

The UI initially shows processing feedback while requests and writes run. Detailed
per-row progress is buffered until persistence finishes; this deliberate change
avoids reintroducing cancellation between successful responses and saved drafts.

## Temporary server logs

Diagnostics are enabled for this investigation. Read JSON lines named
`rta_translation` in the terminal or hosting logs running Streamlit. To explicitly
start with diagnostics enabled:

```sh
RTA_TRANSLATION_DIAGNOSTICS=1 .venv/bin/python -m streamlit run app.py
```

After investigation, disable them without changing code:

```sh
RTA_TRANSLATION_DIAGNOSTICS=0 .venv/bin/python -m streamlit run app.py
```

Disabling logging does not disable receipt recovery, paid consent, caching or
usage accounting. No developer diagnostic panel was added to the page. If a real
run still fails, its action ID and last emitted stage distinguish authorization,
setup, request/response, validation, persistence and refresh failures without
sharing sensitive account data.

## Integration and regression verification

`.venv/bin/python -m pytest -q` — **466 passed in 92.04 seconds**, including real
localhost Streamlit HTTP health and application execution/import startup checks.

New tests exercise the actual Streamlit action path, not just backend functions:

- Mocked Google detection of a French company, checkbox selection in the main table,
  explicit batch authorization, button click, a genuine SDK response object supplied
  by a mocked client, SQLite draft persistence and English text/status in the table.
- Queued rerun at the first progress update after Google responses, verifying all
  drafts persist, the completion outcome is recovered and requests are not repeated.
- Interruption before dispatch, guard release and required fresh authorization.
- Denied Google requests, ineligible English records and missing authorization.
- In-flight workspace guarding and safe, disableable diagnostic logging.
- Startup protection for stale provider/diagnostics modules after code updates.

Existing tests continue to cover cache reuse, workspace isolation, usage tracking,
manual corrections, approvals, Excel/audit completeness, reconciliation and Final
Value safeguards. **No live paid API calls were made.** No dependencies or database
schema changes are required.

## Files changed

- `rta/translation_ui.py`: buffer UI progress, recover completion/selection after
  reruns, prevent overlapping paid actions and emit action/refresh diagnostics.
- `rta/translation_diagnostics.py` (new): count-only JSON logs and bounded action receipts.
- `rta/translation.py`: count-only plan/cache/validation/persistence/completion events;
  existing translation execution and review logic retained.
- `rta/translation_providers.py`: safe request/response/setup/exception diagnostics
  and provider-module build fingerprint; request implementation unchanged.
- `rta/translation_runtime.py`: detect stale provider and diagnostics modules.
- `tests/test_translation_execution_trace.py` (new): eight integration/diagnostic cases.
- `tests/test_stale_google_export.py`: stale-module checks for the two newly guarded modules.
- `docs/translation-execution-diagnostics.md` (this report).
- `docs/translation-workspace-ui.md`: link this execution fix.
- `docs/translate-selected-execution-fix.md`: distinguish the earlier form-ID fix
  from this post-response interruption fix.

## User verification

Restart Streamlit to load every changed module and resume the intended workspace.
Keep the existing language detections. Select eligible foreign-language rows,
inspect the preview and explicitly authorize Translate Selected. Successful English
values must appear as **Translated — Review**. Review/approval remains separate;
original names and Final Value must remain unchanged.

The next manually authorized real run remains the verification of the live browser
and Cloud environment. The regression proves the previously untested interruption
failure and its correction; it does not substitute mocked responses for a claim
that a new live Google request was verified.
