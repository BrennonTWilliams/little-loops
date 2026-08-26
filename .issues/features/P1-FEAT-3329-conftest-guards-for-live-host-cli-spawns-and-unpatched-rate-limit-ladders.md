---
id: FEAT-3329
type: FEAT
title: Add conftest guards that fail the suite on a live host-CLI spawn and on an
  unpatched rate-limit ladder
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
confidence_score: 100
outcome_confidence: 83
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 20
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
- **Wall-clock was the only symptom, in the *default* configuration.** The
  offending class `TestRateLimitCircuitIntegration`
  (`test_fsm_executor.py:7842`) runs under the default `-n logical` addopts and
  passed there — so this was not hidden behind a skip; it was hidden behind
  green. (**Corrected 2026-08-26**: earlier revisions claimed the class was
  `no_parallel` and "never runs under default addopts at all
  (`10 skipped in 1.26s`)". Verified false by execution — the class carries no
  marker, and `python -m pytest
  scripts/tests/test_fsm_executor.py::TestRateLimitCircuitIntegration` reports
  **`10 passed in 1.76s`**. The only `no_parallel` markers in the suite are
  `test_fsm_signal_integration.py:42` and `test_worktree_utils.py:1228`. The
  collector-plus-teardown design does not rest on this premise — it rests on the
  `_evaluate` swallow above — so nothing else in this issue changes.)

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
  happening to mock. **Canonical form of the carve-out, used everywhere in this
  issue: `list(argv[1:]) == ["--version"]` (coerce — argv may be a tuple).**

The wrapper resolves `argv[0]`, compares its basename against the known host
binaries, applies the version-check carve-out, and on a match records the hit in
a module-level collector **and** raises. The raise stops the spend; the collector
defeats the `_evaluate` swallow.

**The `Popen` replacement MUST be a subclass of `subprocess.Popen`, not a
function.** This is a hard constraint, not a style preference: `subprocess.Popen`
is used non-callably across the suite and the production package, and binding a
plain function to that attribute breaks all of it.

- `MagicMock(spec=subprocess.Popen)` (`test_subprocess_utils.py:63`) and
  `Mock(spec=subprocess.Popen)` (`test_worker_pool.py:2915`). Both are evaluated
  *inside fixtures*, i.e. after the session-scoped guard installs. Verified by
  execution (2026-08-26): with a function bound to `subprocess.Popen`, the
  resulting mock raises `AttributeError: Mock object has no attribute 'poll'`
  (likewise `wait`), because a function spec exposes no `Popen` attributes.
- `subprocess.Popen[str]` subscripting: `subprocess_utils.py:39`,
  `mcp_call.py:76`, `parallel/worker_pool.py:189`, `fsm/handoff_handler.py:44,98`,
  `fsm/runners.py:114`, `fsm/executor.py:290`, `cli/queue.py:46`,
  `cli/verify_evidence.py:813,815`. A function is not subscriptable.

Implement as `class _GuardedPopen(subprocess.Popen)` overriding `__init__` to
record/raise *before* `super().__init__(...)`. Verified by execution that a
subclass preserves `spec=` mocking, `[str]` subscripting, `unittest.mock.patch`
shadow-and-restore (the `__exit__` restores to `_GuardedPopen`, not to the real
`Popen`), and the `run` → `Popen` delegation path.

**Raising before `super().__init__()` is safe — do not add a defensive
`self._child_created = False`.** `subprocess.Popen._child_created` is a *class*
attribute (`False`), so `Popen.__del__` running against the partially
initialized instance is well defined and emits no `Exception ignored in:
<function Popen.__del__>` noise. Verified by execution (2026-08-26). Stated
because the obvious defensive assignment looks necessary and is not.

**Basename matching is intentionally coarse.** The guard compares only
`os.path.basename(argv[0])`, and three of the eight names — `pi`, `omp`, `qwen` —
are generic enough to collide with an unrelated binary. Accepted: the escape
hatch is to patch the spawn primitive, which every legitimate test in the suite
already does (see § Why this shape needs no marker opt-out).

**Normalize `argv` defensively — the wrapper sees every subprocess call in the
suite.** Because the patch is process-global, the first argument arrives in every
form CPython accepts, and a `TypeError`/`IndexError` raised by the guard itself
would break unrelated tests in a way that reads as a guard bug. The wrapper must
handle, without raising on its own:

- a `list`/`tuple` of `str`, the common case;
- a bare `str` command (`shell=True`), where `argv[0]` is the whole command line
  and indexing yields a character, not a program name;
- a `PathLike` (or a list whose first element is one);
- an empty or non-subscriptable sequence;
- the command passed as a **keyword** — `run(args=[...])` / `Popen(args=[...])`
  are legal signatures, so resolve the command from
  `a[0] if a else kw.get("args")`. Nothing in the repo uses the kwarg form
  today (verified by grep, 2026-08-26), but the patch is process-global and the
  pass-through contract must not depend on callers we enumerated.

Note the `--version` carve-out must compare via `list(argv[1:]) == ["--version"]`
— argv may arrive as a tuple, and `("--version",) != ["--version"]`.

Anything it cannot confidently resolve to a program name is a **pass-through**,
not a failure — a guard that is noisy about unparseable input will be disabled.
Add a unit test per form.

**Accepted gap: `shell=True` string commands pass through**, so a shell-form host
spawn is not caught. This is acceptable, not an oversight: verified there is no
`shell=True` anywhere in production code — the only occurrence in the repo is
`loops/mechanize-skills.yaml:534`, a loop YAML action, not a Python call path.
State the gap in the guard's docstring so it is not rediscovered as a bug.

**The `run`/`Popen` pair is spawn-API-complete — this is what makes two patches
sufficient, and it was previously unstated.** Verified by grep over
`scripts/little_loops/` (2026-08-26): **zero** occurrences of
`asyncio.create_subprocess_exec`, `asyncio.create_subprocess_shell`,
`os.system`, `os.exec*`, `os.spawn*`, or `pty.spawn`. Every process the package
creates goes through the `subprocess` module. Note especially that
`asyncio.create_subprocess_*` does **not** route through `subprocess.Popen` — had
production used it, the guard would have a silent blind spot. Record this next
to the `shell=True` gap: it is the standing precondition for the guard's
completeness, so a future change introducing an asyncio or `os.exec*` spawn path
must extend the guard.

**Decided: patch exactly `subprocess.run` and `subprocess.Popen`, with `run`
recording first. Do not add more patches, and do not remove `run` as a
"redundant" one.**

`check_output` delegates to the module-global `run`; `call` / `check_call` /
`getoutput` / `getstatusoutput` reach the module-global `Popen`. Both delegation
routes have live production callers — `subprocess.call` at
`fsm/route_table.py:645` and `subprocess.check_output` at
`fsm/concurrency.py:371` — so any third patch would double-record a single spawn.

**`_GuardedPopen` alone is sufficient for coverage; the `run` patch buys
attribution, not reach.** Verified by execution (2026-08-26): with *only* the
`Popen` subclass installed, `subprocess.run(["claude", "-p", "hi"])` raises the
guard's exception — CPython's `run` builds its child through the module-global
`Popen`, which the patch has replaced. Earlier revisions justified the pair as
"demonstrably covers the whole surface"; that overstates the `run` patch's role,
since `Popen` alone already covers every delegation route listed above.

Keep the `run` patch anyway, on its actual merit: it records and raises at the
`run` boundary — before the call descends into `Popen` — so the traceback names
the helper the test actually called (`run_blocking_json`'s `subprocess.run` site)
rather than a `Popen` frame two levels down. Because it raises first, a host spawn
is still recorded exactly once. Stated so an implementer neither "fixes" a phantom
double-count nor deletes the `run` patch believing coverage depends on it — the
correct reason to keep it is diagnostics.

**Host binary basenames — all eight are derivable with no production change.**
`describe_capabilities()` is wired on all eight runners and never raises;
instantiating each `_HOST_RUNNER_REGISTRY` value and reading
`.describe_capabilities().binary` yields, verified by direct execution
(2026-08-26): `claude-code→claude`, `codex→codex`, `opencode→opencode`,
`pi→pi`, `gemini→gemini`, `omp→omp`, `kimi-code→kimi`, `qwen→qwen`.

Two sources that do **not** work, and why:

- `_PROBE_ORDER` (`host_runner.py:1827-1835`) has seven entries and is missing
  `opencode` — confirmed by execution:
  `[('claude-code','claude'), ('codex','codex'), ('pi','pi'), ('gemini','gemini'),
  ('omp','omp'), ('kimi-code','kimi'), ('qwen','qwen')]`.
- `build_version_check()` raises `HostNotConfigured` for **both** `opencode`
  (`host_runner.py:902-906`) and `pi` (`:978-982`), so it resolves only six of
  eight.

**Correction to earlier revisions:** those revisions claimed
`OpenCodeRunner.build_streaming` "does build a real invocation (only its
`build_blocking_json`/`build_detached` raise `HostNotConfigured`)". **That is
false.** `host_runner.py:871-913`: *every* `OpenCodeRunner.build_*` method raises
`HostNotConfigured`, `build_streaming` included; `PiRunner` (`:947-987`) is the
same. Neither host can spawn at all. Their basenames are therefore inert
entries in the guard's set — harmless to include, and cheap insurance if either
stub is ever wired — but they are **not** an argument for anything.

Consequently the "this must be a production change" framing of earlier revisions
is also false. Two shapes; **prefer the first**, now on its own merits rather
than on a forced-hand argument:

1. **A module-level `HOST_BINARY_NAMES: frozenset[str]` in `host_runner.py`**
   that the guard imports, with a unit test asserting
   `{cls().describe_capabilities().binary for cls in _HOST_RUNNER_REGISTRY.values()}
   == HOST_BINARY_NAMES`. Single source of truth, one new symbol, no signature
   churn, and the drift test is one line. **Do not write that test against
   `build_version_check().binary`** — it raises for opencode and pi.
2. Derive the set inside `conftest.py` from
   `describe_capabilities().binary` at fixture-install time. Genuinely zero
   production change, but puts a production invariant in test code and gives
   the guard a silent-drift failure mode (a new runner is picked up
   automatically, which is good; a renamed `describe_capabilities` binary
   string silently changes the guard, which is not).

The rejected third option — a `binary_name` class attribute on the `HostRunner`
Protocol and its eight implementations — is additive but ripples a Protocol
change through mypy and every conformance stub for the same guarantee.

The rest of this issue is written against (1).

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
  report rather than mutating session state. **Verified by execution
  (2026-08-26)** on a standalone spike of this exact design: exit status `1`
  under both `-n 0` and `-n 2 --dist loadfile`;
- attributes to the exact offending test structurally — via the report cursor,
  not by matching collector keys against the running test;
- still defeats the `_evaluate` swallow — the raise is eaten inside the test
  body, but the collector entry survives to teardown;
- removes the new-pattern session-fail entirely. (It does **not** remove the
  `pytest_sessionfinish` hook — that survives, demoted to print-only, and is
  still required; see § Residual gap below. Earlier revisions of this bullet said
  otherwise and contradicted the rest of the issue.)

**It reports as an ERROR, not a FAILURE, and the offending test still prints as
passed.** This is how pytest classifies an exception raised in a fixture's
post-`yield` teardown, and it is worth designing the message around rather than
discovering during implementation. Observed on the spike (2026-08-26):

```
6 passed, 1 error in 0.12s
ERROR spike_test.py::test_run_delegates_and_guard_fires - Failed: live spawn: ...
```

The run does fail (exit `1`), which is what matters for enforcement. But the
contributor's first read of the summary line shows their test green, with a
separately-listed teardown error beside it. **The failure message must therefore
lead with the diagnosis, not the mechanism** — open with something to the effect
of "this test spawned the real host CLI (`claude`) — mock the spawn", then the
binary, the test id, and how to mock it. A message that opens with collector or
cursor mechanics will read as test-infra flakiness against a green test line.

**Where the `test_id` in the collector tuple comes from.** The wrapper reads
`os.environ["PYTEST_CURRENT_TEST"]` (falling back to a placeholder when unset —
collection time, higher-scope fixtures, background threads). This is needed for
the dedupe key and for the `pytest_sessionfinish` summary, both of which must
name a test. It is **not** how attribution works: the teardown fixture attributes
by cursor position, so a hit recorded with a stale or placeholder `test_id` is
still reported exactly once, by the next test to finish. Earlier revisions
described the fixture as needing "no `PYTEST_CURRENT_TEST` keying", which is true
of *attribution* and false of the *recorded tuple*; both facts are stated here
because the bare claim reads as "don't record a test id."

**Advance a monotonic report cursor; do not test the collector for truthiness,
and do not snapshot its length before `yield`.** A naive
`if collector: pytest.fail(...)` cascade-fails every subsequent test on that
worker once any test trips the guard, turning a single real finding into an
unreadable wall of failures and obscuring which test actually spawned. But the
obvious fix — capture `len(collector)` before `yield`, compare after — is
**subtly lossy** and must not be used either: it silently drops any hit appended
outside a given test's function-fixture window, and those hits are then never
reported by any test. Three cases, all reachable:

- **Higher-scope fixture setup.** pytest sets up session- and module-scoped
  fixtures *before* function-scoped ones, so a spawn inside one is already in
  the collector when the first test's pre-`yield` snapshot is taken and reads as
  "not new". For this to be observable at all, the guard installer must run
  before other session-scoped autouse fixtures — same-scope autouse fixtures
  run in definition order, so **define `_install_no_live_host_cli` first among
  the session-scoped autouse fixtures in `conftest.py`**.
- **A background thread whose append lands between two tests** — the issue
  already anticipates thread hits (see Program Design § Background-thread
  spawns), and the length snapshot is precisely the mechanism that loses them.

(Earlier revisions also listed "collection / `pytest_configure` time" as a
source of collector hits. That case is **unreachable**: the guard installs at
session-fixture setup, which runs after collection, so a spawn at collection
time is simply not observed — a bounded, accepted gap, not a cursor case. The
cursor design does not depend on it.)

Use instead a module-level `_reported_upto: int` cursor. In teardown the fixture
reads `collector[_reported_upto:]`, and if that slice is non-empty it advances
`_reported_upto = len(collector)` and `pytest.fail()`s reporting exactly that
slice. This reports every entry exactly once, never cascades, and attributes an
orphaned hit to the next test to finish rather than to nobody. It strictly
dominates the snapshot; there is no case where the snapshot is better.

**The collector is written from FSM worker threads — guard it with a lock.**
Take the slice-and-advance under the same lock the wrapper appends under, so a
concurrent append cannot land between the read and the cursor advance and be
skipped.

**Dedupe the reported slice by `(test_id, binary)`.** Retry-on-error paths can
re-enter the spawn after the guard raises, so one offending test can record the
same spawn N times; the failure message should name the distinct spawns, with a
count, not print N identical lines.

**Residual gap — hits with no "next test", and the print-only hook that must
cover them.** The cursor attributes an out-of-window hit to the next test to
finish. When there is no next test, nothing reports it: the last test on a
worker, and any spawn during session- or module-fixture *teardown*, both land
after the final function-scoped teardown has already advanced the cursor. Left
alone, that is the same silent-no-op hole that disqualified
`pytest_sessionfinish` as the enforcement mechanism.

The `pytest_sessionfinish` hook is therefore **required, not optional** — still
not load-bearing for the failure (it cannot be, under xdist), but it must not be
silent either. It reads `collector[_reported_upto:]` under the lock and, if
non-empty, emits the entries **both** via `terminalreporter.write_line` **and**
via `warnings.warn`, so an unattributable hit is visible in the run output rather
than discarded. The gap it covers is a reporting gap, not an enforcement one:
such a hit does not fail the run. State that explicitly — it is a known,
bounded limitation, not an oversight.

**Undo the patch.** The session-scoped installer uses a raw
`pytest.MonkeyPatch()` instance (function-scoped `monkeypatch` is unavailable at
session scope) and calls `mp.undo()` in a `finally` after `yield`, following
`_guard_real_history_db` (`conftest.py:619-657`) exactly.

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

An autouse fixture patching `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER` to `[0]` and
`_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS` to `0`, making the convention structural
rather than per-test discipline.

**Decided: session-scoped autouse in `conftest.py`, suite-wide.** Earlier
revisions left this open between file-local (`test_fsm_executor.py`) and
suite-wide. File-locality only protects tests written *in that one file*, so a
rate-limit test added to a new file still wedges a worker — which fails the
acceptance criterion ("a rate-limit test that omits the ladder patch cannot
block") that is the actual goal here: structural protection against a
contributor who does not know the convention. Same implementation cost either
way, and `_guard_real_history_db` is precedent for patching production internals
suite-wide from `conftest.py`.

Verified safe (grep, 2026-08-26): the only references to either constant
anywhere in `scripts/` are `executor.py:91,94,3372,3377` and
`test_fsm_executor.py` (one docstring, six intentional patch sites, the `[0.3]`
site). No test asserts the default values, and the only other files mentioning
rate limiting at all (`test_ll_loop_display.py`, `test_generate_schemas.py`)
never drive `_handle_rate_limit`. The in-body `patch.multiple` wins on ordering
regardless of scope.

**Do not enumerate the rate-limit classes.** No test asserts the *default* values
of either constant — the only references are the six intentional patch sites
(`:7175-7176`, `:7202-7203`, `:7223-7224`, `:7996-7997`) plus the deliberate
`[0.3]` at `:7811-7812`. Collapsing both constants suite-wide is therefore safe,
and it removes the "resolve against all five rate-limit classes" enumeration
(`TestRateLimitRetries`, `TestRateLimitStorm`, `TestRateLimitTwoTier`,
`TestRateLimitHeartbeat`, `TestRateLimitCircuitIntegration`) along with the
maintenance risk of a sixth class nobody remembers to add. It also sidesteps the
"no class-scoped autouse fixture precedent" problem noted in Codebase Research.

**No marker exemption — the in-body patch already wins.** Earlier revisions of
this issue called for exempting `test_fsm_executor.py:7808-7813` (the
intentional non-zero `[0.3]` ladder) via a registered marker. That is both
impossible and unnecessary:

- **Impossible at session scope.** A session-scoped fixture runs once and cannot
  observe per-test markers, so there is no mechanism to skip it for a single
  test. Gating on a marker would require demoting the fixture to function scope
  for no benefit.
- **Unnecessary.** Verified at `test_fsm_executor.py:7806-7813`: the test enters
  `patch.multiple("little_loops.fsm.executor", _DEFAULT_RATE_LIMIT_BACKOFF_BASE=0,
  _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0.3], _DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=10)`
  **inside the test body**, so it is applied after — and therefore takes
  precedence over — the session-scoped fixture's patch. This is the file's
  established idiom (`:7172-7177`, `:7199-7203`, `:7220-7224`) and it resolves
  the ordering constraint in the fixture's favour by construction.

The AC that the `[0.3]` sleep is still observed remains, and is the real check;
only the marker mechanism is dropped.

**Patchability confirmed.** `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER`
(`executor.py:94`) and `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS` (`executor.py:91`)
are resolved at call time inside `_handle_rate_limit` (`executor.py:3372`,
`:3377`), not bound as parameter defaults or captured at construction, so
patching the module attributes takes effect.

## Acceptance Criteria

- [ ] **Permanent** unit tests prove the guard, rather than a probe that is
      deleted before merge (which would leave zero durable regression coverage):
      - call the wrapper directly with a fake `argv` whose `argv[0]` is a host
        binary, and assert it **both** records into the collector **and** raises;
      - drive `_drain_new_hits()` directly against a pre-seeded collector and
        assert it returns a failure message naming that hit, then returns `None`
        on the next call. This is the `_evaluate`-swallow property expressed
        durably — a recorded hit still surfaces even when the raise was eaten
        inside the test body.

      **Do not write this second test as "pre-seed the collector and assert the
      teardown fixture fails the test."** That AC appeared in earlier revisions
      and is not implementable, for two independent reasons:

      - **A test cannot assert that its own teardown fails.** By the time
        `_fail_on_live_host_cli`'s post-`yield` body runs, the test body has
        already completed; there is no point at which the test can observe the
        outcome and assert on it.
      - **`test_conftest_cap.py` holds a second, unrelated collector.** That file
        loads `conftest.py` via `importlib.util.spec_from_file_location` /
        `exec_module` (`:28-32`), so `conftest_under_test._hits` and
        `_reported_upto` are *different objects* from the ones the live
        plugin-loaded fixture reads. Seeding one has no effect on the other.

      Hence the extracted helper: put the slice-and-advance logic in
      `_drain_new_hits()` and unit-test that pure function. It is the entirety of
      the teardown fixture's logic, it is testable in either module instance, and
      the fixture itself reduces to `msg = _drain_new_hits(); if msg:
      pytest.fail(msg)` — small enough to verify by inspection.
- [ ] The `subprocess.Popen` replacement is a **subclass** of `subprocess.Popen`,
      not a function. Unit-tested via the two properties that break otherwise:
      `MagicMock(spec=subprocess.Popen).poll` resolves (the shape
      `test_subprocess_utils.py:63` and `test_worker_pool.py:2915` depend on),
      and `subprocess.Popen[str]` still subscripts (the shape
      `subprocess_utils.py:39`, `mcp_call.py:76`, `fsm/handoff_handler.py:44,98`
      and six other production sites depend on).
- [ ] The wrapper does **not** fire on `build_version_check()` invocations
      (`list(argv[1:]) == ["--version"]` — coerce, since argv may be a tuple),
      covered by a unit test. Verified:
      all **six** wired `build_version_check()` implementations emit exactly
      `args=["--version"]` — `claude` (`:473`), `codex` (`:772`), `gemini`
      (`:1152`), `omp` (`:1335`), `kimi` (`:1537`), `qwen` (`:1739`); `opencode`
      (`:902`) and `pi` (`:978`) raise `HostNotConfigured` instead. This single
      condition therefore covers every implementation that can emit an argv.
- [ ] The wrapper passes through, without raising an error of its own, every
      `argv` form CPython accepts: a `list`/`tuple` of `str`, a bare `str`
      command with `shell=True`, a `PathLike` (bare and as element 0), an
      empty sequence, and the command passed as the `args=` **keyword**
      (`run(args=[...])` / `Popen(args=[...])`). One unit test per form. The `shell=True` pass-through is a
      **stated accepted gap**, not a bug — no production code uses `shell=True`
      (verified: the only repo occurrence is `loops/mechanize-skills.yaml:534`).
- [ ] Two consecutive tests where only the first spawns a host CLI produce
      **exactly one** report — the teardown fixture advances a monotonic report
      cursor rather than testing the collector for truthiness, so a single hit
      does not cascade across the worker.
- [ ] The report is an **ERROR at teardown**, not a FAILURE, and the offending
      test itself still prints as passed (`N passed, 1 error`) — this is pytest's
      classification for a post-`yield` fixture raise and is expected, not a
      defect. The run's exit status is nonzero. Correspondingly, the failure
      message **leads with the diagnosis** ("this test spawned the real host CLI
      `<binary>` — mock the spawn"), not with collector/cursor mechanics, since
      the summary line beside it reads green.
- [ ] The collector tuple's `test_id` comes from `PYTEST_CURRENT_TEST` with a
      placeholder fallback when unset, and the guard behaves correctly when it is
      the placeholder — attribution is by cursor position, so a
      placeholder-`test_id` hit is still reported exactly once by the next test
      to finish.
- [ ] No production spawn path bypasses the `run`/`Popen` pair: a test (or a
      documented grep in the guard's docstring) asserts `scripts/little_loops/`
      contains no `asyncio.create_subprocess_exec` / `create_subprocess_shell`,
      `os.system`, `os.exec*`, `os.spawn*`, or `pty.spawn`. Verified zero as of
      2026-08-26; `asyncio.create_subprocess_*` in particular does **not** route
      through `subprocess.Popen` and would be a silent blind spot.
- [ ] `_GuardedPopen` raises before `super().__init__(...)` **without** a
      defensive `self._child_created = False` — `_child_created` is a class
      attribute, so `Popen.__del__` on the partially initialized instance is
      well-defined and emits no "Exception ignored" noise (verified by
      execution).
- [ ] A hit appended **outside** any test's function-fixture window is still
      reported exactly once, attributed to the next test to finish. Unit test:
      append to the collector directly (simulating a higher-scope fixture or
      background-thread spawn), then assert the *next* test's teardown fails and
      the one after it passes. This is the property the rejected
      `len()`-snapshot mechanism silently loses.
- [ ] Repeated identical spawns within one test (retry loops) are reported as
      one deduped `(test_id, binary)` entry with a count, not N lines.
- [ ] The guard fires for all three spawn paths: `run_blocking_json` (blocking),
      `run_claude_command` (streaming), and `build_detached` →
      `handoff_handler.py:123` (detached). **Tested without spending**: build the
      argv via `resolve_host().build_blocking_json(...)` /
      `.build_streaming(...)` / `.build_detached(...)` and pass
      `[inv.binary, *inv.args]` to the patched primitive directly, asserting a
      recorded hit. Do not invoke the production helpers themselves — that would
      spawn for real, which is the defect this issue exists to prevent.
- [ ] A hit with **no next test to attribute to** — the last test on a worker, or
      a spawn during session-/module-fixture teardown — is still surfaced by the
      `pytest_sessionfinish` summary, via **both** `terminalreporter.write_line`
      and `warnings.warn`. Unit-tested by pre-seeding the collector past
      `_reported_upto` and calling the hook directly with a stand-in `session`
      (per `test_pytest_history_plugin.py`'s convention). This is a **reporting**
      guarantee only — such a hit does not fail the run, which is a known,
      bounded limitation, not an oversight.
- [ ] The session-scoped installer restores the originals: `mp.undo()` in a
      `finally` after `yield`, following `_guard_real_history_db`
      (`conftest.py:619-657`). Asserted by a test that reads `subprocess.Popen`
      after a nested install/teardown cycle.
- [ ] The guard fails the run **under the default `-n logical` addopts**, not
      only serially. This is the specific mechanism check: a `pytest_sessionfinish`
      exit-status mutation on an xdist worker does not reach the controller.
      **One-time manual verification, not a permanent test** — with no
      `pytester`/`testdir` convention in this codebase there is no durable
      in-suite form of "a deliberately-tripped guard fails the run"; verify it
      once via the spike shape (already done 2026-08-26: exit `1` under both
      `-n 0` and `-n 2 --dist loadfile`) and do not hunt for a merged
      equivalent.
- [ ] `python -m pytest scripts/tests/test_host_runner.py` passes unchanged — no
      marker opt-out needed, or the opt-out is documented with the specific test
      that required it.
- [ ] Full suite `python -m pytest scripts/tests/` passes with both guards
      active, and a serial `-n 0` run of `test_fsm_executor.py` and
      `test_host_runner.py` also passes.
      The serial run is the real regression check — it is the configuration in
      which BUG-3325's defects were reachable, and with the guard active a live
      spawn is a failure, so "the serial suite passes" *is* "zero live host-CLI
      spawns."
- [ ] A rate-limit test that omits the ladder patch cannot block. The
      **permanent** regression test asserts the patched state directly —
      `executor._DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER == [0]` and
      `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS == 0` — so a fixture regression
      fails fast. **Do not merge a sleep-observing probe**: its failure mode
      when the fixture regresses is a 300s sleep the thread-method watchdog
      cannot kill, i.e. the exact BUG-3208 wedge this issue exists to prevent,
      planted deliberately in the suite. A probe that drives
      `_handle_rate_limit` unpatched-in-body is fine as a **one-time
      verification during implementation only**.
- [ ] `test_fsm_executor.py:7806-7813` still observes its intentional non-zero
      (`[0.3]`) ladder — its in-body `patch.multiple` takes precedence over the
      session-scoped fixture, with no marker exemption involved.
- [ ] Any new marker is registered in `scripts/pyproject.toml` `[tool.pytest.ini_options] markers`
      (`:280-285`); the suite runs under `--strict-markers` (`:264`), so an
      unregistered marker is a hard error.
- [ ] `docs/development/TESTING.md` documents the live-host-CLI guard
      (unconditionally — not gated on a marker being registered): what the
      ERROR-at-teardown means, why the test line beside it still reads
      `passed`, and how to mock the spawn.
- [ ] `_fail_on_live_host_cli` is defined **first** among the function-scoped
      autouse fixtures in `conftest.py`, so its teardown runs after all other
      function-scoped teardowns and a spawn inside another function fixture's
      teardown is attributed to the same test.

## Impact

- **Priority**: P1 — the gap it closes is a live, recurring billing leak with no
  detection signal. BUG-3325 fixes three known instances; nothing stops the
  fourth.
- **Effort**: Medium. All three fixtures live in `conftest.py`: a session-scoped
  installer (patching `subprocess.run` and a `subprocess.Popen` **subclass**,
  undone via `mp.undo()`), a function-scoped teardown-fail fixture, and a
  session-scoped ladder-collapse fixture — plus a print-only
  `pytest_sessionfinish` summary and unit tests.
  **One small production change is chosen, not forced**: a module-level
  `HOST_BINARY_NAMES: frozenset[str]` in `host_runner.py`, so the guard's
  basename list has a single explicit source with a drift test. A
  zero-production-change alternative exists and works — all eight basenames are
  derivable from `describe_capabilities().binary` (verified by execution) — so
  earlier revisions' claim that a production change is unavoidable was itself
  wrong, as was the opencode premise it rested on (see Proposed Solution § Host
  binary basenames).
  **No new marker is expected** — the ladder exemption was dropped as both
  impossible at fixture scope and unnecessary.
- **Risk**: Medium-low, but larger than earlier revisions assumed. Because both
  modules `import subprocess` (so the patch is process-global), the false-positive
  surface is **the entire suite**, not the two named call paths — every
  `subprocess.run`/`Popen` call in every test is inspected. Integration and
  conformance tests are the likeliest legitimate spawners; check
  `-m integration` and `-m conformance` explicitly, since they are excluded from
  the CI unit run and easy to miss.
- **Breaking Change**: No. `HOST_BINARY_NAMES` is additive.

## Integration Map

**Files to modify:**
- `scripts/tests/conftest.py` — **the only test file modified.** Holds all three
  fixtures (session-scoped guard installer, function-scoped teardown-fail,
  session-scoped ladder collapse) plus the print-only `pytest_sessionfinish`
  summary. Existing autouse fixtures live at `:553-762`; `pytest_configure` at
  `:77` and `pytest_collection_modifyitems` at `:98` show the hook conventions in
  force.
- `scripts/tests/test_fsm_executor.py` — **no change.** The ladder fixture is
  suite-wide in `conftest.py` (decided, see Proposed Solution Part 2), and the
  `[0.3]` heartbeat test (`:7806-7813`) needs nothing — its in-body
  `patch.multiple` already wins on ordering.
- `scripts/pyproject.toml` — register a marker at `:280-285` **only if** one
  proves genuinely necessary; none is expected.
- `scripts/little_loops/host_runner.py` — additive module-level
  `HOST_BINARY_NAMES: frozenset[str]` (see § Impact).

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
  actually needs is **not** in `_PROBE_ORDER` (`host_runner.py:1827-1835`),
  which has only **seven** entries and is **missing `opencode`** entirely.
  `cls().describe_capabilities().binary` is wired and non-raising on all eight
  registry entries, opencode and pi included, and is the derivable source.
  [Agent 2 finding, corrected]
- `scripts/tests/test_conftest_cap.py:28-32` loads `conftest.py` as a **second,
  independent module** via `importlib.util.spec_from_file_location` /
  `exec_module`, separate from the plugin-loaded `conftest` pytest itself uses.
  Any module-level collector state the new `_no_live_host_cli` guard introduces
  will exist as two unrelated instances — one in the real plugin, one in this
  file's `conftest_under_test` object. This file's `TestXdistAutoNumWorkers` /
  `TestPytestConfigureNice` / `TestNoParallelMarkerRouting` classes are also the
  de facto regression suite for `conftest.py` hook-level behavior, and the
  natural home for a new `pytest_sessionfinish` unit test (see Tests below).
  One consequence of the double-load: at `exec_module` time the live guard is
  already installed, so the standalone module's `_GuardedPopen` subclasses the
  live guard class rather than the real `Popen`. Harmless (it is never
  installed), but unit tests constructing the standalone class must use a
  host-binary argv (which records/raises before `super().__init__`) — a
  non-host argv would fall through to the live guard's `__init__` and spawn a
  real process. [Agent 2 finding; extended 2026-08-26 review]
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
- `docs/development/TESTING.md` — **add a short paragraph documenting the
  live-host-CLI guard itself, unconditionally** (the marker rows above are
  marker-gated, and no marker is expected — without this the guard would ship
  undocumented). Cover: what the guard is, that the failure surfaces as an
  ERROR-at-teardown beside a test line that still reads `passed`, and how to
  mock the spawn (patch `subprocess.run`/`subprocess.Popen` or the helper one
  level up, per the existing idioms in `test_host_runner.py` /
  `test_subprocess_utils.py`). A contributor who trips the guard otherwise has
  only the failure message. [2026-08-26 review]

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
  **Downgraded from "highest-risk false-positive candidate" (2026-08-26
  review): inspected — every unpatched `subprocess.run` call in this file execs
  a bash hook script (`hooks/scripts/*.sh`), so `argv[0]` is `bash`/a script
  path, never a host binary, and a basename check does not trip.** Keep the
  cheap per-test triage at merge time as confirmation, but this file is
  expected clean. [Agent 1 + 3 finding; downgraded on inspection]
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

- Add an additive module-level `HOST_BINARY_NAMES: frozenset[str]` to
  `host_runner.py` and derive the guard from it, with a drift test comparing it
  against `{cls().describe_capabilities().binary for cls in
  _HOST_RUNNER_REGISTRY.values()}` — **not** against `build_version_check()`,
  which raises for `opencode` and `pi`.
- Make the `subprocess.Popen` replacement a subclass, not a function, and cover
  the two properties that break otherwise (`spec=` mocking, `[str]`
  subscripting).
- Restore the originals with `mp.undo()` in a `finally` after `yield`.
- Add the print-only `pytest_sessionfinish` summary that emits unreported
  collector entries via `terminalreporter.write_line` **and** `warnings.warn`,
  so a hit with no next test to attribute to is still visible. Unit-test it in
  `test_conftest_cap.py` against the standalone-loaded module object, following
  that file's existing convention of calling conftest hooks directly.
- Add the `--version` carve-out (`argv[1:] == ["--version"]`) and confirm it with
  a unit test — four
  production sites (`install_check.py:160,171`, `cli/action.py:350`,
  `cli/doctor.py:1183`) spawn `<host binary> --version`, which is free but trips
  a naive `argv[0]` basename check.
- Cover the detached path (`handoff_handler.py:123`) in the guard's scope and
  acceptance criteria — it is a third host-CLI spawn path and the priciest.
- Triage `test_hooks_integration.py`'s mixed patched/unpatched `subprocess.run`
  calls against the guard's exact monkeypatch target before merge — expected
  clean (inspected 2026-08-26: all unpatched calls exec bash hook scripts, not
  host binaries), so this is confirmation, not risk mitigation.
- Run `-m integration` and `-m conformance` explicitly (per the issue's own
  Testing Strategy) to classify the 18 unreviewed integration/conformance files
  listed above.
- Add marker rows to `docs/development/TESTING.md:1049` and
  `docs/development/TROUBLESHOOTING.md:822-828` **only if** a new marker is
  registered — with the ladder exemption dropped, none is expected.
- Add the unconditional `docs/development/TESTING.md` paragraph documenting the
  guard itself (see Documentation above) — what it is, why the offending test
  line still reads green beside the teardown ERROR, and how to mock the spawn.
  This is not marker-gated.
- Normalize the wrapper's command argument across all `argv` forms (`list`,
  `str` + `shell=True`, `PathLike`, empty, and the `args=` keyword form —
  resolve from `a[0] if a else kw.get("args")`), passing through anything
  unresolvable, with a unit test per form. The process-global patch means the
  wrapper is on the path of every subprocess call in the suite, so a `TypeError`
  from the guard itself would break unrelated tests.
- Advance a monotonic `_reported_upto` cursor — not a truthiness check
  (cascades) and not a pre-`yield` `len()` snapshot (silently drops hits from
  higher-scope fixture setup and background threads). Take the
  slice and advance the cursor under the collector's lock, and dedupe the
  reported slice by `(test_id, binary)`. Define the guard installer **first**
  among the session-scoped autouse fixtures so spawns in the others' setup are
  observed (same-scope autouse fixtures run in definition order); a spawn at
  collection/`pytest_configure` time predates the install and is an accepted,
  unobserved gap. Likewise define `_fail_on_live_host_cli` **first** among the
  function-scoped autouse fixtures, so its teardown runs last and catches
  spawns from other function fixtures' teardowns in the same test.
- Put that slice-and-advance in a module-level `_drain_new_hits() -> str | None`
  helper rather than inline in the fixture, so it is unit-testable — a test
  cannot assert that its own teardown fails, and `test_conftest_cap.py`'s
  standalone-loaded conftest has a separate collector instance.
- Lead the failure message with the diagnosis ("this test spawned the real host
  CLI `<binary>`"), because it surfaces as an ERROR-at-teardown next to a test
  line that still reads `passed`.
- Read `test_id` from `PYTEST_CURRENT_TEST` with a placeholder fallback (needed
  for the dedupe key and the summary; attribution is by cursor).
- Do **not** add `self._child_created = False` to `_GuardedPopen` — it is a class
  attribute and `Popen.__del__` is already safe on the partial instance.
- Record in the guard's docstring that `subprocess.run`/`Popen` is the complete
  spawn surface: no `asyncio.create_subprocess_*`, `os.system`, `os.exec*`,
  `os.spawn*`, or `pty.spawn` in `scripts/little_loops/` (verified zero,
  2026-08-26), and `asyncio.create_subprocess_*` would bypass the guard entirely.
- Put the ladder fixture session-scoped in `conftest.py` (decided; file-local
  scope would not satisfy the AC). Verified safe: no test asserts the constants'
  defaults, and no other test file drives `_handle_rate_limit`.
- Note the `shell=True` pass-through as an accepted gap in the guard's
  docstring; no production code uses `shell=True`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- **`_guard_real_history_db`'s exact fail-shape, for the guard's own design**: session-scoped generator fixture using a raw `pytest.MonkeyPatch()` instance (not the function-scoped `monkeypatch` fixture, since `monkeypatch` isn't available at session scope), with a bare `assert` inside the patched wrapper function and `mp.undo()` in a `finally` after `yield`. It fails synchronously inside whichever test's call stack triggers the violation — no separate collector, no `pytest.fail()`, no session-teardown reporting. It attributes to the true offending test specifically *because* the assertion runs in that test's own stack frame, which the fixture's own docstring contrasts with a prior mtime/size approach that could only blame "the last test in the session."
- **No existing violation-collector-then-report-at-teardown pattern exists anywhere in `scripts/tests/` or `scripts/little_loops/`.** `_guard_real_history_db` fails at the choke point, not via deferred collection. This issue's collector-plus-teardown-fixture shape (needed specifically to defeat `_evaluate`'s exception-swallow) is a new pattern for this codebase, not an extension of an existing one.
- **Marker registration/consumption round-trip, modeled on `no_parallel`**: registered as one string in `pyproject.toml:284` (`"no_parallel: marks tests that must not run on xdist workers ..."`), consumed via `"no_parallel" in item.keywords` inside `pytest_collection_modifyitems` (`conftest.py:98-124`), and applied via `@pytest.mark.no_parallel` on test methods (e.g. `test_worktree_utils.py:1228`). Any new marker this issue adds (ladder exemption, live-CLI opt-out if one proves necessary) should follow this same three-part shape.
- **Module-bound `subprocess` patch convention only has direct precedent on the `host_runner` side.** `TestRunBlockingJson` patches `little_loops.host_runner.subprocess.run` directly (6 sites, `test_host_runner.py:1958-2027`). No existing test patches `little_loops.subprocess_utils.subprocess.Popen` at that same bound-attribute layer — tests exercising `run_claude_command` instead patch one level higher: the function itself (`patch("little_loops.subprocess_utils.run_claude_command", ...)` in `test_action.py:232,392,499,536,579,596`, `test_workflow_sequence_analyzer.py:2304`) or `resolve_host` (`test_subprocess_utils.py:81,1458,2385,2428,2468,2511`, `test_subprocess_mocks.py:30`). Consequence for this issue: since these tests replace `run_claude_command`/`resolve_host` entirely, execution never reaches the `subprocess.Popen` call the guard wraps — the guard is bypassed by construction for these tests (they never call the real function), not by a stacked patch shadowing it the way `TestRunBlockingJson` shadows the `host_runner` guard. Both are "no false positive," but for different mechanical reasons — worth distinguishing during implementation/verification rather than assuming the same shadowing argument applies to both spawn paths.
- **No existing "test-infra self-check" probe-then-delete/xfail pattern in this codebase.** A search across `scripts/tests/` found no prior instance of a test deliberately added to prove a guard fires and then removed/`xfail`-guarded before merge. This is part of why the design uses **permanent** unit tests instead: there is no convention to follow for a disappearing probe, and a deleted one leaves zero durable regression coverage.

## Program Design

### Signatures

- `_install_no_live_host_cli()` — session-scoped autouse fixture in
  `conftest.py`, using a raw `pytest.MonkeyPatch()` instance with `mp.undo()` in
  a `finally` after `yield` (`_guard_real_history_db`'s shape). Monkeypatches the
  **global** `subprocess.run` and `subprocess.Popen` (one pair; see Proposed
  Solution). Both replacements normalize the command argument to a program name
  (pass through anything unresolvable), compare its basename against the eight
  host binary names, apply the `argv[1:] == ["--version"]` carve-out, append
  `(test_id, binary)` to a module-level collector on a match **under a lock**
  (the collector is written from FSM worker threads), then raise a dedicated
  exception whose message names the binary, the test, and how to mock the spawn.
  `test_id` is read from `PYTEST_CURRENT_TEST` with a placeholder fallback; it
  feeds the dedupe key and the summary, not attribution (the cursor does that).
- `_GuardedPopen(subprocess.Popen)` — the `Popen` replacement is a **subclass**,
  overriding `__init__` to record/raise before `super().__init__(...)`. A plain
  function breaks `MagicMock(spec=subprocess.Popen)`
  (`test_subprocess_utils.py:63`, `test_worker_pool.py:2915`) and
  `subprocess.Popen[str]` subscripting (nine production sites). Verified by
  execution; see Proposed Solution Part 1.
- `_drain_new_hits() -> str | None` — **module-level pure helper**, not a
  fixture. Under the collector's lock, reads `collector[_reported_upto:]`;
  returns `None` if empty, otherwise advances the module-level `_reported_upto`
  cursor to `len(collector)` and returns a formatted failure message listing that
  slice, deduped by `(test_id, binary)` with a count. Never a bare truthiness
  check (cascades across the worker) and never a pre-`yield` `len()` snapshot
  (silently drops hits from higher-scope fixtures and background threads). **Extracted as a function specifically so it is
  unit-testable** — a test cannot assert that its own teardown fails, and
  `test_conftest_cap.py`'s standalone-loaded conftest has its own unrelated
  collector (see Acceptance Criteria bullet 1). The message leads with the
  diagnosis, since the failure surfaces as a teardown ERROR beside a green test
  line.
- `_fail_on_live_host_cli()` — **function-scoped** autouse fixture in
  `conftest.py`, reduced to `yield` then `msg = _drain_new_hits(); if msg:
  pytest.fail(msg)`. This is the enforcement mechanism; it works under xdist
  where a `pytest_sessionfinish` exit-status mutation does not (verified by
  execution: exit `1` under both `-n 0` and `-n 2 --dist loadfile`). Note it
  produces an ERROR-at-teardown report, not a FAILURE — see Proposed Solution
  § Failing the run. **Define it first among the function-scoped autouse
  fixtures in `conftest.py`** — function-scoped fixtures tear down in reverse
  setup order, so defining it first makes its teardown run *last*, and a spawn
  inside another function fixture's teardown is caught by the same test's error
  rather than deferring to the next test (or, for the last test on a worker,
  degrading to the print-only summary). This mirrors the define-first rule
  already stated for the session-scoped installer, for the symmetric reason.
- `pytest_sessionfinish(session, exitstatus)` — **required, print-only.** Calls
  the same `_drain_new_hits()` helper (so the lock, the cursor advance, and the
  dedupe are shared with the teardown fixture rather than reimplemented) and, if
  it returns a message, emits it via **both** `terminalreporter.write_line` and
  `warnings.warn`. This is
  what surfaces a hit that has no next test to attribute to (last test on the
  worker; session-/module-fixture teardown). Must not be load-bearing for the
  failure — it cannot fail the run under xdist. **`warnings.warn` here is safe
  today but fragile**: `scripts/pyproject.toml` has no `filterwarnings` config
  (verified 2026-08-26), so the warning cannot escalate to an error — but if
  `filterwarnings = ["error"]` is ever added, a sessionfinish-time warning
  could crash a worker confusingly. Note this in the hook's docstring so the
  interaction is discovered by reading, not by debugging.
- `_collapse_rate_limit_ladder()` — **session-scoped** autouse fixture in
  `conftest.py` (decided; see Proposed Solution Part 2), patching the two ladder
  constants suite-wide. **No marker exemption**: the one intentional non-zero
  ladder patches in-body and therefore wins on ordering.
- `HOST_BINARY_NAMES: frozenset[str]` — new module-level constant in
  `host_runner.py`, the guard's single source for the basename list, with a
  drift test asserting
  `{cls().describe_capabilities().binary for cls in _HOST_RUNNER_REGISTRY.values()}
  == HOST_BINARY_NAMES`. **Not** `build_version_check().binary`, which raises
  `HostNotConfigured` for `opencode` and `pi`. (See Proposed Solution § Host
  binary basenames for the zero-production-change and `binary_name`-Protocol
  alternatives, and for the correction to the false opencode claim.)

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
snapshotted and asserted in the **function-scoped teardown fixture** (not
`pytest_sessionfinish` — see Proposed Solution § Failing the run).

**Background-thread spawns.** `run_claude_command` can be reached from an FSM
worker thread, where a raise-only guard would be swallowed by the thread just as
`_evaluate` swallows it on the main path — the collector catches both, which is a
second independent argument for the record-and-raise shape. Caveat to note in the
implementation: a hit from a thread that outlives its test attributes to whichever
test is in teardown when the append lands. Rare, and the recorded `binary` still
identifies the spawn, but a confusing attribution here is expected behaviour, not
a guard defect.

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
  records *and* raises; separately pre-seed the collector and call
  `_drain_new_hits()` directly, asserting it returns a message naming the hit and
  then `None`. The second test is the `_evaluate`-swallow property in durable
  form — a recorded hit still surfaces even when the raise was eaten — and needs
  no live FSM run. Do **not** try to assert that a real teardown fails: a test
  cannot observe its own teardown, and `test_conftest_cap.py`'s standalone-loaded
  conftest carries a separate collector instance.
- Exercise all three spawn paths (blocking, streaming, detached), not just the
  blocking one, and assert the `--version` carve-out. Build each path's argv from
  `resolve_host().build_*()` and feed `[inv.binary, *inv.args]` to the patched
  primitive — never call the production helper, which would spawn for real.
- Assert the `Popen` replacement is subclass-shaped:
  `MagicMock(spec=subprocess.Popen).poll` resolves and `subprocess.Popen[str]`
  subscripts while the guard is installed. Without this, a regression to a
  function wrapper breaks `test_subprocess_utils.py` and `test_worker_pool.py`
  with an unrelated-looking `AttributeError`.
- Cover the `pytest_sessionfinish` summary by pre-seeding the collector past
  `_reported_upto` and calling the hook with a stand-in `session`
  (`test_pytest_history_plugin.py`'s convention — there is no `pytester`/`testdir`
  usage anywhere in this codebase).
- Cover the wrapper's `argv` normalization for every accepted form; the
  non-cascading property (two consecutive tests, one spawner, one failure); and
  the orphaned-hit property (a collector entry appended outside any test's
  fixture window is still reported exactly once, by the next test to finish).
  The last one is what distinguishes the cursor from the rejected `len()`
  snapshot — without it, a regression back to the snapshot passes every test.
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
- **Rate-limit test classes in `test_fsm_executor.py`**, for orientation only — the ladder fixture is suite-wide and does not enumerate them: `TestRateLimitRetries` (`:7072`), `TestRateLimitStorm` (`:7442`), `TestRateLimitTwoTier` (`:7573`), `TestRateLimitHeartbeat` (`:7756`, contains the intentional `[0.3]` ladder at `:7806-7813`), `TestRateLimitCircuitIntegration` (`:7842`).
- **No class-scoped autouse fixture precedent exists in this codebase**, which is a second reason the ladder fixture is session-scoped rather than class-scoped. All existing autouse fixtures in `conftest.py` (`_isolate_history_db`, `_guard_real_history_db`, `_isolate_session_log_dir`, `_restore_cmd_run_env_vars`, `_reset_deprecated_key_warnings`) apply suite-wide; none uses `request.cls`/`request.node.cls` or a marker check to scope to specific test classes. The only class/marker-scoping precedent anywhere is the `no_parallel` marker's `item.keywords` check inside `pytest_collection_modifyitems` (collection-time item filtering, not a fixture).

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

### Superseded claims — do not re-derive

Four pre-implementation reviews (2026-08-26) retracted the claims below. They are
listed only so a reader who encounters them elsewhere (BUG-3325, git history, an
older copy of this file) does not reintroduce them. Each was verified wrong by
reading or executing the code; the body of this issue is already written against
the corrected design.

- **`pytest_sessionfinish` as the enforcement mechanism.** xdist does not
  propagate a worker-mutated `session.exitstatus` to the controller, so it could
  silently no-op under the default `-n logical` addopts. Replaced by a
  function-scoped teardown fixture; the hook survives as a print-only summary.
- **A pre-`yield` `len()` snapshot of the collector.** Silently drops hits from
  higher-scope fixture setup and background threads. Replaced
  by a monotonic `_reported_upto` cursor. (A bare truthiness check was rejected
  earlier still — it cascade-fails every subsequent test on the worker.)
- **"Collection / `pytest_configure` time" as a source of collector hits.**
  Unreachable — the guard installs at session-fixture setup, after collection.
  Replaced by the fixture-ordering requirement (guard installer defined first
  among session-scoped autouse fixtures) plus a stated accepted gap for
  pre-install spawns.
- **A permanent sleep-observing probe for the ladder guard.** Its regression
  failure mode is the un-killable 300s sleep (the BUG-3208 wedge) rather than a
  fast failure. Replaced by a direct assertion on the patched constants; the
  sleep probe is one-time implementation verification only.
- **"The monkeypatch is module-bound."** Both call sites `import subprocess`, so
  there is one process-global attribute pair. This widened coverage for free
  (detached path, version checks) and widened the false-positive surface to the
  whole suite.
- **`OpenCodeRunner.build_streaming` builds a real invocation.** False — every
  `OpenCodeRunner.build_*` raises `HostNotConfigured` (`host_runner.py:871-913`),
  as does every `PiRunner.build_*` (`:947-987`). Neither host can spawn; their
  basenames are inert entries in the guard's set.
- **"A production change is unavoidable."** False, and it rested on the opencode
  premise above. All eight basenames are derivable with zero production change
  from `cls().describe_capabilities().binary`. `HOST_BINARY_NAMES` is retained as
  the preferred shape on its own merits, not as a forced hand.
- **Resolve basenames from `_PROBE_ORDER`.** It has seven entries and is missing
  `opencode` (confirmed by execution).
- **A registered marker exempting the `[0.3]` ladder test.** Impossible at
  session scope (the fixture cannot observe per-test markers) and unnecessary —
  `test_fsm_executor.py:7806-7813` patches in-body and already wins on ordering.
  No new marker is expected anywhere in this issue.
- **A `binary_name` attribute on the `HostRunner` Protocol.** Same guarantee as
  `HOST_BINARY_NAMES` but ripples a Protocol change through mypy and every
  conformance stub.
- **A delete-before-merge probe proving the guard fires.** Replaced by permanent
  unit tests; a deleted probe leaves zero durable regression coverage.
- **"Pre-seed the collector and assert the teardown fixture fails the test."**
  Not implementable: a test cannot observe its own teardown, and
  `test_conftest_cap.py` loads `conftest.py` as a second module (`:28-32`) whose
  collector is a different object from the live plugin's. Replaced by a
  `_drain_new_hits()` helper unit-tested as a pure function.
- **"The offending class is `no_parallel` / `10 skipped in 1.26s`."** False.
  `TestRateLimitCircuitIntegration` (`test_fsm_executor.py:7842`) carries no
  marker and reports `10 passed in 1.76s` under default addopts (verified by
  execution). The suite's only `no_parallel` markers are
  `test_fsm_signal_integration.py:42` and `test_worktree_utils.py:1228`. The
  defect was hidden behind green, not behind a skip.
- **"The `run`/`Popen` pair demonstrably covers the whole surface."** Overstated:
  `_GuardedPopen` alone catches `subprocess.run` (CPython's `run` builds its
  child via the module-global `Popen`), verified by execution. The `run` patch is
  retained for attribution/diagnostics, not for reach.
- **"The teardown fixture removes the `pytest_sessionfinish` hook entirely."**
  False and self-contradictory — the hook survives as a required print-only
  summary covering hits with no next test to attribute to.
- **"The fixture attributes with no `PYTEST_CURRENT_TEST` keying."** True of
  attribution (the cursor does that), false of the recorded tuple — `test_id`
  comes from `PYTEST_CURRENT_TEST` and is needed for the dedupe key and summary.
- **A five-class enumeration for the ladder fixture.** Replaced by one
  suite-wide fixture; no test asserts the constants' defaults.
- **"Seven wired `build_version_check()` implementations."** Six.

## Session Log
- `/ll:confidence-check` - 2026-08-26T20:52:31 - `88aa69aa-30d3-411b-b2b0-f5cfaf1a8181.jsonl`
- `/ll:wire-issue` - 2026-08-26T20:23:34 - `c52dee45-306e-4834-bf4d-c82265f05dc7.jsonl`
- `/ll:refine-issue` - 2026-08-26T20:16:59 - `c8fbfaf4-7e26-4a99-9fe9-48c752eecfe4.jsonl`
