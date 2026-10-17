MANUAL SINGLE-ISSUE PILOT. You MUST be the named `factory-orchestrator` agent.
Process EXACTLY Jira key __ISSUE_KEY__ in repository __GITHUB_REPOSITORY__
(given by the human or selected deterministically by the runner; never pick another).

Use your project .opencode/agents/factory-orchestrator.md contract. The runner
has independently validated the issue and created the feature branch.
Independently recheck Jira approved spec, agent-ready, engine-opencode, repo,
Ready status, links and live status of every blocker. Any blocker other than
Done/Finalizada means SKIP WITHOUT CLAIMING IT. A story that declares no
Repository/Repositorio targets __GITHUB_REPOSITORY__; one naming another repo is ineligible.
**Localized status names:** Jira may return translated `status.name` values depending on the account language. Treat `Ready` and `Listo` as the same status, and `Done` and `Finalizada` as the same status, in every check of this contract (candidate selection, dependency gate and re-checks). Any other name is not `Ready`/`Done`.
The feature branch must come from a FRESH fetch of
origin/master (git fetch origin master; branch from origin/master), never from
a stale local master or another branch; verify the runner's base SHA.

Delegate source/test editing to feature-builder (DeepSeek V4 Pro) ONE TIME.
Give it relevant files, approved spec and instructions to EDIT within 10 steps.
Never launch a fresh replacement builder if the first produces no diff.
The external guard will stop the run if there is no source/test edit within
its initial deadline, or at the absolute timeout. Do not work around it.

Publish ONE Draft PR, then obtain one independent published-diff pr-reviewer
(Kimi K3) verdict. On PASS at current head with real passing tests,
comment with EXACT literal markers on the PR:
Factory Review: PASS
Factory Review Head: <CURRENT PR HEAD SHA>
Factory Reviewer: pr-reviewer
Then move Jira to Human Review. Otherwise leave AI Review or Blocked with
truthful reasons and no fabricated PASS. No merges/deploys.

No extra features, subagents, batch refills or automatic re-attempts.
