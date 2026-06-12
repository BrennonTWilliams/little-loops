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

## Current Behavior

`ll-ctx-stats` reports per-tool context-savings analysis only. The `ll-logs
stats --json` output — correction rate and per-skill/command invocation
frequency (built in ENH-1921) — is not consumed by any analytics-facing
command; the data exists in the log index but is not surfaced alongside context
savings.

## Expected Behavior

`ll-ctx-stats` surfaces skill-health signals (per-skill invocation frequency
and correction rate) alongside existing context-savings analysis, sourced from
`ll-logs stats --json`. When `ll-logs` data is unavailable (no session logs,
empty index), the skill-health section is omitted gracefully with a notice;
exit code is unchanged.

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

## Scope Boundaries

- **In scope**: New output section or `--with-skill-health` flag in `ll-ctx-stats`; graceful degradation when log data is absent; `--help` text and guide documentation updates; tests for merged output and degradation path
- **Out of scope**: Changes to `ll-logs stats` output format or schema; new standalone CLI tools; modifying existing context-savings logic; changes to any other EPIC-1918 child issues

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/ctx_stats.py` (or equivalent module) — consume
  `ll-logs stats --json`

### Dependent Files (Callers/Importers)
- TBD — use `grep -r "ctx.stats\|ll.ctx.stats" scripts/` to find callers

### Similar Patterns
- `ll-logs stats --json` output shape (ENH-1921)
- Existing graceful-degradation guards in history.db consumers

### Tests
- `scripts/tests/` — add/update ctx-stats tests for merged output and degradation path

### Documentation
- CLI `--help` text for `ll-ctx-stats`
- Relevant guide (e.g., `docs/guides/` or `CLAUDE.md` CLI entry for `ll-ctx-stats`)

### Configuration
- N/A

## Implementation Steps

1. Read `ll-logs stats --json` output from `ctx_stats.py` (subprocess or import)
2. Add a skill-health section (or `--with-skill-health` flag) to the `ll-ctx-stats` report
3. Implement graceful degradation when `ll-logs` data is unavailable or the index is empty
4. Update `--help` text and the relevant guide with the new output section
5. Write tests covering merged output and the degradation path

## Impact

- **Priority**: P3 — closes a named consumer-target gap in EPIC-1918
- **Effort**: Small — JSON merge into an existing report
- **Risk**: Low — additive output section
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-12 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-12T19:18:07 - `2606c3f7-295a-4177-a5bc-08603aa89e55.jsonl`
