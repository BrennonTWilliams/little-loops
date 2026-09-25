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
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (only if a route is missing in the child)

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
- Behavioral, must pass unchanged: `test_spike_verdict_routing.py`,
  `test_autodev_decision_gate.py`, `test_autodev_scores_freshness.py`
- Structural, rewrite: `test_fsm_topology.py`, `test_builtin_loops.py`, `test_autodev_loop.py`

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

## Scope Boundaries

- Only the spike and decision families; wire/reconcile/size-review/go-no-go stay until ENH-3601.
- `oracles/resolve-decision.yaml`'s contract is unchanged.
- Keep distinct skills for research, wiring, decisions and reconciliation; do not merge them into one prompt (ENH-3577).

## Acceptance Criteria

- [ ] No state in `autodev.yaml` runs `/ll:spike` or `oracles/resolve-decision`
- [ ] The eight duplicated states are gone from `autodev.yaml`
- [ ] The listed spike/decision marker files are no longer read or written by autodev
- [ ] The only route into `implement_current` is `outcome == ready` → fail-closed proof gate; BUG-3603's invariant test passes
- [ ] `spike-runs-<ID>` persists across autodev re-entries into the child (real-FSM test: the spike budget does not reset)
- [ ] `auto-refine-and-implement` and `oracles/resolve-decision` behavior unchanged
- [ ] Behavioral test set passes unchanged; refuted/inconclusive spike routing (BUG-3593) still holds end to end
  > ⚠ Superseded — spike-routing tests assert removed autodev markers

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
- `/ll:confidence-check` - 2026-09-25T21:32:35 - `672e0da1-840e-4b60-a432-7b20e9ebbd01.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:46:48 - `2b4a714f-91fd-41aa-b2ac-63b11e2476ce.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:42:47 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:18 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
