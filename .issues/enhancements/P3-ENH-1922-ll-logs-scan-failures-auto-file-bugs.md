---
id: ENH-1922
title: "ll-logs scan-failures: mine failed ll-* calls to auto-file bugs"
type: ENH
priority: P3
status: open
captured_at: "2026-06-04T02:27:34Z"
discovered_date: "2026-06-04"
discovered_by: capture-issue
parent: EPIC-1918
relates_to: [EPIC-1918, ENH-1904, ENH-1921]
labels: [captured, ll-logs, bugs, automation]
---

# ENH-1922: ll-logs scan-failures — mine failed ll-* calls to auto-file bugs

## Summary

Add `ll-logs scan-failures` to find `ll-*` Bash invocations in **interactive**
session logs that returned a nonzero exit or emitted a traceback, and propose
issue files (create/reopen) for them — generalizing the `analyze_log` skill from
ll-parallel/ll-auto runs to all sessions.

## Current Behavior

The `analyze_log` skill only inspects ll-parallel/ll-auto log files. Failures of
`ll-*` tools during ordinary interactive Claude Code sessions — captured in the
log corpus — are never mined, so tool bugs that surface in real use go unfiled.

## Expected Behavior

`ll-logs scan-failures [--project DIR|--all] [--window-days D] [--json]` scans
tool-use results for `ll-*` Bash calls with nonzero exit codes or Python
tracebacks, clusters them by tool + error signature, and emits candidate issues
(or feeds `/ll:capture-issue`). Distinct from ENH-1904, which mines user-*text*
corrections into history.db; this mines *tool failures*.

## Motivation

Real tool failures are the highest-signal bug source and currently leak away.
Closing this turns the log corpus into a passive bug detector for ll's own CLIs.

## Proposed Solution

Add `scan-failures` to `cli/logs.py` reusing the shared extractor (ENH-1919).
Detect nonzero exit / traceback in tool-use result records; cluster by
`(tool, normalized-error-signature)`; emit candidates. Optionally pipe into
`/ll:capture-issue` for file creation with duplicate detection.

## Integration Map

- `analyze_log` skill: shares failure-clustering logic; this is the interactive
  generalization.
- `/ll:capture-issue`: candidate sink (reuses dup detection / reopen flow).
- `session_store` correction path (ENH-1904): sibling, not overlap.

## Implementation Steps

1. Detect failure records (nonzero exit, traceback) for `ll-*` Bash calls.
2. Normalize + cluster by tool and error signature.
3. Emit candidates (text + `--json`); optional `--capture` to file via capture-issue.
4. Tests over a fixture corpus with seeded failures.

## Success Metrics

- Re-running over historical logs surfaces ≥1 real, previously-unfiled tool failure.
- No false-positive issue for an expected nonzero (e.g. `ll-verify-* exit 1` gates).

## Scope Boundaries

- In: failures of `ll-*` CLIs in interactive logs.
- Out: user-text correction mining (ENH-1904); ll-parallel/ll-auto logs (analyze_log).

## API/Interface

`ll-logs scan-failures` — new subcommand; `--capture` optional sink.

## Impact

Continuous, zero-effort bug discovery for ll's own tooling.

## Related Key Documentation

- `docs/reference/API.md` (ll-logs); `skills/` analyze_log

## Labels

captured, ll-logs, bugs, automation

## Status

open

## Session Log
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
