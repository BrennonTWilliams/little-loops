---
id: BUG-2344
title: "is_runnable_loop is non-deterministic within a process for from:-inheritance loops"
type: BUG
priority: P3
status: open
captured_at: "2026-06-27T18:13:55Z"
discovered_date: "2026-06-27"
discovered_by: capture-issue
---

# BUG-2344: is_runnable_loop is non-deterministic within a process for from:-inheritance loops

## Summary

`is_runnable_loop` returns different results for `oracles/generator-evaluator-cli.yaml` (a `from:`-inheritance oracle) depending on whether `resolve_inheritance` has been exercised earlier in the same process. Cold call → `False` (non-runnable, total 95); warm call → `True` (runnable, total 96). `ll-verify-docs` runs cold today so the expected count is 95 and the check passes — but this is a latent flake: any code path that warms the inheritance resolver before `ll-verify-docs` counts loops will push the total to 96 and break the doc check.

## Current Behavior

Within a single Python process:

- **Cold** (first invocation, `resolve_inheritance` / lazy import of `_helpers` not yet exercised): `is_runnable_loop("scripts/little_loops/loops/oracles/generator-evaluator-cli.yaml")` → `False`. Builtin loop total = 95.
- **Warm** (after any earlier call that exercises `resolve_inheritance`): same path → `True`. Total = 96.

`ll-verify-docs` currently runs cold (→ 95, passes). If any future code warms the resolver before `_count_loops()` runs, the doc check will expect 96 and fail intermittently.

## Steps to Reproduce

1. Ensure `oracles/generator-evaluator-cli.yaml` exists (a `from:`-inheritance oracle under `scripts/little_loops/loops/oracles/`).
2. In a fresh Python process, call `is_runnable_loop("scripts/little_loops/loops/oracles/generator-evaluator-cli.yaml")` — observe it returns `False` (cold state, total count = 95).
3. Call any code path that exercises `resolve_inheritance` (e.g., import `little_loops.fsm.fragments` or run any loop resolution).
4. Call `is_runnable_loop` again on the same path — observe it now returns `True` (warm state, total count = 96).
5. Confirm non-determinism: same file path, same process, different return value depending on prior call order.

## Expected Behavior

`is_runnable_loop` must return a consistent, deterministic result for the same file regardless of prior call history in the process. A `from:`-inheritance oracle that fully resolves to a loop with `name`, `initial`, and `states`/`flow` must always return `True`.

## Root Cause

`is_runnable_loop` (`scripts/little_loops/fsm/validation.py:2091`) calls `resolve_inheritance` inside a broad `except Exception: return False` guard. `resolve_inheritance` (`scripts/little_loops/fsm/fragments.py:154`) uses a **lazy import**:

```python
# fragments.py:206-207
from little_loops.cli.loop._helpers import resolve_loop_path
```

On a cold call this lazy import runs for the first time; if any import-order side-effect or transient state causes an exception to propagate into the `except Exception` block, `is_runnable_loop` silently returns `False`. On a warm call the import is already cached and the resolution succeeds.

The specific file affected: `oracles/generator-evaluator-cli.yaml` has `from: generator-evaluator`. `resolve_loop_path` looks for `generator-evaluator.yaml` in the same `oracles/` directory — the file exists — so the resolution itself is sound. The failure must be in the lazy-import or some module-level side-effect triggered only on first call.

Relevant locations:
- `is_runnable_loop` — `scripts/little_loops/fsm/validation.py:2071`
- `resolve_inheritance` lazy import — `scripts/little_loops/fsm/fragments.py:206`
- `_count_loops` in verify-docs — `scripts/little_loops/doc_counts.py:146`

## Motivation

`ll-verify-docs` is a CI-gate command. Non-deterministic loop counts mean CI can pass locally (cold) and fail on a CI server that imports modules in a different order, or vice versa. This is especially risky as more `from:`-inheritance loops are added (BUG-2344 is the first but `create-loop` now generates this pattern for oracle variants).

## Proposed Solution

Two complementary fixes:

**Fix A — eager import (minimal change):** Move the lazy import in `resolve_inheritance` to the module top-level in `fragments.py`. The lazy import comment says "to avoid circular import" — verify whether the circular dependency still exists (it was added for `fsm/executor.py:410` which may have been restructured). If no circular import exists today, promote to a top-level import and the cold/warm difference disappears.

**Fix B — propagate exceptions from `is_runnable_loop`:** Instead of a broad `except Exception: return False`, narrow the guard to only catch `(OSError, yaml.YAMLError, FileNotFoundError)`. Re-raise `ImportError` or `RuntimeError` so cold-call failures are loud (test failures) rather than silent wrong-count bugs.

**Recommended:** Apply both. Fix A eliminates the trigger; Fix B ensures any future lazy-import-style issues surface as test errors, not silent miscounts.

**Test:** Add a test in `test_builtin_loops.py` that calls `is_runnable_loop` twice on `generator-evaluator-cli.yaml` in a fresh subprocess (cold) and asserts both return `True`, then calls it again in-process (warm) and asserts the same.

## Implementation Steps

1. Check whether the circular-import concern in `fragments.py:204` is still valid by attempting to promote the lazy import to the top of the file and running `python -m mypy scripts/little_loops/` + test suite.
2. If no circular import: promote the import and remove the comment.
3. Narrow the `except` clause in `is_runnable_loop` to `(OSError, yaml.YAMLError, FileNotFoundError)`.
4. Add a regression test: call `is_runnable_loop` on the oracle file both before and after any other code exercises `resolve_inheritance`; assert both return `True`.
5. Update `doc_counts.py` expected count comment to note that `from:`-inheritance loops count as runnable.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/fragments.py` — promote lazy import to module-level in `resolve_inheritance`
- `scripts/little_loops/fsm/validation.py` — narrow `except Exception` to `(OSError, yaml.YAMLError, FileNotFoundError)` in `is_runnable_loop`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/doc_counts.py` — `_count_loops` calls `is_runnable_loop`; update expected count comment to note `from:`-inheritance loops count as runnable

### Similar Patterns
- Other `from:`-inheritance loops in `scripts/little_loops/loops/oracles/` that may exhibit the same cold/warm discrepancy

### Tests
- `scripts/tests/test_builtin_loops.py` — add regression test asserting `is_runnable_loop` returns `True` for `generator-evaluator-cli.yaml` both before and after any code exercises `resolve_inheritance`

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — latent flake; CI currently passes cold but will break intermittently as more `from:`-inheritance loops are added via `create-loop`
- **Effort**: Small — two targeted changes (promote import, narrow exception guard) plus one regression test
- **Risk**: Low — fix is contained to `fragments.py` import order and `validation.py` exception scope; no public API change
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `loops`, `non-deterministic`, `captured`

## Status

**Open** | Created: 2026-06-27 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-06-27T18:16:40 - `6eafd1d5-40d0-4472-a29e-7de46e962138.jsonl`
- `/ll:capture-issue` - 2026-06-27T18:13:55Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/46b79929-8b51-4525-bc64-06d247303c56.jsonl`
