# Legacy automatic final values

The former matcher copied matching Original and Proposed values into Final and
marked the row `Verified unchanged`. The model and decision code also inferred
`verified_original` from local matching. These were matching outcomes, not human
approval decisions. New reconciliation no longer performs those assignments.

A read-only inventory of `data/rta.sqlite3` on October 21, 2026 found 18
workspaces containing 125 result records. Seven records had stored Final values
without a saved decision; all seven matched the legacy automatic-final pattern.
No data, decisions, audit events, or workspace credentials were changed during
this inventory. These counts are a snapshot, not a migration command.

The application retains legacy raw Final values in SQLite, flags recognized
automatic finals in review and Excel, and excludes unapproved values from the
displayed/exported Final Value. Matching provenance, Original, Proposed, and
historical stored review status remain available. A raw Approved label alone
does not fabricate an approval decision.

To resolve legacy records safely:

1. Back up the workspace database before any planned data migration.
2. Review each flagged account, its proposal, Source identity, and evidence.
3. Explicitly save Approve or Manual through the existing individual review, or
   use confirmed bulk approval where every account passes its eligibility checks.
   These actions save the current reviewer and timestamp and append a real audit
   event, including the prior raw Final value.
4. Preserve existing saved decisions and audit history. Where a historical status
   lacks a decision, investigate the original audit evidence rather than inferring
   approval from similarity, matching confidence, a timestamp, or a status label.

No automatic migration or deletion is performed. Rejection continues to retain
an existing explicitly verified original where applicable. A new local match
does not create such verification; returning an account to Pending clears its
newly saved Final value.
