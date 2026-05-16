# Hot-Path Hook Intents: Sidecar/IPC Research for Non-Claude-Code Hosts

**Status:** Decision reached — opt-in-only approach recommended; sidecar deferred
**Last verified:** 2026-05-16
**Research issue:** FEAT-1488
**Hosts evaluated:** Codex CLI (Rust GA), OpenCode (Bun plugin)

## Sources

- `hooks/adapters/codex/README.md` — trust model, event→intent mapping table, Codex hooks system
- `hooks/adapters/opencode/index.ts` — `spawnIntent()` implementation, OpenCode plugin shape
- `hooks/adapters/opencode/README.md` — latency target (≤200ms p95), 2× decision rule (≥400ms → sidecar)
- `thoughts/research/codex-command-discovery.md` (FEAT-1483) — Codex feature flag baseline
- `scripts/little_loops/transport.py` — `UnixSocketTransport` (existing AF_UNIX infrastructure)
- `scripts/little_loops/mcp_call.py` — `_send_jsonrpc()` (stdio-pipe request/response pattern)
- `scripts/little_loops/cli/loop/_helpers.py` — `launch_background_loop()`, `register_loop_signal_handlers()`
- `hooks/hooks.json` + `hooks/scripts/` — Claude Code's hot-path handlers (pure Bash + jq, confirming the cold-start problem is Python-specific)

## Research Question 1: Has Codex `plugin_hooks` stabilized?

**Finding: `plugin_hooks` status is irrelevant to the wiring path.**

FEAT-1483 confirmed: as of 2026-05-15, Codex feature flags show `hooks: stable` and
`plugin_hooks: under development`. The critical distinction is that the existing Codex
adapter (`hooks/adapters/codex/`) does **not** use `plugin_hooks` — it uses the stable
`hooks` system via `.codex/hooks.json` shell commands. `PreToolUse` and `PostToolUse`
are valid event keys in the stable Codex hooks schema (confirmed by
`hooks/adapters/codex/README.md` event→intent table, which lists both as "Deferred
(hot-path)"). Codex's `plugin_hooks` feature would be relevant only if hooks were
packaged inside Codex plugins — the current adapter architecture does not require that.

**Conclusion**: The stable `hooks` mechanism can wire `PreToolUse` and `PostToolUse` for
Codex today, without waiting for `plugin_hooks` to stabilize. The only blocker is
latency, not API availability.

## Research Question 2: OpenCode long-lived process model

**Finding: The TypeScript layer is resident; the Python layer is not.**

OpenCode's `hooks/adapters/opencode/index.ts` exports a `Plugin` factory:

```ts
const plugin: Plugin = async (ctx) => ({
  "session.created": async (input) => { ... },
  "session.compacted": async (input) => { ... },
});
```

This TypeScript plugin runs as a **long-lived Bun process** for the entire session.
However, each intent dispatch still calls:

```ts
Bun.spawn(["python", "-m", "little_loops.hooks", intent], { ... })
```

A fresh Python subprocess is spawned per event. The Bun layer adds ~1–2ms overhead;
the Python interpreter cold-start adds ~80–120ms (estimated; benchmark pending via
`scripts/tests/bench_opencode_adapter.py`).

**Does OpenCode expose a long-lived Python process API?** No. The `@opencode-ai/plugin`
SDK (v1.2.27) provides an async event-handler map returning from the plugin factory.
There is no stdin-streaming plugin interface that would allow a single Python process
to handle multiple tool events without being re-spawned. The TypeScript layer IS the
long-lived process; getting Python to be long-lived requires a sidecar.

**Conclusion**: Without a sidecar, OpenCode hot-path intents pay Python cold-start on
every tool call. For `post_tool_use` (fire-and-forget), this is invisible to the user.
For `pre_tool_use` (synchronous blocking), this adds ~100ms to every tool call.

## Research Question 3: Sidecar/daemon pattern viability

**Finding: Technically viable; lifecycle management has one open question for Codex.**

The codebase already contains every primitive needed:

| Primitive | Location | Role in sidecar design |
|-----------|----------|------------------------|
| AF_UNIX socket server | `scripts/little_loops/transport.py` `UnixSocketTransport` | IPC transport; bind at `.ll/hooks.sock` |
| JSON request/response | `scripts/little_loops/mcp_call.py` `_send_jsonrpc()` | Newline-delimited JSON protocol |
| Daemon launch | `scripts/little_loops/cli/loop/_helpers.py` `launch_background_loop()` | PID file + `start_new_session=True` |
| Signal handling | `scripts/little_loops/cli/loop/_helpers.py` `register_loop_signal_handlers()` | SIGINT/SIGTERM two-strike shutdown |

### Proposed sidecar design

```
Host (Codex/OpenCode adapter)
    ↓ JSON request over .ll/hooks.sock (newline-delimited)
Sidecar (python -m little_loops.hooks_sidecar, resident)
    ↓ calls _dispatch_table()[intent].handle(event)
    ↑ JSON response: {exit_code, stdout, stderr}
```

- Bind path: `.ll/hooks.sock`
- Protocol: newline-delimited JSON (same shape as `_send_jsonrpc()`)
- Cold-start round-trip: estimated ~5ms vs ~100ms for subprocess spawn
- Both Codex and OpenCode can share one sidecar; host identity travels in the request payload

### Lifecycle management

| Host | Start trigger | Stop trigger | Risk |
|------|--------------|--------------|------|
| OpenCode | First `tool.execute.before` event (lazy start in `spawnIntent`) | TypeScript plugin teardown via `@opencode-ai/plugin` cleanup hook (if any) | If plugin process exits without cleanup, sidecar orphans; PID file enables detection on next start |
| Codex | `SessionStart` hook (already wired) | `Stop` hook (currently deferred) | If `Stop` never fires, sidecar orphans until next session checks PID file and kills stale process |

**Open question for Codex**: `Stop` event is deferred (`hooks/adapters/codex/README.md`).
Without it, the sidecar cannot be stopped cleanly via a hook. Mitigations:
1. Detect stale PID on `SessionStart` and kill it before launching a new sidecar.
2. Use a short session-scoped timeout in the sidecar (exit if no events for N seconds).
3. Accept orphaned sidecars; they exit when the user's shell exits.

### Error handling if sidecar crashes

Adapters must implement fallback to cold-start subprocess spawn when the socket
connection is refused or times out. This adds complexity to both adapters. Without
fallback, a crashed sidecar silently blocks all hot-path hooks.

**Conclusion**: Viable, but adds meaningful complexity (fallback logic, lifecycle
management for Codex `Stop`). The existing primitives reduce implementation risk;
the lifecycle question for Codex is the main open item.

## Research Question 4: Better alternatives

### Compiled shim (Go/Rust)

A statically linked binary (Go or Rust) would start in <1ms — faster than a sidecar
round-trip. Claude Code's hot-path handlers (`hooks/scripts/context-monitor.sh`,
`scratch-pad-redirect.sh`, `check-duplicate-issue-id.sh`) are already pure Bash + jq
with no Python subprocess. This **proves the model works** for Claude Code.

Drawback: hot-path handlers in ll today access Python package internals
(`little_loops.hooks._dispatch_table`, config loading, etc.). Reimplementing in
Go/Rust is impractical for handlers that are currently Python. A compiled shim would
only work for future handlers that are simple enough to rewrite in another language.

**Verdict**: Not recommended for existing Python handlers. Worth revisiting if a
hot-path handler is simple enough to be self-contained (e.g., a pure rate-limit
counter with no Python dependencies).

### Opt-in-only registration

Only add `PreToolUse`/`PostToolUse` matchers to `hooks.json` when a `ll-config.json`
consumer flag is set (e.g., `hooks.pre_tool_use.enabled: true`). No overhead when
nothing is opted in; cold-start tax when opted in.

**Verdict**: Low-effort, minimal risk. Right approach for `pre_tool_use` until
benchmark data justifies the sidecar investment.

### Batch/async (fire-and-forget)

`post_tool_use` fires after the tool has already executed — it does not gate tool
execution. Spawning a Python subprocess fire-and-forget (no `await proc.exited`)
means zero user-visible latency, at the cost of no result propagation. This is safe
for audit logging, metrics, and usage-counting consumers.

`pre_tool_use` MUST be synchronous — it gates execution and can return `deny` or
`ask`. Fire-and-forget is not an option for blocking handlers.

**Verdict**: `post_tool_use` as fire-and-forget is the clearest quick win. Wire it
immediately with no sidecar needed. `pre_tool_use` cannot use this approach.

## Research Question 5: Minimum viable approach

**Short answer**: Wire `post_tool_use` fire-and-forget now. Benchmark `pre_tool_use`
cold-start before committing to a wiring approach for it.

### Step-by-step minimum viable path

1. **Create `scripts/tests/bench_opencode_adapter.py`** — 100 sequential invocations
   of `session_start` (as a `pre_tool_use`-latency proxy) via the OpenCode adapter;
   report min/median/p95/max. This satisfies the README gate before hot-path intents
   are wired. (FEAT-1489 scope.)

2. **Wire `post_tool_use` for Codex and OpenCode as fire-and-forget** — add
   `PostToolUse` matcher to `hooks/adapters/codex/hooks.json`; add
   `tool.execute.after` to `hooks/adapters/opencode/index.ts` `spawnIntent`. Spawn
   the Python subprocess without awaiting exit. Add `post_tool_use.handle()` module
   at `scripts/little_loops/hooks/post_tool_use.py`. (FEAT-1489 scope.)

3. **Interpret benchmark results for `pre_tool_use`**:
   - p95 < 200ms: proceed with opt-in-only cold-start approach for `pre_tool_use`
   - p95 ≥ 400ms: implement sidecar before wiring `pre_tool_use` (follow-up issue)
   - p95 200–399ms: opt-in-only with documented latency cost; sidecar as optional upgrade

4. **Wire `pre_tool_use`** once the benchmark decision is made. File a separate issue
   for sidecar implementation if the benchmark triggers the 2× threshold.

## Recommendation

**Opt-in-only approach, with `post_tool_use` as fire-and-forget. Sidecar deferred.**

### Rationale

| Factor | Weight |
|--------|--------|
| No current consumer exists for either intent on non-Claude-Code hosts | High — no urgency on latency cost |
| `post_tool_use` can be fire-and-forget (zero user-visible overhead) | High — immediate win, no architecture change |
| `pre_tool_use` cold-start (~100ms) adds meaningful latency per tool call | Medium — acceptable with explicit opt-in |
| Sidecar adds ~150 LOC and lifecycle complexity for a problem not yet measured | Medium — invest after benchmark proves it's needed |
| Existing primitives make sidecar straightforward if benchmark mandates it | Low risk — fallback path is clear |

### Decision tree outcome

```
Wire post_tool_use for Codex + OpenCode?
└── YES — fire-and-forget; no blocking; zero user-visible overhead
    └── Action: FEAT-1489 implements PostToolUse (Codex + OpenCode), benchmark script

Wire pre_tool_use for Codex + OpenCode?
└── BENCHMARK FIRST
    ├── p95 < 200ms → wire with opt-in-only config flag (FEAT-1489 or follow-up)
    └── p95 ≥ 400ms → implement sidecar first (file new issue), then wire

Implement sidecar now?
└── NO — defer until benchmark proves necessary
    └── If needed: use UnixSocketTransport + launch_background_loop() pattern
```

### Child issues filed

- **FEAT-1489** — Wire `post_tool_use` for Codex and OpenCode; create benchmark
  script; wire `pre_tool_use` as opt-in if benchmark clears 200ms threshold.

## Gating recommendation for `HOST_COMPATIBILITY.md`

- `post_tool_use` cells for OpenCode and Codex: change from `(deferred)[^hot]` to
  `(deferred)[^hot]` — unchanged label, but the `[^hot]` footnote text should note
  that the decision is "wire as fire-and-forget via FEAT-1489; benchmark pending."
- `pre_tool_use` cells: remain `(deferred)[^hot]` until benchmark completes.
- Update the `[^hot]` footnote to reference FEAT-1489 and this research note.
- Add FEAT-1488 to the tracking issues table.
