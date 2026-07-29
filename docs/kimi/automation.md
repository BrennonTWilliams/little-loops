# Automation with Kimi Code CLI

Running little-loops orchestration on the Kimi Code CLI via `KimiRunner` (`scripts/little_loops/host_runner.py`, FEAT-2914). Flag behavior on this page was machine-verified on kimi **0.30.0** by the FEAT-2911 spike (`thoughts/research/kimi-cli-surface.md`).

---

## Running orchestration CLIs

All orchestration tools (`ll-auto`, `ll-parallel`, `ll-action`, `ll-harness`, `ll-loop`, `ll-sprint`, plus the FSM evaluators and handoff) support kimi as the backing host CLI. Set `LL_HOST_CLI=kimi-code` to select it explicitly:

```bash
LL_HOST_CLI=kimi-code ll-auto
LL_HOST_CLI=kimi-code ll-parallel --workers 3
LL_HOST_CLI=kimi-code ll-action manage-issue --json
LL_HOST_CLI=kimi-code ll-loop run my-loop
LL_HOST_CLI=kimi-code ll-sprint run v2-launch
```

### Auto-detection

You do not need to set `LL_HOST_CLI` explicitly if `kimi` is on `PATH`. `resolve_host()` in `host_runner.py` probes available binaries and selects `KimiRunner` when `kimi` is found and no override is set.

Detection order (first match wins):

1. `LL_HOST_CLI` environment variable
2. `LL_HOOK_HOST` environment variable
3. Binary probe: `claude` → `codex` → `pi` → `gemini` → `omp` → `kimi` → error

You can also set the host permanently in `.ll/ll-config.json` (or `.kimi-code/ll-config.json`):

```json
{
  "orchestration": {
    "host_cli": "kimi-code"
  }
}
```

---

## What the runner emits

`KimiRunner.build_streaming` assembles argv as:

```
kimi --output-format stream-json [--continue] [--agent <name>] [--add-dir <dir>] [--model <alias>] -p "<prompt>"
```

with `LL_NON_INTERACTIVE=1` and `DANGEROUSLY_SKIP_PERMISSIONS=1` in the child environment. Kimi-specific facts:

- **Flags first, prompt last.** Kimi's argument parser treats a bare positional after options as a subcommand, so `-p <prompt>` always terminates argv.
- **No permission flags, ever.** `kimi -p` runs under the auto permission policy implicitly, and `--yolo` / `--auto` / `--plan` are *rejected* in combination with `-p` (verified: `error: Cannot combine --prompt with --yolo.`). The runner never emits one.
- **Resume** maps to `--continue` (most recent session in the cwd). The terminal `meta` event in the stream carries the `session_id`, which the runner layer can use for resume bookkeeping.
- **Model** maps to `--model <alias>`; the alias must exist in the `[models]` table of kimi's `config.toml`.
- **`--add-dir`** (from `workspace_root`) is an additive workspace dir, **not a sandbox** — it widens rather than confines access.

### Blocking JSON consumers

Kimi has no single-blob `--output-format json` mode — `text` and `stream-json` are the only formats. `build_blocking_json` therefore also streams, and blocking consumers take the **final `role:"assistant"` content event before the terminal `meta` line** (the same consume-the-final-event contract as Codex). There is no `type:"result"` summary event like Claude's.

### Detached runs and `print_background_mode=steer`

In print mode, kimi defaults to `print_background_mode = "steer"`: the process **stays alive** after the main turn while background tasks (including background subagents) are pending, feeding completions back as synthetic user messages. It is bounded by `print_wait_ceiling_s` / `print_max_turns`, which are effectively unbounded by default. Callers of `build_detached` must **not** expect the process to exit at the first final answer when the model backgrounds work.

### `--agent` + resume conflict

Agent selection is native (`--agent <name>`) and works with `-p` — but kimi rejects `--agent` in combination with `--continue` / `--session` (the agent is bound at session creation). When ll's orchestration layer requests a persona on a resume, `KimiRunner` **drops the agent and emits a `CapabilityNotSupported` warning** rather than failing the run.

---

## Conformance

The generic host-parametrized conformance harness covers kimi-code; the golden paths pass:

```bash
pytest -m conformance --conformance-host kimi-code scripts/tests/conformance/
# 4 passed
```

(Point pytest at the conformance directory itself — the `--conformance-host` option is registered by `scripts/tests/conformance/conftest.py`, which is not loaded for broader path args.)

See [CONFORMANCE](../development/CONFORMANCE.md) for the harness contract.

---

## Current limitations

### No token reporting

Kimi 0.30.0 emits **no token-usage events** anywhere in the stream-json output (usage is visible in the TUI `/usage` only). Loops run under kimi produce no `usage.jsonl` file and no per-state cost table in `ll-loop run` output.

### No structured-output flag

Kimi has no `--json-schema` flag and no single-blob JSON mode. A `json_schema` passed to `build_blocking_json` is dropped with a `CapabilityNotSupported` warning, and the FSM evaluators gate on `HostCapabilities.structured_output` (`"unsupported"` for kimi) and fall back to prompt-and-parse — with the BUG-2626 `<StructuredOutput>` tag recovery — instead of appending an inline schema flag.

### No tool allowlist

Kimi has no `--tools` CLI flag. Tool policy lives in agent files (`tools` / `disallowedTools` frontmatter) or the global `[tools]` table in kimi's `config.toml`. A `tools` list passed to the runner is dropped with a `CapabilityNotSupported` warning.

---

## See also

- [Getting Started](getting-started.md) — install, config probe, skill discovery
- [Hook Events](hook-events.md) — event → intent mapping, payload drift, blockable events
- [Host Compatibility Matrix](../reference/HOST_COMPATIBILITY.md) — authoritative per-host feature matrix
- [Troubleshooting](../development/TROUBLESHOOTING.md) — `HostNotConfigured`, binary detection
