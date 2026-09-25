---
id: ENH-3601
type: ENH
title: Move autodev second-pass preparation routing into a preparation controller
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:59Z'
decision_needed: false
blocked_by:
- ENH-3597
- FEAT-3598
- ENH-3599
- FEAT-3573
blocks:
- ENH-3600
relates_to:
- ENH-3602
- ENH-3590
- ENH-3577
parent: EPIC-3565
---

# ENH-3601: Move autodev second-pass preparation routing into a preparation controller

## Summary

Move autodev's remaining second-pass preparation routing — wire/refine, reconcile and
design remedy, pre-deferral remedy, size-review/atomic remediation and go/no-go — out of the
outer loop. Step D of the ENH-3577 decomposition. **Needs a decision on where the
preparation boundary sits** before implementation.

## Current Behavior

After `refine_current` returns, `check_passed` fails into `triage_outcome_failure`, which fans
out (all before `implement_current`) into:

- **wire/refine**: `check_missing_artifacts`, `run_wire`, `run_refine`, `count_repair_cycle_wire`, rescoring triplet `*_wire`
- **reconcile/design**: `check_reconcile_needed`, `reconcile_current`, `refine_for_design`,
  `check_atomic_design_remedy`, `dispatch_design_remedy`, rescoring triplet `*_reconcile`
- **pre-deferral remedy**: `check_pre_deferral_remedy`, `dispatch_pre_deferral_remedy`
  (markers `autodev-pre-deferral-remedy.txt`, `autodev-pre-deferral-remedy-fired`)
- **size-review/atomic**: `detect_children`, `size_review_snap`, `check_broke_down`,
  `snap_and_size_review`, `run_size_review`, `enqueue_or_skip`, `check_size_review_ran_this_pass`,
  `check_guard2_verdict`, `check_guard2_score_fallback`, `check_readiness_for_atomic_remediation`,
  `remediate_oversized_atomic`, `regate_after_atomic_remediation`, rescoring triplet `*_atomic`
- **go/no-go**: `check_go_no_go_eligible`, `run_go_no_go`, `check_go_no_go_waiver`, `reopen_waived`
  (only for `deferred_reason: oversized_atomic`)
- shared: `recheck_scores`, `recheck_after_size_review`, `count_repair_cycle_*`,
  `autodev-repair-cycle-count.txt`, `autodev-design-*`, `autodev-contradiction-reconcile-*`,
  `autodev-rescore-retry-*`

## Expected Behavior

Autodev dispatches to one preparation controller and routes only on its `RunRecord.outcome`.
No wire/reconcile/size-review/go-no-go logic remains in `autodev.yaml`.

## Proposed Solution

Pick one boundary:

### Option A: Child absorbs everything

`refine-to-ready-issue` takes over all second-pass repairs and only exits with a terminal
`PreparationOutcome`. Other callers (`recursive-refine`, `issue-refinement`,
`auto-refine-and-implement`) opt out of size-review/breakdown via a context flag (e.g.
`prepare_mode: refine_only`) to avoid double decomposition with `recursive-refine`'s own
breakdown handling. Fewest loops; child grows substantially; every caller's behavior is at
risk.

### Option B: New wrapper controller

> **Selected:** Option B — matches the existing `loop:` wrapper pattern, isolates blast radius, and satisfies ENH-3577's "autodev owns only the queue" goal.

New `prepare-issue` loop wraps `refine-to-ready-issue` and owns the second-pass repairs
(size-review/atomic, go/no-go, pre-deferral remedy, design remedy). Autodev calls
`prepare-issue`; other callers keep calling `refine-to-ready-issue` unchanged. Isolates blast
radius; adds one loop and a second run-record writer.

### Option C: Keep second pass in autodev, collapse it

Leave second-pass repair in autodev but replace the fan-out with one dispatch on
`ll-issues next-obligation` plus a single shared rescoring sub-loop (replacing the five
rescoring triplets). Smallest change; does not satisfy ENH-3577's "autodev owns only the
queue" goal.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-25.

**Selected**: Option B — New wrapper controller

**Reasoning**: Wrapping a child loop via `loop:` + `context_passthrough` is already the standard shape (`autodev.yaml:533-548`, `recursive-refine.yaml:237-241`, multi-level nesting in `scan-and-implement` → `autodev` → `refine-to-ready-issue`), and other callers stay unchanged. Option A grows an already budget-tuned 68-state child (`max_steps` tuning, BUG-3593) and risks double decomposition with `recursive-refine`; Option C leaves ~103 states in autodev and fails the epic's goal and two acceptance criteria.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 2/3 | 1/3 | 2/3 | 0/3 | 5/12 |
| Option B | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |
| Option C | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- Rejected A (child absorbs): `no_recursion` flag precedent (`recursive-refine.yaml:45,83`) gates a caller's own states, not a child's; autodev ledgers (`autodev-repair-cycle-count.txt`, `spike-runs-<ID>`) would have to move.
- Selected B (wrapper): `loop:` states lack rate-limit handling (`autodev.yaml:527-532`), so the wrapper needs the RunRecord (ENH-3597) rather than sentinel files; `test_builtin_loops.py:304-305` stem set and README loop counts need updating.
- Rejected C (collapse in place): contradicts Expected Behavior and acceptance criteria; still blocked on FEAT-3598 `next-obligation`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (Option A) or new `scripts/little_loops/loops/prepare-issue.yaml` (Option B)
- `.claude/workflows/refine-to-ready.js` (gitignored, machine-local; Option A)
- `scripts/little_loops/loops/README.md` (Option B, loop count)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/recursive-refine.yaml`, `issue-refinement.yaml`, `auto-refine-and-implement.yaml`

### Tests
- Behavioral, must pass unchanged: `test_autodev_scores_freshness.py`, `test_check_readiness.py`,
  `test_arm_proposal_revision.py`, `test_format_probe_routing.py`, `test_ll_issues_check_gate.py`
- Structural, rewrite: `test_fsm_topology.py`, `test_builtin_loops.py`, `test_autodev_loop.py`
- New: recursive-refine does not double-decompose (Option A)

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Large - removes the second-pass repair fan-out (~45 states)
- **Risk**: High - rewrites routing; Option A also changes other callers
- **Breaking Change**: No for Options B/C; possible for callers under Option A

## Open Questions

- Go/no-go is "risk-conditional" per ENH-3577, but no risk signal is defined. Today it runs
  only for `oversized_atomic` deferrals. Which signal widens or narrows it
  (`score_complexity`, `score_change_surface`, `outcome_confidence` band, file count)?
- Coordinate with ENH-3590 (advise consult step), which hooks into the same decision points.

## Scope Boundaries

- Implementation waits for the boundary option to be selected (`/ll:decide-issue`).
- Program Design is written after the decision; it depends on the chosen option.
- Keep distinct skills for research, wiring, decisions and reconciliation; do not merge them into one prompt (ENH-3577).

## Acceptance Criteria

- [ ] Boundary option selected and recorded
- [ ] `autodev.yaml` has no wire/reconcile/design-remedy/pre-deferral/size-review/go-no-go states
- [ ] The five rescoring triplets are gone from autodev
- [ ] Go/no-go trigger is a documented, deterministic risk predicate
- [ ] Behavioral test set passes unchanged

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:decide-issue` - 2026-09-25T19:03:07 - `26d04b78-61d2-44f6-aa98-56c6d251288d.jsonl`
