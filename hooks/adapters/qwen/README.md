# little-loops hook adapter — Qwen Code

Thin transport shims wiring Qwen Code lifecycle hooks to the host-agnostic
Python intent layer (`python -m little_loops.hooks <intent>`). Tracked under
EPIC-3154 (FEAT-3158); surface verified against qwen 0.21.6 by the FEAT-3155
spike (`thoughts/research/qwen-code-surface.md`).

## Install route

`ll-init --hosts qwen` renders `settings-block.json` (substituting
`{{LL_PLUGIN_ROOT}}` / `{{LL_GEN_VERSION}}`) and merges the entries into the
**project's** `.qwen/settings.json` via `install_qwen_adapter()` — a
structured JSON merge, never raw text injection. Managed entries are
identified by their `ll:`-prefixed `name` field and their
`ll-gen:<version>` description stamp; upgrade replaces exactly those entries
and never touches other keys or third-party hooks. Project scope was
live-verified to fire under `qwen -p` headless (no BUG-2921-style fallback
to user scope needed).

## Event → intent map

| Qwen event | Matcher | Shim | ll intent |
|---|---|---|---|
| SessionStart | (all sources) | session-start.sh | `session_start` |
| SessionStart | (all sources) | drift-check.sh | `drift_check` |
| PreCompact | `manual\|auto` | pre-compact.sh | `pre_compact` |
| PreCompact | `manual\|auto` | precompact-handoff.sh | `pre_compact_handoff` |
| UserPromptSubmit | — | prompt-submit.sh | `user_prompt_submit` |
| PreToolUse | `write_file\|edit` | pre-tool-use.sh | `pre_tool_use` |
| PostToolUse | `.*` | post-tool-use.sh | `post_tool_use` |
| PostToolUse | `write_file\|edit` | edit-batch-nudge.sh | `edit_batch_nudge` |
| Stop | — | stop.sh | legacy scripts (see below) |
| SessionEnd | — | session-end.sh | `session_end` |
| SubagentStart | `.*` | subagent-start.sh | `subagent_start` |
| SubagentStop | `.*` | subagent-stop.sh | `subagent_stop` |

Matchers use **Qwen runtime tool ids** (`write_file`, `edit`,
`run_shell_command`) — Claude display names (`Write|Edit`, `Bash`) never
match on this host (verified by the FEAT-3155 marketplace-conversion probe).

## Payload-drift notes

Base payload keys match Claude Code (`session_id`, `transcript_path`, `cwd`,
`hook_event_name`, `timestamp`); Qwen adds `permission_mode`, `model`,
`source` (SessionStart), `prompt` (UserPromptSubmit), `tool_name` /
`tool_input` / `tool_use_id` / `tool_call_id` (PreToolUse),
`tool_response` (PostToolUse), and Stop telemetry (`stop_hook_active`,
`context_usage`, …). The host-tolerant payload accessors in the intent
handlers absorb field-level differences (same posture as Kimi).

## Known host quirks (FEAT-3155)

- **SessionEnd does not fire under `qwen -p` headless** (verified in two
  runs). The `session_end` intent covers interactive teardown; headless
  cleanup rides `stop.sh`, which runs the legacy
  `context-handoff-sentinel.sh` + `session-cleanup.sh` when
  `CLAUDE_PLUGIN_ROOT`/`LL_PLUGIN_ROOT` resolves to a checkout containing
  them (they are not wheel-packaged) and no-ops otherwise.
- Exit semantics match Claude Code: exit 0 = parse stdout JSON, exit 2 =
  block (stderr is the reason), other = non-blocking warning.
- Timeouts are **milliseconds** in Qwen settings (Claude uses seconds).
