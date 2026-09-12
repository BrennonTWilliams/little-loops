---
id: 3454
title: Fake host with a directives language for scripting deterministic event sequences
type: FEAT
priority: P2
status: open
discovered_date: '2026-09-11'
labels:
- testing
- multi-host
---

## Summary

The orchestration paths that matter most — event ordering, abort mid-turn, recovery after a failed start — can only be exercised today against a live host. That makes them slow, expensive, flaky, or simply untested, and it is why the shipped conformance suite settles for asserting a `HostInvocation` is constructable rather than running anything.

Build a fake host runner that accepts a directives language: a test writes a prompt string that encodes an exact sequence of events, failures, and timings for the fake to emit, and the executor drives against it with no model involved. The fake registers through the same `_HOST_RUNNER_REGISTRY` path as a real runner and declares its own `HostCapabilities`, so nothing in the executor knows it is fake.

## Why

- Everything downstream in the harness testing story stands on this: a behavioral conformance suite needs a CI-runnable target, and the only target available today is a live host binary behind an env gate.
- It generalizes the fake-clock idea — deterministic time made temporal paths testable; a scriptable fake host makes the host's whole event stream testable. Same property, larger surface.
- The proven shape elsewhere is small: a ~315-line directives interpreter has been enough to let a large deterministic unit-test tier exercise orchestration logic with no model in the loop at all.

## Current Behavior

`scripts/tests/conformance/test_host_conformance.py` parametrizes over `_HOST_RUNNER_REGISTRY` and checks only that a `HostInvocation` is constructable — its own docstring concedes it never executes the prompt against a live host. Ordering, abort, and recovery paths in the executor are exercised only by live-host runs, or not at all.

## Expected Behavior

- A fake host runner registered through `_HOST_RUNNER_REGISTRY`, indistinguishable from a real runner at the executor boundary.
- A directives language embedded in the prompt string: a test scripts an exact sequence of events, failures, and timings, and the fake emits exactly that sequence.
- The fake declares its own `HostCapabilities`, and can declare different capability profiles per test — which is itself a test surface.
- Deterministic, model-free, and runnable in the default CI suite.
- Terminal-event discipline from the start: a scripted turn emits exactly one terminal event and it is last — including after a scripted abort.

## Scope

Scope the directives language to what the executor actually branches on. A language that can express every possible host behavior is a second harness to maintain; the executor's event types, failure shapes, and timing hooks define the vocabulary, nothing more.
