---
id: FEAT-1712
title: LCM-style hierarchical summary DAG over session history
type: FEAT
priority: P3
status: open
captured_at: "2026-05-26T01:31:23Z"
discovered_date: "2026-05-26"
discovered_by: capture-issue
relates_to: [ENH-1710, ENH-1711]
parent: EPIC-1707
blocks: ENH-1906
decision_needed: false
labels:
- feature
- history
- session-store
- context-management
- captured
---

# FEAT-1712: LCM-style hierarchical summary DAG over session history

## Summary

Implement a Lossless Context Management (LCM) layer over `history.db` that maintains a hierarchical DAG of LLM-generated summary nodes over the immutable session JSONL store, enabling month-scale project history navigation without context saturation.

## Motivation

Inspired by the LCM paper (Ehrlich & Blackman, 2026, arXiv:submit/7269166): the immutable session JSONL files already constitute a lossless store, but navigating them for open-ended queries ("what architectural decisions were made on the auth rewrite?") requires the agent to already know what to grep for. A hierarchical DAG of summaries provides multi-resolution access — high-level summaries for orientation, lossless drill-down for verification — without loading the full history into context.

ENH-1710 and ENH-1711 close the cheapest navigation gaps (session→JSONL path, issue→session linkage). This feature is the third and most significant layer: the compaction and retrieval subsystem that makes history queryable at any resolution.

### Why this beats a flat FTS index

- FTS (`search_index`) already exists but returns decontextualized fragments — it lacks the conversational structure (who said what, in response to what, what was decided afterward) needed for meaningful reconstruction.
- Summary nodes provide the multi-resolution map; lossless pointers beneath them allow targeted expansion into originals.
- Matches the LCM paper's result: performance advantage over raw Claude Code emerges above ~32K tokens per query, which is easily reached when spanning multiple sessions.

## Current Behavior

`history.db` exposes only a flat FTS index (`search_index`) over message content. Cross-session, open-ended queries require the agent to know the right search terms up front, and matches return decontextualized fragments stripped of conversational structure (who said what, in response to what, what was decided). The session JSONL files are a lossless store but are only navigable by direct grep — there is no multi-resolution summary layer, so spanning multiple sessions saturates context.

## Expected Behavior

An LCM compaction/retrieval subsystem maintains a hierarchical DAG of `leaf` and `condensed` summary nodes over the immutable JSONL store. Agents traverse the DAG top-down for orientation and drill into lossless originals via `ll-session expand` only where needed. `ll-session grep` returns matches grouped by their covering summary node with lossless back-references, and `ll-history` answers cross-session questions through DAG traversal (falling back to direct JSONL for un-summarized sessions). Compaction runs idempotently during `backfill()` for completed sessions.

## Use Case

A user asks: "Show me all the architectural decisions made while implementing the FSM loop runner." The agent:
1. Traverses the summary DAG from the project root summary downward.
2. Identifies summary nodes tagged with relevant issues/loops.
3. Uses `ll_expand` to drill into specific sessions where needed.
4. Returns a structured reconstruction without loading raw JSONL into context.

## Implementation Steps

### Phase 1 — Schema (depends on ENH-1710)

Add two tables to `history.db` migrations:

```sql
CREATE TABLE summary_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,          -- 'leaf' | 'condensed'
    content TEXT NOT NULL,       -- LLM-generated summary text
    tokens INTEGER,
    parent_id INTEGER REFERENCES summary_nodes(id),
    session_id TEXT,             -- for leaf nodes
    ts_start TEXT,
    ts_end TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE summary_spans (
    summary_id INTEGER REFERENCES summary_nodes(id),
    message_event_id INTEGER REFERENCES message_events(id),
    PRIMARY KEY (summary_id, message_event_id)
);
```

### Phase 2 — Compaction loop

Implement `compact_session(session_id)` in `session_store.py`:
- Groups `message_events` for the session into blocks by token budget (default: 4K tokens per leaf).
- For each block, calls a summarization prompt (level 1 / 2 / deterministic truncation per LCM Algorithm 3).
- Inserts a `leaf` summary node and populates `summary_spans`.
- If the session already has ≥ 2 leaf nodes, creates a `condensed` node summarizing them.

Trigger: called by `backfill()` for completed sessions (those in `sessions` table with `completed_at` set) that have no summary nodes yet.

> ⚠ `sessions.completed_at` does not exist — the `sessions` table has no completion column. See Risks / Open Questions "Completed session detection" before implementing this trigger.

### Phase 3 — Retrieval tools

- `ll_grep(pattern, summary_id?)` — regex search over `message_events` content, results grouped by covering summary node.
- `ll_expand(summary_id)` — returns the full `message_events` covered by a summary node.
- `ll_describe(id)` — metadata for a summary or file ID.
- Expose as `ll-session grep`, `ll-session expand`, `ll-session describe` subcommands.

### Phase 4 — Integration with ll-history

Update `ll-history` to navigate via summary DAG when answering cross-session questions, falling back to direct JSONL for sessions without summaries.

## API/Interface

- New `summary_nodes` and `summary_spans` tables.
- New `compact_session()` public function in `session_store.py`.
- New `ll-session grep / expand / describe` subcommands.
- `ll-history` updated to use DAG traversal.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis (verified against `session_store.py` @ `SCHEMA_VERSION = 9`):_

### Files to Modify

- `scripts/little_loops/session_store.py` — the single source of truth for `history.db`.
  - **Schema**: append **one** new entry to the `_MIGRATIONS` list (current list has 9 entries, indices 0–8; the new entry is **index 9 → v10**) and bump `SCHEMA_VERSION` to `10`. `_apply_migrations()` runs `conn.executescript()` per entry and writes the new version to `meta`. Put both `CREATE TABLE summary_nodes` and `CREATE TABLE summary_spans` in the same v10 block. Use `CREATE TABLE IF NOT EXISTS` + a `CREATE UNIQUE INDEX IF NOT EXISTS` for idempotency, mirroring the v3/v9 dedup-index pattern (`idx_issue_events_dedup`, `idx_corrections_dedup`).
  - **Compaction**: add `compact_session(session_id)` here. It groups `message_events` rows by token budget — note there is **no chunking/token-budget utility in the codebase**; the only token estimate is `len(s) // 4` (`doc_counts.py:check_skill_budget()`) and the only content-truncation is a trailing-slice (`fsm/evaluators.py`). The block-grouping logic must be written from scratch.
  - **Backfill trigger**: wire compaction into `backfill()` (and consider `backfill_incremental()`, used by the session-start hook). `backfill()` signature: `backfill(db, *, issues_dir, loops_dir, jsonl_files, config)`. It currently processes all `jsonl_files` unconditionally with no completeness gate — see the ⚠ open question below about "completed session" detection.
- `scripts/little_loops/cli/session.py` — add `grep`, `expand`, `describe` subparsers. Follow the `_build_parser()` / `_parse_args()` / `main_session()` split already used for `search` / `recent` / `path` / `related` / `backfill`. Reuse shared arg helpers from `cli_args.py` (`add_json_arg()`, `add_db_arg`). Dispatch on `args.command` in `main_session()`, which already wraps work in `cli_event_context(DEFAULT_DB_PATH, "ll-session", sys.argv[1:])`.
- `scripts/little_loops/cli/history.py` — `main_history()` (inline subparsers, no `_build_parser()` extraction). Update to traverse the summary DAG for cross-session questions, falling back to direct JSONL for un-summarized sessions.
- `scripts/little_loops/history_reader.py` — the typed **read-only** query API (opens DB via `file:{db}?mode=ro`, `PRAGMA query_only = ON`). Add DAG-traversal/grep/expand query functions here as dataclasses + functions, following the existing `SearchResult` / `SessionRef` / `sessions_for_issue()` pattern, so both CLIs and skills share one read path.

### LLM Invocation (compaction summarizer)

- **Must** go through `host_runner.resolve_host()` per `.claude/CLAUDE.md` § Host CLI Abstraction — never a `"claude"` literal. The canonical one-shot pattern is in `scripts/little_loops/fsm/evaluators.py:evaluate_llm_structured()`:
  ```python
  from little_loops.host_runner import resolve_host
  inv = resolve_host().build_blocking_json(prompt=summarize_prompt, model=model)
  proc = subprocess.run([inv.binary, *inv.args], capture_output=True, text=True, timeout=timeout)
  ```
- Handle `subprocess.TimeoutExpired`, `FileNotFoundError` (binary not on PATH), `proc.returncode != 0`, and empty-stdout-on-exit-0. Note `ClaudeCodeRunner.build_blocking_json()` **silently drops** `json_schema` (no CLI flag); structured output is not guaranteed under the Claude host — design the summarizer to parse free text or post-validate.

### Dependent / Related Code

- `scripts/little_loops/hooks/session_start.py` — calls `backfill_incremental()` at session start (ENH-1830). If compaction hooks into incremental backfill, this is the latency-sensitive path; keep it opt-in/rate-limited (see Risks).
- `scripts/little_loops/config/features.py:HistoryConfig` — the natural home for a compaction opt-in toggle / rate-limit / token-budget knob (the issue calls for "opt-in or rate-limited"). Add fields here and surface them in `config-schema.json` under the `history` namespace.

### Similar Patterns To Follow

- Migration mechanics: `session_store.py:_MIGRATIONS` (v4 `sessions`, v5 `issue_sessions` VIEW are the closest analogues to adding new tables/relations).
- Subcommand wiring: `cli/session.py` (`path`/`related` are the newest, ENH-1710/1711) and `cli/action.py:main_action()` (`subparsers.required = True` variant).

### Tests

- `scripts/tests/test_session_store.py` — model new tests on `TestBackfill`, `TestSchemaV2`–`TestSchemaV9` (vN→vN+1 migration-idempotency tests), and `TestMineCorrectionsFromMessages`. DB tests use the bare pytest `tmp_path` fixture + `connect(db)` (which calls `ensure_db()`); insert `message_events` rows via raw SQL, then assert on query results. Add a `TestSchemaV10` and a `TestCompactSession` (assert idempotency: compacting twice creates no duplicate `summary_nodes`).
- `scripts/tests/test_ll_session.py` — model `grep`/`expand`/`describe` CLI tests on `TestArgumentParsing` (call `_parse_args()` directly) and `TestMainSession` (`patch("sys.argv", ...)` + `main_session()`).

### Documentation

- `docs/ARCHITECTURE.md` (history.db section), `docs/reference/CLI.md` (`ll-session` subcommands), `docs/reference/API.md` (`session_store` / `history_reader`), `docs/reference/CONFIGURATION.md` (`history.*` namespace).
- `docs/research/LCM-Lossless-Context-Management.md` and `docs/research/LCM-Integration-Brainstorm.md` already exist as the theory/roadmap basis — cross-reference the Algorithm 3 escalation when implementing.

## Acceptance Criteria

- After `backfill()` on a project with ≥ 2 completed sessions, `summary_nodes` contains at least one `condensed` node.
- `ll-session grep "auth middleware"` returns results grouped by summary node with a lossless reference to the originating message.
- `ll-session expand <summary_id>` returns the original messages covered by that summary.
- Compaction is idempotent: running `backfill()` twice does not create duplicate summary nodes.

## Impact

- **Who benefits**: Agents and users running cross-session, open-ended history queries (architectural decisions, multi-session feature work) that today exceed the context window or return unusable FTS fragments.
- **Cross-session query reach**: flat FTS over a single fragment set → multi-resolution DAG traversal that stays usable above ~32K tokens/query (the LCM crossover point), where raw-JSONL navigation degrades.
- **Reconstruction fidelity**: decontextualized fragments → structured summaries with lossless drill-down to originals.
- **Epic role**: Completes the third and most significant layer of EPIC-1707's history-navigation stack (after ENH-1710 session→JSONL path and ENH-1711 issue→session linkage); unblocks ENH-1906.
- **Cost**: Additive only — text-only summaries, no JSONL duplication; one LLM compaction call per ~4K-token block, confined to opt-in/rate-limited background `backfill()`.

## Risks / Open Questions

- **Storage cost**: Summaries are small (text only); the underlying JSONL is never duplicated. Acceptable.
- **LLM compaction cost**: One compaction call per ~4K-token block. Reasonable for background backfill; should be opt-in or rate-limited for large histories.
- **SQLite vs. PostgreSQL**: LCM paper uses embedded PostgreSQL for referential integrity. SQLite with WAL mode and `PRAGMA foreign_keys = ON` should suffice for the project-local scale here.
- **Compaction quality**: Three-level escalation (LCM Algorithm 3) guards against divergent summaries. Deterministic truncation at level 3 guarantees convergence.

### Codebase Research Findings — Open Questions (added by `/ll:refine-issue`)

- ⚠ **"Completed session" detection has no existing mechanism.** Phase 2's trigger and the first Acceptance Criterion both reference *"sessions ... with `completed_at` set"*, but the `sessions` table (`session_store.py` v4) has **only** `session_id, jsonl_path, started_at, project_path` — there is **no `completed_at` column on `sessions`**. `completed_at` exists only on `issue_events`. `backfill()` processes all `jsonl_files` unconditionally with no completeness gate. Options: (a) add a `completed_at`/`last_seen` column to `sessions` and define when a session is "done" (e.g., no new events for N hours, or session_id ≠ the current live session), or (b) compact every session present in `sessions` and rely on idempotency to re-compact when more messages arrive.
  > **Selected:** Option B (idempotent compaction of all sessions) — compact every session in `sessions` unconditionally; guard duplicates with `INSERT OR IGNORE` + a `UNIQUE INDEX` on `summary_nodes`. All three required mechanisms already exist (`INSERT OR IGNORE` + dedup index in v3/v9, unconditional `_backfill_*` iteration, mtime-gated incremental trigger); Option A requires a new write path and a "session ended" signal that does not exist anywhere in the codebase.
- ⚠ **`message_events` holds user messages only** (`id, ts, session_id, content` — no `role` column; assistant turns are not stored, assistant tool-use goes to `tool_events`). The Motivation/Reconstruction-fidelity claims ("who said what, in response to what, what was decided afterward") **cannot be satisfied from `message_events` alone** — it has no assistant side of the conversation. Options: (a) summarize from user messages only (degraded fidelity), or (b) read the assistant turns directly from the source JSONL (path available via `sessions.jsonl_path`) during `compact_session()`.
  > **Selected:** Option A (user messages only, from `message_events`) — meets all four stated acceptance criteria; fits the DB-only query pattern used throughout `history_reader.py` with zero new I/O infrastructure. Option B would be the first function in `session_store.py` to combine DB queries with on-disk JSONL reads in one call, adding JSONL-unavailability failure modes and interleaving complexity; full-fidelity assistant-turn inclusion can be added in a follow-on if needed.
- **No WAL / `PRAGMA foreign_keys` today.** The Risks note assumes "SQLite with WAL mode and `PRAGMA foreign_keys = ON`", but neither is currently set — `connect()` / `ensure_db()` call bare `sqlite3.connect()`. If `summary_nodes.parent_id` / `summary_spans` FK integrity is to be enforced, the FK pragma must be **added** (it is off by default in SQLite) and tested; otherwise the `REFERENCES` clauses are decorative.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-03.

#### Decision 1 — Completed session detection

**Selected**: Option B — Idempotent compaction of all sessions

**Reasoning**: Every `_backfill_*` function in `session_store.py` is unconditional and idempotent via `INSERT OR IGNORE` + `UNIQUE INDEX` (v3 `idx_issue_events_dedup`, v9 `idx_corrections_dedup`, `_backfill_sessions` PRIMARY KEY). Option B is a direct extension of this established pattern. Option A requires a new `completed_at` write path on a currently insert-only table and a "session ended" detection signal that does not exist (no `SessionEnd` event, no authoritative current-session env var).

#### Scoring Summary — Decision 1

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (add `completed_at` column) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |
| **Option B (idempotent, no gate)** | **3/3** | **3/3** | **3/3** | **2/3** | **11/12** |

**Key evidence**:
- Option A: No write path to `sessions`, no `SessionEnd` hook, live-session detection via mtime heuristic only (`session_log.py:get_current_session_jsonl`)
- Option B: `INSERT OR IGNORE` + dedup index used by all 5 existing `_backfill_*` functions; v10 migration guidance in issue already prescribes this exact pattern

---

#### Decision 2 — Compaction summarizer input

**Selected**: Option A — Summarize from `message_events` (user messages only)

**Reasoning**: All four stated acceptance criteria can be met using `message_events` alone. The DB-only query pattern is universal throughout `history_reader.py` (opened with `mode=ro` + `PRAGMA query_only`); mixing DB reads with JSONL I/O inside `session_store.py` would be the first instance of this pattern and introduces JSONL-unavailability failure modes. Full-fidelity assistant-turn inclusion can be added in a follow-on feature without breaking the compaction schema.

#### Scoring Summary — Decision 2

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| **Option A (user messages, DB only)** | **3/3** | **3/3** | **3/3** | **3/3** | **12/12** |
| Option B (JSONL read for assistant turns) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- Option A: `mine_corrections_from_messages()` query pattern (`SELECT ts, session_id, content FROM message_events`) is identical to what `compact_session()` needs; test fixture pattern (`TestMineCorrectionsFromMessages`) is directly reusable
- Option B: `sessions.jsonl_path` is never currently resolved to an `open()` call in production code; `user_messages._extract_turn_pairs()` provides the interleaving primitive but importing it into `session_store.py` would add a cross-module dependency

## Status

---

open

## Session Log
- `/ll:decide-issue` - 2026-06-04T02:50:10 - `3adfb92d-1176-4e1a-8596-011438501f76.jsonl`
- `/ll:refine-issue` - 2026-06-04T02:42:31 - `44abecab-4e39-43c4-a482-b463053f301b.jsonl`
- `/ll:format-issue` - 2026-06-04T02:36:34 - `baec7ab9-fb68-4a18-b085-34f22f799599.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:42 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:07 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:capture-issue` - 2026-05-26T01:31:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d0765b0-9906-45d9-a15b-8eadbab154a7.jsonl`
