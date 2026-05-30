---
id: ENH-1805
status: open
priority: P3
type: ENH
captured_at: '2026-05-30T04:12:22Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
---

# ENH-1805: Show LLM model in `ll-loop run` and `ll-loop monitor` header

## Summary

Extend the artifact-paths header section introduced in ENH-1701 to also display the LLM model being used in the current turn, when available. This gives users visibility into which model is executing their loop without consulting configuration files or CLI flags.

## Current Behavior

The pinned pane and startup header show:

```
== loop: rn-refine =========================================
  loop:       loops/rn-refine.yaml
  output_dir: .loops/plans/
────────────────────────────────────────────────────────────
[FSM diagram]
```

The LLM model is not displayed anywhere in the run or monitor output. Users must check the loop YAML's `model:` field, `.ll/ll-config.json`, or CLI flags to determine the active model.

## Expected Behavior

The model appears alongside artifact paths in the header:

```
== loop: rn-refine =========================================
  loop:       loops/rn-refine.yaml
  output_dir: .loops/plans/
  model:      claude-opus-4-7
────────────────────────────────────────────────────────────
[FSM diagram]
```

When the model is not available (not yet resolved, or running with the default), the model line is omitted. The model line uses the same 2-space indent and dim colorization as the artifact path lines.

## Motivation

Users running loops need to know which model is executing their work. A loop configured with `claude-haiku-4-5` behaves very differently from one using `claude-opus-4-7`, and surfacing the model in the header helps users:
- Correlate loop behavior and output quality with model capabilities
- Catch misconfigurations (e.g., an expensive model accidentally left on a frequent loop)
- Understand cost implications at a glance

## Proposed Solution

The model can be sourced from `fsm.context` if loops inject it there, or from the resolved FSM's `model` field. The `_artifact_lines` helper from ENH-1701 already extracts path-like values from `fsm.context`; the model should be handled similarly — either as an additional entry in `_artifact_lines` or as a separate `_model_line` helper. The model value should be dim-colorized matching the artifact path style (`colorize(value, '2')`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Canonical model source**: `fsm.llm.model` (`schema.py:592`), a `str` field on `LLMConfig` (default: `"sonnet"` per `DEFAULT_LLM_MODEL` at `schema.py:21`). The `FSMLoop` dataclass holds it as `llm: LLMConfig` at `schema.py:882`. It is resolved at load time and can be overridden by `--llm-model` in `cmd_run` (`run.py:123-124`). No injection into `fsm.context` is needed — the model is always available directly on the FSM object.
- **Recommended approach: separate `model` parameter** (not folded into `_artifact_lines`). `_artifact_lines` filters for path-like context values (`schema.py:806`); model is a simple string identifier, not a path, so mixing it there would blur the helper's semantics. Thread `model: str | None = None` alongside `loop_path: Path | None = None` in all display helpers, following the identical ENH-1701 pattern.
- **`cmd_resume`** also calls `run_foreground` (`lifecycle.py:516-527`) and must pass `model=fsm.llm.model` — same as `cmd_run`.
- **`cmd_monitor`** constructs `StateFeedRenderer` directly (`lifecycle.py:600`), not via `run_foreground`. It needs its own `model=fsm.llm.model` kwarg. The FSM is loaded at `lifecycle.py:581`, so `fsm.llm.model` is available.
- **Model omission rule**: Render the model line only when `model is not None`. Since `fsm.llm.model` always has a default (`"sonnet"`), this is never `None` in practice, but the parameter accepts `None` for caller compatibility.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — `_artifact_lines`, `_build_pinned_pane`, `_render_pinned_pane`, `StateFeedRenderer`, `run_foreground`
- `scripts/little_loops/cli/loop/diagram_modes.py` — references `_build_pinned_pane`, `_render_pinned_pane`
- `scripts/little_loops/cli/loop/run.py` — references `run_foreground`
- `scripts/little_loops/cli/loop/lifecycle.py` — references `StateFeedRenderer`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — calls `run_foreground`
- `scripts/little_loops/cli/loop/diagram_modes.py` — uses `_build_pinned_pane`, `_render_pinned_pane`
- `scripts/little_loops/cli/loop/lifecycle.py` — uses `StateFeedRenderer`

### Similar Patterns
- ENH-1701 artifact path threading pattern (`loop_path: Path | None` parameter chain through display helpers)

### Tests
- `scripts/tests/test_ll_loop_display.py` — display/rendering tests
- `scripts/tests/test_ll_loop_state.py` — FSM context tests

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **FSM schema**: `LLMConfig.model` at `scripts/little_loops/fsm/schema.py:592` — `model: str = DEFAULT_LLM_MODEL` where `DEFAULT_LLM_MODEL = "sonnet"` (line 21). `FSMLoop.llm` at line 882: `llm: LLMConfig = field(default_factory=LLMConfig)`.
- **`cmd_resume` path**: `lifecycle.py:516-527` — also calls `run_foreground()` (with `mode="resume"`) and must pass `model=fsm.llm.model`.
- **`cmd_monitor` path**: `lifecycle.py:600` — constructs `StateFeedRenderer` directly (not via `run_foreground`). FSM is loaded at line 581, so `fsm.llm.model` is available. Needs `model=fsm.llm.model` kwarg.
- **Background spawn path**: `_helpers.py:998-1000` passes `--llm-model` to child processes for `run_background()`; no display change needed there — the child process goes through `cmd_run` which will render the model in its own header.

## Scope Boundaries

- **In scope**: Pinned pane header (`_build_pinned_pane`), non-pinned startup block in `run_foreground`, and `ll-loop monitor` attach display (via shared `StateFeedRenderer`). Model sourced from resolved FSM configuration or context.
- **Out of scope**: Displaying model changes mid-run (if the loop switches models); displaying token usage or cost estimates; model display in `ll-loop run --json` output or `ll-loop info`.

## Success Metrics

- Users can identify the active LLM model from the header without consulting config files
- Both `ll-loop run` and `ll-loop monitor` display the model consistently
- No regressions in artifact path display or header formatting

## Implementation Steps

1. Add `model: str | None = None` parameter to `run_foreground()` (`_helpers.py:1059-1070`), threaded through to `StateFeedRenderer()` constructor (`_helpers.py:1107-1115`).
2. Add `model: str | None = None` parameter to `StateFeedRenderer.__init__()` (`_helpers.py:460-469`), stored as `self.model`, passed through `self._redraw_pinned()` → `_render_pinned_pane()` (`_helpers.py:507-519`) → `_build_pinned_pane()` (`_helpers.py:401-417`).
3. Add `model: str | None = None` parameter to `_render_pinned_pane()` (`_helpers.py:370-384`) and `_build_pinned_pane()` (`_helpers.py:268-284`).
4. In each of the three display locations, render the model line after `_artifact_lines` when `model is not None`: `print(f"  model: {colorize(model, '2')}", flush=True)`. The three locations:
   - `_build_pinned_pane()` at line 359 (pinned pane header)
   - `run_foreground()` startup at line 1119 (non-pinned startup banner)
   - `StateFeedRenderer.handle_event()` at line 635 (non-pinned diagram mode)
5. In callers, pass `model=fsm.llm.model`:
   - `cmd_run` (`run.py:393-403`) — `model=fsm.llm.model`
   - `cmd_resume` (`lifecycle.py:516-527`) — `model=fsm.llm.model`
   - `cmd_monitor` (`lifecycle.py:600`) — `model=fsm.llm.model` to `StateFeedRenderer`
6. Add tests for model display in pinned and non-pinned modes in `scripts/tests/test_ll_loop_display.py` and `scripts/tests/test_state_feed_renderer.py`
7. Verify no regressions in existing header rendering tests

## API/Interface

N/A — No public API changes. Internal threading of a `model: str | None` value through display helpers, following the same pattern as `loop_path: Path | None` from ENH-1701.

## Impact

- **Priority**: P3 — UX improvement; loops are fully functional without this, but model visibility reduces debugging friction
- **Effort**: Small — follows the established ENH-1701 threading pattern; primarily adding a `model` parameter alongside the existing `loop_path` parameter
- **Risk**: Low — output-only change; `model` defaults to `None` so all existing callers are unaffected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ux`, `ll-loop`

## Session Log
- `/ll:refine-issue` - 2026-05-30T04:27:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b91afdfc-9ce2-4940-af6d-9e5124943227.jsonl`
- `/ll:format-issue` - 2026-05-30T04:19:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e63eedbc-67a8-44a9-a0e7-5aaba9394a38.jsonl`
- `/ll:capture-issue` - 2026-05-30T04:12:22Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3dadd8e3-fc7a-4acb-bcd9-75794404ebd6.jsonl`

---

**Open** | Created: 2026-05-29 | Priority: P3
