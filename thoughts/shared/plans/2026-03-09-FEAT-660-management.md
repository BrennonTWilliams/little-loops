# FEAT-660: `/ll:review-loop` Slash Command — Implementation Plan

**Date**: 2026-03-09
**Issue**: `.issues/features/P3-FEAT-660-review-loop-slash-command.md`

## Summary

Implement the `/ll:review-loop` skill — an interactive FSM loop quality reviewer that detects structural, error-handling, configuration, and best-practice issues in `.loops/*.yaml` files.

## Research Findings

- `validate_fsm()` (`validation.py:194`) already covers: unreachable states, missing terminal, invalid state refs, evaluator required fields, operator validity, routing conflicts/missing, numeric range errors
- Format detection: `"paradigm" in spec AND "initial" not in spec` → paradigm format; else raw FSM
- `ll-loop validate <name>` surfaces ERRORs+WARNINGs to stdout
- Skills auto-discovered from `skills/` dir — no plugin.json changes needed
- `skills/create-loop/SKILL.md` is primary pattern to follow
- `skills/review-loop/reference.md` follows `skills/create-loop/reference.md` structure

## Files to Create/Modify

| Action | File |
|--------|------|
| CREATE | `skills/review-loop/SKILL.md` |
| CREATE | `skills/review-loop/reference.md` |
| CREATE | `scripts/tests/test_review_loop.py` |
| MODIFY | `docs/guides/LOOPS_GUIDE.md` — add `/ll:review-loop` to CLI Quick Reference table |
| MODIFY | `skills/create-loop/SKILL.md` — add cross-reference in Step 6 success messages |

## Implementation Phases

### Phase 0: Create directory ✓

### Phase 1: reference.md
Quality check catalog with severity levels and fix templates.

### Phase 2: SKILL.md
Interactive review workflow with 5 steps.

### Phase 3: docs/guides/LOOPS_GUIDE.md
Add `/ll:review-loop` to Further Reading and Skills table.

### Phase 4: skills/create-loop/SKILL.md
Add `/ll:review-loop` cross-reference in success message.

### Phase 5: tests/test_review_loop.py
Test that validate_fsm() detects the issues claimed in reference.md.

## Success Criteria

- [ ] `skills/review-loop/SKILL.md` exists with full interactive workflow
- [ ] `skills/review-loop/reference.md` exists with all check categories
- [ ] `docs/guides/LOOPS_GUIDE.md` updated with `/ll:review-loop` entry
- [ ] `skills/create-loop/SKILL.md` updated with cross-reference
- [ ] `scripts/tests/test_review_loop.py` exists with TestReviewLoopChecks, TestReviewLoopAutoFix, TestReviewLoopDryRun
- [ ] Tests pass
