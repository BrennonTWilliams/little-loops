---
discovered_date: 2026-03-25
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 71
---

# BUG-885: Built-in loops missing after pip install

## Summary

After installing little-loops via `pip install` (non-editable) and running `/ll:init`, `ll-loop list` shows no loops and `ll-loop run <builtin-name>` fails with `FileNotFoundError`. The `loops/` directory is not packaged into the wheel, and `get_builtin_loops_dir()` resolves the wrong path when the package is installed normally.

## Steps to Reproduce

1. On a fresh machine: `pip install little-loops` (or `pip install ./scripts` without `-e`)
2. Run `/ll:init` and complete setup
3. Run `ll-loop list` → shows nothing
4. Run `ll-loop run issue-refinement` → `FileNotFoundError: Loop not found: issue-refinement`

## Root Cause

Two compounding issues in `scripts/little_loops/cli/loop/_helpers.py`:

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `get_builtin_loops_dir()` at line 85

**Issue 1 — Wrong path traversal:**
```python
def get_builtin_loops_dir() -> Path:
    return Path(__file__).parent.parent.parent.parent.parent / "loops"
```
In an editable install, this correctly navigates 5 levels up from `_helpers.py` to the repo root then into `loops/`. In a normal install, `__file__` is inside `site-packages/little_loops/cli/loop/`, and 5 `.parent` traversals land outside the package entirely.

**Issue 2 — `loops/` not packaged:**
`scripts/pyproject.toml` only bundles `little_loops/` (inside `scripts/`):
```toml
[tool.hatch.build.targets.wheel]
packages = ["little_loops"]
```
The `loops/` directory lives at the repo root (outside `scripts/`), so it is never included in the wheel.

## Current Behavior

- `ll-loop list` shows an empty list after a standard `pip install`
- `ll-loop run <any-builtin-name>` raises `FileNotFoundError`
- Only affected users: those who install via `pip install` (non-editable). Editable installs (`pip install -e ./scripts`) work because `__file__` still points to the source tree.

## Expected Behavior

After `pip install little-loops`, `ll-loop list` shows all built-in loops tagged `[built-in]` and `ll-loop run <builtin-name>` works without any setup.

## Motivation

Built-in loops are a key onboarding feature (FEAT-270). The cold-start problem they were designed to solve persists for any user who installs from PyPI or a standard wheel, which is the primary distribution path.

## Proposed Solution

Move `loops/` inside the Python package so it is automatically included in the wheel, then fix the path resolution to match:

1. Move `loops/` from repo root to `scripts/little_loops/loops/`
2. Update `get_builtin_loops_dir()` to use 3 parents instead of 5:
   ```python
   def get_builtin_loops_dir() -> Path:
       return Path(__file__).parent.parent.parent / "loops"
   ```
   (`_helpers.py` → `loop/` → `cli/` → `little_loops/` → `loops/`)
3. Verify `pyproject.toml` wheel packaging now implicitly includes `little_loops/loops/**` via `packages = ["little_loops"]` — no explicit `include` change needed

### Alternative (if move is undesirable)

Use `importlib.resources` / `importlib.metadata` to resolve the package data path, or add an explicit `include` rule in `pyproject.toml` referencing the root `loops/` dir and use `pkg_resources`/`importlib.resources` to access it.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — fix `get_builtin_loops_dir()` path (3 parents, not 5)
- `scripts/pyproject.toml` — verify wheel includes `little_loops/loops/` (likely automatic after move)
- `loops/` → `scripts/little_loops/loops/` — move directory

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:90` — `cmd_list()` calls `get_builtin_loops_dir()` directly, globs `*.yaml` from it
- `scripts/little_loops/cli/loop/run.py:35` — `cmd_run()` constructs path directly as `get_builtin_loops_dir() / f"{loop_name}.yaml"` (bypasses `resolve_loop_path()`)
- `scripts/little_loops/cli/loop/config_cmds.py:45` — `cmd_install()` calls it directly to build source path for copying a built-in loop into `.loops/`
- `scripts/little_loops/cli/loop/_helpers.py:107` — `resolve_loop_path()` calls `get_builtin_loops_dir()` as a fallback when name not found in project `loops_dir`; `load_loop()` (line 114) and `load_loop_with_spec()` (line 128) both call `resolve_loop_path()`, making them indirect callers

### Similar Patterns
- `scripts/little_loops/cli/loop/_helpers.py:90-111` — `resolve_loop_path()` fallback chain; only the final fallback (line 107) calls `get_builtin_loops_dir()` — no change needed here beyond the path fix

### Tests
- `scripts/tests/test_builtin_loops.py` — update path expectations after move
- `scripts/tests/test_ll_loop_commands.py` — patches `little_loops.cli.loop.info.get_builtin_loops_dir` at lines 150, 262, 290, 313; mock return values pointing to old path will need updating to reflect new location

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — verify any path references (note: not `loops.md`)
- `loops/README.md` → `scripts/little_loops/loops/README.md` — update after move to new location

### Configuration
- `scripts/pyproject.toml:76-78` — has both `packages = ["little_loops"]` AND `include = ["little_loops/**", "LICENSE"]`; the explicit `include` pattern confirms that after moving `loops/` into `scripts/little_loops/loops/`, all files will be packaged automatically — no additional `include` rule needed

### Note: `oracles/` Subdirectory
- `loops/oracles/oracle-capture-issue.yaml` exists but none of the current lookup logic (globs or direct path construction) traverses subdirectories — only top-level `*.yaml` files are discoverable. This behavior continues after the move and is pre-existing, not introduced by this fix.

## Implementation Steps

1. Move `loops/` to `scripts/little_loops/loops/` (preserve `oracles/` subdir and `README.md`)
2. Update `get_builtin_loops_dir()` to use 3 `.parent` traversals
3. Run tests to confirm `test_builtin_loops.py` and `test_ll_loop_commands.py` pass
4. Do a test `pip install ./scripts` (non-editable) in a venv and verify `ll-loop list` shows built-ins
5. Update `loops/README.md` path references if needed

## Impact

- **Priority**: P2 - Affects all non-editable installs; silently breaks the primary onboarding feature
- **Effort**: Small - Path fix is trivial; directory move is mechanical
- **Risk**: Low - Additive packaging change; editable installs continue to work
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `packaging`, `install`, `captured`

---

## Session Log
- `/ll:confidence-check` - 2026-03-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9205761a-6cf9-4d88-ad9c-044132ce6444.jsonl`
- `/ll:refine-issue` - 2026-03-25T17:14:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e1845c1-50e0-42b1-b711-63e54cda9cc6.jsonl`
- `/ll:format-issue` - 2026-03-25T17:11:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7dd7859e-e6b7-48ad-8887-66c0ff4ff68b.jsonl`
- `/ll:capture-issue` - 2026-03-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/af344de7-e693-4b47-b015-a17dc5930e72.jsonl`

---

## Status

**Open** | Created: 2026-03-25 | Priority: P2
