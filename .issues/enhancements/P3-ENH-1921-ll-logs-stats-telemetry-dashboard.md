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

- `ll-ctx-stats`: optional cost column join.
- `session_store.is_correction()`: correction detection reuse.
- Feeds ENH-1923 (dead-skill detection).

## Implementation Steps

1. Aggregate per-skill invocation counts from the shared extractor.
2. Attribute adjacent failures and corrections to the preceding invocation.
3. Table + `--json`; `--sort` flag.
4. Tests over a fixture corpus.

## Success Metrics

- Output identifies the top-N invoked skills and the top-N by correction rate.

## API/Interface

`ll-logs stats` — new read-only aggregation subcommand.

## Impact

Provides the observability baseline the rest of the EPIC builds on.

## Related Key Documentation

- `docs/reference/API.md` (ll-logs, ll-ctx-stats)

## Labels

captured, ll-logs, telemetry

## Status

open

## Session Log
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
