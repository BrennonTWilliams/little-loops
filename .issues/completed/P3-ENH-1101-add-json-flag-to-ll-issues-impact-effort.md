---
discovered_date: "2026-04-13"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1101: Add --json flag to ll-issues impact-effort

## Summary

Add a `--json` / `-j` flag to the `ll-issues impact-effort` (alias: `ie`) subcommand so its quadrant data can be consumed programmatically. Output should be a JSON object with four quadrant keys, each containing an array of issue objects matching the fields used by other `ll-issues` JSON outputs.

## Current Behavior

`ll-issues impact-effort` only produces a human-readable ASCII grid. There is no machine-readable output option, making it impossible to consume the quadrant classification in scripts, loops, or downstream tools without parsing ANSI-coloured terminal art.

## Expected Behavior

With `--json` / `-j`, the command prints a JSON object to stdout:

```json
{
  "quick_wins":      [{ "id": "ENH-1101", "title": "...", "effort": 1, "impact": 3, "priority": "P3" }, ...],
  "major_projects":  [...],
  "fill_ins":        [...],
  "thankless_tasks": [...]
}
```

- Field names mirror the quadrant labels used internally (`q_high_low` → `quick_wins`, etc.)
- Per-issue objects include at minimum: `id`, `title`, `priority`, `effort`, `impact`
- The existing ASCII grid is suppressed; the totals line is also omitted
- `--type` filter still applies when combined with `--json`

## Motivation

Several little-loops automation patterns need to know which issues are "quick wins" programmatically — e.g., `ll-auto` could prioritise quick-win issues in its next-batch selection, or a loop could surface the top quick-win to the user. Today that requires parsing the ASCII table, which is fragile and breaks whenever column widths change.

## Proposed Solution

1. Register `--json` / `-j` on the `impact-effort` argparse subparser in `__init__.py` (alongside the existing `--type` arg, lines ~274-277).
2. In `cmd_impact_effort` (`impact_effort.py`), branch on `getattr(args, "json", False)` after the quadrant bucketing loop — reuse the `print_json` helper from `little_loops.cli.output` (same pattern as `count_cmd.py:43-60`).
3. Build the per-issue record dict from `IssueInfo` fields (`issue_id`, `title`, `priority_int`, `effort`, `impact`); infer effort/impact via the existing `_infer_effort` / `_infer_impact` helpers.
4. Return the top-level dict `{"quick_wins": [...], "major_projects": [...], "fill_ins": [...], "thankless_tasks": [...]}`.

## API/Interface

```python
# Argparse registration (issues/__init__.py ~line 276)
ie.add_argument("--json", "-j", action="store_true", help="Output as JSON object")

# JSON output contract
{
  "quick_wins":      list[IssueRecord],   # high impact, low effort
  "major_projects":  list[IssueRecord],   # high impact, high effort
  "fill_ins":        list[IssueRecord],   # low impact, low effort
  "thankless_tasks": list[IssueRecord]    # low impact, high effort
}

# IssueRecord fields (minimum)
{ "id": str, "title": str, "priority": str, "effort": int, "impact": int }
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/impact_effort.py` — add JSON branch to `cmd_impact_effort`
- `scripts/little_loops/cli/issues/__init__.py` — register `--json`/`-j` on `ie` subparser

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` — dispatches to `cmd_impact_effort` (line ~432)

### Similar Patterns
- `scripts/little_loops/cli/issues/count_cmd.py` — `getattr(args, "json", False)` + `print_json`
- `scripts/little_loops/cli/issues/refine_status.py` — `--format json` / `--json` dual-mode
- `scripts/little_loops/cli/issues/list_cmd.py` — `--json` flag on list subcommand

### Tests
- `scripts/tests/test_issues_cli.py` — add test cases for `impact-effort --json` output shape and quadrant assignment

_Wiring pass added by `/ll:wire-issue`:_

Existing tests (lines 729-903, class `TestIssuesCLIImpactEffort`) — all pass without `--json`; no changes needed:
- `test_impact_effort_renders_grid` (729), `test_impact_effort_shows_issue_ids` (756), `test_impact_effort_empty_project` (778), `test_impact_effort_no_ansi_when_no_color` (800), `test_impact_effort_shows_total_count` (829), `test_impact_effort_frontmatter_override` (851), `test_impact_effort_filter_by_type` (879)

New tests to add after line 904 in `TestIssuesCLIImpactEffort` (follow `test_count_json_output` at line 1613 and `test_count_json_short` at line 2328 for pattern):
1. `test_impact_effort_json_output` — `--json` returns valid object with all four quadrant keys; each item has `id`, `title`, `priority`, `effort`, `impact`
2. `test_impact_effort_json_quadrant_correctness` — P5 issue with `effort: 1, impact: 3` frontmatter appears in `data["quick_wins"]`
3. `test_impact_effort_json_type_filter` — `--type BUG --json` emits no FEAT ids in any quadrant list
4. `test_impact_effort_json_short` — `-j` short form parses and returns a dict with the four quadrant keys
5. `test_impact_effort_json_suppresses_ascii` — `"EFFORT"` and `"QUICK WINS"` do NOT appear in stdout when `--json` is passed

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:476-483` — flag table for `impact-effort` subcommand; add `--json` / `-j` row (same format as sibling subcommands)
- `docs/reference/CLI.md:611-612` — usage examples block; add `ll-issues impact-effort --json` (and `--json --type BUG`) lines
- `README.md:417-418` — usage examples near `sequence --json`; add `ll-issues impact-effort --json` example line

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact insertion points:**
- `__init__.py:277` — Insert `ie.add_argument("--json", "-j", action="store_true", help="Output as JSON object")` before `add_config_arg(ie)` (after the `--type` arg at line 276)
- `impact_effort.py:8` — Current output import is `TYPE_COLOR, colorize, terminal_width`; add `print_json` to this same import
- `impact_effort.py:166` — `cmd_impact_effort(config: BRConfig, args: argparse.Namespace) -> int` function definition
- `impact_effort.py:194-211` — Quadrant bucketing loop; `effort`/`impact` are local loop variables (lines 200-201) but only `issue` objects are appended to the four `q_*` lists — they are NOT preserved. The JSON branch must re-call `_infer_effort(issue)`/`_infer_impact(issue)` for each item in each quadrant list (cheap, no side effects)
- `impact_effort.py:213` — `print(_render_grid(...))` — insert JSON branch BEFORE this line (between bucketing end 211 and render 213); return early to skip ASCII rendering and the summary count at lines 215-216

**Per-issue record dict** (follow `list_cmd.py:96-111` pattern — `"id"` maps from `issue.issue_id`):
```python
{"id": issue.issue_id, "title": issue.title, "priority": issue.priority, "effort": _infer_effort(issue), "impact": _infer_impact(issue)}
```

**Confirmed dispatch** (`__init__.py:432-433`): `if args.command == "impact-effort": return cmd_impact_effort(config, args)` — no change needed.

**Test fixtures** (`conftest.py:56-162`):
- `temp_project_dir` (line 56): yields a `Path` to a temp dir with `.ll/` already created
- `sample_config` (line 66): `dict[str, Any]` with `project`, `issues`, `parallel` keys
- `issues_dir` (line 125): creates `.issues/` subdirs with 5 sample issues (BUG-001 P0, BUG-002 P1, BUG-003 P2, FEAT-001 P1, FEAT-002 P2)
- Config written inside each test: `config_path.write_text(json.dumps(sample_config))`
- Call pattern: `patch.object(sys, "argv", ["ll-issues", "impact-effort", "--json", "--config", str(temp_project_dir)])`

## Implementation Steps

1. Add `--json`/`-j` to the `ie` argparse subparser in `__init__.py`
2. In `cmd_impact_effort`, after building the four quadrant lists, check `args.json` and emit JSON via `print_json`; return early to skip ASCII rendering
3. Build per-issue dicts using `_infer_effort`/`_infer_impact` helpers
4. Add tests: JSON output shape, quadrant correctness, `--type` + `--json` combo
5. Run `pytest scripts/tests/test_issues_cli.py` and `ruff check`

### Codebase Research Findings

_Added by `/ll:refine-issue` — confirmed exact locations:_

1. **`__init__.py:277`** — Insert before `add_config_arg(ie)`:
   ```python
   ie.add_argument("--json", "-j", action="store_true", help="Output as JSON object")
   ```

2. **`impact_effort.py:8`** — Add `print_json` to the existing `little_loops.cli.output` import (alongside `TYPE_COLOR, colorize, terminal_width`)

3. **`impact_effort.py:212`** (between bucketing end and `print(_render_grid(...))`) — Insert JSON branch:
   ```python
   if getattr(args, "json", False):
       def _rec(issue: IssueInfo) -> dict:
           return {
               "id": issue.issue_id,
               "title": issue.title,
               "priority": issue.priority,
               "effort": _infer_effort(issue),
               "impact": _infer_impact(issue),
           }
       print_json({
           "quick_wins":      [_rec(i) for i in q_high_low],
           "major_projects":  [_rec(i) for i in q_high_high],
           "fill_ins":        [_rec(i) for i in q_low_low],
           "thankless_tasks": [_rec(i) for i in q_low_high],
       })
       return 0
   ```
   Re-calling `_infer_effort`/`_infer_impact` is correct — the bucketing loop only appends `issue` objects to the quadrant lists, not the computed scores.

4. **`scripts/tests/test_issues_cli.py`** — Model tests after `test_count_json_output` (line 1613) and `test_list_json_output` (line 282). Test class: find or create a `TestImpactEffortCommand` class. Use `temp_project_dir`, `sample_config`, `issues_dir` fixtures (`conftest.py:56-162`). Cover:
   - JSON output is a valid object with all four quadrant keys
   - Each item has `id`, `title`, `priority`, `effort`, `impact` fields
   - `--type BUG` + `--json` filters correctly
   - `-j` short form works (see `test_count_json_short`, line 2328)

5. **Run**: `python -m pytest scripts/tests/test_issues_cli.py -k "impact" -v && ruff check scripts/`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/CLI.md:476-483` — add `--json` / `-j` row to the `impact-effort` flags table
7. Update `docs/reference/CLI.md:611-612` — add `ll-issues impact-effort --json` usage example lines
8. Update `README.md:417-418` — add `ll-issues impact-effort --json` example near the `sequence --json` example

## Impact

- **Priority**: P3 - Useful utility upgrade; not blocking any current workflow
- **Effort**: Small - Pattern is well-established in the codebase; ~40 lines of new code
- **Risk**: Low - Additive flag; no change to existing ASCII path
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `captured`

## Resolution

**Status**: Completed
**Completed**: 2026-04-13

### Changes Made
- `scripts/little_loops/cli/issues/__init__.py` — registered `--json`/`-j` on `ie` subparser
- `scripts/little_loops/cli/issues/impact_effort.py` — added `print_json` import; added JSON branch before ASCII render
- `scripts/tests/test_issues_cli.py` — added 5 new tests (output shape, quadrant correctness, type filter, short form, ASCII suppression)
- `docs/reference/CLI.md` — added `--json`/`-j` row to flag table; added usage examples
- `README.md` — added `ll-issues impact-effort --json` example

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-13T20:49:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad3220fd-9de2-426d-b1a3-53cd1823d326.jsonl`
- `/ll:ready-issue` - 2026-04-13T20:46:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2922f7a8-d5bf-49f5-888b-305c20519a80.jsonl`
- `/ll:confidence-check` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a579a36-3283-4cf4-997b-200ed0e4e3ae.jsonl`
- `/ll:wire-issue` - 2026-04-13T20:40:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36930716-95c2-49f9-94bd-120b2bc412c6.jsonl`
- `/ll:refine-issue` - 2026-04-13T20:36:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a5b8b1ea-7349-43fb-9c79-2c30e427439d.jsonl`
- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/500f1193-bcd3-4daf-9ad8-0b97b6bb5d4a.jsonl`
- `/ll:manage-issue` - 2026-04-13T00:00:00Z - implementation complete

---

**Completed** | Created: 2026-04-13 | Priority: P3
