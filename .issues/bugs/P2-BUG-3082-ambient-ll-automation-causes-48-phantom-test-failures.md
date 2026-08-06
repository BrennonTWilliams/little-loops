---
id: BUG-3082
title: Ambient LL_AUTOMATION makes 48 tests fail inside automation runs, falsely
  reddening every loop-run verification gate
type: BUG
priority: P2
status: done
testable: true
discovered_by: manual-investigation
discovered_date: 2026-08-06
discovered_commit: ea220c9d
discovered_branch: main
completed_at: '2026-08-06T05:44:21Z'
relates_to:
- ENH-2714
- BUG-3058
- BUG-3080
- ENH-3081
labels:
- automation
- testing
- hermeticity
- hooks
size: Small
verify_verdict: VALID
---

# BUG-3082: Ambient `LL_AUTOMATION` causes 48 phantom test failures inside automation runs

## Summary

Every full-suite run captured on 2026-08-05 from inside a `refine-to-ready-issue` /
`ll-auto` session reported exactly **48 failed** across seven test files. The same
suite run from an interactive shell passed clean (18473 passed, 42 skipped).

The tests were correct and the production code was behaving as designed. The suite
was **not hermetic with respect to `LL_AUTOMATION`** — a var that automation runs
export into every descendant process, including the agent's own `pytest`.

## Current Behavior

Seven scratch logs (`.loops/tmp/scratch/test-results.txt`, `test-bug3065-full.txt`,
`enh3050-full.txt`, `test-bug3072-full.txt`, `test-results-enh3061.txt`,
`full-test-results.txt`, `test-results-enh3047-v2.txt`), spanning 13:23–23:37 on
2026-08-05, all end in `48 failed`. Breakdown:

| File | Failures |
|---|---|
| `test_hook_session_start.py` | 24 |
| `test_history_context_cli.py` | 17 |
| `test_hooks_integration.py` | 3 |
| `test_codex_adapter.py` | 1 |
| `test_kimi_adapter.py` | 1 |
| `test_opencode_adapter.py` | 1 |
| `test_hook_intents.py` | 1 |

Representative assertion:

```
assert result.stdout is None
E  AssertionError: assert 'You are running headlessly. Ending your turn ends the
   session. ...' is None
```

## Steps to Reproduce

```bash
LL_AUTOMATION=1 python -m pytest \
  scripts/tests/test_hook_session_start.py scripts/tests/test_history_context_cli.py \
  scripts/tests/test_hook_intents.py scripts/tests/test_hooks_integration.py \
  scripts/tests/test_codex_adapter.py scripts/tests/test_kimi_adapter.py \
  scripts/tests/test_opencode_adapter.py -q -p no:randomly
# → 48 failed, 223 passed
```

Without the var: 271 passed. Deterministic, not order- or seed-dependent.

## Expected Behavior

The test suite produces identical results regardless of ambient `LL_*` environment
state. A run launched from inside an automation session must not report failures
that a run from an interactive shell does not.

## Root Cause

Single cause, two symptom families.

**1. The var reaches the whole process tree.** `host_runner.py:352` (and four
sibling blocks at `:645, :1037, :1224, :1419`) sets `env["LL_AUTOMATION"]="1"`
whenever `automation_profile` is passed. `subprocess_utils.py:412-425` merges it
via `os.environ.copy()`, so it is a plain exported env var inherited by the spawned
`claude -p`, its Bash tool shells, and any `python -m pytest` those shells run.
Nothing anywhere unsets it (see ENH-3081).

Setters that were live on 2026-08-05: `refine-to-ready-issue.yaml` declares
`pruning_profile:` at `:161, 178, 228, 276, 529` (that loop ran all day — see
`.loops/runs/refine-to-ready-issue-*`), and `issue_manager.py:1213` hardcodes
`automation_profile="ll-auto"` for Phase 2, added by BUG-3058.

**2. Two ENH-2714 pruning gates read it and suppress output.** Both secondary-gate
on `history.automation_pruning.enabled`, which **defaults to `True`**
(`config/features.py:1034-1041`), so even a bare `tmp_path` cwd with no config
prunes:

- `hooks/session_start.py:110` — early-returns
  `LLHookResult(exit_code=0, feedback=None, stdout=_STAY_IN_TURN_INSTRUCTION)`,
  killing the config JSON, the `<project_context>` digest, **and all stderr
  warnings**. This is the single gate behind 30 of the 48 failures; the adapter and
  dispatcher tests are thin wrappers that funnel into the same `handle()`.
- `cli/history_context.py:198` — returns `0` with no output *before* the
  argument-validation guards, so even `parser.error()` paths go silent. Accounts
  for the 17 `test_history_context_cli.py` failures, including the ones asserting
  `SystemExit(2)` on malformed args. Filed separately as BUG-3080.

**3. No test scrubbed it.** The `in_tmp` fixture
(`test_hook_session_start.py:18-22`) isolates cwd only. The subprocess-based tests
call `subprocess.run(...)` with no `env=`, so they inherit `os.environ` too. The
autouse `_restore_cmd_run_env_vars` fixture (`conftest.py:725`) existed but its
allowlist did not include `LL_AUTOMATION`.

`test_no_automation_env_no_stay_in_turn_instruction` is the sharpest example: it
asserts the *absence* of automation behavior while never guaranteeing the var is
absent.

## Impact

Not cosmetic. Inside any `ll-auto` / FSM-loop run, the agent's own
`python -m pytest scripts/tests/` reported 48 failures that did not exist — a
**false-red verification gate on exactly the phase meant to validate an
implementation**. Any loop state gating on a green suite could not pass, and any
agent reading the output would chase nonexistent regressions.

## Resolution

Fixed in commit `0add15cd`, *"fix(tests): scrub LL_AUTOMATION env vars and verify
suite hermeticity with ambient automation"*. Test-side only — no production
behavior changed, because `session_start.py` and `history_context.py` behave as
ENH-2714 designed.

**1. Scrub — `scripts/tests/conftest.py`.** Added `LL_AUTOMATION` and
`LL_AUTOMATION_PROFILE` to `_CMD_RUN_ENV_VARS`, consumed by the existing autouse
`_restore_cmd_run_env_vars` fixture. The established `setenv("") + delenv()` idiom
registers a teardown even when the var was absent, so it both scrubs an inbound
ambient value and prevents outbound leaks. Because it mutates `os.environ`, one
change covers in-process *and* subprocess tests. The comment block was widened to
document the two distinct hazards (leak-out per BUG-2011, leak-in per this bug).

Compatible with the tests that *want* the gate
(`test_hook_session_start.py:538, :565`): they `monkeypatch.setenv` in the test
body, after the autouse fixture ran, on the same function-scoped instance.
`test_host_runner.py:965-966` asserts on the returned `invocation.env` dict, not
`os.environ`, so it is unaffected.

**2. Regression guard — `scripts/tests/test_hook_session_start.py`.** Added
`TestAmbientAutomationEnvHermeticity`, which re-runs the module in a subprocess
with `LL_AUTOMATION=1` deliberately set and asserts exit 0. Sentinel-guarded
(`LL_TEST_AMBIENT_AUTOMATION_GUARD`) against infinite recursion and pinned to
`-n 0` so it stays serial when it is itself running inside an xdist worker. This
follows the repo's "wrap a gate as a pytest test that shells out and asserts exit
0" policy and mirrors the existing `_guard_real_history_db` hermeticity fixture.

The guard was proved to bite: with the scrub temporarily removed it went red with
the 24 nested failures, then green once restored.

## Program Design

Test-infrastructure only; no production types, signatures, or call paths changed.

### Types

None added or modified.

### Signatures

- `scripts/tests/conftest.py` — `_CMD_RUN_ENV_VARS: tuple[str, ...]` gains two
  members (`"LL_AUTOMATION"`, `"LL_AUTOMATION_PROFILE"`). The consuming fixture
  signature is unchanged:
  `_restore_cmd_run_env_vars(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]`
- `scripts/tests/test_hook_session_start.py` — new
  `TestAmbientAutomationEnvHermeticity.test_suite_passes_with_ambient_ll_automation(self) -> None`
  and module constant `_AMBIENT_GUARD_SENTINEL: str`.

### Call Path

Scrub, per test:

```
pytest collects test
  → autouse _restore_cmd_run_env_vars (conftest.py:725)
      → monkeypatch.setenv(var, "") + monkeypatch.delenv(var)   # os.environ mutated
  → test body runs with LL_AUTOMATION absent
      → in-process:  session_start.handle() → gate at :110 False → normal payload
      → subprocess:  subprocess.run(...) inherits the scrubbed os.environ
  → monkeypatch teardown restores the original ambient value
```

Guard:

```
test_suite_passes_with_ambient_ll_automation
  → subprocess.run([sys.executable, "-m", "pytest", <this module>, "-n", "0"],
                   env={**os.environ, LL_AUTOMATION: "1", SENTINEL: "1"})
      → inner run: scrub still applies → all tests pass
      → inner run: guard itself skipif(SENTINEL) → no recursion
  → assert returncode == 0
```

Design choice: extend the existing autouse fixture rather than add a new
mechanism. It is the repo's canonical env-isolation pattern, is function-scoped
autouse, and mutates `os.environ` — so a single two-line change covers all three
failing test families (in-process handler, subprocess adapter, subprocess CLI).

## Acceptance Criteria

- [x] The seven-file repro passes with `LL_AUTOMATION=1` — 271 passed (was 48
      failed / 223 passed)
- [x] Full suite passes with a clean env — 18474 passed, 42 skipped
- [x] Full suite passes with `LL_AUTOMATION=1` — 18474 passed, 42 skipped
      (identical counts, confirming hermeticity)
- [x] Removing the scrub turns the new guard red (negative control verified)
- [x] The two intentional automation tests still assert the pruning behavior
- [x] `ruff check` and `ruff format --check` clean on both touched files

## Files Changed

- `scripts/tests/conftest.py` — extended `_CMD_RUN_ENV_VARS`, widened the
  rationale comment
- `scripts/tests/test_hook_session_start.py` — added
  `TestAmbientAutomationEnvHermeticity`

## Status

**done** — fixed and verified in commit `0add15cd` on `main`.

The suite is now hermetic with respect to `LL_AUTOMATION`: full-suite runs with
and without the var report identical counts (18474 passed, 42 skipped), and the
false-red verification gate inside automation runs is gone. The two production
concerns found during the investigation were split out rather than fixed here —
BUG-3080 (pruning before argument validation) and ENH-3081 (no scrub point for an
inherited `LL_AUTOMATION`) — both still open.

## Related Issues

- **ENH-2714** — introduced the automation-pruning gates this bug surfaced
- **BUG-3058** — added `automation_profile="ll-auto"` to ll-auto Phase 2, one of
  the two live setters
- **BUG-3080** — `ll-history-context` prunes before argument validation (a
  production defect found during this investigation, filed separately)
- **ENH-3081** — `host_runner` cannot clear an inherited `LL_AUTOMATION`; the
  underlying "no scrub point in the descendant tree" design gap

## Session Log
- `hook:posttooluse-status-done` - 2026-08-06T05:45:10 - `632189da-ce79-424d-9f6b-a0e7c9cf6398.jsonl`

- **2026-08-06** — Investigated the 48 failures reported across seven full-suite
  logs. Confirmed the current suite passed clean, so bisected on environment
  rather than code. Three parallel research agents traced `LL_AUTOMATION`
  setters/readers, the `history_context` gate, and existing conftest isolation
  conventions. Reproduced deterministically with `LL_AUTOMATION=1`, fixed via the
  conftest scrub, added and negative-control-verified the hermeticity guard, and
  confirmed identical full-suite counts with and without the var.
