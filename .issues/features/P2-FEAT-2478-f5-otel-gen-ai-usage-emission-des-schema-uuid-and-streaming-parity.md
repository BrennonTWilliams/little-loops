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
relates_to: [ENH-2475, ENH-2477, FEAT-2476, ENH-2479, ENH-2461]
depends_on: [ENH-2475, ENH-2479]
labels:
  - token-cost
  - observability
  - otel
  - streaming
  - fsm
  - tier-1
decision_needed: false
learning_tests_required:
  - anthropic
  - phoenix
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
  - `gen_ai.usage.cache_read.input_tokens` (= `cache_read_tokens`)
    — ⚠️ **dotted**, not `cache_read_input_tokens`; see Premise Note
  - `gen_ai.usage.cache_creation.input_tokens` (= `cache_creation_tokens`)
    — ⚠️ **dotted**, not `cache_creation_input_tokens`; see Premise Note
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
  `cost_attribution()` rows. NOTE: this CLI's cache-hit-rate calc
  (lines ~184-240, 296-300, 378) is an **independent** code path that
  parses raw Claude Code session JSONL directly and sums
  `cache_read_input_tokens`/`cache_creation_input_tokens`/
  `input_tokens` — it is not wired through `subprocess_utils`/
  `history_reader` at all, so F5 won't break it, but the field-name
  overlap with the raw Anthropic API names is a naming-consistency
  point worth resolving alongside the `gen_ai.*` vocabulary.
- `ENH-2461` persistence layer — `input_tokens` etc. must come from
  this layer, not a parallel source — coordinate carefully
- `FEAT-2123` (Codex/OpenCode parity) — `gen_ai.provider.vendor`
  values expand to non-Claude hosts

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py` (~line 637-650) — writes
  `usage.jsonl` per state by copying flat keys off the
  `action_complete` event dict (`input_tokens`, `output_tokens`,
  `cache_read_tokens`, `cache_creation_tokens`), gated on
  `"input_tokens" in event`. **Second, independent consumer of the
  action_complete payload shape** — if `gen_ai.*`-namespaced keys are
  added to (or replace) the flat keys, this block must be updated or
  the new attributes never reach `usage.jsonl`.
- `scripts/little_loops/cli/loop/_helpers.py` — `_print_usage_summary()`
  (~line 1653-1710) reads `usage.jsonl` via the same flat keys to build
  the per-state token/cost table printed after `ll-loop run`. Third
  consumer chained off `persistence.py`'s output; breaks silently
  (defaults to 0) if the flat keys are renamed without updating this.
- `scripts/little_loops/cli/action.py` (~line 84-114, `ll-action`
  stream-json mode) — emits its own `action_complete` event with only
  `exit_code`/`duration_ms`; does **not** call `run_claude_command`
  with `on_usage_detailed`, so it never carries token/usage data
  today. If `gen_ai.*` emission is meant to be universal across every
  `action_complete` emitter (not just the FSM executor path), this is
  a second emission site needing wiring — if F5 is scoped to FSM loops
  only, note this as an intentional gap, not silent drift.
- `scripts/little_loops/config/core.py` (`LLConfig`) — `_parse_config()`
  (~line 227) only does `self._events =
  EventsConfig.from_dict(self._raw_config.get("events", {}))`; there is
  currently **no `observability` key parsed anywhere**. The `events`
  property (~310-313) and `to_dict()` serializer (~645-660, the
  `"otel": {...}` block) only round-trip the two existing
  `OTelEventsConfig` fields. Whatever holds
  `observability.otel_attributes.enabled` /
  `observability.streaming_parity.check` needs a matching
  `_parse_config()` line, property accessor, and `to_dict()` entry
  here, or the settings won't persist/round-trip through `ll init`/
  `ll configure`.
- `config-schema.json` — the `events.otel` object (lines 1365-1381) has
  `"additionalProperties": false` and only declares
  `endpoint`/`service_name`. If the new toggles live under
  `events.otel`, this schema needs new property declarations (schema
  validation will otherwise reject them); if a new top-level
  `observability` key is chosen instead, it needs a brand-new schema
  block (no existing `"observability"` key anywhere in this file).
  **`scripts/tests/test_config_schema.py`** (lines 469-480) asserts
  the exact property set of the `events.otel` block and actively
  blocks adding new keys there until updated.
- `scripts/little_loops/fsm/types.py` — `StateResult.usage_events:
  list[TokenUsage]` carries the `TokenUsage` shape through to
  `fsm/executor.py`'s aggregation (~1382-1387), which only reads the
  four existing numeric attributes + `model` — new `TokenUsage`
  attributes won't auto-aggregate there unless that block is extended.
- `scripts/little_loops/fsm/runners.py` — imports `TokenUsage`,
  `UsageCallback`, `DetailedUsageCallback`, `run_claude_command` from
  `subprocess_utils`.
- `scripts/little_loops/cli/loop/run.py` (~line 496) — calls
  `wire_transports()`; relevant if `OTelTransport`'s constructor
  signature gains new params.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_history_reader.py` (`TestNewEventReaders` class)
  — new `cost_attribution()` test; mirror
  `test_summarize_skills_success_rate` (lines 1398-1419) exactly: fresh
  `tmp_path / "history.db"`, seed via a `session_store` writer helper,
  call the reader with `db=db`, assert on returned `list[dict]` shape.
- `scripts/tests/test_config.py` (`TestOTelEventsConfig`,
  `TestEventsConfig`, lines ~1740-1848) — needs new cases for whichever
  new config fields land on `OTelEventsConfig`/`EventsConfig`; existing
  cases won't break (additive dataclass fields with defaults) but are
  incomplete without new assertions.
- `scripts/tests/test_config_schema.py` (lines 469-480) — **will
  actively block** new `events.otel` keys until updated (asserts exact
  property set + `additionalProperties: false`).
- `scripts/tests/test_usage_journal.py` (lines 80, 154-155, 192) —
  constructs `TokenUsage` **positionally**
  (`TokenUsage(100, 20, 0, 0, "claude-sonnet-4-6")`). Any new field
  added to the `TokenUsage` dataclass must have a default and be
  appended **after** existing fields, or these positional constructions
  break.
- `scripts/tests/test_subprocess_mocks.py` (lines 219-220) — mocks the
  raw Claude CLI `stream-json` `"result"` event's `usage` dict; a
  "provider addendum" (multi-provider usage-dict shapes) needs
  additional mock fixtures here for non-Anthropic raw key names.
- `scripts/tests/test_usage_reporter.py` — constructs `usage.jsonl`
  fixture rows with the flat key names to test
  `_print_usage_summary`'s output; test-side counterpart of the
  `persistence.py` → `_helpers.py` chain above — must stay in sync
  with whatever `persistence.py` actually writes.
- `scripts/tests/test_transport.py::test_wire_transports_otel`
  (~line 821) — asserts `MockOTel.assert_called_once_with(...)` with
  exact kwargs; **will break** if `OTelTransport(...)`'s call signature
  gains new params for `gen_ai.*` wiring.
- No existing UUID-uniqueness test pattern exists anywhere in
  `scripts/tests/` (checked case-insensitively) — nearest structural
  analog is the trace/span-id distinctness assertion in
  `test_transport.py::test_loop_resume_opens_new_trace` (line 774);
  `test_otel_attributes.py`'s UUID test will be new, no prior
  convention to mirror.
- `TestOTelTransport` in `test_transport.py` (lines 670-838) has no
  existing `span.attributes[...]` assertions to reuse — asserting
  `gen_ai.usage.*` span attributes in `test_otel_attributes.py`
  introduces a new assertion style, not an extension of an existing one.

### Documentation

- `docs/reference/API.md` — `observability/tracing.py` module
- `docs/ARCHITECTURE.md` — Token cost layer section
- `docs/observability/otel-mapping.md` — internal-name ↔ OTel-canonical
  attribute map

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` (`### action_complete`,
  lines ~200-242) — documents the flat field names with literal JSON
  examples; needs updating/extending to show the new `gen_ai.*`
  attributes and their relationship to the existing flat fields.
- `docs/reference/CLI.md` (~lines 122, 567-589) — `ll-loop run`
  per-state token/cost table docs explicitly name `cache_read_tokens`
  as the `cache` column source; update if field semantics/namespacing
  change.
- `docs/reference/CONFIGURATION.md` (`### events.otel`,
  lines 1241-1258) — documents `events.otel.endpoint`/`service_name`;
  needs a new subsection for whichever config keys land, consistent
  with wherever the config actually lives in `core.py`/
  `config-schema.json`.

### Configuration

- `.ll/ll-config.json` — `observability.otel_attributes.enabled`
  default `true`; `observability.streaming_parity.check` default
  `true`

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — the `events.otel` object (lines 1365-1381)
  is `additionalProperties: false` with only `endpoint`/`service_name`
  declared; needs new property declarations under `events.otel` (or a
  brand-new `observability` schema block if that's the chosen home) —
  see `test_config_schema.py` blocker noted under Tests.
- `scripts/little_loops/config/core.py` (`LLConfig._parse_config()`,
  `events` property, `to_dict()`) — no `observability` key is parsed
  today; must be wired for the new settings to round-trip through
  `ll init`/`ll configure`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (locator +
analyzer + pattern-finder):_

- **Line-correction (Current Behavior refs)**: The captured line refs
  are off by ~80 lines — verified by `codebase-analyzer`:
  - `scripts/little_loops/fsm/executor.py` cache-token aggregation
    lives at **1382–1392** inside `FSMExecutor._run_action()` (not
    1295–1305; that range is the `_route_with_interceptors`
    before/after-route plumbing, not token aggregation).
  - `scripts/little_loops/subprocess_utils.py` UsageEvent capture is
    at **449–470** inside the `result` branch of the selector loop
    (not 462–465 only); the `TokenUsage` dataclass is at **44–52**.
- **`scripts/little_loops/observability/` does not exist yet** — both
  `tracing.py` and a sibling `__init__.py` must be created in the
  same PR. The `__init__.py` should expose `OTelAttributes`,
  `StampUsageEvent`, `StreamingParityChecker`.
- **`correlation_id` does not exist** in `fsm/executor.py` — the only
  `uuid4()` precedent in the codebase is
  `scripts/little_loops/cli/loop/run.py:332` (`entry_id =
  str(uuid.uuid4())` for queue-entry filenames). `gen_ai.invocation.id`
  should mirror this exact pattern: `str(uuid.uuid4())`, declared
  once at process entry, threaded through.
- **`usage_event` table does not exist in `history.db`** —
  `scripts/little_loops/session_store.py` is at `SCHEMA_VERSION = 18`;
  no `usage_events` migration yet (that's the
  **ENH-2461** work item). F5's "emit shaped rows into `history.db`"
  wording depends on ENH-2461 landing first or in the same release —
  this is currently a soft prerequisite, not a hard one in the
  Acceptance Criteria.
- **No `host.vendor()` accessor exists** — `HostRunner.name`
  (`scripts/little_loops/host_runner.py:154, 215`) yields
  `"claude-code"`/`"codex"`/`"opencode"`/`"pi"`/`"gemini"`/`"omp"`,
  but no runner→vendor mapping (`anthropic`/`openai`/`google`/etc.)
  exists. F5 needs a small `_VENDOR_BY_RUNNER: dict[str, str]` table
  (or a `vendor` property on the `HostRunner` Protocol) to populate
  `gen_ai.provider.vendor`.
- **Streaming-vs-blocking test cannot run in production** — the
  `anthropic` SDK is **not** imported anywhere in `scripts/little_loops/`
  today; F1 (EPIC-2456 § Tier 2 [TBD-10], not yet filed — NOT
  FEAT-2476, which is F2/`--max-cost` and adds no pip deps) brings it
  in. The parity test must be a
  test-only harness gated on `importlib.util.find_spec("anthropic")`,
  wrapped per the `_HAS_OTEL_SDK` skipif pattern at
  `scripts/tests/test_transport.py:1`.
- **`OTelTransport` already runs but does not currently emit
  `gen_ai.*`** — `scripts/little_loops/transport.py:338`
  (`OTelTransport` class) handles `action_complete` only as a
  span-end signal (`_handle_action_complete` at line 457-460);
  `_add_span_event` (line 479-484) is the natural hook. F5 can layer
  the `gen_ai.*` attrs onto the action span by extending
  `_handle_action_complete` (or by adding `action_complete` to
  `_OTEL_EVENT_TYPES` and letting `_add_span_event` carry the attrs).
- **`action_complete` JSON Schema** locks the four-token + model
  shape (`scripts/little_loops/generate_schemas.py:129-150`); the
  locked golden is `docs/reference/schemas/action_complete.json`
  (guarded by `scripts/tests/test_generate_schemas.py:151-154`).
  Adding `gen_ai.usage.*` / `gen_ai.invocation.id` /
  `gen_ai.provider.vendor` to the payload requires running
  `ll-generate-schemas` and updating the golden + the
  `test_action_complete_schema` test.
- **GROUP BY precedent for `cost_attribution()`** —
  `history_reader.summarize_skills` (`scripts/little_loops/history_reader.py:472`)
  is the closest analog: read-only `sqlite3.connect(... mode=ro,
  uri=True)`, mandatory `try / except sqlite3.Error / finally
  conn.close()` block returning `list[dict]`, `conn.row_factory =
  sqlite3.Row` access. Mirror that shape for `cost_attribution()`.
- **`OTelEventsConfig` config dataclass pattern** —
  `scripts/little_loops/config/features.py:727` (`OTelEventsConfig`,
  embedded in `EventsConfig` at line 776) shows the `from_dict`
  factory + simple `@dataclass` + `data.get(key, default)` defaults
  convention; the new `ObservabilityConfig` (with
  `otel_attributes.enabled` + `streaming_parity.check`) should
  parallel it. Add to `scripts/little_loops/__init__.py` exports
  (line 47-54, `__all__` at line 95) and
  `scripts/little_loops/config/__init__.py` exports (line 60, 104).
- **Top-level exports**: extend `scripts/little_loops/__init__.py`
  (and `__all__`) with the new helpers; placement alphabetically next
  to `OTelTransport`.
- **Phoenix test gating precedent**: `_HAS_OTEL_SDK` + `_HAS_HTTPX`
  skipif guards at `scripts/tests/test_transport.py:1`. The Phoenix
  fixture should be guarded by a sibling `_HAS_PHOENIX` skipif rather
  than `pytest.importorskip` per-call (consistent style).

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — line refs in steps 2-5 above reflect the
captured values, but the analyzer verified the actual sites:_

- **Step 2** (stamping): call the new `StampUsageEvent.usage_event()`
  inside `subprocess_utils.run_claude_command()` at the
  `on_usage_detailed(TokenUsage(...))` site — lines **458–470** of the
  `result` event branch (not 462–465 only).
- **Step 3** (CLI UUID): `uuid4()` decl should sit at the very top of
  `cli_event_context()` in `scripts/little_loops/cli/loop/__init__.py`
  (around line 24), then be passed into `cmd_run(...)` explicitly —
  `cli_event_context()` yields nothing, so the wrapped block has no
  other access to the ID. Alternative: store the minted UUID on
  `cli_events` (extend the v8 migration DDL) and look it up via the
  connection inside the wrapped block.
- **Step 5** (`cost_attribution()`): mirror
  `history_reader.summarize_skills` (`scripts/little_loops/history_reader.py:472-519`)
  for read-only sqlite connection + `try/except/finally` shape; also
  add a `_row_to_dataclass` mapping for the typed variant.
- **Test verification**: run `python -m pytest scripts/tests/test_subprocess_utils.py scripts/tests/test_transport.py scripts/tests/test_generate_schemas.py -v` — these three cover stamp site,
  OTelTransport sink, and locked schema golden respectively. Full
  gate is `python -m pytest scripts/tests/` for step 9.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be
included in the implementation:_

10. Decide config home for `observability.otel_attributes.enabled` /
    `observability.streaming_parity.check` (new top-level
    `observability` block vs. extending `events.otel`), then wire
    `scripts/little_loops/config/core.py` (`LLConfig._parse_config()`,
    `events` property, `to_dict()`) and `config-schema.json` (update
    `test_config_schema.py` in lockstep — it blocks new `events.otel`
    keys today).
11. Extend `scripts/little_loops/fsm/persistence.py`'s `usage.jsonl`
    writer (~line 637-650) to carry the new `gen_ai.*` keys, and
    `scripts/little_loops/cli/loop/_helpers.py::_print_usage_summary()`
    (~1653-1710) to read them — both are independent consumers of the
    flat `action_complete` keys and silently default to 0 if missed.
12. Decide whether `scripts/little_loops/cli/action.py` (`ll-action`
    stream-json mode) is in scope — it emits `action_complete` without
    ever calling `run_claude_command(..., on_usage_detailed=...)`, so
    it has no usage data to stamp today. Document as an explicit
    out-of-scope gap if not addressed.
13. Add default value to any new `TokenUsage` dataclass field and
    append it after existing fields — `test_usage_journal.py`
    constructs `TokenUsage` positionally and will break otherwise.
14. Update `docs/reference/EVENT-SCHEMA.md`, `docs/reference/CLI.md`,
    and `docs/reference/CONFIGURATION.md` alongside the three docs
    already listed in Integration Map § Documentation.

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

## Premise Note — Phoenix ↔ OTel GenAI schema (ingest works; cache-name fix required)

_Surfaced and then settled by `/ll:explore-api phoenix` (2026-07-05;
learning-test record `.ll/learning-tests/phoenix.md`, status `proven`, all 5
claims pass)._

**The AC as written stands.** Two facts, from live testing against
`arize-phoenix 17.18.0`:

1. Phoenix's *native* span schema is **OpenInference** (`llm.token_count.*`);
   the OpenInference schema (`openinference.semconv` 0.1.30) contains **zero**
   `gen_ai.*` attributes — the two namespaces are disjoint on paper.
2. **But current `phoenix serve` normalizes raw OTel `gen_ai.usage.*` spans on
   ingest** — no OpenInference shim required. Verified live via OTLP HTTP: a
   span carrying *only* `gen_ai.usage.input_tokens=111` /
   `gen_ai.usage.output_tokens=222` was stored by Phoenix as
   `llm.token_count.prompt=111`, `llm.token_count.completion=222`,
   `llm.token_count.total=333` — identical to an OpenInference control span.

Effective mapping Phoenix applies — **all four rows now live-verified** against
`arize-phoenix 17.18.0` via OTLP ingest:

| This issue must emit | Phoenix stores (`llm.token_count.*`) | Verified |
|---|---|---|
| `gen_ai.usage.input_tokens` | `llm.token_count.prompt` | ✅ live |
| `gen_ai.usage.output_tokens` | `llm.token_count.completion` | ✅ live |
| `gen_ai.usage.cache_read.input_tokens` | `llm.token_count.prompt_details.cache_read` | ✅ live |
| `gen_ai.usage.cache_creation.input_tokens` | `llm.token_count.prompt_details.cache_write` | ✅ live |

### ⚠️ Cache-token attribute names — SPEC CORRECTION REQUIRED

The originally-specified cache names used **underscores**
(`gen_ai.usage.cache_read_input_tokens`) — the **Anthropic API** field
spelling, prefixed with `gen_ai.usage.`. But the **OTel semantic-convention**
constant values are **dotted sub-namespaces**:

- `GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS` = `gen_ai.usage.cache_read.input_tokens`
- `GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS` = `gen_ai.usage.cache_creation.input_tokens`

Phoenix's `get_openinference_usage_attributes()` looks up the **dotted** OTel
constants. **Live proof:** a span emitting the underscore names had its cache
tokens **silently dropped** (`cache_read=None`, `cache_write=None`), while a
sibling span with the dotted names surfaced `cache_read=55` / `cache_write=77`.
The `input_tokens`/`output_tokens` names happen to be identical in both
conventions, so only the two cache rows are affected. **Emit the dotted names**
(Expected Behavior list above updated accordingly). This is not Phoenix-specific
— any OTel-semconv consumer expects the dotted form.

**Version floor for the `_HAS_PHOENIX` guard.** The gen_ai→OpenInference
normalization module (`phoenix/trace/gen_ai/conversion.py`) **first shipped in
`arize-phoenix 15.10.0`** (absent in 15.9.0; dep-independent file-presence
bisect). Functional normalization confirmed live on 17.18.0. Gate the fixture
with **skip if `arize-phoenix < 15.10.0`**. (Note: versions well below current
17.x may not `pip install` cleanly today due to an unpinned upstream
`pydantic-ai` transitive dep — a packaging issue in old Phoenix, unrelated to
the normalization logic; in practice teams run recent 17.x.)

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
- `/ll:explore-api phoenix` - 2026-07-05 - live cache-name + version bisect: cache tokens require DOTTED OTel names (`gen_ai.usage.cache_read.input_tokens`), NOT the issue's underscore spelling (silently dropped) — SPEC CORRECTED in Expected Behavior; normalization module first shipped in arize-phoenix 15.10.0 (guard floor). Record `.ll/learning-tests/phoenix.md` (7 claims pass)
- `/ll:explore-api phoenix` - 2026-07-05 - live-tested claim 5: `phoenix serve` (arize-phoenix 17.18.0) normalizes raw `gen_ai.usage.*` -> `llm.token_count.*` on ingest, so the AC stands; residual risk is Phoenix version (pin min ver in `_HAS_PHOENIX` guard). Record `.ll/learning-tests/phoenix.md`
- `/ll:wire-issue` - 2026-07-05T21:51:50 - `f7bc5213-6675-4897-a8b4-82cd276c9c72.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:49:47 - `f22b122e-50d0-4242-97ef-9097cef10d32.jsonl`

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
