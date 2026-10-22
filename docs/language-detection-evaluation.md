# Translation Intelligence language-detection evaluation

## Superseded policy notice — Google-direct v4

The user subsequently authorized a simplified Google-first workflow. See [the current workflow, test results and complete changed-file list](google-direct-translation.md). Valid supported Google codes now determine effective English/non-English classification; confidence and competing alternatives are advisory, and missing/unsupported/failed results stay blocked. All baseline reports and fixtures below remain historical evidence rather than current gating rules.

The fixed-corpus v4 rerun is [results_google_direct.json](../tests/fixtures/language_detection/company_evaluation/results_google_direct.json): on 118 definitive mock/captured cases, 110 language/routing agreements, 8 disagreements, no blocking manual classifications, foreign precision 97.83% and recall 94.74%. There are **39 advisory review flags across all 149 names**. Deliberately wrong mock suggestions pass through the direct policy; this is not a Google accuracy estimate or a claim that every valid suggestion is correct. All English drafts still need explicit human approval. The 25 saved real responses have 23/23 definitive agreement and six advisory flags. No live calls were made. Production safeguards for approvals, reconciliation and Final Value remain unchanged.

## Implemented refinement — October 22, 2026

The explicitly authorized **foreign-only contextual legal-suffix refinement is now implemented** as `google-foreign-legal-context-v3`. Google confidence remains **0.90**, and the 0.20 competing-result margin and all other guards remain unchanged. Only a non-English account-name suggestion with at least three tokens outside the existing legal-suffix and business-vocabulary sets can bypass the legal-suffix veto. English suggestions retain that veto regardless of context. There are no name-specific exceptions.

The complete original evaluation report below and its original `results.json` are retained as the baseline. The fixed 149 labels and raw responses were not changed. The rerun is saved separately in [results_after_refinement.json](../tests/fixtures/language_detection/company_evaluation/results_after_refinement.json), with original/new per-case outcomes, counterfactual results and explicit safety checks. Its additional threshold scenarios remain diagnostic only; no threshold alternative was implemented.

### Before and after on the fixed 149-name corpus

These are **policy stress-test metrics**, not estimates of real-world Google accuracy. Language metrics use 118 definitive cases; 31 explicitly ambiguous cases are tracked separately.

| Measure | Before v2 | After v3 |
|---|---:|---:|
| Correct automatic language/routing | 71 | **75** |
| Incorrect automatic language/routing | 3 | **3 — unchanged** |
| Definitive manual reviews | 44 | **40** |
| All manual-review outcomes, including ambiguous | 71 | **67** |
| Potentially unnecessary high-confidence reviews | 5 | **1** |
| Foreign precision | 100% (58/58) | **100% (62/62)** |
| Foreign recall | 61.05% (58/95) | **65.26% (62/95)** |
| Correct-language foreign recall | 60.00% (57/95) | **64.21% (61/95)** |
| Foreign names missed | 37 | **33** |
| Foreign names incorrectly classified English | 2 | **2 — unchanged** |
| Ambiguous names incorrectly automated | 3 | **3 — unchanged** |
| Additional wrong-English legal counterfactuals accepted | 0/4 | **0/4** |

Exactly these four classifications changed, all from manual review to the correct foreign-language candidate:

- **Les Ateliers du Rivage SAS** → French.
- **Servicios de Ingeniería Rivera SA** → Spanish.
- **Deutsche Werkstätten am Fluss GmbH** → German.
- **Empresa de Energia Renovável Ltd** → Portuguese.

All four use synthetic 0.99 responses. The 25 saved real-response cases remain **19 correct automatic, 0 incorrect, 4 definitive manual reviews, 100% foreign precision and 87.5% foreign recall**. All 23 English-labelled and all 31 ambiguous-case outcomes are unchanged. The six reported English regression names retain their prior outcomes. The three pre-existing synthetic errors, including two wrong-English stress cases, are neither fixed nor increased by this targeted change.

The four recovered names were also replayed with fabricated en/0.99 suggestions: all still require manual review. Low confidence, competing languages, mixed scripts, short legal/brand names, neutral vocabulary and unknown inputs retain their guards. Müller GmbH, Élan, Toyota Motor Corporation and Samsung Electronics Ltd remain protected in the added regressions. No new English classification is introduced.

### Persistence and authorization

The raw Google response cache version is unchanged, while the interpretation policy/build changes. A full Streamlit restart loads the new policy; **Refresh from cached Google detections (no API calls)** safely reinterprets existing workspace-scoped raw responses. It cannot detect uncached values. Existing code continues to preserve human language corrections, approved English translations, audit history and reconciliation decisions. No API authorization, translation approval, Final Value or workspace-isolation rule changed. Regression tests verify protected legal-name records and usage remain unchanged on cache refresh.

### Files modified in this implementation

- `rta/google_detection.py`: only the legal-suffix condition, explanatory comment and classification-policy version.
- `tests/test_legal_suffix_detection.py`: four recovery cases, English counterfactuals, confidence/margin guards, brands/ambiguity, the fixed-corpus release gate and protected cache refresh.
- `tests/test_language_evaluation.py`: retain the original five-review baseline assertion and assert the refined one-review result.
- `tests/fixtures/language_detection/company_evaluation/evaluate.py`: preserve baseline labels/results; produce a separate rerun and fail if classification deltas extend beyond four correct recoveries.
- `tests/fixtures/language_detection/company_evaluation/results_after_refinement.json`: new full rerun and before/after evidence.
- `docs/language-detection-evaluation.md`: this implementation update; baseline report retained below.

No dependencies or database schemas changed. No live Google API calls were made. Focused regression tests: **57 passed**. Complete regression suite: **405 passed, 0 failed, 0 errors in 78.55 seconds**, including real Streamlit HTTP startup and application execution. The refinement passed the fixed-corpus safety gate and is retained; independent native-speaker and representative real-response validation remain limitations rather than claims made by this test.

## Original evaluation decision — retained baseline

**Keep the production threshold at 0.90. No production detection changes have been applied.** The best next safeguard experiment is a contextual legal-suffix refinement **restricted to non-English suggestions**, keeping all current English gates intact. In this diagnostic it removes four candidate unnecessary reviews without adding errors. A broader relaxation recovers five but fails a separate wrong-English counterfactual. These benefits exist only in synthetic cases: the saved live-response subset contains no such recoverable high-confidence suffix cases. Independent validation is needed before implementation.

A blanket confidence reduction is not supported. Lower thresholds improve recall in the small saved sample, but admit additional wrong classifications in the deliberately adversarial mocks. Removing the brief-Latin-name safeguard increases false certainty on ambiguous brands without recovering any definitively labelled names in this corpus.

## Scope and reproducibility

This is an **offline classification-policy diagnostic**, not a new measurement of Google's real-world accuracy. No Google client, ADC lookup, paid API, database cache import or workspace mutation is used by the evaluator. Approvals, reconciliation, translation execution and Final Value safeguards are untouched.

Artifacts:

- [Manually labelled corpus and response provenance](../tests/fixtures/language_detection/company_evaluation/labelled_cases.json).
- [Offline evaluator and isolated alternative-policy experiments](../tests/fixtures/language_detection/company_evaluation/evaluate.py).
- [Complete per-case outputs and metrics](../tests/fixtures/language_detection/company_evaluation/results.json).
- [Evaluation isolation/provenance tests](../tests/test_language_evaluation.py).

Reproduce from the project root:

```sh
PYTHONPATH=. .venv/bin/python tests/fixtures/language_detection/company_evaluation/evaluate.py
.venv/bin/python -m pytest -q
```

The production entry point is `rta.google_detection.interpret`, policy `google-script-aware-v2`. The results artifact records its loaded source hash. Alternative functions are compiled into copied diagnostic namespaces; they do not assign to production constants, modify production files, or write workspace records. The production threshold remains **90%** throughout.

## Dataset and manual labels

**149 unique company-name strings**, with **118 definitive labels** and **31 explicitly uncertain labels**. All cases are evaluated as account-name fields. Classification fields/identifiers are not mixed into the language benchmark.

| Expected label | Names |
|---|---:|
| English | 23 |
| French | 14 |
| Spanish | 14 |
| German | 14 |
| Portuguese | 13 |
| Arabic | 13 |
| Chinese | 12 |
| Japanese | 13 |
| Italian, retained from saved benchmark | 2 |
| Ambiguous/mixed/brand — no definitive language | 31 |
| **Total** | **149** |

The corpus includes the six English regression names, accented text, long descriptive company names, short names, legal suffixes, mixed scripts, Han/kana Japanese, Chinese, Arabic, shared business vocabulary and 20 international-brand/proper-name examples. It is a purposive challenge set, not a random production sample; confidence-boundary cases are intentionally overrepresented.

A definitive label describes the language of the **name's descriptive wording**, not the nationality, registered jurisdiction or official language of a real company. Newly authored descriptive names are fictional and manually labelled for this diagnostic. Real brands such as Google, Microsoft, Toyota, Sony, Samsung, IKEA, Nestlé and L’Oréal have **no definitive expected language**. Country of origin was not used to guess a language. Müller GmbH, Élan, short shared-vocabulary names and Han-only 星河科技 are explicitly uncertain. Japanese-script or Han script alone is not treated as proof of a company's nationality.

These are author-curated annotations, **not independent native-speaker adjudications**. A second reviewer should validate labels before using the corpus as a release gate. This limitation is particularly relevant for short or cross-language names; their uncertain labels must not be replaced with guesses to improve metrics.

### Response provenance

| Response source | Cases | What it establishes |
|---|---:|---|
| Previously authorized, saved live Google responses | 25 | Real captured responses; no new calls. Codes/confidences copied unchanged. |
| Synthetic response stimuli | 124 | Policy behavior under prescribed confidence, error and ambiguity conditions. Not Google error frequencies. |

For descriptive synthetic cases, the normal mock language follows the manual label with a predeclared confidence schedule shared across languages. This tests policy routing and inevitably makes most mock suggestions correct by construction. Explicit counterexamples inject wrong English suggestions, wrong foreign-language suggestions and competing alternatives. Their frequencies are designed stress cases, **not estimated Google accuracy or calibration**. Brand responses are also fabricated and marked accordingly.

The two sources are reported separately below. Aggregate metrics describe this particular mix only and must not be advertised as production precision/recall.

## Original detection policy examined (v2 baseline)

1. Google Advanced v3 is primary. Raw code/confidence/source remain separate from effective RTA classification; cached responses and human decisions remain distinct.
2. Confidence must be **at least 0.90**. The top result must lead competing alternatives by **at least 0.20**. A score of 0.8993325 does not pass 0.90; display rounding should not hide that boundary.
3. Disabled classifications/identifiers, blanks, nonlinguistic values, URLs/emails, codes, dates and short uppercase abbreviations are structurally excluded. `IKEA` exercises this exclusion rather than language review.
4. Multiple scripts trigger review, except the normal Han/hiragana/katakana combination. Detected languages conflicting with recognized scripts also trigger review. Not every Unicode script/language is mapped.
5. Single-token ASCII names trigger review. The same single-token check is not applied identically to accented Latin text, an asymmetry worth investigating separately.
6. Account names made entirely of neutral business vocabulary, or containing **any recognized legal suffix**, trigger review regardless of otherwise strong descriptive evidence.
7. Brief non-English Latin-script account names with fewer than three tokens and fewer than twelve letters trigger review. Whitespace word-count restrictions do not apply to Chinese/Japanese/Arabic and other non-Latin scripts.
8. Passing foreign results become **translation candidates**, not translation approvals or permission to replace official names. Unknown/ambiguous values never enter automatic translation without explicit source-language confirmation.

## Results from the 25 saved live responses

These are the only captured Google measurements in this evaluation.

| Measure | Result |
|---|---:|
| Definitive labels | 23 |
| Raw Google language agreement | **23/23 (100%)** |
| Correct automatic RTA language/routing | **19/23 (82.61%)** |
| Incorrect automatic classifications | **0** |
| Definitive cases sent to manual review | **4** |
| Foreign candidate precision | **100% (14/14)** |
| Foreign candidate recall | **87.5% (14/16)** |
| Foreign names classified English | **0** |
| Ambiguous expected cases safely retained | **2/2** |

The four reviews are Cedar Labs (0.547146), Pioneer Data (0.437176), Boulangerie du Soleil (0.780919) and Haus der Technik (0.899333). Google suggested the correct language in all four, but each fell below the current confidence threshold. **None is a high-confidence safeguard-only unnecessary review.** Calling all four unnecessary would confuse hindsight label agreement with evidence available to the classifier.

All six previously misclassified English names are raw Google English; four classify English automatically and two remain manual for low confidence. Japanese and Chinese classify correctly without space-based restrictions. Müller GmbH and Élan remain manual. Lowering the isolated threshold to 0.85 or 0.80 recovers Haus der Technik: correct automatic classifications become 20/23 and foreign recall 93.75%, with no errors in this very small sample. This does not establish that lowering the threshold is safe generally.

## Original policy on the full stress corpus (v2 baseline)

**The following are synthetic policy-stress results, not a real-world Google accuracy estimate.**

| Measure | Result |
|---|---:|
| Definitive cases | 118 |
| Correct automatic language/routing | **71 (60.17% of definitive cases)** |
| Incorrect automatic language/routing | **3** |
| Definitive manual reviews/abstentions | **44** |
| Potentially unnecessary high-confidence safeguard-only reviews | **5** |
| Foreign candidate true positives | **58** |
| English falsely made foreign candidates | **0** |
| Foreign names missed as automatic candidates | **37** |
| Foreign names incorrectly made English | **2** |
| Foreign candidate precision | **100%** |
| Foreign candidate recall | **61.05%** |
| Correct-language foreign recall | **60.00%** |
| Ambiguous cases safely deferred/excluded | **28/31** |
| Ambiguous cases incorrectly automated | **3/31** |

Of 74 automated definitive cases, 71 are correct (95.95%). Abstentions are not counted as correct, but are also not conflated with confidently wrong language assignments. Binary foreign precision can be 100% while some foreign names are incorrectly assigned English or the wrong foreign language: the separate error measures above make this visible.

The **124 synthetic cases alone** have 95 definitive labels: 52 correct automatic classifications, 3 incorrect and 40 manual; foreign precision 100%, recall 55.70%. The remaining results come from the 25 saved cases. Combining them is useful for a reproducible policy challenge set, not for estimating a production error rate.

### Confusion counts

| Expected | RTA English | RTA foreign candidate | Manual review | Structural exclusion |
|---|---:|---:|---:|---:|
| English, 23 | 14 | 0 | 9 | 0 |
| Foreign, 95 | 2 | 58 | 35 | 0 |
| Ambiguous, 31 | 1 | 2 | 27 | 1 |

One of the 58 foreign candidates has the wrong foreign language code. The 37 missed foreign candidates comprise **35 manual deferrals plus 2 wrong-English decisions**. Ambiguous cases are excluded from definitive-language precision/recall and reported separately; structural exclusion is safe non-automation, not a successful language determination.

### Results by definitive expected language

| Language | Cases | Correct automatic | Incorrect automatic | Manual |
|---|---:|---:|---:|---:|
| English | 23 | 14 | 0 | 9 |
| French | 14 | 7 | 2 | 5 |
| Spanish | 14 | 9 | 0 | 5 |
| German | 14 | 7 | 1 | 6 |
| Portuguese | 13 | 7 | 0 | 6 |
| Arabic | 13 | 9 | 0 | 4 |
| Chinese | 12 | 7 | 0 | 5 |
| Japanese | 13 | 9 | 0 | 4 |
| Italian | 2 | 2 | 0 | 0 |

### Manual-review causes

Among the 44 definitive manual cases:

- **37** have low confidence or insufficient top-result margin.
- **5** have a legal-name/business-vocabulary veto despite correct mock code, confidence 0.99 and clear descriptive wording.
- **2** have a script/code conflict and are correctly deferred despite the definitive label: the injected API suggestion is wrong.

The five potentially unnecessary review candidates are:

| Name | Expected | Mock confidence | Current reason |
|---|---|---:|---|
| Harbor Coastal Research LLC | English | 0.99 | Legal suffix |
| Les Ateliers du Rivage SAS | French | 0.99 | Legal suffix |
| Servicios de Ingeniería Rivera SA | Spanish | 0.99 | Legal suffix |
| Deutsche Werkstätten am Fluss GmbH | German | 0.99 | Legal suffix |
| Empresa de Energia Renovável Ltd | Portuguese | 0.99 | Legal suffix |

All five are **synthetic**. Legal suffixes do not prove language; the proposal is to evaluate the remaining descriptive wording while retaining the suffix/original, not to infer language from the suffix.

### Incorrect classifications and ambiguity examples

| Name | Expected | Injected suggestion | Current outcome | Interpretation |
|---|---|---|---|---|
| Société des Services Portuaires | French | en, 0.96 | English | A confident wrong English result on Latin text is not vetoed. |
| Bäckerei Sonnental | German | en, 0.96 | English | Same failure mode; accents alone do not resolve language. |
| Les Artisans du Vieux Moulin | French | es, 0.97 | Spanish candidate | Binary foreign routing succeeds, exact language fails. |
| Atelier Lumière | Ambiguous | fr, 0.93 | French candidate | Letter-length context surrogate does not establish brand language. |
| 星河科技 | Ambiguous | zh, 0.93 | Chinese candidate | Han-only brand text can be uncertain even at a high supplied score. |
| Atelier Casa Verde | Mixed/ambiguous | en, 0.96 | English | Mixed languages can share Latin script; script checks cannot detect all mixtures. |

These suggestions are fabricated stress inputs, not observed Google mistakes. The examples show what the current safeguards can and cannot prevent if such responses occur.

## Alternative policies — evaluated only, not applied

All alternatives use the same fixed labels and responses. The contextual suffix alternative retains the 0.90 threshold and allows the suffix veto to relax only when at least three non-suffix/non-business-vocabulary tokens remain. That is an experimental context surrogate, not a validated language detector. No individual name exceptions were used.

| Diagnostic policy | Correct | Wrong | Definitive manual | Foreign precision | Foreign recall | Foreign as English | Ambiguous automated |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Current 0.90** | **71** | **3** | **44** | **100%** | **61.05%** | **2** | **3** |
| Global 0.80 | 95 | 5 | 18 | 98.73% | 82.11% | 3 | 3 |
| Global 0.85 | 87 | 5 | 26 | 98.61% | 74.74% | 3 | 3 |
| Global 0.95 | 34 | 3 | 81 | 100% | 29.47% | 2 | 1 |
| Foreign threshold 0.85, English stays 0.90 | 84 | 4 | 30 | 98.61% | 74.74% | 2 | 3 |
| Contextual legal-suffix relaxation, 0.90 | 76 | 3 | 39 | 100% | 65.26% | 2 | 3 |
| **Foreign-only contextual suffix relaxation, 0.90** | **75** | **3** | **40** | **100%** | **65.26%** | **2** | **3** |
| Remove brief-Latin-name veto, 0.90 | 71 | 3 | 44 | 100% | 61.05% | 2 | 8 |
| Contextual suffix + remove brief-Latin veto, 0.90 | 76 | 3 | 39 | 100% | 65.26% | 2 | 8 |

A global threshold reduction admits an additional wrong-English Portuguese example and a false foreign candidate among English names. Restricting the reduction to foreign suggestions avoids the additional wrong-English result here but still introduces that false foreign candidate. Keeping 0.90 and refining the suffix veto only for non-English suggestions recovers four correct cases; English-side decisions are unchanged by construction. It does not fix the two existing high-confidence wrong-English stress failures. Removing brief-Latin safeguards increases ambiguous automation from 3 to 8 and is not recommended.

### Additional legal-name wrong-English counterfactual

Outside the main 149-case metric set, four existing definitively foreign legal-name cases were replayed with a fabricated **en / 0.99** suggestion instead of their correct mock code. Labels/text stayed unchanged. Current policy defers all four; broad contextual suffix relaxation incorrectly classifies all four English. **Foreign-only contextual suffix relaxation still defers all four.** This demonstrates why positive-case recovery alone cannot justify relaxing the English side. These extra response scenarios are stored separately in results.json and do not inflate the main corpus size or denominators.

## Original recommendations (only recommendation 2 implemented above)

1. **Retain 0.90 and the competing-result margin.** Treat the saved 25-case gain at 0.85 as an investigation lead, not a calibration study. Never lower English confidence requirements to reduce the manual queue.
2. **Validate a foreign-only contextual legal-suffix refinement first.** Preserve original names and suffixes, inspect descriptive evidence outside the suffix, and keep brands/short legal entities such as Müller GmbH ambiguous. Keep existing English-side vetoes: the separate counterfactual shows the danger of relaxing them. The current blanket veto causes five high-confidence, definitive safeguard-only deferrals; the conservative experiment recovers four foreign cases and deliberately leaves the English LLC case in review. Do not deploy the token surrogate without a held-out, independently labelled cached-response set.
3. **Separate detection confidence from entity-name translation permission.** A legal name can have recognizable language while still requiring translation approval and brand preservation. Retain both decisions rather than using a legal suffix as proof of either English or foreign language.
4. **Keep short-name review, but replace length-only evidence with a validated context rule in a later experiment.** Blanket removal fails the ambiguity test. Accented single-word handling and sufficiently long but ambiguous brands deserve targeted tests; accents and Han script are supporting signals, not definitive language labels.
5. **Protect foreign names against confident wrong-English suggestions.** Investigate routing to review when strong contradictory descriptive-language evidence or conflicting cached/manual language decisions exist. Evaluate those as proposed review triggers, never as an automatic English override. The existing Unicode conflict check catches the injected Arabic/Chinese English errors but cannot catch Latin-language conflicts.
6. **Distinguish review reasons in the queue.** Low score, close alternatives, pending/no detection, script conflict, legal suffix and brand ambiguity should be visible separately. Group duplicate language-review work carefully while preserving cell-specific corrections/audit; reduced reviewer effort is different from improved detection recall. No bulk language-confirmation implementation is proposed here.
7. **Validate before implementing.** Obtain a second human label review, hold out names independently of rule design, and use authorized existing cached responses with consent/privacy boundaries. Prefer source-balanced samples and enough genuine boundary scores for each language. No new paid collection is authorized by this report. Track wrong-English foreign decisions and ambiguous automation as release gates, not precision alone.

These recommendations do not authorize or implement production changes. The threshold, confidence/script safeguards, translation approvals, matching rules and Final Value protections remain unchanged.

## Limitations

- Only 25 responses are real captured Google results; there are no real Arabic/Portuguese boundary observations beyond that sample's captured cases. Broader language/profile performance here is synthetic.
- Synthetic codes mostly follow the expected labels and confidence values were prescribed. Neither mock accuracy nor aggregate recall estimates Google's performance.
- The challenge set deliberately overrepresents ambiguity and confidence boundaries; its percentages do not estimate the size of RTA's production manual queue.
- Expected labels are author-curated and not independently adjudicated. No official company identity, brand translation or registration is established.
- Incorrect foreign-language codes require separate tracking from English/foreign routing; a correct candidate category alone does not make translation safe.
- No production detection, SQLite data, API usage, review approvals, reconciliation or Final Value behavior was changed.

## Original evaluation tests and changed artifacts

Only evaluation/test/documentation files were added: the evaluator, its labelled JSON corpus, generated per-case results, `tests/test_language_evaluation.py`, and this report. The new tests check provenance, explicit uncertainty, metric partitioning, captured-response replay, zero client construction, wrong-English suffix counterfactuals and alternative-policy isolation with the production threshold fixed at 0.90.

**391 tests passed, 0 failed, 0 errors in 78.03 seconds**: all 387 existing regressions plus four new evaluation tests. This includes real Streamlit HTTP startup and application execution. A final SHA-256 check confirmed the production detection source still matches the evaluation's original source hash, and its threshold is still 0.90. No production improvements were implemented and no live paid calls were made.
