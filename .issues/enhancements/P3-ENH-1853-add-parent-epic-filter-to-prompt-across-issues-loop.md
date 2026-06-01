---
id: ENH-1853
title: Add parent-epic filter to prompt-across-issues loop
type: ENH
priority: P3
captured_at: "2026-06-01T17:06:21Z"
discovered_date: 2026-06-01
discovered_by: capture-issue
status: open
relates_to: [ENH-1643]
---

# ENH-1853: Add parent-epic filter to prompt-across-issues loop

## Summary

`prompt-across-issues` supports type filtering (`--context type=BUG`) via ENH-1643, but has no way to scope a sweep to all issues belonging to a specific epic. A user running a prompt across all children of EPIC-1773 must manually enumerate issue IDs or run the full-backlog sweep. Add an optional `parent` context variable that narrows the pending list to issues whose `parent:` frontmatter matches a given epic ID.

## Current Behavior

`prompt-across-issues` builds its pending list from `ll-issues list --json` with an optional `--type` flag (ENH-1643). There is no `--parent` flag on `ll-issues list` and no `parent` context variable on the loop. Users wanting to sweep all children of an epic have no supported path.

## Expected Behavior

```bash
# Sweep all open issues under EPIC-1773
ll-loop run prompt-across-issues "/ll:ready-issue {issue_id}" --context parent=EPIC-1773
```

When `parent` is supplied, the `init` state filters the pending list to issues whose `parent:` frontmatter field matches the given ID. When omitted, behavior is identical to today.

## Motivation

Wave-based epic work (e.g., EPIC-1773) produces a set of child issues that need the same sweep applied — readiness checks, refinement, verification. Today there's no idiomatic way to run `prompt-across-issues` scoped to those children without manually listing IDs or sweeping the entire backlog. This is the natural sibling to type filtering (ENH-1643): type narrows by category, parent narrows by ownership.

## Proposed Solution

Two options for the filtering mechanism:

**(a) Post-filter in `init`** — run `ll-issues list --json`, then filter the JSON in Python to keep only issues where `parent == context.parent`. No changes to `ll-issues list` CLI.

**(b) Add `--parent` flag to `ll-issues list`** — extend the CLI to support `ll-issues list --parent EPIC-1773 --json`, then pass `--parent ${context.parent}` conditionally in `init` (same pattern as `--type`).

Option (a) is self-contained to the loop YAML. Option (b) is more reusable but requires a Python CLI change.

### Changes (Option a — loop-only)

1. Add `context: { parent: "" }` block above `states:` in `prompt-across-issues.yaml`
2. In `init`, after `ll-issues list --json`, pipe through a Python filter that drops issues where `parent != context.parent` when `context.parent` is non-empty
3. Update loop `description:` to document the new flag

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prompt-across-issues.yaml` — add `parent` context var and filter logic in `init`
- *(Option b only)* `scripts/little_loops/cli/issues/__init__.py` — add `--parent` argument

### Similar Patterns
- `ENH-1643` — type filter on same loop; follow identical context-var + conditional-arg pattern
- `scripts/little_loops/loops/test-coverage-improvement.yaml:20-22` — empty-string default for optional context vars

### Dependent Files (Callers/Importers)
- N/A — loop YAML is not a Python module; invoked directly via `ll-loop run prompt-across-issues`

### Tests
- No new unit tests required; `ll-loop validate prompt-across-issues` + dry-run verification covers it

### Documentation
- N/A — loop `description:` field updated in-place (Implementation Step 3); no separate doc files

### Configuration
- N/A

## Implementation Steps

1. Add `context: { parent: "" }` to `prompt-across-issues.yaml` above `states:`
2. Update `init` action to filter pending list by `parent` when non-empty (Option a: Python post-filter; Option b: `--parent` CLI flag)
3. Update loop `description:` with usage example
4. Run `ll-loop validate prompt-across-issues`
5. Dry-run with `--context parent=EPIC-1773` and verify pending list matches `ll-issues list --json | jq '[.[] | select(.parent=="EPIC-1773")]'`

## API/Interface

```yaml
context:
  parent: ""  # Optional: EPIC-NNN. When set, restricts sweep to issues with matching parent: field.
```

```bash
ll-loop run prompt-across-issues "<prompt>"                          # all open issues (unchanged)
ll-loop run prompt-across-issues "<prompt>" --context parent=EPIC-1773  # children of EPIC-1773 only
ll-loop run prompt-across-issues "<prompt>" --context type=ENH --context parent=EPIC-1773  # both filters
```

## Scope Boundaries

- **Out of scope**: multi-parent selection
- **Out of scope**: filtering by any attribute other than `parent` (priority, label, etc.)
- **Out of scope**: changes to `ll-loop run` itself — uses existing `--context KEY=VALUE` mechanism

## Success Metrics

- `ll-loop validate prompt-across-issues` exits 0
- `--context parent=EPIC-1773` pending list matches `ll-issues list --json` filtered to `parent == "EPIC-1773"`
- Default invocation (no `--context parent`) is bit-for-bit identical to pre-change

## Impact

- **Priority**: P3 — Quality-of-life for epic-scoped sweep workflows
- **Effort**: Small — mirrors ENH-1643 pattern exactly; ~10 lines in one YAML file (Option a)
- **Risk**: Low — empty-string default preserves current behavior; post-filter logic is simple Python
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `fsm`

## Session Log
- `/ll:format-issue` - 2026-06-01T17:14:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96043361-acea-4c7e-bf4e-4bf536eb0898.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:06:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1781e718-7f06-4b5d-95f3-141040199f61.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
