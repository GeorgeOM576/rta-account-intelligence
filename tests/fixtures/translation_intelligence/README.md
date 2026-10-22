# Fictional Translation Intelligence acceptance fixtures

Both XLSX files contain 12 invented businesses. No customer data or live services
are used. Account IDs differ between files; map **Account Name → Account Name**
and **Segment → Segment**, retaining Account ID as an uploaded identifier.
Master Segment is `Verify`; Source contains fictional segment classifications.
Trading Name duplicates Account Name to exercise persisted cache reuse without
creating duplicate business-account rows.

| Rows (Excel data rows, starting at 1) | Purpose |
| --- | --- |
| 1, 10 | English exact matches |
| 2–4 | French, Spanish, German Master names → English Source names |
| 5–7 | English Master names → French, Spanish, German Source names |
| 8 | French Master → Spanish Source, both approved to the same mocked English name |
| 9 | Spelling difference; a fuzzy suggestion requires human verification |
| 11 | Unmatched Master and Source businesses; do not assume correspondence |
| 12 | Exact French names in both datasets; shared draft cache, individual approval |

`expected.json` contains zero-based row expectations and deterministic mock
translations. The field-aware detector recognizes the English context in Azure
Harbor Research and Golden Meadow Systems. Cobalt Lantarn Supply (a typo) and
Unmatched Velvet Acorn Atelier remain ambiguous and are excluded from paid batches
until their language is explicitly confirmed. Classification fields such as
Segment are excluded by default. The separate labelled evaluation fixture lives
in `tests/fixtures/language_detection`.

Reproduce the inputs with `.venv/bin/python tests/fixtures/translation_intelligence/generate.py`.
Run the complete automated workflow with
`.venv/bin/python -m pytest -q tests/test_translation_e2e.py`.
The automated test injects file values at Streamlit's uploader boundary, since
AppTest does not provide browser file selection, then exercises the real import
button, XLSX parser and subsequent widgets. All Google requests are mocked.
