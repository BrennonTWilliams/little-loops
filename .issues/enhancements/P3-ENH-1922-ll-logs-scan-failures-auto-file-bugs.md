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

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `scan-failures` subcommand

### Dependent Files (Callers/Importers)
- `skills/analyze_log/` — shares failure-clustering logic; this is the interactive generalization
- `/ll:capture-issue` — candidate sink (reuses dup detection / reopen flow)
- `session_store` correction path (ENH-1904) — sibling, not overlap

### Similar Patterns
- `skills/analyze_log/` — existing failure-clustering logic to generalize from
- ENH-1919 shared extractor — reuse for log record access

### Tests
- `scripts/tests/` — add fixture corpus with seeded failure records; cover nonzero exit detection, traceback detection, clustering, and false-positive suppression for expected-nonzero gates

### Documentation
- `docs/reference/API.md` — update `ll-logs` section with new subcommand

### Configuration
- N/A

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

```bash
ll-logs scan-failures [--project DIR | --all] [--window-days D] [--json] [--capture]
```

- `--project DIR` — restrict scan to a specific project's logs
- `--all` — scan all project logs
- `--window-days D` — limit to logs from last D days (default: all)
- `--json` — emit structured JSON candidates instead of human-readable text
- `--capture` — pipe candidates into `/ll:capture-issue` for automatic issue filing with duplicate detection

Output (text mode): one candidate block per `(tool, normalized-error-signature)` cluster.

## Impact

- **Priority**: P3 — Real tool failures currently leak undetected; not blocking but high signal value
- **Effort**: Medium — New subcommand reuses shared extractor (ENH-1919) and analyze_log clustering logic; new parts are error-signature normalization and the `--capture` sink
- **Risk**: Low — Additive new subcommand; no changes to existing `ll-logs` behavior or shared code paths
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/API.md` (ll-logs); `skills/` analyze_log

## Labels

`captured`, `ll-logs`, `bugs`, `automation`

## Status

**Open** | Created: 2026-06-04 | Priority: P3



---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1922 owns the per-invocation failure-classification layer (detection of nonzero exits, tracebacks, and correction signals) atop ENH-1919's shared extractor. ENH-1921 aggregates failure/correction rates from ENH-1922's classified output rather than re-implementing failure detection. ENH-1919's shared extractor provides the raw event stream without classification.

## Session Log
- `/ll:verify-issues` - 2026-06-05T22:34:32 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T05:19:22 - `8b34820d-ae67-4c39-b57a-ea2b07021501.jsonl`
- `/ll:format-issue` - 2026-06-04T03:11:09 - `52fea084-ccde-40de-a423-8dea32d03fdb.jsonl`
- `/ll:format-issue` - 2026-06-04T03:10:04 - `9b934de1-4aab-4e21-b930-1823687cb2b1.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`

## Verification Notes (2026-06-05)

- **Path correction needed**: Issue references `skills/analyze_log/` (lines 56, 61) but the actual
  command is at `.claude/commands/analyze_log.md`, not a skill directory.
- **Dependent Files** section references `skills/analyze_log/` — should be `.claude/commands/analyze_log.md`.
- All other references accurate; feature not yet implemented.
- `/ll:verify-issues` - 2026-06-05 - Feature still not implemented. Prior note about `skills/analyze_log/` vs `commands/analyze_log.md` path error remains uncorrected in issue body. The Integration Map and references to `skills/analyze_log/` should be updated to point to the command file at `.claude/commands/analyze_log.md`.
