---
id: FEAT-1451
type: FEAT
priority: P3
status: open
parent: FEAT-1116
discovered_date: 2026-05-12
discovered_by: issue-size-review
---

# FEAT-1451: OpenCode Adapter for Hook Intents

## Summary

Write the OpenCode TypeScript plugin adapter that shells out to `python -m little_loops.hooks <intent>` for SessionStart and PreCompact. This replaces FEAT-961's parallel reimplementation approach. Coordinate with FEAT-961 before executing.

## Parent Issue

Decomposed from FEAT-1116: Hook-Intent Abstraction Layer for Multi-Host Support

## Depends On

- FEAT-1449 (PreCompact Python core handler must exist)
- FEAT-1450 (SessionStart Python core handler must exist)

## Scope

Covers FEAT-1116 Implementation Step 6.

**Decision 3 (from FEAT-1116)**: The OpenCode adapter ships as shell-out first — no FFI, no persistent sidecar in the MVP. The OpenCode TS plugin invokes `python -m little_loops.hooks <intent>` per hook call.

- Create `hooks/adapters/opencode/` directory with TS plugin adapter
- Adapter covers `SessionStart` and `PreCompact` intents (MVP scope)
- When extending to hot-path intents (`PreToolUse`/`PostToolUse`), include **latency measurement** as an explicit deliverable so any sidecar follow-up is data-driven
- **Coordinate with FEAT-961** before executing: if FEAT-961 merges its parallel reimplementation first, the adapter approach arrives too late to replace it

## New Files to Create

- `hooks/adapters/opencode/` — TS plugin adapter directory
- `hooks/adapters/opencode/plugin.ts` (or equivalent) — OpenCode plugin that shells out to Python

## Acceptance Criteria

- OpenCode adapter exists under `hooks/adapters/opencode/`
- Adapter invokes `python -m little_loops.hooks session_start` and `python -m little_loops.hooks pre_compact` for corresponding events
- FEAT-961 is either blocked or rewritten to use this adapter approach (not a parallel reimplementation)
- Latency measurement deliverable documented before any hot-path intent (PreToolUse/PostToolUse) is added

## Session Log
- `/ll:issue-size-review` - 2026-05-12T00:20:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cb0dc9a-fd6f-4945-97b0-ad6acec56482.jsonl`
