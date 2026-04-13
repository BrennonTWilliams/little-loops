---
discovered_date: "2026-04-13"
discovered_by: capture-issue
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

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `--json`/`-j` to the `ie` argparse subparser in `__init__.py`
2. In `cmd_impact_effort`, after building the four quadrant lists, check `args.json` and emit JSON via `print_json`; return early to skip ASCII rendering
3. Build per-issue dicts using `_infer_effort`/`_infer_impact` helpers
4. Add tests: JSON output shape, quadrant correctness, `--type` + `--json` combo
5. Run `pytest scripts/tests/test_issues_cli.py` and `ruff check`

## Impact

- **Priority**: P3 - Useful utility upgrade; not blocking any current workflow
- **Effort**: Small - Pattern is well-established in the codebase; ~40 lines of new code
- **Risk**: Low - Additive flag; no change to existing ASCII path
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/500f1193-bcd3-4daf-9ad8-0b97b6bb5d4a.jsonl`

---

**Open** | Created: 2026-04-13 | Priority: P3
