---
id: ENH-3577
type: ENH
title: Consolidate autodev issue preparation into a single controller loop
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:14Z'
parent: EPIC-3565
blocked_by:
- BUG-3571
- BUG-3591
- BUG-3592
- BUG-3593
- FEAT-3573
- BUG-3574
- ENH-3575
- ENH-3576
- BUG-3588
completed_at: '2026-09-25T18:52:57Z'
---

# ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Summary

Consolidate autodev's per-issue preparation into one single-issue controller (extending
`refine-to-ready-issue`), so the outer `autodev` loop owns only queue orchestration and
accounting. Today repair and rescoring policy is split between parent and child. Autodev
re-implements spike, reconcile, size-review, design-remedy and decision routing, with its own
marker files (`autodev-pre-deferral-remedy.txt`, `autodev-decide-ran`, the fired markers),
and `ll-issues show` + inline Python predicates are copied across states. The route-specific
contract gaps in EPIC-3565's children come directly from this duplication.

## Current Behavior

Autodev (105 states) duplicates the child loop's repair routing, with its own marker
handshakes and copied inline predicates:

- **States present in both loops by name**: `check_spike_needed`, `run_spike`,
  `route_spike_verdict`, `check_spike_budget`, `record_spike_inconclusive`,
  `mark_spike_no_verdict_infra`, `check_missing_artifacts`, `check_decide_rate_limited`,
  `record_decision_unresolved`.
- **Rescoring triplet copied five times**: `clear_scores_before_*` →
  `rerun_confidence_after_*` → `check_scores_present_*` for `decide`, `wire`, `spike`,
  `atomic` and `reconcile` (15 states).
- **Predicate duplication**: `ll-issues show` appears 37× in `autodev.yaml` vs 12× in
  `refine-to-ready-issue.yaml`; inline Python predicates 32× vs 7×.
- **Handshake files**: autodev reads/writes ~50 distinct `${context.run_dir}/autodev-*`
  files. The child already emits a partial typed channel: `refine-terminal-class`
  (`proposal_unsound | gate_unmet | infra | spike_inconclusive | decision_unresolved`,
  read by `skip_inflight`, default `quality`) and `refine-broke-down` (read by
  `copy_broke_down`).
- **Second-pass repair after the child returns**: `refine_current` → `check_passed`; on
  failure `triage_outcome_failure` fans out into spike, wire/refine, size-review, atomic
  remediation, design/reconcile, pre-deferral remedy and go/no-go — all *before*
  `implement_current`. The child's `done` terminal therefore does not mean "ready".

## Expected Behavior

The child owns all per-issue preparation and returns a typed outcome. Autodev owns only the
queue, dispatch, implementation and accounting.

## Motivation

- The outer loop has 105 states, with a large inline `finalize_done`.
- Learning-proof ownership is spread across confidence-check, ready-issue and the learning
  primitive, which each treat refuted/stale records differently.
- Each duplicated route is a place where the readiness invariant can silently fail to apply.

## Proposed Solution

1. The child returns typed outcomes (`ready`, `decomposed`, `cancelled`, `blocked`,
   `deferred`, `retryable_error`) plus child IDs and evidence references, in one per-issue
   run record that supersedes `refine-terminal-class` / `refine-broke-down`.
2. One deterministic assessment + repair selector: read the issue once, run
   format/design/AC/decision/proof checks, and choose the next unmet obligation. Replace the
   copied shell/Python predicates and handshake files with a shared implementation that
   emits structured output. Do not replace it with one large LLM prompt.
3. Keep distinct skills for research, wiring, decisions and reconciliation. Their edit
   contracts are useful boundaries.
4. One budget owner for learning proof; risk-conditional go/no-go.

### Legacy terminal-class → outcome mapping (proposed)

| `refine-terminal-class` | `PreparationOutcome` |
|---|---|
| (child `done`, thresholds met) | `ready` |
| `refine-broke-down` present | `decomposed` |
| `infra` | `retryable_error` |
| `rate-limit` exhaustion (`mark_rate_limit_infra`) | `retryable_error` |
| `decision_unresolved`, `proposal_unsound` | `blocked` |
| `spike_inconclusive`, `gate_unmet` | `deferred` |
| `quality` (default, no file) | `blocked` |

## Decomposition

Split into six children, each shippable and revertable on its own. Step letters map to
IDs: A = ENH-3597, B = FEAT-3598, C = ENH-3599, D = ENH-3601, E = ENH-3602, F = ENH-3600.

| Step | Child scope | Depends on |
|---|---|---|
| A | Child writes a typed run record *alongside* the legacy files (additive, no routing change) | — |
| B | `ll-issues next-obligation` selector; adopted inside the child first | — |
| C | Move spike + decision repair routing from autodev into the child | A, B, FEAT-3573 |
| D | Move wire/refine, reconcile/design-remedy, pre-deferral, size-review/atomic and go/no-go routing (**decision_needed**: boundary + go/no-go risk signal) | A, B, C, FEAT-3573 |
| E | Single budget owner for learning-proof evidence (**decision_needed**) | — |
| F | `finalize_done` / ledger driven only by run records; delete remaining handshake files | C, D, FEAT-3573 |

Parent steps coverage: Proposed Solution 1 → A; 2 → B; 3 → constraint on C/D; 4 → E
(budget owner) + D (risk-conditional go/no-go). Implementation Steps 2 → A; 3 → B; 4 → C, D,
F; 5 → acceptance criteria of every child.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- `scripts/little_loops/cli/issues/` (new `next-obligation` subcommand)
- `.claude/workflows/refine-to-ready.js` (gitignored, machine-local) — mirrors `refine-to-ready-issue.yaml`; must stay in sync

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/issue-refinement.yaml`
- `scripts/little_loops/loops/recursive-refine.yaml` — has its own breakdown handling; moving
  size-review/breakdown into the child risks double decomposition
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- `scripts/little_loops/loops/oracles/resolve-decision.yaml`
- `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml`
- `scripts/little_loops/loops/README.md`, `skills/configure/areas.md`, `commands/verify-issues.md`

### Similar Patterns
- `oracles/resolve-decision.yaml` extraction (ENH-3075)

### Tests
- **Behavioral — must pass unchanged before and after**: `scripts/tests/test_spike_verdict_routing.py`,
  `test_autodev_scores_freshness.py`, `test_autodev_decision_gate.py`, `test_check_readiness.py`,
  `test_arm_proposal_revision.py`, `test_format_probe_routing.py`,
  `test_ll_issues_check_gate.py`, `test_ll_issues_check_verify_verdict.py`
- **Structural — expected to be rewritten** (assert state names/topology):
  `test_fsm_topology.py`, `test_builtin_loops.py`, `test_autodev_loop.py`

### Documentation
- `docs/ARCHITECTURE.md` loop section

### Configuration
- N/A

## Related Issues

- **ENH-3590** (add `advise` second-model consult to autodev) touches the same routing
  decision points. Sequence it after D, or land its hook points in the child controller.

## Implementation Steps

1. Land BUG-3571, BUG-3588, BUG-3591, BUG-3592, BUG-3593, FEAT-3573, BUG-3574, ENH-3575 and
   ENH-3576 with real-FSM regression tests
2. Define the typed per-issue outcome/run-record schema
3. Build the shared deterministic assessment + repair selector
4. Move parent repair routing into the child; delete duplicated states and markers
5. Re-run the regression scenarios

## Program Design

### Types

- `PreparationOutcome: Literal["ready", "decomposed", "cancelled", "blocked", "deferred", "retryable_error"]` — the typed per-issue verdict the child returns
- `Obligation: Enum` — `FORMAT`, `DESIGN`, `ACCEPTANCE_CRITERIA`, `DECISION`, `PROOF`, `SCORES`, `NONE`; checked in that order, first unmet wins
- `RunRecord.outcome: PreparationOutcome` — one record per issue run, at `${context.run_dir}/refine-run-record.json`
- `RunRecord.child_ids: list[str]` — IDs created on `decomposed`
- `RunRecord.evidence_refs: list[str]` — paths to the evidence behind the verdict

### Signatures

- `select_next_obligation(config: BRConfig, issue_id: str) -> Obligation` — reads the issue once, runs the format/design/AC/decision/proof checks and returns the first unmet obligation (or `Obligation.NONE`)
- `cmd_next_obligation(config: BRConfig, args: argparse.Namespace) -> int` — `ll-issues next-obligation ID --format json` wrapper; emits the structured selector output that replaces the copied shell/Python predicates
- `write_run_record(run_dir: Path, record: RunRecord) -> Path` — persists the record that `autodev`'s `finalize_done` reads instead of the marker files

### Call Path

`cmd_next_obligation` -> `select_next_obligation` -> `check_format_gaps`

`autodev.yaml:refine_current` -> `refine-to-ready-issue.yaml:resolve_issue` -> `cmd_next_obligation` -> `write_run_record` -> `autodev.yaml:finalize_done`

## Impact

- **Priority**: P3
- **Effort**: Very Large (decomposed into six children)
- **Risk**: High. This is a large refactor of heavily used loops.

## Scope Boundaries

- Blocked until the behavioral fixes (BUG-3571, BUG-3588, BUG-3591, BUG-3592, BUG-3593,
  FEAT-3573, BUG-3574, ENH-3575, ENH-3576) land with real-FSM regression tests (stateful stub
  skills/CLIs asserting outcomes and evidence freshness, not state names). Consolidating
  first would lose the behavior those tests protect. Additive children (A, B, E) do not
  restructure autodev and are not gated on FEAT-3573.
- No state-count target.

## Acceptance Criteria

- [ ] Autodev contains no repair routing that duplicates the child's
- [ ] A single typed per-issue outcome drives the outer ledger
- [ ] The behavioral test set listed under Tests passes unchanged before and after; structural tests are updated to the new topology

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- `autodev.yaml` has 105 states (was recorded as ~87, then 103) — corrected.
- BUG-3572 is cancelled and was never in `blocked_by`; removed from the prerequisite lists in Implementation Steps and Scope Boundaries.
- Still blocking: FEAT-3573 (open). BUG-3571/3574/3575/3576/3588/3591/3592/3593 are done. `blocks` backlinks verified on all blockers.
- 2026-09-25 review: Call Path cited `autodev.yaml:run_refine` (a `/ll:refine-issue --gap-analysis` slash command) — the child delegation is `refine_current`; `cmd_refine_status` is a reporting command and was removed from the selector path; `Obligation` type added; the AC's "regression scenarios listed in EPIC-3565" did not exist and was replaced by the explicit behavioral test set.

## Status

**Done (decomposed)** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:issue-size-review` - 2026-09-25T18:56:54 - `c01a94cc-9274-4e85-a359-4a84d4780ecf.jsonl`
- `/ll:format-issue` - 2026-09-25T18:01:38 - `e22a5582-f640-4248-a4ce-34068f335196.jsonl`
- `/ll:verify-issues` - 2026-09-25T15:27:34 - `bc279096-6a89-4a82-b7c2-8e6f11cc30f5.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:32 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-09-25
- **Decomposed into**: ENH-3597, FEAT-3598, ENH-3599, ENH-3601, ENH-3602, ENH-3600

Work for ENH-3577 is now carried by its child issues; this parent was closed after a manual review/decomposition session.
