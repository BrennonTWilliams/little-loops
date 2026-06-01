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
labels:
  - enhancement
  - captured
---

# ENH-1831: Add write path for `user_corrections` table

## Summary

The `user_corrections` table in `history.db` was designed to capture moments when
the user corrects Claude's approach during a session. The table exists in the schema
(since v1) but has no active write path — nothing ever inserts rows into it.
ENH-1708 (open, P3) wires `user_corrections` reads into `refine-issue` /
`ready-issue` / `confidence-check`, but will silently return empty results until
this write path is implemented.

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

## Files to Modify

- `scripts/little_loops/session_store.py` — `record_correction()` method
- `scripts/little_loops/hooks/` — new or updated intent handler for user prompt events
- `hooks/hooks.json` — register hook if needed
- `scripts/tests/test_session_store.py` — correction write/read round-trip tests

## Depends On

- ENH-1708 is the primary consumer of this write path

## Session Log
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
