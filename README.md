# RTA Account Intelligence MVP V3

A standalone Python/Streamlit application for reconciling one Master file, one Source file, and one comparison field. Runs fully offline; Tavily and OpenAI research are optional and explicitly started by the user.

**Translation Intelligence** analyzes independently selected fields in both uploads,
shares project-isolated translation drafts, supports reviewer corrections and approvals,
and feeds approved English variants into the existing reconciliation and account-review
workflow. See [setup and integrated workflow](docs/translation-intelligence.md), including
the optional separate Argos runtime required by this Python 3.15 environment. Detection
and manual translation review work without translation models; paid fallback is off by default.

## Red Thread branding

The interface uses Red Thread red (`#D71920`), dark navy (`#081426`), white, and a light gray (`#F5F6F8`) workspace. Streamlit's theme config controls navigation, buttons, progress, chart colors, widget borders and table headers. Presentation-only helpers in `rta/ui.py` render the header and accessible text/icon status badges; scoped CSS uses explicit container keys rather than generated selectors. All workspace pages share the theme. Review cards keep Original, Proposed and Final values visible with written review status and qualitative confidence.

The original logo was not found during this update. Copy the supplied **redthreadadvising_logo.jpg** to **assets/redthreadadvising_logo.jpg**, then refresh the app. Both the sidebar and main header use that relative path automatically. Until the file exists, ordinary Red Thread text is shown; no substitute logo is generated. Restart Streamlit after changing `.streamlit/config.toml` if the theme has not refreshed. Branding changes do not modify matching, research, review decisions, persistence or Excel generation.

## Run locally (PowerShell)

Python 3.11 or newer is required. This workspace already has an installed `.venv`.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m streamlit run app.py
```

Open the local URL printed by Streamlit (normally http://localhost:8501). To run tests:

```powershell
.\.venv\Scripts\python -m pytest -q
```

On macOS/Linux, use `.venv/bin/python` in place of `.\.venv\Scripts\python`.

On macOS, launch from this project directory with the project's interpreter:

```sh
.venv/bin/python -m streamlit run app.py
```

After updating Python modules, stop the existing Streamlit process with Ctrl+C and
run that command again. A browser refresh can reuse modules loaded by the old server.
If an import error persists, verify the module path and suggestion-review helpers:

```sh
.venv/bin/python -c 'import rta.review as r; from rta.review import source_suggestion, suggestion_version, validate_suggestion_approval; print(r.__file__)'
```

The printed path should end in this project's `rta/review.py`. Run
`.venv/bin/python -m pytest tests/test_startup.py -q` to check both a fresh application
session (including its imports) and the real Streamlit server. These tests use
temporary databases and leave saved workspace data untouched.

## First reconciliation

1. Open **Upload Data** and load the synthetic example, or import two CSV/XLSX files.
2. On **Configure Reconciliation**, map each identifier and comparison field. Column names can differ between datasets.
3. Optionally configure verified aliases or known relationships in **Settings** before running.
4. Open **Run Reconciliation** and run automatic local matching.
5. Inspect **Dashboard** and **Review & Approvals**. Choose **Approve**, **Reject**, **Manual**, **Retain original**, or **Pending**. Manual reveals distinct valid Source values (suggested account values first) and a custom input; a nonblank custom entry takes precedence. Enter a reviewer name and verify the account-specific field value before approval. Manual decisions display **Manually Verified** and record whether the value came from the Source dropdown or custom entry.
6. Optionally run **AI Research** after reviewing its estimated requests and explicitly authorizing provider charges and external data transfer.
7. Download the four-sheet workbook from **Export Results**.
8. Download your private resume token from the sidebar. After a restart or new browser session, upload it and click **Resume saved workspace** on the same server/database.
9. Use **Create new workspace** for different datasets or mappings. A saved run's inputs are immutable; rerunning matching preserves findings and reviewer decisions.

Review Status has exactly six filters: **All**, **Intelligence Proposed — Pending Approval**,
**Manual Review Required**, **Approved**, **Rejected**, and **Manually Verified**.
All new proposals require human approval, including exact matches whose proposed
value equals the original. Matching classifications remain separate from human
review outcomes. Pending proposals have no approved Final Value. Historical
automatic finals are retained in SQLite and flagged for review; see
[legacy review handling](docs/legacy-review-approval.md).

## Optional API configuration

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and enter your API keys, or set `TAVILY_API_KEY` and `OPENAI_API_KEY` environment variables. Never commit keys. The UI displays key availability without showing credentials.

The model is configurable in Settings (default `gpt-4.1-mini`; availability depends on your API account and it must support strict structured outputs). Research uses [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search) and [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat), with a strict [structured response schema](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat) and independent application-side validation. No API keys or paid calls are needed for automated tests; test provider responses are mocked and the offline UI test replaces credential lookup with empty test secrets.

### Evidence-backed AI recommendations

Research now produces either a validated Source-field proposal ready for human approval or **Insufficient Evidence — Manual Review Required**. The latter is a status, never a field value. Technical/API failures are separately marked **Failed**. A valid proposal is **Completed** with recommendation status **Proposed**; cached proposals keep this status and carry a separate cache-hit flag.

The analysis receives the Master name and original value, configured comparison-field name, distinct valid Source values, all three local suggestions with similarity scores, and retrieved evidence. It extracts cited company identities, renames, verified aliases, parents, acquisition/merger relationships, and subsidiaries independently of those suggestions. The application then builds an index of **every row in the uploaded Source** and looks up each grounded entity and its separately verified names. There is no 25-record cutoff or restriction to the top three fuzzy candidates. The model does not choose or invent the segment: application code copies the matched Source row's exact valid value. Direct identity takes precedence over renames/aliases and supported corporate inheritance. Equally supported conflicting segments require manual investigation.

In **Settings → Corporate relationship mapping policy**, choose **Evidence-backed inheritance** (the default) or **Same entity only**. The first requires a cited account-specific excerpt naming both companies and explicitly supporting their shared Source field value; ownership alone never suffices. The second blocks segments inherited from separate legal entities even when supporting evidence exists. Policy changes are applied by explicitly re-evaluating saved evidence and never change saved reviewer decisions. These two policies are the MVP's organization-rule controls, not a general rules language.

Evidence URLs must come from retrieved results, and supporting excerpts must occur verbatim in the stored cited content. Each fact must name the Master and related entity and contain relationship language; negated, tentative, or mere name-similarity statements are rejected. Alternate names require their own cited alias/rename excerpt. Parent/subsidiary, acquisition and merger inheritance additionally require explicit field-inheritance support naming both entities and the actual Source value. The app never falls back to an unrelated similar name when the related entity is missing or inheritance is unsupported. High/Medium/Low confidence is the model's qualitative evidence assessment, not a calibrated probability; invalid or insufficient recommendations are conservatively shown as Low. These checks validate provenance and Source consistency; they cannot independently establish the truth or meaning of company statements, so human review remains mandatory.

**AI Research** shows the recommended account, parent company, AI Proposed Value, confidence, recommendation status, explanation, reasoning, and evidence links. **Intelligence Proposed Value** is the effective `proposed` field populated by local matching or AI research. Accounts without a completed saved review decision display **Intelligence Proposed — Pending Approval** when that field is nonblank, or **Manual Review Required** when it is null, empty, or whitespace. Saved approval, rejection, and manual outcomes take precedence. These display statuses do not establish approval eligibility; existing evidence checks still apply. Historical **Approved — AI Recommendation** and **Rejected — AI Recommendation** labels remain stored, while the shared display status is **Approved** or **Rejected**. Rejection preserves an existing explicitly verified original where applicable. Manual verification can select a Source value or use custom text and preserves the original AI proposal and explanation. The workbook contains the persisted fields, cited evidence URLs, stored historical status, and the canonical reviewer outcome.

Both workspaces show **Verified Facts**, **Suggested Matches**, human-readable Original, Intelligence Proposed, and Final values, and **Recommendation Decision**. The raw Proposed Segment dictionary is omitted from the normal interface. Local fuzzy candidates remain visible separately from the complete-Source evidence-backed matches, including matches that cannot justify a segment. Excel retains structured research metadata and the applied policy; reviewer audit events also retain the facts, matches, and policy.

**Re-evaluate saved evidence (no API calls)** locally revalidates saved entity facts and looks them up across the entire Source under the current policy. It does not perform a new model interpretation or network request. New research saves the raw structured facts, retrieved excerpts, candidates, queries, and timestamps in SQLite. Replaced findings are retained in per-record research history. Previous cache versions remain readable. Named parents/acquirers overlooked by older candidate-limited findings can be recovered from saved relationship excerpts and explicit inheritance evidence, without paid calls. Legacy results that saved only URLs and explanations may lack enough information to qualify; local re-evaluation marks them insufficient and preserves their historical explanation/evidence. **Run fresh paid research** explicitly bypasses the cache only after the user authorizes that selected account's new search and AI request. Reviewed records are protected from both operations. Navigation never starts paid research.

Research uses one basic search and one AI interpretation per uncached account. Batch size, retries, timeout, request interval, cache expiration, and maximum output tokens are configurable. Estimates count requests rather than currency because pricing depends on provider plans and model. Retries can incur additional provider charges. Processing is synchronous; completed findings are checkpointed per account. Interrupted in-flight calls may need to be repeated. Resume by reopening the workspace and explicitly starting the next batch.

## Correctness rules

- Exact identifiers take precedence, followed by normalized identifiers, verified aliases, fuzzy suggestions, and configured relationships. Corporate relationships never establish shared segment values.
- Identifier normalization applies Unicode NFKC, case folding, and punctuation/space removal. CSV columns are read as strings. XLSX text identifiers and simple all-zero numeric display formats preserve leading zeros; zeros already lost in a source file cannot be recovered.
- Name identifiers are not globally unique. Duplicate Master names and duplicate Source identifiers require review even when values agree. Normalized collisions with conflicting values also require review, including when an exact spelling exists.
- Fuzzy scoring uses token/prefix/trigram indexes, skips overly common blocking keys, and scores at most approximately 1,200 name candidates plus reliable local hits per Master record. A small fallback pool supplies suggestions when no useful block exists. Suggestions are approximate and may miss the true account. Similarity scores are never identity confidence or automatic approvals.
- Up to three Source row suggestions are shown. Only independently verified aliases can establish a reliable alias match. Configure these carefully.
- A valid unchanged original may become Final Value only after a reliable unambiguous local match. Proposed changes and AI findings stay pending until explicit review. Placeholder values (case/space insensitive) never become final values, and original values are preserved.
- AI extracts evidence-backed names without a Source shortlist restriction. Application code looks those names up across the complete Source index and copies actual Source values. It never maps company names by similarity alone during corporate relationship discovery. Unverified corporate suffix/name variations require explicit alias evidence or manual investigation.
- Evidence and AI findings are advisory. Ownership does not prove field values. Reviewers must verify identity and the comparison field for the specific account.
- Review decisions and audit records are saved atomically. Existing decisions are excluded from research and preserved by reruns.
- SQLite is authoritative for review, navigation, and export. Review saves target the stable workspace/row ID, reload the committed payload, retain the selected record by switching the filter to All, and immediately update the badge, statistics, and results table. Stale research checkpoints cannot overwrite persisted decisions. Audit events retain previous and new final values, status, reviewer notes, value origin, and timestamps for every change.
- Reject and Pending never apply a proposed correction; they retain only an independently verified valid original, when one has been established. Manual corrections export as **Manually Verified** with decision **Manual** and status-based Excel formatting. Existing saved manual decisions are interpreted compatibly without changing historical audit entries.
- Excel exports defensively enforce final-value rules and write formula-like uploaded text as literal strings.

## Project structure

```text
app.py                       Eight-page Streamlit interface
rta/models.py                Mapping, result schema, normalization, placeholders
rta/ingest.py                CSV/XLSX parsing and identifier statistics
rta/matching.py              Indexed local matching and candidate suggestions
rta/research.py              Tavily/OpenAI integration, retries and evidence validation
rta/recommendations.py       Strict response schema and Source/evidence recommendation validation
rta/relationships.py         Grounded entity facts, organization policies and full-Source lookup
rta/storage.py               SQLite projects, token hashes, expiring cache, audit trail
rta/review.py                Explicit human decisions and timestamps
rta/export.py                Summaries and formatted four-sheet Excel reports
samples/                     Synthetic Master and Source CSVs
tests/                       Core, API mock, Streamlit workflow and scale tests
.streamlit/                  Theme, server configuration and example secrets
```

## Persistence and privacy

SQLite defaults to `data/rta.sqlite3`; override the path with `RTA_DB_PATH`. Uploads, findings, source data and checkpoints are stored inside this database, not committed to Git. Protect the database directory and backups using OS access controls and disk encryption. Resume tokens are bearer credentials; store them securely. A token is useful only while the corresponding server database still exists.

Each browser session receives a random workspace and resume token. No uploaded data or findings use shared Streamlit caches. Cache entries are scoped to a workspace and fingerprint the entire Source dataset, mapped columns, normalized company, original comparison value, model and cache version; candidate context is stored with the findings. Legacy cache entries are readable for conservative local re-evaluation. Prior segment approvals are not reused across unrelated datasets. Only token hashes are stored in SQLite. There is no workspace directory/list UI exposing other users' projects.

This MVP is designed for local use or a controlled trusted team. It does not implement organizational authentication, authorization roles, encryption at rest, administrator controls, concurrent editing conflict resolution, or data retention policies. Server administrators can read the local database. Do not deploy confidential client data to a public app. Research sends selected identifiers, candidate account names/values, and retrieved evidence to third parties after explicit authorization.

For production, replace the `Store` implementation with managed PostgreSQL (for example Azure Database for PostgreSQL, Amazon RDS, or an organization-approved service), add authenticated tenant IDs and row-level authorization to every operation, and store uploaded files in private object storage if datasets outgrow database JSON payloads. The service boundaries and explicit mapping/result schemas provide extension points for composite identifiers, multiple sources/fields and provenance without implementing those features in this MVP.

## Streamlit Community Cloud deployment

1. Put the project in a GitHub repository. Review `.gitignore` and ensure only code, configuration examples and synthetic samples are included.
2. Create a Streamlit Community Cloud app pointing to the repository and `app.py`, selecting a supported Python version of at least 3.11. Dependencies install from `requirements.txt`.
3. Add API keys through the app's secrets settings using the example TOML keys. Leave them unset for offline mode.
4. Deploy, load the synthetic data, map columns, run reconciliation, review a correction, and verify the Excel download.
5. Configure appropriate app access for your organization before considering any non-synthetic data.

Community Cloud's local filesystem is not reliable persistent storage: SQLite/checkpoints may disappear after restarts or redeployments. Resume tokens do not back up the database. Use a production database adapter before relying on durable hosted state. Public hosting is not assumed appropriate for confidential client data. Deployment is documented here; this build does not publish a hosted app.

## Validation and limits

The test suite covers exact/normalized/alias/fuzzy matching, duplicate Master and Source identifiers, conflicting values, missing identifiers, placeholders, explicit approvals, related companies, CSV/XLSX identifiers, persistent cache isolation/expiration, mocked research, invented candidates/evidence, API failures/backoff, review audit transactions, Excel integrity, and actual offline Streamlit widget workflows. Recommendation tests cover direct/renamed/fuzzy identities, supported and unsupported inheritance, invalid segments/citations, schema failures, AI approval/rejection/manual overrides, cached/legacy evidence re-evaluation without API calls, protected decisions, and explicit fresh research. A startup smoke test launches a real Streamlit process, checks its HTTP health endpoint, and shuts it down; UI execution is separately checked with AppTest. A representative synthetic workload uses 250 Master and 53,000 Source records.

Full-Source relationship tests place Clinisys at row 53,000 while the local suggestions contain Orchard Group and similar names. Synthetic evidence verifies supported parent/acquisition/merger/subsidiary mappings, renames and aliases, missing entities, unsupported inheritance, negated/unrelated similar names, policy changes, cache re-evaluation, and approval/export persistence. These fixtures are not assertions about the companies' real-world relationships or segments.

Live provider behavior and research quality require real keys and have not been exercised by mocked tests. Retrieved evidence is bounded to five results and 2,200 characters per result; full-Source lookup does not guarantee exhaustive web discovery. Quote/relationship checks are conservative and primarily English; complex phrasing, uncertain direction, incomplete evidence, or unverified name variants may need human investigation. No OCR, legacy XLS files, multi-sheet selection, multiple Source uploads, multiple comparison fields, or enterprise login is implemented. XLSX uses the first worksheet. CSV input must be compatible with Polars' UTF-8 reader. The upload limit is 50 MB per file. Large datasets are held in memory and saved as JSON checkpoints; the current workload is the design target.

## Deployment preparation

See [GitHub and Streamlit Community Cloud preparation](docs/deployment.md) before publishing. It records secret-rotation findings, secure configuration, Cloud service-account authentication, and SQLite persistence limits. Deployment preparation does not deploy the app or migrate workspace data.

Google Translation on Community Cloud supports `[gcp_service_account]` secrets; local ADC remains available when that section is absent. See [Google authentication setup](docs/google-cloud-authentication.md).
