---
id: ENH-2506
title: Capture hook execution telemetry into history.db
type: ENH
priority: P3
status: done
discovered_date: 2026-07-06
captured_at: '2026-07-06T00:00:00Z'
completed_at: '2026-07-22T18:37:58Z'
discovered_by: capture-issue
parent: EPIC-2457
labels:
- enhancement
- history-db
- hooks
- telemetry
- captured
decision_needed: false
confidence_score: 98
outcome_confidence: 75
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 18
---

# ENH-2506: Capture hook execution telemetry into history.db

## Summary

The `post-tool-use`, `session-end`, `pre-compact`, `user-prompt-submit`,
and `stop` hook scripts exit non-zero silently all the time — the outer
`try/except Exception: return LLHookResult(exit_code=0)` wrappers in the
hook handlers swallow the failure, and nothing persists. So when a user
hits "the hook didn't fire" or "the context-monitor is broken", there is
no record of whether the hook ran, what it returned, or how long it
took. Add a `hook_events` table capturing `(session_id, event_name,
matcher, script, exit_code, duration_ms, stderr_preview)` for every hook
fire. Most "the hook didn't fire" debug threads start with no data; this
ends that.

## Motivation

- **Hook telemetry is the largest dark area.** Today, hooks can fail,
  time out, or never fire, and the only signal is "the agent behaves
  strangely." With per-fire rows, every hook invocation becomes a
  queryable point: which matcher matched, which script ran, what exit
  code it returned, how long it took, what stderr it produced.

> **Architectural Note — live-write only; NOT a raw_events parser
> (ARCHITECTURE-144 scope).** ARCHITECTURE-144 (`.ll/decisions.yaml`,
> ENH-2581) named this issue among those "turned into event_type parser
> tasks over raw_events." That does not apply here: the Claude Code host
> does **not** write hook execution results (exit code, duration, stderr)
> into the session transcript JSONL, so `raw_events` carries no hook
> telemetry to parse. Hook telemetry is genuinely out-of-band, exactly
> like ENH-2507's context-pressure readings. Therefore `hook_events` is a
> **live-write-only** table: `record_hook_event` / `hook_event_context`
> is the only producer, it is **excluded from `rebuild()`'s
> `_REBUILD_TABLES`** (a wipe would be unrecoverable), and there is **no
> `_backfill_hook_events` parser** — the earlier spec's backfill bullet is
> retracted below because its data source does not exist. This is a
> documented, justified pattern deviation.
- **EPIC-1707 deliberately deferred this.** ENH-2495 added lifecycle
  *events* (handoff_needed, compaction, sweep) but not lifecycle
  *telemetry* (the fires that produced them). This issue fills the
  second gap.
- **Adjacent to ENH-2495 (lifecycle_events) and ENH-2504
  (verdict_events).** Different table, complementary signal: 2505 says
  "the handoff_needed event happened"; 2506 says "the hook that
  detected it ran in 12ms with exit code 0."
- **Trivial producer.** Extend the existing `skill_event_context`
  precedent (the best-effort pattern at
  `session_store.py:1109-1182`) to a generic `hook_event_context(...)`
  that wraps any hook handler. Every existing `LLHookResult` producer
  drops in for free.

  > ⚠ Codebase Research Findings (added by `/ll:refine-issue`): The issue
  > originally cited `cli_event_context` at `session_store.py:870-908`,
  > but that function is now at `session_store.py:1055-1091` and is **not**
  > the right precedent — it is **not** best-effort (it raises on a
  > missing DB). `skill_event_context` at `session_store.py:1109-1182`
  > is the right model: it tolerates DB-absent / DB-locked failures
  > (EPIC-1707 graceful-degradation contract — same constraint that
  > applies to hook handlers) and uses a mutable `SkillEventCompletion`
  > handle so the caller can set `exit_code` post-hoc. Use
  > `skill_event_context` as the structural model, not `cli_event_context`.

## Current Behavior

- `post_tool_use.py:158` (and the matching patterns in
  `user_prompt_submit.py`, `pre_compact.py`, `sweep_stale_refs.py`,
  `session_start.py`) wraps the body in
  `with contextlib.suppress(Exception):` and the dispatcher wraps that
  in another `try/except Exception: return LLHookResult(exit_code=0)`.
  A failed hook returns success.
- The only durable artifact of a hook fire is `tool_events` for
  `post_tool-use` writes that succeeded. For other hooks, nothing.
- The dispatch table (`scripts/little_loops/hooks/__init__.py:_dispatch_table`)
  registers every hook but doesn't record the fire.

## Expected Behavior

- A `hook_events` table records one row per hook fire with
  `event_name`, `matcher` (the selector from `hooks/hooks.json`),
  `script` (the bash command or Python entry point), `exit_code`,
  `duration_ms`, `stderr_preview` (truncated first N bytes), and
  `session_id`.
- A `hook_event_context(db_path, event_name, matcher, script)`
  context manager measures elapsed time, captures exit code on exit,
  reads stderr if available, and writes the row (best-effort).
- Existing hook handlers adopt the context manager; no other producer
  changes required.
- `ll-session recent --kind hook_event` returns rows; aggregate
  queries (failure rate by event_name, p95 duration) become
  straightforward.

## Impact

- **Priority**: P3 - Fills a debugging dark area (no data on hook fires today)
  but doesn't block any in-flight feature work; correctly deprioritized behind
  active EPIC-2457 siblings.
- **Effort**: Large - one schema migration, ~12 handler wraps (Python + bash
  shim), 3 new read-API functions, a new CLI subcommand, and a wide test/doc
  surface (see Integration Map); mostly mechanical, reusing the
  `skill_event_context` best-effort pattern.
- **Risk**: Low - the outer `hook_event_context` wrap is additive and
  best-effort; it must not alter existing hook exit-code/swallow behavior
  (see Acceptance Criteria) and `hook_events` is excluded from `rebuild()`'s
  `_REBUILD_TABLES` so it can't be wiped by unrelated rebuild operations.
- **Breaking Change**: No.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS hook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    event_name TEXT NOT NULL,     -- "PostToolUse" | "UserPromptSubmit" | "PreCompact" | "Stop" | "SessionStart" | "SessionEnd"
    matcher TEXT,                 -- the `matcher` field from hooks/hooks.json (e.g., "Write|Edit|MultiEdit")
    script TEXT,                  -- bash command or python module path
    exit_code INTEGER,
    duration_ms INTEGER,
    stderr_preview TEXT,          -- truncated first 512 bytes of stderr (if any)
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_hook_event_name ON hook_events(event_name);
CREATE INDEX IF NOT EXISTS idx_hook_session ON hook_events(session_id);
CREATE INDEX IF NOT EXISTS idx_hook_exit ON hook_events(exit_code);
```

Bump `SCHEMA_VERSION`. Add `"hook_event"` to `_VALID_KINDS` and
`"hook_event": "hook_events"` to `_KIND_TABLE`.

### Producer wiring

- Add `record_hook_event(db_path, *, ts, session_id, event_name, matcher,
  script, exit_code, duration_ms, stderr_preview=None, head_sha=None,
  branch=None)` to `session_store.py`, best-effort, FTS-indexing
  `event_name + matcher`.
- Add `hook_event_context(db_path, session_id, event_name, matcher,
  script)` to `session_store.py` modeled on `cli_event_context`
  (`session_store.py:870-908`): a `@contextmanager` that
  records `started_at = time.monotonic()`, yields, and on exit writes
  the row with `duration_ms = int((monotonic() - started_at) * 1000)`,
  `exit_code=<caller's exit code>`, and stderr from a captured buffer.
- Wrap each existing `handle()` in the host-agnostic Python handlers
  with the new context manager. Verified handler anchors (as of
  v1.147.0):
  - `scripts/little_loops/hooks/post_tool_use.py:137` — PostToolUse (the
    one whose `with contextlib.suppress(Exception):` block at line 158
    is the canonical inner-swallow pattern)
  - `scripts/little_loops/hooks/user_prompt_submit.py:61` — UserPromptSubmit
  - `scripts/little_loops/hooks/pre_tool_use.py` — PreToolUse (NEW — not
    in the original issue; `hooks/hooks.json` registers PreToolUse for
    `Write|Edit`, `Bash`, and several dedicated matchers)
  - `scripts/little_loops/hooks/pre_compact.py:84` — PreCompact
  - `scripts/little_loops/hooks/sweep_stale_refs.py:141` — SessionStart
    secondary (stale-refs sweep)
  - `scripts/little_loops/hooks/session_start.py:75` — SessionStart primary
  - `scripts/little_loops/hooks/post_commit.py` — PostToolUse (additional
    producer for issue-auto-commit; NEW)
  - `scripts/little_loops/hooks/edit_batch_nudge.py` — PostToolUse
    (`Edit|Write|MultiEdit` matcher — NEW)
  - `scripts/little_loops/hooks/pre_compact_handoff.py` — PreCompact
    secondary (NEW)
  - `scripts/little_loops/hooks/learning_tests_gate.py`,
    `install_learning_gate.py` — PreToolUse / PostToolUse (NEW, gated by
    `analytics.capture.skills`)

  There is **no** `scripts/little_loops/hooks/stop.py` — the `Stop`
  hook is bash-only in this codebase (`hooks/scripts/context-handoff-sentinel.sh`
  and `hooks/scripts/session-cleanup.sh` per `hooks/hooks.json:177-198`).
  Capture Stop/SessionEnd via a small bash wrapper that calls
  `record_hook_event` from a new `hooks/scripts/record-hook-event.sh`
  shim — pattern follows the existing `post-tool-use.sh` adapter
  (`hooks/adapters/claude-code/post-tool-use.sh`). All other bash hooks
  under `hooks/scripts/*.sh` (scratch-pad, scratch-cleanup,
  user-prompt-check, context-monitor, etc.) likewise emit via the shim.
- Backfill: **none** (retracted). An earlier draft proposed a
  `_backfill_hook_events` parser walking JSONL, but the Claude Code host
  does not emit hook execution results into the transcript, so there is
  nothing to parse — see the Architectural Note above. `hook_events` is
  live-write-only and must be **excluded from `rebuild()`'s
  `_REBUILD_TABLES`** (mirroring `context_pressure_events`/ENH-2507 and
  the `test_run_events`/`cli_events` live-only tables ENH-2581's
  `rebuild()` deliberately leaves untouched).

### Read API

- `history_reader.recent_hook_events(event_name=None, exit_code=None,
  since=None, limit=50)`.
- `history_reader.hook_failure_rate(event_name, since=None)` — exit
  code != 0 rate per event.
- `history_reader.hook_latency_p95(event_name, since=None)` — the
  "is this hook getting slow" signal.

### CLI surface

- `ll-session recent --kind hook_event`.
- `ll-session hook-health [--since 7d]` (optional follow-on) — rollup
  of fires / failures / p95 duration per event_name.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis._

### Files to Modify

- `scripts/little_loops/session_store.py` — append v21 migration block
  to `_MIGRATIONS` (line 333 onward) creating `hook_events` + 3 indexes;
  add `"hook_event": "hook_events"` to `_KIND_TABLE` (line 223);
  add `record_hook_event(...)` and `hook_event_context(...)` next to
  `skill_event_context` (line 1109) so they share the same best-effort
  pattern; **do not add a `_backfill_hook_events`** (no transcript source
  — see Architectural Note) and ensure `hook_events` is left out of
  `rebuild()`'s `_REBUILD_TABLES`
- `scripts/little_loops/hooks/post_tool_use.py:137` — wrap `handle()` in
  `hook_event_context` (preserve the existing `contextlib.suppress` at
  line 158; the new context is best-effort outer wrap)
- `scripts/little_loops/hooks/user_prompt_submit.py:61` — wrap `handle()`
- `scripts/little_loops/hooks/pre_compact.py:84` — wrap `handle()`
- `scripts/little_loops/hooks/sweep_stale_refs.py:141` — wrap `handle()`
- `scripts/little_loops/hooks/session_start.py:75` — wrap `handle()`
- `scripts/little_loops/hooks/pre_tool_use.py` — wrap `handle()`
- `scripts/little_loops/hooks/post_commit.py` — wrap `handle()`
- `scripts/little_loops/hooks/edit_batch_nudge.py` — wrap `handle()`
- `scripts/little_loops/hooks/pre_compact_handoff.py` — wrap `handle()`
- `scripts/little_loops/hooks/learning_tests_gate.py`,
  `install_learning_gate.py` — wrap `handle()`
- `scripts/little_loops/hooks/__init__.py` (`_dispatch_table`,
  lines 74-99) — add a single outer wrap around each registered handler
  so the same context manager applies to every host-agnostic Python
  handler (alternative: wrap each module's `handle()` individually — see
  Implementation Steps for the trade-off)
- `scripts/little_loops/history_reader.py` — add `recent_hook_events`,
  `hook_failure_rate`, `hook_latency_p95` next to existing
  `recent_*` helpers (look for `recent_tool_events` /
  `recent_skill_events` as precedent)
- `scripts/little_loops/cli/session.py` — register `"hook_event"` in
  the `--kind` argument's `choices=` list so `ll-session recent
  --kind hook_event` works
- `scripts/little_loops/cli/session.py` — add `hook-health`
  subcommand (optional follow-on, gated by `--since`)
- `scripts/little_loops/templates/API.md` — add entry to
  `ll-history-context`, `ll-session` for the new `--kind` and
  subcommand
- `hooks/scripts/record-hook-event.sh` (NEW) — bash shim that calls
  `python -m little_loops.cli.session record-hook-event "$@"` so bash
  hooks (Stop, SessionEnd, scratch-cleanup, etc.) can emit rows; the
  shim is invoked from each existing bash hook after its main body
  exits, capturing `$?` as `exit_code`
- `hooks/adapters/claude-code/{stop,session-end}-adapter.sh` (NEW) —
  bash wrappers for the adapter layer, mirroring the
  `post-tool-use.sh` pattern

**Wiring pass additions (added by `/ll:wire-issue`):**

- `scripts/little_loops/__init__.py:62-131` — extend package `__all__`
  tuple to re-export `record_hook_event` and `hook_event_context` so the
  new public API is discoverable alongside the existing peer exports
  (LLHookEvent/LLHookResult already there)
- `scripts/little_loops/session_store.py:16-38` (module docstring
  "Public API" block) — append `record_hook_event` /
  `hook_event_context` lines paralleling the `record_skill_event` /
  `skill_event_context` listing
- `scripts/little_loops/session_store.py:1462-1484` (`recent()`
  docstring "Kinds" sentence) — append `"hook_event"` to the supported-kinds
  list (the `recent()` routing reads `_KIND_TABLE` at runtime, but the
  docstring is the user-facing contract)
- `scripts/little_loops/session_store.py:2824-2834` (`_REBUILD_TABLES`
  comment block) — enumerate `hook_events` in the live-only exclusion
  comment so future maintainers see the architectural note inline
- `scripts/little_loops/session_store.py:3304-3329` (`_EXPORT_TABLE_MAP` /
  `_EXPORT_DEFAULT_TABLES`) — decide whether to register
  `"hook_event": ("hook_events", "ts")` here (matches live-only
  exclusion — `cli_events` and `file_events` precedent not registered;
  default to NOT registering to keep `ll-session export` opt-in)
- `scripts/little_loops/observability/schema.py:479-633` (DES_VARIANTS
  tuple) — add `HookEventVariant` paralleling `SkillEventVariant`/
  `CliEventVariant`. **CRITICAL**: without this,
  `ll-verify-des-audit` (F5 audit gate, ENH-2475) will reject every
  `record_hook_event`/`hook_event_context` emit site as an uncovered
  event type
- `scripts/little_loops/config/features.py:529-558`
  (`AnalyticsCaptureConfig` + `from_dict`) — add `hooks: bool = True`
  dataclass field and the corresponding `from_dict` mapping. Mirrors
  `usage_events` precedent (ENH-2581 / ENH-2461)
- `scripts/little_loops/init/core.py:17` (`_ANALYTICS_CAPTURE_KEYS`
  tuple) — append `"hooks"`. Without this, `ll-init` defaults will not
  include the new gate, leaving users without an explicit `hooks: true`
  config entry
- `scripts/little_loops/config-schema.json:1608-1655` (`analytics.capture`
  schema properties) — add `"hooks": {"type": "boolean", "default":
  true, "description": "..."}` before `additionalProperties: false`;
  required for `test_config_schema.py` to pass

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/session.py` — dispatcher for `ll-session`
  recent / hook-health (the new `--kind hook_event` and aggregate
  subcommand land here)
- `scripts/little_loops/cli/__init__.py`, `cli/history.py` — register
  any new commands if the subcommand split is reused
- `scripts/little_loops/cli/backfill_worker.py` — **no change** (no
  `_backfill_hook_events` to wire; hook telemetry is live-write-only, see
  Architectural Note)

**Wiring pass additions (added by `/ll:wire-issue`):**

- `scripts/little_loops/cli/logs.py:25` — imports `cli_event_context` /
  `resolve_history_db`; observes the new `_KIND_TABLE` extension via
  the kind-discovery path that backs `ll-logs` calls; no functional
  change required but the import block must continue to compile after
  `_KIND_TABLE` gains `"hook_event"`
- `scripts/little_loops/cli/verify_des_audit.py:19-20, 106` — gates
  every DES emit site against `DES_VARIANT_TYPES`; will fail closed if
  `record_hook_event` / `hook_event_context` emit a `HookEvent` without
  a registered `HookEventVariant` (paired with the schema.py edit above)
- `scripts/little_loops/extension.py` (uses `_register_hook_intents`
  via `wire_extensions`) — peer hook intent registration; must
  coexist with the new `_dispatch_table` outer wrap (under Option A,
  wrap is per-handler; under Option B, this becomes the integration
  point)
- `scripts/little_loops/__init__.py:21` — package-level
  re-exports of `LLHookEvent`/`LLHookResult`; per the re-export
  precedent `record_hook_event` and `hook_event_context` belong here
  too (see Files to Modify)
- `scripts/little_loops/hooks/types.py:20-145` — `LLHookEvent` /
  `LLHookResult` definitions referenced by `hook_event_context`;
  unaffected by the new schema but the typed-completion handle needs
  to coexist (use a `dataclass` similar to `SkillEventCompletion` per
  issue §Implementation Steps 2.2)

### Similar Patterns

- `session_store.py:1109` `skill_event_context` — best-effort
  `@contextmanager` with mutable `SkillEventCompletion` handle (the
  right structural model for `hook_event_context`)
- `session_store.py:1055` `cli_event_context` — eager
  `@contextmanager` (NOT best-effort; do NOT mirror)
- `session_store.py:1878` `_backfill_usage_events` — useful only for the
  precise live-`INSERT` shape (column list, `_index()` FTS call shape);
  **not** as a backfill template — `hook_events` has no backfill path
  (see Architectural Note). Contrast the live-only recorders
  `record_test_run_event` / `record_context_pressure_event` (ENH-2507),
  which are the correct structural model here.
- `scripts/little_loops/hooks/post_tool_use.py:158` — the canonical
  inner `with contextlib.suppress(Exception):`; preserve it inside the
  new outer `hook_event_context`

### Tests

- `scripts/tests/test_session_store.py` — extend
  `TestEnsureDb.test_all_tables_created` to assert `"hook_events"` is
  in the table list (currently asserts 8 tables at line 96-106);
  bump that assertion to include `"hook_events"`
- `scripts/tests/test_session_store.py` — add a `TestHookEvents`
  class covering: (a) migration adds the table, (b) `record_hook_event`
  inserts a row, (c) `hook_event_context` writes `exit_code`/`duration_ms`
  on clean exit and on raised exception, (d) DB-absent /
  DB-locked does NOT raise (best-effort contract)
- `scripts/tests/test_hook_post_tool_use.py` — add a fixture that
  captures `hook_events` rows around a `handle()` call and asserts
  one row is inserted
- `scripts/tests/test_hook_user_prompt_submit.py`,
  `test_hook_session_start.py` — same fixture pattern
- `scripts/tests/test_hooks_integration.py` — extend with a
  multi-event rollup test: trigger 3 fires, 1 failure → assert
  `hook_failure_rate("PostToolUse")` returns ≈0.33
- (NEW) `scripts/tests/test_history_reader_hook.py` — direct tests
  for `recent_hook_events`, `hook_failure_rate`, `hook_latency_p95`
  using an in-memory or temp SQLite fixture

**Wiring pass additions (added by `/ll:wire-issue`):**

- `scripts/tests/test_session_store.py:1372` (`TestSchemaV6`),
  `:1817` (`TestCliEventContext`), `:1932` / `:1984`
  (`TestSchemaV9` / `TestSchemaV10`), `:2080` (`TestSchemaV14`),
  `:3658` / `:3699` (`TestSqliteTransportStyleUsage`) — 7+
  `assert SCHEMA_VERSION == 20` sites; ALL must bump to 21 alongside
  the migration. The issue's §1.1 mentions the constant at line 207;
  the test-side bumps are equally required to keep pytest green
- `scripts/tests/test_session_store.py:3413` — `set(VALID_KINDS) ==
  set(_KIND_TABLE.keys())` assertion — must hold with `"hook_event"`
  added to both tuples; if only one is updated, the test fires
- `scripts/tests/test_session_store.py:1945-1969, 2044-2048, 2109-2113,
  3730-3734, 3898-3902` — migration-list tests that iterate
  `_MIGRATIONS[:N]` via `_bootstrap_schema_at`. Existing v14 callers
  (`:3930, :4174, :4422`) keep working unchanged (slice past v14 is
  unaffected); verify post-implementation that the helper's
  version-by-version semantics still hold
- (NEW) `scripts/tests/test_session_store.py::TestSchemaV21HookEvents`
  — column-set assertion + 3-index-existence assertion + v20→v21
  upgrade test (bootstrap at v20, run `ensure_db`, assert
  `hook_events` table + indexes exist). Model on `TestSchemaV20UsageEvents`
  at `test_session_store.py:3221-3243`
- (NEW) `scripts/tests/test_session_store.py::TestRecordHookEvent` —
  round-trip INSERT (single row + multi-row ordering) + FTS5 search
  propagation; kwarg-only signature test (every column test). Model
  on `TestRecordTestRunEvent` at `:4362-4432`
- (NEW) `scripts/tests/test_session_store.py::TestHookEventContext` —
  insert-on-enter/update-on-exit success path, raise-path exit_code=1
  propagation, host-provided exit_code, custom event_name/matcher/
  script propagation, best-effort-on-unopenable-db. Model on
  `TestSkillEventContext` at `:3969-4033`
- `scripts/tests/test_history_reader.py:1395-1546` — `TestNewEventReaders`
  extension: add `test_recent_hook_events_*` (recency ordering,
  filter_by_event_name, filter_by_exit_code, since filter),
  `test_hook_failure_rate` (per-event_name rollup, dispatch-only vs
  completed), `test_hook_latency_p95`
- `scripts/tests/test_history_reader.py:1530-1545` (`test_readers_return_empty_on_missing_db`)
  — extend the missing-db batch test to include
  `recent_hook_events`, `hook_failure_rate`, `hook_latency_p95`
- `scripts/tests/test_verify_kinds.py:18-33` (`TestRun.test_clean_state_returns_zero`)
  — regression gate; no edit required (it reads `_KIND_TABLE` /
  `_MIGRATIONS` dynamically). But the implementation MUST add both
  the migration AND the `_KIND_TABLE` entry in lock-step, or this
  test flips to failure
- `scripts/tests/test_ll_session.py:58-105` (`TestArgumentParsing`)
  — add `test_recent_subcommand_hook_event_accepted` + `test_search_subcommand_hook_event_accepted`
  pair (mirroring the `test_run` precedent at `:88-105`)
- `scripts/tests/test_ll_session.py:1073-1135`
  (`TestSkillStatsAndNewKinds`) — add `test_recent_kind_hook_event_outputs_row`
  (seed via `record_hook_event`, run `ll-session recent --kind
  hook_event`, assert stdout shows the row)
- `scripts/tests/test_ll_session.py:1043-1072` (subparser pattern
  for `skill-stats`) — mirror for `hook-health` subcommand:
  `test_hook_health_subcommand_outputs_rollup`,
  `test_hook_health_subcommand_json_flag`,
  `test_hook_health_since_argument`
- `scripts/tests/test_config.py:1443-1485` (`TestAnalyticsCaptureConfig`)
  — add `test_hooks_true_default` + `test_hooks_false_overrides` cases
  (mirroring `test_file_events_false` at `:1476-1480`)
- `scripts/tests/test_config.py:3043-3098` (`BRConfig` integration)
  — extend round-trip default assertion for `analytics_capture.hooks`
- `scripts/tests/test_config_schema.py:449-485`
  (`test_analytics_capture_in_schema`) — add `assert "hooks" in
  capture_props` mirroring `file_events` at `:478-480`
- `scripts/tests/test_init_core.py:720` — `schema_default(f"analytics.capture.{key}")`
  iterates `_ANALYTICS_CAPTURE_KEYS`; if the const is extended to
  include `"hooks"`, this test exercises the new key automatically
- `scripts/tests/test_wiring_init_and_configure.py:58-65` — wiring
  docs reference `analytics.capture.*`; verify the wiring doc still
  enumerates each gate after the new `hooks` key lands
- `scripts/tests/test_config.py:1391-1440` (analytics.from_dict round-trip)
  — extend to include `hooks` key
- `scripts/tests/test_assistant_messages.py:11, 88` —
  `assert SCHEMA_VERSION == 20` hardcoded; bump to 21 alongside the
  migration
- `scripts/tests/test_hook_intents.py:477-585` (`main_hooks()`
  integration tests) — every dispatch test will exercise the new
  outer wrap on `_dispatch_table`; no edits required but the new
  context manager's emissions get exercised end-to-end here. Add a
  `test_record_hook_event_in_dispatch` case that stubs
  `_dispatch_table`, runs `main_hooks()`, then asserts a `hook_events`
  row exists via `recent_hook_events(db)`
- `scripts/tests/test_extension.py:448-483`
  (`test_wire_extensions_populates_hook_intent_registry`) — extension
  tests must continue to pass; the new outer wrap on `_dispatch_table`
  is orthogonal to extension wiring
- (NEW) per-handler capture fixtures — extend the existing
  `test_hook_post_tool_use.py:100-132` pattern (the
  `TestPostToolUseWithSessionStore.test_writes_row_when_analytics_enabled`
  precedent) to add a `TestHookEventsInHandler` class that wraps the
  existing handler tests, opening `.ll/history.db` post-handler and
  asserting one `hook_events` row was written. Mirror in:
  - `scripts/tests/test_hook_post_tool_use.py`
  - `scripts/tests/test_hook_user_prompt_submit.py`
  - `scripts/tests/test_hook_session_start.py`
  - `scripts/tests/test_pre_compact.py`
  - `scripts/tests/test_pre_compact_handoff.py`
  - `scripts/tests/test_sweep_stale_refs.py`
  - `scripts/tests/test_edit_batch_hook.py`
  - `scripts/tests/test_install_learning_gate.py`
  - `scripts/tests/test_learning_tests_discoverability.py`
- (NEW) `scripts/tests/test_record_hook_event_shim.py` — bash shim
  end-to-end test. Model on
  `scripts/tests/test_check_decisions_yaml_hook.py:146-209`
  (`test_hook_blocks_othe_203_write`). Tests:
  - shim exits 0 on success
  - shim captures `$?` from the preceding bash command
  - shim writes to `.ll/history.db` via
    `python -m little_loops.cli.session record-hook-event "$@"`
  - shim is graceful on DB-absent (does not propagate sqlite failures)
- (NEW) `scripts/tests/test_des_variants.py` (if not already present)
  — assert `HookEventVariant` is registered in `DES_VARIANTS` after
  schema.py edit; mirror `SkillEventVariant` regression coverage

### Documentation

- `docs/ARCHITECTURE.md` — schema versions table; bump v20→v21 entry
  to mention `hook_events` (ENH-2506)
- `docs/reference/API.md` — `session_store` section: add
  `record_hook_event` / `hook_event_context` / `_backfill_hook_events`;
  `hooks` section: note the new telemetry wrap on every `handle()`
- `docs/reference/CLI.md` — `ll-session recent --kind` values table;
  `ll-session hook-health` subcommand entry
- `docs/claude-code/hooks-reference.md` — update the hook-intent
  banner per the `reference_dispatch_table_usage_banner` memory
  (`scripts/little_loops/hooks/__init__.py:_USAGE` line 50-54)
- `docs/development/TROUBLESHOOTING.md` — add the "hook didn't fire"
  debug section pointing to `ll-session recent --kind hook_event`

**Wiring pass additions (added by `/ll:wire-issue`):**

- `docs/ARCHITECTURE.md:655-678` (schema versions table) — add v21
  row for `hook_events` (ENH-2506); the existing v1–v20 rows remain
- `docs/ARCHITECTURE.md:723` ("ensure_db() — bootstrap schema
  (v1–v20)") — bump literal to `v1–v21`
- `docs/ARCHITECTURE.md:748` ("Bootstrap schema (v1–v20 migrations)")
  — bump literal to `v1–v21`
- `docs/ARCHITECTURE.md:811` ("See also: ... full schema-version
  table (v1–v20)") — bump literal to `v1–v21`
- `docs/guides/HISTORY_SESSION_GUIDE.md:51` ("Current schema
  version: 18") — bump to whatever live version applies (per the
  issue's Scope Boundary note, read `session_store.py:SCHEMA_VERSION`
  at implementation time; the doc's prose already drifts from source
  — make this consistent with the new migration slot)
- `docs/guides/HISTORY_SESSION_GUIDE.md:53-75` (schema-version table)
  — add v21 row for `hook_events`
- `docs/guides/HISTORY_SESSION_GUIDE.md:81-99` ("What Gets Recorded"
  table) — add `hook_events` row with columns enumerated
- `docs/guides/HISTORY_SESSION_GUIDE.md:101-107` (`analytics.capture.*`
  config-keys list) — add `hooks` entry mirroring `file_events` line
- `docs/guides/HISTORY_SESSION_GUIDE.md:170, 180` (`--kind` choices in
  prose) — append `hook_event` to both
- `docs/reference/API.md:6837-6850` (`from little_loops.history_reader
  import ...` block) — add `recent_hook_events`,
  `hook_failure_rate`, `hook_latency_p95` to the public import block
- `docs/reference/API.md:7282-7290` (`from
  little_loops.session_store import ...` block) — append
  `record_hook_event` and `hook_event_context` paralleling the
  `skill_event_context` listing at `:7285`
- `docs/reference/API.md:7331-7344` (new `hook_event_context` API
  section) — mirror the `skill_event_context` documentation block;
  this is the user-facing contract for the new context manager
- `docs/reference/CLI.md:2427` and `:2435` (`--kind` choice prose
  lists) — append `hook_event` to both
- `docs/reference/CONFIGURATION.md:507-520` (`analytics.capture`
  config-keys table) — add `hooks` row with default `true` and a
  short description referencing ENH-2506

### Configuration

- `.ll/ll-config.json` → `analytics.capture` keys: gate the new
  producer on a new `analytics.capture.hooks` flag (parallel to
  `analytics.capture.file_events` / `analytics.capture.skills`),
  defaulting to `true`. The `skill_event_context` config parameter is
  a forward-compat stub; reuse the same `config: dict | None` shape.

**Wiring pass additions (added by `/ll:wire-issue`):**

The new `analytics.capture.hooks` config flag must be plumbed through
every layer; adding the user-facing key alone is not sufficient:

- `scripts/little_loops/config/features.py:537-542` — declare
  `hooks: bool = True` as a dataclass field, parallel to
  `usage_events: bool = True`. This is the runtime type that
  `ll_init` / `from_dict` materialize
- `scripts/little_loops/config/features.py:529-558` (`from_dict`)
  — add the `hooks` key mapping; default `True` when key is absent
  (forward compat — older `.ll/ll-config.json` files continue to
  enable telemetry)
- `scripts/little_loops/init/core.py:17` (`_ANALYTICS_CAPTURE_KEYS`)
  — append `"hooks"`. Without this, `schema_default(f"analytics.capture.hooks")`
  returns `None` and the init template omits the key, leaving users
  without an opt-out surface
- `scripts/little_loops/config-schema.json:1608-1655` — add
  `"hooks": {"type": "boolean", "default": true, "description":
  "Capture per-fire hook telemetry into history.db (ENH-2506)."}`
  to `analytics.capture.properties`, before `additionalProperties: false`
- `scripts/tests/test_config.py:1391-1440` (round-trip + from_dict
  tests) — extend to cover the new key
- `scripts/tests/test_config.py:1443-1485` (`TestAnalyticsCaptureConfig`)
  — extend with `test_hooks_true_default` + `test_hooks_false_overrides`
- `scripts/tests/test_config.py:3043-3098` (`BRConfig` integration)
  — extend round-trip default assertion
- `scripts/tests/test_config_schema.py:449-485`
  (`test_analytics_capture_in_schema`) — add `"hooks" in capture_props`
  assertion
- `scripts/tests/test_init_core.py:720` — assert
  `schema_default("analytics.capture.hooks")` is registered (via the
  `_ANALYTICS_CAPTURE_KEYS` iteration in init/core.py)
- `scripts/tests/test_wiring_init_and_configure.py:58-65` — verify the
  wiring doc still enumerates each gate after the new key lands
- `scripts/little_loops/hooks/post_tool_use.py:151` — outer wrap
  goes OUTSIDE the existing `feature_enabled(config, "analytics.enabled")`
  gate (per issue §Implementation Steps 4.1). The new
  `analytics.capture.hooks` gate is layered on the inside: the
  context manager reads `config["analytics"]["capture"]["hooks"]`
  and no-ops when disabled (mirroring `skill_event_context`'s
  forward-compat stub parameter)
- `scripts/little_loops/hooks/scripts/lib/common.sh:184-198` — the
  bash shim reuses `ll_resolve_config` + `ll_feature_enabled` for the
  `analytics.capture.hooks` gate check; no new lib helper needed

## Implementation Steps

_Added by `/ll:refine-issue` — concrete step ordering that mirrors the
existing migration / wrap pattern._

1. **Schema migration (session_store.py)**:
   1.1. Append a new entry to `_MIGRATIONS` (after the v20 usage_events
   block at line 718) with the `hook_events` CREATE TABLE + 3 CREATE
   INDEX statements from the Proposed Solution. Comment it `# v21
   (ENH-2506): hook_events — …` following the v18/v19/v20 convention
   (note: `SCHEMA_VERSION = 20` at line 207 — the issue's "Bump
   `SCHEMA_VERSION`" instruction lands this at v21).
   1.2. Add `"hook_event": "hook_events"` to `_KIND_TABLE` (line 223).
   1.3. Verify `ll-verify-kinds` passes (gates unregistered CREATE
   TABLE statements per ENH-2581).

2. **Producer (session_store.py)**:
   2.1. Add `record_hook_event(db_path, *, ts, session_id, event_name,
   matcher, script, exit_code, duration_ms, stderr_preview=None,
   head_sha=None, branch=None)` modeled on `record_tool_event` /
   `record_skill_event` — single-row INSERT with FTS5 `_index()` call.
   2.2. Add `@contextmanager def hook_event_context(db_path, session_id,
   event_name, matcher, script)` modeled on `skill_event_context`
   (lines 1109-1182) — best-effort, mutable completion handle so the
   caller can set `exit_code` and `stderr_preview` post-hoc. Use
   `time.monotonic()` for the duration (the existing
   `cli_event_context` / `skill_event_context` use `time.time()` —
   monotonic is the correct choice for "elapsed time of this hook fire"
   and matches the issue's specification).

3. **Bash shim** (NEW):
   3.1. Write `hooks/scripts/record-hook-event.sh` — captures `$?`,
   `$STDERR_PREVIEW` (first 512 bytes), `$MATCHER`,
   `$EVENT_NAME`, calls the Python entry point. Mirrors the existing
   `post-tool-use.sh` adapter pattern (no new adapter is needed — the
   shim is invoked from each bash hook directly).
   3.2. Wrap each bash hook entry point in `hooks/hooks.json` to
   invoke the shim after the existing body. Specifically: add a second
   command after each existing bash hook under `PostToolUse`, `Stop`,
   `SessionEnd`, `PreCompact`, `UserPromptSubmit`, `SessionStart`
   that invokes the shim with the right `event_name` and `matcher`.
   (Trade-off — see the Decision-Point below.)

4. **Python wrap (each handler)**:
   4.1. Edit each `handle()` function listed in the Integration Map to
   wrap its body in `with hook_event_context(...):` at the outermost
   level (so the context still records `exit_code` even when the
   handler raises). Where a handler is itself gated by
   `analytics.enabled` (e.g. `post_tool_use.py:151`), the wrap goes
   *outside* the gate so a no-config run still produces telemetry.

5. **Read API (history_reader.py)**:
   5.1. `recent_hook_events(event_name=None, exit_code=None, since=None,
   limit=50)` — copy the shape of `recent_tool_events` /
   `recent_skill_events`. Use `_connect_readonly` (line ~220) and
   `_stale_cutoff` (line ~1397) for consistency with peer functions.
   5.2. `hook_failure_rate(event_name, since=None)` — single SQL with
   `AVG(CASE WHEN exit_code != 0 THEN 1.0 ELSE 0.0 END)`.
   5.3. `hook_latency_p95(event_name, since=None)` — SQL aggregate.

6. **CLI surface (cli/session.py)**:
   6.1. Add `"hook_event"` to the `--kind` argument's `choices=` tuple
   in `recent` subcommand.
   6.2. Add `hook-health` subcommand with `--since` argument
   (default 7d), printing per-event_name fires / failures / p95.

7. **Tests** (per Integration Map → Tests):
   7.1. Bump `test_session_store.py::TestEnsureDb::test_all_tables_created`
   to include `"hook_events"` in the expected table set.
   7.2. Add `TestHookEvents` class with the 4 cases listed.
   7.3. Add the `hook_events` capture fixture to each existing
   `test_hook_*.py` file.
   7.4. (NEW) `test_history_reader_hook.py`.
   7.5. Run `python -m pytest scripts/tests/ -v --tb=short` and
   confirm all green.

8. **Backfill (session_store.py)**:
   8.1. Add `_backfill_hook_events(conn, source)` mirroring
   `_backfill_usage_events` (line 1878). Iterate `_iter_events(source)`,
   filter on `record.get("type") == "hook_fire"` (the synthetic shape
   — verify against the live JSONL shape during implementation), and
   INSERT into `hook_events`.
   8.2. Wire `_backfill_hook_events` into the backfill orchestrator
   in `cli/backfill_worker.py` so `rebuild()` invokes it.

9. **Verification**: `ruff check scripts/`, `ruff format scripts/`,
   `python -m mypy scripts/little_loops/`, and `python -m pytest
   scripts/tests/`. Per `.claude/CLAUDE.md`, the pytest suite is the
   project's only CI gate — do not add GitHub Actions workflows.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be
included in the implementation. Each is a concrete code or doc edit
discovered by tracing every file that imports / calls / depends on
the planned changes._

10. **Module docstrings (session_store.py:16-38, history_reader.py:9-41,
    cli/session.py:7-23)** — append `record_hook_event` /
    `hook_event_context` / `recent_hook_events` / `hook_failure_rate`
    / `hook_latency_p95` entries to each module's "Public API" block,
    keeping the alphabetical ordering convention.

11. **`__all__` block (session_store.py:61-93)** — append
    `"record_hook_event"` and `"hook_event_context"` to the export
    tuple (peer to `record_commit_event`, `skill_event_context`,
    `record_test_run_event`).

12. **`recent()` docstring (session_store.py:1462-1484)** — append
    `"hook_event"` to the supported-kinds prose list so the
    user-facing contract matches the runtime `_KIND_TABLE` lookup.

13. **`_REBUILD_TABLES` exclusion comment
    (session_store.py:2818-2834)** — add `hook_events` to the
    inline enumeration of live-only excluded tables so future
    maintainers see the architectural rationale in context
    (parallel to `cli_events`, `file_events`, `test_run_events`,
    `issue_events`, `loop_events`, `commit_events`,
    `issue_snapshots`).

14. **`_EXPORT_TABLE_MAP` decision (session_store.py:3304-3329)** —
    decide whether to register `"hook_event": ("hook_events", "ts")`
    here. The plan defaults to NOT registering (keep `ll-session
    export` opt-in — matches `cli_events` / `file_events` precedent);
    document the decision in the inline comment.

15. **DES_VARIANTS register (`observability/schema.py:479-633`)** —
    add `HookEventVariant` paralleling `SkillEventVariant` /
    `CliEventVariant`. **F5 audit gate (ENH-2475)** —
    `ll-verify-des-audit` will fail closed if any
    `record_hook_event` / `hook_event_context` emit site is added
    without a registered variant. Implementation must land both the
    schema.py registration AND the new emit calls in lock-step.

16. **`AnalyticsCaptureConfig.hooks` dataclass field
    (`config/features.py:537-542` + `from_dict` at `:529-558`)** —
    declare `hooks: bool = True` and the corresponding mapping. Peer
    to `usage_events` precedent (ENH-2461).

17. **`_ANALYTICS_CAPTURE_KEYS` const (`init/core.py:17`)** — append
    `"hooks"`. Required for `schema_default("analytics.capture.hooks")`
    to resolve during `ll-init`.

18. **`config-schema.json` `analytics.capture.hooks` property
    (lines 1608-1655)** — add boolean property with `default: true`
    and a description referencing ENH-2506. Required for
    `test_config_schema.py` and the `additionalProperties: false`
    gate to pass.

19. **7+ `SCHEMA_VERSION == 20` assertion bumps in
    `scripts/tests/test_session_store.py:1372, 1817, 1932, 1984,
    2080, 3658, 3699` and `scripts/tests/test_assistant_messages.py:88`**
    — bump to 21 alongside the migration. The issue's §1.1 covers
    the session_store.py constant; the test-side bumps are equally
    required to keep pytest green.

20. **`set(VALID_KINDS) == set(_KIND_TABLE.keys())` assertion
    (`scripts/tests/test_session_store.py:3413`)** — verify the
    tuple sets stay in lock-step after adding `"hook_event"` to both.

21. **Bash shim wiring (`hooks/hooks.json` + 15 `hooks/scripts/*.sh`
    + 7 `hooks/adapters/claude-code/*.sh`)** — implement Option A
    (two-commands shape, per the issue's Decision-Point): add a
    second command entry per bash hook that invokes
    `hooks/scripts/record-hook-event.sh`. Coverage matrix per
    `hooks.json` is enumerated at `:5-233` (the 18 follow-on entries
    identified by Agent 2). For each adapter that delegates to
    Python (`hooks/adapters/claude-code/post-tool-use.sh`,
    `pre-tool-use.sh`, `precompact.sh`, `precompact-handoff.sh`,
    `edit-batch-nudge.sh`, `session-start.sh`, `session-end.sh`)
    the wrap goes around the Python invoke, not the adapter
    script (Option A surface — Python handlers are already wrapped
    per Implementation Step 4).

22. **Bash shim test (NEW `scripts/tests/test_record_hook_event_shim.py`)** —
    add `subprocess.run`-based shim coverage modeled on
    `scripts/tests/test_check_decisions_yaml_hook.py:146-209`. Tests:
    (a) shim exits 0 on success, (b) `$?` of the preceding command is
    captured as `exit_code`, (c) `.ll/history.db` row exists with
    the right `event_name` / `matcher`, (d) shim is DB-absent
    graceful.

23. **Per-handler `hook_events` capture fixtures** — extend the
    existing handler-test files with a `TestHookEventsInHandler`
    class that asserts one `hook_events` row was written around
    each `handle()` call. Files:
    `scripts/tests/test_hook_post_tool_use.py`,
    `test_hook_user_prompt_submit.py`,
    `test_hook_session_start.py`,
    `test_pre_compact.py`,
    `test_pre_compact_handoff.py`,
    `test_sweep_stale_refs.py`,
    `test_edit_batch_hook.py`,
    `test_install_learning_gate.py`,
    `test_learning_tests_discoverability.py`.

24. **`docs/ARCHITECTURE.md` schema-version bump** — 4 sites: the
    schema-versions table at `:655-678` (add v21 row for
    `hook_events`/ENH-2506), and 3 literals at `:723, :748, :811`
    (bump `v1–v20` → `v1–v21`).

25. **`docs/guides/HISTORY_SESSION_GUIDE.md` 5-site bump** — the
    schema version literal at `:51`, the schema-version table row at
    `:53-75`, the `What Gets Recorded` row at `:81-99`, the
    `analytics.capture.*` entry at `:101-107`, and the `--kind`
    prose lists at `:170, :180`.

26. **`docs/reference/API.md` 3-site update** — import block at
    `:6837-6850` (read API), import block at `:7282-7290`
    (session_store), and the new `hook_event_context` API section
    at `:7331-7344` (mirror `skill_event_context` precedent).

27. **`docs/reference/CLI.md` and `docs/reference/CONFIGURATION.md`**
    — append `hook_event` to the `--kind` choice lists at
    `:2427, :2435`; add `analytics.capture.hooks` row to the
    config-keys table at `docs/reference/CONFIGURATION.md:507-520`.

### Decision-Point (Implementation Steps §3)

The bash shim wiring has two viable shapes:

**Option A** — add a second command per `hooks/hooks.json` entry that
invokes the shim. Pros: zero changes to existing bash bodies (no
behavioral risk to shipped hooks); a single `hooks.json` edit is the
only required change per hook. Cons: every entry now has two
commands (visual noise); bash hooks that exit early (e.g. on missing
config) still emit a row, so the "fires / failures" rollup includes
early-exit hooks.

> **Selected:** Option A — per the stated recommendation (lower risk,
> matches the existing two-command shape already used under
> PostToolUse for `context-monitor.sh` + `session-capture.sh`).

**Option B** — modify each bash script to call the shim inline at the
end (or via a trap). Pros: only fires that actually reached the shim
get recorded (cleaner signal); one edit per script. Cons: every bash
script needs a behavioural review; trap placement must respect
existing exit-code semantics in scripts that already set `exit $?` at
the end.

**Recommended**: Option A for v1 (lower risk, matches the existing
"two commands" shape under PostToolUse for `context-monitor.sh` +
`session-capture.sh`); revisit with Option B in a follow-on if
"fires that reached the shim" becomes the preferred signal.

## Acceptance Criteria

- Schema migration lands; `hook_events` exists; `SCHEMA_VERSION` bumped.
- Every `PostToolUse` fire writes one row with `event_name="PostToolUse"`,
  `matcher`, `script`, `exit_code`, `duration_ms`.
- A hook that returns non-zero writes `exit_code=<that code>` and the
  outer wrapper still swallows the failure (preserving EPIC-1707
  contract).
- A hook that produces stderr writes the first 512 bytes to
  `stderr_preview`.
- DB-absent/locked does not change hook exit code.
- `ll-session recent --kind hook_event` returns rows; failure-rate
  rollup works.
- Tests cover: success/failure/timeout paths, stderr truncation, DB
  absent graceful degradation.

## Sources

- `autodev-bug2501-kill-analysis.md` (2026-07-07) — "the missing
  events.jsonl is what would distinguish Modes A/B/C" — the hooks that
  should have fired during the killed run left no trace
- EPIC-2457 review (third-pass expansion, 2026-07-06)
- `scripts/little_loops/hooks/__init__.py:_dispatch_table()` (lines 74-99)
  — registers every hook; this issue extends the registration with a
  recording wrap
- ENH-2495 — sibling lifecycle *events* (handoff_needed, etc.); this
  issue captures the *fires* that produced them
- ENH-2496 — sibling config-snapshot work; same `analytics.capture`
  gate applies

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; hook write-paths note |
| `docs/reference/API.md` | `session_store`, `hooks` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |
| `reference_dispatch_table_usage_banner` (memory) | Update hook intent list when adding new intent handlers |

## Status

**Completed** | Created: 2026-07-06 | Completed: 2026-07-22 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("Bump
`SCHEMA_VERSION`"). Several other active EPIC-2457 siblings (ENH-2492,
ENH-2463, ENH-2464, ENH-2465, ENH-2466, ENH-2493, ENH-2494, ENH-2495,
ENH-2496, ENH-2497, ENH-2498, ENH-2504, ENH-2511, and others) independently
make the same schema-slot claim in their own Integration Maps — they cannot
all land at the same version number. Verified against current code
(`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's implied slot;
each child lands its own migration at whatever version is open when it is
implemented (no coordinated release; per EPIC-2457's own "no shared helper
module is required" scope note).

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): **ENH-2498** (prompt
optimization outcomes) also wraps `user_prompt_submit.py`. The two issues
split ownership by **table semantics**, not by hook path: this issue owns
generic execution telemetry — `exit_code`, `duration_ms`, `matcher`,
`script`, `stderr_tail` — for every registered hook intent. ENH-2498 owns
prompt-optimization-specific semantics — `mode` (`quick` / `thorough`),
the offer/bypass reason, and the best-effort outcome — recorded in its own
row. One UserPromptSubmit invocation may intentionally produce **one row in
each table**; this is by design, not duplication.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): **ENH-2505** (subagent
session-tree) registers two new host-agnostic Python handlers
(`SubagentStart`, `SubagentStop`) in `hooks/hooks.json`,
`hooks/__init__.py`, and the static dispatcher usage text. This issue's
dispatcher-level `hook_event_context` wrapper MUST cover those two
dynamically-registered intents exactly once — no second pass — and the new
handlers MUST NOT additionally wrap themselves in this issue's context
manager. The two implementations must agree on a single source of telemetry
to avoid both omission and double-counting.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): **ENH-2497** (subagent Task
discrimination) also modifies `post_tool_use.py` to extract `agent_type`
into the new `tool_events.agent_type` column. The two issues operate at
distinct nesting levels: ENH-2497's `tool_events` insert and FTS `_index()`
remain the **inner** operation, already best-effort-wrapped in
`contextlib.suppress(Exception)` at `post_tool_use.py:158`. This issue's
`hook_event_context` is the **outer, independently-failing** write that
MUST NOT alter, roll back, or wrap the inner `tool_events` persistence. A
telemetry failure must never suppress an agent-spawn write, and vice versa.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The `ll-verify-des-audit`
contract scans for `self._emit(...)` / `event_bus.emit(...)` calls
(`observability/audit.py:55-67`). Direct DB writers like
`record_hook_event(...)` / `hook_event_context(...)` are NOT covered by
the Phase 1 regex unless explicitly registered in
`observability/schema.py` `DES_VARIANTS`. **Register `HookEventVariant`
only if the concrete emit site is discovered by the audit**; if the
implementation remains a pure direct insert / context manager without
going through `event_bus`, the variant is not required. Implementers
should run `ll-verify-des-audit` post-implementation and resolve any
uncovered event types it surfaces (ENH-2475 adoption gate). Sibling
ENH-2504 carries the same contract for `VerdictEventVariant`.

---

## Scope Boundary — Staleness Update (added by `/ll:refine-issue`, 2026-07-22)

**Note**: Verified against current code (`scripts/little_loops/session_store.py`).
The earlier Scope Boundary note above pinned `SCHEMA_VERSION` at **20** with an
implied next slot of **v21**. That has since moved on — `SCHEMA_VERSION` is now
**29**. Nine more migrations have landed on top of v20, none of them this
issue's:

- v21 (FEAT-2478) — OTel `gen_ai.*` addenda on `usage_events`
- v22 (ENH-2492) — `orchestration_runs`
- v23 (ENH-2463) — `loop_runs`
- v24 (ENH-2497) — `agent_type` on `tool_events`
- v25 (ENH-2511) — MCP fields on `tool_events`
- v26 (ENH-2466) — `learning_test_events`
- v27 (ENH-2495/ENH-2509) — `session_lifecycle_events`
- v28 (ENH-2505) — `subagent_runs`
- v29 (ENH-2723) — `run_id` on `usage_events`

The **next available slot is v30, not v21**. Every hardcoded `21` / `assert
SCHEMA_VERSION == 20` reference throughout this issue's Integration Map,
Implementation Steps, and Wiring Phase sections is illustrative only — read
the live constant at implementation time, per this issue's own existing
instruction ("At implementation time, read the live `SCHEMA_VERSION` constant
...").

**ENH-2505 has landed** (this issue's own Scope Boundary above only
anticipated it). `hooks/subagent_start.py` and `hooks/subagent_stop.py` now
exist, each already wrapping its body in a blanket `try/except Exception:
pass` and calling `record_subagent_run_start` / `record_subagent_run_stop`
into `subagent_runs` (v28). This issue's dispatcher-level `hook_event_context`
wrap must cover these two handlers for generic fire/exit_code/duration
telemetry **without** touching or duplicating their existing `subagent_runs`
writes — the two tables are orthogonal (`hook_events` = did the hook fire and
how long did it take; `subagent_runs` = subagent lifecycle state), matching
the coexistence contract this issue's ENH-2505 Scope Boundary note already
committed to.

**`main_hooks()` has no outer try/except today** — confirmed by direct read of
`scripts/little_loops/hooks/__init__.py`: `handler(event)` is called with no
surrounding `try` in `main_hooks()` itself; a raised (unswallowed) exception
would propagate to process exit, not to a silent `exit_code=0`. The "outer
try/except...swallows" behavior described in this issue's Summary lives
**inside** individual handler files (e.g. `subagent_stop.py`'s
`try/except Exception: pass`, `post_tool_use.py`'s two
`contextlib.suppress(Exception)` blocks), not in the dispatcher. This matters
for placement: the correct insertion point for a dispatcher-level
`hook_event_context` wrap is around the `handler(event)` call inside
`main_hooks()` (currently ~line 147 in `hooks/__init__.py`) — this is the one
point every Python-dispatched intent funnels through uniformly, regardless of
each handler's own internal suppress style. Confirmed separately: the `Stop`
hook intent is **not** routed through `main_hooks()`/`_dispatch_table()` at
all — `hooks/hooks.json` binds it directly to two raw bash scripts
(`context-handoff-sentinel.sh`, `session-cleanup.sh`). This matches (and
confirms) this issue's existing plan to cover `Stop`/`SessionEnd` only via the
bash shim, not the Python dispatcher wrap.

**Freshest `DES_VARIANTS` precedent**: `SubagentRunVariant`
(`observability/schema.py`, ~line 508) is a fresher Channel-A direct-writer
example than `SkillEventVariant` for modeling the new `HookEventVariant` —
same shape (`@dataclass(frozen=True)` subclassing `DESVariant` with a
`Literal` `type` field), grouped under the `# --- Channel A: Direct writers
---` comment inside the `DES_VARIANTS` tuple (~line 627). No separate registry
call needed; `DES_VARIANT_TYPES` auto-derives from each variant's `type`
default.

**Current `AnalyticsCaptureConfig` field list** (`config/features.py`,
confirmed present today): `skills`, `cli_commands`, `corrections`,
`file_events`, `usage_events`, `correction_patterns` — no `hooks` field yet,
confirming the gap this issue proposes to fill is still open.

**Freshest schema-migration test shape**: `TestSchemaV28`
(`test_session_store.py`, ~line 5136) is the canonical 3-test pattern every
recent schema version follows — `test_<table>_columns` (PRAGMA table_info
column-set assertion), `test_v<N-1>_db_upgrades_gains_<table>` (bootstrap at
prior version, `ensure_db`, assert table exists), `test_<kind>_is_kinded`
(`VALID_KINDS`/`_KIND_TABLE` assertions). Model the new hook_events schema
test class on this shape. Separately, `test_enh_2505_subagent_runs.py` (341
lines) shows a standalone-test-file organization (one file per feature,
covering lifecycle + hook-handler + backfill classes) as an alternative to
spreading all new tests across `test_session_store.py` — worth considering
given how large this issue's already-planned test surface is.

---

## Resolution

Added `hook_events` table (v30 migration, `session_store.py`) plus
`record_hook_event()`/`hook_event_context()` (best-effort, modeled on
`skill_event_context`). Rather than wrapping 12+ individual handler files,
wrapped the single `handler(event)` call site inside `main_hooks()`
(`hooks/__init__.py`) — per this issue's own Staleness Update finding that
this is the one point every Python-dispatched intent funnels through, gated
on `analytics.enabled` + new `analytics.capture.hooks` (default `true`,
plumbed through `AnalyticsCaptureConfig`/`init/core.py`/`config-schema.json`).
`Stop`/`SessionEnd` are bash-only and never reach `main_hooks()`, so added
`hooks/scripts/record-hook-event.sh` as a second `hooks.json` command
(Option A) calling the new `ll-session record-hook-event` subcommand — fixed
a jq gotcha along the way (`false // true` evaluates `true` in jq; switched
to explicit `== true`/`== false` comparisons). Added read API
(`recent_hook_events`, `hook_failure_rate`, `hook_latency_p95` in
`history_reader.py`) and `ll-session recent --kind hook_event` (works for
free via the existing `VALID_KINDS`-driven `--kind` choices). Confirmed no
`HookEventVariant` DES registration was needed — `ll-verify-des-audit` passed
clean, matching this issue's own Scope Boundary note that direct-DB writers
outside `event_bus.emit()` aren't covered by the Phase 1 regex. Skipped the
optional `hook-health` CLI rollup subcommand (explicitly called out as a
follow-on in the issue). Full test suite: 15,836 passed, 38 skipped;
`ruff check`, `ruff format --check` (this issue's files), `mypy`,
`ll-verify-kinds`, and `ll-verify-des-audit` all clean.

## Session Log
- `/ll:manage-issue` - 2026-07-22T18:36:31Z - `8c7602a2-c2de-4699-ab9c-c9bd1d332cdd.jsonl`
- `/ll:ready-issue` - 2026-07-22T17:57:14 - `3d09890c-6c55-4647-b3d3-5416dc9bef98.jsonl`
- `/ll:decide-issue` - 2026-07-22T17:53:21 - `4dbf04e5-8049-4292-9d13-7edefc42830c.jsonl`
- `/ll:refine-issue` - 2026-07-22T17:51:18 - `07d392c0-4fca-4549-b6ff-9aec46809803.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-17T18:49:45 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-17T18:48:50 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-17T14:03:02 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-17T14:01:04 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:wire-issue` - 2026-07-17T00:45:19 - `36e8e2d1-f879-4f12-a41b-ffd3a462d36b.jsonl`
- `/ll:refine-issue` - 2026-07-16T16:16:11 - `a12fca84-5e71-48ec-aff1-8ea85e8c0067.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:55 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`