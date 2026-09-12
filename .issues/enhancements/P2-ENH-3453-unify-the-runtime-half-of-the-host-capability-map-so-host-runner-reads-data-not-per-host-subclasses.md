---
id: ENH-3453
title: Unify the runtime half of the host capability map so host_runner reads data, not per-host subclasses
type: ENH
priority: P2
status: open
discovered_date: '2026-09-11'
labels:
- multi-host
- ll-hosts
---

## Summary

The build-time half of the declarative host capability map shipped (ENH-2873, then ENH-2883 collapsing the emitters onto it): `adapters/capabilities.py` is data. The runtime half did not. `host_runner.HostCapabilities` is still one `describe_capabilities()` method per runner subclass, so adding a host still means writing a Python class, and the host seam cannot be isolated, tested as data, or versioned on vendor time separately from the engine.

Finish the half: have `host_runner` read runtime host capabilities from the same declarative map the adapter emitters already materialize at build time, so the runtime capability surface is data, not code.

## Current Behavior

Every runner subclass in `host_runner.py` implements its own `describe_capabilities()`, returning a `HostCapabilities` instance (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`, …), defaulted false and flipped true per host. Meanwhile `adapters/capabilities.py` already declares per-host build-time capabilities as data, and the emitters' policy decisions are driven from it. Two views of "what a host supports" therefore exist — one declarative (build-time), one procedural (runtime) — held consistent only by convention.

## Expected Behavior

- Runtime host capabilities are read from the declarative map, the same source the adapter emitters materialize at build time — not from per-subclass methods. A runner subclass may still exist for behavior that genuinely varies, but capability *declaration* is data.
- Adding a host, or correcting a capability flag, is a data change rather than a new subclass method.
- The build-time and runtime views cannot drift: one source of truth, mechanically enforced — the same discipline the `HOST_COMPATIBILITY.md` drift test already applies to the compatibility matrix.
- Nothing outside `host_runner` changes: consumers of `HostCapabilities` see the same object with the same fields.

## Design

- Mirror the build-time precedent exactly: ENH-2873 landed the map as data first, ENH-2883 collapsed the emitters onto it. Here the runtime side collapses in one step — declare once, read everywhere.
- Keep `HostCapabilities` as the runtime object. What changes is where its values come from, not what consumers receive.
- Scope check: this issue is the runtime capability map only. A declarative stanza that also covers CLI invocation shape (request templates, auth types, probe endpoints — a YAML host in place of a class) is a larger, separate piece of work; do not absorb it here.

## Why it matters

The host seam is the fastest-moving surface in this codebase — host code changes in roughly half of releases — and it is the one seam with no standard coming. Until capability declaration is data on both sides of it, "host-agnostic" is a claim maintained by discipline rather than a property enforced by construction, and the seam cannot be isolated behind a stable, testable interface.

## Program Design

### Types

- `HostCapabilities`: existing dataclass — shape preserved (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`, …)
- `RuntimeHostCapabilities`: materialized view of `adapters/capabilities.CAPABILITIES` for a single host_id at runtime (same fields, source differs)

### Signatures

- `load_runtime_capabilities(host_id: str) -> HostCapabilities` — reads the declarative map (the same one the adapter emitters materialize at build time) and returns a `HostCapabilities` instance
- `HostRunner.describe_capabilities(self) -> HostCapabilities` — becomes a thin wrapper: `return load_runtime_capabilities(self.host_id)` (or is deleted if the public surface moves to the factory)

### Call Path

`resolve_host(host_id)` (the factory) → `load_runtime_capabilities(host_id)` → reads `adapters/capabilities.CAPABILITIES[host_id]` → returns `HostCapabilities(...)` → consumers see the same object as before

## Impact

- **Priority**: P2 — host seam moves fastest in the codebase, but the runtime half is bounded: one new lookup function and per-subclass `describe_capabilities` removal.
- **Effort**: Medium — collapses N per-subclass methods (one per host) onto a single data-driven lookup; touches `host_runner.py` subclasses and the host-factory wiring.
- **Risk**: Medium — touches the public `HostCapabilities` shape and every consumer that reads it. Mechanical guardrail (HOST_COMPATIBILITY drift test extended to runtime surface) keeps build-time and runtime views from drifting again.
- **Breaking Change**: No — `HostCapabilities` fields and call sites are unchanged; only the source of the values moves from per-subclass methods to a declarative map.

## Scope Boundaries

- **In scope**: runtime capability *declaration* — replace per-subclass `describe_capabilities()` with a data-driven lookup sourced from the same map `adapters/capabilities.py` already uses.
- **Out of scope**: declarative CLI invocation shape — request templates, auth types, probe endpoints, replacing host subclasses with a YAML host (this is a larger, separate piece of work; ENH-3454 / 3456 territory).
- **Out of scope**: changing the `HostCapabilities` dataclass shape or any consumer-side field access.
- **Out of scope**: build-time emitter consolidation (already done in ENH-2873 / ENH-2883).

## Status

**Open** | Created: 2026-09-11 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-12T03:48:54 - `d9feb271-85a4-4dac-ac6d-ad5d11e623a8.jsonl`
