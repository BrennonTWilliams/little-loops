---
discovered_date: 2026-02-24
discovered_by: capture-issue
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

### 1. Create `scripts/little_loops/cli/issues.py`

Top-level argparse with sub-parsers:

```python
def main_issues():
    parser = argparse.ArgumentParser(prog="ll-issues")
    subs = parser.add_subparsers(dest="command", required=True)

    # next-id
    subs.add_parser("next-id", help="Print next globally unique issue number")

    # impact-effort
    ie = subs.add_parser("impact-effort", help="Display impact vs effort matrix")
    ie.add_argument("--format", choices=["ascii", "rich"], default="rich")

    # sequence
    seq = subs.add_parser("sequence", help="Suggest implementation order")
    seq.add_argument("--limit", type=int, default=10)

    # list
    ls = subs.add_parser("list", help="List active issues")
    ls.add_argument("--type", choices=["BUG", "FEAT", "ENH"])
    ls.add_argument("--priority", choices=["P0","P1","P2","P3","P4","P5"])
```

### 2. `next-id` sub-command

Delegate to `get_next_issue_number()` — identical to current `ll-next-id` logic.

### 3. `impact-effort` sub-command

- Read all active issue files and parse frontmatter fields: `priority`, `effort` (if present), `impact` (if present).
- For issues missing explicit `effort`/`impact` fields, infer from priority (P0-P1 = high impact, P4-P5 = low effort).
- Render a 2D ASCII or `rich` table grid with quadrant labels: Quick Wins / Major Projects / Fill-ins / Thankless Tasks.

### 4. `sequence` sub-command

- Load active issues with their `blockedBy` relationships (from `ll-deps` or inline frontmatter).
- Apply topological sort respecting dependency order.
- Break ties by priority (P0 first) then discovery date.
- Output an ordered list with brief rationale (e.g., `[P2, no blockers] ENH-498: observation masking`).

### 5. `list` sub-command

- Filtered listing of active issues across all categories.
- Supports `--type` and `--priority` filters.
- Output format: one line per issue (filename + title).

### 6. Entry point registration

Add to `scripts/pyproject.toml`:

```toml
[project.scripts]
ll-issues = "little_loops.cli.issues:main_issues"
```

Keep `ll-next-id` pointing to its existing entry point until a deprecation notice is added and the sub-command is confirmed stable.

## API/Interface

```
ll-issues next-id [--config PATH]
ll-issues impact-effort [--format ascii|rich] [--config PATH]
ll-issues sequence [--limit N] [--config PATH]
ll-issues list [--type BUG|FEAT|ENH] [--priority P0..P5] [--config PATH]
```

All sub-commands accept `--config PATH` to specify project root (consistent with other ll-* tools).

## Implementation Steps

1. Create `scripts/little_loops/cli/issues.py` with sub-command dispatcher.
2. Implement `cmd_next_id()` by delegating to existing `get_next_issue_number()`.
3. Implement `cmd_list()` using `IssueParser` / directory scanning utilities.
4. Implement `cmd_sequence()` with topological sort on blockedBy deps.
5. Implement `cmd_impact_effort()` with ASCII grid renderer (rich optional).
6. Register `ll-issues` entry point in `pyproject.toml`.
7. Add deprecation notice to `ll-next-id --help` pointing to `ll-issues next-id`.
8. Add tests for each sub-command in `scripts/tests/`.
9. Update `commands/help.md` and `docs/` to document `ll-issues`.

## Integration Map

### Files to Create
- `scripts/little_loops/cli/issues.py` — main entry point + sub-command implementations

### Files to Modify
- `scripts/pyproject.toml` — add `ll-issues` entry point
- `scripts/little_loops/cli/next_id.py` — add deprecation notice in `--help` epilog
- `commands/help.md` — add `ll-issues` to CLI tool listing
- `.claude/CLAUDE.md` — add `ll-issues` to CLI Tools section

### Tests
- `scripts/tests/test_issues_cli.py` — unit tests for each sub-command
- Integration: verify `ll-issues next-id` output matches `ll-next-id` output

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

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
