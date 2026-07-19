---
id: ENH-2691
title: "rn-refine synth_dispatch computes worker fail flag but never gates on it"
type: ENH
priority: P3
status: open
captured_at: '2026-07-19T00:00:00Z'
discovered_date: 2026-07-19
discovered_by: audit-loop-run
labels:
- loops
- rn-refine
- verdict-laundering
---

# ENH-2691: rn-refine synth_dispatch computes worker fail flag but never gates on it

## Summary

`synth_dispatch` in `loops/rn-refine.yaml` launches N `oracles/integrate-node`
workers in parallel, waits on all of them, and computes `FAIL=1` if any
worker's exit code was non-zero — but the state has no `evaluate`/`on_yes`/
`on_no`, only an unconditional `next: assemble`. The `fail=` value is embedded
in the logged output string (`SYNTH_WORKERS_DONE workers=$WORKERS fail=$FAIL`)
but never inspected by the FSM, so a crashed integration worker is currently
indistinguishable from a clean run at the control-flow level.

## Evidence

Found during audit of run `2026-07-19T161520-rn-refine`
(`.loops/.history/2026-07-19T161520-rn-refine/`). In that run
`fail=0` (both workers succeeded), so the gap did not manifest — but the
`synth_dispatch` state definition has no path that reacts to `fail=1`. If a
worker crashes, `assemble` falls back silently to
`nodes/n0/plan.md` with a `RECOVERY_NEEDED` note appended to
`plan-rubric.md`, framing it as an incomplete-integration case rather than a
worker failure — the two are different problems (a legitimate integration
step that never ran vs. a step that crashed) and currently get the same
downstream handling.

## Proposed Solution

Add an `evaluate: {type: output_contains, pattern: "fail=0"}` to
`synth_dispatch` and route `on_no` to a distinct state that records which
node(s) failed to integrate (e.g. via `worker-logs/worker-*.log`) before
falling through to `assemble`, so the eventual `RECOVERY_NEEDED` note (or a new
marker) can distinguish "worker crashed" from "integration simply didn't
finish."

## Acceptance Criteria

- [ ] A worker failure in `synth_dispatch` is distinguishable in the run
      artifacts from a clean pass.
- [ ] `on_no` path does not silently discard which node(s) failed.
- [ ] Existing clean-pass behavior (`fail=0` → `assemble`) is unchanged.

## Impact

- **Priority**: P3 — did not manifest in the audited run and integration
  worker crashes are likely rare, but the failure mode is currently invisible
  when it does occur.
- **Effort**: Small — one state's `evaluate`/`on_yes`/`on_no` plus a small new
  recording state in `loops/rn-refine.yaml`.

## Related Files

- `loops/rn-refine.yaml` (`synth_dispatch`, `assemble`)

## Status

**Open** | Created: 2026-07-19 | Priority: P3
