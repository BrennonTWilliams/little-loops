---
id: FEAT-1930
title: Communication adapter protocol for async HITL channels
type: FEAT
priority: P3
captured_at: '2026-06-04T00:00:00Z'
completed_at: '2026-09-04T07:19:17Z'
discovered_date: 2026-06-04
discovered_by: scope-epic
status: done
parent: EPIC-1929
relates_to:
- FEAT-1794
- FEAT-1931
- EPIC-2196
- FEAT-3323
blocks:
- FEAT-2102
- FEAT-1794
- FEAT-1931
- FEAT-3384
labels:
- fsm
- harness
- hitl
- extension
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 77
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 18
---

# FEAT-1930: Communication adapter protocol for async HITL channels

## Summary

Define a `CommunicationAdapter` abstract protocol that decouples the FSM
`human_approval` state from transport-specific I/O. The protocol provides two
operations — `send_alert()` for outbound delivery and `await_response()` for
inbound verdict collection — and registers through the extension system so
adapters are discoverable and config-swappable.

This is the **foundational child** of EPIC-1929. FEAT-1794 (FSM state) and
FEAT-1931 (terminal adapter) depend on this interface being stabilized first.

## Re-scope (2026-06-20) — two adapters, EventBus not bespoke push

The Hermes integration (EPIC-2196, `done`) changed what this protocol needs to
abstract over. The original framing — a rich multi-transport protocol spanning
terminal, push, Slack, Telegram, SMS, webhook, with little-loops owning each
transport — is obsolete: **Hermes already reaches the operator on every one of
those channels** (text, Telegram, etc.) and consumes little-loops events via its
webhook and the EventBus/extension surface.

The protocol's surface (`send_alert()` / `await_response()` / `supports_async()`)
and the `CommunicationAdapterExtension` registration decision (Option B, below)
are **unchanged**. What shrinks is the set of adapters this protocol must prove
itself against:

- **`terminal`** — dev/debug/fallback channel (FEAT-1931). Unchanged.
- **`eventbus`** — emit a `human_approval_requested` event; resume when a
  matching `human_response` event arrives. This is the async channel Hermes
  consumes and relays to whatever channel the operator is on. **Replaces the
  cancelled bespoke PushNotification adapter (FEAT-1932).**

This also **resolves Open Question #2** (event bus vs. file-poller for the inbound
callback) in favor of the **event bus** — that is precisely the surface Hermes
already subscribes to, so no new inbound transport is needed. Designing the
protocol for these two adapters (sync terminal + async eventbus) still proves the
abstraction; third-party adapters (a direct Slack adapter, a custom webhook) can
be added later against the same protocol without touching `executor.py`.

> Downstream: FEAT-1932 **cancelled**; FEAT-2102 (adapter-swap test) **deferred**
> until the `eventbus` adapter lands, then retargeted to terminal↔eventbus.

## Relationship to FEAT-3323

FEAT-3323's localhost SSE bridge would relay this issue's `human_approval_requested`
and `human_response` EventBus events read-only, like any other event — a
browser-side verdict adapter letting an operator respond to a HITL prompt from
that page would be a separate, future FEAT layered on both issues, not part of
either's current scope.

## Pre-implementation Review (2026-09-04)

Review pass before implementation. Decisions below are authoritative where they
conflict with older prose in this file; sibling issues still need matching edits.

1. **Adapter return type finalized** — `HumanResponse` is renamed
   `AdapterResponse` and carries `verdict: Literal["approve", "reject", "edit"]`
   (plus `edited_text`) instead of `approved: bool`. This applies the resolution
   recorded in `## Scope Boundary` since 2026-06-25. FEAT-1794's event-bus type
   `HumanResponse(LLEvent)` keeps its name. See `## API/Interface`.
2. **`provided_adapters()` returns `dict[str, CommunicationAdapter]`**, keyed by
   channel name, not `list[type[CommunicationAdapter]]`. The executor registry is
   keyed by the `hitl.channel` value, and a list of classes carries no key. This
   also matches all four existing capability Protocols and lets the
   `wire_extensions()` conflict guard be copied verbatim.
3. **`await_response(alert_id, timeout)` keeps `alert_id`.** The eventbus adapter
   needs it to correlate the inbound `human_response` event. **FEAT-1931 drift:**
   its `## API/Interface` shows `await_response(self, timeout)` and must be
   updated to include `alert_id`.
4. **Canonical event names** — `human_approval_requested` and `human_response`,
   exported as module-level string constants from `communication_adapter.py`
   (`HUMAN_APPROVAL_REQUESTED_EVENT`, `HUMAN_RESPONSE_EVENT`) following the
   `RATE_LIMIT_WAITING_EVENT` convention. **FEAT-1794 drift:** it emits
   `human_approval_request` (no `-ed`) at its lines ~200, ~285, ~319 and must be
   corrected to import these constants. FEAT-3323 already uses the canonical names.
5. **AC "validate warns on non-interactive host" moved to FEAT-1794.**
   `ll-loop validate` cannot know a loop uses HITL until the `human_approval`
   state type exists (FEAT-1794), "unset" is not a failure condition because it
   defaults to `terminal`, and `HostCapabilities` has no interactivity field to
   key on. The correct check is "resolved adapter reports `supports_async() ==
   False` while the host is non-interactive", which belongs where the state is
   introduced. The `validate_fsm` parameter threading, `CATEGORY_PATTERNS`
   ratchet entry, and `CLI.md` rule bullet move with it.
6. **Executor scope here is a resolver, not dispatch.** This issue adds
   `FSMExecutor.resolve_communication_adapter() -> CommunicationAdapter` that
   reads `hitl.channel` (default `"terminal"`) and looks up
   `_contributed_adapters`. On a miss it raises `CommunicationAdapterNotFound`
   (new, in `communication_adapter.py`) naming the requested channel and the
   registered channel names — never a bare `KeyError`. It has **no call site**
   until FEAT-1794 adds the `human_approval` branch. Because FEAT-1931 ships
   `TerminalAdapter`, the default channel resolves to nothing in this issue's
   own tree; that is expected and covered by the miss-path test.
7. **Eventbus adapter is not implemented here.** The 2026-06-20 re-scope says it
   is "folded into FEAT-1930", but nothing in the ACs builds it and ENH-2249
   flagged it as untracked. Decision: scope it as its own child of EPIC-1929
   (`FEAT: EventBus HITL adapter`), `blocked_by: [FEAT-1930]`, and add it to this
   issue's `blocks` when created. This keeps this issue at its stated "Small"
   effort. FEAT-2102's "deferred until eventbus lands" retargets to that issue.
8. **`send_alert()` no longer takes `timeout`.** The wait budget belongs to
   `await_response()`. Adapters that want to show the deadline to the operator
   receive it via `await_response()`'s own argument before blocking, or render
   it from `captured_context`.
9. **`HitlConfig` lives in `config/core.py`**, so the BUG-3192
   `_discover_dataclasses()` guard sees it without extending the walker.
10. Minor: Impact priority corrected P2 → P3 to match frontmatter;
    `TimeoutResponse.timed_out` kept as a constant-`True` discriminator field and
    documented as such.

_Second pass, 2026-09-04 (post-confidence-check review):_

11. **Resolver reads config via `_get_br_config()`, not `self._config`.**
    `FSMExecutor` has no `_config` attribute. The existing accessor is the
    memoized `_get_br_config()` (`executor.py:2643`, BUG-3009), which resolves
    `BRConfig(self.working_dir or Path.cwd())` once per executor. The resolver
    must call `self._get_br_config().hitl.channel`. Tests therefore either
    construct the executor with `working_dir=tmp_path` containing a
    `.ll/ll-config.json`, or pre-seed `executor._br_config` with a `BRConfig`
    built from `tmp_path` — state which in each test.
12. **`await_response()` is re-entrant per `alert_id`.** FEAT-1794 polls
    `await_response()` in `_interruptible_sleep`-style ticks (`executor.py:3833`)
    so `request_shutdown()` / Ctrl-C stay responsive. The protocol therefore
    guarantees: `await_response(alert_id, timeout)` may be called repeatedly for
    the same `alert_id` with short timeouts; an adapter must retain an
    unconsumed verdict that arrives between calls and return it on the next
    call; a `TimeoutResponse` from one call does not invalidate the alert.
    This goes in the method docstring and in the contract tests (mock adapter
    returns `TimeoutResponse` twice, then the verdict).
13. **`CommunicationAdapter` is an `abc.ABC` with `@abstractmethod`** on all
    three methods, not a plain class with `...` bodies. A subclass missing
    `supports_async()` must fail at instantiation, not at first call, and the
    ABC gives `isinstance()` for the resolver tests (the `TestResolveProvider`
    shape).
14. **Miss-exception message follows the 3-precedent template.** Resolving the
    "contested convention" note in `## Program Design`: the message is
    `f"Communication adapter {channel!r} is not registered. Available: {sorted(...)}."`
    matching `resolve_host` / `_instantiate` / `resolve_emitter`, so tests use
    `pytest.raises(CommunicationAdapterNotFound, match="not registered")` like
    `TestResolveProvider`/`TestResolveEmitter`. The `LookupError` base stays.
15. **Optional `cancel_alert(alert_id) -> None` with a no-op default** (concrete
    method on the ABC, not abstract). On timeout, an async adapter would
    otherwise leave a live prompt on the operator's channel whose late verdict
    targets a dead alert. The no-op default leaves FEAT-1931 unaffected;
    FEAT-1794 calls it on the timeout route.
16. **Re-export the two event constants from `fsm/__init__.py`** for parity with
    `RATE_LIMIT_WAITING_EVENT` (`fsm/__init__.py:102,182`), in addition to the
    top-level `little_loops/__init__.py` export. Earlier prose saying
    `fsm/__init__.py` needs no change applied only to the Protocol/ABC types,
    which are still not re-exported there.
17. **EPIC-1929 is stale and is updated in step 9** alongside creating the
    eventbus child: its children list and dependency tree still carry the
    cancelled FEAT-1932 push adapter and no eventbus child. The
    `CONFIGURATION.md` `### hitl` section also gets one sentence disambiguating
    `hitl.channel` from the unrelated `hitl-md`/`hitl-compare` loop family.

## Current Behavior

The FSM executor currently has no abstraction layer for human-in-the-loop (HITL)
communication channels. Any `human_approval` state would need transport-specific
I/O hardcoded directly in `executor.py` — there is no adapter protocol, no
extension-based discovery, and no config-driven channel selection.

## Expected Behavior

1. A `CommunicationAdapter` abstract base class (`abc.ABC`) defining:
   - `send_alert(loop_name, state_name, prompt, captured_context) → alert_id`
   - `await_response(alert_id, timeout) → AdapterResponse | TimeoutResponse`,
     re-entrant per `alert_id` (Pre-implementation Review #12)
   - `supports_async() → bool` — whether the channel can reach an operator who
     isn't watching the terminal
   - `cancel_alert(alert_id) → None`, concrete no-op default (Review #15)
2. Adapters register via the extension system through a new
   `CommunicationAdapterExtension` Protocol (decided 2026-06-12 — see
   Decision Rationale in Proposed Solution) whose `provided_adapters()` returns
   `dict[str, CommunicationAdapter]` keyed by channel name.
3. Config-driven channel selection: `.ll/ll-config.json` key `hitl.channel`
   selects the active adapter (default: `terminal`).
4. The FSM executor exposes `resolve_communication_adapter()` which reads
   `hitl.channel` via the memoized `_get_br_config()` and looks it up in the
   extension registry — it never imports a specific adapter directly. Dispatch (calling `send_alert` /
   `await_response` from a `human_approval` state) is FEAT-1794's scope.
5. Canonical event-name constants `HUMAN_APPROVAL_REQUESTED_EVENT =
   "human_approval_requested"` and `HUMAN_RESPONSE_EVENT = "human_response"`
   are exported for FEAT-1794, the eventbus adapter, and FEAT-3323 to share.

## Motivation

Without this protocol, the `human_approval` state type would hardcode transport
logic in `executor.py` — terminal `input()` today, ripped out and replaced with
push tomorrow, Slack the day after. An adapter protocol is a one-time abstraction
cost that pays back every time a new channel is added.

## Use Case

**Who**: A platform developer wiring ll's human-in-the-loop workflow to an async
relay (the EventBus adapter consumed by Hermes), or adding a further channel
later.

**Context**: An FSM loop reaches a `human_approval` state and needs operator input
before proceeding. The operator might be watching the terminal, or might be away
and reachable only through Hermes (text, Telegram, etc.), which relays the
EventBus-published prompt and feeds the verdict back.

**Goal**: The developer implements a `CommunicationAdapter` subclass for their
channel without modifying `executor.py`, `extension.py`, or any existing adapter.

**Outcome**: Setting `hitl.channel: "eventbus"` in `.ll/ll-config.json` routes all
`human_approval` prompts through the EventBus adapter (relayed by Hermes) — no
code changes to the FSM runner. Switching back to `hitl.channel: "terminal"` for
local dev is the same one-line config change.

## Acceptance Criteria

- [x] `CommunicationAdapter` is an `abc.ABC` with abstract `send_alert()`,
  `await_response()`, and `supports_async()` plus a concrete no-op
  `cancel_alert()`; instantiating a subclass missing an abstract method raises
  `TypeError`; `AdapterResponse` carries
  `verdict: Literal["approve", "reject", "edit"]` (no `approved: bool`)
- [x] `await_response()` docstring states the re-entrancy contract (repeat
  calls for one `alert_id`; unconsumed verdict retained across a
  `TimeoutResponse`); contract test proves it with the mock adapter
- [x] `HUMAN_APPROVAL_REQUESTED_EVENT` / `HUMAN_RESPONSE_EVENT` string constants
  exported from `communication_adapter.py`
- [x] Extension registration path established (adapter discovery via
  `wire_extensions()`; `provided_adapters()` returns
  `dict[str, CommunicationAdapter]`; duplicate channel name raises `ValueError`
  like actions/evaluators)
- [x] Config schema: `hitl.channel` in `.ll/ll-config.json` selects active
  adapter; falls back to `terminal` if unset; `HitlConfig` in `config/core.py`
- [x] `FSMExecutor.resolve_communication_adapter()` resolves via
  `_get_br_config().hitl.channel` + extension registry, not hardcoded import;
  a miss raises `CommunicationAdapterNotFound` whose message matches
  `"not registered"` and lists requested and available channels
- [ ] ~~`ll-loop validate` warns when `hitl.channel` is unset and host is
  non-interactive~~ — moved to FEAT-1794 (see Pre-implementation Review #5)
- [x] Tests: mock adapter registered through a `CommunicationAdapterExtension`,
  resolver returns it for its channel name, miss path raises the named
  exception, conflict path raises `ValueError`
- [x] Follow-up issue `FEAT: EventBus HITL adapter` created under EPIC-1929
  with `blocked_by: [FEAT-1930]` and added to this issue's `blocks`
  (Pre-implementation Review #7); EPIC-1929's children list and dependency
  tree updated to drop FEAT-1932 and add the new child (Review #17)
- [x] `HUMAN_APPROVAL_REQUESTED_EVENT` / `HUMAN_RESPONSE_EVENT` also
  re-exported from `fsm/__init__.py` (Review #16)

## Proposed Solution

Model after the existing transport abstraction (`transport.py`:
`UnixSocketTransport`, `WebhookTransport`) and the extension protocol
(`extension.py:81` `ActionProviderExtension`).

Key design decision: extend `ActionProviderExtension` (adds
`provided_adapters()`) vs. create a new `CommunicationAdapterExtension`.

> **Selected:** Option B — new `CommunicationAdapterExtension` Protocol class — matches the codebase's one-Protocol-per-capability convention (4 existing precedents), and Option A's claimed `_run_action()` dispatch reuse does not hold (adapter resolution is `hitl.channel` config-key-driven, not `action_type`-driven).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-12.

**Selected**: Option B — create a new `CommunicationAdapterExtension` Protocol class with a single `provided_adapters()` method, detected via `hasattr()` in `wire_extensions()`.

**Reasoning**: `extension.py` already contains four separate capability Protocols (`InterceptorExtension` :61, `ActionProviderExtension` :81, `EvaluatorProviderExtension` :92, `LLHookIntentExtension` :104), each with a narrow typed return and its own `hasattr()` gate in `wire_extensions()` (:246–273) — and the most recently added capability (`LLHookIntentExtension`) was created as a new Protocol rather than appended to an existing one. Option A would create the codebase's first fat interface and force `ActionProviderExtension` to carry two methods returning unrelated types (`dict[str, ActionRunner]` vs adapters); its core rationale — reusing the contributed-action dispatch in `_run_action()` — does not survive inspection, because adapter lookup is keyed by the `hitl.channel` config value, not by `state.action_type`. The net-new infrastructure (a `_contributed_adapters` registry on `FSMExecutor` alongside `_contributed_actions`/`_contributed_evaluators` at `executor.py:272–274`, the `hitl.channel` config property, and the resolution call site) is identical under both options, so separation costs nothing extra.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — extend `ActionProviderExtension` | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |
| B — new `CommunicationAdapterExtension` | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- **Option A**: `wire_extensions()` loop and conflict-detection guards are reusable, but no existing extension class mixes `provided_*` methods from different capability types; `provided_actions()` is precisely typed as `dict[str, ActionRunner]`, which a `CommunicationAdapter` does not satisfy.
- **Option B**: replicates a mechanical 4-precedent pattern end-to-end — Protocol class, `hasattr()` gate, `_contributed_*` executor slot, `ValueError` duplicate guard, `__init__.py` export, `TestNewProtocols` smoke/protocol-satisfied tests (`test_extension.py:524–691`), and a one-line addition to the `ll-create-extension` scaffold docstring (`create_extension.py:84`).

**Follow-through for implementation**: register via `hasattr(ext, "provided_adapters")` in `wire_extensions()`; add `_contributed_adapters: dict[str, CommunicationAdapter]` to `FSMExecutor.__init__`; resolve the active adapter from `hitl.channel` with `terminal` fallback; update the `ll-create-extension` docstring and `__init__.py` exports; FEAT-1931 (terminal) and the EventBus adapter (per the 2026-06-20 re-scope; replaces the cancelled FEAT-1932) implement adapters against the new Protocol.

## API/Interface

The `CommunicationAdapter` abstract protocol defines the public contract:

_Revised 2026-09-04 per Pre-implementation Review #1, #3, #4, #6, #8, #11–#15._

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

# Canonical event names shared by FEAT-1794 (emitter), the eventbus adapter,
# and FEAT-3323 (read-only relay). Follows the RATE_LIMIT_WAITING_EVENT
# string-constant convention; LLEvent is never subclassed in this codebase.
HUMAN_APPROVAL_REQUESTED_EVENT = "human_approval_requested"
HUMAN_RESPONSE_EVENT = "human_response"

Verdict = Literal["approve", "reject", "edit"]

@dataclass
class AdapterResponse:
    """Operator verdict returned by an adapter. Named to avoid colliding with
    FEAT-1794's ``HumanResponse`` event-bus payload."""
    verdict: Verdict
    edited_text: str | None = None   # populated for "edit"
    reason: str | None = None

@dataclass
class TimeoutResponse:
    """Returned when no verdict arrived within ``timeout``.

    ``timed_out`` is always True; it exists as a cheap discriminator so callers
    can ``match``/``isinstance`` without importing both types.
    """
    timed_out: bool = True
    elapsed_seconds: float = 0.0

class CommunicationAdapterNotFound(LookupError):
    """Raised by the executor resolver when ``hitl.channel`` names no
    registered adapter. Message follows the resolve_host / resolve_emitter
    template: ``"... is not registered. Available: [...]."``"""

class CommunicationAdapter(ABC):
    """Abstract base class for HITL communication channels."""

    @abstractmethod
    def send_alert(
        self,
        loop_name: str,
        state_name: str,
        prompt: str,
        captured_context: dict,
    ) -> str:
        """Deliver an approval request to the operator. Returns alert_id."""

    @abstractmethod
    def await_response(
        self, alert_id: str, timeout: float
    ) -> AdapterResponse | TimeoutResponse:
        """Block up to ``timeout`` seconds for the operator's verdict on ``alert_id``.

        Re-entrant per alert: the executor polls this in short ticks so
        shutdown stays responsive. Repeat calls for the same ``alert_id`` are
        expected; a verdict that arrives between calls must be retained and
        returned on the next call. A ``TimeoutResponse`` does not invalidate
        the alert — only ``cancel_alert()`` does.
        """

    @abstractmethod
    def supports_async(self) -> bool:
        """True if this channel can reach an operator not watching the terminal."""

    def cancel_alert(self, alert_id: str) -> None:
        """Withdraw a pending alert (e.g. on the timeout route). No-op by default."""
        return None
```

Extension registration (via the new `CommunicationAdapterExtension` — see
Decision Rationale). `provided_adapters()` returns a **dict keyed by channel
name**, matching `provided_actions()` / `provided_evaluators()`:

```python
class CommunicationAdapterExtension(Protocol):
    def provided_adapters(self) -> dict[str, CommunicationAdapter]: ...

class TerminalAdapter(CommunicationAdapter):   # FEAT-1931
    ...

class TerminalAdapterExtension:
    def provided_adapters(self) -> dict[str, CommunicationAdapter]:
        return {"terminal": TerminalAdapter()}
```

Executor resolver (this issue; no call site until FEAT-1794):

```python
class FSMExecutor:
    _contributed_adapters: dict[str, CommunicationAdapter]

    def resolve_communication_adapter(self) -> CommunicationAdapter:
        # _get_br_config() is the memoized BRConfig accessor (executor.py:2643,
        # BUG-3009); FSMExecutor has no `_config` attribute.
        channel = self._get_br_config().hitl.channel  # default "terminal"
        try:
            return self._contributed_adapters[channel]
        except KeyError:
            raise CommunicationAdapterNotFound(
                f"Communication adapter {channel!r} is not registered. "
                f"Available: {sorted(self._contributed_adapters)}."
            ) from None
```

## Integration Map

### Files to Create
- `scripts/little_loops/fsm/communication_adapter.py` — `CommunicationAdapter`
  ABC, `AdapterResponse` / `TimeoutResponse` dataclasses,
  `CommunicationAdapterNotFound`, the two event-name constants
- `scripts/tests/test_communication_adapter.py` — mock adapter, protocol contract
  tests

### Files to Modify
- `scripts/little_loops/extension.py:81` — add the new
  `CommunicationAdapterExtension` Protocol (decided; Option B)
- `scripts/little_loops/fsm/__init__.py:102,182` — re-export the two event
  constants beside `RATE_LIMIT_WAITING_EVENT` (Review #16)
- `scripts/little_loops/extension.py:246` — `wire_extensions()`: wire adapters
  into executor
- `scripts/little_loops/fsm/executor.py` — resolve adapter from config +
  registry
- `.ll/ll-config.json` schema — add `hitl.channel` key
- `scripts/little_loops/__init__.py:9-18,94-101` — `/ll:wire-issue` finding:
  public API export block (`from little_loops.extension import (...)`) and the
  `__all__` list under the `# extensions` comment enumerate
  `ActionProviderExtension`/`EvaluatorProviderExtension`/`InterceptorExtension`/
  `LLHookIntentExtension` by name; `CommunicationAdapter` and
  `CommunicationAdapterExtension` need entries in both if they join the public
  `little_loops` API (note: neither is re-exported from `fsm/__init__.py` today
  — only the top-level package re-exports capability Protocols, so
  `fsm/__init__.py` needs no change)
- `docs/reference/CLI.md:4629-4644` — `ll-create-extension` command reference
  embeds a **second, independent copy** of the scaffold docstring's
  Protocol-name list (distinct from `templates/extension/extension.py.tmpl:8-14`
  already cited above) — drifts separately, needs its own edit
- ~~`docs/reference/CLI.md:904-933` — `ll-loop validate` rule bullet for the
  `hitl.channel` warning~~ — moved to FEAT-1794 (Review #5)
- `scripts/tests/test_config_schema.py:1423-1448` — `_discover_dataclasses()`
  (backing the BUG-3192 `TestDataclassSectionMapCompleteness` guard) ast-walks
  only `config/features.py`, `config/automation.py`, `config/core.py` — **it
  does not scan `config/orchestration.py`**, so `OrchestrationConfig`/
  `AdvisorConfig` already have no entries in `_DATACLASS_SECTION_MAP` and the
  guard is structurally blind to that whole module. If `HitlConfig` lands in
  `config/orchestration.py` per the Proposed Solution's suggested location, the
  drift guard will never detect it as unmapped — either extend
  `_discover_dataclasses()` to walk `config/orchestration.py` too, or place
  `HitlConfig` in `config/core.py` instead, or add a documented exemption.

### Similar Patterns
- `transport.py:115` — `UnixSocketTransport._accept_loop()`: transport
  abstraction with timeout
- `extension.py:81` — `ActionProviderExtension.provided_actions()`: extension
  registration pattern
- `host_runner.py:74` — `HostCapabilities`: capability detection pattern

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

Additional callers, precedent anchors, and config-wiring call sites found beyond what the sections above already cite:

- Documentation anchors (line-level, beyond the file-only citations in `## Related Key Documentation`): `docs/ARCHITECTURE.md:586,594-599` (Extension Architecture & Event Flow — the table listing the 4 existing capability Protocols); `docs/reference/API.md:10790` (`class LLExtension(Protocol)`), `:10887` (`def wire_extensions`), `:10911-10929` (`LLHookIntentExtension` doc block, closest precedent for documenting a 5th Protocol); `docs/reference/CONFIGURATION.md:1359` (`### orchestration`, precedent section shape for documenting a new `hitl` namespace); `CONTRIBUTING.md:676` (`## Authoring Extensions`)
- `scripts/little_loops/config/orchestration.py` — houses `OrchestrationConfig` *and* `AdvisorConfig` as sibling dataclasses in one module; precedent for where a `HitlConfig` dataclass could live rather than a dedicated new file
- `scripts/little_loops/config/__init__.py` — package-level import/`__all__` list a new `HitlConfig` would need to join, alongside `OrchestrationConfig`/`AdvisorConfig`/`ClusterConfig`
- `scripts/little_loops/templates/extension/test_extension.py.tmpl` — companion scaffold test template alongside `extension.py.tmpl`
- Naming-note: a new `hitl` top-level config namespace shares its name with the pre-existing, unrelated `hitl-md`/`hitl-compare` built-in loop family (FEAT-1613/1545 human-review-of-markdown loops — `scripts/little_loops/loops/hitl-md.yaml`, `scripts/little_loops/loops/hitl-compare.yaml`, plus references in `fsm/persistence.py`, `fsm/schema.py`, `cli/output.py`). Different config surface (a loop name vs. a `BRConfig` namespace key), not a functional conflict, but the shared term is worth flagging for reader clarity when documenting `hitl.channel`.
- `.issues/enhancements/P3-ENH-2249-rescope-epic-1929-post-hermes-and-track-curated-ll-artifacts.md` — post-Hermes rescoping enhancement for this issue's parent epic (EPIC-1929), not yet cross-referenced in this issue's own re-scope section
- `.issues/bugs/P3-BUG-3192-config-schemajson-diverges-from-code-...` — documents prior `config-schema.json` vs. dataclass default drift for other namespaces (`learning_tests.enabled`, `sync.github.pull_limit`, `socket.max_clients`); relevant risk precedent for keeping `hitl.channel`'s default in sync across the schema and the `HitlConfig` dataclass

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

- **Additional testing precedent for resolver-miss behavior** (beyond the extension-wiring tests already cited): `scripts/tests/test_codequery_core.py:10-25` (`TestResolveProvider`) and `scripts/tests/test_adapters.py:90-102` (`TestResolveEmitter`) share a 4-test shape for a config-key resolver — a known-good key returns the right concrete type, an unknown key raises the module's exception via `pytest.raises(..., match="not registered")`, the returned instance satisfies the relevant `@runtime_checkable` Protocol via `isinstance()`, and (codequery only) a special-case fallback key resolves to something available. `test_extension.py`'s `TestNewProtocols`/`TestWireExtensions` (already cited) cover Protocol structural-typing and extension-wiring conflict detection, not this resolver-lookup shape — `resolve_communication_adapter()`'s own tests are closer to this pattern. **Config plumbing for these tests**: the resolver reads `hitl.channel` through `_get_br_config()`, which builds `BRConfig(self.working_dir or Path.cwd())`, so each resolver test must either pass `working_dir=tmp_path` with a written `.ll/ll-config.json` or pre-seed `executor._br_config` (Review #11).
- Confirmed (2026-09-04 stale-triage re-check): `scripts/little_loops/cli/verify_kinds.py` and `scripts/little_loops/extensions/reference_interceptor.py` (surfaced by a code-graph impact-of query on `extension.py`) are false positives — neither references `CommunicationAdapter`/`provided_adapters`/`extension` imports; not relevant to this issue.
- Confirmed (2026-09-04 stale-triage re-check): all previously-cited `config/core.py` anchors (`332-333`, `461-463`, `863`) are unchanged by the 2026-09-03 SSE-bridge commit (`92670a9de`) — its only `config/core.py` change is a new `"bridge"` sub-block inside the existing `"events"` block (~938-959), which sits after the cited anchors and does not shift them. `to_dict()` itself (the method definition, distinct from the `"orchestration"` serialization block cited at `863`) is at line `725`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/parallel.py:321` — calls `wire_extensions(event_bus, config.extensions)`
- `scripts/little_loops/cli/sprint/run.py:800` — calls `wire_extensions(event_bus, config.extensions)`
- `scripts/little_loops/cli/loop/run.py:622` — calls `wire_extensions(executor.event_bus, _config.extensions, executor=executor)`
- `scripts/little_loops/cli/loop/lifecycle.py:736` — calls `wire_extensions(executor.event_bus, config.extensions, executor=executor)`

### Tests

_Wiring pass added by `/ll:wire-issue` — 2026-09-03:_

- `scripts/tests/test_extension.py` — `class TestNewProtocols` (524-691) is
  the 1:1 precedent: each capability Protocol gets exactly two hand-written
  methods, a `test_smoke_import_*_extension` (import + not-None) and a
  `test_*_extension_protocol_satisfied` (local minimal class assigned to a
  `: ProtocolName`-annotated variable to prove structural typing). Add
  `test_smoke_import_communication_adapter_extension` and
  `test_communication_adapter_extension_protocol_satisfied` following this
  exact shape.
- `scripts/tests/test_extension.py` — `class TestWireExtensions` (135-522) is
  **not** table-driven; each capability slot gets separate individually-named
  methods (`test_wire_extensions_with_executor_populates_actions` :315,
  `..._conflict_detection_actions` :385, same pattern for evaluators). Add
  `test_wire_extensions_with_executor_populates_adapters` and
  `test_wire_extensions_conflict_detection_adapters` — no existing test breaks
  by adding a 5th slot.
- `scripts/tests/test_interceptor_extension.py:196-235` —
  `TestReferenceInterceptorWiring` is scoped exclusively to
  `ReferenceInterceptorExtension`; only needs a change if a
  `ReferenceCommunicationAdapterExtension` analog is added to
  `little_loops/extensions/` — otherwise out of scope, no update required.
- `scripts/tests/test_config.py` — `TestAdvisorConfig`/`TestOrchestrationConfig`
  (3709-3906) plus the `to_dict()` roundtrip pair `test_to_dict_advisor` /
  `test_to_dict_advisor_defaults_when_unset` (1155-1234) are the pattern a new
  `TestHitlConfig` (from_dict defaults / with values / partial override),
  `TestBRConfigHitl` (property-from-file / defaults-when-key-absent), and
  `test_to_dict_hitl` / `test_to_dict_hitl_defaults_when_unset` should follow.
- `scripts/tests/test_config_schema.py` — `_SCHEMA_DEFAULT_ALLOWLIST`
  (1239-1249) exempts dotted paths with no schema `"default"`; `hitl.channel`
  states a `"terminal"` default so should NOT need this allowlist — but if the
  schema entry omits `"default"`, `TestSchemaValueParity.
  test_to_dict_values_match_schema_defaults` (1283) will fail until it's added.
  `_DATACLASS_SECTION_MAP` / `_discover_dataclasses()` (1346-1448) — see the
  blind-spot finding under Files to Modify above; `HitlConfig` must be added to
  `_DATACLASS_SECTION_MAP` explicitly regardless of which module it lives in,
  since the guard can silently miss it either way.
- ~~(moved to FEAT-1794 with the validate warning, Review #5)~~
  `scripts/tests/test_fsm_validation_evaluator_rules.py:706-954` —
  `TestPruningProfileCoverageValidation` (MR-12) is the precedent for a warning
  driven by an orchestration-level config value threaded through
  `validate_fsm(fsm, orchestration_request_path=...)`
  (`fsm/validation/structural_rules.py:1000-1002,1182`) and `cmd_validate`
  (`cli/loop/config_cmds.py:14-37`, which reads
  `BRConfig(Path.cwd()).orchestration.request_path`). The new `hitl.channel`
  warning needs an analogous parameter (e.g. `hitl_channel` plus a host-
  interactivity signal) threaded the same way, with tests mirroring
  `test_fires_when_orchestration_request_path_sdk_invoking_skill` (843) and
  `test_fires_end_to_end_via_validate_fsm` (938).
- ~~(moved to FEAT-1794 with the validate warning, Review #5)~~
  `scripts/tests/test_builtin_loops.py` — `class TestValidatorWarningBudget`
  (16647-16776): `CATEGORY_PATTERNS` (16657-16669) maps a category name to a
  message substring, and `_classify()`/`_collect_findings()` (16730-16748)
  **silently discard** any warning whose message doesn't match a known
  category. The new `hitl.channel` warning needs a `"hitl-channel": "<substring>"`
  entry added here or `test_deterministic_warning_categories_do_not_regrow`
  will not track it (no existing test breaks without this — it's an opt-in
  ratchet, not a required update, but coverage is incomplete without it).
- `scripts/tests/test_create_extension.py:115-126` —
  `test_extension_py_lists_hook_intent_protocol` is the precedent (asserts the
  generated scaffold contains the literal Protocol name string, not a closed
  list). Add `test_extension_py_lists_communication_adapter_protocol` asserting
  `"CommunicationAdapterExtension" in ext_content`.

_Wiring pass added by `/ll:wire-issue` — 2026-09-04:_

- `scripts/tests/test_wiring_reference_docs.py` — the `DOC_STRINGS_PRESENT`
  table (from line 20; `test_string_present_in_doc` at 230 consumes it) is the
  established doc-wiring-completeness gate every capability-Protocol issue has
  used to lock in its API.md/CONFIGURATION.md prose, e.g.
  `("docs/reference/API.md", "### LLHookIntentExtension", "FEAT-1459")` (:33),
  `("docs/reference/API.md", "provided_hook_intents", "FEAT-1459")` (:34),
  `("docs/reference/CONFIGURATION.md", "LLHookIntentExtension", "FEAT-1459")`
  (:52), and `("docs/reference/API.md", "### little_loops.fsm.rate_limit_circuit",
  "ENH-1138")` (:104, the precedent for the new Submodule Overview row above).
  No row currently references `CommunicationAdapter`/`CommunicationAdapterExtension`/
  `hitl.channel` — add rows for the new Protocol name, `provided_adapters`,
  `hitl.channel`, and the new `### little_loops.fsm.communication_adapter`
  API.md heading.
- `scripts/tests/test_wiring_cli_registry.py` — same table shape keyed to
  `docs/reference/CLI.md`, e.g. `("docs/reference/CLI.md",
  "LLHookIntentExtension", "FEAT-1457")` — needs a row for the
  `ll-create-extension` scaffold-list edit already tracked above.
- `scripts/tests/test_wiring_skills_and_commands.py` — same table shape keyed
  to `create_extension.py`/`SKILL.md`/`docs/claude-code/write-a-hook.md` — add
  a row if any skill/command doc gains `CommunicationAdapterExtension` text.
- `scripts/tests/test_wiring_guides_and_meta.py` — same table shape keyed to
  `CONTRIBUTING.md`/`docs/ARCHITECTURE.md` — add a row for whichever guide
  prose names the new Protocol.
- `scripts/tests/test_config_schema.py:1204-1250` — `TestToDictSchemaParity`
  (BUG-3012 guard, **distinct** from the already-cited
  `_DATACLASS_SECTION_MAP`/`_discover_dataclasses()` guard at 1423-1448 and
  from `TestSchemaValueParity`). `test_to_dict_emits_every_schema_section`
  (1219-1239) diffs `config-schema.json`'s top-level `properties` keys against
  `BRConfig(...).to_dict().keys()` — adding `hitl` to the schema without a
  matching `"hitl"` entry in `to_dict()` (`config/core.py:863+`, already cited)
  fails this test immediately. `test_to_dict_emits_no_key_absent_from_schema`
  (1241-1250) is the reverse guard.
- `scripts/tests/test_fsm_executor.py:6800-6855`
  (`test_action_mode_returns_contributed_when_registered` et al.) and
  `scripts/tests/test_ll_loop_execution.py:2145-2214`
  (`test_contributed_evaluator_called_when_type_registered` et al.) — a third,
  more direct precedent for `resolve_communication_adapter()`'s own unit
  tests, beyond the already-cited `test_codequery_core.py`/`test_adapters.py`
  resolver-shape and `test_extension.py::TestWireExtensions` wiring-through-
  `wire_extensions()` patterns: construct `FSMExecutor` directly and assign
  `executor._contributed_adapters["channel"] = mock_adapter`, bypassing
  extension wiring entirely — the closest match since this issue scopes the
  resolver as executor-only with no wiring call site yet.

### Documentation

_Wiring pass added by `/ll:wire-issue` — 2026-09-03:_

- `docs/reference/CLI.md:4629-4644` — `ll-create-extension` reference embeds
  the scaffold docstring's Protocol-name list verbatim (separate copy from
  `extension.py.tmpl`, see Files to Modify)
- `docs/reference/CLI.md:904-933` — `ll-loop validate` rule catalog needs a new
  bullet for the `hitl.channel` warning (see Files to Modify)
- `scripts/little_loops/__init__.py` public API docstrings/exports — see Files
  to Modify

_Wiring pass added by `/ll:wire-issue` — 2026-09-04:_

- `docs/reference/API.md:5620-5644` — `## little_loops.fsm` `### Submodule
  Overview` table enumerates every `fsm/*.py` file with a one-line purpose
  (distinct from the already-cited extension-Protocol doc anchors at
  10790/10887/10911-10929). The new `communication_adapter.py` needs its own
  row, following the shape of the existing `little_loops.fsm.rate_limit_circuit`
  row (added for ENH-1138). The adjacent `### Quick Import` block does not
  need a change — these types aren't re-exported from `fsm/__init__.py`.

### Additional Confirmed Anchors
- `scripts/little_loops/extension.py:103-111` — `LLHookIntentExtension`, the most recently added of the 4 capability Protocols; nearest structural precedent for a new `CommunicationAdapterExtension`
- `scripts/little_loops/extension.py:234-277` — `wire_extensions()` registration body: `hasattr()` detection loop, the `fsm_executor is not None:` block populating `_contributed_actions`/`_contributed_evaluators`/`_interceptors`, and the separate final loop wiring `provided_hook_intents`
- `scripts/little_loops/fsm/executor.py:494-497` — `FSMExecutor.__init__`: `_contributed_actions`/`_contributed_evaluators`/`_interceptors` declared together; exact site for a parallel `_contributed_adapters: dict[str, CommunicationAdapter] = {}`
- `scripts/little_loops/cli/create_extension.py:80-94` (`_render_extension()`) — hardcodes a 4-item Protocol-name list (`InterceptorExtension, ActionProviderExtension, EvaluatorProviderExtension, LLHookIntentExtension`) in the scaffolded extension docstring; a 5th Protocol needs manual addition here (no data-driven registry exists)
- `scripts/little_loops/templates/extension/extension.py.tmpl:8-14` — a second, independent copy of the same docstring sentence, already out of sync with `create_extension.py` (lists only 3 of the current 4 Protocols, missing `LLHookIntentExtension`) — pre-existing drift, not introduced by this issue
- `scripts/little_loops/config/core.py:332-333` — `BRConfig._parse_config()`: `self._orchestration = OrchestrationConfig.from_dict(self._raw_config.get("orchestration", {}))` — pattern a new `hitl` namespace's wiring would follow
- `scripts/little_loops/config/core.py:461-463` — `BRConfig.orchestration` property accessor — a `hitl` namespace needs the equivalent
- `scripts/little_loops/config/core.py:863+` — `to_dict()`-style serialization block that mirrors each config namespace back out; a third call site any new namespace must also touch
- `scripts/little_loops/config-schema.json:1239-1244` (`learning_tests.release_gate`) and `:1307-1312` (`dependency_mapping.conflict_threshold`) — closest existing precedents for a single string/enum key with both a JSON `"default"` and a dataclass-level default, the shape `hitl.channel` would follow (compare `orchestration.host_cli`, `:1741-1749`, which has no JSON `"default"` and instead documents an env-var-wins fallback in prose)
- `scripts/little_loops/host_runner.py:127-152` (`HostCapabilities`) — confirmed: no `interactive`/non-interactive-host field exists today (fields are `streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`); AC #5's "warns ... when host is non-interactive" has no existing signal to key on and would need one added
- `scripts/little_loops/cli/loop/config_cmds.py:14` — `cmd_validate`, the actual `ll-loop validate` entry point (anchor-drifted from `cli/loop/__init__.py:1089`); warnings flow through `ValidationError(message=..., path=..., severity=ValidationSeverity.WARNING)` (`scripts/little_loops/fsm/validation/_base.py:15-41`), with `_validate_state_action()` (`scripts/little_loops/fsm/validation/structural_rules.py:408-448`) as a concrete WARNING-emission precedent

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

Concrete types, signatures, and the call path this protocol plugs into, derived from `extension.py`'s existing 4-Protocol capability pattern and `FSMExecutor`'s contributed-registry mechanics.

- `EvaluateConfig.type: Literal[...]` (`scripts/little_loops/fsm/schema.py:95-112`) enumerates 16 existing evaluator type strings; `human_approval` is not among them — confirms no partial scaffolding exists as an evaluator type.
- `StateConfig.action_type` (`scripts/little_loops/fsm/schema.py:694`) is typed `str | None`, not a closed `Literal`/enum — a new `human_approval`-style action type requires no FSM schema enum change, only executor-side dispatch plus extension wiring, consistent with how `_contributed_actions` extension actions are already looked up by arbitrary string key rather than a fixed set.
- `wire_extensions()`'s four existing gates (`extension.py:246-273`) split into two structurally different sub-patterns: `InterceptorExtension`/`ActionProviderExtension`/`EvaluatorProviderExtension` are gated inside `if fsm_executor is not None:` (`:246-267`) and are inert when no `executor=` kwarg is passed; `LLHookIntentExtension`'s gate (`:269-273`) runs unconditionally in a separate loop and writes into a module-level registry in `hooks/__init__.py` (`_HOOK_INTENT_REGISTRY`), not onto `FSMExecutor` at all. A `CommunicationAdapterExtension` gate should follow the dict-with-conflict-check shape shared by actions/evaluators, inside the `fsm_executor is not None` block, since adapters are resolved by the `hitl.channel` config key the same way actions are resolved by `state.action_type`.
- `scripts/little_loops/templates/extension/extension.py.tmpl` is confirmed dead code — not referenced anywhere in `create_extension.py` or elsewhere; the scaffold's actual output comes from the inline docstring string list in `create_extension.py:80-94` (`_render_extension()`), which is the only site a 5th Protocol name needs adding to (the `.tmpl` file's independent drift — missing `LLHookIntentExtension` — is pre-existing and out of this issue's scope).

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

- **Contested convention — resolver-miss exception design**: three patterns coexist in this codebase for "resolve by registry key, raise on miss," none of which this issue's drafted `CommunicationAdapterNotFound(LookupError)` fully matches. (a) `HostNotConfigured` (`host_runner.py:107`) / `AdvisorNotConfigured` (`advisor.py:176`) — dedicated `*NotConfigured` subclass of `RuntimeError`. (b) `CodeQueryError` (`codequery/core.py:35`) / `AdapterError` (`adapters/core.py:25`) — a single umbrella exception per module, not miss-specific, reused for the registry-miss case. Both (a) and (b)'s registry-miss call sites share one message template, `f"{Kind} {name!r} is not registered. Available: {sorted(REGISTRY)}."` (`host_runner.py:2015-2023` `resolve_host`, `codequery/core.py:135-140` `_instantiate`, `adapters/core.py:76-78` `resolve_emitter`) — a precedent this issue's own citations (`host_runner.py:74` `HostCapabilities`) don't include. This issue's originally drafted message differed from that 3-precedent template, and its `LookupError` base matches neither (a) nor (b). **Resolved 2026-09-04 (Review #14)**: adopt the 3-precedent message template (`"Communication adapter {channel!r} is not registered. Available: [...]."`) so tests match on `"not registered"`; keep the `LookupError` base as a knowing divergence (a registry miss is a lookup failure, and `KeyError` callers catching `LookupError` still work).

### Types
- `CommunicationAdapter` (`abc.ABC`, `scripts/little_loops/fsm/communication_adapter.py`, new file) — abstract `send_alert()`/`await_response()`/`supports_async()` plus concrete no-op `cancel_alert()`, per API/Interface above (Review #13, #15)
- `CommunicationAdapterExtension(Protocol)` (new, `scripts/little_loops/extension.py`) — single method `provided_adapters() -> dict[str, CommunicationAdapter]` (revised 2026-09-04 from `list[type[...]]`, which had no precedent and no channel key; now matches all 4 existing capability Protocols)
- `AdapterResponse` / `TimeoutResponse` / `CommunicationAdapterNotFound` (new, `communication_adapter.py`) — see API/Interface; the former `HumanResponse` name is retired here to avoid colliding with FEAT-1794's `HumanResponse(LLEvent)` (resolved 2026-09-04)
- `HitlConfig` (new dataclass, `config/core.py`, field `channel: str = "terminal"`) plus `BRConfig.hitl` property and `to_dict()` entry

### Signatures
- `wire_extensions(bus: EventBus, config_paths: list[str] | None = None, executor: FSMExecutor | PersistentExecutor | None = None) -> list[LLExtension]` (`extension.py:201`) — existing signature the new `hasattr(ext, "provided_adapters")` gate plugs into; the executor-registry effect is an in-place mutation of the passed `executor=` kwarg, not the return value
- `FSMExecutor.__init__` declares `_contributed_actions: dict[str, ActionRunner] = {}` / `_contributed_evaluators: dict[str, Evaluator] = {}` (`executor.py:494-497`) with no constructor parameter for pre-seeding — both start empty and are only filled by a later `wire_extensions(..., executor=fsm_executor)` call; a `_contributed_adapters: dict[str, CommunicationAdapter] = {}` would follow the identical shape
- `FSMExecutor._get_br_config(self) -> BRConfig` (`executor.py:2643`) — memoized `BRConfig(self.working_dir or Path.cwd())`; the only config accessor on the executor, and the one `resolve_communication_adapter()` reads `hitl.channel` through (Review #11)
- `FSMExecutor._interruptible_sleep(duration, on_heartbeat=None) -> float` (`executor.py:3833`) — 100 ms tick loop exiting on `_shutdown_requested`; the polling shape FEAT-1794 wraps around `await_response()`, and the reason the re-entrancy contract (Review #12) exists
- `BRConfig._parse_config()` wires each namespace as `self._<ns> = <Ns>Config.from_dict(self._raw_config.get("<ns>", {}))` (`config/core.py:332-333` shows the `orchestration` case) — a `hitl` namespace needs a matching `HitlConfig.from_dict(...)` call plus the `BRConfig.hitl` property (pattern at `config/core.py:461-463`) and a `to_dict()` entry (`:863+`)

### Call Path
`cli/loop/run.py:622` (or `cli/loop/lifecycle.py:736`) → `wire_extensions(executor.event_bus, config.extensions, executor=executor)` (`extension.py:201`) → `hasattr(ext, "provided_adapters")` gate (new, alongside the existing gates at `extension.py:246-273`) → `fsm_executor._contributed_adapters.update(ext.provided_adapters())` (new, mirrors `:248-256`) → (not yet implemented anywhere) a `human_approval` state handler in `executor.py` resolves the active adapter from `_contributed_adapters` keyed by the `hitl.channel` config value, falling back to `"terminal"` → `adapter.send_alert(...)` → `adapter.await_response(...)`

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold; `hitl.channel` is a plain config-key channel selector with a documented default, not a classification rule.

## Implementation Steps

1. Define `CommunicationAdapter(ABC)` with abstract `send_alert()`,
   `await_response()` (re-entrancy contract in docstring), `supports_async()`
   and concrete no-op `cancel_alert()` in a new
   `scripts/little_loops/fsm/communication_adapter.py`
2. Add adapter registration to the extension system — create a new
   `CommunicationAdapterExtension` Protocol with `provided_adapters()` in
   `extension.py` (decided; see Decision Rationale)
3. Wire adapter discovery into `wire_extensions()` so the executor can
   resolve registered adapters
4. Add `_contributed_adapters` and `resolve_communication_adapter()` to
   `FSMExecutor` (`executor.py`), reading `hitl.channel` via
   `_get_br_config()`; raise `CommunicationAdapterNotFound` (`"... is not
   registered. Available: [...]."`) on a miss. No call site in this issue —
   FEAT-1794 adds the `human_approval` branch that calls it.
5. Add `hitl.channel` key to `config-schema.json` with `"default": "terminal"`
   and `HitlConfig` in `config/core.py` (+ `BRConfig.hitl`, `to_dict()`)
6. ~~Add `ll-loop validate` warning when `hitl.channel` is unset on a
   non-interactive host~~ — moved to FEAT-1794 (Pre-implementation Review #5)
7. Write protocol contract tests with a mock adapter registered via a
   `CommunicationAdapterExtension`: resolver hit, resolver miss (`match="not
   registered"`), duplicate channel conflict, `AdapterResponse` verdict
   literals, ABC rejects an incomplete subclass with `TypeError`,
   `await_response()` re-entrancy (two `TimeoutResponse`s then the verdict),
   `cancel_alert()` default is a no-op. Resolver tests seed config per Review
   #11.
8. Export `CommunicationAdapter`, `CommunicationAdapterExtension`,
   `AdapterResponse`, `TimeoutResponse`, `CommunicationAdapterNotFound`, and
   the two event constants from `little_loops/__init__.py`; re-export the two
   event constants from `fsm/__init__.py` beside `RATE_LIMIT_WAITING_EVENT`
9. Create the `FEAT: EventBus HITL adapter` child issue under EPIC-1929,
   update EPIC-1929's children list / dependency tree (drop FEAT-1932, add the
   new child), and apply the FEAT-1794 / FEAT-1931 signature and event-name
   fixes listed in Pre-implementation Review #3 and #4. FEAT-1794 also gains
   a note to call `cancel_alert()` on its timeout route (Review #15).
10. Document the `hitl` namespace in `docs/reference/CONFIGURATION.md` with a
    one-sentence disambiguation from the `hitl-md`/`hitl-compare` loop family
    (Review #17).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Export `CommunicationAdapter`/`CommunicationAdapterExtension` from
  `scripts/little_loops/__init__.py` (import block + `__all__`) if they join
  the public package API
- Update `docs/reference/CLI.md:4629-4644` — second independent copy of the
  scaffold Protocol-list docstring (`ll-create-extension` reference)
- ~~Update `docs/reference/CLI.md:904-933` — add a bullet for the new
  `hitl.channel` unset-on-non-interactive-host warning~~ — moved to FEAT-1794
- Place `HitlConfig` in `config/core.py` (decided 2026-09-04) so BUG-3192's
  `TestDataclassSectionMapCompleteness` guard sees it without extending
  `_discover_dataclasses()` (`scripts/tests/test_config_schema.py:1423-1448`)
- Add `HitlConfig` to `_DATACLASS_SECTION_MAP`
  (`scripts/tests/test_config_schema.py:1346-1411`)
- Add `TestHitlConfig`/`TestBRConfigHitl`/`test_to_dict_hitl*` to
  `scripts/tests/test_config.py`, following the `TestAdvisorConfig` pattern
- Add `test_smoke_import_communication_adapter_extension` +
  `test_communication_adapter_extension_protocol_satisfied` to
  `scripts/tests/test_extension.py`'s `TestNewProtocols`
- Add `test_wire_extensions_with_executor_populates_adapters` +
  `test_wire_extensions_conflict_detection_adapters` to
  `scripts/tests/test_extension.py`'s `TestWireExtensions`
- Add `test_extension_py_lists_communication_adapter_protocol` to
  `scripts/tests/test_create_extension.py`
- ~~Thread a `hitl_channel`/host-interactivity parameter through
  `validate_fsm()` and `cmd_validate` (`cli/loop/config_cmds.py:14-37`),
  mirroring the `orchestration_request_path` pattern (MR-12 precedent)~~ —
  moved to FEAT-1794 with the validate warning
- ~~Add a `"hitl-channel"` entry to `CATEGORY_PATTERNS` in
  `scripts/tests/test_builtin_loops.py`'s `TestValidatorWarningBudget`
  (16657-16669)~~ — moved to FEAT-1794 with the validate warning
- Add a `### little_loops.fsm.communication_adapter` row to the Submodule
  Overview table in `docs/reference/API.md:5620-5644`, following the
  `little_loops.fsm.rate_limit_circuit` row's shape
- Add `DOC_STRINGS_PRESENT` rows to `scripts/tests/test_wiring_reference_docs.py`
  for `CommunicationAdapterExtension`, `provided_adapters`, `hitl.channel`, and
  the new API.md Submodule Overview heading; add matching rows to
  `scripts/tests/test_wiring_cli_registry.py` (`ll-create-extension` CLI.md
  edit) and, if applicable, `test_wiring_skills_and_commands.py` /
  `test_wiring_guides_and_meta.py`
- Confirm `TestToDictSchemaParity`
  (`scripts/tests/test_config_schema.py:1204-1250`) stays green once `hitl` is
  added to `config-schema.json` — it fails independently of the already-cited
  `_DATACLASS_SECTION_MAP` guard if `BRConfig.to_dict()` doesn't also gain a
  `"hitl"` entry

## Impact

- **Priority**: P3 (matches frontmatter; downgraded with EPIC-1929 on 2026-07-03) — prerequisite for FEAT-1794, FEAT-1931, and the EventBus adapter
- **Effort**: Small — abstract class, registration hook, config key
- **Risk**: Low — no user-facing change until adapters are implemented
- **Breaking Change**: No

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-25): Two conflicts with FEAT-1794 require resolution before implementing `communication_adapter.py`:

1. **Class name collision** — This issue's `API/Interface` defines a dataclass `HumanResponse` with `approved: bool, reason, modified_prompt`. FEAT-1794's `API/Interface` also defines `HumanResponse(LLEvent)` with `verdict: Literal["approve","reject","edit"], edited_text`. Importing both into `executor.py` will cause a name collision. Rename this issue's adapter return type to `AdapterResponse` (or `HumanApprovalDecision`) to avoid the collision; FEAT-1794's `HumanResponse(LLEvent)` event-bus type keeps its name.

2. **Binary vs. three-way verdict** — This issue's `HumanResponse` encodes only `approved: bool`, but FEAT-1794 requires three-way FSM routing (`on_yes`/`on_no`/`on_edit`). The protocol cannot unambiguously express an `edit` verdict via `approved: bool` alone. Add an explicit `verdict: Literal["approve", "reject", "edit"]` field to this issue's return dataclass (replacing `approved: bool`) so `await_response()` can return all three verdict types FEAT-1794's routing table requires.

---

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

**Resolved on this side 2026-09-04**: `## API/Interface` now defines
`AdapterResponse` with `verdict: Literal["approve", "reject", "edit"]` and
`edited_text`. FEAT-1794 keeps `HumanResponse` for its event payload; FEAT-1931's
Scope Boundary note (express edit via `verdict`, no third response type) is
satisfied by this shape. The 2026-09-03 record below is kept for history.

**Reconfirmed 2026-09-03**: both open conflicts remain unresolved on both sides.
This issue's `## API/Interface` section still defines `HumanResponse` with
`approved: bool` (unrenamed). FEAT-1794's `## API/Interface`
(`.issues/features/P3-FEAT-1794-hitl-interrupt-fsm-state-type.md`) still
defines, verbatim and unchanged since this conflict was first logged:

```python
@dataclass
class HumanResponse(LLEvent):
    """Emitted when the operator responds to a human_approval request."""
    loop_name: str
    state_name: str
    verdict: Literal["approve", "reject", "edit"]
    edited_text: str | None  # populated for edit verdict
```

Neither issue has applied its half of the agreed resolution (rename this
issue's adapter dataclass to `AdapterResponse`/`HumanApprovalDecision`; add a
`verdict: Literal["approve", "reject", "edit"]` field in place of
`approved: bool`). No code exists yet for either type, so there is no
executor-level collision today — but the rename should land before FEAT-1931
or the EventBus adapter implement `await_response()` against this issue's
current `HumanResponse` shape.

## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

2026-06-18 (UNSTARTED): `scripts/little_loops/fsm/communication_adapter.py` does not exist. No `CommunicationAdapterExtension` in `extension.py`. No `hitl.channel` config key. FEAT-1794, FEAT-1931, FEAT-1932 remain correctly blocked on this issue. Dependency graph is accurate.

2026-09-03 (`/ll:verify-issues`): Re-confirmed still unimplemented — no `class CommunicationAdapter`/`CommunicationAdapterExtension` anywhere in `scripts/little_loops/`. `blocks: [FEAT-2102, FEAT-1794, FEAT-1931]` all backlink correctly; FEAT-2102 is `deferred`/`blocked_by: [FEAT-1930]` as expected. No active decisions-log rules; `ll-verify-evidence` clean. Verdict: VALID (unchanged).

2026-09-04 (`/ll:verify-issues`): Re-confirmed still unimplemented — no `communication_adapter.py`, `CommunicationAdapter`/`CommunicationAdapterExtension`, `hitl.channel`/`HitlConfig`, or `resolve_communication_adapter` call site anywhere in `scripts/little_loops/`; no git activity since the 2026-09-04 Pre-implementation Review touched `fsm/`, `extension.py`, or `config/`. Dependency graph clean: FEAT-1794/FEAT-1931/FEAT-2102/EPIC-1929 all exist and backlink correctly, no cycles. The `FEAT: EventBus HITL adapter` follow-up child (AC item / Pre-implementation Review #7) has not been created yet — open AC, not a defect. Sibling drift claims in `## Pre-implementation Review` re-verified accurate: FEAT-1794 still emits `human_approval_request` (no `-ed`) at lines 200/285/319; FEAT-1931's `## API/Interface` still shows `await_response(self, timeout)` missing `alert_id`; FEAT-3323 already uses the canonical event names. No active decisions-log rules; `ll-verify-evidence` clean (`ok: true, count: 0`). Spot-checked ~10 line citations across `extension.py`, `executor.py`, `config/core.py`, `config/orchestration.py`, `host_runner.py`, `test_extension.py`, `create_extension.py` — all match current code. Verdict: VALID (unchanged).

## Resolution

Implemented `CommunicationAdapter` (`abc.ABC`) with abstract `send_alert()`/`await_response()`/`supports_async()` and a concrete no-op `cancel_alert()`, plus `AdapterResponse`/`TimeoutResponse`/`CommunicationAdapterNotFound` and the `HUMAN_APPROVAL_REQUESTED_EVENT`/`HUMAN_RESPONSE_EVENT` constants, in new `scripts/little_loops/fsm/communication_adapter.py`. Added `CommunicationAdapterExtension` Protocol to `extension.py` and wired `provided_adapters()` into `wire_extensions()` (dict-merge with conflict `ValueError`, matching the actions/evaluators pattern). Added `FSMExecutor._contributed_adapters` and `resolve_communication_adapter()` (`executor.py`), resolving `hitl.channel` via the memoized `_get_br_config()` and raising `CommunicationAdapterNotFound` on a miss (no call site yet — FEAT-1794's scope). Added `HitlConfig` (`config/core.py`, `channel: str = "terminal"`) with `BRConfig.hitl` property and `to_dict()`/schema entries, plus `hitl.channel` in `config-schema.json`. Re-exported the two event constants from `fsm/__init__.py`; exported the full public surface from `little_loops/__init__.py`. Updated the `ll-create-extension` scaffold docstring (`cli/create_extension.py` + its `docs/reference/CLI.md` mirror) to list the 5th Protocol. Documented in `docs/reference/API.md` (new `### CommunicationAdapterExtension` section, `### little_loops.fsm.communication_adapter` module section, Submodule Overview row) and `docs/reference/CONFIGURATION.md` (new `### hitl` section). Created follow-up child `FEAT-3384` (EventBus HITL adapter) under EPIC-1929 with `blocked_by: [FEAT-1930]`; updated EPIC-1929's Children/Dependency Order/`relates_to` to drop the cancelled FEAT-1932 and add FEAT-3384. Applied the FEAT-1930 Pre-implementation Review's sibling-drift fixes to FEAT-1794 (event constant name/import) and FEAT-1931 (`await_response(alert_id, timeout)` signature, `AdapterResponse` type, dropped `timeout` from `send_alert()`); unblocked both (`blocked` → `open`). Added `hitl` to `_ALLOWED_UNTOUCHED_SECTIONS` in `test_init_audit_fixes.py`'s schema-coverage guard (off-by-default section, same posture as `advisor`/`tamper_guard`). 14 new tests in `test_communication_adapter.py` (ABC contract, re-entrancy, resolver hit/miss/config-selection, extension wiring/conflict) plus additions to `test_extension.py`, `test_config.py`, `test_config_schema.py`, `test_create_extension.py`, `test_wiring_reference_docs.py`, `test_wiring_cli_registry.py`. Full suite: 22732 passed, 43 skipped.

## Status

done

## Related Key Documentation

- `docs/ARCHITECTURE.md` — this protocol is a new abstraction layer inside the FSM loop engine (`human_approval` state, `executor.py` adapter resolution), which the architecture doc covers at the FSM-executor-design level.
- `docs/reference/API.md` — directly extends the documented `fsm/*` (executor) and `extension.py` module surfaces with a new `CommunicationAdapter` protocol and `CommunicationAdapterExtension`.
- `CONTRIBUTING.md` — adding a new extension-registered protocol (`CommunicationAdapterExtension`, `provided_adapters()`) is exactly the extension-authoring pattern (`LLExtension` protocol convention) this doc documents.

## Session Log
- `/ll:manage-issue` - 2026-09-04T07:18:53 - `edcf388a-123e-4783-8b95-eba3c9e4b3da.jsonl`
- pre-implementation review (second pass) - 2026-09-04 - Added Review #11–#17: resolver reads config via `_get_br_config()` (no `self._config` exists), `await_response()` re-entrancy contract, `CommunicationAdapter` as `abc.ABC`, miss-exception message adopts the 3-precedent "not registered" template, optional no-op `cancel_alert()`, event constants re-exported from `fsm/__init__.py`, EPIC-1929 stale-children update + `hitl` naming disambiguation. Struck stale prose (`HumanResponse` in Files to Create, Option A/B hedge, validate-warning items in Files to Modify / Tests).
- `/ll:confidence-check` - 2026-09-04T06:38:34 - `74f231b2-8c53-4096-9a3b-94decf14de3c.jsonl`
- `/ll:verify-issues` - 2026-09-04T06:27:52 - `6171b6cf-c484-42e3-b817-793cf904522b.jsonl`
- `/ll:wire-issue` - 2026-09-04T06:06:42 - `b9f5c7d9-a2cc-4071-8c3e-2bf509c70d40.jsonl`
- `/ll:refine-issue` - 2026-09-04T05:55:26 - `2d6e7cfa-0898-45b8-9b3b-c77badcb19a4.jsonl`
- `/ll:confidence-check` - 2026-09-04T05:49:05 - `0e16f2cb-978a-4796-8ce2-588b8c0efeb2.jsonl`
- pre-implementation review - 2026-09-04 - Folded 10 review decisions into `## Pre-implementation Review`: `AdapterResponse` rename + `verdict` literal, `provided_adapters()` → dict, `alert_id` kept, canonical event constants, validate-warning AC moved to FEAT-1794, resolver-only executor scope with `CommunicationAdapterNotFound`, eventbus adapter to its own child issue, `send_alert` drops `timeout`, `HitlConfig` in `config/core.py`, Impact P2→P3. Sibling edits (FEAT-1794 event name, FEAT-1931 `await_response` signature) still pending.
- `/ll:wire-issue` - 2026-09-03T23:58:41 - `11c94de0-8f35-4de1-a272-34e45de9321f.jsonl`
- `/ll:refine-issue` - 2026-09-03T23:44:55 - `aed94642-f109-4502-89a6-54feff7835ca.jsonl`
- `/ll:verify-issues` - 2026-09-03T19:30:24 - `057585fb-7ab7-4b15-b42a-aa3dc8fffb40.jsonl`
- `/ll:refine-issue` - 2026-09-03T18:25:58 - `08ecfe64-9510-40b1-a733-9cb70ecbc67a.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:08:30 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- backlog-grooming - 2026-07-03T00:00:00Z - Downgraded P2 -> P3 with parent EPIC-1929 (stalled since early June; epic downgraded rather than left distorting the P2 band).
- `/ll:audit-issue-conflicts` - 2026-06-25T21:24:01 - `91915c5b-d793-486c-a140-be4dd3d8ca1f.jsonl`
- `/ll:verify-issues` - 2026-06-25T00:51:21 - `3417b033-6605-44ca-9411-53f9fd585b45.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:14:14 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:decide-issue` - 2026-06-12T16:30:50 - `5f156fda-1001-478e-926c-73ffddf7e4b1.jsonl`
- `/ll:format-issue` - 2026-06-05T22:16:53 - `8041e61d-a9eb-4655-91d2-d32792836de3.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
