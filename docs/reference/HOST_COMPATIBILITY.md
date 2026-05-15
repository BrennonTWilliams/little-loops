# Host Compatibility Matrix

little-loops integrates with multiple coding-agent host CLIs. This page is
the authoritative parity matrix — what is wired where, and which gaps are
tracked by which open issues.

Status legend:

- **✓** — wired and verified
- **✗** — not wired (see footnote for tracking issue)
- **N/A** — not applicable to this host
- **(deferred)** — implementable but no current consumer

## Hook intents

Hook intents are dispatched through the host-agnostic Python layer at
`scripts/little_loops/hooks/` (FEAT-1116). Each host adapter sits under
`hooks/adapters/<host>/` and translates the host's native hook protocol
into `LLHookEvent` payloads.

| Hook intent          | Claude Code | OpenCode      | Codex CLI     |
| -------------------- | ----------- | ------------- | ------------- |
| `session_start`      | ✓           | ✓             | ✓ (matcher=`startup`) |
| `pre_compact`        | ✓           | ✓             | ✓             |
| `user_prompt_submit` | ✓           | (deferred)    | (deferred)    |
| `pre_tool_use`       | ✓           | (deferred)[^hot] | (deferred)[^hot] |
| `post_tool_use`      | ✓           | (deferred)[^hot] | (deferred)[^hot] |
| `stop`               | ✓           | (deferred)    | (deferred)    |
| `post_compact`       | N/A         | N/A           | (deferred)[^postcompact] |
| `permission_request` | N/A         | N/A           | (deferred)    |

[^hot]: Hot-path intents (`pre_tool_use` / `post_tool_use`) fire on every
    tool invocation and require a latency budget. The OpenCode adapter
    defers these until a sidecar approach is benchmarked; the Codex
    adapter inherits the same constraint.

[^postcompact]: Codex's `PostCompact` event has the same payload shape as
    `PreCompact`, but ll's existing `pre_compact` handler performs all
    compact-time cleanup *before* compaction. There is no concrete
    consumer for a post-compact intent in ll today.

## Slash-command and skill discovery

| Surface                  | Claude Code               | OpenCode                  | Codex CLI                 |
| ------------------------ | ------------------------- | ------------------------- | ------------------------- |
| Slash-command discovery  | ✓ `.claude/commands/*.md` | ✓ via plugin registration | ✗ — Codex reads `.codex/prompts/`[^cmds] |
| Skill discovery          | ✓ `.claude/skills/*/SKILL.md` | ✓ via plugin registration | ✗ — no known mirror path[^cmds] |

[^cmds]: Codex command/skill discovery is out of scope for FEAT-957
    (the Codex hook adapter). File a separate issue if user demand for
    Codex slash-commands surfaces — the mechanical work is either a
    template-render of `.claude/commands/*.md` into `.codex/prompts/` or
    a runtime adapter, both of which depend on Codex's command format.

## Orchestration CLI

The orchestration tools (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`,
FSM evaluators, FSM handoff) route every host CLI invocation through
`scripts/little_loops/host_runner.py`. The `HostRunner` Protocol is
satisfied by four concrete runners — `ClaudeCodeRunner` (production),
`CodexRunner` (wired, gated behind `LL_HOST_CLI=codex` until validated),
`OpenCodeRunner` (stub), and `PiRunner` (stub) — so adding a new host is
a matter of fleshing out the corresponding runner rather than touching
call sites.

| Tool                          | Claude Code | OpenCode      | Codex CLI    | Pi           |
| ----------------------------- | ----------- | ------------- | ------------ | ------------ |
| `ll-auto`                     | ✓           | stub[^orch]   | gated[^orch] | stub[^orch]  |
| `ll-parallel`                 | ✓           | stub[^orch]   | gated[^orch] | stub[^orch]  |
| `ll-action`                   | ✓           | stub[^orch]   | gated[^orch] | stub[^orch]  |
| `ll-loop`                     | ✓           | stub[^orch]   | gated[^orch] | stub[^orch]  |
| FSM evaluators / handoff      | ✓           | stub[^orch]   | gated[^orch] | stub[^orch]  |

[^orch]: All six call sites now route through
    `scripts/little_loops/host_runner.py` (`HostRunner` Protocol +
    `ClaudeCodeRunner` + `CodexRunner` + `OpenCodeRunner` + `PiRunner`).
    Wiring a non-Claude host means registering a new `HostRunner`
    implementation; the orchestration layer no longer hard-codes the
    `claude` binary or its argv. **stub** = runner is registered so
    `LL_HOST_CLI=<host>` resolves, but every `build_*` raises
    `HostNotConfigured` until the host-specific argv is implemented
    (OpenCode: FEAT-1472 Option B; Pi: research deferred to FEAT-992).
    **gated** = runner is fully implemented but deliberately omitted
    from `_PROBE_ORDER`; opt in with `LL_HOST_CLI=codex` (FEAT-1465).

## Config probe path

Resolved by `resolve_config_path()` in
`scripts/little_loops/config/core.py`. The probe order depends on
`LL_HOOK_HOST` (and the alternate `LL_STATE_DIR` trigger for Codex).

| Host        | Probe order                                                                              |
| ----------- | ---------------------------------------------------------------------------------------- |
| Claude Code | `.ll/ll-config.json` → root-level `ll-config.json`                                       |
| OpenCode    | `.ll/ll-config.json` → root-level `ll-config.json` (same as default)                     |
| Codex CLI   | `.codex/ll-config.json` → `.ll/ll-config.json` → root-level `ll-config.json`             |

The Codex order is triggered by either `LL_HOOK_HOST=codex` or
`LL_STATE_DIR=.codex` in the environment. The Codex adapter sets the
former; users can set the latter manually to force Codex probe order
without invoking the adapter.

## State directory

| State surface                       | Claude Code | OpenCode | Codex CLI |
| ----------------------------------- | ----------- | -------- | --------- |
| Config file                         | `.ll/`      | `.ll/`   | `.codex/` (first) then `.ll/` |
| Issue tracking (`.issues/`)         | `.issues/`  | `.issues/` | `.issues/` (same path)[^state] |
| FSM runs (`.loops/`)                | `.loops/`   | `.loops/` | `.loops/` (same path)[^state] |
| Scratch pads (`.loops/tmp/scratch/`) | `.loops/tmp/scratch/` | `.loops/tmp/scratch/` | `.loops/tmp/scratch/` (same path)[^state] |
| Continuation prompt                 | `.ll/ll-continue-prompt.md` | `.ll/ll-continue-prompt.md` | `.ll/ll-continue-prompt.md` (same path)[^state] |

[^state]: FEAT-957 deliberately scopes `LL_STATE_DIR=.codex` to the
    config probe only. Other state directories remain at their default
    paths regardless of host. If a future feature needs full per-host
    state redirection, file a separate issue — do not silently expand
    `LL_STATE_DIR`'s reach.

## Installation

| Action                              | Claude Code                   | OpenCode                                 | Codex CLI                                |
| ----------------------------------- | ----------------------------- | ---------------------------------------- | ---------------------------------------- |
| Install command                     | Plugin auto-enables           | `bun install` under `hooks/adapters/opencode/` | `/ll:init --codex` writes `.codex/hooks.json` |
| Trust prompt on first run           | N/A (plugin trust model)      | N/A                                      | **Yes** — Codex shows a hook-trust dialog; user must "Trust All" or "Review Hooks" before hooks fire |
| Host identification env var         | (default, no var needed)      | `LL_HOOK_HOST=opencode`                  | `LL_HOOK_HOST=codex`                     |
| Adapter runtime                     | Bash + Python                 | TypeScript / Bun + Python                | Bash + Python                            |

## Adapter locations

- Claude Code: [`hooks/adapters/claude-code/`](../../hooks/adapters/claude-code/) — Bash shim
- OpenCode: [`hooks/adapters/opencode/`](../../hooks/adapters/opencode/) — TypeScript/Bun plugin
- Codex CLI: [`hooks/adapters/codex/`](../../hooks/adapters/codex/) — Bash shim with `matcher: "startup"`

Each adapter is a thin transport (`spawn → set env → pipe stdin → exit`);
all real logic lives in `scripts/little_loops/hooks/`.

## Tracking issues

- **FEAT-957** — Codex CLI plugin compatibility (this matrix's Codex column).
- **FEAT-1462** — Abstract host CLI invocation in orchestration layer
  (resolves the orchestration ✗ cells above).
- **FEAT-992** — Raspberry Pi compatibility (deferred — will add a Pi
  column once the Pi plugin API research is done).
