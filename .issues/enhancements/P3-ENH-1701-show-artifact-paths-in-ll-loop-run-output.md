---
id: ENH-1701
status: done
priority: P3
type: ENH
captured_at: '2026-05-25T21:57:02Z'
completed_at: 2026-05-29 03:22:42+00:00
discovered_date: 2026-05-25
discovered_by: capture-issue
parent: EPIC-1744
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1701: Show artifact paths in `ll-loop run` and `ll-loop monitor` output

## Summary

Add a small artifact-paths section to the `ll-loop run` and `ll-loop monitor` pinned header, displayed between the `== loop: name ==` line and the FSM diagram. The section shows the resolved loop YAML file path and any context values that look like filesystem paths (e.g. `output_dir: .loops/plans/`), so the user can preview outputs in another terminal while the loop runs. Both commands share the same `StateFeedRenderer`, so a single implementation covers both.

## Motivation

Loop runs that write plan files, rubric files, research findings, or other outputs give the user no indication of where those files are. For example, `rn-refine` writes to `.loops/plans/<slug>/` but nothing in the output points there. Users must consult the YAML or guess. Surfacing these paths at startup reduces friction and makes loops feel more transparent.

## Current Behavior

The pinned pane header shows only:

```
== loop: rn-refine =========================================
[FSM diagram]
```

No file paths are displayed until the loop completes and the `report` state prints them.

## Expected Behavior

```
== loop: rn-refine =========================================
  loop:       loops/rn-refine.yaml
  output_dir: .loops/plans/
────────────────────────────────────────────────────────────
[FSM diagram]
```

The same section also appears in the non-pinned (no `--show-diagrams`) startup block printed by `run_foreground`, and in the `ll-loop monitor` attach display (which reuses `StateFeedRenderer`).

## Proposed Solution

Add a `_artifact_lines(fsm, loop_path)` helper that extracts path-like context values from the FSM using a simple heuristic (non-empty string, starts with `.`/`/`/`~` or contains `/`, and does not contain `${`). Render the extracted paths between the `== loop: name ==` header and the FSM diagram in `_build_pinned_pane`, and in the non-pinned startup block in `run_foreground`. Thread `loop_path: Optional[Path]` through display functions, defaulting to `None` so sub-loop callers are unaffected. Both `ll-loop run` and `ll-loop monitor` share `StateFeedRenderer`, so monitor gets the artifact section automatically.

## Scope Boundaries

- **In scope**: Pinned pane header (`_build_pinned_pane`) and non-pinned startup block in `run_foreground`; `ll-loop monitor` attach display (via shared `StateFeedRenderer`); path-like context values using the heuristic below; `loop_path` defaulting to `None` so sub-loop callers are unaffected.
- **Out of scope**: Runtime validation or resolution of displayed paths; colorization or styling beyond the existing header format; surfacing context values that are not path-like strings; integration with the `report` state or post-run summaries.

## Success Metrics

- Users can identify loop YAML and output directory paths from the pinned header without consulting the YAML file
- Both `ll-loop run` and `ll-loop monitor` display artifact paths consistently via shared `StateFeedRenderer`
- No regressions in sub-loop display (loop_path defaults to None, all existing callers unaffected)

## Implementation Steps

1. **Thread `loop_path: Path | None` through call sites** — `resolve_loop_path()` is already called at `cmd_run` (`run.py:107`) and inside `load_loop` (`_helpers.py:825`); the resolved path is local-only and discarded after `load_and_validate`. Capture it at each call site:
   - `run.py:107` → pass `path` to `run_foreground(fsm, args, executor=executor, loop_path=path)` at line 392
   - `lifecycle.py:509` (`cmd_resume`) → same: thread through `run_foreground` call
   - `lifecycle.py:573` (`cmd_monitor`) → capture path from `load_loop` return, pass to `StateFeedRenderer(fsm, args, loops_dir=loops_dir, loop_path=path)` at line 587
   - `_helpers.py:934` (`run_background`) → display path in startup output (following existing pattern at lines 1023-1028)

2. **Add `_artifact_lines(fsm, loop_path)` helper** — extract path-looking values from `fsm.context` (a `dict[str, Any]`, see `FSMLoop` schema at `fsm/schema.py:872`): a value qualifies if it is a non-empty string, starts with `.` or `/` or contains `/`, and contains no `${` template expressions. Return a list of `(key, value)` pairs. The `loop_path` parameter is always included as the first entry (key: `"loop"`) when not `None`.

3. **Render the section** — three insertion points:
   - `_build_pinned_pane` (`_helpers.py:338-361`): after the `== loop: name ==` header line (appended at line 361), before the FSM diagram (line 362-364). Format: indented `"  key: value"` lines using `colorize(value, '2')` (dim), matching the `run_background` pattern at lines 1023-1028.
   - `run_foreground` startup block (`_helpers.py:1086-1089`): after `Max iterations:` line (line 1088), before the blank line (line 1089).
   - `StateFeedRenderer.handle_event` non-pinned path (`_helpers.py:630-636`): after the `== loop: name ==` header print (line 632), before the diagram print (line 636). This covers subsequent state transitions when `show_diagrams` is enabled in non-pinned mode.

4. **Add `loop_path: Path | None = None` to signatures**:
   - `_build_pinned_pane` (line 272): add `loop_path: Path | None = None` parameter
   - `_render_pinned_pane` (line 371): thread through to `_build_pinned_pane`
   - `StateFeedRenderer.__init__` (line 459): add `loop_path: Path | None = None`, store as `self.loop_path`
   - `StateFeedRenderer._redraw_pinned` (line 499): pass `self.loop_path` to `_render_pinned_pane`
   - `run_foreground` (line 1032): add `loop_path: Path | None = None` parameter; pass to `StateFeedRenderer` constructor at line 1078

_Enhanced by `/ll:refine-issue` — line numbers and third insertion point from codebase analysis_

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and should be included in the implementation:_

5. **Write `_artifact_lines` unit test** — create a test in `test_state_feed_renderer.py` or `test_ll_loop_display.py` using `_make_test_fsm()` with context values (`output_dir`, `plan_dir`, etc.); verify path-like values are extracted and template expressions (`${...}`) are excluded. Follow `TestStateFeedRendererHandleEvent` pattern (line 76).

6. **Write `_build_pinned_pane` with `loop_path` test** — add test in `test_ll_loop_display.py` that passes a `loop_path` and verifies artifact lines appear between the `== loop: name ==` header and the FSM diagram. Follow `test_show_diagrams_state_enter_prints_diagram` pattern (line 2002).

7. **Write non-pinned `handle_event` artifact-lines test** — add test in `test_state_feed_renderer.py` that sets up `show_diagrams=True` (non-pinned path at `_helpers.py:630-636`) with a `loop_path` and verifies artifact lines are printed after the header.

8. **Review `docs/reference/CLI.md` example output** — the `ll-loop monitor` example (lines 506-508) shows current output format; consider updating to include artifact-paths section for consistency with the new display.

## API/Interface

N/A — No public API changes. Internal helper `_artifact_lines(fsm, loop_path)` added to `_helpers.py`; `_build_pinned_pane` signature gains optional `loop_path: Optional[Path] = None` parameter.

## Heuristic for "looks like a path"

A context value is treated as a path if it:
- Is a non-empty `str`
- Starts with `.`, `/`, or `~`, OR contains at least one `/`
- Does NOT contain `${` (template expression — not yet resolved)

This matches `".loops/plans"`, `"./output"`, `"/tmp/scratch"` and excludes `"ITERATE"`, `"LOW"`, `"${captured.run_dir.output}"`.

## Files

- `scripts/little_loops/cli/loop/_helpers.py` — primary change site
  - `_build_pinned_pane` (line 272): add `loop_path` param, insert artifact section after header line
  - `_render_pinned_pane` (line 371): thread `loop_path` through
  - `StateFeedRenderer.__init__` (line 459): add `loop_path` param, store as `self.loop_path`
  - `StateFeedRenderer._redraw_pinned` (line 499): pass `self.loop_path` to `_render_pinned_pane`
  - `StateFeedRenderer.handle_event` (line 630-636): insert artifact section after non-pinned header
  - `run_foreground` (line 1032): add `loop_path` param; print artifact section after `Max iterations:` line
  - New: `_artifact_lines(fsm, loop_path)` helper
- `scripts/little_loops/cli/loop/run.py` — threading change only
  - `cmd_run` (line 107): capture resolved `path`, pass to `run_foreground` at line 392
- `scripts/little_loops/cli/loop/lifecycle.py` — threading change only
  - `cmd_resume` (line 509): thread `loop_path` through `run_foreground` call
  - `cmd_monitor` (line 573/587): capture `path` from `load_loop`, pass to `StateFeedRenderer`

_Enhanced by `/ll:refine-issue` — added run.py and lifecycle.py threading changes from codebase analysis_

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — primary change site. `_build_pinned_pane` (line 272): add `loop_path` param, insert artifact section after header. `_render_pinned_pane` (line 371): thread through. `StateFeedRenderer.__init__` (line 459): add `loop_path` param. `StateFeedRenderer._redraw_pinned` (line 499): pass `self.loop_path`. `StateFeedRenderer.handle_event` (line 630-636): insert artifact section after non-pinned header. `run_foreground` (line 1032): add `loop_path` param, print artifact section after `Max iterations:`. New: `_artifact_lines(fsm, loop_path)` helper.
- `scripts/little_loops/cli/loop/run.py` — `cmd_run` (line 107): capture resolved `path`, pass to `run_foreground` at line 392.
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume` (line 509): thread `loop_path` through `run_foreground`. `cmd_monitor` (line 573/587): capture path from `load_loop`, pass to `StateFeedRenderer`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:392` — `cmd_run` calls `run_foreground(fsm, args, executor=executor)`; resolved `path` is local-only at line 107, must be threaded through
- `scripts/little_loops/cli/loop/lifecycle.py:509` — `cmd_resume` calls `run_foreground(fsm, args, executor=executor)`; no `loop_path` threaded
- `scripts/little_loops/cli/loop/lifecycle.py:587` — `cmd_monitor` instantiates `StateFeedRenderer(fsm, args, loops_dir=loops_dir)`; no `loop_path` passed
- `scripts/little_loops/cli/loop/_helpers.py:934` — `run_background` calls `load_loop` (which resolves path internally but discards it); path would need extraction for display
- `scripts/little_loops/cli/loop/_helpers.py:825` — `load_loop` calls `resolve_loop_path` internally but discards the resolved path after `load_and_validate`
- `scripts/little_loops/cli/loop/_helpers.py:845` — `load_loop_with_spec` same pattern: resolves path, reads YAML, path is local-only

_Added by `/ll:refine-issue` — based on codebase analysis_

### Similar Patterns
- `scripts/little_loops/cli/loop/info.py:889-895` (`cmd_show`) — displays `str(path)` in a config line using `" · ".join(...)` with 3-space indent
- `scripts/little_loops/cli/loop/_helpers.py:1023-1028` (`run_background`) — prints path info with `colorize(str(path_value), '2')` (dim) and 2-space indent (`"  Log: ..."`)
- `scripts/little_loops/cli/loop/lifecycle.py:39-48` (`_format_log_label`) — factored helper that returns `str(log_file)` for display; pattern to model `_artifact_lines` after
- `scripts/little_loops/cli/loop/_helpers.py:1086-1089` (`run_foreground` startup block) — prints `Running loop: {name}` + `Max iterations: {N}` with colorize; artifact lines slot after this block

_Added by `/ll:refine-issue` — based on codebase analysis_

### Tests
- `scripts/tests/test_ll_loop_display.py` — primary test file for display functions; imports `run_foreground`, `_choose_pinned_layout`; uses `MockExecutor` + `capsys` for output assertions
- `scripts/tests/test_state_feed_renderer.py` — directly tests `StateFeedRenderer`; verifies rendering output
- `scripts/tests/test_cli_loop_lifecycle.py` — tests `cmd_monitor` via `lifecycle.py`; imports `_helpers` module
- `scripts/tests/test_cli_loop_worktree.py` — tests `run_foreground` in worktree contexts
- `scripts/tests/test_cli_loop_background.py` — tests `run_background` which also displays path info (existing pattern at `_helpers.py:1023-1028`)

_Added by `/ll:refine-issue` — based on codebase analysis_

_Wiring pass added by `/ll:wire-issue`:_
- **New tests to write** (3 gaps identified):
  - `_artifact_lines(fsm, loop_path)` unit test — no existing test; follow pattern in `test_state_feed_renderer.py` `_make_test_fsm()` (line 11) to create minimal FSM with context values
  - `_build_pinned_pane` with `loop_path` test — no direct test exists; follow `TestDisplayProgressEvents.test_show_diagrams_state_enter_prints_diagram` (line 2002) in `test_ll_loop_display.py`
  - Non-pinned `handle_event` artifact-lines test — the `show_diagrams=True, in_pinned_mode=False` code path at `_helpers.py:630-636` has no test; follow `TestStateFeedRendererHandleEvent` (line 76) in `test_state_feed_renderer.py`
- **Existing tests confirmed safe**: All existing tests use substring `in` assertions on output; `loop_path=None` default means no constructor/function calls break. `test_ll_loop_execution.py` (lines 149, 194, 242), `test_state_feed_renderer.py` (lines 52, 62, 69), `test_cli_loop_lifecycle.py` `TestCmdMonitor` (line 2235) all pass unchanged.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — shows example `ll-loop monitor` output (lines 506-508) and documents `ll-loop run` behavior; example output may need updating to reflect the new artifact-paths section between the header and diagram

### Configuration
- N/A

## Impact

- **Priority**: P3 — UX improvement; loops are fully functional without this, but users must consult the YAML to locate output paths during a run.
- **Effort**: Small — single file change; new `_artifact_lines` helper plus threading `loop_path: Optional[Path]` through two display functions.
- **Risk**: Low — output-only change; `loop_path` defaults to `None` so all existing callers are unaffected with no behavioral changes.
- **Breaking Change**: No

## Labels

`enhancement`, `ux`, `ll-loop`

## Resolution

Implemented by `/ll:manage-issue enhancement improve ENH-1701` on 2026-05-29.

### Changes Made

- **`scripts/little_loops/cli/loop/_helpers.py`**: Added `_artifact_lines(fsm, loop_path)` helper that extracts path-like context values from the FSM. Threaded `loop_path: Path | None = None` through `_build_pinned_pane`, `_render_pinned_pane`, `StateFeedRenderer.__init__`, `StateFeedRenderer._redraw_pinned`, and `run_foreground`. Artifact lines are rendered with 2-space indent and dim colorization between the `== loop: name ==` header and the FSM diagram in: the pinned pane, the non-pinned `handle_event` path, and the `run_foreground` startup block.
- **`scripts/little_loops/cli/loop/run.py`**: Pass resolved `loop_path` to `run_foreground(loop_path=path)` in `cmd_run`.
- **`scripts/little_loops/cli/loop/lifecycle.py`**: Resolve `loop_path` alongside `load_loop` in `cmd_resume` and `cmd_monitor`, thread to `run_foreground` / `StateFeedRenderer`.

### Tests Added

- `TestArtifactLines` (4 tests) in `test_state_feed_renderer.py` — unit tests for path extraction heuristic
- `test_non_pinned_handle_event_prints_artifact_lines` in `test_state_feed_renderer.py` — verifies artifact lines in non-pinned mode
- `test_run_foreground_startup_shows_artifact_paths` in `test_ll_loop_display.py` — verifies startup block output

### Verification

- 8040 tests pass (0 regressions; 10 pre-existing failures in `TestShowDiagramsSubprocessReemit`)
- `ruff check` passes
- `mypy` type checking passes

## Session Log
- `/ll:manage-issue` - 2026-05-29T03:24:02 - `d85f12a7-c85e-4471-b885-9197d219ef77.jsonl`
- `/ll:ready-issue` - 2026-05-29T02:55:50 - `82f0529e-8000-4736-8a2a-e8c25f82d1b0.jsonl`
- `/ll:confidence-check` - 2026-05-28 - `358f113a-4acd-4899-a149-3c67227c3aac.jsonl`
- `/ll:wire-issue` - 2026-05-29T02:48:32 - `ae7b0149-ae11-41b9-943c-cc3211273c10.jsonl`
- `/ll:refine-issue` - 2026-05-29T02:41:24 - `805655a0-3762-4e3d-929a-ece68774fd31.jsonl`
- `/ll:format-issue` - 2026-05-29T02:25:47 - `c530bceb-47b8-4d43-bb17-49b4bbf4410b.jsonl`
- `/ll:format-issue` - 2026-05-25T22:02:36 - `432171fe-0cc8-40cb-a835-f0fb1286db77.jsonl`
- `/ll:capture-issue` - 2026-05-25T21:57:02Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

---
**Open** | Created: 2026-05-25 | Priority: P3
