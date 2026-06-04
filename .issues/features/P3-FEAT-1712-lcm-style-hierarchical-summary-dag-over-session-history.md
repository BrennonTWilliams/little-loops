---
id: FEAT-1712
title: LCM-style hierarchical summary DAG over session history
type: FEAT
priority: P3
status: open
captured_at: '2026-05-26T01:31:23Z'
discovered_date: '2026-05-26'
discovered_by: capture-issue
relates_to:
- ENH-1710
- ENH-1711
parent: EPIC-1707
blocks: ENH-1906
decision_needed: false
labels:
- feature
- history
- session-store
- context-management
- captured
confidence_score: 98
outcome_confidence: 77
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. **Config serialization** — add the new `HistoryConfig` compaction fields to `config/core.py:BRConfig.to_dict()` `"history"` block (~line 643) so they round-trip; add the same fields' definitions to `config-schema.json` under `history.properties` (required — `additionalProperties: false`).
6. **Public-API exports** — add `compact_session` to `session_store.py`'s `__all__` and module docstring; add the new DAG functions/dataclasses to `history_reader.py`'s module docstring.
7. **Fix breaking tests** — update the three `SCHEMA_VERSION == 9` literals in `test_session_store.py` to `10`; reconcile `test_backfill_missing_sources_is_noop` and `test_backfill_reports_messages_count` if `backfill()` gains a compaction count.
8. **New test coverage** — add `TestSchemaV10` + `TestCompactSession` (`test_session_store.py`), grep/expand/describe tests (`test_ll_session.py`), DAG-query tests (`test_history_reader.py`), `HistoryConfig` compaction-field tests (`test_config.py`), and a `history.compaction*` schema-declaration test (`test_config_schema.py`).
9. **Doc + self-doc sync** — update `.claude/CLAUDE.md`, `commands/help.md`, `CONTRIBUTING.md` (stale `v1–v9` / reader counts), `skills/configure/areas.md` history area, and the `cli/session.py` docstring + `_build_parser()` epilog; add the v10 schema row and `compact_session()` row to `docs/ARCHITECTURE.md`.

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

    **Pinned block-grouping algorithm** (resolves the "write from scratch" risk; greedy single-pass, deterministic):
    1. Token estimator: `est(s) = len(s) // 4` — reuse the exact `doc_counts.py:check_skill_budget()` heuristic; do **not** add a tokenizer dependency.
    2. Query `SELECT id, ts, content FROM message_events WHERE session_id = ? ORDER BY ts, id` (mirrors `mine_corrections_from_messages()` per Decision 2 — user messages only).
    3. Greedy accumulation into a current block: maintain a running `block_tokens`. For each row, if `block_tokens + est(content) > budget` **and the block is non-empty**, flush the current block as a `leaf` node, then start a new block with this row. Otherwise append the row to the block and add to `block_tokens`. A single row whose `est(content) > budget` becomes its own block (never split mid-message — preserves the lossless `summary_spans` back-reference).
    4. `budget` defaults to `4096` and is read from `HistoryConfig.compaction` (see config wiring below).
    5. Per flushed block: insert one `leaf` `summary_nodes` row (with `session_id`, `ts_start` = first row ts, `ts_end` = last row ts), then one `summary_spans` row per covered `message_event_id`. Use `INSERT OR IGNORE` against the `UNIQUE INDEX` for idempotency (Decision 1).
    6. After all leaves for the session exist, if there are ≥ 2 leaf nodes, insert one `condensed` node summarizing the leaf summaries, with each leaf's `parent_id` left null and the condensed node covering them via its own `summary_spans` (or a `parent_id` back-link from leaves — pick one and assert it in `TestCompactSession`).
  - **Backfill trigger**: wire compaction into `backfill()` (and consider `backfill_incremental()`, used by the session-start hook). `backfill()` signature: `backfill(db, *, issues_dir, loops_dir, jsonl_files, config)`. It currently processes all `jsonl_files` unconditionally with no completeness gate — see the ⚠ open question below about "completed session" detection.
- `scripts/little_loops/cli/session.py` — add `grep`, `expand`, `describe` subparsers. Follow the `_build_parser()` / `_parse_args()` / `main_session()` split already used for `search` / `recent` / `path` / `related` / `backfill`. Reuse shared arg helpers from `cli_args.py` (`add_json_arg()`, `add_db_arg`). Dispatch on `args.command` in `main_session()`, which already wraps work in `cli_event_context(DEFAULT_DB_PATH, "ll-session", sys.argv[1:])`.
- `scripts/little_loops/cli/history.py` — `main_history()` (inline subparsers, no `_build_parser()` extraction). Update to traverse the summary DAG for cross-session questions, falling back to direct JSONL for un-summarized sessions.
- `scripts/little_loops/history_reader.py` — the typed **read-only** query API (opens DB via `file:{db}?mode=ro`, `PRAGMA query_only = ON`). Add DAG-traversal/grep/expand query functions here as dataclasses + functions, following the existing `SearchResult` / `SessionRef` / `sessions_for_issue()` pattern, so both CLIs and skills share one read path.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py` — `BRConfig.to_dict()` enumerates the `"history"` block key-by-key (~line 643). The new `HistoryConfig` compaction fields **must** be serialized here, or `to_dict()` round-trips will drop them and `test_config.py:TestBRConfigHistoryIntegration.test_history_to_dict_round_trip` will fail. `HistoryConfig.from_dict()` is lenient (ignores unknown keys), so the read path won't break — but the write path here is the coupling. [Agent 2 finding]
- `scripts/little_loops/session_store.py` — beyond the schema/compaction logic already noted, update the module-level `__all__` list (~lines 50–65) and module docstring (~lines 17–33) to export `compact_session` if it is public API. [Agent 2 finding]
- `scripts/little_loops/history_reader.py` — update the module-level docstring (~lines 17–25, which enumerates exported functions/dataclasses) to list the new DAG-traversal/grep/expand functions. [Agent 2 finding]

### LLM Invocation (compaction summarizer)

- **Must** go through `host_runner.resolve_host()` per `.claude/CLAUDE.md` § Host CLI Abstraction — never a `"claude"` literal. The canonical one-shot pattern is in `scripts/little_loops/fsm/evaluators.py:evaluate_llm_structured()`:
  ```python
  from little_loops.host_runner import resolve_host
  inv = resolve_host().build_blocking_json(prompt=summarize_prompt, model=model)
  proc = subprocess.run([inv.binary, *inv.args], capture_output=True, text=True, timeout=timeout)
  ```
- Handle `subprocess.TimeoutExpired`, `FileNotFoundError` (binary not on PATH), `proc.returncode != 0`, and empty-stdout-on-exit-0. Note `ClaudeCodeRunner.build_blocking_json()` **silently drops** `json_schema` (no CLI flag); structured output is not guaranteed under the Claude host — design the summarizer to parse free text or post-validate.

  **Pinned summarizer output contract** (resolves the structured-output-gap risk):
  - The summarizer prompt requests **plain prose** (no JSON). `compact_session()` stores `proc.stdout.strip()` directly as `summary_nodes.content`. There is no schema to parse, so the dropped `json_schema` is irrelevant.
  - **Post-validation**: accept the summary only if non-empty after `.strip()`. On any failure path (timeout, `returncode != 0`, empty stdout, or `FileNotFoundError`), fall back to **deterministic truncation** — concatenate the block's `message_events.content` and trailing-slice to the token budget (LCM Algorithm 3 level-3 convergence guarantee; mirrors the existing `fsm/evaluators.py` truncation). This makes compaction total: a `leaf` node is always produced, so `backfill()` never blocks on LLM availability and idempotency still holds.
  - This keeps `compact_session()` DB-and-subprocess only — no JSONL I/O — consistent with Decision 2.

### Dependent / Related Code

- `scripts/little_loops/hooks/session_start.py` — calls `backfill_incremental()` at session start (ENH-1830). If compaction hooks into incremental backfill, this is the latency-sensitive path; keep it opt-in/rate-limited (see Risks).
- `scripts/little_loops/config/features.py:HistoryConfig` — the natural home for a compaction opt-in toggle / rate-limit / token-budget knob (the issue calls for "opt-in or rate-limited"). Add fields here and surface them in `config-schema.json` under the `history` namespace.

### Similar Patterns To Follow

- Migration mechanics: `session_store.py:_MIGRATIONS` (v4 `sessions`, v5 `issue_sessions` VIEW are the closest analogues to adding new tables/relations).
- Subcommand wiring: `cli/session.py` (`path`/`related` are the newest, ENH-1710/1711) and `cli/action.py:main_action()` (`subparsers.required = True` variant).

### Tests

- `scripts/tests/test_session_store.py` — model new tests on `TestBackfill`, `TestSchemaV2`–`TestSchemaV9` (vN→vN+1 migration-idempotency tests), and `TestMineCorrectionsFromMessages`. DB tests use the bare pytest `tmp_path` fixture + `connect(db)` (which calls `ensure_db()`); insert `message_events` rows via raw SQL, then assert on query results. Add a `TestSchemaV10` and a `TestCompactSession` (assert idempotency: compacting twice creates no duplicate `summary_nodes`).
- `scripts/tests/test_ll_session.py` — model `grep`/`expand`/`describe` CLI tests on `TestArgumentParsing` (call `_parse_args()` directly) and `TestMainSession` (`patch("sys.argv", ...)` + `main_session()`).

_Wiring pass added by `/ll:wire-issue`:_

**Tests that WILL BREAK on the v10 bump (update required):**
- `scripts/tests/test_session_store.py` — three hard-coded `assert SCHEMA_VERSION == 9` / `assert int(row[0]) == 9` assertions break when `SCHEMA_VERSION` → 10: `TestSchemaV6.test_schema_version_is_seven` (~line 1089), `TestCliEventContext.test_schema_v8_cli_events_table_exists` (~line 1406), and `TestSchemaV9.test_schema_version_is_nine` (~line 1490). Update all three to `10`. (Tests that assert against the `SCHEMA_VERSION` *constant* rather than a literal — e.g. `TestEnsureDb.test_applies_schema_version` — adapt automatically.) [Agent 2 + 3 finding]
- `scripts/tests/test_session_store.py:TestBackfill.test_backfill_missing_sources_is_noop` (~line 268) — asserts an exact `counts == {...}` dict. If `backfill()` gains a `"summaries"`/compaction key, this equality and the `Backfilled {sum(counts.values())}` total break. [Agent 2 + 3 finding]
- `scripts/tests/test_ll_session.py:TestMainSession.test_backfill_reports_messages_count` — asserts the hard-coded total `"Backfilled 12"` (= `sum(counts.values())`) and exact `messages=`/`sessions=`/`corrections=` segments; a new compaction count shifts the total. Also update the `main_session()` backfill-branch format string in `cli/session.py` if a new key should display. [Agent 2 finding]
- `scripts/tests/test_hook_session_start.py:TestSessionStartBackfillThread` — `monkeypatch.setattr(ss, "backfill_incremental", ...)`. If compaction is wired into `backfill_incremental()` (the latency-sensitive session-start path), this coupling and the thread test must be revisited. [Agent 2 finding]

**New test files needed (not in known tests):**
- `scripts/tests/test_history_reader.py` — add tests for the new DAG-traversal/grep/expand query functions. Follow the `TestMissingDatabase` / `TestEmptyTables` guard patterns and the `TestProjectDigest` `_insert_X` + populated-data pattern. [Agent 3 finding]
- `scripts/tests/test_issue_history_cli.py` — if `main_history()` gains DAG-aware behavior or subcommands, add coverage modeled on `TestMainHistoryIntegration` / `TestSessionsSubcommand` (`patch.object(sys, "argv", ["ll-history", "--config", ...])` + `main_history()`). [Agent 3 finding]
- `scripts/tests/test_config.py` — add `TestHistoryConfig` assertions for the new compaction fields (model on `test_flat_key_override`) and extend `TestBRConfigHistoryIntegration.test_history_to_dict_round_trip` to assert the new keys appear in the serialized `history` block. [Agent 2 + 3 finding]
- `scripts/tests/test_config_schema.py` — extend `TestConfigSchema.test_history_in_schema` (or add a sibling) to assert the new `history.compaction*` key(s) are declared. **Required**: `history` uses `additionalProperties: false`, so an undeclared key makes any config that sets it fail validation. Model on `test_commands_recursive_refine_in_schema`. [Agent 2 + 3 finding]

### Documentation

- `docs/ARCHITECTURE.md` (history.db section), `docs/reference/CLI.md` (`ll-session` subcommands), `docs/reference/API.md` (`session_store` / `history_reader`), `docs/reference/CONFIGURATION.md` (`history.*` namespace).
- `docs/research/LCM-Lossless-Context-Management.md` and `docs/research/LCM-Integration-Brainstorm.md` already exist as the theory/roadmap basis — cross-reference the Algorithm 3 escalation when implementing.

_Wiring pass added by `/ll:wire-issue` — non-`docs/` documentation that enumerates `ll-session` subcommands or schema versions and will go stale:_
- `.claude/CLAUDE.md` — `## CLI Tools` section: the `ll-session` entry lists `search --fts / recent --kind / recent --issue <ID> / backfill / path <session_id>` subcommands. Add `grep` / `expand` / `describe`. [Agent 2 finding]
- `commands/help.md` — the `ll-session` line enumerates subcommands in its description; add the three new ones. [Agent 2 finding]
- `CONTRIBUTING.md` — two stale annotations: the `session_store.py` comment reads `… v1–v9 migrations` (becomes `v1–v10`), and the `history_reader.py` comment reads `5 query functions, 5 dataclasses` (counts increase with the new DAG functions/dataclasses). [Agent 2 finding]
- `skills/configure/areas.md` — the `history` area (~line 1238) describes `history.db` config options by name; add the new compaction tunables (opt-in / rate-limit / token-budget) or update existing option descriptions. [Agent 2 finding]
- `cli/session.py` self-documentation — the module-level docstring and `_build_parser()` epilog both enumerate the 5 current subcommands with example invocations; extend both for `grep`/`expand`/`describe` (in-file, but doc-coupled). [Agent 2 finding]
- `docs/ARCHITECTURE.md` — beyond the history.db section already noted: add a **v10 row** to the schema-version table (`summary_nodes` + `summary_spans`) and a `compact_session()` row to the key-function reference table; revisit the "no manual backfill needed" closing paragraph if compaction joins `backfill()`. [Agent 2 finding]

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
  > **Resolved (Decision 3):** Leave FK references decorative — do **not** enable `PRAGMA foreign_keys` and do **not** switch to WAL. `foreign_keys` is a per-connection pragma (off by default), so enforcing it would mean setting it on every `connect()` — a global behavior change to a 9-migration, insert-only store, out of scope for this feature. Integrity is guaranteed at the application layer instead: `compact_session()` is the sole writer, controls insert ordering (leaf nodes before the condensed node that references them; the summary node before its `summary_spans` rows), and dedups with `INSERT OR IGNORE` + `UNIQUE INDEX` — the same mechanism Decision 1 relies on. The `REFERENCES` clauses remain as schema documentation. WAL is a separate cross-cutting concern (a future ENH if concurrent-writer contention is ever observed); the existing daemon-thread `backfill_incremental()` already runs without it. See Decision 3 below.

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

---

#### Decision 3 — Referential integrity & journal mode

Decided by `/ll:confidence-check` on 2026-06-03 (resolving the third open question from `/ll:refine-issue`).

**Selected**: Decorative FK references — no `PRAGMA foreign_keys`, no WAL

**Reasoning**: `PRAGMA foreign_keys` is a per-connection setting (off by default in SQLite) and is **not** persisted in the database file. Enforcing it would require setting it on every `connect()` call, which changes behavior for all 9 prior migrations' worth of insert paths in a currently insert-only store — a global, out-of-scope change with latent-ordering risk. Integrity is instead guaranteed at the application layer: `compact_session()` is the sole writer to `summary_nodes`/`summary_spans`, controls insert ordering (leaf nodes → condensed node; summary node → spans), and dedups via `INSERT OR IGNORE` + `UNIQUE INDEX` — identical to the mechanism Decision 1 already commits to. WAL mode is a separate cross-cutting concern (future ENH if writer contention is observed); the daemon-thread `backfill_incremental()` already runs without it today.

#### Scoring Summary — Decision 3

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| **Decorative FKs (no pragma, no WAL)** | **3/3** | **3/3** | **3/3** | **3/3** | **12/12** |
| Enable `foreign_keys = ON` + WAL globally | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Decorative: `connect()`/`ensure_db()` (`session_store.py:362,376`) call bare `sqlite3.connect()`; no existing test asserts FK enforcement; `INSERT OR IGNORE` + dedup index is the universal integrity pattern across all `_backfill_*` functions
- Enforce: per-connection pragma must be re-set on every connection; turning it on retroactively could surface insert-ordering violations in existing write paths that have never run under FK enforcement

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-03; revised same day after resolving the FK/WAL open question (Decision 3) and pinning the block-grouping + summarizer algorithms._

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 77/100 → MODERATE (top of band; 3 points below HIGH)

### Resolved Since Initial Check

- **FK/WAL ambiguity** → Decision 3: decorative FK references, no pragma, no WAL (Criterion C: 18 → 25).
- **compact_session() block-grouping "from scratch"** → pinned greedy single-pass algorithm in the Integration Map (Criterion A depth: Moderate → Local).
- **Summarizer structured-output gap** → pinned plain-prose contract with deterministic-truncation fallback in the LLM Invocation section.

### Remaining Outcome Risk Factors

- **Broad change surface (18+ sites)** — the sole remaining drag on outcome confidence (Criterion A breadth: 0/12). Each site is now individually straightforward; the risk is coordination, not per-site complexity. Plan staged commits (schema+breaking-tests → compaction → retrieval+integration), or split out the compaction sub-issue to raise per-issue breadth. This is the only lever the algorithm pins did **not** move.
- **4+ breaking tests must be updated in tandem with the v10 migration** — hard-coded `SCHEMA_VERSION == 9` at test_session_store.py:1089, 1406, 1490 and `Backfilled 12` in test_ll_session.py will fail on the first test run unless updated alongside the migration. Mitigation: land the v10 migration + these fixes as the opening commit so the suite stays green.

## Status

---

open

## Session Log
- `/ll:confidence-check` - 2026-06-03T00:00:00 - `9fef4b9d-8625-4d9d-bbfe-e80b3b41de49.jsonl`
- `/ll:wire-issue` - 2026-06-04T02:58:34 - `c800cb86-9c2d-4ca5-9d7f-f62db6d3e2cc.jsonl`
- `/ll:decide-issue` - 2026-06-04T02:50:10 - `3adfb92d-1176-4e1a-8596-011438501f76.jsonl`
- `/ll:refine-issue` - 2026-06-04T02:42:31 - `44abecab-4e39-43c4-a482-b463053f301b.jsonl`
- `/ll:format-issue` - 2026-06-04T02:36:34 - `baec7ab9-fb68-4a18-b085-34f22f799599.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:42 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:07 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:capture-issue` - 2026-05-26T01:31:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d0765b0-9906-45d9-a15b-8eadbab154a7.jsonl`
