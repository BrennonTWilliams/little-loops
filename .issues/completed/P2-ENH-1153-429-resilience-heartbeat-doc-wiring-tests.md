---
id: ENH-1153
type: ENH
priority: P2
status: completed
discovered_date: 2026-04-17
parent: ENH-1151
related: [ENH-1144, ENH-1150, ENH-1152]
size: Small
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1153: 429 Resilience — Heartbeat Doc-Wiring Tests

## Summary

Write `scripts/tests/test_enh1146_doc_wiring.py` to assert all `rate_limit_waiting` heartbeat doc content is present across reference files, then run all verification commands.

## Parent Issue

Decomposed from ENH-1151: 429 Resilience — Heartbeat Docs (Guide, Skill, Changelog, Tests).

## Dependency Note

Run this issue **after** ENH-1152 completes (doc edits). The test file asserts strings written by ENH-1150 and ENH-1152.

## Current Behavior

No test file exists that asserts the `rate_limit_waiting` heartbeat doc content is wired into the reference docs, skill, guide, and changelog. Doc drift in any of the 7 target strings (across `EVENT-SCHEMA.md`, `OUTPUT_STYLING.md`, `analyze-loop/SKILL.md`, `API.md`, `CLI.md`, `COMMANDS.md`) would silently regress without test coverage.

## Current Pain Point

ENH-1150 and ENH-1152 landed doc edits for the `rate_limit_waiting` heartbeat, but without a regression test those strings can be removed or renamed later with no signal. The sibling feature (ENH-1138 circuit breaker) already has `test_enh1138_doc_wiring.py` locking its doc content — the `rate_limit_waiting` heartbeat needs the equivalent safety net.

## Impact

- **Scope**: Test-only — adds one new file (`scripts/tests/test_enh1146_doc_wiring.py`), no runtime changes
- **Risk**: Low. Pure assertion tests over existing doc content; all 7 target strings have been verified present at validation time
- **Benefit**: Locks heartbeat doc wiring against silent regressions; matches the coverage pattern already used for ENH-1138

## Scope Boundaries

**In scope**:
- Create `scripts/tests/test_enh1146_doc_wiring.py` with the 7 assertions specified in the skeleton
- Run the overlapping-doc regression tests (`test_enh1138_doc_wiring.py`, `test_circuit_breaker_doc_wiring.py`, `test_create_extension_wiring.py`)
- Run `ll-verify-docs` and `ll-check-links`

**Out of scope**:
- Modifying doc content (owned by ENH-1150/ENH-1152, already completed)
- Fixing `test_generate_schemas.py` 21→22 count failure (owned by ENH-1147/ENH-1144)
- Core `rate_limit_waiting` event emission (owned by ENH-1144)

## Labels

testing, documentation, rate-limits, regression-safety

## Expected Behavior

### `scripts/tests/test_enh1146_doc_wiring.py` (new file)

Follow the pattern in `scripts/tests/test_enh1138_doc_wiring.py` (read real files, assert strings present). Cover:

- `rate_limit_waiting` present in `docs/reference/EVENT-SCHEMA.md`
- `rate_limit_waiting` present in `docs/reference/OUTPUT_STYLING.md`
- `rate_limit_waiting` present in `skills/analyze-loop/SKILL.md`
- `rate_limit_max_wait_seconds` present in `docs/reference/API.md`
- `rate_limit_long_wait_ladder` present in `docs/reference/API.md`
- `22 \`LLEvent\` types` present in `docs/reference/CLI.md`
- `rate_limit_waiting` present in `docs/reference/COMMANDS.md`

### Test Skeleton (fully specified — copy and run)

```python
from __future__ import annotations
from pathlib import Path

PROJECT_ROOT   = Path(__file__).parent.parent.parent
EVENT_SCHEMA   = PROJECT_ROOT / "docs" / "reference" / "EVENT-SCHEMA.md"
OUTPUT_STYLING = PROJECT_ROOT / "docs" / "reference" / "OUTPUT_STYLING.md"
ANALYZE_LOOP   = PROJECT_ROOT / "skills" / "analyze-loop" / "SKILL.md"
API_REFERENCE  = PROJECT_ROOT / "docs" / "reference" / "API.md"
CLI_REFERENCE  = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
COMMANDS       = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"

class TestEventSchemaWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in EVENT_SCHEMA.read_text(), \
            "docs/reference/EVENT-SCHEMA.md must document rate_limit_waiting heartbeat event"

class TestOutputStylingWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in OUTPUT_STYLING.read_text(), \
            "docs/reference/OUTPUT_STYLING.md must document rate_limit_waiting styling"

class TestAnalyzeLoopSkillWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in ANALYZE_LOOP.read_text(), \
            "skills/analyze-loop/SKILL.md event payload table must include rate_limit_waiting row"

class TestApiReferenceWiring:
    def test_rate_limit_max_wait_seconds_present(self) -> None:
        assert "rate_limit_max_wait_seconds" in API_REFERENCE.read_text(), \
            "docs/reference/API.md must reference rate_limit_max_wait_seconds"
    def test_rate_limit_long_wait_ladder_present(self) -> None:
        assert "rate_limit_long_wait_ladder" in API_REFERENCE.read_text(), \
            "docs/reference/API.md must reference rate_limit_long_wait_ladder"

class TestCliReferenceWiring:
    def test_llevent_type_count_present(self) -> None:
        assert "22 `LLEvent` types" in CLI_REFERENCE.read_text(), \
            "docs/reference/CLI.md must state '22 `LLEvent` types' (updated count after rate_limit_waiting)"

class TestCommandsWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in COMMANDS.read_text(), \
            "docs/reference/COMMANDS.md must document rate_limit_waiting in analyze-loop heuristics"
```

## Integration Map

### New Files to Create

- `scripts/tests/test_enh1146_doc_wiring.py`

### Tests to Run

- `python -m pytest scripts/tests/test_enh1146_doc_wiring.py` — new test (after ENH-1152 completes)
- `python -m pytest scripts/tests/test_enh1138_doc_wiring.py` — regression check
- `ll-verify-docs` — event count check
- `ll-check-links` — catch broken internal links

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_circuit_breaker_doc_wiring.py` — existing coverage of `docs/reference/API.md`; regression check that ENH-1150 doc edits did not break circuit-breaker assertions [Agent 1 finding]
- `scripts/tests/test_create_extension_wiring.py` — existing coverage of `docs/reference/CLI.md`, `API.md`, `COMMANDS.md`; regression check for all three overlapping docs [Agent 1 finding]

### Pre-existing Test Suite Note

_Wiring pass added by `/ll:wire-issue`:_
`scripts/tests/test_generate_schemas.py` hardcodes `== 21` LLEvent type count at lines 17–19, 52–56, and 62–63, and its expected event-type set does not include `rate_limit_waiting`. Running the full suite (`python -m pytest scripts/tests/`) will expose these pre-existing failures — they are owned by ENH-1147 and ENH-1144, not ENH-1153. The ENH-1153 acceptance criteria only requires `test_enh1146_doc_wiring.py` and `test_enh1138_doc_wiring.py` to pass.

## Implementation Steps

1. Write `scripts/tests/test_enh1146_doc_wiring.py` using the skeleton above
2. Run `python -m pytest scripts/tests/test_enh1146_doc_wiring.py scripts/tests/test_enh1138_doc_wiring.py`
3. Run `ll-verify-docs && ll-check-links`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Run overlapping-doc regression checks: `python -m pytest scripts/tests/test_circuit_breaker_doc_wiring.py scripts/tests/test_create_extension_wiring.py`
5. If the full suite is run, expect pre-existing failures in `scripts/tests/test_generate_schemas.py` (21 vs. 22 count) — do not fix; those belong to ENH-1147/ENH-1144

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Pattern reference `scripts/tests/test_enh1138_doc_wiring.py` exists and uses the exact pattern the skeleton follows: `PROJECT_ROOT = Path(__file__).parent.parent.parent`, plain `read_text()` calls, class-per-file grouping with descriptive assertion messages.
- All 7 target strings are already present in the referenced docs at refinement time — ENH-1150's reference-file edits and ENH-1152's guide/skill/changelog edits appear to have landed. Running the test immediately after writing should pass without needing ENH-1152 to strictly "complete" first. The Dependency Note still holds as a safety guard in case docs change before this lands.
- Test file naming in this repo uses lowercase ENH IDs (e.g., `test_enh1138_doc_wiring.py`); the specified filename `test_enh1146_doc_wiring.py` follows that convention. Note the mismatch between this issue's ID (ENH-1153) and the test filename (`test_enh1146_...`) — `1146` tracks the underlying feature (the `rate_limit_waiting` heartbeat event), matching how `test_enh1138_doc_wiring.py` tracks ENH-1138's circuit-breaker feature.

## Acceptance Criteria

- `scripts/tests/test_enh1146_doc_wiring.py` written and all 7 assertions pass
- `python -m pytest scripts/tests/test_enh1138_doc_wiring.py` passes (regression)
- `ll-verify-docs` passes

## Session Log
- `/ll:ready-issue` - 2026-04-17T09:52:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c62ada8-41f1-4f97-abf4-d8b7c8eccd2f.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81f09afb-2957-4d8f-9b1d-7d71616fd8c9.jsonl`
- `/ll:wire-issue` - 2026-04-17T09:47:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a5506112-582b-48a0-9359-caf98676c901.jsonl`
- `/ll:refine-issue` - 2026-04-17T09:42:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5a890d69-0a46-495e-9cd7-95d024356218.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee709210-6491-4684-b5fd-fd33f555658f.jsonl`
- `/ll:manage-issue` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/85180e01-f526-44cc-a98b-a677ac7ffc9b.jsonl`

## Resolution

Created `scripts/tests/test_enh1146_doc_wiring.py` with 7 assertions covering the `rate_limit_waiting` heartbeat doc content across `EVENT-SCHEMA.md`, `OUTPUT_STYLING.md`, `analyze-loop/SKILL.md`, `API.md` (two strings), `CLI.md` (22 LLEvent types), and `COMMANDS.md`. All assertions pass.

**Verification**:
- `pytest test_enh1146_doc_wiring.py test_enh1138_doc_wiring.py test_circuit_breaker_doc_wiring.py test_create_extension_wiring.py` → 45 passed
- `ruff check` / `ruff format --check` → clean
- `ll-verify-docs` → all 9 counts match
- `ll-check-links` → 3 broken links, all pre-existing and unrelated (excalidraw README, FEAT-918)

---

## Status
- [x] Completed 2026-04-17
