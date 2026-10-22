# Organization-name draft eligibility investigation

> **Current Translate Selected behavior:** [Silent-submit fix](translate-selected-execution-fix.md) stabilizes the form identity. The button now remains clickable to explain empty/ineligible selections, and changed previews require fresh consent instead of dropping the click. This supersedes older disabled-button descriptions below.

## Finding

The removed checkbox is **not the cause of a disabled translation button in the
current redesigned page**. `rta/translation_ui.py` explicitly passes
`allow_names=True` to both `engine.plan()` and `engine.process()`. It never reads
the previous `names_<workspace>` checkbox session key. Before the backend change,
new mocked UI tests passed for Master, Source and All, using the real table row
checkboxes and an explicitly false obsolete session value.

A separate inconsistency existed: `TranslationEngine.plan()` and `.process()`
still defaulted `allow_names=False` for callers that omitted the argument. A new
backend regression test reproduced this: two detected foreign-language names
produced a zero-name batch. Both defaults are now `True`. An explicit backend
opt-out remains available for compatibility, but the page offers no such toggle.
This change aligns backend defaults with the already-enabled company-name UI;
it does not claim to fix an independently reproduced UI permission regression.

## Selected-row workflow investigation

The button depends on `preview['unique_texts']`, calculated from selected table
snapshots. Dataset/status filters alone do not select rows. With no rows selected,
the preview and button correctly remain empty/disabled. Eligible records must:

- Be selected, current workspace/upload/field records.
- Have Translation Needed or retryable Failed status.
- Have a supported non-English source language from detection or human confirmation.
- Be enabled fields and have no existing English draft.

Unknown/unsupported languages need confirmation. English names, existing review
drafts and approved translations are excluded. Low-confidence valid Google codes
remain eligible under the existing detection policy. No language-detection code
or threshold was changed.

Tests exercised individual checkbox selection for Master, Source and both datasets,
preview/button activation, refusal without paid consent, explicit confirmed
execution, SQLite draft persistence, no retransmission, and original data/approval
safeguards. No additional selected-row defect was reproduced.

A read-only inspection of `data/rta.sqlite3` found 33 saved workspaces. The most
recently created populated workspace had:

| Dataset | English / Not Required | Translation Needed | Translated — Review |
| --- | ---: | ---: | ---: |
| Master | 7 | 17 | 1 |
| Source | 170 | 72 | 0 |

There were **89 eligible unique untranslated names**, independent of the obsolete
name permission. The active browser workspace and its in-memory row selections
cannot be established from this SQLite snapshot. These counts do not identify the
active workspace or prove the cause of an earlier browser observation. No saved
workspace records were updated by this investigation.

## User verification

Restart Streamlit to load the updated engine, resume the intended workspace and
open Translation Intelligence. Filter Translation status to **Translation Needed**
and Dataset to **All**. Check desired rows or press **Select all visible rows**;
that button selects only the current page. Verify a nonzero selected-name preview,
authorize the displayed batch and click **Translate Selected**. Repeat selection
and fresh authorization for later batches. There is no organization-name permission
checkbox to enable.

Generated values must appear as **Translated — Review**. Review/approval remains a
separate action; original names and account Final Values remain unchanged. Existing
drafts should be reviewed rather than retransmitted. For unknown source languages,
confirm a supported source-language code before selecting translation.

## Validation and files changed

Before the change, the new targeted test module had **4 passes and 1 failure**:
only the backend-default eligibility assertion failed. The three UI scope cases
already passed without the former checkbox.

After the change: `.venv/bin/python -m pytest -q` — **449 passed in 81.05 seconds**,
including real Streamlit HTTP startup and application execution/import checks.
All Google responses were mocked. No live paid API calls were made.

Files changed in this follow-up:

- `rta/translation.py`: default name-draft eligibility to True in plan/process;
  document its independence from paid consent.
- `tests/test_organization_draft_defaults.py` (new): five regression cases covering
  default eligibility, Master/Source/All page execution, stale false widget state,
  explicit backend opt-out, paid consent and unapproved draft safeguards.
- `tests/test_translation.py`: make the existing explicit name-opt-out scenario
  pass False rather than relying on the retired default.
- `tests/test_translation_e2e.py`: assert names are included by the new backend default.
- `docs/organization-name-draft-permission.md` (this report).
- `docs/translation-workspace-ui.md`: link this investigation/default clarification.

No UI layout, detection implementation, authorization logic, reconciliation logic,
Final Value logic, dependencies or database schema were changed.
