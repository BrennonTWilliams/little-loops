---
discovered_date: 2026-03-20T00:00:00Z
discovered_by: capture-issue
---

# ENH-838: Show LLM model name in ll-auto header via stream-json init event

## Summary

`ll-auto` (and other CLI tools) invoke Claude via `claude --dangerously-skip-permissions -p <command>` but never display which model is actually running. Adding `--output-format stream-json` to the subprocess call exposes a `system` init event as the very first line of output — before any LLM tokens — that contains the `model` field. Parsing this event lets `AutoManager` log the model name in the run header.

## Location

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Anchor**: `run_claude_command()` — `cmd_args` assembly and readline loop
- **Related**: `scripts/little_loops/issue_manager.py` — `AutoManager`, `run_claude_command()` wrapper, `Logger.header()`

## Current Behavior

The model used for a run is invisible. Users have no way to confirm which Claude model processed their issues from the `ll-auto` output alone.

## Expected Behavior

The `ll-auto` header (or per-issue header) displays the active model name, e.g.:

```
════════════════════════════════════════
ll-auto  |  model: claude-sonnet-4-6
════════════════════════════════════════
```

## Motivation

When testing multiple models or when the default model changes, users need to know which model ran. This is especially valuable in automated contexts where the terminal session log is the only audit trail.

## Proposed Solution

1. **Add `--output-format stream-json`** to `cmd_args` in `subprocess_utils.run_claude_command()`
2. **In the readline loop**, attempt `json.loads(line)` on each stdout line:
   - On `{"type": "system", "subtype": "init", "model": "..."}` — capture the model name (call a `on_model_detected` callback or store on a mutable container)
   - On `{"type": "assistant", ...}` — extract text content blocks and pass those as the `stream_callback` line (maintaining streaming UX)
   - Other event types — skip or pass through as-is
3. **Accumulate text** from assistant events into `stdout_lines` so `result.stdout` (used by `output_parsing.py`) remains plain text — no downstream changes needed
4. **Expose model** via a new optional `on_model_detected: Callable[[str], None] | None = None` parameter on `run_claude_command()`
5. **`AutoManager`** passes a callback that stores the model name and logs it in the run header via `logger.info()`

## Scope Boundaries

- Out of scope: Changing `output_parsing.py` regex parsers (they receive plain text as before)
- Out of scope: Exposing model on the `CompletedProcess` return value (callback is sufficient)
- Out of scope: `ll-parallel` / `ll-sprint` (can adopt the same approach independently)

## Implementation Steps

1. Add `--output-format stream-json` to `cmd_args` in `subprocess_utils.py:88`
2. Wrap the `json.loads(line)` parse in a try/except and route by `event["type"]`
3. Extract text from assistant content blocks: `event["message"]["content"]` list, `type == "text"` entries
4. Add `on_model_detected` callback param to `run_claude_command()` signature
5. Wire callback in `issue_manager.py` wrapper; store result; log in `AutoManager.run()` header

## Impact

- **Priority**: P4 — QoL observability improvement
- **Effort**: Small — ~40 lines in `subprocess_utils.py` + callback wiring
- **Risk**: Low — fallback: if JSON parse fails on a line, pass it through as raw text
- **Breaking Change**: No — `on_model_detected` is an optional param

## Labels

`enhancement`, `ll-auto`, `subprocess`

## Status

**Open** | Created: 2026-03-20 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07c52770-6d90-48f0-81b1-6b09daee89b1.jsonl`
