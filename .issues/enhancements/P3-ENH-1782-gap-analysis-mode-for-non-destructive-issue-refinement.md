---
id: ENH-1782
title: Gap-analysis mode for non-destructive issue refinement
type: enh
status: open
priority: P3
captured_at: "2026-05-29T02:23:45Z"
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
  - issues
  - refinement
  - captured
---

# ENH-1782: Gap-analysis mode for non-destructive issue refinement

## Summary

Add a non-destructive, additive-only gap-analysis mode to `/ll:refine-issue` that inventories current coverage, identifies gaps, reports them with priorities, and applies only additive changes — never removing existing content. Modeled after CLI-Anything's `/refine` command.

## Current Behavior

`/ll:refine-issue` rewrites issues with codebase-driven research, which can lose valuable human-written content, acceptance criteria, or implementation notes that were already in the issue. There's no "fill gaps only" mode.

## Expected Behavior

A gap-analysis refinement mode that:
1. **Inventories** current coverage — what sections, criteria, and implementation details already exist
2. **Analyzes** the codebase for what's missing (missing files in Integration Map, missing edge cases in acceptance criteria, stale anchor references)
3. **Presents** a prioritized gap report to the user
4. **Applies** only additive changes with user confirmation — fills gaps, never removes content
5. **Verifies** existing tests still pass / existing content is preserved

Core contract: "Refine never removes existing content — it only adds or enhances."

## Motivation

CLI-Anything's `/refine` command demonstrates that additive-only refinement builds user trust — the user knows running refinement won't destroy their work. Current `/ll:refine-issue` carries risk of content loss, which discourages iterative refinement. A gap-analysis mode makes refinement safe to run repeatedly, steadily improving issue quality over time.

## Proposed Solution

Add a `--gap-analysis` flag to `/ll:refine-issue` (or make it the default behavior, with `--full-rewrite` for the legacy mode). The gap-analysis flow:

1. **Parse** the existing issue into a section map
2. **Check** each section against codebase reality:
   - Integration Map: are there referenced files that don't exist? Missing callers?
   - Proposed Solution: are anchor references (function/class names) still valid?
   - Implementation Steps: do they cover all files identified in Integration Map?
   - Acceptance Criteria: are edge cases covered based on code paths?
3. **Score** each gap by impact (critical / high / medium / low)
4. **Report** findings to user with specific suggestions
5. **Apply** approved additions via Edit (append-only)

## Integration Map

### Files to Modify
- `skills/refine-issue/SKILL.md` — add gap-analysis flow instructions
- `scripts/little_loops/issue_ops/` — gap analysis logic if implemented in Python

### Dependent Files (Callers/Importers)
- `ll-auto`, `ll-parallel`, `ll-sprint` — orchestrators that invoke refinement

### Similar Patterns
- CLI-Anything `commands/refine.md` — the reference implementation for gap-analysis flow

### Tests
- `scripts/tests/test_refine_issue.py` — test that gap-analysis preserves existing content, only appends

### Documentation
- Update `/ll:refine-issue` skill description

## Implementation Steps

1. Study CLI-Anything's `/refine` command for the gap-analysis flow pattern
2. Design the section-map data structure for parsing existing issues
3. Update `/ll:refine-issue` SKILL.md with the gap-analysis flow
4. Add `--gap-analysis` flag detection and routing
5. Implement gap checks: integration map staleness, anchor reference validity, edge case coverage
6. Add tests verifying content preservation and additive-only changes

## Impact

- **Priority**: P3 — Not blocking, but improves refinement safety and encourages iterative use
- **Effort**: Medium — New flow design + implementation in skill instructions and/or Python
- **Risk**: Low — Additive mode is opt-in (via flag); existing refinement behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `issues`, `refinement`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-05-29T02:23:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8b24cba6-684e-4420-9519-de98c8b4822b.jsonl`

---

**Open** | Created: 2026-05-29 | Priority: P3
