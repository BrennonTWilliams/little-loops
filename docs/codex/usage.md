# Using little-loops with Codex CLI

---

## Running orchestration CLIs

All orchestration tools (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, `ll-sprint`) support Codex as the backing host CLI. Set `LL_HOST_CLI=codex` to select it explicitly:

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

`CodexRunner` does not support the `--agent` flag in ll-orchestrated sessions (`ll-auto`, `ll-parallel`, `ll-loop`). When an orchestration tool or skill requests a persona (e.g., `--agent coding`), the flag is silently dropped and `CapabilityNotSupported` is emitted to the log. The session proceeds with Codex's default model configuration.

**Mitigation for interactive sessions:** Run `ll-adapt-agents-for-codex --apply` once to generate `.codex/agents/*.toml` files from ll's `agents/*.md` definitions. After this step, the Codex TUI can select ll subagents via `--agent <name>` (e.g., `--agent codebase-analyzer`). Re-run after adding new agents to `agents/`.

### `--tools` (tool allowlist / sandbox modes)

Only basic sandbox modes pass through to Codex. Fine-grained tool allowlist flags (`--allowedTools`, `--disallowedTools`) are not translated and are dropped silently.

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
