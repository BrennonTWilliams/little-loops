---
id: BUG-2811
type: BUG
priority: P2
status: open
captured_at: "2026-07-25T21:08:26Z"
discovered_date: 2026-07-25
discovered_by: capture-issue
---

# BUG-2811: test_spawn_behavior asserts hardcoded "claude" binary, flakes under xdist

## Summary

`scripts/tests/test_handoff_handler.py::TestHandoffHandler::test_spawn_behavior`
asserts `cmd[0] == "claude"` against a host binary resolved at runtime from
ambient environment and config. The test performs no environment isolation, so
under a parallel run it can observe a different host and fail with
`AssertionError: assert 'codex' == 'claude'`.

Observed once during the v1.151.0 release run (2026-07-25) under
`python -m pytest scripts/tests/ -x -q -n 4`. The same test passes in isolation,
passes for its whole file, and a subsequent full unrestricted `-n 4` run of the
entire suite was green (16,259 passed) — so it is order/shard dependent, not a
deterministic failure.

## Current Behavior

`HandoffHandler._spawn` (`scripts/little_loops/fsm/handoff_handler.py:117`)
builds its command via the host abstraction:

```python
invocation = resolve_host().build_detached(prompt=prompt)
```

`resolve_host()` is called with no `env` argument, so it falls through its
documented precedence chain — `LL_HOST_CLI` → `LL_HOOK_HOST` → binary probe —
reading the ambient `os.environ` and project config at call time.

The test patches only `subprocess.Popen` and then asserts a literal:

```python
cmd = mock_popen.call_args[0][0]
assert cmd[0] == "claude"
```

There is no `monkeypatch.delenv("LL_HOST_CLI")` / `delenv("LL_HOOK_HOST")`, no
pinned config, and no autouse fixture in `scripts/tests/conftest.py` that
neutralizes host selection. Whatever host the ambient environment names at that
moment is what the assertion sees.

## Expected Behavior

The test should assert against a deliberately pinned host, so its verdict is a
property of `HandoffHandler` rather than of the environment or shard ordering.
It should pass identically in serial, under any `-n` value, and regardless of
what a previously-executed test left in `os.environ`.

## Root Cause

`scripts/little_loops/fsm/handoff_handler.py` → `HandoffHandler._spawn` —
resolves the host from ambient state, while
`scripts/tests/test_handoff_handler.py` → `TestHandoffHandler.test_spawn_behavior`
asserts a hardcoded binary name without isolating that state.

The repo's own `.ll/ll-config.json` pins `orchestration.host_cli: "claude-code"`,
which is why the test passes almost always — the failure requires another test
in the same worker process to have mutated the host signal first. Candidate
leak sources (not yet confirmed as the specific culprit) are the tests that
manipulate host selection: `test_host_runner.py`, `test_cross_host_baseline.py`,
`test_cli_doctor.py`, `test_cli_doctor_full.py`.

Note this is the same *class* of defect as the closed BUG-2489 / BUG-2523 /
BUG-2650 xdist-isolation flakes, but a distinct test and a distinct leaked
signal (host CLI selection rather than event-bus or subprocess state).

## Motivation

A flake in the release-gating suite is expensive out of proportion to its size:
`python -m pytest scripts/tests/` *is* this project's CI (see `.claude/CLAUDE.md`
§ Testing & CI Policy), so a spurious red under `-x` halts a release until a
human decides it is noise. It cost exactly that during the v1.151.0 run. It also
erodes the signal — a suite that cries wolf trains maintainers to re-run rather
than investigate.

## Proposed Solution

Pin the host explicitly in the test rather than relying on ambient state.
Preferred approach — neutralize the env and assert against the resolved host:

```python
def test_spawn_behavior(self, monkeypatch) -> None:
    monkeypatch.setenv("LL_HOST_CLI", "claude-code")
    monkeypatch.delenv("LL_HOOK_HOST", raising=False)
    with patch("subprocess.Popen") as mock_popen:
        ...
        assert cmd[0] == "claude"
```

Two alternatives worth weighing during implementation:

1. **Patch `resolve_host` at the handoff_handler seam** so the test exercises
   command *shape* independent of host identity — stronger isolation, but stops
   covering the real `build_detached` wiring.
2. **Add an autouse fixture in `scripts/tests/conftest.py`** that clears
   `LL_HOST_CLI`/`LL_HOOK_HOST` for every test that does not opt in. This fixes
   the whole class rather than this one instance, and would harden the other
   host-sensitive tests too — but it is a broader blast radius and should be
   checked against the tests that deliberately set those vars.

Option 3 is the more valuable fix if the leak turns out to affect more than this
one assertion; start by identifying the actual polluting test.

## Implementation Steps

1. Reproduce deterministically — bisect shard ordering (e.g. `-p no:randomly`
   plus explicit test selection, or `--dist loadfile`) to identify which test
   leaves the host signal mutated.
2. Fix the polluting test's cleanup if it is a missing `monkeypatch` teardown.
3. Pin the host in `test_spawn_behavior` per the snippet above.
4. Decide on the conftest autouse fixture based on step 1's blast radius.
5. Verify: run the full suite under `-n 4` and `-n 0`, plus a targeted repeat
   run of the affected file after the identified polluter.

## Impact

- **Severity**: low functional risk, moderate process risk. No shipped-code
  defect — `HandoffHandler` behaves correctly; only the test is under-specified.
- **Blast radius**: one test today; the underlying env leak may affect any test
  that calls `resolve_host()` without an explicit `env`.
- **Frequency**: observed once in one `-x -n 4` run; not reproducible on demand
  as of capture.

## Acceptance Criteria

- [ ] The polluting test (or ambient signal) is identified and named in the fix.
- [ ] `test_spawn_behavior` passes regardless of ambient `LL_HOST_CLI` /
      `LL_HOOK_HOST` values — verified by running it with `LL_HOST_CLI=codex` set.
- [ ] Full suite is green under both `-n 0` and `-n 4`.
- [ ] No new hardcoded host-binary literals are introduced (per `.claude/CLAUDE.md`
      § Host CLI Abstraction).

## Steps to Reproduce

Not deterministic. Observed via:

```bash
python -m pytest scripts/tests/ -x -q -n 4
# FAILED scripts/tests/test_handoff_handler.py::TestHandoffHandler::test_spawn_behavior
# AssertionError: assert 'codex' == 'claude'
# 1 failed, 15829 passed, 29 skipped in 176.00s
```

Passes in isolation:

```bash
python -m pytest scripts/tests/test_handoff_handler.py -q   # 11 passed
```

A forced-pollution reproduction should work as a regression check:

```bash
LL_HOST_CLI=codex python -m pytest \
  scripts/tests/test_handoff_handler.py::TestHandoffHandler::test_spawn_behavior -q
```

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` § Host CLI Abstraction | Defines `resolve_host()` as the only sanctioned host-selection path |
| `.claude/CLAUDE.md` § Testing & CI Policy | The local suite is the release gate, so flakes block releases |
| `docs/reference/HOST_COMPATIBILITY.md#orchestration-cli` | Host selection precedence and config keys |

## Session Log
- `/ll:capture-issue` - 2026-07-25T21:08:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/152bd4d1-0711-4abd-8c88-411ddf897de4.jsonl`

---

## Status

**Current**: open
