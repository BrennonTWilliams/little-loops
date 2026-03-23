---
discovered_date: 2026-03-23
discovered_by: /ll:capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-860: Add `ll-issues next-action` subcommand

## Summary

The `evaluate` state in `loops/issue-refinement.yaml` embeds a 28-line inline Python script that classifies the next issue action (`NEEDS_FORMAT`, `NEEDS_VERIFY`, `NEEDS_SCORE`, `NEEDS_REFINE`, `ALL_DONE`). All the data it needs is already available from `ll-issues refine-status --json`. Adding a `ll-issues next-action` subcommand would replace the inline script with a single CLI call, making the loop simpler and the logic testable and reusable.

## Current Behavior

The `evaluate` state calls `ll-issues refine-status --json` and pipes it into an inline Python script:

```yaml
action: |
  ll-issues refine-status --json | python3 -c "
  import json, sys
  issues = json.load(sys.stdin)
  issues.sort(key=lambda i: (int(i['priority'][1]), -int(i['id'].split('-')[1])))
  for issue in issues:
      ...28 lines of classification logic...
  print('ALL_DONE')
  "
```

## Expected Behavior

The `evaluate` state becomes a single CLI call:

```yaml
action: ll-issues next-action
```

Output and exit codes match current behavior:
- Prints `NEEDS_FORMAT ENH-860` (exit 1) when work remains
- Prints `ALL_DONE` (exit 0) when all issues are graduated

All downstream states (`parse_id`, `route_format`, `route_verify`, `route_score`) are unchanged — the output format stays the same.

## Motivation

- **Testable**: The classification logic (thresholds 85/70, refine cap 5) can have unit tests
- **Reusable**: Other loops or scripts can call `ll-issues next-action` without copy-pasting the Python
- **Readable**: The loop YAML drops ~28 lines of inline script to 1 line
- **Configurable path**: Thresholds and the refine cap can later be wired to config without touching YAML

## Success Metrics

- **Loop complexity**: `evaluate` state in `loops/issue-refinement.yaml` reduces from ~28 lines of inline Python → 1 CLI call
- **Test coverage**: Unit tests cover all five branches (`NEEDS_FORMAT`, `NEEDS_VERIFY`, `NEEDS_SCORE`, `NEEDS_REFINE`, `ALL_DONE`)
- **Reusability**: `ll-issues next-action` callable from other loops or scripts without copy-pasting classification logic

## Scope Boundaries

- **In scope**: `next_action.py` subcommand; CLI registration in `__init__.py`; `evaluate` state update in `loops/issue-refinement.yaml`; unit tests in `scripts/tests/test_next_action.py`
- **Out of scope**: Changes to `ll-issues refine-status` JSON output format; threshold defaults used elsewhere; modification of any loop other than `issue-refinement.yaml`

## Proposed Solution

Add `next-action` (alias `na`) subcommand to `scripts/little_loops/cli/issues/__init__.py` and implement `scripts/little_loops/cli/issues/next_action.py`:

```python
def cmd_next_action(config: BRConfig, args: argparse.Namespace) -> int:
    """Print the next refinement action needed across all active issues.

    Output: NEEDS_FORMAT|NEEDS_VERIFY|NEEDS_SCORE|NEEDS_REFINE <id>  (exit 1)
            ALL_DONE                                                   (exit 0)
    """
    from little_loops.issue_parser import find_issues, is_formatted

    issues = find_issues(config)
    issues.sort(key=lambda i: (i.priority_int, -int(i.issue_id.split("-")[1])))

    refine_cap = getattr(args, "refine_cap", 5)
    ready_threshold = getattr(args, "ready_threshold", 85)
    outcome_threshold = getattr(args, "outcome_threshold", 70)

    for issue in issues:
        if not is_formatted(issue.path):
            print(f"NEEDS_FORMAT {issue.issue_id}")
            return 1
        if "/ll:verify-issues" not in issue.session_commands:
            print(f"NEEDS_VERIFY {issue.issue_id}")
            return 1
        cs, oc = issue.confidence_score, issue.outcome_confidence
        if cs is None or oc is None:
            print(f"NEEDS_SCORE {issue.issue_id}")
            return 1
        if issue.session_command_counts.get("/ll:refine-issue", 0) < refine_cap:
            if cs < ready_threshold or oc < outcome_threshold:
                print(f"NEEDS_REFINE {issue.issue_id}")
                return 1

    print("ALL_DONE")
    return 0
```

**Arguments** (all optional, default to loop-compatible values):
- `--refine-cap N` (default: 5) — max refinements before graduating an issue
- `--ready-threshold N` (default: 85) — minimum `confidence_score` to pass
- `--outcome-threshold N` (default: 70) — minimum `outcome_confidence` to pass

## Integration Map

| Component | File | Change |
|---|---|---|
| New subcommand impl | `scripts/little_loops/cli/issues/next_action.py` | Create |
| CLI registration | `scripts/little_loops/cli/issues/__init__.py` | Add `next-action` parser + dispatch |
| Loop simplification | `loops/issue-refinement.yaml` | Replace 28-line inline Python with `ll-issues next-action` |
| Tests | `scripts/tests/test_next_action.py` | Create |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files to modify:**

- `scripts/little_loops/cli/issues/__init__.py` — three insertion points:
  1. **Lines 17–25** (import block inside `main_issues()`): add `from little_loops.cli.issues.next_action import cmd_next_action`
  2. **Lines 29–276** (subparser registration block): add `next-action` parser after the last `add_parser` call (currently `append-log`)
  3. **Lines 290–308** (dispatch `if`-chain): add `if args.command == "next-action": return cmd_next_action(config, args)`
- `loops/issue-refinement.yaml` — **lines 12–48** contain the `evaluate` state; lines 14–41 are the inline Python to replace

**Sibling implementations to model after:**

- `scripts/little_loops/cli/issues/count_cmd.py` — best pattern match: `cmd_count(config, args)` with `getattr(args, "attr", default)` for optional flags, early JSON branch, `return 0`/`return 1` exit codes
- `scripts/little_loops/cli/issues/next_id.py` — minimal `cmd_*` shape (no args), deferred runtime imports, `TYPE_CHECKING` guard

**Data source fields confirmed** (`scripts/little_loops/cli/issues/refine_status.py:282–300`):
- All fields used by `cmd_next_action` exist on `IssueInfo`: `priority_int` (computed property, `issue_parser.py:241`), `issue_id`, `confidence_score`, `outcome_confidence`, `session_commands` (list of distinct `/ll:*` commands), `session_command_counts` (dict of counts)
- `is_formatted(issue.path)` confirmed at `scripts/little_loops/issue_parser.py:45–96`
- `find_issues(config)` confirmed at `scripts/little_loops/issue_parser.py:612–618`; follows same call pattern as `cmd_refine_status`

**Tests — existing fixtures and patterns:**

- `scripts/tests/conftest.py` — use `temp_project_dir`, `sample_config`, `issues_dir` fixtures
- `scripts/tests/test_refine_status.py:19–53` — copy `_make_issue()` helper to build issue files with custom `confidence_score`, `outcome_confidence`, and Session Log entries
- Core test invocation: `patch.object(sys, "argv", ["ll-issues", "next-action", "--config", str(temp_project_dir)])` + `main_issues()` (pattern from `test_issues_cli.py:29–36`)
- Model test class as `TestIssuesCLINextAction` (convention from `test_issues_cli.py`)

## API/Interface

```bash
ll-issues next-action [--refine-cap N] [--ready-threshold N] [--outcome-threshold N]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--refine-cap N` | 5 | Max refinements before graduating an issue |
| `--ready-threshold N` | 85 | Minimum `confidence_score` to pass |
| `--outcome-threshold N` | 70 | Minimum `outcome_confidence` to pass |

**Output + exit codes:**
- Exit 1 + `NEEDS_FORMAT|NEEDS_VERIFY|NEEDS_SCORE|NEEDS_REFINE <id>` — work remains on highest-priority issue
- Exit 0 + `ALL_DONE` — all active issues have graduated

## Implementation Steps

1. Create `scripts/little_loops/cli/issues/next_action.py` with `cmd_next_action`
   - Follow the `count_cmd.py` shape: module docstring, `TYPE_CHECKING` guard, `import argparse` at top, deferred domain imports inside the function
   - Use `getattr(args, "refine_cap", 5)` etc. for safe arg access
2. Register `next-action` (alias `na`) in `scripts/little_loops/cli/issues/__init__.py`:
   - Add `from little_loops.cli.issues.next_action import cmd_next_action` to the import block at lines 17–25
   - Add `subs.add_parser("next-action", aliases=["na"], ...)` + `.set_defaults(command="next-action")` in the parser block (lines 29–276)
   - Add three `add_argument` calls (`--refine-cap`, `--ready-threshold`, `--outcome-threshold`) then `add_config_arg(next_action_p)` last
   - Add `if args.command == "next-action": return cmd_next_action(config, args)` to the dispatch chain (lines 290–308)
3. Update `loops/issue-refinement.yaml` evaluate state (lines 12–48): replace the `ll-issues refine-status --json | python3 -c "..."` block (lines 14–41) with `action: ll-issues next-action`
4. Create `scripts/tests/test_next_action.py`:
   - Class `TestIssuesCLINextAction`; use `temp_project_dir`, `sample_config`, `issues_dir` from conftest; copy `_make_issue()` from `test_refine_status.py:19–53`
   - One test per branch: `NEEDS_FORMAT` (unformatted issue), `NEEDS_VERIFY` (no `/ll:verify-issues` in session log), `NEEDS_SCORE` (missing confidence fields), `NEEDS_REFINE` (scores below threshold), `ALL_DONE` (all graduated)

## Impact

- **Scope**: `scripts/little_loops/cli/issues/` (2 files modified, 2 files created)
- **Risk**: Low — pure addition; existing loop behavior is preserved via identical output format
- **Testing**: 4 unit test cases + existing refine-status tests still pass

## Related Key Documentation

| Document | Relevance |
|---|---|
| `loops/issue-refinement.yaml` | Primary loop that benefits from this change |
| `scripts/little_loops/cli/issues/refine_status.py` | Data source (`--json` output) the new command reads |

## Labels

`cli` `loops` `dx`

## Status

---
Active


## Session Log
- `/ll:confidence-check` - 2026-03-23T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd212742-4759-4df9-a71a-5ef5be2730f6.jsonl`
- `/ll:refine-issue` - 2026-03-23T18:12:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5fa1144-2913-4f9f-933b-4f7f5b56008b.jsonl`
- `/ll:format-issue` - 2026-03-23T18:07:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6707ae34-6988-4f2d-9043-0625567bfb1c.jsonl`
- `/ll:capture-issue` - 2026-03-23T17:02:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06fdc033-986b-4b59-b280-3505ad02d65c.jsonl`
