---
id: ENH-2505
title: "Link subagent session-tree (parent\u2192child) into history.db"
type: ENH
priority: P3
status: done
discovered_date: 2026-07-06
captured_at: '2026-07-06T00:00:00Z'
completed_at: '2026-07-20T23:42:10Z'
discovered_by: capture-issue
parent: EPIC-2457
depends_on:
- ENH-2497
learning_tests_required:
- sqlite3
- claude-code-hooks
decision_needed: false
labels:
- enhancement
- history-db
- agents
- captured
confidence_score: 100
outcome_confidence: 70
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 18
---

# ENH-2505: Link subagent session-tree (parent→child) into history.db

## Summary

Every `Agent` (Task) tool spawn produces a child session_id; the parent →
child relationship is currently invisible because tool_events records the
spawn as a generic `Task` row but never links the spawned session back to
its caller. So "which parent sessions burn budget on subagent retries",
"how often does Task spawn an `Explore` agent", and "which subagents
oscillate the most" — the three questions the kill-analysis
(`autodev-bug2501-kill-analysis.md`) couldn't answer — are unanswerable
without re-parsing JSONL. Add a `subagent_runs` table (or fold as columns
into `sessions`) capturing `(parent_session_id, child_session_id,
agent_type, started_at, ended_at)` so the spawn tree is queryable.

## Motivation

- **The parent→child linkage is the missing join.** ENH-2497 captures
  `agent_type` on `tool_events`, so we know *what* was spawned; this issue
  captures *which session the spawn belongs to* and *what that session
  returned*. Together they answer "parent X spawned N children of type Y,
  P% of which re-spawned children of their own."
- **ENH-2497 covers the spawn event but not the lifecycle.** Without
  `ended_at`, you can't tell a subagent that's still running from one that
  crashed mid-flight. Without the parent linkage, you can't tell which
  parent's budget a subagent burned.
- **The kill-analysis showed the cost.** The autodev-kill analysis had to
  walk three separate session IDs by hand because the tool_events row
  carried the spawn but not the resulting session_id. A single
  `subagent_runs` row would have surfaced the tree in one query.

## Current Behavior

- A `Task` spawn is recorded by `post_tool_use` as a `tool_events` row
  with `tool_name="Task"`, `agent_type=<subagent_type>` (after ENH-2497),
  and the tool response payload — but the *child session_id* returned by
  the spawn is not extracted from the response.
- There is no way to ask "which subagents did session `a21e4561-...`
  spawn?" without reading JSONL.
- `ll-ctx-stats` / `ll-logs dead-skills` cover skill usage; nothing
  covers subagent trees.

## Expected Behavior

- A `subagent_runs` table records one row per subagent spawn with
  `parent_session_id`, `agent_id`, `agent_type`, `started_at`,
  `ended_at` (nullable while running), and `status` (`running` |
  `completed` | `failed` | `timeout`).
- `SubagentStart` supplies `agent_id`/`agent_type` (and the parent
  `session_id`) at spawn time; write the row from that payload
  (best-effort). **Note**: `agent_id` (e.g. `"def456"`) is a spawn-local
  identifier, not a `sessions.session_id` — the subagent's transcript is
  a *nested* file (`<transcript_dir>/subagents/agent-<id>.jsonl`), not a
  top-level session row. Do not assume a join against `sessions` on this
  column.
- `SubagentStop` supplies `agent_transcript_path` and updates `ended_at`
  / `status` for the matching `agent_id` row (best-effort).
- `ll-session recent --kind subagent_run` returns rows; FTS matches
  `agent_id` / `agent_type`.
- Future `ll-ctx-stats` per-agent block can roll up
  "subagents spawned by this session" alongside the executor tool-count.

## Impact

- **Who's affected**: Anyone debugging subagent-heavy automation runs
  (`ll-parallel`, `ll-sprint`, `rn-*` recursive loops) or analyzing budget
  burn across a fleet of Task spawns — currently limited to hand-walking
  JSONL transcripts session-by-session.
- **Severity if unaddressed**: Medium — no data loss or breakage, but the
  spawn tree stays unqueryable, so questions like "which parent burns the
  most subagent budget" or "which agent type oscillates" require manual
  JSONL archaeology every time (as the kill-analysis in
  `autodev-bug2501-kill-analysis.md` had to do).
- **Scope of change**: One new table (`subagent_runs`, schema v28), two
  new best-effort lifecycle hook handlers (`SubagentStart`/
  `SubagentStop`), three new `history_reader` helpers, and one new
  `ll-session --kind subagent_run` value — additive only, no changes to
  existing tables or read paths.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS subagent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    parent_session_id TEXT,
    agent_id TEXT,
    agent_type TEXT,              -- "codebase-locator" | "Explore" | "loop-specialist" | ...
    agent_transcript_path TEXT,   -- nested transcript path from SubagentStop
    started_at TEXT,
    ended_at TEXT,                -- NULL while running
    status TEXT,                  -- "running" | "completed" | "failed" | "timeout"
    head_sha TEXT,
    branch TEXT,
    UNIQUE(parent_session_id, agent_id)  -- one row per (parent, agent_id); INSERT OR IGNORE on replay
);
CREATE INDEX IF NOT EXISTS idx_subagent_parent ON subagent_runs(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_subagent_agent_id ON subagent_runs(agent_id);
CREATE INDEX IF NOT EXISTS idx_subagent_agent ON subagent_runs(agent_type);
CREATE INDEX IF NOT EXISTS idx_subagent_status ON subagent_runs(status);
```

**Naming decision (resolved 2026-07-20, see "Naming Decision" below)**: the
child-identifier column is `agent_id`, matching the `SubagentStart`/
`SubagentStop` payload verbatim — not `child_session_id`. `agent_id` is
spawn-local (e.g. `"def456"`), scoped to its parent session, not a global
session id, so the UNIQUE constraint is a composite
`(parent_session_id, agent_id)`, not a bare `UNIQUE(agent_id)`.

Bump `SCHEMA_VERSION`. Add `"subagent_run"` to `VALID_KINDS` and
`"subagent_run": "subagent_runs"` to `_KIND_TABLE`.

### Producer wiring

- `SubagentStart` fires with `session_id` (parent), `agent_id`, and
  `agent_type` in its payload; the handler calls
  `record_subagent_run(db_path, parent_session_id=session_id, agent_id=...,
  agent_type=..., started_at=..., status="running")`.
- `SubagentStop` fires with `agent_id`, `agent_type`, and
  `agent_transcript_path`; the handler updates `ended_at`, `status`, and
  `agent_transcript_path` for the row matching
  `(parent_session_id, agent_id)`. Best-effort, batched.
- Backfill: extend `_backfill_tool_events` (or add a sibling
  `_backfill_subagent_runs`) to walk each session's nested
  `subagents/agent-<id>.jsonl` transcripts (discoverable from the parent's
  transcript directory) and populate rows from historical JSONL.

### Read API

- `history_reader.subagent_tree(session_id)` — returns the direct
  `agent_id` spawns for a parent session, plus grandchild counts derived
  by recursing into each nested `agent_transcript_path` (not a join
  against `sessions`, since subagent transcripts are nested files, not
  top-level session rows).
- `history_reader.subagent_retries(agent_type, since=None)` — counts of
  same-agent re-spawns by a single parent (the "oscillation" signal).
- `history_reader.subagent_budget(session_id)` — total subagent-run
  duration rollup for a parent session (the "burn budget" signal).

### CLI surface

- `ll-session recent --kind subagent_run`.
- `ll-session tree <session_id>` (optional follow-on) — renders the
  spawn tree as ASCII / JSON.

## Acceptance Criteria

- Schema migration lands; `subagent_runs` exists; `SCHEMA_VERSION` bumped.
- A `SubagentStart` event writes one row with the correct
  `parent_session_id`, `agent_id`, `agent_type`, and `started_at`.
- A `SubagentStop` event updates the matching row's `ended_at`, `status`,
  and `agent_transcript_path` (best-effort).
- `ll-session recent --kind subagent_run` returns rows; FTS matches
  `agent_type`.
- Writes are best-effort: a missing/malformed payload writes
  `agent_id=NULL` (or skips), never raises.
- Tests cover: spawn, end, replay idempotency (`INSERT OR IGNORE` on
  `(parent_session_id, agent_id)`), missing-field graceful handling.

## Sources

- `autodev-bug2501-kill-analysis.md` (2026-07-07) — section "Extract the
  session-store trace" walks three session IDs by hand; the linkage
  would have surfaced the tree
- EPIC-2457 review (third-pass expansion, 2026-07-06)
- ENH-2497 — captures `agent_type` on tool_events; this issue captures
  the lifecycle + parent linkage that ENH-2497 deliberately deferred
- `scripts/little_loops/hooks/post_tool_use.py` — spawn producer site
- `scripts/little_loops/hooks/stop.py` (or equivalent) — end-of-session
  producer site

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Codebase Research Findings

_Added by `/ll:refine-issue ENH-2505 --auto` on 2026-07-16, based on codebase analysis of three parallel research agents (codebase-locator, codebase-analyzer, codebase-pattern-finder):_

### Critical Decision: Source of Child Session Identifier

The Proposed Solution above assumes `child_session_id` is present in the `tool_response` payload of the Agent tool. **Codebase research did not find any checked-in evidence that this payload shape is real.** A repository-wide search returned zero matches for `child_session_id`, `tool_response.agent_id`, `tool_response.session_id`, or `tool_response.sessionId` in any sample payload, test fixture, or reference. The only Claude-Code-documented surface for child-session identifiers is the `SubagentStart` / `SubagentStop` lifecycle hook pair (see `docs/claude-code/hooks-reference.md`), which carries `agent_id` (not `child_session_id`).

This is the meaningful implementation choice an implementer must resolve before writing the producer:

**Option A: Extract `child_session_id` from `tool_response` inside `post_tool_use.py`** — match the issue's Proposed Solution as written; requires empirical verification against a live Claude Code run that the PostToolUse response actually carries a child-session key. If it does, the change is local to `post_tool_use.py:158-180` and does not require new hook wiring.

**Option B: Bind `SubagentStart` / `SubagentStop` lifecycle hooks** — use the only Claude-Code-documented surface that carries child identifiers. Requires adding two new event bindings to `hooks/hooks.json`, two new Python handlers (`subagent_start.py` / `subagent_stop.py`) under `scripts/little_loops/hooks/`, and `_dispatch_table()` registrations in `hooks/__init__.py:74-92`. The schema column `child_session_id` would more accurately be named `agent_id` for fidelity to the documented payload. Backfill from JSONL is feasible because the matching child transcript is at `<transcript_path>/<parent_session>/subagents/<agent_id>.jsonl` per the `SubagentStop` documented sample.

> **Selected:** Option B: Bind `SubagentStart` / `SubagentStop` lifecycle hooks — Documented payload carries `agent_id`/`agent_type`/`agent_transcript_path` directly; PostToolUse `tool_response` shape for Agent/Task is unverified in the repo (zero fixture/sample/doc matches)

**Recommended**: Option B — `SubagentStart` / `SubagentStop`. The Claude Code hooks reference documents the payload shape (`session_id`, `agent_id`, `agent_type`, `agent_transcript_path`) and these events fire on every spawn/completion. PostToolUse child-session extraction is unverified in this repository and would require an empirical test before the producer could land. EPIC-2457 third-pass expansion notes already flag ENH-2511 and ENH-2505 as schema-coordination constraints, suggesting the maintainers expect lifecycle hooks rather than response-payload parsing.

### Integration Map

**Files to Modify**

- `scripts/little_loops/session_store.py` — bump `SCHEMA_VERSION = 20` (line 207) to `21` after ENH-2497 lands, then to `22` for this issue; append `_MIGRATIONS` entry creating `subagent_runs`; add `"subagent_run"` to `VALID_KINDS` (line 209); add `"subagent_run": "subagent_runs"` to `_KIND_TABLE` (line 223); add `record_subagent_run(...)` writer (template: `record_test_run_event` at line 1352 or `record_commit_event` at lines 1078-1087); add `_backfill_subagent_runs(...)` companion to `_backfill_tool_events` (line 1836); wire it into `rebuild()` orchestrator at lines 2838-2893.
- `scripts/little_loops/hooks/post_tool_use.py` — if Option A is chosen, add Agent/Task-specific branch in the analytics-gated insert block (lines 158-180) that calls `record_subagent_run(...)` after extracting child ID from `tool_response`. If Option B, no change to this file.
- `scripts/little_loops/hooks/__init__.py` — register new intent handlers if Option B (`subagent_start`, `subagent_stop`) in `_dispatch_table()` at lines 74-92; update `_USAGE` static intent list at lines 50-56 (the `_USAGE` banner is a discoverability surface — `reference_dispatch_table_usage_banner` memory notes it must be updated when new hook intents are added).
- `scripts/little_loops/hooks/sweep_stale_refs.py` — extend the existing `session_end` handler to also `UPDATE subagent_runs SET ended_at = ?, status = ?` for any rows whose `agent_id` matches an unstopped spawn from this session (best-effort, batched fallback for the case a `SubagentStop` was missed). Or fold this into a new SubagentStop handler if Option B is chosen.
- `hooks/hooks.json` — if Option B, add `SubagentStart` and `SubagentStop` event bindings; if neither, leave Stop bindings alone (they currently only call shell cleanup scripts).
- `scripts/little_loops/history_reader.py` — add `SubagentRun` dataclass (template: `RunEvent` at lines 138-161); add three helpers: `subagent_tree(session_id)`, `subagent_retries(agent_type, since=None)`, `subagent_budget(session_id)`. Templates: `recent_test_runs()` (lines 689-725) for the dataclass mapping shape; `issue_effort()` (line 767) and `lookup_session_metadata()` (line 836) for tree/rollup queries.
- `scripts/little_loops/cli/session.py` — `recent --kind` choices derive from `VALID_KINDS` (lines 112-130); will auto-include `subagent_run` once registered. Optional follow-on `tree <session_id>` subcommand.
- `scripts/little_loops/cli/verify_kinds.py` — `ll-verify-kinds` gate enforces `_KIND_TABLE` registration; must pass before migration lands.
- `scripts/tests/test_session_store.py` — add `TestSchemaV22SubagentRuns` migration test using `_bootstrap_schema_at(db, version)` helper (lines 3891-3911); model on `TestSchemaV20UsageEvents` (lines 3221-3243).
- `scripts/tests/test_history_reader.py` — add tests for `subagent_tree`, `subagent_retries`, `subagent_budget` (pattern: lines 1395-1635).
- `scripts/tests/test_hook_post_tool_use.py` — if Option A, add Agent/Task-spawn case to `TestPostToolUseWithSessionStore` (lines 100-237); if Option B, add tests in a new `test_hook_subagent_start.py` / `test_hook_subagent_stop.py`.
- `scripts/tests/test_verify_kinds.py` — no new test required; existing gate will validate.
- `docs/ARCHITECTURE.md` — add v22 row to `history.db` schema versions table (lines 657-679).
- `docs/reference/API.md` — fix stale `SCHEMA_VERSION` example at line 7279 (currently says 19, actual is 20); add `record_subagent_run`, `subagent_tree`, `subagent_retries`, `subagent_budget` to `little_loops.session_store` section (starts at line 7273) and `little_loops.history_reader` section.
- `docs/reference/CLI.md` — add `--kind subagent_run` row.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/subagent_start.py` — new host-agnostic `SubagentStart` handler that records the parent/child start row.
- `scripts/little_loops/hooks/subagent_stop.py` — new best-effort `SubagentStop` handler that closes the child row and records terminal status.
- `hooks/adapters/claude-code/subagent-start.sh` — thin Claude Code adapter for the new start intent.
- `hooks/adapters/claude-code/subagent-stop.sh` — thin Claude Code adapter for the new stop intent.
- `scripts/little_loops/observability/schema.py` — register the direct `subagent_runs` history writer in `DES_VARIANTS` so the DES audit documents the new table target.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — reconcile the stale schema-version/table map and document querying `subagent_runs`.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — document the new lifecycle hooks in the event table and session flow.

**Dependent Files (Callers/Importers)**

- `scripts/little_loops/parallel/orchestrator.py` — spawns subagents; consumer of the new `subagent_runs` data for fleet telemetry.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — uses subagent spawns heavily; future iteration could query `subagent_retries()` to detect oscillation.
- `scripts/little_loops/worktree_utils.py` — worktree-per-issue model; future `ll-ctx-stats` per-agent block will roll up against `subagent_runs`.

**Similar Patterns to Follow**

- `record_commit_event()` (`session_store.py:1078-1087`) — `INSERT OR IGNORE` + `cursor.rowcount` guard; closest analogue for idempotent write.
- `record_test_run_event()` (`session_store.py:1352`) — single-row writer with named `ts`/`ended_at` kwargs; closest pattern for `record_subagent_run`.
- `cli_event_context()` (`session_store.py:1054-1091`) — two-phase write-and-update-on-exit `@contextmanager`; useful alternative if a `subagent_run_context()` style API is preferred over split write/update.
- `recent_test_runs()` (`history_reader.py:689-725`) — `_connect_readonly()` + `_row_to_dataclass()` + parametrized WHERE clauses; canonical reader-helper shape.

**Tests**

- `scripts/tests/test_session_store.py` — schema-version + idempotency tests.
- `scripts/tests/test_history_reader.py` — reader helper tests.
- `scripts/tests/test_hook_post_tool_use.py` — live producer tests (Option A only).
- `scripts/tests/test_verify_kinds.py` — `_KIND_TABLE` registration gate.
- Suggested new test file: `scripts/tests/test_enh_2505_subagent_runs.py` with classes `TestSubagentRunMigration`, `TestAgentSpawnLifecycle`, `TestSubagentTreeAPI`, `TestSubagentReplayIdempotency` (mirrors the `test_enh_2497_agent_type.py` naming pattern referenced in the ENH-2497 plan).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_claude_code_adapter.py` — extend structural adapter checks for the new executable scripts and `SubagentStart`/`SubagentStop` entries in `hooks/hooks.json`.
- `scripts/tests/test_hooks_integration.py` — add subprocess round-trip coverage for the new Claude Code adapters and their best-effort exit behavior.
- `scripts/tests/test_hook_intents.py` — assert `_dispatch_table()` exposes both new intents and malformed lifecycle payloads remain non-blocking.
- `scripts/tests/test_ll_session.py` — assert `recent` and `search` accept `--kind subagent_run`, following the existing per-kind parser tests.
- `scripts/tests/test_des_schema.py` — cover the `SubagentRun` direct-writer variant in the `DES_VARIANTS` registry.
- `scripts/tests/test_assistant_messages.py` — update the schema-version assertion that currently pins the database at v20.
- `scripts/tests/test_sweep_stale_refs.py` — extend shared best-effort/session-end coverage if the terminal-row update is folded into the existing sweep path rather than isolated in `subagent_stop`.

### Constants & Discovered Drift

- **Constant name**: The issue text references `_VALID_KINDS` (with underscore prefix) in the `Proposed Solution > Schema migration` section. The actual public constant in `session_store.py:209` is **`VALID_KINDS`** (no underscore prefix). Implementer should use `VALID_KINDS`, not `_VALID_KINDS`.
- **SCHEMA_VERSION**: Currently `20` at `session_store.py:207`. `docs/reference/API.md:7279` example is stale (says `19`).
- **`_KIND_TABLE`**: Exposed as `_KIND_TABLE` (with underscore) at `session_store.py:223`. The `VALID_KINDS` constant is the public name (no underscore); the leading underscore on `_KIND_TABLE` is intentional (module-private dispatch table, while `VALID_KINDS` is the public surface).
- **`session_end` intent relocation**: `sweep_stale_refs.handle` is registered as the `session_end` intent (`hooks/__init__.py:92`) but the Claude Code adapter (`hooks/adapters/claude-code/session-end.sh`) is bound under `SessionStart`, not `SessionEnd`. The relocation is deliberate (see `sweep_stale_refs.py` module docstring — full scan timed out at SessionEnd). This means the issue's "Stop hook updates ended_at" needs a different wiring path than assuming a Python Stop handler exists.

### Coordination with ENH-2497

ENH-2497 is **planned, not landed** — its issue file remains `status: open`; `SCHEMA_VERSION` is still 20; `tool_events` has no `agent_type` column; `post_tool_use.py` does not extract `subagent_type`; `_backfill_tool_events()` does not extract `block["input"]["subagent_type"]`; there are no `agent_usage()` or `recent_tool_events()` reader helpers. ENH-2497 plans to bump `SCHEMA_VERSION` to `21` (adding `agent_type` column to `tool_events`). Because ENH-2505 `depends_on: [ENH-2497]`, **ENH-2505 must bump to v22, not v21**, and must append after the ENH-2497 migration entry. The `agent_type` column added by ENH-2497 is the parent table's existing discriminator; ENH-2505's `subagent_runs.agent_type` denormalizes the same value for tree-query convenience.

> ⚠ **Stale as of 2026-07-20** — see "Staleness Correction" subsection below. ENH-2497 has since landed; all version numbers and line references above are superseded.

### Staleness Correction (2026-07-20 re-run of `/ll:refine-issue --auto`)

_The dependency this issue is blocked on has since landed, and the codebase has moved through four more schema migrations. This subsection corrects the drift; it does not replace the analysis above, which remains useful for the Option A/B reasoning trail._

- **ENH-2497 is landed**, not open. `ll-issues show ENH-2497` reports `Status: Completed`. It shipped as schema **v24** (`scripts/little_loops/session_store.py:816-824`, comment tags `ENH-2497`): `ALTER TABLE tool_events ADD COLUMN agent_type TEXT;` plus `idx_tool_events_agent` index. Reader helpers `agent_usage()` and `recent_tool_events()` exist in `history_reader.py` (confirmed via `scripts/tests/test_enh_2497_agent_type.py`, which also documents the v24 migration test pattern — `TestSchemaV24AgentType`, `_bootstrap_schema_at(db, 23)` then `ensure_db(db)`).
- **`SCHEMA_VERSION` is now 27** (`session_store.py:217`), not 20. Migrations since v24: **v25** (ENH-2511, `mcp_server`/`mcp_tool`/`mcp_outcome`/`latency_ms` on `tool_events`, `session_store.py:825-837`), **v26** (ENH-2466, `learning_test_events` table, `session_store.py:838-857`), **v27** (ENH-2495/ENH-2509, `session_lifecycle_events` table, `session_store.py:859-877`). **A new `subagent_runs` migration for this issue must be appended as v28**, not v22.
- **`VALID_KINDS` is now at `session_store.py:219`, `_KIND_TABLE` at `session_store.py:237`** (both shifted from the 209/223 cited earlier in this document due to the four intervening migrations).
- **The Option A vs. Option B question is now empirically resolved, confirming the earlier decision.** `post_tool_use.py`'s Task-tool handling block calls `_normalize_agent_type(tool_input.get("subagent_type"))` at **line 168-169**, reading the agent label from `tool_input` (the call), not `tool_response`. `tool_response` is read separately (~lines 152, 176-178) but only for `isError` / `bytes_out` / `mcp_outcome` — **no session-id-shaped field is extracted from it anywhere in the file**. This confirms — with a live code read rather than a zero-grep-match absence — that Option A's premise (child session id in `tool_response`) does not hold in this codebase today. The already-selected **Option B (SubagentStart/SubagentStop lifecycle hooks) remains correct** and does not need to be revisited.
- **SubagentStart/SubagentStop still do not exist anywhere in the repo** — confirmed via grep on `hooks/hooks.json`, `scripts/little_loops/hooks/__init__.py`, and a repo-wide `subagent_start|subagent_stop|subagent-start|subagent-stop` search (only match: this issue file itself). The wiring described in the Integration Map is still fully greenfield.
- **Fresher template citations** (supersede the ones earlier in this section, which now point at different code after the version bump):
  - Schema migration template: v26/v27 above (`session_store.py:838-877`) — clearer recent examples of `CREATE TABLE IF NOT EXISTS ... UNIQUE ...` + indexes than what was cited previously.
  - Idempotent writer template: `record_commit_event()` is now at `session_store.py:1396-1446` (guard `inserted = bool(cursor.rowcount)`); sibling patterns `record_test_run_event` (writer ~1526, guard ~1672) and `record_loop_run_event` (writer ~1721, guard ~1740).
  - Host-agnostic hook handler + adapter + dispatch template: `scripts/little_loops/hooks/session_start.py:75` (`handle(event: LLHookEvent) -> LLHookResult`), adapter `hooks/adapters/claude-code/session-start.sh` (`cat` stdin → `python -m little_loops.hooks session_start`), registered in `hooks/hooks.json:10` and `scripts/little_loops/hooks/__init__.py:88-97` (`_dispatch_table()`'s `built_ins` dict). This is the exact 3-layer triad the new `subagent_start`/`subagent_stop` handlers should follow.
  - Reader rollup/aggregation template: `issue_effort()` (`history_reader.py:1506-1538`, `COUNT`/`MIN`/`MAX` single-row rollup), `worktree_summary()` (`history_reader.py:1174-1208`, `COUNT(*) FILTER (WHERE event = ...)` grouped rollup), `aggregate_loop_runs()` (`history_reader.py:1423-1449`, whitelisted `GROUP BY` pattern) — all return `None`/`[]` on missing DB via `_connect_readonly()` (`history_reader.py:339`). Use these over the `recent_test_runs()` citation earlier in this section for the tree/budget/retries helpers.
- **No test file exists yet** for this issue (`scripts/tests/*subagent*.py` glob returns no files) — the suggested `test_enh_2505_subagent_runs.py` file from the Tests subsection above is still accurate and still needs to be created.

### Idempotency & Best-Effort Conventions

- All hook writes must be wrapped in `with contextlib.suppress(Exception):` per the EPIC-1707 best-effort contract — see `post_tool_use.py:158` and `session_start.py:75`. New producer code must follow.
- `INSERT OR IGNORE` + `cursor.rowcount` guard (the `record_commit_event` pattern at `session_store.py:1078-1087`) for replay safety; `UNIQUE(parent_session_id, agent_id)` composite constraint enforces single-row-per-spawn (an `agent_id` is scoped to its parent session, not globally unique on its own).
- Missing/malformed payloads write `agent_id=NULL` (or skip), never raise.
- Four existing precedents for `UNIQUE` + `INSERT OR IGNORE`: v3 (ENH-1690) `idx_issue_events_dedup`, v9 (ENH-1904) `idx_corrections_dedup`, v11 `idx_assistant_messages_dedup`, v17 (ENH-2458) `commit_sha TEXT NOT NULL UNIQUE` declared inline.

### Test Patterns

- Use `_bootstrap_schema_at(db, version)` helper (`scripts/tests/test_session_store.py:3891-3911`) for v22 migration test.
- Add `TestSchemaV22SubagentRuns` class modeled on `TestSchemaV20UsageEvents` (lines 3221-3243).
- Upgrade-pattern test (model on `TestSchemaV15SkillCompletionColumns` lines 3914-3956): bootstrap at v21, insert pre-migration rows, run `ensure_db(db)` to bump to v22, assert `row["new_column"] is None` on pre-existing rows.
- Idempotency test (model on `record_commit_event` test at lines 4256-4264): call `record_subagent_run` twice with the same `(parent_session_id, agent_id)`, assert second call is a no-op.
- `ll-verify-kinds` test will validate `_KIND_TABLE` registration; no new test required but the gate must pass.

### Documentation Updates

- `docs/ARCHITECTURE.md` schema-versions table (lines 657-679) — add v22 row referencing `subagent_runs`.
- `docs/reference/API.md` — fix stale `SCHEMA_VERSION = 19` example at line 7279 (actual is 20, will be 22 after this issue); document `record_subagent_run`, `subagent_tree`, `subagent_retries`, `subagent_budget` helpers.
- `docs/reference/CLI.md` — add `--kind subagent_run` row under `ll-session recent`.
- `.claude/CLAUDE.md` — `ll-session` entry already documents `--kind`; the new value is auto-derived from `VALID_KINDS` and needs no `.claude/CLAUDE.md` change unless listed.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md` — update the current schema version, append the migration/table entries, and add a subagent-tree query recipe.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — add `SubagentStart`/`SubagentStop` to the lifecycle-at-a-glance table and session-flow narrative.

### Open Questions for Implementer

1. Does Claude Code's PostToolUse response actually carry a child-session identifier (e.g., under `tool_response`)? Empirical verification needed before Option A is viable. Check the kill-analysis referenced in the issue (`autodev-bug2501-kill-analysis.md`) for any captured PostToolUse payload samples.
2. ~~Should `child_session_id` be renamed `agent_id` for fidelity to the Claude Code hook payload if Option B is chosen?~~ **Resolved 2026-07-20 — see "Naming Decision" below.**
3. Is the backfill feasible from JSONL alone? `SubagentStop` documented sample places child transcripts at `<parent_transcript_path>/subagents/<agent_id>.jsonl`, which is discoverable during backfill.
4. Does the `ll-ctx-stats` per-agent block need to roll up against `subagent_runs`, or is that a separate follow-on (the issue mentions it as "future")?

### Naming Decision

Decided during `/ll:confidence-check` follow-up on 2026-07-20.

**Selected**: `agent_id` (not `child_session_id`), with a **composite**
`UNIQUE(parent_session_id, agent_id)` constraint (not a bare
`UNIQUE(agent_id)`).

**Reasoning**: `docs/claude-code/hooks-reference.md` (`SubagentStart`/
`SubagentStop` sections) documents `agent_id` as a spawn-local identifier
(example values: `"agent-abc123"`, `"def456"`) — it is not a
`sessions.session_id`. The subagent's transcript is stored as a *nested*
file (`<parent-transcript-dir>/subagents/agent-<id>.jsonl`), not a
top-level session with its own row in the `sessions` table. Naming the
column `child_session_id` would have implied a join against `sessions`
that does not hold — `subagent_tree()` and friends must instead recurse
via `agent_transcript_path`, not `sessions.session_id`. Because `agent_id`
is scoped to its parent (not globally unique across all sessions), the
uniqueness constraint must be the composite
`(parent_session_id, agent_id)` pair rather than `agent_id` alone, or a
replay could silently collide two different parents' spawns that happen
to reuse the same `agent_id` value.

This resolves Open Question #2 and corrects the Read API description
above (originally written assuming a `sessions`-table join).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-16.

**Selected**: Option B: Bind `SubagentStart` / `SubagentStop` lifecycle hooks

**Reasoning**: Option A's load-bearing assumption — that PostToolUse `tool_response` carries a child-session identifier for Agent/Task — has zero checked-in evidence in the repo (no fixture, no test sample, no documented surface; repository-wide grep for `tool_response.agent_id` / `tool_response.session_id` / `tool_response.sessionId` returns zero matches). Option B uses the only Claude-Code-documented surface (`docs/claude-code/hooks-reference.md:1059-1112`) where `SubagentStart` / `SubagentStop` payloads carry `agent_id`, `agent_type`, and `agent_transcript_path` directly. The 3-layer wiring pattern (`hooks/hooks.json` binding → bash adapter under `hooks/adapters/claude-code/` → Python handler registered in `scripts/little_loops/hooks/__init__.py:_dispatch_table()`) has four clean precedents (SessionStart, Stop, SessionEnd, PreCompact), so Option B's larger surface area is template-driven boilerplate rather than novel work. The known SessionEnd hard-ceiling bug (`scripts/little_loops/hooks/sweep_stale_refs.py:10-19`, anthropics/claude-code#32712) is a designable risk class — Option B handles it by budgeting the `SubagentStop` handler for sub-second best-effort completion from day one.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A: Extract `child_session_id` from `tool_response` | 1/3 | 3/3 | 1/3 | 0/3 | 5/12 |
| Option B: Bind `SubagentStart` / `SubagentStop` lifecycle hooks | 3/3 | 2/3 | 2/3 | 2/3 | 9/12 |

**Key evidence**:
- **Option A**: Excellent producer-side reuse — `scripts/little_loops/hooks/post_tool_use.py:158-180` already extracts from `tool_response` inside an analytics-gated block, calls `session_store.connect()` / `commit()` / close, and wraps the whole block in `with contextlib.suppress(Exception):`. The `record_subagent_run` writer would template directly on `record_test_run_event()` (`session_store.py:1352`) or `record_commit_event()` (`session_store.py:1078-1087`). However, the data source itself is unverified: a repository-wide grep for `tool_response.agent_id` / `tool_response.session_id` / `tool_response.sessionId` returns zero matches in any sample payload, test fixture, or documentation surface. Implementing Option A requires empirical confirmation from a live Claude Code run before the producer can land, and the unlanded ENH-2497 dependency adds schema-coordination risk.
- **Option B**: SubagentStart / SubagentStop payloads are documented at `docs/claude-code/hooks-reference.md:1059-1112` with `agent_id` / `agent_type` / `agent_transcript_path` fields that map directly to the schema columns (the issue text at line 181 already flags the `child_session_id` → `agent_id` column rename). The 3-layer wiring has four precedents (SessionStart, Stop, SessionEnd, PreCompact). The plugin config auditor (`.codex/agents/plugin-config-auditor.toml:53-54`) already enumerates both events as known events — only the bindings/handlers themselves are missing. Test patterns at three layers (unit, adapter round-trip, DB-write) all have templates; no live-fire evidence in the suite, but this is consistent with all other lifecycle hooks.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Add the `SubagentStart`/`SubagentStop` Python handlers and Claude Code adapter scripts, then register both intents in `hooks/hooks.json`, `hooks/__init__.py`, and the static dispatcher usage text.
2. Extend `session_store.py` and `history_reader.py` for the new migration, kind registration, live/backfill writers, FTS rows, and tree/retry/budget read helpers; register the direct writer in `observability/schema.py`.
3. Extend lifecycle, adapter, CLI-kind, schema, DES registry, and malformed-payload tests, including the existing schema-version assertion in `test_assistant_messages.py`.
4. Reconcile `HISTORY_SESSION_GUIDE.md` and `BUILTIN_HOOKS_GUIDE.md` with the new schema table and lifecycle events, alongside the already-listed architecture/API/CLI documentation.
5. Run `ll-verify-kinds`, `ll-verify-des-audit`, the focused ENH-2505 tests, and the full `python -m pytest scripts/tests/` gate.

## Status

**Open** | Created: 2026-07-06 | Priority: P3 | Decision Needed: no (child-session identifier source resolved 2026-07-20 — see "Naming Decision" and "Decision Rationale")

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): **ENH-2497** (subagent Task
discrimination) owns the authoritative spawn-event discriminator at
`tool_events.agent_type`. This issue's `subagent_runs.agent_type` is a
query-side denormalization populated from the same normalized value at write
time, not an independent second source. The existing frontmatter
`depends_on: [ENH-2497]` enforces the ordering — this issue lands after
ENH-2497.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): **ENH-2506** (hook execution
telemetry) wraps every registered hook handler with `hook_event_context`.
This issue adds two new host-agnostic Python handlers (`SubagentStart`,
`SubagentStop`) and registers them in `hooks/hooks.json`,
`hooks/__init__.py`, and the static dispatcher usage text. To avoid both
omission (handlers fire without telemetry) and double-counting
(dispatcher-level + per-handler wrapping), the implementations must apply
exactly one telemetry wrap per `SubagentStart` / `SubagentStop` invocation.
The wrap belongs in ENH-2506's dispatcher-level wrapper, not duplicated in
this issue's per-handler body.

## Resolution

Implemented as Option B (`SubagentStart`/`SubagentStop` lifecycle hooks) per
the issue's decided rationale:

- Schema migration v28 adds `subagent_runs` (`scripts/little_loops/session_store.py`):
  `UNIQUE(parent_session_id, agent_id)` composite key, four indexes.
  `VALID_KINDS`/`_KIND_TABLE` gained `"subagent_run"`.
- `record_subagent_run_start()` (`INSERT OR IGNORE`, idempotent replay) and
  `record_subagent_run_stop()` (`UPDATE` on the composite key, best-effort) —
  modeled on `record_commit_event()`/`update_loop_run_diagnostics()`.
  `_backfill_subagent_runs()` seeds historical rows from nested
  `subagents/*.jsonl` transcripts (wired into `backfill(sessions_root=...)`
  and the `ll-session backfill` CLI via `get_project_folder()`).
- New host-agnostic handlers `hooks/subagent_start.py` / `subagent_stop.py`,
  registered in `hooks/__init__.py`'s `_dispatch_table()` + `_USAGE`, with
  Claude Code adapters `hooks/adapters/claude-code/subagent-start.sh` /
  `subagent-stop.sh` and `SubagentStart`/`SubagentStop` bindings in
  `hooks/hooks.json`. No `hook_event_context` telemetry wrap added here per
  the ENH-2506 scope-boundary note above — that wrap belongs in ENH-2506's
  dispatcher-level wrapper.
- `history_reader.py` gained the `SubagentRun` dataclass and
  `subagent_tree()`/`subagent_retries()`/`subagent_budget()` readers.
  `subagent_tree()` returns direct children only — grandchild recursion
  requires re-parsing each `agent_transcript_path`, not a SQL join, per the
  "Naming Decision" section above.
- `observability/schema.py` gained `SubagentRunVariant` in `DES_VARIANTS`
  (registry completeness; the audit walker only scans `event_bus.emit`/
  `self._emit` call sites, which this Channel-A direct writer doesn't use).
- Tests: new `scripts/tests/test_enh_2505_subagent_runs.py` (writer
  round-trip, replay idempotency, reader API, hook handlers, backfill), plus
  a `TestSchemaV28` migration class in `test_session_store.py` and coverage
  additions to `test_claude_code_adapter.py` (adapter existence + round-trip),
  `test_hook_intents.py` (dispatch registration + CLI round-trip),
  `test_ll_session.py` (`--kind subagent_run`), and the stale
  `SCHEMA_VERSION == 27` sanity assertions scattered across
  `test_session_store.py` (bumped to 28). `test_des_schema.py` and
  `test_verify_kinds.py` already parametrize over the full registry/table
  set, so no edits were needed there — both gates plus `ll-verify-des-audit`
  pass unchanged.
- Docs: `docs/ARCHITECTURE.md` (v28 schema row), `docs/reference/API.md`
  (new `session_store`/`history_reader` exports, stale `SCHEMA_VERSION`
  example fixed), `docs/reference/CLI.md` (`--kind subagent_run`),
  `docs/guides/HISTORY_SESSION_GUIDE.md`, and
  `docs/guides/BUILTIN_HOOKS_GUIDE.md` (new lifecycle-table row + dedicated
  section).

Full suite (`python -m pytest scripts/tests/`, 15641 passed / 38 skipped),
`ruff check`/`ruff format --check`, `mypy` (no new errors — only pre-existing
repo-wide `ruamel` stub warnings), `ll-verify-kinds`, and
`ll-verify-des-audit` all pass.

## Session Log
- `/ll:manage-issue` - 2026-07-20T23:41:14Z - `918e74d7-bdb8-4897-82ad-f60e5f91108e.jsonl`
- `/ll:ready-issue` - 2026-07-20T22:59:03 - `979aa45d-ce9d-401a-ad2b-aedea8458837.jsonl`
- `/ll:confidence-check` - 2026-07-20T00:00:00Z - `08a90449-d727-4ea4-8c30-244ca2ad7678.jsonl`
- `/ll:confidence-check` - 2026-07-20T00:00:00Z - `fafd5571-7c8d-4594-b219-0c7ca7229d44.jsonl`
- `/ll:refine-issue` - 2026-07-20T22:31:58 - `83f47fa3-b788-4e86-83c7-99cdc314f94f.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-17T14:03:02 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-17T13:59:18 - `ff04da3c-210f-4c14-9967-762b390ae67c.jsonl`
- `/ll:wire-issue` - 2026-07-17T00:32:24 - `93986e3c-827b-4964-9860-7394e662a283.jsonl`
- `/ll:decide-issue` - 2026-07-16T19:41:23 - `c5a83150-c2c4-41fe-8bff-072a77dba866.jsonl`
- `/ll:refine-issue` - 2026-07-16T16:08:30 - `8babd643-3346-4d9e-a0fd-d91a1800504e.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:55 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`