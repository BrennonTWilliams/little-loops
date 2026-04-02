---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# ENH-923: Enhance `ll-sprint show` Detail and Output Quality

## Summary

Improve the `ll-sprint show` command with richer detail and better output formatting: add a readiness/confidence table per issue, omit empty descriptions, use human-friendly timestamps, show sprint composition breakdown, surface sprint run state from `.sprint-state.json`, use lighter visual separators, widen title truncation, add a `--json` flag, and display file paths for each issue.

## Current Behavior

`ll-sprint show` displays sprint metadata, an execution plan, and issue lists, but:

- Shows `Description: (none)` for empty descriptions, adding noise.
- Uses microsecond-precision ISO 8601 timestamps (e.g., `2026-04-02T19:49:32.123456`) which are hard to scan.
- Does not show readiness or outcome confidence scores per issue.
- No composition breakdown (type/priority distribution).
- Does not surface previous run state even when `.sprint-state.json` exists.
- Uses heavy full-width `===` banners as section separators.
- Truncates titles at ~45 characters, clipping useful context.
- No `--json` output flag (unlike `ll-sprint list`).
- Does not show the file path for each issue.

## Expected Behavior

1. **Issue table with scores** — Each issue in the execution plan shows readiness and outcome confidence scores, styled consistently with `ll-issues list` output.
2. **Omit empty description** — Only render `Description:` when a value exists.
3. **Human-friendly timestamps** — `Created: 2026-04-02 19:49 UTC (today)` or relative like `2h ago`.
4. **Composition line** — After health summary: `Composition: 4 ENH  |  P3: 2, P4: 2`
5. **Sprint run state** — If `.sprint-state.json` exists, show: `Last run: 2026-04-01 — 3/4 completed, 1 failed (ENH-921)`
6. **Lighter separators** — Replace `===` banners with: `── Execution Plan (4 issues, 1 wave) ──────────────────`
7. **Wider title truncation** — Bump to ~60 chars or calculate dynamically from terminal width minus fixed-width prefix/suffix.
8. **`--json` flag** — Structured JSON output for scripting, matching the pattern from `ll-sprint list --json`.
9. **Issue file paths** — Show file path below each issue entry:
   ```
   ├── ENH-919: Wire EventBus Emission into Issue Lifecycle (P3)
   │   .issues/enhancements/P3-ENH-919-wire-eventbus-issue-lifecycle.md
   ```

## Motivation

`ll-sprint show` is the single entry point for understanding a sprint's full status. Currently it requires users to cross-reference multiple commands to get readiness scores, run history, or file locations. Consolidating this information and aligning the visual style with other `ll-` CLI commands makes sprint review faster and reduces context-switching.

## Proposed Solution

Modify the sprint `show` subcommand and its helper renderers. The sprint CLI is split into a package at `scripts/little_loops/cli/sprint/` with dedicated modules.

### Key Modifications

1. **`show.py:_cmd_sprint_show()`** (line 154) — Main handler. Add description omission logic (line 190), human-friendly timestamp (line 191), composition breakdown after health summary (line 227), and sprint run state from `.sprint-state.json`.
2. **`_helpers.py:_render_execution_plan()`** (line 15) — Replace `"=" * width` banners (lines 58-61) with `──` style separators. Increase title truncation from 45 chars (lines 83, 129) to dynamic width. Add issue file paths and readiness/confidence scores per issue.
3. **`show.py:_render_dependency_graph()`** (line 23) — Replace `"=" * width` banners (lines 49-51) with lighter separators.
4. **`__init__.py`** (line 145-149) — Add `--json` flag to `show_parser`, matching the pattern from `list_parser` at line 142.
5. **`show.py`** — Add JSON output path using `print_json()` from `cli/output.py:97`.

### Reusable Utilities

- **`cli/output.py:terminal_width()`** (line 16) — Already wraps `shutil.get_terminal_size()`, used in `_helpers.py`. Use for dynamic title truncation.
- **`cli/output.py:colorize()`** (line 90) — Already used throughout sprint rendering.
- **`cli/output.py:print_json()`** (line 97) — Used by `_cmd_sprint_list` for `--json` output.
- **`cli/loop/lifecycle.py:_format_relative_time()`** (line 22) — Formats seconds as `"3m ago"`, `"2h ago"`, etc. Should be moved to a shared location (e.g., `cli/output.py`) or imported directly.
- **`IssueInfo.confidence_score` / `IssueInfo.outcome_confidence`** — Already parsed by `issue_parser.py` (lines 235-236). Available on objects returned by `SprintManager.load_issue_infos()`.
- **`SprintState.from_dict()`** (sprint.py:103) and `_load_sprint_state()` (run.py:49) — Read `.sprint-state.json` with fields: `sprint_name`, `completed_issues`, `failed_issues`, `started_at`, `last_checkpoint`.
- **`cli/issues/refine_status.py`** — Table rendering with readiness/confidence columns. Column definitions at lines 67-71 show width and label conventions.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint/show.py` — `_cmd_sprint_show()` handler (line 154): timestamp formatting, description omission, composition, run state, `--json` gate
- `scripts/little_loops/cli/sprint/_helpers.py` — `_render_execution_plan()` (line 15): separator style, title truncation width, issue file paths, readiness/confidence scores per issue
- `scripts/little_loops/cli/sprint/__init__.py` — `show_parser` definition (line 145): add `--json` argument
- `scripts/little_loops/cli/output.py` — Consider adding `format_relative_time()` as shared utility (currently only in `cli/loop/lifecycle.py:22`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/__init__.py:20-23` — imports `_cmd_sprint_show`, `_render_dependency_graph`, `_render_health_summary` from `show.py`
- `scripts/little_loops/cli/sprint/__init__.py:8` — imports `_render_execution_plan` from `_helpers.py`
- `scripts/little_loops/cli/sprint/manage.py:10` — also imports `_render_execution_plan` from `_helpers.py`
- `scripts/tests/test_sprint.py` — tests `_cmd_sprint_show` (lines 946, 969, 984, 1009, 1033), `_render_execution_plan`, `_render_health_summary`

### Similar Patterns
- `scripts/little_loops/cli/sprint/manage.py:16-52` — `_cmd_sprint_list()` with `--json` flag: check `getattr(args, "json", False)`, early return with `print_json([...])`. Follow this exact pattern for `show`.
- `scripts/little_loops/cli/issues/refine_status.py` — Table rendering with readiness/confidence score columns, dynamic column elision based on terminal width
- `scripts/little_loops/cli/loop/lifecycle.py:22-36` — `_format_relative_time()` converting seconds to human-friendly strings

### Tests
- `scripts/tests/test_sprint.py` (1897 lines) — Existing tests:
  - `test_show_includes_dependency_analysis` (line 946)
  - `test_show_skip_analysis_flag` (line 969)
  - `test_show_color_output` (line 991)
  - `test_show_no_color_output` (line 1015)
  - Add new tests for: `--json` output, omitted empty description, human-friendly timestamps, composition line, run state display, wider titles, issue file paths, readiness/confidence scores

### Documentation
- N/A (CLI output changes, no doc updates needed)

### Configuration
- N/A (no new config keys needed)

## Implementation Steps

1. **Move `_format_relative_time()` to shared location** — Relocate from `cli/loop/lifecycle.py:22-36` to `cli/output.py` so both loop and sprint modules can use it. Update the import in `lifecycle.py`.

2. **Replace separators in `_helpers.py` and `show.py`** — Change `"=" * width` (at `_helpers.py:58-61` and `show.py:49-51`) to `── Title (context) ──...` style. Pattern: `f"── {title} {'─' * (width - len(title) - 4)}"`.

3. **Increase title truncation** — In `_helpers.py` lines 83 and 129, replace hardcoded `45` with dynamic calculation: `terminal_width() - 30` (accounting for prefix, priority, and padding). Minimum floor of 45.

4. **Omit empty descriptions** — In `show.py:190`, guard with `if sprint.description: print(f"Description: {sprint.description}")`.

5. **Human-friendly timestamps** — In `show.py:191`, parse `sprint.created` ISO string, format as `"2026-04-02 19:49 UTC"` with relative suffix using the shared `_format_relative_time()`.

6. **Add composition breakdown** — After health summary (`show.py:227`), compute type/priority distribution from `issue_infos` and print: `Composition: 4 ENH | P3: 2, P4: 2`.

7. **Add sprint run state** — In `show.py`, import `_get_sprint_state_file` and `SprintState.from_dict()`. If `.sprint-state.json` exists, load and display: `Last run: <date> — N/M completed, K failed (IDs)`.

8. **Add readiness/confidence scores per issue** — In `_helpers.py:_render_execution_plan()`, access `issue.confidence_score` and `issue.outcome_confidence` from the `IssueInfo` objects. Display inline: `ENH-919: Title (P3) [ready: 85, conf: 72]`.

9. **Add issue file paths** — In `_helpers.py`, after each issue line, add `│   <issue.path>` using the `IssueInfo.path` attribute.

10. **Add `--json` flag** — In `__init__.py` at line 149, add `show_parser.add_argument("-j", "--json", ...)`. In `show.py:_cmd_sprint_show()`, add early `--json` branch following `_cmd_sprint_list` pattern (`manage.py:21-37`): build dict with sprint metadata, issues, waves, scores, state; output via `print_json()`.

11. **Update tests** — In `scripts/tests/test_sprint.py`, add tests for: omitted empty description, human-friendly timestamp format, composition line, `--json` output structure, lighter separators, wider titles, file path display, readiness/confidence display, run state display.

## Success Metrics

- All 9 improvements are visible in `ll-sprint show` output
- `--json` flag produces valid JSON matching the displayed information
- Existing `test_sprint.py` tests pass without regression
- New tests cover each added feature

## Scope Boundaries

- Does not change `ll-sprint list` output (already styled)
- Does not modify sprint execution logic or wave planning
- Does not add interactive features to `show`

## Impact

- **Priority**: P3 - Quality-of-life improvement for sprint review workflow
- **Effort**: Medium - 9 discrete changes to rendering logic, but mostly additive
- **Risk**: Low - Output-only changes, no execution logic modified
- **Breaking Change**: No (additive only; `--json` is opt-in)

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | CLI module structure and output conventions |
| `docs/reference/API.md` | Sprint manager API and state file format |

## Labels

`enhancement`, `cli`, `sprint`, `captured`

## Session Log
- `/ll:refine-issue` - 2026-04-02T22:09:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/290105ed-73d3-4d92-b9c4-5473c65fa704.jsonl`
- `/ll:capture-issue` - 2026-04-02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2d0784e-0b23-40cf-bd8f-79c2a103fa18.jsonl`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P3
