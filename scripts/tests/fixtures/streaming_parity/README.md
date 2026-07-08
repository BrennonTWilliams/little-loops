# Streaming-vs-Blocking Cache-Accounting Parity — Trace Set (ENH-2479)

This directory contains the locked 3-trace fixture set used by
`scripts/tests/test_streaming_cache_parity.py` to verify that
`client.messages.create()` and `client.messages.stream()` return
matching token counts within a 0.1% relative tolerance across all
four token fields.

## Trace Catalog

| Trace ID | Pattern | Phase sequence |
|----------|---------|----------------|
| `trace_a_static_prefix_stable_turn_2` | Same system + skill blocks across 2+ turns; cache_read jumps on turn 2 | `write_with_pre_warmed_read` → `read_stable_prefix` |
| `trace_b_write_then_read_across_tool_result` | First turn writes cache; tool result lands; second turn reads it | `write_initial_prefix` → `read_across_tool_result` |
| `trace_c_tool_result_only_cache_hit` | Pure tool-result-only cache hit with no system-prefix change | `tool_result_no_prefix_change` → `tool_result_only_cache_hit` |

## Per-Trace File Layout

```
trace_<id>/
├── recorded.jsonl    # raw stream-json events verbatim (init + result per turn)
└── expected.jsonl    # per-turn {create, stream, phase, diff_pct, turn, model}
```

### `recorded.jsonl` row shape

Raw upstream stream-json events, one JSON object per line:

- Line 1: `{"type": "system", "subtype": "init", "model": "<model>"}`
- Line 2+: `{"type": "result", "model": "<model>", "usage": {<4 fields with UPSTREAM names>}}`

The wire field `cache_read_input_tokens` (and `cache_creation_input_tokens`) is the
upstream name; the rename boundary at `subprocess_utils.py:462-465` converts it to the
internal `cache_read_tokens` for downstream consumers. **The fixture preserves the
upstream names verbatim** so it can serve as a regression target for the rename
boundary itself.

### `expected.jsonl` row shape

One row per turn, structurally parallel to `recorded.jsonl`:

```json
{
  "turn": <int>,
  "model": "<model>",
  "create": {"input_tokens": <int>, "output_tokens": <int>, "cache_read_tokens": <int>, "cache_creation_tokens": <int>},
  "stream": {"input_tokens": <int>, "output_tokens": <int>, "cache_read_tokens": <int>, "cache_creation_tokens": <int>},
  "phase": "<trace-specific phase label>",
  "diff_pct": <float>
}
```

`expected.jsonl` uses **INTERNAL** field names (`cache_read_tokens`,
`cache_creation_tokens`) consistent with `subprocess_utils.py:462-465`. FEAT-2478's
production `StreamingParityChecker` consumes the same fixtures via
`importlib.resources` from the wheel-side mirror (see `rebuild.sh` for the dual-copy
sync contract).

## Parity Scope

All four token fields are covered per Decision 1 (parity scope = all four, not
cache_read only). Drift in any of `input_tokens`, `output_tokens`,
`cache_read_tokens`, or `cache_creation_tokens` would silently propagate to the
three downstream consumers (persistence writer, cost_graph reader, per-state
cost table).

## Synthetic vs Real Recordings

These fixtures are **synthetic-but-realistic test data** authored to exercise the
0.1% diff-assertion logic. The `create` and `stream` values match exactly
(`diff_pct=0.0`) so the test gates on the assertion machinery, not on a particular
SDK version's exact behavior. To replace with real recordings, see `rebuild.sh`.

## Test Wiring

- `scripts/tests/test_streaming_cache_parity.py` — test file
- `TestStreamingParityFixtures` class — sanity-checks directory structure
- `test_streaming_vs_blocking_cache_parity[trace_id]` — parametrize over the
  3 trace IDs, asserts 0.1% relative diff on all 4 fields per turn

## Coordination

- **FEAT-2478** — ships a wheel-side mirror of these fixtures under
  `scripts/little_loops/observability/fixtures/streaming_parity/`. `rebuild.sh`
  keeps both copies in sync.
- **ENH-2518** — sibling tier-0 trace set under the same EPIC-2456.
  Hand-authored `docs/observability/tier0-traces.md` and
  `docs/observability/streaming-parity-traces.md` should share a forward-compat
  convention (see `schema_version` envelope note in the rebuild script).
- **ENH-2475** — auto-generated `docs/observability/des-audit.md` is the only
  pre-existing file in `docs/observability/`.
