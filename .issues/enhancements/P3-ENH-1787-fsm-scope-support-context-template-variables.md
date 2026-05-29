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
- `scripts/little_loops/cli/loop/run.py` — call `resolve_scope()` at line ~264 before `lock_manager.acquire()`
- `scripts/little_loops/cli/loop/_helpers.py` — call `resolve_scope()` in `run_background()` pre-flight check
- `scripts/little_loops/loops/rn-refine.yaml` — add `scope: ["${context.plan_file}"]`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` also calls `run_background()`; covered by the `_helpers.py` change

### Similar Patterns
- Context variable interpolation already exists in `action:` fields via the FSM runner — scope resolution follows the same pattern
- Template resolution in `scripts/little_loops/fsm/executor.py` — check for existing variable expansion utilities to reuse

### Tests
- `scripts/tests/test_concurrency.py` — add `test_resolve_scope_static`, `test_resolve_scope_with_context_var`, `test_resolve_scope_unresolved_var`, `test_resolve_scope_mixed`
- `scripts/tests/test_cli_loop_background.py` — add `test_scope_resolution_before_spawn`: two `run_background()` calls with different context values should not conflict
- `scripts/tests/test_cli_loop_run.py` — add integration test: two foreground runs with disjoint scopes don't conflict

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — document template variable support in scope section
- `docs/reference/CLI.md` — update `ll-loop run` scope documentation

### Configuration
- N/A

## Implementation Steps

1. Add `resolve_scope()` to `scripts/little_loops/fsm/concurrency.py`
2. Wire resolution into `cmd_run()` in `run.py` before the lock acquisition block
3. Wire resolution into `run_background()` in `_helpers.py` before the pre-flight check
4. Add `scope: ["${context.plan_file}"]` to `rn-refine.yaml`
5. Add unit tests for `resolve_scope()` in `test_concurrency.py`
6. Add integration test in `test_cli_loop_background.py` for scope resolution before spawn
7. Run existing concurrency and background tests to verify no regressions

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

## Session Log
- `/ll:capture-issue` - 2026-05-29T06:08:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b88328d9-b43a-4afd-b941-7bc140700c24.jsonl`

---

**Open** | Created: 2026-05-29 | Priority: P3
