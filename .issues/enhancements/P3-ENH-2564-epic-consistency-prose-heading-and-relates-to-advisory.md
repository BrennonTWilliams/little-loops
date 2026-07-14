---
type: ENH
id: ENH-2564
title: "epic-consistency recognizes ### FEAT-NNN prose headings and downgrades relates_to membership to advisory"
priority: P3
status: done
created: 2026-07-09
completed_at: 2026-07-09T18:30:00Z
discovered_by: confidence-check-followup
relates_to:
- EPIC-2451
labels:
- issues
- tooling
- epics
---

# epic-consistency: prose-heading child recognition + relates_to advisory

## Summary

`ll-issues epic-consistency` (`scripts/little_loops/cli/issues/epic_consistency.py`)
mis-reported two things against EPIC-2451 and, more broadly, across the EPIC
backlog:

- **(a) Missing from body** — the body parser only recognized *bullet* child refs
  (`- FEAT-001`), so EPICs that document children as `### FEAT-NNNN —` prose
  headings (EPIC-2451 and 16 others) were reported as having undocumented
  children even though every child was documented richly.
- **(c) relates_to leaking membership** — any child that also appeared in the
  EPIC's `relates_to:` was flagged as failing drift. This fired on **32/48**
  EPICs, i.e. the near-universal, deliberate maintainer convention, making the
  check exit non-zero as noise.

This enhancement reconciles the checker with the established prose conventions.

## Impact

- `ll-issues epic-consistency` stops reporting false category-(a) drift on the 17
  EPICs that document children via prose headings, and stops failing on the
  near-universal `relates_to:` membership convention (32/48 EPICs) — the check now
  fails only on genuine drift, restoring its signal.
- EPIC-2451 goes green (exit 0) without any hand-edit to its rich `## Children`
  prose. No issue files were rewritten.

## Current Behavior

- `_parse_children_body()` scanned only `_BODY_BULLET_RE` (`^\s*[-*]\s+…`), so
  h3–h6 heading child docs were invisible → false category-(a) drift.
- `relates_to_is_child` was part of `EpicDrift.has_drift`, so a child listed in
  `relates_to:` forced a non-zero exit under a `(c) relates_to: leaking
  membership` label.
- `ll-issues epic-consistency EPIC-2451` exited **1** with 7×(a) + 9×(c) reports.

## Expected Behavior

- Added `_BODY_HEADING_RE` (`^\s*#{3,6}\s+\*{0,2}([A-Z]+-\d+)`, optional bold
  wrapper) and folded it into `_parse_children_body()` via `itertools.chain`
  alongside the existing bullet regex. Children documented as `### FEAT-NNNN —`
  or `### **FEAT-NNNN** —` now count as documented.
- Category (c) is downgraded from failing drift to a **non-failing advisory**:
  - `relates_to_is_child` removed from `has_drift`.
  - New `has_advisory` property (`sub_epic_advisory or relates_to_is_child`)
    gates the `— OK` line so advisories still print.
  - Output relabeled from `(c) relates_to: leaking membership` to
    `[advisory] relates_to lists child membership (parent: backref implies it)`.
  - `relates_to_is_child` field is **preserved in `--format json`** for
    backward compatibility.
- `ll-issues epic-consistency EPIC-2451` now exits **0**, surfacing only the
  advisory. No issue-file content was rewritten (`--fix` never run).

## Scope Boundaries

- **In scope**: body-parser heading recognition; (c) advisory downgrade; tests.
- **Out of scope**: the 16 EPICs still flagging genuine category-(a) drift
  (children truly undocumented in any format) — real drift, intentionally left
  flagged. No mass migration of `relates_to:` frontmatter. No `--fix` behavior
  change (still category-(a) only, still preserves prose).

## Files Modified

- `scripts/little_loops/cli/issues/epic_consistency.py`
  - `import itertools`
  - `_BODY_HEADING_RE` added; `_parse_children_body()` unions bullet + heading
    matches.
  - `has_drift` drops `relates_to_is_child`; new `has_advisory` property.
  - Text output: `— OK` guard uses `has_advisory`; (c) block relabeled
    `[advisory]`.
- `scripts/tests/test_epic_consistency.py`
  - `test_h3_heading_child_docs_recognized` (new) — h3/bold-h3 children clear (a).
  - `TestEpicConsistencyRelatesTo` rewritten: `test_relates_to_child_is_advisory_not_drift`
    (exit 0, advisory printed) + `test_relates_to_child_still_in_json`
    (JSON field preserved).

## Verification

- `python -m pytest scripts/tests/test_epic_consistency.py` → 29 passed.
- `python -m pytest scripts/tests/test_epic_consistency.py
  scripts/tests/test_issue_parser.py` → 215 passed.
- `python -m mypy scripts/little_loops/cli/issues/epic_consistency.py` → clean.
- `ruff check` (module + test) → clean.
- Live: `ll-issues epic-consistency EPIC-2451` exits 0 (was 1). `--all` (a) count
  17→16 (only EPIC-2451 used h3 style); 32 relates_to reports now advisory; 0
  old `(c)` labels remain.

## Decisions

- **Teach the checker prose headings** rather than migrate 17 EPIC bodies to
  bullets — preserves rich per-child scope prose. (User choice.)
- **Relax (c) to advisory** rather than mass-strip `relates_to:` across 32 EPICs
  — the child-in-`relates_to` listing is the deliberate maintainer convention.
  (User choice.)

## Status

Done — completed 2026-07-09. Implemented, tested (29 + 215 passing), type/lint
clean, and verified live against EPIC-2451 and `--all`.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-09T22:55:20 - `ea2fbe10-d783-4d4d-9ed3-f61386171d98.jsonl`

- 2026-07-09: Resumed from handoff (`/ll:resume`) documenting the EPIC-2451
  epic-consistency disagreement. Confirmed via `--all` that both categories are
  checker-wide, not EPIC-2451-specific. Implemented both reconciliations,
  verified, and recorded here. Related decomposition work (FEAT-2449 →
  FEAT-2561/2562/2563 under EPIC-2451) remains separately staged/uncommitted.
