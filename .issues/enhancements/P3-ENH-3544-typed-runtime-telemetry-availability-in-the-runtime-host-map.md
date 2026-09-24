---
id: ENH-3544
type: ENH
title: Typed runtime telemetry availability in the runtime host map
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:14Z'
labels:
- observability
- multi-host
relates_to:
- ENH-3528
---

# ENH-3544: Typed runtime telemetry availability in the runtime host map

## Summary

Add typed telemetry availability to the runtime host map: per host, which metrics are available on which acquisition channel (e.g. live invocation usage vs. rollout usage), with explicit supported/unsupported/unknown entries. Split out of ENH-3528 (its first acceptance criterion) because it has no dependency on the reporting work.

## Current Behavior

- `RUNTIME_HOST_CAPABILITIES` (`little_loops.host_runner`) describes runtime operations; its `token_reporting` field is an advisory `ll-doctor` report, not structured data.
- `adapters/capabilities.py` is a build-time emission map and must not gain token fields.

## Expected Behavior

- A frozen telemetry-capability record per runtime host, keyed by metric and channel, covering every host in the runtime registry.
- The `token_reporting` text is derived from, or checked against, that record by `ll-verify-host-map`.
- Capabilities describe what a host *can* expose. They are never used to label a stored observation's provenance, and there is no `token_source_for(host)`.

## Scope Boundaries

- **In scope**: the typed runtime telemetry map, `token_reporting` parity, `ll-verify-host-map` coverage.
- **Out of scope**: observation provenance (ENH-3528); the build-time adapter map.

## Program Design

### Types

- `TelemetryAvailability = Literal["supported", "unsupported", "unknown"]`.
- `TelemetryCapability` (frozen dataclass): `metric: str`, `channel: str`, `availability: TelemetryAvailability`, `note: str | None`.
- `RUNTIME_HOST_CAPABILITIES` entries gain `telemetry: tuple[TelemetryCapability, ...]`.

### Signatures

- `main_verify_host_map() -> int` — extended to fail when a runtime host lacks telemetry entries or disagrees with `token_reporting`.

### Call Path

- `RUNTIME_HOST_CAPABILITIES` → `main_verify_host_map` (parity) and `ll-doctor` token-reporting output

## Integration Map

- `scripts/little_loops/host_runner.py`, `cli/verify_host_map.py`, `cli/doctor.py`.
- Tests: `test_host_runner.py`, `test_verify_host_map.py`, `test_cli_doctor.py`.

## Impact

- **Priority**: P3.
- **Effort**: Small.
- **Risk**: Low.

## Acceptance Criteria

- [ ] Every runtime host has explicit entries for each metric/channel; `ll-verify-host-map` fails when a host is missing.
- [ ] `token_reporting` agrees with the typed map (test).
- [ ] `ll-doctor` output is unchanged or updated with its tests.
- [ ] `docs/reference/HOST_COMPATIBILITY.md` documents the map.

## Status

**Open** | Created: 2026-09-24 | Priority: P3
