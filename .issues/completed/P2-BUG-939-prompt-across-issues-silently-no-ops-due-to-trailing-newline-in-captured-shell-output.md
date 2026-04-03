---
discovered_date: 2026-04-03
discovered_by: capture-issue
---

# BUG-939: `prompt-across-issues` silently no-ops on every issue due to trailing newline in captured shell output

## Summary

The `prompt-across-issues` built-in loop processes all issues but applies the prompt to none of them. Every issue is silently skipped. The loop completes in seconds rather than minutes because no real work is done.

Root cause: the FSM captures shell output including its trailing newline. In the `prepare_prompt` state, `${captured.current_item.output}` resolves to `"FEAT-001\n"`. The `sed "s/{issue_id}/$ISSUE_ID/g"` command fails (exit 1) because the replacement string contains an embedded newline. The captured `final_prompt` is empty, so `execute` runs a blank prompt.

## Steps to Reproduce

1. `ll-loop run prompt-across-issues "/ll:format-issue {issue_id} --auto" --verbose`
2. Observe `prepare_prompt` shows `exit: 1` for every issue
3. Observe `execute` shows `✦ (0 lines)` — no prompt sent
4. Loop completes all issues in ~10s with no changes made

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `_run_action()` — the capture storage block
- **Cause**: Captured shell output is stored verbatim from subprocess stdout, which includes the trailing `\n` emitted by `head -1`. When interpolated into a shell variable and used as a `sed` replacement string, the embedded newline causes `sed` to exit 1 and produce no output. `final_prompt` captures empty string; `execute` runs `""`.

```python
# executor.py — current behavior (capture stores raw stdout with \n)
if state.capture:
    self.captured[state.capture] = {
        "output": result.output,   # ← includes trailing \n
        ...
    }
```

The fix: strip trailing whitespace/newlines from captured output before storing.

```python
# proposed fix
if state.capture:
    self.captured[state.capture] = {
        "output": result.output.rstrip("\n\r"),  # ← strip trailing newlines
        ...
    }
```

## Current Behavior

- `prepare_prompt` exits 1 on every issue (sed fails due to `\n` in ISSUE_ID)
- `execute` receives empty `final_prompt`, sends blank prompt, does nothing
- Loop "completes" all issues in seconds with zero actual work done
- No error is reported; output looks normal

## Expected Behavior

- Captured shell output is free of trailing newlines (matching normal shell variable assignment behavior, e.g. `VAR=$(command)` strips trailing newlines automatically)
- `{issue_id}` is substituted correctly, `execute` runs the intended prompt per issue

## Motivation

This bug renders `prompt-across-issues` completely non-functional. Any loop that captures shell output and uses it in a subsequent shell substitution is broken by the same underlying issue. The silent failure is particularly harmful — there's no error, just wasted time.

## Proposed Solution

Strip trailing newlines from captured output in `_run_action()` in `executor.py`. This mirrors how shell command substitution works natively (`VAR=$(cmd)` always strips trailing newlines), making captured output behave as users intuitively expect.

```python
# scripts/little_loops/fsm/executor.py — _run_action()
if state.capture:
    self.captured[state.capture] = {
        "output": result.output.rstrip("\n\r"),  # strip trailing newlines
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
    }
```

No changes needed to the loop YAML or any other loop definitions.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_run_action()` capture storage block

### Dependent Files (Callers/Importers)
- All FSM loops that use `capture:` on shell states — all will benefit from the fix
- `scripts/little_loops/loops/prompt-across-issues.yaml` — specifically broken by this bug

### Similar Patterns
- Any existing loop with `capture:` + shell action that uses captured output in a subsequent shell action

### Tests
- `scripts/tests/` — add test: captured shell output should not include trailing newlines
- Existing FSM executor tests that cover `capture:` behavior

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `_run_action()` in `executor.py`, apply `.rstrip("\n\r")` to `result.output` before storing in `self.captured`
2. Run existing FSM executor tests to confirm no regressions
3. Add a test asserting `captured["x"]["output"]` has no trailing newline after a shell action
4. Manually verify: `ll-loop run prompt-across-issues "/ll:format-issue {issue_id} --auto" --verbose` shows `prepare_prompt` succeeding and `execute` receiving the correct prompt

## Impact

- **Priority**: P2 — `prompt-across-issues` is completely non-functional; silent failure means users may not notice
- **Effort**: Small — one-line fix in `executor.py`
- **Risk**: Low — behavior change only affects trailing whitespace in captured values; no existing loop should depend on a trailing newline
- **Breaking Change**: No — removes unwanted trailing newlines that no loop would intentionally rely on

## Related

- BUG-940: `on_error` dead code when `next` also defined — the same `prepare_prompt` state
- `scripts/little_loops/fsm/executor.py` — `_run_action()` capture block
- `scripts/little_loops/loops/prompt-across-issues.yaml` — affected loop

## Labels

`bug`, `fsm`, `loops`, `captured`

---

## Resolution

- Applied `.rstrip("\n\r")` to `result.output` before storing in `self.captured` in `executor.py:_run_action()`
- Added `test_capture_strips_trailing_newline` and `test_capture_strips_trailing_crlf` to `TestCapture` in `test_fsm_executor.py`
- All 131 tests pass

## Session Log
- `/ll:ready-issue` - 2026-04-03T22:14:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a85d9d85-aa09-48cc-87d7-2dd3a055329b.jsonl`
- `/ll:capture-issue` - 2026-04-03T22:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1745900e-c050-4c53-81d7-10a084dba4e9.jsonl`
- `/ll:manage-issue` - 2026-04-03T22:30:00Z - fix applied

---

**Closed** | Created: 2026-04-03 | Priority: P2
