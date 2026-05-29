# ENH-1701 Implementation Plan

## Issue
Show artifact paths in `ll-loop run` and `ll-loop monitor` output

## Research Findings Summary
- `_build_pinned_pane` @ line 272: header appended at 361, diagram at 362-364
- `_render_pinned_pane` @ line 371: builds closure `_build()` that calls `_build_pinned_pane`
- `StateFeedRenderer.__init__` @ line 459: stores fsm, args, loops_dir, etc.
- `StateFeedRenderer._redraw_pinned` @ line 499: calls `_render_pinned_pane`
- `StateFeedRenderer.handle_event` non-pinned path @ lines 621-636
- `run_foreground` @ line 1032: startup block @ 1086-1089, StateFeedRenderer @ 1078
- `run_background` @ line 912: existing path display pattern @ 1023-1028
- `resolve_loop_path` @ line 792, `load_loop` @ line 816
- `cmd_run` @ run.py:88, `cmd_resume` @ lifecycle.py:360, `cmd_monitor` @ lifecycle.py:532

## Implementation Steps

### Phase 0: Tests (Red)
- [ ] `_artifact_lines` unit test — verify path-like values extracted, template expressions excluded
- [ ] `_build_pinned_pane` with `loop_path` test — verify artifact lines between header and diagram
- [ ] Non-pinned `handle_event` artifact-lines test — verify lines printed after header

### Phase 1: _helpers.py Core
- [ ] Add `_artifact_lines(fsm, loop_path)` helper
- [ ] Add `loop_path` to `_build_pinned_pane` signature, insert artifact lines after header
- [ ] Add `loop_path` to `_render_pinned_pane` signature, thread through `_build` closure
- [ ] Add `loop_path` to `StateFeedRenderer.__init__`, store as `self.loop_path`
- [ ] Update `StateFeedRenderer._redraw_pinned` to pass `self.loop_path`
- [ ] Add artifact lines in non-pinned `handle_event` path after header
- [ ] Add `loop_path` to `run_foreground` signature, pass to StateFeedRenderer, print in startup block
- [ ] In `run_background`, display loop path using existing pattern

### Phase 2: Callers
- [ ] `run.py:cmd_run` — pass resolved `path` to `run_foreground(loop_path=path)`
- [ ] `lifecycle.py:cmd_resume` — resolve path, thread through `run_foreground`
- [ ] `lifecycle.py:cmd_monitor` — resolve path, pass to `StateFeedRenderer`

### Phase 3: Verify
- [ ] Run test suite
- [ ] Run linter
- [ ] Run type checker
