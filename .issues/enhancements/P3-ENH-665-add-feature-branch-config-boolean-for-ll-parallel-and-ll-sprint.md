---
id: ENH-665
type: ENH
priority: P3
status: active
discovered_date: 2026-03-10
discovered_by: capture-issue
---

# ENH-665: Add Feature Branch Config Boolean for ll-parallel and ll-sprint

## Summary

Add a `use_feature_branches` boolean to `ll-config.json` (and `config-schema.json`) that controls whether `ll-parallel` and `ll-sprint` create and operate on feature branches per issue, defaulting to `False`.

## Current Behavior

`ll-parallel` and `ll-sprint` currently do not have a configurable option for feature branch creation. Branch behavior is hardcoded or not present.

## Expected Behavior

When `use_feature_branches: true` is set in `ll-config.json`, `ll-parallel` and `ll-sprint` create a dedicated feature branch per issue (e.g., `feature/FEAT-665-...`) before running the Claude session, and merge or PR from that branch. When `false` (default), current behavior is preserved.

## Motivation

Teams using `ll-parallel` and `ll-sprint` in real CI/CD workflows need each issue to land on its own branch for proper code review, PR creation, and traceability. The default of `false` ensures no breaking change for existing users.

## Success Metrics

- When `use_feature_branches: true`, each issue processed by `ll-parallel` and `ll-sprint` results in a dedicated branch (e.g., `feature/ENH-123-slug`) in the worktree
- When `use_feature_branches: false` (default), behavior is identical to the current implementation — no new branches created
- All existing `ll-parallel` and `ll-sprint` tests pass without modification

## Scope Boundaries

- **In scope**: Adding `use_feature_branches` boolean config option; reading it in `parallel.py` and `sprint.py`; creating the feature branch inside the worktree; documenting the new option
- **Out of scope**: Auto-creating PRs from feature branches (separate concern); merging feature branches back to main; branch naming customization beyond issue slug; changes to worktree cleanup logic

## Proposed Solution

1. Add `use_feature_branches` boolean to the `parallel` and `sprints` sections of `config-schema.json` with `default: false`.
2. Read the config value in `scripts/little_loops/parallel.py` and `scripts/little_loops/sprint.py` (or wherever worktree/branch setup occurs).
3. When `true`, derive a branch name from the issue ID/slug and create/checkout that branch inside the worktree before invoking the Claude session.
4. Document in `docs/` and update the config schema description.

## Integration Map

- `config-schema.json` — add property to `parallel` and `sprints` sections
- `scripts/little_loops/parallel.py` — read config, conditionally create feature branch in worktree
- `scripts/little_loops/sprint.py` — same wiring for sprint execution

## Implementation Steps

1. Add `use_feature_branches` boolean (default `false`) to `parallel` and `sprints` sections in `config-schema.json`
2. Locate worktree setup code in `ll-parallel` and `ll-sprint` Python scripts
3. After worktree checkout, if `use_feature_branches` is `true`, run `git checkout -b feature/<issue-slug>` inside the worktree
4. Pass the branch info through to any post-merge/PR logic
5. Add tests for the new config flag behavior
6. Update docs/reference and any relevant README sections

## Impact

- **Scope**: `config-schema.json`, `scripts/little_loops/parallel.py`, `scripts/little_loops/sprint.py`
- **Risk**: Low — default is `false`, no behavior change for existing users
- **Effort**: Medium — requires tracing worktree setup in two CLI tools

## API/Interface

```python
# ll-config.json
{
  "parallel": {
    "use_feature_branches": false  # new boolean
  },
  "sprints": {
    "use_feature_branches": false  # new boolean
  }
}
```

## Related Key Documentation

- `config-schema.json` — authoritative schema for all config options
- `docs/ARCHITECTURE.md` — system design overview

## Labels

enhancement, config, ll-parallel, ll-sprint

## Status

Active

## Session Log
- `/ll:capture-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eec31a4c-27c6-4b78-bafd-8496b3a68d4a.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/644cb258-98f9-4276-9d10-660523431e43.jsonl`


## Blocked By
- BUG-656
## Blocks
- FEAT-638
- ENH-507
- ENH-470
- ENH-459
- ENH-654
- ENH-497
- ENH-485
