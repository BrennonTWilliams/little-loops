---
id: ENH-804
type: ENH
priority: P3
status: open
discovered_date: 2026-03-18
discovered_by: capture-issue
---

# ENH-804: Add --priority filter to ll-auto and ll-parallel

## Summary

Add a `--priority` CLI argument to `ll-auto` and `ll-parallel` that filters which issues are processed based on their priority level (P0–P5). Users should be able to pass one or more priority levels (e.g., `--priority P1,P2`) to restrict processing to only those priority tiers.

## Current Behavior

`ll-auto` and `ll-parallel` process all active issues in priority order, with filtering only by `--type` (BUG/ENH/FEAT), `--category` (bugs/features/enhancements), `--only` (specific IDs), and `--skip` (specific IDs). There is no way to say "only process P1 and P2 issues."

## Expected Behavior

```bash
ll-auto --priority P1,P2      # Process only P1 and P2 issues
ll-auto --priority P0          # Process only critical issues
ll-parallel --priority P1,P2   # Same filter in parallel mode
```

Invalid priority values (e.g., `--priority P9`) should fail with a clear error. The filter should compose with all existing filters (`--type`, `--skip`, `--only`, `--category`, `--max-issues`).

## Motivation

Running `ll-auto` on a large backlog processes low-priority issues when the intent is to focus automation budget on high-value work. Without a priority filter, users resort to `--only BUG-001,BUG-002,...` which requires knowing issue IDs in advance. A `--priority` flag enables natural, intent-driven scoping: "burn down all P1s first."

## Proposed Solution

Model after the existing `--type` filter pattern (`parse_issue_types` / `add_type_arg`):

1. Add `parse_priorities(value: str | None) -> set[str] | None` to `cli_args.py` — validates against `{"P0","P1","P2","P3","P4","P5"}`, raises `argparse.ArgumentTypeError` on invalid input.
2. Add `add_priority_arg(parser)` to `cli_args.py` — `--priority/-p` accepting comma-separated list.
3. Add `add_priority_arg` to both `add_common_auto_args` and `add_common_parallel_args`.
4. Wire the parsed set into `AutoManager.__init__` as `priority_filter: set[str] | None`.
5. In `AutoManager._get_next_issue` (and the parallel equivalent in `priority_queue.py`), add a filter clause: `i.priority in self.priority_filter` (or skip if `None`).
6. Update epilog examples in `auto.py` and `parallel.py`.

Priority is read from the issue filename prefix (`P3-ENH-804-...` → `"P3"`), which is already parsed by the issue model.

## API/Interface

```python
# cli_args.py
VALID_PRIORITIES: frozenset[str] = frozenset({"P0", "P1", "P2", "P3", "P4", "P5"})

def parse_priorities(value: str | None) -> set[str] | None: ...
def add_priority_arg(parser: argparse.ArgumentParser) -> None: ...

# issue_manager.py — AutoManager
class AutoManager:
    def __init__(
        self,
        ...,
        priority_filter: set[str] | None = None,  # new param
    ): ...
```

```bash
ll-auto --priority P1,P2
ll-parallel --priority P0,P1
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli_args.py` — add `parse_priorities`, `add_priority_arg`, extend `add_common_auto_args` + `add_common_parallel_args`, update `__all__`
- `scripts/little_loops/cli/auto.py` — parse `args.priority`, pass to `AutoManager`, update epilog
- `scripts/little_loops/cli/parallel.py` — same as auto.py
- `scripts/little_loops/issue_manager.py` — `AutoManager.__init__` + `_get_next_issue` filtering
- `scripts/little_loops/parallel/priority_queue.py` — parallel queue filtering

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — re-exports; update `__all__` if needed
- Any code that constructs `AutoManager` directly in tests

### Similar Patterns
- `parse_issue_types` / `add_type_arg` / `type_prefixes` in `issue_manager.py` — exact pattern to follow

### Tests
- `scripts/tests/test_cli.py` — add tests for `--priority` parsing, invalid values, passthrough to `AutoManager`
- `scripts/tests/test_priority_queue.py` — add filter coverage
- `scripts/tests/test_issue_manager.py` — add `priority_filter` filtering tests

### Documentation
- `docs/reference/API.md` — `AutoManager` signature
- `CLAUDE.md` epilog examples (if updated)

### Configuration
- N/A

## Implementation Steps

1. Add `parse_priorities` and `add_priority_arg` to `cli_args.py`; extend both `add_common_auto_args` and `add_common_parallel_args`
2. Wire `--priority` in `auto.py` and `parallel.py` (parse + pass to manager)
3. Add `priority_filter` param and filtering logic to `AutoManager` in `issue_manager.py`
4. Add the same filtering to `priority_queue.py` for parallel mode
5. Add tests in `test_cli.py`, `test_issue_manager.py`, `test_priority_queue.py`
6. Update epilog examples and API docs

## Scope Boundaries

- Out of scope: filtering by priority range (e.g., "P0 through P2") — only exact set matching
- Out of scope: changing the sort order (issues still sorted by priority numerically within the filtered set)
- Out of scope: `ll-sprint` (sprints are curated lists; priority filtering is less relevant there)

## Impact

- **Priority**: P3 - Useful QoL improvement; not blocking any workflow
- **Effort**: Small - Direct clone of existing `--type` filter pattern; ~5 files, minimal new logic
- **Risk**: Low - Additive only; no existing behavior changes; `None` default preserves backward compat
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `ll-auto`, `ll-parallel`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

**Open** | Created: 2026-03-18 | Priority: P3
