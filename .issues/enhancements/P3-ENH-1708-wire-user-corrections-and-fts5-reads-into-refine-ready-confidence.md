---
id: ENH-1708
title: Wire user_corrections + FTS5 Reads into refine-issue / ready-issue / confidence-check
type: ENH
priority: P3
status: open
parent: EPIC-1707
discovered_date: 2026-05-26
captured_at: "2026-05-26T00:48:43Z"
discovered_by: capture-issue
depends_on: [ENH-1782]
labels:
  - enhancement
  - captured
---

# ENH-1708: Wire user_corrections + FTS5 Reads into refine-issue / ready-issue / confidence-check

## Summary

Add `.ll/history.db` reads (specifically `user_corrections` and the FTS5 `search_index`) into three high-leverage refinement skills so they can surface "have I been told this before about this issue?" context without prompt bloat. First concrete child of EPIC-1707.

## Motivation

The producer side of `.ll/history.db` records `user_corrections` ("don't mock the database", "use snake_case here") and indexes content via FTS5 on `(kind, ref, anchor, ts)`. But no skill queries it. The three refinement skills below are the highest-leverage consumers because they decide whether an issue is implementation-ready — exactly where prior corrections most often apply:

- **`refine-issue`**: when adding codebase findings to an issue, a prior correction on the touched file is high-signal context.
- **`ready-issue`**: when validating an issue is ready, "user previously corrected our approach on this anchor" should block readiness or surface as a concern.
- **`confidence-check`**: when computing pre-implementation confidence, a recent correction on this issue's scope is a confidence-lowering signal.

Other skills (e.g. `commit`, `open-pr`, `run-tests`) get less value from history reads — they operate on artifacts that already exist, not on decisions about future code.

## Current Behavior

All three skills build their prompt from the issue file + targeted codebase grep results. They have no access to:
- Prior `user_corrections` referencing the issue ID, the file paths it touches, or the anchors it mentions.
- Recent `file_events` showing what's changed near this issue's scope since it was captured.
- Related `issue_events` (e.g., "a similar issue was deferred 2 weeks ago for reason X").

## Expected Behavior

Each of the three skills queries `.ll/history.db` via a small read API (introduced as part of EPIC-1707) and includes the matched rows in its prompt context. Queries are **anchor-driven** — by issue ID, by file path, or by FTS5 phrase from the issue title — not broad time-windowed dumps.

Example for `refine-issue`:
1. Skill loads issue file.
2. Skill extracts file paths from the issue's "Integration Map" or codebase findings.
3. Skill calls `history_reader.find_user_corrections(anchors=[file_path, issue_id])` and `history_reader.recent_file_events(path=file_path, since="30d")`.
4. Matched rows (capped at N=5 per query, dedup'd) are formatted into a "## Historical Context" prompt section.
5. If DB is missing/empty, skill proceeds without the section (no hard failure).

## Scope Boundaries

- **In scope**:
  - Read API methods consumed: `find_user_corrections(anchors)`, `recent_file_events(path, since)`, `search(query, kind, limit)`.
  - Wiring into exactly the three skills listed: `refine-issue`, `ready-issue`, `confidence-check`.
  - Result caps and dedup (avoid prompt bloat).
  - Graceful degradation for missing/empty DB.
  - Unit tests per skill verifying the prompt-section behavior.
- **Out of scope**:
  - Designing the read API itself (owned by EPIC-1707; this is a consumer).
  - Wiring history into other skills (separate children of the EPIC).
  - Schema changes.
  - Cross-project history.

## Implementation Steps

1. Confirm the read API surface from EPIC-1707 (block on its design if not yet done).
2. For each of the three skills, identify the prompt section where historical context should be injected (typically just before the "Codebase Findings" or "Confidence Factors" section).
3. Implement the query — anchor-driven, capped, dedup'd.
4. Add formatter that renders matched rows as a compact markdown block (1-2 lines per row, with timestamp).
5. Add graceful-degradation path for missing/empty DB.
6. Add tests covering: DB present with matches, DB present with no matches, DB missing, DB empty, stale rows older than the configured window.
7. Document the new prompt section in each skill's `SKILL.md`.

### Codebase Research Findings

_To be added by `/ll:refine-issue` — concrete file:line references for each step._

## Impact

- **Priority**: P3 — High value but not blocking; lands after EPIC-1707's read API is defined.
- **Effort**: Medium — three skills × (query + formatter + tests + docs).
- **Risk**: Medium — stale or irrelevant history actively misleads agents into spurious "concerns" or false confidence drops. Anchor-driven queries + caps mitigate but don't eliminate this.
- **Breaking Change**: No — additive prompt section, omitted when DB has nothing relevant.

## Acceptance Criteria

- `refine-issue`, `ready-issue`, and `confidence-check` each include a "## Historical Context" section in their generated prompts when matches exist.
- Each skill has tests covering: matches present, no matches, DB missing, DB empty.
- Each skill's `SKILL.md` documents the new section and when it appears.
- Per-skill prompt-byte impact when no matches: 0 bytes added.
- Per-skill prompt-byte impact when matches present: capped at ~500 tokens (configurable).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`

- `/ll:capture-issue` - 2026-05-26T00:48:43Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2c695cf-9995-4a8f-9ec7-81cdca0d77e5.jsonl`

---

**Open** | Created: 2026-05-26 | Priority: P3
