---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# FEAT-488: Add `--idle-timeout` CLI flag to ll-auto and ll-parallel

## Summary

The idle-timeout kill mechanism (`idle_timeout_seconds` in config) is fully functional at the library level but has no CLI flag exposure. Users must edit `ll-config.json` to set it. Adding `--idle-timeout` to both `ll-auto` and `ll-parallel` would allow per-run overrides, consistent with how `--timeout` already works.

## Current Behavior

- `config.py:181` — `idle_timeout_seconds: int = 0` exists in `AutomationConfig`
- `parallel/types.py:320` — `idle_timeout_per_issue: int = 0` exists in `ParallelConfig`
- These are used in `issue_manager.py:317` and `worker_pool.py:688`
- Neither `cli/auto.py` nor `cli/parallel.py` exposes an `--idle-timeout` argument

## Expected Behavior

Both `ll-auto` and `ll-parallel` accept an `--idle-timeout SECONDS` flag that overrides the config file value for that run.

## Use Case

A developer runs `ll-parallel --idle-timeout 300` to kill any worker that produces no output for 5 minutes, without modifying the shared config file. This is useful for one-off runs with known-problematic issues.

## Acceptance Criteria

- [ ] `ll-auto --idle-timeout N` sets `idle_timeout_seconds` for that run
- [ ] `ll-parallel --idle-timeout N` sets `idle_timeout_per_issue` for that run
- [ ] Default behavior unchanged when flag is not provided (uses config value)
- [ ] Flag documented in `--help` output

## Proposed Solution

Add `add_idle_timeout_arg(parser)` to `cli_args.py` following the `add_timeout_arg` pattern, and wire it into `auto.py` and `parallel.py`.

## Implementation Steps

1. Add `add_idle_timeout_arg` to `cli_args.py`
2. Call it from `add_common_auto_args` and `add_common_parallel_args`
3. Wire `args.idle_timeout` into the config override in both CLI entry points
4. Add help text

## Integration Map

### Files to Modify
- `scripts/little_loops/cli_args.py` — add `add_idle_timeout_arg`
- `scripts/little_loops/cli/auto.py` — wire flag to config
- `scripts/little_loops/cli/parallel.py` — wire flag to config

### Dependent Files (Callers/Importers)
- N/A

### Similar Patterns
- `add_timeout_arg` in `cli_args.py` — same pattern

### Tests
- `scripts/tests/` — add test for CLI argument parsing

### Documentation
- N/A — `--help` auto-generated

### Configuration
- N/A — overrides existing config value

## Impact

- **Priority**: P4 — Quality-of-life improvement for CLI users
- **Effort**: Small — Follows existing `--timeout` pattern exactly
- **Risk**: Low — Additive CLI flag
- **Breaking Change**: No

## Labels

`feature`, `cli`, `automation`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4
