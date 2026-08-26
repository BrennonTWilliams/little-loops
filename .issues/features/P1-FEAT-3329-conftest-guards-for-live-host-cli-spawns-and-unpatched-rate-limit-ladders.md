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
learning_tests_required:
- pytest
- pytest-xdist
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

- Any test that spawns a real host CLI fails — attributed to the offending test
  and naming the binary — including when the executor swallows the guard's
  exception into an `error` verdict, and including under the default xdist
  addopts.
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

**The patch is process-global, not module-bound.** Both `host_runner.py:29` and
`subprocess_utils.py:15` do a plain `import subprocess`, so
`little_loops.host_runner.subprocess`, `little_loops.subprocess_utils.subprocess`
and the global `subprocess` are the *same module object*. Patching `.run` /
`.Popen` through any of those references patches the whole process. Implement it
as **one patch pair** — `subprocess.run` and `subprocess.Popen` — not as two
independent per-module patches; the "as bound in its own module" framing that
appeared in earlier revisions of this issue is mechanically wrong and would
mislead the implementer into thinking the blast radius is narrow.

Two consequences follow, and both must be designed for:

- **Coverage is free and wider than the two named paths.** The same patch pair
  also covers `fsm/handoff_handler.py:123` (`build_detached` → `Popen`, a
  **third** host-CLI spawn path and the priciest one — it launches a detached
  session), `parallel/worker_pool.py:835`, `init/install_check.py:160,171`,
  `cli/action.py:350`, and `cli/doctor.py:1183`. Good, but state it, because it
  changes the false-positive triage below.
- **The false-positive surface is the entire suite, not two call paths.** Of the
  sites above, four are `build_version_check()` → `claude --version`: free, but
  `argv[0]`'s basename is still `claude`, so a naive basename check trips on
  them. **Carve out version checks explicitly** (e.g. skip when the argument
  vector is exactly `["--version"]`) rather than relying on those tests
  happening to mock.

The wrapper resolves `argv[0]`, compares its basename against the known host
binaries, applies the version-check carve-out, and on a match records the hit in
a module-level collector **and** raises. The raise stops the spend; the collector
defeats the `_evaluate` swallow.

**Host binary basenames.** All eight are `binary="…"` literals in
`host_runner.py`: `claude`, `codex`, `gemini`, `kimi`, `omp`, `opencode`, `pi`,
`qwen`. Do **not** source them from `_PROBE_ORDER` (seven entries, missing
`opencode`) — `OpenCodeRunner.build_streaming` *does* build a real invocation
(only its `build_blocking_json` / `build_detached` raise `HostNotConfigured`), so
opencode genuinely can spawn and cannot be dropped. `build_version_check()` is a
pure literal constructor with no PATH probing for the wired hosts, so
instantiating `_HOST_RUNNER_REGISTRY` values and reading `.binary` (catching
`HostNotConfigured`) works for seven of eight but still misses opencode. The
clean fix is a `binary_name` class attribute on `HostRunner` and its eight
implementations — **note this makes the "no production change" claim in § Impact
false**; decide it deliberately rather than discovering it mid-implementation.

### Failing the run: teardown fixture, NOT `pytest_sessionfinish`

`pytest_sessionfinish` **cannot reliably fail the run under the default
addopts** and must not be the enforcement mechanism. pytest-xdist workers do not
propagate a worker-mutated `session.exitstatus` to the controller; the controller
derives exit status from collected test reports. Under `-n logical` a worker-side
session-fail is at best an internal error and at worst silently nothing — exactly
the "guard exists but emits no signal" failure this issue was filed to prevent.
The absence of any session-fail precedent in this repo (see Codebase Research) is
a smell, not merely a gap.

**Use a function-scoped autouse fixture that inspects the collector after
`yield` and calls `pytest.fail()` in that test's teardown.** It:

- works identically serially and under xdist, because it produces an ordinary
  test-failure report rather than mutating session state;
- attributes to the exact offending test with no `PYTEST_CURRENT_TEST` keying
  and no collector-key bookkeeping;
- still defeats the `_evaluate` swallow — the raise is eaten inside the test
  body, but the collector entry survives to teardown;
- removes the `pytest_sessionfinish` hook, the new-pattern session-fail, and the
  `test_conftest_cap.py` hook-unit-test wiring item entirely.

Keep a `pytest_sessionfinish` hook only if a **print-only** end-of-run summary is
wanted; it must not be load-bearing for the failure.

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

A **module-scoped autouse fixture living in `test_fsm_executor.py` — not
`conftest.py`** — patching `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER` to `[0]` and
`_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS` to `0` for the whole file, making the
convention structural rather than per-test discipline.

**Do not enumerate the rate-limit classes.** No test asserts the *default* values
of either constant — the only references are the six intentional patch sites
(`:7175-7176`, `:7202-7203`, `:7223-7224`, `:7996-7997`) plus the deliberate
`[0.3]` at `:7811-7812`. Collapsing both constants file-wide is therefore safe,
and it removes the "resolve against all five rate-limit classes" enumeration
(`TestRateLimitRetries`, `TestRateLimitStorm`, `TestRateLimitTwoTier`,
`TestRateLimitHeartbeat`, `TestRateLimitCircuitIntegration`) along with the
maintenance risk of a sixth class nobody remembers to add. It also sidesteps the
"no class-scoped autouse fixture precedent" problem noted in Codebase Research.

**Must exempt `test_fsm_executor.py:7808-7813`**, which patches a non-zero
ladder (`[0.3]`) on purpose to observe a real short sleep. Gate the exemption on
a registered marker rather than a name-based check so it survives refactors.

Note the ordering constraint: an autouse fixture's patch must not clobber a
test's own narrower `patch.multiple(...)` context, which is the file's
established idiom (`:7172-7177`, `:7199-7203`, `:7220-7224`). Since those enter
*inside* the test body they take precedence naturally, but verify rather than
assume.

## Acceptance Criteria

- [ ] **Permanent** unit tests prove the guard, rather than a probe that is
      deleted before merge (which would leave zero durable regression coverage):
      - call the wrapper directly with a fake `argv` whose `argv[0]` is a host
        binary, and assert it **both** records into the collector **and** raises;
      - pre-seed the collector and assert the teardown fixture fails the test.
        This is the `_evaluate`-swallow property expressed durably — a recorded
        hit still fails even when the raise was eaten inside the test body.
- [ ] The wrapper does **not** fire on `build_version_check()` invocations
      (`argv == [<host binary>, "--version"]`), covered by a unit test.
- [ ] The guard fires for all three spawn paths: `run_blocking_json` (blocking),
      `run_claude_command` (streaming), and `build_detached` →
      `handoff_handler.py:123` (detached).
- [ ] The guard fails the run **under the default `-n logical` addopts**, not
      only serially. This is the specific mechanism check: a `pytest_sessionfinish`
      exit-status mutation on an xdist worker does not reach the controller.
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
- **Effort**: Medium. A session-scoped installer fixture plus a function-scoped
  teardown-fail fixture in `conftest.py`, a module-scoped ladder fixture in
  `test_fsm_executor.py`, a marker registration, and unit tests.
  **One small production change** is expected: a `binary_name` class attribute on
  `HostRunner` and its eight implementations, so the guard's basename list has a
  single derivable source (see Proposed Solution § Host binary basenames). Prior
  revisions of this issue claimed "no production change"; that is false unless
  the basename list is hand-maintained in `conftest.py`, which is the worse
  trade.
- **Risk**: Medium-low, but larger than earlier revisions assumed. Because both
  modules `import subprocess` (so the patch is process-global), the false-positive
  surface is **the entire suite**, not the two named call paths — every
  `subprocess.run`/`Popen` call in every test is inspected. Integration and
  conformance tests are the likeliest legitimate spawners; check
  `-m integration` and `-m conformance` explicitly, since they are excluded from
  the CI unit run and easy to miss.
- **Breaking Change**: No. The `binary_name` attribute is additive.

## Integration Map

**Files to modify:**
- `scripts/tests/conftest.py` — the session-scoped guard installer + the
  function-scoped teardown-fail fixture. Existing autouse fixtures live at
  `:553-762`; `pytest_configure` at `:77` and `pytest_collection_modifyitems` at
  `:98` show the hook conventions in force.
- `scripts/tests/test_fsm_executor.py` — the module-scoped ladder fixture and the
  exemption marker on the `[0.3]` heartbeat test (`:7808-7813`).
- `scripts/pyproject.toml` — register any new marker at `:280-285`.
- `scripts/little_loops/host_runner.py` — additive `binary_name` class attribute
  on `HostRunner` and its eight implementations (see § Impact).

**Choke point to wrap — ONE global patch pair, not per-module:**

Because both call sites `import subprocess` as a module, there is a single
attribute pair to patch — `subprocess.run` and `subprocess.Popen` — reachable
through any module reference. The sites below are what that pair *covers*, not
separate things to wrap:

- `scripts/little_loops/host_runner.py:2146` — `subprocess.run` inside
  `run_blocking_json` (`:2103`) — blocking path
- `scripts/little_loops/subprocess_utils.py:526` — `subprocess.Popen` inside
  `run_claude_command` (`:414`) — streaming path
- `scripts/little_loops/fsm/handoff_handler.py:123` — `subprocess.Popen` for
  `build_detached` — **detached path; the third host-CLI spawn path, absent from
  earlier revisions of this issue and the most expensive of the three**
- `scripts/little_loops/parallel/worker_pool.py:835` — `build_blocking_json`
  health probe
- `scripts/little_loops/init/install_check.py:160,171`,
  `scripts/little_loops/cli/action.py:350`,
  `scripts/little_loops/cli/doctor.py:1183` — `build_version_check()` →
  `<binary> --version`. **Free, but `argv[0]` is still a host binary — these are
  the version-check carve-out's reason for existing.**
- *(stretch)* `scripts/little_loops/host_runner.py:2517`, `:2577` — SDK dispatch
  (not a subprocess; needs its own wrapper if in scope)

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:3179-3231` `FSMExecutor::_run_baseline_arm` —
  a **second production call path** into the streaming spawn boundary, calling
  `run_claude_command` directly (comment at `:3205` explicitly notes "the baseline
  arm calls `run_claude_command()` directly"), separate from the evaluator path
  already documented in Program Design § Call Path. Legitimate real-CLI spawn in
  production; relevant to scoping false positives, not a file the guard itself
  needs to touch. [Agent 1 finding]
- `scripts/little_loops/host_runner.py:1811-1820` `_HOST_RUNNER_REGISTRY` has
  **eight** entries (`claude-code`, `codex`, `opencode`, `pi`, `gemini`, `omp`,
  `kimi-code`, `qwen`), not the four (`claude`, `codex`, `opencode`, `pi`) the
  Proposed Solution's prose names — and its keys are host *names*, not CLI
  *binary basenames*. The binary-basename list the guard's `argv[0]` check
  actually needs lives in `_PROBE_ORDER` (`host_runner.py:1827-1835`), which has
  only **seven** entries and is **missing `opencode`**'s binary basename
  entirely. "Derive from the `HostRunner` registry" therefore isn't a single
  literal lookup — `opencode`'s binary name has no registry-derivable source and
  must be sourced from `OpenCodeRunner` itself or filled in by hand. [Agent 2
  finding]
- `scripts/tests/test_conftest_cap.py:28-32` loads `conftest.py` as a **second,
  independent module** via `importlib.util.spec_from_file_location` /
  `exec_module`, separate from the plugin-loaded `conftest` pytest itself uses.
  Any module-level collector state the new `_no_live_host_cli` guard introduces
  will exist as two unrelated instances — one in the real plugin, one in this
  file's `conftest_under_test` object. This file's `TestXdistAutoNumWorkers` /
  `TestPytestConfigureNice` / `TestNoParallelMarkerRouting` classes are also the
  de facto regression suite for `conftest.py` hook-level behavior, and the
  natural home for a new `pytest_sessionfinish` unit test (see Tests below).
  [Agent 2 finding]
- `scripts/tests/test_host_runner.py:1958-2027` `TestRunBlockingJson` (6 test
  methods) — confirmed via code-graph query and direct read: each opens its own
  `with patch("little_loops.host_runner.subprocess.run") as mock_run:` context
  manager, individually. `unittest.mock.patch` used this way captures whatever is
  bound to the attribute at `__enter__` (the session-scoped guard, once installed)
  and restores exactly that captured value at `__exit__` — a strict
  replace/restore, not a chain. Confirms the issue's "shadows the guard rather
  than tripping it" claim empirically. [Agent 1 + 3 finding]
- `scripts/tests/test_subprocess_utils.py` and `test_subprocess_mocks.py` patch
  the **bare** `"subprocess.Popen"` module attribute (not the
  `little_loops.subprocess_utils.subprocess.Popen`-qualified form) — since
  `subprocess_utils.py` does `import subprocess` then calls `subprocess.Popen`,
  patching the bare attribute mutates the same object the guard's monkeypatch
  target resolves to, so this **also shadows** the guard rather than bypassing
  it. `test_action.py` and `test_workflow_sequence_analyzer.py` instead patch
  `little_loops.subprocess_utils.run_claude_command` one level above the
  `Popen` call — that call path never reaches `subprocess.Popen` at all, so the
  guard is bypassed by construction for these (never called), not shadowed the
  way the two `Popen`-patching files are. [Agent 1 finding, refining the issue's
  Codebase Research Findings distinction]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md:1049` — markers reference table documents
  `no_parallel` verbatim with its exact `pytest_collection_modifyitems`
  interaction; if this issue registers a new marker (ladder exemption or a
  live-CLI opt-out, if one proves genuinely needed), a row belongs here in the
  same format. Not currently listed in "Related Key Documentation." [Agent 2
  finding]
- `docs/development/TROUBLESHOOTING.md:822-828` — documents the `no_parallel`
  marker / skip-on-workers mechanism in a flaky-test troubleshooting entry,
  citing the same `conftest.py` mechanism a ladder-exemption marker would need
  to follow. Not currently listed in "Related Key Documentation." [Agent 2
  finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_conftest_cap.py` — add a `TestPytestSessionFinish`-style
  class here (new test), following this file's existing convention of calling
  conftest hooks directly against the standalone-loaded module object
  (`conftest.pytest_collection_modifyitems(...)`, `conftest.pytest_configure(...)`).
  This is the established location for unit coverage of `conftest.py` hook
  *logic*; no other file plays this role. [Agent 2 + 3 finding]
- `scripts/tests/test_pytest_history_plugin.py` — pattern to follow for testing
  the new `pytest_sessionfinish` hook itself: call it directly with a hand-built
  `SimpleNamespace`/`MagicMock` stand-in for `session`, pre-seed the module-level
  collector, assert it fails as expected. Confirmed **no `pytest.pytester`/
  `testdir` usage exists anywhere in this codebase** (zero grep hits) — do not
  reach for a nested-pytest-subprocess test; this stand-in-object convention is
  the only precedent. [Agent 3 finding]
- `scripts/tests/conformance/test_host_conformance.py::test_golden_path_invocation`
  — confirmed **not** a false-positive risk: only calls `resolve_host()` /
  `build_streaming()`, which construct a `HostInvocation` but never call
  `subprocess.run`/`Popen`. The only `-m conformance` file in the suite. [Agent
  1 + 3 finding]
- `scripts/tests/test_cli_e2e.py` (`pytestmark = pytest.mark.integration`) and
  `scripts/tests/test_fsm_signal_integration.py` — confirmed clean: both spawn
  real subprocesses (`git`, `sys.executable -m little_loops.cli.loop`) with a
  non-host `argv[0]`, so an argv[0]-basename check does not trip on them. Note
  `test_fsm_signal_integration.py`'s spawn is a **separate child process** — a
  parent-process guard fixture cannot observe subprocess calls the child makes
  internally in its own process; only relevant if the guard were expected to
  cover the child's execution too (it is not, per the issue's design). [Agent 3
  finding]
- `scripts/tests/test_hooks_integration.py` — mixes explicit
  `patch("subprocess.Popen")`/`patch("subprocess.run")` context managers
  (`:248-249`, `:321-322`, `:367-368`) with unpatched direct `subprocess.run(...)`
  calls elsewhere in the same file (`:34`, `:46`, `:65`, `:71`, `:156`, `:478`).
  Needs per-test triage against the guard's exact binding before merge — flagged
  as the highest-risk false-positive candidate found. [Agent 1 + 3 finding]
- 20 additional `-m integration`/`-m conformance` files were located but not
  individually inspected for `subprocess.run`/`subprocess.Popen` calls this pass
  (full list: `test_worker_pool.py`, `test_design_tokens.py`,
  `test_orchestrator.py`, `test_sprint_integration.py`,
  `integration/test_loop_run_e2e.py`, `test_wheel_smoke.py`,
  `integration/test_init_e2e.py`, `test_git_operations.py`, `test_rn_build.py`,
  `test_merge_coordinator.py`, `test_worktree_concurrency.py`,
  `test_init_skill_fixtures.py`, `test_decisions_fragments.py`,
  `test_cli_e2e.py` and `test_fsm_signal_integration.py` already covered above,
  `integration/test_issue_lifecycle_e2e.py`, `test_issue_workflow_integration.py`,
  `test_goals_parser.py`, `test_git_lock.py`) — run `-m integration` and
  `-m conformance` explicitly once the guard lands, per the issue's own Testing
  Strategy, to classify the remainder. [Agent 3 finding; not exhaustively
  verified — flagging per skill's no-silent-cap rule]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

- ~~Resolve host binary basenames from `_PROBE_ORDER`~~ — **superseded.**
  `_PROBE_ORDER` (`host_runner.py:1827-1835`) has seven entries and is missing
  `opencode`, and `OpenCodeRunner.build_streaming` *does* build a real invocation
  (only its `build_blocking_json`/`build_detached` raise `HostNotConfigured`), so
  opencode can spawn and cannot be dropped. All eight basenames — `claude`,
  `codex`, `gemini`, `kimi`, `omp`, `opencode`, `pi`, `qwen` — exist as
  `binary="…"` literals. Add an additive `binary_name` class attribute to
  `HostRunner` and its eight implementations and derive from that.
- ~~Add a `TestPytestSessionFinish`-style unit test to `test_conftest_cap.py`~~ —
  **dropped.** The enforcement mechanism is a function-scoped teardown fixture,
  not a `pytest_sessionfinish` hook, so there is no hook logic to unit-test
  there. (This also moots the `test_conftest_cap.py` double-module-load concern
  below: no session-level collector state needs to be shared with the
  standalone-loaded `conftest_under_test` object.) If a print-only summary hook
  is added anyway, it is not load-bearing and does not need this coverage.
- Add the `--version` carve-out and confirm it with a unit test — four
  production sites (`install_check.py:160,171`, `cli/action.py:350`,
  `cli/doctor.py:1183`) spawn `<host binary> --version`, which is free but trips
  a naive `argv[0]` basename check.
- Cover the detached path (`handoff_handler.py:123`) in the guard's scope and
  acceptance criteria — it is a third host-CLI spawn path and the priciest.
- Triage `test_hooks_integration.py`'s mixed patched/unpatched `subprocess.run`
  calls against the guard's exact monkeypatch target before merge.
- Run `-m integration` and `-m conformance` explicitly (per the issue's own
  Testing Strategy) to classify the 18 unreviewed integration/conformance files
  listed above.
- Add marker rows to `docs/development/TESTING.md:1049` and
  `docs/development/TROUBLESHOOTING.md:822-828` if a new marker is registered.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- **`_guard_real_history_db`'s exact fail-shape, for the guard's own design**: session-scoped generator fixture using a raw `pytest.MonkeyPatch()` instance (not the function-scoped `monkeypatch` fixture, since `monkeypatch` isn't available at session scope), with a bare `assert` inside the patched wrapper function and `mp.undo()` in a `finally` after `yield`. It fails synchronously inside whichever test's call stack triggers the violation — no separate collector, no `pytest.fail()`, no session-teardown reporting. It attributes to the true offending test specifically *because* the assertion runs in that test's own stack frame, which the fixture's own docstring contrasts with a prior mtime/size approach that could only blame "the last test in the session."
- **No existing violation-collector-then-report-at-teardown pattern exists anywhere in `scripts/tests/` or `scripts/little_loops/`.** `_guard_real_history_db` fails at the choke point, not via deferred collection. This issue's `pytest_sessionfinish`-based collector (needed specifically to defeat `_evaluate`'s exception-swallow) is a new pattern for this codebase, not an extension of an existing one.
- **Marker registration/consumption round-trip, modeled on `no_parallel`**: registered as one string in `pyproject.toml:284` (`"no_parallel: marks tests that must not run on xdist workers ..."`), consumed via `"no_parallel" in item.keywords` inside `pytest_collection_modifyitems` (`conftest.py:98-124`), and applied via `@pytest.mark.no_parallel` on test methods (e.g. `test_worktree_utils.py:1228`). Any new marker this issue adds (ladder exemption, live-CLI opt-out if one proves necessary) should follow this same three-part shape.
- **Module-bound `subprocess` patch convention only has direct precedent on the `host_runner` side.** `TestRunBlockingJson` patches `little_loops.host_runner.subprocess.run` directly (6 sites, `test_host_runner.py:1958-2027`). No existing test patches `little_loops.subprocess_utils.subprocess.Popen` at that same bound-attribute layer — tests exercising `run_claude_command` instead patch one level higher: the function itself (`patch("little_loops.subprocess_utils.run_claude_command", ...)` in `test_action.py:232,392,499,536,579,596`, `test_workflow_sequence_analyzer.py:2304`) or `resolve_host` (`test_subprocess_utils.py:81,1458,2385,2428,2468,2511`, `test_subprocess_mocks.py:30`). Consequence for this issue: since these tests replace `run_claude_command`/`resolve_host` entirely, execution never reaches the `subprocess.Popen` call the guard wraps — the guard is bypassed by construction for these tests (they never call the real function), not by a stacked patch shadowing it the way `TestRunBlockingJson` shadows the `host_runner` guard. Both are "no false positive," but for different mechanical reasons — worth distinguishing during implementation/verification rather than assuming the same shadowing argument applies to both spawn paths.
- **No existing "test-infra self-check" probe-then-delete/xfail pattern in this codebase.** A search across `scripts/tests/` found no prior instance of a test deliberately added to prove a guard fires and then removed/`xfail`-guarded before merge; the AC's "delete or `xfail`-guard the probe before merge" instruction establishes a new convention rather than following an existing one.

## Program Design

### Signatures

- `_install_no_live_host_cli()` — session-scoped autouse fixture in
  `conftest.py`. Monkeypatches the **global** `subprocess.run` and
  `subprocess.Popen` (one pair; see Proposed Solution) with wrappers that inspect
  `argv[0]`'s basename against the eight host binary names, apply the
  `--version` carve-out, append `(test_id, binary)` to a module-level collector
  on a match, then raise.
- `_fail_on_live_host_cli()` — **function-scoped** autouse fixture in
  `conftest.py`. Yields, then `pytest.fail()`s in teardown if the collector
  gained entries during this test. This is the enforcement mechanism; it works
  under xdist where a `pytest_sessionfinish` exit-status mutation does not.
- `pytest_sessionfinish(session, exitstatus)` — **optional, print-only**
  end-of-run summary listing each `(test_id, binary)`. Must not be load-bearing.
- `_collapse_rate_limit_ladder()` — module-scoped autouse fixture in
  `test_fsm_executor.py` patching the two ladder constants file-wide, with a
  marker-based exemption for the intentional `[0.3]` heartbeat test.
- `HostRunner.binary_name: str` — additive class attribute on the Protocol and
  its eight implementations, giving the guard a single derivable source for the
  basename list.

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

The detached path (**absent from earlier revisions of this issue**):
`FSMExecutor` handoff → `handoff_handler.py:116` `resolve_host().build_detached()`
→ `subprocess.Popen` (`handoff_handler.py:123`). Covered for free by the global
patch pair, but it is the most expensive spawn of the three — it launches a
whole detached host session — so it belongs in the guard's stated scope and in
the acceptance criteria.

The swallow that defeats a raise-only guard:
`FSMExecutor._evaluate` (`executor.py:2571-2621`) catches the evaluator's
exception and returns an `error` verdict, which `_execute_state` routes via
`on_error` — so the raise never reaches pytest. Hence the module-level collector,
drained and asserted in the **function-scoped teardown fixture** (not
`pytest_sessionfinish` — see Proposed Solution § Failing the run).

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
  itself covers only the blocking path and misses `run_claude_command` and
  `build_detached` entirely. Wrapping the global `subprocess.run` /
  `subprocess.Popen` pair covers all three, and inspecting `argv[0]` makes the
  guard precise about *what* is being spawned rather than *which helper* was
  called.
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

- Prove the guard with **permanent** unit tests, not a probe that is deleted
  before merge. Call the wrapper directly with a synthetic `argv` and assert it
  records *and* raises; separately pre-seed the collector and assert the teardown
  fixture fails. The second test is the `_evaluate`-swallow property in durable
  form — a recorded hit fails even when the raise was eaten — and needs no live
  FSM run.
- Exercise all three spawn paths (blocking, streaming, detached), not just the
  blocking one, and assert the `--version` carve-out.
- Verify the failure actually surfaces **under the default `-n logical`
  addopts**, not only under `-n 0`. This is the mechanism check that rules out
  the `pytest_sessionfinish` dead end.
- Run the full suite **serially** (`-n 0`) as well as under default addopts. The
  serial run is the one where BUG-3325's defects were reachable, and it is the
  meaningful regression check.
- Check `-m integration` and `-m conformance` separately for false positives;
  they are excluded from the CI unit run and are the likeliest legitimate
  spawners.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- **No `pytest_sessionfinish` (or `pytest_sessionstart`) hook currently exists in `scripts/tests/conftest.py`** (grep confirms zero matches). The only `pytest_sessionfinish` in the codebase is `LLHistoryPlugin.pytest_sessionfinish` (`scripts/little_loops/pytest_history_plugin.py:118-121`), which is best-effort (`contextlib.suppress(Exception)`) and never fails the session. The new hook this issue proposes has no existing session-fail precedent to extend or collide with — it is a new pattern for this codebase.
- **xdist per-process hook semantics, confirmed from the existing `pytest_configure` docstring** (`conftest.py:78-84`): under `-n logical --dist loadfile` (`pyproject.toml:268-271`), each xdist worker is a separate process that independently re-runs session-scoped pytest hooks. `pytest_sessionfinish` will therefore fire once per worker process, each seeing only the collector state accumulated by tests that ran on that worker — never a single global view. The controller process runs no test bodies itself (per the existing `pytest_collection_modifyitems` docstring, `conftest.py:106-111`), so a controller-side `pytest_sessionfinish` invocation will see an empty collector by construction. **Follow-up from the 2026-08-26 design review**: the consequence is stronger than "must work correctly on workers." A worker-side `pytest_sessionfinish` cannot fail the run at all — xdist does not propagate a worker's `session.exitstatus` to the controller, which derives exit status from collected test reports. This is why the design now enforces via a function-scoped teardown fixture instead; see Proposed Solution § Failing the run.
- **`TestRunBlockingJson` patch-stacking confirmed empirically** (`test_host_runner.py:1939-2030`): each test method opens its own `with patch("little_loops.host_runner.subprocess.run") as mock_run:` (context-manager form, not a class-level/autouse patch), individually at lines 1958, 1973, 1988, 2001, 2016, 2027. `unittest.mock.patch` used this way captures whatever is bound to the attribute at `__enter__` (i.e., a session-scoped guard installed earlier) and restores exactly that captured value at `__exit__` — so during the test body the guard is fully shadowed by `mock_run`, and afterward the guard is restored underneath (not lost). This is a strict replace/restore, not a chain — confirms the issue's "shadows the guard rather than tripping it" claim empirically rather than by inspection alone.
- **Full list of rate-limit test classes in `test_fsm_executor.py`** (for scoping the ladder-guard fixture): `TestRateLimitRetries` (`:7072`), `TestRateLimitStorm` (`:7442`), `TestRateLimitTwoTier` (`:7573`), `TestRateLimitHeartbeat` (`:7756`, contains the intentional `[0.3]` ladder at `:7806-7813`), `TestRateLimitCircuitIntegration` (`:7842`). The issue's current text names only `TestRateLimitRetries`'s docstring and the `TestRateLimitHeartbeat` exemption; a fixture scoped to "rate-limit test classes" needs to resolve against all five.
- **No class-scoped autouse fixture precedent exists in this codebase.** All four existing autouse fixtures in `conftest.py` (`_isolate_history_db`, `_guard_real_history_db`, `_isolate_session_log_dir`, `_restore_cmd_run_env_vars`, `_reset_deprecated_key_warnings`) apply suite-wide; none uses `request.cls`/`request.node.cls` or a marker check to scope to specific test classes. The only class/marker-scoping precedent anywhere is the `no_parallel` marker's `item.keywords` check inside `pytest_collection_modifyitems` (collection-time item filtering, not a fixture). Scoping the ladder-guard fixture "to the rate-limit test classes" per the Proposed Solution therefore has no existing pattern to follow — the mechanism (autouse class-fixture vs. marker-gated fixture vs. `request.node.cls` check) is an open implementation choice, not a convention to match.

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

Sequencing: BUG-3325 should land first, so this issue's guards go in against an
already-clean tree and any failure they surface is a genuinely new finding.
**Satisfied** — BUG-3325 landed 2026-08-26 (`94c702afc`, "fix(tests): stop
TestRateLimitCircuitIntegration from hitting the live host CLI"), fixing all
three known offenders. This issue is unblocked.

### Design revision — 2026-08-26 (pre-implementation review)

Four changes to the design as originally refined, all verified against the code:

1. **`pytest_sessionfinish` replaced by a function-scoped teardown fixture.**
   xdist workers do not propagate a worker-mutated `session.exitstatus` to the
   controller, so the original mechanism could silently no-op under the default
   `-n logical` addopts — the exact failure this issue exists to prevent.
2. **The monkeypatch is process-global, not module-bound.** Both call sites
   `import subprocess`, so there is one attribute pair to patch. This widens
   coverage for free (picking up the detached path and the version checks) and
   widens the false-positive surface to the whole suite.
3. **The `--version` carve-out and the detached spawn path** were both missing
   from the original scope.
4. **The delete-before-merge probe replaced by permanent unit tests**, and the
   ladder fixture simplified from a five-class enumeration to one module-scoped
   fixture in `test_fsm_executor.py`.


## Session Log
- `/ll:wire-issue` - 2026-08-26T20:23:34 - `c52dee45-306e-4834-bf4d-c82265f05dc7.jsonl`
- `/ll:refine-issue` - 2026-08-26T20:16:59 - `c8fbfaf4-7e26-4a99-9fe9-48c752eecfe4.jsonl`
