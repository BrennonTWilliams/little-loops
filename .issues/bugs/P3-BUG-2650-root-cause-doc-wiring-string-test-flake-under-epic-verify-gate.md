---
id: BUG-2650
type: BUG
priority: P3
status: open
captured_at: '2026-07-15T00:00:00Z'
discovered_date: 2026-07-15
discovered_by: manage-issue
relates_to:
- BUG-2649
- BUG-2629
- BUG-2640
decision_needed: false
---

# BUG-2650: Root-cause the doc-wiring string test flake under the epic verify gate

## Summary

`test_string_present_in_doc` (`scripts/tests/test_wiring_skills_and_commands.py`)
was observed to false-negative **once**, only under the epic-merge verify gate
(`verify_epic_branch_before_merge`), which runs `python -m pytest scripts/tests/`
against an EPIC branch tip with an injected `PYTHONPATH=<worktree>/scripts` under
`pytest-xdist`. The failing case was
`[.claude/CLAUDE.md-spike-FEAT-2567]` on the EPIC-2570 run (2026-07-15). The
string *is* present on the branch; the test passes in an isolated branch worktree
run and on merged `main`.

As the immediate remediation (BUG-2649) the test is **quarantined under the gate
condition**: it skips when `os.environ.get("LL_VERIFY_GATE") == "1"` (a marker
`verify_epic_branch_before_merge` now always sets in its child env). This bug
tracks the deferred **root-cause** work so the quarantine can be removed.

## Current Behavior

- The presence test skips under the gate (`LL_VERIFY_GATE=1`); it still runs and
  passes under the standard `python -m pytest scripts/tests/` invocation.
- The underlying flake mechanism is **undetermined**. The original "conftest
  resolves to main vs worktree" theory was investigated and disproved in BUG-2649:
  the `project_root` fixture is `Path(__file__).parent.parent.parent`-anchored and
  the `conftest.py` is path-collected from the worktree, so it already resolves to
  the worktree root under the gate (where `.claude/CLAUDE.md` *does* contain the
  needle). Switching to a `request.config.rootpath`-anchored fixture would resolve
  to the same worktree root and is unlikely to change behavior.

## Expected Behavior

The flake mechanism is identified and fixed (e.g. a reproducible cross-tree read,
an xdist worker/`conftest` import race, or a stale worktree read is pinned down and
eliminated), the `LL_VERIFY_GATE` skip is removed from `test_string_present_in_doc`,
and the test runs green under the gate condition.

## Steps to Reproduce

Not reliably reproducible to date. The single observed failure was on the
`sprint-refine-and-implement` run for EPIC-2570 (`2 failed, 14994 passed`; the
other failure — Test 1 — was branch staleness, since fixed). Re-running the
node id in isolation on the branch worktree passed. A repro harness that drives
`verify_epic_branch_before_merge(..., src_dir="scripts")` against a branch and
loops the doc-wiring subset under `-n logical` may be needed to surface it.

## Acceptance Criteria

1. The flake mechanism is root-caused with a concrete, documented reproduction
   (or a definitive proof it cannot recur under the gate).
2. The fix is applied, the `@pytest.mark.skipif(... LL_VERIFY_GATE ...)` quarantine
   on `test_string_present_in_doc` is removed, and the test passes under the gate.
3. `python -m pytest scripts/tests/` still exits 0 on `main`.

## References

- Quarantine + `LL_VERIFY_GATE` marker: BUG-2649
  (`scripts/little_loops/worktree_utils.py`,
  `scripts/tests/test_wiring_skills_and_commands.py:207`).
- xdist context: `scripts/pyproject.toml` `[tool.pytest.ini_options]` `-n logical`;
  `scripts/tests/conftest.py:208` (`project_root`), `:77-101`
  (`pytest_collection_modifyitems` `no_parallel` serial-only idiom).

## Status

- **Current Status**: open
- **Blockers**: Hard to reproduce; needs a repro harness before root cause can be pinned.
