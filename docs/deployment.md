# GitHub and Streamlit Community Cloud deployment preparation

Audit date: 2026-10-22. Preparation only: nothing deployed, pushed or committed; no workspace records modified.

## Readiness and blockers

The sanitized source is suitable for a **fresh private repository after rotating the exposed keys and reviewing the prospective file list**. This is not a certification of any existing remote/history: this directory has no `.git` repository, and `git status` reports “not a git repository.” No tracked files or history could be examined. Ignore rules do not remove previously tracked data or old commits.

The original `.streamlit/secrets.toml.example` contained real-looking OpenAI and Tavily credentials (and malformed TOML). It has been replaced with valid empty placeholders. Treat both original keys as exposed: revoke/rotate them in the respective provider dashboards, update your ignored local secrets and future Cloud secrets, and audit any copies/remotes/backups previously shared. No provider account changes were performed. The real local `.streamlit/secrets.toml` remains on disk, ignored and untouched. Existing database files and checkpoint archives also remain on disk and are excluded from Git.

**Community Cloud is not ready for durable production RTA use without further work:**

1. The existing Google providers use ADC only. There is no adapter from a `[gcp_service_account]` TOML section to Google credentials. Local Mac ADC is not transferred to Cloud. Google authentication must be provisioned separately as described below.
2. SQLite lives on the local filesystem. Community Cloud runtime-generated files are not guaranteed to persist; consequently this storage must be treated as ephemeral. Durable production workspace storage needs an external database or a host with managed persistent storage. This preparation does not migrate the storage engine. [Streamlit file persistence caveat](https://docs.streamlit.io/develop/concepts/configuration/serving-static-files)
3. Credential rotation is an operator action still required. If an existing GitHub repository/history exists elsewhere, it needs a redacted secret/customer-data history audit before reuse.

A disposable, access-controlled demonstration can run without paid-provider secrets, using fictional uploads. Missing keys leave research offline. That does not validate live Google/OpenAI/Tavily permissions or billing.

## Entrypoint and dependencies

Repository root entrypoint: **`app.py`**. Run from the repository root:

```sh
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Keep `app.py`, `rta/`, `assets/`, `samples/`, `.streamlit/config.toml` and `requirements.txt` together. Community Cloud runs from the repository root. [File organization](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)

The declared runtime packages cover Streamlit, Polars, RapidFuzz, openpyxl, requests, jsonschema, langdetect, Google Cloud Translation and now explicit pandas. SQLite, pathlib, json and other standard-library modules require no pip package. OpenAI and Tavily are called through requests; their Python SDKs are not required. pytest is retained for the existing test workflow. Google auth/API-core/gRPC dependencies are installed by `google-cloud-translate`.

`requirements-translation-offline.txt` is optional for the retained Argos fallback, not needed by the Google-first page or clean startup. It also needs separately installed model files and an appropriate interpreter via `RTA_ARGOS_PYTHON`. No model downloads are performed automatically. Do not install that optional heavy stack for this deployment by default.

A fresh Python **3.14** virtual environment was created outside the project, without system site packages, and installed only `requirements.txt`. `pip check` passed. Select Python 3.14 in Community Cloud Advanced settings to match that validation; do not assume the platform default matches your local interpreter. Community Cloud executes on Linux; local clean-environment validation here is macOS, not a completed Linux Cloud build. Existing dependency ranges remain; future resolution can differ. [Dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies), [Python selection](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

Fresh-environment resolved direct versions: Streamlit 1.66.1, Polars 1.44.2, RapidFuzz 3.14.6, openpyxl 3.1.5, requests 2.34.2, jsonschema 4.26.0, langdetect 1.0.9, pytest 9.1.1, google-cloud-translate 3.28.0, pandas 3.1.0.

## Git upload boundaries and audit

Use Git with the supplied `.gitignore`; do not drag the whole local project folder/archive into GitHub, because that bypasses Git ignore filtering. Review staged filenames before any first commit. This preparation did not initialize or stage the real project.

Excluded: all local virtual environments (including `.venv_old`), caches, `.env` variants, real Streamlit secrets, credential/key files, ADC/service-account JSON, resume-token files, SQLite and sidecars, uploaded/generated/customer datasets, logs, checkpoints, backup archives and outputs. Only reviewed fictional/public samples and test fixtures are allowed exceptions for CSV/JSON/XLSX. Credential JSON patterns override fixture exceptions.

A prospective-file audit used isolated Git metadata in a temporary directory so it could evaluate the actual ignore rules without initializing/staging this project. Credential scanning reports only paths/categories, never values. Findings outside the prospective upload are the real ignored local secrets and runtime/backup data. The source/template scan found no remaining embedded OpenAI/Tavily/Google API keys, private-key blocks or private resume-token JSON. This is a pattern-based audit, not proof that arbitrary future files cannot contain sensitive data.

No hardcoded Mac filesystem paths were found in `app.py` or `rta/`. Two historical documentation examples contained a local username/path and were made portable. Historical `/private/tmp` checkpoint references in old reports describe local audit artifacts, not runtime requirements. The original user CSV path is not needed at runtime; the approved visible schema is stored in code and a header-only fixture.

## Secrets and environment variables

| Setting | Existing code behavior | Deployment handling |
| --- | --- | --- |
| `OPENAI_API_KEY` | Read from environment, then root Streamlit secrets | Required for paid AI Research; use a newly rotated key |
| `TAVILY_API_KEY` | Read from environment, then root Streamlit secrets | Required alongside OpenAI for paid research; use a newly rotated key |
| `GOOGLE_APPLICATION_CREDENTIALS` | Read by Google ADC; must point to a real runtime credential/config file | Optional ADC source; a path alone cannot create the file |
| `GOOGLE_CLOUD_PROJECT` | Does not override this app's fixed provider project | Providers currently use `rta-translation` |
| `GOOGLE_CLOUD_QUOTA_PROJECT` | ADC-related setting; clients explicitly specify quota project | Existing clients use `rta-translation`; do not assume this setting changes app configuration |
| `RTA_DB_PATH` | Environment override for default `data/rta.sqlite3` | Optional; changing a local path does not make storage durable |
| `RTA_TRANSLATION_DIAGNOSTICS` | Default `1`; `0` disables structured translation diagnostic events | Optional; logs omit account text/credentials by design |
| `RTA_ARGOS_PYTHON` | Optional offline interpreter | Not needed for Google deployment |

### Streamlit Community Cloud settings

When deployment is separately authorized, choose the private repository/branch, set **main file path `app.py`**, select Python 3.14 in Advanced settings, and paste secrets in **Advanced settings → Secrets**, or later **App settings → Secrets**. Configure app viewing access appropriately; repository privacy is not a substitute for reviewing app access settings. Never commit the real secrets file. [Community Cloud secrets management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)

The existing code supports these root TOML secrets directly:

```toml
OPENAI_API_KEY = "replace-in-cloud-with-new-rotated-key"
TAVILY_API_KEY = "replace-in-cloud-with-new-rotated-key"
# Optional, string values:
RTA_TRANSLATION_DIAGNOSTICS = "0"
```

The repository's `.streamlit/secrets.toml.example` contains empty values only. Do not paste a private workspace resume token into Cloud secrets or a source file.

### Google Cloud authentication: unresolved Community Cloud integration

Cloud Translation Advanced v3 uses ADC/IAM, **not a Google API key**. Project and quota project are `rta-translation`; the API and billing must be enabled. The identity needs suitable translation permissions, such as Cloud Translation API User (`roles/cloudtranslate.user`), and Service Usage Consumer where required for quota-project use. [Google Translation authentication](https://docs.cloud.google.com/translate/docs/authentication), [IAM roles](https://docs.cloud.google.com/translate/docs/api-overview)

ADC can discover a securely mounted credential configuration file via `GOOGLE_APPLICATION_CREDENTIALS`, local developer ADC, or an attached service account on a suitable host. Google recommends workload identity federation for supported external-cloud environments. [ADC discovery](https://docs.cloud.google.com/docs/authentication/application-default-credentials)

For **this unmodified app on Community Cloud**, pasting service-account fields under `[gcp_service_account]` is insufficient: the providers never read that section, and Cloud secrets do not automatically materialize an ADC JSON file. Likewise, setting `GOOGLE_APPLICATION_CREDENTIALS` to a Mac path or a nonexistent Cloud path cannot authenticate. Do not commit a service-account key or copy personal developer ADC into GitHub.

Before enabling Google on Community Cloud, separately implement/review a narrowly scoped secrets-to-credentials adapter, or arrange a supported secure runtime credential mount/workload-identity environment. Store any approved service-account fields only in Cloud's Secrets UI, never in the repository, and ensure the adapter explicitly consumes them without logging/exporting them. An ADC-native hosting platform is another option. No such adapter was added here because this task prohibits application-functionality changes. Google live access remains unverified; no paid calls were made.

## Ephemeral storage impact

A runtime restart/rebuild or lost local filesystem can remove uploaded Master/Source data, saved mapping/results, translation drafts/approvals/manual corrections, decisions/Final Values, audit history, research cache, translation/detection caches and monthly usage settings/records. Workspace tokens identify existing records; they do not contain or recover the database. Exported Excel files are review artifacts, not a full workspace restore system.

Losing caches can cause paid requests to be repeated. Losing usage records resets the local estimate, not Google's charges or billing-account-wide credits. Local monthly tracking must never be treated as authoritative billing. Multiple replicas would also need coordinated durable storage; separate local SQLite copies do not provide shared persistence. No periodic replication, external database or backup restore is implemented by this preparation.

## Validation results

See `docs/deployment-validation.md` for clean-copy startup, full regression results and remaining operator actions. All provider tests use mocks; no Google, OpenAI or Tavily live requests are authorized by this preparation.
