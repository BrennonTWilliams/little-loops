---
id: BUG-3484
type: BUG
title: SSE bridge two-producers test crashes xdist worker under full-suite CPU contention
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T03:53:50Z'
completed_at: '2026-09-16T03:59:13Z'
---

# BUG-3484: SSE bridge two-producers test crashes xdist worker under full-suite CPU contention

## Summary

`scripts/tests/test_feat3323_sse_bridge.py::TestSseBridgeFanIn::test_two_producers_reach_one_client_with_distinct_producer_pid`
occasionally crashes its entire xdist worker during a full-suite run instead
of failing normally: `[gwN] node down: Not properly terminated` /
`worker 'gwN' crashed while running '...test_two_producers_reach_one_client_with_distinct_producer_pid'`.

This is distinct from BUG-3481 (closed today), which fixed the controller
wedging forever after any worker crash via `--max-worker-restart=0`. That
fix makes the crash fail fast with a non-zero exit code — good for CI gating
— but does not address why THIS specific test occasionally kills its worker
in the first place.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

`scripts/little_loops/transport.py`'s `SseBridge`/`UnixSocketTransport` have
no deadlock or lock-ordering bug — every `recv()`, `Queue.get()`, and
`thread.join()` in the fan-in/relay/close paths is correctly wall-clock
timeout-bounded. The problem is a budget-vs-global-ceiling mismatch:

This test is the file's most thread/socket-heavy test (2 real
`UnixSocketTransport` producers + a full `SseBridge` with serve/fanin/relay
threads, 5 real thread hops before the test observes an event) and its own
legitimate worst-case wall-clock budget already sums close to the suite's
global pytest-timeout ceiling:

- `_sse_connect` + `_read_sse_headers`: 5s + 5s
- `_wait_until(...)`: 5s
- two `_read_sse_frame(..., timeout=30.0)`: 60s
- `finally`: `bridge.close()` + 2x `producer.close()`, each budgeted up to
  10s = 30s

Worst case ≈ 100-105s, against `scripts/pyproject.toml`'s
<!-- ll-evidence-ok: addopts string at scripts/pyproject.toml:267-268 (BUG-3484 capture, 2026-09-15) -->`"--timeout=120"` and `"--timeout-method=thread"`. Under full-suite CPU contention
(`-n <cpus-2>`, `--dist loadfile`) this occasionally tips past 120s. The
close-path timeouts are already exercised near their ceiling under ordinary
contention alone: an isolated single-file run of this test logged
`SseBridge: SSE handler thread did not exit within 2.0s`
(`.loops/tmp/scratch/feat3323-run3.txt`, this session).

Because pytest-timeout's thread-method watchdog cannot interrupt a blocked
C-level `recv()`/thread-join, when this test does exceed 120s the watchdog
hard-kills the whole worker (`os._exit`) rather than failing just the test —
matching the observed `node down`/`worker crashed` signature exactly. The
same test name (never a different test in the file) appeared in 3
independent full-suite crash logs this session
(`.loops/tmp/scratch/full-suite.txt`, `.loops/tmp/scratch/enh3472-fullsuite.txt`,
plus one more) — always
`TestSseBridgeFanIn::test_two_producers_reach_one_client_with_distinct_producer_pid`.

## Fix

Add `@pytest.mark.timeout(180)` to this one test so its legitimate worst
case has headroom under the global 120s ceiling. Chosen over tightening the
test's own step timeouts (already deliberately generous per the test's own
inline comments documenting prior CPU-contention flakiness — two rounds of
widening already landed) or marking it `no_parallel`/serial-only (would
remove this test from the default parallel gate entirely for a timing issue,
not a genuine parallel-unsafety issue).

## Acceptance Criteria

- [x] `test_two_producers_reach_one_client_with_distinct_producer_pid` carries
      `@pytest.mark.timeout(180)` (or equivalent per-test override)
- [x] Full suite still passes: `python -m pytest scripts/tests/`

## Resolution

- **Action**: fix
- **Completed**: 2026-09-16
- **Status**: Completed

### Changes Made
- `scripts/tests/test_feat3323_sse_bridge.py`: added `@pytest.mark.timeout(180)`
  to `TestSseBridgeFanIn::test_two_producers_reach_one_client_with_distinct_producer_pid`
  with a comment citing this issue and the worst-case-budget math, giving the
  test's legitimate ~100-105s worst case real headroom under the global
  `--timeout=120` ceiling instead of tightening its already-generous per-step
  timeouts or excluding it from the parallel gate.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 24561 passed, 51 skipped,
  exit 0, 232.30s; the target test itself passes standalone in 4.22s)
- Lint: PASS (`ruff check scripts/tests/test_feat3323_sse_bridge.py`)
- Format: PASS (`ruff format --check scripts/tests/test_feat3323_sse_bridge.py`)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Completed** | Created: 2026-09-16 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-16T03:54:37 - `04314571-fc25-426c-b42b-97698128ee34.jsonl`
