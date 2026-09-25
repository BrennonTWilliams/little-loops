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
- ENH-3602
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

### Go/no-go trigger (resolves the Open Question)

Keep today's trigger unchanged: go/no-go runs only for `deferred_reason: oversized_atomic`.
The trigger is deterministic, based on the `oversized_atomic` reason code written in the
size-review path. Moving it into `prepare-issue` unchanged keeps "behavioral test set
passes unchanged" achievable. Widening it with a risk signal (`score_complexity`,
`score_change_surface`, `outcome_confidence` band, file count) changes behavior and
belongs in a separate follow-up issue, not in this migration. The epic's "risk-conditional
go/no-go" wording is satisfied by this documented predicate.

## Program Design

### Types

- No new Python types. Uses `RunRecord` and `RunRecordWriter` from ENH-3597 with `writer = "prepare-issue"`, and `ObligationResult` from FEAT-3598.

### Signatures

- `write_run_record(run_dir: Path, record: RunRecord) -> Path` — (ENH-3597) called by every `prepare-issue` terminal with `writer="prepare-issue"`
- `read_run_record(run_dir: Path, writer: RunRecordWriter, issue_id: str) -> RunRecord | None` — (ENH-3597) `prepare-issue` reads the child's record after its `loop: refine-to-ready-issue` state; autodev reads the wrapper's record
- `select_next_obligation(config: BRConfig, issue_id: str) -> ObligationResult` — (FEAT-3598) replaces `triage_outcome_failure`'s fan-out predicates inside the wrapper

### Loop shape (`prepare-issue.yaml`)

- `loop: refine-to-ready-issue` with `context_passthrough: true`, so the wrapper shares
  autodev's `run_dir` and the `spike-runs-<ID>` / `autodev-repair-cycle-count.txt` counters.
- The second-pass repair states move here from autodev, keeping their names where
  possible: wire/refine, reconcile/design remedy, pre-deferral remedy, size-review/atomic,
  go/no-go. The five rescoring triplets collapse into one shared rescoring path that keeps
  BUG-3588's freshness rules.
- **Rate limits**: `loop:` call states cannot use `with_rate_limit_handling` (BUG-3390,
  `autodev.yaml:527-532`). Skill states inside the wrapper use the fragment. On
  exhaustion they route to a wrapper terminal that writes `outcome: retryable_error`.
  They never route to autodev's `finalize_rate_limited`, which does not exist in the
  wrapper. Autodev's `loop: prepare-issue` state keeps the BUG-2611 rule (no `on_no`) and
  routes `on_error` to `skip_inflight_infra`.
- Autodev routes only on the wrapper's `RunRecord.outcome`. `ready` → fail-closed proof
  gate (BUG-3603) → `implement_current`.

### Call Path

`autodev.yaml:refine_current` -> `prepare-issue.yaml` -> `refine-to-ready-issue.yaml:classify_terminal` -> `write_run_record`

`prepare-issue.yaml` (second-pass dispatch) -> `select_next_obligation` -> `write_run_record` -> `autodev.yaml:check_proof_defer_or_implement` -> `cmd_check_gate`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Decision Rules**: N/A — no new decision logic. The go/no-go trigger stays the existing `deferred_reason: oversized_atomic` predicate; moving states must be behavior-preserving.
- **Constraint on the wrapper's `outcome` vocabulary**: autodev must be able to distinguish, from the wrapper's record alone, at least `ready`, quality failure, infra failure (including rate-limit exhaustion as `retryable_error`) and children-enqueued (breakdown); today these are encoded in sentinel files and terminal names (`refine-terminal-class`, `copy_broke_down`/`enqueue_children`). The record's enum is owned by ENH-3597 — this issue must not invent extra outcome values.
- **Constraint on ordering with BUG-3603**: the fail-closed proof gate before `implement_current` (`check_proof_gate_before_implement` / `check_proof_defer_or_implement`) remains in autodev and is downstream of the wrapper's `ready` outcome; no `prepare-issue` terminal may route into `implement_current`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`
- new `scripts/little_loops/loops/prepare-issue.yaml`
- `scripts/little_loops/loops/README.md` and root `README.md` loop count (mirror to `scripts/README.md`)
- `docs/ARCHITECTURE.md` loop section (new wrapper)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/recursive-refine.yaml`, `issue-refinement.yaml`, `auto-refine-and-implement.yaml` — unchanged; they keep calling `refine-to-ready-issue` directly (Option B)

### Tests
- Behavioral, must pass unchanged: `test_autodev_scores_freshness.py`, `test_check_readiness.py`,
  `test_arm_proposal_revision.py`, `test_format_probe_routing.py`, `test_ll_issues_check_gate.py`
- Structural, rewrite: `test_fsm_topology.py`, `test_builtin_loops.py` (stem set at lines 304-305), `test_autodev_loop.py`
- New: `prepare-issue` rate-limit exhaustion writes `retryable_error` and autodev ledgers it
- New: a `ready` outcome never hits `LEARNING_GATE_BLOCKED` for a reason `assess_proof` (ENH-3602) reports (controller-level AC, moved here from ENH-3602)
- BUG-3603's invariant test (no fail-open edge into `implement_current`) still passes

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Current size (measured, `autodev.yaml`)**: 105 states, `max_steps: 500`, 3190 lines; `refine-to-ready-issue.yaml` has 67 states, `max_steps: 90`. `prepare-issue.yaml` does not exist yet. Every state named in Current Behavior exists today.
- **Reachable set is wider than the listed ~45 states.** Everything reachable from `triage_outcome_failure` before `implement_current` is 94 states in total, because the fan-out also reaches the spike states (`check_spike_needed`, `run_spike`, `route_spike_verdict`, `*_spike`), the decide states (`resolve_decision_direct`, `decide_current`, `*_decide`) and the dequeue-time gates. Those belong to ENH-3599, not this issue. The ~45 estimate only holds if ENH-3599 lands first and moves the spike/decide subgraph into `refine-to-ready-issue`; the `blocked_by` edge is load-bearing for scope, not just ordering.
- **Rescoring triplets present today**: `clear_scores_before_{wire,reconcile,atomic}` / `rerun_confidence_after_{wire,reconcile,atomic_remediation}` / `check_scores_present_{wire,reconcile,atomic}` (the spike and decide triplets also exist and are ENH-3599's). `count_repair_cycle_*` has six variants: `refine`, `wire`, `spike`, `size_review`, `refine_for_design`, `reconcile`.
- **Sub-loop wiring invariants** (`fsm/executor.py`): a `loop:` state with `context_passthrough` inherits the parent context, and `run_dir` is re-injected into the child via `setdefault` (executor lines ~1132-1151), so a `prepare-issue` wrapper and its `refine-to-ready-issue` child share one `run_dir`. Captures from the child are merged back into the parent when `context_passthrough` or `with:` is set (~line 1315). Shared counters (`spike-runs-<ID>`, `autodev-repair-cycle-count.txt`) therefore keep working across the extra nesting level.
- **Existing exit-class contract that the wrapper must not regress**: `refine-to-ready-issue`'s `classify_terminal` writes `refine-terminal-class`; autodev's `skip_inflight` reads it to split quality failures (`refine_failed`) from infra kills (`skip_inflight_infra`, `refine_failed_infra`). Autodev's `refine_current` routes `on_success` to `count_repair_cycle_refine`, `on_failure` to `skip_inflight`, `on_error` to `skip_inflight_infra`, with no `on_no` (BUG-2611: an explicit `on_no` shadows `on_failure`). The new `loop: prepare-issue` state has to preserve that shape until the run record replaces the sentinel.
- **Contested convention — rate-limit fragment on `loop:` states**: `autodev.yaml` (BUG-3390 comment on `refine_current`) says `fragment: with_rate_limit_handling` is inert on a `loop:` call state, whereas `recursive-refine.yaml` `run_refine` still applies that fragment to a `loop:` state. The wrapper must follow the autodev reading (no fragment on the `loop:` state; rate-limit handling only on skill states inside the wrapper), which is what Program Design already says.
- **Run-record dependency state**: ENH-3597 (`RunRecord`/`write_run_record`/`read_run_record`) and FEAT-3598 (`select_next_obligation`) have not landed; no `RunRecord` symbol exists in `scripts/little_loops` yet (the `_LoopRunRecord` in `cli/logs.py` is unrelated fleet-review aggregation). Signatures in Program Design are therefore forward references to sibling issues and must be re-checked against their final shapes before implementation.
- **Structural test hook**: `test_builtin_loops.py` asserts `expected == actual` over the stem set of `BUILTIN_LOOPS_DIR.glob("*.yaml")` (around lines 295-306), so adding `prepare-issue` fails that test until the stem is listed. Behavioral test files named in Tests all exist under `scripts/tests/`.
- **Mirror gates**: a new loop YAML bumps the loop count in root `README.md` (mirrored to `scripts/README.md`) and `scripts/little_loops/loops/README.md`; skills/README edits also trip the `ll-adapt` mirror gates.

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Large - removes the second-pass repair fan-out (~45 states)
- **Risk**: High - rewrites routing; Option A also changes other callers
- **Breaking Change**: No for Options B/C; possible for callers under Option A

## Open Questions

- ~~Which risk signal widens go/no-go?~~ Resolved above: keep the `oversized_atomic`-only trigger; widening is a follow-up.
- ENH-3590 (advise consult) lands after this issue and targets `prepare-issue.yaml`.

## Scope Boundaries

- Keep distinct skills for research, wiring, decisions and reconciliation; do not merge them into one prompt (ENH-3577).
- Callers other than autodev are untouched.
- No change to the go/no-go trigger condition.
- **Size**: about 45 states move, plus a new loop, at High risk. Run
  `/ll:issue-size-review` before implementation. A natural split is D1 (wrapper +
  wire/refine + reconcile/design remedy + shared rescoring path) and D2 (size-review/atomic
  + go/no-go + pre-deferral remedy).

## Acceptance Criteria

- [x] Boundary option selected and recorded (Option B, 2026-09-25)
- [ ] `autodev.yaml` has no wire/reconcile/design-remedy/pre-deferral/size-review/go-no-go states
- [ ] The five rescoring triplets are gone from autodev; `prepare-issue` has one shared rescoring path with BUG-3588 freshness rules
- [ ] Go/no-go trigger is the documented, deterministic `oversized_atomic` predicate, unchanged
- [ ] `prepare-issue` writes a `writer: prepare-issue` run record on every terminal, including rate-limit exhaustion (`retryable_error`)
- [ ] A `ready` preparation outcome never hits `LEARNING_GATE_BLOCKED` for a reason `assess_proof` could have detected (moved from ENH-3602)
- [ ] Behavioral test set passes unchanged

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-25T19:42:32 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:decide-issue` - 2026-09-25T19:03:07 - `26d04b78-61d2-44f6-aa98-56c6d251288d.jsonl`
