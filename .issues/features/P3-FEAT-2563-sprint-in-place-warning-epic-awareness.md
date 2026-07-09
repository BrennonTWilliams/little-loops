---
id: FEAT-2563
title: per-EPIC integration branch — cli/sprint/run.py in-place warning epic-awareness
type: FEAT
priority: P3
status: open
captured_at: '2026-07-09T00:00:00Z'
discovered_date: 2026-07-09
discovered_by: confidence-check-decomposition
labels:
- parallel
- sprint
- epics
- git
parent: EPIC-2451
relates_to:
- EPIC-2451
- FEAT-2447
- FEAT-2448
- FEAT-2449
blocked_by: []
unblocks:
- FEAT-2450
decision_needed: false
---

# FEAT-2563: per-EPIC integration branch — cli/sprint/run.py in-place warning epic-awareness

## Summary

Unit C extracted from FEAT-2449 (decomposed via `/ll:confidence-check` on
2026-07-09). Makes the sprint runner's single-issue / contention-subwave in-place
warning **epic-branches-aware**: today it warns only when feature-branch mode is
active but the wave runs in-place; the same caveat applies to epic-branch mode.

This unit is **fully independent** — it reads config/args flags only
(`config.parallel.use_feature_branches`, `args.feature_branches`) and needs no
issue→EPIC mapping, so it does not depend on FEAT-2561 and can land in parallel
with any sibling. It is the smallest, lowest-risk child of the split.

## Parent Issue

Decomposed from FEAT-2449 on 2026-07-09 (was Scope item #4). EPIC-2451 is the
parent EPIC and remains the coordination container.

## Scope

1. **`effective_epic_branches` in-place warning**
   (`scripts/little_loops/cli/sprint/run.py`, in-place / contention-subwave block
   at lines ~517, 519–529) — add a parallel `effective_epic_branches` check with
   the **identical shape** to the existing `effective_feature_branches` resolution
   (`args.epic_branches if not None else config.parallel.epic_branches.enabled`),
   and **append** the epic-branch caveat to the existing warning message rather
   than replacing it.

   Critical constraint: the existing warning contains the substring
   `"feature-branch mode does not apply"` which `test_cli_sprint.py`
   `TestFeatureBranchInPlaceWarning` asserts on (per FEAT-2339 Decision
   Rationale #4). The epic variant must **preserve** that substring — append a
   new clause (e.g. `"; epic-branch mode likewise does not apply to in-place
   sub-waves"`) to the same `logger.warning(...)`, or emit a second guarded
   warning, without altering the original substring.

   > **Note**: `args.epic_branches` may not exist yet as a CLI flag — that flag
   > is FEAT-2450's scope. Resolve defensively with
   > `getattr(args, "epic_branches", None)` (mirrors the existing
   > `getattr(args, "feature_branches", None)` at `run.py:518`), falling back to
   > `config.parallel.epic_branches.enabled`. This keeps the warning correct
   > before and after FEAT-2450 wires the flag.

2. **Tests** —
   - `scripts/tests/test_cli_sprint.py::TestFeatureBranchInPlaceWarning`
     (`:732-879`) — add an `epic_branches` counterpart. Reuse the existing
     `mock_logger.warning.side_effect = lambda msg: warning_calls.append(msg)`
     capture pattern. The new test must:
     - assert the epic caveat fires when epic mode is effective + wave is in-place
     - **preserve** the existing `"feature-branch mode does not apply"` substring
       assertions (`:841, 851, 861, 870, 878`) — do not break them.

## Out of Scope

- The `--epic-branches` CLI flag itself (argparse wiring, TUI surface) —
  **FEAT-2450**. This child only reads it defensively via `getattr`.
- EPIC-completion detection / merge / partial-failure gate — **FEAT-2449**.
- `_inspect_worktree` epic-awareness — **FEAT-2562**.

## Acceptance Criteria

- [ ] `cli/sprint/run.py` resolves `effective_epic_branches` (defensive `getattr`
      + config fallback) alongside `effective_feature_branches`.
- [ ] When epic mode is effective and the wave runs in-place, an epic-branch
      caveat is emitted (appended to, or emitted alongside, the existing warning).
- [ ] The existing `"feature-branch mode does not apply"` substring test still
      passes unchanged.
- [ ] A new `TestFeatureBranchInPlaceWarning` epic counterpart asserts the epic
      caveat.
- [ ] Full `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation (1 file):**
- `scripts/little_loops/cli/sprint/run.py` (in-place warning block ~`:517-529`)

**Tests (1 file):**
- `scripts/tests/test_cli_sprint.py` (`TestFeatureBranchInPlaceWarning` epic
  counterpart)

**Estimated file count:** 1 implementation + 1 test = **2 files**.

## Integration Map

- **Files to Modify**: `cli/sprint/run.py`
- **Depends On**: nothing (config/args flags only; independent of FEAT-2561)
- **Similar Patterns**: the `effective_feature_branches` resolution + guarded
  `logger.warning` immediately above the change site (`run.py:518-529`).
- **Tests**: `TestFeatureBranchInPlaceWarning` (`test_cli_sprint.py:732-879`)
- **Substring to preserve**: `"feature-branch mode does not apply"`.

## Blocks

- FEAT-2450 (CLI/TUI/docs polish waits on all functional epic-branch work)

## Session Log
- `/ll:confidence-check` - 2026-07-09T00:00:00 - `b4b437e8-ceeb-4657-a600-ad4fd9cabd3d.jsonl` (decomposition of FEAT-2449)
