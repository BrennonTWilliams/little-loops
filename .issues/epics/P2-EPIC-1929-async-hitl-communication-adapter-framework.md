---
id: EPIC-1929
title: Async HITL Communication Adapter Framework
type: EPIC
priority: P2
captured_at: "2026-06-04T00:00:00Z"
discovered_date: 2026-06-04
discovered_by: scope-epic
status: open
parent: null
relates_to: [FEAT-1794, FEAT-1545, FEAT-1613]
---

# EPIC-1929: Async HITL Communication Adapter Framework

## Summary

Build an adapter-based communication layer that decouples the FSM `human_approval`
state from transport-specific I/O, then implement that state and its first two
adapters. The FSM asks "approve this?" and blocks for a response; the adapter
decides whether the operator sees that prompt in their terminal, on their phone,
or in Slack.

FEAT-1794 identified the gap correctly — we need a `human_approval` FSM state type
that pauses execution, surfaces a prompt, waits for a human verdict, and routes
accordingly. But the *transport* is not an implementation detail of the state
type. It's a separate axis of variation: terminal, PushNotification, Slack,
Telegram, webhook callback — each with different delivery semantics, response
latency, and auth. An adapter protocol lets the FSM treat them uniformly and lets
new channels be added without touching the executor.

## Motivation

- **FEAT-1794's v1 "terminal only" path creates a refactor tax.** If
  `_execute_human_approval_state()` hardcodes `input()` / terminal rendering,
  adding PushNotification or Slack later requires either ripping out that code or
  bolting on a channel switch inside the executor. An adapter protocol designed
  first avoids both.
- **The event bus already has a transport abstraction** (`transport.py`:
  `UnixSocketTransport`, `WebhookTransport`). The communication adapter protocol
  is the same idea applied one layer up — the FSM doesn't know or care which
  channel delivered the verdict, only that a verdict arrived.
- **Unattended HITL is the whole point.** A `human_approval` state that requires
  the operator to be watching the terminal is just `input()` with extra steps.
  The PushNotification adapter — where the FSM blocks, the operator gets paged,
  and a callback resumes execution — is what makes this a real HITL primitive.
- **FEAT-1545 and FEAT-1613** (hitl-compare, hitl-md) are existing HITL loops
  that run interactively in the terminal. They predate the adapter concept and
  would benefit from it — a hitl-md review surfaced via PushNotification while
  the operator is away from their desk.

## Goal

When this epic is done:
- A `CommunicationAdapter` protocol exists, registered through the extension
  system, with a config-driven channel selector.
- `action_type: human_approval` states in loop YAML route through the adapter
  protocol — the FSM executor calls `adapter.send_alert()` and
  `adapter.await_response()` without knowing which channel is in use.
- The terminal adapter works as the dev/debug/fallback channel (synchronous
  `input()`-style, but behind the protocol).
- The PushNotification adapter delivers alerts to the operator's phone and
  accepts approve/reject/edit responses via a callback path, enabling truly
  unattended HITL.
- FEAT-1794's FSM state type is implemented against the protocol, not against
  any specific transport.

## Scope

### In scope

- **Adapter protocol** (`CommunicationAdapter` abstract interface): `send_alert()`
  for outbound prompt + context delivery, `await_response()` for inbound verdict
  collection with timeout, registration via the extension system
  (`ActionProviderExtension` or a new `CommunicationAdapterExtension`).
- **`human_approval` FSM state type** (FEAT-1794): schema, executor dispatch,
  prompt interpolation, timeout handling, verdict routing (`on_yes`/`on_no`/
  `on_edit`/`on_timeout`), event emission — implemented against the adapter
  protocol, not hardcoded to any transport.
- **Terminal adapter**: stdin/stdout implementation of the protocol. Synchronous
  blocking with formatted prompt output. Serves as the dev fallback and the
  default when no other adapter is configured.
- **PushNotification adapter**: implementation using the `PushNotification` tool
  for outbound delivery, with a response callback mechanism (event bus subscribe
  or file-poller) for inbound verdict. This is the first truly async channel and
  the one that validates the protocol design.
- **Config and host integration**: channel selection in `.ll/ll-config.json`
  (`hitl.channel`), headless-host detection (no adapter configured + non-
  interactive → loud warning or safe default), `ll-loop validate` warnings for
  unattended-context timeouts.

### Out of scope

- Slack, Telegram, email, or webhook adapters — these are natural follow-ons
  once the protocol is validated, but designing the protocol for exactly two
  implementations (terminal + push) is sufficient to prove the abstraction.
- Multi-user approval quorums — the protocol models one-prompt → one-response.
- Replacing the existing hitl-compare / hitl-md loops (FEAT-1545, FEAT-1613)
  to use the adapter protocol — those are done and stable; retrofitting is a
  separate decision.

## Children

- **FEAT-1930** — Communication adapter protocol: abstract interface, extension
  registration, config schema, channel selection
- **FEAT-1794** (existing, reparented) — `human_approval` FSM state type:
  schema, executor dispatch, timeout/verdict routing, event emission
- **FEAT-1931** — Terminal adapter: stdin/stdout `CommunicationAdapter`
  implementation
- **FEAT-1932** — PushNotification adapter: push-based `CommunicationAdapter`
  with response callback

## Dependency Order

```
FEAT-1930 (protocol)
    ├── FEAT-1794 (FSM state — depends on protocol interface)
    ├── FEAT-1931 (terminal adapter — implements protocol)
    └── FEAT-1932 (push adapter — implements protocol)
```

FEAT-1930 must be designed first (or at least its interface stabilized) so
FEAT-1794, FEAT-1931, and FEAT-1932 can be built against it. The three
implementation children can then proceed in parallel.

## Open Questions

1. Should the adapter protocol extend the existing `ActionProviderExtension`
   (`extension.py:81`) or be a new `CommunicationAdapterExtension`? The former
   reuses the contributed-action dispatch; the latter is cleaner separation but
   adds a new extension type.
2. Response callback mechanism for PushNotification: event bus subscribe
   (`EventBus.register()` with a `human_response` event type) vs. file-poller
   (write response to `.ll/hitl-responses/<id>.json`, poll in
   `_interruptible_sleep()` loop)? Event bus is architecturally cleaner; file
   poller is simpler and works cross-host.
3. Should the terminal adapter be the default when no channel is configured, or
   should the system require explicit opt-in? Default-terminal is forgiving;
   require-explicit prevents surprise blocking in unattended contexts.
4. Does the protocol need a `supports_async()` capability flag so the FSM can
   decide whether to warn about unattended timeouts? Terminal is sync (operator
   must be present), PushNotification is async (operator can respond later).

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | Target for HITL phase documentation |
| `.claude/CLAUDE.md` § Loop Authoring (MR-1) | `human_approval` qualifies as non-LLM evaluator |
| `docs/ARCHITECTURE.md` | Event bus + extension system this hooks into |
| `scripts/little_loops/transport.py` | Existing transport abstraction — pattern to follow |
| `scripts/little_loops/extension.py` | Extension protocol — registration path for adapters |

## Verification Notes

Acceptance gates:
- `ll-loop validate` passes on a loop containing `action_type: human_approval`
  with the terminal adapter configured.
- `ll-loop validate` passes on the same loop with the PushNotification adapter
  configured.
- Switching adapters is a config change, not a loop YAML change — the same loop
  works with either channel.
- A `human_approval` state with no timeout + non-interactive host + no async
  adapter configured produces a validation warning.
- The protocol interface is documented and a third-party adapter can be written
  against it without touching `executor.py`.

---
## Status

open

## Session Log
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
