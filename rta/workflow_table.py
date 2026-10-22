"""Display-only workflow schema from the user-approved Windows-1252 CSV header.

Source: Run Reconcillation (Updated)(in).csv. No customer rows are bundled.
Exports and backend result projections deliberately do not use this schema.
"""

COLUMNS = (
    'Master Identifier',
    'Master Approved English Translation',
    'Matched Source Original Name',
    'Master Original Value',
    'Proposed Value',
    'Final Value',
    'Match Status',
    'Review Status',
    'Suggested Account 1',
    'Similarity Score 1',
    'Suggested Value 1',
    'Suggested Account 2',
    'Similarity Score 2',
    'Suggested Value 2',
    'Suggested Account 3',
    'Similarity Score 3',
    'Suggested Value 3',
    'Research Status',
    'Research Explanation',
    'Evidence URL 1',
    'Evidence URL 2',
    'Reviewer Decision',
    'Reviewer Notes',
    'Reviewer',
    'Reviewed At',
    'Value Origin',
    'Record ID',
    'Parent Company',
    'AI Proposed Value',
    'AI Confidence',
    'AI Recommendation Status',
)

# The CSV label differs from the existing comparison-value field, not the account name.
ALIASES = {'Master Original Value': 'Original Value'}


def visible_table(rows):
    """Build a separate, exact-schema render payload without mutating backend rows."""
    rows = list(rows)
    return {column: [row.get(column, row.get(ALIASES.get(column), '')) for row in rows]
            for column in COLUMNS}
