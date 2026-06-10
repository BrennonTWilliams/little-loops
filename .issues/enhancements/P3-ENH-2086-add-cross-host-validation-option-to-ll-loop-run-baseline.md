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
---

# ENH-2086: Add cross-host validation option to ll-loop run --baseline

## Motivation

Loop quality improvements validated on a single host may be artifacts of that host's tooling rather than genuine capability gains. Running the same harness on a second supported host (Claude Code vs. Codex vs. OpenCode) and confirming the qualitative ordering is preserved provides validity evidence that improvements are real.

## Proposed Solution

Add a `--cross-host` flag to `ll-loop run --baseline` that re-runs the same loop on a second host via `resolve_host()` and appends a cross-host comparison table to the baseline report. The comparison should show pass rates and Wilson CIs per host, flag cases where the ordering reverses, and emit a warning if reversal is detected. Limit to hosts that are configured and available via `ll-doctor`. Document the flag in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` as a recommended validity check before promoting a baseline.

## Implementation Steps

1. Add `--cross-host` flag to `ll-loop run --baseline` CLI
2. Implement second-host runner via `resolve_host()` for available hosts per `ll-doctor`
3. Build cross-host comparison table: pass rates + Wilson CIs per host
4. Detect and warn on ordering reversals between hosts
5. Append cross-host table to baseline report output
6. Document `--cross-host` in `HARNESS_OPTIMIZATION_GUIDE.md` as a pre-promotion validity check

## Acceptance Criteria

- [ ] `ll-loop run --baseline --cross-host` runs the loop on a second available host
- [ ] Output includes per-host pass rates and Wilson CIs in a comparison table
- [ ] Ordering reversal between hosts emits a warning
- [ ] Only available hosts (per `ll-doctor`) are used
- [ ] `HARNESS_OPTIMIZATION_GUIDE.md` documents the flag and its purpose

## Status

open
