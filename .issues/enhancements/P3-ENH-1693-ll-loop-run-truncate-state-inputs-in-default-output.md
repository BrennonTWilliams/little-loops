---
id: ENH-1693
status: done
priority: P3
type: ENH
captured_at: '2026-05-25T20:51:20Z'
completed_at: '2026-05-26T02:00:06Z'
discovered_date: 2026-05-25
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — `display_progress()` inside `run_foreground()`; the `action_start` + `if is_prompt:` branch is where `✦ (N lines)` is printed unconditionally and up to 5 content lines are shown; this is the only place needing changes

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — calls `run_foreground(args, ...)` with `args.verbose`; no changes needed
- `scripts/little_loops/cli/loop/__init__.py` — defines `--verbose` / `-v` on `run_parser`; help text currently reads `"Show full prompt at action start (default: first 5 lines)"` — may want to update to reflect new single-line-preview default

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py` — imports and calls `run_foreground()` inside `cmd_resume()` at line 553; no changes needed but confirms the function signature must not change
- `scripts/little_loops/cli/loop/layout.py` — defines `_ACTION_TYPE_BADGES = {"prompt": "✦", ...}` at line 110; the `✦` glyph source (informational — `_helpers.py` currently hardcodes the same character inline rather than reading from this dict)

### Similar Patterns
- `scripts/little_loops/cli/loop/info.py:_truncate()` — existing `_truncate(text: str, max_len: int) -> str` helper using Unicode `…`; already used for the `--follow` / `ll-loop history` action display; can be imported and reused here instead of inline `[:60] + "..."`
- `scripts/little_loops/cli/loop/_helpers.py:display_progress()` (shell branch) — existing inline `action[:max_line] + "..."` truncation for non-prompt actions; same shape, different width constant

### Tests
- `scripts/tests/test_ll_loop_display.py` — primary test file; `test_nonverbose_action_start_still_clips()` and `test_verbose_action_start_prompt_not_clipped()` are the most relevant existing tests to update or extend
- New test should assert: (a) no `✦ (N lines)` in non-verbose output, (b) single-line preview truncated at ~60 chars, (c) verbose still shows `✦ (N lines)` header + full content

_Wiring pass added by `/ll:wire-issue`:_
- **Breaking**: `TestDisplayProgressEvents.test_nonverbose_action_start_still_clips` (line 1848) — assert `"3 more lines" in out` will fail when multi-line display is replaced by single-line preview; update to assert `"3 more lines"` is absent and `"(N lines)"` header is absent instead
- **New test A**: `test_nonverbose_action_start_prompt_no_line_count_header` — send multi-line `action_start` with `verbose=False`; assert `"(3 lines)"` is not in output
- **New test B**: `test_nonverbose_action_start_prompt_single_line_preview` — send 80-char first line with `verbose=False` and `terminal_width=80`; assert `✦` glyph present, second line absent, `"..."` present
- **New test C**: `test_verbose_action_start_prompt_shows_line_count_header` — send 3-line prompt with `verbose=True`; assert `"(3 lines)"` in output and all lines shown

### Documentation
- `docs/reference/CLI.md` — may document `--verbose` flag behavior; review for accuracy after change

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — line 2561 references `--verbose` as "default shows a short response head preview"; general language, unlikely to break but review after change

## Implementation Steps

1. In `scripts/little_loops/cli/loop/_helpers.py`, locate the `action_start` event handler in `display_progress()` — the `if is_prompt:` branch where `prompt_badge = "✦"` and the `✦ (N lines)` header is printed unconditionally
2. In non-verbose mode: suppress the `✦ (N lines)` meta-line; instead compute `preview = lines[0][:60] + "..."` if the first line is longer than 60 chars (or reuse `_truncate` from `cli/loop/info.py`), and print `-> ✦ <preview>` as a single line
3. In `--verbose` mode: keep existing behavior — print `✦ (N lines)` header followed by all content lines unclipped
4. Confirm shell branch (non-prompt `action_start`) already truncates correctly via the existing `action[:max_line] + "..."` path — no change needed there
5. Add regression tests in `scripts/tests/test_ll_loop_display.py` following the `test_nonverbose_action_start_still_clips()` pattern; verify the `✦ (N lines)` line is absent in non-verbose output and the single-line preview appears instead
6. Optionally update the `--verbose` help text in `scripts/little_loops/cli/loop/__init__.py` `run_parser` to describe new default behavior

## Impact

- **Priority**: P3 - Non-critical UX improvement; full content remains accessible via `--verbose`
- **Effort**: Small - Display-only change in the loop runner render layer; no data-flow or evaluation logic changes
- **Risk**: Low - Output-only change; no effect on loop execution, evaluator routing, or YAML format
- **Breaking Change**: No

## Labels

`cli`, `ux`, `loop`, `output`, `captured`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/tests/test_ll_loop_display.py` — remove `"3 more lines"` assertion from `test_nonverbose_action_start_still_clips`; add the three new test functions (A, B, C) from the Tests section above
8. Review `docs/guides/LOOPS_GUIDE.md` line 2561 — confirm `--verbose` description remains accurate after the change

## Session Log
- `/ll:confidence-check` - 2026-05-25T22:00:00Z - `40b9e85f-3df3-4dbe-9eca-4660b1f63bad.jsonl`
- `/ll:wire-issue` - 2026-05-26T02:13:36 - `dcc3802e-2828-4704-a30b-3db7ca529d8f.jsonl`
- `/ll:refine-issue` - 2026-05-26T02:07:57 - `3eaac8be-eba9-48b8-a2d9-322df5114921.jsonl`
- `/ll:ready-issue` - 2026-05-26T01:56:52 - `390ae9e1-a32b-4da7-b395-03f2137e1b1f.jsonl`
- `/ll:confidence-check` - 2026-05-25T21:00:00Z - `b2b1b983-d9ad-4fe0-ae43-26bbbe98524d.jsonl`
- `/ll:wire-issue` - 2026-05-26T01:52:25 - `ef26377f-1811-47ab-854e-40635e78ae61.jsonl`
- `/ll:refine-issue` - 2026-05-26T01:47:46 - `c2047892-4db7-4e3b-823a-5c1f57ef6384.jsonl`
- `/ll:format-issue` - 2026-05-25T20:54:45 - `98c0c55a-a905-432a-936c-1fdaa0a11afd.jsonl`
- `/ll:capture-issue` - 2026-05-25T20:51:20Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/389c4de8-bd09-42af-b2cc-f8421b2bd729.jsonl`

---

## Status

**Open** | Created: 2026-05-25 | Priority: P3
