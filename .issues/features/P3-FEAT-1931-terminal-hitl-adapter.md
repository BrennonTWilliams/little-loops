---
id: FEAT-1931
title: Terminal adapter for async HITL communication
type: FEAT
priority: P3
captured_at: '2026-06-04T00:00:00Z'
discovered_date: 2026-06-04
discovered_by: scope-epic
status: open
parent: EPIC-1929
relates_to:
- FEAT-1930
- FEAT-1794
- FEAT-1932
labels:
- fsm
- harness
- hitl
- adapter
verify_verdict: VALID
decision_needed: true
unproven_mechanism: true
learning_tests_required:
- rich
- questionary
spike_attempted: true
spike_completed: true
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- No shared helper exists in this codebase for case-insensitive prefix matching of free-text confirmation words (y/yes/approve style). The two nearest analogues are exact-string numeric matching (`SimulationActionRunner._prompt_result()`, `fsm/runners.py:530-556`) and LLM-output verdict extraction via regex/keyword search (`output_parsing.py:102-166` `_extract_verdict_from_text()`) — neither does prefix matching of a single free-typed word against a short alias set. This issue's verdict parser is new ground, not an existing pattern to follow.
- The Acceptance Criteria specify accepted inputs (y/yes/approve, n/no/reject, e/edit) but do not specify behavior on unrecognized input — no re-prompt-vs-error decision is stated. `SimulationActionRunner._prompt_result()` (`fsm/runners.py:530-556`) is the nearest precedent and retries on invalid input inside a `while True` loop, but that is not confirmation this issue must do the same — left for the implementer.

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
    ) -> str:
        """Render formatted prompt + context to stdout."""

    def await_response(self, alert_id: str, timeout: float) -> AdapterResponse | TimeoutResponse:
        """Block on stdin with shutdown-signal awareness, parse verdict."""

    def supports_async(self) -> bool:
        """Terminal adapter is synchronous — operator must be present."""
        return False
```

The adapter receives pre-interpolated prompt text from the FSM state; it
only renders, not resolves, variables.

## Program Design

### Types
- No new dataclass/type is introduced by this issue itself — `AdapterResponse`
  and `TimeoutResponse` are FEAT-1930's types (implemented 2026-09-04 in
  `scripts/little_loops/fsm/communication_adapter.py`). The verdict is
  expressed via `AdapterResponse.verdict: Literal["approve", "reject", "edit"]`
  — there is no separate `EditResponse` type.

### Signatures
- `TerminalAdapter.send_alert(self, loop_name: str, state_name: str, prompt: str, captured_context: dict) -> str`
  — no `timeout` parameter; FEAT-1930 Pre-implementation Review #8 moved the
  wait budget to `await_response()`.
- `TerminalAdapter.await_response(self, alert_id: str, timeout: float) -> AdapterResponse | TimeoutResponse` —
  matches FEAT-1930's base protocol (`communication_adapter.py`), which
  defines `await_response(self, alert_id: str, timeout: float)`, re-entrant
  per `alert_id`.
- `TerminalAdapter.supports_async(self) -> bool` — returns `False`

### Call Path
`FSMExecutor._execute_state()` (`executor.py:1948`) → (once FEAT-1794 adds a
`human_approval` dispatch branch structurally mirroring the existing
`state.type == "learning"` branch at `:1973-1974`) → adapter resolved via
`FSMExecutor.resolve_communication_adapter()` (implemented, `executor.py`;
reads `_contributed_adapters`, itself populated by `wire_extensions()` from a
`CommunicationAdapterExtension.provided_adapters()`) →
`TerminalAdapter.send_alert(...)` → `TerminalAdapter.await_response(...)`.
`self.fsm.name` (loop_name) and `self.current_state`/`ctx.state_name`
(state_name) are both available at the `_execute_state` call site, confirming
those two protocol fields are satisfiable without new executor plumbing. No
`prompt` field exists yet on `StateConfig` (`fsm/schema.py`) — sourcing
`prompt`/`captured_context` at the call site is FEAT-1794's gap, not this
issue's.

### Decision Rules
- **Accepted verdict keywords** (from Acceptance Criteria): `y`/`yes`/`approve` → approve,
  `n`/`no`/`reject` → reject, `e`/`edit` → edit. Case-insensitive, unambiguous
  prefix matching (the three aliases start with distinct letters, so no
  collision is possible under prefix matching).
- **Escape hatch on unrecognized input**: not specified by this issue's
  Acceptance Criteria or Proposed Solution — left to the implementer. See the
  Codebase Research Findings under Acceptance Criteria for the nearest
  precedent (retry-loop behavior in `SimulationActionRunner._prompt_result()`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

- **`_interruptible_sleep()` (`executor.py:3856`) is not reusable as-is by a standalone adapter**: it is a bound method reading `self._shutdown_requested` (an `FSMExecutor` instance attribute), not a free function — a `TerminalAdapter` class cannot call it without either being handed the executor instance, an extracted free-function equivalent, or duplicating the loop. It also only wraps `time.sleep()` ticks; it has no mechanism for interrupting a blocking `sys.stdin` read.
- **`await_response()`'s re-entrancy contract, exact docstring** (`communication_adapter.py`): "Block up to `timeout` seconds for the operator's verdict on `alert_id`. Re-entrant per alert: the executor polls this in short ticks so shutdown stays responsive. Repeat calls for the same `alert_id` are expected; a verdict that arrives between calls must be retained and returned on the next call. A `TimeoutResponse` does not invalidate the alert — only `cancel_alert()` does." This means an adapter is not contractually required to internally combine a selectors-bounded read with shutdown-flag polling in one blocking call (the combination the Proposed Solution's `⚠ Unproven mechanism` finding says has no precedent) — it only needs to honor one bounded `timeout` per call and retain any verdict arriving outside that window for the next call. This narrows, but does not resolve, `unproven_mechanism` (only `/ll:spike` resolves it).

## Proposed Solution

Wrap `input()` in an `_interruptible_sleep()`-style polling loop (see
`_interruptible_sleep()` at `scripts/little_loops/fsm/executor.py:3378`) that checks the shutdown signal between reads.
Use `sys.stdin` directly rather than `input()` for finer control over blocking
and signal handling.

Format the prompt using the existing `${captured.<state>.<field>}` interpolation
from the FSM context — the adapter receives pre-interpolated text from the FSM
state, so it only needs to render, not resolve variables.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- **No existing technique combines the two mechanisms this issue's polling approach depends on.** `_interruptible_sleep()` (`executor.py:3833`) checks `self._shutdown_requested` between 100ms `time.sleep()` ticks — but that only works because `time.sleep()` naturally returns control every tick; a blocking `sys.stdin` read has no such checkpoint. The codebase's only bounded-timeout blocking-read technique (`selectors.DefaultSelector()` + `sel.select(timeout=...)`, used in `mcp_call.py:101-124` and `fsm/runners.py:284-349`) never checks `_shutdown_requested` inside its loop. No existing call site in the codebase exercises "selectors-bounded read on a file object" together with "shutdown-flag polling" — the combination this issue's Proposed Solution assumes works has no confirming precedent. ⚠ Unproven mechanism — no site combines selectors-bounded read with shutdown-flag polling
- **Extension registration approach in Proposed Solution/Implementation Steps needs updating**: see the correction under Integration Map above — there is no "register as default adapter in extension.py" mechanism; the ratified path is a `TerminalAdapterExtension(CommunicationAdapterExtension)` implementing `provided_adapters()`.
- **Terminal output formatting has two unreconciled existing conventions in this codebase — an implementer decision, not resolved by precedent:**

**Option A**: Follow `scripts/little_loops/cli/output.py`'s convention — raw ANSI-escape `colorize()` plus `status_block()`/`table()` pure string-returning helpers (used by ~80 existing call sites for structured terminal output, e.g. `cli/harness.py:763-771`). Color gated on `NO_COLOR`/`FORCE_COLOR` env vars and `sys.stdout.isatty()`.

**Option B**: Follow `scripts/little_loops/init/tui.py`'s convention — the third-party `rich` library's `console.print()` with `[color]...[/color]` markup, paired with `questionary` for confirmation prompts (`questionary.confirm(...).ask()` returning `bool | None`).

No recommendation from research — both conventions are actively used elsewhere in the codebase for different subsystems (general CLI output vs. the init wizard specifically), and neither is deprecated relative to the other.

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

- **`await_response()` re-entrancy contract narrows the "unproven mechanism" concern** (see `## Program Design` → Codebase Research Findings for the full docstring): the protocol does not require an adapter to internally combine a selectors-bounded stdin read with shutdown-flag polling in one call — the executor is expected to call `await_response()` repeatedly with short per-call timeouts. This does not clear `unproven_mechanism: true` (that requires `/ll:spike`), but the implementer should re-derive the simplest viable `await_response()` shape from this contract before assuming the selectors+shutdown-polling combination is required.

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
   > ⚠ Superseded — no such mechanism exists; see § Codebase Research Findings under Integration Map
8. Write tests: mock stdin/stdout, verify prompt format, verdict parsing
   (approve/reject/edit), timeout handling, shutdown signal behavior
9. `TerminalAdapterExtension.provided_adapters()` returns a dict keyed exactly
   `{"terminal": TerminalAdapter()}` (matching `HitlConfig.channel`'s default),
   registered under `[project.entry-points."little_loops.extensions"]` in
   `scripts/pyproject.toml` — this is what makes the channel resolve with zero
   user configuration; see § Codebase Research Findings under Integration Map

## Integration Map

### Files to Create
- `scripts/little_loops/fsm/adapters/terminal_adapter.py` —
  `TerminalAdapter(CommunicationAdapter)`
- `scripts/tests/test_terminal_adapter.py`

### Files to Modify
- `scripts/little_loops/extension.py` — register `TerminalAdapter` as default
  adapter
  > ⚠ Superseded — no such mechanism exists; see § Codebase Research Findings below
- `scripts/little_loops/fsm/executor.py` — no changes (uses protocol interface)
- `scripts/pyproject.toml` — add `TerminalAdapterExtension` under
  `[project.entry-points."little_loops.extensions"]` (`:131-134`, currently
  empty); this is the actual zero-config registration mechanism — see
  § Codebase Research Findings below

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- **`transport.py` path correction**: the "Similar Patterns" entry names `transport.py` implying `fsm/transport.py`; the real file is top-level `scripts/little_loops/transport.py` (`UnixSocketTransport` at `:133`). No `fsm/transport.py` exists.
- **`extension.py` registration mechanism does not exist as described**: `grep -rn "class CommunicationAdapter" scripts/little_loops/` returns zero matches — the protocol FEAT-1930 defines is prose-only. The ratified registration shape (`.ll/decisions.yaml`, entry `ARCHITECTURE-027`) is a `CommunicationAdapterExtension` Protocol with `provided_adapters() -> list[type[CommunicationAdapter]]`, hasattr-gated in `wire_extensions()` (`extension.py:201`) exactly like the four existing capability Protocols (`ActionProviderExtension`, `EvaluatorProviderExtension`, `InterceptorExtension`, `LLHookIntentExtension` — `extension.py:38-132`, wired at `:246-273`). This issue would need to ship its own `TerminalAdapterExtension(CommunicationAdapterExtension)` returning `[TerminalAdapter]`, not a hardcoded default registered directly in `extension.py`. Note the four existing Protocols all return `dict[str, X]`; `list[type[X]]` (as FEAT-1930 specifies) has no existing precedent — flagged in FEAT-1930's own body already.
- **Confirmed callers of `_interruptible_sleep`** (`executor.py:3833`, the pattern this issue's Proposed Solution cites): `executor.py:3626, :3640` (`_handle_rate_limit`), `:3699` (`_check_host_guard`), `:3831` (`_maybe_wait_for_circuit`), `:3919` (`_handle_api_error`), `:3955` (`_handle_infra_retry`) — all internal `FSMExecutor` methods; none are adapter-related, confirming no existing caller needs to change when `TerminalAdapter` is added.
- **Confirmed importers of `extension.py`**: `testing.py:27`, `test_interceptor_extension.py:11`, `test_extension.py:11`, `little_loops/__init__.py:9`.
- **Reusable formatting code**: `scripts/little_loops/cli/output.py` — `status_block()`, `table()`, `colorize()` (ANSI, gated on `NO_COLOR`/`isatty()`) are pure string-returning helpers used by ~80 files for structured terminal output. A contested alternative exists at `scripts/little_loops/init/tui.py` using the third-party `rich`+`questionary` stack instead — the two conventions are not reconciled elsewhere in the codebase (see Proposed Solution decision point below).
- **Reusable timeout-bounded read code**: `scripts/little_loops/mcp_call.py:101-124` (`_send_request`) and `scripts/little_loops/fsm/runners.py:284-349` both use a `selectors.DefaultSelector()` + `sel.select(timeout=min(1.0, remaining))` deadline loop for bounded blocking reads on a file object — structurally reusable for `sys.stdin`, but neither existing instance checks `self._shutdown_requested` inside the loop (see Proposed Solution note on this gap).
- **No countdown-to-deadline formatter exists**: `format_duration()` (`logger.py:115`), `_format_duration()` (`interpolation.py:473`, and a second independent same-named one at `cli/loop/info.py:854`), and `format_relative_time()` (`cli/output.py:232`) all format an already-known elapsed duration, none compute "time remaining until a future deadline."
- **Test pattern precedent**: `scripts/tests/test_fsm_runners.py:185-223` (`TestSimulationActionRunnerPromptResult`) is the closest existing precedent for mocking blocking `sys.stdin` — two styles: `patch("sys.stdin", StringIO(text))` for literal input, and `patch("sys.stdin")` with `.readline.side_effect = EOFError`/`KeyboardInterrupt` for interrupt simulation.
- **Extension conformance test shape**: `scripts/tests/test_extension.py:524-692` gives every existing capability Protocol exactly two tests — a smoke-import test and a "protocol satisfied" test using a minimal ad-hoc class assigned under `# type: ignore[assignment]` (never `isinstance()`, even for `@runtime_checkable` protocols). A future `CommunicationAdapterExtension` conformance test would follow this same two-test shape.

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

- **Zero-config default registration mechanism located**: `scripts/pyproject.toml:131-134` declares `[project.entry-points."little_loops.extensions"]`, currently empty (placeholder comment only) — this is the entry-points group `ExtensionLoader.from_entry_points()` (`extension.py:170-186`) reads via `ENTRY_POINT_GROUP = "little_loops.extensions"`. `ExtensionLoader.from_config()` / ad-hoc `config_paths` require a user's `ll-config.json` entry and are NOT how a "zero configuration" default channel is achieved. A `TerminalAdapterExtension` needs an entry here (e.g. `terminal_adapter = "little_loops.fsm.adapters.terminal_adapter:TerminalAdapterExtension"`) for the Motivation section's "works out of the box with zero configuration" claim to hold — add `scripts/pyproject.toml` to Files to Modify.
- **`resolve_communication_adapter()`'s exact channel-resolution key confirmed**: `channel = self._get_br_config().hitl.channel` (a flat dict lookup into `_contributed_adapters[channel]`, `executor.py:2661-2677`); `HitlConfig.channel` (`scripts/little_loops/config/core.py:185`) defaults to the literal string `"terminal"`. `TerminalAdapterExtension.provided_adapters()` must return a dict keyed exactly `{"terminal": ...}` for the config default to resolve it — any other key requires the user to set `hitl.channel` explicitly.
- **`docs/reference/API.md:11061-11099` already contains a `TerminalAdapter` code example** (`class TerminalAdapter(CommunicationAdapter):` at `:11086`) as an illustrative usage snippet inside the `CommunicationAdapterExtension` documentation section — it is not a reference to a real shipped class. The Documentation task is to reconcile this illustrative snippet with the real implementation, not to add a new doc entry from scratch.
- **`ExtensionLoader.from_config()`/`.from_entry_points()` swallow load failures** (`extension.py:147-192`): a malformed extension (e.g. one whose `__init__` raises) is caught, logged via `logger.warning(..., exc_info=True)`, and skipped — it never appears in `_contributed_adapters`. A broken `TerminalAdapterExtension` would surface downstream as `CommunicationAdapterNotFound: Communication adapter 'terminal' is not registered` at `resolve_communication_adapter()`, not as the original load-time exception.
- **Existing reference-extension package convention**: `scripts/little_loops/extensions/reference_interceptor.py` (`ReferenceInterceptorExtension`) is the one existing example of a top-level `extensions/` package holding a concrete extension implementation — a location precedent, not a template to copy (its own use case is unrelated).

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

## Spike Results

_Added by `/ll:spike` on 2026-09-04_

**Retired risks**

| Risk (from Proposed Solution's ⚠ Unproven mechanism finding) | Proven by | Result |
|----------------------------------|-----------|--------|
| Combined selectors-bounded stdin read + shutdown-flag polling has no precedent | `TestPollingMechanism::test_polling_returns_line_when_available_before_timeout`, `test_polling_returns_none_on_pure_timeout_no_shutdown`, `test_polling_exits_promptly_on_shutdown_signal_mid_block` | ✓ pass — a shutdown flag flipped from another thread interrupts a blocking `selectors`-bounded read within ~one tick (100ms), combining cleanly with the `mcp_call.py`-style deadline loop |
| Whether internal shutdown polling is even required, given `await_response()`'s documented re-entrant short-timeout contract | `TestSingleReadMechanism::test_single_read_returns_line_when_available_before_timeout`, `test_single_read_returns_none_on_timeout`, `test_repeated_short_timeout_calls_satisfy_reentrant_contract` | ✓ pass — a single bounded `selectors` read per call, invoked repeatedly with short timeouts and the shutdown flag checked by the *caller* between calls, achieves equivalent responsiveness with no internal polling loop and loses no in-flight verdict |
| Isolation guard | `TestSpikeIsolation::test_spike_does_not_import_production_adapter_modules` | ✓ pass |

**Finding for the implementer**: both candidate shapes work. `await_line_single_read()` (the simpler shape, no internal shutdown-flag loop) is recommended as the default for `TerminalAdapter.await_response()` — it matches the `communication_adapter.py` re-entrant contract precisely and is less code, deferring shutdown responsiveness to however FEAT-1794's executor loop ends up calling `await_response()`. Fall back to the combined `await_line_polling()` shape only if FEAT-1794 turns out to call `await_response()` with one long timeout instead of short repeated ticks.

**Spike location**: `scripts/tests/spike/terminal_hitl_await/`
**Verification**: 7 tests pass in the spike suite; 104 tests pass across the two named regression suites (`test_fsm_runners.py`, `test_extension.py`).
**Promotion**: the proven `await_line_single_read()` shape is intended to be copied directly into `TerminalAdapter.await_response()` during FEAT-1931 implementation; `scripts/tests/spike/terminal_hitl_await/` need not be promoted verbatim to `scripts/little_loops/spike/`.

## Blocks

- FEAT-2102

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

2026-06-19: `_interruptible_sleep` has drifted to :1911 (was :1886). `send_alert()` signature mismatch with FEAT-1930 protocol still unresolved — missing `loop_name`, `state_name` params. `fsm/adapters/terminal_adapter.py` does not exist (expected, pending FEAT-1930).

- **2026-06-26** (/ll:verify-issues): Aligned `API/Interface` `send_alert()` to FEAT-1930's ratified protocol `send_alert(loop_name, state_name, prompt, captured_context, timeout) -> str`; corrected `_interruptible_sleep` body reference to `scripts/little_loops/fsm/executor.py:1955`. Baseline (no `fsm/adapters/` yet, pending FEAT-1930) unchanged.

- **2026-09-03** (/ll:verify-issues): `_interruptible_sleep` has drifted again — now `scripts/little_loops/fsm/executor.py:3833` (was :3378/:1955). `send_alert()`/`await_response()` signature-mismatch findings above remain open and correctly block implementation on FEAT-1930. Not editing the scattered body citations (lines 133, 217) — this note carries the current anchor for whoever implements next.

- **2026-09-03** (/ll:verify-issues, re-check): Re-verified same-day, no drift since the note above. `scripts/little_loops/fsm/adapters/` still does not exist (confirmed via `ls`). `blocked_by: [FEAT-1930]` backlink confirmed on FEAT-1930's `blocks` list. No active decisions-log rules; `ll-verify-evidence` clean. Verdict: VALID (unchanged).

- **2026-09-04** (`/ll:manage-issue` FEAT-1930 implementation): FEAT-1930 is now implemented (`scripts/little_loops/fsm/communication_adapter.py`, `CommunicationAdapterExtension` in `extension.py`, `FSMExecutor.resolve_communication_adapter()`). `send_alert()`/`await_response()` signature drift (Scope Boundary notes below) fixed in `## API/Interface` and `## Program Design` above: `send_alert()` drops `timeout` (moved to `await_response()` per FEAT-1930 Review #8), `await_response()` gains `alert_id` as its first parameter, and the response type is `AdapterResponse` (not `HumanResponse`/`EditResponse`) carrying `verdict: Literal["approve", "reject", "edit"]`. `blocked_by: [FEAT-1930]` cleared; status flipped `blocked` → `open`.

- **2026-09-04** (`/ll:verify-issues`): Frontmatter still carried `blocked_by: [FEAT-1930]` despite the note above claiming it was cleared — removed it now (FEAT-1930 confirmed `status: Completed`; backlink on FEAT-1930's `blocks` list still holds informationally). Line drift: `_interruptible_sleep` now `executor.py:3856` (was :3833); `_execute_state` def now `:1953` (issue's Call Path cites :1948); `state.type == "learning"` sibling branch now `:1978` (issue cites :1973-1974) — not editing the scattered body citations, this note carries the current anchors. New finding from `communication_adapter.py`'s implemented docstring (not available at the 2026-09-03 pass): `await_response()` is documented "Re-entrant per alert: the executor polls this in short ticks" — i.e. FEAT-1794's caller is expected to call `await_response()` repeatedly with short per-call timeouts and do its own shutdown-checking between calls, closer to the executor-level `_interruptible_sleep` pattern than to a single long-blocking call. This doesn't contradict this issue's Proposed Solution (an adapter satisfying `await_response(alert_id, timeout)` may still block internally up to `timeout`), but it weakens the "unproven mechanism" framing: if FEAT-1794 calls with short timeouts, `TerminalAdapter.await_response()` may not need its own internal shutdown-signal polling loop at all — worth the implementer re-checking once FEAT-1794 lands, rather than building the selectors+shutdown-flag combination pre-emptively. Confirmed via code: `provided_adapters(self) -> dict[str, CommunicationAdapter]` (`extension.py:121`) matches the four existing capability Protocols' `dict[str, X]` convention, resolving the `list[type[X]]` ambiguity flagged in the Integration Map findings — no further action needed there. `await_response` still has zero callers anywhere in the codebase (FEAT-1794 is `status: Open`, unimplemented) — the human_approval dispatch branch this issue depends on for its Call Path still doesn't exist. `ll-verify-evidence` clean; no active decisions-log rules. Verdict: **VALID** (unchanged — findings are informational/anchor-drift, not claim defects).

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): The `API/Interface` section above shows `TerminalAdapter.send_alert(prompt, context, timeout)` but the `CommunicationAdapter` protocol in FEAT-1930 defines `send_alert(loop_name, state_name, prompt, captured_context, timeout) -> None`. Align this issue's `send_alert()` signature with FEAT-1930's protocol **before** implementing — add `loop_name: str` and `state_name: str` as the first two parameters to match the base protocol. This allows the terminal adapter to display the state name in the formatted prompt output without requiring the caller to pre-interpolate it.

**Note** (added by `/ll:audit-issue-conflicts`): This issue's edit-verdict handling returns an `EditResponse` type that does not exist in FEAT-1930's base protocol — `await_response()` there is typed `HumanResponse | TimeoutResponse` only. Do not introduce a third response type; express the edit verdict via the `verdict: Literal["approve", "reject", "edit"]` field FEAT-1930 is adding to its `HumanResponse`/`AdapterResponse` dataclass instead.

**Note** (added by `/ll:audit-issue-conflicts`): This issue's `API/Interface` shows `TerminalAdapter.await_response(self, timeout)`, but FEAT-1930's base protocol defines `await_response(self, alert_id: str, timeout: float)`. Add `alert_id: str` as the first parameter to match the base protocol.

## Session Log
- `/ll:spike` - 2026-09-04T17:07:00 - `996a4184-d64a-4718-acaf-3c2b33b6304f.jsonl`
- `/ll:refine-issue` - 2026-09-04T17:00:36 - `f3346010-0c2d-44a4-8a0e-3cc848bc8952.jsonl`
- `/ll:verify-issues` - 2026-09-04T16:49:24 - `32d87180-d8bc-4b79-9b7f-315760a0277d.jsonl`
- `/ll:manage-issue` - 2026-09-04T07:19:43 - `edcf388a-123e-4783-8b95-eba3c9e4b3da.jsonl`
- `/ll:verify-issues` - 2026-09-03T19:30:24 - `057585fb-7ab7-4b15-b42a-aa3dc8fffb40.jsonl`
- `/ll:refine-issue` - 2026-09-03T18:43:32 - `aa57eda6-6094-4ecb-9d7d-caa100953877.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:56 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:08:30 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:44 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
- backlog-grooming - 2026-07-03T00:00:00Z - Downgraded P2 -> P3 with parent EPIC-1929 (stalled chain; root FEAT-1930 unstarted).
- `/ll:verify-issues` - 2026-06-20T00:34:45 - `fe5ace5b-6f94-43ca-9f1d-09a0705f08c4.jsonl`
- `/ll:verify-issues` - 2026-06-18T02:52:53 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:verify-issues` - 2026-06-14T00:12:51 - `dcbaf608-eff5-4e7b-8a64-4d13a266c421.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:57 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:02 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:format-issue` - 2026-06-05T22:19:19 - `4c87a3f2-1298-4938-ae70-4c5f78013645.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`