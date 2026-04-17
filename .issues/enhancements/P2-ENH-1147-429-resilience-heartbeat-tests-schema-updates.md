---
id: ENH-1147
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1145
related: [ENH-1144, ENH-1145, ENH-1148, ENH-1149]
size: Medium
confidence_score: 80
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1147: 429 Resilience — Heartbeat Tests: Schema Updates

## Summary

Update `test_generate_schemas.py` to account for the new `rate_limit_waiting` event added in ENH-1144: bump all count assertions from 21→22, rename test functions and update docstrings, and add the new event to the expected event-type set.

## Parent Issue

Decomposed from ENH-1145: 429 Resilience — Heartbeat Tests

## Depends On

- ENH-1144 — `rate_limit_waiting` must be registered in the schema catalog before count assertions can pass

## Expected Behavior

### File: `scripts/tests/test_generate_schemas.py`

**Count assertions** — bump all `== 21` to `== 22` at:
- Line 19
- Line 56
- Line 63
- Line 173

**Test names and docstrings** — update for consistency:
- `:17` — `def test_all_21_event_types_defined` → `test_all_22_event_types_defined`
- `:18` — docstring `"""All 21 LLEvent types must be defined."""` → `"""All 22 LLEvent types must be defined."""`
- `:22` — docstring `"""Each of the 21 known event types must appear in catalog."""` → `"22 known"`
- `:52` — `def test_creates_21_files` → `test_creates_22_files`
- `:53` — docstring `"""Generates exactly 21 schema files."""` → `"22"`
- `:168` — docstring `"""CLI generates 21 schema files in the specified output directory."""` → `"22"`

**Expected event-type set** — in `test_all_event_types_in_catalog` at lines 32-33:
- Add `"rate_limit_waiting"` to the expected set alongside `"rate_limit_exhausted"` / `"rate_limit_storm"`

## Integration Map

### Files to Modify
- `scripts/tests/test_generate_schemas.py` — count assertions, test names, docstrings, expected event-type set

### Upstream Source of Truth (Read-Only for This Issue)
- `scripts/little_loops/generate_schemas.py:82-320` — `SCHEMA_DEFINITIONS` dict (currently 21 keys). ENH-1144 adds the `rate_limit_waiting` entry here using the `_schema()` helper (precedent: `rate_limit_storm` entry near line 181). Test assertions in this issue validate against `SCHEMA_DEFINITIONS`, so ENH-1144 must land first.
- `scripts/little_loops/generate_schemas.py:1` and `:329` — module/function docstrings also say "21 LLEvent types"; those updates belong to ENH-1144, not this issue.

### Test Import Surface
- `test_generate_schemas.py:11` imports `SCHEMA_DEFINITIONS` and `generate_schemas` from `little_loops.generate_schemas`. No new imports needed — only data assertions change.

### Sibling Issues (Coordination)
- ENH-1148 (`test_fsm_executor.py`) — asserts on `rate_limit_exhausted` / `rate_limit_storm` via filter-by-event-key pattern (e.g., `:4408`, `:4606`). Separate scope; do not touch here.
- ENH-1149 (`test_ll_loop_display.py`) — display-edge spotchecks (e.g., `:2408`). Separate scope.

### Codebase Research Findings

_Added by `/ll:refine-issue` — claims in "Expected Behavior" were verified against the current file:_

- All four `== 21` assertion lines confirmed: 19, 56, 63, 173.
- Test function names and docstring line numbers confirmed: `test_all_21_event_types_defined` at `:17` (docstring `:18`, `:22`), `test_creates_21_files` at `:52` (docstring `:53`, `:168`).
- Expected event-type set actually spans `:23–45` (the issue cited "32-33" — those are the current lines of `rate_limit_exhausted` and `rate_limit_storm`; the new `rate_limit_waiting` should slot adjacent to them, preserving existing ordering).
- `rate_limit_waiting` currently absent from both the test file and `SCHEMA_DEFINITIONS`.

## Implementation Steps

1. Open `test_generate_schemas.py`
2. Rename `test_all_21_event_types_defined` → `test_all_22_event_types_defined`; update docstrings
3. Rename `test_creates_21_files` → `test_creates_22_files`; update docstrings at `:53` and `:168`
4. Replace all 4 `== 21` count assertions with `== 22` (lines 19, 56, 63, 173)
5. Add `"rate_limit_waiting"` to the expected event-type set near lines 32-33
6. Run: `python -m pytest scripts/tests/test_generate_schemas.py -v`

## Acceptance Criteria

- All `== 22` count assertions pass
- `test_all_22_event_types_defined` and `test_creates_22_files` exist with correct docstrings
- `"rate_limit_waiting"` present in expected event-type set assertion
- Full `test_generate_schemas.py` test suite passes

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-17_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 100/100 → HIGH CONFIDENCE

### Concerns
- **ENH-1144 must land first.** `rate_limit_waiting` is absent from `SCHEMA_DEFINITIONS` in `generate_schemas.py`. If ENH-1147 is implemented before ENH-1144, all four `== 22` assertions will fail and `test_expected_event_types_present` will fail too (the key won't be in the catalog). The code changes themselves are valid — ordering is the only risk.

## Session Log
- `/ll:refine-issue` - 2026-04-17T08:12:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f31b64d3-b4f0-4639-b22c-9b2909d1dd61.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b94d8ebc-87c0-4120-8a97-2c53bebf4e84.jsonl`
- `/ll:confidence-check` - 2026-04-17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ef29820-11df-40a0-9c67-a9335ee05d61.jsonl`
- `/ll:wire-issue` - 2026-04-17T08:10:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdc90935-b56b-4a93-88c9-c812afdc458b.jsonl`
- `/ll:refine-issue` - 2026-04-17T08:05:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0abf7aa-5b3b-43f4-9f06-7130ff136651.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/714a7073-85c4-4a11-87ff-d55b6cd3eeba.jsonl`

---

## Status
- [ ] Open
