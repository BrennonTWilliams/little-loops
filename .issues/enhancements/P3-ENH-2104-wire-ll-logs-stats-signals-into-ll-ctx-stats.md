---
id: ENH-2104
title: Wire `ll-logs stats` signals into `ll-ctx-stats`
type: ENH
priority: P3
status: open
captured_at: "2026-06-12T00:00:00Z"
discovered_date: 2026-06-12
discovered_by: review-epic
parent: EPIC-1918
relates_to: [ENH-1921]
labels:
  - telemetry
  - ll-logs
  - ctx-stats
  - integration
---

# ENH-2104: Wire `ll-logs stats` signals into `ll-ctx-stats`

## Summary

Extend `ll-ctx-stats` to report skill-health signals — correction rate and
skill/command invocation frequency — sourced from `ll-logs stats --json`, so
the per-tool context-savings analysis and the telemetry layer surface in a
single command.

## Motivation

EPIC-1918's scope section names `ll-ctx-stats` as an integration consumer
target ("Integration wiring into existing consumers: loop-suggester,
create-eval-from-issues/ll-harness, find-dead-code, ll-ctx-stats"), but no
child issue covers it. ENH-1921 (done) built the `stats` subcommand that
produces the data; nothing consumes it from the analytics side.

## Acceptance Criteria

- [ ] `ll-ctx-stats` gains a section (or `--with-skill-health` flag) showing
  per-skill invocation frequency and correction-rate signals from
  `ll-logs stats --json`
- [ ] Graceful degradation when `ll-logs` data is unavailable (no session
  logs, empty index) — section is omitted with a notice, exit code unchanged
- [ ] Output documented in the CLI `--help` text and the relevant guide
- [ ] Tests cover the merged output and the degradation path

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/ctx_stats.py` (or equivalent module) — consume
  `ll-logs stats --json`
- Tests for the ctx-stats CLI

### Similar Patterns
- `ll-logs stats --json` output shape (ENH-1921)
- Existing graceful-degradation guards in history.db consumers

## Impact

- **Priority**: P3 — closes a named consumer-target gap in EPIC-1918
- **Effort**: Small — JSON merge into an existing report
- **Risk**: Low — additive output section
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-12 | Priority: P3
