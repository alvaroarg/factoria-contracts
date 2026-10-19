# Shared execution contract - Agentic Factory / v1

This is a semantic contract, not a claim that all vendors expose identical tools.
The human owns product architecture, issue approval, conflict resolution, and merges.

## Sources of truth
- Jira: approved functional/technical design, acceptance criteria, dependencies, target `owner/repo`, Rank, engine assignment, state.
- GitHub: code, branches, published PR diffs, tests/CI, merge state.
- Repository: root and applicable nested AGENTS.md, existing CLAUDE.md when relevant. Do not overwrite repository policies.

## Mandatory eligibility before any work
1. Work only in the environment's EXACT selected GitHub `owner/repo` and configured Jira board/project.
2. Search `Ready` + `agent-ready`, ordered `Rank ASC`. Read entire candidate details, not only search excerpts.
3. Require EXACTLY ONE routing label from `engine-claude`, `engine-cursor`, `engine-opencode`; its value MUST match this runner. Missing, conflicting, or unreadable labels -> SKIP. Other labels do not count.
4. Require human-approved detailed technical spec, verifiable acceptance criteria, explicit correct target repo, no missing architecture decisions, no active execution and no open PR for the same Jira key.
5. Enumerate all blocking dependencies via structured Jira links, dependency fields, and explicit textual blockers. Interpret link directions correctly: `A blocks B` does NOT mean B blocks A. Ambiguous semantics -> SKIP.
6. Fetch EACH blocker by exact key in Jira; `status.name` must be exactly `Done` (case/whitespace normalization only). NOT Human Review, Resolved, statusCategory Done or a merged PR. Missing/incomplete status or link data -> SKIP. No blockers is acceptable only if all dependency sources were inspected successfully.
   - **Localized status names:** Jira may return translated `status.name` values depending on the account language. Treat `Ready` and `Listo` as the same status, and `Done` and `Finalizada` as the same status, in every check of this contract (candidate selection, dependency gate and re-checks). Any other name is not `Ready`/`Done`.
7. Recheck the candidate's status, its route label and EVERY blocker immediately before transition to `In Progress`. Do not dispatch if a gate fails. Document skip; do not move skipped issues to Blocked.
8. One non-overlapping run per engine/repo; Jira status alone is not an atomic lease. Do not launch overlapping schedules for same engine/repo. Two engines cannot own the same issue when routing is exclusive.

## Workflow
- Claim eligible issue -> In Progress with verified transition and run identification.
- Implement only the original approved design, scoped to the target repo, in a dedicated branch/worktree or provider-isolated checkout. Multiple features may edit the same files in separate workspaces; Git integration conflicts belong to the human.
- Create every builder worktree/branch from `origin/master` (the repository's actual default branch) immediately after a fresh `git fetch`, never from a stale local branch or another feature branch, and record that base commit.
- Execute feasible prescribed tests, recording actual commands, exit codes and unrun checks. Never invent PASS.
- Parent orchestration agent MAY update EXISTING AGENTS.md files inside the feature branch when objectively necessary for durable, accurate project instructions. Record why and have changes reviewed. Do not invent new architecture/policies; do not modify main directly. Feature builders and reviewers do not edit instruction files.
- Publish one independent DRAFT PR against actual default branch. PR includes `Factory Engine: <claude|cursor|opencode>`, Jira issue URL, test evidence, acceptance mapping, documented AGENTS.md changes and human-review requirement.
- Independent review must read the real published PR diff and original Jira spec, including changes to AGENTS.md. If tool support cannot provide an independent reviewer, state this gap; never call self-review independent.
- Review failures -> corrections in the SAME branch/PR, within configured max 3 rounds; new independent review each round when available. `AI Review` during review; `Human Review` only after a real published PR, verified checks and reviewer PASS.
- No agent merges, rebases across feature branches, resolves conflicts between unrelated PRs, deploys, changes permissions/secrets or bypasses policy. User handles final PR approval/merge and Jira Done until sync is implemented.

## Batch safety
- At most 3 issues per batch. Parallel builders only in isolated workspaces the runner can verify: a provider-native isolated worktree/VM (Claude `isolation: worktree`) or, for Cursor, one git worktree per issue created and verified by the orchestrator before dispatch (that verification is the isolation proof). Never more than one writer in the same directory. A runner without such isolation (e.g. the OpenCode pilot) processes ONE issue per run.
- Never refill a batch after one feature completes.
- Do not use a passing implementation of an issue in the same batch to bypass the Jira Done dependency requirement.

## Required output per issue
`ISSUE`, `ENGINE`, `REPO`, `ROUTE_VERIFIED`, `DEPENDENCY_GATE` (Done blockers / no blockers / skipped), `BRANCH`, `PR_URL`, `TEST_COMMANDS_AND_RESULTS`, `REVIEW_VERDICT`, `AGENTS_MD_ACTION`, `JIRA_STATUS`, `NEXT_HUMAN_ACTION`.

Fail closed when required provider/Jira/GitHub/MCP permissions or actual code evidence are unavailable. No fake issue transitions, PRs or reviews.

## Cursor v2 operational addendum

Cursor uses ONE scheduled orchestration Automation (not two independent PR-trigger runs) plus repository subagents. It implements up to 3 eligible issues in parallel in the same invocation: before dispatch the orchestrator creates one git worktree per issue (`git worktree add /tmp/<KEY>-wt -b cursor/<KEY>-<slug> <BASE_COMMIT>` from the frozen `origin/master` after a fetch) and verifies it; that verification is the isolation proof. A worktree that cannot be created/verified makes only that issue `CONFIG_BLOCKED`; a dirty parent checkout after a builder makes the affected issue `BLOCKED`. A new read-only reviewer subagent inspects the published diff after every change; because the reviewer cannot make authenticated GitHub calls, the orchestrator fetches the published PR diff with authenticated git (`git fetch origin pull/<N>/head:pr-<N>` + `git diff <BASE_COMMIT>...pr-<N>`) and hands it over as a local file/text. Up to 3 corrections occur on the same branch/PR. AGENTS.md changes are owned by the parent orchestrator and reviewed before Jira Human Review. Separate v1 PR-event reviewer must be disabled. These are contracts, not guaranteed platform capabilities.
