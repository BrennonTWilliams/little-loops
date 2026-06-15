# Gemini CLI Surface Research

**Status:** Research complete — all three questions have definitive answers
**Last verified:** 2026-06-15
**Research issue:** FEAT-2179
**Gemini CLI version:** 0.46.0 (npm package `@google/gemini-cli`)

## Sources

- `gemini --help` output (locally installed via npm at `/Users/brennon/.npm-global/bin/gemini`)
- `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/hooks/index.md`
- `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/hooks/reference.md`
- `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/hooks/writing-hooks.md`
- `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/cli/gemini-md.md`
- `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/cli/custom-commands.md`
- `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/cli/skills.md`
- `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/extensions/reference.md`
- `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/extensions/writing-extensions.md`
- `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/cli/settings.md`
- `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/examples/hooks/hooks/hooks.json`
- `gemini hooks --help`, `gemini extensions --help`, `gemini skills --help`
- `~/.gemini/skills/skill-repair/SKILL.md` (installed skill, format reference)
- Web: google-gemini/gemini-cli README, hooks docs, extensions reference

---

## Q1: Binary surface

**Finding: YES — full headless orchestration support, flags nearly identical to Claude Code.**

### Binary and version

```
Binary name:   gemini
npm package:   @google/gemini-cli
Install:       npm install -g @google/gemini-cli
               brew install gemini-cli
Installed at:  /Users/brennon/.npm-global/bin/gemini
Version:       0.46.0
```

### Flag translation table

| Claude Code flag | Gemini CLI equivalent | Notes |
|---|---|---|
| `claude -p "<prompt>"` | `gemini -p "<prompt>"` | **Identical flag** — `-p`/`--prompt` means headless in both |
| `--output-format stream-json` | `--output-format stream-json` (or `-o stream-json`) | **Identical flag name** |
| `--output-format json` | `--output-format json` (or `-o json`) | Single `{response, stats, error?}` blob |
| `--model <id>` | `-m <id>` / `--model <id>` | Accepts `auto`, `pro`, `flash`, `flash-lite`, `gemini-2.5-pro`, etc. |
| `--dangerously-skip-permissions` | `--approval-mode=yolo` or `--yolo` | `--yolo` is deprecated; prefer `--approval-mode=yolo` |
| `--continue` / `--session-id` | `-r latest` / `-r <index>` / `-r <session-id>` | `--resume` accepts session ID, `"latest"`, or numeric index |
| `--agent <name>` | **N/A → CapabilityNotSupported** | No per-agent selection flag; skills activate implicitly |
| `--tools <list>` | `--policy <path>` (Policy Engine) | `--allowed-tools` is deprecated; Policy Engine replaces it |
| `--sandbox` | `-s` / `--sandbox` | Runs in Docker sandbox |
| `claude --version` | `gemini --version` | Returns `0.46.0` style output |
| — | `--extensions <names>` / `-e <names>` | Comma-separated: restrict which extensions are active |
| — | `--acp` | ACP (Agent Code Pilot) mode — no Claude Code equivalent |

### Exit codes (headless mode)

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error / API failure |
| 42 | Input error (invalid prompt or args) |
| 53 | Turn limit exceeded |

### `build_*` method flag shapes

```python
# build_streaming — streaming JSONL output
["gemini", "-p", prompt, "--output-format", "stream-json", "--approval-mode", "yolo"]

# build_blocking_json — single JSON blob
["gemini", "-p", prompt, "--output-format", "json", "--approval-mode", "yolo"]

# build_version_check
["gemini", "--version"]

# build_detached — background invocation (no output-format)
["gemini", "-p", prompt, "--approval-mode", "yolo"]
```

### Recommended `HostCapabilities` values

```python
HostCapabilities(
    streaming=True,          # --output-format stream-json ✓
    permission_skip=True,    # --approval-mode=yolo ✓
    agent_select=False,      # no --agent flag; implicit via skills
    tool_allowlist=False,    # Policy Engine exists but no simple flag; keep False
)
```

`tool_allowlist` is marked `False` because the Policy Engine requires a TOML file path rather than a simple command-line argument list — callers that check `HostCapabilities.tool_allowlist` expect a flag-based mechanism. Track as a future `partial` if demand arises.

---

## Q2: Lifecycle hooks / extension events

**Finding: YES — first-class hook system, 11 events, stdin/stdout JSON protocol nearly identical to Claude Code.**

### Hook configuration location

Hooks are configured in `settings.json` under the `hooks:` key. Resolution order (highest to lowest precedence):

1. `.gemini/settings.json` — project scope (committed to version control)
2. `~/.gemini/settings.json` — user scope (global)
3. `/etc/gemini-cli/settings.json` — system scope
4. Extension `hooks/hooks.json` — per-extension bundle

**For ll's `ll:init --gemini`**, hooks should be written to `.gemini/settings.json` in the project. Alternatively, distributing ll as a Gemini extension bundles hooks in `hooks/hooks.json` within the extension directory (same JSON schema as the `hooks:` block in settings).

### Configuration schema

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "name": "ll-session-start",
            "type": "command",
            "command": "$GEMINI_PROJECT_DIR/.gemini/hooks/ll-session-start.sh",
            "timeout": 30000
          }
        ]
      }
    ],
    "PreCompress": [
      {
        "hooks": [
          {
            "name": "ll-pre-compress",
            "type": "command",
            "command": "$GEMINI_PROJECT_DIR/.gemini/hooks/ll-pre-compress.sh",
            "timeout": 30000
          }
        ]
      }
    ]
  }
}
```

Hook configuration fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | Currently only `"command"` |
| `command` | string | Yes | Shell command to execute |
| `name` | string | No | Friendly name for logs |
| `timeout` | number | No | Milliseconds; default 60000 |
| `description` | string | No | Documentation string |

### Event inventory and ll intent mapping

| Gemini event | ll intent | Advisory? | Input extras | ll handler relevance |
|---|---|---|---|---|
| `SessionStart` | `session_start` | Advisory only (cannot block) | `source: "startup"|"resume"|"clear"` | context loading, config probe |
| `SessionEnd` | `session_end` | Best-effort (CLI won't wait) | `reason: "exit"|"clear"|"logout"|"other"` | cleanup |
| `BeforeAgent` | `user_prompt_submit` | ✓ Blocking | `prompt` | duplicate-ID check, optimize-prompt |
| `BeforeTool` | `pre_tool_use` | ✓ Blocking | `tool_name`, `tool_input`, `mcp_context` | learning-test discoverability gate |
| `AfterTool` | `post_tool_use` | ✓ Blocking | `tool_name`, `tool_input`, `tool_response` | analytics byte tracking |
| `PreCompress` | `pre_compact` | Advisory, async | `trigger: "auto"|"manual"` | pre-compact checkpoint |
| `AfterAgent` | (no ll intent yet) | ✓ Blocking (deny=retry) | `prompt`, `prompt_response` | potential: response validation |
| `BeforeModel` | (no ll intent yet) | ✓ Blocking | `llm_request` | potential: model swap |
| `AfterModel` | (no ll intent yet) | ✓ Per-chunk | `llm_request`, `llm_response` | potential: PII filtering |
| `BeforeToolSelection` | (no ll intent yet) | Filter-only | `llm_request` | potential: tool filtering |
| `Notification` | (no ll intent yet) | Observability only | `notification_type`, `message`, `details` | potential: alerting |

**Advisory-only caveats**: `SessionStart` and `PreCompress` cannot block the lifecycle — `continue` and `decision` output fields are ignored. For `session_start`, `additionalContext` from output is injected as the first history turn (interactive) or prepended to the prompt (headless). For `PreCompress`, the hook fires asynchronously and cannot modify the compression.

### I/O protocol

**Stdin** (all hooks receive these base fields as JSON):
```json
{
  "session_id": "string",
  "transcript_path": "string",
  "cwd": "string",
  "hook_event_name": "string",
  "timestamp": "ISO 8601"
}
```

**Stdout** (common output fields):
```json
{
  "systemMessage": "string (shown to user)",
  "suppressOutput": false,
  "continue": true,
  "stopReason": "string (when continue=false)",
  "decision": "allow | deny",
  "reason": "string (sent to agent when denied)",
  "hookSpecificOutput": {}
}
```

Exit codes: **0** = success (parse stdout as JSON), **2** = system block (use stderr as rejection reason), **other** = warning (non-fatal, CLI continues).

### Environment variables in hook scripts

| Variable | Description |
|---|---|
| `GEMINI_PROJECT_DIR` | Absolute path to project root |
| `GEMINI_SESSION_ID` | Unique session ID |
| `GEMINI_CWD` | Current working directory |
| `GEMINI_PLANS_DIR` | Plans directory path |
| `CLAUDE_PROJECT_DIR` | **Alias for `GEMINI_PROJECT_DIR`** — provided for Claude Code compatibility |

The `CLAUDE_PROJECT_DIR` alias confirms intentional Claude Code parity in Gemini CLI. The `gemini hooks migrate --from-claude` command further confirms this: Gemini has a built-in tool to migrate Claude Code hooks to Gemini format.

### Matcher semantics

- **Tool events** (`BeforeTool`, `AfterTool`): matcher is a **regex** (e.g., `"write_file|replace"`)
- **Lifecycle events**: matcher is an **exact string** (e.g., `"startup"`, `"resume"`, `"clear"`)
- `"*"` or `""` (empty string) matches all occurrences

### Adapter implementation path

**Option A — Direct settings injection** (`ll:init --gemini`):
Write the `hooks:` block into `.gemini/settings.json` at install time. Simple but invasive (modifies a file Gemini owns). Suitable for a quick initial implementation.

**Option B — Extension bundle** (recommended long-term):
Distribute ll as a Gemini extension. The extension directory (`hooks/adapters/gemini/`) contains `hooks/hooks.json` (same schema) and the adapter shell scripts. Users install with `gemini extensions install <ll-repo-url>`. Hooks are isolated to the extension, not mixed into the user's `settings.json`.

The adapter shell scripts themselves will be very similar to the existing `hooks/adapters/claude-code/` scripts — the event payload shapes are intentionally compatible.

---

## Q3: Plugin / skill / command discovery

**Finding: YES — three distinct surfaces, two are directly compatible with ll's existing format.**

### Surface 1: Custom commands (`.gemini/commands/*.toml`)

| Aspect | Detail |
|---|---|
| Project scope | `.gemini/commands/*.toml` (committed to VCS) |
| User scope | `~/.gemini/commands/*.toml` (global) |
| Format | TOML with required `prompt =` and optional `description =` |
| Namespacing | Subdirectories → colon separator: `git/commit.toml` → `/git:commit` |
| Precedence | Project overrides user of same name |
| Reload | `/commands reload` — no restart needed |

**Format example:**
```toml
description = "Capture an issue from conversation context"
prompt = "Run /ll:capture-issue to analyze the conversation and capture any actionable issues."
```

**Gap vs ll `commands/*.md`**: ll uses markdown with YAML frontmatter; Gemini uses TOML. A bridge script (`ll-adapt-commands-for-gemini`) would need to convert each `commands/*.md` into a `.toml` file. The Extension approach (Option B) bundles `.toml` files inside the extension directory — less invasive for project users.

### Surface 2: Agent skills (`.gemini/skills/<name>/SKILL.md`)

| Aspect | Detail |
|---|---|
| Workspace scope | `.gemini/skills/<name>/SKILL.md` or `.agents/skills/<name>/SKILL.md` |
| User scope | `~/.gemini/skills/<name>/SKILL.md` or `~/.agents/skills/` |
| Format | YAML frontmatter + markdown body (same structure as ll's `skills/*/SKILL.md`) |
| Discovery | Skills list (name + description) injected into system prompt at session start |
| Activation | Model calls `activate_skill` tool; user gets consent prompt; then full body is injected |
| Install | `gemini skills install <github-url>` |

**`SKILL.md` frontmatter:**
```yaml
---
name: skill-slug           # required; slug identifier
description: |             # required; trigger hint for the model
  When and why to use this skill.
license: Apache-2.0        # optional
metadata:
  version: v1              # optional
  publisher: google        # optional
---
```

**Compatibility with ll `skills/*/SKILL.md`**:

| Field | ll format | Gemini format | Compatible? |
|---|---|---|---|
| `name:` | absent (uses dir name) | required | Minor gap — most ll skills already have `name:` |
| `description:` | required (≤100 chars) | required (free-form trigger hint) | ✓ (same key, compatible semantics) |
| `license:` | absent | optional | N/A |
| `metadata.version:` | absent | optional | N/A |
| `metadata.publisher:` | absent | optional | N/A |
| Body | Skill instructions | Instructions + on-demand context | ✓ |
| `agents/openai.yaml` | absent (not needed) | absent (no Gemini equivalent) | N/A — no adaptation needed |

**Key difference from Codex**: Gemini skills are **on-demand** (progressive disclosure — only name + description loaded at startup; full body injected on `activate_skill`). Claude Code and Codex inject skill content directly into context. This means Gemini users will experience a consent prompt before each skill activates — different UX from Claude Code.

**Adaptation work**: minimal. An `ll-adapt-skills-for-gemini` script (or manual pass) would add `name:` to the few ll `SKILL.md` files missing it. No `agents/openai.yaml` equivalent exists or is needed.

**`.agents/skills/` alias**: Gemini also recognizes `.agents/skills/` as a workspace skills path — this is an interoperability alias for cross-tool compatibility.

### Surface 3: Extensions (`~/.gemini/extensions/<name>/`)

Extensions are the packaging and distribution layer. They bundle all four surfaces:

```
my-ll-extension/
├── gemini-extension.json    # manifest
├── hooks/
│   └── hooks.json           # hook definitions (same schema as settings.json hooks block)
├── skills/                  # agent skills
│   └── <name>/SKILL.md
├── commands/                # custom commands
│   └── <name>.toml
├── agents/                  # sub-agent definitions (.md files) — preview feature
└── GEMINI.md                # context loaded into every session
```

**`gemini-extension.json` key fields:**
```json
{
  "name": "little-loops",
  "version": "1.0.0",
  "description": "Issue management and automation toolkit for Gemini CLI",
  "contextFileName": "GEMINI.md"
}
```

Variables available in the manifest and `hooks/hooks.json`:
- `${extensionPath}` — absolute path to extension directory
- `${workspacePath}` — absolute path to current workspace
- `${/}` — platform-specific path separator

**Install:** `gemini extensions install https://github.com/BrennonTWilliams/little-loops`
**Link (dev):** `gemini extensions link ./hooks/adapters/gemini/`

The extension approach is the **recommended long-term packaging strategy** for ll on Gemini, analogous to how Codex uses the Skills API + `ll-adapt-skills-for-codex`.

### Project instructions file

`GEMINI.md` is the exact analog of `CLAUDE.md`. Loaded hierarchically:
1. `~/.gemini/GEMINI.md` (global user context)
2. Workspace parent directories (scanning upward)
3. JIT: when a tool accesses a file, `GEMINI.md` files in that path's ancestors are auto-loaded

`ll:init --gemini` should create a `.gemini/GEMINI.md` that imports or mirrors the content of `.claude/CLAUDE.md` (or a shared `AGENTS.md` at the project root if cross-tool support is desired). Gemini also recognizes `context.fileName: ["AGENTS.md", "CLAUDE.md", "GEMINI.md"]` if configured in `settings.json`.

### Config probe path

ll config for Gemini should live at `.gemini/ll-config.json` (NOT `.gemini/settings.json` which Gemini CLI owns). This follows the established pattern:
- Claude Code: `.claude/ll-config.json` (or `.ll/ll-config.json`)
- Codex: `.codex/ll-config.json`
- Pi: `.pi/ll-config.json`
- **Gemini: `.gemini/ll-config.json`**

---

## Decision tree outcomes

```
Q1: Headless mode?
└── YES → -p / --prompt (identical to Claude Code)
    └── Streaming JSON: -o stream-json (identical flag name)
    └── build_streaming / build_blocking_json / build_version_check / build_detached → straightforward

Q2: Lifecycle hooks?
└── YES → 11 events, stdin/stdout JSON, nearly identical to Claude Code
    ├── High-priority wiring: SessionStart, PreCompress, BeforeTool, AfterTool, BeforeAgent
    ├── Advisory-only: SessionStart (cannot block), PreCompress (async)
    └── New ll intents possible: AfterAgent, BeforeModel, BeforeToolSelection, Notification

Q3: Plugin/skill/command discovery?
└── YES → three surfaces
    ├── Skills: .gemini/skills/<name>/SKILL.md — compatible; minor adaptation (add name: field)
    ├── Commands: .gemini/commands/*.toml — TOML format; bridge script or extension bundle needed
    └── Extensions: distribution channel — cleanest install path for ll as a whole
```

---

## Recommended child issues for EPIC-2178

| # | Type | Title | Depends on |
|---|---|---|---|
| 1 | FEAT | `GeminiRunner` stub in `host_runner.py` (raises `HostNotConfigured`; `_PROBE_ORDER` entry) | — |
| 2 | FEAT | `GeminiRunner` full implementation (real `build_*` methods; flag translation) | child 1 |
| 3 | FEAT | Hook adapter — write to `.gemini/settings.json` (Option A) OR extension bundle (Option B) | child 1 |
| 4 | ENH | Config probe — `.gemini/ll-config.json` in `config/core.py _config_candidates()` | child 1 |
| 5 | ENH | Skills adaptation — `ll-adapt-skills-for-gemini` (add `name:` where missing) | — |
| 6 | ENH | Commands adaptation — `ll-adapt-commands-for-gemini` (`.md` → `.toml`) OR extension commands bundle | child 5 |
| 7 | FEAT | `GEMINI.md` project context file (created by `ll:init --gemini`) | — |
| 8 | FEAT | `HOST_COMPATIBILITY.md` Gemini column — flip cells from `(deferred)` to ✓ as children land | children 1–6 |
| 9 | FEAT | Conformance test suite (`ll-auto`/`ll-sprint`/`ll-loop` golden paths against `gemini -p`) | children 2–4 |

**Decision required before child 3**: Extension bundle vs direct settings injection. The Extension approach (Option B) is cleaner long-term and matches the established Codex pattern, but requires more scaffolding upfront. Option A (direct settings) is a valid quick start and can be replaced by Option B later.

---

## Capability map

```python
# Recommended GeminiRunner HostCapabilities (for host_runner.py)
HostCapabilities(
    streaming=True,          # gemini -o stream-json
    permission_skip=True,    # gemini --approval-mode=yolo
    agent_select=False,      # no --agent flag; skills activate implicitly
    tool_allowlist=False,    # Policy Engine is TOML-file-based, not a simple list flag
)
```
