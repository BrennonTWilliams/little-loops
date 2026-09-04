# Spike Plan: FEAT-1931 (terminal-hitl-adapter)

## Context

FEAT-1931 has no `## Confidence Check Notes` → `### Outcome Risk Factors`
section yet, so this spike's scope was derived by standalone analysis of the
issue's `## Proposed Solution` (per `/ll:spike` Phase 2 step 3) and confirmed
interactively with the user.

The issue's Proposed Solution flags one unprecedented mechanism verbatim:

> ⚠ Unproven mechanism — no site combines selectors-bounded read with
> shutdown-flag polling. No existing call site in the codebase exercises
> "selectors-bounded read on a file object" together with "shutdown-flag
> polling" — the combination this issue's Proposed Solution assumes works has
> no confirming precedent.

Both canonical low-confidence drivers apply: **(a)** zero precedent —
`mcp_call.py:101-124` and `fsm/runners.py:284-349` use
`selectors.DefaultSelector()` bounded reads but never check
`_shutdown_requested` inside the loop; `_interruptible_sleep()`
(`executor.py:3856`) checks `_shutdown_requested` but only wraps
`time.sleep()`, which has no analogue for a blocking `sys.stdin` read.
**(b)** no test exercises the combined core — `test_fsm_runners.py:185-223`
(`TestSimulationActionRunnerPromptResult`) mocks blocking stdin but never
combines it with a timeout-bounded selector loop or shutdown polling.

A later verification note (2026-09-04) narrows but does not resolve this:
`await_response(alert_id, timeout)` is documented as re-entrant — "the
executor polls this in short ticks so shutdown stays responsive" — meaning
FEAT-1794's future caller may invoke `await_response()` repeatedly with short
per-call timeouts and do its own shutdown-checking between calls. If so,
`TerminalAdapter` might only need a single bounded selectors read per call,
with no internal shutdown-flag polling at all. The user selected **both
variants** be proven: (1) the combined mechanism as originally scoped, and
(2) the simpler contract-compliant shape that omits internal polling and
relies on the re-entrant short-timeout contract instead.

## Approach

Build an isolated `TerminalAwaiter` class (not the real `TerminalAdapter` —
that stays FEAT-1931's implementation, out of scope here) that exercises two
`await_response`-shaped methods against a **real** `sys.stdin`-like pipe (an
`os.pipe()` file object, not `StringIO`, since `StringIO` doesn't block and
can't prove selector-readiness semantics):

- `await_line_polling(timeout, shutdown_event)` — the combined mechanism:
  `selectors.DefaultSelector()` bounded read loop with `shutdown_event.is_set()`
  checked each iteration (mirrors `mcp_call.py`'s deadline loop, adds the
  `_interruptible_sleep()`-style flag check).
- `await_line_single_read(timeout)` — the simpler shape: one
  `sel.select(timeout=timeout)` bounded read, no internal shutdown check,
  proving it's safe for a caller to satisfy the re-entrant contract by
  calling this repeatedly with short timeouts itself.

A real `threading.Event` stands in for `FSMExecutor._shutdown_requested`
(a plain bool flag in the real class) — equivalent semantics, thread-safe for
the test that flips it from a background thread mid-block. A real
`os.pipe()` stands in for `sys.stdin` — selectors requires a real
file-descriptor-backed object; mocking would not prove the mechanism.

## Critical files

Read-only references (production contracts this spike must honor, not
modify):
- `scripts/little_loops/fsm/executor.py:3856` — `_interruptible_sleep()`
  (shutdown-flag polling pattern)
- `scripts/little_loops/mcp_call.py:101-124` — `_send_request()`
  (selectors-bounded read pattern)
- `scripts/little_loops/fsm/runners.py:284-349` — second selectors-bounded
  read instance
- `scripts/little_loops/fsm/communication_adapter.py` — `CommunicationAdapter`
  ABC, `AdapterResponse`/`TimeoutResponse`, `await_response()`'s re-entrancy
  docstring

New spike paths (this skill writes only here):
- `scripts/tests/spike/terminal_hitl_await/__init__.py`
- `scripts/tests/spike/terminal_hitl_await/awaiter.py`
- `scripts/tests/spike/terminal_hitl_await/test_awaiter.py`

## Implementation

```
scripts/tests/spike/terminal_hitl_await/
├── __init__.py
├── awaiter.py               # TerminalAwaiter: both candidate mechanisms
└── test_awaiter.py          # AC test class
```

```python
# awaiter.py
class TerminalAwaiter:
    """Isolated proof of two candidate await-with-timeout shapes for a
    terminal HITL adapter. Not the real TerminalAdapter — proves the I/O
    core only."""

    def __init__(self, stream: IO[str]) -> None: ...

    def await_line_polling(
        self, timeout: float, shutdown_event: threading.Event
    ) -> str | None:
        """Combined mechanism: selectors-bounded read + shutdown-flag
        polling in one call. Returns the line, or None on timeout/shutdown."""

    def await_line_single_read(self, timeout: float) -> str | None:
        """Simpler mechanism: one bounded selectors read, no internal
        shutdown check. Returns the line, or None on timeout."""
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_polling_returns_line_when_available_before_timeout` | Risk: combined mechanism correctness (happy path) | behavior |
| `test_polling_returns_none_on_pure_timeout_no_shutdown` | Risk: combined mechanism doesn't false-positive on shutdown | behavior |
| `test_polling_exits_promptly_on_shutdown_signal_mid_block` | Risk (a): unprecedented combination — proves shutdown flag flipped from another thread interrupts a blocking selectors read within one tick, not just at the next `await_response()` call | behavior |
| `test_single_read_returns_line_when_available_before_timeout` | Risk: contract-compliant simpler shape, happy path | behavior |
| `test_single_read_returns_none_on_timeout` | Risk: simpler shape respects its bound, doesn't hang | behavior |
| `test_repeated_short_timeout_calls_satisfy_reentrant_contract` | Verifies the re-entrant contract from `communication_adapter.py`'s `await_response()` docstring: calling `await_line_single_read()` in a loop with short timeouts, checking a shutdown flag between calls, achieves the same responsiveness as the combined mechanism — without internal polling | behavior |
| `test_spike_does_not_import_production_adapter_modules` | isolation guard — AST sniff: no import of `little_loops.fsm.adapters.terminal_adapter` or `little_loops.fsm.executor` | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/terminal_hitl_await/ -v
python -m pytest scripts/tests/test_fsm_runners.py -v
python -m pytest scripts/tests/test_extension.py -v
```

The regression suites confirm the spike didn't need to touch (and doesn't
break) the two files it draws its precedent from — `test_fsm_runners.py`
covers the selectors/stdin-mocking precedent's own suite, `test_extension.py`
covers the extension-registration convention `TerminalAdapterExtension` will
later follow.

## Out of Scope

- The real `TerminalAdapter` class, `TerminalAdapterExtension`, prompt
  formatting/rendering, verdict parsing (y/yes/approve etc.), edit-verdict
  secondary prompt, and `pyproject.toml` entry-point registration — all
  FEAT-1931 implementation, not this spike.
- `rich`/`questionary` API proving — separately flagged via
  `learning_tests_required` in FEAT-1931's frontmatter; that's
  `/ll:explore-api` territory, not an internal mechanism.
- Deciding which of the two mechanisms FEAT-1931 should ship — this spike
  proves both work in isolation; the choice belongs to the implementer once
  FEAT-1794's actual calling pattern (single long block vs. repeated
  short-timeout calls) is confirmed.

## Promotion

On acceptance, promotable code moves from
`scripts/tests/spike/terminal_hitl_await/` to
`scripts/little_loops/spike/terminal_hitl_await/` in a separate PR — but
because this spike's purpose is mechanism selection rather than reusable
production code, the more likely outcome is the implementer copies whichever
proven shape (`await_line_polling` or `await_line_single_read`) directly into
`TerminalAdapter.await_response()` in FEAT-1931's real implementation, and
this spike package is left as reference / deleted per this issue's own
`## Spike Results` write-up.
