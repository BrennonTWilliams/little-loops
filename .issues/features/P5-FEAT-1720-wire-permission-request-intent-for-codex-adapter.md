---
id: FEAT-1720
type: FEAT
priority: P5
status: open
captured_at: "2026-05-26T02:23:05Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1463
labels: [codex, hooks, host-compat]
---

# FEAT-1720: Wire `permission_request` intent for Codex adapter

## Summary

Codex exposes a `permission_request` event when a tool requires user approval. EPIC-1463 listed this as an unfiled deferred child. This issue formalizes the gap with a concrete tracking entry and implementation path, gated on identifying a real consumer.

## Motivation

Without a wired `permission_request` handler, ll has no way to intercept Codex approval prompts — e.g., to auto-approve known-safe tools, inject project-level policy, or log permission events. The gap is currently invisible (no `(deferred)` entry in `hooks.json`). Capturing it makes the path clear and gives future consumers a place to wire against.

## Current Behavior

`hooks/adapters/codex/hooks.json` has no `PermissionRequest` entry. `HOST_COMPATIBILITY.md` shows `(deferred)` for this row with no tracking link. No `permission_request.py` handler module exists.

## Expected Behavior

A `PermissionRequest` entry exists in `hooks/adapters/codex/hooks.json`. A no-op `permission_request` Python handler is registered and returns pass-through (exit 0) by default, allowing the model to proceed with its normal approval dialog. Consumers can add blocking logic (exit 2) to auto-deny or inject policy.

## Acceptance Criteria

- `scripts/little_loops/hooks/permission_request.py` exists with a no-op `handle(event: LLHookEvent) -> LLHookResult` returning `LLHookResult(exit_code=0)`
- `scripts/little_loops/hooks/__init__.py` `_dispatch_table()` includes `permission_request` entry; `_USAGE` string updated
- `hooks/adapters/codex/permission-request.sh` exists, executable, sets `LL_HOOK_HOST=codex`, invokes `python -m little_loops.hooks permission_request`
- `hooks/adapters/codex/hooks.json` includes a `PermissionRequest` entry (timeout: 5s)
- `docs/reference/HOST_COMPATIBILITY.md` `permission_request` Codex CLI cell updated from `(deferred)` to `✓`

## Implementation Steps

1. Create `scripts/little_loops/hooks/permission_request.py` — no-op handler mirroring `post_tool_use.py`
2. Register in `scripts/little_loops/hooks/__init__.py`
3. Create `hooks/adapters/codex/permission-request.sh` — 4-line shim, intent `permission_request`
4. Add `PermissionRequest` entry to `hooks/adapters/codex/hooks.json` (timeout: 5s, `statusMessage: "Checking permission..."`)
5. Extend `scripts/tests/test_codex_adapter.py`
6. Flip `permission_request` Codex cell in `docs/reference/HOST_COMPATIBILITY.md`

## Notes

- Trust-hash churn on `hooks.json` change — document in PR.
- Exit code semantics: exit 0 = pass-through (model decides); exit 2 = block with feedback injected. No-op handler ships as exit 0.
- Verify `permission_request` payload shape from Codex CLI docs before implementing — confirm field names (tool name, arguments) match expected schema.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `hooks/adapters/codex/hooks.json` | File to modify |
| `scripts/little_loops/hooks/post_tool_use.py` | Template for no-op handler |
| `docs/reference/HOST_COMPATIBILITY.md` | Row to flip |

## Status

**Open** | Created: 2026-05-26 | Priority: P5

## Session Log
- `/ll:capture-issue` - 2026-05-26T02:23:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e210ff4-bcab-4372-9c8c-a0ba98da62d5.jsonl`
