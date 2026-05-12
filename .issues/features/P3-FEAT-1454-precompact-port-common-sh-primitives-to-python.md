---
id: FEAT-1454
type: FEAT
priority: P3
status: done
parent: FEAT-1449
discovered_date: 2026-05-11
completed_at: 2026-05-12T01:32:27Z
discovered_by: issue-size-review
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1454: PreCompact — Port common.sh Primitives to Python (Option B)

## Summary

Port the four `lib/common.sh` primitives needed by the precompact hook into their natural Python homes (Option B decision from FEAT-1449): `atomic_write_json` + `acquire_lock` into `file_utils.py`, `resolve_config_path` into `config/core.py`, and `feature_enabled` into `config/features.py`. Replace the bash-source `TestSharedConfigFunctions` test class with Python-direct equivalents.

## Parent Issue

Decomposed from FEAT-1449: PreCompact Intent — Python Core Handler and Claude Code Adapter

## Depends On

- FEAT-1448 (LLHookEvent/LLHookResult types must exist)

## Covers

Implementation Steps 3 and 8 (partial — TestSharedConfigFunctions replacement + new primitive tests) from FEAT-1449.

## Scope

### Step 3: Extend Python modules

**`scripts/little_loops/file_utils.py`**
- `atomic_write_json(path: Path, data: Any) -> None` — thin wrapper: `atomic_write(path, json.dumps(data, indent=2))` with `json.loads` round-trip validation (the missing step vs. existing `atomic_write`).
- `acquire_lock(path: Path, timeout: float = 10.0) -> ContextManager` — `@contextmanager` using `fcntl.flock(LOCK_EX | LOCK_NB)` with polled retry up to timeout; mirror shell's `flock -w` / `mkdir`-fallback semantics. Preserve the 3-second timeout used by `precompact-state.sh`.

**`scripts/little_loops/config/core.py`**
- `resolve_config_path(project_root: Path) -> Path | None` — standalone function (alongside `BRConfig`) implementing two-step lookup: `.ll/ll-config.json` then `ll-config.json`; does NOT mutate global state. Extend `BRConfig._load_config()` to use it and pick up the root-level fallback (currently absent).

**`scripts/little_loops/config/features.py`**
- `feature_enabled(config_data: dict, dot_path: str) -> bool` — generic dot-path boolean lookup against a parsed config dict. Needed for `TestSharedConfigFunctions` parity; `pre_compact` itself does not call it.

### Step 8 (partial): Migrate TestSharedConfigFunctions

**`scripts/tests/test_hooks_integration.py`**
- Replace `TestSharedConfigFunctions` class (lines 1469-1700) — currently uses `_run_bash()` to `source lib/common.sh` — with Python-direct tests targeting the new functions above.
- Use `monkeypatch.chdir(tmp_path)` instead of manual `os.chdir` / `try/finally`.
- Concurrency tests for `acquire_lock` use `ThreadPoolExecutor` (pattern from existing `test_concurrent_precompact_writes`).

**`scripts/tests/test_config.py`**
- Add `TestResolveConfigPath`: test root-level `ll-config.json` fallback (not currently tested).
- Add `TestFeatureEnabledHelper`: test `feature_enabled(config_dict, "dot.path") -> bool` against truthy and falsy dot-path keys.

**Model after:**
- `scripts/tests/test_ll_issues_atomic_write.py` — `TestAtomicWrite` for `atomic_write_json` + `acquire_lock` tests.
- `scripts/tests/test_hook_intents.py` — dataclass test style.

## Files to Modify

- `scripts/little_loops/file_utils.py`
- `scripts/little_loops/config/core.py`
- `scripts/little_loops/config/features.py`
- `scripts/tests/test_hooks_integration.py` (replace `TestSharedConfigFunctions`)
- `scripts/tests/test_config.py` (add `TestResolveConfigPath`, `TestFeatureEnabledHelper`)
- `scripts/tests/test_file_utils.py` (new file — `TestAtomicWriteJson`, `TestAcquireLock`)

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis._

### Bash Source (being ported)

- `hooks/scripts/lib/common.sh` — actual path of the bash primitives (issue body says `lib/common.sh`; canonical location is `hooks/scripts/lib/common.sh`):
  - `acquire_lock()` lines 8–38 — `flock -w` primary, `mkdir`-fallback poll loop with 0.1s sleep (`max_iterations = timeout * 10`); default timeout 10s
  - `release_lock()` lines 41–54 — clears `mkdir` lock dir and `trap` (flock FD closes on process exit)
  - `atomic_write_json()` lines 59–85 — `mkdir -p $(dirname)`, write to `${target}.tmp.$$`, validate with `jq empty` (skipped if `jq` absent), `mv -f`
  - `ll_resolve_config()` lines 184–192 — `mkdir -p .ll` side effect; sets global `LL_CONFIG_FILE`; checks `.ll/ll-config.json` then `ll-config.json`
  - `ll_feature_enabled()` lines 198–212 — requires `LL_CONFIG_FILE` set and `jq` present; runs `jq -r ".${flag_path} // false"`; returns 0 if `"true"`, else 1

### Python Targets (to add)

- `scripts/little_loops/file_utils.py` — currently only `atomic_write()` (lines 10–26): uses `tempfile.mkstemp(dir=path.parent, suffix=".tmp")` + `os.fdopen` + `os.replace`. **Gap vs. bash `atomic_write_json`**: no `json.loads` round-trip validation, no `mkdir -p` parent. New `atomic_write_json(path, data)` must add both.
- `scripts/little_loops/config/core.py` — `BRConfig._load_config()` (lines 90–96) only checks `<root>/.ll/ll-config.json`. **Gap vs. bash `ll_resolve_config`**: no root-level `ll-config.json` fallback. New standalone `resolve_config_path(project_root)` must implement both candidates without the `mkdir -p .ll` side effect; then `_load_config` should call it.
- `scripts/little_loops/config/features.py` — currently dataclass-only (`CategoryConfig`, `NextIssueConfig`, etc.); no generic dot-path helper. New `feature_enabled(config_data, dot_path) -> bool` traverses split-on-`.` returning `bool(value)` or `False` for missing keys (mirroring jq's `// false` default).

### Bash Callers of the Primitives (verifies signatures must stay compatible)

- `hooks/scripts/precompact-state.sh:72-79` — `acquire_lock "$STATE_LOCK" 3` (3s timeout), then `atomic_write_json`, then `release_lock`; on lock timeout falls through to best-effort unlocked write — this caller behavior is preserved in the *bash adapter*; Python port keeps `acquire_lock` returning a context manager (caller composes the fallback).
- `hooks/scripts/context-monitor.sh:171,220` — `atomic_write_json` and `acquire_lock`
- `hooks/scripts/check-duplicate-issue-id.sh:98` — `acquire_lock`
- `hooks/scripts/context-monitor.sh:20-21`, `user-prompt-check.sh:20,42`, `context-handoff-sentinel.sh:22-23`, `scratch-pad-redirect.sh:46-47`, `issue-completion-log.sh:37`, `check-duplicate-issue-id*.sh` — `ll_resolve_config` + `ll_feature_enabled` / `ll_config_value`

(Note: these bash callers continue to use the bash primitives; FEAT-1454 only adds Python parity for use by the new precompact Python handler. Bash callers are not migrated by this issue.)

### Python Callers of Existing `atomic_write`

- `scripts/little_loops/session_log.py:129`
- `scripts/little_loops/issue_lifecycle.py:813,816,819`
- `scripts/little_loops/issues/anchor_sweep.py:96`

These continue to use the existing string-content `atomic_write`. The new `atomic_write_json` is additive; do not change existing call sites.

### Similar Patterns to Model After

- **JSON + atomic-write pattern**: `scripts/little_loops/fsm/rate_limit_circuit.py:_write_atomic` (lines 121–134) — closest existing pattern (`json.dumps` then `mkstemp` + `os.replace`). Mirror this structure, add `json.loads` round-trip and `mkdir(parents=True, exist_ok=True)`.
- **`fcntl.flock` inline usage**: `scripts/little_loops/fsm/concurrency.py:LockManager.acquire` (lines 122–142) and `scripts/little_loops/fsm/rate_limit_circuit.py:record_rate_limit` (lines 52–75) — both use `with open(lock_path, "w") as fd: fcntl.flock(fd, fcntl.LOCK_EX)` inline. No existing `@contextmanager` wraps `fcntl.flock` today; FEAT-1454 introduces the first one.
- **`@contextmanager` style**: `scripts/little_loops/issue_manager.py:timed_phase` (lines 71–94) — the canonical project example: `from contextlib import contextmanager`, `Generator[...]` return annotation from `collections.abc`, `try / yield / finally`.
- **Dot-path traversal**: `scripts/little_loops/config/core.py:BRConfig.resolve_variable` (lines 548–570) — `parts = var_path.split(".")`; iterate over parts, descend into dict, return `None` on miss. `feature_enabled` follows the same shape but coerces the terminal to `bool` and defaults to `False`.

### Tests to Add / Replace

- `scripts/tests/test_ll_issues_atomic_write.py:TestAtomicWrite` — **model** for new `TestAtomicWriteJson` (in same file or new `test_file_utils.py`): one method per invariant, `tmp_path: Path` fixture, patches `os.replace` for failure paths, asserts no orphan `.tmp` files via `list(tmp_path.glob("*.tmp")) == []`.
- `scripts/tests/test_hook_intents.py:TestLLHookEvent` / `TestLLHookResult` — **model** for dataclass-style assertion patterns; not directly applicable to these helpers but good for the test class layout.
- `scripts/tests/test_state.py:TestStateConcurrency.test_concurrent_save_no_corruption` (lines 412–436) — **canonical `ThreadPoolExecutor` + `as_completed` pattern**, including `assert isinstance(state, dict)` after `json.loads`. Use this (not the `test_concurrent_precompact_writes` subprocess version) for `acquire_lock` concurrency tests since the Python port runs in-process.
- `scripts/tests/test_concurrency.py:TestLockManagerRaceConditions.test_concurrent_acquire_same_scope_only_one_wins` (lines 333–355) — `threading.Barrier(2)` + `results.count(True) == 1` pattern for testing exclusive acquisition.
- `scripts/tests/test_hooks_integration.py:TestSharedConfigFunctions` (lines 1469–1593, **not** 1469–1700 as the issue body says) — class to be replaced. Has 9 tests across `ll_resolve_config` (3), `ll_feature_enabled` (5), `ll_config_value` (2). Drop the `_run_bash` helper and `common_sh` fixture (lines 1473, 1477); replace each test with a Python-direct equivalent.
- **`monkeypatch.chdir(tmp_path)` pattern**: see `scripts/tests/test_ll_loop_state.py:TestCmdStop` (multiple methods around lines 106, 124, 159, 193, 226) — preferred over the manual `os.chdir` + `try/finally` pattern used by the bash-sourcing tests.
- `scripts/tests/test_config.py:TestBRConfig` — four existing tests exercise `BRConfig._load_config` behavior: `test_load_config_from_file`, `test_load_config_without_file`, `test_load_config_invalid_json_raises`, `test_load_config_empty_file_raises`. These must remain green after `_load_config` is refactored to call `resolve_config_path`; the `.ll/` lookup path and `json.JSONDecodeError` propagation are unchanged, so no edits expected — but verify after implementation. [Wiring pass added by `/ll:wire-issue`]

### Documentation

- `docs/reference/API.md` — Python module reference; if it documents `file_utils` / `config.core` / `config.features`, add entries for the new functions.
- `docs/ARCHITECTURE.md` — no changes expected (intent abstraction lives in `hooks/`).
- `docs/development/TROUBLESHOOTING.md` — line 865 names `atomic_write_json` in the context `"check hook scripts source lib/common.sh"`; after this port a Python counterpart exists in `file_utils.py` — update the hint to mention both the bash and Python implementations. [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py` — re-exports all public symbols from `config.core` and `config.features` via `__all__`; verify whether `resolve_config_path` and `feature_enabled` need to be added to `__all__` (they are internal helpers used by FEAT-1455's `pre_compact.py` via direct submodule import, so likely no change needed — but confirm and document the decision)

### Configuration

- `hooks/hooks.json` — unchanged by this issue. Bash hooks remain wired; the parent FEAT-1449 / sibling FEAT-1450 issues handle adapter wiring.

## Implementation Notes

_Added by `/ll:refine-issue` — based on codebase analysis._

### Semantic Differences to Preserve

| Primitive | Bash behavior | Python port requirement |
|---|---|---|
| `atomic_write_json` | `mkdir -p $(dirname)`; `jq empty` validates temp before rename | Call `path.parent.mkdir(parents=True, exist_ok=True)`; do `json.dumps(data)` then `json.loads(...)` round-trip before writing (raise `ValueError` on round-trip failure) |
| `acquire_lock` | `flock -w timeout` blocks up to N seconds; default 10s | `fcntl.flock(LOCK_EX \| LOCK_NB)` in a polled loop with `time.sleep(0.05)` (or similar), bounded by `timeout`; raise `TimeoutError` (or return-style failure — decide and document) on expiry; default `timeout=10.0` |
| `acquire_lock` mkdir fallback | If `flock` missing, `mkdir lock_dir` polled at 0.1s | Catch `OSError` on `fcntl.flock` and fall back to `Path.mkdir(exist_ok=False)` polling — only needed for NFS/exotic FS; Linux/macOS dev paths use `flock` |
| `acquire_lock` semantic for precompact | `acquire_lock "$STATE_LOCK" 3` (caller passes 3s) | Precompact Python handler calls `acquire_lock(path, timeout=3.0)` — same value, just expressed in seconds-float |
| `resolve_config_path` | Two-step: `.ll/ll-config.json` then `ll-config.json`; side-effects `mkdir -p .ll` | Pure lookup, no mutation; returns `Path \| None`; caller (e.g., `BRConfig._load_config`) creates `.ll` only if/when it writes |
| `feature_enabled` | jq path on file; `// false` default; exit 0=true, 1=false | Operates on already-parsed `dict`; returns `bool`; missing key or wrong-type value → `False` |

### Decision: lock primitive failure mode

The issue body specifies `@contextmanager` for `acquire_lock`. Two reasonable failure modes for timeout — decide and document at implementation time:

- **Raise `TimeoutError`** (Pythonic) — caller writes `try: ... with acquire_lock(p, timeout=3.0): ...` (recommended; clearer in test assertions and matches `fcntl` error idioms)
- **Yield `None` / sentinel** (closer to bash `return 1`) — caller checks the yielded value

Recommendation: raise `TimeoutError`. The bash adapter for precompact wraps this with `try/except TimeoutError: <best-effort unlocked write>` to preserve the bash caller's semantics.

### Test Layout Recommendation

- Put new `atomic_write_json` and `acquire_lock` tests in `scripts/tests/test_file_utils.py` (new file) **or** extend `scripts/tests/test_ll_issues_atomic_write.py`. Prefer a new `test_file_utils.py` so the file's name matches the module.
- Put `TestResolveConfigPath` and `TestFeatureEnabledHelper` in `scripts/tests/test_config.py` as specified.
- Replace `TestSharedConfigFunctions` in `scripts/tests/test_hooks_integration.py` with a thin "smoke" reference (or delete) once the Python-direct tests cover equivalent invariants — keep the surrounding `TestSessionStartValidation` / `TestPrecompactState` classes untouched.

### Implementation Steps

1. **Add `atomic_write_json`** to `scripts/little_loops/file_utils.py` — model after `rate_limit_circuit.py:_write_atomic`; add `json.loads` round-trip and `path.parent.mkdir(parents=True, exist_ok=True)`.
2. **Add `acquire_lock`** to `scripts/little_loops/file_utils.py` as `@contextmanager` — `from contextlib import contextmanager`; use `fcntl.flock(LOCK_EX | LOCK_NB)` polled with `time.sleep(0.05)` up to `timeout`; raise `TimeoutError` on expiry; release via `with open(...)` + flock auto-release on FD close.
3. **Add `resolve_config_path`** standalone function to `scripts/little_loops/config/core.py` — two-step lookup, pure; then update `BRConfig._load_config` (lines 90–96) to call it and pick up the root-level fallback.
4. **Add `feature_enabled`** to `scripts/little_loops/config/features.py` — `dot_path.split(".")` traversal; coerce terminal to `bool`; `False` for missing keys; model traversal after `BRConfig.resolve_variable` (lines 548–570).
5. **Write Python-direct tests** for new primitives:
   - `TestAtomicWriteJson` (new file `scripts/tests/test_file_utils.py` or extend `test_ll_issues_atomic_write.py`) — round-trip validation, parent mkdir, no orphan `.tmp` on failure.
   - `TestAcquireLock` — happy path, timeout via `ThreadPoolExecutor` race (model after `test_state.py:TestStateConcurrency`), `TimeoutError` raised, cross-thread exclusivity via `threading.Barrier` (model after `test_concurrency.py:TestLockManagerRaceConditions`).
   - `TestResolveConfigPath` in `test_config.py` — `.ll/ll-config.json` preferred, root-level `ll-config.json` fallback, both absent → `None`.
   - `TestFeatureEnabledHelper` in `test_config.py` — truthy dot-path, falsy, missing key, wrong-type → `False`.
6. **Replace `TestSharedConfigFunctions`** (lines 1469–1593 in `test_hooks_integration.py`) — the new Python tests cover the same invariants; remove the bash-source class (or leave a minimal smoke test that runs `bash -c 'source common.sh && declare -f acquire_lock' >/dev/null` to confirm bash callers still source cleanly).
7. **Run `python -m pytest scripts/tests/test_hooks_integration.py scripts/tests/test_config.py scripts/tests/test_file_utils.py -v`**.
8. **Run `python -m mypy scripts/little_loops/file_utils.py scripts/little_loops/config/`**.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be addressed during implementation:_

9. **Verify `scripts/little_loops/config/__init__.py` exports** — `resolve_config_path` and `feature_enabled` are not currently in `__all__`. Since FEAT-1455's `pre_compact.py` will import them via direct submodule path (`from little_loops.config.core import resolve_config_path`), no `__all__` update is expected — but confirm this choice and do not leave it unresolved.
10. **Update `docs/development/TROUBLESHOOTING.md:865`** — the hint currently says `"check hook scripts source lib/common.sh"` for `atomic_write_json`; after this port, note that a Python implementation now lives in `little_loops.file_utils`.

## Acceptance Criteria

- `atomic_write_json` and `acquire_lock` exist in `file_utils.py` and pass tests
- `resolve_config_path` exists in `config/core.py`; root-level fallback tested in `test_config.py`
- `feature_enabled` exists in `config/features.py` and passes dot-path tests
- `TestSharedConfigFunctions` replaced with Python-direct equivalents that pass
- `python -m pytest scripts/tests/test_hooks_integration.py scripts/tests/test_config.py scripts/tests/test_file_utils.py -v`
- `python -m mypy scripts/little_loops/file_utils.py scripts/little_loops/config/`
- `scripts/little_loops/config/__init__.py` export decision documented (add or explicitly omit `resolve_config_path` / `feature_enabled`)

## Resolution

- `atomic_write_json` added to `scripts/little_loops/file_utils.py` with `allow_nan=False` + round-trip validation + `parents=True, exist_ok=True` parent-dir creation.
- `acquire_lock` added to `scripts/little_loops/file_utils.py` as `@contextmanager` using `fcntl.flock(LOCK_EX | LOCK_NB)` polled at 0.05s; raises `TimeoutError` on expiry; lock released via FD close on context-manager exit.
- `resolve_config_path(project_root)` added to `scripts/little_loops/config/core.py` as a pure two-step lookup (`.ll/ll-config.json` then `ll-config.json`); `BRConfig._load_config` now uses it and picks up the root-level fallback that was previously absent.
- `feature_enabled(config_data, dot_path)` added to `scripts/little_loops/config/features.py` — dot-path traversal returning `bool(value)` or `False` for missing keys / non-dict intermediates (parity with jq's `// false`).
- Export decision (per acceptance criteria): `resolve_config_path` and `feature_enabled` are intentionally NOT added to `little_loops.config.__all__`. Callers import via direct submodule paths. Decision is documented as a comment in `scripts/little_loops/config/__init__.py`.
- Replaced `TestSharedConfigFunctions` (bash-source harness) in `scripts/tests/test_hooks_integration.py` with `TestSharedConfigFunctionsBashSmoke`, a single smoke test verifying bash primitives are still defined in `common.sh` (bash callers unmodified). Exhaustive coverage now lives in the new Python-direct tests.
- Added `scripts/tests/test_file_utils.py` with `TestAtomicWriteJson` (7 tests) and `TestAcquireLock` (6 tests including `ThreadPoolExecutor` race + `threading.Barrier` exclusivity).
- Added `TestResolveConfigPath` (5 tests) and `TestFeatureEnabledHelper` (7 tests) to `scripts/tests/test_config.py`.
- Updated `docs/development/TROUBLESHOOTING.md:865` to note the Python implementation alongside the bash one.

**Verification**: `python -m pytest scripts/tests/test_file_utils.py scripts/tests/test_config.py scripts/tests/test_hooks_integration.py -v` → 252 passed. `python -m mypy scripts/little_loops/file_utils.py scripts/little_loops/config/` → no issues. `ruff check` → clean. Full pytest suite shows 7 pre-existing failures in `test_generate_schemas.py` / `test_update_skill.py` unrelated to FEAT-1454 scope.

## Session Log
- `/ll:manage-issue feature implement FEAT-1454` - 2026-05-12T01:32:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e5f6a22-78eb-4d07-abdb-1dd8e5918efc.jsonl`
- `/ll:ready-issue` - 2026-05-12T01:24:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7bdf149e-d761-4941-845b-48e95c585f82.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cc930c4-274c-44dc-ba72-41c83d8a694c.jsonl`
- `/ll:wire-issue` - 2026-05-12T01:20:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d3a00a5f-ee5e-44a7-8db8-4540ddf6b6e8.jsonl`
- `/ll:refine-issue` - 2026-05-12T01:14:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9394b375-f65a-47e6-8794-9044c5abf0d6.jsonl`
- `/ll:issue-size-review` - 2026-05-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c5f319b-68fa-4ac3-990a-9ace13bbeaea.jsonl`
