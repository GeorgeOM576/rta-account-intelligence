# Google Translation authentication on Streamlit Community Cloud

Both Detect Languages and Translate Selected now use the same lazy Google Cloud Translation Advanced v3 client factory, `rta/google_auth.py`.

## Configuration and precedence

1. If `st.secrets["gcp_service_account"]` exists, convert that section to a dictionary and call `google.oauth2.service_account.Credentials.from_service_account_info()` with the cloud-platform OAuth scope. Pass the resulting credentials to `TranslationServiceClient`.
2. If the section or local secrets file is absent, construct the client without an explicit credential argument. Google's normal ADC discovery continues to support local macOS development, workload identity or securely mounted host credentials.
3. If the configured section, credential key, secrets file or client setup is invalid, fail with a sanitized message. Never silently fall back to another identity after an explicit configuration error.

Project and quota project remain **`rta-translation`**; the request parent remains `projects/rta-translation/locations/global`. The intended service account is `rta-translation-service@rta-translation.iam.gserviceaccount.com`; the code does not hardcode a particular email or key ID, permitting safe rotation.

In Community Cloud **App settings → Secrets**, retain the configured section. Its required Google JSON fields must be represented as TOML strings, for example:

```toml
[gcp_service_account]
type = "service_account"
project_id = "rta-translation"
client_email = "rta-translation-service@rta-translation.iam.gserviceaccount.com"
private_key = """PASTE THE ACTUAL PRIVATE KEY HERE IN CLOUD SECRETS ONLY"""
token_uri = "https://oauth2.googleapis.com/token"
```

This is documentation, not a usable credential. Copy the actual service-account values only into the Cloud Secrets UI. The private key must parse to a string containing its PEM header/footer and real newline characters; use a TOML multiline string or correctly escaped newlines. The other fields from Google's JSON, such as `private_key_id` and `client_id`, may be included in the section. Never commit a filled-in example or the original JSON file.

Keep unrelated root secrets such as `OPENAI_API_KEY` and `TAVILY_API_KEY` before the `[gcp_service_account]` header, or they become members of that table in TOML. Local users should leave the entire section absent to retain ADC; adding an empty section is an explicit invalid configuration.

The Cloud Translation API and billing must be enabled. The service account must have appropriate permissions on `rta-translation`, such as Cloud Translation API User, plus quota-project service-usage permissions where required. This change does not grant IAM roles, validate the deployed secret contents or make a live permission/billing test.

## Security and existing workflow

Credentials are read only when the existing provider reaches an authorized, nonempty paid batch. Page opening, preview calculation, caching and reruns do not initialize the client or call Google. Explicit consent remains separate for detection and translation. Existing injected mock clients remain supported.

No credential values are logged, written to SQLite, stored in exports, materialized as JSON files or placed in session state. Credentials/client objects exist only in process memory for the provider's action. SDK/parser error text is suppressed because it may include private fields. The factory is not globally cached; a new paid action reads current secrets, allowing key rotation.

The existing module freshness guard includes the authentication helper. Reboot the Cloud app after redeploying changed Python modules if Streamlit reports a stale build. Local restart also clears previously imported modules.

Classification, selected-row/filter scope, translation batching/retries, cost authorization, usage accounting, caching, drafts, approvals, reconciliation and Final Value safeguards are unchanged. All generated drafts still enter `Translated — Review`. Existing local SQLite persistence limitations on Community Cloud remain.

## Verification and redeployment

Mocked tests verify credentials passed to both v3 operations, ADC fallback, absent/invalid/malformed secrets, invalid private-key parsing, sanitized errors/logs, no usage reservation before setup succeeds, no credential material in SQLite, consent before client creation, key rotation and a real Streamlit detection → selection → translation → persisted-draft flow.

No live Google, OpenAI or Tavily API calls were made. The private service-account JSON mentioned in the IDE context was not opened. Successful redeployment requires the correctly configured Cloud section and existing IAM/billing; their live validity is not claimed from mocked tests. See the final test results in the completion report.

## Final results and changed files

- Final full regression suite: **611 passed in 174.55 seconds**, including application import/execution and real local Streamlit HTTP startup checks.
- **14 new mocked authentication tests**, including the real Streamlit detection/translation action path and credential non-persistence checks.
- Focused authentication/research UI regression verification: **74 passed**. A first full run exposed two tests relying on local research keys; the test-only isolation fixture now provides fictional keys and blocks unmocked provider HTTP. Their original no-mutation assertions remain intact. No application changes were made to those workflows.
- `pip check`: no broken requirements. `google-auth` is now an explicit dependency because the helper imports it directly.
- Ready to redeploy the authentication code. Actual Cloud secret validity and live IAM/quota/billing access remain unverified; no paid test was performed and no deployment/push was made.

Files changed:

- `rta/google_auth.py` (new shared lazy factory)
- `rta/google_detection.py`
- `rta/translation_providers.py`
- `rta/translation_runtime.py`
- `requirements.txt`
- `tests/test_google_cloud_auth.py` (new)
- `tests/conftest.py` (new test-only credential/network isolation)
- `.streamlit/secrets.toml.example` (comments only; no empty Google section)
- `README.md`
- `docs/deployment.md`
- `docs/deployment-validation.md` (marks the earlier auth blocker superseded)
- `docs/google-cloud-authentication.md` (new)

No private credential files, real secrets, workspace database records, matching rules, review decisions or Final Value logic were modified.
