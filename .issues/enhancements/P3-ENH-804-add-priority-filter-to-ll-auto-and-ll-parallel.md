---
id: ENH-804
type: ENH
priority: P3
status: open
discovered_date: 2026-03-18
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 93
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

1. Add `parse_priorities(value: str | None) -> set[str] | None` to `cli_args.py` — validates against `{"P0","P1","P2","P3","P4","P5"}`, raises `sys.exit(2)` (same pattern as `parse_issue_types`, not `argparse.ArgumentTypeError`) on invalid input.
2. Add `add_priority_arg(parser)` to `cli_args.py` — `--priority/-p` accepting comma-separated list.
3. Add `add_priority_arg` to `add_common_auto_args` only (not `add_common_parallel_args` — `parallel.py` adds args individually, not via that helper).
4. Wire the parsed set into `AutoManager.__init__` as `priority_filter: set[str] | None`.
5. In `AutoManager._get_next_issue`, add filter clause: `i.priority in self.priority_filter` (or skip if `None`). Also apply to the `remaining` set at `issue_manager.py:793-797`.
6. Update `parallel.py` to use `parse_priorities()` instead of its current bare `split(",")+upper()` for validation parity.
7. Update epilog in `auto.py` and API docs.

Priority is read from `IssueInfo.priority` (from filename prefix `P3-ENH-804-...` → `"P3"`), already parsed.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**ll-parallel is already fully implemented.** The remaining work is ll-auto only:

- `parallel.py:64-69` — `--priority/-p` arg already in the parser, help text "Comma-separated priorities to process (default: all)"
- `parallel.py:156-158` — priority_filter already parsed: `[p.strip().upper() for p in args.priority.split(",")]`
- `parallel.py:183` — `priority_filter=priority_filter` already passed to `config.create_parallel_config()`
- `priority_queue.py:214-253` — `scan_issues(priority_filter: list[str] | None = None)` already implemented and filtering applied at line 251
- `parallel/types.py:319` — `ParallelConfig.priority_filter` field already exists (default all priorities)
- Tests already exist: `test_priority_queue.py:667`, `test_parallel_types.py:734,887,904,960,973,1000`, `test_cli.py:167,172,1465`

**Gap**: `parallel.py:157-159` does no validation — accepts `P9`, `INVALID`, etc. silently. The new `parse_priorities()` should fix this in both tools.

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
- `scripts/little_loops/cli_args.py` — add `VALID_PRIORITIES`, `parse_priorities`, `add_priority_arg`; call `add_priority_arg` from `add_common_auto_args`; update `__all__`
- `scripts/little_loops/cli/auto.py` — import `parse_priorities`, parse `args.priority`, pass `priority_filter` to `AutoManager`, add epilog example
- `scripts/little_loops/issue_manager.py` — add `priority_filter: set[str] | None = None` to `AutoManager.__init__:682`; add filter to `_get_next_issue:770-777` (candidates) and `_get_next_issue:793-797` (remaining)
- `scripts/little_loops/cli/parallel.py` — replace bare `split(",")+upper()` at line 156-158 with `parse_priorities()` call for validation parity

### Already Implemented (No Changes Needed)
- `scripts/little_loops/parallel/priority_queue.py:214-253` — `scan_issues(priority_filter=...)` fully implemented
- `scripts/little_loops/parallel/types.py:319` — `ParallelConfig.priority_filter` field exists
- `scripts/little_loops/cli/parallel.py:63-70` — `--priority/-p` arg already in parser
- `scripts/little_loops/cli/parallel.py:183` — `priority_filter` already passed to `create_parallel_config`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — re-exports; update `__all__` if needed
- Any code that constructs `AutoManager` directly in tests

### Similar Patterns
- `parse_issue_types` / `add_type_arg` / `type_prefixes` in `issue_manager.py:770-797` — exact pattern to clone for priority
- `cli_args.py:262-289` — `parse_issue_types` implementation (use same `sys.exit(2)` error pattern, not `argparse.ArgumentTypeError`)
- `cli_args.py:296-308` — `add_common_auto_args` where `add_priority_arg` should be inserted

### Tests
- `scripts/tests/test_cli_args.py:131-182` — add `TestParsePriorities` class following `TestParseIssueTypes` pattern (None returns None, single value, multiple values, whitespace, invalid exits with code 2); add `TestAddPriorityArg` class; update `TestAddCommonAutoArgs` to assert `--priority` is wired
- `scripts/tests/test_cli.py` — add ll-auto `--priority` parsing tests and invalid value tests (parallel already covered at lines 167, 172, 1465)
- `scripts/tests/test_issue_manager.py` — add `priority_filter` filtering tests for `AutoManager._get_next_issue`
- `scripts/tests/test_priority_queue.py:667` — already covers `scan_issues` filter; no changes needed
- `scripts/tests/test_parallel_types.py:734,887,904,960,973,1000` — already covers `ParallelConfig.priority_filter`; no changes needed

### Documentation
- `docs/reference/API.md` — update `AutoManager` signature
- Epilog in `auto.py` — add `%(prog)s --priority P1,P2  # Only process P1 and P2 issues`

### Configuration
- N/A

## Implementation Steps

1. Add `VALID_PRIORITIES`, `parse_priorities`, and `add_priority_arg` to `cli_args.py`; call `add_priority_arg` from `add_common_auto_args`; add all three to `__all__`
2. In `auto.py`: import `parse_priorities`, parse `args.priority` → `priority_filter`, pass to `AutoManager`; add epilog example
3. In `issue_manager.py` `AutoManager.__init__` (line 682): add `priority_filter: set[str] | None = None` param; store as `self.priority_filter`
4. In `issue_manager.py` `_get_next_issue` (lines 770-797): add `and (self.priority_filter is None or i.priority in self.priority_filter)` to candidates filter AND to remaining set filter
5. In `parallel.py` (line 157-159): replace bare `args.priority.split(",")` with `parse_priorities(args.priority)` (validation fix); import `parse_priorities`
6. Add tests in `test_cli.py` (ll-auto `--priority` parsing, invalid values) and `test_issue_manager.py` (`priority_filter` filtering)
7. Update `AutoManager` signature in `docs/reference/API.md`

## Scope Boundaries

- Out of scope: filtering by priority range (e.g., "P0 through P2") — only exact set matching
- Out of scope: changing the sort order (issues still sorted by priority numerically within the filtered set)
- Out of scope: `ll-sprint` (sprints are curated lists; priority filtering is less relevant there)
- **ll-parallel full implementation is already done** — Step 5 above is a validation-only fix (parallel.py line 157-159 currently accepts any string silently)

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
- `/ll:confidence-check` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/56e068a2-169f-4e14-b8ca-00caa619a741.jsonl`
- `/ll:refine-issue` - 2026-03-18T21:38:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/18f420b1-0c39-4794-9ebd-f0386a21c8dd.jsonl`
- `/ll:refine-issue` - 2026-03-18T21:32:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3aa0fcd8-e52b-4672-b5cc-4af0e7f14784.jsonl`

- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

**Open** | Created: 2026-03-18 | Priority: P3
