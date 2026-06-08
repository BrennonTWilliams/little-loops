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
| `user_prompt_submit` | ✓           | (deferred)    | ✓             |
| `pre_tool_use`       | ✓ (active)[^hot] | (opt-in)[^hot] | (opt-in)[^hot] |
| `post_tool_use`      | ✓           | ✓ (fire-and-forget)[^hot] | ✓ (fire-and-forget)[^hot] |
| `stop` → `session_end` | ✓ (dispatched as `session_end`) | (deferred)    | (deferred)    |
| `post_compact`       | N/A         | N/A           | (deferred)[^postcompact] |
| `permission_request` | N/A         | N/A           | (deferred)    |

[^hot]: Hot-path intents (`pre_tool_use` / `post_tool_use`) fire on every
    tool invocation and require a latency budget. Research decision
    (FEAT-1488, `thoughts/research/hot-path-hook-intents.md`), executed
    by FEAT-1489 and extended by FEAT-1623:
    - `post_tool_use` is wired on all three hosts. Claude Code uses a
      blocking shim (`hooks/adapters/claude-code/post-tool-use.sh`) with a
      5s timeout (BUG-1881). OpenCode invokes `spawnIntent` without `await`
      (fire-and-forget). Codex uses a 4-line blocking shim with a 5s
      timeout. Per FEAT-1623 the handler persists per-tool
      byte metrics into `.ll/history.db` when `analytics.enabled` is set;
      a single-row INSERT (or the disabled-guard early return) keeps
      handler p95 well below the timeout. Failures are suppressed inside
      the handler so the host tool path is never disturbed.
    - `pre_tool_use` is **active for Claude Code**: wired via
      `hooks/adapters/claude-code/pre-tool-use.sh` for the `"Write|Edit"`
      matcher in `hooks/hooks.json` (FEAT-1742 learning-test discoverability
      gate). It remains opt-in for OpenCode (`tool.execute.before`) and
      Codex (`PreToolUse`) — see the adapter READMEs.
    - Measured cold-start p95 (OpenCode adapter, 30 sequential
      invocations on dev hardware): **≈10ms** for both `session_start`
      and `pre_compact`, well below the 200ms target. The
      `UnixSocketTransport` sidecar (viable if p95 ≥ 400ms) is not
      required and remains deferred.

[^postcompact]: Codex's `PostCompact` event has the same payload shape as
    `PreCompact`, but ll's existing `pre_compact` handler performs all
    compact-time cleanup *before* compaction. There is no concrete
    consumer for a post-compact intent in ll today.

## Slash-command and skill discovery

| Surface                  | Claude Code               | OpenCode                  | Codex CLI                 |
| ------------------------ | ------------------------- | ------------------------- | ------------------------- |
| Slash-command discovery  | ✓ `.claude/commands/*.md` | ✓ via plugin registration | ✓ — `commands/*.md` bridged to `skills/ll-<name>/SKILL.md` by `ll-adapt-skills-for-codex` (FEAT-1493)[^cmds] |
| Skill discovery          | ✓ `.claude/skills/*/SKILL.md` | ✓ via plugin registration | ✓ — `~/.codex/skills/<name>/SKILL.md`; all ll skills adapted by `ll-adapt-skills-for-codex` (FEAT-1486)[^cmds] |

[^cmds]: Codex has no `.codex/prompts/` slash-command path (that reference in
    prior footnotes was speculative — no such surface exists in the current
    Codex CLI). The extensibility surface is the **Skills API**
    (`~/.codex/skills/<name>/SKILL.md` + optional `agents/openai.yaml`);
    it covers both "commands" and "skills" in one mechanism. Research
    findings: `thoughts/research/codex-command-discovery.md` (FEAT-1483).
    Adaptation work: FEAT-1486 (add `name:` field + `agents/openai.yaml`
    to ll's `skills/*/SKILL.md`; landed) and FEAT-1493 (bridge
    `commands/*.md` to `skills/ll-<name>/` entries so `/ll:*` slash
    commands are discoverable from Codex; landed — every active command
    is now exposed).

    **`disable-model-invocation` flag scope:** `ll-adapt-skills-for-codex`
    does **not** read `disable-model-invocation: true`; all 16 SKILL.md files
    carrying that flag are exposed in Codex. The flag governs two other tools
    only: `ll-generate-skill-descriptions` (skips for token-budget compliance)
    and Claude Code's auto-invocation gate. See ENH-1497.

## Runner Capabilities

Runtime capabilities reported by `ll-doctor` for each host runner.

| Capability       | Claude Code | OpenCode | Codex CLI                          |
| ---------------- | ----------- | -------- | ---------------------------------- |
| Streaming        | ✓           | ✓        | ✓                                  |
| Permission skip  | ✓           | ✗        | ✗                                  |
| Agent selection  | ✓           | ✗        | partial (prompt injection)[^agent] |
| Tool allowlist   | ✓           | ✗        | ✗                                  |
| `json_schema`    | ✗           | ✗        | partial (file-mediated)[^schema]   |
| Token reporting  | ✓           | ✗[^tok]  | ✗[^tok]                            |

[^tok]: OpenCode and Codex CLI do not expose per-invocation token usage in their streaming output. The `on_usage_detailed` callback in `subprocess_utils.run_claude_command()` therefore fires only for `claude`-backed runs. Adapter work to surface usage from OpenCode/Codex is deferred (see EPIC-1744). Loops run under those hosts will produce no `usage.jsonl` file and no per-state cost table in `ll-loop run` output.

[^schema]: `CodexRunner.build_blocking_json` serializes the schema dict to a temp file and passes `--output-schema <path>` to Codex (ENH-1530). The temp file path is returned in `HostInvocation.cleanup_paths`; callers must call `p.unlink(missing_ok=True)` for each path after the subprocess completes. `ClaudeCodeRunner` has no schema flag and silently drops `json_schema`.

[^agent]: Codex agent selection works via `.codex/agents/*.toml` files generated
    by `ll-adapt-agents-for-codex --apply` (FEAT-1527). Interactive Codex TUI
    sessions can use `--agent <name>` (e.g., `--agent codebase-analyzer`) once
    those TOML files are present.

    **Programmatic prompt-injection workaround (ENH-1533)**: For ll's
    orchestration layer (`ll-auto`, `ll-parallel`, `ll-loop`),
    `CodexRunner.build_streaming(agent=…)` reads
    `.codex/agents/<name>.toml`, extracts `developer_instructions`, and
    prepends `[Persona: <name>]\n<instructions>\n\n---\n\n` to the prompt
    payload. When the TOML file (or its `developer_instructions` key) is
    absent, `CodexRunner` falls back to emitting `CapabilityNotSupported`
    plus a stderr notice that names the dropped agent and points users at
    `ll-adapt-agents-for-codex --apply`. `HostCapabilities.agent_select`
    stays `False` because there is still no native `--agent` CLI parity;
    `describe_capabilities()` reports `agent_select.status == "partial"`.

    **Permanent native-gap (ENH-1531)**: Research confirmed no CLI-level
    mechanism exists to select a named agent profile at `codex exec`
    invocation time. The `codex` CLI has no `--agent` flag; `CODEX_AGENT`
    and `CODEX_PROFILE` env-vars do not exist; the
    `agents.<name>.config_file` config stanza only governs `spawn_agent`
    subagent calls, not the root session's persona. The feature request is
    tracked at openai/codex#10067 (open, no linked PR). See
    `thoughts/research/codex-agent-selection.md` for full findings.

## Orchestration CLI

The orchestration tools (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-action`, `ll-loop`,
FSM evaluators, FSM handoff) route every host CLI invocation through
`scripts/little_loops/host_runner.py`. The `HostRunner` Protocol is
satisfied by four concrete runners — `ClaudeCodeRunner` (production),
`CodexRunner` (wired, auto-detects when `codex` is on PATH),
`OpenCodeRunner` (stub), and `PiRunner` (stub) — so adding a new host is
a matter of fleshing out the corresponding runner rather than touching
call sites.

| Tool                          | Claude Code | OpenCode      | Codex CLI    | Pi           |
| ----------------------------- | ----------- | ------------- | ------------ | ------------ |
| `ll-auto`                     | ✓           | stub[^orch]   | ✓            | stub[^orch]  |
| `ll-parallel`                 | ✓           | stub[^orch]   | ✓            | stub[^orch]  |
| `ll-action`                   | ✓           | stub[^orch]   | ✓            | stub[^orch]  |
| `ll-loop`                     | ✓           | stub[^orch]   | ✓            | stub[^orch]  |
| `ll-harness`                  | ✓           | stub[^orch]   | ✓            | stub[^orch]  |
| `ll-sprint`                   | ✓           | stub[^orch]   | ✓            | stub[^orch]  |
| FSM evaluators / handoff      | ✓           | stub[^orch]   | ✓            | stub[^orch]  |

[^orch]: All seven call sites now route through
    `scripts/little_loops/host_runner.py` (`HostRunner` Protocol +
    `ClaudeCodeRunner` + `CodexRunner` + `OpenCodeRunner` + `PiRunner`).
    Wiring a non-Claude host means registering a new `HostRunner`
    implementation; the orchestration layer no longer hard-codes the
    `claude` binary or its argv. **stub** = runner is registered so
    `LL_HOST_CLI=<host>` resolves, but every `build_*` raises
    `HostNotConfigured` until the host-specific argv is implemented
    (OpenCode: FEAT-1472 Option B; Pi: research deferred to FEAT-992).

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
| Session store (`SQLiteTransport`)   | `.ll/history.db` | `.ll/history.db` | `.ll/history.db` (same path)[^state] |

[^state]: FEAT-957 deliberately scopes `LL_STATE_DIR=.codex` to the
    config probe only. Other state directories remain at their default
    paths regardless of host. If a future feature needs full per-host
    state redirection, file a separate issue — do not silently expand
    `LL_STATE_DIR`'s reach.

## Installation

| Action                              | Claude Code                   | OpenCode                                 | Codex CLI                                |
| ----------------------------------- | ----------------------------- | ---------------------------------------- | ---------------------------------------- |
| Install command                     | Plugin auto-enables           | `bun install` under `hooks/adapters/opencode/` | `ll-init --hosts codex` writes `.codex/hooks.json` |
| Trust prompt on first run           | N/A (plugin trust model)      | N/A                                      | **Yes** — Codex shows a hook-trust dialog; user must "Trust All" or "Review Hooks" before hooks fire |
| Host identification env var         | (default, no var needed)      | `LL_HOOK_HOST=opencode`                  | `LL_HOOK_HOST=codex`                     |
| Adapter runtime                     | Bash + Python                 | TypeScript / Bun + Python                | Bash + Python                            |

## Environment variables

| Env var          | Description |
| ---------------- | ----------- |
| `LL_HOST_CLI`    | Override host runner selection (`claude-code`, `codex`, `opencode`, `pi`). Takes precedence over binary probe and `orchestration.host_cli` config. |
| `LL_HOOK_HOST`   | Identify the host to hook adapters (`claude-code`, `opencode`, `codex`). Set by each adapter before invoking the Python hook layer. |
| `LL_STATE_DIR`   | Scope config probe to a host-specific directory (e.g. `.codex`). Affects config resolution only — other state paths are unaffected (see [^state]). |
| `LL_HISTORY_DB`  | Override the default `.ll/history.db` session-store path (e.g. for test isolation). |

## Adapter locations

- Claude Code: [`hooks/adapters/claude-code/`](../../hooks/adapters/claude-code/) — Bash shim
- OpenCode: [`hooks/adapters/opencode/`](../../hooks/adapters/opencode/) — TypeScript/Bun plugin
- Codex CLI: [`hooks/adapters/codex/`](../../hooks/adapters/codex/) — Bash shim with `matcher: "startup"`

Each adapter is a thin transport (`spawn → set env → pipe stdin → exit`);
all real logic lives in `scripts/little_loops/hooks/`.

## Runnable Capability Check

To verify which little-loops features your active host CLI supports, run:

```bash
ll-doctor          # human-readable ✓/○/✗ table
ll-doctor --json   # machine-readable CapabilityReport
```

`ll-doctor` probes the active host binary and prints a `CapabilityReport` with one entry per capability (streaming, permission skip, agent selection, tool allowlist) and per registered hook event. It also prints an "Analytics Capture" section reporting the current `analytics.capture` config state (enabled/disabled per category). Exits non-zero if any capability is unsupported. See [`docs/reference/API.md#capabilityreport`](API.md#capabilityreport) for the data model.

## User onboarding

For a user-facing walkthrough of Codex CLI setup and usage, see:

- [`docs/codex/README.md`](../codex/README.md) — what works, what is deferred, quick orientation
- [`docs/codex/getting-started.md`](../codex/getting-started.md) — install, trust prompt, config file, skill discovery
- [`docs/codex/usage.md`](../codex/usage.md) — orchestration CLIs, skill invocation, current limitations

This matrix is the authoritative parity reference; the Codex docs above are the user-facing onboarding entry point.

## Tracking issues

- **FEAT-957** — Codex CLI plugin compatibility (this matrix's Codex column).
- **FEAT-1462** — Abstract host CLI invocation in orchestration layer
  (resolves the orchestration ✗ cells above).
- **FEAT-1463** — Umbrella epic for deferred Codex interop gaps.
- **FEAT-1483** — Research spike: Codex slash-command and skill discovery
  (confirmed Skills API stable; see `thoughts/research/codex-command-discovery.md`).
- **FEAT-1486** — Adapt `skills/*/SKILL.md` for Codex Skills API (resolves
  the Skill discovery ✗ cell).
- **FEAT-1487** — Update parity matrix and footnote for Codex slash-command gap.
- **FEAT-992** — Raspberry Pi compatibility (deferred — will add a Pi
  column once the Pi plugin API research is done).
- **FEAT-1488** — Research spike: sidecar/IPC for hot-path intents on
  non-Claude-Code hosts (completed — decision: opt-in-only + fire-and-forget
  `post_tool_use`; sidecar deferred until benchmark; see
  `thoughts/research/hot-path-hook-intents.md`).
- **FEAT-1489** — Wire `post_tool_use` for Codex and OpenCode (fire-and-forget);
  create benchmark script; wire `pre_tool_use` if benchmark clears 200ms threshold.
