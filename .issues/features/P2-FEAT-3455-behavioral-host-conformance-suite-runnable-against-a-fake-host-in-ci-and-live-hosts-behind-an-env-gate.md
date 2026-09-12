---
id: FEAT-3455
title: Behavioral host-conformance suite runnable against a fake host in CI and live hosts behind an env gate
type: FEAT
priority: P2
status: open
discovered_date: '2026-09-11'
labels:
- multi-host
- verification
---

## Summary

Every registered host runner is currently defended by a type check. `scripts/tests/conformance/test_host_conformance.py` parametrizes over `_HOST_RUNNER_REGISTRY` and asserts, per host per golden path, that a `HostInvocation` is constructable — its own docstring concedes it never executes the prompt against a live host. Nothing verifies that a runner which constructs a valid invocation actually produces the behavior the multi-host layer promises callers.

Replace the constructability check with one parameterized behavioral suite that takes a target and asserts observable outcomes: the event sequence a turn emits, its terminal event, abort handling, and the shape of a failure. The same file runs against the fake host on every CI run and against real host binaries behind an explicit env gate, so the contract is enforced continuously and validated against reality on demand.

## Why

The multi-host layer's premise is that a caller does not know which host is running; this is the enforcement half of that promise. The payoff is concrete: adding another adapter becomes a day of work against a known contract instead of a rewrite.

## Current Behavior

`scripts/tests/conformance/test_host_conformance.py` parametrizes over `_HOST_RUNNER_REGISTRY` and asserts, per host per golden path, that `resolve_host() + build_streaming()` returns a constructable `HostInvocation`. The test's own docstring concedes the conformance suite "does not execute the prompt against a live host." A runner that constructs a syntactically valid `HostInvocation` but produces the wrong event sequence (extra events, terminal mid-stream, missing abort handling, malformed failure shape) passes this gate. The contract the multi-host layer promises callers is unenforced.

## Expected Behavior

Replace the constructability check with a single, parameterized behavioral suite `test_golden_path_behavior(host, golden_path)` that runs against a target and asserts observable outcomes:

- The event sequence a turn emits, in order.
- Exactly one terminal event, and it is the last event on the stream.
- Abort mid-turn terminates the stream with the declared abort terminal; the runner does not silently drain remaining tokens.
- The shape of a failure event is stable across hosts (same keys, same primitive types).

The fake host runs the suite in the default CI gate (every `python -m pytest scripts/tests/` invocation). Live host binaries run the same suite behind an explicit env var (e.g. `LL_HOST_CONFORMANCE_LIVE=1`) with a per-target timeout, so the suite is enforced continuously and validated against reality on demand.

Capability-gated cases early-return when the capability is undeclared, so one suite covers a matrix of host abilities without forking per host. The capability profile is a promise, not a hint: where `describe_capabilities()` declares a capability absent, the suite asserts the corresponding event never appears — a negative assertion, not a skip. A host that under-declares is a bug on equal footing with one that over-declares.

## Use Case

A maintainer ports a new CLI host to `HostRunner`. They wire `detect()`, `build_streaming()`, `build_blocking_json()`, `build_version_check()`, and `build_detached()`, then run `LL_HOST_CONFORMANCE_LIVE=1 pytest -m conformance scripts/tests/conformance/test_host_conformance.py -k <runner>` against their binary. Any deviation from the contract — wrong terminal event, missing abort handling, malformed failure payload — fails loudly with a diff against the expected event sequence. The maintainer knows the day the suite goes green, the host satisfies the multi-host promise. No manual smoke run, no "looks right," no latent regression caught only after a loop run hangs.

## Acceptance Criteria

- `test_host_conformance.py` contains a single parameterized test `test_golden_path_behavior` (or equivalent) that asserts observable outcomes — event sequence, terminal-event-last, abort termination, failure shape — and replaces the current `test_golden_path_invocation` constructability check.
- The suite is runnable against the fake host (FEAT-3454) by default on every `python -m pytest scripts/tests/` invocation and exits 0 when the fake satisfies the contract.
- The suite is runnable against live host binaries behind `LL_HOST_CONFORMANCE_LIVE=1` (or equivalent env var) with a per-target timeout, and exits non-zero when a live runner deviates from the contract.
- For every capability marked absent in a runner's `describe_capabilities()` output, the corresponding event-emission case asserts the event never appears (negative assertion), not a skip.
- A diffed failure report shows expected vs actual event sequence, runner name, golden path, and the assertion that fired.
- The conformance gate is wired through the existing `pytest -m conformance` marker contract; existing live-host skip conditions (binary missing, stub raises `HostNotConfigured`) still apply.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- `scripts/little_loops/host_runner.py` — owns `HostRunner` Protocol, `_HOST_RUNNER_REGISTRY`, `resolve_host()`, `HostInvocation` (frozen), `HostCapabilities`, `CapabilityReport`, `describe_capabilities()`. The fake target (FEAT-3454) registers itself into this registry under a fixed name (e.g. `"fake"`); `resolve_host(env={"LL_HOST_CLI": "fake"})` resolves to it (consistent with `test_host_conformance.py:101`).
- `scripts/tests/conformance/test_host_conformance.py` — the file being rewritten. Existing `test_golden_path_invocation` (`:64-71`) is the constructability check; replaces with `test_golden_path_behavior` over `(host, golden_path)`. SKIP rules at `:96-109` (binary missing, `HostNotConfigured` on `build_streaming`) carry over verbatim.
- `scripts/tests/conformance/conftest.py` — already defines `--conformance-host` option (`:10-15`) and `isolated_env` fixture (`:21-26`). May need a complementary `_live_conformance` fixture that activates when `LL_HOST_CONFORMANCE_LIVE=1`.
- `scripts/tests/conformance/__init__.py` — empty package init; no change needed.
- `scripts/tests/conftest.py` — owns the live-host-spawn guard (`_install_no_live_host_cli` `:353-397`, `_fail_on_live_host_cli` `:400-427`) and `_CMD_RUN_ENV_VARS` scrub (`:1100-1119`). The new suite must respect this guard; tests that want a real host binary set `LL_HOST_CONFORMANCE_LIVE=1` and rely on the env-gate opt-in (not bypass the fixture).
- `scripts/tests/test_host_runner.py` — reference for per-runner capability assertions (`:2029-2055`), `TestAutomationProfileEnvAcrossRunners` (`:64-74`) for the explicit-class-list parametrize shape, and the negative-assertion pattern `pytest.raises(HostNotConfigured)` (`:294-303`).
- `pytest.ini:24` and `scripts/pyproject.toml:280-285` — both register the `conformance` marker (`conformance: marks tests as host conformance tests (deselect with '-m "not conformance"')`); both must agree; `--strict-markers` (`:15`, `pyproject.toml:269`) fails collection otherwise.
- `.github/workflows/ci.yml` — `conformance` job runs `-m conformance`; the new test runs in default CI via this gate without workflow change. Live-host-binary path is local-only behind `LL_HOST_CONFORMANCE_LIVE=1` (no CI job added — keep CI runner hermetic).
- `docs/development/CONFORMANCE.md` — authoritative conformance doc; documents the current constructability-check baseline. Must be rewritten/extended to cover behavioral assertions, `LL_HOST_CONFORMANCE_LIVE`, per-target timeout, and the negative-capability assertion contract.
- `docs/reference/HOST_COMPATIBILITY.md` — "Conformance harness" row already references `docs/development/CONFORMANCE.md`; needs no direct edit if CONFORMANCE.md is updated.
- `docs/development/TESTING.md` — already mentions the `conformance` marker and conformance/ subdirectory layout; needs no direct edit.
- `scripts/little_loops/cli/verify_host_map.py` — `ll-verify-host-map` is the closest existing analogue (cross-host capability-floor gate); reuses `describe_capabilities()` parity check. Not modified by this issue; informational reference.

Conventions in force (rule + cited evidence; not templates to reproduce):
- Parametrize over registry keys for multi-host assertions — evidence: `test_host_conformance.py:64-71`, `test_host_runner.py:64-74`, `:347-359`. Stacking a second `@pytest.mark.parametrize` produces cartesian product with descriptive `ids=`.
- Module-level `pytestmark = pytest.mark.skipif(...)` for env/bin gates, computed at import time — evidence: `test_claude_code_adapter.py:22-24`, `test_omp_adapter.py:28-30`, `conftest.py:88-99`.
- Capability-driven assertions assert both `full` (positive) AND `unsupported` (negative) — evidence: `test_host_runner.py:2047-2055`. A host that under-declares is as much a bug as one that over-declares.
- Negative assertions use `not in <stream>` with diagnostic string — evidence: `test_fsm_signal_integration.py:211`, `test_next_issues.py:880`, `test_git_operations.py:319-320`.
- SKIP-not-FAIL for binary missing and stub runners — evidence: `test_host_conformance.py:96-109`. Concrete `reason=` string, not bare `pytest.skip()`.
- Failure-message diagnostic in every assertion — evidence: `test_streaming_cache_parity.py:182-186`, `conftest.py:258-270`. Use `repr`-style f-strings (`argv={argv!r}`).
- Per-target timeout at the production `subprocess.run(timeout=N)` site, not at the test site — evidence: `host_runner.py:245-253`. Suite-wide watchdog is `--timeout=120 --timeout-method=thread` (`pyproject.toml:266-267`, `pytest.ini:17`).
- Event streams over JSONL (one event per line, `\n`-terminated) — evidence: `test_subprocess_mocks.py:178-214`, `test_streaming_cache_parity.py:59-67`. Terminal event is `{"type": "result", ...}` for Claude and `{"type": "turn.completed", ...}` for Codex.
- `isolated_env` fixture scrubs `LL_HOST_CLI` and `LL_HOOK_HOST` — duplicated in `conftest/conftest.py:21-26` and `test_host_runner.py:56-61` (FEAT-2259 noted the duplication as either promote or redefine).

## Program Design

### Types

- `ConformanceTarget`: `(runner: HostRunner, name: str, binary: str | None)` — what a single parameter slot supplies
- `BehavioralEvent` (in test file): `{kind: Literal["stdout"|"stderr"|"tool"|"result"|"abort"|"error"|"terminal"], data: Any, ts: float}` — observable event envelope; shape is host-stable
- `BehavioralFailure`: `{kind: str, message: str, exit_code: int | None, recoverable: bool}` — host-stable failure shape
- `TerminalEvent`: `BehavioralEvent` whose `kind in {"result", "abort", "error"}` and is the stream's last event

### Signatures

- `conformance_target(runner: HostRunner) -> ConformanceTarget` — wires runner + binary name into a parameter slot
- `run_golden_path(target: ConformanceTarget, prompt: str, *, timeout_s: float) -> list[BehavioralEvent]` — single target, one prompt, observable event stream to terminal
- `assert_event_sequence_equals(events: list[BehavioralEvent], expected: list[str]) -> None` — ordered-kind assertion, fails with a diff
- `assert_terminal_is_last(events: list[BehavioralEvent]) -> None` — exactly one terminal event; it is the last element
- `assert_capability_not_emitted(events: list[BehavioralEvent], absent_capability: str) -> None` — negative assertion: event kind tied to the capability must not appear
- `_golden_path_behavior(target: ConformanceTarget, prompt: str, capabilities: CapabilityReport) -> None` — orchestrator: gate capability-conditional cases off `capabilities`, sequence+terminal+abort+failure assertions run unconditionally

### Call Path

`pytest collection` -> `_HOST_RUNNER_REGISTRY` resolved into `ConformanceTarget` list -> if `LL_HOST_CONFORMANCE_LIVE` unset, fake target substituted -> `test_golden_path_behavior(target, golden_path)` -> `run_golden_path` -> `resolve_host(name).describe_capabilities()` -> `_golden_path_behavior(target, prompt, caps)`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- New decision rule: the capability profile is a *promise*, not a hint. Where `describe_capabilities()` declares a capability absent, the suite asserts the corresponding event kind never appears via `<kind> not in [e.kind for e in events]`. A host that under-declares (`status == unsupported` yet emits the event) is a bug on equal footing with one that over-declares. This is the negative-assertion contract; capability-conditional POSITIVE assertions early-return on `status != full` instead.
- Existing classification rule (carried over from `test_host_runner.py:2029-2055`): capability status is `Literal["full", "partial", "unsupported"]`; positive assertions gate on `full`, partial/unsupported take the capability-absent path.
- Existing SKIP-vs-FAIL rule (carried over from `test_host_conformance.py:96-109`): binary missing on PATH and `HostNotConfigured` on `build_streaming` are SKIP (not FAIL); only observable-behavior deviations are FAIL.
- New env-gate rule (FEAT-3455): `LL_HOST_CONFORMANCE_LIVE=1` enables the live-host-binary path. When unset, the suite substitutes the fake target (`FakeHostRunner` from FEAT-3454). The env var is read at fixture resolution, not at module import, so `monkeypatch.setenv()` in a test body still wins (per `conftest.py:1095-1096` precedent).
- Per-target timeout (carried over from `host_runner.py:245-253` + suite-wide `pyproject.toml:266`): production-site `subprocess.run(timeout=N)` is the tighter bound; `--timeout=120` watchdog is the upper bound. Per-target value must be ≤ 120s.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

1. Replace `test_golden_path_invocation` in `scripts/tests/conformance/test_host_conformance.py` with `test_golden_path_behavior(target, golden_path)` parameterized over `(host, golden_path)`. The new test must drive the runner through one prompt end-to-end and assert the observable event stream — not the `HostInvocation` shape. Existing parametrize shape carries over from `test_host_conformance.py:64-71`.
2. Wire `ConformanceTarget` resolution so `LL_HOST_CONFORMANCE_LIVE` unset substitutes the fake target (`FakeHostRunner` from FEAT-3454) and set leaves the registry as-is. Resolution lives in `conftest.py:_live_conformance` (or equivalent) — modeled on `conftest.py:31-33` (`LL_FUZZ` profile switch) and `test_cross_host_baseline.py:353-367` (env-var-keyed fake_which).
3. Keep the existing SKIP conditions verbatim: `shutil.which(binary) is None` and `HostNotConfigured` on `build_streaming` (from `test_host_conformance.py:96-109`). Module-level `pytestmark = pytest.mark.conformance` plus per-test `pytest.skip(...)` for runtime gates.
4. Implement four assertion helpers — `assert_event_sequence_equals`, `assert_terminal_is_last`, `assert_capability_not_emitted`, `_golden_path_behavior` (orchestrator) — per the signatures in §Program Design. Capability-conditional assertions early-return on `describe_capabilities()`; the negative assertion (`not in events`) fires unconditionally. Diagnostic strings on every `assert` (modeled on `test_streaming_cache_parity.py:182-186`).
5. Per-target timeout via `subprocess.run(timeout=N)` at the production site (e.g. in `_resolve_runner` wrapper that invokes the binary). Suite-wide `--timeout=120` (`pyproject.toml:266`) is the upper bound; the per-target value should be tighter (modeled on `host_runner.py:245-253` `timeout=10`).
6. Negative-capability assertion contract: when `describe_capabilities()` declares a capability absent, the suite asserts the corresponding event kind never appears via `<kind> not in [e.kind for e in events], f"<host> {<host>!r} capability {<cap>!r} declared absent — <kind> event must not appear; events={events!r}"`. Modeled on `test_fsm_signal_integration.py:211` and `test_next_issues.py:880`.
7. Diff-style failure report: when `assert_event_sequence_equals` fails, the message includes runner name, golden path, expected event kinds, actual event kinds, and the index of the first divergence. Modeled on `test_streaming_cache_parity.py:182-186` (`expected=... actual=... diff_pct=...`).
8. Extend `docs/development/CONFORMANCE.md` to cover: the four assertion helpers, the `LL_HOST_CONFORMANCE_LIVE` env gate, the per-target timeout policy, the negative-capability assertion contract, and the diff-style failure report. The current doc only describes the constructability-check baseline.
9. Verify CI: `python -m pytest scripts/tests/` exits 0 (the new suite runs against the fake by default) and `python -m pytest scripts/tests/ -m "not conformance"` continues to skip the new test. Live-binary path (`LL_HOST_CONFORMANCE_LIVE=1`) is verified locally; no CI job is added (keep CI runner hermetic).
10. Verify the live-host-spawn guard (`conftest.py:_install_no_live_host_cli` `:353-397`) is respected — the test must mock the spawn or use the fake; an un-mocked real-binary spawn still fails the suite at fixture teardown.

## Impact

- **Priority**: P2 — defensive infrastructure for a capability that already exists (constructability check); gates a rewrite risk that is latent, not active.
- **Effort**: Medium — rewrites one test function into a parameterized suite; depends on the fake host (FEAT-3454); integrates with the existing `pytest -m conformance` marker, the `LL_HOST_CONFORMANCE_LIVE` env gate is new but trivial.
- **Risk**: Low — additive on the existing suite, no runner contract change, no public API change. The negative-capability assertion can produce failure-shaped-by-design cases that previously passed silently; treat first green as the new baseline.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-11 | Priority: P2

## Design

One suite, parameterized by target — the shape that lets the fake and a real host run the identical file:

- A single conformance function over a target. The fake host runs it in the default CI suite; real host binaries run the same suite behind an explicit env var, with a timeout.
- Assert observable outcomes, not invocation shapes: the event sequence a turn emits; exactly one terminal event, and it is last; abort mid-turn still terminates the stream; the shape of a failure.
- Capability-gated cases early-return when the capability is undeclared, so one suite covers a matrix of host abilities without forking per host.
- The capability profile is a promise, not a hint: where a capability is declared false, assert the corresponding event never appears — a negative assertion, not a skip. A host that under-declares is as much a bug as one that over-declares.

## Dependencies

- Depends on the fake host with a directives language (FEAT-3454) for a CI-runnable target; the suite is the reason that fake exists.
- Pairs with coverage: this suite is about whether the covered cases actually run. Whether an uncovered case went unnoticed is the complementary concern, tracked separately.


## Session Log
- `/ll:refine-issue` - 2026-09-12T04:00:52 - `e6d1e59e-6622-4d79-806e-0adbe063751c.jsonl`
- `/ll:format-issue` - 2026-09-12T03:50:16 - `b5367032-da18-428d-be91-16777a0b7408.jsonl`
