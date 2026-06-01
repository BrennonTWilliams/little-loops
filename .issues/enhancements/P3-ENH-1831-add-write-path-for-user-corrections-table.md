---
id: ENH-1831
type: ENH
priority: P3
status: open
discovered_date: 2026-06-01
captured_at: "2026-06-01T01:10:54Z"
discovered_by: capture-issue
relates_to:
  - ENH-1708
  - EPIC-1707
  - FEAT-1112
depends_on: [ENH-1830]
labels:
  - enhancement
  - captured
parent: EPIC-1707
---

# ENH-1831: Add write path for `user_corrections` table

## Summary

The `user_corrections` table in `history.db` was designed to capture moments when
the user corrects Claude's approach during a session. The table exists in the schema
(since v1) but has no active write path — nothing ever inserts rows into it.
ENH-1708 (open, P3) wires `user_corrections` reads into `refine-issue` /
`ready-issue` / `confidence-check`, but will silently return empty results until
this write path is implemented.

## Current Behavior

The `user_corrections` table exists in `history.db` since schema v1, but has no
active write path. Nothing ever inserts rows into it, so
`history_reader.find_user_corrections()` always returns `[]`.

## Expected Behavior

User correction signals detected from hook payloads (`post_tool_use` or
`user_prompt_submit`) are inserted into `user_corrections` with `content`,
`session_id`, and `source`. `ll-session recent --kind correction` returns captured
rows, and `history_reader.find_user_corrections()` returns non-empty results when
corrections exist.

## Motivation

User corrections are high-signal training data: they record exactly where the AI
deviated from user intent. Surfacing recent corrections during issue refinement
(ENH-1708) gives the model project-specific guidance that generalizes beyond the
current session. Without a writer, `history_reader.find_user_corrections()` always
returns `[]`, making ENH-1708's integration a no-op.

## Acceptance Criteria

- A detection heuristic identifies user correction signals from `post_tool_use` or
  `user_prompt_submit` hook payloads (e.g., user message starts with "no", "don't",
  "stop", "revert", "that's wrong", "not like that", or explicit correction phrases)
- Detected corrections are inserted into `user_corrections` with `content` (truncated
  to 512 chars), `session_id`, and `source` ("post_tool_use" or "user_prompt_submit")
- The heuristic has a low false-positive rate: only explicit correction signals are
  captured, not general user messages
- `ll-session recent --kind correction` returns the captured rows
- `history_reader.find_user_corrections()` returns non-empty results when corrections
  exist

## Scope Boundaries

- **In scope**: Keyword/regex-based correction-detection heuristic; `record_correction()` DB write method; `user_prompt_submit` hook integration; FTS5 index inclusion for `kind='correction'`; unit tests for detection heuristic and DB write path
- **Out of scope**: ML-based correction classification; retroactive detection from existing session logs; UI or reporting for browsing corrections; read-side ENH-1708 integration (handled separately in that issue)

## Implementation Steps

1. Define a correction-detection heuristic in `session_store.py` or a new
   `hooks/correction_detector.py` module — regex/keyword matching on message text
2. Wire detection into the `user_prompt_submit` hook intent handler
   (`hooks/pre_tool_use.py` or a new `hooks/user_prompt_submit.py`), inserting rows
   via `SessionStore.record_correction(content, session_id, source)`
3. Add `record_correction()` method to `session_store.py`
4. Update FTS5 `search_index` insert to include `kind='correction'` rows
5. Add tests for the detection heuristic (true positives, true negatives) and the
   DB insert path

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — add `record_correction()` method and FTS5 index insert
- `scripts/little_loops/hooks/` — new or updated intent handler for `user_prompt_submit` events
- `hooks/hooks.json` — register hook if `user_prompt_submit` event needs wiring
- `scripts/tests/test_session_store.py` — correction write/read round-trip tests and heuristic tests

### Dependent Files (Callers/Importers)
- `scripts/little_loops/history_reader.py` — `find_user_corrections()` will return non-empty results once write path exists
- ENH-1708 consumers (`refine-issue`, `ready-issue`, `confidence-check`) — receive actual correction data once writes land

### Similar Patterns
- Existing `SessionStore` write methods in `session_store.py` — follow same insert + FTS5 index pattern

### Tests
- `scripts/tests/test_session_store.py` — true-positive and true-negative heuristic cases; DB round-trip test for `record_correction()`

### Documentation
- N/A

### Configuration
- `hooks/hooks.json` — hook registration for `user_prompt_submit` event (if not already registered)

## API/Interface

```python
class SessionStore:
    def record_correction(
        self,
        content: str,        # truncated to 512 chars before insert
        session_id: str,
        source: str,         # "post_tool_use" or "user_prompt_submit"
    ) -> None:
        """Insert a detected user correction into the user_corrections table."""
```

## Impact

- **Priority**: P3 — ENH-1708's correction-based refinement silently returns `[]` until this lands; no user-visible breakage today
- **Effort**: Small-Medium — New `record_correction()` method and detection heuristic follow existing `SessionStore` write patterns; hook wiring is incremental
- **Risk**: Low — Purely additive write path; no changes to existing read behavior or schema
- **Breaking Change**: No

## Depends On

- ENH-1708 is the primary consumer of this write path

## Status

**Open** | Created: 2026-06-01 | Priority: P3

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:format-issue` - 2026-06-01T01:16:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eee9dd1e-f437-4c64-b581-24724e938107.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
