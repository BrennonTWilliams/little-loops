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

1. Render a prompt (the state's `prompt:` field) plus any captured
   context (e.g., `${captured.execute.output}`) to a notification
   channel — minimally the terminal/TUI, ideally also `PushNotification`
   or an IM adapter (Slack/Telegram per the IM-gateway adjacency).
2. Block FSM execution while waiting for a response.
3. Accept at least three verdicts:
   - `approve` → take `on_yes`
   - `reject` → take `on_no`
   - `edit` → take `on_edit`, with the edited text captured for the next
     state to consume via `${captured.<state>.edit}`
4. Honor a `timeout:` field — on timeout, take `on_timeout` (default to
   `on_no` if unspecified). This is critical for unattended `ll-auto`
   runs that must not deadlock if the human is away.
5. Emit a `LLEvent` so the operator can be paged via the existing event
   bus instead of polling.

Example shape (TBD on exact field names):

```yaml
check_human:
  action_type: human_approval
  prompt: >
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

- [ ] FSM runner recognizes `action_type: human_approval` and dispatches to the HITL handler
- [ ] Prompt text plus captured context (e.g., `${captured.execute.output}`) is rendered to the notification channel
- [ ] FSM execution blocks while waiting for a human response (no CPU spin, no premature advance)
- [ ] Three verdicts are accepted: `approve` (→ `on_yes`), `reject` (→ `on_no`), `edit` (→ `on_edit` with edited text captured as `${captured.<state>.edit}`)
- [ ] `timeout:` field is honored; on timeout, takes `on_timeout` (defaults to `on_no` if `on_timeout` unspecified)
- [ ] An `LLEvent` is emitted on state entry so the operator can be paged via the event bus rather than polling
- [ ] `ll-loop validate` warns when a `human_approval` state has no `timeout:` AND the loop is referenced by unattended automation (ll-auto, ll-sprint)
- [ ] Headless/non-interactive contexts (e.g., `LL_HOST_CLI=codex`) take a safe default without deadlocking

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
  prompt: "string — rendered to operator; supports ${captured.<state>.<field>} interpolation"
  timeout: 1800          # seconds; optional but warned if absent for unattended contexts
  on_yes: advance        # transition when operator approves
  on_no: execute         # transition when operator rejects
  on_edit: re_execute    # transition when operator edits; edit captured at ${captured.<state>.edit}
  on_timeout: advance    # fallback transition; defaults to on_no if unspecified
```

New LLEvent types:

```python
@dataclass
class HumanApprovalRequest(LLEvent):
    """Emitted when a human_approval state is entered."""
    loop_name: str
    state_name: str
    prompt: str
    timeout: int
    captured_context: dict

@dataclass
class HumanResponse(LLEvent):
    """Emitted when the operator responds to a human_approval request."""
    loop_name: str
    state_name: str
    verdict: Literal["approve", "reject", "edit"]
    edited_text: str | None  # populated for edit verdict
```

Validator rules: `ll-loop validate` SHALL warn (not error) when `action_type:
human_approval` is present without `timeout:` AND the loop is referenced by
unattended automation config (ll-auto, ll-sprint). This is a safety gate, not a
hard block — the loop author can suppress it with `timeout: 0` to explicitly
accept the default.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `StateConfig` dataclass: add `on_edit: str | None`, `on_timeout: str | None` fields; add `"on_edit"` and `"on_timeout"` to `_known_on_keys` set; update `to_dict()`/`from_dict()`/`get_referenced_states()`
- `scripts/little_loops/fsm/executor.py` — `_execute_state()`: add dispatch branch for `action_type == "human_approval"` (before the generic action path, following the learning-state dispatch pattern at the top of the method)
- `scripts/little_loops/fsm/executor.py` — `_action_mode()`: add `"human_approval"` to mode classification
- `scripts/little_loops/fsm/executor.py` — `_run_action()`: add branch for the new mode (emit `LLEvent`, block on external response, route by verdict)
- `scripts/little_loops/fsm/validation/structural_rules.py:406` — `_validate_state_action()`: add human_approval validations (warn if no `timeout`, require `on_yes`/`on_no`) (module split from `fsm/validation.py` in commit `9a4977a1`)
- `scripts/little_loops/fsm/validation/_base.py:65` — Add `"human_approval"` to `NON_LLM_EVALUATOR_TYPES` awareness (it IS a non-LLM evaluator per MR-1)
- `scripts/little_loops/fsm/fsm-loop-schema.json:247` — Document `human_approval` as valid `action_type`, add `on_edit`/`on_timeout` properties
- `scripts/little_loops/host_runner.py:74` — `HostCapabilities`: add `interactive: bool` flag for headless detection
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add a new "HITL phase" section
- `skills/create-loop/reference.md:415` — document `human_approval` action_type and new routing fields

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:391` — `wire_extensions()`: may register human_approval if implemented as extension
- `scripts/little_loops/extension.py:81` — `ActionProviderExtension` protocol: alternative implementation path (contributed action)
- `scripts/little_loops/extension.py:246` — `wire_extensions()` populates `_contributed_actions` dict
- `scripts/little_loops/fsm/schema.py:539` — `get_referenced_states()`: must include `on_edit` and `on_timeout` targets

### Similar Patterns
- `action_type: mcp_tool` was added across 4 files (schema + executor + validator + JSON schema) — the exact pattern to follow. See `_action_mode()` for the mode classification branch, `_run_action()` for the dispatch, `_validate_state_action()` in `validation.py` for the `params`-only-with-mcp_tool check.
- `_interruptible_sleep()` in `executor.py` — polling-with-timeout pattern for blocking while respecting shutdown signals — directly reusable for the HITL wait loop
- `_emit()` in `executor.py` — event emission pattern — emit `HUMAN_APPROVAL_REQUESTED_EVENT` (`"human_approval_requested"`, imported from `little_loops.fsm.communication_adapter` — FEAT-1930) on state entry
- `events.py:70` — `EventBus` with `register()`/`emit()`/`add_transport()`: existing pub/sub infrastructure
- `transport.py:115` — `UnixSocketTransport._accept_loop()`: socket polling with timeout — pattern for out-of-band response channel
- `schema.py:389` — `extra_routes: dict[str, str]`: catches unrecognized `on_*` keys — `on_edit` could be handled via `extra_routes` instead of a dedicated field, simplifying the schema change
- **Correction**: `PushNotification` does NOT exist in the codebase (confirmed by grep). The event bus + `WebhookTransport` (`transport.py`) is the closest notification infrastructure. v1 should use terminal output + event bus; PushNotification/IM adapter is v2 scope.

### Tests
- `scripts/tests/test_fsm_executor.py:401` — `TestActionTypeMcpTool`: model new `TestActionTypeHumanApproval` class after this pattern (mock event callback, verify approve/reject/edit/timeout routing)
- `scripts/tests/test_fsm_schema.py:1801` — `TestMcpToolSchema`: model new `TestHumanApprovalSchema` class after this (field acceptance, round-trip, validation pass/fail)
- `scripts/tests/test_fsm_validation.py` — add tests for timeout warning on `human_approval` without `timeout:`
- `scripts/tests/test_fsm_executor.py:4246` — `TestContributedActionDispatch`: pattern if implementing as extension-based action type

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (phase chain table, decision guide, troubleshooting)
- `skills/create-loop/reference.md` (FSM field reference, line ~415 for `action_type` docs)

### Configuration
- `.ll/ll-config.json` — optional `hitl.default_timeout` and `hitl.notification_channel` keys (defer if not needed for v1)
- `LL_HOST_CLI` env var — already used by `host_runner.py:751` `resolve_host()` for host detection; headless hosts (codex) should force timeout path

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Test anchor drift (2026-09-04 pass):** `TestActionTypeMcpTool` is now at `scripts/tests/test_fsm_executor.py:685` (Implementation Steps cites `:401`, now stale). `TestMcpToolSchema` is now at `scripts/tests/test_fsm_schema.py:2062` (Implementation Steps cites `:1801`, now stale). Both classes' internal test structure is unchanged — model `TestActionTypeHumanApproval` on `TestActionTypeMcpTool`'s pattern (private `_make_*_fsm()` helper, mock `_run_subprocess`/action runner, assert on `executor.run().final_state`), and `TestHumanApprovalSchema` on `TestMcpToolSchema`'s pattern (field-acceptance test + `to_dict()`/`from_dict()` round-trip test).
- `HostCapabilities` reconfirmed at `host_runner.py:128-152`; fields present: `streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`. No `interactive` field. The only `isatty()` precedent in the codebase is `sys.stdin.isatty()` at `hooks/__init__.py:194` (gates stdin-read for a hook payload, unrelated subsystem) — there is no existing `HostCapabilities`-level interactivity check to model the new flag after; it would be new territory for that dataclass.
- `action_type` has no enum constraint in `fsm-loop-schema.json` — it's a free-text string with a `description` field (`fsm-loop-schema.json:436-444`) documenting the recognized values in prose. Adding `human_approval` support means extending that description string, not adding an enum member.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

**Re-confirmed 2026-09-04 (fresh pass, all anchors re-grepped):** `_action_mode()` :3093 (was :3062), `_execute_state()` :1953 (was :1948), `_run_action()` :2317 (was :2312), `_emit()` :3581 (was :3550), `_interruptible_sleep()` :3864 (was :3833), `resolve_communication_adapter()` :2661. `StateConfig` :621, `timeout` field :708, `extra_routes` field :730 — unchanged since the prior pass. `on_yes`/`on_no` are separate declared dataclass fields (`schema.py:698-699`), not part of `extra_routes` — only unrecognized `on_*` keys (which today excludes `on_yes`/`on_no`/`on_success`/`on_failure`/etc. per `_known_on_keys`, `schema.py:896-908`) fall into `extra_routes`.
- **New architectural finding — `await_response()`'s re-entrant contract requires a net-new executor-side tick loop.** `CommunicationAdapter.await_response()`'s docstring (`communication_adapter.py:70-78`) states the intended calling contract explicitly: "the executor polls this in short ticks so shutdown stays responsive... a verdict that arrives between calls must be retained and returned on the next call." No code anywhere currently implements that tick loop — `_interruptible_sleep()` is the closest existing shape (100ms-tick `while` loop checking `self._shutdown_requested`) but nothing today calls `await_response()` from inside such a loop. The `_execute_human_approval_state()` handler this issue adds must build this loop itself, e.g. repeatedly calling `adapter.await_response(alert_id, tick_duration)` inside an `_interruptible_sleep()`-shaped `while` guarding on `state.timeout` and `self._shutdown_requested`, rather than a single call with the full timeout (which would defeat shutdown responsiveness).

### Types
- No new data type is structurally required for routing: `StateConfig.extra_routes: dict[str, str]` (`schema.py:730`) is the existing container that can carry `edit`/`timeout` verdict targets — see Proposed Solution → Codebase Research Findings for why dedicated `on_edit`/`on_timeout` fields are not required.

### Signatures
- `FSMExecutor._action_mode(self, state: StateConfig) -> str` (`executor.py:3062`) — classification chokepoint; a `human_approval` branch is one `if state.action_type == "human_approval": return "human_approval"` added ahead of the `/`-prefix heuristic fallback, following the `mcp_tool` precedent.
- `FSMExecutor._execute_state(self, state: StateConfig) -> str` (`executor.py:1948`) — per-state dispatcher. The `human_approval` branch must sit near the top of this method, alongside the existing `state.type == "learning"` check (`executor.py:1973-1974`), not inside the generic action-and-evaluate fallthrough `mcp_tool` uses — `mcp_tool`'s specialization lives entirely in `_action_mode`/`_run_action`/`_evaluate` because it never blocks mid-state, but `human_approval` does.
- `FSMExecutor._interruptible_sleep(self, duration: float, on_heartbeat: Callable[[float], None] | None = None) -> float` (`executor.py:3833`) — existing blocking-wait-with-shutdown-respect primitive, already reused by two unrelated call sites (`_check_host_guard`, `_maybe_wait_for_circuit`).
- `FSMExecutor._emit(self, event: str, data: dict[str, Any]) -> None` (`executor.py:3550`) — event emission; takes a flat event-name string and a payload dict, not an `LLEvent` subclass (see Proposed Solution → Codebase Research Findings: `LLEvent` is never subclassed in this codebase).

### Call Path
`FSMExecutor.run()` -> `_execute_state()` [new `human_approval` branch beside the `state.type == "learning"` branch] -> new `_execute_human_approval_state()` -> `_emit(HUMAN_APPROVAL_REQUESTED_EVENT, ...)` -> `adapter = self.resolve_communication_adapter()` -> `adapter.send_alert(...)` -> blocking wait shaped like `_interruptible_sleep()`, polling `adapter.await_response(alert_id, timeout)` (FEAT-1930, implemented — `CommunicationAdapter`/`resolve_communication_adapter()` now exist in `little_loops.fsm.communication_adapter`/`executor.py`; this issue no longer needs `blocked_by: FEAT-1930`) -> on the timeout route, call `adapter.cancel_alert(alert_id)` (FEAT-1930 Pre-implementation Review #15) -> route via `state.on_yes` / `state.on_no` / `state.extra_routes["edit"]` / `state.extra_routes["timeout"]`.

### Decision Rules
- Gate: `ll-loop validate` warning when a `human_approval` state has no `timeout:`.
- Exact input: `state.action_type == "human_approval" and state.timeout is None` — reuses the existing `timeout: int | None` field on `StateConfig` (`schema.py:708`); no new field needed for the duration itself.
- Scoping: unconditional. Prior research (Proposed Solution → Codebase Research Findings, existing) found `ll-auto`/`ll-sprint` do not directly load FSM loop YAMLs, so a "referenced by unattended automation" cross-reference check is infeasible for v1 — warn whenever the field is absent, regardless of caller context.
- Escape hatch: WARNING, not ERROR — loop author suppresses by setting `timeout: 0` to explicitly accept the default fallback (`on_timeout`, defaulting to `on_no`) per the existing Validator rules in `## API/Interface`.

## Implementation Steps

1. **Schema** (`fsm/schema.py:309`): Add `on_edit: str | None` and `on_timeout: str | None` to `StateConfig`; add `"on_edit"` and `"on_timeout"` to `_known_on_keys` (~line 485); update `to_dict()`/`from_dict()`/`get_referenced_states()`. Also update `fsm-loop-schema.json:247` to document `human_approval` as valid `action_type`.
   - Alternative: use `extra_routes` (`schema.py:389`) for `on_edit`/`on_timeout` to avoid schema changes — unrecognized `on_*` keys are already captured there.
2. **Validator** (`fsm/validation/structural_rules.py:406`): In `_validate_state_action()`, add: require `on_yes`/`on_no` when `action_type == "human_approval"`; WARNING if no `timeout` is set; add `"human_approval"` to `NON_LLM_EVALUATOR_TYPES` awareness in `fsm/validation/_base.py:65` (it IS a non-LLM evaluator per MR-1).
3. **Executor dispatch** (`fsm/executor.py`): Add `"human_approval"` to `_action_mode()` (before the heuristic fallthrough). In `_execute_state()`, add a dispatch branch before the generic action path — follow the learning-state dispatch pattern at the top of the method: `if state.action_type == "human_approval": return self._execute_human_approval_state(state, ctx)`.
4. **HITL handler** (new method `_execute_human_approval_state()` in `fsm/executor.py`): Render prompt with `${captured.*}` interpolation, resolve the active `CommunicationAdapter` from config + extension registry (FEAT-1930), call `adapter.send_alert()` to deliver the prompt, call `adapter.await_response()` to block for verdict (using `_interruptible_sleep()`-style polling — see `_interruptible_sleep()` in `executor.py`), route based on verdict/timeout. The executor never imports a specific adapter — it only calls the protocol methods.
5. **Host capability** (`host_runner.py:74`): Add `interactive: bool` flag to `HostCapabilities`. Set based on `sys.stdin.isatty()` (existing pattern in `hooks/__init__.py:111`). In the HITL handler, if not interactive, short-circuit to `on_timeout`/`on_no`.
6. **Tests**: Add `TestActionTypeHumanApproval` in `test_fsm_executor.py` (model after `TestActionTypeMcpTool` at line 401) — mock event callback, verify approve/reject/edit/timeout routing. Add `TestHumanApprovalSchema` in `test_fsm_schema.py` (model after `TestMcpToolSchema` at line 1801). Add timeout-warning test in `test_fsm_validation.py`.
   > ⚠ Superseded — `test_fsm_validation.py` no longer exists; timeout-warning test belongs in `test_fsm_validation_structural.py` (companion to `structural_rules.py`); see § Codebase Research Findings under Integration Map
7. **Docs**: Add HITL phase section to `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`; document `human_approval` action_type and new routing fields in `skills/create-loop/reference.md:415`; add example loop under `loops/examples/`.
   > ⚠ Superseded — `loops/examples/` doesn't exist yet, must be created; see § Codebase Research Findings under Proposed Solution
8. **EPIC-1929 siblings** (separate issues, not in this FEAT's scope): Terminal adapter (FEAT-1931), PushNotification adapter (FEAT-1932), future adapters (Slack, Telegram, webhook).

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

## Session Log
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

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-25): Two conflicts with FEAT-1930 require coordination at implementation time:

1. **Class name collision** — This issue's `API/Interface` defines `HumanResponse(LLEvent)` with `verdict: Literal[...]` as an event-bus type. FEAT-1930's `API/Interface` also defines a dataclass `HumanResponse` with `approved: bool` as the adapter return type. Both live in the same import namespace within `executor.py`. Resolution: FEAT-1930 must rename its adapter return type to `AdapterResponse` (or `HumanApprovalDecision`). This issue's `HumanResponse(LLEvent)` keeps its name.

2. **Binary vs. three-way verdict** — FEAT-1930's current `HumanResponse.approved: bool` is binary and cannot express the `edit` verdict that this issue's `on_edit` routing requires. FEAT-1930 must update its adapter return type to include `verdict: Literal["approve", "reject", "edit"]` before FEAT-1931 (terminal adapter) and the EventBus adapter implement `await_response()`.

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The Stop hook infrastructure introduced by FEAT-1680 (session-end sweep of stale cross-issue status refs) is an independent path from the HITL event bus path in this issue. FEAT-1680 registers a Stop hook in `hooks/hooks.json` for sweeping stale prose references; this issue adds a blocking `human_approval` FSM state that emits `LLEvent` messages via the existing event bus. The two hooks.json registrations target different events (Stop vs. in-loop FSM execution) and touch entirely different data. No coordination between FEAT-1680 and FEAT-1794 is required at implementation time.
