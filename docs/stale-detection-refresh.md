# RTA V3 — Stale detection diagnosis and safe reanalysis

October 21, 2026. No live Google API calls were made. The original local database
was inspected read-only; production workspaces were not bulk-modified.

## What the inspection established

The files in this project contain the field-aware detector. Read-only inspection
of `data/rta.sqlite3` found 23 workspaces at the time of inspection:

- Two older workspaces each contain 40 translation records without a detection
  policy stamp. These include the reported vi/ca/nl/de/Uncertain classifications.
  Twenty cells in each workspace belong to deselected fields and remain stored.
- A newer workspace contains 20 name cells with the field-aware policy stamp;
  the reported business names already resolve to English / Not Required there.
- One older workspace selects **Customer Segment** as its Source translation
  field instead of **Company**. A different workspace/selection therefore changes
  what appears in a table or export, even with the same uploaded files.
- Local process inspection found no running Python/Streamlit server at that
  moment. Source files on disk do not establish which code served a previous
  browser render. The previous CSV itself was not supplied for provenance checks.

The dedicated Export Results action previously generated XLSX, not CSV. A CSV
could have come from a Streamlit dataframe's download menu or an older render.
The updated interface supplies an explicit **Download current translation CSV**
action with a build-stamped filename and analysis provenance columns.

It is not possible to attribute the earlier identical CSV conclusively to a
specific process, workspace or download using these observations alone. In
particular, missing-policy rows in the active selection should already migrate
when read by the previous updated engine. Their continued old state is consistent
with that workspace not having passed through the updated read path.

## Confirmed defects and fixes

| Check | Finding and fix |
| --- | --- |
| Running code | A previous UI/export lacked runtime provenance. Detection now shows the policy/build, loaded-vs-disk rule hashes, module path, Python executable, process ID, database path and workspace identifier. A mismatch blocks reanalysis/translation UI and Excel export until restart. |
| Persisted rows | `detect()` skipped existing rows whenever their policy stamp matched, even on an explicit rerun. Explicit detection now forces reanalysis; a separate workspace action recomputes all stored current-revision fields while keeping field selections. |
| Cache invalidation | Cache keys included the manually maintained policy version and settings, but no source-build fingerprint. They now include the loaded rule-source SHA-256. Rule edits invalidate detection even if VERSION is unchanged. |
| Cached bad results | A matching policy/cache entry could keep returning a bad result. Force mode bypasses persistent and in-memory detection caches and overwrites only the relevant current-workspace cache entries. No wholesale cache clear is performed. |
| Protected reviews | Preserving a review also froze automatic detected-language metadata. Automatic language/outcome/build/time now refresh independently, while approved English, confirmed language, corrections, reviewer data, audit events and account decisions remain intact. |
| Excluded fields/export | Excluded records could still be passed to workbook generation, and old deselected field records were left untouched. Active CSV/XLSX translation exports now omit excluded fields. Reanalysis updates stored current-revision deselected classification records too. Prior dataset revisions remain historical. |
| Export source | The app's Excel action and the new CSV download use `export_records()`: current workspace, current dataset revision, selected enabled fields. CSV bytes and its widget/filename change with the current record digest. Audit history is kept separately. |

Original uploaded segment columns remain in Master/Source export sheets. They do
not receive active English translation columns while excluded. Historical audit
snapshots may still legitimately contain earlier language values; they are not
current detection results. Raw `detector_language` hints in detailed diagnostic
metadata may disagree with the final rule-based `detected_language`; the explicit
current CSV exports the final automatic language, not those raw hints.

## Exact steps to refresh the current workspace

1. If the current browser session is still open, download its private resume token
   from **Save / resume workspace** in the sidebar. Keep it private. Do not create
   a new workspace to try to repair the current one.
2. Stop the old Streamlit command with Ctrl+C if it is running. From this exact
   project directory, start the updated app against the same database:

   ```sh
   cd /path/to/rta-account-intelligence
   RTA_DB_PATH="$PWD/data/rta.sqlite3" .venv/bin/python -m streamlit run app.py
   ```

   The inspected database is `data/rta.sqlite3`. If your actual server uses a
   different `RTA_DB_PATH`, retain that same path instead of switching databases.
   A browser refresh alone does not guarantee imported Python modules reload.
3. Reopen the app. If necessary, upload the saved token in the sidebar and click
   **Resume saved workspace**. Confirm the dataset filenames and workspace in
   **Translation Intelligence → Detection runtime and refresh details**.
4. Confirm the page shows **Detection refresh v1** and policy
   `field-aware-business-v2`. Loaded and on-disk rule hashes must match, and the
   module/database paths must point to this checkout and the intended database.
5. For the inspected CSV schema, choose **Account** in **Master text fields** and
   **Company** in **Source text fields**. Do not select Customer Segment in place
   of Company. Under **Language detection settings**, leave Segment and Customer
   Segment as `classification`, with their enable lists empty. If changing those
   settings, click **Save language detection settings**.
6. Click **Reanalyse current workspace languages**. This is local detection only:
   no Google request or paid consent is involved. The action processes current
   selected fields plus stored current-revision deselected fields, then preserves
   your selection. Check the new timestamp under refresh details.
7. Use **Translation status → All** to inspect the now-unflagged English names.
   Expect HARBOR HEALTH, Cedar Labs, Summit Holdings, Pioneer Data, Orchard Systems
   and Bluebird Studio to show automatic language `en`, status Not Required, unless
   a saved human review intentionally retains a different effective status.
   Classification values are excluded from active candidates and current
   translation downloads. A preserved human language is displayed separately.
8. Click **Download current translation CSV** to obtain newly generated current
   results with Detection Policy, Detection Build and Analyzed At columns. Do not
   reopen a previously downloaded CSV or rely on an older dataframe render.
   **Export Results → Download Excel report** also reads current enabled records;
   it requires a reconciliation run to exist. Reanalysis itself does not rerun
   reconciliation or change saved account decisions/Final Values.

If a human previously approved an incorrect language or translation, reanalysis
refreshes the automatic detection but preserves that human choice. Correct it
through the existing reviewed translation workflow; it is not silently removed.

## Validation using the real database safely

A disposable, private SQLite backup was made through SQLite's backup API after
opening the original database read-only. Reanalysis was exercised against each
workspace containing the reported names:

| Inspected workspace ordinal | Current cells reanalysed | Target name cells corrected | Classification cells excluded | Enabled selected export cells |
| --- | ---: | ---: | ---: | ---: |
| 20 | 40 | 10 | 20 | 20 |
| 22 | 40 | 10 | 20 | 10 |
| 23 | 20 | 10 | 0 (not stored) | 20 |

Ordinals describe this inspection, not stable workspace IDs. In workspace 22,
the smaller export is due to Customer Segment being selected instead of Company;
reanalysis deliberately does not silently change a user's field selections.
All six target names were present and correct in each checked workspace. Checks
confirmed audit events, provider translation cache, usage, account results and
field selections were unchanged. The disposable backup was removed afterwards.
The original database was not rewritten.

## Regression coverage and result

`tests/test_detection_refresh.py` reproduces stale rows and poisoned cache entries
under a matching policy stamp, stale missing-policy legacy rows, in-memory stale
results, rule edits without version bumps, deselected field records, and old
revisions. It checks preservation of approved translations, incomplete legacy
approvals, unapproved manual corrections, language confirmations, audit history,
usage, provider cache, decisions, selections and other workspaces. It verifies
actual UI reanalysis, the current CSV, the real Export Results workbook path,
exclusion filtering, loaded/disk mismatch handling and CSV literal-value safety.
Google client construction is forbidden during the refresh UI scenario.

Full-suite verification: **328 passed, 0 failed in 60.98 seconds**, including the
real Streamlit startup/HTTP health check and application import/execution checks.
The initial sandbox run passed 325 tests; its only failure was the sandbox
disallowing the localhost socket. The final complete rerun with localhost
permission also included two additional protection/export regressions. All
14 new stale-detection regressions passed. No live Google API calls were made.

## Changed files

- `rta/language_detection.py`: build fingerprint, runtime details and targeted uncached detection.
- `rta/translation.py`: safe force/reanalysis path, refreshed automatic metadata, protected review state and current export selection.
- `rta/translation_ui.py`: runtime diagnostics, force/reanalysis actions, current CSV, provenance and exclusion filtering.
- `rta/export.py`: explicit current CSV and excluded-field filtering at the Excel boundary.
- `app.py`: runtime check and current-record selection for Excel export.
- `tests/test_detection_refresh.py`: stale-state, preservation and UI/export regressions.
- `docs/translation-intelligence.md`: refresh workflow and cache-build details.
- `docs/stale-detection-refresh.md`: this diagnosis and operator steps.

No dependency changes, database deletion, global cache clearing, live translation
requests or changes to the six account-review filters were made.
