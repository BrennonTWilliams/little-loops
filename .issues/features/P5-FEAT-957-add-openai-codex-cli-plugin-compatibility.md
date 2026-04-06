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
- Probe `.codex/ll-config.json` first, fall back to `.ll/ll-config.json`

**State directory**: `${LL_STATE_DIR:-.ll}` mechanism (established by FEAT-769) used as-is; Codex init sets `LL_STATE_DIR=".codex"`.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**FEAT-769 status**: As of 2026-04-05, `P4-FEAT-769-add-opencode-plugin-compatibility.md` is **open and unimplemented**. No `opencode-plugin/` directory exists; `LL_STATE_DIR` env var is absent from all Python and shell files. FEAT-957 cannot begin until FEAT-769 ships.

**Current state directory**: Hook scripts have already been migrated from `.claude/` to `.ll/`. The default for `${LL_STATE_DIR}` should be `.ll`, not `.claude`.

**Files to Modify — Full List with Line References**

Shell config layer:
- `hooks/scripts/lib/common.sh:184-192` — `ll_resolve_config()`: add `.codex/` as first probe candidate; automatically propagates to `context-monitor.sh`, `check-duplicate-issue-id.sh`, and `user-prompt-check.sh` (all source this library)
- `hooks/scripts/session-start.sh:13,16,64-72` — **independent** (does NOT source `lib/common.sh`); must patch shell probe at line 16, embedded Python probe at lines 64-72, and state cleanup `rm -f .ll/ll-context-state.json` at line 13 separately
- `hooks/scripts/session-cleanup.sh:14,20` — **independent** (does NOT source `lib/common.sh`); own hardcoded `CONFIG_FILE=".ll/ll-config.json"` at line 20 and cleanup at line 14; patching `lib/common.sh` does NOT cover this file
- `hooks/scripts/context-monitor.sh:180,268,309` — three hardcoded `.ll/` paths NOT covered by `ll_resolve_config()`: `precompact_file` at line 180, cleanup `rm -f` at line 268, `HANDOFF_FILE` at line 309
- `hooks/scripts/precompact-state.sh:28,66` — `STATE_DIR=".ll"` at line 28 (change to `${LL_STATE_DIR:-.ll}`); `CONTINUE_PROMPT=".ll/ll-continue-prompt.md"` at line 66 is **not derived from `STATE_DIR`** — needs a separate patch

Python config layer:
- `scripts/little_loops/config/core.py:75,87-93` — `CONFIG_DIR = ".ll"` at line 75; `_load_config()` at lines 87-93 builds a single path with no fallback; extend to probe `.codex/ll-config.json` before `.ll/ll-config.json`

Python CLI injection sites for `LL_STATE_DIR` (follow `LL_HANDOFF_THRESHOLD` pattern at `auto.py:74-82`):
- `scripts/little_loops/cli/auto.py:77` — add `os.environ["LL_STATE_DIR"] = ".codex"` alongside `LL_HANDOFF_THRESHOLD`
- `scripts/little_loops/cli/parallel.py:173` — same pattern
- `scripts/little_loops/cli/loop/run.py:74` — same pattern
- `scripts/little_loops/cli/sprint/run.py:103` — same pattern

Additional Python paths (not in original Integration Map):
- `scripts/little_loops/subprocess_utils.py:32` — module-level `CONTINUATION_PROMPT_PATH = Path(".ll/ll-continue-prompt.md")`; needs `.codex/` probe

Init skill:
- `skills/init/SKILL.md:43-60` — flag-parsing block has no `--opencode` or `--codex` flags yet; add Codex detection (probe `codex.json` or `which codex`) following the settings detection pattern at lines 406-419

**Test Files**
- `scripts/tests/test_config.py:458-481` — add `test_load_config_codex_path()` modeled after `test_load_config_from_file` (line 458); add `test_load_config_fallback_to_ll()` modeled after `test_load_config_without_file` (line 473)
- `scripts/tests/conftest.py:55-62` — add `codex_project_dir` fixture creating `.codex/` alongside existing `temp_project_dir` (creates `.ll/`)
- `scripts/tests/test_hooks_integration.py:22-36,247-262` — add hook config fixture variant placing config at `.codex/ll-config.json`; use env var injection pattern at lines 247-262 for `LL_STATE_DIR=".codex"`

**OpenCode Reference Pattern** (for `codex-plugin/` structure):
- `opencode.json` plugin key: `{ "plugin": ["@ll/opencode-plugin"] }` — Codex equivalent format is unknown (see Research Required above)
- Claude Code hooks use `$CLAUDE_PLUGIN_ROOT` in every command; OpenCode and Codex JS plugins handle event wiring internally via the plugin SDK instead

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file references per step:_

- **Step 1** — External research only; no codebase anchor. OpenCode reference in `P4-FEAT-769-add-opencode-plugin-compatibility.md:76-84` for event name mapping table.
- **Step 2** — Model `codex-plugin/` directory structure after FEAT-769's planned `opencode-plugin/` layout; at minimum: `package.json`, `index.ts`, `hooks/session.ts`, `hooks/tool.ts`, `hooks/compact.ts`
- **Step 3** — Mirrors `hooks/scripts/session-start.sh` logic; includes config load at `session-start.sh:16,64-72` and local overrides from `.ll/ll.local.md` (`session-start.sh:75`)
- **Step 4** — Mirrors `hooks/scripts/context-monitor.sh`; key paths: `STATE_FILE` at line 29, `HANDOFF_FILE` at line 309, threshold read via `LL_HANDOFF_THRESHOLD` at line 26
- **Step 5** — Mirrors `hooks/scripts/check-duplicate-issue-id.sh`; config read via `ll_resolve_config()` at `lib/common.sh:184`
- **Step 6** — Mirrors `hooks/scripts/precompact-state.sh:28-30,66` and `hooks/scripts/session-cleanup.sh:14,20`
- **Step 7** — Modify `skills/init/SKILL.md:43-60` (flag-parsing); add detection probe following pattern at lines 406-419; write `codex.json` plugin registration (format TBD from step 1 research)
- **Step 8** — Patch `scripts/little_loops/config/core.py:75,87-93`; patch `hooks/scripts/lib/common.sh:184-192`; also patch independent scripts `session-start.sh:16,64`, `session-cleanup.sh:20`; patch `precompact-state.sh:28,66` and `context-monitor.sh:180,268,309`; inject `LL_STATE_DIR` at `cli/auto.py:77`, `cli/parallel.py:173`, `cli/loop/run.py:74`, `cli/sprint/run.py:103`; patch `subprocess_utils.py:32`
- **Step 9** — Add tests at `scripts/tests/test_config.py:458` (codex path) and `test_hooks_integration.py:22` (codex fixture); add `codex_project_dir` fixture to `scripts/tests/conftest.py:55`

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
- `/ll:refine-issue` - 2026-04-06T02:33:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c273f16-a946-4cde-a3ce-1eb1a83742ae.jsonl`
- `/ll:format-issue` - 2026-04-05T23:24:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80483a00-b614-43e6-8ba2-461cc77fadae.jsonl`
- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d4087be-1201-4786-a118-8eb18c18f952.jsonl`

---

**Open** | Created: 2026-04-05 | Priority: P5
