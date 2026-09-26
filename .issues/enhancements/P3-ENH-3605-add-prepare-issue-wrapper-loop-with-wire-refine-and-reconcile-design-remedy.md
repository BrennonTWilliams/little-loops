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
- ENH-3608
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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Files to modify**: `scripts/little_loops/loops/autodev.yaml` (states listed in Scope; `refine_current` ~:511, `run_wire` ~:1033, `check_missing_artifacts` ~:1871, `check_reconcile_needed` ~:2051, `check_atomic_design_remedy` ~:2411, `refine_for_design` ~:2523, `reconcile_current` ~:2565, `dispatch_design_remedy` ~:2951); new `scripts/little_loops/loops/prepare-issue.yaml` (does not exist yet); `scripts/little_loops/cli/loop/next_loop.py` (`_PARAM_RESOLVERS` has one key, `autodev`; a loop with no resolver gets `{}` — no input on the suggested command).
- **Already in place (do not re-create)**: `run_record.py` already registers `prepare-issue` in `RunRecordWriter` / `WRITERS`, and `test_run_record.py` already exercises that writer. No caller anywhere outside tests invokes `read_run_record`; autodev reads sentinels and ledgers only.
- **Rescoring triplets — five exist, not two**: `decide`, `wire`, `spike`, `atomic`, `reconcile` (`clear_scores_before_X` → `rerun_confidence_after_Y` → `check_scores_present_X`; the atomic rerun state is named `rerun_confidence_after_atomic_remediation`). They differ only in entry point, successor, and retry-marker name (`autodev-rescore-retry-X-<ID>`, cleared by `dequeue_next`). `refine_for_design` and `count_repair_cycle_reconcile` both feed `clear_scores_before_reconcile`, so the design remedy shares the reconcile triplet. The `decide` and `spike` triplets belong to states this issue does not list (ENH-3599 owns `check_spike_needed`, `run_spike`, `route_spike_verdict`, `resolve_decision*`, `decide_current`); the `atomic` triplet is ENH-3606's.
- **Cross-boundary edges (scope constraint)**: the moved states currently route into states that stay in autodev until ENH-3606: `check_scores_present_wire` → `enqueue_or_skip`; `check_reconcile_needed` (on_no) → `check_size_review_ran_this_pass`; `check_scores_present_reconcile` → `recheck_after_size_review`; `check_atomic_design_remedy` (on_no) → `check_go_no_go_eligible`; `dispatch_design_remedy` (on_no/on_error) → `dispatch_pre_deferral_remedy`. A `loop:` child cannot route into its parent's states, so after this issue lands alone every one of these edges needs a defined destination inside `prepare-issue` (or a documented terminal). The split as scoped leaves `refine_for_design`/`check_atomic_design_remedy` on the ENH-3605 side while their partner `regate_after_atomic_remediation` is ENH-3606's; the implementer must decide where that seam sits before either issue is landable independently.
- **Routing constraint on `loop:` states**: the executor (`fsm/executor.py`, `_execute_sub_loop`) maps only the child's terminal type and `terminated_by` to `on_yes`/`on_no`(→`on_failure`)/`on_error`/timeout routes; it never reads a run record. "Autodev routes only on `RunRecord.outcome`" therefore needs an autodev-side probe state that reads the record after the `loop:` state returns (cf. how `skip_inflight` reads `refine-terminal-class`). ENH-3599 (open, blocks this issue) plans `route_refine_outcome` / `select_obligation` in autodev and changes `refine_current`'s successors — the two issues must agree on who owns that state.
- **Rate-limit constraint**: `with_rate_limit_handling` and `on_rate_limit_exhausted` are inert on `loop:` states (BUG-3390; pinned by `test_no_loop_call_state_declares_on_rate_limit_exhausted`, ~`test_builtin_loops.py:3335`, currently scoped to `refine-to-ready-issue.yaml`). The repo has two working shapes for exhaustion: a marker-file + probe state (`decide-rate-limited-<ID>` → `check_decide_rate_limited`, in autodev and mirrored in `refine-to-ready-issue.yaml`), and the `subloop_rate_limit_diagnostic` fragment in `lib/common.yaml` (used by `rn-decompose`). `outcome_from_legacy_class` yields `retryable_error` only for `--legacy-class infra`, so a rate-limit terminal record must pass that class.
- **Sentinels autodev reads (must keep being written until ENH-3600)**: `refine-terminal-class` (read by `skip_inflight`), `refine-broke-down` (→ `autodev-broke-down` via `copy_broke_down`; `check_broke_down` also needs `autodev-new-children.txt`), and the ledgers `finalize_done` reads: `autodev-skipped`, `-gate-blocked`, `-decision-unresolved`, `-not-started`, `-spike-inconclusive`, `-proposal-unsound`, `-spike-no-verdict`, `-proof-gate-infra`, `-unverified`, `autodev-stop-reason`. `autodev-scores-absent.txt` and `autodev-gate-infra.txt` are written but never read by `finalize_done`. Shared per-issue state that must survive the move because states on both sides read it: `autodev-repair-cycle-count.txt`, `autodev-pre-readiness.txt`, `autodev-pre-spike-readiness.txt`, `spike-runs-<ID>`, `autodev-design-gate-failed-<ID>`, `autodev-design-remedy-attempted-<ID>`, `autodev-contradiction-reconcile-*`.
- **`ready` path / BUG-3603**: `ready` reaches implementation only via `check_passed` → `check_proof_gate_before_implement` → `check_proof_defer_or_implement` (the sole edge into `implement_current`). `check-gate` and `assess_proof` are different code paths: `check_gate` consults `assess_proof` only inside `_spike_status`. `LEARNING_GATE_BLOCKED` is emitted by `issue_manager.py` (~:1216) after `implement_current`, so the AC that a `ready` outcome never hits it for an `assess_proof`-detectable reason is verified against `assess_proof` verdicts, not against `check-gate`. The invariant tests are per-state pins (`test_builtin_loops.py` ~:8119 `test_mark_proof_gate_infra_*`, ~:8423, ~:9277; `test_ll_issues_check_gate.py` ~:313), not a graph-wide "no fail-open edge" test.
- **`select_next_obligation`** (`cli/issues/next_obligation.py`) has no loop-YAML callers today; tiers are FORMAT/VERIFY/HEDGES/PLACEHOLDERS/ACCEPTANCE_CRITERIA/DESIGN, then scores, then (only when readiness passes and outcome is low) DECISION/PROOF/ARTIFACTS. It is stateless — budget state arrives via `--skip`.
- **What `refine-to-ready-issue.yaml` already owns**: wire (`check_wire_done`/`wire_issue`), reconcile (`check_reconcile_limit`, one attempt per run, plus `reconcile_revision`), decision, spike, design gate (`check_design`), and `breakdown_issue`. It has no score-freshness triplet and no design remedy / pre-deferral / atomic / go-no-go. It shares `run_dir` under `context_passthrough` (child context = parent context ∪ captured ∪ child context); other caller: `recursive-refine.yaml` (`run_refine`, ~:237).

### Conventions in Force

- New top-level loop YAMLs are registered in an exact-set assertion (`test_builtin_loops.py::test_expected_loops_exist`, ~:204-305); `test_fsm_fragments.py::TestBuiltinLoopMigration` `migration_targets` is conventional but non-exhaustive.
- `TestInterpSweepBaseline::test_completeness_guard` (~`test_builtin_loops.py:21014`) fails in both directions (unbaselined site / stale entry) against `scripts/tests/data/loop_interpolation_baseline.json` — the autodev entries (~:95-122) and `enqueue_or_skip` / `recheck_scores` entries move files with their states.
- `test_fsm_topology.py::TestAutodevSmoke::test_autodev_topology` (~:233-261) pins autodev's total state count (106 at time of research) and records each change as a commented delta with the issue ID; every state move changes it.
- Moved-state absence is asserted with a `REMOVED_INLINE_STATES` parametrized test (`TestIssueRefinementSubLoop`, ~`test_builtin_loops.py:1323`); extraction tests live in a per-loop file (`test_rn_decompose.py`). No test gates comment citations of moved state names — those are updated by hand (e.g. `refine-to-ready-issue.yaml` header comments cite autodev states).
- Terminal convention in `refine-to-ready-issue.yaml`: each terminal writes the legacy sentinel and then `ll-issues run-record write <ID> --run-dir ${context.run_dir} --writer <loop> [--legacy-class X] || true` in a shell state.
- Two child-loop parameter shapes coexist: passthrough (`autodev` → `refine-to-ready-issue`, input arrives as `context.input`) and `with:` parameters (`rn-implement` → `rn-decompose`). The issue specifies passthrough.
- README loop count lives at `README.md:185` (`~108 FSM loops`); `doc_counts.py` counts top-level `loops/*.yaml`. Mirrors: `command cp -f README.md scripts/README.md`; `ll-adapt --host <gemini|kimi-code|qwen> --apply` after skills edits.
- `ll-loop validate` rules relevant here: MR-3, MR-7, MR-9, MR-11 (`# ll-lint: mr11-ok(...)` per-site opt-out), MR-14, static `loop:` refs use the full relative path, `scope:` declared (see `rn-decompose.yaml`).

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
- `/ll:refine-issue` - 2026-09-26T03:22:24 - `7612ef86-47f8-4d5d-aa01-e50211538dc3.jsonl`
- `/ll:format-issue` - 2026-09-26T03:07:12 - `34887897-5e19-4ee2-b656-5f0a00c15f02.jsonl`
