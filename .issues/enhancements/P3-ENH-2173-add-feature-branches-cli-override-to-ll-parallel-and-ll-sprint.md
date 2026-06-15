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
---

# ENH-2173: Add --feature-branches CLI override to ll-parallel / ll-sprint

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

## Proposed Solution

Mirror the existing override pattern used for `stream_output` / `show_model`
(`arg if arg else None` → fall back to config):

1. Add `--feature-branches` (store_true, default `None`) to `cli/parallel.py`.
2. Add a `use_feature_branches: bool | None = None` parameter to
   `create_parallel_config()`; resolve as
   `use_feature_branches if use_feature_branches is not None else self._parallel.use_feature_branches`.
3. Pass `args.feature_branches or None` from `cli/parallel.py`.
4. Add the same `--feature-branches` flag to `cli/sprint/run.py` and thread it
   into its `create_parallel_config()` call.
5. (Optional, depends on BUG-2172) if push/PR sub-flags are added, expose
   matching CLI flags here too.

## API/Interface

- `create_parallel_config(..., use_feature_branches: bool | None = None)` —
  new keyword-only parameter; `None` preserves config-driven default.
- New CLI flags: `ll-parallel --feature-branches`, `ll-sprint run --feature-branches`.

## Acceptance Criteria

1. `ll-parallel --feature-branches` enables feature-branch mode for that run
   regardless of config value.
2. Omitting the flag falls back to the config value (no behavior change for
   existing users).
3. `ll-sprint run --feature-branches` applies the same override to multi-issue waves.
4. `create_parallel_config()` accepts and correctly resolves the new parameter.
5. Tests cover: flag set → True, flag unset + config True → True, flag unset +
   config False → False.

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

## Impact

- **Priority**: P3 — DX gap; removes the hand-edit-config requirement to use the flag.
- **Effort**: Small — argparse + one config param + tests.
- **Risk**: Low — additive; `None` default preserves current behavior.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`
