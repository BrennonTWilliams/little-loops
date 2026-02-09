---
discovered_date: 2026-02-08
discovered_by: manual_review
---

# ENH-277: Add pre-implementation confidence check skill

## Summary

Add a confidence-check skill that gates implementation work. Before `/ll:manage_issue` begins coding, verify: no duplicate implementations exist, architecture compliance, root cause identified, issue is well-specified. Inspired by SuperClaude's confidence-check pattern. Claimed ROI: 100-200 tokens spent to save 5,000-50,000 on wrong-direction work.

## Current Behavior

`/ll:manage_issue` proceeds directly from planning to implementation. The `/ll:ready_issue` command validates the issue file format and content, but there is no check for implementation readiness — whether the codebase is prepared, whether the approach is sound, or whether duplicate work already exists.

## Expected Behavior

Create a `skills/confidence-check/SKILL.md` with a 5-point assessment:

1. **No duplicate implementations** — Search for existing code that already solves the problem
2. **Architecture compliance** — Verify the proposed approach fits existing patterns
3. **Root cause identified** — For bugs, confirm the actual cause is understood (not just symptoms)
4. **Issue well-specified** — Check that acceptance criteria, affected files, and scope are clear
5. **Dependencies satisfied** — Verify any blocking issues are resolved

### Scoring:
- **>=90%**: Proceed with implementation
- **70-89%**: Present alternatives and concerns, ask user to confirm
- **<70%**: Stop and ask user to address gaps before proceeding

### Relationship to `/ll:ready_issue`:
- `/ll:ready_issue` validates the issue file (format, required sections, content quality)
- `confidence-check` validates readiness to implement (codebase state, approach soundness)
- They are complementary, not overlapping

Integrate as a recommended step in `/ll:manage_issue` planning phase.

## Files to Modify

- New `skills/confidence-check/SKILL.md` — Skill definition with assessment criteria
- `commands/manage_issue.md` — Reference the confidence-check skill in the planning phase

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Low — skill is advisory, does not block by default

## Labels

`enhancement`, `skills`, `quality`

---

## Status

**Open** | Created: 2026-02-08 | Priority: P3
