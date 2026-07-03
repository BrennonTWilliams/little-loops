---
id: ENH-2464
title: Backlink .ll/decisions.yaml entries to issuing session_id and issue_id
type: ENH
priority: P3
status: open
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - decisions
  - history-db
  - captured
---

# ENH-2464: Backlink .ll/decisions.yaml entries to issuing session_id and issue_id

## Summary

`.ll/decisions.yaml` (FEAT-948 done, ENH-2152 done for extraction) holds `rule`, `decision`, and `exception` entries with author-provided fields like `rule`, `rationale`, `issue`, `category`, `enforcement`. `correction_retirements` (a sibling table) marks corrections as "codified as a rule" but it's only a one-way link from correction → rule. The `decisions` source file itself carries no `session_id` or `issuing_session_id` — when a `decision` is appended by `/ll:decide-issue`, `/ll:tradeoff-review-issues`, or `/ll:go-no-go`, the originating session and any related issue are not recorded. Add `source_session_id` and `source_issue_id` (or restructure `issue:` to include both) so a rule/decision can be traced to the session and issue that produced it. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #7: *"when a decision is added or its outcome is recorded, write the source `session_id`/`issue_id` so `ll-session search` can trace a rule back to the incident that produced it."*

## Motivation

The current decisions log is the project's rule substrate, but it's a write-once, manual-source-of-truth ledger with no traceback:

- **Why was this rule added?** — currently the rule entry has a `rationale` field but no link to the session that discussed it.
- **Which issue prompted this rule?** — `issue:` is set when present but isn't required; some entries drift orphan.
- **No backward trace from `correction_retirements` to issuing session** — corrections are linked to rule IDs, but the rule doesn't say "this rule came from session S discussing issue I."
- **No cross-query with `skill_events`** — without `source_session_id`, `ll-session search` cannot surface "which rules were added by `/ll:decide-issue` last week?" because the rule entry has no provenance.

## Current Behavior

- `.ll/decisions.yaml` schema (per FEAT-948): each entry has `id`, `type`, `timestamp`, `category`, `labels`, `rule`, `rationale`, optional `issue`, optional `scope`, optional `outcome`, optional `enforcement`, optional `supersedes`/`rule_ref`.
- Skill-level capture bridges (`/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go`) all write `rule` and `rationale` and `issue` if available — but the current session_id and a structured `source_session_id` are not recorded.
- `correction_retirements` in `.ll/history.db` has `topic_fingerprint`, `rule_id`, `addressed_at`, `session_id` — partial traceability on the corrections side.
- `ll-session search --fts "<rationale fragment>"` returns no decisions entries because decisions live in YAML, not the DB.

## Expected Behavior

- `DecisionEntry` and `RuleEntry` (per FEAT-948 / `scripts/little_loops/decisions.py`) gain `source_session_id: str | None` and structured `source_issue_id` fields.
- Skill-level capture bridges (the three pipelines named above) populate these from the orchestrator's runtime context when adding a new entry.
- `ll-session search --fts "<decision content>"` returns decision rows via a parallel DB mirror (analogous to `issue_snapshots` per ENH-2151 — store summaries in history.db, full text in YAML).
- `ll-issues decisions list --source-session <sid>` filters by issuing session; `ll-issues decisions show <id>` shows full YAML.
- Round-trip safe: editing a YAML entry preserves any already-set `source_session_id`.

## Proposed Solution

### Schema (dataclass + YAML + DB)

**Dataclass** (`scripts/little_loops/decisions.py`):
```python
@dataclass
class DecisionEntry:
    ...
    source_session_id: Optional[str] = None
    source_issue_id: Optional[str] = None  # canonical form; existing 'issue' field remains
```

Add the same to `RuleEntry` and `ExceptionEntry` (or only `DecisionEntry` — decide by adoption cost).

**YAML schema** (backward compatible):
```yaml
- id: TOOLING-001
  type: decision
  timestamp: "2026-04-04T00:00:00Z"
  category: tooling
  rule: "..."
  rationale: "..."
  source_session_id: "abc-1234-uuid"   # NEW; nullable
  source_issue_id: "FEAT-948"           # NEW; nullable
  issue: "P3-FEAT-948-..."               # existing (kept)
  ...
```

**DB mirror** (`scripts/little_loops/session_store.py`):
```sql
CREATE TABLE IF NOT EXISTS decision_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    decision_type TEXT NOT NULL,        -- rule | decision | exception
    category TEXT,
    rule TEXT,
    rationale TEXT,
    source_session_id TEXT,
    source_issue_id TEXT,
    issue TEXT                          -- existing
);
CREATE INDEX IF NOT EXISTS idx_decision_events_source_session ON decision_events(source_session_id);
CREATE INDEX IF NOT EXISTS idx_decision_events_source_issue ON decision_events(source_issue_id);
CREATE INDEX IF NOT EXISTS idx_decision_events_decision_id ON decision_events(decision_id);
```

Add `"decision"` to `_VALID_KINDS` and `"decision": "decision_events"` to `_KIND_TABLE`. The DB row is a search/join mirror; YAML remains the source of truth for editable detail.

### Producer wiring

- Update `/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go` skill capture bridges (per FEAT-948 / ENH-2152) to thread `session_id` (from the active orchestrator context) and the current `issue_id` if any.
- Extend `scripts/little_loops/decisions.py::add_entry()` to accept `source_session_id` and `source_issue_id` kwargs; pass through to YAML serialization and DB row insert.
- Mirror inserts to `decision_events` are best-effort (`contextlib.suppress(Exception)`); YAML remains canonical.

### Read API

Add to `history_reader.py`:
- `find_decisions_for_session(session_id)` returning `list[DecisionRecord]`.
- `find_decisions_for_issue(issue_id)` returning `list[DecisionRecord]`.

### CLI surface

- `ll-session search --fts "<rationale fragment>" --kind decision` returns matching decisions.
- `ll-session recent --kind decision` returns recent decisions.
- `ll-issues decisions show <id>` shows full YAML.
- `ll-issues decisions list --source-session <sid>` filters by issuing session.

## Acceptance Criteria

- New YAML fields `source_session_id` and `source_issue_id` are backward-compatible (legacy YAML without them loads as `None`).
- A new `decision` entry added via `/ll:decide-issue` carries the current `session_id` and the current `issue_id` from runtime context.
- A `decision_events` row mirrors the YAML entry in `decision_events` table.
- `ll-session recent --kind decision` returns rows; FTS search matches `rule` and `rationale` text.
- `history_reader.find_decisions_for_session(sid)` returns the decisions issued by that session.
- Round-trip safe: loading + saving YAML preserves all three of `issue`, `source_session_id`, `source_issue_id`.
- Tests cover: legacy YAML load, capture-bridge wiring, DB mirror, read API, CLI surface.

## Implementation Steps

1. Extend `DecisionEntry` / `RuleEntry` / `ExceptionEntry` dataclasses (`scripts/little_loops/decisions.py`) with the two new fields.
2. Update `to_yaml` / `from_yaml` to round-trip the new fields.
3. Schema migration for `decision_events`; bump `SCHEMA_VERSION`.
4. Add `"decision"` to `_VALID_KINDS` and `_KIND_TABLE`.
5. Implement `record_decision_event()` and `_backfill_decision_events()` in `session_store.py`.
6. Update three skill capture bridges (`/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go`) to thread `session_id` and `issue_id` into `add_entry()`.
7. Mirror to DB at write time (best-effort).
8. Extend `history_reader` with `find_decisions_for_session` and `find_decisions_for_issue`.
9. CLI: ensure `--kind decision` enumerations; add `--source-session` to `ll-issues decisions list`.
10. Tests: `TestDecisionEntryNewFields`, `TestRecordDecisionEvent`, `TestSchemaV15` (or higher), skill-bridge integration test, read-API tests.
11. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md` updates, `docs/guides/DECISIONS_LOG_GUIDE.md` new fields section, `docs/reference/CLI.md` new flag.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 6 ("`decisions.yaml` content — Partial"), §3 ranked recommendation #7
- `.issues/features/P3-FEAT-948-rules-and-decisions-log-for-issue-compliance.md` — decision entry schema
- `.issues/enhancements/P3-ENH-2152-extract-decisions-and-rules-from-completed-issues.md` — extraction pipeline that depends on these fields existing
- `scripts/little_loops/decisions.py` — core schema (single source of truth)
- `scripts/little_loops/correction_retirements` — existing one-way linkage precedent

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; persistence layer section |
| `docs/guides/DECISIONS_LOG_GUIDE.md` | Decisions schema and CLI surface |
| `docs/reference/CLI.md` | New `--source-session` flag |

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
