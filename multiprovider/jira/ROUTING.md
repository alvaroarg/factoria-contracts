# Jira routing configuration - rollout contract

## Recommended current MVP: exactly one routing label
- `engine-claude`
- `engine-cursor`
- `engine-opencode`

These labels are mutually exclusive. A Ready issue must have EXACTLY ONE; unlabeled or multi-labeled issues must be skipped by EVERY engine. Do not preserve the single-provider default after enabling routing.

Keep `agent-ready` in addition to the routing label; neither label overrides `Ready` status, repo match, detailed design, or blocker gate.

A future Jira single-select field `Implementation Engine` can replace the engine label if and only if ALL providers switch over atomically; don't silently mix rules. Prefer labels for the first rollout to avoid configuration friction.

Sample candidate JQLs (substitute real project key):

```jql
project = APP AND status = "Ready" AND labels = "agent-ready" AND labels = "engine-claude" ORDER BY Rank ASC
```
```jql
project = APP AND status = "Ready" AND labels = "agent-ready" AND labels = "engine-cursor" ORDER BY Rank ASC
```
```jql
project = APP AND status = "Ready" AND labels = "agent-ready" AND labels = "engine-opencode" ORDER BY Rank ASC
```

JQL is the INITIAL filter only. Fetch all labels and issues for the exact repo; reject another engine label even if the JQL matched. Always run the per-blocker exact Done gate against latest Jira detail, twice.

Issue template:

```text
Repository: OWNER/REPO
Dependencies: None | PROJ-123, PROJ-125
Design approved: Yes (by human)
Technical design: ...
Acceptance criteria: ...
Testing: ...
```

Before switching on multiprovider:
1. Add engine-claude to ALL remaining Claude-eligible Ready issues you want Claude to pick up.
2. Deploy strict routing prompt in existing Claude Routine. Verify one NO_WORK for an unlabeled issue and one eligible labeled test issue, without letting an unintended task run.
3. Only then label an issue engine-cursor or engine-opencode and activate that provider's own run.
4. Use separate non-overlapping run schedules per engine+repo. Jira In Progress is not an atomic lock.
5. Keep Jira Done manual after GitHub merges until a separate sync is delivered; otherwise dependent issues cannot start (by design).
