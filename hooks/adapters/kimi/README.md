# Kimi Code Adapter for little-loops Hook Intents

Thin Bash shims that let [Kimi Code CLI](https://www.kimi.com/code/docs/en/)
delegate to the host-agnostic Python hook dispatcher in `little_loops.hooks`.
Mirrors the shape of the Codex adapter in
[`scripts/little_loops/hooks/adapters/codex/`](../../../scripts/little_loops/hooks/adapters/codex/)
— set `LL_HOOK_HOST=kimi-code` in the subprocess environment, pipe the host
event payload as JSON to stdin, propagate stdout/stderr/exit-code back to
Kimi. No logic lives in this adapter; it is purely a transport.

> **Runtime note**: Kimi hooks are language-agnostic shell commands declared
> in `[[hooks]]` arrays of `$KIMI_CODE_HOME/config.toml` (or a plugin
> manifest's `hooks` array), invoked with the event payload on stdin. That is
> why this adapter follows the Bash pattern of `hooks/adapters/claude-code/`,
> **not** the TypeScript pattern of `hooks/adapters/opencode/`.

## Installation

`ll-init --hosts kimi-code` reads the
[`hooks.toml`](../../../scripts/little_loops/hooks/adapters/kimi/hooks.toml)
template, substitutes `{{LL_PLUGIN_ROOT}}` with the absolute path of the
installed little-loops package, and inserts the result as a
**marker-delimited managed block** in `$KIMI_CODE_HOME/config.toml`
(default `~/.kimi-code/config.toml`, honoring the `KIMI_CODE_HOME` env var):

```
# >>> little-loops kimi hooks (managed, do not edit)
...rendered [[hooks]] entries...
# <<< little-loops kimi hooks
```

Re-running `ll-init` replaces the block in place when the embedded
`# ll-gen-version:` stamp diverges from the installed package (the update
path); content outside the markers is never touched. Hooks take effect in
new Kimi sessions.

Ensure `little_loops` is installed in the Python interpreter on `PATH`
(`pip install -e ./scripts`). The adapter resolves `python` from the ambient
`PATH`.

### Plugin-manifest alternative

Kimi also loads hooks from a plugin manifest's `hooks` array. little-loops
ships a `kimi.plugin.json` manifest for the per-repo install route
(`/plugins install <path>` copies the plugin to
`$KIMI_CODE_HOME/plugins/managed/ll/`), which provides the true `/ll:<name>`
slash-command namespace in addition to hooks. Plugin hooks run with
cwd = plugin root and may use `./`-relative command paths. See FEAT-2917
and `thoughts/research/kimi-cli-surface.md` §Q6.

## Event → Intent Mapping

| Kimi event (`[[hooks]].event`) | ll intent            | Python invocation                                | Notes |
| ------------------------------ | -------------------- | ------------------------------------------------ | ----- |
| `SessionStart`                 | `session_start`      | `python -m little_loops.hooks session_start`     | `matcher = "startup"` only (see below) |
| `PreCompact`                   | `pre_compact`        | `python -m little_loops.hooks pre_compact`       | `matcher = "manual\|auto"`; Kimi ignores PreCompact return values |
| `UserPromptSubmit`             | `user_prompt_submit` | `python -m little_loops.hooks user_prompt_submit` | Blockable |
| `PreToolUse`                   | `pre_tool_use`       | `python -m little_loops.hooks pre_tool_use`      | No matcher = all tools; blockable |
| `PostToolUse`                  | `post_tool_use`      | `python -m little_loops.hooks post_tool_use`     | No matcher = all tools; fire-and-forget (≤30s timeout) |
| `SessionEnd`                   | `session_end`        | `python -m little_loops.hooks session_end`       | **Native** SessionEnd (contrast Claude Code, where `session_end` is dispatched from SessionStart due to an upstream bug) |
| `SubagentStart`                | `subagent_start`     | `python -m little_loops.hooks subagent_start`    | Fire-and-forget telemetry |
| `SubagentStop`                 | `subagent_stop`      | `python -m little_loops.hooks subagent_stop`     | Fire-and-forget telemetry |

This mapping conforms to the `LLHookEvent` contract introduced by
[FEAT-1116](../../../.issues/features/P3-FEAT-1116-hook-intent-abstraction-layer.md)
and reuses the same Python dispatcher as the Claude Code, Codex, and
OpenCode adapters. Eight wired intents — the best non-Claude parity yet
(Codex wires four).

## SessionStart `matcher: "startup"`

The [`hooks.toml`](../../../scripts/little_loops/hooks/adapters/kimi/hooks.toml)
template restricts the SessionStart hook to the `startup` source variant —
the same policy the Codex adapter applies. Firing on `resume` would re-emit
identifiers for an already-running session; `session_start.handle()`
performs config load and duplicate-ID emission keyed off a fresh session.

## Host Identification

The adapter sets `LL_HOOK_HOST=kimi-code` on the subprocess environment. The
Python dispatcher reads this env var to populate `LLHookEvent.host` so that
core handlers can branch on host-specific quirks if needed. Without this
var, the dispatcher defaults to `host="claude-code"`.

## Subprocess Contract

| Channel    | Direction        | Format                                                                          |
| ---------- | ---------------- | ------------------------------------------------------------------------------- |
| stdin      | adapter → python | Raw JSON dict — Kimi's event payload (base fields `hook_event_name`, `session_id`, `cwd` on every event) |
| stdout     | python → adapter | For `session_start`: merged config JSON (Kimi appends stdout to the session context); empty for most other intents |
| stderr     | python → adapter | Human-readable status/feedback lines; on exit 2 for a blockable event, stderr is the block reason shown to the user |
| exit code  | python → adapter | `0` = allow (stdout may be appended to context), `2` = block (blockable events only), other non-zero = **fail-open allow** (Kimi logs and continues) |
| cwd        | adapter inherits | Kimi sets the subprocess CWD to the session working directory (project root). Python handlers resolve `.kimi-code/ll-config.json` (or `.ll/ll-config.json`) and write state files relative to it |

### Exit-code semantics (fail-open)

Unlike Claude Code, any non-zero exit other than `2` is **fail-open**: Kimi
logs the hook failure and allows the action. Deliberate blocking is only
possible on the blockable set — `PreToolUse`, `UserPromptSubmit`, `Stop` —
via exit `2` (stderr = reason) or a stdout JSON
`{"hookSpecificOutput":{"permissionDecision":"deny",...}}`. This is the same
blockable set as Claude Code.

## Kimi Quirks

- **No project-local hook file.** Hooks load ONLY from
  `$KIMI_CODE_HOME/config.toml` `[[hooks]]` arrays or a plugin manifest's
  `hooks` array. `.kimi-code/local.toml` exists but supports only
  `[workspace]`. That is why `ll-init` installs the managed block at user
  level rather than into the project.
- **User-level install.** The managed block in `$KIMI_CODE_HOME/config.toml`
  is shared across all projects for the user; the shims dispatch on the
  session cwd, so per-project ll config (`.kimi-code/ll-config.json` /
  `.ll/ll-config.json`) still applies.
- **Payload drift vs Claude Code** (verified on kimi 0.30.0; see
  `thoughts/research/kimi-cli-surface.md` §Q3). Handled by host-tolerant
  accessors in the Python handlers (FEAT-2915) — the shims stay dumb:

  | Event | Kimi sends | Claude sends | Handler tolerance |
  |---|---|---|---|
  | SessionStart | no `transcript_path` | `transcript_path` | already optional-guarded (`session_start.py`) |
  | UserPromptSubmit | `prompt` = `[{"type":"text","text":...}]` (array) | `prompt` = string | `user_prompt_submit.py` joins block texts |
  | PostToolUse | `tool_output` (string); no `cache_hit`/`tool_call` | `tool_response` (dict) + `cache_hit` | `post_tool_use.py` falls back to `tool_output`; absent keys default |
  | SubagentStart | `agent_name` (the type), no `agent_id` | `agent_id` + `agent_type` | `subagent_start.py` falls back to `agent_name` |
  | SubagentStop | `agent_name` + `response` (full text) | `agent_id` + `agent_type` + `agent_transcript_path` | `subagent_stop.py` falls back; `response` surfaced via the transcript field |
  | SessionEnd | `reason` (native event) | dispatched from SessionStart (upstream bug) | compatible as-is |

  Because Kimi sends no per-instance `agent_id`, `subagent_runs` rows are a
  silent no-op for Kimi today (the writers no-op on a missing `agent_id`) —
  the `agent_type` fallback is in place so that changes if Kimi adds one.

## State Directory (`LL_HOOK_HOST=kimi-code`)

When `LL_HOOK_HOST=kimi-code`, the Python config resolver
(`resolve_config_path()` in `scripts/little_loops/config/core.py`, ENH-2913)
probes `.kimi-code/ll-config.json` **before** the default `.ll/ll-config.json`
and root-level `ll-config.json` candidates — same pattern as the Codex
adapter's `.codex/` probe. No other state directories are redirected.

## Smoke Test

The Python-side integration test at
`scripts/tests/test_kimi_adapter.py` exercises this adapter end-to-end via
`bash scripts/little_loops/hooks/adapters/kimi/session-start.sh` (and the
sibling shims). It is automatically skipped if `bash` is not available on
`PATH`.

## Related

- Parent epic: [FEAT-1116](../../../.issues/features/P3-FEAT-1116-hook-intent-abstraction-layer.md) (hook-intent
  abstraction layer for multi-host support); EPIC-2910 (Kimi Code host support)
- Research spike: `thoughts/research/kimi-cli-surface.md` (FEAT-2911 —
  verified kimi 0.30.0 hook payloads and event surface)
- Sibling adapter: [`hooks/adapters/claude-code/`](../claude-code/) (Bash
  shim, canonical template — the reference for this adapter)
- Sibling adapter: Codex (Bash shims in
  [`scripts/little_loops/hooks/adapters/codex/`](../../../scripts/little_loops/hooks/adapters/codex/),
  contract doc at [`hooks/adapters/codex/README.md`](../codex/README.md)) —
  the pattern this adapter follows
- Tracking issue: FEAT-2915
