---
id: ENH-2296
title: 'FSM executor: opt-in --bare + --plugin-dir mode for prompt-state LLM invocations'
priority: P4
type: ENH
status: deferred
captured_at: '2026-06-25T00:00:00Z'
discovered_date: '2026-06-25'
discovered_by: conversation
labels:
- fsm
- host-runner
- loops
- performance
---

# ENH-2296: FSM executor opt-in --bare + --plugin-dir mode for prompt-state LLM invocations

## Summary

The `claude` CLI exposes a `--bare` minimal mode that skips hooks, LSP, plugin
sync, attribution, auto-memory, background prefetches, keychain reads, and
CLAUDE.md auto-discovery (sets `CLAUDE_CODE_SIMPLE=1`). For the FSM loop
executor's per-state LLM calls (`prompt` / `slash_command` states routed through
`ClaudeCodeRunner.build_streaming`), `--bare` paired with `--plugin-dir` (to keep
ll's own skills resolvable) and `--add-dir` (to restore CLAUDE.md context) could
isolate loop sub-invocations from the host's hooks/auto-memory and improve
prompt-cache reuse and startup latency.

This is captured as a **deferred** speculative optimization — there is no measured
pain driving it today, and a hard auth constraint (below) means it can only ever
be an opt-in, gated feature rather than a default.

## Current Behavior

`scripts/little_loops/fsm/executor.py` dispatches `prompt` and `slash_command`
states (`LLM_ACTION_TYPES`, executor.py:92) through the host runner's
`build_streaming`. `ClaudeCodeRunner.build_streaming`
(`scripts/little_loops/host_runner.py:234`) emits:

```
--dangerously-skip-permissions --verbose --output-format stream-json [-p <prompt>] ...
```

with env `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`, `LL_NON_INTERACTIVE`,
`DANGEROUSLY_SKIP_PERMISSIONS`. It does **not** pass `--bare`, does **not**
inject an API key, and inherits the user's ambient Claude auth (OAuth/keychain or
`ANTHROPIC_API_KEY`). Every loop iteration's action call plus its LLM evaluators
runs a full Claude session (hooks, plugin sync, CLAUDE.md discovery, auto-memory).

## Motivation

Potential benefits of `--bare` for loop sub-invocations:

- **Hook isolation** — host lifecycle hooks (e.g. `optimize-prompt-hook`,
  `session_start`) don't re-fire inside automated loop calls.
- **Auto-memory isolation** — automated runs don't write to the user's
  auto-memory.
- **Prompt-cache reuse** — a deterministic, minimal system prompt improves cache
  hit rates across iterations.
- **Lower startup latency** — skips plugin sync, background prefetches, keychain
  reads per invocation.

`--plugin-dir` closes the obvious objection (ll's `/ll:*` skills must still
resolve in `slash_command` states); `--add-dir` restores project CLAUDE.md
context for meta-loops.

## The Blocking Constraint: Auth

`--bare` makes Anthropic auth **strictly `ANTHROPIC_API_KEY` or apiKeyHelper —
OAuth and keychain are never read**. `--plugin-dir` does not change this.
Because `build_streaming` injects no API key and inherits ambient auth, and even
the headless lanes (`ll-auto` / `ll-parallel` / cron) inherit the user's login
(often OAuth/subscription), enabling `--bare` unconditionally would silently
break authentication for any user not on an `ANTHROPIC_API_KEY`.

Therefore this can only be an **opt-in, API-key-gated** feature — it cannot be a
default, which caps the addressable benefit to the API-key segment.

## Proposed Solution (when un-deferred)

1. Add a config flag, e.g. `loops.bare_invocations` (default `false`).
2. Thread an optional `bare: bool` (plus resolved `plugin_dir` / `add_dir`
   paths) into `ClaudeCodeRunner.build_streaming`. When enabled, append
   `--bare --plugin-dir <ll-plugin> --add-dir <claude-md-dirs>`.
3. **Gate activation** on `ANTHROPIC_API_KEY` actually being present in the
   environment; fall back to the current non-bare invocation otherwise (never
   silently break OAuth users).
4. **Scope to pure `prompt` states only** — never `slash_command` states unless
   `--plugin-dir` resolution to the ll plugin is verified, since bare skips
   plugin sync.
5. Tests across auth modes (API-key present vs absent) and across
   `prompt` vs `slash_command` action modes.

## Defer Rationale

- No measured pain (hook recursion, auto-memory pollution, or startup latency)
  has been observed in loop runs to date.
- The auth gate means two maintained code paths for a subset of users — poor
  cost/benefit until the automation lanes are deliberately standardized on
  `ANTHROPIC_API_KEY`.

**Pull this forward when** either (a) the headless lanes
(`ll-auto`/`ll-parallel`/cron) are moved onto API-key auth deliberately — at
which point `--bare` becomes the natural default *for that lane* and the value
jumps from "minority gate" to "whole automation surface" — or (b) hook-recursion
/ auto-memory pollution / per-state startup latency is actually observed in loop
runs.

## Scope Boundaries

- Touches only `ClaudeCodeRunner.build_streaming` (and a `loops` config key);
  no change to FSM routing/evaluator logic.
- No change to OAuth/subscription default path — that remains the fallback.
- Non-Claude hosts (Codex/opencode/pi) unaffected.

## Impact

- **Priority**: P4 — speculative latency/cleanliness optimization, no driving
  pain.
- **Effort**: Medium — config flag, API-key detection, `--plugin-dir`/`--add-dir`
  threading, prompt-vs-slash-command scoping, multi-auth-mode tests.
- **Risk**: Medium if mis-scoped (auth break); Low if the API-key gate and
  fallback are implemented as specified.
- **Breaking Change**: No (opt-in, default off).

## Status

**Deferred** | Created: 2026-06-25 | Priority: P4

## Session Log
- conversation capture - 2026-06-25
