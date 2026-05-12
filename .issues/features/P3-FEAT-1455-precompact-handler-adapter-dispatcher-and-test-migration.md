---
id: FEAT-1455
type: FEAT
priority: P3
status: done
parent: FEAT-1449
discovered_date: 2026-05-11
completed_at: 2026-05-12T02:03:00Z
discovered_by: issue-size-review
decision_needed: false
confidence_score: 96
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1455: PreCompact — Handler, Adapter, Dispatcher, and Test Migration

## Summary

Implement `pre_compact.py` core handler, create the Claude Code adapter wrapper, wire the `main_hooks()` dispatcher, update `hooks/hooks.json`, migrate/add the adapter test suite, and verify the behavioral contract against `context-monitor.sh`. This is the second and final implementation child of FEAT-1449.

## Parent Issue

Decomposed from FEAT-1449: PreCompact Intent — Python Core Handler and Claude Code Adapter

## Depends On

- FEAT-1454 (primitives `atomic_write_json`, `acquire_lock` must exist in `file_utils.py` before `pre_compact.py` can import them)

## Covers

Implementation Steps 4, 5, 6, 7, 8 (remaining test migration), 9, 10, and final verify from FEAT-1449.

## Scope

### Step 4: Implement `scripts/little_loops/hooks/pre_compact.py`

Pure function `def handle(event: LLHookEvent) -> LLHookResult`. Must be byte-equivalent to `precompact-state.sh` (source: `hooks/scripts/precompact-state.sh:17-84`) for the wire-visible state file.

**Note**: `pre_compact.py` will be the **first** ported handler in `scripts/little_loops/hooks/`. There is no sibling handler to model the function shape after — the contract is defined by `LLHookEvent`/`LLHookResult` in `scripts/little_loops/hooks/types.py:21,85`.

**State contract** — write atomically to `.ll/ll-precompact-state.json`:
```json
{
  "compacted_at": "<UTC ISO 8601>",
  "transcript_path": "<from payload or empty string>",
  "preserved": true,
  "context_state_at_compact": { /* contents of .ll/ll-context-state.json if exists */ },
  "recent_plan_files": ["<thoughts/shared/plans/*.md modified < 24h, max 5, sorted by find>"],
  "continue_prompt_exists": true  // ONLY if .ll/ll-continue-prompt.md exists — KEY ABSENT otherwise
}
```

**Locking**: acquire exclusive lock on `.ll/ll-precompact-state.json.lock` with 3-second timeout; on timeout, fall back to lock-free write (best-effort — do NOT block).

**Result**: `LLHookResult(exit_code=2, feedback="[ll] Task state preserved before context compaction. Check .ll/ll-precompact-state.json if resuming work.")`

**Edge cases** (preserve from shell version):
- Create `.ll/` if it does not exist (`atomic_write_json` already does `path.parent.mkdir(parents=True, exist_ok=True)`)
- If `LLHookEvent` fails to parse: return `LLHookResult(exit_code=0)` (noop)
- If `thoughts/shared/plans/` does not exist: `recent_plan_files: []`
- Lock timeout must NOT block the write

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on `scripts/little_loops/file_utils.py` analysis (FEAT-1454):_

- **`acquire_lock` is a context manager that raises `TimeoutError`** (NOT a boolean-returning function like the shell version). The fallback pattern is:
  ```python
  from little_loops.file_utils import acquire_lock, atomic_write_json
  try:
      with acquire_lock(state_lock, timeout=3.0):
          atomic_write_json(state_file, state_dict)
  except TimeoutError:
      atomic_write_json(state_file, state_dict)  # best-effort, no lock
  ```
  The `acquire_lock` docstring at `scripts/little_loops/file_utils.py:61` already documents the precompact 3.0s + best-effort fallback contract.

- **`atomic_write_json(path, data)` takes a Python object, not a JSON string** (unlike the shell version which takes a pre-serialized string). Build the result as a Python `dict` and pass it directly — `atomic_write_json` handles `json.dumps(..., indent=2, allow_nan=False)` plus a round-trip `json.loads` validation internally.

- **`recent_plan_files` sort order**: The shell uses `find "$PLANS_DIR" -name "*.md" -mtime -1 | head -5` with no explicit sort — filesystem (inode) order. Do NOT impose Python `sorted()`; use `Path.glob("*.md")` (which returns scandir order) and slice `[:5]`. Filter to mtime within last 24h via `(time.time() - p.stat().st_mtime) < 86400`.

- **`continue_prompt_exists` key absence is wire-visible**: the shell omits the key entirely when `.ll/ll-continue-prompt.md` doesn't exist (NOT `false`/`null`). In Python, conditionally insert the key with `if continue_prompt.exists(): state["continue_prompt_exists"] = True` — do NOT include an `else` branch.

### Step 5: Wire `scripts/little_loops/hooks/__init__.py::main_hooks()`

Current state: `main_hooks()` at `scripts/little_loops/hooks/__init__.py:29-44` is a stub that prints usage and returns 0 unconditionally. Replace the body with:

- **No-arg path first**: `if len(sys.argv) < 2: print(usage, file=sys.stderr); return 0`. This MUST come before any `sys.argv[1]` access — `test_module_dispatch_exit_zero` (`scripts/tests/test_hook_intents.py:250-259`) invokes the module with no args and asserts `returncode == 0` + `"little_loops.hooks" in stderr`.
- Parse `sys.argv[1]` as intent name; reject unknown intents with non-zero exit + stderr message.
- For `pre_compact`: read stdin JSON (handle empty/malformed → fall back to `payload={}`) → build `LLHookEvent(host="claude-code", intent="pre_compact", payload=<parsed>, cwd=os.getcwd())` → call `pre_compact.handle(event)` → print `result.feedback` to stderr if set → exit `result.exit_code`.

`__main__.py` already calls `raise SystemExit(main_hooks())` — no changes needed there.

### Step 6: Create `hooks/adapters/claude-code/precompact.sh`

Three-line wrapper (`chmod +x`):
```bash
#!/usr/bin/env bash
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks pre_compact
exit $?
```
Also creates the `hooks/adapters/claude-code/` directory.

### Step 7: Update `hooks/hooks.json`

Change `PreCompact.command` (lines 110-122) from:
```
bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/precompact-state.sh
```
to:
```
bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/precompact.sh
```
Preserve `matcher: "*"`, `timeout: 5`, `statusMessage: "Preserving task state..."`.

### Step 8 (remaining): Test migration

**`scripts/tests/test_hooks_integration.py`**
- Update `TestPrecompactState.hook_script` fixture at `scripts/tests/test_hooks_integration.py:1624` (the class is at line 1624; fixture body returns the path on line ~1630) from `hooks/scripts/precompact-state.sh` to `hooks/adapters/claude-code/precompact.sh` (or rename class to `TestClaudeCodePrecompactAdapter`). The two existing test methods (`test_atomic_write_with_missing_directory`, `test_concurrent_precompact_writes` at ~line 1666) should pass unchanged once the fixture path is updated — they invoke the script via `subprocess.run` and assert `returncode == 2` plus `state["preserved"] is True`, which the Python-via-adapter path produces identically.

**`scripts/tests/test_hook_intents.py`**
- Update or guard `TestHooksMainModule.test_module_dispatch_exit_zero` to verify no-arg invocation still exits 0 + prints usage.

**`scripts/tests/test_pre_compact.py`** (new file)
- Python-direct tests for `handle()`: import handler, call with `LLHookEvent`, assert `LLHookResult` fields and `.ll/ll-precompact-state.json` contents.
- Use `monkeypatch.chdir(tmp_path)` for cwd isolation (pattern: `scripts/tests/test_generate_schemas.py:180`).
- Model after `scripts/tests/test_hook_intents.py` (`TestLLHookEvent`/`TestLLHookResult`) for dataclass construction style and after `scripts/tests/test_file_utils.py` (`TestAcquireLock.test_concurrent_writers_via_acquire_lock`) for the concurrent lock+write pattern.
- Required test cases:
  - happy path: `.ll/` created, JSON contains `compacted_at`, `transcript_path`, `preserved=true`, `recent_plan_files=[]` when plans dir absent
  - merges `.ll/ll-context-state.json` into `context_state_at_compact` when present
  - `recent_plan_files` returns up to 5 paths with mtime < 24h
  - `continue_prompt_exists` key is **absent** when `.ll/ll-continue-prompt.md` does not exist, **`true`** when it does
  - `LLHookResult(exit_code=2, feedback=...)` shape
  - parse-failure noop: passing an event constructed from malformed payload returns `LLHookResult(exit_code=0)` without raising

### Step 9: Verify behavioral contract

- `hooks/scripts/context-monitor.sh::check_compaction()` (lines 176-206) is the only consumer of `.ll/ll-precompact-state.json` from the shell side. Per analyzer findings, it **only structurally reads `compacted_at`** at line 185 via `jq -r '.compacted_at // ""'`; a missing or `"null"` value causes `return 1`. The other keys (`preserved`, `transcript_path`, `context_state_at_compact`, `recent_plan_files`, `continue_prompt_exists`) are present for downstream consumers (resume-prompt logic), not for `check_compaction()`.
- Verification approach: add a test that grep-asserts `check_compaction()` still references the `compacted_at` key (cheap byte-contract check), AND add a Python-direct test in `test_pre_compact.py` asserting the full JSON shape (compacted_at, preserved, transcript_path, plus optional keys per their conditions). Do NOT require `check_compaction()` to read the optional keys — that would over-specify.

### Step 10: Update `__init__.py` module docstring

Remove the stub/FEAT-1449 forward reference from `scripts/little_loops/hooks/__init__.py` and replace with accurate description of the real dispatcher behavior.

### Step 11: Add dispatcher routing tests to `test_hook_intents.py`

_Wiring pass added by `/ll:wire-issue`:_

Extend `TestHooksMainModule` with CLI-level routing tests (distinct from Python-direct tests in `test_pre_compact.py` and subprocess adapter tests in `test_hooks_integration.py`):

- `test_dispatch_pre_compact_happy_path` — pipe valid stdin JSON (`{"transcript_path": "/tmp/t.jsonl"}`); assert `returncode == 2` and feedback string in `stderr`
- `test_dispatch_unknown_intent` — pass unknown intent name as `sys.argv[1]`; assert non-zero exit and error message in `stderr`
- `test_dispatch_pre_compact_empty_stdin` — pipe empty string; assert `returncode == 0` (noop fallback from malformed-payload branch)

Note: `test_module_dispatch_exit_zero` (line 250) asserts `"little_loops.hooks" in result.stderr` — the new dispatcher's no-arg usage string must retain this substring.

### Step 12: Update documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/ARCHITECTURE.md` — add `hooks/adapters/claude-code/precompact.sh` to the `hooks/` directory tree (new `adapters/` subtree is entirely absent from current tree listing)
- `docs/development/TROUBLESHOOTING.md` — update three stale references:
  - Line 806: add `chmod +x hooks/adapters/claude-code/precompact.sh` to the "make hooks executable" setup step
  - Lines 1005–1008: update manual test snippet from `bash hooks/scripts/precompact-state.sh` to `python -m little_loops.hooks pre_compact`
  - Line 1039: update lock timeout reference from `precompact-state.sh` to the Python handler

## Files to Create

- `scripts/little_loops/hooks/pre_compact.py`
- `hooks/adapters/claude-code/precompact.sh`
- `hooks/adapters/claude-code/` (directory)
- `scripts/tests/test_pre_compact.py`

## Files to Modify

- `scripts/little_loops/hooks/__init__.py` (dispatcher wiring + docstring)
- `hooks/hooks.json` (PreCompact command path)
- `scripts/tests/test_hooks_integration.py` (TestPrecompactState fixture path)
- `scripts/tests/test_hook_intents.py` (guard test_module_dispatch_exit_zero)

## Integration Map

### Source of truth being ported

- `hooks/scripts/precompact-state.sh` — shell handler. Key behaviors to preserve byte-for-byte:
  - stdin via `cat` → `jq -r '.transcript_path // ""'` (line 25)
  - base JSON shape (lines 39–46): `compacted_at`, `transcript_path`, `preserved: true`
  - optional `context_state_at_compact` merge (lines 49–54)
  - `recent_plan_files` via `find ... -mtime -1 | head -5` (lines 57–63, filesystem order)
  - optional `continue_prompt_exists` (lines 66–69) — KEY OMITTED when file absent
  - `acquire_lock "$STATE_LOCK" 3` with best-effort fallback (lines 72–79)
  - feedback to stderr (line 82), exit 2 (line 84)
- `hooks/scripts/lib/common.sh` — shell primitives `acquire_lock`, `atomic_write_json` (the behavior the Python equivalents in `file_utils.py` replicate)

### Dependents / Consumers

- `hooks/scripts/context-monitor.sh::check_compaction()` (lines 176–206) — reads `.compacted_at` from `.ll/ll-precompact-state.json` (line 185); deletes the file after consumption at `main()` line 268. Sole structural dependency on the JSON shape.
- `hooks/hooks.json` PreCompact entry (lines 110–122) — Claude Code triggers the adapter via `bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/precompact.sh` after this change.

### Python primitives in use (FEAT-1454)

- `scripts/little_loops/file_utils.py:35` — `atomic_write_json(path: Path, data: Any) -> None` (raises `ValueError` on NaN/Infinity, `OSError` on disk failure)
- `scripts/little_loops/file_utils.py:61` — `acquire_lock(path: Path, timeout: float = 10.0)` — context manager, raises `TimeoutError`
- `scripts/little_loops/hooks/types.py:21` — `LLHookEvent(host, intent="", timestamp="", payload={}, session_id=None, cwd=None)`
- `scripts/little_loops/hooks/types.py:85` — `LLHookResult(exit_code=0, feedback=None, decision=None, data={})`

### Patterns to model after

- `scripts/tests/test_file_utils.py::TestAcquireLock.test_concurrent_writers_via_acquire_lock` — lock + atomic write under contention
- `scripts/tests/test_hook_intents.py::TestLLHookEvent` / `TestLLHookResult` — dataclass construction and assertion style
- `scripts/tests/test_hook_intents.py::TestHooksMainModule.test_module_dispatch_exit_zero` (line 250) — subprocess module-CLI assertion (must continue passing)
- `scripts/tests/test_generate_schemas.py:180` — `monkeypatch.chdir(tmp_path)` cwd isolation
- `scripts/tests/test_hooks_integration.py::TestPrecompactState` (line 1624) — subprocess adapter execution pattern (fixture path will be retargeted)

### Adapter scaffolding

- `hooks/adapters/` and `hooks/adapters/claude-code/` directories do NOT yet exist — this is the first adapter wrapper landing under the new layout.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/hooks/__main__.py` — entry point that calls `raise SystemExit(main_hooks())`; no changes needed but affected by dispatcher rewrite [Agent 1 finding]
- `scripts/tests/test_extension.py` — smoke-imports `LLHookEvent` and `LLHookResult` from `little_loops` top-level (lines ~558, ~565); watch for circular import if `pre_compact.py` inadvertently imports from the top-level `little_loops` package [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_hook_intents.py` — **dispatcher routing tests missing**: `TestHooksMainModule` currently has only `test_module_dispatch_exit_zero`; Step 11 adds routing tests for `pre_compact` intent dispatch, unknown intent dispatch, and empty-stdin noop (see Step 11 above) [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py::TestContextMonitorLockTimeout.test_lock_timeout_leaves_adequate_margin` (line 1919) — docstring names `precompact-state.sh` as lock-timeout reference; will become stale after migration but test itself remains valid (reads shell file directly) — no functional change needed [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/ARCHITECTURE.md` — directory tree under `hooks/` lists `precompact-state.sh` but omits the new `hooks/adapters/` subtree; update to show `hooks/adapters/claude-code/precompact.sh` (see Step 12) [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — three stale references: line 806 setup step, lines 1005–1008 manual test snippet, line 1039 lock timeout comment (see Step 12) [Agent 2 finding]
- `docs/reference/API.md` — Module Overview table omits `little_loops.hooks` entirely; consider adding a row for the dispatch entry point after this issue lands [Agent 2 finding]

## Acceptance Criteria

- `scripts/little_loops/hooks/pre_compact.py` exists as a pure-function handler
- `hooks/adapters/claude-code/precompact.sh` is executable and wired in `hooks/hooks.json`
- Manual: trigger a Claude Code PreCompact event; `.ll/ll-precompact-state.json` is still written with correct shape
- `TestClaudeCodePrecompactAdapter` (or updated `TestPrecompactState`) passes
- `test_pre_compact.py` Python-direct tests pass
- `test_module_dispatch_exit_zero` still passes
- `python -m pytest scripts/tests/test_hook_intents.py scripts/tests/test_hooks_integration.py scripts/tests/test_pre_compact.py -v`
- `python -m mypy scripts/little_loops/hooks/`

## Resolution

Implemented in this session:

- `scripts/little_loops/hooks/pre_compact.py` — pure-function `handle(LLHookEvent) -> LLHookResult`, byte-equivalent to `precompact-state.sh` for the wire-visible state file. Uses `acquire_lock(timeout=3.0)` + best-effort `TimeoutError` fallback and `atomic_write_json` from `little_loops.file_utils`.
- `scripts/little_loops/hooks/__init__.py::main_hooks()` — replaced the FEAT-1448 stub with a real dispatcher: no-arg → usage + exit 0; unknown intent → exit 1; `pre_compact` → reads stdin JSON (empty/malformed → exit 0 noop), builds `LLHookEvent`, calls handler, prints feedback to stderr, returns handler exit code.
- `hooks/adapters/claude-code/precompact.sh` — three-line wrapper invoking `python -m little_loops.hooks pre_compact`.
- `hooks/hooks.json` — `PreCompact.command` retargeted from `hooks/scripts/precompact-state.sh` to `hooks/adapters/claude-code/precompact.sh`.
- `scripts/tests/test_pre_compact.py` — 11 Python-direct tests covering happy path, context-state merge, recent_plan_files (collection, 5-cap, 24h filter), continue_prompt key presence/absence, result contract, malformed-payload noop, concurrent invocation, and a grep-assert that `context-monitor.sh::check_compaction` still reads `.compacted_at`.
- `scripts/tests/test_hook_intents.py::TestHooksMainModule` — added `test_dispatch_pre_compact_happy_path`, `test_dispatch_unknown_intent`, `test_dispatch_pre_compact_empty_stdin`; the existing `test_module_dispatch_exit_zero` still passes (usage string retains "little_loops.hooks" substring).
- `scripts/tests/test_hooks_integration.py::TestPrecompactState` — fixture path retargeted to the new adapter; existing methods pass unchanged.
- `docs/ARCHITECTURE.md`, `docs/development/TROUBLESHOOTING.md` — updated for the new adapter layout (chmod step, manual-test snippet, lock-timeout reference).

Verification: `python -m pytest scripts/tests/test_pre_compact.py scripts/tests/test_hook_intents.py scripts/tests/test_hooks_integration.py -v` → 99 passed. `python -m mypy scripts/little_loops/hooks/` → success. End-to-end adapter smoke test in `/tmp` produced the expected exit 2 + state file. Full-suite pytest shows 7 unrelated pre-existing failures (`test_generate_schemas.py`, `test_update_skill.py`) verified to fail on baseline before my changes.

## Session Log
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15c3bdc5-0e46-4393-8af1-1aeee63a95a5.jsonl`
- `/ll:wire-issue` - 2026-05-12T01:43:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c136dd57-fddc-4b3e-832e-be413bb882fd.jsonl`
- `/ll:refine-issue` - 2026-05-12T01:37:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d0396bd-965c-48cc-8504-566ce6869c22.jsonl`
- `/ll:issue-size-review` - 2026-05-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c5f319b-68fa-4ac3-990a-9ace13bbeaea.jsonl`
- `/ll:manage-issue` - 2026-05-12T02:03:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f22057c-6347-4485-a795-f6dc07951014.jsonl`
