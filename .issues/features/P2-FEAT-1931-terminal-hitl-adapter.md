---
id: FEAT-1931
title: Terminal adapter for async HITL communication
type: FEAT
priority: P2
captured_at: "2026-06-04T00:00:00Z"
discovered_date: 2026-06-04
discovered_by: scope-epic
status: blocked
blocked_by: [FEAT-1930]
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

## Current Behavior

The FSM executor currently runs loops without a human-in-the-loop (HITL)
communication channel. While the `CommunicationAdapter` protocol is defined
(FEAT-1930), no stdin/stdout implementation exists for interactive
terminal-based operator approval. The system has no way to pause execution
and prompt a terminal operator for decisions — loops that encounter states
requiring human judgment have no mechanism to request it.

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

## Use Case

**Who**: A developer iterating on an FSM loop configuration locally

**Context**: The developer is tuning a loop's approval gate and wants to
observe each decision point interactively. The loop encounters a state that
requires human judgment — no automated predicate can decide correctly.

**Goal**: The FSM prints a formatted prompt to the terminal showing the
current state, context, available responses, and timeout. The developer
reads the prompt, decides, and types `approve`, `reject`, or `edit` (with
unambiguous prefix matching).

**Outcome**: The FSM receives a parsed `HumanResponse` (approve/reject) or
`EditResponse` (with edited text), and continues execution. On timeout with
no input, the FSM receives a `TimeoutResponse` and follows its configured
timeout route.

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

## API/Interface

```python
class TerminalAdapter(CommunicationAdapter):
    """Stdin/stdout implementation of the HITL communication protocol.

    Synchronous adapter: blocks the FSM on input() until a response is
    received or timeout expires. Always available with zero configuration.
    """

    def send_alert(
        self,
        loop_name: str,
        state_name: str,
        prompt: str,
        captured_context: dict,
        timeout: float,
    ) -> str:
        """Render formatted prompt + context to stdout."""

    def await_response(self, timeout: float) -> HumanResponse | TimeoutResponse:
        """Block on stdin with shutdown-signal awareness, parse verdict."""

    def supports_async(self) -> bool:
        """Terminal adapter is synchronous — operator must be present."""
        return False
```

The adapter receives pre-interpolated prompt text from the FSM state; it
only renders, not resolves, variables.

## Proposed Solution

Wrap `input()` in an `_interruptible_sleep()`-style polling loop (see
`_interruptible_sleep()` at `scripts/little_loops/fsm/executor.py:1955`) that checks the shutdown signal between reads.
Use `sys.stdin` directly rather than `input()` for finer control over blocking
and signal handling.

Format the prompt using the existing `${captured.<state>.<field>}` interpolation
from the FSM context — the adapter receives pre-interpolated text from the FSM
state, so it only needs to render, not resolve variables.

## Implementation Steps

1. Study the `CommunicationAdapter` protocol definition (FEAT-1930) and the
   `_interruptible_sleep()` polling pattern in `executor.py`
2. Implement `TerminalAdapter` class with `send_alert()`, `await_response()`,
   and `supports_async()` methods
3. Implement formatted prompt rendering: state name, prompt text, captured
   context, timeout countdown, valid response keys
4. Implement stdin reading loop using `sys.stdin` with shutdown-signal-aware
   polling (check shutdown event between reads)
5. Implement verdict parsing: case-insensitive unambiguous prefix matching
   for `approve`/`y`/`yes`, `reject`/`n`/`no`, `edit`/`e`
6. Implement edit verdict: prompt for edited text on secondary input, return
   `EditResponse` with captured text
7. Register `TerminalAdapter` as default adapter in `extension.py`
8. Write tests: mock stdin/stdout, verify prompt format, verdict parsing
   (approve/reject/edit), timeout handling, shutdown signal behavior

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
- `executor.py` — `_interruptible_sleep()`: polling-with-shutdown-signal
  pattern
- `transport.py` — `UnixSocketTransport`: blocking I/O with timeout

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — will call adapter through
  `CommunicationAdapter` protocol interface (no direct import of
  `TerminalAdapter` needed)
- `scripts/little_loops/extension.py` — will import and register
  `TerminalAdapter`

### Tests
- `scripts/tests/test_terminal_adapter.py` — new test file (mock stdin/stdout)

### Documentation
- `docs/reference/API.md` — add `TerminalAdapter` entry under FSM adapters

### Configuration
- N/A — terminal adapter is always available with zero configuration

## Impact

- **Priority**: P2 — default channel, required for FEAT-1794 to function
- **Effort**: Small — single adapter implementation, ~100-150 lines
- **Risk**: Low — well-understood I/O pattern
- **Breaking Change**: No

## Related Key Documentation

- [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) — FSM and adapter architecture
- [API.md](../../docs/reference/API.md) — `CommunicationAdapter` protocol reference
- [HOST_COMPATIBILITY.md](../../docs/reference/HOST_COMPATIBILITY.md) — host CLI abstraction layer

---
## Status

open

## Verification Notes (2026-06-05)

- **Line drift**: References `executor.py:1647 _interruptible_sleep` — now at L1735 (drift +88).
- Proposed file `scripts/little_loops/fsm/adapters/terminal_adapter.py` does not exist (expected).
- Created recently; line number from parent EPIC-1929/related FEAT-1794 needs updating.
- **2026-06-13**: `_interruptible_sleep` has drifted further — current location is `executor.py:1766` (verification note said 1735; issue body says 1647). Update the line reference before implementing.

## Verification Notes (2026-06-13)

2026-06-13: Line number drift in executor.py: `_interruptible_sleep` now at :1766 (issue references :1647). Critical pre-implementation fix required: `send_alert()` signature in this issue shows `(prompt, context, timeout)` but FEAT-1930 protocol specifies `(loop_name, state_name, prompt, captured_context, timeout) -> str` — must align before implementation.

2026-06-17: `_interruptible_sleep` has drifted further to :1886 (was :1766). `send_alert()` signature mismatch with FEAT-1930 protocol still unresolved — missing `loop_name`, `state_name` params. `scripts/little_loops/fsm/adapters/terminal_adapter.py` does not exist (expected).

2026-06-19: `_interruptible_sleep` has drifted to :1911 (was :1886). `send_alert()` signature mismatch with FEAT-1930 protocol still unresolved — missing `loop_name`, `state_name` params. `fsm/adapters/terminal_adapter.py` does not exist (expected, blocked on FEAT-1930).

- **2026-06-26** (/ll:verify-issues): Aligned `API/Interface` `send_alert()` to FEAT-1930's ratified protocol `send_alert(loop_name, state_name, prompt, captured_context, timeout) -> str`; corrected `_interruptible_sleep` body reference to `scripts/little_loops/fsm/executor.py:1955`. Baseline (no `fsm/adapters/` yet, blocked on FEAT-1930) unchanged.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): The `API/Interface` section above shows `TerminalAdapter.send_alert(prompt, context, timeout)` but the `CommunicationAdapter` protocol in FEAT-1930 defines `send_alert(loop_name, state_name, prompt, captured_context, timeout) -> None`. Align this issue's `send_alert()` signature with FEAT-1930's protocol **before** implementing — add `loop_name: str` and `state_name: str` as the first two parameters to match the base protocol. This allows the terminal adapter to display the state name in the formatted prompt output without requiring the caller to pre-interpolate it.

## Session Log
- `/ll:verify-issues` - 2026-06-20T00:34:45 - `fe5ace5b-6f94-43ca-9f1d-09a0705f08c4.jsonl`
- `/ll:verify-issues` - 2026-06-18T02:52:53 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:verify-issues` - 2026-06-14T00:12:51 - `dcbaf608-eff5-4e7b-8a64-4d13a266c421.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:57 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:02 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:format-issue` - 2026-06-05T22:19:19 - `4c87a3f2-1298-4938-ae70-4c5f78013645.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`