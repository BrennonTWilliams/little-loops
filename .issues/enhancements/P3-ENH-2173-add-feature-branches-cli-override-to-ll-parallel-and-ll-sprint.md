---
id: ENH-2173
title: Add --feature-branches CLI override to ll-parallel / ll-sprint
type: ENH
status: open
priority: P3
parent: EPIC-2171
captured_at: '2026-06-15T16:51:50Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [parallel, sprint, cli, feature-branches, dx]
depends_on: [BUG-2172]
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
- `scripts/little_loops/cli/parallel.py` — add `--feature-branches` arg; pass into `create_parallel_config`
- `scripts/little_loops/config/core.py` — add `use_feature_branches` param to `create_parallel_config` (~line 415, resolve at ~487)
- `scripts/little_loops/cli/sprint/run.py` — add `--feature-branches` arg; pass into `create_parallel_config` (~line 503)

### Similar Patterns
- `config/core.py` — `stream_output` / `show_model` resolution (`arg if arg is not None else config`) — model after this
- `cli/parallel.py` — `--stream-output` / `--show-model` argparse entries — model after these

### Tests
- `scripts/tests/test_config.py` — add cases for `create_parallel_config(use_feature_branches=...)` resolution
- `scripts/tests/test_parallel_types.py` — existing `use_feature_branches` coverage

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/parallel.py` — primary caller of `create_parallel_config()`; already in Files to Modify
- `scripts/little_loops/cli/sprint/run.py` — secondary caller of `create_parallel_config()` for multi-issue waves; already in Files to Modify

### Documentation
- N/A — no documentation files reference `create_parallel_config` or `use_feature_branches` directly; CLI `--help` output updates automatically from argparse.

### Configuration
- `.ll/ll-config.json` → `parallel.use_feature_branches` — read-only by this change; no schema changes required; the new CLI flag overrides this value per-run.

## Impact

- **Priority**: P3 — DX gap; removes the hand-edit-config requirement to use the flag.
- **Effort**: Small — argparse + one config param + tests.
- **Risk**: Low — additive; `None` default preserves current behavior.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-15T20:47:59 - `fc9e22f8-f75a-4ab7-a570-0b05a961077c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:33:23 - `708f5540-fdfd-4ca1-92bc-72a7cb548730.jsonl`
- `/ll:format-issue` - 2026-06-15T16:57:39 - `c31adb30-3c6b-4940-9ce0-5ccae335bee1.jsonl`
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`
