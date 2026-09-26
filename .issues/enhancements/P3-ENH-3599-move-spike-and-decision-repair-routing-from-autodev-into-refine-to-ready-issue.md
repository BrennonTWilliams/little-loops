---
id: ENH-3599
type: ENH
title: Move spike and decision repair routing from autodev into refine-to-ready-issue
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:50Z'
blocked_by:
- ENH-3597
- FEAT-3598
- BUG-3603
blocks:
- ENH-3601
- ENH-3600
parent: EPIC-3565
reconcile_attempted: true
relates_to:
- ENH-3577
confidence_score: 70
outcome_confidence: 53
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3599: Move spike and decision repair routing from autodev into refine-to-ready-issue

## Summary

Delete autodev's copies of the spike and decision repair routes and let the child own them,
driven by the run record (A) and the selector (B). Step C of the ENH-3577 decomposition —
the first routing migration, chosen because these states are literal duplicates.

## Current Behavior

These states exist in both `autodev.yaml` and `refine-to-ready-issue.yaml`:
`check_spike_needed`, `run_spike`, `route_spike_verdict`, `check_spike_budget`,
`record_spike_inconclusive`, `mark_spike_no_verdict_infra`, `check_decide_rate_limited`,
`record_decision_unresolved`. Autodev additionally has decision entry points
(`check_decision_at_dequeue`, `resolve_decision_at_dequeue`, `mark_decide_ran_at_dequeue`,
`check_decision_after_refine`, `decide_current`, `resolve_decision`,
`resolve_decision_direct`, `mark_decide_ran`, `check_rearmed_spike_after_decide`,
`check_decision_before_size_review`, `check_spike_needed_before_skip`,
`check_proof_gate_before_implement`), the rescoring triplets for `decide` and `spike`, and
the markers `autodev-decide-ran`, `autodev-spike-inconclusive.txt`,
`autodev-spike-no-verdict.txt`, `autodev-decision-unresolved.txt`,
`autodev-pre-spike-readiness.txt`, `spike-runs-*`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- The eight named states are duplicates in name only. Autodev's copies differ from the child's in ways the removal must account for: autodev reads the ID from `captured.input.output`, the child from `captured.issue_id.output`; autodev's `run_spike` (`autodev.yaml:1662`) carries `with_rate_limit_handling`, `rate_limit_max_wait_seconds: 14400`, `on_rate_limit_exhausted: finalize_rate_limited` and a `count_repair_cycle_spike` successor (FEAT-2751 stagnation counter), none of which the child's `run_spike` (`refine-to-ready-issue.yaml:1031`) has.
- Both proof-gate states in autodev fail open today: `check_proof_gate_before_implement` (`autodev.yaml:690`) and `check_proof_defer_or_implement` (`autodev.yaml:730`) both set `on_error: implement_current`, and both map unrecognised `ll-issues check-gate` output to `PROOF_CLEAR`. That is BUG-3603, still open; the "fail-closed" route this issue depends on does not exist yet.
- `spike-runs-<ID>` is written by both loops today: the child increments it in `check_spike_needed` (`refine-to-ready-issue.yaml:1018`), autodev in `check_spike_needed` (`autodev.yaml:1643`), `check_spike_needed_before_skip` (`:1987`), `check_proof_gate_before_implement` (`:703`) and `dispatch_pre_deferral_remedy` (`:2943`). Removing autodev's writers leaves the child as the sole writer, so carry-over across re-entries holds only if `resolve_issue` in the child keeps not touching it (BUG-3593 comment at `:1012`).
- `RunRecord`, `read_run_record` and `write_run_record` do not exist in `scripts/little_loops` yet (ENH-3597 is open); no code in this issue can be verified against them until that lands.

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- The blockers have landed, so the "does not exist yet" claims above are stale. ENH-3597, FEAT-3598 and BUG-3603 are all `status: done`. `scripts/little_loops/run_record.py` defines `RunRecord`, `write_run_record` and `read_run_record`. `scripts/little_loops/cli/issues/next_obligation.py` provides `ll-issues next-obligation`. The fail-closed proof gate is in `autodev.yaml`.
- Proof gate today: `check_proof_gate_before_implement` (`autodev.yaml:691`) sets `on_error: mark_proof_gate_infra` and emits `PROOF_INFRA` on unrecognised output. `check_proof_defer_or_implement` (`:744`) is the only predecessor of `implement_current` (route `PROOF_CLEAR`, `:769`). The earlier finding that both states fail open into `implement_current` no longer holds.
- Autodev reads no run record. `refine_current` (`:511`) still routes `on_success: count_repair_cycle_refine` → `copy_broke_down` → `check_decision_after_refine` (`:657`) → `check_passed` (`:667`, `ll-issues check-readiness ... --honor-waiver`). `on_failure` goes to `skip_inflight` (`:551`), which greps three child-written markers.
- The child writes a run record at every terminal: `record_proposal_unsound`, `record_gate_unmet`, `write_broke_down`, `mark_rate_limit_infra`, `mark_evidence_absent_infra`, `mark_spike_no_verdict_infra`, `record_spike_inconclusive`, `record_decision_unresolved` and `classify_terminal` (`refine-to-ready-issue.yaml:1575`). Every write is `|| true`.
- `outcome_from_legacy_class` maps `decision_unresolved`, `proposal_unsound` and `quality` to `blocked`, and `spike_inconclusive` and `gate_unmet` to `deferred`. `infra` maps to `retryable_error`. That is the mapping the "blocked/deferred for a decision or proof reason" wording in Expected Behavior depends on.

## Expected Behavior

Autodev never invokes `/ll:spike` or `oracles/resolve-decision` directly. When the child
returns `blocked`/`deferred` for a decision or proof reason, autodev ledgers it from the run
record and moves on; when the issue still needs a decision/spike after a second-pass repair,
autodev re-enters the child rather than running its own route.

## Proposed Solution

- Route `refine_current` success by `RunRecord.outcome` instead of `check_passed` for the
  decision/proof dimensions.
- Remove the dequeue-time decision resolution (BUG-3569 already routes it through the
  refine pipeline) and the post-refine decision/spike states listed above.
- Remove the `decide`/`spike` rescoring triplets; the child's `confidence_check` owns
  rescoring (BUG-3588 freshness rules must carry over).
- Stop autodev from reading or writing the listed marker files. Ledger rows
  (`autodev-skipped.txt` etc.) are written from the run record.

### Replacement edge into `implement_current`

`check_proof_gate_before_implement` is one of only two predecessors of
`implement_current`. Deleting it without a replacement would leave an edge into
implementation that skips the proof gate, which breaks EPIC-3565's AC. The route after
this change must be:

`refine_current` → read the `RunRecord` → `outcome == ready` →
`check_proof_defer_or_implement` (fail-closed per BUG-3603) → `implement_current`

The proof gate stays as a cheap deterministic assertion before implementation, even
though the child now owns spike routing. BUG-3603's structural invariant test (no
`on_error` edge into `implement_current`; every predecessor is a proof-gate state) must
keep passing.

### Markers the child writes and other loops read

The child itself writes `autodev-decide-ran`, `autodev-decision-unresolved.txt`,
`autodev-proposal-unsound.txt` and `autodev-spike-inconclusive.txt`
(`refine-to-ready-issue.yaml`). Two other loops depend on them:

- `auto-refine-and-implement.yaml:1112` counts `autodev-decision-unresolved.txt` for its
  own summary.
- `oracles/resolve-decision.yaml:249` relies on the write-once `autodev-decide-ran`.

This issue removes only **autodev's** reads and writes. The child keeps writing these
files until ENH-3600 migrates `auto-refine-and-implement` to run records.

### Spike budget across re-entries

`spike-runs-<ID>` lives in the shared `run_dir`, and both loops count against it
(BUG-3553/BUG-3593). When autodev re-enters the child, the counter must carry over and
must not be reset. Otherwise every re-entry grants a fresh spike budget.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — the child's `run_spike` lacks autodev's `with_rate_limit_handling` / `rate_limit_max_wait_seconds: 14400` / `on_rate_limit_exhausted` behavior, so the child must gain it before autodev's copy is deleted (finding: autodev's `run_spike` invariant)
- `scripts/little_loops/cli/issues/run_record.py` (or a shell JSON read in `autodev.yaml`) — add the run-record read path autodev routes on; only a `write` subcommand exists today, and a missing/mismatched record must route as infra/legacy, never as `ready` (finding: `read_run_record` returns `None`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` (callers change, contract doesn't; relies on the `autodev-decide-ran` marker at line 249)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (reads `autodev-decision-unresolved.txt` at line 1112; unchanged here, migrated in ENH-3600)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/scan-and-implement.yaml:79` — `loop: autodev` sub-loop dispatch outside the known list; consumes autodev's terminal shape, which this issue reshapes [Agent 1 finding]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — beyond the known `:1112` reader, `finalize` also counts `autodev-skipped.txt` (`:1099`), `autodev-gate-blocked.txt` (`:1105`), reads `autodev-inflight` sentinels (`:1048-1058`) and awks `autodev-decision-unresolved.txt` (`:1133-1144`); the run-record ledger replacing autodev's markers must keep these counts meaningful until ENH-3600 [Agent 2 finding]
- `scripts/little_loops/cli/issues/show.py:134` — ENH-2640 comment "spike-remediation flags read by autodev's check_spike_needed" (also `:339`); flags stay, comment goes stale [Agent 1 finding]
- `scripts/little_loops/cli/issues/check_gate.py:4` — module docstring cites `check_gate_at_dequeue` and `recheck_after_size_review` as consumers [Agent 1 finding]
- `scripts/little_loops/issue_lifecycle.py:75` — deferral-reason enum comments attribute `decision_unresolved` and neighbors to autodev states; values are loop-agnostic, comments need re-attribution [Agent 2 finding]
- `scripts/little_loops/loops/spike-gate.yaml:28` — carries its own same-named `check_spike_needed` / `run_spike_auto` states; no edit needed, but any state-name grep sweep must scope to `autodev.yaml` [Agent 1 finding]
- `scripts/little_loops/loops/rn-remediate.yaml:301` — its own `resolve_decision` / `resolve_decision_direct` / `check_decide_rate_limited` survive; the `:307` comment "Mirrors autodev's resolve_decision_direct" goes stale, and `scripts/tests/test_rn_remediate.py:279` docstrings assert that parity [Agent 1 finding]

### Tests
- Behavioral, must pass unchanged: `test_autodev_scores_freshness.py` (BUG-3588 freshness). `test_spike_verdict_routing.py` and `test_autodev_decision_gate.py` pin removed autodev states/markers and the post-decide chain to `implement_current`, so each test gets a per-test call at implementation time: behavioral cases keep passing against the child (BUG-3593 routing), structural/autodev-leg cases are rewritten against the new owner, not deleted (ENH-3075 AC 8)
- Structural, rewrite: `test_fsm_topology.py` (`test_autodev_topology` state count 106, with history comment), `test_builtin_loops.py` (incl. `AUTODEV_NOT_READY_STATES`), `test_autodev_loop.py`, `test_ll_issues_check_gate.py` (`TestAutodevRouting`, and `TestProofGateFailClosed`'s `check_proof_gate_before_implement.on_error` assertion), plus stays-deleted guards for the removed states (pattern: `TestAssertDecisionClearedStructural`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_check_gate.py` (TestAutodevRouting) — `test_unsatisfied_proof_gate_reaches_run_spike()` (~:214) asserts `check_proof_gate_before_implement.on_yes == run_spike` and writes `spike-runs-<ID>`; `test_spent_spike_budget_defers()` (~:228) and `test_implement_edges_route_through_guard()` (~:240) cover the deleted state's edges — currently listed only under ENH-3601 [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py` — beyond topology: the decide chain `test_decide_current_*` / `test_resolve_decision_direct_*` / `test_mark_decide_ran_*` / `test_recheck_after_decide_*` (~:9190-9457), the spike chain `test_check_spike_needed_*` / `test_run_spike_action_and_routing` / `test_rerun_confidence_after_spike_routing` (~:8940-9058), dequeue-decision routing (~:6754, :6783), skip-ledger tests (~:7949-7961), `test_record_decision_unresolved_defers_via_set_status` (~:8087), and `AUTODEV_NOT_READY_STATES` including `record_decision_unresolved` (~:9698) [Agent 3 finding]
- `scripts/tests/test_autodev_decision_gate.py` — `TestSpikeTriageStructural` (~:417) asserts `check_spike_needed`/`run_spike` exist in autodev.yaml; `TestCheckDecisionAtDequeue*` (~:97, :225), `TestCheckDecisionBeforeSizeReview*` (~:334, :903) and `TestDecidePathSpikeGate` (~:474) cover the removed chain; `TestAssertDecisionClearedStructural::test_assert_decision_cleared_absent_from_autodev_states` (~:1004) is the "state must stay deleted" guard pattern to copy for the removal [Agent 3 finding]
- `scripts/tests/test_spike_verdict_routing.py` — `test_autodev_routing_table()` (~:89-108) asserts `autodev-spike-inconclusive.txt` inside `skip_inflight`/`init` actions and `check_rearmed_spike_after_decide → run_spike`; `test_autodev_spike_gate_budget`, `test_dispatch_pre_deferral_remedy_spike_budget` (~:141), `test_rearm_spike_*` (~:181-215) and `test_autodev_ledgers_proposal_unsound_stop_not_as_refine_failed` (~:225) parametrize the removed gates [Agent 3 finding]
- `scripts/tests/data/loop_interpolation_baseline.json` — `check_spike_needed` (:114) and `check_spike_needed_before_skip` (:123) entries go stale; delete in the same commit (`TestInterpSweepBaseline::test_completeness_guard` ratchet) [Agent 1 finding]
- `scripts/tests/test_show.py:372` — `test_spike_flags_surfaced_as_bool_strings()` contract unchanged; docstrings naming autodev's gates go stale [Agent 1 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the autodev section (`### autodev — Targeted Refine-and-Implement`, ~:1013) names the removed states/markers verbatim: score-freshness paragraph (~:1077), diagram omissions (~:1079), outcome-failure triage (~:1085), decidability gate parity (~:1087); `:146` also credits `record_decision_unresolved` as "mirroring autodev's state of the same name" [Agent 2 finding]
- `docs/reference/DEFERRAL_CODES.md:21` — Source column cites `record_decision_unresolved` and `record_spike_inconclusive` in both loops; this issue removes autodev's writers [Agent 1 finding]
- `docs/reference/CLI.md:2318` — `**FSM loop use**` for `check-gate` names `check_gate_at_dequeue`, `recheck_after_size_review` and `check_proof_gate_before_implement`; `:2828` names `recheck_after_decide`/`recheck_scores` as `--honor-waiver` callers [Agent 1 finding]
- `docs/reference/API.md:4663` — documents `record_decision_unresolved` and `recheck_after_size_review` as autodev deferral-code writers [Agent 1 finding]
- `docs/reference/ISSUE_TEMPLATE.md:919` — `spike_attempted` row: "Read by autodev's `check_spike_needed` gate … never re-enters `run_spike`" [Agent 1 finding]
- `docs/guides/DECISIONS_LOG_GUIDE.md:644` — describes autodev's `check_decision_needed` / `resolve_decision` handling [Agent 1 finding]
- `skills/decide-issue/reference.md:290` — cites `record_decision_unresolved` (BUG-3593 routing); host mirrors under `.gemini/`, `.qwen/`, `.kimi-code/` regenerate via `ll-adapt --host <host> --apply` [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Autodev sites that touch the listed spike/decision markers or run a spike/decision route but are NOT among the twenty-odd states named in Current Behavior — each must be resolved for AC 1 and AC 3 to hold:
  - `skip_inflight` (`autodev.yaml:550-600`) greps `autodev-decision-unresolved.txt`, `autodev-spike-inconclusive.txt` and `autodev-proposal-unsound.txt` to avoid double-counting a child-ledgered stop (BUG-3390/BUG-3593/BUG-3574). With run records this must become an outcome check, or child-ledgered stops are counted as `refine_failed` a second time.
  - `dispatch_pre_deferral_remedy` (`autodev.yaml:2943`, reached via `check_pre_deferral_remedy:2880` / `dispatch_design_remedy:2901`) writes `autodev-pre-spike-readiness.txt` and routes into the spike family; `recheck_after_size_review` (`:2833`) reads `spike-runs-<ID>`. These are spike routes outside the eight states and are not addressed by Scope Boundaries (size-review stays until ENH-3601).
  - `finalize_done` summary reads `autodev-decision-unresolved.txt` (`:3030`) and `autodev-spike-inconclusive.txt` (`:3106`); the initial-state block truncates the markers (`:68-71`), `dequeue_next` removes `autodev-pre-spike-readiness.txt` (`:140`), and `autodev-decide-ran` is removed at `:108`.
  - `recheck_after_decide` (`:901`) and `recheck_scores` (`:1552`) are the shared rescoring states the `decide`/`spike` triplets feed; their BUG-3588 freshness checks must be preserved when the triplets go (`test_autodev_scores_freshness.py`).
- The only autodev predecessors of `implement_current` are `check_proof_gate_before_implement` (`on_error`, `:728`) and `check_proof_defer_or_implement` (`on_no` `:743`, `on_error` `:744`); `check_proof_gate_before_implement` is entered from `check_passed` (`:685`), `check_decision_after_refine`-family states (`:929`) and `check_decision_before_size_review`-family retries (`:760-761`).
- `cmd_check_gate` lives at `scripts/little_loops/cli/issues/check_gate.py:145` (verdicts `structured_proof` / `structured_open` / other).
- Existing behavioral tests (`test_autodev_decision_gate.py`, e.g. `post_decide_chain_fsm` fixtures near `:140-170`, `:980-1115`) hard-code `implement_current` reachability through the post-decide chain; the "pass unchanged" AC conflicts with removing that chain, so which of those tests are behavioral (kept) versus structural (rewritten) needs a per-test call at implementation time.
- Conventions in force: the child owns `oracles/resolve-decision` through `check_decision_mid_refine`/`resolve_decision_mid_refine` (`refine-to-ready-issue.yaml:309-322`), `..._mid_wire` (`:363-374`) and `resolve_decision_pre_breakdown` (`:1092`); a decision route belongs in the child as a `loop: oracles/resolve-decision` state, evidence: those three states.

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Current `autodev.yaml` anchors, superseding the line numbers cited earlier in this section: `check_passed:667`, `check_proof_gate_before_implement:691`, `check_proof_defer_or_implement:744`, `decide_current:774`, `resolve_decision:791`, `resolve_decision_direct:812`, `check_decide_rate_limited:829`, `recheck_after_decide:929`, `check_rearmed_spike_after_decide:962`, `record_decision_unresolved:988`, `implement_current:1134`, `recheck_scores:1597`, `check_decision_before_size_review:1633`, `check_spike_needed:1668`, `run_spike:1707`, `route_spike_verdict:1738`, `check_spike_budget:1767`, `record_spike_inconclusive:1781`, `mark_spike_no_verdict_infra:1801`, `check_spike_needed_before_skip:2008`, `recheck_after_size_review:2682`, `check_pre_deferral_remedy:2930`, `dispatch_design_remedy:2951`, `dispatch_pre_deferral_remedy:2975`, `finalize_done:3021`.
- Current marker sites in `autodev.yaml`: ledger truncation `:68-70`; `autodev-decide-ran` removed `:109`, written `:283` and `:863`; `autodev-pre-spike-readiness.txt` removed `:141`, written `:718`, `:1696`, `:2040`, `:3000`; `skip_inflight` greps `:584`, `:591`, `:597`; `autodev-spike-inconclusive.txt` written `:1786`; `finalize_done` reads `:3080`, `:3160`, `:3164`. `spike-runs-<ID>` is touched at `:713`, `:969`, `:1688`, `:1774`, `:2032`, `:2883`, `:2993`.
- Current child anchors in `refine-to-ready-issue.yaml`: `check_decision_mid_refine:311`, `resolve_decision_mid_refine:324`, `check_decision_mid_wire:365`, `resolve_decision_mid_wire:376`, `check_spike_needed:1003` (counter increment `:1033`), `run_spike:1039`, `route_spike_verdict:1057`, `check_spike_budget:1086`, `resolve_decision_pre_breakdown:1100`, `check_decide_rate_limited:1298`, `mark_spike_no_verdict_infra:1337`, `record_spike_inconclusive:1348`, `record_decision_unresolved:1371`, `classify_terminal:1575`.
- Invariant: autodev's `run_spike` (`:1707`) carries `with_rate_limit_handling`, `rate_limit_max_wait_seconds: 14400`, `on_rate_limit_exhausted: finalize_rate_limited` and a `count_repair_cycle_spike` successor (`:1727`). The child's `run_spike` (`:1039`) has none of these. Deleting autodev's copy while the child owns spike routing removes rate-limit-wait behavior for spikes unless the child gains it, so "only if a route is missing in the child" applies to `refine-to-ready-issue.yaml` here.
- Invariant: no loop YAML reads a run record and `ll-issues run-record` has only a `write` subcommand (`cli/issues/run_record.py`, `cmd_run_record_write`). Autodev routing on `RunRecord.outcome` needs a read path that does not exist yet. That path could be a CLI subcommand or a shell JSON read. `read_run_record` returns `None` on a missing file, bad JSON, or a writer/ID mismatch, so a missing record must route as an infra/legacy case, not as `ready`.
- Invariant: the child deletes its record at `resolve_issue` (`refine-to-ready-issue.yaml:184`, `rm -f .../run-records/refine-to-ready-issue/$ID.json`), so each child run starts without a stale record. Autodev must read the record only after the child returns.
- No loop consumes `ll-issues next-obligation` yet. `--format token` prints `OBLIGATION[:sub_reason]` for FSM `route:` tables. The selector is stateless: the caller owns budgets and passes `--skip`, so it does not spend `spike-runs-<ID>`. `PROOF` in the selector uses `assess_proof` (ENH-3602), which differs from the `check_spike_needed` phrase scan.
- Tests that pin the removed states, beyond those already listed: `scripts/tests/test_ll_issues_check_gate.py` `TestAutodevRouting` (`test_unsatisfied_proof_gate_reaches_run_spike` now at ~`:237`); `TestAutodevRnImplementDeferralParity` in `test_builtin_loops.py` (~`:9736-9777`), whose `AUTODEV_NOT_READY_STATES` includes `record_decision_unresolved`, so removal raises `KeyError` on that case; `test_fsm_topology.py` `TestAutodevSmoke::test_autodev_topology` asserts `len(topo["states"]) == 106`.
- Invariant: `TestProofGateFailClosed` (`test_ll_issues_check_gate.py`) asserts `implement_current`'s predecessors are exactly `{"check_proof_defer_or_implement"}` and that no `on_error` or `on_cannot_judge` edge reaches it. It also asserts `check_proof_gate_before_implement.on_error == "mark_proof_gate_infra"`. Removing `check_proof_gate_before_implement` breaks the last of those, so the invariant needs a stated new home for the first-stage proof classification, or that assertion must be rewritten deliberately.
- Convention: state removals in autodev keep a stays-deleted guard, retarget every inbound edge, and update the topology count with a history comment in the same change (evidence: `test_autodev_decision_gate.py` `TestAssertDecisionClearedStructural`, `test_fsm_topology.py` `test_autodev_topology`). Old assertions are rewritten against the new owner, not deleted (ENH-3075 AC 8).
- Convention: `scripts/tests/data/loop_interpolation_baseline.json` is an exact-set ratchet checked in both directions by `TestInterpSweepBaseline::test_completeness_guard`. The entries to delete with the states are `check_spike_needed` and `check_spike_needed_before_skip` (autodev).
- Convention: a child's outcome crosses a `loop:` boundary through files under the shared `${context.run_dir}` because `loop:` states route only on success, failure or error (evidence: `check_decide_rate_limited`, `copy_broke_down`, `skip_inflight`). The run record is the typed successor to that pattern and is written alongside the legacy files, never replacing them (`run_record.py` docstring).
- Contested convention: the child and autodev name the issue ID differently (`captured.issue_id.output` vs `captured.input.output`). `test_spike_verdict_routing.py` `_run()` substitutes both, so tests parametrized over both loops lose their autodev leg when the autodev states go.
- `spike-runs-<ID>`, `decide-options-deposited-<ID>` and `decide-rate-limited-<ID>` live in the shared `run_dir` without an `autodev-` prefix. The AC wording "listed marker files" covers only the names listed in Current Behavior. `test_resolve_issue_does_not_reset_spike_counter` pins the carry-over that AC 5 depends on.

## Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/data/loop_interpolation_baseline.json` — delete the stale `check_spike_needed` / `check_spike_needed_before_skip` entries in the same commit as the state removal
- Update `docs/guides/LOOPS_REFERENCE.md` — rewrite the autodev-section paragraphs naming the removed spike/decision states and markers
- Update `docs/reference/DEFERRAL_CODES.md`, `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/ISSUE_TEMPLATE.md` — re-attribute citations naming removed autodev states
- Update `skills/decide-issue/reference.md` — drop the `record_decision_unresolved` autodev-routing mention; regenerate host mirrors (`ll-adapt --host <gemini|kimi-code|qwen> --apply`)
- Scope state-name greps to `autodev.yaml` — `spike-gate.yaml` and `rn-remediate.yaml` carry same-named states that must survive

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Large - removes ~30 autodev states and their markers
- **Risk**: High - rewrites routing in the most-used loop
- **Breaking Change**: No - loop-internal

## Program Design

### Types

- No new types; consumes `RunRecord` / `PreparationOutcome` from ENH-3597

### Signatures

- `read_run_record(run_dir: Path, writer: RunRecordWriter, issue_id: str) -> RunRecord | None` — (from ENH-3597) read by the state that replaces `check_passed` for decision/proof routing

### Call Path

`autodev.yaml:refine_current` -> `refine-to-ready-issue.yaml:classify_terminal` -> `write_run_record`

`autodev.yaml` (post-refine routing state) -> `read_run_record` -> `autodev.yaml:check_proof_defer_or_implement` -> `cmd_check_gate` -> `autodev.yaml:implement_current`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Signature correction: `read_run_record(run_dir: Path, writer: str, issue_id: str) -> RunRecord | None` (`scripts/little_loops/run_record.py`). `writer` is a `str` validated against `RunRecordWriter`, not the enum type. `PreparationOutcome` is one of `ready | decomposed | cancelled | blocked | deferred | retryable_error`.
- `RunRecord` is a frozen dataclass with `writer`, `issue_id`, `outcome`, `child_ids`, `evidence_refs`, `legacy_class`, `readiness`, `outcome_confidence`. The path is `<run_dir>/run-records/<writer>/<ID>.json`. `write_run_record(run_dir, record) -> Path`.
- Call path correction: today `refine-to-ready-issue.yaml:classify_terminal` writes the record through `ll-issues run-record write` → `cmd_run_record_write` → `write_run_record`. No consumer state exists in `autodev.yaml`, so the second call path in this section names a state that has to be created.

## Scope Boundaries

- Only the spike and decision families; wire/reconcile/size-review/go-no-go stay until ENH-3601.
- `oracles/resolve-decision.yaml`'s contract is unchanged.
- Keep distinct skills for research, wiring, decisions and reconciliation; do not merge them into one prompt (ENH-3577).

## Acceptance Criteria

- [ ] No state in `autodev.yaml` runs `/ll:spike` or `oracles/resolve-decision`
- [ ] The eight duplicated states are gone from `autodev.yaml`
- [ ] The listed spike/decision marker files are no longer read or written by autodev
- [ ] The only route into `implement_current` is `outcome == ready` (read from the run record; a missing record routes as infra/legacy, never `ready`) → fail-closed `check_proof_defer_or_implement`; `TestProofGateFailClosed` still asserts `implement_current`'s predecessors are exactly `{"check_proof_defer_or_implement"}` with no `on_error`/`on_cannot_judge` edge, and its `check_proof_gate_before_implement.on_error` assertion is rewritten deliberately for the surviving first-stage proof classification
- [ ] `spike-runs-<ID>` persists across autodev re-entries into the child (real-FSM test: the spike budget does not reset)
- [ ] `auto-refine-and-implement` and `oracles/resolve-decision` behavior unchanged
- [ ] `test_autodev_scores_freshness.py` passes unchanged; tests that pinned removed autodev states/markers are rewritten against the child (not deleted); refuted/inconclusive spike routing (BUG-3593) still holds end to end

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, applied 2026-09-25): This issue lands before ENH-3601, so autodev reads the child's record (`writer: refine-to-ready-issue`). After ENH-3601, autodev re-enters the `prepare-issue` wrapper and reads the wrapper's record (`writer: prepare-issue`, `run-records/prepare-issue/<ID>.json`; see ENH-3597). FEAT-3573 was removed from `blocked_by`. It changes closure accounting only and blocks ENH-3600.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-25_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 53/100 → LOW

### Gaps to Address
- blocked_by ENH-3597, FEAT-3598, BUG-3603 (all open) — `RunRecord`/`read_run_record` and the selector do not exist yet, and the fail-closed proof gate this issue routes through is BUG-3603's deliverable. Land the chain first.

### Outcome Risk Factors
- deep per-site complexity — removes ~30 states and rewires routing into `implement_current` in the most-used loop (`autodev.yaml`); marker lifecycles and `spike-runs-<ID>` budget carry-over must survive the rewrite (mitigation: the named behavioral suites + BUG-3603's structural invariant test).
- broad enumeration across ~20 files (2 loop YAMLs + ~10 test files + ~8 docs/skills mirrors); scope state-name greps to `autodev.yaml` so `spike-gate.yaml` / `rn-remediate.yaml` same-named states survive.

## Session Log
- `/ll:refine-issue` - 2026-09-26T02:53:28 - `545abdda-09d4-4321-83bd-74f9c6ff9067.jsonl`
- `/ll:confidence-check` - 2026-09-25T21:32:35 - `672e0da1-840e-4b60-a432-7b20e9ebbd01.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:46:48 - `2b4a714f-91fd-41aa-b2ac-63b11e2476ce.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:42:47 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:18 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
