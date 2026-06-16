---
id: ENH-2173
title: Add --feature-branches CLI override to ll-parallel / ll-sprint
type: ENH
status: done
priority: P3
parent: EPIC-2171
captured_at: '2026-06-15T16:51:50Z'
completed_at: '2026-06-16T16:08:53Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels:
- parallel
- sprint
- cli
- feature-branches
- dx
depends_on:
- BUG-2172
confidence_score: 100
outcome_confidence: 90
decision_needed: false
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 23
---

# ENH-2173: Add --feature-branches CLI override to ll-parallel / ll-sprint

## Summary

Add `--feature-branches` CLI override flag to `ll-parallel` and `ll-sprint run` so users can opt into the feature-branch/PR-based workflow for a single run without editing `.ll/ll-config.json`.

## Motivation

`parallel.use_feature_branches` is the only major parallel setting with no CLI
override. Every sibling setting (`--workers`, `--worktree-base`,
`--stream-output`, `--show-model`, etc.) can be set per-run on `ll-parallel`,
but `use_feature_branches` is read exclusively from `.ll/ll-config.json`
(`config/core.py:487` → `self._parallel.use_feature_branches`).
`create_parallel_config()` does not even accept the parameter. As a result a
user cannot opt into the PR-based workflow for a single run — they must hand-edit
config and revert it afterward.

## Current Behavior

- `cli/parallel.py` argument list (lines ~62-153) has no `--feature-branches`.
- `create_parallel_config()` (`config/core.py:415`+) has no
  `use_feature_branches` parameter; it always uses
  `self._parallel.use_feature_branches` (line 487).
- `cli/sprint/run.py:503` calls `create_parallel_config()` for multi-issue
  waves and likewise cannot override the flag per run.

## Expected Behavior

- `ll-parallel --feature-branches` enables feature-branch mode for that run regardless of the config value.
- Omitting the flag falls back to the config value (no behavior change for existing users).
- `ll-sprint run --feature-branches` applies the same override to multi-issue sprint waves.
- `create_parallel_config()` accepts and correctly resolves the new `use_feature_branches: bool | None` parameter.

## Proposed Solution

Mirror the existing override pattern used for `stream_output` / `show_model`
(`arg if arg else None` → fall back to config):

1. Add `--feature-branches` / `--no-feature-branches` to `cli/parallel.py` using
   `action=argparse.BooleanOptionalAction, default=None` (Python 3.9+) so both
   the enable and negate forms are available from the first release.
2. Add a `use_feature_branches: bool | None = None` parameter to
   `create_parallel_config()`; resolve as
   `use_feature_branches if use_feature_branches is not None else self._parallel.use_feature_branches`.
3. Pass `args.feature_branches` straight through (it is already `True` / `False` /
   `None` with `BooleanOptionalAction`); do **not** apply `or None` coercion so an
   explicit `False` survives and forces the flag off.
4. Add the same `BooleanOptionalAction` flag to `cli/sprint/run.py` and thread it
   into its `create_parallel_config()` call.
5. (Optional, depends on BUG-2172) if push/PR sub-flags are added, expose
   matching CLI flags here too.

## API/Interface

- `create_parallel_config(..., use_feature_branches: bool | None = None)` —
  new keyword-only parameter; `None` preserves config-driven default.
- New CLI flags: `ll-parallel --feature-branches` / `--no-feature-branches`, `ll-sprint run --feature-branches` / `--no-feature-branches`.

## Acceptance Criteria

1. `ll-parallel --feature-branches` enables feature-branch mode for that run
   regardless of config value.
2. Omitting the flag falls back to the config value (no behavior change for
   existing users).
3. `ll-sprint run --feature-branches` applies the same override to multi-issue waves.
4. `create_parallel_config()` accepts and correctly resolves the new parameter.
5. Tests cover the full truth table: `--feature-branches` → True;
   `--no-feature-branches` → False; neither + config True → True;
   neither + config False → False.

## Scope Boundaries

- Adding push/PR sub-flags (depends on BUG-2172) is explicitly optional and excluded from this issue's scope.
- No changes to `.ll/ll-config.json` schema or default values — the flag only overrides, never replaces, the config setting.
- Scope absorbed from ENH-2180: `--no-feature-branches` (the negation form) is in scope and implemented via `BooleanOptionalAction` alongside `--feature-branches`. ENH-2180 is closed as merged into this issue.
- No behavior changes to feature-branch mode itself — only the activation mechanism.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/parallel.py` — add `--feature-branches` / `--no-feature-branches` arg (after line 113 where `--show-model` is defined); thread `args.feature_branches` into `create_parallel_config()` at the main call site (line 202); do NOT touch the cleanup-path call at line 167 (uses all config defaults, never reaches feature-branch code)
- `scripts/little_loops/config/core.py` — add `use_feature_branches: bool | None = None` as a keyword-only parameter to `create_parallel_config()` signature (line 415); resolve at line 487 where `use_feature_branches=self._parallel.use_feature_branches` is assigned
- `scripts/little_loops/cli/sprint/__init__.py` — add `--feature-branches` / `--no-feature-branches` to the `run` subparser in `main_sprint()` (lines 119–144 where other `run` subcommand args are defined); `args` from this parser are available in `_cmd_sprint_run()`
- `scripts/little_loops/cli/sprint/run.py` — thread `args.feature_branches` into the `create_parallel_config()` call at line 503 in `_cmd_sprint_run()`; no argparse changes here

### Similar Patterns

_Exact patterns verified by codebase research:_

**`--stream-output` argparse definition** (`cli/parallel.py` lines 105–108):
```python
parser.add_argument(
    "--stream-output",
    action="store_true",
    help="Stream Claude CLI subprocess output to console",
)
```
The new `--feature-branches` flag should use `action=argparse.BooleanOptionalAction, default=None` instead of `store_true`, because we need three states: `True` (explicit enable), `False` (explicit disable via `--no-feature-branches`), and `None` (absent → use config).

**`store_true` threading idiom** (`cli/parallel.py` lines 210–211):
```python
stream_output=args.stream_output if args.stream_output else None,
show_model=args.show_model if args.show_model else None,
```
`BooleanOptionalAction` flags must **NOT** use this `if arg else None` coercion — an explicit `--no-feature-branches` gives `False`, which `if arg else None` would convert back to `None`, losing the override. Pass `args.feature_branches` directly (already `True` / `False` / `None`).

**Resolution idiom** (`config/core.py` lines 473–476):
```python
stream_subprocess_output=(
    stream_output if stream_output is not None else self._parallel.base.stream_output
),
show_model=show_model if show_model is not None else False,
```
`use_feature_branches` should follow the `stream_output` pattern (fall back to config value, not hardcoded `False`):
```python
use_feature_branches=(
    use_feature_branches if use_feature_branches is not None else self._parallel.use_feature_branches
),
```

**Existing assignment** (`config/core.py` line 487):
```python
use_feature_branches=self._parallel.use_feature_branches,
```
Replace with the ternary above.

### Tests
- `scripts/tests/test_config.py` — add cases to `TestBRConfig.create_parallel_config` for the full truth table (lines 875–904 model existing override tests)
- `scripts/tests/test_parallel_types.py` — existing `use_feature_branches` coverage; no changes needed
- `scripts/tests/conftest.py` — `sample_config` fixture (lines 139–189) does not include `use_feature_branches`; add `"use_feature_branches": True` to the `parallel` subsection to enable testing the config-driven fallback

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/parallel.py` (line 202) — primary caller of `create_parallel_config()`; already in Files to Modify
- `scripts/little_loops/cli/sprint/run.py` (line 503) — secondary caller of `create_parallel_config()` for multi-issue waves; already in Files to Modify
- `scripts/little_loops/cli/parallel.py` (line 167) — cleanup-path call with no args; no changes needed

### Documentation
- N/A — no documentation files reference `create_parallel_config` or `use_feature_branches` directly; CLI `--help` output updates automatically from argparse.

### Configuration
- `.ll/ll-config.json` → `parallel.use_feature_branches` — read-only by this change; no schema changes required; the new CLI flag overrides this value per-run.

## Implementation Steps

1. **`config/core.py` — extend `create_parallel_config()` signature** (line 415): add `use_feature_branches: bool | None = None` as the last keyword-only parameter before `-> ParallelConfig:`
2. **`config/core.py` — resolve the override** (line 487): replace `use_feature_branches=self._parallel.use_feature_branches,` with `use_feature_branches=(use_feature_branches if use_feature_branches is not None else self._parallel.use_feature_branches),`
3. **`cli/parallel.py` — add argparse flag** (after line 113): add `parser.add_argument("--feature-branches", action=argparse.BooleanOptionalAction, default=None, help="Enable/disable feature-branch mode for this run (overrides config)")`; ensure `import argparse` is already present
4. **`cli/parallel.py` — thread flag into call site** (line 202): add `use_feature_branches=args.feature_branches,` to the `create_parallel_config()` keyword arguments (pass directly, no `if arg else None` coercion)
5. **`cli/sprint/__init__.py` — add argparse flag** (lines 119–144): add the same `BooleanOptionalAction` argument to the `run` subparser in `main_sprint()`
6. **`cli/sprint/run.py` — thread flag into call site** (line 503): add `use_feature_branches=args.feature_branches,` to the `create_parallel_config()` call in `_cmd_sprint_run()`
7. **`tests/conftest.py` — extend fixture** (lines 171–182): add `"use_feature_branches": True` to the `parallel` section of `sample_config` so config-driven fallback tests work
8. **`tests/test_config.py` — add truth-table tests** (after line 904): add four cases to `TestBRConfig`: `--feature-branches` → `True`; `--no-feature-branches` → `False`; neither + config `True` → `True`; neither + config `False` → `False`
9. **Verify**: `python -m pytest scripts/tests/test_config.py -v -k "feature_branches"` passes all four new cases

## Impact

- **Priority**: P3 — DX gap; removes the hand-edit-config requirement to use the flag.
- **Effort**: Small — argparse + one config param + tests.
- **Risk**: Low — additive; `None` default preserves current behavior.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-16T15:57:56 - `4f663461-f762-4efe-b9a5-50900006aa86.jsonl`
- `/ll:confidence-check` - 2026-06-16T16:00:00Z - `3e2d361c-8a9c-477d-90f0-34d278d05004.jsonl`
- `/ll:refine-issue` - 2026-06-16T15:52:50 - `b5c00f10-e24d-45e3-bfd8-2db6e286450e.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `7d92b745-9845-4025-b2bd-6c0f91be6cf2.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:47:59 - `fc9e22f8-f75a-4ab7-a570-0b05a961077c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:33:23 - `708f5540-fdfd-4ca1-92bc-72a7cb548730.jsonl`
- `/ll:format-issue` - 2026-06-15T16:57:39 - `c31adb30-3c6b-4940-9ce0-5ccae335bee1.jsonl`
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`
