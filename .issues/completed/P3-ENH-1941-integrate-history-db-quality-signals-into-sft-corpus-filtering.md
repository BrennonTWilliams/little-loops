---
id: ENH-1941
title: Integrate history.db session-quality signals into sft-corpus filtering
type: ENH
priority: P3
status: done
captured_at: '2026-06-04T15:57:41Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1880
relates_to:
- EPIC-1707
- ENH-1710
labels:
- epic: EPIC-1880
- enhancement
- sft
- history-db
- corpus-quality
- captured
confidence_score: 82
outcome_confidence: 64
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 15
score_change_surface: 25
decision_needed: false
missing_artifacts: true
implementation_order_risk: true
size: Very Large
---

# ENH-1941: Integrate history.db session-quality signals into sft-corpus filtering

## Summary

Join `history.db` session metadata (EPIC-1707) against the `sft-corpus` pipeline at filter time via session ID, so the filter state can gate on structured quality signals — issue outcomes, user corrections, tool invocation counts, and file modifications — instead of only token length and PII regex matches.

## Context

Identified during EPIC-1880 status review. The `sft-corpus` pipeline currently drops all structured session metadata at extraction time: `extract_conversation_turns()` returns bare `list[tuple[str, str]]` (role, content) pairs. Meanwhile, `history.db` already captures per-session structured data across six event tables (`user_corrections`, `issue_events`, `tool_events`, `file_events`, `loop_events`, `message_events`) plus an FTS5 index — but none of it flows into corpus quality decisions.

ENH-1710 (session-ID → JSONL path mapping) provides the join key between the two data sources. The read API (`history_reader.py`) and `ll-history-context` CLI (ENH-1846) already exist and follow a graceful-degradation pattern when `history.db` is missing or empty — the pipeline can adopt the same pattern.

## Motivation

The difference between "all conversations" and "conversations that closed issues, used tools, and had no user corrections" is the difference between a corpus that trains a generic chatbot and one that trains a useful coding assistant. The data to make this distinction already exists — it's just not wired into the pipeline.

Without this integration, the corpus includes:
- Sessions where the assistant went in circles and the user gave up
- Sessions that were pure research/planning with no code changes
- Sessions where the user repeatedly corrected the assistant
- Sessions with no measurable outcome

These are low-quality training examples that dilute the signal in the final corpus.

## Current Behavior

The `sft-corpus` filter state can only gate on:
- Token length (`min_tokens`, `max_tokens`) — a word-count approximation
- PII presence (`pii_action: flag | redact | discard`) — regex-based email/phone/SSN matching via `little_loops.pii`

All other session metadata is discarded at extraction time.

## Expected Behavior

The filter state gains optional quality predicates backed by `history.db` lookups:

```yaml
context:
  # Existing
  min_tokens: 50
  max_tokens: 4096
  pii_action: redact
  # New (all optional; omit to skip the check)
  require_issue_outcome: true       # only sessions that closed an issue
  exclude_user_corrections: true    # skip sessions where user said "wrong"
  min_tool_invocations: 3           # require at least N tool calls
  require_file_modifications: true  # only sessions that actually changed code
```

When `history.db` is missing, empty, or lacks the relevant tables, these predicates degrade to no-ops (pass-through) — following the EPIC-1707 graceful-degradation pattern established in `history_reader.py`.

## Success Metrics

- **Corpus quality**: Sessions with `issue_outcome=done` + `has_corrections=false` + `files_modified>0` should represent >80% of the filtered corpus (vs. 0% filtering today)
- **Filter precision**: Each predicate independently drops only the sessions it claims to target — `require_issue_outcome` should not drop sessions that closed an issue, `exclude_user_corrections` should not drop sessions with zero corrections
- **Graceful degradation**: Pipeline completes successfully (no crashes, no empty corpus) when `history.db` is missing or empty — verified by test
- **Rejection transparency**: Every dropped example has a `rejected_by` annotation identifying which predicate(s) rejected it

## Implementation Steps

1. **Add a `lookup_session_metadata()` helper** — new function (or inline shell) that takes a session ID and queries `history.db` via `ll-history-context` or direct SQLite, returning a JSON metadata dict: `{"has_corrections": bool, "issue_outcome": str|null, "tool_count": int, "files_modified": int, "loop_outcome": str|null}`. Degrades to empty dict when DB is absent.

2. **Add an `enrich` state before `filter`** in `sft-corpus.yaml` — batch-joins metadata from `history.db` onto each example in the staged `raw.jsonl` by extracting the session ID from the example's source path and calling `lookup_session_metadata()`. Writes enriched examples to a new staged file.

3. **Extend the `filter` state** — add shell predicates for each new context key:
   - `require_issue_outcome`: drop examples where `metadata.issue_outcome != "done"`
   - `exclude_user_corrections`: drop examples where `metadata.has_corrections == true`
   - `min_tool_invocations`: drop examples where `metadata.tool_count < context.min_tool_invocations`
   - `require_file_modifications`: drop examples where `metadata.files_modified == 0`

4. **Add filter rejection tracking** — extend the filter state to emit a rejection-reason annotation per dropped example (e.g., `"rejected_by": "require_issue_outcome"`) so the analytics report (future issue) can break down rejection rates by reason.

5. **Update `sft-corpus.yaml` context block** — add the four new optional keys with defaults that mean "skip this check" (`require_issue_outcome: false`, `exclude_user_corrections: false`, `min_tool_invocations: 0`, `require_file_modifications: false`).

6. **Add tests** in `scripts/tests/test_loops_sft_corpus.py` (created by FEAT-1826):
   - Test graceful degradation when `history.db` is missing
   - Test that each predicate drops the correct examples
   - Test that predicate=false means pass-through

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Register `sft-corpus` in the built-in loop catalog** — add `"sft-corpus"` to the hardcoded `expected` set in `scripts/tests/test_builtin_loops.py:test_expected_loops_exist()` (line 73). This is the primary registration gate; without this entry, `test_expected_loops_exist()` fails, blocking CI.

8. **Document `sft-corpus` in the loop registry** — add a row for `sft-corpus` to the "Data & Testing" table in `scripts/little_loops/loops/README.md` and the built-in loops reference table in `docs/guides/LOOPS_GUIDE.md`. These are FEAT-1826 deliverables that ENH-1941 inherits.

9. **Verify MR-3 artifact isolation** — confirm that the `enrich` state writes intermediate files to `${context.run_dir}/enriched.jsonl` (not shared `.loops/tmp/`). The static validator in `scripts/little_loops/fsm/validation.py:_validate_artifact_isolation()` (line 1256) emits WARNING severity if any hardcoded `.loops/tmp/` paths are detected.

10. **Ensure `sft-corpus` is not misclassified as a meta-loop** — the `_is_meta_loop()` function at `scripts/little_loops/fsm/validation.py` (line 1009) checks action strings against harness artifact patterns. If any action string in `sft-corpus.yaml` contains `skills/`, `agents/`, `commands/`, `hooks/`, or `CLAUDE.md`, the loop will be classified as a meta-loop and MR-1 will fire requiring non-LLM evaluators on every LLM-judged state. Keep action strings data-focused to avoid this.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Critical Implementation Context

**Session-ID recovery is the primary design challenge.** `extract_conversation_turns()` at `user_messages.py:773` returns bare `list[list[tuple[str, str]]]` — role and content only. The JSONL filename IS the session ID (UUID.jsonl), and it's available at line 803 inside the function loop, but it is never propagated to the return value. ENH-1942 proposes adding a `conversation_turns()` function to `history_reader.py` that queries `history.db` directly (inherently carrying session_id), but ENH-1942 is also `open` and this issue's Scope Boundaries explicitly exclude changing `extract_conversation_turns()`'s return type.

**Workaround approach for the `enrich` state**: The `harvest` state calls `ll-messages --sft-format --output raw.jsonl`. If each JSONL line in `raw.jsonl` carries the source filename, the `enrich` state can extract the session ID from that filename. Alternatively, the `harvest` state can be configured to emit session IDs alongside conversation windows. If neither approach works, the `enrich` state may need to call `ll-session path` (at `cli/session.py:188`: `SELECT jsonl_path FROM sessions WHERE session_id = ?`) to reverse-map from content back to session ID — but this is fragile (content matching).

**Decided**: Implement ENH-1942 first so that `history_reader.conversation_turns()` provides session-tagged turn-pairs natively. Then the `enrich` state has a direct `session_id` key without content-matching hacks.

#### Database Schema Support

The `history.db` schema (v10, `session_store.py`) already has all the tables needed for the four predicates:

| Predicate | Table | Query |
|-----------|-------|-------|
| `require_issue_outcome` | `issue_events` | `SELECT session_id FROM issue_events WHERE issue_id = ? AND transition = 'done'` — also supported by the `issue_sessions` VIEW at `session_store.py:254` |
| `exclude_user_corrections` | `user_corrections` | `SELECT COUNT(*) FROM user_corrections WHERE session_id = ?` — `find_user_corrections()` at `history_reader.py:193` returns `[UserCorrection(ts, session_id, content, source), ...]` |
| `min_tool_invocations` | `tool_events` | `SELECT COUNT(*) FROM tool_events WHERE session_id = ?` — no existing `history_reader.py` wrapper; requires direct SQLite or a new function |
| `require_file_modifications` | `file_events` | `SELECT COUNT(*) FROM file_events WHERE session_id = ? AND op IN ('write', 'create')` — `recent_file_events()` at `history_reader.py:227` returns `[FileEvent(ts, session_id, path, op, ...), ...]` |

The `sessions` table (`session_id TEXT PRIMARY KEY, jsonl_path TEXT, started_at TEXT, project_path TEXT`) provides the `session_id → jsonl_path` join key (ENH-1710).

#### Loop Pattern References

- **Filter predicate structure**: Model after `dataset-curation.yaml` `route_quality` state (line 64) — `output_numeric` evaluator with `operator: ge/eq` against `${context.key}`. Example for `min_tool_invocations`:
  ```yaml
  evaluate:
    type: output_numeric
    operator: ge
    target: "${context.min_tool_invocations}"
  ```
- **Rejection annotations**: Model after `dataset-curation.yaml` `reject_item` state (line 98) — append `{path, score, reason, timestamp}` to a rejections log, then `publish` (line 168) reports aggregate stats. For ENH-1941, each dropped example gets `"rejected_by": "<predicate_name>"` appended to a rejections sidecar file.
- **Per-run artifact isolation**: Follow `hitl-compare.yaml` `init` state (line 31) — write intermediate enriched JSONL to `${context.run_dir}/enriched.jsonl`, never to shared `.loops/tmp/` (MR-3 compliance).
- **Graceful degradation**: Replicate the `history_reader.py` `_connect_readonly()` pattern (line 164): attempt to connect, return `None`/empty on failure, catch `sqlite3.Error`, close in finally. The `lookup_session_metadata()` helper must return `{}` (empty dict) when the DB is absent, and the filter predicates must treat missing metadata as pass-through.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/sft-corpus.yaml` — add `enrich` state and extend `filter` state predicates
  > ⚠ **Dependency**: This file does not exist yet — it is the primary deliverable of FEAT-1826 (status: `open`). ENH-1941 cannot be implemented until FEAT-1826 lands `sft-corpus.yaml`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/history_reader.py` — existing read API used by the new `lookup_session_metadata()` helper:
  - `find_user_corrections(topic, *, limit=10, db=DEFAULT_DB_PATH)` → `list[UserCorrection]` — returns `[UserCorrection(ts, session_id, content, source), ...]`; degrades to `[]` on missing/empty DB
  - `sessions_for_issue(issue_id, *, limit=10, db=DEFAULT_DB_PATH)` → `list[SessionRef]` — returns `[SessionRef(issue_id, session_id, jsonl_path, first_message_ts, last_message_ts), ...]`; provides the join key between issue_id and session_id
  - `issue_effort(issue_id, *, db=DEFAULT_DB_PATH)` → `dict | None` — returns `{session_count, cycle_time_days, ...}`; degrades to `None` on missing DB
  - `recent_file_events(path, *, limit=10, db=DEFAULT_DB_PATH)` → `list[FileEvent]` — returns `[FileEvent(ts, session_id, path, op, issue_id, git_sha), ...]`; files modified per session
  - Graceful-degradation entry point: `_connect_readonly(db_path)` → `sqlite3.Connection | None` at `history_reader.py:164`
- `scripts/little_loops/cli/history_context.py` — `main_history_context()` at line 99; CLI alternative for metadata lookup via `ll-history-context` (ENH-1846); also degrades gracefully (exit 0 on no matches/absent DB at line 207)
- `scripts/little_loops/user_messages.py` — `extract_conversation_turns()` at line 773 returns bare `list[list[tuple[str, str]]]` with NO session_id; the JSONL filename (which IS the session ID) is available at line 803 but never propagated; changing this return type is **out of scope** per Scope Boundaries
- `scripts/little_loops/session_store.py` — `_backfill_sessions()` at line 1374 writes session_id → jsonl_path into `sessions` table; `_backfill_messages()` at line 930 writes user messages; `_backfill_tool_events()` at line 883 writes tool invocations; the `issue_sessions` VIEW (schema v5, line 254) joins `issue_events` to `message_events` via overlapping timestamps

### Similar Patterns
- **Graceful-degradation pattern**: Every function in `history_reader.py` follows the same shape — `_connect_readonly()` → if `None` return `[]`, try query, catch `sqlite3.Error` return `[]`, close in finally. The `lookup_session_metadata()` helper must replicate this pattern exactly.
- **Metadata-joining analog**: `examples-miner.yaml` `calibrate` state (line 93) and `merge` state (line 244) perform two-source data joins with metadata enrichment — closest structural analog to an `enrich` state
- **Filter-evaluator pattern**: `dataset-curation.yaml` `route_quality` state (line 64) uses `output_numeric` evaluator with `operator: ge` against `${context.quality_threshold}` — identical pattern to the new predicate comparisons (`output_numeric` / `eq` / `0` for `exclude_user_corrections`, `output_numeric` / `ge` / `${context.min_tool_invocations}` for tool counts)
- **Rejection-tracking pattern**: `dataset-curation.yaml` `reject_item` state (line 98) appends `{path, score, reason, timestamp}` to `${context.output_dir}/rejections.jsonl` and `publish` state (line 168) reports aggregate rejection stats — the exact pattern for `rejected_by` annotations
- **Per-run artifact isolation**: `hitl-compare.yaml` `init` state (line 31) writes to `${context.run_dir}/` — the `enrich` state's intermediate staging file must follow this pattern (per MR-3)

### Tests
- `scripts/tests/test_loops_sft_corpus.py` — add tests for enrichment + filter predicates + degradation (created by FEAT-1826; does not yet exist). Follow pattern from `test_loops_recursive_refine.py` for bash-based loop state testing.
- `scripts/tests/test_history_reader.py` — `TestMissingDatabase` (line 27) and `TestEmptyTables` (line 56) classes set the pattern for "all functions return empty when DB absent/empty" tests; the new `lookup_session_metadata()` tests must follow this pattern. Add a `TestLookupSessionMetadata` class with degradation + per-predicate correctness tests.
- `scripts/tests/test_fsm_evaluators.py` — `TestOutputNumericEvaluator` (line 76) sets the pattern for evaluator testing with `@pytest.mark.parametrize`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `test_expected_loops_exist()` (line 73) maintains a hardcoded `expected` set of ~68 loop names; `"sft-corpus"` must be added (FEAT-1826 dependency, inherited by ENH-1941)
- `scripts/tests/test_fsm_schema.py` — pattern reference for YAML validation test helpers (`make_state`, `make_fsm`)
- `scripts/tests/test_loop_router.py` — pattern reference for `load_and_validate()` structural validation of loop YAML files

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — add `sft-corpus` to the built-in loops reference table (FEAT-1826 dependency, inherited by ENH-1941)
- `scripts/little_loops/loops/README.md` — add `sft-corpus` row to "Data & Testing" table (FEAT-1826 dependency, inherited by ENH-1941)

### Configuration
- `sft-corpus.yaml` context block — four new optional keys with pass-through defaults:
  ```yaml
  require_issue_outcome: false       # default: skip this check
  exclude_user_corrections: false    # default: skip this check
  min_tool_invocations: 0            # default: skip this check
  require_file_modifications: false  # default: skip this check
  ```
  Referenced via `${context.require_issue_outcome}` etc. in shell/prompt actions per `InterpolationContext.resolve()` at `scripts/little_loops/fsm/interpolation.py:38`

## API / Interface

No public API changes. The integration is internal to the `sft-corpus` loop's `enrich` and `filter` states. The `history.db` read path uses the existing `history_reader.py` API or `ll-history-context` CLI — no new read API surface.

## Use Case

A practitioner wants to fine-tune an SLM that's good at implementing code changes. They run:

```bash
ll-loop run sft-corpus
```

With context configured as:
```yaml
require_issue_outcome: true
exclude_user_corrections: true
require_file_modifications: true
min_tool_invocations: 5
```

The resulting corpus contains only conversations where: an issue was closed, the user never corrected the assistant, files were actually modified, and at least 5 tool calls were made. This corpus trains a model that completes tasks, not one that chats about them.

## Scope Boundaries

- **In scope**: New `enrich` state in `sft-corpus.yaml`; four new optional filter predicates backed by `history.db` lookups; graceful degradation when DB is absent; filter rejection-reason annotations
- **Out of scope**: Changes to `history.db` schema or write paths (owned by EPIC-1707); changes to `extract_conversation_turns()` return type; new `ll-history-context` features; analytics/reporting on rejection rates (future issue); making `history.db` a required dependency

## Impact

- **Priority**: P3 — Quality lever for an already-P3 epic; not blocking
- **Effort**: Medium — New `enrich` state + extended `filter` predicates + tests; all dependencies (`history_reader.py`, `ll-history-context`, graceful-degradation pattern) already exist
- **Risk**: Low — Additive to `sft-corpus.yaml` only; all new predicates are opt-in and default to pass-through; degrades gracefully when DB is absent
- **Breaking Change**: No — FEAT-1826 is not yet implemented, so there's no existing behavior to break
- **Depends on**: ENH-1710 (session-ID → JSONL path mapping) for the join key; FEAT-1826 (sft-corpus loop) for the file to modify

## Related

- EPIC-1880 — parent epic (SLM fine-tuning from session logs)
- EPIC-1707 — history.db as agent context layer (provides the read API and degradation pattern)
- ENH-1710 — session-ID to JSONL path mapping (provides the join key)
- FEAT-1826 — sft-corpus FSM loop (the file this issue modifies)
- ENH-1846 — ll-history-context CLI (one possible lookup path)
- ENH-1904 — user_corrections mining from message_events (feeds the `exclude_user_corrections` predicate)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Producer→consumer flow for history.db |
| reference | docs/reference/API.md | history_reader.py read API surface |

## Labels

`enhancement`, `sft`, `history-db`, `corpus-quality`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-04 (updated)_

**Readiness Score**: 82/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- **FEAT-1826 blocker**: `sft-corpus.yaml` doesn't exist — the file this issue modifies is the primary deliverable of an open FEAT-1826. Implementation should either block on FEAT-1826 or absorb its skeleton creation into ENH-1941's scope.
- **ENH-1942 dependency chain**: The "Decided" session-ID approach ("Implement ENH-1942 first") depends on another open issue. The workaround (filename extraction from JSONL lines) is viable if ENH-1942 isn't done first.

### Outcome Risk Factors
- **Missing artifact — blocked pre-condition**: `sft-corpus.yaml` does not exist (FEAT-1826 is open). Implementation cannot begin until this file is created by FEAT-1826 or incorporated into ENH-1941's scope.
- **Low test coverage for primary change site**: `test_loops_sft_corpus.py` is a FEAT-1826 co-deliverable that doesn't exist yet. Implement tests first to avoid shipping untested filter predicates — each predicate needs independent verification.
- **Moderate breadth — 6 change sites across 3 subsystems** (loops YAML, test suite, documentation). The enrich + filter state changes interact through shared context interpolation — regressions in one predicate can affect the others.

## Session Log
- `/ll:decide-issue` - 2026-06-04T16:59:54 - `dc377f5e-54d2-46f2-8a7c-e837139d1888.jsonl`
- `/ll:wire-issue` - 2026-06-04T16:52:29 - `8c16c11d-faf0-49d4-95bc-697d5a33feaa.jsonl`
- `/ll:refine-issue` - 2026-06-04T16:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5af07d20-b493-4c8d-8248-1ab98c6f7d8c.jsonl`
- `/ll:format-issue` - 2026-06-04T16:01:00 - `5329f937-a419-47c6-b537-332549e1fb53.jsonl`
- `/ll:capture-issue` - 2026-06-04T15:57:41Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-06-04T16:52:00Z - `5f67c2cb-a255-43f3-914c-4f40f929f875.jsonl`
- `/ll:confidence-check` - 2026-06-04T18:45:00Z - `7277ed1f-3a31-4950-9357-0a5d28a5e2eb.jsonl`
- `/ll:issue-size-review` - 2026-06-04T18:45:00Z - `ca366434-0e71-4ffe-883b-0f265ec672e1.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-04
- **Reason**: Issue too large for single session (score: 11/11 — Very Large). 10 implementation steps + wiring phase across 3 subsystems with 15+ files.

### Decomposed Into
- ENH-1943: Add lookup_session_metadata() helper for history.db session-quality queries
- ENH-1944: Add enrich state and quality predicates to sft-corpus.yaml filter
