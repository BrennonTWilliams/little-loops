---
id: BUG-3522
type: BUG
title: policy-builder node conformance gate is dormant in CI and the flake is a JS hash-completion race
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-20'
captured_at: '2026-09-20T05:20:00Z'
labels:
- policy-builder
- node
- xdist
- flake
- test-stability
relates_to:
- ENH-3453
- BUG-3486
- BUG-3502
- BUG-3484
- BUG-2523
---

# BUG-3522: policy-builder node conformance gate is dormant in CI and the flake is a JS hash-completion race

## Summary

`scripts/tests/test_policy_builder_node_gate.py::test_node_conformance_suite_passes` — the FEAT-2390 gate that runs the 231-subtest JS conformance suite via `node --test` — **can no longer fail in CI**. It carries `@pytest.mark.no_parallel`, added by `60358e836` (committed as BUG-3521, the ID this issue was later renumbered from) on the theory that xdist CPU contention starved the test's 180-second subprocess budget. Under the default `-n logical` addopts that marker skips the test on every xdist worker, and the controller never executes tests itself, so the gate is dormant: a green `unit-tests` job no longer says anything about the JS core.

The flake that motivated the marker was real, but it is **not** a timeout. Both failing runs on record fail on the same assertion — `'hashing' !== 'ready'` inside the `reviewed()` helper in `scripts/tests/js/policy_submission.test.mjs` — while the entire JS suite finishes in **438 ms**. `settleHash()` waits for a genuinely asynchronous `crypto.subtle.digest` by spinning a bounded 50 `setImmediate` turns (≈0.7 ms of wall clock), which is not a completion signal once the libuv threadpool is starved. The defect is test-side synchronization, so it is fixable — and once fixed, the marker can be dropped and the gate runs again in the normal parallel CI job with no new workflow step.

## Current Behavior

**Dormancy (verified locally):** from `scripts/`, `python -m pytest tests/test_policy_builder_node_gate.py -n 2` → `5 passed, 1 skipped`. The skip is `test_node_conformance_suite_passes`; the five `test_round_trip_yaml_validates_for_each_mode` cases in the same file still run.

**Why it is unreachable in CI:** `scripts/pyproject.toml` addopts pin `--timeout=120 --timeout-method=thread -n logical --dist loadfile`; `pytest_collection_modifyitems` in `scripts/tests/conftest.py` adds a skip marker to every item carrying `@pytest.mark.no_parallel`; the `unit-tests` job in `.github/workflows/ci.yml` runs the suite with no `-n` override and no serial `-n 0` step, and the `conformance` job selects `-m conformance`, which this test does not carry. There is therefore no invocation anywhere that executes the gate.

**The signature that was misread:** in run `35490420257` the node suite reported `# tests 231 / # pass 227 / # fail 4 / # duration_ms 438.873238`. Four failures, all `'hashing' !== 'ready'`, all raised from `reviewed()` at `scripts/tests/js/policy_submission.test.mjs:90`, reached from lines 158, 263, 297 and 478. In run `35490782202` the same assertion failed once (line 478) — the count varies, the defect does not.

## Expected Behavior

- A JS-core regression in `scripts/little_loops/templates/policy_builder_core.mjs` fails the `unit-tests` job on a push to `main`.
- The JS conformance suite is deterministic: it waits for the real asynchronous completion it depends on, not for a fixed number of event-loop turns, so CPU contention cannot change the verdict.
- "CI is green" implies the gate executed. A missing Node toolchain is a loud failure, not a silent skip.

## Steps to Reproduce

### Deterministic (no CI, no load needed)

1. Build the submission controller exactly as `setup()` does in `scripts/tests/js/policy_submission.test.mjs`, injecting the real `globalThis.crypto.subtle` as `subtle` (line 72 does this today).
2. Occupy the whole libuv threadpool: start `UV_THREADPOOL_SIZE` (default 4) concurrent, long-running `pbkdf2` jobs from `node:crypto`.
3. Call `ctl.review({ yaml })`, then run the `settleHash` loop verbatim (up to 50 `setImmediate` turns, then `flush()`).
4. Read `ctl.getState().review.status` — it is still `"hashing"`. Measured on this checkout: `hashing` after 2.16 ms, i.e. exactly the CI failure `'hashing' !== 'ready'`.

### Idle-machine measurements (why it hides)

| Measurement | Value |
| --- | --- |
| 50 `setImmediate` turns (the `settleHash` budget) | 0.74 ms mean, 0.96 ms max |
| `crypto.subtle.digest` of the same 12-byte YAML, idle | 0.011 ms p50, 0.045 ms max (n=300) |

That is a ~67× margin while idle, which collapses as soon as the digest's threadpool thread is descheduled and only the (already hot) main thread keeps spinning turns.

### Historical (from CI)

- `gh run download <run-id>` yields `pytest-unit-failures-<run_id>-<attempt>/pytest.log` plus `pytest-junit.xml`; the node subtest detail is in `pytest.log` under the `test_node_conformance_suite_passes` assertion message.

## Likely Root Cause

_The capture-era hypothesis — subprocess/CPU-contention timeout, possibly Node 20 → 24 drift — is falsified by the artifacts; see `## Root Cause` and `## Verification Evidence` below._

## Proposed Solution

1. **Fix the wait, not the schedule** in `scripts/tests/js/policy_submission.test.mjs`: replace the bounded `settleHash` spin with a real completion signal. Preferred: make `subtle` injectable via `setup()` (the `createSubmissionController` seam at line 72 already exists) and resolve the digest explicitly, so the interleaving test at line 158 becomes exact instead of racy; alternative: poll on real timers against a generous deadline.
2. **Add a regression test for the race itself** — a starved or stubbed digest must still let `reviewed()` observe `ready`.
3. **Drop `@pytest.mark.no_parallel`** from `test_node_conformance_suite_passes` once (1) lands: with the race gone there is nothing for contention to break, and the gate returns to the default parallel invocation. Pair that with `@pytest.mark.timeout(240)` — strictly above the inner `timeout=180` — following the convention in `scripts/tests/test_verify_evidence.py`. Without it, a hung node process trips the 120-second thread watchdog first, whose `os._exit(1)` kills the worker instead of producing a clean `TimeoutExpired` assertion.
4. **Make a skip loud:** in CI, a missing Node toolchain should fail rather than skip, and the failure message should name `process.version`. Today a green job and a skipped gate are indistinguishable, which is how this bug stayed invisible.
5. **Optional coverage tidy-up:** `JS_TEST_DIR.glob("*.test.mjs")` does not descend into `scripts/tests/js/feat3304/`. Those tests are not uncovered, though — `scripts/tests/test_feat3304_artifact_dashboard.py::TestDashboardNodeRuntimeGate::test_generated_page_runtime_behaviour` runs them in CI. Widen the glob only if you want a single home for JS gates.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- **Conventions in force**: a timing-sensitive or long-subprocess test is marked `no_parallel` (runs only under serial `-n 0`); tests needing more than the 120s default set `@pytest.mark.timeout(N)` strictly above any inner subprocess timeout (`test_verify_evidence.py`). The codebase disagrees on dormancy: `test_worktree_utils.py` (BUG-2650) explicitly rejects `no_parallel` because it is dormant under the default CI command, and instead runs a nested `-n 0` pytest.
- Any resolution must keep the gate exercised somewhere (CLAUDE.md § Testing & CI Policy requires other-toolchain gates to run under the pytest suite), and must keep `test_conftest_cap.py::TestNoParallelMarkerRouting` passing.
- **Superseded framing** (evidence review, 2026-09-20): the open trade-off recorded here — "accept a dormant gate, add a serial CI invocation, or drop `no_parallel` in favor of a `timeout` marker above 180" — assumed the flake was a timeout budget mismatch. It is not (`## Root Cause`). Dormancy and a serial CI step are both unnecessary; the JS helper's wait is the defect, and `no_parallel` can come off entirely.

## Acceptance Criteria

- A regression test reproduces the race deterministically (threadpool-starved or stubbed digest) and fails before the fix, passes after; the `settleHash`/`reviewed` wait observes `ready` under starvation in `scripts/tests/js/policy_submission.test.mjs`
- `test_node_conformance_suite_passes` **executes** (not skipped) in the `unit-tests` job of `.github/workflows/ci.yml` on a push to `main`, and the uploaded `pytest-junit.xml` shows it as passed — no serial `-n 0` step required
- 5+ consecutive CI runs on `main` are green **with the gate executed in each**; the junit artifact for at least one run is cited as evidence that green means executed, not skipped
- `scripts/tests/test_conftest_cap.py::TestNoParallelMarkerRouting` still passes, and no other test's marker semantics change
- A Node toolchain absent from CI fails the gate (rather than skipping it), and the failure message names the Node version
- `test_round_trip_yaml_validates_for_each_mode` and the `feat3304` dashboard runtime gate are unaffected

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- The Program Design note that "runs on the controller" means "runs only in serial `-n 0`" makes the old AC 1 (5+ consecutive CI runs pass) trivially satisfiable by dormancy; a real criterion needs the gate to execute in at least one CI invocation. **Addressed:** the criteria above now require execution in the default parallel job and cite the junit artifact as proof.
- The old AC that pinned `actions/setup-node` is dropped: no artifact ties the failure to a Node version, and the proposed pin contradicted itself (`22.x.y` in the AC vs 24.x.y in Notes). See `## Notes`.

## Notes

- **The "Node 20 → 24 migration" framing is unsupported.** The Node version was never captured in the failure evidence — the artifacts contain `pytest.log`/`pytest-junit.xml`, and the only version visible is the executable path `/usr/local/bin/node`. This checkout's `node --version` is v26.0.0. Nothing in either failing run depends on the Node major; the failing assertion is a race that a faster or slower digest only changes the odds of.
- **The cited "2-fail / 1-pass on the same base" comparison does not hold.** Run `35490420257` failed on `main @ fdf6773d2`; the passing run `35490447772` was a `workflow_dispatch` on `enh/ll-loop-rename-and-cleanup @ 2f84ad50`; the second failing run `35490782202` was a `workflow_dispatch` on `fix/bug-3484-addopts-suppression-restored @ b5ab95ad`. Three different trees, not one base. The nondeterminism is still established — but by the varying failure count (4 vs 1) on the same helper, not by the run tally.
- **If a Node pin is still wanted,** it should pin what the runner actually ships, for reproducibility rather than for this bug, and it must not narrow the ratified "Node >= 22" posture that the gate itself enforces. `docs/development/TESTING.md` "Testing & CI Policy" in AGENTS.md forbids adding paid/hosted CI; `actions/setup-node` is free, but it is now unmotivated work.
- The marker commit `60358e836` repeated the unverified timeout hypothesis in its message ("intermittently exceeds time budgets or hits timing-sensitive assertions"). That message is now the main reason the wrong theory is in circulation.
- `relates_to` also carries `ENH-3453` (host capability map), which looks like an artifact of the BUG-3453 → BUG-3521 → BUG-3522 renumber chain rather than a real relationship.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- **Marker already landed**: `@pytest.mark.no_parallel` was added by `60358e836` (2026-09-20, `fix(tests): mark node conformance test no_parallel (BUG-3521) (#33)`), after the cited runs on `main @ fdf6773d2` (2026-09-19). The marker is the second half of this bug, not the fix.
- **Consequence of the marker**: `scripts/tests/conftest.py:pytest_collection_modifyitems` skips `no_parallel` items on xdist workers; the controller never runs tests under `-n N`. With `-n logical` in addopts, the gate never executes in either `.github/workflows/ci.yml` job (`unit-tests` on `ubuntu-latest`, `conformance` on self-hosted with `-m conformance`; the test has no `conformance` marker). No workflow step runs `-n 0`, so the FEAT-2390 policy-builder JS gate is currently dormant in CI.
- **Dependent/precedent files**: `scripts/tests/test_fsm_signal_integration.py` (module-level `pytestmark`, BUG-2523), `scripts/tests/test_feat3323_sse_bridge.py` (BUG-3484, stacked with `@pytest.mark.timeout(180)`), `scripts/tests/test_conftest_cap.py:TestNoParallelMarkerRouting` (hook contract), `docs/development/TESTING.md` (marker table ~L1050), `docs/development/TROUBLESHOOTING.md` (BUG-2523 section ~L825).
- **CI Node**: `.github/workflows/ci.yml` has no `actions/setup-node` and no `node-version`; Node comes from the runner image. The Node-pin acceptance criterion would be the first Node pin in the repo.
- **AC references that do not resolve**: `test_node_22plus_runs_ok` and `test_node_test_runner_emits_tap_v13` do not exist anywhere; the sibling test in the file is `test_round_trip_yaml_validates_for_each_mode` (no `no_parallel`, inner `timeout=30`).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — § Testing & CI Policy cites `test_policy_builder_node_gate.py` as the enforced example of a wrapped other-toolchain gate; a dormant gate under default `-n logical` contradicts that claim [Agent 2 finding]
- `AGENTS.md` — mirrors the same `test_policy_builder_node_gate.py` reference; keep consistent with CLAUDE.md [Agent 2 finding]
- `scripts/tests/test_policy_builder_node_gate.py` — module docstring (L1-17) says "no hosted CI … single enforced location is the local suite" and "this repo's environment ships Node 22"; both are stale (`.github/workflows/ci.yml` exists, the runner ships 24, this checkout ships 26) — update alongside any resolution [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md` — marker table row for `no_parallel` (~L1050) says "runs on the controller or in a serial `-n 0` invocation"; under `-n N` the controller runs no tests, so reword to "serial `-n 0` only" [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — the BUG-2523 section (~L825) asserts "The tests still run — they just don't share cores"; for a gate whose only CI invocation is `-n logical`, that is exactly the false assumption this issue falsifies [evidence review addition]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/js/policy_submission.test.mjs` — `settleHash` (L44-49), `reviewed` (L87-91) and `setup` (L71-81) are the primary fix site; the race is here, not in the Python gate [evidence review addition]
- `scripts/tests/test_conftest_cap.py` — `TestNoParallelMarkerRouting` must keep passing if the marker is changed/removed [Agent 3 finding]
- `scripts/tests/js/feat3304/feat3304_dashboard_runtime.test.mjs` — lives in a subdir, so the gate's non-recursive `JS_TEST_DIR.glob("*.test.mjs")` never runs it; it is nevertheless executed in CI by `scripts/tests/test_feat3304_artifact_dashboard.py::TestDashboardNodeRuntimeGate::test_generated_page_runtime_behaviour` (no `no_parallel`, inner `timeout=180`) — scope the "the gate covers X" discussion accordingly [Agent 3 finding, corrected during evidence review]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `.github/workflows/ci.yml` — **no** serial `-n 0` step is needed once the race is fixed: removing `no_parallel` restores the gate to the existing parallel `unit-tests` invocation. The workflow change reduces to a skip-to-fail guard for the Node gate (evidence review revision; the earlier "add a serial `-n 0` step" wiring rested on the falsified timeout hypothesis).

## Program Design

### Types

- No new types. The JS fix touches test-side helper plumbing only; `createSubmissionController`'s `subtle` injection point (`scripts/little_loops/templates/policy_builder_core.mjs`) already exists.

### Signatures

- `settleHash(env) -> Promise<void>` and `reviewed(env, yaml = YAML) -> Promise<void>` — in `scripts/tests/js/policy_submission.test.mjs`; the bounded turn spin becomes a real completion wait (or an explicit digest resolution once `subtle` is injected)
- `setup(over = {})` — same file; currently hardcodes `subtle: globalThis.crypto.subtle` (L72) and becomes injectable so tests control digest completion
- `test_node_conformance_suite_passes() -> None` — in `scripts/tests/test_policy_builder_node_gate.py`; loses `@pytest.mark.no_parallel` (L53) and gains `@pytest.mark.timeout(240)`
- `pytest_collection_modifyitems(config, items) -> None` — in `scripts/tests/conftest.py`; unchanged, only this test's marker changes

### Call Path

`test_node_conformance_suite_passes` -> `_node_major` -> `subprocess.run` (`node --test scripts/tests/js/*.test.mjs`, 180s timeout) -> `policy_submission.test.mjs` `reviewed` -> `settleHash` -> `createSubmissionController.review` -> `sha256Hex` -> `crypto.subtle.digest`

### Behavior Notes

- Under `-n N` the controller only collects and distributes work, so a `no_parallel` skip means the test does not execute at all in parallel mode. That is why the marker dorms the gate, and why removing it (rather than adding a serial CI step) is the cheaper restoration path.
- The controller leaves `review.status = "hashing"` while the digest is outstanding and only reaches `ready`/`refused` from the digest's settle handlers, so any wait shorter than the digest's actual completion observes `hashing` — there is no third state to misinterpret.

## Impact

- **Priority**: P3 at capture — **revisit**. Scope has grown from "one marker on one test" to "the ratified FEAT-2390 JS gate is dormant in CI **and** the flake that justified that is a live test-side race in 231 assertions' worth of coverage". Reviewers may want P2.
- **Effort**: Small — rewrite one JS helper plus a regression test, remove one marker, add one skip-to-fail guard, refresh docs
- **Risk**: Low — test-side and CI-visibility changes only; removing the marker adds coverage rather than removing it
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-20 | Priority: P3

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_Revised 2026-09-20 after the evidence review; the original list assumed the timeout hypothesis._

- Fix the wait in `scripts/tests/js/policy_submission.test.mjs` (`settleHash` / `setup` `subtle` injection) and add the starvation regression test
- Remove `@pytest.mark.no_parallel` from `test_node_conformance_suite_passes`, add `@pytest.mark.timeout(240)`, and refresh the module docstring ("no hosted CI", "ships Node 22")
- Add the skip-to-fail guard for a missing Node toolchain in `.github/workflows/ci.yml`, and include the Node version in the gate's failure message
- Update `docs/development/TESTING.md` (`no_parallel` row wording) and `docs/development/TROUBLESHOOTING.md` (the "tests still run" claim)
- Verify the `.claude/CLAUDE.md` / `AGENTS.md` gate-example wording still holds once the gate executes again
- Re-run `scripts/tests/test_conftest_cap.py` (`TestNoParallelMarkerRouting`)

## Session Log
- `/ll:wire-issue` - 2026-09-20T21:53:51 - `80e0a309-7358-453f-8fdc-92553921aa72.jsonl`
- `/ll:refine-issue` - 2026-09-20T21:21:36 - `09272224-9351-4571-a369-7e216b7645b5.jsonl`
- `/ll:format-issue` - 2026-09-20T21:17:56 - `4117c50f-02ee-4b8b-8840-0c4b382de04b.jsonl`

## Verification Evidence

_Added 2026-09-20 by an evidence review of the CI artifacts — this section exists so the root cause below is falsifiable without re-deriving it. Artifacts were fetched with `gh run download <run-id>`._

### The three cited runs

| Run | Branch / SHA | Trigger | Result | JS suite |
| --- | --- | --- | --- | --- |
| `35490420257` | `main @ fdf6773d2` | push | failure | `# tests 231 / # pass 227 / # fail 4 / # duration_ms 438.873238` |
| `35490447772` | `enh/ll-loop-rename-and-cleanup @ 2f84ad50` | workflow_dispatch | success | not a same-base comparison |
| `35490782202` | `fix/bug-3484-addopts-suppression-restored @ b5ab95ad` | workflow_dispatch | failure | `# fail 1`, same assertion |

### What the failing runs actually contain

- Failures: `not ok 52` (L158), `not ok 58` (L263), `not ok 59` (L297), `not ok 71` (L478) in run `35490420257`; `FAIL` at L478 only in run `35490782202`. Every one is `Expected values to be strictly equal: 'hashing' !== 'ready'` (`ERR_ASSERTION`), stack `reviewed (policy_submission.test.mjs:90:10)`.
- No worker kill: `0` occurrences of `crashed`, `Timeout >`, `INTERNALERROR`; both runs complete normally (`1 failed, 24120 passed, 55 skipped … in ~920s`). The `pytest-timeout` thread-method `os._exit(1)` mechanism is real but never fired here.
- No timeout pressure: the node subprocess used **438 ms** of its 180-second budget — 0.24%. A watchdog (120s) below the inner budget (180s) is a genuine latent hazard, but it is not what failed.

### Why the race is real and reproducible

- `settleHash` bounds its wait at 50 `setImmediate` turns (`scripts/tests/js/policy_submission.test.mjs:44-49`); `review` sets `hashing` and settles from `sha256Hex(yaml, d.subtle).then(...)` (`scripts/little_loops/templates/policy_builder_core.mjs:4428-4441`), i.e. a real threadpool round-trip.
- Idle: 50 turns ≈ 0.74 ms vs digest p50 0.011 ms → passes ~always.
- Threadpool starved: the identical wait observes `hashing` after 2.16 ms → the CI assertion.
- A 40-run loop of `node --test scripts/tests/js/policy_submission.test.mjs` under 48 CPU hogs on a 14-core machine reproduced **0** failures, which is consistent with the mechanism being threadpool-scheduling-dependent rather than purely CPU-bound: the deterministic starvation recipe above is the reliable reproducer, and the right basis for a regression test.

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis (hypothesis since falsified):_

- **File**: `scripts/tests/test_policy_builder_node_gate.py`, `test_node_conformance_suite_passes` — the inner `subprocess.run(..., timeout=180)` carried no `@pytest.mark.timeout`, so the suite-wide 120s thread-method pytest-timeout budget applied. Because the watchdog budget (120s) is below the inner budget (180s), a slow `node --test` under contention would be killed by the thread watchdog, hard-killing the xdist worker before `TimeoutExpired` could fire. Convention violated: `test_verify_evidence.py` keeps the per-test cap strictly above the inner subprocess timeout (`GATE_TIMEOUT + 30`). This was a hypothesis from static reading; no failing CI log was inspected.
- The JS files in `scripts/tests/js/` use injected fake clocks (`policy_submission.test.mjs`, `policy_validator.test.mjs`), not wall-clock waits — the only real-time limit appeared to be the Python-side timeout.

### Verified root cause (evidence review, 2026-09-20)

The flake is a **test-side synchronization defect in `scripts/tests/js/policy_submission.test.mjs`**, and the marker that was added for it removes the gate instead of fixing it:

- `settleHash` (L44-49) waits for `review.status !== "hashing"` by spinning at most 50 `setImmediate` turns. That is a turn budget, not a completion signal. The awaited work is a real `crypto.subtle.digest` (injected as `globalThis.crypto.subtle` at L72), whose completion is delivered through the libuv threadpool. When the threadpool thread is descheduled — as on a saturated 4-vCPU runner alongside ~24k other tests — the digest lands *after* the 50 turns are exhausted, and the assertion at L90 sees `hashing`.
- Both falsified alternatives fail on the evidence: the 180-second subprocess budget was 0.24% consumed, and no worker crash or watchdog kill appears in either log. A Node-version-driven behavior change would not produce a varying failure count (4 vs 1) on a single bounded-spin helper, and `subtle` was present and functioning in both runs (an absent or rejecting `subtle` would surface as `refused`, never as a lingering `hashing`).
- Consequence of the marker: `pytest_collection_modifyitems` skips the item on every xdist worker and the controller runs no tests, so the FEAT-2390 JS gate — the "real, named, enforced location" FEAT-2390 requires — executes nowhere in CI. Green CI now also hides the very race that prompted the change.
