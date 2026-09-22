---
id: BUG-3522
type: BUG
title: policy-builder node conformance gate is dormant in CI and the flake is a JS
  hash-completion race
priority: P2
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
- BUG-3486
- BUG-3502
- BUG-3484
- BUG-2523
- BUG-3523
confidence_score: 100
outcome_confidence: 64
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 0
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

_Superseded. The capture-era timeout hypothesis is falsified by the CI artifacts; the suggested Node 20 → 24 attribution is unsupported because the runner version was not captured. See `## Root Cause` § "Verified root cause" and `## Verification Evidence`._

## Proposed Solution

1. **Fix the wait, not the schedule** in `scripts/tests/js/policy_submission.test.mjs`: replace the bounded `settleHash` spin with an **exact completion signal from the controller's own `onChange` subscription** (review revision, 2026-09-22). `createSubmissionController` already exposes `onChange(cb)` (`scripts/little_loops/templates/policy_builder_core.mjs:4537`), and every `review.status` transition goes through `emit()`. `settleHash` becomes: if `review.status !== "hashing"` return immediately (synchronous refusals never enter `hashing`); otherwise subscribe, resolve on the first emit where `status !== "hashing"`, unsubscribe, then `await flush()`. Keep readiness assertions in `reviewed()`, outside the listener: `emit()` catches listener exceptions, so an assertion thrown inside the callback can be swallowed. This observes the exact state transition the assertion at L90 reads, needs no wrapper around `subtle`, keeps the real `crypto.subtle` threadpool path the CI race was about, and works unchanged with any `subtle` a test injects via `over.subtle` (add that passthrough to `setup()` — it is not there today; L72 hardcodes `globalThis.crypto.subtle`). Shapes to avoid: a fully fake `subtle` (loses the real threadpool path across all ~25 `reviewed()` call sites); timer-based polling against a generous deadline (reintroduces the time-dependence being fixed); and the earlier draft's capturing wrapper that records each `digest` promise into `env.pendingDigests` — workable, but it waits on an intermediate promise and then leans on the 12-tick `flush()` to reach the controller's `.then` handler, where `onChange` waits on the terminal state itself.
2. **Add a deterministic regression test for the race** — no wall-clock, no threadpool: inject via `over.subtle` a `subtle` whose `digest` returns a manual deferred, release it on a `setImmediate` turn past the old budget (e.g. turn 60 of 50), then await `reviewed()`. The old spin helper exhausts its turns before the release and fails with `'hashing' !== 'ready'`; the exact wait resolves on the `ready` emit and passes. The pbkdf2 threadpool-starvation recipe in Steps to Reproduce stays a manual demonstrator — it is threadpool-scheduling-dependent (the 40-run loop under 48 CPU hogs reproduced 0 failures) and must not be the CI regression test. Also cover a deferred digest rejection and an already-refused review: `settleHash()` must finish on refusal, unsubscribe when it subscribed, and let the readiness assertion in `reviewed()` reject promptly.
3. **Drop `@pytest.mark.no_parallel`** from `test_node_conformance_suite_passes` once (1) lands: with the race gone there is nothing for contention to break, and the gate returns to the default parallel invocation. Pair that with `@pytest.mark.timeout(240)` — strictly above the inner `timeout=180` — following the convention in `scripts/tests/test_verify_evidence.py`. Without it, a hung node process trips the 120-second thread watchdog first, whose `os._exit(1)` kills the worker instead of producing a clean `TimeoutExpired` assertion.
4. **Make a skip loud through one shared Python guard** (review revision, 2026-09-22). Route both `test_node_conformance_suite_passes` and the five round-trip validations through `_require_node()`. When `LL_REQUIRE_NODE=1`, unavailable or unusable Node must fail; with the variable unset, preserve graceful skips. Set the variable on the existing `unit-tests` job. Probe `node --version` once per guard call and preserve stdout, stderr, exit status, and exception/timeout details alongside the parsed major. A nonzero probe exit is unusable even if stdout resembles a supported version. Missing Node must report that the executable was not found; it cannot provide version output.
   - Add mocked guard tests for missing Node, Node <22, malformed version output, nonzero probe exit, `OSError`, and `TimeoutExpired`, with `LL_REQUIRE_NODE=1` and with it unset. Assert fail versus skip and useful diagnostics; also cover successful Node >=22. Verify both gate entry points use the shared guard. Keep these guard-policy tests in a separate test module so the existing gate module remains six executable cases.
   - **Runner-Node contingency:** the runner's Node version is unverified — no artifact captured it, only the path `/usr/local/bin/node`. If the guard reveals missing or too-old Node on the existing runner, add `actions/setup-node` configured for `22.x` or newer to the existing `unit-tests` job. This provisions the required toolchain; it does not change the supported Node >=22 policy or add another CI job.

The non-recursive `JS_TEST_DIR.glob("*.test.mjs")` stays unchanged. The nested `feat3304` dashboard tests already have their own Python gate; moving or duplicating that ownership is out of scope.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- **Conventions in force**: a timing-sensitive or long-subprocess test is marked `no_parallel` (runs only under serial `-n 0`); tests needing more than the 120s default set `@pytest.mark.timeout(N)` strictly above any inner subprocess timeout (`test_verify_evidence.py`). The codebase disagrees on dormancy: `test_worktree_utils.py` (BUG-2650) explicitly rejects `no_parallel` because it is dormant under the default CI command, and instead runs a nested `-n 0` pytest.
- Any resolution must keep the gate exercised somewhere (CLAUDE.md § Testing & CI Policy requires other-toolchain gates to run under the pytest suite), and must keep `test_conftest_cap.py::TestNoParallelMarkerRouting` passing.
- **Superseded framing** (evidence review, 2026-09-20): the open trade-off recorded here — "accept a dormant gate, add a serial CI invocation, or drop `no_parallel` in favor of a `timeout` marker above 180" — assumed the flake was a timeout budget mismatch. It is not (`## Root Cause`). Dormancy and a serial CI step are both unnecessary; the JS helper's wait is the defect, and `no_parallel` can come off entirely.

## Acceptance Criteria

- A regression test reproduces the race deterministically — deferred digest released past the old 50-turn budget; no wall-clock, no threadpool dependence — and fails against the old spin helper while passing with the exact wait, in `scripts/tests/js/policy_submission.test.mjs`. The old helper is deleted in the same commit, so the fails-before/passes-after demonstration exists **only** in the PR description (or a two-commit stack); the reviewer checks it there. Do not keep a dead copy of the spin helper in-tree to make the demo self-contained
- Rejected-digest and already-refused-review tests prove `settleHash()` finishes on refusal, releases its subscription when present, and lets `reviewed()` reject through its readiness assertion outside the listener. Delayed success still unsubscribes normally
- **Pre-merge readiness:** with Node >=22 installed, `LL_REQUIRE_NODE=1 python -m pytest scripts/tests/test_policy_builder_node_gate.py -n 2` reports **6 passed, zero skipped**; the separate guard-policy tests pass; and `python -m pytest scripts/tests/` exits 0
- `test_node_conformance_suite_passes` **executes** (not skipped) in the `unit-tests` job of `.github/workflows/ci.yml` on a push to `main`, and the uploaded `pytest-junit.xml` shows it as passed — no serial `-n 0` step required
- **Post-merge closure evidence (separate from pre-merge readiness):** at least one post-merge CI run on `main` is green with the gate executed, and its `pytest-junit.xml` artifact is cited as evidence that green means executed, not skipped. The deterministic regression test carries the correctness burden; further re-runs (`workflow_dispatch` on `main`) are optional confidence, not a gate — the earlier "5+ consecutive runs" bar was ceremony for a push-only workflow (review revision, 2026-09-21)
- `scripts/tests/test_conftest_cap.py::TestNoParallelMarkerRouting` still passes, and no other test's marker semantics change
- Both Node gates use `_require_node()`. Mocked tests cover missing Node, Node <22, malformed output, nonzero probe exit, `OSError`, and probe timeout: each fails with `LL_REQUIRE_NODE=1` and skips with the variable unset. Node >=22 with a successful probe is accepted. Diagnostics preserve available stdout/stderr, exit status, or exception details without a second probe; missing Node explicitly reports the missing executable
- `test_round_trip_yaml_validates_for_each_mode` and the `feat3304` dashboard runtime gate are unaffected

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- The Program Design note that "runs on the controller" means "runs only in serial `-n 0`" makes the old AC 1 (5+ consecutive CI runs pass) trivially satisfiable by dormancy; a real criterion needs the gate to execute in at least one CI invocation. **Addressed:** the criteria above now require execution in the default parallel job and cite the junit artifact as proof.
- The old AC that pinned `actions/setup-node` is dropped: no artifact ties the failure to a Node version, and the proposed pin contradicted itself (`22.x.y` in the AC vs 24.x.y in Notes). See `## Notes`.

## Notes

- **The "Node 20 → 24 migration" framing is unsupported.** The Node version was never captured in the failure evidence — the artifacts contain `pytest.log`/`pytest-junit.xml`, and the only version visible is the executable path `/usr/local/bin/node`. This checkout's `node --version` is v26.0.0. The evidence establishes a synchronization defect; it does not establish or rule out Node-version influence on its frequency.
- **The cited "2-fail / 1-pass on the same base" comparison does not hold.** Run `35490420257` failed on `main @ fdf6773d2`; the passing run `35490447772` was a `workflow_dispatch` on `enh/ll-loop-rename-and-cleanup @ 2f84ad50`; the second failing run `35490782202` was a `workflow_dispatch` on `fix/bug-3484-addopts-suppression-restored @ b5ab95ad`. Three different trees, not one base. The nondeterminism is still established — but by the varying failure count (4 vs 1) on the same helper, not by the run tally.
- **Node provisioning is conditional:** use the Runner-Node contingency in Proposed Solution 4 if the required-toolchain guard finds Node absent or too old. No version pin is needed to explain or fix the hash race itself; provisioning must preserve support for Node >=22.
- The marker commit `60358e836` repeated the unverified timeout hypothesis in its message ("intermittently exceeds time budgets or hits timing-sensitive assertions"). That message is now the main reason the wrong theory is in circulation.
- ENH-3453 (host capability map) was dropped from `relates_to` on 2026-09-21 — it was a BUG-3453 → BUG-3521 → BUG-3522 renumber-chain artifact, not a real relationship.
- **The interleaving test at line 158 is only half-racy** (review correction, 2026-09-21): its first assertion (`review.status === "none"` after `contextChanged`) is already deterministic — `contextChanged` resets review synchronously (`scripts/little_loops/templates/policy_builder_core.mjs:4387`) — so only its `reviewed()` call needs the fixed wait. An earlier draft of Proposed Solution 1 called the whole test "racy"; implementers should not re-engineer the synchronous part. Note also that the digest started by the abandoned first `review` still resolves later; its `.then` handler is fenced by the `gen !== reviewGen` check, so it never emits, and the `onChange` wait in the subsequent `reviewed()` is unaffected — this is harmless and needs no handling.
- **Sibling dormancy, out of scope — filed as BUG-3523:** `scripts/tests/test_feat3323_sse_bridge.py:215` (`TestSseBridgeFanIn::test_two_producers_reach_one_client_with_distinct_producer_pid`) carries `@pytest.mark.no_parallel` with no `integration`/`conformance` marker and no `-n 0` invocation anywhere, so it is CI-dormant by the identical mechanism (verified locally 2026-09-21: under `-n 2` the file reports the fan-in test among its skips). A sweep of all `no_parallel` users found no other genuine cases: `test_fsm_signal_integration.py` is doubly excluded by its `integration` marker; `test_dependency_mapper.py` / `test_worktree_utils.py` are name/comment matches only. Keep it out of this fix; the structural follow-up — a meta-guard that makes `no_parallel`-without-serial-invocation visible instead of silent — belongs there.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- **Marker already landed**: `@pytest.mark.no_parallel` was added by `60358e836` (2026-09-20, `fix(tests): mark node conformance test no_parallel (BUG-3521) (#33)`), after the cited runs on `main @ fdf6773d2` (2026-09-19). The marker is the second half of this bug, not the fix.
- **Consequence of the marker**: `scripts/tests/conftest.py:pytest_collection_modifyitems` skips `no_parallel` items on xdist workers; the controller never runs tests under `-n N`. With `-n logical` in addopts, the gate never executes in either `.github/workflows/ci.yml` job (`unit-tests` on `ubuntu-latest`, `conformance` on self-hosted with `-m conformance`; the test has no `conformance` marker). No workflow step runs `-n 0`, so the FEAT-2390 policy-builder JS gate is currently dormant in CI.
- **Dependent/precedent files**: `scripts/tests/test_fsm_signal_integration.py` (module-level `pytestmark`, BUG-2523), `scripts/tests/test_feat3323_sse_bridge.py` (BUG-3484, stacked with `@pytest.mark.timeout(180)`), `scripts/tests/test_conftest_cap.py:TestNoParallelMarkerRouting` (hook contract), `docs/development/TESTING.md` (marker table ~L1050), `docs/development/TROUBLESHOOTING.md` (BUG-2523 section ~L825).
- **CI Node**: `.github/workflows/ci.yml` has no `actions/setup-node` and no `node-version`; Node comes from the runner image. The Node-pin acceptance criterion would be the first Node pin in the repo.
- **Removed historical AC references that do not resolve**: `test_node_22plus_runs_ok` and `test_node_test_runner_emits_tap_v13` do not exist anywhere; the sibling test in the file is `test_round_trip_yaml_validates_for_each_mode` (no `no_parallel`, inner `timeout=30`).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — § Testing & CI Policy cites `test_policy_builder_node_gate.py` as the enforced example of a wrapped other-toolchain gate; a dormant gate under default `-n logical` contradicts that claim [Agent 2 finding]
- `AGENTS.md` — mirrors the same `test_policy_builder_node_gate.py` reference; keep consistent with CLAUDE.md [Agent 2 finding]
- `scripts/tests/test_policy_builder_node_gate.py` — module docstring (L1-17) says "no hosted CI … single enforced location is the local suite" and "this repo's environment ships Node 22"; both are stale (`.github/workflows/ci.yml` exists; this checkout ships 26; the runner's Node major is **unverified** — no artifact captured it, see the Runner-Node contingency under Proposed Solution 4) — update alongside any resolution [Agent 1 finding; runner-version claim corrected 2026-09-22]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md` — marker table row for `no_parallel` (~L1050) says "runs on the controller or in a serial `-n 0` invocation"; under `-n N` the controller runs no tests, so reword to "serial `-n 0` only" [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — the BUG-2523 section (~L825) asserts "The tests still run — they just don't share cores"; for a gate whose only CI invocation is `-n logical`, that is exactly the false assumption this issue falsifies [evidence review addition]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/js/policy_submission.test.mjs` — `settleHash` (L44-49), `reviewed` (L87-91) and `setup` (L71-81) are the primary fix site; the race is here, not in the Python gate [evidence review addition]
- `scripts/little_loops/templates/policy_builder_core.mjs:4537` — `onChange(cb)` on the controller is the completion signal the fixed `settleHash` subscribes to; every `review.status` transition passes through `emit()` (L3864) [review addition, 2026-09-22]
- A separate Python guard-policy test module — mock executable discovery and version probing to cover the success/failure/skip matrix and both callers of `_require_node()`; keep the six real gate cases in their existing module
- `scripts/tests/test_conftest_cap.py` — `TestNoParallelMarkerRouting` must keep passing if the marker is changed/removed [Agent 3 finding]
- `scripts/tests/js/feat3304/feat3304_dashboard_runtime.test.mjs` — lives in a subdir, so the gate's non-recursive `JS_TEST_DIR.glob("*.test.mjs")` never runs it; it is nevertheless executed in CI by `scripts/tests/test_feat3304_artifact_dashboard.py::TestDashboardNodeRuntimeGate::test_generated_page_runtime_behaviour` (no `no_parallel`, inner `timeout=180`) — scope the "the gate covers X" discussion accordingly [Agent 3 finding, corrected during evidence review]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `.github/workflows/ci.yml` — **no** serial `-n 0` step is needed once the race is fixed: removing `no_parallel` restores the gate to the existing parallel `unit-tests` invocation. The required workflow change is setting `LL_REQUIRE_NODE=1` on the `unit-tests` job, with conditional Node provisioning as specified in Proposed Solution 4 — the skip-to-fail logic itself lives in the Python test module, because a workflow step cannot see the "node present but < 22" skip path (review revision, 2026-09-21; the earlier "add a serial `-n 0` step" wiring rested on the falsified timeout hypothesis).

## Verification Notes

_Added by `/ll:verify-issues --auto` — 2026-09-22._

**Verdict: EVIDENCE_UNVERIFIED** (check B7, `ll-verify-evidence`), on a single flagged
span — advisory only, does not reflect on the issue's substance:

- `## Current Behavior` (L36) paraphrases `scripts/pyproject.toml`'s `addopts` as the
  single string `--timeout=120 --timeout-method=thread -n logical --dist loadfile`.
  The file stores these as a TOML list (`addopts = ["--timeout=120",
  "--timeout-method=thread", "-n", "logical", "--dist", "loadfile", ...]`,
  `scripts/pyproject.toml:271-280`) — the checker can't match a reformatted-into-prose
  span, which is the documented low-precision "paraphrase" class the command's own
  advisory-verdict decision names, not a fabricated claim. Every flag named is
  verifiably present and correctly attributed.

Everything else checked clean, including several claims re-verified independently of
the flagged span (line-exact, not just presence):
- `settleHash`/`setup`/`reviewed` in `scripts/tests/js/policy_submission.test.mjs`
  (L44-49, L56/L71-81, L87-91) and the `subtle` injection at L72 — exact.
- `contextChanged`'s synchronous reset at
  `scripts/little_loops/templates/policy_builder_core.mjs:4387`, and the
  `review`/`sha256Hex` hashing path at L4428-4441 — exact (the causal/identity claim
  in `## Notes` re: line 158 being only half-racy was read directly against this
  code, not inferred).
- CI shape: `.github/workflows/ci.yml` push-only (no `pull_request`), `unit-tests` on
  `ubuntu-latest` with no `-n` override (inherits `-n logical` from addopts),
  `conformance` on self-hosted Thinky with `-m conformance` — `test_node_conformance_suite_passes`
  carries no `conformance` marker, so it is unreachable in either job as described.
- `docs/development/TESTING.md:1050` and `docs/development/TROUBLESHOOTING.md:827`
  quotes match verbatim; `.claude/CLAUDE.md:153` / `AGENTS.md:153` both cite the gate
  test file as claimed.
- `node --version` on this checkout is v26.0.0, confirming the "Notes" claim.
- `test_node_22plus_runs_ok` / `test_node_test_runner_emits_tap_v13` (old AC refs)
  confirmed absent; `_require_node`, `JS_TEST_DIR.glob("*.test.mjs")` (non-recursive)
  confirmed present/as-described.
- Sibling-dormancy sweep confirmed: `test_fsm_signal_integration.py:42` module
  `pytestmark` includes both `integration` and `no_parallel`; `test_feat3323_sse_bridge.py:215-216`
  stacks `no_parallel` + `timeout(180)`; `test_worktree_utils.py`/`test_dependency_mapper.py`
  hits are comment/name matches only, no actual marker usage. `BUG-3523` exists,
  status `open`, matching the "filed as BUG-3523" note.
- No active required decision-log rules (`ll-issues decisions list --type rule
  --enforcement required --active-only` empty) — no `DECISIONS_VIOLATION` possible.
- All `relates_to` IDs (BUG-3486, BUG-3502, BUG-3484, BUG-2523, BUG-3523) resolve to
  existing issue files.

The earlier verification described the now-abandoned capturing wrapper. The current
proposal uses the controller's `onChange` subscription with assertions outside its
listener. The 2026-09-22 review added refusal coverage, a shared Node guard and its
failure/skip matrix, and explicit pre-merge checks; those requirements are reflected
in the Acceptance Criteria and Implementation Steps.

**Review evidence, 2026-09-22:** the affected Python module under `-n 2` reproduced
`5 passed, 1 skipped`. A standalone probe using the real controller and a deferred
digest released after 60 `setImmediate` turns observed `hashing` with the old helper
and `ready` with the proposed subscription. This supports the design; implementation
must still add the regression tests and run the pre-merge checks above.

## Program Design

### Types

- No new production types. The Python version probe may use a small result dataclass for the parsed major and diagnostics; the JS fix touches test-side helper plumbing only; `createSubmissionController`'s `subtle` injection point (`scripts/little_loops/templates/policy_builder_core.mjs`) already exists.

### Signatures

- `settleHash(env) -> Promise<void>` and `reviewed(env, yaml = YAML) -> Promise<void>` — in `scripts/tests/js/policy_submission.test.mjs`; the bounded turn spin becomes an `onChange` subscription that resolves on the first emit where `review.status !== "hashing"` (returning immediately if not hashing), unsubscribes, then `await flush()` — an exact wait on the terminal state the assertion reads
- `setup(over = {})` — same file; the hardcoded `subtle: globalThis.crypto.subtle` (L72) becomes `over.subtle || globalThis.crypto.subtle` so the regression test can inject a manually-deferred digest; no wrapper layer
- `test_node_conformance_suite_passes() -> None` — in `scripts/tests/test_policy_builder_node_gate.py`; loses `@pytest.mark.no_parallel` (L53) and gains `@pytest.mark.timeout(240)`
- `_node_major(node) -> tuple[int | None, str]` (or a small result dataclass) — same file; returns the usable major and diagnostics from a single probe, including stdout/stderr, exit status, and exception/timeout details. Nonzero exit or a failed probe never yields a usable major
- `_require_node() -> str` — same file; shared by both gate entry points. Under `LL_REQUIRE_NODE=1` converts unavailable/unusable Node into failure; otherwise skips. Includes probe diagnostics when available, or an explicit executable-not-found message
- `pytest_collection_modifyitems(config, items) -> None` — in `scripts/tests/conftest.py`; unchanged, only this test's marker changes

### Call Path

`test_node_conformance_suite_passes` -> `_require_node` -> `_node_major` -> `subprocess.run` (`node --test scripts/tests/js/*.test.mjs`, 180s timeout) -> `policy_submission.test.mjs` `reviewed` -> `settleHash` -> `createSubmissionController.onChange` (resolves on the `ready`/`refused` emit) <- `emit` <- `startReview`'s `sha256Hex(...).then(...)` <- `crypto.subtle.digest`

### Behavior Notes

- Under `-n N` the controller only collects and distributes work, so a `no_parallel` skip means the test does not execute at all in parallel mode. That is why the marker dorms the gate, and why removing it (rather than adding a serial CI step) is the cheaper restoration path.
- The controller leaves `review.status = "hashing"` while the digest is outstanding and only reaches `ready`/`refused` from the digest's settle handlers, so any wait shorter than the digest's actual completion observes `hashing` — there is no third state to misinterpret.

## Impact

- **Priority**: P2 (bumped from P3 on 2026-09-21). The ratified FEAT-2390 bar — "an unenforced gate does not count as met" — is currently violated, and green CI is actively misleading: it hid the very race that prompted the marker. Not P1: no user-facing breakage, and the fix is test-side and CI-visibility only.
- **Effort**: Small — rewrite one JS helper plus a regression test, remove one marker, add one skip-to-fail guard, refresh docs
- **Risk**: Low — test-side and CI-visibility changes only; removing the marker adds coverage rather than removing it
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-20 | Priority: P2 (bumped from P3, 2026-09-21)

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_Revised 2026-09-20 after the evidence review; the original list assumed the timeout hypothesis._

- Fix the wait in `scripts/tests/js/policy_submission.test.mjs`: `settleHash` subscribes via `ctl.onChange` and resolves on the first emit where `review.status !== "hashing"`; `setup()` gains an `over.subtle` passthrough (no wrapper)
- Add the deterministic race regression test (deferred digest injected via `over.subtle`, released past the 50-turn budget — no wall-clock, no threadpool), and record the fails-before/passes-after demonstration in the PR description; delete the old spin helper, do not keep it in-tree
- Remove `@pytest.mark.no_parallel` from `test_node_conformance_suite_passes`, add `@pytest.mark.timeout(240)`, and refresh the module docstring ("no hosted CI", "ships Node 22")
- Add rejected-digest and already-refused-review tests, including subscription cleanup; keep all readiness assertions outside the `onChange` listener
- Preserve version-probe diagnostics and reject unsuccessful probes; consolidate both Node gates through `_require_node()` with the `LL_REQUIRE_NODE=1` fail / unset skip policy. Add the mocked guard matrix in a separate test module; set the env var on the existing `unit-tests` job
- If the first `LL_REQUIRE_NODE=1` run reveals missing or too-old Node on the runner, add `actions/setup-node` pinned to `22.x`+ to the `unit-tests` job (free action, not paid CI)
- Do **not** scope in the `test_feat3323_sse_bridge.py:215` sibling dormancy — that is BUG-3523. Keep the JS glob and the existing nested dashboard gate ownership unchanged
- Update `docs/development/TESTING.md` (`no_parallel` row wording) and `docs/development/TROUBLESHOOTING.md` (the "tests still run" claim)
- Verify the `.claude/CLAUDE.md` / `AGENTS.md` gate-example wording still holds once the gate executes again
- Re-run `scripts/tests/test_conftest_cap.py` (`TestNoParallelMarkerRouting`), the new guard-policy tests, and `LL_REQUIRE_NODE=1 python -m pytest scripts/tests/test_policy_builder_node_gate.py -n 2` (6 passed, zero skipped). Run the full local suite before merge
- After merge, cite a green `main` CI run and its JUnit artifact showing the gate passed as closure evidence

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-22_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across ~25 call sites: the Proposed Solution notes the `settleHash`/`reviewed` fix "loses the real threadpool path across all ~25 `reviewed()` call sites" if done wrong — a wide blast radius by caller count even though every call site is same-file and mechanically uniform. Mitigation: the deterministic regression tests specified in the Acceptance Criteria (deferred-digest race, rejected-digest, already-refused-review) exercise this shared path directly before the marker is dropped, so a regression surfaces at the helper, not scattered across 25 individually-audited sites.

## Session Log
- `/ll:confidence-check` - 2026-09-22T15:56:07 - `68851bf3-365d-45b2-b4f4-498d3742ec29.jsonl`
- `/ll:verify-issues` - 2026-09-22T15:27:50 - `5972c48c-9075-49d4-83d4-288f2927cb32.jsonl`
- `/ll:refine-issue` - 2026-09-22T15:21:53 - `83f6ed80-53e1-4d9e-8978-6a6d02a3e6c7.jsonl`
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
- A 40-run loop of `node --test scripts/tests/js/policy_submission.test.mjs` under 48 CPU hogs on a 14-core machine reproduced **0** failures, which is consistent with the mechanism being threadpool-scheduling-dependent rather than purely CPU-bound: the deterministic starvation recipe above is the reliable *manual* reproducer. _(Correction, 2026-09-21: this originally called the starvation recipe "the right basis for a regression test" — withdrawn; precisely because it is threadpool-scheduling-dependent, the CI regression test is the deferred-digest design in Proposed Solution 2, with starvation kept for manual demonstration.)_

## Root Cause

_The 2026-09-20 `/ll:refine-issue` hypothesis (120s pytest-timeout watchdog below the 180s inner subprocess budget hard-killing the worker) was a static-reading guess later falsified by the CI logs: no worker kill, 0.24% of the budget used. Its one surviving point — the watchdog/inner-budget inversion is a real latent hazard — is carried by Proposed Solution 3's `timeout(240)` marker._

### Verified root cause (evidence review, 2026-09-20)

The flake is a **test-side synchronization defect in `scripts/tests/js/policy_submission.test.mjs`**, and the marker that was added for it removes the gate instead of fixing it:

- `settleHash` (L44-49) waits for `review.status !== "hashing"` by spinning at most 50 `setImmediate` turns. That is a turn budget, not a completion signal. The awaited work is a real `crypto.subtle.digest` (injected as `globalThis.crypto.subtle` at L72), whose completion is delivered through the libuv threadpool. When the threadpool thread is descheduled — as on a saturated 4-vCPU runner alongside ~24k other tests — the digest lands *after* the 50 turns are exhausted, and the assertion at L90 sees `hashing`.
- Both falsified alternatives fail on the evidence: the 180-second subprocess budget was 0.24% consumed, and no worker crash or watchdog kill appears in either log. The varying failure count (4 vs 1) is consistent with nondeterminism in the bounded-spin helper; it does not rule out Node-version influence on timing. No Node version was captured, so that attribution remains unsupported. The observed `hashing` state shows the readiness assertion ran before a terminal hash result was handled; it does not by itself prove the eventual digest result.
- Consequence of the marker: `pytest_collection_modifyitems` skips the item on every xdist worker and the controller runs no tests, so the FEAT-2390 JS gate — the "real, named, enforced location" FEAT-2390 requires — executes nowhere in CI. Green CI now also hides the very race that prompted the change.
