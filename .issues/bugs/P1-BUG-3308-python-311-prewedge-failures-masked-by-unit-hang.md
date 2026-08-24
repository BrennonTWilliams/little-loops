---
id: BUG-3308
title: "258 pre-wedge unit-test failures masked by the chronic unit-test hang on Python 3.11 runner"
type: BUG
priority: P1
status: open
discovered_date: 2026-08-24
discovered_by: qa-pipeline-watch
labels:
- ci
- test-quality
- python-3.11
- chronic-failure
- watch-pair
verify_verdict: VALID
confidence_score: 88
outcome_confidence: 60
score_complexity: 65
score_test_coverage: 90
score_ambiguity: 40
score_change_surface: 55
size: Large
size_bucket: many
relates_to:
- PR-6
- run-32686625918
- run-32092369016
- BUG-322
relates_to_note: independent of the BUG-322 promotion-defect; surfaces because the wedge is fixed
execution_target: little-loops
parent: EPIC-101
decision_needed: false
---

# BUG-3308: 258 pre-wedge unit-test failures masked by the chronic unit-test hang on Python 3.11 runner

## Summary

`unit-tests` on `main` has been wedged (chronic failure, ~135MB RSS, not OOM,
pre-dates PR #6 by ≥1 week and masked for ~6 months by Thinky's
no-timeout-hang tolerance). The wedge kills pytest before it can write
`junit.xml`, so the artifact uploader has nothing to upload — meaning the
*real* unit-test result for the last several months of pushes-to-main has
never been visible. What has been visible (Watcher, 2026-08-24): at least
**258 distinct test failures** in the pre-wedge portion of execution order
in run `32686625918` (the most recent diagnosis-branch CI run on
2026-08-24T03:29Z, 55m5s, failure).

This BUG tracks the 258 failures as a separate workstream from the wedge
fix. The wedge must be fixed first to give us reliable visibility into the
failure set; once it is, the 258 need to be either fixed or classified as
known-failing and quarantined.

This BUG is filed in **little-loops** (the runner owner) rather than
ll-product, because the failures live in `scripts/tests/` of this repo and
need Python 3.11 reproduction against the runner image.

## Current Behavior

Run `32686625918` (main @ `9d1fa2935`, diagnosis-branch tip `22f1d8623`,
2026-08-24T03:29Z, ubuntu-latest, 55m5s, failure):

- **0 failures visible in CI summary** because pytest hangs before
  `junit.xml` is written.
- **258 failures visible in pre-wedge execution** (per Watcher +
  pytest-log pull from the run). Examples cited by Watcher:
  - `TestBackfillAssistantMessages` — 8/8 fail
  - `TestRecheckScoresDesignGateEndToEnd` — 2/2 fail
  - `TestBrainstormDryRun::test_all_states_reachable` — fail
  - Plus failures across `test_claude_code_adapter.py`,
    `test_codex_adapter.py`, `test_kimi_adapter.py`,
    `test_compaction.py`, `test_fsm_executor.py`,
    `test_goal_cluster.py`.
- **Wedge itself**: `pytest` stops reporting at ~52m, runner death,
  conformance job skipped (`needs: [unit-tests]`).
- **Instrumentation gap**: `timeout --signal=TERM --kill-after=30s 30m`
  backstop in the run is not honored (process kept running 24m past it),
  and artifact upload cannot capture hang-mode (no junit on hard wedge).

`19/19 pass on local Python 3.12` (Watcher's claim, not yet verified by
this filing). This is the working hypothesis for why the failures did not
surface earlier: they are **Python 3.11-specific**.

Local repro on this branch (Python 3.12.3, after `pip install -e "./scripts[dev]"`):

- `test_assistant_messages.py` — 19/19 passed (1.97s) — *contradicts*
  Watcher's 8/8 fail claim.
- `test_claude_code_adapter.py` — 15/15 passed (1.72s)
- `test_codex_adapter.py` — 12/12 passed (1.50s)
- `test_kimi_adapter.py` — 11/11 passed (1.53s)
- `test_compaction.py` — 21/21 passed (1.19s)
- `test_fsm_executor.py` — 416/416 passed (87s) — *contradicts* Watcher's
  failure claim.
- `test_goal_cluster.py` — 1/36 fail (`test_ll_loop_validate_passes`,
  `FileNotFoundError: 'll-loop'` because subprocess PATH does not
  inherit venv bin) — *environmental*, not 3.11-specific.

**Conclusion**: Either the failures are indeed 3.11-specific and need
reproduction against the runner image, or Watcher's pytest-log pull
included tests not actually in the run's execution. Both hypotheses need
verification before this BUG moves out of `open`.

## Expected Behavior

Once the wedge is fixed (Builder's `ci/fix-unit-test-hang` PR), every
push-to-main produces a complete `junit.xml` and the artifact uploader
captures it. The 258 failures become individually actionable:

- Each failure has a known cause (3.11 compat, missing CLI on runner,
  missing fixture, flaky test, etc.).
- Each failure has a known fix path (or a known-quarantine reason if the
  test should be skipped/removed).
- The fix path is independent of the wedge fix — this is a *separate*
  workstream from the wedge, but cannot start in earnest until the wedge
  is fixed (visibility).

## Acceptance Criteria

1. **The 258 failures are enumerated** with at minimum: test file,
   test class, test method, failure mode (`assertion`, `error`, `xfail`
   miscategorization, etc.).
2. **Each failure is classified** into one of:
   - `3.11-compat` — fails on 3.11, passes on 3.12; needs code fix or
     `pytest.mark.skip` with TODO
   - `runner-env` — fails because of missing CLI / fixture on the runner
     image; needs image fix or test setup fix
   - `flake` — non-deterministic; needs flake fix or quarantine
   - `genuine-regression` — passes on a previous main, fails now; needs
     code fix
   - `test-bug` — the test itself is wrong; needs test fix
3. **Each classified failure has an owner** (file:line and the module
   it lives in) and a proposed fix (or a "quarantine" justification
   if not worth fixing).
4. **`Python 3.11` repro environment exists** in this repo — either via
   `tox`, `pyenv` config, or a CI matrix entry — so future regressions
   in the 3.11-specific class are caught before they ship.
5. **The wedge fix PR (Builder's, in pre-flight)** is verified not to
   hide any of these failures: pytest's junit must contain *every*
   failure that was previously pre-wedge, not just the wedge as failure.
6. **Green main** achievable without fixing all 258 — i.e., the
   failures can be quarantined (skip + tracked) rather than all fixed
   in one PR.

## Out of Scope (separate workstreams)

- **The unit-hang wedge itself** — Builder owns
  `ci/fix-unit-test-hang` (in pre-flight per Watcher 2026-08-24). This
  BUG depends on that PR landing; it does not include the wedge fix.
- **Broken instrumentation** (`timeout --kill-after=30s` not honored,
  artifact upload silent loss) — also Builder's
  `ci/fix-unit-test-hang` PR (the `if-no-files-found: error` change).
- **Bug-322 cluster** — different defect class (hub→spoke promotion
  reconciliation). Listed as `relates_to` only because BUG-322 surfaced
  the same kind of "we don't see the real test result" pathology.

## Verification Strategy

1. **Once the wedge PR lands**: pull `junit.xml` from a fresh
   green-main run. Confirm the 258 failures are present (and that the
   list matches Watcher's count).
2. **Cross-check on Python 3.12 locally**: the failures that don't
   reproduce locally are the 3.11-specific subset. Run each in a
   Python 3.11 venv to confirm.
3. **For each failure class**, run the test 5× to surface flakes
   before classifying as `genuine-regression` or `test-bug`.
4. **Owner mapping**: for each failure, find the file:line of the
   failing test, then map to the owning module (CLI loop, FSM executor,
   host adapter, etc.) and surface to the corresponding maintainer.

## Source

- Watcher signal 2026-08-24 (3 corrections in one evening) —
  `cfcedab68b1d44cef43224d17da1bdbd3169eb573a262f3b1d82f7ae65cca442`
- Run `32686625918` (main @ `9d1fa2935`, diagnosis-branch
  `22f1d8623`, 2026-08-24T03:29Z, 55m5s, failure)
- Run `32092369016` (main, 2026-08-18, unit-tests `in_progress` at 14m,
  conformance green, overall failure — pre-PR-6 wedge evidence)
- Local Python 3.12.3 repro on this branch (results above)
- CI workflow `.github/workflows/ci.yml` (push-only on main, no PR
  trigger — intentional security posture)

## Status

**Open** | Created: 2026-08-24 | Priority: P1 | Discovered by: QA pipeline
watch (post-#6 CI analysis)

Tracking this in parallel with Builder's `ci/fix-unit-test-hang` PR.
Once that lands, this BUG moves from "queued for visibility" to
"actively enumerating failures."
