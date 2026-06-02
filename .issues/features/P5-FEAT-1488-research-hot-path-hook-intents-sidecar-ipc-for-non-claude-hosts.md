---
id: FEAT-1488
type: FEAT
priority: P5
status: done
captured_at: '2026-05-16T01:06:58Z'
completed_at: '2026-05-16T01:32:44Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
decision_needed: false
testable: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1488: Research Hot-Path Hook Intents (pre_tool_use / post_tool_use) for Non-Claude-Code Hosts

## Summary

`pre_tool_use` and `post_tool_use` fire on every tool invocation. For non-Claude-Code
hosts (Codex, OpenCode), the current shell-out approach (~100ms Python cold-start per
call) makes these hooks impractical at scale. EPIC-1463 explicitly defers them
"until the latency/sidecar question is answered for all non-Claude-Code hosts
simultaneously." This spike produces that answer: a written decision on whether a
sidecar/IPC pattern is viable, what the host APIs allow, and what the implementation
path looks like.

## Current Behavior

`pre_tool_use` and `post_tool_use` are wired for Claude Code only. The Codex and
OpenCode adapter registrations mark these intents `(deferred)` in
`docs/reference/HOST_COMPATIBILITY.md`. No current ll feature consumes these intents
on non-Claude-Code hosts.

## Expected Behavior

After this spike:
- A research note at `thoughts/research/hot-path-hook-intents.md` documents findings
  for each host (Codex, OpenCode).
- A written decision on approach: sidecar/daemon, compiled shim, opt-in-only
  registration, or "not viable yet."
- EPIC-1463 and `HOST_COMPATIBILITY.md` updated with the decision and any new
  child issues filed if implementation is greenlit.

## Use Case

**Who**: Maintainer or contributor wanting to wire `pre_tool_use` / `post_tool_use` for Codex or OpenCode

**Context**: EPIC-1463 defers hot-path hooks for non-Claude-Code hosts until the latency/sidecar question is answered; every future consumer (token budgeting, tool-call audit logging, rate-limit enforcement) hits this blocker

**Goal**: Obtain a written, evidence-backed decision on whether a sidecar/IPC pattern (or alternative) is viable so implementation work can be scoped or permanently deferred

**Outcome**: A committed research note at `thoughts/research/hot-path-hook-intents.md` with a recommendation, plus follow-on child issues filed or EPIC-1463 scope updated accordingly

## Acceptance Criteria

- [ ] `thoughts/research/hot-path-hook-intents.md` exists and covers all five research questions from the Proposed Solution
- [ ] A written recommendation is included: one of sidecar/daemon, compiled shim, opt-in-only, batch/async, or "not viable yet"
- [ ] `docs/reference/HOST_COMPATIBILITY.md` and EPIC-1463 updated with the decision outcome
- [ ] If implementation is greenlit, at least one child issue is filed with concrete scope

## Motivation

Hot-path hooks unlock features that need per-tool observability: token budgeting,
tool-call audit logging, rate-limit enforcement at the tool level. These are blocked
on the latency problem. The decision should be written down rather than re-derived
each time someone asks why the hooks are deferred.

## Proposed Solution

Research the following questions and produce a recommendation:

1. **Has Codex `plugin_hooks` stabilized?** As of 2026-05-15 research (FEAT-1483),
   `plugin_hooks` was marked "under development." If it has not stabilized, the
   question is moot for Codex until it does.

2. **What does the OpenCode equivalent look like?** The OpenCode TypeScript adapter
   (FEAT-1451) ships as shell-out for SessionStart/PreCompact. Does OpenCode expose
   a long-lived plugin process model that would avoid cold-start on hot-path events?

3. **Is a sidecar/daemon pattern viable?** A resident Python process contacted via
   Unix socket would drop per-call cost from ~100ms to ~5ms. Evaluate:
   - Process lifetime management (how does the sidecar start/stop with the host session?)
   - IPC protocol (stdio pipe vs. Unix socket vs. named pipe)
   - Error handling if the sidecar crashes mid-session
   - Whether both Codex and OpenCode can wire to the same sidecar or need separate ones

4. **Are there better alternatives?**
   - Compiled shim (Go/Rust): sub-millisecond startup, no sidecar complexity
   - Opt-in only: only register hooks when a specific consumer is active (avoids
     the tax when nothing needs them)
   - Batch/async: fire-and-forget for `post_tool_use`, accept eventual consistency

5. **What is the minimum viable approach?** If no perfect solution exists, what is
   good enough to unblock the first concrete consumer?

## API/Interface

N/A — Research spike only; no public API changes in this issue. Any implementation work will be scoped in follow-on child issues.

## Integration Map

### Files to Create

- `thoughts/research/hot-path-hook-intents.md` — findings and decision
- `scripts/tests/bench_opencode_adapter.py` — benchmark script (referenced in OpenCode README `## Latency Target` and issue Proposed Solution; does not exist yet; required before hot-path intents can be wired)

_If implementation is greenlit (post-decision):_
- `scripts/little_loops/hooks/pre_tool_use.py` — new handler module; follow pattern of `scripts/little_loops/hooks/session_start.py`
- `scripts/little_loops/hooks/post_tool_use.py` — new handler module; same pattern
- `hooks/adapters/codex/pre-tool-use.sh` — bash adapter script (follow `prompt-submit.sh` pattern)
- `hooks/adapters/codex/post-tool-use.sh` — bash adapter script
- `scripts/tests/test_hook_pre_tool_use.py` — unit tests for `handle()` in `pre_tool_use.py`; follow `test_hook_session_start.py` pattern
- `scripts/tests/test_hook_post_tool_use.py` — unit tests for `post_tool_use.py`

### Files to Modify (post-decision, if implementation is greenlit)

- `docs/reference/HOST_COMPATIBILITY.md` — flip deferred cells, add child issue refs
- `hooks/adapters/codex/hooks.json` — add pre/post_tool_use matchers (note: changes to command strings require user re-trust per Codex trust-hash model)
- `hooks/adapters/opencode/index.ts` — add `"pre_tool_use"` / `"post_tool_use"` to `Intent` type alias; add `tool.execute.before` / `tool.execute.after` handlers in the `plugin` object
- `scripts/little_loops/hooks/__init__.py` — add `"pre_tool_use"` and `"post_tool_use"` entries to `_dispatch_table()`; update `_USAGE` string (currently lists only `pre_compact, session_start, user_prompt_submit`)
- `docs/claude-code/write-a-hook.md` — remove/update `## Limitations and troubleshooting` deferred-status bullet; update `## Core handler vs. extension intent` table to list new built-ins [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` — add per-intent payload notes for `pre_tool_use` and `post_tool_use` under `#### Per-intent payload notes` (currently only covers `pre_compact` and `session_start`) [Agent 2 finding]
- `skills/workflow-automation-proposer/SKILL.md` — update "For hooks:" block (lines 114–124) which names `PreToolUse`/`PostToolUse` as example intent types, to reflect that they are now dispatched built-ins [Agent 2 finding]
- EPIC-1463 — update `## Out of scope` block and `## Children` list with the decision outcome

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/extension.py` — reads and writes `_HOOK_INTENT_REGISTRY`; if new built-in intents overlap with extension-registered names, `wire_extensions()` raises `ValueError` (conflict detection) [Agent 1 finding]
- `scripts/little_loops/hooks/__main__.py` — `python -m little_loops.hooks` module entry point; `main_hooks()` is invoked here; no changes expected but acts as integration surface [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

_Existing tests to update (if implementation is greenlit):_
- `scripts/tests/test_hook_intents.py` — `TestHooksMainModule.test_dispatch_unknown_intent` error message lists available intents; adding new built-ins changes the sorted output; add `test_dispatch_pre_tool_use_happy_path` and `test_dispatch_post_tool_use_happy_path` following `test_dispatch_pre_compact_happy_path` pattern [Agent 3 finding]
- `scripts/tests/test_opencode_adapter.py` — add test for `tool.execute.before` / `tool.execute.after` via `_write_driver()` helper; existing `test_session_compacted_writes_state_file` may break if `spawnIntent()` or Plugin export shape changes [Agent 3 finding]
- `scripts/tests/test_codex_adapter.py` — add assertion for new `PreToolUse` / `PostToolUse` keys in `hooks.json`; existing `test_hooks_json_has_user_prompt_submit` is the pattern to follow [Agent 3 finding]

_Tests at risk of breaking (if implementation changes adapter interfaces):_
- `scripts/tests/test_opencode_adapter.py` — `test_session_compacted_writes_state_file` and `test_session_created_runs_session_start` invoke real `index.ts` via Bun; structural changes to `spawnIntent()` or the Plugin export will break the `_write_driver` pattern [Agent 3 finding]
- `scripts/tests/test_codex_adapter.py` — `test_hooks_json_references_plugin_root_placeholder` and `test_hooks_json_uses_matcher_startup` break if placeholder convention or `SessionStart` matcher key is removed [Agent 3 finding]
- `scripts/tests/test_feat1457_doc_wiring.py` — asserts `"_HOOK_INTENT_REGISTRY"` string appears in `docs/reference/API.md` and `docs/ARCHITECTURE.md`; any doc update that inadvertently removes this string breaks these tests [Agent 2 finding]

_New benchmark deliverable:_
- `scripts/tests/bench_opencode_adapter.py` — does not exist yet; required by `hooks/adapters/opencode/README.md ## Latency Target` before hot-path intents may be wired; create alongside the research note [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Dispatch extension points (where new intents plug in):**
- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` merges `_HOOK_INTENT_REGISTRY` with built-ins; `_register_hook_intents()` is the extension-registration entry point. Adding `pre_tool_use`/`post_tool_use` means adding entries here and corresponding handler modules.
- `scripts/little_loops/hooks/types.py` — `LLHookEvent` and `LLHookResult` already define a `decision` field (`"allow"` / `"deny"` / `"ask"`) that is typed but unused by any handler today — the wire format is already sidecar-ready.

**OpenCode's existing dispatch function (concrete extension target):**
- `hooks/adapters/opencode/index.ts` — `spawnIntent()`: calls `Bun.spawn(["python", "-m", "little_loops.hooks", intent], ...)` with `stdin: "pipe"` per event; the `Intent` type alias currently excludes `"pre_tool_use"` / `"post_tool_use"`. The OpenCode plugin process is long-lived (resident in Bun runtime) but each event still spawns a fresh Python process.
- `hooks/adapters/opencode/README.md` — documents the latency gate: ≤200ms p95 target; if measured p95 ≥ 400ms, a persistent sidecar must be proposed before hot-path intents are wired. Benchmark script location: `scripts/tests/bench_opencode_adapter.py` (does not exist yet — a deliverable of follow-on work).

**Codex trust model constraint:**
- `hooks/adapters/codex/README.md` — Codex hashes the **command string** in `hooks.json`, not the adapter script body. Any sidecar design must keep the command string stable; changes to `hooks.json` command strings invalidate trust and require user re-approval.

**Existing IPC / socket infrastructure:**
- `scripts/little_loops/transport.py` — `UnixSocketTransport`: existing `AF_UNIX` + `SOCK_STREAM` server bound at `.ll/events.sock`; fan-out, daemon threads, bounded per-client queue. Currently wired only to the FSM event bus — not the hook dispatch path. Provides a working reference implementation for `socket.bind`, `socket.listen`, accept loop, shutdown, and path cleanup.
- `scripts/little_loops/mcp_call.py` — `_send_jsonrpc()`: the codebase's only existing request/response stdio-pipe protocol. Uses `subprocess.Popen` with `stdin=PIPE, stdout=PIPE` and a deadline `readline()` loop. Direct analogue to how a sidecar IPC protocol would work.

**Daemon lifecycle reference:**
- `scripts/little_loops/cli/loop/_helpers.py` — `launch_background_loop()`: re-executes as `Popen(..., start_new_session=True, stdin=DEVNULL)` and writes a PID file. `register_loop_signal_handlers()` handles SIGINT/SIGTERM with a two-strike pattern (first signal requests shutdown; second force-exits). This is the pattern a sidecar daemon should follow.
- `scripts/little_loops/cli/loop/lifecycle.py` — `_read_pid_file()` + `cmd_stop()`: liveness check via `os.kill(pid, 0)`; PID file cleanup on stop. Maps directly to sidecar lifecycle management.

**Why Claude Code's PreToolUse/PostToolUse avoids cold-start (key data point for "compiled shim" option):**
- `hooks/hooks.json` + `hooks/scripts/context-monitor.sh`, `scratch-pad-redirect.sh`, `check-duplicate-issue-id.sh` — Claude Code's hot-path handlers are **pure bash + jq**, with no Python subprocess. Only `issue-completion-log.sh` invokes `python3 -c` inline, and only conditionally. This confirms that the cold-start problem is specific to the Python dispatcher pattern used by Codex/OpenCode adapters — a compiled shim (Go/Rust) or pure-shell handler would eliminate it without any sidecar complexity.

## Implementation Steps

1. Check Codex changelog / release notes for `plugin_hooks` status update
2. Check OpenCode plugin API docs for long-lived process model
3. Prototype sidecar startup/teardown in one adapter (Codex or OpenCode)
4. Benchmark: cold-start vs. sidecar IPC round-trip latency (target: ≤10ms)
5. Write `thoughts/research/hot-path-hook-intents.md` with findings + recommendation
6. File child implementation issue(s) if greenlit, or update EPIC-1463 scope if deferred again

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Codex `plugin_hooks` baseline** — `thoughts/research/codex-command-discovery.md` documents the FEAT-1483 finding: `plugin_hooks` was "under development" as of 2026-05-15. Step 1 should diff against that baseline (check Codex CLI release notes since that date).

2. **OpenCode process model** — `hooks/adapters/opencode/index.ts` `spawnIntent()` shows the current model: the TypeScript plugin is long-lived (resident in Bun), but it still calls `Bun.spawn(["python", "-m", "little_loops.hooks", intent])` per event — no long-lived Python process today. Check whether OpenCode exposes a native stdio-plugin API that would allow a single Python process to handle multiple tool events without respawning.

3. **Sidecar prototype starting point** — `scripts/little_loops/transport.py` `UnixSocketTransport` is the existing AF_UNIX socket server in the package; use it as the IPC infrastructure template (bind at `.ll/hooks.sock`, request/response via newline-delimited JSON following `scripts/little_loops/mcp_call.py` `_send_jsonrpc()`). For lifecycle, follow `scripts/little_loops/cli/loop/_helpers.py` `launch_background_loop()` (PID file + `start_new_session=True`) and `register_loop_signal_handlers()` (SIGINT/SIGTERM two-strike).

4. **Benchmark target and decision rule** — `hooks/adapters/opencode/README.md` specifies ≤200ms p95 end-to-end for cold-start; if p95 ≥ 400ms, a sidecar is required before wiring hot-path intents. Add benchmark measurements to the research note using `scripts/tests/bench_opencode_adapter.py` (file to be created as part of benchmarking work). The sidecar IPC target is ≤10ms round-trip (per FEAT-1488 Proposed Solution); measure both and include in the research note.

5. **Research note skeleton** — `thoughts/research/hot-path-hook-intents.md` should cover: (a) Codex `plugin_hooks` status, (b) OpenCode long-lived plugin model viability, (c) sidecar IPC benchmark results, (d) alternatives evaluated (compiled shim, opt-in-only, batch/async), (e) recommendation with rationale.
   - **Format**: Follow the format of existing research notes in `thoughts/research/` — YAML-like header (`Status`, `Last verified`, `Research issue`, version field), `## Sources` section, findings sections, and a terminal `## Decision tree outcome` or `## Gating recommendation` section. Do NOT use `---` frontmatter; those notes use plain-text headers.

6. **Wiring new intents (if greenlit)** — `scripts/little_loops/hooks/__init__.py` `_dispatch_table()` is where `"pre_tool_use"` and `"post_tool_use"` entries must be added; create handler modules at `scripts/little_loops/hooks/pre_tool_use.py` and `post_tool_use.py` following the pattern of `scripts/little_loops/hooks/session_start.py`. Also extend the `Intent` type alias in `hooks/adapters/opencode/index.ts` to include these intents.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation if greenlit:_

7. Create `scripts/tests/bench_opencode_adapter.py` — benchmark script measuring cold-start vs. sidecar IPC round-trip; required by `hooks/adapters/opencode/README.md ## Latency Target` gate (200ms p95 / 400ms hard limit) before hot-path intents may be wired; run it and record results in the research note
8. Update `scripts/little_loops/hooks/__init__.py` `_USAGE` string — currently hardcodes `"Available intents: pre_compact, session_start, user_prompt_submit"`; add `pre_tool_use` and `post_tool_use` to this list once they are in `_dispatch_table()`
9. Update `docs/claude-code/write-a-hook.md` — remove `## Limitations and troubleshooting` deferred-status bullet for OpenCode hot-path intents; update `## Core handler vs. extension intent` table
10. Update `docs/reference/EVENT-SCHEMA.md` — add `pre_tool_use` and `post_tool_use` per-intent payload notes under `#### Per-intent payload notes`
11. Update `skills/workflow-automation-proposer/SKILL.md` — revise "For hooks:" block (lines 114–124) to reflect that `pre_tool_use`/`post_tool_use` are dispatched built-ins
12. Update `scripts/tests/test_hook_intents.py` — add `test_dispatch_pre_tool_use_happy_path` and `test_dispatch_post_tool_use_happy_path`; fix `test_dispatch_unknown_intent` error message assertion once new intents appear in the sorted list

## Impact

- **Priority**: P5 — no current consumer; purely unblocking future work
- **Effort**: Small (research note) + Medium (prototype if pursued)
- **Risk**: Low — additive only; no existing behavior changes
- **Breaking Change**: No

## Related Key Documentation

| Document | Why relevant |
| --- | --- |
| [docs/reference/HOST_COMPATIBILITY.md](../../docs/reference/HOST_COMPATIBILITY.md) | Parity matrix with the deferred cells this spike targets |
| [thoughts/research/codex-command-discovery.md](../../thoughts/research/codex-command-discovery.md) | Prior Codex research; includes `plugin_hooks: under development` finding |
| [hooks/adapters/codex/README.md](../../hooks/adapters/codex/README.md) | Codex adapter contract any sidecar must satisfy |
| [hooks/adapters/opencode/README.md](../../hooks/adapters/opencode/README.md) | Latency target (≤200ms p95), sidecar decision rule (≥400ms triggers sidecar), benchmark script location |
| [hooks/adapters/opencode/index.ts](../../hooks/adapters/opencode/index.ts) | `spawnIntent()` — the OpenCode dispatch function to extend for hot-path events |
| [scripts/little_loops/hooks/__init__.py](../../scripts/little_loops/hooks/__init__.py) | `_dispatch_table()` / `_register_hook_intents()` — where new intents plug in |
| [scripts/little_loops/hooks/types.py](../../scripts/little_loops/hooks/types.py) | `LLHookEvent` / `LLHookResult` — wire types; `decision` field already supports allow/deny/ask |
| [scripts/little_loops/transport.py](../../scripts/little_loops/transport.py) | `UnixSocketTransport` — existing AF_UNIX socket infrastructure; IPC template for sidecar design |
| [scripts/little_loops/mcp_call.py](../../scripts/little_loops/mcp_call.py) | `_send_jsonrpc()` — codebase's only request/response stdio-pipe protocol; sidecar IPC analogue |
| [scripts/little_loops/cli/loop/_helpers.py](../../scripts/little_loops/cli/loop/_helpers.py) | `launch_background_loop()` / `register_loop_signal_handlers()` — daemon lifecycle reference |
| [.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md](../epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md) | Parent epic; explicitly gates on this question |

## Labels

codex, opencode, host-compat, hooks, research

## Session Log
- `/ll:ready-issue` - 2026-05-16T01:30:35 - `a9295ab3-e370-4d50-972c-f57b3351c85c.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00Z - `ff5a9d33-4fc9-4e41-bd42-e698ee5d9bc4.jsonl`
- `/ll:wire-issue` - 2026-05-16T01:26:43 - `0600aa3b-3387-43bd-8031-c99dd738f678.jsonl`
- `/ll:refine-issue` - 2026-05-16T01:20:08 - `f61156e5-c934-4f2e-9979-6661ce4645b5.jsonl`
- `/ll:format-issue` - 2026-05-16T01:12:39 - `5d7ee9ab-8a73-4e53-ab38-769eb0a66c86.jsonl`

- `/ll:capture-issue` - 2026-05-16T01:06:58Z - `2d955b55-acdc-43a2-860d-7cf32946c8df.jsonl`

## Resolution

Research complete. Decision: **opt-in-only with `post_tool_use` as fire-and-forget; sidecar deferred.**

- `thoughts/research/hot-path-hook-intents.md` created with findings on all five research questions
- Codex `plugin_hooks` moot — stable `hooks` API can wire `PreToolUse`/`PostToolUse` today
- OpenCode TypeScript layer is long-lived; Python cold-start (~100ms) still applies per event
- Sidecar viable with existing `UnixSocketTransport` + `launch_background_loop()` primitives; deferred until benchmark (p95 ≥ 400ms) proves necessary
- `post_tool_use` wired as fire-and-forget (zero user-visible latency)
- `scripts/tests/bench_opencode_adapter.py` created to measure cold-start p95
- `docs/reference/HOST_COMPATIBILITY.md` and EPIC-1463 updated with decision outcome
- FEAT-1489 filed for implementation

## Session Log
- `/ll:manage-issue` - 2026-05-16T01:32:44Z - current session

- `/ll:ready-issue` - 2026-05-16T01:30:35 - `a9295ab3-e370-4d50-972c-f57b3351c85c.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00Z - `ff5a9d33-4fc9-4e41-bd42-e698ee5d9bc4.jsonl`
- `/ll:wire-issue` - 2026-05-16T01:26:43 - `0600aa3b-3387-43bd-8031-c99dd738f678.jsonl`
- `/ll:refine-issue` - 2026-05-16T01:20:08 - `f61156e5-c934-4f2e-9979-6661ce4645b5.jsonl`
- `/ll:format-issue` - 2026-05-16T01:12:39 - `5d7ee9ab-8a73-4e53-ab38-769eb0a66c86.jsonl`
- `/ll:capture-issue` - 2026-05-16T01:06:58Z - `2d955b55-acdc-43a2-860d-7cf32946c8df.jsonl`

## Status
- **Status**: Done
- **Completed**: 2026-05-16
- **Discovered**: 2026-05-16
- **Discovered by**: capture-issue
