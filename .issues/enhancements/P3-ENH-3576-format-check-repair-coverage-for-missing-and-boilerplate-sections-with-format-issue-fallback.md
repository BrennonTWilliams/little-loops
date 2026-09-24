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

[Why this issue matters - business value, user impact, technical debt cost]

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
