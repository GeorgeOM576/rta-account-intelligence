# Translation Intelligence — integrated Master and Source workflow

> **Current interface:** [Table-first Translation Intelligence workspace](translation-workspace-ui.md) replaces older controls described below. The page offers Google-only detection, selected-row translation, paged review and compact per-batch consent. Monthly accounting and audit history remain in the backend and Excel exports.

> **Current workflow:** [Google-direct v4](google-direct-translation.md) uses supported Google codes directly. Confidence and ambiguity are advisory; historical hard classification gates below are retired.

> **Current provider direction:** Google Cloud Translation Advanced v3 is now the
> default language detection provider. No automatic upload/navigation/API calls
> occur: review the detection preview and explicitly confirm the Google batch.
> Local `langdetect` remains available only as **Local offline (explicit fallback)**.
> Historical local-scan and reanalysis instructions below apply to that selected
> fallback. See [Google-primary transition and validation](google-primary-detection.md)
> for the current Google workflow, checkpoint, migration and test report.


This implements the original engine request and its Master/Source integration
requirements in the existing RTA app. It uses the uploaded datasets, mapped
fields, matching engine, SQLite workspace, account-review workflow and exports.
Original uploads are never overwritten.

## Operation

1. Upload Master and Source. RTA uses field-aware defaults on each side;
   identifiers and classification fields are excluded. In **Translation Intelligence**, independently select
   any number of Master and Source fields, including account names, descriptions
   and comparison fields. Changing selections scans both sides automatically.
2. Inspect separate Master, Source and combined counts. Counts are per selected
   cell, with unique flagged text counts separately labelled. Nonlinguistic
   identifiers, dates, URLs and blanks are skipped. Accents alone do not trigger
   translation. Short, ambiguous and mixed-language values remain Uncertain.
3. Explicitly start Master-only, Source-only or combined translation. Combined
   batches interleave datasets so a shared batch limit does not prioritize Master.
   Unknown/ambiguous values are never batch-eligible. Use **Save confirmed language**
   with a reviewer and confirmation first. Name fields require a separate opt-in
   before producing machine drafts; preserve legal entity names by default.
4. Review original text beside English drafts. Correct the language/text, approve
   each translation, or mark unnecessary translations Not Required. Confirm proper
   names, legal suffixes and identifiers. These approvals are translation approvals,
   not account identity or segment approvals. Corrected approvals retain audit history.
5. On **Run Reconciliation**, explicitly enable approved translations and rerun.
   Only approved, current-dataset translations participate. Original comparisons
   retain precedence; additional exact/normalized English-variant comparisons cover
   original→translated, translated→original and translated→translated identifiers.
   Any selected column can be mapped as an identifier using the existing mapping.
   Approved mapped comparison-field variants are also compared in all available
   directions and retained as contextual agreement, never automatic approval.
6. Translation-assisted proposals use the actual mapped Source comparison value,
   retain original Source row identities and translation provenance, and enter
   **Intelligence Proposed — Pending Approval**. English comparison translations
   remain separate columns, not replacement Source values. Translation-assisted
   identity stays unverified; bulk approval skips it unless the existing independent
   evidence checks establish eligibility. Individual verified approval/Manual
   review uses the existing account-review controls. Final remains blank until then.
7. Account decisions and saved research are preserved on reconciliation reruns.
   Rerunning after new translation approval refreshes undecided local proposals.
   Translation corrections never retroactively rewrite saved account decisions.

The six translation statuses are **Not Required**, **Translation Needed**,
**Translated — Review**, **Uncertain**, **Failed**, and **Approved Translation**.
English and untranslated values have blank English columns rather than unnecessary
copies. Drafts and approvals are distinguishable in every exported translation sheet.

## Runtime compatibility and explicit offline setup

The installed app environment is CPython 3.15.0 on macOS arm64. Actual pip
wheel-resolution checks could not resolve Lingua's compiled/legacy dependencies
or Argos/CTranslate2 for that interpreter. `langdetect==1.0.9` installed successfully
and is the offline detector. Its local profiles ship with the package; no detection
API or language-model download is used. Short-text output is deliberately treated
conservatively instead of trusting its probability as a calibrated confidence.

Argos is an optional provider, not a mandatory dependency that breaks app startup.
Install a compatible supported Python separately, then create a separate environment:

```sh
python3.13 -m venv .venv-argos
.venv-argos/bin/python -m pip install -r requirements-translation-offline.txt
```

Choose/download models explicitly using the official Argos package interface.
For example, the following user-run setup downloads Spanish→English and may
download required sentence-boundary resources on the test translation:

```sh
.venv-argos/bin/python -c 'import argostranslate.package as p; p.update_package_index(); model=next(x for x in p.get_available_packages() if x.from_code=="es" and x.to_code=="en"); p.install_from_path(model.download())'
.venv-argos/bin/python -c 'import argostranslate.translate as t; print(t.translate("Texto de prueba", "es", "en"))'
```

Run an analogous explicit setup for each desired direct-to-English language model.
Alternatively install a locally downloaded `.argosmodel` through
`argostranslate.package.install_from_path(...)`. Setup commands are provided for
the operator; this implementation did not install a second Python or download any
translation models. Verify supported wheels/OS for the separate environment first.

Start RTA with the separate interpreter configured:

```sh
RTA_ARGOS_PYTHON="$PWD/.venv-argos/bin/python" .venv/bin/python -m streamlit run app.py
```

The worker uses only installed direct English models, fingerprints their package
versions, and blocks socket connections. Missing models/resources fail gracefully
instead of downloading. Proper-name/identifier preservation remains a human review
responsibility; drafts are not authoritative translations of legal entity names.
Without compatible models, detection, manual correction/translation approval,
reconciliation using those approved corrections, and exports remain usable.

## Paid fallback

OpenAI fallback is disabled by default. It uses the existing configured research
model and API key, sends only one unique flagged text value per request, and never
sends an entire spreadsheet. It requires explicit per-run consent, positive request,
reserved-token and USD limits, plus operator-entered current input/output rates.
The UI shows a conservative uncached estimate. The dollar bound uses the supplied
rates; verify them against the configured model/account pricing. Request and token
limits are enforced independently before requests, including failed attempts.
No automatic paid retries occur. The original text is treated as data and the
response uses a strict JSON schema. Provider errors are sanitized; keys and
confidential response bodies are not saved in UI/audit/cache or printed by workers.

## Persistence, isolation and performance

Additive `translations` and `translation_cache` tables leave existing project,
research-cache and audit data intact. Cell references include workspace, dataset,
dataset content revision, row index and field. Original text and detected language
are retained separately from confirmed language and reviewer-corrected English.
Approvals and corrections use optimistic version checks and SQLite transactions
with their individual existing-model audit events. Dataset changes invalidate
active row references; prior records/audit history remain in SQLite.

Draft cache keys contain exact original text, source/target language, provider,
model/version and preservation-policy version, scoped by workspace. Master/Source
share drafts, never approvals. Reviewer corrections do not poison shared draft
entries. This is workspace/token isolation using the existing application's trust
model, not a claim of enterprise tenant authentication. Future tenant authorization
must bind every workspace operation to its authenticated tenant.

Detection deduplicates values per field policy across both datasets, using a
workspace-scoped persistent `language_detection_cache` and bounded local model cache. Translation
deduplicates per batch and shares persisted drafts across batches/datasets. Matching
indexes approved variants instead of doing a Cartesian comparison. Review lists
paginate at 50 cells; failed translations can be explicitly retried.

Exports preserve the original four sheets and formatting. With selected translation
records they add Translation Summary, Translation Details, Master Translations and
Source Translations. Generated English/metadata names avoid uploaded-column
collisions. Reconciliation rows and account-review audit events retain direction,
dataset, field, original/English text, provider/model and translation approval
provenance. Original and historical account review values remain unchanged.

## References and validation limits

- [langdetect documentation and deterministic seeding](https://pypi.org/project/langdetect/)
- [Lingua packages and supported runtimes](https://pypi.org/project/lingua-language-detector/)
- [Argos explicit package installation](https://argos-translate.readthedocs.io/en/latest/source/examples.html)
- [Official OpenAI documentation: structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)

Regression tests exercise the real offline detector, all matching directions,
independent dataset selection, shared drafts and isolation, failures, correction
and approval, stale references, paid consent/limits using mocked requests, original
preservation, exports, and the complete Streamlit translation→reconciliation→account
approval path. Live Argos inference awaits explicit compatible runtime/model setup;
live paid translation is intentionally not exercised by tests.

### Google Cloud Translation Advanced v3

Install `requirements.txt`. Select **Google Cloud Translation v3** in Translation
Intelligence. The configured resource and quota project is `rta-translation`,
location `global`, model `general/nmt`, target English, plain text input.
The preview uses the same dataset, field, language, name authorization, unique-text
limit and cache selection as execution. Only flagged non-English values are sent.
It shows unique values, cache hits, uncached characters and estimated USD at $20
per million input Unicode characters before credits (verify current pricing at
https://cloud.google.com/products/translate/pricing). Up to three attempts for
429/503 responses are explicitly disclosed; the retry allowance is three times
the base estimate. Actual billing/credits are controlled by Google.

No API client is initialized until the user confirms and submits a run. Local
credentials use the existing ADC configuration; no keys need to be entered in the
app. The SDK explicitly sets quota project `rta-translation`. The identity needs
Cloud Translation API User access and permission to consume the quota project,
with API and billing enabled. Production uses the hosting platform's ADC identity:
prefer attached service accounts or workload identity federation. If necessary,
the platform may securely mount a service-account credential file and supply
`GOOGLE_APPLICATION_CREDENTIALS`; never commit or upload that file to this app.
Credentials are resolved by the SDK and never copied into SQLite, exports or logs.

Requests group up to 100 values of one language and 30,000 Unicode characters.
A single longer value fails for manual correction. Only 429/503 responses retry,
with 1/2 second backoff, three attempts maximum and 30-second request timeouts;
timeouts and other failures require an explicit new run. Successful batches still
produce drafts if another batch fails. Provider details are suppressed in errors.
Existing project cache entries are reused and successful drafts are cached.
Each cell initially has **Translated — Review** status; individual reviewer
approval remains mandatory for reconciliation matching. Final Value is never
populated by translation. Manual correction and translation remain available.

The optional live smoke test must be confirmed separately before running. It
should send only `Bonjour le monde` (French, 16 characters) to English, estimated
$0.000320 before credits, maximum retry allowance $0.000960. Mocked tests and
startup verification do not require credentials or make translation requests.

### Monthly Google usage estimates

Translation Intelligence shows a persistent, workspace-scoped monthly Google
usage tracker, including when no translation fields are selected. Existing SQLite
databases are upgraded additively with `google_translation_usage` and
`google_translation_usage_settings`; original data and review history are retained.
Each request attempt stores only workspace ID, UTC timestamp, reporting month,
input Unicode character count (including whitespace), and confirmed/uncertain
status. It never stores text, credentials, tokens, or raw provider errors.

An uncertain row is committed **before** dispatch. Every retry records another
attempt. A returned API response confirms submission even if response validation,
identifier checks, caching or per-cell updates subsequently fail. Exceptions,
timeouts, interrupted processes, and failed local usage confirmation remain
uncertain. This deliberately includes attempts that may have been rejected or
never reached Google; confirmed is not a claim of billable usage. If initial
usage persistence fails, dispatch stops; if confirmation persistence fails,
remaining requests stop and the prior uncertain entry is retained. Cache hits,
preflight failures and missing consent do not add request usage.

Reports use calendar months in **America/Toronto** and assign usage to the month
of each attempt's start. The current report switches automatically on the next
render after a month boundary, without deleting or resetting historical rows.
The history table shows each month's confirmed/uncertain characters and attempt
count. Tracking starts with this implementation: earlier translations, the prior
standalone smoke test, other workspaces, and use outside RTA are not backfilled.

The configurable monthly free-credit equivalent defaults to 500,000 characters;
set it to zero when no credit is available, or reduce it to the portion assumed
available to this workspace. It is an estimate, **not** a Google project quota.
Google's monthly credit is shared across eligible Cloud Translation usage in the
billing account, including use outside RTA. Local counts are not Google's actual
billing, do not query billing, and cannot establish remaining shared credit.
The assumption persists per workspace across months. Changing it changes current
cost estimates, not historical usage records. It does not impose an API limit.

At the configured $20 per million NMT input character rate, the tracker uses:

- Potential characters = confirmed + uncertain attempt characters.
- Remaining estimated equivalent = max(0, allowance − potential characters).
- Estimated USD before credits = potential characters × 20 / 1,000,000.
- Estimated USD after assumed credits = max(0, potential characters − allowance)
  × 20 / 1,000,000.

Progress and cost estimates include uncertain characters conservatively. The
warning appears at the earlier of 400,000 characters or 80% of the configured
allowance. With a zero allowance, it warns on any usage and avoids division by
zero. Going beyond the allowance does not block explicitly authorized translation.
Before each batch, the cache-aware preview shows base cost and incremental cost
after the locally estimated remaining equivalent, plus a worst-case three-attempt
retry estimate. Submission still requires explicit consent; changes in reporting
month, usage, allowance or batch selection reset that consent form.

Tests use injected mock Google clients and temporary SQLite databases. They cover
persisted counts, workspace isolation, month/year rollover, Unicode counting,
uncertain failures and retries, downstream rejection, storage failures, cache reuse,
cost calculations, allowance settings, progress/warnings, history and UI consent.
No live translation API calls are made by these tests.

### Field-aware business language detection

The `field-aware-business-v2` policy separates **Confident English — No Translation
Needed**, **Confident Non-English — Translation Candidate**, and **Unknown/Ambiguous
— Manual Language Review**. Excluded fields have a separate outcome. These are
language workflow labels, not account identity verification or calibrated
statistical guarantees. The six account-review filters are unchanged.

Account names require contextual evidence: multiple language cues agreeing with
the detector, supported non-Latin scripts, or an English phrase using context
words beyond shared business vocabulary. Short brands and proper nouns abstain
when evidence is insufficient. A high `langdetect` score, an accent, or a shared
term like Data, Studio or Commercial does not establish the language of a name.
Descriptions and free text can additionally use longer prose context. The first
Latin name cue dictionaries cover French, Spanish and German; other short Latin
names commonly need manual confirmation rather than an automatic foreign label.

In **Language detection settings**, inspect or override field types, explicitly
enable classification fields, and configure business vocabulary. Standard neutral
terms remain conservative; additional terms neutralize unreliable language cues,
not prove English. Types/settings are persisted per workspace. Segment/category/
tier/industry and other classification fields default to excluded; identifier
fields are always excluded. Select an enabled field in the main field selector
when you want to scan it. Exclusions are listed for each dataset and the dashboard
separates English, non-English candidates, ambiguity and excluded cells.

Unknown/ambiguous values and `und` are never submitted automatically to any
translation provider, including when an older caller passes `include_uncertain`.
In the row review form, enter a known source-language code, reviewer and explicit
confirmation, then **Save confirmed language**. This records a language-review
audit entry and makes a confirmed non-English value a candidate; it does not
translate, approve a translation, approve a match, set Final Value or waive the
separate paid API consent. Confirming English marks translation not required.
Manual English entry and translation correction/approval remain available.

On the next read, older automatic detections are refreshed against the new policy.
Existing human reviews and manual language confirmations are preserved. Obsolete
unreviewed drafts are removed from the active English value and retained as
`draft_english`; prior provider cache entries and usage are retained. Disabling a
classification field preserves review history but excludes it from future request
plans and translation matching context. Rerun reconciliation to refresh pending
proposals; saved human account decisions remain authoritative.

Detection cache keys include the policy version, field kind, classification
permission, vocabulary and exact value, and are scoped by workspace. The same
value in a name and a description can intentionally have different outcomes.
See [labelled validation results](language-detection-validation.md) for measured
precision/recall, regressions and remaining ambiguous cases.

### Refreshing stale workspace detections

Use **Reanalyse current workspace languages** to recompute the current dataset
revisions without reusing detection caches. It also refreshes stored deselected
fields (so old classification detections become excluded), while retaining field
selections, human review/correction state, audit history, provider cache, usage and
account decisions. The ordinary **Detect languages in both datasets** button now
also forces recomputation for its selected fields. Neither action calls Google.
Automatic detected-language metadata is refreshed separately from any preserved
reviewer-confirmed language or approved English translation.

Detection row/cache signatures now include a rule-source build fingerprint in
addition to policy/settings. Runtime details compare loaded versus on-disk rules
and show the database/workspace and last reanalysis. Restart Streamlit if the
builds differ; do not delete the database or clear caches wholesale.
**Download current translation CSV** and Excel export use only current selected
enabled fields; excluded classifications are kept as original upload columns,
not active translation records. CSV carries policy/build/analysis timestamps.
See [stale-state diagnosis and exact refresh steps](stale-detection-refresh.md).
