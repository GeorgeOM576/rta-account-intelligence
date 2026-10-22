# Approved translations in reconciliation and AI research

Only current-workspace, current-upload **Approved Translation** records with nonblank English text participate. The join validates the persisted dataset/revision/row/field identity and the unchanged original cell. A draft cache hit is not an approval. Original upload columns are never replaced.

## Workflow

1. Approve translations in the existing Translation Intelligence workspace.
2. Navigate to Run Reconciliation. The current approved English names appear immediately beside the original names in existing results; no reupload or cache reset is needed.
3. Run automatic local matching. Approved name variants are always included; the old optional opt-in is retired.
4. Review translation-assisted proposals separately from translation approval. Final Value remains empty until an account reviewer makes an explicit decision.
5. AI Research and Excel exports resolve current approved names again on navigation/export.

The reconciliation table adds Original Account Name, Approved English Translation, Matched Account Name, Matched Account Approved English Translation, Match Method, Match Basis and Match Score. Existing result/review fields remain available. For unresolved fuzzy records the Source columns describe the leading suggestion, not a verified identity; consult Match Status and Identity Confidence.

## Matching and ambiguity

Original identifier matches retain priority, including aliases, duplicate conflicts and existing relationship policy. Additional comparisons use original and approved English account names on either side. Exact and normalized matches may propose the actual Source comparison value; they never substitute a translated comparison-field value. Fuzzy variants use the same blocked candidate mechanism and remain suggestions without a proposed value.

The matching field is the mapped identifier when it is an account-name field. When separate identifiers are mapped, the first recognized company-name field supplies supplementary names. The current revision and original text must agree with the persisted translation record. The opaque account record ID incorporates dataset, upload revision, row ID and field; it is not an unqualified DataFrame position.

All Source collisions and repeated Master name variants remain ambiguous. Conflicting Source comparison values produce Duplicate conflict and no proposal. Repeated identities with the same value retain Duplicate identifier. A unique translation match is still unverified, because different legal entities can translate to the same generic name. No translation-assisted path grants reliable identity confidence, automatically merges accounts or bypasses human review. Equivalent matching evidence favors originals.

## Research

The original company name is primary. Approved English text is auxiliary context, supplied alongside dataset, stable record identity, original account fields (including available country/location/identifiers), Source candidate fields, and local match evidence. A combined original-and-English query uses the existing **one Tavily search + one OpenAI request** per account budget. Separate extra searches are not introduced.

Prompts explicitly forbid treating translations as verified aliases. Existing citation, quote, relationship and identity validators still determine whether an AI finding supports a recommendation. Similarity or an unsupported generic English name cannot prove identity. The current approved-name context is part of research cache identity; prior-context caches are not substituted for it. Original Source company names also supplement mapped account identifiers during evidence-backed entity lookup; translated names are never treated as verified lookup aliases. Historical research snapshots and human decisions are preserved; rerun fresh research explicitly when new investigation is required.

## Export and compatibility

Reconciliation Results retains prior fields and formatting, adding Master/Source Original Name, Master/Source Approved English Translation, Match Method, Match Basis, Match Score, Research Recommendation and Research Evidence / Sources. Full Master/Source translation sheets, audit trail and formula-injection protections remain intact. No schema deletion or workspace migration is required; new Result fields have defaults for old saved results. Existing human decisions and evidence-backed research proposals remain authoritative on rerun. A past insufficient research snapshot is preserved but does not freeze local candidates when a new translation is approved.

Dependencies: no additions. Existing Polars, RapidFuzz, Streamlit and openpyxl are reused.

No changes were made to the Translation Intelligence UI, Google detection, Google translation, usage accounting, paid API authorization or six reconciliation review filters. No paid API calls were made.

## Verification

Baseline: **476 tests passed**. New mocked integration cases cover all name directions, approval exclusion, normalized/fuzzy variants, generic collisions, identifier priority, revision/original validation, workspace isolation, live SQLite approval visibility through the actual Streamlit reconciliation page, Excel completeness, and research context/evidence rejection.

**Final verification: 496 tests passed in 103.84 seconds**, including 20 new approved-name integration cases. Both Streamlit checks passed: actual application execution/imports and a real local server HTTP health check. No live Google, OpenAI or Tavily calls were made.

The mocked demonstration approves **Les Jardins de Provence → The Gardens of Provence**, finds the original English Source account, proposes its existing SMB value with **Exact — Approved Translation / Master Translation ↔ Source Original**, and leaves Final Value blank. The research test captures both names and account fields in the real Tavily/OpenAI request path. A similarity-only identity assertion is rejected; a separate test accepts a cited explicit identity statement while preserving account identifiers for reviewer selection.

Limitations: generic translated names remain unverified even with a unique local hit; fuzzy candidates require review; separate extra translated-only searches are not issued because that would expand the authorized research budget. Previous provenance/research snapshots remain historical evidence; current approved-translation columns come from current SQLite approvals. Restart the existing Streamlit process once to load the changed modules, resume the workspace, and run reconciliation; no data reset is required.

## Modified files

- `app.py`
- `rta/approved_names.py` (new)
- `rta/translation_matching.py`
- `rta/models.py`
- `rta/research.py`
- `rta/relationships.py`
- `rta/export.py`
- `tests/test_approved_translation_integration.py` (new)
- `tests/test_translation.py` (retired opt-in checkbox interaction)
- `tests/test_translation_e2e.py` (retired opt-in checkbox interaction)
- `tests/test_google_detection.py` (retired opt-in checkbox interaction)
- `docs/approved-translation-integration.md` (new)
