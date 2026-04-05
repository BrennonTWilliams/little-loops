---
id: FEAT-955
discovered_date: 2026-04-05
discovered_by: capture-issue
---

# FEAT-955: Add `ll-issues skip` subcommand to deprioritize issues that fail refinement

## Summary

Loop configs that use a `skip_issue` state to handle refinement failures currently have no standard way to lower an issue's priority so `ll-issues next-issue` returns a different issue next time. Without this, any `skip_issue → get_next_issue` cycle will fetch the same issue again forever. Add an `ll-issues skip <ID>` subcommand that permanently deprioritizes an issue (e.g. bumps it to P5) and records the skip in the issue file, giving loop authors a reliable primitive for skip semantics.

## Use Case

A user's `auto-issue-processor` loop calls `refine-to-ready-issue` for each issue. When refinement fails, `skip_issue` echoes a message and calls `get_next_issue` — but `ll-issues next-issue` returns the same top-ranked issue again, creating an infinite loop. With `ll-issues skip FEAT-013`, the loop can atomically lower priority and move on:

```yaml
skip_issue:
  action: "ll-issues skip ${captured.input.output}"
  action_type: shell
  next: get_next_issue
```

## Motivation

`skip_issue` patterns in FSM loops are currently implementation-defined ad-hoc shell snippets. Without a standard skip primitive, loops silently cycle on stuck issues and users have no audit trail of which issues were skipped. A first-class `ll-issues skip` command gives loop authors a safe, consistent, auditable way to defer stuck issues.

## Proposed Solution

Add `skip` subcommand to `ll-issues` CLI:

```
ll-issues skip <ISSUE_ID> [--priority P5] [--reason "text"]
```

Behavior:
1. Locate the issue file by ID (all active categories)
2. Rename the file to bump its priority prefix to `--priority` (default P5)
3. Append a `## Skip Log` section with timestamp and optional reason
4. Print the new file path to stdout (so callers can confirm)

The rename preserves the full filename slug and issue number; only the `P[0-5]` prefix changes.

## API/Interface

```
ll-issues skip FEAT-013
# → Deprioritized FEAT-013 to P5: .issues/features/P5-FEAT-013-my-feature.md

ll-issues skip BUG-042 --priority P4 --reason "flaky test env, retry after CI fix"
# → Deprioritized BUG-042 to P4: .issues/bugs/P4-BUG-042-my-bug.md
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues.py` (or equivalent `ll-issues` entry point) — add `skip` subcommand
- `scripts/little_loops/issue_manager.py` (or similar) — implement rename + append logic

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — could use in `skip_issue`-equivalent states
- Any project-level loop YAML with `skip_issue` states
- `ll-issues next-issue` — benefits from lower priority keeping skipped issues out of rotation

### Similar Patterns
- `ll-issues next-id` — ID lookup pattern
- `ll-issues list` — issue discovery pattern

### Tests
- Test that `skip` renames file correctly with updated priority prefix
- Test that `skip` appends `## Skip Log` section
- Test that skipped issue no longer ranks first in `next-issue` output

## Implementation Steps

1. Add `skip` subparser to `ll-issues` CLI with `issue_id`, `--priority`, `--reason` args
2. Implement file search by ID across all active category dirs
3. Rename file with new priority prefix (atomic `Path.rename`)
4. Append `## Skip Log` section with ISO timestamp and reason
5. Print new path to stdout
6. Update docs / `ll:help` output to include `skip`

## Impact

- **Priority**: P4 — nice-to-have quality-of-life; loops work around it with inline shell
- **Effort**: Small — single CLI subcommand, no external dependencies
- **Risk**: Low — purely additive; renames are reversible
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `ll-issues`, `cli`, `fsm`, `loops`, `captured`

## Status

**Open** | Created: 2026-04-05 | Priority: P4

---

## Session Log

- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a3203fd4-ea84-4c13-b186-96678a2c9062.jsonl`
