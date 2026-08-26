---
id: FEAT-3329
type: FEAT
title: Add conftest guards that fail the suite on a live host-CLI spawn and on an unpatched rate-limit ladder
priority: P1
status: open
discovered_by: manual-review
discovered_date: '2026-08-26'
captured_at: '2026-08-26T00:00:00Z'
relates_to:
- BUG-3325
- BUG-3208
- BUG-2524
labels:
- tests
- test-infra
- conftest
- billing
- ci-wedge
---

# FEAT-3329: Add conftest guards that fail the suite on a live host-CLI spawn and on an unpatched rate-limit ladder

## Summary

Two structural gaps in `scripts/tests/conftest.py` let a test spend real money
and wedge a worker without anything failing. Both were split out of BUG-3325,
which found and fixed three concrete instances but deliberately left the guards
to this issue.

1. **No guard against a test spawning the real host CLI.** `conftest.py`
   sanitizes `LL_HOST_CLI` (`conftest.py:729`) but nothing fails a test that
   actually execs `claude`. BUG-3325 found three such tests, two of which had
   been **passing** — burning ~20s and real spend per iteration with no signal
   whatsoever.
2. **No guard against an unpatched rate-limit ladder.** The convention
   (`_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0]`, `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=0`)
   is documented only in a class docstring (`test_fsm_executor.py:7076-7079`) and
   enforced by per-test discipline. Miss it and the test sleeps on the real 300s
   ladder, which the 120s thread-method watchdog cannot kill — the BUG-3208 wedge.

Item (1) is the high-value one. It is not hypothetical: it is exactly the defect
BUG-3325 documents, and the two silent instances went undetected indefinitely
because a passing test emits no signal.

## Current Behavior

- A test that spawns the real `claude` binary runs to completion, bills the
  account, and **passes** if its assertions happen not to depend on the verdict.
  Nothing in `conftest.py` observes the spawn. Measured on `main` (2026-08-26):
  `test_pre_action_sleep_when_circuit_active` 56.21s and
  `test_pre_action_no_sleep_when_circuit_stale` 59.88s, both green.
- A rate-limit test that omits the ladder patch sleeps on the real
  `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER[0]` = 300s. The
  `--timeout=120 --timeout-method=thread` watchdog dumps a traceback but cannot
  kill the main thread, so a serial run hangs indefinitely and an xdist worker is
  consumed (BUG-3208 / BUG-3325).
- `conftest.py:729` sanitizes `LL_HOST_CLI`, which controls *which* host is
  selected but does nothing about a test that actually execs one.

## Expected Behavior

- Any test that spawns a real host CLI fails the session with a message naming
  the offending test and the binary — including when the executor swallows the
  guard's exception into an `error` verdict.
- Any rate-limit test runs with a collapsed ladder by default, so omitting the
  patch cannot block; the one intentional non-zero ladder
  (`test_fsm_executor.py:7808-7813`) still observes its real `[0.3]` sleep.
- Both hold under default addopts and under a serial `-n 0` run.

## Use Case

A contributor adds an FSM test using a slash-command action, or copies an
existing prompt-mode test, and does not realize `_action_mode` routes it to
`evaluate_llm_structured` → the real CLI. Today the test passes, the suite gets
slower, and the account is billed on every serial run, indefinitely — this went
undetected across three tests until a manual review of BUG-3325. With the guard,
the contributor gets an immediate, self-explanatory failure naming their test.

Second case: a maintainer writes a rate-limit test and follows the class docstring
convention from memory, missing `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER`. Today
that wedges a worker and surfaces as an unattributable CI hang; with the guard it
simply runs fast.

## Motivation

BUG-3325 is the existence proof. Its post-mortem surfaced three properties that
make this class of defect undetectable by ordinary means, and which this issue's
design must account for:

- **A passing test can be billing.** Two of the three offenders asserted only on
  a `sleeps` list and routed every verdict to a terminal state, so they passed
  identically whether the evaluator was live or stubbed. Wall-clock was the only
  visible symptom, and only under `--durations`.
- **A raise-only guard is insufficient.** `FSMExecutor._evaluate` swallows an
  evaluator exception into an `error` verdict rather than propagating it. A guard
  that merely raises is therefore invisible to any test whose FSM routes
  `on_error` to a terminal state. BUG-3325's original "scope evidence" probe was
  unsound for exactly this reason and had to be retracted. **The guard must
  record hits out-of-band and fail the session.**
- **Skipped tests hide it further.** The offending class is `no_parallel`, so it
  never runs under default addopts at all (`10 skipped in 1.26s`). A guard that
  only reports on tests that ran in the default configuration would have caught
  none of these.

## Proposed Solution

### Part 1 — `_no_live_host_cli` (host-CLI spawn guard)

**Guard at the process-spawn boundary, inspecting `argv[0]` — not by patching
the callable.** This is the key design decision and it supersedes BUG-3325's
sketch (see Program Design § Correction).

Wrap the two spawn sites *as bound in their own modules*:

- `little_loops.host_runner.subprocess.run` — the blocking path
  (`host_runner.py:2146`, reached via `run_blocking_json`)
- `little_loops.subprocess_utils.subprocess.Popen` — the streaming path
  (`subprocess_utils.py:526`, reached via `run_claude_command`)

The wrapper resolves `argv[0]`, compares its basename against the known host
binaries (`claude`, `codex`, `opencode`, `pi` — derive from the `HostRunner`
registry rather than hardcoding), and on a match records the hit in a
module-level collector keyed by `PYTEST_CURRENT_TEST` **and** raises. A
`pytest_sessionfinish` hook fails the session if the collector is non-empty,
naming each offending test. The raise stops the spend; the collector defeats the
`_evaluate` swallow.

**Why this shape needs no marker opt-out.** Tests that legitimately exercise
these functions already patch the spawn primitive itself, so they replace the
guard rather than trip it:

- `test_host_runner.py::TestRunBlockingJson` (`:1939-2030`) patches
  `little_loops.host_runner.subprocess.run` in every test — verified at
  `:1957`, `:1971`, `:1983`, `:1995`.
- The many callers of `run_claude_command` across `test_subprocess_utils.py`,
  `test_fsm_runners.py`, `test_worker_pool.py`, `test_issue_manager.py`, and
  others mock at the `Popen` layer.

This is a strict improvement over BUG-3325's assumption that an explicit marker
opt-out was *required*; verify the claim during implementation rather than
trusting it, and add the marker only if a genuine exception appears.

Also consider extending the guard to `dispatch_anthropic_request` /
`dispatch_batch_request` (`host_runner.py:2517`, `:2577`), which bill via the
SDK rather than a subprocess and are a separate spend surface. Scope this as a
stretch item — the subprocess paths are what BUG-3325 proved.

### Part 2 — `_rate_limit_ladder_patched` (ladder guard)

An autouse fixture scoped to the rate-limit test classes patching
`_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER` to `[0]` and
`_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS` to `0`, making the convention structural
rather than per-test discipline.

**Must exempt `test_fsm_executor.py:7808-7813`**, which patches a non-zero
ladder (`[0.3]`) on purpose to observe a real short sleep. Prefer an
opt-out marker over a name-based exemption so the exemption survives refactors.

Note the ordering constraint: an autouse fixture's patch must not clobber a
test's own narrower `patch.multiple(...)` context, which is the file's
established idiom (`:7172-7177`, `:7199-7203`, `:7220-7224`). Since those enter
*inside* the test body they take precedence naturally, but verify rather than
assume.

## Acceptance Criteria

- [ ] A deliberately-added probe test that reaches the real host CLI fails the
      suite with a message naming the offending test, **including** when its FSM
      routes `on_error` to a terminal state (the `_evaluate`-swallow case). Delete
      or `xfail`-guard the probe before merge; it exists to prove the guard.
- [ ] The guard fires for both spawn paths: `run_blocking_json` (blocking) and
      `run_claude_command` (streaming).
- [ ] `python -m pytest scripts/tests/test_host_runner.py` passes unchanged — no
      marker opt-out needed, or the opt-out is documented with the specific test
      that required it.
- [ ] Full suite `python -m pytest scripts/tests/` passes with both guards
      active, and a serial `-n 0` run of `test_fsm_executor.py` and
      `test_host_runner.py` also passes.
- [ ] Running the full suite serially (`-n 0`) reports **zero** live host-CLI
      spawns. This is the real regression check — it is the configuration in
      which BUG-3325's defects were reachable.
- [ ] A rate-limit test that omits the ladder patch cannot block: verified by a
      probe that would otherwise sleep on the 300s ladder.
- [ ] `test_fsm_executor.py:7808-7813` still observes its intentional non-zero
      (`[0.3]`) ladder — the guard does not clobber it.
- [ ] Any new marker is registered in `scripts/pyproject.toml` `[tool.pytest.ini_options] markers`
      (`:280-285`); the suite runs under `--strict-markers` (`:264`), so an
      unregistered marker is a hard error.

## Impact

- **Priority**: P1 — the gap it closes is a live, recurring billing leak with no
  detection signal. BUG-3325 fixes three known instances; nothing stops the
  fourth.
- **Effort**: Medium. Two conftest fixtures plus a `pytest_sessionfinish` hook,
  a marker registration, and probe tests. No production change.
- **Risk**: Medium-low. Both guards are suite-wide and can produce false
  positives on tests that legitimately spawn (integration/conformance tests are
  the likely candidates — check `-m integration` and `-m conformance` explicitly,
  since they are excluded from the CI unit run and easy to miss).
- **Breaking Change**: No — test-infra only.

## Integration Map

**Files to modify:**
- `scripts/tests/conftest.py` — both fixtures + `pytest_sessionfinish`. Existing
  autouse fixtures live at `:553-762`; `pytest_configure` at `:77` and
  `pytest_collection_modifyitems` at `:98` show the hook conventions in force.
- `scripts/pyproject.toml` — register any new marker at `:280-285`.

**Choke points to wrap:**
- `scripts/little_loops/host_runner.py:2146` — `subprocess.run` inside
  `run_blocking_json` (`:2103`)
- `scripts/little_loops/subprocess_utils.py:526` — `subprocess.Popen` inside
  `run_claude_command` (`:414`)
- *(stretch)* `scripts/little_loops/host_runner.py:2517`, `:2577` — SDK dispatch

**Related call sites (not choke points, useful for scoping):**
- `scripts/little_loops/fsm/evaluators.py:1090` — `evaluate_llm_structured` →
  `run_blocking_json`; note `evaluators.py:46` imports `run_blocking_json`
  directly, so it is bound as `little_loops.fsm.evaluators.run_blocking_json`
- `scripts/little_loops/runner_spec.py:212`, `scripts/little_loops/fsm/handoff_handler.py:116`,
  `scripts/little_loops/advisor.py:272`,
  `scripts/little_loops/cli/artifact/discover.py:429`, `.../extract.py:166`

**Conventions in force:**
- `_guard_real_history_db` (`conftest.py:617-657`) is the closest precedent — a
  session-scoped autouse fixture that monkeypatches one choke point and asserts
  when it resolves to production state. Follow its shape, **not** its "no opt-out"
  property (see below).
- The suite runs under `--strict-markers` and `--strict-config`
  (`pyproject.toml:264-265`); markers must be registered.
- Default addopts are `-n logical --dist loadfile` (`pyproject.toml:268-271`),
  so a session-scoped collector lives per-worker — `pytest_sessionfinish` must
  work correctly on workers, not just the controller.

## Program Design

### Signatures

- `_no_live_host_cli()` — session-scoped autouse fixture in `conftest.py`.
  Monkeypatches `little_loops.host_runner.subprocess.run` and
  `little_loops.subprocess_utils.subprocess.Popen` with wrappers that inspect
  `argv[0]`, append `(test_id, binary)` to a module-level collector on a host-CLI
  match, then raise.
- `pytest_sessionfinish(session, exitstatus)` — fails the session when the
  collector is non-empty, listing each `(test_id, binary)`.
- `_rate_limit_ladder_patched()` — autouse fixture scoped to the rate-limit test
  classes, patching the two ladder constants, with a marker-based exemption.

### Call Path

The blocking path the guard must intercept:
`FSMExecutor._execute_state` (`executor.py:1872`) → `FSMExecutor._evaluate`
(`executor.py:2571-2621`) → `evaluate_llm_structured` (`fsm/evaluators.py:1090`)
→ `run_blocking_json` (`host_runner.py:2103`) → `subprocess.run`
(`host_runner.py:2146`). The guard wraps the final hop.

The streaming path:
`run_claude_command` (`subprocess_utils.py:414`) → `HostRunner.build_streaming`
(via `resolve_host()`, `host_runner.py:1960`) → `subprocess.Popen`
(`subprocess_utils.py:526`). The guard wraps the final hop here too.

The swallow that defeats a raise-only guard:
`FSMExecutor._evaluate` (`executor.py:2571-2621`) catches the evaluator's
exception and returns an `error` verdict, which `_execute_state` routes via
`on_error` — so the raise never reaches pytest. Hence the module-level collector
plus `pytest_sessionfinish`.

The ladder path the second guard must collapse:
`FSMExecutor._handle_rate_limit` short tier (`executor.py:3396-3402`) → long tier
(`executor.py:3406-3427`) → `FSMExecutor._interruptible_sleep`
(`executor.py:3545-3554`) → `time.sleep` (`executor.py:3549`).

### Correction to BUG-3325's sketch

BUG-3325 § Program Design proposed patching **`little_loops.host_runner.run_blocking_json`**
(the function) to raise, and stated that this "**requires** an explicit marker
opt-out for `test_host_runner.py::TestRunBlockingJson`."

Both halves are superseded:

- **Patch the spawn primitive, not the function.** Patching `run_blocking_json`
  itself covers only the blocking path and misses `run_claude_command` entirely.
  Wrapping `subprocess.run` / `subprocess.Popen` as bound in each module covers
  both, and inspecting `argv[0]` makes the guard precise about *what* is being
  spawned rather than *which helper* was called.
- **No marker opt-out is expected to be needed.** `TestRunBlockingJson` patches
  `little_loops.host_runner.subprocess.run` in each of its tests (verified at
  `:1957`, `:1971`, `:1983`, `:1995`), so it shadows the guard rather than
  tripping it. Confirm this empirically; add a marker only if something genuinely
  needs one.

BUG-3325's other constraint still stands and must be honored: **do not implement
this by patching `little_loops.fsm.executor.evaluate_llm_structured`.** Verified
in that issue — an autouse patch of that name breaks
`TestEvaluators::test_llm_structured_evaluator_routes_on_verdict`, which drives
the real evaluator with `subprocess.run` mocked (fails at
`test_fsm_executor.py:2827`, `assert 'check' == 'done'`).

### Testing Strategy

- Prove the guard with a probe that reaches the CLI through an FSM routing
  `on_error` to a terminal state — the shape that defeats a raise-only guard.
- Exercise both spawn paths, not just the blocking one.
- Run the full suite **serially** (`-n 0`) as well as under default addopts. The
  serial run is the one where BUG-3325's defects were reachable, and it is the
  meaningful regression check.
- Check `-m integration` and `-m conformance` separately for false positives;
  they are excluded from the CI unit run and are the likeliest legitimate
  spawners.

## Related Key Documentation

- `.claude/CLAUDE.md` — `## Testing & CI Policy` names `python -m pytest scripts/tests/` as the authoritative gate this issue's guards must keep passing.
- `CONTRIBUTING.md` — `### Running Tests` documents the pytest invocation conventions (`-m integration`, `-m "not integration"`) this issue's AC explicitly checks for false positives.

## Status

**Open** | Created: 2026-08-26 | Priority: P1

## Notes

### Origin

Split out of BUG-3325 § "Follow-on hardening — SPLIT OUT, not in scope here",
which had deferred these two guards across several revisions without the issue
ever being filed. BUG-3325's own second review found two additional live-CLI
tests that had been passing silently, which is the concrete argument for
Part 1's value.

Sequencing: BUG-3325 should land first. It fixes the three known offenders, so
this issue's guards go in against an already-clean tree and any failure they
surface is a genuinely new finding.
