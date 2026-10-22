# Stale Translation Intelligence export investigation

## Findings

The local SQLite database was inspected read-only. Existing workspace data was
not refreshed, migrated through the engine, or edited during this investigation.
The running Streamlit process was confirmed to use this project directory and
`streamlit run app.py`. Its in-memory Python module versions cannot be established
from its process command; a correct directory does not establish fresh imports.

Three older workspaces retain legacy detection rows without Google provider
metadata and have **zero workspace-scoped raw Google cache entries**. One older
workspace still selects Customer Segment as its Source detection field instead
of the account name. A separate, newer workspace has 25 raw Google cache entries.
Cache entries in that newer workspace cannot be used by the older workspace.
No workspace identities or uploaded account data are included in this report.
The browser's active workspace identity and the actual reported CSV were not
provided, so the affected browser session cannot be uniquely identified here.

The authorized live 25-name experiment explicitly saved only standalone output
artifacts. It did **not** populate any workspace's raw cache, usage ledger or
translation records. Copying that fixture into a production workspace would
misrepresent the provenance and usage of its detection; this fix does not do so.

The reported CSV layout (one Provider column, missing detection source) is an
older layout or table download, not the explicit current CSV layout. Blank
translation Provider fields alone do not mean detection failed: language
detection and translation are separate operations. Existing downloaded files
never change when workspace records change.

## Data flow and defects

1. `GoogleDetectionProvider.detect` requires explicit batch consent. Each raw
   response is persisted under workspace + Google provider/raw-response version
   + exact text. Usage is recorded separately. No consent or cache refresh sends
   an automatic request.
2. `run_detection` writes successful raw responses, then `TranslationEngine.detect`
   interprets them per field under the current classification version/build and
   persists current-revision per-cell records. The engine protects manual
   language decisions and approved translations.
3. `records()` reads current revisions and selected fields from SQLite and
   reinterprets old-policy rows. `reanalyse()` explicitly bypasses interpreted
   caches, reuses only raw Google responses, and refreshes current revisions
   including retained unselected fields. It cannot create an uncached Google
   result: those cells become pending/manual review, not the old vi/ca/nl/de
   classifications. Older upload revisions remain untouched.
4. `app.py` already reloads the workspace payload from SQLite on every rerun.
   However, **the provider and field widgets had keys that did not reflect the
   persisted settings**. Old widget values could override an external settings
   update and write the old selection/provider back to SQLite. Their keys now
   include persisted provider/selection, so external updates replace stale
   widget state while normal user edits still save.
5. Streamlit can rerun `app.py` with previously imported Python modules still
   cached. The prior fingerprint check covered detector code only; older
   translation/CSV/UI implementations could remain loaded. A new application
   guard checks loaded fingerprints for all four translation modules and blocks
   exports until a full restart if a fingerprint differs or is absent. Browser
   refresh alone is insufficient in that situation.
6. The explicit current CSV calls `engine.export_records()` each render, excludes
   disabled classification fields, and uses a download key/name based on the
   current content. It does not read audit snapshots or historical revisions.
   Its new explicit Record Scope, Detection Provider and Translation Provider
   columns distinguish provenance. Preserved human language is exported
   separately from automatic detected language and raw Google language.

## User-visible fixes

- Current selected cell count, excluded count, historical-upload count and
  current-unselected count appear separately. Historical, unselected and excluded
  cells are retained and omitted from the current CSV.
- Older selections containing excluded fields are identified with an instruction
  to select account-name fields instead. Classification fields remain excluded
  unless explicitly enabled; no saved choice is silently deleted.
- When a pending batch has no reusable cache, a warning explains that the
  standalone diagnostic did not populate the workspace. The existing character,
  request and cost preview and consent-controlled Google detection remain
  available.
- Cache refresh reports how many current cells have Google results and how many
  do not. It instructs the user to download a new CSV.
- Interface and CSV distinguish detection from translation providers. A blank
  Translation Provider is expected if no translation has been generated or
  manually supplied; it does not conceal the Google Detection Provider.

## Exact workspace refresh steps

1. Stop the existing Streamlit process using Ctrl+C in its terminal. From this
   project directory run `.venv/bin/python -m streamlit run app.py`. A module
   mismatch banner must be resolved by a full process restart.
2. Resume the **affected saved workspace** with its existing workspace token.
   Compare its workspace identifier/database path under **Detection runtime and
   refresh details** with the workspace you intend to refresh. Do not create a
   new workspace or expect another workspace's cached results to appear.
3. Open **Translation Intelligence** and select **Google Cloud (primary)**.
4. Under **Master text fields** and **Source text fields**, select the actual
   account-name columns (for the older sample mapping, Account and Company).
   Deselect Customer Segment. Keep classification fields disabled in **Language
   detection settings** unless explicitly wanted. This preserves the original
   uploaded segment values and retained review history.
5. Click **Refresh from cached Google detections (no API calls)**. If the workspace
   has matching Google raw results, current classifications are recomputed with
   current rules. Approved translations and manual corrections remain human
   decisions even if Google's automatic suggestion differs.
6. If the warning says no reusable Google cache exists, refresh alone cannot
   produce Google classifications. Review **Datasets to detect**, batch limit,
   unique texts, character/request counts and estimated cost. To obtain results,
   explicitly check the Google language detection authorization and click
   **Detect languages with Google**. This is a user-controlled paid operation;
   it was not performed during this fix. Manual language correction is also
   available without Google calls.
7. Set **Translation status** to **All** to inspect English/non-actionable rows
   in the review table; the default Flagged records view intentionally omits
   confident English. Download **Download current translation CSV** anew. Check Google Detected
   Language, Google Confidence, Detection Source, Detection Provider, Detection
   Policy/Build, Analyzed At and Confirmed Language. Customer Segment must not
   appear when excluded. Use this explicit download, not an older downloaded
   file or a historical table snapshot. Ambiguous raw-English names can still
   have effective language und and manual-review status under the confidence
   policy; that is different from an old foreign-language classification.

## Changed files and preservation

- `app.py`: block stale imported translation modules before rendering/export.
- `rta/translation_runtime.py`: new loaded-versus-disk fingerprint checker.
- `rta/translation.py`: module fingerprint and current/history inventory.
- `rta/translation_ui.py`: configuration-aware widget state, cache-miss warnings,
  scope counts, refresh feedback and separate provider columns.
- `rta/export.py`: module fingerprint and explicit CSV scope/provider columns.
- `tests/test_stale_google_export.py`: real UI stale-13-record workflow, cache
  refresh/export persistence, settings synchronization and old-module blocking.
- `docs/stale-google-export.md`: this report.

No dependencies changed. No database deletion, global cache clearing, fixture
injection into production, live Google requests, or automatic translation was
performed. Audit history, manual corrections, approved translations, historical
uploads, reconciliation decisions and Final Value safeguards are preserved.

## Validation

Focused regression tests passed: **34 passed**. The new end-to-end test starts
with the exact six bad language codes and seven selected segment records, checks
the no-cache/pending export and blocked no-consent action, repairs the field
selection, seeds captured Google responses only into the disposable test SQLite
database, and validates interface refresh and actual CSV-generation bytes across
navigation. It verifies history, human reviews, zero API usage, and workspace
results remain intact. Additional tests reproduce stale widget settings and
block each of the four stale module types.

Final complete regression suite: **373 passed, 0 failed, 0 errors in 66.57
seconds**, including real Streamlit HTTP startup and application execution.
The first full run caught a widget-timing regression introduced by the new keys:
the initial default-field save changed the key before the user's next edit.
The UI now rerenders immediately after saving field selection. The existing
classification-settings test and six new regressions then passed (7/7), followed
by the clean complete run above. Existing tests and assertions were retained.
No live Google calls were made.
