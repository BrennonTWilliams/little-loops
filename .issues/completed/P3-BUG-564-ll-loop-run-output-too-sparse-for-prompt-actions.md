# BUG-564: ll-loop run output too sparse for prompt actions

## Summary

The `ll-loop run` output is too sparse and truncated to understand what's happening during execution, especially for prompt-type actions. Users cannot see what prompts are being executed or what output they produce.

## Current Behavior

Three specific problems:

1. **Prompt actions show NO output** - `executor.py:527` explicitly sets `output_preview = None` for slash commands/prompts:
   ```python
   preview = result.output[-200:].strip() if result.output and not is_slash_command else None
   ```
   Users see duration but zero indication of what the action produced.

2. **Action text severely truncated** - `_helpers.py:225-226` truncates actions to ~52 chars for prompts:
   ```python
   max_len = 60 - len(prefix)  # ~52 chars for prompts
   action_display = action[:max_len] + "..." if len(action) > max_len else action
   ```
   Complex prompts (like the issue-refinement fix state with 1200+ chars) are cut off after the first sentence.

3. **Evaluate event drops the raw LLM response** - The evaluator returns `details["raw"]` with full LLM response but display only shows verdict, confidence, and reason. Additional context about which specific issues need work is lost.

Current output example:
```
[1/100] evaluate -> [prompt] Run ll-issues refine-status...
       (45.2s)
       ✗ failure (0.92)
         Some issues have em-dashes
       -> fix
```

## Expected Behavior

Users should be able to see:
- More of the action text (or full text in verbose mode)
- At least a summary of prompt output (not just duration)
- Key details from raw LLM response (e.g., which specific issue IDs need attention)

## Steps to Reproduce

1. Run `ll-loop run issue-refinement`
2. Observe the output during execution
3. Note that you cannot see what the prompt is doing or what it produced

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `in _run_action()` line 527
- **Cause**: Output preview intentionally excluded for prompt/slash command actions

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `in display_progress()` lines 225-226
- **Cause**: Action text truncated to 60 chars minus prefix length

## Proposed Solution

1. **Show output preview for prompts** - Include last N lines or a summary of prompt output (not just shell commands)
2. **Increase action truncation limit** - Show more context, or add `--verbose` flag to show full action text
3. **Include key details from raw LLM response** - Extract and display relevant details like issue IDs from the evaluation result

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` - Add output preview for prompts
- `scripts/little_loops/cli/loop/_helpers.py` - Increase truncation limit, show more evaluation details

### Tests
- `scripts/tests/test_loop_execution.py` - Add tests for output display

### Documentation
- Update loop documentation if new `--verbose` flag added

## Implementation Steps

1. Modify `executor.py` to capture output preview for prompt-type actions
2. Update `_helpers.py` display logic to show more context
3. Add verbose mode flag if needed for full output
4. Test with issue-refinement loop

## Impact

- **Priority**: P3 - Reduces observability but doesn't break functionality
- **Effort**: Small - Changes localized to two files
- **Risk**: Low - Display-only changes
- **Breaking Change**: No

## Labels

`bug`, `captured`, `ll-loop`

---

## Resolution

- **Status**: Fixed
- **Date**: 2026-03-04
- **Changes**:
  - `scripts/little_loops/fsm/executor.py:527` — Removed `not is_slash_command` guard so prompt actions now emit output preview (last 500 chars)
  - `scripts/little_loops/cli/loop/_helpers.py:225` — Increased action truncation limit from 60 to 120 chars (prompts now show ~111 chars instead of ~51)
  - `scripts/little_loops/cli/loop/_helpers.py:244-257` — Prompt `action_complete` now shows last 3 lines of output (each up to 120 chars); shell keeps showing last 1 line (up to 100 chars)
  - `scripts/little_loops/cli/loop/_helpers.py:280` — Increased evaluate `reason` truncation from 120 to 300 chars
  - `scripts/tests/test_ll_loop_display.py` — Updated `test_action_truncation` to use new 120-char limit

## Session Log

- `/ll:capture-issue` - 2026-03-04T09:50:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07dab55f-8142-425b-8507-7a9873d64648.jsonl`
- `/ll:ready-issue` - 2026-03-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbc1c475-4122-4160-92ec-f5d55de86681.jsonl`
- `/ll:manage-issue` - 2026-03-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

---

**Completed** | Created: 2026-03-04 | Priority: P3
