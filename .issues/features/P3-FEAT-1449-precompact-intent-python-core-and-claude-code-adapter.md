---
id: FEAT-1449
type: FEAT
priority: P3
status: done
parent: FEAT-1116
discovered_date: 2026-05-12
discovered_by: issue-size-review
decision_needed: false
confidence_score: 100
outcome_confidence: 72
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 18
size: Very Large
completed_at: 2026-05-11T00:00:00Z
---

# FEAT-1449: PreCompact Intent — Python Core Handler and Claude Code Adapter

## Summary

Port `precompact-state.sh` to a Python core handler, audit and reuse existing Python equivalents of `lib/common.sh`, build the Claude Code adapter wrapper, update `hooks/hooks.json`, and replace the now-broken shell-sourcing tests with Python-direct tests. This is the first end-to-end intent migration in FEAT-1116.

## Parent Issue

Decomposed from FEAT-1116: Hook-Intent Abstraction Layer for Multi-Host Support

## Depends On

- FEAT-1448 (types must exist before implementing the handler)

## Scope

Covers FEAT-1116 Implementation Steps 2, 3, 4, 13, 14 (precompact portion), 16.

- **Step 16 (prerequisite)**: Before writing `hooks/common.py`, audit `scripts/little_loops/file_utils.py` (`atomic_write_json`, file locking), `scripts/little_loops/config/core.py` (`ll_resolve_config` equivalent), and `scripts/little_loops/config/features.py` (`ll_feature_enabled` equivalent). Reuse or thin-wrap — do not duplicate.
- **Step 2**: Port `precompact-state.sh` → `scripts/little_loops/hooks/pre_compact.py`. Pure function: `(event: LLHookEvent) -> LLHookResult`. Snapshots state to `.ll/ll-precompact-state.json`.
- **Step 3**: Move any `lib/common.sh` primitives not already covered by the Step 16 audit into Python (e.g. `acquire_lock` if not already in `file_utils.py`). Do not duplicate what already exists.
- **Step 4**: Create `hooks/adapters/claude-code/precompact.sh` — thin wrapper: `INPUT=$(cat); echo "$INPUT" | python -m little_loops.hooks pre_compact; exit $?`. Update `hooks/hooks.json` `PreCompact` entry to point at the adapter instead of `hooks/scripts/precompact-state.sh`.
- **Step 13**: `TestSharedConfigFunctions` (lines 1192–1316 in `test_hooks_integration.py`) bash-sources `lib/common.sh` directly and will break when those functions are ported to Python. Replace with a Python-direct test class covering `hooks/common.py` (or whichever module absorbed the primitives).
- **Step 14 (precompact)**: Update `TestPrecompactState` fixture path from `hooks/scripts/precompact-state.sh` to `hooks/adapters/claude-code/precompact.sh`, or add `TestClaudeCodePrecompactAdapter` and retire the legacy class.

## New Files to Create

- `scripts/little_loops/hooks/pre_compact.py` — Python core handler
- `hooks/adapters/claude-code/precompact.sh` — Claude Code adapter wrapper
- `hooks/adapters/claude-code/` directory (if not yet created)

## Files to Modify

- `hooks/hooks.json` — update `PreCompact` event to point at `hooks/adapters/claude-code/precompact.sh`
- `scripts/tests/test_hooks_integration.py` — migrate `TestSharedConfigFunctions` + update `TestPrecompactState` fixture path

## Files to Audit (Step 16 — do not skip)

- `scripts/little_loops/file_utils.py` — check for `atomic_write_json`, file locking
- `scripts/little_loops/config/core.py` — check for `ll_resolve_config` equivalent
- `scripts/little_loops/config/features.py` — check for `ll_feature_enabled` equivalent

### Codebase Research Findings

_Added by `/ll:refine-issue` — Step 16 audit results:_

| `lib/common.sh` primitive | Python status | Anchor reference |
|---|---|---|
| `atomic_write_json(target, content)` | **Partial** — `atomic_write(path, content, encoding)` exists; missing the `jq empty` JSON-validation step. Compose: `atomic_write(path, json.dumps(data, indent=2))` or add thin `atomic_write_json` wrapper that validates via `json.loads(content)` before write. | `scripts/little_loops/file_utils.py` — `atomic_write()` (only function in module; uses `tempfile.mkstemp` + `os.replace`) |
| `acquire_lock(file, timeout)` / `release_lock(file)` | **Absent** — no Python locking primitive anywhere in `scripts/little_loops/`. Must port. Shell version: `flock -w` with `mkdir`-fallback. Python idiomatic equivalent: `fcntl.flock(fd, LOCK_EX \| LOCK_NB)` with timeout loop, or `filelock` package. | N/A — does not exist |
| `ll_resolve_config()` (shell side-effect, sets `LL_CONFIG_FILE`) | **Partial** — `BRConfig._load_config()` resolves `<project_root>/.ll/ll-config.json` only. **Missing the shell's secondary fallback to root-level `ll-config.json`.** No standalone resolver function — resolution is private inside `__init__`. | `scripts/little_loops/config/core.py` — `BRConfig._load_config()`; `CONFIG_DIR=".ll"`, `CONFIG_FILENAME="ll-config.json"` |
| `ll_feature_enabled(dot_path)` | **Absent as dot-path helper** — Python exposes feature flags as typed dataclass attributes (e.g., `config.sync.enabled`). The dot-path-string semantic has no equivalent. Either add a generic helper or update callers to use typed access. | `scripts/little_loops/config/features.py` — `SyncConfig.enabled`, `EventsConfig.enabled`, etc. via `from_dict` factories |

**Primitives `precompact-state.sh` actually uses:** only `acquire_lock`, `release_lock`, `atomic_write_json`. It does NOT call `ll_resolve_config` or `ll_feature_enabled` — those are covered by `TestSharedConfigFunctions` because other hooks (`session-start.sh`, `context-monitor.sh`) use them. Step 13 therefore requires porting the **full common.sh surface tested by that class**, not just the precompact-touched subset.

## Integration Map

### Files to Modify
- `hooks/hooks.json:110-122` — `PreCompact` entry currently runs `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/precompact-state.sh`; change `command` to `bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/precompact.sh`. `matcher: "*"`, `timeout: 5`, `statusMessage: "Preserving task state..."` all preserved as-is.
- `scripts/little_loops/hooks/__init__.py` — `main_hooks()` is currently a stub that prints usage to stderr. Wire dispatch on `sys.argv[1]` so `python -m little_loops.hooks pre_compact` reads stdin → builds `LLHookEvent` → calls `pre_compact.handle(event)` → prints `LLHookResult.feedback` to stderr → exits `result.exit_code`.
- `scripts/tests/test_hooks_integration.py:1720` — `TestPrecompactState.hook_script` fixture points at `hooks/scripts/precompact-state.sh`; update to `hooks/adapters/claude-code/precompact.sh` (or add `TestClaudeCodePrecompactAdapter` and retire the legacy class). Two test methods reuse the fixture: `test_atomic_write_with_missing_directory` (line 1728), `test_concurrent_precompact_writes` (line 1762).
- `scripts/tests/test_hooks_integration.py:1469-1700` — `TestSharedConfigFunctions` class with `_run_bash()` helper at line 1477 sources `lib/common.sh` via `bash -e -c 'source "..."\n<snippet>'`. Replace with Python-direct tests against the chosen common module (see Proposed Solution).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/context-monitor.sh` — `check_compaction()` (lines 176-206) reads `.ll/ll-precompact-state.json` and deletes it after compaction handling; this is the **runtime consumer of the state file written by `pre_compact.handle()`**. Behavioral spec must produce byte-equivalent JSON or `check_compaction()` silently breaks without test coverage. No path-level change needed — the consumer reads the output file, not the hook script path.
- `scripts/little_loops/hooks/__main__.py` — the actual CLI entrypoint; `raise SystemExit(main_hooks())`; confirms `python -m little_loops.hooks` already routes through `main_hooks()`. No changes needed — but existence means Step 5 only needs to update `__init__.py:main_hooks()`, not `__main__.py`.

### Files to Create
- `scripts/little_loops/hooks/pre_compact.py` — pure-function handler `def handle(event: LLHookEvent) -> LLHookResult`. Reproduce 4-field state contract exactly (see Behavioral Spec below).
- `hooks/adapters/claude-code/precompact.sh` — three-line wrapper (chmod 755):
  ```bash
  #!/usr/bin/env bash
  INPUT=$(cat)
  echo "$INPUT" | python -m little_loops.hooks pre_compact
  exit $?
  ```
- `hooks/adapters/claude-code/` — new directory.

### Behavioral Spec for `pre_compact.handle()`

The Python port MUST be byte-equivalent to `precompact-state.sh` for the wire-visible state file:

1. **Input**: `LLHookEvent.payload` carries the Claude Code PreCompact stdin JSON. Only `payload.get("transcript_path", "")` is read; all other fields ignored (matches shell `jq -r '.transcript_path // ""'`).
2. **Output state** written atomically to `.ll/ll-precompact-state.json` (under `cwd`):
   ```json
   {
     "compacted_at": "<UTC ISO 8601, e.g. 2026-05-11T14:00:00Z>",
     "transcript_path": "<from payload or empty string>",
     "preserved": true,
     "context_state_at_compact": { /* contents of .ll/ll-context-state.json if it exists */ },
     "recent_plan_files": ["<thoughts/shared/plans/*.md modified < 24h, max 5, sorted by find>"],
     "continue_prompt_exists": true  // ONLY present if .ll/ll-continue-prompt.md exists — KEY ABSENT otherwise (not false)
   }
   ```
3. **Locking**: acquire exclusive lock on `.ll/ll-precompact-state.json.lock` with 3-second timeout; on timeout, fall back to lock-free write (`atomic_write_json ... || true` in shell version).
4. **Result**: return `LLHookResult(exit_code=2, feedback="[ll] Task state preserved before context compaction. Check .ll/ll-precompact-state.json if resuming work.")`. The dispatcher prints `feedback` to stderr and exits 2.

### Edge cases inherited from shell version (preserve these)
- If `.ll/` does not exist, it must be created (shell does this via `atomic_write_json`'s `mkdir -p`).
- If `jq` is missing, shell exits `0` immediately as a noop. Python equivalent: if `LLHookEvent` fails to parse, return `LLHookResult(exit_code=0)` (noop, no error to user).
- If `thoughts/shared/plans/` does not exist, `recent_plan_files: []`.
- Lock acquire failure must NOT block the write — best-effort fallback. Concurrent test (`test_concurrent_precompact_writes`) expects all 5 parallel invocations to exit 2 and the resulting file to be valid JSON.

## Proposed Solution

Two reasonable placements for the ported `common.sh` primitives. Pick one before implementing — Step 13's `TestSharedConfigFunctions` replacement must target the chosen module(s).

### Option A — Single `scripts/little_loops/hooks/common.py`

Co-locate hook-specific primitives in a new `hooks/common.py` module:

- `atomic_write_json(path: Path, data: Any) -> None` — thin wrapper: `atomic_write(path, json.dumps(data, indent=2))` with `json.loads` round-trip validation
- `acquire_lock(path: Path, timeout: float = 10.0) -> ContextManager` — `fcntl.flock` (POSIX) with `mkdir` fallback to mirror shell semantics; expose as `@contextmanager` so handlers use `with acquire_lock(...):`.
- `resolve_config_path(project_root: Path) -> Path | None` — mirrors `ll_resolve_config`'s two-step lookup (`.ll/ll-config.json` then `ll-config.json`); does NOT mutate global state.
- `feature_enabled(config: dict, dot_path: str) -> bool` — generic dot-path boolean lookup against a parsed config dict.

**Pros**: All hook-related concerns in one module; matches the `lib/common.sh` mental model; easy to find. **Cons**: Splits responsibility — `atomic_write_json` arguably belongs next to `atomic_write` in `file_utils.py`; locking is generic enough to live outside `hooks/`.

### Option B — Spread across existing modules

> **Selected:** Option B — Spread across existing modules — each primitive co-located with its natural home; direct extension of `file_utils`, `config/core`, `config/features`; no new naming conventions.

Put each primitive where its concern already lives:

- `scripts/little_loops/file_utils.py` gains `atomic_write_json(path, data)` and `acquire_lock(path, timeout)` (locking is a file-system concern, not hook-specific).
- `scripts/little_loops/config/core.py` gains a standalone `resolve_config_path(project_root) -> Path | None` function alongside `BRConfig`; extend `BRConfig._load_config()` to use it and pick up the root-level fallback (currently absent).
- `scripts/little_loops/config/features.py` gains `feature_enabled(config_data, dot_path) -> bool`.

**Pros**: Each primitive lives next to related code; reusable beyond hooks; no new "junk drawer" module. **Cons**: Spreads the port across three files; `TestSharedConfigFunctions` replacement spans 2-3 new test files (or one file with multiple test classes).

**Decision deferred to `/ll:decide-issue`.**

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-11.

**Selected**: Option B — Spread across existing modules

**Reasoning**: Option B puts each primitive next to its natural home — `atomic_write_json` and `acquire_lock` extend `file_utils.py` (where `atomic_write` already lives), `resolve_config_path` slots alongside `BRConfig._load_config` in `config/core.py`, and `feature_enabled` complements the dot-path traversal precedent set by `resolve_variable`. The established `config/__init__` re-export pattern (100+ call sites) means no existing callers change import paths, and there is no new naming convention to introduce. Option A scores lower on Consistency because it would create a `common.py` module (absent from the codebase — convention is `_utils.py`/`_helpers.py`) and add thin delegation wrappers that duplicate logic already encapsulated in `BRConfig`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Single hooks/common.py | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |
| Option B — Spread across existing modules | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- Option A: `atomic_write` already has a home in `file_utils.py` with its own test file; `common.py` would create delegation chains and duplicate `BRConfig` constants; no existing `common.py` in any sub-package.
- Option B: `file_utils.py` is a direct extension target (4 existing importers, `TestAtomicWrite` template); `config/__init__` re-export surface is well-established; `resolve_variable` in `core.py` provides the dot-path precedent; only friction is that `features.py` and `core.py` have no existing module-level standalone functions yet.

## Tests

- Python-direct test for `pre_compact` handler: import handler, call with `LLHookEvent`, assert `LLHookResult` fields and that `.ll/ll-precompact-state.json` is written correctly
- Adapter round-trip test (`TestClaudeCodePrecompactAdapter`): subprocess pattern from `test_hooks_integration.py`, fixture pointing to `hooks/adapters/claude-code/precompact.sh`
- Python-direct replacement for `TestSharedConfigFunctions`: tests for `atomic_write_json`, `acquire_lock`, `ll_resolve_config`, `ll_feature_enabled` against the Python modules

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md:806,865,1003-1006,1037` — four references to `hooks/scripts/precompact-state.sh` by name (chmod block, manual invocation, lock timeout list, state corruption guide); all become stale after `hooks/hooks.json` is updated. Formally owned by FEAT-1453 for the full doc rewrite, but these references go stale as soon as this issue ships.
- `scripts/little_loops/hooks/__init__.py` module docstring — explicitly identifies the current `main_hooks()` as a stub and names FEAT-1449 as future work; **must be updated as part of Step 5** (wiring dispatcher) so the docstring describes the real behavior.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_intents.py::TestHooksMainModule.test_module_dispatch_exit_zero` — asserts `returncode == 0` AND `"little_loops.hooks" in result.stderr` when `python -m little_loops.hooks` is invoked with **no argument**. Will break if `main_hooks()` returns non-zero on no-arg invocation. Either (a) ensure the new dispatcher still exits 0 and prints module usage to stderr on no-arg, or (b) update this test alongside Step 5 to reflect the new no-arg behavior. **This test is at risk — flag in Step 8.**
- `scripts/tests/test_config.py` — add tests for the new standalone primitives introduced in Step 3:
  - `TestResolveConfigPath` or extend `TestBRConfig`: test root-level `ll-config.json` fallback (not currently tested; only `.ll/ll-config.json` is covered)
  - `TestFeatureEnabledHelper`: test `feature_enabled(config_dict, "dot.path") -> bool` against truthy and falsy dot-path keys (no test exists anywhere for this function)

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete test patterns to model after:_

**Reference Python-direct test patterns** (already in the suite — model after these):
- `scripts/tests/test_ll_issues_atomic_write.py` — `TestAtomicWrite`: direct import + `tmp_path` fixture + assert file content. Closest template for testing `atomic_write_json` and locking.
- `scripts/tests/test_hook_intents.py` — `TestLLHookEvent`, `TestLLHookResult`: direct dataclass tests for `to_dict` / `from_dict` round-trip; reuse these for `pre_compact.handle()` input/output assertions.
- `scripts/tests/test_events.py` — `TestLLEvent`: same dataclass test style.

**Existing subprocess fixture pattern to update** (`TestPrecompactState`, `test_hooks_integration.py:1720-1797`):
```python
@pytest.fixture
def hook_script(self) -> Path:
    # BEFORE: Path(__file__).parent.parent.parent / "hooks/scripts/precompact-state.sh"
    # AFTER:
    return Path(__file__).parent.parent.parent / "hooks/adapters/claude-code/precompact.sh"
```
Subprocess invocation pattern itself stays identical: `subprocess.run([str(hook_script)], input=json.dumps({"transcript_path": "..."}), capture_output=True, text=True, timeout=5)`. The two existing tests (`test_atomic_write_with_missing_directory`, `test_concurrent_precompact_writes`) should pass unchanged once the fixture path is updated — the adapter wrapper produces identical state file output, which is the exact contract these tests assert.

**Pythonic cwd isolation** — replace the manual `os.chdir(tmp_path)` / `try/finally` dance in the existing tests with `monkeypatch.chdir(tmp_path)` (pattern from `test_generate_schemas.py:TestGenerateSchemasCLI.test_cli_default_output_dir` at line 180). Apply to both the legacy tests (when updating their fixture) and any new tests.

**Replacing `TestSharedConfigFunctions` (lines 1469-1700)** — current bash-source helper:
```python
def _run_bash(self, common_sh: Path, script: str, cwd: Path) -> subprocess.CompletedProcess:
    full_script = f'source "{common_sh}"\n{script}'
    return subprocess.run(["bash", "-e", "-c", full_script], capture_output=True, text=True, timeout=5, cwd=str(cwd))
```
Replace with direct imports of the Python equivalents (per the Proposed Solution decision). Each existing test method maps to a Python equivalent — e.g., a test that writes `ll-config.json` and asserts `ll_resolve_config` sets `LL_CONFIG_FILE` becomes a test that constructs the chosen `resolve_config_path()` helper and asserts the returned `Path`. Concurrency tests for `acquire_lock` use `ThreadPoolExecutor` (already a pattern in `test_concurrent_precompact_writes`).

## Implementation Steps

1. **Audit** (Step 16 — already done in this refinement; see "Codebase Research Findings" under Files to Audit). Confirm the gap matrix has not drifted before coding.
2. **Decide** common-module placement via `/ll:decide-issue FEAT-1449` (Option A vs. Option B in Proposed Solution).
3. **Port primitives** into the chosen location:
   - `atomic_write_json` — wrap existing `little_loops.file_utils.atomic_write` with `json.dumps` + `json.loads` validation round-trip.
   - `acquire_lock` / `release_lock` — implement as `@contextmanager` using `fcntl.flock(LOCK_EX | LOCK_NB)` with polled retry up to timeout; preserve the 3-second timeout used by `precompact-state.sh`.
   - `resolve_config_path` — two-step lookup matching shell `ll_resolve_config`; export as a standalone function (in addition to whatever path-resolution `BRConfig` does internally).
   - `feature_enabled` — generic dot-path boolean lookup (only needed for `TestSharedConfigFunctions` parity; `pre_compact` does not call it).
4. **Implement `scripts/little_loops/hooks/pre_compact.py`** as `def handle(event: LLHookEvent) -> LLHookResult` reproducing the 4-field state contract in "Behavioral Spec" above.
5. **Wire dispatcher** in `scripts/little_loops/hooks/__init__.py::main_hooks()`:
   - Parse `sys.argv[1]` as intent name; reject unknown intents with non-zero exit and stderr message.
   - For `pre_compact`: read stdin JSON, build `LLHookEvent(host="claude-code", intent="pre_compact", payload=<parsed>, cwd=os.getcwd(), ...)`, call `pre_compact.handle(event)`, print `result.feedback` to stderr if set, exit `result.exit_code`.
6. **Create adapter** `hooks/adapters/claude-code/precompact.sh` (3-line wrapper); `chmod +x`.
7. **Update `hooks/hooks.json:110-122`** `PreCompact.command` to `bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/precompact.sh`.
8. **Migrate tests**:
   - Update `TestPrecompactState.hook_script` fixture path (or rename class to `TestClaudeCodePrecompactAdapter`).
   - Add `scripts/tests/test_pre_compact.py` with Python-direct tests of `handle()`.
   - Replace `TestSharedConfigFunctions` with Python-direct tests targeting the chosen module(s) from Step 3.
   - Update or guard `TestHooksMainModule.test_module_dispatch_exit_zero` in `test_hook_intents.py` — verify no-arg behavior of the new dispatcher is still exit 0 + usage message, or update assertion to match the new behavior.
   - Add `TestResolveConfigPath` and `TestFeatureEnabledHelper` to `scripts/tests/test_config.py` covering the new standalone functions from Step 3.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Verify behavioral contract against `hooks/scripts/context-monitor.sh::check_compaction()` — this runtime consumer reads the state file output; any deviation from the 4-field JSON spec silently breaks compaction detection. Add a test fixture that reads `context-monitor.sh` and asserts the `compacted_at` / `preserved` / `transcript_path` keys are read (snapshot comparison).
10. After Step 5 (`main_hooks()` dispatch wiring), update the `__init__.py` module docstring to remove the stub/FEAT-1449 forward reference.
9. **Verify**:
   - `python -m pytest scripts/tests/test_hook_intents.py scripts/tests/test_hooks_integration.py scripts/tests/test_pre_compact.py -v`
   - `python -m mypy scripts/little_loops/hooks/`
   - Manual: trigger a Claude Code PreCompact event and confirm `.ll/ll-precompact-state.json` is written with the same shape as before (diff against a snapshot from the shell version if possible).

## Acceptance Criteria

- `scripts/little_loops/hooks/pre_compact.py` exists as a pure-function handler
- `hooks/adapters/claude-code/precompact.sh` is executable and wired in `hooks/hooks.json`
- Manual: trigger a Claude Code PreCompact event; `.ll/ll-precompact-state.json` is still written
- `TestSharedConfigFunctions` replaced by Python-direct tests that pass
- `TestClaudeCodePrecompactAdapter` (or updated `TestPrecompactState`) passes
- `python -m pytest scripts/tests/test_hook_intents.py scripts/tests/test_hooks_integration.py -v`
- `python -m mypy scripts/little_loops/hooks/`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-11 (re-run after `/ll:decide-issue` resolved Option A/B on 2026-05-12)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors

- **Wide change surface across 11 distinct sites**: 6 modify + 3 create + 2 test additions — breadth requires coordination to not miss a site; integration test suite provides safety net
- **TestSharedConfigFunctions migration scope**: 230-line bash-source test class (lines 1469-1700) requires deliberate line-by-line port to Python-direct equivalents; `ThreadPoolExecutor` concurrency pattern is established but must be applied carefully for `acquire_lock` tests
- **At-risk test `test_module_dispatch_exit_zero`**: Adding intent dispatch to `main_hooks()` must preserve exit-0 + usage-message on no-arg invocation; if broken, `test_hook_intents.py:258` fails silently during Step 8

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-11
- **Reason**: Issue too large for single session (size score 11/11)

### Decomposed Into
- FEAT-1454: PreCompact — Port common.sh Primitives to Python (Option B)
- FEAT-1455: PreCompact — Handler, Adapter, Dispatcher, and Test Migration

## Session Log
- `/ll:issue-size-review` - 2026-05-11T00:00:00Z - `3c5f319b-68fa-4ac3-990a-9ace13bbeaea.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `5d17799b-927a-42c6-8ac0-8696d4065cc4.jsonl`
- `/ll:decide-issue` - 2026-05-12T01:04:17 - `8f37f61c-dbf6-408b-a3ef-afe93e14f879.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `f25984e6-3fdf-45b9-bd49-5b2d1085eb4f.jsonl`
- `/ll:wire-issue` - 2026-05-12T00:57:42 - `ba6dca18-b972-49a3-8947-4965a13110cd.jsonl`
- `/ll:refine-issue` - 2026-05-12T00:51:02 - `0310090e-383d-4bb5-9502-3fc349335e9b.jsonl`
- `/ll:issue-size-review` - 2026-05-12T00:20:02 - `5cb0dc9a-fd6f-4945-97b0-ad6acec56482.jsonl`
