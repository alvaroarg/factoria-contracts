# Cursor v2 acceptance tests (manual Run / controlled Jira tickets)

Do not activate the daily schedule until the first small controlled test has passed. Do not test by allowing Claude and Cursor to claim the same issue.

| Test | Arrange in Jira / GitHub | Expected |
| --- | --- | --- |
| Routing absent | Ready + agent-ready, no engine label | SKIP, no Jira transition or PR |
| Routing conflicted | Ready with engine-cursor AND engine-claude | SKIP |
| Other provider | Ready with engine-opencode | SKIP |
| Repo mismatch | Ready engine-cursor, different Repository | SKIP |
| Blocker open | A is Ready, depends on B in Human Review | SKIP A, leave Ready |
| Blocker exact Done | A depends on B with current status.name Done | A eligible if remaining gates pass |
| Two blockers | B Done, C In Progress | SKIP A |
| Link direction | Candidate A blocks B, but has no blockers itself | Does NOT treat B as prerequisite |
| Missing blocker data | Jira lacks access to blocker key or link direction | SKIP (fail closed) |
| Only one valid issue | One fully eligible issue | One isolated builder, published Draft PR, independent review |
| Independent reviewer | PR exists and contains real published diff | Fresh pr-reviewer returns verdict referencing real diff/commit |
| Review fixes | Reviewer requests specific source changes | Original builder/branch, same PR, new fresh reviewer, <=3 rounds |
| AGENTS.md | Durable repo convention changed | Parent orchestrator edits existing AGENTS.md in SAME PR and reviewer reviews it |
| Shared checkout | Cloud Automation cannot isolate parallel writable subagents | BATCH_LIMIT=1, report PARALLELISM_UNVERIFIED |
| True parallel | Three eligible, isolated copies + publication/resume confirmed | 3 builders launched before first completion; 3 independent PRs + reviews |
| Collision | A and B edit same path on separate branches | Both PRs kept; user owns conflicts |
| Run overlap | Previous Cursor run still active | Do not duplicate issue/PR; exit or skip with evidence |
| Final status | Review PASS on latest PR commit, tests successful | Human Review only; PR remains Draft, no Done/merge |

**Important:** Jira status updates and engine labels are application-level safeguards; they are NOT atomic distributed locks. Observe actual run logs. Start `BATCH_LIMIT=1` until Cloud Automation isolation and reviewer support are verified, then enable 3 by proof, not assumption.
