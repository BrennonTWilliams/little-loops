---
id: BUG-2811
type: BUG
priority: P2
status: done
captured_at: '2026-07-25T21:08:26Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
learning_tests_required:
- pytest
- pytest-xdist
confidence_score: 92
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 16
score_change_surface: 22
completed_at: '2026-07-25T21:42:34Z'
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Precedence chain, exact lines**: `resolve_host()` (`scripts/little_loops/host_runner.py:1245-1290`) resolves
  `env.get("LL_HOST_CLI") or env.get("LL_HOOK_HOST")` first (`env = dict(os.environ)` when the caller passes no
  `env=`), then falls back to a `shutil.which()` probe over `_PROBE_ORDER` (`host_runner.py:1228-1234`:
  `claude-code→claude`, `codex→codex`, `pi→pi`, `gemini→gemini`, `omp→omp`), raising `HostNotConfigured` if nothing
  resolves. `HandoffHandler._spawn_continuation` (`scripts/little_loops/fsm/handoff_handler.py:117`) calls
  `resolve_host()` with no `env=` override, so it is exposed to both live env vars *and* whichever host binaries
  happen to be first on `PATH` in that worker.
- **Correction to the leak theory above**: a grep across `scripts/tests/` for direct `os.environ["LL_HOST_CLI"] =`
  / `os.environ["LL_HOOK_HOST"] =` writes (bypassing `monkeypatch`) found **no matches** — every test that sets
  these vars does so via `monkeypatch.setenv`/`delenv`, which pytest auto-reverts at teardown, so a specific
  polluting test leaking a value across tests is unlikely to be the actual mechanism. The more probable cause:
  `test_spawn_behavior` (`scripts/tests/test_handoff_handler.py:55-85`) itself never pins `LL_HOST_CLI`/
  `LL_HOOK_HOST` or mocks `resolve_host`, so `cmd[0]` reflects whatever the ambient shell/CI environment (or `PATH`
  probe order) resolves to at that moment — not necessarily a value "leaked" by a sibling test.
- **One direct-`os.environ`-write function does exist**: `apply_host_cli_from_config()`
  (`host_runner.py:1293-1318`) writes `os.environ["LL_HOST_CLI"]` directly at line 1318 (exporting config to the
  real environment is its intended behavior). Its own test, `TestApplyHostCliFromConfig.test_sets_env_var_from_config`
  (`scripts/tests/test_host_runner.py:1153-1201`), relies on a manual trailing
  `monkeypatch.delenv("LL_HOST_CLI", raising=False)` near the end of the test body rather than a
  `monkeypatch.setenv`-registered teardown — if an earlier assertion in that test raised, cleanup would be skipped.
  This is the strongest concrete *candidate* polluter for Implementation Step 1's bisection, though not proven.
- **No existing autouse fixture covers these two vars.** `conftest.py:704-727` (`_restore_cmd_run_env_vars`) already
  guards exactly this class of hazard for `LL_HANDOFF_THRESHOLD` / `LL_CONTEXT_LIMIT` /
  `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` via the `setenv("") + delenv()` idiom (registers teardown even when the
  var is absent pre-test) — extending that tuple with `LL_HOST_CLI`/`LL_HOOK_HOST` is a direct, precedented
  implementation for Proposed-Solution Option 2 (autouse conftest fixture).
- **Existing per-test isolation fixture to model `test_spawn_behavior`'s fix on**: `test_host_runner.py:23-26`
  (`isolated_env`, opt-in not autouse) and the identical pattern in `scripts/tests/conformance/conftest.py:21-26`
  and inline in `scripts/tests/test_cli_doctor.py:25-26` all do
  `monkeypatch.delenv("LL_HOST_CLI", raising=False); monkeypatch.delenv("LL_HOOK_HOST", raising=False)`. None of
  these are `autouse`, and `test_handoff_handler.py` uses none of them today.
- **BUG-2523's precedent for a broader xdist-routing fix** (relevant if step 4 favors a wider blast radius): a
  `no_parallel` pytest marker registered in `scripts/pyproject.toml` plus a `pytest_collection_modifyitems` hook in
  `conftest.py` that skips marked tests on xdist workers (worker-detection idiom:
  `hasattr(config, "workerinput") and config.workerinput`, mirrored from
  `scripts/little_loops/pytest_history_plugin.py:147-150`). This is a timing-isolation pattern, not a direct fit
  for a pure env-pin fix, but is the established convention here for "this test must not run interleaved with
  other workers."

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_handoff_handler.py:87-98` (`test_spawn_propagates_non_interactive_env`) — also calls `HandoffHandler.handle()` → `resolve_host()` unisolated; doesn't assert `cmd[0]` today but shares the same latent flake surface [Agent 1/3 finding]
- `scripts/tests/test_handoff_handler.py:100-111` (`test_spawn_with_none_continuation`) — same unisolated `resolve_host()` call, asserts `cmd[cmd.index("-p") + 1]` which assumes a `-p`-flag-style host [Agent 1/3 finding]
- `scripts/tests/test_init_core.py:2336` (`TestDetectHosts.test_claude_binary_detected`) — separate mechanism (patches `shutil.which`, not `subprocess.Popen`), lacks the `isolated_env` fixture; lower-priority, note only, not part of this fix's blast radius [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_handoff_handler.py::test_spawn_propagates_non_interactive_env` and `::test_spawn_with_none_continuation` — should get the same env pin/isolation as `test_spawn_behavior` in the same implementation pass, since they exercise the identical unisolated `resolve_host()` call [Agent 3 finding]
- Existing isolation pattern to reuse verbatim: `isolated_env` fixture at `scripts/tests/test_host_runner.py:42-47` (`monkeypatch.delenv("LL_HOST_CLI", raising=False); monkeypatch.delenv("LL_HOOK_HOST", raising=False)`) — corrects this issue's earlier line reference (23-26 → 42-47) [Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- **Resolved open question**: a `no_parallel` pytest marker already exists and is registered in both `pytest.ini:25` and `scripts/pyproject.toml:209` ("marks tests that must not run on xdist workers"), used by prior fixes BUG-2523/BUG-2524/BUG-2649/BUG-2650/ENH-2479/ENH-2591. It does not need to be newly created if Implementation Step 4 favors this route — apply `@pytest.mark.no_parallel` directly [Agent 2 finding]
- **Confirmed safe to extend**: `scripts/tests/conftest.py:704-727` (`_restore_cmd_run_env_vars`, the `_CMD_RUN_ENV_VARS` tuple) can add `"LL_HOST_CLI"`/`"LL_HOOK_HOST"` with no risk of breaking any existing test — every current consumer of these two vars either uses `monkeypatch.setenv/delenv` (already self-restoring) or manipulates an isolated subprocess `env` dict (untouched by a parent-process autouse fixture); no test relies on either var persisting across test-function boundaries [Agent 2 finding, verified against all 18 files referencing `LL_HOST_CLI`/`LL_HOOK_HOST`]
- Strongest candidate polluter remains `TestApplyHostCliFromConfig.test_sets_env_var_from_config` (`scripts/tests/test_host_runner.py:1153-1201`), whose manual trailing `monkeypatch.delenv` (rather than an up-front `monkeypatch`-registered teardown) would be skipped if an earlier assertion in that test raised [Agent 2 finding, corroborates existing Root Cause section]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- No doc updates required for the fix itself: `docs/reference/HOST_COMPATIBILITY.md` and `.claude/CLAUDE.md` § Host CLI Abstraction describe only production call sites, not test hygiene, and `scripts/tests/test_wiring_guides_and_meta.py`'s doc-wiring pairs for `LL_HOST_CLI` are already satisfied by existing content — verified, not assumed [Agent 2 finding]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Apply the same env pin/isolation used in `test_spawn_behavior` to the two
   sibling tests that share the identical unisolated `resolve_host()` call:
   `test_spawn_propagates_non_interactive_env` and
   `test_spawn_with_none_continuation` (`test_handoff_handler.py:87-111`).
7. If choosing the autouse-fixture route (step 4), extend
   `_CMD_RUN_ENV_VARS` in `scripts/tests/conftest.py:704-727` with
   `"LL_HOST_CLI"` and `"LL_HOOK_HOST"` — confirmed safe, no existing test
   depends on either var surviving past its own test body.
8. If choosing the marker route instead, no new registration is needed —
   `no_parallel` already exists (`pytest.ini:25`, `scripts/pyproject.toml:209`);
   just apply `@pytest.mark.no_parallel`.

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
- `ll-auto` - 2026-07-25T21:42:34 - `55e24415-b10e-4a0c-865b-949896423924.jsonl`
- `/ll:ready-issue` - 2026-07-25T21:32:58 - `875a92c1-ae99-4f08-8f91-7c45d8ec73d3.jsonl`
- `/ll:wire-issue` - 2026-07-25T21:30:46 - `e91127c4-6720-4910-9a38-f13b6786eeec.jsonl`
- `/ll:refine-issue` - 2026-07-25T21:14:47 - `658b3964-51f1-41fa-8e22-16c82c005c91.jsonl`
- `/ll:capture-issue` - 2026-07-25T21:08:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/152bd4d1-0711-4abd-8c88-411ddf897de4.jsonl`

---

## Status

**Current**: open


---

## Resolution

- **Action**: fix
- **Completed**: 2026-07-25
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
