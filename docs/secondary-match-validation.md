# RTA secondary match validation — independent 60-account challenge

## Result

Correct accepted matches and Segment proposals increase from 26 to 36. All 36 proposals are correct against the independent answer key. All ten deliberately unmatched accounts remain unmatched. No previously accepted match/proposal regresses. Nothing populates Final Value without a human decision.

| Measure | Before | After |
|---|---:|---:|
| Correct first candidates among 50 matchable accounts | 48/50 | 48/50 |
| Correct accepted matches | 26/50 | 36/50 |
| Correct Segment proposals | 26/26 | 36/36 |
| Proposal coverage among 50 matchable accounts | 52% | 72% |
| Proposal coverage across all 60 Master records | 43.3% | 60% |
| Proposal precision | 100% | 100% |
| False-positive accepted matches | 0 | 0 |
| Incorrect proposals | 0 | 0 |
| Deliberately unmatched accounts correctly left unmatched | 10/10 | 10/10 |
| Matchable accounts still unresolved | 24 | 14 |
| Correctly first-ranked but unresolved matchable accounts | 22 | 12 |
| All accounts without an accepted match or proposal, including deliberate nonmatches | 34 | 24 |
| Proposal reviews available | 26 | 36 |
| Human decisions still required | 60 | 60 |
| Final values populated by the engine | 0 | 0 |

This reduces the matchable-account investigation queue by ten (24 to 14), not the requirement for human approval. Raw CSV control, without any translations or research, improves from 24 to 33 correct matches/proposals; first candidates stay 45/50; coverage across all 60 increases from 40% to 55%, and coverage among the 50 matchable accounts increases from 48% to 66%. Precision remains 100%, with zero false positives and all ten nonmatches withheld.

## Inputs and benchmark boundaries

Used RTA_Phase2_Master_60.csv, RTA_Phase2_Source_60.csv, Another Test Phase 2.csv, and RTA_Phase2_Challenge_60x60_With_Answer_Key.xlsx. The workbook Master and Source sheets were checked against the CSVs. Unlike the original 50-row benchmark, scoring uses the explicit answer key, not positional Source row pairing. Each expected Source account and Segment was checked against the Source dataset. Answer-key data is loaded only after all reconciliation calls and is never supplied to production matching code.

The provided export is the reported “Before” baseline. An additional fresh pre-change local run was frozen before editing; it independently reproduced 26 proposals and 48 correct first candidates. Raw pre-change output was also frozen. Input and frozen-baseline SHA-256 hashes are in summary.json.

The same 11 values explicitly labeled Master Approved English Translation in the saved challenge export were reused. Approval audit records are not available in the export, so reconstructing these as approved-name inputs remains an explicit benchmark assumption; no new name, alias or translation was invented or approved.

Available research in the export is 51 Insufficient Evidence, 2 Failed, and 7 Not researched. The export contains summaries and URLs, not stored retrieved excerpts or structured research snapshots. Those original statuses/summaries/URLs were retained as context in the output, but none could positively confirm a new match. All ten new proposals come from deterministic uploaded-name/approved-name equivalence. No research, translation or paid API was called.

## Architecture and targeted changes

| Existing responsibility | Location/data |
|---|---|
| Candidate generation and blocked fuzzy ranking | rta/matching.py, Matcher.candidates |
| Original names, approved current-revision variants and provenance | rta/approved_names.py and rta/translation_matching.py |
| Ranked candidate Source row IDs, accounts, raw similarity and comparison values | Result.candidates; scores are not calibrated identity confidence |
| Saved research outcomes | Result.research_status, research_snapshot (finding, retrieved_evidence, source_context, approved_name_context), research history and explanatory fields |
| Grounded research validation | rta/recommendations.py and rta/relationships.py |
| New offline corroboration | rta/secondary_validation.py, SecondaryValidator |
| Source-backed suggestions | Result.proposed/local_proposed and new secondary_validation JSON metadata |
| Explicit review, final values and audit | rta/review.py and rta/storage.py |
| Configured table display and Excel export | rta/workflow_table.py and rta/export.py |

The secondary layer runs after existing matching and retained research/decisions are attached. It evaluates the first candidate for unresolved records against actual uploaded Source rows, including duplicate/competing records beyond the visible three. For an existing AI proposal pointing to a different supported Source, identity contradictions are checked against that actual proposed Source rather than an unrelated first fuzzy candidate.

Positive evidence can be a unique exact uploaded legal identifier, a unique bounded name/approved-name equivalent, an explicit workspace alias, or saved authoritative quoted same-identity evidence. Domains are parsed locally and can corroborate a name link; a website alone cannot establish identity. Uploaded registration, tax/VAT, company-ID, LEI/DUNS fields are considered; identifiers retain leading zeros and are compared only across same-named fields. Internal Master/Source account IDs may legitimately differ across systems and are not treated as legal-identity contradictions.

Name additions are a bounded, general vocabulary: Centre/Center; Svcs/Services; Labs/Laboratories; Agri/Agriculture; Property/Properties; Product/Products; Pharmaceutical/Pharmaceuticals; ampersand/“and”; and terminal KK or leading approved romanized OOO legal forms. Meaningful business qualifiers are retained. The rule does not infer Power/Energy, Systems/Solutions, hotel/semantic translations, or arbitrary business synonyms. No company pairs from the answer key appear in production logic.

Source/Master identifier or domain contradictions veto pending proposals, even with identical company names. Reused legal identifiers, multiple equivalent Source/Master records, and close competitors stay unresolved. A score gap below five points can veto name-only promotion; a large gap never creates evidence by itself. High secondary confidence requires a unique uploaded legal identifier; name-based promotions are Medium and retain individual review requirements. Existing primary matching rules still supply their original confidence labels. No aggregate 96% candidate accuracy is used as individual confidence.

Research reuse revalidates quoted structured findings against current Source/mapping and current approved-name context, using the existing grounding validators. For secondary confirmation, accepted source hosts must be an uploaded first-party domain or the bounded SEC/Companies House registry hosts. Parent ownership alone is not direct identity proof. Unsupported summaries, unrelated companies, absent quotes, untrusted sources, stale snapshots, failed research and Insufficient Evidence are never positive confirmation. Existing research proposals remain subject to their original evidence/approval checks; the secondary status does not grant them new authority merely because they already exist.

Research completion, failure and the existing no-API saved-evidence re-evaluation action invoke the offline callback using current attached data. Human-reviewed results are skipped entirely. New local corroboration can support a proposal even if AI research remains insufficient; that does not turn the AI finding into positive evidence or bypass its existing approval restrictions. Those records can still use the existing individual Manual review when an Insufficient Evidence restriction applies. Secondary proposals do not gain reliable-local bulk approval eligibility.

The application adds status/reason only in existing per-account review/research details. The configured workflow table columns are unchanged. Excel gains secondary status, confidence, reason and evidence fields. The matching signature version is bumped so older runs are marked stale until explicitly rerun; no database schema, secrets, authentication, provider configurations, consent, caching, cost controls or deployment changed.

## Every newly resolved account

| Master row (1-based data row) | Master | Actual linked Source | Proposed Segment | Reason |
|---|---|---|---|---|
| 9 | NOVA PHARMA DISTRIBUTION | Nova Pharmaceutical Distribution | Healthcare | Pharma expands to Pharmaceuticals; Pharmaceutical/Pharmaceuticals is a bounded inflection equivalent. |
| 11 | Oak & Stone Construction | Oak and Stone Construction | Construction | Ampersand and the explicit word “and” have the same connector; other tokens are retained. |
| 13 | TERRA NOVA AGRI CO. | Terra Nova Agriculture Company | Agriculture | Agri/Agriculture expansion plus terminal Co./Company legal-form handling. |
| 18 | Evergreen Learning Centre | Evergreen Learning Center | Education | Centre/Center orthographic spelling equivalent. |
| 19 | ARCTIC DATA LABS | Arctic Data Laboratories | Technology | Labs/Laboratories abbreviation equivalent. |
| 25 | Sakura Electronics KK | SAKURA ELECTRONICS | Electronics | Terminal KK legal form; the remaining uploaded company name matches uniquely. |
| 27 | Central City Property | Central City Properties | Real Estate | Property/Properties bounded inflection equivalent. |
| 29 | Pioneer Education Svcs | Pioneer Education Services | Education | Svcs/Services abbreviation equivalent. |
| 37 | Orchid Beauty Products | Orchid Beauty Product Co. | Consumer Goods | Product/Products bounded inflection plus terminal Co. handling. |
| 43 | ООО Восточный Свет | Vostochny Svet LLC | Energy | The already saved approved English name OOO Vostochny Svet differs from Vostochny Svet LLC only by legal forms. No new translation was generated or approved. |

## Remaining matchable accounts

| Row | Master | Expected Source | Why it remains unresolved |
|---|---|---|---|
| 15 | Maritime Exporters Group | Maritime Exports Group | Exporters/Exports is not a safe inflection identity rule. |
| 16 | BLUE HARBOR HOTELS | Blue Harbor Hotels & Resorts | Additional Resorts is a meaningful business qualifier. |
| 17 | SILVERLINE AUTO PARTS | Silverline Automotive Parts | Auto/Automotive is not automatically assumed. |
| 26 | GOLDEN OAK FINANCIAL | Golden Oak Financial Services | Additional Services is meaningful; competing Golden Oak entity also exists. |
| 31 | Kilimanjaro Coffee Traders | Kilimanjaro Coffee Trading | Traders/Trading is not a safe inflection identity rule. |
| 35 | Bright Future Solar | BrightFuture Solar Energy | Additional Energy is meaningful. |
| 40 | MOUNTAIN PEAK OUTDOORS | Mountain Peak Outdoor Gear | Outdoors/Outdoor Gear changes meaningful tokens. |
| 41 | JARDINS DU SOLEIL | Sun Gardens | No approved semantic equivalence to Sun Gardens; first suggestion remains wrong. |
| 42 | Casa del Mar Hotel | Seaside Hotel | No approved semantic equivalence to Seaside Hotel. |
| 44 | 東京未来商事 | Tokyo Mirai Trading | Approved Tokyo Mirai Shoji does not establish Tokyo Mirai Trading. |
| 47 | NORDIC WIND SYSTEMS | Nordic Wind Solutions | Systems/Solutions is not a safe identity synonym; a Technologies competitor exists. |
| 48 | Greenfield Medical | Greenfield Medical Supplies | Supplies and Research are competing entities with tied scores; first suggestion is wrong. |
| 49 | ALPHA CAPITAL | Alpha Capital Partners | Partners and Management compete; tied similarity cannot prove identity even though first is correct. |
| 50 | CITYLINE TRANSIT | Cityline Transportation | Transit/Transportation is not treated as established identity. |

## Candidate ties and regressions

There are no accepted-match or proposal regressions and no correct-first-candidate regressions against the provided saved export. The first suggestion for the deliberately unmatched OCEANIC BIOFUELS record changes between tied weak options; it remains unresolved.

A separate pre-change local snapshot had Greenfield Medical Supplies first for row 48 and Alpha Capital Management first for row 49, whereas the provided export had Research and Partners respectively. Both pre-change versions scored 48/50. This exposed hash/set-order-dependent ties. Ranking now sorts blocking keys deterministically, uses unweighted ratio to break equal weighted scores, then stable Source order. The new run matches the saved export's first choices for rows 48/49. Those rows remain unresolved. Identical complete result objects were verified in independent processes under PYTHONHASHSEED=1 and 99. The comparison CSV includes both saved and frozen-local first suggestions so this variation is visible rather than credited as an accuracy gain.

## Approval and validation

The full final test suite passes: **705 passed**, including Streamlit startup, configured display columns, translation/research mocks, review/audit workflows and Excel export. The focused secondary suite passes **42 tests**. New adversarial cases include similar distinct companies, conflicting legal identifiers/domains, reused identifiers, leading zeros, translation collisions, score ties, unsupported/hallucinated/unrelated research, untrusted URLs, stale evidence/records, existing decisions, retained originals, legacy raw finals, and research callbacks without provider calls.

All 60 updated result objects and the reopened Excel workbook have zero reviewer decisions and zero Final Values. All 36 proposed values exactly match the actual linked Source values and the answer key. Original Master Segments remain unchanged; conflicts are flagged for review. No human decision, final value or audit history was overwritten. No commit, push, deployment, paid research/translation or external write was performed.

Observed 100% precision is specific to this challenge and the adversarial fixtures; name equivalence alone cannot guarantee legal-entity identity in all future data. Medium confidence and explicit human review remain essential.

Artifacts are in /private/tmp/rta-secondary-validation/final: comparison.csv, summary.json, after-results.json and updated-results.xlsx. Frozen pre-change snapshots are in the parent directory. The reusable runner is scripts/benchmark_secondary_validation.py; its required path arguments keep datasets and answer keys outside production logic. It uses frozen before outputs for comparison rather than silently re-running the changed engine as a baseline.
