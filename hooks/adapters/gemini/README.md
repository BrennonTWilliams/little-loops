# little-loops hook adapter — Gemini CLI

Thin transport shims wiring Gemini CLI lifecycle hooks to the host-agnostic
Python intent layer (`python -m little_loops.hooks <intent>`). Tracked under
EPIC-2178 (FEAT-2186); surface verified against gemini-cli 0.46.0 by the
FEAT-2179 spike (`thoughts/research/gemini-cli-surface.md`).

## Install route

`ll-init --hosts gemini` renders `hooks.json` (substituting
`{{LL_PLUGIN_ROOT}}` / `{{LL_GEN_VERSION}}`) and merges the entries into the
**project's** `.gemini/settings.json` via `install_gemini_adapter()` — a
structured JSON merge, never raw text injection (ARCHITECTURE-046 Option A,
same shape as the Qwen adapter). Managed entries are identified by their
`ll:`-prefixed `name` field and their `ll-gen:<version>` description stamp;
upgrade replaces exactly those entries and never touches other keys or
third-party hooks.

## Event → intent map

| Gemini event | Matcher | Shim | ll intent | Blocking? |
|---|---|---|---|---|
| SessionStart | `startup` | session-start.sh | `session_start` | Advisory only |
| PreCompress | — | pre-compact.sh | `pre_compact` | Advisory, async |
| BeforeAgent | — | prompt-submit.sh | `user_prompt_submit` | ✓ Blocking |
| BeforeTool | `.*` | pre-tool-use.sh | `pre_tool_use` | ✓ Blocking |
| AfterTool | `.*` | post-tool-use.sh | `post_tool_use` | ✓ Blocking |
| SessionEnd | — | session-end.sh | `session_end` | Best-effort |

Six events with no ll intent today (`AfterAgent`, `BeforeModel`,
`AfterModel`, `BeforeToolSelection`, `Notification`) are not wired by this
adapter — see the Event Mapping table in FEAT-2186 for the full 11-event
inventory.

## Payload-drift notes

Base payload keys match Claude Code (`session_id`, `transcript_path`, `cwd`,
`hook_event_name`, `timestamp`) — Gemini's hook I/O protocol is intentionally
Claude Code-compatible, down to a `CLAUDE_PROJECT_DIR` env-var alias for
`GEMINI_PROJECT_DIR`. `LLHookEvent.host` is populated from
`LL_HOOK_HOST=gemini`, exported by every shim before dispatch.

## Known host quirks (FEAT-2179)

- **SessionStart and PreCompress cannot block** — Gemini ignores the
  `continue`/`decision` output fields for these two events.
  `additionalContext` from `session_start`'s stdout is injected as the first
  history turn (interactive) or prepended to the prompt (headless).
- **SessionEnd is best-effort** — Gemini does not wait on it, so failures in
  `session-end.sh` must stay silent (matches the exit-0 posture of the other
  shims' error handling).
- Exit semantics match Claude Code: exit 0 = success, exit 2 = system block
  (stderr is the rejection reason sent to the agent), other = non-fatal
  warning.
- Timeouts are **milliseconds** in Gemini's `settings.json` (Claude uses
  seconds).
