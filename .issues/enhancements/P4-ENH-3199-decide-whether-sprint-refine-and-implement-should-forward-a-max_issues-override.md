---
id: ENH-3199
type: ENH
title: Decide whether sprint-refine-and-implement should forward a max_issues override
priority: P4
status: open
testable: true
discovered_by: ll-issues-create
relates_to: [BUG-3191]
discovered_date: '2026-08-15'
captured_at: '2026-08-15T19:45:21Z'
---

# ENH-3199: Decide whether sprint-refine-and-implement should forward a max_issues override

## Summary

LOOPS_REFERENCE.md documented a `max_issues` context variable for sprint-refine-and-implement that has no effect: the loop YAML declares only `sprint_name` and `skip_learning_gate`, and its `with:` block forwards neither, so the child auto-refine-and-implement always uses its own default of 100. BUG-3191 deleted the doc paragraph rather than wiring the knob. This issue is the decision on whether the knob is wanted at all.

## Problem

`docs/guides/LOOPS_REFERENCE.md` documented a `max_issues` context variable
(default 100) for `sprint-refine-and-implement`. It does nothing:

- `sprint-refine-and-implement.yaml` declares only `sprint_name` and
  `skip_learning_gate` in its context block.
- Its `with:` block forwards neither `max_issues` nor anything that would reach
  the child's own `max_issues` (`auto-refine-and-implement.yaml`).

So `--context max_issues=10` on the sprint alias is silently ignored and the
child's default of 100 applies. BUG-3191 deleted the doc paragraph rather than
wiring the knob, because wiring it is a YAML behavior change and was out of
scope for a doc-only sweep. This issue carries the open question forward.

## Current Behavior

`sprint-refine-and-implement.yaml` declares exactly two context variables —
`sprint_name` and `skip_learning_gate` — and its `with:` block forwards neither
`max_issues` nor anything reaching the child's own `max_issues`. Passing
`--context max_issues=10` on the sprint alias is accepted by the CLI, silently
ignored by the loop, and the child `auto-refine-and-implement` applies its own
default of 100.

The doc that advertised the knob was removed by BUG-3191, so nothing currently
promises behavior that does not exist. The asymmetry between the two loops
remains.

## Expected Behavior

Either the knob works end to end — `--context max_issues=N` on the sprint alias
caps the child's issue set at N — or the decision not to have it is recorded, so
the next reader of the two YAMLs does not re-open the question.

## Program Design

No new Python symbols. Two YAML edits in
`scripts/little_loops/loops/sprint-refine-and-implement.yaml`, plus a test.

### Signatures

`test_sprint_alias_forwards_max_issues(tmp_path: Path) -> None` — assert that running the sprint alias with `max_issues=N` in context reaches the `auto-refine-and-implement` sub-loop as N, and that omitting it yields the child's default of 100.

### Call Path

`ll-loop run sprint-refine-and-implement --context max_issues=N` -> FSM context
-> `delegate` state -> `with:` block (`sprint-refine-and-implement.yaml`) ->
**forwarding gap** (the missing step) -> `auto-refine-and-implement` ->
`resolve_set` -> `ll-issues next-issues` capped at the child's own `max_issues`.

Wiring the knob means declaring `max_issues` in the parent's context block with
default `100` and adding it to the `with:` block, so the value survives the
delegate hop instead of dying at it.

## Scope Boundaries

**In scope**: the decision; if implemented, the two YAML lines in
`sprint-refine-and-implement.yaml`, the forwarding test, and restoring the
`LOOPS_REFERENCE.md` paragraph.

**Out of scope**:
- `auto-refine-and-implement.yaml`'s own `max_issues` default of 100 — unchanged either way.
- Any other unforwarded context variable between the two loops; if the audit turns up more, they are separate issues, not scope creep here.
- Re-adding the doc paragraph unless the knob is actually wired. A documented no-op knob is the defect BUG-3191 removed.

## Proposed Solution

The default action is **do nothing and close.** Nobody has reported wanting this
override, the child already caps at 100, and a sprint's issue set is normally
bounded by the sprint definition rather than by this cap — which is likely why
the gap went unnoticed long enough for the doc to drift.

Implement only if a concrete need appears. If it does:

1. Declare `max_issues` in `sprint-refine-and-implement.yaml`'s context block
   with a default matching the child's (`100`), so behavior is unchanged when
   the knob is not passed.
2. Forward it through the `with:` block to the `auto-refine-and-implement`
   sub-loop.
3. Restore the doc paragraph in `LOOPS_REFERENCE.md` — this time describing a
   knob that works.

Do **not** implement by giving the sprint alias a different default from the
child; a silently divergent cap between a loop and its sub-loop is worse than
no knob.

## Acceptance Criteria

- [ ] A decision is recorded: wire it, or close as won't-fix with the rationale.
- [ ] If wired: `ll-loop run sprint-refine-and-implement --context max_issues=N` demonstrably caps the child's issue set at N, covered by a test.
- [ ] If wired: the default is `100`, matching `auto-refine-and-implement.yaml`, so an unset knob changes nothing.
- [ ] If wired: `LOOPS_REFERENCE.md` documents it again; if closed, the doc stays silent.
- [ ] `ll-loop validate sprint-refine-and-implement` passes.

## Motivation

A documented knob that does nothing is worse than an undocumented one: a user who
passes `--context max_issues=10` reasonably believes they capped the run, and
gets 100. The doc is now correct by omission, but the asymmetry between the two
loops remains and will prompt the same question again. Settling it closes the
loop.

## Impact

- **Priority**: P4 — no defect now that the doc no longer promises the knob. This is a design question, not a bug.
- **Effort**: Small — two YAML lines plus a test, if implemented at all.
- **Risk**: Low — additive with a default matching current behavior.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-15 | Priority: P4
