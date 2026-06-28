---
id: BUG-2375
title: recursive-refine 'skipped-decision.txt' is misnamed — decision-needed issues
  are still implemented; rename and document the policy
type: BUG
status: open
priority: P3
captured_at: '2026-06-28T00:00:00Z'
discovered_date: '2026-06-28'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- naming
- docs
relates_to:
- BUG-2374
---

# BUG-2375: recursive-refine 'skipped-decision.txt' is misnamed and undocumented

## Summary

`recursive-refine.check_decision_needed` (`recursive-refine.yaml:538-544`) writes
an issue ID to `recursive-refine-skipped-decision.txt` when the issue carries
`decision_needed: true`. The filename implies the issue was **skipped**, but the
write happens *after* the issue already passed confidence and was appended to
`recursive-refine-passed.txt` (lines 260/491). So the issue still flows into
`implement-issue-chain` and gets implemented — the `-skipped-decision.txt` file
is only an informational sidecar, not a skip.

In the `2026-06-28` audit, FEAT-370 appeared in
`recursive-refine-skipped-decision.txt` yet `record_implemented` fired for it.
That is the **expected** behavior (it passed confidence), but the "skipped"
naming makes it read like a bug — a decision-gate miss that was nonetheless
implemented without review.

## Root Cause

- **File**: `scripts/little_loops/loops/recursive-refine.yaml`
- **Anchor**: `check_decision_needed` (line ~538); the `decision` sidecar write
- **Cause**: the file is named with a `skipped-` prefix despite recording issues
  that are *not* skipped. The decision gate only short-circuits the **size
  review** step, not implementation.

## Expected Behavior

Either (a) the file is renamed to a non-"skipped" name (e.g.
`recursive-refine-decision-needed.txt`) and the "issues here still proceed to
implementation" policy is documented, or (b) if review-before-implement was the
intent, a guard is added upstream so decision-needed issues are held back. The
audit's analysis points to (a): the issue legitimately passed confidence.

## Integration Map

### Files to Modify (option a — recommended)
- `scripts/little_loops/loops/recursive-refine.yaml` — rename the sidecar file
  and update the comment at `check_decision_needed`.
- `docs/guides/LOOPS_REFERENCE.md` — document that decision-needed issues that
  pass confidence still proceed to implementation; the sidecar is informational.

### Tests
- `scripts/tests/test_builtin_loops.py` — update any assertion referencing
  `recursive-refine-skipped-decision.txt` to the new name.

## Acceptance Criteria

- [ ] The decision sidecar file no longer carries a "skipped" name, OR the
      review-before-implement guard is added (decide which is intended first).
- [ ] The policy is documented in `LOOPS_REFERENCE.md`.
- [ ] Tests referencing the old filename are updated.

## Impact

- **Priority**: P3 — naming/clarity issue; no incorrect work is performed today.
- **Effort**: Small — rename + doc, or a small guard.
- **Risk**: Low.
- **Breaking Change**: No.

## Notes

Resolve the intent question first (is decision-needed-but-passed meant to proceed
to implementation?). The audit and the FSM both indicate yes. If so, this is a
pure rename + documentation task.

## Session Log
- `audit-loop-run` - 2026-06-28 - `.loops/audits/2026-06-28-sprint-refine-and-implement-audit.md`

---

## Status

**Open** | Created: 2026-06-28 | Priority: P3
