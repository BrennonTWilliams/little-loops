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
---

# BUG-3603: Autodev pre-implement proof gate fails open into implement_current

## Summary

The only two edges into `implement_current` in `autodev.yaml` fail open. A helper error in
the proof gate sends the issue straight into implementation. This breaks EPIC-3565's
acceptance criterion that every edge into `implement_current` passes the same preparation
gates. No existing child covers it.

## Current Behavior

`check_passed` → `check_proof_gate_before_implement` → `check_proof_defer_or_implement` →
`implement_current` (`scripts/little_loops/loops/autodev.yaml:690-744`). Both gate states
fail open, in two ways:

1. **Routing**: both states have `on_error: implement_current` (lines 728, 744).
2. **Action**: both run `ll-issues check-gate "$ID" 2>/dev/null || true` and map any
   unrecognised output to `PROOF_CLEAR` (the `*)` case). When the helper crashes, cannot
   resolve the ID or exits 2 with empty output, the result is `PROOF_CLEAR`, and the
   issue goes to `on_no: implement_current`.

The comment at line 697 says the fail-open is deliberate and "matching the dequeue gate".
That reasoning does not carry over. A dequeue-time gate that fails open (lines 202, 305,
432) sends the issue into the refine pipeline, where later gates still apply. The
pre-implement gate is the **last** gate. After it, nothing checks the proof obligation
again. The `ll-auto` learning gate covers only Learning Test Registry records, not
`check-gate` `structured_proof` / `structured_open`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `cmd_check_gate` (`scripts/little_loops/cli/issues/check_gate.py`) prints exactly one verdict token — structured_open, structured_proof, structured_satisfied, prose, or none — and exits 0 for the in-force verdicts (structured_open, structured_proof), 1 for structured_satisfied/none, and 2 when the issue cannot be resolved. The `2>/dev/null || true` wrapper in both gate states erases that exit code, so a real none verdict (exit 1) and a not-found helper failure (exit 2, empty stdout) are indistinguishable — capturing the exit code is the discriminator that separates verdict from failure.
- Every other `check-gate` consumer in the repo uses the same `$(... || true)` fail-open shape (`check_gate_at_dequeue`, ~L420-485, carries the same comment). The dequeue sites can stay fail-open (later gates still apply); only the two pre-implement states need the discriminator.

## Expected Behavior

A helper error in either pre-implement gate state never reaches `implement_current`. It
routes to a named infra deferral (for example `skip_inflight_infra` or `defer_gated`
with an infra reason) and is ledgered in `summary.json`. The only way to reach
`implement_current` is a positive `PROOF_CLEAR` from a successful `check-gate` call.

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

- In both states, tell a real `check-gate` verdict apart from a helper failure. Capture
  the exit code and emit `PROOF_INFRA` on non-zero exit or empty output. Keep
  `PROOF_CLEAR` only for a recognised "no proof gate" verdict.
- Route `PROOF_INFRA` and `on_error` to an infra deferral, never to `implement_current`.
- Replace the line-697 comment with the fail-closed rationale.
- Add a structural invariant test: in `autodev.yaml`, no state's `on_error` (or
  `on_cannot_judge`) targets `implement_current`, and every predecessor of
  `implement_current` is a proof-gate state. This test protects the invariant through
  the ENH-3599 / ENH-3601 routing migrations.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `summary.json` (`autodev.yaml` `finalize_done` ~L3165) is a fixed printf with keys `verdict, closed, not_closed, skipped, gate_blocked, decision_unresolved, not_started, inflight_unresolved, abandoned, stop_reason, pending` — no infra key exists today. Infra deferrals currently surface only as text lines: `finalize_done` filters `refine_failed_infra`-suffixed entries out of `SKIPPED_IDS` into `INFRA_SKIPPED_IDS` (~L3005-3022), and the per-reason ledgers (`autodev-scores-absent.txt`, `autodev-gate-infra.txt`, `autodev-spike-no-verdict.txt`) are never counted into the JSON. Satisfying AC 3 therefore means either extending the `summary.json` key set or adding a per-reason ledger `finalize_done` counts — no existing mechanism puts infra deferrals in that file.

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

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/` — `check-gate` output/exit contract (read only; confirm the recognised verdict set)

### Similar Patterns
- `mark_evidence_absent_infra` / `skip_inflight_infra` infra deferral routes

### Tests
- New real-FSM test: `check-gate` stub failing → issue is deferred as infra, `implement_current` not entered
- New structural test: no `on_error`/`on_cannot_judge` edge into `implement_current`
- Must still pass: `scripts/tests/test_spike_verdict_routing.py`, `test_ll_issues_check_gate.py`

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Infra-deferral state convention — the rule shared by `mark_scores_absent_infra` (~L1301), `mark_gate_infra` (~L1286), `mark_spike_no_verdict_infra` (~L1756), and `skip_inflight_infra` (~L609): append the ID to a per-reason file under `${context.run_dir}/`, `rm -f ${context.run_dir}/autodev-inflight`, echo a `[TAG] $ID` line, route `next`/`on_error` to `dequeue_next`, and never call `ll-issues set-status`. `init` (~L63-73) truncates the ledger files it knows about — a new ledger file must be added there.
- Structural-test convention: load `autodev.yaml` via `yaml.safe_load(...)["states"]` and loop every state collecting its route targets, asserting the forbidden target absent — same shape as `test_commit_change_reachable_only_via_accept_gate_on_yes` (`scripts/tests/test_builtin_loops.py` ~L14138) and `test_check_residual_decision_never_reenters_open_question_progress` (~L3887). Edge sets vary between those tests (some omit `next`, none seen include `route` values); the new invariant should collect the full `{on_yes, on_no, on_cannot_judge, on_error, next}` set plus `classify` `route:` values.
- Real-state-action test convention: extract `action` from the YAML, textually replace `${captured.input.output[:shell]}`/`${context.run_dir}`, run under `bash -c` with a stub `ll-issues` first on `PATH` — `test_ll_issues_check_gate.py:_run_state` (~L26-51) and the one-line stub in `test_spike_verdict_routing.py`. No existing test stubs `check-gate` to exit nonzero/empty against the two proof-gate states (searched, none found) — the new failure-path coverage is genuinely new, not a duplicate.
- Existing pins that must keep passing: `test_ll_issues_check_gate.py:240` `test_implement_edges_route_through_guard` (`check_passed.on_yes` → `check_proof_gate_before_implement`; `check_proof_defer_or_implement.on_no` → `implement_current`); `test_fsm_topology.py` ~L253-258 asserts the autodev **state count** (+2 from ENH-3575) — adding any new state changes the expected number there; `test_builtin_loops.py:7935` `test_check_readiness_call_sites_pass_honor_waiver`.

## Impact

- **Priority**: P2 — an unproven issue can be implemented on a helper failure, in every local-editable project
- **Effort**: Small — two states, one route target, two tests
- **Risk**: Low — tightens only the error path; the success path is unchanged
- **Breaking Change**: No

## Acceptance Criteria

- [ ] A failing `check-gate` never routes to `implement_current`
- [ ] No `on_error` / `on_cannot_judge` in `autodev.yaml` targets `implement_current` (structural test)
- [ ] Infra deferrals from this gate appear in `summary.json`
- [ ] Behavioral spike/gate tests pass unchanged

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-09-25T19:48:48 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:capture-issue` - 2026-09-25 - EPIC-3565 child review
