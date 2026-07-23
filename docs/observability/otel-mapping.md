# OTel `gen_ai.*` attribute mapping (FEAT-2478)

little-loops emits OpenTelemetry-semantic-convention-shaped `gen_ai.*` attributes
for every host-CLI token-usage row **without** an OTel SDK in-process — the
canonical names are produced as plain dicts (`observability/tracing.py`) that
downstream consumers (Phoenix, Langfuse, Grafana) or the local `history.db`
reader can index directly. See EPIC-2456 § Tier 1, Goal #8.

## Internal name ↔ OTel-canonical attribute map

| Internal (Anthropic-API spelling) | OTel-canonical attribute | Notes |
|---|---|---|
| `input_tokens` | `gen_ai.usage.input_tokens` | identical in both conventions |
| `output_tokens` | `gen_ai.usage.output_tokens` | identical in both conventions |
| `cache_read_input_tokens` / `cache_read_tokens` | `gen_ai.usage.cache_read.input_tokens` | ⚠️ **dotted** sub-namespace, not underscore |
| `cache_creation_input_tokens` / `cache_creation_tokens` | `gen_ai.usage.cache_creation.input_tokens` | ⚠️ **dotted** sub-namespace, not underscore |
| _(per-CLI-invocation UUID4)_ | `gen_ai.invocation.id` | enables `GROUP BY` rollups matching raw usage totals |
| _(host runner → vendor)_ | `gen_ai.provider.vendor` | non-OTel-enum addendum: `anthropic` / `openai` / `google` / `other` |

### ⚠️ Cache-token names are dotted, not underscore

The two cache attributes use the **dotted** OTel-semconv sub-namespace
(`gen_ai.usage.cache_read.input_tokens`), **not** the underscore Anthropic-API
spelling prefixed with `gen_ai.usage.`. An OTel-semconv consumer — verified live
against `arize-phoenix 17.18.0` — **silently drops** the underscore form. The
`input_tokens`/`output_tokens` names are identical in both conventions, so only
the two cache attributes are affected.

## Provider vendor addendum

`gen_ai.provider.vendor` is a non-OTel-enum addendum (OTel semconv has no closed
vendor enum). `observability.tracing.vendor_for_runner(name)` maps a
`HostRunner.name` to a value:

| `HostRunner.name` | vendor |
|---|---|
| `claude-code` | `anthropic` |
| `codex` | `openai` |
| `gemini` | `google` |
| `opencode` / `pi` / `omp` / _unknown_ | `other` (provider-agnostic at the runner level) |

## Primitives

`observability/tracing.py` (exported from `little_loops.observability`):

- `OTelAttributes.from_usage(usage, vendor=None, invocation_id=None) -> dict` —
  shape a `TokenUsage` (or flat dict) into the canonical dotted `gen_ai.*` dict.
- `StampUsageEvent.usage_event(row, vendor=None, invocation_id=None) -> dict` —
  non-destructively augment a flat usage row (e.g. a `usage.jsonl` entry) with
  `gen_ai.*` keys, preserving the flat keys existing consumers read.
- `StreamingParityChecker.diff(blocking, streaming) -> list[ParityDiff]` /
  `.within_threshold(...)` — gate the ENH-2479 0.1% streaming-vs-blocking
  cache-token parity threshold across all four token fields.

## Persistence

- **`usage.jsonl`** (per-state, per-run) — the runner-written rows now carry the
  four dotted `gen_ai.usage.*` keys alongside the flat keys (additive; gated on
  `observability.otel_attributes.enabled`). Flat-key consumers
  (`fsm/cost_graph.py`, `_print_usage_summary`) ignore the extra keys.
- **`usage_events` table** (`history.db`, schema v21) — carries `invocation_id`
  (→ `gen_ai.invocation.id`) and `provider_vendor` (→ `gen_ai.provider.vendor`)
  columns; still `NULL` on parser-written rows (like `state`) since the
  backfill path has no invocation/vendor signal to attach. Schema v29 adds a
  `run_id` join key, populated by the live per-invocation writer at loop-run
  finish (`FSMExecutor._finish()` via `record_usage_event()`, ENH-2724) — that
  writer also populates `state`, unlike parser-written rows. Column names stay
  underscore/internal; the dotted OTel spelling is derived on read.

## Cost attribution query

`history_reader.cost_attribution(group_by="gen_ai.invocation.id")` returns a
per-`group_by` token/cost rollup over `usage_events`, keyed by the canonical
dotted OTel names. `group_by` accepts `gen_ai.invocation.id`,
`gen_ai.provider.vendor`, or a raw column (`session_id` / `model` / `state` /
`invocation_id` / `provider_vendor` / `run_id`); any other value raises
`ValueError` (the `GROUP BY` clause is whitelisted, never interpolated raw).

## Phoenix ingest

`phoenix serve` (≥ `arize-phoenix 15.10.0`) normalizes raw OTel `gen_ai.usage.*`
spans to OpenInference `llm.token_count.*` on ingest — no OpenInference shim
required. The parse fixture test (`test_otel_attributes.py::TestPhoenixIngest`)
is skipped when Phoenix is absent, so it gates only where Phoenix is installed.

| little-loops emits | Phoenix stores (`llm.token_count.*`) |
|---|---|
| `gen_ai.usage.input_tokens` | `llm.token_count.prompt` |
| `gen_ai.usage.output_tokens` | `llm.token_count.completion` |
| `gen_ai.usage.cache_read.input_tokens` | `llm.token_count.prompt_details.cache_read` |
| `gen_ai.usage.cache_creation.input_tokens` | `llm.token_count.prompt_details.cache_write` |

## Scope

- **In**: OTel attribute shaping, per-CLI `gen_ai.invocation.id` UUID, provider
  vendor addendum, streaming-parity checker, `cost_attribution()` query,
  `usage.jsonl` enrichment on the FSM host-invocation path.
- **Deferred** (mechanical follow-on): threading `on_usage_detailed` (and thus
  live `invocation_id`/`provider_vendor` writes) through the three optional
  callers — `cli/action.py`, `issue_manager.py::run_claude_command()`,
  `worker_pool.py::_run_claude_command()` — so the `ll-action` / `ll-auto` /
  `ll-parallel` paths also stamp `gen_ai.*`. Decision 2 = Option D
  (`/ll:decide-issue`, 2026-07-11): no gate forces the wider surface, and
  `subprocess_utils.py` already isolates `on_usage` / `on_usage_detailed` into
  independent branches, so the three callers are untouched today.
- **Verification**: EPIC-2456's F1 gate (`cache_read_input_tokens` populated on
  >50% of FSM iterations) is measured against `usage_events.cache_read_input_tokens`
  in `docs/observability/realized-savings-verification.md` (ENH-2719).
- **Out**: in-process OTel SDK / external collector adapter (consumers read from
  `history.db`, not the wire).
