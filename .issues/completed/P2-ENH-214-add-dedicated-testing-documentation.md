# P2-ENH-214: Add dedicated testing documentation

## Summary
Limited testing documentation exists (E2E_TESTING.md). A comprehensive docs/TESTING.md file would document all testing patterns, conventions, and examples for contributors, including unit tests, property tests, mutation testing, and advanced patterns.

## Current State
- Testing documentation: `docs/E2E_TESTING.md` exists (E2E testing only)
- Contributing guide: Has some test info but not comprehensive (lines 40-86)
- Impact: Contributors must reverse-engineer unit testing patterns, property testing, and advanced techniques
- Gap: No comprehensive testing guide covering all test types and patterns

## Proposed Documentation Structure
1. **Testing Overview**
   - How to run tests
   - Test suite organization
   - Coverage requirements (80% threshold)

2. **Writing Tests**
   - Test file naming and location
   - Test naming conventions
   - Fixture usage guide (conftest.py patterns)
   - Parametrized test patterns

3. **Advanced Testing**
   - Property-based testing with Hypothesis (examples)
   - Mutation testing with mutmut (how to run)
   - Integration vs unit test markers
   - Mock usage guidelines

4. **Test Patterns by Module**
   - How to test CLI commands
   - How to test git operations
   - How to test FSM execution
   - Common pitfalls and solutions

5. **CI/CD and Coverage**
   - Note: CI/CD not configured (no .github/ workflows)
   - How to generate coverage reports locally
   - How to troubleshoot coverage issues
   - Coverage threshold: 80% (configured in pyproject.toml)

## Acceptance Criteria
- [ ] docs/TESTING.md created with above sections
- [ ] Code examples for each testing pattern
- [ ] Hypothesis examples included (reference existing property tests)
- [ ] Fixture usage documented (reference conftest.py)
- [ ] Integration with existing E2E_TESTING.md (either link or merge)
- [ ] Linked from CONTRIBUTING.md
- [ ] Reviewed for accuracy against actual test patterns

## Implementation Notes
- Reference existing test files for real examples
- Keep examples simple but realistic
- Include troubleshooting section for common issues
- Consider adding "How to add your first test" section

## Priority
P2 - Medium: Testing documentation is important for onboarding but not blocking for immediate work.

## Related Files
- docs/TESTING.md (to be created)
- docs/E2E_TESTING.md (existing - reference or merge)
- CONTRIBUTING.md (link from here)
- scripts/tests/conftest.py (reference for fixtures)
- scripts/tests/test_issue_parser_properties.py (Hypothesis examples)
- scripts/tests/test_fsm_compiler_properties.py (Hypothesis examples)
- scripts/pyproject.toml (coverage, mutmut, pytest config)

## Audit Source
Test Coverage Audit - 2026-02-01

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `docs/TESTING.md` [CREATED] - Comprehensive testing guide with all sections from acceptance criteria
- `CONTRIBUTING.md` [MODIFIED] - Added link to TESTING.md in related documentation
- `docs/E2E_TESTING.md` [MODIFIED] - Added link to TESTING.md for cross-reference

### Verification Results
- Tests: PASS (pytest runs successfully)
- Documentation accuracy: VERIFIED (all examples sourced from actual test files)
- Acceptance criteria: ALL MET
  - [x] docs/TESTING.md created with all proposed sections
  - [x] Code examples for each testing pattern (sourced from actual test files)
  - [x] Hypothesis examples included (test_issue_parser_properties.py, test_fsm_compiler_properties.py)
  - [x] Fixture usage documented (conftest.py patterns)
  - [x] Integration with existing E2E_TESTING.md (cross-referenced)
  - [x] Linked from CONTRIBUTING.md
