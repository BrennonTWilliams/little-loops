# Using little-loops with Codex CLI

---

## Running orchestration CLIs

All orchestration tools (`ll-auto`, `ll-parallel`, `ll-action`, `ll-harness`, `ll-loop`, `ll-sprint`) support Codex as the backing host CLI. Set `LL_HOST_CLI=codex` to select it explicitly:

```bash
LL_HOST_CLI=codex ll-auto
LL_HOST_CLI=codex ll-parallel --workers 3
LL_HOST_CLI=codex ll-action manage-issue --json
LL_HOST_CLI=codex ll-loop run my-loop
LL_HOST_CLI=codex ll-sprint run v2-launch
```

### Auto-detection

You do not need to set `LL_HOST_CLI` explicitly if `codex` is on `PATH`. `resolve_host()` in `host_runner.py` probes available binaries in order and selects `CodexRunner` when `codex` is found and no override is set.

Detection order (first match wins):

1. `LL_HOST_CLI` environment variable
2. `LL_HOOK_HOST` environment variable (falls back to `claude-code` when absent)
3. Binary probe: `claude` → `codex` → error

You can also set the host permanently in `.ll/ll-config.json` (or `.codex/ll-config.json`):

```json
{
  "orchestration": {
    "host_cli": "codex"
  }
}
```

---

## Invoking skills

After running `ll-adapt-skills-for-codex --apply` (see [Getting Started](getting-started.md#skill-and-command-discovery)), all `/ll:*` slash commands are available in the Codex TUI:

```
/ll:manage-issue enhancement improve ENH-001
/ll:scan-codebase
/ll:prioritize-issues
/ll:create-sprint
```

Skills are installed to `~/.codex/skills/<name>/SKILL.md`. Re-run `ll-adapt-skills-for-codex --apply` after upgrading little-loops to pick up new or updated skills.

---

## Opt-in: pre_tool_use

The `PreToolUse` hook fires before every tool invocation, adding ~10ms per call. It is **not** wired by default to avoid latency and trust-hash churn for existing users.

To opt in, add a `PreToolUse` entry to `.codex/hooks.json`:

```json
"PreToolUse": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "bash {{LL_PLUGIN_ROOT}}/hooks/adapters/codex/pre-tool-use.sh",
        "timeout": 5,
        "statusMessage": "Checking tool call..."
      }
    ]
  }
]
```

After saving, start a new Codex session. Codex will prompt you to re-trust the modified `hooks.json`.

---

## Current Limitations

### `--agent` (persona selection)

`CodexRunner` has no native `--agent` CLI flag (this is the permanent native gap tracked in ENH-1531 / openai/codex#10067). Instead, ENH-1533 implements a **prompt-injection workaround**: when `CodexRunner.build_streaming(agent=…)` is called, it reads `.codex/agents/<name>.toml`, extracts `developer_instructions`, and prepends a `[Persona: <name>]\n<instructions>\n\n---\n\n` block to the prompt payload. No warning fires when injection succeeds, and `describe_capabilities()` reports `agent_select.status == "partial"`.

**Setup:** Run `ll-adapt-agents-for-codex --apply` once to generate `.codex/agents/*.toml` files from ll's `agents/*.md` definitions. Re-run after adding new agents.

**Fallback path:** When the TOML file (or its `developer_instructions` key) is absent, `CodexRunner` emits `CapabilityNotSupported` and prints a `[ll] Warning` stderr notice that names the dropped persona and points at `ll-adapt-agents-for-codex --apply`. The session proceeds with Codex's default model configuration.

**Native-flag gap (permanent).** Research (ENH-1531, `thoughts/research/codex-agent-selection.md`) confirmed no Codex CLI mechanism selects a named profile at invocation time:
- The `codex` CLI has no `--agent` flag. Feature request: openai/codex#10067 (open, no timeline).
- `CODEX_AGENT` and `CODEX_PROFILE` environment variables do not exist.
- The `agents.<name>.config_file` config stanza only governs `spawn_agent` subagent calls within an existing session, not the root session persona.

The injection workaround is therefore the only way to get ll-defined persona behavior under Codex; interactive Codex TUI sessions can additionally select agents via `--agent <name>` once the TOML files exist.

**Note for CI/`ll-doctor` consumers:** Before ENH-1533, `ll-doctor` exited `1` on Codex hosts because `agent_select` was `"unsupported"`. With prompt injection, `agent_select` is `"partial"`, which does not trigger exit `1`. Codex hosts that previously failed `ll-doctor` solely on `agent_select` will now exit `0`.

### `--tools` (tool allowlist / sandbox modes)

Codex does not support a fine-grained tool allowlist (`--tools` parameter emits
`CapabilityNotSupported` and is dropped). Instead, use the `sandbox_mode=`
parameter on `CodexRunner` build methods (ENH-1529) to constrain execution:

| `sandbox_mode` value | Codex flag |
|---|---|
| `None` (default) / `"off"` | `--dangerously-bypass-approvals-and-sandbox` |
| `"read-only"` | `--sandbox read-only` |
| `"workspace-write"` | `--sandbox workspace-write` |
| `"danger-full-access"` | `--sandbox danger-full-access` |

Invalid `sandbox_mode` values raise `ValueError`. All three build methods
(`build_streaming`, `build_blocking_json`, `build_detached`) accept the
parameter.

### `json_schema` inline dict (tool schemas)

`CodexRunner.build_blocking_json` supports `json_schema` via a file-mediated bridge (ENH-1530): the schema dict is serialized to a temp file and `--output-schema <path>` is appended to the Codex invocation args. The temp file path is returned in `HostInvocation.cleanup_paths`; callers must unlink it after the subprocess completes:

```python
inv = runner.build_blocking_json(prompt=..., json_schema=my_schema)
result = subprocess.run([inv.binary, *inv.args], ...)
for p in inv.cleanup_paths:
    p.unlink(missing_ok=True)
```

This support is marked `"partial"` in `describe_capabilities` because the schema is file-mediated rather than passed inline. Direct ll-orchestration call sites (`evaluators.py`, `worker_pool.py`) do not pass `json_schema`, so `cleanup_paths` is always `()` in those paths.

### Hook intents without consumers

`stop`, `post_compact`, and `permission_request` events fire in Codex but have no little-loops consumer today. These hooks are intentionally absent from `.codex/hooks.json`.

---

## See also

- [Getting Started](getting-started.md) — install, trust prompt, skill discovery
- [Host Compatibility Matrix](../reference/HOST_COMPATIBILITY.md) — authoritative per-host feature matrix
- [Troubleshooting](../development/TROUBLESHOOTING.md) — `HostNotConfigured`, hook trust, binary detection
- [Codex adapter source](../../hooks/adapters/codex/) — transport shims and trust-model details
