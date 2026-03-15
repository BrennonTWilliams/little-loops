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

## Motivation

Inconsistent CLI output degrades developer experience. Users context-switch between `ll-sprint show` and `ll-issues list` frequently during sprint work; visual inconsistency creates friction and makes the tool feel unpolished.

## Proposed Solution

Audit the output helpers used by `ll-issues list` (and similar commands), then apply the same helpers/patterns to `ll-sprint show`'s rendering logic. Reuse existing style utilities rather than introducing new ones.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint/show.py` — `_cmd_sprint_show` (lines 187–255), `_render_health_summary` (lines 95–149), `_render_dependency_graph` (lines 23–92); currently only imports `terminal_width` from `output.py` — needs `colorize`, `PRIORITY_COLOR`, `TYPE_COLOR` added
- `scripts/little_loops/cli/sprint/_helpers.py` — `_render_execution_plan` (lines 15–137); issue line at line 126 formats `f"{prefix}{issue.issue_id}: {title} ({issue.priority})"` with no color wrapping; needs `colorize`, `PRIORITY_COLOR`, `TYPE_COLOR` imported

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
2. **Colorize execution plan issue lines** — in `_render_execution_plan` at `_helpers.py:126`, wrap `issue.issue_id` with `colorize(issue.issue_id, TYPE_COLOR.get(issue_type, "0"))` and `issue.priority` with `colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))`; extract `issue_type = issue.issue_id.split("-", 1)[0]` before the format string
3. **Add color imports to `show.py`** — update `scripts/little_loops/cli/sprint/show.py:9` to import `colorize`, `PRIORITY_COLOR`, `TYPE_COLOR` alongside `terminal_width`
4. **Colorize health summary prefix** — in `_render_health_summary` add an inline color map `{"OK": "32", "REVIEW": "33", "WARNING": "38;5;208", "BLOCKED": "31"}` and wrap the leading word with `colorize()`; follow pattern at `show.py:329-330`
5. **Colorize sprint metadata header** — in `_cmd_sprint_show` at lines 187–197, apply a dim or bold style to the "Sprint:" label line using `colorize("Sprint:", "1")` for consistency with other command headers
6. **Add/update tests** — in `scripts/tests/test_sprint.py`, add a color-on test asserting `"\033[" in captured.out` when `_USE_COLOR=True`, and a no-color test using `patch.object(output_mod, "_USE_COLOR", False)` asserting `"\033[" not in captured.out`; follow pattern from `test_cli_output.py:251-292`

## Impact

- **Priority**: P3 - Developer experience improvement; not blocking
- **Effort**: Small - Reuses existing utilities; no new infrastructure
- **Risk**: Low - Cosmetic/display change only
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `ux`, `captured`

## Status

**Open** | Created: 2026-03-14 | Priority: P3

---

## Session Log
- `/ll:confidence-check` - 2026-03-15T22:44:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e049f68d-a6fb-4ec9-8c68-b186e19251c7.jsonl`
- `/ll:refine-issue` - 2026-03-15T22:43:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e049f68d-a6fb-4ec9-8c68-b186e19251c7.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ccc2230-6d69-46a3-8836-f6cde953377c.jsonl`
- `/ll:capture-issue` - 2026-03-14T22:22:31Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/70565b3c-7eae-4789-9be2-378cdc962a48.jsonl`
