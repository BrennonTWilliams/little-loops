---
discovered_date: 2026-03-10T00:00:00Z
discovered_by: capture-issue
---

# ENH-671: Eliminate paradigms as a runtime concept

## Summary

The FSM loop engine currently supports two authoring layers: paradigm YAML (goal/convergence/invariants/imperative) that compiles to FSM YAML, and raw FSM YAML directly. The paradigm compilation layer adds complexity without commensurate value — paradigms are partially redundant with each other, create a leaky abstraction (advanced features require FSM knowledge anyway), and force users to learn two schemas. The engine should speak only FSM; paradigms should survive purely as wizard templates that generate FSM YAML, not as a runtime-compiled schema concept.

## Current Behavior

The engine accepts paradigm YAML (`paradigm: goal`, `paradigm: convergence`, etc.) and compiles it to FSM at load time via `compile_paradigm()` in `fsm/compilers.py`. Users can write either paradigm YAML or raw FSM YAML. The four paradigms (goal, convergence, invariants, imperative) are first-class schema concepts with their own required fields and validation.

## Expected Behavior

The engine accepts only FSM YAML (states + transitions). Paradigm templates exist as starting points in `/ll:create-loop` wizard output and documentation examples, but are not compiled at runtime. A user invoking `/ll:create-loop` with "goal" style gets FSM YAML generated for them — they see and edit FSM directly. The `compile_paradigm()` function and paradigm-specific field validation are removed from the execution path.

## Motivation

- Paradigm redundancy: Invariants is structurally identical to chained Goal loops; Goal and Convergence differ only in stall detection (a parameter, not a paradigm). The taxonomy doesn't earn its complexity.
- Leaky abstraction: `on_partial_target`, `extra_states`, and raw `route:` tables are FSM concepts bleeding through the paradigm layer. Power users already need FSM knowledge.
- Two-schema problem: Users must learn paradigm YAML for simple cases and FSM YAML for advanced cases, rather than learning FSM once.
- The `fsm` passthrough paradigm already exists, which is an implicit admission that paradigms are sometimes insufficient.
- Simpler engine: removing the compile step reduces code surface area and eliminates a class of bugs where compiled FSM diverges from user intent.

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
- `scripts/little_loops/cli/loop/_helpers.py` — remove `compile_paradigm()` call in `load_loop()`
- `scripts/little_loops/cli/loop/config_cmds.py` — remove paradigm compilation from validate/compile commands
- `scripts/little_loops/fsm/validation.py` — remove paradigm-specific validation paths

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — calls `load_loop()` which triggers compilation
- `scripts/little_loops/cli/loop/testing.py` — uses paradigm compile for `ll-loop test`
- `skills/create-loop/SKILL.md` — wizard that generates paradigm YAML; update to emit FSM YAML

### Similar Patterns
- `.loops/*.yaml` built-in loops — verify all use `paradigm: fsm` or raw FSM
- `scripts/tests/` — paradigm compiler tests need updating or removal

### Tests
- `scripts/tests/test_compilers.py` (likely) — compiler unit tests; keep as wizard template tests
- `scripts/tests/test_loop_*.py` — integration tests may use paradigm YAML fixtures

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — major rewrite of "The 4 Paradigms" section
- `docs/generalized-fsm-loop.md` — remove compiler/paradigm sections

### Configuration
- N/A

## Implementation Steps

1. Audit all test fixtures and `.loops/` files that use paradigm YAML (not raw FSM)
2. Move `compile_paradigm()` and compiler functions out of the engine load path; retain as template utilities
3. Update `load_loop()` in `_helpers.py` to reject paradigm YAML with a clear migration message
4. Update `/ll:create-loop` wizard to emit FSM YAML using compilers as generation helpers
5. Update built-in loop files and documentation
6. Run test suite; update/remove paradigm-specific tests

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

## Session Log

- `/ll:capture-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1564701c-0b71-47e9-8677-e3a418dce76e.jsonl`

---

**Open** | Created: 2026-03-10 | Priority: P3
