---
discovered_date: 2026-03-20T00:00:00Z
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 90
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

1. Add `--output-format stream-json` to `cmd_args` in `subprocess_utils.py:88` — insert `"--output-format", "stream-json"` into the four-element list
2. In the readline loop at `subprocess_utils.py:122–179`: wrap each stdout `line` in `try: event = json.loads(line) except json.JSONDecodeError: pass`; route by `event["type"]`:
   - `{"type": "system", "subtype": "init", "model": "..."}` → call `on_model_detected(event["model"])` if set
   - `{"type": "assistant", ...}` → extract text from `event["message"]["content"]` list (`type == "text"` entries), join, use as the effective `line` for `stream_callback` and `stdout_lines`
   - All other event types → skip (do not append to `stdout_lines`, do not call `stream_callback`)
   - Non-JSON lines (fallback) → pass through as raw text (maintains backward compat)
3. Add `on_model_detected: Callable[[str], None] | None = None` parameter to `run_claude_command()` at `subprocess_utils.py:58–66` (after existing `on_process_end` param)
4. Add matching `on_model_detected` param to the `issue_manager.run_claude_command()` wrapper at `issue_manager.py:92`; pass it through to `_run_claude_base()` at line 120
5. In `AutoManager.run()` at `issue_manager.py:833–885`: define `detected_model: list[str] = []`; pass `on_model_detected=lambda m: detected_model.append(m)` when calling `run_claude_command()`; after/during first call, emit `self.logger.info(f"model: {detected_model[0]}")` near the startup log at line 840

> **Note**: `logger.header()` (`logger.py:106`) is gated by `if self.verbose` — if verbose mode is off (the default in ll-auto), it will not print. Use `logger.info()` as stated in step 5, or call `print()` directly for guaranteed visibility.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — primary change site: cmd_args (line 88), readline loop (lines 122–179), `run_claude_command()` signature (line 58)
- `scripts/little_loops/issue_manager.py` — thread `on_model_detected` through module-level wrapper (line 92) and wire in `AutoManager.run()` (line 833)

#### Dependent Callers of `_run_claude_base`
- `scripts/little_loops/issue_manager.py:120` — calls `_run_claude_base()` directly; receives the new param as optional (no breaking change)
- `scripts/little_loops/parallel/worker_pool.py:721` — also calls `_run_claude_base()` directly (method `_run_claude_command` starts at line 686); out-of-scope but unaffected (optional param)
- `scripts/little_loops/issue_manager.py:318` — `process_issue_inplace()` calls `issue_manager.run_claude_command()`; this is the call site being extended

#### Similar Patterns (to follow)
- `scripts/little_loops/mcp_call.py:108` — per-line `json.loads()` with `JSONDecodeError: continue` guard on live subprocess stdout — **closest parallel** to the stream-json readline loop change
- `scripts/little_loops/parallel/worker_pool.py:617` — uses `--output-format json` (blocking) to extract model name from `data["modelUsage"]` keys — related prior art for model detection
- `scripts/little_loops/user_messages.py:386` — JSONL per-line parse pattern with `except json.JSONDecodeError: continue`
- `scripts/little_loops/fsm/evaluators.py:619` — JSONL vs single-JSON disambiguation

#### Tests
- `scripts/tests/test_subprocess_utils.py:461` — `TestRunClaudeCommandStreaming`: follow for new `on_model_detected` callback tests (uses `io.StringIO` + `_patch_selector_cm` helpers)
- `scripts/tests/test_subprocess_utils.py:673` — `TestRunClaudeCommandProcessCallbacks`: follow for callback-invoked-once and callback-on-error patterns
- `scripts/tests/test_subprocess_mocks.py` — uses `issue_manager.run_claude_command` wrapper; update if wrapper signature changes
- `scripts/tests/test_issue_manager.py` — add test verifying model name appears in `AutoManager` startup output

#### Documentation
- `docs/reference/API.md` — documents `run_claude_command` parameters; update when signature changes
- `docs/research/claude-cli-integration-mechanics.md` — covers `--output-format stream-json` event structure; reference for implementation

## Impact

- **Priority**: P4 — QoL observability improvement
- **Effort**: Small — ~40 lines in `subprocess_utils.py` + callback wiring
- **Risk**: Low — fallback: if JSON parse fails on a line, pass it through as raw text
- **Breaking Change**: No — `on_model_detected` is an optional param

## Labels

`enhancement`, `ll-auto`, `subprocess`

## Resolution

**Completed** | 2026-03-20

### Changes Made

- `scripts/little_loops/subprocess_utils.py`:
  - Added `import json` and `ModelCallback = Callable[[str], None]` type alias
  - Added `--output-format stream-json` to `cmd_args`
  - Added `on_model_detected: ModelCallback | None = None` parameter to `run_claude_command()`
  - In the readline loop: routes `system/init` events to callback, extracts text from `assistant` events, skips all other event types, passes non-JSON lines through as raw text

- `scripts/little_loops/issue_manager.py`:
  - Added `Callable` to imports
  - Added `on_model_detected` parameter to `run_claude_command()` wrapper; passes through to `_run_claude_base()`
  - Added `on_model_detected` parameter to `process_issue_inplace()`; passed to both `run_claude_command()` call sites (initial + fallback retry)
  - Added `self._detected_model: list[str] = []` to `AutoManager.__init__()`
  - In `AutoManager._process_issue()`: builds a one-shot callback that appends model and calls `self.logger.info(f"model: {m}")`; passed to `process_issue_inplace()`

### Tests Added

- `TestRunClaudeCommandModelDetection` (7 tests) in `test_subprocess_utils.py`
- `test_wrapper_passes_on_model_detected` in `test_subprocess_mocks.py`
- `TestAutoManagerModelDetection` in `test_issue_manager.py`

## Status

**Completed** | Created: 2026-03-20 | Resolved: 2026-03-20 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-03-20T23:02:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4570ed6e-f15e-4647-8373-b99d8c1f9a40.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83be42b0-964f-445f-adf0-2d937be906b5.jsonl`
- `/ll:refine-issue` - 2026-03-20T22:54:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0521297f-d479-439c-a1a1-1262178dbfc7.jsonl`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07c52770-6d90-48f0-81b1-6b09daee89b1.jsonl`
- `/ll:manage-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
