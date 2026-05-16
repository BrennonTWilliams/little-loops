---
id: ENH-1267
priority: P3
parent: ENH-1266
size: Medium
decision_needed: false
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-04-23T03:24:36Z
status: done
---

# ENH-1267: Test Coverage for analyze-loop Step 3b Semantic Synthesis

## Summary

Add automated test coverage for the Step 3b Semantic Synthesis phase in `/ll:analyze-loop`. The core SKILL.md implementation is already complete; this issue adds the fixtures and test file needed to validate the structural conditions each synthesis sub-step relies on.

## Current Behavior

Step 3b Semantic Synthesis is implemented in `skills/analyze-loop/SKILL.md` but has no automated test coverage. Regressions in path reconstruction (3b-2), goal alignment (3b-3), cross-signal grouping (3b-4), or sub-threshold detection (3b-5) would be invisible.

## Expected Behavior

Three YAML fixtures and a `TestAnalyzeLoopSynthesis` test class exercise each structural condition in sub-steps 3b-3 through 3b-5. All new tests pass with `python -m pytest scripts/tests/test_analyze_loop_synthesis.py scripts/tests/test_enh1146_doc_wiring.py -v`.

## Parent Issue

Decomposed from ENH-1266: Add Semantic Synthesis Phase to analyze-loop

## Motivation

Step 3b is live but has no automated tests. Without them, regressions in the synthesis logic (path reconstruction, cross-signal grouping, sub-threshold detection) would be invisible. The pattern is established in `scripts/tests/test_review_loop.py` (`TestReviewLoopSemanticChecks`, line 748).

## Proposed Solution

### 1. Add FSM event sequence fixtures

Create three YAML fixture files in `scripts/tests/fixtures/fsm/` following the structure of `semantic-goal-mismatch.yaml`:

**`analysis-multi-signal.yaml`**
- Adjacent states each with action failure + evaluate failure
- Exercises sub-step 3b-4 (cross-signal adjacency note)

**`analysis-dominant-cycling.yaml`**
- One state accounts for ≥70% of total iterations
- Exercises sub-step 3b-5 (sub-threshold detection)

**`analysis-completed-misaligned.yaml`**
- `terminated_by == "terminal"` with heavy cycling, `description` unrelated to dominant state
- Exercises sub-step 3b-3 (goal alignment check)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**YAML fixture schema** — all fixtures in `scripts/tests/fixtures/fsm/` use exactly four top-level keys (see `semantic-goal-mismatch.yaml:1-22`):
```yaml
name: analysis-dominant-cycling
description: "..."
initial: <state-name>
states:
  <state-name>:
    action: "..."
    action_type: prompt|shell
    on_yes: <state>   # or next: <state> for unconditional
    on_no:  <state>
    on_error: <state>
    terminal: true    # marks terminal state only
    evaluate:         # shell states only
      type: exit_code
```
No `events` key is embedded in fixtures — event sequences are constructed inline in tests as Python dicts.

**Sub-step structural conditions from `skills/analyze-loop/SKILL.md`:**

| Sub-step | Condition tested | Threshold |
|----------|-----------------|-----------|
| 3b-3 goal alignment | `terminated_by == "terminal"` + total iterations > 3× distinct states; description ≥ 5 words unrelated to dominant state (lines 206-214) | ≥50% dominant share |
| 3b-4 cross-signal | Two adjacent states (A→B via `on_yes`/`on_no`/`next`) each with classified signals: action failure in A + evaluate failure in B → output format mismatch candidate (lines 215-224) | adjacency |
| 3b-5 dominant cycling | Dominant state ≥ **70%** of total `state_enter` events AND more than one state visited (lines 225-231) | 70% |
| 3b-5 decision-state dominance | Dominant state name matches `check_*`, `verify_*`, `evaluate_*`, or `wait_*` (note: wider than SR-2's `GATE_STATE_PREFIXES`) | prefix match |

**Inline event dict fields** for `state_enter` events in tests:
```python
{"event": "state_enter", "state": "check_done", "iteration": 1}
```
`loop_complete` event uses: `{"event": "loop_complete", "terminated_by": "terminal", "final_state": "done", "iterations": N}`

### 2. Add test file

Create `scripts/tests/test_analyze_loop_synthesis.py` with class `TestAnalyzeLoopSynthesis` modeled after `TestReviewLoopSemanticChecks` in `test_review_loop.py:748`:

- Use a class-level `_load_fixture()` instance method (not `conftest.load_fixture` — that returns `str`; the class method returns `dict` via `yaml.safe_load`) and inline event sequence dicts (not `.jsonl` files)
- Group tests by sub-step: 3b-2 (path reconstruction), 3b-3 (goal alignment), 3b-4 (cross-signal grouping), 3b-5 (sub-threshold detection)
- Structural condition tests only — no LLM execution needed

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`_load_fixture()` is a class-level method, not from conftest** (`test_review_loop.py:758-762`):
```python
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fsm"

class TestAnalyzeLoopSynthesis:
    def _load_fixture(self, name: str) -> dict:
        path = FIXTURES_DIR / name
        assert path.exists(), f"Fixture not found: {path}"
        with open(path) as f:
            return yaml.safe_load(f)
```
The conftest `load_fixture` at `conftest.py:36` returns raw `str` (via `.read_text()`), not a parsed dict — do not use it here.

**`_happy_path()` helper** (`test_review_loop.py:764-777`) traces `on_yes`/`next` from `initial` to terminal state; copy directly if path-based assertions are needed for 3b-2:
```python
def _happy_path(self, spec: dict) -> list[str]:
    states = spec.get("states", {})
    current = spec.get("initial")
    path: list[str] = []
    seen: set[str] = set()
    while current and current not in seen:
        path.append(current)
        seen.add(current)
        state = states.get(current, {})
        if state.get("terminal"):
            break
        current = state.get("on_yes") or state.get("next")
    return path
```

**Required imports** (inferred from `test_review_loop.py:1-25`):
```python
from __future__ import annotations
from pathlib import Path
import yaml
```

**Assertion patterns to follow** from `TestReviewLoopSemanticChecks`:
- `test_sr1_mismatch_fixture_has_description` (line 781) — fixture field presence
- `test_sr2_incoherent_state_action_is_broad` (line 831) — computed property threshold
- `test_sr3_backwards_transition_fixture_has_on_yes_backward` (line 876) — adjacency via path index
- `test_sr4_goal_gap_fixture_has_uncovered_activity` (line 918) — text coverage across all state text

**Module-level constant** mirroring `test_review_loop.py:25`:
```python
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fsm"
```

### 3. Enhance doc-wiring test

In `scripts/tests/test_enh1146_doc_wiring.py` (around line 38), add an assertion that `skills/analyze-loop/SKILL.md` contains the `"Semantic Synthesis"` or `"Step 3b"` heading, following the existing pattern.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact location**: `TestAnalyzeLoopSkillWiring` class at `test_enh1146_doc_wiring.py:38`. Currently has one method (`test_rate_limit_waiting_present`, lines 39-42). Add a second method in the same class:

```python
class TestAnalyzeLoopSkillWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in ANALYZE_LOOP.read_text(), (
            "skills/analyze-loop/SKILL.md event payload table must include rate_limit_waiting row"
        )

    def test_semantic_synthesis_heading_present(self) -> None:
        assert "Step 3b" in ANALYZE_LOOP.read_text(), (
            "skills/analyze-loop/SKILL.md must contain the 'Step 3b' semantic synthesis heading"
        )
```

The `ANALYZE_LOOP` path constant is already defined at `test_enh1146_doc_wiring.py:18`:
```python
ANALYZE_LOOP = PROJECT_ROOT / "skills" / "analyze-loop" / "SKILL.md"
```
`"Step 3b"` appears at `skills/analyze-loop/SKILL.md:187` as `## Step 3b: Semantic Synthesis` — the assertion will pass immediately.

## Acceptance Criteria

- [ ] Three YAML fixtures in `scripts/tests/fixtures/fsm/` covering the three synthesis scenarios
- [ ] `scripts/tests/test_analyze_loop_synthesis.py` with `TestAnalyzeLoopSynthesis` class, tests grouped by sub-step
- [ ] `test_enh1146_doc_wiring.py` assertion for `"Step 3b"` or `"Semantic Synthesis"` heading in SKILL.md
- [ ] All new tests pass: `python -m pytest scripts/tests/test_analyze_loop_synthesis.py scripts/tests/test_enh1146_doc_wiring.py -v`

## Integration Map

### Files to Create
- `scripts/tests/fixtures/fsm/analysis-multi-signal.yaml`
- `scripts/tests/fixtures/fsm/analysis-dominant-cycling.yaml`
- `scripts/tests/fixtures/fsm/analysis-completed-misaligned.yaml`
- `scripts/tests/test_analyze_loop_synthesis.py`

### Files to Modify
- `scripts/tests/test_enh1146_doc_wiring.py:38-42` — add `test_semantic_synthesis_heading_present` to `TestAnalyzeLoopSkillWiring` class

### Similar Patterns
- `scripts/tests/test_review_loop.py:748-965` — `TestReviewLoopSemanticChecks`; primary test pattern to follow
- `scripts/tests/test_review_loop.py:758-762` — `_load_fixture()` instance method (dict-returning, not conftest)
- `scripts/tests/test_review_loop.py:764-777` — `_happy_path()` helper for path tracing
- `scripts/tests/fixtures/fsm/semantic-goal-mismatch.yaml:1-23` — fixture YAML schema to follow
- `scripts/tests/fixtures/fsm/semantic-valid-aligned.yaml:1-20` — control fixture pattern (aligned case)

### Reference
- `skills/analyze-loop/SKILL.md:186` — `## Step 3b: Semantic Synthesis` heading
- `skills/analyze-loop/SKILL.md:196-231` — sub-steps 3b-2 through 3b-5 with structural conditions
- `scripts/tests/conftest.py:36` — `load_fixture()` returns `str` (NOT the fixture loader to use here)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md:115` — hardcoded FSM fixture count `(8 files)` is already stale (currently 14 fixtures); adding the 3 new `analysis-*.yaml` fixtures brings the total to 17 — update this count during implementation

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `docs/development/TESTING.md:115` — change `(8 files)` to `(17 files)` after the three new `analysis-*.yaml` fixtures are added (note: `ll-verify-docs` does not track this count automatically)

## Scope Boundaries

- No changes to `skills/analyze-loop/SKILL.md` synthesis logic
- No changes to any Python runtime code
- Fixture authoring and test file creation only; no new CLI commands or agent changes
- The `docs/development/TESTING.md` fixture count update is the only documentation change in scope

## Impact

- **Priority**: P3
- **Effort**: Small-Medium — fixture authoring + test file setup; no Python logic changes
- **Risk**: Low — tests only; no runtime behavior changes
- **Breaking Change**: No

## Labels

`enhancement`, `testing`, `analyze-loop`

## Status

**Open** | Created: 2026-04-22 | Priority: P3

## Resolution

Implemented by `/ll:manage-issue` on 2026-04-23.

**Changes made:**
- Created `scripts/tests/fixtures/fsm/analysis-multi-signal.yaml` — prompt→shell adjacency fixture for 3b-4
- Created `scripts/tests/fixtures/fsm/analysis-dominant-cycling.yaml` — check_build cycling fixture for 3b-5
- Created `scripts/tests/fixtures/fsm/analysis-completed-misaligned.yaml` — misaligned description fixture for 3b-3
- Created `scripts/tests/test_analyze_loop_synthesis.py` with `TestAnalyzeLoopSynthesis` (18 tests across 3b-2 through 3b-5)
- Added `test_semantic_synthesis_heading_present` to `TestAnalyzeLoopSkillWiring` in `test_enh1146_doc_wiring.py`
- Updated `docs/development/TESTING.md:115` fixture count from `(8 files)` to `(17 files)`

All 26 tests passed: `python -m pytest scripts/tests/test_analyze_loop_synthesis.py scripts/tests/test_enh1146_doc_wiring.py -v`

## Session Log
- `/ll:manage-issue` - 2026-04-23T03:24:36Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3c75e0d-fff1-4f6a-a91a-7188868319dd.jsonl`
- `/ll:ready-issue` - 2026-04-23T03:18:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3c75e0d-fff1-4f6a-a91a-7188868319dd.jsonl`
- `/ll:wire-issue` - 2026-04-23T03:11:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/100383fa-ae6f-4332-a8a7-f66b0135eed9.jsonl`
- `/ll:refine-issue` - 2026-04-23T03:07:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8e7ed822-ee8c-47c4-89ee-dec801417887.jsonl`
- `/ll:issue-size-review` - 2026-04-22T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac265e54-5386-49fe-bf5b-6e6f9305772d.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c4436af-605a-4242-89e1-38fa218f74ee.jsonl`
