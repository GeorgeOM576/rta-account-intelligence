# Reconciliation accuracy improvements

Local exact, normalized and configured alias matches receive High confidence. Unique company-name matches after removing terminal legal suffixes receive Medium confidence, as do approved translation matches. Fuzzy candidates, duplicate identifiers, conflicting duplicates and corporate relationships remain Low confidence and do not generate local proposals. Similarity scores remain ranking evidence rather than identity probabilities. Medium confidence proposals require individual review through the existing workflow.

Original Master values are preserved. A differing Source value is explicitly described as a conflict requiring reviewer approval; agreeing Source values remain reviewable under the existing workflow. Blank and existing unresolved placeholders accept valid Source values as proposals only. No matching step writes a final value or creates a reviewer decision.

Review shows local confidence, method and reason. Excel exports include those fields and now populate Proposed Segment from the effective proposal, rather than only the AI proposal. AI Proposed Value remains separate. Approved translation records continue to require current revision, matching original cell, Approved Translation status and no exclusion. Approved transliterations use this same path; automatic unapproved transliteration is not introduced. Original account strings and provenance remain intact.

Optional research retains its existing calls, authorization, caching and evidence validation. An insufficient or failed research attempt preserves a current local proposal while recording the separate AI research outcome. It does not grant approval eligibility to insufficient research.

## Validation and measurement

The requested original 50-account Master, Source and result files were not found. The user has been asked to supply them. No before/after accuracy or coverage claim is made for that benchmark. The pasted request ends at “Run the original benchmark through the existing engine”; any additional requirements beyond that line were not available.

The bundled samples/master.csv and samples/source.csv contain 10 rows each. An offline comparison with the HEAD version of Matcher produced 4 proposals and 0 finalized values both before and after. These are illustrative samples, not the original benchmark, and proposal counts do not establish correctness.

Deterministic regression fixtures cover the three requested multilingual pairs, approved versus draft translations, unresolved placeholders, suffix differences, ambiguity, conflicts, original values, individual approval, optional insufficient research and Excel output. No live paid APIs are used. Broader existing tests cover translation provenance, review, bulk eligibility and display configuration.

Validation result: 625 tests passed in the full tests/ suite, including the Streamlit startup smoke test (which requires permission to bind a local port outside the sandbox). After the final configured-alias precedence adjustment, 90 focused tests also passed. Python compilation and git diff whitespace checks passed.
