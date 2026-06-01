# OpenCode Adapter for little-loops Hook Intents

Thin TypeScript plugin that lets OpenCode delegate to the host-agnostic Python
hook dispatcher in `little_loops.hooks`. Mirrors the shape of the Claude Code
shell adapters in `hooks/adapters/claude-code/` — spawn `python -m
little_loops.hooks <intent>`, pipe the host event payload as JSON to stdin,
propagate stdout/stderr/exit-code back to OpenCode. No logic lives in this
adapter; it is purely a transport.

## Installation

Inside your OpenCode project (Bun runtime):

```bash
cd hooks/adapters/opencode
bun install
```

Then wire the plugin via OpenCode's plugin registration mechanism (per
`@opencode-ai/plugin` v1.2.27). Example:

```ts
// opencode.config.ts (or wherever your OpenCode entry-point lives)
import llHooks from "./hooks/adapters/opencode/index.ts";

export default {
  plugins: [llHooks],
};
```

The adapter resolves `python` from the ambient `PATH`. Ensure
`little_loops` is installed in that interpreter (`pip install -e
./scripts`).

## Event → Intent Mapping (MVP)

| OpenCode event       | ll intent       | Python invocation                              |
| -------------------- | --------------- | ---------------------------------------------- |
| `session.created`    | `session_start` | `python -m little_loops.hooks session_start`   |
| `session.compacted`  | `pre_compact`   | `python -m little_loops.hooks pre_compact`     |
| `tool.execute.before`| `pre_tool_use` (opt-in) | `python -m little_loops.hooks pre_tool_use` — handler is registered but the adapter does **not** wire `tool.execute.before` by default |
| `tool.execute.after` | `post_tool_use` | `python -m little_loops.hooks post_tool_use` — invoked fire-and-forget (no `await` on the spawned Promise); handler writes byte metrics and a `file_events` row to `.ll/history.db` when `analytics.enabled` is set (FEAT-1623, ENH-1832) |
| `session.idle`       | (deferred)      | —                                              |
| `tui.prompt.append`  | (deferred)      | —                                              |

`tool.execute.after` is wired fire-and-forget per FEAT-1489: `spawnIntent`
is called without `await`, so the OpenCode tool path never blocks on the
Python handler. Stderr and exit code are dropped. Per FEAT-1623 and ENH-1832,
the handler persists per-tool byte metrics (`bytes_in` / `bytes_out` /
`cache_hit`) and one `file_events` row per file-touching call into
`.ll/history.db` when `analytics.enabled` is set in the project config;
consumers (e.g. `/ll:ctx-stats`) read those rows asynchronously and must
tolerate observational-only semantics — failed writes are suppressed inside
the handler so the OpenCode tool path is
never disturbed.

`tool.execute.before` is intentionally **not** wired by default. The
Python handler (`pre_tool_use`) is available, and the cold-start budget
(≈10ms p95, see below) makes a blocking pre-tool handler viable, but
adding a synchronous wait to every tool invocation by default is opt-in.
To opt in, add the following alongside the existing handlers in `index.ts`:

```ts
"tool.execute.before": async (input: unknown) => {
  const { stderr, exitCode } = await spawnIntent("pre_tool_use", input, ctx.cwd);
  if (stderr) console.error(stderr);
  if (exitCode !== 0 && exitCode !== 2) {
    throw new Error(stderr || `pre_tool_use failed with exit ${exitCode}`);
  }
},
```

## Host Identification

The adapter sets `LL_HOOK_HOST=opencode` on the subprocess environment. The
Python dispatcher reads this env var to populate `LLHookEvent.host` so that
core handlers can branch on host-specific quirks if needed. Without this var,
the dispatcher defaults to `host="claude-code"`.

## Subprocess Contract

| Channel    | Direction         | Format                                                                          |
| ---------- | ----------------- | ------------------------------------------------------------------------------- |
| stdin      | adapter → python  | Raw JSON dict — the host's event payload (for `pre_compact`, must include `transcript_path`) |
| stdout     | python → adapter  | Raw bytes; for `session_start` this is the merged config JSON (consumed as session context); empty for `pre_compact` |
| stderr     | python → adapter  | Human-readable status/feedback lines                                            |
| exit code  | python → adapter  | `0` = pass, `2` = block + inject feedback, `1` = unknown intent (hard error)    |
| cwd        | adapter sets      | OpenCode's working directory (`ctx.cwd`) — Python handlers resolve `.ll/ll-config.json` and write `.ll/ll-precompact-state.json` relative to it |

`pre_compact`'s success path is `exit_code=2` with feedback-only; the
adapter surfaces stderr to the OpenCode console but does not throw for
exit codes `0` or `2`.

## Latency Target

- **Target:** end-to-end `Bun.spawn → python interpreter cold start → handler
  → exit` ≤ **200 ms p95** on dev hardware.
- **Method:** the benchmark script at
  `scripts/tests/bench_opencode_adapter.py` times sequential invocations of
  each intent and reports min / median / p95 / max in milliseconds. Run from
  the project root with `bun install` already complete.
- **Decision rule:** if measured p95 exceeds the target by **2×** (i.e.
  ≥ 400 ms), a follow-up issue must propose a **persistent sidecar**
  (long-lived Python process the adapter talks to over IPC) **before**
  any new blocking hot-path intent is wired.

### Measured (FEAT-1489, 2026-05-16)

30 sequential invocations on dev hardware (macOS, Apple Silicon):

| Intent          | min   | median | p95   | max   | n  |
| --------------- | ----- | ------ | ----- | ----- | -- |
| `session_start` | 7.9ms | 8.5ms  | 9.8ms | 61.2ms | 30 |
| `pre_compact`   | 8.1ms | 8.5ms  | 9.3ms | 9.7ms | 30 |

**Verdict:** p95 ≈ 10ms ≪ 200ms target. Cold-start is acceptable; the
sidecar is not required. `post_tool_use` is wired fire-and-forget and
adds a single-row SQLite INSERT under the `analytics.enabled` guard
(FEAT-1623); `pre_tool_use` is registered for opt-in. Re-run the
benchmark whenever
the adapter shape, Bun version, or Python startup path changes
materially.

## Smoke Test

The Python-side integration test at
`scripts/tests/test_opencode_adapter.py` exercises the adapter end-to-end via
`bun hooks/adapters/opencode/index.ts`. It is automatically skipped if Bun is
not available on `PATH`.

## Related

- Parent epic: `FEAT-1116` (hook-intent abstraction layer for multi-host support)
- Dependencies: `FEAT-1449` (PreCompact core), `FEAT-1450` (SessionStart core)
- Supersedes: `FEAT-961` (parallel reimplementation approach)
- Sibling adapter: `hooks/adapters/claude-code/` (Bash shim, canonical template)
