---
id: ENH-2086
title: Add cross-host validation option to ll-loop run --baseline
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
parent: EPIC-2087
depends_on: ENH-2084
---

# ENH-2086: Add cross-host validation option to ll-loop run --baseline

## Summary

`ll-loop run --baseline` currently validates loop quality improvements on a single configured host only, providing no cross-host evidence. This enhancement adds a `--cross-host` flag that re-runs the same loop on a second available host (per `ll-doctor`) and appends a comparison table to the baseline report showing per-host pass rates and Wilson CIs, with a warning when ordering reversal is detected.

## Current Behavior

`ll-loop run --baseline` runs evaluation trials on one host only. There is no mechanism to verify that measured quality improvements hold across other supported hosts (Claude Code, Codex, OpenCode). A loop optimized on one host may appear improved due to host-specific tooling behavior rather than genuine capability gains.

## Expected Behavior

When `--cross-host` is passed to `ll-loop run --baseline`:
1. A second available host is identified via `ll-doctor`
2. The same loop is re-run on that host
3. A comparison table is appended to the baseline report showing pass rates and Wilson CIs per host
4. A warning is emitted if the quality ordering reverses between hosts
5. Only configured, available hosts are used (no-op if only one host is available)

## Motivation

Loop quality improvements validated on a single host may be artifacts of that host's tooling rather than genuine capability gains. Running the same harness on a second supported host (Claude Code vs. Codex vs. OpenCode) and confirming the qualitative ordering is preserved provides validity evidence that improvements are real.

## Proposed Solution

Add a `--cross-host` flag to `ll-loop run --baseline` that re-runs the same loop on a second host via `resolve_host()` and appends a cross-host comparison table to the baseline report. The comparison should show pass rates and Wilson CIs per host, flag cases where the ordering reverses, and emit a warning if reversal is detected. Limit to hosts that are configured and available via `ll-doctor`. Document the flag in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` as a recommended validity check before promoting a baseline.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` or baseline runner module — add `--cross-host` flag and second-host trial logic
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document `--cross-host` as a pre-promotion validity check

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` — `resolve_host()` and host enumeration used to identify available hosts
- TBD - grep for baseline runner: `grep -r "baseline" scripts/little_loops/`

### Similar Patterns
- `scripts/little_loops/host_runner.py` — existing multi-host resolution pattern to follow

### Tests
- TBD - identify baseline runner test files: `grep -r "baseline" scripts/tests/`

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — add `--cross-host` section as validity check step

### Configuration
- N/A

## Implementation Steps

1. Add `--cross-host` flag to `ll-loop run --baseline` CLI
2. Implement second-host runner via `resolve_host()` for available hosts per `ll-doctor`
3. Build cross-host comparison table: pass rates + Wilson CIs per host
4. Detect and warn on ordering reversals between hosts
5. Append cross-host table to baseline report output
6. Document `--cross-host` in `HARNESS_OPTIMIZATION_GUIDE.md` as a pre-promotion validity check

## Scope Boundaries

- **Out of scope**: Parallelizing baseline trials across multiple hosts simultaneously
- **Out of scope**: Adding new host support beyond what `ll-doctor` already reports as available
- **Out of scope**: Persisting cross-host comparison results to a separate store or database
- **Out of scope**: Automatic host selection heuristics beyond picking the first available second host
- **Out of scope**: Changing existing `--baseline` behavior when `--cross-host` is not passed

## API/Interface

CLI-only addition; no Python API changes.

```
ll-loop run --baseline --cross-host [--trials N] <loop-name>
```

Uses existing `resolve_host()` from `scripts/little_loops/host_runner.py` for host enumeration. No new public functions exposed.

## Acceptance Criteria

- [ ] `ll-loop run --baseline --cross-host` runs the loop on a second available host
- [ ] Output includes per-host pass rates and Wilson CIs in a comparison table
- [ ] Ordering reversal between hosts emits a warning
- [ ] Only available hosts (per `ll-doctor`) are used
- [ ] `HARNESS_OPTIMIZATION_GUIDE.md` documents the flag and its purpose

## Impact

- **Priority**: P3 - Useful validity check for advanced baseline workflows; not on the critical path for core functionality
- **Effort**: Medium - Requires CLI flag addition, `resolve_host()` integration, second-host trial execution, and comparison table output
- **Risk**: Low - Purely additive flag; existing `--baseline` behavior is completely unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `baseline`, `multi-host`, `ll-loop`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-10T23:34:21 - `714a8869-591f-4a9c-91ec-045042d7d120.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-10T23:30:28 - `59a16773-20bc-402b-b0cb-97d45d141b4c.jsonl`
