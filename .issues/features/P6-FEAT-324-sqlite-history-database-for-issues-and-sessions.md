---
discovered_date: 2026-02-10
discovered_by: capture_issue
---

# FEAT-324: SQLite History Database for Completed Issues and Sessions

## Summary

Create a SQLite database (e.g., `.ll/history.db`) that stores completed issue metadata and their linked session data. The database is used by the plugin for historical development analysis, issue regression/duplicate detection at creation time, and powering commands like `/ll:analyze-history` with real queryable data instead of file scanning.

## Current Behavior

Completed issues are stored as markdown files in `.issues/completed/`. Historical analysis relies on scanning these files at runtime. Duplicate detection in `/ll:capture-issue` uses simple word overlap on active issues only. There is no structured, queryable store of past work.

## Expected Behavior

A `.ll/history.db` SQLite database stores:
- **issues** table: completed issue metadata (ID, type, priority, title, description, resolution, dates)
- **sessions** table: linked JSONL paths, command used, timestamps, duration (from FEAT-323)
- ~~**session_summaries** table~~: Deferred — tool usage and operational data per session is better served by FEAT-417 (Hybrid Telemetry), which captures fine-grained events queryable by issue_id. Avoids duplicating data between two stores.

The database is queried by:
- `/ll:capture-issue` for duplicate/regression detection against historical issues
- `/ll:analyze-history` for velocity, trends, and project health metrics
- Sprint planning tools for effort estimation based on past similar work

## Motivation

The plugin generates valuable historical data through issue completion but currently discards the queryable structure. A SQLite DB enables instant lookups instead of file scanning, semantic duplicate detection against all past work (not just active issues), and data-driven development metrics. This is the foundation for making the plugin learn from its own history.

## Use Case

A developer runs `/ll:capture-issue "API response caching is slow"`. The capture command queries `history.db` and finds that FEAT-187 (completed 3 months ago) implemented API caching and ENH-201 (completed 1 month ago) optimized cache TTLs. It surfaces these as potential duplicates/regressions, giving the developer immediate context on prior work.

## Acceptance Criteria

- [ ] `.ll/history.db` SQLite database is created and managed by the plugin
- [ ] Completed issues are ingested into the `issues` table (on completion or via backfill)
- [ ] Session log entries (from FEAT-323) are stored in the `sessions` table
- [ ] `/ll:capture-issue` queries the DB for duplicate/regression detection against historical issues
- [ ] `/ll:analyze-history` queries the DB instead of scanning files
- [ ] A backfill command or migration ingests existing completed issues
- [ ] `.ll/` directory is gitignored (local to each developer)
- [ ] DB schema is versioned for future migrations
- [ ] ~~session_summaries table~~ — Deferred to FEAT-417 (telemetry events queryable by issue_id)

## API/Interface

```python
# New module: scripts/little_loops/history_db.py
class HistoryDB:
    def __init__(self, db_path: Path): ...
    def ingest_completed_issue(self, issue_path: Path) -> None: ...
    def ingest_session(self, issue_id: str, command: str, jsonl_path: Path, timestamp: str) -> None: ...
    def find_similar_issues(self, title: str, description: str, threshold: float) -> list[dict]: ...
    def get_velocity_metrics(self, days: int = 30) -> dict: ...
    def backfill_from_completed(self, completed_dir: Path) -> int: ...
```

## Proposed Solution

Use Python's built-in `sqlite3` module (no new dependencies). Create a `history_db.py` module in `scripts/little_loops/` with:

1. Schema creation/migration on first access
2. Ingestion functions called by `manage_issue` on completion
3. Query functions called by `capture_issue` and `analyze-history`
4. A backfill function to populate from existing `.issues/completed/` files
5. Word-based similarity search using SQLite FTS5 for efficient text matching

Storage location: `.ll/history.db` at project root (gitignored). This keeps it project-local but outside `.claude/` which is for plugin config.

## Integration Map

### Files to Modify
- `skills/manage_issue.md` - Ingest completed issue into DB
- `skills/capture_issue.md` - Query DB for historical duplicate detection
- `skills/analyze-history.md` - Query DB for metrics
- `.gitignore` - Add `.ll/` directory

### Dependent Files (Callers/Importers)
- FEAT-323 (session linking) provides session data to ingest

### Similar Patterns
- `scripts/little_loops/messages.py` - Similar pattern of parsing files into structured data

### Tests
- `scripts/tests/test_history_db.py` - DB operations, ingestion, similarity queries

### Documentation
- `docs/ARCHITECTURE.md` - Document history DB design and schema

### Configuration
- `.claude/ll-config.json` - Potential `history.db_path` override setting

## Implementation Steps

1. Design and implement SQLite schema with versioning
2. Create `history_db.py` module with core CRUD operations
3. Add FTS5-based similarity search for duplicate detection
4. Integrate ingestion into `manage_issue` completion flow
5. Integrate historical query into `capture_issue` duplicate detection
6. Update `analyze-history` to query DB
7. Create backfill command for existing completed issues
8. Add `.ll/` to `.gitignore`

## Impact

- **Priority**: P2 - High value for plugin intelligence, depends on FEAT-323
- **Effort**: Large - New module, schema design, multiple integration points
- **Risk**: Medium - New persistent state to manage; schema migrations needed over time
- **Breaking Change**: No

## Related Issues

- **FEAT-417** (Hybrid Telemetry) — Complementary. FEAT-417 captures operational event data (timings, tool usage, context consumption) in a JSONL stream. This issue captures domain data (issue metadata, resolutions) in SQLite. They share `.ll/` directory and `issue_id` as correlation key. The `session_summaries` table originally planned here is deferred in favor of querying FEAT-417's telemetry events by issue_id, avoiding data duplication.

## Blocked By

- ~~FEAT-323: Link session JSONL logs to issue files~~ (completed 2026-02-10 — dependency satisfied)
- BUG-403: dependency graph renders empty nodes without edges (shared ARCHITECTURE.md)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | System design, module structure |
| architecture | docs/API.md | Python module conventions |

## Labels

`feature`, `captured`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2

---

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID
- .ll/ directory does not exist — no SQLite DB implemented
- scripts/little_loops/history_db.py does not exist
- No issue ingestion or DB query functionality exists
- Feature is new work, depends on FEAT-323 for session linking

---

## Tradeoff Review Note

**Reviewed**: 2026-02-10 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | HIGH |
| Implementation effort | HIGH |
| Complexity added | HIGH |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first - High value but scope is too broad for a single issue. Needs refinement on:
1. **session_summaries table scope**: What content is extracted from JSONL files? How is it summarized? This is underspecified.
2. **Migration strategy**: How will schema versioning work? What happens when history.db schema changes?
3. **Phased implementation**: Consider splitting into Phase 1 (basic issue metadata + FTS5 search) and Phase 2 (session summaries integration)

### Implementation Prerequisites
- Must complete FEAT-323 (session linking) first
- Clarify session_summaries table content and extraction strategy

---

## Tradeoff Review Note

**Reviewed**: 2026-02-11 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | HIGH |
| Implementation effort | HIGH |
| Complexity added | HIGH |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first - High value but scope too broad. Split into Phase 1 (core issue metadata + FTS5 duplicate detection) and Phase 2 (session summaries integration). Database migrations and schema versioning strategy need clarification before implementation.

---

## Tradeoff Review Note

**Reviewed**: 2026-02-12 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | HIGH |
| Implementation effort | HIGH |
| Complexity added | HIGH |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first - High value feature but scope is too broad and underspecified (session_summaries table, migration strategy unclear). Consistent recommendation across three reviews: split into phases and clarify scope before implementation.

---

## Scope Refinement (2026-02-13)

**Addressing tradeoff review feedback** (3 reviews recommending scope narrowing):

1. **`session_summaries` table**: Deferred. Operational data (tool usage, durations per phase) is now handled by FEAT-417 (Hybrid Telemetry). FEAT-324 scope is narrowed to `issues` + `sessions` tables only.
2. **Migration strategy**: Use SQLite's `user_version` pragma for schema versioning. On first access, create tables if absent. On schema changes, check `user_version` and apply migrations sequentially. No external migration framework needed.
3. **Phased implementation**: Phase 1 = `issues` table + FTS5 duplicate detection + backfill. Phase 2 = `sessions` table + `analyze-history` integration. This aligns with the consistent recommendation to split.
