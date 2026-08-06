---
id: ENH-3079
title: Document inert on_rate_limit_exhausted on recursive-refine's sub-loop call state
type: ENH
priority: P4
status: done
discovered_by: manual
discovered_date: 2026-08-06
captured_at: '2026-08-06T05:23:38Z'
completed_at: '2026-08-06T05:23:38Z'
relates_to:
- BUG-3065
- ENH-3075
- BUG-2065
labels:
- loops
- fsm
- docs
- rate-limit
testable: false
decision_needed: false
size: Small
---

# ENH-3079: Document inert `on_rate_limit_exhausted` on `recursive-refine`'s sub-loop call state

## Summary

`recursive-refine.yaml`'s `run_refine` state declares `on_rate_limit_exhausted: dequeue_next`
alongside `fragment: with_rate_limit_handling`. Because `run_refine` is a `loop:` (sub-loop call)
state rather than an action state, that route **can never fire** — it reads as working rate-limit
escalation and silently does nothing.

BUG-3065 discovered and analyzed this while extracting `oracles/resolve-decision.yaml`, and
explicitly scoped it out as "pre-existing, out of scope, worth a comment where noticed"
(`### Rate-limit exhaustion (must not exit done)`). BUG-3065 shipped without adding the comment.
This issue adds it.

## Motivation

The declaration is actively misleading in the direction that costs the most: a reader auditing
rate-limit handling sees a route on the state and concludes the path is covered. BUG-3065's own
analysis had to re-derive the mechanism from `executor.py` before it could correctly decide *not*
to add the same dead route to `refine-to-ready-issue`'s three new `loop:` call states. Recording
the finding at the site prevents the next reader from paying that cost again — or, worse, from
copying the pattern into a new sub-loop call state.

## Current Behavior

`scripts/little_loops/loops/recursive-refine.yaml` `run_refine` declared `on_rate_limit_exhausted:
dequeue_next` with no indication the route is unreachable.

Why it cannot fire (verified against the current source, not carried over from BUG-3065's prose):

- `_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:820`) returns a routing target directly
  from `child_result.terminated_by`. It never produces an `ActionResult`.
- The 429 interception (`scripts/little_loops/fsm/executor.py:1673`) is gated on
  `action_result is not None` — and additionally on `exit_code != 0` per BUG-2065's fix — so a
  `loop:` state is never classified as rate-limited.
- The child's exit is indistinguishable after the fact: `captured.<state>.failure_terminal` is a
  **bool** (`fsm/types.py`), not the terminal's name, so giving the child a dedicated
  rate-limit-flavored failure terminal would buy the parent nothing either.

Net effect: a 429 that exhausts the retry budget inside `refine-to-ready-issue` surfaces to
`recursive-refine` as `on_failure` → `gate_recursion`, never as `on_rate_limit_exhausted` →
`dequeue_next`.

## Expected Behavior

The dead route is annotated at the site with the mechanism, the actual observed behavior, and what a
real fix would require — so the next reader neither trusts it nor re-derives it.

## What Was Done

Added a comment block above `on_rate_limit_exhausted` in
`scripts/little_loops/loops/recursive-refine.yaml` (`run_refine`, ~line 230) covering:

1. That the route is dead config on a `loop:` state, with the two `executor.py` anchors.
2. That `failure_terminal` being a bool rules out the child-side workaround.
3. What actually happens instead — `on_failure` → `gate_recursion`.
4. What a real fix needs: a marker file the child writes before exiting `failed`, which callers read
   on `on_failure` (the same mechanism BUG-3065 deferred to ENH-3075 for the `autodev` path).

The key itself is **kept, not deleted**, so the intent stays on record and a future engine change
that makes sub-loop 429s classifiable finds the route already expressed.

## Scope Boundaries

**In scope:** the comment block on `recursive-refine.yaml`'s `run_refine` state.

**Out of scope:**

- Making the route actually work. That needs the marker-file mechanism BUG-3065 deferred to
  ENH-3075 — a `${context.run_dir}/decide-rate-limited-<issue_id>` file the child writes before
  exiting `failed`, which callers read on `on_failure`. ENH-3075 owns it because it only changes an
  outcome on the `autodev` path, where today's `on_rate_limit_exhausted: done` gracefully ends the
  whole run and losing that would walk the entire queue into deferral one 429 at a time.
- Auditing every other `loop:` call state in the built-in loops for the same dead key. Worth doing
  as a sweep; not done here (see `### Similar Patterns`).
- Any routing, state, or fragment change. The declaration is deliberately kept, not deleted.

## Program Design

No code, types, or signatures change — this is a YAML comment. The subsections below record the
engine surface the comment's claims rest on, so a future reader can re-verify them.

### Types

```python
# scripts/little_loops/fsm/types.py:60
failure_terminal: bool = False
```

The load-bearing detail: a **bool**, not the terminal's name. Docstring at `types.py:44` — "True
when execution stopped on a terminal state whose ...". A parent inspecting
`captured.<state>.failure_terminal` learns *that* the child failed, never *how*.

### Signatures

```python
# scripts/little_loops/fsm/executor.py:820
def _execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None: ...

# scripts/little_loops/fsm/executor.py:1441 — encloses the 429 interception at :1673
def _execute_state(self, state: StateConfig) -> str | None: ...
```

`_execute_sub_loop` returns `str | None` — a routing target — with no `ActionResult` anywhere in its
return type. That type signature *is* the reason the route is dead.

### Call Path

`_execute_state` → `_execute_sub_loop` → routing target from `child_result.terminated_by`

versus the rate-limit branch, a sibling under the same caller:

`_execute_state` → `if action_result is not None:` (`executor.py:1673`) → `classify_failure` →
`_handle_rate_limit` (`executor.py:1683`) → `on_rate_limit_exhausted`

The sub-loop branch never populates `action_result`, so `_handle_rate_limit` is unreachable for a
`loop:` state and `on_rate_limit_exhausted` is never consulted.

At the YAML layer: `recursive-refine.run_refine` → `loop: refine-to-ready-issue` → a 429 exhausted
inside the child → child exits `failed` → parent's `on_failure` → `gate_recursion`. Never
`dequeue_next`.

### Claims the comment asserts

| Claim | Anchor | Verified this session |
|---|---|---|
| Sub-loop dispatch never yields an `ActionResult` | `_execute_sub_loop`, `fsm/executor.py:820` | Yes — returns a routing target from `child_result.terminated_by` |
| 429 interception requires one | `fsm/executor.py:1673` (`if action_result is not None:`) | Yes — plus BUG-2065's `exit_code != 0` guard |
| Child-side terminal naming is not observable to the parent | `failure_terminal` in `fsm/types.py` | Yes — bool, not a name |

If any of the three ever stops holding, the comment is the thing that must be revisited, and the
kept `on_rate_limit_exhausted: dequeue_next` route becomes live rather than needing to be written.

## Impact

**Risk:** none. Comment-only; no behavioral surface. `ll-loop validate` and the full
`test_builtin_loops.py` suite confirm nothing moved.

**Benefit:** removes a false-positive signal from a rate-limit audit path. The concrete cost already
paid: BUG-3065 had to re-derive this mechanism from `executor.py` mid-implementation before it could
correctly decide *not* to add the same dead route to `refine-to-ready-issue`'s three new `loop:`
states. Without the annotation the next such change re-pays that, or silently copies the pattern.

**Blast radius if wrong:** a misleading comment, caught by the anchors it cites.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/recursive-refine.yaml` — comment only, no routing change.

### Dependent Files

None. Comment-only; no state names, routes, or fragments changed.

### Similar Patterns

- `scripts/little_loops/loops/autodev.yaml:385` (`refine_current`) — also a `loop:` call state into
  `refine-to-ready-issue`. Not audited under this issue; if it carries the same dead key it deserves
  the same annotation.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — its three new `resolve_decision_*`
  `loop:` states deliberately carry **no** `on_rate_limit_exhausted`, per BUG-3065's requirement not
  to add a route that "would read as working and silently never fire." Already correct; no change.

## Tests

No new test. The change is a YAML comment with no behavioral surface, and asserting on comment text
would be a brittle test of prose.

Regression gates that do cover it:

- `ll-loop validate recursive-refine` — still valid. The three emitted warnings are pre-existing
  ENH-2805 (MR-12) pruning-profile advisories on `commit_periodic`, `run_wire_for_artifacts`, and
  `run_size_review`; unrelated to this change.
- `python -m pytest scripts/tests/test_builtin_loops.py` — 1437 passed.

## Session Log
- `hook:posttooluse-status-done` - 2026-08-06T05:24:27 - `c23e61c6-3bd3-4aa0-8338-59919fbe2f99.jsonl`

**2026-08-06** — Session verified BUG-3065's fix end-to-end, then closed its one deferred loose end.

**BUG-3065 verification** (run `.loops/runs/refine-to-ready-issue-20260805T234108/`, history
`.loops/.history/2026-08-06T044108-refine-to-ready-issue/`, subject `FEAT-3060`):

The bug's reproduction was a 4-state truncated run ending `check_decision_mid_refine → done`. This
run completed 21 iterations, `terminated_by: terminal`, `failure_terminal: false`:

```
refine_issue → check_decision_mid_refine → resolve_decision_mid_refine
                 └─[sub-loop, depth 1] route_entry → check_decision_decidable
                      → run_decide → assert_decision_cleared → done   (4 iters)
             → check_wire_done → wire_issue → mark_wire_done → check_decision_mid_wire
             → verify_issue → check_verify_verdict → check_hedges → check_ac_automatable
             → confidence_check → check_readiness → check_outcome
             → check_decision_needed → check_missing_artifacts → breakdown_issue → done
```

Everything BUG-3065 reported as silently skipped — wire, verify, confidence — ran. Corroborating:

- `resolve_decision_mid_refine.on_success → check_wire_done` matches the per-gate resume table in
  BUG-3065's `### Three gates need three call states`.
- `FEAT-3060` ends with `decision_needed: false`, a written `### Decision Rationale` (Option A,
  10/12 vs 6/12), and `/ll:decide-issue` in its History — `run_decide` did real work and
  `assert_decision_cleared` confirmed it.
- Gate 3 (`check_decision_needed`, iteration 18) fell through `on_no`, proving the flag stayed
  cleared and the `resolve_decision_pre_breakdown → confidence_check` cycle did not spin.
- The run terminated on the designed low-outcome path (outcome 45 < threshold 65 → `breakdown_issue`,
  which produced FEAT-3076 / FEAT-3077 / FEAT-3078), not a dead-end.
- 21 of `max_steps: 40` used — BUG-3065's ENH-3031 budget raise holds with headroom.

Spec conformance re-checked against the shipped `oracles/resolve-decision.yaml`: `import:
lib/common.yaml` present; per-issue marker name; `on_rate_limit_exhausted: failed` (not `done`) on
both `deposit_options` and `run_decide`; explicit per-issue `evaluate.history_file` fixing the inert
open-question stall gate; `route_entry` + `skip_probe` for autodev's fifth entry point;
`record_decision_unresolved` → `failed` with the BUG-2729 already-resolved guard. `ll-loop validate`
passes both loops. 115 targeted tests pass, including per-gate assertions for all three resume
targets.

**Caveat recorded, not a defect:** this run exercised gate 1 (`check_decision_mid_refine`) only.
Gates 2 and 3 are asserted statically in `test_builtin_loops.py` but have never fired live.

**Follow-up triage:** BUG-3065's other named follow-up — `recursive-refine.yaml`'s
`check_decision_needed` skipping rather than resolving (`### Similar Patterns`) — was assessed and
**not filed**. Post-fix it is defense-in-depth: an issue reaching it has already had its decision
resolved by the sub-loop, and a failed resolution returns `failed` → `gate_recursion` instead. The
inert `on_rate_limit_exhausted` was the only actionable remainder, and became this issue.

## Status

Done. Comment landed in `recursive-refine.yaml`; `ll-loop validate` clean; full
`test_builtin_loops.py` suite green (1437 passed).
