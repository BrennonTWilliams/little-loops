# P2-FEAT-212: Add CI/CD pipeline with test automation

## Summary
No CI/CD configuration exists. A GitHub Actions workflow would automatically run tests, enforce coverage, and validate code quality on every push and pull request.

## Current State
- CI/CD: None configured
- Test automation: Manual only
- Code quality checks: Manual only

## Proposed Workflow (.github/workflows/tests.yml)
1. **On push to main/PR**
   - Run full test suite
   - Generate coverage report
   - Fail if coverage below 80%
   - Run type checking (mypy)
   - Run linting (ruff check)
   - Run formatting check (ruff format --check)

2. **On PR only**
   - Run mutation testing (mutmut) as optional job
   - Generate coverage diff (new code must be covered)
   - Run integration tests separately

3. **Scheduled (nightly)**
   - Run performance benchmarks
   - Run mutation testing full suite
   - Generate test reports

## Acceptance Criteria
- [ ] .github/workflows/tests.yml created
- [ ] Tests run on every push to main branch
- [ ] Tests run on every pull request
- [ ] Coverage threshold enforced (fail if < 80%)
- [ ] Type checking and linting enforced
- [ ] Status badge added to README
- [ ] Documentation of CI workflow

## Implementation Notes
- Use GitHub Actions (standard for GitHub projects)
- Consider using caching for Python dependencies
- Use matrix strategy for multiple Python versions if needed
- Keep workflow fast (run quick checks first)

## Priority
P2 - Medium: CI/CD is important for team collaboration and quality assurance but can be added incrementally.

## Related Files
- .github/workflows/tests.yml (to be created)
- scripts/pyproject.toml (test configuration)
- README.md (add badge)

## Audit Source
Test Coverage Audit - 2026-02-01
