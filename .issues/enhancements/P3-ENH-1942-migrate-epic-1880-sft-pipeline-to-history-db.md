---
id: ENH-1942
title: Migrate EPIC-1880 SFT pipeline from JSONL to history.db via history_reader.py
type: ENH
priority: P3
status: done
captured_at: '2026-06-04T18:00:00Z'
completed_at: '2026-06-04'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1880
relates_to: [ENH-1941, ENH-1710, ENH-1827, FEAT-1826, EPIC-1707]
labels:
  - epic: EPIC-1880
  - enhancement
  - sft
  - history-db
  - session-logs
  - multi-host
  - captured
---

# ENH-1942: Migrate EPIC-1880 SFT pipeline from JSONL to history.db via history_reader.py

## Summary

Add an `assistant_messages` table to `history.db` (schema v11), extend the backfill system to populate it, and add a `conversation_turns()` function to `history_reader.py` so the EPIC-1880 SFT pipeline reads conversation turn-pairs exclusively from the database. Keep the existing `user_messages.py` JSONL code as a graceful-degradation fallback, following the DB-first-then-files pattern established by `ll-history`.

## Context

EPIC-1880's SFT pipeline currently reads Claude Code session JSONL files directly via `user_messages.extract_conversation_turns()`. This has two problems:

1. **It bypasses `history.db` entirely.** The database already stores user messages (`message_events`), tool calls (`tool_events`), file modifications (`file_events`), user corrections (`user_corrections`), and issue outcomes (`issue_events`). But the SFT pipeline's core ingest — conversation turn-pairs — reads raw JSONL, so it can't join against any of this structured metadata. ENH-1941 (quality-signal filtering) is designed assuming DB-sourced turns; with JSONL-sourced turns, the enrich state must cross-join two data sources by session ID.

2. **It's host-coupled.** `get_project_folder()` hardcodes `~/.claude/projects/<encoded-path>/`. When Codex and Pi support land, their session logs will live at different paths. The `history.db` read path (`history_reader.py`) is already host-agnostic — it queries normalized SQL rows regardless of which host wrote them. The backfill layer is the only host-specific piece, and it's already factored as per-host adapter functions.

The critical gap: `message_events` only stores user messages. The backfill code in `_backfill_tool_events()` extracts `tool_use` blocks from assistant records but **discards the assistant's text responses** — the other half of every conversation turn. There is no `assistant_messages` table.

## Motivation

### Why not a new `session_reader.py` module with an ABC?

The original Option C design proposed a `SessionReader` abstract base class with pluggable backends (`DbSessionReader`, `JsonlSessionReader`, future `CodexSessionReader`, `PiSessionReader`). This was rejected in favor of folding the read API into the existing `history_reader.py` for three reasons:

1. **Premature abstraction.** There are only two concrete implementations right now (DB and JSONL), and both read the same Claude Code JSONL shape (one via backfill, one directly). The ABC pays off only when host log *formats* diverge materially — and we don't know yet whether Codex/Pi will use a different format or just a different directory layout.

2. **Consistent with existing idioms.** `ll-history` already uses a DB-first-then-files fallback pattern (`scan_completed_issues_from_db()` → `scan_completed_issues()`). `history_reader.py` already owns the typed read-only query API for `history.db`. Adding `conversation_turns()` there follows the established layering instead of creating a competing read-side entry point.

3. **Less throwaway code.** A phased approach (DB ingest first → ABC layer later) avoids writing `extract_conversation_turns_from_db()` only to immediately wrap it behind an abstraction in the next issue. The function in `history_reader.py` is the stable API; an ABC can be introduced later if/when host log formats actually diverge.

### Why now?

ENH-1941 (quality-signal filtering) and FEAT-1826 (the `sft-corpus` FSM loop) are both designed around DB-sourced conversation turns. Shipping them with JSONL-sourced turns means either (a) building a dual-source join in the `enrich` state, or (b) deferring the DB integration and shipping a pipeline that can't use quality signals. Neither is attractive. Doing this migration first gives both downstream issues a clean, single-source architecture.

## Current Behavior

```
extract_conversation_turns()
  └─ glob("~/.claude/projects/<encoded>/*.jsonl")
       └─ parse JSONL records
            └─ _extract_turn_pairs()
                 └─ return list[list[tuple[str, str]]]  # (role, content)
```

- `_backfill_messages()` only extracts `type == "user"` records → `message_events`
- `_backfill_tool_events()` extracts `tool_use` blocks from `type == "assistant"` records → `tool_events`
- Assistant text blocks are parsed but immediately discarded during backfill
- `extract_conversation_turns()` is the **only** code path that reads assistant text — and it reads JSONL directly

## Expected Behavior

```
conversation_turns()  [in history_reader.py]
  └─ SELECT u.content, a.content
     FROM message_events u
     JOIN assistant_messages a USING (session_id)
     WHERE a.ts BETWEEN u.ts AND ...
     ORDER BY u.ts
  └─ graceful degradation: return [] if history.db missing

extract_conversation_turns()  [in user_messages.py, delegated]
  └─ try: return history_reader.conversation_turns(...)
     except/empty: fall back to JSONL parsing (existing code)
```

- `_backfill_assistant_messages()` extracts text blocks from `type == "assistant"` records → `assistant_messages`
- `history_reader.conversation_turns()` queries the DB for turn-pairs
- `user_messages.extract_conversation_turns()` becomes a delegation wrapper: DB first, JSONL fallback
- `ll-messages --sft-format` gains a `--reader db|jsonl|auto` flag (default: `auto` = DB first)

## API/Interface

### New Database Table

```sql
CREATE TABLE assistant_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_use_count INTEGER DEFAULT 0
);
CREATE INDEX idx_assistant_messages_session_ts
    ON assistant_messages(session_id, ts);
```

### New Function in `history_reader.py`

```python
def conversation_turns(
    db_path: str | Path,
    since: datetime | None = None,
    context_window: int = 3,
) -> list[list[tuple[str, str]]]:
    """Return conversation turn-pair windows from history.db.

    Returns [] when the database is missing, empty, or predates schema v11.
    """
```

### Modified Function in `user_messages.py`

```python
def extract_conversation_turns(
    ...,
    reader: str = "auto",  # new parameter: "auto" | "db" | "jsonl"
) -> list[list[tuple[str, str]]]:
    """DB-first delegation wrapper; falls back to JSONL parsing."""
```

### New CLI Flag on `ll-messages`

```
ll-messages --sft-format chatml --reader auto    # default: DB first, JSONL fallback
ll-messages --sft-format chatml --reader db      # DB only, error if unavailable
ll-messages --sft-format chatml --reader jsonl   # JSONL only (current behavior)
```

## Design Decisions

### 1. `assistant_messages` table shape

```sql
CREATE TABLE assistant_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,                -- ISO 8601 timestamp
    session_id TEXT NOT NULL,        -- Claude Code session ID
    content TEXT NOT NULL,           -- concatenated text blocks from assistant response
    tool_use_count INTEGER DEFAULT 0 -- number of tool_use blocks in this message
);
CREATE INDEX idx_assistant_messages_session_ts
    ON assistant_messages(session_id, ts);
```

**Why concatenated text blocks and not per-block rows?** The `_extract_turn_pairs()` function already concatenates assistant text blocks with `"\n\n"`. Storing the concatenated result matches the existing SFT output shape exactly. Per-block rows would require the read query to reconstruct the concatenation, adding complexity for no benefit — the SFT pipeline only needs the full assistant text, not individual blocks.

**Why `tool_use_count` and not the tool_use blocks themselves?** Tool calls are already normalized into `tool_events`. Duplicating them in `assistant_messages` would create a maintenance burden (two tables to keep in sync). The count column enables filter predicates like `min_tool_invocations` (ENH-1941) without a JOIN.

### 2. Turn-pair reconstruction strategy

Two approaches for pairing user messages with their assistant responses:

**Approach A: Temporal adjacency.** ORDER BY `ts`, pair each user message with all assistant messages until the next user message. This matches the current `_extract_turn_pairs()` algorithm exactly.

**Approach B: Message sequence numbers.** Add a `seq` column to both `message_events` and `assistant_messages` during backfill, then pair by adjacent sequence numbers.

**Decision: Approach A** (temporal adjacency). It requires no schema changes to existing tables, works correctly for all existing data (the backfill processes records in file order), and reproduces the exact behavior of `_extract_turn_pairs()`. The edge case of interleaved sessions (two sessions with overlapping timestamps) is handled by filtering on `session_id`.

### 3. Graceful degradation pattern

Following the existing pattern in `history_reader.py` (all query functions return empty lists when the DB is missing or lacks required tables):

```python
def conversation_turns(
    db_path: str | Path,
    since: datetime | None = None,
    context_window: int = 3,
) -> list[list[tuple[str, str]]]:
    """Return conversation turn-pair windows from history.db.

    Returns [] when the database is missing, empty, or predates schema v11.
    Callers should fall back to JSONL parsing in that case.
    """
```

The fallback in `user_messages.extract_conversation_turns()`:
1. Try `history_reader.conversation_turns()` with the project's `history.db`
2. If it returns a non-empty list, use it
3. If it returns `[]`, fall through to the existing JSONL parsing code
4. Log a one-time warning: "history.db missing or predates v11; falling back to JSONL parsing. Run `ll-session backfill` to migrate."

### 4. `--reader` flag on `ll-messages`

```
ll-messages --sft-format chatml --reader auto    # default: DB first, JSONL fallback
ll-messages --sft-format chatml --reader db      # DB only, error if unavailable
ll-messages --sft-format chatml --reader jsonl   # JSONL only, current behavior
```

`auto` is the default and matches the delegation wrapper behavior.

## Implementation Steps

### 1. Schema v11 migration (`session_store.py`)

- Add migration 11 to `_MIGRATIONS`: CREATE TABLE `assistant_messages` + index
- Bump `CURRENT_SCHEMA_VERSION` to 11
- Add `has_table()` helper check for graceful degradation

### 2. Backfill function (`session_store.py`)

- Add `_backfill_assistant_messages(conn, jsonl_files)` — mirrors `_backfill_messages()` but selects `type == "assistant"` records
- Extract text blocks from `message.content` (same concatenation logic as `_extract_turn_pairs`)
- Count `tool_use` blocks and store in `tool_use_count`
- Insert into `assistant_messages` + index into FTS `search_index`
- Wire into `backfill()` and `backfill_incremental()`

### 3. `conversation_turns()` read function (`history_reader.py`)

- Add `conversation_turns(db_path, since, context_window)` function
- Implement temporal-adjacency pairing via SQL (or in-Python pairing over ordered query results)
- Return `list[list[tuple[str, str]]]` — same shape as `user_messages.extract_conversation_turns()`
- Graceful degradation: return `[]` if DB missing, empty, or schema < 11

### 4. Delegate in `user_messages.py`

- Add `_db_conversation_turns_fallback()` helper that wraps `history_reader.conversation_turns()`
- Modify `extract_conversation_turns()` to try DB first, fall back to existing JSONL code
- Add `reader: str = "auto"` parameter to `extract_conversation_turns()`
- Add deprecation notice to the function docstring: JSONL direct reading is still supported but DB is preferred
- Do NOT remove or modify `get_project_folder()`, `extract_user_messages()`, or `_extract_turn_pairs()` — they remain as the JSONL fallback path and are used by non-SFT consumers (`ll-logs`, `ll-messages` without `--sft-format`)

### 5. Wire `ll-messages --reader` flag (`cli/messages.py`)

- Add `--reader {auto,db,jsonl}` argument (default: `auto`)
- Pass through to `extract_conversation_turns(reader=...)`
- `db`: error if `history_reader.conversation_turns()` returns `[]`
- `jsonl`: skip DB, use existing JSONL path directly

### 6. Tests

- **`test_assistant_messages_migration.py`**: verify v11 migration creates table + index, verify upgrade from v10
- **`test_backfill_assistant_messages.py`**: mock JSONL with mixed user/assistant/tool_use records, verify correct extraction
- **`test_conversation_turns_from_db.py`**: populate DB with known turn-pairs, verify output matches expected windows
- **`test_conversation_turns_degradation.py`**: missing DB → `[]`, missing table → `[]`, empty DB → `[]`
- **`test_extract_conversation_turns_fallback.py`**: verify `user_messages.extract_conversation_turns()` falls back to JSONL when DB returns `[]`

### 7. Documentation

- Update `docs/ARCHITECTURE.md` — add `assistant_messages` to schema diagram, document backfill flow
- Update `docs/reference/API.md` — add `conversation_turns()` to `history_reader.py` API surface
- Add migration note to `CHANGELOG.md` under the next release

## Integration Map

### Files to Modify

| File | Change | Lines (est.) |
|------|--------|-------------|
| `scripts/little_loops/session_store.py` | v11 migration, `_backfill_assistant_messages()`, wire into backfill | ~80 |
| `scripts/little_loops/history_reader.py` | `conversation_turns()` function | ~60 |
| `scripts/little_loops/user_messages.py` | DB-first delegation wrapper in `extract_conversation_turns()`, `reader` param | ~40 |
| `scripts/little_loops/cli/messages.py` | `--reader` flag | ~25 |
| `docs/ARCHITECTURE.md` | Schema diagram + backfill flow update | ~15 |
| `docs/reference/API.md` | `conversation_turns()` entry | ~10 |

### New Files

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `scripts/tests/test_assistant_messages.py` | Migration + backfill + reader tests | ~200 |
| `scripts/tests/test_conversation_turns_fallback.py` | Delegation/fallback tests | ~80 |

### Dependent Files (Callers/Importers)

- `scripts/little_loops/sft_formatter.py` — no changes needed (takes `list[list[tuple[str, str]]]`, format unchanged)
- `scripts/little_loops/loops/sft-corpus.yaml` — no changes needed (FEAT-1826; calls `ll-messages --sft-format`, which delegates internally)
- `scripts/little_loops/cli/logs.py` — no changes needed (reads JSONL for non-SFT purposes; `--reader` flag deferred to follow-up)

### Similar Patterns

- `ll-history` DB-first-then-files fallback (`scan_completed_issues_from_db()` → `scan_completed_issues()`) — replicate in `extract_conversation_turns()`
- `_backfill_messages()` structure — mirror in `_backfill_assistant_messages()`
- `history_reader.py` graceful degradation (all functions return `[]` on missing DB) — replicate in `conversation_turns()`

## Success Metrics

- **Schema**: `assistant_messages` table exists with correct columns and index after `ensure_db()`
- **Backfill**: `ll-session backfill` populates `assistant_messages` for all existing sessions
- **Read parity**: `history_reader.conversation_turns()` produces identical output to `user_messages.extract_conversation_turns()` for the same session data
- **Graceful degradation**: `extract_conversation_turns()` returns results (via JSONL fallback) when `history.db` is missing
- **No regression**: existing tests for `ll-messages --sft-format` pass unchanged
- **Multi-host readiness**: `conversation_turns()` has zero host-specific logic — it queries normalized SQL rows

## Scope Boundaries

- **In scope**: Schema v11 (`assistant_messages`), backfill function, `conversation_turns()` in `history_reader.py`, DB-first delegation in `user_messages.extract_conversation_turns()`, `--reader` flag on `ll-messages`, tests, docs
- **Out of scope**: New `session_reader.py` module or ABC (deferred until host log formats diverge); removing JSONL parsing (retained as fallback); changes to `ll-logs` (separate issue); host-agnostic `get_project_folder()` (separate issue); changes to `ll-messages` non-SFT modes; backfill adapters for Codex/Pi (separate issues when those hosts land)

## Impact

- **Priority**: P3 — Matches parent EPIC-1880; foundational for ENH-1941 and FEAT-1826 but not blocking
- **Effort**: Medium — Schema migration + backfill (~80 lines) + read function (~60 lines) + delegation (~40 lines) + CLI flag (~25 lines) + tests (~280 lines) + docs (~25 lines) ≈ 510 lines
- **Risk**: Low — Additive to existing tables (new table, no column changes to existing tables); backfill is additive (INSERT, never UPDATE/DELETE); delegation wrapper preserves exact fallback behavior; no existing SFT pipeline to break (FEAT-1826 not yet built)
- **Breaking Change**: No — `extract_conversation_turns()` return type is unchanged; DB is optional (graceful degradation); `--reader` defaults to `auto` which preserves current behavior
- **Depends on**: ENH-1710 (session-ID → JSONL path mapping) for the `sessions` table join key — already done

## Related

- EPIC-1880 — parent epic (SLM fine-tuning from session logs)
- ENH-1941 — builds on this (quality-signal filtering from history.db)
- FEAT-1826 — consumes this (sft-corpus FSM loop ingest state)
- ENH-1827 — related (ll-messages --sft-format, the CLI this modifies)
- EPIC-1707 — provides the history.db read API and degradation pattern
- ENH-1710 — session-ID to JSONL path mapping (join key)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Schema diagram, producer→consumer flow |
| reference | docs/reference/API.md | history_reader.py API surface |
| guide | docs/guides/AUTOMATIC_HARNESSING_GUIDE.md | Loop authoring patterns for sft-corpus |

## Labels

`enhancement`, `sft`, `history-db`, `session-logs`, `multi-host`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-04T16:20:03 - `a4889662-f1e9-4f9d-89d3-a64a71a5e8ae.jsonl`
- `/ll:capture-issue` - 2026-06-04T18:00:00Z
- `/ll:manage-issue` - 2026-06-04 - Completed implementation

---

## Resolution

### Changes Made

| File | Change |
|------|--------|
| `scripts/little_loops/session_store.py` | Schema v11 (`assistant_messages` table + dedup index), `_backfill_assistant_messages()`, wired into `backfill()` and `backfill_incremental()` |
| `scripts/little_loops/history_reader.py` | `conversation_turns()` function with temporal-adjacency SQL pairing + graceful degradation |
| `scripts/little_loops/user_messages.py` | `extract_conversation_turns()` DB-first delegation wrapper with `reader` param |
| `scripts/little_loops/cli/messages.py` | `--reader {auto,db,jsonl}` flag on `ll-messages` |
| `scripts/tests/test_assistant_messages.py` | 19 tests: migration, backfill, conversation turns, degradation |
| `scripts/tests/test_session_store.py` | Updated 6 schema version assertions (10→11) |

### Architecture

```
ll-messages --sft-format chatml --reader auto
  └─ extract_conversation_turns(reader="auto")
       ├─ try: history_reader.conversation_turns(db_path)  ← NEW DB path
       │    └─ SELECT u.*, a.* FROM message_events u
       │       JOIN assistant_messages a
       │       WHERE a.ts BETWEEN u.ts AND next_user_ts   ← temporal adjacency
       │    └─ returns [] if DB missing/empty/pre-v11      ← graceful degradation
       └─ fallback: JSONL parsing (existing code)           ← preserved
```

### Verification

- `test_assistant_messages.py` — **19/19 passed**
- `test_session_store.py` — **all passed** (6 version tests updated)
- `test_history_reader.py` — **all passed** (no regressions)
- `test_user_messages.py` — **all passed** (no regressions)
- Full test suite — **9809 passed, 5 skipped, 0 failures**
- `ruff check` — **clean**

### Success Metrics

| Metric | Status |
|--------|--------|
| Schema v11 creates `assistant_messages` table + index | ✓ |
| `_backfill_assistant_messages()` populates correctly | ✓ |
| `conversation_turns()` returns correct turn-pair windows | ✓ |
| Graceful degradation (missing DB → `[]`) | ✓ |
| DB-first delegation in `extract_conversation_turns()` | ✓ |
| `--reader` flag on `ll-messages` | ✓ |
| No regressions (9809 tests) | ✓ |

**Done** | Completed: 2026-06-04 | Priority: P3
