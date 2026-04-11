---
id: FEAT-961
type: FEAT
priority: P4
status: open
discovered_date: 2026-04-05
discovered_by: issue-size-review
parent_issue: FEAT-769
blocked_by: [FEAT-960]
---

# FEAT-961: OpenCode JS/TS Plugin Implementation

## Summary

Create the `opencode-plugin/` directory with a Bun/TypeScript plugin that bridges little-loops' hook logic to OpenCode's event API via `@opencode-ai/plugin`, implementing all 6 event handlers.

## Parent Issue

Decomposed from FEAT-769: Add OpenCode Plugin Compatibility

## Current Behavior

No OpenCode plugin exists. OpenCode users get commands and skills (via `.claude/` fallback) but no session lifecycle hooks — context monitoring doesn't fire, duplicate ID checks are skipped, and config loading doesn't run.

## Expected Behavior

- `session.created` handler loads ll config and applies `.opencode/ll.local.md` overrides
- `tool.execute.before` handler fires duplicate issue ID check on Write/Edit operations targeting `.issues/` paths
- `tool.execute.after` handler runs context monitoring (token estimation and handoff trigger)
- `session.compacted` handler preserves task state
- `session.idle` handler cleans up state files
- Plugin loads and registers all event handlers without runtime errors

## Acceptance Criteria

- `opencode-plugin/package.json` sets `"name": "@ll/opencode-plugin"`, `"type": "module"`, Bun runtime pinned
- `opencode-plugin/index.ts` exports a `Plugin` function (from `@opencode-ai/plugin` v1.2.27) that registers all 6 handlers
- `session.created` loads `.opencode/ll-config.json` (falls back to `.claude/ll-config.json`), applies `ll.local.md` overrides
- `tool.execute.before` checks `.issues/` write/edit operations for duplicate IDs
- `tool.execute.after` estimates tokens and triggers handoff when threshold exceeded
- `session.compacted` saves precompact state to `.opencode/ll-precompact-state.json`
- `session.idle` removes `.opencode/ll-context-state.json` and `.opencode/.ll-lock`
- All handlers use `ctx.$` (BunShell) for shell execution
- Plugin installs via `npm install ./opencode-plugin` and is resolvable as `@ll/opencode-plugin`

## Proposed Solution

### Directory structure

```
opencode-plugin/
├── package.json          # { "name": "@ll/opencode-plugin", "type": "module" }
├── index.ts              # Main plugin entry point
└── hooks/
    ├── session.ts        # session.created → session-start logic
    ├── tool.ts           # tool.execute.before/after → duplicate-id + context monitor
    └── compact.ts        # session.compacted / session.idle → precompact-state logic
```

### Plugin entry point (`index.ts`)

```typescript
import type { Plugin } from "@opencode-ai/plugin";
import { onSessionCreated } from "./hooks/session.js";
import { onToolBefore, onToolAfter } from "./hooks/tool.js";
import { onCompacted, onIdle } from "./hooks/compact.js";

const plugin: Plugin = async (ctx) => ({
  "session.created": onSessionCreated(ctx),
  "session.compacted": onCompacted(ctx),
  "session.idle": onIdle(ctx),
  "tool.execute.before": onToolBefore(ctx),
  "tool.execute.after": onToolAfter(ctx),
});

export default plugin;
```

### Event mapping

| ll hook (Claude Code) | OpenCode event | Handler file |
|---|---|---|
| `SessionStart` | `session.created` | `hooks/session.ts` |
| `PreToolUse` (Write/Edit) | `tool.execute.before` | `hooks/tool.ts` |
| `PostToolUse` | `tool.execute.after` | `hooks/tool.ts` |
| `PreCompact` | `session.compacted` | `hooks/compact.ts` |
| `Stop` | `session.idle` | `hooks/compact.ts` |
| `UserPromptSubmit` | `tui.prompt.append` | (no-op or minimal) |

### Runtime notes

- **Bun confirmed**: `PluginInput` includes `$: BunShell` — use `ctx.$` for shell execution
- **State files**: Write to `.opencode/ll-context-state.json`, `.opencode/ll-precompact-state.json`, `.opencode/ll-continue-prompt.md`
- **Config**: Load `.opencode/ll-config.json`, fall back to `.claude/ll-config.json`

### Handler implementation guidance

Port existing shell script logic to TypeScript:
- `hooks/session.ts` ← `hooks/scripts/session-start.sh` logic
- `hooks/tool.ts` ← `hooks/scripts/context-monitor.sh` + `hooks/scripts/check-duplicate-issue-id.sh`
- `hooks/compact.ts` ← `hooks/scripts/precompact-state.sh` + `hooks/scripts/session-cleanup.sh`

## Integration Map

### Files to Create
- `opencode-plugin/package.json`
- `opencode-plugin/index.ts`
- `opencode-plugin/hooks/session.ts`
- `opencode-plugin/hooks/tool.ts`
- `opencode-plugin/hooks/compact.ts`

### Files to Reference (for porting logic)
- `hooks/scripts/session-start.sh` — session start logic
- `hooks/scripts/context-monitor.sh` — token estimation + handoff trigger
- `hooks/scripts/check-duplicate-issue-id.sh` — duplicate ID check
- `hooks/scripts/precompact-state.sh` — precompact state save
- `hooks/scripts/session-cleanup.sh` — cleanup logic
- `hooks/scripts/lib/common.sh` — `ll_resolve_config()`, `ll_config_value()` helpers (port to TS)

## Impact

- **Priority**: P4 — Core deliverable for OpenCode parity
- **Effort**: Medium-Large — 6 new files; logic is translation from existing shell scripts, not new logic
- **Risk**: Medium — No existing JS/Bun infrastructure in repo; Bun version pinning and import resolution must be established first
- **Breaking Change**: No (additive new directory)

## Notes

**Prerequisites**: FEAT-960 should be complete before this (state paths need to be parameterized first, or the JS plugin must hardcode `.opencode/` for its own state — acceptable since the plugin is OpenCode-only).

**No existing JS test tooling in repo**: Establish Bun test setup (`bun test`) in this issue's scope. Even a smoke test that imports the plugin and verifies it exports a valid Plugin function provides meaningful coverage.

**SDK versions**: `@opencode-ai/plugin` v1.2.27, `@opencode-ai/sdk` + `zod` as dependencies (confirmed on npm).

## Blocks

- FEAT-962: OpenCode ll:init Support, Tests, and Docs (init skill should reference implemented plugin)

## Verification Notes

**Verdict**: VALID — No `opencode-plugin/` directory exists. Blocker FEAT-960 still open (shell hooks path abstraction unimplemented). The `@opencode-ai/plugin` v1.2.27 version reference should be confirmed against npm before implementation.

— Verified 2026-04-11

## Session Log
- `/ll:verify-issues` - 2026-04-11T23:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:issue-size-review` - 2026-04-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e591ecf6-7232-42fc-b4c4-903ec2858064.jsonl`

---

**Open** | Created: 2026-04-05 | Priority: P4
