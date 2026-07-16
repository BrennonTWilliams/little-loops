---
id: ENH-2511
title: Capture MCP tool-call telemetry in tool_events
type: ENH
priority: P3
status: open
discovered_date: 2026-07-06
captured_at: "2026-07-06T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
depends_on: [ENH-2497]
labels:
  - enhancement
  - history-db
  - mcp
  - widening
  - captured
---

# ENH-2511: Capture MCP tool-call telemetry in tool_events

## Summary

Every MCP server call (e.g., `mcp__pencil__batch_design`,
`mcp__zai-mcp-server__analyze_image`) produces a tool invocation with
its own server/tool/outcome semantics — but the live `tool_events`
write records it as `tool_name="mcp__pencil__batch_design"` (the full
prefixed name), with no clean breakdown of `server` vs. `tool`, no
`outcome_class` (`success` | `error` | `timeout`), and no `args` /
`result_size` / `latency_ms`. So "how often does pencil fail" or "which
MCP server burns the most tool_events rows" can't be answered without
string parsing the tool_name. Add three nullable columns to
`tool_events` — `mcp_server`, `mcp_tool`, `mcp_outcome` — and widen
ENH-2497's migration so the same v19 migration carries both changes.
Overlaps ENH-2497 explicitly noted in the user's gap list.

## Motivation

- **MCP calls are first-class tool uses but second-class in tool_events.**
  The full `mcp__pencil__batch_design` name lives in `tool_name`, but
  the server/tool breakdown requires string parsing. A column for each
  is one ALTER TABLE away.
- **Outcome classification is missing.** `tool_events` has
  `bytes_out` (proxy for response size) but no
  `success`/`error`/`timeout` discriminator. The `tool_response`
  payload carries the outcome (MCP results return `{isError: true}` or
  the equivalent), but it's not extracted.
- **Latency_ms is missing.** Other event tables (test_run_events at
  v18, commit_events at v17) carry `duration_ms`; tool_events has
  `bytes_in/out` and `cache_hit` but not elapsed time. Adding
  `latency_ms` to `tool_events` is the natural symmetry.
- **Widens ENH-2497 rather than spawning a new table.** ENH-2497 adds
  `agent_type` to `tool_events` (also nullable, same migration target
  v19). Adding `mcp_server`, `mcp_tool`, `mcp_outcome`, `latency_ms`
  to the same migration is one version bump, multiple additive
  columns. Same pattern ENH-2498 used to widen ENH-2494.

## Current Behavior

- A `mcp__pencil__batch_design` call writes a `tool_events` row with
  `tool_name="mcp__pencil__batch_design"` (full prefixed string) and
  the usual byte accounting. No server/tool breakdown, no outcome
  discriminator.
- `_backfill_tool_events` (`session_store.py:1620-1664`) extracts
  `subagent_type` from Task calls (after ENH-2497) but not MCP
  breakdown.
- There is no way to ask `SELECT COUNT(*) FROM tool_events WHERE
  mcp_server='pencil' AND mcp_outcome='error'` — the columns don't
  exist.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Stale anchors in this section:**
- `_backfill_tool_events` is at `scripts/little_loops/session_store.py:1836-1875` (not `:1620-1664` as cited above)
- `scripts/little_loops/hooks/post_tool_use.py:163-177` is approximately correct (the current 8-column INSERT block sits there)
- `SCHEMA_VERSION` is **20** at `scripts/little_loops/session_store.py:207` — not 18 as the issue text's "Schema migration (v19, batched with ENH-2497)" subsection implies. v17=`commit_events` (ENH-2458), v18=`test_run_events` (ENH-2459), v19=`raw_events` (ENH-2581), v20=`usage_events` (ENH-2461) are already taken. The next migration slot is **v21**, which is where the batched `agent_type` + `mcp_*` ALTERs land.

**Confirmed current behavior (anchor-level):**
- `tool_events` is registered as `kind="tool"` in `_KIND_TABLE` at `session_store.py:210-235`; the `recent()` helper at `:1462-1484` does `SELECT * FROM {table} ORDER BY id DESC LIMIT ?`, so the four new columns flow through to CLI / history_reader output automatically — no render-path change needed.
- `tool_events` has **zero indexes** today (no `CREATE INDEX … ON tool_events` anywhere in `_MIGRATIONS`); the proposed `idx_tool_events_mcp_server` / `idx_tool_events_mcp_outcome` are greenfield additions.
- `ll-verify-kinds` invariant unaffected — adding columns to an existing `tool_events` table does not require `_KIND_TABLE` / `_KINDLESS_TABLES` registration.
- Live `post_tool_use.handle()` does **not** call `_index()` after its INSERT (only `_backfill_tool_events` does at `session_store.py:1866-1873`). FTS coverage of MCP rows via `ll-session search --fts "pencil"` therefore depends on the backfill path having run — the same asymmetry flagged in ENH-2497. Consider extending `_index()`'s `content` arg to `f"{tool_name} {mcp_server or ''}".strip()` once ENH-2497's `_index()` widening lands.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store.py:207` — `SCHEMA_VERSION` constant (bump 20 → 21, batched with ENH-2497's `agent_type` column per the Scope Boundary note)
- `scripts/little_loops/session_store.py:709-734` — `_MIGRATIONS` list; append v21 entry co-locating `agent_type` + `mcp_server` + `mcp_tool` + `mcp_outcome` + `latency_ms` (single migration block, comment line naming both ENH-2497 and ENH-2511 for grep-ability, matching the v15/v16/v17 precedent comments)
- `scripts/little_loops/session_store.py:1836-1875` — `_backfill_tool_events()`; add `mcp__<server>__<tool>` regex parser before the INSERT; populate `mcp_server` / `mcp_tool` only (see Codebase Research Findings under Proposed Solution — `mcp_outcome` and `latency_ms` cannot be backfilled from JSONL today)
- `scripts/little_loops/hooks/post_tool_use.py:151-180` — `handle()` live write; extend the INSERT to include the four new columns and add MCP parsing / outcome / latency extraction inside the existing `contextlib.suppress(Exception)` block (lines 158-180)
- `scripts/little_loops/history_reader.py:106-162` — add `ToolEvent` dataclass with `mcp_server: str | None = None`, `mcp_tool: str | None = None`, `mcp_outcome: str | None = None`, `latency_ms: int | None = None` (mirrors `SkillEvent` at `:106-121`; `_row_to_dataclass()` at `:273-277` is column-tolerant so pre-migration rows still construct)
- `scripts/little_loops/history_reader.py` (near `:466-546`) — add `recent_tool_events(mcp_server=None, mcp_tool=None, mcp_outcome=None, *, limit=20, db=DEFAULT_DB_PATH)` mirroring `recent_skill_events()` shape at `:466-494`
- `scripts/little_loops/history_reader.py` (near `:497-546`) — add `mcp_server_usage(server=None, *, since=None, db=DEFAULT_DB_PATH)` and `mcp_failure_rate(server=None, tool=None, *, since=None, db=DEFAULT_DB_PATH)` helpers mirroring `summarize_skills()` (use `_connect_readonly()` at `:256-270` for read-only access)
- `scripts/little_loops/cli/session.py:112-130` — extend `recent_parser` with `--mcp-server NAME`, `--mcp-tool NAME`, `--mcp-outcome {success,error,timeout}` optional filters (matches the existing `--issue` filter pattern at `:430-447`)
- `scripts/little_loops/cli/session.py:430-461` — extend the `recent` dispatch to push MCP filters into the SQL when `--kind tool` plus any MCP flag is set (mirror the `--issue` branch at `:434-447`)
- `scripts/little_loops/cli/ctx_stats.py:118-166` — `_aggregate_tool_events()`; add sibling "MCP server health" block (per-server success/latency rollup)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/backfill_worker.py` — invokes `_backfill_tool_events` during backfill dispatch (called from `session_store.py:2882`); will produce `mcp_server` / `mcp_tool` rows on rebuilt DBs
- `scripts/little_loops/hooks/__init__.py:74-99` — intent dispatch table; no change needed (post_tool_use is already wired)
- `scripts/little_loops/hooks/adapters/claude-code/post-tool-use.sh:1-13` — Claude Code stdin shim; no change needed (passes the raw payload through)
- `scripts/little_loops/observability/schema.py` — observability schema definitions; verify if `tool_events` is referenced and add v21 row if so
- `docs/ARCHITECTURE.md:655-679` — schema versions table; add v21 row documenting the ENH-2497 + ENH-2511 batched migration

### Similar Patterns

- `scripts/little_loops/adapters/codex.py:188-204` — `_derive_mcp_servers()` uses `str.split("__")` to extract server from `mcp__<server>__<tool>`; an alternate in-tree parser precedent. Produces identical results to the regex `^mcp__(.+?)__(.+)$` specified in the issue for valid `mcp__<server>__<tool>` names (verified by trace for `mcp__zai-mcp-server__analyze_image`).
- `scripts/little_loops/session_store.py:580-584` — v15 migration (ENH-2460) precedent for nullable-column-add migrations on `skill_events`; the comment-block + multi-statement-string shape is the template to follow for the v21 entry.
- `scripts/little_loops/fsm/evaluators.py:962-1019` — `evaluate_mcp_result()` is the canonical MCP envelope `isError` / `exit_code` → verdict mapping; its `envelope.get("isError", exit_code != 0)` at `:1008` is the canonical `isError` read.
- `scripts/little_loops/mcp_call.py:296` — `is_error = result.get("isError", False)` is the canonical MCP-result-extractor read for non-PostToolUse paths.
- `scripts/little_loops/history_reader.py:497-546` — `summarize_skills()` precedent for per-group aggregation with success-rate and `AVG(duration_ms)` computation; `mcp_server_usage` / `mcp_failure_rate` should mirror its `_connect_readonly()` + `try/except sqlite3.Error → []` shape.
- `scripts/little_loops/history_reader.py:466-494` — `recent_skill_events(skill_name=None, *, limit=20)` is the precedent for `recent_tool_events(mcp_server=None, mcp_tool=None, mcp_outcome=None, *, limit=20)` (filter stacking via `WHERE … AND`).

### Tests

- `scripts/tests/test_session_store.py:3891-3911` — `_bootstrap_schema_at(version)` helper; reusable for the v21 migration test
- `scripts/tests/test_session_store.py:3914-3966` — `TestSchemaV15SkillCompletionColumns` three-test template (column-existence via PRAGMA, pre-migration row preservation, dispatch-only NULL handling) — model for `TestSchemaV21ToolMcpTelemetry`
- `scripts/tests/test_hook_post_tool_use.py:100-132` — `TestPostToolUseWithSessionStore.test_writes_row_when_analytics_enabled` template for live MCP write tests (success / error / timeout outcomes, non-MCP NULL handling, malformed-payload NULL handling)
- `scripts/tests/test_history_reader.py:1415-1436` — `test_summarize_skills_success_rate` template for `mcp_server_usage` / `mcp_failure_rate` aggregation tests
- `scripts/tests/test_history_reader.py:1530-1545` — `test_readers_return_empty_on_missing_db` template for graceful-degradation tests of new history_reader helpers
- `scripts/tests/test_session_store.py` (post-v20 location) — add `TestBackfillToolEventsMcpColumns` covering JSONL backfill populating `mcp_server` / `mcp_tool` from assistant `tool_use` blocks

### Documentation

- `docs/ARCHITECTURE.md:655-679` — schema versions table; add v21 row
- `docs/reference/API.md` — document new `tool_events` columns and `mcp_server_usage` / `mcp_failure_rate` / `recent_tool_events` helpers
- `docs/reference/CLI.md` — document new `ll-session recent --mcp-server` / `--mcp-tool` / `--mcp-outcome` flags
- `docs/claude-code/hooks-reference.md:901-929` — referenced (but does not currently expose `tool_call.started_at` / `tool_call.completed_at`); note this limitation in the Producer wiring Codebase Research Findings

### Configuration

- No new config keys; the entire change rides the existing `analytics.enabled` gate at `post_tool_use.py:151`. No `ll-config.json` schema additions required.

## Expected Behavior

- `tool_events` gains four nullable columns: `mcp_server TEXT`,
  `mcp_tool TEXT`, `mcp_outcome TEXT` (`success` | `error` |
  `timeout`), and `latency_ms INTEGER` (elapsed time of the MCP /
  tool call).
- The live `post_tool_use` write at `post_tool_use.py:163-177`
  extracts `server` and `tool` from the `mcp__<server>__<tool>` prefix
  when present, and reads `tool_response.isError` (or the
  MCP-shape equivalent) for `outcome`.
- `latency_ms` is computed from the tool-call wallclock — available
  from the Claude Code host via `tool_call.started_at` /
  `tool_call.completed_at`, or measured by the hook handler with
  `time.monotonic()` around the dispatch.
- Non-MCP tool calls leave the new columns NULL.
- `ll-session recent --kind tool --server pencil --outcome error` (or
  equivalent filter via the existing `--kind tool` plus new flags)
  returns the MCP failure subset.

## Proposed Solution

### Schema migration (v19, batched with ENH-2497)

```sql
ALTER TABLE tool_events ADD COLUMN mcp_server TEXT;
ALTER TABLE tool_events ADD COLUMN mcp_tool TEXT;
ALTER TABLE tool_events ADD COLUMN mcp_outcome TEXT;
ALTER TABLE tool_events ADD COLUMN latency_ms INTEGER;
CREATE INDEX IF NOT EXISTS idx_tool_events_mcp_server ON tool_events(mcp_server);
CREATE INDEX IF NOT EXISTS idx_tool_events_mcp_outcome ON tool_events(mcp_outcome);
```

Bump `SCHEMA_VERSION = 18` → `19`. Coordinate with ENH-2497's
`agent_type` column (also a `tool_events` ALTER) — single migration
batch. Pre-migration rows read back with `mcp_server=NULL,
mcp_tool=NULL, mcp_outcome=NULL, latency_ms=NULL`.

### Producer wiring

- In `scripts/little_loops/hooks/post_tool_use.py:handle()`, inside
  the existing `contextlib.suppress(Exception)` block:
  - Compute `mcp_server`, `mcp_tool` by parsing `tool_name` when it
    matches `^mcp__(.+?)__(.+)$`.
  - Compute `mcp_outcome` by inspecting `tool_response.isError` (MCP
    standard) or `tool_response.error` (legacy); default to `success`
    when the response is non-empty and `error` is absent.
  - Compute `latency_ms` from `tool_call.started_at` /
    `tool_call.completed_at` if present in the payload; else leave
    NULL (don't measure from the hook handler — that measures only
    the hook itself, not the tool).
- Extend `_backfill_tool_events` (`session_store.py:1620-1664`) to
  extract the same fields from historical JSONL assistant blocks.

### Read API

- `history_reader.mcp_server_usage(server=None, since=None)` —
  call counts and average latency per server.
- `history_reader.mcp_failure_rate(server=None, tool=None, since=None)`
  — fraction of MCP calls with `mcp_outcome='error'`.
- Extend `agent_usage` (ENH-2497) to roll up MCP servers alongside
  subagent types.

### CLI surface

- `ll-session recent --kind tool --mcp-server pencil` (optional flag).
- `ll-ctx-stats`: add an "MCP server health" block (per-server
  success/latency rollup).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**MCP server/tool parser — regex vs split equivalence:**
Both the regex `^mcp__(.+?)__(.+)$` specified in the issue and the `str.split("__")` heuristic used in `scripts/little_loops/adapters/codex.py:188-204` produce identical `(server, tool)` tuples for valid `mcp__<server>__<tool>` names. Verified by trace for `mcp__pencil__batch_design` → `("pencil", "batch_design")`, `mcp__zai-mcp-server__analyze_image` → `("zai-mcp-server", "analyze_image")`, and the degenerate `mcp__foo` → `(None, None)` cases. Recommendation: use the issue's anchored regex because it documents the contract more explicitly and rejects accidental `mcp`-prefix matches on strings like `mcp_foo__bar` (single underscore after `mcp`), which `startswith("mcp__")` + `split` would also reject — so functionally identical, but the regex makes the matcher visible at the call site.

**MCP outcome source — `isError` is canonical, no snake_case fallback needed for Claude Code:**
The codebase has two `isError`/`is_error` variants: the MCP-standard camelCase `isError` (per `mcp_call.py:296` and `fsm/evaluators.py:1008`) and a legacy snake_case `is_error` from `subprocess_utils.py:471` (a non-MCP CLI streaming path). For Claude Code's PostToolUse payload the issue's "MCP standard, then legacy fallback" sequence is conservative — the legacy `is_error` is not relevant to MCP tool calls. The MCP standard read `tool_response.get("isError", False)` is sufficient. Document the fallback in case the host evolves.

**`latency_ms` source — host-supplied timestamps do NOT exist in Claude Code PostToolUse today:**
The issue text at lines 81-84 proposes either `tool_call.started_at` / `tool_call.completed_at` from the payload OR `time.monotonic()` measured around the dispatch. Verified by codebase analysis: neither `started_at` nor `completed_at` appears anywhere under `scripts/little_loops/` (Grep returns no matches against `tool_call.*`), and neither field is in the Claude Code PostToolUse input schema documented at `docs/claude-code/hooks-reference.md:907-929`. `time.monotonic()` inside the hook measures only the hook handler (a single INSERT + a few `json.dumps` calls), not the MCP dispatch — the issue text already rejects this approach. Practical consequence: `latency_ms` will be **NULL in all writes until/unless the host adds timing data to its payload**. The column is forward-compatible — populate it conditionally inside the `contextlib.suppress(Exception)` block:

```python
tool_call = payload.get("tool_call") or {}
started = tool_call.get("started_at")
completed = tool_call.get("completed_at")
latency_ms = None
if isinstance(started, (int, float)) and isinstance(completed, (int, float)):
    latency_ms = int(max(0, completed - started))
```

Leave NULL (don't raise) when the payload doesn't carry these fields.

**`mcp_outcome` cannot be backfilled from JSONL today:**
`_backfill_tool_events` (`session_store.py:1836-1875`) iterates only assistant `type == "tool_use"` blocks. The MCP response envelope (`isError` and friends) lives in the *paired* user `tool_result` block — `_backfill_tool_events` does not consult those. To backfill `mcp_outcome` from JSONL, the producer would need to walk paired records by `tool_use_id` (a non-trivial restructure). The issue text at lines 150-152 explicitly accepts `NULL` for pre-migration rows, and the same NULL semantics apply to backfilled rows after the v21 migration lands (the column exists but historical backfills populate `mcp_server` / `mcp_tool` only). This is acceptable — `mcp_outcome` will populate for live writes going forward.

**JSONL FTS coverage caveat:**
`_backfill_tool_events` at `session_store.py:1866-1873` calls `_index(content=tool_name, ...)` after each INSERT. Live `post_tool_use.handle()` does NOT call `_index()` after its INSERT (the same asymmetry flagged in ENH-2497). For MCP FTS coverage, `ll-session search --fts "pencil"` will only surface **backfilled** MCP rows. The live-insert `_index()` call is a known gap; consider extending once ENH-2497's live `_index()` widening lands (out of scope for ENH-2511 alone).

## Implementation Steps

1. **Schema migration (batched with ENH-2497, v21).** Append a new entry to `_MIGRATIONS` at `scripts/little_loops/session_store.py:709-734` with the comment `# v21 (ENH-2497 + ENH-2511): agent_type on tool_events (ENH-2497) + mcp_server/mcp_tool/mcp_outcome/latency_ms (ENH-2511). All nullable so pre-migration rows remain valid.` followed by the `ALTER TABLE tool_events ADD COLUMN …` statements and the two `CREATE INDEX IF NOT EXISTS idx_tool_events_mcp_server / mcp_outcome` statements from the Proposed Solution. Bump `SCHEMA_VERSION = 20` → `21` at `session_store.py:207`. Coordinate with ENH-2497's PR so the single migration block lands atomically.

2. **Extend `_backfill_tool_events` for MCP columns.** In `scripts/little_loops/session_store.py:1836-1875`, before the existing INSERT at `:1861`, add the regex parser:

   ```python
   m = re.match(r"^mcp__(.+?)__(.+)$", tool_name)
   mcp_server = m.group(1) if m else None
   mcp_tool = m.group(2) if m else None
   ```

   Extend the INSERT column list and tuple to include `mcp_server, mcp_tool` (with values `None, None` — see Codebase Research Findings above: `mcp_outcome` and `latency_ms` cannot be backfilled from JSONL today). Keep the existing `_index()` call unchanged.

3. **Extend live `post_tool_use.handle()` for MCP columns.** In `scripts/little_loops/hooks/post_tool_use.py:151-180`, inside the existing `with contextlib.suppress(Exception):` block at `:158`, before the INSERT at `:163`, add:
   - regex parser for `mcp_server` / `mcp_tool` (same regex as backfill)
   - `mcp_outcome` extraction: `tool_response.get("isError", False)` → `"error"` if True, else `"success"` (skip the legacy `is_error` fallback — not relevant to MCP tool calls per Codebase Research Findings)
   - `latency_ms` extraction from `payload.get("tool_call", {})` per the conditional snippet in Codebase Research Findings

   Extend the INSERT column list and tuple to include all four new columns. The whole extraction block stays inside `contextlib.suppress(Exception)` so a malformed `tool_response` leaves the new columns NULL and never raises.

4. **Add `ToolEvent` dataclass + `recent_tool_events` / `mcp_server_usage` / `mcp_failure_rate` to `history_reader.py`.** At `scripts/little_loops/history_reader.py:106-162`, add a `ToolEvent` dataclass with the existing `tool_events` columns plus the four new nullable fields (defaults `None`). At `:466-546`, add `recent_tool_events(mcp_server=None, mcp_tool=None, mcp_outcome=None, *, limit=20, db=DEFAULT_DB_PATH)` mirroring `recent_skill_events()` shape — stack optional `WHERE … AND` clauses. At `:497-546`, add `mcp_server_usage(server=None, *, since=None, db=DEFAULT_DB_PATH)` (returns `[{mcp_server, invocations, completions, successes, success_rate, avg_latency_ms}, …]`) and `mcp_failure_rate(server=None, tool=None, *, since=None, db=DEFAULT_DB_PATH)` (returns `[{mcp_server, mcp_tool, invocations, error_count, failure_rate}, …]`), both using `_connect_readonly()` at `:256-270` and returning `[]` on `sqlite3.Error`.

5. **Add CLI filters to `ll-session recent --kind tool`.** In `scripts/little_loops/cli/session.py:112-130`, add three optional args to `recent_parser`: `--mcp-server NAME`, `--mcp-tool NAME`, `--mcp-outcome {success,error,timeout}` (default `None`). In the dispatch at `:430-461`, when `--kind tool` and any MCP flag is set, push the corresponding `WHERE mcp_server = ?` / `mcp_tool = ?` / `mcp_outcome = ?` clauses into the SQL (extend the `recent()` call or add a dedicated `recent_tool_events(...)` branch mirroring the existing `--issue` branch at `:434-447`).

6. **Extend `ll-ctx-stats` MCP server health block.** In `scripts/little_loops/cli/ctx_stats.py:118-166`, add a sibling section to `_aggregate_tool_events()` that calls the new `mcp_server_usage()` helper and prints a per-server rollup (count + success-rate + avg latency).

7. **Tests.** Add to `scripts/tests/test_session_store.py`:
   - `TestSchemaV21ToolMcpTelemetry` mirroring `TestSchemaV15SkillCompletionColumns` at `:3914-3966` (three tests: column-existence via PRAGMA, pre-migration row preservation via `_bootstrap_schema_at(db, 20)`, dispatch-only NULL handling)
   - `TestBackfillToolEventsMcpColumns` covering JSONL backfill populating `mcp_server` / `mcp_tool` from assistant `tool_use` blocks (and `mcp_outcome` / `latency_ms` remaining NULL for backfilled rows)

   Add to `scripts/tests/test_hook_post_tool_use.py`: extend `TestPostToolUseWithSessionStore` with cases for MCP success / error / timeout outcomes, non-MCP NULL handling, malformed-payload NULL handling, and a payload carrying `tool_call.started_at` / `completed_at` populating `latency_ms`.

   Add to `scripts/tests/test_history_reader.py`: `test_mcp_server_usage_success_rate` (mirrors `test_summarize_skills_success_rate` at `:1415-1436`), `test_recent_tool_events_filters`, and an entry in `test_readers_return_empty_on_missing_db` at `:1530-1545` covering the new helpers.

8. **Docs + verify.** Add v21 row to `docs/ARCHITECTURE.md:655-679` schema versions table. Document the new `tool_events` columns + `history_reader` helpers in `docs/reference/API.md` and the new `ll-session recent` flags in `docs/reference/CLI.md`. Run `python -m pytest scripts/tests/test_session_store.py scripts/tests/test_hook_post_tool_use.py scripts/tests/test_history_reader.py scripts/tests/test_cli_ctx_stats.py scripts/tests/test_cli_session.py` and `python -m pytest scripts/tests/ -v` for the full suite gate.

## Acceptance Criteria

- Schema migration lands; the four new columns exist on `tool_events`;
  `SCHEMA_VERSION` bumped.
- An `mcp__pencil__batch_design` call writes a row with
  `mcp_server="pencil"`, `mcp_tool="batch_design"`,
  `mcp_outcome="success"` (or `"error"` on failure), and
  `latency_ms=<elapsed>`.
- A non-MCP tool call (`Read`, `Write`, `Edit`) leaves all four new
  columns NULL.
- Pre-migration rows read back with all four columns NULL (no data
  fix required).
- Writes are best-effort: a malformed MCP response payload leaves the
  columns NULL, never raises.
- `ll-session recent --kind tool` returns rows with the new columns
  populated for MCP entries; the MCP failure rate query works.
- Tests cover: success/error/timeout outcomes, non-MCP NULL handling,
  pre-migration NULL handling, DB-absent graceful degradation.

## Sources

- EPIC-2457 review (third-pass expansion, 2026-07-06) — item from the
  user-reported gap list (explicitly noted as "Overlaps ENH-2497")
- ENH-2497 — sibling `agent_type` column on `tool_events`; this issue
  shares the migration
- `scripts/little_loops/hooks/post_tool_use.py` — live producer
- `.mcp.json` / `~/.claude/.mcp.json` — MCP server catalog whose usage
  this makes observable
- ENH-2493 — sibling executor telemetry work

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | `ll-session --kind tool` extensions |

## Status

**Open** | Created: 2026-07-06 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and **ENH-2497**
both propose additive `ALTER TABLE tool_events ADD COLUMN ...` migrations
against the *same* target schema version and explicitly plan to land as one
batched migration (this issue's own text: "Overlaps ENH-2497 explicitly noted
in the user's gap list" / "Coordinate with ENH-2497's `agent_type` column
... single migration batch"). Verified against current code
(`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done) — neither
issue's stale "bump 18→19" Integration Map text is current. `depends_on:
[ENH-2497]` has been added to this issue's frontmatter so ENH-2497 is
implemented first (its `agent_type` column lands), and this issue's migration
is authored as an *addition to that same migration block* rather than a
second independent `tool_events` ALTER — avoiding two competing migrations
racing for the same next-available schema version.

## Session Log
- `/ll:refine-issue` - 2026-07-16T17:13:15 - `55bce7cb-d5cb-4ddb-8673-741da1056e98.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:21:42 - `33e15d2a-429d-48f8-8998-aca5080acdd5.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`