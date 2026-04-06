---
id: FEAT-957
type: FEAT
priority: P5
status: open
discovered_date: 2026-04-05
discovered_by: capture-issue
---

# FEAT-957: Add OpenAI Codex CLI Plugin Compatibility

## Summary

OpenAI Codex CLI is a terminal AI coding agent from OpenAI. This issue tracks adding Codex CLI plugin support so that ll's full feature set — commands, skills, and session hooks — works in Codex CLI projects, following the same pattern established by FEAT-769 (OpenCode compatibility).

## Current Behavior

little-loops has no Codex CLI plugin layer. Commands and skills may work via any `.claude/` path fallback Codex supports, but session hooks (context monitoring, duplicate ID checks, config loading) do not fire because there is no Codex plugin wiring them to lifecycle events.

## Expected Behavior

A user running Codex CLI can install little-loops and get all commands, skills, and session hooks working at parity with the Claude Code experience.

## Acceptance Criteria

- All `/ll:*` slash commands work in a Codex CLI project without modification
- All skills work in a Codex CLI project without modification
- Session lifecycle hooks fire via a Codex CLI plugin (config loading, duplicate ID check, context monitoring, compact/cleanup)
- Config resolves from `.codex/ll-config.json` when present, falls back to `.claude/ll-config.json`
- `ll:init --codex` detects Codex CLI presence and offers to register the plugin
- Existing Claude Code and OpenCode behavior is unchanged (no regressions)

## Motivation

Codex CLI gives users access to OpenAI models in the terminal. Supporting it expands ll's reach beyond Anthropic and OpenCode users. The content layer (commands, skills) is already platform-agnostic — only the hook execution layer needs a plugin bridge.

## Use Case

A developer uses Codex CLI with GPT-4o. They discover little-loops and want its issue management and loop automation. Commands and skills work, but context monitoring and duplicate ID checks don't fire because there's no plugin wiring. With this feature, `ll:init --codex` sets up the plugin and gives them full parity.

## Proposed Solution

Research the Codex CLI plugin/extension API (SDK name, runtime, event names) and create a plugin in a new `codex-plugin/` directory that bridges ll's hook logic to Codex events — mirroring the OpenCode plugin structure from FEAT-769.

**New directory**: `codex-plugin/`
```
codex-plugin/
├── package.json
├── index.ts              # Main plugin entry point
└── hooks/
    ├── session.ts        # session-start equivalent
    ├── tool.ts           # pre/post-tool equivalent
    └── compact.ts        # pre-compact equivalent
```

**Config path resolution** (extend Python layer already updated by FEAT-769):
- Probe `.codex/ll-config.json` first, fall back to `.claude/ll-config.json`

**State directory**: `${LL_STATE_DIR:-.claude}` mechanism (established by FEAT-769) used as-is; Codex init sets `LL_STATE_DIR=".codex"`.

## API/Interface

N/A - No public Python API changes.

New CLI flag exposed via `ll:init`:
```
ll:init --codex    # Detect Codex CLI and register codex-plugin/
```

New environment variable (established by FEAT-769, reused here):
```
LL_STATE_DIR=".codex"   # Set by codex init to redirect state files
```

Plugin entry point (internal, not a public API):
```typescript
// codex-plugin/index.ts
export default {
  name: "little-loops",
  // hooks wired to Codex CLI lifecycle events
}
```

## Integration Map

### Prerequisites
- **FEAT-769** must be completed first — provides `LL_STATE_DIR` shell mechanism, Python config fallback chain, and `ll:init` OpenCode scaffolding to model after.

### Files to Modify (after FEAT-769)
- `scripts/little_loops/config/core.py` — extend fallback chain to include `.codex/ll-config.json`
- `hooks/scripts/lib/common.sh:ll_resolve_config()` — extend to probe `.codex/` as additional candidate
- `skills/init/SKILL.md` — add `--codex` flag handling alongside `--opencode`

### New Files
- `codex-plugin/package.json`
- `codex-plugin/index.ts` (and sub-modules)

### Research Required
- Codex CLI plugin SDK: package name, runtime (Node.js/Bun/Deno), event names
- Codex CLI config file location (equivalent of `opencode.json`)
- Plugin registration mechanism (equivalent of `"plugin"` key in `opencode.json`)
- Detection signal for `ll:init` (binary name, env var, config file presence)

## Implementation Steps

1. **Research Codex CLI plugin API** — identify SDK package, runtime, event names, and registration format; update this issue with findings before implementation
2. **Scaffold `codex-plugin/`** — create `package.json` and no-op `index.ts`; establish runtime tooling (parallel to FEAT-769 step 5)
3. **Port session-start logic** — `session.created` equivalent: load config, apply local overrides
4. **Port context monitor** — post-tool handler: token estimation and handoff trigger
5. **Port duplicate ID check** — pre-tool handler for Write/Edit on `.issues/` paths
6. **Port compact/cleanup hooks** — compact and idle/stop handlers
7. **Extend `ll:init`** — add `--codex` detection and plugin registration alongside `--opencode`
8. **Extend config fallback chain** — add `.codex/` probe to `config/core.py` and `lib/common.sh` (if not already done by FEAT-769)
9. **Tests and docs** — add `test_config.py` Codex path tests; update `docs/ARCHITECTURE.md`

## Impact

- **Priority**: P5 — Speculative audience expansion; Codex plugin API unverified
- **Effort**: Low-Medium — FEAT-769 does the hard work; this is a parallel translation once Codex plugin API is understood
- **Risk**: Low — Additive change, no modifications to Claude Code or OpenCode paths
- **Breaking Change**: No
- **Depends on**: FEAT-769

## Related Key Documentation

_No documents linked._

## Labels

`feature`, `codex`, `compatibility`, `hooks`

## Session Log
- `/ll:format-issue` - 2026-04-05T23:24:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80483a00-b614-43e6-8ba2-461cc77fadae.jsonl`
- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d4087be-1201-4786-a118-8eb18c18f952.jsonl`

---

**Open** | Created: 2026-04-05 | Priority: P5
