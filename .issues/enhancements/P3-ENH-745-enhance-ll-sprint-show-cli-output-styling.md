---
id: ENH-745
type: enhancement
discovered_date: 2026-03-14
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 90
---

# ENH-745: Enhance `ll-sprint show` CLI Output Styling

## Summary

The `ll-sprint show` command's CLI output lacks the rich styling, colors, and formatting used by other commands like `ll-issues list`. This enhancement brings `ll-sprint show` in line with the project's existing CLI output conventions.

## Current Behavior

`ll-sprint show` renders sprint details in plain/minimal text without the styled tables, colored priority indicators, status badges, or rich formatting present in other CLI commands like `ll-issues list`.

## Expected Behavior

`ll-sprint show` uses the same CLI output styling conventions as `ll-issues list` and other commands: colored output, formatted tables, priority/status indicators with consistent visual treatment.

## Success Metrics

- `ll-sprint show` output contains ANSI escape codes (`\033[`) when `_USE_COLOR=True`
- `ll-sprint show` output contains no ANSI escape codes when `_USE_COLOR=False`
- All existing `test_sprint.py` tests pass without regression
- New color-on and color-off tests pass in `test_sprint.py`

## Motivation

Inconsistent CLI output degrades developer experience. Users context-switch between `ll-sprint show` and `ll-issues list` frequently during sprint work; visual inconsistency creates friction and makes the tool feel unpolished.

## Proposed Solution

Audit the output helpers used by `ll-issues list` (and similar commands), then apply the same helpers/patterns to `ll-sprint show`'s rendering logic. Reuse existing style utilities rather than introducing new ones.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint/show.py` — `_cmd_sprint_show` (lines 152–256), `_render_health_summary` (lines 95–149), `_render_dependency_graph` (lines 23–92); currently only imports `terminal_width` from `output.py` — needs `colorize`, `PRIORITY_COLOR`, `TYPE_COLOR` added
- `scripts/little_loops/cli/sprint/_helpers.py` — `_render_execution_plan` (lines 15–137); **two** issue-line formatting sites both need colorizing:
  - `_helpers.py:87` — contention/serialized path: `f"    └── {issue.issue_id}: {title} ({issue.priority})"`
  - `_helpers.py:126` — normal/parallel path: `f"{prefix}{issue.issue_id}: {title} ({issue.priority})"`
  - Currently imports only `terminal_width`; needs `colorize`, `PRIORITY_COLOR`, `TYPE_COLOR` added

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_helpers.py:87` (contention path) and `_helpers.py:126` (parallel path) are both plain f-strings with no color — both must be updated
- `_cmd_sprint_show` function declaration is at `show.py:152` (display logic begins around line 187)
- `colorize()` signature: `def colorize(text: str, code: str) -> str` — returns text unchanged when `_USE_COLOR=False`, otherwise `f"\033[{code}m{text}\033[0m"`
- `PRIORITY_COLOR` keys: `"P0"→"38;5;208;1"`, `"P1"→"38;5;208"`, `"P2"→"33"`, `"P3"→"0"`, `"P4"→"2"`, `"P5"→"2"`
- `TYPE_COLOR` keys: `"BUG"→"38;5;208"`, `"FEAT"→"32"`, `"ENH"→"34"`
- Type prefix extracted via `issue.issue_id.split("-", 1)[0]` (confirmed pattern from `list_cmd.py:130`, `sequence.py:67`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/__init__.py:220-221` — dispatches `args.command == "show"` to `_cmd_sprint_show`; already calls `configure_output(config.cli)` at line 215 so `_USE_COLOR` and color dicts are initialized before `show` runs

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py:63-76` — reference for colorized issue lines: `colorize(issue.priority, PRIORITY_COLOR[priority])` + `colorize(issue.issue_id, TYPE_COLOR[type_prefix])` — apply same pattern to execution plan issue rows in `_render_execution_plan`
- `scripts/little_loops/cli/issues/sequence.py:67-70` — minimal single-line pattern: `f"  [{colored_pri}, ...] {colored_id}: {issue.title}"` — closest match to sprint's `"  ├── FEAT-001: Title (P2)"` format
- `scripts/little_loops/cli/issues/show.py:324-330` — inline color map for status/risk strings (e.g., `{"High": "38;5;208", ...}.get(risk, "0")`) — apply same pattern to health summary prefix (`"OK"`, `"REVIEW"`, `"WARNING"`, `"BLOCKED"`)

### Tests
- `scripts/tests/test_sprint.py` — existing `test_show_includes_dependency_analysis` (line 946) and `TestSprintShowDependencyVisualization` (line 882) use plain-text assertions only — no ANSI coverage; add color assertions following `test_cli_output.py:251-292` patch pattern
- `scripts/tests/test_cli_output.py:251-292` — `TestIssueListNoColor` test class shows the pattern for `_USE_COLOR=False` no-color assertions: `patch.object(output_mod, "_USE_COLOR", False)` then assert `"\033[" not in captured.out`
- `scripts/tests/test_cli.py:882-1054` — render-function unit tests for `_render_execution_plan` — add parallel tests asserting `colorize()` was applied to issue IDs and priorities

### Documentation
- `docs/reference/OUTPUT_STYLING.md` — documents the output styling system; may need a line noting `ll-sprint show` now participates in the color system

## Implementation Steps

1. **Add color imports to `_helpers.py`** — update `scripts/little_loops/cli/sprint/_helpers.py:7` to import `colorize`, `PRIORITY_COLOR`, `TYPE_COLOR` alongside `terminal_width`
2. **Colorize execution plan issue lines** — update **both** issue-line sites in `_render_execution_plan`; extract `issue_type = issue.issue_id.split("-", 1)[0]` before each, then wrap `issue.issue_id` with `colorize(issue.issue_id, TYPE_COLOR.get(issue_type, "0"))` and `issue.priority` with `colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))`:
   - `_helpers.py:87` — contention/serialized path: `f"    └── {issue.issue_id}: {title} ({issue.priority})"`
   - `_helpers.py:126` — normal/parallel path: `f"{prefix}{issue.issue_id}: {title} ({issue.priority})"`
3. **Add color imports to `show.py`** — update `scripts/little_loops/cli/sprint/show.py:9` to import `colorize`, `PRIORITY_COLOR`, `TYPE_COLOR` alongside `terminal_width`
4. **Colorize health summary prefix** — in `_render_health_summary` add an inline color map `{"OK": "32", "REVIEW": "33", "WARNING": "38;5;208", "BLOCKED": "31"}` and wrap the leading word with `colorize()`; follow pattern at `show.py:329-330`
5. **Colorize sprint metadata header** — in `_cmd_sprint_show` at lines 187–197, apply a dim or bold style to the "Sprint:" label line using `colorize("Sprint:", "1")` for consistency with other command headers
6. **Add/update tests** — in `scripts/tests/test_sprint.py`, add a color-on test asserting `"\033[" in captured.out` when `_USE_COLOR=True`, and a no-color test using `patch.object(output_mod, "_USE_COLOR", False)` asserting `"\033[" not in captured.out`; follow pattern from `test_cli_output.py:251-292`

## Impact

- **Priority**: P3 - Developer experience improvement; not blocking
- **Effort**: Small - Reuses existing utilities; no new infrastructure
- **Risk**: Low - Cosmetic/display change only
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Colorizing output in `_render_execution_plan`, `_render_health_summary`, and `_cmd_sprint_show` using existing utilities (`colorize`, `PRIORITY_COLOR`, `TYPE_COLOR`) from `output.py`
- **Out of scope**: Changes to `output.py` or the color system itself — reuse only, no new utilities
- **Out of scope**: Other sprint subcommands (`create`, `edit`, `run`, `list`) — `show` only
- **Out of scope**: Non-terminal output formats (markdown export, JSON) — terminal display only
- **Out of scope**: New color schemes or palette changes — match existing `ll-issues list` styling exactly

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `ux`, `captured`

## Status

**Open** | Created: 2026-03-14 | Priority: P3

---

## Session Log
- `/ll:refine-issue` - 2026-03-17T03:35:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/532865b2-afcc-4542-a851-1511b776f7cd.jsonl`
- `/ll:format-issue` - 2026-03-16T01:20:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4e105a0a-8129-46b0-9889-ec4f193c35ed.jsonl`
- `/ll:confidence-check` - 2026-03-15T22:44:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e049f68d-a6fb-4ec9-8c68-b186e19251c7.jsonl`
- `/ll:refine-issue` - 2026-03-15T22:43:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e049f68d-a6fb-4ec9-8c68-b186e19251c7.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ccc2230-6d69-46a3-8836-f6cde953377c.jsonl`
- `/ll:capture-issue` - 2026-03-14T22:22:31Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/70565b3c-7eae-4789-9be2-378cdc962a48.jsonl`
