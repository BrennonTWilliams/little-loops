---
id: BUG-3603
type: BUG
title: Autodev pre-implement proof gate fails open into implement_current
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T20:00:00Z'
parent: EPIC-3565
blocks:
- ENH-3599
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3603: Autodev pre-implement proof gate fails open into implement_current

## Summary

The only three edges into `implement_current` in `autodev.yaml` (all in the two proof-gate
states, `autodev.yaml:728`, `:743`, `:744`) fail open, in two distinct ways: a helper error
in the proof gate sends the issue straight into implementation, and so does a real `prose`
verdict, which every other `check-gate` consumer treats as a gate in force. Either breaks
EPIC-3565's acceptance criterion that every edge into `implement_current` passes the same
preparation gates. No existing child covers it.

## Current Behavior

`check_passed` → `check_proof_gate_before_implement` → `check_proof_defer_or_implement` →
`implement_current` (`scripts/little_loops/loops/autodev.yaml:690-744`). Both gate states
fail open, in three ways:

1. **Routing**: both states have `on_error: implement_current` (lines 728, 744), and the
   second state's `on_no` is `implement_current` (line 743).
2. **Action**: both run `ll-issues check-gate "$ID" 2>/dev/null || true` and map any
   unrecognised output to `PROOF_CLEAR` (the `*)` case). When the helper crashes, cannot
   resolve the ID or exits 2 with empty output, the result is `PROOF_CLEAR`, and the
   issue goes to `on_no: implement_current`.
3. **`prose` verdict** (real verdict, not helper error): a `prose` hit falls to the same
   `*)` → `PROOF_CLEAR` case, but every other `check-gate` consumer treats `prose` as a
   gate in force — dequeue routes `structured_open|prose` to `defer_gated`
   (`autodev.yaml:445`), and `recheck_after_size_review` counts `structured_proof|prose`
   as `GATE_MARKER=true` (`:2822`). The proof states are the only consumers that let a
   `prose` gate through. This is reachable: refine/reconcile rewrites can add gate prose
   mid-run after a clean dequeue, and the last gate then waves the issue into
   implementation.

The comment at line 697 says the fail-open is deliberate and "matching the dequeue gate".
That reasoning does not carry over. A dequeue-time gate that fails open (lines 202, 305,
432) sends the issue into the refine pipeline, where later gates still apply. The
pre-implement gate is the **last** gate. After it, nothing checks the proof obligation
again. The `ll-auto` learning gate covers only Learning Test Registry records, not
`check-gate` `structured_proof` / `structured_open`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `cmd_check_gate` (`scripts/little_loops/cli/issues/check_gate.py`) prints exactly one verdict token — structured_open, structured_proof, structured_satisfied, prose, or none — and exits 0 for the in-force verdicts (**structured_open, structured_proof, prose**), 1 for structured_satisfied/none, and 2 when the issue cannot be resolved. The `2>/dev/null || true` wrapper in both gate states erases that exit code, so a real none verdict (exit 1) and a not-found helper failure (exit 2, empty stdout) are indistinguishable — capturing the exit code is the discriminator that separates verdict from failure. Note that `prose` being in the exit-0 in-force set is load-bearing: a `prose` verdict is a *successful* helper call reporting a gate, so the exit-code discriminator alone cannot catch it; it needs its own `PROOF_DEFER` case (see Proposed Solution).
- Every other `check-gate` consumer in the repo uses the same `$(... || true)` fail-open shape (`check_gate_at_dequeue`, ~L420-485, carries the same comment). The dequeue sites can stay fail-open (later gates still apply); only the two pre-implement states need the discriminator.

## Expected Behavior

A helper error in either pre-implement gate state never reaches `implement_current` — it
routes to a named infra deferral (a `mark_proof_gate_infra` sibling of `mark_gate_infra`)
and is ledgered in `summary.json`. A `prose` verdict at either state routes to
`PROOF_DEFER`, consistent with dequeue's `defer_gated` and recheck's `GATE_MARKER`
handling. The only way to reach `implement_current` is a positive `PROOF_CLEAR` from a
successful `check-gate` call reporting no gate (`none` / `structured_satisfied`).

## Steps to Reproduce

1. Stub `ll-issues check-gate` to exit 2 with no output (or raise).
2. Run autodev on an issue whose `check-readiness` passes and whose gate is
   `structured_proof`.
3. Observe the route `check_proof_gate_before_implement` → `check_proof_defer_or_implement`
   → `implement_current`. The unproven issue is implemented.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `check_proof_gate_before_implement`, `check_proof_defer_or_implement`
- **Cause**: ENH-3575 copied the dequeue gates' fail-open policy onto the final gate
  before implementation, where no downstream gate exists.

## Proposed Solution

- In both states, tell a real verdict apart from a helper failure. Capture the exit code
  and emit `PROOF_INFRA` only when the call failed **as a helper**: exit >= 2, empty
  stdout, or an unrecognised token. Exit 1 with a recognised token (`none`,
  `structured_satisfied`) and exit 0 with any of the five tokens are real verdicts —
  `none`/`structured_satisfied` stay `PROOF_CLEAR` (pinned by
  `test_no_gate_reaches_implement`; "non-zero exit" alone cannot be the discriminator).
- Add `prose` to the `PROOF_DEFER` case in both states — dequeue (`:445`) and recheck
  (`:2822`) already treat `prose` as in-force, and no existing test pins `prose` at the
  proof states.
- Route `PROOF_INFRA` and `on_error` to an infra deferral, never to `implement_current`.
- Keep `recheck_after_size_review` (`:2821`) fail-open — DECIDED: every path out of it is
  backstopped by the fixed pre-implement gate (on_yes → `decide_current` → proof gate;
  on_no/on_error → remedy/dequeue paths that never implement). Add a comment at the site
  saying so.
- Replace the line-697 comment with the fail-closed rationale.
- Add a structural invariant test: in `autodev.yaml`, no state's `on_error` (or
  `on_cannot_judge`) targets `implement_current`, and every predecessor of
  `implement_current` is a proof-gate state. This test protects the invariant through
  the ENH-3599 / ENH-3601 routing migrations.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `summary.json` (`autodev.yaml` `finalize_done` ~L3165) is a fixed printf with keys `verdict, closed, not_closed, skipped, gate_blocked, decision_unresolved, not_started, inflight_unresolved, abandoned, stop_reason, pending` — no infra key exists today. Infra deferrals currently surface only as text lines: `finalize_done` filters `refine_failed_infra`-suffixed entries out of `SKIPPED_IDS` into `INFRA_SKIPPED_IDS` (~L3005-3022), and the per-reason ledgers (`autodev-scores-absent.txt`, `autodev-gate-infra.txt`, `autodev-spike-no-verdict.txt`) are never counted into the JSON. Satisfying AC 4 (infra deferrals in `summary.json`) therefore means either extending the `summary.json` key set or adding a per-reason ledger `finalize_done` counts — no existing mechanism puts infra deferrals in that file.

## Program Design

### Types

- No new types. Adds a `PROOF_INFRA` sentinel alongside the existing `PROOF_SPIKE` / `PROOF_DEFER` / `PROOF_CLEAR` shell outputs.

### Signatures

- `cmd_check_gate(config: BRConfig, args: argparse.Namespace) -> int` — existing; its exit code and verdict set become the discriminator between a real verdict and a helper failure (no signature change)

### Call Path

`autodev.yaml:check_proof_gate_before_implement` -> `cmd_check_gate` -> `autodev.yaml:check_proof_defer_or_implement` -> `autodev.yaml:implement_current`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `check_proof_gate_before_implement`, `check_proof_defer_or_implement`
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — `recheck_after_size_review` (~L2821) is a third `check-gate` consumer (GATE_MARKER remedy-selector branch); DECIDED: keep it fail-open — every path out of it is backstopped by the fixed pre-implement gate (on_yes → `decide_current` → proof gate; on_no/on_error → remedy/dequeue paths that never implement). Add a comment at the site stating the backstop.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/` — `check-gate` output/exit contract (read only; confirm the recognised verdict set)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — VERIFIED 2026-09-25: the wire-issue pass overstated this — the `skip_inflight_infra` references at :155/:4320 are BUG-2731 comments only; the string appears nowhere in executor code, and the state itself lives in `autodev.yaml`. **No executor change is needed**: the new infra state is reached via plain `on_error` routing, and BUG-2731's exit-143 retry fall-through lands on the same `on_error` edge naturally.
- `scripts/little_loops/loops/scan-and-implement.yaml` — `loop: autodev` subloop at :79, the only loop YAML invoking autodev; inherits the new gate behavior
- `scripts/little_loops/cli/loop/audit.py` — `audit_run` (~L194) embeds summary.json into `verdict_inputs["summary"]` (~L247); no strict key-set parser exists for autodev's summary (the strict asserts at `test_rn_refine.py:1485/:1540` are rn-refine's), so a new infra key is additive-safe

### Similar Patterns
- `mark_evidence_absent_infra` / `skip_inflight_infra` infra deferral routes

### Tests
- New real-FSM test: `check-gate` stub failing → issue is deferred as infra, `implement_current` not entered
- New real-FSM test: `prose` verdict at either proof state → `PROOF_DEFER` (no existing test pins `prose` there)
- New structural test: no `on_error`/`on_cannot_judge` edge into `implement_current`
- Must still pass: `scripts/tests/test_spike_verdict_routing.py`, `test_ll_issues_check_gate.py`
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_check_gate.py` — `_run_state` (:165) returns only stdout; PROOF_INFRA tests need returncode+stderr surfaced — extend the helper, don't fork it. Discriminator nuance: the `none` verdict ("no proof gate") exits **1** with token `none` (TestCli param row in `test_verdict_and_exit_code`; `test_no_gate_reaches_implement` :236 pins `PROOF_CLEAR`) — the discriminator must keep exit-1-with-recognised-token → PROOF_CLEAR; `PROOF_INFRA` is only for exit 2 / empty stdout / unrecognised output
- May break: `scripts/tests/test_fsm_topology.py:259` — `len(states) == 105` must be bumped with a change-log comment line naming BUG-3603 (convention :239-258)
- Rename-sensitive pins (break only if the guard is renamed/interposed): `test_autodev_decision_gate.py:990` `test_recheck_after_decide_on_yes_routes_to_implement_current`; routing pins `test_builtin_loops.py:8372` (`check_passed.on_yes`), :9226/:9234 (`decide_current` on_no/on_error), :9426 (`recheck_after_decide.on_yes`)
- Infra-state test exemplars: `test_skip_inflight_infra_*` family (`test_builtin_loops.py:6921-7019`); `test_infra_state_is_distinct_and_does_not_defer` (`test_autodev_scores_freshness.py:76` — per-reason ledger separation, no `set-status`, `next == dequeue_next`); `test_mark_gate_infra_advances_queue_without_defers` (:8072)
- Structural-invariant exemplars: `test_assert_decision_cleared_absent_from_autodev_states` (`test_autodev_decision_gate.py:1004` — every-state × every-edge-kind iteration), the `only_done_edge` predecessor-set comprehension (`test_builtin_loops.py:7567-7572`), graph-walk idiom (:18306); host in `TestAutodevLoop` (`test_builtin_loops.py:6643`) or a dedicated per-fix file
- Corpus gates every new state must clear: `test_all_validate_as_valid_fsm` (:77), `test_no_failure_edge_routes_to_a_success_terminal` (:87), `MR11_MARKER_ALLOWLIST` ratchet (:21037) if a lint marker is added
- Additive summary-key test exemplars: `test_finalize_summary_has_enh_2404_keys` (:5436) / `test_finalize_sources_gate_blocked_ledger` (:5630) — extend the `_run_finalize_done` harness (:7475) with a ledger-seeding parameter; note `INFRA_SKIPPED_COUNT` is computed in `finalize_done` (~L3044) but never printed — the new key joins the printf at ~L3165 and its key-set test pins the full key list
- Init-ledger tests to extend: `test_spike_verdict_routing.py:108`/:231 (init must reference each per-reason ledger), `test_init_resets_autodev_inflight` (`test_builtin_loops.py:8548`)

### Documentation
- N/A
_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — autodev section: the state-flow diagram (~L1033-1085) already omits the ENH-3575 proof-gate states; the "Diagram omissions" paragraph (~L1079) documents the fail-open policy — BUG-3603 creates the first deliberately fail-closed gate, record the distinction; the "Notes" paragraph (~L1081) documents the infra-deferral ledger set the new ledger joins
- `docs/reference/CLI.md` — `#### ll-issues check-gate` (~L2316-2318): the verdict/exit-code contract and the FSM-consumer-states note; after this change the pre-implement states consume the exit code, not just the stdout token
- `skills/audit-loop-run/SKILL.md` — "Step 6a: Summary Cross-Check" (~L258-279) lists summary.json keys under an explicit additive-keys convention; add the new infra key there (test exemplars: `test_audit_loop_run_skill.py` :144/:157/:168)

### Configuration
- N/A

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/LOOPS_REFERENCE.md` — fail-closed gate distinction, new infra ledger, diagram omission note
- Update `docs/reference/CLI.md` check-gate section and `skills/audit-loop-run/SKILL.md` Step 6a key list for the new summary.json infra key
- ~~Audit `scripts/little_loops/fsm/executor.py` `skip_inflight_infra` special case (:155, :4320)~~ RESOLVED: verified 2026-09-25 that this was a phantom — the references are BUG-2731 comments only, `skip_inflight_infra` appears nowhere in executor code; no executor change needed (see Dependent Files)
- Extend `_run_state` in `scripts/tests/test_ll_issues_check_gate.py` to surface returncode+stderr for the PROOF_INFRA failure-path tests
- Bump `test_fsm_topology.py:259` autodev state count (105 → 106+) with a BUG-3603 change-log comment
- Keep exit-1-with-`none`-token routing to `PROOF_CLEAR` — `test_no_gate_reaches_implement` pins it; "non-zero exit" alone cannot be the discriminator

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Infra-deferral state convention — the rule shared by `mark_scores_absent_infra` (~L1301), `mark_gate_infra` (~L1286), `mark_spike_no_verdict_infra` (~L1756), and `skip_inflight_infra` (~L609): append the ID to a per-reason file under `${context.run_dir}/`, `rm -f ${context.run_dir}/autodev-inflight`, echo a `[TAG] $ID` line, route `next`/`on_error` to `dequeue_next`, and never call `ll-issues set-status`. `init` (~L63-73) truncates the ledger files it knows about — a new ledger file must be added there.
- Structural-test convention: load `autodev.yaml` via `yaml.safe_load(...)["states"]` and loop every state collecting its route targets, asserting the forbidden target absent — same shape as `test_commit_change_reachable_only_via_accept_gate_on_yes` (`scripts/tests/test_builtin_loops.py` ~L14138) and `test_check_residual_decision_never_reenters_open_question_progress` (~L3887). Edge sets vary between those tests (some omit `next`, none seen include `route` values); the new invariant should collect the full `{on_yes, on_no, on_cannot_judge, on_error, next}` set plus `classify` `route:` values.
- Real-state-action test convention: extract `action` from the YAML, textually replace `${captured.input.output[:shell]}`/`${context.run_dir}`, run under `bash -c` with a stub `ll-issues` first on `PATH` — `test_ll_issues_check_gate.py:_run_state` (:165; the ~L26-51 cite in an earlier draft pointed at the `_cli`/`_write`/`_run` helpers) and the one-line stub in `test_spike_verdict_routing.py`. No existing test stubs `check-gate` to exit nonzero/empty against the two proof-gate states (searched, none found) — the new failure-path coverage is genuinely new, not a duplicate.
- Existing pins that must keep passing: `test_ll_issues_check_gate.py:240` `test_implement_edges_route_through_guard` (`check_passed.on_yes` → `check_proof_gate_before_implement`; `check_proof_defer_or_implement.on_no` → `implement_current`); `test_fsm_topology.py` ~L253-258 asserts the autodev **state count** (+2 from ENH-3575) — adding any new state changes the expected number there; `test_builtin_loops.py:7935` `test_check_readiness_call_sites_pass_honor_waiver`.

## Impact

- **Priority**: P2 — an unproven issue can be implemented on a helper failure, in every local-editable project
- **Effort**: Small — two states (helper-failure discriminator + `prose` case), one new infra-deferral state + ledger, three tests
- **Risk**: Low — tightens the error path and the `prose`-verdict path; the `PROOF_CLEAR` success path for `none`/`structured_satisfied` is unchanged
- **Breaking Change**: No

## Acceptance Criteria

- [ ] A failing `check-gate` (exit ≥ 2 / empty stdout / unrecognised token) never routes to `implement_current`
- [ ] A `prose` verdict at either pre-implement state routes to `PROOF_DEFER` (consistent with dequeue/recheck consumers)
- [ ] No `on_error` / `on_cannot_judge` in `autodev.yaml` targets `implement_current` (structural test)
- [ ] Infra deferrals from this gate appear in `summary.json`
- [ ] Behavioral spike/gate tests pass unchanged

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item). Verified via
`/ll:verify-issues BUG-3603 --auto` on 2026-09-25:

- **Fail-open claims confirmed exact**: lines 728/743/744 are the only routing
  edges into `implement_current` (all other mentions are comments); both states
  run `ll-issues check-gate "$ID" 2>/dev/null || true` with a `*) → PROOF_CLEAR`
  fallthrough; the line-697 comment reads verbatim "Fail-open (implement_current)
  on helper error, matching the dequeue gate."
- **`prose` inconsistency confirmed**: dequeue (`check_gate_at_dequeue`, state at
  :420) maps `structured_open|prose` → gated; `recheck_after_size_review`
  (~:2822) maps `structured_proof|prose` → `GATE_MARKER=true`. The proof states'
  `*)` case is the only consumer that waves `prose` through.
- **Helper contract confirmed**: `_IN_FORCE = ("structured_open",
  "structured_proof", "prose")` (`check_gate.py:29`); exit 0 in-force / 1
  not-in-force / 2 not-found — the `|| true` wrapper erases exactly that
  discriminator.
- **Summary/infra claims confirmed**: `summary.json` printf (~:3165) has exactly
  the listed keys, no infra key; `INFRA_SKIPPED_IDS` filter (~:3005-3022) and
  `INFRA_SKIPPED_COUNT` (~:3044, computed but never printed) as described;
  infra-state convention sites (`skip_inflight_infra` :609, `mark_gate_infra`
  :1286, `mark_scores_absent_infra` :1301, `mark_spike_no_verdict_infra` :1756)
  and `init` ledger truncation (~:63-73) verified.
- **Executor phantom confirmed resolved**: `skip_inflight_infra` appears in
  `fsm/executor.py` only at :155 and :4320, both inside BUG-2731 comments — no
  executor change needed, as the wiring pass states.
- **Test/doc pins spot-checked**: `_run_state` :165, `test_no_gate_reaches_implement`
  :236, `test_implement_edges_route_through_guard` :240, topology count 105 at
  `test_fsm_topology.py:259`, routing pins `test_builtin_loops.py:8372/:9226/:9234/:9426`
  (all assert routes *to* `check_proof_gate_before_implement`, so "rename-sensitive"
  is accurate), `test_autodev_decision_gate.py:990/:1004`,
  `test_autodev_scores_freshness.py:76`, `test_builtin_loops.py:8072`,
  `test_spike_verdict_routing.py:108/:231`, CLI.md check-gate section, and
  audit-loop-run SKILL.md Step 6a all present as cited.
- **Fixed in this pass**: the codebase-research line cited `_run_state` at
  "~L26-51"; those lines hold the `_cli`/`_write`/`_run` helpers. Corrected to
  :165 (which the Tests section already had right). Also corrected a stale
  cross-reference in the summary.json research finding: "Satisfying AC 3" →
  "Satisfying AC 4" (the infra-deferrals-in-summary.json requirement is the
  fourth Acceptance Criterion; AC 3 is the structural `on_error` test).
- **Checks run clean**: decisions required-rules query (no active required
  rules), `ll-verify-evidence` (0 findings), dependency integrity (`blocks:
  ENH-3599` exists with BUG-3603 in its Blocked By; `parent: EPIC-3565` exists).
- **Proposal consequence check (ENH-3250)**: no conflict found — the proposal's
  discriminator, `prose` → `PROOF_DEFER` case, infra state + ledger + init
  truncation + topology bump, and summary-key addition each name the code they
  touch, and the ACs cover every Integration Map point. The
  exit-1-with-`none`-token → `PROOF_CLEAR` nuance is correctly preserved against
  `test_no_gate_reaches_implement`.

## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Session Log
- `/ll:verify-issues` - 2026-09-25T22:07:56 - `2f707f2c-dcf9-4b23-953c-4a951adbadbc.jsonl`
- Review revision - 2026-09-25 - pre-implementation review: folded the `prose`-verdict fail-open into scope, reconciled the PROOF_INFRA discriminator spec with the wiring nuance (exit ≥ 2 / empty stdout / unrecognised token; exit-1-with-recognised-token stays PROOF_CLEAR), corrected the phantom executor.py special-case claim, resolved the recheck_after_size_review decision (keep fail-open, backstopped)
- `/ll:confidence-check` - 2026-09-25T21:22:42 - `345d0814-f8e9-469f-ad62-bef9083d17be.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:51:15 - `85e4cae3-0d07-49cf-9a70-1d94df7e46ab.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:48:48 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:capture-issue` - 2026-09-25 - EPIC-3565 child review
