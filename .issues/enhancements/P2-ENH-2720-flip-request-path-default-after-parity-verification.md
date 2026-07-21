---
id: ENH-2720
type: ENH
title: "Default-flip tranche: orchestration.request_path cli → sdk/batch after parity verification"
priority: P2
status: open
captured_at: '2026-07-21T17:22:20Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
parent: EPIC-2456
depends_on:
- ENH-2719
labels:
- token-cost
- caching
- configuration
relates_to:
- EPIC-2456
- ENH-2719
- FEAT-2673
- FEAT-2674
- FEAT-2710
- FEAT-2716
---

# ENH-2720: Default-flip tranche — orchestration.request_path cli → sdk/batch after parity verification

## Summary

Most of EPIC-2456's shipped savings are dormant behind opt-in config: `orchestration.request_path` defaults to `"cli"` (`config-schema.json`), and the cache-marking oracle (FEAT-2673), deferred tool loading (FEAT-2672), tool catalog (FEAT-2679/2680), speculative warming (FEAT-2674), and Message Batches (FEAT-2710/2716) are all only consulted under `"sdk"` or `"batch"`. Flip the default to `"sdk"` — and set `"batch"` per-loop where latency-insensitive — once ENH-2719's measurement runs demonstrate CLI/SDK parity and realized savings. This converts already-written code into realized $/run reduction; it is likely the cheapest remaining lever in the epic.

## Motivation

The 0.1×-read prompt-caching discount and the flat 50% Batches discount only apply on requests that actually travel the SDK/Batches path. With the default at `"cli"`, every `ll-loop`/`ll-auto`/`ll-sprint` invocation on an unconfigured project gets none of it. A default flip is a one-line schema/config change whose entire cost is the verification discipline — which ENH-2719 provides.

## Current Behavior

- `config-schema.json` `orchestration.request_path`: enum `["cli", "sdk", "batch"]`, `default: "cli"`. The schema's own descriptions note the CLI shell path "never carries a cache_control parameter" and "never serializes a tool-definition catalog at all."
- `.ll/ll-config.json` in this repo does not set `orchestration.request_path`, so even the source project runs dormant.
- Compression (FEAT-2675) is **already default-on** (executor wired from `BRConfig.compression` in `cli/loop/run.py`, trigger-gated at `trigger_pct=0.4`) — explicitly out of scope here; no flip needed.

## Expected Behavior

- `orchestration.request_path` defaults to `"sdk"` in `config-schema.json` (and any generated-config template), with `"cli"` remaining a supported explicit opt-out and the automatic fallback when the `anthropic` SDK import or API-key resolution fails — the flip must never hard-break a host that only has the CLI.
- Latency-insensitive automation surfaces (e.g. verify loops, background summarization states — candidates identified in FEAT-2710) get documented `"batch"` opt-in defaults, per-loop rather than global.
- The flip lands only after the gate below passes.

## Proposed Solution

1. **Gate (from ENH-2719's run set)**: N ≥ 10 real `ll-loop run` invocations under `request_path: "sdk"` across ≥2 distinct loops showing (a) exit-status/verdict parity with `"cli"` baselines on the same inputs, (b) no new failure modes in `usage_events`/run logs, and (c) measured `cache_read_input_tokens` share consistent with the F1 gate (>50% of iterations). Quantify realized $/run delta.
2. **Fallback audit**: confirm the SDK path's behavior when the `anthropic` package or `ANTHROPIC_API_KEY` is absent degrades to the CLI path (or a clear error) — the default must be safe on fresh installs and non-Anthropic hosts (Codex/OpenCode/omp adapters must be unaffected; `resolve_host()` scope check).
3. **Flip**: change the schema default; update `ll-init` template output if it stamps the key; CHANGELOG entry (concrete version section, not Unreleased).
4. **Batch tranche**: add `request_path: "batch"` (or per-state equivalent) to the identified latency-insensitive loop YAMLs, each with a note citing the 50% discount and the submit+poll latency tradeoff.

## Implementation Steps

1. Consume ENH-2719's parity/savings evidence; if the gate fails, close this as blocked-on-findings rather than flipping.
2. Audit and, if needed, harden the missing-SDK/missing-key fallback.
3. Flip the schema default + template output + docs + CHANGELOG.
4. Apply per-loop `"batch"` defaults.

## Integration Map

### Files to Modify
- `scripts/little_loops/config-schema.json` (`orchestration.request_path` default)
- `.ll/ll-config.json` (this repo's own setting, if kept explicit)
- Loop YAMLs selected for `"batch"` (per FEAT-2710's candidate list)
- `CHANGELOG.md`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` (`build_anthropic_request()` / `build_batch_request()` dispatch — verify fallback behavior, likely no change)
- `scripts/little_loops/config/features.py` (CacheConfig/deferred-tools docstrings referencing the opt-in)
- `ll-init` config generation (`init/` templates) if it stamps `orchestration.*`

### Similar Patterns
- FEAT-2716's SDK/Batches dispatch wiring and its test coverage of path selection.

### Tests
- Extend existing request-path dispatch tests to assert the new default resolves to `"sdk"` and that missing-SDK environments fall back cleanly.
- Existing `test_cache_control.py` / batches tests unchanged.

### Documentation
- `docs/ARCHITECTURE.md` orchestration.request_path documentation; `docs/reference/HOST_COMPATIBILITY.md` (non-Anthropic hosts unaffected).

### Configuration
- `config-schema.json` default change is the deliverable.

## Impact

- **Priority**: P2 — cheapest remaining $/run lever in EPIC-2456; converts shipped, dormant code into realized savings.
- **Effort**: Small once gated — the flip itself is a one-line default plus fallback audit; the gate's cost lives in ENH-2719.
- **Risk**: Medium — changes the default network path for every Anthropic-host invocation; mitigated by the parity gate and a hard requirement that missing-SDK environments degrade to CLI.
- **Breaking Change**: No for behavior/outputs (parity-gated); yes for the default transport, which is why the gate exists.

## Related Key Documentation

| Document | Relevance | Notes |
|---|---|---|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | **High** | Documents orchestration request-path dispatch (SDK/Batches, FEAT-2716). |
| [thoughts/plans/2026-07-02-token-cost-optimal-techniques.md](../../thoughts/plans/2026-07-02-token-cost-optimal-techniques.md) | Medium | Tier 2 caching rationale and vendor-measured anchors the flip unlocks by default. |

## Labels

`token-cost`, `caching`, `configuration`, `captured`

## Status

**Open** | Created: 2026-07-21 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-21T17:22:20Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9384c3a9-e5cf-4f15-a503-33c5d34b10c7.jsonl`
