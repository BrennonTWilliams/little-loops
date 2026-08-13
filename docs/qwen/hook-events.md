# Qwen Code Hook Events

How Qwen Code hook events map to little-loops hook intents. All mappings on this page were live-verified on qwen **0.21.6** by the FEAT-3155 research spike (`thoughts/research/qwen-code-surface.md`); the adapter landed as FEAT-3158 under EPIC-3154.

The adapter shims (`scripts/little_loops/hooks/adapters/qwen/*.sh`) are deliberately dumb: each exports `LL_HOOK_HOST=qwen`, re-`cd`s into the payload's `cwd` (in case hooks are spawned from an extension/plugin root — BUG-2921 hardening), pipes the stdin JSON payload to `python -m little_loops.hooks <intent>`, and exits with its status. All payload handling lives in the host-agnostic Python layer (`scripts/little_loops/hooks/`).

---

## Event → intent mapping

| Qwen event | little-loops intent | Notes |
| --- | --- | --- |
| `SessionStart` | `session_start` | Wired without a matcher (fires for `startup`, `resume`, `clear`, `compact` sources); payload carries `source`, `permission_mode`, `model` |
| `SessionStart` | `drift_check` | Second entry on the same event — advisory doc-drift report |
| `PreCompact` | `pre_compact` | Wired with matcher `manual\|auto`; advisory |
| `PreCompact` | `pre_compact_handoff` | Second entry on the same event — preserves handoff state |
| `UserPromptSubmit` | `user_prompt_submit` | **Blockable.** `prompt` is a plain string (no block-array drift like kimi) |
| `PreToolUse` | `pre_tool_use` | **Blockable.** Wired with matcher `write_file\|edit` — Qwen **runtime tool ids**, never Claude display names |
| `PostToolUse` | `post_tool_use` | Two groups: `.*` (all tools, fire-and-forget) and `write_file\|edit` (`edit_batch_nudge` advisory) |
| `Stop` | — (legacy scripts) | No `stop` intent exists — the shim resolves `hooks/scripts/context-handoff-sentinel.sh` + `session-cleanup.sh` via `CLAUDE_PLUGIN_ROOT`/`LL_PLUGIN_ROOT` and no-ops gracefully when absent |
| `SessionEnd` | `session_end` | **Native event** — but **does not fire under `qwen -p` headless** (see below) |
| `SubagentStart` | `subagent_start` | Payload carries `agent_id` / `agent_type` |
| `SubagentStop` | `subagent_stop` | Same payload shape |
| `PostToolUseFailure` | — | Qwen-only event; **(deferred)** — no ll consumer yet |
| `PermissionRequest` / `PermissionDenied` | — | Native Qwen events; **(deferred)** — no ll consumer yet |
| `Notification`, `SessionDelete`, `MessageDisplay`, `TodoCreated`, `TodoCompleted` | N/A | Qwen-only events with no ll analog |

Every payload carries the Claude-compatible base fields: `hook_event_name`, `session_id`, `transcript_path`, `cwd`, `timestamp` — plus Qwen extras (`permission_mode`, `model`, `tool_call_id`, Stop telemetry like `context_usage`).

---

## The headless SessionEnd gap

The FEAT-3155 spike verified (two runs) that under `qwen -p`:

- **Fire:** `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`
- **Does NOT fire:** `SessionEnd`

Consequences baked into the adapter design:

- The managed block installs at **project scope** (`.qwen/settings.json`) — the BUG-2921-style user-scope fallback is unnecessary because project-scope hooks fire headless.
- Headless session cleanup rides the `Stop` shim's legacy-script resolution instead of the `session_end` intent. Interactive sessions get the native `SessionEnd` sweep as well.

---

## Blockable events and exit semantics

Exit-code contract (Claude-compatible):

| Exit | Effect |
| --- | --- |
| `0` | Allow; stdout JSON parsed, `hookSpecificOutput.additionalContext` merged |
| `2` | Block; stderr is the reason shown to the user |
| other non-zero | **Fail-open** — non-blocking warning, stderr visible to the user |

Timeouts in Qwen settings are **milliseconds** (Claude uses seconds); the managed entries use 10000–30000.

---

## Where hooks are declared

1. **Managed `.qwen/settings.json` entries** (default, automation-grade) — `ll-init --hosts qwen` merges `ll:`-prefixed entries into the project's `.qwen/settings.json`. Structured JSON merge: other keys and third-party hook entries are preserved; upgrades remove-and-re-add exactly the `ll:` entries. Fires in both interactive and `-p` headless sessions.
2. **Native extension** — repo-root `qwen-extension.json` declares the same hooks **inline** with `${extensionPath}`-hydrated commands and Qwen-native matchers (`qwen extensions link .` for dev). Inline hooks take priority over file-based `hooks/hooks.json`.
3. **Marketplace conversion** (zero-artifact) — `qwen extensions install BrennonTWilliams/little-loops:ll` copies the Claude plugin's `hooks/hooks.json` verbatim: `*`-matcher events fire, but tool-specific matchers keep Claude names and never match. Not recommended; see the [Host Compatibility Matrix](../reference/HOST_COMPATIBILITY.md) footnote `[^qwenmarket]`.

Headless automation should always rely on route 1.

---

## See also

- [Getting Started](getting-started.md) — install and verification
- [Automation](automation.md) — orchestration CLIs under qwen
- [Host Compatibility Matrix](../reference/HOST_COMPATIBILITY.md) — authoritative parity reference
