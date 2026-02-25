# FEAT-505: ll-issues CLI Implementation Plan

**Date**: 2026-02-25
**Issue**: FEAT-505 — ll-issues CLI Command with Sub-commands and Visualizations

## Summary

Create `ll-issues` CLI entry point with 4 sub-commands: `next-id`, `list`, `sequence`, `impact-effort`.

## Research Findings

- Follow `history.py` pattern for sub-command dispatch with `add_subparsers(dest="command")`
- Follow `sprint/__init__.py` for sub-package structure
- Use `add_config_arg(parser)` from `cli_args.py` on parent parser (sync.py pattern)
- Domain imports deferred inside function body (all cli/*.py files)
- IssueInfo at `issue_parser.py:127` — add `effort: int | None = None` and `impact: int | None = None`
- `parse_file()` at `issue_parser.py:212` — read effort/impact from frontmatter
- `get_next_issue_number()` at `issue_parser.py:42`
- `find_issues()` at `issue_parser.py:473` — supports `type_prefixes` filter
- `DependencyGraph.from_issues()` + `.topological_sort()` at `dependency_graph.py:52,223`
- ASCII rendering: `sprint/_helpers.py:12` — build `lines: list[str]`, return `"\n".join(lines)`
- Tests: use `patch("sys.argv", [...])` + `capsys` + `temp_project_dir`/`sample_config`/`config_file`/`issues_dir` fixtures

## Implementation Steps

### [x] 1. Modify `scripts/little_loops/issue_parser.py`
- Add `effort: int | None = None` and `impact: int | None = None` to IssueInfo (after product_impact)
- Update docstring
- Update `parse_file()` to read effort/impact from frontmatter
- Update `to_dict()` and `from_dict()`

### [x] 2. Create `scripts/little_loops/cli/issues/__init__.py`
- `main_issues()` dispatcher following history.py pattern
- `add_config_arg(parser)` on root parser
- 4 subcommands: next-id, list, sequence, impact-effort

### [x] 3. Create `scripts/little_loops/cli/issues/next_id.py`
- `cmd_next_id(config) -> int` delegating to `get_next_issue_number(config)`

### [x] 4. Create `scripts/little_loops/cli/issues/list_cmd.py`
- `cmd_list(config, args) -> int` using `find_issues(config, type_prefixes=...)`
- Apply --priority filter post-scan

### [x] 5. Create `scripts/little_loops/cli/issues/sequence.py`
- `cmd_sequence(config, args) -> int`
- Call `find_issues(config)` → `DependencyGraph.from_issues()` → `.topological_sort()`
- Output one line per issue: `[P2, no blockers] ENH-498: observation masking`

### [x] 6. Create `scripts/little_loops/cli/issues/impact_effort.py`
- `cmd_impact_effort(config, args) -> int`
- Infer effort/impact from priority_int (0-1=high, 2-3=medium, 4-5=low)
- Override with frontmatter values if present
- Render ASCII 2×2 grid with box-drawing chars

### [x] 7. Update `scripts/little_loops/cli/__init__.py`
- Add `from little_loops.cli.issues import main_issues`
- Add to `__all__` and docstring

### [x] 8. Update `scripts/pyproject.toml`
- Add `ll-issues = "little_loops.cli:main_issues"` after ll-next-id

### [x] 9. Update `scripts/little_loops/cli/next_id.py`
- Add deprecation notice in epilog

### [x] 10. Create `scripts/tests/test_issues_cli.py`
- TestIssuesCLINextId
- TestIssuesCLIList
- TestIssuesCLISequence
- TestIssuesCLIImpactEffort

### [x] 11. Update documentation
- commands/help.md
- .claude/CLAUDE.md
- README.md
