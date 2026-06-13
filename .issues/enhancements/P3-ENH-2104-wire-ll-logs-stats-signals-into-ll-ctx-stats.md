---
id: ENH-2104
title: Wire `ll-logs stats` signals into `ll-ctx-stats`
type: ENH
priority: P3
status: open
captured_at: "2026-06-12T00:00:00Z"
discovered_date: 2026-06-12
discovered_by: review-epic
parent: EPIC-1918
relates_to: [ENH-1921]
labels:
  - telemetry
  - ll-logs
  - ctx-stats
  - integration
decision_needed: false
---

# ENH-2104: Wire `ll-logs stats` signals into `ll-ctx-stats`

## Summary

Extend `ll-ctx-stats` to report skill-health signals — correction rate and
skill/command invocation frequency — sourced from `ll-logs stats --json`, so
the per-tool context-savings analysis and the telemetry layer surface in a
single command.

## Current Behavior

`ll-ctx-stats` reports per-tool context-savings analysis only. The `ll-logs
stats --json` output — correction rate and per-skill/command invocation
frequency (built in ENH-1921) — is not consumed by any analytics-facing
command; the data exists in the log index but is not surfaced alongside context
savings.

## Expected Behavior

`ll-ctx-stats` surfaces skill-health signals (per-skill invocation frequency
and correction rate) alongside existing context-savings analysis, sourced from
`ll-logs stats --json`. When `ll-logs` data is unavailable (no session logs,
empty index), the skill-health section is omitted gracefully with a notice;
exit code is unchanged.

## Motivation

EPIC-1918's scope section names `ll-ctx-stats` as an integration consumer
target ("Integration wiring into existing consumers: loop-suggester,
create-eval-from-issues/ll-harness, find-dead-code, ll-ctx-stats"), but no
child issue covers it. ENH-1921 (done) built the `stats` subcommand that
produces the data; nothing consumes it from the analytics side.

## Acceptance Criteria

- [ ] `ll-ctx-stats` gains a section (or `--with-skill-health` flag) showing
  per-skill invocation frequency and correction-rate signals from
  `ll-logs stats --json`
- [ ] Graceful degradation when `ll-logs` data is unavailable (no session
  logs, empty index) — section is omitted with a notice, exit code unchanged
- [ ] Output documented in the CLI `--help` text and the relevant guide
- [ ] Tests cover the merged output and the degradation path

## Scope Boundaries

- **In scope**: New output section or `--with-skill-health` flag in `ll-ctx-stats`; graceful degradation when log data is absent; `--help` text and guide documentation updates; tests for merged output and degradation path
- **Out of scope**: Changes to `ll-logs stats` output format or schema; new standalone CLI tools; modifying existing context-savings logic; changes to any other EPIC-1918 child issues

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/ctx_stats.py` (or equivalent module) — consume
  `ll-logs stats --json`

### Dependent Files (Callers/Importers)
- No external callers of `main_ctx_stats()` beyond the entry point in `scripts/pyproject.toml:78`
- `_aggregate_skill_stats()` in `scripts/little_loops/cli/logs.py` — the function to import; also called internally by `_cmd_stats()` and `_cmd_dead_skills()` in the same module

### Similar Patterns
- `ll-logs stats --json` output shape (ENH-1921)
- Existing graceful-degradation guards in history.db consumers

### Tests
- `scripts/tests/test_cli_ctx_stats.py` — `TestMainCtxStats` — add new test cases here (see Implementation Steps); existing tests use `in output` checks and are tolerant of additive output — no existing test will break [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- **Extend** `TestMainCtxStats.test_json_mode()` — add assertion `"skill_health" in data` when skill events present; `data.get("skill_health") is None` when not [Agent 3 finding]
- **Helpers to copy** from `scripts/tests/test_ll_logs.py` into `test_cli_ctx_stats.py` (cannot import cross-test-file):
  - `_populate_skill_events(db_path, rows: list[tuple[str, str, str, str]])` at line 1395 — seeds `skill_events` table
  - `_insert_correction(db_path, ts, session_id, content)` at line 1413 — seeds `user_corrections` table
- `scripts/tests/test_wiring_cli_registry.py` — already asserts `"ll-ctx-stats"` string presence in `commands/help.md`, `docs/reference/CLI.md`, `.claude/CLAUDE.md`; no changes needed unless string is removed [Agent 1 finding]

### Documentation
- CLI `--help` text for `ll-ctx-stats`
- Relevant guide (e.g., `docs/guides/` or `CLAUDE.md` CLI entry for `ll-ctx-stats`)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### main_ctx_stats` section (line 3632+) documents the entry-point function; update to describe new skill-health aggregation call and output shape [Agent 2 finding]
- `commands/help.md` — one-liner `"ll-ctx-stats      Show context-window analytics…"`; update to mention skill-health signals [Agent 2 finding]
- `scripts/little_loops/init/writers.py` — CLAUDE.md template at line 89 contains the same one-liner written to new projects during `ll-init`; needs the same description update as `.claude/CLAUDE.md` [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Key functions to modify in `scripts/little_loops/cli/ctx_stats.py`:**
- `_build_parser()` — add `--with-skill-health` flag (`action="store_true", default=False`) **or** omit flag for always-on behavior
- `_render()` — append skill-health section after the cache-summary block (currently the final block in `_render()`)
- `_print_json()` — add `"skill_health": [...]` key (or `None`) to the `payload` dict when `source == "sqlite"`
- `main_ctx_stats()` — call `_aggregate_skill_stats(db_path)` after `db_path` is resolved; the same `.ll/history.db` path serves both `tool_events` and `skill_events`

**Import to add in `ctx_stats.py`:**
- `from little_loops.cli.logs import _aggregate_skill_stats`
  (already cross-module-imported in `scripts/tests/test_ll_logs.py`, establishing the precedent)

**Degradation guard to replicate (from `_aggregate_tool_events()` pattern):**
- `_aggregate_skill_stats()` returns `None` (DB absent/schema broken) or `{}` (DB exists, no skill rows) — both cases omit the section; emit a `logger.info()` notice per the `_render_fallback()` pattern in `ctx_stats.py`

**Concrete similar patterns:**
- `_aggregate_tool_events()` in `ctx_stats.py` — the `None`/empty-dict/populated-dict degradation shape to replicate exactly
- `_cmd_stats()` JSON serialization in `logs.py` (lines 1176–1193) — `{"skill", "invocations", "corrections", "correction_rate", "errors", "error_rate"}` row shape; re-use directly in `_print_json()`
- `--effort` flag in `scripts/little_loops/cli/history_context.py` — closest codebase analog to a boolean flag that gates an optional output section

**Test helpers already available:**
- `_populate_skill_events(db_path, rows)` in `scripts/tests/test_ll_logs.py` — seed `skill_events` table
- `_insert_correction(db_path, ...)` in `scripts/tests/test_ll_logs.py` — seed `user_corrections` table
- `_populate_tool_events(db_path, rows)` in `scripts/tests/test_cli_ctx_stats.py` — seed `tool_events` table (existing helper, line 29)
- `TestMainCtxStats` in `scripts/tests/test_cli_ctx_stats.py` — add new test cases here

## Implementation Steps

1. Read `ll-logs stats --json` output from `ctx_stats.py` (subprocess or import)
2. Add a skill-health section (or `--with-skill-health` flag) to the `ll-ctx-stats` report
3. Implement graceful degradation when `ll-logs` data is unavailable or the index is empty
4. Update `--help` text and the relevant guide with the new output section
5. Write tests covering merged output and the degradation path

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> **Selected:** Option A — Always-on skill-health section — exactly mirrors the existing `_aggregate_tool_events` unconditional-call + conditional-render pattern; no new flag needed.

**Option A — Always-on skill-health section (simpler, no new flag):**
1. Add `from little_loops.cli.logs import _aggregate_skill_stats` to imports in `ctx_stats.py`
2. In `main_ctx_stats()`, after resolving `db_path`, call `skill_stats = _aggregate_skill_stats(db_path)` (no extra args needed for default behavior)
3. Pass `skill_stats` to `_render()` and `_print_json()`; in `_render()` after the cache-summary block: `if skill_stats: <print ranked rows>; elif skill_stats is not None: logger.info("No skill events recorded yet.")`
4. In `_print_json()`, add `"skill_health": [<row dicts>] if skill_stats else None` to the `payload`

**Option B — `--with-skill-health` opt-in flag:**
1–2. Same import and aggregation, but gated: in `_build_parser()` add `parser.add_argument("--with-skill-health", action="store_true", default=False)`, and call `_aggregate_skill_stats` only when `args.with_skill_health` is set
3. **Note**: no `--with-*` flags exist anywhere in the codebase currently; this would be the first instance of the pattern

**Test cases to add in `TestMainCtxStats` (`scripts/tests/test_cli_ctx_stats.py`):**
- Merged-output path: seed `tool_events` (via `_populate_tool_events`) and `skill_events` (copy `_populate_skill_events` helper from `test_ll_logs.py`); assert skill-health section appears in stdout
- Degradation — no skill rows: seed only `tool_events`, empty `skill_events`; assert skill-health section absent and exit code is 0
- Degradation — no DB: `tmp_path` with no `.ll/`; assert exit code unchanged at 1
- JSON output: `["ll-ctx-stats", "--json"]`; assert `payload["skill_health"]` key present when data available, `None` or absent when not

**Documentation targets:**
- `docs/reference/CLI.md` at `### ll-ctx-stats` (line 251+) — add flag description and example output
- `.claude/CLAUDE.md` CLI list entry for `ll-ctx-stats` — add note about skill-health signals

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-13.

**Selected**: Option A — Always-on skill-health section (simpler, no new flag)

**Reasoning**: Option A exactly mirrors the existing `_aggregate_tool_events()` unconditional-aggregation + conditional-render pattern in `ctx_stats.py` (lines 278, 198–211). Grep confirms zero `--with-*` flags exist anywhere in `scripts/` — Option B would introduce the first-ever instance of that naming convention for no benefit, since `_aggregate_skill_stats` reads from the same `.ll/history.db` already being queried. Reuse of existing helpers (`_populate_skill_events` in `test_ll_logs.py:1395`, `_aggregate_skill_stats` already cross-module-imported in `test_ll_logs.py:16`) is direct with Option A.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/API.md` `### main_ctx_stats` section — describe new skill-health aggregation call, output shape, and degradation behavior
7. Update `commands/help.md` one-liner for `ll-ctx-stats` — mention skill-health signals alongside context savings
8. Update `scripts/little_loops/init/writers.py` CLAUDE.md template (line 89) — same one-liner update as `.claude/CLAUDE.md` so new projects initialized via `ll-init` get the accurate description
9. Copy `_populate_skill_events` and `_insert_correction` helpers into `test_cli_ctx_stats.py`; extend `TestMainCtxStats.test_json_mode` with `skill_health` key assertion

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (always-on) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (`--with-skill-health`) | 1/3 | 2/3 | 3/3 | 2/3 | 8/12 |

**Key evidence**:
- Option A: `_aggregate_tool_events()` called unconditionally at `ctx_stats.py:278`; `_aggregate_skill_stats` already imported cross-module in `test_ll_logs.py:16`; `_populate_skill_events` helper at `test_ll_logs.py:1395`
- Option B: `grep --with-` returns zero matches in `scripts/` — no precedent; would be first `--with-*` flag in the codebase

## Impact

- **Priority**: P3 — closes a named consumer-target gap in EPIC-1918
- **Effort**: Small — JSON merge into an existing report
- **Risk**: Low — additive output section
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-12 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-06-13T14:17:09 - `bb95cdb9-2fae-4775-ad2d-2ee497cc504b.jsonl`
- `/ll:decide-issue` - 2026-06-13T14:13:57 - `9aaae9fc-d0da-4b2b-80af-8f24ea621c5f.jsonl`
- `/ll:refine-issue` - 2026-06-13T14:07:15 - `08370739-55b2-494f-8c11-f2199b52c4f3.jsonl`
- `/ll:format-issue` - 2026-06-12T19:18:07 - `2606c3f7-295a-4177-a5bc-08603aa89e55.jsonl`
