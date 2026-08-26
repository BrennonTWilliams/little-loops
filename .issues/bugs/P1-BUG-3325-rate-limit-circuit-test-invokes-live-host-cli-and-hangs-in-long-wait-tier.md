---
id: BUG-3325
type: BUG
title: test_record_rate_limit_called_on_short_tier invokes the live host CLI on every suite run, then wedges its xdist worker
priority: P1
status: open
discovered_by: manual-review
discovered_date: '2026-08-26'
captured_at: '2026-08-26T00:00:00Z'
relates_to:
- BUG-3208
labels:
- tests
- fsm
- rate-limit
- ci-wedge
- billing
confidence_score: 100
outcome_confidence: 95
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 10
score_change_surface: 20
reconcile_attempted: true
---

# BUG-3325: `test_record_rate_limit_called_on_short_tier` invokes the live host CLI on every suite run, then wedges its xdist worker

## Summary

`TestRateLimitCircuitIntegration::test_record_rate_limit_called_on_short_tier`
(`scripts/tests/test_fsm_executor.py:7963`) has two fixture defects that compound.

**First**, its state uses `action="/work"`, which `_action_mode` classifies as
prompt mode, so `_evaluate` routes to `evaluate_llm_structured` → the real
`claude` binary. `MockActionRunner` mocks the *action* but never the
*evaluator*, so the test makes **live, billed API calls** — ~20s and real spend
per iteration, on every full-suite run. Every sibling test in the class uses
`action="work.sh"` and avoids this entirely.

**Second**, `MockActionRunner` runs out of indexed results after two calls and
its pattern-scan fallback returns the *first* `/work` match — the 429 — forever.
The state therefore climbs the short-burst tier to exhaustion and drops into the
**long-wait** tier, where it sleeps on the real unpatched ladder
(`_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER[0]` = **300 seconds**). The test patches
only `_DEFAULT_RATE_LIMIT_BACKOFF_BASE=0`, which collapses the short tier alone.

Under the repo's standard addopts (`--timeout=120 --timeout-method=thread`) this
is a guaranteed timeout, not a slow pass — a live instance of the wedge class
BUG-3208 is chasing (xdist #1094/#117 + pytest-timeout #72/#137, documented at
`scripts/pyproject.toml:144-160`).

No production code is at fault; see Root Cause for the trace that clears
`executor.py:2041`.

## Location

- **File**: `scripts/tests/test_fsm_executor.py`
- **Line(s)**: 7963 (test), 7991 (the lone `patch` context)
- **Anchor**: `TestRateLimitCircuitIntegration.test_record_rate_limit_called_on_short_tier`
- **Blocking site**: `scripts/little_loops/fsm/executor.py:3415` — the long-wait
  `self._interruptible_sleep(_wait, on_heartbeat=...)` call, which lands in
  `_interruptible_sleep`'s `time.sleep` loop at `executor.py:3549`.

```python
with patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0):
    executor = FSMExecutor(fsm, action_runner=runner, circuit=circuit)
    executor.run()
```

The sibling classes all patch the ladder as well. `TestRateLimitRetries`'
class docstring (`test_fsm_executor.py:7076-7079`) states the convention
explicitly:

> Tests that expect exhaustion also patch `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0]`
> and `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=0` so the long-wait tier collapses
> into an immediate exhaustion on first long-tier attempt.

There are 16 such patch sites in the file (`grep -n LONG_WAIT_LADDER`); this test
is not one of them.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- The file currently contains 5 occurrences of `LONG_WAIT_LADDER` (verified via `grep -c 'LONG_WAIT_LADDER' scripts/tests/test_fsm_executor.py`), not the 16 this section's estimate cites. Does not change the root cause or the fix; noted for the operator.

## Current Behavior

Reproduces unconditionally — this is **not** order-dependent and **not** an
artifact of plugin selection. Confirmed on `main` at `4761888fc`:

| Invocation | Result |
|---|---|
| `-k <test> -n 0 -p no:randomly` | hangs, faulthandler dump at `executor.py:3415` |
| `-k <test> -n 0` (default plugins) | hangs, identical stack |
| full file, `-n 0`, no `-k` | hangs at ~65% through the file, identical stack |

Also confirmed identical on a scratch worktree with PR #17 + PR #15 both merged,
so neither PR causes or fixes it.

The `--timeout-method=thread` watchdog dumps the traceback at 120s but cannot
kill the main thread in a serial run, so the process then hangs indefinitely
rather than failing. Under xdist it consumes the worker.

## Steps to Reproduce

```bash
python -m pytest scripts/tests/test_fsm_executor.py -q -n 0 \
  -k test_record_rate_limit_called_on_short_tier
# hangs; faulthandler prints:
#   File ".../fsm/executor.py", line 3415, in _handle_rate_limit
#     total_wait += self._interruptible_sleep(
#   File ".../fsm/executor.py", line 3549, in _interruptible_sleep
#     time.sleep(min(0.1, _deadline - time.time()))
```

## Expected Behavior

The test completes in milliseconds and asserts what its docstring claims — that a
**short-tier** 429 writes a backoff window to the `RateLimitCircuit`. It should
never enter the long-wait tier at all.

## Root Cause

**Traced end-to-end. Both defects are in the test fixture; no production code is
at fault.** The `executor.py:2041` reset is *correct* and must not be changed.

### Defect 1 — `action="/work"` puts the state in prompt mode, invoking the real host CLI

`_action_mode(state)` classifies a leading-slash action as `"prompt"`, and
`_evaluate` (`executor.py:2594-2607`) routes prompt-mode actions to
`evaluate_llm_structured(...)` → `host_runner.run_blocking_json` →
`subprocess.run`. **`MockActionRunner` only mocks the action, never the
evaluator**, so every iteration of this test shells out to a live `claude`
process.

Instrumented run, real values pulled from the returned `EvaluationResult`:

| Iter | verdict | `llm_model` | `llm_latency_ms` | `total_cost_usd` |
|---|---|---|---|---|
| 1 | `no` | sonnet | 20326 | 0.0794 |
| 2 | `cannot_judge` | sonnet | 20564 | 0.0794 |
| 3 | `no` | sonnet | 20771 | 0.0115 |
| 4 | `no` | sonnet | 21587 | 0.0115 |
| 5 | `no` | sonnet | 20288 | 0.0114 |

Real `session_id`s, real cache-token counts, ~$0.14 of billed spend in the five
iterations before the 120s timeout fired. This happens on **every full-suite
run**, and it is also why the test is slow enough to hit the timeout at all —
the 300s ladder sleep is the second-order problem, not the first.

Every sibling test in `TestRateLimitCircuitIntegration` uses
`action="work.sh"` (shell mode, no LLM eval) — including
`test_record_rate_limit_not_called_when_circuit_none` directly below it, and the
`_make_fsm` helper shared by `TestRateLimitRetries`
(`test_fsm_executor.py:7098`). This test is the only one in the file that builds
an inline FSM with a slash-command action. `"/work"` looks like a deliberate
choice but nothing in the test depends on prompt mode; the assertion is purely
about `RateLimitCircuit.get_estimated_recovery()`.

### Defect 2 — the mock serves the 429 forever after its indexed results run out

`MockActionRunner.run` uses indexed results only while
`call_index < len(results)` (`test_fsm_executor.py:93`). After that it falls
through to a **pattern scan that returns the first match**
(`test_fsm_executor.py:105-116`). Both configured entries use the pattern
`"/work"`, so from call 3 onward every action returns the **429** — the `ok`
result is unreachable.

### The traced sequence

```
[1] 429 (indexed 0) → EVAL 'no'  → HRL: record created, short_retries=1
[2] ok  (indexed 1) → EVAL 'cannot_judge' → not rate-limited →
                      else-branch POPs the record (executor.py:2041) → back to 'execute'
[3] 429 (fallback)  → EVAL 'no'  → HRL: record recreated, short_retries=1
[4] 429 (fallback)  → EVAL 'no'  → HRL: short_retries=2
[5] 429 (fallback)  → EVAL 'no'  → HRL: short_retries=3
[6] 429 (fallback)  → short tier exhausted (_short_max=3) → LONG-WAIT TIER
                    → _interruptible_sleep(300.0) on the unpatched ladder → wedge
```

### Why the `record=None` observation was a red herring

The reset seen at `[3]` is the `else` branch at `executor.py:2041` doing exactly
what it is documented to do: iteration `[2]` returned `exit_code=0`, which is a
genuine recovery, so the per-state retry record is correctly discarded. A
429 → success → 429 sequence *is* two separate rate-limit episodes. There is no
accumulator bug in `_handle_rate_limit`; `short_retries` increments correctly
(1 → 2 → 3) across `[3]`–`[5]` once the mock stops interleaving a success.

Note this also means the test never asserts what its docstring claims: the
circuit record it checks comes from an episode the fixture reaches by accident.

## Proposed Solution

Test-only. No production change.

1. **Switch the action to shell mode**: `action="work.sh"`, matching every
   sibling in the class. This alone removes the live `claude` invocation, the
   ~20s-per-iteration latency, and the billed spend. Nothing in the assertion
   requires prompt mode.
2. **Make the mock deterministic**: give the two results distinct patterns, or
   supply enough indexed results that the pattern-scan fallback is never
   reached, so the intended 429 → recovery sequence actually runs.
3. **Add the missing tier patches** —
   `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0]` and
   `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=0` — as a belt-and-braces guard, per
   the `TestRateLimitRetries` docstring convention
   (`test_fsm_executor.py:7076-7079`).
4. **Assert the tier**: the test claims short-tier behavior, so it should assert
   `short_retries` advanced and that the long-wait tier was never entered —
   otherwise it can silently regress back into the ladder.

### Follow-on hardening (worth splitting out)

Two structural gaps let this sit undetected, both broader than this test:

- **No guard against tests invoking the real host CLI.** `conftest.py` sanitizes
  `LL_HOST_CLI` (`conftest.py:729`) but nothing fails a test that actually spawns
  `claude`. An autouse fixture that makes `host_runner.run_blocking_json` raise
  unless explicitly opted into would have caught this immediately, and would
  catch the next one. This is the highest-value item here.
- **No guard against unpatched rate-limit ladders.** An autouse fixture scoped to
  the rate-limit classes patching the ladder to `[0]` makes the convention
  structural rather than per-test discipline.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- The established idiom for collapsing the ladder in this file is `patch.multiple("little_loops.fsm.executor", _DEFAULT_RATE_LIMIT_BACKOFF_BASE=0, _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0], _DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=0)` scoped to a `with` block around `executor.run()` (never a class-level `@patch`, never a fixture) — evidence: `test_fsm_executor.py:7172-7177`, `:7199-7203`, `:7220-7224`.
- The established idiom for making `MockActionRunner` deterministic through an exhaustion sequence is to over-provision indexed results (enough entries for every expected call) rather than rely on the pattern-scan fallback — evidence: `test_fsm_executor.py:7161-7169`, `[("work.sh", self._rl_result())] * (_DEFAULT_RATE_LIMIT_RETRIES + 3)`.
- The established idiom for asserting a call never happened is `mock.assert_not_called()` on a `patch(...)`-created `MagicMock` — evidence: `test_fsm_executor.py:3244-3249`, `:5002-5006`, `:5027-5031`, `:5820-5827`. No existing test in this file patches `run_blocking_json` directly for this purpose; every prompt-mode test instead patches `little_loops.fsm.executor.evaluate_llm_structured` (see Program Design's patch-target correction).

## Acceptance Criteria

- [ ] `test_record_rate_limit_called_on_short_tier` completes in under 1s.
- [ ] The test spawns **no** live host CLI call — verified by asserting on a
      patched `little_loops.fsm.executor.evaluate_llm_structured`, not
      `little_loops.host_runner.run_blocking_json` (unreachable from
      `fsm/evaluators.py`, which imports `run_blocking_json` directly), and not
      by wall-clock alone.
- [ ] The test asserts short-tier behavior explicitly: `short_retries` advanced,
      long-wait tier never entered.
- [ ] `python -m pytest scripts/tests/test_fsm_executor.py -q -n 0` completes with
      no faulthandler timeout dump.
- [ ] No rate-limit test can block on an unpatched
      `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER`.
- [ ] Full suite `python -m pytest scripts/tests/` shows this test passing rather
      than among the pre-existing timeout failures.

## Impact

- **Priority**: P1 — this is not merely a hung test. Every full-suite run makes
  live, billed Anthropic API calls (~$0.14 observed in one partial run, unbounded
  in principle since the loop only stops at the 120s timeout) and wedges an xdist
  worker via the same thread-method watchdog mechanism as BUG-3208.
- **Effort**: Small. Four test-only edits, no production change.
- **Risk**: Very low. Confined to one test function; the production reset it was
  suspected of exposing is confirmed correct and stays untouched.
- **Breaking Change**: No.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

**Files to modify:**
- `scripts/tests/test_fsm_executor.py` — the target test (`TestRateLimitCircuitIntegration.test_record_rate_limit_called_on_short_tier`, line 7964) and, if a class/session-scoped fixture is added, the `TestRateLimitCircuitIntegration` class body (7843-8250)
- `scripts/tests/conftest.py` — candidate location for the proposed `_no_live_host_cli`/ladder-guard autouse fixtures; the file's existing autouse fixtures (`_isolate_history_db_session`, `_isolate_history_db`, `_guard_real_history_db`, `_isolate_session_log_dir`, `_restore_cmd_run_env_vars`, `_reset_deprecated_key_warnings`) live at lines 553-762

**Dependent files (callers/importers):**
- `scripts/little_loops/fsm/executor.py:2011` — `FSMExecutor._execute_state()` calls `_handle_rate_limit()`, the function whose long-wait tier this test's fixture bug reaches unintentionally
- `scripts/little_loops/fsm/evaluators.py:1090` — `evaluate_llm_structured()` calls `run_blocking_json()`, the live-CLI call this test's fixture bug fails to intercept
- Other in-repo callers of `run_blocking_json()`: `scripts/little_loops/advisor.py:272` (`consult`), `scripts/little_loops/cli/artifact/discover.py:429`, `scripts/little_loops/cli/artifact/extract.py:166`, plus the direct unit tests in `scripts/tests/test_host_runner.py` `TestRunBlockingJson` (lines 1962-2030)

**Conventions in force:**
- Every `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER`/`_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS` patch site in this file uses `patch.multiple("little_loops.fsm.executor", _DEFAULT_RATE_LIMIT_BACKOFF_BASE=0, _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0], _DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=0)` scoped to a `with` block around `executor.run()` — never a class-level `@patch`, never a fixture — evidence: `test_fsm_executor.py:7172-7177`, `:7199-7203`, `:7220-7224`; the sole intentional exception is `test_fsm_executor.py:7808-7813`, which patches a non-zero ladder on purpose to observe a real short sleep
- Tests that expect an exhaustion sequence over-provision `MockActionRunner`'s indexed results (enough entries for every expected call) rather than rely on the pattern-scan fallback — evidence: `test_fsm_executor.py:7161-7169`, `[("work.sh", self._rl_result())] * (_DEFAULT_RATE_LIMIT_RETRIES + 3)`
- Prompt-mode evaluation tests in this file patch the imported name `little_loops.fsm.executor.evaluate_llm_structured` (the executor module's own bound reference), not `little_loops.host_runner.run_blocking_json` — evidence: `test_fsm_executor.py:571, 623, 1681, 1748, 1812, 8094, 10838`. This matters here: `scripts/little_loops/fsm/evaluators.py:46` imports `run_blocking_json` directly (`from little_loops.host_runner import (...)`), so it is bound as `little_loops.fsm.evaluators.run_blocking_json` — patching `little_loops.host_runner.run_blocking_json` would not intercept the call this test needs to block.
- The codebase's idiom for asserting a side-effecting call never happened is `mock.assert_not_called()` on a `patch(...)`-created `MagicMock` — evidence: `test_fsm_executor.py:3244-3249`, `:5002-5006`, `:5027-5031`, `:5820-5827`
- No existing autouse fixture in `scripts/tests/conftest.py` patches the rate-limit ladder constants or guards the host-CLI subprocess boundary. The closest analog for the proposed `_no_live_host_cli` fixture is `_guard_real_history_db` (`conftest.py:617-657`) — a session-scoped autouse fixture that monkeypatches a single choke point and asserts if it resolves to production state, with no marker-based opt-out (legitimate calls are routed around it by a sibling isolation fixture)

**Tests:**
- `scripts/tests/test_fsm_executor.py:7843-8250` — `TestRateLimitCircuitIntegration`; already carries the `no_parallel` marker (per its class docstring, landed for BUG-2524) because a *different* test's real short-tier wall-clock sleep crashed xdist workers under contention — an existing, unrelated mitigation that does not address this issue's live-CLI-call or long-wait-tier symptoms
- `scripts/tests/test_fsm_executor.py:7072-7079` — `TestRateLimitRetries` class docstring states the ladder-patching convention explicitly

**Related issues:**
- `.issues/bugs/P3-BUG-2524-xdist-worker-crash-on-rate-limit-test.md` — prior sibling bug on this same test class; landed the `no_parallel` marker referenced above

## Program Design

### Signatures

No production signatures change. Proposed test-side additions:

- `_no_live_host_cli()` — autouse pytest fixture (session- or module-scoped) that patches `little_loops.host_runner.run_blocking_json` to raise, so any test that reaches the real host CLI fails loudly instead of silently spending money. Opt-out via an explicit marker for tests that genuinely exercise the host path.
- `_rate_limit_ladder_patched()` — autouse fixture scoped to the rate-limit test classes, patching `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER` to `[0]` and `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS` to `0`.

### Call Path

The path that must stop being reached:
`_execute_state` (`executor.py:1872`) → `_evaluate` (`executor.py:2603`) →
`evaluate_llm_structured` (`fsm/evaluators.py:1090`) → `run_blocking_json`
(`host_runner.py:2146`) → `subprocess.run`. Switching `action="/work"` to
`action="work.sh"` diverts `_action_mode` away from `"prompt"` before
`_evaluate` is reached.

The path that must terminate:
`_handle_rate_limit` short tier (`executor.py:3396-3402`) → long tier
(`executor.py:3406-3427`) → `_interruptible_sleep` (`executor.py:3545-3554`).
Patching the ladder collapses the long tier; fixing the mock keeps the test in
the short tier where it belongs.

### Testing Strategy

- Verify serially (`-n 0`) and under default xdist — the failure shows as a
  *hang* in the former and a *timeout* in the latter.
- Assert on the patched `run_blocking_json` mock, not on elapsed time; a
  wall-clock assertion would pass on a fast-but-still-live call.
- Re-run the whole `test_fsm_executor.py` file, not just `-k` the one test: the
  full-file serial run is the reproduction that proved this is unconditional.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- **Patch-target correction for the proposed "no live host CLI" fixture and for the Acceptance Criteria assertion**: `scripts/little_loops/fsm/evaluators.py:46` imports `run_blocking_json` directly (`from little_loops.host_runner import (...)`), so within that module it is bound as `little_loops.fsm.evaluators.run_blocking_json`, not reachable via a patch on `little_loops.host_runner.run_blocking_json`. The latter target is wrong for intercepting this call. The codebase's existing convention for prompt-mode tests in this file is instead to patch `little_loops.fsm.executor.evaluate_llm_structured` — evidence: `test_fsm_executor.py:571, 623, 1681, 1748, 1812, 8094, 10838`.
- **`_action_mode()` classification confirmed** at `scripts/little_loops/fsm/executor.py:2844-2859` — explicit `action_type` fields are checked first (`"contract"`, `"mcp_tool"`, `"prompt"`/`"slash_command"`, `"shell"`, contributed actions); only when none are set does it fall to the leading-`/`-prefix heuristic that classifies `action="/work"` as `"prompt"` mode.
- **`_evaluate()` dispatch confirmed** at `scripts/little_loops/fsm/executor.py:2571-2621`; the prompt-mode branch calls `evaluate_llm_structured()` unconditionally on `action_result` truthiness — it does not first inspect `exit_code`, so a mocked 429-shaped `ActionResult` (still a truthy object) triggers the live-CLI call regardless of the mock's intended semantics. The rate-limit-specific text classification that routes into `_handle_rate_limit()` only happens afterward, at `executor.py:1997-2014` — the live-CLI call happens on every "execute" iteration in this test, not only the ones the mock intends as 429s.
- **Existing fixture precedent for the proposed guard**: `_guard_real_history_db` (`scripts/tests/conftest.py:617-657`) is the closest existing analog — a session-scoped autouse fixture that monkeypatches a single choke point and asserts if it resolves to a real/production target, with no marker-based opt-out (legitimate calls are routed around it by a sibling isolation fixture). No fixture in this codebase currently guards the host-CLI subprocess boundary or the rate-limit ladder constants.

## Status

**Open** | Created: 2026-08-26 | Priority: P1

## Notes

Split out during review of PR #17 / PR #15 (both BUG-3208). Neither PR touches
this path; both were verified against it. Filed as a sibling of BUG-3208 rather
than a standalone flake because the 120s thread-method timeout on a blocking test
is the same worker-wedge mechanism.


## Session Log
- `/ll:reconcile-issue` - 2026-08-26T17:23:20 - `5a39850d-35a2-49b4-a59f-151abf0cd32d.jsonl`
- `/ll:refine-issue` - 2026-08-26T17:08:08 - `2be9d313-ffa2-4c26-a423-8e5a0df02ae0.jsonl`
