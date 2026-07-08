# Streaming-vs-Blocking Cache-Accounting Parity — Trace Set

> **ENH-2479 — F5 — Streaming-vs-blocking cache-accounting parity trace set**

This document describes the locked 3-trace fixture set that gates the
0.1% parity threshold between `client.messages.create()` and
`client.messages.stream()` for the four token fields the production
aggregation block (`fsm/executor.py:1462-1474`) sums into the
`action_complete` payload.

## Overview

When FEAT-2478 emits `gen_ai.usage.*` rows, it must decide which
client path (`create()` vs `stream()`) is the source of truth. The two
paths can return `cache_read_input_tokens` with small fractional drift
(typically from network variance, SDK version differences, or model
behavioral changes). Without a locked parity gate, drift accumulates
silently until cost-attribution graphs under-report.

The trace set in `scripts/tests/fixtures/streaming_parity/` locks three
canonical patterns so the gate recovers regressions, not just textbook
cases.

## Trace Catalog

| Trace ID | Pattern | Phase sequence |
|----------|---------|----------------|
| `trace_a_static_prefix_stable_turn_2` | Same system + skill blocks across 2+ turns; cache_read jumps on turn 2 | `write_with_pre_warmed_read` → `read_stable_prefix` |
| `trace_b_write_then_read_across_tool_result` | First turn writes cache; tool result lands; second turn reads it | `write_initial_prefix` → `read_across_tool_result` |
| `trace_c_tool_result_only_cache_hit` | Pure tool-result-only cache hit with no system-prefix change | `tool_result_no_prefix_change` → `tool_result_only_cache_hit` |

## Fixture Format

Per `scripts/tests/fixtures/streaming_parity/README.md`:

- `recorded.jsonl` — raw upstream stream-json events verbatim
  (`init` + `result` per turn, upstream field names)
- `expected.jsonl` — per-turn `{create, stream, phase, diff_pct, turn, model}`
  snapshots observed through both code paths at recording time
  (internal field names)

## Parity Scope

All four token fields:

- `input_tokens`
- `output_tokens`
- `cache_read_tokens` (internal; upstream: `cache_read_input_tokens`)
- `cache_creation_tokens` (internal; upstream: `cache_creation_input_tokens`)

A `cache_read`-only gate would silently pass drift in three of the four
fields. Three independent downstream consumers read all four with no
reconciliation layer:

1. `scripts/little_loops/fsm/persistence.py:710-727` — writer
2. `scripts/little_loops/fsm/cost_graph.py:184-254` —
   `CostReport.from_usage_jsonl(...)` reader
3. `scripts/little_loops/cli/loop/_helpers.py:1699-1702` →
   `_print_usage_summary` at `:1742` — CLI table aggregator

## Test Strategy

**Recorded-diff, not live-replay.** The test runtime only loads both
JSONL files and asserts `create.{f} == pytest.approx(stream.{f},
rel=0.001)` for each of the four fields. No `anthropic` import is
required at test time — the `rebuild.sh` helper gates on the SDK at
recording time only.

This means:

- CI runs without `ANTHROPIC_API_KEY`.
- Drift detection works against frozen baselines.
- The `--timeout=120` cap is not at risk from network variance on
  fixture loading.

## Rebuild Procedure

See `scripts/tests/fixtures/streaming_parity/rebuild.sh` (the first
such helper in the entire repo). Run when:

1. Anthropic ships a new SDK version that changes how the cache
   fields are reported.
2. The upstream wire-protocol field names change.
3. A new model variant is added whose behavior drifts in `create()`
   vs `stream()`.
4. The internal rename boundary at `subprocess_utils.py:462-465`
   changes.

## Coordination with FEAT-2478

FEAT-2478's production `StreamingParityChecker` ships its own copy of
the fixtures under
`scripts/little_loops/observability/fixtures/streaming_parity/`
(wheel-packagable via `[tool.hatch.build.targets.wheel] packages =
["little_loops"]`, line 129-131). The two copies are kept in sync via
`rebuild.sh`, which regenerates both directories from the same
captured run.

**Why dual-copy, not single?** The wheel config at
`pyproject.toml:129-131` only packages `little_loops/**`, NOT
`scripts/tests/fixtures/`. The pytest-side fixtures are unreachable
from an installed wheel via `importlib.resources`, so FEAT-2478 must
ship its own wheel-side copy. `rebuild.sh` is the sync mechanism.

**Schema-version envelope (forward-compat):** both copies carry a
`schema_version` envelope per ENH-2518's forward-compat invariants.
Mismatched `schema_version` between the two copies is a coordination
break that should fail loudly in CI.

## Forward-Compat

Sibling docs in `docs/observability/`:

- `tier0-traces.md` (ENH-2518) — tier-0 verification trace set under
  the same EPIC-2456
- `des-audit.md` (ENH-2475) — auto-generated DES variant registry
  (only pre-existing hand-authored doc; landing zone for variant-class
  metadata)
- `otel-mapping.md` (FEAT-2478) — OTel `gen_ai.usage.*` attribute
  emission contract

Future writers of sibling fixtures should share a common
`schema_version` envelope convention. The `expected.jsonl` row shape
in this directory is the first such convention; subsequent sibling
docs should add to the same envelope family.

## Decision History

Four architectural decisions are locked in the issue file at
`.issues/enhancements/P2-ENH-2479-...md` (lines 670-806):

1. Parity scope = all 4 token fields
2. Fixture shape = `expected.jsonl` (per-turn row)
3. Test strategy = recorded-diff (no live SDK at test time)
4. Fixture packaging = wheel-side mirror (FEAT-2478)

These decisions supersede the original "Implementation Steps" in the
issue and were locked on 2026-07-08 after a Drift Audit pass.
