---
id: FEAT-1719
title: Wire `PostCompact` intent for Codex adapter
type: FEAT
priority: P5
status: open
captured_at: "2026-05-26T02:23:05Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1463
blocked_by: [ENH-1718]
labels: [codex, hooks, host-compat]
---

# FEAT-1719: Wire `PostCompact` intent for Codex adapter

## Summary

Codex exposes a `PostCompact` event with the same payload shape as `PreCompact`. EPIC-1463 listed this as an unfiled child deferred until "a real consumer is identified." This issue formalizes that gap so it has a concrete tracking entry and implementation path.

## Motivation

`PostCompact` is a Codex-native event with no ll consumer yet, but the gap is invisible — there is no documented "this intentionally does nothing" entry in `hooks/adapters/codex/hooks.json`. When a consumer is built (e.g., post-compaction state reset, index refresh), the adapter hook needs to exist. Capturing now makes the gap explicit and the wiring path clear.

## Current Behavior

`hooks/adapters/codex/hooks.json` has no `PostCompact` entry. The `HOST_COMPATIBILITY.md` marks it `(deferred)[^postcompact]` with a footnote acknowledging the payload shape is compatible. No `post_compact.py` handler module exists in `scripts/little_loops/hooks/`.

## Expected Behavior

A `PostCompact` entry exists in `hooks/adapters/codex/hooks.json` pointing to a `post-compact-after.sh` adapter script. A no-op `post_compact` Python handler is registered in `_dispatch_table()`. The HOST_COMPATIBILITY matrix `PostCompact` Codex cell reflects wired status.

## Acceptance Criteria

- `scripts/little_loops/hooks/post_compact.py` exists with a no-op `handle(event: LLHookEvent) -> LLHookResult` returning `LLHookResult(exit_code=0)`
- `scripts/little_loops/hooks/__init__.py` `_dispatch_table()` includes `post_compact` and `_USAGE` string is updated
- `hooks/adapters/codex/post-compact-after.sh` exists, is executable, sets `LL_HOOK_HOST=codex`, invokes `python -m little_loops.hooks post_compact`
- `hooks/adapters/codex/hooks.json` includes a `PostCompact` entry (timeout: 30s to match `PreCompact`, `statusMessage: "Post-compaction cleanup..."`)
- `scripts/tests/test_codex_adapter.py` covers the new script
- `docs/reference/HOST_COMPATIBILITY.md` `post_compact` Codex CLI cell updated from `(deferred)` to `✓`

## Implementation Steps

1. Create `scripts/little_loops/hooks/post_compact.py` — mirror `post_tool_use.py` (no-op handler, `LLHookResult(exit_code=0)`)
2. Register in `scripts/little_loops/hooks/__init__.py` — add `post_compact` to `_dispatch_table()` built_ins dict and `_USAGE` string
3. Create `hooks/adapters/codex/post-compact-after.sh` — 4-line shim mirroring `pre-compact.sh`, intent `post_compact`
4. Add `PostCompact` entry to `hooks/adapters/codex/hooks.json`
5. Extend `scripts/tests/test_codex_adapter.py` (file-exists, executable, hooks.json presence, LL_HOOK_HOST sentinel)
6. Flip `post_compact` Codex cell in `docs/reference/HOST_COMPATIBILITY.md`; remove or update `[^postcompact]` footnote

## Notes

- Trust-hash churn: adding `PostCompact` to `hooks.json` invalidates the existing hash; users re-trust on next startup.
- Handler intentionally no-op at creation — consumers add logic as needed.
- Timeout: use 30s (same as `PreCompact`) since post-compaction cleanup may involve file I/O.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `hooks/adapters/codex/hooks.json` | File to modify |
| `hooks/adapters/codex/pre-compact.sh` | Template for new script |
| `docs/reference/HOST_COMPATIBILITY.md` | `post_compact` row to flip |
| `scripts/little_loops/hooks/post_tool_use.py` | Template for no-op handler module |

## Status

**Open** | Created: 2026-05-26 | Priority: P5

## Session Log
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:23:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e210ff4-bcab-4372-9c8c-a0ba98da62d5.jsonl`
