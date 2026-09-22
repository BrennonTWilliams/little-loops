---
id: BUG-3523
type: BUG
title: "SSE bridge fan-in test is CI-dormant \u2014 no_parallel marker with no serial\
  \ invocation anywhere"
priority: P3
status: open
discovered_by: manual
discovered_date: '2026-09-21'
captured_at: '2026-09-21T02:43:58Z'
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
---

# BUG-3523: SSE bridge fan-in test is CI-dormant — no_parallel marker with no serial invocation anywhere

## Summary

<!-- ll-prose-ok: no_parallel is a pytest marker name (registered via decorator/keyword), not a def-site symbol; not a stale reference -->
`scripts/tests/test_feat3323_sse_bridge.py::TestSseBridgeFanIn::test_two_producers_reach_one_client_with_distinct_producer_pid` — the only end-to-end fan-in test for the FEAT-3323 SSE bridge (two producers, one client, distinct `producer_pid` attribution) — **never executes in CI**. It carries `@pytest.mark.no_parallel` (stacked on `@pytest.mark.timeout(180)`, added for BUG-3484), and the dormancy mechanism verified end-to-end in BUG-3522 applies verbatim: `pytest_collection_modifyitems` in `scripts/tests/conftest.py` skips `no_parallel` items on every xdist worker, the controller runs no tests under `-n N`, the `scripts/pyproject.toml` addopts pin `-n logical`, and no invocation in `.github/workflows/ci.yml` (or anywhere else) runs a serial `-n 0` pass. The test has no `integration`/`conformance` marker, so the `unit-tests` job's `-m "not integration and not conformance"` filter does not exclude it — it is collected, then skipped on the worker. A green `unit-tests` job says nothing about SSE fan-in.

Unlike BUG-3522, the marker here was added for a **legitimate wall-clock reason** — the test's own comment block (`test_feat3323_sse_bridge.py:201-214`) documents a ~100-105s worst-case budget that, under full-suite xdist contention, exceeded the suite-wide `--timeout=120` and even `timeout(180)`, and pytest-timeout's thread-method watchdog cannot interrupt a blocked C-level `recv()`/thread-join, so it hard-kills the whole worker (`os._exit`) instead of failing one test. There is no identified test-side race to fix; the defect is that the marker's consequence — silent coverage removal — was never made visible or compensated.

## Current Behavior

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

**RESOLVED** — Option 2 (keep the marker, add a real serial invocation). This is a **decision-shaped issue** — pick one and record the rationale here:

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

**Known trade-off (review 2026-09-22) — contention is load-bearing here, unlike the cited precedents.** The wrapper test runs on an xdist worker in CI while every other worker is busy, so the nested `-n 0` subprocess executes the fan-in test under the *same* full-suite CPU contention that pushed its ~100-105s budget past `timeout(180)` in BUG-3484. Both precedents dodged this: `test_worktree_utils.py:1477-1480` states "the xdist dimension is not load-bearing for this read path", and the `test_hook_session_start.py` guard is short. Option 2 therefore does **not** remove the BUG-3484 failure mode; it changes its consequence. Inside the nested run, pytest-timeout's `os._exit` kills the *nested subprocess*, so the wrapper sees a non-zero return code and fails as one visible test instead of hard-killing the outer xdist worker. Honest framing: **silent skip becomes possibly-flaky red**, with blast radius contained to one test. Mitigation adopted: the wrapper performs one bounded retry of the inner run on non-zero exit (two attempts total), logging the first attempt's stdout/stderr tail in the failure message so a genuine regression is still diagnosable and a contention flake is visible in the log rather than swallowed. `pytest-rerunfailures` is not a dependency and is not added (minimize third-party deps).

**Scope of Expected Behavior bullet 2 ("can never again silently delete")**: satisfied by option 2 *only if* the wrapper discovers the set by marker over the whole tree (`scripts/tests/ -m ...`), never by a hand-maintained file list. Measured 2026-09-22: `pytest scripts/tests/ -n 0 -m "no_parallel and not integration and not conformance" --collect-only -q` → `2/25244 tests collected (25242 deselected) in 4.26s`, so whole-tree discovery is cheap. Option 3 (AST meta-guard) is **out of scope** for this issue; split as its own ENH only if a future marker user needs a serial invocation other than this wrapper.

**Key evidence**:
- Option 1: Only one landed instance of the `GATE_TIMEOUT`-constant-plus-margin pairing exists repo-wide (`test_verify_evidence.py:77-81,1531`); a second `GATE_TIMEOUT` site (`test_verify_private_refs.py:44`) skips the pairing entirely, and BUG-3522's parallel case is unlanded. No stress-run/repeated-full-suite harness exists anywhere in `scripts/` to satisfy the option's own prerequisite; the closest artifact (`spike/epic_verify_gate_doc_flake/repro_harness.py`) is narrowly scoped to a different bug. BUG-3484's own resolution already tried raising the timeout alone on this exact test and it wasn't sufficient.
- Option 2: `no_parallel` is a pre-registered strict marker (`pytest.ini:22-26`) selectable natively via `-m no_parallel` over exactly 2 tests suite-wide; `test_hook_session_start.py:712-763` supplies a directly reusable nested-serial-subprocess wrapper-test template already passing inside the `unit-tests` CI job; `test_worktree_utils.py:1471-1480` is an on-point in-repo precedent choosing this same approach over a bare `no_parallel` marker for a comparable problem.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- **Dormancy mechanism confirmed identical to BUG-3522**: `pytest_collection_modifyitems` (`scripts/tests/conftest.py:120-146`) skips `no_parallel`-marked items on every xdist worker; `scripts/pyproject.toml` addopts pin `-n logical` with no `-n 0` anywhere; `.github/workflows/ci.yml`'s `unit-tests` job (~lines 127-128) runs `pytest scripts/tests/ -m "not integration and not conformance"` with no `-n` override, so the fan-in test — carrying neither marker — is collected then skipped on every worker.
- **Marker origin**: `@pytest.mark.no_parallel` (`test_feat3323_sse_bridge.py:215`) is stacked under `@pytest.mark.timeout(180)` (line 216); the comment block at lines 201-214 attributes both to BUG-3484 and documents a ~100-105s worst-case wall-clock budget for the full two-producer + `SseBridge` + 5-real-thread-hop path, which under full-suite xdist contention can exceed both `--timeout=120` and `timeout(180)` — and pytest-timeout's thread-method watchdog cannot interrupt a blocked C-level `recv()`/thread-join, so it hard-kills the whole worker via `os._exit` rather than failing the one test.
- **What coverage is lost**: `SseBridge`'s multi-thread fan-in path in `scripts/little_loops/transport.py` — `_fan_in_producer_sockets` (line 1069) spawning one `_read_producer_socket` (line 981) reader thread per connected producer, merging onto the shared `_fanin_queue`, relayed to SSE clients by `_relay_loop` (line 1440) — is exercised with **two simultaneously connected producers** only by this test. Every other `TestSseBridgeFanIn` test in the file uses a single producer and carries no `no_parallel` marker, so it runs in CI; only the two-producer merge and the `producer_pid`-attribution-under-fan-in guarantee (stamped per-copy at `transport.py:321-326`, `stamped = {**event, "producer_pid": os.getpid()}`) is unverified in CI.
- **Dependent/precedent files** (mirrors BUG-3522's sweep exactly): `scripts/tests/test_fsm_signal_integration.py` (module-level `pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]`, line 42 — doubly excluded via its own `integration` marker, not a genuine dormancy case), `scripts/tests/test_policy_builder_node_gate.py` (BUG-3522's own subject, identical mechanism), `scripts/tests/test_conftest_cap.py::TestNoParallelMarkerRouting` (lines 143-220 — unit-tests the hook's routing logic in isolation via synthetic `MagicMock` items; must keep passing regardless of which option is chosen here), `scripts/tests/test_dependency_mapper.py:938` and `scripts/tests/test_worktree_utils.py:1471-1480` (both name/comment matches only, not the real marker — the latter explicitly rejects `no_parallel` in favor of a nested serial `pytest ... -n 0` subprocess invoked from inside a normally-scheduled test).
- **Doc surface needing the same reword BUG-3522 already flagged**: `docs/development/TESTING.md` (`no_parallel` marker-table row, ~line 1050) still reads "runs on the controller or in a serial `-n 0` invocation"; `docs/development/TROUBLESHOOTING.md` (BUG-2523 section, ~lines 825-835) still reads "The tests still run — they just don't share cores with six other pytest invocations." Both predate the corrected wording already landed in `scripts/pyproject.toml:293`'s `no_parallel` marker registration string ("the controller never runs tests under `-n N`; it only actually runs in a serial `-n 0` invocation").
- **No existing convention pairs a `no_parallel` marker with a required serial-invocation declaration** — the closest analog is the `grader_case` marker, whose registration string names its consuming meta-test (`test_grader_coverage.py`); `no_parallel`'s registration string does not name one, because none exists yet. The closest precedent for Proposed Solution option 3's shape is `scripts/tests/test_grader_coverage.py` (`TestGraderCoverage`, line 115+), which AST-scans `scripts/tests/*.py` source text (not pytest's own collection/session machinery, deliberately — so a subset run like `-k`/`--lf`/mutmut's `-n0` selection doesn't false-fail) and asserts a coverage property about decorator usage.

### Conventions in Force

- A pytest marker's own `pyproject.toml` registration string is where this codebase names the meta-test that consumes it, when one exists — `grader_case` does this (`scripts/pyproject.toml:294`, "per ENH-3463's test_grader_coverage.py meta-test"); `no_parallel` (`scripts/pyproject.toml:293`) describes the skip mechanism but names no consumer, confirming (not merely asserting) the "no existing convention pairs a `no_parallel` marker with a required serial-invocation declaration" claim already on file.
- Where a per-test timeout must sit strictly above a documented inner worst-case budget (so the suite-wide `--timeout=120` watchdog doesn't kill the worker first), this codebase pairs a named constant with `@pytest.mark.timeout(CONSTANT + margin)` — `test_verify_evidence.py:77-81,1531` (`GATE_TIMEOUT = 120`, `@pytest.mark.timeout(GATE_TIMEOUT + 30)`) is the only site that actually pairs a constant with a strictly-greater marker; `test_verify_private_refs.py:44,358` defines the same `GATE_TIMEOUT` constant but carries no `@pytest.mark.timeout` decorator at all. BUG-3522's own proposed `timeout(240)` vs inner `timeout=180` pairing (its option 1) is not yet landed in `test_policy_builder_node_gate.py` — that file still carries bare `@pytest.mark.no_parallel` with no timeout decorator and BUG-3522's own `status:` is still `open` — so there is no in-repo precedent yet for what the pairing looks like once removed, only issue text.
- A meta-test that must enumerate marker usage across the whole `scripts/tests/` tree does so by AST-parsing test source files directly (`ast.parse`/`ast.walk` over `.decorator_list`), not via pytest's own collection/session API — `test_grader_coverage.py:10-13,57-93,115` is the sole precedent for this shape; its module docstring states the reason explicitly: a subset run (`-k`, `--lf`, a single file, mutmut's per-mutant `-n0` selection) must not make the gate fail spuriously because the tagged tests weren't collected alongside it. No meta-test in the repo enumerates markers via pytest's live collection API (`--collect-only`, `pytest_collection_finish`, a gating `pytest.main([...])` call); the only two `pytest.main(...)` sites (`test_loop_layout_alignment.py:725`, `spike/usage_events_run_id_writer/test_writer.py:108`) are manual `if __name__ == "__main__"` conveniences, not coverage gates.
- Where a serial pass genuinely must execute in CI, the existing pattern is a normally-scheduled (non-`no_parallel`) test shelling out to a nested `pytest ... -n 0 ...` subprocess itself, scoped to one named test file — never a `no_parallel`-marked test and never a dedicated CI workflow step: `test_worktree_utils.py:1471-1480,1519-1522` states the rejection of `no_parallel` explicitly for this reason; `test_hook_session_start.py:739-757` does the same for a different guard. Neither is a suite-wide serial pass over the full `no_parallel` set as Proposed Solution option 2 describes — an unfiltered repo-wide search confirms no such invocation exists anywhere (not in `.github/workflows/ci.yml`, not in `docs/`, not as a standalone script).

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `pytest.ini:26` — the `no_parallel` marker's *second* registration string still carries the pre-BUG-3522-fix wording ("marks tests that must not run on xdist workers … — see scripts/tests/conftest.py"), out of sync with `scripts/pyproject.toml:293`'s already-corrected wording; `pytest.ini:1-11`'s own header comment requires keeping the two in sync. Should get the same reword and, per the `grader_case` convention (`scripts/pyproject.toml:294`, "per ENH-3463's test_grader_coverage.py meta-test"), name the new wrapper test as `no_parallel`'s consumer [Agent 1/2 finding]
- `scripts/pyproject.toml:293` — same registration string; append the consumer name (`test_no_parallel_serial_gate.py`) so both registrations name the wrapper [review 2026-09-22]
- **new** `scripts/tests/test_no_parallel_serial_gate.py` — home of the wrapper test (decided; follows the `*_gate.py` convention of `test_policy_builder_node_gate.py` / `test_verify_evidence.py`). No recursion guard is needed: selection is by marker and the wrapper itself is unmarked, so `-m no_parallel` never selects it [review 2026-09-22]
- `scripts/tests/test_feat3323_sse_bridge.py:210-214` — the comment block still says the test "only runs on the controller (or in a serial `-n 0` invocation)"; reword to state that the controller never runs tests under `-n N` and that the test executes in CI via `test_no_parallel_serial_gate.py` [review 2026-09-22]
- `scripts/tests/conftest.py:129-133` — `pytest_collection_modifyitems` docstring already carries the corrected "runs only in a serial `-n 0` run" wording; add the wrapper's name as the invocation that actually provides it [review 2026-09-22]
- `docs/development/TESTING.md` (`no_parallel` marker-table row, ~line 1050) and `docs/development/TROUBLESHOOTING.md` (BUG-2523 section, ~lines 825-835) — reword the "runs on the controller" claims and name the wrapper as the serial invocation. **Owned by this issue** (whichever of BUG-3522/BUG-3523 lands first does the reword; the second verifies it names both the marker mechanism and this wrapper) [review 2026-09-22]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_policy_builder_node_gate.py:53` (`test_node_conformance_suite_passes`, BUG-3522's still-`open` subject) also carries `@pytest.mark.no_parallel` — the new wrapper's `-m no_parallel -n 0` invocation will collect and execute this test too, not just the SSE fan-in test; its own runtime budget must be folded into the wrapper's outer timeout, and BUG-3522's unresolved status is a coordination risk [Agent 1/3 finding]
- `scripts/tests/test_fsm_signal_integration.py:42` (`pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]`) will also be collected by a bare `-m no_parallel -n 0` invocation unless the new wrapper scopes its `-m` expression to exclude `integration` (mirroring the outer CI job's own `-m "not integration and not conformance"` filter) — an explicit scoping decision the issue doesn't yet make [Agent 1/3 finding]
- Reference idiom to copy: `scripts/tests/test_hook_session_start.py::TestAmbientAutomationEnvHermeticity.test_suite_passes_with_ambient_ll_automation` (lines 731-763) — exact `subprocess.run` shape, `cwd=repo_root`, `capture_output=True, text=True`, `returncode == 0` assertion with truncated stdout/stderr tails; the new wrapper test itself must **not** carry `@pytest.mark.no_parallel` (else the very hook it's meant to bypass would skip it too) [Agent 3 finding]
- **Inner invocation details** [review 2026-09-22]:
  - `-m "no_parallel and not integration and not conformance"` — mirror the CI job's *full* filter, not just `not integration`.
  - Pass `-n 0` only; do **not** clear addopts (`-o addopts=`, as `test_worktree_utils.py:1519` does) or the inner run loses `--strict-markers`, `--strict-config` and `--timeout=120`. `-n 0` on the command line overrides the addopts `-n logical`.
  - Pass `-p no:ll_history` (or set `PYTEST_DISABLE_PLUGIN_LL_HISTORY=1` in `env`) so the nested session does not double-record into `history.db` via `little_loops.pytest_history_plugin`.
  - Pass `-p no:randomly` as the precedent does.
  - **Empty-set case**: once BUG-3522 drops the node gate's marker, and if the SSE marker is ever dropped too, `-m no_parallel ...` selects nothing and pytest exits **5** ("no tests collected"). The wrapper must accept return code `0` or `5` (or assert on the collected count from `-q` output), not fail on an empty set.
  - **Inner `--timeout=120` is the effective budget for `test_node_conformance_suite_passes`**: that test carries no `@pytest.mark.timeout`, only a `subprocess.run(..., timeout=180)`, so inside the nested run the suite-wide 120s watchdog governs it. Size the combined budget as SSE `180` + node `120` (not 180 + 180), plus inner startup/collection (~5-10s measured at 4.26s collection).
  - **Bounded retry**: on non-zero exit (excluding 5), re-run the inner command once; fail only if both attempts fail, with the first attempt's stdout/stderr tail included in the assertion message. Rationale in Decision Rationale ("Known trade-off").
  - **CI tail**: the wrapper holds one worker for roughly 3-5 minutes; under `--dist loadfile` it is a single-file unit, so the job's wall clock may lengthen by up to that on the slowest worker. Acceptable; noted so a slower CI run is not mistaken for a regression.

## Program Design

Decision landed: **option 2** (see Decision Rationale). The option-1/option-3
shapes below are retained for the record only; the committed design is the
`test_no_parallel_serial_pass` wrapper in `scripts/tests/test_no_parallel_serial_gate.py`.

### Types

- No new types for options 1/2. Option 3 needs no new dataclass — a
  collection-time enumeration over existing `pytest.Item` objects.

### Signatures

- `test_two_producers_reach_one_client_with_distinct_producer_pid(self, ...) -> None` — in `scripts/tests/test_feat3323_sse_bridge.py:217`, `TestSseBridgeFanIn` (L200); option 1 drops `@pytest.mark.no_parallel` (L215) and raises `@pytest.mark.timeout(180)` (L214) strictly above the documented ~100-105s worst case
- `pytest_collection_modifyitems(config, items) -> None` — in `scripts/tests/conftest.py`; unchanged by options 1/2, read (not modified) by option 3's meta-guard
- new: `test_no_parallel_markers_have_named_serial_invocation() -> None` (option 3 only) — a new test in `scripts/tests/`; enumerates collected items carrying the `no_parallel` marker and fails any that lack an explicit annotation naming their serial invocation
- new (option 2 — **the selected option**): `test_no_parallel_serial_pass() -> None` — wrapper test in new file `scripts/tests/test_no_parallel_serial_gate.py` (decided; `*_gate.py` convention of `test_policy_builder_node_gate.py`/`test_verify_evidence.py`). Shells out via `subprocess.run([sys.executable, "-m", "pytest", "scripts/tests/", "-n", "0", "-m", "no_parallel and not integration and not conformance", "-q", "-p", "no:randomly", "-p", "no:ll_history"], cwd=repo_root, capture_output=True, text=True, timeout=SERIAL_GATE_TIMEOUT)` and asserts `returncode in (0, 5)` (5 = empty set after future marker removals), copying `test_hook_session_start.py:731-763`'s idiom with one bounded retry on any other non-zero exit. Constant `SERIAL_GATE_TIMEOUT` sized as SSE `180` + node-gate effective `120` (inner `--timeout=120` governs it; it has no per-test marker) + ~30s inner startup/collection, i.e. **330** for the inner `subprocess.run` per attempt; the outer `@pytest.mark.timeout` must cover *both* attempts: `@pytest.mark.timeout(2 * SERIAL_GATE_TIMEOUT + 30)`, per the `GATE_TIMEOUT` convention cited below. Must **not** itself carry `@pytest.mark.no_parallel`. Does **not** clear addopts (`-n 0` alone overrides `-n logical`).

### Call Path

`pytest` collection -> `pytest_collection_modifyitems` (`scripts/tests/conftest.py`) -> skip items with `no_parallel` in `item.keywords` on xdist workers; option 3 adds `test_no_parallel_markers_have_named_serial_invocation` -> `pytest.Config` item enumeration -> assert against the annotation

## Acceptance Criteria

- The fan-in test either **executes** in the `unit-tests` CI job (its `pytest-junit.xml` artifact cited as passed) or runs via a **named, actually-executed** serial invocation — with the decision and rationale recorded in this issue
- If the marker is dropped: the per-test timeout is strictly above the documented 100-105s worst case, and repeated full-suite parallel runs show no BUG-3484-class worker kill
- If the meta-guard is chosen: it flags this test red today and passes once the decision lands
- BUG-3522's changes (marker removal on the node gate, `no_parallel` doc-row rewording) do not regress this file or its outcome

_Option-2 wiring ACs (added 2026-09-22 to resolve the `PROPOSAL_UNSOUND` verification verdict):_

- **AC-W1 (registration strings)**: both `pytest.ini:26` and `scripts/pyproject.toml:293` carry the corrected "controller never runs tests under `-n N`" wording **and** name `test_no_parallel_serial_gate.py` as the consumer; `pytest.ini`'s header sync rule holds.
- **AC-W2 (scope)**: the wrapper's inner `-m` expression is exactly `no_parallel and not integration and not conformance`; `test_fsm_signal_integration.py` is not collected by it (verify via `--collect-only` in the wrapper's own docstring or a companion assertion).
- **AC-W3 (timeout sizing)**: `SERIAL_GATE_TIMEOUT` covers SSE `180` + node-gate effective `120` + inner startup; the outer `@pytest.mark.timeout` strictly exceeds the sum of all inner attempts (`2 * SERIAL_GATE_TIMEOUT + 30`).
- **AC-W4 (not dormant itself)**: the wrapper carries no `@pytest.mark.no_parallel`, `integration`, or `conformance` marker, and `pytest scripts/tests/test_no_parallel_serial_gate.py -n 2 -q` reports it **passed**, not skipped.
- **AC-W5 (self-discovering)**: the inner run targets `scripts/tests/` by marker, never an explicit file list; adding `@pytest.mark.no_parallel` to any new unit test makes that test execute inside the wrapper with no edit to the wrapper.
- **AC-W6 (empty set)**: inner exit code `5` is treated as pass; documented in the wrapper's docstring.
- **AC-W7 (no side effects)**: the inner run passes `-p no:ll_history` (or the env opt-out) so `history.db` receives no nested session; addopts are **not** cleared.
- **AC-W8 (retry visible)**: on a first-attempt failure the wrapper retries once and, if the second attempt passes, the run still passes; if both fail, the assertion message includes both attempts' stdout/stderr tails.
- **AC-W9 (stale comments)**: `test_feat3323_sse_bridge.py:210-214` and `conftest.py:129-133` no longer claim the test runs "on the controller" and both name the wrapper.
- **AC-W10 (docs)**: `docs/development/TESTING.md` marker row and `docs/development/TROUBLESHOOTING.md` BUG-2523 section reworded per Files to Modify, unless BUG-3522 has already landed the identical reword (then verified only).

## Impact

- **Priority**: P3 — one test among 48 in the file (the rest run in CI), no ratified-gate violation as in BUG-3522; but it is the only remaining end-to-end coverage of the two-producer fan-in + pid-attribution path, so dormancy is not free
- **Effort**: Small (option 2 as decided)
- **Risk**: Low-Medium — test-infra only, but option 2 does **not** remove the BUG-3484 contention failure mode (the nested serial run still executes under full-suite xdist load); it converts a silent skip into a possibly-flaky, visibly-red single test whose worker-kill is contained to the nested subprocess. Mitigated by one bounded retry (see Decision Rationale, "Known trade-off"). If CI shows the wrapper failing on both attempts with a timeout signature, that is the signal to revisit option 1 or the fan-in test's own per-step budgets, not to re-add a bare marker.
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

## Status

**Open** | Created: 2026-09-21 | Priority: P3

## Implementation Steps

- ~~Reproduce the dormancy locally and confirm the sweep claim~~ — done (Current Behavior)
- ~~Decide between options 1-3~~ — done, option 2 (Decision Rationale)
- Create `scripts/tests/test_no_parallel_serial_gate.py` per Program Design Signatures (marker-scoped inner `-n 0` run, `-p no:ll_history -p no:randomly`, exit `0|5` accepted, one bounded retry, `SERIAL_GATE_TIMEOUT` = 330, outer `timeout(2*330+30)`)
- Verify locally: `pytest scripts/tests/test_no_parallel_serial_gate.py -n 2 -q` → passed (not skipped); inner run's `-q` output shows both `no_parallel` tests executed (or node gate skipped for a missing Node, which is exit 0)
- Reword registration strings (`pytest.ini:26`, `scripts/pyproject.toml:293`) and stale comments (`test_feat3323_sse_bridge.py:210-214`, `conftest.py:129-133`) to name the wrapper
- Reword `docs/development/TESTING.md` marker row and `docs/development/TROUBLESHOOTING.md` BUG-2523 section (or verify BUG-3522's identical reword if already landed)
- Confirm `test_conftest_cap.py::TestNoParallelMarkerRouting` still passes (hook unchanged)
- Run the full suite once with `-n logical` and note the wrapper's wall clock in the Resolution section (expected 3-5 min on one worker)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `pytest.ini:26` — reword the `no_parallel` registration string to match `scripts/pyproject.toml:293`'s already-corrected wording, and name the new wrapper test as its consumer (mirroring `grader_case` at `scripts/pyproject.toml:294`)
- Scope the new wrapper's `-m` expression to `no_parallel and not integration and not conformance` (the CI job's full filter) so it doesn't also pull in `test_fsm_signal_integration.py`'s doubly-marked class
- Size the new wrapper's timeout to cover the combined worst case of both currently-`no_parallel` tests: the SSE fan-in test's 180s budget and the node gate's **effective 120s** (inner `--timeout=120` governs it; its own 180s is a subprocess timeout with no pytest marker), plus inner startup — and the outer marker must cover both retry attempts
- Do not mark the new wrapper test itself `@pytest.mark.no_parallel` — it must run normally under `-n logical` so it actually executes in CI
- Pass `-p no:ll_history` on the inner run (no nested `history.db` session) and do not clear addopts
- Accept inner exit code 5 (empty set) as pass; retry once on any other non-zero exit
- Reword the stale "runs on the controller" comment in `test_feat3323_sse_bridge.py:210-214` and add the wrapper's name to `conftest.py:129-133`'s docstring

## Session Log
- `/ll:verify-issues` - 2026-09-22T15:45:41 - `bfb59371-f535-4c56-8b82-ba5a535b470c.jsonl`
- `/ll:wire-issue` - 2026-09-22T15:39:19 - `03d961d3-9a5a-4fcc-81d7-c9c6f85c6cd8.jsonl`
- `/ll:decide-issue` - 2026-09-22T15:32:23 - `ac5fb0be-e93b-41b1-bfc9-5ed4d9b825c2.jsonl`
- `/ll:refine-issue` - 2026-09-22T15:24:01 - `f6c11c46-8116-4e24-83a3-9e7ac209cbad.jsonl`
- `/ll:format-issue` - 2026-09-22T15:16:00 - `484f6d1d-ca00-4295-b7f6-7aec856c3eee.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- **File**: `scripts/tests/conftest.py`
- **Anchor**: `pytest_collection_modifyitems` (line 120)
- **Cause**: The hook adds `pytest.mark.skip(reason="no_parallel: cannot run on xdist workers")` (lines 143-146) to every item carrying the `no_parallel` keyword whenever `config.workerinput` is truthy — i.e. on every xdist worker, never on the controller (lines 140-142). Under `-n N` the controller only collects and distributes work and never executes a test body itself (the hook's own docstring, lines 129-131). `scripts/pyproject.toml`'s `addopts` pins `-n logical` (no `-n 0` anywhere in that file), and `.github/workflows/ci.yml`'s `unit-tests` job invokes `pytest scripts/tests/ -m "not integration and not conformance"` with no `-n` override, so it inherits that default. `test_two_producers_reach_one_client_with_distinct_producer_pid` carries neither `integration` nor `conformance`, so the job's `-m` filter collects it — it is then unconditionally skipped on every worker and never run on the controller. This is not a logic defect in the hook itself (it matches BUG-2523's original intent, and `scripts/tests/test_conftest_cap.py::TestNoParallelMarkerRouting` already covers the hook's routing correctness in isolation); the defect is that `@pytest.mark.no_parallel` was stacked onto this test — for a legitimate reason, BUG-3484's ~100-105s wall-clock budget exceeding the suite watchdog — with no compensating serial invocation added anywhere, so the coverage loss is silent rather than a deliberate, visible trade-off.
