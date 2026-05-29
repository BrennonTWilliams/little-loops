---
id: ENH-1787
title: FSM scope should support context template variables for file-level locking
type: ENH
status: open
priority: P3
captured_at: '2026-05-29T06:08:56Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
labels:
- enhancement
- fsm
- concurrency
- scope
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1787: FSM scope should support context template variables for file-level locking

## Summary

The `scope:` field in FSM loop YAML is a static list of hardcoded path strings. Loops that operate on a single file (like `rn-refine` operating on a plan file passed via `${context.plan_file}`) cannot declare a file-level scope — they must either omit `scope:` (defaulting to `["."]`, the whole repo) or hardcode a broad directory. This causes false conflicts: two instances of the same loop operating on completely disjoint files are blocked from running concurrently because both claim the entire repo.

The workaround is `--no-lock`, which bypasses all safety rather than providing precise locking.

## Current Behavior

- `scope:` is read statically from the loop YAML at load time via `FSMLoop.from_dict()`
- No variable interpolation is performed on scope values
- Loops without an explicit `scope:` default to `["."]` (whole project) in `LockManager.acquire()`
- Two `ll-loop run rn-refine plan-a.md -b` and `ll-loop run rn-refine plan-b.md -b` conflict even though they touch completely disjoint files

## Expected Behavior

Scope paths can contain `${context.<var>}` template expressions that are resolved at runtime before the lock check:

```yaml
# rn-refine.yaml
scope:
  - "${context.plan_file}"
```

Two instances with different `plan_file` values would have non-overlapping scopes and run concurrently. Two instances with the same `plan_file` would correctly conflict.

## Motivation

This is the complement of BUG-1760 (scope too narrow → false negatives). That bug is about scopes that fail to detect real conflicts. This enhancement is about scopes that falsely detect conflicts where none exist.

Both stem from the same root cause: scope is static and inexpressive. Supporting template variables fixes both directions:

- **False positives** (this issue): loops with different context values are blocked from safe concurrent runs
- **False negatives** (BUG-1760): loops with different context values are allowed to run when they shouldn't (because the scope system can't express "same loop name = conflict regardless of scope" — but that's a separate concern)

Concrete impact: a user wanting to refine two plan files in parallel must either serialize (wait for one to finish) or use `--no-lock` (disable all safety). Neither is good.

## Proposed Solution

### Approach: Template variable interpolation in scope

Resolve `${context.<var>}` expressions in scope paths before passing them to `LockManager`:

1. **Resolution point**: In `cmd_run()` (`run.py`) and `run_background()` (`_helpers.py`), after the FSM is loaded and context is populated, resolve scope template variables against `fsm.context`
2. **Resolution mechanics**: Scan each scope entry for `${context.<var>}` patterns, replace with the corresponding context value
3. **Unresolved variables**: If a variable isn't in context, treat the literal as-is (allowing partial resolution) — or error if the template is malformed
4. **Path normalization**: After resolution, normalize paths as currently done

### Key design decisions

- **Resolution happens in the CLI layer, not in `LockManager`**: `LockManager` continues to receive concrete path lists. The CLI layer resolves templates before calling `acquire()` or `find_conflict()`. This keeps `LockManager` simple and testable.
- **Scope is resolved after context is fully populated**: By the time `cmd_run()` reaches the lock acquisition (line ~262), context is already populated from CLI args and YAML defaults. Resolution happens there.
- **Backwards compatible**: Loops without template variables in scope behave identically. Static scopes continue to work.

### Alternative considered: Name-based locking

Instead of making scope dynamic, add a "same loop name → always conflict" rule. Rejected because it's too coarse — it would prevent safe concurrent runs of the same loop on different files. The point is to enable that use case, not block it.

## API/Interface

### Scope resolution function

```python
# scripts/little_loops/fsm/scope.py (new or in concurrency.py)
def resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]:
    """Resolve ${context.<var>} templates in scope paths."""
    resolved = []
    for path in scope:
        match = re.match(r'^\$\{context\.(.+)\}$', path)
        if match:
            var = match.group(1)
            if var in context:
                resolved.append(str(context[var]))
            else:
                resolved.append(path)  # unresolved — keep literal
        else:
            resolved.append(path)
    return resolved
```

### rn-refine.yaml change (after resolution support lands)

```yaml
scope:
  - "${context.plan_file}"
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/concurrency.py` — add `resolve_scope()` function
- `scripts/little_loops/fsm/__init__.py` — export `resolve_scope` in imports (line 75), `__all__` (near line 189), and module docstring (near line 68)  
  _Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — call `resolve_scope()` at line ~264 before `lock_manager.acquire()`
- `scripts/little_loops/cli/loop/_helpers.py` — call `resolve_scope()` in `run_background()` pre-flight check
- `scripts/little_loops/loops/rn-refine.yaml` — add `scope: ["${context.plan_file}"]`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` also calls `run_background()`; covered by the `_helpers.py` change

### Similar Patterns
- Context variable interpolation already exists in `action:` fields via the FSM runner — scope resolution follows the same pattern
- `VARIABLE_PATTERN` at `scripts/little_loops/fsm/interpolation.py:25` — the canonical regex (`r"\$\{([^}]+)\}"`) for template variable extraction; `interpolate()` at line 169 handles all `${namespace.path}` resolution
- `_ctx_var_re` at `scripts/little_loops/cli/loop/run.py:215` — existing pattern that scans for `${context.<var>}` in action/evaluate templates before execution; directly analogous to what scope resolution needs
- `run_dir` auto-injection at `scripts/little_loops/cli/loop/run.py:159-162` — closest "resolve at runtime" analogue: a context value is computed and injected into `fsm.context` before lock acquisition so `${context.run_dir}` resolves in YAML templates
- `_compute_progress_fingerprint()` at `scripts/little_loops/fsm/executor.py:677` — interpolates file paths from context for stall detection; same pattern of runtime path resolution from context variables

### Tests
- `scripts/tests/test_concurrency.py` — add `test_resolve_scope_static`, `test_resolve_scope_with_context_var`, `test_resolve_scope_unresolved_var`, `test_resolve_scope_mixed`
- `scripts/tests/test_cli_loop_background.py` — add `test_scope_resolution_before_spawn`: two `run_background()` calls with different context values should not conflict
- `scripts/tests/test_cli_loop_run.py` — add integration test: two foreground runs with disjoint scopes don't conflict

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — document template variable support in scope section
- `docs/reference/CLI.md` — update `ll-loop run` scope documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — add `resolve_scope` entry to concurrency module section (near line 4805); update `FSMLoop.scope` attribute doc (line 3982) to note `${context.<var>}` template support [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — update "Concurrency and Locking" section (lines 1411-1442) with template variable scope example [Agent 2 finding]
- `skills/create-loop/reference.md` — document `${context.<var>}` template support in scope field reference (lines 571-579) [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Add `resolve_scope()` to `scripts/little_loops/fsm/concurrency.py` — pure function that takes `list[str]` + `dict[str, Any]`, returns resolved `list[str]`; use regex matching the existing `VARIABLE_PATTERN` at `interpolation.py:25`
2. Wire resolution into `cmd_run()` in `run.py` between context population (~line 162) and lock acquisition (~line 264): `scope = resolve_scope(fsm.scope or ["."], fsm.context)`
3. Wire resolution into `run_background()` in `_helpers.py` — CRITICAL: `run_background()` does NOT currently apply `--context` to the local `fsm` before the pre-flight check at line 967-974; context is only forwarded to the child process via CLI args (line 1026-1027). Step 3 must also parse `args.context` into a local dict and pass it to `resolve_scope()` for the pre-flight `find_conflict()` call. The child process will independently resolve scope in `cmd_run()`.
4. Add `scope: ["${context.plan_file}"]` to `rn-refine.yaml`
5. Add unit tests for `resolve_scope()` in `test_concurrency.py` — follow the `TestScopeLock` class pattern (line 18): test static passthrough, context var resolution, unresolved var preservation, mixed static+template
6. Add integration test in `test_cli_loop_background.py` — model after `test_scope_conflict_returns_1` (line 561): two `run_background()` calls with different context values for the same template var should produce disjoint scopes and not conflict
7. Run existing concurrency and background tests to verify no regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Export `resolve_scope` from `scripts/little_loops/fsm/__init__.py` — add to import block (line 75), `__all__` (near line 189), and module docstring "Concurrency Control" section (near line 68) [Agent 1 + 2 finding]
9. Update `docs/reference/API.md` — add `resolve_scope` function entry in the `little_loops.fsm.concurrency` section; note `${context.<var>}` support in `FSMLoop.scope` attribute description [Agent 2 finding]
10. Update `docs/generalized-fsm-loop.md` — add template variable example to "Concurrency and Locking" section [Agent 2 finding]
11. Update `skills/create-loop/reference.md` — document template variable support in scope field reference [Agent 2 finding]

## Success Metrics

- Two `rn-refine` instances with different `plan_file` values acquire locks without conflict
- Two `rn-refine` instances with the same `plan_file` correctly conflict
- Static scopes (no template variables) behave identically to before
- `--no-lock` still works as an escape hatch

## Scope Boundaries

- Template variable support is limited to `${context.<var>}` — no arbitrary expressions, no nested resolution, no function calls
- Resolution happens at lock-acquisition time only, not continuously during loop execution
- This does NOT add name-based locking (same loop name always conflicts). That's a separate concern tracked in BUG-1760
- Only `context.*` variables are supported; environment variables and other namespaces are out of scope

## Impact

- **Priority**: P3 — `--no-lock` workaround exists, no data loss; but the false conflicts are a daily friction point for anyone running multiple refinement loops
- **Effort**: Small — ~30 lines of new code, one new function, two call sites, YAML change
- **Risk**: Low — additive feature behind template syntax; static scopes are unaffected; resolution happens before lock acquisition
- **Breaking Change**: No — loops without `${context.*}` in scope are unchanged

## Related Key Documentation

- [LOOPS_GUIDE - Scope-Based Concurrency](../docs/guides/LOOPS_GUIDE.md) — current scope documentation
- [API Reference](../docs/reference/API.md) — LockManager and FSM concurrency docs

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Reusable regex**: `VARIABLE_PATTERN` at `interpolation.py:25` (`r"\$\{([^}]+)\}"`) is the canonical template extraction regex — `resolve_scope()` should use the same pattern for consistency, or a simpler `${context.<var>}`-specific regex
- **Pre-existing context scan pattern**: `_ctx_var_re` at `run.py:215` already scans action/evaluate templates for `${context.<var>}` — the same approach applies to scope entries
- **`run_background()` context gap**: The pre-flight scope check at `_helpers.py:967-974` runs before context from `--context` is applied to the local `fsm` (context is only forwarded to the child process at line 1026). Scope resolution in `run_background()` must independently parse `args.context` into a dict and pass it to `resolve_scope()`.
- **`cmd_resume()` foreground path** (`lifecycle.py:361`): Does NOT acquire locks — scope resolution changes don't affect this code path
- **`LockManager` normalization ordering**: `_normalize_path()` at `concurrency.py:277` calls `Path(path).resolve()`, which would turn a literal `${context.plan_file}` into an absolute path containing the literal template string. Resolution MUST happen before `LockManager` receives the scope list, confirming the issue's design decision to resolve at the CLI layer.
- **No existing loops use `scope:`**: All current loops default to `["."]` (whole-project lock). The `rn-refine.yaml` change in this issue will be the first use of the `scope:` field in a committed loop.

## Session Log
- `/ll:wire-issue` - 2026-05-29T20:04:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/abdc7cdc-bdc0-4301-8614-cf927bab7407.jsonl`
- `/ll:refine-issue` - 2026-05-29T06:48:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cce38edf-049a-436e-a20e-74ea5a16ea27.jsonl`
- `/ll:format-issue` - 2026-05-29T06:38:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0074390b-f718-4916-9a17-f29727630895.jsonl`
- `/ll:capture-issue` - 2026-05-29T06:08:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b88328d9-b43a-4afd-b941-7bc140700c24.jsonl`
- `/ll:confidence-check` - 2026-05-29T22:09:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42d54349-d303-49ce-a074-ab7903bdc951.jsonl`

---

**Open** | Created: 2026-05-29 | Priority: P3
