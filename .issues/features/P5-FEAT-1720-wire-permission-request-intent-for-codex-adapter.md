---
id: FEAT-1720
title: Wire `permission_request` intent for Codex adapter
type: FEAT
priority: P5
status: cancelled
captured_at: '2026-05-26T02:23:05Z'
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1463
blocked_by:
- ENH-1718
depends_on:
- FEAT-1719
blocks: FEAT-1721
labels:
- codex
- hooks
- host-compat
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

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-01_

**Verdict: OUTDATED** — Implementation not started:
- `scripts/little_loops/hooks/permission_request.py` does NOT exist
- `_dispatch_table()` has no `permission_request` entry
- No `PermissionRequest` entry in `hooks/adapters/codex/hooks.json`
- Depends on FEAT-1719 (PostCompact wiring, also unstarted)

## Status

**Open** | Created: 2026-05-26 | Priority: P5

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:01 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:55 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T14:29:20 - `f3a091ba-2869-499e-9de4-7f5c8ca96083.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:58 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:11 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:23:05Z - `1e210ff4-bcab-4372-9c8c-a0ba98da62d5.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and FEAT-1719 both modify the same three shared files: `scripts/little_loops/hooks/__init__.py` (`_dispatch_table()` and `_USAGE`), `hooks/adapters/codex/hooks.json`, and `scripts/tests/test_codex_adapter.py`. This issue's PR **must be rebased on FEAT-1719's merged commit** before opening, so the `_dispatch_table()` and `hooks.json` edits from each issue are reviewed in sequence and do not produce conflicting hunks. Alternatively, batch both handler registrations into a single PR.

---

## Resolution

- **Status**: Closed - Superseded
- **Completed**: 2026-06-09
- **Reason**: Superseded by FEAT-1719 via conflict resolution audit (`/ll:audit-issue-conflicts`)
- **Status correction** (2026-06-12, epic audit): frontmatter was `done`, which implied the `permission_request` artifacts shipped — they did not (`scripts/little_loops/hooks/permission_request.py`, `hooks/adapters/codex/permission-request.sh`, and the `hooks.json` entry do not exist). Corrected to `cancelled` to match this supersession; the scope lives in FEAT-1719 (open).
- **Proposed change**: Both `post_compact` and `permission_request` handlers batched into a single PR under FEAT-1719, eliminating the rebase coordination burden on `scripts/little_loops/hooks/__init__.py`, `hooks/adapters/codex/hooks.json`, and `scripts/tests/test_codex_adapter.py`. See FEAT-1719 Scope Addition for the full implementation spec.
