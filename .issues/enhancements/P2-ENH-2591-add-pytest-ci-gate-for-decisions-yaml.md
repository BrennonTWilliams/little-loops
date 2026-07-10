---
id: ENH-2591
title: Add pytest CI gate for `.ll/decisions.yaml` corruption
type: ENH
status: done
priority: P2
parent: ENH-2587
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T22:15:00Z'
completed_at: '2026-07-10T23:57:44Z'
decision_needed: false
labels:
- decisions
- data-integrity
- tooling
- ci
- pytest
size: Small
confidence_score: 97
outcome_confidence: 95
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 25
---

# ENH-2591: Add pytest CI gate for `.ll/decisions.yaml` corruption

## Summary

Add a pytest gate (`scripts/tests/test_decisions_yaml_gate.py`) that fails
the local test suite when `.ll/decisions.yaml` is corrupted. This is the
**CI-side belt** to the pre-commit hook (ENH-2590) and the **catch-all** for
`--no-verify` / non-hook edit paths. Mirrors the canonical shape established
by `scripts/tests/test_policy_builder_node_gate.py:1-72` (FEAT-2390).

The gate is **the project's CI** per `CLAUDE.md` — there is no hosted CI,
so `python -m pytest scripts/tests/` IS the CI command. A failing
`test_decisions_yaml_gate.py` enforces the integrity check on every test run.

## Current Behavior

`.ll/decisions.yaml` is protected by the `ll-verify-decisions` CLI and the
pre-commit hook, but the default local test-suite command does not yet include a
subprocess integration gate that runs the validator as part of pytest.

## Expected Behavior

`python -m pytest scripts/tests/` includes a pytest test file that invokes
`ll-verify-decisions` against the live decisions log and a corrupted OTHE-203
fixture, so YAML corruption fails the project CI/local test suite even when hooks
are bypassed.

## Motivation

Developers can bypass pre-commit validation with `--no-verify` or by editing the
file outside git hook paths; without a pytest gate, those corruptions are not
caught by the project's only CI command.

## Proposed Solution

Create `scripts/tests/test_decisions_yaml_gate.py` as a small subprocess gate:
skip if `ll-verify-decisions` is not installed, assert the current
`.ll/decisions.yaml` validates, and assert an OTHE-203 corrupted `tmp_path`
fixture fails with a stderr reference to `decisions.yaml`. Document the gate in
`docs/reference/CONFIGURATION.md` and optionally cross-link it from the decisions
log guide.

## Parent Issue

Decomposed from ENH-2587: "Guard `.ll/decisions.yaml` with a load-time validation
check on commit/CI"

## Why This Child Exists Standalone

Pytest gates are independently runnable shell-out tests — the canonical
template wraps an external validator into the local test suite. This child
ships a single test file plus its OTHE-203 fixture.

## Acceptance Criteria

- `scripts/tests/test_decisions_yaml_gate.py` exists and shells out to
  `ll-verify-decisions` (or the validator CLI produced by ENH-2589).
- The test passes on the current (repaired) `.ll/decisions.yaml`.
- The test fails when the OTHE-203 fixture is substituted in via `tmp_path`:
  - `rationale: "abc \"\" def"` → `yaml.parser.ParserError`
- The test skips gracefully when `ll-verify-decisions` is not on
  `PATH` (use the `pytest.skip(...)` idiom from
  `scripts/tests/test_policy_builder_node_gate.py:52`).
- A positive + negative case pair exists for OTHE-203 corruption.
- `python -m pytest scripts/tests/test_decisions_yaml_gate.py -v` exits 0
  against the working tree.
- The gate is wired as part of the local test suite's default run
  (`python -m pytest scripts/tests/`).

## Scope Boundaries

- **In scope**: one pytest subprocess gate, the positive/negative OTHE-203
  fixtures, and documentation references to the local gate.
- **Out of scope**: hosted CI/GitHub Actions, changes to validator semantics,
  adding a new pytest marker, changing the pre-commit hook, and the Claude Code
  PreToolUse hook tracked separately by ENH-2592.

## Impact

- **Priority**: P2 — decisions-log corruption can break active required-rule
  governance and readiness checks, but the core validator and pre-commit belt
  already exist.
- **Effort**: Small — add one subprocess pytest gate plus a short documentation
  note, reusing the existing validator CLI and sibling gate patterns.
- **Risk**: Low — read-only validation path; skip guard avoids hard-blocking
  contributors whose editable install is missing the CLI.
- **Breaking Change**: No.

## Files to Modify

- `scripts/tests/test_decisions_yaml_gate.py` (new) — mirror
  `scripts/tests/test_policy_builder_node_gate.py:1-72` shape:
  - No module-level `pytestmark = pytest.mark.gate`; `gate` is not registered
    under `--strict-markers`.
  - `shutil.which("ll-verify-decisions")` skip guard.
  - `tmp_path` fixture for the OTHE-203 corrupted `decisions.yaml`.
  - Positive case (valid file → exit 0).
  - Negative case (corrupted file → exit non-zero, stderr contains the path).
- `docs/reference/CONFIGURATION.md` — note the gate exists and where to
  find it (one paragraph).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Sibling test file already exists at `scripts/tests/test_decisions_yaml_pre_commit_gate.py`**
— added by ENH-2590. That file owns the `OTHE_203_PAYLOAD` and `CLEAN_PAYLOAD`
module-level constants (lines 36-48) and the `_init_git_repo` helper (lines 51-68).
The new pytest gate should mirror these constants locally rather than importing
across files — the codebase convention (per `test_decisions.py:127-132` and
`test_verify_decisions.py:49-58`) is to inline the payload rather than share
fixtures across files.

**`pytest.mark.gate` is NOT registered in `scripts/pyproject.toml`** — the
markers list at `scripts/pyproject.toml:180-185` registers only `integration`,
`slow`, `conformance`, and `no_parallel`. The `addopts` block at
`scripts/pyproject.toml:172-179` includes `--strict-markers` (line 173), so any
test using `pytestmark = pytest.mark.gate` would fail collection with an
unknown-marker error. The canonical skip-when-missing idiom in this
codebase is inline `pytest.skip(...)` (see
`test_policy_builder_node_gate.py:52-57` and
`test_decisions_yaml_pre_commit_gate.py:155-163`). **Drop the
`pytestmark = pytest.mark.gate` line from the implementation snippet below.**

**`subprocess.run` needs an explicit `timeout`** — the sibling
pre-commit gate uses `timeout=60` (`test_decisions_yaml_pre_commit_gate.py:175-181`)
and the canonical template uses `timeout=180` (`test_policy_builder_node_gate.py:62-67`).
The new gate should use `timeout=60` (single-file validator, fast path). Without
`timeout=`, the gate could wedge a worker indefinitely on a hung subprocess.

**`ll-verify-decisions` is already wired** — entry point at
`scripts/pyproject.toml:89` (`ll-verify-decisions = "little_loops.cli:main_verify_decisions"`)
and re-exported in `scripts/little_loops/cli/__init__.py:82, 123`. ENH-2589
resolved during ENH-2590's wiring pass; this dependency is already satisfied
on disk.

**Exit-code contract** — `verify_decisions.py:65-108` returns `0` on clean
files, `1` on any caught `yaml.YAMLError`, `KeyError`, or `ValueError`. On
failure the CLI writes a single-line `ERROR: {log_path}: {ExcClass}: {exc}`
to **stderr** (line 107) — never stdout. The negative-case assertion that
`"decisions.yaml" in result.stderr.lower()` is therefore the correct target.

## Depends On

- **ENH-2589** — `ll-verify-decisions` CLI must exist on `PATH`.

## Blocks

Nothing.

## Implementation Steps

1. Read `scripts/tests/test_policy_builder_node_gate.py:1-72` to extract the
   canonical template (skip-when-missing, subprocess invocation, exit-code
   assertion, OTHE-203 fixture pattern).
2. Create `scripts/tests/test_decisions_yaml_gate.py`:
   ```python
   """Gate: fail the test suite when .ll/decisions.yaml is corrupted.

   Mirrors the policy_builder node gate (FEAT-2390). The validator CLI
   (ENH-2589) must be installed; otherwise skip.
   """
   import shutil
   import subprocess
   from pathlib import Path

   import pytest

   CLI = "ll-verify-decisions"
   REPO_ROOT = Path(__file__).resolve().parents[2]
   OTHE_203_PAYLOAD = (
       "entries:\n"
       "  - id: OTHE-203\n"
       "    type: decision\n"
       '    rationale: "abc "" def"\n'
   )

   @pytest.fixture(scope="module")
   def validator():
       path = shutil.which(CLI)
       if not path:
           pytest.skip(f"{CLI} not installed; install via `pip install -e ./scripts[dev]`")
       return path

   def test_decisions_yaml_loads(validator):
       result = subprocess.run(
           [validator],
           cwd=REPO_ROOT,
           capture_output=True,
           text=True,
           timeout=60,
       )
       assert result.returncode == 0, f"{CLI} failed: {result.stderr}"

   def test_decisions_yaml_rejects_othe_203(validator, tmp_path):
       decisions = tmp_path / ".ll"
       decisions.mkdir()
       (decisions / "decisions.yaml").write_text(OTHE_203_PAYLOAD)
       result = subprocess.run(
           [validator, "--config-root", str(tmp_path)],
           cwd=tmp_path,
           capture_output=True,
           text=True,
           timeout=60,
       )
       assert result.returncode != 0
       assert "decisions.yaml" in result.stderr.lower()
   ```
3. Add one paragraph to `docs/reference/CONFIGURATION.md` referencing the
   new gate.
4. Run the gate: `python -m pytest scripts/tests/test_decisions_yaml_gate.py -v`.
5. Run the full suite: `python -m pytest scripts/tests/`.

### Codebase Research Findings — Implementation Steps

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Implementation snippet corrections:**

1. **Do not add `pytestmark = pytest.mark.gate`**. The `gate` marker is not
   registered in `scripts/pyproject.toml:180-185` and `--strict-markers`
   (`scripts/pyproject.toml:173`) would fail collection. Use inline
   `pytest.skip(...)` instead, matching the canonical template at
   `test_policy_builder_node_gate.py:52-57`.
2. **Add `timeout=60` to both `subprocess.run(...)` calls**. The sibling pre-commit
   gate uses `timeout=60` (`test_decisions_yaml_pre_commit_gate.py:175-181`).
   Without `timeout=`, the gate can wedge a worker indefinitely. Update to:
   ```python
   result = subprocess.run([validator], cwd=REPO_ROOT,
                            capture_output=True, text=True, timeout=60)
   ```
   and:
   ```python
   result = subprocess.run([validator, "--config-root", str(tmp_path)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=60)
   ```
3. **Re-use the OTHE-203 payload constant locally** (don't import across test
   files). Mirror the sibling file's pattern at
   `test_decisions_yaml_pre_commit_gate.py:36-41`:
   ```python
   OTHE_203_PAYLOAD = (
       "entries:\n"
       "  - id: OTHE-203\n"
       "    type: decision\n"
       '    rationale: "abc "" def"\n'
   )
   ```
4. **Optionally append a doc touchpoint to `docs/guides/DECISIONS_LOG_GUIDE.md`**
   (line 512 area) linking to the new test file alongside the existing
   `test_decisions_yaml_pre_commit_gate.py` reference. The guide already
   names ENH-2591 as transport layer #2 (lines 502-505), so the cross-reference
   is the natural completion of that block.

## Integration Map

### Files to Modify
- `scripts/tests/test_decisions_yaml_gate.py` (new) — pytest CI belt; mirrors
  `scripts/tests/test_policy_builder_node_gate.py:1-72` shape. Skips when
  `ll-verify-decisions` is not on `PATH`; otherwise runs the validator against
  the live `.ll/decisions.yaml` (positive case) and against a `tmp_path`
  containing the OTHE-203 corrupted payload (negative case).
- `docs/reference/CONFIGURATION.md` — one-paragraph note under or near
  `### decisions` (lines 774-782), pointing readers at the gate file.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/verify_decisions.py:65-108` — `main_verify_decisions`
  is the subprocess target. Entry point registered at
  `scripts/pyproject.toml:89` as `ll-verify-decisions = "little_loops.cli:main_verify_decisions"`.
- `scripts/little_loops/cli/__init__.py:82, 123` — re-exports
  `main_verify_decisions` in `__all__`.

### Similar Patterns
- `scripts/tests/test_policy_builder_node_gate.py:1-72` — canonical template
  (FEAT-2390). Single test function, inline `pytest.skip(...)` guard,
  `subprocess.run` with `timeout=180`, exit-code + multi-line stdout/stderr
  assertion.
- `scripts/tests/test_decisions_yaml_pre_commit_gate.py:36-48, 147-224` —
  sibling gate shipped by ENH-2590. Owns the `OTHE_203_PAYLOAD` and
  `CLEAN_PAYLOAD` module-level constants (lines 36-41, 43-48). Skip guard
  pattern at lines 155-163 / 194-202 is the closest analog.
- `scripts/tests/conformance/test_host_conformance.py:96-99` — host conformance
  parametrize with per-binary `shutil.which(...)` + `pytest.skip(...)`.

### Tests
- `scripts/tests/test_verify_decisions.py:100-208` — existing direct unit
  tests for the validator's exit-code contract (clean / YAML / Key /
  Value). The new gate complements these by adding a subprocess-out
  integration check.
- `scripts/tests/test_decisions.py:127-163` — direct unit tests of
  `load_decisions` covering the three corruption classes
  (`yaml.YAMLError`, `KeyError`, `ValueError`).

### Documentation
- `docs/reference/CONFIGURATION.md` — needs one-paragraph note (per spec).
- `docs/guides/DECISIONS_LOG_GUIDE.md:485-512` — `## Load-Time Validation`
  section already references ENH-2591 as item 2 of the three transport
  layers (added during ENH-2590's wiring pass). The new gate's doc
  cross-reference should be a `[`link to the test file`](../../scripts/tests/test_decisions_yaml_gate.py)`
  appended after the existing
  `[`link to the pre-commit sibling`](../../scripts/tests/test_decisions_yaml_pre_commit_gate.py)`
  in the "See [`scripts/tests/test_decisions_yaml_pre_commit_gate.py`...]"
  paragraph near line 512.
- `docs/development/TROUBLESHOOTING.md:771-787` — pattern template for a
  "test times out on xdist worker" entry, only if the gate turns out to
  be sensitive to xdist scheduling.

### Configuration
- `scripts/pyproject.toml:180-185` — `[tool.pytest.ini_options].markers` block;
  `gate` is intentionally NOT registered (see Findings above).
- `.pre-commit-config.yaml:6-13` — pre-commit hook from ENH-2590 is the
  complementary belt-and-suspenders transport layer.

## Status

**Open** | Created: 2026-07-10 | Priority: P2 | Parent: ENH-2587 (done) | Depends on: ENH-2589 (done)

## Session Log
- `/ll:manage-issue` - 2026-07-10T23:57:24 - implemented pytest CI belt + doc touchpoints
- `/ll:ready-issue` - 2026-07-10T23:42:27 - `ce7650d8-d6fc-4091-81ae-96aeb2080beb.jsonl`
- `/ll:refine-issue` - 2026-07-10T23:27:53 - `065e102c-1f97-418d-9c9b-03a38bf9a558.jsonl`
- `/ll:issue-size-review` - 2026-07-10T22:15:00 - `61c51949-414d-4865-b102-91b1bc365edd.jsonl`
- `/ll:refine-issue` - 2026-07-10T22:30:00 - `<pending>`

## Resolution

Implemented the pytest CI belt per acceptance criteria:

- **New**: `scripts/tests/test_decisions_yaml_gate.py` — wraps `ll-verify-decisions`
  as a subprocess-asserting gate. `test_decisions_yaml_loads` (positive case,
  exit 0 against live `.ll/decisions.yaml`) + `test_decisions_yaml_rejects_othe_203`
  (negative case, exit ≠ 0 + stderr references `decisions.yaml`). Skips via
  inline `pytest.skip(...)` when the CLI is missing (mirrors the canonical
  template at `scripts/tests/test_policy_builder_node_gate.py:52-57`). No
  `pytestmark = pytest.mark.gate` (the `gate` marker is unregistered under
  `--strict-markers`). Both `subprocess.run` calls use `timeout=60`.
- **Docs**: One paragraph added to `docs/reference/CONFIGURATION.md` under
  `### decisions` referencing the new gate file. Cross-link added to
  `docs/guides/DECISIONS_LOG_GUIDE.md` (line 513 area) alongside the existing
  pre-commit sibling reference.

Verified: `python -m pytest scripts/tests/test_decisions_yaml_gate.py -v`
exits 0; full suite passes (`14527 passed, 36 skipped`).
