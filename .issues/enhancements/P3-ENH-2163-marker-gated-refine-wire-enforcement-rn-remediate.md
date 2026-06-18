---
id: ENH-2163
title: Marker-gated refine+wire enforcement for above-minimal issues in rn-remediate
type: ENH
priority: P3
status: done
captured_at: '2026-06-15T00:00:00Z'
completed_at: '2026-06-15T00:00:00Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
relates_to:
- BUG-2007
- ENH-2107
size: Small
labels:
- loops
- fsm
- planning
---

# ENH-2163: Marker-gated refine+wire enforcement for above-minimal issues in rn-remediate

## Summary

`rn-remediate.yaml` is a single-dimension dispatcher: each remediation pass picks
exactly one action (refine *or* wire *or* decide *or* decompose) targeting the
dominant deficiency, then re-assesses. Convergence short-circuits to `implement`
the moment scores clear the joint readiness gate
(`route_conv_pass.on_yes → implement`). As a result an **above-minimal-complexity**
issue could reach `implement` having run *only* refine, *only* wire, or **neither**
(e.g. `diagnose → IMPLEMENT` on the first visit). There was no invariant
guaranteeing that a non-trivial issue was both refined and wired at least once
before `ll-auto` ran.

This enhancement adds a **marker-gated choke point** in front of `implement` so an
issue whose `score_complexity` is above minimal
(`≥ diagnose_complexity_threshold`, default 15 on the 0–25 scale) is guaranteed at
least one `/ll:refine-issue … --auto --full-rewrite` pass **and** at least one
`/ll:wire-issue … --auto` pass before implementation. Minimal issues are unaffected.

## Motivation

- Honor the design expectation that non-trivial issues receive both codebase
  research (refine) and integration wiring (wire) before automated implementation,
  rather than whichever single dimension the dispatcher judged dominant.
- Close the gap where `diagnose → IMPLEMENT` (or a single-action convergence PASS)
  could implement a complex issue that was never wired or never refined.
- Keep the change bounded and opt-out-able so existing callers can preserve the
  prior single-dimension behavior.

## Current Behavior (before)

The two diagnose/convergence routes to `implement` fired directly:

```yaml
route_d_implement:
  on_yes: implement      # diagnose IMPLEMENT can fire on first visit, zero refine/wire
route_conv_pass:
  on_yes: implement      # reachable after a single refine OR wire OR decide
```

`refine` and `wire` routed straight back to `re_assess` on success, with nothing
recording that they had run.

## Expected Behavior (after)

An above-minimal issue is forced through any missing action before implement; a
minimal issue (or any caller that set `require_refine_and_wire: false`) passes
straight through. Markers are write-once, so the gate adds **at most one refine +
one wire detour, then IMPLEMENT** — bounded, no unbounded looping.

## Resolution

- **Status**: Done
- **Closed**: 2026-06-15

### Changes to `scripts/little_loops/loops/rn-remediate.yaml`

1. **Context toggle** — added `require_refine_and_wire: true` (overridable by the
   parent `rn-implement` via `with:`; set `false` to restore the single-dimension
   short-circuit).

2. **Stable complexity band** — folded a one-time band snapshot into
   `verify_scores_persisted`. `pre_scores_<ID>.json` is overwritten every pass by
   `check_convergence` (`cp "$POST" "$PRE"`), so the genuine pre-remediation
   complexity is captured once into `complexity_band_<ID>.txt` (`ABOVE_MINIMAL` /
   `MINIMAL`) that the gate reads without it mutating mid-run.

3. **Monotonic markers** — new `mark_refined` / `mark_wired` side-effect states
   write write-once marker files then continue to `re_assess`. `refine.on_success`
   and `wire.on_success` now hop through them (BUG-2007 intent preserved — success
   still reaches `re_assess`, never an unconditional `--full-rewrite` bounce).

   ```yaml
   # refine / wire on_success now route through the marker writers
   refine:  { on_success: mark_refined, on_error: emit_implement_failed }
   wire:    { on_success: mark_wired,   on_error: refine }
   mark_refined: { action: 'echo 1 > .../refined_<ID>.txt',  next: re_assess }
   mark_wired:   { action: 'echo 1 > .../wired_<ID>.txt',     next: re_assess }
   ```

4. **The gate** — `gate_implement` + `route_gate_refine` + `route_gate_wire`. The
   gate emits one of three disjoint tokens and cascades:

   ```yaml
   gate_implement:        # IMPLEMENT | NEED_REFINE | NEED_WIRE; on_error: implement (fail-open)
     next: route_gate_refine
   route_gate_refine: { pattern: NEED_REFINE, on_yes: refine, on_no: route_gate_wire }
   route_gate_wire:   { pattern: NEED_WIRE,   on_yes: wire,   on_no: implement }
   ```

   Logic: flag off → IMPLEMENT; band ≠ ABOVE_MINIMAL → IMPLEMENT; no refined marker
   → NEED_REFINE; no wired marker → NEED_WIRE; else IMPLEMENT.

5. **Re-routed the two above-minimal entry points** through the gate:

   ```yaml
   route_d_implement: { on_yes: gate_implement }   # was: implement
   route_conv_pass:   { on_yes: gate_implement }   # was: implement
   ```

   `check_wire_pre_implement → implement` was left unchanged — it is only reachable
   when `complexity < threshold` (MINIMAL), so the gate would be a no-op there.

### Termination argument

`complexity_band_<ID>.txt` is fixed; `refined_<ID>.txt` / `wired_<ID>.txt` are
write-once. The gate emits `NEED_REFINE` only while the refined marker is absent →
one `refine` → `mark_refined` sets it; same for wire. After both markers exist the
gate emits `IMPLEMENT`. So the gate contributes at most two detours; the existing
`max_remediation_passes` / `max_iterations: 100` bounds still hold. If a forced
action *regresses* scores below threshold, the issue correctly falls into the
existing budget / `emit_stalled_needs_decompose` machinery instead of implementing
an unstable change — an intentional safety valve.

### Tests — `scripts/tests/test_rn_remediate.py`

- Updated 4 routing assertions: `refine`/`wire` → marker hop;
  `route_d_implement.on_yes` and `route_conv_pass.on_yes` → `gate_implement`.
- Added `TestMarkerGate` (8 tests): toggle default, band snapshot, monotonic
  markers, three disjoint gate tokens, flag/band short-circuits, the
  refine→wire→implement cascade, both entry points gated, and the minimal-path
  exemption.

## Trade-offs

- Every above-minimal issue now incurs ≥1 refine **and** ≥1 wire even if `diagnose`
  judged it implement-ready — the explicit "at least once each" requirement. The
  `require_refine_and_wire` toggle (default `true`) lets a caller opt out.
- A forced wire/refine that destabilizes a previously-ready issue can route it to
  decompose/defer instead of implement — acceptable, and arguably more correct than
  implementing a complex issue that was never wired.

## Verification

- `ll-loop validate rn-remediate` — valid; all 6 new states reachable.
- `python -m pytest scripts/tests/test_rn_remediate.py scripts/tests/test_builtin_loops.py`
  — 940 passed (incl. global FSM reachability / `test_all_validate_as_valid_fsm`
  sweeps).
- `python -m pytest scripts/tests/test_rn_implement.py test_fsm_fragments.py test_rn_decompose.py`
  — 304 passed.
- `ruff check` + `ruff format --check` — clean.

## Files Changed

- `scripts/little_loops/loops/rn-remediate.yaml` — context toggle, band snapshot,
  `mark_refined`/`mark_wired`, `gate_implement`/`route_gate_refine`/`route_gate_wire`,
  two entry-point re-routes.
- `scripts/tests/test_rn_remediate.py` — updated routing assertions + `TestMarkerGate`.

## Follow-ups (not done this session)

- Optionally have the parent `rn-implement` pass `require_refine_and_wire` through
  `with:` explicitly (it inherits the `true` default today).


## Session Log
- `hook:posttooluse-status-done` - 2026-06-15T05:21:59 - `2de355a0-cdb9-4b50-8684-4cc62bd77e8c.jsonl`
