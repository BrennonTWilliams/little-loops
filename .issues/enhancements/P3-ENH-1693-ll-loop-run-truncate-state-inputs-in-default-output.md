---
id: ENH-1693
status: open
priority: P3
type: ENH
captured_at: "2026-05-25T20:51:20Z"
discovered_date: 2026-05-25
discovered_by: capture-issue
---

# ENH-1693: `ll-loop run` truncates state inputs in default output but shows full content without `--verbose`

## Summary

`ll-loop run` without `--verbose` still prints the full state input payload for each step (bash heredocs, Python scripts, etc.), even though these inputs are identical across iterations. The default output should truncate long inputs to a brief one-line preview; full content should only appear with `--verbose`.

## Motivation

Users running loops non-interactively want concise per-step status they can scan. Today the default output can be hundreds of lines of repeated heredoc content per iteration, which buries the meaningful signal (transition target, evaluator result). The `--verbose` flag exists but has no effect on input display.

## Current Behavior

Without `--verbose`, state input blocks print in full:

```
 [2/500] check_lifetime_limit (0s)   -> MAX_TOTAL=$(python3 << 'PYEOF'
import json
from pathlib import Path
p = Path('.ll/ll-config.json')
cfg = {}
if p.exists():
    try:
        cfg = j...
         0
         (0.4s)
         ✓ yes
         -> refine_issue
  [3/500] refine_issue (0s)   -> ✦ (1 lines)
         /ll:refine-issue ENH-1688 --auto
         Now I'll spawn 3 parallel research agents...
```

Note that `refine_issue` also shows the meta line `✦ (1 lines)` before the actual content instead of showing the content directly.

## Expected Behavior

Without `--verbose`, inputs are truncated to the first ~60 chars followed by `...`:

```
 [2/500] check_lifetime_limit (0s)   -> MAX_TOTAL=$(python3 << 'PYEOF'...
         0
         (0.4s)
         ✓ yes
         -> refine_issue
  [3/500] refine_issue (0s)   -> ✦ /ll:refine-issue ENH-1688 --auto
         Now I'll spawn 3 parallel research agents...
```

With `--verbose`, the full input is shown as today.

## Scope Boundaries

- **In scope**: Truncate state `input` display in default mode; remove the `✦ (N lines)` prefix when not verbose; gate full input behind `--verbose`
- **Out of scope**: Changing evaluator output display, loop YAML format, or other CLI flags

## Implementation Steps

1. Locate where `ll-loop run` prints each state's input (likely `scripts/little_loops/loop_runner.py` or the CLI rendering layer)
2. Add a helper that truncates a string to ~60 chars with `...` suffix if longer
3. In default (non-verbose) mode, apply the helper before printing state input
4. Remove or suppress the `✦ (N lines)` meta line in non-verbose mode; show the actual first line of content instead
5. In `--verbose` mode, keep existing full-content behavior

## Impact

- **Priority**: P3 - Non-critical UX improvement; full content remains accessible via `--verbose`
- **Effort**: Small - Display-only change in the loop runner render layer; no data-flow or evaluation logic changes
- **Risk**: Low - Output-only change; no effect on loop execution, evaluator routing, or YAML format
- **Breaking Change**: No

## Labels

`cli`, `ux`, `loop`, `output`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-25T20:54:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/98c0c55a-a905-432a-936c-1fdaa0a11afd.jsonl`
- `/ll:capture-issue` - 2026-05-25T20:51:20Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/389c4de8-bd09-42af-b2cc-f8421b2bd729.jsonl`

---

## Status

**Open** | Created: 2026-05-25 | Priority: P3
