---
discovered_date: 2026-03-23
discovered_by: /ll:capture-issue
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

## Implementation Steps

1. Create `scripts/little_loops/cli/issues/next_action.py` with `cmd_next_action`
2. Register `next-action` (alias `na`) in `__init__.py` with `--refine-cap`, `--ready-threshold`, `--outcome-threshold` args
3. Update `loops/issue-refinement.yaml` `evaluate` state to use `ll-issues next-action`
4. Add unit tests covering all four `NEEDS_*` branches and `ALL_DONE`

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
- `/ll:capture-issue` - 2026-03-23T17:02:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06fdc033-986b-4b59-b280-3505ad02d65c.jsonl`
