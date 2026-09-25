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
chain) rescores every outcome the same way. Now that BUG-3592 produces a verdict, the loops
must send a refuted spike to a decision **before any rescoring**, stop an inconclusive spike
at a named human-needed deferral, treat a spike that wrote no verdict as infra, re-arm one new
spike after a decision replaces the refuted approach, run that re-armed spike **before** any
decomposition, and bound the whole cycle with a per-issue spike budget.

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
  readiness score and whether or not a decision was already resolved earlier in the run.
- An inconclusive spike keeps the cap, is not re-spiked automatically, and stops at
  `record_spike_inconclusive` with deferral code `spike_inconclusive` — including when
  refine-to-ready runs nested under autodev.
- A spike that wrote no verdict (crash/kill before write-back) is classified infra, not
  inconclusive or refuted.
- Resolving the decision re-arms exactly one new spike on the chosen approach, and that
  spike runs before any size review / decomposition.
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

1. **`route_spike_verdict`** — a new four-way state (inline python over
   `ll-issues show --json`, per the two-field predicate convention). Predicates are
   evaluated **in this order**:
   1. **refuted** — `spike_attempted == 'true'` and `spike_refuted == 'true'`
   2. **proven** — `spike_attempted == 'true'` and `spike_completed == 'true'`
   3. **inconclusive** — `spike_attempted == 'true'`, neither of the above
   4. **no verdict** — `spike_attempted != 'true'` (the skill crashed or was killed before
      Phase 6; on a re-armed issue every spike flag is absent). This is the case the removed
      `refine-to-ready-spike-ran` marker (BUG-3553) guarded; the budget counter (item 2)
      still prevents a re-spike.

   Routing:
   - **refine-to-ready**: `run_spike.next`/`on_error` → `route_spike_verdict`:
     refuted → `check_spike_budget` → `resolve_decision_pre_breakdown` (whose `on_success`
     already returns to `confidence_check`). The refuted edge **bypasses
     `check_decide_attempts`**: the loop decides before it spikes, so a decision resolved
     earlier in the run leaves the decide counter at 1 and a second
     `check_decide_attempts` reading would defer a refuted issue as `decision_unresolved`
     without ever reaching a decision. The spike counter bounds this edge instead.
     inconclusive → `record_spike_inconclusive`; proven → `confidence_check` (unchanged);
     no verdict → `mark_spike_no_verdict_infra` (writes `infra` to `refine-terminal-class`,
     echoes `[SPIKE_NO_VERDICT] <ID>`, then `failed`; modeled on `mark_evidence_absent_infra`).
   - **autodev**: insert between `count_repair_cycle_spike` and `clear_scores_before_spike`:
     refuted → `check_spike_budget` → `resolve_decision`; inconclusive →
     `record_spike_inconclusive`; proven → `clear_scores_before_spike` (BUG-3588's clear →
     rescore → `check_scores_present_spike` chain and its `on_yes: enqueue_or_skip` edge
     stay unchanged); no verdict → `mark_spike_no_verdict_infra` (modeled on
     `mark_scores_absent_infra`: ledger to `autodev-spike-no-verdict.txt`, clear
     `autodev-inflight`, `dequeue_next`, **no deferral**). No path that proceeds to scoring
     may bypass `check_scores_present_spike`.
   - **Scores on the refuted path**: autodev's refuted branch skips BUG-3588's clear, so the
     issue keeps its pre-spike scores until `resolve_decision` → `mark_decide_ran` →
     `rerun_confidence_after_decide` rescores; on resolve failure,
     `check_decide_rate_limited` → `record_decision_unresolved` reads no scores. Verify no
     path from the refuted branch reaches `enqueue_or_skip` without a fresh rescoring.
   - Not decidable (no remaining option after BUG-3592's exclusion, `ALL_OPTIONS_REFUTED`)
     → the resolve-decision oracle fails → `record_decision_unresolved` in both loops.
2. **Per-issue spike budget, shared across nesting.** autodev runs refine-to-ready as
   `refine_current` with `context_passthrough: true` (`autodev.yaml:529-530`), so the child
   shares autodev's `${context.run_dir}` (`recursive-refine.yaml` `run_refine` nests it the
   same way). Use one counter file `spike-runs-<ID>` in the run dir:
   - **Increment point**: the counter is incremented on the on_yes branch of every gate
     that enters `run_spike`, **before** `run_spike` runs (the same place the
     `refine-to-ready-spike-ran` marker is written today), so a crashed spike still counts.
   - **Gate**: every `run_spike` entry spikes only when the counter is **< 2** (original +
     one re-armed spike) — the same threshold in both loops. Entries: autodev
     `check_spike_needed`, `check_spike_needed_before_skip`, `dispatch_pre_deferral_remedy`,
     and the new `check_rearmed_spike_after_decide` (item 3); refine-to-ready
     `check_spike_needed`.
   - **`check_spike_budget`** (refuted edge, both loops): counter < 2 → decision; otherwise
     → `record_decision_unresolved`. After the original spike the counter is 1 (decide);
     after the re-armed spike it is 2 (a second refutation defers).
   - The counter is **never reset per issue**. refine-to-ready's `resolve_issue` currently
     deletes `refine-to-ready-spike-ran` (`refine-to-ready-issue.yaml:157`); drop that
     marker and its reset — carrying the reset over to the new counter would let the nested
     child wipe autodev's budget.
   - **Budget-spent fall-throughs**: refine-to-ready `check_spike_needed` → its existing
     `on_no` (`check_missing_artifacts`); autodev `check_spike_needed` → existing `on_no`;
     `check_spike_needed_before_skip` → existing `on_no` (`check_reconcile_needed`);
     `dispatch_pre_deferral_remedy` with a `spike` token → `reconcile_current` (its existing
     `on_no`).
   - **Step budget**: refine-to-ready `max_steps` 60 → 70, with the usual budget comment
     (refuted → budget → resolve → `confidence_check` → `check_readiness` → `check_outcome`
     plus a second `check_spike_needed` → `run_spike` → `route_spike_verdict` pass).
3. **Re-arm, and run the re-armed spike before decomposition.**
   - **Re-arm is a deterministic loop step, not decide-issue prose.** There is no CLI verb
     that removes a frontmatter flag, and "decision_needed was cleared in this invocation"
     should be a routing fact, not a model judgment. Add a new `ll-issues` subcommand, `rearm-spike <ID>`: if
     the issue carries `spike_refuted: true`, remove `spike_attempted` and `spike_refuted`
     (`frontmatter.remove_frontmatter_keys`) and print `[SPIKE_REARMED] <ID>`; otherwise a
     no-op. Always exit 0 on a resolvable ID.
   - Call it from a new `rearm_refuted_spike` shell state in
     `oracles/resolve-decision.yaml`, inserted on `assert_decision_cleared.on_no` (the
     flag-cleared edge) before `done`. The residual-group path
     (`assert_decision_cleared.on_yes` → `check_residual_decision` → `done`) never passes
     through it, so a residual `done` cannot re-arm. This covers every loop caller: autodev
     `resolve_decision` / `resolve_decision_direct` / `resolve_decision_at_dequeue` and
     refine-to-ready `resolve_decision_pre_breakdown`. `on_error` → `done` (the decision
     itself is resolved; a failed re-arm just leaves the spike un-re-run).
   - `unproven_mechanism` stays true, so the cap and `spike_needed` re-apply. Set-only flag
     writes are safe: `ll-issues set-flags` cannot clear the spike's `decision_needed`
     (`set_flags.py:apply_flags_from_notes`).
   - **refine-to-ready (standalone or nested)**: after the decision, `confidence_check` →
     cap → `check_outcome` no → `check_decision_needed` no → `check_spike_needed` sees
     `spike_attempted` absent and counter 1 < 2 → runs the re-armed spike in the same run.
     (With a `== 0` gate it would instead fall to `check_missing_artifacts` →
     `breakdown_issue` and decompose the issue — nested under autodev, before autodev ever
     saw it.)
   - **autodev**: `resolve_decision` → `mark_decide_ran` → rescore →
     `recheck_after_decide.on_no` currently goes straight to `snap_and_size_review`, so the
     re-armed spike would run only if size review declined to decompose. Add
     `check_rearmed_spike_after_decide` on `recheck_after_decide.on_no`: predicate
     `spike_needed == 'true' and spike_attempted != 'true'` and counter < 2 → snapshot
     `autodev-pre-spike-readiness.txt`, increment the counter, → `run_spike`; otherwise →
     `snap_and_size_review` (unchanged). `recheck_after_decide.on_error` stays
     `snap_and_size_review`.
   - Manual `/ll:decide-issue` does not re-arm. Its Phase 7 next-step line for an issue that
     carries a resolved `**Refuted option**:` marker points at `/ll:spike <ID> --force`.
4. **`record_spike_inconclusive`** in each loop, modeled on `record_decision_unresolved`
   (skip if already done/cancelled; `ll-issues set-status <ID> deferred --by automation
   --reason spike_inconclusive`), echoing the classifier's cause and
   `[SPIKE_INCONCLUSIVE] <ID> — spike could not reach a verdict (<cause>); fix the cause,
   then run /ll:spike <ID> --force and re-run to resurface`. Both loops write the ID to one
   shared ledger, `autodev-spike-inconclusive.txt` in the run dir — the same pattern as
   `autodev-decision-unresolved.txt`, which refine-to-ready's `record_decision_unresolved`
   already writes directly:
   - **autodev**: appends the ID to `autodev-spike-inconclusive.txt` (not
     `autodev-skipped.txt`), removes `autodev-inflight`, then `dequeue_next`. autodev's init
     truncates the ledger beside `autodev-decision-unresolved.txt` (`autodev.yaml:68`).
   - **refine-to-ready**: writes `spike_inconclusive` to `refine-terminal-class`, appends the
     ID to `autodev-spike-inconclusive.txt`, then `failed`.
5. **autodev `skip_inflight` must recognise the nested stop.** It is the only other reader
   of `refine-terminal-class` (`autodev.yaml:546-590`) and today treats any class other than
   `infra` as quality, ledgering `refine_failed`. A nested refine-to-ready
   `spike_inconclusive` stop would be mislabelled and double-counted (the child already
   deferred it) — the same failure BUG-3390 fixed for `decision_unresolved` via the
   `autodev-decision-unresolved.txt` ledger check. Add the equivalent `grep -qxF` check
   against `autodev-spike-inconclusive.txt`: skip the `refine_failed` ledger line, clear
   `autodev-inflight`, exit 0. `finalize_done` reports the ledger under its own
   `Spike-inconclusive (N): …` bucket (and `autodev-spike-no-verdict.txt` under an infra
   bucket), mirroring the `Decision-unresolved` line (`autodev.yaml:~2824`, `~2898`).
   (`auto-refine-and-implement.yaml` does **not** read `refine-terminal-class`; it needs no
   change. `recursive-refine.yaml` routes a failed child to `gate_recursion`; confirm a
   deferred `spike_inconclusive` child is not re-enqueued.)
6. **`recheck_after_size_review` remedy selector** (`autodev.yaml:~2638-2654`). A refuted
   issue never reaches the selector with `decision_needed` still armed: `route_spike_verdict`
   sends it to `resolve_decision` first, and the ENH-2936 `decision_needed` branch
   (`autodev.yaml:2580-2589`) runs before the selector. The live risk is the reverse: after
   re-arm, `spike_attempted` is absent, so the selector can pick `spike` →
   `dispatch_pre_deferral_remedy` → `run_spike`. Pass the spike counter into the selector
   and treat counter ≥ 2 as spike-exhausted (fall to `reconcile` if not attempted, else
   `''`); `dispatch_pre_deferral_remedy`'s own budget check (item 2) is the backstop.

## Program Design

### Types

- `DeferReason.SPIKE_INCONCLUSIVE = "spike_inconclusive"` — new member of the existing `DeferReason` enum (`issue_lifecycle.py`, beside `DECISION_UNRESOLVED`). `ll-issues set-status --reason` validates against this enum, and the loop states call it with `|| true`, so an unregistered code would be rejected **silently**.
- `spike-runs-<ID>` — run-dir counter file (integer text), shared by both loops.
- `autodev-spike-inconclusive.txt` — run-dir ledger (one ID per line), written by both loops' `record_spike_inconclusive`.

### Signatures

- `cmd_show(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues show --json`; `route_spike_verdict` reads `spike_refuted` / `spike_completed` / `spike_attempted` from it (BUG-3592 added `spike_refuted` to the output).
- `cmd_set_status(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues set-status`; `record_spike_inconclusive` calls it with `deferred --by automation --reason spike_inconclusive`.
- `remove_frontmatter_keys(content: str, keys: Iterable[str]) -> str` — existing helper in `frontmatter.py`; the new `rearm-spike` subcommand of `ll-issues` uses it to drop `spike_attempted` / `spike_refuted`.

### Call Path

`cmd_show` -> `parse_frontmatter`; `cmd_set_status` -> `DeferReason`; `rearm_spike` -> `parse_frontmatter` -> `remove_frontmatter_keys`

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — `DeferReason.SPIKE_INCONCLUSIVE`
- `scripts/little_loops/cli/issues/deferred_triage.py` — `_REASON_RANK["spike_inconclusive"]` (otherwise it sorts as an unknown code); rank beside `decision_unresolved`
- `scripts/little_loops/cli/issues/__init__.py` + `scripts/little_loops/cli/issues/rearm_spike.py` (new file) — the `rearm-spike <ID>` subcommand
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — `rearm_refuted_spike` on `assert_decision_cleared.on_no`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `run_spike.next`/`on_error` → `route_spike_verdict`; `check_spike_budget`; `record_spike_inconclusive`; `mark_spike_no_verdict_infra`; `check_spike_needed` switches to the shared counter (`< 2`, increment on the yes branch); remove `refine-to-ready-spike-ran` and its reset in `resolve_issue`; `max_steps` 60 → 70; header routing comment
- `scripts/little_loops/loops/autodev.yaml` — `route_spike_verdict` after `count_repair_cycle_spike`; `check_spike_budget`; `record_spike_inconclusive`; `mark_spike_no_verdict_infra`; `check_rearmed_spike_after_decide` on `recheck_after_decide.on_no`; counter check (`< 2`) + increment at `check_spike_needed`, `check_spike_needed_before_skip`, `dispatch_pre_deferral_remedy`; ledger init; `skip_inflight` spike-inconclusive ledger check; `finalize_done` buckets; remedy selector budget check
- `skills/decide-issue/SKILL.md` — Phase 7 next-step line for a resolved refuted-option marker (`/ll:spike <ID> --force`); no flag edits
- `docs/reference/DEFERRAL_CODES.md` — `spike_inconclusive` row
- `docs/reference/CLI.md` — the `rearm-spike` subcommand
- `docs/guides/LOOPS_REFERENCE.md`, `scripts/little_loops/loops/README.md` (~L85 `spike-gate` row)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — `check_residual_decision` (residual `done` must not pass through `rearm_refuted_spike`)
- `scripts/little_loops/loops/recursive-refine.yaml` — nests refine-to-ready with `context_passthrough: true` (shares the counter); `run_refine.on_failure` → `gate_recursion`
- `scripts/little_loops/loops/spike-gate.yaml` — completion-keyed; confirm a refuted issue stays blocked
- `scripts/little_loops/cli/issues/set_flags.py` — `_spike_not_already_flagged()` stays attempt-bound; re-arm removing `spike_attempted` re-enables `spike_needed` as intended

### Tests
- `scripts/tests/test_builtin_loops.py` / `test_refine_to_ready_*` — `route_spike_verdict` four-way routing via a stub `ll-issues` on `PATH` executing the real state `action`; refuted reaches the decision with readiness **both passing and failing**, and **with the decide counter already at 1**; inconclusive → `record_spike_inconclusive` → `failed`, never `breakdown_issue`; no verdict → `mark_spike_no_verdict_infra` (class `infra`); after re-arm, `check_spike_needed` runs the second spike instead of reaching `breakdown_issue`
- `scripts/tests/test_autodev_loop.py`, `test_autodev_decision_gate.py` — refuted → `resolve_decision` before rescoring; proven still passes `check_scores_present_spike`; `recheck_after_decide.on_no` with a re-armed spike → `run_spike`, not `snap_and_size_review`; remedy selector with counter ≥ 2 does not pick `spike`; nested `spike_inconclusive` is not ledgered `refine_failed`
- Budget tests: repeated refutation (refute → decide → re-arm → refute) stops with `decision_unresolved`; nested refine-to-ready does not reset autodev's counter; a crashed spike still increments the counter; at most two spikes per issue per top-level run
- `rearm-spike` subcommand unit tests — removes both keys only when `spike_refuted: true`; no-op otherwise
- resolve-decision oracle routing test — `rearm_refuted_spike` reached on the cleared edge; not on a residual-group `done`
- `scripts/tests/test_deferred_triage*.py` — `spike_inconclusive` rank
- deferral-code coverage for `spike_inconclusive` wherever `DEFERRAL_CODES.md` rows are pinned
- `scripts/tests/test_set_status_cli.py::test_set_status_deferred_stamps_autodev_reason_codes` (~341) — add `spike_inconclusive` to the parametrized reason codes

## Implementation Steps

1. `DeferReason.SPIKE_INCONCLUSIVE`, triage rank, the `rearm-spike` subcommand
2. Shared `spike-runs-<ID>` counter (increment on yes branch, `< 2` gate); remove `refine-to-ready-spike-ran`
3. `rearm_refuted_spike` in `oracles/resolve-decision.yaml`
4. `route_spike_verdict`, `check_spike_budget`, `record_spike_inconclusive`, `mark_spike_no_verdict_infra` in refine-to-ready; `max_steps` bump
5. Same in autodev, plus `check_rearmed_spike_after_decide`, budget checks at every entry, shared ledger init, `skip_inflight` ledger check, `finalize_done` buckets, remedy selector
6. decide-issue Phase 7 line
7. Routing, budget, nesting and re-arm tests; docs; `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply`

## Acceptance Criteria

- [ ] A refuted spike routes to a decision before any rescoring in both autodev and refine-to-ready, whatever its readiness score and even when a decision was already resolved earlier in the run; in autodev it reaches `resolve_decision` rather than a `decision_unresolved` deferral, while budget remains
- [ ] An inconclusive spike keeps the cap, is not re-spiked automatically, and stops at `record_spike_inconclusive` in both loops (deferral code `spike_inconclusive`, not decomposition), with a message naming `/ll:spike <ID> --force`
- [ ] A spike that wrote no verdict routes to an infra terminal in both loops (no deferral, no decision)
- [ ] Under autodev, a nested refine-to-ready `spike_inconclusive` stop is not ledgered as `refine_failed` or counted twice
- [ ] Resolving a decision on a refuted issue re-arms exactly one new spike on the chosen approach (deterministically, via the `rearm-spike` subcommand in the resolve-decision oracle); a residual-group `done` does not re-arm
- [ ] The re-armed spike runs in the same top-level run, before any size review or decomposition, in autodev (nested or not) and in standalone refine-to-ready
- [ ] One per-issue spike counter, shared by every `run_spike` entry in both loops, incremented before each spike and never reset per issue, bounds re-runs to two spikes per issue per top-level run; a repeated refutation within one run stops with `decision_unresolved`
- [ ] autodev's proven path still passes BUG-3588's score-presence gate (`check_scores_present_spike`)

## Impact

- **Priority**: P2 - without routing, refuted/inconclusive spikes decompose or defer silently instead of reaching a decision or a named stop
- **Effort**: Medium - new states in two loops and the resolve-decision oracle, a shared budget, one small CLI verb
- **Risk**: Medium - routing changes in autodev, refine-to-ready and resolve-decision; oscillation after re-arm rests on the shared budget plus the FEAT-2751 backstop
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-25 | Priority: P2
