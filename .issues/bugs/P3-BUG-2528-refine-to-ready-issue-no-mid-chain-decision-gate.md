---
id: BUG-2528
title: 'refine-to-ready-issue does not short-circuit on decision_needed: true set
  by mid-chain skills, wasting LLM budget on wire and confidence-check invocations'
type: BUG
priority: P3
status: open
discovered_date: 2026-07-07
discovered_by: capture-issue
decision_needed: false
---

# BUG-2528: `refine-to-ready-issue` does not short-circuit on `decision_needed: true` set by mid-chain skills

## Summary

The `refine-to-ready-issue` FSM loop (`scripts/little_loops/loops/refine-to-ready-issue.yaml`)
consults the `decision_needed` flag exactly once — at the `check_decision_needed`
state (line 197), reached only when `check_outcome` returns NO. If any of the
mid-chain skills (`/ll:refine-issue`, `/ll:wire-issue`, `/ll:confidence-check`)
sets `decision_needed: true`, the loop continues to run the remaining skills in
the chain anyway. The outer `autodev` loop's `check_decision_after_refine`
(`autodev.yaml:165`) eventually catches the flag and routes to `run_decide` —
but only after the sub-loop has already spent LLM budget on the wire and
confidence-check invocations that should have been skipped.

This is the budget analogue of the routing bug BUG-1366 fixed: BUG-1366 added
the late-chain `check_decision_needed` gate before `breakdown_issue`, but no
mid-chain gate exists to short-circuit between the three skill invocations.

## Current Behavior

The unconditional chain inside `refine-to-ready-issue.yaml`:

```
refine_issue (line 78)     → check_wire_done (line 88, unconditional)
refine_followup (line 91)  → check_wire_done (line 98, unconditional)
wire_issue (line 113)      → mark_wire_done (line 116, unconditional)
mark_wire_done (line 119)  → confidence_check (line 122, unconditional)
confidence_check (line 125)→ check_readiness (line 129, on_success)
check_readiness (line 133) → check_outcome (line 161, on_yes)
check_outcome (line 165)   → check_decision_needed (line 194, on_no)
```

`decision_needed` is consulted exactly once, at `check_decision_needed`
(line 197), and only when `check_outcome` returns NO (i.e., the outcome
score is below `commands.confidence_gate.outcome_threshold`).

If `/ll:refine-issue` or `/ll:wire-issue` sets `decision_needed: true`, the
flag is not re-checked until the very end of the chain. The remaining skills
(wire and/or confidence_check) still run. They see the flag but cannot
resolve it, so the only effect is wasted LLM budget.

The outer `autodev` loop's `check_decision_after_refine` (`autodev.yaml:165`)
catches the flag after the sub-loop returns, but it catches it AFTER the
wasted invocations, not instead of them.

## Expected Behavior

A `decision_needed: true` flag set by any of the three skills should
short-circuit the sub-loop at the next state boundary, routing to `done` so
the outer autodev loop's `check_decision_after_refine` can route to
`run_decide`. This matches:

- The existing pattern at `check_decision_needed` (line 197), which already
  routes to `done` on yes with the comment "Exit via done so autodev's
  check_decision_after_refine can route to run_decide."
- The `BUG-1366` precedent for putting decision gates on the sub-loop
  boundary.

Concretely:

- After `refine_issue` (or `refine_followup`), consult the flag. On yes →
  `done`. On no → `check_wire_done` (existing).
- After `mark_wire_done`, consult the flag. On yes → `done`. On no →
  `confidence_check` (existing).

The `refine-to-ready-wire-done` ledger already prevents wire from re-running
on a retry; the new decision gate must not re-fire on a retry refinement
either (single check per skill pass).

## Steps to Reproduce

1. Construct an issue that, after `/ll:refine-issue --auto`, has
   `decision_needed: true` set in frontmatter (e.g., the issue has
   competing options in `## Proposed Solution` and refine cannot choose).
2. Run `ll-loop run autodev` against that issue (or invoke
   `refine-to-ready-issue` directly via `ll-loop run refine-to-ready-issue
   --input ISSUE-NNN`).
3. Observe: after `refine_issue` returns with the flag set, the loop
   still proceeds to `wire_issue` and then `confidence_check`. The
   wire and confidence-check LLM invocations run on an issue that is
   blocked on a design decision.
4. Check the run log: refine-to-ready-issue returns `done` (with the
   `decision_needed` flag now set in frontmatter); the outer autodev
   loop's `check_decision_after_refine` then routes to `run_decide`.
   The wire and confidence-check invocations were wasted.

## Root Cause

Three unconditional `next:` arrows inside `refine-to-ready-issue.yaml` skip
the decision check:

- Line 88: `refine_issue.next: check_wire_done`
- Line 98: `refine_followup.next: check_wire_done`
- Line 116: `wire_issue.next: mark_wire_done` (and `:122`
  `mark_wire_done.next: confidence_check`)

The only consultation point, `check_decision_needed` (line 197), is reached
only when `check_outcome: on_no` (line 194). When outcome passes — e.g., the
issue scores well on most dimensions but has an unresolved decision — the
flag is never consulted inside the sub-loop, and the only catch is the outer
loop's post-sub-loop gate.

The BUG-1366 fix added the `check_decision_needed` state but did not add
mid-chain gates between the three skill invocations, because the original
bug report described the late-chain symptom (issue reaching breakdown_issue
without a decision check) rather than the mid-chain symptom (wasted budget
when the flag is set earlier in the chain).

## Proposed Solution

Insert two mid-chain `check_decision_mid` states that run
`ll-issues check-flag decision_needed`. Reuse the existing
`fragment: shell_exit` pattern from `check_decision_needed` (line 203) and
`check_decision_at_dequeue` (`autodev.yaml:110`).

### Part 1 — gate after refine (insert between `refine_issue`/`refine_followup` and `check_wire_done`)

```yaml
check_decision_after_refine:
  # Mid-chain gate: if /ll:refine-issue set decision_needed: true, skip the
  # remaining wire + confidence_check invocations and exit via done so the
  # outer autodev loop's check_decision_after_refine (autodev.yaml:165) can
  # route to run_decide. Mirrors check_decision_needed (line 197) pattern;
  # differs only in placement (mid-chain, not end-of-chain).
  action: "ll-issues check-flag ${captured.issue_id.output} decision_needed"
  fragment: shell_exit
  on_yes: done
  on_no: check_wire_done
  on_error: check_wire_done
```

Update line 88 (`refine_issue.next`) and line 98 (`refine_followup.next`) to
point to `check_decision_after_refine` instead of `check_wire_done`.

### Part 2 — gate after wire (insert between `mark_wire_done` and `confidence_check`)

```yaml
check_decision_after_wire:
  # Mid-chain gate: if /ll:wire-issue set decision_needed: true, skip the
  # confidence_check invocation. Same exit-via-done contract as Part 1.
  action: "ll-issues check-flag ${captured.issue_id.output} decision_needed"
  fragment: shell_exit
  on_yes: done
  on_no: confidence_check
  on_error: confidence_check
```

Update line 122 (`mark_wire_done.next`) to point to `check_decision_after_wire`
instead of `confidence_check`.

### Notes

- The new states do NOT need to consult the wire-done ledger; they only fire
  after a state that has already written to the ledger (`mark_wire_done`) or
  before it (`refine_issue`). The existing `refine-to-ready-wire-done` ledger
  still gates wire re-runs on a retry refinement unchanged.
- The new states do NOT execute `/ll:decide-issue` themselves — they only
  detect the flag and exit, matching the line 197 comment's reasoning
  ("Exit via done so autodev's check_decision_after_refine can route to
  run_decide"). `decide-issue` remains an outer-loop concern with its
  rate-limit handling, decidable-check, and deposit_options detour.
- A single `check_decision_after_refine` retry path is fine; the `refine_followup`
  → `check_decision_after_refine` transition is identical to the
  `refine_issue` → `check_decision_after_refine` transition.

## Location

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- **Anchors**:
  - Line 88: `refine_issue.next` change to `check_decision_after_refine`
  - Line 98: `refine_followup.next` change to `check_decision_after_refine`
  - Insert new `check_decision_after_refine` state (location: after
    `refine_followup`, before `check_wire_done`)
  - Line 122: `mark_wire_done.next` change to `check_decision_after_wire`
  - Insert new `check_decision_after_wire` state (location: after
    `mark_wire_done`, before `confidence_check`)

## Integration Map

### Files Modified

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — add two
  `check_decision_*` mid-chain states and re-route the three `next:`
  arrows that currently skip them (lines 88, 98, 122).

### Tests Added (`scripts/tests/test_loop_refine_to_ready.py` or analogous)

- `test_refine_sets_decision_needed_skips_wire` — stub `refine_issue` and
  `wire_issue` to set the flag; assert the loop reaches `done` after
  `refine_issue` without invoking `wire_issue` or `confidence_check`.
- `test_wire_sets_decision_needed_skips_confidence_check` — stub `wire_issue`
  to set the flag; assert the loop reaches `done` after `wire_issue` without
  invoking `confidence_check`.
- `test_no_decision_needed_unchanged_chain` — assert the existing chain
  (refine → wire → confidence_check → check_readiness → ...) is unchanged
  when no flag is set, including the existing `max_refine_count` retry
  loop.
- `test_refine_followup_decision_gate` — assert `refine_followup` →
  `check_decision_after_refine` is consulted exactly once per retry (not
  re-consulted on the same refine pass).

### Reuse, Not Reinvent

- `fragment: shell_exit` — already used at `refine-to-ready-issue.yaml:203`
  (`check_decision_needed`) and `autodev.yaml:111`
  (`check_decision_at_dequeue`).
- `ll-issues check-flag` — already used at `refine-to-ready-issue.yaml:202`
  and `autodev.yaml:110, 169, 568`.
- The `done` terminal state (line 283) is the existing destination for
  the BUG-1366 fix; reusing it preserves the "outer autodev handles
  decide" contract.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against the codebase 2026-07-07:_

**Verified accurate.** Every line anchor in this issue matches the current
`refine-to-ready-issue.yaml` (88, 98, 116, 122, 197, 202–203, 283). The
`ll-issues check-flag <issue_id> <field>` CLI exists with exactly the
signature the proposed states use (`ll-issues check-flag --help` confirms
positional `issue_id field`). The outer-loop anchors are also correct:
`check_decision_after_refine` at `autodev.yaml:165`, `check-flag` calls at
`autodev.yaml:110, 169, 568`, and `check_decision_at_dequeue` at
`autodev.yaml:102`.

**Correction — the named test target does not exist.** There is no
`scripts/tests/test_loop_refine_to_ready.py`. The structural tests for this
loop live in `scripts/tests/test_builtin_loops.py`, class
`TestRefineToReadyIssueSubLoop` (line 980), which parses the YAML via a
`data` fixture (`yaml.safe_load`) and asserts on the state dict. Add the new
tests **there**, following that class's structural style — NOT the behavioral
"stub `refine_issue` / assert the loop reaches `done`" style described under
"Tests Added" above. The repo does not stub slash-command states for this
loop; it asserts routing directly on the parsed YAML.

**Correction — three existing tests must be UPDATED (they will FAIL on the
rewire), not merely supplemented:**

- `test_refine_issue_next_is_check_wire_done`
  (`test_builtin_loops.py:1309`) — asserts `refine_issue.next ==
  "check_wire_done"`. Part 1 rewires this arrow. Update the expected value.
- `test_refine_followup_next_is_check_wire_done`
  (`test_builtin_loops.py:1316`) — asserts `refine_followup.next ==
  "check_wire_done"`. Part 1 rewires this arrow. Update the expected value.
- `test_mark_wire_done_routes_to_confidence_check`
  (`test_builtin_loops.py:1218`) — asserts `mark_wire_done.next ==
  "confidence_check"`. Part 2 rewires this arrow. Update the expected value.

The AC "Full suite green with no new skips" is **unsatisfiable** unless these
three are edited in lockstep with the YAML change.

**Suggested new structural tests** (in `TestRefineToReadyIssueSubLoop`,
mirroring `test_refine_issue_next_is_check_wire_done` at line 1309):

- assert each new gate state exists, uses `fragment: shell_exit`, and its
  `action` is `ll-issues check-flag ${captured.issue_id.output} decision_needed`
- assert each gate's `on_yes == "done"` and its `on_no`/`on_error` fall
  through to the existing next state (`check_wire_done` after refine,
  `confidence_check` after wire)
- assert `refine_issue.next`, `refine_followup.next`, and `mark_wire_done.next`
  now point at the new gate states

**Naming caution.** The proposed inner state name `check_decision_after_refine`
(Part 1) is **identical** to the OUTER autodev state at `autodev.yaml:165`
that this issue references throughout. There is no technical collision
(states are namespaced per YAML file), but two same-named states across the
two composed loops is a readability/debugging trap in run logs and traces.
Consider naming the inner gates `check_decision_mid_refine` /
`check_decision_mid_wire` to keep the inner/outer distinction obvious.

**Variable reference confirmed.** The proposed snippets correctly use
`${captured.issue_id.output}` — this loop captures `issue_id` at
`resolve_issue` (line 31). Do NOT copy autodev's `${captured.input.output}`
form (autodev captures `input`, this sub-loop captures `issue_id`).

## Acceptance Criteria

- [ ] New `check_decision_after_refine` state inserted after
      `refine_followup`; `refine_issue.next` and `refine_followup.next`
      updated to point to it.
- [ ] New `check_decision_after_wire` state inserted after
      `mark_wire_done`; `mark_wire_done.next` updated to point to it.
- [ ] Both new states use `fragment: shell_exit` and run
      `ll-issues check-flag ${captured.issue_id.output} decision_needed`.
- [ ] Both new states route to `done` on yes (preserving the
      `check_decision_after_refine` outer-loop contract from
      `autodev.yaml:165`).
- [ ] Both new states fall through to the existing next state on no
      (no regression on the happy path).
- [ ] No mid-chain gate between `wire_issue` and `mark_wire_done` (wire
      failure routes to confidence_check, not to a decision gate — that
      path is the existing `on_error: confidence_check` at line 117).
- [ ] `max_refine_count` lifetime cap behavior unchanged
      (`check_lifetime_limit` still routes to `breakdown_issue`).
- [ ] Tests added covering: flag set after refine → done reached; flag
      set after wire → done reached; no flag → chain unchanged;
      `refine_followup` consults the gate exactly once.
- [ ] Existing structural tests updated in lockstep with the rewire:
      `test_refine_issue_next_is_check_wire_done` (`test_builtin_loops.py:1309`),
      `test_refine_followup_next_is_check_wire_done` (`:1316`), and
      `test_mark_wire_done_routes_to_confidence_check` (`:1218`) now assert
      the new gate states instead of the old `next:` targets.
- [ ] Full suite green: `python -m pytest scripts/tests/` exits 0 with
      no new skips.

## Verification

1. **Unit tests** in `scripts/tests/test_loop_refine_to_ready.py`
   (or analogous test file): four tests as listed in
   "Tests Added" above. Run:
   `python -m pytest scripts/tests/test_loop_refine_to_ready.py -v`
2. **Full suite green**: `python -m pytest scripts/tests/` exits 0
   (no regressions, no new skips).
3. **End-to-end manual**: set `decision_needed: true` on a test issue
   frontmatter; run `ll-loop run refine-to-ready-issue --input
   ISSUE-NNN`; confirm the loop reaches `done` after the first skill
   that saw the flag (refine or wire) without invoking the remaining
   skills.

## Impact

- **Priority**: P3 — wastes LLM budget but does not cause incorrect
  behavior. The outer-loop `check_decision_after_refine` (autodev.yaml:165)
  is the safety net that catches the flag post-hoc. The bug is a budget
  leak, not a correctness bug.
- **Effort**: Small — three `next:` rewires and two ~5-line state
  additions in one YAML file; four unit tests reusing the existing
  `shell_exit` fragment and `ll-issues check-flag` patterns.
- **Risk**: Low — both new states follow the established
  `check_decision_needed` (line 197) and `check_decision_at_dequeue`
  (`autodev.yaml:102`) patterns exactly. The only behavior change is
  "exit `done` earlier when the flag is set," which is the BUG-1366
  invariant the late-chain gate was originally written to enforce.
- **Compatibility**: No CLI or frontmatter changes. The fix is
  internal to one YAML file; the sub-loop's externally visible
  contract (returns `done` when the flag is set; outer loop handles
  decide) is unchanged.

## Related Key Documentation

- `docs/ARCHITECTURE.md` — FSM loop composition
- `docs/reference/API.md` — `refine-to-ready-issue` loop semantics
- `docs/development/TROUBLESHOOTING.md` — decision-gate routing

## Related Issues

- `BUG-1366` — Added the late-chain `check_decision_needed` gate before
  `breakdown_issue` in `refine-to-ready-issue`. This bug is the
  mid-chain analogue: BUG-1366 prevents the flag from being ignored
  at the very end of the chain; BUG-2528 prevents the chain from
  running past the point where the flag was set.
- `BUG-2513` — Added `check_decision_at_dequeue` in `autodev` to catch
  pre-existing `decision_needed: true` issues before `refine_current`
  runs. The defense-in-depth complement of this fix: BUG-2513 catches
  pre-refine flags; BUG-2528 catches mid-refine flags; the existing
  `check_decision_after_refine` (`autodev.yaml:165`) catches
  post-sub-loop flags as a final safety net.

## Status

open

## Session Log
- `/ll:refine-issue` - 2026-07-07T19:49:17 - `14039683-e0ea-4bd7-a9c4-78de45770ee0.jsonl`
- `/ll:capture-issue` - 2026-07-07T19:43:26Z - captured from conversation
  about `refine-to-ready-issue` mid-chain decision_needed handling
