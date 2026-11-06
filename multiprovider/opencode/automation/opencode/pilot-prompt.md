MANUAL SINGLE-ISSUE PILOT. You MUST be the named `factory-orchestrator` agent.
Process EXACTLY Jira key __ISSUE_KEY__ in repository __GITHUB_REPOSITORY__
(given by the human or selected deterministically by the runner; never pick another).
This invocation is exactly one issue. The workflow may start up to 3 such
invocations in parallel; do not pick or refill another issue.

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

Delegate source/test editing to feature-builder (DeepSeek V4.1 Flash) ONE TIME
for the initial implementation.
Give it relevant files, approved spec and instructions to EDIT within 10 steps.
Never launch a fresh replacement builder if the first produces no diff.
The external guard will stop the run if there is no source/test edit within
its initial deadline, or at the absolute timeout. Do not work around it.

Publish ONE Draft PR, then obtain an independent published-diff pr-reviewer
(Kimi K3.1 Pro) verdict on the current PR HEAD. On CHANGES_REQUESTED, resume
the SAME original builder session on the SAME branch and publish to the SAME
PR. Allow at most 3 correction cycles and at most 3 re-reviews after the
initial review (4 reviews total). Each correction is one resume of that same
session; each re-review is one fresh pr-reviewer on the new head. The initial
review is not a re-review. Do not start a fourth correction or a fourth
re-review. If the same session cannot be resumed, or a correction publishes no
update, leave the Draft PR and mark Blocked without another reviewer on the
unchanged head. Do not count a review of an older head as the current verdict.
On PASS at the current head with real passing tests,
comment with EXACT literal markers on the PR:
Factory Review: PASS
Factory Review Head: <CURRENT PR HEAD SHA>
Factory Reviewer: pr-reviewer
Then move Jira to Human Review. Otherwise leave AI Review or Blocked with
truthful reasons and no fabricated PASS. No merges/deploys.

No extra features, extra subagent types, batch refills, or a second initial
implementation. One guarded opencode run only; do not relaunch the story.
