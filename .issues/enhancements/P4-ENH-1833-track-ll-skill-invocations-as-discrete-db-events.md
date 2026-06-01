---
id: ENH-1833
type: ENH
priority: P4
status: open
discovered_date: 2026-06-01
captured_at: "2026-06-01T01:10:54Z"
discovered_by: capture-issue
relates_to:
  - FEAT-1262
  - EPIC-1707
  - ENH-1830
labels:
  - enhancement
  - captured
---

# ENH-1833: Track `/ll:` skill invocations as discrete DB events

## Summary

When a user runs a `/ll:` skill (e.g., `/ll:refine-issue`, `/ll:capture-issue`),
that invocation is not captured in `history.db` unless `ll-session backfill` is
run manually against session JSONL files. There is no DB table or write path for
skill dispatch events. This makes it impossible to query "which skills were invoked
recently" or "how often was `/ll:ready-issue` used last week" from the DB alone.

## Current Behavior

Skill invocations are not recorded in `history.db` at dispatch time. The only way
historical skill usage appears in the DB is via `ll-session backfill`, which parses
session JSONL files post-hoc. There is no `skill_events` table and no real-time
write path. `ll-session recent --kind skill` returns nothing; FTS5 search has no
`kind='skill'` rows.

## Expected Behavior

Each `/ll:` skill invocation is written to a `skill_events` table in `history.db`
at dispatch time via the `user_prompt_submit` hook, recording `ts`, `session_id`,
`skill_name`, and `args` (truncated). `ll-session recent --kind skill` returns
these rows and FTS5 search includes them with `kind='skill'`.

## Motivation

Skill invocation history would enable:
- `ll-history` to report skill usage frequency alongside issue completion stats
- `analyze-workflows` to derive skill usage patterns directly from the DB
- Future personalization that surfaces skills the user frequently chains together

FEAT-1262 (deferred) was the original vehicle for capturing slash-command events,
but was superseded by the hook-intent abstraction with no replacement created for
the skill dispatch signal specifically.

## Acceptance Criteria

- A new `skill_events` table (or extend `tool_events` with a `skill_name` column)
  records each `/ll:` skill invocation with: `ts`, `session_id`, `skill_name`,
  `args` (truncated), `source` ("user_prompt_submit")
- The `user_prompt_submit` hook detects `/ll:<name>` patterns in the user message
  and writes the event
- FTS5 `search_index` is updated with `kind='skill'` rows
- `ll-session recent --kind skill` returns the captured rows
- Detection is best-effort: `/ll:` prefix match is sufficient; no deep arg parsing

## Implementation Steps

1. New migration (v4 or v5) adding `skill_events` table to `session_store.py`
2. Add `kind='skill'` to `_VALID_KINDS` and `_KIND_TABLE` in `session_store.py`
3. Add `record_skill_event(db_path, session_id, skill_name, args)` to `session_store.py`
4. Wire detection into a `user_prompt_submit` hook intent handler: scan message text
   for `/ll:[a-z-]+` pattern, extract skill name and remainder as args
5. Update FTS5 insert; add tests

## Files to Modify

- `scripts/little_loops/session_store.py` — new table, `record_skill_event()`
- `scripts/little_loops/hooks/` — `user_prompt_submit` or similar intent handler
- `hooks/hooks.json` — register hook if needed
- `scripts/tests/test_session_store.py` — skill event tests

## Depends On

- ENH-1830 is complementary (auto-backfill fills historical gaps; this fills forward)

## Scope Boundaries

- Detection is best-effort `/ll:` prefix regex match only; no deep arg parsing or validation
- Does not backfill historical skill events from existing JSONL files (ENH-1830 covers that)
- Does not capture non-`/ll:` slash commands (built-in `/clear`, `/help`, etc.)
- No analytics dashboard or aggregation UI; raw event capture only
- No deduplication of repeated invocations within a session

## Impact

- **Priority**: P4 — Useful observability improvement; not blocking any current workflow
- **Effort**: Small — Additive: new DB table, `record_skill_event()` helper, hook wiring; no existing behavior changed
- **Risk**: Low — Purely additive; no existing tables modified; hook write failure does not affect skill execution
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-01 | Priority: P4

## Session Log
- `/ll:format-issue` - 2026-06-01T01:20:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c78d4399-dc58-4488-ac5a-557b6cd5e073.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
