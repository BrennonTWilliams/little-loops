---
id: FEAT-1931
title: Terminal adapter for async HITL communication
type: FEAT
priority: P2
captured_at: "2026-06-04T00:00:00Z"
discovered_date: 2026-06-04
discovered_by: scope-epic
status: open
parent: EPIC-1929
relates_to: [FEAT-1930, FEAT-1794, FEAT-1932]
labels:
  - fsm
  - harness
  - hitl
  - adapter
---

# FEAT-1931: Terminal adapter for async HITL communication

## Summary

Implement the `CommunicationAdapter` protocol (FEAT-1930) for stdin/stdout.
This is the synchronous, interactive channel: the FSM prints a formatted prompt
to the terminal, blocks on `input()`, parses the verdict, and returns it.

The terminal adapter is the default channel (always available, zero config) and
the dev/debug fallback when richer adapters aren't configured.

## Expected Behavior

1. Implements `CommunicationAdapter.send_alert()`: renders the prompt + captured
   context to stdout with clear formatting (state name, timeout remaining, valid
   responses).
2. Implements `CommunicationAdapter.await_response()`: blocks on stdin (respecting
   the FSM's shutdown signal via existing `_interruptible_sleep()` pattern),
   parses `approve`/`reject`/`edit` (with flexible matching: `y`/`yes`/`approve`,
   `n`/`no`/`reject`, `e`/`edit`), returns a `HumanResponse`.
3. On timeout (no input within deadline), returns `TimeoutResponse`.
4. `supports_async()` returns `False` — the operator must be present at the
   terminal.

## Motivation

The terminal adapter serves three roles:
- **Default channel**: works out of the box with zero configuration
- **Dev/debug channel**: when iterating on a loop, the operator is at the
  terminal anyway
- **Protocol validation**: the simplest possible implementation proves the
  `CommunicationAdapter` interface is sufficient before building the more
  complex PushNotification adapter

## Acceptance Criteria

- [ ] Implements `CommunicationAdapter` protocol
- [ ] Formatted prompt output includes: state name, prompt text, captured
  context, timeout countdown (or deadline), valid response keys
- [ ] Accepts `y`/`yes`/`approve`, `n`/`no`/`reject`, `e`/`edit` (case-
  insensitive, unambiguous prefix matching)
- [ ] Edit verdict captures the edited text from a secondary input prompt
- [ ] Respects FSM shutdown signal during blocking input (doesn't hang on ^C)
- [ ] Timeout returns `TimeoutResponse` (not `HumanResponse`)
- [ ] `supports_async()` returns `False`
- [ ] Tests: mock stdin/stdout, verify prompt format, verdict parsing, timeout

## Proposed Solution

Wrap `input()` in an `_interruptible_sleep()`-style polling loop (existing
pattern at `executor.py:1647`) that checks the shutdown signal between reads.
Use `sys.stdin` directly rather than `input()` for finer control over blocking
and signal handling.

Format the prompt using the existing `${captured.<state>.<field>}` interpolation
from the FSM context — the adapter receives pre-interpolated text from the FSM
state, so it only needs to render, not resolve variables.

## Integration Map

### Files to Create
- `scripts/little_loops/fsm/adapters/terminal_adapter.py` —
  `TerminalAdapter(CommunicationAdapter)`
- `scripts/tests/test_terminal_adapter.py`

### Files to Modify
- `scripts/little_loops/extension.py` — register `TerminalAdapter` as default
  adapter
- `scripts/little_loops/fsm/executor.py` — no changes (uses protocol interface)

### Similar Patterns
- `executor.py:1647` — `_interruptible_sleep()`: polling-with-shutdown-signal
  pattern
- `transport.py:115` — `UnixSocketTransport`: blocking I/O with timeout

## Impact

- **Priority**: P2 — default channel, required for FEAT-1794 to function
- **Effort**: Small — single adapter implementation, ~100-150 lines
- **Risk**: Low — well-understood I/O pattern
- **Breaking Change**: No

---
## Status

open
