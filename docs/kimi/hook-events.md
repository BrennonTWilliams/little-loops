# Kimi Code Hook Events

How Kimi Code CLI hook events map to little-loops hook intents. All mappings on this page were machine-verified on kimi **0.30.0** by the FEAT-2911 research spike (`thoughts/research/kimi-cli-surface.md`); the adapter landed as FEAT-2974 under EPIC-2910.

The adapter shims (`scripts/little_loops/hooks/adapters/kimi/*.sh`) are deliberately dumb: each exports `LL_HOOK_HOST=kimi-code`, pipes the stdin JSON payload to `python -m little_loops.hooks <intent>`, and exits with its status. All payload handling lives in the host-agnostic Python layer (`scripts/little_loops/hooks/`).

---

## Event → intent mapping

| Kimi event | little-loops intent | Notes |
| --- | --- | --- |
| `SessionStart` | `session_start` | Wired with matcher `startup`. `transcript_path` is absent from kimi's payload — the handler guards it (`or ""`), so transcript backfill skips gracefully |
| `PreCompact` | `pre_compact` | Wired with matcher `manual\|auto`. Kimi ignores return values for this event (advisory) |
| `UserPromptSubmit` | `user_prompt_submit` | **Blockable.** Payload drift handled — see below |
| `PreToolUse` | `pre_tool_use` | **Blockable.** `tool_name` / `tool_input` are compatible as-is |
| `PostToolUse` | `post_tool_use` | Payload drift handled — see below |
| `SessionEnd` | `session_end` | **Native event.** Claude Code needs a SessionStart-dispatch workaround here (upstream `SessionEnd` timeout bug, anthropics/claude-code#32712) — kimi does not |
| `SubagentStart` | `subagent_start` | Payload drift handled — see below |
| `SubagentStop` | `subagent_stop` | Payload drift handled — see below |
| `Stop` | — | Fires and payload-compatible (`stop_hook_active`), but **not wired** — no current consumer |
| `PostCompact` | — | Available in kimi; **(deferred)** — no adapter wiring yet (EPIC-2910 follow-up) |
| `PermissionRequest` / `PermissionResult` | — | Available in kimi; **(deferred)** — no adapter wiring yet (EPIC-2910 follow-up) |

Every payload carries the same snake_case base fields as Claude: `hook_event_name`, `session_id`, `cwd`.

---

## Payload drift (handled in the Python handlers)

Kimi's payload shapes drift from Claude's in four places. The shims stay dumb; the drift is absorbed by host-tolerant accessors in the intent handlers (FEAT-2974):

| Event | Kimi sends | Handler expects | Resolution |
| --- | --- | --- | --- |
| `UserPromptSubmit` | `prompt` = `[{"type":"text","text":"..."}]` (array of blocks) | a plain string | Handler joins block texts |
| `PostToolUse` | `tool_output` (string) | `tool_response` | Falls back to `tool_output`; `cache_hit` / `tool_call` are absent but already guarded |
| `SubagentStart` | `agent_name` | `agent_id` / `agent_type` | `agent_name` ≈ `agent_type`; no per-instance `agent_id` |
| `SubagentStop` | `agent_name`, `response` (full result text) | `agent_id`, `agent_type`, `agent_transcript_path` | No transcript path, but `response` carries the result inline |

---

## Blockable events and fail-open semantics

**Blockable set:** `PreToolUse`, `UserPromptSubmit`, `Stop` — the same blockable set as Claude Code.

Exit-code contract for hook commands:

| Exit | Effect |
| --- | --- |
| `0` | Allow; stdout may be appended to the session context |
| `2` | Block; stderr is shown as the reason |
| other non-zero | **Fail-open allow** — a crashing hook never blocks the tool path |

For blockable events, kimi also honors stdout JSON of the form `{"hookSpecificOutput":{"permissionDecision":"deny",...}}` as an alternative to exit 2. Hook timeouts are configurable per entry (1–600s); the little-loops shims use 30s. The hook's working directory is the session project dir.

---

## Where hooks are declared

1. **Managed `[[hooks]]` block** (default) — `ll-init --hosts kimi-code` installs a marker-delimited block into the **user-level** `$KIMI_CODE_HOME/config.toml` (default `~/.kimi-code/config.toml`). Entry fields: `event`, `matcher` (regex), `command`, `timeout`. Kimi has no project-local hook file, so this is the only ll-init target; see [Getting Started](getting-started.md#install). **This is the only route that fires in `kimi -p` print mode** (see caveats below), so automation setups should install it even when the plugin is present.
2. **Plugin manifest** — the `hooks` array of `kimi.plugin.json` (FEAT-2917) declares the same eight events with `./`-relative command paths. Plugin hooks run with cwd = plugin root and additionally receive `KIMI_CODE_HOME` and `KIMI_PLUGIN_ROOT` in the environment.

### Caveats verified on kimi 0.30.0 (BUG-2921)

- **Print mode does not fire plugin hooks.** `kimi -p` sessions do not load plugin-sourced hooks (config.toml `[[hooks]]` fire fine in print mode). Headless automation (`ll-auto` via `kimi -p`) therefore gets little-loops hooks only from the managed `[[hooks]]` block.
- **`/plugins info` renders no Hooks section** even when plugin hooks are loaded and firing — a display gap, not a failure. Verify firing via `.ll/history.db` `hook_events` instead.
- **Plugin hooks spawn with cwd = plugin root.** little-loops shims `cd` into the payload's `cwd` before dispatching, so config and telemetry always resolve against the *project's* `.ll/` (without this, telemetry lands in the managed plugin copy's database).

### Legacy `hooks/scripts/*.sh` are Claude-only

The legacy shell handlers under `hooks/scripts/` (e.g. `context-monitor.sh`) are registered through the Claude plugin's `hooks/hooks.json` only. They are **not** wired for kimi — all kimi hook handling goes through the in-package shims at `scripts/little_loops/hooks/adapters/kimi/`.

---

## See also

- [Getting Started](getting-started.md) — install, config probe, skill discovery
- [Automation](automation.md) — orchestration CLIs under kimi
- [Host Compatibility Matrix](../reference/HOST_COMPATIBILITY.md#hook-intents) — per-host intent parity
- [Kimi adapter source](../../scripts/little_loops/hooks/adapters/kimi/) — shims and the `hooks.toml` template
