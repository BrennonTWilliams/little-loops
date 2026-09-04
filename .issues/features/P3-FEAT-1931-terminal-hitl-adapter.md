---
id: FEAT-1931
title: Terminal adapter for async HITL communication
type: FEAT
priority: P3
captured_at: '2026-06-04T00:00:00Z'
completed_at: '2026-09-04T19:02:47Z'
discovered_date: 2026-06-04
discovered_by: scope-epic
status: done
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
decision_needed: false
unproven_mechanism: true
spike_attempted: true
spike_completed: true
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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
2. Implements `CommunicationAdapter.await_response()`: one bounded
   `selectors`-timed stdin read per call (the spike-proven
   `await_line_single_read()` shape), parses `approve`/`reject`/`edit` (with
   flexible matching: `y`/`yes`/`approve`, `n`/`no`/`reject`, `e`/`edit`),
   returns an `AdapterResponse`. Shutdown responsiveness comes from the
   executor's re-entrant short-tick calling pattern plus `KeyboardInterrupt`
   propagating uncaught — not from an internal polling loop.
3. On timeout (no input within this call's `timeout`), returns
   `TimeoutResponse`; the alert stays pending for the next call.
4. `supports_async()` returns `False` — the operator must be present at the
   terminal.
5. Zero configuration: the executor seeds the terminal adapter in-process
   when `hitl.channel` is `"terminal"` (the default) and no extension has
   registered one — no packaging entry point, no `ll-config.json` entry.

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

**Outcome**: The FSM receives a parsed `AdapterResponse` (verdict
approve/reject, or edit with `edited_text` populated), and continues
execution. On timeout with no input, the FSM receives a `TimeoutResponse`
and follows its configured timeout route.

## Acceptance Criteria

- [x] Implements `CommunicationAdapter` protocol (`send_alert`,
  `await_response`, `supports_async`, plus a `cancel_alert` override)
- [x] Formatted prompt output includes: loop name, state name, prompt text,
  captured context, valid response keys. Time remaining is rendered **only**
  if `captured_context` carries an optional `deadline` key (monotonic-clock
  float, supplied by FEAT-1794's caller); otherwise it is omitted — the
  adapter has no other way to learn the overall deadline (`send_alert()`
  carries no timeout and `await_response()` only sees per-tick budgets)
- [x] Accepts `y`/`yes`/`approve`, `n`/`no`/`reject`, `e`/`edit` (case-
  insensitive, unambiguous prefix matching); optional trailing text after a
  reject alias (`n too risky`) populates `AdapterResponse.reason`
- [x] Empty line or unrecognized input: prints a one-line hint, the alert
  stays pending, and the current call returns `TimeoutResponse`. No default
  on bare Enter (never silently approve); no internal retry loop
- [x] Edit verdict: after `e`, the adapter prompts for a single line of
  replacement text on a second bounded read. If that read times out, the
  alert stays in an awaiting-edit-text state and the next
  `await_response()` call for the same `alert_id` resumes there
- [x] Never catches `KeyboardInterrupt` or `EOFError` — `ll-loop run` relies
  on `KeyboardInterrupt` propagating (`cli/loop/lifecycle.py:881`); each call
  blocks at most `timeout` seconds so the executor's between-call shutdown
  checks stay responsive
- [x] Closed or non-interactive stdin (EOF, e.g. `ll-auto`/detached runs):
  latches a closed flag, logs once, and every subsequent call sleeps for
  `timeout` before returning `TimeoutResponse` — never busy-loops until the
  executor's deadline
- [x] Timeout returns `TimeoutResponse` (not `AdapterResponse`)
- [x] `cancel_alert()` prints a withdrawn notice to the operator and clears
  the alert's pending state
- [x] `supports_async()` returns `False`
- [x] Zero config: `hitl.channel: terminal` (the default) resolves with no
  pyproject entry point and no `ll-config.json` entry; an extension
  registering its own `"terminal"` adapter still overrides the built-in
- [x] Tests: inject `os.pipe()`-backed streams through the constructor
  (`StringIO` has no file descriptor, so `selectors` rejects it); verify
  prompt format, verdict parsing incl. reason capture, unrecognized input,
  edit flow incl. resumption after a timed-out second read, timeout, EOF
  latch, `cancel_alert`, and the zero-config executor resolution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- No shared helper exists in this codebase for case-insensitive prefix matching of free-text confirmation words (y/yes/approve style). The two nearest analogues are exact-string numeric matching (`SimulationActionRunner._prompt_result()`, `fsm/runners.py:530-556`) and LLM-output verdict extraction via regex/keyword search (`output_parsing.py:102-166` `_extract_verdict_from_text()`) — neither does prefix matching of a single free-typed word against a short alias set. This issue's verdict parser is new ground, not an existing pattern to follow.
- The Acceptance Criteria specify accepted inputs (y/yes/approve, n/no/reject, e/edit) but do not specify behavior on unrecognized input — no re-prompt-vs-error decision is stated. `SimulationActionRunner._prompt_result()` (`fsm/runners.py:530-556`) is the nearest precedent and retries on invalid input inside a `while True` loop, but that is not confirmation this issue must do the same — left for the implementer.

## API/Interface

```python
class TerminalAdapter(CommunicationAdapter):
    """Stdin/stdout implementation of the HITL communication protocol.

    Synchronous adapter: one bounded stdin read per await_response() call.
    Always available with zero configuration.
    """

    def __init__(self, stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> None:
        """Streams default to sys.stdin/sys.stdout resolved at call time.

        Tests inject os.pipe()-backed streams; selectors needs a real fd.
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

    def cancel_alert(self, alert_id: str) -> None:
        """Print a withdrawn notice and drop the alert's pending state."""
```

The adapter receives pre-interpolated prompt text from the FSM state; it
only renders, not resolves, variables.

## Program Design

### Deviations

_Added by `/ll:manage-issue` — 2026-09-04:_

- **`_read_line()` does not call `stream.readline()`** (spec text: "the spike's
  `await_line_single_read()` body: one `selectors` wait bounded by `timeout`,
  then `readline()`"). Implemented instead: raw `os.read(fd, 4096)` into an
  instance-owned `bytes` buffer (`self._read_buffer`), with lines split off
  manually. Reason: a real bug found during implementation, not caught by the
  spike or its tests — `TextIOWrapper.readline()` performs internal chunk
  read-ahead, so if two lines are already available on the fd (e.g. an
  operator types/pastes the edit-flow's verdict line and replacement line
  together, or two `send_alert()`/`await_response()` pairs are answered
  back-to-back), the *first* `readline()` call can pull both lines off the OS
  pipe/tty in one read, leaving nothing for the *second* call's
  `selectors.select()` to see — causing a false timeout on already-available
  input. The spike's own tests never exercised two sequential reads on the
  same stream instance with both lines pre-written, so this didn't surface
  there. Signature (`_read_line(self, timeout: float) -> str | None`),
  call path, and external behavior (timeout/EOF semantics) are unchanged;
  only the internal read mechanism differs. Regression test:
  `scripts/tests/test_terminal_adapter.py::TestReadAhead`.

### Types
- No new dataclass/type is introduced by this issue itself — `AdapterResponse`
  and `TimeoutResponse` are FEAT-1930's types (implemented 2026-09-04 in
  `scripts/little_loops/fsm/communication_adapter.py`). The verdict is
  expressed via `AdapterResponse.verdict: Literal["approve", "reject", "edit"]`
  — there is no separate `EditResponse` type.
- Private per-adapter state (no public type): `_pending: dict[str, _PendingAlert]`
  keyed by `alert_id`, where `_PendingAlert` is a small module-private
  dataclass holding `state_name: str` and `awaiting_edit_text: bool`; plus
  `_stdin_closed: bool` (EOF latch, starts `False`).

### Signatures
- `TerminalAdapter.__init__(self, stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> None`
  — `None` means resolve `sys.stdin`/`sys.stdout` at call time (so `capsys`
  and `patch("sys.stdout")` work); tests pass `os.pipe()`-backed streams.
- `TerminalAdapter.send_alert(self, loop_name: str, state_name: str, prompt: str, captured_context: dict) -> str`
  — no `timeout` parameter; FEAT-1930 Pre-implementation Review #8 moved the
  wait budget to `await_response()`. Returns a fresh `uuid4().hex` alert id
  and records it in `_pending`.
- `TerminalAdapter.await_response(self, alert_id: str, timeout: float) -> AdapterResponse | TimeoutResponse` —
  matches FEAT-1930's base protocol (`communication_adapter.py`), which
  defines `await_response(self, alert_id: str, timeout: float)`, re-entrant
  per `alert_id`. Unknown `alert_id` raises `KeyError` (programming error,
  not an operator outcome).
- `TerminalAdapter.cancel_alert(self, alert_id: str) -> None` — prints a
  withdrawn notice, pops `_pending[alert_id]` (no-op if absent).
- `TerminalAdapter.supports_async(self) -> bool` — returns `False`
- `TerminalAdapter._read_line(self, timeout: float) -> str | None` — the
  spike's `await_line_single_read()` body: one `selectors` wait bounded by
  `timeout`, then `readline()`; returns `None` on timeout. Empty string from
  `readline()` (EOF) sets `_stdin_closed` and returns `None`.
- `_parse_verdict(line: str) -> AdapterResponse | None` — module-level pure
  function; `None` means unrecognized.

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

Zero-config seeding (this issue's one executor change): on the `KeyError`
branch of `resolve_communication_adapter()` (`executor.py:2661-2677`), when
`channel == "terminal"`, lazily import `TerminalAdapter`, store it in
`_contributed_adapters["terminal"]`, and return it. Extensions registered by
`wire_extensions()` populate the dict *before* any resolve call, so an
extension contributing its own `"terminal"` wins without tripping the
extension-vs-extension conflict check. Update the method docstring, which
currently says it "never imports a specific adapter directly".

### Decision Rules
- **Accepted verdict keywords** (from Acceptance Criteria): `y`/`yes`/`approve` → approve,
  `n`/`no`/`reject` → reject, `e`/`edit` → edit. Case-insensitive, unambiguous
  prefix matching (the three aliases start with distinct letters, so no
  collision is possible under prefix matching).
- **Prefix matching, exactly**: lowercase and strip the line; split off the
  first whitespace-delimited token; the token matches an alias if it is a
  non-empty prefix of one of `yes`, `approve`, `no`, `reject`, `edit` (so
  `y`, `a`, `ap`, `n`, `r`, `e` all resolve). Any remaining text after a
  reject alias becomes `AdapterResponse.reason`; trailing text after
  approve/edit is ignored.
- **Unrecognized or empty input** (decided 2026-09-04 pre-implementation
  review): write one hint line (`Expected y/yes/approve, n/no/reject, e/edit`)
  to stdout, leave the alert pending, return `TimeoutResponse` from this
  call. Do **not** copy `SimulationActionRunner._prompt_result()`'s internal
  `while True` retry loop — the executor's re-entrant tick loop is the retry
  loop. Bare Enter has no default.
- **Edit flow state machine**: on `e`, print `Enter replacement text (one
  line):`, set `awaiting_edit_text=True`, and immediately attempt a second
  `_read_line()` with whatever `timeout` budget remains in this call. If it
  returns text → `AdapterResponse(verdict="edit", edited_text=text)` and pop
  `_pending`. If it times out → `TimeoutResponse`; the next call for this
  `alert_id` sees `awaiting_edit_text` and goes straight to reading the
  text (no re-prompt for a verdict). Single-line only in this issue.
- **EOF / non-interactive stdin**: once `_stdin_closed` is set, every
  subsequent `await_response()` call does `time.sleep(timeout)` and returns
  `TimeoutResponse` — this keeps the executor's overall deadline honest
  without a hot loop. Log a single `logger.warning` the first time.
- **Signals**: never wrap `_read_line()` in `except (EOFError,
  KeyboardInterrupt)` — `cli/loop/lifecycle.py:881` catches
  `KeyboardInterrupt` at the top level and that is the documented ^C path.
- **Deadline rendering**: only when `captured_context.get("deadline")` is a
  number; render `int(deadline - time.monotonic())` seconds. FEAT-1794 owns
  whether the caller supplies it. No countdown widget — a single static line.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

- **`_interruptible_sleep()` (`executor.py:3856`) is not reusable as-is by a standalone adapter**: it is a bound method reading `self._shutdown_requested` (an `FSMExecutor` instance attribute), not a free function — a `TerminalAdapter` class cannot call it without either being handed the executor instance, an extracted free-function equivalent, or duplicating the loop. It also only wraps `time.sleep()` ticks; it has no mechanism for interrupting a blocking `sys.stdin` read.
- **`await_response()`'s re-entrancy contract, exact docstring** (`communication_adapter.py`): "Block up to `timeout` seconds for the operator's verdict on `alert_id`. Re-entrant per alert: the executor polls this in short ticks so shutdown stays responsive. Repeat calls for the same `alert_id` are expected; a verdict that arrives between calls must be retained and returned on the next call. A `TimeoutResponse` does not invalidate the alert — only `cancel_alert()` does." This means an adapter is not contractually required to internally combine a selectors-bounded read with shutdown-flag polling in one blocking call (the combination the Proposed Solution's `⚠ Unproven mechanism` finding says has no precedent) — it only needs to honor one bounded `timeout` per call and retain any verdict arriving outside that window for the next call. This narrows, but does not resolve, `unproven_mechanism` (only `/ll:spike` resolves it).

## Proposed Solution

Use the spike-proven `await_line_single_read()` shape
(`scripts/tests/spike/terminal_hitl_await/awaiter.py`): one
`selectors`-bounded read of the injected stdin stream per `await_response()`
call, no internal shutdown polling. The executor's re-entrant short-tick
calling pattern (documented on `CommunicationAdapter.await_response()`) plus
an uncaught `KeyboardInterrupt` provide shutdown responsiveness. The
`_interruptible_sleep()` polling pattern (`executor.py:3856`) is relevant
only to the fallback `await_line_polling()` shape, which is not needed unless
FEAT-1794 calls `await_response()` with one long timeout.

Format the prompt using the existing `${captured.<state>.<field>}` interpolation
from the FSM context — the adapter receives pre-interpolated text from the FSM
state, so it only needs to render, not resolve variables.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-04 — based on codebase analysis:_

- **`await_response()` re-entrancy contract narrows the "unproven mechanism" concern** (see `## Program Design` → Codebase Research Findings for the full docstring): the protocol does not require an adapter to internally combine a selectors-bounded stdin read with shutdown-flag polling in one call — the executor is expected to call `await_response()` repeatedly with short per-call timeouts. Resolved by the 2026-09-04 spike (see `## Spike Results`): the single-read shape is the selected default.

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- **No existing technique combines the two mechanisms this issue's polling approach depends on.** `_interruptible_sleep()` (`executor.py:3833`) checks `self._shutdown_requested` between 100ms `time.sleep()` ticks — but that only works because `time.sleep()` naturally returns control every tick; a blocking `sys.stdin` read has no such checkpoint. The codebase's only bounded-timeout blocking-read technique (`selectors.DefaultSelector()` + `sel.select(timeout=...)`, used in `mcp_call.py:101-124` and `fsm/runners.py:284-349`) never checks `_shutdown_requested` inside its loop. No existing call site in the codebase exercises "selectors-bounded read on a file object" together with "shutdown-flag polling" — the combination this issue's Proposed Solution assumes works has no confirming precedent. ⚠ Unproven mechanism — no site combines selectors-bounded read with shutdown-flag polling
- **Extension registration approach in Proposed Solution/Implementation Steps needs updating**: see the correction under Integration Map above — there is no "register as default adapter in extension.py" mechanism; the ratified path is a `TerminalAdapterExtension(CommunicationAdapterExtension)` implementing `provided_adapters()`.
- **Terminal output formatting has two unreconciled existing conventions in this codebase — an implementer decision, not resolved by precedent:**

**Option A**: Follow `scripts/little_loops/cli/output.py`'s convention — raw ANSI-escape `colorize()` plus `status_block()`/`table()` pure string-returning helpers (used by ~80 existing call sites for structured terminal output, e.g. `cli/harness.py:763-771`). Color gated on `NO_COLOR`/`FORCE_COLOR` env vars and `sys.stdout.isatty()`.

> **Selected:** Option A — dominant, dependency-free, actively-tested convention with ~80 existing call sites; Option B's rich/questionary usage is scoped to a single file and has no proven timeout-compatible primitive.

**Option B**: Follow `scripts/little_loops/init/tui.py`'s convention — the third-party `rich` library's `console.print()` with `[color]...[/color]` markup, paired with `questionary` for confirmation prompts (`questionary.confirm(...).ask()` returning `bool | None`).

No recommendation from research — both conventions are actively used elsewhere in the codebase for different subsystems (general CLI output vs. the init wizard specifically), and neither is deprecated relative to the other.

### Decision Rationale

_Added by `/ll:decide-issue` — 2026-09-04:_

**Selected**: Option A — follow `scripts/little_loops/cli/output.py`'s `colorize()`/`status_block()`/`table()` convention for the terminal adapter's formatted-prompt rendering.

**Reasoning**: Two parallel `ll:codebase-pattern-finder` evidence passes (one per option) found both options equally unable to cover this issue's hardest requirement — the timeout countdown and bounded-timeout stdin read, neither of which has precedent in either module (the FEAT-1931 spike proved that mechanism with raw `selectors`/`sys.stdin`, independent of formatting library). On the half each option does cover — static formatted rendering — Option A is the clearly better codebase fit: `status_block()`/`colorize()` are pure, dependency-free, string-returning helpers with ~80 existing call sites across the CLI (three of them the near-identical "assemble dict → `status_block()` → `print()`" shape this adapter needs, e.g. `cli/harness.py:763-771`, `cli/queue.py:295-317`, `init/cli.py:457`), backed by dedicated test suites (`test_cli_output.py`, `test_snapshot_output_primitives.py`). Option B's `rich`/`questionary` stack, while already a core dependency, is used nowhere in the codebase outside the single-purpose init wizard (`init/tui.py`) and its test file, and its `.ask()` calls block indefinitely with no timeout parameter — a direct mismatch with this issue's "respects FSM shutdown signal during blocking input" acceptance criterion for the edit-verdict secondary prompt, and the source of the still-unresolved `learning_tests_required: [rich, questionary]` frontmatter flag.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A: `cli/output.py` (`colorize`/`status_block`/`table`) | 3 | 3 | 3 | 2 | 11/12 |
| B: `rich`+`questionary` (`init/tui.py` convention) | 1 | 1 | 1 | 1 | 4/12 |

**Key evidence**:
- `status_block()` (`cli/output.py:347-359`, the selected convention) matches 3+ existing call sites in the exact shape needed (`cli/harness.py:763-771`, `cli/queue.py:295-317`, `init/cli.py:457`); module has zero `deprecated`/legacy markers and active recent additions (`ENH-2539`).
- The rejected `rich`/`questionary` convention's usage is confirmed (repo-wide grep) limited to `init/tui.py` + its test file only; no `.ask()` call anywhere in the codebase passes a timeout; `rich.live.Live`/countdown widgets have zero usage.
- Neither convention's module has a countdown-to-deadline formatter or a bounded-timeout stdin-read precedent — that piece is net-new regardless of which was chosen (confirmed independently by the FEAT-1931 spike, which used raw `selectors`, not either formatting library).

## Implementation Steps

1. Study the `CommunicationAdapter` protocol definition (FEAT-1930) and the
   proven `await_line_single_read()` shape from the FEAT-1931 spike
   (`scripts/tests/spike/terminal_hitl_await/`)
2. Create `scripts/little_loops/fsm/adapters/__init__.py` and
   `terminal_adapter.py`; implement `TerminalAdapter(stdin=None, stdout=None)`
   with `send_alert()`, `await_response()`, `supports_async()`, and a
   `cancel_alert()` override, plus the private `_pending`/`_stdin_closed`
   state from `## Program Design`
3. Implement formatted prompt rendering using `cli/output.py`'s
   `colorize()`/`status_block()`/`table()` convention (Decision Rationale:
   Option A). Include loop name, state name, prompt, captured context, the
   valid-response line, and a remaining-seconds line only when
   `captured_context["deadline"]` is present
4. Implement `_read_line()` from the spike-proven `await_line_single_read()`
   shape: one bounded `selectors`-timed read per call on the injected stdin,
   no internal shutdown-flag polling loop — matches the re-entrant
   short-timeout contract documented in `communication_adapter.py`. Set
   `_stdin_closed` on EOF. Do not catch `KeyboardInterrupt`/`EOFError`.
   Fall back to the combined `await_line_polling()` shape only if FEAT-1794's
   executor ends up calling `await_response()` with one long timeout instead
   of short repeated ticks.
5. Implement `_parse_verdict()`: case-insensitive unambiguous prefix matching
   for `approve`/`y`/`yes`, `reject`/`n`/`no`, `edit`/`e`; trailing text
   after a reject alias → `AdapterResponse.reason`. Unrecognized/empty →
   hint line + `TimeoutResponse` for this call (alert stays pending).
6. Implement the edit flow: on `e`, prompt for one line of replacement text
   with the remaining call budget; express it via
   `AdapterResponse(verdict="edit", edited_text=...)` — there is no separate
   `EditResponse` type. Persist `awaiting_edit_text` across calls so a timed-
   out second read resumes at the text prompt on the next call.
7. Implement the EOF latch (sleep `timeout` then `TimeoutResponse` once
   `_stdin_closed`, single warning log) and `cancel_alert()` (withdrawn notice
   + pop pending state).
8. Zero-config registration: in `FSMExecutor.resolve_communication_adapter()`
   (`executor.py:2661`), on `KeyError` with `channel == "terminal"`, lazily
   import and cache `TerminalAdapter()` in `_contributed_adapters`, then
   return it. Update the docstring. Do **not** add a
   `[project.entry-points."little_loops.extensions"]` entry — ⚠ Superseded
   (2026-09-04 pre-implementation review): entry-point metadata only refreshes
   on `pip install -e`, so every `local-editable` consumer on this machine
   would hit `CommunicationAdapterNotFound: 'terminal'` until reinstalled, and
   `ExtensionLoader` swallows load failures. A `TerminalAdapterExtension`
   class is still fine to ship as an *example* but must not be the default's
   only registration path.
9. Write tests (`scripts/tests/test_terminal_adapter.py`) with
   `os.pipe()`-backed streams (copy the spike's `pipe` fixture): prompt
   format, verdict parsing incl. reason, unrecognized input, edit flow incl.
   resumption, timeout, EOF latch timing, `cancel_alert`, and an executor
   test that `resolve_communication_adapter()` returns a `TerminalAdapter`
   with an empty `_contributed_adapters` and default config
10. Reconcile the illustrative `TerminalAdapter` snippet in
    `docs/reference/API.md` (`CommunicationAdapterExtension` section) and note
    the built-in default under `docs/reference/CONFIGURATION.md#hitl`

## Integration Map

### Files to Create
- `scripts/little_loops/fsm/adapters/__init__.py` — new subpackage
- `scripts/little_loops/fsm/adapters/terminal_adapter.py` —
  `TerminalAdapter(CommunicationAdapter)`
- `scripts/tests/test_terminal_adapter.py`

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `resolve_communication_adapter()`
  (`:2661-2677`): seed the built-in `TerminalAdapter` on the `KeyError`
  branch when `channel == "terminal"`; update the docstring
- `docs/reference/API.md` — reconcile the illustrative snippet (see
  Documentation below)
- `docs/reference/CONFIGURATION.md` — `hitl` section: state that `terminal`
  is built in and needs no extension
- ~~`scripts/pyproject.toml` — add `TerminalAdapterExtension` under
  `[project.entry-points."little_loops.extensions"]`~~ — ⚠ Superseded
  (2026-09-04 pre-implementation review): not the zero-config path; see
  Implementation Step 8. `scripts/little_loops/extension.py` needs no
  modification.

### Similar Patterns
- `scripts/little_loops/mcp_call.py:101-124` (`_send_request`) and
  `scripts/little_loops/fsm/runners.py:284-349` —
  `selectors.DefaultSelector()` + `sel.select(timeout=...)` bounded-read
  pattern; the spike's proven `await_line_single_read()` shape (recommended
  default) is built directly on this, not on `_interruptible_sleep()`
- `executor.py` — `_interruptible_sleep()`: polling-with-shutdown-signal
  pattern; relevant only to the fallback `await_line_polling()` shape (see
  Implementation Steps)
- `scripts/little_loops/transport.py` — `UnixSocketTransport`: blocking I/O
  with timeout (path corrected — not `fsm/transport.py`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — will call adapter through
  `CommunicationAdapter` protocol interface via
  `resolve_communication_adapter()` (no direct import of `TerminalAdapter`
  needed)
- `scripts/little_loops/fsm/executor.py` — one lazy, function-local import
  of `TerminalAdapter` inside `resolve_communication_adapter()` (keeps the
  module import graph acyclic); no other file imports it outside its own
  module and tests

### Tests
- `scripts/tests/test_terminal_adapter.py` — new test file; stdin via
  `os.pipe()` (not `StringIO` — `selectors` needs a real fd; see the spike's
  `pipe` fixture), stdout via an injected `io.StringIO`

### Documentation
- `docs/reference/API.md:11061-11099` — reconcile the existing illustrative
  `TerminalAdapter` code example (inside the `CommunicationAdapterExtension`
  section) with the real implementation; this is not a new entry from scratch

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

- **Priority**: P3 — default channel, required for FEAT-1794 to function
  (downgraded from P2 with parent EPIC-1929 on 2026-07-03; see Session Log)
- **Effort**: Small — single adapter implementation plus a ~10-line executor
  seed, ~150-200 lines
- **Risk**: Low — I/O core proven by the 2026-09-04 spike
- **Breaking Change**: No

## Resolution

_Added by `/ll:manage-issue` — 2026-09-04:_

Implemented `TerminalAdapter` (`scripts/little_loops/fsm/adapters/terminal_adapter.py`)
per the ratified `## Program Design`. Zero-config seeding added to
`FSMExecutor.resolve_communication_adapter()` (`executor.py:2661`) as
specified — no `TerminalAdapterExtension`/entry-point was created, matching
Implementation Step 8's superseded-registration note.

Found and fixed a real bug during implementation not caught by the
2026-09-04 spike: see `## Program Design` → `### Deviations` for
`_read_line()`'s raw-fd manual line buffering (replacing
`stream.readline()`) to avoid `TextIOWrapper` read-ahead causing false
timeouts on already-buffered input.

22 new tests in `scripts/tests/test_terminal_adapter.py`, all passing.
Full suite: `python -m pytest scripts/tests/` — 22760 passed, 43 skipped, 1
pre-existing unrelated failure (`test_prose_dep_sweep_gate.py` — FEAT-1794
prose drift against FEAT-1930, confirmed present on `main` before this
change via `git stash`; out of scope for this issue). `ruff check` and
`mypy` clean on all changed/new files.

Reconciled `docs/reference/API.md` (`CommunicationAdapterExtension` usage
snippet) and `docs/reference/CONFIGURATION.md` (`hitl` section) to describe
the built-in zero-config `"terminal"` channel per Implementation Step 10.

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

_All three notes below were resolved on 2026-09-04 when FEAT-1930 landed;
`## API/Interface` and `## Program Design` now carry the ratified
signatures. Retained for provenance only._

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): The `API/Interface` section above shows `TerminalAdapter.send_alert(prompt, context, timeout)` but the `CommunicationAdapter` protocol in FEAT-1930 defines `send_alert(loop_name, state_name, prompt, captured_context, timeout) -> None`. Align this issue's `send_alert()` signature with FEAT-1930's protocol **before** implementing — add `loop_name: str` and `state_name: str` as the first two parameters to match the base protocol. This allows the terminal adapter to display the state name in the formatted prompt output without requiring the caller to pre-interpolate it.

**Note** (added by `/ll:audit-issue-conflicts`): This issue's edit-verdict handling returns an `EditResponse` type that does not exist in FEAT-1930's base protocol — `await_response()` there is typed `HumanResponse | TimeoutResponse` only. Do not introduce a third response type; express the edit verdict via the `verdict: Literal["approve", "reject", "edit"]` field FEAT-1930 is adding to its `HumanResponse`/`AdapterResponse` dataclass instead.

**Note** (added by `/ll:audit-issue-conflicts`): This issue's `API/Interface` shows `TerminalAdapter.await_response(self, timeout)`, but FEAT-1930's base protocol defines `await_response(self, alert_id: str, timeout: float)`. Add `alert_id: str` as the first parameter to match the base protocol.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-04_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (hard override)
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- Requirements clarity (Criterion 3): behavior on unrecognized stdin input (retry vs. hard error) is explicitly left unspecified by Acceptance Criteria; nearest precedent (`SimulationActionRunner._prompt_result()`, `fsm/runners.py:530-556`) retries in a loop, but this issue doesn't confirm that's required.
- `questionary` learning-test record is `proven` but carries 2 failing claims (partial-answer behavior on EOF via `questionary.prompt()`; `Separator()`/`Choice` typing) — moot if Option A (the selected convention) stands, since neither library is used by the chosen implementation.

### Gaps to Address
- **Learning Test Hard Override**: `rich` has no learning-test record (`missing`), forcing STOP regardless of aggregate score. This issue's Decision Rationale (2026-09-04) already selected Option A (`cli/output.py`'s `colorize`/`status_block`/`table`) over the rich/questionary-based Option B — `rich` (and likely `questionary`) is no longer a real dependency of the chosen approach. Recommend clearing both from `learning_tests_required` frontmatter (or via `/ll:decide-issue`) rather than running `/ll:explore-api rich` to prove an assumption for an abandoned option.
- **Decision Cap** (Criterion C capped at 10/25): `ll-issues format-check` flags `unapplied_decision` — `await_response()` still appears, unmarked, in `## Program Design` and `## Implementation Steps` as if it were a rejected option. This may be a detector false-positive (the issue's only ratified `> **Selected:**` decision concerns the output-formatting convention, not `await_response()`, which is the real protocol method being implemented) — worth a quick verification pass before treating it as a real unresolved decision.

### Outcome Risk Factors
_(none — 71/100 is above this project's configured `outcome_threshold` of 65)_

## Pre-implementation Review (2026-09-04)

Manual review before `/ll:manage-issue`. Changes applied to the body above:

- **Deadline AC was unsatisfiable**: `send_alert()` carries no timeout and
  `await_response()` only sees per-tick budgets, so the adapter cannot render a
  countdown on its own. Replaced with an optional `captured_context["deadline"]`
  contract owned by FEAT-1794.
- **Entry-point registration replaced by executor seeding**: pyproject entry
  points only refresh on reinstall, which would break every `local-editable`
  consumer, and `wire_extensions()`'s conflict check would make the built-in
  un-overridable. Zero-config now means a lazy seed in
  `resolve_communication_adapter()`.
- **Decided previously-open behavior**: unrecognized/empty input (hint +
  `TimeoutResponse`, alert stays pending), edit flow resumption across calls,
  EOF latch to avoid a busy loop under non-interactive stdin, uncaught
  `KeyboardInterrupt` as the ^C path, `cancel_alert()` behavior, optional
  reject reason.
- **Testability**: constructor stream injection; tests use `os.pipe()` since
  `selectors` rejects `StringIO`.
- Housekeeping: Impact priority aligned to P3; `_interruptible_sleep`
  citation in Proposed Solution corrected to `:3856`; the 2026-09-04
  re-entrancy finding moved out of the Option B block (it was tripping
  `unapplied_decision` as a rejected-option mention); Scope Boundary notes
  marked resolved.

Re-run `/ll:confidence-check` before implementing — the recorded 75/100 is
below this project's `readiness_threshold` of 85.

## Session Log
- `/ll:manage-issue` - 2026-09-04T19:01:27 - `a8753b0f-28e6-4493-9607-3f7aa213017c.jsonl`
- `/ll:confidence-check` - 2026-09-04T17:51:49 - `94c5757c-d9f5-4eca-9c07-95f38c364ba5.jsonl`
- manual pre-implementation review - 2026-09-04 - see `## Pre-implementation Review (2026-09-04)`
- `/ll:explore-api` - 2026-09-04 - Skipped exploration and cleared `learning_tests_required: [rich, questionary]` from frontmatter per this issue's own 2026-09-04 Confidence Check note: Option A (`cli/output.py` convention) was selected over the rich/questionary-based Option B, so neither library is a real dependency of the chosen implementation.
- `/ll:confidence-check` - 2026-09-04T17:34:47 - `6ce3bc7e-5cc0-4c07-bc92-274906ec8f9b.jsonl`
- `/ll:reconcile-issue` - 2026-09-04T17:28:24 - `9c215218-0709-4612-905a-d94c22135410.jsonl`
- `/ll:decide-issue` - 2026-09-04T17:23:32 - `c44d62f6-fc1d-40b3-bdf0-f62b5b1b46ac.jsonl`
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