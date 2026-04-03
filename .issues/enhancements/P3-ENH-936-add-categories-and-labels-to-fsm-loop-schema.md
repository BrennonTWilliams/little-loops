---
id: ENH-936
type: ENH
priority: P3
status: open
discovered_date: 2026-04-03
discovered_by: capture-issue
---

# ENH-936: Add Categories and Labels to FSM Loop Schema

## Summary

Add `category` and `labels` metadata fields to the FSM loop YAML schema, and expose filtering by these fields in `ll-loop list`. Currently 33+ loops are listed without any grouping, making it hard to find the right loop for a task.

## Current Behavior

`ll-loop list` dumps all loops in a flat list with only `name` and `description`. There is no way to group or filter by purpose (e.g., "code quality", "AI optimization", "issue management"). The schema only supports `name`, `description`, `initial`, `max_iterations`, `timeout`, and `states`.

## Expected Behavior

- Loop YAML files can declare a `category` (single string) and optional `labels` (list of strings) at the top level
- `ll-loop list` groups loops by category when no filter is given
- `ll-loop list --category <name>` filters to a specific category
- `ll-loop list --label <label>` filters to loops matching a label
- Built-in loops and user-defined loops both support these fields

## Motivation

With 33+ loops and growing, users cannot quickly discover which loop to run. Issues use a `P[0-5]-[TYPE]` file-naming convention and `Labels:` frontmatter for similar organization. Applying the same concept to loops improves discoverability and aligns with the existing mental model in the project.

## Proposed Solution

1. Add optional `category: str` and `labels: list[str]` fields to the FSM loop loader (likely `scripts/little_loops/fsm/` or wherever loop YAML is parsed and validated)
2. Annotate all existing built-in loops in `scripts/little_loops/loops/*.yaml` with appropriate categories (e.g., `apo`, `code-quality`, `issue-management`, `harness`, `meta`)
3. Extend `cmd_list` in `scripts/little_loops/cli/loop/info.py` to:
   - Accept `--category` and `--label` filter flags
   - Group output by category when listing all loops (similar to how `ll-issues list` groups by type)
4. Update `ll-loop list` argparser in `scripts/little_loops/cli/loop/__init__.py` with the new flags

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `--category` and `--label` args to the `list` subparser
- `scripts/little_loops/cli/loop/info.py` — update `cmd_list` to support filtering and grouped display
- `scripts/little_loops/fsm/` — wherever loop YAML is loaded/validated, add `category` and `labels` to the schema (check `runners.py`, schema dataclasses)
- All `scripts/little_loops/loops/*.yaml` — add `category:` and `labels:` to each built-in loop

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` imports `cmd_list` from `info.py`
- Any test that exercises `cmd_list` or the loop list output

## Implementation Steps

1. Find where loop YAML is deserialized into a Python object (likely a dataclass or dict in `fsm/`) and add `category: str = ""` and `labels: list[str] = field(default_factory=list)`
2. Categorize all 33 built-in loops and add `category:` / `labels:` metadata to each YAML file
3. Update `cmd_list` to filter by `--category` / `--label` flags when provided, and to group output by category in the default (no-filter) view
4. Update the argparser with the new flags
5. Run `ll-loop list` and verify grouped/filtered output looks correct

## Impact

- **Priority**: P3 - Usability improvement, not blocking
- **Effort**: Medium - Schema change is small; the bulk is annotating 33+ YAML files and updating display logic
- **Risk**: Low - additive change; existing loops without `category`/`labels` fall back to "uncategorized" group

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `cli`, `usability`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d21e2100-9421-4796-91d0-fde897d2aa2b.jsonl`

---

## Status

**Open** | Created: 2026-04-03 | Priority: P3
