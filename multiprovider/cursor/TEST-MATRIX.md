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
| Worktree failure | `git worktree add` or its verification fails for one of the issues | That issue `CONFIG_BLOCKED`, no builder for it; the others continue |
| Parent checkout dirty | A builder wrote into the parent checkout (`git status --porcelain` not empty after it returns) | Affected issue `BLOCKED`, nothing published from the parent checkout |
| True parallel | Three eligible issues | 3 orchestrator-created, verified worktrees from the same `BASE_COMMIT`; 3 builders launched before first completion; 3 independent PRs + reviews; report `CONCURRENCY: PARALLEL` with the real count |
| Fewer than 3 | One or two eligible issues | Same flow with 1 or 2 worktrees/builders; real count reported |
| Private repo review | PR in a private repo, reviewer read-only | Orchestrator fetches `pull/<N>/head` with authenticated git and passes the diff file; reviewer verdict cites that `HEAD_COMMIT`, no 404 |
| Collision | A and B edit same path on separate branches | Both PRs kept; user owns conflicts |
| Run overlap | Previous Cursor run still active | Do not duplicate issue/PR; exit or skip with evidence |
| Final status | Review PASS on latest PR commit, tests successful | Human Review only; PR remains Draft, no Done/merge |

**Important:** Jira status updates and engine labels are application-level safeguards; they are NOT atomic distributed locks. Observe actual run logs. `BATCH_LIMIT=3`: isolation is proven in each run by the orchestrator creating and verifying one worktree per issue; check the run log for those verifications and for the parent-checkout `git status --porcelain` checks.
