---
id: FEAT-1160
type: FEAT
priority: P4
status: done
size: Very Large
discovered_date: 2026-04-18
discovered_by: capture-issue
blocked_by: []
depends_on:
- ENH-1114
relates_to:
- FEAT-1159
- FEAT-1112
- ENH-1114
confidence_score: 95
outcome_confidence: 69
score_complexity: 13
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 18
missing_artifacts: false
decision_needed: false
---

# FEAT-1160: Context Window Analytics Command

## Summary

Add an `ll-ctx-stats` CLI command (not a `/ll:` skill — this needs Python for SQLite queries and computation) that reports context window savings metrics for the current session: bytes processed vs bytes entered into context, per-tool breakdown, prompt cache hits and bytes saved, estimated session time gained, and compact count. Modeled after context-mode's `AnalyticsEngine`/`FullReport` pattern but scoped down to a focused one-shot stats dump (no sandboxing, no web UI, no cross-session memory, no composite scores).

## Current Behavior

little-loops has no visibility into context window usage. There is no way to see how many tokens/bytes were processed by tools vs actually entered the context window, whether prompt cache is being hit, or how long tools are extending the usable session life.

## Expected Behavior

A command (e.g. `ll-ctx-stats`) shows a before/after summary like:

```
Without savings:  |########################################| 480 KB in conversation
With savings:     |#########                               |  98 KB in conversation

382 KB processed by tools, never entered conversation. (79% reduction)
+6m session time gained.

  read          12 calls     42.1 KB used
  bash          8 calls      18.3 KB used

Cache: 4 hits | 96 KB saved | 5h TTL remaining
```

## Use Case

**Who**: A developer running a long Claude Code session with multiple tool invocations

**Context**: Mid-session, after running several commands and code analyses, the developer wants to check whether their context window is filling up unnecessarily

**Goal**: See at a glance which tools are consuming the most context, whether prompt caching is working, and how much session time they've gained

**Outcome**: The developer runs `ll-ctx-stats` and sees a breakdown showing 79% of processed bytes never entered the conversation, giving them confidence to continue without manually compacting

## Acceptance Criteria

- [ ] Running `ll-ctx-stats` displays total bytes processed vs bytes entered into context, with a percentage reduction figure
- [ ] Output includes per-tool breakdown (call count, bytes used per tool)
- [ ] Output includes prompt cache metrics (hit count, bytes saved, TTL remaining)
- [ ] Output includes estimated session time gained
- [ ] Command queries FEAT-1112's SQLite store as the data source (no flat-file `.ll/ll-ctx-stats.json` dependency)
- [ ] Compact count is reported when available

## Motivation

context-mode (github.com/mksglu/context-mode) demonstrates that this class of metrics—bytes kept out, per-tool savings, cache hit rate—is both computable from Claude Code hook data and genuinely useful for understanding session health. little-loops already has hook infrastructure (PostToolUse) that could accumulate these counters. Without this, users have no signal on whether compaction is near or whether large tool outputs are burning context unnecessarily.

## API/Interface

### CLI

```
ll-ctx-stats
```

New standalone `ll-` CLI command (not a `/ll:` skill — skills are markdown prompts and can't run SQLite queries or compute analytics). Follows the project's standard 3-step CLI registration pattern:

1. **Module**: `scripts/little_loops/cli/ctx_stats.py` — `main_ctx_stats(argv=None) -> int` with argparse
2. **Registry**: import + `__all__` entry in `scripts/little_loops/cli/__init__.py`
3. **Entry point**: `ll-ctx-stats = "little_loops.cli:main_ctx_stats"` in `scripts/pyproject.toml` under `[project.scripts]`

Pattern reference: `scripts/little_loops/cli/doctor.py` (109-line standalone command with argparse, Logger, and color output).

### Why CLI, not Skill

Skills (`/ll:ctx-stats` in `commands/` or `skills/`) are markdown prompts. This feature needs to:
- Run parameterized SQLite queries against FEAT-1112's store
- Compute aggregation math (ratios, percentages, per-tool breakdowns)
- Format a terminal table with alignment, truncation, and color

None of these are possible from a markdown skill. The issue title says "Command" — in ll parlance, CLI commands are `ll-<name>` Python entry points, not `/ll:` skills.

### Data Schema (extends FEAT-1112)

Extends the `tool_events` table with per-tool byte-tracking columns:
- `bytes_in` (INTEGER): bytes read by the tool
- `bytes_out` (INTEGER): bytes produced by the tool
- `cache_hit` (BOOLEAN): whether the result was served from prompt cache

## Proposed Solution

Extend FEAT-1112's SQLite + FTS5 store to include per-tool byte columns, then query that store from a new `ll-ctx-stats` CLI command. Approach 1 (PostToolUse hook writing to `.ll/ll-ctx-stats.json`) is out of scope — it re-introduces the fragmentation FEAT-1112 was designed to eliminate.

## Integration Map
### Files to Modify
- `scripts/little_loops/cli/ctx_stats.py` — new file; implement `main_ctx_stats(argv=None) -> int` following `doctor.py` pattern
- `scripts/little_loops/cli/__init__.py` — add `from little_loops.cli.ctx_stats import main_ctx_stats` import and `"main_ctx_stats"` to `__all__`
- `scripts/pyproject.toml` — add `ll-ctx-stats = "little_loops.cli:main_ctx_stats"` under `[project.scripts]` (lines 49–77)
- `scripts/little_loops/hooks/post_tool_use.py` — extend `handle()` to write `bytes_in`/`bytes_out`/`cache_hit` to FEAT-1112's `tool_events` table (currently a no-op: `return LLHookResult(exit_code=0)`)
- `scripts/little_loops/session_store.py` — not yet created; FEAT-1112's artifact; must add `bytes_in INTEGER`, `bytes_out INTEGER`, `cache_hit BOOLEAN` columns to `tool_events` migration

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store.py` — not yet created (FEAT-1112 prerequisite); primary data source for SQLite queries
- `.ll/ll-context-state.json` — interim data source written by `hooks/scripts/context-monitor.sh` PostToolUse hook; full schema (verified 2026-05-22): `{"breakdown": {"bash": N, "read": N, ...}, "estimated_tokens": N, "tool_calls": N, "session_start": "...", "detected_model": "...", "threshold_crossed_at": null|"ISO8601", "handoff_complete": bool, "transcript_baseline_tokens": N}` — token estimates only, not raw bytes; `transcript_baseline_tokens` captures the session baseline before tool calls, which can drive the delta calculation for "bytes kept out"; `threshold_crossed_at`/`handoff_complete` can derive compact count without a separate counter
- `scripts/little_loops/hooks/types.py` — `LLHookEvent` and `LLHookResult` dataclasses required when extending `post_tool_use.py::handle()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/__init__.py` — hook dispatcher; `_dispatch_table()` registers `post_tool_use.handle` and routes the `post_tool_use` intent to it; no modification needed but a key dependency to understand when extending `handle()`
- `hooks/adapters/codex/post-tool-use.sh` — 4-line shim that pipes stdin to `python -m little_loops.hooks post_tool_use`; no modification needed but is the entry point through which `handle()` is invoked in Codex; behavior changes to `handle()` will surface here first

### Similar Patterns
- context-mode `src/session/analytics.ts` — reference implementation for the metrics shape (but scoped down: no sandboxing, no web UI, no cross-session memory, no composite scores)
- `hooks/hooks.json` — existing PostToolUse hooks to extend or add alongside
- `scripts/little_loops/cli/doctor.py` — pattern for simple standalone CLI command (argparse, Logger, color output, `main_*() -> int`)
- `scripts/little_loops/cli/gitignore.py` — pattern for CLI command with shared arg helpers from `cli_args.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/hooks/session_start.py::handle()` — example of a data-producing hook handler returning `LLHookResult(exit_code=0, stdout=payload)`; model for how `post_tool_use.py::handle()` should write byte metrics
- `hooks/scripts/context-monitor.sh::estimate_tokens()` — existing per-tool analytics accumulator that writes `.ll/ll-context-state.json`; `breakdown` dict shape mirrors the per-tool breakdown `ll-ctx-stats` should produce from SQLite queries
- `scripts/little_loops/cli/output.py::terminal_width()` — use for scaling the before/after progress bar width to the terminal
- `scripts/little_loops/cli/logs.py::_build_parser()` + `_parse_args()` — pattern for exposing `_parse_args()` as a testable helper separate from `main_logs()`
- No `import sqlite3` exists anywhere in `scripts/little_loops/` today — FEAT-1112 will introduce the first SQLite dependency
- `scripts/little_loops/cli/output.py::format_relative_time(seconds: float) -> str` — converts seconds to human-readable strings (`"3m ago"`, `"2h 15m ago"`); use this to render the "+6m session time gained" line in the output report (negate the sign convention or pass a positive delta)
- `event.payload` byte extraction for `post_tool_use.handle()`: confirmed payload schema from `test_hook_post_tool_use.py::test_arbitrary_payload_returns_pass` is `{"tool_name": str, "tool_input": dict, "tool_response": dict, "session_id": str}`; compute `bytes_in = len(json.dumps(payload.get("tool_input", {})))`, `bytes_out = len(json.dumps(payload.get("tool_response", {})))`, `cache_hit = bool(payload.get("cache_hit", False))` — `cache_hit` is not in the current test payload, so default to `False` until the host populates it

### Tests
- New file: `scripts/tests/test_cli_ctx_stats.py` — follow `test_cli_doctor.py:TestMainDoctor` pattern: `patch("sys.argv", ["ll-ctx-stats", ...])`, patch SQLite query callables, call `main_ctx_stats()`, assert return code and output
- Reference: `scripts/tests/test_cli_doctor.py` — captures `print()` via side-effect list; asserts `"\n".join(lines)` content

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_post_tool_use.py` — **will break**: `TestPostToolUseBaseline.test_empty_payload_returns_pass` and `test_arbitrary_payload_returns_pass` both assert `result.stdout is None` and `not result.data`; these will fail when `handle()` becomes non-no-op; must update assertions and add `TestPostToolUseWithSessionStore` class covering: successful SQLite write with valid payload, graceful fallback when store is absent/locked, byte fields extracted from `event.payload`
- `scripts/tests/test_hook_intents.py` — **will break**: `TestHooksMainModule.test_dispatch_post_tool_use_happy_path` (line 319) asserts `result.stdout == ""` and `result.stderr == ""`; the subprocess assertion will fail once `handle()` emits any output; update to assert the new feedback content or structure
- `scripts/tests/test_feat1504_doc_wiring.py` — **will break**: `TestConfigureAreasWiring.test_authorize_all_count_is_25` (renamed; line 47) hard-codes `"Authorize all 25"` as the assertion string against `skills/configure/areas.md`; both the test method name and the assertion string must be updated to `26` when `ll-ctx-stats` is added (method renames in this file follow the count-bump convention — see prior `_count_is_24` → `_count_is_25` rename)

_Wiring pass (3rd) added by `/ll:wire-issue` 2026-05-22:_
- `scripts/tests/test_ll_logs_wiring.py` — **will break**: `TestConfigureAreasWiring.test_authorize_all_count_is_25` (line 43) also hard-codes `"Authorize all 25"` assertion against `skills/configure/areas.md`; must update to `26` in the same pass as `test_feat1504_doc_wiring.py` — this second occurrence was not identified in prior wiring passes [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — new `test_analytics_in_schema` method needed: asserts `"analytics" in data["properties"]` with `enabled` sub-property; follow `TestConfigSchema.test_learning_tests_in_schema` (line 120) pattern — required because `config-schema.json` uses `additionalProperties: false` [Agent 3 finding]
- `scripts/tests/test_session_store.py` — new `TestToolEventsByteColumns` class: verify `bytes_in`/`bytes_out`/`cache_hit` are populated when `post_tool_use` handler fires; follow `TestBackfill.test_backfill_tool_events_from_jsonl` + `test_tool_events_reserves_feat1160_columns` pattern [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — add `ll-ctx-stats` entry describing flags and output format
- `docs/reference/API.md` — add `main_ctx_stats` reference under `little_loops.cli`

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — **CLI Tools** section lists every `ll-` tool by name; add `ll-ctx-stats` entry to keep the list authoritative
- `README.md` — two occurrences of `28 typed CLI tools` / `28 CLI tools` (lines 46 and 166) must be incremented to `29` (counts re-verified 2026-05-22 — other recent work has already bumped these from the previously documented `27 → 28`)
- `CONTRIBUTING.md` — package structure tree (~line 188) explicitly lists individual `cli/*.py` files (e.g. `doctor.py`, `deps.py`); add `ctx_stats.py` to keep it consistent
- `scripts/little_loops/cli/__init__.py` — module-level docstring (lines 1–30) is a hand-maintained list of all tools with one-line descriptions; add `ll-ctx-stats` bullet to match the other entries
- `commands/help.md` — CLI TOOLS block (begins at line 239, runs through ~line 268) maintains a hand-enumerated table of `ll-*` commands with one-line descriptions; add `ll-ctx-stats` entry; `test_feat1504_doc_wiring.py` establishes the precedent that a parallel wiring test should verify presence here
- `skills/configure/areas.md` — line 823 contains `"Authorize all 25 ll- CLI tools"` plus an inline exhaustive list of all tool names; increment count to `26` and add `ll-ctx-stats` to the inline list (count re-verified 2026-05-22 — already bumped from `24 → 25` by other recent work)
- `skills/init/SKILL.md` — two blocks (lines ~502–522 and ~583–619) contain hard-coded `Bash(ll-*:*)` allow-list entries; both end with `Bash(ll-doctor:*)` as the last entry; add `"Bash(ll-ctx-stats:*)"` and a narrative list entry to both blocks
- `docs/development/TROUBLESHOOTING.md` — **review needed**: document mentions the hook dispatch mechanism; if any section describes `post_tool_use` as a no-op, update prose to reflect the new byte-tracking behavior

_Wiring pass (3rd) added by `/ll:wire-issue` 2026-05-22:_
- `hooks/adapters/codex/post-tool-use.sh` — lines 7 and 12 contain inline comments describing the handler as "a no-op" and claiming "≤200ms p95" based on no-op behavior; update both when `handle()` becomes non-no-op [Agent 2 finding]
- `hooks/adapters/opencode/index.ts` — line 75 comment "the handler is a no-op baseline today" — update when handler becomes active [Agent 2 finding]
- `hooks/adapters/codex/README.md` — line 84 "A no-op handler that returns in ≪200ms p95" — p95 claim based on no-op speed; update latency characterization [Agent 2 finding]
- `hooks/adapters/opencode/README.md` — lines 46–49 and 111 describe "observational-only semantics" and zero observable output; update when handler writes to SQLite [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — footnote `[^hot]` (lines 32–40) — "fire-and-forget is achieved through handler speed (no-op p95 well below the timeout)"; update latency characterization after SQLite writes are added [Agent 2 finding]

### Configuration
- `.ll/ll-config.json` — may need `analytics.enabled` flag

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — schema uses `"additionalProperties": false` at the top level; if `analytics.enabled` is implemented, a new `"analytics"` property block must be added to the top-level `properties` object or config validation will reject it; coordinate with `ll-config.json` default value
- `templates/generic.json`, `templates/python-generic.json` (and all other project-type templates) — all templates reference `config-schema.json` via `"$schema"`; if `analytics.enabled` is added to the schema, add `"analytics": {"enabled": false}` to each template for consistency; pattern reference: `"context_monitor": {"enabled": true}` in existing templates

_Wiring pass (3rd) added by `/ll:wire-issue` 2026-05-22 — explicit template enumeration (all 9 project templates confirmed via Agent 1):_
- `templates/javascript.json` — add `"analytics": {"enabled": false}` beside `context_monitor`
- `templates/typescript.json` — add `"analytics": {"enabled": false}` beside `context_monitor`
- `templates/go.json` — add `"analytics": {"enabled": false}` beside `context_monitor`
- `templates/java-maven.json` — add `"analytics": {"enabled": false}` beside `context_monitor`
- `templates/java-gradle.json` — add `"analytics": {"enabled": false}` beside `context_monitor`
- `templates/rust.json` — add `"analytics": {"enabled": false}` beside `context_monitor`
- `templates/dotnet.json` — add `"analytics": {"enabled": false}` beside `context_monitor`

_Clarification added by `/ll:refine-issue` 2026-05-22:_
- The `analytics.enabled` flag governs the `post_tool_use.py` byte-tracking hook extension (step 2), **not** the `ll-ctx-stats` CLI command itself (which is already opt-in by invocation). Follow the `context_monitor.enabled` guard pattern in `hooks/scripts/context-monitor.sh` (line ~19: `ll_feature_enabled "context_monitor.enabled"`) — add an analogous guard in `post_tool_use.py::handle()` that skips SQLite writes when `analytics.enabled: false`. Recommendation: **include the flag** — it gives users a way to disable byte tracking if the SQLite write adds latency without requiring hook removal. The flag addition to `config-schema.json` is then a required step, not optional, making implementation step 9 unconditional.

_State re-verification added by `/ll:refine-issue` 2026-05-22 (post-FEAT-1112 landing):_
- **VERIFIED**: `scripts/little_loops/session_store.py:513-514` INSERT statement already binds `result_size, bytes_in, bytes_out, cache_hit)` — the migration step is fully in place; Implementation Step 1 reduces to verifying the column types match the analytics computation needs (no further migration work expected).
- **VERIFIED**: `scripts/little_loops/hooks/post_tool_use.py` is still the 24-line no-op (`return LLHookResult(exit_code=0)`); the handler docstring at lines 1-14 explicitly cites FEAT-1489 as the wiring point and identifies "audit logging, token budgeting, rate-limit enforcement" as the intended future consumers — this issue is one of those consumers, so the implementation should preserve the docstring's framing.
- **VERIFIED**: `scripts/little_loops/cli/output.py::terminal_width()` (line 16) and `format_relative_time()` (line 109) both exist as documented.
- **VERIFIED**: `scripts/little_loops/cli/doctor.py` is 108 lines (matches the "~109-line" claim) and confirms the argparse + Logger + `main_doctor() -> int` pattern is current.
- **VERIFIED**: `scripts/tests/test_hook_post_tool_use.py:24-35` `TestPostToolUseBaseline.test_empty_payload_returns_pass` and `test_arbitrary_payload_returns_pass` exist; their assertions will indeed break when `handle()` becomes non-no-op.
- **VERIFIED**: `scripts/tests/test_hook_intents.py:342` asserts `result.stdout == ""` inside `test_dispatch_post_tool_use_happy_path` (declared at line 319).
- **DEPENDENCY REASSESSMENT — ENH-1114**: The earlier confidence-check note characterizes ENH-1114 as "FTS5 intent-ranking indexing" but the current ENH-1114 title is "Intent Parameter for Large ll-* CLI Outputs" (`.issues/enhancements/P4-ENH-1114-intent-parameter-for-large-ll-outputs.md`) — it adds an `--intent <query>` parameter to `ll-history`/`ll-deps`/`ll-scan-*`/`ll-workflows` for filtered output, **not** schema changes to `tool_events`. The historical concern about `tool_events` migration collisions no longer applies. Recommendation: re-evaluate `depends_on: [ENH-1114]` — likely safe to drop, since FEAT-1112's columns are already merged and ENH-1114 touches CLI argument handling rather than the session store schema.

## Implementation Steps

> **Prerequisite**: FEAT-1112 must land first (SQLite + FTS5 store).

1. Add `bytes_in INTEGER`, `bytes_out INTEGER`, `cache_hit BOOLEAN` columns to FEAT-1112's `tool_events` migration in `scripts/little_loops/session_store.py`; coordinate sequentially with ENH-1114 (both target the same migration framework)
2. Extend `scripts/little_loops/hooks/post_tool_use.py::handle()` to write byte metrics per tool call — model on `session_start.py::handle()` which returns `LLHookResult(exit_code=0, stdout=payload)`; input schema from `scripts/little_loops/hooks/types.py::LLHookEvent`
3. Create `scripts/little_loops/cli/ctx_stats.py` with `main_ctx_stats(argv=None) -> int`: call `configure_output()` + `Logger(use_color=use_color_enabled())` first, then `argparse.ArgumentParser(prog="ll-ctx-stats", formatter_class=argparse.RawDescriptionHelpFormatter)`; query SQLite for session totals and per-tool breakdown; use `output.py::terminal_width()` to scale the before/after progress bar
4. Register: add `from little_loops.cli.ctx_stats import main_ctx_stats` + `"main_ctx_stats"` in `scripts/little_loops/cli/__init__.py`; add `ll-ctx-stats = "little_loops.cli:main_ctx_stats"` to `[project.scripts]` in `scripts/pyproject.toml`
5. Add `scripts/tests/test_cli_ctx_stats.py` following `test_cli_doctor.py:TestMainDoctor`: `patch("sys.argv", ["ll-ctx-stats"])`, patch SQLite query callables, capture `print()` via side-effect list, assert return code and output content

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_hook_post_tool_use.py` — adapt `TestPostToolUseBaseline.test_empty_payload_returns_pass` and `test_arbitrary_payload_returns_pass` to reflect new handler behavior (drop `result.stdout is None` / `not result.data` assertions); add `TestPostToolUseWithSessionStore` class covering successful SQLite write, graceful fallback when store absent/locked, and byte field extraction from `event.payload`
7. Update `scripts/tests/test_hook_intents.py` — revise `TestHooksMainModule.test_dispatch_post_tool_use_happy_path` (line 319) to assert the new stdout content instead of `result.stdout == ""`
8. Update docs: add `ll-ctx-stats` to `.claude/CLAUDE.md` CLI Tools list; update `README.md` CLI count (28 → 29, two occurrences); add `ctx_stats.py` to `CONTRIBUTING.md` package structure tree; add `ll-ctx-stats` bullet to `scripts/little_loops/cli/__init__.py` module docstring
9. If `analytics.enabled` flag is implemented: add `"analytics"` property block to `config-schema.json` top-level `"properties"` (required — schema uses `"additionalProperties": false`); also add `"analytics": {"enabled": false}` default to each `templates/*.json` file
10. Update `commands/help.md` — add `ll-ctx-stats` entry to the CLI TOOLS block (begins line 239)
11. Update `skills/configure/areas.md` — change `"Authorize all 25 ll- CLI tools"` to `26` and add `ll-ctx-stats` to the inline tool list (line 823); rename `scripts/tests/test_feat1504_doc_wiring.py::TestConfigureAreasWiring.test_authorize_all_count_is_25` (line 47) to `_count_is_26` and update the assertion string accordingly
12. Update `skills/init/SKILL.md` — add `"Bash(ll-ctx-stats:*)"` to both Bash allow-list JSON array blocks (~lines 502–522 and 583–619) and to both narrative description lists
13. Update adapter no-op language — in the same commit as Step 2 (hook change): update `hooks/adapters/codex/post-tool-use.sh` (lines 7, 12), `hooks/adapters/opencode/index.ts` (line 75), `hooks/adapters/codex/README.md` (line 84), `hooks/adapters/opencode/README.md` (lines 46–49, 111), and `docs/reference/HOST_COMPATIBILITY.md` footnote `[^hot]` (lines 32–40) — replace "no-op" and "no-op p95" language with accurate latency characterization for SQLite-writing handler
14. In same pass as Step 11 (areas.md count bump): update `scripts/tests/test_ll_logs_wiring.py::TestConfigureAreasWiring.test_authorize_all_count_is_25` (line 43) to `_count_is_26` — second test file with the same hardcoded count assertion (parallel to `test_feat1504_doc_wiring.py` Step 11 update)
15. Add `test_config_schema.py::test_analytics_in_schema` and `test_session_store.py::TestToolEventsByteColumns` — write alongside Step 5 tests; follow `TestConfigSchema.test_learning_tests_in_schema` and `TestBackfill.test_backfill_tool_events_from_jsonl` patterns respectively
16. Step 9 template pass covers all 9 project templates explicitly: `generic.json`, `python-generic.json`, `javascript.json`, `typescript.json`, `go.json`, `java-maven.json`, `java-gradle.json`, `rust.json`, `dotnet.json`

## Impact
- **Priority**: P4 - Nice-to-have visibility feature; no current blocker
- **Effort**: Medium - SQLite query layer + CLI display + tests
- **Risk**: Low - Additive, no changes to existing behavior
- **Breaking Change**: No

## Related Key Documentation
_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels
`analytics`, `context-window`, `hooks`, `captured`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-22_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 69/100 → MODERATE

### Concerns
- **ENH-1114 still in `depends_on`**: Open P4 issue that adds `--intent` to CLI tools — no schema changes to `tool_events`. Collision risk is moot since FEAT-1112 already shipped the byte columns. Drop from `depends_on` frontmatter before starting.
- **`cache_hit` not populated by current hook payload**: Hosts don't emit a `cache_hit` field today. The "prompt cache metrics" AC will report 0 hits until the host wires this through — expected initial behavior, not a bug.

### Outcome Risk Factors
- **Broad enumeration across 27+ sites** — after the 3rd wiring pass, ~17 are mechanical doc/template edits and ~10 are code changes. Pattern B fanout with no explicit verification grep for `ll-ctx-stats` completeness. Add a wiring test similar to `test_feat1504_doc_wiring.py`.
- **Two breaking test files** (`test_hook_post_tool_use.py`, `test_hook_intents.py:319`) — sequence Step 6 (test updates) in the same commit as Step 2 (hook change) to avoid a broken-test window.
- **`analytics.enabled` config step is required** (not optional): add `"analytics"` block to `config-schema.json` and `"analytics": {"enabled": false}` to all 9 templates in one pass; schema uses `additionalProperties: false`.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-22
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1623: ctx-stats Data Layer — Schema Extension and PostToolUse Hook
- FEAT-1624: ctx-stats CLI Command — `ll-ctx-stats` Implementation and Tests
- FEAT-1625: ctx-stats Docs and Wiring — Documentation, Config Schema, and Count Bumps

## Session Log
- `/ll:issue-size-review` - 2026-05-22T00:00:00 - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:confidence-check` - 2026-05-22T00:00:00 - `75d29147-cdd1-4b59-a119-df913396b6b7.jsonl`
- `/ll:wire-issue` - 2026-05-23T00:56:03 - `5e7f7149-9b71-4fe5-b27f-1ce2ae1e4968.jsonl`
- `/ll:refine-issue` - 2026-05-23T00:48:53 - `40796b5b-8bda-4c75-b096-f4b2cc589273.jsonl`
- `/ll:confidence-check` - 2026-05-22T00:00:01 - re-run; FEAT-1112 done, missing_artifacts cleared, readiness 85→91
- `/ll:verify-issues` - 2026-05-23T00:35:43 - `2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:refine-issue` - 2026-05-22T20:01:26 - `d6c016c0-757a-4c25-9fb0-6b6bf3c10291.jsonl`
- `/ll:wire-issue` - 2026-05-22T19:57:06 - `71050fdf-80e1-449c-b1fe-daa146bb5f88.jsonl`
- `/ll:confidence-check` - 2026-05-22T00:00:00 - `71369049-8e66-40d9-974d-c382f4314900.jsonl`
- `/ll:refine-issue` - 2026-05-22T19:47:58 - `e312d3c3-3d24-4cb6-ab47-748c38cba6f8.jsonl`
- `/ll:confidence-check` - 2026-05-22T00:00:00 - `4d993416-8a80-45be-9b6a-2bd17fce2b4f.jsonl`
- `/ll:wire-issue` - 2026-05-22T19:40:58 - `930d04eb-ce45-4bd2-b1d2-17f6dd98dc26.jsonl`
- `/ll:refine-issue` - 2026-05-22T19:35:38 - `b4352269-7aec-46b6-b012-4ff34a66934a.jsonl`
- `/ll:format-issue` - 2026-05-22T19:04:09 - `888ec989-94b9-4241-bd4f-a791cfe37296.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-22T16:01:45 - `bd1623c9-b064-4a18-a889-d90953167101.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-18T05:02:36 - `16717e5e-bfe4-4e7f-8d36-177b4b791f2d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-17T18:46:35 - `ebf7abce-1ef1-46c8-8cbc-56d9f857d730.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-14T21:18:01 - `75505ad4-6733-4424-b334-3143f412786b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:08 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:17 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-23T00:14:34 - `2c0e0697-1da9-403b-82a7-6eb401f63ad3.jsonl`
- `/ll:capture-issue` - 2026-04-18T00:00:00 - `f6ae308f-90dc-4b4e-8527-5207880ea6dd.jsonl`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- No `ll-ctx-stats` CLI command exists ✓
- No PostToolUse hook accumulating byte counters to `.ll/ll-ctx-stats.json` ✓
- Blocked by FEAT-1112 (session store) which is itself not yet implemented ✓
- Feature not yet implemented ✓

---

## Status
**Open** | Created: 2026-04-18 | Priority: P4

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): The "Approach 1" implementation path (PostToolUse hook writing to `.ll/ll-ctx-stats.json`) is removed from scope. Scope this issue exclusively to Approach 2: extend FEAT-1112's SQLite schema with per-tool byte columns and implement `ll-ctx-stats` as a standalone CLI command (not a `/ll:` skill) that queries that store. The flat-file hook approach re-introduces the fragmentation FEAT-1112 was designed to eliminate. Implementation steps 1-3 must be rewritten to describe schema extension + query logic rather than a hook accumulator.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-17): Schema extensions to FEAT-1112's `tool_events` table must be coordinated with ENH-1114. This issue adds per-tool `bytes_in`/`bytes_out`/`cache_hit` columns; ENH-1114 adds FTS5 intent-ranking indexing. Both must target FEAT-1112's migration framework to avoid column collisions — implement sequentially after FEAT-1112 ships, not concurrently.
