---
id: BUG-1760
title: autodev scope declared as issue IDs not whole repo, allows concurrent conflicting runs
type: BUG
status: cancelled
priority: P3
captured_at: '2026-05-28T00:42:55Z'
discovered_date: '2026-05-28'
discovered_by: capture-issue
labels:
- bug
- autodev
- ll-loop
- concurrency
cancelled_reason: |
  Root cause misdiagnosed. autodev.yaml has no scope field, defaults to ["."]
  (run.py:264), so two autodev runs already conflict via _paths_overlap. The
  May 27 incident was likely sequential runs (no .lock files from that day remain).
  Actual desired behavior (parallel autodev on disjoint issues) is a feature, not
  a bug — deferred to FEAT-1789.
---

# BUG-1760: autodev scope declared as issue IDs not whole repo, allows concurrent conflicting runs

## Summary

`LockManager._scopes_overlap()` compares scope paths as strings. If two `ll-loop run autodev` invocations use different issue ID sets (e.g. `ENH-1699,ENH-1700` vs `BUG-031`), the path-based overlap check finds no conflict and both acquire locks. Both autodev instances then operate concurrently on the same git repo, racing on git operations, issue status writes, and `.loops/.running/` state files.

## Root Cause

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Function**: `LockManager._scopes_overlap()` (line 242) → `_paths_overlap()` (line 250)
- **Explanation**: The overlap algorithm at `concurrency.py:242-248` performs a Cartesian product comparison of every path in scope1 against every path in scope2 via `_paths_overlap()`. That method (`concurrency.py:250-275`) detects overlap as (a) exact path equality or (b) one path is a parent directory of the other (bidirectional `Path.relative_to()`). There is **no loop-name-based conflict detection** anywhere in `LockManager`. Two instances of the same loop with disjoint scope tokens are siblings under path comparison and always return no-conflict.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Current autodev.yaml state**: `scripts/little_loops/loops/autodev.yaml` has **no `scope:` field** (confirmed by `git log` — never has). It defaults to `["."]` via `cmd_run()` at `scripts/little_loops/cli/loop/run.py:264` (`scope = fsm.scope or ["."]`) and the redundant fallback in `LockManager.acquire()` at `concurrency.py:109-111`. With the default, two autodev instances resolve `"."` to the same absolute project path and `_paths_overlap()` returns True — so they DO conflict under current code.
- **The real vulnerability is architectural**: `_paths_overlap()` (`concurrency.py:250-275`) is purely a filesystem-path comparison (`Path.relative_to()`). It has zero awareness of what the paths represent semantically. If any loop YAML (or a user-level `.loops/autodev.yaml` override) declared `scope:` tokens that are not shared filesystem paths — e.g., issue IDs like `["ENH-1699", "ENH-1700"]` — they would normalize to sibling paths that `_paths_overlap()` classifies as non-overlapping. Neither path needs to exist on disk for the non-overlap verdict.
- **CWD sensitivity**: `_normalize_path()` (`concurrency.py:277-279`) uses `Path(path).resolve()`, which resolves relative to process CWD. If two `ll-loop run autodev` invocations were started from significantly different working directories, `"."` would resolve to different absolute paths and could potentially bypass the overlap check if those directories are siblings rather than parent-child.
- **ENH-1354 conflict**: `test_concurrent_same_name_non_overlapping_scopes_both_acquire` at `scripts/tests/test_concurrency.py:545` explicitly validates that two instances of the same loop name with non-overlapping scopes BOTH succeed — this is intentional design. A blanket loop-name-based conflict would break this. Any name-based guard must be opt-in (e.g., a `singleton: true` YAML field).
- **Only 2 of ~60 loop YAMLs declare explicit scope**: `dead-code-cleanup.yaml` (`scope: ["scripts/"]`) and `docs-sync.yaml` (`scope: ["docs/", "*.md"]`). All others (including autodev) rely on the `["."]` default.

## Current Behavior

During the 2026-05-27 incident: a second `ll-loop run autodev BUG-031` was started at 7:14 PM while `ll-loop run autodev ENH-1699,ENH-1700,ENH-1701,ENH-1702` was still running (since 3:42 PM). Both acquired `.lock` files in `.loops/.running/` without conflict. Both had active lock files simultaneously.

## Steps to Reproduce

1. Start a long-running autodev session with multiple issues: `ll-loop run autodev ENH-1699,ENH-1700,ENH-1701,ENH-1702`
2. While that session is still running, start a second autodev session with different issues: `ll-loop run autodev BUG-031`
3. Observe: Both sessions acquire `.lock` files in `.loops/.running/` without conflict
4. Observe: Both instances operate concurrently on the same git repo, racing on git operations and state files

## Expected Behavior

Only one autodev instance should run at a time because all autodev runs share the git working tree. A second `ll-loop run autodev` should either block (if `--queue`) or exit with a clear conflict message.

## Motivation

This bug fix would:
- Prevent concurrent autodev runs from corrupting git repository state and `.loops/.running/` state files
- Ensure issue status writes are serialized correctly when multiple autodev instances target the same repo
- Eliminate a class of hard-to-diagnose race condition bugs caused by concurrent harness operations on shared filesystem state

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The autodev YAML (`scripts/little_loops/loops/autodev.yaml`) currently has **no `scope:` field**, defaulting to `["."]` at `run.py:264`. Under current code, two `ll-loop run autodev` invocations both default to `["."]` → same absolute path → `_paths_overlap()` detects the conflict. The fix is defense-in-depth to prevent the vulnerability from manifesting.

**Three implementation options identified:**

**Option A: Explicit `scope: ["."]` in autodev.yaml (YAML-only, minimal)**
Add `scope: ["."]` to `scripts/little_loops/loops/autodev.yaml`. This is a no-op under current defaults but documents intent and prevents a future misconfiguration from introducing the vulnerability. No code changes. No test changes needed.

**Option B: `singleton: true` YAML field on LockManager (opt-in name-based guard)**
Add a `singleton` boolean to `FSMLoop` schema (`schema.py:874`) and `ScopeLock` dataclass (`concurrency.py:46`). When `singleton: true`, `LockManager.find_conflict()` blocks ANY concurrent instance of the same loop name regardless of scope overlap. This preserves ENH-1354 (same-name instances on non-overlapping scopes) for loops that don't opt in. Changes needed:
- `scripts/little_loops/fsm/schema.py` — add `singleton: bool = False` to `FSMLoop`
- `scripts/little_loops/fsm/concurrency.py` — add `singleton` to `ScopeLock`; add name-match check in `find_conflict()`
- `scripts/tests/test_concurrency.py` — add test for singleton conflict, verify non-singleton same-name still allowed

**Option C: Both (defense-in-depth)**
Apply Option A to autodev.yaml AND implement Option B for systemic protection. Any loop that must only run one-at-a-time can set `singleton: true`.

```yaml
# Option A — add to autodev.yaml (already the default, explicit is better):
scope:
  - "."
```

```yaml
# Option B — new field for any loop that must be exclusive:
singleton: true
```

## Implementation Steps

### If Option A (YAML-only scope fix):
1. Add `scope: ["."]` to `scripts/little_loops/loops/autodev.yaml` (between `timeout` and `on_handoff` lines)
2. Verify with `ll-loop validate autodev` — scope field must parse correctly
3. No code or test changes required (default is already `["."]`)

### If Option B (singleton name-based guard):
1. Add `singleton: bool = False` field to `FSMLoop` dataclass at `scripts/little_loops/fsm/schema.py:874`
2. Add `singleton: bool = False` field to `ScopeLock` dataclass at `scripts/little_loops/fsm/concurrency.py:46`; include in `to_dict()` / `from_dict()`
3. In `LockManager.find_conflict()` at `concurrency.py:154`, after the existing scope overlap check, add a name-match check: if `lock.singleton and lock.loop_name == candidate_loop_name` → conflict
4. Pass `singleton` through `LockManager.acquire()` → `ScopeLock` constructor
5. In `cmd_run()` at `run.py:271`, pass `fsm.singleton` to `acquire()` (or read it from the lock file in `find_conflict`)
6. Add test at `test_concurrency.py` in `TestMultiInstanceSameName`: `test_singleton_loop_conflicts_on_name_regardless_of_scope` — acquires singleton lock on `["src/"]`, second acquire on `["lib/"]` must fail
7. Add test: non-singleton same-name on non-overlapping scopes still succeeds (ENH-1354 preserved)
8. Add `singleton: true` to `autodev.yaml`

### If Option C (both):
1. Apply Option A steps 1-2
2. Apply Option B steps 1-8

## API/Interface

The autodev loop YAML `scope:` field should be:
```yaml
scope:
  - "."
```
Not:
```yaml
scope:
  - "ENH-1699"
  - "ENH-1700"
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/concurrency.py` — `LockManager._scopes_overlap()` method
- `.loops/autodev.yaml` (or similar) — autodev loop definition YAML

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:264` — `cmd_run()` resolves `scope = fsm.scope or ["."]`, passes to `acquire()` at line 271
- `scripts/little_loops/cli/loop/_helpers.py:959` — `run_background()` pre-flight `find_conflict()` check using the same `fsm.scope or ["."]` resolution
- `scripts/little_loops/fsm/__init__.py:69-78` — re-exports `LockManager` and `ScopeLock` as public API
- `scripts/little_loops/fsm/schema.py:874` — `FSMLoop.scope: list[str]` field definition; line 989 — `from_dict()` extraction with `data.get("scope", [])` default
- `scripts/little_loops/fsm/persistence.py:460` — `_reconcile_stale_runs()` mirrors `find_conflict()` stale-lock cleanup strategy for `.state.json` files

### Similar Patterns
- `scripts/little_loops/loops/dead-code-cleanup.yaml:8-9` — explicit `scope: ["scripts/"]` (only loop with subdirectory scope)
- `scripts/little_loops/loops/docs-sync.yaml:8-10` — explicit `scope: ["docs/", "*.md"]` (only loop with multi-path scope; glob not expanded — literal `*` char)
- All other ~58 loop YAMLs omit `scope:` entirely, relying on the `["."]` default at `run.py:264`
- `scripts/tests/test_concurrency.py:517-581` — `TestMultiInstanceSameName` class: ENH-1354 deliberately allows same-name concurrent instances on non-overlapping scopes

### Tests
- `scripts/tests/test_concurrency.py:452-514` — `TestPathOverlap`: unit tests for `_paths_overlap()` and `_scopes_overlap()` (same, parent/child, sibling, empty)
- `scripts/tests/test_concurrency.py:517-581` — `TestMultiInstanceSameName`: `test_concurrent_same_name_non_overlapping_scopes_both_acquire` (line 545) — explicitly asserts both succeed
- `scripts/tests/test_concurrency.py:60-255` — `TestLockManager`: acquire/release, conflict detection, stale lock cleanup, empty scope default
- `scripts/tests/test_concurrency.py:256-398` — `TestLockManagerRaceConditions`: TOCTOU fixes (BUG-525 sentinel, BUG-423 missing_ok)
- `scripts/tests/test_cli_loop_background.py:560-613` — `test_scope_conflict_returns_1`, `test_queue_bypasses_preflight_check` (BUG-1771 pre-flight pattern)

### Documentation
- `docs/guides/LOOPS_GUIDE.md:1697-1721` — "Scope-Based Concurrency" section documenting `scope:` field, `--queue`, FIFO ordering
- `docs/reference/API.md:4803-4837` — `ScopeLock` dataclass and `LockManager` class API docs

### Configuration
- N/A

## Impact

- **Priority**: P3 — Can corrupt repo state if concurrent autodev runs collide on git operations and state files; requires specific timing to trigger
- **Effort**: Small — Primary fix is a one-line YAML scope change; lock-semantics update is a few lines in `_scopes_overlap()`
- **Risk**: Low — Well-understood locking mechanism; scope change is configuration-only with no code path changes
- **Breaking Change**: No

## Related Issues

- BUG-232: TOCTOU race in scope-lock acquisition — different (race during acquire, not scope definition)
- BUG-525: TOCTOU race condition lock acquire — same
- BUG-1359 (done): outer-loop-eval scope conflict with sub-loop — different direction (sub-loop blocked by parent, not two peers)

## Session Log
- `/ll:refine-issue` - 2026-05-29T18:39:22 - `f6c0d464-ab61-4de1-ba48-aea405639ba8.jsonl`
- `/ll:format-issue` - 2026-05-29T18:30:34 - `4c853141-e354-40cd-b5da-dc4005c2b086.jsonl`
- `/ll:capture-issue` - 2026-05-28T00:42:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

**Cancelled** | Created: 2026-05-28 | Priority: P3
