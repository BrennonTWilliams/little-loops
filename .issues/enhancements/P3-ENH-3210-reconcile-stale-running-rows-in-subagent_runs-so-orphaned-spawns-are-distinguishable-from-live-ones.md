---
id: ENH-3210
type: ENH
title: Reconcile stale running rows in subagent_runs so orphaned spawns are distinguishable
  from live ones
priority: P3
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T02:10:41Z'
relates_to:
- ENH-3211
---

# ENH-3210: Reconcile stale running rows in subagent_runs so orphaned spawns are distinguishable from live ones

## Summary

`subagent_runs` rows are opened `running` by the SubagentStart hook
(`scripts/little_loops/hooks/subagent_start.py` -> `session_store/writers.py:1800`) and
closed by SubagentStop (`hooks/subagent_stop.py` -> `writers.py:1855`). When the Stop
hook never fires — the common case when the parent `claude -p` turn ends and
`_kill_process_group` reaps the process group (`subprocess_utils.py:630-645`) — the row
stays `running` forever.

Live evidence from this repo's `.ll/history.db`:

    completed | 2699
    running   |   40      # oldest started 2026-08-02

Those 40 rows are indistinguishable from a genuinely in-flight agent, which makes any
future consumer of this table (see the companion telemetry-surface issue) report a
false picture.

`_backfill_subagent_runs` (`writers.py:2063`) does not help: it is `INSERT OR IGNORE`,
so it seeds missing rows but never corrects an existing stale one.

Proposed fix: reconcile on read and/or at session end, mirroring the ENH-1669 loop-run
reconciliation that rewrites a `running` loop state to `interrupted` when its PID is
provably dead. Here the liveness signal is the parent session: a `running` row whose
`parent_session_id` has an ended session (or whose `started_at` is older than a
threshold with no matching live session) becomes `orphaned` with a `reconciled_at`
stamp. Keep it best-effort per the EPIC-1707 contract — never raise, never block.

Decide as part of implementation whether `orphaned` is a new status value or whether
the existing `status` column reuses an established term, and whether reconciliation
runs in the SessionEnd handler (mind the hard-ceiling bug noted in
`hooks/subagent_stop.py`'s docstring) or lazily at query time in `history_reader`.


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
