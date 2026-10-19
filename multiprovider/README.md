# Agentic Factory | Multi-provider v2 | Cursor orchestration parity pilot

Updated 2026-10-17. **v2 supersedes v1's split Cursor build/review Automations.** Claude nightly batch is already working and remains unchanged except the previously prepared STRICT ENGINE ROUTING prompt. OpenCode is included unchanged as a guarded pilot, not a production unattended service.

## What changes in v2?

The Cursor configuration is now **ONE cloud scheduled Automation** (orchestrator) backed by TWO committed custom Cursor subagents:

- `.cursor/agents/feature-builder.md` -> implement one approved issue only inside the git worktree the orchestrator assigned (absolute paths, toplevel verified first, never the parent checkout).
- `.cursor/agents/pr-reviewer.md` -> independently review a real published PR with a fresh context, no edits, from the authenticated diff file the orchestrator provides (no unauthenticated GitHub calls).
- `cursor/01-scheduled-implement.md` -> main orchestration prompt: select up to 3 Cursor issues, enforce Jira Done dependency gate, create and verify one git worktree per issue and spawn the builders in parallel (v3), verify, update AGENTS.md when justified, publish Draft PR, spawn reviewer, request up to 3 correction rounds, advance Jira to Human Review only on credible PASS.

**Do not install a Cursor orchestrator agent file in a product repo.** Its contract is in the Automation prompt, matching Claude architecture. Do not duplicate global spec in AGENTS.md. Existing Claude files remain unchanged.

## Product repo layout

```text
product-repo/
  AGENTS.md                         # existing, specific to repo
  .claude/agents/
    feature-builder.md              # keep Claude v6
    pr-reviewer.md                  # keep Claude v6
  .cursor/agents/
    feature-builder.md              # v2 Cursor contract
    pr-reviewer.md                  # v2 Cursor contract
  ... actual product code
```

Cursor docs prioritize `.cursor/agents` over equivalent `.claude/agents` files, which is why two Cursor-specific files matter here.

## Install / activate in order

1. **Jira router first.** Keep EXACTLY one label per Ready issue: `engine-claude`, `engine-cursor`, or `engine-opencode`, plus `agent-ready`, exact Repository and full approved spec. Every blocking dependency must be `Done`. See `jira/ROUTING.md`.
2. **Protect Claude.** Ensure Claude Ready issues carry `engine-claude` and that your existing Claude Routine uses `claude/01-jira-three-parallel-STRICT-ROUTING.md`. Do not change proven Claude feature-builder/pr-reviewer files.
3. **Commit only the two Cursor agent files** from `cursor/.cursor/agents/` into your product repo's `.cursor/agents/` and push. Leave `AGENTS.md` as-is.
4. **Cursor account entitlement:** verify that your Cursor plan actually enables Cloud Agents and Automations. Current docs put these capabilities on Premium and above; Cursor Plus does not provide them. Do not assume Grokbot access implies an Automation subscription. Billing is based on cloud agent usage.
5. **Cursor environment:** set up a working Cloud Agent environment for ONE repo; configure Jira MCP (full issue detail, issue link lookup, transition, comments), GitHub (actual diff, branch write, create Draft PR). Ensure tests run in the cloud. Configure minimum necessary secrets/permissions.
6. **Migration:** DISABLE the old v1 separate `Draft PR opened` reviewer Automation; use `cursor/02-migration-old-reviewer.md`. Reconfigure its v1 daily build Automation (do not create a duplicate) to the FULL v2 instructions in `cursor/01-scheduled-implement.md`. Schedule only daily.
7. **Manual pilot first:** test with exactly one `engine-cursor` issue, verify routing + dependency gate + real Draft PR + fresh independent review + Jira state. Read `cursor/TEST-MATRIX.md`.
8. **Parallel worktrees (v3):** the orchestrator creates `/tmp/<KEY>-wt` per issue from the frozen `origin/master` base, verifies it and dispatches up to 3 builders in parallel; this verification is the isolation proof. A failed worktree makes only that issue `CONFIG_BLOCKED`. No shared-checkout parallel writers. After changing `cursor/01-scheduled-implement.md`, paste it again into the Automation prompt.
9. **After pilot:** enable the daily schedule staggered from Claude, preferably while the two services cannot compete over the same issue (engine labels protect selection but are not distributed locks).

## Files outside Cursor

- `claude/01-jira-three-parallel-STRICT-ROUTING.md`: the full existing Claude prompt with multi-provider labels, strict Done gate and Opus-owned AGENTS.md edits (unchanged from v1).
- `contracts/PORTABLE-CONTRACT.md`: source-neutral policy; now supplemented for Cursor's single-automation review cycle.
- `jira/ROUTING.md`: Jira tagging convention and query templates (unchanged).
- `opencode/`: v1 guarded one-issue OpenCode Go pilot and CLI/GitHub Actions setup (unchanged). Not an unattended multi-issue system yet.

## Explicit limitations, not hidden functionality

- Isolation in Cursor v3 comes from git worktrees the orchestrator creates on the same VM, not from a platform sandbox: Cursor subagents share the parent's checkout by default. The builder contract requires absolute paths inside its worktree and the orchestrator checks the parent checkout stays clean; this is a behavioral requirement plus a verification, not an external hard lock. Parallel test runs share the VM (CPU, memory, ports).
- The `readonly: true` reviewer frontmatter and task instructions reduce editing permissions, but should not be confused with a hard sandbox for external Jira/GitHub tools. Disable reviewer's write tools through account permissions where possible and audit the first run.
- Cursor Cloud Agents / Automations are metered; verify current plan's access. OpenCode Go itself does not provide a cloud scheduler, so its GitHub Actions pilot remains disabled by default.
- This is not an automatic setup of live Jira/Cloud Agent/GitHub credentials. No PRs have been generated by this package alone. Do not claim success before a real run verifies it.
- Comments received from the HUMAN after the scheduled run, GitHub merge -> Jira Done and daily main audit are future workflows (same as Claude).

## Relevant official references

- Cursor Subagents: https://cursor.com/docs/subagents
- Cursor Cloud Agents: https://cursor.com/docs/cloud-agent
- Cursor Automations: https://cursor.com/docs/cloud-agent/automations
- Cursor Models/Pricing: https://cursor.com/docs/models-and-pricing
- Cursor Cloud Environment: https://cursor.com/docs/cloud-agent/setup
- Cursor Jira: https://cursor.com/docs/integrations/jira
- OpenCode GitHub Actions: https://opencode.ai/docs/github/
