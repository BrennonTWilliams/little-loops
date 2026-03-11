---
discovered_date: 2026-03-11
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 61
---

# ENH-674: Remove deprecated 4 Paradigms compilation from codebase

## Summary

Fully remove all references to the 4 Paradigms compilation feature across code and documentation. The paradigm compilation pipeline is deprecated/legacy and should be completely removed rather than maintained or deduplicated.

## Current Behavior

The codebase contains paradigm compilation logic scattered across multiple files — paradigm detection (`"paradigm" in spec and "initial" not in spec`), compilation functions, paradigm-specific schemas, documentation, and tests. This code is deprecated but still present and maintained.

## Expected Behavior

All paradigm compilation code, references, documentation, and tests are fully removed. Loop definitions use FSM format directly without any paradigm abstraction layer.

## Motivation

Maintaining deprecated paradigm compilation code creates unnecessary maintenance burden, confuses new contributors, and adds dead code paths. Removing it simplifies the codebase and eliminates the need for deduplication efforts like ENH-606.

## Scope Boundaries

**In scope:**
- Remove paradigm compilation functions and modules
- Remove paradigm detection logic from all call sites
- Remove paradigm-related schemas, types, and constants
- Remove paradigm references from documentation
- Remove or update paradigm-specific tests
- Remove vestigial `paradigm: fsm` key from loop YAML files (`.loops/`, `loops/`)
- Close ENH-606 (deduplicate paradigm auto-compile logic) as superseded

**Out of scope:**
- Changing the FSM execution engine
- Modifying FSM logic (states, transitions, actions) in existing loop definitions

## Proposed Solution

1. Identify all paradigm compilation code (compilers, schemas, detection logic)
2. Remove paradigm compiler modules and their imports
3. Remove paradigm detection conditionals from `_helpers.py`, `run.py`, `config_cmds.py`
4. Remove paradigm-related documentation sections
5. Update or remove tests that exercise paradigm compilation
6. Verify all existing FSM loops still work without paradigm support

## Success Metrics

- All `grep -ri "paradigm" scripts/` results return zero hits in source code (excluding comments referencing this removal)
- Full test suite passes with no regressions
- No paradigm-related schemas remain in `fsm-loop-schema.json`
- ENH-606 closed as superseded

## API/Interface

N/A — No new public APIs. This is a removal of deprecated internal APIs only. The paradigm compilation functions in `compilers.py` and paradigm detection logic in `_helpers.py` are internal and not part of the public interface.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/compilers.py` — paradigm compiler modules
- `scripts/little_loops/fsm/schema.py` — paradigm-related schemas/types
- `scripts/little_loops/fsm/validation.py` — paradigm validation logic
- `scripts/little_loops/fsm/__init__.py` — paradigm exports
- `scripts/little_loops/fsm/fsm-loop-schema.json` — paradigm schema definitions
- `scripts/little_loops/cli/loop/_helpers.py` — paradigm detection logic
- `scripts/little_loops/cli/loop/run.py` — paradigm detection logic
- `scripts/little_loops/cli/loop/config_cmds.py` — paradigm detection logic
- `scripts/little_loops/cli/loop/info.py` — paradigm references
- `scripts/little_loops/cli/loop/__init__.py` — paradigm imports

### Dependent Files (Callers/Importers)
- `commands/loop-suggester.md` — may reference paradigm concepts
- `skills/review-loop/SKILL.md` — may reference paradigm validation
- `.loops/issue-refinement-git.yaml` — remove `paradigm: fsm` key
- `loops/fix-quality-and-tests.yaml` — remove `paradigm: fsm` key
- `loops/issue-refinement.yaml` — remove `paradigm: fsm` key

### Similar Patterns
- ENH-606 identifies 4 copy-paste sites for paradigm detection — all should be removed
- ENH-671 (completed) eliminated paradigms as runtime concept — this finishes the cleanup

### Tests
- `scripts/tests/test_fsm_compilers.py` — paradigm compiler tests (remove or convert)
- `scripts/tests/test_fsm_compiler_properties.py` — property-based paradigm tests (remove)
- `scripts/tests/test_ll_loop_execution.py` — paradigm execution paths
- `scripts/tests/test_ll_loop_parsing.py` — paradigm parsing tests
- `scripts/tests/test_ll_loop_commands.py` — paradigm CLI command tests
- `scripts/tests/test_create_loop.py` — paradigm creation tests
- `scripts/tests/test_builtin_loops.py` — paradigm built-in loop tests
- `scripts/tests/test_cli.py` — paradigm CLI references
- `scripts/tests/test_review_loop.py` — paradigm review tests
- `scripts/tests/test_loop_suggester.py` — paradigm suggestion tests
- `scripts/tests/test_ll_loop_integration.py` — paradigm integration tests
- `scripts/tests/test_ll_loop_errors.py` — paradigm error handling tests

### Documentation
- `README.md` — paradigm references
- `CONTRIBUTING.md` — paradigm references
- `CHANGELOG.md` — historical references (preserve as history)
- `docs/generalized-fsm-loop.md` — paradigm documentation
- `docs/reference/API.md` — paradigm API docs
- `docs/reference/CLI.md` — paradigm CLI docs
- `docs/development/TESTING.md` — paradigm test docs
- `docs/guides/LOOPS_GUIDE.md` — paradigm usage guide

### Configuration
- `scripts/little_loops/fsm/fsm-loop-schema.json` — paradigm schema definitions

## Implementation Steps

1. Grep codebase for all paradigm-related code and documentation references
2. Remove paradigm compiler modules and related utility functions
3. Remove paradigm detection logic from all call sites
4. Remove `paradigm: fsm` key from loop YAML files
5. Remove paradigm-related tests or convert to pure FSM tests
6. Update documentation to remove paradigm references
7. Run full test suite to confirm no regressions

## Impact

- **Priority**: P3 - Removes deprecated feature, reduces maintenance burden
- **Effort**: Medium - Touches many files but changes are straightforward removals
- **Risk**: Low - Feature is already deprecated; existing loops should be FSM format
- **Breaking Change**: Yes - Any loops still using paradigm format will need manual conversion to FSM

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | May reference paradigm compilation in system design |
| `docs/reference/API.md` | May document paradigm-related APIs |

## Labels

`enhancement`, `ll-loop`, `cleanup`, `deprecation-removal`

## Resolution

**Resolved**: 2026-03-11

### Changes Made
- Deleted `scripts/little_loops/fsm/compilers.py` (530 lines — 4 paradigm compilers + routing function)
- Removed `paradigm` field from `FSMLoop` dataclass in `schema.py`
- Removed `paradigm` from `KNOWN_TOP_LEVEL_KEYS` in `validation.py`
- Removed `paradigm` schema definition from `fsm-loop-schema.json`
- Removed `cmd_compile` function and `compile` CLI subcommand
- Removed 4 paradigm detection blocks (`"paradigm" in spec and "initial" not in spec`) from `_helpers.py`, `run.py`, `config_cmds.py`
- Removed paradigm display from `info.py` (`_load_loop_meta`, show command header)
- Removed `paradigm: fsm` from 3 loop YAML files
- Deleted `test_fsm_compilers.py` (1278 lines) and `test_fsm_compiler_properties.py` (470 lines)
- Removed paradigm compilation tests from 8 additional test files
- Updated documentation: API.md, CLI.md, LOOPS_GUIDE.md, README.md, CONTRIBUTING.md, TESTING.md, SKILL.md, generalized-fsm-loop.md

### Verification
- `grep -ri "paradigm" scripts/little_loops/` returns zero hits in source code
- `grep -ri "compile_paradigm" scripts/` returns zero hits in source code
- Full test suite: 3283 passed, 0 failed
- Type checking: clean (mypy)
- Linting: clean (ruff)
- ENH-606 already closed as superseded

## Session Log
- `/ll:capture-issue` - 2026-03-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a62efb4c-0a29-4bd8-a178-c13c34639add.jsonl`
- `/ll:format-issue` - 2026-03-11 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f08c54d6-5d2f-49fa-be74-5b3e2575dc08.jsonl`
- `/ll:confidence-check` - 2026-03-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/137a7b5c-d986-4fd2-9e3c-4896313879c2.jsonl`
- `/ll:ready-issue` - 2026-03-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/78bd6806-7974-4164-b7e2-9489ee13d916.jsonl`
- `/ll:manage-issue` - 2026-03-11 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a1ed10ad-297a-4b15-899f-f7abcb35ac49.jsonl`

---

## Status

**Completed** | Created: 2026-03-11 | Completed: 2026-03-11 | Priority: P3
