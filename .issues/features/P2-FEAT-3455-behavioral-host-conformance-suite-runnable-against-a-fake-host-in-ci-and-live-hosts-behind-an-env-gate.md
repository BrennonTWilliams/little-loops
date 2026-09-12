---
id: 3455
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

## Design

One suite, parameterized by target — the shape that lets the fake and a real host run the identical file:

- A single conformance function over a target. The fake host runs it in the default CI suite; real host binaries run the same suite behind an explicit env var, with a timeout.
- Assert observable outcomes, not invocation shapes: the event sequence a turn emits; exactly one terminal event, and it is last; abort mid-turn still terminates the stream; the shape of a failure.
- Capability-gated cases early-return when the capability is undeclared, so one suite covers a matrix of host abilities without forking per host.
- The capability profile is a promise, not a hint: where a capability is declared false, assert the corresponding event never appears — a negative assertion, not a skip. A host that under-declares is as much a bug as one that over-declares.

## Dependencies

- Depends on the fake host with a directives language (FEAT-3454) for a CI-runnable target; the suite is the reason that fake exists.
- Pairs with coverage: this suite is about whether the covered cases actually run. Whether an uncovered case went unnoticed is the complementary concern, tracked separately.
