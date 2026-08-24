---
id: BUG-3308
title: "Pre-wedge unit-test failures masked by chronic hang — split into env-artifact vs genuine-breakage"
type: BUG
priority: P1
status: open
discovered_date: 2026-08-24
discovered_by: qa-pipeline-watch
labels:
- ci
- test-quality
- chronic-failure
- env-artifact
- watch-pair
verify_verdict: VALID
confidence_score: 92
outcome_confidence: 70
score_complexity: 60
score_test_coverage: 90
score_ambiguity: 30
score_change_surface: 45
size: Large
size_bucket: many
relates_to:
- PR-6
- run-32686625918
- run-32092369016
- run-32684060984
- BUG-3208
- BUG-322
- BUG-891
relates_to_note: BUG-3208 is the upstream wedge defect (already fixed by ci/fix-unit-test-hang); BUG-322 is a different defect class with the same "we don't see the real test result" pathology; BUG-891 is the historical __main__.py landing for cli.loop (this BUG extends to cli/)
execution_target: little-loops
parent: EPIC-101
decision_needed: false
---

# BUG-3308: Pre-wedge unit-test failures masked by chronic hang — split into env-artifact vs genuine-breakage

## Summary

`unit-tests` on `main` has been wedged (chronic failure, ~135MB→400-580MB
RSS, not OOM, xdist shutdown after `pytest_sessionfinish`) for at least a
week before PR #6 and ~6 months before that (masked by Thinky's
no-timeout-hang tolerance). The wedge kills pytest before `junit.xml` is
written, so the *real* unit-test result for the last several months of
pushes-to-main has never been visible.

**The full failure set is now known** (Cooper, 2026-08-24): a complete
full-suite repro on **Python 3.12.3** (Thinky, 16m21s, **122 failed /
19907 passed**, memory flat ~520MB) shows the failures reproduce on 3.12
— they are **not 3.11-specific** (the "3.11-specific" hypothesis is
**dropped**).

**The 122 splits cleanly:**

- **~105 of 122** share one signature: `No module named
  little_loops.cli.__main__; 'little_loops.cli' is a package and cannot
  be directly executed`. This is an **env artifact, not product
  breakage**. The test helper `shutil.which("ll-issues")` returns `None`
  in CI because `.github/workflows/ci.yml` runs `.venv/bin/python`
  directly with `.venv/bin` never on `PATH` (verified: ci.yml L141).
  `little_loops/cli/__main__.py` doesn't exist. **One commit** — add
  `__main__.py` dispatching to the existing `main_*` entry points (or
  put `.venv/bin` on PATH in the workflow) — clears ~105 of those
  "failures."
- **The remaining ~17** (adapters / compaction / fsm / backfill /
  recheck / goal_cluster / etc.) are **genuine breakage** that needs
  per-failure triage.

The wedge fix PR (`ci/fix-unit-test-hang`) is now in flight (Builder /
Cooper), so visibility into the real test result is restored. This BUG
tracks the triage of the post-wedge failure set.

## Current Behavior

- **Wedge (BUG-3208)**: pytest stops at ~52m, runner death,
  conformance skipped. The pin `pytest-xdist<3.8` (commit `3abd9b38c`,
  the other half of BUG-3208) was insufficient — fresh venv resolves
  pytest-xdist>=3.0 to 3.8.0 via transitive resolution path.
  - **Fix**: switch `--timeout-method=thread` → `signal` in
    `pytest.ini` AND `scripts/pyproject.toml` (CI reads the latter
    because `test_cmd` passes `scripts/tests` explicitly; root flip
    alone is a CI no-op). Plus `if-no-files-found: warn → error` on
    artifact uploads so a wedged run surfaces as a real failure next
    time.
  - **Tradeoff**: signal-method historically raced with xdist worker
    process management. pytest-timeout 2.0+ redesigned signal-mode to
    install the handler per-worker, so the race is no longer
    load-bearing for our pytest-timeout pin (>=2.0). Accepting this
    tradeoff deliberately to fix the wedge.
  - **References**: BUG-3208, run `32684060984` (Cooper's durable-sink
    capture — `pytest_sessionfinish` *fired*, RSS 400→580MB, freeze in
    xdist shutdown after sessionfinish).
- **Env-artifact failures (~105)**: missing
  `little_loops/cli/__main__.py`. The test helper pattern (e.g.
  `scripts/tests/test_ll_issues_check_*.py`):
  ```python
  if shutil.which("ll-issues") is not None:
      return ["ll-issues"]
  return [sys.executable, "-m", "little_loops.cli"]  # FAILS: no __main__.py
  ```
  In CI (`.venv/bin` not on PATH), `shutil.which("ll-issues")` is
  `None`, so the fallback fires and the package cannot be executed.
  - Local repro on this branch (Python 3.12.3, `PATH` stripped of
    `.venv/bin`): **35 failures across 6 affected files** in
    ~6 seconds:
    - `scripts/tests/test_ll_issues_check_decidable.py` — 16/18
    - `scripts/tests/test_ll_issues_check_unresolved_decisions.py`
    - `scripts/tests/test_ll_issues_check_design.py`
    - `scripts/tests/test_ll_issues_check_open_questions.py`
    - `scripts/tests/test_ll_issues_check_flag.py`
    - `scripts/tests/test_ll_issues_check_acceptance_criteria.py` (via
      shared helper)
    - `scripts/tests/test_check_family_not_found_exit_code.py` (via
      shared helper)
    - `scripts/tests/test_cli_loop_background.py` (different — tests
      the existence of `cli/loop/__main__.py`, which DOES exist; this
      one passes)
  - The error message is consistent:
    `'little_loops.cli' is a package and cannot be directly executed`.
- **Genuine failures (~17)**: adapters (`test_claude_code_adapter.py`,
  `test_codex_adapter.py`, `test_kimi_adapter.py`), `test_compaction.py`,
  `test_fsm_executor.py`, `test_goal_cluster.py` (1/36: the
  `@pytest.mark.slow` `test_ll_loop_validate_passes` with subprocess
  PATH not inherited from venv — small fix), `test_backfill_*`,
  `test_recheck_*`. Need per-failure triage.

## Expected Behavior

Once both the wedge fix and the `__main__.py` fix land:

- Every push-to-main produces a complete `junit.xml`.
- The artifact uploader captures it (no silent loss).
- The test summary in GH Actions shows the *actual* failures, not a
  52m timeout.
- The remaining ~17 genuine failures are individually actionable
  (each has a known cause: 3.11-compat / runner-env / flake /
  genuine-regression / test-bug, with a fix path or quarantine
  justification).

## Acceptance Criteria

1. **`__main__.py` env-artifact failures (~105) cleared by the
   `__main__.py` fix**: either
   - Add `scripts/little_loops/cli/__main__.py` dispatching to
     `main_issues` (and any sibling entry points the affected tests
     use), OR
   - Put `.venv/bin` on PATH in `.github/workflows/ci.yml` so
     `shutil.which("ll-issues")` returns the installed binary and the
     fallback doesn't fire.
   **Verify**: with `PATH` stripped of `.venv/bin`, the 6 affected
   test files all pass (35 failures → 0).

2. **The remaining ~17 genuine failures are enumerated** with at
   minimum: test file, test class, test method, failure mode
   (`assertion`, `error`, etc.). The workstream is small enough to be
   enumerated in a single triage PR.

3. **Each genuine failure is classified** into one of:
   - `3.11-compat` — fails on 3.11, passes on 3.12; needs code fix or
     `pytest.mark.skip` with TODO
   - `runner-env` — fails because of missing CLI / fixture on the
     runner image; needs image fix or test setup fix
   - `flake` — non-deterministic; needs flake fix or quarantine
   - `genuine-regression` — passes on a previous main, fails now;
     needs code fix
   - `test-bug` — the test itself is wrong; needs test fix

4. **The `test_goal_cluster.py::test_ll_loop_validate_passes` fix
   ships in the same release** (Builder flagged it as the one
   actionable item parallel to the wedge fix): either set
   `env={**os.environ, "PATH": str(Path(sys.executable).parent) +
   os.pathsep + os.environ.get("PATH", "")}` in the `subprocess.run`,
   or invoke via `[sys.executable, "-m", "little_loops.cli", …]`.

5. **Wedge fix PR (`ci/fix-unit-test-hang`) verified not to hide
   any failures**: pytest's junit on a green dispatch must contain
   *every* failure that was previously pre-wedge, not just the wedge
   as failure.

6. **Green main** achievable without fixing all ~17 remaining genuine
   failures — i.e., each can be quarantined (skip + tracked) rather
   than all fixed in one PR.

## Out of Scope (separate workstreams)

- **The unit-hang wedge itself (BUG-3208)** — fixed by
  `ci/fix-unit-test-hang` (in flight). This BUG depends on that PR
  landing; it does not include the wedge fix.
- **Bug-322 cluster** — different defect class (hub→spoke promotion
  reconciliation). Listed as `relates_to` only because BUG-322
  surfaced the same kind of "we don't see the real test result"
  pathology.
- **BUG-891** (the historical `cli/loop/__main__.py` landing for
  `python -m little_loops.cli.loop`) — that file exists and tests
  pass; the missing piece is `cli/__main__.py` for `python -m
  little_loops.cli`. Listed as `relates_to` for context.

## Verification Strategy

1. **Once the wedge fix lands**: pull `junit.xml` from a fresh
   green-main run. Confirm the 122 failures are present (and that
   the list matches Cooper's count).
2. **Apply the `__main__.py` fix** (or PATH fix) on a separate PR.
   Confirm the ~105 env-artifact failures go away.
3. **The remaining ~17** are the genuine-breakage workstream —
   triage by the maintenance owner of each module (CLI loop, FSM
   executor, host adapter, etc.).
4. **Cross-check on Python 3.12** (Cooper's repro data is already on
   3.12; the 3.11 hypothesis is dropped, so no separate 3.11 env
   needed unless 3.11-specific regressions emerge after the triage).

## Source

- Watcher signal 2026-08-24 (3 corrections in one evening) —
  `cfcedab68b1d44cef43224d17da1bdbd3169eb573a262f3b1d82f7ae65cca442`
- Cooper's 3.12 repro: Thinky, 16m21s, **122 failed / 19907 passed**,
  memory flat ~520MB
- Cooper's wedge evidence: run `32684060984` (durable-sink capture;
  `pytest_sessionfinish` fired; RSS 400→580MB; freeze in xdist
  shutdown after sessionfinish — the `--timeout-method=thread`
  watchdog-thread wedge)
- Wedge fix PR: `ci/fix-unit-test-hang` (in flight)
- Run `32686625918` (main @ `9d1fa2935`, diagnosis-branch
  `22f1d8623`, 2026-08-24T03:29Z, 55m5s, failure) — pre-wedge failure
  set is partially visible in pytest logs
- Run `32092369016` (main, 2026-08-18, unit-tests `in_progress` at
  14m, conformance green, overall failure — pre-PR-6 wedge evidence)
- Local repro on this branch (Python 3.12.3, `PATH` stripped of
  `.venv/bin`): 35 failures across 6 affected files; error message
  `'little_loops.cli' is a package and cannot be directly executed`
- CI workflow `.github/workflows/ci.yml` (push-only on main, no PR
  trigger — intentional security posture)

## Status

**Open** | Created: 2026-08-24 | Priority: P1 | Discovered by: QA
pipeline watch (post-#6 CI analysis)

The wedge fix PR (`ci/fix-unit-test-hang`) is the gating dependency.
Once it lands and `__main__.py` (or PATH) is fixed, the ~105
env-artifact failures go away, leaving ~17 to triage. Green main is
achievable in 1-2 PRs after that, not 2-3.
