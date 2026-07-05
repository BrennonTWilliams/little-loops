---
id: ENH-2487
title: Config-gate rn-implement auto-prove on learning_tests.enabled and apply it at both gate sites (all depths)
type: ENH
priority: P2
status: open
captured_at: '2026-07-05T23:10:00Z'
discovered_date: '2026-07-05'
discovered_by: audit-loop-run
depends_on:
- ENH-2431
relates_to:
- ENH-2430
- ENH-2406
- ENH-2319
labels:
- learning-tests
- rn-implement
- automation
- config
---

# ENH-2487: Config-gate rn-implement auto-prove on `learning_tests.enabled` and apply it at both gate sites (all depths)

## Summary

`ENH-2431` added one-attempt auto-prove to `rn-implement`'s **pre-dequeue**
learning gate (`check_learning_ready`), but shipped it **opt-in / default-off**
behind the `auto_prove_learning_gate` context flag, and wired it into **only one
of the two** learning-gate sites in the loop. As a result, a run against an
issue with an unproven target (e.g. FEAT-2478's `anthropic` target) exits
immediately with `learning_gate_blocked_pre_dequeue: 1` and implements nothing,
even though `learning_tests.enabled: true` in `.ll/ll-config.json`.

Two changes:

1. **Config-drive auto-prove.** When `learning_tests.enabled: true`, auto-prove
   should be the default (not a separate default-off context flag). Gate it on a
   new `learning_tests.auto_prove` config key (default `true`) so budget-conscious
   callers retain an opt-out, per the deferral note in `ENH-2431`.
2. **Apply at both gate sites (more than depth 1).** The prove attempt currently
   exists only at the shallow pre-dequeue `check_learning_ready`. The deeper
   remediation-path gate `route_rem_learning_gate` (fires after `rn-remediate`
   runs `ll-auto --only` and hits the ENH-2319 JIT gate) has **no** prove path —
   it only tags `LEARNING_GATE_BLOCKED` and records the block. Auto-prove must
   also cover this site so targets surfaced deeper in the pipeline (and in
   decomposed children that reach remediation) are proven, not dead-ended.

## Current Behavior

`scripts/little_loops/loops/rn-implement.yaml`:

- `context.auto_prove_learning_gate: ""` (line ~45) — default off.
- `check_learning_ready` reads `auto_prove = "${context.auto_prove_learning_gate}"`
  (line ~520); the prove branch is `if not proven and auto_prove:` (line ~568).
  Never fires unless the flag is explicitly set on the CLI.
- `route_rem_learning_gate` (line ~898) → `record_learning_gate_blocked`
  (line ~1057): no prove attempt at all.
- No loop reads `learning_tests.enabled`; the config-schema `learning_tests`
  block (`config-schema.json:949`) has **no** `auto_prove` key.

Evidence — run `2026-07-05T224821-rn-implement` (input FEAT-2478):
`state.json` captured `[LEARNING_NOT_READY] FEAT-2478 has unproven
targets:anthropic`; `summary.json` reported `implemented: 0`,
`learning_gate_blocked_pre_dequeue: 1`. `context.auto_prove_learning_gate` was
empty, so the loop parked the issue and exited in 11 iterations / 661ms.

## Expected Behavior

With `learning_tests.enabled: true` and `learning_tests.auto_prove: true`
(default): a dequeued (or remediation-stage) issue with an unproven required
target triggers one `ll-learning-tests prove <target>` attempt before being
parked, at **both** gate sites, at every recursion depth. Only if the prove
attempt fails does the issue route to `mark_learning_blocked` /
`record_learning_gate_blocked`.

## Acceptance Criteria

- [ ] `config-schema.json` `learning_tests` gains `auto_prove` (boolean, default
      `true`) with a description; defaults source from the schema (not hardcoded).
- [ ] `rn-implement` `init` reads `learning_tests.enabled` + `learning_tests.auto_prove`
      from config and seeds the context default; the standalone
      `auto_prove_learning_gate` CLI override still works (explicit override wins).
- [ ] Auto-prove fires at `check_learning_ready` **and** `route_rem_learning_gate`
      (or an equivalent pre-block prove step on the remediation path).
- [ ] A run against an issue with an unproven target and default config attempts
      proving instead of parking pre-dequeue (regression test over the
      FEAT-2478-style path).
- [ ] `python -m pytest scripts/tests/` passes (extend `test_builtin_loops.py`
      learning-gate coverage).

## Impact

Unattended `rn-implement` / `autodev` / `auto-refine-and-implement` runs against
any issue whose required learning target is cold-registry currently no-op
(implement 0, park 1) unless the operator remembers a non-discoverable context
flag. Config-gating on the already-enabled `learning_tests` feature makes the
automation self-healing by default and removes a silent manual round-trip.

## Scope Boundaries

- **In scope:** `config-schema.json` `learning_tests.auto_prove` key;
  `rn-implement.yaml` `init` config read + both gate sites; regression tests.
- **Out of scope:** changing `ll-learning-tests prove` internals (ENH-2430);
  altering the ENH-2319 JIT detection itself; auto-prove in `ll-auto`/`ll-parallel`
  Python paths (loop-only here); budget/parallelism tuning of the prove agent.

## Status

open — captured 2026-07-05 from an `/ll:audit-loop-run` of the FEAT-2478 run.

## Notes

- Do not re-introduce the 30-min prove timeout inline without a budget guard —
  reuse the `timeout=1800` structure ENH-2431 already added (line ~577).
- Confirm decomposed children re-entering `dequeue_next` inherit the same
  config-gated behavior (they already re-pass `check_learning_ready`).
- The `auto_prove_learning_gate` context flag can remain as an explicit
  per-run override layered over the config default.
