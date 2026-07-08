# Tier 0 Verification Trace Set

> **ENH-2518 — Tier 0 — EPIC-2456 token-cost baseline trace set**

This document describes the locked Tier 0 trace set used to measure
FEAT-2470's behavioral quick-wins (EPIC-2456 Tier 0 success gate). The
trace set is the moving-target anchor: any before/after cost delta is
measured against this set, not against whatever `general-task-*` runs
happen to be on disk.

## When to Use This Guide

Use this when you:

- Add or refresh a Tier 0 trace (the set is locked, additions are gated
  by `>= 2` and `single_model_only`).
- Compute a FEAT-2470 before/after delta and need to know which traces
  to diff against.
- Add a downstream consumer (ENH-2477 F6, FEAT-2476 cost ceiling, FEAT-2478
  OTel extension) and need to know the exact aggregation order.
- Diagnose why a fixture or test fails (the schema, the envelope, the
  forward-compat invariants).

## Table of Contents

- [Locked Trace Set](#locked-trace-set)
- [Fixture Layout](#fixture-layout)
- [Manifest Format](#manifest-format)
- [Per-Trace Envelope](#per-trace-envelope)
- [Aggregation Order](#aggregation-order)
- [Forward-Compat](#forward-compat)
- [Coordination](#coordination)

---

## Locked Trace Set

| Trace ID | Rows | States | Cache footprint (read) | Single-model |
|---|---|---|---|---|
| `general-task-20260608T194041` | 56 | 6 (canonical) | ~14.75M | `claude-sonnet-4-6` |
| `general-task-20260619T225602` | 93 | 7 (superset + `summarize_partial`) | ~48.07M | `claude-sonnet-4-6` |

The trace set contains two single-model general-task runs whose
`usage.jsonl` rows parse cleanly under `CostReport.from_usage_jsonl`.

**Why >= 2 and not 3-5**: the original AC required 3-5 traces. A supposed
third candidate (`.loops/runs/general-task-20260530T143631/`) exists but
is empty — no `usage.jsonl`, no artifacts. The `>= 2` relaxation reuses
the `>=` threshold precedent at `scripts/tests/test_policy_builder_corpus.py:51-52`.
The deviation is documented inline at `_meta.count_relaxation_note` so
future re-aggregation consumers see it without reading the issue.

## Fixture Layout

```
scripts/tests/fixtures/tier0_traces/
├── manifest.json
├── general-task-20260608T194041.json
└── general-task-20260619T225602.json
```

All three files are load-bearing: deleting any one breaks the locked-set
test gate at `scripts/tests/test_tier0_traces.py`.

## Manifest Format

`manifest.json` enumerates the locked set. The `_meta` envelope follows
the `_meta` convention enforced by:

- `scripts/tests/test_issue_template.py:42-49` (asserts `_meta.version`
  and `_meta.type`)
- `scripts/tests/test_init_core.py:2536-2551` (asserts
  `_meta.command_options` is present and non-empty)
- `scripts/little_loops/init/detect.py:63-169` (reads `_meta` to drive
  detection logic)

Model the `_meta` block on `scripts/little_loops/templates/python-generic.json`
shape: a flat dict with `name` / `description` / `tags` plus
domain-specific fields (`schema_version`, `owner`, `epic`, `tier`,
`lock_date`, `baseline_source`, `aggregation_consumer`,
`count_relaxation_note`).

Required keys:

| Key | Type | Purpose |
|---|---|---|
| `_meta.schema_version` | string | Forward-compat slot for FEAT-2476 / FEAT-2478 bumps |
| `_meta.type` | string | `"tier0_traces_manifest"` |
| `_meta.owner` | string | Citing issue ID (`"ENH-2518"`) |
| `_meta.tier` | string | `"tier-0"` |
| `_meta.epic` | string | `"EPIC-2456"` |
| `_meta.aggregation_consumer` | string | Canonical anchor path (`scripts/little_loops/fsm/cost_graph.py:CostReport.from_usage_jsonl`) |
| `_meta.count_relaxation_note` | string | Inline deviation justification |
| `traces[]` | array | Each entry: `{id, path, loop}` |

## Per-Trace Envelope

Each `<trace_id>.json` carries the verbatim parsed `usage.jsonl` rows
plus precomputed aggregates. Required keys:

| Key | Type | Purpose |
|---|---|---|
| `schema` | string | `"usage_jsonl_v1"` |
| `trace_id` | string | Loop run directory name |
| `source_path` | string | Relative path to original `usage.jsonl` |
| `model` | string | Locked single-model (`"claude-sonnet-4-6"`) |
| `has_unknown_model` | bool | AND of all bucket-level flags (false for locked set) |
| `rows[]` | array | Verbatim parsed `usage.jsonl` rows (RFC3339 `+00:00` preserved) |
| `totals.input_tokens` | int | Sum across all rows |
| `totals.output_tokens` | int | Sum across all rows |
| `totals.cache_read_tokens` | int | Sum across all rows (kept SEPARATE from cache_creation per `cost_graph.py:225-243`) |
| `totals.cache_creation_tokens` | int | Sum across all rows |
| `totals.baseline_cost_usd` | float | Sum of `estimate_cost_usd(...)` across priced rows |
| `states.<name>.input_tokens` | int | Per-state sum |
| `states.<name>.output_tokens` | int | Per-state sum |
| `states.<name>.cache_read_tokens` | int | Per-state sum (separate) |
| `states.<name>.cache_creation_tokens` | int | Per-state sum (separate) |
| `states.<name>.cost_usd` | float | Per-state sum |
| `states.<name>.wallclock_ms` | int | Per-state sum |
| `states.<name>.iterations` | int | Row count for this state |
| `budget_accumulator` | object | Reserved `{}` for FEAT-2476 `--max-cost` ceiling |

**Per-state keys MUST match the state names that appear in
`usage.jsonl`**, not a fixed canonical set. Trace 1's `states` map has 6
entries; trace 2's `states` map has 7 entries (the additional
`summarize_partial` is a superset, not a replacement).

**RFC3339 preservation**: real `usage.jsonl` rows use `+00:00` suffix
(e.g. `"2026-06-09T00:41:04.755670+00:00"`), NOT the `Z` suffix used in
synthetic test rows. The per-trace JSON's `rows` field preserves the
on-disk format verbatim — do not normalize to `Z` (downstream diffs
must stay byte-stable).

## Aggregation Order

The fixture's per-state aggregates and totals are computed via the
canonical consumer at
`scripts/little_loops/fsm/cost_graph.py:CostReport.from_usage_jsonl`
(`cost_graph.py:184-254`). The CLI table aggregator at
`scripts/little_loops/cli/loop/_helpers.py:1742-1767`
(`_print_usage_summary`) is a thin delegator that calls
`CostReport.from_usage_jsonl` and prints the pre-sorted table.

Five behavioral nuances the implementer must respect:

1. **`cache_read` and `cache_creation` stay distinct internally, collapse
   in the print column.** `CostReport.from_usage_jsonl`
   (`cost_graph.py:225-243`) accumulates the two channels independently
   per state. `PerStateCost.table_row()` (line 96) renders them as a
   single combined `"cache"` column. The per-trace JSON envelope keeps
   them separate (so F6 ENH-2477 can attribute cost per channel); only
   the print path collapses them.

2. **`model` is consumed per-row but not stored in the bucket.** The
   refactored `CostReport.from_usage_jsonl` reads `model` from each row
   only to feed `estimate_cost_usd(...)` (`cost_graph.py:241`); it is
   NOT retained on the per-state aggregate. For locked single-model
   traces this is a no-op.

3. **`has_unknown_model` is bucket-poisoned, not row-poisoned.** A
   single `estimate_cost_usd(...)` returning `None` flips the entire
   bucket's `has_unknown_model` to `True` and renders the printed cost
   as `"n/a"` (`cost_graph.py:241-246, 97`). The fixture-level
   `has_unknown_model: false` is therefore the AND of all bucket-level
   flags; an implementer adding a third trace that touches a non-Claude
   model must either ensure that trace's `model` resolves in
   `MODEL_PRICING` or relax this assertion.

4. **Print output is sorted lexicographically, not in YAML order.**
   `cost_graph.py:136` (`CostReport.table()`) iterates
   `sorted(self.states, key=lambda s: s.state)` to render rows. The
   per-trace fixture's `states: {...}` map may preserve canonical order
   for human readability, but downstream diff consumers MUST sort
   before comparing — otherwise F6 re-aggregation diffs will be
   order-sensitive.

5. **RFC3339 timestamps preserved verbatim.** The `rows` field preserves
   the on-disk `+00:00` suffix; downstream diff consumers must NOT
   normalize to `Z`.

## Forward-Compat

Three future-facing slots in the envelope shape:

| Slot | Reserved for | Bump semantics |
|---|---|---|
| `_meta.schema_version` | FEAT-2476 (cost ceiling) + FEAT-2478 (OTel `gen_ai.usage.*`) | Increment when adding or removing top-level envelope keys |
| `budget_accumulator` (per-trace) | FEAT-2476 `--max-cost` ceiling data | Stays `{}` until FEAT-2476 populates it; consumers treat `{}` as "no ceiling recorded" |
| `has_unknown_model` (per-trace, per-state, totals) | Cross-host token compatibility (ENH-2479 `[^tok]` footnote at `docs/reference/HOST_COMPATIBILITY.md:132`) | Stays `false` for Claude-only traces; flips to `true` for non-Claude model rows until pricing entries are added |

When `observability/tracing.py` lands (FEAT-2478), per-trace rows gain
`gen_ai.usage.*` fields; the envelope schema bumps gracefully via the
reserved `_meta.schema_version` slot.

## Coordination

Siblings in `docs/observability/`:

- [`des-audit.md`](des-audit.md) — auto-generated DES variant registry
  (the only pre-existing hand-authored doc; landing zone for
  variant-class metadata)
- [`streaming-parity-traces.md`](streaming-parity-traces.md) — ENH-2479
  F5 streaming-vs-blocking parity trace set, landed 2026-07-08
- [`otel-mapping.md`](otel-mapping.md) — FEAT-2478 OTel `gen_ai.usage.*`
  attribute emission contract (when it lands)

Downstream consumers of this fixture:

- **ENH-2477 (F6 per-state cost attribution)** — reads the `states`
  map directly. Per-state keys must use the same names as
  `scripts/little_loops/loops/general-task.yaml:32+`. F6 must tolerate
  the trace-2 superset (`summarize_partial` in addition to the canonical
  6 states), not assume exact equality.

- **FEAT-2476 (cost ceiling)** — writes to `budget_accumulator` per
  trace. Reserved shape `{}` until FEAT-2476 lands.

- **FEAT-2478 (OTel)** — when `observability/tracing.py` lands, rows
  gain `gen_ai.usage.*` fields and the envelope schema bumps via
  `_meta.schema_version`.

- **EPIC-2456 Tier 0 measurement** — computes FEAT-2470's before/after
  delta as `current_cost - this_fixture.baseline_cost_usd` and stamps
  the result into the manifest's `_meta` envelope as a follow-on commit.

## See Also

- `scripts/little_loops/fsm/cost_graph.py:184-254` — `CostReport.from_usage_jsonl` (canonical aggregator)
- `scripts/little_loops/fsm/cost_graph.py:71-82` — `PerStateCost.to_dict` (locked per-state shape)
- `scripts/little_loops/cli/loop/_helpers.py:1742-1767` — `_print_usage_summary` (thin delegating wrapper)
- `scripts/little_loops/pricing.py:10-55` — `MODEL_PRICING` constants
- `scripts/tests/test_tier0_traces.py` — regression test gate
- `scripts/tests/fixtures/policy_builder/conformance_corpus.json` — closest analog precedent (top-level indexed case-list)
- `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` — parent epic
- `.issues/features/P2-FEAT-2470-tier-0-token-cost-behavioral-quick-wins.md` — the work this set measures