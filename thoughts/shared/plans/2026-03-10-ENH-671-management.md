# ENH-671: Eliminate paradigms as a runtime concept

## Objective
Remove `compile_paradigm()` from the engine runtime load path. Keep `compilers.py` as a
wizard/template utility used only by `cmd_compile()` and `/ll:create-loop`. All five runtime
call sites are replaced with a `ValueError` pointing users to FSM YAML or `ll-loop compile`.

## Design Decision (autonomous)
Use `ValueError` (hard failure) rather than a soft deprecation warning. The success metric
requires "zero calls to `compile_paradigm()` in the engine loader." The codebase research
recommends a deprecation window, but since all built-in loops already use `paradigm: fsm`,
the only breaking impact is user-authored `.loops/` files and tests. The `ll-loop compile`
escape hatch allows migration without data loss.

## Files to Modify

### Runtime (engine load path)
- [x] `scripts/little_loops/cli/loop/_helpers.py` — remove compile calls from load_loop() and load_loop_with_spec()
- [x] `scripts/little_loops/cli/loop/run.py` — remove direct compile_paradigm() call
- [x] `scripts/little_loops/cli/loop/config_cmds.py` — remove auto-compile from cmd_validate()
- [x] `scripts/little_loops/fsm/__init__.py` — remove compile_paradigm export

### Tests
- [x] `scripts/tests/test_builtin_loops.py` — update test_all_compile_to_valid_fsm to use load_and_validate

### NOT changing (compile_paradigm still valid in compilers.py)
- `scripts/tests/test_fsm_compilers.py` — tests compile functions directly; stays as wizard template tests
- `scripts/tests/test_fsm_compiler_properties.py` — same
- `scripts/tests/test_ll_loop_integration.py` — cmd_compile tests mock compilers.compile_paradigm; cmd_compile stays
- `scripts/tests/test_ll_loop_parsing.py` — tests compile subcommand arg parsing; subcommand stays
- `scripts/tests/test_loop_suggester.py` — imports from compilers directly; unaffected

## Success Criteria
- [x] `_helpers.load_loop()` raises ValueError for paradigm YAML (no initial:)
- [x] `_helpers.load_loop_with_spec()` raises ValueError for paradigm YAML
- [x] `run.cmd_run()` uses load_and_validate directly (no compile_paradigm)
- [x] `config_cmds.cmd_validate()` uses load_and_validate for all files
- [x] `fsm/__init__.py` no longer exports compile_paradigm
- [x] `test_builtin_loops` uses load_and_validate (built-in loops are FSM)
- [x] All tests pass: `python -m pytest scripts/tests/ -v --tb=short`
