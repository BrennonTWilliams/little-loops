---
id: FEAT-1455
type: FEAT
priority: P3
status: open
parent: FEAT-1449
discovered_date: 2026-05-11
discovered_by: issue-size-review
decision_needed: false
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

Pure function `def handle(event: LLHookEvent) -> LLHookResult`. Must be byte-equivalent to `precompact-state.sh` for the wire-visible state file:

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
- Create `.ll/` if it does not exist
- If `LLHookEvent` fails to parse: return `LLHookResult(exit_code=0)` (noop)
- If `thoughts/shared/plans/` does not exist: `recent_plan_files: []`
- Lock timeout must NOT block the write

### Step 5: Wire `scripts/little_loops/hooks/__init__.py::main_hooks()`

- Parse `sys.argv[1]` as intent name; reject unknown intents with non-zero exit + stderr message.
- For `pre_compact`: read stdin JSON → build `LLHookEvent(host="claude-code", intent="pre_compact", payload=<parsed>, cwd=os.getcwd())` → call `pre_compact.handle(event)` → print `result.feedback` to stderr if set → exit `result.exit_code`.
- **Preserve no-arg behavior**: still exit 0 and print usage to stderr (required by `test_module_dispatch_exit_zero`).

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
- Update `TestPrecompactState.hook_script` fixture (line 1720) from `hooks/scripts/precompact-state.sh` to `hooks/adapters/claude-code/precompact.sh` (or rename class to `TestClaudeCodePrecompactAdapter`). The two existing test methods (`test_atomic_write_with_missing_directory`, `test_concurrent_precompact_writes`) should pass unchanged once the fixture path is updated.

**`scripts/tests/test_hook_intents.py`**
- Update or guard `TestHooksMainModule.test_module_dispatch_exit_zero` to verify no-arg invocation still exits 0 + prints usage.

**`scripts/tests/test_pre_compact.py`** (new file)
- Python-direct tests for `handle()`: import handler, call with `LLHookEvent`, assert `LLHookResult` fields and `.ll/ll-precompact-state.json` contents.
- Use `monkeypatch.chdir(tmp_path)` for cwd isolation.
- Model after `scripts/tests/test_hook_intents.py` dataclass test style.

### Step 9: Verify behavioral contract

- Add a test fixture or assertion that reads `hooks/scripts/context-monitor.sh::check_compaction()` and asserts the `compacted_at`, `preserved`, `transcript_path` keys are consumed — ensuring byte-equivalent JSON contract is maintained.

### Step 10: Update `__init__.py` module docstring

Remove the stub/FEAT-1449 forward reference from `scripts/little_loops/hooks/__init__.py` and replace with accurate description of the real dispatcher behavior.

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

## Acceptance Criteria

- `scripts/little_loops/hooks/pre_compact.py` exists as a pure-function handler
- `hooks/adapters/claude-code/precompact.sh` is executable and wired in `hooks/hooks.json`
- Manual: trigger a Claude Code PreCompact event; `.ll/ll-precompact-state.json` is still written with correct shape
- `TestClaudeCodePrecompactAdapter` (or updated `TestPrecompactState`) passes
- `test_pre_compact.py` Python-direct tests pass
- `test_module_dispatch_exit_zero` still passes
- `python -m pytest scripts/tests/test_hook_intents.py scripts/tests/test_hooks_integration.py scripts/tests/test_pre_compact.py -v`
- `python -m mypy scripts/little_loops/hooks/`

## Session Log
- `/ll:issue-size-review` - 2026-05-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c5f319b-68fa-4ac3-990a-9ace13bbeaea.jsonl`
