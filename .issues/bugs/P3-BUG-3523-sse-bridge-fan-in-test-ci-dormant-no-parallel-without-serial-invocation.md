---
id: BUG-3523
type: BUG
title: SSE bridge fan-in test is CI-dormant — no_parallel marker with no serial invocation anywhere
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

This is a **decision-shaped issue** — pick one and record the rationale here:

1. **Drop the marker, widen the budget.** If BUG-3484-era contention flakiness is no longer reproducible, remove `no_parallel` and set `@pytest.mark.timeout(N)` strictly above the documented 100-105s worst case plus margin (the `test_verify_evidence.py` `GATE_TIMEOUT + 30` convention; BUG-3522 uses 240 for the same reason). Prerequisite: a stress demonstration (repeated full-suite `-n logical` runs) showing the watchdog no longer fires, because the C-level block cannot be interrupted — budget ≥ worst case is the only protection.
2. **Keep the marker, make the serial invocation real.** Add an explicit serial pass for the `no_parallel` set (e.g. a CI step or documented local command running `python -m pytest scripts/tests/ -n 0 -k <the set>`). Must stay within the AGENTS.md Testing & CI Policy shape (a pytest invocation under the local suite, no new hosted/paid CI); mind the cost — a full serial suite is ~24k tests, so scope the `-k` selection.
3. **Meta-guard (structural; may be split as its own ENH).** A collection-time test that enumerates `no_parallel`-marked items and fails (or requires an explicit annotation naming the serial invocation) for any that lack one — turning "marker = silent coverage removal" into a visible decision. BUG-3522's history is the motivation: a marker landed as a "fix" and silently deleted the ratified FEAT-2390 gate from CI.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- **Dormancy mechanism confirmed identical to BUG-3522**: `pytest_collection_modifyitems` (`scripts/tests/conftest.py:120-146`) skips `no_parallel`-marked items on every xdist worker; `scripts/pyproject.toml` addopts pin `-n logical` with no `-n 0` anywhere; `.github/workflows/ci.yml`'s `unit-tests` job (~lines 127-128) runs `pytest scripts/tests/ -m "not integration and not conformance"` with no `-n` override, so the fan-in test — carrying neither marker — is collected then skipped on every worker.
- **Marker origin**: `@pytest.mark.no_parallel` (`test_feat3323_sse_bridge.py:215`) is stacked under `@pytest.mark.timeout(180)` (line 216); the comment block at lines 201-214 attributes both to BUG-3484 and documents a ~100-105s worst-case wall-clock budget for the full two-producer + `SseBridge` + 5-real-thread-hop path, which under full-suite xdist contention can exceed both `--timeout=120` and `timeout(180)` — and pytest-timeout's thread-method watchdog cannot interrupt a blocked C-level `recv()`/thread-join, so it hard-kills the whole worker via `os._exit` rather than failing the one test.
- **What coverage is lost**: `SseBridge`'s multi-thread fan-in path in `scripts/little_loops/transport.py` — `_fan_in_producer_sockets` (line 1069) spawning one `_read_producer_socket` (line 981) reader thread per connected producer, merging onto the shared `_fanin_queue`, relayed to SSE clients by `_relay_loop` (line 1440) — is exercised with **two simultaneously connected producers** only by this test. Every other `TestSseBridgeFanIn` test in the file uses a single producer and carries no `no_parallel` marker, so it runs in CI; only the two-producer merge and the `producer_pid`-attribution-under-fan-in guarantee (stamped per-copy at `transport.py:321-326`, `stamped = {**event, "producer_pid": os.getpid()}`) is unverified in CI.
- **Dependent/precedent files** (mirrors BUG-3522's sweep exactly): `scripts/tests/test_fsm_signal_integration.py` (module-level `pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]`, line 42 — doubly excluded via its own `integration` marker, not a genuine dormancy case), `scripts/tests/test_policy_builder_node_gate.py` (BUG-3522's own subject, identical mechanism), `scripts/tests/test_conftest_cap.py::TestNoParallelMarkerRouting` (lines 143-220 — unit-tests the hook's routing logic in isolation via synthetic `MagicMock` items; must keep passing regardless of which option is chosen here), `scripts/tests/test_dependency_mapper.py:938` and `scripts/tests/test_worktree_utils.py:1471-1480` (both name/comment matches only, not the real marker — the latter explicitly rejects `no_parallel` in favor of a nested serial `pytest ... -n 0` subprocess invoked from inside a normally-scheduled test).
- **Doc surface needing the same reword BUG-3522 already flagged**: `docs/development/TESTING.md` (`no_parallel` marker-table row, ~line 1050) still reads "runs on the controller or in a serial `-n 0` invocation"; `docs/development/TROUBLESHOOTING.md` (BUG-2523 section, ~lines 825-835) still reads "The tests still run — they just don't share cores with six other pytest invocations." Both predate the corrected wording already landed in `scripts/pyproject.toml:293`'s `no_parallel` marker registration string ("the controller never runs tests under `-n N`; it only actually runs in a serial `-n 0` invocation").
- **No existing convention pairs a `no_parallel` marker with a required serial-invocation declaration** — the closest analog is the `grader_case` marker, whose registration string names its consuming meta-test (`test_grader_coverage.py`); `no_parallel`'s registration string does not name one, because none exists yet. The closest precedent for Proposed Solution option 3's shape is `scripts/tests/test_grader_coverage.py` (`TestGraderCoverage`, line 115+), which AST-scans `scripts/tests/*.py` source text (not pytest's own collection/session machinery, deliberately — so a subset run like `-k`/`--lf`/mutmut's `-n0` selection doesn't false-fail) and asserts a coverage property about decorator usage.

## Program Design

This is decision-shaped (see Proposed Solution options 1-3); the shapes below
cover the identifiers each option touches, not a single committed design.

### Types

- No new types for options 1/2. Option 3 needs no new dataclass — a
  collection-time enumeration over existing `pytest.Item` objects.

### Signatures

- `test_two_producers_reach_one_client_with_distinct_producer_pid(self, ...) -> None` — in `scripts/tests/test_feat3323_sse_bridge.py:217`, `TestSseBridgeFanIn` (L200); option 1 drops `@pytest.mark.no_parallel` (L215) and raises `@pytest.mark.timeout(180)` (L214) strictly above the documented ~100-105s worst case
- `pytest_collection_modifyitems(config, items) -> None` — in `scripts/tests/conftest.py`; unchanged by options 1/2, read (not modified) by option 3's meta-guard
- new: `test_no_parallel_markers_have_named_serial_invocation() -> None` (option 3 only) — a new test in `scripts/tests/`; enumerates collected items carrying the `no_parallel` marker and fails any that lack an explicit annotation naming their serial invocation

### Call Path

`pytest` collection -> `pytest_collection_modifyitems` (`scripts/tests/conftest.py`) -> skip items with `no_parallel` in `item.keywords` on xdist workers; option 3 adds `test_no_parallel_markers_have_named_serial_invocation` -> `pytest.Config` item enumeration -> assert against the annotation

## Acceptance Criteria

- The fan-in test either **executes** in the `unit-tests` CI job (its `pytest-junit.xml` artifact cited as passed) or runs via a **named, actually-executed** serial invocation — with the decision and rationale recorded in this issue
- If the marker is dropped: the per-test timeout is strictly above the documented 100-105s worst case, and repeated full-suite parallel runs show no BUG-3484-class worker kill
- If the meta-guard is chosen: it flags this test red today and passes once the decision lands
- BUG-3522's changes (marker removal on the node gate, `no_parallel` doc-row rewording) do not regress this file or its outcome

## Impact

- **Priority**: P3 — one test among 48 in the file (the rest run in CI), no ratified-gate violation as in BUG-3522; but it is the only remaining end-to-end coverage of the two-producer fan-in + pid-attribution path, so dormancy is not free
- **Effort**: Small (option 1/2) to Medium (option 3)
- **Risk**: Low — test-infra only; option 1 carries the watchdog-recurrence risk called out above, hence the stress prerequisite
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-21 | Priority: P3

## Implementation Steps

- Reproduce the dormancy locally (`-n 2` run shows the skip) and confirm the sweep claim (only genuine additional case)
- Decide between Proposed Solution options 1-3; record the rationale in this issue
- Implement: marker/timeout change, serial invocation, or meta-guard (possibly split as an ENH with this bug as its first customer)
- Stress-verify per the chosen option's acceptance criterion
- Coordinate the shared doc surface with BUG-3522: `docs/development/TESTING.md` marker table and `docs/development/TROUBLESHOOTING.md` BUG-2523 section both reword "runs on the controller" claims

## Session Log
- `/ll:format-issue` - 2026-09-22T15:16:00 - `484f6d1d-ca00-4295-b7f6-7aec856c3eee.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- **File**: `scripts/tests/conftest.py`
- **Anchor**: `pytest_collection_modifyitems` (line 120)
- **Cause**: The hook adds `pytest.mark.skip(reason="no_parallel: cannot run on xdist workers")` (lines 143-146) to every item carrying the `no_parallel` keyword whenever `config.workerinput` is truthy — i.e. on every xdist worker, never on the controller (lines 140-142). Under `-n N` the controller only collects and distributes work and never executes a test body itself (the hook's own docstring, lines 129-131). `scripts/pyproject.toml`'s `addopts` pins `-n logical` (no `-n 0` anywhere in that file), and `.github/workflows/ci.yml`'s `unit-tests` job invokes `pytest scripts/tests/ -m "not integration and not conformance"` with no `-n` override, so it inherits that default. `test_two_producers_reach_one_client_with_distinct_producer_pid` carries neither `integration` nor `conformance`, so the job's `-m` filter collects it — it is then unconditionally skipped on every worker and never run on the controller. This is not a logic defect in the hook itself (it matches BUG-2523's original intent, and `scripts/tests/test_conftest_cap.py::TestNoParallelMarkerRouting` already covers the hook's routing correctness in isolation); the defect is that `@pytest.mark.no_parallel` was stacked onto this test — for a legitimate reason, BUG-3484's ~100-105s wall-clock budget exceeding the suite watchdog — with no compensating serial invocation added anywhere, so the coverage loss is silent rather than a deliberate, visible trade-off.
