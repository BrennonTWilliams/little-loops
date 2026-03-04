---
id: ENH-569
priority: P3
status: active
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: null
outcome_confidence: null
---

# ENH-569: `ll-loop show` prompt action text over-truncated at 70 chars

## Summary

`cmd_show` truncates all action text to 70 characters regardless of action type. For `action_type: prompt` states, the full prompt *is* the spec — 70 chars conveys almost nothing useful. The output is misleading because it implies completeness.

## Current Behavior

For the `fix` state in `issue-refinement`:
```
  [fix]
    action: Run `ll-issues refine-status` to see the current refinement state of a...
    type: prompt
```

The prompt is ~1,500 chars long. The truncation hides all actionable content.

## Expected Behavior

Show a meaningful excerpt, differentiated by action type:

- **`shell`** actions: keep 70-char single-line truncation (these are commands, brevity works)
- **`prompt`** actions: show first 3 lines or ~200 chars, then `...` — enough to see the intent
- **`slash_command`** actions: show full command (usually short)

Additionally, add a `--verbose` / `-v` flag to `ll-loop show` that prints the full action text and full evaluate prompt for all states.

## Motivation

When debugging a loop or reviewing it before running, the prompt action text is what you most need to read. The current 70-char cap forces users to open the YAML file directly, defeating the purpose of `ll-loop show`.

## Implementation Steps

1. In `cmd_show` (`scripts/little_loops/cli/loop/info.py`), change the action display logic:
   ```python
   if state.action:
       if state.action_type == "prompt":
           # Show first ~200 chars or 3 lines
           lines = state.action.strip().splitlines()
           preview = "\n      ".join(lines[:3])
           if len(lines) > 3 or len(state.action) > 200:
               preview += " ..."
           print(f"    action: |\n      {preview}")
       else:
           action_display = state.action[:70] + "..." if len(state.action) > 70 else state.action
           print(f"    action: {action_display}")
   ```

2. Add `--verbose` flag to the `show` subcommand parser (in `scripts/little_loops/cli/loop/__init__.py` or wherever args are parsed) and thread it through to `cmd_show`.

3. In verbose mode, print full action text and full evaluate prompt without truncation.

## Files to Change

- `scripts/little_loops/cli/loop/info.py` — `cmd_show` action display logic
- `scripts/little_loops/cli/loop/__init__.py` (or main arg parser) — add `--verbose` flag

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d569869-6d78-45db-ae07-4c05f23b46fe.jsonl`
