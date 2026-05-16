---
discovered_date: 2026-03-10T00:00:00Z
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 71
---

# ENH-671: Eliminate paradigms as a runtime concept

## Summary

The FSM loop engine currently supports two authoring layers: paradigm YAML (goal/convergence/invariants/imperative) that compiles to FSM YAML, and raw FSM YAML directly. The paradigm compilation layer adds complexity without commensurate value — paradigms are partially redundant with each other, create a leaky abstraction (advanced features require FSM knowledge anyway), and force users to learn two schemas. The engine should speak only FSM; paradigms should survive purely as wizard templates that generate FSM YAML, not as a runtime-compiled schema concept.

## Current Behavior

The engine accepts paradigm YAML (`paradigm: goal`, `paradigm: convergence`, etc.) and compiles it to FSM at load time via `compile_paradigm()` in `fsm/compilers.py`. Users can write either paradigm YAML or raw FSM YAML. The four paradigms (goal, convergence, invariants, imperative) are first-class schema concepts with their own required fields and validation.

## Expected Behavior

The engine accepts only FSM YAML (states + transitions). Paradigm templates exist as starting points in `/ll:create-loop` wizard output and documentation examples, but are not compiled at runtime. A user invoking `/ll:create-loop` with "goal" style gets FSM YAML generated for them — they see and edit FSM directly. The `compile_paradigm()` function and paradigm-specific field validation are removed from the execution path.

## Motivation

- **Code surface area**: `fsm/compilers.py` is 529 lines with 4 compiler functions (`compile_goal`, `compile_convergence`, `compile_invariants`, `compile_imperative`) that would move out of the runtime path. Removing the compile step eliminates an entire call-site category — 2 `compile_paradigm()` calls in `_helpers.py` and their associated validation branches.
- **Paradigm redundancy**: Invariants is structurally identical to chained Goal loops; Goal and Convergence differ only in stall detection (a parameter, not a paradigm). 4 schemas collapse to 0 runtime-compiled schemas — the taxonomy doesn't earn its complexity.
- **Leaky abstraction**: `on_partial_target`, `extra_states`, and raw `route:` tables are FSM concepts bleeding through the paradigm layer. Power users already need FSM knowledge to use advanced features.
- **Two-schema problem**: Users must learn paradigm YAML for simple cases and FSM YAML for advanced cases, rather than learning FSM once. The `fsm` passthrough paradigm (already in use by all current built-in loops) is an implicit admission that paradigms are sometimes insufficient.
- **Zero migration risk from built-ins**: All existing built-in loops already use `paradigm: fsm`; the migration cost is concentrated in tests (5 test files reference non-FSM `paradigm:` values) and user-authored `.loops/` files.

## Proposed Solution

1. **Deprecate paradigm YAML as a runtime input** — add a deprecation warning when `paradigm:` field is detected without `initial:` (i.e., paradigm-style, not FSM with paradigm label).
2. **Move compilers to wizard/template layer** — `fsm/compilers.py` becomes a template generation utility used only by `/ll:create-loop`, not by the engine loader.
3. **Update `/ll:create-loop`** — wizard continues to offer paradigm-style guidance ("fix until clean", "drive a metric", etc.) but outputs FSM YAML. Users see the generated FSM and can edit it directly.
4. **Remove paradigm-specific field validation** from `_helpers.py` / `load_loop()` — only FSM schema validation remains.
5. **Update built-in loops** — `fix-quality-and-tests` and `issue-refinement` already use `paradigm: fsm`; verify they need no changes.
6. **Update documentation** — LOOPS_GUIDE.md paradigm section becomes "Loop Templates" showing FSM examples; compilers.py docstrings updated.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/compilers.py` — move from runtime path to wizard/template utility
- `scripts/little_loops/cli/loop/_helpers.py` — remove `compile_paradigm()` call in **both** `load_loop()` (line 130) and `load_loop_with_spec()` (line 159); also review `resolve_loop_path()` (lines 86-107) which prefers `.fsm.yaml` over `.yaml` (paradigm-preference logic may simplify)
- `scripts/little_loops/cli/loop/config_cmds.py` — remove `cmd_compile()` (lines 12-46) or repurpose as a template-generation utility; remove paradigm auto-compile in `cmd_validate()` (lines 59-72)
- `scripts/little_loops/cli/loop/run.py` — remove direct `compile_paradigm()` call at line 44 (auto-compile block lines 41-44); this is a **direct** call in `cmd_run()`, not via `load_loop()`
- `scripts/little_loops/fsm/__init__.py` — remove `compile_paradigm` from package exports (line 73) and `__all__` (line 167)
- `scripts/little_loops/fsm/validation.py` — minimal change: optionally remove `paradigm` from `KNOWN_TOP_LEVEL_KEYS` (line 78) if it should no longer be a recognized top-level field; note: no paradigm-specific _validation logic_ exists here today

### Dependent Files (Callers/Importers)
- `skills/create-loop/SKILL.md` — wizard that generates paradigm YAML; update to emit FSM YAML

### Similar Patterns
- `loops/issue-refinement.yaml` — uses `paradigm: fsm` ✓ (no change needed)
- `loops/fix-quality-and-tests.yaml` — uses `paradigm: fsm` ✓ (no change needed)
- `.loops/issue-refinement-git.yaml` — uses `paradigm: fsm` ✓ (no change needed)

### Tests
- `scripts/tests/test_fsm_compilers.py` (1278 lines) — dedicated compiler unit tests for all 4 paradigms + `compile_paradigm` dispatcher; move/repurpose as template generation tests
- `scripts/tests/test_fsm_compiler_properties.py` (470 lines) — property-based compiler tests; move/repurpose alongside above
- `scripts/tests/test_ll_loop_execution.py` — E2E tests with real paradigm YAML fixtures (goal, convergence, invariants, imperative); update to FSM YAML fixtures
- `scripts/tests/test_ll_loop_integration.py` — integration tests that mock `compile_paradigm`; remove mock and update fixtures
- `scripts/tests/test_ll_loop_parsing.py` — has `"compile paradigm.yaml"` argument test; update for new compile command behavior

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — major rewrite of "The 4 Paradigms" section; also remove/correct `extra_states` reference (documented but never implemented)
- `docs/generalized-fsm-loop.md` — remove compiler/paradigm sections
- `docs/reference/API.md` — remove `compile_paradigm` from public API reference
- `docs/reference/CLI.md` — update `ll-loop compile` command description
- `skills/create-loop/paradigms.md` — update or remove paradigm authoring reference
- `skills/create-loop/templates.md` — convert paradigm YAML templates to FSM YAML
- `skills/create-loop/reference.md` — update paradigm concepts
- `skills/review-loop/SKILL.md` + `skills/review-loop/reference.md` — update paradigm references

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on direct codebase analysis:_

**Correction: `testing.py` has no paradigm compile calls** — `scripts/little_loops/cli/loop/testing.py` contains zero references to `compile_paradigm`. The `ll-loop test` subcommand does not auto-compile paradigm files. The issue's original mention of this file was incorrect.

**`run.py` has a DIRECT `compile_paradigm()` call** (not just via `load_loop()`) — `run.py:44` independently detects paradigm files and calls `compile_paradigm(spec)` directly. There are therefore **4 independent compile_paradigm call sites** to remove, not 2:
1. `_helpers.py:130` — inside `load_loop()`
2. `_helpers.py:159` — inside `load_loop_with_spec()`
3. `config_cmds.py:29` — inside `cmd_compile()`
4. `run.py:44` — inside `cmd_run()`
And the validate auto-compile block: `config_cmds.py:70-72`.

**`validation.py` scope is minimal** — no paradigm-specific validation logic exists in this file. The only change is whether to keep `"paradigm"` in `KNOWN_TOP_LEVEL_KEYS` (line 84) as allowed metadata. Since `paradigm: fsm` will remain valid on FSM YAML files, keeping it is likely correct.

**Test count** — the issue's "5 test files" figure understates the scope. At least 12 test files reference `paradigm` in some form; 5 have meaningful paradigm-YAML fixtures to update. Note: `test_builtin_loops.py:36-45` asserts all built-in loops have a `paradigm` field — this test remains valid since `paradigm: fsm` will still be present on FSM YAML files.

**`lifecycle.py` also calls `load_loop`** — `scripts/little_loops/cli/loop/lifecycle.py` calls `load_loop()` (from `_helpers.py`) for `ll-loop resume`. It will automatically benefit from any change to `load_loop()` without needing its own edit.

**Deprecation warning approach** — the codebase has no `warnings.warn(DeprecationWarning)` Python calls. The established pattern for "unexpected but non-fatal" conditions is `ValidationSeverity.WARNING` via `logger.warning()` (see `validation.py:387-415`). A deprecation warning for paradigm YAML should follow the same pattern: emit a logger warning rather than raising a hard error, to allow a deprecation period before removal.

**Additional skill/docs files needing updates** — the locator found these not listed in the issue:
- `skills/create-loop/paradigms.md` — paradigm reference documentation; update or remove
- `skills/create-loop/templates.md` — loop templates in paradigm format; convert to FSM YAML
- `skills/create-loop/reference.md` — references paradigm concepts; update
- `skills/review-loop/SKILL.md` and `skills/review-loop/reference.md` — reference paradigm concepts
- `docs/reference/API.md` and `docs/reference/CLI.md` — reference `compile_paradigm` and the `ll-loop compile` command

**`extra_states` is documented but not implemented** — `LOOPS_GUIDE.md` references `extra_states` as a way to extend paradigm-compiled states, but no `extra_states` key is read in any compiler function in `compilers.py`. This is a doc inconsistency to clean up during the documentation update step.

### Configuration
- N/A

## Implementation Steps

1. **Audit test fixtures** — grep for non-fsm `paradigm:` values in `scripts/tests/`; the 5 primary files to update are `test_fsm_compilers.py`, `test_fsm_compiler_properties.py`, `test_ll_loop_execution.py`, `test_ll_loop_integration.py`, `test_ll_loop_parsing.py`
2. **Audit built-in loops** — all 3 loop YAML files already use `paradigm: fsm`; no changes needed
3. **Remove compile_paradigm from engine load path** — edit 5 locations:
   - `_helpers.py:128-130` (load_loop auto-compile block)
   - `_helpers.py:157-159` (load_loop_with_spec auto-compile block)
   - `run.py:41-44` (cmd_run auto-compile block)
   - `config_cmds.py:69-72` (cmd_validate auto-compile block)
   - `config_cmds.py:cmd_compile()` — repurpose or remove the compile subcommand
4. **Add deprecation path** — in `load_loop()` and `load_loop_with_spec()`, replace the auto-compile block with a `ValueError` (or deprecation warning) pointing users to pre-compile with `ll-loop compile` or update to FSM YAML
5. **Remove package export** — remove `compile_paradigm` from `fsm/__init__.py:73` and `__all__` list at line 167
6. **Update `skills/create-loop/SKILL.md`** — wizard continues to offer paradigm-style guidance but outputs FSM YAML using compilers as generation helpers (call compile functions internally, emit FSM YAML to user)
7. **Update test suite** — convert paradigm YAML fixtures to FSM YAML; keep `test_fsm_compilers.py` as wizard template tests (rename class docstrings); remove `compile_paradigm` mock from integration tests
8. **Update documentation** — rewrite paradigm section in `docs/guides/LOOPS_GUIDE.md`; verify `docs/generalized-fsm-loop.md`
9. **Run tests** — `python -m pytest scripts/tests/ -v --tb=short`

## Impact

- **Priority**: P3 — Significant architectural simplification; not blocking current features
- **Effort**: Medium — Compiler code moves rather than disappears; main cost is updating tests, docs, and the create-loop wizard
- **Risk**: Medium — Any existing `.loops/` files using paradigm YAML (not `paradigm: fsm`) will break; needs migration path or deprecation period
- **Breaking Change**: Yes — paradigm YAML authoring format deprecated/removed

## Success Metrics

- Engine loader contains zero calls to `compile_paradigm()`
- `/ll:create-loop` wizard outputs valid FSM YAML that passes `ll-loop validate`
- All existing built-in loops validate without modification
- `docs/guides/LOOPS_GUIDE.md` references "FSM states and transitions" as the single authoring model

## Scope Boundaries

- The wizard UX guidance ("fix until clean", "drive a metric") is **in scope** to keep — just as template names, not runtime paradigms
- Hierarchical FSM (FEAT-659) is **out of scope** — separate concern
- The `convergence` evaluator type in `evaluators.py` is **out of scope** — that's an evaluator, not a paradigm

## API/Interface

```python
# BEFORE: compile_paradigm() called at load time
def load_loop(name: str) -> FSMLoop:
    spec = yaml.safe_load(...)
    if "paradigm" in spec and "initial" not in spec:
        return compile_paradigm(spec)   # ← removed
    return FSMLoop.from_dict(spec)

# AFTER: compile_paradigm() used only by wizard/template generation
def load_loop(name: str) -> FSMLoop:
    spec = yaml.safe_load(...)
    return FSMLoop.from_dict(spec)      # FSM only
```

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/LOOPS_GUIDE.md` | Primary user-facing doc describing paradigms — major update required |
| `docs/generalized-fsm-loop.md` | FSM architecture reference — paradigm compiler section to be removed |
| `scripts/little_loops/fsm/compilers.py` | Implementation to be relocated |

## Labels

`architecture`, `refactoring`, `fsm`, `captured`

## Resolution

Removed `compile_paradigm()` from all 4 engine runtime call sites:
- `_helpers.py`: `load_loop()` and `load_loop_with_spec()` now raise `ValueError` for paradigm YAML
- `run.py`: `cmd_run()` now raises `ValueError` for paradigm YAML instead of auto-compiling
- `config_cmds.py`: `cmd_validate()` now returns error code 1 for paradigm YAML
- `fsm/__init__.py`: Removed `compile_paradigm` from package exports and `__all__`

`cmd_compile()` retained as the migration path for converting paradigm YAML → FSM YAML.

Updated tests:
- `test_builtin_loops.py`: `test_all_compile_to_valid_fsm` → `test_all_validate_as_valid_fsm` using `load_and_validate`
- `test_create_loop.py`: 5 `TestLoopFileValidation` tests converted to FSM YAML fixtures
- `test_ll_loop_execution.py`: 4 `TestCmdTest` tests converted from paradigm YAML to FSM YAML

## Session Log

- `/ll:capture-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1564701c-0b71-47e9-8677-e3a418dce76e.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b31fd356-3f18-4de7-a793-37b195831fdb.jsonl`
- `/ll:refine-issue` - 2026-03-11T03:37:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/85130897-5362-4131-a548-590ccb343ee9.jsonl`
- `/ll:confidence-check` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/97efacd9-f7cd-4738-9952-c7a34ce0ed0b.jsonl`
- `/ll:ready-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c8f8071-e5fb-4ae8-bb16-8e133482ff0f.jsonl`
- `/ll:ready-issue` - 2026-03-10T22:52:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1a15a49-08e8-460c-b269-32f7ad022079.jsonl`

---

**Completed** | Created: 2026-03-10 | Resolved: 2026-03-10 | Priority: P3

## Blocks
- ENH-493
- ENH-668
- ENH-606
