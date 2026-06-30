---
id: ENH-2402
title: Consistent learning-test gating across core implementation loops (rn-implement, autodev, sprint-refine-and-implement)
type: ENH
status: done
priority: P2
captured_at: '2026-06-30T18:37:07Z'
discovered_date: '2026-06-30'
discovered_by: manual
labels:
- enhancement
- loops
- learning-tests
- consistency
- observability
completed_at: '2026-06-30T18:37:07Z'
---

# ENH-2402: Consistent learning-test gating across core implementation loops

## Summary

The three core implementation FSM loops — `rn-implement` (via its `rn-remediate`
sub-loop), `autodev`, and `sprint-refine-and-implement` (via
`auto-refine-and-implement` → `autodev`) — already converged on a single learning-gate
choke point: every one implements through `ll-auto --only "$ID"`, which re-enters
`process_issue_inplace()` and runs the ENH-2319 per-issue learning gate
(`proof-first-task` → `assumption-firewall` → `/ll:explore-api`). The gate was therefore
*mechanically* consistent, but it was invisible and uncontrollable at the loop layer:

1. A gate **block** was laundered into a generic `IMPLEMENT_FAILED` / failure outcome —
   indistinguishable from a real implementation crash in `summary.json` / `failures.txt`.
2. There was **no skip knob**: `ll-auto`, `ll-parallel`, and `ll-sprint` all expose
   `--skip-learning-gate`, but the FSM loops hardcoded `ll-auto --only "$ID"` with no way
   to thread it.

This issue made the consistency real and observable — keeping the single
`process_issue_inplace` gate as the source of truth (no duplicated gate logic) and
surfacing its outcome distinctly in every loop, plus a uniform skip control.

## Motivation

Without a distinct outcome, operators running `rn-implement` / `autodev` against issues
with unproven external-API dependencies saw "failures" with no indication that the remedy
was `/ll:explore-api` rather than a code fix. And there was no parity with the
`--skip-learning-gate` knob every other implementation entrypoint already offered. The fix
mirrors the existing ENH-2353 `ENV_NOT_READY` split (a precedent in the same code paths).

## What Changed

### A. Distinct, observable gate-block outcome (mirrors ENH-2353 `ENV_NOT_READY`)

- **`scripts/little_loops/issue_manager.py`** — on a `blocked` verdict,
  `process_issue_inplace()` now prints a stable, greppable `LEARNING_GATE_BLOCKED <id>`
  marker to stdout (captured by the loops' `ll-auto --only ... 2>&1`).
- **`scripts/little_loops/loops/lib/common.yaml`** — new shared
  `ll_auto_learning_gate_check` fragment that greps the marker and exposes it via
  `output_contains` (modeled on `ll_auto_auth_check`).
- **`rn-remediate.yaml`** — `implement` routes failures to `check_learning_gate` **first**
  → `emit_learning_gate_blocked` (new `LEARNING_GATE_BLOCKED` outcome token), falling
  through to the existing auth (`check_impl_auth`) / failure path otherwise.
- **`rn-implement.yaml`** — new `route_rem_learning_gate` router + `record_learning_gate_blocked`
  state; tallied separately in `summary.json` (`learning_gate_blocked` key) and the report
  line, subtracted from the generic `FAILURES` bucket.
- **`autodev.yaml`** — new `check_learning_gate` → `mark_gate_blocked` (records to
  `autodev-gate-blocked.txt`, surfaced in the run Summary with the `/ll:explore-api`
  remedy). `sprint-refine-and-implement` inherits this for free via the delegation chain.

### B. Uniform `skip_learning_gate` knob (parity with `ll-auto --skip-learning-gate`)

- Added as a `context` var (and a `parameters` entry on `rn-remediate`) and threaded down
  the full chain — `rn-implement → rn-remediate`, and
  `sprint-refine-and-implement → auto-refine-and-implement → autodev` — each appending
  `--skip-learning-gate` to its inner `ll-auto --only` call when set.
- Usage: `ll-loop run autodev <ids> --context skip_learning_gate=1` (and the analogous
  `rn-implement` / `sprint-refine-and-implement` invocations).

### C. Config

- **`.ll/ll-config.json`** — `learning_tests.enabled: true` (the gate is now live in this
  repo; it only fires for issues with resolvable external-API targets).

### D. Documentation

- **`docs/guides/RECURSIVE_LOOPS_GUIDE.md`** — added the `LEARNING_GATE_BLOCKED` (and the
  previously-missing `ENV_NOT_READY`) rows to the sub-loop outcome-token table, plus a
  paragraph stating the cross-loop consistency guarantee.

## Design Notes

- **One gate, not three.** The gate stays at the shared `process_issue_inplace` choke
  point (it already covers decomposed children created mid-run and is shared with
  `ll-auto`). The loops only *observe and route* its outcome — they do not re-run it. This
  deliberately avoids the heavier alternative of hoisting an explicit `proof-first-task`
  preflight state into each loop, which would duplicate gate logic across two layers and
  require keeping double-gate suppression in sync.
- A gate-blocked issue is **left in place** (not skipped-as-failed) so it re-surfaces once
  its dependencies are proven via `/ll:explore-api`.
- Ordering: `check_learning_gate` runs **before** `check_impl_auth` so a gate block is
  never misattributed as an auth failure or a generic implementation failure.

## Files Changed

- `scripts/little_loops/issue_manager.py` — `LEARNING_GATE_BLOCKED` stdout marker
- `scripts/little_loops/loops/lib/common.yaml` — `ll_auto_learning_gate_check` fragment
- `scripts/little_loops/loops/rn-remediate.yaml` — `check_learning_gate`, `emit_learning_gate_blocked`, skip flag, context+parameter
- `scripts/little_loops/loops/rn-implement.yaml` — `route_rem_learning_gate`, `record_learning_gate_blocked`, report tally, skip passthrough
- `scripts/little_loops/loops/autodev.yaml` — `check_learning_gate`, `mark_gate_blocked`, ledger + summary, skip flag
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — skip-knob context + passthrough to autodev
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — skip-knob context + passthrough
- `.ll/ll-config.json` — `learning_tests.enabled: true`
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — outcome-token table + consistency note
- `scripts/tests/test_builtin_loops.py` — `TestLearningGateConsistency` (new) + updated routing tests
- `scripts/tests/test_issue_manager.py` — marker-emission unit test

## Verification Results

- All 5 changed loops pass `ll-loop validate` (including the meta-loop MR rules).
- `mypy` and `ruff` clean on the changed Python files.
- Full suite: 13164 passed, 23 skipped. The only failures (3 deterministic doc-drift
  assertions in `README.md` / `CONTRIBUTING.md`) are **pre-existing** — confirmed by
  re-running them with the session changes stashed; they are unrelated to this work.
- New tests: `TestLearningGateConsistency` (12 tests across the shared fragment, both
  loop routers, the report tally, and end-to-end skip threading) + a marker-emission
  unit test in `test_issue_manager.py`.

## Impact

- **Priority**: P2 — consistency + observability fix across the three primary
  implementation loops; not blocking, but it removes a real "silent failure" foot-gun once
  `learning_tests.enabled` is on.
- **Effort**: Medium — one stdout marker, one shared fragment, two new routing states per
  loop, report tally, and skip-knob plumbing across five YAMLs, plus tests.
- **Risk**: Low — additive; the gate itself is unchanged and config-gated by
  `learning_tests.enabled` (defaults to `false`), and the skip knob defaults to off.
- **Breaking Change**: No.

## Related

- ENH-2319 — per-issue learning gate wired into `ll-auto` (`process_issue_inplace`)
- ENH-2353 — `ENV_NOT_READY` auth fast-fail split (the pattern this mirrors)
- ENH-2219 / ENH-2208 — `proof-first-task` gate and shared staleness helpers

## Labels

`enhancement`, `loops`, `learning-tests`, `consistency`, `observability`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-06-30
- **Status**: Completed (manual implementation, interactive session)
- **Implementation**: Added a distinct `LEARNING_GATE_BLOCKED` outcome and a uniform
  `skip_learning_gate` knob across `rn-implement` / `rn-remediate` / `autodev` /
  `auto-refine-and-implement` / `sprint-refine-and-implement`, keeping the single
  `process_issue_inplace` learning gate as the source of truth.

### Verification
- `ll-loop validate` passes for all 5 changed loops; full pytest suite green except
  pre-existing, unrelated doc-drift failures; `mypy` + `ruff` clean.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-30T18:37:57 - `5b28319a-9fe2-441d-af7f-729f50d0b512.jsonl`
