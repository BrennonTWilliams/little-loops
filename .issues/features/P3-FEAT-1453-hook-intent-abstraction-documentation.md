---
id: FEAT-1453
type: FEAT
priority: P3
status: open
parent: FEAT-1116
discovered_date: 2026-05-12
discovered_by: issue-size-review
---

# FEAT-1453: Hook-Intent Abstraction Layer — Documentation

## Summary

Write all end-user and developer documentation for the hook-intent abstraction layer introduced by FEAT-1116. Covers the "How to write a little-loops hook" guide, reference doc updates, architecture updates, and TROUBLESHOOTING path fixes.

## Parent Issue

Decomposed from FEAT-1116: Hook-Intent Abstraction Layer for Multi-Host Support

## Depends On

- FEAT-1448 (types exist)
- FEAT-1450 (both SessionStart and PreCompact adapters exist — enough system to document)
- FEAT-1452 (Protocol documented alongside extension authoring docs)

## Scope

Covers FEAT-1116 Implementation Step 8 and all documentation coupling identified by the wiring pass.

### New Docs

- `docs/claude-code/` — new "How to write a little-loops hook" guide covering the intent model, `LLHookEvent`/`LLHookResult`, adapter flow, and how to register via `LLHookIntentExtension`
- `docs/claude-code/automate-workflows-with-hooks.md` — add adapter flow diagram

### Reference Doc Updates

- `docs/claude-code/hooks-reference.md` — add section on the intent model and adapters
- `docs/reference/EVENT-SCHEMA.md` — document `LLHookEvent` type (analogous to existing `LLEvent` documentation); cross-link between the two types
- `docs/reference/API.md:36-37` — add `little_loops.hooks` row to the Module Overview table; add `LLHookEvent`, `LLHookResult`, `LLHookIntentExtension` to the Extension API section (lines 5163-5339)
- `docs/reference/CONFIGURATION.md:617` — add `little_loops.hook_intents` entry-point group description (or note that it uses the existing `little_loops.extensions` group per Decision 2)
- `docs/reference/CONFIGURATION.md:527` — update `### scratch_pad` section: `hooks/scripts/scratch-pad-redirect.sh` path becomes stale if/when it migrates to `hooks/adapters/claude-code/`

### Architecture Updates

- `docs/ARCHITECTURE.md:84-95` — add `hooks/adapters/` and `hooks/core/` to the directory tree
- `docs/ARCHITECTURE.md` Extension Architecture section (lines 454-512) — update to document `LLHookIntentExtension` alongside `LLExtension`, `InterceptorExtension`, `wire_extensions()`
- `docs/ARCHITECTURE.md:969` — update exact path reference if `hooks/scripts/issue-completion-log.sh` migrates

### Troubleshooting Updates

- `docs/development/TROUBLESHOOTING.md:750-941` — update `chmod +x` instructions and manual test invocations for `context-monitor.sh`, `user-prompt-check.sh`, `precompact-state.sh`, `check-duplicate-issue-id.sh` to reflect adapter paths under `hooks/adapters/claude-code/`

### Testing Docs

- `docs/development/TESTING.md:774-781` — update `hook_script: Path` fixture pattern to show both legacy shell and adapter fixture variants

## Acceptance Criteria

- "How to write a little-loops hook" guide exists under `docs/claude-code/`
- `hooks-reference.md` has an intent model section
- `EVENT-SCHEMA.md` documents `LLHookEvent` with cross-link to `LLEvent`
- `API.md` Module Overview table includes `little_loops.hooks`
- `ARCHITECTURE.md` directory tree includes `hooks/adapters/` and `hooks/core/`
- `TROUBLESHOOTING.md` paths updated for moved adapter scripts
- `TESTING.md` fixture pattern updated

## Session Log
- `/ll:issue-size-review` - 2026-05-12T00:20:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cb0dc9a-fd6f-4945-97b0-ad6acec56482.jsonl`
