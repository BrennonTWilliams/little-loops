---
id: BUG-1008
type: BUG
priority: P2
discovered_date: 2026-04-09
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# BUG-1008: resolve_fragments() missing fallback to built-in loops dir

## Summary

When a user's loop file imports `lib/common.yaml` (e.g. via `fragments: [lib/common.yaml]`),
`resolve_fragments()` resolves the path relative to the loop file's directory — producing
`.loops/lib/common.yaml`. Because `lib/` only exists inside the little-loops package
(`scripts/little_loops/loops/lib/`), not the user's project, a `FileNotFoundError` fires
immediately with no fallback attempted. `resolve_loop_path()` already handles this pattern
for loop files, but `resolve_fragments()` has no equivalent fallback.

## Current Behavior

```
FileNotFoundError: Fragment library not found: lib/common.yaml
  (checked '.loops/lib/common.yaml')
```

User-facing impact: any loop file that imports built-in fragment libraries via a relative
`lib/` path is completely unusable until the user manually copies the library into their
project directory.

## Expected Behavior

`resolve_fragments()` should fall back to the built-in loops dir
(`scripts/little_loops/loops/`) when the path is not found relative to the loop file's
directory — matching the existing behavior of `resolve_loop_path()`.

## Motivation

Built-in fragment libraries like `lib/common.yaml` are distributed inside the package for
shared reuse. Without the fallback, any loop that imports them is broken in user projects,
even though the libraries ship with every install.

## Root Cause

- **File**: `scripts/little_loops/fsm/fragments.py`
- **Anchor**: `in resolve_fragments()` at lines 91–97 (confirmed)
- **Cause**: After computing `lib_path = loop_dir / import_path`, the code raises
  `FileNotFoundError` immediately if the path doesn't exist. No fallback to
  `_BUILTIN_LOOPS_DIR / import_path` is attempted, unlike `resolve_loop_path()`.

```python
# Current (broken)
lib_path = loop_dir / import_path
if not lib_path.exists():
    raise FileNotFoundError(...)   # no fallback attempted
```

## Proposed Solution

1. Add a module-level constant in `fragments.py` before the `_deep_merge` function (around line 88):
   ```python
   _BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "loops"
   ```
   (`fragments.py` is at `little_loops/fsm/fragments.py`, so `parent.parent` = `little_loops/`,
   giving `little_loops/loops` — same target as `get_builtin_loops_dir()` in `scripts/little_loops/cli/loop/_helpers.py:88`, which uses 3 parents from its deeper path.)

2. In `resolve_fragments()`, fall back to the builtin dir before raising:
   ```python
   lib_path = loop_dir / import_path
   if not lib_path.exists():
       builtin_path = _BUILTIN_LOOPS_DIR / import_path
       if builtin_path.exists():
           lib_path = builtin_path
       else:
           raise FileNotFoundError(
               f"Fragment library not found: {import_path} "
               f"(checked '{loop_dir / import_path}' and '{builtin_path}')"
           )
   ```

No callers need to change — `validation.py:482` calls `resolve_fragments(data, path.parent)`
and will automatically benefit from the fallback.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/fragments.py` — add `_BUILTIN_LOOPS_DIR` constant and fallback logic in `resolve_fragments()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py:482` — calls `resolve_fragments(data, path.parent)`, benefits automatically

### Similar Patterns
- `scripts/little_loops/cli/loop/_helpers.py:88` — `get_builtin_loops_dir()` returns `Path(__file__).parent.parent.parent / "loops"` (note: 3 parents from `cli/loop/`; from `fsm/` use only 2)
- `scripts/little_loops/cli/loop/_helpers.py:93` — `resolve_loop_path()` shows the 4-step fallback chain: local → `.fsm.yaml` → `.yaml` → builtin; fragment fallback needs only: local → builtin → raise

### Tests
- `scripts/tests/test_fsm_fragments.py:300` — class is `TestResolveFragmentsImport` (not `TestResolveFragmentsWithImports`); add new test method here
- Template: `test_missing_import_file_raises_filenotfounderror` at line 340 — inverse of the new test (same structure, no `pytest.raises`, passes `tmp_path` as `loop_dir` **without** creating `tmp_path/lib/common.yaml`, asserts `shell_exit` fragment resolved via builtin)
- Built-in `lib/common.yaml` defines: `shell_exit`, `retry_counter`, `llm_gate`, `numeric_gate` — use `shell_exit` in assertion

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py:340-348` (`test_missing_import_file_raises_filenotfounderror`) — update: after the fix the error message includes both checked paths; broaden the `match=` assertion (e.g. `match=r"missing\.yaml.*builtin|checked.*missing\.yaml"`) to verify the new two-path format [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:1675` — states "copy or symlink the library" as the workaround for built-in lib imports; this instruction becomes incorrect after the fix (automatic fallback makes manual copying unnecessary) [Agent 2 finding]

### Configuration
- N/A - no configuration changes required

## Implementation Steps

1. Add `_BUILTIN_LOOPS_DIR` module-level constant to `fragments.py`
2. Add fallback logic in `resolve_fragments()` after the initial `lib_path` check
3. Add unit test confirming built-in lib resolution when local path is absent
4. Verify with `ll-loop validate` on a loop that imports `lib/common.yaml`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/guides/LOOPS_GUIDE.md:1675` — remove "copy or symlink the library" workaround instruction; replace with a note that `lib/common.yaml` and other built-in fragment libraries resolve automatically
6. Update `scripts/tests/test_fsm_fragments.py:340-348` — broaden `match=` in `test_missing_import_file_raises_filenotfounderror` to assert the new two-path error message includes both the local and builtin checked paths

## Impact

- **Priority**: P2 — Any loop importing built-in fragment libraries is broken in user projects
- **Effort**: Small — Single file change, ~10 lines
- **Risk**: Low — Purely additive; existing behavior (local path wins) is unchanged
- **Breaking Change**: No

## Steps to Reproduce

1. Create a loop file in a user project (e.g. `.loops/my-loop.yaml`) that includes `fragments: [lib/common.yaml]`
2. Run `ll-loop validate my-loop`
3. Observe: `FileNotFoundError: Fragment library not found: lib/common.yaml`

## Error Messages

```
FileNotFoundError: Fragment library not found: lib/common.yaml (checked '.loops/lib/common.yaml')
```

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM module structure and resolution patterns |
| `docs/reference/API.md` | `resolve_fragments()` public API |

## Labels

`bug`, `fsm`, `fragments`, `path-resolution`, `captured`

## Status

**Open** | Created: 2026-04-09 | Priority: P2

---

## Session Log
- `/ll:confidence-check` - 2026-04-09T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1fba563-25de-457a-8a36-60a62fb88a99.jsonl`
- `/ll:wire-issue` - 2026-04-09T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/loop-viz-recursive-refine.jsonl`
- `/ll:refine-issue` - 2026-04-09T05:31:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa2f7fcc-7a9a-4554-8835-7b3ae6bbabe4.jsonl`
- `/ll:format-issue` - 2026-04-09T05:28:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/856a40eb-26de-4b04-8d33-182ff2ffc08d.jsonl`
- `/ll:capture-issue` - 2026-04-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de13387d-dae4-488b-861a-ea1d6bb4a2aa.jsonl`
