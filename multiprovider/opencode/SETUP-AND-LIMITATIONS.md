# OpenCode Go: setup and launch constraints

Official docs: https://opencode.ai/docs/github/ and https://opencode.ai/docs/go/

OpenCode Go is a model SUBSCRIPTION/PROVIDER, NOT a hosted job scheduler. Use official GitHub Actions integration to run without a local computer. This first pilot processes ONE issue, not three. Parallel worktree/subagent isolation in OpenCode is NOT assumed to match Claude Code.

## Auth blocker that must be cleared before enabling
1. Verify actual OpenCode Go CLI model names and your plan allowance. Model IDs suggested: `opencode-go/kimi-k3` orchestrator/reviewer, `opencode-go/glm-5.3` builder. Model availability/quotas change.
2. Verify the official OpenCode GitHub Action can authenticate your Go provider on an ephemeral runner. Env key placement can vary with OpenCode versions. Do not assume the sample `OPENCODE_GO_API_KEY` is automatically consumed. Do not commit secrets or `auth.json`.
3. Verify Jira's MCP can authenticate NONINTERACTIVELY in that runner and expose read issue links, individual blocker status, update issue status, and comments. OAuth login performed once locally does not automatically authenticate a new CI runner. If headless auth is not supportable, DO NOT enable scheduled unattended mode.
4. Install OpenCode official GitHub integration / GitHub App when appropriate, or use `use_github_token: true` as in provided pilot. Check repo branch protection and PR permissions.
5. Copy `.opencode/agents/*.md` to the desired repo; do not remove existing AGENTS.md/Claude agents. Add the shared contract where orchestrator can read it (copy contracts/PORTABLE-CONTRACT.md to repo or inline the hard rules in orchestration prompt; hard rules are already in agent file).
6. Save the pilot workflow as `.github/workflows/opencode-factory.yml`; set GitHub repository variable ENABLE_OPENCODE_FACTORY_PILOT=true only when BOTH auth paths are verified. Run `workflow_dispatch` to test ONE engine-opencode issue. No automated scheduling yet.
7. After one real PR + independent review + Jira transition are proven, consider enabling `schedule` in that workflow and only then move from single-issue to isolated concurrent workers.

## Limitation / security
- The sample workflow is disabled by default and is NOT deployment-ready until Go and Jira auth are verified. Its generic env injection is intentionally a placeholder requiring adaptation; the GitHub action may need additional provider configuration.
- Give Jira the minimal project/issue permissions and GitHub write access only to PRs/branches. Do not grant merging or deployment rights.
- Workflow schedules are usually UTC and can be delayed; do not schedule it to race Claude/Cursor's windows.
- No user comments to PRs are automatically handled by this pilot; that is intentionally a later phase.
