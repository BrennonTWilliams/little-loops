# ENH-674: Remove deprecated 4 Paradigms compilation from codebase

**Created**: 2026-03-11
**Issue**: `.issues/enhancements/P3-ENH-674-remove-4-paradigms-compilation-references.md`
**Action**: implement
**Confidence**: 96/100 readiness

## Decision Log

- **Keep `paradigm` field on FSMLoop**: The `paradigm` field on `FSMLoop` schema is used as metadata
  to tag loops (e.g., `paradigm: fsm` in YAML files). Since existing FSM YAML files use it as a
  harmless annotation, we'll remove it entirely — no loops need `paradigm: fsm` as it's the default.
- **Delete entire compilers.py**: The file only contains paradigm compilation logic. No functions
  are reusable without paradigms.
- **Remove compile subcommand**: `ll-loop compile` has no purpose without paradigms.

## Implementation Phases

### Phase A: Remove paradigm compilation core
- [x] Delete `scripts/little_loops/fsm/compilers.py`
- [x] Remove `paradigm` field from `FSMLoop` dataclass in `schema.py` (lines 350, 364, 382-383, 421)
- [x] Remove `paradigm` from `KNOWN_TOP_LEVEL_KEYS` in `validation.py` (line 78)
- [x] Remove `paradigm` from `fsm-loop-schema.json` (lines 25-29)
- [x] Update `__init__.py` module docstring (remove paradigm mention)

### Phase B: Remove paradigm detection from CLI
- [x] Remove paradigm YAML detection blocks from `_helpers.py` (lines 126-132, 158-164)
- [x] Update docstrings in `_helpers.py` referencing paradigm
- [x] Remove paradigm detection from `run.py` (lines 40-46)
- [x] Remove `cmd_compile` and paradigm detection from `config_cmds.py` (lines 12-48, 68-75)
- [x] Remove compile subcommand from `__init__.py` CLI parser (lines 131-135, 261-262)
- [x] Remove paradigm display from `info.py` (`_load_loop_meta`, show command)

### Phase C: Clean up YAML files
- [x] Remove `paradigm: fsm` from `.loops/issue-refinement-git.yaml`
- [x] Remove `paradigm: fsm` from `loops/fix-quality-and-tests.yaml`
- [x] Remove `paradigm: fsm` from `loops/issue-refinement.yaml`

### Phase D: Update tests
- [x] Delete `scripts/tests/test_fsm_compilers.py`
- [x] Delete `scripts/tests/test_fsm_compiler_properties.py`
- [x] Update remaining test files to remove paradigm references

### Phase E: Update documentation
- [x] Update relevant docs to remove paradigm references

### Phase F: Close ENH-606 as superseded
- [x] Move ENH-606 to completed with note that it's superseded by ENH-674

## Success Criteria
- `grep -ri "paradigm" scripts/little_loops/` returns zero hits (excluding comments about this removal)
- `grep -ri "compile_paradigm" scripts/` returns zero hits
- Full test suite passes
- No paradigm-related schemas in `fsm-loop-schema.json`
