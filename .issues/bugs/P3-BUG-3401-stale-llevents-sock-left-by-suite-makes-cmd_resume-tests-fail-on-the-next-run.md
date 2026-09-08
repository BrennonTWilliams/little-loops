---
id: BUG-3401
type: BUG
title: Stale .ll/events-*.sock left by suite makes cmd_resume tests fail on the next
  run
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-07'
captured_at: '2026-09-07T23:44:14Z'
---

# BUG-3401: Stale .ll/events-*.sock left by suite makes cmd_resume tests fail on the next run

## Summary

Running the full unit suite on a tree where `.ll/events-*.sock` files already exist produces 35 failures in `scripts/tests/test_cli_loop_lifecycle.py` (the `cmd_resume` transport tests). The files are left behind by the suite's own earlier socket-transport tests, so a second consecutive run of `python -m pytest scripts/tests/` in the same checkout is red while a run after `rm .ll/events-*.sock` is green.

Observed 2026-09-07 while verifying the EPIC-3212 merge. `.ll/events.sock` and `.ll/events-<pid>.sock` were present with no live process holding them (`lsof -U` empty).

## Current Behavior

- Some socket-transport test (candidates: `scripts/tests/test_transport.py`, `scripts/tests/test_feat3323_sse_bridge.py`) binds `UnixSocketTransport` against the real project `.ll/` directory instead of `tmp_path`, or binds it there and never calls `close()`, so the socket file survives the test session.
- On the next run, `_claim_socket_path()` in `scripts/little_loops/transport.py` treats the stale file as a possible live listener (BUG-3324 sibling logic), pushes the transport onto an `events-<pid>.sock` sibling path, and the `cmd_resume` tests that assert on the wiring/teardown path fail.
- The failure is order- and state-dependent, so it looks like a regression in whatever branch was merged last. It cost an investigation cycle on EPIC-3212 before it was traced to the leftover files.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Codebase-locator and codebase-analyzer agents traced the two named candidate files and the `wire_transports()` call path itself, refining the leak hypothesis:

Every direct `UnixSocketTransport(...)` construction in `test_transport.py` and `test_feat3323_sse_bridge.py` (the two files this issue names as candidates) already binds under a `short_tmp_path` fixture (`tempfile.mkdtemp(prefix="ll-")`, not the real project `.ll/`) with a matching `.close()` in every case — confirmed by exhaustive grep across both files. Neither named candidate file's own transport tests appear to be the leak source as originally hypothesized.

The more likely mechanism, found by tracing `wire_transports()` itself (`scripts/little_loops/transport.py:1876-1917`): its `log_dir` parameter defaults to `Path(".ll")` **relative to the process's current working directory** when not explicitly passed (`base = log_dir if log_dir is not None else Path(".ll")`, line 1896) — this is a documented, intentional default for production use (real `ll-loop`/`ll-parallel` invocations run from a project root and are meant to write into that project's real `.ll/`). The three production call sites — `cmd_resume` (`cli/loop/lifecycle.py:737`), `cmd_run` (`cli/loop/run.py:623`), `main_parallel` (`cli/parallel.py:322`) — all call `wire_transports(bus, config.events)` with **no `log_dir` argument**. `EventsConfig.transports` defaults to an empty list (`config/features.py:1342`), so this only matters when something enables the `"socket"` transport. This repo's own `.ll/ll-config.json` does exactly that (`"events": {"transports": ["socket"]}`) — a test path that ends up consulting the real project's own config (rather than a fully isolated tmp-path config) while calling `cmd_resume`/`cmd_run`/`main_parallel` for real, without also passing an isolated `log_dir`, would write `.ll/events.sock` at the real repo root exactly as observed. This is a plausible, code-verified mechanism, not a confirmed root cause — the specific test/fixture combination that omits the `log_dir` override was not identified by this pass and needs runtime confirmation (e.g. bisecting with `-p no:randomly` or instrumenting `wire_transports` during a full-suite run).

## Steps to Reproduce

1. In a clean checkout, run `python -m pytest scripts/tests/` once — it passes and leaves `.ll/events.sock` and/or `.ll/events-<pid>.sock` behind (the socket-transport tests bind against the real project `.ll/` instead of `tmp_path`, or never call `close()`).
2. Without removing those files, run `python -m pytest scripts/tests/` again in the same checkout.
3. Observe: 35 failures in `scripts/tests/test_cli_loop_lifecycle.py` (`cmd_resume` transport tests) — `_claim_socket_path()` treats the stale, listener-less socket file as live and pushes the transport onto an `events-<pid>.sock` sibling path, breaking the wiring/teardown assertions.

## Expected Behavior

- No test writes into the checkout's real `.ll/`; socket-transport tests bind under `tmp_path` (or monkeypatch the project root) and close the transport in teardown.
- Two consecutive full-suite runs in the same checkout are both green with no manual cleanup.
- Ideally `_claim_socket_path()`'s stale-vs-live probe treats a socket with no listener as stale and reclaims it, so a crashed producer does not poison later runs either.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Codebase-locator confirmed no `.ll/` cleanliness fixture exists today and identified the nearest sibling fixture to model one after:

### Files to Modify
- `scripts/tests/conftest.py` — no existing fixture guards `.ll/` socket-file cleanliness (confirmed absent). Existing session-scoped isolation fixtures to model after: `_isolate_history_db_session` (~888) and `_guard_real_history_db` (~952-993), which patches `little_loops.session_store.sqlite3.connect` as a choke point and asserts the resolved path is never the real DB — its docstring explicitly notes this **replaced** an earlier before/after directory-snapshot approach because a snapshot can't attribute a leak to the offending test and isn't immune to concurrent external writers. This is directly relevant to the issue's own proposed `assert_ll_clean_after_session` shape (a snapshot-diff), which this codebase already tried and moved away from for a sibling problem.
- `scripts/little_loops/transport.py` — `_claim_socket_path()` (line 1559) and `_probe_socket_path()` (line 1529) are the existing stale-vs-live probe; `wire_transports()` (line 1876) is where the `log_dir`-default-to-cwd mechanism lives (see Current Behavior finding above).

### Dependent Files (Callers/Importers)
- Every direct `UnixSocketTransport(...)` construction in `scripts/tests/test_transport.py` and `scripts/tests/test_feat3323_sse_bridge.py` already binds under each file's own `short_tmp_path` fixture (`tempfile.mkdtemp(prefix="ll-")`) with a matching `.close()` — confirmed by exhaustive grep, not a leak source as originally hypothesized.
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdResumeTransportWiring`-style tests (~2277-2376) patch `little_loops.transport.wire_transports` entirely (`MagicMock(transports=[])`), never constructing a real socket. Hundreds of other real (non-mocked) `cmd_resume(...)`/`cmd_run(...)` calls exist in this file (lines 621-1524+) with `tmp_path` as the project-root argument — these are real invocations whose internal `wire_transports()` call still defaults `log_dir` to cwd-relative `.ll` regardless of the `tmp_path` project root passed to `cmd_resume` itself, if `config.events.transports` ends up containing `"socket"`.
- `scripts/tests/test_cli_e2e.py` — `e2e_project_dir` fixture (line 28) uses `tempfile.TemporaryDirectory()`, not the real repo `.ll/`; `test_ll_parallel_wires_transports` patches `wire_transports` entirely.

### Conventions in Force
- **Choke-point interception beats snapshot-diff** for this codebase's own established preference: `_guard_real_history_db` (`conftest.py:952-993`) patches the single function every real DB-open routes through and asserts at the moment of the violation; its docstring states this replaced "the previous mtime/size snapshot" approach specifically because a snapshot can't attribute a leak to the offending test and isn't safe against concurrent external writers (live `ll-auto`/`ll-loop` runs touching the same file). This is a documented precedent against the issue's own proposed `assert_ll_clean_after_session` snapshot shape — an implementer should read this docstring before choosing a mechanism.
- **Real-Transport-lifecycle convention**: every real `UnixSocketTransport`/`LocalBridgeTransport`/`SseBridge` construction anywhere in the test suite uses inline `try/finally: t.close()`, never a `yield`-based pytest fixture — there is no existing Transport-lifecycle fixture to reuse; a new one would be the first of its kind.
- **Stale-resource reclaim strategies disagree by resource type**: `_claim_socket_path`/`_probe_socket_path` (`transport.py`) reclaims by *connecting* to classify a socket as listener-less (no pid metadata exists on a socket file), whereas every other stale-reclaim path in the codebase (`fsm/concurrency.py::_process_alive`, `worktree_utils.py::_pid_is_live`, `cli/queue.py::_verify_owner_alive`) trusts a **recorded pid field** in the artifact and asks the OS via `os.kill(pid, 0)`. These are not interchangeable without adding a pid field to the socket-adjacent metadata — relevant if the "ideally `_claim_socket_path()` treats a listener-less socket as stale" hardening in Expected Behavior is pursued.
- `short_tmp_path` is duplicated (not imported) between `test_transport.py` and `test_feat3323_sse_bridge.py` deliberately, per an inline comment citing ruff F811 and "no existing precedent for cross-module fixture re-export" — a third consumer of this fixture should follow the same duplicate-don't-import convention unless that precedent changes.

### Tests
- `scripts/tests/test_transport.py:57-69` / `scripts/tests/test_feat3323_sse_bridge.py:56-70` — `short_tmp_path` fixture, the template for any new test needing an isolated AF_UNIX-safe socket directory (macOS `sun_path` 104-char limit is why `tmp_path` itself isn't used directly — see `docs/reference/API.md:10924,10929`, `BUG-1638`).

### Documentation
- `docs/reference/CONFIGURATION.md:1622-1656` — already documents, as a known and accepted limitation, that orphaned `events-<pid>.sock` files "are not swept by this or any other mechanism" and accumulate in `.ll/` across crashes. This confirms the sibling half of the bug (stale files from crashed producers, not just from the test suite) is a pre-existing, documented gap this issue's optional `_claim_socket_path()` hardening would also close.
- `docs/ARCHITECTURE.md:617-620` — table of which CLI entry points call `wire_transports()`/`close_transports()`.

## Program Design

### Types

- N/A — no new data types; fix is test-hygiene plus an optional hardening tweak to existing logic.

### Signatures

- `_claim_socket_path(preferred: Path) -> Path` (existing, `scripts/little_loops/transport.py`) — stale-vs-live probe to harden against a listener-less socket file.
- `assert_ll_clean_after_session() -> None` (new, session-scoped autouse fixture in `scripts/tests/conftest.py`) — fails the session if any test leaves files under the real `.ll/`.

### Call Path

`scripts/tests/conftest.py::assert_ll_clean_after_session` (autouse fixture) -> snapshot `.ll/` contents before/after the session -> fail loudly on new files; offending tests (candidates: `scripts/tests/test_transport.py`, `scripts/tests/test_feat3323_sse_bridge.py`) -> `UnixSocketTransport(...)` bound under `tmp_path` -> `.close()` in teardown -> `_claim_socket_path()` reclaims a listener-less stale socket instead of treating it as live.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

1. Confirm the actual leaking call path: run the full suite once, then re-run with a temporary instrumentation of `wire_transports()` (or a `strace`/`opensnoop`-style trace) to catch which call constructs `.ll/events.sock` at the real repo root without an isolated `log_dir` — the `test_transport.py`/`test_feat3323_sse_bridge.py` candidates named in the original bug report are not the source (see Current Behavior → Codebase Research Findings); the more likely mechanism is a real, non-mocked `cmd_resume`/`cmd_run`/`main_parallel` invocation combined with a config where `events.transports` includes `"socket"`, since `wire_transports()`'s `log_dir` defaults to cwd-relative `Path(".ll")` (`transport.py:1896`) whenever the caller omits it, which all three production call sites do by design.
2. Fix the confirmed offending test(s) to either isolate `log_dir` (mirroring `short_tmp_path`, `test_transport.py:57-69`) or ensure `config.events.transports` excludes `"socket"` in that fixture's config, plus `.close()`/teardown per the existing inline `try/finally` convention (no `yield`-fixture precedent exists for this in the codebase).
3. Add a choke-point guard, not a snapshot-diff — this codebase already tried and replaced a directory-snapshot approach for a sibling problem (`_guard_real_history_db`, `conftest.py:952-993`, docstring explains why); the equivalent for sockets would intercept the actual socket-bind/connect call and assert the resolved path is never under the real project `.ll/`.
4. `python -m pytest scripts/tests/` run twice back-to-back in a clean checkout is green both times; verified per the existing Acceptance Criteria.

## Impact

- **Priority**: P3 - test-hygiene defect; no production impact, but it manufactures false regressions and cost an investigation cycle during the EPIC-3212 merge review.
- **Effort**: Small - locate the offending test(s), move them to `tmp_path`, add teardown, add a `.ll/` cleanliness guard.
- **Risk**: Low - test-only change; the optional `_claim_socket_path()` hardening is a small, separately testable tweak.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Identify the test(s) that create `.ll/events*.sock` in the repo root; fix them to use `tmp_path` and to close the transport in teardown.
- [ ] Add a session-scoped guard (fixture or `conftest.py` check) that fails loudly if a test leaves files in the real `.ll/` directory.
- [ ] `python -m pytest scripts/tests/` run twice back-to-back in a clean checkout is green both times.
- [ ] The 35 `cmd_resume` failures reproduce with a hand-placed stale `.ll/events.sock` before the fix and do not after.

## Relates To

- BUG-3324 (socket claim/eviction logic), FEAT-3323 (SSE bridge tests)

## Status

**Open** | Created: 2026-09-07 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-08T00:56:23 - `c12a8469-1c0e-4551-abdc-a66d5e5d6bda.jsonl`
- `/ll:format-issue` - 2026-09-08T00:07:35 - `a2e8c1bc-23e1-4b7e-a7d7-ca1d7c6bb1b1.jsonl`
