# Host Conformance Harness

The conformance harness has two tiers, both parametrized over every host
registered in `_HOST_RUNNER_REGISTRY` (`scripts/little_loops/host_runner.py`)
— adding a new host requires only a registry entry, no new test code:

1. **Constructability** (`test_golden_path_invocation`) — validates that every
   registered host runner can construct valid invocations for the four
   little-loops orchestration golden paths: `ll-auto`, `ll-sprint`,
   `ll-loop`, `ll-action`. Never executes the prompt.
2. **Behavioral** (`test_golden_path_behavior` — Tier 1 — plus the
   `test_scripted_*` cases — Tier 2) — actually runs the invocation through
   `run_claude_command()` and asserts the observable stream-shape contract:
   ordering, terminal discipline, exit codes, timeout/abort behavior, and
   process-group cleanup. FEAT-3455.

Both live in `scripts/tests/conformance/test_host_conformance.py`. A third,
separate suite — the composition suite (`test_host_composition.py`) — proves
the executor is host-agnostic rather than shaped around one fake; see
"Composition suite" below.

## Tier 1: behavioral invariants (every host, happy path)

`test_golden_path_behavior[<host>]` sends one fixed prompt,
`_LIVE_PROMPT = "Reply with exactly: OK"`, and asserts invariants that hold
for any host, scripted or live:

- If the host's `_STREAM_SHAPE` row says an init event is expected, `init` is
  the first entry in the observed callback-kind sequence.
- The terminal (a `result` or `turn.completed` event) fires exactly once,
  and is the last observed kind.
- For `result`-terminal hosts, `on_result_seen(True)` fires. For
  `turn.completed`-terminal hosts (Codex), `on_result_seen(False)` fires —
  the consumer reaches EOF instead, since `turn.completed` never sets the
  internal `result_seen` flag.
- `CompletedProcess.returncode == 0`.
- `stderr`: exactly `""` for the fake. For a live host, only that no stderr
  line starts with `[result] ` (the consumer's error marker) — real CLIs
  write benign noise to stderr on a clean run (Node deprecation warnings,
  update nags, credential log lines), so exact-empty would fail on noise,
  not a contract deviation.

Runs unconditionally for the fake host (FEAT-3454's default emission,
~150ms). For every other host, Tier 1 only runs behind
`LL_HOST_CONFORMANCE_LIVE=1` — it spends real model tokens and requires host
auth, so it stays opt-in. The `_STREAM_SHAPE` table
(`test_host_conformance.py`) is gate-tested against the registry so a new
host can't land without a row.

Failure-shape and abort invariants are **not** part of Tier 1 — a golden
prompt can't make a live host fail or abort without spending tokens on a
deliberately broken run. Those are Tier 2, fake-only.

## Tier 2: scripted-exact scenarios (fake only)

The fake host's prompt carries an `@@fake` / `@@end` directive block that
scripts an exact wire sequence (see `scripts/little_loops/fake_host.py`).
Eight `test_scripted_*` cases assert the exact callback-derived observation
for: normal ordering, a `result error=` failure, exit-nonzero before any
terminal, a failed start (no `init`), an idle timeout, an abort via
`request_shutdown()` fired from inside `stream_callback`, a wall-clock
`hang`, and a `result` immediately followed by a `hang` (grace-period kill).

These never skip — FEAT-3454's session-start PATH prepend makes
`ll-fake-host` resolvable in every job, so a missing binary here is a
failure, not a skip. They run on every `python -m pytest scripts/tests/`
invocation and are not filtered out by `--conformance-host <real-host>`
(they're the suite's spawn-path regression coverage, independent of which
real host a maintainer is validating live).

On the three `TimeoutExpired` rows (idle timeout, abort, wall-clock hang),
`result_seen` is asserted as `None` — the consumer's `on_result_seen`
callback only fires on the normal-return path, never when
`run_claude_command()` raises.

## Composition suite

`scripts/tests/conformance/test_host_composition.py` (ENH-3459) drives `fake`
and `fake-minimal` — two `HostRunner` implementations sharing the
`ll-fake-host` binary but deliberately disagreeing on argv shape, `env`
population, and default `HostCapabilities` — through the **unpatched
production executor** (`run_claude_command`, `run_blocking_json`) against the
same directive script, and asserts the executor produces the same
`Observed` result for both. A single fake proves the code runs; a second,
deliberately divergent fake proves the executor is host-agnostic rather than
shaped around one fake's assumptions.

`TestExecutorTouchesOnlyAbstractInterface` and `TestRegressionGuard` pin that
mechanically via an AST walk over the `host_runner.py` and
`subprocess_utils.py` sources: the executor chain reads only the abstract
`HostRunner`/`HostInvocation` surface, with `_structured_output_args`'s
pinned `{"claude", "qwen"}` binary-literal branches as the one named
exception. `TestCompositionThroughExecutor` (the Popen-driving class) skips
when `ll-fake-host` is not on PATH (non-editable install); the AST-only
classes carry no such marker and run unconditionally in the plain unit
suite.

## Capability assertions: argv facts, not event facts

`HostCapabilities` flags (`permission_skip`, `agent_select`,
`tool_allowlist`, `structured_output`, `workspace_sandboxed`, `streaming`)
describe what a runner puts in argv, not event kinds observed on the wire.
The rule enforced:

- **Negative (unconditional):** when a flag is `False`, the corresponding
  argv marker must be absent. Under-declaring is a bug on equal footing
  with over-declaring.
- **Positive (gated):** when a flag is `True`, the argv marker is present.

`structured_output` and `streaming` are the only two flags exercisable on a
directly-constructed fake invocation (`FakeHostRunner(capabilities=...)`) —
`FakeHostRunner.build_streaming()` always returns `args=[prompt]`, so it
never threads `agent`/`tools`/`workspace_root` into argv, making a
fake-based negative *or* positive test for `permission_skip`,
`agent_select`, `tool_allowlist`, or `workspace_sandboxed` vacuous in both
directions. Those four are instead tested both directions against each real
runner's own `build_streaming()`. No stream-level assertion exists for
`streaming` — the fake executable never sees capabilities, so what it
emits is decided entirely by the script, not the flag.

## Running the Harness

```bash
# Everything: constructability + Tier 1 (fake only) + Tier 2
pytest -m conformance scripts/tests/

# Single host only (Tier 2 fake-only cases still run — see above)
pytest -m conformance --conformance-host codex scripts/tests/

# Deselect conformance from a full suite run
pytest -m "not conformance" scripts/tests/

# Live Tier 1 behavioral tier for one host with a binary on PATH and
# credentials configured — spends real tokens
LL_HOST_CONFORMANCE_LIVE=1 pytest -m conformance --conformance-host codex \
    scripts/tests/conformance/

# Composition suite: fake vs. fake-minimal through the unpatched executor,
# plus the AST-pinned interface-surface checks
pytest scripts/tests/conformance/test_host_composition.py
```

## Reading the Results

`test_golden_path_invocation[<golden-path>-<host>]` (constructability):

| Result | Meaning |
|--------|---------|
| `PASSED` | Host runner is wired; `build_streaming()` returns a valid `HostInvocation`. |
| `SKIPPED` (binary absent) | Host CLI binary not found on PATH — install or set `LL_HOST_CLI`. |
| `SKIPPED` (stub runner) | Host runner is registered but not yet implemented (`HostNotConfigured`). |
| `FAILED` | Runner is wired but produces an invalid `HostInvocation` (empty binary or args). |

`test_golden_path_behavior[<host>]` (Tier 1 behavioral):

| Result | Meaning |
|--------|---------|
| `PASSED` | Host satisfies every stream-shape invariant against `_LIVE_PROMPT`. |
| `SKIPPED` (non-fake, no env var) | `LL_HOST_CONFORMANCE_LIVE` not set — live tier opted out. |
| `SKIPPED` (binary absent / stub) | Same conditions as constructability. |
| `FAILED` | A genuine contract deviation — treat as a bug, not a baseline, per the Impact section of FEAT-3455. |

`test_scripted_*` (Tier 2, fake only): never skips. `PASSED`/`FAILED` only.
A failure prints the runner name, case name, expected vs. actual event
kinds, and the index of first divergence.

PASS/SKIP for constructability maps directly to the "Orchestration CLI"
table in `docs/reference/HOST_COMPATIBILITY.md`: PASS → ✓, SKIP(stub) →
`stub[^orch]`.

## Baseline Pass/Fail Board

Registry keys in `TEST_ONLY_HOSTS` (`fake`, `fake-minimal`) are deliberately
**not** columns on this board — they always PASS by construction
(`ll-fake-host` is always on PATH via the session-start PATH prepend,
FEAT-3454) and carry no host-support signal. The next board refresh must not
add a column for either.

Snapshot as of 2026-09-12 (constructability tier; `_HOST_RUNNER_REGISTRY` now
has 10 entries — the original 4-host board below predates `gemini`, `omp`,
`kimi-code`, `qwen`, and the two `TEST_ONLY_HOSTS` entries):

| Golden Path | claude-code | codex | opencode | pi | gemini | omp | kimi-code | qwen |
|-------------|:-----------:|:-----:|:--------:|:--:|:------:|:---:|:---------:|:----:|
| `ll-auto`   | PASS        | PASS  | SKIP     | SKIP | PASS | PASS | PASS | PASS |
| `ll-sprint` | PASS        | PASS  | SKIP     | SKIP | PASS | PASS | PASS | PASS |
| `ll-loop`   | PASS        | PASS  | SKIP     | SKIP | PASS | PASS | PASS | PASS |
| `ll-action` | PASS        | PASS  | SKIP     | SKIP | PASS | PASS | PASS | PASS |

SKIP = stub runner (`HostNotConfigured`) — see
`docs/reference/HOST_COMPATIBILITY.md` footnote `[^orch]`.

Tier 1 behavioral results depend on `LL_HOST_CONFORMANCE_LIVE=1` plus
per-host auth/binary availability — no fixed snapshot; run it locally per
the "Running the Harness" section above to check a given host.

## Adding a New Host

1. Implement `HostRunner` for the new host in `host_runner.py` and add it to
   `_HOST_RUNNER_REGISTRY`.
2. The constructability tier automatically picks it up on the next run.
   Add a row to `_STREAM_SHAPE` in `test_host_conformance.py` — a coverage
   gate test fails collection until every registry key has one — describing
   whether the host emits an init event and what its terminal event kind is.
3. The new host's Tier 1 test stays skipped until `LL_HOST_CONFORMANCE_LIVE=1`
   is set for a run that includes it (real binary + auth required).
4. Update the baseline board above once the host passes constructability —
   unless the new host is a `TEST_ONLY_HOSTS` entry, which is excluded from
   the board by policy (see above) and gets no column.

## Closing Superseded Issues

Per FEAT-2259, once this harness lands:

- Run `pytest -m conformance --conformance-host codex` and verify all four
  paths pass, then close **FEAT-1721** (Codex conformance) as superseded.
- Run `pytest -m conformance --conformance-host gemini` once a `GeminiRunner`
  lands, then close **FEAT-2192** (Gemini conformance) as superseded.
</content>
