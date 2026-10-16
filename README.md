# Claude/Jira Agentic Factory — Daily v6

**Purpose:** evolve the already successful three-feature parallel Claude workflow without adding infrastructure. Two required changes over v5:

1. **Mandatory fail-closed dependency gate.** Every explicitly blocking Jira issue must have its **current `status.name` exactly `Done`**; otherwise Opus may not select, transition or dispatch the dependent issue.
2. **Authorized AGENTS.md edits by parent Opus.** After Sonnet implements and before the final PR review, Opus may edit an existing `AGENTS.md` in **that issue's worktree/branch only**, backed by the actual implementation. The edit belongs to the SAME Draft PR and is reviewed by the independent Opus reviewer and the human. Optional uncertain improvements stay proposals. No direct main edits.

The v6 package preserves the working batch model: one daily Claude Routine, up to three Sonnet feature builders in independent worktrees, one fresh Opus PR reviewer per published PR, at most three correction rounds, Jira/PR traceability and **human-only merge / Git conflict resolution**. This is ONE repository per Routine; multi-provider/multi-repo are future phases.

## Install (update existing Routine; do NOT create a second one)

| File | Destination | Change |
|---|---|---|
| `.claude/agents/feature-builder.md` | Existing repo at the same path, commit + push | Builder requires verified dependency-gate receipt; still cannot edit AGENTS.md. |
| `.claude/agents/pr-reviewer.md` | Existing repo at the same path, commit + push | Explicitly reviews AGENTS.md changes authored by parent Opus as part of the same PR; remains read-only. |
| `routines/01-jira-three-parallel.md` | **Entire Instructions field of your existing Claude Code Routine** | Includes full Opus contract and selection hard gate. |
| `reference/opus-contract-batch.md` | Reference only | Already embedded in Routine prompt; do not duplicate in each repo. |
| `reference/dependency-gate-examples.md` | Reference only | Examples to check Jira links and expected skip behavior. |

**No need to edit any existing AGENTS.md manually when installing**, and do not install cron, extra YAMLs, custom dispatchers, or VPS. Existing `AGENTS.md` content belongs to each product repo.

## Jira setup required

- Jira Ready candidates require `status = "Ready"`, label `agent-ready`, matching canonical `Repository: owner/repo`, technical spec/acceptance criteria approved and no existing open PR/active execution.
- Place blocking relationships in Jira **Linked issues → `is blocked by` / `depends on`**. For readability, mirror keys in a dedicated `Dependencies` section of the issue or a custom dependency field. For issues without blockers, prefer `Dependencies: None`.
- `Rank ASC` is the manual Kanban priority. Skip ineligible top-ranked issues; Opus can take the next eligible issue lower down. Do not require all three to be independent from one another if Jira blockers are not Done: the dependent one simply waits.
- **Only exact Jira `Done` counts**. A blocker still in Human Review, Resolved or AI Review disqualifies the candidate even if its PR is merged/passing. Do not use statusCategory=Done or resolution as substitutes for actual Done.
- `Blocks` default Jira semantics: `inwardIssue` with label `is blocked by` denotes a blocker; `outwardIssue` with label `blocks` denotes an issue blocked BY the current one. For `Depends`, `outwardIssue` with label `depends on` is a prerequisite. Jira link types can be customized: use actual inward/outward labels, never guess from the field name alone.
- The Jira MCP must be authorized to read FULL issue links and CURRENT status for every referenced blocker. A Jira JQL search by itself does NOT validate linked issues' statuses. If missing, the Routine skips a candidate rather than guessing.
- In Progress, AI Review, Human Review and Blocked must be valid transitions for the orchestrator. The current system does not automatically set Done upon merge.

## Examples

| Candidate | Declared blockers | Gate result |
|---|---|---|
| APP-101 | None, fully verified | Eligible if other gates pass |
| APP-102 | APP-80: Done | Eligible if other gates pass |
| APP-103 | APP-80: Done, APP-81: Human Review | **SKIP** (APP-81 is not Done) |
| APP-104 | APP-82: Resolved | **SKIP** (not exactly Done) |
| APP-105 | APP-83: issue detail not readable | **SKIP** (cannot verify) |
| APP-106 | APP-107: Ready, selected in the same batch | **SKIP** (not yet Done) |

The Routine leaves skipped issues in their previous Jira status (normally Ready), reports `DEPENDENCY_NOT_DONE` / `DEPENDENCY_UNVERIFIED` with blocker details, and continues down the ranked backlog until it finds at most three eligible issues.

## AGENTS.md editing policy

- Sonnet implements application code and supplies `AGENTS_MD_IMPACT_HINT`; the read-only reviewer audits what is in the actual PR.
- **Parent Opus may amend an existing root/nested AGENTS.md directly** when an already approved/implemented feature makes an instruction false or creates a durable new requirement future agents need. Edits must be minimal, factual and made only in the exact issue worktree/feature branch.
- Commit/push the changed AGENTS.md in the **same feature PR**. The reviewer independently audits both code and AGENTS.md; your GitHub human review still controls the merge.
- No new architectural policies, speculative rules or wholesale rewrites. Opus never edits other instruction or protected configuration files, secrets, or application source/tests.
- For a well-grounded but not yet approved architectural convention, Opus leaves a textual `PROPOSED` comment rather than changing the policy. For no lasting change, `NONE` without noisy comments.
- AGENTS.md changed in two parallel feature PRs may conflict after merge; those cross-feature Git conflicts remain **human-owned**.

## Schedule (Claude UI)

1. Go to https://claude.ai/code/routines, **Edit** the working Routine and paste the COMPLETE v6 `routines/01-jira-three-parallel.md` instructions.
2. Keep Opus as main model and the current repo + Jira/GitHub connectors. Verify Jira issue-links/read permissions.
3. Set only one **Schedule → Daily** trigger, choose your desired local hour, and remove other triggers. Do not manually `Run now` on the same day as the scheduled invocation if you are enforcing strict once/day.
4. Commit + push the two agents before that run. Check three parallel subagent invocations, dependency skip log, Draft PRs, reviewer verdicts and any AGENTS.md edits in the feature PRs.

**Important:** this package edits prompts and agent files; it does NOT change the Routine schedule, Jira configuration, remote repo or stored issues itself. Current subscription usage constraints still apply. Post-run human PR feedback automation, Done-on-merge and daily main audit remain next roadmap steps.

## Validation included

- YAML frontmatter parse on both agents and retained Sonnet/Opus separation.
- Exact full-contract inclusion in Routine prompt.
- Static assertions on hard dependency gate, explicit Jira `Done`, skip rules and allowed AGENTS.md scope.
- Contract decision examples. Not an integration test of your live Jira/Claude permissions or actual daily trigger.

Jira API link interpretation: https://developer.atlassian.com/cloud/jira/platform/issue-linking-model/
Claude Routines: https://code.claude.com/docs/en/routines
