---
id: FEAT-2747
type: FEAT
title: Assistant-inclusive session compaction (message_events + assistant_messages)
priority: P3
status: done
parent: FEAT-2711
discovered_by: confidence-check
discovered_date: '2026-07-22'
completed_at: '2026-07-23T18:43:58Z'
labels:
- token-cost
- fsm
- session-store
relates_to:
- FEAT-2711
- FEAT-2598
size: Small
confidence_score: 90
outcome_confidence: 73
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 10
score_change_surface: 22
---

# FEAT-2747: Assistant-inclusive session compaction (message_events + assistant_messages)

## Summary

A new assistant-inclusive compaction function (joins `message_events` and
`assistant_messages`, extending `session_store.py`'s `compact_session()`/
`compact_result_for_session()` at line 3444 / `compaction/result.py:34`).
Carved out of FEAT-2711 so the new mechanism can be built and proven in
isolation before FEAT-2711 wires it into the FSM state chain.

## Motivation

FEAT-2711's spike (`scripts/tests/spike/fsm_continuity_compaction/`,
`/ll:spike` 2026-07-21) found that `compact_session()` reads only
`message_events` — populated exclusively from `type == "user"` JSONL records
by `_backfill_messages`. The assistant's derived understanding (file reads,
analysis, decisions) lives in a separate `assistant_messages` table that
`_compact_session_conn()` never queries. For a single FSM prompt-state
invocation, the "user" turn is just the already-known interpolated prompt —
the state's *new* information is entirely in the assistant turn.

**Used unmodified, `compact_session()`/`compact_result_for_session()` would
summarize the prompt already sent, not the reasoning a caller wants carried
forward.** This issue closes that gap independently of any FSM-side caller,
so FEAT-2711 can consume a proven primitive instead of building a novel
mechanism inline.

## Current Behavior

`compact_session()`/`compact_result_for_session()`
(`scripts/little_loops/session_store.py:3444`,
`scripts/little_loops/compaction/result.py:34`) summarize only user turns
(`message_events`), never `assistant_messages`.

## Expected Behavior

A new function — exact name/signature TBD by the implementer (e.g.
`compact_session_with_reasoning()`) — joins `message_events` and
`assistant_messages` and produces a summary that includes the assistant's
derived reasoning from the session, not just the prompt that was sent. The
function is callable standalone, with no dependency on FSM-layer wiring.

## Proposed Solution

Extend `scripts/little_loops/session_store.py` (near `compact_session()` at
line 3444) and/or `scripts/little_loops/compaction/result.py` (near
`compact_result_for_session()` at line 34) with the new function. Reuse the
existing LCM 3-level escalation machinery already in place rather than
reimplementing summarization from scratch — only the source query (which
tables it joins) needs to change.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The reusable escalation machinery is `_summarize_block()`
  (`session_store.py:3544`) and `_call_llm_for_summary()`
  (`session_store.py:3619`) — both operate on a plain `list[str]` of message
  contents and are agnostic to which table each string came from, confirming
  the issue's "reuse machinery unchanged" premise. `_estimate_tokens()`
  (`session_store.py:3539`, `len(s)//4` heuristic) is the other shared
  helper the new query's block-grouping loop will need.
- Concretely, the new function is a `_compact_session_conn()`-shaped sibling:
  keep everything from the greedy block-accumulation loop onward
  (`session_store.py:3720-3742` region) unchanged, and swap only the initial
  `SELECT ... FROM message_events` for the `UNION ALL` query documented under
  Integration Map's Codebase Research Findings below. A new public wrapper
  mirroring `compact_session()` (`session_store.py:4047`) — same
  `CompactionConfig` resolution, same `connect(db)`/`try`/`finally`
  lifecycle — is the appropriate entry point, matching the existing
  public/`_..._conn` pairing convention.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` (near `compact_session()`,
  line 3444) — add the new query joining `message_events` and
  `assistant_messages` for a given session ID.
- `scripts/little_loops/compaction/result.py` (near
  `compact_result_for_session()`, line 34) — add the assistant-inclusive
  counterpart that calls the new query and produces a `summary_text` result
  via the existing LCM escalation path.
- `scripts/little_loops/compaction/__init__.py` (lines 37-44) — `wire-issue`
  finding: this module explicitly re-exports `CompactResult` /
  `compact_result_for_session` via a hand-maintained `from
  little_loops.compaction.result import (...)` line + `__all__` list. If the
  new assistant-inclusive function is meant to be importable the same way
  existing callers import `compact_result_for_session` (FEAT-2711 will need
  this), it needs a matching entry added to both. Not enforced by any test —
  a manual convention-following step, easy to miss.

### Dependent Files (Callers/Importers)
- None today — this is new, standalone functionality. FEAT-2711 will become
  the first caller once it lands (`blocked_by: [FEAT-2747]` on FEAT-2711).
- **Confirmed via `ll-code callers-of` + grep (`/ll:wire-issue`)**: existing
  callers of the functions this new code sits alongside — none require
  changes, listed here only to confirm the "no existing callers to break"
  claim is accurate:
  - `scripts/little_loops/cli/compact_session.py:70-71` —
    `main_compact_session()` calls `compact_session()` /
    `compact_result_for_session()` directly (CLI entry point; unaffected,
    since the new function is a sibling, not a modification).
  - `scripts/little_loops/session_store.py:3888` — `_compact_sessions()`
    (the internal *batch* compaction path, distinct from the per-session
    `compact_session()` this issue extends) also calls
    `_compact_session_conn()` at line 3923. Unaffected by this issue since
    the new function is additive, but confirms `_compact_session_conn()` has
    a second existing caller beyond the public `compact_session()` wrapper —
    worth knowing if a future issue considers making the batch path
    assistant-inclusive too.
  - `scripts/little_loops/hooks/pre_compact.py` /
    `pre_compact_handoff.py` were checked and do **not** call
    `compact_session`/`compact_result_for_session` — ruled out as false
    leads from an initial manifest grep.

### Similar Patterns
- The existing `compact_session()`/`compact_result_for_session()`
  implementations — same file, same module, same tested LCM escalation path.
  This issue is a sibling function, not a new subsystem.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> ⚠ The `session_store.py:3444` / `compaction/result.py:34` anchors above are
> partially stale: `compact_session()` is now at **line 4047** and
> `_compact_session_conn()` (the actual query/escalation worker) is at
> **line 3720** — `3444` currently lands inside an unrelated function
> (`_backfill_skill_events()`). `compaction/result.py:34` for
> `compact_result_for_session()` is still accurate.

- **Exact query to extend** — `_compact_session_conn()`
  (`session_store.py:3720-3742`) runs
  `SELECT id, ts, content FROM message_events WHERE session_id = ? ORDER BY ts, id`,
  then greedily packs rows into token-budgeted blocks. The new function only
  needs to change this one query; the block-grouping/escalation/dedup code
  below it is schema-agnostic and can be reused unmodified.
- **`assistant_messages` schema** (`session_store.py:558-568`, added v11 /
  ENH-1942): `(id, ts, session_id, content, tool_use_count)` — the `(id, ts,
  content)` projection matches `message_events` exactly, so a
  `SELECT id, ts, content FROM message_events WHERE session_id=? UNION ALL
  SELECT id, ts, content FROM assistant_messages WHERE session_id=? ORDER BY
  ts, id` is schema-compatible with zero changes downstream. Populated by
  `_backfill_assistant_messages()` (`session_store.py:3294`), which the
  spike's `backfill_and_compact()` helper (see Tests below) already calls.
- **No existing `UNION ALL` precedent** — the one existing
  `message_events`⋈`assistant_messages` join in the codebase is
  `history_reader.py`'s `conversation_turns()` (~line 1990), which pairs each
  user turn with assistant turns via a temporal-adjacency correlated `JOIN`
  (not a shared key) bounded by the next user turn's timestamp. That shape
  fits a "pair turns" read, not `_compact_session_conn()`'s flat ordered
  `(id, ts, content)` block-builder — prefer the `UNION ALL` shape above over
  adapting `conversation_turns()`'s join.
- **Naming precedent for the sibling function**: no `_with_reasoning`/
  `_inclusive`/`_with_assistant` suffix exists anywhere in the codebase today.
  The closest analog is `_backfill_messages()` → `_backfill_assistant_messages()`
  (`session_store.py:3242` / `:3294`), whose docstring states "Mirrors
  `_backfill_messages` but selects `type == "assistant"` records" — same
  pairing convention this issue's new function should follow.
- **Design consideration — id collision across tables**: `message_events.id`
  and `assistant_messages.id` are both independent autoincrement PKs (no
  shared key). A `UNION ALL` row set needs a role tag (e.g. `'user'`/
  `'assistant'` literal column) to disambiguate, because
  `summary_spans.message_event_id` (`session_store.py:541`) is a `REFERENCES
  message_events(id)` FK only — it has no column for `assistant_messages`
  ids today. Decide during implementation whether `summary_spans` needs a
  new nullable FK column (e.g. `assistant_message_id`) or whether the new
  function should skip writing `summary_spans` rows for assistant-sourced
  content (accepting that `compact_result_for_session()`'s
  `compacted_messages` list stays `message_events`-only). This determines
  whether the schema needs a migration or not — flag before starting
  Implementation Step 2.

### Conditional Wiring — only if `summary_spans` gains an `assistant_message_id` column

_Added by `/ll:wire-issue` — this whole subsection is conditional on choosing
option (a) above (new nullable FK column). If option (b) is chosen (skip
`summary_spans` rows for assistant content), none of the following applies
and the issue's current "None required" Documentation claim holds as-is._

- **Migration**: `_MIGRATIONS` (`session_store.py:372`) is a flat list;
  current highest is v33 (`# v33 (ENH-2504): verifier verdict outcome
  telemetry`). A new column would be v34, following the same
  comment-block-above-`ALTER TABLE` convention as every prior entry (e.g. the
  v12 entry at line 570). Note: `summary_spans` has a composite
  `PRIMARY KEY (summary_id, message_event_id)` — an assistant-sourced row
  would need `message_event_id = NULL`, which needs an explicit dedup/PK
  strategy decision (SQLite's NULL-in-PK uniqueness semantics), not just a
  bare `ALTER TABLE`.
  - `summary_spans` is already listed in `_KINDLESS_TABLES`
    (`session_store.py:290`); an `ALTER TABLE` on an already-classified table
    does **not** require a new `ll-verify-kinds` entry (that gate only fires
    on new `CREATE TABLE` statements) — confirmed so this isn't mistaken for
    a required step.
- **Downstream consumers that would need an assistant-branch** (currently
  `message_events`-only, confirmed via read):
  - `scripts/little_loops/history_reader.py` `ll_grep()` (~line 2062) and
    `ll_expand()` (~line 2146) — both `JOIN summary_spans ss ON
    ss.message_event_id = me.id` against `message_events` only.
  - `GrepResult` dataclass (`history_reader.py:348-357`) has a
    `message_event_id: int` field with no assistant-id equivalent.
- **Docs that would need a new row/section** (contradicts the issue's
  current "None required at this scope" Documentation claim, conditional on
  this schema path):
  - `docs/guides/HISTORY_SESSION_GUIDE.md` — migration table (lines 58-91)
    needs a `v34 | FEAT-2747 | ...` row; lines 69/116 describe the current
    two-column `summary_spans` shape and would need amending.
  - `docs/reference/API.md:7726-7741` — `CompactResult` /
    `compact_result_for_session()` section would need a parallel entry for
    the new function.
  - `docs/ARCHITECTURE.md:761,764` — migration range (`v1-v33`) and
    `compaction.result` module description would need bumping/updating.

### Discrepancy Note

_Added by `/ll:wire-issue`_ — this issue's own Codebase Research Findings
above (line ~129) state `assistant_messages` was "added v11 / ENH-1942".
`scripts/tests/test_session_store.py`'s `TestSchemaV10::test_v9_to_v10_migration`
asserts `"assistant_messages" in names` after migrating v9→v10 — i.e. the
table actually lands at **v10**, one version earlier than stated. Not
load-bearing for this issue's implementation, but affects which
`_MIGRATIONS` slice a new migration test (if any) should bootstrap from.

### Tests
- Promote the spike's
  `TestSummaryOmitsAssistantContent::test_compact_summary_omits_assistant_derived_content`
  (currently in `scripts/tests/spike/fsm_continuity_compaction/`) as the
  regression baseline proving the *old* gap.
- Add a new `test_compact_includes_assistant_derived_content`-style test
  proving the *new* function closes it.
- Reuse the existing regression fixture set referenced in FEAT-2711's Spike
  Results (`test_compaction.py`: 18 passed; `test_session_store.py -k
  "backfill or compact"`: 66 passed) to confirm no regression in the
  unmodified `compact_session()`/`compact_result_for_session()` callers.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The spike test to promote is
  `scripts/tests/spike/fsm_continuity_compaction/test_continuity_pipeline.py:127-162`
  (`TestSummaryOmitsAssistantContent::test_compact_summary_omits_assistant_derived_content`).
  Pattern: mock `little_loops.session_store.subprocess.run`, run
  `backfill_and_compact()` (`continuity_pipeline.py:25`), collect every `-p
  <prompt>` arg actually sent to the mocked summarizer CLI, then assert user
  turns are present and the assistant turn is absent. The new
  `test_compact_includes_assistant_derived_content` should mirror this exact
  structure, inverting only the final assertion (assistant turn now present).
- `backfill_and_compact()` (`continuity_pipeline.py:25`) already seeds both
  `message_events` and `assistant_messages` via `_backfill_messages()` +
  `_backfill_assistant_messages()` before calling `compact_session()` — the
  fixture-seeding half of this work is already done by the spike; only the
  query inside `_compact_session_conn()` needs to change.
- `TestCompactSession` (`scripts/tests/test_session_store.py:2209`) has the
  established fixture-builder pattern (`_make_db_with_messages`-style helper
  seeding `sessions` + `message_events` rows) and `TestCompactResult`
  (`scripts/tests/test_compaction.py:129`) has the `CompactResult`-field
  assertion pattern — model the new function's unit tests after these two
  classes.
- `scripts/tests/test_assistant_messages.py` already covers the
  `assistant_messages` table schema (v11 migration) and its backfill in
  isolation — useful for confirming fixture data shape but does not test
  compaction; not itself a target for modification.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_session.py:714,831` and
  `scripts/tests/test_history_reader.py:1172,1288` — additional existing
  `compact_session()` callers (DB-fixture helpers for `ll_grep`/`ll_expand`/
  `ll_describe` tests) beyond the two files the issue already names. All are
  `message_events`-only and unaffected by this issue's additive change —
  listed here only to confirm the "no regression in unmodified callers"
  acceptance criterion has full coverage, not because they need edits.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_compaction.py::TestMessageEventsUnchangedRegression::test_compact_session_does_not_delete_message_events`
  (line ~285) is the existing precedent for a "does not mutate/delete source
  table" regression guard — if the new function is also expected not to
  mutate `assistant_messages`, add a parallel guard following this shape.
- If the conditional `summary_spans.assistant_message_id` schema path above
  is taken, model the new migration test after
  `TestSchemaV12::test_v11_to_v12_migration`
  (`test_session_store.py:2172-2206`) or the more recent
  `TestSchemaV14::test_v13_to_v14_migration` (`test_session_store.py:3932+`)
  — both follow a bootstrap-N-1-migrations → stamp `schema_version` →
  `ensure_db()` → assert-version-bump-and-new-column shape.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- The "None required at this scope" claim above holds only if the
  `summary_spans` schema is left untouched (design option (b) in the
  Codebase Research Findings above). If option (a) — a new
  `assistant_message_id` column — is chosen instead, three docs need a new
  row/section: `docs/guides/HISTORY_SESSION_GUIDE.md` (migration table +
  `summary_spans` shape description), `docs/reference/API.md:7726-7741`
  (`CompactResult`/`compact_result_for_session` section), and
  `docs/ARCHITECTURE.md:761,764` (migration version range +
  `compaction.result` module description). See the "Conditional Wiring"
  subsection under Integration Map's Codebase Research Findings for the full
  detail.

## Implementation Steps

1. Design the join query: `message_events` + `assistant_messages` keyed by
   session ID, in chronological order.
2. Implement the new compaction function, reusing the existing LCM
   escalation path from `compact_session()`/`compact_result_for_session()`.
3. Promote the spike's
   `test_compact_summary_omits_assistant_derived_content` test as the
   regression baseline for the old gap.
4. Add a new test proving the new function includes assistant-derived
   content.
5. Run the full `test_compaction.py` and `test_session_store.py -k
   "backfill or compact"` suites to verify no regression in existing
   `compact_session()` callers.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

6. Resolve the `summary_spans` design question (Codebase Research
   Findings, Integration Map) before writing the new function's insert path
   — this decides whether steps 7-9 apply.
7. If a new `assistant_message_id` column is chosen: add a v34 entry to
   `_MIGRATIONS` (`session_store.py:372`), update `history_reader.py`'s
   `ll_grep()`/`ll_expand()`/`GrepResult` to branch on it, and add the three
   doc updates listed under "Conditional Wiring".
8. Update `scripts/little_loops/compaction/__init__.py`'s import line and
   `__all__` list to re-export the new function, matching how
   `compact_result_for_session` is currently exported.
9. Add a `test_assistant_messages`-untouched regression guard alongside the
   new function's tests, mirroring
   `TestMessageEventsUnchangedRegression::test_compact_session_does_not_delete_message_events`.

## Acceptance Criteria

- [x] New function joins `message_events` and `assistant_messages` and the
      resulting summary includes assistant-derived content (proven by a
      test, not just manual inspection).
- [x] Existing `compact_session()`/`compact_result_for_session()` callers
      and tests are unaffected (no signature break).
- [x] Function is usable standalone (no FSM-layer dependency) so FEAT-2711
      can call it once unblocked.

## Impact

- **Priority**: P3 — matches parent FEAT-2711's priority; blocks it.
- **Effort**: Small — isolated to `session_store.py`/`compaction/result.py`,
  well-scoped by the FEAT-2711 spike (mechanics already proven: synchronous
  backfill-then-compact has no race, `session_id` capture works).
- **Risk**: Low — new query + summarization path, no existing callers to
  break, spike already retired the feasibility risks.

## Session Log
- `/ll:confidence-check` - 2026-07-23T18:33:04 - `031310d2-6f65-430d-b4b1-b144d2dd3f15.jsonl`
- `/ll:wire-issue` - 2026-07-23T18:30:48 - `6f27b3f4-1759-4704-a6d8-e7c3c2978976.jsonl`
- `/ll:refine-issue` - 2026-07-23T18:21:57 - `a7e1da84-e805-4aa8-8603-1ea25facc936.jsonl`
- Decomposed from FEAT-2711 on 2026-07-22 by `/ll:confidence-check` follow-up
  (outcome-confidence mitigation for FEAT-2711's Complexity risk).
- `/ll:manage-issue` - 2026-07-23T18:43:15Z - `ea4b683d-1cd4-4dbb-97f7-c533ec19a4b5.jsonl`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-07-23
- **Status**: Completed

### Changes Made
- `scripts/little_loops/session_store.py`: added
  `_compact_session_conn_with_reasoning()` (UNION ALL over `message_events` +
  `assistant_messages`, role-tagged, reusing the existing greedy block
  grouping and `_summarize_block()` escalation) and its public wrapper
  `compact_session_with_reasoning()`, mirroring `compact_session()`'s
  `CompactionConfig`/`connect` lifecycle. Neither writes to
  `summary_nodes`/`summary_spans` — see design note below.
- `scripts/little_loops/compaction/result.py`: added
  `compact_result_for_session_with_reasoning()`, the assistant-inclusive
  counterpart to `compact_result_for_session()`.
- `scripts/little_loops/compaction/__init__.py`: re-exported
  `compact_result_for_session_with_reasoning` alongside
  `compact_result_for_session` (Wiring Phase step 8).
- `scripts/tests/spike/fsm_continuity_compaction/test_continuity_pipeline.py`:
  added `TestSummaryIncludesAssistantContent`, mirroring
  `TestSummaryOmitsAssistantContent` with the final assertion inverted.
- `scripts/tests/test_compaction.py`: added `TestCompactResultWithReasoning`
  (mirrors `TestCompactResult`) and `TestAssistantMessagesUnchangedRegression`
  (Wiring Phase step 9, mirrors `TestMessageEventsUnchangedRegression`).

### Design decision (resolves the issue's open `summary_spans` question)
Investigation found a constraint the issue's own research didn't surface:
`idx_summary_nodes_condensed_dedup` is `UNIQUE(session_id) WHERE
kind='condensed'` — one condensed node per session, with no discriminator for
which function produced it. Persisting the new function's output into
`summary_nodes`/`summary_spans` under the same `session_id` would silently
collide with `compact_session()`'s existing condensed node, regardless of
which `summary_spans` FK option (a/b) was chosen. The new function therefore
does not persist at all — it computes and returns the assistant-inclusive
summary directly (a plain `(str | None, list[int])` tuple / `CompactResult`),
matching FEAT-2711's actual need (a value for one FSM prompt-state invocation
to carry forward, not a durable DAG node). This avoids the v34 migration +
`history_reader.py` branching + doc updates the issue's conditional wiring
section flagged, keeping the change scoped to the issue's own "Small
effort"/"Low risk" assessment. Full detail in
`thoughts/shared/plans/2026-07-23-FEAT-2747-management.md`.

### Verification Results
- Tests: PASS (full suite: 15965 passed, 38 skipped)
- Lint: PASS (`ruff check`)
- Types: PASS (`mypy`)
- Integration: PASS (additive siblings; no existing callers changed)

---

## Status

**Done** | Created: 2026-07-22 | Priority: P3
