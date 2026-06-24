---
id: BUG-2276
type: BUG
priority: P4
status: open
captured_at: "2026-06-24T00:00:00Z"
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2279
relates_to: [BUG-2275, FEAT-2274, BUG-885]
labels: [bug, packaging, assets, install, path-resolution]
decision_needed: true
---

# BUG-2276: CLI logo asset excluded from the wheel — `get_logo()` silently returns None on non-editable installs

## Summary

`logo.py:get_logo()` reads the ASCII logo from
`Path(__file__).parent.parent.parent / "assets" / "ll-cli-logo.txt"` — the
repo-root `assets/` directory, which is **not** in the pip wheel (`pyproject.toml`
packages only `little_loops/**` + `LICENSE`). On every non-editable
`pip install little-loops`, the path resolves above `site-packages/`, the file
does not exist, and `get_logo()` returns `None`; `print_logo()` is then a silent
no-op. The CLI logo never displays for installed users.

Same root-cause class as the `templates/` cluster (BUG-2271 / BUG-2273 /
FEAT-2274) and BUG-2275 (`hooks/`): *package code reaches outside the package via
`__file__` traversal to read a repo-root asset the wheel does not contain*. This
is the `assets/` instance. Cosmetic, hence P4 — but identical mechanism and
silently masked by editable dev installs.

## Motivation

Installed users never see the CLI logo — `print_logo()` silently no-ops on every non-editable `pip install`. The editable dev install masks the gap, so it goes unnoticed until an end user reports missing output. Fixing this as part of FEAT-2274's packaging sweep avoids another one-off patch for a misplaced repo-root asset.

## Steps to Reproduce

1. `pip install little-loops` (non-editable) into a fresh venv.
2. Run any CLI entry point that calls `print_logo()`.
3. Observe: no logo is printed; `get_logo()` returned `None` because
   `assets/ll-cli-logo.txt` is not on disk relative to the installed package.

## Root Cause

- **File**: `scripts/little_loops/logo.py`
- **Anchor**: `get_logo()` (line 11)

```python
logo_path = Path(__file__).parent.parent.parent / "assets" / "ll-cli-logo.txt"
if logo_path.exists():
    return logo_path.read_text()
return None
```

In an editable install `__file__` points into the source tree, so three parents
up + `assets/` resolves to the repo `assets/` (exists). In a non-editable install
the same traversal lands above `site-packages/`, where `assets/` does not exist.

## Current Behavior

`get_logo()` returns `None` and `print_logo()` is a silent no-op on all
non-editable installs. Works in editable dev installs, masking the bug.

## Expected Behavior

The logo resolves in every install mode (logo displays). At minimum, the asset
ships in the wheel so `Path(__file__).parent / ... / "ll-cli-logo.txt"`
resolves.

## Proposed Solution

`assets/ll-cli-logo.txt` is package data read by package code → it belongs in the
wheel (FEAT-2274's principle). Either:

1. `git mv assets/ll-cli-logo.txt scripts/little_loops/assets/ll-cli-logo.txt`
   (BUG-885 precedent) and repoint `get_logo()` to
   `Path(__file__).parent / "assets" / "ll-cli-logo.txt"`; or
2. `force-include` `assets/` into the wheel and use the shared resolver.

Add `assets/` to FEAT-2274's packaging sweep so it lands with the other
package-data moves.

## Integration Map

### Files to Modify
- `scripts/little_loops/logo.py` — `get_logo()` path resolution (one-line change).
- `scripts/pyproject.toml` — **no change needed for Option 1** (git mv): the existing `include = ["little_loops/**", "LICENSE"]` glob already captures any new `scripts/little_loops/assets/` subdirectory. Option 2 (force-include) would require a manifest edit.

### Dependent Files (Callers/Importers)
- **Zero production callers** — grep of all `scripts/little_loops/` confirms `get_logo()` and `print_logo()` are not imported or called by any live CLI entry point or module; the path fix is self-contained within `logo.py`.
- `scripts/tests/test_ll_loop_execution.py:TestQuietMode.test_quiet_mode_suppresses_logo` — implicit test dependency: asserts `"little loops"` is absent from stdout in `--quiet` mode, which presupposes `print_logo()` would fire in non-quiet mode; however, no entry point currently calls `print_logo()`, so this test's positive precondition is unverified. Ensure this test remains passing after the fix and verify the wiring concern separately.

### Similar Patterns
- BUG-2275 — `hooks/` package data excluded from the wheel (same class).
- FEAT-2274 — `templates/` packaging (extend its scope to `assets/`).
- BUG-885 — moved `loops/` in-package; the precedent.

### Tests
- `scripts/tests/test_ll_loop_execution.py:TestQuietMode.test_quiet_mode_suppresses_logo` — existing quiet-mode test; must remain passing after the path fix.
- New test needed: follow `scripts/tests/test_action.py:TestLoadSkills` patch pattern — `patch("little_loops.logo.Path", return_value=<sim-site-packages-path>)` — to assert `get_logo()` returns the file content when called from a simulated non-editable location.
- Model for fixture shape: `scripts/tests/test_builtin_loops.py` — tests `get_builtin_loops_dir()` after the BUG-885 in-package move using `Path(__file__).parent.parent / "little_loops" / "loops"` to reference the in-package location.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`print_logo()` has zero live callers**: No CLI entry point under `scripts/little_loops/cli/` or `scripts/little_loops/init/cli.py` currently imports or calls `print_logo()` or `get_logo()`. The function is a public API with no integration point. The packaging fix resolves the asset-path bug; wiring `print_logo()` into a CLI entry point is a separate scoping concern.
- **After Option 1 (git mv), the path expression needs only ONE parent, not three**: `logo.py` sits at `scripts/little_loops/logo.py`, so `Path(__file__).parent` already resolves to `scripts/little_loops/` — the sibling `assets/` subdir is reachable with a single parent traversal, identical to the BUG-885 pattern in `scripts/little_loops/fsm/fragments.py:_BUILTIN_LOOPS_DIR` (`Path(__file__).parent.parent / "loops"`).
- **No `importlib.resources` precedent exists**: All asset resolution in `scripts/little_loops/` uses `Path(__file__).parent...` traversal; `importlib.resources.files()` is unused. Option 1 (git mv + path fix) is more consistent with the codebase; Option 2 would introduce a new pattern.
- **Option 2 (force-include) still requires the path expression update**: The current three-parent traversal reaches above `site-packages/` regardless of inclusion strategy; `get_logo()` must be repointed in either option. Option 1 is strictly simpler (one file, one line).
- **`scripts/little_loops/assets/` does not yet exist** and must be created as part of the move.

### Documentation
- N/A — no user-facing documentation references the logo asset path.

### Configuration
- N/A — no configuration files affected; the fix is a move + path update only.

## Implementation Steps

1. **Move asset into package** (BUG-885 precedent): `mkdir -p scripts/little_loops/assets/ && git mv assets/ll-cli-logo.txt scripts/little_loops/assets/ll-cli-logo.txt`. No `pyproject.toml` change needed — the existing `little_loops/**` glob captures the new subdirectory automatically.
2. **Repoint `get_logo()`** in `scripts/little_loops/logo.py:get_logo()`: change `Path(__file__).parent.parent.parent / "assets" / "ll-cli-logo.txt"` → `Path(__file__).parent / "assets" / "ll-cli-logo.txt"` (one parent from `little_loops/logo.py` → `little_loops/`).
3. **Add test** following `scripts/tests/test_action.py:TestLoadSkills` patch pattern: assert `get_logo()` returns the ASCII content when invoked with a simulated non-editable `__file__` path outside the source tree.
4. **Build and verify**: `python -m build && unzip -l dist/*.whl | grep ll-cli-logo.txt` (aligns with ENH-2277's wheel smoke test proposal).

## Impact

- **Priority**: P4 — cosmetic (missing logo); no functional breakage.
- **Effort**: Small — one path + packaging.
- **Risk**: Low.
- **Breaking Change**: No.

## Related

- BUG-2275 — `hooks/` package data (same class, higher severity).
- FEAT-2274 — packaging decision; extend its scope to include `assets/`.
- BUG-885 — precedent for moving consumed assets into the package.
- ENH-2277 — systemic lint + wheel smoke test that would have caught this.

## Labels

`bug`, `packaging`, `assets`, `install`, `path-resolution`

## Status

**Open** | Created: 2026-06-24 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-06-24T23:35:47 - `8a54fdd7-3020-4216-95d6-fd9489d38b88.jsonl`
- `/ll:format-issue` - 2026-06-24T23:25:56 - `7a6b079f-6b9c-4751-8816-e0520ba8c865.jsonl`
