# FEAT-270: Ship Built-in Loops with Plugin - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-270-ship-built-in-loops-with-plugin.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

### Key Discoveries
- `resolve_loop_path()` at `cli.py:635-651` only searches `.loops/` relative to cwd — no plugin fallback
- `cmd_list()` at `cli.py:903-930` only searches project `.loops/` directory
- No `loops/` directory exists at plugin root
- The only `__file__`-based path resolution in the package is `logo.py:17`: `Path(__file__).parent.parent.parent / "assets"`
- `pyproject.toml:72-74` wheel build only includes `little_loops/**` and `LICENSE`
- Loop suggestions already exist in `.claude/loop-suggestions/suggestions-2026-02-02.yaml` with 4 well-tested loop definitions
- Paradigm files need `paradigm` field but no `initial` field — auto-compiled at runtime (`cli.py:767-772`)

### Patterns to Follow
- Existing resolution priority: (1) direct path, (2) `.loops/<name>.fsm.yaml`, (3) `.loops/<name>.yaml`
- Loop YAML format for imperative: `paradigm`, `name`, `description`, `steps`, `until`, `max_iterations`
- Loop YAML format for invariants: `paradigm`, `name`, `description`, `constraints`, `maintain`, `max_iterations`
- Test pattern: `monkeypatch.chdir(tmp_path)`, patch `sys.argv`, call `main_loop()` directly

## Desired End State

After implementation:
1. `ll-loop list` shows built-in loops tagged with `[built-in]`
2. `ll-loop run <built-in-name>` works without any user setup
3. `ll-loop install <name>` copies a built-in loop to `.loops/` for customization
4. Project-local loops override built-in loops of the same name
5. Built-in loops are bundled at `loops/` in the plugin root (not inside the Python package)

### How to Verify
- `ll-loop list` shows built-in loops when no `.loops/` exists
- `ll-loop run pre-pr-checks --dry-run` resolves to built-in loop
- Project-local `.loops/pre-pr-checks.yaml` overrides the built-in
- `ll-loop install pre-pr-checks` creates `.loops/pre-pr-checks.yaml`
- All existing tests pass

## What We're NOT Doing

- Not adding built-in loops to the Python wheel/package (they live at plugin root level like `templates/`)
- Not changing `.loops/` runtime state paths (`.running/`, `.state.json`, etc.)
- Not adding configuration options — discovery is automatic
- Not changing `ll-loop compile` behavior
- Not modifying the plugin manifest (plugin.json) — loops are discovered by CLI, not by Claude Code runtime

## Solution Approach

1. Create `loops/` directory at the plugin root with 5 built-in loop YAML files
2. Add a `get_plugin_root()` utility function to find the plugin root via `__file__` traversal
3. Extend `resolve_loop_path()` to search `loops/` in the plugin root as a final fallback
4. Extend `cmd_list()` to also list built-in loops with `[built-in]` tag
5. Add `cmd_install()` subcommand to copy built-in loops to project `.loops/`
6. Add tests for all new behavior

## Implementation Phases

### Phase 1: Create Built-in Loop YAML Files

#### Overview
Create 5 built-in loop files at `loops/` in the plugin root.

#### Changes Required

**Directory**: `loops/` (new, at plugin root)

Files to create:

1. `loops/issue-readiness-cycle.yaml` — imperative paradigm, processes issues through ready then manage
2. `loops/pre-pr-checks.yaml` — invariants paradigm, code quality + tests before PR
3. `loops/issue-verification.yaml` — invariants paradigm, verify + normalize issues
4. `loops/codebase-scan.yaml` — imperative paradigm, scan → verify → prioritize
5. `loops/quality-gate.yaml` — invariants paradigm, lint + types + format + tests

Based on the proven suggestions from `.claude/loop-suggestions/suggestions-2026-02-02.yaml`, adapted for general use (removing project-specific paths).

#### Success Criteria

**Automated Verification**:
- [ ] Each YAML file parses with `yaml.safe_load()` without errors
- [ ] Each loop compiles via `compile_paradigm()` without errors
- [ ] Each compiled loop passes `validate_fsm()` without ERROR-severity issues

---

### Phase 2: Add Plugin Root Discovery + Update Resolution Logic

#### Overview
Add a utility to find the plugin root directory, then extend `resolve_loop_path()` to search built-in loops as a fallback.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**:
1. Add a helper to compute the plugin root: `Path(__file__).parent.parent.parent` (same pattern as `logo.py:17`)
2. Extend `resolve_loop_path()` to add step 4: check `<plugin_root>/loops/<name>.yaml`

```python
# After existing step 3 (paradigm in .loops/)
# Try built-in loops from plugin directory
builtin_path = Path(__file__).parent.parent.parent / "loops" / f"{name_or_path}.yaml"
if builtin_path.exists():
    return builtin_path
```

Resolution priority becomes:
1. Direct path (existing)
2. `.loops/<name>.fsm.yaml` (existing)
3. `.loops/<name>.yaml` (existing)
4. `<plugin_root>/loops/<name>.yaml` (new — built-in fallback)

#### Success Criteria

**Automated Verification**:
- [ ] `resolve_loop_path("pre-pr-checks")` returns built-in path when no `.loops/` exists
- [ ] Project-local `.loops/pre-pr-checks.yaml` takes priority over built-in
- [ ] `FileNotFoundError` still raised for truly missing loops
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`

---

### Phase 3: Update `cmd_list` to Show Built-in Loops

#### Overview
Extend the `list` subcommand to also discover and display built-in loops, tagged with `[built-in]`.

#### Changes Required

**File**: `scripts/little_loops/cli.py` (in `cmd_list()`)
**Changes**: After listing project loops, also scan `<plugin_root>/loops/*.yaml` and show any that aren't overridden by project loops.

```python
# After project loop listing, add built-in discovery
builtin_dir = Path(__file__).parent.parent.parent / "loops"
if builtin_dir.exists():
    builtin_files = sorted(builtin_dir.glob("*.yaml"))
    project_names = {p.stem for p in yaml_files} if yaml_files else set()
    new_builtins = [f for f in builtin_files if f.stem not in project_names]
    if new_builtins:
        for path in new_builtins:
            print(f"  {path.stem}  [built-in]")
```

#### Success Criteria

**Automated Verification**:
- [ ] `ll-loop list` shows built-in loops with `[built-in]` tag
- [ ] Project-local loops with same name hide the built-in (no duplicate)
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`

---

### Phase 4: Add `ll-loop install` Subcommand

#### Overview
Add an `install` subcommand that copies a built-in loop to `.loops/` for customization.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**:
1. Add `install` to `known_subcommands`
2. Add argument parser for `install` subcommand
3. Implement `cmd_install()` function

```python
install_parser = subparsers.add_parser("install", help="Copy built-in loop for customization")
install_parser.add_argument("loop", help="Built-in loop name to install")
```

The function copies from `<plugin_root>/loops/<name>.yaml` to `.loops/<name>.yaml`, creating `.loops/` if needed.

#### Success Criteria

**Automated Verification**:
- [ ] `ll-loop install pre-pr-checks` creates `.loops/pre-pr-checks.yaml`
- [ ] Error if loop already exists in `.loops/`
- [ ] Error if built-in loop name doesn't exist
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- `resolve_loop_path` with built-in fallback
- `cmd_list` showing built-in loops
- `cmd_install` copying loops
- Priority: project-local overrides built-in

### Integration Tests
- Full `ll-loop list` with mixed project and built-in loops
- `ll-loop run <built-in> --dry-run`
- `ll-loop install` then `ll-loop list` shows it as project loop

## References

- Original issue: `.issues/features/P3-FEAT-270-ship-built-in-loops-with-plugin.md`
- Resolution logic: `scripts/little_loops/cli.py:635-651`
- List command: `scripts/little_loops/cli.py:903-930`
- Path pattern: `scripts/little_loops/logo.py:17`
- Loop suggestions: `.claude/loop-suggestions/suggestions-2026-02-02.yaml`
- Test patterns: `scripts/tests/test_ll_loop_parsing.py:169+`
