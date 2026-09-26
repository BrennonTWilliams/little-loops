---
id: ENH-3604
type: ENH
title: Adopt ll-issues next-obligation inside refine-to-ready-issue and settle next-action
  delegation
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-26'
captured_at: '2026-09-26T01:51:59Z'
parent: EPIC-3565
blocked_by:
- FEAT-3598
relates_to:
- ENH-3577
- ENH-3599
- ENH-3608
- ENH-3610
- ENH-3601
---

# ENH-3604: Adopt ll-issues next-obligation inside refine-to-ready-issue and settle next-action delegation

## Summary

Adopt `ll-issues next-obligation` (FEAT-3598) inside `refine-to-ready-issue.yaml`,
replacing the child's bespoke inline predicates with one `route:` dispatch where
the mapping is 1:1, and decide how `ll-issues next-action` relates to the selector.
Split out of FEAT-3598 during its 2026-09-25 review; FEAT-3598 ships the selector only.

## Current Behavior

`refine-to-ready-issue.yaml` evaluates each preparation gate in its own state, several
with bespoke inline Python: `check_placeholders` re-derives `placeholder_count` shell-side
from `format-check --format json`; `check_readiness` / `check_outcome` /
`check_scores_from_file` run heredoc `ll-issues show --json` comparisons against the
seeded `${context.readiness_threshold}` / `${context.outcome_threshold}` (BUG-3552).
`ll-issues next-action` keeps its own per-issue checks (`is_formatted`, session-log
`/ll:verify-issues` presence, threshold read of `commands.confidence_gate`), which differ
from the selector's on every token.

## Expected Behavior

The child's pre-score chain and score predicates route on
`ll-issues next-obligation ID --format token` output, with behaviour identical to today
on every existing routing test. `next-action`'s output tokens and exit codes are unchanged.

## Motivation

Removes the copied readiness predicates FEAT-3598 was created to consolidate (Step B of
ENH-3577), so the child, ENH-3599 and ENH-3601 share one ordering instead of drifting.

## Proposed Solution

Constraints found in the FEAT-3598 review (verified against the child YAML 2026-09-25):

- **FORMAT is not adoptable.** `precheck_format` and `normalize_structure` run
  `format-check --fix --apply` (writes) and bump the one-shot
  `refine-to-ready-format-fallback` counter; the selector is read-only.
  `test_format_probe_routing.py` parametrizes over both states and executes their
  actions. Keep both states.
- **DECISION gains nothing.** `check_decision_needed` / `check_decision_mid_refine` /
  `check_decision_mid_wire` are already one-line `ll-issues check-flag ... decision_needed`.
- **Adoption targets:** the pre-score chain `check_verify_verdict` →
  `check_evidence_unverified` / `check_proposal_unsound` / `check_directive_drift` →
  `check_hedges` → `check_placeholders` → `check_ac_automatable` → `check_design`, and the
  inline heredoc predicates in `check_readiness` / `check_outcome` / `check_scores_from_file`.
- **Keep the done-path gate states.** `check_outcome` and `check_missing_artifacts` write
  the run record on pass, and `test_run_record.py` pins them as `DONE_PATH_GATES`
  (including RC-guard byte-order). Swap only their predicates. Keep
  `test_ready_iff_check_passed_would_pass` (run-record `ready` ≡
  `check-readiness --honor-waiver`) consistent with the selector's `--honor-waiver`.
- **Dispatch mechanics:** one `route:` state over
  `ll-issues next-obligation ID --format token --readiness-threshold ... --outcome-threshold ... --skip ...`,
  modelled on `route_spike_verdict`. It routes to the existing budget states
  (`check_hedge_attempts`, `check_gate_refine_limit`, `check_reconcile_limit`,
  `check_verify_retries`, `check_proposal_revision_budget`, `check_refine_limit`,
  `check_decide_attempts`), never directly to repair states. Budget states that tolerate a
  soft gate record it in a per-run skip file under `${context.run_dir}` that the dispatch
  state turns into `--skip` flags.
- **Error stance:** fail-closed selector errors (exit 2) must route where today's
  fail-closed gates do (`check_verify_verdict.on_error → mark_evidence_absent_infra`;
  outcome → `diagnose`); fail-open gates keep continuing.
- **PROOF:** the selector's PROOF (`assess_proof`) departs from `check_spike_needed`
  (`spike_attempted=true` without `spike_completed` → `absent`; structured `proof` gate
  folded in). Either keep `check_spike_needed` (it also spends the `spike-runs-<ID>`
  budget) or pass `--skip PROOF` when the child's rule says don't respawn. Coordinate with
  ENH-3599, which moves spike/decision repair routing into this child.
- **`next-action`:** either delegate using FEAT-3598's Behavior Parity map (enrich
  `test_next_action.py` fixtures so they pass every preceding obligation), or reduce to
  one shared threshold-resolution helper used by `next-action`, `fsm/context_seed.py`'s
  seeder and the selector. Recommended: the shared helper, because the token semantics
  differ (format session-log shortcut vs `check_format_gaps`; verify session-log presence
  vs persisted verdict).

## Integration Map

Carried over from FEAT-3598's wiring passes (see that issue for per-line citations).

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- `.claude/workflows/refine-to-ready.js` (gitignored, machine-local mirror of the loop)
- `scripts/little_loops/cli/issues/next_action.py` (delegation or shared threshold helper)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — embeds the child (`refine_current`)
- `scripts/little_loops/loops/issue-refinement.yaml`, `scripts/little_loops/loops/recursive-refine.yaml` — delegate into the child and consume `next-action` tokens
- `scripts/little_loops/loops/lib/cli.yaml` — `ll_issues_next` / `ll_issues_next_issue` fragments (unchanged token contract)
- `scripts/little_loops/cli/issues/refine_status.py` — mirrors next-action's predicate inputs
- `scripts/little_loops/fsm/context_seed.py` — `seed_confidence_thresholds` (called from `cli/loop/run.py`, `cli/loop/lifecycle.py`, `cli/loop/info.py`, `fsm/executor.py`)

### Tests
- `scripts/tests/test_builtin_loops.py` — TestRefineToReadyIssueSubLoop routing tests for every replaced state; `check_readiness.on_error == check_scores_from_file` pins; `MR11_MARKER_ALLOWLIST` refine tuples (move in lockstep with `# ll-lint: mr11-ok(...)` markers); `test_context_fallbacks_match_selector_defaults`; `TestInterpSweepBaseline::test_completeness_guard`
- `scripts/tests/data/loop_interpolation_baseline.json` — three refine entries (`check_outcome`, `check_readiness`, `check_scores_from_file`); baseline any new dispatch state
- `scripts/tests/test_run_record.py` — `DONE_PATH_GATES`, RC-guard ordering, `TestTerminalExecution`, `test_ready_iff_check_passed_would_pass`
- `scripts/tests/test_format_probe_routing.py` — executes `normalize_structure` / `precheck_format` actions (keep both states)
- `scripts/tests/test_spike_verdict_routing.py` — child spike/decision route table
- `scripts/tests/test_next_action.py`, `scripts/tests/test_fsm_fragments.py`, `scripts/tests/test_issue_refinement_broke_down.py`, `scripts/tests/test_issue_parser.py` (`next_action:30` anchor)
- Corpus gates: `scripts/tests/test_builtin_loop_interpolation.py` (escape bash `${...}` as `$${...}`), `test_fsm_fragments.py::test_builtin_loops_load_after_migration`, MR-14 sweep in `scripts/tests/test_fsm_schema.py`

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — refine-to-ready gate-chain narrative, ASCII diagrams, fragment table rows
- `docs/reference/CLI.md` — state-name prose (check-flag consumers, run-record callers, `--proposal-unsound` / `--directive-drift`, check-readiness FSM-loop-use note)
- `docs/reference/DEFERRAL_CODES.md` — `spike_inconclusive` / `proposal_unsound` source states
- `commands/verify-issues.md` — persisted-verdict contract names `check_verify_verdict` / `check_proposal_unsound` (host mirrors via `ll-adapt`)
- `scripts/little_loops/loops/README.md` — child catalog rows

## Program Design

### Types

- No new Python types. Consumes `Obligation` / `ObligationResult` from FEAT-3598.

### Signatures

- `seed_confidence_thresholds(context: dict[str, Any], config: Any = None) -> None` — existing seeder in `fsm/context_seed.py`; if the shared-helper option is chosen, the threshold resolution it and `cmd_next_action` share is extracted beside it
- `cmd_next_action(config: BRConfig, args: argparse.Namespace) -> int` — existing; output tokens and exit codes unchanged

### Call Path

- Loop: `refine-to-ready-issue` dispatch state -> `cmd_next_obligation` -> `select_next_obligation` (FEAT-3598 deliverables)
- Thresholds (shared-helper option): `cmd_next_action` -> `seed_confidence_thresholds` resolution, replacing its direct `commands.confidence_gate` read

## Implementation Steps

1. Confirm FEAT-3598's final CLI shape (`--format token`, `--skip`, threshold flags, exit codes).
2. Add the dispatch state and the per-run skip file; rewire the pre-score chain through it to the existing budget states.
3. Swap the predicates inside `check_readiness` / `check_outcome` / `check_scores_from_file` for the selector, keeping the states, run-record writes and RC guards.
4. Decide and implement the `next-action` option (shared threshold helper recommended).
5. Update routing/baseline/MR11 tests in lockstep; update the gate-chain docs.

## Impact

- **Priority**: P3 — follow-up to FEAT-3598 under EPIC-3565
- **Effort**: Medium — loop rewiring plus a broad test/doc lockstep
- **Risk**: Medium — changes routing in a child embedded by autodev, issue-refinement and recursive-refine
- **Breaking Change**: No

## Scope Boundaries

- No change to FEAT-3598's selector semantics; if adoption needs one, change FEAT-3598's surface first.
- Adoption in `autodev.yaml` stays with ENH-3599 / ENH-3601.
- `next-action` output tokens and exit codes stay unchanged.

## Acceptance Criteria

- [ ] The child's pre-score chain and score predicates route through `ll-issues next-obligation`; FORMAT states and the decision `check-flag` states are kept
- [ ] Every existing child routing test passes with only the documented lockstep updates (state renames, baseline entries, MR11 tuples)
- [ ] `test_run_record.py` done-path gate and ready-iff-check-readiness tests pass
- [ ] Soft gates (hedge budget, format fallback) still let the run proceed via `--skip`
- [ ] `next-action` output unchanged; its threshold resolution shares one helper with the selector and seeder (or delegates, per the decision recorded here)
- [ ] Gate-chain docs updated

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-26T01:52:07 - `f544b4eb-e137-4689-a451-49e3380df0f3.jsonl`
