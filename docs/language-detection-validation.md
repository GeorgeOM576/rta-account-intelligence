# RTA V3 — Field-aware language detection validation

October 21, 2026. No live Google Translation calls were made. No new dependencies.

## Result

The six reported business names now resolve to English without a translation flag.
The three reported customer-segment labels are excluded by default. The updated
workflow separates English, non-English candidates, ambiguity and exclusions;
unknown/ambiguous values cannot enter an automatic translation request.

The measured results below use the same 68 manually labelled fixture entries for
both implementations. The fixture contains the reported cases, unique names from
the existing Master/Source XLSX datasets, and extra French/Spanish/German and
ambiguous business-name/prose cases. The original outputs were frozen **before**
the implementation changed. The precision/recall figures are limited to this
regression fixture, not a claim about all real account names.

| Metric | Original policy | Field-aware policy |
| --- | ---: | ---: |
| Foreign false positives | 6 | 0 |
| Foreign true positives | 27 / 28 | 26 / 28 |
| Foreign candidate precision | 81.8% | 100.0% |
| Foreign candidate recall | 96.4% | 92.9% |
| Correct foreign language codes | 26 | 26 |
| English values confidently resolved | 13 / 27 | 23 / 27 |
| English values sent to manual language review | 9 | 4 |

The change retains 26 correctly identified foreign values: **10 French, 9 Spanish,
and 7 German**. All nine unique foreign names in the existing XLSX scenario remain
candidates (ten cells because one value is repeated across the two datasets).
The updated existing end-to-end test still exercises all three translation match
directions, approvals, cache reuse, usage, workspace isolation and Excel export.

## Reported-case regression results

| Value | Original local result | Updated result |
| --- | --- | --- |
| HARBOR HEALTH | Vietnamese; Translation Needed | English; Not Required |
| Cedar Labs | Catalan suggestion; Uncertain | English; Not Required |
| Pioneer Data | Dutch; Translation Needed | English; Not Required |
| Orchard Systems | German; Translation Needed | English; Not Required |
| Bluebird Studio | German; Translation Needed | English; Not Required |
| Summit Holdings | English suggestion; Uncertain | English; Not Required |
| Enterprise (segment) | und; Uncertain | Excluded classification field |
| Healthcare (segment) | und; Uncertain | Excluded classification field |
| Commercial (segment) | und; Uncertain | Excluded classification field |

Four of the six business names were actual foreign candidates in the captured
baseline; Cedar Labs had an incorrect foreign suggestion but remained Uncertain,
and Summit Holdings was an English suggestion incorrectly held for review.
The six total foreign false positives in the wider fixture also include Enterprise
Data Services and Data Studio. These two now abstain rather than being forced to
English. This is not an all-English solution.

## Remaining ambiguity and tradeoff

Thirteen fixture cases remain Uncertain:

- Cobalt Lantarn Supply; Unmatched Velvet Acorn Atelier.
- Enterprise Data Services; Commercial Health Systems.
- Élan; Müller GmbH.
- Orion; Acme; Nova; Café International; Data Studio; Commercial; Health.

Four of these have English fixture labels. Two have known foreign fixture labels
but insufficient language evidence in isolation: Élan and Müller GmbH. These two
count against recall. The original implementation labelled Müller GmbH Turkish,
so abstaining removes an incorrect language assignment while preserving the same
number of correct foreign language codes overall. IBM is treated as an excluded
code rather than being asserted English or foreign.

These cases require a reviewer to confirm a known language or enter a manually
reviewed translation. The removed include-uncertain shortcut cannot bypass this
requirement, even through the legacy Python call argument. Saving a confirmed
language is audited and does not constitute translation approval or paid consent.

The English context vocabulary and multilingual cue dictionaries are deliberately
bounded. Short brands, loanwords, mixed scripts and names in other Latin languages
can require manual review; richer descriptions use a separate prose policy.
Configured business vocabulary supplies neutral terms, not declarations that a
company is English. The source detector's scores are not calibrated probabilities
of a business name's real language. Its own [documentation](https://github.com/Mimino666/langdetect)
notes the limitations of short/ambiguous inputs and explains deterministic seeding.

## Persistence and safeguards verified

- Field types, classification opt-ins and business vocabulary persist by workspace.
- Detection deduplicates identical values within a policy across both files and
  reuses a persistent workspace-scoped cache, including across engine restarts.
- Cache keys distinguish field types, vocabulary, opt-in and policy version.
- Existing automatic v1 detections are refreshed on read, including unreviewed
  false-positive machine drafts. Superseded drafts are retained for inspection.
- Translation approvals, manual language confirmations, audit history, usage and
  provider translation cache remain intact. Reviewed values are not overwritten.
- Disabled classification fields cannot enter request plans or matching context,
  even if a prior approved translation remains in historical state.
- No automatic ambiguous/und submissions occur; manually confirmed language still
  requires the existing explicit paid batch confirmation.
- Account review filters, approval-only reconciliation and Final Value safeguards
  remain covered by the existing end-to-end regression tests.

## Test execution

New detector regressions: **35 passed**. Full suite: **314 passed, 0 failed in
58.34 seconds**, including application import/execution and real Streamlit HTTP
startup health checks. The initial complete sandbox run had 313 passes; its only
failure was the sandbox blocking the localhost socket. The complete rerun with
localhost permission passed. Google calls were mocked throughout.

## Files changed

Application:

- `rta/language_detection.py` — field-aware evidence policy and neutral business vocabulary.
- `rta/translation.py` — settings, persistent detection cache, migration, manual language review, eligibility and metrics.
- `rta/translation_ui.py` — field settings, exclusion/outcome displays, language confirmation and removal of uncertain batch opt-in.
- `rta/storage.py` — additive workspace-scoped detection-cache table.
- `rta/translation_matching.py` — exclude disabled fields from approved translation evidence.
- `app.py` — field-aware upload defaults.

Tests and fixtures:

- `tests/test_language_detection.py` — reported false positives, genuine foreign names, quality thresholds, cache/isolation, settings UI, migration and manual review regressions.
- `tests/test_translation.py` — intentional new ambiguity/name-permission/classification opt-in expectations.
- `tests/test_translation_e2e.py` — improved English detection expectations; foreign-name and approval checks retained.
- `tests/fixtures/language_detection/labelled_cases.json`.
- `tests/fixtures/language_detection/baseline_v1.json`.
- `tests/fixtures/language_detection/evaluate.py`.
- `tests/fixtures/language_detection/evaluation.json`.
- `tests/fixtures/language_detection/README.md`.
- `tests/fixtures/translation_intelligence/README.md` — current detector expectations.

Documentation:

- `docs/translation-intelligence.md` — updated workflow and policy details.
- `docs/language-detection-validation.md` — this report.

No usage-tracker, provider authentication, account review, Final Value, or unrelated
RTA business logic was changed. Existing XLSX input fixtures are unchanged.
