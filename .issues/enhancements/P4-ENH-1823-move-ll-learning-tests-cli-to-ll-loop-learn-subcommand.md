---
id: ENH-1823
title: Move ll-learning-tests CLI to ll-loop learn subcommand
type: ENH
priority: P4
captured_at: '2026-05-31T05:47:13Z'
discovered_date: '2026-05-31'
discovered_by: capture-issue
status: cancelled
labels:
- enhancement
- cli
- refactor
- loops
- learning-tests
---

# ENH-1823: Move ll-learning-tests CLI to ll-loop learn subcommand

## Summary

Consolidate the standalone `ll-learning-tests` CLI into `ll-loop learn <subcommand>` to reduce top-level CLI surface and improve discoverability. The three existing subcommands (`check`, `list`, `mark-stale`) become `ll-loop learn check`, `ll-loop learn list`, and `ll-loop learn mark-stale`. The logic module (`learning_tests.py`) is unchanged — only the CLI dispatch layer moves. The `ll-learning-tests` entry point is removed entirely (clean cut, no deprecated alias).

## Current Behavior

`ll-learning-tests` is a standalone CLI entry point registered in `pyproject.toml` with three subcommands:
- `ll-learning-tests check <name>` — check whether a learning test passes
- `ll-learning-tests list` — list all registered learning tests
- `ll-learning-tests mark-stale <name>` — mark a learning test as stale

It is invoked primarily by the `/ll:explore-api` skill, not by end users directly. The CLI handler lives in `scripts/little_loops/cli/learning_tests.py` (~91 lines); the logic lives in `scripts/little_loops/learning_tests.py` (~142 lines).

## Expected Behavior

Learning test operations are accessible via `ll-loop learn <subcommand>`:
- `ll-loop learn check <name>`
- `ll-loop learn list`
- `ll-loop learn mark-stale <name>`

The `ll-learning-tests` binary is removed. References in `/ll:explore-api` and `CLAUDE.md` are updated to the new surface. The logic module is untouched.

## Motivation

`ll-learning-tests` is a niche tool (primarily Claude-invoked, not user-facing) occupying a top-level CLI slot. Learning tests are conceptually part of the loop ecosystem — they test loop/FSM API contracts. Surfacing them under `ll-loop learn` makes them discoverable via `ll-loop --help`, reduces the number of entry points to maintain, and keeps the `ll-loop` namespace as the single home for loop-related operations.

## Proposed Solution

1. Add a `learn` subcommand to `scripts/little_loops/cli/loop/__init__.py` that delegates to the existing `cmd_check`, `cmd_list`, `cmd_mark_stale` functions in `scripts/little_loops/cli/learning_tests.py`. The `learn` dispatcher should accept a nested `COMMAND` argument and forward to the correct handler — same pattern as `diagnose-evaluators` and `promote-baseline`.
2. Remove `ll-learning-tests` from `scripts/pyproject.toml` `[project.scripts]` table.
3. Update `/ll:explore-api` skill to invoke `ll-loop learn check` / `ll-loop learn list` / `ll-loop learn mark-stale` instead of `ll-learning-tests *`.
4. Update `.claude/CLAUDE.md` CLI Tools entry: replace `ll-learning-tests - Query and manage the learning test registry (check/list/mark-stale)` with a note under `ll-loop` that `learn` subcommand covers these operations.
5. Update `known_subcommands` set in `main_loop()` to include `"learn"`.

The `cli/learning_tests.py` module can stay as internal implementation or be inlined into the loop CLI — either works since it has no external importers.

## API/Interface

```
# Before
ll-learning-tests check <name>
ll-learning-tests list
ll-learning-tests mark-stale <name>

# After
ll-loop learn check <name>
ll-loop learn list
ll-loop learn mark-stale <name>
```

No changes to `LearningTestRegistry`, `LearningTest`, or any public Python API in `learning_tests.py`.

## Success Metrics

- [ ] `ll-loop learn check`, `ll-loop learn list`, `ll-loop learn mark-stale` all execute correctly
- [ ] `ll-learning-tests` binary no longer exists after install
- [ ] `/ll:explore-api` skill invocations reference `ll-loop learn *` and work end-to-end
- [ ] `ll-loop --help` lists `learn` in the subcommand list

## Scope Boundaries

- No changes to `learning_tests.py` logic module.
- No changes to the learning test registry format or storage.
- No adding new learning test operations beyond what `ll-learning-tests` already provided.
- `ll-learning-tests` is removed; no deprecated shim or alias is added.

## Implementation Steps

1. Add `learn` dispatch branch to `scripts/little_loops/cli/loop/__init__.py` — sub-parser with `check`, `list`, `mark-stale`; delegate to existing handlers in `cli/learning_tests.py`
2. Add `"learn"` to `known_subcommands` set in `main_loop()`
3. Remove `ll-learning-tests` entry from `scripts/pyproject.toml` `[project.scripts]`
4. Update `/ll:explore-api` skill references from `ll-learning-tests *` to `ll-loop learn *`
5. Update `.claude/CLAUDE.md` CLI Tools section
6. Update tests: rename/adapt `test_cli_learning_tests.py` to test via `ll-loop learn`; add `test_learn_subcommand_registered` in `test_ll_loop_execution.py`
7. Run `pip install -e "./scripts[dev]"` to verify entry-point removal; run pytest

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `learn` subcommand dispatch and `"learn"` to `known_subcommands`
- `scripts/pyproject.toml` — remove `ll-learning-tests` from `[project.scripts]`
- `skills/explore-api/` — update `ll-learning-tests` invocations to `ll-loop learn`
- `.claude/CLAUDE.md` — update CLI Tools section

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/learning_tests.py` — CLI handlers stay; imported by the new `learn` dispatch branch (no external callers beyond the entry point)
- `scripts/little_loops/cli/__init__.py` — check if `main_learning_tests` is exported; if so, remove

### Similar Patterns
- `scripts/little_loops/cli/loop/__init__.py` — `diagnose-evaluators` subcommand registration pattern to follow for `learn`

### Tests
- `scripts/tests/test_cli_learning_tests.py` — update to invoke via `ll-loop learn *` CLI path or keep testing handlers directly; add `test_learn_subcommand_registered` following `test_diagnose_evaluators_subcommand_registered` pattern in `test_ll_loop_execution.py`

### Documentation
- `.claude/CLAUDE.md` — CLI Tools section (replace `ll-learning-tests` bullet)
- `docs/reference/API.md` — if `ll-learning-tests` CLI is documented, update reference

### Configuration
- `scripts/pyproject.toml` — `[project.scripts]` entry removal

## Impact

- **Priority**: P4 — cleanup only; `ll-learning-tests` works fine today. Not on any critical path.
- **Effort**: Small — dispatch wiring (~20 lines), one `pyproject.toml` edit, skill + doc updates. No logic changes.
- **Risk**: Low — `ll-learning-tests` is primarily Claude-invoked via `/ll:explore-api`; the skill reference update is the highest-risk touch point. The logic module is untouched.
- **Breaking Change**: Yes (binary rename) — but impact is contained to the `/ll:explore-api` skill which is updated as part of this issue.

## Related Key Documentation

| Path | Why relevant |
|------|--------------|
| `.claude/CLAUDE.md` | CLI Tools section lists `ll-learning-tests`; must be updated |
| `docs/reference/API.md` | May document `ll-learning-tests` CLI; update if so |

## Session Log
- `/ll:capture-issue` - 2026-05-31T05:47:13Z - `7da4f0e0-fdbc-430e-95a5-ae05ed7be793.jsonl`

---

## Cancellation Note

Cancelled 2026-05-31. `ll-learning-tests` is primarily Claude-invoked via `/ll:explore-api`, not user-typed — the discoverability argument for consolidating under `ll-loop` doesn't apply. Churn cost (skill update, entry-point removal, test rewiring) exceeds the benefit of a cleaner top-level binary list. Keep `ll-learning-tests` as-is.

## Status
cancelled
