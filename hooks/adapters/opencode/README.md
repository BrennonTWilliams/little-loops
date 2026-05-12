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
| `tool.execute.before`| (deferred)      | —                                              |
| `tool.execute.after` | (deferred)      | —                                              |
| `session.idle`       | (deferred)      | —                                              |
| `tui.prompt.append`  | (deferred)      | —                                              |

Hot-path events (`tool.execute.before/after`) are deferred per
[FEAT-1116 Decision 3](../../../.issues/completed/P3-FEAT-1116-hook-intent-abstraction-layer.md)
until end-to-end latency is measured (see below).

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

## Latency Target (Pre-Hot-Path Gate)

Before any future issue adds hot-path intents (`tool.execute.before/after`),
this adapter must satisfy the latency budget below. The current MVP scope
(`session_start`, `session.compacted`) is invoked at most once per session and
is not latency-sensitive.

- **Target:** end-to-end `Bun.spawn → python interpreter cold start → handler
  → exit` ≤ **200 ms p95** on dev hardware. This is an initial target; refine
  by measurement before promoting it to a hard limit.
- **Method:** a benchmark script at
  `scripts/tests/bench_opencode_adapter.py` (to be added by the hot-path
  follow-up issue) times **100 sequential invocations** of each intent and
  reports min / median / p95 / max in milliseconds. Run from the project
  root with `bun install` already complete.
- **Decision rule:** if measured p95 exceeds the target by **2×** (i.e.
  ≥ 400 ms), a follow-up issue must propose a **persistent sidecar**
  (long-lived Python process the adapter talks to over IPC) **before**
  hot-path intents are wired.

Until the benchmark has been run and the p95 figure recorded here in this
README, hot-path event handlers (`tool.execute.before` / `tool.execute.after`)
**must not** be added to the plugin's handler map.

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
