---
id: FEAT-3458
priority: P3
type: FEAT
status: open
discovered_date: 2026-09-11
discovered_by: capture-issue
confidence_score: 85
outcome_confidence: 80
unproven_mechanism: true
decision_needed: false
reconcile_attempted: true
blocked_by:
- EPIC-3299
- EPIC-3212
---

# FEAT-3458: Serve `html-website-generator` Artifacts via `LocalBridgeTransport` with Interaction Routing

## Summary

Replace the copy/paste transport in `html-website-generator` artifacts with a real local backend. Today the Message Stream triage console (`scripts/little_loops/loops/html-website-generator.yaml`, FEAT-1023) is a static `file://` page whose action buttons copy slash commands (`/ll:analyze-workflows`, etc.) to the clipboard for the user to paste into Claude Code. The infrastructure to do better already exists — `LocalBridgeTransport` (transport.py:721) provides bidirectional localhost HTTP/SSE with a `POST /{token}/interaction` endpoint — it's just not wired into this artifact generator.

## Current Behavior

After `html-website-generator` produces `${output_dir}/index.html`:

1. User opens the file directly in a browser (`file://`).
2. Pastes `ll-messages -n 100 --stdout` output into the textarea.
3. Selects messages and clicks **Copy selected** — gets a clipboard payload.
4. To run `analyze-workflows`, `propose-automations`, or `analyze-history`, clicks the action button, which copies a slash command to clipboard.
5. User pastes that command into Claude Code in another window.
6. Round-trip latency, two application contexts, easy to forget which clipboard slot holds what.

## Expected Behavior

After the loop's `done` state, the generator either:

- **(a)** auto-spawns `ll-artifact serve-run --run-dir ${context.output_dir}`, OR
- **(b)** prints a one-shot command (`ll-artifact serve-run <path>`) for the user to run manually.

Either path binds `LocalBridgeTransport` on `127.0.0.1` (per the `events.bridge.port` config, default `8766`), serves the artifact under `/{token}/`, and prints the URL. The page's action buttons `fetch('{interaction_url}', {method:'POST', body:JSON.stringify({action:'analyze-workflows'})})` instead of copying. The server dispatches to the underlying CLI as a foreground subprocess, streams stdout/stderr lines back as SSE `data:` events tagged with the request id, and renders the result inline in the page (collapsible log panel below the action button).

Dispatch table for v1:

| Action button              | Dispatched command               | Input                          |
|----------------------------|----------------------------------|--------------------------------|
| `Analyze workflows`        | `ll-analyze-workflows`           | (none — reads from history)    |
| `Propose automations`      | `ll-workflow-automation-proposer` | requires `analyze-workflows` first |
| `Analyze history`          | `ll-analyze-history`             | (none)                         |

Discovery of `interaction_url` is server-injected: `LocalBridgeTransport` wraps the artifact HTML in a host page that sets `window.LL_INTERACTION_URL = '<url>interaction'` and `window.LL_EVENTS_URL = '<url>events'` before the artifact's own scripts run. The artifact's existing copy/paste code is replaced with `fetch` calls keyed off these globals.

## Use Case

**Who**: A developer triaging messages from `ll-messages` runs `ll-loop run html-website-generator "Message Stream triage console"`. After the loop completes, they want to act on the loaded messages without leaving the page.

**Context**: Today the artifact is functionally a viewer; to trigger follow-up commands, the user context-switches to Claude Code and pastes a clipboard payload. For a triage workflow this is a meaningful friction multiplier — every selection → action requires two app hops.

**Goal**: One-click execution of `ll-analyze-workflows`, `ll-propose-automations`, and `ll-analyze-history` against the currently-selected messages, with output rendered live in the same browser tab.

**Outcome**: The artifact becomes a real console rather than a viewer. No more clipboard round-trips; no more parallel terminal windows.

## Acceptance Criteria

- [ ] `ll-artifact serve-run <run-dir>` (or `--run-dir` flag on existing `ll-artifact serve`) binds `LocalBridgeTransport` for the run's `index.html` and prints the URL.
- [ ] The action buttons in the generated artifact `fetch` against `window.LL_INTERACTION_URL` rather than copying to clipboard.
- [ ] Server-side HTML injection wraps the artifact in a small bootstrap script that sets `window.LL_INTERACTION_URL` / `window.LL_EVENTS_URL` from the bound transport.
- [ ] Interaction handlers dispatch to the corresponding `ll-*` CLI as a foreground subprocess; stdout/stderr stream back to the requesting client as SSE events tagged with the request id.
- [ ] The page renders a collapsible log panel per dispatched action with live-streaming output and a final exit-code status.
- [ ] `ll-loop run html-website-generator "..."` triggers `ll-artifact serve-run` via a post-run hook in `cli/loop/run.py` after the FSM reaches `done` (not an FSM `serve` state — see Decision Rationale/Option FSM-B) and prints the bound URL; exact flag/hook name is an open decision distinct from the existing `--serve` run-duration bridge (ENH-3351, `run.py:588-657`) — see Verification Notes.
- [ ] The clipboard-copy code path remains in the artifact as a fallback for users who open `index.html` directly without serving — graceful degradation.
- [ ] Tests cover: dispatch table correctness, SSE event tagging per request id, server-injected `window.LL_*` globals present in served HTML but absent in raw `file://` HTML, server-side subprocess cancellation on client disconnect.

## Motivation

The generator-evaluator loop produces a beautiful single-page artifact and then leaves its action surface as 1990s-style clipboard handoff. We already ship:

- `LocalBridgeTransport` with `POST /{token}/interaction` (transport.py:721) — the missing half.
- `SseBridge` (transport.py:1248) and `ll-artifact serve` (cli/artifact/serve.py) for read-only history dashboards.
- `claude-code-guide`'s example precedent: `dashboard.llat` artifacts already wire `ServeContext(events_url=..., interaction_url=..., history_url=...)` (cli/artifact/serve.py:152-159).

The only missing piece is the run-artifact serving wrapper — and a generator prompt update so the artifact's buttons use `fetch` instead of clipboard.

## Proposed Solution

### Server side — new CLI: `ll-artifact serve-run`

```
ll-artifact serve-run <run-dir> [--port N] [--no-events]
```

1. Resolves `index.html` under `<run-dir>` (error if missing).
2. Instantiates `LocalBridgeTransport(port=..., inbound=queue.Queue(), render_fragment=..., page_html=<wrap_html>)` where `<wrap_html>` is the artifact HTML plus the URL-injection bootstrap script.
3. Registers interaction handlers (one per dispatch-table entry) that:
   - `subprocess.Popen(['ll-<cmd>'], stdout=PIPE, stderr=STDOUT, text=True)`
   - Iterate stdout, `transport.send({"event":"action_output","request_id":...,"line":line})` per line.
   - On exit, `transport.send({"event":"action_complete","request_id":...,"exit_code":rc})`.
   - On `KeyboardInterrupt` / client-disconnect (detected via the transport's inbound queue), `proc.terminate()` and clean up.
4. Prints the bound URL and blocks until Ctrl-C.

The HTML bootstrap is a tiny `<script>` prepended to the served page:

```html
<script>
  window.LL_INTERACTION_URL = "<url>interaction";
  window.LL_EVENTS_URL = "<url>events";
  // Subclass EventSource to tag messages by request id when used.
</script>
```

The artifact's existing `<script>` block reads these globals. When `window.LL_INTERACTION_URL` is undefined (i.e. raw `file://` open), the buttons fall back to the existing copy-to-clipboard behavior.

### Client side — artifact generator prompt update

Append to the `generate` state's action prompt in `scripts/little_loops/loops/html-website-generator.yaml`:

> Action buttons must call `fetch(window.LL_INTERACTION_URL, ...)` with `{method:'POST', body:JSON.stringify({action, request_id, payload})}`. If `window.LL_INTERACTION_URL` is undefined, fall back to `navigator.clipboard.writeText` for the corresponding slash command (graceful degradation for `file://` users).
>
> Listen on `new EventSource(window.LL_EVENTS_URL)` for `action_output` and `action_complete` events; filter by `event.request_id` and append to a per-button collapsible log.

### Loop wiring — `serve` state

Append a `serve` state after `done`:

```yaml
serve:
  action: |
    echo "Serving at http://127.0.0.1:${context.bridge_port}/${token}/"
    ll-artifact serve-run "${context.output_dir}" --port "${context.bridge_port}"
  action_type: shell
  terminal: true
```

The state reads `${context.bridge_port}` and `${token}` from `BRConfig.events.bridge`; tests can pin both via `context`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

The research finding that the FSM's shell-action executor is bounded by a 3600s wall-clock timeout (executor.py:2563, :2588) creates a fork in how `serve-run` integrates with the loop. Two viable resolutions:

**Option FSM-A**: As proposed — append a `serve` state to the loop YAML with `action_type: shell, terminal: true` that calls `ll-artifact serve-run` and expects the subprocess to block on Ctrl-C.

**Option FSM-B**: Run `ll-artifact serve-run` outside the FSM — either via a post-loop hook added to `ll-loop run` (alongside `register_loop_signal_handlers` at run.py:627), or as a separate manual `ll-artifact serve-run <run-dir>` command that the user runs after the loop completes. The FSM terminates cleanly at `done`; the server is a separate process that the harness spawns after `_execute_state` returns.

> **Selected:** Option FSM-B — no FSM YAML combines `terminal: true` with a blocking `action_type: shell` action, and the executor's 3600s wall-clock fallback SIGKILLs the whole process group on any shell overrun (`executor.py:2563,2588`; `runners.py:450-451`), so an indefinite Ctrl-C-wait server under FSM-A would be force-killed by default. FSM-B reuses the established `run.py:627` signal-handler hook and the `run_background()` detached-`Popen` pattern (`cli/loop/runner.py:291-298`), keeping the change out of FSM/executor internals.

**Recommended**: Option FSM-B — the FSM's shell-action executor has a 3600s wall-clock fallback with no daemon-action precedent in any existing loop YAML (every `terminal: true` state in html-website-generator.yaml at lines 294/302 is action-less). Running the server outside the FSM avoids modifying the executor's timeout machinery and reuses the existing signal-handler path at run.py:627.

### Decision Rationale

**Selected**: Option FSM-B (run `ll-artifact serve-run` outside the FSM, via a post-`run_foreground` hook in `cli/loop/run.py` or as a standalone manual command)

**Reasoning**: Two parallel `ll:codebase-pattern-finder` evidence passes confirmed the issue's own recommendation. No loop YAML in `scripts/little_loops/loops/` (104 files scanned) pairs `terminal: true` with a blocking `action_type: shell` action; the two existing long-lived-service patterns (`rn-build.yaml:1010-1032`, `oracles/code-run-gate.yaml:380-401`) both explicitly `kill` the backgrounded service via `trap cleanup EXIT` before the shell action returns — neither leaves a server running past its own bounded action. The executor's `_wall_fallback = 3600` (executor.py:2563, applied 2588) applies to shell actions regardless of idle-timeout settings and forcibly `SIGKILL`s the process group (`_kill_process_group`, runners.py:451) on timeout, which is fundamentally incompatible with FSM-A's "block until Ctrl-C" design. FSM-B, by contrast, has a concrete in-repo template: `run.py:627`'s signal-handler registration is already exercised on every `ll-loop run` invocation, and `run_background()` (`cli/loop/runner.py:291-298`) already demonstrates "finish primary work, hand off to a detached `subprocess.Popen(..., start_new_session=True)`" in the same package. FSM-B's remaining risk — no code path currently fires after `run_foreground()` returns in `run.py`, and the new hook must stay clearly distinct from the existing run-duration `--serve` bridge (`run.py:588-657`, ENH-3351) to avoid lifecycle confusion — is scoped and addressable, not a structural blocker like FSM-A's timeout conflict.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:------------:|:----:|:-----:|
| FSM-A  | 0 | 1 | 1 | 0 | 2/12 |
| FSM-B  | 2 | 2 | 2 | 2 | 8/12 |

**Key evidence**:
- No precedent for `terminal: true` + blocking `action_type: shell` in any of 104 scanned loop YAMLs (FSM-A evidence pass).
- `executor.py:2563,2588` + `runners.py:450-451` — shell actions are SIGKILLed on the 3600s wall-clock fallback regardless of idle-timeout opt-in, directly conflicting with FSM-A's indefinite-block design.
- `rn-build.yaml:1010-1032` / `oracles/code-run-gate.yaml:380-401` — the only existing backgrounded-service patterns explicitly kill the service before the shell action exits, never leave it running (evidence against FSM-A).
- `run.py:627` signal-handler hook + `run_background()` detached-`Popen` pattern (`cli/loop/runner.py:291-298`) — concrete, working precedent for FSM-B's "primary task ends, hand off to a new long-lived process" shape.
- Open risk for FSM-B: the existing `--serve` run-duration bridge (`run.py:588-657`, ENH-3351) is torn down in the same `finally` block that would need to host the new post-terminal hook — sequencing must be explicit to avoid conflating the two lifecycles (still requires resolving the `--serve` naming/lifecycle collision flagged in Verification Notes below, which is a separate, still-open decision point not covered by this scoring pass).

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/artifact/serve.py` — Add `serve-run` subcommand parser + `cmd_serve_run` (binding `LocalBridgeTransport` for an arbitrary `index.html`, registering interaction handlers).
- `scripts/little_loops/cli/artifact/__init__.py` — Register `serve_run` parser in the subparsers group.
- `scripts/little_loops/loops/html-website-generator.yaml` — Update `run_gen_eval.with.generate_prompt` to use `fetch` + `EventSource` with clipboard fallback. No FSM state added (Option FSM-B selected — a `serve` state would be SIGKILLed by the 3600s shell-action wall-clock fallback).
- `scripts/little_loops/cli/loop/run.py` — Add a post-run hook after `run_foreground()` returns (near the existing signal-handler registration at `run.py:627`) that launches `ll-artifact serve-run "${run_dir}"` as a detached process for `html-website-generator` runs, following the `run_background()` pattern (`cli/loop/runner.py:291-298`). Naming must avoid colliding with the existing `--serve` run-duration bridge (ENH-3351, `run.py:588-657`) — see Verification Notes.
- `scripts/little_loops/cli/loop/__init__.py` — Wire the new hook's CLI flag alongside the existing `--serve` flag registration (lines 296-310).
- `scripts/little_loops/transport.py` — Possibly expose a thin helper `_make_inbound_dispatch_handler(actions: dict[str, Callable[[dict], None]])` to standardize the dispatch pattern (used by `LocalBridgeTransport`, `serve.py`, and any future transport-consuming page). Verify it doesn't already exist.

### Dependent Files (Callers/Importers)

- `ll-artifact` CLI surface (`scripts/little_loops/cli/artifact/__init__.py`) — new subcommand.
- `scripts/little_loops/transport.py` `LocalBridgeTransport` — already supports inbound queue + interaction POST route (lines 692-716); no changes expected.
- `scripts/little_loops/fsm/executor.py` — Unchanged: Option FSM-B keeps the server outside the FSM entirely, so no `serve` state is added and `action_type: shell` dispatch (executor.py:3361) is not exercised by this feature.

### Similar Patterns

- `cli/artifact/serve.py` `make_history_route` (lines 51-135) — read-only `GET /history` JSON handler. Different: GET, no subprocess, no streaming. Same shape though.
- `cli/artifact/dashboard.py` `ServeContext(events_url, interaction_url, history_url)` — the three-URL triple that the new `serve-run` should mirror.
- `transport.py:692` `_handle_interaction` — exact existing pattern: read body, parse JSON, put on inbound queue. `serve-run` will spin a worker thread that consumes from the same queue.
- `run.py:627` signal-handler registration + `run_background()` detached-`Popen` pattern (`cli/loop/runner.py:291-298`) — the precedent Option FSM-B's post-run hook follows: finish primary work, then hand off to a new long-lived process.

### Tests

- `scripts/tests/test_artifact_serve_run.py` (new):
  - `test_dispatch_table` — every entry in `ACTIONS` maps to a callable that resolves to an `ll-*` CLI.
  - `test_serve_html_injection` — `LocalBridgeTransport.set_page_html` output contains `window.LL_INTERACTION_URL` and `window.LL_EVENTS_URL` when wrapped; raw artifact HTML does NOT contain them.
  - `test_sse_event_tagging` — interaction dispatch emits `action_output` events with matching `request_id`; multiple concurrent requests don't cross-stream.
  - `test_subprocess_cleanup_on_disconnect` — kill client mid-run; subprocess terminates within bounded timeout; no orphan processes.
  - `test_fallback_when_serving_off` — opening the raw `index.html` in a JSDOM-like environment; `window.LL_INTERACTION_URL === undefined`; button handler falls back to clipboard.
- `scripts/tests/test_builtin_loops.py` / `cli/loop` tests — extend or add coverage asserting the post-run hook invokes `ll-artifact serve-run` after the FSM reaches `done`; not an FSM-state assertion, since no `serve` state exists under Option FSM-B.

### Documentation

- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — Document `serve-run` as Level 3 usage on arbitrary run artifacts (vs. the existing Level 1 placeholder and Level 2 dashboard history).
- `docs/reference/CLI.md` — Add `ll-artifact serve-run` to the artifact CLI surface.
- `scripts/little_loops/loops/README.md` — Note that `html-website-generator` now auto-serves its output.

### Behavior Parity

| Artifact behavior | Status | Notes |
|-------------------|--------|-------|
| `html-website-generator.yaml` `generate` state produces `index.html` in `${output_dir}` | Preserved | No change to generation prompt's output contract |
| `generate` state's prompt asks for `copy-to-clipboard` action buttons | Changed | Prompt now requires `fetch` + `EventSource` with graceful clipboard fallback when `window.LL_INTERACTION_URL` is undefined (i.e. raw `file://` open) |
| Loop FSM terminates after `done` state | Preserved | `--no-serve` (default) leaves FSM at `done`; behavior identical to today |
| Loop auto-serves and blocks on Ctrl-C | New | New `serve` state appended after `done`; only entered when `--serve` is passed |
| Clipboard fallback for `file://` users | Preserved | Existing copy-to-clipboard code path remains in the artifact; the prompt explicitly requires it as graceful-degradation fallback |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- `LocalBridgeTransport.__init__` (transport.py:772-778) — constructor signature is `(port=0, inbound=None, render_fragment=None, page_html=None)`. `daemon_threads` is NOT a constructor param; it is set on the underlying `http.server.ThreadingHTTPServer` at transport.py:795. Any wrapper that instantiates the transport must pass these four params explicitly.
- `_handle_interaction` (transport.py:692-716) — POST handler responds `204` BEFORE enqueueing, so an inbound-queue-full condition is invisible to the client (deliberate). Body dict is forwarded unchanged — no `request_id` plumbing exists today. Setting `inbound=None` at construction time silently disables every POST (transport.py:703-704); `serve-run` must construct with `inbound=queue.Queue()`.
- `transport.send(event)` (transport.py:820-830, called from `EventBus.emit` at events.py:136) — outbound direction is *broadcast*: the same event reaches every connected SSE client. There is no per-`request_id` fan-out channel today; the artifact-side EventSource must filter by `request_id` itself.
- `LocalBridgeTransport.close()` (transport.py:832-877) — bounded shutdown by `_LOCAL_BRIDGE_CLOSE_TIMEOUT = 10.0s` (transport.py:79). The HTTP server runs `daemon_threads = True`, so close() does not block on handler threads. No signal is sent to a separate inbound-queue worker thread; any consumer holding `inbound.get()` is a daemon thread.
- `cmd_serve` (cli/artifact/serve.py:166-203) uses `SseBridge`, NOT `LocalBridgeTransport`. Existing `ll-artifact serve` has NO inbound-queue wiring on this code path. `serve-run` must be a separate subcommand that constructs `LocalBridgeTransport` directly — `cmd_serve` cannot be repurposed as-is.
- `ServeContext(events_url, interaction_url=None, history_url=None)` (cli/artifact/dashboard.py:132-153) — `interaction_url=None` disables the page-side interaction block via Jinja conditional (templates/dashboard.llat/template.html.j2:374,381), but the HTTP-side POST route on `LocalBridgeTransport` still exists regardless. `serve-run`'s server-side route is automatically available; only the page-side wiring is the artifact's bootstrap-script responsibility.
- `cli/loop/run.py:601` already uses `getattr(args, "port", None) or 0` for `--serve` — the same flag-default idiom is the natural model for the loop YAML's `serve` state's port source.
- `BridgeEventsConfig` (config/features.py:1299-1330) — `port: int = 8766`, `history: bool = False`. `BRConfig.events.bridge.port` (read at core.py:354, exposed via property at core.py:478) is the source of truth. No consumer currently injects `bridge_port` into a loop's `context:` block — `cli/loop/run.py` injects `run_dir`/`max_steps`/`max_iterations`/`include` only.
- `${context.run_dir}` is the actual context variable name (injected at cli/loop/run.py:207-208); the issue's references to `${context.output_dir}` do not resolve anywhere in `scripts/little_loops/cli/loop/run.py` or any loop YAML scanned.
- No existing `make_inbound_dispatch_handler(actions: dict)` helper exists in `scripts/little_loops/transport.py` or anywhere in the repo (verified via grep, no glob). The function named in `## Program Design` is greenfield.
- No per-request-id SSE pattern exists anywhere in `scripts/little_loops/`. The closest existing pattern is `fsm/runners.py:DefaultActionRunner.run` (runners.py:128-477) which streams shell stdout into the FSM's event bus via `_on_line` → `self._emit("action_output", {"line": line})` at executor.py:2473-2474 — but this is a bus broadcast, not an SSE-targeted per-request stream. A new dispatch shape is required.
- Shell-action executor runtime (`fsm/runners.py:355-373`, `executor.py:2471-2474, 2656`) emits per-line `action_output` events and a final `action_complete` event — the same `{event, line|exit_code, ...}` shape the proposed `action_output`/`action_complete` SSE events mirror. The artifact's EventSource handler can re-use the existing observer envelope or be a thinner direct SSE channel.

## Program Design

### Types

- `ActionName: Literal["analyze-workflows", "propose-automations", "analyze-history"]`
- `ActionDispatch = Callable[[ActionName, dict], None]`
- `InboundEvent: TypedDict` (`{"action": ActionName, "request_id": str, "payload": dict}`)
- `SseOutputEvent: TypedDict` (`{"event": "action_output", "request_id": str, "line": str}`)
- `SseCompleteEvent: TypedDict` (`{"event": "action_complete", "request_id": str, "exit_code": int}`)

### Signatures

- `cmd_serve_run(args: argparse.Namespace) -> int` — entry point registered under `ll-artifact serve-run`
- `make_inbound_dispatch_handler(transport: LocalBridgeTransport, actions: dict[ActionName, ActionDispatch]) -> Callable[[InboundEvent], None]` — helper in `transport.py` (FEAT-3456 introduces this if absent)
- `LocalBridgeTransport.set_page_html(html: str) -> str` — wraps the supplied HTML with `<script>window.LL_INTERACTION_URL=…; window.LL_EVENTS_URL=…</script>` (already exists at transport.py:721)
- `bridge_run(state: FsmState, ctx: FsmContext) -> FsmTransition` — `serve` state body in `html-website-generator.yaml`; invokes `ll-artifact serve-run "${context.output_dir}"`

### Call Path

`html-website-generator.yaml: serve` -> `cmd_serve_run` -> `LocalBridgeTransport(port=bridge_port, page_html=wrapped_html)` -> `serve_forever()` (blocks on Ctrl-C) ; client-side: `artifact JS button click` -> `fetch(window.LL_INTERACTION_URL, POST JSON)` -> `LocalBridgeTransport._handle_interaction` -> `inbound.put_nowait` -> worker thread `make_inbound_dispatch_handler(actions)` -> `subprocess.Popen(['ll-<cmd>'])` -> `transport.send({"event":"action_output",...})` over SSE -> `EventSource` in artifact -> per-button log panel render

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- `LocalBridgeTransport.set_page_html` is at **transport.py:809-818**, NOT transport.py:721 as the existing Program Design block states. Line 721 is `class LocalBridgeTransport:` itself (corrected by `/ll:verify-issues` — a prior refine pass mischaracterized line 721 as the `POST /{token}/interaction` route registration, which is actually `_handle_interaction` at transport.py:692). The Summary's original `transport.py:721` citation for the class was already correct; only the Program Design "Signatures" block's citation of `set_page_html` at 721 needed the 809-818 fix. The corrected anchor must be used when citing the helper.
- The `bridge_run(state: FsmState, ctx: FsmContext) -> FsmTransition` signature in the existing Program Design block is fabricated — no such function exists in the FSM. The loop YAML's `serve` state body is just an `action: |...` string executed by `action_type: shell`; the FSM does not have a `bridge_run` callable.
- Shell-action in FSM is bounded by a 3600s wall-clock fallback (`executor.py:2563` via `_wall_fallback = 0 if (action_mode == "prompt" and _idle_timeout) else 3600`, applied at `executor.py:2588`). Every `action_type: shell` action is killed by `_kill_process_group(process)` (runners.py:451) when the budget expires. **A `serve` state that calls `ll-artifact serve-run` and expects to block forever on Ctrl-C will be terminated by the FSM shell-action timeout — the proposed mechanism has no precedent in any loop YAML in `scripts/little_loops/loops/`.**
  > ⚠ Unproven mechanism — FSM shell action blocks on Ctrl-C; no precedent in loops/
- `_handle_interaction` (transport.py:692-716) does NOT stamp a `request_id` on the inbound body. The `request_id` field must be added to the client POST body and threaded through the dispatch worker; today the inbound dict is forwarded unchanged (transport.py:714 calls `self._inbound.put_nowait(parsed)`).
- `transport.send()` is broadcast to every connected SSE client (transport.py:879-886 via `_render_event`/`_render_fragment`). There is no per-client targeting. The artifact's EventSource handler must filter by `event.request_id` itself; the server side cannot address a single client.

## Codebase Research Findings

**`LocalBridgeTransport` is bidirectional** (transport.py:721) — `POST /{token}/interaction` reads JSON body and `inbound.put_nowait()`s it (lines 692-716). The inbound queue can be consumed by a worker thread that dispatches per request. Already supports `daemon_threads = True` on the server (line 795), so subprocess cleanup on `close()` is straightforward.

**`dashboard.llat` precedent** (`cli/artifact/serve.py:138-163`) — `_make_page_html_factory` builds `ServeContext(events_url, interaction_url=None, history_url)`. Setting `interaction_url=None` is what disables the dashboard's POST route today. For `serve-run` we want it non-null.

**Subprocess lifecycle** — `transport.py:_LOCAL_BRIDGE_CLOSE_TIMEOUT = 10.0` (line 79) bounds `LocalBridgeTransport`'s own shutdown (corrected by `/ll:verify-issues` — `_CLOSE_TOTAL_TIMEOUT` at line 69 is a different constant used by `UnixSocketTransport.close()`, transport.py:385, not by `LocalBridgeTransport`). Interaction subprocesses need their own bounded termination (e.g. `proc.terminate(); proc.wait(timeout=5)` then `proc.kill()`); follow the existing BUG-3324 socket-reclaim TOCTOU pattern of "check the worker's actual state before unlinking" rather than blindly terminating.

**No `serve-run` exists yet** — verified via `grep -rn "serve_run\|serve-run" scripts/` returning empty. Greenfield addition; no migration concerns.

## Implementation Steps

1. Add `serve_run` subcommand + `cmd_serve_run` to `cli/artifact/serve.py`; register parser in `cli/artifact/__init__.py`.
2. Add `_make_inbound_dispatch_handler(actions)` helper in `transport.py` (if it doesn't already exist) — extracts the `subprocess.Popen` + `transport.send` pattern into a reusable shape.
3. Update `run_gen_eval.with.generate_prompt` in `scripts/little_loops/loops/html-website-generator.yaml` to use `fetch` + `EventSource` with graceful `file://` fallback (corrected state path — `generate` is not a state name).
4. Add a post-run hook in `cli/loop/run.py`, after `run_foreground()` returns and near the existing signal-handler registration at `run.py:627`, that launches `ll-artifact serve-run "${run_dir}"` as a detached process, following the `run_background()` pattern (`cli/loop/runner.py:291-298`) — not an FSM `serve` state (Option FSM-B selected: a `serve` state would be SIGKILLed by the executor's 3600s shell-action wall-clock fallback). Exact flag/hook name is an open decision distinct from the existing `--serve` run-duration bridge (ENH-3351) — see Verification Notes.
5. Write `scripts/tests/test_artifact_serve_run.py` covering the test surface above.
6. Update docs per Documentation section.

## API/Interface

```bash
# One-shot: serve an existing run's artifact
ll-artifact serve-run .loops/runs/html-website-generator-20260911T190205/

# Output:
# http://127.0.0.1:8766/<token>/
# (Ctrl-C to stop)

# Loop-driven: end-of-loop auto-serve
ll-loop run html-website-generator "Message Stream triage console"
# ... generation happens ...
# done
# serve → http://127.0.0.1:8766/<token>/
```

## Impact

- **Priority**: P3 — Removes real friction from a workflow the user runs repeatedly; not blocking anything else.
- **Effort**: Small-medium — One new CLI subcommand (~150 LoC), one transport helper (~50 LoC), one loop-YAML prompt update (~30 words added), one new test file (~200 LoC), doc touchups.
- **Risk**: Low — additive, no existing API changes. Subprocess lifecycle is the main thing to get right; bounded terminate→kill pattern with test coverage.
- **Breaking Change**: No — `ll-artifact serve` (existing FEAT-3323/3321) is untouched. `html-website-generator.yaml` adds a state; if a user runs the loop with `--no-serve` (default off), behavior is identical to today.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/ARTIFACT_CONTROL_LEVELS.md` | Level 3 (interactive POST) is exactly the pattern `serve-run` enables for arbitrary artifacts |
| `docs/reference/API.md#little_loopstransport` | `LocalBridgeTransport` is the underlying primitive |
| `docs/guides/LOOPS_GUIDE.md` (Harness Examples) | `html-website-generator` row should mention auto-serve |

## Labels

`feat`, `artifacts`, `transport`, `local-bridge`, `serve`, `html-website-generator`, `interaction`, `level-3`

## Verification Notes

Verdict at time of check: **PROPOSAL_UNSOUND** (corrections below applied in
the same pass, so the issue as it now reads is up to date on citations — this
section is a record of what was wrong/missing and fixed, plus one outstanding
design conflict that is not fixed here).

**Citations — exhaustively spot-checked against HEAD, all confirmed exact
except one (fixed inline):** `LocalBridgeTransport` class def at
transport.py:721, `_handle_interaction` 692-716 (no `request_id` stamping,
confirmed), `__init__` signature 772-778, `daemon_threads = True` at 795,
`set_page_html` 809-818, `send()` 820-830 (broadcast, confirmed — no
per-client targeting), `close()` 832-877 bounded by `_LOCAL_BRIDGE_CLOSE_TIMEOUT`
at line 79, `events.py:136` `transport.send(event)` call site, executor.py
`_wall_fallback = 3600` at line 2563 applied at line 2588, `action_type ==
"shell"` dispatch at line 3361, runners.py `_kill_process_group` at line 451,
`cli/artifact/serve.py` `make_history_route` 51-135 / `cmd_serve` 166-203
(confirmed: uses `SseBridge`, not `LocalBridgeTransport`), `cli/artifact/
dashboard.py` `ServeContext` 132-153, `template.html.j2` `serve_interaction_enabled`
at 374/381, `config/features.py` `BridgeEventsConfig` 1299-1330, `config/
core.py` `self._events = EventsConfig.from_dict(...)` at 354 and the `events`
property at 478, and `html-website-generator.yaml` `terminal: true` at 294/302
(both action-less) plus `run_gen_eval.with.generate_prompt` (confirmed: there
is no `generate` state). `ll-verify-evidence --json` reports clean (0
findings). `ll-issues decisions list --type rule --enforcement required
--active-only` returns no entries (no `DECISIONS_VIOLATION` possible). No
`## Blocked By`/`## Blocks` section exists, so no dependency-graph checks
apply. Codegraph (`ll-code --json status`) is available/fresh and was used
for corroboration only. Doesn't match any completed issue's scope closely
enough to be a regression candidate.

**Fixed**: the "Subprocess lifecycle" Codebase Research Finding cited
`transport.py:_CLOSE_TOTAL_TIMEOUT = 10.0` (line 69) as bounding
`LocalBridgeTransport`'s shutdown — that constant actually bounds
`UnixSocketTransport.close()` (used at transport.py:385); the correct
constant is `_LOCAL_BRIDGE_CLOSE_TIMEOUT = 10.0` at line 79, corrected in
place. Separately, the Program Design research block's aside "Line 721
corresponds to the `POST /{token}/interaction` route registration" was
itself wrong — line 721 is `class LocalBridgeTransport:`; the interaction
route handler is `_handle_interaction` at transport.py:692. The underlying
correction in that same block (`set_page_html` lives at 809-818, not 721)
was and remains correct; only the incorrect gloss about what line 721 *is*
has been fixed.

**PROPOSAL_UNSOUND finding (not fixed — needs a design decision, not a text
edit)**: `--serve` is not an available flag name. `ll-loop run --serve`
already exists and ships today (ENH-3351, `status: done`, `cli/loop/
__init__.py:296-310`, `cli/loop/run.py:588-657`, documented at
`docs/reference/CLI.md:810-811`): it binds `LocalBridgeTransport` with an
inbound queue *before* the executor starts, serves a live FSM
dashboard/history page for the run's duration, and — per its own docs —
"Server lifetime == run lifetime: it shuts down ... when the loop reaches a
terminal state." That is the **opposite** lifecycle of what this issue wants
(server starts serving *after* `done` and blocks on Ctrl-C). The AC
("`ll-loop run html-website-generator "..."` adds a `serve` state ... or a
`--serve` flag on the generator") and the Behavior Parity table ("only
entered when `--serve` is passed") both reuse the `--serve` name without
noting this collision, and the Integration Map's "Files to Modify" never
lists `cli/loop/run.py` or `cli/loop/__init__.py` even though that's exactly
where the existing flag is wired. As written, implementing this proposal
either silently overloads an already-documented flag with incompatible
semantics, or ships with an undiscovered naming conflict. This needs a
`/ll:decide-issue`-or-`/ll:reconcile-issue` pass: pick a distinct flag/state
name (or fold post-completion artifact-serving into the existing `--serve`
bridge as a `done`-state addendum instead of a new lifecycle), and add
`cli/loop/run.py`/`cli/loop/__init__.py` to the Integration Map. This is
additional to (not a replacement for) the already-flagged FSM-A/FSM-B
3600s-timeout fork, which remains an open, correctly-annotated
`decision_needed: true` item.

**Also fixed**: the H1 title read "FEAT-3456" while frontmatter `id`/filename
both say `FEAT-3458`; corrected to `FEAT-3458` (no other issue in this repo
carries FEAT-3456 in a way that suggests this was an intentional cross-ref).

**Missing precedent** (contributes to but doesn't cause the above): ENH-3351
also demonstrates the "Similar Patterns" section is incomplete — it cites
`cli/artifact/serve.py`/`dashboard.py`/`transport.py:692` but omits the
closest and most directly relevant precedent for wiring
`LocalBridgeTransport` + an inbound queue into a CLI-driven loop run
(`cli/loop/run.py:592-657`).

**Remaining**: resolve the `--serve` naming/lifecycle collision against
ENH-3351 and update the AC/Behavior Parity/Integration Map accordingly;
resolve the FSM-A/FSM-B decision and reconcile the Proposed Solution/
Implementation Steps sections to match (both destructive rewrites — left for
`/ll:reconcile-issue` or `/ll:decide-issue`, not applied here).

---

## Session Log

- `/ll:audit-issue-conflicts` - 2026-09-12T17:49:25 - `24bcbb37-7da0-4a87-b50e-2d2e5174a4e2.jsonl`
- `/ll:reconcile-issue` - 2026-09-12T17:48:58 - `53449bfc-4a43-46cf-93a9-b9b522f17bce.jsonl`
- `/ll:decide-issue` - 2026-09-12T17:42:10 - `71fadad1-1c93-41b3-b03e-d94f4739e170.jsonl`
- `/ll:verify-issues` - 2026-09-12T17:13:32 - `5fc78720-4226-4a87-b83b-58bd16519b14.jsonl`
- `/ll:verify-issues` - 2026-09-12T17:05:55 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- `/ll:refine-issue` - 2026-09-12T04:05:20 - `a44d1787-2431-457b-ab50-9c782f796d04.jsonl`
- `/ll:format-issue` - 2026-09-12T03:53:55 - `b93d4f64-d30d-48d3-a313-aef11620bf9b.jsonl`
_(none yet — newly captured)_

---

## Status

**Open** | Created: 2026-09-11 | Priority: P3
