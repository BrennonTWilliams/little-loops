---
id: FEAT-1450
type: FEAT
priority: P3
status: open
parent: FEAT-1116
discovered_date: 2026-05-12
discovered_by: issue-size-review
---

# FEAT-1450: SessionStart Intent — Python Core Handler and Claude Code Adapter

## Summary

Port `session-start.sh` to a Python core handler and build its Claude Code adapter wrapper. SessionStart exercises the most complex shell logic (deep-merge of `ll.local.md`), so it follows FEAT-1449 which establishes the shared Python primitives for `ll_resolve_config` and deep-merge.

## Parent Issue

Decomposed from FEAT-1116: Hook-Intent Abstraction Layer for Multi-Host Support

## Depends On

- FEAT-1448 (types must exist)
- FEAT-1449 (Python primitives for `ll_resolve_config`, deep-merge, and `lib/common.sh` equivalents must be established first)

## Scope

Covers FEAT-1116 Implementation Steps 5 and 14 (session-start portion).

- **Step 5**: Port `session-start.sh` → `scripts/little_loops/hooks/session_start.py`. Logic: loads config, deep-merges `ll.local.md`, validates feature flags. Pure function: `(event: LLHookEvent) -> LLHookResult`. Reuses Python primitives established in FEAT-1449 (`ll_resolve_config`, `ll_feature_enabled`, deep-merge).
- **Step 14 (session-start)**: Update `TestSessionStartValidation` (lines 1318–1465 in `test_hooks_integration.py`) fixture path from `hooks/scripts/session-start.sh` to `hooks/adapters/claude-code/session-start.sh`, or add `TestClaudeCodeSessionStartAdapter` and retire the legacy class. Note: this test asserts exact stderr strings — verify they match the Python handler's output.
- Create `hooks/adapters/claude-code/session-start.sh` — thin wrapper: `INPUT=$(cat); echo "$INPUT" | python -m little_loops.hooks session_start; exit $?`. Update `hooks/hooks.json` `SessionStart` entry to point at the adapter.

## New Files to Create

- `scripts/little_loops/hooks/session_start.py` — Python core handler
- `hooks/adapters/claude-code/session-start.sh` — Claude Code adapter wrapper

## Files to Modify

- `hooks/hooks.json` — update `SessionStart` event to point at `hooks/adapters/claude-code/session-start.sh`
- `scripts/tests/test_hooks_integration.py` — update `TestSessionStartValidation` fixture path or add `TestClaudeCodeSessionStartAdapter`

## Tests

- Python-direct tests for `session_start` handler: call with `LLHookEvent`, assert on config-load, deep-merge, and feature-flag validation behavior; verify exact stderr-equivalent error messages match those previously asserted in `TestSessionStartValidation`
- Adapter round-trip test (`TestClaudeCodeSessionStartAdapter`): subprocess pattern pointing to `hooks/adapters/claude-code/session-start.sh`
- Manual: trigger a Claude Code SessionStart; verify config deep-merge applies `ll.local.md` overrides correctly

## Acceptance Criteria

- `scripts/little_loops/hooks/session_start.py` exists as a pure-function handler
- `hooks/adapters/claude-code/session-start.sh` is executable and wired in `hooks/hooks.json`
- All assertions from `TestSessionStartValidation` are preserved in updated/new test class
- `python -m pytest scripts/tests/test_hook_intents.py scripts/tests/test_hooks_integration.py -v`
- `python -m mypy scripts/little_loops/hooks/`

## Session Log
- `/ll:issue-size-review` - 2026-05-12T00:20:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cb0dc9a-fd6f-4945-97b0-ad6acec56482.jsonl`
