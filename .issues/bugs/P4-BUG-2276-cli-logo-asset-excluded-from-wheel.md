---
id: BUG-2276
type: BUG
priority: P4
status: open
captured_at: '2026-06-24T00:00:00Z'
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2279
relates_to:
- BUG-2275
- FEAT-2274
- BUG-885
labels:
- bug
- packaging
- assets
- install
- path-resolution
decision_needed: false
implementation_order_risk: true
confidence_score: 84
outcome_confidence: 72
score_complexity: 22
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 22
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

> **Selected:** Option 1 (git mv + path fix) — BUG-885 precedent; no `pyproject.toml` change; single-line `get_logo()` fix

2. `force-include` `assets/` into the wheel and use the shared resolver.

Add `assets/` to FEAT-2274's packaging sweep so it lands with the other
package-data moves.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-24.

**Selected**: Option 1 — `git mv` asset into package + path fix

**Reasoning**: Option 1 directly applies the BUG-885 precedent used by two production files (`fsm/fragments.py:_BUILTIN_LOOPS_DIR`, `cli/loop/_helpers.py:824`) — move the asset inside the package where the existing `little_loops/**` wheel glob captures it automatically, then fix the one-line path expression. Option 2 builds entirely from scratch (no `importlib.resources` or `force-include` precedent in the codebase), still requires the same path fix, and would pull unrelated marketing images (`assets/little-loops.jpeg`) into the wheel.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 (git mv + path fix) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option 2 (force-include) | 0/3 | 0/3 | 1/3 | 1/3 | 2/12 |

**Key evidence**:
- Option 1: BUG-885 precedent in `fsm/fragments.py:38` and `cli/loop/_helpers.py:824`; existing `little_loops/**` glob requires zero `pyproject.toml` changes; `TestLoadSkills` patch pattern (`test_action.py`) directly applicable.
- Option 2: No `importlib.resources` or `force-include` anywhere in the codebase; `assets/` directory contains non-package marketing images; path expression must change regardless of inclusion strategy.

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
- `scripts/tests/test_ll_loop_execution.py:TestQuietMode.test_quiet_mode_suppresses_logo` — existing quiet-mode test; must remain passing after the path fix. Won't mechanically break (asserts absence of logo in quiet mode), but is insufficient as a correctness guard since it passes vacuously if `get_logo()` returns `None`.
- New test needed: follow `scripts/tests/test_builtin_loops.py:BUILTIN_LOOPS_DIR` pattern (simpler than Path mocking) — declare `LOGO_PATH = Path(__file__).parent.parent / "little_loops" / "assets" / "ll-cli-logo.txt"` at test module top level, then assert `LOGO_PATH.exists()` and `get_logo()` returns a non-None string containing logo content. No `Path` mock needed; the in-package path resolves correctly from the test file's location in an editable dev install [Agent 3 finding].

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed: no additional test files beyond `test_ll_loop_execution.py` import `logo`, `get_logo`, or `print_logo`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`print_logo()` has zero live callers**: No CLI entry point under `scripts/little_loops/cli/` or `scripts/little_loops/init/cli.py` currently imports or calls `print_logo()` or `get_logo()`. The function is a public API with no integration point. The packaging fix resolves the asset-path bug; wiring `print_logo()` into a CLI entry point is a separate scoping concern.
- **After Option 1 (git mv), the path expression needs only ONE parent, not three**: `logo.py` sits at `scripts/little_loops/logo.py`, so `Path(__file__).parent` already resolves to `scripts/little_loops/` — the sibling `assets/` subdir is reachable with a single parent traversal, identical to the BUG-885 pattern in `scripts/little_loops/fsm/fragments.py:_BUILTIN_LOOPS_DIR` (`Path(__file__).parent.parent / "loops"`).
- **No `importlib.resources` precedent exists**: All asset resolution in `scripts/little_loops/` uses `Path(__file__).parent...` traversal; `importlib.resources.files()` is unused. Option 1 (git mv + path fix) is more consistent with the codebase; Option 2 would introduce a new pattern.
- **Option 2 (force-include) still requires the path expression update**: The current three-parent traversal reaches above `site-packages/` regardless of inclusion strategy; `get_logo()` must be repointed in either option. Option 1 is strictly simpler (one file, one line).
- **`scripts/little_loops/assets/` does not yet exist** and must be created as part of the move.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/OUTPUT_STYLING.md` — "Logo: `scripts/little_loops/logo.py`" section references `assets/ll-cli-logo.txt` (repo-root path); must be updated to `scripts/little_loops/assets/ll-cli-logo.txt` after the `git mv` [Agent 2 finding]

### Configuration
- N/A — no configuration files affected; the fix is a move + path update only.

## Implementation Steps

1. **Move asset into package** (BUG-885 precedent): `mkdir -p scripts/little_loops/assets/ && git mv assets/ll-cli-logo.txt scripts/little_loops/assets/ll-cli-logo.txt`. No `pyproject.toml` change needed — the existing `little_loops/**` glob captures the new subdirectory automatically.
2. **Repoint `get_logo()`** in `scripts/little_loops/logo.py:get_logo()`: change `Path(__file__).parent.parent.parent / "assets" / "ll-cli-logo.txt"` → `Path(__file__).parent / "assets" / "ll-cli-logo.txt"` (one parent from `little_loops/logo.py` → `little_loops/`).
3. **Add test** following `scripts/tests/test_action.py:TestLoadSkills` patch pattern: assert `get_logo()` returns the ASCII content when invoked with a simulated non-editable `__file__` path outside the source tree.
4. **Update `docs/reference/OUTPUT_STYLING.md`**: In the "Logo" section, update the path reference from `assets/ll-cli-logo.txt` to `scripts/little_loops/assets/ll-cli-logo.txt` to reflect the new in-package location [Wiring Phase].
5. **Build and verify**: `python -m build && unzip -l dist/*.whl | grep ll-cli-logo.txt` (aligns with ENH-2277's wheel smoke test proposal).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/OUTPUT_STYLING.md` — "Logo" section references the old `assets/ll-cli-logo.txt` repo-root path; update to `scripts/little_loops/assets/ll-cli-logo.txt` after the `git mv`

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


---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The packaging `git mv assets/ll-cli-logo.txt → scripts/little_loops/assets/ll-cli-logo.txt` is owned by **FEAT-2274**, which explicitly includes `assets/ll-cli-logo.txt` in its scope. Do NOT perform the `git mv` independently here — coordinate with FEAT-2274. BUG-2276 owns: (1) the path fix in `logo.py:get_logo()` (one-line change), (2) the test asserting `get_logo()` resolves from the in-package path, and (3) the `docs/reference/OUTPUT_STYLING.md` update. Related issue: [FEAT-2274].

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-24_

**Readiness Score**: 84/100 → PROCEED with attention to noted concerns
**Outcome Confidence**: 72/100 → below threshold

### Concerns
- FEAT-2274 (open) owns the `git mv assets/ll-cli-logo.txt → scripts/little_loops/assets/ll-cli-logo.txt`. BUG-2276's path fix has no effect until that move lands. Coordinate implementation with or after FEAT-2274.
- Implementation Steps list `git mv` as Step 1, but the Scope Boundary note assigns it to FEAT-2274. Step 1 should be removed or marked as a pre-condition to avoid scope collision.

### Outcome Risk Factors
- Tests are co-deliverables: no existing test validates `get_logo()` returns non-None content. The quiet-mode test (`test_quiet_mode_suppresses_logo`) passes vacuously when `get_logo()` returns None. Implement tests first so correctness is verifiable.
- `assets/ll-cli-logo.txt` still exists at the repo root (never deleted — confirmed in git history from Jan 9 2026). FEAT-2274 owns the `git mv` to `scripts/little_loops/assets/ll-cli-logo.txt`; no creation needed, just relocation. The path fix in `logo.py` cannot be meaningfully tested until that move lands.

## Session Log
- `/ll:confidence-check` - 2026-06-24T00:00:00Z - `b128ec64-1e93-499b-9f80-d41e92fa74d3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-25T01:15:24 - `4d9c6bcd-b580-4f4a-bc4f-3993c0160aa9.jsonl`
- `/ll:wire-issue` - 2026-06-24T23:59:51 - `73a37eb2-f3ec-44e0-ac15-6eae379762fd.jsonl`
- `/ll:decide-issue` - 2026-06-24T23:45:44 - `3a5eb345-fd4d-4bec-870b-28d824f9c27e.jsonl`
- `/ll:refine-issue` - 2026-06-24T23:35:47 - `8a54fdd7-3020-4216-95d6-fd9489d38b88.jsonl`
- `/ll:format-issue` - 2026-06-24T23:25:56 - `7a6b079f-6b9c-4751-8816-e0520ba8c865.jsonl`
