---
id: ENH-2722
type: ENH
title: ll-ctx-stats waste view over history.db (split from ENH-2712)
priority: P2
status: done
captured_at: '2026-07-21T18:20:00Z'
completed_at: '2026-07-23T03:02:46Z'
discovered_date: '2026-07-21'
discovered_by: confidence-check
parent: EPIC-2456
labels:
- token-cost
- observability
- history-db
relates_to:
- EPIC-2456
- ENH-2712
- ENH-2721
- FEAT-2478
- ENH-2477
- ENH-2461
- ENH-2623
decision_needed: false
confidence_score: 98
outcome_confidence: 80
score_complexity: 21
score_test_coverage: 23
score_ambiguity: 15
score_change_surface: 21
---

# ENH-2722: `ll-ctx-stats` waste view over history.db (split from ENH-2712)

## Summary

Split out of ENH-2712's query/CLI half: once ENH-2721 lands a `run_id` join key on `usage_events`, add a `waste` view to `ll-ctx-stats` that joins per-run token totals against terminal run outcome, so failure-mode fixes can be ranked against per-token optimizations. This issue is read-only analytics — no schema changes.

## Motivation

All of EPIC-2456 optimizes $/token on successful work; nothing measures tokens spent on runs that produced no accepted artifact — oscillating loops, GATE_FAILED retries, toothless-evaluator iterations. If a meaningful share of spend goes to those runs, fixing them dominates every remaining tier of the epic — but today that share is unknown.

**Blocked by ENH-2721**: this issue's join (`usage_events.run_id = loop_runs.run_id`) does not exist until ENH-2721's schema migration and live writer ship. Do not start implementation before ENH-2721 is merged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Blocker resolved — no longer blocking.** ENH-2721 (status `done`) was itself decomposed into ENH-2723 (schema migration), ENH-2724 (live writer), ENH-2725 (backfill) — all three are `status: done`. Verified in the live codebase: `usage_events` gained `run_id TEXT` at schema **v29** (`session_store.py:916-923`, comment tags it `ENH-2723`), with `CREATE INDEX IF NOT EXISTS idx_usage_events_run_id`. `SCHEMA_VERSION` is now **31** (up from the 28 assumed when this issue was written). The live writer is `record_usage_event()` (`session_store.py:2065-2109`), called from `FSMExecutor._finish()` (`fsm/executor.py:2690-2748`), which derives `run_id` identically for both the `usage_events` row and the corresponding `loop_runs` row in the same call — `self.started_at.replace(":", "").replace(".", "").replace("+", "")[:17] + f"-{self.fsm.name}"` (`fsm/executor.py:2708/2711` and `2732/2738`) — so the equi-join matches by construction for live-written rows. Backfilled historical rows use a separate timestamp-window matcher, `_derive_run_id_for_ts()` (`session_store.py:2980-2990`), which leaves `run_id` `NULL` when a timestamp falls in zero or multiple overlapping `loop_runs` windows (e.g. concurrent `ll-parallel` runs, `session_store.py:2983-2985`) — those rows simply won't join, they don't misattribute. `frontmatter blocked_by` has been cleared accordingly.

## Current Behavior

`ll-ctx-stats` reports context savings and per-tool stats; no view correlates token spend with run outcome. Wasted spend is invisible.

## Expected Behavior

`ll-ctx-stats` prints per-loop and aggregate: total tokens, tokens on runs ending in failure/stall/no-artifact, waste percentage, and the top-N most wasteful loops/states — read-only over `.ll/history.db` (respecting the `LL_HISTORY_DB` → config → default resolution, ENH-2623).

## Proposed Solution

- Define "wasted": run terminal status ∈ {failed, killed, max_steps-exhausted-without-success}. Start with terminal-status only; per-iteration `diff_stall`/`score_stall` discard tracking is an explicit follow-on, not in scope here.
- SQL join: `usage_events.run_id = loop_runs.run_id` (exact key, once ENH-2721 ships) — no time-range join, no schema change in this issue.
- Read-only; no automated deletion or compaction side effects (per project policy on `raw_events`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The "wasted" definition above does not match any real `terminated_by` value — it needs correcting before implementation.** `loop_runs.terminated_by` is a free-form `TEXT` column (`session_store.py:818`, no CHECK constraint) populated from `FSMExecutor._finish(terminated_by: str, ...)` in `fsm/executor.py`. There is no literal `"failed"` or `"killed"` value anywhere. The actual observed values: `"terminal"` (normal completion, `fsm/executor.py:593`), `"max_steps"` (step-cap exhaustion, lines 490/586/729), `"max_iterations_reached"` (iteration-cap exhaustion, lines 513/590/731), `"timeout"` (line 536), `"error"` (uncaught exception / no valid transition, lines 662/732/787), `"user_stopped"` (line 426), `"system_signal"` (line 429), `"interrupted"` (line 430), `"handoff"` (context-handoff, line 2816, via a separate `ExecutionResult` path that bypasses `_finish()`).
- **Critically, `terminated_by == "terminal"` is not itself success or failure** — a normal FSM completion into a `"failed"` (or any other non-`"done"`) final state also reports `terminated_by: "terminal"`. The executor's own success check (`fsm/executor.py:995-1001`) distinguishes them by pairing `terminated_by == "terminal"` with `final_state == "done"` for success; any other `final_state` on a `"terminal"` finish is a failure. `waste_attribution()` therefore needs a two-part predicate, not a `terminated_by IN (...)` filter alone: `terminated_by IN ('error', 'max_steps', 'max_iterations_reached', 'timeout', 'system_signal', 'interrupted')` OR (`terminated_by = 'terminal'` AND `final_state != 'done'`). Confirm `loop_runs` has a `final_state` column (it does, alongside `terminated_by`, per the v23 migration) before finalizing the SQL. `"user_stopped"` and `"handoff"` are ambiguous (operator-initiated, not necessarily wasted) — worth an explicit decision on whether to count them, since the current binary framing doesn't cover them.
- `cost_attribution()`'s `_COST_ATTR_GROUP_COLUMNS` whitelist (`history_reader.py:850-859`) already includes `"run_id": "run_id"` as a valid GROUP BY dimension — `cost_attribution(group_by="run_id")` already works today and could be a useful cross-check/building block alongside a dedicated `waste_attribution()`.

## Implementation Steps

1. Query module in `history_reader.py` (`waste_attribution()`), modeled on `cost_attribution()` (line 854, whitelist-dict `_COST_ATTR_GROUP_COLUMNS` at line 843 guards `GROUP BY` against injection) and `aggregate_loop_runs()` (line 1550, whitelist `_LOOP_RUN_GROUP_COLUMNS` at line 1544). Follow the module's universal contract: `_connect_readonly()` (line 363, never raises), `try/except sqlite3.Error: logger.warning(...); return []`, numeric aggregates guarded with `row["x"] or 0`. Add to the module docstring's "Public API" list (lines 8-60).
2. CLI surface in `ctx_stats.py`: `ctx_stats.py` has no subcommand structure today (`_build_parser()`, line 40, is a flat parser) — add a `waste` section to the existing combined report (model `_aggregate_mcp_health()`, line 169, which thinly delegates to a `history_reader` function) rather than introducing a new subcommand structure.
3. Fix the existing `ctx_stats.py` ENH-2623 gap while touching this file: it does not call `resolve_history_db()` — it builds `db_path` from a locally-defined `DEFAULT_DB_RELPATH` (line 36), bypassing the `LL_HISTORY_DB` env/config chain entirely. Route through `resolve_history_db()` (`session_store.py:179`), following `cli/history.py:245,262,299,316`'s reference usage (`from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context, resolve_history_db`).
4. Docs: API.md entry + a short "interpreting waste" note.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/little_loops/init/writers.py:92` — mirror whatever wording change is made to `commands/help.md:300`'s one-line `ll-ctx-stats` description, so newly-scaffolded projects' `CLAUDE.md` doesn't go stale relative to the description in this repo.
6. When writing `TestWasteAttribution`'s `waste_pct` divide-by-zero guard test, follow `scripts/tests/test_enh_2511_mcp_telemetry.py:310-423` (`test_mcp_server_usage_success_rate`/`test_mcp_failure_rate`), not `TestCostAttribution` — it's the only existing ratio-computation test template in the codebase; `mcp_server_usage()`/`mcp_failure_rate()` themselves have no unit tests inside `test_history_reader.py` to copy instead.

### Codebase Research Findings

_Added by `/ll:refine-issue` — line numbers re-verified against current source; the file has shifted since this issue was written:_

- `cost_attribution()` is now at `history_reader.py:862` (not 854); its whitelist `_COST_ATTR_GROUP_COLUMNS` is now at `history_reader.py:850` (not 843).
- `aggregate_loop_runs()` is now at `history_reader.py:1558` (not 1550); its whitelist `_LOOP_RUN_GROUP_COLUMNS` is now at `history_reader.py:1552` (not 1544).
- `_connect_readonly()` is at `history_reader.py:370-384` (not 363) — bootstraps via `ensure_db()` then opens `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` with `PRAGMA query_only = ON`.
- `resolve_history_db()` is at `session_store.py:186` (not 179).
- `mcp_server_usage()` (`history_reader.py:746-793`) and `mcp_failure_rate()` (`history_reader.py:796-844`) are closer structural analogs than `cost_attribution()`/`aggregate_loop_runs()` for a percentage/ratio rollup — both compute `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` then a Python-side ratio guarded against divide-by-zero (`successes / completions if completions else None`); `waste_attribution()` should follow this exact ratio-computation shape for `waste_pct`.
- `main_ctx_stats()`'s db-path resolution (the bug being fixed) is at `cli/ctx_stats.py:628`: `db_path = args.db if args.db is not None else cwd / DEFAULT_DB_RELPATH`.

## Scope Boundaries

- **Out of scope**: the `usage_events` schema migration and live writer — that is ENH-2721, which this issue is blocked on.
- **Out of scope**: per-iteration `diff_stall`/`score_stall` discard tracking — an explicit follow-on, not required for a terminal-status waste view.
- **In scope**: `waste_attribution()` query function, the `ll-ctx-stats` waste report section, and fixing `ctx_stats.py`'s existing `resolve_history_db()` bypass.

## Acceptance Criteria

- [x] `waste_attribution()` returns per-loop totals: tokens_total, tokens_wasted, waste_pct, run counts.
- [x] CLI view lists top wasteful loops with `--json` support.
- [x] Read-only: no writes/deletes against history.db.
- [x] `ctx_stats.py` routes through `resolve_history_db()` instead of its local `DEFAULT_DB_RELPATH`.
- [x] Documented definition of "wasted" with its known limitations (terminal-status only, no per-iteration discard tracking yet).

## Integration Map

### Files to Modify
- `scripts/little_loops/history_reader.py` — add `waste_attribution()`, modeled on `cost_attribution()` (line 854) and `aggregate_loop_runs()` (line 1550)
- `scripts/little_loops/cli/ctx_stats.py` — add `_aggregate_waste()` (following `_aggregate_mcp_health()`, line 169) and a report section; fix the `resolve_history_db()` bypass (line 36)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/history.py:245,262,299,316` — reference implementation for the `resolve_history_db()` fix
- `scripts/little_loops/cli/loop/info.py:1161,1217` (`cmd_diagnose_evaluators()`, `cmd_calibrate_budget()`) — related but separate waste-adjacent tooling (evaluator health, not token cost); no code change needed, worth cross-referencing in docs

### Similar Patterns
- `history_reader.py:854` `cost_attribution()` — token-sum rollup with whitelisted `GROUP BY`
- `history_reader.py:1550` `aggregate_loop_runs()` — outcome rollup by `loop_name`/`terminated_by`
- `history_reader.py:739,789` `mcp_server_usage()` / `mcp_failure_rate()` — `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` success/failure rollup shape, closest existing analog to a waste-percentage calculation

### Tests
- `scripts/tests/test_history_reader.py` — `TestCostAttribution` (lines 92-181) and `test_aggregate_loop_runs` (~line 1786) are the fixture-seeding templates; `TestMissingDatabase`/`TestEmptyTables` (lines 29-89) for the never-raise contract. New `TestWasteAttribution` class mirroring the same shape.
- `scripts/tests/test_cli_ctx_stats.py` — `test_json_mode` / `test_json_mode_skill_health_present` (lines 282-366) for CLI-level `--json` assertions
- New test gap: `test_cli_ctx_stats.py` has no test that sets `LL_HISTORY_DB` env or `history.db_path` config with no `--db` flag — this is the regression proof for the `resolve_history_db()` fix; it fails today and passes once `ctx_stats.py` routes through `resolve_history_db()`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh_2511_mcp_telemetry.py:310-423` — `test_mcp_server_usage_success_rate`/`test_mcp_failure_rate`/their missing-db companions are the only existing ratio-computation test template in the codebase (`cost_attribution()`'s `TestCostAttribution` tests sums, not a `x/y if y else None` percentage guard) — `TestWasteAttribution`'s `waste_pct` divide-by-zero test should follow this file's shape, not `TestCostAttribution`'s [Agent 3 finding]
- Note: `mcp_server_usage()`/`mcp_failure_rate()` (`history_reader.py:746-844`, the issue's own cited closest structural analogs) have no unit test class inside `test_history_reader.py` itself — the ratio-test template lives only in `test_enh_2511_mcp_telemetry.py` [Agent 1/3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — line numbers re-verified against current source:_

- `test_aggregate_loop_runs()` is now at `test_history_reader.py:1805` (not ~1786).
- `TestCostAttribution._seed()` (`test_history_reader.py:92-201`) is the concrete fixture template: builds raw row tuples with a `# (col, col, ...)` header comment, `conn.executemany(...)`, `conn.commit()`; includes a dedicated `test_unsupported_group_by_raises` test feeding a SQL-injection string as `group_by` — `TestWasteAttribution` should include the equivalent injection-safety test if `waste_attribution()` exposes a `group_by` parameter.
- `test_json_mode_skill_health_present()` / its "absent" companion in `test_cli_ctx_stats.py` show the present/absent pairing convention every optional report section follows — `waste` section tests should follow the same present-when-rows-exist / `None`-or-absent-when-not pairing.

### Documentation
- `docs/reference/API.md` — `history_reader.py` module reference section needs a `waste_attribution()` entry
- `docs/ARCHITECTURE.md` — note the waste view as a consumer of ENH-2721's `run_id` join
- `docs/reference/CLI.md` (`### ll-ctx-stats`, lines 270-289) — new "waste" JSON-key/section
- `commands/help.md:300` — one-line `ll-ctx-stats` description, cosmetic update only

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/writers.py:92` — a second one-line `ll-ctx-stats` description (scaffolded into new projects' `CLAUDE.md` by `ll-init`), near-identical wording to `commands/help.md:300` — same cosmetic update, easy to miss since it's generated-output rather than hand-maintained docs [Agent 2 finding]

### Configuration
- `resolve_history_db()` (`session_store.py:179`) — only config-path touchpoint, to fix `ctx_stats.py`'s existing bypass

## Impact

- **Priority**: P2 — cheap to build once unblocked, potentially reorders remaining token-cost work.
- **Effort**: Small (~100 LOC + tests).
- **Risk**: Low — read-only analytics; the only dependency is ENH-2721's `run_id` column landing first.

## Resolution

Implemented `waste_attribution()` in `history_reader.py` (equi-join on
`usage_events.run_id = loop_runs.run_id`, GROUP BY `loop_name`, two-part
wasted predicate per the refine-issue findings). Wired a "Waste" section into
`ll-ctx-stats` (`_aggregate_waste()`, human-readable + `--json`), and fixed the
`resolve_history_db()` bypass in `main_ctx_stats()` (was building `db_path`
from a local `DEFAULT_DB_RELPATH` constant, ignoring `LL_HISTORY_DB`/config
overrides when `--db` was not passed). Updated `docs/reference/API.md`,
`docs/reference/CLI.md`, `docs/ARCHITECTURE.md`, `commands/help.md`, and
`scripts/little_loops/init/writers.py:92`. All 5 acceptance criteria met;
full suite (15907 passed, 38 skipped), ruff, and mypy all green.

## Status

**Done** | Created: 2026-07-21 | Priority: P2 | Completed: 2026-07-23


## Session Log
- `/ll:manage-issue` - 2026-07-23T03:02:18Z - `a653f25c-1f69-40f3-8205-29eb79b88865.jsonl`
- `/ll:ready-issue` - 2026-07-23T02:48:50 - `2dffd25a-5dd0-4e06-8b1e-3cc8a16696f6.jsonl`
- `/ll:confidence-check` - 2026-07-22T00:00:00Z - `7c2b58e8-cb9b-4f18-ab40-cca4d3ae19dd.jsonl`
- `/ll:wire-issue` - 2026-07-23T02:45:35 - `28bf6ba0-a081-4b51-9dc0-e703372b828a.jsonl`
- `/ll:refine-issue` - 2026-07-23T02:38:11 - `ca74b558-3cd3-478c-8b80-027a7de11a84.jsonl`
