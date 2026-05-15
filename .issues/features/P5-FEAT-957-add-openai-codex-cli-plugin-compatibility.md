---
id: FEAT-957
type: FEAT
priority: P5
status: open
discovered_date: 2026-04-05
discovered_by: capture-issue
blocked_by: []
confidence_score: 95
outcome_confidence: 62
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
---

# FEAT-957: Add OpenAI Codex CLI Plugin Compatibility

## Summary

OpenAI Codex CLI is a terminal AI coding agent from OpenAI. This issue tracks adding Codex CLI plugin support so that ll's full feature set — commands, skills, and session hooks — works in Codex CLI projects, following the same pattern established by FEAT-769 (OpenCode compatibility).

## Current Behavior

little-loops has no Codex CLI plugin layer. Commands and skills may work via any `.claude/` path fallback Codex supports, but session hooks (context monitoring, duplicate ID checks, config loading) do not fire because there is no Codex plugin wiring them to lifecycle events.

## Expected Behavior

A user running Codex CLI can install little-loops and get all commands, skills, and session hooks working at parity with the Claude Code experience.

## Acceptance Criteria

- Session lifecycle hooks fire via `.codex/hooks.json` wiring (`session_start`, `pre_compact` intents) — verified by running Codex CLI in a fixture project and observing hook stderr/state mutations
- Config resolution: `resolve_config_path()` probes `.codex/ll-config.json` before the existing `.ll/ll-config.json` and root-level `ll-config.json` candidates when `LL_HOOK_HOST=codex` or `LL_STATE_DIR=.codex` is set. Cross-host default order, when no host env var is set, remains `.ll/ → root-level` (unchanged). Note: there is no `.claude/ll-config.json` probe today and this issue does NOT add one.
- `ll:init --codex` detects Codex CLI (binary `codex` on PATH OR `.codex/` directory present) and writes `.codex/hooks.json` from the adapter template; also prints a one-line warning that Codex will show a hook-trust dialog on next session start and that hooks remain inactive until trusted
- `resolve_config_path()` in `scripts/little_loops/config/core.py` is refactored from a hardcoded 2-candidate probe into a function that accepts (or iterates) an ordered candidate list, so FEAT-992 (Pi) adds a path entry rather than a code branch. The legacy `hooks/scripts/lib/common.sh:ll_resolve_config` is NOT touched (FEAT-1116 superseded it).
- The Codex event → ll hook-intent mapping table lives in `hooks/adapters/codex/README.md` and explicitly references the FEAT-1116 hook-intent contract (matching the OpenCode adapter's pattern). A top-level `docs/reference/PLUGIN_COMPAT.md` is NOT a deliverable of this issue; FEAT-992 reuses the per-adapter README pattern.
- A **host parity matrix** is added to `docs/reference/HOST_COMPATIBILITY.md` (new file) enumerating, per host: hook intents wired, slash-command discovery path, skill discovery path, orchestration CLI binary, and feature parity status. Codex column is filled in by this issue; OpenCode and Claude Code columns are backfilled from current state.
- Slash commands (`/ll:*`) and skills are **explicitly out of scope** for this issue — Codex reads `.codex/prompts/`, not `.claude/commands/`, and verification/symlink work is tracked separately (see Cross-Compat Scope Boundary note below). This issue does NOT claim commands/skills work in Codex; it only delivers the hook adapter layer.
- The orchestration layer (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`) is **explicitly out of scope** — those tools hard-code the `claude` binary and remain Claude-Code-only until [[FEAT-1462]] ships. This issue does NOT claim ll automation works under Codex.
- Existing Claude Code and OpenCode behavior is unchanged (no regressions): full test suite passes, `LL_HOOK_HOST` defaults to `claude-code`, and OpenCode adapter tests still skip-or-pass identically.

## Motivation

Codex CLI gives users access to OpenAI models in the terminal. Supporting it expands ll's reach beyond Anthropic and OpenCode users. The content layer (commands, skills) is already platform-agnostic — only the hook execution layer needs a plugin bridge.

## Use Case

A developer uses Codex CLI with GPT-4o. They discover little-loops and want its issue management and loop automation. Commands and skills work, but context monitoring and duplicate ID checks don't fire because there's no plugin wiring. With this feature, `ll:init --codex` sets up the plugin and gives them full parity.

## Proposed Solution

Follow the `hooks/adapters/<host>/` thin-stub pattern established by FEAT-1116 (hook-intent abstraction). Create `hooks/adapters/codex/` with a thin entry point that shells out to `python -m little_loops.hooks <intent>` for SessionStart and PreCompact — mirroring the OpenCode adapter at `hooks/adapters/opencode/`.

**Do NOT create `codex-plugin/`** — the TypeScript plugin directory structure described in earlier versions of this issue is superseded.

**CORRECTION — runtime** (added `/ll:refine-issue` 2026-05-14): Codex CLI is Rust-based and has **no TypeScript/Bun plugin SDK**. Entry points in `hooks/adapters/codex/` must be **Bash shell scripts**, not TypeScript files. Registration is via `.codex/hooks.json` written by `ll:init --codex` — not via a TypeScript plugin export. The reference pattern is `hooks/adapters/claude-code/` (Bash + hooks.json template), not `hooks/adapters/opencode/` (TypeScript/Bun plugin).

### Policy Decisions (added 2026-05-15)

**SessionStart matcher** — Use `"matcher": "startup"` on the SessionStart MatcherGroup. Rationale: ll's `session_start.handle()` performs config load and duplicate-ID emission keyed off a fresh session; firing on `resume` would re-emit identifiers for an already-running session, and firing on `clear` would re-run during in-session context resets. Restricting to `startup` matches the semantics ll's Claude Code adapter already relies on. Reconsider only if a future intent needs resume/clear-aware behavior.

**PostCompact intent** — Defer. ll has no PostCompact handler today; the existing `pre_compact` intent does all compact-time cleanup *before* compaction. Wiring PostCompact would require a new intent + handler with no concrete consumer. Track as a follow-up issue if a future feature needs post-compact cleanup; do not add a no-op handler in this issue.

**Other deferred events** (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `PermissionRequest`, `Stop`) — Out of scope. ll's Claude Code adapter consumes some of these (e.g. auto-prompt-optimizer on `UserPromptSubmit`); the parity gap is documented in `docs/reference/HOST_COMPATIBILITY.md` (new in this issue) rather than implemented here. Filing per-intent follow-up issues is the right path if user demand emerges.

**Trust-model UX** — `ll:init --codex` MUST print, after writing `.codex/hooks.json`:
> "Codex will show a hook-trust dialog on next session start. Choose 'Trust All' (or 'Review Hooks') — until you do, little-loops hooks will not fire."
Rationale: untrusted hooks are silently skipped (`HookRunStatus::Untrusted`), which is the worst failure mode (no error, no effect). One warning line at install time prevents the support load.

**Trust-hash churn** — `hooks/adapters/codex/README.md` MUST document that any edit to `session-start.sh` or `pre-compact.sh` (including ll plugin updates) flips Codex's trust status to `Modified` and prompts re-trust on next startup. To minimize churn, keep adapter scripts minimal (just env-set + exec) so version bumps don't routinely modify them; put any churning logic in the Python `little_loops.hooks` package instead, where it lives behind a stable subprocess interface.

**New directory**: `hooks/adapters/codex/`
```
hooks/adapters/codex/
├── session-start.sh      # Sets LL_HOOK_HOST=codex; calls python -m little_loops.hooks session_start
├── pre-compact.sh        # Sets LL_HOOK_HOST=codex; calls python -m little_loops.hooks pre_compact
├── hooks.json            # Template written by ll:init --codex to .codex/hooks.json
└── README.md             # Codex event → ll hook-intent mapping table, subprocess contract, trust-model note
```

**Config path resolution**: Add `.codex/ll-config.json` to the ordered candidate list in `scripts/little_loops/config/core.py → resolve_config_path()`. Do NOT patch `hooks/scripts/lib/common.sh` directly (FEAT-1116 superseded that approach).

## API/Interface

N/A - No public Python API changes.

New CLI flag exposed via `ll:init`:
```
ll:init --codex    # Detect Codex CLI (binary: codex) and write .codex/hooks.json
```

New environment variable (established by FEAT-769, reused here):
```
LL_STATE_DIR=".codex"   # Set by codex init to redirect state files
```

Hook configuration template written by `ll:init --codex` to `.codex/hooks.json` (internal):
```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "bash hooks/adapters/codex/session-start.sh", "timeout": 30 }] }
    ],
    "PreCompact": [
      { "hooks": [{ "type": "command", "command": "bash hooks/adapters/codex/pre-compact.sh", "timeout": 60 }] }
    ]
  }
}
```

Note: Subprocess CWD is confirmed as the session working directory (project root) — `command.current_dir(cwd)` in `codex-rs/hooks/src/engine/command_runner.rs`. Relative paths like `bash hooks/adapters/codex/session-start.sh` work as-is.

Each event value is an array of **MatcherGroup** objects. Each MatcherGroup has an optional `matcher` string (filters by event-specific fields, e.g. `"startup"` for SessionStart `source`) and a required `hooks` array. Without `matcher`, the group fires for all variants of that event. Additional handler fields: `commandWindows` (Windows command override), `async` (bool, default false), `statusMessage` (display string).

## Integration Map

### Prerequisites
- **FEAT-769** must be completed first — provides `LL_STATE_DIR` shell mechanism, Python config fallback chain, and `ll:init` OpenCode scaffolding to model after.

### Files to Modify
- `scripts/little_loops/config/core.py → resolve_config_path()` — refactor hardcoded 2-candidate probe into an ordered list; add `.codex/ll-config.json` candidate
- `skills/init/SKILL.md` — add `--codex` flag detection alongside `--opencode`
- `scripts/tests/conftest.py` — add `codex_project_dir` fixture
- `scripts/tests/test_config.py` — add Codex config path tests
- `docs/reference/PLUGIN_COMPAT.md` (or equivalent) — Codex event mapping table

### New Files
- `hooks/adapters/codex/<entry-point>` — thin stub calling `python -m little_loops.hooks <intent>`

### Research Findings — Codex CLI Plugin API

_Added by `/ll:refine-issue` 2026-05-14 — sourced from openai/codex repository:_

**Runtime**: Codex CLI is Rust-based (`codex-rs/`). Hook handlers are language-agnostic shell commands invoked via `$SHELL -lc`. **No TypeScript/Bun adapter needed** — the entry point pattern mirrors `hooks/adapters/claude-code/` (Bash scripts), not `hooks/adapters/opencode/` (TypeScript/Bun plugin). See correction in Proposed Solution.

**Binary name**: `codex` — detect via `which codex` or `.codex/` directory presence in project root.

**Config location**: `.codex/config.toml` (TOML) at project root; `~/.codex/config.toml` user-level. `CODEX_HOME` env var overrides `~/.codex/`. Hooks live in `.codex/hooks.json` (project) and `~/.codex/hooks.json` (user), merged at startup.

**Hook registration**: `ll:init --codex` should write a project-level `.codex/hooks.json`. Format (each event maps to an array of MatcherGroup objects; `matcher` is optional — omit to fire on all variants):
```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "bash hooks/adapters/codex/session-start.sh", "timeout": 30 }] }
    ],
    "PreCompact": [
      { "hooks": [{ "type": "command", "command": "bash hooks/adapters/codex/pre-compact.sh", "timeout": 60 }] }
    ]
  }
}
```

**Event → intent mapping** (8 events total — sourced from `HookEventsToml` and `HookEventNameWire` in `codex-rs/config/src/hook_config.rs`):
| Codex event (`hooks.json` key) | ll intent | Status |
|---|---|---|
| `SessionStart` | `session_start` | Implement |
| `PreCompact` | `pre_compact` | Implement |
| `PreToolUse` | — | Deferred |
| `PermissionRequest` | — | Deferred (fires when tool approval needed; hook can return `allow`/`deny`) |
| `PostToolUse` | — | Deferred |
| `PostCompact` | — | Deferred (same input shape as `PreCompact`) |
| `UserPromptSubmit` | — | Deferred |
| `Stop` | — | Deferred |

**Stdin JSON payload — `SessionStart`**:
```json
{
  "hook_event_name": "SessionStart",
  "session_id": "<uuid>",
  "cwd": "/path/to/project",
  "model": "gpt-4o",
  "permission_mode": "default",
  "source": "startup",
  "transcript_path": "/path/to/transcript.jsonl"
}
```

**Stdin JSON payload — `PreCompact`**:
```json
{
  "hook_event_name": "PreCompact",
  "session_id": "<uuid>",
  "cwd": "/path/to/project",
  "model": "gpt-4o",
  "trigger": "manual",
  "turn_id": "<uuid>",
  "transcript_path": "/path/to/transcript.jsonl"
}
```

**Hook stdout format** (sourced from `codex-rs/hooks/src/events/session_start.rs`):
- Empty stdout + exit 0: no-op, continues normally
- Plain text stdout + exit 0: injected as `additionalContext` into the model
- JSON stdout + exit 0: parsed per output schema
- Non-zero exit: sets `HookRunStatus::Failed` (logged error entry), **session continues** — non-zero does NOT block

**To abort a session from `SessionStart`**: exit 0 and return `{"continue": false, "stopReason": "reason"}`. The session stops only when the hook explicitly sets `continue: false`.

`permission_mode` enum values: `"default"`, `"acceptEdits"`, `"plan"`, `"dontAsk"`, `"bypassPermissions"`

`source` enum values: `"startup"`, `"resume"`, `"clear"` — use `"matcher": "startup"` in the MatcherGroup to limit SessionStart hook to fresh starts only.

**Env vars available in hook subprocess**: User and project hooks inherit the **parent process environment** only — no special Codex env vars are injected (confirmed from `codex-rs/hooks/src/engine/command_runner.rs`). The previously documented `CODEX_THREAD_ID` and `CODEX_SANDBOX` vars are **not confirmed** as injected. `CODEX_HOME` is present only if already set in the shell that launched Codex. Payload data arrives via stdin only. (Plugin hooks, which are distinct from user/project hooks, do get `PLUGIN_ROOT` and `PLUGIN_DATA` injected — not relevant here.)

**Trust model** (sourced from `codex-rs/hooks/src/engine/discovery.rs` and `codex-rs/tui/src/startup_hooks_review.rs`):
- Hook trust status: `managed` (always runs), `trusted` (hash matches), `modified` (hash changed → re-review), `untrusted` (no saved hash → does not run)
- On first run with a new project hook, Codex shows a startup review dialog: "Review Hooks", "Trust All and Continue", or "Continue Without Trusting"
- Trusting saves `hooks.state.<key>.trusted_hash` into **user-level** `~/.codex/config.toml` (not the project's `.codex/config.toml`)
- Key format: `file:<absolute-path-to-hooks.json>:<event_snake_case>:<group_index>:<handler_index>` — e.g. `file:/repo/.codex/hooks.json:session_start:0:0`
- If the hook command changes after being trusted, `current_hash` changes → status becomes `Modified` → user prompted to re-trust on next startup
- Document in `hooks/adapters/codex/README.md`.

**Adapter directory**: `hooks/adapters/codex/` should contain:
- `session-start.sh` — sets `LL_HOOK_HOST=codex`, pipes stdin to `python -m little_loops.hooks session_start`
- `pre-compact.sh` — sets `LL_HOOK_HOST=codex`, pipes stdin to `python -m little_loops.hooks pre_compact`
- `hooks.json` — template that `ll:init --codex` copies to `.codex/hooks.json`
- `README.md` — event→intent mapping table, subprocess contract, trust-model note

### Codebase Research Findings

> **SUPERSEDED** (2026-05-14): The "Files to Modify — Full List with Line References" block below predates FEAT-1116 (hook-intent abstraction). The shell script patch list (`lib/common.sh`, `session-start.sh`, etc.) is no longer applicable — the hook-intent Python layer replaced that approach. Use the Integration Map above for the current file list.

**Current reference pattern**: `hooks/adapters/opencode/` — study this before implementing the Codex adapter.

**FEAT-769 status** (as of 2026-05-14): **Completed**. OpenCode adapter exists at `hooks/adapters/opencode/`. FEAT-957 can begin immediately.

_Added by `/ll:refine-issue` — based on codebase analysis (2026-05-14):_

**CORRECTION — config probe file**: `scripts/little_loops/hooks/common.py` **does not exist**. The config probe lives in `scripts/little_loops/config/core.py → resolve_config_path()`. This function currently checks two candidates in order: (1) `<cwd>/.ll/ll-config.json`, (2) `<cwd>/ll-config.json`. Neither `.opencode/` nor `.codex/` is present yet. The Scope Boundary note's request for an ordered candidate list means refactoring `resolve_config_path()` to accept a parameter (or iterate a list) rather than hardcoding 2 paths.

**CORRECTION — `--opencode` in init skill**: `skills/init/SKILL.md` has **no `--opencode` flag** today. The skill only recognizes `--interactive`, `--yes`, `--force`, `--dry-run`. Implementing `--codex` means adding it as a new flag (not "alongside" an existing `--opencode`). Check completed FEAT-962 in `.issues/completed/` to see if `--opencode` was added to a different mechanism.

**CORRECTION — test pattern**: No `opencode_project_dir` fixture exists in `scripts/tests/conftest.py`. The existing config tests (`test_config.py → TestResolveConfigPath`) use `tmp_path` (pytest built-in) directly. Model the codex config path test after `TestResolveConfigPath.test_prefers_ll_dir_config` and `test_falls_back_to_root_level` — no named fixture needed.

**CORRECTION — PLUGIN_COMPAT.md**: This file does not exist. The event → intent mapping table lives in each adapter's own `README.md` (see `hooks/adapters/opencode/README.md`). The codex adapter should follow this pattern with a `hooks/adapters/codex/README.md` documenting the Codex event → ll intent mapping table, subprocess contract, and exit codes. A top-level `docs/reference/PLUGIN_COMPAT.md` is optional but not established by prior work.

**OpenCode adapter structure** (canonical reference to replicate):
- `hooks/adapters/opencode/index.ts` — TypeScript Bun plugin; `spawnIntent(intent, payload, cwd)` spawns `python -m little_loops.hooks <intent>` with `LL_HOOK_HOST: "opencode"` in env, pipes JSON payload to stdin, propagates stdout/stderr/exit-code
- `hooks/adapters/opencode/package.json` — declares `@opencode-ai/plugin` dependency; requires `bun >= 1.1.0`
- `hooks/adapters/opencode/tsconfig.json` — ESNext target with `bun-types`
- `hooks/adapters/opencode/README.md` — event → intent mapping table and subprocess contract

**Python dispatcher wiring** (`scripts/little_loops/hooks/__init__.py → main_hooks()`): reads `LL_HOOK_HOST` env var defaulting to `"claude-code"`; routes `session_start` → `session_start.handle()` and `pre_compact` → `pre_compact.handle()`. No code changes needed for the dispatcher itself — setting `LL_HOOK_HOST: "codex"` in the adapter subprocess env is sufficient for host identification.

**Test patterns for adapter**:
- Bun-required tests: `scripts/tests/test_opencode_adapter.py` (skipped when `bun` not on PATH via `pytestmark = pytest.mark.skipif`); uses `tmp_path` + per-test `_write_driver()` helper to inject a fake `little_loops.hooks.__main__`; no custom conftest fixture
- In-process host propagation tests: `scripts/tests/test_hook_intents.py → TestHooksMainModule.test_ll_hook_host_env_var_propagates` using `monkeypatch.setenv("LL_HOOK_HOST", "opencode")`
- Config probe tests: `scripts/tests/test_config.py → TestResolveConfigPath` using `tmp_path`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/session_start.py` — calls `resolve_config_path(cwd)` in `handle()` (line 85); refactored signature must remain backward-compatible with single positional `Path` arg (add new candidates as keyword-optional, not required positional) [Agent 1 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — add `"codex"` to `hooks.host` enum (currently `["claude-code", "opencode"]`); omitting this causes config-validation tooling to reject any config with `LL_HOOK_HOST=codex` [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — `test_hooks_in_schema` at line 155 asserts exact equality `host["enum"] == ["claude-code", "opencode"]`; **will break** when `"codex"` is added to schema — update assertion to include `"codex"` [Agent 3 finding]
- `scripts/tests/test_hook_intents.py` — add `TestHooksMainModule.test_ll_hook_host_env_var_propagates_codex` parallel to line 325 test; `monkeypatch.setenv("LL_HOOK_HOST", "codex")` → `assert event.host == "codex"` [Agent 3 finding]
- `scripts/tests/test_hook_session_start.py` — add `TestSessionStartConfigLoad.test_falls_back_to_codex_dir_config`; place config at `.codex/ll-config.json` and verify `session_start.handle()` picks it up [Agent 3 finding]
- `scripts/tests/test_codex_adapter.py` — new test file; mirror `test_opencode_adapter.py` with `ADAPTER_PATH = REPO_ROOT / "hooks" / "adapters" / "codex" / "<entrypoint>"`; include `test_adapter_sets_ll_hook_host_codex` using sentinel-file pattern from `test_opencode_adapter.py` lines 135–181 [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — `adapters/` description reads "one subdir per host (claude-code/, opencode/)"; add `codex/` [Agent 2 finding]
- `docs/reference/API.md` — add codex adapter bullet in `main_hooks` section alongside claude-code and opencode adapter references [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` — add `"codex"` to `LLHookEvent.host` example values (currently lists `"claude-code"` and `"opencode"`) [Agent 2 finding]
- `docs/claude-code/write-a-hook.md` — add codex adapter to "The two concrete adapters" section and `LL_HOOK_HOST` troubleshooting note [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — add codex adapter chmod entry and `LL_HOOK_HOST=codex` manual-test snippet; add codex to lock-timeout adapter list [Agent 2 finding]
- `docs/guides/GETTING_STARTED.md` — add `--codex` row to `/ll:init` flags table [Agent 2 finding]

_Second wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — directory tree at lines 85–89 lists only `claude-code/` and `opencode/` under `hooks/adapters/`; add `codex/` entry with runtime annotation (also mentioned in Step 6 prose) [Agent 1+2 finding]
- `docs/development/TESTING.md` — example fixture at lines 793, 823–825 names both existing adapter paths; add codex as third `LL_HOOK_HOST` example [Agent 2 finding]
- `docs/claude-code/automate-workflows-with-hooks.md` — Mermaid diagram at line 635 reads `Claude Code or OpenCode`; add Codex [Agent 2 finding]
- `skills/workflow-automation-proposer/SKILL.md` — line 119 example list reads `(e.g. claude-code/, opencode/)`; add `codex/` [Agent 1+2 finding]
- `skills/configure/areas.md` — illustrative hook table at lines 861, 868 shows `adapters/claude-code/` paths; update example to note codex uses its own `.codex/hooks.json` wiring [Agent 2 finding]

## Implementation Steps

> **Reference**: Study `hooks/adapters/opencode/` before starting — it is the canonical pattern for host adapter stubs.

1. ~~**Research Codex CLI plugin API**~~ **DONE** — See "Research Findings — Codex CLI Plugin API" in Integration Map above. Key result: Codex uses shell-command hooks via `.codex/hooks.json` (no TypeScript SDK). Adapter is Bash scripts, not TypeScript. Event names: `SessionStart` → `session_start`, `PreCompact` → `pre_compact`.
2. **Scaffold `hooks/adapters/codex/`** — create `session-start.sh` and `pre-compact.sh` Bash scripts (set `LL_HOOK_HOST=codex`, pipe stdin, call `python -m little_loops.hooks <intent>`); add `hooks.json` template **with `"matcher": "startup"` on SessionStart** (see Policy Decisions); add `README.md` with event→intent mapping table, trust-model note, and trust-hash-churn guidance. Mirror `hooks/adapters/claude-code/` (Bash), NOT `hooks/adapters/opencode/` (TypeScript). Keep scripts minimal — env-set + exec only — so plugin updates don't routinely flip Codex trust status to `Modified`.
3. **Extend config fallback chain** — refactor `scripts/little_loops/config/core.py → resolve_config_path()` from a hardcoded 2-candidate check into an ordered probe list; add `.codex/ll-config.json` candidate (probed first when `LL_HOOK_HOST=codex` or `LL_STATE_DIR=.codex`, otherwise after `.ll/` and root-level — preserve the host-unset default). Do NOT patch `hooks/scripts/lib/common.sh` or a non-existent `hooks/common.py`. Do NOT redirect other state directories (`.loops/`, `.issues/`, etc.) — that is explicitly out of scope (see Cross-Compat Scope Boundaries).
4. **Extend `ll:init`** — add `--codex` detection flag in `skills/init/SKILL.md`; detection signal: `which codex` binary OR `.codex/` directory; write `.codex/hooks.json` from `hooks/adapters/codex/hooks.json` template; **print the trust-dialog warning** (see Policy Decisions → Trust-model UX) as the last line of the init flow.
5. **Tests** — use `tmp_path` directly (no named fixture needed); add `test_load_config_codex_path()` and `test_codex_path_takes_precedence_when_host_codex()` to `scripts/tests/test_config.py`; add `scripts/tests/test_codex_adapter.py` with Bash subprocess tests (skip guard: `shutil.which("bash")`); add `test_ll_hook_host_env_var_propagates_codex` to `scripts/tests/test_hook_intents.py`; update `test_config_schema.py::test_hooks_in_schema` enum assertion to include `"codex"`.
6. **Docs and listing** — update `docs/ARCHITECTURE.md`, `docs/reference/API.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/claude-code/write-a-hook.md`, `docs/development/TROUBLESHOOTING.md`, `docs/guides/GETTING_STARTED.md`, `docs/development/TESTING.md`, `docs/claude-code/automate-workflows-with-hooks.md`, `skills/workflow-automation-proposer/SKILL.md`, `skills/configure/areas.md`, and `.claude/CLAUDE.md` per the Wiring Phase notes below. `hooks/adapters/codex/README.md` is the canonical event→intent mapping document reused by FEAT-992 (no top-level `PLUGIN_COMPAT.md`).
7. **Create `docs/reference/HOST_COMPATIBILITY.md`** (new file) — host parity matrix with columns for Claude Code, OpenCode, Codex; rows for each hook intent, slash-command discovery, skill discovery, orchestration CLI binary, config probe path, state dir. Mark cells with ✓ / ✗ / N/A and footnote-link to the issue covering each ✗ (e.g. FEAT-1462 for orchestration). Backfill Claude Code and OpenCode columns from current state.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `config-schema.json` — add `"codex"` to `hooks.host` enum array
8. Update `scripts/tests/test_config_schema.py` — fix `test_hooks_in_schema` enum assertion to include `"codex"` (exact-equality check will break when schema is updated)
9. Add `scripts/tests/test_codex_adapter.py` — new adapter integration test mirroring `test_opencode_adapter.py`; include `test_adapter_sets_ll_hook_host_codex` sentinel-file test
10. Add `TestHooksMainModule.test_ll_hook_host_env_var_propagates_codex` to `scripts/tests/test_hook_intents.py`
11. Add `TestSessionStartConfigLoad.test_falls_back_to_codex_dir_config` to `scripts/tests/test_hook_session_start.py`
12. Update documentation: `.claude/CLAUDE.md` adapters line; `docs/reference/API.md` main_hooks section; `docs/reference/EVENT-SCHEMA.md` host examples; `docs/claude-code/write-a-hook.md` adapter list; `docs/development/TROUBLESHOOTING.md` chmod and lock-timeout sections; `docs/guides/GETTING_STARTED.md` init flags table
13. Verify `scripts/little_loops/hooks/session_start.py` `handle()` call site — `resolve_config_path(cwd)` must remain a valid single-positional call after the signature refactor
14. Update second-pass doc sites (added by second `/ll:wire-issue` pass): `docs/ARCHITECTURE.md` adapter tree (line 89); `docs/development/TESTING.md` fixture prose (lines 793, 823–825); `docs/claude-code/automate-workflows-with-hooks.md` Mermaid node (line 635); `skills/workflow-automation-proposer/SKILL.md` example list (line 119); `skills/configure/areas.md` illustrative table (lines 861, 868)

## Impact

- **Priority**: P5 — Speculative audience expansion; Codex plugin API unverified
- **Effort**: Low-Medium — FEAT-769 does the hard work; this is a parallel translation once Codex plugin API is understood
- **Risk**: Low — Additive change, no modifications to Claude Code or OpenCode paths
- **Breaking Change**: No
- **Depends on**: FEAT-769

## Related Key Documentation

_No documents linked._


## Blocked By

_None — FEAT-1116 (hook-intent abstraction) and FEAT-769 (OpenCode compatibility) both completed; the canonical pattern at `hooks/adapters/<host>/` is now in place._


## Blocks

- FEAT-992

## Labels

`feature`, `codex`, `compatibility`, `hooks`

## Verification Notes

**Verdict**: READY — Verified 2026-05-15 (manual review)

- Stale ACs rewritten: AC #4 (config path now matches `resolve_config_path()` reality), AC #6 (no longer references `lib/common.sh`), AC #7 (resolves PLUGIN_COMPAT.md vs per-adapter README tension — per-adapter README wins, `HOST_COMPATIBILITY.md` is the new shared deliverable).
- Deferred policies decided: SessionStart matcher = `"startup"`; PostCompact = deferred (no consumer); trust-dialog warning required in `ll:init --codex`; trust-hash churn documented in adapter README.
- Cross-compat scope explicitly bounded: orchestration → FEAT-1462; slash-command/skill discovery → out of scope; `LL_STATE_DIR` → config-probe only, not full state redirection.
- Outstanding risk: `HOST_COMPATIBILITY.md` is a new doc deliverable adding a 24th touchpoint to an already wide change surface; consider splitting the matrix doc into a fast-follow if implementation churn becomes painful.

### Prior verdicts

**Verdict**: NEEDS_UPDATE — Verified 2026-05-14

- **FEAT-1116 completed** (hook-intent abstraction shipped: `scripts/little_loops/hooks/` + `hooks/adapters/`). Removed from `blocked_by`.
- **FEAT-769 completed** (OpenCode adapter exists at `hooks/adapters/opencode/`). Removed implicit blocker.
- Now **unblocked**. Could be re-prioritized up.
- **Integration Map is stale**: The `codex-plugin/` TypeScript directory structure, edits to `hooks/scripts/lib/common.sh`, edits to `hooks/scripts/session-start.sh` etc. are all SUPERSEDED. See the 2026-05-04 and 2026-05-10 Scope Boundary notes below — implementation should follow the `hooks/adapters/codex/` adapter pattern (thin stub calling `python -m little_loops.hooks.<intent>`), not a full TS plugin directory. The Python config-fallback chain is centralized via the hook-intent abstraction, not patched into `lib/common.sh`.
- Implementation Steps and "Files to Modify — Full List" sections need a rewrite before pickup; the current text predates FEAT-1116.

### Prior verifications
- 2026-04-11 — VALID; both FEAT-769 and FEAT-1116 still open at that time.

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-14 (post-wiring-pass re-run)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 62/100 → MODERATE

### Concerns
- Acceptance criterion 6 still references `lib/common.sh` — corrections explicitly say NOT to patch it; AC wording is stale
- "Files to Modify" lists `scripts/tests/conftest.py` but codebase research says no named fixture is needed (`tmp_path` directly)
- Acceptance criterion 7 says mapping table lives in "shared docs (e.g. `docs/reference/PLUGIN_COMPAT.md`)" but implementation steps resolve this to `hooks/adapters/codex/README.md`; minor tension, resolvable during implementation

### Outcome Risk Factors
- **Wide change surface across 23 sites** (7 code/config, 5 test files, 4-file adapter scaffold, 7 primary doc files, 5 secondary doc sites added by second wiring pass) — breadth penalty drives Criterion A to 9/25 despite mechanical depth at most sites; mitigate by batching doc-only updates last and verifying each code/test change atomically
- ~~**Codex CLI plugin API is unresearched**~~ **RESOLVED** — API fully documented in Research Findings (web research 2026-05-14). Runtime is Rust/Bash; hooks.json format, stdin payloads, exit-code semantics, env vars, and trust model all verified against openai/codex source. Step 1 is complete; Step 2 (adapter scaffold) may begin.

## Session Log
- manual-review - 2026-05-15T00:00:00 - Cross-compat readiness review; rewrote stale ACs (#4, #6, #7), decided SessionStart matcher / PostCompact / trust-UX / trust-hash policies, added Cross-Compat Scope Boundaries carving out orchestration (→ FEAT-1462), slash-command/skill discovery, and LL_STATE_DIR semantics; added `docs/reference/HOST_COMPATIBILITY.md` as new doc deliverable.
- `/ll:confidence-check` - 2026-05-14T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c29411a8-f788-4af4-a6c1-f2ab8b0c6047.jsonl`
- `/ll:wire-issue` - 2026-05-14T22:49:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5897d5a7-85bb-4129-b8c1-6df022abf343.jsonl`
- `web-research` - 2026-05-14T00:00:00 - Verified hooks.json format, exit-code semantics, stdin payloads, env vars, trust model, and full 8-event list against openai/codex source; corrected `CODEX_THREAD_ID`/`CODEX_SANDBOX` claim (unconfirmed for user hooks); added `PermissionRequest` and `PostCompact` events; fixed `permission_mode` enum value; documented blocking via JSON `continue:false`, not non-zero exit; trust model hash key format and storage location
- `/ll:refine-issue` - 2026-05-14T22:40:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5e4ca05-0acd-48f8-9ebf-e8c60b164a84.jsonl`
- `/ll:confidence-check` - 2026-05-14T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/222fabb8-b6c2-40a8-9146-048eacc2b33f.jsonl`
- `/ll:wire-issue` - 2026-05-14T22:27:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/119e6b0a-fc31-4207-8bc8-362b914e7b55.jsonl`
- `/ll:refine-issue` - 2026-05-14T22:21:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bdf17f7b-9bb9-4a3e-83f0-34964c6a1743.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-14T21:19:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75505ad4-6733-4424-b334-3143f412786b.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T19:40:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d630f0d-2126-4eb0-8da2-2057ea37658f.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-23T00:14:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c0e0697-1da9-403b-82a7-6eb401f63ad3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-22T20:04:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82d256a6-9a99-40f5-8866-377a208de262.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-19T01:16:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c7ed14d-9621-459d-9f93-384968b2e6f6.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:refine-issue` - 2026-04-06T02:33:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c273f16-a946-4cde-a3ce-1eb1a83742ae.jsonl`
- `/ll:format-issue` - 2026-04-05T23:24:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80483a00-b614-43e6-8ba2-461cc77fadae.jsonl`
- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d4087be-1201-4786-a118-8eb18c18f952.jsonl`

---

**Open** | Created: 2026-04-05 | Priority: P5

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue establishes the plugin-compatibility pattern that FEAT-992 (Pi) will reuse. Extract a reusable config-directory-resolution abstraction in `scripts/little_loops/config/core.py` and `hooks/scripts/lib/common.sh` that accepts an ordered list of candidate config dirs (`.claude/`, `.codex/`, `.opencode/`, `.pi/`, ...), so FEAT-992 can reuse the mechanism instead of patching the same functions again.

**Note** (added by `/ll:audit-issue-conflicts`): The `codex-plugin/` scaffold step (Step 2) must be gated on completing the Codex CLI SDK runtime research (Step 1). If Codex uses a different JS runtime than the Bun/TypeScript approach established by FEAT-961 for the OpenCode plugin, document the divergence explicitly here and in FEAT-961 before creating the plugin directory, so multi-runtime JS tooling decisions are made deliberately rather than discovered mid-implementation.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): The `codex-plugin/` TypeScript directory structure (session.ts, tool.ts, compact.ts) described in the Proposed Solution and Integration Map is superseded by FEAT-1116's hook-intent abstraction model. When implementing, use the thin adapter stub approach under `hooks/adapters/codex/` (calling into `python -m little_loops.hooks.<intent>`) rather than scaffolding a full TS plugin directory. Do NOT create `codex-plugin/`.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): The implementation MUST NOT extend `hooks/scripts/lib/common.sh:ll_resolve_config()` directly. FEAT-1116 will port that function to Python (`scripts/little_loops/hooks/common.py`). Add `.codex/` to the ordered candidate list in the new Python `common.py` module introduced by FEAT-1116 instead. Add this constraint to the "Files to Modify" list and implementation steps.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-10): This issue implements a **Host Adapter** (Codex CLI integration), NOT an Extension in the FEAT-917 sense. Host adapters live under `hooks/adapters/codex/`, have no PyPI manifest, and are NOT discoverable via `ll extensions` commands. Do not reference FEAT-917's extension registry schema or `ll extensions` CLI from this issue's implementation. The canonical naming: "Extensions" = PyPI packages (`little-loops-ext-*`); "Host Adapters" = per-host wiring under `hooks/adapters/`.

### Cross-Compat Scope Boundaries (added 2026-05-15)

Three categories of cross-host work were considered for this issue and explicitly carved out:

**Orchestration layer (carved out → [[FEAT-1462]])**: `ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, FSM evaluators, and FSM handoff all spawn `claude -p` directly (call sites: `scripts/little_loops/subprocess_utils.py:261`, `parallel/worker_pool.py:584`, `cli/action.py:142,149`, `fsm/handoff_handler.py:114`, `fsm/evaluators.py:609`). This issue does NOT abstract the binary. Until FEAT-1462 ships, Codex users get hook wiring only — the automation tools remain Claude-Code-only. The `HOST_COMPATIBILITY.md` matrix added by this issue MUST mark this clearly in the Codex column.

**Slash-command and skill discovery (carved out)**: Codex reads `.codex/prompts/` (markdown prompts), not `.claude/commands/*.md`. There is no evidence Codex picks up `.claude/skills/*/SKILL.md` either. This issue does NOT mirror or symlink command/skill content into `.codex/`. Track separately if/when user demand exists; current scope is hook-adapter parity, full stop. The `HOST_COMPATIBILITY.md` matrix MUST show command/skill cells as "not available" for Codex.

**`LL_STATE_DIR` semantics (clarified, not extended)**: The FEAT-769 env var redirects `.ll/` state lookups. Within FEAT-957's scope, the only redirection added is the `.codex/ll-config.json` config-probe candidate. Other state directories (`.loops/`, `.issues/`, scratch pads under `.loops/tmp/scratch/`, FSM run dirs) remain under their existing paths regardless of `LL_STATE_DIR`. If a future issue needs full state redirection per host, file it explicitly — do NOT silently expand the env var's reach here. Document the exact set of files affected by `LL_STATE_DIR=.codex` in `hooks/adapters/codex/README.md`.

**Hook surface parity matrix (in scope, doc deliverable)**: The new `docs/reference/HOST_COMPATIBILITY.md` matrix is the visible artifact users consult to know what's wired where. Columns: Claude Code, OpenCode, Codex. Rows: each hook intent, command discovery, skill discovery, orchestration CLI, config probe path, state dir. Cells: ✓ / ✗ / N/A with footnote links to the relevant issue (e.g. FEAT-1462 for the orchestration ✗).
