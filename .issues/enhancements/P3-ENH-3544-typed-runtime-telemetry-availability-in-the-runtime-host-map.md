---
id: ENH-3544
type: ENH
title: Typed runtime telemetry availability in the runtime host map
priority: P3
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:14Z'
labels:
- observability
- multi-host
relates_to:
- ENH-3528
- ENH-3648
blocks:
- ENH-3534
---

# ENH-3544: Typed runtime telemetry availability in the runtime host map

## Summary

Add typed telemetry availability to the runtime host map: per host, which metrics are available on which acquisition channel (e.g. live invocation usage vs. rollout usage), with explicit supported/unsupported/unknown entries. Split out of ENH-3528 (its first acceptance criterion) because it has no dependency on the reporting work.

## Current Behavior

- `RUNTIME_HOST_CAPABILITIES` (`little_loops.host_runner`) describes runtime operations as `CapabilityEntry(name, level, note)` report rows. A `token_reporting` row exists **only for `codex`** (level `"full"`, prose note); the other seven production hosts have none. Doctor's `_ADVISORY_CAPABILITIES` set lists the "token_reporting" row name as advisory.
- The existing row vocabulary is `full`/`unsupported`/…, not `supported`/`unsupported`/`unknown`.
- Metric naming is split: `usage_events` columns are `cache_read_input_tokens`/`cache_creation_input_tokens`, while `TokenUsage` fields are `cache_read_tokens`/`cache_creation_tokens`.
- `usage_events.channel` values are `live` and `transcript` today (v53); ENH-3532 adds `rollout`. `context_hook` is not a `usage_events` channel.
- `adapters/capabilities.py` is a build-time emission map and must not gain token fields.

## Expected Behavior

- A frozen telemetry-capability record per runtime host, keyed by metric and channel, covering every host in the runtime registry.
- The `token_reporting` text is derived from, or checked against, that record by `ll-verify-host-map`.
- Capabilities describe what a host *can* expose. They are never used to label a stored observation's provenance, and there is no `token_source_for(host)`.

### Availability semantics and evidence

`supported` means version/channel evidence establishes that the host can expose the metric (directly or with a verified normalization). `unsupported` means evidence establishes absence or inapplicability; lack of a captured sample or missing little-loops ingestion is `unknown`, not proof of unsupported capability. Notes identify the producer version/acquisition evidence and limitations. Capability never certifies a particular stored observation.

Do not overload native availability with ingestion implementation status. If doctor discusses both, render them separately; ENH-3534 can add ingestion while leaving a previously supported native metric unchanged. Derive the `token_reporting` report summary from the typed entries with a documented deterministic rule, preserving distinctions between partial channel/metric support and complete absence. Do not compare arbitrary prose strings as the parity contract.

Required host coverage is the production registry excluding `TEST_ONLY_HOSTS` (currently eight hosts). Scripted fake hosts remain test-only; tests prove the exclusion and verify that adding a production host without a complete matrix fails.

### Decisions recorded 2026-09-28 (epic review)

- **`token_reporting` for hosts without a row:** derive a `token_reporting` report row for every production host from its typed entries, so all eight report consistently. This changes `ll-doctor` output for seven hosts; update doctor tests accordingly. Mapping rule: all consumption metrics `supported` on at least one channel → `full`; some `supported` → `partial`; none `supported` but some `unknown` → `unknown`; all `unsupported` → `unsupported`. The existing Codex prose note moves into the typed entries' notes.
- **Metric names:** use the `usage_events` column names (`cache_read_input_tokens`, `cache_creation_input_tokens`), since the map describes stored/exposed metrics; document the mapping to `TokenUsage` field names beside the `TelemetryMetric` literal.
- **Channels:** `live`, `rollout`, `transcript` match `usage_events.channel` values; `context_hook` is an occupancy-only channel with no `usage_events` rows. Document that.
- **Initial evidence:** only `claude-code` (ENH-3546 evidence where landed, else `unknown`) and `codex` (BUG-3531 fixtures, `codex-cli 0.152.1`) get non-`unknown` entries here. The other six stay `unknown` until ENH-3648's survey supplies evidence.
- **Matrix construction:** 8 hosts × 5 metrics × 4 channels = 160 pairs. Build each host's tuple with a helper that takes explicit overrides and fills the remaining pairs with `unknown` + a fixed "not investigated" note. The helper rejects unknown vocabulary and duplicate overrides. A registered production host whose entry has no `telemetry` argument at all still fails verification.

## Scope Boundaries

- **In scope**: the typed runtime telemetry map, `token_reporting` parity, `ll-verify-host-map` coverage.
- **Out of scope**: observation provenance (ENH-3528); the build-time adapter map.

## Program Design

### Types

- `TelemetryAvailability = Literal["supported", "unsupported", "unknown"]`.
- `TelemetryMetric = Literal["input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "context_occupancy_tokens"]` — normalized disjoint consumption components plus the separate occupancy metric.
- `TelemetryChannel = Literal["live", "rollout", "transcript", "context_hook"]`.
- `TelemetryCapability` (frozen dataclass): `metric: TelemetryMetric`, `channel: TelemetryChannel`, `availability: TelemetryAvailability`, `note: str | None`.
- The required matrix is the Cartesian product of these metrics/channels for each production runtime host. Reject unknown vocabulary and duplicate pairs, as well as omissions. An inapplicable pair is explicitly unsupported; an uninvestigated pair is unknown.
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

- [ ] The closed metric/channel vocabulary and required matrix are documented; missing pairs, duplicate pairs, and unknown keys fail verification.
- [ ] Tests distinguish unsupported from uninvestigated and native capability from ingestion support; supported claims carry version/channel evidence.
- [ ] Test-only hosts are explicitly excluded, and a newly registered production host without telemetry entries fails.
- [ ] A deterministic typed-map-to-report summary covers partial metric/channel support; doctor does not imply unsupported ingestion means the producer lacks usage.

- [ ] Every runtime host has explicit entries for each metric/channel; `ll-verify-host-map` fails when a host is missing.
- [ ] `token_reporting` agrees with the typed map (test).
- [ ] `ll-doctor` output is unchanged or updated with its tests.
- [ ] `docs/reference/HOST_COMPATIBILITY.md` documents the map.

## Status

**Open** | Created: 2026-09-24 | Priority: P3
