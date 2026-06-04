---
id: ENH-1944
title: Add enrich state and quality predicates to sft-corpus.yaml filter
type: ENH
priority: P3
status: open
parent: ENH-1941
relates_to:
- EPIC-1880
- EPIC-1707
- ENH-1710
- ENH-1943
- FEAT-1826
labels:
- enhancement
- sft
- history-db
- corpus-quality
- loops
---

# ENH-1944: Add enrich state and quality predicates to sft-corpus.yaml filter

## Summary

Add an `enrich` state to `sft-corpus.yaml` that batch-joins `history.db` session-quality metadata onto staged examples, and extend the `filter` state with four optional quality predicates backed by that metadata. Includes wiring (loop registration, documentation, MR-3 compliance, meta-loop classification avoidance) and tests.

## Parent Issue

Decomposed from ENH-1941: Integrate history.db session-quality signals into sft-corpus filtering

## Prerequisites

- **FEAT-1826**: `sft-corpus.yaml` must exist (this file is the primary deliverable of FEAT-1826). If FEAT-1826 is still `open`, either block on it or absorb its skeleton creation into this issue's scope.
- **ENH-1943**: `lookup_session_metadata()` function must be available in `history_reader.py`.

## Implementation Steps

### Enrich State

1. **Add `enrich` state before `filter` in `sft-corpus.yaml`** — batch-joins metadata from `history.db` onto each example in the staged `raw.jsonl`:
   - Extract session ID from each JSONL line's source filename (the JSONL filename IS the session ID — UUID.jsonl)
   - Call `lookup_session_metadata(session_id)` (from ENH-1943)
   - Write enriched examples to `${context.run_dir}/enriched.jsonl` (MR-3 compliance: never to shared `.loops/tmp/`)
   - Model structural pattern after `examples-miner.yaml` `calibrate` state (line 93) and `merge` state (line 244)

### Filter State Extension

2. **Extend the `filter` state** with four new optional predicates. Each uses an `output_numeric` evaluator (pattern from `dataset-curation.yaml` `route_quality` state, line 64):

   | Predicate | Evaluator | Target | Drops when |
   |-----------|-----------|--------|------------|
   | `require_issue_outcome` | `output_numeric` / `eq` | `1` | `metadata.issue_outcome != "done"` |
   | `exclude_user_corrections` | `output_numeric` / `eq` | `0` | `metadata.has_corrections == true` |
   | `min_tool_invocations` | `output_numeric` / `ge` | `${context.min_tool_invocations}` | `metadata.tool_count < context.min_tool_invocations` |
   | `require_file_modifications` | `output_numeric` / `ge` | `1` | `metadata.files_modified == 0` |

3. **Add filter rejection tracking** — extend the filter state to emit a `rejected_by` annotation per dropped example (pattern from `dataset-curation.yaml` `reject_item` state, line 98):
   - Append `{path, score, reason, timestamp}` to `${context.output_dir}/rejections.jsonl`
   - `reason` field = the predicate name that rejected (e.g., `"require_issue_outcome"`)
   - Publish aggregate rejection stats (pattern from `dataset-curation.yaml` `publish` state, line 168)

### Context Block

4. **Update `sft-corpus.yaml` context block** — add four new optional keys with pass-through defaults:
   ```yaml
   require_issue_outcome: false       # default: skip this check
   exclude_user_corrections: false    # default: skip this check
   min_tool_invocations: 0            # default: skip this check
   require_file_modifications: false  # default: skip this check
   ```
   Referenced via `${context.require_issue_outcome}` etc. per `InterpolationContext.resolve()` at `scripts/little_loops/fsm/interpolation.py:38`.

### Wiring (TDD Mode — wiring stays with implementation)

5. **Register `sft-corpus` in the built-in loop catalog** — add `"sft-corpus"` to the hardcoded `expected` set in `scripts/tests/test_builtin_loops.py:test_expected_loops_exist()` (line 73). This is the primary registration gate; without this entry, CI fails.

6. **Document `sft-corpus` in the loop registry** — add rows to:
   - `scripts/little_loops/loops/README.md` — "Data & Testing" table
   - `docs/guides/LOOPS_GUIDE.md` — built-in loops reference table

7. **Verify MR-3 artifact isolation** — ensure the `enrich` state writes intermediate files to `${context.run_dir}/enriched.jsonl` (not shared `.loops/tmp/`). The static validator at `scripts/little_loops/fsm/validation.py:_validate_artifact_isolation()` (line 1256) emits WARNING severity if hardcoded `.loops/tmp/` paths are detected.

8. **Ensure `sft-corpus` is not misclassified as a meta-loop** — keep all action strings in `sft-corpus.yaml` data-focused. The `_is_meta_loop()` function at `scripts/little_loops/fsm/validation.py` (line 1009) checks action strings against harness artifact patterns (`skills/`, `agents/`, `commands/`, `hooks/`, `CLAUDE.md`). Do not reference these patterns in action strings.

### Tests

9. **Add tests** in `scripts/tests/test_loops_sft_corpus.py` (created by FEAT-1826; if it doesn't exist yet, create it):
   - Graceful degradation when `history.db` is missing — pipeline completes, no crashes, no empty corpus
   - Each predicate drops only the examples it claims to target (filter precision):
     - `require_issue_outcome` drops sessions where no issue was closed
     - `exclude_user_corrections` drops sessions with user corrections
     - `min_tool_invocations` drops sessions with too few tool calls
     - `require_file_modifications` drops sessions with zero file modifications
   - Predicate=false means pass-through (opt-in behavior)
   - Rejection annotations are correct (each dropped example has a `rejected_by` field with the right predicate name)
   - Follow bash-based loop state testing pattern from `test_loops_recursive_refine.py`

## Scope Boundaries

- **In scope**: `enrich` state; four filter predicates; rejection tracking; context block; wiring (registration, docs, MR-3, meta-loop avoidance); tests
- **Out of scope**: `lookup_session_metadata()` implementation (ENH-1943); changes to `history.db` schema or write paths (EPIC-1707); changes to `extract_conversation_turns()` return type; analytics/reporting on rejection rates (future issue)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/sft-corpus.yaml` — add `enrich` state, extend `filter` predicates, add context keys
  > ⚠ **Dependency**: FEAT-1826 must create this file first (or this issue absorbs skeleton creation)
- `scripts/tests/test_loops_sft_corpus.py` — add enrichment + filter predicate + degradation tests
- `scripts/tests/test_builtin_loops.py` — add `"sft-corpus"` to `expected` set (line 73)
- `scripts/little_loops/loops/README.md` — add `sft-corpus` row to "Data & Testing" table
- `docs/guides/LOOPS_GUIDE.md` — add `sft-corpus` to built-in loops reference table

### Similar Patterns
- **Metadata join**: `examples-miner.yaml` `calibrate` (line 93) and `merge` (line 244)
- **Filter evaluator**: `dataset-curation.yaml` `route_quality` (line 64) — `output_numeric` with `operator: ge`
- **Rejection tracking**: `dataset-curation.yaml` `reject_item` (line 98) — append to rejections sidecar
- **Per-run isolation**: `hitl-compare.yaml` `init` (line 31) — `${context.run_dir}/` pattern
- **Graceful degradation**: `history_reader.py` `_connect_readonly()` (line 164) — try/catch/finally

## Impact

- **Priority**: P3 — inherited from parent ENH-1941
- **Effort**: Medium — New YAML state + extended predicates + wiring + tests across 5 files
- **Risk**: Low — All predicates are opt-in (default pass-through); degrades gracefully when DB absent
- **Breaking Change**: No — FEAT-1826 is not yet implemented, so no existing behavior to break
- **Depends on**: ENH-1943 (`lookup_session_metadata()`), FEAT-1826 (`sft-corpus.yaml` skeleton), ENH-1710 (session-ID mapping)

## Session Log
- `/ll:issue-size-review` - 2026-06-04T18:45:00Z - `ca366434-0e71-4ffe-883b-0f265ec672e1.jsonl`
