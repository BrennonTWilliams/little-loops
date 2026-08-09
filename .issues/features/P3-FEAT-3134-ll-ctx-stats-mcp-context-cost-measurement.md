---
id: 3134
title: 'll-ctx-stats: measure ll-mcp context cost via ttlMs/cacheScope'
type: FEAT
priority: P3
status: deferred
discovered_date: '2026-08-09'
labels:
- multi-host
- mcp
parent: EPIC-3127
depends_on:
- FEAT-3135
- FEAT-3136
- FEAT-3137
relates_to:
- FEAT-3128
verify_verdict: VALID
reconcile_attempted: true
confidence_score: 60
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
size: Very Large
deferred_by: automation
deferred_date: '2026-08-09T11:38:11Z'
deferred_reason: readiness_stagnated
---

# FEAT-3134: ll-ctx-stats: measure ll-mcp context cost via ttlMs/cacheScope

## Summary

`ll-ctx-stats` learns to measure the `ll-mcp` surface's context cost from
the protocol-level `ttlMs`/`cacheScope` fields the `ll-mcp` server's
responses carry (emitted by FEAT-3135/FEAT-3136/FEAT-3137), rather than
re-measuring transport bytes. This directly answers the
context-cost open question for the prompts-from-skills list: the host
prompt cache can reuse list responses per the declared TTL.

This issue depends on FEAT-3135, FEAT-3136, and FEAT-3137 shipping first — it
consumes the `ttlMs`/`cacheScope` fields those surface issues emit on
`tools/list` (FEAT-3135), `resources/list`/`resources/read` (FEAT-3136), and
`prompts/list` (FEAT-3137). The original blocker, FEAT-3132, was decomposed
into these three issues (`Resolution: Decomposed`, 2026-08-09) without
shipping any of this surface itself — `depends_on` has been corrected to
point at the issues that actually carry the work; FEAT-3135 is `Deferred`,
FEAT-3136 and FEAT-3137 are `Open` as of this refinement pass.

## Parent Issue

Decomposed from FEAT-3128: ll-mcp: read-only server (queries, resources,
prompts-from-skills from skills). Split out from the core server (originally
FEAT-3132, since decomposed into FEAT-3135/FEAT-3136/FEAT-3137) because
context-cost measurement is a separately testable subsystem
(`cli/ctx_stats.py`'s aggregation path) that consumes the server's protocol
responses rather than being part of the server.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

### Conventions in Force (from codebase-pattern-finder)

- **`_aggregate_*()` shape**: every aggregator in `cli/ctx_stats.py` (`_aggregate_tool_events`, `_aggregate_mcp_health`, `_aggregate_waste`, `_aggregate_usage_events`, `_aggregate_context_pressure`) takes a single `db_path: Path` argument and opens with the identical `if not db_path.exists(): return None` guard, each docstring cross-referencing the sibling it mirrors — evidence: `cli/ctx_stats.py:169` (`_aggregate_mcp_health`), `:183` (`_aggregate_waste`).
- **Two implementation shapes coexist among the aggregators, not one**: `_aggregate_mcp_health`/`_aggregate_waste` are thin delegators (local `from little_loops.history_reader import <fn>` then `return <fn>(db=db_path)`, no SQL of their own — `cli/ctx_stats.py:169-180`); `_aggregate_tool_events`/`_aggregate_usage_events`/`_aggregate_context_pressure` run raw `sqlite3.connect`/`SELECT` directly with `try/finally: conn.close()`. This is a contested convention, not a single rule — an implementer choosing between them is a real decision, not dictated by the codebase.
- **Composition**: `main_ctx_stats()` (`cli/ctx_stats.py:726-790`) calls every aggregator unconditionally near the top, threading each result as a trailing positional into both `_render()` and `_print_json()`. `_render()` guards each section with `if <name>:` (truthy — `None` and `[]` both skip) except `_aggregate_context_pressure`'s render, which adds an extra key check (`if pressure and pressure["samples"]:`) — evidence this guard shape is not fully uniform either.
- **`history_reader.py` query-function shape**: optional positional filters, then bare `*`, then keyword-only `since`, then keyword-only `db=DEFAULT_DB_PATH` last; body opens a readonly connection via `_connect_readonly`, returns `[]` on `None`/`sqlite3.Error` (module docstring's stated contract: "missing/empty/corrupt databases return empty lists, never raise") — evidence: `mcp_server_usage` (`history_reader.py:796-843`), `mcp_failure_rate` (`:846-894`).
- **Schema migrations**: new columns added via `ALTER TABLE ... ADD COLUMN` as nullable, paired with `CREATE INDEX IF NOT EXISTS` on columns expected to be filtered/grouped — evidence: v25 (`schema.py:581-593`, ENH-2511, docs row at `docs/ARCHITECTURE.md:689`). Note: this convention is not consistently honored by the three most recent migrations (`schema.py:906-961`), which have no corresponding `docs/ARCHITECTURE.md` row — evidence of drift, not an instruction to skip the row here.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_mcp_health()` (line
  169) currently derives MCP health from `tool_events` byte/latency columns
  via `history_reader.mcp_server_usage()`, not protocol `ttlMs`/
  `cacheScope`; no `ttl_ms`/`cache_scope` columns exist in that schema yet —
  a parallel aggregation path is needed
- `scripts/little_loops/session_store/schema.py` — `SCHEMA_VERSION = 39`
  (line 21) must bump to `40` if a new `ALTER TABLE tool_events ADD COLUMN
  ttl_ms/cache_scope` migration is appended to `_MIGRATIONS`
  [wire-issue finding]
- `scripts/little_loops/hooks/post_tool_use.py` (lines 160-213) — the live
  writer that parses `mcp_server`/`mcp_tool`/`mcp_outcome`/`latency_ms` from
  the tool-call payload and builds the `INSERT INTO tool_events(...)`
  statement; if `ttl_ms`/`cache_scope` are populated at write time (rather
  than backfilled), this is where the parse + column-list + bind-params
  addition goes [wire-issue finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/writers.py` — `_backfill_tool_events()`
  (line 2425); if `ttl_ms`/`cache_scope` are retroactively derivable (like
  `mcp_server`/`mcp_tool`, not live-write-only like `latency_ms`), this
  backfill path needs a matching column population [Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py` (line 958) — calls
  `_backfill_tool_events()`; only relevant if the backfill path above is
  touched [Agent 1 finding]

### Tests
- `scripts/tests/test_cli_ctx_stats.py` — precedent for testing a CLI
  module's internals directly; model the new aggregator's unit-test class on
  `TestAggregateWaste` (lines 535-567, same thin-delegation shape as the
  planned function) and its CLI-level test class on
  `TestMainCtxStatsWasteSection` (lines 570-645) [Agent 3 finding]
- `scripts/tests/test_enh_2511_mcp_telemetry.py` — existing coverage of
  `mcp_server_usage()`'s current byte/latency-only shape (`mcp_server,
  invocations, completions, successes, avg_latency_ms`); the new
  ttlMs/cacheScope aggregation path must coexist with this shape unchanged,
  not replace it. Its `_bootstrap_schema_at(db, version)` helper (lines
  25-37) replays `_MIGRATIONS[:version]` and is the precedent for testing
  the new migration additively [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_schema.py` — ~17 lines hardcode
  `SCHEMA_VERSION == 39` (e.g. lines 650, 664, 716, 812, 1034, 1075, 1413,
  1453, 1497, 1547, 1622, 1682, 1750, 1815, 1883, 1928, 1983); every one
  must update to `== 40` if the migration is added [Agent 3 finding,
  confirmed by grep — 24 total `== 39` occurrences in this file]
- `scripts/tests/test_session_store_writers.py` — hardcodes
  `SCHEMA_VERSION == 39` at lines 470, 1153, 1455, 1653 (plus `int(row[0])
  == 39` at 471); must update to `40` [Agent 3 finding, grep-confirmed]
- `scripts/tests/test_assistant_messages.py:88` — hardcodes
  `SCHEMA_VERSION == 39`; must update to `40` [Agent 3 finding,
  grep-confirmed]
- `scripts/tests/test_hook_post_tool_use.py` — tests `tool_events`
  population (`cache_hit`, `bytes_in`, `bytes_out`, `latency_ms` fields);
  needs new assertions if `post_tool_use.py`'s INSERT gains `ttl_ms`/
  `cache_scope` [Agent 1 finding]
- `scripts/tests/test_session_store_writers.py` — also covers
  `_backfill_tool_events()`; needs new coverage if the backfill path is
  touched [Agent 1 finding]

### Documentation
- `docs/ARCHITECTURE.md` — schema-migration table needs a new row
  (following the v25 `tool_events.mcp_server`/`mcp_tool`/`mcp_outcome`/
  `latency_ms` row pattern) if new `ttl_ms`/`cache_scope` columns are added
  to `tool_events`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### main_ctx_stats` (line 4576) already omits
  `mcp_health` from its `--json` key enumeration (pre-existing gap); a new
  ttl/cache-scope key lands in the same doc block and should be added
  alongside a fix for the `mcp_health` omission. `### mcp_server_usage`
  (line 7810) is the format precedent if a sibling `history_reader` reader
  function is added — insert a matching `###` entry near it (lines
  7810-7835) [Agent 2 finding]
- `docs/reference/CLI.md` — `### ll-ctx-stats` section (lines 289-312) also
  omits `mcp_health` from its documented JSON keys (pre-existing gap); needs
  a new bullet under **Flags** (298-299) and a human-readable-section
  call-out (pattern: "Waste" at line 295, "Context pressure curve" at line
  301) for the new key [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:560` — only if `ttl_ms`/`cache_scope`
  capture is gated by a *new* `analytics.capture.*` flag rather than reusing
  an existing one; this table would need a new row [Agent 2 finding,
  conditional]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `scripts/little_loops/cli/ctx_stats.py:169-180` — `_aggregate_mcp_health(db_path: Path) -> list[dict[str, Any]] | None` is a thin delegator: guards on `db_path.exists()` (returns `None` if absent, mirroring `_aggregate_tool_events`'s contract), then locally imports and returns `history_reader.mcp_server_usage(db=db_path)` directly — no transformation logic of its own.
- `scripts/little_loops/history_reader.py:796-843` — `mcp_server_usage(server: str | None = None, *, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> list[dict]` reads only `mcp_server`, `mcp_outcome`, `latency_ms` from `tool_events` (plus `ts` for the optional `since` filter); returns `[]` on missing/corrupt DB or query failure (never raises), logging via `logger.warning("history_reader: mcp_server_usage query failed", exc_info=True)`.
- `scripts/little_loops/cli/ctx_stats.py:726,749,754,777-779` — `main_ctx_stats()` calls `_aggregate_mcp_health(db_path)` once at line 749, threading the result into both `_print_json()` (JSON payload key `"mcp_health"`, always present even when `None`) and `_render()` (text mode, guarded by a plain `if mcp_health:` truthy check at lines 492-505 — no explicit "no data" message when falsy, unlike the `skill_stats` branch).
- `scripts/little_loops/session_store/schema.py:107` (`_MIGRATIONS`) — no `ttl_ms`/`cache_scope` columns exist anywhere in the migration list today (confirmed via repo-wide grep; only issue markdown and `.ll/learning-tests/mcp.md` mention these terms). The v25 entry (lines 581-593, ENH-2511) is the precedent for adding new nullable `tool_events` columns via `ALTER TABLE ... ADD COLUMN`, paired with a `CREATE INDEX IF NOT EXISTS` on columns expected to be filtered/grouped on.
- `docs/ARCHITECTURE.md:663-701` — schema-migration table; the v25 row (line 689) is the exact format precedent: `| vNN | <backtick-quoted column/index list> | <prose: meaning, live-vs-backfill provenance, nullability, what it enables, closing with issue ID> |`. Note: the three most recent migrations (schema.py:906-961, ENH-2814/ENH-141) dropped the `vNN` comment prefix and have no corresponding table row — the convention of "every migration gets a docs row" is not consistently honored in current code.
- No server-side MCP implementation exists yet in this codebase — `ll-mcp` has no console entry point in `pyproject.toml` and no `scripts/little_loops/` module. Existing MCP code (`mcp_call.py`, `runner_spec.py:_run_mcp`, `cli/harness.py:cmd_mcp`) is exclusively a client that talks to *external* MCP servers, not evidence of a protocol capture path for a server this codebase would run.
- Test pattern precedent (`scripts/tests/test_cli_ctx_stats.py`): one `TestAggregateX` class per aggregator, minimum 3 tests (`test_missing_db_returns_none`, an absent-table/legacy-DB case returning `None`, an empty-vs-populated data case), paired with a `TestMainCtxStatsXSection` class exercising the full CLI (both text output via `capsys` substring checks and `--json` mode via `json.loads`). A new ttlMs/cacheScope aggregation path would follow this same paired-class shape for consistency, though this is a convention observed, not a requirement enforced by any gate.
- `scripts/tests/test_enh_2511_mcp_telemetry.py`'s `_bootstrap_schema_at(db, version)` helper (lines 25-37) replays `_MIGRATIONS[:version]` directly to simulate a pre-migration DB, then asserts `ensure_db(db)` reaches `SCHEMA_VERSION` with old rows intact and new columns `NULL` — the established precedent for testing an additive schema migration in place.

## Program Design

### Types
- `tool_events` table (`session_store/schema.py:107` `_MIGRATIONS`) currently has no `ttl_ms`/`cache_scope` columns. The v25 precedent (lines 581-593) is nullable `INTEGER`/`TEXT` columns added via `ALTER TABLE ... ADD COLUMN`, each paired with a `CREATE INDEX IF NOT EXISTS` when the column is expected to be filtered/grouped on.

### Signatures
- `_aggregate_mcp_health(db_path: Path) -> list[dict[str, Any]] | None`
- `mcp_server_usage(server: str | None = None, *, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> list[dict]`

Existing signatures, verbatim from `cli/ctx_stats.py:169` and `history_reader.py:796` — a sibling
`_aggregate_*` function for ttlMs/cacheScope would take the same single `db_path: Path` argument
and follow this file's established three-state return contract (`None` = DB missing, `[]` = DB
exists with no rows, non-empty = data); a sibling `history_reader.py` reader function would follow
`mcp_server_usage`'s parameter-ordering shape (optional positional filters, then keyword-only
`since`, then keyword-only `db` last).

### Call Path
`main_ctx_stats()` (`cli/ctx_stats.py:726`) → currently `_aggregate_mcp_health()`
(`cli/ctx_stats.py:169`) wraps `history_reader.mcp_server_usage()`, sourced from `tool_events`
byte/latency columns (no `ttl_ms`/`cache_scope` columns exist in that schema yet) → a parallel
aggregation path is needed once the server surface emits those protocol fields, either a new
`history_reader.py` reader function (mirrors `mcp_server_usage`'s shape) or direct SQL against
new `tool_events.ttl_ms`/`tool_events.cache_scope` columns (mirrors the v25 migration pattern,
`schema.py:581-593`) → threaded into both `_render()` (text mode, new truthy-guarded section,
`cli/ctx_stats.py:492-505` pattern) and `_print_json()` (JSON payload key, `cli/ctx_stats.py:604`
pattern).

### Decision Rules
N/A — no new decision logic

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **Error-handling contract, exact anchors** (codebase-analyzer, confirms the existing "returns `[]`/`None`, never raises" contract already cited above at the anchor level): `_connect_readonly()` (`history_reader.py:420-434`) has two `sqlite3.Error` catches — `ensure_db()` failure (`:422-426`, returns `None`) and read-only connect failure (`:427-433`, returns `None`) — both logging via `logger.warning(..., exc_info=True)`. `mcp_server_usage()`'s own query-failure catch is at `:823-828`. A sibling ttlMs/cacheScope aggregator or reader function inherits this contract by construction if it reuses `_connect_readonly()`.
- **Base `tool_events` columns, confirmed** (codebase-analyzer): the table's original `CREATE TABLE IF NOT EXISTS tool_events` (`session_store/schema.py:109-119`) has no `mcp_server`/`mcp_outcome`/`latency_ms`/`ttl_ms`/`cache_scope` columns — those were all added later via `ALTER TABLE` migrations (v25 at `:581-593` adds `mcp_server`/`mcp_tool`/`mcp_outcome`/`latency_ms`). Confirms the v25 additive-migration precedent applies cleanly to a further `ttl_ms`/`cache_scope` addition.
- **Repo-wide confirmation this is greenfield** (codebase-analyzer): a repo-wide grep for `ttlMs`/`cacheScope`/`ttl_ms`/`cache_scope` matches only issue markdown (FEAT-3134/3135/3136/3137, EPIC-3127, FEAT-3128) and `.ll/learning-tests/mcp.md` — zero Python/test/schema code. No branch or file for the three blocking sibling issues (FEAT-3135/3136/3137) exists yet in this checkout.

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- **codebase-analyzer confirmation (independent pass)**: verifies the greenfield/additive findings above at the anchor level — `_aggregate_mcp_health()` (`cli/ctx_stats.py:169-180`) and `mcp_server_usage()` (`history_reader.py:796-843`) are unchanged by this issue; a new ttlMs/cacheScope aggregation path is purely additive (new `_aggregate_*` function, new `history_reader` reader or direct SQL, new threaded argument into `_render()`/`_print_json()`). No existing schema column, table, or code path anywhere in this repo carries `ttl_ms`/`cache_scope`-shaped data today — the only MCP code present is the client (`mcp_call.py`), not a server.
- **Why Implementation Step 1 stays a decision, not a finding**: "new columns vs. derive from existing data" cannot be resolved by this codebase alone — it depends on the actual wire shape FEAT-3135/FEAT-3136/FEAT-3137 emit for `ttlMs`/`cacheScope` on their respective protocol responses, and none of those three issues has shipped code yet (FEAT-3135 Deferred, FEAT-3136/FEAT-3137 Open). There are not two concrete, codebase-groundable options to choose between yet; this is a blocked decision, not an under-researched one.

## Implementation Steps

1. Decide whether `ttlMs`/`cacheScope` telemetry needs new `tool_events`
   columns or can be derived from existing captured data; if new columns
   are added, record the schema-migration row in `docs/ARCHITECTURE.md`.
2. Add the parallel aggregation path in `cli/ctx_stats.py` that reports
   `ttlMs`/`cacheScope`-derived context cost, alongside (not replacing)
   `_aggregate_mcp_health()`'s existing byte/latency-only shape.
3. `python -m pytest scripts/tests/` passes, including
   `test_enh_2511_mcp_telemetry.py` unchanged and new coverage for the
   ttlMs/cacheScope path.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- If a new `tool_events.ttl_ms`/`tool_events.cache_scope` migration is added,
  bump `SCHEMA_VERSION` (`session_store/schema.py:21`) from `39` to `40` and
  update every hardcoded `== 39` assertion in `test_session_store_schema.py`
  (~24 occurrences), `test_session_store_writers.py` (4 occurrences), and
  `test_assistant_messages.py:88`
- If the new columns are populated at write time, add the parse + INSERT
  column/bind-param logic to `hooks/post_tool_use.py` (lines 160-213,
  alongside the existing `mcp_server`/`mcp_outcome`/`latency_ms` parsing)
  and extend `test_hook_post_tool_use.py`
- If the new columns are retroactively derivable (not live-write-only), add
  population logic to `_backfill_tool_events()`
  (`session_store/writers.py:2425`) and extend its test coverage
- Update `docs/reference/API.md`'s `### main_ctx_stats` (line 4576) and add
  a sibling `###` entry near `### mcp_server_usage` (line 7810) if a new
  `history_reader` reader function is added
- Update `docs/reference/CLI.md`'s `### ll-ctx-stats` section (lines
  289-312) with the new JSON key and human-readable section

## Acceptance criteria

- `ll-ctx-stats` reports the MCP surface's context cost, consuming the
  protocol's `ttlMs` / `cacheScope` fields rather than measuring transport
  bytes.
- `mcp_server_usage()`'s existing byte/latency-only shape is unchanged
  (`test_enh_2511_mcp_telemetry.py` continues to pass).


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-09_

**Readiness Score**: 60/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 71/100 → MODERATE

### Gaps to Address
- Dependencies unresolved: `depends_on` lists FEAT-3135 (Deferred), FEAT-3136 (Open), FEAT-3137 (Open) — none is done/cancelled. A repo-wide grep confirms zero code exists yet for `ttlMs`/`cacheScope` outside issue markdown; this issue cannot be implemented until at least the server surface it consumes ships.
- Core design decision left open: Implementation Step 1 is literally "Decide whether ttlMs/cacheScope telemetry needs new tool_events columns or can be derived from existing captured data" — this can't be resolved concretely until FEAT-3135/3136/3137 define the actual wire shape of those fields.
- Standard FEAT template sections are missing per `ll-issues format-check` (Acceptance Criteria header casing aside, `Current Behavior`, `Expected Behavior`, `Impact`, `Use Case` are absent) — low-cost fix via `/ll:format-issue`.

### Escalation
- **Unresolved options (score_ambiguity = 10)**: Run `/ll:decide-issue FEAT-3134` — the columns-vs-derive question is a real open option, not just a research gap.

## Session Log
- `/ll:confidence-check` - 2026-08-09T11:37:34 - `9b845dee-97c0-40e4-9daa-158134eac1ae.jsonl`
- `/ll:reconcile-issue` - 2026-08-09T11:36:05 - `6b2102e4-402e-43f5-9688-033a6e49e0c0.jsonl`
- `/ll:confidence-check` - 2026-08-09T11:33:58 - `c223943f-d6ec-49ee-b72b-eb314417b98c.jsonl`
- `/ll:decide-issue` - 2026-08-09T11:32:25 - `cd0a9e71-2638-49e3-90ba-22b00177561f.jsonl`
- `/ll:refine-issue` - 2026-08-09T11:31:39 - `cd0a9e71-2638-49e3-90ba-22b00177561f.jsonl`
- `/ll:confidence-check` - 2026-08-09T11:26:32 - `5d5314ea-f28b-4aed-8f83-cf3948459cb4.jsonl`
- `/ll:verify-issues` - 2026-08-09T11:23:46 - `34a4f599-ff50-454d-ab32-41ef57f07b39.jsonl`
- `/ll:refine-issue` - 2026-08-09T11:20:28 - `727f393e-e11b-45ea-b294-48deb90e19f5.jsonl`
- `/ll:verify-issues` - 2026-08-09T11:15:44 - `2734c313-be28-4e73-b50f-6039cbac4b37.jsonl`
- `/ll:wire-issue` - 2026-08-09T11:13:13 - `35dc9043-2215-4fe0-9870-047a572fd5ab.jsonl`
- `/ll:refine-issue` - 2026-08-09T11:04:29 - `0309a621-b6e2-48e6-9686-7106737cf9ba.jsonl`
- `/ll:issue-size-review` - 2026-08-09T06:59:30 - `1a2b4d88-27a6-4756-bc3a-7bce0e10a356.jsonl`
