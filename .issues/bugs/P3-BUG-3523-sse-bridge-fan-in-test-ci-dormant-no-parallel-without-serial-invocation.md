---
id: BUG-3523
type: BUG
title: "SSE bridge fan-in test is CI-dormant \u2014 no_parallel marker with no serial\
  \ invocation anywhere"
priority: P3
status: done
discovered_by: manual
discovered_date: '2026-09-21'
captured_at: '2026-09-21T02:43:58Z'
completed_at: '2026-09-22T19:59:18Z'
labels:
- test-stability
- xdist
- ci
- sse-bridge
relates_to:
- BUG-3522
- BUG-3484
- BUG-2523
- FEAT-3323
learning_tests_required:
- pytest
- pytest-timeout
- pytest-xdist
decision_needed: false
confidence_score: 95
outcome_confidence: 79
verify_verdict: VALID
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
reconcile_attempted: true
---

# BUG-3523: SSE bridge fan-in test is CI-dormant — no_parallel marker with no serial invocation anywhere

## Summary

<!-- ll-prose-ok: no_parallel is a pytest marker name (registered via decorator/keyword), not a def-site symbol; not a stale reference -->
`scripts/tests/test_feat3323_sse_bridge.py::TestSseBridgeFanIn::test_two_producers_reach_one_client_with_distinct_producer_pid` — the only end-to-end fan-in test for the FEAT-3323 SSE bridge (two producers, one client, distinct `producer_pid` attribution) — **never executes in CI**. It carries `@pytest.mark.no_parallel` (stacked on `@pytest.mark.timeout(180)`, added for BUG-3484), and the dormancy mechanism verified end-to-end in BUG-3522 applies verbatim: `pytest_collection_modifyitems` in `scripts/tests/conftest.py` skips `no_parallel` items on every xdist worker, the controller runs no tests under `-n N`, the `scripts/pyproject.toml` addopts pin `-n logical`, and no invocation in `.github/workflows/ci.yml` (or anywhere else) runs a serial `-n 0` pass. The test has no `integration`/`conformance` marker, so the `unit-tests` job's `-m "not integration and not conformance"` filter does not exclude it — it is collected, then skipped on the worker. A green `unit-tests` job says nothing about SSE fan-in.

Unlike BUG-3522, the marker here was added for a **legitimate wall-clock reason** — the test's own comment block (`test_feat3323_sse_bridge.py:201-214`) documents per-step timeout budgets summing to ~100-105s and historical execution under full-suite xdist contention exceeding the suite-wide `--timeout=120` and even `timeout(180)`, and pytest-timeout's thread-method watchdog cannot interrupt a blocked C-level `recv()`/thread-join, so it hard-kills the whole worker (`os._exit`) instead of failing one test. There is no identified test-side race to fix; the defect is that the marker's consequence — silent coverage removal — was never made visible or compensated.

## Current Behavior

- **Serial baseline reported by Fable 5.1's review (2026-09-22; not independently rerun in this edit):** `python -m pytest scripts/tests/ -n 0 -m "no_parallel and not integration and not conformance" -q -p no:randomly -p no:ll_history` → `2 passed, 25249 deselected in 7.19s`. Node was present, so both the SSE fan-in test and the Node gate executed successfully. This establishes a passing local baseline, not reliability under full-suite CI contention. The ~100-105s cited elsewhere is the sum of per-step timeout budgets, not measured normal runtime or CPU usage.

- **Verified locally (2026-09-21):** `python -m pytest scripts/tests/test_feat3323_sse_bridge.py -n 2 -q` → `46 passed, 2 skipped in 31.42s`. One skip is the fan-in test (`no_parallel` on an xdist worker); the other is an unrelated environment-conditional skip in the same file, not an xdist artifact.
- The test is the file's only `no_parallel` user (single occurrence, L215).
- **Sweep of all `no_parallel` users (2026-09-21, from the BUG-3522 review):** this test is the only *additional* genuine CI-dormancy case. `test_fsm_signal_integration.py` is doubly excluded by its `integration` marker (never in the unit job by design); `test_dependency_mapper.py` / `test_worktree_utils.py` hits are test names/comments, not markers; `test_policy_builder_node_gate.py` is BUG-3522's subject.

## Expected Behavior

- The SSE bridge fan-in path is exercised by CI — or the marker is a deliberate, documented decision backed by a named serial invocation that actually runs somewhere.
- Adding `no_parallel` to a test can never again silently delete it from every default invocation (structural guard, see Proposed Solution option 3).

## Steps to Reproduce

1. `python -m pytest scripts/tests/test_feat3323_sse_bridge.py -n 2 -q` → the fan-in test is among the skips (`46 passed, 2 skipped`).
2. Confirm no escape hatch exists: `grep -n '\-n 0' .github/workflows/ci.yml docs/` → nothing; the only documented serial invocation shape in `docs/development/TESTING.md` is the marker-table note that `no_parallel` "only actually runs in a serial `-n 0` invocation" — which nothing automates.

## Proposed Solution

**RESOLVED** — Option 2 (keep the marker, add a real serial invocation). The alternatives below are retained as decision history; only option 2 is in implementation scope:

1. **Drop the marker, widen the budget.** If BUG-3484-era contention flakiness is no longer reproducible, remove `no_parallel` and set `@pytest.mark.timeout(N)` strictly above the documented 100-105s worst case plus margin (the `test_verify_evidence.py` `GATE_TIMEOUT + 30` convention; BUG-3522 uses 240 for the same reason). Prerequisite: a stress demonstration (repeated full-suite `-n logical` runs) showing the watchdog no longer fires, because the C-level block cannot be interrupted — budget ≥ worst case is the only protection.
2. **Keep the marker, make the serial invocation real.** Add an explicit serial pass for the `no_parallel` set (e.g. a CI step or documented local command running `python -m pytest scripts/tests/ -n 0 -k <the set>`). Must stay within the AGENTS.md Testing & CI Policy shape (a pytest invocation under the local suite, no new hosted/paid CI); mind the cost — a full serial suite is ~24k tests, so scope the `-k` selection.
3. **Meta-guard (structural; may be split as its own ENH).** A collection-time test that enumerates `no_parallel`-marked items and fails (or requires an explicit annotation naming the serial invocation) for any that lack one — turning "marker = silent coverage removal" into a visible decision. BUG-3522's history is the motivation: a marker landed as a "fix" and silently deleted the ratified FEAT-2390 gate from CI.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-22.

**Selected**: Option 2 — Keep the marker, make the serial invocation real

**Reasoning**: Option 2 reuses two pieces already landed in this codebase: the `no_parallel` marker is pre-registered under `--strict-markers` (`pytest.ini:22-26`, `scripts/pyproject.toml:289-293`), so `pytest scripts/tests/ -n 0 -m no_parallel` selects the full (currently 2-test) set natively with no hand-maintained `-k` string; and `test_hook_session_start.py:712-763`'s `TestAmbientAutomationEnvHermeticity` already implements the exact nested `subprocess.run([..., "-m", "pytest", ..., "-n", "0"], ...)` + `assert returncode == 0` wrapper-test idiom this option needs, running inside the same `unit-tests` CI job with no new workflow step. `test_worktree_utils.py:1471-1480` independently reasons through this same "`no_parallel` marker vs. real nested `-n 0` serial invocation" trade-off for a comparable dormancy problem and chooses the nested-serial shape — direct in-repo precedent for this exact decision. Option 1, by contrast, would repeat BUG-3484's own resolution history: BUG-3484 already tried `@pytest.mark.timeout(180)` alone (no marker) and that was insufficient, which is presumably why `no_parallel` was added afterward — and Option 1's stated stress-test prerequisite (repeated full-suite `-n logical` runs proving the watchdog no longer fires) has no existing harness in the repo to satisfy it.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Drop the marker, widen the budget | 1/3 | 2/3 | 1/3 | 1/3 | 5/12 |
| Keep the marker, make the serial invocation real | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |

**Known trade-off (review updated 2026-09-22).** The nested `-n 0` run still shares CPU with the outer xdist workers; it does not eliminate the historical BUG-3484 contention risk. However, the ~100-105s figure is a sum of per-step timeout budgets, not expected execution time: Fable's local serial baseline completed both selected tests in 7.19s. Keep the conservative timeout budgets pending loaded-suite validation, without projecting a 3-5 minute normal CI cost or treating elapsed time as CPU usage. A nested watchdog exit or wrapper timeout becomes a visible wrapper failure, with one bounded retry (two attempts total). Process-group cleanup and child reaping must complete before retry so surviving descendants do not accumulate. Containment is an intended property to verify, not an unconditional guarantee. Retain both attempts' diagnostics on final failure and make recovered retries observable in uploaded artifacts. `pytest-rerunfailures` is not added.

**Sequencing with BUG-3522.** Do not implement these issues concurrently: both touch `pytest.ini`, `scripts/pyproject.toml`, `docs/development/TESTING.md`, and `docs/development/TROUBLESHOOTING.md`. Prefer landing BUG-3522 first, then apply this issue against its final wording. This is edit coordination, not a functional dependency. After BUG-3522 removes the Node gate's marker, the current marker-selected set becomes the SSE test alone; update validation expectations accordingly without replacing marker discovery with a fixed file list. Keep the conservative 330s per-attempt budget for now.

**Scope of Expected Behavior bullet 2 ("can never again silently delete")**: satisfied by option 2 *only if* the wrapper discovers the set by marker over the whole tree (`scripts/tests/ -m ...`), never by a hand-maintained file list. Measured 2026-09-22: `pytest scripts/tests/ -n 0 -m "no_parallel and not integration and not conformance" --collect-only -q` → `2/25244 tests collected (25242 deselected) in 4.26s`, so whole-tree discovery is cheap. Option 3 (AST meta-guard) is **out of scope** for this issue; split as its own ENH only if a future marker user needs a serial invocation other than this wrapper.

**Key evidence**:
- Option 1: Only one landed instance of the `GATE_TIMEOUT`-constant-plus-margin pairing exists repo-wide (`test_verify_evidence.py:77-81,1531`); a second `GATE_TIMEOUT` site (`test_verify_private_refs.py:44`) skips the pairing entirely, and BUG-3522's parallel case is unlanded. No stress-run/repeated-full-suite harness exists anywhere in `scripts/` to satisfy the option's own prerequisite; the closest artifact (`spike/epic_verify_gate_doc_flake/repro_harness.py`) is narrowly scoped to a different bug. BUG-3484's own resolution already tried raising the timeout alone on this exact test and it wasn't sufficient.
- Option 2: `no_parallel` is a pre-registered strict marker (`pytest.ini:22-26`) selectable natively via `-m no_parallel` over exactly 2 tests suite-wide; `test_hook_session_start.py:712-763` supplies a directly reusable nested-serial-subprocess wrapper-test template already passing inside the `unit-tests` CI job; `test_worktree_utils.py:1471-1480` is an on-point in-repo precedent choosing this same approach over a bare `no_parallel` marker for a comparable problem.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- **Dormancy mechanism confirmed identical to BUG-3522**: `pytest_collection_modifyitems` (`scripts/tests/conftest.py:120-146`) skips `no_parallel`-marked items on every xdist worker; `scripts/pyproject.toml` addopts pin `-n logical` with no `-n 0` anywhere; `.github/workflows/ci.yml`'s `unit-tests` job (~lines 127-128) runs `pytest scripts/tests/ -m "not integration and not conformance"` with no `-n` override, so the fan-in test — carrying neither marker — is collected then skipped on every worker.
- **Marker origin**: `@pytest.mark.no_parallel` (`test_feat3323_sse_bridge.py:215`) is stacked under `@pytest.mark.timeout(180)` (line 216); the comment block at lines 201-214 attributes both to BUG-3484 and documents per-step timeout budgets summing to ~100-105s for the full two-producer + `SseBridge` + 5-real-thread-hop path, plus historical contention overruns of both `--timeout=120` and `timeout(180)` — and pytest-timeout's thread-method watchdog cannot interrupt a blocked C-level `recv()`/thread-join, so it hard-kills the whole worker via `os._exit` rather than failing the one test.
- **What coverage is lost**: `SseBridge`'s multi-thread fan-in path in `scripts/little_loops/transport.py` — `_fan_in_producer_sockets` (line 1069) spawning one `_read_producer_socket` (line 981) reader thread per connected producer, merging onto the shared `_fanin_queue`, relayed to SSE clients by `_relay_loop` (line 1440) — is exercised with **two simultaneously connected producers** only by this test. Every other `TestSseBridgeFanIn` test in the file uses a single producer and carries no `no_parallel` marker, so it runs in CI; only the two-producer merge and the `producer_pid`-attribution-under-fan-in guarantee (stamped per-copy at `transport.py:321-326`, `stamped = {**event, "producer_pid": os.getpid()}`) is unverified in CI.
- **Dependent/precedent files** (mirrors BUG-3522's sweep exactly): `scripts/tests/test_fsm_signal_integration.py` (module-level `pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]`, line 42 — doubly excluded via its own `integration` marker, not a genuine dormancy case), `scripts/tests/test_policy_builder_node_gate.py` (BUG-3522's own subject, identical mechanism), `scripts/tests/test_conftest_cap.py::TestNoParallelMarkerRouting` (lines 143-220 — unit-tests the hook's routing logic in isolation via synthetic `MagicMock` items; must keep passing regardless of which option is chosen here), `scripts/tests/test_dependency_mapper.py:938` and `scripts/tests/test_worktree_utils.py:1471-1480` (both name/comment matches only, not the real marker — the latter explicitly rejects `no_parallel` in favor of a nested serial `pytest ... -n 0` subprocess invoked from inside a normally-scheduled test).
- **Doc surface needing the same reword BUG-3522 already flagged**: `docs/development/TESTING.md` (`no_parallel` marker-table row, ~line 1050) still reads "runs on the controller or in a serial `-n 0` invocation"; `docs/development/TROUBLESHOOTING.md` (BUG-2523 section, ~lines 825-835) still reads "The tests still run — they just don't share cores with six other pytest invocations." Both predate the corrected wording already landed in `scripts/pyproject.toml:300`'s `no_parallel` marker registration string ("the controller never runs tests under `-n N`; it only actually runs in a serial `-n 0` invocation").
- **No existing convention pairs a `no_parallel` marker with a required serial-invocation declaration** — the closest analog is the `grader_case` marker, whose registration string names its consuming meta-test (`test_grader_coverage.py`); `no_parallel`'s registration string does not name one, because none exists yet. The closest precedent for Proposed Solution option 3's shape is `scripts/tests/test_grader_coverage.py` (`TestGraderCoverage`, line 115+), which AST-scans `scripts/tests/*.py` source text (not pytest's own collection/session machinery, deliberately — so a subset run like `-k`/`--lf`/mutmut's `-n0` selection doesn't false-fail) and asserts a coverage property about decorator usage.

### Conventions in Force

- A pytest marker's own `pyproject.toml` registration string is where this codebase names the meta-test that consumes it, when one exists — `grader_case` does this (`scripts/pyproject.toml:294`, "per ENH-3463's test_grader_coverage.py meta-test"); `no_parallel` (`scripts/pyproject.toml:300`) describes the skip mechanism but names no consumer, confirming (not merely asserting) the "no existing convention pairs a `no_parallel` marker with a required serial-invocation declaration" claim already on file.
- Where a per-test timeout must sit strictly above a documented inner worst-case budget (so the suite-wide `--timeout=120` watchdog doesn't kill the worker first), this codebase pairs a named constant with `@pytest.mark.timeout(CONSTANT + margin)` — `test_verify_evidence.py:77-81,1531` (`GATE_TIMEOUT = 120`, `@pytest.mark.timeout(GATE_TIMEOUT + 30)`) is the only site that actually pairs a constant with a strictly-greater marker; `test_verify_private_refs.py:44,358` defines the same `GATE_TIMEOUT` constant but carries no `@pytest.mark.timeout` decorator at all. BUG-3522's own proposed `timeout(240)` vs inner `timeout=180` pairing (its option 1) is not yet landed in `test_policy_builder_node_gate.py` — that file still carries bare `@pytest.mark.no_parallel` with no timeout decorator and BUG-3522's own `status:` is still `open` — so there is no in-repo precedent yet for what the pairing looks like once removed, only issue text.
- A meta-test that must enumerate marker usage across the whole `scripts/tests/` tree does so by AST-parsing test source files directly (`ast.parse`/`ast.walk` over `.decorator_list`), not via pytest's own collection/session API — `test_grader_coverage.py:10-13,57-93,115` is the sole precedent for this shape; its module docstring states the reason explicitly: a subset run (`-k`, `--lf`, a single file, mutmut's per-mutant `-n0` selection) must not make the gate fail spuriously because the tagged tests weren't collected alongside it. No meta-test in the repo enumerates markers via pytest's live collection API (`--collect-only`, `pytest_collection_finish`, a gating `pytest.main([...])` call); the only two `pytest.main(...)` sites (`test_loop_layout_alignment.py:725`, `spike/usage_events_run_id_writer/test_writer.py:108`) are manual `if __name__ == "__main__"` conveniences, not coverage gates.
- Where a serial pass genuinely must execute in CI, the existing pattern is a normally-scheduled (non-`no_parallel`) test shelling out to a nested `pytest ... -n 0 ...` subprocess itself, scoped to one named test file — never a `no_parallel`-marked test and never a dedicated CI workflow step: `test_worktree_utils.py:1471-1480,1519-1522` states the rejection of `no_parallel` explicitly for this reason; `test_hook_session_start.py:739-757` does the same for a different guard. Neither is a suite-wide serial pass over the full `no_parallel` set as Proposed Solution option 2 describes — an unfiltered repo-wide search confirms no such invocation exists anywhere (not in `.github/workflows/ci.yml`, not in `docs/`, not as a standalone script).

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `pytest.ini:26` — the `no_parallel` marker's *second* registration string still carries the pre-BUG-3522-fix wording ("marks tests that must not run on xdist workers … — see scripts/tests/conftest.py"), out of sync with `scripts/pyproject.toml:300`'s already-corrected wording; `pytest.ini:1-11`'s own header comment requires keeping the two in sync. Should get the same reword and, per the `grader_case` convention (`scripts/pyproject.toml:294`, "per ENH-3463's test_grader_coverage.py meta-test"), name the new wrapper test as `no_parallel`'s consumer [Agent 1/2 finding]
- `scripts/pyproject.toml:300` — same registration string; append the consumer name (`test_no_parallel_serial_gate.py`) so both registrations name the wrapper [review 2026-09-22]
- **new** `scripts/tests/test_no_parallel_serial_gate.py` — home of the wrapper test (decided; follows the `*_gate.py` convention of `test_policy_builder_node_gate.py` / `test_verify_evidence.py`). No recursion guard is needed: selection is by marker and the wrapper itself is unmarked, so `-m no_parallel` never selects it [review 2026-09-22]
- `scripts/tests/test_feat3323_sse_bridge.py:210-214` — the comment block still says the test "only runs on the controller (or in a serial `-n 0` invocation)"; reword to state that the controller never runs tests under `-n N` and that the test executes in CI via `test_no_parallel_serial_gate.py` [review 2026-09-22]
- `scripts/tests/conftest.py:129-133` — `pytest_collection_modifyitems` docstring already carries the corrected "runs only in a serial `-n 0` run" wording; add the wrapper's name as the invocation that actually provides it [review 2026-09-22]
- `docs/development/TESTING.md` (`no_parallel` marker-table row, ~line 1050) and `docs/development/TROUBLESHOOTING.md` (BUG-2523 section, ~lines 825-835) — reword the "runs on the controller" claims and name the wrapper as the serial invocation. **Owned by this issue** (whichever of BUG-3522/BUG-3523 lands first does the reword; the second verifies it names both the marker mechanism and this wrapper) [review 2026-09-22]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- **[ready-issue 2026-09-22] BUG-3522 landed (`status: done`, commit `ed40543fa`).** Its fix dropped `@pytest.mark.no_parallel` from `scripts/tests/test_policy_builder_node_gate.py::test_node_conformance_suite_passes` (now at line 44, decorated only with `@pytest.mark.timeout(240)`), so the wrapper's `-m no_parallel` selection now collects only the SSE fan-in test — the coordination risk this bullet originally flagged is resolved. `SERIAL_GATE_TIMEOUT = 330` (sized for the combined SSE+node worst case) remains a valid, if now over-conservative, budget; the Sequencing note's "keep 330s for now" guidance still applies. [Superseded finding, retained for history]: `scripts/tests/test_policy_builder_node_gate.py:53` (`test_node_conformance_suite_passes`, BUG-3522's then-`open` subject) also carried `@pytest.mark.no_parallel` — the wrapper's `-m no_parallel -n 0` invocation would have collected and executed this test too, not just the SSE fan-in test [Agent 1/3 finding]
- `scripts/tests/test_fsm_signal_integration.py:42` (`pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]`) will also be collected by a bare `-m no_parallel -n 0` invocation unless the new wrapper scopes its `-m` expression to exclude `integration` (mirroring the outer CI job's own `-m "not integration and not conformance"` filter) — excluded by the selected design and AC-W2 [Agent 1/3 finding]
- Reference idiom for command construction and diagnostics (adapt to the process-group lifecycle specified below, rather than copying bare `subprocess.run`): `scripts/tests/test_hook_session_start.py::TestAmbientAutomationEnvHermeticity.test_suite_passes_with_ambient_ll_automation` (lines 731-763) — exact `subprocess.run` shape, `cwd=repo_root`, `capture_output=True, text=True`, `returncode == 0` assertion with truncated stdout/stderr tails; the new wrapper test itself must **not** carry `@pytest.mark.no_parallel` (else the very hook it's meant to bypass would skip it too) [Agent 3 finding]
- **Inner invocation details** [review 2026-09-22]:
  - `-m "no_parallel and not integration and not conformance"` — mirror the CI job's *full* filter, not just `not integration`.
  - Pass `-n 0` only; do **not** clear addopts (`-o addopts=`, as `test_worktree_utils.py:1519` does) or the inner run loses `--strict-markers`, `--strict-config` and `--timeout=120`. `-n 0` on the command line overrides the addopts `-n logical`.
  - Pass `-p no:ll_history` (or set `PYTEST_DISABLE_PLUGIN_LL_HISTORY=1` in `env`) so the nested session does not double-record into `history.db` via `little_loops.pytest_history_plugin`.
  - Pass `-p no:randomly` as the precedent does.
  - **Empty-set case**: once BUG-3522 drops the node gate's marker, and if the SSE marker is ever dropped too, `-m no_parallel ...` selects nothing and pytest exits **5** ("no tests collected"). The wrapper must accept return code `0` or `5` (or assert on the collected count from `-q` output), not fail on an empty set.
  - **Inner `--timeout=120` is the effective budget for `test_node_conformance_suite_passes`**: that test carries no `@pytest.mark.timeout`, only a `subprocess.run(..., timeout=180)`, so inside the nested run the suite-wide 120s watchdog governs it. Size the combined budget as SSE `180` + node `120` (not 180 + 180), plus inner startup/collection (~5-10s measured at 4.26s collection).
  - **Bounded retry**: treat both non-zero exits (excluding 5) and `subprocess.TimeoutExpired` as failures; clean up the process group and reap the child before retrying once. Preserve both attempts' output tails and failure kinds on final failure; make recovered retries observable in uploaded artifacts. See AC-W8 and AC-W11.
  - **CI runtime**: Fable reported 7.19s for the current two-test inner command locally. CI runtime under full-suite load remains unmeasured; record it during validation. Timeout budgets bound failure handling, not expected successful runtime.

## Program Design

Decision landed: **option 2**. The wrapper is `test_no_parallel_serial_pass` in new file `scripts/tests/test_no_parallel_serial_gate.py`. Options 1 and 3 remain historical alternatives in Proposed Solution, not implementation requirements.

### Types

- No new public types or third-party dependencies.

### Signatures

- `test_no_parallel_serial_pass() -> None` — a normally scheduled test with no `no_parallel`, `integration`, or `conformance` marker.
- Inner command: `[sys.executable, "-m", "pytest", "scripts/tests/", "-n", "0", "-m", "no_parallel and not integration and not conformance", "-q", "-p", "no:randomly", "-p", "no:ll_history"]`, with `cwd=repo_root`; retain addopts.
- Use `subprocess.Popen(..., stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)` and `communicate(timeout=SERIAL_GATE_TIMEOUT)` per attempt. Keep `SERIAL_GATE_TIMEOUT = 330` (the conservative pre-BUG-3522 budget: SSE 180 + Node effective 120 + startup 30). Keep outer `@pytest.mark.timeout(2 * SERIAL_GATE_TIMEOUT + 30)` for now; both attempts' cleanup/drain/reap budgets must fit within that 30s margin. If validation shows the margin insufficient, explicitly increase it rather than introducing unbounded cleanup.
- Wrap each attempt in `try/except subprocess.TimeoutExpired`; a timeout is retryable just like a non-zero, non-5 exit. Preserve partial exception output and final drained output without duplication, normalizing bytes/text when necessary. Record timeout versus exit status and stdout/stderr tails separately for each attempt.
- On timeout, terminate the POSIX process group with `os.killpg`, escalate to SIGKILL if needed, and drain/reap the direct child with bounded waits before retry. Also clean up surviving descendants on non-zero exits, including inner pytest-timeout watchdog exits; the group may outlive its leader. Handle already-exited groups without masking the original failure. Document the platform scope; do not call POSIX-only APIs unconditionally on unsupported platforms or claim unverified cross-platform containment.
- Accept exit codes 0 and 5; otherwise retry once after cleanup. Fail if both attempts fail, with both attempts' diagnostics. Successful completion after retry must leave an observable recovery record in uploaded artifacts, not merely a captured `print` that disappears on a passing test.

### Call Path

Outer pytest schedules `test_no_parallel_serial_pass` on an xdist worker (never skipped by `pytest_collection_modifyitems`, since it carries no `no_parallel` marker) → `test_no_parallel_serial_pass` starts an isolated nested `pytest` session via `subprocess.Popen` → `-n 0` executes all marker-selected unit tests, including `TestSseBridgeFanIn::test_two_producers_reach_one_client_with_distinct_producer_pid` (which `pytest_collection_modifyitems` would otherwise skip under `-n N`) → `test_no_parallel_serial_pass` collects the result/diagnostics, cleans up failed attempts via `os.killpg`, and retries at most once → outer JUnit records `test_no_parallel_serial_pass`'s result.

## Acceptance Criteria

- The named wrapper **passes** in the `unit-tests` CI job's uploaded `pytest-junit.xml`; validation demonstrates that its inner marker-selected run executes the SSE fan-in test. The nested test will not appear as a separate passed test case in outer JUnit (the separately collected outer item can still appear as skipped).
- Provide verified artifact visibility for the inner summary and any recovered retry, using the existing uploaded JUnit/log artifacts; a bare `print` is insufficient under successful-test capture. Validate this on a passing wrapper run and a simulated first-failure/second-success run.
- BUG-3522's changes (Node marker removal and overlapping documentation/registration edits) remain intact; follow the sequencing note above.

_Option-2 wiring ACs (added 2026-09-22 to resolve the `PROPOSAL_UNSOUND` verification verdict):_

- **AC-W1 (registration strings)**: both `pytest.ini:26` and `scripts/pyproject.toml:300` carry the corrected "controller never runs tests under `-n N`" wording **and** name `test_no_parallel_serial_gate.py` as the consumer; `pytest.ini`'s header sync rule holds.
- **AC-W2 (scope)**: the wrapper's inner `-m` expression is exactly `no_parallel and not integration and not conformance`; `test_fsm_signal_integration.py` is not collected by it (verify via `--collect-only` in the wrapper's own docstring or a companion assertion).
- **AC-W3 (timeout sizing)**: retain `SERIAL_GATE_TIMEOUT = 330` and outer `timeout(2 * SERIAL_GATE_TIMEOUT + 30)` as conservative budgets; explicitly bound both attempts' cleanup/drain/reap work within the outer margin. These are failure bounds, not expected runtimes. Reassess the margin if validation requires more cleanup time.
- **AC-W4 (not dormant itself)**: the wrapper carries no `@pytest.mark.no_parallel`, `integration`, or `conformance` marker, and `pytest scripts/tests/test_no_parallel_serial_gate.py -n 2 -q` reports it **passed**, not skipped.
- **AC-W5 (self-discovering)**: the inner run targets `scripts/tests/` by marker, never an explicit file list; adding `@pytest.mark.no_parallel` to any new unit test makes that test execute inside the wrapper with no edit to the wrapper.
- **AC-W6 (empty set)**: inner exit code `5` is treated as pass; documented in the wrapper's docstring.
- **AC-W7 (no side effects)**: the inner run passes `-p no:ll_history` (or the env opt-out) so `history.db` receives no nested session; addopts are **not** cleared.
- **AC-W8 (retry visible)**: a non-zero, non-5 exit or `TimeoutExpired` triggers one retry after cleanup. If the second attempt passes, the wrapper passes and the recovered failure is observable in an uploaded artifact. If both fail, the assertion includes both attempts' failure kinds and stdout/stderr tails, including partial timeout output. Verify timeout-then-success and two-failure paths with controlled subprocess fixtures.
- **AC-W9 (stale comments)**: `test_feat3323_sse_bridge.py:210-214` and `conftest.py:129-133` no longer claim the test runs "on the controller" and both name the wrapper.
- **AC-W10 (docs)**: `docs/development/TESTING.md` marker row and `docs/development/TROUBLESHOOTING.md` BUG-2523 section reworded per Files to Modify, unless BUG-3522 has already landed the identical reword (then verified only).
- **AC-W11 (descendant containment)**: each attempt uses a new process session; timeout and non-zero/watchdog-exit paths clean up surviving process-group members and reap the direct child before retry, using bounded waits within AC-W3's margin. Controlled subprocess validation verifies descendant cleanup for both paths; unsupported platforms are handled explicitly.

## Impact

- **Priority**: P3 — one test among 48 in the file (the rest run in CI), no ratified-gate violation as in BUG-3522; but it is the only remaining end-to-end coverage of the two-producer fan-in + pid-attribution path, so dormancy is not free
- **Effort**: Small (option 2 as decided)
- **Risk**: Low-Medium — test-infra only, but option 2 does **not** remove the BUG-3484 contention failure mode (the nested serial run still executes under full-suite xdist load); it converts a silent skip into a potentially flaky, visibly red wrapper test. Descendant containment depends on the cleanup lifecycle and must be verified under AC-W11. Mitigated by one bounded retry (see Decision Rationale, "Known trade-off"). If CI shows the wrapper failing on both attempts with a timeout signature, that is the signal to revisit option 1 or the fan-in test's own per-step budgets, not to re-add a bare marker.
- **Breaking Change**: No

## Verification Notes

Verdict: **PROPOSAL_UNSOUND**

- Claims about current state — every cited `file:line` anchor across
  `scripts/tests/conftest.py`, `scripts/little_loops/transport.py`,
  `pytest.ini`, `scripts/pyproject.toml`, `.github/workflows/ci.yml`,
  `docs/development/TESTING.md`, `docs/development/TROUBLESHOOTING.md`, and
  the precedent test files (`test_hook_session_start.py`,
  `test_worktree_utils.py`, `test_grader_coverage.py`,
  `test_verify_evidence.py`, `test_verify_private_refs.py`,
  `test_dependency_mapper.py`, `test_conftest_cap.py`,
  `test_fsm_signal_integration.py`, `test_policy_builder_node_gate.py`) —
  checked individually against the working tree on 2026-09-22 and found
  accurate; no line drift. Local reproduction confirms Steps to Reproduce
  step 1: `pytest scripts/tests/test_feat3323_sse_bridge.py -n 2 -q` → `46
  passed, 2 skipped in 31.41s`.
- **Proposal-vs-code check**: the selected Option 2 fix is sound in
  isolation, but the four touchpoints the Wiring Phase itself requires — (1)
  reword `pytest.ini:26` and name the new wrapper as `no_parallel`'s
  consumer, (2) scope the wrapper's `-m` to `no_parallel and not
  integration`, (3) size `SERIAL_GATE_TIMEOUT` to the *combined* worst case
  of both currently-`no_parallel` tests, (4) never mark the wrapper itself
  `no_parallel` — have no corresponding Acceptance Criteria. An implementer
  could satisfy all four stated ACs (fan-in test runs in CI or via a named
  serial invocation; rationale recorded; BUG-3522 non-regression) while
  skipping any of the four wiring touchpoints, and nothing would fail.
  **Remaining**: add explicit ACs covering each Wiring Phase touchpoint
  before implementation. **Resolved 2026-09-22** — AC-W1..AC-W10 added under
  Acceptance Criteria; verdict should be re-run by `/ll:verify-issues`.
- `ll-verify-evidence --json` flagged one span (Steps to Reproduce, L51 —
  the `grep -n '\-n 0' .github/workflows/ci.yml docs/` command) as
  unverifiable against `test_feat3323_sse_bridge.py`. Reviewed manually:
  it's a shell command to run against `ci.yml`/`docs/`, not a quote claimed
  to exist in the SSE bridge test file — judged a tool misattribution
  (proximity to the nearest artifact mention in the Summary), not
  fabricated evidence. Not escalated to `EVIDENCE_UNVERIFIED`.
- Decisions log: no active required rules (`ll-issues decisions list --type
  rule --enforcement required --active-only` → empty).
- Graph: provider=`codegraph` freshness=`fresh` (corroboration only, per
  the graph-assisted-checks contract — did not originate this verdict).

### Re-verification (2026-09-22, `/ll:verify-issues --auto`)

Verdict: **PROPOSAL_UNSOUND** (narrower than the previous pass — the four
wiring gaps below are now resolved by AC-W1..AC-W10; one new gap found)

- **Previous four wiring-touchpoint gaps — confirmed resolved**: AC-W1
  (`pytest.ini:26` + `scripts/pyproject.toml:300` reword and wrapper
  naming), AC-W2 (`-m` scope excludes `integration`), AC-W3 (timeout
  sizing to the combined 180+120+30 worst case), AC-W4 (wrapper itself
  unmarked) each map 1:1 onto the four touchpoints the previous verdict
  flagged as AC-less. All cited file:line anchors re-checked against the
  working tree (`pytest.ini:26`, `scripts/pyproject.toml:300`,
  `scripts/tests/conftest.py:120-146`, `test_feat3323_sse_bridge.py:200-219`)
  — unchanged, no drift. `scripts/tests/test_no_parallel_serial_gate.py`
  does not yet exist (Implementation Steps not started); BUG-3522 is
  still `open` (the coordination-risk note is accurate). Decisions log:
  no active required rules. `ll-verify-evidence` still flags only the
  same Steps-to-Reproduce span already reviewed and dismissed as a tool
  misattribution, not fabricated evidence.
- **New finding — exception-handler compatibility (check B6)**: the
  Program Design's `subprocess.run(..., timeout=SERIAL_GATE_TIMEOUT)`
  call (copying `test_hook_session_start.py:731-763`'s idiom, which
  itself has no `try/except`) raises `subprocess.TimeoutExpired` rather
  than returning a non-zero exit code when the inner run overruns its
  wall-clock budget. AC-W8's "bounded retry ... on a first-attempt
  failure" and the Decision Rationale's "one bounded retry of the inner
  run on non-zero exit" are both phrased in terms of a returned exit
  code; as literally specified, an implementer checks `proc.returncode`
  after a call that can instead raise, so a first-attempt timeout — the
  exact failure mode this retry exists to absorb (Known trade-off:
  "silent skip becomes possibly-flaky red") — would propagate as an
  uncaught `TimeoutExpired` and skip the retry entirely instead of
  triggering the intended second attempt. `SERIAL_GATE_TIMEOUT=330` is
  sized tight to the documented worst case (180+120+30, no slack beyond
  that margin), so this is a live path, not a hypothetical one.
  **Remaining**: the wrapper's retry loop must wrap each
  `subprocess.run` call in `try/except subprocess.TimeoutExpired` and
  treat it the same as a non-zero, non-5 return code for retry purposes
  (the caught exception's own `.stdout`/`.stderr` attributes supply the
  tail for the failure message). Add this to AC-W8 (or a new AC-W11)
  before implementation. **Addressed in the specification on 2026-09-22** by the updated Program Design and AC-W8/AC-W11 above; implementation validation remains outstanding.

### Review disposition (2026-09-22)

Fable 5.1's review has been folded into the selected design, AC-W8/AC-W11, and implementation steps: timeouts are explicitly retryable, process-group cleanup covers timeout and watchdog-exit paths, and runtime claims distinguish the reported 7.19s local baseline from timeout budgets. The earlier exception-handler gap is **addressed in the specification**; the historical verification verdicts above are retained as history, not evidence that implementation has been verified. Implementation and loaded-suite/artifact validation remain outstanding.

### Re-verification (2026-09-22, `/ll:verify-issues`)

Verdict: **VALID**

- All cited `file:line` anchors re-checked against the working tree
  (`conftest.py:120-146`, `pytest.ini:26`, `scripts/pyproject.toml:300`,
  `test_feat3323_sse_bridge.py:210-216`, `transport.py` fan-in anchors,
  `.github/workflows/ci.yml` unit-tests job, and all precedent test files:
  `test_hook_session_start.py:712-763`, `test_worktree_utils.py:1471-1480`,
  `test_conftest_cap.py:143`, `test_policy_builder_node_gate.py:53`) —
  unchanged, no drift.
- Reproduction reconfirmed: `pytest scripts/tests/test_feat3323_sse_bridge.py
  -n 2 -q` → `46 passed, 2 skipped in 31.16s`.
- **Both prior `PROPOSAL_UNSOUND` findings are now resolved**: the four
  wiring-touchpoint gaps are covered by AC-W1..AC-W4, and the
  `subprocess.TimeoutExpired` exception-handling gap is addressed by the
  Program Design's `try/except subprocess.TimeoutExpired` wrap plus
  AC-W8/AC-W11. Re-traced the full Files to Modify / Wiring Phase touchpoint
  list against Acceptance Criteria — every touchpoint maps to an AC; no new
  proposal-vs-code defect found.
- `scripts/tests/test_no_parallel_serial_gate.py` still does not exist
  (implementation not started, as expected).
- BUG-3522 coordination note still accurate — still `status: open`.
- `ll-verify-evidence --json` still flags only the same Steps-to-Reproduce
  span already reviewed and dismissed as a tool misattribution, not
  fabricated evidence.
- Decisions log: no active required rules.
- Graph: provider=`codegraph` freshness=`fresh` (corroboration only).

### Re-verification (2026-09-22, `/ll:verify-issues --auto`)

Verdict: **VALID**

- All cited `file:line` anchors re-checked against the working tree
  (`conftest.py:120-146`, `pytest.ini:26`, `scripts/pyproject.toml:300`,
  `test_feat3323_sse_bridge.py:200-219`) — unchanged, no drift; the stale
  "runs on the controller" comment (AC-W9) is still present as expected
  since implementation has not started.
- `scripts/tests/test_no_parallel_serial_gate.py` still does not exist.
- BUG-3522 still `status: open` — coordination note remains accurate.
- `ll-verify-evidence --json` still flags only the same Steps-to-Reproduce
  span already reviewed and dismissed as a tool misattribution, not
  fabricated evidence.
- Decisions log: no active required rules (`ll-issues decisions list --type
  rule --enforcement required --active-only` → empty).
- No `## Blocked By` section; `relates_to` entries are informational, not
  blocking edges — no dependency issues found.
- Proposal-vs-code check: AC-W1..AC-W11 still present and continue to cover
  all Wiring Phase touchpoints; no new gap found.

## Status

**Open** | Created: 2026-09-21 | Priority: P3

## Implementation Steps

- ~~Reproduce the dormancy locally and confirm the sweep claim~~ — done (Current Behavior)
- ~~Decide between options 1-3~~ — done, option 2 (Decision Rationale)
- ~~Coordinate with BUG-3522 before implementation~~ — done: BUG-3522 landed `status: done` (commit `ed40543fa`, 2026-09-22 [ready-issue]). Reconcile this issue's edits (`pytest.ini:26`, `scripts/pyproject.toml:300`, `docs/development/TESTING.md`, `docs/development/TROUBLESHOOTING.md`) against BUG-3522's final wording before touching them.
- ~~Create `scripts/tests/test_no_parallel_serial_gate.py` per Program Design Signatures~~ — done (`Popen` process session, marker-scoped inner `-n 0`, exit `0|5` accepted, one bounded retry including `TimeoutExpired`, bounded group cleanup and child reaping, `SERIAL_GATE_TIMEOUT = 330`, outer `timeout(2*330+30)`)
- ~~Verify locally~~ — done: `pytest scripts/tests/test_no_parallel_serial_gate.py -n 2 -q` → `6 passed` (not skipped); inner output confirms the SSE test executed. BUG-3522 had already landed before implementation started, so only the SSE test is in the current `no_parallel` set (`--collect-only` confirms `1/25273` collected). Successful inner-summary and recovered-retry artifact visibility verified via a manual patched-retry probe against `--junitxml` (see Resolution)
- ~~Reword registration strings and stale comments to name the wrapper~~ — done (`pytest.ini:26`, `scripts/pyproject.toml:300`, `test_feat3323_sse_bridge.py:210-214`, `conftest.py:129-133`)
- ~~Reword docs~~ — done (`docs/development/TESTING.md` marker row, `docs/development/TROUBLESHOOTING.md` BUG-2523 section)
- ~~Confirm `test_conftest_cap.py::TestNoParallelMarkerRouting` still passes~~ — done, unchanged (hook not modified)
- ~~Validate timeout-then-success, two failures, and descendant cleanup~~ — done via `TestSerialPassWithRetry` (4 unit tests, fake attempts) and `TestKillGroupIfAlive` (real process-tree cleanup) in the new file
- ~~Run the full suite once with `-n logical`~~ — done: `25218 passed, 54 skipped, 1 failed in 242.22s`; the 1 failure is a pre-existing, unrelated evidence-gate finding (confirmed via `git stash` on unmodified `main`), see Resolution. The wrapper's own measured wall clock under full-suite `-n logical` load was not isolated from this run; the `-n 2` local baseline (10.4s for the 6-test file) is the available evidence — record the isolated CI figure from the first post-merge `unit-tests` JUnit artifact per the Decision Rationale's "Known trade-off" note

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Update `pytest.ini:26`~~ — done: reworded to match `scripts/pyproject.toml:300`'s wording and name the new wrapper test as its consumer (mirroring `grader_case` at `scripts/pyproject.toml:294`)
- ~~Scope the new wrapper's `-m` expression~~ — done: `no_parallel and not integration and not conformance`, so it doesn't also pull in `test_fsm_signal_integration.py`'s doubly-marked class (verified via `--collect-only`)
- ~~Size the new wrapper's timeout~~ — done: `SERIAL_GATE_TIMEOUT = 330` (SSE 180s + node effective 120s + margin), outer `timeout(2*330+30)` covers both retry attempts
- ~~Do not mark the new wrapper test itself `@pytest.mark.no_parallel`~~ — done: unmarked, confirmed passing (not skipped) under `-n 2`
- ~~Pass `-p no:ll_history` on the inner run and do not clear addopts~~ — done
- ~~Accept inner exit code 5 as pass; retry once on other non-zero exit or `TimeoutExpired`~~ — done, with bounded process-group cleanup and diagnostics per AC-W8/AC-W11
- ~~Reword the stale "runs on the controller" comment and name the wrapper in `conftest.py`~~ — done

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- **File**: `scripts/tests/conftest.py`
- **Anchor**: `pytest_collection_modifyitems` (line 120)
- **Cause**: The hook adds `pytest.mark.skip(reason="no_parallel: cannot run on xdist workers")` (lines 143-146) to every item carrying the `no_parallel` keyword whenever `config.workerinput` is truthy — i.e. on every xdist worker, never on the controller (lines 140-142). Under `-n N` the controller only collects and distributes work and never executes a test body itself (the hook's own docstring, lines 129-131). `scripts/pyproject.toml`'s `addopts` pins `-n logical` (no `-n 0` anywhere in that file), and `.github/workflows/ci.yml`'s `unit-tests` job invokes `pytest scripts/tests/ -m "not integration and not conformance"` with no `-n` override, so it inherits that default. `test_two_producers_reach_one_client_with_distinct_producer_pid` carries neither `integration` nor `conformance`, so the job's `-m` filter collects it — it is then unconditionally skipped on every worker and never run on the controller. This is not a logic defect in the hook itself (it matches BUG-2523's original intent, and `scripts/tests/test_conftest_cap.py::TestNoParallelMarkerRouting` already covers the hook's routing correctness in isolation); the defect is that `@pytest.mark.no_parallel` was stacked onto this test — for a legitimate reason, BUG-3484's historical contention overruns (the cited ~100-105s is a sum of per-step budgets, not measured normal runtime) — with no compensating serial invocation added anywhere, so the coverage loss is silent rather than a deliberate, visible trade-off.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-22; re-checked 2026-09-22 (three times) — Program Design gap resolved this pass by naming concrete anchors (`test_no_parallel_serial_pass`, `pytest_collection_modifyitems`) in the Call Path text; `ll-issues check-design BUG-3523` now exits 0_

**Readiness Score**: 95/100 → PROCEED (Program Design hard override cleared)
**Outcome Confidence**: 79/100 → MODERATE

### Outcome Risk Factors
- Deep per-site complexity concentrated in the new `test_no_parallel_serial_gate.py` file (process-group lifecycle, bounded retry across `subprocess.TimeoutExpired` and non-zero/non-5 exits, descendant cleanup) — the surrounding 6 touch-points (`pytest.ini`, `scripts/pyproject.toml`, two stale-comment rewords, two docs rewords) are mechanical, so the aggregate Complexity score undercounts the one genuinely stateful site; validate the retry/cleanup paths with controlled subprocess fixtures per AC-W8/AC-W11 before trusting a green run.

## Resolution

- **Status**: Implemented and locally verified. Option 2 (named serial
  invocation) is landed: `scripts/tests/test_no_parallel_serial_gate.py`
  runs the marker-selected `no_parallel` set under a nested `-n 0` pytest
  invocation, unmarked itself so it executes under the outer `-n logical`
  suite. All Program Design signatures and AC-W1..AC-W11 wiring touchpoints
  are implemented; see Changes Made and Validation below.

### Changes Made

- **new** `scripts/tests/test_no_parallel_serial_gate.py` — `test_no_parallel_serial_pass`
  (unmarked) shells to `pytest scripts/tests/ -n 0 -m "no_parallel and not
  integration and not conformance" -q -p no:randomly -p no:ll_history` via
  `subprocess.Popen(..., start_new_session=True)`; accepts inner exit `0` or
  `5` (empty selection); one bounded retry on `TimeoutExpired` or any other
  non-zero/non-5 exit; `_kill_group_if_alive` does a bounded POSIX
  `os.killpg` TERM-then-KILL sweep (5s wait per stage) after every attempt,
  timeout or not, since a clean/non-zero leader exit can still leave
  descendants alive. `SERIAL_GATE_TIMEOUT = 330` (SSE 180 + node effective
  120 + ~30s margin), outer `@pytest.mark.timeout(2 * SERIAL_GATE_TIMEOUT +
  30)`. A recovered retry is `print`ed (captured into the JUnit
  `<system-out>` via the existing `junit_logging = "system-out"` config —
  validated empirically, see below). Also includes `TestSerialPassWithRetry`
  (4 fast unit tests against injected fake attempts: first-try pass,
  timeout-then-success, exit-5-is-pass, two-failures-exhausts-retry) and
  `TestKillGroupIfAlive::test_kills_grandchild_in_same_group` (spawns a real
  process tree, confirms the grandchild is gone after cleanup), covering
  AC-W8 and AC-W11.
- `pytest.ini:26`, `scripts/pyproject.toml:300` — reworded the `no_parallel`
  registration string to name `scripts/tests/test_no_parallel_serial_gate.py`
  as the consumer, mirroring the `grader_case` convention (AC-W1).
- `scripts/tests/test_feat3323_sse_bridge.py:210-214` — stale "runs on the
  controller" comment reworded to name the wrapper (AC-W9).
- `scripts/tests/conftest.py:129-133` — `pytest_collection_modifyitems`
  docstring now names the wrapper as the invocation that actually runs the
  serial `-n 0` pass (AC-W9).
- `docs/development/TESTING.md` (`no_parallel` marker row) and
  `docs/development/TROUBLESHOOTING.md` (BUG-2523 section) — reworded to
  name the wrapper; the TROUBLESHOOTING.md fsm-signal-integration example
  clarifies that those two tests carry `integration` and remain outside the
  wrapper's own scope too, not just the CI job's (AC-W10).

### Validation

- `pytest scripts/tests/test_no_parallel_serial_gate.py -n 2 -q` → `6
  passed` (not skipped — AC-W4), including a real execution of the inner
  serial pass that itself ran the SSE fan-in test.
- `pytest scripts/tests/ -n 0 -m "no_parallel and not integration and not
  conformance" --collect-only -q` → `1/25273 tests collected` — only the SSE
  fan-in test (BUG-3522 already dropped the node gate's marker), confirming
  AC-W2/AC-W5 scope and by-marker (not file-list) discovery.
- `pytest scripts/tests/test_conftest_cap.py::TestNoParallelMarkerRouting
  scripts/tests/test_feat3323_sse_bridge.py -n 2 -q` → `50 passed, 2
  skipped` (unchanged from pre-implementation baseline — no regression).
- Manually verified recovered-retry artifact visibility: patched
  `_run_inner_once` to return timeout-then-success, ran under `--junitxml`
  without `-s` (the CI shape), and confirmed the recovery `print` appears in
  the generated `<system-out>` block.
- `ruff check` / `ruff format --check` / `mypy` clean on all changed and new
  files.
- Full suite: `python -m pytest scripts/tests/` → `25218 passed, 54 skipped,
  1 failed in 242.22s`. The one failure
  (`test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence`)
  is a pre-existing, unrelated evidence-corpus baseline gap (flags two spans
  in `P2-BUG-3522-...md:45` and this issue's own pre-existing Steps to
  Reproduce line, `:61`) — confirmed via `git stash` to fail identically on
  unmodified `main`, before any of this issue's edits. Out of scope for
  BUG-3523 (the flagged issue text is BUG-3522's, and this issue's own
  flagged line was already reviewed and dismissed in the Verification Notes
  above); not caused or fixed by this change.
- CI runtime for the wrapper under full-suite `-n logical` load remains
  unmeasured (Fable's 7.19s figure is a local `-n 0` baseline); record it
  from the first post-merge `unit-tests` JUnit artifact.

## Session Log
- `/ll:manage-issue` - 2026-09-22T19:58:50 - `033c8748-0fd3-43ec-8efe-dfc335b26eed.jsonl`
- `/ll:ready-issue` - 2026-09-22T19:44:27 - `81af7dc6-0208-40f9-878c-c49e6891b514.jsonl`
- `/ll:confidence-check` - 2026-09-22T16:31:30 - `00004522-d744-453d-9393-066be704b3ae.jsonl`
- `/ll:confidence-check` - 2026-09-22T16:29:23 - `00004522-d744-453d-9393-066be704b3ae.jsonl`
- `/ll:reconcile-issue` - 2026-09-22T16:26:47 - `da6595a1-fc9b-4f09-92ce-9a598a4335fe.jsonl`
- `/ll:confidence-check` - 2026-09-22T16:25:15 - `08d6ef1e-1b9c-4a4d-935a-fce06a8a019b.jsonl`
- `/ll:verify-issues` - 2026-09-22T16:24:39 - `971b8e9e-da71-4859-ba73-1cc041bb9883.jsonl`
- `/ll:reconcile-issue` - 2026-09-22T16:19:54 - `dd7982c9-14ba-4a41-940f-6fecc033ca70.jsonl`
- `/ll:confidence-check` - 2026-09-22T16:16:18 - `9771b48d-f4c0-41e2-91d6-313376eb5ef8.jsonl`
- `/ll:verify-issues` - 2026-09-22T16:13:43 - `2426bc78-355e-49c0-b1d4-bbd04fabb869.jsonl`
- `/ll:confidence-check` - 2026-09-22T16:00:45 - `f1a52e94-8652-4d09-be78-f2bf7d0ad19c.jsonl`
- `/ll:verify-issues` - 2026-09-22T15:55:43 - `bfbb9153-ce71-46cf-a05b-72f0af991763.jsonl`
- `/ll:verify-issues` - 2026-09-22T15:45:41 - `bfb59371-f535-4c56-8b82-ba5a535b470c.jsonl`
- `/ll:wire-issue` - 2026-09-22T15:39:19 - `03d961d3-9a5a-4fcc-81d7-c9c6f85c6cd8.jsonl`
- `/ll:decide-issue` - 2026-09-22T15:32:23 - `ac5fb0be-e93b-41b1-bfc9-5ed4d9b825c2.jsonl`
- `/ll:refine-issue` - 2026-09-22T15:24:01 - `f6c11c46-8116-4e24-83a3-9e7ac209cbad.jsonl`
- `/ll:format-issue` - 2026-09-22T15:16:00 - `484f6d1d-ca00-4295-b7f6-7aec856c3eee.jsonl`
