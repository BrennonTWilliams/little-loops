---
discovered_date: 2026-04-14
discovered_by: user-request
confidence_score: 100
outcome_confidence: 95
---

# ENH-1110: Remove `/ll:format-issue` step from recursive-refine sub-loop

## Summary

The built-in `refine-to-ready-issue` sub-loop unconditionally ran `/ll:format-issue` as the first state after `resolve_issue`, before `refine → wire → confidence-check`. This step added latency to every run of `recursive-refine`, `auto-refine-and-implement`, `sprint-refine-and-implement`, and `issue-refinement` without changing outcomes in practice — `/ll:refine-issue` already establishes the template structure it needs.

## Change

`scripts/little_loops/loops/refine-to-ready-issue.yaml`:
- Deleted the `format_issue` state (previously invoked `/ll:format-issue ${issue} --auto`).
- Rewired `resolve_issue.next` from `format_issue` → `check_lifetime_limit`.

`scripts/little_loops/loops/recursive-refine.yaml`:
- Updated the loop description from `format → refine → wire → confidence-check` to `refine → wire → confidence-check` so the documented flow matches behavior.

## Files Not Touched

- `skills/format-issue/` — the skill itself is preserved; it remains invocable directly by users and via `ll-issues next-action` / refine-status tooling. Only its automatic invocation inside the sub-loop was removed.
- `scripts/tests/test_builtin_loops.py` — no tests asserted `format_issue` existed in `refine-to-ready-issue.yaml`. The `format_issues` token in `TestIssueRefinementSubLoop.REMOVED_STATES` refers to an unrelated legacy state in `issue-refinement.yaml`.
- Docs — `LOOPS_GUIDE.md` and related docs describe `format-issue` as a standalone skill, not as part of the recursive-refine pipeline, so no doc edits were needed.

## Blast Radius

Because `recursive-refine` delegates to `refine-to-ready-issue` rather than owning its own format step, the removal also affects every other consumer of the sub-loop:
- `recursive-refine`
- `auto-refine-and-implement`
- `sprint-refine-and-implement`
- `issue-refinement`

This was the correct scope given the user's intent; forking the sub-loop to remove the step from `recursive-refine` alone would create drift without benefit.

## Verification

- `python -m pytest scripts/tests/test_builtin_loops.py -q` — **207 passed** (no regressions).
- Manual diff review of both loop YAML files confirmed state routing is intact and no orphaned references to `format_issue` remain.

## Related

- Plan file: `~/.claude/plans/whimsical-leaping-moon.md`
