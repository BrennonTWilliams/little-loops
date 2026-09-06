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
confidence_score: 95
outcome_confidence: 67
verify_verdict: NON_VALID
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
relates_to:
- BUG-3387
reconcile_attempted: true
---

# FEAT-3384: EventBus HITL adapter

## Summary

Implement the `eventbus` `CommunicationAdapter` (FEAT-1930): a HITL channel
whose `send_alert()` records a pending alert and returns an `alert_id` (the
executor — not the adapter — then emits `human_approval_requested` on the bus,
see Pre-implementation Review #2), and whose `await_response()` resolves when
a matching `human_response` event (`HUMAN_RESPONSE_EVENT`, from
`little_loops.fsm.communication_adapter`) arrives on the `EventBus` for the
same `alert_id`. This is the async channel an out-of-process relay (Hermes,
the `--serve` dashboard, or any consumer of the socket/SSE transports)
consumes and answers — replacing the cancelled bespoke PushNotification
adapter (FEAT-1932, cancelled 2026-06-20).

## Current Behavior

`hitl.channel` accepts any string, but only `"terminal"` resolves:
`FSMExecutor.resolve_communication_adapter()` (`executor.py:2661`) seeds a
built-in `TerminalAdapter` for that channel and raises
`CommunicationAdapterNotFound` for everything else, including `"eventbus"`
(two tests use it as the canonical unregistered channel). No
`CommunicationAdapterExtension` is implemented outside test fixtures, the
`little_loops.extensions` entry-point group in `scripts/pyproject.toml:131`
is empty, and no code anywhere emits or consumes `HUMAN_RESPONSE_EVENT`.
There is also no path by which an external process can put a
`human_response` event on the in-process `EventBus`: every transport is
outbound, and the one inbound mechanism (`LocalBridgeTransport`'s
`POST /{token}/interaction` → `inbound` queue → `FSMExecutor._drain_inbound()`,
`executor.py:564-593`) re-emits every queued item as `artifact_interaction`.
Since BUG-3387 (done), `_drain_inbound()` strips the executor-owned keys
`event`/`ts`/`run_id`/`loop`/`depth` (`_INBOUND_EXECUTOR_OWNED_KEYS`,
`executor.py:102`) from the body before spreading it into `self._emit()`, so
a body with `"event": "human_response"` is wrapped as `artifact_interaction`
with its `event` key dropped — the verdict never reaches the bus under its
own name, and nothing observes it. (Before BUG-3387 the body's `event` key
overrode the envelope instead; see Second Review #5 for the history.)
FEAT-1794 (done, `837638dfe`) already drains inbound each tick of a
`human_approval` wait (`executor.py:2829`), so the only missing piece on the
inbound side is a `_drain_inbound()` branch that recognises a verdict body
and re-emits it as `human_response`.

## Expected Behavior

With `hitl.channel: "eventbus"` and no other configuration, a
`human_approval` state (FEAT-1794) sends its alert through
`EventBusAdapter`, the executor emits `human_approval_requested` with the
`alert_id` on the bus (so every transport — JSONL, Unix socket, SSE bridge —
relays it), and the FSM blocks until a `human_response` event with the same
`alert_id` is emitted on the bus. Under `ll-loop run --serve`, a
`POST /{token}/interaction` whose body is
`{"event": "human_response", "alert_id": ..., "verdict": ..., "edited_text": ...}`
is re-emitted by `_drain_inbound()` as a `human_response` bus event built
from a whitelisted payload (`alert_id`, `verdict`, `edited_text`, `reason` —
never the raw body spread over the envelope) and satisfies the wait. A
`human_approval` state inside a `loop:` sub-loop resolves the same adapter as
its parent. An unconsumed
verdict survives repeated `await_response()` calls and `TimeoutResponse`s;
`cancel_alert()` discards it. Without an inbound source the adapter still
works for in-process emitters (tests, embedded callers) and the executor logs
one warning at alert time that no inbound path is attached.

## Use Case

**Who**: An operator running an unattended loop (`ll-loop run --serve`, `nohup`, or under `ll-auto`) who is not watching the terminal.

**Context**: A `human_approval` state (FEAT-1794) fires mid-run. With the default `terminal` channel the prompt goes to a stdin nobody is reading and the state times out. With `hitl.channel: "eventbus"`, the request is relayed by whatever transport the operator already consumes (the SSE dashboard, the Unix-socket stream a Hermes relay reads, the JSONL log).

**Goal**: Answer the request from wherever the operator is — a browser tab on the `--serve` page, a chat relay, a `curl` — and have the FSM resume on the chosen route.

**Outcome**: The operator's `human_response` reaches the bus with the matching `alert_id`, the adapter hands the verdict to the executor on its next tick, and the loop continues without anyone at the terminal.

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

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

- **New pattern-finder evidence (2026-09-05 pass) supporting Option B's `BUILTIN_EXTENSIONS` design:** the closest existing precedent for a hardcoded tuple of implementation classes is `DES_VARIANTS: Final[tuple[type[DESVariant], ...]]` (`scripts/little_loops/observability/schema.py:770`), manually curated per `CONTRIBUTING.md:816`. It differs from the proposed `BUILTIN_EXTENSIONS` in function, not shape: `DES_VARIANTS` is the *sole* registration path for its type, not one of several parallel discovery sources competing for the same registration slot the way `BUILTIN_EXTENSIONS` would sit alongside `from_config()`/`from_entry_points()`. This confirms the `Final[tuple[type[X], ...]]` shape itself is idiomatic here, even though the "built-in + config + entry-point" three-source pattern has no precedent (grep-confirmed: no `BUILTIN_*` constant repo-wide holds a class registry; `BUILTIN_LOOPS_DIR` is a `Path`, unrelated).
- **`scripts/tests/test_interceptor_extension.py`** (`TestReferenceInterceptorPassthrough`) follows the identical `ExtensionLoader`/`wire_extensions` registration-test convention as `test_communication_adapter.py::TestWireExtensionsAdapters` — a third, independent confirmation of the test shape to model the new adapter's registration tests after, in addition to the two already cited.
- **Reconfirmed (independent second pass): no correlation-id blocking-wait pattern exists anywhere outside `terminal_adapter.py`/`communication_adapter.py`.** Repo-wide grep for `alert_id|correlation_id` returns only those two files. The closest additional bounded-wait shapes beyond `_interruptible_sleep()`/`UnixSocketTransport._accept_loop()`/`HandoffHandler` are `mcp_call.py:103-110` and `file_utils.py:103-111` (both `deadline = time.monotonic() + timeout` tick loops), but neither is correlation-id-based — they wait on a single pipe/file, not a multi-observer bus filtered by id. This adapter remains the first "emit + block for one correlated reply" consumer of `EventBus`.

### Registration path — two viable options

FEAT-3384's own Acceptance Criteria states registration should be "consistent with FEAT-1931's `TerminalAdapter` registration pattern" — **this premise no longer holds** (see the superseded marker under Acceptance Criteria below). `TerminalAdapter` is not registered via `CommunicationAdapterExtension` at all; it's wired through a hardcoded `if channel == "terminal":` fallback branch inside `FSMExecutor.resolve_communication_adapter()` (`executor.py:2661-2685`). No production code implements `provided_adapters()` anywhere in this codebase today — the `CommunicationAdapterExtension` Protocol (`extension.py:115`) exists and is wired through `wire_extensions()` (`extension.py:274-281`), but is exercised only by test fixtures.

**Option A**: Extend `resolve_communication_adapter()`'s existing hardcoded fallback with an `elif channel == "eventbus":` branch, mirroring the `"terminal"` branch's shape exactly — lazily instantiate `EventBusAdapter(self.event_bus)`, cache it in `self._contributed_adapters["eventbus"]`. Matches the only shipped precedent (`TerminalAdapter`) directly; no new extension class needed.

**Option B**: Implement a `CommunicationAdapterExtension` (e.g. an `EventBusAdapterExtension.provided_adapters() -> {"eventbus": EventBusAdapter(...)}`) and register it through the standard `wire_extensions()` path. This exercises the protocol the codebase was explicitly built to support for exactly this case (decoupling adapter registration from `executor.py`), but has zero production precedent today — every `provided_adapters()` implementation that exists is a test fixture.

> **Selected:** Option B — scored 8/12 vs. Option A's 4/12; matches the documented extension-registration contract (`CONFIGURATION.md:1585`, `API.md:6894`) and avoids the `FSMExecutor` constructor-surface change Option A requires. See Decision Rationale below.

**Recommended**: Option B — `resolve_communication_adapter()`'s hardcoded fallback reads as a zero-config bootstrap for the single built-in `terminal` channel (FEAT-1930's own scoping), not a pattern meant to grow with every new adapter; a second hardcoded `elif` starts down a path the extension protocol was purpose-built to avoid. Extension registration also gives the adapter a natural place to receive the live `EventBus` instance it needs, without `executor.py` reaching into adapter construction.

### Decision Rationale

**Selected:** Option B — implement `EventBusAdapterExtension.provided_adapters()` and register it via `wire_extensions()`, rather than a hardcoded `elif channel == "eventbus":` branch in `resolve_communication_adapter()`.

**Reasoning:** Two parallel `ll:codebase-pattern-finder` passes (one per option) found that Option A's "mirror the terminal branch" premise doesn't hold structurally: `FSMExecutor` has zero references to `event_bus`/`EventBus` anywhere in `executor.py` — the live `EventBus` instance lives on the outer `PersistentExecutor` (`persistence.py:976`), not on the class `resolve_communication_adapter()` is defined on. Making `self.event_bus` resolvable there requires threading a new constructor parameter through `FSMExecutor.__init__`, which ripples to `PersistentExecutor` and every other direct `FSMExecutor(...)` construction site — a materially larger change than "add one `elif`." Option A also directly contradicts the published doc that names `"eventbus"` as the worked example of a channel requiring extension registration (`docs/reference/CONFIGURATION.md:1585,1597`; the `API.md:6894` / `config-schema.json:1913` citations from the 09-04 pass no longer mention eventbus — Third Review #16), and would break two existing tests (`test_communication_adapter.py:170-185`) that use `hitl_channel="eventbus"` specifically as their not-yet-registered-channel fixture.

Option B has a real gap too — `ExtensionLoader.from_config()`/`.from_entry_points()` construct extensions with a zero-arg `cls()` call (`extension.py:166,189`) before `wire_extensions()` even has `bus` in scope, so `provided_adapters()` cannot receive the live `EventBus` exactly as `EventBusAdapter(self.event_bus)` is written in this issue's own Program Design section. But that fix is localized: `wire_extensions()` already holds `bus` when it merges `_contributed_adapters` (`extension.py:274-281`), so a small addition there (e.g. an optional bus-injection hook checked before calling `provided_adapters()`) closes the gap without touching `FSMExecutor`'s constructor surface. Option B also matches 3 other shipped capability-Protocol precedents (`ActionProviderExtension`, `EvaluatorProviderExtension`, `LLHookIntentExtension`), the ratified FEAT-1930 decision record (`.ll/decisions.yaml:343-346`), and has directly reusable test scaffolding (`TestWireExtensionsAdapters`, `test_communication_adapter.py:188-228`).

**Implementation note:** ~~Step 4 of Implementation Steps ("resolve Option A vs. B before writing this step") must additionally design the bus-injection hook~~ — designed in Pre-implementation Review #3: an optional `bind_event_bus(bus)` extension method called by `wire_extensions()` before the `provided_*` passes; `ExtensionLoader` stays zero-arg.

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
- `scripts/little_loops/fsm/adapters/eventbus_adapter.py` (new) — `EventBusAdapter(CommunicationAdapter)` implementing `send_alert()`/`await_response()`/`supports_async()`/`cancel_alert()`, plus `EventBusAdapterExtension` (the `CommunicationAdapterExtension` implementation with `bind_event_bus(bus)` and `provided_adapters()`) in the same module so `BUILTIN_EXTENSIONS` has one import target. The extension constructs the adapter **once** and returns the same instance from every `provided_adapters()` call — `wire_extensions()` calls `provided_adapters()` twice per extension (conflict-check loop at `extension.py:274-276`, then `.update()` at `:281`), so a fresh `EventBusAdapter(...)` per call would build two adapters and register only the second (Third Review #12)
- `scripts/little_loops/fsm/executor.py:2797` — `_execute_human_approval_state()`: immediately after `adapter.send_alert()` returns, `if adapter.supports_async() and self.inbound is None: logger.warning(...)` once per alert, saying the run is not under `--serve` so only in-process emitters can answer. The Decision Rules previously attributed this warning to FEAT-1794; FEAT-1794 landed (`837638dfe`) without it, so it is this issue's obligation (Third Review #10)
- `scripts/little_loops/extension.py:213-281` — `wire_extensions()`: before the `provided_actions`/`provided_evaluators`/`provided_adapters` passes, call `ext.bind_event_bus(bus)` on every extension that has it (Pre-implementation Review #3). `ExtensionLoader` is untouched — `cls()` stays zero-arg
- ~~`scripts/pyproject.toml:131` — `[project.entry-points."little_loops.extensions"]`: add `eventbus = ...`~~ — superseded (Second Review #8): discovery is a `BUILTIN_EXTENSIONS: tuple[type, ...]` constant in `extension.py`, consulted by `ExtensionLoader.load_all()` alongside config paths and entry points. No pyproject change, no reinstall step, no entry-point leakage into tests
- `scripts/little_loops/extension.py:195` — `ExtensionLoader.load_all()`: instantiate each class in `BUILTIN_EXTENSIONS` (zero-arg, same as the other two sources) and prepend them to the returned list; `from_config()`/`from_entry_points()` untouched
- `scripts/little_loops/fsm/executor.py:564-593` — `_drain_inbound()`: an inbound item with `item.get("event") == HUMAN_RESPONSE_EVENT and "alert_id" in item` — tested on the **raw** item, before the BUG-3387 `_INBOUND_EXECUTOR_OWNED_KEYS` strip at `:591` removes `event` (Third Review #11) — is re-emitted as `self._emit(HUMAN_RESPONSE_EVENT, {k: item[k] for k in ("alert_id", "verdict", "edited_text", "reason") if k in item})` (still recorded in `inbound_events`); everything else keeps today's stripped `artifact_interaction` path (Pre-implementation Review #1, Second Review #5). The whitelist is belt-and-braces now that the strip exists, but keep it: it also keeps arbitrary body keys off the `human_response` event every transport relays. FEAT-1794's tick loop calls `_drain_inbound()` each tick (`:2829`)
- `scripts/little_loops/fsm/executor.py:1205-1220` — `_execute_sub_loop()`: after constructing `child_executor`, copy `self._contributed_adapters` (and, for consistency, `_contributed_actions`/`_contributed_evaluators`/`_interceptors`) onto it so a `human_approval` state inside a sub-loop resolves the parent's `eventbus` adapter instead of raising `CommunicationAdapterNotFound` (Second Review #6). The adapter instance is shared, which is correct: it observes the one bus

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — add `EventBusAdapter` and `EventBusAdapterExtension` to the public re-export list, following the existing pattern for `CommunicationAdapterExtension`/`TerminalAdapter`-sibling symbols (import block at lines 9-19, 21-28; `__all__` listing at lines 102-111, 112-118) [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:2682` — `resolve_communication_adapter()`: the resolution chokepoint either registration path ultimately feeds
- `scripts/little_loops/extension.py:274-281` — `wire_extensions()`: the registration/conflict-check path, relevant if Option B
- `scripts/little_loops/fsm/communication_adapter.py` — `CommunicationAdapter` ABC, `AdapterResponse`/`TimeoutResponse`, `HUMAN_APPROVAL_REQUESTED_EVENT`/`HUMAN_RESPONSE_EVENT` constants this adapter imports and reuses
- `scripts/little_loops/events.py:70` — `EventBus`: `register()`/`unregister()`/`emit()` — the pub/sub surface this adapter is the first request/response consumer of
- `.issues/features/P3-FEAT-1794-hitl-interrupt-fsm-state-type.md` — the emitter side (`HUMAN_APPROVAL_REQUESTED_EVENT`), currently unimplemented; this adapter's `await_response()` has nothing to correlate against in a live FSM run until FEAT-1794's executor dispatch also lands, though the adapter itself can be built and unit-tested independently by emitting/consuming test events directly against a bare `EventBus`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/extensions/reference_interceptor.py` — the one real (non-test-fixture) shipped `LLExtension` implementation relying on the current zero-arg `cls()` construction contract; the bus-injection hook must stay additive so this class keeps constructing with no args [Agent 2 finding]
- `scripts/little_loops/cli/create_extension.py:70-95` (`_render_extension()`) — scaffold generator's doc-comment enumerates the opt-in mixin Protocols (`InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension`, `LLHookIntentExtension`, `CommunicationAdapterExtension`); `EventBusAdapterExtension` is a concrete registration, not a generic opt-in mixin, so it does not belong in this list — confirmed no change needed, called out so it isn't flagged as missed in review [Agent 1/2 finding]
- `scripts/little_loops/cli/loop/run.py:619-623`, `scripts/little_loops/cli/loop/lifecycle.py:709,736`, `scripts/little_loops/cli/sprint/run.py:794-800`, `scripts/little_loops/cli/parallel.py:313-321` — the four production `wire_extensions()` call sites; confirmed unaffected since all four already pass a live `EventBus` positionally, in scope before `wire_extensions()` runs — the bus-injection gap is strictly internal, between `wire_extensions()` and `ExtensionLoader.load_all()` not forwarding `bus` into `from_config()`/`from_entry_points()` [Agent 1/2 finding]

### Similar Patterns
- `scripts/little_loops/fsm/adapters/terminal_adapter.py` — the only existing `CommunicationAdapter` implementation; matches on per-alert pending-state bookkeeping (`_pending: dict[str, _PendingAlert]`), `alert_id = uuid.uuid4().hex` generation, and popping the pending entry only on a terminal verdict — diverges on the wait mechanism itself (`selectors` fd read vs. an `EventBus` observer + tick loop), since there is no fd to select on for an in-process bus
- `scripts/little_loops/fsm/executor.py:3864` — `_interruptible_sleep()`: the codebase's general shape for a bounded, shutdown-responsive tick loop; the closest existing precedent for the poll loop `await_response()` needs, despite not being `EventBus`-integrated itself

### Tests
- `scripts/tests/test_terminal_adapter.py` — the only adapter test file; model a new `test_eventbus_adapter.py` on its class-per-concern shape (`TestSendAlert`, `TestCancelAlert`, `TestSupportsAsync`, plus re-entrancy tests), substituting a bare `EventBus()` fixture for the `os.pipe()` fixture `TerminalAdapter`'s tests use
- `scripts/tests/test_communication_adapter.py` — `TestAwaitResponseReentrancy` (retained-verdict contract test pattern via a hand-rolled `_MockAdapter`); `TestWireExtensionsAdapters` (conflict-check test pattern, relevant if Option B) and `TestResolveCommunicationAdapter` (relevant if Option A) — model the new adapter's registration tests after whichever pair applies once the option is decided

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_extension.py::TestExtensionLoader` (lines 84-133: `test_from_config_empty`, `test_from_config_loads_valid_path`, `test_from_config_invalid_path_skips`, `test_from_config_multiple`, `test_from_entry_points_empty`, `test_load_all_combines_sources`, `test_load_all_no_config`) — the only tests exercising the real (unmocked) `cls()` construction path the bus-injection hook touches; all call `from_config`/`from_entry_points`/`load_all` with no `bus` argument, so they break with `TypeError` only if the hook adds a required positional `bus` param — keep the hook additive/optional, or update these 7 tests to pass one [Agent 2/3 finding]
- New test needed in `scripts/tests/test_extension.py` (unmocked — no `patch.object(ExtensionLoader, "load_all", ...)`) proving the bus-injection hook actually delivers the live `EventBus` into a bus-dependent extension's constructor — two independent agent passes confirmed zero existing tests exercise this mechanism; every `TestWireExtensions*`/`TestWireExtensionsAdapters` test bypasses it via mocking [Agent 2/3 finding]
- New test needed in `scripts/tests/test_communication_adapter.py`, modeled on `TestWireExtensionsAdapters.test_populates_contributed_adapters` (lines 191-207), asserting `EventBusAdapterExtension.provided_adapters()` receives the same `bus` instance passed into `wire_extensions(bus, executor=executor)` — the existing fixture there uses an adapter with no bus dependency, so it doesn't model this [Agent 3 finding]
- `scripts/tests/test_communication_adapter.py::TestResolveCommunicationAdapter` (`test_miss_raises_communication_adapter_not_found`, `test_miss_message_lists_requested_and_available_channels`, lines 149-186, both use `hitl_channel="eventbus"` as their "not-yet-registered-channel" fixture) — confirmed unaffected under the selected Option B: both build a bare `FSMExecutor` via `__new__` and never call `wire_extensions()`, so registering `EventBusAdapterExtension` in production code has no effect on them — no update needed, verified rather than assumed [Agent 3 finding]

### Documentation
- `docs/reference/CONFIGURATION.md:1581` — `### hitl` section documents `hitl.channel` selection and its default (`"terminal"`); add `"eventbus"` as a recognized value once implemented
- `docs/reference/API.md:11061-11099` — `CommunicationAdapterExtension` doc example currently illustrates a hypothetical `PushNotificationAdapter`; consider updating or adding a real `EventBusAdapter` example once Option A/B is decided

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` § `### ExtensionLoader` (~lines 10944-10971) — prose states "the class is instantiated with no arguments"; this stays TRUE under the `bind_event_bus` design (Pre-implementation Review #3) — no change needed, only add a sentence that `wire_extensions()` calls `bind_event_bus(bus)` afterwards when present [Agent 2 finding, revised]
- `docs/reference/API.md` § `### wire_extensions` Behavior bullets (~lines 11005-11006) — already stale independent of this issue (omits the `_contributed_adapters`/`provided_adapters()` merge pass added for FEAT-1930); add the `bind_event_bus` pass in the same fix [Agent 2 finding]
- `docs/claude-code/write-a-hook.md:148` — "instantiated with `cls()` (no constructor arguments)" remains true; add the optional `bind_event_bus` hook alongside it, and re-check its `extension.py:103-111` line citation for drift [Agent 2 finding, revised]
- `docs/reference/EVENT-SCHEMA.md` / `scripts/little_loops/observability/schema.py` — add the `human_response` inbound event shape (`alert_id`, `verdict`, `edited_text?`, `reason?`) and note `_drain_inbound()`'s special-casing of it. `human_approval_requested`/`human_approval_resolved` already landed with FEAT-1794. If `human_response` is added to `SCHEMA_DEFINITIONS`, the two hardcoded `58` counts in `test_generate_schemas.py` (`:17`, `:123`) must be bumped and `docs/reference/schemas/human_response.json` generated (Third Review #15)

### Configuration
- `hitl.channel: "eventbus"` — selects this adapter via the existing `HitlConfig` (`scripts/little_loops/config/core.py:184-199`); no new config keys are needed, the `channel` key already exists

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

- **Anchor refresh (2026-09-05 pass, all re-grepped current):** `resolve_communication_adapter()` now at `executor.py:2682` (was `:2661`). `_drain_inbound()` now at `executor.py:557` (was `:549`), its only production caller is `FSMExecutor.run()` at `:609`. `wire_extensions()` (`extension.py:213-297`) confirmed unchanged in shape: the `provided_adapters` merge/conflict-check pass already exists at `:274-281`; no `bind_event_bus`-style pre-pass exists anywhere in the file today — the only pre-`provided_*` work is the `on_event` bus registration at `:246-248`. `ExtensionLoader.load_all()`/`from_config()`/`from_entry_points()` (`:195/:148/:172`) confirmed still zero-arg `cls()` construction; no `BUILTIN_EXTENSIONS`-like constant exists anywhere in the repo (grep-confirmed, 0 hits outside this issue file).
- **`_execute_sub_loop()` child-executor construction now at `executor.py:1198-1212`** (was cited `:1170-1191`) — confirmed still passes only `fsm, action_runner, loops_dir, event_callback, circuit, working_dir, orchestration_config, run_model, run_effort, compression_config, inbound, capture_git_facts, loop_yaml_path`; line `1213` sets `child_executor._depth` as the only post-construction attribute copied. `_contributed_adapters`/`_contributed_actions`/`_contributed_evaluators`/`_interceptors` remain uncopied — the gap this issue's Step 5b targets is still live and at these updated lines.
- **`EventBus` (`events.py`) current signatures confirmed:** `register(self, callback: EventCallback, filter: str | list[str] | None = None) -> None` at `:81`; `unregister(self, callback: EventCallback) -> None` at `:98` (deletes by index via `enumerate(self._observers)`, identity-compares `cb is callback`, returns after first match); `emit(self, event: dict) -> None` at `:117`, iterating the live `self._observers` at `:124` (not a snapshot) before a separate transport loop at `:134-138`. No production caller of `EventBus.unregister()` exists today (grep-confirmed — all `.unregister(` hits in `scripts/little_loops/` are unrelated `selectors.BaseSelector.unregister()` calls).

_Added by `/ll:refine-issue` — 2026-09-06 — based on codebase analysis:_

- **FEAT-1794 has landed** (commit `837638dfe`, "feat(fsm): add human-in-the-loop interrupt state type"). `FSMExecutor._execute_human_approval_state()` now exists at `executor.py:2722-2881` and is no longer "unimplemented" as this issue's Call Path/Dependent Files sections state — this adapter can now be exercised end-to-end against a live `human_approval` state, not only via bare-`EventBus` unit tests. See Program Design findings below for the behavioral detail.
- **Anchor refresh (2026-09-06 pass, all re-grepped current):** `resolve_communication_adapter()` now at `executor.py:2696-2720` (was cited `:2661`/`:2682`) — logic unchanged, still special-cases only `channel == "terminal"`, raises `CommunicationAdapterNotFound` for `"eventbus"`. `_drain_inbound()` now at `executor.py:564-590` (was `:557`/`:549`) — still no `human_response` branch; BUG-3387's fix only strips envelope keys before re-emitting everything as `artifact_interaction`, confirming Implementation Step 5 is unmodified in substance at the new line. `_execute_sub_loop()`'s child `FSMExecutor(...)` construction now at `executor.py:1205-1220` (was cited `:1198-1213`); still only copies `child_executor._depth = depth` (line 1220) post-construction — the `_contributed_adapters` propagation gap (Step 5b) is still live at this new line.
- `scripts/tests/test_fsm_executor.py:896-1210` (FEAT-1794's `human_approval` tests) already call `executor._execute_human_approval_state(state, ctx)` directly against a stub adapter seeded into `_contributed_adapters` (lines 942, 1153, 1188) and assert on `human_approval_requested`/`human_approval_resolved` event payloads — a directly reusable integration-test harness for `test_eventbus_adapter.py` (or a new end-to-end test), beyond the unit-level `test_terminal_adapter.py` model already cited.
- `scripts/tests/test_fsm_executor.py:8698-8753` (`test_execute_sub_loop_signature_drift_guard`) AST-inspects only `_execute_sub_loop`'s `FSMExecutor(...)` call keyword arguments (breaking on the first match) plus `__init__`'s signature — it never inspects any statement after the constructor call. Confirmed by direct read: a post-construction copy line for Step 5b (e.g. `child_executor._contributed_adapters = self._contributed_adapters`, mirroring the existing `child_executor._depth = depth` line at `:1220`) will not trip this guard.
- `docs/reference/EVENT-SCHEMA.md:549` (`### human_approval_requested`) and `:569` (`### human_approval_resolved`), plus `docs/reference/schemas/human_approval_requested.json` / `human_approval_resolved.json`, already exist (landed with FEAT-1794) — see Documentation section findings below for the correction to this issue's own Documentation bullet.

_Added by `/ll:refine-issue` — 2026-09-06 — based on codebase analysis:_

**Correcting `### Documentation` above:** `docs/reference/EVENT-SCHEMA.md:549` (`### human_approval_requested`) and `:569` (`### human_approval_resolved`) already document both events, with schema JSON files `docs/reference/schemas/human_approval_requested.json` / `human_approval_resolved.json` already present — landed with FEAT-1794 (commit `837638dfe`). The `### Documentation` bullet describing these as something "FEAT-1794 adds" is now stale; the remaining doc gap for this issue is only the inbound `human_response` shape (`alert_id`, `verdict`, `edited_text?`, `reason?`) and `_drain_inbound()`'s special-casing of it (Implementation Step 5), which is genuinely still undocumented.

`docs/reference/API.md:6930`'s note "no `human_approval` state dispatch call site exists yet (added by FEAT-1794)" is stale now that FEAT-1794 has landed — worth fixing in the same documentation pass as this issue's other `API.md` updates, though the fix itself belongs to FEAT-1794's scope, not a new obligation this issue introduces.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-05 — based on codebase analysis:_

- **`_emit()` anchor and behavior reconfirmed (2026-09-05 pass):** now at `executor.py:3602` (was cited `:3583`); exact current body: `{"event": event, "ts": _iso_now(), "run_id": self.run_id, "loop": self.fsm.name, **data}` — `**data` still spreads last, so a `data` key sharing a name with an envelope key overrides it. This reconfirms the Decision Rules' whitelisting requirement for the `_drain_inbound()` verdict branch is still necessary at the current line.
- **`TerminalAdapter._pending`/`_PendingAlert` shape reconfirmed** (`fsm/adapters/terminal_adapter.py`): `_PendingAlert` (`:70-75`) holds `state_name: str` and `awaiting_edit_text: bool = False` — no verdict-storage field; the entry is deleted (`del self._pending[alert_id]`, `:193/212/215`) only once a terminal verdict is produced, rather than storing the verdict in place. `alert_id = uuid.uuid4().hex` confirmed at `:116`. `EventBusAdapter`'s pending-state dict needs an additional verdict-storage field this sibling shape doesn't have, since (unlike `TerminalAdapter`'s synchronous stdin read) the verdict here arrives asynchronously via the bus observer and must be retained until the next `await_response()` poll.

_Added by `/ll:refine-issue` — 2026-09-06 — based on codebase analysis:_

- **`_execute_human_approval_state()` (executor.py:2722-2881, FEAT-1794) is now real code, not a planned call path** — verified line-for-line against this issue's Call Path: `adapter.send_alert(...)` -> `self._emit(HUMAN_APPROVAL_REQUESTED_EVENT, ...)` -> tick loop (`self._drain_inbound()` then `adapter.await_response(alert_id, tick)`) -> `_resolve_verdict()` -> `self._route()` -> `self._emit("human_approval_resolved", ...)` matches exactly what this issue's `EventBusAdapter` is designed against. `adapter.cancel_alert(alert_id)` is called on both the shutdown branch (`:2814`) and the timeout branch (`:2841`) — `cancel_alert()`'s contract is already exercised on both routes by landed code, not just the one route this issue's Acceptance Criteria calls out.
- **`_HITL_TICK_SECONDS = 0.5` (executor.py:163)** is the executor's per-call cap: `tick = min(_HITL_TICK_SECONDS, monotonic_deadline - time.monotonic())` is the `timeout` argument `await_response(alert_id, tick)` receives each iteration. Load-bearing contract this section didn't yet state explicitly: `await_response()` must return within (not necessarily block for the full) `timeout` seconds — the executor's `self._shutdown_requested` check and `_drain_inbound()` call only run *between* `await_response()` calls, so an implementation blocking past its `timeout` argument delays shutdown-responsiveness and inbound-draining by the overrun. This bounds `EventBusAdapter.await_response()`'s internal poll loop from above only; nothing constrains its internal poll granularity below that — the ≤100ms internal tick this issue already plans comfortably satisfies it.
- **Exact `headless` condition (executor.py:2763-2765):** `headless = not adapter.supports_async() and (sys.stdin is None or sys.stdin.closed or not sys.stdin.isatty())`. Confirmed by short-circuit evaluation: `EventBusAdapter.supports_async() -> True` makes `not True` = `False`, so the whole expression short-circuits to `False` before any stdin check runs — the headless branch (`reason: "headless"`, zero-`elapsed_seconds` route) is categorically unreachable for this adapter, exactly as this issue's Acceptance Criteria assumes.
- **Two field-shape facts in the events `_execute_human_approval_state()` already emits** (not a defect in this issue's own design — `EventBusAdapter` receives `captured_context` directly via its own `send_alert()` parameter, not via the event — but relevant to anything downstream of this adapter that consumes the bus events): the `human_approval_requested` event's `captured_context` field is unconditionally `{}` (`:2806`) — the real dict (`{"deadline": <monotonic float>}`) is passed to `send_alert()` directly but never re-serialized onto the bus; and `human_approval_resolved`'s `verdict` field carries the adapter's raw vocabulary (`"approve"/"reject"/"edit"/"timeout"/"shutdown"`), not the routed word (`"yes"/"no"/"edit"`) `_resolve_verdict()` computes internally.
- **`resolve_communication_adapter()` (executor.py:2696-2720) reconfirmed** to have no built-in fallback for `"eventbus"` the way it does for `"terminal"` (`:2711-2716`) — `hitl.channel: "eventbus"` resolves only once something populates `self._contributed_adapters["eventbus"]`, i.e. only via `wire_extensions()` + this issue's planned `EventBusAdapterExtension.provided_adapters()`. No alternate path exists.

### Types
- No new dataclass is required beyond what `communication_adapter.py` already defines (`AdapterResponse`, `TimeoutResponse`, `Verdict = Literal["approve", "reject", "edit"]`) — this adapter constructs and returns those existing types; it does not add new ones.
- `EventBusAdapter` needs private per-alert state analogous to `TerminalAdapter`'s `_PendingAlert` — a dict entry tracking whatever the retained-verdict / observer-lifecycle bookkeeping requires. The exact shape is an implementation detail, not a fixed contract.

### Signatures
- `EventBusAdapter.__init__(self, event_bus: EventBus) -> None` — the adapter must be constructed with the `EventBus` instance it observes. `CommunicationAdapter` itself defines no `__init__` (bare `ABC`), so this is net-new for the concrete subclass, mirroring `TerminalAdapter.__init__(self, stdin=None, stdout=None)`'s shape of accepting its I/O dependency by constructor injection.
- `EventBusAdapterExtension.bind_event_bus(self, bus: EventBus) -> None` — stores the bus and constructs the single `EventBusAdapter(bus)` instance; called by `wire_extensions()` before `provided_adapters()`. `EventBusAdapterExtension.provided_adapters(self) -> dict[str, CommunicationAdapter]` — returns `{"eventbus": self._adapter}`, the same instance on every call (Third Review #12); raises a clear `RuntimeError` if `bind_event_bus` was never called (only possible if a caller bypasses `wire_extensions()`). The class deliberately defines NO `on_event` — `wire_extensions()` registers any extension with `on_event` as a bus observer (`extension.py:246-248`), which would subscribe this registration-only shim to every event on every run (Second Review #7). Nothing runtime-checks the `LLExtension` Protocol (grep confirmed), so omitting it is safe.
- `BUILTIN_EXTENSIONS: tuple[type, ...] = (EventBusAdapterExtension,)` in `extension.py` — imported lazily inside `load_all()` to avoid an `extension.py` → `fsm.adapters` → `fsm.communication_adapter` import cycle at module load (Second Review #8).
- `EventBusAdapter.send_alert(self, loop_name: str, state_name: str, prompt: str, captured_context: dict) -> str` (matches ABC at `communication_adapter.py:60`) — generates `alert_id`, creates the pending entry, registers (or reuses) the bus observer, and returns `alert_id`. It does NOT emit `human_approval_requested` — the executor is that event's sole emitter (Pre-implementation Review #2).
- `EventBusAdapter.await_response(self, alert_id: str, timeout: float) -> AdapterResponse | TimeoutResponse` (matches ABC at `communication_adapter.py:70`) — must satisfy the re-entrant contract documented there (see Proposed Solution → Codebase Research Findings).
- `EventBusAdapter.supports_async(self) -> bool` — returns `True` (unlike `TerminalAdapter`'s `False`) since this channel doesn't require the operator to be watching the terminal — this is the Acceptance Criteria's own stated requirement and the reason FEAT-3384 exists as EPIC-1929's async channel.
- `EventBusAdapter.cancel_alert(self, alert_id: str) -> None` — must actually withdraw pending state (unlike the ABC's no-op default), per the Acceptance Criteria and per FEAT-1930 Review #15's "a late verdict must not target a dead alert" requirement — should also unregister any `EventBus` observer registered for that alert, so it stops consuming events after cancellation.

### Call Path
`FSMExecutor._execute_human_approval_state()` (FEAT-1794, unimplemented) -> `adapter = self.resolve_communication_adapter()` -> `alert_id = adapter.send_alert(loop_name, state_name, prompt, captured_context)` (`EventBusAdapter` records pending state + registers its `HUMAN_RESPONSE_EVENT` observer) -> executor `_emit(HUMAN_APPROVAL_REQUESTED_EVENT, {"alert_id": alert_id, ...})` -> `PersistentExecutor._handle_event` -> `event_bus.emit()` -> every transport relays it (JSONL, Unix socket, SSE bridge) -> an external consumer answers by `POST /{token}/interaction` with `{"event": "human_response", "alert_id": ..., "verdict": ...}` (or an in-process emitter calls `bus.emit()` directly) -> executor tick loop: `self._drain_inbound()` re-emits it as a `human_response` bus event on the main thread -> `EventBusAdapter`'s observer stores the verdict in the pending entry -> `EventBusAdapter.await_response(alert_id, tick)` returns `AdapterResponse(verdict=..., edited_text=...)` (or `TimeoutResponse()` when nothing arrived this tick) -> on the timeout/shutdown routes, `EventBusAdapter.cancel_alert(alert_id)` withdraws the pending entry and unregisters the observer.

All bus emits in this path happen on the executor's main thread (`_drain_inbound()` is the only bridge from the HTTP handler thread's queue), so `EventBus`'s unlocked observer list is never mutated concurrently with `emit()`. If a future inbound transport emits from another thread, `EventBus` needs a lock first — out of scope here, but the adapter must not assume it.

Same-thread reentrancy still matters: `EventBus.emit()` iterates `self._observers` live (`events.py:124`), and `unregister()` deletes by index, so an observer that unregisters itself from inside its own callback shifts the list and skips the next observer for that event. The adapter's observer therefore only writes into `self._pending`; `unregister()` is called exclusively from `await_response()` (after a verdict is returned) and `cancel_alert()` (Second Review #9).

### Decision Rules
- `_drain_inbound()` classification: an inbound dict is a verdict iff `item.get("event") == HUMAN_RESPONSE_EVENT` and `"alert_id" in item`; it is re-emitted under that name with a whitelisted payload of `alert_id`, `verdict`, `edited_text`, `reason` (only keys present are copied). Anything else keeps today's `artifact_interaction` path. Both are still appended to `inbound_events` (the raw item). Never `self._emit(name, item)` with the raw body: `_emit()` spreads it last and a body key would overwrite the envelope's `event`/`ts`/`run_id`/`loop` (Second Review #5).
- Observer lifecycle: the observer callback only mutates `self._pending`; `EventBus.unregister()` is called from `await_response()`/`cancel_alert()`, never from inside the callback (Second Review #9).
- `EventBusAdapter` observer match: `event.get("event") == HUMAN_RESPONSE_EVENT and event.get("alert_id") in self._pending`. A `verdict` outside `{"approve", "reject", "edit"}` is logged and ignored (the alert stays pending). `edit` without `edited_text` is treated as `edit` with `""` — the executor's `on_edit` fallback handles it.
- Untrusted payload typing (Third Review #13): the values come from an arbitrary JSON POST body, so the observer checks `isinstance(alert_id, str)` **before** the `in self._pending` lookup (an unhashable `alert_id` such as a list would raise `TypeError` inside the callback — swallowed by `EventBus.emit()`'s try/except, but logged as a warning on every emit) and `isinstance(verdict, str)` before the membership check; non-`str` `edited_text`/`reason` are treated as absent (`None`). After validation, `cast(Verdict, verdict)` for mypy, since `AdapterResponse.verdict` is a `Literal`.
- No inbound path warning: **this issue's** executor change (Files to Modify, `executor.py:2797`): `_execute_human_approval_state()` logs once per alert when `adapter.supports_async()` is true and `self.inbound is None` — the run is not started under `--serve`, so only in-process emitters can answer. (Previously attributed to FEAT-1794, which landed without it — Third Review #10.)

## Implementation Steps

1. Implement `EventBusAdapter(CommunicationAdapter)` in `scripts/little_loops/fsm/adapters/eventbus_adapter.py`, constructed with an `EventBus` instance; `send_alert()` generates `alert_id` (`uuid.uuid4().hex`, matching `TerminalAdapter`'s convention), creates the pending entry, ensures one `HUMAN_RESPONSE_EVENT`-filtered observer is registered, and returns the id. It emits nothing (Pre-implementation Review #2).
2. Implement `await_response()`'s re-entrant polling contract: the observer stores a matching verdict into the pending entry (after the type checks in Decision Rules); `await_response(alert_id, timeout)` returns it immediately if present, else waits up to `timeout` re-checking the entry (the executor's own tick loop is what drains inbound between calls, so a long `timeout` here would starve it — document that callers pass short ticks). In production every verdict arrives via `_drain_inbound()` on the main thread *between* calls, so nothing can land during the wait; a single check → `time.sleep(timeout)` → re-check is equivalent to a ≤100ms tick loop and simpler. Use the tick loop only if tests emit from another thread (Third Review #17). An unconsumed verdict survives repeated calls and `TimeoutResponse`s. The entry is popped (and the observer unregistered when no alerts remain pending) only on a returned verdict or `cancel_alert()`.
3. Implement `supports_async()` returning `True` and `cancel_alert()` withdrawing pending state and unregistering the observer when no alerts remain.
4. Registration (Option B, decided): add `EventBusAdapterExtension` in the same module with `bind_event_bus(bus)` (constructs the one adapter instance) + `provided_adapters()` (returns that same instance every call — `wire_extensions()` calls it twice, Third Review #12) and no `on_event` (Second Review #7); in `wire_extensions()` add a pass before the `provided_*` merges: `for ext in extensions: if hasattr(ext, "bind_event_bus"): ext.bind_event_bus(bus)`. Discovery: add `BUILTIN_EXTENSIONS = (EventBusAdapterExtension,)` in `extension.py` (lazy import inside `load_all()`) and have `ExtensionLoader.load_all()` instantiate them first, before config paths and entry points (Second Review #8). ~~Add the `eventbus` entry point to `scripts/pyproject.toml:131` and re-run `pip install -e`~~ — superseded: no pyproject change, no reinstall.
5. `_drain_inbound()` (`executor.py:564-593`): classify on the raw item **before** the BUG-3387 key strip (the strip removes `event`, so checking afterwards can never match — Third Review #11); re-emit items with `"event" == HUMAN_RESPONSE_EVENT` and an `alert_id` under that name with the whitelisted payload (Decision Rules; Second Review #5). Add tests in `test_fsm_executor.py` next to the existing `_drain_inbound` tests: the verdict branch, and that a body carrying `run_id`/`loop`/`ts` keys cannot overwrite the envelope on the verdict path.
5b. `_execute_sub_loop()` (`executor.py:1205-1220`): after `child_executor` is built, copy `_contributed_adapters`/`_contributed_actions`/`_contributed_evaluators`/`_interceptors` from `self` (Second Review #6). Add a test asserting a child executor resolves the parent's registered adapter. Note this is a deliberate behavior change beyond HITL — contributed actions/evaluators/interceptors also become visible inside sub-loops for the first time — so cover at least one non-adapter registry in the test too (Third Review #18).
5c. `_execute_human_approval_state()` (`executor.py:2797`): after `send_alert()` returns, log one warning per alert when `adapter.supports_async() and self.inbound is None` (Third Review #10). Test with the FEAT-1794 harness in `test_fsm_executor.py:896-1210` using a stub adapter whose `supports_async()` is `True` and `inbound=None`, asserting the warning via `caplog`; and that it does not fire with `inbound` set or with `TerminalAdapter`.
6. Add `scripts/tests/test_eventbus_adapter.py`, modeled on `test_terminal_adapter.py`'s class-per-concern shape, covering: `send_alert()` returns a hex id and emits nothing; verdict resolution from a matching `human_response` bus event (approve / reject with reason / edit with text); non-matching `alert_id` and unknown `verdict` are ignored; re-entrancy across repeated `await_response()` calls including retained-verdict-across-timeout; `cancel_alert()` withdrawal and a late verdict after cancel being ignored; observer unregistered once no alerts are pending; a second observer registered after the adapter's still receives the event that resolves a verdict (guards Second Review #9); `supports_async()` is `True`.
7. Verification: `python -m pytest scripts/tests/test_eventbus_adapter.py scripts/tests/test_communication_adapter.py scripts/tests/test_extension.py scripts/tests/test_fsm_executor.py -k "inbound or adapter or extension or sub_loop" -v` passes; then an end-to-end check under `ll-loop run --serve` with a `human_approval` state (needs FEAT-1794) answered by `curl -X POST <bridge.url>interaction -d '{"event":"human_response","alert_id":"...","verdict":"approve"}'`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/__init__.py` — add `EventBusAdapter`/`EventBusAdapterExtension` to the public re-export list and `__all__`, following the existing `CommunicationAdapterExtension` pattern
- The bus-injection hook is `bind_event_bus(bus)` called from `wire_extensions()` (Pre-implementation Review #3) — `ExtensionLoader` and `cls()` construction are untouched, so `scripts/tests/test_extension.py::TestExtensionLoader`'s 7 zero-arg-construction tests pass unmodified
- Add a test in `scripts/tests/test_extension.py` (patching `load_all` like `TestWireExtensions*` do) proving `wire_extensions()` calls `bind_event_bus` with the same `bus` instance before `provided_adapters()` runs, and that an extension without `bind_event_bus` is unaffected
- Add a new test in `scripts/tests/test_communication_adapter.py`, modeled on `TestWireExtensionsAdapters.test_populates_contributed_adapters`, asserting the registered `eventbus` adapter observes the `bus` passed into `wire_extensions(bus, ...)`
- Built-in discovery replaces the entry point (Second Review #8): `load_all()` now always returns at least `EventBusAdapterExtension`. The exact tests that break (grep-confirmed, Third Review #14): `test_extension.py::TestExtensionLoader::test_load_all_no_config` (`:129-132`, asserts `== []`), `test_load_all_combines_sources` (`:121-127`, asserts `len == 1`), `TestWireExtensions::test_wire_extensions_no_extensions` (`:160-171`, asserts `== []`), and `test_wire_extensions_failed_load_doesnt_crash` (`:173-180`, asserts `== []`). Update them to expect the built-in. `test_from_config_empty` is NOT affected — it calls `from_config()`, which is untouched; entry-point patching in those tests is unaffected
- Verification-time contract check (Third Review #15): `test_generate_schemas.py:17` (`test_all_58_event_types_defined`) and `:123` (`test_creates_58_files`) hardcode the schema count. If the `human_response` shape is added to `SCHEMA_DEFINITIONS`/`DES_VARIANTS` per the Documentation section, bump both counts and regenerate `docs/reference/schemas/` (add `human_response.json`). Nothing forces the addition — `test_des_schema.py:56-66` only requires `_LOOP_EVENT_TYPES` ⊆ `DES_VARIANTS`, and `human_response` is not a loop-event type — so either do it fully or explicitly leave it out; do not half-do it
- Update `docs/reference/API.md`'s `### wire_extensions` Behavior bullets to add the `bind_event_bus` pass (and fix the pre-existing FEAT-1930 gap omitting `_contributed_adapters`); `### ExtensionLoader`'s "instantiated with no arguments" stays true; document `BUILTIN_EXTENSIONS` as the third discovery source
- `docs/reference/CONFIGURATION.md:1581` § `hitl`: document `channel: "eventbus"`, that it is built in (no `extensions:` entry needed), and that a live run needs `ll-loop run --serve` (or an in-process emitter) to receive verdicts; document the `human_response` POST body shape and that only `alert_id`/`verdict`/`edited_text`/`reason` are forwarded. FEAT-1794 adds `hitl.default_timeout` to the same section — coordinate

## Pre-implementation Review (2026-09-04)

_Manual review against the codebase before implementation, done jointly with FEAT-1794. Already folded into the sections above; this is the index._

1. **No inbound path existed for `human_response`.** The call path assumed an external consumer "emits `HUMAN_RESPONSE_EVENT` back onto the same bus", but every transport is outbound, `scripts/` has no Hermes references, and the only inbound mechanism (`--serve` → `POST /{token}/interaction` → `inbound` queue → `_drain_inbound()`, `executor.py:549`) wraps items as `artifact_interaction` and runs only between states. Resolution: `_drain_inbound()` re-emits `human_response` items under their own name, FEAT-1794's tick loop calls it each tick, and the adapter keeps its bus-observer design. All emits stay on the main thread, so the unlocked `EventBus` is safe.
2. **`human_approval_requested` was emitted twice** (executor per FEAT-1794 AC5, adapter per this issue's `send_alert()`) on the same bus, with complementary missing fields. Resolution: executor is the sole emitter, after `send_alert()` returns so it carries `alert_id`; `send_alert()` here emits nothing.
3. **Bus-injection hook designed**: optional `bind_event_bus(bus)` on the extension, called by `wire_extensions()` before the `provided_*` passes. `ExtensionLoader`/`cls()` stay zero-arg; the seven `TestExtensionLoader` tests and the "no constructor arguments" doc prose stay valid.
4. **Discovery was unspecified**: `ExtensionLoader.load_all()` only reads config `extensions:` paths and the `little_loops.extensions` entry-point group, which is empty — `hitl.channel: eventbus` alone raised `CommunicationAdapterNotFound`. Resolution: ~~ship a pyproject entry point~~ → superseded by Second Review #8 (built-in `BUILTIN_EXTENSIONS` list); the extension is always loaded but only resolved when the channel selects it.
5. Filled the `Current Behavior` / `Expected Behavior` / `Impact` template placeholders.

Order: FEAT-1794 first (against `TerminalAdapter`), then this issue; #1 and #2 are the contract both sides implement.

## Second Review (2026-09-04, post-confidence-check)

_Verified against the working tree after the confidence check scored this issue 85/100. Already folded into the sections above; this is the index. Numbering continues from the first review._

5. **`_drain_inbound()` already spoofs event names.** `_emit()` builds `{"event": name, "ts", "run_id", "loop", **data}` (`executor.py:3583`), so `self._emit("artifact_interaction", item)` lets any body key overwrite the envelope — a body with `"event": "human_response"` is re-emitted under that name today, not wrapped. Review #1's "wrapped as `artifact_interaction`" premise was wrong for such bodies, and the fix must not inherit the hole: the verdict branch builds a whitelisted payload (`alert_id`, `verdict`, `edited_text`, `reason`). The general impersonation (any POST can emit `loop_complete`, etc.) is pre-existing and is tracked as BUG-3387; not fixed here beyond the verdict path. **Superseded by `/ll:verify-issues` 2026-09-05: BUG-3387 is now Completed** — see Verification Notes below.
6. **Sub-loops don't inherit contributed adapters.** `_execute_sub_loop()` (`executor.py:1198-1213`) builds the child `FSMExecutor` with `inbound=self.inbound` but never copies `_contributed_adapters` (nor actions/evaluators/interceptors — a pre-existing gap for contributed actions too). A `human_approval` state inside a `loop:` child works with `terminal` only via the lazy fallback; `eventbus` raises `CommunicationAdapterNotFound`. Added propagation as Step 5b.
7. **The extension must not define `on_event`.** `wire_extensions()` registers every extension that has one as a bus observer (`extension.py:246-248`); a no-op `on_event` on a registration-only shim would subscribe it to every event on every `ll-loop`/`ll-sprint`/`ll-parallel` run. Nothing runtime-checks the `LLExtension` Protocol, so leaving it off is safe.
8. **Entry-point discovery replaced with a built-in list.** `importlib.metadata` entry points refresh only on reinstall, which this repo's local-editable workflow (every consuming project on this machine points at this checkout) makes easy to miss — `hitl.channel: eventbus` would raise `CommunicationAdapterNotFound` in every project until someone reruns `python -m pip install -e` (and `pip` ≠ `python` here). It also leaks into any unpatched `from_entry_points()` test. A `BUILTIN_EXTENSIONS` tuple consulted by `ExtensionLoader.load_all()` keeps Option B's registration shape with none of that. Review #4's resolution is superseded.
9. **Observer must not unregister from inside its callback.** `EventBus.emit()` iterates `_observers` live and `unregister()` deletes by index (`events.py:98-132`); self-removal mid-dispatch skips the next observer. Unregister only from `await_response()`/`cancel_alert()`; added a two-observer test to guard it.

## Third Review (2026-09-05, post-FEAT-1794 landing)

_Manual review against HEAD (`7360a0171`) after FEAT-1794 and BUG-3387 landed. Already folded into the sections above; this is the index. Numbering continues from the Second Review._

10. **The "no inbound path" warning was orphaned.** Expected Behavior and Decision Rules assigned it to FEAT-1794's handler; FEAT-1794 landed (`837638dfe`) without it — `_execute_human_approval_state()` (`executor.py:2722-2881`) has no `self.inbound is None` check. Now this issue's Step 5c / Files to Modify (`executor.py:2797`) and an Acceptance Criteria bullet.
11. **Current Behavior was still pre-BUG-3387.** It claimed a `human_response` body is "re-emitted under the spoofed name"; since BUG-3387 the body's `event`/`ts`/`run_id`/`loop`/`depth` are stripped (`executor.py:585-592`) and it is wrapped as `artifact_interaction`. Prose rewritten. Implementation consequence: Step 5's verdict classification must read `event` from the raw item before the strip, or it can never match.
12. **`provided_adapters()` runs twice per extension** in `wire_extensions()` (`extension.py:274-281`), so `{"eventbus": EventBusAdapter(self._bus)}` would construct two adapters and register only the second. Extension now builds the adapter once in `bind_event_bus()` and returns that instance.
13. **Untrusted payload types.** The POST body is arbitrary JSON; the observer must type-check `alert_id`/`verdict` before the `in self._pending` lookup (unhashable `alert_id` → `TypeError` inside the callback, swallowed by `EventBus.emit()` but logged every emit) and coerce non-`str` `edited_text`/`reason` to `None`; `cast(Verdict, ...)` for mypy.
14. **Wrong test list for the built-in extension.** The tests that break are `test_load_all_no_config`, `test_load_all_combines_sources`, `test_wire_extensions_no_extensions`, `test_wire_extensions_failed_load_doesnt_crash`; `test_from_config_empty` is unaffected.
15. **Schema count gates.** `test_generate_schemas.py` hardcodes `58` twice; adding `human_response` to `SCHEMA_DEFINITIONS` needs both bumped plus a regenerated `docs/reference/schemas/human_response.json`. Optional — not a loop-event type — so all-or-nothing.
16. **Stale citations.** `config-schema.json:1913` and `API.md:6894` no longer mention eventbus (only `CONFIGURATION.md:1597`); `_execute_sub_loop()` construction is at `:1205-1220`; `_emit()` at `:3783`; `_drain_inbound()` at `:564-593`.
17. **Internal poll loop is optional.** Every production verdict arrives via `_drain_inbound()` on the main thread between `await_response()` calls, so check → `sleep(timeout)` → re-check is equivalent to a ≤100ms tick loop; keep the loop only for other-thread test emitters.
18. **Step 5b is a behavior change beyond HITL** (contributed actions/evaluators/interceptors become visible in sub-loops for the first time); keep it, but test at least one non-adapter registry.

Verified correct in the same pass: tick loop drains inbound before each `await_response()` (`:2829-2833`); `cancel_alert()` on both shutdown (`:2814`) and timeout (`:2841`); headless short-circuits for async adapters (`:2763`); `wire_extensions()` runs before `wire_transports()` on run (`cli/loop/run.py:622`) and on resume (`lifecycle.py:736`); `_handle_interaction` already rejects non-dict bodies (`transport.py:707-709`); all inbound emits stay on the main thread. Frontmatter note: the Confidence Check Notes section still shows the 09-04 scores (85/67); the frontmatter's 95/67 is from the 09-05 run — re-run `/ll:confidence-check` after this pass rather than hand-editing either.

## Impact

- **Priority**: P3 - Async HITL is the reason EPIC-1929 exists, but the terminal channel (FEAT-1931) already unblocks attended use; this issue matters once FEAT-1794 lands and loops run unattended.
- **Effort**: Small - one new adapter module (~150 lines), a 3-line `wire_extensions()` pass, a `BUILTIN_EXTENSIONS` hook in `load_all()`, a 5-line `_drain_inbound()` branch, a 4-line sub-loop propagation, tests, docs. No executor dispatch work (that is FEAT-1794).
- **Risk**: Low - opt-in via `hitl.channel: eventbus`; the built-in extension registers an adapter that is never resolved unless selected and subscribes to nothing (no `on_event`). The `_drain_inbound()` change only affects inbound items that already declare `event: human_response` plus an `alert_id`.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `EventBusAdapter(CommunicationAdapter)` implements `send_alert()`
  (records a pending alert, registers the `HUMAN_RESPONSE_EVENT` observer,
  returns a generated `alert_id`; emits NOTHING — the executor emits
  `human_approval_requested`, Pre-implementation Review #2),
  `await_response()` (re-entrant per `alert_id`, per FEAT-1930's contract —
  resolves from a matching `HUMAN_RESPONSE_EVENT` observed on the bus, retains
  an unconsumed verdict across `TimeoutResponse`s), and `supports_async()`
  returning `True`
- [ ] Registers via `EventBusAdapterExtension` (`bind_event_bus(bus)` +
  `provided_adapters()` returning `{"eventbus": EventBusAdapter(bus)}`; no
  `on_event`, so it is never registered as a bus observer), discovered
  through `BUILTIN_EXTENSIONS` in `extension.py` (consulted by
  `ExtensionLoader.load_all()`), so `hitl.channel: "eventbus"` resolves with
  no `extensions:` config and no reinstall (Second Review #7/#8)
- [ ] `wire_extensions()` calls `bind_event_bus(bus)` on any extension that
  defines it, before the `provided_*` merge passes; extensions without it are
  unaffected and `ExtensionLoader` construction stays zero-arg
- [ ] `FSMExecutor._drain_inbound()` re-emits an inbound item whose `event`
  is `human_response` and that carries an `alert_id` under that name with a
  whitelisted payload (`alert_id`, `verdict`, `edited_text`, `reason`) — a
  body cannot overwrite the envelope's `event`/`ts`/`run_id`/`loop` on this
  path (Second Review #5) — so a `--serve` POST satisfies the wait when
  FEAT-1794's tick loop drains it
- [ ] `_execute_sub_loop()` propagates `_contributed_adapters` (and the other
  contributed registries) to the child executor, so a `human_approval` state
  inside a `loop:` child resolves `eventbus` (Second Review #6)
- [ ] The adapter's bus observer never calls `EventBus.unregister()` from
  inside the callback (Second Review #9)
- [ ] `cancel_alert()` override withdraws a pending alert and unregisters the
  observer once nothing is pending (no-op default on the base class is
  insufficient for an async channel — a late verdict must not target a dead
  alert per FEAT-1930 Review #15)
- [ ] `EventBusAdapterExtension.provided_adapters()` returns the same
  `EventBusAdapter` instance on every call (`wire_extensions()` calls it
  twice per extension — Third Review #12)
- [ ] The observer ignores (with a log line, never an exception) a
  `human_response` whose `alert_id` or `verdict` is not a `str`, and treats a
  non-`str` `edited_text`/`reason` as absent (Third Review #13)
- [ ] `_execute_human_approval_state()` logs one warning per alert when
  `adapter.supports_async()` is true and `self.inbound is None` (the run is
  not under `--serve`); no warning with `inbound` set or with the terminal
  adapter (Third Review #10)
- [ ] Tests: `send_alert()` emits nothing and returns a hex id; verdict
  resolution from a matching `human_response` event (approve / reject with
  reason / edit with text); non-matching `alert_id`, non-`str` `alert_id`
  (e.g. a list), and unknown verdicts ignored; re-entrancy across repeated
  `await_response()` calls; `cancel_alert()` withdraws the alert;
  `bind_event_bus` wiring; the `_drain_inbound()` branch including
  envelope-overwrite protection and that a verdict body still classifies
  after the BUG-3387 strip; the sub-loop propagation; `load_all()` returns
  the built-in extension (and the four `test_extension.py` tests listed in
  the Wiring Phase are updated); the no-inbound warning
- [ ] `docs/reference/CONFIGURATION.md` § `hitl` documents `eventbus`, the
  `--serve` requirement for out-of-process verdicts, and the POST body shape

## Verification Notes

_Added by `/ll:verify-issues` on 2026-09-05:_

**Verdict: NEEDS_UPDATE.** The Proposed Solution, Decision Rationale, Program
Design, Integration Map, and Implementation Steps were all re-verified against
current HEAD and remain accurate and buildable — `EventBusAdapter` still does
not exist (`scripts/little_loops/fsm/adapters/eventbus_adapter.py` absent),
no `BUILTIN_EXTENSIONS`-style constant exists anywhere in the repo, and
`_execute_sub_loop()` still does not propagate `_contributed_adapters` to the
child executor. The one defect: **BUG-3387 — cited in the "Current Behavior"
section as "independent of this feature" and still open — is now `status:
Completed`.** Its fix makes `_drain_inbound()` (`executor.py:557-586`)
unconditionally strip `event`/`ts`/`run_id`/`loop`/`depth` from every inbound
body before re-emitting it as `artifact_interaction`, so the section's claim
"a body with `\"event\": \"human_response\"` is not actually wrapped as
`artifact_interaction` today; it is re-emitted under the spoofed name" is now
false — it IS wrapped (with `event` stripped) today. This does **not**
invalidate this issue's plan: the dedicated whitelisted `human_response`
branch this issue still needs to add to `_drain_inbound()` is genuinely
absent from the BUG-3387 fix (which only stripped keys on the generic
`artifact_interaction` path), so Implementation Step 5 remains required
work. Two stale `_execute_sub_loop()` line citations (`:1170-1191`) and one
stale `_drain_inbound()` citation (`:549`) were corrected to their current
anchors (`:1198-1213` / `:557`) in this pass. Recommend a follow-up
`/ll:reconcile-issue` pass (or manual edit) to rewrite the "Current Behavior"
prose itself to describe the post-BUG-3387 baseline rather than the
pre-fix vulnerability. **Done in the Third Review (2026-09-05, #11).**

## Related Key Documentation

- `scripts/little_loops/fsm/communication_adapter.py` — `CommunicationAdapter`
  ABC, `AdapterResponse`/`TimeoutResponse`, event-name constants (FEAT-1930)
- `scripts/little_loops/extension.py` — `CommunicationAdapterExtension`
  Protocol, `wire_extensions()` registration path
- `scripts/little_loops/events.py` — `EventBus` — the pub/sub surface this
  adapter subscribes to for inbound `human_response` events

## Status

**Open** | Created: 2026-09-04 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-04_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 67/100 → MODERATE

### Concerns
- Criterion 4 (Issue Well-Specified) capped at 10/20: `template_placeholders`/`boilerplate` gap in `Current Behavior`/`Expected Behavior`/`Impact` — these are unfilled template boilerplate, not load-bearing for implementation, but worth a `format-check --fix` pass.
- Criterion C (Ambiguity) capped at 10/25: `unapplied_decision` flags `TerminalAdapter` still appearing unmarked in Proposed Solution/Program Design/Implementation Steps/Files to Modify. Most of these are legitimate pattern-reference mentions (e.g. `uuid.uuid4().hex` convention, test-shape modeling), not restatements of the rejected Option A (hardcoded `elif` branch) — only the Acceptance Criteria bullet needed (and received) a superseded marker. Verify with `/ll:decide-issue` if this should be suppressed, or leave as-is since it doesn't block implementation.

## Session Log
- `/ll:confidence-check` - 2026-09-06T01:55:54 - `c0275b19-45a2-4dc2-bddf-421eab5bb2a9.jsonl`
- third-review - 2026-09-05 - manual review against HEAD `7360a0171` after FEAT-1794/BUG-3387 landed; see § Third Review (items 10–18: no-inbound warning reassigned to this issue, Current Behavior rewritten post-BUG-3387, single adapter instance, payload typing, exact test list, schema-count gates, citation refresh)
- `/ll:refine-issue` - 2026-09-06T01:36:34 - `f817486e-5b64-46c4-9c78-9077675551e2.jsonl`
- `/ll:confidence-check` - 2026-09-05T23:51:32 - `ccea2523-fb7a-4a89-bcc0-21d2c056da68.jsonl`
- `/ll:reconcile-issue` - 2026-09-05T23:48:27 - `36a19b65-5c6b-4fe0-93ce-e7fb3332f17a.jsonl`
- `/ll:verify-issues` - 2026-09-05T23:38:33 - `161a68e7-1fed-48cb-8c40-28051a0cd1ac.jsonl`
- `/ll:refine-issue` - 2026-09-05T23:24:41 - `182fc9b6-abae-4d60-a265-d4ec9a1cc50e.jsonl`
- second-review - 2026-09-04 - manual review against working tree; see § Second Review (items 5–9; supersedes Pre-implementation Review #4's entry-point discovery, corrects #1's `artifact_interaction` premise)
- `/ll:confidence-check` - 2026-09-04T20:06:36 - `14bfc7bf-c190-4cad-96e1-061fbfdc3e5e.jsonl`
- pre-implementation-review - 2026-09-04 - manual review; see § Pre-implementation Review (5 items, cross-linked with FEAT-1794 #1/#7)
- `/ll:confidence-check` - 2026-09-04T19:46:20 - `2408c918-9fd9-4316-bbc3-17cce9e381e1.jsonl`
- `/ll:wire-issue` - 2026-09-04T19:41:11 - `16be6d3d-b797-4958-b3aa-7f5ae8374599.jsonl`
- `/ll:decide-issue` - 2026-09-04T19:26:43 - `2e7a26f2-b8bf-48e7-b3ea-48fd933d6045.jsonl`
- `/ll:refine-issue` - 2026-09-04T19:18:04 - `4a1099fd-9d48-4f02-88bf-6554245a52cb.jsonl`
- `/ll:manage-issue` - 2026-09-04T07:19:43 - `edcf388a-123e-4783-8b95-eba3c9e4b3da.jsonl`
