---
id: BUG-2276
type: BUG
priority: P4
status: open
captured_at: "2026-06-24T00:00:00Z"
discovered_date: 2026-06-24
discovered_by: capture-issue
relates_to: [BUG-2275, FEAT-2274, BUG-885]
labels: [bug, packaging, assets, install, path-resolution]
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
- `scripts/little_loops/logo.py` — `get_logo()` path resolution.
- `scripts/pyproject.toml` — bundle the logo asset (git mv or force-include).

### Similar Patterns
- BUG-2275 — `hooks/` package data excluded from the wheel (same class).
- FEAT-2274 — `templates/` packaging (extend its scope to `assets/`).
- BUG-885 — moved `loops/` in-package; the precedent.

### Tests
- `scripts/tests/` — assert `get_logo()` resolves the bundled asset when
  `__file__` is monkeypatched to a non-editable path.

## Implementation Steps

1. Move/force-include the logo asset into the wheel.
2. Repoint `get_logo()` to the in-package location.
3. Add a test for the non-editable resolution path.
4. Build the wheel; assert `unzip -l dist/*.whl | grep ll-cli-logo.txt`.

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
