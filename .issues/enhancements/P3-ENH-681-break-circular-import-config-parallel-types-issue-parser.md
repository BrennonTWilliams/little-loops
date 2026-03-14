---
discovered_commit: 3e9beea
discovered_branch: main
discovered_date: 2026-03-12
discovered_by: audit-architecture
focus_area: integration
confidence_score: 96
outcome_confidence: 93
---

# ENH-681: Break circular import: config <-> parallel.types <-> issue_parser

## Summary

Architectural issue found by `/ll:audit-architecture`.

Circular dependency detected on a critical import path:
`config` -> `parallel.types` -> `issue_parser` -> `config`

## Motivation

Circular imports on a path involving the central `config` module are the most dangerous kind: any new code touching these three modules risks triggering an `ImportError` depending on import order. The cycle also prevents `issue_parser` and `parallel.types` from being used in isolation (e.g., in tests or tools) without dragging in the full config graph.

## Location

- **File**: `scripts/little_loops/config.py`, `scripts/little_loops/parallel/types.py`, `scripts/little_loops/issue_parser.py`
- **Module**: `little_loops.config`, `little_loops.parallel.types`, `little_loops.issue_parser`

## Finding

### Current State

Three core modules form a circular import triangle. All three legs are already guarded with `TYPE_CHECKING`, so no runtime `ImportError` occurs today. The structural hazard is latent — the cycle exists architecturally but is mitigated by existing patterns.

**Exact import lines (all three legs):**

- `config.py:14-15` → `parallel/types.py` — TYPE_CHECKING guard (return-type annotation on `create_parallel_config`)
- `config.py:841` → `parallel/types.py` — **Runtime deferred import** (inside method body; fires on every call to `create_parallel_config`)
- `parallel/types.py:15-16` → `issue_parser.py` — TYPE_CHECKING guard (`IssueInfo` field type on `QueuedIssue.issue_info`)
- `issue_parser.py:16-17` → `config.py` — TYPE_CHECKING guard (`BRConfig` parameter annotations on 4 functions)

All three files have `from __future__ import annotations` (config.py:7, parallel/types.py:7, issue_parser.py:6), which makes annotation evaluation lazy — the `TYPE_CHECKING` guards are effective.

**The one genuine runtime concern:** `config.py:841` has a function-body `from little_loops.parallel.types import ParallelConfig` inside `create_parallel_config()`. This is the deferred/lazy import pattern — it works today because by the time this method is called, both modules are already loaded, but it is a code smell (hidden dependency, not visible at module top level).

### Impact

- **Development velocity**: New imports touching these modules risk import errors
- **Maintainability**: Circular imports make refactoring risky and reasoning about load order difficult
- **Risk**: Can cause `ImportError` at runtime depending on import order

## Proposed Solution

The `TYPE_CHECKING` guard approach is already in use and working. The targeted fix is to eliminate the deferred runtime import at `config.py:841` — the only genuine architectural smell remaining.

**Option A (preferred — minimal change):** Move `ParallelConfig` to the top-level `TYPE_CHECKING` block in `config.py` and make `create_parallel_config` return `Any` at runtime, or restructure the method to receive a pre-built `ParallelConfig` from the caller.

**Option B:** Extract `ParallelConfig` (and related parallel types) to a `little_loops/parallel/models.py` leaf module (pure dataclasses, no `little_loops` imports) modeled after `dependency_mapper/models.py` and `issue_history/models.py`. `config.py` can then import `ParallelConfig` at the top level without risk. `parallel/types.py` becomes a thin re-export or merges into `parallel/models.py`.

**Option C (overkill — avoid):** Create a `core_types.py`. Research found no need for this — the cycle is already handled by existing patterns and no shared types module is necessary.

### Recommended Approach

Option A is the minimum fix: make the one runtime import in `config.py:841` type-safe by promoting it to the top-level guard and refactoring `create_parallel_config` to not need a runtime import of the return type (it already imports its field values from `self._parallel` which is a `ParallelAutomationConfig`, not a `ParallelConfig`).

## Scope Boundaries

- Only change import structure; no API or behavior changes
- Do not modify the public interface of any of the three modules
- Verify with `python -c "import little_loops"` and full test suite after the fix

## Implementation Steps

1. **Confirm the runtime import** at `scripts/little_loops/config.py:841` (`from little_loops.parallel.types import ParallelConfig` inside `create_parallel_config`) — this is the only non-guarded cross-leg import
2. **Remove the deferred import** at `config.py:841`; `ParallelConfig` is already in the `TYPE_CHECKING` block at `config.py:14-15` (covers the return annotation at `config.py:818`)
3. **Make `create_parallel_config` instantiate `ParallelConfig` without a local import** — since this method already has all field values from `self._parallel` (a `ParallelAutomationConfig`), the pattern is already complete; the runtime import just needs to be removed and replaced with a top-level import or restructured call
4. **Run `python -c "import little_loops.config; import little_loops.parallel.types; import little_loops.issue_parser"`** to verify no `ImportError`
5. **Run `python -m pytest scripts/tests/test_config.py scripts/tests/test_parallel_types.py scripts/tests/test_issue_parser.py -v`** to verify all tests pass

## Integration Map

### Files to Modify
- `scripts/little_loops/config.py` — remove runtime import at line 841; `create_parallel_config` is the only method that needs to change

### Files to Leave Unchanged (already correctly guarded)
- `scripts/little_loops/parallel/types.py` — TYPE_CHECKING guard at lines 15-16 is correct; no change needed
- `scripts/little_loops/issue_parser.py` — TYPE_CHECKING guard at lines 16-17 is correct; no change needed

### Dependent Files (Callers of `create_parallel_config`)
- `scripts/little_loops/parallel/orchestrator.py` — calls `config.create_parallel_config()`
- `scripts/little_loops/cli/parallel.py` — calls `config.create_parallel_config()`

### Tests
- `scripts/tests/test_config.py` — primary test coverage for `BRConfig`; will catch regressions
- `scripts/tests/test_parallel_types.py` — tests `QueuedIssue`, `ParallelConfig`; imports `IssueInfo` directly
- `scripts/tests/test_issue_parser.py` — imports `BRConfig` for fixtures via `conftest.py`

### Similar Patterns to Follow
- `scripts/little_loops/dependency_mapper/models.py` — pure-dataclass leaf module, no internal imports (model for Option B if pursued)
- `scripts/little_loops/issue_history/models.py` — same leaf-module pattern

### No New Files Required
- `core_types.py` is unnecessary — all three legs are already `TYPE_CHECKING`-guarded; only `config.py:841` needs fixing

## Impact Assessment

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`

---

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- The three referenced files exist (`config.py`, `parallel/types.py`, `issue_parser.py`). A runtime import test shows no current `ImportError` — Python resolves the cycle at startup — but the structural circular dependency chain (config → parallel.types → issue_parser → config) is a latent architectural hazard. The issue correctly identifies the problem as a maintainability/fragility risk even if it doesn't presently fail.

## Status

**Open** | Created: 2026-03-12 | Priority: P3
