# oh-my-pi (omp) Adapter for little-loops Hook Intents

Thin TypeScript module that lets [oh-my-pi](https://omp.sh) (`omp`) delegate
to the host-agnostic Python hook dispatcher in `little_loops.hooks`. omp
hooks are native Bun/TS modules loaded via `HookAPI.on()` registration
(`export default function(pi: HookAPI) { pi.on(...) }`), not JSON config or
shell shims, so this adapter follows the transport pattern of
`hooks/adapters/opencode/index.ts` (`spawnIntent()` helper) rather than the
Bash-shim pattern of `hooks/adapters/codex/`. No logic lives in this
adapter; it is purely a transport.

> **Packaging note**: per the pip-wheel split established by BUG-2275
> (`pyproject.toml`'s `include` only ships `little_loops/**`), the runnable
> shim lives at
> [`scripts/little_loops/hooks/adapters/omp/`](../../../scripts/little_loops/hooks/adapters/omp/)
> — this README is the only file this adapter keeps at repo-root
> `hooks/adapters/omp/`.

## Installation

There is no `ll-init --hosts omp` auto-install (Option B — see
[FEAT-2261](../../../.issues/features/P4-FEAT-2261-omp-hook-adapter.md)'s
Decision Rationale; `hooks/adapters/opencode/` is the confirmed precedent for
a recognized host with a real adapter directory but no writer/generated
config). Install manually:

```bash
cd scripts/little_loops/hooks/adapters/omp
bun install
```

Then register the hook module with omp per its hook-loading convention
(a hook file exporting a default `function(pi: HookAPI)`. e.g. drop or
symlink `index.ts` where omp discovers project/user hooks, per omp's own
hook-discovery docs).

The adapter resolves its interpreter as `$LL_PYTHON` → `python3` → `python`
(BUG-2921), matching the shell adapters and the OpenCode adapter. Set
`LL_PYTHON` to pin a specific interpreter; otherwise the first of
`python3`/`python` on the ambient `PATH` wins. Ensure `little_loops` is
installed in that interpreter (`pip install -e ./scripts`).

## Event → Intent Mapping

Full native-event detail and advisory/blocking semantics:
`thoughts/research/omp-hook-event-parity.md` (FEAT-2263).

| omp event (`HookAPI.on()` key) | ll intent | Python invocation | Status |
| --- | --- | --- | --- |
| `session_start` | `session_start` | `python -m little_loops.hooks session_start` | Implemented |
| `tool_result` | `post_tool_use` | `python -m little_loops.hooks post_tool_use` | Implemented (fire-and-forget, FEAT-1489 precedent) |
| `tool_call` | `pre_tool_use` | `python -m little_loops.hooks pre_tool_use` | Deferred — richest blocking+input-revision candidate of any host audited, but no cold-start latency budget has been measured for omp yet (see OpenCode's Latency Target section for the precedent this issue did not repeat) |
| `session_before_compact` (1st registration) | `pre_compact` | `python -m little_loops.hooks pre_compact` | Deferred — out of this issue's acceptance criteria |
| `session_before_compact` (2nd registration) | `pre_compact_handoff` | `python -m little_loops.hooks pre_compact_handoff` | Deferred — same native event as `pre_compact`, second handler registration (matches every other host's pattern) |
| `before_agent_start` | `user_prompt_submit` | `python -m little_loops.hooks user_prompt_submit` | Deferred — injection-only native event (cannot block/reject), narrower than Claude Code's |
| `session_shutdown` | `session_end` | `python -m little_loops.hooks session_end` | Deferred — hard-timeout behavior on `session_shutdown` handlers is unverified; safer to dispatch from the next `session_start` per the `[^ssend]` pattern other hosts use |

## Host Identification

The adapter sets `LL_HOOK_HOST=omp` on the subprocess environment. The
Python dispatcher reads this env var to populate `LLHookEvent.host` so that
core handlers can branch on host-specific quirks if needed. Without this
var, the dispatcher defaults to `host="claude-code"`.

## Subprocess Contract

| Channel    | Direction         | Format                                                                          |
| ---------- | ----------------- | ------------------------------------------------------------------------------- |
| stdin      | adapter → python  | Raw JSON dict — the native omp event object (`event` passed to the `HookAPI.on()` handler) |
| stdout     | python → adapter  | Raw bytes; empty for the two wired intents (`session_start`, `post_tool_use`) — neither has a documented stdout-consuming return path on omp today |
| stderr     | python → adapter  | Human-readable status/feedback lines, forwarded via `console.error`             |
| exit code  | python → adapter  | `0` = pass, `2` = block + inject feedback, `1` = unknown intent (hard error); `session_start`'s handler is advisory-only (`HookHandler<SessionStartEvent>` returns `void`), so the adapter does not act on exit code for that intent |
| cwd        | adapter sets      | omp's `HookContext.cwd` — Python handlers resolve `.ll/ll-config.json` (or `.omp/ll-config.json`, FEAT-2262) and write state files relative to it |

## Host Quirks

- **No cancel path on `session_start`**: `HookHandler<SessionStartEvent>`
  returns `void` on omp — there is no `exit_code=2` block/inject convention
  to honor for this intent, unlike Codex/OpenCode. The adapter forwards
  stderr for visibility only.
- **`tool_result` is fire-and-forget**: `spawnIntent()` is called without
  `await`, matching `hooks/adapters/opencode/index.ts`'s
  `tool.execute.after` handler (FEAT-1489) — the omp tool-result path never
  blocks on the Python handler's SQLite write.

## Smoke Test

The Python-side integration test at
`scripts/tests/test_omp_adapter.py` exercises the adapter end-to-end via a
synthetic Bun driver that stubs `HookAPI.on()` and invokes the registered
handlers directly (mirroring `test_opencode_adapter.py`'s `_write_driver()`
pattern). It is automatically skipped if Bun is not available on `PATH`. The
same module gates `bun x tsc --noEmit -p tsconfig.json`
(`TestOmpAdapterTypecheck`), so the adapter's `strict: true` typecheck runs
as part of `python -m pytest scripts/tests/`.

## Related

- Parent epic: `EPIC-2258` (oh-my-pi host adapter tracking)
- Dependency: `FEAT-2263` (omp hook-event parity audit — supplies the
  event mapping above)
- Sibling adapter: [`hooks/adapters/opencode/`](../opencode/) (TS/Bun plugin
  — the structural analog this adapter's transport shape follows)
- Sibling adapter: [`hooks/adapters/codex/`](../codex/) (Bash shim — the
  README skeleton and 4-column mapping-table shape this file follows)
