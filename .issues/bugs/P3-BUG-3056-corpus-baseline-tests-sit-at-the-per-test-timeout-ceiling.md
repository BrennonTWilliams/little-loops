---
id: BUG-3056
title: TestCorpusBaseline sits at the 120s per-test timeout ceiling and fails serial
  runs
type: BUG
priority: P3
status: done
testable: true
discovered_by: run-forensics
discovered_date: 2026-08-05
captured_at: '2026-08-05T05:42:22Z'
completed_at: '2026-08-05T05:42:22Z'
relates_to:
- ENH-2971
- BUG-2488
- BUG-2788
labels:
- testing
- timeout
- flake
---

# BUG-3056: TestCorpusBaseline sits at the 120s per-test timeout ceiling and fails serial runs

## Summary

`TestCorpusBaseline` sweeps the entire `.issues/` corpus, spawning a `git grep`
subprocess per Program Design symbol anchor. Each of its three tests now takes
about 121 seconds against the suite-wide `--timeout=120` in
`scripts/pyproject.toml`. The margin is gone: serial runs fail, parallel runs
squeak through, and corpus growth only widens the gap.

## Steps to Reproduce

1. Run the suite serially:
   ```
   python -m pytest scripts/tests/ -n 0
   ```
2. Observe the run abort inside
   `test_skips_at_least_twenty_percent_of_axis_spawns` with a faulthandler stack
   dump ending in `program_design.py:283, in git_grep_resolver` →
   `subprocess.run` → `selector.select(timeout)`.
3. Confirm the work is slow rather than hung — with the ceiling raised, all three
   pass:
   ```
   python -m pytest scripts/tests/test_research_triage.py -n 0 --timeout=900 \
       -k TestCorpusBaseline
   # 3 passed in 362.63s
   ```

## Current Behavior

The class carries `@pytest.mark.slow` but no timeout override, so it inherits the
120s per-test ceiling from `addopts`. At roughly 121s per test it fails or passes
on scheduling noise. `time` reports 1106% CPU for the three-test run — the cost is
`git grep` subprocess fan-out, not a wedged process, which is exactly what the
120s net was designed to kill.

The failure mode is also misleading: the run aborts with a thread stack dump
rather than a named test failure, which reads as a hang. During this session's
investigation it initially looked like the known xdist beachball
(BUG-2488 / BUG-2788), and the agent in the original `ll-auto` run made the same
misattribution.

## Expected Behavior

The class runs to completion under both `-n 0` and the default parallel mode. Its
ceiling reflects its real runtime, so a genuine hang is still caught but ordinary
corpus-scale work is not.

## Root Cause

`--timeout=120` is a global safety net calibrated for unit tests. `TestCorpusBaseline`
is a corpus-scale integration gate whose cost scales with the number of issues on
disk. It was written when the corpus was small enough for the default to be
generous, and nothing re-evaluated the ceiling as the corpus grew.

## Program Design

No production code changes. The class gains an explicit per-test ceiling, the
mechanism `pyproject.toml` already documents for this case ("Tests with
legitimately slow wall-clock can opt out via `@pytest.mark.timeout(N)` per test").

### Signatures

- `class TestCorpusBaseline` — `scripts/tests/test_research_triage.py:460`, gains `@pytest.mark.timeout(600)` above the existing `@pytest.mark.slow`.
- `triage_research_axes(issue, repo_root: Path, index=None, check_staleness: bool = True)` — existing, `issues/research_triage.py:311`; unchanged.
- `git_grep_resolver(symbol: str, root: Path) -> bool` — existing, `issues/program_design.py:283`; unchanged, and the per-anchor subprocess this test's cost comes from.

### Call Path

`TestCorpusBaseline.test_skips_at_least_twenty_percent_of_axis_spawns` (`test_research_triage.py:515`) -> `triage_research_axes` (`issues/research_triage.py:311`) -> `_program_design_unmet` (`issues/research_triage.py:369`) -> `grade_issue_section` (`issues/program_design.py:447`) -> `git_grep_resolver` (`issues/program_design.py:283`) -> `subprocess.run`. No production node on this path changes; only the test's timeout marker.

600s gives roughly 5x headroom over the measured ~121s, leaving room for corpus
growth while still bounding a true hang.

Raising the ceiling treats the symptom. The growth curve itself — one `git grep`
subprocess per anchor per issue, with no memoization in
`program_design.git_grep_resolver` — is left in place deliberately: caching is a
change to production resolution semantics and does not belong in a test-timeout
fix.

## Implementation Steps

1. Add `@pytest.mark.timeout(600)` above the existing `@pytest.mark.slow` on
   `TestCorpusBaseline` in `scripts/tests/test_research_triage.py`.
2. Record the measured runtime and the reasoning in a comment so the next person
   to see a slow run does not mistake it for a hang.

## Impact

Intermittent full-suite failures unrelated to any change under test. This is
especially damaging in automation: `ll-auto` and sprint runs gate completion on a
green suite, so a borderline-timeout test can fail an otherwise correct run — and
the stack-dump presentation sends the investigation toward the wrong cause. It
cost real time in this session before being isolated.

## Resolution

`@pytest.mark.timeout(600)` applied to the class. Verified: the three tests pass
in 362.63s total under `-n 0`, and the full suite completes under both serial and
parallel modes.

Follow-up worth considering but deliberately not done here: memoize
`git_grep_resolver` per symbol within a run, which attacks the growth curve rather
than the ceiling.

## Status

**Completed** — 2026-08-05

## Session Log
- `hook:posttooluse-status-done` - 2026-08-05T05:45:56 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- run-forensics - 2026-08-05 - Isolated while verifying an unrelated fix; ceiling
  raised after measuring actual runtime.
