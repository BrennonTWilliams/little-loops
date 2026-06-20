---
id: FEAT-1930
title: Communication adapter protocol for async HITL channels
type: FEAT
priority: P2
captured_at: "2026-06-04T00:00:00Z"
discovered_date: 2026-06-04
discovered_by: scope-epic
status: open
parent: EPIC-1929
relates_to: [FEAT-1794, FEAT-1931, EPIC-2196]
blocks:
- FEAT-2102
labels:
  - fsm
  - harness
  - hitl
  - extension
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

## Current Behavior

The FSM executor currently has no abstraction layer for human-in-the-loop (HITL)
communication channels. Any `human_approval` state would need transport-specific
I/O hardcoded directly in `executor.py` — there is no adapter protocol, no
extension-based discovery, and no config-driven channel selection.

## Expected Behavior

1. A `CommunicationAdapter` abstract class / protocol defining:
   - `send_alert(loop_name, state_name, prompt, captured_context, timeout) → alert_id`
   - `await_response(alert_id, timeout) → HumanResponse | TimeoutResponse`
   - `supports_async() → bool` — whether the channel can reach an operator who
     isn't watching the terminal
2. Adapters register via the extension system through a new
   `CommunicationAdapterExtension` Protocol (decided 2026-06-12 — see
   Decision Rationale in Proposed Solution).
3. Config-driven channel selection: `.ll/ll-config.json` key `hitl.channel`
   selects the active adapter (default: `terminal`).
4. The FSM executor resolves the configured adapter and calls the protocol
   methods — it never imports a specific adapter directly.

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

- [ ] `CommunicationAdapter` abstract interface defined with `send_alert()`,
  `await_response()`, and `supports_async()`
- [ ] Extension registration path established (adapter discovery via
  `wire_extensions()` or equivalent)
- [ ] Config schema: `hitl.channel` in `.ll/ll-config.json` selects active
  adapter; falls back to `terminal` if unset
- [ ] FSM executor resolves adapter via config + extension registry, not
  hardcoded import
- [ ] `ll-loop validate` warns when `hitl.channel` is unset and host is
  non-interactive (no adapter can reach the operator)
- [ ] Tests: mock adapter implementation, verify executor calls protocol methods
  not transport-specific code

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

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class HumanResponse:
    approved: bool
    reason: Optional[str] = None
    modified_prompt: Optional[str] = None

@dataclass
class TimeoutResponse:
    timed_out: bool = True
    elapsed_seconds: float = 0.0

class CommunicationAdapter:
    """Abstract protocol for async HITL communication channels."""

    def send_alert(
        self,
        loop_name: str,
        state_name: str,
        prompt: str,
        captured_context: dict,
        timeout: float,
    ) -> str:
        """Deliver an approval request to the operator. Returns alert_id."""
        ...

    def await_response(
        self, alert_id: str, timeout: float
    ) -> HumanResponse | TimeoutResponse:
        """Block until the operator responds or timeout expires."""
        ...

    def supports_async(self) -> bool:
        """True if this channel can reach an operator not watching the terminal."""
        ...
```

Extension registration (via the new `CommunicationAdapterExtension` — see
Decision Rationale):

```python
class TerminalAdapter(CommunicationAdapter):
    ...

class TerminalAdapterExtension(CommunicationAdapterExtension):
    def provided_adapters(self) -> list[type[CommunicationAdapter]]:
        return [TerminalAdapter]
```

## Integration Map

### Files to Create
- `scripts/little_loops/fsm/communication_adapter.py` — `CommunicationAdapter`
  abstract class, `HumanResponse` / `TimeoutResponse` dataclasses
- `scripts/tests/test_communication_adapter.py` — mock adapter, protocol contract
  tests

### Files to Modify
- `scripts/little_loops/extension.py:81` — either extend
  `ActionProviderExtension` or add new `CommunicationAdapterExtension`
- `scripts/little_loops/extension.py:246` — `wire_extensions()`: wire adapters
  into executor
- `scripts/little_loops/fsm/executor.py` — resolve adapter from config +
  registry
- `.ll/ll-config.json` schema — add `hitl.channel` key

### Similar Patterns
- `transport.py:115` — `UnixSocketTransport._accept_loop()`: transport
  abstraction with timeout
- `extension.py:81` — `ActionProviderExtension.provided_actions()`: extension
  registration pattern
- `host_runner.py:74` — `HostCapabilities`: capability detection pattern

## Implementation Steps

1. Define `CommunicationAdapter` abstract class with `send_alert()`,
   `await_response()`, and `supports_async()` in a new
   `scripts/little_loops/fsm/communication_adapter.py`
2. Add adapter registration to the extension system — create a new
   `CommunicationAdapterExtension` Protocol with `provided_adapters()` in
   `extension.py` (decided; see Decision Rationale)
3. Wire adapter discovery into `wire_extensions()` so the executor can
   resolve registered adapters
4. Update FSM executor in `executor.py` to resolve the configured adapter
   from config + registry and call protocol methods (never a direct import)
5. Add `hitl.channel` key to `.ll/ll-config.json` schema with `terminal`
   default
6. Add `ll-loop validate` warning when `hitl.channel` is unset on a
   non-interactive host
7. Write protocol contract tests with a mock adapter implementation,
   verifying the executor calls protocol methods not transport-specific code

## Impact

- **Priority**: P2 — prerequisite for FEAT-1794, FEAT-1931, and the EventBus adapter
- **Effort**: Small — abstract class, registration hook, config key
- **Risk**: Low — no user-facing change until adapters are implemented
- **Breaking Change**: No

---

## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

2026-06-18 (UNSTARTED): `scripts/little_loops/fsm/communication_adapter.py` does not exist. No `CommunicationAdapterExtension` in `extension.py`. No `hitl.channel` config key. FEAT-1794, FEAT-1931, FEAT-1932 remain correctly blocked on this issue. Dependency graph is accurate.

## Status

open

## Session Log
- `/ll:verify-issues` - 2026-06-13T21:14:14 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:decide-issue` - 2026-06-12T16:30:50 - `5f156fda-1001-478e-926c-73ffddf7e4b1.jsonl`
- `/ll:format-issue` - 2026-06-05T22:16:53 - `8041e61d-a9eb-4655-91d2-d32792836de3.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
