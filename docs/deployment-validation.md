# Deployment validation and security audit results

Subsequent update: the hosted Google credential adapter has now been implemented; see [Google authentication](google-cloud-authentication.md). The results below record the earlier deployment-preparation audit; its Google-auth blocker is superseded. SQLite persistence and key-rotation findings remain applicable.

Date: 2026-10-22 (America/Toronto). No deployment, push, commit, provider API calls, database resets or workspace-record changes were performed.

## Result

**Sanitized-source upload: conditional go for a fresh private Git repository after exposed-key rotation and final staged-file review. Full production Community Cloud deployment: blocked on hosted Google ADC provisioning and durable storage.**

No Git metadata is present in this directory. Tracked files, branches, remote history and historical exposures therefore cannot be certified. No real repository was initialized. A temporary isolated Git repository was used only to evaluate `.gitignore` and packaging tests. If a previous remote or another checkout exists, inspect its entire history with a redacted secret scanner and customer-data review before reusing it. Adding ignore rules does not scrub history.

## Security findings and remediation

- **Exposure found:** `.streamlit/secrets.toml.example` contained real-looking OpenAI and Tavily keys. These were removed and replaced with empty valid TOML. Both exposed keys require operator revocation/rotation; their validity was not tested. No credential values are included in this report.
- The real local `.streamlit/secrets.toml` still contains provider keys. It is ignored and was not changed. Workspace databases, resume tokens, uploads, outputs and checkpoint archives were not modified and must remain local.
- Prospective upload scanning found no remaining provider-key patterns, private-key blocks, credential JSON or literal private resume-token JSON. The prospective upload excludes real secrets, SQLite data and generated/customer files. Fixtures retained for tests are the deliberately fictional/public labelled data and header-only schema, not live workspace records.
- The audit is pattern-based and does not prove that arbitrary future text/binary files are safe. Review the staged filenames/content before the first commit; do not upload the entire local folder/archive through a browser.
- No Mac-specific absolute paths were found in the runtime entrypoint/modules. Two historical docs were made portable. Old `/private/tmp` references in reports are historical checkpoint locations, not application dependencies.

## Runtime and clean-environment validation

- Correct entrypoint: `app.py`, executed from the repository root.
- Added explicit `pandas>=2.2,<4`; all directly used mandatory runtime libraries are covered by the existing requirements plus that declaration. Optional Argos remains separate. OpenAI/Tavily use requests, not SDK imports.
- Created a fresh Python 3.14 venv at `/private/tmp/rta-deployment-clean`, without system site packages. Installed only `requirements.txt`; `pip check` found no broken requirements.
- Created a source-only copy at `/private/tmp/rta-deployment-source` using the prospective Git file list. The copy contains neither the real secrets file nor the workspace database/datasets. Application modules in that copy were not modified.
- **Full suite using the clean interpreter:** 596 passed in 207.59 seconds; one HTTP startup test was blocked by sandbox permission to bind localhost.
- **Sanitized source-copy startup and deployment safety tests with localhost permission:** 33 passed in 8.12 seconds. This includes actual `app.py` import/execution, a real Streamlit server returning HTTP health success, and 31 packaging/template/source safety cases.
- Thus all **597 distinct tests** were verified; the sole full-run failure was an environment permission restriction, and that same startup test passed separately. No application test regression remains.
- Clean validation ran on macOS Python 3.14. A real Linux Community Cloud build, hosted credentials, provider access/billing and durable persistence were not tested. No live Google/OpenAI/Tavily requests were made.

## Remaining operator actions

1. Rotate/revoke the exposed OpenAI/Tavily keys and update local/cloud secret stores.
2. Review staged source before a fresh private upload; if reusing another Git repository, audit its history first. Nothing has been uploaded by this task.
3. Follow `docs/deployment.md` for the `app.py` entrypoint, Python version and secure Community Cloud secrets configuration.
4. Resolve Google hosted authentication. Current providers only use ADC; a service-account TOML section alone is not consumed by this code. A secure credential adapter or an ADC-capable hosting arrangement requires separate work.
5. Resolve durable workspace persistence before production use. Community Cloud local SQLite loss would also lose approvals, audit history, caches and local monthly usage estimates; resume tokens do not back up data. Changing `RTA_DB_PATH` alone does not solve this.

## Files changed

- `.gitignore`
- `requirements.txt`
- `.streamlit/secrets.toml.example`
- `README.md`
- `docs/stale-detection-refresh.md` (portable command example)
- `docs/visible-workflow-columns.md` (portable historical CSV reference)
- `docs/deployment.md` (new)
- `docs/deployment-validation.md` (new)
- `tests/test_deployment_safety.py` (new)

No `app.py` or `rta/` application-functionality files were changed by deployment preparation.
