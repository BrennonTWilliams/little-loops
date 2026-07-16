---
id: ENH-2505
title: Link subagent session-tree (parent→child) into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-06
captured_at: "2026-07-06T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
depends_on: [ENH-2497]
decision_needed: false
labels:
  - enhancement
  - history-db
  - agents
  - captured
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
  `parent_session_id`, `child_session_id`, `agent_type`, `started_at`,
  `ended_at` (nullable while running), and `status` (`running` |
  `completed` | `failed` | `timeout`).
- The Agent tool's `tool_response` payload carries the child session_id;
  extract it in `post_tool_use` and write the row at end-of-spawn
  (best-effort).
- A small SessionEnd/Stop hook updates `ended_at` for any rows whose
  child_session_id has since stopped (best-effort, batched).
- `ll-session recent --kind subagent_run` returns rows; FTS matches
  `child_session_id` / `agent_type`.
- Future `ll-ctx-stats` per-agent block can roll up
  "subagents spawned by this session" alongside the executor tool-count.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS subagent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    parent_session_id TEXT,
    child_session_id TEXT,
    agent_type TEXT,              -- "codebase-locator" | "Explore" | "loop-specialist" | ...
    started_at TEXT,
    ended_at TEXT,                -- NULL while running
    status TEXT,                  -- "running" | "completed" | "failed" | "timeout"
    head_sha TEXT,
    branch TEXT,
    UNIQUE(child_session_id)      -- one row per child; INSERT OR IGNORE on replay
);
CREATE INDEX IF NOT EXISTS idx_subagent_parent ON subagent_runs(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_subagent_child ON subagent_runs(child_session_id);
CREATE INDEX IF NOT EXISTS idx_subagent_agent ON subagent_runs(agent_type);
CREATE INDEX IF NOT EXISTS idx_subagent_status ON subagent_runs(status);
```

Bump `SCHEMA_VERSION`. Add `"subagent_run"` to `_VALID_KINDS` and
`"subagent_run": "subagent_runs"` to `_KIND_TABLE`.

### Producer wiring

- In `scripts/little_loops/hooks/post_tool_use.py`, when
  `tool_name == "Agent"` (or `"Task"` for older Claude Code versions),
  extract `child_session_id` from `tool_response` and call
  `record_subagent_run(db_path, parent_session_id=..., child_session_id=...,
  agent_type=..., started_at=..., status="running")`.
- The Stop hook (`scripts/little_loops/hooks/stop.py` or equivalent)
  updates `ended_at` for any rows where `child_session_id IN (this
  session)` and `ended_at IS NULL`. Best-effort, batched.
- Backfill: extend `_backfill_tool_events` (or add a sibling
  `_backfill_subagent_runs`) to walk the assistant block for
  `tool_name="Task"` and the user block for the matching child session
  log; populate rows from historical JSONL.

### Read API

- `history_reader.subagent_tree(session_id)` — returns the parent +
  immediate children + grandchild counts for a session.
- `history_reader.subagent_retries(agent_type, since=None)` — counts of
  same-agent re-spawns by a single parent (the "oscillation" signal).
- `history_reader.subagent_budget(session_id)` — total child-session
  duration rollup (the "burn budget" signal).

### CLI surface

- `ll-session recent --kind subagent_run`.
- `ll-session tree <session_id>` (optional follow-on) — renders the
  spawn tree as ASCII / JSON.

## Acceptance Criteria

- Schema migration lands; `subagent_runs` exists; `SCHEMA_VERSION` bumped.
- An `Agent` spawn writes one row with the correct `parent_session_id`,
  `child_session_id`, `agent_type`, and `started_at`.
- A child session's end updates the parent row's `ended_at` and `status`
  (best-effort).
- `ll-session recent --kind subagent_run` returns rows; FTS matches
  `agent_type`.
- Writes are best-effort: a missing/malformed response payload writes
  `child_session_id=NULL` (or skips), never raises.
- Tests cover: spawn, end, replay idempotency (`INSERT OR IGNORE` on
  `child_session_id`), missing-field graceful handling.

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
- `scripts/little_loops/hooks/sweep_stale_refs.py` — extend the existing `session_end` handler to also `UPDATE subagent_runs SET ended_at = ?, status = ?` for any rows whose `child_session_id` matches this session (best-effort, batched). Or fold this into a new SubagentStop handler if Option B is chosen.
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

### Constants & Discovered Drift

- **Constant name**: The issue text references `_VALID_KINDS` (with underscore prefix) in the `Proposed Solution > Schema migration` section. The actual public constant in `session_store.py:209` is **`VALID_KINDS`** (no underscore prefix). Implementer should use `VALID_KINDS`, not `_VALID_KINDS`.
- **SCHEMA_VERSION**: Currently `20` at `session_store.py:207`. `docs/reference/API.md:7279` example is stale (says `19`).
- **`_KIND_TABLE`**: Exposed as `_KIND_TABLE` (with underscore) at `session_store.py:223`. The `VALID_KINDS` constant is the public name (no underscore); the leading underscore on `_KIND_TABLE` is intentional (module-private dispatch table, while `VALID_KINDS` is the public surface).
- **`session_end` intent relocation**: `sweep_stale_refs.handle` is registered as the `session_end` intent (`hooks/__init__.py:92`) but the Claude Code adapter (`hooks/adapters/claude-code/session-end.sh`) is bound under `SessionStart`, not `SessionEnd`. The relocation is deliberate (see `sweep_stale_refs.py` module docstring — full scan timed out at SessionEnd). This means the issue's "Stop hook updates ended_at" needs a different wiring path than assuming a Python Stop handler exists.

### Coordination with ENH-2497

ENH-2497 is **planned, not landed** — its issue file remains `status: open`; `SCHEMA_VERSION` is still 20; `tool_events` has no `agent_type` column; `post_tool_use.py` does not extract `subagent_type`; `_backfill_tool_events()` does not extract `block["input"]["subagent_type"]`; there are no `agent_usage()` or `recent_tool_events()` reader helpers. ENH-2497 plans to bump `SCHEMA_VERSION` to `21` (adding `agent_type` column to `tool_events`). Because ENH-2505 `depends_on: [ENH-2497]`, **ENH-2505 must bump to v22, not v21**, and must append after the ENH-2497 migration entry. The `agent_type` column added by ENH-2497 is the parent table's existing discriminator; ENH-2505's `subagent_runs.agent_type` denormalizes the same value for tree-query convenience.

### Idempotency & Best-Effort Conventions

- All hook writes must be wrapped in `with contextlib.suppress(Exception):` per the EPIC-1707 best-effort contract — see `post_tool_use.py:158` and `session_start.py:75`. New producer code must follow.
- `INSERT OR IGNORE` + `cursor.rowcount` guard (the `record_commit_event` pattern at `session_store.py:1078-1087`) for replay safety; `UNIQUE(child_session_id)` constraint enforces single-row-per-child.
- Missing/malformed payloads write `child_session_id=NULL` (or skip), never raise.
- Four existing precedents for `UNIQUE` + `INSERT OR IGNORE`: v3 (ENH-1690) `idx_issue_events_dedup`, v9 (ENH-1904) `idx_corrections_dedup`, v11 `idx_assistant_messages_dedup`, v17 (ENH-2458) `commit_sha TEXT NOT NULL UNIQUE` declared inline.

### Test Patterns

- Use `_bootstrap_schema_at(db, version)` helper (`scripts/tests/test_session_store.py:3891-3911`) for v22 migration test.
- Add `TestSchemaV22SubagentRuns` class modeled on `TestSchemaV20UsageEvents` (lines 3221-3243).
- Upgrade-pattern test (model on `TestSchemaV15SkillCompletionColumns` lines 3914-3956): bootstrap at v21, insert pre-migration rows, run `ensure_db(db)` to bump to v22, assert `row["new_column"] is None` on pre-existing rows.
- Idempotency test (model on `record_commit_event` test at lines 4256-4264): call `record_subagent_run` twice with the same `child_session_id`, assert second call is a no-op.
- `ll-verify-kinds` test will validate `_KIND_TABLE` registration; no new test required but the gate must pass.

### Documentation Updates

- `docs/ARCHITECTURE.md` schema-versions table (lines 657-679) — add v22 row referencing `subagent_runs`.
- `docs/reference/API.md` — fix stale `SCHEMA_VERSION = 19` example at line 7279 (actual is 20, will be 22 after this issue); document `record_subagent_run`, `subagent_tree`, `subagent_retries`, `subagent_budget` helpers.
- `docs/reference/CLI.md` — add `--kind subagent_run` row under `ll-session recent`.
- `.claude/CLAUDE.md` — `ll-session` entry already documents `--kind`; the new value is auto-derived from `VALID_KINDS` and needs no CLAUDE.md change unless listed.

### Open Questions for Implementer

1. Does Claude Code's PostToolUse response actually carry a child-session identifier (e.g., under `tool_response`)? Empirical verification needed before Option A is viable. Check the kill-analysis referenced in the issue (`autodev-bug2501-kill-analysis.md`) for any captured PostToolUse payload samples.
2. Should `child_session_id` be renamed `agent_id` for fidelity to the Claude Code hook payload if Option B is chosen?
3. Is the backfill feasible from JSONL alone? `SubagentStop` documented sample places child transcripts at `<parent_transcript_path>/subagents/<agent_id>.jsonl`, which is discoverable during backfill.
4. Does the `ll-ctx-stats` per-agent block need to roll up against `subagent_runs`, or is that a separate follow-on (the issue mentions it as "future")?

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

## Status

**Open** | Created: 2026-07-06 | Priority: P3 | Decision Needed: yes (child-session identifier source)

## Session Log
- `/ll:decide-issue` - 2026-07-16T19:41:23 - `c5a83150-c2c4-41fe-8bff-072a77dba866.jsonl`
- `/ll:refine-issue` - 2026-07-16T16:08:30 - `8babd643-3346-4d9e-a0fd-d91a1800504e.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:55 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`