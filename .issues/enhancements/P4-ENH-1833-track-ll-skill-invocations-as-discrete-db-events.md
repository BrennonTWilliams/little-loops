---
id: ENH-1833
type: ENH
priority: P4
status: done
discovered_date: 2026-06-01
captured_at: '2026-06-01T01:10:54Z'
completed_at: '2026-06-01T07:41:12Z'
discovered_by: capture-issue
relates_to:
- FEAT-1262
- EPIC-1707
- ENH-1830
depends_on:
- ENH-1832
- ENH-1830
- ENH-1831
labels:
- enhancement
- captured
parent: EPIC-1707
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
decision_needed: false
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

1. **New migration** (`session_store.py`): Append `_MIGRATIONS[7]` with the SQL below; update `SCHEMA_VERSION = 7` at line 48:
   ```sql
   CREATE TABLE IF NOT EXISTS skill_events (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       ts TEXT NOT NULL,
       session_id TEXT,
       skill_name TEXT,
       args TEXT
   );
   ```
2. **Registry update** (`session_store.py:50-58`): Add `"skill"` to `_VALID_KINDS` and `"skill": "skill_events"` to `_KIND_TABLE`.
3. **Write function** (`session_store.py` after `record_correction()`): Add `record_skill_event(db_path, session_id, skill_name, args, config=None)` following the `record_correction()` pattern at line 338. No config gate in this issue — the `config=None` param is a forward-compatibility stub so ENH-1835 can inject the `analytics.capture.skills` gate without a signature change. Truncate `args` to 200 chars. FTS5 index call: `_index(conn, content=skill_name, kind="skill", ref=session_id or "", anchor=skill_name, ts=ts)`.
4. **Hook wiring** (`hooks/user_prompt_submit.py:76`): Insert after the `TODO(ENH-1835)` comment in the analytics block (lines 69–76, which runs **before** the bypass guard at ~line 94). No config gate here — ENH-1835 owns per-skill filtering:
   ```python
   m = re.match(r"^/ll:([a-z][a-z0-9-]*)(.*)", user_prompt.strip(), re.DOTALL)
   if m:
       session_id = event.payload.get("session_id") or event.session_id
       with contextlib.suppress(Exception):
           record_skill_event(cwd / ".ll" / "history.db", session_id,
                              m.group(1), m.group(2).strip()[:200])
   ```
5. **CLI** (`cli/session.py:72`): Add `"skill"` to the `choices` list in the `--kind` argument of the `recent_parser`. **Also update the `search_parser` choices at ~line 61** — both parsers share a parallel `choices=` list; omitting the `search_parser` update will cause `ll-session search --fts "x" --kind skill` to be rejected with `SystemExit` even though the FTS index will contain `kind='skill'` rows.
6. **Tests** (`test_session_store.py`): Add `TestRecordSkillEvent` class — roundtrip, FTS indexed, gate disabled. (`test_hook_user_prompt_submit.py`): Add class for skill write with analytics enabled/disabled. Run: `python -m pytest scripts/tests/test_session_store.py scripts/tests/test_hook_user_prompt_submit.py -v`.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py:48` — update `SCHEMA_VERSION` constant (6→7)
- `scripts/little_loops/session_store.py:50` — add `"skill"` to `_VALID_KINDS` frozenset
- `scripts/little_loops/session_store.py:51-58` — add `"skill": "skill_events"` to `_KIND_TABLE`
- `scripts/little_loops/session_store.py` (`_MIGRATIONS` list) — append `_MIGRATIONS[7]` with `CREATE TABLE IF NOT EXISTS skill_events`
- `scripts/little_loops/session_store.py` (after `record_correction()` at line ~338) — add `record_skill_event()`
- `scripts/little_loops/hooks/user_prompt_submit.py:76` — add skill detection in analytics block after the `TODO(ENH-1835)` comment
- `scripts/little_loops/cli/session.py:72` — add `"skill"` to `--kind` argument choices list

### Dependent Files (Tests)
- `scripts/tests/test_session_store.py` — add `TestRecordSkillEvent` class following `TestRecordCorrection` pattern (line ~1115); **update** `TestSchemaV6.test_schema_version_is_six` (hardcoded `assert SCHEMA_VERSION == 6` at line ~986 will break at v7 — update to `== 7` or add `TestSchemaV7`); **update** `TestEnsureDb.test_all_tables_created` (add `"skill_events"` to the checked table tuple at line ~52)
- `scripts/tests/test_hook_user_prompt_submit.py` — add `TestUserPromptSubmitSkillWrite` class following `TestUserPromptSubmitWithSessionStore` pattern (line ~43)
- `scripts/tests/test_ll_session.py` — add `test_recent_subcommand_skill_accepted` to `TestArgumentParsing`; add `test_recent_skill_kind` and `test_recent_skill_empty` to `TestMainSession` following the `test_recent_correction_kind`/`test_recent_correction_empty` pattern (line ~385)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — both the `search` and `recent` flag tables in the `ll-session` section list `--kind` choices inline (e.g., `{tool,file,issue,loop,correction,message}`); add `skill` to both tables [Agent 2 finding]
- `docs/reference/API.md` — `main_session` `recent` subcommand description at ~line 3458 enumerates valid kind values; add `skill` [Agent 2 finding]
- `docs/ARCHITECTURE.md` — schema versions table (lines ~538–545) lists v1–v6; add a v7 row for `skill_events` [Agent 2 finding]

### No Changes Needed
- `hooks/hooks.json` — `UserPromptSubmit` hook already registered; no new entry required
- `scripts/little_loops/config/features.py` — `AnalyticsCaptureConfig.skills: list[str]` already defined (line ~404)

### Similar Patterns
- `record_correction()` at `session_store.py:338` — direct template for `record_skill_event()`; same config-gate → connect → INSERT → `_index()` → commit/finally pattern
- `_MIGRATIONS` additive table entry (e.g. migration adding `message_events`) — template for the new `skill_events` migration
- `TestRecordCorrection` at `test_session_store.py:1115` — test template (roundtrip, FTS indexed, gate disabled)
- `TestUserPromptSubmitWithSessionStore` at `test_hook_user_prompt_submit.py:43` — hook test template

## Files to Modify

- `scripts/little_loops/session_store.py` — new table, `record_skill_event()`
- `scripts/little_loops/hooks/user_prompt_submit.py` — skill detection in analytics block
- `scripts/little_loops/cli/session.py` — add `"skill"` to `--kind` choices
- `scripts/tests/test_session_store.py` — skill event tests
- `scripts/tests/test_hook_user_prompt_submit.py` — hook skill write tests

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

## Resolution

Implemented `skill_events` table (schema v7), `record_skill_event()` write helper, hook wiring in `user_prompt_submit.py`, and `"skill"` added to `--kind` choices in both `search` and `recent` subcommands of `ll-session`. Tests added for roundtrip, FTS indexing, hook dispatch, and CLI argument parsing.

## Status

**Done** | Created: 2026-06-01 | Completed: 2026-06-01 | Priority: P4

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors

- **Open decision on config-gate implementation**: Implementation Steps 3 & 4 explicitly wire `feature_enabled_for(config, "analytics.capture.skills", ...)` in `record_skill_event()` and the hook block. The Scope Boundary note (added by `/ll:audit-issue-conflicts`) contradicts this: "Ship `record_skill_event()` without a config gate; ENH-1835 will add the analytics.capture.skills glob check." Resolve before implementing by updating Steps 3 & 4 to align with the Scope Boundary decision — the note appears authoritative but the steps haven't been updated to reflect it.

## Session Log
- `/ll:ready-issue` - 2026-06-01T07:36:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5efdcf76-6192-4dbd-9da2-f8caab8e4345.jsonl`
- `/ll:confidence-check` - 2026-06-01T08:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6416e06-4afd-4107-8a6a-153a47d898fb.jsonl`
- `/ll:decide-issue` - 2026-06-01T07:31:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b5ee914-f3aa-48b7-a5c7-01c672a23761.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d6ae5a2-5cb2-4b13-b9c2-4dfc50ceada2.jsonl`
- `/ll:wire-issue` - 2026-06-01T07:25:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef7ff611-871b-4275-bb3a-7135e10433e8.jsonl`
- `/ll:refine-issue` - 2026-06-01T07:21:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/058af3ee-7008-4c20-ace5-9dc421e66beb.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T04:19:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f60c9218-3661-4445-8adb-23f9182491a5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:format-issue` - 2026-06-01T01:20:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c78d4399-dc58-4488-ac5a-557b6cd5e073.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Per-skill filtering via `analytics.capture.skills` is out of scope for this issue and owned by ENH-1835. Ship `record_skill_event()` without a config gate; ENH-1835 will add the `analytics.capture.skills` glob check. Design `record_skill_event()` to accept an optional config parameter so ENH-1835 can inject the gate without a method signature change. Related: ENH-1833 vs ENH-1835 (MEDIUM requirement conflict resolved by /ll:audit-issue-conflicts).
