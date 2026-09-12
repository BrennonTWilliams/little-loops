---
id: 3456
title: Prove host-agnosticism with two deliberately divergent fakes, not one
type: ENH
priority: P3
status: open
discovered_date: '2026-09-11'
labels: []
---

## Summary

The fake host (FEAT-3454) and the behavioral conformance suite (FEAT-3455) both assume a single fake. A single fake proves the code runs; it cannot prove the code is agnostic, because that one fake's action and observation shapes may be silently baked into the surface under test. The assertion only becomes real with a second fake whose shapes deliberately disagree with the first — different action vocabulary, different observation structure — composed through the same abstract interface, with the test asserting the layer under test touches only that interface and never a concrete shape.

## Why now

This is timing-sensitive rather than large. It is cheap to add while the fake host is still being built and its shape has not hardened; it gets progressively more expensive once code accretes around a single fake's assumptions. Scope is one additional fake plus the composition test, not a redesign of either.

## Design

- One additional fake host whose action and observation shapes deliberately diverge from the first: different action vocabulary, different observation structure, a different capability profile.
- A composition test that drives both fakes through the same executor paths and asserts the multi-host layer touches only the abstract host interface — never a concrete shape.
- The proven pattern elsewhere is exactly this test: the framework it is borrowed from keeps its largest test file as a composition of two deliberately divergent dummies asserting only-interface access, because one fake proves a layer runs while two prove it is agnostic.

## Scope

Distinct from parity-testing generated artifacts against their declarations — a different axis. This is about whether the host surface itself is genuinely shape-independent.
