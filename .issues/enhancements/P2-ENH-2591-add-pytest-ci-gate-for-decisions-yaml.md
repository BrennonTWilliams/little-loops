---
id: ENH-2591
title: Add pytest CI gate for `.ll/decisions.yaml` corruption
type: ENH
status: open
priority: P2
parent: ENH-2587
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T22:15:00Z'
decision_needed: false
labels:
  - decisions
  - data-integrity
  - tooling
  - ci
  - pytest
size: Small
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

## Files to Modify

- `scripts/tests/test_decisions_yaml_gate.py` (new) — mirror
  `scripts/tests/test_policy_builder_node_gate.py:1-72` shape:
  - Module-level `pytestmark = pytest.mark.gate` (matches the established
    gate marker convention).
  - `shutil.which("ll-verify-decisions")` skip guard.
  - `tmp_path` fixture for the OTHE-203 corrupted `decisions.yaml`.
  - Positive case (valid file → exit 0).
  - Negative case (corrupted file → exit non-zero, stderr contains the path).
- `docs/reference/CONFIGURATION.md` — note the gate exists and where to
  find it (one paragraph).

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
   
   pytestmark = pytest.mark.gate
   
   @pytest.fixture(scope="module")
   def validator():
       path = shutil.which(CLI)
       if not path:
           pytest.skip(f"{CLI} not installed; install via `pip install -e ./scripts[dev]`")
       return path
   
   def test_decisions_yaml_loads(validator):
       result = subprocess.run([validator], cwd=REPO_ROOT,
                                capture_output=True, text=True)
       assert result.returncode == 0, f"{CLI} failed: {result.stderr}"
   
   def test_decisions_yaml_rejects_othe_203(validator, tmp_path):
       decisions = tmp_path / ".ll"
       decisions.mkdir()
       (decisions / "decisions.yaml").write_text(
           'entries:\n  - id: OTHE-203\n    type: decision\n    rationale: "abc "" def"\n'
       )
       result = subprocess.run([validator, "--config-root", str(tmp_path)],
                                cwd=tmp_path, capture_output=True, text=True)
       assert result.returncode != 0
       assert "decisions.yaml" in result.stderr.lower()
   ```
3. Add one paragraph to `docs/reference/CONFIGURATION.md` referencing the
   new gate.
4. Run the gate: `python -m pytest scripts/tests/test_decisions_yaml_gate.py -v`.
5. Run the full suite: `python -m pytest scripts/tests/`.

## Session Log
- `/ll:issue-size-review` - 2026-07-10T22:15:00 - `61c51949-414d-4865-b102-91b1bc365edd.jsonl`
