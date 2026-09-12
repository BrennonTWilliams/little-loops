---
id: FEAT-3455
title: Behavioral host-conformance suite runnable against a fake host in CI and live hosts behind an env gate
type: FEAT
priority: P2
status: open
discovered_date: '2026-09-11'
labels:
- multi-host
- verification
---

## Summary

Every registered host runner is currently defended by a type check. `scripts/tests/conformance/test_host_conformance.py` parametrizes over `_HOST_RUNNER_REGISTRY` and asserts, per host per golden path, that a `HostInvocation` is constructable — its own docstring concedes it never executes the prompt against a live host. Nothing verifies that a runner which constructs a valid invocation actually produces the behavior the multi-host layer promises callers.

Replace the constructability check with one parameterized behavioral suite that takes a target and asserts observable outcomes: the event sequence a turn emits, its terminal event, abort handling, and the shape of a failure. The same file runs against the fake host on every CI run and against real host binaries behind an explicit env gate, so the contract is enforced continuously and validated against reality on demand.

## Why

The multi-host layer's premise is that a caller does not know which host is running; this is the enforcement half of that promise. The payoff is concrete: adding another adapter becomes a day of work against a known contract instead of a rewrite.

## Current Behavior

`scripts/tests/conformance/test_host_conformance.py` parametrizes over `_HOST_RUNNER_REGISTRY` and asserts, per host per golden path, that `resolve_host() + build_streaming()` returns a constructable `HostInvocation`. The test's own docstring concedes the conformance suite "does not execute the prompt against a live host." A runner that constructs a syntactically valid `HostInvocation` but produces the wrong event sequence (extra events, terminal mid-stream, missing abort handling, malformed failure shape) passes this gate. The contract the multi-host layer promises callers is unenforced.

## Expected Behavior

Replace the constructability check with a single, parameterized behavioral suite `test_golden_path_behavior(host, golden_path)` that runs against a target and asserts observable outcomes:

- The event sequence a turn emits, in order.
- Exactly one terminal event, and it is the last event on the stream.
- Abort mid-turn terminates the stream with the declared abort terminal; the runner does not silently drain remaining tokens.
- The shape of a failure event is stable across hosts (same keys, same primitive types).

The fake host runs the suite in the default CI gate (every `python -m pytest scripts/tests/` invocation). Live host binaries run the same suite behind an explicit env var (e.g. `LL_HOST_CONFORMANCE_LIVE=1`) with a per-target timeout, so the suite is enforced continuously and validated against reality on demand.

Capability-gated cases early-return when the capability is undeclared, so one suite covers a matrix of host abilities without forking per host. The capability profile is a promise, not a hint: where `describe_capabilities()` declares a capability absent, the suite asserts the corresponding event never appears — a negative assertion, not a skip. A host that under-declares is a bug on equal footing with one that over-declares.

## Use Case

A maintainer ports a new CLI host to `HostRunner`. They wire `detect()`, `build_streaming()`, `build_blocking_json()`, `build_version_check()`, and `build_detached()`, then run `LL_HOST_CONFORMANCE_LIVE=1 pytest -m conformance scripts/tests/conformance/test_host_conformance.py -k <runner>` against their binary. Any deviation from the contract — wrong terminal event, missing abort handling, malformed failure payload — fails loudly with a diff against the expected event sequence. The maintainer knows the day the suite goes green, the host satisfies the multi-host promise. No manual smoke run, no "looks right," no latent regression caught only after a loop run hangs.

## Acceptance Criteria

- `test_host_conformance.py` contains a single parameterized test `test_golden_path_behavior` (or equivalent) that asserts observable outcomes — event sequence, terminal-event-last, abort termination, failure shape — and replaces the current `test_golden_path_invocation` constructability check.
- The suite is runnable against the fake host (FEAT-3454) by default on every `python -m pytest scripts/tests/` invocation and exits 0 when the fake satisfies the contract.
- The suite is runnable against live host binaries behind `LL_HOST_CONFORMANCE_LIVE=1` (or equivalent env var) with a per-target timeout, and exits non-zero when a live runner deviates from the contract.
- For every capability marked absent in a runner's `describe_capabilities()` output, the corresponding event-emission case asserts the event never appears (negative assertion), not a skip.
- A diffed failure report shows expected vs actual event sequence, runner name, golden path, and the assertion that fired.
- The conformance gate is wired through the existing `pytest -m conformance` marker contract; existing live-host skip conditions (binary missing, stub raises `HostNotConfigured`) still apply.

## Program Design

### Types

- `ConformanceTarget`: `(runner: HostRunner, name: str, binary: str | None)` — what a single parameter slot supplies
- `BehavioralEvent` (in test file): `{kind: Literal["stdout"|"stderr"|"tool"|"result"|"abort"|"error"|"terminal"], data: Any, ts: float}` — observable event envelope; shape is host-stable
- `BehavioralFailure`: `{kind: str, message: str, exit_code: int | None, recoverable: bool}` — host-stable failure shape
- `TerminalEvent`: `BehavioralEvent` whose `kind in {"result", "abort", "error"}` and is the stream's last event

### Signatures

- `conformance_target(runner: HostRunner) -> ConformanceTarget` — wires runner + binary name into a parameter slot
- `run_golden_path(target: ConformanceTarget, prompt: str, *, timeout_s: float) -> list[BehavioralEvent]` — single target, one prompt, observable event stream to terminal
- `assert_event_sequence_equals(events: list[BehavioralEvent], expected: list[str]) -> None` — ordered-kind assertion, fails with a diff
- `assert_terminal_is_last(events: list[BehavioralEvent]) -> None` — exactly one terminal event; it is the last element
- `assert_capability_not_emitted(events: list[BehavioralEvent], absent_capability: str) -> None` — negative assertion: event kind tied to the capability must not appear
- `_golden_path_behavior(target: ConformanceTarget, prompt: str, capabilities: CapabilityReport) -> None` — orchestrator: gate capability-conditional cases off `capabilities`, sequence+terminal+abort+failure assertions run unconditionally

### Call Path

`pytest collection` -> `_HOST_RUNNER_REGISTRY` resolved into `ConformanceTarget` list -> if `LL_HOST_CONFORMANCE_LIVE` unset, fake target substituted -> `test_golden_path_behavior(target, golden_path)` -> `run_golden_path` -> `resolve_host(name).describe_capabilities()` -> `_golden_path_behavior(target, prompt, caps)`

## Impact

- **Priority**: P2 — defensive infrastructure for a capability that already exists (constructability check); gates a rewrite risk that is latent, not active.
- **Effort**: Medium — rewrites one test function into a parameterized suite; depends on the fake host (FEAT-3454); integrates with the existing `pytest -m conformance` marker, the `LL_HOST_CONFORMANCE_LIVE` env gate is new but trivial.
- **Risk**: Low — additive on the existing suite, no runner contract change, no public API change. The negative-capability assertion can produce failure-shaped-by-design cases that previously passed silently; treat first green as the new baseline.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-11 | Priority: P2

## Design

One suite, parameterized by target — the shape that lets the fake and a real host run the identical file:

- A single conformance function over a target. The fake host runs it in the default CI suite; real host binaries run the same suite behind an explicit env var, with a timeout.
- Assert observable outcomes, not invocation shapes: the event sequence a turn emits; exactly one terminal event, and it is last; abort mid-turn still terminates the stream; the shape of a failure.
- Capability-gated cases early-return when the capability is undeclared, so one suite covers a matrix of host abilities without forking per host.
- The capability profile is a promise, not a hint: where a capability is declared false, assert the corresponding event never appears — a negative assertion, not a skip. A host that under-declares is as much a bug as one that over-declares.

## Dependencies

- Depends on the fake host with a directives language (FEAT-3454) for a CI-runnable target; the suite is the reason that fake exists.
- Pairs with coverage: this suite is about whether the covered cases actually run. Whether an uncovered case went unnoticed is the complementary concern, tracked separately.


## Session Log
- `/ll:format-issue` - 2026-09-12T03:50:16 - `b5367032-da18-428d-be91-16777a0b7408.jsonl`
