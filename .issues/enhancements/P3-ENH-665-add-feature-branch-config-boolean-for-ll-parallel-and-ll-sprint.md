---
id: ENH-665
type: ENH
priority: P3
status: active
discovered_date: 2026-03-10
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 72
---

# ENH-665: Add Feature Branch Config Boolean for ll-parallel and ll-sprint

## Summary

Add a `use_feature_branches` boolean to `ll-config.json` (and `config-schema.json`) that controls whether `ll-parallel` and `ll-sprint` create and operate on feature branches per issue, defaulting to `False`.

## Current Behavior

`ll-parallel` and `ll-sprint` currently do not have a configurable option for feature branch creation. Branch behavior is hardcoded or not present.

## Expected Behavior

When `use_feature_branches: true` is set in `ll-config.json`, `ll-parallel` and `ll-sprint` create a dedicated feature branch per issue (e.g., `feature/ENH-665-...`) before running the Claude session. Auto-merge to main is skipped — the branch stays alive for a PR. When `false` (default), current behavior is preserved (auto-merge runs, `parallel/` branch is deleted after merge).

## Motivation

Teams using `ll-parallel` and `ll-sprint` in real CI/CD workflows need each issue to land on its own branch for proper code review, PR creation, and traceability. The default of `false` ensures no breaking change for existing users.

## Success Metrics

- When `use_feature_branches: true`, each issue results in a `feature/<id>-<slug>` branch that survives worktree removal; auto-merge to main is skipped; the final run summary lists these as "PR-ready"
- When `use_feature_branches: false` (default), behavior is identical to current — `parallel/<id>-<timestamp>` branch, auto-merged, then deleted
- All existing `ll-parallel` and `ll-sprint` tests pass without modification

## Scope Boundaries

- **In scope**: Adding `use_feature_branches` boolean config option; reading it in `parallel.py` and `sprint.py`; creating the feature branch inside the worktree; skipping auto-merge in the orchestrator when `true`; updating the final run summary to report "PR-ready" branches; documenting the new option
- **Out of scope**: Auto-creating PRs from feature branches (separate concern); branch naming customization beyond issue slug; changes to worktree cleanup logic (the `parallel/` deletion guard already correctly preserves `feature/` branches)

## Proposed Solution

1. Add `use_feature_branches` boolean to the `parallel` and `sprints` sections of `config-schema.json` with `default: false`.
2. Read the config value in `scripts/little_loops/parallel.py` and `scripts/little_loops/sprint.py` (or wherever worktree/branch setup occurs).
3. When `true`, derive a branch name from the issue ID/slug and create/checkout that branch inside the worktree before invoking the Claude session.
4. Document in `docs/` and update the config schema description.

## Integration Map

### Files to Modify
- `config-schema.json` — add `use_feature_branches` boolean to `parallel` section (see line ~264 near `require_code_changes`)
- `scripts/little_loops/config/automation.py` — add `use_feature_branches: bool = False` to `ParallelAutomationConfig` dataclass and its `from_dict()` (lines 39-88)
- `scripts/little_loops/parallel/types.py` — add `use_feature_branches: bool = False` to `ParallelConfig` dataclass and its `from_dict()` (lines 282-454)
- `scripts/little_loops/config/core.py` — add `use_feature_branches` to `create_parallel_config()` factory method (lines 253-329)
- `scripts/little_loops/parallel/worker_pool.py` — change branch naming logic at line 241
- `scripts/little_loops/parallel/orchestrator.py` — skip `queue_merge` at line 869 when `use_feature_branches=True`; update final summary (lines ~966-970) to report "PR-ready" issues as a third outcome bucket

### Key Branch-Naming Anchor
```python
# worker_pool.py:241 — current branch naming (the only place for ll-parallel):
branch_name = f"parallel/{issue.issue_id.lower()}-{timestamp}"
# When use_feature_branches=True, derive a human-readable feature branch name instead:
# branch_name = f"feature/{issue.issue_id.lower()}-{slugify(issue.title)}"
```

### Dependent Files (Callers / Sprint Path)
- `scripts/little_loops/cli/sprint/run.py:377` — calls `config.create_parallel_config(...)`, which feeds `WorkerPool`; no change needed here if `create_parallel_config()` reads `use_feature_branches` from config automatically
- `scripts/little_loops/cli/parallel.py:153` — calls `config.create_parallel_config()` for `ll-parallel`

### Slug Utility (Reusable)
- `scripts/little_loops/issue_parser.py:99` — `slugify(text: str) -> str` already exists; converts text to lowercase hyphenated slug; already imported in `issue_lifecycle.py:19`
- `IssueInfo.title` is the field to slugify (available on the `issue` parameter in `_process_issue()`)

### Tests
- `scripts/tests/test_worker_pool.py` — covers `_setup_worktree` (line 632+); add test asserting branch name is `feature/<id>-<slug>` when `use_feature_branches=True`
- `scripts/tests/test_parallel_types.py` — add `use_feature_branches` to `ParallelConfig` serialization tests
- `scripts/tests/test_sprint.py` and/or `test_sprint_integration.py` — sprint passes through `create_parallel_config()`, which delegates to `WorkerPool`; no separate sprint-specific worktree code

### Branch Deletion Guard (Critical Side Effect)
Both `worker_pool.py:679` and `merge_coordinator.py:1188` guard branch deletion with:
```python
if branch_name.startswith("parallel/"):
    git branch -D <branch_name>
```
When `use_feature_branches: true` produces a `feature/` prefix, this guard will **naturally prevent branch deletion** — the feature branch stays alive after the worktree is removed, ready for a PR. No change needed to cleanup code.

### Sprint Scope Note
Single-issue sprint waves (`cli/sprint/run.py:320-354`) call `process_issue_inplace()` with no worktree — `use_feature_branches` only applies to multi-issue waves (line 364+) that go through `ParallelOrchestrator`.

### Configuration
- `.claude/ll-config.json` — add `"parallel": { "use_feature_branches": false }` to enable

## Implementation Steps

1. **`config-schema.json`** — add `use_feature_branches` boolean property to the `parallel` section, following the pattern of `require_code_changes` at line ~264:
   ```json
   "use_feature_branches": {
     "type": "boolean",
     "description": "Create a dedicated feature branch per issue (e.g., feature/ENH-123-slug) instead of the default parallel/<id>-<timestamp> branch. Use for PR-based CI/CD workflows.",
     "default": false
   }
   ```
2. **`scripts/little_loops/config/automation.py`** — add `use_feature_branches: bool = False` to `ParallelAutomationConfig` (line ~49) and wire it in `from_dict()` (line ~75): `use_feature_branches=data.get("use_feature_branches", False)`
3. **`scripts/little_loops/parallel/types.py`** — add `use_feature_branches: bool = False` to `ParallelConfig` (after line ~350) and wire it in `from_dict()` (after line ~450) and `to_dict()` (after line ~411)
4. **`scripts/little_loops/config/core.py`** — add `use_feature_branches=self._parallel.use_feature_branches` in `create_parallel_config()` return value (after line ~328)
5. **`scripts/little_loops/parallel/worker_pool.py:241`** — replace hardcoded branch naming with conditional logic:
   ```python
   if self.parallel_config.use_feature_branches:
       from little_loops.issue_parser import slugify
       branch_name = f"feature/{issue.issue_id.lower()}-{slugify(issue.title)}"
   else:
       branch_name = f"parallel/{issue.issue_id.lower()}-{timestamp}"
   ```
6. **`scripts/little_loops/parallel/orchestrator.py:869`** — skip `queue_merge` when `use_feature_branches=True`:
   ```python
   if self.parallel_config.use_feature_branches:
       self.logger.info(f"{result.issue_id}: feature branch ready — {result.branch_name}")
   else:
       self.merge_coordinator.queue_merge(result)
       self.merge_coordinator.wait_for_completion(timeout=120)
   ```
   Also update the final summary section (lines ~966-970) to collect and report "PR-ready" issues alongside `merged_ids` and `failed_merges`.
7. **Tests** — add to `scripts/tests/test_worker_pool.py`: test that `_process_issue` uses `feature/<id>-<slug>` branch name when `use_feature_branches=True` on `ParallelConfig`, following the mock pattern in `test_setup_worktree_creates_worktree` (line 632)
8. **Docs** — update `docs/reference/` config reference for the new `parallel.use_feature_branches` option

## Design Note: Merge Behavior with Feature Branches

**Decision: skip auto-merge when `use_feature_branches: true`.**

Rationale: if the `MergeCoordinator` still runs, the `feature/<id>-<slug>` branch's commits land on `main` automatically — leaving the feature branch alive but stale (a PR from it would show an empty diff). That defeats the entire purpose of PR-based CI/CD workflows.

The correct behavior:
- `use_feature_branches: false` (default) → current flow unchanged: merge to main, delete `parallel/` branch
- `use_feature_branches: true` → skip `queue_merge` in `orchestrator.py:869`; feature branch survives (deletion guard at `worker_pool.py:679` and `merge_coordinator.py:1188` already ignores non-`parallel/` prefixes); final run summary reports these issues as "PR-ready" instead of "merged"

Implementation point: `orchestrator.py:869` — wrap `queue_merge` call in `if not self.parallel_config.use_feature_branches`.

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
- `/ll:ready-issue` - 2026-03-24T02:56:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e44ebfe-f83d-445a-a181-9ab066a50540.jsonl`
- `/ll:refine-issue` - 2026-03-24T02:45:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f55ddb5-9f42-4fd3-81cb-591c4d42d468.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:capture-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eec31a4c-27c6-4b78-bafd-8496b3a68d4a.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/644cb258-98f9-4276-9d10-660523431e43.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9efa266e-995d-4387-9681-5c79c26d2743.jsonl`


## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `config-schema.json` does not contain a `use_feature_branches` key (not implemented). Referenced files `scripts/little_loops/parallel.py` and `scripts/little_loops/sprint.py` exist. Feature is not yet implemented.

## Resolution

**Status**: Completed
**Action**: improve
**Date**: 2026-03-23

### Changes Made

- `config-schema.json`: Added `use_feature_branches` boolean property to `parallel` section (default: `false`)
- `scripts/little_loops/config/automation.py`: Added `use_feature_branches: bool = False` field to `ParallelAutomationConfig` and wired in `from_dict()`
- `scripts/little_loops/parallel/types.py`: Added `use_feature_branches: bool = False` to `ParallelConfig`, `to_dict()`, and `from_dict()`
- `scripts/little_loops/config/core.py`: Threaded `use_feature_branches=self._parallel.use_feature_branches` through `create_parallel_config()`
- `scripts/little_loops/parallel/worker_pool.py`: Conditional branch naming — `feature/<id>-<slug>` when `use_feature_branches=True`, `parallel/<id>-<timestamp>` otherwise (existing deletion guard naturally preserves `feature/` branches)
- `scripts/little_loops/parallel/orchestrator.py`: Skip `queue_merge` when `use_feature_branches=True`; mark issue completed immediately; track PR-ready branches in `_pr_ready_branches`; report them in `_report_results()`
- `docs/reference/CONFIGURATION.md`: Documented `require_code_changes` and `use_feature_branches` in the `parallel` table
- Tests: Added `use_feature_branches` assertions to `test_parallel_types.py` (default value + roundtrip) and new `test_process_issue_uses_feature_branch_name_when_enabled` in `test_worker_pool.py`

### Verification

- 3891 tests pass (0 failures)
- `ruff check`: All checks passed
- `mypy`: No issues found in 110 source files

## Blocked By
## Blocks
- ENH-507
- ENH-470
- ENH-459
- ENH-654
- ENH-497
- ENH-485
