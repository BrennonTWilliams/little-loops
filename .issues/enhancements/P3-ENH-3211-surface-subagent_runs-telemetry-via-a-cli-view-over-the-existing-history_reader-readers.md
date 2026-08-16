---
id: ENH-3211
type: ENH
title: Surface subagent_runs telemetry via a CLI view over the existing history_reader
  readers
priority: P3
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T02:10:42Z'
relates_to:
- ENH-3210
---

# ENH-3211: Surface subagent_runs telemetry via a CLI view over the existing history_reader readers

## Summary

ENH-2505 added `subagent_runs` plus three readers in `history_reader.py` —
`subagent_tree` (`:1573`), `subagent_retries` (`:1615`), and `subagent_budget`
(`:1655`) — but nothing consumes them. A repo-wide search finds the only callers in
`scripts/tests/test_enh_2505_subagent_runs.py`; no CLI exposes them, and neither
`ll-auto` nor the FSM executor reads the table. The data is write-only telemetry.

Consequence: answering "how many subagents did this run spawn, and did they all
finish?" requires a manual `sqlite3 .ll/history.db` query. Orphan rate (see the
companion stale-row reconciliation issue) is invisible, as is per-agent retry churn
and time budget — all three of which the readers already compute.

Proposed solution: a read-only CLI view over the existing readers, following the
established `ll-logs` / `ll-history` subcommand patterns rather than adding a new
entry point. Sketch:

- `ll-logs subagents --session <id>` — the spawn tree for one session
  (`subagent_tree`), showing agent_type, duration, status
- `--agent <type>` — repeat-spawn/retry rollup (`subagent_retries`)
- `--budget` — per-session spawn count and summed duration (`subagent_budget`)
- `--json` for machine consumption, matching sibling commands

Scope note: this issue is the surface only — it must not change the writers, the
hooks, or the schema. Which of `ll-logs` vs `ll-history` is the right host, and the
exact flag names, are implementation decisions to settle against the existing CLI
surface (`docs/reference/CLI.md`) before writing code.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:capture-issue` - 2026-08-16T02:10:52 - `3b0498bf-ef93-4aa9-88c2-660ecc956b99.jsonl`
