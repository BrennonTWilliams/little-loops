---
id: FEAT-769
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-15
discovered_by: capture-issue
---

# FEAT-769: Add OpenCode Plugin Compatibility

## Summary

little-loops currently targets Claude Code exclusively. OpenCode (github.com/sst/opencode) is the leading open-source terminal AI coding agent with 75+ provider support, and it shares enough architectural conventions with Claude Code that a compatibility layer is feasible. This issue tracks adding OpenCode support via an OpenCode JS/TS plugin shim (Option B), enabling ll's full feature set — commands, skills, hooks, and config — to work in OpenCode projects.

## Current Behavior

little-loops is hard-coupled to Claude Code in four areas:
1. **Plugin manifest**: `.claude-plugin/plugin.json` — Claude Code-specific format
2. **Hooks**: `hooks/hooks.json` + shell scripts via `$CLAUDE_PLUGIN_ROOT` — no equivalent in OpenCode
3. **Config path**: `.claude/ll-config.json` — hardcoded in Python and hook scripts
4. **Log parsing**: `~/.claude/projects/` path in `ll-messages` / `ll-workflows`

Commands, skills, agents, and all Python CLI tools are already platform-agnostic. OpenCode natively falls back to `.claude/` paths, so those components work in OpenCode today with zero changes.

## Expected Behavior

A user running OpenCode can install little-loops and get:
- All slash commands (`/ll:*`) working
- All skills working
- Session lifecycle hooks (context monitoring, duplicate ID checks, config loading) active via an OpenCode JS/TS plugin
- Config read from `.opencode/ll-config.json` with fallback to `.claude/ll-config.json`
- `ll:init` sets up both Claude Code and OpenCode config paths

## Motivation

OpenCode's provider freedom (Gemini, GPT-4, local Ollama, etc.) makes it attractive to users who can't or won't use Claude Code. Supporting OpenCode expands ll's audience to all terminal AI agent users, not just Anthropic customers. The content layer is already free — only the hook execution layer needs a bridge, making the effort-to-value ratio high.

## Use Case

A developer uses OpenCode with Gemini 2.0 Flash as their primary AI coding agent. They discover little-loops and want its issue management, sprint, and loop automation features. Today they get commands and skills (via OpenCode's `.claude/` fallback) but no session hooks — context monitoring doesn't fire, duplicate ID checks are skipped, and config loading doesn't run. With this feature, they run `ll:init --opencode` and get full parity.

## Proposed Solution

### Recommended: Option B — OpenCode Plugin Shim

Create an OpenCode JS/TS plugin in a new `opencode-plugin/` directory that bridges ll's hook logic to OpenCode's event API. The existing shell scripts remain untouched for Claude Code users.

**New directory**: `opencode-plugin/`
```
opencode-plugin/
├── package.json          # { "name": "@ll/opencode-plugin", "type": "module" }
├── index.ts              # Main plugin entry point
└── hooks/
    ├── session.ts        # session.created → session-start logic
    ├── tool.ts           # tool.execute.before/after → duplicate-id + context monitor
    └── compact.ts        # session.compacted → precompact-state logic
```

**Plugin event mapping**:

| ll hook (Claude Code) | OpenCode event | Notes |
|---|---|---|
| `SessionStart` | `session.created` | Load config, apply local overrides |
| `UserPromptSubmit` | `tui.prompt.append` | Input validation (if needed) |
| `PreToolUse` (Write/Edit) | `tool.execute.before` | Duplicate issue ID check |
| `PostToolUse` | `tool.execute.after` | Context monitoring, token estimation |
| `PreCompact` | `session.compacted` | Preserve task state |
| `Stop` | `session.idle` | Cleanup state files |

**Config path resolution** (in both Python and the JS plugin):
```python
def find_config() -> Path:
    for candidate in [Path(".opencode/ll-config.json"), Path(".claude/ll-config.json")]:
        if candidate.exists():
            return candidate
    return Path(".claude/ll-config.json")  # default (create on init)
```

**Registration** in user's `opencode.json`:
```json
{
  "plugins": ["./opencode-plugin/index.ts"]
}
```

`ll:init` would offer to add this automatically when OpenCode is detected.

### Alternative: Option C — Full Dual-Target Restructure

Formalize a platform abstraction layer: a `PlatformAdapter` interface with `ClaudeCodeAdapter` and `OpenCodeAdapter` implementations, a shared Python core, and unified config schema. Better long-term architecture but ~3x the effort of Option B. Appropriate if OpenCode adoption is significant and Option B's shim shows maintenance friction.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/core.py` — add `.opencode/` path fallback
- `hooks/scripts/session-start.sh` — document OpenCode non-support (Claude Code only)
- `skills/init/SKILL.md` — add `--opencode` flag handling
- `commands/init.md` — same

### Dependent Files (Callers/Importers)
- `scripts/little_loops/user_messages.py` — log path parsing (future: Option C)
- All hook scripts that reference `${CLAUDE_PLUGIN_ROOT}` — Claude Code only, no change needed

### Similar Patterns
- N/A — no existing multi-platform plugin support to match

### Tests
- `scripts/tests/` — add tests for config path fallback logic
- Integration test: OpenCode plugin loads and registers events without error

### Documentation
- `docs/ARCHITECTURE.md` — add OpenCode compatibility section
- `CONTRIBUTING.md` — add OpenCode setup instructions
- `README.md` (if exists) — note OpenCode support

### Configuration
- New: `opencode-plugin/package.json`
- New: `opencode-plugin/index.ts` (and sub-modules)
- `config-schema.json` — no changes needed (schema is platform-agnostic)

## Implementation Steps

1. **Config path abstraction** — Update `config/core.py` to check `.opencode/ll-config.json` before `.claude/ll-config.json`; update hook scripts to do the same
2. **OpenCode plugin scaffold** — Create `opencode-plugin/` with `package.json` and `index.ts` that imports `@opencode-ai/plugin` types and exports a no-op plugin (validates the plumbing)
3. **Port session-start logic** — Implement `session.created` handler: load config, apply `.opencode/ll.local.md` overrides via Bun shell
4. **Port context monitor** — Implement `tool.execute.after` handler: replicate token estimation and handoff trigger from `context-monitor.sh`
5. **Port duplicate ID check** — Implement `tool.execute.before` handler for Write/Edit tools on `.issues/` paths
6. **Port compact/cleanup hooks** — Implement `session.compacted` and `session.idle` handlers
7. **Update `ll:init`** — Detect OpenCode presence (`opencode.json` or `opencode` binary in PATH), offer to register the plugin
8. **Document and test** — Add architecture docs, integration test, update CONTRIBUTING.md

## Impact

- **Priority**: P3 — High value for audience expansion, not blocking any current users
- **Effort**: Medium — Hook logic is already written in bash; porting to JS is translation work. Config path abstraction is small. No architectural changes to the Python core.
- **Risk**: Low — Additive change, no modifications to Claude Code path. OpenCode plugin can be opt-in.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `opencode`, `compatibility`, `hooks`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd2aa170-6761-45f4-b494-2ab248f32aea.jsonl`

---

**Open** | Created: 2026-03-15 | Priority: P3
