---
id: FEAT-2563
title: "per-EPIC integration branch \u2014 cli/sprint/run.py in-place warning epic-awareness"
type: FEAT
priority: P3
status: done
captured_at: '2026-07-09T00:00:00Z'
discovered_date: 2026-07-09
discovered_by: confidence-check-decomposition
completed_at: '2026-07-11T05:30:41Z'
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
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

- [x] `cli/sprint/run.py` resolves `effective_epic_branches` (defensive `getattr`
      + config fallback) alongside `effective_feature_branches`.
- [x] When epic mode is effective and the wave runs in-place, an epic-branch
      caveat is emitted (appended to, or emitted alongside, the existing warning).
- [x] The existing `"feature-branch mode does not apply"` substring test still
      passes unchanged.
- [x] A new `TestFeatureBranchInPlaceWarning` epic counterpart asserts the epic
      caveat.
- [x] Full `python -m pytest scripts/tests/` exits 0.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Line numbers confirmed exact, no drift**: current `run.py` still has the
  in-place branch at `511` (`if len(wave) == 1 or is_contention_subwave:`),
  `_current_branch = _detect_current_branch()` at `517`, and the guarded
  `logger.warning` block at `524-529`. `_fb_warning_emitted = False` is
  declared once at `486`, before the wave loop — the epic counterpart
  (`_eb_warning_emitted`) should follow the same one-shot-per-sprint-run
  idiom, declared alongside it at `486`.
- **`config.parallel.epic_branches.enabled` already exists** — no config
  work needed. `EpicBranchesConfig` (`scripts/little_loops/config/automation.py:39-61`)
  defines `enabled: bool = False` and is wired onto
  `ParallelAutomationConfig.epic_branches` (`automation.py:91,127`). This is
  the exact attribute path to mirror `config.parallel.use_feature_branches`.
- **`args.epic_branches` confirmed absent from argparse** — grepping
  `scripts/little_loops/cli/sprint/__init__.py:120-152` (the `run` subparser)
  shows only `--feature-branches` (`BooleanOptionalAction`, `default=None`,
  lines 142-147); no `--epic-branches` flag exists yet, confirming the issue's
  defensive-`getattr` note is correct and necessary.
- **Message-concatenation idiom to follow**: this file's established pattern
  for multi-clause `logger.warning(...)` calls is implicit string-literal
  concatenation inside a single call (see `run.py:525-528` and other warning
  sites at `:423-426`, `:456-459`, `:661-665`) — not building a `msg` variable
  and appending to it before calling `logger.warning(msg)`. Follow this idiom:
  append the epic clause as an additional literal inside the same
  `logger.warning(...)` call (or add a second guarded `logger.warning(...)`
  call directly below, gated on `effective_epic_branches`), rather than
  mutating a message string.
- **Test scaffolding to extend**: `TestFeatureBranchInPlaceWarning`
  (`test_cli_sprint.py:732-879`) has three helpers to mirror —
  `_make_args(feature_branches=None)` (`:735`), `_make_config(*,
  use_feature_branches: bool)` (`:753`), and `_run(args, config, num_waves=1)`
  (`:761`) which patches `little_loops.cli.sprint.run.Logger` and captures
  `mock_logger.warning.side_effect` into a `warning_calls` list. The epic
  counterpart test should add `epic_branches=None` to `_make_args` and
  `epic_branches_enabled: bool` to `_make_config` (setting
  `config.parallel.epic_branches.enabled`), reusing `_run` unchanged, then
  filter `warning_calls` for the new epic-branch substring exactly as the
  five existing tests do at `:841, 851, 860, 869, 878` for the feature-branch
  substring.
- **No cross-file epic-branch override plumbing needed for this issue**:
  `create_parallel_config(...)` at `run.py:585-593` only forwards
  `use_feature_branches=getattr(args, "feature_branches", None)` — it does
  not forward an `epic_branches=` override either, so the multi-issue
  (`ParallelOrchestrator`) path is unaffected by this issue's scope and
  relies solely on static `config.parallel.epic_branches` today. Confirms
  "Out of Scope" is correctly bounded — no `create_parallel_config` change
  is needed here.

## Resolution

Added `effective_epic_branches` resolution (defensive `getattr(args,
"epic_branches", None)` falling back to `config.parallel.epic_branches.enabled`)
mirroring the existing `effective_feature_branches` pattern in
`cli/sprint/run.py`'s in-place / contention-subwave block. When epic mode is
effective, a second guarded `logger.warning(...)` call fires (deduplicated via
`_eb_warning_emitted`, one-shot per sprint run), independent of the existing
feature-branch warning — preserving the `"feature-branch mode does not apply"`
substring unchanged. Added 6 new tests to
`TestFeatureBranchInPlaceWarning` in `test_cli_sprint.py` covering the epic
counterpart (config flag, CLI flag, unset, explicit false, dedup-across-waves,
and both-warnings-independent). Full suite: 14596 passed, 36 skipped.

## Blocks

- FEAT-2450 (CLI/TUI/docs polish waits on all functional epic-branch work)

## Session Log
- `/ll:manage-issue` - 2026-07-11T05:29:54 - `43e5506a-1207-4c57-ae1c-f2b3502390db.jsonl`
- `/ll:refine-issue` - 2026-07-11T05:17:43 - `88d823f1-e29f-4fd4-9b9e-53537a554e68.jsonl`
- `/ll:confidence-check` - 2026-07-09T00:00:00 - `b4b437e8-ceeb-4657-a600-ad4fd9cabd3d.jsonl` (decomposition of FEAT-2449)
- `/ll:confidence-check` - 2026-07-11T00:00:00 - `c4858b0c-0eb2-4285-a321-ffa51473f7fa.jsonl`
