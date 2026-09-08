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

## Steps to Reproduce

1. In a clean checkout, run `python -m pytest scripts/tests/` once — it passes and leaves `.ll/events.sock` and/or `.ll/events-<pid>.sock` behind (the socket-transport tests bind against the real project `.ll/` instead of `tmp_path`, or never call `close()`).
2. Without removing those files, run `python -m pytest scripts/tests/` again in the same checkout.
3. Observe: 35 failures in `scripts/tests/test_cli_loop_lifecycle.py` (`cmd_resume` transport tests) — `_claim_socket_path()` treats the stale, listener-less socket file as live and pushes the transport onto an `events-<pid>.sock` sibling path, breaking the wiring/teardown assertions.

## Expected Behavior

- No test writes into the checkout's real `.ll/`; socket-transport tests bind under `tmp_path` (or monkeypatch the project root) and close the transport in teardown.
- Two consecutive full-suite runs in the same checkout are both green with no manual cleanup.
- Ideally `_claim_socket_path()`'s stale-vs-live probe treats a socket with no listener as stale and reclaims it, so a crashed producer does not poison later runs either.

## Program Design

### Types

- N/A — no new data types; fix is test-hygiene plus an optional hardening tweak to existing logic.

### Signatures

- `_claim_socket_path(preferred: Path) -> Path` (existing, `scripts/little_loops/transport.py`) — stale-vs-live probe to harden against a listener-less socket file.
- `assert_ll_clean_after_session() -> None` (new, session-scoped autouse fixture in `scripts/tests/conftest.py`) — fails the session if any test leaves files under the real `.ll/`.

### Call Path

`scripts/tests/conftest.py::assert_ll_clean_after_session` (autouse fixture) -> snapshot `.ll/` contents before/after the session -> fail loudly on new files; offending tests (candidates: `scripts/tests/test_transport.py`, `scripts/tests/test_feat3323_sse_bridge.py`) -> `UnixSocketTransport(...)` bound under `tmp_path` -> `.close()` in teardown -> `_claim_socket_path()` reclaims a listener-less stale socket instead of treating it as live.

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
- `/ll:format-issue` - 2026-09-08T00:07:35 - `a2e8c1bc-23e1-4b7e-a7d7-ca1d7c6bb1b1.jsonl`
