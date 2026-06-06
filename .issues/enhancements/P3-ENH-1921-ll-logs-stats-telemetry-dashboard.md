---
id: ENH-1921
title: 'll-logs stats: skill frequency/error/correction telemetry'
type: ENH
priority: P3
status: done
captured_at: '2026-06-04T02:27:34Z'
completed_at: '2026-06-06T01:47:12Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1918
relates_to:
- EPIC-1918
- ENH-1922
labels:
- captured
- ll-logs
- telemetry
decision_needed: false
confidence_score: 96
outcome_confidence: 77
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 23
---

# ENH-1921: ll-logs stats — skill frequency / error / correction telemetry

## Summary

Add `ll-logs stats` to aggregate, across the log corpus, per-skill invocation
frequency, failure rate, and correction rate — a quality dashboard for the ll
skill/command catalog.

## Current Behavior

There is no aggregate view of how often each ll skill is invoked, how often its
invocation is followed by a failure or user correction, or which skills dominate
real usage. `ll-ctx-stats` covers context bytes but not invocation/quality.

## Expected Behavior

`ll-logs stats [--project DIR|--all] [--window-days D] [--sort freq|errors|corrections] [--json]`
prints a table: skill/command, invocation count, error count/rate, correction
count/rate, and (optionally) median cost via `ll-ctx-stats` join.

## Motivation

Surfaces which skills are heavily used vs. ignored, and which produce the most
failures or corrections — directing refinement effort where it matters and
feeding dead-skill detection (ENH-1923).

## Proposed Solution

Add `stats` to `cli/logs.py` reusing the shared ll-invocation extractor
(ENH-1919). Count invocations per skill; consume per-invocation failure
classifications from ENH-1922's `scan-failures` output (do not independently
detect failures); attribute corrections by reusing `is_correction()` from
`session_store.py`. Optionally join `ll-ctx-stats` for cost.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option A — JSONL-first (mirrors `_cmd_sequences()`)**: Walk the JSONL corpus via `_extract_ll_event_streams()` already in `logs.py`; derive invocation counts from the resulting `Counter[str]`; within each session, walk the full JSONL to find `user` records adjacent (within ~30 s) to each invocation and apply `is_correction()` from `session_store.py` for correction attribution. Consistent with how `sequences` works; needs no DB.

**Option B — SQLite-first (mirrors `ctx_stats._aggregate_tool_events()`)**: Query `skill_events` in `.ll/history.db` (schema: `ts TEXT, session_id TEXT, skill_name TEXT, args TEXT`; populated live by `hooks/user_prompt_submit.py:handle()` via `record_skill_event()`) for invocation counts grouped by `skill_name`; join `user_corrections` by `session_id` + timestamp proximity for correction rate. Simpler and faster but limited to sessions where the `user_prompt_submit` hook was active; fall back gracefully if DB absent.

> **Selected:** Option B — SQLite-first — directly reuses `_aggregate_tool_events()` template, `skill_events` DB infrastructure, and `_populate_tool_events()` test fixture shape (10/12 vs 8/12).

**ENH-1922 dependency (blocking error-rate column)**: `scan-failures` is `open`, its classified output does not yet exist. The `Errors`/`Error%` columns should output `N/A` or be omitted until ENH-1922 is complete; do not independently re-detect failures.

**Output primitives already exist — no new utilities needed**: `output.table()` renders box-drawn tables with auto column widths; `print_json()` emits indented JSON; `add_json_arg()` from `cli_args.py` attaches `--json`/`-j`. `--sort choices=["freq","errors","corrections"]` follows the `issues/__init__.py` argparse pattern.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-05.

**Selected**: Option B — SQLite-first

**Reasoning**: Option B directly reuses the `_aggregate_tool_events()` pattern from `ctx_stats.py` (same connect/guard/aggregate/return shape), the established `skill_events` table populated live by `record_skill_event()`, and the `_populate_tool_events()` test fixture shape from `test_cli_ctx_stats.py` — scoring 3/3 on reuse vs 2/3 for Option A. Option A requires a new second JSONL pass with per-event proximity-window logic for correction attribution (no existing helper), and `_extract_ll_event_streams()` strips `user`-type records, making a separate scan unavoidable.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — JSONL-first | 2/3 | 1/3 | 2/3 | 3/3 | 8/12 |
| Option B — SQLite-first | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: `_cmd_sequences()` is a structural template but correction attribution requires a new second JSONL pass; `_extract_ll_event_streams()` strips `user`-type records so a separate scan is unavoidable.
- Option B: `_aggregate_tool_events()` in `ctx_stats.py` is the direct copy-and-adapt template; `skill_events` is actively populated by the live hook; `_populate_tool_events()` in `test_cli_ctx_stats.py` is the exact fixture helper shape. The `analytics.enabled` completeness constraint is already handled by the existing `if not db_path.exists(): return None` guard.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `stats` subparser in `_build_parser()` and dispatch branch in `main_logs()`; implement `_cmd_stats(args, logger)` reusing `_extract_ll_event_streams()` and `_extract_tool_name()` already in this file

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store.py` — reuse `is_correction()` (lines ~128–152, pure string classifier, no DB access) for correction attribution; `mine_corrections_from_messages()` and `ensure_db()` for SQLite-first approach; `record_skill_event()` writes to `skill_events` table that the SQLite path reads
- `scripts/little_loops/cli/output.py` — use `table()` for box-drawn tabular output, `print_json()` for `--json` mode, `terminal_width()` for column sizing
- `scripts/little_loops/cli_args.py` — use `add_json_arg(parser)` helper for consistent `--json`/`-j` flag
- `scripts/little_loops/cli/ctx_stats.py` — reference `_aggregate_tool_events()` pattern for optional cost-column join from `.ll/history.db`; `_format_bytes()` for cost display

### Similar Patterns
- `scripts/little_loops/cli/logs.py:_cmd_sequences()` — closest handler template: resolves `--project`/`--all`, calls `_extract_ll_event_streams()`, aggregates with `Counter`, outputs via `print_json()` or plain ranked loop
- `scripts/little_loops/cli/ctx_stats.py:_aggregate_tool_events()` — canonical `defaultdict` aggregation from SQLite with `None`-safe DB guard; direct model for Option B (SQLite-first)
- `scripts/little_loops/cli/issues/__init__.py` — `--sort choices=[...]` + `--asc`/`--desc` argparse pattern (lines ~725–769)
- `scripts/little_loops/cli/output.py:table()` — box-drawn table renderer with auto column widths and `…` truncation; use for the skill/count/error/correction stats table

### Tests
- `scripts/tests/test_ll_logs.py` — existing test file (50+ tests, `TestArgumentParsing`, `TestDiscover`, `TestExtract` classes); add `TestStats` class following the same `patch("sys.argv", ["ll-logs", "stats", ...])` + `patch("builtins.print", ...)` + `monkeypatch.chdir(tmp_path)` pattern
- `scripts/tests/test_cli_ctx_stats.py` — reference for `_populate_*` DB fixture helper shape using `ensure_db()` + raw `sqlite3.connect()` to seed `skill_events` rows

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli.py` — `TestMainLogsIntegration` class (line ~2921) already tests `discover`, `tail`, `no_subcommand`; add `test_stats_returns_0` following the `test_discover_returns_0` pattern with `patch("sys.argv", ["ll-logs", "stats", "--all"])` + patched `pathlib.Path.home` [Agent 1 finding]

### Documentation
- `docs/reference/API.md` — add `ll-logs stats` subcommand entry under the `ll-logs` section
- `docs/reference/CLI.md` — add `stats` subcommand section with flags table and examples
- `.claude/CLAUDE.md` — update ll-logs subcommand list (line ~184) to include `stats`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — line ~250 inline comment on `logs.py` currently enumerates `discover/extract/sequences/tail`; add `stats` to the subcommand list [Agent 2 finding]
- `CHANGELOG.md` — add new entry for `ll-logs stats` under the current release section [Agent 2 finding]
- `commands/help.md` — one-liner description at the `ll-logs` entry currently references `sequences` parenthetically; update to mention `stats` as well [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. **Add `stats` subparser** in `_build_parser()` in `scripts/little_loops/cli/logs.py`: add `subparsers.add_parser("stats")`, attach `--project`/`--all`/`--window-days` (copy from `sequences` subparser), `--sort choices=["freq","errors","corrections"] default="freq"` (argparse pattern from `issues/__init__.py`), and `add_json_arg(stats_parser)` from `cli_args.py`.
2. **Implement `_cmd_stats(args, logger)`** in `logs.py` choosing one data strategy (see Proposed Solution options); build `Counter[str]` of invocation counts per skill and a parallel corrections dict.
3. **Failure attribution**: ENH-1922 is not yet implemented; output `N/A` for `Errors`/`Error%` columns or omit them with a `--with-errors` guard until ENH-1922's classified output exists.
4. **Render output** using `output.table()` (from `output.py`) for plain text with headers `["Skill", "Invocations", "Corrections", "Corr%"]` and `print_json()` for `--json` mode; sort by `args.sort` before rendering.
5. **Add dispatch branch** in `main_logs()`: `if args.command == "stats": return _cmd_stats(args, logger)` (before the final `return 1`).
6. **Add `TestStats` class** in `scripts/tests/test_ll_logs.py` using `patch("sys.argv", ["ll-logs", "stats", ...])` + `patch("builtins.print", ...)` + `monkeypatch.chdir(tmp_path)` pattern; seed `skill_events` via `ensure_db()` + `sqlite3.connect()` fixture helper (follow `test_cli_ctx_stats.py:_populate_tool_events()` shape).
7. **Update primary docs**: add `stats` entry in `docs/reference/API.md` under ll-logs and update `docs/reference/CLI.md` with flags table; update `.claude/CLAUDE.md` ll-logs subcommand list.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Add `test_stats_returns_0` in `scripts/tests/test_cli.py` (`TestMainLogsIntegration`) following the `test_discover_returns_0` pattern with `patch("sys.argv", ["ll-logs", "stats", "--all"])` + patched `pathlib.Path.home`
9. Update `docs/ARCHITECTURE.md` line ~250 — add `stats` to the inline comment enumerating `logs.py` subcommands (`discover/extract/sequences/tail` → include `stats`)
10. Add `CHANGELOG.md` entry for `ll-logs stats` under the current release section
11. Update `commands/help.md` `ll-logs` one-liner to mention `stats` alongside `sequences` in the parenthetical description

## Success Metrics

- Output identifies the top-N invoked skills and the top-N by correction rate.

## Scope Boundaries

Out of scope:
- Real-time or live dashboards (batch aggregation only)
- Collecting new session data — reads existing logs via the shared extractor (ENH-1919)
- Automatic remediation of low-quality skills
- Visual/chart output — tabular text + `--json` only
- Non-ll CLI tools; aggregation is scoped to ll skill/command invocations

## API/Interface

`ll-logs stats` — new read-only aggregation subcommand.

## Impact

- **Priority**: P3 — Foundational observability for EPIC-1918; blocks dead-skill detection (ENH-1923) but not critical-path
- **Effort**: Small — adds one subcommand to `cli/logs.py` reusing existing extractors and `is_correction()`
- **Risk**: Low — read-only aggregation; no writes to session data or issue files
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/API.md` (ll-logs, ll-ctx-stats)



---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1922 owns the per-invocation failure-classification layer (detection of nonzero exits, tracebacks, and correction signals) atop ENH-1919's shared extractor. ENH-1921 aggregates failure/correction rates from ENH-1922's classified output rather than re-implementing failure detection. ENH-1919's shared extractor provides the raw event stream without classification.


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Resolution

Implemented `ll-logs stats` subcommand (Option B — SQLite-first) in `scripts/little_loops/cli/logs.py`:
- `_aggregate_skill_stats(db_path, *, window_days)` — queries `skill_events` for invocation counts and joins `user_corrections` by session_id + 30s proximity window for correction attribution
- `_cmd_stats(args, logger)` — resolves project DB paths, merges across projects, renders via `output.table()` or `print_json()`
- `stats` subparser with `--project DIR`/`--all`, `--window-days D`, `--sort {freq,corrections}`, `--json`
- Errors/error-rate columns output `N/A` pending ENH-1922

Added 18 tests in `TestStats` (`test_ll_logs.py`) and `test_stats_returns_0` in `TestMainLogsIntegration` (`test_cli.py`).
Updated `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md`, `.claude/CLAUDE.md`, `commands/help.md`, `CHANGELOG.md`.

## Session Log
- `/ll:manage-issue` - 2026-06-06T01:47:12Z - current-session.jsonl
- `/ll:ready-issue` - 2026-06-06T01:34:40 - `66920665-ccf7-4866-bd24-a9c30d75d4e4.jsonl`
- `/ll:confidence-check` - 2026-06-06T02:00:00Z - `6e81df01-88a4-4631-a7af-5b8d97ab76c3.jsonl`
- `/ll:decide-issue` - 2026-06-06T01:30:34 - `72f3f22c-7917-4ef8-b294-f78df3450def.jsonl`
- `/ll:wire-issue` - 2026-06-06T01:22:39Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:refine-issue` - 2026-06-06T01:17:51 - `8c7006b0-b991-44c4-b8cf-82d918cc21f8.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T20:02:29 - `0860b18c-08b7-4093-862a-cc8046f35aaa.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T05:19:22 - `cd123288-5c07-482f-b424-1eebfea29b6e.jsonl`
- `/ll:format-issue` - 2026-06-04T03:09:55 - `9b934de1-4aab-4e21-b930-1823687cb2b1.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
