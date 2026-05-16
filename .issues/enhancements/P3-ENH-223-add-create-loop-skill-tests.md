# Add Tests for /ll:create-loop Skill

## Problem

The `/ll:create-loop` interactive loop creation wizard has no test coverage. While loop execution (`ll-loop` CLI) has 200+ tests across 7 test files, the loop creation pathway is completely untested.

This creates a gap where the primary user entry point for creating loops could break without detection.

## Current State

**Well-tested (ll-loop execution):**
- `test_ll_loop_parsing.py` - CLI argument parsing (23 tests)
- `test_ll_loop_state.py` - Stop/resume (8 tests)
- `test_ll_loop_errors.py` - Error handling (12 tests)
- `test_ll_loop_integration.py` - End-to-end execution (80+ tests)
- `test_ll_loop_display.py` - Display formatting (54 tests)
- `test_ll_loop_commands.py` - Subcommands (18 tests)
- `test_fsm_schema.py` - Schema dataclasses
- `test_fsm_compilers.py` - Paradigm compilation

**Untested (loop creation):**
- `/ll:create-loop` command (`commands/create_loop.md`)

## Expected Behavior

Create a test file `test_create_loop.py` covering:

1. **Template selection and population**
   - Each paradigm template loads correctly
   - Required fields are present in templates

2. **Paradigm-specific question flows**
   - Goal paradigm asks for goal condition
   - Convergence paradigm asks for convergence criteria
   - Invariants paradigm asks for invariant conditions
   - Imperative paradigm asks for state sequence

3. **YAML generation for each paradigm**
   - Generated YAML is valid and parseable
   - Generated YAML passes `ll-loop validate`
   - All required fields are populated

4. **File creation and overwrite handling**
   - Creates file in `.loops/` directory
   - Handles existing file gracefully (prompt or error)
   - Uses correct filename from loop name

5. **End-to-end wizard flow**
   - Complete flow from paradigm selection to file creation
   - Error handling for invalid inputs

## Files to Examine

- `commands/create_loop.md` - Command definition (implements /ll:create-loop)
- `scripts/little_loops/fsm/` - FSM modules for reference
- `scripts/tests/test_ll_loop*.py` - Existing test patterns to follow

## Acceptance Criteria

- [x] New test file `scripts/tests/test_create_loop.py` exists
- [x] Tests cover all 4 paradigms (goal, convergence, invariants, imperative)
- [x] Tests verify YAML generation produces valid output
- [x] Tests verify file creation in `.loops/` directory
- [x] All tests pass with `pytest scripts/tests/test_create_loop.py -v`

## Priority Rationale

P3 - The loop creation feature works but lacks regression protection. Not blocking any functionality, but important for maintainability.

---
*Discovered by: test coverage analysis*
*Related: FEAT-048 (create-loop command)*

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-04
- **Status**: Completed

### Changes Made
- `scripts/tests/test_create_loop.py`: New test file with 40 tests covering:
  - Template validation (4 templates: python-quality, javascript-quality, tests-until-passing, full-quality-gate)
  - Goal paradigm YAML generation (6 tests)
  - Invariants paradigm YAML generation (6 tests)
  - Convergence paradigm YAML generation (6 tests)
  - Imperative paradigm YAML generation (8 tests)
  - CLI validation via `ll-loop validate` (5 tests)
  - File creation in `.loops/` directory (5 tests)

- `thoughts/shared/plans/2026-02-04-ENH-223-management.md`: Implementation plan

### Note on Test Scope
Since `/ll:create-loop` is a prompt-based skill (markdown instructions for Claude), the interactive wizard flow cannot be directly unit tested. The tests validate the **artifacts** produced by the command:
1. Template YAML definitions compile to valid FSMs
2. Example YAML patterns from the command documentation are valid
3. CLI validation works on generated loop files
4. File creation in `.loops/` directory structure

### Verification Results
- Tests: PASS (40/40)
- Lint: PASS (ruff check)
- Types: PASS (mypy)
