---
id: ENH-2194
priority: P4
type: ENH
status: open
discovered_date: 2026-06-15
discovered_by: capture-issue
captured_at: '2026-06-15T21:55:27Z'
relates_to: [ENH-2161]
decision_needed: false
---

# ENH-2194: `from:` Stubs Without `initial`/`states` Hidden from `ll-loop list --internal`

## Summary

Pure context-override `from:` stubs — loop files that set `from:` plus context overrides but declare no `initial:` or `states:` of their own — are silently excluded from `ll-loop list` at every visibility tier (`--internal`, `--all`). The root cause is that `is_runnable_loop()` checks raw YAML for `initial` and `states` without resolving `from:` inheritance, so these stubs never enter the listing pool. `deep-research-arxiv.yaml` (introduced in ENH-2161) is the canonical example: it has `visibility: internal` and is runnable via `ll-loop run` / `ll-loop validate`, but is invisible to `ll-loop list --internal`.

## Motivation

`visibility: internal` was designed so that delegated-only loops surface under `ll-loop list --internal` rather than cluttering the public list. That contract breaks for pure context-override stubs: users and tooling that run `ll-loop list --internal` to discover available internal loops won't see them at all.

The workaround — adding `initial: init` and `states: {}` to every stub — is viable but fragile: it's easy to forget on future stubs and produces misleading raw YAML (the stub has states that don't exist in it). The correct fix is to extend `is_runnable_loop()` so it returns `True` for stubs that become runnable after inheritance resolution.

## Expected Behavior

`ll-loop list --internal` (and `--all`) should include `deep-research-arxiv` (and any future pure context-override stubs) because:
- The stub is runnable (`ll-loop validate` passes, `ll-loop run --dry-run` resolves the full FSM).
- The stub declares `visibility: internal`, signaling intent to appear under `--internal`.

## Implementation Steps

Two viable approaches:

### Option A — Extend `is_runnable_loop()` (preferred)

> **Selected:** Option A — Extend `is_runnable_loop()` — aligns with the existing pattern where `load_and_validate()` and `ll-loop run`/`ll-loop validate` already call `resolve_inheritance()` first; ~10-line change with maximum reuse of existing infrastructure and no operational discipline burden.

In `scripts/little_loops/fsm/validation.py`, update `is_runnable_loop()` to call `resolve_inheritance()` when the raw YAML contains a `from:` key before checking for `initial`/`states`:

```python
def is_runnable_loop(path: Path) -> bool:
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    if "from" in data:
        try:
            from little_loops.fsm.fragments import resolve_inheritance
            data = resolve_inheritance(data, path.parent)
        except Exception:
            return False
    has_flow = "states" in data or "flow" in data
    return "name" in data and "initial" in data and has_flow
```

Cost: adds a `resolve_inheritance` call per stub file during listing. Stubs are few; this is acceptable.

### Option B — Require `initial`/`states: {}` in stubs (documentation + lint)

Document in loop authoring guidelines that all `from:` stubs intended to be listed must declare `initial:` and `states: {}`. Add an `ll-loop validate` warning when a `from:` stub lacks these fields and has `visibility` != `"public"`. No engine change.

Cost: relies on authors remembering; the existing `deep-research-arxiv` stub still needs to be patched.

**Recommendation**: Option A, since it fixes the existing stub without requiring authors to remember a workaround.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-15.

**Selected**: Option A — Extend `is_runnable_loop()`

**Reasoning**: `load_and_validate()`, `ll-loop run`, and `ll-loop validate` all call `resolve_inheritance()` before checking required fields — Option A brings `is_runnable_loop()` into alignment with this codebase-wide convention. The fix reuses `resolve_inheritance()` from `scripts/little_loops/fsm/fragments.py:154` directly, is safe to call unconditionally (no-op when `from:` is absent), and the existing `TestIsRunnableLoop` and `TestLoopListVisibilityFilter` test patterns provide a clear testing scaffold. Option B would require authors to remember a workaround, leaves the existing `deep-research-arxiv.yaml` stub broken, and produces misleading raw YAML.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Extend `is_runnable_loop()` | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B — Require `initial`/`states: {}` (lint + docs) | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- Option A: `resolve_inheritance()` at `fragments.py:154` accepts `(raw_loop_dict, loop_dir)` and returns unchanged if no `from:` key — zero overhead for non-stub files. Three callers of `is_runnable_loop()` at `info.py:140`, `info.py:151`, `doc_counts.py:146` all benefit from the fix simultaneously.
- Option B: No existing lint rule for this stub pattern; `deep-research-arxiv.yaml` still needs manual patching regardless; author-discipline enforcement has historically produced fragile contracts in this codebase.

## Acceptance Criteria

- [ ] `ll-loop list --internal` includes `deep-research-arxiv` (and any other pure context-override stubs with `visibility: internal`)
- [ ] `ll-loop list` (default) still hides `deep-research-arxiv` (visibility gate still applies)
- [ ] `is_runnable_loop()` returns `True` for a `from:` stub that resolves to a valid FSM after inheritance, `False` if the stub's `from:` chain is broken
- [ ] `test_fsm_validation.py` covers the new behavior: a `from:` stub without own `initial`/`states` returns `True` from `is_runnable_loop()` when the parent provides them
- [ ] `test_ll_loop_commands.py` `TestLoopListVisibilityFilter` verifies that a pure context-override stub with `visibility: internal` appears under `--internal` and is absent from default listing

## Success Metrics

- `ll-loop list --internal` stub coverage: 0 pure context-override stubs visible → all `from:` stubs with `visibility: internal` appear
- `is_runnable_loop()` accuracy: returns `True` for valid `from:` stubs (currently returns `False`)
- Test coverage: 2 new tests added (1 in `test_fsm_validation.py`, 1 in `test_ll_loop_commands.py`)

## Scope Boundaries

- Only `is_runnable_loop()` changes; `load_and_validate()` already handles stubs correctly.
- No changes to the FSM executor, fragment resolver, or schema.
- `deep-research-arxiv.yaml` stub does not need to be modified under Option A.

## API/Interface

N/A — No public API changes. The fix modifies `is_runnable_loop()` in `scripts/little_loops/fsm/validation.py` — an internal utility function called only during listing and doc-count verification.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — update `is_runnable_loop()` to call `resolve_inheritance()` when `from:` key is present

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:140` — `cmd_list()` project loop scan: `sorted(p for p in loops_dir.rglob("*.yaml") if is_runnable_loop(p))`
- `scripts/little_loops/cli/loop/info.py:151` — `cmd_list()` builtin loop scan: `if is_runnable_loop(f) and _rel_key(f, builtin_dir) not in project_names`
- `scripts/little_loops/doc_counts.py:146` — `verify_counts()` loop count: `sum(1 for p in loops_dir.rglob("*.yaml") if is_runnable_loop(p))` — secondary impact: `from:` stubs also go uncounted here, under-reporting the `loops` doc-count total
- `scripts/little_loops/fsm/__init__.py` — re-exports `is_runnable_loop` as part of the public `little_loops.fsm` API (imported by `doc_counts.py` and tests via `from little_loops.fsm import is_runnable_loop`)

### Similar Patterns
- `scripts/little_loops/fsm/fragments.py` — `resolve_inheritance()` already handles `from:` chain resolution; reuse this path

### Tests
- `scripts/tests/test_fsm_validation.py` — add test: `from:` stub without own `initial`/`states` returns `True` from `is_runnable_loop()` when parent provides them
- `scripts/tests/test_ll_loop_commands.py` — add to `TestLoopListVisibilityFilter`: pure context-override stub with `visibility: internal` appears under `--internal` and is absent from default listing

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Behavioral asymmetry**: `load_and_validate()` and `ll-loop run`/`ll-loop validate` call `resolve_inheritance()` as their first step, so stubs work there. `is_runnable_loop()` never calls it — same required-fields check (`name`, `initial`, `states`/`flow`) without the prerequisite resolution. `_load_loop_meta()` in `info.py` also calls `resolve_inheritance()` (try/except), so it would correctly read `visibility: internal` from a stub — but it's never reached because the stub is excluded before `_load_loop_meta()` is called.
- **`resolve_inheritance()` call signature** (`fragments.py:154`): `resolve_inheritance(raw_loop_dict, loop_dir, _seen=())` — pass `data` and `path.parent`; returns merged dict with `from:` stripped. If the input has no `from:` key it returns unchanged (safe to call unconditionally).
- **Secondary impact on `doc_counts.py`**: The doc-count verifier uses `is_runnable_loop()` at line 146, so pure `from:` stubs (like `deep-research-arxiv.yaml`) are also under-counted in the `loops` total. Option A fixes both the listing and the count gap simultaneously.
- **Test patterns to follow**:
  - `TestLoopListVisibilityFilter` in `test_ll_loop_commands.py:712` — uses `_seed()` helper (line 715) to write minimal YAML fixtures into `tmp_path / ".loops"` and patches `get_builtin_loops_dir`. Add a new `test_internal_includes_from_stubs` method that writes a stub YAML with `from:` and `visibility: internal` but no `initial`/`states`, then asserts `cmd_list(args_with_internal, loops_dir)` outputs the stub name.
  - `TestIsRunnableLoop` in `test_doc_counts.py` — direct unit-test class for `is_runnable_loop()`; add a parallel class or extend it in `test_fsm_validation.py` using `tmp_path` fixtures.
  - `_runnable(spec)` helper in `test_ll_loop_commands.py:22` — appends a minimal FSM tail to pass `is_runnable_loop()`. For the new stub fixture this helper is NOT used (the stub should NOT have `initial`/`states`); assert it returns `True` after the fix.
- **`deep-research-arxiv.yaml` keys** (`scripts/little_loops/loops/deep-research-arxiv.yaml`): `name`, `from: deep-research`, `category`, `visibility: internal`, `input_key`, `required_inputs`, `description`, `context` block — no `initial`, `states`, or `flow`. Confirmed pure context-override stub.

## Impact

- **Priority**: P4 — Discoverability gap; the loop is still runnable by name, and the public list is unaffected.
- **Effort**: Small — Option A is a ~10-line change in one function plus two test additions.
- **Risk**: Low — `is_runnable_loop()` is called only during listing and doc-count verification; the inheritance resolution path it would add is already well-tested.

## Session Log
- `/ll:decide-issue` - 2026-06-15T22:15:12 - `b1d17ad8-dc9f-4eae-9b2e-e90be9fcd350.jsonl`
- `/ll:refine-issue` - 2026-06-15T22:11:41 - `10a24057-b22d-4d1f-8907-08b18272ac1e.jsonl`
- `/ll:format-issue` - 2026-06-15T22:01:05 - `03c14e80-681d-442d-8c26-164fa44dd1da.jsonl`
- `/ll:capture-issue` - 2026-06-15T21:55:27Z - `22e5e3c4-fe6e-4acb-9ef0-9a19d70b3da7.jsonl`
