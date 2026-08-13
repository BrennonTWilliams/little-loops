# Automation with Qwen Code

Running little-loops orchestration on the Qwen Code CLI via `QwenRunner` (`scripts/little_loops/host_runner.py`, ENH-3156). Flag behavior on this page was live-verified on qwen **0.21.6** by the FEAT-3155 spike (`thoughts/research/qwen-code-surface.md`).

---

## Running orchestration CLIs

All orchestration tools (`ll-auto`, `ll-parallel`, `ll-action`, `ll-harness`, `ll-loop`, `ll-sprint`, plus the FSM evaluators and handoff) support qwen as the backing host CLI. Set `LL_HOST_CLI=qwen` to select it explicitly:

```bash
LL_HOST_CLI=qwen ll-auto
LL_HOST_CLI=qwen ll-parallel --workers 3
LL_HOST_CLI=qwen ll-action manage-issue --json
LL_HOST_CLI=qwen ll-loop run my-loop
LL_HOST_CLI=qwen ll-sprint run v2-launch
```

### Auto-detection

You do not need to set `LL_HOST_CLI` explicitly if `qwen` is on `PATH`. `resolve_host()` in `host_runner.py` probes available binaries and selects `QwenRunner` when `qwen` is found and no override is set.

Detection order (first match wins):

1. `LL_HOST_CLI` environment variable
2. `LL_HOOK_HOST` environment variable
3. Binary probe: `claude` → `codex` → `pi` → `gemini` → `omp` → `kimi` → `qwen` → error

You can also set the host permanently in `.ll/ll-config.json` (or `.qwen/ll-config.json`):

```json
{
  "orchestration": {
    "host_cli": "qwen"
  }
}
```

---

## What the runner emits

`QwenRunner.build_streaming` assembles argv as:

```
qwen --yolo --output-format stream-json [--continue] [--include-directories <dir>] [--model <alias>] -p "<prompt>"
```

with `LL_NON_INTERACTIVE=1`, `DANGEROUSLY_SKIP_PERMISSIONS=1`, and `QWEN_CODE_SUPPRESS_YOLO_WARNING=1` (keeps stderr clean for error diagnostics) in the child environment. Qwen-specific facts:

- **`--yolo`** (alias of `--approval-mode yolo`) is hidden from `--help` but live — the permission-skip path for headless runs.
- **`-p <prompt>`** always terminates the argv (Claude/Kimi convention).
- **`--continue`** resumes the most recent session in the project (requires `general.chatRecording`, default on).
- **`--include-directories`** is additive, not a jail — `workspace_root` widens access rather than confining it (`workspace_sandboxed=False`).

---

## Structured output — the headline capability

Qwen is the **second host after Claude Code** with `structured_output=True`:

- The FSM evaluators append the inline `--json-schema <json>` flag when `HostCapabilities.structured_output` is true. The schema is Ajv-validated through a synthetic `structured_output` tool; the verdict arrives as a JSON *string* in the final envelope's `result` field (there is no claude-style `structured_output` envelope key), and the evaluators' existing `json.loads(result)` path handles it.
- Session persistence for these one-shot evaluator calls is opted out via `--chat-recording false` — qwen rejects claude's `--no-session-persistence` flag (argv parse error), so `_structured_output_args()` keys the persistence opt-out on `invocation.binary`.
- Hosts without the capability fall back to prompt-and-parse (BUG-2626 tag recovery) — nothing changes for them.

This re-enables the schema-constrained verdict path for `ll-loop` FSM evaluators on a non-Claude host for the first time.

---

## Output shapes

- **Streaming** (`--output-format stream-json`): JSONL — `system/init` → interleaved `stream_event` deltas (Qwen-internal, ignorable) → `assistant` messages (`message.content[]`, `message.usage`) → final `{"type":"result","subtype":"success","result":"…","usage":{…},"is_error":false}`.
- **Blocking**: `build_blocking_json` also streams (qwen's `--output-format json` buffers a JSON **array** that breaks single-envelope consumers — Kimi posture); consumers take the last `result` envelope.
- Token reporting: `usage` (including `total_tokens`) is present on assistant messages and on the final result envelope.

---

## Capability limitations (warn-and-drop)

| Parameter | Behavior |
| --- | --- |
| `agent=` | Dropped with a `CapabilityNotSupported` warning — qwen has no `--agent` CLI flag (documented upstream as planned future work) |
| `tools=` | Dropped with a warning — `--exclude-tools` is a denylist, not allowlist semantics |
| `disable_background_tasks=` | Accepted, no-op (Protocol conformance; no qwen equivalent) |

---

## Current limitations

- `agent_select` and `tool_allowlist` are ✗ (see above).
- `SessionEnd` hooks do not fire under `-p` — session cleanup in headless runs rides the `Stop` legacy scripts (see [Hook Events](hook-events.md)).
- Qwen chat-file wire format is not parsed by `ll-session backfill` extraction yet (folder resolution works; ENH-3161 follow-up).
- `--include-directories` widens rather than confines — treat `workspace_root` as access expansion.

---

## See also

- [Getting Started](getting-started.md) — install and verification
- [Hook Events](hook-events.md) — event → intent mapping
- [Host Compatibility Matrix](../reference/HOST_COMPATIBILITY.md) — authoritative parity reference
