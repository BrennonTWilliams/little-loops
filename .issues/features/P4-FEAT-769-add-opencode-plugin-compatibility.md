---
id: FEAT-769
type: FEAT
priority: P4
status: open
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 82
outcome_confidence: 36
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

## Acceptance Criteria

- All `/ll:*` slash commands work in an OpenCode project without modification
- All skills work in an OpenCode project without modification
- `session.created` handler loads config and applies `.opencode/ll.local.md` overrides
- `tool.execute.before` handler fires duplicate issue ID check on Write/Edit operations targeting `.issues/` paths
- `tool.execute.after` handler runs context monitoring (token estimation and handoff trigger)
- `session.compacted` and `session.idle` handlers preserve/clean task state correctly
- Config resolves from `.opencode/ll-config.json` when present, falls back to `.claude/ll-config.json`
- `ll:init --opencode` detects OpenCode (via `opencode.json` or `opencode` in PATH) and offers to add the plugin to `opencode.json`
- Existing Claude Code behavior is unchanged (no regressions to the Claude Code path)
- OpenCode plugin loads and registers all event handlers without runtime errors

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

**Registration** in user's `opencode.json` (key is `"plugin"` singular, not `"plugins"`):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@ll/opencode-plugin"]
}
```

The `opencode-plugin/package.json` sets `"name": "@ll/opencode-plugin"` so after `npm install ./opencode-plugin` the package is resolvable by name. `ll:init` would offer to add this automatically when OpenCode is detected.

### Alternative: Option C — Full Dual-Target Restructure

Formalize a platform abstraction layer: a `PlatformAdapter` interface with `ClaudeCodeAdapter` and `OpenCodeAdapter` implementations, a shared Python core, and unified config schema. Better long-term architecture but ~3x the effort of Option B. Appropriate if OpenCode adoption is significant and Option B's shim shows maintenance friction.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/core.py` — add `.opencode/` path fallback
- `hooks/scripts/session-start.sh` — document OpenCode non-support (Claude Code only)
- `skills/init/SKILL.md` — add `--opencode` flag handling

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Complete file list (research-verified, with exact locations):**

Config / Python layer:
- `scripts/little_loops/config/core.py:74-75` — `CONFIG_DIR = ".claude"` class constant; `_load_config()` at line 89 builds `project_root / CONFIG_DIR / CONFIG_FILENAME` — add `.opencode` fallback here
- `scripts/little_loops/config/features.py:193,206` — `state_file: str = ".claude/ll-sync-state.json"` hardcoded as both the field default and the `data.get()` fallback in `GithubSyncConfig`; update default to probe `.opencode/ll-sync-state.json` first
- `scripts/little_loops/config/automation.py:54,83` — `worktree_copy_files` default includes `.claude/settings.local.json"`; for OpenCode users this file doesn't exist — either expand the default to include `.opencode/` settings or document the difference in `ll:init --opencode`
- `scripts/little_loops/user_messages.py:338` — `claude_projects = Path.home() / ".claude" / "projects"` (hardcoded); needs OpenCode variant (`~/.opencode/projects/` or equivalent)
- `scripts/little_loops/user_messages.py:703` — `output_dir = Path.cwd() / ".claude"` default output dir (hardcoded)

Shell hooks layer — **KEY INSIGHT**: `hooks/scripts/lib/common.sh:ll_resolve_config()` at lines 186–190 is the canonical config resolver used by all hook scripts. Patching this one function propagates to `check-duplicate-issue-id.sh`, `context-monitor.sh`, `precompact-state.sh`, and `user-prompt-check.sh` at once:
- `hooks/scripts/lib/common.sh:186-190` — `ll_resolve_config()` hardcodes `.claude/ll-config.json`; add `.opencode/ll-config.json` as first probe
- `hooks/scripts/session-start.sh:16` — shell layer hardcodes `CONFIG_FILE=".claude/ll-config.json"`; embedded Python at lines 65–72 mirrors same two-path check (both shell and Python need the `.opencode/` prefix)
- `hooks/scripts/session-start.sh:13` — deletes `.claude/ll-context-state.json` by hardcoded path
- `hooks/scripts/session-cleanup.sh:14` — deletes `.claude/.ll-lock` and `.claude/ll-context-state.json`; line 20 hardcodes `CONFIG_FILE=".claude/ll-config.json"`
- `hooks/scripts/context-monitor.sh:181` — `precompact_file=".claude/ll-precompact-state.json"` hardcoded; line 238 also hardcodes `.claude/ll-precompact-state.json`; line 309 hardcodes `.claude/ll-continue-prompt.md`
- `hooks/scripts/precompact-state.sh:28-29` — `STATE_DIR=".claude"` constant; line 66 hardcodes `CONTINUE_PROMPT=".claude/ll-continue-prompt.md"`
- `hooks/scripts/check-duplicate-issue-id.sh:45` — `CONFIG_FILE=".claude/ll-config.json"` (consumed by `ll_resolve_config()` — covered if `lib/common.sh` is patched)

**`$CLAUDE_PLUGIN_ROOT` accuracy correction**: The issue states this variable is used by `session-start.sh` — research shows this is incorrect. `$CLAUDE_PLUGIN_ROOT` is used in two places only: `hooks/hooks.json` (lines 10, 22, 35, 48, 60, 73 — all 6 hook commands) and `hooks/scripts/user-prompt-check.sh:81` (`HOOK_PROMPT_FILE="${CLAUDE_PLUGIN_ROOT:-$SCRIPT_DIR/..}/prompts/optimize-prompt-hook.md"` with a self-relative fallback already in place). `session-start.sh` does not reference `$CLAUDE_PLUGIN_ROOT`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/user_messages.py` — log path parsing needs OpenCode path support (lines 338, 703); this IS in scope for Option B (not just future Option C)
- `hooks/hooks.json` — all 6 hook `command` values use `${CLAUDE_PLUGIN_ROOT}` prefix; no change needed for Claude Code path but this variable has no OpenCode equivalent (the JS plugin handles event registration instead)

### Similar Patterns
- `hooks/scripts/lib/common.sh:ll_resolve_config()` — existing two-location fallback pattern (`.claude/` → bare root); extend to three locations (`.opencode/` → `.claude/` → bare root)
- `hooks/scripts/session-start.sh:15-18` — shell + embedded Python two-path probe; model for adding `.opencode/` as first candidate
- `scripts/tests/conftest.py:55-121` — `temp_project_dir` fixture creates `.claude/` dir; replicate for `.opencode/` in new tests
- `scripts/tests/test_config.py` — config-absent default test pattern at lines 373–381; env var test pattern using `patch.dict`

### Tests
- `scripts/tests/test_config.py` — add `test_load_config_opencode_path()` and `test_load_config_fallback_to_claude()` following existing pattern at lines 373–381
- `scripts/tests/conftest.py` — add `opencode_project_dir` fixture alongside `temp_project_dir` (creates `.opencode/` dir)
- `scripts/tests/test_hooks_integration.py` — existing hook integration tests; add OpenCode config path coverage
- Integration test: OpenCode JS plugin loads and registers all 6 event handlers without runtime errors (requires JS test runner to be set up first)

### Documentation
- `docs/ARCHITECTURE.md` — add OpenCode compatibility section
- `CONTRIBUTING.md` — add OpenCode setup instructions
- `README.md` (if exists) — note OpenCode support
- `docs/reference/CONFIGURATION.md` — config system reference; note `.opencode/` path resolution

### Additional Files (Run 3)

_Added by `/ll:refine-issue` run 3 — based on codebase analysis:_

- `scripts/little_loops/state.py` — **VERIFIED CLEAN**: zero `.claude/` hardcodes. `StateManager.__init__` accepts `state_file: Path` as an injected parameter; never constructs a path itself. State file defaults are in `config/automation.py:19` (`.auto-manage-state.json`) and resolve via `config/core.py:247` to project root — NOT inside `.claude/`. No changes needed in `state.py`.
- `scripts/tests/test_user_messages.py` — add OpenCode log-path tests alongside Claude Code path tests
- `scripts/tests/test_state.py` — **VERIFIED CLEAN**: uses `tmp_path`-based fixtures only; no `.claude/` strings anywhere. No OpenCode variants needed.
- `scripts/tests/test_hooks_integration.py:33,104` — two fixtures create `.claude/ll-config.json` inside `tmp_path` because tests invoke `context-monitor.sh` as a subprocess (which reads config from `.claude/ll-config.json` in its working dir); add `.opencode/` variant fixture paths when adding OpenCode config path tests here

### Implementation Accuracy Corrections (Run 3)

_Added by `/ll:refine-issue` run 3 — correcting prior research:_

- **`session-cleanup.sh` does NOT use `ll_resolve_config()`**: Unlike `context-monitor.sh` and `user-prompt-check.sh`, `session-cleanup.sh:20` has its own independent hardcoded `CONFIG_FILE=".claude/ll-config.json"` and does not source `lib/common.sh`. Patching `ll_resolve_config()` will NOT fix `session-cleanup.sh` — it requires a separate, independent patch.
- **`context_monitor.state_file` is already semi-parameterized**: `context-monitor.sh:29` reads `STATE_FILE=$(ll_config_value "context_monitor.state_file" ".claude/ll-context-state.json")`. If the OpenCode config sets `context_monitor.state_file = ".opencode/ll-context-state.json"`, the `STATE_FILE` variable will pick it up automatically. However, the three remaining hardcoded paths (`precompact_file` at line 181, the cleanup `rm -f` at line 238, and `HANDOFF_FILE` at line 309) are NOT parameterized and must be patched directly.
- **`ll:init` `.gitignore` entries need `.opencode/` variants**: `skills/init/SKILL.md:313-319` writes `.claude/ll-context-state.json`, `.claude/ll-sync-state.json` etc. to `.gitignore`. The `--opencode` path should also add `.opencode/ll-context-state.json`, `.opencode/ll-sync-state.json`, etc.

### Configuration
- New: `opencode-plugin/package.json`
- New: `opencode-plugin/index.ts` (and sub-modules)
- `config-schema.json` — no changes needed (schema is platform-agnostic)

### Codebase Research Findings (Run 5 — OpenCode API Verification)

_Added by `/ll:refine-issue` — based on web research (opencode.ai/docs/plugins, npm, GitHub sst/opencode):_

**OpenCode plugin SDK confirmed:**
- `@opencode-ai/plugin` v1.2.27 — published on npm, MIT license; `@opencode-ai/sdk` + `zod` as dependencies
- Runtime: **Bun** (confirmed). `PluginInput` includes `$: BunShell` — use `ctx.$` for shell execution inside handlers
- Plugin function signature: `type Plugin = (input: PluginInput) => Promise<Hooks>`
- `PluginInput` fields: `client`, `project`, `directory`, `worktree`, `serverUrl`, `$` (BunShell)

**All 6 event names verified against official docs (opencode.ai/docs/plugins):**
- `session.created` ✓ | `session.compacted` ✓ | `session.idle` ✓
- `tool.execute.before` ✓ | `tool.execute.after` ✓ | `tui.prompt.append` ✓

**`LL_STATE_DIR` mechanism design (concrete model exists):**
The `LL_HANDOFF_THRESHOLD` / `LL_CONTEXT_LIMIT` pattern (`auto.py:71,76`) is the exact model: Python CLIs set `os.environ["LL_STATE_DIR"] = ".opencode"` before spawning Claude processes; shell scripts read `${LL_STATE_DIR:-.claude}`. `precompact-state.sh:28` already has `STATE_DIR=".claude"` as the single derivation point — change to `STATE_DIR="${LL_STATE_DIR:-.claude}"` to cover all 3 derived paths in that file at once. Apply the same `${LL_STATE_DIR:-.claude}` substitution to `context-monitor.sh:181,238,309`, `session-cleanup.sh:14,20`, and `session-start.sh:13`. The 4 Python CLIs that need `os.environ["LL_STATE_DIR"]`: `cli/auto.py:71`, `cli/parallel.py:165`, `cli/loop/run.py:70`, `cli/sprint/run.py:103` (mirroring existing `LL_HANDOFF_THRESHOLD` injection points). The JS plugin writes state files to `.opencode/` directly — no env var needed for the JS side.

**New scope gap — `skills/init/SKILL.md` gitignore block (lines 313-319) is missing 2 entries:**
- `.claude/ll-precompact-state.json` (written by `precompact-state.sh`)
- `.claude/ll-continue-prompt.md` (written by `context-monitor.sh`)
Step 10 must add these missing Claude Code entries AND add all 6 `.opencode/` equivalents.

## Implementation Steps

1. **Config path abstraction (Python)** — Update `config/core.py:75` to change `CONFIG_DIR = ".claude"` to a priority-ordered search: try `.opencode/ll-config.json` first, fall back to `.claude/ll-config.json`; review `config/features.py` and `config/automation.py` for additional `.claude/` hardcodes; write tests in `scripts/tests/test_config.py` following the `test_load_config_without_file` pattern at line 373
2. **Config path abstraction (Shell)** — Update `hooks/scripts/lib/common.sh:ll_resolve_config()` at lines 186–190 to probe `.opencode/ll-config.json` first (propagates to `context-monitor.sh` and `user-prompt-check.sh` automatically); also update `session-start.sh:16` (shell) and `session-start.sh:65-72` (embedded Python); **separately** patch `session-cleanup.sh:20` which has its own independent hardcoded `CONFIG_FILE=".claude/ll-config.json"` and does NOT source `lib/common.sh` — this script needs its own independent fix
3. **State file paths (Shell + Python CLIs)** — Replace hardcoded `.claude/` state paths with `${LL_STATE_DIR:-.claude}`: change `precompact-state.sh:28` from `STATE_DIR=".claude"` to `STATE_DIR="${LL_STATE_DIR:-.claude}"` (covers all 3 derived paths in that file); apply same to `context-monitor.sh:181,238,309`, `session-cleanup.sh:14,20`, and `session-start.sh:13`; add `os.environ["LL_STATE_DIR"] = ".opencode"` to 4 Python CLI entry points (`cli/auto.py:71`, `cli/parallel.py:165`, `cli/loop/run.py:70`, `cli/sprint/run.py:103`) when OpenCode context detected — mirrors existing `LL_HANDOFF_THRESHOLD` injection pattern at those same lines; also update `subprocess_utils.py:28` (`CONTINUATION_PROMPT_PATH`) to probe `.opencode/ll-continue-prompt.md` first
4. **user_messages.py log path** — Update `user_messages.py:338` (`Path.home() / ".claude" / "projects"`) and `user_messages.py:703` (`Path.cwd() / ".claude"`) to probe OpenCode log path when Claude Code path doesn't exist; follow `get_project_folder()` pattern
5. **OpenCode plugin scaffold** — Create `opencode-plugin/` with `package.json` (`"name": "@ll/opencode-plugin"`) and `index.ts` that imports `Plugin` from `@opencode-ai/plugin` and exports a no-op handler; **Bun runtime confirmed** — `ctx.$` is the `BunShell` instance, use `ctx.$.shell(["cmd", "arg"])` syntax in later steps (not `Bun.shell` global)
6. **Port session-start logic** — Implement `session.created` handler: load config following `session-start.sh` logic; apply `.opencode/ll.local.md` overrides; confirm shell execution API based on step 5 findings
7. **Port context monitor** — Implement `tool.execute.after` handler: replicate token estimation and handoff trigger from `context-monitor.sh` (key state files: `.opencode/ll-context-state.json`, `.opencode/ll-continue-prompt.md`)
8. **Port duplicate ID check** — Implement `tool.execute.before` handler for Write/Edit tools on `.issues/` paths, replicating `check-duplicate-issue-id.sh` logic
9. **Port compact/cleanup hooks** — Implement `session.compacted` and `session.idle` handlers (key state file: `.opencode/ll-precompact-state.json`)
10. **Update `ll:init` skill** — In `skills/init/SKILL.md`: detect OpenCode presence via `opencode.json` file or `opencode` binary in PATH; offer to register `@ll/opencode-plugin` using `"plugin"` key (singular) in `opencode.json`; create `.opencode/ll-config.json` if absent; fix missing gitignore entries at lines 313-319 — add `.claude/ll-precompact-state.json` and `.claude/ll-continue-prompt.md` (currently absent), then add all 6 `.opencode/` variants for OpenCode users
11. **Document and test** — Add `test_config.py` OpenCode path tests; update `docs/ARCHITECTURE.md`; update `CONTRIBUTING.md` with OpenCode setup

## Impact

- **Priority**: P4 — High value for audience expansion, not blocking any current users
- **Effort**: Medium — Hook logic is already written in bash; porting to JS is translation work. Config path abstraction is small. No architectural changes to the Python core.
- **Risk**: Low — Additive change, no modifications to Claude Code path. OpenCode plugin can be opt-in.
- **Breaking Change**: No

## Verification Notes

_Verified: 2026-03-19 | Verdict: NEEDS_UPDATE_

- **VALID**: `.claude-plugin/plugin.json` exists ✓
- **VALID**: `hooks/hooks.json` exists ✓
- **VALID**: `scripts/little_loops/config/core.py` exists; confirms `CONFIG_DIR = ".claude"` and hardcoded `.claude/ll-config.json` path ✓
- **VALID**: `skills/init/SKILL.md` exists ✓
- **VALID**: `scripts/little_loops/user_messages.py` exists; confirms `~/.claude/projects/` path references ✓
- **INACCURACY**: `commands/init.md` does not exist — `init` is implemented as a skill only (`skills/init/SKILL.md`). Remove `commands/init.md` from the Integration Map's "Files to Modify" list.
- **MINOR**: `$CLAUDE_PLUGIN_ROOT` is referenced in `hooks/scripts/user-prompt-check.sh`, not `session-start.sh`. The claim about shell scripts using `$CLAUDE_PLUGIN_ROOT` is correct overall but the specific association with session-start is inaccurate.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `opencode`, `compatibility`, `hooks`, `captured`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-03-20 (post-refine-issue run 5 — OpenCode API verified)_

**Readiness Score**: 82/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 36/100 → VERY LOW

### Readiness Scores

| Criterion | Score | Details |
|-----------|-------|---------|
| No duplicate implementations | 20/20 | `opencode-plugin/` doesn't exist; zero OpenCode code in Python/shell layer (grep-confirmed) |
| Architecture compliance | 12/20 | Python/shell changes fit existing patterns; JS/TS plugin needs new Bun tooling infrastructure — runtime confirmed, SDK confirmed, but no existing JS conventions in repo |
| Requirements clarity | 18/20 | 10 ACs, Option B chosen, `@opencode-ai/plugin` v1.2.27 verified, Bun confirmed, all 6 events verified, `opencode.json` key corrected; minor gap: OpenCode detection logic in Python CLIs undesigned |
| Issue well-specified | 17/20 | 11 concrete steps with file:line refs; LL_STATE_DIR mechanism designed (mirrors `LL_HANDOFF_THRESHOLD` at `auto.py:71`); minor gaps: JS test tooling setup, OpenCode detection heuristic |
| Dependencies satisfied | 15/20 | All Python/shell files verified; `@opencode-ai/plugin` SDK confirmed on npm; no Bun/JS tooling in repo (in-scope setup, not a pre-existing dep) |

### Outcome Confidence Scores

| Criterion | Score | Details |
|-----------|-------|---------|
| Complexity | 0/25 | 13+ existing files across 3 language subsystems (Python/Shell/TS) + 6 new JS files |
| Test coverage | 18/25 | `test_config.py`, `test_hooks_integration.py`, `test_user_messages.py` cover Python/shell (>50%); no JS test infra for 6 new plugin files |
| Ambiguity | 18/25 | Major unknowns resolved (Bun confirmed, events verified, LL_STATE_DIR designed, opencode.json key corrected); minor open: OpenCode detection logic in Python CLIs, Bun test tooling setup |
| Change surface | 0/25 | `config/core.py` imported by 60 files (114 occurrences, grep-confirmed); very wide blast radius |

### Concerns
- **No JS/Bun tooling in repo**: Step 5 scaffold must establish `package.json`, Bun version pinning, and import resolution before steps 6-9 can proceed; treat as prerequisite
- **Config blast radius**: `config/core.py` with 60 importers — path-fallback change is additive and backward-safe, but write `test_config.py` tests BEFORE modifying `core.py:74-75`
- **OpenCode detection logic undesigned**: Python CLIs need a reliable heuristic to set `os.environ["LL_STATE_DIR"] = ".opencode"` — detection signal (presence of `opencode.json`? `OPENCODE_SESSION` env var?) not yet specified
- **`session-cleanup.sh` independent probe**: Does NOT use `ll_resolve_config()` — has its own independent hardcoded `CONFIG_FILE=".claude/ll-config.json"` at line 20; patching `lib/common.sh` alone will miss this script

### Outcome Risk Factors
- **Complexity**: 13+ existing files + 6 new JS files across 3 subsystems — strict sequential execution required (step 5 scaffold → steps 6-9)
- **Change surface**: `config/core.py` changes affect 60 importers — additive pattern is safe, but test-first (`test_config.py`) is non-negotiable before modifying `core.py:74-75`
- **JS test gap**: No Bun test runner; 6 new plugin files have zero automated coverage at completion; establish Bun testing setup in step 11 as a scope item, not an afterthought

## Session Log
- `/ll:confidence-check` - 2026-03-20T00:39:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:refine-issue` - 2026-03-20T00:37:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:30:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:refine-issue` - 2026-03-20T00:29:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:25:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:refine-issue` - 2026-03-20T00:22:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:18:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:refine-issue` - 2026-03-20T00:15:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:13:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:refine-issue` - 2026-03-20T00:10:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:verify-issues` - 2026-03-20T00:03:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:format-issue` - 2026-03-20T00:02:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`

- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd2aa170-6761-45f4-b494-2ab248f32aea.jsonl`

---

**Open** | Created: 2026-03-15 | Priority: P4
