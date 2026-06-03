---
id: ENH-1888
title: Expand history.db consumer wiring to go-no-go and capture-issue
type: ENH
priority: P3
status: open
discovered_date: 2026-06-02
captured_at: "2026-06-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-1707
depends_on: [ENH-1847, ENH-1887]
blocked_by: []
labels:
  - enhancement
  - captured
---

# ENH-1888: Expand history.db consumer wiring to go-no-go and capture-issue

## Summary

ENH-1847 wired `history.db` reads into the initial 3 skills (`refine-issue`, `ready-issue`, `confidence-check`), satisfying EPIC-1707's minimum success metric. Two additional high-leverage consumers are untracked: `go-no-go` (where prior corrections on an issue's scope are a direct halt signal) and `capture-issue` (where recently closed or deferred issues could flag near-duplicate captures before they land in the backlog).

## Motivation

### `go-no-go`

`go-no-go` is the final gate before implementation begins. A prior `user_corrections` row saying "we decided not to do this approach for X reason" is exactly the kind of signal that should surface here — it's more decision-critical than `confidence-check`, which is advisory. Currently `go-no-go` builds its verdict purely from the issue file and codebase state.

### `capture-issue`

When a user captures a new issue, `capture-issue` has no visibility into recently closed or deferred issues. A common waste pattern: re-capturing an issue that was deferred 2 weeks ago with a "not now, low priority" note, or re-capturing a variant of something that was `done` last sprint. A `related_issue_events(issue_id)` lookup on the new issue's title keywords could surface a "similar issue was closed N days ago: <reason>" warning before the issue is written.

## Current Behavior

- `go-no-go`: reads issue file + optional codebase context; no history DB access
- `capture-issue`: writes new issue file; no duplicate/recency check against history DB

## Expected Behavior

### `go-no-go`

After loading the issue file (Phase 1), query:
```bash
ll-history-context <issue_id> 2>/dev/null || true
```
If output is non-empty, include as a `## Historical Context` section. A corrections match on this issue ID is a `-0.2` signal on the go/no-go verdict confidence. Surface any matched corrections as explicit "prior concerns" in the output.

### `capture-issue`

After the user describes the issue but before writing the file, query:
```bash
ll-session search --fts "<title_keywords>" --kind issue_event --limit 5 2>/dev/null || true
```
If results include closed/deferred issues with >70% title overlap, surface a "Similar closed issue found: <ID> — <reason>" warning and ask the user whether to proceed or link instead.

## Scope Boundaries

- **In scope**: wiring `ll-history-context` into `go-no-go`; wiring FTS5 near-duplicate check into `capture-issue`; graceful degradation for missing DB; tests for both consumers
- **Out of scope**: changing `go-no-go` verdict logic beyond the additional signal; changing issue capture storage format; cross-project dedup

## Implementation Steps

1. Wire `ll-history-context` into `go-no-go/SKILL.md`: add `Bash(ll-history-context:*)` to `allowed-tools`, add DB query step in Phase 1 "Gather Context" after issue file load
2. Wire `ll-session search --fts` into `capture-issue/SKILL.md`: add `Bash(ll-session:*)` to `allowed-tools`, add near-duplicate check step before file write
3. Update bridge stubs (`skills/ll-go-no-go/SKILL.md`, `skills/ll-capture-issue/SKILL.md`) to reflect matching `allowed-tools`
4. Add `TestGoNoGoHistoryContextInjection` (corrections present, no corrections, DB missing) to `test_go_no_go_skill.py`
5. Add `TestCaptureIssueNearDuplicateCheck` (duplicate closed, duplicate deferred, no match, DB missing) to `test_capture_issue_skill.py`
6. Verify end-to-end: both skills proceed normally with no hard failure when `.ll/history.db` is absent

## Integration Map

### Files to Modify
- `skills/go-no-go/SKILL.md` — add `Bash(ll-history-context:*)` to `allowed-tools`; add DB query step to Phase 1 "Gather Context" after issue file load
- `skills/capture-issue/SKILL.md` — add `Bash(ll-session:*)` to `allowed-tools`; add near-duplicate check step before file write
- `skills/ll-go-no-go/SKILL.md` — verify bridge stub `allowed-tools` matches source
- `skills/ll-capture-issue/SKILL.md` — verify bridge stub `allowed-tools` matches source

### Tests
- `scripts/tests/test_go_no_go_skill.py` — add `TestGoNoGoHistoryContextInjection` covering: corrections present, no corrections, DB missing
- `scripts/tests/test_capture_issue_skill.py` — add `TestCaptureIssueNearDuplicateCheck` covering: duplicate found (closed), duplicate found (deferred), no match, DB missing

### CLI (already exists, no changes)
- `scripts/little_loops/cli/history_context.py` — `ll-history-context` CLI (from ENH-1846)
- `scripts/little_loops/cli/session.py` — `ll-session search --fts` (already supports `--kind`)

### Dependent Files (Callers/Importers)
- N/A — skills are invoked by users directly, not imported by other modules

### Similar Patterns
- `skills/refine-issue/SKILL.md`, `skills/ready-issue/SKILL.md`, `skills/confidence-check/SKILL.md` — established the `ll-history-context` wiring pattern in ENH-1847; follow the same `allowed-tools` + Phase 1 query pattern

### Documentation
- N/A — no user-facing docs need updating (skill behavior is self-describing)

### Configuration
- N/A — no config file changes; `.ll/history.db` is read-only in consumer skills

## Impact

- **Priority**: P3 — expands value of the consumer layer to two more decision-critical touchpoints
- **Effort**: Small — both wiring points follow the established pattern from ENH-1847; no new infrastructure
- **Risk**: Low — additive; skills degrade gracefully when DB is empty
- **Breaking Change**: No

## Success Metrics

- `go-no-go` Historical Context injection: `ll-history-context` output appears in skill output when DB has a corrections row for the issue → verified by `TestGoNoGoHistoryContextInjection.test_corrections_present`
- `capture-issue` near-duplicate warning: warning emitted for closed/deferred issues with >70% title overlap → verified by `TestCaptureIssueNearDuplicateCheck.test_duplicate_closed`
- Graceful degradation: both skills exit 0 and proceed normally when `.ll/history.db` is missing → verified by DB-missing test cases
- Test suite: 6 new tests (3 per skill), all green

## Acceptance Criteria

- `go-no-go` includes a `## Historical Context` section in its output when `ll-history-context` returns non-empty
- `capture-issue` surfaces a near-duplicate warning when FTS5 finds a closed/deferred issue with matching title keywords
- Both skills proceed normally (no hard failure) when `.ll/history.db` is missing or empty
- Test coverage: 3 cases per skill (matches present, no matches, DB missing)

---

**Open** | Created: 2026-06-02 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-03T01:14:03 - `6440d944-a7d1-441a-bc55-42e0d5f7c1f8.jsonl`
