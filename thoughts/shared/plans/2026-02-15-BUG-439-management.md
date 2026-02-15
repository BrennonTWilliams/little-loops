# BUG-439: Hardcoded main branch breaks sprint on feature branches

## Plan

### Phase 1: Data Model (types.py)
- Add `base_branch: str = "main"` to `ParallelConfig`
- Update `to_dict()` and `from_dict()` to include `base_branch`

### Phase 2: Branch Detection (cli/parallel.py, cli/sprint.py, config.py)
- Add `base_branch` param to `create_parallel_config()`
- Detect current branch via `git rev-parse --abbrev-ref HEAD` in both CLI entry points
- Pass detected branch to `create_parallel_config()`

### Phase 3: Replace Hardcoded References
- **worker_pool.py**: Lines 778, 806, 818 — use `self.parallel_config.base_branch`
- **merge_coordinator.py**: Lines 743, 760, 780, 804, 983, 989 — use `self.config.base_branch`
- **orchestrator.py**: Line 289 — use `self.parallel_config.base_branch`
- Update all related error/log messages

### Phase 4: Tests
- Update test fixtures to include `base_branch`
- Add test for non-main branch scenarios
- Update hardcoded "main" assertions in test_merge_coordinator.py, test_subprocess_mocks.py

### Success Criteria
- [x] `base_branch` field exists on `ParallelConfig` with `"main"` default
- [ ] CLI entry points detect and pass current branch
- [ ] All 9+ hardcoded `"main"` references replaced
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Linting passes: `ruff check scripts/`
- [ ] Type checking passes: `python -m mypy scripts/little_loops/`
