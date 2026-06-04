---
id: ENH-1921
title: "ll-logs stats: skill frequency/error/correction telemetry"
type: ENH
priority: P3
status: open
captured_at: "2026-06-04T02:27:34Z"
discovered_date: "2026-06-04"
discovered_by: capture-issue
parent: EPIC-1918
relates_to: [EPIC-1918, ENH-1922]
labels: [captured, ll-logs, telemetry]
---

# ENH-1921: ll-logs stats — skill frequency / error / correction telemetry

## Summary

Add `ll-logs stats` to aggregate, across the log corpus, per-skill invocation
frequency, failure rate, and correction rate — a quality dashboard for the ll
skill/command catalog.

## Current Behavior

There is no aggregate view of how often each ll skill is invoked, how often its
invocation is followed by a failure or user correction, or which skills dominate
real usage. `ll-ctx-stats` covers context bytes but not invocation/quality.

## Expected Behavior

`ll-logs stats [--project DIR|--all] [--window-days D] [--sort freq|errors|corrections] [--json]`
prints a table: skill/command, invocation count, error count/rate, correction
count/rate, and (optionally) median cost via `ll-ctx-stats` join.

## Motivation

Surfaces which skills are heavily used vs. ignored, and which produce the most
failures or corrections — directing refinement effort where it matters and
feeding dead-skill detection (ENH-1923).

## Proposed Solution

Add `stats` to `cli/logs.py` reusing the shared ll-invocation extractor
(ENH-1919). Count invocations per skill; detect adjacent failures (nonzero/
traceback, see ENH-1922) and corrections (reuse `is_correction()` from
`session_store.py`). Optionally join `ll-ctx-stats` for cost.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `stats` subcommand

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store.py` — reuse `is_correction()` for correction detection
- `scripts/little_loops/cli/logs.py` — reuse shared ll-invocation extractor (ENH-1919)

### Similar Patterns
- `ll-ctx-stats` aggregation approach for optional cost column join

### Tests
- `scripts/tests/` — new fixture-corpus test for stats aggregation

### Documentation
- `docs/reference/API.md` — add `ll-logs stats` to ll-logs and ll-ctx-stats entries

### Configuration
- N/A

## Implementation Steps

1. Aggregate per-skill invocation counts from the shared extractor.
2. Attribute adjacent failures and corrections to the preceding invocation.
3. Table + `--json`; `--sort` flag.
4. Tests over a fixture corpus.

## Success Metrics

- Output identifies the top-N invoked skills and the top-N by correction rate.

## Scope Boundaries

Out of scope:
- Real-time or live dashboards (batch aggregation only)
- Collecting new session data — reads existing logs via the shared extractor (ENH-1919)
- Automatic remediation of low-quality skills
- Visual/chart output — tabular text + `--json` only
- Non-ll CLI tools; aggregation is scoped to ll skill/command invocations

## API/Interface

`ll-logs stats` — new read-only aggregation subcommand.

## Impact

- **Priority**: P3 — Foundational observability for EPIC-1918; blocks dead-skill detection (ENH-1923) but not critical-path
- **Effort**: Small — adds one subcommand to `cli/logs.py` reusing existing extractors and `is_correction()`
- **Risk**: Low — read-only aggregation; no writes to session data or issue files
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/API.md` (ll-logs, ll-ctx-stats)

## Session Log
- `/ll:format-issue` - 2026-06-04T03:09:55 - `9b934de1-4aab-4e21-b930-1823687cb2b1.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
