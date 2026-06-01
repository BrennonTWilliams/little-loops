---
id: ENH-1753
title: Document history.db producer→consumer flow in ARCHITECTURE.md
type: ENH
priority: P3
status: open
parent: EPIC-1707
discovered_date: 2026-05-27
captured_at: "2026-05-27T20:37:30Z"
discovered_by: capture-issue
labels:
  - enhancement
  - captured
  - testable: false
relates_to: [EPIC-1707, ENH-1752]
depends_on: [ENH-1711]
testable: false
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

After ENH-1752 lands:
1. Add "History DB: Producer→Consumer Flow" section to `docs/ARCHITECTURE.md` with a flow diagram and description of each layer
2. Update `docs/reference/API.md` with the `history_reader` module entry, following existing API doc patterns in that file

## Integration Map

### Files to Modify

- `docs/ARCHITECTURE.md` — add producer→consumer section
- `docs/reference/API.md` — add `history_reader` module documentation

### Dependent Files (Callers/Importers)

- Depends on ENH-1752 (read API must exist before it can be documented)

### Similar Patterns

- Existing `docs/ARCHITECTURE.md` sections for reference on style/structure
- Existing `docs/reference/API.md` module entries for API doc format

### Tests

- `ll-verify-docs` — verify documented counts remain accurate after changes
- `ll-check-links` — verify no broken links introduced

### Documentation

- This issue IS the documentation work — no additional docs needed

### Configuration

- N/A

## Implementation Steps

1. Read existing `docs/ARCHITECTURE.md` to match section style
2. Draft and insert "History DB: Producer→Consumer Flow" section with diagram
3. Read existing `docs/reference/API.md` to match module-entry format
4. Add `history_reader` module documentation
5. Run `ll-check-links` and `ll-verify-docs` to validate

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
- `/ll:verify-issues` - 2026-06-01T03:08:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed2ec455-964e-4a94-92a4-e94218c08ad6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`

- `/ll:capture-issue` - 2026-05-27T20:37:30Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b49625e3-8e47-4c6d-9fa3-75d4dde31106.jsonl`

---

**Open** | Created: 2026-05-27 | Priority: P3
