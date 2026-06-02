---
id: FEAT-1624
type: FEAT
priority: P4
status: done
completed_at: 2026-05-23T02:10:05Z
parent: EPIC-1626
depends_on:
- FEAT-1623
relates_to:
- FEAT-1160
- FEAT-1623
- FEAT-1625
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1624: ctx-stats CLI Command — `ll-ctx-stats` Implementation and Tests

## Summary

Create the `ll-ctx-stats` standalone CLI command that queries FEAT-1112's SQLite session store and displays context window savings metrics: bytes processed vs bytes entered into context, per-tool breakdown, prompt cache metrics, estimated session time gained, and compact count.

## Parent Issue
Decomposed from FEAT-1160: Context Window Analytics Command

## Scope
Covers Implementation Steps 3, 4, 5, 15 from FEAT-1160. Requires FEAT-1623 (data layer) to be merged first.

## Expected Output

```
Without savings:  |########################################| 480 KB in conversation
With savings:     |#########                               |  98 KB in conversation

382 KB processed by tools, never entered conversation. (79% reduction)
+6m session time gained.

  read          12 calls     42.1 KB used
  bash          8 calls      18.3 KB used

Cache: 4 hits | 96 KB saved | 5h TTL remaining
```

## Proposed Solution

### Step 3: Create `scripts/little_loops/cli/ctx_stats.py`
Implement `main_ctx_stats(argv=None) -> int` following `doctor.py` pattern (108 lines, argparse + Logger + color output):
- Call `configure_output()` + `Logger(use_color=use_color_enabled())` first
- Use `argparse.ArgumentParser(prog="ll-ctx-stats", formatter_class=argparse.RawDescriptionHelpFormatter)`
- Query SQLite for session totals and per-tool breakdown from FEAT-1623's extended `tool_events` table
- Use `output.py::terminal_width()` to scale the before/after progress bar width
- Use `output.py::format_relative_time()` to render the "+Xm session time gained" line
- Fall back gracefully to `.ll/ll-context-state.json` (token estimates) if SQLite store is absent
- Expose `_parse_args()` as a testable helper (follow `cli/logs.py::_build_parser()` + `_parse_args()` pattern)

### Step 4: Register the CLI entry point
- Add `from little_loops.cli.ctx_stats import main_ctx_stats` + `"main_ctx_stats"` to `__all__` in `scripts/little_loops/cli/__init__.py`
- Add `ll-ctx-stats = "little_loops.cli:main_ctx_stats"` to `[project.scripts]` in `scripts/pyproject.toml` (lines 49–77)

### Step 5: Add `scripts/tests/test_cli_ctx_stats.py`
Follow `test_cli_doctor.py:TestMainDoctor` pattern:
- `patch("sys.argv", ["ll-ctx-stats", ...])`
- Patch SQLite query callables
- Capture `print()` via side-effect list
- Assert return code and output content (percentage reduction, per-tool breakdown presence, cache metrics line)

### Step 15: Additional tests
- `scripts/tests/test_session_store.py` — new `TestToolEventsByteColumns` class: verify `bytes_in`/`bytes_out`/`cache_hit` are populated when `post_tool_use` handler fires; follow `TestBackfill.test_backfill_tool_events_from_jsonl` + `test_tool_events_reserves_feat1160_columns` pattern
- `scripts/tests/test_config_schema.py` — new `test_analytics_in_schema` method: assert `"analytics" in data["properties"]` with `enabled` sub-property; follow `TestConfigSchema.test_learning_tests_in_schema` (line 120) pattern

## Files to Create/Modify
- `scripts/little_loops/cli/ctx_stats.py` — new file; `main_ctx_stats(argv=None) -> int`
- `scripts/little_loops/cli/__init__.py` — add `from little_loops.cli.ctx_stats import main_ctx_stats` (alongside `main_doctor` import at line 40) + `"main_ctx_stats"` entry in `__all__`
- `scripts/pyproject.toml` — add `ll-ctx-stats = "little_loops.cli:main_ctx_stats"` to `[project.scripts]` after `ll-session` (line 72) and before the `# internal:` comment block
- `scripts/tests/test_cli_ctx_stats.py` — new test file
- `scripts/tests/test_session_store.py` — add `TestToolEventsByteColumns` class
- `scripts/tests/test_config_schema.py` — add `test_analytics_in_schema` method

## Integration Map

### Files to Create
- `scripts/little_loops/cli/ctx_stats.py` — implementation
- `scripts/tests/test_cli_ctx_stats.py` — tests

### Files to Modify
- `scripts/little_loops/cli/__init__.py` — import + `__all__` registration (model after `main_doctor` lines 40, 73); module docstring bullet list (lines 1–31) also enumerates all CLI tools — that bullet is deferred to FEAT-1625 Step 8 but lives in this same file; leave docstring unchanged in FEAT-1624
- `scripts/pyproject.toml` — `[project.scripts]` entry (lines 49–79 block)
- `scripts/tests/test_session_store.py` — add `TestToolEventsByteColumns`
- `scripts/tests/test_config_schema.py` — add `test_analytics_in_schema`

### Existing Infrastructure to Reuse (no changes needed)
- `scripts/little_loops/session_store.py` — `connect(path)`, `recent(db, kind="tool")`, `DEFAULT_DB_PATH = Path(".ll/session.db")`. `connect()` already calls `ensure_db()` internally; columns `bytes_in`/`bytes_out`/`cache_hit` already exist via migration 0.
- `scripts/little_loops/cli/output.py` — `configure_output()` (line 49), `use_color_enabled()` (line 92), `terminal_width(default=80)` (line 16), `format_relative_time(seconds)` (line 109), `colorize(text, code)` (line 97)
- `scripts/little_loops/logger.py` — `Logger(use_color=...)` class with `info/success/warning/error/debug/header` methods
- `scripts/little_loops/config/features.py` — `feature_enabled(config_data, "analytics.enabled")` (line 13)
- `scripts/little_loops/hooks/post_tool_use.py` — writes `bytes_in`/`bytes_out`/`cache_hit` when `analytics.enabled: true`; uses `cwd / ".ll/session.db"` as the absolute DB path

### Dependent Files (Callers/Importers after registration)
- After `pyproject.toml` install, the script appears as `ll-ctx-stats` on PATH. No internal Python callers — the function is entry-point invoked only.

### Documentation (deferred to FEAT-1625)
- `.claude/CLAUDE.md`, `README.md` (CLI tool count 28→29), `CONTRIBUTING.md`, `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md` — all handled in sibling FEAT-1625

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_post_tool_use.py` — existing; `TestPostToolUseWithSessionStore` (line 95) covers the **write side** (`bytes_in`/`bytes_out`/`cache_hit` populated after `handle()` fires with `analytics.enabled: true`). Do not duplicate this in the new `TestToolEventsByteColumns` — that class should verify the **read/query side** via `recent(db, kind="tool")`, confirming values survive the round-trip. [Agent 3 finding]

## Implementation Constraints

These are non-obvious gotchas discovered from analyzing the FEAT-1623 hook handler and session_store:

1. **Backfilled rows have NULL byte columns.** `session_store._backfill_tool_events()` inserts `bytes_in=None, bytes_out=None, cache_hit=None` for rows reconstructed from historical JSONL. All aggregation queries MUST filter with `WHERE bytes_in IS NOT NULL` or use `COALESCE(bytes_in, 0)`. Otherwise per-tool byte sums will be skewed by backfilled noise.

2. **`analytics.enabled` defaults to `false`.** `post_tool_use.handle()` is gated on `feature_enabled(config, "analytics.enabled")`. The project's own `.ll/ll-config.json` does not currently set this flag, so live data only flows when a user opts in. The graceful fallback to `.ll/ll-context-state.json` is the **expected normal case** for first-time users, not an edge case.

3. **DB path: absolute, not the bare `DEFAULT_DB_PATH`.** `post_tool_use.handle()` constructs `event.cwd / ".ll/session.db"` (absolute). `ll-ctx-stats` should similarly use `Path.cwd() / ".ll/session.db"` (or accept `--db PATH`) — not the bare relative `DEFAULT_DB_PATH`, which breaks when invoked from a subdirectory.

4. **`format_relative_time()` appends `" ago"`.** The helper is designed for past-tense durations (e.g. `"3m ago"`, `"1h 20m ago"`). For the `"+Xm session time gained"` line, either strip the trailing `" ago"` or write a small local formatter — do not change the shared helper.

5. **`config-schema.json` already contains the `"analytics"` block (lines 1203–1214).** No schema modification is needed. The block has `enabled: boolean`, `default: false`, `additionalProperties: false`. `test_analytics_in_schema` will pass immediately on write. [Wiring pass confirmed — Agent 2 finding]

6. **`bytes_out` and `result_size` carry the same value.** The hook writes `bytes_out = result_size = len(json.dumps(tool_response))`. Prefer reading `bytes_out` (the FEAT-1160-reserved column) over `result_size` for forward-compatibility.

7. **`connect()` returns rows with `row_factory = sqlite3.Row`.** Column-name access (`row["tool_name"]`) works directly — no manual mapping needed. Caller owns closing the connection (no context manager wrapper).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **CLI structure**: `doctor.py::main_doctor()` (108 lines) is the closest structural analog — inlines argparse without the `_build_parser()`/`_parse_args()` split. Since `ll-ctx-stats` is subcommand-free, the simpler `doctor.py` shape is acceptable; the split (used by `logs.py`/`session.py`) is only needed when tests must construct the parser independently of `main_*()`.
- **Test patterns**: `test_cli_doctor.py::_capture_print()` (line 29) is the reusable helper for capturing `print()` output via `patch("builtins.print", side_effect=...)`. Patch targets must reference where the name is *used* (e.g. `"little_loops.cli.ctx_stats.terminal_width"`), not where it's defined.
- **SQLite test fixtures**: Use pytest `tmp_path` fixture (file-based, not `:memory:`). Pattern from `test_session_store.py::TestEnsureDb.test_tool_events_reserves_feat1160_columns`: `ensure_db(db)` then `conn.execute("PRAGMA table_info(tool_events)")` to verify columns.
- **No existing progress-bar primitive**: The codebase has no `|####  |` bar renderer. Closest analogs are header-fill rules in `cli/loop/info.py:749` and `cli/sprint/show.py:49` (which use `─` * computed width). Implementer will need to write a small inline bar formatter scaled to `terminal_width()`.
- **`pyproject.toml` insertion point**: Exact line is after `ll-session = "little_loops.cli:main_session"` (line 72) and before the `# internal: dev tooling` comment — keeps user-facing tools grouped above the dev-only block.

## Acceptance Criteria
- [ ] `ll-ctx-stats` command is installable and runnable
- [ ] Displays total bytes processed vs bytes entered into context with percentage reduction
- [ ] Per-tool breakdown (call count, bytes used per tool) is shown
- [ ] Prompt cache metrics (hit count, bytes saved) are shown
- [ ] Estimated session time gained is shown using `format_relative_time()`
- [ ] Compact count is reported when available
- [ ] `test_cli_ctx_stats.py` tests pass (≥3 test cases)
- [ ] `test_session_store.py::TestToolEventsByteColumns` passes
- [ ] `test_config_schema.py::test_analytics_in_schema` passes
- [ ] Graceful fallback when SQLite store is absent

## Similar Patterns
- `scripts/little_loops/cli/doctor.py` — 108-line standalone command with argparse, Logger, color
- `scripts/little_loops/cli/logs.py` — `_build_parser()` + `_parse_args()` testable helper pattern
- `scripts/little_loops/cli/output.py::terminal_width()` and `format_relative_time()`
- `scripts/tests/test_cli_doctor.py` — test pattern with `patch("sys.argv")` and side-effect list

## Resolution

Implemented `ll-ctx-stats` standalone CLI command per the proposed solution. Module
`scripts/little_loops/cli/ctx_stats.py` aggregates `tool_events` byte columns
written by the FEAT-1623 hook, renders a before/after progress bar scaled to
`terminal_width()`, a per-tool breakdown, cache metrics, and an estimated
session-time-gained line (using a local `_time_gained()` wrapper that strips
`format_relative_time()`'s trailing ` ago`). NULL byte columns from backfilled
rows are filtered out. Falls back to `.ll/ll-context-state.json` when the
SQLite store is absent. Entry point registered in `cli/__init__.py` and
`pyproject.toml`. 21 new tests pass; full suite shows only one pre-existing
unrelated failure (`test_feat1287_doc_wiring.py`).

## Session Log
- `/ll:manage-issue` - 2026-05-23T02:10:05Z
- `/ll:wire-issue` - 2026-05-23T01:59:56 - `227ff552-97da-4235-9dfd-1118f2e84058.jsonl`
- `/ll:refine-issue` - 2026-05-23T01:54:13 - `4fc33475-b1d3-4eef-921f-60c38ed6a611.jsonl`
- `/ll:issue-size-review` - 2026-05-22T00:00:00 - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:confidence-check` - 2026-05-22T00:00:00 - `10d30c66-69fd-433a-8be8-9968a140a16b.jsonl`

---

## Status
**Done** | Created: 2026-05-22 | Completed: 2026-05-23 | Priority: P4
