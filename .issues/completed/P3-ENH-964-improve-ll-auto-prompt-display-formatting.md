---
discovered_date: 2026-04-06
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 72
---

# ENH-964: Improve ll-auto Prompt Display Formatting

## Summary

Improve the formatting and display of the prompt passed to the coding agent in the `ll-auto` CLI output, making it easier to read and debug what instructions are being sent.

## Current Behavior

The prompt sent to the coding agent is displayed in the `ll-auto` CLI output without visual structure — it appears as a dense block of text that is difficult to scan, and may be truncated or interleaved with other log output in ways that make it hard to understand what was actually sent to the agent.

## Expected Behavior

The prompt display in `ll-auto` output should be clearly delineated, visually formatted, and easy to read at a glance — with clear start/end markers, consistent indentation or truncation behavior, and separation from surrounding log lines so users can quickly inspect what the agent received.

## Motivation

When debugging `ll-auto` runs or reviewing what instructions were sent to the coding agent, the current raw prompt output is hard to read. Better formatting reduces debugging friction and improves transparency into what the automation is doing. This is especially valuable for users tuning prompts or investigating why an agent behaved unexpectedly.

## Proposed Solution

The single change point is `scripts/little_loops/issue_manager.py:116` inside `run_claude_command()`:

```python
# Current (produces dense repr-escaped single line):
logger.info(f"Running: claude --dangerously-skip-permissions -p {command!r}")
```

Replace with a formatted display modeled after the ll-loop prompt preview pattern at `scripts/little_loops/cli/loop/_helpers.py:390-409`:

```python
# Replace the single logger.info line with structured display:
from scripts.little_loops.cli.output import terminal_width

lines = command.strip().splitlines()
line_count = len(lines)
tw = terminal_width()
max_line = tw - 4
logger.info(f"Running: claude --dangerously-skip-permissions -p ({line_count} lines)")
show_count = line_count if logger.verbose else min(5, line_count)  # or a separate flag
for line in lines[:show_count]:
    display = line[:max_line] + "..." if len(line) > max_line else line
    logger.info(f"  {display}")
if line_count > show_count:
    logger.info(f"  ... ({line_count - show_count} more lines)")
```

Design decisions:
- Default (non-verbose): show `(N lines)` count + first 5 lines + `... (N more lines)` — sufficient to identify which skill was invoked without flooding output
- `--verbose`: show all lines (or use a dedicated `--show-prompt` flag if even `--verbose` is too much)
- No `repr()` / `!r` — display actual newline-separated lines
- Use `terminal_width()` from `cli/output.py:16` for per-line truncation
- `Logger.header()` at `logger.py:106-113` can provide the `---` delimiter if desired

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py:116` — the single line that displays the prompt via `logger.info` with `!r` repr formatting; this is the only change required
- `scripts/little_loops/logger.py:106` — optionally add a `prompt_display(command, verbose)` method alongside the existing `header()` method if logic is complex enough to abstract

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:337-344` — Phase 1 call site: `run_claude_command(_ready_cmd, logger, ...)` (ready-issue phase)
- `scripts/little_loops/issue_manager.py:564-573` — Phase 2 call site: `run_claude_command(_initial_cmd, logger, ...)` (manage-issue phase)
- `scripts/little_loops/issue_manager.py:174` — `run_with_continuation()` also routes through `run_claude_command()`, so continuation rounds will also get the new formatting automatically
- `scripts/little_loops/cli/output.py:16-24` — `terminal_width()` and `wrap_text()` are available for per-line truncation; import as needed

### Similar Patterns
- `scripts/little_loops/cli/loop/_helpers.py:390-409` — ll-loop's `run_foreground()` prompt display: shows `(N lines)` badge, first 5 lines by default, all lines in `--verbose`, `... (N more lines)` indicator — **follow this pattern exactly**
- `scripts/little_loops/cli/loop/_helpers.py:162-176` — dry-run 3-line preview with ` ...` suffix; secondary reference
- `scripts/little_loops/logger.py:106-113` — `Logger.header()` — existing `===` block primitive usable for delimiters
- `scripts/little_loops/issue_manager.py:964-967` — inline 60-char truncation pattern already used in summary output

### Tests
- `scripts/tests/test_issue_manager.py` — primary test file; `TestAutoManagerQuietMode` (~line 725) and streaming tests (~line 851) are the most relevant test classes; add assertions on prompt display format here
- `scripts/tests/test_logger.py:381-446` — `Logger.header()` test pattern: use `capsys.readouterr()` and assert line count and content; follow this pattern for any new `Logger` method
- `scripts/tests/test_cli_output.py` — test pattern for `terminal_width()` / `colorize()` utilities

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_subprocess_mocks.py:TestRunClaudeCommand` (lines 22–202) — **this file is NOT in the known tests list above**; it has 4 tests that call `issue_manager.run_claude_command` with a `MagicMock(spec=Logger)` logger and assert only on subprocess args and return value — never on `logger.info`; this is the primary place to add new format assertions, alongside `test_issue_manager.py:TestRunClaudeCommand`; use `mock_logger.info.call_args_list` to assert on the `(N lines)` header, indented first line, and `... (N more)` trailer
- `scripts/tests/test_issue_manager.py:TestRunClaudeCommand` (~line 842) — same gap: **zero assertions on `logger.info` call args**; add assertions here for the streaming-enabled path specifically

### Documentation
- `docs/reference/CLI.md:250` — documents that `--verbose` "shows full prompt text and more output lines"; update if default (non-verbose) behavior now shows a prompt preview
- `docs/reference/OUTPUT_STYLING.md` — documents all CLI output styling patterns; update if a new `Logger` method is added

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (flags table, lines 38–55) — **`--verbose` is entirely absent from the ll-auto flags table**; the flag exists at `cli/auto.py:59-63` but has no documentation entry; this issue changes its visible effect (partial prompt preview in non-verbose vs full prompt in verbose), so the flag must be added to the table — add a row: `| \`--verbose\` | \`-v\` | Show full prompt text and all output lines (default: abbreviated) | \`ll-auto\` |`
- **Correction**: `docs/reference/CLI.md:250` (referenced in this issue as the `--verbose` description to update) is in the `ll-loop run` section, **not** the `ll-auto` section — `ll-auto` has no existing `--verbose` documentation at all
- `docs/reference/API.md:2136-2146` — Logger methods table lists all public methods (`info`, `debug`, `success`, `warning`, `error`, `timing`, `header`); if `Logger.prompt_display()` is added as a public method, a new row is required here; also update the code example at `API.md:2114-2122`

### Configuration
- N/A — no config changes needed; `--verbose` flag already exists at `cli/auto.py:59-63`

### Architecture Note

_Wiring pass added by `/ll:wire-issue`:_

There are **two distinct `run_claude_command` functions** in the codebase — only one is the target of this issue:

- `scripts/little_loops/issue_manager.py:94` — the logger-aware wrapper being changed; takes `Logger` as second argument; used by `ll-auto` and `ll-sprint` via `run_with_continuation()`
- `scripts/little_loops/subprocess_utils.py:62` — the low-level subprocess invoker with no `Logger`; used by `scripts/little_loops/fsm/runners.py:94` (ll-loop FSM) and `scripts/little_loops/parallel/worker_pool.py:626` (`_run_claude_command` method)

The `fsm/runners.py` and `worker_pool.py` callers use the `subprocess_utils` version and are **not affected** by this change — they do not log the prompt command text at all before execution.

## Implementation Steps

1. **Modify `run_claude_command()` at `issue_manager.py:116`**: replace the single `logger.info(f"Running: ... {command!r}")` line with a multi-line formatted display — show `(N lines)` count, first 5 lines with per-line truncation at `terminal_width() - 4`, and a `... (N more lines)` trailer when truncated; show all lines when `logger.verbose` is true
2. **Import `terminal_width`** from `scripts/little_loops/cli/output.py:16` at the top of `issue_manager.py` — **this import does NOT currently exist** in `issue_manager.py`; add `from little_loops.cli.output import terminal_width` to the imports block
3. **Optionally add `Logger.prompt_display(command)`** at `logger.py:106` if the display logic warrants abstraction — follow the existing `header()` method structure at `logger.py:106-113`
4. **Add tests in `test_issue_manager.py`** following the `capsys.readouterr()` pattern from `test_logger.py:381-446`; assert: `(N lines)` appears, first line of prompt appears, `... (N more lines)` appears when prompt is long, full prompt appears in verbose mode
5. **Update `docs/reference/CLI.md:250`** if the `--verbose` prompt behavior description changes
6. **Verify in terminal**: run `ll-auto` against a test issue and confirm the prompt display is readable, delineated from surrounding log lines, and the `--verbose` mode shows the complete prompt

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Add `--verbose` to `docs/reference/CLI.md` flags table** (lines 38–55) — `--verbose`/`-v` is entirely absent from the ll-auto flags table despite existing at `cli/auto.py:59-63`; add row with description covering the new abbreviated vs full-prompt behavior
8. **Update `docs/reference/API.md:2136-2146`** — if `Logger.prompt_display()` is added as a public method, add a row to the methods table and update the code example at `API.md:2114-2122`
9. **Assert on `logger.info.call_args_list` in `test_subprocess_mocks.py:TestRunClaudeCommand`** (lines 22–202) — the primary unit test class for `run_claude_command`; add at least two new methods: default-path (abbreviated: `(N lines)` header, first line visible, `... (N more)` trailer) and verbose-path (`logger.verbose = True`, all lines visible); also add matching tests in `test_issue_manager.py:TestRunClaudeCommand:~842`

## Scope Boundaries

- Display/formatting changes only — not changes to prompt content or agent behavior
- Should not add verbose output by default that significantly increases log noise

## Impact

- **Priority**: P3 - Developer experience improvement; doesn't block core functionality
- **Effort**: Small - Localized display change in one or two files
- **Risk**: Low - Output formatting only, no behavioral change
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `ll-auto`, `ux`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-04-06T15:15:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef062685-c5d4-4cf0-9d98-3192f4daee5f.jsonl`
- `/ll:refine-issue` - 2026-04-06T15:00:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8815b708-27f4-4123-8e08-59ca7fade218.jsonl`
- `/ll:capture-issue` - 2026-04-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/50b40e21-0da1-463a-8746-aa62a9c2590b.jsonl`
- `/ll:wire-issue` - 2026-04-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5346cd1d-cff6-400f-8cb5-496b5c442901.jsonl`
- `/ll:confidence-check` - 2026-04-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05cbe6ce-f48f-46a4-bc0d-de973bc80f17.jsonl`

---

## Resolution

- **Status**: Completed
- **Date**: 2026-04-06
- **Changes**:
  - `scripts/little_loops/issue_manager.py`: replaced single-line `{command!r}` display in `run_claude_command()` with structured multi-line output — shows `(N lines)` count header, first 5 lines with per-line truncation at `terminal_width() - 4`, and `... (N more lines)` trailer; lazy-imports `terminal_width` from `little_loops.cli.output` to avoid circular import
  - `scripts/tests/test_subprocess_mocks.py`: added 3 new tests in `TestRunClaudeCommand` asserting on `logger.info.call_args_list` for abbreviated format, short-command (no trailer), and long-line truncation
  - `docs/reference/CLI.md`: added `--verbose` / `-v` row to the ll-auto flags table

## Session Log
- `/ll:manage-issue` - 2026-04-06T00:00:00Z - improvement complete

---

## Status

**Completed** | Created: 2026-04-06 | Completed: 2026-04-06 | Priority: P3
