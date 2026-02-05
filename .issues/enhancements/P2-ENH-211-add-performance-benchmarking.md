# P2-ENH-211: Add performance benchmarking

## Summary
pytest-benchmark is installed in the development environment but unused. Performance benchmarking would establish baselines and catch performance regressions.

## Current State
- pytest-benchmark: Not installed (needs to be added to dev dependencies)
- Performance tests: None
- Performance tracking: No baseline measurements

## Proposed Benchmarks
1. **Issue parsing performance**
   - Parse time per issue file
   - Parse time for large issue sets (100+ issues)
   - Validate regex performance

2. **FSM execution performance**
   - State transition time
   - Evaluator execution time
   - State persistence time

3. **Git operations performance**
   - Worktree creation time
   - Merge operation time
   - Status/diff operation time

4. **CLI startup performance**
   - Time to invoke CLI commands
   - Import time for main modules

5. **Issue history operations**
   - History parsing time
   - Analysis operation time

## Acceptance Criteria
- [ ] At least 10 benchmark tests covering critical paths
- [ ] Benchmarks stored in scripts/tests/benchmarks/ or marked with @pytest.mark.benchmark
- [ ] Baseline measurements established and committed
- [ ] Documentation on running benchmarks
- [ ] Consider adding benchmark comparison to CI (as optional)

## Implementation Notes
- Use pytest-benchmark's @pytest.mark.benchmark decorator
- Store benchmark results in .benchmarks/ (gitignored)
- Use benchmark groups for related operations
- Consider separate benchmark suite from unit tests

## Priority
P2 - Medium: Performance tracking is valuable but not critical; nice-to-have for long-term health.

## Related Files
- scripts/pyproject.toml (add pytest-benchmark to dev dependencies)
- scripts/tests/ (test structure)

## Audit Source
Test Coverage Audit - 2026-02-01

## Verification Notes
- **Verified**: 2026-02-05
- **Correction**: Original issue incorrectly stated pytest-benchmark was installed. Verified against pyproject.toml - pytest-benchmark is not in dev dependencies and needs to be added as part of this enhancement.
