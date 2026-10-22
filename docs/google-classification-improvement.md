# Google detection classification policy improvement

No new live API calls. The saved authorized 25-name results are replayed exactly; raw codes and confidence scores are unchanged. Chinese zh-CN is compared with expected Chinese zh. Müller GmbH and Élan are excluded from the 23 definitive cases.

| Metric | Before | After |
|---|---:|---:|
| Correct automatic language/routing | 16/23 (69.57%) | 19/23 (82.61%) |
| Foreign candidate precision | 100% (11/11) | 100% (14/14) |
| Foreign candidate recall | 68.75% (11/16) | 87.5% (14/16) |
| Incorrect foreign candidates among six English regression names | 0 | 0 |

After-policy definitive confusion counts: English → 5 English, 0 foreign, 2 manual; foreign → 0 English, 14 foreign, 2 manual. Raw Google accuracy remains 23/23 (100%). Automatic classification coverage is 19/23; all classified definitive cases are correct.

## Per-name replay

| Name | Google code | Confidence | Before | After |
|---|---|---:|---|---|
| HARBOR HEALTH | en | 0.966054 | English | English |
| Cedar Labs | en | 0.547146 | Manual review | Manual review |
| Summit Holdings | en | 0.928436 | English | English |
| Pioneer Data | en | 0.437176 | Manual review | Manual review |
| Orchard Systems | en | 1.000000 | English | English |
| Bluebird Studio | en | 0.926130 | English | English |
| Boulangerie du Soleil | fr | 0.780919 | Manual review | Manual review |
| Les Jardins de Provence | fr | 1.000000 | Foreign-language candidate | Foreign candidate |
| Société des Transports | fr | 0.989807 | Foreign-language candidate | Foreign candidate |
| Panadería La Esperanza | es | 1.000000 | Foreign-language candidate | Foreign candidate |
| Servicios de Construcción | es | 1.000000 | Foreign-language candidate | Foreign candidate |
| Distribuidora El Sol | es | 1.000000 | Foreign-language candidate | Foreign candidate |
| Deutsche Maschinenfabrik | de | 0.985569 | Manual review | Foreign candidate |
| Bäckerei am Markt | de | 0.958315 | Foreign-language candidate | Foreign candidate |
| Haus der Technik | de | 0.899333 | Manual review | Manual review |
| Tecnologia e Soluções | pt | 0.989459 | Foreign-language candidate | Foreign candidate |
| Comércio de Alimentos | pt | 0.926470 | Foreign-language candidate | Foreign candidate |
| Azienda Agricola Toscana | it | 0.987967 | Foreign-language candidate | Foreign candidate |
| Forno della Famiglia | it | 1.000000 | Foreign-language candidate | Foreign candidate |
| 株式会社さくら商事 | ja | 1.000000 | Manual review | Foreign candidate |
| 北京科技有限公司 | zh-CN | 1.000000 | Manual review | Foreign candidate |
| شركة النور للتجارة | ar | 0.977084 | Foreign-language candidate | Foreign candidate |
| Müller GmbH | de | 0.500305 | Manual review | Manual review |
| Élan | fr | 0.565217 | Manual review | Manual review |
| Global Tech Solutions | en | 0.965993 | English | English |

## Policy and cache changes

- Google code, confidence (minimum 0.90) and competing-result margin (minimum 0.20) remain primary signals. No company-name exceptions were added.
- Unicode letter scripts replace whitespace length assumptions for non-Latin names. Han plus kana is supported as Japanese; high-confidence Chinese, Japanese, Arabic and other supported scripts can classify without word-count gates. Explicit script/language conflicts and mixed scripts remain manual. Script checks are conservative, not an exhaustive linguistic detector.
- High-confidence longer Latin business phrases can classify with fewer than three words. Brief Latin account names with fewer than three words and fewer than twelve letters remain manual because proper-name context is limited. Legal suffixes and entirely shared business vocabulary remain review safeguards.
- Interpretation version is google-script-aware-v2. Raw Google response cache version stays unchanged: field interpretation keys change, existing raw responses remain reusable without paid calls. Existing records refresh against current interpretation on read or explicit cache refresh. No database deletion or global cache clearing.
- Approved translations, manual language corrections and audit history are protected; automatic metadata can be updated while human decisions remain authoritative.
- Original names remain unchanged. Non-English is a candidate label only. Account-name translation opt-in, explicit paid-batch consent, translation approval, reconciliation approval and Final Value safeguards remain unchanged. Workspace usage and cache isolation remain unchanged.

## Remaining manual review

Cedar Labs (0.547146), Pioneer Data (0.437176), Boulangerie du Soleil (0.780919), and Haus der Technik (0.899333) remain below 0.90 confidence. Müller GmbH and Élan remain appropriately ambiguous. The threshold was not lowered to fit this sample.

## Refresh instructions

Restart Streamlit to load the updated source. Open the workspace → Translation Intelligence → keep Google Cloud (primary) selected → Refresh from cached Google detections (no API calls). Existing raw detections are reused, human decisions remain protected. Uncached names stay pending; this refresh never makes Google requests. The standalone accuracy-test fixture is not injected into production workspace caches.

## Files changed

- rta/google_detection.py: Unicode scripts, revised classification rules, separate classification version.
- rta/translation.py: interpretation version in policy signatures and metadata.
- tests/test_google_classification.py: saved-response replay, multilingual scripts, conflicts and safe cache refresh tests.
- tests/fixtures/language_detection/google_live_25.json: unmodified copy of authorized saved live responses, provenance/build/time and prior metrics included; contains fictional names only.
- tests/fixtures/language_detection/google_live_25_comparison.json: reproducible offline before/after comparison.
- docs/google-classification-improvement.md: this report.
- docs/google-primary-detection.md: current policy description.

No dependency changes. Existing 68-case synthetic routing assertions remain unchanged; synthetic cases are not a measurement of real Google accuracy.

## Validation

- Focused Google policy/provider tests: **39 passed**.
- Complete regression suite: **367 passed, 0 failed, 0 errors in 65.33 seconds**.
- Includes Streamlit AppTest application execution and a real Streamlit server HTTP health check, plus existing reconciliation, six review filters, approval, export, usage, consent and workspace-isolation regressions.
- An initial sandbox run could not bind the startup-test localhost socket; its in-process UI runs also overlapped policy edits. The complete suite was rerun after all source changes, with localhost access, and passed cleanly. No assertions were deleted or weakened.
- New live Google requests during implementation/testing: **0**.
