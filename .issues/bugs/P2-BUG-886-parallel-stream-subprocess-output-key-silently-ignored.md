---
discovered_date: 2026-03-25
discovered_by: audit-architecture
focus_area: integration
confidence_score: 100
outcome_confidence: 100
---

# BUG-886: `parallel.stream_subprocess_output` config key silently ignored by Python CLI

## Summary

`ParallelAutomationConfig.from_dict()` reads `data.get("stream_output", False)` instead of
`data.get("stream_subprocess_output", False)`. The user-facing config key documented in the
schema, written by the `configure` skill, and shown in `CONFIGURATION.md` is
`stream_subprocess_output` — but the Python layer never reads it. Any user setting is silently
dropped and the value is always `False`.

## Current Behavior

Setting `parallel.stream_subprocess_output: true` in `ll-config.json` has no effect. `ParallelAutomationConfig.from_dict()` reads the wrong key (`stream_output`) and always returns `False` for `stream_subprocess_output`, regardless of the user's config.

## Expected Behavior

Setting `parallel.stream_subprocess_output: true` in `ll-config.json` should cause `ll-parallel` to run with subprocess output streaming enabled (`stream_subprocess_output=True`).

## Steps to Reproduce

1. Set `parallel.stream_subprocess_output: true` in `.claude/ll-config.json`
2. Run `ll-parallel` to process an issue
3. Observe that subprocess output is not streamed — `stream_subprocess_output` is effectively `False` regardless of config
4. Or directly: `ParallelAutomationConfig.from_dict({"stream_subprocess_output": True}).base.stream_output` returns `False` (should be `True`)

## Root Cause

- **File**: `scripts/little_loops/config/automation.py`
- **Anchor**: `in function ParallelAutomationConfig.from_dict()`
- **Cause**: `from_dict()` calls `data.get("stream_output", False)` but the documented config key is `stream_subprocess_output`. The wrong key name means user config is never read and the value is always `False`.

## Location

- **File**: `scripts/little_loops/config/automation.py`
- **Line**: 73
- **Module**: `little_loops.config.automation.ParallelAutomationConfig`

## Finding

### Current State

```python
# automation.py:68-74 — reads wrong key name
base = AutomationConfig(
    timeout_seconds=data.get("timeout_per_issue", data.get("timeout_seconds", 3600)),
    state_file=data.get("state_file", ".parallel-manage-state.json"),
    worktree_base=data.get("worktree_base", ".worktrees"),
    max_workers=data.get("max_workers", 2),
    stream_output=data.get("stream_output", False),   # ← bug: key should be "stream_subprocess_output"
)
```

All other config sources consistently use the name `stream_subprocess_output` for the parallel section:
- `config-schema.json:236`: defines `parallel.stream_subprocess_output`
- `skills/configure/areas.md:241`: reads and writes `stream_subprocess_output`
- `docs/reference/CONFIGURATION.md:58`: documents it as `stream_subprocess_output`
- `scripts/little_loops/parallel/types.py:325`: `ParallelConfig.stream_subprocess_output` field

The `automation` section correctly uses `stream_output` in both schema and code — the mismatch
is specific to the `parallel` section only.

### Impact

- **Functional**: Setting `parallel.stream_subprocess_output: true` in `ll-config.json` has no
  effect. `ll-parallel` always runs with `stream_subprocess_output=False` regardless of config.
- **User trust**: The `configure` skill accepts and persists this setting, giving no indication it
  is ignored.
- **Tracing**: Log output from parallel workers is never streamed even when explicitly enabled.

## Proposed Solution

Fix the key name read in `ParallelAutomationConfig.from_dict()`:

```python
# automation.py:73 — fix
stream_output=data.get("stream_subprocess_output", data.get("stream_output", False)),
```

The `data.get("stream_output", ...)` fallback preserves backwards compatibility for any existing
configs that accidentally used the wrong key.

### Test to add

```python
def test_stream_subprocess_output_key_is_respected(self) -> None:
    config = ParallelAutomationConfig.from_dict({"stream_subprocess_output": True})
    assert config.base.stream_output is True

def test_stream_output_fallback_still_works(self) -> None:
    config = ParallelAutomationConfig.from_dict({"stream_output": True})
    assert config.base.stream_output is True
```

## Integration Map

### Files to Modify
- `scripts/little_loops/config/automation.py` — fix key name in `ParallelAutomationConfig.from_dict()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config/core.py:310-311` — `create_parallel_config()` bridges `ParallelAutomationConfig.base.stream_output` → `ParallelConfig.stream_subprocess_output`; the fix here will flow through correctly
- `scripts/little_loops/config/__init__.py` — re-exports `ParallelAutomationConfig` as part of public API
- `scripts/little_loops/parallel/types.py:440` — `ParallelConfig.from_dict()` reads `stream_subprocess_output` directly (correct)
- `scripts/little_loops/parallel/worker_pool.py:707` — reads `parallel_config.stream_subprocess_output` to control streaming
- `scripts/little_loops/cli/parallel.py:194` — passes `args.stream_output` into `create_parallel_config()` (CLI flag, separate from config file)

### Similar Patterns
- `config-schema.json` — correctly defines `parallel.stream_subprocess_output`
- `skills/configure/areas.md` — reads/writes `stream_subprocess_output`
- `docs/reference/CONFIGURATION.md` — documents `stream_subprocess_output`

### Tests
- `scripts/tests/test_config.py:263-325` — `TestParallelAutomationConfig` class with `test_from_dict_with_all_fields` and `test_from_dict_with_defaults`; note: existing all-fields test uses `"stream_output"` key (not `"stream_subprocess_output"`), so it passes despite the bug — new tests target the correct key
- Add `test_stream_subprocess_output_key_is_respected` and `test_stream_output_fallback_still_works` to `TestParallelAutomationConfig` in `scripts/tests/test_config.py`
- Pattern: follow `test_timeout_per_issue_key_is_respected` / `test_timeout_seconds_fallback` at lines ~304-322 for the key-alias test pattern

### Documentation
- N/A — bug fix does not require documentation updates (schema and docs are already correct)

### Configuration
- N/A — `config-schema.json` schema is correct; only code fix needed

## Implementation Steps

1. Fix key name in `ParallelAutomationConfig.from_dict()` (`automation.py` ~line 73): change `data.get("stream_output", False)` to `data.get("stream_subprocess_output", data.get("stream_output", False))`
2. Add regression tests: `test_stream_subprocess_output_key_is_respected` and `test_stream_output_fallback_still_works`
3. Run `python -m pytest scripts/tests/` to verify fix and confirm no regressions

## Impact

- **Priority**: P2 — config silently ignored; users cannot enable subprocess streaming despite explicit configuration
- **Severity**: High
- **Effort**: Small (one-line fix + two test cases)
- **Risk**: Low
- **Breaking Change**: No

## Labels

`bug`, `config`, `parallel`, `auto-generated`

## Session Log
- `hook:posttooluse-git-mv` - 2026-03-25T23:51:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c08a4d1-4815-492c-b395-d3c62c150492.jsonl`
- `/ll:ready-issue` - 2026-03-25T23:47:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a87eee94-da5c-4b40-8e7a-8e59e29af4a1.jsonl`
- `/ll:refine-issue` - 2026-03-25T23:08:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`
- `/ll:format-issue` - 2026-03-25T23:05:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`
- `/ll:confidence-check` - 2026-03-25T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`
- `/ll:manage-issue` - 2026-03-25T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Resolution

**Fixed** | 2026-03-25

Changed `data.get("stream_output", False)` to `data.get("stream_subprocess_output", data.get("stream_output", False))` in `ParallelAutomationConfig.from_dict()` (`scripts/little_loops/config/automation.py:73`). Added two regression tests to `TestParallelAutomationConfig` in `scripts/tests/test_config.py`: `test_stream_subprocess_output_key_is_respected` and `test_stream_output_fallback_still_works`. All 3909 tests pass.

---

## Status

**Completed** | Created: 2026-03-25 | Priority: P2
