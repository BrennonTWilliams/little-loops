---
discovered_date: 2026-04-11
discovered_by: capture-issue
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

### No other files need changes

`output_preview` is already populated for prompt states — `executor.py:522` computes `result.output[-2000:].strip()` unconditionally, regardless of action mode. The data is there; it is only suppressed in the display layer.

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
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1437654-cf08-44ef-b694-93b1f1d22897.jsonl`
