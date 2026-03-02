# ENH-510: Extract output_parsing from parallel/ to shared location

## Plan

### Phase 1: Move File
- [ ] `git mv scripts/little_loops/parallel/output_parsing.py scripts/little_loops/output_parsing.py`
- [ ] Update module docstring to follow `work_verification.py` pattern (name both consumers)

### Phase 2: Update Production Imports
- [ ] `issue_manager.py:33` — change `from little_loops.parallel.output_parsing` → `from little_loops.output_parsing`
- [ ] `parallel/worker_pool.py:24` — change `from little_loops.parallel.output_parsing` → `from little_loops.output_parsing`

### Phase 3: Update Test Imports
- [ ] `test_output_parsing.py:5` — update top-level import block
- [ ] `test_issue_manager.py:83,160,242,285` — update 4 inline imports
- [ ] `test_workflow_integration.py:348` — update 1 inline import

### Phase 4: Update Root __init__.py
- [ ] Add import statement for `parse_ready_issue_output` and `parse_manage_issue_output`
- [ ] Add `# output_parsing` comment group to `__all__`

### Phase 5: Update Documentation
- [ ] `docs/reference/API.md:1927,1960,2638` — module path and import examples
- [ ] `docs/ARCHITECTURE.md:243` — directory tree listing
- [ ] `CONTRIBUTING.md:235` — directory tree listing
- [ ] `docs/research/claude-cli-integration-mechanics.md:168,253` — source path references

### Phase 6: Verify
- [ ] `python -m pytest scripts/tests/` — all tests pass
- [ ] `ruff check scripts/` — no lint errors
- [ ] `python -m mypy scripts/little_loops/` — type checking passes

## Success Criteria
- No file exists at `scripts/little_loops/parallel/output_parsing.py`
- All imports reference `little_loops.output_parsing`
- All tests pass
- No backwards-compatibility shim needed
