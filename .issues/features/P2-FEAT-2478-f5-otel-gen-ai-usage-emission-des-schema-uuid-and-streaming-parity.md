---
id: FEAT-2478
title: "F5 \u2014 OTel gen_ai.usage.* emission + streaming parity + UUID + provider\
  \ addendum"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-04T20:05:34Z'
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- ENH-2475
- ENH-2477
- FEAT-2476
- ENH-2479
- ENH-2461
depends_on:
- ENH-2475
- ENH-2479
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
confidence_score: 98
outcome_confidence: 65
score_complexity: 14
score_test_coverage: 23
score_ambiguity: 10
score_change_surface: 18
size: Very Large
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

### Open Decisions (scorable)

Two orthogonal design decisions gate wiring. Each is a scorable
Option group. `/ll:decide-issue` selects one winner per pass, so
resolve them one decision at a time (or interactively) — Decision 1
(A/B) first, then Decision 2 (C/D).

#### Decision 1 — Config home for the new settings

Where do `otel_attributes.enabled` and `streaming_parity.check` live in
`.ll/ll-config.json` and `config-schema.json`?

### Option A — New top-level `observability` block

> **Selected:** Option A (`/ll:decide-issue`, 2026-07-11) — the toggles govern an always-on capture-time behavior independent of the opt-in OTLP transport, so a dedicated top-level home matches the codebase's ~30-block convention and avoids loosening the `events.otel` guard.

Add `observability.otel_attributes.enabled` (default `true`) and
`observability.streaming_parity.check` (default `true`) as a new
top-level config namespace. Requires a new `observability` schema block
in `scripts/little_loops/config-schema.json`, a new `ObservabilityConfig`
dataclass + `from_dict` parse path in `config/core.py` (parallel to
`EventsConfig.from_dict`, core.py:231), and a matching `to_dict()` branch
(parallel to the `events` branch, core.py:682–695) so the settings
round-trip through `ll init` / `ll configure`.
- **For**: attribute stamping happens on every `UsageEvent` at capture
  time (`subprocess_utils.py:462–465`), feeding local
  `history_reader.cost_attribution()` — it is independent of whether the
  OTLP `events.otel` transport (which needs `little-loops[otel]` + a
  collector endpoint) is wired. A user can want cost attribution in the
  local SQLite history with no collector. Homing a
  behavior-that-runs-always under a transport sink config is misleading.
- **Against**: more new infrastructure — a new dataclass, parse path,
  schema block, and `to_dict()` wiring — i.e. broader change surface than
  Option B.

### Option B — Extend the existing `events.otel` block

Add `otel_attributes` / `streaming_parity` (or flat
`emit_usage_attributes` / `check_streaming_parity`) under the existing
`events.otel` object; flip its `additionalProperties: false`
(config-schema.json, `events.otel`) to admit the new keys.
- **For**: minimal new infra — reuses the existing
  `EventsConfig.from_dict` / `to_dict` round-trip (core.py:231, 688–691);
  smallest diff.
- **Against**: semantically couples "emit `gen_ai.*` on every UsageEvent"
  to the OTLP-transport namespace even when no OTLP transport is enabled;
  `additionalProperties: false` is a deliberate guard (test_config_schema.py),
  so this is an intentional loosening.

> **Recommendation (not yet locked):** Option A — the settings govern a
> capture-time behavior independent of OTLP export, so a dedicated
> `observability` home is the honest fit. Confirm via `/ll:decide-issue`.

#### Decision 2 — Optional-caller scope

Do the three callers that wire only the 2-arg `on_usage` callback
(`cli/action.py`, `issue_manager.py::run_claude_command()`,
`worker_pool.py::_run_claude_command()`) get upgraded to
`on_usage_detailed` (which carries cache tokens) in F5, or later?

### Option C — In scope: upgrade all three now

Thread `on_usage_detailed` through the three callers so their host
invocations also stamp `gen_ai.usage.*` + `gen_ai.invocation.id`.
- **For**: complete coverage across every host-invocation path; no
  follow-on gap.
- **Against**: +3 call-site edits touching the parallel/worker path;
  broader change surface. Not required by the DES adoption gate
  (`ll-verify-des-audit`, ENH-2475) — that gate checks event-emit-site →
  registered-variant coverage, which is orthogonal to these callback
  signatures.

### Option D — Deferred: F5 covers only the mandatory FSM path

> **Selected:** Option D (`/ll:decide-issue`, 2026-07-11) — `subprocess_utils.py:449-470` already isolates `on_usage` and `on_usage_detailed` into independent branches, so F5's FSM-path scope needs zero edits to the three callers; deferring the mechanical upgrade to a follow-on matches direct in-repo precedent (`FEAT-958`) and no gate or test forces the wider surface.

Leave the three on 2-arg `on_usage`; F5 stamps attributes only on the
mandatory FSM host-invocation path (`subprocess_utils.py:462–465`). The
three optional callers are upgraded in a mechanical follow-on.
- **For**: narrowest change surface; keeps F5 focused on the FSM path;
  DES gate unaffected.
- **Against**: those three invocation paths won't emit `gen_ai.usage.*`
  until the follow-on — a bounded incomplete-coverage window.

> **Decided:** Option D — no gate forces the three callers in, and the
> smaller surface aligns with F5 being the FSM-host-invocation feature.
> See § Decision Rationale › Decision 2 below.

### Decision Rationale

#### Decision 1 — Config home (decided)

Decided by `/ll:decide-issue` on 2026-07-11.

**Selected**: Option A — New top-level `observability` block.

**Reasoning**: The only production reader of `events.otel.*`
(`transport.py:633-634`, inside `wire_transports()`) is gated behind
`"otel" in config.transports` — a fully opt-in OTLP export path — whereas F5's
`otel_attributes.enabled` / `streaming_parity.check` govern an always-on,
capture-time behavior that writes shaped rows directly to `history.db` with no
SDK or collector. Homing them under `events.otel` would be the first non-transport
setting in that block and a deliberate loosening of its `additionalProperties: false`
guard. Option A instead follows the ~30-block top-level convention, with a literal
test template (`test_hooks_in_schema`, `test_config_schema.py:441-460`) and a
copy-paste structural donor (`OTelEventsConfig`, `config/features.py:745-758`), and
adds a new `test_observability_in_schema` without editing existing `test_events_in_schema`
assertions.

##### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — New `observability` block | 3/3 | 2/3 | 3/3 | 3/3 | **11/12** |
| B — Extend `events.otel` | 1/3 | 3/3 | 2/3 | 1/3 | 7/12 |

**Key evidence**:
- Option A: ~30 top-level blocks precedent + `FooConfig.from_dict`/`to_dict()`/property triad (`core.py:206-242`); literal "new top-level block" test template `test_hooks_in_schema`; additive — no churn to existing test assertions.
- Option B: reuses the `EventsConfig`/`OTelEventsConfig` plumbing (smallest diff) but has zero semantically-fitting consumer — every `events.*` sibling is narrowly scoped to transport-construction kwargs, and the doc (`CONFIGURATION.md:1269-1280`) scopes `events.otel` to OTLP export requiring `pip install 'little-loops[otel]'`.

#### Decision 2 — Optional-caller scope (decided)

Decided by `/ll:decide-issue` on 2026-07-11.

**Selected**: Option D — Deferred; F5 covers only the mandatory FSM path.

**Reasoning**: `subprocess_utils.py:449-470` already dispatches `on_usage` and
`on_usage_detailed` as two independent `if` branches, so stamping `gen_ai.*` inside the
`on_usage_detailed` path touches zero lines in `cli/action.py`, `issue_manager.py`, or
`worker_pool.py` — the three callers keep passing only 2-arg `on_usage` as they do today.
Option C, by contrast, has reuse score 1: the only existing `on_usage_detailed` consumer
(`fsm/runners.py:141-160`) is a shallow collect-and-forward not even used by its own caller
(`fsm/executor.py` reads `ActionResult.usage_events` instead), so all three sites need
bespoke closure work — and `cli/action.py` needs wiring built from scratch plus an
`action_complete` payload-shape change that touches the locked JSON Schema golden. Deferral
has direct in-repo precedent (`FEAT-958` deferred the identical `ll-parallel` gap under
`## Out of Scope`), the DES adoption gate (`ll-verify-des-audit`) checks type-literal
coverage only and is already pre-satisfied for `action_complete`, and no test or doc claims
`gen_ai.*`/cache-token telemetry for `ll-auto`/`ll-parallel`/`ll-action` today (the
Per-State Token/Cost Summary, ENH-1797/ENH-2477, is scoped to `ll-loop run`). The
incomplete-coverage window is bounded and handled by a mechanical follow-on.

##### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| D — Defer to follow-on | 3/3 | 3/3 | 3/3 | 3/3 | **12/12** |
| C — Upgrade all three now | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Option D: `on_usage`/`on_usage_detailed` are already independent branches (`subprocess_utils.py:449-470`) → zero-touch on the three callers; direct precedent `FEAT-958` `## Out of Scope`; DES gate is type-literal-only and already satisfied; no user-facing telemetry regression (docs scope the cost table to `ll-loop run`).
- Option C: base plumbing is shared via import alias, but there is no caller-side precedent for live `on_usage_detailed` consumption, no shared closure helper (each of 2 files needs a duplicated `TokenUsage`-shaped closure at 2 sites), and `cli/action.py` needs from-scratch wiring plus a locked-schema-golden change.

**Follow-on**: file a mechanical enhancement to thread `on_usage_detailed` through
`cli/action.py`, `issue_manager.py::run_claude_command()`, and
`worker_pool.py::_run_claude_command()` so the `ll-action`/`ll-auto`/`ll-parallel` paths
also stamp `gen_ai.usage.*`.

> **Both decisions now resolved** — `decision_needed` set to `false`. Decision 1 selected
> Option A (top-level `observability` block); Decision 2 selected Option D (defer the three
> optional callers).

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

_Second wiring gap found by `/ll:refine-issue` (2026-07-11):_
- `scripts/little_loops/fsm/cost_graph.py:184-254`
  (`CostReport.from_usage_jsonl()`) — a **third**, previously
  uncaptured, independent consumer of `usage.jsonl`'s flat keys. It
  sits between `fsm/persistence.py`'s writer and
  `_helpers.py::_print_usage_summary()`'s renderer (which calls
  `CostReport.from_usage_jsonl(usage_path)` at `_helpers.py:1869`,
  itself invoked from the run-exit path at `_helpers.py:1826`) — so
  there are three consumers of the flat-key shape in this chain, not
  two. Confirmed via the landed `scripts/tests/test_streaming_cache_parity.py`
  module docstring (ENH-2479, `status: done`), which cites this exact
  line range while documenting why its parity gate covers all four
  token fields.

_Third wiring gap found by `/ll:wire-issue` (2026-07-11):_
- `scripts/little_loops/issue_manager.py::run_claude_command()` (wraps
  `_run_claude_base`, def at ~line 105) and
  `scripts/little_loops/parallel/worker_pool.py::WorkerPool._run_claude_command()`
  (~line 795) — two more callers of the base `run_claude_command`
  (`subprocess_utils.py`), both accepting only the simpler
  `on_usage: Callable[[int, int], None]` two-value callback, **not**
  `on_usage_detailed`. This is the same "no usage data captured" gap
  already flagged for `cli/action.py` above, but for the `ll-auto`
  (sequential) and `ll-parallel`/`ll-sprint` (concurrent worker pool)
  invocation paths respectively — cache_read/cache_creation tokens (and
  therefore `gen_ai.usage.cache_read.input_tokens` /
  `gen_ai.usage.cache_creation.input_tokens`) are not captured for
  issues processed through either path today. Same scope decision
  applies: either wire `on_usage_detailed` through both wrapper
  functions, or document `ll-auto`/`ll-parallel` as an explicit
  out-of-scope gap alongside `cli/action.py`.
- `observability/schema.py:222-227` (`ActionCompleteVariant`) — its own
  docstring reads `"action_complete — action returned (carries
  TokenUsage)"`, but the dataclass fields are only `type`, `exit_code`,
  `duration_ms` — **no token-shaped fields exist on this variant
  today**. This nuances (does not reverse) the "DES audit gate is
  structurally pre-satisfied" finding in the round-2 block above: the
  *type-literal* `"action_complete"` is registered (satisfying the
  audit walker's per-type coverage check), but if `gen_ai.*`
  field-level validation via the DES variant shape is also desired,
  `ActionCompleteVariant`'s dataclass needs new fields added — that is
  additional scope beyond "no new variant registration needed."
- `cli_event_context()` is defined in
  `scripts/little_loops/session_store.py:870`, **not** inside
  `scripts/little_loops/cli/loop/__init__.py`. Line 24 of
  `cli/loop/__init__.py` is only the *call site* invoking it for
  `"ll-loop"` (`with cli_event_context(DEFAULT_DB_PATH, "ll-loop",
  sys.argv[1:]):`). This clarifies (does not reverse) Implementation
  Step 3's placement guidance below — the `uuid4()` decl goes either in
  the block wrapping that call site in `cli/loop/__init__.py:24`, or
  inside `cli_event_context()` itself in `session_store.py:870` if it
  should be threaded to every CLI entry point, not just `ll-loop`.

### Similar Patterns

- `scripts/little_loops/observability/__init__.py` (if exists) —
  extend instead of creating a parallel sibling
- The `invocation_id` UUID pattern mirrors `correlation_id` in
  `fsm/executor.py` (check for existing)

> ⚠ **Update (2026-07-11, `/ll:refine-issue`)**: `scripts/little_loops/observability/`
> now EXISTS — it landed with **ENH-2475** (status `done`), which added
> `__init__.py`, `schema.py`, and `audit.py` (the DES variant registry +
> audit walker). F5 must **extend** this package (add `tracing.py`
> alongside the existing files, extend `__init__.py`'s `__all__`) rather
> than create it from scratch. `observability/audit.py`'s own module
> docstring already names `observability/tracing.py` as F5's landing
> site, confirming the path. This supersedes the "does not exist yet"
> finding under Implementation Steps § Codebase Research Findings below,
> which was accurate when written (2026-07-05) but is now stale.

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

_Wiring pass added by `/ll:wire-issue` (2026-07-11):_
- `scripts/tests/test_host_runner.py` — zero references to "vendor"
  anywhere in this 1170-line file today; whatever `_VENDOR_BY_RUNNER`
  table or `vendor` property F5 adds to `host_runner.py` needs wholly
  new test coverage here, no existing case to extend. Closest
  structural analog: the per-runner `.name ==` assertions in
  `TestClaudeCodeRunner` / `TestCodexRunner` / `TestGeminiRunner`.
- `scripts/tests/test_fsm_cost_graph.py` (`TestCostReport` class) — an
  **existing** test file not previously named in this section, covering
  `CostReport.from_usage_jsonl()` (`fsm/cost_graph.py:184-254`)
  directly: `test_from_usage_jsonl_aggregates_per_state`,
  `test_from_usage_jsonl_empty_file`,
  `test_from_usage_jsonl_skips_malformed_rows`,
  `test_from_usage_jsonl_missing_file`,
  `test_totals_aggregate_across_states`, `test_to_dict_top_level_shape`,
  `test_table_matches_existing_layout`, `test_write_json_round_trip`.
  Its fixtures build flat-key JSONL rows — if `persistence.py`'s writer
  changes, these 8 tests are upstream of (and independent from)
  `test_usage_reporter.py`, which only covers `_helpers.py`'s renderer.

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

_Wiring pass added by `/ll:wire-issue` (2026-07-11):_
- `docs/reference/loops.md:111` — the `general-task` § Output Artifacts
  "Runner-written files" callout literally enumerates the flat
  `usage.jsonl` per-line schema: `{iteration, state, action_type,
  input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
  model, timestamp}`. A fourth doc site (alongside `EVENT-SCHEMA.md`,
  `CLI.md`, `CONFIGURATION.md`) that will go stale if `gen_ai.*`
  attributes are added to `usage.jsonl` rows without updating this line.
- `CHANGELOG.md` — confirmed convention: file the F5 landing as a
  one-line bullet (`- **Title** — description (FEAT-2478)`) under the
  next dated `### Added` section, following the `ENH-2475` precedent at
  line 291 — not under `## [Unreleased]`.

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

### Codebase Research Findings (round 2 — `/ll:refine-issue`, 2026-07-11)

_Both `depends_on` prerequisites are now satisfied, one round of line
citations above is itself stale, and a hard dependency's deliverables
already exist on disk. Verified live against current `main`:_

- **Both hard dependencies are done.** `ENH-2475` (DES audit) and
  `ENH-2479` (streaming-parity trace set) — this issue's two
  `depends_on` entries — are both `status: done`. This issue is no
  longer prerequisite-blocked. (`ENH-2461`, referenced separately in
  the Integration Map as a coordination point, is still `open` — the
  `usage_event` table still does not exist in `history.db`
  (`session_store.py` remains at `SCHEMA_VERSION = 18`); that
  soft-dependency caveat is unchanged and still accurate.)

- **The ENH-2479 streaming-parity trace set already exists** — F5 does
  not need to create it, only consume it from the production
  `StreamingParityChecker`. Confirmed present on disk today:
  - `scripts/tests/fixtures/streaming_parity/{trace_a_static_prefix_stable_turn_2,
    trace_b_write_then_read_across_tool_result,
    trace_c_tool_result_only_cache_hit}/` — each with `recorded.jsonl`
    (raw upstream stream-json, verbatim `cache_read_input_tokens`
    naming) + `expected.jsonl` (per-turn `{create, stream}` snapshots
    using INTERNAL field names), plus `README.md` + `rebuild.sh`.
  - `scripts/tests/test_streaming_cache_parity.py` — the pytest-side
    parity test, parametrized over the 3 trace dirs, gated on
    `_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None`
    (no live SDK call needed at test time).
  - `docs/observability/streaming-parity-traces.md` — trace A/B/C
    documentation.
  - Per ENH-2479's own "FEAT-2478 coordination schema contract"
    section: both the internal names (for the pytest loader) and the
    upstream names (`cache_read_input_tokens` /
    `cache_creation_input_tokens`, for FEAT-2478's reader) are already
    recorded in these fixtures, so F5's `StreamingParityChecker.diff()`
    can load `expected.jsonl` directly without a new recording pass.

- **Line-reference correction, round 2 — supersedes the round-1
  correction immediately above this block.** The round-1 correction
  (captured 2026-07-05) itself drifted; the now-landed
  `test_streaming_cache_parity.py` module docstring (written against
  ENH-2479's implementation, ENH-2479 status `done`) independently
  cites the same sites, matching a fresh direct read of each file:
  - `scripts/little_loops/fsm/executor.py:1462–1474` — the
    `total_cache_read` / `total_cache_creation` aggregation and
    `payload["cache_read_tokens"]` / `payload["cache_creation_tokens"]`
    assignment inside `_run_action()`. (NOT 1382–1392 — that range is
    `_run_action()`'s closing docstring followed by `interpolate()`,
    `_action_mode()`, and the ENH-2486 prompt-size guard; NOT the
    original 1295–1305 either.)
  - `scripts/little_loops/fsm/persistence.py:710–727` — the
    `usage.jsonl` writer block inside `_handle_event()`, gated on
    `event_type == "action_complete" and "input_tokens" in event`.
    (NOT `~637-650`, the figure currently cited in the Wiring Phase
    section below.)
  - `scripts/little_loops/cli/loop/_helpers.py:1699–1702` — the
    specific token-table-rendering lines inside
    `_print_usage_summary()`; the function's own `def` line is
    **1869** and its call site is **1826**. (NOT `~1653-1710`, the
    figure currently cited in the Wiring Phase section below — that
    range falls inside an unrelated log-redirection block.)
  - **New, not previously cited anywhere in this issue**:
    `scripts/little_loops/fsm/cost_graph.py:184–254`
    (`CostReport.from_usage_jsonl()`) — see the new Integration Map §
    Dependent Files entry above; a third independent consumer of the
    flat-key shape, not just the two (`persistence.py` writer,
    `_helpers.py` printer) already named in the Wiring Phase section.

- **DES audit gate is structurally pre-satisfied for this issue's
  scope.** `observability/schema.py:222–225` already registers
  `ActionCompleteVariant` (`type: Literal["action_complete"] =
  "action_complete"`) in `DES_VARIANT_TYPES`. Since F5 adds new
  attributes to the existing `action_complete` event rather than a new
  event `type`, `ll-verify-des-audit` / `audit_tree` needs no new
  variant registration for this work — the "DES schema accept rate
  100%" test target is a compatibility check against an already-covered
  type, not new-registration work.

- **`pyproject.toml` still has no `[anthropic]` extra** (confirmed
  unchanged: `[project.optional-dependencies]` at line 104 declares
  only `[otel]` / `[webhooks]`; `packages = ["little_loops"]` at line
  131). F1 (this issue's own prerequisite work, EPIC-2456 § Tier 2
  [TBD-10]) still owns adding `[anthropic]` as its own opt-in extra —
  not bundled into `[dev]` — so contributors without it get a clean
  skip via `_HAS_ANTHROPIC`, matching the existing
  `test_streaming_cache_parity.py` gating pattern above.

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

_Wiring pass added by `/ll:wire-issue` (2026-07-11, round 2):_
15. Decide whether `scripts/little_loops/issue_manager.py::run_claude_command()`
    and `scripts/little_loops/parallel/worker_pool.py::_run_claude_command()`
    (both wrap the base `run_claude_command` with a 2-arg `on_usage`
    callback, not `on_usage_detailed`) are in scope, same as the
    `cli/action.py` decision at step 12 — `ll-auto`/`ll-parallel`-driven
    invocations otherwise don't capture cache tokens for `gen_ai.*`
    emission.
16. Update `docs/reference/loops.md:111` (flat `usage.jsonl` field-list
    callout) alongside the three docs already listed at step 14.
17. If `gen_ai.*` field-level DES validation is desired (not just
    type-literal coverage), extend `ActionCompleteVariant`
    (`observability/schema.py:222-227`) with the new token-shaped
    fields — its current dataclass has none despite its own docstring
    claiming it "carries TokenUsage".

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-11_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 65/100 → MODERATE

### Outcome Risk Factors
- Config home for `observability.otel_attributes.enabled` / `observability.streaming_parity.check` is enumerated as a scorable Option group (Decision 1 — Option A/B, under `## Proposed Solution › Open Decisions`; recommended: Option A). Resolve via `/ll:decide-issue` before wiring `config/core.py` and `config-schema.json`.
- Broad enumeration across ~11 mandatory code-change sites (`tracing.py`, `subprocess_utils.py`, CLI UUID entry point, `history_reader.py`, `persistence.py`, `_helpers.py`, `config/core.py`, `config-schema.json`, `fsm/types.py`, `host_runner.py`) that must be kept in sync — the `persistence.py` → `_helpers.py` → `cost_graph.py` chain silently defaults to 0 if any site is missed. Per-site depth is low (mostly contained additions), but breadth drives the risk.
- Scope for the three optional callers (`cli/action.py`, `issue_manager.py::run_claude_command()`, `worker_pool.py::_run_claude_command()`) — each wires only a 2-arg `on_usage`, not `on_usage_detailed` — is enumerated as a scorable Option group (Decision 2 — Option C/D, under `## Proposed Solution › Open Decisions`; recommended: Option D — defer). Resolve via `/ll:decide-issue`.

## Status

**Open** | Created: 2026-07-04 | Priority: P2

## Session Log
- `/ll:decide-issue` - 2026-07-11T23:01:46 - `76857e57-bb36-467b-a675-eb133a2f4272.jsonl`
- `/ll:decide-issue` - 2026-07-11T22:55:41 - `5108c085-82ed-425a-a7e2-f3dfee0de132.jsonl`
- `/ll:confidence-check` - 2026-07-11T00:00:00 - `e59193e3-64de-4bf2-ac76-b0b4ae767a77.jsonl` (re-run, no codebase changes since prior check — scores unchanged)
- `/ll:decide-issue` - 2026-07-11T22:28:29 - `6e23c9de-4c08-4ae3-bf3a-8995fd222f86.jsonl`
- `/ll:refine-issue` - 2026-07-11T22:26:33 - `ab1fb8fd-0e9a-4d53-90d0-a4f8eea88108.jsonl`
- `/ll:confidence-check` - 2026-07-11T00:00:00 - `269c69d4-80af-4bcc-a914-50ae2437f8f8.jsonl`
- `/ll:wire-issue` - 2026-07-11T22:19:15 - `671a288d-6fef-4fea-a26b-3a5d66d58711.jsonl`
- `/ll:refine-issue` - 2026-07-11T22:10:05 - `aaeec779-0ce0-40fe-9b1a-5f6fbfee36b3.jsonl`
- `/ll:explore-api phoenix` - 2026-07-05 - live cache-name + version bisect: cache tokens require DOTTED OTel names (`gen_ai.usage.cache_read.input_tokens`), NOT the issue's underscore spelling (silently dropped) — SPEC CORRECTED in Expected Behavior; normalization module first shipped in arize-phoenix 15.10.0 (guard floor). Record `.ll/learning-tests/phoenix.md` (7 claims pass)
- `/ll:explore-api phoenix` - 2026-07-05 - live-tested claim 5: `phoenix serve` (arize-phoenix 17.18.0) normalizes raw `gen_ai.usage.*` -> `llm.token_count.*` on ingest, so the AC stands; residual risk is Phoenix version (pin min ver in `_HAS_PHOENIX` guard). Record `.ll/learning-tests/phoenix.md`
- `/ll:wire-issue` - 2026-07-05T21:51:50 - `f7bc5213-6675-4897-a8b4-82cd276c9c72.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:49:47 - `f22b122e-50d0-4242-97ef-9097cef10d32.jsonl`

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
