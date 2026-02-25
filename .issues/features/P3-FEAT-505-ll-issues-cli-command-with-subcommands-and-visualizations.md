---
discovered_date: 2026-02-24
discovered_by: capture-issue
confidence_score: 93
outcome_confidence: 78
---

# FEAT-505: ll-issues CLI Command with Sub-commands and Visualizations

## Summary

Create a new `ll-issues` CLI entry point that consolidates issue utility commands under a single sub-command interface. The existing `ll-next-id` command becomes `ll-issues next-id`, and new sub-commands expose visualizations like impact vs. effort matrices and suggested implementation sequencing.

## Current Behavior

- `ll-next-id` is a standalone command that only prints the next available issue ID.
- No CLI-level tooling exists for visualizing issue priority, effort, or sequencing.
- Users must mentally cross-reference issue frontmatter and priority levels to plan implementation order.

## Expected Behavior

A single `ll-issues` entry point with sub-commands:

```
ll-issues next-id              # replacement for ll-next-id (prints next ID, e.g., 071)
ll-issues impact-effort        # ASCII/rich matrix of impact vs effort for active issues
ll-issues sequence             # suggested implementation order based on priority, deps, and effort
ll-issues list [--type] [--priority]  # filtered listing of active issues
```

The `ll-next-id` binary remains available as a shim or alias for backwards compatibility until deprecated.

## Motivation

`ll-next-id` is a narrow utility that belongs in a broader issue management CLI surface. As the project grows, more issue-level queries (sequencing, visualization, filtering) belong together under a coherent namespace. A sub-command model (`ll-issues <verb>`) makes the tool surface discoverable, composable with `--help`, and easier for both users and agents to reason about.

The visualization sub-commands directly support sprint planning and backlog grooming: an impact-vs-effort matrix surfaces quick wins, and sequencing output reduces the cognitive load of manually ordering issues.

## Use Cases

- **Sprint planning**: Run `ll-issues impact-effort` to identify P2/P3 issues with low effort, pick 3-5 for the sprint.
- **Starting a session**: Run `ll-issues sequence` to get an opinionated ordering of open issues to work through.
- **Issue creation workflow**: Skills and hooks call `ll-issues next-id` (same as today's `ll-next-id`).

## Acceptance Criteria

- [ ] `ll-issues next-id` produces the same output as the current `ll-next-id` command
- [ ] `ll-issues impact-effort` renders a 2D ASCII/rich grid of active issues grouped by priority and inferred effort
- [ ] `ll-issues sequence` outputs a dependency-ordered list of active issues with brief rationale per entry
- [ ] `ll-issues list [--type] [--priority]` filters and lists active issues, one per line (filename + title)
- [ ] `ll-next-id` retains backward compatibility and continues to function as before
- [ ] `ll-issues` entry point registered in `scripts/pyproject.toml`
- [ ] All sub-commands support `--help` and `--config PATH`
- [ ] At least one test per sub-command in `scripts/tests/test_issues_cli.py`

## Proposed Solution

### 1. Create `scripts/little_loops/cli/issues/` sub-package

Follow the `sprint/` and `loop/` sub-package pattern (`scripts/little_loops/cli/sprint/__init__.py`). Structure:

```
scripts/little_loops/cli/issues/
  __init__.py       # main_issues() dispatcher with add_subparsers()
  next_id.py        # cmd_next_id() — delegates to get_next_issue_number()
  list_cmd.py       # cmd_list() — uses find_issues() with type_prefixes filter
  sequence.py       # cmd_sequence() — uses DependencyGraph.topological_sort()
  impact_effort.py  # cmd_impact_effort() — ASCII grid renderer
```

Top-level dispatcher in `__init__.py` (follows `history.py:9-140` pattern):

```python
def main_issues() -> int:
    parser = argparse.ArgumentParser(prog="ll-issues",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    add_config_arg(parser)          # --config on parent (like ll-sync)
    subs = parser.add_subparsers(dest="command", help="Available commands")

    subs.add_parser("next-id", help="Print next globally unique issue number")

    ie = subs.add_parser("impact-effort", help="Display impact vs effort matrix")
    # no --format flag needed — output is always ASCII plain text

    seq = subs.add_parser("sequence", help="Suggest implementation order")
    seq.add_argument("--limit", type=int, default=10)

    ls = subs.add_parser("list", help="List active issues")
    ls.add_argument("--type", choices=["BUG", "FEAT", "ENH"])
    ls.add_argument("--priority", choices=["P0","P1","P2","P3","P4","P5"])

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)
    if args.command == "next-id": return cmd_next_id(config)
    if args.command == "impact-effort": return cmd_impact_effort(config, args)
    if args.command == "sequence": return cmd_sequence(config, args)
    if args.command == "list": return cmd_list(config, args)
    return 1
```

### 2. `next-id` sub-command (`next_id.py`)

Delegate to `get_next_issue_number(config)` at `issue_parser.py:42` — identical logic to `main_next_id()`.

### 3. `impact-effort` sub-command (`impact_effort.py`)

- Read active issues via `find_issues(config)` at `issue_parser.py:473`.
- **effort/impact inference** (no `effort`/`impact` fields exist on `IssueInfo` today): infer defaults from `priority_int` — add optional `effort: int | None` and `impact: int | None` fields to `IssueInfo` at `issue_parser.py:127`, populated from frontmatter if present, otherwise inferred (P0-P1 → high impact/high effort, P2-P3 → medium, P4-P5 → low impact/low effort).
- Update `IssueParser.parse_file()` at `issue_parser.py:212` to read `effort` and `impact` from `parse_frontmatter()` output.
- Render a 2D ASCII grid (no Rich — codebase uses plain Python strings with unicode box-drawing chars following `sprint/_helpers.py:12`) with quadrant labels: Quick Wins / Major Projects / Fill-ins / Thankless Tasks.
- **Grid layout spec** (decided 2026-02-25):
  - 2×2 grid, X-axis = Effort (Low → High), Y-axis = Impact (High → Low top-to-bottom)
  - Each quadrant is a fixed-width column (~34 chars). Use `─`, `│`, `┌`, `┐`, `└`, `┘`, `├`, `┤`, `┬`, `┴`, `┼` box-drawing chars.
  - Quadrant header line: symbol + label (`★ QUICK WINS`, `▲ MAJOR PROJECTS`, `· FILL-INS`, `✗ THANKLESS TASKS`)
  - Per-issue line: `ISSUEID  slug` — where `slug` is the filename description segment (everything after `[TYPE]-NNN-`) with hyphens replaced by spaces, truncated to 20 chars. Example: `ENH-498  obs masking scratch pa`
  - Axis labels printed above (`← EFFORT →`) and to the left (`IMPACT`) with `High`/`Low` tick labels at grid corners.
  - Example output structure:
    ```
                       ← EFFORT →
                  Low            High
             ┌──────────────────┬──────────────────┐
        High │ ★ QUICK WINS     │ ▲ MAJOR PROJECTS │
             │ ENH-498  obs mas │ FEAT-505 ll issu │
    IMPACT   ├──────────────────┼──────────────────┤
        Low  │ · FILL-INS       │ ✗ THANKLESS      │
             │ BUG-503  minor f │ (none)           │
             └──────────────────┴──────────────────┘
    ```
  - If a quadrant has more issues than fit in a reasonable height, append `  … +N more` on the last line.

### 4. `sequence` sub-command (`sequence.py`)

Use the existing dependency infrastructure:
1. `find_issues(config)` at `issue_parser.py:473` → `list[IssueInfo]` (already sorted by priority)
2. `DependencyGraph.from_issues(issues, completed_ids=set(), all_known_ids=set())` at `dependency_graph.py:51`
3. `graph.topological_sort()` at `dependency_graph.py:223` (Kahn's algorithm, priority-aware tie-breaking)
4. Output one line per issue: `[P2, no blockers] ENH-498: observation masking`

### 5. `list` sub-command (`list_cmd.py`)

Use `find_issues(config, type_prefixes=type_filter)` at `issue_parser.py:473` — the `type_prefixes` parameter directly supports `--type` filtering. Apply `--priority` filter post-scan on `info.priority`.

### 6. Entry point registration

Add to `scripts/pyproject.toml` (after existing entries at line 58):

```toml
ll-issues = "little_loops.cli:main_issues"
```

Export `main_issues` in `scripts/little_loops/cli/__init__.py` (lines 16-46, same pattern as all other `main_*` exports).

Keep `ll-next-id = "little_loops.cli:main_next_id"` pointing to its existing standalone entry point.

## API/Interface

```
ll-issues next-id [--config PATH]
ll-issues impact-effort [--config PATH]
ll-issues sequence [--limit N] [--config PATH]
ll-issues list [--type BUG|FEAT|ENH] [--priority P0..P5] [--config PATH]
```

All sub-commands accept `--config PATH` to specify project root (consistent with other ll-* tools).

## Implementation Steps

1. Add optional `effort: int | None` and `impact: int | None` fields to `IssueInfo` at `issue_parser.py:127`; update `IssueParser.parse_file()` at `issue_parser.py:212` to read them from `parse_frontmatter()` output.
2. Create sub-package `scripts/little_loops/cli/issues/` with `__init__.py` dispatcher (follows `sprint/__init__.py:46` pattern); add `add_config_arg(parser)` on parent parser (like `sync.py:14`).
3. Implement `cmd_next_id()` in `next_id.py` delegating to `get_next_issue_number(config)` at `issue_parser.py:42`.
4. Implement `cmd_list()` in `list_cmd.py` using `find_issues(config, type_prefixes=...)` at `issue_parser.py:473`; apply `--priority` filter post-scan.
5. Implement `cmd_sequence()` in `sequence.py`: call `find_issues(config)`, build `DependencyGraph.from_issues()` at `dependency_graph.py:51`, call `graph.topological_sort()` at `dependency_graph.py:223`, output rationale per issue.
6. Implement `cmd_impact_effort()` in `impact_effort.py`: infer effort/impact from `priority_int` (0-1 = high, 2-3 = medium, 4-5 = low), override with frontmatter values if present; render ASCII 2D grid (plain Python strings following `sprint/_helpers.py:12` pattern — no Rich).
7. Export `main_issues` in `scripts/little_loops/cli/__init__.py` (lines 16-46, same pattern as other exports).
8. Register `ll-issues = "little_loops.cli:main_issues"` in `scripts/pyproject.toml` (after existing entries at line 58).
9. Add deprecation notice to `scripts/little_loops/cli/next_id.py` `--help` epilog pointing to `ll-issues next-id`.
10. Add `scripts/tests/test_issues_cli.py` with one class per subcommand; use `patch("sys.argv", ["ll-issues", subcmd, "--config", ...])` + `capsys` + `temp_project_dir`/`sample_config`/`config_file`/`issues_dir` fixtures from `conftest.py`.
11. Update `commands/help.md`, `.claude/CLAUDE.md`, and `README.md` (lines 325-343) to document `ll-issues`.

## Integration Map

### Files to Create
- `scripts/little_loops/cli/issues/__init__.py` — `main_issues()` dispatcher with `add_subparsers()`
- `scripts/little_loops/cli/issues/next_id.py` — `cmd_next_id()` delegating to `get_next_issue_number()`
- `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list()` using `find_issues()` with `type_prefixes`
- `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence()` using `DependencyGraph.topological_sort()`
- `scripts/little_loops/cli/issues/impact_effort.py` — `cmd_impact_effort()` with ASCII grid renderer
- `scripts/tests/test_issues_cli.py` — one test class per sub-command

### Files to Modify
- `scripts/pyproject.toml` — add `ll-issues = "little_loops.cli:main_issues"` (after line 58)
- `scripts/little_loops/cli/__init__.py` — export `main_issues` (follows existing export pattern lines 16-46)
- `scripts/little_loops/issue_parser.py` — add optional `effort: int | None` and `impact: int | None` fields to `IssueInfo` dataclass (line 127); update `IssueParser.parse_file()` (line 212) to populate them from frontmatter
- `scripts/little_loops/cli/next_id.py` — add deprecation notice in `--help` epilog pointing to `ll-issues next-id`
- `commands/help.md` — add `ll-issues` to CLI tool listing
- `.claude/CLAUDE.md` — add `ll-issues` to CLI Tools section
- `README.md` — add `ll-issues` to CLI tools section (near existing `ll-next-id` and `ll-deps` entries, around lines 325-343)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/next_id.py` — imports `get_next_issue_number` from `issue_parser.py:42`
- `scripts/little_loops/cli/issues/list_cmd.py` — imports `find_issues` from `issue_parser.py:473`
- `scripts/little_loops/cli/issues/sequence.py` — imports `find_issues` from `issue_parser.py:473`, `DependencyGraph` from `dependency_graph.py:51`
- `scripts/little_loops/cli/issues/impact_effort.py` — imports `find_issues` from `issue_parser.py:473`

### Similar Patterns
- `scripts/little_loops/cli/sprint/__init__.py:46` — sub-package dispatcher with per-file subcommand handlers (closest structural match)
- `scripts/little_loops/cli/history.py:9` — clean `add_subparsers(dest="command")` + no-command guard pattern
- `scripts/little_loops/cli/sync.py:14` — `add_config_arg(parser)` on parent parser pattern
- `scripts/little_loops/cli/sprint/_helpers.py:12` — ASCII execution plan renderer with unicode box-drawing chars (model for `impact-effort` grid)
- `scripts/little_loops/dependency_graph.py:223` — `topological_sort()` — reuse directly for `sequence`

### Tests
- `scripts/tests/test_issues_cli.py` — unit tests for each sub-command
  - `TestIssuesCLINextId` — follows `test_cli_next_id.py` exactly
  - `TestIssuesCLIList` — uses `issues_dir` fixture + `--type`/`--priority` filter assertions
  - `TestIssuesCLISequence` — uses `issues_dir` fixture + `DependencyGraph` mock or real
  - `TestIssuesCLIImpactEffort` — uses `issues_dir` fixture + output string assertions
  - All use `patch("sys.argv", ["ll-issues", subcmd, "--config", str(temp_project_dir)])` + `capsys`
- Integration: verify `ll-issues next-id` output matches `ll-next-id` output

### Documentation
- `commands/help.md` — add `ll-issues` to CLI tool listing
- `.claude/CLAUDE.md` — add `ll-issues` to CLI Tools section
- `README.md` — add `ll-issues` (near lines 325-343 where `ll-next-id` and `ll-deps` are documented)

## Impact

- **Priority**: P3 — Moderate; improves discoverability and adds planning utilities
- **Effort**: Medium — New CLI module plus 4 sub-commands; visualization logic is the main complexity
- **Risk**: Low — Additive change; `ll-next-id` remains functional
- **Breaking Change**: No — `ll-next-id` stays as-is until explicitly deprecated

## Labels

`feature`, `cli`, `visualization`, `ux`, `tooling`, `sprint-planning`

## Session Log
- `/ll:capture-issue` - 2026-02-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71365a34-a4b0-468f-af55-a3641738c45e.jsonl`
- `/ll:format-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a32a1e4-137e-4580-a6db-a31be30ec313.jsonl`
- `/ll:refine-issue` - 2026-02-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a32a1e4-137e-4580-a6db-a31be30ec313.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
