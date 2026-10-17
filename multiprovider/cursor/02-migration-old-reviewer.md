# Migration notice: disable previous separate Cursor PR-review Automation

The v1 package supplied two Automations:
1. Scheduled `01-scheduled-implement.md` that made one PR.
2. Draft-PR-opened `02-pr-review.md` that reviewed that PR in a new run.

**v2 replaces both with ONE scheduled orchestration Automation:** `01-scheduled-implement.md` delegates one or more isolated `feature-builder` subagents, publishes Draft PRs, starts fresh `pr-reviewer` subagents and iterates up to three correction rounds per issue.

Before enabling v2:
- DISABLE or DELETE the old Cursor `Draft PR opened` review Automation. A second review runner on the same PR could race Jira transitions or post duplicate findings.
- REPLACE the v1 scheduled build Automation prompt with v2's full `cursor/01-scheduled-implement.md` body and select ONLY a daily Schedule trigger.
- Install both `.cursor/agents/*.md` files in the selected repository's default branch.
- Verify the `pr-reviewer` is a fresh separate subagent that really reads the published diff. If this environment does not support it, report BLOCKED; do not falsely claim independent review.

If you intentionally want a separate GitHub-event reviewer later for HUMAN COMMENTS, design a dedicated event workflow with explicit idempotency and PR-head checks, not a duplicate of this implementation review.
