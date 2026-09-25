---
id: FEAT-3584
type: FEAT
title: Brainstorm ground state with codebase and web evidence probes
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
---

# FEAT-3584: Brainstorm ground state with codebase and web evidence probes

## Summary

Add a gated `ground` state to the brainstorm engine that attaches evidence to ideas
before shortlisting, with **non-LLM probes** to reject unsupported ideas. Sources:
`none` (artifact/visual default), `codebase` (functional default), `web` (business
default).

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

- `codebase`: each idea must cite concrete anchors (file paths, symbols, issue IDs);
  a script verifies they exist (git-tracked files, `git grep` for symbols,
  `ll-issues show` for IDs) and flags conflicts with open issues.
- `web`: research competitors, prior art, and demand signals; each idea carries
  cited sources and an explicit assumption list.
- Ideas failing grounding are dropped or marked `ungrounded` and excluded from the
  tournament per profile policy.
- Skipped entirely when `ground=none`.

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

## Acceptance Criteria

- Codebase probes are deterministic and cover: missing file, missing symbol,
  unknown issue ID.
- Grounding results recorded per idea in `ideas.jsonl` (`evidence`, `grounded`).
- Core loop stays decoupled from the Issue system: issue-ID probing is only active
  when `.issues/` / `ll-issues` is available.
- Tests cover probe pass/fail with fixture ideas.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-25T00:33:44 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
