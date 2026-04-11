---
discovered_date: 2026-04-11
discovered_by: capture-issue
---

# ENH-1037: Remove Trivial Init Attribute Tests in test_worker_pool.py

## Summary

`test_worker_pool.py` contains ~15% trivial tests (out of 92) that only assert `pool.<attr> == default_value` — verifying that Python's `__init__` stored an argument correctly, not any logic. Remove these while keeping tests that verify real side effects (directory creation, executor initialization, etc.).

## Current Behavior

Tests like `test_init_sets_attributes` assert `pool.parallel_config == default_parallel_config`. These pass as long as Python can run `self.x = x`, which is guaranteed by the language. They provide no behavioral signal.

## Expected Behavior

Only `__init__` tests that verify side effects remain (e.g., directory creation, executor setup, threading configuration). Pure attribute-storage tests are removed. Test count reduced by ~12–15.

## Motivation

Attribute-storage tests for `self.x = x` assignments add no value — they can only fail if the attribute name is typo'd, which would immediately surface in any real test. They make the suite feel more comprehensive than it is.

## Proposed Solution

For each test in `test_worker_pool.py`:
- If the assertions are purely `assert pool.<attr> == <input_arg>` with no side-effect verification → delete
- If assertions cover directory creation, executor init, threading behavior, or derived state → keep

## Integration Map

### Files to Modify
- `scripts/tests/test_worker_pool.py`

### Dependent Files (Callers/Importers)
- N/A — test-only change

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_worker_pool.py` — the file being modified

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/test-quality-audit.md:9-13` — test count table (`~4,061` total, `87` files) becomes stale; this issue removes ~2 tests from `test_worker_pool.py` [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Trivial tests to delete (`class TestWorkerPoolInit`, L164):**
- `test_init_sets_attributes` (L167-189): Asserts `pool.parallel_config == default_parallel_config`, `pool.br_config == br_config`, `pool.logger == mock_logger`, `pool.repo_path == temp_repo_with_config` — pure `self.x = x` checks. Also asserts `pool._executor is None`, `pool._active_workers == {}`, `pool._active_processes == {}` — initial state that is trivially guaranteed by `= None` / `= {}` in `__init__`. **Delete.**

**Borderline trivial tests in `class TestWorkerResultInterrupted`:**
- `test_interrupted_defaults_to_false` (L122-131): Asserts dataclass default value `result.interrupted is False`. Trivial — the dataclass field default is `False`, this tests Python's dataclass behavior. **Candidate for deletion.**
- `test_interrupted_can_be_set_true` (L133-144): Asserts `interrupted=True` when explicitly passed. Borderline — tests correct field wiring for a non-default constructor path. **Keep** (it verifies the field is functional, not just stored).

**Tests to preserve (`class TestWorkerPoolInit`):**
- `test_init_creates_git_lock_if_not_provided` (L190-206): Asserts `pool._git_lock is not None` and `isinstance(pool._git_lock, GitLock)` — tests side-effect of creating a new `GitLock` object. **Keep.**
- `test_init_uses_provided_git_lock` (L208-225): Asserts `pool._git_lock is mock_git_lock` — tests the dependency-injection path (external `git_lock` is wired correctly). **Keep.**

**Other meaningful `__init__`-adjacent tests that stay:**
- `test_interrupted_serialization` (L147-161): Tests `to_dict()`/`from_dict()` round-trip for `interrupted` field. **Keep.**
- `test_start_creates_executor` (L231): Tests `ThreadPoolExecutor` creation side effect. **Keep.**
- `test_start_creates_worktree_base_directory` (L242): Tests directory creation side effect. **Keep.**

## Implementation Steps

1. Read `test_worker_pool.py` and list all `test_init_*` or attribute-checking tests
2. For each: classify as trivial (pure attribute storage) vs meaningful (side effects)
3. Delete trivial tests
4. Run `python -m pytest scripts/tests/test_worker_pool.py -v --tb=short` and confirm remaining tests pass
5. Verify test count drops by ~12–15

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete targets with verdict:_

| Test | Line | Verdict | Reason |
|------|------|---------|--------|
| `test_interrupted_defaults_to_false` | L122 | **Delete** | Tests Python dataclass default `= False` |
| `test_init_sets_attributes` | L167 | **Delete** | Pure `self.x = x` attribute-storage checks |
| `test_init_creates_git_lock_if_not_provided` | L190 | **Keep** | Tests GitLock creation side effect |
| `test_init_uses_provided_git_lock` | L208 | **Keep** | Tests dependency-injection wiring |

**Revised count:** The confirmed trivial targets are 2 tests (L122, L167). The issue estimate of ~12–15 may overcount — review other `test_init_*` functions across the full file to find additional candidates before finalizing the PR count claim.

**Test command:**
```bash
python -m pytest scripts/tests/test_worker_pool.py -v --tb=short
```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/test-quality-audit.md:9-13` — decrement the total test count by ~2 to reflect deleted trivial tests

## Scope Boundaries

- **In scope**: Removing pure attribute-storage `__init__` tests in `scripts/tests/test_worker_pool.py` where assertions are exclusively `pool.<attr> == <input_arg>`
- **Out of scope**: Changes to production code, changes to other test files, removing any test that verifies side effects (directory creation, executor initialization, threading behavior)

## Impact

- **Priority**: P4 - Test quality cleanup, no behavioral change
- **Effort**: Small - Straightforward deletion after classification
- **Risk**: Low - Tests only; no production code changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`test-quality`, `test_worker_pool`, `captured`

## Status

**Open** | Created: 2026-04-11 | Priority: P4

---

## Session Log
- `/ll:wire-issue` - 2026-04-11T20:12:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a526cc2e-06c1-44e3-add0-5ba3cb7b1190.jsonl`
- `/ll:refine-issue` - 2026-04-11T20:08:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2f0bc40-5233-4c1b-a17d-6bd5566483a9.jsonl`
- `/ll:format-issue` - 2026-04-11T20:03:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da64ad23-684f-4724-8a57-4063931ce01c.jsonl`
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9439fb7-57cc-417c-9114-6eea87ed8705.jsonl`
