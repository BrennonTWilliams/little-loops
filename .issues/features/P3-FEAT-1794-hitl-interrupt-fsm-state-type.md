---
id: FEAT-1794
type: FEAT
title: HITL interrupt FSM state type (action_type human_approval)
priority: P3
status: open
blocked_by: []
captured_at: '2026-05-29T20:37:23Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
- captured
- fsm
- harness
- hitl
- loops
parent: EPIC-1929
relates_to:
- FEAT-1545
- FEAT-1613
- FEAT-1930
- FEAT-1931
- FEAT-1932
decision_needed: false
decision: "Option A \u2014 hardcoded dispatch following the mcp_tool pattern. Simpler\
  \ single-file executor change, follows existing conventions. Extension-based path\
  \ (Option B) deferred as future refactor. Note: transport is now delegated to the\
  \ CommunicationAdapter protocol (FEAT-1930); the executor calls adapter.send_alert()\
  \ / adapter.await_response() rather than hardcoding terminal I/O."
verify_verdict: VALID
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1794: HITL interrupt FSM state type (`action_type: human_approval`)

## Summary

Add a first-class human-in-the-loop interrupt to the FSM runner: a new
`action_type: human_approval` (or equivalent state shape) that pauses a
running harness, surfaces a question/context to the operator out-of-band,
waits for a yes/no/edit response, and routes via `on_yes` / `on_no` /
`on_edit`. This is the analogue of DeerFlow's `interrupt()` and
`ask_clarification` patterns and is the missing primitive that prevents
our harness from collaborating with a human inside the loop.

## Current Behavior

The harness pipeline today (`check_concrete` → `check_mcp` → `check_skill`
→ `check_semantic` → `check_invariants`) is fully autonomous. When an
evaluation fails, the only options are:
- `on_no: execute` — retry the same input
- `on_no: advance` / `done` — skip / give up

There is no way for a long-running loop (e.g., `ll-auto` over 30 issues,
a multi-hour `harness-optimize` run) to ask "the diff looks runaway —
keep going or abort?", or to surface a planner output for human review
before paying for the implement step. The operator either babysits the
terminal (defeats the point) or trusts the LLM judge in isolation
(violates our MR-1 anti-self-eval rule for meta-loops).

## Expected Behavior

A state with `action_type: human_approval` should:

1. Render a prompt (the state's `action:` field — the same slot
   `action_type: prompt` uses; `StateConfig` has no `prompt` field, see
   Pre-implementation Review #3) plus any captured context (e.g.,
   `${captured.execute.output}`) to the configured `CommunicationAdapter`
   — terminal by default, `eventbus` (FEAT-3384) for out-of-band relay.
2. Block FSM execution while waiting for a response.
3. Accept at least three verdicts:
   - `approve` → take `on_yes`
   - `reject` → take `on_no`
   - `edit` → take `on_edit`, with the edited text captured for the next
     state to consume via `${captured.<state>.edit}`
4. Honor a `timeout:` field — on timeout, take `on_timeout` (default to
   `on_no` if unspecified). This is critical for unattended `ll-auto`
   runs that must not deadlock if the human is away. When the state has
   no `timeout:`, the wait is bounded by `hitl.default_timeout` (config,
   default 1800s) — never by the loop's `default_timeout`, which is the
   action-subprocess timeout (Second Review #13).
5. Emit `human_approval_requested` (once, from the executor, carrying the
   adapter-assigned `alert_id`) so the operator can be paged via the
   existing event bus instead of polling.

Example shape:

```yaml
check_human:
  action_type: human_approval
  action: >
    The execute step modified 240 lines. Threshold is 50.
    Diff summary: ${captured.check_invariants.output}
    Approve to continue, reject to retry execute, edit to adjust the diff.
  timeout: 1800   # 30 min unattended fallback
  on_yes: advance
  on_no: execute
  on_edit: re_execute
  on_timeout: advance
```

## Use Case

**Who**: A developer or operator running long-lived little-loops automation (e.g.,
`ll-auto` over 30+ issues, multi-hour `harness-optimize` runs).

**Context**: During an unattended or semi-attended FSM run, an evaluation step
detects a condition that warrants human judgment — a diff exceeding a safety
threshold, a planner output that looks questionable, or a meta-loop's
`check_semantic` result that needs independent verification per MR-1.

**Goal**: Pause the harness, surface the relevant context and a yes/no/edit
question to the operator, then route the FSM based on the response — without
requiring the operator to babysit the terminal or trusting the LLM judge alone.

**Outcome**: The operator receives a notification (terminal, push, or IM), reviews
the context, responds with approve/reject/edit, and the FSM resumes on the
appropriate transition path. If the operator is away, a configurable timeout
falls back to a safe default (typically `on_no`) so unattended runs never
deadlock.

## Motivation

- Closes a confirmed gap surfaced by the DeerFlow comparison in
  `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`: DeerFlow's clarification
  loop + plan review + tool-call approval pause execution at strategic
  checkpoints; ours has zero such primitives.
- Strengthens MR-1 compliance — a `human_approval` state IS a non-LLM
  evaluator, so it can pair with `check_semantic` in meta-loops without
  triggering the rule.
- Unlocks workflows that today require either a separate hitl-* loop
  (FEAT-1545, FEAT-1613) or babysitting: mid-`harness-optimize`
  review, gated `ll-auto` runs, dangerous-diff confirmations.
- As models improve and loops get more ambitious, the value of a single
  well-placed human checkpoint goes up, not down.

## Acceptance Criteria

- [ ] FSM runner recognizes `action_type: human_approval` and dispatches to the HITL handler from `_execute_state()`; `_action_mode()` also returns a distinct `"human_approval"` mode so the shell/prompt heuristics consulted outside dispatch (the BUG-1226 flush at `executor.py:674`, tamper guard, host guard, circuit wait) never classify the state as `"shell"` and run the prompt text through bash (Second Review #11)
- [ ] Prompt text (the state's `action:` field, interpolated) plus captured context (e.g., `${captured.execute.output}`) is rendered via `adapter.send_alert()`; `captured_context` includes a monotonic `deadline` key (the `TerminalAdapter` renders "Time remaining" from it)
- [ ] FSM execution blocks while waiting for a human response (no CPU spin, no premature advance); each tick calls `self._drain_inbound()` so an inbound `human_response` posted via `ll-loop run --serve` reaches the bus during the wait (FEAT-3384 Review #1)
- [ ] Three verdicts are accepted: `approve` (→ `on_yes`), `reject` (→ `on_no`), `edit` (→ `on_edit` with edited text captured as `${captured.<state>.edit}`); `captured[<state>]` also carries `verdict`, `reason` (reject reason from `AdapterResponse.reason`), and `output` (= edited text or empty). Routing goes through the existing `_route()` (`executor.py:2994`) with verdict strings `yes`/`no`/`edit`/`timeout`, so `route:` tables, `advance`/`done`, and `${...}` targets work exactly as for evaluate states (Second Review #12). The handler's `edit`→`yes` and `timeout`→`no` fallbacks apply **only when `_route()` returns `None`**: with a `route:` table, an unrouted `edit`/`timeout` resolves to `route.default` first and `no` falls to `route.error`, exactly as for evaluate verdicts (Third Review #21) — tests must encode that, not the shorthand-only rule
- [ ] Effective timeout is `state.timeout` if set, else `hitl.default_timeout` (new `HitlConfig` field, default 1800) — NOT `fsm.default_timeout`, which is the action-subprocess timeout (Second Review #13) — and, when the loop sets a wall-clock `timeout:` (`fsm.timeout`), clamped to the loop's remaining budget so the operator is never asked a question the loop can no longer act on (Third Review #20). On timeout, calls `adapter.cancel_alert()` then takes `on_timeout` (defaults to `on_no` if `on_timeout` unspecified)
- [ ] A `TimeoutResponse` returned by `adapter.await_response()` on a single tick means "no verdict yet", never "timed out": the `TerminalAdapter` returns one on every idle tick, on unrecognized input, and on every call after stdin EOF. Only the executor-side deadline ends the wait. The tick length is a module constant `_HITL_TICK_SECONDS = 0.5` (not `_interruptible_sleep()`'s 100 ms — the terminal adapter builds a selector per call) (Third Review #19)
- [ ] `human_approval_requested` is emitted exactly once by the executor via `_emit()`, after `send_alert()` returns, carrying `alert_id`, `state`, `prompt`, `timeout`, and a wall-clock ISO `deadline_ts` (the monotonic `deadline` stays in `captured_context` only — it is meaningless to out-of-process consumers, Second Review #14) — the adapter never emits it itself (FEAT-3384 Review #2); `human_approval_resolved` is emitted after routing with `verdict`, `elapsed_seconds`, `route`
- [ ] `ll-loop validate` warns (unconditionally) when a `human_approval` state has no `timeout:` — message names the `hitl.default_timeout` fallback that will apply. A "referenced by unattended automation" scoping check is infeasible since `ll-auto`/`ll-sprint` don't directly load FSM loop YAMLs (confirmed finding); the warning fires regardless of caller context. `timeout: 0` is NOT a suppression idiom (see Pre-implementation Review #5). The validator requires a non-empty `action` and either `on_yes`+`on_no` or a `route:` table with `yes`/`no` keys
- [ ] Headless/non-interactive contexts take a safe default without deadlocking: when `not adapter.supports_async()` and stdin is non-interactive (`sys.stdin is None or sys.stdin.closed or not sys.stdin.isatty()` — `TerminalAdapter._read_line()` calls `fileno()` and raises on a closed stream, Second Review #15), the handler routes `on_timeout` immediately without sending an alert. This is the **normal** path for `ll-loop run --background` (`cli/loop/runner.py:296` re-execs with `stdin=subprocess.DEVNULL`) and for any loop launched from a Claude Code Bash call, so it must not be silent: the handler logs a `WARNING` naming the state and pointing at `hitl.channel: eventbus`, and the `human_approval_resolved` payload carries `verdict: "timeout"`, `reason: "headless"` so it is distinguishable from a real timeout (Third Review #18). An async adapter (`eventbus`) is never short-circuited — headless is exactly where it is needed
- [ ] On `_shutdown_requested` mid-wait, the handler calls `adapter.cancel_alert()` and returns `None` so `run()`'s existing interrupted-save branch fires; a resumed run re-enters the state and re-sends the alert
- [ ] Both new events are registered per CONTRIBUTING § Event Schema Maintenance: `SCHEMA_DEFINITIONS` entries in `generate_schemas.py`, regenerated `docs/reference/schemas/*.json`, `DESVariant` classes in `observability/schema.py` `DES_VARIANTS`, sections in `docs/reference/EVENT-SCHEMA.md`, and the hard-coded counts in `test_generate_schemas.py:21` / `:124` bumped 59→61. Both are added to `_LOOP_EVENT_TYPES` (`session_store/schema.py:100`) so they persist to SQLite `loop_events` for `ll-logs` (Third Review #17)
- [ ] `cli/loop/feed.py` renders one line for each new event (`_format_event` and `handle_event`), so `--quiet` runs and log files show that the loop is waiting on a human even though the adapter's own `print()` goes straight to stdout (Third Review #22)

## Proposed Solution

**Updated 2026-06-04**: This issue is now a child of EPIC-1929 (Async HITL
Communication Adapter Framework). Transport is delegated to the
`CommunicationAdapter` protocol (FEAT-1930); the executor calls
`adapter.send_alert()` and `adapter.await_response()` rather than hardcoding
terminal I/O. This issue owns the FSM side: schema, dispatch, routing, timeout,
and event emission — not the transport implementations (FEAT-1931 terminal,
FEAT-1932 PushNotification).

Original investigation items (resolved by EPIC-1929 decomposition):
- ~~Notification surface: PushNotification vs PushNotification + IM
  adapter chain.~~ → Delegated to CommunicationAdapter protocol (FEAT-1930)
  and individual adapters (FEAT-1931, FEAT-1932).
- Wait semantics: blocking poll on a file/socket vs the existing event
  bus subscribe. → The adapter protocol's `await_response()` abstracts this;
  each adapter chooses its mechanism.
- Headless mode: `LL_HOST_CLI=codex` / non-interactive contexts need a
  safe default. → Still relevant; the FSM state checks
  `adapter.supports_async()` and host interactivity to decide whether to
  warn/fallback.
- Schema rules: `ll-loop validate` should warn if a `human_approval`
  state has no `timeout:` AND the loop is referenced by ll-auto /
  ll-sprint. → Still relevant; validator change is in this issue's scope.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Implementation approach — two options identified:**

**Option A: Hardcoded dispatch (mcp_tool pattern)**
Add `human_approval` as a built-in action type in the executor core, following the exact pattern `action_type: mcp_tool` used:
- `_action_mode()` at `executor.py:2706` — add `if state.action_type == "human_approval": return "human_approval"` (before the heuristic fallthrough)
- `_execute_state()` at `executor.py:1711` — add dispatch branch before the generic action path (similar to the learning-state dispatch near the top of the method, `executor.py:1735`): `if state.action_type == "human_approval": return self._execute_human_approval_state(state, ctx)`
- New method `_execute_human_approval_state()`: emit event via `self._emit()`, block with `_interruptible_sleep()`-style polling (existing pattern at `executor.py:3378`), route by verdict
- Pros: simpler, single-file executor change, follows existing pattern
- Cons: couples HITL logic to executor core

**Option B: Extension-based (ActionProviderExtension)**
Implement as a contributed action via the extension protocol:
- Register via `ActionProviderExtension.provided_actions()` (`extension.py:81`)
- Wired through `wire_extensions()` at `extension.py:246` which populates `executor._contributed_actions`
- The executor already dispatches contributed actions in `_action_mode()` (`executor.py:2706`) and `_run_action()` (`executor.py:2049`)
- Pros: decoupled, testable in isolation, follows extension architecture
- Cons: the contributed-action path runs through `_run_action()` which assumes fire-and-evaluate semantics — blocking on external response requires either extending the protocol or adding a dispatch branch in `_execute_state()` anyway

**Key corrections to issue assumptions:**
- **PushNotification does NOT exist** in the codebase (confirmed by grep). The `EventBus` (`events.py:70`) + transports (`transport.py`) are the closest notification infrastructure. v1 should render to terminal + emit an `LLEvent`; PushNotification/IM adapter is v2 scope.
- **`timeout` field already exists** on `StateConfig` at `schema.py:375` — can be reused for the HITL timeout without adding a new field.
- **`extra_routes`** on `StateConfig` (`schema.py:389`) already catches unrecognized `on_*` keys as dynamic routes — `on_edit` could be handled via `extra_routes` instead of a dedicated field, simplifying the schema change.
- **No `interactive` capability flag** exists on `HostCapabilities` (`host_runner.py:74`). Headless detection for the `LL_HOST_CLI=codex` requirement needs a new flag or a `sys.stdin.isatty()` check (currently only `sys.stdout.isatty()` checks exist in the codebase).
- **`ll-auto` and `ll-sprint` do NOT directly load FSM loop YAMLs** — they invoke Claude CLI slash commands. The "referenced by unattended automation" validation check would need a cross-reference mechanism that doesn't currently exist in `validate_fsm()`. Simplest v1 approach: warn whenever a `human_approval` state has no `timeout`, regardless of context.

**Reusable infrastructure identified:**
- `_interruptible_sleep()` at `executor.py:3378` — polling sleep with shutdown-signal respect, directly reusable for the HITL wait loop
- `_emit()` at `executor.py:3178` — event emission, emit `HUMAN_APPROVAL_REQUESTED_EVENT` (`"human_approval_requested"`, imported from `little_loops.fsm.communication_adapter` — FEAT-1930) on state entry
- `EventBus.register()` at `events.py:81` — subscribe to `human_response` events with glob filter
- `UnixSocketTransport._accept_loop()` at `transport.py:177` — socket-based polling with timeout, pattern for out-of-band response channel
- `SignalDetector` in `signal_detector.py` — detects in-band signals from action output; a `human_response` signal type could reuse this path
- `HandoffHandler` at `handoff_handler.py:68` — existing pause/spawn semantics; the HITL interrupt has analogous pause/resume behavior

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

**Corrections from re-verification (2026-09-03 research pass):**

- **`extra_routes` already covers `on_edit`/`on_timeout` with zero schema changes.** `StateConfig.extra_routes: dict[str, str]` (`schema.py:730`) captures any unrecognized `on_*` YAML key — `_known_on_keys` (`schema.py:896`) does not include `on_edit` or `on_timeout` — and already round-trips through `to_dict()`/`from_dict()`/`get_referenced_states()` with no further code change. There is a shipped precedent for exactly this shape: `_execute_sub_loop`'s sub-loop timeout routing (ENH-3019, `executor.py:~1271`) reads `state.extra_routes.get("timeout")` directly instead of a dedicated field. Implementation Steps #1 and the Integration Map's `schema.py` bullet already flag this as an "alternative" — this pass confirms it is the lower-risk, already-proven route, not merely an untested alternative.
- **`LLEvent` is never subclassed anywhere in this codebase.** `events.py:31-43` defines one non-subclassed `LLEvent(type: str, timestamp: str, payload: dict[str, Any])`; `FSMExecutor._emit()` (`executor.py:3550`) builds the flat dict directly, and event identity is carried by module-level `str` constants (e.g. `RATE_LIMIT_WAITING_EVENT`), not dataclass subclasses. This issue's own `## API/Interface` section sketches `HumanApprovalRequest(LLEvent)` / `HumanResponse(LLEvent)` as typed subclasses — that shape has no precedent here; the established convention is a flat event-name string plus a payload dict via `self._emit(event_name, data)`.
- **Path corrections**: `signal_detector.py` and `handoff_handler.py` (cited bare, without a directory prefix, in "Reusable infrastructure identified" above) both live under `scripts/little_loops/fsm/` — i.e. `fsm/signal_detector.py` and `fsm/handoff_handler.py`.
- **`HostCapabilities` moved**: now at `host_runner.py:128` (was cited at `:74`); fields are `streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed` — still no `interactive` field, confirming the issue's claim is current.
- **`StateConfig` anchors drifted**: class now at `schema.py:621` (was `:309`); `timeout` field at `:708` (was `:375`); `extra_routes` field at `:730` (was `:389`); `_known_on_keys` at `:896`. Function/class-name anchors are stable across passes; only line numbers moved (consistent with the drift already logged in Verification Notes below).
- **`scripts/tests/test_fsm_validation.py` no longer exists** — split (commit `9a4977a1`) into `test_fsm_validation_structural.py`, `test_fsm_validation_meta_rules.py`, `test_fsm_validation_shell_safety.py`, `test_fsm_validation_reachability.py`, `test_fsm_validation_evaluator_rules.py`. The timeout-warning test belongs in `test_fsm_validation_structural.py` (companion to `structural_rules.py`, where `_validate_state_action` lives).
- **`loops/examples/` does not exist** anywhere in the repo (confirmed via glob) — Implementation Steps #7's "add example loop under `loops/examples/`" names a proposed new location, not an existing one.
- **FEAT-1930 (`CommunicationAdapter` protocol) reconfirmed 0% implemented**: no `communication_adapter.py`, no `CommunicationAdapterExtension` Protocol in `extension.py` (which defines `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension`, `LLHookIntentExtension` only), no `send_alert`/`await_response`/`HumanResponse`/`AdapterResponse` symbols anywhere outside `.issues/` prose. This issue's `blocked_by: FEAT-1930` remains accurate and current.

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Correction to the 2026-09-03 pass's "FEAT-1930 reconfirmed 0% implemented" finding above — that finding is now stale.** As of this pass, `scripts/little_loops/fsm/communication_adapter.py` fully exists: `CommunicationAdapter(ABC)` with `send_alert()`, `await_response()`, `supports_async()`, `cancel_alert()`, plus `AdapterResponse`/`TimeoutResponse` dataclasses and the `HUMAN_APPROVAL_REQUESTED_EVENT`/`HUMAN_RESPONSE_EVENT` constants. `CommunicationAdapterExtension` Protocol exists in `extension.py:115` and is wired through `wire_extensions()` (`extension.py:274-281`). `FSMExecutor.resolve_communication_adapter()` exists at `executor.py:2661`. `TerminalAdapter(CommunicationAdapter)` (FEAT-1931) is fully implemented at `scripts/little_loops/fsm/adapters/terminal_adapter.py` with its own test suite (`scripts/tests/test_terminal_adapter.py`). FEAT-1930 and FEAT-1931 both show `status: Completed` via `ll-issues show`. `blocked_by: FEAT-1930` has been unlinked from this issue's frontmatter this pass (resolved dependency).
- **Still confirmed unimplemented (this issue's actual scope):** `resolve_communication_adapter()` has zero production callers — only two test files call it (`test_terminal_adapter.py`, `test_communication_adapter.py`). No `action_type == "human_approval"` or `state.type == "human_approval"` branch exists anywhere in `executor.py`/`schema.py`. `TerminalAdapter.send_alert()`/`await_response()` are never invoked from FSM state execution. This confirms the gap this issue tracks is entirely open, isolated to: the executor dispatch branch, the schema round-trip for `on_edit`/`on_timeout`, the validator warning, and the `HostCapabilities.interactive` flag.
- **Existing interim workaround, pre-dating this issue:** `scripts/little_loops/loops/loop-router.yaml:345-380` (`present_choices` state) uses `action_type: prompt` + `timeout:` + an `output_contains` evaluator as a manual HITL substitute — a human types a keyword back and the FSM routes on it. `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:47-58` has a commented-out block explicitly noting "Until FEAT-1794 lands, use the workaround pattern from loop-router.yaml". This is evidence of real demand for this feature but is not a design precedent to copy — it doesn't use `CommunicationAdapter` at all.

## API/Interface

New FSM state schema (`action_type: human_approval`):

```yaml
# In loop YAML definitions
check_human:
  action_type: human_approval
  action: "string — rendered to operator; supports ${captured.<state>.<field>} interpolation"
  timeout: 1800          # seconds; falls back to hitl.default_timeout (config, 1800); warned if absent
  on_yes: advance        # transition when operator approves
  on_no: execute         # transition when operator rejects
  on_edit: re_execute    # transition when operator edits; edit captured at ${captured.<state>.edit}
  on_timeout: advance    # fallback transition; defaults to on_no if unspecified
```

Events (flat `_emit()` dicts — `LLEvent` is never subclassed in this codebase;
the previous `HumanApprovalRequest(LLEvent)`/`HumanResponse(LLEvent)` sketch is
withdrawn, see Pre-implementation Review #4):

```python
# On entry, after adapter.send_alert() returns — emitted ONCE, by the executor only
self._emit(HUMAN_APPROVAL_REQUESTED_EVENT, {
    "state": state_name, "alert_id": alert_id, "prompt": rendered_prompt,
    "timeout": effective_timeout,
    "deadline_ts": iso_utc(now + effective_timeout),  # wall-clock; NOT the monotonic deadline
    "captured_context": {...},                          # minus the monotonic "deadline" key
})
# After routing. Deliberately NOT named "human_response": that name is the
# INBOUND verdict event the eventbus adapter subscribes to (FEAT-3384); an
# executor echo under the same name would re-trigger the adapter's observer.
self._emit("human_approval_resolved", {
    "state": state_name, "alert_id": alert_id, "verdict": verdict,   # approve|reject|edit|timeout|shutdown
    "elapsed_seconds": elapsed, "route": next_state,
    "reason": reason,   # reject reason from AdapterResponse.reason; "headless" on the
                        # no-TTY short-circuit (alert_id is None there); else None
})
```

Both events are registered in `generate_schemas.py` `SCHEMA_DEFINITIONS`,
`observability/schema.py` `DES_VARIANTS`, `session_store/schema.py`
`_LOOP_EVENT_TYPES`, and `docs/reference/EVENT-SCHEMA.md` (Third Review #17).

Validator rules: `ll-loop validate` SHALL warn (not error) when `action_type:
human_approval` is present without `timeout:` (the loop-level
`default_timeout:` does NOT count — it is the action-subprocess timeout,
Second Review #13). Unconditional — no caller-context scoping (see Decision
Rules). Suppression is by supplying `timeout:`, not by `timeout: 0`.

Config (`.ll/ll-config.json`):

```json
"hitl": { "channel": "terminal", "default_timeout": 1800 }
```

`default_timeout` is a new `HitlConfig` field (`config/core.py:185`); the
run is never unbounded — a state without `timeout:` waits at most this long.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — no `StateConfig` field changes needed: `extra_routes: dict[str, str]` (`:730`) already captures unrecognized `on_edit`/`on_timeout` keys and round-trips through `to_dict()`/`from_dict()`/`get_referenced_states()` with zero further code change (confirmed finding; precedented by ENH-3019's sub-loop timeout routing, `executor.py:~1271`)
- `scripts/little_loops/fsm/executor.py` — `_execute_state()`: add a dispatch branch for `action_type == "human_approval"` near the top of the method, alongside the existing `state.type == "learning"` check — not inside the generic action-and-evaluate fallthrough — calling a new `_execute_human_approval_state()` method (mcp_tool's `_action_mode()`/`_run_action()`/`_evaluate()` specialization doesn't apply here because mcp_tool never blocks mid-state and human_approval does)
- `scripts/little_loops/fsm/executor.py` — `_action_mode()` (`:3093`): add `if state.action_type == "human_approval": return "human_approval"` ahead of the `"shell"` fallthrough. **Reinstated** (Second Review #11, reversing Pre-implementation Review #9): the branch is not for dispatch — `_action_mode()` is consulted independently of `_execute_state()` at the BUG-1226 wall-clock flush (`:674`, `== "shell"` gate → `_flush_pending_shell_state()` would bash the prompt text), the tamper-guard snapshot (`:1998`), `_check_host_guard` (`:3708`) and `_maybe_wait_for_circuit` (`:3855`). Without it a `human_approval` state whose prompt doesn't start with `/` classifies as `"shell"`
- `scripts/little_loops/fsm/executor.py` — new method `_execute_human_approval_state()`: resolve the adapter via `resolve_communication_adapter()`, headless short-circuit (`not adapter.supports_async()` and stdin non-interactive — `None`/closed/not a tty; logs a WARNING and resolves with `reason: "headless"`, Third Review #18), compute `effective_timeout` (state → `hitl.default_timeout`, then clamped to the remaining `fsm.timeout` budget when the loop sets one, Third Review #20), call `adapter.send_alert()` (with `deadline` in `captured_context`), THEN emit `HUMAN_APPROVAL_REQUESTED_EVENT` with the returned `alert_id` and a wall-clock `deadline_ts`, then poll `adapter.await_response(alert_id, _HITL_TICK_SECONDS)` in an `_interruptible_sleep()`-shaped tick loop (not a single full-timeout call) that also calls `self._drain_inbound()` each tick and treats a per-tick `TimeoutResponse` as "no verdict yet" (Third Review #19), calling `adapter.cancel_alert()` on the timeout/shutdown routes, write `captured[<state>]`, emit `human_approval_resolved`, then route via `self._route(state, verdict_word, ctx)` where `verdict_word` ∈ `yes`/`no`/`edit`/`timeout` (`timeout` and `edit` fall back to `no`/`yes` respectively only when `_route()` returns `None`, Third Review #21)
- `scripts/little_loops/config/core.py:185` — `HitlConfig`: add `default_timeout: int = 1800` (+ `from_dict`, `to_dict` at `:916`); `scripts/little_loops/config-schema.json` `hitl` object: add the key (Second Review #13)
- `scripts/little_loops/generate_schemas.py` — `SCHEMA_DEFINITIONS`: add `human_approval_requested` and `human_approval_resolved`; regenerate `docs/reference/schemas/` via `ll-generate-schemas` (Third Review #17)
- `scripts/little_loops/observability/schema.py` — add a `DESVariant` for each new event to `DES_VARIANTS` (`test_des_schema.py` cross-checks the registry against `SCHEMA_DEFINITIONS` and `_LOOP_EVENT_TYPES`) (Third Review #17)
- `scripts/little_loops/session_store/schema.py:100` — `_LOOP_EVENT_TYPES`: add both events so `SQLiteTransport` persists them to `loop_events` (Third Review #17)
- `scripts/little_loops/cli/loop/feed.py` — `handle_event()` (`:672`) and `_format_event()` (`:1011` onward): one-line rendering for each new event (Third Review #22)
- `scripts/little_loops/fsm/validation/structural_rules.py:406` — `_validate_state_action()`: add human_approval validations — WARNING if no state `timeout` (message names the `hitl.default_timeout` fallback); ERROR unless a non-empty `action` and either `on_yes`+`on_no` or a `route:` table with `yes` and `no` keys (mirrors what `_route()` accepts). Loop-level `default_timeout` is irrelevant to this check (module split from `fsm/validation.py` in commit `9a4977a1`)
- `scripts/little_loops/fsm/validation/meta_rules.py:96` — MR-1: treat any state with `action_type == "human_approval"` as satisfying the non-LLM-evaluator requirement, and mention it in the MR-1 message. NOT via `NON_LLM_EVALUATOR_TYPES` in `_base.py` — that set holds `evaluate.type` values and is intersected against `state.evaluate.type`; a `human_approval` state has no `evaluate:` block, so adding the string there is a no-op (Pre-implementation Review #6)
- `scripts/little_loops/fsm/fsm-loop-schema.json:247` — Document `human_approval` in the `action_type` description string (no enum constraint exists to update — `fsm-loop-schema.json:436-444` documents allowed values in prose); no new `on_edit`/`on_timeout` properties needed since they route via `extra_routes`
- ~~`scripts/little_loops/host_runner.py:128` — `HostCapabilities`: add `interactive: bool` flag~~ — dropped (Pre-implementation Review #2): `HostCapabilities` is a frozen per-host-CLI descriptor built at six sites; `stdin.isatty()` is a per-process runtime fact and lives in the handler instead
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add a new "HITL phase" section
- `skills/create-loop/reference.md:415` — document `human_approval` action_type and new routing fields
- `docs/reference/CONFIGURATION.md:1581` § `hitl` — document `default_timeout` (FEAT-3384 also edits this section for `channel: eventbus`; coordinate)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:1170-1191` — `_execute_sub_loop()` builds the child `FSMExecutor` without copying `_contributed_adapters`. A `human_approval` state inside a `loop:` child therefore works only for the `terminal` channel (lazy fallback in `resolve_communication_adapter()`); the `eventbus` channel raises `CommunicationAdapterNotFound` there. Propagation is scoped to FEAT-3384 (its Second Review #6); this issue's tests need not cover sub-loop nesting
- Option A (hardcoded dispatch, decided — see frontmatter `decision`) touches no extension-registration callers: `scripts/little_loops/extension.py:81` (`ActionProviderExtension`), `extension.py:246` (`wire_extensions()` → `_contributed_actions`), and `cli/loop/run.py:391` (`wire_extensions()`) are the deferred Option B's dependent files, not this issue's.
- `scripts/little_loops/fsm/schema.py` — `get_referenced_states()` (`:539`) already includes `extra_routes` values in its output; `on_edit`/`on_timeout` targets flow through automatically once `extra_routes` captures them — no code change needed here (confirmed finding)

### Similar Patterns
- `action_type: mcp_tool` — model the mode-classification branch after `_action_mode()` and the JSON-schema/validator pattern after `_validate_state_action()` in `validation/structural_rules.py`. Its dispatch (`_run_action()`) is *not* the pattern to follow for the executor branch itself: mcp_tool's specialization lives entirely in `_action_mode()`/`_run_action()`/`_evaluate()` because it never blocks mid-state, while `human_approval` does — that branch belongs in `_execute_state()` calling a new `_execute_human_approval_state()` method instead (confirmed finding, Program Design).
- `_interruptible_sleep()` in `executor.py` — polling-with-timeout pattern for blocking while respecting shutdown signals — the `_execute_human_approval_state()` handler must build its own tick loop calling `adapter.await_response()` shaped like this, not a single call with the full timeout (which would defeat shutdown responsiveness)
- `_emit()` in `executor.py` — event emission pattern — emit `HUMAN_APPROVAL_REQUESTED_EVENT` (imported from `little_loops.fsm.communication_adapter`, now implemented — FEAT-1930/FEAT-1931 both `status: Completed`) on state entry
- `events.py:70` — `EventBus` with `register()`/`emit()`/`add_transport()`: existing pub/sub infrastructure
- `transport.py:115` — `UnixSocketTransport._accept_loop()`: socket polling with timeout — pattern for out-of-band response channel
- `schema.py:730` — `extra_routes: dict[str, str]`: already captures unrecognized `on_*` keys, including `on_edit`/`on_timeout`, with zero schema changes — confirmed as the implementation path (not merely an option), precedented by ENH-3019's sub-loop timeout routing (`executor.py:~1271`)
- **Correction**: `PushNotification` does NOT exist in the codebase (confirmed by grep). The event bus + `WebhookTransport` (`transport.py`) is the closest notification infrastructure. v1 should use terminal output + event bus; PushNotification/IM adapter is v2 scope.

### Tests
- `scripts/tests/test_fsm_executor.py:685` — `TestActionTypeMcpTool` (line drifted from `:401`): model new `TestActionTypeHumanApproval` class after this pattern (mock event callback, verify approve/reject/edit/timeout routing)
- `scripts/tests/test_fsm_schema.py:2062` — `TestMcpToolSchema` (line drifted from `:1801`): model new `TestHumanApprovalSchema` class after this (field acceptance, round-trip, validation pass/fail)
- `scripts/tests/test_fsm_validation_structural.py` — add tests for the unconditional timeout warning on `human_approval` without `timeout:` (companion to `structural_rules.py`; `test_fsm_validation.py` no longer exists — split by commit `9a4977a1`)
- `scripts/tests/test_fsm_executor.py:4246` — `TestContributedActionDispatch`: reference only for the deferred Option B (extension-based) path, not this issue's chosen Option A
- `scripts/tests/test_generate_schemas.py:21` / `:124` — hard-coded `SCHEMA_DEFINITIONS` count (59) and generated-file count (59): bump both to 61 (Third Review #17)
- `scripts/tests/test_des_schema.py` — no edit needed, but it fails until the two `DESVariant`s exist (`test_variants_cover_all_schema_definitions`, `test_variants_cover_all_loop_event_types`)

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (phase chain table, decision guide, troubleshooting)
- `skills/create-loop/reference.md` (FSM field reference, line ~415 for `action_type` docs)

### Configuration
- `.ll/ll-config.json` — `hitl.default_timeout` (int seconds, default 1800) is now in scope (Second Review #13); `hitl.notification_channel` remains deferred
- `LL_HOST_CLI` env var — not consulted by this feature (Pre-implementation Review #2): headlessness is a property of the process's stdin and the adapter's `supports_async()`, not of the host CLI
- `hitl.channel` (`HitlConfig`, `config/core.py:185`) — selects the adapter via `resolve_communication_adapter()`; `eventbus` (FEAT-3384) needs `ll-loop run --serve` for out-of-process verdicts

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Test anchor drift (2026-09-04 pass):** `TestActionTypeMcpTool` is now at `scripts/tests/test_fsm_executor.py:685` (Implementation Steps cites `:401`, now stale). `TestMcpToolSchema` is now at `scripts/tests/test_fsm_schema.py:2062` (Implementation Steps cites `:1801`, now stale). Both classes' internal test structure is unchanged — model `TestActionTypeHumanApproval` on `TestActionTypeMcpTool`'s pattern (private `_make_*_fsm()` helper, mock `_run_subprocess`/action runner, assert on `executor.run().final_state`), and `TestHumanApprovalSchema` on `TestMcpToolSchema`'s pattern (field-acceptance test + `to_dict()`/`from_dict()` round-trip test).
- `HostCapabilities` reconfirmed at `host_runner.py:128-152`; fields present: `streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`. No `interactive` field. The only `isatty()` precedent in the codebase is `sys.stdin.isatty()` at `hooks/__init__.py:194` (gates stdin-read for a hook payload, unrelated subsystem) — there is no existing `HostCapabilities`-level interactivity check to model the new flag after; it would be new territory for that dataclass.
- `action_type` has no enum constraint in `fsm-loop-schema.json` — it's a free-text string with a `description` field (`fsm-loop-schema.json:436-444`) documenting the recognized values in prose. Adding `human_approval` support means extending that description string, not adding an enum member.

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

- **Anchor refresh (2026-09-05 pass, all re-grepped current):** `_execute_state` now `:1974` (was `:1948`), `resolve_communication_adapter` `:2682` (was `:2661`), `_route` `:2994` (was `:2973`), `_action_mode` `:3114` (was `:3093`), `_emit` `:3602` (was `:3550`), `_interruptible_sleep` `:3885` (was `:3833`), `_drain_inbound` `:557` (unchanged since last pass). `StateConfig`/`extra_routes`/`timeout`/`_known_on_keys` anchors (`schema.py:621/730/708/896`) all reconfirmed exact, no drift.
- **Correction — the BUG-1226 wall-clock flush gate is NOT at `executor.py:674`** as currently cited: line `674` now falls inside an unrelated `max_iterations` fallback comment block. The actual gate is `run()` lines `677-698`, with the `_action_mode(pending) == "shell"` check at line `695` (matching the already-confirmed `run():695` seed) → `self._flush_pending_shell_state(pending)` at `:3082` → `self._run_action(...)` at `:3104`.
- **Correction — `fsm-loop-schema.json:247` does not contain the `action_type` description.** Line `247` is inside the unrelated `safety.repeated_failure.window` schema block. The actual `action_type`/`params` description properties are at `fsm-loop-schema.json:436-444` (matches the issue's own alternate citation of that range).
- **Correction — `skills/create-loop/reference.md:415` currently has zero `human_approval`/`FEAT-1794`/`HITL` content.** That line sits inside an unrelated `diff_stall_gate` example (`on_no: skip_item`). The file has extensive `action_type` documentation elsewhere (lines 118, 142, 152, 164, 206, 411, 427-524, 699-1341) but none of it mentions `human_approval` yet — this doc update is a net-new addition, not an edit to existing `human_approval` prose at that line.
- **Test anchor drift**: `TestActionTypeMcpTool` now at `test_fsm_executor.py:686` (was `:685`, off by one). `TestContributedActionDispatch` now at `test_fsm_executor.py:6782` (was cited `:4246` — drifted ~2536 lines; this is a reference-only citation for the deferred Option B path per the issue's own note, not load-bearing for the chosen Option A implementation).
- **Reconfirmed unimplemented**: repo-wide grep for `human_approval` (no filter) returns exactly 3 source-tree files — `test_communication_adapter.py`, `communication_adapter.py` (the two event-name constants only), and the commented-out block in `harness-plan-research-implement-report.yaml:47-58`. Zero hits in `executor.py`, `schema.py`, `fsm-loop-schema.json`, `structural_rules.py`, `meta_rules.py`, or either test file's actual test bodies — the gap this issue tracks remains entirely open.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Re-confirmed 2026-09-04 (fresh pass, all anchors re-grepped):** `_action_mode()` :3093 (was :3062), `_execute_state()` :1953 (was :1948), `_run_action()` :2317 (was :2312), `_emit()` :3581 (was :3550), `_interruptible_sleep()` :3864 (was :3833), `resolve_communication_adapter()` :2661. `StateConfig` :621, `timeout` field :708, `extra_routes` field :730 — unchanged since the prior pass. `on_yes`/`on_no` are separate declared dataclass fields (`schema.py:698-699`), not part of `extra_routes` — only unrecognized `on_*` keys (which today excludes `on_yes`/`on_no`/`on_success`/`on_failure`/etc. per `_known_on_keys`, `schema.py:896-908`) fall into `extra_routes`.
- **New architectural finding — `await_response()`'s re-entrant contract requires a net-new executor-side tick loop.** `CommunicationAdapter.await_response()`'s docstring (`communication_adapter.py:70-78`) states the intended calling contract explicitly: "the executor polls this in short ticks so shutdown stays responsive... a verdict that arrives between calls must be retained and returned on the next call." No code anywhere currently implements that tick loop — `_interruptible_sleep()` is the closest existing shape (100ms-tick `while` loop checking `self._shutdown_requested`) but nothing today calls `await_response()` from inside such a loop. The `_execute_human_approval_state()` handler this issue adds must build this loop itself, e.g. repeatedly calling `adapter.await_response(alert_id, tick_duration)` inside an `_interruptible_sleep()`-shaped `while` guarding on `state.timeout` and `self._shutdown_requested`, rather than a single call with the full timeout (which would defeat shutdown responsiveness).

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

- **Re-confirmed 2026-09-05 (fresh pass, all anchors re-grepped again — further drift since the 2026-09-04 pass):** `_execute_state` `:1974` (was `:1948`), `_action_mode` `:3114` (was `:3062`/`:3093`), `_route` `:2994` (was `:2973`), `_emit` `:3602` (was `:3550`), `_interruptible_sleep` `:3885` (was `:3833`), `_drain_inbound` `:557` (unchanged), `resolve_communication_adapter` `:2682` (was `:2661`).
- **`_execute_state()`'s current dispatch order** (`executor.py:1974` onward): `ctx = self._build_context()` (`:1984`) → sub-loop dispatch `if state.loop is not None: return self._execute_sub_loop(...)` (`:1987-1993`) → the learning-state dispatch this issue models its branch after, `if state.type == "learning" and state.learning is not None: return self._execute_learning_state(...)` (`:1995-2000`) → tamper-guard snapshot gated on `_action_mode(state) != "contract"` (`:2016-2024`) → generic action path (`:2028` onward, `_action_mode(state) != "contract"` check at `:2094`). A `human_approval` branch belongs at `:1994-2001`, before both the tamper-guard snapshot and the generic action dispatch — both of which already consult `_action_mode()`, reinforcing why the `_action_mode()` branch (Second Review #11) is still needed even though dispatch itself happens earlier.
- **`_action_mode()`'s current fallthrough** (`executor.py:3114-3129`): `contract`→`:3116`, `mcp_tool`→`:3118`, `prompt`/`slash_command`→`:3120`, `shell`→`:3122`, contributed actions→`:3124`, action starting with `/`→`:3126`, else falls through to `return "shell"` at `:3129`. Confirms an unmapped `human_approval` state whose `action:` text doesn't start with `/` reaches this final fallthrough today.
- **`_route()`'s dynamic verdict resolution** (`executor.py:2994-3066`): `route:` table path `:3025-3041` (including `_uncertain`-suffix fallback bounded to one level, and `state.route.error` for `verdict in ("error", "no")`); shorthand `on_yes`/`on_no`/etc. `:3043-3055`; dynamic `on_<verdict>` via `extra_routes` `:3057-3059` (`if verdict in state.extra_routes: return self._resolve_route(state.extra_routes[verdict], ctx)`) — this is the exact mechanism, confirmed unchanged, that resolves `on_edit`/`on_timeout` targets at runtime with zero further `_route()` code needed.

### Types
- No new data type is structurally required for routing: `StateConfig.extra_routes: dict[str, str]` (`schema.py:730`) is the existing container that can carry `edit`/`timeout` verdict targets — see Proposed Solution → Codebase Research Findings for why dedicated `on_edit`/`on_timeout` fields are not required.

### Signatures
- `FSMExecutor._action_mode(self, state: StateConfig) -> str` (`executor.py:3093`) — returns `"human_approval"` for the new state type. Modified after all (Second Review #11 reverses Pre-implementation Review #9): it is consulted by the wall-clock flush, tamper guard, host guard and circuit wait independently of `_execute_state()` dispatch.
- `FSMExecutor._route(self, state: StateConfig, verdict: str, ctx: InterpolationContext) -> str | None` (`executor.py:2973`) — the existing verdict router; the handler feeds it `yes`/`no`/`edit`/`timeout` instead of reading `on_yes`/`extra_routes` directly, so `route:` tables and `_resolve_route()`'s `advance`/`done`/interpolation apply (Second Review #12). The interceptor `before_route`/`after_route` hooks (`executor.py:2292/2312`) live in the generic action path and are bypassed, as the learning-state and sub-loop handlers already do.
- `HitlConfig.default_timeout: int = 1800` (`config/core.py:185`) — new field; read via `self._get_br_config().hitl.default_timeout` next to the existing `.hitl.channel` read in `resolve_communication_adapter()`.
- `FSMExecutor._drain_inbound(self) -> None` (`executor.py:557`) — called once per HITL tick so `--serve` inbound verdicts are re-emitted onto the bus while the state is blocked (Pre-implementation Review #7).
- `FSMExecutor._execute_human_approval_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None` — new; same shape as `_execute_learning_state()` / `_execute_sub_loop()`. `None` only on shutdown.
- `_HITL_TICK_SECONDS: float = 0.5` — new module constant in `executor.py`; the per-call `timeout` handed to `adapter.await_response()` (Third Review #19).
- `FSMExecutor._execute_state(self, state: StateConfig) -> str | None` (`executor.py:1974`) — per-state dispatcher. The `human_approval` branch must sit near the top of this method, alongside the existing `state.type == "learning"` check (`executor.py:1973-1974`), not inside the generic action-and-evaluate fallthrough `mcp_tool` uses — `mcp_tool`'s specialization lives entirely in `_action_mode`/`_run_action`/`_evaluate` because it never blocks mid-state, but `human_approval` does.
- `FSMExecutor._interruptible_sleep(self, duration: float, on_heartbeat: Callable[[float], None] | None = None) -> float` (`executor.py:3833`) — existing blocking-wait-with-shutdown-respect primitive, already reused by two unrelated call sites (`_check_host_guard`, `_maybe_wait_for_circuit`).
- `FSMExecutor._emit(self, event: str, data: dict[str, Any]) -> None` (`executor.py:3550`) — event emission; takes a flat event-name string and a payload dict, not an `LLEvent` subclass (see Proposed Solution → Codebase Research Findings: `LLEvent` is never subclassed in this codebase).

### Call Path
`FSMExecutor.run()` -> `_execute_state()` [new `human_approval` branch beside the `state.type == "learning"` branch] -> new `_execute_human_approval_state()` -> `adapter = self.resolve_communication_adapter()` -> headless short-circuit check -> `alert_id = adapter.send_alert(...)` -> `_emit(HUMAN_APPROVAL_REQUESTED_EVENT, {alert_id, ...})` (sole emitter) -> blocking wait shaped like `_interruptible_sleep()`: each tick `self._drain_inbound()` then `adapter.await_response(alert_id, tick)` (FEAT-1930, implemented) -> on the timeout/shutdown routes, call `adapter.cancel_alert(alert_id)` (FEAT-1930 Pre-implementation Review #15) -> write `captured[<state>]` -> `_emit("human_approval_resolved", ...)` -> `self._route(state, "yes"|"no"|"edit"|"timeout", ctx)` (which itself resolves `on_yes`/`on_no`, `route:` tables and `extra_routes["edit"|"timeout"]`), falling back to `_route(state, "no", ctx)` for an unrouted `timeout` and `_route(state, "yes", ctx)` for an unrouted `edit`.

### Decision Rules
- Gate: `ll-loop validate` warning when a `human_approval` state has no explicit `timeout:`.
- Exact input: `state.action_type == "human_approval" and state.timeout is None` — reuses the existing `timeout: int | None` field on `StateConfig` (`schema.py:708`). The loop-level `default_timeout` (`schema.py:1396`) is deliberately NOT consulted: every executor use of it (`executor.py:2417/2437/2502/3453`) is the action-subprocess timeout, so a loop that sets `default_timeout: 600` for its LLM actions would otherwise silently cap human waits at ten minutes and suppress this warning (Second Review #13).
- Runtime: `effective = state.timeout if state.timeout is not None else hitl.default_timeout` (config, default 1800). The wait is therefore never unbounded. `0` is treated as an immediate timeout, consistent with its literal meaning; it is NOT a suppression idiom (Pre-implementation Review #5).
- Clamp: when `fsm.timeout` is set, `effective = min(effective, remaining_loop_budget)` where `remaining_loop_budget = fsm.timeout - (elapsed_ms + elapsed_offset_ms) / 1000` (the same arithmetic as `run()`'s wall-clock check, `executor.py:677-680`). The loop timeout is only checked between states, so without the clamp a wait can overrun it and the verdict is routed then discarded by `_finish("timeout")` (Third Review #20).
- Headless: `not adapter.supports_async()` and (`sys.stdin is None or sys.stdin.closed or not sys.stdin.isatty()`) → route `timeout` immediately with `reason: "headless"` and a WARNING log, no alert sent (the `TerminalAdapter` would otherwise sleep the full duration on closed stdin, and raises from `fileno()` on a closed stream). This is the normal path for `ll-loop run --background` (stdin is `DEVNULL`) and for loops launched from a Claude Code Bash call (Third Review #18).
- Per-tick semantics: `TimeoutResponse` from `await_response()` = "no verdict yet"; only `time.monotonic() >= deadline` in the handler is a timeout (Third Review #19).
- Route-table fallbacks: `edit`→`yes` and `timeout`→`no` fallbacks fire only when `_route()` returns `None`. With a `route:` table, `route.default` catches an unrouted `edit`/`timeout` first and `route.error` catches `no` (Third Review #21).
- Known limitation: stdin EOF *after* the wait starts is invisible through the adapter protocol (`TerminalAdapter` sets a private `_stdin_closed` and logs one warning); the wait runs to the deadline. Not solved here.
- Scoping: unconditional. Prior research (Proposed Solution → Codebase Research Findings, existing) found `ll-auto`/`ll-sprint` do not directly load FSM loop YAMLs, so a "referenced by unattended automation" cross-reference check is infeasible for v1 — warn whenever the state timeout is absent, regardless of caller context.
- Escape hatch: WARNING, not ERROR — loop author suppresses by supplying `timeout:` on the state.
- Routing shape: accept `on_yes`+`on_no` OR a `route:` table containing `yes` and `no`; ERROR otherwise. `_route()` handles both at runtime.

## Implementation Steps

1. **Schema**: No `StateConfig` field changes needed — the prompt text lives in the existing `action: str | None` field (`schema.py:693`, same slot `action_type: prompt` uses; there is no `StateConfig.prompt` — the `prompt` at `schema.py:119` belongs to `EvaluateConfig`), and `extra_routes: dict[str, str]` (`schema.py:730`) already captures unrecognized `on_edit`/`on_timeout` keys and round-trips through `to_dict()`/`from_dict()`/`get_referenced_states()` with zero further code change (confirmed 2026-09-03; precedented by ENH-3019's sub-loop timeout routing, `executor.py:~1271`). Only update the `action_type` description string in `fsm-loop-schema.json` (`:436-444`; the earlier `:247` citation was wrong) to document `human_approval` (no enum constraint exists — `action_type` is free text). `stateConfig` already declares `patternProperties: ^on_` alongside `additionalProperties: false`, so `on_edit`/`on_timeout` pass JSON-schema validation with no further change (confirmed 2026-09-05).
2. **Validator** (`fsm/validation/structural_rules.py:406`): In `_validate_state_action()`, add for `action_type == "human_approval"`: ERROR unless a non-empty `action` and either `on_yes`+`on_no` or a `route:` table with `yes`/`no` keys; WARNING if `state.timeout is None` (message: "no timeout: — waits fall back to hitl.default_timeout"). No `FSMLoop` threading needed — the loop-level `default_timeout` is not consulted (Second Review #13). In `fsm/validation/meta_rules.py:96`, make MR-1 pass when any state has `action_type == "human_approval"` and add it to the MR-1 message's list — do NOT touch `NON_LLM_EVALUATOR_TYPES` (see Integration Map).
3. **Executor dispatch** (`fsm/executor.py`): In `_execute_state()`, add a dispatch branch before the generic action path — follow the learning-state dispatch pattern at the top of the method: `if state.action_type == "human_approval": return self._execute_human_approval_state(state, ctx)`. ALSO add `if state.action_type == "human_approval": return "human_approval"` to `_action_mode()` (`:3093`) before the `"shell"` fallthrough — not for dispatch, but so the `== "shell"` / `!= "prompt"` heuristics at `:674` (BUG-1226 flush → `_flush_pending_shell_state()`), `:1998`, `:3708`, `:3855` never treat the prompt text as a shell command (Second Review #11).
4. **HITL handler** (new method `_execute_human_approval_state()` in `fsm/executor.py`): Render `state.action` with `${captured.*}` interpolation, resolve the active `CommunicationAdapter` via `resolve_communication_adapter()` (`executor.py:2661`, FEAT-1930 — implemented). Compute `effective_timeout` per Decision Rules (`state.timeout` else `hitl.default_timeout`, then clamped to the remaining `fsm.timeout` budget when the loop sets one — Third Review #20) and `deadline = time.monotonic() + effective_timeout`. Headless short-circuit: if `not adapter.supports_async()` and stdin is non-interactive (`sys.stdin is None or sys.stdin.closed or not sys.stdin.isatty()`), log a WARNING (`"human_approval state '<name>': stdin is not interactive and channel '<channel>' cannot reach a remote operator — routing on_timeout; set hitl.channel: eventbus and run with --serve for unattended runs"`) and route `timeout` immediately (emit `human_approval_resolved` with `verdict: "timeout"`, `reason: "headless"`, `alert_id: None`, no alert sent — Third Review #18). Otherwise call `adapter.send_alert(loop_name, state_name, prompt, {"deadline": deadline, ...})`, THEN `self._emit(HUMAN_APPROVAL_REQUESTED_EVENT, {alert_id, state, prompt, timeout, deadline_ts (ISO wall-clock), captured_context minus "deadline"})` — the executor is the sole emitter of this event; adapters never emit it (FEAT-3384 Review #2). Poll `adapter.await_response(alert_id, _HITL_TICK_SECONDS)` inside an `_interruptible_sleep()`-shaped tick loop guarding on `deadline` and `self._shutdown_requested`; a per-tick `TimeoutResponse` just continues the loop (Third Review #19); call `self._drain_inbound()` at the top of each tick so `--serve` inbound verdicts reach the bus mid-wait. On timeout: `adapter.cancel_alert(alert_id)`, `next = self._route(state, "timeout", ctx) or self._route(state, "no", ctx)`. On shutdown: `adapter.cancel_alert(alert_id)`, emit resolved with `verdict: "shutdown"`, return `None`. On verdict: write `self.captured[state_name] = {"output": edited_text or "", "verdict": verdict, "edit": edited_text, "reason": reason}`, emit `human_approval_resolved`, then `next = self._route(state, {"approve": "yes", "reject": "no", "edit": "edit"}[verdict], ctx)`; if `edit` resolves to `None` (no `on_edit`), fall back to `_route(state, "yes", ctx)` and log a warning. `_route()` already covers `route:` tables, `extra_routes`, and `_resolve_route()`'s `advance`/`done`/`${...}` handling (Second Review #12). The executor never imports a specific adapter — it only calls the protocol methods.
5. **Config**: add `default_timeout: int = 1800` to `HitlConfig` (`config/core.py:185`, `from_dict`, and the `to_dict` block at `:916`) and to the `hitl` object in `config-schema.json` (Second Review #13). Host-capability flag remains dropped (Pre-implementation Review #2).
5b. **Event registration** (code, test-gated — Third Review #17): follow CONTRIBUTING § Event Schema Maintenance for `human_approval_requested` and `human_approval_resolved` — add both to `SCHEMA_DEFINITIONS` in `generate_schemas.py`, run `ll-generate-schemas` and commit the two new `docs/reference/schemas/*.json`, add a frozen `DESVariant` for each to `DES_VARIANTS` in `observability/schema.py`, add both to `_LOOP_EVENT_TYPES` in `session_store/schema.py:100`, add sections to `docs/reference/EVENT-SCHEMA.md`, and bump the two hard-coded counts in `test_generate_schemas.py` (`:21`, `:124`) from 59 to 61. Then add one-line rendering for each event in `cli/loop/feed.py` (`handle_event` `:672`, `_format_event` `:1011` onward) so quiet runs and log files show the wait (Third Review #22).
6. **Tests**: Add `TestActionTypeHumanApproval` in `test_fsm_executor.py` (model after `TestActionTypeMcpTool`, now at line `:686`) — inject a mock adapter into `executor._contributed_adapters`, verify approve/reject/edit/timeout/shutdown routing (including a `route:`-table variant where an unrouted `edit` lands on `route.default`, not `on_yes` — Third Review #21 — and an `advance` target), the single `human_approval_requested` emission (with `alert_id` and `deadline_ts`) plus `human_approval_resolved`, the `captured[<state>]` shape, the headless short-circuit for a sync adapter (including `sys.stdin = None`; asserts `reason: "headless"` and the WARNING log), that an async adapter is NOT short-circuited under non-TTY stdin, that `_action_mode()` returns `"human_approval"`, that a mock adapter returning `TimeoutResponse` on the first N ticks and a verdict on tick N+1 routes on the verdict (Third Review #19), that the `hitl.default_timeout` fallback (not `fsm.default_timeout`) bounds the wait, and that `fsm.timeout` clamps the wait (Third Review #20). Add `TestHumanApprovalSchema` in `test_fsm_schema.py` (model after `TestMcpToolSchema`, now at line `:2062`). Add the timeout-warning tests (state timeout present / absent; loop `default_timeout` present must NOT suppress) and the routing-shape tests in `test_fsm_validation_structural.py`, an MR-1 test in `test_fsm_validation_meta_rules.py`, and a `HitlConfig` round-trip test next to the existing config tests.
7. **Docs and examples**: Add HITL phase section to `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`; document `human_approval` action_type and routing fields in `skills/create-loop/reference.md` (net-new prose near the `action_type` reference, `:427-524`; the `:415` citation is inside an unrelated example); add an example loop under `scripts/little_loops/loops/` with `visibility: example` (bump the README.md loop count and re-run `ll-adapt --host <gemini|kimi-code|qwen> --apply` + `command cp -f README.md scripts/README.md` for the mirror gates). **Do NOT uncomment** the workaround block in `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:47-58` — that would make a shipped, unattended-by-design loop block for up to 30 minutes per run (Third Review #23). Instead fix the comment so it is copy-pasteable once this lands: `prompt:` → `action:` (Pre-implementation Review #3), add `timeout:` and `on_timeout:`, and drop the "Until FEAT-1794 lands" sentence.
   > ⚠ Superseded — this step originally directed the example loop to `loops/examples/`. That directory does not exist anywhere in the repo (confirmed via glob) and was never a real location; corrected to `scripts/little_loops/loops/` with `visibility: example`. Event registration moved out of this step into 5b (it is test-gated code, not docs).
8. **EPIC-1929 siblings** (separate issues, not in this FEAT's scope): Terminal adapter (FEAT-1931), PushNotification adapter (FEAT-1932), future adapters (Slack, Telegram, webhook).

## Pre-implementation Review (2026-09-04)

_Manual review against the codebase before implementation. Each item below has already been folded into the sections above; this list is the index of what changed and why._

1. **Event ownership (cross-issue with FEAT-3384 Review #2).** `human_approval_requested` is emitted exactly once, by the executor via `_emit()`, after `send_alert()` returns so it carries `alert_id`, `run_id`, `loop`, `ts`. Adapters never emit it. Previously both this issue (AC5) and FEAT-3384 (`send_alert()`) emitted it on the same bus (`wire_extensions` receives `executor.event_bus`, which `_handle_event` fans every executor event into), producing two events with complementary missing fields.
2. **Headless detection moved out of `HostCapabilities`.** That dataclass is frozen, per-host-CLI, and constructed at six sites; `stdin.isatty()` is a per-process fact. More importantly, "not interactive → `on_timeout`" would have defeated the `eventbus` adapter under `ll-auto`/`nohup` — the exact context it exists for. Rule is now `not adapter.supports_async() and not sys.stdin.isatty()`.
3. **`prompt:` is not a `StateConfig` field.** `schema.py:119`'s `prompt` belongs to `EvaluateConfig`; `StateConfig.from_dict` silently drops an unknown `prompt:` key. The prompt text uses `action:`, matching `action_type: prompt` and the loop-router workaround.
4. **API/Interface rewritten as flat `_emit()` dicts.** The `HumanApprovalRequest(LLEvent)`/`HumanResponse(LLEvent)` subclasses contradicted the issue's own finding that `LLEvent` is never subclassed. The post-verdict event is named `human_approval_resolved`, not `human_response`: `human_response` is the inbound verdict event the eventbus adapter subscribes to (filter `HUMAN_RESPONSE_EVENT`), so an executor echo under that name would re-trigger the adapter's own observer.
5. **`timeout: 0` dropped as a suppression idiom.** Every `state.timeout or self.fsm.default_timeout or N` idiom in the executor treats 0 as unset, and a literal 0 means "time out now". Effective timeout is state, then loop-level `default_timeout`; the validator warns only when both are absent.
6. **MR-1 wiring corrected.** `NON_LLM_EVALUATOR_TYPES` is derived from `EVALUATOR_REQUIRED_FIELDS` and intersected with `state.evaluate.type` (`meta_rules.py:96`); a `human_approval` state has no `evaluate:` block, so adding the string there was a no-op. MR-1 now checks `action_type == "human_approval"` directly.
7. **Inbound verdicts during the wait (cross-issue with FEAT-3384 Review #1).** `_drain_inbound()` (`executor.py:549`) runs once per iteration between states; nothing drains during a blocking wait. The HITL tick loop calls it each tick so a `--serve` POST reaches the bus while the state is blocked.
8. **Handler details that were unspecified**: pass `captured_context["deadline"]` (monotonic; `TerminalAdapter` renders "Time remaining" from it); persist `verdict`/`edit`/`reason`/`output` under `captured[<state>]` (reject `reason` was being dropped); on shutdown cancel the alert and return `None` so `run()`'s interrupted-save branch (`executor.py:923`) fires.
9. **`_action_mode()` change dropped** — dispatch happens in `_execute_state()` before `_action_mode()` is consulted; the branch would be dead code. `loops/examples/` replaced with `scripts/little_loops/loops/` + `visibility: example`.
10. **Scope Boundary #1/#2 with FEAT-1930 marked resolved** — `AdapterResponse` with three-way `Verdict` shipped.

Recommended order: implement this issue first against the `TerminalAdapter`, then FEAT-3384; items 1 and 7 are the contract FEAT-3384 builds on.

## Second Review (2026-09-04, post-confidence-check)

_Verified against the working tree after the confidence check scored this issue 100/100. Each item is already folded into the sections above; this is the index. Numbering continues from the first review._

11. **Pre-implementation Review #9 reversed — `_action_mode()` needs a `"human_approval"` branch.** The first review dropped it as dead code because dispatch happens in `_execute_state()`. But `_action_mode()` is also called from `run()`'s BUG-1226 wall-clock flush (`executor.py:674`, gated on `== "shell"`), the tamper-guard snapshot (`:1998`), `_check_host_guard` (`:3708`) and `_maybe_wait_for_circuit` (`:3855`). Its fallthrough returns `"shell"` for any unknown `action_type` whose action doesn't start with `/`, so if `fsm.timeout` fires in the route→`state_enter` window with a `human_approval` state pending, `_flush_pending_shell_state()` would run the operator prompt through bash. Returning a distinct mode excludes it from every such heuristic.
12. **Route through `_route()`.** The handler was reading `state.on_yes`/`extra_routes[...]` directly, which silently ignores a `route:` table and bypasses `_resolve_route()` (`advance`/`done`/`${...}`). `_route()` (`executor.py:2973`) already resolves all three, including dynamic `extra_routes` verdicts — feed it `yes`/`no`/`edit`/`timeout`. The validator accepts a `route:` table as an alternative to `on_yes`+`on_no` for the same reason.
13. **`fsm.default_timeout` dropped from the timeout chain; `hitl.default_timeout` added.** Every executor use of the loop-level `default_timeout` (`executor.py:2417/2437/2502/3453`) is the action-subprocess timeout; only one built-in loop sets it (`14400`). Falling back to it would let `default_timeout: 600` (a reasonable LLM-action bound) cap human waits at ten minutes and, worse, suppress the validator warning. The new `HitlConfig.default_timeout` (1800) is the fallback instead, so the wait is never unbounded and the warning only asks the author to be explicit.
14. **`deadline` is monotonic; the event needs a wall-clock `deadline_ts`.** `time.monotonic()` is process-local, so the value the `TerminalAdapter` renders "Time remaining" from is meaningless to SSE/socket/JSONL consumers of `human_approval_requested`. Keep `deadline` in `captured_context` for the adapter; emit `timeout` plus an ISO `deadline_ts` on the bus.
15. **Headless guard hardened.** `sys.stdin` can be `None` (no console) or closed; `TerminalAdapter._read_line()` calls `stream.fileno()` and raises `ValueError` on a closed stream. The rule is `sys.stdin is None or sys.stdin.closed or not sys.stdin.isatty()`.
16. **Sub-loop nesting noted, scoped to FEAT-3384.** `_execute_sub_loop()` (`executor.py:1170-1191`) doesn't copy `_contributed_adapters` into the child executor. `terminal` still works there via the lazy fallback; `eventbus` would raise `CommunicationAdapterNotFound`. Recorded under Dependent Files; propagation is FEAT-3384's Second Review #6.

## Third Review (2026-09-05, pre-implementation)

_Verified against the working tree at `5cf210cad`. Each item is already folded into the sections above; this is the index. Numbering continues from the second review._

17. **Event registration is test-gated code, not docs.** Step 7 filed `observability/schema.py` under Docs. CONTRIBUTING § Event Schema Maintenance requires `SCHEMA_DEFINITIONS` (`generate_schemas.py`) + regenerated `docs/reference/schemas/` + a `DESVariant` in `DES_VARIANTS` + `EVENT-SCHEMA.md`. `test_generate_schemas.py:21`/`:124` hard-code the count (59 → 61) and `test_des_schema.py` cross-checks the registry. Both events also join `_LOOP_EVENT_TYPES` (`session_store/schema.py:100`) so they persist for `ll-logs`. Now Step 5b.
18. **Background runs always short-circuit the terminal channel.** `run_background()` re-execs with `stdin=subprocess.DEVNULL` (`cli/loop/runner.py:296`); stdin is also non-TTY inside a Claude Code Bash call. With `hitl.channel: terminal` every such run routes `on_timeout` instantly. The short-circuit now logs a WARNING pointing at `hitl.channel: eventbus` and emits `reason: "headless"` so it is distinguishable from a real timeout.
19. **Per-tick `TimeoutResponse` is not a timeout.** `TerminalAdapter.await_response()` returns `TimeoutResponse` on every idle tick, on unrecognized input, and on every call after stdin EOF (`terminal_adapter.py`). Only the executor deadline ends the wait. Tick length pinned as `_HITL_TICK_SECONDS = 0.5` — `_interruptible_sleep()`'s 100 ms is too tight for a selector-per-call adapter.
20. **Clamp to the remaining `fsm.timeout` budget.** The wall-clock check runs only between states (`run()`, `executor.py:677-680`), so a 30-minute wait can overrun the loop timeout; the verdict would then be routed and immediately discarded by `_finish("timeout")`. `effective_timeout = min(effective_timeout, remaining_loop_budget)` when `fsm.timeout` is set.
21. **`route:`-table fallbacks differ from the shorthand ones.** `_route()` (`executor.py:3025-3041`) resolves an unrouted `edit`/`timeout` to `route.default` first and `no` to `route.error`. The handler's `edit`→`yes` / `timeout`→`no` fallbacks apply only when `_route()` returns `None`; AC #3 and Decision Rules now say so.
22. **`feed.py` has no branch for either event.** Added one-line rendering in `handle_event()`/`_format_event()` so `--quiet` runs and log files show the wait; the adapter's own `print()` bypasses the feed. Screen clearing is not a problem: the feed clears only on `state_enter` (`feed.py:686-692`), which precedes the adapter's print.
23. **Don't uncomment the `harness-plan-research-implement-report.yaml` block.** Step 7 said to replace it with a live state; that turns a shipped unattended loop into one that blocks up to 30 minutes per run. Keep it commented, fix `prompt:` → `action:`, add `timeout:`/`on_timeout:`. The `visibility: example` loop is the live demo.
24. **Confirmed, no change:** `stateConfig` in `fsm-loop-schema.json` has `patternProperties: ^on_` next to `additionalProperties: false`, so `on_edit`/`on_timeout` validate today. `run()` `:944` already maps `None` + `_shutdown_requested` to `_finish_for_shutdown()`. The existing `test_action_mode_returns_shell_when_not_registered` uses `"unknown_type"`, so the new `_action_mode()` branch does not conflict. Stale citations fixed: Step 1's `fsm-loop-schema.json:247` → `:436-444`; `_execute_state` returns `str | None`, not `str`; `_drain_inbound` is `:557`, not `:549`.

## Impact

- **Priority**: P2 — Highest-leverage gap from the DeerFlow comparison;
  enables a class of workflows (gated automation, mid-loop review) that
  are awkward or impossible today.
- **Effort**: Medium — new dispatch path, schema entry, validator
  changes, docs, tests. Notification surface scope determines size.
- **Risk**: Medium — unattended contexts can deadlock if `timeout:`
  semantics aren't conservative by default.
- **Breaking Change**: No — new opt-in state type.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | Currently lists zero HITL primitives; this issue adds one |
| `.claude/CLAUDE.md` § Loop Authoring | Meta-loop MR-1 rule — `human_approval` qualifies as a non-LLM evaluator |
| `docs/ARCHITECTURE.md` | Event-bus + host_runner abstraction this hooks into |

## Labels

`captured`, `fsm`, `harness`, `hitl`, `loops`

## Status

**Open** | Created: 2026-05-29 | Priority: P3

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: UPDATED (2026-06-12, epic audit)** — Integration Map line references refreshed to current `executor.py` anchors: `_execute_state` :838, `_run_action` :1053, `_action_mode` :1421, `_emit` :1642, `_interruptible_sleep` :1766 (with the learning-state dispatch at :863). These drift quickly; prefer the function-name anchors over raw numbers when implementing.

2026-06-13: Line number drift detected in executor.py. `_interruptible_sleep` is now at :1766 (was :1647/1735). `_emit` at :1642, `_execute_state` at :838, `_action_mode` at :1421 are accurate. Core architectural assumptions remain sound. At the time of this 2026-06-13 note, FEAT-1930 was an unresolved prerequisite; FEAT-1930 has since completed (2026-09-04 `/ll:refine-issue` pass unlinked `blocked_by` and confirmed the `CommunicationAdapter` protocol is now implemented — see Proposed Solution → Codebase Research Findings).

2026-06-17: Further drift — `_execute_state` :942 (was :838), `_run_action` :1157 (was :1053), `_action_mode` :1541 (was :1421), `_emit` :1762 (was :1642), `_interruptible_sleep` :1886 (was :1766). Use function-name anchors rather than line numbers when implementing.

2026-08-12 (`/ll:verify-issues`): `fsm/validation.py` no longer exists — commit `9a4977a1` split it into a `fsm/validation/` subpackage; `_validate_state_action` now lives at `fsm/validation/structural_rules.py:406` and `NON_LLM_EVALUATOR_TYPES` at `fsm/validation/_base.py:65`. All `executor.py` anchors have drifted again and were re-grepped and updated: `_execute_state` :1711, `_run_action` :2049, `_action_mode` :2706, `_emit` :3178, `_interruptible_sleep` :3378 (learning-state dispatch pattern now at :1735). The core architectural gap this issue tracks — no `human_approval` action type, no `interactive` bool on `HostCapabilities` — remains unimplemented and the issue stays valid, hence `verify_verdict: NON_VALID` (NEEDS_UPDATE) rather than a clean VALID.

- 2026-08-16: Core gap confirmed still real — no `human_approval` action_type anywhere in `fsm/executor.py`/`fsm/schema.py`. This file's line-number citations have now drifted across at least four prior verification passes; recommend future updates cite functions by name (e.g. `_execute_state`, `_run_action`) rather than line numbers, since line numbers churn too fast to stay accurate between passes. Verdict: OUTDATED.

- 2026-09-03 (`/ll:verify-issues`): Core gap confirmed still real — no `human_approval` action_type in `fsm/executor.py`/`fsm/schema.py`; issue stays valid. Line-number anchors drifted a fifth time — current: `_execute_state` :1948, `_run_action` :2312, `_action_mode` :3062, `_emit` :3550, `_interruptible_sleep` :3833. Not re-editing the scattered body citations per the 2026-08-16 recommendation above — function-name anchors are the stable reference; this note carries the current line numbers for whoever implements next.

- 2026-09-03 (`/ll:verify-issues`, re-check): Re-verified same-day — no drift since the pass above (all anchors re-confirmed identical: `_execute_state` :1948, `_run_action` :2312, `_action_mode` :3062, `_emit` :3550, `_interruptible_sleep` :3833, `StateConfig` :621, `timeout` :708, `extra_routes` :730, `HostCapabilities` :128). Decisions log has no active required rules. `ll-verify-evidence` clean. Dependency backlinks with FEAT-1930 (blocked_by/blocks) and FEAT-1680 (Scope Boundary) confirmed consistent. Verdict updated from stale `NON_VALID` to `VALID` (persisted `verify_verdict` frontmatter now matches).

- 2026-09-05 (`/ll:verify-issues`): Re-verified against the further-drifted 2026-09-05 `/ll:refine-issue` anchor pass. All current-pass anchors confirmed exact: `_execute_state` :1974, `resolve_communication_adapter` :2682, `_route` :2994, `_action_mode` :3114, `_emit` :3602, `_interruptible_sleep` :3885, `_drain_inbound` :557 (called once/iteration at `run()` :609). `_execute_state()` dispatch order, `_action_mode()` fallthrough table, and `_route()` shape all confirmed to match the cited line ranges exactly. `HitlConfig` (`config/core.py:185`) still has only `channel`, no `default_timeout` — matches this issue's proposed addition. Test anchors (`TestActionTypeMcpTool` :686, `TestContributedActionDispatch` :6782, `TestMcpToolSchema` :2062) confirmed. Core gap reconfirmed still entirely open (zero `human_approval` references in `executor.py`/`schema.py`/validation modules). Checked BUG-3387 (now Completed, fixes `_drain_inbound()` envelope-key stripping) for cross-issue impact: orthogonal — this issue only calls `_drain_inbound()` from its new tick loop and doesn't modify it, so no conflict. Only drift: `_validate_state_action` now at `structural_rules.py:408` (cited `:406`), cosmetic. Verdict stays `VALID`.

## Session Log
- third-review - 2026-09-05 - manual review against working tree `5cf210cad`; see § Third Review (items 17–24: event registration is test-gated, headless short-circuit is the normal background path, per-tick TimeoutResponse semantics, fsm.timeout clamp, route-table fallbacks, feed rendering, keep the built-in loop's block commented)
- `/ll:verify-issues` - 2026-09-05T23:38:33 - `161a68e7-1fed-48cb-8c40-28051a0cd1ac.jsonl`
- `/ll:refine-issue` - 2026-09-05T23:24:41 - `182fc9b6-abae-4d60-a265-d4ec9a1cc50e.jsonl`
- second-review - 2026-09-04 - manual review against working tree; see § Second Review (items 11–16; reverses Pre-implementation Review #9, replaces `fsm.default_timeout` fallback with `hitl.default_timeout`)
- `/ll:format-issue` - 2026-09-04T20:11:10 - `0f3f14f4-cb49-45c9-a835-dd9786829027.jsonl`
- `/ll:confidence-check` - 2026-09-04T20:07:16 - `5b74e11a-f7b6-41ec-809e-9c5477863193.jsonl`
- pre-implementation-review - 2026-09-04 - manual review; see § Pre-implementation Review (10 items, cross-linked with FEAT-3384)
- `/ll:confidence-check` - 2026-09-04T19:40:12 - `16be6d3d-b797-4958-b3aa-7f5ae8374599.jsonl`
- `/ll:reconcile-issue` - 2026-09-04T19:24:35 - `2e7a26f2-b8bf-48e7-b3ea-48fd933d6045.jsonl`
- `/ll:refine-issue` - 2026-09-04T19:12:55 - `4a1099fd-9d48-4f02-88bf-6554245a52cb.jsonl`
- `/ll:manage-issue` - 2026-09-04T07:19:43 - `edcf388a-123e-4783-8b95-eba3c9e4b3da.jsonl`
- `/ll:verify-issues` - 2026-09-03T19:30:24 - `057585fb-7ab7-4b15-b42a-aa3dc8fffb40.jsonl`
- `/ll:refine-issue` - 2026-09-03T18:12:55 - `fda4cd5c-a51b-4a98-bfeb-d76bd3f6c25a.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:55 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:23 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:08:30 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- backlog-grooming - 2026-07-03T00:00:00Z - Downgraded P2 -> P3 with parent EPIC-1929 (stalled chain; root FEAT-1930 unstarted).
- `/ll:audit-issue-conflicts` - 2026-06-25T21:24:02 - `91915c5b-d793-486c-a140-be4dd3d8ca1f.jsonl`
- `/ll:verify-issues` - 2026-06-17T00:00:00 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:verify-issues` - 2026-06-14T00:12:44 - `dcbaf608-eff5-4e7b-8a64-4d13a266c421.jsonl`
- `/ll:verify-issues` - 2026-06-09T09:21:00 - `e40557ae-4da3-4ea7-b023-bf5e57e8b61a.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:22:06 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:53 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:42 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:verify-issues` - 2026-06-01T03:08:52 - `ed2ec455-964e-4a94-92a4-e94218c08ad6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:57 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:53:49 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:refine-issue` - 2026-05-30T04:16:33 - `5e2daf50-26d6-4657-859b-a4e70fd08209.jsonl`
- `/ll:format-issue` - 2026-05-29T21:13:19 - `2b9fd7ee-19a7-49f3-85a1-70addaba91a5.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`

---

## Scope Boundary

**Resolved 2026-09-04** (pre-implementation review): FEAT-1930 shipped `AdapterResponse` (not `HumanResponse`) with a three-way `Verdict = Literal["approve", "reject", "edit"]` (`communication_adapter.py:21-34`), and this issue no longer defines an `LLEvent` subclass named `HumanResponse` (see API/Interface). Both conflicts below are closed; kept for history.

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-25): Two conflicts with FEAT-1930 require coordination at implementation time:

1. **Class name collision** — This issue's `API/Interface` defines `HumanResponse(LLEvent)` with `verdict: Literal[...]` as an event-bus type. FEAT-1930's `API/Interface` also defines a dataclass `HumanResponse` with `approved: bool` as the adapter return type. Both live in the same import namespace within `executor.py`. Resolution: FEAT-1930 must rename its adapter return type to `AdapterResponse` (or `HumanApprovalDecision`). This issue's `HumanResponse(LLEvent)` keeps its name.

2. **Binary vs. three-way verdict** — FEAT-1930's current `HumanResponse.approved: bool` is binary and cannot express the `edit` verdict that this issue's `on_edit` routing requires. FEAT-1930 must update its adapter return type to include `verdict: Literal["approve", "reject", "edit"]` before FEAT-1931 (terminal adapter) and the EventBus adapter implement `await_response()`.

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The Stop hook infrastructure introduced by FEAT-1680 (session-end sweep of stale cross-issue status refs) is an independent path from the HITL event bus path in this issue. FEAT-1680 registers a Stop hook in `hooks/hooks.json` for sweeping stale prose references; this issue adds a blocking `human_approval` FSM state that emits `LLEvent` messages via the existing event bus. The two hooks.json registrations target different events (Stop vs. in-loop FSM execution) and touch entirely different data. No coordination between FEAT-1680 and FEAT-1794 is required at implementation time.
