---
discovered_date: 2026-04-11
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-1051: Show prompt state response output in ll-loop run non-verbose mode

## Summary

`ll-loop run` shows up to 5 lines of the input prompt for LLM/AI agent states but shows **zero lines** of the response. Shell states get an 8-line tail preview in non-verbose mode. The asymmetry makes live loop monitoring nearly useless for prompt-heavy loops — you can watch the prompt go in but you have no idea what came back without running with `--verbose`.

## Motivation

The output suppression is an explicit intentional skip in `_helpers.py:446`:

```python
if output_preview and not is_prompt and not verbose:
```

The comment above it reads `"Skip output preview for prompt states (already streamed)"`, but this is only true in verbose mode. In non-verbose mode, `action_output` events are gated behind `if not quiet and verbose` (`_helpers.py:418`), so nothing streams. The prompt response disappears completely. Users who want to watch a loop run without the full `--verbose` firehose have no feedback on what the LLM produced.

## Current Behavior

For a prompt (LLM/AI agent) state in non-verbose mode:

```
[1/10] refine  (3s)
 -> ✦ (47 lines)
       You are an expert...
       The issue below needs...
       ...
       ... (42 more lines)
       (12.4s)
✓ yes (0.87)
       → evaluate
```

The LLM response (potentially hundreds of lines) is never surfaced. Only the prompt input is shown.

## Expected Behavior

Show a configurable head preview of the LLM response after `action_complete`, symmetric with how shell states show a tail preview:

```
[1/10] refine  (3s)
 -> ✦ (47 lines)
       You are an expert...
       The issue below needs...
       ...
       ... (42 more lines)
       (12.4s)  ← response (8 lines shown):
       The issue has been analyzed. The root cause is...
       ## Changes Made
       1. Updated `foo.py` to handle the edge case...
       2. Added validation in `bar.py`...
       ... (143 more lines)
✓ yes (0.87)
       → evaluate
```

## Implementation Steps

### `scripts/little_loops/cli/loop/_helpers.py` — `action_complete` block (lines 443–451)

**Current logic:**

```python
# Skip output preview for prompt states (already streamed) and in verbose mode
# (lines already shown via action_output events). In non-verbose mode, show
# a tail summary for shell states.
if output_preview and not is_prompt and not verbose:
    lines = [ln for ln in output_preview.splitlines() if ln.strip()]
    show_lines = lines[-8:] if lines else []
    for line in show_lines:
        display = line[:max_line] + "..." if len(line) > max_line else line
        print(f"{indent}       {display}", flush=True)
```

**Proposed logic:**

```python
# In verbose mode, output was already shown via action_output events — skip preview.
# In non-verbose mode, show a head preview for prompt states and a tail preview
# for shell states so users get signal on what the action produced.
if output_preview and not verbose:
    lines = [ln for ln in output_preview.splitlines() if ln.strip()]
    if is_prompt:
        # Head preview for LLM responses — the meaningful content is usually upfront
        show_lines = lines[:8] if lines else []
        if lines:
            print(f"{indent}       {colorize(f'← response ({len(lines)} lines):', '2')}", flush=True)
    else:
        # Tail preview for shell commands — the summary is usually at the end
        show_lines = lines[-8:] if lines else []
    for line in show_lines:
        display = line[:max_line] + "..." if len(line) > max_line else line
        print(f"{indent}       {display}", flush=True)
    if is_prompt and len(lines) > 8:
        print(f"{indent}       {colorize(f'... ({len(lines) - 8} more lines)', '2')}", flush=True)
```

**Key decisions:**
- **Head for prompts, tail for shell**: LLM responses lead with the result; shell command output summarizes at the end.
- **8 lines default**: matches existing shell tail behavior; consider making this configurable via `cli.output.response_preview_lines` in a follow-up.
- **The `not is_prompt` condition is removed**: the "already streamed" comment only applies to verbose mode, which is already excluded by `not verbose`.
- **Label the response section**: `← response (N lines):` header gives context that this is output, not more prompt content.

### No other files need changes for the core display logic

`output_preview` is already populated for prompt states — `executor.py:522` computes `result.output[-2000:].strip()` unconditionally, regardless of action mode. The data is there; it is only suppressed in the display layer.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

2. Update `scripts/little_loops/cli/loop/__init__.py:129` — revise `--verbose` argparse help string so it accurately describes the new distinction between default (head-preview) and verbose (full streaming) modes; e.g. `"Stream all action output live; default shows a short response preview"`
3. Update `docs/reference/CLI.md:251` — revise the `--verbose` table row to reflect that non-verbose now shows a response head preview (not zero output)
4. Update `docs/guides/LOOPS_GUIDE.md:1462` — same description repeated verbatim; update in tandem

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — change the `action_complete` gate at line 446 from `not is_prompt and not verbose` → `not verbose`; add head-preview branch with `← response` label and trailing `... (N more lines)` footer
- `scripts/little_loops/cli/loop/__init__.py:129` — update `--verbose` help string (`"Show full prompt text and more output lines"`) to distinguish streaming-all vs. head-preview default [Wiring pass added by `/ll:wire-issue`]
- `docs/reference/CLI.md:251` — `--verbose` table row description becomes misleading after non-verbose mode shows response head preview [Wiring pass added by `/ll:wire-issue`]
- `docs/guides/LOOPS_GUIDE.md:1462` — same `--verbose` description repeated verbatim; update in tandem with CLI.md [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Read-Only, No Changes Needed)
- `scripts/little_loops/fsm/executor.py:522` — computes `preview = result.output[-2000:].strip()`; populates `output_preview` for all action modes unconditionally; `is_prompt` set via `action_mode == "prompt"` at line 527
- `scripts/little_loops/cli/output.py:90` — `colorize(text: str, code: str) -> str`; already imported in `_helpers.py:14`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py:224` — the sole caller of `run_foreground()`; passes `args` with `verbose`/`quiet` flags; no signature change needed

### Test File
- `scripts/tests/test_ll_loop_display.py` — add tests to the `TestDisplayProgressEvents` class following the existing `MockExecutor` + `capsys` + `_make_args()` pattern (see lines 1494–1602)

### Similar Patterns to Follow
- `_helpers.py:393-415` — `action_start` prompt head-preview: shows `min(5, line_count)` lines with `colorize('(N lines)', '2')` badge; same `{indent}       {display}` indentation used by the response preview
- `test_ll_loop_display.py:1566-1602` — `test_verbose_shell_output_printed_once` / `test_nonverbose_shell_output_shows_preview`: exact template for new `test_nonverbose_prompt_output_shows_head_preview` and `test_verbose_prompt_output_not_duplicated` tests

### Tests to Add (`TestDisplayProgressEvents`)

```python
def test_nonverbose_prompt_output_shows_head_preview(
    self, capsys: pytest.CaptureFixture[str]
) -> None:
    """In non-verbose mode, prompt action_complete shows a head preview of the response."""
    events = [
        {
            "event": "action_complete",
            "exit_code": 0,
            "duration_ms": 5000,
            "output_preview": "Line 1\nLine 2\nLine 3",
            "is_prompt": True,
        }
    ]
    executor = MockExecutor(events)
    run_foreground(executor, self._make_fsm(), self._make_args(verbose=False))
    out = capsys.readouterr().out
    assert "Line 1" in out
    assert "← response" in out

def test_verbose_prompt_output_not_shown_at_action_complete(
    self, capsys: pytest.CaptureFixture[str]
) -> None:
    """In verbose mode, prompt output streams via action_output; action_complete must not duplicate it."""
    events = [
        {"event": "action_output", "line": "streamed line"},
        {
            "event": "action_complete",
            "exit_code": 0,
            "duration_ms": 5000,
            "output_preview": "streamed line",
            "is_prompt": True,
        },
    ]
    executor = MockExecutor(events)
    run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
    out = capsys.readouterr().out
    assert out.count("streamed line") == 1

def test_quiet_prompt_output_not_shown(self, capsys: pytest.CaptureFixture[str]) -> None:
    """In quiet mode, no output preview is shown for prompt states."""
    events = [
        {
            "event": "action_complete",
            "exit_code": 0,
            "duration_ms": 1000,
            "output_preview": "should not appear",
            "is_prompt": True,
        }
    ]
    executor = MockExecutor(events)
    run_foreground(executor, self._make_fsm(), self._make_args(quiet=True))
    out = capsys.readouterr().out
    assert "should not appear" not in out
```

## Verification

1. `ll-loop run <loop-with-prompt-state>` (non-verbose) → LLM response head (≤8 lines) appears after duration line
2. `ll-loop run <loop-with-prompt-state> --verbose` → no change (action_output stream already shows full response)
3. `ll-loop run <loop-with-shell-state>` (non-verbose) → shell tail preview unchanged (last 8 lines)
4. `ll-loop run <loop-with-prompt-state> --quiet` → nothing shown (quiet suppresses all)
5. Existing tests: `python -m pytest scripts/tests/ -k loop -v`

## Related Issues

- ENH-1050: Wire display_progress and print_execution_plan to config-driven color system (same file)
- ENH-595 (completed): Added basic `colorize()` and `terminal_width()` to `_helpers.py`

---

## Status

Open

## Session Log
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/edc93ae2-94de-4f41-8e9d-da6398b38296.jsonl`
- `/ll:wire-issue` - 2026-04-12T05:04:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a85d1e55-862d-4918-9fa4-361cea909a58.jsonl`
- `/ll:refine-issue` - 2026-04-12T04:57:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0152ccce-218b-4988-9c5c-e983140da495.jsonl`
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1437654-cf08-44ef-b694-93b1f1d22897.jsonl`
