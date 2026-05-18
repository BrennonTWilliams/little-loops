---
id: BUG-1608
type: BUG
priority: P3
title: Add test coverage for failure terminal diagnostic action requirement
status: done
completed_at: 2026-05-18T10:02:08Z
parent: BUG-1603
size: Medium
decision_needed: false
confidence_score: 88
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1608: Add test coverage for failure terminal diagnostic action requirement

## Summary

Add tests that assert all built-in loop YAML files have a pre-terminal `diagnose` state before any failure terminal, and validate the new `validate_failure_terminal_action()` check in `validation.py` (if BUG-1607 adds it). Also update per-loop test assertions to confirm the `diagnose` state exists after BUG-1606 lands.

## Current Behavior

No tests assert that built-in loop YAML files have a pre-terminal `diagnose` state before failure terminals. Running `pytest scripts/tests/test_builtin_loops.py -k "failure_terminal"` or `pytest scripts/tests/test_fsm_validation.py -k "FailureTerminalAction"` finds zero matching tests. Per-loop test classes (`TestSprintBuildAndValidateLoop`, `TestHitlCompareLoop`, `TestSvgTextgradLoop`, `TestHtmlAnythingLoop`) lack companion `test_diagnose_routes_to_failed` / `test_diagnose_is_not_terminal` assertions.

## Expected Behavior

- `TestBuiltinLoopFiles` contains `test_all_failure_terminals_have_diagnostic_action` asserting all fixed loops have a pre-terminal diagnose state
- `TestSprintBuildAndValidateLoop` and `TestHitlCompareLoop` (plus `TestSvgTextgradLoop` and `TestHtmlAnythingLoop` as needed) have companion `test_diagnose_routes_to_failed` and `test_diagnose_is_not_terminal` methods
- `TestFailureTerminalActionValidation` covers `validate_failure_terminal_action()` once BUG-1607 lands
- All 12 fixed loops pass the global regression test; no regressions in existing executor or schema tests

## Steps to Reproduce

1. Run `python -m pytest scripts/tests/test_builtin_loops.py -k "failure_terminal"` — zero tests collected
2. Run `python -m pytest scripts/tests/test_fsm_validation.py -k "FailureTerminalAction"` — zero tests collected
3. Observe: no assertions guard the pre-terminal diagnostic requirement added by BUG-1606

## Impact

- **Priority**: P3 — test coverage gap; no user-facing regression but loops could silently lose `diagnose` states in future changes
- **Effort**: Medium — multiple test classes across two test files; conditional on BUG-1606 and BUG-1607
- **Risk**: Low — adding new tests only, no production code changes
- **Breaking Change**: No

## Parent Issue

Decomposed from BUG-1603: failure terminal states in built-in loops have no diagnostic action — silent failure in ll-loop history

## Dependencies

- BUG-1606 must land first (YAML fixes must exist before per-loop assertions can pass)
- BUG-1607 should land first if `TestFailureTerminalActionValidation` is to be written (requires `validate_failure_terminal_action()` in validation.py)

## Integration Map

### Files to Modify
- `scripts/tests/test_builtin_loops.py` — Add `test_all_failure_terminals_have_diagnostic_action` to `TestBuiltinLoopFiles` (line 18); add companion `diagnose` assertions to non-compliant per-loop test classes (`TestSprintBuildAndValidateLoop`, `TestHitlCompareLoop`)
- `scripts/tests/test_fsm_validation.py` — Add `TestFailureTerminalActionValidation` class after `TestDescriptionFieldValidation` (line 81); conditional on BUG-1607

### Files to Review Only (No Modifications Expected)
- `scripts/tests/test_fsm_executor.py` — Inline `failed: terminal: true` fixtures at lines ~3830–3834 and ~3856–3859 are run through `FSMExecutor` directly, NOT through `validate_fsm()`; no changes needed
- `scripts/tests/test_fsm_schema.py` — `test_terminal_only_state_valid()` (line 951) filters by `ValidationSeverity.ERROR` and uses state named `"end"` (not `"failed"`/`"error"`/`"aborted"`); will pass unchanged after BUG-1607

### Similar Patterns
- `scripts/tests/test_fsm_validation.py:81` — `TestDescriptionFieldValidation` — exact structural model for `TestFailureTerminalActionValidation` (3 methods: missing/present/empty)
- `scripts/tests/test_builtin_loops.py:3242` — `TestRlCodingAgentLoop` — model for per-loop `test_diagnose_routes_to_failed`, `test_diagnose_is_not_terminal` assertions

### Reference YAMLs
- `scripts/little_loops/loops/general-task.yaml` — canonical `diagnose → failed` two-state pattern
- `scripts/little_loops/loops/rl-coding-agent.yaml` — convergence evaluator with `route: error: diagnose` pattern

### Validation Module
- `scripts/little_loops/fsm/validation.py:635` — `validate_fsm()` function
- `scripts/little_loops/fsm/validation.py:32` — `ValidationSeverity` enum
- `scripts/little_loops/fsm/validation.py:40` — `ValidationError` dataclass

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestBuiltinLoopResolution.test_builtin_fallback` (line 146) — calls `main_loop(["ll-loop", "validate", "fix-quality-and-tests"])` end-to-end; asserts exit code `== 0`; must remain 0 after BUG-1607 (warnings must not change exit behavior) [Agent 1 finding]
- `scripts/tests/test_review_loop.py:TestReviewLoopChecks` — 8 direct `validate_fsm()` calls, all filter `ValidationSeverity.ERROR`; safe from new WARNINGs [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `validate_fsm` "Checks performed" bullet list (~lines 4456–4463); new diagnostic-predecessor check should be documented here — BUG-1607's responsibility, but cross-issue awareness needed [Agent 2 finding]
- `skills/review-loop/reference.md` — V-series check table (V-1 through V-17); if BUG-1607 assigns a V-number to the new warning, extend this table [Agent 2 finding]
- `skills/review-loop/SKILL.md` — parses `ll-loop validate` text output; new WARNING text will appear in output; verify skill logic handles unexpected warning lines gracefully [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestSvgTextgradLoop` — wiring research found only `test_score_on_error_routes_to_failed` (line ~2779); `test_diagnose_routes_to_failed` and `test_diagnose_is_not_terminal` are absent (refine-issue claim "already has test_diagnose_* assertions" appears incorrect — verify before skipping) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:TestHtmlAnythingLoop` — wiring research found no `test_diagnose_*` methods despite `"diagnose"` in required_states; both methods are absent (refine-issue claim "no additions needed" appears incorrect — verify before skipping) [Agent 3 finding]

## Implementation Steps

### Step 1 — test_builtin_loops.py: global regression test

In `scripts/tests/test_builtin_loops.py`, add `test_all_failure_terminals_have_diagnostic_action` to `TestBuiltinLoopFiles`:

```python
def test_all_failure_terminals_have_diagnostic_action(self):
    """All built-in loops must have a pre-terminal diagnose state before failure terminals."""
    for loop_name, loop_yaml in self._load_all_builtin_loops():
        states = loop_yaml.get("states", {})
        failure_terminals = [
            name for name, cfg in states.items()
            if cfg.get("terminal") and name in ("failed", "error", "aborted")
        ]
        for ft in failure_terminals:
            # Find any state that routes to this terminal
            routes_to_terminal = [
                (name, cfg) for name, cfg in states.items()
                if cfg.get("next") == ft or ft in (cfg.get("transitions") or {}).values()
            ]
            # That routing state must have an action
            for name, cfg in routes_to_terminal:
                assert cfg.get("action"), (
                    f"Loop '{loop_name}': state '{name}' routes to terminal '{ft}' "
                    f"but has no diagnostic action"
                )
```

Adjust routing detection to match the actual FSM YAML structure.

### Codebase Research Findings — Step 1 Corrections

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No `_load_all_builtin_loops()` helper exists.** Use the existing `builtin_loops: list[Path]` pytest fixture (line 22 of `TestBuiltinLoopFiles`). Signature: `@pytest.fixture def builtin_loops(self) -> list[Path]`. The new method must accept `self, builtin_loops: list[Path]` and iterate with `yaml.safe_load(open(loop_file))`.
- **4 loops are still non-compliant** after BUG-1606's partial land: `sprint-build-and-validate.yaml` (bare `failed: terminal: true`), `eval-driven-development.yaml`, `rl-bandit.yaml`, `hitl-compare.yaml` (`failed:` with both `action_type:` and `terminal: true` inline — silently skipped by executor). The global regression test will fail for these until they are fixed. Either guard the test behind BUG-1606 full completion or scope it to loops that have a `diagnose` state (checking that it has an action and routes to the terminal).
- **Import line**: `from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm` (matches `test_builtin_loops.py:13`).

### Step 2 — Per-loop test assertions in test_builtin_loops.py

At the existing assertions in `test_builtin_loops.py` at lines 1967, 2354, 2717, 2914, 3071 that assert `terminal: true` on `failed` states, add a companion assertion:

```python
# After BUG-1606: a pre-terminal diagnose state must exist
diagnose_state = states.get("diagnose") or states.get("diagnose_failure") or states.get("report")
assert diagnose_state is not None, f"Expected a pre-terminal diagnose state before 'failed'"
assert diagnose_state.get("action"), "Pre-terminal diagnose state must have an action"
```

Adjust state name lookup to match what BUG-1606 actually used for each loop.

### Codebase Research Findings — Step 2 Corrections

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Accurate per-loop class names and line numbers:**
  - `TestRecursiveRefineLoop` (line 1946) — already has `test_diagnose_routes_to_failed` (line 2014), `test_diagnose_is_not_terminal` (line 2018); no additions needed
  - `TestSprintBuildAndValidateLoop` (line ~2335) — `"diagnose"` is NOT in the required states set; no `test_diagnose_*` methods; needs companion assertions (but YAML also not yet fixed — coordinate with BUG-1606 completion)
  - `TestSvgTextgradLoop` (line 2639) — already has `test_diagnose_*` assertions; no additions needed
  - `TestHtmlAnythingLoop` (line 2922) — already has `"diagnose"` in required states set; no additions needed
  - `TestHitlCompareLoop` (line 3079) — has `test_failed_state_is_terminal` but NO `test_diagnose_*`; needs companion assertions (but YAML also not yet fixed)
  - `TestRlCodingAgentLoop` (line 3242) and `TestAgentEvalImproveLoop` (line 3289) — both fully compliant with `test_diagnose_routes_to_failed` and `test_diagnose_is_not_terminal`; no additions needed
- **Loops that still need YAML fixes before per-loop companion assertions can pass:** `sprint-build-and-validate`, `eval-driven-development`, `rl-bandit`, `hitl-compare`

### Step 3 — test_fsm_validation.py: TestFailureTerminalActionValidation (if BUG-1607 adds validation)

If `validate_failure_terminal_action()` is added to `validation.py` by BUG-1607, add `TestFailureTerminalActionValidation` following the `TestDescriptionFieldValidation` pattern:

```python
class TestFailureTerminalActionValidation:
    def test_bare_failure_terminal_emits_warning(self):
        fsm = {"states": {"failed": {"terminal": True}}}
        errors = validate_fsm(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert any("failed" in str(w) for w in warnings)

    def test_failure_terminal_with_diagnose_state_passes(self):
        fsm = {"states": {
            "diagnose": {"action_type": "prompt", "action": "...", "next": "failed"},
            "failed": {"terminal": True}
        }}
        errors = validate_fsm(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING
                    and "failed" in str(e)]
        assert not warnings
```

### Step 4 — test_fsm_executor.py fixture updates

Lines ~3830–3834 and ~3856–3859 contain inline `failed: terminal: true` YAML fixtures. These tests run the child loop through `FSMExecutor.run()` directly — they do NOT call `validate_fsm()` on the fixtures. As a result, the new WARNING from BUG-1607 will **not** be emitted during these tests. No changes to `test_fsm_executor.py` are required.

_Confirmed by `/ll:refine-issue` codebase analysis: both fixtures are written to `tmp_path / ".loops" / "child.yaml"` and executed via `FSMExecutor`, not validated via `validate_fsm()`._

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Correct Step 2 scope** — add `test_diagnose_routes_to_failed` and `test_diagnose_is_not_terminal` to `TestSvgTextgradLoop` and `TestHtmlAnythingLoop` in addition to `TestSprintBuildAndValidateLoop` and `TestHitlCompareLoop`; wiring research found the refine-issue assertions that these two classes "already have test_diagnose_* assertions / no additions needed" are likely incorrect
7. **Verify CLI exit code** before writing the global regression test in Step 1 — confirm `ll-loop validate` returns exit code `0` for WARNING-only results (not ERROR); `TestBuiltinLoopResolution.test_builtin_fallback` (line 146) calls `main_loop(["ll-loop", "validate", ...])` and asserts exit `== 0`; check `scripts/little_loops/cli/loop/config_cmds.py:cmd_validate()` exit logic
8. **Cross-issue doc tracking** — after BUG-1607 lands, confirm `docs/reference/API.md:validate_fsm` "Checks performed" section and `skills/review-loop/reference.md` V-series table are updated to reflect the new warning

### Step 5 — test_fsm_schema.py

`test_terminal_only_state_valid()` at line ~951–963 explicitly asserts `StateConfig(terminal=True)` with no action produces zero errors. Since BUG-1607 uses `ValidationSeverity.WARNING` (not ERROR), this test passes unchanged. Verify this is still true after BUG-1607 lands.

## Acceptance Criteria

- `test_all_failure_terminals_have_diagnostic_action` passes for all 12 fixed loops (after BUG-1606)
- Per-loop assertions at lines 1967, 2354, 2717, 2914, 3071 each have companion `diagnose` state assertions
- `TestFailureTerminalActionValidation` passes (if BUG-1607 adds validation)
- `test_terminal_only_state_valid()` still passes (WARNING severity, not ERROR)
- No regressions in test_fsm_executor.py fixtures

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-18_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Concerns
- BUG-1607 is still open — Step 3 (`TestFailureTerminalActionValidation`) requires `validate_failure_terminal_action()` in `validation.py` which BUG-1607 has not yet delivered; skip Step 3 or add a conditional import guard during implementation
- Global regression test (Step 1) has an unresolved design decision: whether to scope it to all loops (will fail for `sprint-build-and-validate`, `eval-driven-development`, `rl-bandit` which lack diagnose states) or filter to loops that already have a `diagnose` state; decide which approach before writing the test

## Labels

`bug`, `tests`, `fsm`, `diagnostics`

---

**Priority**: P3 | **Created**: 2026-05-18

## Session Log
- `/ll:ready-issue` - 2026-05-18T09:55:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7cd4bcd1-64f9-44c8-a217-cb30cd0a7e5d.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d9f8c4a-4284-47cc-b396-b8ed5cb5ce3e.jsonl`
- `/ll:wire-issue` - 2026-05-18T09:49:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/150faf7f-fbd6-464e-92f0-8a81ae8c4906.jsonl`
- `/ll:refine-issue` - 2026-05-18T09:42:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5a5f400-07f0-4c18-b4e3-6821f796ba8d.jsonl`
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbd13cdc-51a4-41ee-85fe-30c33cc936aa.jsonl`
- `/ll:manage-issue` - 2026-05-18T10:02:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
