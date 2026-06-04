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
relates_to: [FEAT-1794, FEAT-1931, FEAT-1932]
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

This is the **foundational child** of EPIC-1929. FEAT-1794 (FSM state), FEAT-1931
(terminal adapter), and FEAT-1932 (PushNotification adapter) all depend on this
interface being stabilized first.

## Expected Behavior

1. A `CommunicationAdapter` abstract class / protocol defining:
   - `send_alert(loop_name, state_name, prompt, captured_context, timeout) → alert_id`
   - `await_response(alert_id, timeout) → HumanResponse | TimeoutResponse`
   - `supports_async() → bool` — whether the channel can reach an operator who
     isn't watching the terminal
2. Adapters register via the extension system (either extending
   `ActionProviderExtension` or a new `CommunicationAdapterExtension`).
3. Config-driven channel selection: `.ll/ll-config.json` key `hitl.channel`
   selects the active adapter (default: `terminal`).
4. The FSM executor resolves the configured adapter and calls the protocol
   methods — it never imports a specific adapter directly.

## Motivation

Without this protocol, the `human_approval` state type would hardcode transport
logic in `executor.py` — terminal `input()` today, ripped out and replaced with
push tomorrow, Slack the day after. An adapter protocol is a one-time abstraction
cost that pays back every time a new channel is added.

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
`provided_adapters()`) vs. create a new `CommunicationAdapterExtension`. The
former reuses the existing contributed-action dispatch in `_run_action()`; the
latter is cleaner separation. Resolve during refinement.

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

## Impact

- **Priority**: P2 — prerequisite for FEAT-1794, FEAT-1931, FEAT-1932
- **Effort**: Small — abstract class, registration hook, config key
- **Risk**: Low — no user-facing change until adapters are implemented
- **Breaking Change**: No

---
## Status

open
