# ENH-506 Implementation Plan: Split dependency_mapper.py into Sub-package

**Date**: 2026-03-03
**Issue**: ENH-506 (P4 Enhancement)
**Confidence**: 98/100 · Outcome: 79/100

---

## Summary

Split `scripts/little_loops/dependency_mapper.py` (1,361 lines) into a sub-package
mirroring the `issue_history/` pattern. Zero breaking changes — `__init__.py`
re-exports all public and test-required private names.

---

## File Map

| Source lines | Destination |
|---|---|
| 94–176, 917–929 (dataclasses) | `dependency_mapper/models.py` |
| 28–91 (constants) + 179–558 (analysis fns) | `dependency_mapper/analysis.py` |
| 561–757 (format fns) | `dependency_mapper/formatting.py` |
| 760–1037 (ops fns) | `dependency_mapper/operations.py` |
| 1040–1360 (CLI + `_load_issues`) | `cli/deps.py` |
| Re-export hub | `dependency_mapper/__init__.py` |

---

## Phase 0: Create sub-module files

1. `mkdir scripts/little_loops/dependency_mapper/`
2. Create `models.py` — 5 dataclasses (incl. FixResult from line 917)
3. Create `analysis.py` — 6 constants + 7 functions + logger
4. Create `formatting.py` — 2 functions
5. Create `operations.py` — 5 functions + `import re`
6. Create `__init__.py` — re-exports all 16 names + `main` alias

## Phase 1: Create CLI entrypoint

7. Create `cli/deps.py` with `main_deps()` and `_load_issues()` helper
   - `argparse`, `Path` at module level
   - All `dependency_mapper` imports deferred inside `main_deps()`

## Phase 2: Update routing

8. `pyproject.toml:59` — change `ll-deps` entry point to `little_loops.cli:main_deps`
9. `cli/__init__.py` — add `from little_loops.cli.deps import main_deps` + `__all__` entry

## Phase 3: Delete monolith

10. `git rm scripts/little_loops/dependency_mapper.py`

## Phase 4: Update documentation

11. `docs/reference/API.md` — update module reference for `dependency_mapper`
12. `docs/ARCHITECTURE.md` — update references
13. `CONTRIBUTING.md` — update directory structure
14. `skills/map-dependencies/SKILL.md` — update `apply_proposals()` reference

## Phase 5: Verify

15. `python -m pytest scripts/tests/test_dependency_mapper.py -v`
16. `ruff check scripts/`
17. `python -m mypy scripts/little_loops/`

---

## Circular Import Analysis

`dependency_mapper/__init__.py` imports `main_deps` from `cli/deps.py`.
`cli/deps.py` only imports stdlib at module-level; all `dependency_mapper` imports
are deferred inside `main_deps()`. No circular dependency.

`operations.py` imports `validate_dependencies` from `analysis.py` (same package).
No cross-package circular dependency.

---

## Success Criteria

- [ ] All 16 names importable from `little_loops.dependency_mapper`
- [ ] `main` importable from `little_loops.dependency_mapper` (test compat)
- [ ] `ll-deps analyze/validate/fix` subcommands work
- [ ] All tests pass
- [ ] Ruff + mypy clean
