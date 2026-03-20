# ENH-838: Show LLM model name in ll-auto header
**Date**: 2026-03-20
**Issue**: `.issues/enhancements/P4-ENH-838-show-llm-model-name-in-ll-auto-header.md`

## Summary

Add `--output-format stream-json` to the Claude subprocess call, parse the `system/init` event to extract the model name, and surface it via an `on_model_detected` callback so `AutoManager` can log it in the run header.

## Solution Design

### Core Approach
- Switch `cmd_args` to `stream-json` mode and parse each stdout line
- Route events: init → model callback, assistant → extract text, other → skip, non-JSON → passthrough
- New optional `on_model_detected: Callable[[str], None] | None` parameter threads through the call stack
- `AutoManager` stores detected model on instance, logs it when first detected

### Call Chain for `on_model_detected`
```
subprocess_utils.run_claude_command(on_model_detected=...)
    ↑ called by
issue_manager.run_claude_command(on_model_detected=...)  [wrapper]
    ↑ called by
process_issue_inplace(on_model_detected=...)
    ↑ called by
AutoManager._process_issue()  [uses self._detected_model + closure]
```

## Implementation Steps

### Phase 0: Write Tests (Red)

**`scripts/tests/test_subprocess_utils.py`** — new class `TestRunClaudeCommandModelDetection`:

1. `test_on_model_detected_called_with_model_name` — init event fires callback with model string
2. `test_init_event_not_added_to_stdout` — init event line not in result.stdout
3. `test_assistant_event_text_extracted_to_stdout` — text content from assistant event goes to result.stdout
4. `test_assistant_event_text_passed_to_stream_callback` — assistant text goes to stream_callback
5. `test_unknown_event_type_skipped` — non-init/non-assistant JSON lines skipped
6. `test_non_json_line_passthrough` — non-JSON lines pass through as raw text
7. `test_on_model_detected_none_no_error` — no callback, init event, no exception

**`scripts/tests/test_subprocess_mocks.py`** — extend `TestRunClaudeCommand`:
8. `test_wrapper_passes_on_model_detected` — `issue_manager.run_claude_command` passes callback to `_run_claude_base`

**`scripts/tests/test_issue_manager.py`** — new test:
9. `test_auto_manager_logs_model_name` — `AutoManager` calls `self.logger.info` with `"model: <name>"`

### Phase 1: subprocess_utils.py changes

**File**: `scripts/little_loops/subprocess_utils.py`

1. Add `import json` (line 10 area)
2. Add type alias: `ModelCallback = Callable[[str], None]`
3. Add `on_model_detected: ModelCallback | None = None` to `run_claude_command()` signature (after `on_process_end`)
4. Update docstring for new param
5. Change `cmd_args` (line 88):
   ```python
   cmd_args = ["claude", "--dangerously-skip-permissions", "--output-format", "stream-json", "-p", command]
   ```
6. In the readline loop, after `line = line.rstrip("\n")`, replace direct append/callback with event routing:
   ```python
   if not is_stderr:
       try:
           event = json.loads(line)
           etype = event.get("type")
           if etype == "system" and event.get("subtype") == "init":
               if on_model_detected and "model" in event:
                   on_model_detected(event["model"])
               continue  # don't add to stdout_lines
           elif etype == "assistant":
               # Extract text from content blocks
               msg = event.get("message", {})
               text_parts = [
                   block["text"]
                   for block in msg.get("content", [])
                   if block.get("type") == "text"
               ]
               line = "".join(text_parts)
               if not line:
                   continue
           else:
               continue  # skip other event types
       except (json.JSONDecodeError, KeyError, TypeError):
           pass  # non-JSON: passthrough as raw text

   if is_stderr:
       stderr_lines.append(line)
   else:
       stdout_lines.append(line)

   if stream_callback:
       stream_callback(line, is_stderr)
   ```

### Phase 2: issue_manager.py changes

**File**: `scripts/little_loops/issue_manager.py`

1. Add `on_model_detected: Callable[[str], None] | None = None` to `run_claude_command()` wrapper (line 92)
2. Pass it to `_run_claude_base()` call
3. Add `on_model_detected: Callable[[str], None] | None = None` to `process_issue_inplace()` (line 284)
4. Pass it to `run_claude_command()` calls at lines 318 and ~367 (fallback retry)
5. In `AutoManager`:
   - Add `self._detected_model: list[str] = []` in `__init__`
   - In `_process_issue()`, create callback if not yet detected, pass via `process_issue_inplace(on_model_detected=...)`

### Phase 3: AutoManager model logging

In `AutoManager._process_issue()`:
```python
on_model: Callable[[str], None] | None = None
if not self._detected_model:
    def on_model(m: str) -> None:
        self._detected_model.append(m)
        self.logger.info(f"model: {m}")

result = process_issue_inplace(
    info, self.config, self.logger, self.dry_run,
    on_model_detected=on_model,
)
```

## Success Criteria

- [x] `--output-format stream-json` added to cmd_args
- [x] Init event triggers `on_model_detected` callback
- [x] Assistant text content extracted to stdout (no JSON bleed)
- [x] Other event types skipped, non-JSON passes through
- [x] `issue_manager.run_claude_command` wrapper passes callback
- [x] `process_issue_inplace` accepts and passes callback
- [x] `AutoManager` logs `model: <name>` on first detection
- [x] All new tests pass (green after implementation)
- [x] Existing tests pass (no regressions)
- [x] `ruff check` and `mypy` pass

## Files Changed

- `scripts/little_loops/subprocess_utils.py`
- `scripts/little_loops/issue_manager.py`
- `scripts/tests/test_subprocess_utils.py`
- `scripts/tests/test_subprocess_mocks.py`
- `scripts/tests/test_issue_manager.py`
