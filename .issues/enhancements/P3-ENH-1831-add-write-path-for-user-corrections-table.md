---
id: ENH-1831
type: ENH
priority: P3
status: done
discovered_date: 2026-06-01
captured_at: '2026-06-01T01:10:54Z'
completed_at: '2026-06-01T05:49:22Z'
discovered_by: capture-issue
relates_to:
- ENH-1708
- EPIC-1707
- FEAT-1112
depends_on:
- ENH-1830
labels:
- enhancement
- captured
parent: EPIC-1707
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `hooks/scripts/user-prompt-check.sh` — after `INPUT=$(cat)`, add `echo "$INPUT" | python -m little_loops.hooks user_prompt_submit`; follow the `hooks/adapters/claude-code/session-start.sh` pattern; this is the only change required for the Python handler to fire under Claude Code (Codex adapter `hooks/adapters/codex/prompt-submit.sh` already pipes correctly)
7. Create `scripts/tests/test_hook_user_prompt_submit.py` — new test file with `TestUserPromptSubmitWithSessionStore` class; test both the correction-detected-writes-db path and the non-correction/analytics-disabled/unwritable-store paths; follow `TestPostToolUseWithSessionStore` in `test_hook_post_tool_use.py`
8. Update `scripts/tests/test_ll_session.py` — add `test_recent_correction_kind` and `test_recent_correction_empty` to `TestMainSession`; follow `test_recent_loop` pattern

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete implementation details from codebase analysis:_

- **Step 1** (heuristic): define `_CORRECTION_PATTERNS = re.compile(r"^\s*(no[,\s]|don'?t\s|stop\s|revert|that'?s wrong|not like that)", re.IGNORECASE)` and `def is_correction(text: str) -> bool` alongside private helpers in `session_store.py`; or co-locate in `hooks/user_prompt_submit.py` if preferred to keep detection close to the write call
- **Step 2** (hook wiring — critical): `user_prompt_submit.handle()` in `scripts/little_loops/hooks/user_prompt_submit.py` is in `_dispatch_table()` but is NOT reached by the current `hooks/scripts/user-prompt-check.sh`; update that bash script to pipe its JSON stdin to `python -m little_loops.hooks user_prompt_submit` (same pattern as `hooks/adapters/claude-code/session-start.sh`); the prompt text will then be available via `event.payload.get("prompt", "")`; `session_id` comes from `event.session_id`
- **Step 3** (write method): implement as standalone `def record_correction(db_path, content, session_id, source)` — NOT a class method; truncate `content = content[:512]` before insert; exact `_index()` call: `_index(conn, content=content, kind="correction", ref=session_id or "", anchor=source or "", ts=ts)`
- **Step 4** (FTS5): no additional wiring needed beyond calling `_index()` in step 3 — `_VALID_KINDS` and `_KIND_TABLE["correction"]` are already defined
- **Step 5** (tests): model round-trip test after `TestToolEventsByteColumns.test_recent_tool_returns_byte_columns` — `connect(db)` + direct `INSERT` or `record_correction()` call, then `recent(db, kind="correction")`, assert `rows[0]["content"]` and `rows[0]["source"]`; parametrize `is_correction()` with ≥3 true positives (`"no, don't do that"`, `"stop"`, `"revert that"`) and ≥3 true negatives (`"no problem"`, `"sounds good"`, `"noted"`)

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — add `record_correction()` method and FTS5 index insert
- `scripts/little_loops/hooks/` — new or updated intent handler for `user_prompt_submit` events
- `hooks/hooks.json` — register hook if `user_prompt_submit` event needs wiring
- `scripts/tests/test_session_store.py` — correction write/read round-trip tests and heuristic tests
- `hooks/scripts/user-prompt-check.sh` — add `echo "$INPUT" | python -m little_loops.hooks user_prompt_submit` so the Python dispatcher actually fires for Claude Code hosts; current script reads stdin via `INPUT=$(cat)` but never pipes it to Python — `user_prompt_submit.handle()` is unreachable for Claude Code without this change [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/history_reader.py` — `find_user_corrections()` will return non-empty results once write path exists
- ENH-1708 consumers (`refine-issue`, `ready-issue`, `confidence-check`) — receive actual correction data once writes land

### Similar Patterns
- Existing `SessionStore` write methods in `session_store.py` — follow same insert + FTS5 index pattern

### Tests
- `scripts/tests/test_session_store.py` — true-positive and true-negative heuristic cases; DB round-trip test for `record_correction()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_user_prompt_submit.py` — **new test file** (does not exist yet); follow `TestPostToolUseWithSessionStore` in `test_hook_post_tool_use.py`: `_write_config(analytics_enabled=True)` + `monkeypatch.chdir` + `handle(_event({"prompt": "..."}, cwd=...))` + `sqlite3.connect(db_path)` assertions; tests needed: `test_correction_detected_writes_db`, `test_non_correction_writes_no_db_row`, `test_skips_write_when_analytics_disabled`, `test_graceful_when_store_unwritable`
- `scripts/tests/test_ll_session.py` — add `test_recent_correction_kind` (insert via `record_correction()` → `ll-session --db ... recent --kind correction` → assert content in output) and `test_recent_correction_empty` (no rows → assert "No correction events" or equivalent); follow `TestMainSession.test_recent_loop` pattern
- `scripts/tests/test_hook_intents.py` — verify `test_dispatch_user_prompt_submit_happy_path` still passes; payload `"fix the authentication bug in this project"` does not match correction patterns, so safe, but confirm after wiring the handler

### Documentation
- N/A (core docs already reference `ll-session recent --kind correction` and the `user_prompt_submit` intent)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — **conditional**: update `### analytics` section to mention `user_corrections` writes if the correction write path is gated by `analytics.enabled` (follow the `post_tool_use.py` analytics-gate pattern); no change needed if writes are unconditional — this is an implementer decision point

### Configuration
- `hooks/hooks.json` — hook registration for `user_prompt_submit` event (if not already registered)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No schema migration needed**: `_VALID_KINDS` already contains `"correction"` and `_KIND_TABLE["correction"] = "user_corrections"` in `session_store.py` — FTS5 routing is fully wired; step 4 only requires calling `_index(conn, content=content[:512], kind="correction", ref=session_id or "", anchor=source, ts=ts)` inside `record_correction()`
- **`record_correction` should be a standalone function** (not a class method): follow `write_file_event()` — `connect()` → `INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, ?)` → `_index(conn, ...)` → `conn.commit()` → `conn.close()` in `try/finally`; the `SessionStore` class shown in the API section is the wrong shape for this codebase pattern
- **Critical hook wiring gap**: `hooks/scripts/user-prompt-check.sh` (the script registered in `hooks/hooks.json` for `UserPromptSubmit`) does **not** pipe its stdin to the Python dispatcher — `user_prompt_submit.handle()` is in `_dispatch_table()` but is never invoked by the current bash script; must either (a) update `user-prompt-check.sh` to pipe JSON stdin to `python -m little_loops.hooks user_prompt_submit` following the `hooks/adapters/claude-code/session-start.sh` pattern, or (b) place detection logic directly in the bash script calling `python -c "..."` inline
- **Detection heuristic pattern to follow**: module-level compiled regex (see `post_tool_use._BASH_PATH_RE`) or a phrasing-map of `(pattern_str, label)` tuples searched with `re.search(..., re.IGNORECASE)` as in `output_parsing._extract_verdict_from_text()` — apply against `text[:512]` to stay within the 512-char truncation limit
- **Test template**: `test_hook_post_tool_use.py::TestPostToolUseWithSessionStore` — uses `_write_config(tmp_path, analytics_enabled=True)`, `monkeypatch.chdir(tmp_path)`, and `handle(_event(payload, cwd=str(tmp_path)))`; use `@pytest.mark.parametrize` for true-positive / true-negative heuristic cases
- **Additional test file**: `scripts/tests/test_history_reader.py` already has `find_user_corrections` read tests using direct SQL inserts — round-trip tests (write via `record_correction()`, read via `recent(db, kind="correction")`) belong in `test_session_store.py` following `TestToolEventsByteColumns.test_recent_tool_returns_byte_columns`

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
- `/ll:ready-issue` - 2026-06-01T05:39:03 - `c8daa84a-d638-4374-bc4f-299e7f02f75a.jsonl`
- `/ll:confidence-check` - 2026-06-01T06:00:00 - `23b4d655-f133-4f14-95cf-cd3a9ec650ea.jsonl`
- `/ll:wire-issue` - 2026-06-01T05:35:54 - `25d24d41-feb1-4738-984e-38b0f9f355ac.jsonl`
- `/ll:refine-issue` - 2026-06-01T05:29:59 - `757bcfad-eb40-4ad8-ae8c-e59ea37ce8e1.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:59 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:format-issue` - 2026-06-01T01:16:53 - `eee9dd1e-f437-4c64-b581-24724e938107.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
