---
id: FEAT-3454
title: Fake host with a directives language for scripting deterministic event sequences
type: FEAT
priority: P2
status: open
testable: true
discovered_date: '2026-09-11'
labels:
- testing
- multi-host
relates_to:
- FEAT-3455
- ENH-3459
- ENH-3460
confidence_score: 100
outcome_confidence: 86
score_complexity: 16
score_test_coverage: 24
score_ambiguity: 24
score_change_surface: 22
---

## Summary

The orchestration paths that matter most — event ordering, abort mid-turn, idle
timeout, recovery after a failed start, rate-limit retry — can only be exercised
today against a live host. That makes them slow, expensive, flaky, or simply
untested, and it is why the shipped conformance suite settles for asserting a
`HostInvocation` is constructable rather than running anything.

Build a fake host: a **real executable** (`ll-fake-host`, a console script) plus a
`FakeHostRunner` registered through `_HOST_RUNNER_REGISTRY`. A test writes a prompt
string that encodes an exact sequence of wire events, failures, and timings; the
runner hands that prompt to the executable exactly as a real runner would; the
executable emits the scripted stream-JSON on stdout and exits with the scripted
code. The executor drives it through the untouched `subprocess.Popen` path in
`run_claude_command`, so nothing in the executor knows it is fake.

## Motivation

- Everything downstream in the harness testing story stands on this: a behavioral
  conformance suite (FEAT-3455) needs a CI-runnable target, and the only target
  available today is a live host binary behind an env gate.
- It generalizes the fake-clock idea — deterministic time made temporal paths
  testable; a scriptable fake host makes the host's whole event stream testable.
- The consumer-side precedent already exists (`_NeverEOFStdout` in
  `scripts/tests/test_subprocess_utils.py:2589-2611` drives a scripted JSONL list
  into the read loop), but it patches `Popen`. The fake host is the producer-side
  version: the real spawn path, the real selectors loop, the real exit-code and
  timeout handling.

## Current Behavior

`scripts/tests/conformance/test_host_conformance.py` parametrizes over
`_HOST_RUNNER_REGISTRY` and asserts only that a `HostInvocation` is constructable —
its docstring concedes it never executes the prompt. Ordering, abort, idle-timeout,
and failed-start paths in `run_claude_command`
(`scripts/little_loops/subprocess_utils.py:422-771`) are exercised only by
live-host runs, or by tests that patch `subprocess.Popen` and therefore never touch
the spawn, exit-code, or process-group-kill code.

## Design Decision: the fake must be a real executable

`HostRunner` (`scripts/little_loops/host_runner.py:394-492`) is an argv builder. It
has no run method, and a `HostInvocation` cannot emit anything. The only consumer of
host events is `run_claude_command`, which does `subprocess.Popen([invocation.binary,
*invocation.args])` at `subprocess_utils.py:526-536`. Therefore:

- **`FakeHostRunner` is a normal runner.** Its `build_*` methods return
  `HostInvocation(binary="ll-fake-host", args=[...prompt...], env=..., capabilities=...)`.
  It never spawns, never parses directives, and records nothing.
- **`ll-fake-host` is a console script** (`[project.scripts]` in
  `scripts/pyproject.toml`, entry point `little_loops.fake_host:main`). It parses the
  directives out of its prompt argument and writes the scripted stream-JSON to
  stdout, stderr text to stderr, sleeps where told, and exits with the scripted code.
  Editable install (`pip install -e "./scripts[dev]"`, which both the dev setup and
  CI perform) installs it into the running interpreter's scripts dir.
- **Put the scripts dir on PATH at session start; a missing fake is a FAIL, not a
  skip.** Editable install alone does not make `ll-fake-host` resolvable: the CI
  jobs run `.venv/bin/python -m pytest` without activating the venv, and only the
  `unit-tests` job appends `.venv/bin` to `GITHUB_PATH` (`.github/workflows/ci.yml:110`);
  the Thinky `conformance` job (`:149-207`) does not, and on this machine
  `ll-verify-host-map` resolves to the miniforge bin while `ll-fake-host` is not on
  PATH at all. A `shutil.which`-gated skip would therefore silently drop every
  behavioral test in the one CI job meant to run them — the exact
  passing-test-that-asserts-nothing failure this issue exists to remove. Add a
  `pytest_sessionstart` hook to `scripts/tests/conftest.py` that prepends
  `sysconfig.get_path("scripts")` (the dir console scripts land in for the running
  interpreter — `.venv/bin` in CI, the miniforge bin here) to `os.environ["PATH"]`.
  After that, `shutil.which("ll-fake-host") is None` means a broken editable
  install; the tests fail with "run `pip install -e ./scripts[dev]`". The
  CLAUDE.md skip-gracefully rule is for *external* toolchains; the fake is our own
  package. `subprocess.Popen` resolves a bare `binary` via the PATH in the `env=`
  it is given, and `project_child_env()` inherits from `os.environ`
  (`host_runner.py:2109-2122`), so the prepend reaches the spawn.
- **Never use `sys.executable` (or any interpreter) as `binary`.** Its basename
  would join `HOST_BINARY_NAMES` (`host_runner.py:2028-2030`) and the live-spawn
  guard would then fail every Python subprocess in the suite.
- **The live-spawn guard needs a carve-out for `ll-fake-host`.** The guard
  (`scripts/tests/conftest.py:_match_host_binary` `:237-255`) fails any spawn whose
  `argv[0]` basename is in `HOST_BINARY_NAMES`; the fake's basename joins that set
  by construction. Add the carve-out (alongside the existing `--version` carve-out)
  — it is model-free and costs nothing, which is the guard's whole rationale.
  **Derive it, don't hard-code it**: the carve-out reads
  `host_runner.TEST_ONLY_BINARIES` (below), not the literal `"ll-fake-host"`, so the
  second test-only runner (ENH-3459) rides the same rule with no conftest edit.
  Extend `scripts/tests/test_conftest_cap.py::TestNoLiveHostCLIGuard`
  (`:281-300`) with the four-shape pattern: fake basename returns None; real basename
  still returns a tuple; `--version` carve-out preserved; non-host basename unaffected.
- **One constant names every test-only registry entry.** Add to `host_runner.py`,
  next to `_HOST_RUNNER_REGISTRY`:

  ```python
  # Registry keys that exist for the test suite, not for users. Every drift
  # gate that counts or enumerates "real" hosts subtracts this set; the
  # live-spawn guard carves out its binaries. Grows by one key per fake
  # (ENH-3459 adds the second); nothing else about the gates changes.
  TEST_ONLY_HOSTS: frozenset[str] = frozenset({"fake"})
  TEST_ONLY_BINARIES: frozenset[str] = frozenset(
      _HOST_RUNNER_REGISTRY[k]().describe_capabilities().binary for k in TEST_ONLY_HOSTS
  )
  ```

  Consumers: the guard carve-out (above); the binary-count test (Wiring); a new
  `assert TEST_ONLY_HOSTS.isdisjoint(k for k, _ in _PROBE_ORDER)` test next to the
  OpenCode not-probed test (`test_host_runner.py:1073-1078`); `HOST_COMPATIBILITY.md`
  prose that enumerates real runners. The tier-table gate
  (`test_wiring_guides_and_meta.py:381-392`) keeps asserting strict equality against
  the registry — the doc gets a row per fake, flagged test-only, because that table
  is where a maintainer looks. Export both names from `__all__` and mirror in
  `scripts/little_loops/__init__.py`. This is the ENH-3460 collapse: with the
  constant in place, the second entry's drift sync is one key plus doc rows.

## Directives Language

**Vocabulary = the wire events the consumer dispatches on, nothing else.** The
consumer at `subprocess_utils.py:628-719` branches on `event.get("type")` ∈
`{"system"(subtype "init"), "assistant", "result", "turn.completed"}` and treats
anything else (including non-JSON lines) as raw stdout. FSM envelope constants
(`HOST_PRESSURE_ABORT_EVENT`, `action_complete`, `RATE_LIMIT_EXHAUSTED_EVENT`, …)
are **not** wire events; they are produced by the FSM after the stream is consumed
and must not appear in the grammar.

One directive per line; blank lines and `#` comments skipped. The script block is
the lines between a `@@fake` line and a `@@end` line, so a real prompt can precede
it; everything outside the fence is ignored. (Rejected: "every line starting with
`@`" — prompts routinely contain `@path/to/file` mentions, which would parse as
malformed directives.) Malformed directives **raise `ValueError` with the
line number** at parse time (mirrors `fsm/policy_rules.py:125-127`), not silent
skip — directive scripts are test-owned, and a silently dropped directive is a
passing test that asserts nothing.

| Directive | Emits / does | Consumer branch exercised |
|---|---|---|
| `init [model=<m>] [session=<id>]` | `{"type":"system","subtype":"init","model":…,"session_id":…}` | `:636-643` (`on_model_detected`, `on_session_id_detected`) |
| `text <str>` | `{"type":"assistant","message":{"content":[{"type":"text","text":…}]}}`; `\n` in `<str>` is unescaped to a newline (the consumer splits text on lines at `:660`, so one directive can yield several `stdout_lines`) | `:644-664` (`stdout_lines`, `stream_callback`) |
| `tool <name> [json-input]` | `assistant` event with a `tool_use` block | `:651-660` (`on_tool_call`) |
| `result [error=<msg>] [in=<n> out=<n> cache=<n>] [structured=<json>]` | `{"type":"result","subtype":"success","is_error":bool,"result":<msg or "ok">,"usage":{…}}`; `error=` sets the `error` key and `is_error:true`; `structured=` adds a `structured_output` dict — the field `run_blocking_json` reads (`host_runner.py:2530-2565`) | `:665-697` (`on_usage*`, `result_seen`) |
| `turn_completed [in=<n> out=<n> cached=<n>]` | `{"type":"turn.completed","usage":{…}}` (Codex terminal) | `:698-717` — note this branch does **not** set `result_seen`; the consumer drains to EOF, so the script must `exit` |
| `raw <str>` | stdout line written verbatim; means **non-JSON**. Valid JSON with an unrecognized `type` hits `else: continue` (`:718-719`) and is dropped, not passed through | `:720-726` (`except (json.JSONDecodeError, KeyError, TypeError): pass` fallthrough to the plain-append path) |
| `stderr <str>` | line on stderr | `stderr_lines` |
| `sleep <seconds>` | wall-clock pause before the next directive | idle-timeout (`:603`), `request_shutdown` poll (`sel.select(timeout=1.0)`) |
| `exit <code>` | flush and exit with code; must be last if present | `process.returncode` (`:766`), rate-limit detection (needs nonzero exit + 429 text) |
| `hang` | stop emitting and block (`signal.pause()` loop) until killed; must be last if present | with no terminal before it: wall-clock timeout (`:592`) or idle timeout (`:603`). **After** a terminal: the post-stream-close grace kill (`:743-751`) — see discipline below |

**Terminal-event discipline is enforced in the executable, not the runner:** at
most one of `result`/`turn_completed`; nothing but `exit` or `hang` may follow it.
A script that violates this fails at parse time. A script with no terminal directive
models a host that crashed or hung (paired with `exit <nonzero>` or `hang`).

**`hang` after a terminal is how the grace-kill path is reached.** The
`post_stream_close_grace_seconds` wait (`subprocess_utils.py:743-751`) is entered
only after `result_seen` breaks the loop (`:734`) or the pipes hit EOF; a bare
`hang` never gets there — it sits in `sel.select` until the wall-clock or idle
timeout fires. `result` then `hang` models a host that reported its turn and then
lingered with the pipes open (the BUG-2718 background-task shape), which is what the
grace kill exists for. Tests pass a small `post_stream_close_grace_seconds` (the
default is 300).

**Flush after every line.** `emit` writes each stdout/stderr line with
`flush=True`. With a pipe on stdout, Python block-buffers by default: `text` before
`sleep` would never reach the consumer until exit, the idle-timeout scenario would
observe no output before the kill, and SIGKILL on `hang` would discard everything
still buffered.

**stdout and stderr are separate pipes.** The consumer's `sel.select` sees them in
arrival order, which is not deterministic across two pipes. Tests assert `stderr`
*content*, never its position relative to stdout lines.

**Abort semantics.** There is no abort event on the wire. "Abort mid-turn" is one
of: (a) the test calls `request_shutdown()` (`subprocess_utils.py:323-335`) while the
fake is inside a `sleep`, and asserts `TimeoutExpired(output="interrupted")` plus
process-group kill — fire it from the `stream_callback` on the first `text` line, not
from a timer thread: the loop checks `_shutdown_event` at the top of every iteration
(`:581`), so a callback-triggered shutdown is deterministic and needs no sleeps in
the test; (b) `exit <nonzero>` before any terminal (host died);
(c) `result error=…` (host reported failure, terminal still last).
"Recovery after failed start" is `stderr <msg>` + `exit 1` with no `init`.

Scope the grammar to this table. A language that can express every possible host
behavior is a second harness to maintain; add a directive only when a consumer
branch needs it.

## Expected Behavior

- `FakeHostRunner` registered as `"fake"` in `_HOST_RUNNER_REGISTRY`, absent from
  `_PROBE_ORDER` (OpenCodeRunner precedent, `host_runner.py:1033-1042`), resolvable
  via `resolve_host_named("fake")` or `LL_HOST_CLI=fake`.
- `FakeHostRunner.__init__(capabilities: HostCapabilities | None = None)`; the
  override flows into `invocation.capabilities` on every `build_*` call so
  capability-gated consumers (`_structured_output_args`, `host_runner.py:2365-2383`)
  read the per-test profile. Default profile: `streaming=True`, everything else
  `False`. No new capability type — `HostCapabilities` is already a frozen dataclass.
- `build_streaming` accepts the full Protocol kwarg set explicitly (not `**_`), calls
  `_apply_automation_env` (`host_runner.py:2203-2220`) like every real runner, and
  forwards `prompt` verbatim so the directives reach the executable. **The prompt is
  the last element of `args` on every `build_*` method**, and `main()` locates it
  as *the argv element containing the `@@fake` fence*, falling back to `argv[-1]`
  only when no element does. Bare `argv[-1]` is not enough: `_structured_output_args`
  (`host_runner.py:2376`) appends `["--json-schema", <json>]` *after* the runner's
  args under `structured_output=True`, so through the real `run_blocking_json`
  path `argv[-1]` is the schema, not the prompt (ENH-3459's composition case
  exercises exactly that path; amended 2026-09-12).
- `build_blocking_json` returns the same shape of invocation; the executable has no
  blocking mode. `run_blocking_json` (`host_runner.py:2434-2578`) parses the last
  non-blank stdout line as the envelope and reads `structured_output`, then
  `result`, so a script ending in `result structured={"verdict":"pass"}` (or
  `result` alone, whose default `"result":"ok"` string falls to the `json.loads` /
  tag-fallback path) exercises it end-to-end. The no-script default emission
  (`init`, `text`, `result`) also parses, so a plain prompt through
  `run_blocking_json` does not raise. `structured_output=False` is the default
  profile, so `_structured_output_args` appends nothing; a test that overrides
  `structured_output=True` asserts the `--json-schema` flag lands in argv (argv
  fact only — the executable ignores it).
- **Capability overrides reach `build_*` only through direct construction.**
  `resolve_host()` instantiates `runner_cls()` with no arguments
  (`host_runner.py:2323, :2334`), so `run_claude_command` (which calls
  `resolve_host()` itself, `subprocess_utils.py:516`) always gets the default
  profile. The executable never sees capabilities either — what it emits is decided
  by the script alone. Consequence: capability flags are testable as **argv facts**
  on a directly-built invocation, never as stream facts through the executor. No
  env-var side channel for capabilities (rejected: it would be a second way to
  configure the fake, and nothing in the executor reads a flag).
- `describe_capabilities()` returns `CapabilityReport(host="fake", binary="ll-fake-host", …)`.
- Deterministic, model-free, runs in the default suite with no env gate.

## Use Case

A loop-run author needs to assert that an idle-timeout mid-stream followed by a
retry actually kills the first process group and re-invokes. They write a prompt
whose script block is `init`, `text working`, `sleep 5`, `result` with
`automation.idle_timeout=1`, assert `TimeoutExpired(output="idle_timeout")`, then a
second prompt with `init`, `text done`, `result` and assert the retry completes —
in under ten seconds, no model, in the default suite.

## Acceptance Criteria

- `FakeHostRunner` is registered as `"fake"` in `_HOST_RUNNER_REGISTRY`, not in
  `_PROBE_ORDER`, and `isinstance(FakeHostRunner(), HostRunner)` holds.
- `ll-fake-host` is a console script in `scripts/pyproject.toml`; running it with a
  prompt containing a script block emits exactly the scripted stream-JSON and exit
  code; a prompt with no script block emits `init` (with `model` and `session_id`),
  one `text`, `result` (with `usage` and a `result` string), exit 0 — every default
  event carries the fields that fire a consumer callback.
- `scripts/tests/conftest.py` prepends `sysconfig.get_path("scripts")` to PATH at
  session start; no test skips on a missing `ll-fake-host` — the smoke test fails
  with an install-hint message instead.
- Every directive in the table above is implemented; the parser rejects unknown
  directives and terminal-discipline violations with `ValueError` naming the line;
  `hang` is accepted after a terminal; every emitted line is flushed.
- `run_claude_command` (unpatched, real Popen) driven against the fake's default
  emission produces the expected `CompletedProcess` (exit 0, `stdout` = the text
  line, `on_model_detected` / `on_session_id_detected` / `on_usage_detailed` /
  `on_result_seen(True)` all fired). This single end-to-end case proves the seam;
  **the failure, timeout, abort and grace-kill scenarios are owned by FEAT-3455's
  Tier 2**, not duplicated here.
- The live-spawn guard carve-out is derived from `TEST_ONLY_BINARIES` (no
  `"ll-fake-host"` literal in conftest) and is regression-tested in
  `test_conftest_cap.py::TestNoLiveHostCLIGuard`.
- `TEST_ONLY_HOSTS == {"fake"}` and `TEST_ONLY_BINARIES == {"ll-fake-host"}` are
  exported from `host_runner` and `little_loops`; `TEST_ONLY_HOSTS` is disjoint from
  `_PROBE_ORDER` keys (tested); `HOST_BINARY_NAMES - TEST_ONLY_BINARIES` equals the
  eight real basenames (tested, count-free test name).
- Per-test capability override propagates to `invocation.capabilities` on all five
  `build_*` methods (direct construction only; see Expected Behavior).
- The prompt is `args[-1]` on all five `build_*` methods (tested).
- Parser, executable smoke, and the single end-to-end case live under the unit
  suite with no `conformance` marker; FEAT-3455 owns the scenario matrix and the
  conformance-suite integration.
- All drift gates tripped by the ninth registry entry are updated (see Wiring).

## Behavior Parity

- `_remediation_hint()` (`host_runner.py:2283-2289`): today a static string naming
  eight hosts and seven binaries. After: the same sentence shape, host list derived
  from `sorted(set(_HOST_RUNNER_REGISTRY) - TEST_ONLY_HOSTS)` and binary list from
  `sorted(HOST_BINARY_NAMES - TEST_ONLY_BINARIES)`. For the eight real hosts the
  rendered text is byte-identical to today's (pin with a test); fakes never appear.
- Live-spawn guard: every existing real-host match and the `--version` carve-out
  behave exactly as before; the only new behavior is a `None` (allow) for
  `TEST_ONLY_BINARIES` basenames.
- `test_has_all_eight_known_binaries` → count-free split; the eight-real-basename
  assertion is preserved verbatim as the left-hand side of the subtraction.

## Integration Map

### Files to Modify
- `scripts/little_loops/fake_host.py` (new) — `parse_directives(prompt) -> DirectivesScript`, `main()` entry point.
- `scripts/little_loops/host_runner.py` — add `FakeHostRunner`; registry entry; `TEST_ONLY_HOSTS` / `TEST_ONLY_BINARIES` constants (Design Decision above); `_remediation_hint()` (`:2283-2289`) replaces the static eight-host literal with `sorted(set(_HOST_RUNNER_REGISTRY) - TEST_ONLY_HOSTS)` — users should not be told to set `LL_HOST_CLI=fake` (ENH-3460 needs nothing here for the second fake).
- `scripts/pyproject.toml` `[project.scripts]` (`:74+`) — `ll-fake-host = "little_loops.fake_host:main"`.
- `scripts/tests/conftest.py:_match_host_binary` (`:237-255`) — carve-out `if binary in TEST_ONLY_BINARIES: return None`, imported from `host_runner` next to the existing `HOST_BINARY_NAMES` import.
- `scripts/tests/conftest.py` — `pytest_sessionstart` hook prepending `sysconfig.get_path("scripts")` to `os.environ["PATH"]` (idempotent; no-op if already first). Under xdist each worker runs its own sessionstart, so the prepend lands in every worker process.
- `scripts/little_loops/__init__.py` — re-export `FakeHostRunner`, `TEST_ONLY_HOSTS`, `TEST_ONLY_BINARIES` alongside `HostInvocation` (`:33, :38, :100`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:422-771` — `run_claude_command`; the consumer every directive targets. Not modified.
- `scripts/little_loops/fsm/runners.py:249` — `DefaultActionRunner.run` calls `run_claude_command`; FSM-level tests can set `LL_HOST_CLI=fake` and drive real actions.
- `scripts/little_loops/cli/verify_host_map.py:_check_runtime_contradiction` (`:100-128`) intersects `HOST_CAPABILITIES` with the registry — a fake with no `HOST_CAPABILITIES` entry is simply not checked. **No `HostCapabilityEntry` is required.** `_check_emitter_agreement` (`:131-188`) only reads `HOST_CAPABILITIES` and is likewise unaffected.
- `scripts/little_loops/init/cli.py:102-104, :270-274` — validates `LL_HOST_CLI` against the registry; `fake` becomes accepted. Acceptable; not user-facing in docs.

### Drift gates tripped by the ninth registry entry (Wiring)
- `scripts/tests/test_host_runner.py:2359-2371` `test_has_all_eight_known_binaries` — rename to the count-free `test_real_binaries_are_the_eight_known_hosts` asserting `HOST_BINARY_NAMES - TEST_ONLY_BINARIES == {…eight…}`, plus a sibling `test_test_only_binaries_are_registered` asserting `TEST_ONLY_BINARIES <= HOST_BINARY_NAMES`. Number-in-name tests break on every fake; the subtraction does not. The registry-derived companion at `:2348-2357` is invariant.
- `scripts/tests/test_host_runner.py:1073-1078` (OpenCode not-probed precedent) — add `test_test_only_hosts_are_never_probed`: `TEST_ONLY_HOSTS.isdisjoint(k for k, _ in _PROBE_ORDER)`.
- `scripts/tests/test_wiring_guides_and_meta.py:381-392` `test_host_tier_table_matches_runner_registry` — add a `fake` row to `docs/reference/HOST_COMPATIBILITY.md` `## Host tiers` (`:16-31`) marked as a test fixture. The gate keeps strict equality; the doc row is where a maintainer looks. (Rejected: a test-side exclusion — it would hide the fake from the one table that lists every `LL_HOST_CLI` value the registry accepts.)
- `scripts/tests/conformance/test_host_conformance.py:_HOST_BINARY` (`:52-61`) — add `"fake": "ll-fake-host"` so the constructability test's PATH probe has an entry for it; with the session-start PATH prepend the probe finds it and the test runs rather than skipping.
- `scripts/tests/test_host_runner.py` cross-runner parametrize sites (`:85, :92, :285, :300, :363, :1949, :2216-2244`) — registry-derived sites auto-extend; explicit-list sites need the `("fake", FakeHostRunner)` row only where the fake's behavior is meant to match (automation env: yes; argv-shape checks: no).
- `docs/reference/HOST_COMPATIBILITY.md:462-472, :491-507` — "eight concrete runners" prose and `[^orch]` footnote: keep "eight" for the real runners and add one sentence that registry keys in `TEST_ONLY_HOSTS` are test fixtures outside the tier semantics. Do not enumerate fakes by name here (ENH-3459 adds a second; the sentence must not need editing).
- `docs/ARCHITECTURE.md:857-875` — Host Runner Layer table footnote.
- `docs/development/TESTING.md:1075-1088` — live-spawn guard docs: document the `ll-fake-host` carve-out and why it is safe.
- `docs/reference/API.md` `## little_loops.host_runner` — "Concrete runners" table row; new `## little_loops.fake_host` section with the directive table.
- `docs/reference/CLI.md` — `ll-fake-host` entry (marked test-only).

### Conventions in Force
- `name` is a class attribute; class-level `capabilities = HostCapabilities(...)`; `HostCapabilities` and `HostInvocation` are `frozen=True` (`host_runner.py:288-313`; `test_host_runner.py:1869-1879`).
- `@runtime_checkable HostRunner` is matched structurally; the canonical test is `assert isinstance(Runner(), HostRunner)` (8 sites, e.g. `test_host_runner.py:679, 1024, 1105`).
- All `build_*` methods are keyword-only. `CapturingRunner` (`test_runner_spec.py:44-58`) exists because `**_: object` absorption silently dropped `automation=`; declare kwargs explicitly.
- `describe_capabilities().binary` feeds `HOST_BINARY_NAMES`; pick a basename that collides with nothing real (`ll-fake-host`).
- Registered-but-not-probed runner precedent: OpenCodeRunner (`host_runner.py:1033-1042`; `test_host_runner.py:1073-1078`).
- Tiny-DSL parsing precedents: `env_file.py:38-62` (silent skip — rejected here), `fsm/policy_rules.py:98-160` (`ValueError` with line number — adopted).
- Scripted-stream precedent on the consumer side: `test_subprocess_utils.py:2589-2720` (`_NeverEOFStdout`, `TestRunClaudeCommandResultBreak`); reuse its assertions (`read_past_result`, `"LEAKED"` sentinel) as the shape for the fake's terminal-discipline tests.

### Tests
- `scripts/tests/test_fake_host.py` (new) — parser unit tests (each directive, comments, `@@fake`/`@@end` fence, `\n` unescape in `text`, `structured=` on `result`, `ValueError` cases, terminal discipline incl. `hang`-after-terminal accepted and `text`-after-terminal rejected), `emit` in-process tests with `io.StringIO` asserting a flush per line, executable smoke via `subprocess.run(["ll-fake-host", prompt])` (fails with an install hint if `shutil.which("ll-fake-host")` is None), and the single `run_claude_command` end-to-end case in the AC. The seven-scenario matrix is FEAT-3455's.
- `scripts/tests/test_conftest_cap.py` — the session-start PATH prepend is covered by asserting `sysconfig.get_path("scripts")` is the first PATH entry once the session is up.
- `scripts/tests/test_host_runner.py::TestFakeHostRunner` — per-runner class following `TestOpenCodeRunner` (`:1058-1106`): argv shape, `_apply_automation_env` called, capability override on all five `build_*`, Protocol check, not in `_PROBE_ORDER`.
- `scripts/tests/test_conftest_cap.py::TestNoLiveHostCLIGuard` — four-shape carve-out tests.
- `scripts/tests/conformance/test_host_conformance.py` — the existing constructability test auto-extends to `fake`; the behavioral tier is FEAT-3455's.

### Configuration
- None. `LL_HOST_CLI=fake` works after registration.

## Program Design

### Types
- `Directive`: `(kind: str, args: dict[str, str], lineno: int)`.
- `DirectivesScript`: `(directives: list[Directive], terminal_index: int | None, exit_code: int)`; construction validates terminal discipline (at most one terminal; only `exit`/`hang` after it; `exit`/`hang` last).
- `DEFAULT_SCRIPT`: the no-fence emission — `init model=fake-model session=fake-session`, `text ok`, `result in=1 out=1` — every event carrying its callback-triggering fields.

### Signatures
- `parse_directives(prompt: str) -> DirectivesScript` — raises `ValueError(f"line {n}: …")`; returns `DEFAULT_SCRIPT` when no `@@fake` fence is present.
- `emit(script: DirectivesScript, *, stdout, stderr) -> int` — writes events with `flush=True` per line, sleeps, blocks on `hang`, returns exit code. Separated from `main()` so tests can drive it in-process with `io.StringIO`.
- `main(argv: list[str] | None = None) -> int` — prompt is the argv element containing the `@@fake` fence, else `argv[-1]`; ignores every other element so any argv shape the runner emits is accepted, including flags the executor appends after the prompt (`--json-schema <json>`).
- `FakeHostRunner(capabilities: HostCapabilities | None = None)`; `name = "fake"`; four `build_*` methods (`build_streaming`, `build_blocking_json`, `build_version_check`, `build_detached` — the full Protocol set); `describe_capabilities()`.

### Call Path
`resolve_host_named("fake")` → `FakeHostRunner.build_streaming(prompt=…)` → `HostInvocation(binary="ll-fake-host", args=["-p", prompt, …])` → `run_claude_command` spawns it via `subprocess.Popen` (`subprocess_utils.py:526`) → `ll-fake-host` `main()` → `parse_directives` → `emit` → consumer loop `:628-735` → `CompletedProcess`.

## Implementation Steps

1. `fake_host.py`: `Directive`, `DirectivesScript`, `parse_directives`, `emit`, `main`; parser tests first (TDD).
2. Console script entry in `scripts/pyproject.toml`; reinstall editable; smoke test.
3. `FakeHostRunner` in `host_runner.py` with capability override and `_apply_automation_env`; registry entry; `TEST_ONLY_HOSTS` / `TEST_ONLY_BINARIES` constants + `__all__` / package re-export; `_remediation_hint()` derived from the registry minus `TEST_ONLY_HOSTS`.
4. Live-spawn guard carve-out derived from `TEST_ONLY_BINARIES` + four-shape regression tests; not-probed disjointness test; `pytest_sessionstart` PATH prepend.
5. Drive `run_claude_command` unpatched against the fake's default emission (the one end-to-end case); confirm `run_blocking_json` parses a `result structured=…` script.
6. Drift-gate sync: count-free binary tests, tier table row, `_HOST_BINARY`, cross-runner parametrize rows, docs (prose refers to `TEST_ONLY_HOSTS`, never enumerates fakes).
7. `ll-verify-host-map`, `python -m pytest scripts/tests/`, mypy, ruff all clean.

## Impact

- **Priority (P2)**: blocks FEAT-3455 and ENH-3459; first model-free coverage of the real spawn/exit/timeout paths.
- **Effort**: medium — one ~300-line module, one runner class, guard carve-out, drift sync.
- **Risk**: low — additive; the executor and every real runner are untouched. The one shared edit (`_remediation_hint`) is a pure drift fix.

## Status

**Open** | Created: 2026-09-11 | Priority: P2

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md#little_loopshost_runner` | `HostRunner` Protocol surface the fake must satisfy |
| `docs/development/TESTING.md` § live-spawn guard | The guard the fake's basename must be carved out of |
| `docs/development/CONFORMANCE.md` | Conformance harness the fake becomes a target for (FEAT-3455) |
| `.claude/CLAUDE.md` § Host CLI Abstraction | `resolve_host()` is the only entry point; the fake registers there |

## Verification Notes

Verdict at time of check: **VALID** (correction below applied in the same pass,
so the issue as it now reads is up to date — this section is a record of what
was wrong and fixed, not an outstanding action item).

- **Checked**: every `file:line` citation in Current Behavior, Design Decision,
  Directives Language, Expected Behavior, Behavior Parity, and Integration Map
  against the working tree. All resolved to the claimed function/class/constant,
  most exactly and the rest within 1-2 lines of harmless drift (illustrative,
  not load-bearing): `run_claude_command` (`subprocess_utils.py:422`, cited
  `422-771`), `Popen` call (`:534`, cited `526-536`), `request_shutdown`
  (`:323`, cited `323-335`), the idle-timeout check (`:603`, exact),
  `event.get("type")` dispatch and its per-branch sub-citations (`:630` for the
  dispatch itself; `init` at `:631-638` vs. cited `636-643`; `assistant`/`text`
  at `:639-664` vs. cited `644-664`; `tool_use` at `:647-657` vs. cited
  `651-660`; `result` at `:665-697`, exact; `turn.completed` at `:698-717` vs.
  cited `698-714`), `_match_host_binary` (`conftest.py:237-255`, exact, and its
  four-shape carve-out tests at `:281-300`, exact), `_remediation_hint`
  (`host_runner.py:2283`, cited `2283-2289`), `_apply_automation_env`
  (`host_runner.py:2203`, exact), `HOST_BINARY_NAMES` (`host_runner.py:2028`,
  exact), `_structured_output_args` (`host_runner.py:2365`, exact),
  `HostRunner`/`HostCapabilities`/`HostInvocation` (`:395`/`:289`/`:317`, cited
  `394-492`/`288-313`), `OpenCodeRunner` and its not-probed precedent
  (`host_runner.py:1033`, `test_host_runner.py:1073-1078`, exact),
  `test_has_all_eight_known_binaries` and its registry-derived sibling
  (`test_host_runner.py:2348-2371`, exact), `test_host_tier_table_matches_runner_registry`
  (`test_wiring_guides_and_meta.py:381-392`, exact, `[BUG-3186]` message
  confirmed), `CapturingRunner` (`test_runner_spec.py:44-58`), `parse_env_file`
  silent-skip precedent (`env_file.py:38-62`), `parse_rules` /
  `ValueError`-with-lineno convention (`fsm/policy_rules.py:98`, docstring
  `Raises:` block at `125-127`), `_NeverEOFStdout` /
  `TestRunClaudeCommandResultBreak` (`test_subprocess_utils.py:2589-2720`,
  exact), and `[project.scripts]` (`scripts/pyproject.toml:74`, exact).
  Graph-corroborated via `ll-code callers-of run_claude_command`:
  `fsm/runners.py:249 DefaultActionRunner::run` is an exact hit, confirming the
  Dependent Files claim without relying on grep alone.
- **Fixed**: the `raw <str>` directive's "Consumer branch exercised" cell cited
  `:716-719`. That span is actually the tail of the `turn.completed` branch
  plus the `else: continue` catch-all for a recognized-but-unhandled JSON
  `"type"` — which *drops* the line, the opposite of "passthrough." The real
  non-JSON passthrough is the `except (json.JSONDecodeError, KeyError,
  TypeError): pass` fallthrough into the plain-append code at `:720-726`.
  Corrected the table cell in place to cite `:720-726` with the mechanism
  named explicitly.
- **Proposal-vs-code check**: this issue uses `## Design Decision` /
  `## Expected Behavior` / `## Integration Map` / `## Program Design` in place
  of a `## Proposed Solution` section, so the trace was applied to those
  sections instead. The "fake must be a real executable" design decision is
  externally corroborated, not just self-consistent: the in-process spike this
  issue's cluster grew out of (`scripts/tests/spike/host_compose/
  {fakes.py,executor_shim.py,test_host_compose.py}`) still exists on disk,
  unpromoted, exactly as ENH-3459 (a `relates_to` sibling) describes — ENH-3459's
  "Decisions" §1 explicitly states the spike's `executor_shim.py`/
  `_wrap_invocation` in-process proxy is "retired, not promoted" precisely
  because it never touches the real `subprocess.Popen` path, and instead reuses
  FEAT-3454's real-executable `ll-fake-host` design. No inconsistency between
  this issue's design and either the spike's current shape or the sibling issue
  that supersedes it. No `PROPOSAL_UNSOUND` finding.
  `fake_host.py`, `FakeHostRunner`, `TEST_ONLY_HOSTS`, `TEST_ONLY_BINARIES`, and
  the `ll-fake-host` console-script entry were confirmed absent from the tree —
  correct, since this issue proposes creating them and is `status: open`.
- **Evidence-quote check**: `ll-verify-evidence` on this file returned
  `{"ok": true, "count": 0, "findings": []}` — clean, no `EVIDENCE_UNVERIFIED`.
- **Decisions log**: `ll-issues decisions list --type rule --enforcement
  required --active-only` returned no entries — clean pass, no
  `DECISIONS_VIOLATION` possible.
- **Dependency references**: this issue declares no `blocked_by`/`depends_on`
  of its own; its `relates_to: [FEAT-3455, ENH-3459, ENH-3460]` all resolve to
  real, open issues via `ll-issues list --json --status all`, with a coherent,
  acyclic ordering elsewhere in the cluster: `FEAT-3455.depends_on: FEAT-3454`;
  `ENH-3459.blocked_by: [FEAT-3454, FEAT-3455]`; `ENH-3460.blocked_by:
  [ENH-3459]`. The cluster's common ancestor, ENH-3456, is `done` (decomposed
  into ENH-3459 / ENH-3460, not into FEAT-3454) — no broken refs, no cycles.
- **Graph tools**: `ll-code --json status` reports provider=`codegraph`,
  available=true, freshness=`fresh`; used for the `callers-of` corroboration
  above. No "never called" claims in this issue to check further.
- **Regression check**: skipped — no completed issue matches this feature; it
  is net-new, unimplemented work.

## Session Log
- `/ll:confidence-check` - 2026-09-12T18:34:13 - `4c64a9f3-3fe1-44fa-8a00-bbded475e3ef.jsonl`
- Manual review (ENH-3459 cross-check) - 2026-09-12 - `main()` prompt location changed from bare `argv[-1]` to fence-locates-prompt with `argv[-1]` fallback, because `_structured_output_args` appends `--json-schema <json>` after the prompt; "five `build_*`" corrected to four
- Manual pre-implementation review - 2026-09-12 - PATH prepend + fail-not-skip (CI conformance job never had `.venv/bin` on PATH); `hang` re-modeled (grace kill needs `result` + `hang`); `@@fake`/`@@end` fence decided (`@`-prefix collides with file mentions); `result structured=` for `run_blocking_json`; flush-per-line; stderr-interleaving caveat; `request_shutdown` from `stream_callback`; prompt-last contract; capability override is direct-construction-only; seven-scenario matrix moved to FEAT-3455 (was duplicated)
- `/ll:verify-issues` - 2026-09-12T17:14:12 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- `/ll:verify-issues` - 2026-09-12T17:12:07 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- `/ll:verify-issues` - 2026-09-12T17:03:59 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- Manual review rewrite - 2026-09-12 - folded execution-seam decision (real executable), wire-only vocabulary, abort semantics, guard carve-out; dropped stale FSM-constant guidance and `FakeHostCapabilities`
- `/ll:confidence-check` - 2026-09-12T06:43:59 - `535817ba-f87e-4270-be40-3b5e78ddef13.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-12T06:37:39 - `fd455bb5-43a5-4cb2-ab0e-353cbf4886b2.jsonl`
- `/ll:verify-issues` - 2026-09-12T06:34:45 - `062d49e4-2eda-402d-b2d9-86b1a4b53aa4.jsonl`
- `/ll:wire-issue` - 2026-09-12T06:29:51 - `f67590da-6478-467b-b9ac-c3f6855d5bad.jsonl`
- `/ll:refine-issue` - 2026-09-12T06:14:52 - `d07828f4-6645-496e-92fa-00556a005640.jsonl`
- `/ll:refine-issue` - 2026-09-12T04:47:19 - `63ed2222-46d0-4175-b050-49b2a402d5c5.jsonl`
- `/ll:refine-issue` - 2026-09-12T04:06:04 - `b7b7f9e7-8f55-4db9-84ab-f495556f1242.jsonl`
- `/ll:format-issue` - 2026-09-12T03:49:49 - `8c6cc97d-774e-45fd-be34-14d7ed48d65c.jsonl`
