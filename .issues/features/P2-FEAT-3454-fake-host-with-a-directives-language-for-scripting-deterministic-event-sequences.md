---
id: FEAT-3454
title: Fake host with a directives language for scripting deterministic event sequences
type: FEAT
priority: P2
status: open
testable: true
discovered_date: '2026-09-11'
labels:
- testing
- multi-host
---

## Summary

The orchestration paths that matter most — event ordering, abort mid-turn, recovery after a failed start — can only be exercised today against a live host. That makes them slow, expensive, flaky, or simply untested, and it is why the shipped conformance suite settles for asserting a `HostInvocation` is constructable rather than running anything.

Build a fake host runner that accepts a directives language: a test writes a prompt string that encodes an exact sequence of events, failures, and timings for the fake to emit, and the executor drives against it with no model involved. The fake registers through the same `_HOST_RUNNER_REGISTRY` path as a real runner and declares its own `HostCapabilities`, so nothing in the executor knows it is fake.

## Motivation

- Everything downstream in the harness testing story stands on this: a behavioral conformance suite needs a CI-runnable target, and the only target available today is a live host binary behind an env gate.
- It generalizes the fake-clock idea — deterministic time made temporal paths testable; a scriptable fake host makes the host's whole event stream testable. Same property, larger surface.
- The proven shape elsewhere is small: a ~315-line directives interpreter has been enough to let a large deterministic unit-test tier exercise orchestration logic with no model in the loop at all.

## Current Behavior

`scripts/tests/conformance/test_host_conformance.py` parametrizes over `_HOST_RUNNER_REGISTRY` and asserts only that a `HostInvocation` (defined in `scripts/little_loops/host_runner.py`) is constructable — its own docstring concedes it never executes the prompt against a live host. Ordering, abort, and recovery paths in the executor are exercised only by live-host runs, or not at all.

## Expected Behavior

- A fake host runner registered through `_HOST_RUNNER_REGISTRY`, indistinguishable from a real runner at the executor boundary.
- A directives language embedded in the prompt string: a test scripts an exact sequence of events, failures, and timings, and the fake emits exactly that sequence.
- The fake declares its own `HostCapabilities`, and can declare different capability profiles per test — which is itself a test surface.
- Deterministic, model-free, and runnable in the default CI suite.
- Terminal-event discipline from the start: a scripted turn emits exactly one terminal event and it is last — including after a scripted abort.

## Scope

Scope the directives language to what the executor actually branches on. A language that can express every possible host behavior is a second harness to maintain; the executor's event types, failure shapes, and timing hooks define the vocabulary, nothing more.

## Use Case

A loop-run author needs to assert that orchestration paths do the right thing under adversarial host event ordering — e.g. an `abort_received` mid-stream followed by a delayed `tool_result` and a forced startup timeout. Today those paths are exercised only by live host binary runs (slow, flaky, env-gated) or simply left uncovered. With a fake host, the author writes a test whose prompt string encodes the exact sequence (events + failures + timings) and asserts on the executor's recorded response, in milliseconds, no model involved, in the default CI suite.

## Acceptance Criteria

- A fake host runner is registered through `_HOST_RUNNER_REGISTRY` (`scripts/little_loops/host_runner.py`) under a distinct runner name and is constructable via `resolve_host("<name>")` indistinguishably from a real runner at the executor boundary.
- A directives language embedded in the prompt string drives the fake's emitted event sequence: events, failures (including `abort_received`, timeout, startup failure), and timings are all expressible in the prompt and emitted deterministically.
- The fake declares its own `HostCapabilities` record; the constructor accepts a per-test capability profile override so capability-driven executor branches become a test surface.
- Terminal-event discipline: a scripted turn emits exactly one terminal event, and it is last; this holds even when the script includes an explicit abort directive.
- A new behavior-level conformance test (`scripts/tests/conformance/test_host_conformance.py` or sibling) exercises event ordering, abort mid-turn, and recovery-after-failed-start against the fake and runs in the unit suite without env-gating.
- All directives used in the conformance tests stay within the vocabulary the executor actually branches on — no script-only directives drift into the language surface.

## Program Design

### Types

- `FakeHostCapabilities`: dataclass mirroring `HostCapabilities` shape so the fake can declare a profile override
- `DirectivesScript`: parsed representation of the prompt-string program (event list with attached timings/failures)

### Signatures

- `FakeHostRunner(capabilities: HostCapabilities | None = None)` registers itself into `_HOST_RUNNER_REGISTRY` under a fixed name (e.g. `"fake"`)
- `parse_directives(prompt: str) -> DirectivesScript`
- `FakeHostRunner.build_streaming(prompt: str, **kwargs) -> HostInvocation` — emits the scripted sequence with no subprocess and no model

### Call Path

`resolve_host("fake")` -> `FakeHostRunner.build_streaming()` -> `FakeExecutor._drive_iter` consumes scripted events

## Implementation Steps

1. Add `FakeHostRunner` implementing the runner interface from `scripts/little_loops/host_runner.py`; register via `_HOST_RUNNER_REGISTRY`.
2. Define a minimal directives grammar in the prompt string (one directive per emitted event/failure/timing) and a `parse_directives` interpreter.
3. Wire capability-profile override into the fake's constructor; emit `HostCapabilities` accordingly.
4. Enforce terminal-event discipline inside the fake (one terminal, last).
5. Add behavior-level conformance tests for ordering / abort-mid-turn / recovery-after-failed-start; keep them inside the unit suite with no env gate.
6. Update `scripts/tests/conformance/test_host_conformance.py` so behavioral (not just constructable) coverage is the default for the fake entry.

## Impact

- **Priority justification (P2)**: blocks any behavior-level conformance coverage of orchestration paths — currently exercised only by live-host runs or not at all.
- **Effort**: medium — one fake runner, a small directives interpreter, plus a handful of conformance tests; the ~315-line referenced interpreter suggests the directive core is the bulk.
- **Risk**: low — fake is additive in the registry; nothing in the executor changes, and the live-host path stays untouched.
- **Benefit**: deterministic, model-free behavioral conformance in the default CI tier; unblocks testing of event-ordering, abort, and recovery paths.

## Status

**Open** | Created: 2026-09-11 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-12T03:49:49 - `8c6cc97d-774e-45fd-be34-14d7ed48d65c.jsonl`
