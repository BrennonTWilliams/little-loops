---
id: BUG-2732
title: finalize_decomposed_parent() moves closed parents into legacy .issues/completed/,
  reintroducing the directory BUG-2403 tried to retire
type: BUG
status: done
priority: P1
parent: BUG-2728
discovered_date: '2026-07-21'
discovered_by: issue-size-review
labels:
- issues
- dependency-graph
- regression
relates_to:
- BUG-2403
- ENH-1390
- BUG-2733
confidence_score: 92
outcome_confidence: 79
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 18
score_change_surface: 18
completed_at: '2026-07-22T00:20:49Z'
---

# BUG-2732: `finalize_decomposed_parent()` still moves closed parents into legacy `.issues/completed/`

## Summary

Decomposed from BUG-2728: `finalize_decomposed_parent()`
(`scripts/little_loops/recursive_finalize.py`, lines 110–210) writes
`status: done` in place (correct, per ENH-1418) but then unconditionally
`git mv`s the file to `<issues_dir>/completed/` unless the caller passes
`--no-move`. `move_to_completed` defaults to `True`, so every parent closed
via decomposition (`ll-issues finalize-decomposition`, wired from
`autodev.yaml`'s `enqueue_children`/`enqueue_or_skip` states and
`rn-decompose.yaml`'s `finalize_parent` state) lands in the legacy directory
that ENH-1390's `ll-migrate` was supposed to retire in favor of type-based
directories.

This is one of two component defects from BUG-2728. This child covers the
**write path** — stopping new files from landing in `completed/` and
relocating the one file BUG-2728 found already parked there. The companion
defect (blocker-status resolution not recognizing a `done` issue that's
already parked in a legacy directory) is tracked separately as BUG-2733.

## Current Behavior

When a decomposed parent issue is closed via `ll-issues finalize-decomposition`
(called from `autodev.yaml`'s `enqueue_children`/`enqueue_or_skip` states and
`rn-decompose.yaml`'s `finalize_parent` state), `finalize_decomposed_parent()`
writes `status: done` in place and then unconditionally `git mv`s the file
into `<issues_dir>/completed/` — because `move_to_completed` defaults to
`True` and the CLI only skips the move via an opt-in `--no-move` flag.
BUG-2728 itself demonstrates this: it was closed via decomposition into
BUG-2732/BUG-2733 and landed at
`.issues/completed/P1-BUG-2728-done-issues-in-vestigial-completed-dir-break-blocked-by-resolution.md`
instead of staying in `.issues/bugs/`.

## Expected Behavior

`finalize_decomposed_parent()` closes the parent in place — `status: done`
written to the file at its existing type-based path (`.issues/bugs/`,
`.issues/enhancements/`, etc.) — with no move to `.issues/completed/`,
matching the ENH-1418 in-place convention already used by
`issue_lifecycle.py:complete_issue_lifecycle()`. No new files appear under
`.issues/completed/` after a decomposition-driven closure.

## Steps to Reproduce

1. Decompose an issue into children (e.g. via `/ll:decide-issue` or manually
   creating child issue files with `parent:` pointing at the same EPIC/none).
2. Run `ll-issues finalize-decomposition <PARENT-ID> --children <CHILD-ID>...`
   without `--no-move`.
3. Observe the parent file's `status:` becomes `done` **and** the file is
   `git mv`'d from its type directory (`.issues/bugs/`, etc.) into
   `.issues/completed/`.

## Parent Issue

Decomposed from BUG-2728: `done` issues in vestigial `.issues/completed/` are
invisible to `blocked_by` resolution, permanently blocking dependents.

## Root Cause

- **File**: `scripts/little_loops/recursive_finalize.py`
- **Anchor**: `finalize_decomposed_parent()` (lines 110–210), move logic at
  lines 167–173
- **Cause**: `if move_to_completed and "completed" not in parent_path.parts:`
  `git mv`s the file to `<issues_dir>/completed/`. `move_to_completed`
  defaults to `True`; `cmd_finalize_decomposition()`
  (`scripts/little_loops/cli/issues/finalize_decomposition.py`) only skips
  the move via an opt-in `--no-move` flag.
- **Why BUG-2403 didn't catch this**: BUG-2403 fixed only
  `auto-refine-and-implement.yaml`'s closure-metric counting of `completed/`
  and explicitly rejected adding a new finalize state that would move every
  `status: done` issue there. It treated the decomposition path's move as a
  separate, pre-existing, retained behavior to route around (via
  union-counting), not something in its own scope to fix.

## Proposed Fix

- Relocate the file BUG-2728 found already parked in the legacy directory —
  `.issues/completed/P2-ENH-2721-usage-events-run-id-live-writer.md` — into
  `.issues/enhancements/` (its type-based directory). Reuse the
  `ll-migrate` one-time-migration convention
  (`scripts/little_loops/cli/migrate.py:main_migrate()`, ENH-1390) rather
  than a one-off manual move, so any other already-parked files are swept in
  the same pass.
- Flip `finalize_decomposed_parent()`'s default to in-place (no move),
  bringing it in line with ENH-1418's in-place convention already used by
  `issue_lifecycle.py:close_issue()`. Update
  `cmd_finalize_decomposition()`'s `--no-move` flag surface (help text and
  default) in lockstep — see Integration Map.
- Add a guard (test or `ll-verify-*` gate) asserting no new files appear
  under `.issues/completed/` after a decomposition-driven closure.

## Integration Map

### Files to Modify
- `scripts/little_loops/recursive_finalize.py` — `finalize_decomposed_parent()`
  (lines 110–210): stop moving closed parents into `completed/`.
- `scripts/little_loops/cli/issues/finalize_decomposition.py` —
  `cmd_finalize_decomposition()` calls `finalize_decomposed_parent(...,
  move_to_completed=not args.no_move)` and owns the `--no-move` argparse
  flag (`add_finalize_decomposition_parser()`). If the fix flips the default
  to in-place (no move), the flag's help text and default must be updated
  here in lockstep with `recursive_finalize.py`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py:1072,1491` — parallel-sprint
  `close_issue()` callers; confirm they stay in-place-only (they should
  already, per ENH-1418) so the decomposition path is the only remaining
  mover.

### Similar Patterns
- `scripts/little_loops/cli/migrate.py:main_migrate()` (lines 87–215,
  ENH-1390) — the established one-time-migration-CLI convention for
  reconciling files left in `completed_dir`/`deferred_dir` back into
  type-scoped directories; use for the immediate ENH-2721 relocation instead
  of a one-off manual move.
- `scripts/little_loops/issue_lifecycle.py:close_issue()` (lines 621–717) —
  the in-place, no-move convention (ENH-1418) that
  `finalize_decomposed_parent()` should be brought in line with.

### Tests
- `scripts/tests/test_recursive_finalize.py:test_parent_closed_and_moved`
  (lines 40–56), `test_idempotent` (lines 78–90), and
  `test_cli_children_file_path` (lines 102–130) — currently assert the
  parent **is** moved to `completed/`; these encode the behavior this bug
  wants changed and need updating alongside the fix.
- `scripts/tests/test_builtin_loops.py:TestRecursiveRefineLoop`
  (lines 5279–5318) — `test_enqueue_children_moves_parent_to_completed` and
  `test_enqueue_or_skip_moves_parent_to_completed_when_children_found`
  string-assert `"completed"`/`"mv"` in the FSM action text. **Reconcile
  first**: ENH-2615's `test_..._calls_finalize_decomposition` (lines
  4103–4123) already asserts `"git mv" not in action` for the
  CLI-delegated states, so these older raw-`mv` assertions may already be
  stale/coincidentally-passing — check the current
  `enqueue_children`/`enqueue_or_skip` YAML before editing.
- **New tests to write**:
  - `finalize_decomposed_parent(..., move_to_completed=False)` — assert
    parent stays at its type-dir path, `status: done` written,
    `result["moved"] is False`.
  - `cmd_finalize_decomposition` with `--no-move` — argparse
    `Namespace(no_move=True)` case asserting no move occurred.
  - A guard/regression asserting no new files appear under
    `.issues/completed/` after a decomposition-driven closure.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_decompose.py:test_finalize_parent_writes_decomposed_and_calls_cli`
  (line ~462) — string-asserts the `rn-decompose` `finalize_parent` action
  contains `"ll-issues finalize-decomposition"` and routes `next == "done"`; it
  does **not** assert on `--no-move`/move behavior. Should stay green as written
  (verify unaffected); it's the `rn-decompose`-side call-site anchor relying on
  the current default. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — `auto-refine-and-implement` `finalize`
  **consumer** tests (~lines 2334–2629, e.g. `test_finalize_counts_decomposition_closure_as_closed`,
  `test_finalize_combines_completed_and_done_in_place_closures`,
  `_run_finalize`/`_write_done_in_place_fixture` helpers) seed
  `completed=("EPIC-9",)` as **decomposition-closure ground truth**, encoding the
  old "decomposed parents show up as a `completed/` diff" assumption. After the
  flip, decomposed parents complete in place — confirm the union's `status:done`
  branch still counts them (see Consumer-Side Ripple above) and add/adjust a
  done-in-place fixture if the `completed/`-seeding no longer reflects reality.
  **Not this bug's direct scope to alter, but flag-and-confirm.** [Agent 3 finding]
- Confirmed NOT affected (no edit): `scripts/tests/test_output_parsing.py`
  `test_phrasing_move_to_completed_directory`/`test_phrasing_closure_status`
  (lines 692, 702) — these test `/ll:ready-issue` free-text phrase parsing, a
  name collision only, unrelated to `finalize_decomposed_parent`. [Agent 3]

### Consumer-Side Ripple (Closure Metric)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — the `finalize`
  state's CLOSED verdict is the **UNION** of a `.issues/completed/` diff and a
  `status:done` diff (BUG-2403). Its comments explicitly frame the `completed/`
  diff as the channel for **decomposed umbrellas that autodev git-mv's there**
  (lines 14–17, 77–85, 690–748, esp. 710–711 "ENH-2385: decomposed-parent
  closures — issues that reached `.issues/completed/` during this run"). After
  this fix, decomposed parents complete **in place** (`status: done`) and no
  longer enter `completed/`; the union's `status:done` branch (lines 723–748)
  should still count them, so the CLOSED **count is expected to be preserved** —
  but this must be **verified**, and the ENH-2385/BUG-2403 comments describing
  the `git-mv`-to-`completed/` decomposition channel go stale and need updating.
  [Agent 3 finding — downstream ripple, must confirm the union still catches
  decomposed parents via the status:done diff]

### Documentation
- `docs/reference/CLI.md` — `ll-issues finalize-decomposition` `--no-move`
  entry (~lines 1341–1359, "Do not move the closed parent into the
  completed directory") needs reconciling if the move default flips.
- `docs/ARCHITECTURE.md` — Issue Processing Lifecycle mermaid diagram
  (`Move to completed/`, `Move to .issues/completed/`,
  `Move to .issues/deferred/`) is adjacent stale documentation of the
  move-based model ENH-1418 deprecated.
- `scripts/little_loops/loops/autodev.yaml` — inline ENH-2615 comments at
  the `enqueue_children`/`enqueue_or_skip` states (~lines 611–617, 867–871)
  assert "finalize-decomposition … owns the status-done close + completed/
  move"; update the comments if the owned side effect changes.
- `scripts/little_loops/loops/rn-decompose.yaml` — `finalize_parent` state
  (~lines 218–232) calls `ll-issues finalize-decomposition` with **no**
  `--no-move`, i.e. relies on the current default. If the default flips,
  this call site's behavior changes silently unless it passes an explicit
  flag.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (~line 82) — the `little_loops.recursive_finalize`
  module-reference row ("Powers `ll-issues finalize-decomposition`…"). Generic;
  states no default or move behavior, so **not stale** under the flip — verify
  only, no edit expected. [Agent 1 + Agent 2 finding]
- `scripts/little_loops/cli/issues/__init__.py` (lines 48–50, 912–913) —
  imports `add_finalize_decomposition_parser`/`cmd_finalize_decomposition` and
  dispatches `args.command == "finalize-decomposition"`. **Pure routing, no
  default/polarity logic — unaffected by the flip.** Listed for completeness;
  no change needed. [Agent 1 finding]
- `scripts/little_loops/config-schema.json` — defines `completed_dir`/
  `deferred_dir` (both `[DEPRECATED]`). Confirmed **NOT** a coupling point:
  `recursive_finalize.py` hardcodes the `"completed"` literal and never reads
  these keys. (Whether resolvers should honor `completed_dir` is BUG-2733's
  open decision, not this issue's.) [Agent 2 finding — negative result]

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. All existing anchors
in this issue were verified accurate against current source in this pass._

- **Two files are currently parked in `.issues/completed/`, not one.** The dir
  holds both `P2-ENH-2721-usage-events-run-id-live-writer.md` **and**
  `P1-BUG-2728-...done-issues-in-vestigial-completed-dir...md` (this issue's own
  parent). The Proposed Fix / AC name only ENH-2721, but the `ll-migrate` sweep
  the fix already advocates ("so any other already-parked files are swept in the
  same pass") will relocate **both**: `main_migrate()`
  (`scripts/little_loops/cli/migrate.py`, lines 87–215) resolves each file's
  target dir from its frontmatter `type` (precedence) then filename prefix, so
  ENH-2721 → `.issues/enhancements/` and BUG-2728 → `.issues/bugs/`. AC-1 should
  be read as "relocate ENH-2721 **and any other already-parked file**," which
  the sweep satisfies. (`main_migrate()` skips-and-errors rather than overwrites
  if the target already exists, backfills `completed_at`, and uses `git mv` for
  tracked / rename for untracked files.)

- **ENH-1418 in-place precedent: cite `complete_issue_lifecycle()`, not
  `close_issue()`.** Both are in-place (neither moves the file), but the literal
  ENH-1418 callout comment — "Does not move the file (ENH-1418 decoupled status
  from directory location)" — lives on `complete_issue_lifecycle()`
  (`scripts/little_loops/issue_lifecycle.py`, lines 728–730). `close_issue()`
  (lines 621–717) is behaviorally in-place too, but its own docstring (line 632)
  still stale-says "moving it to completed." Use `complete_issue_lifecycle()` as
  the precedent anchor when bringing `finalize_decomposed_parent()` in line.

- **Flipping the default is a one-boolean change; the argparse registration does
  not need editing** (unless the fix also changes `--no-move`'s polarity/help).
  `--no-move` is `action="store_true"` with no explicit `default=` in
  `finalize_decomposition.py` (implicit `False`); the CLI computes
  `move_to_completed=not args.no_move` (line 47). Flipping to in-place means
  changing `finalize_decomposed_parent()`'s own `move_to_completed: bool = True`
  default (`recursive_finalize.py`, line 115) — and deciding whether the CLI
  should invert to an opt-in `--move` flag or keep `--no-move` as a redundant
  no-op. The Proposed Fix's "update `--no-move` help/default in lockstep" is
  really a flag-surface **redesign** decision, not just a default flip.

- **The three loop-YAML call-site comments assert the `completed/` move as
  *intentional, owned* behavior** (ENH-1977 Fix 4 / ENH-2615), so the
  Integration-Map doc updates are correcting documented design intent in three
  places, not just clearing incidental stale comments: `rn-decompose.yaml`
  `finalize_parent` (lines 219–220), `autodev.yaml` `enqueue_children` (lines
  613–616) and `enqueue_or_skip` (lines 870–871). None pass `--no-move`; all
  rely on the current default, so behavior at all three flips silently when the
  default flips — matching the issue's own callout.

- **Guard AC — recommended implementation (fills the "test or `ll-verify-*`
  gate" gap).** No directory-emptiness guard exists anywhere in the suite today
  (grep-confirmed). Lowest-cost satisfying option: a **plain pytest test** in
  `scripts/tests/test_recursive_finalize.py` that runs a decomposition closure
  and asserts `list((issues / "completed").glob("*.md")) == []`, using the same
  `Path.glob` idiom already used at `test_recursive_finalize.py:65,70,87,129`.
  If a persistent, install-wide CI gate is preferred instead, the established
  `ll-verify-*` recipe is: a new `cli/verify_*.py` `main_verify_*()` returning
  exit 1 on violation (model: `cli/verify_kinds.py`) + a `[project.scripts]`
  entry in `scripts/pyproject.toml` + import & `__all__` in `cli/__init__.py` +
  a `shutil.which`-skip-guarded subprocess pytest belt (model:
  `scripts/tests/test_decisions_yaml_gate.py`) so it runs under
  `python -m pytest scripts/tests/`. **Recommendation:** the pytest test — the
  guard is a narrow behavioral invariant, and a new console-script gate is more
  scaffolding than the invariant warrants.

- **Existing move-asserting tests confirmed** (need inverting alongside the fix):
  `test_parent_closed_and_moved` (asserts `result["moved"] is True` +
  `completed/…exists()`), `test_idempotent`, and `test_cli_children_file_path`
  in `test_recursive_finalize.py`. `test_missing_parent_reports_warning` already
  asserts `result["moved"] is False` and is unaffected. New tests should assert
  `result["moved"] is False`, parent stays at its type-dir path, and
  `status: done` is still written.

## Acceptance Criteria

- [x] `.issues/completed/P2-ENH-2721-usage-events-run-id-live-writer.md` is
      relocated to `.issues/enhancements/`
- [x] The closure write path (`finalize_decomposed_parent()`) no longer
      creates files under `.issues/completed/`
- [x] A guard/test asserts no new files appear under `.issues/completed/`
      after a decomposition-driven closure

## Impact

- **Severity**: High (P1) — silently reintroduces a legacy directory ENH-1390
  set out to retire, and is a direct contributor to BUG-2728's `blocked_by`
  resolution failures for every dependent of a decomposed parent.
- **Scope**: Every decomposition-driven closure (`autodev.yaml`,
  `rn-decompose.yaml`) until fixed; already caused BUG-2728 itself, and
  ENH-2721 before it, to land in `.issues/completed/`.
- **Effort**: Low — a single default flip in `finalize_decomposed_parent()`
  plus a one-time sweep of already-parked files via `ll-migrate`.
- **Risk**: Low — brings the decomposition path in line with the existing
  ENH-1418 in-place convention already used elsewhere in the codebase.

## Resolution

- **Status**: Fixed
- **Closed**: 2026-07-22
- `finalize_decomposed_parent()`'s `move_to_completed` default flipped to
  `False` (`scripts/little_loops/recursive_finalize.py`); the parent now
  closes in place (`status: done`) at its existing type-based path, matching
  the ENH-1418 convention.
- `ll-issues finalize-decomposition`'s flag surface replaced `--no-move`
  (opt-out) with `--move` (opt-in to the legacy `completed/` move), since the
  in-place behavior is now the default (`scripts/little_loops/cli/issues/finalize_decomposition.py`).
- Ran `ll-migrate` to sweep the two files already parked in
  `.issues/completed/` back to their type-based directories: BUG-2728 →
  `.issues/bugs/`, ENH-2721 → `.issues/enhancements/`.
- Updated `test_recursive_finalize.py` (renamed/added tests for in-place
  default, explicit `move_to_completed=True`, the `--move` CLI flag, and a
  guard asserting no new files appear under `.issues/completed/`).
- Updated stale `completed/`-move comments in `autodev.yaml` (`enqueue_children`,
  `enqueue_or_skip`) and `rn-decompose.yaml` (`finalize_parent`), and the
  `docs/reference/CLI.md` `finalize-decomposition` reference.
- Confirmed unaffected: `test_rn_decompose.py`'s CLI-call assertion, the
  `auto-refine-and-implement.yaml` CLOSED-count union tests (status:done
  branch still counts in-place closures), and `recursive-refine.yaml`'s
  separate raw `git mv` decomposition path (a distinct legacy loop, out of
  this bug's scope).

## Status

**Done** | Discovered: 2026-07-21 | Priority: P1

## Session Log
- `/ll:manage-issue` - 2026-07-22T00:20:21Z - bug fix
- `/ll:ready-issue` - 2026-07-22T00:11:28 - `6bd17951-4621-46a0-aa7b-be92ed6f5ae1.jsonl`
- `/ll:confidence-check` - 2026-07-22T00:08:25 - `21a53531-4ba6-47f1-aaf6-3a4a1f42f43a.jsonl`
- `/ll:wire-issue` - 2026-07-22T00:06:16 - `cbd1c0a6-59b0-4953-9095-51deb707a86d.jsonl`
- `/ll:refine-issue` - 2026-07-21T23:59:39 - `aee65b80-d95f-4660-945f-83ae026e84ac.jsonl`
- `/ll:issue-size-review` - 2026-07-21T23:52:25 - `35cd122b-5b42-4ccf-8307-837e09286f3f.jsonl`
