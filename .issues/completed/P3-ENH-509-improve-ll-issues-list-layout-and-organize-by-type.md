---
discovered_date: 2026-02-26
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# ENH-509: Improve ll-issues list layout and organize by type

## Summary

The `ll-issues list` subcommand currently outputs a flat, unsorted list of all active issues with minimal formatting. Improve the layout and formatting to group issues by type (BUG, FEAT, ENH), add visual structure (headers, separators, counts), and make the output easier to scan at a glance.

## Current Behavior

`ll-issues list` outputs a flat list sorted by priority then ID, with each line showing the filename and title:

```
P3-ENH-491-use-issue-sections-json-in-ll-sync-pull.md  Use issue-sections.json in ll-sync pull
P3-ENH-493-rewrite-skill-descriptions-as-trigger-documents.md  Rewrite Skill Descriptions as Trigger Documents
P3-FEAT-487-implement-ll-loop-run-background-daemon-mode.md  Implement `ll-loop run --background` daemon mode
...
```

No grouping by type, no summary counts, and the full filename is redundant with the information already visible in the ID and title.

## Expected Behavior

Output should be organized by issue type with clear section headers, cleaner per-line formatting, and a summary. Example:

```
Enhancements (14)
  P3  ENH-491  Use issue-sections.json in ll-sync pull
  P3  ENH-493  Rewrite Skill Descriptions as Trigger Documents
  P3  ENH-495  Structured Handoff with Anchored Iterative Summarization
  ...

Features (5)
  P3  FEAT-487  Implement ll-loop run --background daemon mode
  P3  FEAT-489  Add diff and close subcommands to ll-sync
  ...

Bugs (0)

Total: 21 active issues
```

## Motivation

When scanning the backlog, users want to quickly see how many issues exist per type and find issues within a category. With 20+ active issues, users must visually parse every line to distinguish features from enhancements at a glance, and the full filename adds noise without value.

## Proposed Solution

Modify the `list` subcommand to group issues by type and add `--flat` for backward compatibility:

1. Parse each issue's type from `issue.issue_id.split("-")[0]` (already used at `issue_parser.py:544`)
2. Group issues into ordered buckets by type: `{"BUG": [], "FEAT": [], "ENH": []}`
3. Print each group with a header showing type name and count (skip empty groups or show `(0)`)
4. Format each line as: `  P[n]  TYPE-NNN  Title` (two-space indent, priority left-justified)
5. Print a total count at the bottom
6. Add `--flat` flag that preserves current behavior for scripting

**Key correction**: The actual files are `list_cmd.py` and `__init__.py` inside `scripts/little_loops/cli/issues/`, not a monolithic `ll_issues.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list()` function (lines 12–36); the entire 25-line implementation to be replaced with grouped output logic
- `scripts/little_loops/cli/issues/__init__.py` — `list` subparser registration (lines 48–55); add `--flat` flag here: `ls.add_argument("--flat", action="store_true", help="Output flat list (original format) for scripting")`

### Dependent Files (Callers/Importers)
- N/A — CLI entry point, invoked only via `main_issues()` dispatch at `__init__.py:77-78`

### Similar Patterns

#### Section-header output with counts (closest match)
- `scripts/little_loops/issue_history/formatting.py:29-58` — `format_summary_text()` uses `list[str]` buffer + `"\n".join(lines)`, section headers like `"By Type:"` + `"-" * 7` separator, two-space-indented items with fixed-width format strings

#### Grouping / bucketing by type
- `scripts/little_loops/issue_history/formatting.py:402-410` — inline dict bucketing: `by_agent: dict[str, list[...]] = {}` + `for k in sorted(by_agent): ...`
- `scripts/little_loops/issue_history/summary.py:28-51` — `type_counts: dict[str, int] = {}` with `type_counts.get(key, 0) + 1`

#### Type prefix extraction from `IssueInfo`
- `scripts/little_loops/issue_parser.py:544` — `prefix = info.issue_id.split("-", 1)[0]` — the canonical way to get type prefix from an `IssueInfo` object

#### Slug display from filename
- `scripts/little_loops/cli/issues/impact_effort.py:37-46` — `name.split("-", 3)` gives `[priority, type, number, description]`

### Tests
- `scripts/tests/test_issues_cli.py` — primary test file; uses `capsys` + `patch(sys.argv)` + `main_issues()` pattern (see `TestIssuesCLIList`); assertions use `"keyword" in captured.out` (not exact string matching)
- Note: `conftest.py` `issues_dir` fixture (lines 125–157) has BUG and FEAT sample files but no ENH — add an ENH sample issue to the fixture or create a local fixture for grouped-output tests

### Documentation
- `README.md` — lines 345–355 show `ll-issues list` usage examples; update if `--flat` flag is added

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Current `cmd_list()` implementation** (`list_cmd.py:12-36`):
```python
def cmd_list(config: BRConfig, args: argparse.Namespace) -> int:
    from little_loops.issue_parser import find_issues
    type_prefixes = {args.type} if args.type else None
    issues = find_issues(config, type_prefixes=type_prefixes)
    if args.priority:
        issues = [i for i in issues if i.priority == args.priority]
    if not issues:
        print("No active issues found.")
        return 0
    for issue in issues:
        print(f"{issue.path.name}  {issue.title}")  # full filename + title, no grouping
    return 0
```

**Recommended implementation skeleton** (following `format_summary_text()` pattern):
```python
def cmd_list(config: BRConfig, args: argparse.Namespace) -> int:
    from little_loops.issue_parser import find_issues
    type_prefixes = {args.type} if getattr(args, "type", None) else None
    issues = find_issues(config, type_prefixes=type_prefixes)
    if getattr(args, "priority", None):
        issues = [i for i in issues if i.priority == args.priority]

    if not issues:
        print("No active issues found.")
        return 0

    if getattr(args, "flat", False):
        for issue in issues:
            print(f"{issue.path.name}  {issue.title}")
        return 0

    # Group by type prefix
    buckets: dict[str, list] = {"BUG": [], "FEAT": [], "ENH": []}
    for issue in issues:
        prefix = issue.issue_id.split("-", 1)[0]
        if prefix in buckets:
            buckets[prefix].append(issue)

    type_labels = {"BUG": "Bugs", "FEAT": "Features", "ENH": "Enhancements"}
    lines: list[str] = []
    for prefix, label in type_labels.items():
        group = buckets[prefix]
        header = f"{label} ({len(group)})"
        lines.append(header)
        for issue in group:
            lines.append(f"  {issue.priority}  {issue.issue_id}  {issue.title}")
        lines.append("")
    lines.append(f"Total: {len(issues)} active issues")
    print("\n".join(lines))
    return 0
```

**`--flat` flag registration** (add to `__init__.py` after existing `--priority` arg at line ~53):
```python
ls.add_argument("--flat", action="store_true", help="Output flat list (current format) for scripting compatibility")
```

## Scope Boundaries

- **In scope**: Grouped-by-type output with headers, counts, cleaner per-line format, total count, and `--flat` flag for backward compatibility
- **Out of scope**: Color/ANSI output, interactive/TUI mode, filtering/search within list, JSON/CSV export formats

## Success Metrics

- Issues are grouped by type (BUG, FEAT, ENH) with per-group counts; users can locate an issue's type section in <2 seconds of scanning
- All type groups are shown even if count is 0; total count matches sum of groups
- `--flat` flag produces output identical to current behavior for scripting compatibility

## Implementation Steps

1. **Add `--flat` flag** to `scripts/little_loops/cli/issues/__init__.py` (after the `--priority` arg, ~line 53): `ls.add_argument("--flat", action="store_true", ...)`
2. **Rewrite `cmd_list()`** in `scripts/little_loops/cli/issues/list_cmd.py` (lines 12–36): replace flat print loop with type-bucketing logic using `issue.issue_id.split("-", 1)[0]` for prefix extraction; use `list[str]` buffer + `"\n".join()` following the `format_summary_text()` pattern at `issue_history/formatting.py:29-58`
3. **Preserve `--flat` path** inside `cmd_list()`: if `args.flat`, fall back to the original `print(f"{issue.path.name}  {issue.title}")` loop
4. **Update tests** in `scripts/tests/test_issues_cli.py`: add tests for grouped output (verify type headers like `"Enhancements (N)"` appear in `captured.out`), empty-type handling, total count line, and `--flat` backward compatibility; may need to add an ENH sample issue to `conftest.py:issues_dir` fixture or create a local fixture
5. **Run tests**: `python -m pytest scripts/tests/test_issues_cli.py -v`

## Impact

- **Priority**: P3 - Quality-of-life improvement for daily workflow
- **Effort**: Small - Single file change, straightforward formatting logic
- **Risk**: Low - Output-only change, no data mutations
- **Breaking Change**: No (unless scripts parse current output; mitigated by `--flat` flag)

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | CLI tool design patterns |

## Labels

`enhancement`, `cli`, `captured`

## Resolution

**Completed**: 2026-02-26

### Changes Made

- `scripts/little_loops/cli/issues/list_cmd.py` — Rewrote `cmd_list()` to group issues by type (BUG, FEAT, ENH) with section headers showing counts, cleaner per-line format (`  Pn  TYPE-NNN  Title`), total count footer, and `--flat` fallback path
- `scripts/little_loops/cli/issues/__init__.py` — Added `--flat` flag to the `list` subparser for backward-compatible scripting output
- `scripts/tests/test_issues_cli.py` — Added `issues_dir_with_enh` fixture and 4 new tests covering: grouped headers/counts, per-line format, `--flat` backward compatibility, empty group display

### Verification

- All 19 tests pass (`python -m pytest scripts/tests/test_issues_cli.py -v`)
- Lint clean (`ruff check`)
- Type-check clean (`mypy`)

## Session Log
- `/ll:capture-issue` - 2026-02-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c897290c-f61e-463d-8d24-8a80f1c64fb2.jsonl`
- `/ll:format-issue` - 2026-02-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a606bda7-f113-4f3b-8c19-e6d153438758.jsonl`
- `/ll:refine-issue` - 2026-02-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bb239519-7377-476c-aab7-df27933ff082.jsonl`
- `/ll:manage-issue` - 2026-02-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c897290c-f61e-463d-8d24-8a80f1c64fb2.jsonl`

---

## Status

**Completed** | Created: 2026-02-26 | Completed: 2026-02-26 | Priority: P3
