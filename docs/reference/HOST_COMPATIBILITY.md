# Host Compatibility Matrix

> **Last Updated: 2026-06-25** — update this date whenever a matrix cell changes status.

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

| Hook intent          | Claude Code | OpenCode      | Codex CLI     | Gemini CLI    |
| -------------------- | ----------- | ------------- | ------------- | ------------- |
| `session_start`      | ✓           | ✓             | ✓ (matcher=`startup`) | (deferred)[^gemini] — `SessionStart`; advisory only |
| `pre_compact`        | ✓           | ✓             | ✓             | (deferred)[^gemini] — `PreCompress`; advisory, async |
| `user_prompt_submit` | ✓           | (deferred)    | ✓             | (deferred)[^gemini] — `BeforeAgent` |
| `pre_tool_use`       | ✓ (active)[^hot] | (opt-in)[^hot] | (opt-in)[^hot] | (deferred)[^gemini] — `BeforeTool` |
| `post_tool_use`      | ✓           | ✓ (fire-and-forget)[^hot] | ✓ (fire-and-forget)[^hot] | (deferred)[^gemini] — `AfterTool` |
| `stop` → `session_end` | ✓ (dispatched as `session_end`) | (deferred)    | (deferred)    | (deferred)[^gemini] — `SessionEnd`; best-effort |
| `post_compact`       | N/A         | N/A           | (deferred)[^postcompact] | N/A — no equivalent |
| `permission_request` | N/A         | N/A           | (deferred)[^permreq] | N/A — `Notification` hook is observability-only |

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

[^permreq]: Codex exposes a `permission_request` event when a tool requires
    user approval. The original tracking issue (FEAT-1720) was **cancelled**
    and its scope absorbed into **FEAT-1719**, which now wires both
    `PostCompact` and `PermissionRequest` no-op handlers in one pass. Deferred
    until a concrete consumer exists; the cell flips to ✓ when FEAT-1719 lands.

[^gemini]: Gemini CLI (`gemini` binary, npm `@google/gemini-cli`) support is
    tracked by **EPIC-2178**. Research spike **FEAT-2179** (2026-06-15) confirmed
    all three research questions — binary surface, hook model, plugin discovery —
    have definitive answers. No unknowns remain; implementation work is gated on
    child issues of EPIC-2178. Research artifact:
    `thoughts/research/gemini-cli-surface.md`. Key findings: `-p`/`--prompt` headless
    mode and `--output-format stream-json` flags are **identical to Claude Code**;
    hook I/O protocol (stdin/stdout JSON) is compatible; `CLAUDE_PROJECT_DIR` env
    var alias is provided by Gemini for Claude Code compatibility; `gemini hooks
    migrate --from-claude` command exists. Cells flip from `(deferred)` to ✓ as
    EPIC-2178 children land.

## Slash-command and skill discovery

| Surface                  | Claude Code               | OpenCode                  | Codex CLI                 | Gemini CLI                |
| ------------------------ | ------------------------- | ------------------------- | ------------------------- | ------------------------- |
| Slash-command discovery  | ✓ `.claude/commands/*.md` | ✓ via plugin registration | ✓ — `commands/*.md` bridged to `skills/ll-<name>/SKILL.md` by `ll-adapt-skills-for-codex` (FEAT-1493)[^cmds] | (deferred)[^gemini] — `.gemini/commands/*.toml`; TOML format; bridge script needed |
| Skill discovery          | ✓ `.claude/skills/*/SKILL.md` | ✓ via plugin registration | ✓ — `~/.codex/skills/<name>/SKILL.md`; all ll skills adapted by `ll-adapt-skills-for-codex` (FEAT-1486)[^cmds] | (deferred)[^gemini] — `.gemini/skills/<name>/SKILL.md`; compatible format; minor adaptation (add `name:`) |

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

| Capability       | Claude Code | OpenCode | Codex CLI                          | Gemini CLI                         |
| ---------------- | ----------- | -------- | ---------------------------------- | ---------------------------------- |
| Streaming        | ✓           | ✓        | ✓                                  | ✓ (`-o stream-json`)[^gemini]      |
| Permission skip  | ✓           | ✗        | ✗[^runnercap]                      | ✓ (`--approval-mode=yolo`)[^gemini] |
| Agent selection  | ✓           | ✗        | partial (subagents)[^agent]        | ✗ — skills activate implicitly; no `--agent` flag[^gemini] |
| Tool allowlist   | ✓           | ✗        | ✗[^runnercap]                      | ✗ — Policy Engine (TOML); not a simple flag[^gemini] |
| `json_schema`    | ✗           | ✗        | partial (file-mediated)[^schema]   | ✗[^gemini]                         |
| Token reporting  | ✓           | ✗[^tok]  | ✗[^tok]                            | ✗[^gemini]                         |

[^tok]: OpenCode and Codex CLI do not expose per-invocation token usage in their streaming output. The `on_usage_detailed` callback in `subprocess_utils.run_claude_command()` therefore fires only for `claude`-backed runs. Adapter work to surface usage from OpenCode/Codex is tracked by **FEAT-2123**. Loops run under those hosts will produce no `usage.jsonl` file and no per-state cost table in `ll-loop run` output.

[^runnercap]: `permission skip` and `tool allowlist` are reported `✗` by `ll-doctor`
    for both OpenCode and Codex. Whether these have native Codex equivalents
    (e.g., `sandbox_mode`/approval policy for permission skip; per-agent
    `mcp_servers`/`skills.config` scoping for tool allowlist) is unresearched —
    the cells were never backed by a tracking issue. **ENH-2124** produces that
    research note and either wires the capability or marks it a documented
    permanent gap.

[^schema]: `CodexRunner.build_blocking_json` serializes the schema dict to a temp file and passes `--output-schema <path>` to Codex (ENH-1530). The temp file path is returned in `HostInvocation.cleanup_paths`; callers must call `p.unlink(missing_ok=True)` for each path after the subprocess completes. `ClaudeCodeRunner` has no schema flag and silently drops `json_schema`.

[^agent]: **Codex has first-class custom agents — "subagents".** They are
    defined as TOML files in `~/.codex/agents/` (personal) or `.codex/agents/`
    (project), with required fields `name`, `description`,
    `developer_instructions` and optional `model`, `model_reasoning_effort`,
    `sandbox_mode`, `mcp_servers`, `skills.config`, `nickname_candidates`
    (see <https://developers.openai.com/codex/subagents>). ll generates these
    via `ll-adapt-agents-for-codex --apply` (FEAT-1527).

    **Spawn-based, not flag-based.** Codex's agent model differs from Claude
    Code's: agents are *spawned from within a session* (in-session prompt,
    the `spawn_agents_on_csv` batch tool, or `/agent` to switch threads),
    governed by `[agents]` config (`max_threads`, `max_depth`). Per the docs,
    "Codex only spawns a new agent when you explicitly ask it to do so."
    There is **no startup CLI flag** to assign the *root* `codex exec` session
    a named persona — `--agent`, `CODEX_AGENT`, and `CODEX_PROFILE` do not
    exist (openai/codex#10067 requests one; a minor ergonomic ask, not a
    parity blocker). The cell reads **partial** for this one reason only.

    **Root-session persona via prompt-injection (ENH-1533)**: For ll's
    orchestration layer (`ll-auto`, `ll-parallel`, `ll-loop`),
    `CodexRunner.build_streaming(agent=…)` reads `.codex/agents/<name>.toml`,
    extracts `developer_instructions`, and prepends
    `[Persona: <name>]\n<instructions>\n\n---\n\n` to the prompt payload —
    covering the one case Codex's spawn-based model does not. When the TOML
    file (or its `developer_instructions` key) is absent, `CodexRunner` emits
    `CapabilityNotSupported` plus a stderr notice pointing at
    `ll-adapt-agents-for-codex --apply`. `describe_capabilities()` reports
    `agent_select.status == "partial"`.

    **Follow-ups:** the adapter currently emits only `name`/`description`/
    `model`/`developer_instructions` and drops the richer Codex fields
    (**ENH-2121**); ll does not yet exploit the native `spawn_agents_on_csv`
    batch model, which maps onto `ll-parallel`'s per-issue fan-out
    (**FEAT-2122**). See `thoughts/research/codex-agent-selection.md`.

## Orchestration CLI

The orchestration tools (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-action`, `ll-loop`,
FSM evaluators, FSM handoff) route every host CLI invocation through
`scripts/little_loops/host_runner.py`. The `HostRunner` Protocol is
satisfied by four concrete runners — `ClaudeCodeRunner` (production),
`CodexRunner` (wired, auto-detects when `codex` is on PATH),
`OpenCodeRunner` (stub), and `PiRunner` (stub) — so adding a new host is
a matter of fleshing out the corresponding runner rather than touching
call sites.

| Tool                          | Claude Code | OpenCode      | Codex CLI    | Pi           | Gemini CLI   |
| ----------------------------- | ----------- | ------------- | ------------ | ------------ | ------------ |
| `ll-auto`                     | ✓           | stub[^orch]   | ✓            | stub[^orch]  | stub[^orch]  |
| `ll-parallel`                 | ✓           | stub[^orch]   | ✓            | stub[^orch]  | stub[^orch]  |
| `ll-action`                   | ✓           | stub[^orch]   | ✓            | stub[^orch]  | stub[^orch]  |
| `ll-loop`                     | ✓           | stub[^orch]   | ✓            | stub[^orch]  | stub[^orch]  |
| `ll-harness`                  | ✓           | stub[^orch]   | ✓            | stub[^orch]  | stub[^orch]  |
| `ll-sprint`                   | ✓           | stub[^orch]   | ✓            | stub[^orch]  | stub[^orch]  |
| FSM evaluators / handoff      | ✓           | stub[^orch]   | ✓            | stub[^orch]  | stub[^orch]  |
| Conformance harness[^conf]    | ✓           | stub[^orch]   | ✓            | stub[^orch]  | stub[^orch]  |

[^conf]: Generic host-parametrized conformance harness (FEAT-2259). Run with
    `pytest -m conformance scripts/tests/` or per-host with
    `--conformance-host <host>`. PASS/SKIP maps to ✓/stub in this table.
    See `docs/development/CONFORMANCE.md`.

[^orch]: All seven call sites now route through
    `scripts/little_loops/host_runner.py` (`HostRunner` Protocol +
    `ClaudeCodeRunner` + `CodexRunner` + `OpenCodeRunner` + `PiRunner`).
    Wiring a non-Claude host means registering a new `HostRunner`
    implementation; the orchestration layer no longer hard-codes the
    `claude` binary or its argv. **stub** = runner is registered so
    `LL_HOST_CLI=<host>` resolves, but every `build_*` raises
    `HostNotConfigured` until the host-specific argv is implemented
    (OpenCode: FEAT-1472 Option B). **Vanilla Pi (pi-mono) host support is
    CANCELLED** (2026-06-24, ARCHITECTURE-050) — the `PiRunner` stub is frozen
    and superseded by oh-my-pi (`omp`), tracked under EPIC-2258. The Pi column
    is retained only because the stub is still registered in code; it will be
    replaced by an `omp` column once `OmpRunner` lands (FEAT-1850). Do not
    invest in the Pi column.

## Config probe path

Resolved by `resolve_config_path()` in
`scripts/little_loops/config/core.py`. The probe order depends on
`LL_HOOK_HOST` (and the alternate `LL_STATE_DIR` trigger for Codex).

| Host        | Probe order                                                                              |
| ----------- | ---------------------------------------------------------------------------------------- |
| Claude Code | `.ll/ll-config.json` → root-level `ll-config.json`                                       |
| OpenCode    | `.ll/ll-config.json` → root-level `ll-config.json` (same as default)                     |
| Codex CLI   | `.codex/ll-config.json` → `.ll/ll-config.json` → root-level `ll-config.json`             |
| Gemini CLI  | `.gemini/ll-config.json` → `.ll/ll-config.json` → root-level `ll-config.json` (deferred)[^gemini] |

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
| `LL_HOST_CLI`         | Override host runner selection (`claude-code`, `codex`, `opencode`, `pi`). Takes precedence over binary probe and `orchestration.host_cli` config. |
| `LL_HOOK_HOST`        | Identify the host to hook adapters (`claude-code`, `opencode`, `codex`). Set by each adapter before invoking the Python hook layer. |
| `LL_STATE_DIR`        | Scope config probe to a host-specific directory (e.g. `.codex`). Affects config resolution only — other state paths are unaffected (see [^state]). |
| `LL_HISTORY_DB`       | Override the default `.ll/history.db` session-store path (e.g. for test isolation). |
| `LL_NON_INTERACTIVE`  | Set to `"1"` by all `build_*` host runner methods to signal that a skill is running in a non-interactive automation context. Skills check this (via `[[ -n "${LL_NON_INTERACTIVE:-}" ]]`) to auto-enable `--auto` mode and skip `AskUserQuestion` prompts. Use `DANGEROUSLY_SKIP_PERMISSIONS` as a fallback during the migration period. |

## Adapter locations

- Claude Code: [`hooks/adapters/claude-code/`](../../hooks/adapters/claude-code/) — Bash shim
- OpenCode: [`hooks/adapters/opencode/`](../../hooks/adapters/opencode/) — TypeScript/Bun plugin
- Codex CLI: [`scripts/little_loops/hooks/adapters/codex/`](../../scripts/little_loops/hooks/adapters/codex/) — Bash shim with `matcher: "startup"`

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
- **FEAT-992** — Original Pi (pi-mono) coding-agent compatibility epic.
  **Vanilla Pi support cancelled** 2026-06-24 (ARCHITECTURE-050); superseded by
  oh-my-pi (`omp`) under **EPIC-2258**. An `omp` column replaces the Pi column
  once `OmpRunner` lands (FEAT-1850).
- **FEAT-1488** — Research spike: sidecar/IPC for hot-path intents on
  non-Claude-Code hosts (completed — decision: opt-in-only + fire-and-forget
  `post_tool_use`; sidecar deferred until benchmark; see
  `thoughts/research/hot-path-hook-intents.md`).
- **FEAT-1489** — Wire `post_tool_use` for Codex and OpenCode (fire-and-forget);
  create benchmark script; wire `pre_tool_use` if benchmark clears 200ms threshold.
- **EPIC-2178** — Gemini CLI host adapter tracking (this matrix's Gemini column).
- **FEAT-2179** — Research spike: gemini-cli binary surface, hook events, and plugin
  discovery (completed — all cells confirmed; see `thoughts/research/gemini-cli-surface.md`).
