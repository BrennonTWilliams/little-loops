---
id: BUG-3179
type: BUG
title: 'python -m build fails on main: hatchling rejects readme = ''../README.md'''
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T03:55:13Z'
relates_to:
- BUG-3177
blocks:
- BUG-3177
decision_needed: false
testable: true
learning_tests_required:
- hatchling
---

# BUG-3179: python -m build fails on main: hatchling rejects readme = '../README.md'

## Summary

`python -m build --wheel scripts/` fails on main with `ValueError: Readme path must be within the project directory: ../README.md`.

## Root Cause

`scripts/pyproject.toml` sets `readme = "../README.md"` (README.md lives at the repo root, outside `scripts/`, the packaging project directory) and `requires = ["hatchling"]` with no version pin. The PEP 517 isolated build environment resolves the latest hatchling (1.31.0 observed), whose metadata validation rejects a readme path that escapes the project directory via `../`.

## Steps to Reproduce

Direct:
```
python -m build --wheel --outdir /tmp/dist scripts/
```
fails with the ValueError above, before any package code is touched.

Via the test suite:
```
PYTEST_INTEGRATION=1 python -m pytest scripts/tests/test_wheel_smoke.py
```
already fails at the `installed_venv` fixture's wheel-build step (`scripts/tests/test_wheel_smoke.py:44` `assert result.returncode == 0`), before any of that file's actual assertions run. This blocks every test in `TestWheelSmoke`, not just new ones.

## Impact

Blocks any workflow that needs to build/install the wheel non-editable, including:
- `TestWheelSmoke`'s whole class (gated on `PYTEST_INTEGRATION=1`, so not caught by the default fast suite — silently broken until someone runs the integration marker)
- BUG-3177's Implementation Step 1 ("Reproduce in a clean venv against a built wheel — this is the acceptance test and does not exist today")
- Any future packaging verification that assumes a wheel can be built at all

Discovered 2026-08-14 while proving the `hatchling` learning-test target for BUG-3177's confidence check; proof recorded at `.ll/learning-tests/hatchling.md` (2 failing assertions specifically document this).

This is a pre-existing defect, not caused by BUG-3177 or any other in-flight issue — it blocks BUG-3177's acceptance test but is independent of that issue's own changes.

## Current Behavior

`python -m build --wheel scripts/` aborts during metadata validation, before any
file is collected into a distribution. No wheel or sdist is produced. Because the
only test that would catch this (`TestWheelSmoke`) is gated behind
`PYTEST_INTEGRATION=1`, the default `python -m pytest scripts/tests/` suite passes
green while the package is unbuildable.

## Expected Behavior

`python -m build --wheel scripts/` exits 0 against a clean isolated build
environment with no version pin needed to avoid the failure, and
`PYTEST_INTEGRATION=1 python -m pytest scripts/tests/test_wheel_smoke.py` runs its
assertions rather than dying in the fixture.

## Motivation

little-loops ships to PyPI as `pip install little-loops`; an unbuildable wheel means
no release can be cut at all. The defect is currently invisible to the enforced test
suite, so it will stay broken until someone happens to run the integration marker or
attempt a release. It additionally blocks BUG-3177, whose entire acceptance test is
"install the wheel into a clean venv and check the prompt surface."

## Proposed Solution

Option B (see the decision under Codebase Research Findings below): duplicate
`README.md` into `scripts/README.md` following the existing `LICENSE` precedent, and
point `readme` at the local copy so no path escapes the packaging root. Add a drift
guard so the duplicate cannot silently diverge from the repo-root original.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

**Option A**: Pin `hatchling` in `[build-system].requires` to a version that still accepts a `readme` path outside the project directory. Would need the issue-ID + failure-mode + proof-artifact comment convention already used for `anthropic`/`psutil`/`ruff`/`mcp` pins in `scripts/pyproject.toml` (see Integration Map → Conventions in Force).

> **Verified 2026-08-15**: no bisection needed — `requires = ["hatchling==1.27.0"]` builds
> successfully with `readme = "../README.md"` left unchanged (minimal-repro proof). So Option A
> is *viable*, contrary to the "unconfirmed — not yet identified" note above. It remains
> non-preferred: it freezes the build backend to dodge a validation upstream added deliberately,
> and leaves the escaping path latent to resurface at the next unpin. Keep it in reserve as a
> one-line temporary unblock if Option B proves larger than expected.

**Option B**: Bring `README.md` inside the packaging project directory (`scripts/`) so `readme` never needs a `../`-escaping path. This matches the only precedent this codebase has for the same class of problem: every prior "package needs a repo-root file" case was resolved by `git mv`-ing the file into `scripts/little_loops/...`, never a build-time copy or symlink (FEAT-2274, four such moves — see Integration Map → Conventions in Force). The direct analogue already exists for `LICENSE`, which is physically duplicated at `scripts/LICENSE` and referenced with a plain (non-escaping) path via `include = ["little_loops/**", "LICENSE"]` (`scripts/pyproject.toml:177`) — no `git mv` precedent duplicates a file outside `little_loops/` itself, so whether `README.md` should live at `scripts/README.md` (duplicate, `LICENSE`-style) or move fully into `scripts/little_loops/` is unresolved and would need a decision on which precedent it follows more closely.

**Option C**: Switch `readme` from the plain string form to the table form (`{ file = "...", content-type = "..." }`).

> **Ruled out 2026-08-15**: the proof-of-concept this option called for was run.
> `readme = { file = "../README.md", content-type = "text/markdown" }` fails with the
> *identical* `ValueError: Readme path must be within the project directory: ../README.md`.
> Validation is on the resolved path regardless of scalar-vs-table spelling, exactly as the
> "nothing indicates a different code path" reasoning suspected. **Do not spend time here.**

> **Selected: Option B** — bring the readme inside `scripts/`. It is the only option with a
> direct, repeated precedent in this codebase (FEAT-2274's four `git mv` moves, plus the
> existing `LICENSE` handling), it makes the two cross-packaging-boundary files (`LICENSE`,
> `README.md`) consistent rather than leaving them handled two disagreeing ways, and it does
> not leave the project exposed to a future hatchling release re-breaking the build the way
> Option A's pin eventually will. Option A is verified-viable and held in reserve as a
> temporary unblock only; Option C is dead.

**Open sub-decision within Option B** (flagged in the option text above, still unresolved):
whether `README.md` becomes a *duplicate* at `scripts/README.md` (following the `LICENSE`
precedent, which duplicates rather than moves) or moves fully into `scripts/little_loops/`
(following the FEAT-2274 `git mv` precedent). These precedents point different directions.
Recommend the `LICENSE` shape — `scripts/README.md` as a duplicate — because the repo-root
`README.md` is the GitHub landing page and cannot move. A duplicate needs a drift guard; see
Implementation Steps.

**Note for implementers coordinating with BUG-3177**: hatchling's
`[tool.hatch.build.targets.wheel.force-include]` *can* reach outside the project directory
(proven under BUG-3177 — `"../skills" = "little_loops/skills"` builds fine). That does **not**
rescue this bug: `readme` is a metadata field validated before/independently of file
inclusion, so force-include cannot satisfy it.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Files to Modify
- `scripts/pyproject.toml` — the fix candidates are `readme = "../README.md"` (line 9, escapes the `scripts/` packaging root) and `requires = ["hatchling"]` (line 2, unpinned)

### Dependent Files (Callers/Importers)
- `scripts/tests/test_wheel_smoke.py:49` — `assert result.returncode == 0` in the class-scoped `installed_venv` fixture is the exact assertion this bug currently fails (issue text cites line 44; the fixture has since shifted — current line is 49, still the same `python -m build --wheel` call at `test_wheel_smoke.py:30-37`)
- `.ll/learning-tests/hatchling.md` and `.ll/learning-tests/raw/hatchling.txt` — proof artifacts already document this exact failure (2 failing assertions) and will need re-verification once a fix lands

### Conventions in Force
- Cross-packaging-boundary files are handled two different, disagreeing ways in this repo today: `LICENSE` is physically duplicated into `scripts/LICENSE` and picked up via `include = ["little_loops/**", "LICENSE"]` (`scripts/pyproject.toml:177`), while `README.md` is referenced across the boundary with an escaping `../` path (`scripts/pyproject.toml:9`) — the `LICENSE` precedent has no `../` and does not trip hatchling's validation; `README.md` has no local duplicate.
- Every prior instance of "package code/metadata needs a repo-root file inside the wheel" was resolved by `git mv`-ing the file into `scripts/little_loops/...`, never by a symlink, build-time copy, or `[tool.hatch.build.hooks]` plugin — established across four such moves (`templates/`, `assets/ll-cli-logo.txt`, `hooks/prompts/optimize-prompt-hook.md`, `hooks/adapters/codex/hooks.json`) per `.issues/features/P2-FEAT-2274-package-host-agnostic-templates-into-wheel.md:128,224-225,337-348`. No `hatch_build.py`/`BuildHookInterface`/`[tool.hatch.build.hooks.*]` exists anywhere in the repo.
- Dependency pins in `scripts/pyproject.toml` are always accompanied by an issue-ID + failure-mode + proof-artifact comment directly above the pin (`scripts/pyproject.toml:46-51` anthropic, `:52-58` psutil, `:142-145` ruff==0.14.10, `:152-166` mcp==2.0.0) — `[build-system].requires = ["hatchling"]` (`scripts/pyproject.toml:2`) currently has no such comment because it carries no version constraint at all; a hatchling pin would need to match this shape, and `.ll/learning-tests/hatchling.md` already exists as the proof artifact to cite.

### Tests
- `scripts/tests/test_wheel_smoke.py` — `TestWheelSmoke.installed_venv` (`@pytest.mark.slow`, `@pytest.mark.integration`, `PYTEST_INTEGRATION=1`-gated); this is the whole class's blocking fixture
- `scripts/tests/test_package_data_manifest.py` — sibling manifest-completeness test, not integration-gated, unaffected by this bug (asserts against the current possibly-editable install, not a built wheel)

### Documentation
- None identified needing updates for this fix — no doc currently describes the `readme` field's value or the build-system pin.

### Configuration
- `scripts/pyproject.toml` only; no `MANIFEST.in` or root-level `pyproject.toml` exists in the repo.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Signatures
- `installed_venv(self, tmp_path_factory: pytest.TempPathFactory)` — the fixture at `scripts/tests/test_wheel_smoke.py:29-75` whose build step is what currently fails; any fix is verified through this fixture passing.

### Call Path
`installed_venv` invokes `python -m build --wheel` (`scripts/tests/test_wheel_smoke.py:30-37`) against `scripts/pyproject.toml`; the process fails at the `assert result.returncode == 0` on `scripts/tests/test_wheel_smoke.py:49`. The actual validation failure happens inside the resolved `hatchling` package (outside this repo), so `installed_venv` is the nearest in-repo anchor on this call path — the fix changes what `scripts/pyproject.toml` feeds into that external call, not `installed_venv` itself.

### Revision (repo-anchored)

- **Signature-shaped anchor**: `[project] readme = "../README.md"` — `scripts/pyproject.toml:9`; `[build-system] requires = ["hatchling"]` — `scripts/pyproject.toml:2`. These two lines are the entire surface any fix (Option A/B/C) changes.
- **Call Path (repo-anchored)**: `scripts/tests/test_wheel_smoke.py:30-37` (`subprocess.run([sys.executable, "-m", "build", ...], cwd=scripts_dir)`) invokes `python -m build` against `scripts/pyproject.toml`, which fails at `scripts/tests/test_wheel_smoke.py:49` (`assert result.returncode == 0`). The failure originates outside this repo, inside the resolved `hatchling` package's metadata validation (traceback in `.ll/learning-tests/raw/hatchling.txt`) — there is no in-repo function on this call path between `test_wheel_smoke.py:30` and the `pyproject.toml` fields it reads; the fix changes the fields themselves, not code that calls them.

### Types
N/A — this fix does not introduce or modify a data shape; it changes `scripts/pyproject.toml` build configuration only.

### Signatures
N/A — no project-owned Python function/class signature is touched by this fix (see Call Path below for the external library entry point involved).

### Call Path
`python -m build --wheel scripts/` → PEP 517 `pyproject_hooks` build backend hook → `hatchling.build.build_wheel` → `hatchling.metadata.core`'s `readme` property on `MetadataCore` → raises `ValueError: Readme path must be within the project directory: ...` when the resolved `readme` path escapes the project directory via `../` (traceback confirmed in `.ll/learning-tests/raw/hatchling.txt`). Any fix (Options A/B/C in Proposed Solution) must change what reaches this property call, not the property itself — it is external library code, not part of this codebase.

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold is introduced; this is a packaging-configuration correction, not new decision logic.

## Implementation Steps

1. Copy `README.md` to `scripts/README.md` and change `scripts/pyproject.toml:9` to
   `readme = "README.md"` (no `../`). Confirm `include` at `scripts/pyproject.toml:177`
   carries it into the distribution the way `LICENSE` is carried.
2. Add a drift guard. Verified 2026-08-15: **no such guard exists today** — `LICENSE`
   and `scripts/LICENSE` are duplicated with nothing asserting they match (both 1074
   bytes, but unenforced). Add one non-integration-gated pytest test asserting the
   repo-root and `scripts/` copies of *both* `README.md` and `LICENSE` are byte-identical,
   so this fix does not introduce a second silently-divergable duplicate and closes the
   pre-existing `LICENSE` gap at the same time.
3. Leave `[build-system].requires = ["hatchling"]` unpinned. The pin is Option A's
   fallback, not part of this fix; adding both would mask whether the readme change
   actually worked.
4. Verify: `python -m build --wheel --outdir <tmp> scripts/` exits 0 from a clean state
   (no cached isolated-build env), and the built wheel's `METADATA` carries the
   long-description.
5. Verify: `PYTEST_INTEGRATION=1 python -m pytest scripts/tests/test_wheel_smoke.py -v`
   passes end-to-end.
6. Update `.ll/learning-tests/hatchling.md` — flip the previously-failing unpinned-build
   assertion to `pass` and re-record `raw/hatchling.txt`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

1. The chosen fix (per Proposed Solution's Option A/B/C decision) resolves `scripts/pyproject.toml`'s `readme` field and/or `[build-system].requires` pin without any path escaping the `scripts/` packaging root — verified by `python -m build --wheel --outdir <dir> scripts/` exiting 0 from a clean state (no cached isolated-build env).
2. `TestWheelSmoke.installed_venv` (`scripts/tests/test_wheel_smoke.py:29-75`) passes end-to-end, including the build assertion at `scripts/tests/test_wheel_smoke.py:49`, unblocking the rest of the `TestWheelSmoke` class.
3. `.ll/learning-tests/hatchling.md`'s previously-failing assertion (the unpinned-`hatchling` build claim) is re-verified and its `result` updated to `pass`.
4. `PYTEST_INTEGRATION=1 python -m pytest scripts/tests/test_wheel_smoke.py -v` passes.

## Impact

- **Priority**: P2 — the package cannot be built or released at all, and the defect is
  invisible to the enforced test suite. Not P1 only because editable installs (every
  little-loops project on this machine) are unaffected.
- **Effort**: Small — a file copy, a one-line `pyproject.toml` change, and one guard test.
  All three fix options have already been proof-of-concept'd, so no investigation remains.
- **Risk**: Low — packaging metadata only; no package code path changes. The main risk is
  the duplicated README silently diverging, which step 2 guards against.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-15 | Priority: P2 | Blocks: BUG-3177


## Session Log
- `/ll:refine-issue` - 2026-08-15T04:01:23 - `57b2face-63ba-4158-8d18-dd727b2a0aeb.jsonl`
- `/ll:capture-issue` - 2026-08-15T03:55:19 - `49e15b7f-91ee-43ed-876b-a654ebdcd023.jsonl`

## Candidate Fixes

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

See Option A/B/C decision under Proposed Solution → Codebase Research Findings.
