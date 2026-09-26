---
id: ENH-3605
type: ENH
title: Add prepare-issue wrapper loop with wire/refine and reconcile/design remedy
priority: P3
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-26'
decision_needed: false
blocked_by:
- ENH-3599
- ENH-3602
blocks:
- ENH-3606
- ENH-3600
relates_to:
- ENH-3590
- ENH-3577
parent: ENH-3601
---

# ENH-3605: Add prepare-issue wrapper loop with wire/refine and reconcile/design remedy

## Summary

First half of ENH-3601 (Option B, selected). Create the `prepare-issue` wrapper loop around
`refine-to-ready-issue` and move autodev's wire/refine and reconcile/design remedy states into
it, collapsing their rescoring triplets into one shared rescoring path. Autodev calls
`prepare-issue` and routes only on its `RunRecord.outcome`. Size-review/atomic, go/no-go and
pre-deferral remedy stay in autodev until ENH-3606.

## Parent Issue

Decomposed from ENH-3601: Move autodev second-pass preparation routing into a preparation controller.
See the parent for the full Option B decision rationale, Program Design, Codebase Research
Findings and wiring/test/doc inventories; the items below are the D1 share.

## Current Behavior

`autodev.yaml` owns the wire/refine and reconcile/design remedy states inline
(`check_missing_artifacts`, `run_wire`, `run_refine`, `check_reconcile_needed`,
`reconcile_current`, `dispatch_design_remedy`, …), each with its own
`clear_scores_before_*` / `rerun_confidence_after_*` / `check_scores_present_*` rescoring
triplet. Autodev routes on many per-state sentinels rather than one preparation outcome.

## Expected Behavior

`prepare-issue` (wrapping `refine-to-ready-issue`) owns those states and one shared rescoring
path. Autodev's `refine_current` is a single `loop: prepare-issue` state that routes only on the
`RunRecord.outcome` the wrapper writes; ledger buckets in `finalize_done` are unchanged.

## Scope Boundaries

- **In scope**: wire/refine and reconcile/design-remedy states, their shared rescoring path,
  the `prepare-issue` run-record terminals, and the docs/tests listed below.
- **Out of scope**: size-review/atomic, go/no-go and pre-deferral remedy (ENH-3606); removing
  the legacy sentinels (ENH-3600); widening the go/no-go trigger; changes to other callers of
  `refine-to-ready-issue`.

## Scope

- New `scripts/little_loops/loops/prepare-issue.yaml`: `loop: refine-to-ready-issue` with
  `context_passthrough: true` (shares autodev's `run_dir`, `spike-runs-<ID>` and
  `autodev-repair-cycle-count.txt`).
- Move from `autodev.yaml`:
  - **wire/refine**: `check_missing_artifacts`, `run_wire`, `run_refine`, `count_repair_cycle_wire`
  - **reconcile/design**: `check_reconcile_needed`, `reconcile_current`, `refine_for_design`,
    `check_atomic_design_remedy`, `dispatch_design_remedy`
  - shared rescoring path replacing the `*_wire` and `*_reconcile` triplets (`clear_scores_before_*`,
    `rerun_confidence_after_*`, `check_scores_present_*`), keeping BUG-3588 freshness rules;
    the shared path must be extensible so ENH-3606 can fold in the `*_atomic` triplet
- Autodev's `refine_current` becomes `loop: prepare-issue`: keep the BUG-2611 shape (no `on_no`;
  `on_failure` → `skip_inflight`, `on_error` → `skip_inflight_infra`); no
  `with_rate_limit_handling` on the `loop:` state (BUG-3390). Until ENH-3600 removes them, the
  wrapper keeps writing the sentinels autodev reads (`refine-terminal-class`,
  `refine-broke-down`, ledgers) so `finalize_done` buckets do not change.
- Every wrapper terminal writes `ll-issues run-record write ... --writer prepare-issue`,
  including rate-limit exhaustion (`outcome: retryable_error`, routed to a wrapper-local
  terminal, never `finalize_rate_limited`). Outcomes stay within the ENH-3597 six-value
  `PreparationOutcome` vocabulary.
- `ready` → autodev's fail-closed proof gate (BUG-3603) → `implement_current`; no
  `prepare-issue` terminal routes into `implement_current`.
- Use `select_next_obligation` (FEAT-3598) only for the wire/refine/design-facing subset; it has
  no obligation for size-review, go/no-go, reconcile or pre-deferral remedy.
- Decide `ll-loop next-loop` input resolution for `prepare-issue` (`cli/loop/next_loop.py`
  `_PARAM_RESOLVERS`).

## Tests (in this child)

- Structural: register `prepare-issue` in `test_builtin_loops.py` stem set (~:304-305) and
  `test_fsm_fragments.py` `migration_targets`; rewrite the affected `test_fsm_topology.py` /
  `test_autodev_loop.py` pins; move the wire/refine/reconcile/design suites
  (`TestCheckReconcileNeeded*`, `test_run_wire_*`, `test_check_reconcile_needed_*`,
  `TestReconcilePlateau*`, `TestDesignGateRefineRemedy`, `TestAtomicDesignRemedyRouting` as applicable).
- Update `scripts/tests/data/loop_interpolation_baseline.json` (stale autodev entries out,
  `prepare-issue` sites in, same commit).
- New: `prepare-issue` rate-limit exhaustion writes `retryable_error` and autodev ledgers it.
- New: a `ready` outcome never hits `LEARNING_GATE_BLOCKED` for a reason `assess_proof` (ENH-3602) reports.
- BUG-3603 invariant (no fail-open edge into `implement_current`) still passes.
- Behavioral tests (`test_autodev_scores_freshness.py` behavior, `test_check_readiness.py`,
  `test_arm_proposal_revision.py`, `test_format_probe_routing.py`, `test_ll_issues_check_gate.py`) pass;
  topology pins in `test_autodev_scores_freshness.py:95-96` move with the states.

## Docs (in this child)

- `scripts/little_loops/loops/README.md`, root `README.md` loop count, mirror to `scripts/README.md`.
- `docs/ARCHITECTURE.md` loop section (new wrapper); `docs/guides/LOOPS_REFERENCE.md` new
  `### prepare-issue` section and the wire/reconcile/score-freshness paragraphs moved out of autodev.
- `commands/reconcile-issue.md` (`check_reconcile_needed` / `reconcile_current` handshake),
  `docs/reference/COMMANDS.md` (reconcile handshake, `run_wire` repair path), and moved-state
  citations for these states in `docs/reference/CLI.md` / `API.md`.
- Run `ll-loop validate` on the new YAML (MR-3/7/9/11/14, capture reachability, `scope:`).

## Acceptance Criteria

- [ ] `prepare-issue.yaml` exists, wraps `refine-to-ready-issue`, and passes `ll-loop validate`
- [ ] `autodev.yaml` has no wire/refine/reconcile/design-remedy states; wire and reconcile rescoring triplets are gone from autodev
- [ ] `prepare-issue` has one shared rescoring path with BUG-3588 freshness rules
- [ ] `prepare-issue` writes a `writer: prepare-issue` run record on every terminal, including rate-limit exhaustion (`retryable_error`)
- [ ] A `ready` outcome never hits `LEARNING_GATE_BLOCKED` for a reason `assess_proof` could have detected
- [ ] Autodev ledger buckets in `finalize_done` are unchanged; other callers of `refine-to-ready-issue` untouched

## Impact

- **Priority**: P3 - structural cleanup that unblocks ENH-3606 and ENH-3600; no user-facing defect
- **Effort**: Large - moves ~9 states plus rescoring consolidation, with test and doc migration
- **Risk**: Medium - autodev is live in every local-editable project; mitigated by keeping legacy sentinels and the BUG-3603 proof-gate invariant test
- **Breaking Change**: No

## Program Design

### Types

- `PreparationOutcome`: six-value Literal in `little_loops.run_record` (reused, not extended)
- `prepare-issue.yaml`: FSM loop, `loop: refine-to-ready-issue`, `context_passthrough: true`

### Signatures

- `select_next_obligation(config: BRConfig, issue_id: str, *, skip: Iterable[Obligation] = (), ...) -> ObligationResult | None` — reused for the wire/refine/design subset
- `write_run_record(run_dir: Path, record: RunRecord) -> Path` — reached via `ll-issues run-record write ... --writer prepare-issue` at every wrapper terminal

### Call Path

`autodev.yaml:refine_current` -> `prepare-issue.yaml` -> `refine-to-ready-issue.yaml`; wrapper terminal -> `ll-issues run-record write` -> autodev `finalize_done`

## Status

**Open** | Created: 2026-09-26 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-09-26T03:07:12 - `34887897-5e19-4ee2-b656-5f0a00c15f02.jsonl`
