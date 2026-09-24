---
id: ENH-3576
type: ENH
title: Format-check repair coverage for missing and boilerplate sections with format-issue
  fallback
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:14Z'
parent: EPIC-3565
---

# ENH-3576: Format-check repair coverage for missing and boilerplate sections with format-issue fallback

## Summary

`refine-to-ready-issue`'s normalization step runs `ll-issues format-check <ID> --fix --apply`
and tolerates failure with `|| true`. `format_check._REPAIR_DISPATCH` repairs exactly six gap
classes: `prose_dep_drift`, `duplicate_findings_block`, `duplicate_heading`,
`empty_provenance_stub`, `template_placeholders` (derivable tokens only) and
`duplicate_session_log`. Missing or renamed sections, empty sections and boilerplate have no
deterministic repair, and the closure never invokes `/ll:format-issue`. Refinement and
ready-issue may incidentally repair some gaps, but there is no guaranteed
check → apply → recheck cycle.

## Current Behavior

A structurally malformed issue can reach expensive research and scoring with gaps that no
step is responsible for repairing.

## Expected Behavior

1. Deterministic check
2. Apply supported repairs
3. Recheck
4. Invoke `/ll:format-issue` only for remaining template gaps
5. Author missing substantive content via the appropriate skill
6. Recheck

Run this before expensive research when structure is malformed, and again after
content-changing repairs. Advisory template preferences stay distinct from implementation
blockers.

## Motivation

Malformed structure is cheap to detect and fix deterministically. Leaving it to incidental repair during expensive research wastes budget and lowers score quality.

## Proposed Solution

- Add a `recheck_format` state after `format-check --fix --apply` that reads the remaining
  gap classes from `format-check --json`.
- On remaining `missing`/`boilerplate` in directive sections (at least `Summary` and
  `Acceptance Criteria`, matching Phase 1.8's allowlist), conditionally run
  `/ll:format-issue <ID> --auto`, bounded once per issue per run.
- Consider adding a deterministic `missing` fixer that inserts empty template headings for
  ceremonial sections.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — normalization step
- `scripts/little_loops/cli/issues/format_check.py` — `_REPAIR_DISPATCH` (optional new fixer)

### Dependent Files (Callers/Importers)
- `skills/confidence-check/SKILL.md` Phase 1.8 (`STRUCT_GAP`), corrected in BUG-3570

### Similar Patterns
- Existing `_fix_*` fixers in `format_check.py`

### Tests
- `scripts/tests/test_ll_issues_format_check.py`, `scripts/tests/test_builtin_loops.py`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `recheck_format` after `format-check --fix --apply` in refine-to-ready-issue
2. Conditionally run `/ll:format-issue --auto` once for remaining directive gaps
3. Optionally add a ceremonial-`missing` heading inserter to `_REPAIR_DISPATCH`
4. Tests for the conditional format-issue route

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Low

## Acceptance Criteria

- [ ] A remaining directive-section `missing` gap after `--fix` triggers one `/ll:format-issue` pass
- [ ] Normalization no longer silently swallows an unrepaired directive gap

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3
