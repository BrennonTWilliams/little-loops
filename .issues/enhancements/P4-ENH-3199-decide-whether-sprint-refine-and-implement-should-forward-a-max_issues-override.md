---
id: ENH-3199
type: ENH
title: Decide whether sprint-refine-and-implement should forward a max_issues override
priority: P4
status: cancelled
testable: true
discovered_by: ll-issues-create
relates_to:
- BUG-3191
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

- [x] A decision is recorded: wire it, or close as won't-fix with the rationale. — closed as won't-fix; see **Resolution**.
- [x] ~~If wired: `ll-loop run sprint-refine-and-implement --context max_issues=N` demonstrably caps the child's issue set at N, covered by a test.~~ — N/A, not wired.
- [x] ~~If wired: the default is `100`, matching `auto-refine-and-implement.yaml`, so an unset knob changes nothing.~~ — N/A, not wired.
- [x] If wired: `LOOPS_REFERENCE.md` documents it again; if closed, the doc stays silent. — closed; doc stays silent (BUG-3191's deletion stands).
- [x] `ll-loop validate sprint-refine-and-implement` passes. — verified 2026-08-15, exit 0 (the one WARNING is the child's deliberately-declined `required_inputs`, per `scripts/tests/test_builtin_loops.py:13852`).

## Resolution

**Closed as won't-fix, 2026-08-15.** Decision: do not forward `max_issues`.

The issue's own framing understated the problem — it described the value dying at
the delegate hop. The real blocker is one level deeper: **on the sprint path the
child never reads `max_issues` at all**, so forwarding it would still be a no-op.

`auto-refine-and-implement.yaml:127-158` reads `max_issues` in exactly one place,
the `else` branch of `resolve_set`:

```
if [ -n "${context.scope}" ]; then
  LIST=$(... SprintManager.load_or_resolve(arg) ...)   # no cap applied
else
  LIST=$(ll-issues next-issues | head -n ${context.max_issues} | ...)
fi
```

The sprint alias always takes the `if` branch:

- `sprint-refine-and-implement.yaml:13` — `required_inputs: ["sprint_name"]`
- `scripts/little_loops/cli/loop/run.py:321-322` enforces that pre-flight —
  present **and non-empty**, exit 1 otherwise
- the `delegate` `with:` block passes `scope: "${context.sprint_name}"`

So `scope` is non-empty by construction, the set comes from `SprintManager`
uncapped, and the `head -n ${context.max_issues}` line is unreachable from this
loop. Following the Proposed Solution's steps 1–2 would successfully forward the
value into a variable the active code path never interpolates: `--context
max_issues=10` would still yield the full sprint. That is the same defect
BUG-3191 removed from the docs, relocated into YAML — and step 3 would
re-introduce the identical false promise.

The asymmetry between the two loops is correct design, not a gap. A sprint's
issue set is defined by `.sprints/<name>.yaml` (or the EPIC's children);
`max_issues` exists only to bound the *unbounded* case — ranking the open
backlog. A cap that silently truncated an explicitly named sprint would be
surprising.

If a concrete need for capping a sprint ever appears, the honest implementation
is a cap applied **inside** the `if` branch of the child's `resolve_set`, with a
`truncated N→M` log line so the truncation is visible — a different and larger
change than context forwarding. File it fresh; do not reopen this.

`LOOPS_REFERENCE.md` stays silent on the knob, per the Scope Boundaries above.

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

**Cancelled** (won't-fix) | Created: 2026-08-15 | Closed: 2026-08-15 | Priority: P4
