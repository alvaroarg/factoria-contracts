# Claude Code: 3 features in parallel (v4)

Version tailored to **one manual Claude Code Routine launch**, processing **up to three approved Jira features in parallel**, with **one fresh Opus reviewer subagent per PR**. This is the multi-feature trial **before** building scheduling, feedback automation or multi-provider support.

## Where files go

| File | Destination |
|---|---|
| `.claude/agents/feature-builder.md` | **Copy to your repository** (replaces old builder) |
| `.claude/agents/pr-reviewer.md` | **Copy to your repository** (new reviewer) |
| `routines/01-jira-three-parallel.md` | **Paste its entire content into the existing Claude Routine's Instructions** |
| `reference/opus-contract-batch.md` | Reference copy of the main contract; **do not copy to repo**. It is already embedded in the Routine prompt. |

Keep each repository's own `AGENTS.md` unchanged. Do not copy GitHub Actions, a Python worker or `automation/` into the repo.

## Quick start

1. Commit + push the two `.claude/agents/*.md` files to the repo/branch that the Routine clones.
2. Open Claude Code Routines, select the same repository and Jira connection, choose **Opus** as the main model (if selectable).
3. Replace the Routine's entire instruction field with `routines/01-jira-three-parallel.md`; remove any old instruction saying **ONE issue** or referencing `automation/prompts/opus-contract.md`.
4. Leave the Routine **manual** for this first three-feature test. Check Jira: issues are Ready, marked `agent-ready`, have a detailed human-approved design, target this repository, and are correctly ordered via Rank.
5. Click **Run now**. No custom input is required; the prompt already requests up to three issues. Observe the transcript and verify parallel `feature-builder` calls, worktree paths, then Draft PRs and corresponding `pr-reviewer` calls.
6. Verify on GitHub/Jira: each issue has a different branch and Draft PR; the PR diffs exist and tests are truthful; Jira reports the correct statuses. Review and merge yourself later.

## Non-goals / limits

- This does **not** create schedules, GitHub webhooks or automation for handling human feedback after the Routine ends.
- This does **not** add multi-provider support or new Jira fields.
- This does **not** resolve cross-feature Git conflicts. The human owns merges and conflict resolution.
- Prompts are not atomic locks, security sandboxes or guaranteed performance constraints. Keep branch protection and limit credentials. Run just one batch per repository at a time.
- A `pr-reviewer` subagent is independent in **context** but not a separate cloud Routine/session. Its read-only Bash behavior is enforced by instruction rather than a shell-level allowlist.
- Cloud Routine quotas, tool permissions and the ability to retain/publish subagent worktrees are platform-dependent. If these operations are unavailable, expect a blocker instead of a completed PR. Three parallel Sonnet agents plus three Opus reviews may exhaust a Pro subscription's quota.
- Claude Code's native `AGENTS.md` behavior depends on runtime version/configuration; explicitly read the file from this Routine if needed.

## Up-to-date docs

- https://code.claude.com/docs/en/sub-agents
- https://code.claude.com/docs/en/routines
- https://code.claude.com/docs/en/memory
