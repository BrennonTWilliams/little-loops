---
id: BUG-2513
title: autodev decision_needed gate bypassed on refine_current non-success exits
type: BUG
status: done
priority: P1
captured_at: '2026-07-07T06:36:33Z'
completed_at: '2026-07-07T08:19:28Z'
discovered_date: '2026-07-07'
discovered_by: audit-loop-run
relates_to:
- BUG-2501
- BUG-2514
labels:
- loops
- fsm
- autodev
- decide-issue
- decision-gate
confidence_score: 98
outcome_confidence: 87
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 22
---

# BUG-2513: autodev decision_needed gate bypassed on refine_current non-success exits

## Summary

In `scripts/little_loops/loops/autodev.yaml`, the `decision_needed` gate is only
reachable on the `on_success` path out of `refine_current`. A dequeued issue with
`decision_needed: true` can advance past the gate — or re-enter the queue — without
`/ll:decide-issue` ever running.

`refine_current` (the `refine-to-ready-issue` sub-loop delegate) has five exits:

```
on_success            → copy_broke_down → check_decision_after_refine   (reads the flag)
on_failure            → skip_inflight   → dequeue_next                  (flag never read)
on_error              → skip_inflight   → dequeue_next                  (flag never read)
on_no                 → dequeue_next                                    (flag never read)
on_rate_limit_exhausted → dequeue_next                                  (flag never read)
```

Four of the five exits never consult `decision_needed`. The earliest the flag is
read is `check_decision_after_refine`, *after* a full sub-loop pass. There is no
state that checks `decision_needed` on a fresh dequeue, before `refine_current`.

The second gate, `check_decision_before_size_review`, has the same dependency: it
also only fires downstream of an `on_success` from `refine_current`, so it does not
close the hole.

## Motivation

This bug matters because:

- **Silent correctness violation**: A user-facing `/ll:decide-issue` step that is
  explicitly requested by the issue's `decision_needed: true` flag is never invoked.
  No error is raised — the loop just continues refining the issue.
- **Infinite bypass loop**: Because the flag is never cleared on a non-success exit,
  the same issue can be re-dequeued and re-refined indefinitely, wasting compute and
  blocking the queue. Observed live in the killed `autodev` run against BUG-2501
  (`.loops/runs/autodev-20260706T212035/`) — symptom: "kept running refining Skills
  instead of running /ll:decide-issue."
- **Repeated pattern, not an isolated hole**: The same `on_success`-coupled
  dependency exists on the second gate (`check_decision_before_size_review`). The
  defect is structural to how decision gates are wired into the loop, not a one-off
  routing mistake.
- **P1 priority**: A production automation loop (`autodev`) has a reproducible
  routing defect with a live fixture (BUG-2501 still carries `decision_needed: true`),
  and the fix is small and well-scoped, so the work should not slip past P1.

## Current Behavior

A dequeued issue with `decision_needed: true` whose `refine_current` sub-loop
returns `on_no`, `on_failure`, `on_error`, or `on_rate_limit_exhausted` advances to
`dequeue_next` (directly or via `skip_inflight`) without consulting the
`decision_needed` flag. Observed live during a user-killed `autodev` run against
BUG-2501 (post-mortem: `autodev-bug2501-kill-analysis.md`): the loop "kept running
refining Skills instead of running /ll:decide-issue." A 200-record
`ll-session grep "decide-issue"` sweep confirmed `/ll:decide-issue BUG-2501 --auto`
was **not invoked at any point** during the killed run, ruling out the two failure
modes that require `run_decide` to fire (sub-loop oscillation, `deposit_options`
retry detour) and leaving the `on_no → dequeue_next` bypass ("Mode B") as the most
consistent cause. The FSM `events.jsonl` / `state.json` for the killed run were
lost to SIGKILL (see BUG-2514); the failure mode was reconstructed from the three
host-CLI session logs the sub-loop's `/ll:refine-issue`, `/ll:wire-issue`, and
`/ll:confidence-check` invocations produced.

## Expected Behavior

- A dequeued issue with `decision_needed: true` reaches `run_decide` regardless of
  the `refine_current` exit branch (`on_success`, `on_failure`, `on_error`, `on_no`,
  `on_rate_limit_exhausted`).
- `/ll:decide-issue <ID> --auto` fires on the first dequeue for any issue carrying
  `decision_needed: true`, before any refine-cycle work is attempted.
- The decision gate is decoupled from the sub-loop's outcome; a refine-pass
  failure does not silently bypass the user's explicit decision request.
- `ll-loop validate autodev` passes; the new routing has no dead `no` / `partial`
  ends.
- A pytest under `scripts/tests/` drives the new gate and asserts that `run_decide`
  is reached before `refine_current` for a `decision_needed: true` fixture issue.
- Reproduction against BUG-2501 (still `decision_needed: true`) shows
  `/ll:decide-issue` invoked on first dequeue.

## Steps to Reproduce

BUG-2501 still has `decision_needed: true`. Run in a detachable session so a kill
does not destroy the audit archive:

```bash
ll-loop run autodev --input BUG-2501 --max-steps 20
```

Pre-patch expectation: `/ll:decide-issue` is **not** invoked. Post-patch: it fires
on the first dequeue.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `state refine_current` (around line 102) and the downstream routing
  through `dequeue_next` / `check_decision_after_refine`
- **Cause**: The decision gate is coupled to sub-loop success. When
  `refine-to-ready-issue` returns `on_no` (queue empty / sub-loop never started),
  `on_failure` / `on_error` (skip path), or `on_rate_limit_exhausted`, the issue
  re-enters `dequeue_next` without any state reading `decision_needed`. The
  `decision_needed: true` flag is never cleared, so the issue can be re-dequeued
  into the same bypass on the next iteration — producing the observed "keeps
  refining, never decides" loop. The second gate (`check_decision_before_size_review`)
  has the same dependency and does not close the hole.

## Proposed Solution

Add a `check_decision_at_dequeue` state between `dequeue_next.on_yes` and
`refine_current` that short-circuits straight to `run_decide` when
`decision_needed: true`, making the decision gate independent of the sub-loop's
`on_success` / `on_failure` / `on_error` / `on_no` / `on_rate_limit_exhausted`
outcome.

```
dequeue_next.on_yes → check_decision_at_dequeue
  check-flag ${captured.input.output} decision_needed
  on_yes → run_decide
  on_no  → refine_current
  on_error → refine_current
```

`dequeue_next` already `rm -f`s `autodev-decide-ran` and
`autodev-decide-options-deposited`, so a fresh dequeue enters this gate clean; no
extra marker-clearing is needed at this entry point. Confirm the
`run_decide → mark_decide_ran → rerun_confidence_after_decide` chain lands
sensibly when entered pre-refine (the issue has not yet been through the
refine / confidence sub-loop), and that `check_decision_decidable` /
`deposit_options` still bound the option-enumeration detour on this path.

Because the fix targets a `check_semantic`-free deterministic gate, it can be
verified by a pytest that drives the loop against a fixture issue with
`decision_needed: true` and asserts `run_decide` is reached before
`refine_current`.

## Implementation Steps

1. Add the `check_decision_at_dequeue` state in `scripts/little_loops/loops/autodev.yaml`
   between `dequeue_next.on_yes` and `refine_current`, with a
   `check-flag ${captured.input.output} decision_needed` predicate routing
   `on_yes → run_decide` and `on_no / on_error → refine_current`.
2. Verify the `run_decide → mark_decide_ran → rerun_confidence_after_decide`
   chain lands sensibly when entered pre-refine (the issue has not yet been
   through the refine / confidence sub-loop), and that `check_decision_decidable`
   / `deposit_options` still bound the option-enumeration detour on this entry
   path.
3. Add a pytest under `scripts/tests/` that drives the new gate with a fixture
   issue carrying `decision_needed: true` and asserts `run_decide` is reached
   before `refine_current`.
4. Run `ll-loop validate autodev` to confirm no dead `no` / `partial` ends in the
   new routing.
5. Reproduce against BUG-2501 (`ll-loop run autodev --input BUG-2501 --max-steps 20`)
   and confirm `/ll:decide-issue` is invoked on the first dequeue.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — add the `check_decision_at_dequeue`
  state between `dequeue_next.on_yes` and `refine_current`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — sub-loop delegate
  invoked from `refine_current`; unchanged contract (the decision gate moves
  upstream, so the sub-loop is only invoked when no decision is needed)
- `scripts/little_loops/fsm/executor.py` — runs FSM states; no change needed,
  the new state reuses the existing `check-flag` evaluator type
- `scripts/little_loops/cli/loop/_helpers.py` — invoked by `run_decide`; no
  change needed, the chain entry point is unchanged

### Similar Patterns
- `check_decision_after_refine` (in `autodev.yaml`) — existing decision gate;
  same `check-flag decision_needed` predicate but currently only fires downstream
  of an `on_success`. The new `check_decision_at_dequeue` state is a peer, not a
  replacement — keep both so the post-refine gate still catches flags added
  during refinement (e.g. by a future decide hook).
- `check_decision_before_size_review` (in `autodev.yaml`) — second decision gate
  with the same `on_success`-coupled dependency. The same fix pattern could be
  applied here; out of scope for this issue but worth a follow-on if the bug
  class recurs.

### Tests
- New pytest under `scripts/tests/` driving the new gate with a fixture issue
  carrying `decision_needed: true` and asserting `run_decide` is reached before
  `refine_current` (per Implementation Step 3).

### Documentation
- `docs/reference/API.md` § Loop DSL — `check-flag` evaluator is already
  documented; no change needed for the new state to be self-describing in YAML.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — link the closed BUG as the
  motivating example for "decision gates must be wired on the dequeue path, not
  only on refine-success."
- `autodev-bug2501-kill-analysis.md` (repo root; the run directory
  `.loops/runs/autodev-20260706T212035/` contains only the run artifacts — the
  post-mortem was promoted out of the run dir into the repo for traceability) —
  link the closed BUG from the post-mortem as the fix lands.

### Configuration
- N/A — no `ll-config.json` or schema changes; the gate reads `decision_needed`
  directly from the dequeued issue's frontmatter.

## Impact

- **Priority**: P1 — production automation loop defect, reproducible from an
  existing fixture, silent failure mode (no error, just wrong behavior).
- **Effort**: Small — one new state in `autodev.yaml` plus a focused pytest. The
  state reuses the existing `check-flag` evaluator and the existing
  `run_decide → mark_decide_ran → rerun_confidence_after_decide` chain.
- **Risk**: Low — the change adds a new state *before* `refine_current`;
  existing paths through `refine_current` are unchanged. The only behavioral
  change is that `decision_needed: true` issues now reach `run_decide` on
  first dequeue (which is the documented intended behavior). Need to confirm
  the pre-refine entry into `rerun_confidence_after_decide` is sensible, since
  the issue has not yet been through the refine / confidence sub-loop.
- **Breaking Change**: No — for `decision_needed: false` (or absent) issues
  the routing is identical; for `decision_needed: true` issues the routing
  changes from "refine → maybe decide" to "decide immediately, then refine if
  needed," which is the documented intended behavior.

## Status

**Done** | Created: 2026-07-07 | Priority: P1 | Closed: 2026-07-07

## Resolution

Added a `check_decision_at_dequeue` state between `dequeue_next.on_yes` and
`refine_current` in `scripts/little_loops/loops/autodev.yaml`. The new gate
runs `ll-issues check-flag ${captured.input.output} decision_needed` (mirrors
the existing `check_decision_after_refine` predicate) and routes
`on_yes → run_decide`, `on_no / on_error → refine_current`. This decouples the
decision gate from the sub-loop's `on_success` / `on_failure` / `on_error` /
`on_no` / `on_rate_limit_exhausted` outcome, closing the bypass loop where a
`decision_needed: true` issue was re-dequeued and re-refined indefinitely
without `/ll:decide-issue` ever running (BUG-2501 symptom).

The pre-existing `check_decision_after_refine` gate is retained as defense in
depth — it still catches flags added during refinement (e.g. by a future
decide hook) on the post-refine path.

`dequeue_next` already clears `autodev-decide-ran` and
`autodev-decide-options-deposited` markers on every dequeue, so the new gate
enters clean. The `run_decide → mark_decide_ran → rerun_confidence_after_decide
→ recheck_after_decide` chain lands sensibly when entered pre-refine.

Tests: `scripts/tests/test_autodev_decision_gate.py` (11 tests, all passing)
covers structural YAML assertions, FSMExecutor-driven routing assertions
(decision_needed=true → run_decide before refine_current; =false → refine_current;
error → fail-open to refine_current), and `ll-loop validate autodev` schema
compliance. One pre-existing test
(`test_dequeue_next_routes_to_refine_current` in
`scripts/tests/test_builtin_loops.py`) was updated to assert the new
routing and renamed to `test_dequeue_next_routes_to_check_decision_at_dequeue`.

Verification: 14081 passed, 27 skipped, 0 failed (full suite); `ll-loop validate
autodev` returns "autodev is valid".

## Session Log
- `/ll:ready-issue` - 2026-07-07T07:54:11 - `1f067e0b-5e9d-462a-88ed-c9fb11192feb.jsonl`
- `/ll:format-issue` - 2026-07-07T07:40:02 - `1cc86841-6530-4686-b2a2-86a91595290e.jsonl`
- `/ll:confidence-check` - 2026-07-07T08:15:00 - `6a354f59-11f8-4a33-afa6-7c0307e0aa61.jsonl`
- `/ll:manage-issue fix` - 2026-07-07T08:19:28 - `300573a5-e174-402e-8367-69ea04d7149d.jsonl`
