---
id: FEAT-3384
type: FEAT
title: EventBus HITL adapter
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T07:05:03Z'
parent: EPIC-1929
labels:
- fsm
- harness
- hitl
- extension
blocked_by: []
decision_needed: false
---

# FEAT-3384: EventBus HITL adapter

## Summary

Implement the `eventbus` `CommunicationAdapter` (FEAT-1930): a HITL channel
that emits a `human_approval_requested` event (`HUMAN_APPROVAL_REQUESTED_EVENT`,
from `little_loops.fsm.communication_adapter`) via `send_alert()`, then resumes
`await_response()` when a matching `human_response` event
(`HUMAN_RESPONSE_EVENT`) arrives for the same `alert_id`. This is the async
channel Hermes consumes and relays to whatever channel the operator is on
(text, Telegram, etc.) — replacing the cancelled bespoke PushNotification
adapter (FEAT-1932, cancelled 2026-06-20).

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

FEAT-1930's 2026-06-20 re-scope resolved Open Question #2 (event bus vs.
file-poller for the inbound callback) in favor of the event bus — that is
precisely the surface Hermes already subscribes to via the EventBus/extension
system, so no new inbound transport is needed. FEAT-1930 Pre-implementation
Review #7 (2026-09-04) scoped this adapter out to its own child issue rather
than bundling it into FEAT-1930, to keep that issue at its stated "Small"
effort.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

- `CommunicationAdapter` ABC (`scripts/little_loops/fsm/communication_adapter.py:56`) requires `send_alert()`, `await_response()`, `supports_async()`, with `cancel_alert()` a concrete no-op override point. `AdapterResponse`/`TimeoutResponse` dataclasses and `HUMAN_APPROVAL_REQUESTED_EVENT`/`HUMAN_RESPONSE_EVENT` constants already exist in the same module — this issue reuses them, it does not redefine them.
- The `await_response()` docstring (`communication_adapter.py:70-78`) defines the re-entrant polling contract explicitly: the executor calls it in short ticks, and a verdict arriving between calls must be retained and returned on the next call; a `TimeoutResponse` never invalidates the alert. `TerminalAdapter` (FEAT-1931, `fsm/adapters/terminal_adapter.py`) satisfies this via a `self._pending: dict[str, _PendingAlert]` dict that is only popped on a terminal verdict — the eventbus adapter needs equivalent per-alert pending state, populated by an `EventBus.register()` observer instead of a stdin read.
- **`EventBus.emit()`/`register()` (`scripts/little_loops/events.py`) is fully synchronous and fire-and-forget.** No existing consumer anywhere in the codebase blocks waiting for one specific correlated response event — every current `.register()` call site (`cli/loop/runner.py`, `fsm/persistence.py`, `testing.py`) streams and reacts to every matching event inline, none correlate by an id and block. This adapter is the first "emit a request, then block for a correlated reply" consumer of `EventBus` — confirmed absent by two independent research passes (analyzer + pattern-finder) searching `register()`/`emit()`/`alert_id`/`correlation_id` repo-wide. There is no existing pattern to copy for the wait mechanism itself.
- `EventBus.register(callback, filter=...)` (`events.py:81`) accepts a glob pattern matched via `fnmatch` against `event["event"]` — `filter=HUMAN_RESPONSE_EVENT` scopes a registered observer to only response events, but filtering-by-event-name is not filtering-by-`alert_id`; the observer callback itself must compare `event.get("alert_id")` against the alert the in-progress `await_response()` call is waiting on.
- `TerminalAdapter._read_line()`'s bounded-wait shape (`selectors.DefaultSelector`, one bounded read per call) doesn't transfer directly — there's no fd to select on for an in-process event bus. The transferable idiom instead is `FSMExecutor._interruptible_sleep()` (`executor.py:3864`): a 100ms-tick `while` loop bounded by a deadline. `await_response(alert_id, timeout)` can register an `EventBus` observer once (at `send_alert()` time, or lazily on first `await_response()` call) that stores an incoming matching verdict into the adapter's own pending state, then poll that state inside a tick loop bounded by `timeout` — never registering more than one observer per alert, and unregistering it (`EventBus.unregister()`, `events.py:98`) once a terminal verdict is retrieved or `cancel_alert()` withdraws it.
- `uuid.uuid4().hex` (`terminal_adapter.py:116`) is this codebase's convention for `alert_id` generation on the sibling adapter — reuse it for consistency rather than the dashed `str(uuid.uuid4())` form used elsewhere in the codebase.

### Registration path — two viable options

FEAT-3384's own Acceptance Criteria states registration should be "consistent with FEAT-1931's `TerminalAdapter` registration pattern" — **this premise no longer holds** (see the superseded marker under Acceptance Criteria below). `TerminalAdapter` is not registered via `CommunicationAdapterExtension` at all; it's wired through a hardcoded `if channel == "terminal":` fallback branch inside `FSMExecutor.resolve_communication_adapter()` (`executor.py:2661-2685`). No production code implements `provided_adapters()` anywhere in this codebase today — the `CommunicationAdapterExtension` Protocol (`extension.py:115`) exists and is wired through `wire_extensions()` (`extension.py:274-281`), but is exercised only by test fixtures.

**Option A**: Extend `resolve_communication_adapter()`'s existing hardcoded fallback with an `elif channel == "eventbus":` branch, mirroring the `"terminal"` branch's shape exactly — lazily instantiate `EventBusAdapter(self.event_bus)`, cache it in `self._contributed_adapters["eventbus"]`. Matches the only shipped precedent (`TerminalAdapter`) directly; no new extension class needed.

**Option B**: Implement a `CommunicationAdapterExtension` (e.g. an `EventBusAdapterExtension.provided_adapters() -> {"eventbus": EventBusAdapter(...)}`) and register it through the standard `wire_extensions()` path. This exercises the protocol the codebase was explicitly built to support for exactly this case (decoupling adapter registration from `executor.py`), but has zero production precedent today — every `provided_adapters()` implementation that exists is a test fixture.

> **Selected:** Option B — scored 8/12 vs. Option A's 4/12; matches the documented extension-registration contract (`CONFIGURATION.md:1585`, `API.md:6894`) and avoids the `FSMExecutor` constructor-surface change Option A requires. See Decision Rationale below.

**Recommended**: Option B — `resolve_communication_adapter()`'s hardcoded fallback reads as a zero-config bootstrap for the single built-in `terminal` channel (FEAT-1930's own scoping), not a pattern meant to grow with every new adapter; a second hardcoded `elif` starts down a path the extension protocol was purpose-built to avoid. Extension registration also gives the adapter a natural place to receive the live `EventBus` instance it needs, without `executor.py` reaching into adapter construction.

### Decision Rationale

**Selected:** Option B — implement `EventBusAdapterExtension.provided_adapters()` and register it via `wire_extensions()`, rather than a hardcoded `elif channel == "eventbus":` branch in `resolve_communication_adapter()`.

**Reasoning:** Two parallel `ll:codebase-pattern-finder` passes (one per option) found that Option A's "mirror the terminal branch" premise doesn't hold structurally: `FSMExecutor` has zero references to `event_bus`/`EventBus` anywhere in `executor.py` — the live `EventBus` instance lives on the outer `PersistentExecutor` (`persistence.py:976`), not on the class `resolve_communication_adapter()` is defined on. Making `self.event_bus` resolvable there requires threading a new constructor parameter through `FSMExecutor.__init__`, which ripples to `PersistentExecutor` and every other direct `FSMExecutor(...)` construction site — a materially larger change than "add one `elif`." Option A also directly contradicts three already-published docs that name `"eventbus"` as the worked example of a channel requiring extension registration (`docs/reference/CONFIGURATION.md:1585,1594`, `docs/reference/API.md:6894`, `scripts/little_loops/config-schema.json:1913`), and would break two existing tests (`test_communication_adapter.py:170-185`) that use `hitl_channel="eventbus"` specifically as their not-yet-registered-channel fixture.

Option B has a real gap too — `ExtensionLoader.from_config()`/`.from_entry_points()` construct extensions with a zero-arg `cls()` call (`extension.py:166,189`) before `wire_extensions()` even has `bus` in scope, so `provided_adapters()` cannot receive the live `EventBus` exactly as `EventBusAdapter(self.event_bus)` is written in this issue's own Program Design section. But that fix is localized: `wire_extensions()` already holds `bus` when it merges `_contributed_adapters` (`extension.py:274-281`), so a small addition there (e.g. an optional bus-injection hook checked before calling `provided_adapters()`) closes the gap without touching `FSMExecutor`'s constructor surface. Option B also matches 3 other shipped capability-Protocol precedents (`ActionProviderExtension`, `EvaluatorProviderExtension`, `LLHookIntentExtension`), the ratified FEAT-1930 decision record (`.ll/decisions.yaml:343-346`), and has directly reusable test scaffolding (`TestWireExtensionsAdapters`, `test_communication_adapter.py:188-228`).

**Implementation note:** Step 4 of Implementation Steps ("resolve Option A vs. B before writing this step") must additionally design the bus-injection hook into `wire_extensions()`/`EventBusAdapterExtension` — this was not previously called out and has no existing precedent to copy.

**Scoring summary:**

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 1 | 2 |
| Simplicity | 1 | 2 |
| Testability | 1 | 2 |
| Risk | 1 | 2 |
| **Total** | **4/12** | **8/12** |

**Key evidence:**
- Against the hardcoded-`elif` approach: `executor.py` has zero `event_bus`/`EventBus` references (confirmed by repo-wide grep); `TerminalAdapter()` is zero-arg-constructible, `EventBusAdapter(event_bus)` is not, under the current `FSMExecutor` shape.
- Against the hardcoded-`elif` approach: `CONFIGURATION.md:1585` — "Any other channel value must be contributed by an extension's `CommunicationAdapterExtension.provided_adapters()`" — uses `"eventbus"` as the literal example this approach would contradict.
- For the extension-registration approach: `wire_extensions()`'s `provided_adapters` merge/conflict-check path (`extension.py:274-281`) is already implemented and tested — zero changes needed there for the base registration flow.
- For the extension-registration approach: `ExtensionLoader` zero-arg construction (`extension.py:166,189`) means the `EventBus` injection this issue's own `EventBusAdapter.__init__(self, event_bus: EventBus)` signature assumes has no existing mechanism — new, scoped design work required before Step 4 can be written.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/adapters/eventbus_adapter.py` (new) — `EventBusAdapter(CommunicationAdapter)` implementing `send_alert()`/`await_response()`/`supports_async()`/`cancel_alert()`, constructed with an `EventBus` instance
- `scripts/little_loops/extension.py` — a new `EventBusAdapterExtension` class, following `CommunicationAdapterExtension`'s Protocol shape (Option B, selected — see Proposed Solution → Decision Rationale); also needs the bus-injection hook into `wire_extensions()` this decision surfaced as unspecified work (`extension.py:274-281`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:2661` — `resolve_communication_adapter()`: the resolution chokepoint either registration path ultimately feeds
- `scripts/little_loops/extension.py:274-281` — `wire_extensions()`: the registration/conflict-check path, relevant if Option B
- `scripts/little_loops/fsm/communication_adapter.py` — `CommunicationAdapter` ABC, `AdapterResponse`/`TimeoutResponse`, `HUMAN_APPROVAL_REQUESTED_EVENT`/`HUMAN_RESPONSE_EVENT` constants this adapter imports and reuses
- `scripts/little_loops/events.py:70` — `EventBus`: `register()`/`unregister()`/`emit()` — the pub/sub surface this adapter is the first request/response consumer of
- `.issues/features/P3-FEAT-1794-hitl-interrupt-fsm-state-type.md` — the emitter side (`HUMAN_APPROVAL_REQUESTED_EVENT`), currently unimplemented; this adapter's `await_response()` has nothing to correlate against in a live FSM run until FEAT-1794's executor dispatch also lands, though the adapter itself can be built and unit-tested independently by emitting/consuming test events directly against a bare `EventBus`

### Similar Patterns
- `scripts/little_loops/fsm/adapters/terminal_adapter.py` — the only existing `CommunicationAdapter` implementation; matches on per-alert pending-state bookkeeping (`_pending: dict[str, _PendingAlert]`), `alert_id = uuid.uuid4().hex` generation, and popping the pending entry only on a terminal verdict — diverges on the wait mechanism itself (`selectors` fd read vs. an `EventBus` observer + tick loop), since there is no fd to select on for an in-process bus
- `scripts/little_loops/fsm/executor.py:3864` — `_interruptible_sleep()`: the codebase's general shape for a bounded, shutdown-responsive tick loop; the closest existing precedent for the poll loop `await_response()` needs, despite not being `EventBus`-integrated itself

### Tests
- `scripts/tests/test_terminal_adapter.py` — the only adapter test file; model a new `test_eventbus_adapter.py` on its class-per-concern shape (`TestSendAlert`, `TestCancelAlert`, `TestSupportsAsync`, plus re-entrancy tests), substituting a bare `EventBus()` fixture for the `os.pipe()` fixture `TerminalAdapter`'s tests use
- `scripts/tests/test_communication_adapter.py` — `TestAwaitResponseReentrancy` (retained-verdict contract test pattern via a hand-rolled `_MockAdapter`); `TestWireExtensionsAdapters` (conflict-check test pattern, relevant if Option B) and `TestResolveCommunicationAdapter` (relevant if Option A) — model the new adapter's registration tests after whichever pair applies once the option is decided

### Documentation
- `docs/reference/CONFIGURATION.md:1581` — `### hitl` section documents `hitl.channel` selection and its default (`"terminal"`); add `"eventbus"` as a recognized value once implemented
- `docs/reference/API.md:11061-11099` — `CommunicationAdapterExtension` doc example currently illustrates a hypothetical `PushNotificationAdapter`; consider updating or adding a real `EventBusAdapter` example once Option A/B is decided

### Configuration
- `hitl.channel: "eventbus"` — selects this adapter via the existing `HitlConfig` (`scripts/little_loops/config/core.py:184-199`); no new config keys are needed, the `channel` key already exists

## Program Design

### Codebase Research Findings

### Types
- No new dataclass is required beyond what `communication_adapter.py` already defines (`AdapterResponse`, `TimeoutResponse`, `Verdict = Literal["approve", "reject", "edit"]`) — this adapter constructs and returns those existing types; it does not add new ones.
- `EventBusAdapter` needs private per-alert state analogous to `TerminalAdapter`'s `_PendingAlert` — a dict entry tracking whatever the retained-verdict / observer-lifecycle bookkeeping requires. The exact shape is an implementation detail, not a fixed contract.

### Signatures
- `EventBusAdapter.__init__(self, event_bus: EventBus) -> None` — the adapter must be constructed with (or given access to) the `EventBus` instance it emits on and observes. `CommunicationAdapter` itself defines no `__init__` (bare `ABC`), so this is net-new for the concrete subclass, mirroring `TerminalAdapter.__init__(self, stdin=None, stdout=None)`'s shape of accepting its I/O dependency by constructor injection.
- `EventBusAdapter.send_alert(self, loop_name: str, state_name: str, prompt: str, captured_context: dict) -> str` (matches ABC at `communication_adapter.py:60`) — must call `self.event_bus.emit(...)` with `event: HUMAN_APPROVAL_REQUESTED_EVENT` and a generated `alert_id` in the payload, and return that `alert_id`.
- `EventBusAdapter.await_response(self, alert_id: str, timeout: float) -> AdapterResponse | TimeoutResponse` (matches ABC at `communication_adapter.py:70`) — must satisfy the re-entrant contract documented there (see Proposed Solution → Codebase Research Findings).
- `EventBusAdapter.supports_async(self) -> bool` — returns `True` (unlike `TerminalAdapter`'s `False`) since this channel doesn't require the operator to be watching the terminal — this is the Acceptance Criteria's own stated requirement and the reason FEAT-3384 exists as EPIC-1929's async channel.
- `EventBusAdapter.cancel_alert(self, alert_id: str) -> None` — must actually withdraw pending state (unlike the ABC's no-op default), per the Acceptance Criteria and per FEAT-1930 Review #15's "a late verdict must not target a dead alert" requirement — should also unregister any `EventBus` observer registered for that alert, so it stops consuming events after cancellation.

### Call Path
`FSMExecutor._execute_human_approval_state()` (FEAT-1794, unimplemented) -> `adapter = self.resolve_communication_adapter()` -> `adapter.send_alert(loop_name, state_name, prompt, captured_context)` -> `EventBusAdapter.send_alert()` -> `self.event_bus.emit({"event": HUMAN_APPROVAL_REQUESTED_EVENT, "alert_id": alert_id, ...})` -> (an external consumer — Hermes per this issue's Summary — reacts and eventually emits `HUMAN_RESPONSE_EVENT` back onto the same bus) -> `EventBusAdapter.await_response(alert_id, timeout)` observes for a matching `HUMAN_RESPONSE_EVENT` whose payload `alert_id` matches -> returns `AdapterResponse(verdict=..., edited_text=...)` or `TimeoutResponse()` -> on cancellation, `EventBusAdapter.cancel_alert(alert_id)` withdraws the pending entry and unregisters any observer.

### Decision Rules
N/A — no new decision logic (gate/threshold/keyword classification). This issue implements a fixed ABC contract; the only open question is structural (registration path, see Proposed Solution → Option A/B), not decision-rule-shaped.

## Implementation Steps

1. Implement `EventBusAdapter(CommunicationAdapter)` in `scripts/little_loops/fsm/adapters/eventbus_adapter.py`, constructed with an `EventBus` instance; `send_alert()` emits `HUMAN_APPROVAL_REQUESTED_EVENT` with a generated `alert_id` (`uuid.uuid4().hex`, matching `TerminalAdapter`'s convention) and returns it.
2. Implement `await_response()`'s re-entrant polling contract: register (or reuse) an `EventBus` observer filtered to `HUMAN_RESPONSE_EVENT`, correlate incoming events by `alert_id`, and retain an unconsumed verdict across repeated calls and across `TimeoutResponse`s — following the tick-loop shape of `_interruptible_sleep()` (`executor.py:3864`) rather than a single full-duration wait, since `EventBus.emit()` is synchronous and delivers inline.
3. Implement `supports_async()` returning `True` and `cancel_alert()` withdrawing pending state and any registered observer for that `alert_id`.
4. Register the adapter under the `"eventbus"` channel — resolve Option A vs. B (Proposed Solution) before writing this step; both are compatible with the same `EventBusAdapter` class, only the wiring site differs.
5. Add `scripts/tests/test_eventbus_adapter.py`, modeled on `test_terminal_adapter.py`'s class-per-concern shape, covering: correct event shape on `send_alert()`, verdict resolution from a matching `human_response` event, re-entrancy across repeated `await_response()` calls (including retained-verdict-across-timeout per the ABC contract), and `cancel_alert()` withdrawal — this is the Acceptance Criteria's test bullet made concrete.
6. Verification: `python -m pytest scripts/tests/test_eventbus_adapter.py scripts/tests/test_communication_adapter.py -v` passes.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] `EventBusAdapter(CommunicationAdapter)` implements `send_alert()`
  (emits `HUMAN_APPROVAL_REQUESTED_EVENT` with `loop_name`, `state_name`,
  `prompt`, `captured_context`, and a generated `alert_id`),
  `await_response()` (re-entrant per `alert_id`, per FEAT-1930's contract —
  polls/subscribes for a matching `HUMAN_RESPONSE_EVENT`, retains an
  unconsumed verdict across `TimeoutResponse`s), and `supports_async()`
  returning `True`
- [ ] Registers via a `CommunicationAdapterExtension` (`provided_adapters()`
  returns `{"eventbus": EventBusAdapter(...)}`), consistent with FEAT-1931's
  `TerminalAdapter` registration pattern
  > ⚠ Superseded — `TerminalAdapter` is not registered via `CommunicationAdapterExtension`; it's a hardcoded fallback in `resolve_communication_adapter()`. See § Codebase Research Findings under Proposed Solution
- [ ] `cancel_alert()` override withdraws a pending alert (no-op default on
  the base class is insufficient for an async channel — a late verdict must
  not target a dead alert per FEAT-1930 Review #15)
- [ ] Tests: adapter emits the correct event shape, resolves a verdict from a
  matching `human_response` event, re-entrancy across repeated
  `await_response()` calls, `cancel_alert()` withdraws the alert

## Related Key Documentation

- `scripts/little_loops/fsm/communication_adapter.py` — `CommunicationAdapter`
  ABC, `AdapterResponse`/`TimeoutResponse`, event-name constants (FEAT-1930)
- `scripts/little_loops/extension.py` — `CommunicationAdapterExtension`
  Protocol, `wire_extensions()` registration path
- `scripts/little_loops/events.py` — `EventBus` — the pub/sub surface this
  adapter subscribes to for inbound `human_response` events

## Status

**Open** | Created: 2026-09-04 | Priority: P3


## Session Log
- `/ll:decide-issue` - 2026-09-04T19:26:43 - `2e7a26f2-b8bf-48e7-b3ea-48fd933d6045.jsonl`
- `/ll:refine-issue` - 2026-09-04T19:18:04 - `4a1099fd-9d48-4f02-88bf-6554245a52cb.jsonl`
- `/ll:manage-issue` - 2026-09-04T07:19:43 - `edcf388a-123e-4783-8b95-eba3c9e4b3da.jsonl`
