---
id: ENH-2364
title: 'refine-to-ready-issue: retire or downscope the restore_best snapshot guard'
type: ENH
priority: P3
status: open
captured_at: '2026-06-28T04:24:39Z'
discovered_date: '2026-06-28'
discovered_by: conversation
decision_needed: false
relates_to:
- ENH-2037
- ENH-2363
labels:
- loops
- issue-management
- refine-to-ready-issue
- cleanup
confidence_score: 100
outcome_confidence: 95
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2364: Retire or downscope `restore_best` in refine-to-ready-issue

## Summary

`restore_best` (added by ENH-2037) and its companion `snapshot_issue` state in
`scripts/little_loops/loops/refine-to-ready-issue.yaml` exist to undo regressions
caused by destructive `--full-rewrite` refine passes — it copies the
highest-composite-scoring `iter-N/` snapshot back over the issue file before
the loop declares `done`. After ENH-2363, the loop no longer uses
`--full-rewrite`: the first pass is plain `--auto` and retries are additive
`--auto --gap-analysis` (never removes content). With additive retries the
"late rewrite regresses a better earlier iteration" failure mode the guard was
built for is largely gone, so the guard is now mostly dead weight.

## Background

ENH-2037 added `restore_best` with the explicit rationale (loop comment, lines
~287–292): *"Prevents a late --full-rewrite regression from persisting over a
better prior iteration."* That premise no longer holds once refines are additive.
`snapshot_issue` still writes per-iteration `iter-N/` copies under
`${context.run_dir}/`, and `restore_best` still scans them and picks a winner by
composite score (`confidence_score * 1000 + outcome_confidence`).

## Current Behavior

- `snapshot_issue` — copies the issue file to `${run_dir}/iter-N/<ID>.md` after
  every refine.
- `restore_best` — on `check_outcome` `on_yes`, compares the live issue file
  against all `iter-N/` snapshots and restores the highest-scoring one before
  `done`.
- Because retries are now additive, the live file at termination is normally the
  most-complete version, so `restore_best` almost always logs "current file is
  already best-scoring" and changes nothing.

## Expected Behavior

After this change, the loop terminates on the live issue file — already the
most-complete version under additive refines — without a silent `restore_best`
overwrite. Either `restore_best` is removed entirely (routing `check_outcome.on_yes`
to `done`), or it is converted to a warning-only diagnostic that logs when the live
file is *not* the best-scoring snapshot instead of overwriting it. Whatever
snapshotting remains is reconciled with the `artifact_versioning` declaration, no
state dead-ends, and `ll-loop validate refine-to-ready-issue` passes.

## Proposed Solution

Evaluate and pick one:

1. **Retire** — remove `restore_best` (route `check_outcome.on_yes` straight to
   `done`) and remove `snapshot_issue` (route `refine_issue`/`refine_followup`
   `next:` directly to `check_wire_done`). Drop `artifact_versioning: true` if no
   other state needs it. Simplest; relies on additive refine being non-regressive.

> **Selected:** Retire — removes dead-weight compensating states now that upstream additive refines (ENH-2363) are non-regressive.

2. **Downscope** — keep `snapshot_issue` for debugging/audit trails (cheap, useful
   when diagnosing a run) but remove the `restore_best` restore step, OR keep
   `restore_best` only as a no-op/diagnostic logger that warns when the live file
   is *not* the best snapshot rather than silently overwriting.

Recommendation: start with option 2 (keep snapshots for forensics, drop the
restore mutation), then retire snapshots in a later pass if they prove unused.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-28.

**Selected**: Option 1 — Retire

**Reasoning**: The codebase research confirms `restore_best` and `snapshot_issue` are the only two states reading/writing `iter-N/` paths and their routing is fully isolated — rewiring maps cleanly to 3 route changes and 6 specific test assertions. The active `.ll/decisions.yaml` rule ("compensating/rollback states signal upstream logic issues, not downstream patches") directly endorses retirement now that ENH-2363 fixed the upstream cause. Option 2 retains overhead that the research shows almost never mutates anything, adding code paths without measurable benefit.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Retire | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Downscope | 2/3 | 2/3 | 2/3 | 3/3 | 9/12 |

**Key evidence**:
- **Retire**: Aligns with `.ll/decisions.yaml` compensating-state principle; 6 specific test assertions to update (all directly about removed states); routing changes fully mapped in codebase research; `artifact_versioning: true` flag is currently inert for `issue-management` category loops (MR-5 early-returns for non-`harness` loops).
- **Downscope**: Lower risk (snapshots preserved, no mutation), but retains acknowledged dead weight and requires new warning-path test coverage with unclear payoff given additive refines are the new policy.

## Acceptance Criteria

- `restore_best`'s silent overwrite is removed (or converted to a warning-only
  diagnostic).
- If snapshots are removed, `snapshot_issue` and any `iter-N/` references are
  cleaned up and routing is rewired so no state dead-ends.
- `ll-loop validate refine-to-ready-issue` passes.
- The MR-5 / `artifact_versioning` declaration is reconciled with whatever
  snapshotting remains (remove the flag if snapshots are dropped).

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — remove `snapshot_issue` and
  `restore_best` states; rewire `check_outcome.on_yes` → `done`; rewire `refine_issue` /
  `refine_followup` `next: snapshot_issue` → `check_wire_done`; drop `artifact_versioning: true`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — invokes `refine-to-ready-issue` as a sub-loop (no change needed; ENH-2364 changes are internal to the sub-loop)
- `scripts/little_loops/loops/recursive-refine.yaml` — invokes `refine-to-ready-issue` as a sub-loop (no change needed)
- `scripts/little_loops/loops/issue-refinement.yaml` — invokes `refine-to-ready-issue` (no change needed)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — invokes `refine-to-ready-issue` (no change needed)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — invokes `refine-to-ready-issue` (no change needed)
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` — invokes `refine-to-ready-issue` (no change needed)

### Tests

Known breaking tests in `scripts/tests/test_builtin_loops.py` (`TestRefineToReadyIssueSubLoop`):

- `test_check_outcome_on_yes_routes_to_restore_best` (line 917) — **UPDATE**: rename and change assert from `"restore_best"` to `"done"`; update docstring to drop ENH-2037 rationale
- `test_restore_best_state_exists` (line 1162) — **DELETE** (state removed)
- `test_restore_best_is_shell` (line 1169) — **DELETE** (state removed)
- `test_restore_best_routes_to_done` (line 1176) — **DELETE** (state removed)
- `test_restore_best_shell_action_restores_higher_scoring_snapshot` (line 1183) — **DELETE** (state removed)
- `test_restore_best_no_op_when_current_is_already_best` (line 1238) — **DELETE** (state removed)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py:993` — `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` loads and validates `refine-to-ready-issue.yaml`; will stay green as long as YAML remains structurally valid — **VERIFY** (no code change needed)
- `TestValidatorWarningBudget` ratchet in `test_builtin_loops.py:7662` — tracks `artifact-versioning` category warnings; after removing `snapshot_issue` the MR-5 trigger condition is no longer met, so the flag removal is safe — **VERIFY** by running `ll-loop validate refine-to-ready-issue` after edit (no code change expected)

New tests to write in `TestRefineToReadyIssueSubLoop` (`test_builtin_loops.py`):
- `test_check_outcome_on_yes_routes_to_done` — the updated version of the line-917 test; `assert state.get("on_yes") == "done"`
- `test_refine_issue_next_is_check_wire_done` — new: `assert data["states"]["refine_issue"]["next"] == "check_wire_done"`
- `test_refine_followup_next_is_check_wire_done` — new: same pattern for `refine_followup`
- `test_restore_best_state_absent` — new guard: `assert "restore_best" not in data["states"]` (follow pattern of `test_verify_issue_state_absent` at line 953)
- `test_snapshot_issue_state_absent` — new guard: `assert "snapshot_issue" not in data["states"]`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — add `### Removed` entry for `restore_best`, `snapshot_issue`, and `artifact_versioning: true` from `refine-to-ready-issue` in the release that ships ENH-2364 (the feature was announced at `## [1.120.0] - 2026-06-09`, line 358)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — no change needed (MR-5 docs reference `artifact_versioning` generically, not specific to this loop)
- `docs/reference/API.md` — no change needed (documents the `FSMLoop` dataclass field generally)
- `scripts/little_loops/fsm/schema.py` / `validation.py` — no change needed (general FSM infrastructure; removing the flag just causes it to deserialize as `False` default)

## Scope Boundaries

- **In scope**: `restore_best` / `snapshot_issue` states, their routing, and the
  `artifact_versioning` flag in `refine-to-ready-issue.yaml`.
- **Out of scope**: Any change to the refine-mode policy itself (handled by ENH-2363).

## Impact

- **Priority**: P3 — cleanup; removes a now-redundant guard and reduces per-run
  filesystem churn. Not blocking.
- **Effort**: Small — localized to one loop YAML plus test adjustments.
- **Risk**: Low–Medium — must confirm additive refines really are non-regressive
  in practice before removing the safety net; option 2 (warning-only) de-risks
  the transition.
- **Breaking Change**: No.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Exact anchors in `scripts/little_loops/loops/refine-to-ready-issue.yaml`

- **`category: issue-management`** (line 3) — **not `harness`**. This is the key
  finding for the `artifact_versioning` decision (see below).
- **`artifact_versioning: true`** (line 15).
- **`snapshot_issue`** state — lines 103–120. `action_type: shell`; writes
  `${context.run_dir}/iter-N/<ID>.md` via a `.iter_counter` sentinel; `next: check_wire_done`,
  `on_error: check_wire_done` (non-fatal in both directions).
- **`check_outcome`** state — lines 186–216. `on_yes: restore_best` (line 214),
  `on_no: check_decision_needed` (line 215), `on_error: diagnose`.
- **`restore_best`** state — lines 304–344. `action_type: shell`; `next: done` (line 344);
  **no `on_error` key** (a shell failure here has no explicit guard). Composite score =
  `confidence_score * 1000 + outcome_confidence` (lines 323, 331).

### Routing into the affected states

- `refine_issue` (`next: snapshot_issue`, line 90) and `refine_followup`
  (`next: snapshot_issue`, line 100) are the **only** states routing into `snapshot_issue`.
  Both `on_error` route to `diagnose`, not around the snapshot.
- `restore_best` is reachable **only** via `check_outcome.on_yes`. The fallback paths
  `check_scores_from_file` (`on_yes: done`, line 288), `check_decision_needed`, and
  `check_missing_artifacts` already route straight to `done`, bypassing `restore_best`.
- All `${context.run_dir}/iter-*` references live in exactly two states: `snapshot_issue`
  (writes) and `restore_best` (reads). No other state depends on `iter-N/` or `.iter_counter`.

### MR-5 / `artifact_versioning` reconciliation (sharpens AC #4)

`_validate_artifact_overwrite` in `scripts/little_loops/fsm/validation.py:1452` (rule MR-5)
**early-returns when `category not in ("harness",)`** (line 1466). Because this loop is
`category: issue-management`, **MR-5 never fires for it regardless of the
`artifact_versioning` flag** — the flag at line 15 is currently inert/defensive. It can be
removed with no validation impact. (Even within `harness` loops, MR-5 only flags writers to
`${context.run_dir}/...` flat paths in a self-reachable cycle; the only such writer here is
`snapshot_issue`, and the refine states write to the issue file via the `ll:refine-issue`
skill, not a `run_dir` path — so MR-5 would not catch them anyway.)

### Test impact — `scripts/tests/test_builtin_loops.py`

Tests that **must be updated** if `restore_best` is retired (Option 1) and
`check_outcome.on_yes` is rewired to `done`:

- `test_check_outcome_on_yes_routes_to_restore_best` (line 917) — asserts
  `check_outcome.on_yes == "restore_best"`. Becomes false; update to assert `done` (or the
  warning-only diagnostic state under Option 2).
- `test_restore_best_state_exists` (line 1162)
- `test_restore_best_is_shell` (line 1169)
- `test_restore_best_routes_to_done` (line 1176)
- `test_restore_best_shell_action_restores_higher_scoring_snapshot` (line 1183)
- `test_restore_best_no_op_when_current_is_already_best` (line 1238)

Tests that **stay green**:

- There is **no test referencing `snapshot_issue` by name** and **no test asserting
  `refine_issue`/`refine_followup` `next: snapshot_issue`** — removing `snapshot_issue` (or
  keeping it for forensics) breaks no existing assertion directly.
- `test_artifact_versioning_declared` (line 7948) belongs to `TestOpenSCADModelGeneratorLoop`
  (a `harness`-category loop), **not** refine-to-ready-issue — removing `artifact_versioning`
  here does not break it.

### Implications for the two options

- **Option 1 (Retire)** is mechanically clean: rewire `check_outcome.on_yes → done`,
  rewire `refine_issue`/`refine_followup` `next: snapshot_issue → check_wire_done`, delete
  both states, drop `artifact_versioning: true`, and update the 6 `restore_best` tests above.
- **Option 2 (Downscope)** keeps `snapshot_issue` (forensics) and converts `restore_best` to
  a warning-only logger (drop the `cp` overwrite, keep the score comparison + log). Fewer
  routing changes; `test_restore_best_no_op_*` may survive while the two
  `restore_best_..._restores_*` assertions need updating to expect no overwrite.

### Additional references (update / no-op on implementation)

- **`.ll/decisions.yaml` (≈lines 2681–2685)** — an existing decision rule notes that
  compensating/rollback states signal a need to fix the *upstream* logic rather than patch
  downstream; this directly supports retiring `restore_best`. Cite it in the implementation
  rationale.
- **`CHANGELOG.md` (line 358)** — the `restore_best` feature was announced; the
  retire/downscope change needs a corresponding CHANGELOG entry (promote to a concrete
  `## [X.Y.Z]` section, not `[Unreleased]`).
- **`docs/guides/LOOPS_REFERENCE.md:2133`** — references a `restore_best` state, but in the
  **`rlhf-animated-svg`** flow, **not** refine-to-ready-issue. Out of scope; do not edit it.
  (`restore_best` is a reused pattern name across loops — `rlhf-animated-svg.yaml`,
  proposed `vega-viz` in ENH-2045 — so scope edits to this loop's test class
  `TestRefineToReadyIssueSubLoop` only.)
- **`test_check_readiness_on_yes_routes_to_check_outcome`** (`test_builtin_loops.py:896`)
  exercises the path *leading to* `restore_best` but asserts only `check_readiness → check_outcome`;
  it stays green under either option.

---
**Open** | Created: 2026-06-28 | Priority: P3


## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Edit `refine-to-ready-issue.yaml` — rewire `check_outcome.on_yes` → `done`; rewire `refine_issue.next` and `refine_followup.next` → `check_wire_done`; delete `snapshot_issue` state; delete `restore_best` state; remove `artifact_versioning: true` top-level key.
2. Update `test_builtin_loops.py` — rename `test_check_outcome_on_yes_routes_to_restore_best` (line 917) and change its assert to `"done"`; delete the 5 `restore_best`-specific tests (lines 1162, 1169, 1176, 1183, 1238).
3. Write 5 new tests in `TestRefineToReadyIssueSubLoop` — `test_check_outcome_on_yes_routes_to_done`, `test_refine_issue_next_is_check_wire_done`, `test_refine_followup_next_is_check_wire_done`, `test_restore_best_state_absent`, `test_snapshot_issue_state_absent`.
4. Run `ll-loop validate refine-to-ready-issue` — confirm no MR-5 / artifact-versioning warning fires; confirm `TestValidatorWarningBudget` ratchet passes.
5. Add `### Removed` entry to `CHANGELOG.md` in the release that ships this change.

## Session Log
- `/ll:confidence-check` - 2026-06-28T06:00:00Z - `703279fb-8dcb-48bd-aeb4-d68977d78282.jsonl`
- `/ll:wire-issue` - 2026-06-28T05:16:42 - `d85817cb-a77f-47c1-b630-287fcad6d515.jsonl`
- `/ll:decide-issue` - 2026-06-28T05:03:07 - `df40cbc8-6274-462a-a779-6eadb47810e2.jsonl`
- `/ll:refine-issue` - 2026-06-28T04:59:39 - `29b8a0e9-fe28-436c-b9ac-cfb3352fe1ca.jsonl`
- `/ll:format-issue` - 2026-06-28T04:54:47 - `a7b072a9-c67d-4012-848b-dac474792170.jsonl`
