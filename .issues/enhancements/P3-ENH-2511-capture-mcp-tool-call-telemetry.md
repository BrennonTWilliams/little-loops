---
id: ENH-2511
title: Capture MCP tool-call telemetry in tool_events
type: ENH
priority: P3
status: done
discovered_date: 2026-07-06
captured_at: '2026-07-06T00:00:00Z'
completed_at: '2026-07-17T23:47:20Z'
discovered_by: capture-issue
parent: EPIC-2457
depends_on:
- ENH-2497
labels:
- enhancement
- history-db
- mcp
- widening
- captured
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

- `scripts/little_loops/session_store.py:211` — `SCHEMA_VERSION` constant (bump 24 → **25**; standalone migration, ENH-2497's v24 `agent_type` migration already shipped independently)
- `scripts/little_loops/session_store.py:806-815` — `_MIGRATIONS` list; append a **new v25 entry** after the existing v24 (ENH-2497) entry — `ALTER TABLE tool_events ADD COLUMN mcp_server/mcp_tool/mcp_outcome/latency_ms` + the two `CREATE INDEX` statements, comment naming ENH-2511 only (matching the v24 entry's comment shape, not a shared block)
- `scripts/little_loops/session_store.py:2116-2160` — `_backfill_tool_events()`; add `mcp__<server>__<tool>` regex parser before the INSERT (`:2145-2149`); extend the column list/tuple to populate `mcp_server` / `mcp_tool` only (see Codebase Research Findings — `mcp_outcome` and `latency_ms` cannot be backfilled from JSONL today); mirror how `agent_type` is derived at `:2140-2144`
- `scripts/little_loops/hooks/post_tool_use.py:137-231` — `handle()` live write; extend the 9-column INSERT at `:175-190` to 13 columns, adding MCP parsing / outcome / latency extraction inside the existing `contextlib.suppress(Exception)` block (`:158-202`), gated by the same `feature_enabled(config, "analytics.enabled")` check at `:151`
- `scripts/little_loops/history_reader.py:627-655` — extend the **existing** `recent_tool_events()` (added by ENH-2497; dict-returning, hardcoded SELECT list at `:640-641`) with `mcp_server` / `mcp_tool` / `mcp_outcome` in both the SELECT list and the optional filter params. **No `ToolEvent` dataclass** — `tool_events` reads are dict-based under the existing convention (unlike `skill_events`'s `SkillEvent`); do not introduce one.
- `scripts/little_loops/history_reader.py` (near `:593-624`, after `agent_usage()`) — add `mcp_server_usage(server=None, *, since=None, db=DEFAULT_DB_PATH)` and `mcp_failure_rate(server=None, tool=None, *, since=None, db=DEFAULT_DB_PATH)` helpers mirroring `summarize_skills()` shape at `:541-590` (GROUP BY + `COUNT(success)`/`SUM(CASE...)`, `_connect_readonly()` at `:300-314`)
- `scripts/little_loops/cli/session.py:112-130` — extend `recent_parser` with `--mcp-server NAME`, `--mcp-tool NAME`, `--mcp-outcome {success,error,timeout}` optional filters. This is the **first** CLI wiring for `recent_tool_events()`'s filter family (no `--agent-type` flag exists yet either) — model the dispatch on the `skill-stats` command (`:616-633`), not the `--issue` branch, which is a different code path
- `scripts/little_loops/cli/session.py:431-464` — extend the `recent` dispatch: when `--kind tool` plus any MCP flag is set, call the extended `recent_tool_events(mcp_server=..., mcp_tool=..., mcp_outcome=...)` instead of the generic `recent()` dispatcher
- `scripts/little_loops/cli/ctx_stats.py:118-166` — `_aggregate_tool_events()`; add a sibling "MCP server health" block feeding a new `mcp_health` key into the flat payload dict, mirroring the `skill_health` shape at `ctx_stats.py:455-471` (sourced from `_aggregate_skill_stats` in `cli/logs.py:760`), not a bespoke shape

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

### Schema migration (v25, standalone — ENH-2497's v24 `agent_type` migration already shipped independently)

```sql
ALTER TABLE tool_events ADD COLUMN mcp_server TEXT;
ALTER TABLE tool_events ADD COLUMN mcp_tool TEXT;
ALTER TABLE tool_events ADD COLUMN mcp_outcome TEXT;
ALTER TABLE tool_events ADD COLUMN latency_ms INTEGER;
CREATE INDEX IF NOT EXISTS idx_tool_events_mcp_server ON tool_events(mcp_server);
CREATE INDEX IF NOT EXISTS idx_tool_events_mcp_outcome ON tool_events(mcp_outcome);
```

Append as a new entry in `_MIGRATIONS` (`session_store.py:806-815`)
immediately after ENH-2497's v24 entry; bump `SCHEMA_VERSION = 24` →
`25` at `session_store.py:211`. No coordination needed with ENH-2497's
PR — it already merged as its own independent migration; this issue's
`depends_on: [ENH-2497]` is satisfied. Pre-migration rows read back
with `mcp_server=NULL, mcp_tool=NULL, mcp_outcome=NULL,
latency_ms=NULL`.

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

### Codebase Research Findings (2026-07-17 refresh — supersedes the 2026-07-16 pass above)

_Added by `/ll:refine-issue --auto --full-rewrite` — every anchor below was re-verified against current code; the 2026-07-16 pass's anchors (and the "batched with ENH-2497" plan) are now stale on two counts, not one._

- **ENH-2497 shipped independently at v24 — this issue's migration is now v25, standalone, not batched.** `SCHEMA_VERSION = 24` at `session_store.py:211`. The `_MIGRATIONS` list runs `session_store.py:341-815`; ENH-2497's `agent_type` migration is its own entry at `session_store.py:806-814`:
  ```python
  # v24 (ENH-2497): agent_type discriminator on tool_events for Task-tool spawns...
  """
  ALTER TABLE tool_events ADD COLUMN agent_type TEXT;
  CREATE INDEX IF NOT EXISTS idx_tool_events_agent ON tool_events(agent_type);
  """,
  ]
  ```
  This issue's migration must be appended as a **new** entry after line 814 (before the list's closing `]` at line 815), bumping `SCHEMA_VERSION` 24 → **25**. `depends_on: [ENH-2497]` remains correct (for the `_normalize_agent_type`-style precedent and shared table), but there is no shared migration block to coordinate — ENH-2497 already merged.
- **`_backfill_tool_events` is now at `session_store.py:2116-2160`** (not `:1836-1875`, not `:1620-1664`). Its INSERT (`:2145-2149`) is already a 9-column statement — `ts, session_id, tool_name, args_hash, result_size, bytes_in, bytes_out, cache_hit, agent_type` — since ENH-2497 landed. No MCP columns exist yet.
- **Live `post_tool_use.handle()` INSERT is now at `post_tool_use.py:175-190`** (not `:163-177`), inside `contextlib.suppress(Exception)` starting `:158`, gated by `feature_enabled(config, "analytics.enabled")` at `:151`. Also a 9-column INSERT (added `agent_type`).
- **`history_reader.py` has no `ToolEvent` dataclass and never will under the existing convention** — unlike `skill_events`'s `SkillEvent`, `tool_events` reads are dict-returning. ENH-2497 already added `agent_usage()` (`:593-624`, group-by-count-only) and `recent_tool_events()` (`:627-655`, dict-returning, **hardcoded SELECT column list at `:640-641`**, optional `agent_type` filter). This issue should **extend `recent_tool_events()`'s existing SELECT list and filter params** with `mcp_server`/`mcp_tool`/`mcp_outcome` — not invent a new function or a dataclass. `summarize_skills()` (`:541-590`) remains the best template for the `mcp_server_usage`/`mcp_failure_rate` GROUP BY + success-rate shape (`COUNT(success)` / `SUM(CASE WHEN...)` / Python-side `successes/completions if completions else None`).
- **`cli/session.py` `recent` parser spans `:112-130`.** `"tool"` is already a valid `--kind` (`VALID_KINDS` at `session_store.py:214`, `_KIND_TABLE` at `:230`) and `recent_tool_events()` already exists — but has **no CLI flag wiring yet** (no `--agent-type` flag shipped despite the function supporting it). This issue's `--mcp-server`/`--mcp-tool`/`--mcp-outcome` flags would be the *first* CLI wiring for this function family. Model the dispatch on the `skill-stats` command (`cli/session.py:616-633`, calls `summarize_skills(...)` and prints a rollup) rather than the `--issue` filter, which is a different code path (`sessions_for_issue()`, not `recent_tool_events()`).
- **`cli/ctx_stats.py` `_aggregate_tool_events()` is still at `:118-166`** — reads only `tool_name, bytes_in, bytes_out, cache_hit`, filtered to rows where byte data is non-NULL; no `agent_type`/MCP awareness. The `skill_health` JSON-aggregation shape (`ctx_stats.py:455-471`, sourced from `_aggregate_skill_stats` in `cli/logs.py:760`) is the pattern to follow for a new "MCP server health" block — add a sibling `mcp_health` key to the flat payload dict, not a bespoke shape.
- **`docs/ARCHITECTURE.md` schema table's last row is v24** at line 682; range references at lines 727 and 752 also need bumping to "v1–v25".
- **Test precedent upgrade: use `scripts/tests/test_enh_2497_agent_type.py` (291 lines) as the structural template**, not the generic `TestSchemaV15SkillCompletionColumns` cited in the prior pass. It ships `_bootstrap_schema_at()`, plus `TestSchemaV24AgentType`, `TestTaskSpawnAgentType`, `TestBackfillAgentType`, `TestAgentUsageAggregation`, `TestFTSIndexing`, `TestReadersEmptyOnMissingDb` — mirror this exact class structure as `TestSchemaV25ToolMcpTelemetry` / `TestTaskSpawnMcpColumns` / etc.
- **MCP-name parsing precedent confirmed partial only:** `adapters/codex.py:188-204` `_derive_mcp_servers()` extracts just the server segment (`tool.split("__")[1]`), not the tool segment — this issue's full `server`+`tool` regex parser is new work, not an extension of existing code.
- **`isError` extraction precedent confirmed unchanged:** `mcp_call.py:294-298` (`result.get("isError", False)`) and `fsm/evaluators.py:962-1014` (`evaluate_mcp_result`, `envelope.get("isError", exit_code != 0)`) are still the canonical shape.

## Implementation Steps

1. **Schema migration (v25, standalone).** Append a new entry to `_MIGRATIONS` at `scripts/little_loops/session_store.py:806-815`, immediately after the existing v24 (ENH-2497) entry, with the comment `# v25 (ENH-2511): mcp_server/mcp_tool/mcp_outcome/latency_ms on tool_events. All nullable so pre-migration rows remain valid.` followed by the `ALTER TABLE tool_events ADD COLUMN …` statements and the two `CREATE INDEX IF NOT EXISTS idx_tool_events_mcp_server / mcp_outcome` statements from the Proposed Solution. Bump `SCHEMA_VERSION = 24` → `25` at `session_store.py:211`. No coordination with another PR needed — ENH-2497 already merged independently.

2. **Extend `_backfill_tool_events` for MCP columns.** In `scripts/little_loops/session_store.py:2116-2160`, before the existing INSERT at `:2145`, add the regex parser (mirroring how `agent_type` is derived at `:2140-2144`):

   ```python
   m = re.match(r"^mcp__(.+?)__(.+)$", tool_name)
   mcp_server = m.group(1) if m else None
   mcp_tool = m.group(2) if m else None
   ```

   Extend the INSERT column list and tuple (currently 9 columns ending in `agent_type`) to include `mcp_server, mcp_tool` (with values `None, None` for `mcp_outcome`/`latency_ms` — see Codebase Research Findings above: they cannot be backfilled from JSONL today). Keep the existing `_index()` call unchanged.

3. **Extend live `post_tool_use.handle()` for MCP columns.** In `scripts/little_loops/hooks/post_tool_use.py:137-231`, inside the existing `with contextlib.suppress(Exception):` block at `:158`, before the INSERT at `:175`, add:
   - regex parser for `mcp_server` / `mcp_tool` (same regex as backfill)
   - `mcp_outcome` extraction: `tool_response.get("isError", False)` → `"error"` if True, else `"success"` (skip the legacy `is_error` fallback — not relevant to MCP tool calls per Codebase Research Findings)
   - `latency_ms` extraction from `payload.get("tool_call", {})` per the conditional snippet in Codebase Research Findings

   Extend the INSERT column list and tuple (currently 9 columns) to include all four new columns. The whole extraction block stays inside `contextlib.suppress(Exception)` so a malformed `tool_response` leaves the new columns NULL and never raises.

4. **Extend `recent_tool_events` + add `mcp_server_usage` / `mcp_failure_rate` to `history_reader.py`.** At `scripts/little_loops/history_reader.py:627-655`, extend the existing `recent_tool_events()` (added by ENH-2497) — add `mcp_server`, `mcp_tool`, `mcp_outcome` params and widen the hardcoded SELECT list at `:640-641` to include the four new columns; stack optional `WHERE … AND` clauses as it already does for `agent_type`. Near `:593-624` (after `agent_usage()`), add `mcp_server_usage(server=None, *, since=None, db=DEFAULT_DB_PATH)` (returns `[{mcp_server, invocations, completions, successes, success_rate, avg_latency_ms}, …]`) and `mcp_failure_rate(server=None, tool=None, *, since=None, db=DEFAULT_DB_PATH)` (returns `[{mcp_server, mcp_tool, invocations, error_count, failure_rate}, …]`), both mirroring `summarize_skills()`'s shape at `:541-590` and using `_connect_readonly()` at `:300-314`, returning `[]` on `sqlite3.Error`. Do not add a `ToolEvent` dataclass — `tool_events` reads are dict-based under the existing convention.

5. **Add CLI filters to `ll-session recent --kind tool`.** In `scripts/little_loops/cli/session.py:112-130`, add three optional args to `recent_parser`: `--mcp-server NAME`, `--mcp-tool NAME`, `--mcp-outcome {success,error,timeout}` (default `None`). In the dispatch at `:431-464`, when `--kind tool` and any MCP flag is set, call the extended `recent_tool_events(mcp_server=..., mcp_tool=..., mcp_outcome=...)` instead of the generic `recent()` dispatcher — this is the first CLI wiring for this function family, so model the dispatch shape on the `skill-stats` command (`:616-633`) rather than the `--issue` branch (a different code path).

6. **Extend `ll-ctx-stats` MCP server health block.** In `scripts/little_loops/cli/ctx_stats.py:118-166`, add a sibling section to `_aggregate_tool_events()` that calls the new `mcp_server_usage()` helper and feeds a new `mcp_health` key into the flat payload dict (mirroring `skill_health` at `ctx_stats.py:455-471`) — count + success-rate + avg latency per server.

7. **Tests.** Model the whole suite on `scripts/tests/test_enh_2497_agent_type.py` (291 lines) as the structural template. Add to `scripts/tests/test_session_store.py`:
   - `TestSchemaV25ToolMcpTelemetry` mirroring `TestSchemaV24AgentType` (three tests: column-existence via PRAGMA, pre-migration row preservation via `_bootstrap_schema_at(db, 24)`, dispatch-only NULL handling)
   - `TestBackfillToolEventsMcpColumns` mirroring `TestBackfillAgentType`, covering JSONL backfill populating `mcp_server` / `mcp_tool` from assistant `tool_use` blocks (and `mcp_outcome` / `latency_ms` remaining NULL for backfilled rows)

   Add to `scripts/tests/test_hook_post_tool_use.py`: extend `TestPostToolUseWithSessionStore` (mirroring `TestTaskSpawnAgentType`) with cases for MCP success / error / timeout outcomes, non-MCP NULL handling, malformed-payload NULL handling, and a payload carrying `tool_call.started_at` / `completed_at` populating `latency_ms`.

   Add to `scripts/tests/test_history_reader.py`: `test_mcp_server_usage_success_rate` (mirrors `test_summarize_skills_success_rate`), `test_recent_tool_events_mcp_filters`, and an entry in `test_readers_return_empty_on_missing_db` covering the new helpers (mirroring `TestReadersEmptyOnMissingDb`).

8. **Docs + verify.** Add a v25 row to `docs/ARCHITECTURE.md`'s schema versions table (last row is currently v24 at line 682) and bump the "v1–v24" range references at lines 727 and 752 to "v1–v25". Document the new `tool_events` columns + `history_reader` helpers in `docs/reference/API.md` and the new `ll-session recent` flags in `docs/reference/CLI.md`. Run `python -m pytest scripts/tests/test_session_store.py scripts/tests/test_hook_post_tool_use.py scripts/tests/test_history_reader.py scripts/tests/test_cli_ctx_stats.py scripts/tests/test_cli_session.py` and `python -m pytest scripts/tests/ -v` for the full suite gate.

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

## Success Metrics

- MCP failure visibility: today, "how often does pencil fail" requires
  manual string-parsing of `tool_name`; after this change,
  `mcp_failure_rate(server="pencil")` answers it in one query.
- MCP server call volume: today, per-server call counts require regex
  extraction from `tool_name`; after this change, `mcp_server_usage()`
  returns per-server invocation counts directly.
- `latency_ms` coverage: 0% populated until the host adds
  `tool_call.started_at`/`completed_at` to the PostToolUse payload (see
  Codebase Research Findings) — a known limitation, not a launch
  blocker.

## Scope Boundaries

- **In scope**: `mcp_server`, `mcp_tool`, `mcp_outcome`, `latency_ms`
  columns on `tool_events` (v25 standalone migration — ENH-2497's v24
  `agent_type` migration already shipped independently);
  live `post_tool_use` extraction; `_backfill_tool_events` extraction
  of `mcp_server`/`mcp_tool` only; `history_reader` read helpers;
  `ll-session recent` CLI filters; `ll-ctx-stats` MCP health block.
- **Out of scope**: backfilling `mcp_outcome` for historical JSONL
  rows (would require restructuring `_backfill_tool_events` to walk
  paired `tool_use`/`tool_result` blocks by `tool_use_id` — non-trivial,
  deferred); populating `latency_ms` via `time.monotonic()` in the hook
  handler (measures only the hook, not the tool dispatch — explicitly
  rejected in Proposed Solution); extending live `_index()` FTS
  coverage for MCP rows (same asymmetry ENH-2497 already flags,
  deferred to that issue).

## API/Interface

```python
def recent_tool_events(
    mcp_server: str | None = None,
    mcp_tool: str | None = None,
    mcp_outcome: str | None = None,
    *,
    limit: int = 20,
    db: Path = DEFAULT_DB_PATH,
) -> list[ToolEvent]: ...

def mcp_server_usage(
    server: str | None = None, *, since: str | None = None, db: Path = DEFAULT_DB_PATH
) -> list[dict]: ...

def mcp_failure_rate(
    server: str | None = None,
    tool: str | None = None,
    *,
    since: str | None = None,
    db: Path = DEFAULT_DB_PATH,
) -> list[dict]: ...
```

CLI: `ll-session recent --kind tool --mcp-server NAME --mcp-tool NAME
--mcp-outcome {success,error,timeout}` — new optional filters,
additive only (no change to existing `recent` invocations).

## Impact

- **Priority**: P3 - Observability enhancement, not user-facing;
  unblocks per-server MCP failure/latency analysis but doesn't block
  other work.
- **Effort**: Medium - Touches six files (migration, live hook,
  backfill, history_reader, CLI, ctx_stats) but each change follows an
  existing precedent (v15 migration shape, `recent_skill_events`/
  `summarize_skills` shape, `--issue` CLI filter shape) rather than
  introducing new patterns.
- **Risk**: Low - All four new columns are nullable; the live-write
  extraction sits inside the existing `contextlib.suppress(Exception)`
  block, so a malformed MCP payload leaves columns NULL instead of
  raising; pre-migration rows read back with all four columns NULL.
- **Breaking Change**: No

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-17_

**Readiness Score**: 84/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → Below threshold

### Concerns
- The migration plan is stale: the issue still describes batching into a
  shared "v21" migration with ENH-2497's `agent_type` column. ENH-2497 is now
  `status: done` and shipped its own standalone migration at **v24**
  (`session_store.py:806-813`); `SCHEMA_VERSION` is now **24**, not 20/21.
  This issue's migration must target **v25** as its own `_MIGRATIONS` entry,
  not an amendment to ENH-2497's already-committed block.
- Every Integration Map line-number anchor has drifted since this issue's
  last refine pass, because ENH-2497 plus three unrelated migrations
  (FEAT-2478 v21, ENH-2492 v22, ENH-2463 v23) landed in between:
  `_backfill_tool_events` is now at `session_store.py:2116` (issue cites
  `:1836-1875`); the live `post_tool_use.handle()` INSERT is now a 9-column
  statement at `:163-186` including `agent_type` (issue cites an 8-column
  block at `:163-177`); `history_reader.py` has no `ToolEvent` dataclass yet
  and `recent_skill_events` is at `:510` (issue cites `:466-494`).

### Outcome Risk Factors
- Broad enumeration across 6+ distinct sites (migration, live hook, backfill,
  three new `history_reader` helpers, CLI filters, `ll-ctx-stats`) — each
  site's change is mechanical/local, but the breadth raises coordination
  risk.
- Stale integration-map anchors (see Concerns) mean the implementer must
  re-locate every insertion point in `session_store.py`, `post_tool_use.py`,
  and `history_reader.py` against current code rather than trusting the
  cited line numbers.

### Resolution (`/ll:refine-issue --auto --full-rewrite`, 2026-07-17)

Both Concerns above are addressed: the migration plan now targets **v25**
as a standalone `_MIGRATIONS` entry (Integration Map, Proposed Solution,
and Implementation Steps all updated — see the "2026-07-17 refresh"
Codebase Research Findings subsection under Current Behavior), and every
Integration Map anchor was re-verified against current code by three
parallel research agents (locator/analyzer/pattern-finder) this pass.
Two additional findings beyond what the confidence check flagged: (1)
`history_reader.py` has no `ToolEvent` dataclass under the *current*
convention and never will — `tool_events` reads are dict-based, so the
plan now extends the existing `recent_tool_events()` (already shipped
by ENH-2497) rather than inventing a dataclass; (2) the best test
template is `scripts/tests/test_enh_2497_agent_type.py`, not the
generic `TestSchemaV15SkillCompletionColumns` the issue previously
cited — Implementation Steps now reference it directly.

## Resolution

Implemented as specified. Added the v25 `_MIGRATIONS` entry (four nullable
`tool_events` columns + two indexes), bumped `SCHEMA_VERSION` 24→25, added
`_parse_mcp_tool_name()` (mirrors `_normalize_agent_type`), and wired
`mcp_server`/`mcp_tool` into `_backfill_tool_events()` and all four new
columns into the live `post_tool_use.handle()` write (`mcp_outcome` from
`tool_response.isError`, `latency_ms` from `tool_call.started_at`/
`completed_at` when present — currently always NULL until the host supplies
those fields, a known limitation the issue itself documents in Success
Metrics). Extended `recent_tool_events()` with MCP filter params and added
`mcp_server_usage()`/`mcp_failure_rate()` readers mirroring
`summarize_skills()`. Wired `--mcp-server`/`--mcp-tool`/`--mcp-outcome`
flags into `ll-session recent --kind tool`, and an MCP health block into
`ll-ctx-stats` (both text and `--json` output). Updated
`docs/ARCHITECTURE.md` (v25 schema row + v1–v25 range bumps),
`docs/reference/API.md`, and `docs/reference/CLI.md`.

Added `scripts/tests/test_enh_2511_mcp_telemetry.py` (15 tests) mirroring
`test_enh_2497_agent_type.py`'s structure. Discovered and fixed 9 other
tests across `test_session_store.py` and `test_assistant_messages.py` that
hardcoded `SCHEMA_VERSION == 24` — bumped to 25 alongside this migration
(same pattern each prior schema bump has followed).

Full suite: `python -m pytest scripts/tests/` — 15197 passed, 37 skipped.
`ruff check scripts/` and `python -m mypy scripts/little_loops/` clean.
`ll-verify-kinds` passes (no `_KIND_TABLE` changes needed for additive
columns).

Deferred (per issue's explicit Scope Boundaries): backfilling `mcp_outcome`
for historical JSONL rows, populating `latency_ms` via in-hook
`time.monotonic()` (explicitly rejected — measures the hook, not the tool),
and extending live `_index()` FTS coverage for MCP rows.

## Session Log
- `/ll:manage-issue` - 2026-07-17T23:46:46Z - `3259400c-221e-4914-8555-5c8433943c52.jsonl`
- `/ll:ready-issue` - 2026-07-17T23:25:55 - `95d58502-efed-4086-9368-d33049450ddd.jsonl`
- `/ll:confidence-check` - 2026-07-17T00:00:00Z - `3d4dc684-7fa0-4a7f-9c7f-02673d08beb3.jsonl`
- `/ll:refine-issue` - 2026-07-17T23:21:30 - `7d467726-0058-4674-8493-2959934ee2e9.jsonl`
- `/ll:confidence-check` - 2026-07-17T00:00:00Z - `ba6bbeba-8f6d-40e7-864f-c6224605834e.jsonl`
- `/ll:format-issue` - 2026-07-17T23:10:15 - `d146d3f9-5589-4cca-b4a4-6607e48ed6fb.jsonl`
- `/ll:refine-issue` - 2026-07-16T17:13:15 - `55bce7cb-d5cb-4ddb-8673-741da1056e98.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:21:42 - `33e15d2a-429d-48f8-8998-aca5080acdd5.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`