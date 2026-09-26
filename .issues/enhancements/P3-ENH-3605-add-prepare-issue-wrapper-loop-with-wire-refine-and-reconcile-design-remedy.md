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
- ENH-3611
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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `loop: autodev` (~:381); reads autodev's shared-`run_dir` ledgers (`autodev-queue.txt` ~:477/:1077, `autodev-inflight` ~:1058, `-passed`/`-skipped`/`-gate-blocked`/`-decision-unresolved` ~:1088-1144). Ledger writers must keep writing these until ENH-3600. `scan-and-implement.yaml:79` also calls `loop: autodev` [Agent 1]
- `scripts/little_loops/loops/recursive-refine.yaml` — second `refine-to-ready-issue` caller (`run_refine` ~:237); shares the `refine-broke-down` file (~:217, :484) and has its **own** `check_missing_artifacts` (~:594-602). Name collision only, not moved [Agent 1/2]
- `scripts/little_loops/cli/issues/run_record.py` — `add_run_record_parser` (`choices=WRITERS`/`LEGACY_CLASSES`, both already accept `prepare-issue`); `_read_broke_down` reads the shared `<run_dir>/refine-broke-down`, so a wrapper `decomposed` terminal must write it [Agent 1/2]
- `scripts/little_loops/fsm/validation/reachability.py` — `_validate_loop_references`: `autodev.refine_current` → `prepare-issue` is a load ERROR until `prepare-issue.yaml` exists (land YAML and autodev edit in one commit) [Agent 2]
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop`: with a 3-level passthrough chain, autodev's `captured.refine_current` nests one level deeper; no YAML/Python reads `captured.refine_current` today, so no break [Agent 2]
- Inbound edges from states that **stay** in autodev into moved states (each needs a new destination): `check_spike_needed` on_no/on_error → `check_missing_artifacts` (~:1704); `check_spike_needed_before_skip` on_no → `check_reconcile_needed` (~:2048); `regate_after_atomic_remediation` on_no → `check_atomic_design_remedy` (~:2407); `check_pre_deferral_remedy` on_yes → `dispatch_design_remedy` (~:2947); `dispatch_pre_deferral_remedy` on_no/on_error → `reconcile_current` (~:3006) [Agent 2]
- Rate-limit behavior change: moved slash states use `with_rate_limit_handling` with `on_rate_limit_exhausted: finalize_rate_limited` (autodev-only; halts the queue). A wrapper-local `retryable_error` terminal infra-skips one issue instead; decide and document. The wrapper also lacks `${captured.issue_id.output}` / `${context.issue_id}` that `mark_rate_limit_infra` and `subloop_rate_limit_diagnostic` (`lib/common.yaml`) read [Agent 2]
- Stale-record isolation: `read_run_record` has no run-instance field; `prepare-issue` needs a `resolve_issue`-style delete of its own `run-records/prepare-issue/<ID>.json` on entry (as `refine-to-ready-issue` does, `test_run_record.py:524`) [Agent 2]

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/loops/prepare-issue.yaml` — re-declare per-state `pruning_profile:` blocks for moved slash states (`run_wire` `wire-issue-auto`, `run_refine`/`refine_for_design` `refine-issue-repair`, `rerun_confidence_after_wire`/`_reconcile` `confidence-check-recheck`, `reconcile_current` `reconcile-issue-auto`) or MR-12 warns; declare `scope:` (BUG-3107) and no `timeout:` on the `loop:` state (`TestSubLoopStateTimeoutAudit`) [Agent 2/3]
- `docs/guides/LOOPS_REFERENCE.md` — autodev ASCII tree (~:1038-1069, :1184-1186), notes paragraph ~:1083, wire/reconcile paragraph ~:1087, ~:1081 dispatch description; keep heading "Typed run record (ENH-3597)" (pinned by `test_wiring_reference_docs.py:260`) [Agent 2]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/DEFERRAL_CODES.md` — `:26` (`readiness_stagnated` repair-class list), `:27` (`design_gate_failed` cites `refine_for_design`/`reconcile_current`), `:30` (`autodev-scores-absent`/`-gate-infra` ledgers) [Agent 2]
- `docs/reference/CLI.md` — `:2272` (`missing_artifacts` read by `check_missing_artifacts` "in both" loops), `:2335`, `:2687` (`check_reconcile_needed`), `:1359` (`next-loop` autodev-only resolver), `:2404-2432` (run-record section already names `prepare-issue` writer) [Agent 2]
- `docs/reference/API.md` — `:983` (`check_reconcile_needed` payload), `:4681` (`refine_for_design`) [Agent 2]
- `docs/reference/COMMANDS.md` — `:307`, `:311` (reconcile one-shot/plateau), `:366` (`run_wire`) [Agent 2]
- `docs/reference/ISSUE_TEMPLATE.md` — `:916` (`missing_artifacts` routes autodev to wire-issue), `:919` (`spike_attempted`) [Agent 2]
- `docs/reference/CONFIGURATION.md:456` — list of loops that must not pin confidence thresholds; add `prepare-issue` (matches `TestConfidenceGateThresholdsNotHardcoded.LOOPS`, `test_builtin_loops.py` ~:21326) [Agent 2]
- `commands/reconcile-issue.md` — `:83`, `:145`, `:197`, `:368` describe `check_reconcile_needed` routing/one-shot guard and "Called by `reconcile_current`"; `commands/refine-issue.md:1073` cites the `autodev.yaml` remedy [Agent 2]
- `skills/audit-loop-run/SKILL.md:119` — `ll-loop show <loop> --resolved` expands one sub-loop level (`cli/loop/info.py` `cmd_show`), so autodev will show `prepare-issue`'s states, not `refine-to-ready-issue`'s [Agent 2]
- `docs/guides/LOOPS_GUIDE.md` (`:88`, `:395`), `docs/ARCHITECTURE.md` (`:463`, `:676`), `docs/guides/RECURSIVE_LOOPS_GUIDE.md:271-302` — loop tables/pickers; add wrapper row [Agent 2]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` header comments citing autodev states (comment-only; no gate) [Agent 1]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_builtin_loops.py::TestAutodevLoop` — `test_required_states_exist` (~:6659; also lists ENH-3606 states), `test_refine_current_delegates_to_refine_to_ready_issue` (~:6798, asserts `loop == refine-to-ready-issue`; hard break), `test_context_passthrough_on_refine_current` (~:8588), moved-state edge pins: `check_missing_artifacts` (~:9183-9209), `run_wire`/`run_refine` (~:9214-9238, :9519-9531), `rerun_confidence_after_wire` (~:9534-9590), `check_reconcile_needed` (~:8328, :8636-8660, :8839-8872, :9121-9165), `reconcile_current`/`count_repair_cycle_reconcile` (~:9145-9166), `dispatch_design_remedy` (~:8771-8793), `check_atomic_design_remedy` (~:8229). Cross-boundary assertions on staying states change too (`check_spike_needed_before_skip` ~:9081) [Agent 3]
- `scripts/tests/test_autodev_decision_gate.py` (~64 hits, not in issue) — `TestSpikeTriageStructural` (~:446-447), `TestReconcilePlateauStructural`/`Routing` (~:532-695), `TestDesignGateRefineRemedy` (~:698-770), `TestAtomicDesignRemedyRouting` (~:772-818), `TestGuard2VerdictBypass` (~:820); file loads only `autodev.yaml` via `_load_autodev_yaml`, so moved suites need a `prepare-issue.yaml` loader [Agent 3]
- `scripts/tests/test_autodev_loop.py::TestRepairCycleCounterStates` (~:450-486; `count_repair_cycle_wire`/`_reconcile`/`_refine_for_design`, `test_refine_current_routes_through_counter_before_copy_broke_down`) and `check_reconcile_needed` tests (~:190-300, :923-961) [Agent 2/3]
- `scripts/tests/test_spike_verdict_routing.py` — `test_autodev_routing_table` (~:89-106), `test_dispatch_pre_deferral_remedy_*` (~:147, comment `-> reconcile_current`); loop over `("autodev.yaml", "refine-to-ready-issue.yaml")` (~:136); verify no moved key is indexed [Agent 3]
- `scripts/tests/test_cli_loop_next.py` (~:224-225, :336-344) — add a `prepare-issue` case beside `test_unknown_loop_returns_empty_dict` if a resolver is added [Agent 2/3]
- Global gates that will run on the new file automatically: `TestBuiltinLoopFiles` (~:66, `test_all_have_scope_field` ~:183, `test_all_failure_terminals_have_diagnostic_action` ~:416, `test_no_failure_edge_routes_to_a_success_terminal` ~:87), `TestBuiltinLoopReferencesResolve`, `TestMr11MarkerSet`, `TestSubLoopStateTimeoutAudit` (~:21377), `TestHostRunnerEnvSweep` (`test_host_runner.py:2720`); `test_concurrency.py` scope-lock tests keyed on loop names (~:738-860) [Agent 3/1]
- `scripts/tests/data/loop_interpolation_baseline.json` — correction: autodev entries for the moved cluster are `check_reconcile_needed` plus `check_blockers_at_dequeue`, `check_spike_needed`, `check_spike_needed_before_skip` (latter three stay); `enqueue_or_skip`/`recheck_scores` entries are keyed to `recursive-refine.yaml`, not autodev [Agent 3, from ENH-3606 pass]
- **New**: `scripts/tests/test_prepare_issue.py` modeled on `test_rn_decompose.py` (`_load_loop`, `TestDecompositionChain`, `TestTerminalStates`, `TestFSMHealth`) plus the `test_run_record.py` two-layer run-record pattern (`TestLoopCallSites`-style structural pins incl. `--writer prepare-issue` window check; `TestTerminalExecution`-style `_run_state` execution asserting `retryable_error` for rate-limit exhaustion) [Agent 3]
- **New**: a `prepare-issue` twin of `test_no_loop_call_state_declares_on_rate_limit_exhausted` (existing at `test_builtin_loops.py` ~:3335 for refine-to-ready-issue and ~:7945 for autodev) [Agent 3]
- **New**: graph-wide "no `prepare-issue` terminal routes into `implement_current`" test — none exists; BUG-3603 pins are per-state only (~:8119, :8423, :9277) [Agent 3]
- Unaffected despite name hits: `test_run_record.py` `DONE_PATH_GATES`/`TestLoopCallSites` (target `refine-to-ready-issue.yaml`'s own states), `TestRecursiveRefineLoop`, `test_ll_issues_next_obligation.py:377`, `test_rn_remediate.py` [Agent 3]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/loop/next_loop.py` — `_scan_history` reads `.loops/.history/<run_id>-<loop>`; a wrapper run only as a sub-loop never produces one, so the "no resolver" decision matters only for direct `ll-loop run prepare-issue` [Agent 2]
- No change needed: `pyproject.toml` (`include = ["little_loops/**"]` glob), `.claude-plugin/*.json`, `hooks/`, `config-schema.json` (only `max_refine_count` prose at :542), `fsm/` (no loop-name-keyed logic). README count `README.md:185` is a manual bump [Agent 1/2]

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Land `prepare-issue.yaml` and the `refine_current` → `loop: prepare-issue` edit in one commit (static `loop:` ref is a load error otherwise)
- Give each inbound cross-boundary edge from a staying autodev state (`check_spike_needed`, `check_spike_needed_before_skip`, `regate_after_atomic_remediation`, `check_pre_deferral_remedy`, `dispatch_pre_deferral_remedy`) a defined destination
- Add an autodev-side probe state after `refine_current` that reads the `prepare-issue` run record (the executor never reads records); reconcile ownership with ENH-3599's `route_refine_outcome`
- Delete stale `run-records/prepare-issue/<ID>.json` on wrapper entry; write `refine-broke-down` before any `decomposed` terminal
- Re-declare `pruning_profile:` blocks and `scope:` in the new YAML; no `timeout:` on the `loop:` state
- Update `test_builtin_loops.py`, `test_autodev_decision_gate.py`, `test_autodev_loop.py`, `test_spike_verdict_routing.py` per the Tests list; add `test_prepare_issue.py`, the rate-limit pin twin and the no-edge-into-`implement_current` test
- Update `loop_interpolation_baseline.json` (moved `check_reconcile_needed` site → `prepare-issue.yaml`), `test_fsm_topology.py` count, README count and mirror (`command cp -f README.md scripts/README.md`)
- Update the docs/commands/skill lines in the Documentation list; `ll-adapt --host <gemini|kimi-code|qwen> --apply` if skills change

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
- `/ll:wire-issue` - 2026-09-26T03:36:28 - `e6ad8ea2-14d6-441f-a607-435314c2d056.jsonl`
- `/ll:refine-issue` - 2026-09-26T03:22:24 - `7612ef86-47f8-4d5d-aa01-e50211538dc3.jsonl`
- `/ll:format-issue` - 2026-09-26T03:07:12 - `34887897-5e19-4ee2-b656-5f0a00c15f02.jsonl`
