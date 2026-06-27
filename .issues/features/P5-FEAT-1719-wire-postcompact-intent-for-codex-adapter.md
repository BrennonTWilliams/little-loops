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
blocks:
- FEAT-1721
labels: [codex, hooks, host-compat]
---

# FEAT-1719: Wire `PostCompact` intent for Codex adapter

## Summary

Codex exposes a `PostCompact` event with the same payload shape as `PreCompact`. EPIC-1463 listed this as an unfiled child deferred until "a real consumer is identified." This issue formalizes that gap so it has a concrete tracking entry and implementation path.

## Motivation

`PostCompact` is a Codex-native event with no ll consumer yet, but the gap is invisible — there is no documented "this intentionally does nothing" entry in `scripts/little_loops/hooks/adapters/codex/hooks.json`. When a consumer is built (e.g., post-compaction state reset, index refresh), the adapter hook needs to exist. Capturing now makes the gap explicit and the wiring path clear.

## Current Behavior

`scripts/little_loops/hooks/adapters/codex/hooks.json` has no `PostCompact` entry. The `HOST_COMPATIBILITY.md` marks it `(deferred)[^postcompact]` with a footnote acknowledging the payload shape is compatible. No `post_compact.py` handler module exists in `scripts/little_loops/hooks/`.

## Expected Behavior

A `PostCompact` entry exists in `scripts/little_loops/hooks/adapters/codex/hooks.json` pointing to a `post-compact-after.sh` adapter script. A no-op `post_compact` Python handler is registered in `_dispatch_table()`. The HOST_COMPATIBILITY matrix `PostCompact` Codex cell reflects wired status.

## Acceptance Criteria

- `scripts/little_loops/hooks/post_compact.py` exists with a no-op `handle(event: LLHookEvent) -> LLHookResult` returning `LLHookResult(exit_code=0)`
- `scripts/little_loops/hooks/__init__.py` `_dispatch_table()` includes `post_compact` and `_USAGE` string is updated
- `scripts/little_loops/hooks/adapters/codex/post-compact-after.sh` exists, is executable, sets `LL_HOOK_HOST=codex`, invokes `python -m little_loops.hooks post_compact`
- `scripts/little_loops/hooks/adapters/codex/hooks.json` includes a `PostCompact` entry (timeout: 30s to match `PreCompact`, `statusMessage: "Post-compaction cleanup..."`)
- `scripts/tests/test_codex_adapter.py` covers the new script
- `docs/reference/HOST_COMPATIBILITY.md` `post_compact` Codex CLI cell updated from `(deferred)` to `✓`

## Implementation Steps

1. Create `scripts/little_loops/hooks/post_compact.py` — mirror `post_tool_use.py` (no-op handler, `LLHookResult(exit_code=0)`)
2. Register in `scripts/little_loops/hooks/__init__.py` — add `post_compact` to `_dispatch_table()` built_ins dict and `_USAGE` string
3. Create `scripts/little_loops/hooks/adapters/codex/post-compact-after.sh` — 4-line shim mirroring `pre-compact.sh`, intent `post_compact`
4. Add `PostCompact` entry to `scripts/little_loops/hooks/adapters/codex/hooks.json`
5. Extend `scripts/tests/test_codex_adapter.py` (file-exists, executable, hooks.json presence, LL_HOOK_HOST sentinel)
6. Flip `post_compact` Codex cell in `docs/reference/HOST_COMPATIBILITY.md`; remove or update `[^postcompact]` footnote

## Notes

- Trust-hash churn: adding `PostCompact` to `hooks.json` invalidates the existing hash; users re-trust on next startup.
- Handler intentionally no-op at creation — consumers add logic as needed.
- Timeout: use 30s (same as `PreCompact`) since post-compaction cleanup may involve file I/O.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/hooks/adapters/codex/hooks.json` | File to modify |
| `scripts/little_loops/hooks/adapters/codex/pre-compact.sh` | Template for new script |
| `docs/reference/HOST_COMPATIBILITY.md` | `post_compact` row to flip |
| `scripts/little_loops/hooks/post_tool_use.py` | Template for no-op handler module |

## Verification Notes

2026-06-13 (OUTDATED): Implementation not started. `scripts/little_loops/hooks/post_compact.py` does not exist. `_dispatch_table()` in hooks/__init__.py has no post_compact entry. PostCompact is absent from `hooks/adapters/codex/hooks.json`. Scope includes PermissionRequest handling (absorbed from cancelled FEAT-1720). Create handler, register in dispatch table, add to hooks.json, create post-compact-after.sh shim.

2026-06-18 (OUTDATED): `scripts/little_loops/hooks/post_compact.py` still absent. `_dispatch_table()` has no `post_compact` entry. `hooks/adapters/codex/hooks.json` still has no PostCompact or PermissionRequest entries. Implementation not started; issue scope (absorbing FEAT-1720's PermissionRequest) is accurate.

- **2026-06-26** (/ll:verify-issues): Updated stale repo-root `hooks/adapters/codex/` path references (hooks.json, post-compact-after.sh, pre-compact.sh) to the post-FEAT-2274 in-package location `scripts/little_loops/hooks/adapters/codex/` across Motivation, Current/Expected Behavior, Acceptance Criteria, Implementation Steps, doc table, and the shared-files Scope Boundary note. PostCompact handler/dispatch/hooks.json gap is real and unstarted — substance unchanged.

## Status

**Open** | Created: 2026-05-26 | Priority: P5

## Session Log
- `/ll:verify-issues` - 2026-06-25T00:51:21 - `3417b033-6605-44ca-9411-53f9fd585b45.jsonl`
- `/ll:verify-issues` - 2026-06-14T00:13:05 - `dcbaf608-eff5-4e7b-8a64-4d13a266c421.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:01 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:55 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T14:29:20 - `f3a091ba-2869-499e-9de4-7f5c8ca96083.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:57 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:10 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:23:05Z - `1e210ff4-bcab-4372-9c8c-a0ba98da62d5.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and FEAT-1720 both modify the same three shared files: `scripts/little_loops/hooks/__init__.py` (`_dispatch_table()` and `_USAGE`), `scripts/little_loops/hooks/adapters/codex/hooks.json`, and `scripts/tests/test_codex_adapter.py`. FEAT-1720 `depends_on: [FEAT-1719]` — this issue's PR **must be merged first**. FEAT-1720's PR must be rebased on this merged commit before opening. Alternatively, batch both handler registrations into a single PR to eliminate the coordination burden entirely.

---

## Scope Addition

**Source**: Merged from FEAT-1720 during `/ll:audit-issue-conflicts` conflict resolution (2026-06-09).

Both issues register Codex adapter hooks in the same three shared files. To eliminate rebase coordination overhead, this issue's PR now covers both handlers in one pass:

- **PostCompact** (original scope): `post_compact.py` no-op handler, `post-compact-after.sh`, `hooks.json` `PostCompact` entry (timeout: 30s), test coverage, HOST_COMPATIBILITY flip.
- **PermissionRequest** (absorbed from FEAT-1720): `permission_request.py` no-op handler returning `LLHookResult(exit_code=0)`, `permission-request.sh`, `hooks.json` `PermissionRequest` entry (timeout: 5s, `statusMessage: "Checking permission..."`), test coverage, HOST_COMPATIBILITY flip. Exit code semantics: exit 0 = pass-through (model decides); exit 2 = block. Verify `permission_request` payload shape from Codex CLI docs before implementing — confirm field names (tool name, arguments) match expected schema.
