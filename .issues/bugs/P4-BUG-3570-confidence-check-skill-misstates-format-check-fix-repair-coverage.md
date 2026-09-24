---
id: BUG-3570
type: BUG
title: Confidence-check skill misstates format-check --fix repair coverage
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:12Z'
parent: EPIC-3565
---

# BUG-3570: Confidence-check skill misstates format-check --fix repair coverage

## Summary

`skills/confidence-check/SKILL.md` Phase 1.8 (`STRUCT_GAP`, ENH-3257) said `format-check
--fix` repairs `boilerplate` and inserts `missing` sections, and that `template_placeholders`
has no `--fix`. Both claims were backwards against `format_check._REPAIR_DISPATCH`. That table
has no fixer for `boilerplate` or `missing`. `_fix_template_placeholders` does fill the four
frontmatter-derivable placeholder tokens (Priority, Status date, type label). The test
`test_phase_1_8_documents_remedy_split` pinned the wrong wording.

## Current Behavior

Before the fix, the scorer was told structural gaps are auto-repairable when they are not,
and that placeholders have no repair when some do.

## Expected Behavior

The doc matches the dispatch table.

## Steps to Reproduce

1. Read `skills/confidence-check/SKILL.md` Phase 1.8 (pre-fix, commit `958bf1f90`)
2. Compare with `format_check._REPAIR_DISPATCH`: no fixer for `boilerplate`/`missing`; `_fix_template_placeholders` exists

## Motivation

The scorer used this guidance to decide whether structural gaps are self-healing. Wrong guidance hides real gaps (tracked in ENH-3576).

## Proposed Solution

Correct the Phase 1.8 remedy sentence to match `_REPAIR_DISPATCH`. Implemented; see Resolution.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 1.8
- `.gemini/`, `.kimi-code/`, `.qwen/` skill mirrors

### Dependent Files (Callers/Importers)
- N/A — loop-internal routing

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_confidence_check_skill.py` — `test_phase_1_8_documents_remedy_split`
- `scripts/tests/test_enh494_skill_companions.py` — line cap

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Rewrite the Phase 1.8 remedy sentence within the 500-line cap
2. Update `test_phase_1_8_documents_remedy_split`
3. Run `ll-adapt --host gemini|kimi-code|qwen --apply`

## Impact

- **Priority**: P4
- **Effort**: Small
- **Risk**: Low

## Root Cause

- **File**: `skills/confidence-check/SKILL.md`, Phase 1.8
- **Cause**: the doc text predated or diverged from ENH-3247/ENH-3248's dispatch table

## Resolution

Rewrote the remedy sentence (kept at 4 lines so the skill stays at the 500-line cap):
`boilerplate`/`missing` have no `--fix` repair (`/ll:format-issue` inserts missing sections);
`--fix` fills only the frontmatter-derivable `template_placeholders` tokens. Updated
`test_phase_1_8_documents_remedy_split` in `test_confidence_check_skill.py` to assert the
corrected claims, and re-ran `ll-adapt --apply` for the gemini, kimi-code and qwen mirrors.
The first rewrite landed in `9a5d0f523`. The 4-line version, test update and mirrors were
uncommitted at capture time.

The underlying gap (no repair path for `missing`/`boilerplate`) is tracked in ENH-3576.

## Acceptance Criteria

- [x] Phase 1.8 matches `_REPAIR_DISPATCH`
- [x] `SKILL.md` ≤ 500 lines; mirrors synced

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P4
