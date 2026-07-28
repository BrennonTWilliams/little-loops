---
id: ENH-2775
status: open
priority: P3
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:26Z
discovered_by: audit-architecture
focus_area: large-files
labels:
- enhancement
- architecture
- refactoring
- auto-generated
parent: EPIC-2789
---

# ENH-2775: Split history_reader.py and fsm/executor.py along concern boundaries

## Summary

Architectural issue found by `/ll:audit-architecture`. Two more top-tier large
files sit just behind the worst offenders and are accreting unrelated
concerns.

## Location

- **File**: `scripts/little_loops/history_reader.py` — 3,099 lines, 88 defs
- **File**: `scripts/little_loops/fsm/executor.py` — 2,915 lines
- **Modules**: `little_loops.history_reader`, `little_loops.fsm.executor`

## Finding

### Current State

- `history_reader.py`: 88 top-level defs mixing JSONL parsing, session
  discovery, querying, and formatting in one flat module.
- `fsm/executor.py`: the core state-machine step loop plus retry/429 handling,
  context-handoff detection, and session-reuse continuity chains (FEAT-2711)
  in one file; it is among the most-edited files in the repo, so every feature
  lands in the same hot file.

### Impact

- **Development velocity**: both files are recurring merge-conflict hotspots.
- **Maintainability**: concern boundaries exist informally (region comments,
  naming prefixes) but not structurally.
- **Risk**: medium — executor changes for one feature (e.g. retry) can
  regress another (e.g. handoff) with no module boundary to flag the overlap.

## Proposed Solution

Split each along its existing seams, preserving public import paths via
re-exports.

### Suggested Approach

1. `history_reader` → package: `parsing.py` (JSONL/event decoding),
   `discovery.py` (session file location), `queries.py`, `formatting.py`.
2. `fsm/executor.py` → extract retry/backoff policy and
   session-reuse/handoff handling into sibling modules (`fsm/retry.py`,
   `fsm/session_continuity.py`), leaving the step loop in `executor.py`.
3. Full test suite green with no importer changes.

## Impact Assessment

- **Severity**: Medium
- **Effort**: Large
- **Risk**: Medium
- **Breaking Change**: No

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3
