---
id: FEAT-2478
title: "F5 — OTel gen_ai.usage.* emission + streaming parity + UUID + provider addendum"
type: FEAT
priority: P2
status: open
captured_at: "2026-07-04T20:05:34Z"
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to: [ENH-2475, ENH-2477, FEAT-2476, ENH-2461]
labels:
  - token-cost
  - observability
  - otel
  - streaming
  - fsm
  - tier-1
---

# FEAT-2478: F5 — OTel `gen_ai.usage.*` emission

## Summary

Add OpenTelemetry-shaped `gen_ai.usage.*` attribute emission on every FSM
host invocation, plus per-CLI-invocation `gen_ai.invocation.id` UUID
stamping and a non-OTel-enum `gen_ai.provider.vendor` addendum.
Concurrent with emission, address streaming-vs-blocking
`cache_read_input_tokens` parity. This is EPIC-2456 § Children
[TBD-6] — directly serves Goal #8 in the EPIC.

## Motivation

Today the cost telemetry surface is in `.ll/history.db` (`usage_event`
table) but uses ad-hoc attribute names; downstream consumers can't
reuse off-the-shelf OTel dashboards (Phoenix, Langfuse, Grafana) without
shim code. F5 emits the canonical OTel attribute set so those
consumers work, but does so without an OTel SDK in-process — it writes
shaped rows directly into `history.db`.

The streaming-parity piece is because `client.messages.create()` and
`client.messages.stream()` return `cache_read_input_tokens` differently
at small fractions; locking a parity test prevents drift.

The `gen_ai.invocation.id` UUID lets `GROUP BY gen_ai.invocation.id`
rollups match raw `result`-event `usage` totals row-for-row.

## Current Behavior

- `scripts/little_loops/fsm/executor.py:1295–1305` aggregates
  `cache_read_tokens` / `cache_creation_tokens` per state into the
  `usage_event` table.
- `scripts/little_loops/subprocess_utils.py:50–51, 462–465` capture
  the same fields into a `UsageEvent`. Attribute names are internal
  (`cache_read_tokens`), not OTel canonical.
- No `gen_ai.invocation.id` UUID stamp; no `gen_ai.provider.vendor`
  addendum.

## Expected Behavior

- `usage_event` rows carry OTel-canonical attribute names alongside
  the existing fields:
  - `gen_ai.usage.input_tokens` (= `input_tokens`)
  - `gen_ai.usage.output_tokens` (= `output_tokens`)
  - `gen_ai.usage.cache_read_input_tokens` (= `cache_read_tokens`)
  - `gen_ai.usage.cache_creation_input_tokens` (= `cache_creation_tokens`)
  - `gen_ai.invocation.id` — UUID4 stamped per CLI invocation
  - `gen_ai.provider.vendor` — `anthropic` / `openai` / `gemini` /
    `mistral` / `<other>` (non-OTel-enum value carried as a
    semantic-convention addendum)
- The `phoenix serve` parser accepts emitted rows (verify via fixture).
- Streaming `cache_read_input_tokens` matches blocking within 0.1% on
  the locked 3-trace set (TBD-7 / ENH-2479).
- `history_reader.cost_attribution()` exposes a `GROUP BY
  gen_ai.invocation.id` query.

## Proposed Solution

1. **`scripts/little_loops/observability/tracing.py`** (new, ~110
   LOC + ~30 streaming):
   - `OTelAttributes.from_usage(usage_event, vendor, invocation_id)` —
     emits the canonical attribute dict
   - `StampUsageEvent.usage_event(...)` — stamps an existing
     `UsageEvent` row with `gen_ai.*` keys + UUID
   - `StreamingParityChecker.diff(blocking_usage, streaming_usage)` —
     returns the per-field mismatch; gates the 0.1% threshold

2. **`scripts/little_loops/subprocess_utils.py:462–465`**:
   - On every `UsageEvent` capture, call `OTelAttributes.from_usage`
   - Stamp `gen_ai.invocation.id` from a per-CLI-invocation UUID
     (declared once in `__main__.py` and threaded through)

3. **`scripts/little_loops/history_reader.py`** (new query):
   ```python
   def cost_attribution(group_by: str = "gen_ai.invocation.id"):
       # returns rows: invocation_id, state, sum(input_tokens), ...
   ```

4. **`scripts/little_loops/cli/loop/__main__.py`**: declare
   `invocation_id = uuid4()` at start of process; thread through.

5. **Streaming parity**: every CLI invocation that uses streaming
   captures both `messages.create()` and `messages.stream()` results on
   a 5-call sample; `StreamingParityChecker` flags drifts >0.1% on
   `cache_read_input_tokens`.

## Integration Map

### Files to Modify

- `scripts/little_loops/observability/tracing.py` (new)
- `scripts/little_loops/subprocess_utils.py:462–465` — stamp
- `scripts/little_loops/cli/loop/__main__.py` — invocation UUID
- `scripts/little_loops/history_reader.py` — `cost_attribution()`
- `scripts/little_loops/fsm/executor.py:1295` — verify rows carry
  OTel keys

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/ctx_stats.py` — surfaces
  `cost_attribution()` rows
- `ENH-2461` persistence layer — `input_tokens` etc. must come from
  this layer, not a parallel source — coordinate carefully
- `FEAT-2123` (Codex/OpenCode parity) — `gen_ai.provider.vendor`
  values expand to non-Claude hosts

### Similar Patterns

- `scripts/little_loops/observability/__init__.py` (if exists) —
  extend instead of creating a parallel sibling
- The `invocation_id` UUID pattern mirrors `correlation_id` in
  `fsm/executor.py` (check for existing)

### Tests

- `scripts/tests/test_otel_attributes.py` (new) — attribute name
  mapping; UUID uniqueness across invocations; vendor addendum for
  non-OTel enums; DES schema accept rate 100%
- `scripts/tests/test_streaming_cache_parity.py` (new) — gates the
  0.1% parity threshold on the 3-trace set (ENH-2479)

### Documentation

- `docs/reference/API.md` — `observability/tracing.py` module
- `docs/ARCHITECTURE.md` — Token cost layer section
- `docs/observability/otel-mapping.md` — internal-name ↔ OTel-canonical
  attribute map

### Configuration

- `.ll/ll-config.json` — `observability.otel_attributes.enabled`
  default `true`; `observability.streaming_parity.check` default
  `true`

## Implementation Steps

1. Land **ENH-2475** (DES audit) first — required prerequisite
2. Author `observability/tracing.py` with `OTelAttributes` +
   `StampUsageEvent` + `StreamingParityChecker`
3. Stamp rows in `subprocess_utils.py:462–465`
4. Add `gen_ai.invocation.id` UUID at CLI start
5. Add `history_reader.cost_attribution()` query
6. Run streaming-parity gate (covered by ENH-2479 trace set)
7. Verify Phoenix `serve` parses emitted rows (optional fixture)
8. Coordinate lock: attribute name mappings to **ENH-2461**
   persistence layer
9. `python -m pytest scripts/tests/` exits 0

## Acceptance Criteria

- `usage_event` rows contain all `gen_ai.usage.*` keys plus
  `gen_ai.invocation.id` + `gen_ai.provider.vendor`
- `history_reader.cost_attribution(group_by="gen_ai.invocation.id")`
  returns one row per invocation; sum across rows matches raw
  `result`-event `usage` totals exactly
- Streaming vs blocking `cache_read_input_tokens` matches within 0.1%
  on the ENH-2479 trace set
- Phoenix fixture parse test passes (Phoenix optional; test is
  skipped when absent — gates only where Phoenix is installed)
- `python -m pytest scripts/tests/` exits 0

## Scope Boundaries

- **In**: OTel attribute emission + UUID stamping + provider addendum +
  parity check + cost-attribution query
- **Out**: OTel SDK install (we emit shaped rows into `history.db`
  directly per EPIC replication-not-integration stance); an external
  collector adapter (Phoenix / Langfuse consumers read from
  `history.db`, not the wire)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent; § Tier 1 [TBD-6], Goal #8 |
| `ENH-2475` (DES audit) | Hard prerequisite for canonical schema |
| `ENH-2461` | Persistence layer whose columns map onto `gen_ai.usage.*` |
| `FEAT-2123` | Cross-host parity — vendor addendum must cover OpenAI/Gemini/etc. |

## Impact

- **Priority**: P2 — direct input to OTel-style dashboards; enables
  external consumers
- **Effort**: Medium — ~150 LOC + 30 streaming parity
- **Risk**: Medium — first emission of OTel-shaped attributes; name
  mismatch with downstream consumers is a tracked risk
- **Breaking Change**: No — additive fields; existing `usage_event`
  columns unchanged

## Status

**Open** | Created: 2026-07-04 | Priority: P2

## Session Log

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
