---
id: ENH-1243
type: ENH
priority: P3
title: "Add decide-issue conditional gate to autodev loop"
status: backlog
captured_at: "2026-04-21T23:34:57Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
---

# ENH-1243: Add decide-issue gate to autodev loop

## Summary

The `autodev` loop refines and implements issues end-to-end, but has no hook for issues
that carry `decision_needed: true` after refinement. Such issues currently fall through
to `implement_current` with an unresolved multi-option proposed solution, which produces
inconsistent or incorrect implementations. A conditional `decide_current` state should be
inserted between confidence-check and implementation so the `/ll:decide-issue` skill runs
exactly when — and only when — the flag is set.

## Current Behavior

After `check_passed` routes to `implement_current`, the loop calls `ll-auto --only <ID>`
regardless of whether the issue's frontmatter contains `decision_needed: true`. Issues
with competing implementation options are implemented without a winner being selected,
leaving the choice to the implementing agent at random.

## Expected Behavior

When `check_passed` (or `recheck_scores` / `recheck_after_size_review`) routes toward
implementation, the loop first checks whether the issue has `decision_needed: true`. If
so, it runs `/ll:decide-issue <ID> --auto`, which selects a winning option and clears the
flag. Only after that does it call `ll-auto --only <ID>`. Issues without the flag skip
the new state entirely with zero overhead.

## Motivation

`/ll:refine-issue --auto` deliberately sets `decision_needed: true` when it can't pick
between two valid approaches without codebase evidence. The `decide-issue` skill was
built to close that gap. Without a gate in `autodev`, the refinement → decision →
implementation pipeline is broken: the middle step is silently skipped, and the quality
guarantee of the whole loop degrades.

## Proposed Solution

Add a `decide_current` state to `autodev.yaml` positioned between all three
implementation-routing states and `implement_current`:

```
check_passed        → on_yes: decide_current   (was: implement_current)
recheck_scores      → on_yes: decide_current   (was: implement_current)
recheck_after_size_review → on_yes: decide_current (was: implement_current)

decide_current:
  action: |
    ISSUE_ID="${captured.input.output}"
    FLAG=$(ll-issues show "$ISSUE_ID" --json \
      | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('decision_needed','false'))")
    [ "$FLAG" = "true" ] && exit 0 || exit 1
  fragment: shell_exit
  on_yes: run_decide   # decision needed → run the skill
  on_no:  implement_current

run_decide:
  fragment: with_rate_limit_handling
  action: "/ll:decide-issue ${captured.input.output} --auto"
  action_type: slash_command
  next: implement_current
  on_error: implement_current        # degraded: proceed even if decide fails
  on_rate_limit_exhausted: done
```

The `on_error: implement_current` fallback ensures a decide-skill failure doesn't silently
drop the issue; it still gets implemented (with the unresolved options), which is no worse
than the current behavior.

## Integration Map

- **Modified**: `scripts/little_loops/loops/autodev.yaml`
  - States `check_passed`, `recheck_scores`, `recheck_after_size_review`: change
    `on_yes` target from `implement_current` to `decide_current`
  - New states: `decide_current`, `run_decide`
- **Consumed skill**: `skills/decide-issue/SKILL.md` — invoked via `run_decide`
- **Issue frontmatter field**: `decision_needed` (boolean) — read by `decide_current`
  check; cleared by `decide-issue` on success

## Implementation Steps

1. In `autodev.yaml`, update `on_yes` in `check_passed`, `recheck_scores`, and
   `recheck_after_size_review` to point to `decide_current`.
2. Add `decide_current` state (shell script that reads `decision_needed` from
   `ll-issues show --json` and exits 0/1).
3. Add `run_decide` state (slash command with rate-limit handling).
4. Write a unit test / eval case: issue with `decision_needed: true` should pass through
   `decide_current → run_decide → implement_current`; issue without the flag should
   skip straight to `implement_current`.

## Impact

- **Scope**: `autodev.yaml` only — two new states, three one-line routing changes
- **Risk**: Low — `on_error` fallback ensures no regressions for existing issues
- **Benefit**: Closes the refinement → decision → implementation pipeline gap; prevents
  under-specified issues from reaching the implementer

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/loops/autodev.yaml` | State machine being modified |
| `skills/decide-issue/SKILL.md` | Skill invoked by the new gate |

## Labels

loop, autodev, decide-issue, issue-pipeline

---

## Status

- [ ] Backlog
- [ ] In Progress
- [ ] Complete

## Session Log
- `/ll:capture-issue` - 2026-04-21T23:34:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b62f8c-b061-414c-9935-ffe01637b6ec.jsonl`
