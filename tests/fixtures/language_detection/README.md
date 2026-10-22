# Manually labelled business language evaluation

`labelled_cases.json` contains 68 deliberately small, human-authored labels:
27 English values, 28 non-English values (French/Spanish/German), 8 inherently
ambiguous name/term cases, and 5 classification values that should be excluded.
The set includes the user's nine reported cases, unique names from both existing
fictional XLSX files, and additional business-name, shared-vocabulary, short-name,
description and free-text examples. Labels are semantic fixture annotations, not
outputs of a second language detector or Google.

`baseline_v1.json` freezes the actual original `detect_text` outputs, captured
before changing that implementation, using langdetect 1.0.9 with seed 0. The v1
implementation ignored field type. Do not regenerate this file using the updated
implementation. `evaluate.py` checks that baseline annotations match the labelled
set before comparing results, and produces `evaluation.json`.

Reproduce current results from the repository root:

```sh
PYTHONPATH=. .venv/bin/python tests/fixtures/language_detection/evaluate.py
.venv/bin/python -m pytest -q tests/test_language_detection.py
```

A positive is an automatic Translation Needed candidate. Precision counts genuine
foreign values among candidates; recall counts candidates among all 28 labelled
foreign values. Ambiguous abstentions are false negatives for a known foreign
label, not silently counted as English. Language-code correctness and English
coverage are reported separately. Non-English candidates from labels English,
ambiguous, or excluded count as false positives.

This is a small regression fixture containing the motivating examples, not an
independent held-out corpus or a production accuracy guarantee. No live Google
API calls are made. See `docs/language-detection-validation.md` for limitations.
