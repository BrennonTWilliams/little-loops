---
id: ENH-1753
title: "Document history.db producer\u2192consumer flow in ARCHITECTURE.md"
type: ENH
priority: P3
status: done
parent: EPIC-1707
discovered_date: 2026-05-27
captured_at: '2026-05-27T20:37:30Z'
completed_at: '2026-06-01T11:22:55Z'
discovered_by: capture-issue
labels:
- enhancement
- captured
relates_to:
- EPIC-1707
- ENH-1752
depends_on:
- ENH-1752
decision_needed: false
testable: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1753: Document history.db producer→consumer flow in ARCHITECTURE.md

## Summary

Add a dedicated section to `docs/ARCHITECTURE.md` describing the full history.db producer→consumer flow, and update `docs/reference/API.md` with the read API surface introduced by ENH-1752. This is an explicit EPIC-1707 success metric and prevents the read API from being undiscoverable to future contributors.

## Current Behavior

`docs/ARCHITECTURE.md` has no section covering the history.db pipeline. The write side (`SQLiteTransport`, `EventBus`, writer hooks) and read side (the `history_reader.py` module added by ENH-1752) are both undocumented at the architecture level. `docs/reference/API.md` does not cover `history_reader.py`.

## Expected Behavior

`docs/ARCHITECTURE.md` contains a "History DB: Producer→Consumer Flow" section covering:
- Event tables (`tool_events`, `file_events`, `issue_events`, `loop_events`, `message_events`, `user_corrections`) and FTS5 `search_index`
- Write path: `EventBus` → `SQLiteTransport` → `.ll/history.db`, triggered by hooks (`post_tool_use.py`, `session_start.py`)
- Read path: `history_reader.py` query functions → skill prompt files via `ll-session search` CLI wrapper
- Graceful-degradation contract (missing DB, empty tables, stale rows)
- A simple ASCII or Mermaid diagram of the flow

`docs/reference/API.md` documents the `history_reader` module's public API (`find_user_corrections`, `recent_file_events`, `search`, `related_issue_events`) with parameter descriptions and return types.

## Motivation

EPIC-1707's success metrics explicitly require this documentation. Without it, new contributors won't know the DB exists as an agent context layer, will re-implement ad-hoc queries, and the graceful-degradation contract won't be enforced consistently. Documentation is load-bearing here, not cosmetic.

## Proposed Solution

ENH-1752 has landed: `history_reader.py` exists (297 lines) with all 5 query functions and 5 dataclasses confirmed. Proceed directly.

### docs/ARCHITECTURE.md — New Section

Insert after `## Extension Architecture & Event Flow` (section ends at line ~575, before `---` and `## Host Runner Layer`). Use H2 heading `## History DB: Producer→Consumer Flow`.

Section structure (matching existing section style):
1. **Intro prose** — one paragraph: "`.ll/history.db` is the per-project event history ... queryable in milliseconds without re-parsing JSONL or markdown."
2. **Write-path `sequenceDiagram`** — participants: `Hook (post_tool_use/user_prompt_submit)`, `session_start`, `EventBus`, `SQLiteTransport`, `history.db`. Model after `## Sequential Mode` (line 325). Show that `session_start` bootstraps schema via `ensure_db()` and then launches a background backfill thread; `post_tool_use` writes `tool_events`/`file_events` per-call directly (not via EventBus); `EventBus.emit()` routes `issue.*` and `loop.*` events through `SQLiteTransport.send()`.
3. **Read-path `flowchart TB`** — nodes: `history.db` → `history_reader.py` → three consumers: `ll-session CLI`, `ll-history-context CLI`, `refine-issue/ready-issue/confidence-check skills`.
4. **Components table** (3 columns: Component | File | Role) — one row per producer and consumer class/function group.
5. **Graceful-degradation contract** — bulleted list: `_connect_readonly()` returns `None` on schema failure or read-only open failure; all query functions return `[]` on `None` connection; all hook writers wrap DB calls in `contextlib.suppress(Exception)`; `SQLiteTransport.send()` is a no-op when `self._conn is None`.
6. **Cross-reference note**: "See [Extension Architecture & Event Flow](#extension-architecture--event-flow) for the full schema-version table (v1–v7) and CLI transport-wiring table."

**Do not** duplicate the schema-version table (lines 537–549) or transport-wiring table (lines 510–530) — cross-reference them.

### docs/reference/API.md — New Module Section

Insert `## little_loops.history_reader` after `## little_loops.events` (ends ~line 5822). The Module Overview table entry (line ~50) is already correct — no change needed there.

Section structure (matching `## little_loops.issue_lifecycle` at lines 2166–2241):
1. **H2 heading** `## little_loops.history_reader`
2. **Prose** — one paragraph from module docstring
3. **Cross-reference blockquote** — `> **Session store:** For the write-side schema, `SQLiteTransport`, and backfill functions, see [`little_loops.session_store`](#little_loopssession_store).`
4. **Five `@dataclass` H3 sections**: `UserCorrection`, `FileEvent`, `SearchResult`, `IssueEvent`, `SessionRef` — each with exact field list from `history_reader.py`
5. **Five query function H3 sections**: `find_user_corrections`, `recent_file_events`, `search`, `related_issue_events`, `sessions_for_issue` — each with exact signature from `history_reader.py`, **Parameters:** bullets, **Returns:** line, stale-filter behavior note where applicable

Exact signatures to document (confirmed from `history_reader.py`):
```python
def find_user_corrections(topic: str, *, limit: int = 10, include_stale: bool = False, db: Path | str = DEFAULT_DB_PATH) -> list[UserCorrection]
def recent_file_events(path: str, *, limit: int = 10, include_stale: bool = False, db: Path | str = DEFAULT_DB_PATH) -> list[FileEvent]
def search(query: str, *, kind: str | None = None, limit: int = 10, db: Path | str = DEFAULT_DB_PATH) -> list[SearchResult]
def related_issue_events(issue_id: str, *, limit: int = 20, db: Path | str = DEFAULT_DB_PATH) -> list[IssueEvent]
def sessions_for_issue(issue_id: str, *, limit: int = 20, db: Path | str = DEFAULT_DB_PATH) -> list[SessionRef]
```

## Integration Map

### Files to Modify

- `docs/ARCHITECTURE.md` — insert new H2 section "History DB: Producer→Consumer Flow" **after** the existing `## Extension Architecture & Event Flow` section (ends around line 575). The existing schema-version table at lines 537–549 and transport-wiring table at lines 510–530 should be cross-referenced, not duplicated. New section should use a Mermaid `sequenceDiagram` (matching the style of `## Sequential Mode` at line 325) for the write-path flow, a `flowchart TB` for the read-path consumer fan-out, and a components table.
- `docs/reference/API.md` — insert `## little_loops.history_reader` section **after** `## little_loops.events` (currently ends around line 5822). The module is already listed in the Module Overview table (line ~50) as a one-liner; this adds the full expanded section. Follow the `## little_loops.issue_lifecycle` section format (lines 2166–2241) for dataclasses and query functions.
- `CONTRIBUTING.md` — add `history_reader.py` and `session_store.py` to the `scripts/little_loops/` package tree (lines ~182–281); both files are absent from the developer-facing package map. [_Wiring pass added by `/ll:wire-issue`:_]

### Dependent Files (Source of Truth for Documentation Content)

- `scripts/little_loops/history_reader.py` — all 5 public query functions and 5 dataclasses; read before writing the API.md section to get exact signatures, parameter names, and return types
- `scripts/little_loops/session_store.py` — `SQLiteTransport.send()` routing logic (loop events vs. issue events), `ensure_db()`, `_MIGRATIONS` list (v1–v7), `backfill()`, `backfill_incremental()`; defines `DEFAULT_DB_PATH`
- `scripts/little_loops/events.py` — `EventBus.emit()` dispatch to observers and transports; `add_transport()` / `close_transports()`
- `scripts/little_loops/transport.py` — `wire_transports()` function; `Transport` protocol
- `scripts/little_loops/hooks/session_start.py` — calls `ensure_db()` directly at startup; spawns background thread calling `backfill_incremental()` for incremental JSONL seeding (ENH-1830)
- `scripts/little_loops/hooks/post_tool_use.py` — writes `tool_events` and `file_events` per tool call when `analytics.enabled`; extracts file path via `_extract_file_path()` and issue ID via `_detect_issue_id()`
- `scripts/little_loops/hooks/user_prompt_submit.py` — writes `user_corrections` and `skill_events` via `record_correction()` and `record_skill_event()` from `session_store`
- `scripts/little_loops/cli/session.py` — `ll-session` CLI; routes to `history_reader.search()`, `related_issue_events()`, `sessions_for_issue()` for queries; routes to `backfill()`/`backfill_incremental()` for seeding
- `scripts/little_loops/cli/history_context.py` — `ll-history-context` CLI; the primary read-path consumer: calls `find_user_corrections()` and `recent_file_events()`, caps at 5 rows, deduplicates, renders the `## Historical Context` markdown block; confirms exact read-path contract [_Wiring pass added by `/ll:wire-issue`:_]
- `scripts/little_loops/cli/history.py` — `ll-history` CLI; secondary read-path consumer for analytics and topic-filtered exports from `history.db` [_Wiring pass added by `/ll:wire-issue`:_]

### Similar Patterns

- `docs/ARCHITECTURE.md:325` (`## Sequential Mode`) — best model for `sequenceDiagram` format: shows a multi-actor flow (User → CLI → Manager → Claude → Git) with a `loop` block; use this shape for the write-path hook → SQLiteTransport → history.db flow
- `docs/ARCHITECTURE.md:537-549` — existing schema-version table (already in "Extension Architecture & Event Flow"); the new section should cross-reference this table rather than duplicate it
- `docs/ARCHITECTURE.md:510-530` — existing transport-wiring table showing which CLI entry points wire `SQLiteTransport`; cross-reference or extend rather than duplicate
- `docs/reference/API.md:2166-2241` (`## little_loops.issue_lifecycle`) — canonical format for a module entry: H2 heading, prose description, code import block, then H3 per function with Python signature block, **Parameters:** bullets, **Returns:** line
- `docs/reference/API.md:5704-5822` (`## little_loops.events`) — uses a "see also" cross-reference blockquote at section top (`> **Event catalog:** see EVENT-SCHEMA.md`) and a methods table under each class; adopt the cross-reference pattern pointing to `docs/reference/EVENT-SCHEMA.md`
- `docs/reference/API.md:3465-3486` (`### main_history_context`) — existing CLI entry-point doc format with **Flags:** table and **Behavior:** bullets; `ll-session` and `ll-history-context` are already documented here; do not add duplicate entries

### Consumers of history_reader (cross-cutting callers)

- `commands/refine-issue.md:116` — `HIST=$(ll-history-context {{issue_id}} 2>/dev/null || true)` invocation
- `commands/ready-issue.md:132` — same pattern
- `skills/confidence-check/SKILL.md:180` — same pattern; all three use `allowed-tools: [Bash(ll-history-context:*)]`

### Tests

- `ll-verify-docs` — verify documented counts remain accurate after changes
- `ll-check-links` — verify no broken links introduced
- `scripts/tests/test_enh1753_doc_wiring.py` — **NEW** (must be created); canonical doc-wiring test asserting section heading, diagram types, graceful-degradation contract, and function signatures in API.md; follow pattern from `scripts/tests/test_enh1846_doc_wiring.py` [_Wiring pass added by `/ll:wire-issue`:_]
- `scripts/tests/test_history_reader.py` — existing coverage; `TestMissingDatabase`, `TestEmptyTables`, and `TestStaleRowFiltering` directly validate the graceful-degradation bullets to document [_Wiring pass added by `/ll:wire-issue`:_]
- `scripts/tests/test_session_store.py` — `TestSQLiteTransport.test_send_after_close_is_noop` validates the `self._conn is None` graceful-degradation contract for the write path [_Wiring pass added by `/ll:wire-issue`:_]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` lines 1501–1548 (`### ll-session`) and 1552–1572 (`### ll-history-context`) — neither section links to the new ARCHITECTURE.md section; optional cross-reference addition after implementation
- `docs/reference/CONFIGURATION.md` lines 1031–1048 (`### events.sqlite`) — describes `history.db` write path without linking to new architecture section; optional cross-reference addition

### Documentation

- This issue IS the documentation work — no additional docs needed

### Configuration

- N/A

## Implementation Steps

1. Read `docs/ARCHITECTURE.md` lines 325–370 (`## Sequential Mode`) to confirm `sequenceDiagram` style, then read lines 489–575 (`## Extension Architecture & Event Flow`) to confirm insertion point and identify exact content to cross-reference (schema table at lines 537–549, transport table at lines 510–530).
2. Draft `## History DB: Producer→Consumer Flow` section with:
   - Write-path `sequenceDiagram` (actors: `session_start`, `post_tool_use`, `user_prompt_submit`, `EventBus`, `SQLiteTransport`, `history.db`)
   - Read-path `flowchart TB` (`history.db` → `history_reader.py` → three consumer paths)
   - Components table and graceful-degradation bullet list
3. Insert the new section into `docs/ARCHITECTURE.md` immediately after the `## Extension Architecture & Event Flow` closing `---` separator (before `## Host Runner Layer` at line ~577).
4. Read `docs/reference/API.md` lines 2166–2241 (`## little_loops.issue_lifecycle`) to confirm module-section format, then read lines 5704–5822 (`## little_loops.events`) to find the insertion point.
5. Draft `## little_loops.history_reader` section using exact signatures from `scripts/little_loops/history_reader.py`: 5 `@dataclass` blocks (lines 42–89) and 5 query function signatures (lines 130–297).
6. Insert the new section into `docs/reference/API.md` immediately after `## little_loops.events` ends (~line 5822).
7. Run `ll-check-links` and `ll-verify-docs` to confirm no broken links or count mismatches were introduced.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Read `scripts/little_loops/cli/history_context.py` to confirm the exact 5-row cap, deduplication logic, and stale-filter behavior before writing the read-path consumer description in ARCHITECTURE.md.
9. Create `scripts/tests/test_enh1753_doc_wiring.py` asserting: (a) `## History DB: Producer→Consumer Flow` in ARCHITECTURE.md, (b) `sequenceDiagram` and `flowchart TB` present, (c) `_connect_readonly` in ARCHITECTURE.md (graceful-degradation contract), (d) `## little_loops.history_reader` in API.md, (e) `find_user_corrections`, `sessions_for_issue`, `include_stale`, `SessionRef` in API.md. Follow pattern from `scripts/tests/test_enh1846_doc_wiring.py`.
10. Update `CONTRIBUTING.md` lines ~182–281 (`scripts/little_loops/` package tree) to add `history_reader.py` and `session_store.py` entries.

## Impact

- **Priority**: P3 — Required by EPIC-1707 success metrics; no functional impact
- **Effort**: Small — Documentation-only, no code changes
- **Risk**: Low — Docs only; cannot break functionality
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: NEEDS_UPDATE** — Prerequisite (ENH-1752) is done; documentation section still absent.
- `history_reader.py` now EXISTS (249 lines) — ENH-1752 is **DONE** ✓
- `docs/ARCHITECTURE.md` has NO "History DB: Producer→Consumer Flow" section ✓ (still needs writing)
- `docs/reference/API.md` lists `history_reader` as a one-liner only; no detailed module documentation ✓
- Action: ENH-1752 dependency is satisfied; update `depends_on` field and proceed with documentation

## Session Log
- `/ll:ready-issue` - 2026-06-01T11:11:46 - `5747c773-27f3-4bb6-ba7d-ee09995d5504.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `7f83f795-ddd9-4a6d-8c23-142bff64a6f8.jsonl`
- `/ll:wire-issue` - 2026-06-01T11:06:43 - `6f4aab65-d5c9-452a-97af-1aec7cc9daa3.jsonl`
- `/ll:refine-issue` - 2026-06-01T10:59:01 - `5f80ab83-ead5-408e-a07e-f0983da571c9.jsonl`
- `/ll:verify-issues` - 2026-06-01T03:08:51 - `ed2ec455-964e-4a94-92a4-e94218c08ad6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:58 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:15 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`

- `/ll:capture-issue` - 2026-05-27T20:37:30Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b49625e3-8e47-4c6d-9fa3-75d4dde31106.jsonl`

---

**Open** | Created: 2026-05-27 | Priority: P3
