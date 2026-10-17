# Agentic Factory - Multi-provider rollout v1 (2026-10-17)

## Start from a proven baseline
Your Claude v6 already completed an unattended nighttime batch. Do not rewrite its workers or scheduling. Multiprovider should be incremental, with Jira as the COMMON control plane and GitHub as the code source of truth.

## Routing: the one mandatory cross-provider change
Adopt EXACTLY ONE Jira label on each Ready issue: `engine-claude`, `engine-cursor`, `engine-opencode`. Keep `agent-ready`, full approved technical design, repository `owner/repo`, and the strict blockers-must-be-exactly-Done rule. See jira/ROUTING.md. Deploy Claude strict routing FIRST; otherwise Claude's single-provider fallback might pick unlabeled work.

## What is inside
- `contracts/PORTABLE-CONTRACT.md`: shared semantic contract, including strict Done dependency gate, routing, PRs, human-owned merges, and AGENTS.md edits only in feature branches.
- `jira/ROUTING.md`: labels, rollout safety, JQL for all three engines.
- `claude/01-jira-three-parallel-STRICT-ROUTING.md`: FULL Claude Routine prompt derived from v6 with only the routing admission rule tightened. Does not replace Claude agent files.
- `cursor/01-scheduled-implement.md`: cloud native Cursor Automation instructions for one issue per run; Cursor will create a Draft PR and transition to AI Review.
- `cursor/02-pr-review.md`: separate independent Cursor Automation on Draft PR opened; only PRs marked Factory Engine: cursor; PASS -> Human Review.
- `opencode/.opencode/agents/`: initial Kimi K3 orchestrator and reviewer, GLM-5.3 builder. One issue per job until isolated parallel runs are verified.
- `opencode/.github/workflows/opencode-factory-PILOT.yml`: OFF by default manually triggered official GitHub Action skeleton, NOT silently scheduled.
- `opencode/SETUP-AND-LIMITATIONS.md`: provider Go and headless Jira auth blockers to resolve.

## Recommended rollout order
1. Ensure remaining Claude Ready tasks explicitly carry engine-claude. Paste updated FULL Claude Routine prompt, leave existing worker files untouched. Test NO_WORK for unassigned issues.
2. In Cursor Automations, create a single-repo implementation Automation with Jira MCP + PR tool, manually test a Ready engine-cursor issue with no blockers, then a deliberately blocked one. Separately create PR reviewer triggered only for Cursor Draft PRs. Confirm billing/permissions.
3. In OpenCode Go, verify models and run CLI locally (not claiming this is unattended), then solve secure NONINTERACTIVE Go/Jira auth for GitHub Actions. Pilot one engine-opencode issue manually with `workflow_dispatch`. Only activate schedule after success.
4. Add second repository by cloning provider-specific contracts and retaining each repository's own AGENTS.md; always filter both engine and owner/repo.
5. DO NOT automate GitHub merge, post-Routine human comments or Jira Done in this phase. Keep Done manual after merge; blocked dependent work needs that Done state.

## Provider-specific caveats
- Cursor Automations offer native scheduling, MCP tools and PR support, but billing/plan access is separate and provider cloud models are not guaranteed to have Claude-style three independent worktrees in one run.
- OpenCode Go supplies models and subscription allowance, not the cloud runner. Official GitHub Action requires credentials; Jira MCP interactive OAuth from a laptop does not solve headless CI authentication. The pilot is intentionally gated.
- `AGENTS.md` remains the universal repo-specific architecture source. Opus is allowed to edit it inside the PR according to Claude v6; other orchestrators obey the same semantic permission, never main.

Official references:
- Cursor Automations: https://cursor.com/docs/cloud-agent/automations
- Cursor AGENTS.md: https://cursor.com/docs/rules
- OpenCode GitHub Action: https://opencode.ai/docs/github/
- OpenCode agent syntax: https://opencode.ai/docs/agents/
- OpenCode Go: https://opencode.ai/docs/go/
- OpenCode MCP: https://opencode.ai/docs/mcp-servers/
