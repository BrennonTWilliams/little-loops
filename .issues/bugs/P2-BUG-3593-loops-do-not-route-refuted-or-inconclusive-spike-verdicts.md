---
id: BUG-3593
type: BUG
title: Loops do not route refuted or inconclusive spike verdicts
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T03:40:43Z'
parent: EPIC-3565
supersedes:
- BUG-3572
blocked_by:
- BUG-3591
- BUG-3592
blocks:
- ENH-3577
---

# BUG-3593: Loops do not route refuted or inconclusive spike verdicts

## Summary

Part (c) of BUG-3572's split: loop routing. After `/ll:spike`, neither loop branches on the
result. `refine-to-ready-issue.yaml` `run_spike` returns `next`/`on_error: confidence_check`,
and autodev's `run_spike` → `count_repair_cycle_spike` → `clear_scores_before_spike` →
`rerun_confidence_after_spike` → `check_scores_present_spike` → `enqueue_or_skip` (BUG-3588
chain) rescores every outcome the same way. Once BUG-3592 produces a verdict, the loops must
send a refuted spike to a decision **before any rescoring**, stop an inconclusive spike at a
named human-needed deferral, re-arm one new spike after a decision replaces the refuted
approach, and bound the whole cycle with a per-issue spike budget.

The full design record is BUG-3572 (cancelled, superseded by this issue, BUG-3591 and
BUG-3592). Its Proposed Solution items 5–8 are the source of this child, amended here for
refine-to-ready running nested inside autodev.

## Current Behavior

- refine-to-ready: a spike always re-enters `confidence_check`. With BUG-3591's cap, a
  failed spike falls `check_outcome` → `check_decision_needed` (no) → `check_spike_needed`
  (no) → `check_missing_artifacts` → toward `breakdown_issue`. `confidence_check` →
  `check_readiness` runs **before** `check_outcome`, so a readiness drop after rescoring
  routes to `refine_followup` / `breakdown_issue` and never reaches the decision gate.
- autodev never reaches a decision after a spike: `recheck_after_size_review` re-reads
  `decision_needed` only to defer it as `decision_unresolved` (ENH-2936), and
  `check_decision_before_size_review` → `resolve_decision` is reachable only from
  `recheck_scores`.
- The ENH-1415 `autodev-decide-ran` marker is read only in `decide_current`, and
  `check_decide_rate_limited` is a 429 check, so refute → decide → re-arm → spike → refute
  would cycle within one run, bounded only by the FEAT-2751 stagnation backstop.

## Expected Behavior

- A refuted spike routes to a decision before any rescoring in both loops, whatever its
  readiness score.
- An inconclusive spike keeps the cap, is not re-spiked automatically, and stops at
  `record_spike_inconclusive` with deferral code `spike_inconclusive` — including when
  refine-to-ready runs nested under autodev.
- Resolving the decision re-arms exactly one new spike on the chosen approach.
- One per-issue spike budget, shared by every `run_spike` entry path in both loops, bounds
  re-runs.

## Steps to Reproduce

1. With BUG-3591 and BUG-3592 landed, take an issue with `unproven_mechanism: true` and `spike_needed: true` whose spike refutes the mechanism
2. Run `ll-loop run refine-to-ready-issue <ID>`; `/ll:spike --auto` writes `spike_refuted: true` and `decision_needed: true`
3. Observe `run_spike` → `confidence_check` rescore the issue first; if readiness drops, `check_readiness.on_no` routes to `refine_followup` / `breakdown_issue` and the decision is never reached

## Root Cause

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`, `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `run_spike` (both loops); autodev `count_repair_cycle_spike`
- **Cause**: post-spike transitions are unconditional; no state reads the spike outcome.

## Proposed Solution

1. **`route_spike_verdict`** — a new three-way state reading `spike_refuted` /
   `spike_completed` / `spike_attempted` (inline python over `ll-issues show --json`, per
   the two-field predicate convention):
   - **refine-to-ready**: `run_spike.next`/`on_error` → `route_spike_verdict`: refuted →
     `check_decide_attempts` (→ `resolve_decision_pre_breakdown`, whose `on_success` already
     returns to `confidence_check`); inconclusive → `record_spike_inconclusive`; proven →
     `confidence_check` (unchanged).
   - **autodev**: insert between `count_repair_cycle_spike` and `clear_scores_before_spike`:
     refuted → `check_spike_budget` → `resolve_decision`; inconclusive →
     `record_spike_inconclusive`; proven → `clear_scores_before_spike` (BUG-3588's clear →
     rescore → `check_scores_present_spike` chain and its `on_yes: enqueue_or_skip` edge
     stay unchanged). No path that proceeds to scoring may bypass
     `check_scores_present_spike`.
   - **Scores on the refuted path**: autodev's refuted branch skips BUG-3588's clear, so the
     issue keeps its pre-spike scores until `resolve_decision` → `mark_decide_ran` →
     `rerun_confidence_after_decide` rescores; on resolve failure,
     `check_decide_rate_limited` → `record_decision_unresolved` reads no scores. Verify no
     path from the refuted branch reaches `enqueue_or_skip` without a fresh rescoring.
   - Not decidable (no remaining option after BUG-3592's exclusion) → the resolve-decision
     oracle fails → `record_decision_unresolved` in both loops.
2. **Per-issue spike budget, shared across nesting.** autodev runs refine-to-ready as
   `refine_current` with `context_passthrough: true` (`autodev.yaml:529-530`), so the child
   shares autodev's `${context.run_dir}`. Use one counter file `spike-runs-<ID>` in the run
   dir, incremented by every entry into `run_spike` in either loop, and checked before every
   `run_spike` entry (autodev `check_spike_needed`, `check_spike_needed_before_skip`,
   `dispatch_pre_deferral_remedy`; refine-to-ready `check_spike_needed`):
   - **refine-to-ready spikes only when the counter is 0** (its first spike for the issue in
     this top-level run, standalone or nested).
   - **autodev spikes when the counter is < 2** (original + one re-armed spike).
   - The counter is **never reset per issue**. refine-to-ready's `resolve_issue` currently
     deletes `refine-to-ready-spike-ran` (`refine-to-ready-issue.yaml:~157`); drop that
     marker and its reset — carrying the reset over to the new counter would let the nested
     child wipe autodev's budget.
   - A refuted verdict with the budget spent routes to `record_decision_unresolved`, not
     `resolve_decision`.
3. **Re-arm rule** (in `/ll:decide-issue`, so it covers every caller via
   `oracles/resolve-decision`: autodev `resolve_decision` / `resolve_decision_direct` /
   `resolve_decision_at_dequeue` and refine-to-ready `resolve_decision_pre_breakdown`):
   remove `spike_attempted` and `spike_refuted` only when **both** the issue carries
   `spike_refuted: true` **and** `decision_needed` was cleared in this invocation. It must
   not fire when the oracle finishes `done` with a residual group still armed
   (`resolve-decision.yaml` `check_residual_decision`). `unproven_mechanism` stays true, so
   the cap and `spike_needed` re-apply. When the new spike runs:
   - **refine-to-ready standalone**: counter is 1, so no second spike this run; the chosen
     approach stays capped and the run ends not-ready. The new spike runs on the next
     top-level run (fresh run dir).
   - **under autodev (refine-to-ready nested or autodev's own path)**: autodev's
     `check_spike_needed` (predicate `spike_needed == 'true' and spike_attempted != 'true'`)
     can run the re-armed spike in the **same** run, since the counter (1) is < 2.
   - Set-only flag writes are safe: `ll-issues set-flags` cannot clear the spike's
     `decision_needed` (`set_flags.py:apply_flags_from_notes`).
4. **`record_spike_inconclusive`** in each loop, modeled on `record_decision_unresolved`
   (skip if already done/cancelled; `ll-issues set-status <ID> deferred --by automation
   --reason spike_inconclusive`), echoing the classifier's cause and
   `[SPIKE_INCONCLUSIVE] <ID> — spike could not reach a verdict (<cause>); fix the cause,
   then run /ll:spike <ID> --force and re-run to resurface`:
   - **autodev**: appends `<ID>  spike_inconclusive` to `autodev-skipped.txt`, removes
     `autodev-inflight`, then `dequeue_next`.
   - **refine-to-ready**: writes `spike_inconclusive` to `refine-terminal-class` and to a
     `refine-spike-inconclusive.txt` ledger in the run dir, then `failed`.
5. **autodev `skip_inflight` must recognise the nested stop.** It is the only other reader
   of `refine-terminal-class` (`autodev.yaml:~556-590`) and today treats any class other than
   `infra` as quality, ledgering `refine_failed`. A nested refine-to-ready
   `spike_inconclusive` stop would be mislabelled and double-counted (the child already
   deferred it) — the same failure BUG-3390 fixed for `decision_unresolved` via the
   `autodev-decision-unresolved.txt` ledger check. Add the equivalent check against
   `refine-spike-inconclusive.txt`: skip the `refine_failed` ledger line, clear
   `autodev-inflight`, and let `finalize_done` report it under its own bucket.
   (`auto-refine-and-implement.yaml` does **not** read `refine-terminal-class`; it needs no
   change.)
6. **`recheck_after_size_review` remedy selector** (`spike_attempted == 'true'` → no remedy)
   must not treat a refuted issue as remedy-exhausted when a decision is still available.

## Program Design

### Types

- `DeferReason.SPIKE_INCONCLUSIVE = "spike_inconclusive"` — new member of the existing `DeferReason` enum (`issue_lifecycle.py`, beside `DECISION_UNRESOLVED`). `ll-issues set-status --reason` validates against this enum, and the loop states call it with `|| true`, so an unregistered code would be rejected **silently**.
- `spike-runs-<ID>` — run-dir counter file (integer text), shared by both loops.

### Signatures

- `cmd_show(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues show --json`; `route_spike_verdict` reads `spike_refuted` / `spike_completed` / `spike_attempted` from it (BUG-3592 adds `spike_refuted` to the output).
- `cmd_set_status(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues set-status`; `record_spike_inconclusive` calls it with `deferred --by automation --reason spike_inconclusive`.

### Call Path

`cmd_show` -> `parse_frontmatter`; `cmd_set_status` -> `DeferReason`

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — `DeferReason.SPIKE_INCONCLUSIVE`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `run_spike.next`/`on_error` → `route_spike_verdict`; `record_spike_inconclusive`; `check_spike_needed` switches to the shared counter (`== 0`); remove `refine-to-ready-spike-ran` and its reset in `resolve_issue`
- `scripts/little_loops/loops/autodev.yaml` — `route_spike_verdict` after `count_repair_cycle_spike`; `check_spike_budget`; `record_spike_inconclusive`; counter check (`< 2`) at `check_spike_needed`, `check_spike_needed_before_skip`, `dispatch_pre_deferral_remedy`; `skip_inflight` spike-inconclusive ledger check; `finalize_done` bucket; `recheck_after_size_review` selector
- `skills/decide-issue/SKILL.md` — re-arm step
- `docs/reference/DEFERRAL_CODES.md` — `spike_inconclusive` row
- `docs/guides/LOOPS_REFERENCE.md`, `scripts/little_loops/loops/README.md` (~L85 `spike-gate` row)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — `check_residual_decision` (re-arm must not fire on a residual `done`)
- `scripts/little_loops/loops/spike-gate.yaml` — completion-keyed; confirm a refuted issue stays blocked
- `scripts/little_loops/cli/issues/set_flags.py` — `_spike_not_already_flagged()` stays attempt-bound; re-arm removing `spike_attempted` re-enables `spike_needed` as intended

### Tests
- `scripts/tests/test_builtin_loops.py` / `test_refine_to_ready_*` — `route_spike_verdict` three-way routing via a stub `ll-issues` on `PATH` executing the real state `action`; refuted reaches the decision with readiness **both passing and failing**; inconclusive → `record_spike_inconclusive` → `failed`, never `breakdown_issue`
- `scripts/tests/test_autodev_loop.py`, `test_autodev_decision_gate.py` — refuted → `resolve_decision` before rescoring; proven still passes `check_scores_present_spike`; remedy selector with `spike_refuted`; nested `spike_inconclusive` is not ledgered `refine_failed`
- Budget tests: repeated refutation (refute → decide → re-arm → refute) stops with `decision_unresolved`; nested refine-to-ready does not reset autodev's counter; standalone refine-to-ready runs at most one spike
- decide-issue contract test — re-arm fires only when refuted **and** `decision_needed` cleared; not on a residual-group `done`
- deferral-code coverage for `spike_inconclusive` wherever `DEFERRAL_CODES.md` rows are pinned
- `scripts/tests/test_set_status_cli.py::test_set_status_deferred_stamps_autodev_reason_codes` (~341) — add `spike_inconclusive` to the parametrized reason codes

## Implementation Steps

1. Shared `spike-runs-<ID>` counter; remove `refine-to-ready-spike-ran`
2. `route_spike_verdict` + `record_spike_inconclusive` in refine-to-ready
3. Same in autodev, plus `check_spike_budget`, `skip_inflight` ledger check, `finalize_done` bucket, remedy selector
4. Decide-issue re-arm
5. Routing, budget, nesting and re-arm tests; docs; `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply`

## Acceptance Criteria

- [ ] A refuted spike routes to a decision before any rescoring in both autodev and refine-to-ready, whatever its readiness score; in autodev it reaches `resolve_decision` rather than a `decision_unresolved` deferral, while budget remains
- [ ] An inconclusive spike keeps the cap, is not re-spiked automatically, and stops at `record_spike_inconclusive` in both loops (deferral code `spike_inconclusive`, not decomposition), with a message naming `/ll:spike <ID> --force`
- [ ] Under autodev, a nested refine-to-ready `spike_inconclusive` stop is not ledgered as `refine_failed` or counted twice
- [ ] Resolving a decision on a refuted issue re-arms exactly one new spike on the chosen approach — in the same run under autodev (nested or not), on the next run for standalone refine-to-ready; a residual-group `done` does not re-arm
- [ ] One per-issue spike counter, shared by every `run_spike` entry in both loops and never reset per issue, bounds re-runs; a repeated refutation within one run stops with `decision_unresolved`
- [ ] autodev's proven path still passes BUG-3588's score-presence gate (`check_scores_present_spike`)

## Impact

- **Priority**: P2 - without routing, refuted/inconclusive spikes decompose or defer silently instead of reaching a decision or a named stop
- **Effort**: Medium - new states in two loops, a shared budget, one decide-issue step
- **Risk**: Medium - routing changes in autodev and refine-to-ready; oscillation after re-arm rests on the budget plus the FEAT-2751 backstop
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-25 | Priority: P2
