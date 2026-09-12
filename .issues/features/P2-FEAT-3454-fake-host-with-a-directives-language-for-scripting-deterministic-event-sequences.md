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
  CI perform) puts it on PATH.
- **Never use `sys.executable` (or any interpreter) as `binary`.** Its basename
  would join `HOST_BINARY_NAMES` (`host_runner.py:2028-2030`) and the live-spawn
  guard would then fail every Python subprocess in the suite.
- **The live-spawn guard needs a carve-out for `ll-fake-host`.** The guard
  (`scripts/tests/conftest.py:_match_host_binary` `:237-255`) fails any spawn whose
  `argv[0]` basename is in `HOST_BINARY_NAMES`; the fake's basename joins that set
  by construction. Add `ll-fake-host` to the carve-out (alongside the existing
  `--version` carve-out) — it is model-free and costs nothing, which is the guard's
  whole rationale. Extend `scripts/tests/test_conftest_cap.py::TestNoLiveHostCLIGuard`
  (`:281-300`) with the four-shape pattern: fake basename returns None; real basename
  still returns a tuple; `--version` carve-out preserved; non-host basename unaffected.

## Directives Language

**Vocabulary = the wire events the consumer dispatches on, nothing else.** The
consumer at `subprocess_utils.py:628-719` branches on `event.get("type")` ∈
`{"system"(subtype "init"), "assistant", "result", "turn.completed"}` and treats
anything else (including non-JSON lines) as raw stdout. FSM envelope constants
(`HOST_PRESSURE_ABORT_EVENT`, `action_complete`, `RATE_LIMIT_EXHAUSTED_EVENT`, …)
are **not** wire events; they are produced by the FSM after the stream is consumed
and must not appear in the grammar.

One directive per line; blank lines and `#` comments skipped; the script block is
delimited so a real prompt can precede it (e.g. lines between `@@fake` and `@@end`,
or every line starting with `@`). Malformed directives **raise `ValueError` with the
line number** at parse time (mirrors `fsm/policy_rules.py:125-127`), not silent
skip — directive scripts are test-owned, and a silently dropped directive is a
passing test that asserts nothing.

| Directive | Emits / does | Consumer branch exercised |
|---|---|---|
| `init [model=<m>] [session=<id>]` | `{"type":"system","subtype":"init","model":…,"session_id":…}` | `:636-643` (`on_model_detected`, `on_session_id_detected`) |
| `text <str>` | `{"type":"assistant","message":{"content":[{"type":"text","text":…}]}}` | `:644-664` (`stdout_lines`, `stream_callback`) |
| `tool <name> [json-input]` | `assistant` event with a `tool_use` block | `:651-660` (`on_tool_call`) |
| `result [error=<msg>] [in=<n> out=<n> cache=<n>]` | `{"type":"result","is_error":bool,"usage":{…}}` | `:665-697` (`on_usage*`, `result_seen`) |
| `turn_completed [in=<n> out=<n> cached=<n>]` | `{"type":"turn.completed","usage":{…}}` (Codex terminal) | `:698-714` |
| `raw <str>` | non-JSON stdout line | `:716-719` passthrough |
| `stderr <str>` | line on stderr | `stderr_lines` |
| `sleep <seconds>` | wall-clock pause before the next directive | idle-timeout (`:603`), `request_shutdown` poll (`sel.select(timeout=1.0)`) |
| `exit <code>` | flush and exit with code; must be last if present | `process.returncode` (`:766`), rate-limit detection (needs nonzero exit + 429 text) |
| `hang` | never emit a terminal; block until killed | `_kill_process_group` after `post_stream_close_grace_seconds` |

**Terminal-event discipline is enforced in the executable, not the runner:** at
most one of `result`/`turn_completed`; nothing but `exit` may follow it. A script
that violates this fails at parse time. A script with no terminal directive models a
host that crashed or hung (paired with `exit <nonzero>` or `hang`).

**Abort semantics.** There is no abort event on the wire. "Abort mid-turn" is one
of: (a) the test calls `request_shutdown()` (`subprocess_utils.py:323-335`) while the
fake is inside a `sleep`, and asserts `TimeoutExpired(output="interrupted")` plus
process-group kill; (b) `exit <nonzero>` before any terminal (host died);
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
  forwards `prompt` verbatim so the directives reach the executable.
- `build_blocking_json` returns an invocation whose executable prints the scripted
  JSON blob (a `text` directive's payload) so `run_blocking_json` is also testable.
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
  code; a prompt with no script block emits `init`, one `text`, `result`, exit 0.
- Every directive in the table above is implemented; the parser rejects unknown
  directives and terminal-discipline violations with `ValueError` naming the line.
- `run_claude_command` (unpatched, real Popen) driven against the fake produces the
  expected `CompletedProcess` for: ordered happy path; `result error=`; exit-nonzero
  before terminal; `stderr`+`exit 1` failed start; idle timeout via `sleep`;
  `request_shutdown()` during `sleep`; `hang` + grace-period kill.
- The live-spawn guard carve-out for `ll-fake-host` exists and is regression-tested
  in `test_conftest_cap.py::TestNoLiveHostCLIGuard`.
- Per-test capability override propagates to `invocation.capabilities` on all five
  `build_*` methods.
- Behavioral tests live under the unit suite (no `conformance` marker required for
  the fake-only tests; FEAT-3455 owns the conformance-suite integration).
- All drift gates tripped by the ninth registry entry are updated (see Wiring).

## Integration Map

### Files to Modify
- `scripts/little_loops/fake_host.py` (new) — `parse_directives(prompt) -> DirectivesScript`, `main()` entry point.
- `scripts/little_loops/host_runner.py` — add `FakeHostRunner`; registry entry; `_remediation_hint()` (`:2283-2289`) replaces the static eight-host literal with `sorted(_HOST_RUNNER_REGISTRY)` (ENH-3460 tracks the same drift for the second fake; do it once here).
- `scripts/pyproject.toml` `[project.scripts]` (`:74+`) — `ll-fake-host = "little_loops.fake_host:main"`.
- `scripts/tests/conftest.py:_match_host_binary` (`:237-255`) — carve-out for basename `ll-fake-host`.
- `scripts/little_loops/__init__.py` — re-export `FakeHostRunner` alongside `HostInvocation` (`:33, :38, :100`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:422-771` — `run_claude_command`; the consumer every directive targets. Not modified.
- `scripts/little_loops/fsm/runners.py:249` — `DefaultActionRunner.run` calls `run_claude_command`; FSM-level tests can set `LL_HOST_CLI=fake` and drive real actions.
- `scripts/little_loops/cli/verify_host_map.py:_check_runtime_contradiction` (`:100-128`) intersects `HOST_CAPABILITIES` with the registry — a fake with no `HOST_CAPABILITIES` entry is simply not checked. **No `HostCapabilityEntry` is required.** `_check_emitter_agreement` (`:131-188`) only reads `HOST_CAPABILITIES` and is likewise unaffected.
- `scripts/little_loops/init/cli.py:102-104, :270-274` — validates `LL_HOST_CLI` against the registry; `fake` becomes accepted. Acceptable; not user-facing in docs.

### Drift gates tripped by the ninth registry entry (Wiring)
- `scripts/tests/test_host_runner.py:2359-2371` `test_has_all_eight_known_binaries` — rename to nine, add `"ll-fake-host"`. The registry-derived companion at `:2348-2357` is invariant.
- `scripts/tests/test_wiring_guides_and_meta.py:381-392` `test_host_tier_table_matches_runner_registry` — add a `fake` row to `docs/reference/HOST_COMPATIBILITY.md` `## Host tiers` (`:16-31`) marked as a test fixture, or add a documented exclusion in the test. Prefer the doc row: it is where a maintainer looks.
- `scripts/tests/conformance/test_host_conformance.py:_HOST_BINARY` (`:52-61`) — add `"fake": "ll-fake-host"` so the PATH probe skips cleanly when the console script is missing (non-editable installs).
- `scripts/tests/test_host_runner.py` cross-runner parametrize sites (`:85, :92, :285, :300, :363, :1949, :2216-2244`) — registry-derived sites auto-extend; explicit-list sites need the `("fake", FakeHostRunner)` row only where the fake's behavior is meant to match (automation env: yes; argv-shape checks: no).
- `docs/reference/HOST_COMPATIBILITY.md:462-472, :491-507` — "eight concrete runners" prose and `[^orch]` footnote: state that `FakeHostRunner` is a ninth, test-only entry.
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
- `scripts/tests/test_fake_host.py` (new) — parser unit tests (each directive, comments, delimiter, `ValueError` cases, terminal discipline), executable smoke via `subprocess.run(["ll-fake-host", prompt])` (skip with reason if `shutil.which("ll-fake-host")` is None), and the seven `run_claude_command` scenarios in the AC.
- `scripts/tests/test_host_runner.py::TestFakeHostRunner` — per-runner class following `TestOpenCodeRunner` (`:1058-1106`): argv shape, `_apply_automation_env` called, capability override on all five `build_*`, Protocol check, not in `_PROBE_ORDER`.
- `scripts/tests/test_conftest_cap.py::TestNoLiveHostCLIGuard` — four-shape carve-out tests.
- `scripts/tests/conformance/test_host_conformance.py` — the existing constructability test auto-extends to `fake`; the behavioral tier is FEAT-3455's.

### Configuration
- None. `LL_HOST_CLI=fake` works after registration.

## Program Design

### Types
- `Directive`: `(kind: str, args: dict[str, str], lineno: int)`.
- `DirectivesScript`: `(directives: list[Directive], terminal_index: int | None, exit_code: int)`; construction validates terminal discipline.

### Signatures
- `parse_directives(prompt: str) -> DirectivesScript` — raises `ValueError(f"line {n}: …")`.
- `emit(script: DirectivesScript, *, stdout, stderr) -> int` — writes events, sleeps, returns exit code. Separated from `main()` so tests can drive it in-process with `io.StringIO`.
- `main(argv: list[str] | None = None) -> int` — prompt is the last positional arg; ignores every other flag so any argv shape the runner emits is accepted.
- `FakeHostRunner(capabilities: HostCapabilities | None = None)`; `name = "fake"`; five `build_*` methods; `describe_capabilities()`.

### Call Path
`resolve_host_named("fake")` → `FakeHostRunner.build_streaming(prompt=…)` → `HostInvocation(binary="ll-fake-host", args=["-p", prompt, …])` → `run_claude_command` spawns it via `subprocess.Popen` (`subprocess_utils.py:526`) → `ll-fake-host` `main()` → `parse_directives` → `emit` → consumer loop `:628-735` → `CompletedProcess`.

## Implementation Steps

1. `fake_host.py`: `Directive`, `DirectivesScript`, `parse_directives`, `emit`, `main`; parser tests first (TDD).
2. Console script entry in `scripts/pyproject.toml`; reinstall editable; smoke test.
3. `FakeHostRunner` in `host_runner.py` with capability override and `_apply_automation_env`; registry entry; `_remediation_hint()` derived from the registry.
4. Live-spawn guard carve-out + four-shape regression tests.
5. Drive `run_claude_command` unpatched against the fake for the seven AC scenarios.
6. Drift-gate sync: binary-count test, tier table row, `_HOST_BINARY`, cross-runner parametrize rows, docs.
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

## Session Log
- Manual review rewrite - 2026-09-12 - folded execution-seam decision (real executable), wire-only vocabulary, abort semantics, guard carve-out; dropped stale FSM-constant guidance and `FakeHostCapabilities`
- `/ll:confidence-check` - 2026-09-12T06:43:59 - `535817ba-f87e-4270-be40-3b5e78ddef13.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-12T06:37:39 - `fd455bb5-43a5-4cb2-ab0e-353cbf4886b2.jsonl`
- `/ll:verify-issues` - 2026-09-12T06:34:45 - `062d49e4-2eda-402d-b2d9-86b1a4b53aa4.jsonl`
- `/ll:wire-issue` - 2026-09-12T06:29:51 - `f67590da-6478-467b-b9ac-c3f6855d5bad.jsonl`
- `/ll:refine-issue` - 2026-09-12T06:14:52 - `d07828f4-6645-496e-92fa-00556a005640.jsonl`
- `/ll:refine-issue` - 2026-09-12T04:47:19 - `63ed2222-46d0-4175-b050-49b2a402d5c5.jsonl`
- `/ll:refine-issue` - 2026-09-12T04:06:04 - `b7b7f9e7-8f55-4db9-84ab-f495556f1242.jsonl`
- `/ll:format-issue` - 2026-09-12T03:49:49 - `8c6cc97d-774e-45fd-be34-14d7ed48d65c.jsonl`
