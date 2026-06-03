# Codex CLI Adapter for little-loops Hook Intents

Thin Bash shim that lets [OpenAI Codex CLI](https://github.com/openai/codex)
delegate to the host-agnostic Python hook dispatcher in `little_loops.hooks`.
Mirrors the shape of the Claude Code shell adapter in `hooks/adapters/claude-code/`
— set `LL_HOOK_HOST=codex` in the subprocess environment, pipe the host event
payload as JSON to stdin, propagate stdout/stderr/exit-code back to Codex. No
logic lives in this adapter; it is purely a transport.

> **Runtime note**: Codex CLI is Rust-based and has **no** TypeScript/Bun
> plugin SDK. Codex hooks are language-agnostic shell commands invoked via
> `$SHELL -lc`. That is why this adapter follows the Bash pattern of
> `hooks/adapters/claude-code/`, **not** the TypeScript pattern of
> `hooks/adapters/opencode/`.

## Installation

`ll:init --codex` writes a `.codex/hooks.json` into the user's project from
the [`hooks.json`](./hooks.json) template, substituting `{{LL_PLUGIN_ROOT}}`
with the absolute path of the installed little-loops plugin. The user must
then accept the hook-trust dialog the next time they start Codex CLI.

Ensure `little_loops` is installed in the Python interpreter on `PATH`
(`pip install -e ./scripts`). The adapter resolves `python` from the ambient
`PATH`.

## Event → Intent Mapping (MVP)

| Codex event (`hooks.json` key) | ll intent       | Python invocation                              | Status     |
| ------------------------------ | --------------- | ---------------------------------------------- | ---------- |
| `SessionStart`                 | `session_start` | `python -m little_loops.hooks session_start`   | Implemented |
| `PreCompact`                   | `pre_compact`   | `python -m little_loops.hooks pre_compact`     | Implemented |
| `PostCompact`                  | —               | —                                              | Deferred — no concrete consumer in ll today; `pre_compact` performs all compact-time cleanup |
| `PreToolUse`                   | `pre_tool_use` (opt-in) | `python -m little_loops.hooks pre_tool_use`   | Opt-in — handler registered; not wired in `hooks.json` by default (FEAT-1489) |
| `PostToolUse`                  | `post_tool_use` | `python -m little_loops.hooks post_tool_use`   | Implemented (fire-and-forget via ≤5s timeout) |
| `UserPromptSubmit`             | `user_prompt_submit` | `python -m little_loops.hooks user_prompt_submit` | Implemented |
| `PermissionRequest`            | —               | —                                              | Deferred — hook can return `allow`/`deny`; no current consumer |
| `Stop`                         | —               | —                                              | Deferred |

This mapping conforms to the `LLHookEvent` contract introduced by
[FEAT-1116](../../../.issues/completed/) and reuses the same Python
dispatcher as the Claude Code and OpenCode adapters.

## SessionStart `matcher: "startup"`

The [`hooks.json`](./hooks.json) template restricts the SessionStart hook to
the `startup` source variant.

Codex's `SessionStart` event fires for three `source` values: `startup`,
`resume`, and `clear`. ll's `session_start.handle()` performs config load and
duplicate-ID emission keyed off a fresh session — firing on `resume` would
re-emit identifiers for an already-running session, and firing on `clear`
would re-run during in-session context resets. Restricting the matcher to
`startup` matches the semantics the Claude Code adapter already relies on.

## Host Identification

The adapter sets `LL_HOOK_HOST=codex` on the subprocess environment. The
Python dispatcher reads this env var to populate `LLHookEvent.host` so that
core handlers can branch on host-specific quirks if needed. Without this
var, the dispatcher defaults to `host="claude-code"`.

## Subprocess Contract

| Channel    | Direction        | Format                                                                          |
| ---------- | ---------------- | ------------------------------------------------------------------------------- |
| stdin      | adapter → python | Raw JSON dict — Codex's event payload (`hook_event_name`, `session_id`, `cwd`, `model`, `source`/`trigger`, `transcript_path`) |
| stdout     | python → adapter | For `session_start`: merged config JSON (Codex injects as `additionalContext`); empty for `pre_compact` |
| stderr     | python → adapter | Human-readable status/feedback lines (Codex shows these in the TUI status area) |
| exit code  | python → adapter | `0` = pass, `2` = block + inject feedback, `1` = unknown intent (hard error)    |
| cwd        | adapter inherits | Codex sets subprocess CWD to the session working directory (project root). Python handlers resolve `.codex/ll-config.json` (or `.ll/ll-config.json`) and write state files relative to it |

`pre_compact`'s success path is `exit_code=2` with feedback-only; the
adapter surfaces stderr to the Codex console but does not treat exit codes
`0` or `2` as failure.

### Blocking-Shim Pattern (`post-tool-use.sh`)

`post-tool-use.sh` follows the same 4-line blocking shim shape as its
siblings (`session-start.sh`, `pre-compact.sh`, `prompt-submit.sh`) — it
does **not** background the Python invocation with `&` / `disown`. The
handler (FEAT-1623) persists a single ``tool_events`` row per tool call
when ``analytics.enabled`` is set; latency stays well under the timeout
because:

1. A single-row SQLite INSERT (or an early return when analytics is
   disabled) keeps the handler well under 200ms p95.
2. A short (≤5s) `timeout` in `hooks.json` bounds the worst case if the
   session store is contended.

This keeps the adapter shell-script layer uniform: every script is a
blocking shim, every script is testable with the same sentinel-file
pattern in `scripts/tests/test_codex_adapter.py`. The blocking-with-short-
timeout approach was selected over `&`/`disown` because it avoids
introducing a backgrounded subprocess pattern that has no other
representative in the adapter layer.

### Opt-in: `PreToolUse`

`hooks.json` deliberately omits a `PreToolUse` entry for Codex. The Python
handler (`pre_tool_use`) now implements the learning-test discoverability gate
(FEAT-1742) and is **active by default for Claude Code** via
`hooks/adapters/claude-code/pre-tool-use.sh` (wired in `hooks/hooks.json` for
the `"Write|Edit"` matcher). For Codex users, opt in by adding the entry
manually:

```json
"PreToolUse": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "bash {{LL_PLUGIN_ROOT}}/hooks/adapters/codex/pre-tool-use.sh",
        "timeout": 5,
        "statusMessage": "Checking learning-test coverage..."
      }
    ]
  }
]
```

Then create `pre-tool-use.sh` as a sibling shim invoking the `pre_tool_use`
intent (same pattern as `post-tool-use.sh`). After the edit, Codex will prompt
for re-trust.

> **Codex non-zero exit semantics**: Codex logs a non-zero hook exit as
> `HookRunStatus::Failed` and continues the session. To deliberately abort
> a session from a hook, exit `0` and return `{"continue": false,
> "stopReason": "reason"}` on stdout as JSON. ll does not currently abort
> sessions from `session_start`.

## Trust Model

Codex hooks are subject to a per-project, per-handler trust model
(`codex-rs/hooks/src/engine/discovery.rs`). Each handler has one of four
statuses:

- `managed` — always runs (reserved for Codex-internal hooks).
- `trusted` — content hash matches the value stored in
  `~/.codex/config.toml` under `hooks.state.<key>.trusted_hash`. Runs.
- `modified` — content hash differs from the saved trusted hash. Codex
  prompts the user to re-trust on next startup.
- `untrusted` — no saved hash. Codex **silently skips** the hook (no error,
  no stderr) and shows a startup review dialog: "Review Hooks", "Trust All
  and Continue", or "Continue Without Trusting".

Key format used for the trust hash:
```
file:<absolute-path-to-hooks.json>:<event_snake_case>:<group_index>:<handler_index>
```
For ll the keys are:
```
file:<project>/.codex/hooks.json:session_start:0:0
file:<project>/.codex/hooks.json:pre_compact:0:0
file:<project>/.codex/hooks.json:user_prompt_submit:0:0
file:<project>/.codex/hooks.json:post_tool_use:0:0
```

The trusted hash lives in the **user-level** `~/.codex/config.toml`, not the
project's `.codex/config.toml`, so trust survives across `git clone` /
`rm -rf .codex/` cycles but is per-user.

### Trust-Hash Churn

Codex hashes the **command string** in `hooks.json` (the
`"command": "bash …/session-start.sh"` line), not the script body. So:

- Edits to **this script** (`session-start.sh` / `pre-compact.sh`) do
  **not** change the trust hash. The plugin can roll forward freely.
- Edits to **`.codex/hooks.json`** (path changes, timeout changes, matcher
  changes) **do** change the trust hash and prompt the user to re-trust on
  next startup.

To minimize churn for end users, keep the [`hooks.json`](./hooks.json)
template stable across releases and put any churning logic in the Python
`little_loops.hooks` package behind the stable
`python -m little_loops.hooks <intent>` subprocess interface.

## State Directory (`LL_STATE_DIR`)

When `LL_HOOK_HOST=codex`, the Python config resolver
(`resolve_config_path()` in `scripts/little_loops/config/core.py`) probes
`.codex/ll-config.json` **before** the default `.ll/ll-config.json` and
root-level `ll-config.json` candidates. This is the **only** state
redirection performed by the Codex adapter today.

Other state directories are **not** redirected by `LL_STATE_DIR=.codex`:

- `.loops/` (FSM run state)
- `.issues/` (issue tracking)
- `.loops/tmp/scratch/` (scratch pads)
- Any other directory rooted at the project root

If a future feature needs full per-host state redirection, file a separate
issue — do not silently expand `LL_STATE_DIR`'s reach here.

## Smoke Test

The Python-side integration test at
`scripts/tests/test_codex_adapter.py` exercises this adapter end-to-end via
`bash hooks/adapters/codex/session-start.sh` (and the sibling shims for
`pre-compact`, `prompt-submit`, `post-tool-use`). It is automatically
skipped if `bash` is not available on `PATH`.

## Related

- Parent epic: [FEAT-1116](../../../.issues/completed/) (hook-intent
  abstraction layer for multi-host support)
- Sibling adapter: [`hooks/adapters/claude-code/`](../claude-code/) (Bash
  shim, canonical template — the reference for this adapter)
- Sibling adapter: [`hooks/adapters/opencode/`](../opencode/) (TypeScript /
  Bun plugin — different runtime, same dispatcher contract)
- Tracking issue: FEAT-957
- Out of scope (tracked separately): orchestration CLI abstraction
  (FEAT-1462); slash-command and skill discovery for Codex — **Codex Skills
  API is confirmed stable** (`~/.codex/skills/`); see
  `thoughts/research/codex-command-discovery.md` (FEAT-1483), FEAT-1486
  (skill adaptation), FEAT-1487 (parity matrix update), and FEAT-1493
  (commands bridged to `skills/ll-<name>/` so `/ll:*` slash commands are
  also Codex-discoverable); PostCompact / hot-path intents
