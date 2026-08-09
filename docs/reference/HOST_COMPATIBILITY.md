# Host Compatibility Matrix

> **Last Updated: 2026-07-29** — update this date whenever a matrix cell changes status.

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

| Hook intent          | Claude Code | OpenCode      | Codex CLI     | Gemini CLI    | Kimi Code                                                            |
| -------------------- | ----------- | ------------- | ------------- | ------------- | -------------------------------------------------------------------- |
| `session_start`      | ✓           | ✓             | ✓ (matcher=`startup`) | (deferred)[^gemini] — `SessionStart`; advisory only | ✓ — `transcript_path` absent (guarded)[^kimi]  |
| `pre_compact`        | ✓           | ✓             | ✓             | (deferred)[^gemini] — `PreCompress`; advisory, async | ✓[^kimi]                                         |
| `user_prompt_submit` | ✓           | (deferred)    | ✓             | (deferred)[^gemini] — `BeforeAgent` | ✓ (blockable; block-array prompt handled)[^kimi] |
| `pre_tool_use`       | ✓ (active)[^hot] | (opt-in)[^hot] | (opt-in)[^hot] | (deferred)[^gemini] — `BeforeTool` | ✓ (active, blockable)[^kimi]                     |
| `post_tool_use`      | ✓           | ✓ (fire-and-forget)[^hot] | ✓ (fire-and-forget)[^hot] | (deferred)[^gemini] — `AfterTool` | ✓ — `tool_output` payload tolerated (FEAT-2974)[^kimi] |
| `session_end`        | ✓ (dispatched from `SessionStart` event → `session_end` intent[^ssend]) | (deferred)    | (deferred)    | (deferred)[^gemini] — `SessionEnd`; best-effort | ✓ — native `SessionEnd`; no SessionStart workaround needed[^kimi] |
| `post_compact`       | N/A         | N/A           | (deferred)[^postcompact] | N/A — no equivalent | (deferred)[^kimi] — kimi fires `PostCompact`; unwired |
| `permission_request` | N/A         | N/A           | (deferred)[^permreq] | N/A — `Notification` hook is observability-only | (deferred)[^kimi] — kimi fires `PermissionRequest`/`Result`; unwired |

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

[^ssend]: The `session_end` intent (stale cross-issue-ref sweep, FEAT-1680) is
    dispatched from Claude Code's `SessionStart` event, not `SessionEnd`. Claude
    Code enforces a hard ~1.5s ceiling on `SessionEnd` hooks before killing them
    on any exit path (Ctrl+C, Ctrl+D, `/exit`), regardless of the configured
    `timeout` — an unfixed upstream bug (anthropics/claude-code#32712, #41577).
    The sweep's full-tree issue scan exceeds that ceiling on repos with a few
    thousand issue files, so it was being killed on nearly every exit. It now
    runs once at the start of the *next* session instead, with the same
    detection value and no exit-teardown race. The adapter file and dispatch
    intent name are unchanged (`session-end.sh` → `session_end`) — only the
    `hooks.json` event binding moved.

[^postcompact]: Codex's `PostCompact` event has the same payload shape as
    `PreCompact`, but ll's existing `pre_compact` handler performs all
    compact-time cleanup *before* compaction. There is no concrete
    consumer for a post-compact intent in ll today.

[^permreq]: Codex exposes a `permission_request` event when a tool requires
    user approval. The original tracking issue (FEAT-1720) was **cancelled**
    and its scope absorbed into **FEAT-1719** (cancelled 2026-07-03 per SCOPE-041);
    the PostCompact + PermissionRequest wiring is not yet tracked by an open
    issue. Cell stays (deferred) until a concrete consumer exists.

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
    EPIC-2178 children land. **Landed so far:** `GeminiRunner` (ENH-2184 /
    ENH-2185 — all four `build_*` methods wired) and the `.gemini/ll-config.json`
    config probe (ENH-2187). Hook adapter (FEAT-2186) and `GEMINI.md` project
    instructions (FEAT-2190) are still pending — hook-intent and discovery cells
    stay `(deferred)` until those land.

[^kimi]: Kimi Code CLI (`kimi` binary) support is tracked by **EPIC-2910**.
    Research spike **FEAT-2911** (2026-07-29) machine-verified the full
    adapter surface on kimi 0.30.0 — binary flags, stream-json event shapes,
    hook payloads, session-log layout, skills/commands/agents discovery, and
    plugin packaging. Research artifact:
    `thoughts/research/kimi-cli-surface.md`. **Landed:** `KimiRunner`
    (ENH-2912 registration / FEAT-2914 wiring — all four `build_*` methods),
    the `.kimi-code/ll-config.json` config probe (ENH-2913), the hook adapter
    (FEAT-2974 — eight events wired via a managed `[[hooks]]` block in
    `~/.kimi-code/config.toml`, including `subagent_start`/`subagent_stop`
    intents, which have no rows in the table above), the `ll-adapt` emitter
    (FEAT-2916), `kimi.plugin.json` packaging (FEAT-2917), and
    `session_index.jsonl`-based session-log resolution (FEAT-2918).
    Payload drift vs Claude is absorbed by host-tolerant accessors in the
    Python handlers (block-array `prompt`, `tool_output` for `tool_response`,
    `agent_name` for `agent_type`) — the Bash shims stay dumb. **Deferred:**
    `post_compact` and `permission_request` — kimi fires `PostCompact` and
    `PermissionRequest`/`PermissionResult` events, but there is no adapter
    wiring and no current consumer (EPIC-2910 follow-up).

## Slash-command and skill discovery

| Surface                  | Claude Code               | OpenCode                  | Codex CLI                 | Gemini CLI                | Kimi Code |
| ------------------------ | ------------------------- | ------------------------- | ------------------------- | ------------------------- | --------- |
| Slash-command discovery  | ✓ `.claude/commands/*.md` | ✓ via plugin registration | ✓ — `commands/*.md` bridged to `skills/ll-<name>/SKILL.md` by `ll-adapt --host codex` (FEAT-1493)[^cmds] | (deferred)[^gemini] — `.gemini/commands/*.toml`; TOML format; bridge script needed | ✓ — `kimi.plugin.json` (plugin id `ll`) registers `commands/*.md` as `/ll:<name>` (confirmed working on 0.30.0; plugin **hooks** are inert — separate issue)[^kimiplugin]; project-local bridged skills via `ll-adapt --host kimi-code --apply` (FEAT-2916)[^kimi] |
| Skill discovery          | ✓ `.claude/skills/*/SKILL.md` | ✓ via plugin registration | ✓ — `~/.codex/skills/<name>/SKILL.md`; all ll skills adapted by `ll-adapt --host codex` (FEAT-1486)[^cmds] | (deferred)[^gemini] — `.gemini/skills/<name>/SKILL.md`; compatible format; minor adaptation (add `name:`) | ✓ — `.kimi-code/skills/` is a native scan dir; SKILL.md near-1:1 (extra frontmatter keys tolerated)[^kimi] |

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

    **`disable-model-invocation` flag scope:** `ll-adapt --host codex`
    honours `disable-model-invocation: true` (see
    `scripts/little_loops/adapters/core.py:process_skills`/`process_commands`);
    the 51 SKILL.md files carrying that flag are skipped and NOT exposed in
    Codex. The flag governs two other tools only:
    `ll-generate-skill-descriptions` (skips for token-budget compliance)
    and Claude Code's auto-invocation gate. See ENH-1497.

## Runner Capabilities

Runtime capabilities reported by `ll-doctor` for each host runner.

| Capability       | Claude Code | OpenCode | Codex CLI                          | Gemini CLI                         | omp                                | Kimi Code |
| ---------------- | ----------- | -------- | ---------------------------------- | ---------------------------------- | ---------------------------------- | --------- |
| Streaming        | ✓           | ✓        | ✓                                  | ✓ (`--output-format stream-json`)[^gemini]      | ✓ (`--mode json`, JSONL)[^omp]     | ✓ (`--output-format stream-json`)[^kimi] |
| Permission skip  | ✓           | ✗        | ✗[^runnercap]                      | ✓ (`--approval-mode=yolo`)[^gemini] | ✓ (implicit — print mode never prompts)[^omp] | ✓ (implicit — `-p` runs under the auto permission policy; `--yolo`/`--auto`/`--plan` are rejected with `-p`)[^kimi] |
| Agent selection  | ✓           | ✗        | partial (subagents)[^agent]        | ✗ — skills activate implicitly; no `--agent` flag[^gemini] | ✗ — subagents spawn in-session; no `--agent` flag[^omp] | partial (native `--agent`; rejected with `--continue` — dropped with warning on resume)[^kimi] |
| Tool allowlist   | ✓           | ✗        | ✗[^runnercap]                      | ✗ — Policy Engine (TOML); not a simple flag[^gemini] | ✓ (`--tools <comma-list>`)[^omp]   | ✗ — no `--tools` flag; tool policy via agent files / global `[tools]` config[^kimi] |
| `json_schema`    | ✓[^schema]  | ✗        | partial (file-mediated)[^schema]   | ✗[^gemini]                         | ✗[^omp]                            | ✗[^kimi] |
| `structured_output` | ✓        | ✗        | ✗[^struct]                         | ✗[^struct]                         | ✗[^struct]                         | ✗[^struct] — no single-blob JSON mode; blocking consumers take the final assistant stream event[^kimi] |
| Token reporting  | ✓           | ✗[^tok]  | ✗[^tok]                            | ✗[^gemini]                         | ✗[^omp]                            | ✗ — no usage events in stream-json (0.30.0)[^kimi] |
| `disable_background_tasks` | ✓ (`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`)[^bgtasks] | ✗ (no-op) | ✗ (no-op) | ✗ (no-op) | ✗ (no-op) | ✗ (no-op) |

[^bgtasks]: **FEAT-3078/FEAT-3060, Claude-Code-only.** When `orchestration.disable_background_tasks` is `true` (default) and `automation_profile` is set, `ClaudeCodeRunner.build_streaming()` injects `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, hard-disabling tool-level background tasks (`Bash run_in_background: true`) in the child so completed work can't be silently discarded because the parent session ended before a background task's result was retrieved. The other five runners accept the `disable_background_tasks` parameter for `HostRunner` Protocol conformance but ignore it — no equivalent capability exists for those CLIs. Shell-level backgrounding (a trailing `&`) is outside this flag's reach on every host.

[^omp]: oh-my-pi (`omp` binary, Bun package `@oh-my-pi/pi-coding-agent`) support
    is tracked by **EPIC-2258**. The runner core (`OmpRunner`, FEAT-1850) and the
    `.omp/ll-config.json` config probe (FEAT-2262) are landed; the hook adapter
    (FEAT-2261) and hook-event parity audit (FEAT-2263) are pending — hook-intent
    cells for omp are not tracked in the matrix until FEAT-2261 lands. omp has no
    single-blob JSON mode: `--mode json` emits a JSONL event stream (same
    consume-the-final-event contract as Codex `--json`). Audit artifact:
    `thoughts/research/omp-headless-flags.md`.

[^tok]: OpenCode and Codex CLI do not expose per-invocation token usage in their streaming output. The `on_usage_detailed` callback in `subprocess_utils.run_claude_command()` therefore fires only for `claude`-backed runs. Adapter work to surface usage from OpenCode/Codex is tracked by **FEAT-2123**. Loops run under those hosts will produce no `usage.jsonl` file and no per-state cost table in `ll-loop run` output.

[^runnercap]: `permission skip` and `tool allowlist` are reported `✗` by `ll-doctor`
    for both OpenCode and Codex. Whether these have native Codex equivalents
    (e.g., `sandbox_mode`/approval policy for permission skip; per-agent
    `mcp_servers`/`skills.config` scoping for tool allowlist) is unresearched —
    the cells were never backed by a tracking issue. **ENH-2124** produces that
    research note and either wires the capability or marks it a documented
    permanent gap.

[^schema]: `CodexRunner.build_blocking_json` serializes the schema dict to a temp file and passes `--output-schema <path>` to Codex (ENH-1530). The temp file path is returned in `HostInvocation.cleanup_paths`; callers must call `p.unlink(missing_ok=True)` for each path after the subprocess completes. `ClaudeCodeRunner` honors an inline `--json-schema` flag (BUG-2759 corrected this row to agree with `structured_output` below) — but its `build_blocking_json()` has no schema flag of its own and still silently drops a `json_schema` parameter passed there.

[^struct]: `HostCapabilities.structured_output` (ENH-2627) is a *separate* flag from `json_schema`: it describes whether the host's CLI honors the inline `--json-schema` flag the FSM evaluators (`evaluators.py`) append at their call sites. Only the Anthropic `claude` CLI does, so the evaluators gate the flag on this capability and fall back to prompt-and-parse (with the BUG-2626 `<StructuredOutput>` tag recovery) on every other host. Codex's file-mediated `--output-schema` path is unrelated — the evaluators do not use it.

[^agent]: **Codex has first-class custom agents — "subagents".** They are
    defined as TOML files in `~/.codex/agents/` (personal) or `.codex/agents/`
    (project), with required fields `name`, `description`,
    `developer_instructions` and optional `model`, `model_reasoning_effort`,
    `sandbox_mode`, `mcp_servers`, `skills.config`, `nickname_candidates`
    (see <https://developers.openai.com/codex/subagents>). ll generates these
    via `ll-adapt --host codex --apply` (FEAT-1527).

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
    `ll-adapt --host codex --apply`. `describe_capabilities()` reports
    `agent_select.status == "partial"`.

    **Follow-ups:** ll does not yet exploit the native `spawn_agents_on_csv`
    batch model, which maps onto `ll-parallel`'s per-issue fan-out
    (**FEAT-2122**). See `thoughts/research/codex-agent-selection.md`.

## Adapter Host Capabilities

Build-time capabilities of `ll-adapt`'s per-host output emitters
(`scripts/little_loops/adapters/{codex,gemini,omp,kimi,claude_code}.py`),
authored in `scripts/little_loops/adapters/capabilities.py`'s
`HOST_CAPABILITIES` map (ENH-2873). This is a **distinct surface from
"Runner Capabilities" above**: this table describes what `ll-adapt` writes to
disk for a host (build-time emission); the Runner Capabilities table above
describes what a host's CLI can do when it is invoked (runtime invocation).
The two host key sets are not fully congruent — `opencode`/`pi` have no
adapter-side entry at all, since `ll-adapt` only emits for hosts that need
frontmatter translated into a different discovery format or an MCP config
written. `claude-code` is the one host present on both sides: its
adapter-side entry (FEAT-3139) emits only `.mcp.json` at the project root
(`config_dir="."`) — skills/commands/agents need no adapter-side output since
the plugin marketplace serves them natively. `ll-verify-host-map`
(`ll-doctor --full`) mechanically checks this table against the map,
`host_runner.HostCapabilities`, and the emitters' actual behavior — see its
module docstring for the checks.

| Host   | Config dir | Skill output                                 | Command output                          | Agent output                | Subagents | Agents | Commands | Hooks |
| ------ | ---------- | --------------------------------------------- | ---------------------------------------- | ---------------------------- | --------- | ------ | -------- | ----- |
| codex  | `.codex`   | SKILL.md + `agents/openai.yaml` sidecar (Codex Skills API) | bridged into `skills/ll-<stem>/`         | TOML (`.codex/agents/<name>.toml`) | native    | ✓      | ✓        | ✓     |
| gemini | `.gemini`  | SKILL.md (name injected, `metadata.short-description` stripped) | TOML (`.gemini/commands/<stem>.toml`)    | Markdown, degraded mode (`.gemini/agents/<name>.md`) — authored body verbatim, prefixed with an inline-execution + one-line-disclosure preamble (ENH-2874) | none      | ✓      | ✓        | ✗     |
| omp    | `.omp` | SKILL.md (name injected when absent, `.omp/skills/<name>/SKILL.md`) | Markdown, flat file (`.omp/commands/<stem>.md`, self-derived path — no bridging into `skills/`) | Markdown, native task-agent file (`.omp/agents/<name>.md`) | native | ✓ | ✓ | ✗ |
| kimi-code | `.kimi-code` | SKILL.md (name injected when absent, `metadata.short-description` stripped) | bridged into `.kimi-code/skills/ll-<stem>/` (SKILL.md) — no project-local commands surface outside plugins | Markdown, native Claude-style agent file (`.kimi-code/agents/<name>.md`) | native | ✓ | ✓ | ✓ |
| claude-code | `.` (project root) | none — plugin marketplace serves skills natively | none — plugin marketplace serves commands natively | none — plugin marketplace serves agents natively | none | ✗ | ✗ | ✗ |

`claude-code`'s only real emission is `emit_mcp_config`, writing/merging the
`ll-mcp` server entry into `.mcp.json` at the project root (not a `Config
dir` row column since MCP config isn't captured in this table — see
`emit_mcp_config` in `ClaudeCodeEmitter`, `adapters/claude_code.py`).

omp's emitter (`adapters/omp.py`) is tracked by **EPIC-2258**; `emit_skill`/
`emit_command` are real as of **FEAT-3105**, against the native discovery
format **FEAT-3103**'s research spike documented in
`thoughts/research/omp-skill-command-surface.md`: skills are one directory
per skill (`.omp/skills/<name>/SKILL.md`, `description` required by omp's
loader); commands are a flat, non-bridged `.omp/commands/<stem>.md` file
(`description` optional, falls back to a truncated first body line).
`emit_agent` is real (**FEAT-3104**): FEAT-2797 established that omp
discovers agents via a native `.omp/agents/` scan dir (not a reused
`.claude/agents`/`.codex/agents` path) with a frontmatter `output:` key for
an optional per-agent output schema, and spawns real subagents from these
files — the same native shape as `kimi-code`'s emitter, hence
`subagents: native` and a real `agent_output_format`. It is explicitly
excluded from ENH-2874's degraded-emission coverage because it never needed
that path — it emits natively, not via the degraded fallback.

Gemini has no native subagent-spawning support (`subagents: none`), so
`GeminiEmitter.emit_agent` produces the degraded-mode file described above
instead of raising — every role in `agents/` gets an inline-role reference
the model is instructed to perform itself, disclosing the substitution in
its report (ENH-2874). Discoverability: the file lives at
`.gemini/agents/<name>.md`, generated 1:1 from `agents/<name>.md` by
`ll-adapt --host gemini --apply`; nothing else currently indexes or links to
it (same as Codex's `.codex/agents/*.toml`, which is discovered by the host
CLI's own agent directory scan rather than an ll-side index). If Gemini
agents exit preview and gain native subagent spawning later, the capability
map's `subagents` flips to `native` and `agent_output_format` switches to
describe the native format — no other code changes required.

> **Last Verified: 2026-07-29** — this table was re-checked against the
> emitters' actual source (not just re-dated); distinct from *Last Updated*
> above, which only means the file text changed. Update both dates when the
> table changes; update only *Last Verified* after a re-check that finds no
> drift.

## Orchestration CLI

The orchestration tools (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-action`, `ll-loop`,
FSM evaluators, FSM handoff) route every host CLI invocation through
`scripts/little_loops/host_runner.py`. The `HostRunner` Protocol is
satisfied by seven concrete runners — `ClaudeCodeRunner` (production),
`CodexRunner` (wired, auto-detects when `codex` is on PATH),
`GeminiRunner` (wired, ENH-2185), `OmpRunner` (wired, FEAT-1850),
`KimiRunner` (wired, FEAT-2914), `OpenCodeRunner` (stub), and
`PiRunner` (frozen stub) — so adding a new
host is a matter of fleshing out the corresponding runner rather than
touching call sites.

| Tool                          | Claude Code | OpenCode      | Codex CLI    | Gemini CLI   | omp          | Kimi Code    |
| ----------------------------- | ----------- | ------------- | ------------ | ------------ | ------------ | ------------ |
| `ll-auto`                     | ✓           | stub[^orch]   | ✓            | ✓            | ✓            | ✓            |
| `ll-parallel`                 | ✓           | stub[^orch]   | ✓            | ✓            | ✓            | ✓            |
| `ll-action`                   | ✓           | stub[^orch]   | ✓            | ✓            | ✓            | ✓            |
| `ll-loop`                     | ✓           | stub[^orch]   | ✓            | ✓            | ✓            | ✓            |
| `ll-harness`                  | ✓           | stub[^orch]   | ✓            | ✓            | ✓            | ✓            |
| `ll-sprint`                   | ✓           | stub[^orch]   | ✓            | ✓            | ✓            | ✓            |
| FSM evaluators / handoff      | ✓           | stub[^orch]   | ✓            | ✓            | ✓            | ✓            |
| Conformance harness[^conf]    | ✓           | stub[^orch]   | ✓            | ✓            | ✓            | ✓            |

[^conf]: Generic host-parametrized conformance harness (FEAT-2259). Run with
    `pytest -m conformance scripts/tests/` or per-host with
    `--conformance-host <host>`. PASS/SKIP maps to ✓/stub in this table.
    See `docs/development/CONFORMANCE.md`.

[^orch]: All call sites in the table route through
    `scripts/little_loops/host_runner.py` (`HostRunner` Protocol +
    `ClaudeCodeRunner` + `CodexRunner` + `GeminiRunner` + `OmpRunner` +
    `KimiRunner` + `OpenCodeRunner` + `PiRunner`).
    Wiring a non-Claude host means registering a new `HostRunner`
    implementation; the orchestration layer no longer hard-codes the
    `claude` binary or its argv. **stub** = runner is registered so
    `LL_HOST_CLI=<host>` resolves, but every `build_*` raises
    `HostNotConfigured` until the host-specific argv is implemented
    (OpenCode: FEAT-1472 Option B). **Vanilla Pi (pi-mono) host support is
    CANCELLED** (2026-06-24, ARCHITECTURE-050) — the `PiRunner` stub is frozen
    and superseded by oh-my-pi (`omp`), tracked under EPIC-2258. The former Pi
    column was replaced by the `omp` column when `OmpRunner` landed
    (FEAT-1850); the frozen `PiRunner` stub remains registered in code
    (`LL_HOST_CLI=pi` resolves, every `build_*` raises) but is no longer
    tracked in this matrix.

## Config probe path

Resolved by `resolve_config_path()` in
`scripts/little_loops/config/core.py`. The probe order depends on
`LL_HOOK_HOST` (and the alternate `LL_STATE_DIR` trigger for Codex).

| Host        | Probe order                                                                              |
| ----------- | ---------------------------------------------------------------------------------------- |
| Claude Code | `.ll/ll-config.json` → root-level `ll-config.json`                                       |
| OpenCode    | `.ll/ll-config.json` → root-level `ll-config.json` (same as default)                     |
| Codex CLI   | `.codex/ll-config.json` → `.ll/ll-config.json` → root-level `ll-config.json`             |
| Gemini CLI  | `.gemini/ll-config.json` → `.ll/ll-config.json` → root-level `ll-config.json` (ENH-2187) |
| omp         | `.omp/ll-config.json` → `.ll/ll-config.json` → root-level `ll-config.json` (FEAT-2262)   |
| Kimi Code   | `.kimi-code/ll-config.json` → `.ll/ll-config.json` → root-level `ll-config.json` (ENH-2913) |

The host-specific order is triggered by either `LL_HOOK_HOST=<host>` or
the matching `LL_STATE_DIR` value (`.codex`, `.gemini`, `.omp`,
`.kimi-code`) in the environment. Each adapter sets the former; users can
set the latter manually to force the host probe order without invoking
the adapter.

## State directory

| State surface                       | Claude Code | OpenCode | Codex CLI | Kimi Code |
| ----------------------------------- | ----------- | -------- | --------- | --------- |
| Config file                         | `.ll/`      | `.ll/`   | `.codex/` (first) then `.ll/` | `.kimi-code/` (first) then `.ll/` |
| Issue tracking (`.issues/`)         | `.issues/`  | `.issues/` | `.issues/` (same path)[^state] | `.issues/` (same path)[^state] |
| FSM runs (`.loops/`)                | `.loops/`   | `.loops/` | `.loops/` (same path)[^state] | `.loops/` (same path)[^state] |
| Scratch pads (`.loops/tmp/scratch/`) | `.loops/tmp/scratch/` | `.loops/tmp/scratch/` | `.loops/tmp/scratch/` (same path)[^state] | `.loops/tmp/scratch/` (same path)[^state] |
| Continuation prompt                 | `.ll/ll-continue-prompt.md` | `.ll/ll-continue-prompt.md` | `.ll/ll-continue-prompt.md` (same path)[^state] | `.ll/ll-continue-prompt.md` (same path)[^state] |
| Session store (`SQLiteTransport`)   | `.ll/history.db` | `.ll/history.db` | `.ll/history.db` (same path)[^state] | `.ll/history.db` (same path)[^state] |
| Session logs (`get_project_folder()`) | `~/.claude/projects/<dash-encoded cwd>/` | `~/.opencode/projects/<dash-encoded cwd>/` | `~/.codex/projects/<dash-encoded cwd>/` | ✓ — `~/.kimi-code/sessions/wd_*/` resolved via `~/.kimi-code/session_index.jsonl` (`workDir` → `sessionDir`; FEAT-2918)[^kimiwire] |

[^state]: FEAT-957 deliberately scopes `LL_STATE_DIR=.codex` to the
    config probe only. Other state directories remain at their default
    paths regardless of host. If a future feature needs full per-host
    state redirection, file a separate issue — do not silently expand
    `LL_STATE_DIR`'s reach.

[^kimiwire]: Kimi wire files (`session_*/agents/main/wire.jsonl`) use a
    typed-event schema, not Claude's message schema — session-folder
    *resolution* works (FEAT-2918), but `ll-session backfill` message
    *extraction* does not parse them yet (ENH-2918 follow-up).

[^kimiplugin]: **BUG-2921** — plugin-manifest hooks **fire** on kimi 0.30.0
    in TUI sessions (verified via `hook_events` telemetry; `/plugins info`
    renders no Hooks section — a display gap, not a failure), and `/ll:*`
    commands work. Two caveats: (1) `kimi -p` print mode does **not** fire
    plugin-sourced hooks — headless automation gets hooks only from the
    managed `[[hooks]]` block in `~/.kimi-code/config.toml`
    (`ll-init --hosts kimi-code`); (2) kimi spawns plugin hooks with
    cwd = plugin root, so ll shims `cd` into the payload's project dir —
    config and telemetry resolve against the project's `.ll/`, never the
    managed plugin copy.

## Installation

| Action                              | Claude Code                   | OpenCode                                 | Codex CLI                                | Kimi Code |
| ----------------------------------- | ----------------------------- | ---------------------------------------- | ---------------------------------------- | --------- |
| Install command                     | Plugin auto-enables           | `bun install` under `hooks/adapters/opencode/` | `ll-init --hosts codex` writes `.codex/hooks.json` | `ll-init --hosts kimi-code` installs a managed `[[hooks]]` block into `~/.kimi-code/config.toml` (user-level — kimi has no project-local hook file; **required for hooks in `kimi -p` automation**[^kimiplugin]); optional plugin install of repo-root `kimi.plugin.json` via `/plugins install` (per-user only; covers interactive TUI sessions) |
| Trust prompt on first run           | N/A (plugin trust model)      | N/A                                      | **Yes** — Codex shows a hook-trust dialog; user must "Trust All" or "Review Hooks" before hooks fire | N/A — no trust dialog; hooks take effect in new sessions |
| Host identification env var         | (default, no var needed)      | `LL_HOOK_HOST=opencode`                  | `LL_HOOK_HOST=codex`                     | `LL_HOOK_HOST=kimi-code` |
| Adapter runtime                     | Bash + Python                 | TypeScript / Bun + Python                | Bash + Python                            | Bash + Python |

## Environment variables

| Env var          | Description |
| ---------------- | ----------- |
| `LL_HOST_CLI`         | Override host runner selection (`claude-code`, `codex`, `opencode`, `pi`, `gemini`, `omp`, `kimi-code`). Takes precedence over binary probe and `orchestration.host_cli` config. |
| `LL_HOOK_HOST`        | Identify the host to hook adapters (`claude-code`, `opencode`, `codex`, `kimi-code`). Set by each adapter before invoking the Python hook layer. |
| `LL_STATE_DIR`        | Scope config probe to a host-specific directory (e.g. `.codex`). Affects config resolution only — other state paths are unaffected (see [^state]). |
| `LL_HISTORY_DB`       | Override the default `.ll/history.db` session-store path (e.g. for test isolation). Takes precedence over the `history.db_path` config key, which is the persistent per-project alternative for a durable relocation. Also exported by `setup_worktree()` into the orchestrator's own `os.environ` (BUG-3112), so every descendant process spawned with `cwd=<worktree>` — host-CLI sessions, FSM shell actions, hooks, pytest runs — inherits the main repo's DB instead of resolving a throwaway `<worktree>/.ll/history.db` that worktree teardown deletes. |
| `LL_NON_INTERACTIVE`  | Set to `"1"` by all `build_*` host runner methods to signal that a skill is running in a non-interactive automation context. Skills check this (via `[[ -n "${LL_NON_INTERACTIVE:-}" ]]`) to auto-enable `--auto` mode and skip `AskUserQuestion` prompts. Use `DANGEROUSLY_SKIP_PERMISSIONS` as a fallback during the migration period. |

## Adapter locations

- Claude Code: [`hooks/adapters/claude-code/`](../../hooks/adapters/claude-code/) — Bash shim
- OpenCode: [`hooks/adapters/opencode/`](../../hooks/adapters/opencode/) — TypeScript/Bun plugin
- Codex CLI: [`scripts/little_loops/hooks/adapters/codex/`](../../scripts/little_loops/hooks/adapters/codex/) — Bash shim with `matcher: "startup"` (SessionStart), plus PreCompact / UserPromptSubmit / PostToolUse handlers
- Kimi Code: [`scripts/little_loops/hooks/adapters/kimi/`](../../scripts/little_loops/hooks/adapters/kimi/) — Bash shims + `hooks.toml` template (managed `[[hooks]]` block installed into `~/.kimi-code/config.toml` by `ll-init`; eight events: SessionStart, PreCompact, UserPromptSubmit, PreToolUse, PostToolUse, SessionEnd, SubagentStart/Stop)

Each adapter is a thin transport (`spawn → set env → pipe stdin → exit`);
all real logic lives in `scripts/little_loops/hooks/`.

## Runnable Capability Check

To verify which little-loops features your active host CLI supports, run:

```bash
ll-doctor          # human-readable ✓/○/✗ table
ll-doctor --json   # machine-readable CapabilityReport
```

`ll-doctor` probes the active host binary and prints a `CapabilityReport` with one entry per capability (streaming, permission skip, agent selection, tool allowlist, structured output). When the binary is detected, it also runs the host's version check and reports the real version string, degrading to `(unknown)` only when the binary is absent, the probe fails, or it times out (ENH-2761). It also prints an "Analytics Capture" section reporting the current `analytics.capture` config state (enabled/disabled per category) and an "Issues" section reporting `issues.auto_commit` state. `--json` mirrors both of these under `analytics_capture` and `issues` keys alongside `capabilities`, so machine consumers get the same diagnostic surface as the text output (ENH-2762).

`ll-doctor` is **not host-capability-only**: it always also validates little-loops' own install surface within the current project — Entry Points, Skills & Commands, Decisions Store, History DB, and FSM Loop Validity — and `--full` additionally aggregates the full `ll-verify-*` / `ll-check-links` checker family. See [`docs/reference/CLI.md#ll-doctor`](CLI.md#ll-doctor) for the complete check list and `--json` key set (FEAT-2793/FEAT-2795).

Exits non-zero if any error-tier check is unsupported — the host-capability report and any registered install-surface checks (including the `--full` verifier family, when requested) are folded through the same `CheckResult` severity split (error-tier vs. informational); informational checks never affect the exit code (FEAT-2793). See [`docs/reference/API.md#capabilityreport`](API.md#capabilityreport) for the data model.

## User onboarding

For a user-facing walkthrough of Codex CLI setup and usage, see:

- [`docs/codex/README.md`](../codex/README.md) — what works, what is deferred, quick orientation
- [`docs/codex/getting-started.md`](../codex/getting-started.md) — install, trust prompt, config file, skill discovery
- [`docs/codex/usage.md`](../codex/usage.md) — orchestration CLIs, skill invocation, current limitations

For Kimi Code CLI setup and usage, see:

- [`docs/kimi/getting-started.md`](../kimi/getting-started.md) — install, hook adapter, plugin, skill/command discovery
- [`docs/kimi/hook-events.md`](../kimi/hook-events.md) — event → intent mapping, payload drift, blockable events
- [`docs/kimi/automation.md`](../kimi/automation.md) — orchestration CLIs under kimi, runner flags, current limitations

This matrix is the authoritative parity reference; the per-host docs above are the user-facing onboarding entry points.

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
  oh-my-pi (`omp`) under **EPIC-2258**. The `omp` column replaced the Pi column
  when `OmpRunner` landed (FEAT-1850).
- **EPIC-2258** — oh-my-pi (`omp`) host adapter tracking (this matrix's omp
  column). Runner core (FEAT-1850) and config probe (FEAT-2262) landed; hook
  adapter (FEAT-2261) and hook-event parity (FEAT-2263) pending.
- **FEAT-1488** — Research spike: sidecar/IPC for hot-path intents on
  non-Claude-Code hosts (completed — decision: opt-in-only + fire-and-forget
  `post_tool_use`; sidecar deferred until benchmark; see
  `thoughts/research/hot-path-hook-intents.md`).
- **FEAT-1489** — Wire `post_tool_use` for Codex and OpenCode (fire-and-forget);
  create benchmark script; wire `pre_tool_use` if benchmark clears 200ms threshold.
- **EPIC-2178** — Gemini CLI host adapter tracking (this matrix's Gemini column).
- **FEAT-2179** — Research spike: gemini-cli binary surface, hook events, and plugin
  discovery (completed — all cells confirmed; see `thoughts/research/gemini-cli-surface.md`).
- **EPIC-2910** — Kimi Code CLI host adapter tracking (this matrix's Kimi Code
  column). Research spike **FEAT-2911** completed 2026-07-29 (see
  `thoughts/research/kimi-cli-surface.md`); runner, config probe, hook
  adapter, emitter, plugin packaging, and session-log resolution all landed
  (ENH-2912/2913, FEAT-2914/2915/2916/2917/2918) — see [^kimi].
