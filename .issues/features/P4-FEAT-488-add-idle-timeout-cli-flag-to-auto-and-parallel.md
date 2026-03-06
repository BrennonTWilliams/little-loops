---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
confidence_score: 90
outcome_confidence: 85
---

# FEAT-488: Add `--idle-timeout` CLI flag to ll-auto and ll-parallel

## Summary

The idle-timeout kill mechanism (`idle_timeout_seconds` in config) is fully functional at the library level but has no CLI flag exposure. Users must edit `ll-config.json` to set it. Adding `--idle-timeout` to both `ll-auto` and `ll-parallel` would allow per-run overrides, consistent with how `--timeout` already works.

## Current Behavior

- `config.py:193` — `idle_timeout_seconds: int = 0` exists in `AutomationConfig`
- `parallel/types.py:320` — `idle_timeout_per_issue: int = 0` exists in `ParallelConfig`
- These are used in `issue_manager.py:317` and `worker_pool.py:713`
- Neither `cli/auto.py` nor `cli/parallel.py` exposes an `--idle-timeout` argument

## Expected Behavior

Both `ll-auto` and `ll-parallel` accept an `--idle-timeout SECONDS` flag that overrides the config file value for that run.

## Motivation

The `--idle-timeout` config value exists but requires users to edit `ll-config.json` to change it per run. For one-off runs with problematic issues, this is cumbersome. Exposing `--idle-timeout` as a CLI flag follows the existing `--timeout` pattern and allows per-run overrides without modifying shared config — consistent with the principle that CLI flags override config values.

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

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Sequential and parallel mode design, configuration flow (line 508) |
| `docs/reference/CONFIGURATION.md` | `idle_timeout_seconds` (automation section) and `idle_timeout_per_issue` (parallel section) config options |

## Labels

`feature`, `cli`, `automation`, `auto-generated`

## Verification Notes

- **2026-03-05** — VALID. `config.py:181` `idle_timeout_seconds` confirmed; `parallel/types.py` `idle_timeout_per_issue` confirmed; no `--idle-timeout` argument in `cli/auto.py` or `cli/parallel.py`. `add_timeout_arg` pattern in `cli_args.py` confirmed for reference.
- **2026-03-06** — VALID with corrections. Two line numbers in "Current Behavior" were stale: `config.py:181` corrected to `config.py:193`; `worker_pool.py:688` corrected to `worker_pool.py:713`. All other facts confirmed: `idle_timeout_seconds` at config.py:193, `idle_timeout_per_issue` at parallel/types.py:320, `issue_manager.py:317` usage, no `--idle-timeout` flag in cli/auto.py or cli/parallel.py, `add_timeout_arg` at cli_args.py:96. result: VALID (corrections applied)

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a32a1e4-137e-4580-a6db-a31be30ec313.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is well-specified; add_timeout_arg pattern in cli_args.py confirmed as the model to follow; no knowledge gaps identified
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; still blocked by FEAT-490, FEAT-441, ENH-459
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c629849-3bc7-41ac-bef7-db62aeeb8917.jsonl`
- `/ll:refine-issue` - 2026-03-03T23:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` - Linked `docs/ARCHITECTURE.md` (line 508) and `docs/reference/CONFIGURATION.md` to Related Key Documentation
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a018087-87e4-41d0-99de-499289e1e675.jsonl` — Removed FEAT-441 from Blocked By (completed/satisfied)
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`
- `/ll:confidence-check` - 2026-03-06 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — confidence_score=90, outcome_confidence=85
- `/ll:verify-issues` - 2026-03-06 - Corrected two stale line numbers: config.py:181→193, worker_pool.py:688→713. All other facts valid. result: VALID

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4

---

## Tradeoff Review Note

**Reviewed**: 2026-02-26 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Deferred - Good utility-to-cost ratio (MEDIUM utility, LOW effort) but blocked by 3 upstream issues (FEAT-490, FEAT-441, ENH-459). This becomes a quick win once blockers resolve. No changes needed to the issue itself.

## Blocked By

- FEAT-490

- ENH-459

## Blocks

- ENH-507
