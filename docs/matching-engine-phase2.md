# Matching Engine Optimization Phase 2 — local benchmark

The engine resolves 15 additional accounts: 35/50 correct actual matches and 35 correct proposals (70% coverage), with no incorrect accepted matches or proposals in this benchmark. First-choice candidate accuracy rises to 48/50. All 20 Phase 1 matches/proposals are retained; no first-choice regressions.

## Method

Current means the saved Phase 1 local run in /private/tmp/rta-benchmark-50, not the older Good Test.csv result (8 proposals). After uses the same 50-row Master and Source files and exactly the same 16 saved approved-translation inputs. Input SHA-256 hashes match Phase 1. Expected identities use the same corresponding-row Source reference; there is no independent identity crosswalk. Translation approval audit records are not present: reuse of the export's explicitly approved-name column remains a benchmark assumption. No expected Source names were inserted as translations.

## Comparison

| Metric | Current (Phase 1) | Phase 2 |
|---|---:|---:|
| Correct first candidates | 47/50 | 48/50 |
| Correct actual matches | 20/50 | 35/50 |
| Correct Segment proposals | 20/20 | 35/35 |
| Proposal coverage | 40% | 70% |
| Proposal precision | 100% | 100% |
| Incorrect accepted matches | 0 | 0 |
| Incorrect proposals | 0 | 0 |
| Unresolved accounts | 30 | 15 |
| Automatically finalized values | 0 | 0 |

Raw-CSV control (no translations): correct first candidates 41/50 → 42/50; correct actual matches/proposals 15 → 30; coverage 30% → 60%; precision remains 100%; zero incorrect matches/proposals and zero final values. Phase 2 raw proposals were explicitly checked for both Source identity and Segment correctness.

The 18-account multilingual subset (rows 6–20, 25, 47, 48) improves from 15/18 to 16/18 correct first candidates and from 5/18 to 11/18 actual matches/proposals. The specific three hard cases remain without accepted matches or proposals. Severny Veter LLC is now ranked first via Cyrillic romanization, used only for ranking. Boulangerie du Soleil and Casa de Moda Bella still have incorrect first suggestions. Bakery of the Sun is not treated as an approved alias for Sunshine Bakery; Casa has no approved translation. Optional Translation Intelligence can collect a new translation for explicit review; none was requested, auto-approved or paid for in this phase.

## Engineering behavior and safeguards

New bounded keys apply only to company-name fields: Unicode NFKD accent folding; German umlaut/digraph variants; terminal legal forms including Co./Company, GmbH and SA; controlled Pharma/Pharmaceuticals, Telecom/Telecommunications and Edu/Education expansions; explicit plural pairs. Original names, Segment values and approved translations are never rewritten. There is no broad stemming, semantic synonym table, arbitrary token sorting or deletion of business words such as Partners, Group, Distribution or Center.

Exact/normalized identifier rules retain precedence; explicit identifiers do not use the new company-name equivalences. Deterministic keys force candidate priority over fuzzy scores. All matching key variants must agree on one Source record, including suffix and transformed collisions. Competing transformed names with very close similarity (96% character ratio or greater) cause abstention; fuzzy scores never generate proposals alone. Conflicting approved-name evidence and transformed original-name evidence cause review rather than silent replacement. New equivalences remain Medium confidence and do not gain reliable-local bulk approval eligibility. Cyrillic romanization stays Low confidence, does not manufacture an approved translation and never produces a proposal by itself.

Matching provenance records the method applied to either side; approved translations retain their existing provenance. The matching-input signature version was incremented so previously saved runs are marked stale until explicitly rerun. Existing reviewed decisions are retained through the existing workflow. No database schema or integration changes.

## Every previously unresolved row

Most rows were already correctly ranked but failed conservative acceptance rules; they were not candidate-generation failures. Rows 11, 16 and 47 had candidate-generation/ranking failures. Unsupported semantic/word variations still fail acceptance rather than being upgraded on similarity alone. Confidence reflects the accepted evidence; no fuzzy confidence threshold was loosened to force coverage.

| Row | Master | Primary failure category | Original bottleneck | Outcome and explanation |
|---|---|---|---|---|
| 5 | sunrise retail co. | Company legal suffix variations | Acceptance rules | Newly resolved: Co./Company are terminal legal forms. |
| 7 | MÜLLER MASCHINENBAU GMBH | Transliteration | Acceptance rules | Newly resolved: German umlaut-to-digraph variant, plus terminal GmbH handling; retains approved translation provenance. |
| 9 | Compañía de Alimentos del Sur | Unicode accents and diacritics | Acceptance rules | Newly resolved: Accent-folded original names agree. |
| 10 | SOCIÉTÉ DES TRANSPORTS PARISIENS | Unicode accents and diacritics | Acceptance rules | Newly resolved: Accent-folded original names agree. |
| 11 | Boulangerie du Soleil | Semantic translations | Candidate generation/ranking | Unresolved: Bakery of the Sun does not establish Sunshine Bakery; requires independently approved identity/translation evidence. |
| 12 | PANADERÍA LA ESPERANZA | Unicode accents and diacritics | Acceptance rules | Newly resolved: Accent-folded original names agree. |
| 14 | Deutsche Maschinenfabrik | Semantic translations | Acceptance rules | Unresolved: Approved Machine Factory does not establish Machine Works; no semantic synonym invented. |
| 16 | ООО Северный Ветер | Transliteration | Candidate generation/ranking, then acceptance | Unresolved: Cyrillic romanization now ranks Severny Veter LLC first; romanization alone remains Low confidence and supplies no proposal. |
| 18 | Indústria Metalúrgica São Paulo | Unicode accents and diacritics | Acceptance rules | Newly resolved: Accent-folded original names agree. |
| 19 | Café de la Montaña | Unicode accents and diacritics | Acceptance rules | Newly resolved: Accent-folded original names agree. |
| 20 | 서울 미래 전자 | Transliteration | Acceptance rules | Unresolved: Saved Seoul Future Electronics differs from Source Seoul Mirae Electronics; no Korean transliteration or semantic identity asserted. |
| 24 | BLUEBIRD STUDIO | Singular/plural differences | Acceptance rules | Newly resolved: Explicit Studio/Studios equivalence. |
| 25 | Les Jardins de Provence | Word-order or token variations | Acceptance rules | Unresolved: Approved The Gardens of Provence differs by article; original also differs linguistically. Do not globally delete articles. |
| 27 | EAST COAST PHARMA | Abbreviations | Acceptance rules | Newly resolved: Controlled Pharma/Pharmaceuticals expansion. |
| 30 | Kilimanjaro Coffee Exporters | Singular/plural differences | Acceptance rules | Unresolved: Exporters and Exports are not simple singular/plural variants; no arbitrary stemming. |
| 31 | NOVA AUTO PARTS | Abbreviations | Acceptance rules | Unresolved: Auto can mean automotive or automatic; omitted from the controlled equivalence list. |
| 32 | Silver Oak Capital | Word-order or token variations | Acceptance rules | Unresolved: Additional Partners is meaningful; no deletion. |
| 33 | OCEAN VIEW HOTELS | Word-order or token variations | Acceptance rules | Unresolved: Additional Resorts is meaningful; no deletion. |
| 34 | Prairie Farm Supply Co | Singular/plural differences | Acceptance rules | Newly resolved: Explicit Supply/Supplies equivalence combined with Co./Company suffix handling. |
| 35 | MERCURY TELECOM | Abbreviations | Acceptance rules | Newly resolved: Controlled Telecom/Telecommunications expansion. |
| 37 | Horizon Edu Services | Abbreviations | Acceptance rules | Newly resolved: Controlled Edu/Education expansion. |
| 38 | TERRA VERDE ENERGIA | Company legal suffix variations | Acceptance rules | Newly resolved: Terminal SA legal form. |
| 39 | ALPINE MEDICAL DEVICES | Company legal suffix variations | Acceptance rules | Newly resolved: Terminal GmbH legal form. |
| 40 | Cedar Ridge Properties | Word-order or token variations | Acceptance rules | Unresolved: Properties/Property plus additional Group; Group cannot simply be deleted. |
| 41 | PACIFIC FRESH FOODS | Word-order or token variations | Acceptance rules | Unresolved: Food/Foods equivalence does not justify deleting Distribution. |
| 42 | BrightPath Learning | Word-order or token variations | Acceptance rules | Unresolved: Additional Center is meaningful; no deletion. |
| 45 | Emerald Coast Shipping | Company legal suffix variations | Acceptance rules | Newly resolved: Terminal Co. legal form. |
| 46 | ARCTIC WIND POWER | Ambiguous or genuinely different names | Acceptance rules | Unresolved: Power and Energy may describe distinct entities; no automatic synonym substitution. |
| 47 | Casa de Moda Bella | Semantic translations | Candidate generation/ranking | Unresolved: No approved English variant; requires optional translation workflow and explicit approval, without automatic API calls. |
| 48 | LUMIÈRE COSMÉTIQUES | Semantic translations | Acceptance rules | Unresolved: Accent folding alone cannot turn French Cosmétiques into English Cosmetics. |

## Newly resolved accounts and Source Segments

| Row | Master | Matched Source | Proposed Segment |
|---|---|---|---|
| 5 | sunrise retail co. | Sunrise Retail Company | Retail |
| 7 | MÜLLER MASCHINENBAU GMBH | Mueller Maschinenbau GmbH | Manufacturing |
| 9 | Compañía de Alimentos del Sur | Compania de Alimentos del Sur | Food & Beverage |
| 10 | SOCIÉTÉ DES TRANSPORTS PARISIENS | Societe des Transports Parisiens | Transportation |
| 12 | PANADERÍA LA ESPERANZA | Panaderia La Esperanza | Food & Beverage |
| 18 | Indústria Metalúrgica São Paulo | Industria Metalurgica Sao Paulo | Manufacturing |
| 19 | Café de la Montaña | Cafe de la Montana | Hospitality |
| 24 | BLUEBIRD STUDIO | Bluebird Studios | Media & Entertainment |
| 27 | EAST COAST PHARMA | East Coast Pharmaceuticals | Healthcare |
| 34 | Prairie Farm Supply Co | Prairie Farm Supplies Company | Agriculture |
| 35 | MERCURY TELECOM | Mercury Telecommunications | Telecommunications |
| 37 | Horizon Edu Services | Horizon Education Services | Education |
| 38 | TERRA VERDE ENERGIA | Terra Verde Energia SA | Energy |
| 39 | ALPINE MEDICAL DEVICES | Alpine Medical Devices GmbH | Healthcare |
| 45 | Emerald Coast Shipping | Emerald Coast Shipping Co. | Logistics |

## Approval and validation

All 50 result objects and the reopened Excel output have no decisions or final values. The 35 proposals still require explicit human review/approval; 15 remain unresolved. A valid existing Master value is preserved in Original Value, and a differing proposal is flagged as a conflict. No benchmark action updates a live workspace or a Master dataset.

Adversarial regression tests cover accent, umlaut, legal-form, abbreviation and plural collisions (both agreeing and conflicting Segments), close competitors, different geographic words and numbers, meaningful added words, word order, conflicting approved translations, Master-side collisions, exact-ID/name priority, unapproved translations, and Cyrillic ranking without acceptance. These tests demonstrate the specified guardrails, not universal absence of real-world false positives: two distinct companies can share a canonically equivalent name without stronger identifiers. Medium confidence and human review remain essential.

Artifacts: phase2-comparison.csv gives all 50 rows compared directly with Phase 1; comparison.csv and summary.json additionally retain the original Good Test.csv comparison; updated-results.xlsx is the fresh unapproved output. benchmark.py and analyze.py reproduce this local analysis from the repository root using the project Python. Production, paid APIs, commits and pushes were not touched.

Primary failure-category counts for the original 30 unresolved rows: legal suffixes 4; transliteration 3; Unicode accents 5; semantic translations 4; singular/plural differences 3; token variations 6; abbreviations 4; ambiguous/different names 1. These are exclusive primary labels; some rows need more than one transformation. Twenty-nine of the 41 originally unresolved Master Segments now have proposals (70.7%); six proposals agree with already valid Master values.

Final validation: 663 tests passed in the full tests/ suite, including Streamlit startup, with zero failures; 111 focused tests passed. Python compilation and git diff whitespace checks passed.
