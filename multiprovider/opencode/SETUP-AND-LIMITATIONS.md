# OpenCode Go: setup and launch constraints

Official docs: https://opencode.ai/docs/github/ and https://opencode.ai/docs/go/

OpenCode Go is a model SUBSCRIPTION/PROVIDER, NOT a hosted job scheduler. Use official GitHub Actions integration to run without a local computer. The v3 workflow processes up to 3 issues per run, each in its own GitHub-hosted job (not shared worktrees). Parallel worktree/subagent isolation inside one OpenCode process is NOT assumed to match Claude Code.

## Auth blocker that must be cleared before enabling
1. Verify actual OpenCode Go CLI model names and your plan allowance. Model IDs: `opencode-go/kimi-k3.1-pro` orchestrator/reviewer, `opencode-go/deepseek-v4.1-flash` builder. Model availability/quotas change.
2. Verify the official OpenCode GitHub Action can authenticate your Go provider on an ephemeral runner. Env key placement can vary with OpenCode versions. Do not assume the sample `OPENCODE_GO_API_KEY` is automatically consumed. Do not commit secrets or `auth.json`.
3. Verify Jira's MCP can authenticate NONINTERACTIVELY in that runner and expose read issue links, individual blocker status, update issue status, and comments. OAuth login performed once locally does not automatically authenticate a new CI runner. If headless auth is not supportable, DO NOT enable scheduled unattended mode.
4. Install OpenCode official GitHub integration / GitHub App when appropriate, or use `use_github_token: true` as in provided pilot. Check repo branch protection and PR permissions.
5. Copy `.opencode/agents/*.md` to the desired repo; do not remove existing AGENTS.md/Claude agents. Add the shared contract where orchestrator can read it (copy contracts/PORTABLE-CONTRACT.md to repo or inline the hard rules in orchestration prompt; hard rules are already in agent file).
6. Save the pilot workflow as `.github/workflows/opencode-factory.yml`; set GitHub repository variable ENABLE_OPENCODE_FACTORY_PILOT=true only when BOTH auth paths are verified. Run `workflow_dispatch` to test ONE engine-opencode issue. The v3 workflow also has a daily schedule (see below); do not add a second one.
7. The v3 workflow already runs up to 3 isolated jobs (`max-parallel: 3`, `fail-fast: false`), each from a fresh `origin/master`. Prove one real PR + independent review + Jira transition before leaving a schedule unattended. The daily schedule is already `cron: '0 23 * * *'` (00:00 Europe/Madrid en invierno, CET; en verano, CEST, sería `'0 22 * * *'`). Do not add a second one.

## Limitation / security
- The sample workflow is disabled by default and is NOT deployment-ready until Go and Jira auth are verified. Its generic env injection is intentionally a placeholder requiring adaptation; the GitHub action may need additional provider configuration.
- Give Jira the minimal project/issue permissions and GitHub write access only to PRs/branches. Do not grant merging or deployment rights.
- GitHub Actions cron is UTC and can be delayed. This factory uses `cron: '0 23 * * *'` so the run is 00:00 Europe/Madrid in winter (CET); in summer (CEST) that hour would be `'0 22 * * *'`. Do not add another schedule that races Claude/Cursor's windows.
- No user comments to PRs are automatically handled by this pilot; that is intentionally a later phase.

## Pilot update (steps 6 and 7)

- `opencode-connectivity.yml` (save as `.github/workflows/opencode-connectivity.yml`): manual connectivity test. Its last step, `Read Jira using Kimi K3.1 Pro (READ ONLY)`, checks that Kimi really calls `jira_search` and `jira_get_issue` via MCP with `READ_ONLY_MODE=true`. Do not enable the pilot until this step proves real MCP calls.
- `opencode-factory-PILOT.yml`: manual-only (`workflow_dispatch`), gated by `ENABLE_OPENCODE_FACTORY_PILOT`. Optional `issue_key` input: with a key it processes exactly that issue; empty means autonomous selection of the first eligible `Ready`/`Listo` + `agent-ready` + ONLY `engine-opencode` issue by `Rank ASC`, with every blocker `Done`/`Finalizada`, batch limit 1, or `NO_WORK` without changes.
- `pr-reviewer.md` allows only read commands (`gh pr view`, `gh pr diff`, `git diff`, `git status`) so it can inspect the published PR diff. This is not credential isolation; prefer a read-only token or GitHub MCP for production.
- Repository setting needed: Actions → General → Workflow permissions → allow GitHub Actions to create pull requests. The contract still forbids merging.

## Factoría v3 (17/10/2026) — supersedes the pilot above

- Engine for up to 3 issues per run: see `V3-README.md`, `MIGRACION.md` and `PRUEBAS-Y-ARRANQUE-LIMPIO.md`. Job `select` (no LLM) preflights models and picks up to 3 Listo + `engine-opencode` stories by Rank, blockers in Finalizada, no existing branch/PR. Job `factory` is a matrix (`max-parallel: 3`, `fail-fast: false`) with the same per-story caps and a branch from a fresh `origin/master`. `issue_key` forces that one story; no eligible story is `NO_WORK` and a green run. Models: orchestrator **Kimi K3.1 Pro** (`opencode-go/kimi-k3.1-pro`), builder **DeepSeek V4.1 Flash** (`opencode-go/deepseek-v4.1-flash`), reviewer **Kimi K3.1 Pro**. CLI pin: `OPENCODE_VERSION: 1.19.4` (not `@latest`) in the factory, pilot and connectivity workflows. `check_config.py` retries `opencode models opencode-go` up to 3 times, 60 s apart, and names every missing model without substituting. Daily run: `cron: '0 23 * * *'` (00:00 Europe/Madrid en invierno, CET; en verano, CEST, sería `'0 22 * * *'`). The previous Kimi K3 had a lower Go quota than Kimi K2.7 Code (about $15 vs $60 of monthly Go usage); that figure is not a quota for Kimi K3.1 Pro.
- `.github/workflows/opencode-factory.yml` (v3, `mode=inspect|build`, optional `issue_key` with deterministic no-LLM selection, no new GitHub Variables required) **supersedes `opencode-factory-PILOT.yml`**. The old file is kept only because nothing is deleted without Álvaro's explicit order; he may delete it. Never install both in a product repo.
- Board equivalences kept: Ready = Listo, Done = Finalizada (`jira_gate.py` accepts both). Feature branches come from a fresh fetch of `origin/master`.
- The model IDs above replace the older `glm-5.3` suggestion in "Auth blocker" step 1.
