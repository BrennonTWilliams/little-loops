---
discovered_date: 2026-04-06
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# ENH-969: ll-auto --verbose Should Show Full Content Without Truncation

## Summary

When `ll-auto` is run with the `--verbose` flag, output for prompts, responses, and other content is currently truncated (e.g., `"... (406 more lines)"`). The verbose mode should display full, untruncated content as intended.

## Current Behavior

Running `ll-auto --verbose` produces truncated output such as:
```
... (406 more lines)
```
Long prompt or response content is cut off, defeating the purpose of the verbose flag.

## Expected Behavior

With `--verbose`, all content (prompts, responses, tool outputs, etc.) should be displayed in full without any truncation. The verbose flag signals the user wants complete output for debugging or inspection purposes.

## Motivation

The `--verbose` flag is a debugging/inspection tool. Truncation undermines its value — if a user is investigating a prompt or response, they need the full text. Truncation may hide the exact content relevant to the issue being debugged.

## Root Cause

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `run_claude_command()` lines 118–128
- **Cause**: Two unconditional truncation mechanisms run regardless of the `--verbose` flag:
  1. **Vertical truncation**: `show_count = min(5, line_count)` — only the first 5 lines of the command are shown, producing `"... (N more lines)"` when there are more
  2. **Horizontal truncation**: each shown line is clipped to `terminal_width() - 4` characters
- `run_claude_command()` receives a `logger: Logger` but no `verbose` parameter; `Logger.verbose` only gates whether to print at all (`if self.verbose: print(...)`), not how much to print. The `--verbose` flag is therefore completely disconnected from truncation behavior.
- The `verbose` value itself (`args.verbose or not args.quiet`) defaults to `True` even without `--verbose`, so `verbose=True` is indistinguishable from "explicitly passed `--verbose`" inside the truncation code.

## Proposed Solution

Add a `preview_full: bool = False` parameter to `run_claude_command()` that disables both truncation mechanisms when `True`. Pass `args.verbose` (the raw flag, not the derived `verbose or not quiet`) as `preview_full` when calling `run_claude_command` from `AutoManager`.

This follows the existing `--full` bypass pattern in `scripts/little_loops/cli/loop/info.py:273-316`:
```python
prompt_text = llm_prompt if full else _truncate(llm_prompt, max(avail_w, 40))
```

Concrete changes to `run_claude_command()` lines 122-128:
```python
show_count = line_count if preview_full else min(5, line_count)
for line in lines[:show_count]:
    display = line if preview_full else (line[:max_line] + "..." if len(line) > max_line else line)
    logger.info(f"  {display}")
if line_count > show_count:
    logger.info(f"  ... ({line_count - show_count} more lines)")
```

`AutoManager` needs to store the raw `verbose` flag (`self._preview_full`) separately from the derived `Logger(verbose=...)` and pass it when invoking `run_claude_command`.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py:94-128` — add `preview_full: bool = False` parameter to `run_claude_command()`; apply conditional truncation inside
- `scripts/little_loops/issue_manager.py:743-770` — store `self._preview_full = verbose` on `AutoManager.__init__` (where `verbose` = raw `args.verbose`)
- `scripts/little_loops/issue_manager.py` — pass `preview_full=self._preview_full` at every `run_claude_command(...)` call site within `AutoManager`/`process_issue_inplace`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:146-155` — `run_with_continuation()` signature needs `preview_full: bool = False` parameter; it calls `run_claude_command` internally at line 186 and must thread the flag through [Agent 2 finding]
- `scripts/little_loops/issue_manager.py:349` — Phase 1 ready-issue call site inside `process_issue_inplace`; add `preview_full=preview_full` (passed down from `AutoManager`) [Agent 2 finding]
- `scripts/little_loops/issue_manager.py:404` — Phase 1 fallback/retry call site (path-mismatch path); same treatment as line 349 [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py:100` — currently passes `verbose=args.verbose or not args.quiet`; change to also pass raw `args.verbose` for the `preview_full` path
- `scripts/little_loops/cli/parallel.py:233` — `ParallelOrchestrator` follows the same `verbose → Logger` pattern; may need the same treatment for consistency (separate issue)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py:327,429` — calls `process_issue_inplace` directly; if `process_issue_inplace` gains a `preview_full` parameter, sprint runner may need to pass it or accept `False` as default [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/cli/loop/info.py:273-316` — `value if full else _truncate(value, N)` ternary pattern for truncation bypass; follow this exactly
- `scripts/little_loops/cli/loop/__init__.py:264-271` — `--full` flag definition that implies `--verbose`; reference for how to wire a bypass flag

### Tests
- `scripts/tests/test_subprocess_mocks.py:204-263` — three existing tests cover current truncation:
  - `test_prompt_display_abbreviated_for_long_command` (line 204) — asserts `"15 more lines"` trailer
  - `test_prompt_display_shows_all_lines_for_short_command` (line ~230) — no trailer for short prompts
  - `test_prompt_display_truncates_long_lines` (line ~247) — per-line `...` truncation
  - **New test needed**: `test_prompt_display_full_when_preview_full_true` — call `run_claude_command(long_command, logger, preview_full=True)` and assert no `"more lines"` trailer and no per-line `...` truncation
- `scripts/tests/test_issue_manager.py:724-839` — `TestAutoManagerQuietMode` tests verbose/quiet logger construction; add test that `AutoManager(verbose=True)._preview_full is True`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_subprocess_mocks.py` — **New test**: `test_prompt_display_full_shows_all_lines_when_preview_full_true` — call with 20-line command and `preview_full=True`, assert `"line 5"` through `"line 19"` appear in logger calls and no `"more lines"` trailer logged; follow pattern at lines 204-226 [Agent 3 finding]
- `scripts/tests/test_subprocess_mocks.py` — **New test**: `test_prompt_display_full_skips_line_truncation` — call with a 200-char line and `preview_full=True`, assert no `"..."` suffix in any logger output for that line [Agent 3 finding]
- `scripts/tests/test_cli.py:483-501` — `test_main_auto_verbose_short_flag` tests `-v` threading to `AutoManager(verbose=True)` but does not assert `preview_full` kwarg; update to also assert the new kwarg is passed correctly [Agent 3 finding]
- `scripts/tests/test_issue_manager.py:724-839` — add `TestAutoManagerQuietMode.test_auto_manager_verbose_stores_preview_full`: assert `manager._preview_full is True` when `AutoManager(config, verbose=True)` and `False` when `verbose=False` [Agent 3 finding]

### Documentation
- No documentation changes needed (the `--verbose` flag behavior change is self-explanatory)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:1861-1866` — `run_claude_command` signature already stale (missing `idle_timeout`, `on_model_detected` from prior changes); adding `preview_full` extends this gap further; note for a future API doc pass but not blocking for this issue [Agent 2 finding]

## Implementation Steps

1. **Add `preview_full` parameter** to `run_claude_command()` in `scripts/little_loops/issue_manager.py:94`: `preview_full: bool = False`
2. **Replace the truncation block** at lines 122-128 with conditional logic: `show_count = line_count if preview_full else min(5, line_count)` and `display = line if preview_full else (line[:max_line] + "..." if len(line) > max_line else line)`
3. **Store raw verbose flag** on `AutoManager`: add `self._preview_full: bool = verbose` in `__init__` at `issue_manager.py:770` (alongside the existing `Logger(verbose=verbose)`)
4. **Pass `preview_full`** at each `run_claude_command(...)` call inside `process_issue_inplace` / `AutoManager`
5. **Thread raw `args.verbose`** from `cli/auto.py:100` into `AutoManager` as its `verbose` argument (note: this currently already passes `args.verbose or not args.quiet`; the `or not args.quiet` part should remain for `Logger` but the raw `args.verbose` is what controls `preview_full`)
6. **Add test** in `test_subprocess_mocks.py`: call `run_claude_command(20_line_cmd, logger, preview_full=True, stream_output=False)` and assert no `"more lines"` string in any `logger.info` call and no per-line `"..."` truncation
7. **Run tests**: `python -m pytest scripts/tests/test_subprocess_mocks.py scripts/tests/test_issue_manager.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/issue_manager.py:146-155` (`run_with_continuation`) — add `preview_full: bool = False` parameter and pass it through to the internal `run_claude_command` call at line 186
9. Update `scripts/little_loops/issue_manager.py:349` — add `preview_full=preview_full` to the Phase 1 ready-issue call (thread down from `process_issue_inplace` signature)
10. Update `scripts/little_loops/issue_manager.py:404` — same as step 9 for the fallback/retry call site
11. Review `scripts/little_loops/cli/sprint/run.py:327,429` — calls `process_issue_inplace` directly; confirm it passes `preview_full=False` (default) or receives the flag from the sprint CLI if sprint gains `--verbose` support
12. Add 2 new tests to `scripts/tests/test_subprocess_mocks.py`: `test_prompt_display_full_shows_all_lines_when_preview_full_true` and `test_prompt_display_full_skips_line_truncation` (follow pattern at lines 204-226)
13. Add `test_auto_manager_verbose_stores_preview_full` to `TestAutoManagerQuietMode` in `scripts/tests/test_issue_manager.py`
14. Update `scripts/tests/test_cli.py:483-501` — assert that `preview_full` is correctly threaded from `args.verbose` into `AutoManager`
15. **Run expanded tests**: `python -m pytest scripts/tests/test_subprocess_mocks.py scripts/tests/test_issue_manager.py scripts/tests/test_cli.py -v`

## Impact

- **Priority**: P3 - Verbose mode is only used by power users/debuggers, but when used, truncation is a hard blocker for its purpose
- **Effort**: Small - Likely a single conditional check around existing truncation logic
- **Risk**: Low - Only affects verbose output path; no production behavior change
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-auto`, `verbose`, `captured`

## Session Log
- `/ll:wire-issue` - 2026-04-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:refine-issue` - 2026-04-06T16:20:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29fbacf3-5ab1-4393-bae1-5ddf56f58c33.jsonl`
- `/ll:capture-issue` - 2026-04-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`
- `/ll:confidence-check` - 2026-04-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/14c5639a-6d13-4c2e-bff7-74c8b914dcc3.jsonl`

---

## Status

**Open** | Created: 2026-04-06 | Priority: P3
