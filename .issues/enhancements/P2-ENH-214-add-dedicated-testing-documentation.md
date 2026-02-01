# P2-ENH-214: Add dedicated testing documentation

## Summary
No dedicated testing documentation exists. A docs/TESTING.md file would document testing patterns, conventions, and examples for contributors.

## Current State
- Testing documentation: None (only general docs)
- Contributing guide: Has some test info but not comprehensive
- Impact: Contributors must reverse-engineer test patterns

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
   - How CI runs tests
   - How to generate coverage reports
   - How to troubleshoot coverage issues

## Acceptance Criteria
- [ ] docs/TESTING.md created with above sections
- [ ] Code examples for each testing pattern
- [ ] Hypothesis examples included
- [ ] Fixture usage documented
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
- CONTRIBUTING.md (link from here)
- scripts/tests/conftest.py (reference for fixtures)

## Audit Source
Test Coverage Audit - 2026-02-01
