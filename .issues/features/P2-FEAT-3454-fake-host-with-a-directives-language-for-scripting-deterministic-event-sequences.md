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
---

## Summary

The orchestration paths that matter most — event ordering, abort mid-turn, recovery after a failed start — can only be exercised today against a live host. That makes them slow, expensive, flaky, or simply untested, and it is why the shipped conformance suite settles for asserting a `HostInvocation` is constructable rather than running anything.

Build a fake host runner that accepts a directives language: a test writes a prompt string that encodes an exact sequence of events, failures, and timings for the fake to emit, and the executor drives against it with no model involved. The fake registers through the same `_HOST_RUNNER_REGISTRY` path as a real runner and declares its own `HostCapabilities`, so nothing in the executor knows it is fake.

## Motivation

- Everything downstream in the harness testing story stands on this: a behavioral conformance suite needs a CI-runnable target, and the only target available today is a live host binary behind an env gate.
- It generalizes the fake-clock idea — deterministic time made temporal paths testable; a scriptable fake host makes the host's whole event stream testable. Same property, larger surface.
- The proven shape elsewhere is small: a ~315-line directives interpreter has been enough to let a large deterministic unit-test tier exercise orchestration logic with no model in the loop at all.

## Current Behavior

`scripts/tests/conformance/test_host_conformance.py` parametrizes over `_HOST_RUNNER_REGISTRY` and asserts only that a `HostInvocation` (defined in `scripts/little_loops/host_runner.py`) is constructable — its own docstring concedes it never executes the prompt against a live host. Ordering, abort, and recovery paths in the executor are exercised only by live-host runs, or not at all.

## Expected Behavior

- A fake host runner registered through `_HOST_RUNNER_REGISTRY`, indistinguishable from a real runner at the executor boundary.
- A directives language embedded in the prompt string: a test scripts an exact sequence of events, failures, and timings, and the fake emits exactly that sequence.
- The fake declares its own `HostCapabilities`, and can declare different capability profiles per test — which is itself a test surface.
- Deterministic, model-free, and runnable in the default CI suite.
- Terminal-event discipline from the start: a scripted turn emits exactly one terminal event and it is last — including after a scripted abort.

## Scope

Scope the directives language to what the executor actually branches on. A language that can express every possible host behavior is a second harness to maintain; the executor's event types, failure shapes, and timing hooks define the vocabulary, nothing more.

## Use Case

A loop-run author needs to assert that orchestration paths do the right thing under adversarial host event ordering — e.g. an `abort_received` mid-stream followed by a delayed `tool_result` and a forced startup timeout. Today those paths are exercised only by live host binary runs (slow, flaky, env-gated) or simply left uncovered. With a fake host, the author writes a test whose prompt string encodes the exact sequence (events + failures + timings) and asserts on the executor's recorded response, in milliseconds, no model involved, in the default CI suite.

## Acceptance Criteria

- A fake host runner is registered through `_HOST_RUNNER_REGISTRY` (`scripts/little_loops/host_runner.py`) under a distinct runner name and is constructable via `resolve_host("<name>")` indistinguishably from a real runner at the executor boundary.
- A directives language embedded in the prompt string drives the fake's emitted event sequence: events, failures (including `abort_received`, timeout, startup failure), and timings are all expressible in the prompt and emitted deterministically.
- The fake declares its own `HostCapabilities` record; the constructor accepts a per-test capability profile override so capability-driven executor branches become a test surface.
- Terminal-event discipline: a scripted turn emits exactly one terminal event, and it is last; this holds even when the script includes an explicit abort directive.
- A new behavior-level conformance test (`scripts/tests/conformance/test_host_conformance.py` or sibling) exercises event ordering, abort mid-turn, and recovery-after-failed-start against the fake and runs in the unit suite without env-gating.
- All directives used in the conformance tests stay within the vocabulary the executor actually branches on — no script-only directives drift into the language surface.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — add `FakeHostRunner` class implementing the `HostRunner` Protocol (defined at `host_runner.py:394-492`); add one entry in `_HOST_RUNNER_REGISTRY` (`:1995-2004`); do NOT add to `_PROBE_ORDER` (`:2011-2019`) — mirrors OpenCodeRunner precedent at `host_runner.py:1033-1042` whose absence from `_PROBE_ORDER` is asserted at `test_host_runner.py:1073-1078`
- `scripts/little_loops/host_runner.py:2028-2030` — `HOST_BINARY_NAMES` is derived dynamically from `describe_capabilities().binary`; the fake's `describe_capabilities()` must return a `binary` string and a drift test at `test_host_runner.py:2348-2371` re-derives it every test run
- `scripts/tests/test_host_runner.py` — add a `TestFakeHostRunner` class following the per-runner pattern (e.g. `TestCodexRunner` at `:707-1056`, `TestOpenCodeRunner` at `:1058-1106`); add a `("fake", FakeHostRunner)` row to the cross-runner parametrize at `:2216-2244`
- `scripts/tests/conformance/test_host_conformance.py` — `test_golden_path_invocation` at `:64-113` auto-extends via `@pytest.mark.parametrize("host", list(_HOST_RUNNER_REGISTRY.keys()))`; the fake entry will run unconditionally (no PATH check, no `HostNotConfigured` skip — see the skip predicates in the test body)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:422-689` — `run_claude_command()` calls `runner = resolve_host()` (`:516`), `invocation = runner.build_streaming(...)` (`:517`), then parses stream-json events (`system`/`init`, `assistant`, `result`, `error_max_structured_output_retries`) at `:628-689`; terminal-event detection at the `result` branch (`:665`). This is the corresponding real-consumer site for the scripted events the fake emits.
- `scripts/little_loops/fsm/runners.py:23, :128, :488` — `DefaultActionRunner.run` and `SimulationActionRunner` import `AutomationContext, gh_scope_extra, project_child_env, resolve_automation, resolve_scopes` from `host_runner`
- `scripts/little_loops/fsm/executor.py:81, :2382, :2500, :2586` — executor's `_run_action` and `action_runner.run(...)`; FSM-side terminal-event vocabulary at `:2472-2474, :2618-2656`
- `scripts/little_loops/runner_spec.py:39, :250, :425` — `_run_skill` and `_run_prompt` each call `resolve_host().build_streaming(...)` / `resolve_host().build_blocking_json(...)`
- `scripts/little_loops/cli/verify_host_map.py:109, :116, :119` — cross-validates `_HOST_RUNNER_REGISTRY` against `HOST_CAPABILITIES`. **Adding the fake without an exclude rule will cause `ll-verify-host-map` to treat `"fake"` as a host needing parity-matrix entries in `HOST_COMPATIBILITY.md`** — either exclude or document
- `scripts/little_loops/init/cli.py:102-104, :138, :149, :270-274, :355-363` — validates `LL_HOST_CLI` names against the registry (no change needed unless `LL_HOST_CLI=fake` is meant to be a user-facing option)
- `scripts/little_loops/__init__.py:33, :38, :100` — re-exports `HostInvocation`; the new class would conventionally be re-exported here

### Conventions in Force
- `name` is a **class attribute** (string) on every runner — 8 examples at `host_runner.py:504, 755, 1044, 1120, 1209, 1426, 1619, 1825`. Evidence: registry is keyed by `runner.name` at `host_runner.py:1995-2004`.
- Class-level `capabilities = HostCapabilities(...)` is set on every runner. Evidence: `HostCapabilities` is a `frozen=True` dataclass (`host_runner.py:288-313`); tests assert `FrozenInstanceError` at `test_host_runner.py:1869-1879`. Per-instance override is via `__init__(capabilities=...)`, mirroring `FakeRunner.__init__(self, detect_returns: bool = True)` at `test_action.py:31-32`.
- `@runtime_checkable HostRunner` Protocol is matched structurally — "any class with a name attribute and the five methods below satisfies HostRunner" (`host_runner.py:394-492`). Evidence: test conformance via `isinstance(runner, HostRunner)` at `test_host_runner.py:679-682, 1024-1025, 1105-1106`.
- `describe_capabilities()` returns `CapabilityReport(host, binary, version, capabilities=[CapabilityEntry...])` with `status ∈ {"full", "partial", "unsupported"}` (`host_runner.py:379-391, :662-712`). Evidence: `binary` field feeds `HOST_BINARY_NAMES` (`:2028-2030`), drift-tested at `test_host_runner.py:2348-2371`.
- OpenCodeRunner is registered but absent from `_PROBE_ORDER` to disable auto-detection (`host_runner.py:1033-1042`; tests `test_host_runner.py:1073-1078`). Evidence: this is the existing pattern for "registered-but-not-auto-probed" runners — the fake should mirror it.
- All `build_*` methods take keyword-only arguments and return `HostInvocation` (`host_runner.py:394-492`). Evidence: every runner in the file follows this signature; tests assert the keyword-only contract.
- Live-spawn guard at `scripts/tests/conftest.py:132-397` patches `subprocess.run`/`Popen`; derived from `HOST_BINARY_NAMES`; carve-out is `argv == ["<binary>", "--version"]`. Evidence: guard is structurally a no-op for runners that don't actually subprocess — but the `binary` field in `describe_capabilities()` still determines which carve-outs apply, so pick a value distinct from any real host (e.g. `"fake-host"` rather than `"claude"`).

### Tests
- Existing fake-runner precedents to mirror:
  - `scripts/tests/test_action.py:25-50` — full 5-method `FakeRunner` with `**_: object` kwarg absorption (the standard shape for "satisfies Protocol without changing the runner signature")
  - `scripts/tests/test_cli_harness.py:30-39` and `scripts/tests/test_runner_spec.py:36-41` — minimal 2-method `FakeRunner` (only when the test doesn't exercise `detect()`)
  - `scripts/tests/test_runner_spec.py:44-58` — `CapturingRunner` records `build_streaming_calls: list[dict]`. **Direct precedent for the FEAT-3454 fake** — "records what it received from the executor."
  - `scripts/tests/test_feat3310_artifact_extract.py:66-76` — `type("FakeRunner", (), {...})()` dynamic factory for per-instance `name` override
  - `scripts/tests/test_fsm_executor.py:48-152` — `MockActionRunner` with `results: list[tuple[str, dict]]` and `use_indexed_order: bool`. **Closest precedent for "scriptable test double that emits a deterministic sequence of returns"** — the FEAT-3454 fake is the same shape inverted: the prompt string encodes the sequence, the runner emits it via `build_*` calls.
- New behavior-level conformance tests: extend `scripts/tests/conformance/test_host_conformance.py` for ordering / abort-mid-turn / recovery-after-failed-start. Sibling coverage is scoped in FEAT-3455 — that issue depends on this one and the conformance tests added here become the target it consumes.

### Documentation
- `docs/reference/API.md:10252+` — `## little_loops.host_runner` documents every existing runner; a "Concrete runners" table row at `:10362` is the natural slot for `FakeHostRunner`
- `docs/reference/HOST_COMPATIBILITY.md` — authoritative parity matrix checked by `ll-verify-host-map`; would need either an "is a test fixture, not a real host" caveat or an exclude rule to keep `ll-verify-host-map` clean
- `docs/development/CONFORMANCE.md` — conformance docs may want a note on how the fake entry participates
- `.claude/CLAUDE.md` § Host CLI Abstraction references `resolve_host()` and `HostInvocation` as the canonical abstraction; this addition does not change the abstraction, but the fake's role (testing) is worth a sentence if the section grows

### Configuration
- N/A — no config keys affect host-runner registration today. `LL_HOST_CLI` is env-only; `_HOST_RUNNER_REGISTRY` is module-level. The fake is reachable by `LL_HOST_CLI=fake` after registration without any config changes.

## Program Design

### Types

- `FakeHostCapabilities`: dataclass mirroring `HostCapabilities` shape so the fake can declare a profile override
- `DirectivesScript`: parsed representation of the prompt-string program (event list with attached timings/failures)

### Signatures

- `FakeHostRunner(capabilities: HostCapabilities | None = None)` registers itself into `_HOST_RUNNER_REGISTRY` under a fixed name (e.g. `"fake"`)
- `parse_directives(prompt: str) -> DirectivesScript`
- `FakeHostRunner.build_streaming(prompt: str, **kwargs) -> HostInvocation` — emits the scripted sequence with no subprocess and no model

### Call Path

`resolve_host("fake")` -> `FakeHostRunner.build_streaming()` returns `HostInvocation` (no subprocess); the streaming consumer at `scripts/little_loops/subprocess_utils.py:422-689` (event parsing at `:628-689`, terminal `result` branch at `:665`) is the real-consumer site. The FSM-side terminal-event vocabulary the fake must respect is `action_start` -> `action_output` -> `action_complete` (exactly once, last) at `scripts/little_loops/fsm/executor.py:2472-2474, :2618-2656`; abort vocabulary already exists as `HOST_PRESSURE_ABORT_EVENT` / `HOST_BUDGET_EXCEEDED_EVENT` at `fsm/executor.py:51-56`.

## Implementation Steps

1. Add `FakeHostRunner` implementing the runner interface from `scripts/little_loops/host_runner.py`; register via `_HOST_RUNNER_REGISTRY`.
2. Define a minimal directives grammar in the prompt string (one directive per emitted event/failure/timing) and a `parse_directives` interpreter.
3. Wire capability-profile override into the fake's constructor; emit `HostCapabilities` accordingly.
4. Enforce terminal-event discipline inside the fake (one terminal, last).
5. Add behavior-level conformance tests for ordering / abort-mid-turn / recovery-after-failed-start; keep them inside the unit suite with no env gate.
6. Update `scripts/tests/conformance/test_host_conformance.py` so behavioral (not just constructable) coverage is the default for the fake entry.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- Protocol surface the fake must satisfy: `name: str` (class attribute) + `detect()` + `build_streaming(...)` + `build_blocking_json(...)` + `build_version_check()` + `build_detached(...)` + `describe_capabilities()` — all `build_*` methods take keyword-only args (`scripts/little_loops/host_runner.py:394-492`); `isinstance(FakeHostRunner(), HostRunner)` is the conformance check, validated at `test_host_runner.py:679-682, 1024-1025, 1105-1106`
- Per-instance capability override via `FakeHostRunner.__init__(capabilities: HostCapabilities | None = None)` mirrors `FakeRunner.__init__(self, detect_returns: bool = True)` at `test_action.py:31-32`; the override must propagate to `invocation.capabilities` returned by every `build_*` call so capability-gated consumers (e.g. `_structured_output_args` at `host_runner.py:2365-2383`) read the per-test profile. Construction shape precedent: `scripts/tests/test_fsm_evaluators.py:1066-1086` builds `HostInvocation(binary="codex", args=["-p","prompt"], capabilities=HostCapabilities(structured_output=False))` to test capability branches
- Terminal-event discipline must mirror the FSM vocabulary, not invent new symbols: the executor emits `action_start` -> repeated `action_output` -> exactly one `action_complete` (last) at `scripts/little_loops/fsm/executor.py:2472-2474, :2618-2656`. Abort vocabulary already exists as `HOST_PRESSURE_ABORT_EVENT` / `HOST_BUDGET_EXCEEDED_EVENT` constants at `fsm/executor.py:51-56`; the fake's `abort_received` / timeout / startup-failure directives should match these strings (or the closest existing executor branch) rather than invent new ones — keeping the language surface to what the executor actually branches on (matches Acceptance Criterion: "no script-only directives drift into the language surface")
- DSL parsing precedent: the codebase's only existing "tiny DSL embedded in a string" is `scripts/little_loops/env_file.py:38-62` — `text.splitlines()`, skip blanks and `#` comments early, regex per line with `re.VERBOSE`, malformed lines skipped silently (mirrors `dotenv` convention). The fake's `parse_directives` should follow this same shape; `DirectivesScript` is a forward-looking name, no existing type to reuse
- `CapturingRunner` (`scripts/tests/test_runner_spec.py:44-58`) records `build_streaming_calls: list[dict]` — direct precedent for "records what it received" — the FEAT-3454 fake must likewise record the scripted sequence it parsed so behavioral tests can assert on what the executor actually saw
- `MockActionRunner` (`scripts/tests/test_fsm_executor.py:48-152`) is the closest existing precedent for a "scriptable test double that emits a deterministic sequence of returns" — same shape inverted: the prompt string encodes the sequence, the fake's `build_*` returns surface it (no subprocess needed). `results: list[tuple[str, dict]]` + `use_indexed_order: bool` + `set_result()`/`always_return()` is the API shape to mirror for the directive parser
- `_HOST_RUNNER_REGISTRY` key = `runner.name` (string class attribute); value = class (not instance) — `resolve_host()` calls `runner_cls()` (`host_runner.py:1995-2004, :2292-2336`). Built-ins shadow extensions on collision (mirrors `hooks/__init__.py:_dispatch_table`); registering the fake as a built-in is the only available seam (no public extension API)
- `cli/verify_host_map.py:109, :116, :119` cross-validates registry entries against `HOST_CAPABILITIES`. Adding the fake without an exclude rule will cause `ll-verify-host-map` to flag `"fake"` as needing parity-matrix entries in `HOST_COMPATIBILITY.md` — either add an explicit `"fake"` exclude in `verify_host_map.py` or document the fake as a test fixture in the matrix
- Live-spawn guard at `scripts/tests/conftest.py:132-397` patches `subprocess.run`/`Popen` and is keyed off `HOST_BINARY_NAMES` (derived from `describe_capabilities().binary`). The guard is structurally a no-op for runners that don't actually subprocess, but `describe_capabilities().binary` still determines which carve-outs apply — pick a value distinct from any real host binary (e.g. `"fake-host"`) so the guard's intent stays unambiguous if it ever fires

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- **Closest scripted-JSONL-stream analog is `_NeverEOFStdout` + `TestRunClaudeCommandResultBreak`** — `scripts/tests/test_subprocess_utils.py:2589-2611` (`_NeverEOFStdout(lines: list[str])` yields one-per-`readline()`) and `scripts/tests/test_subprocess_utils.py:2613-2680` (drives a scripted `[assistant_event, result_event]` JSONL stream into the same consumer the fake feeds). This is the precedent that ties the directives language to the actual stream-JSON envelope: each directive expands to one JSONL line shaped like `{"type": "assistant", ...}` or `{"type": "result", ...}` per the consumer's dispatch at `scripts/little_loops/subprocess_utils.py:628-689` (`event.get("type") ∈ {"system", "init", "assistant", "result", "error_max_structured_output_retries"}`, terminal event `{"type": "result", ...}` for Claude / `{"type": "turn.completed", ...}` for Codex)
- **Three additional DSL parsing strategies `parse_directives` should weigh against the existing env_file precedent** (env_file uses silent skip per `scripts/little_loops/env_file.py:38-43`, matching dotenv convention for user-managed input): (a) `scripts/little_loops/fsm/policy_rules.py:98-160` — `parse_rules` enumerates `splitlines()` with `lineno`, dispatches by literal `->` partitioning, **raises `ValueError` at parse time with the offending line number** (`policy_rules.py:125-127`) — pick ValueError here since directive scripts are test-owned, not user-managed; (b) `scripts/little_loops/output_parsing.py:182-194` — `parse_sections` uses regex with `re.MULTILINE` and header detection; (c) `scripts/little_loops/fsm/signal_detector.py:31-70` — `SignalPattern` is find-first regex, multi-line aware. The codebase has 4 distinct strategies for "tiny grammar in a string"; `parse_directives` should consciously diverge from env_file if it adopts anything stricter than silent-skip
- **Full FSM event vocabulary the directives grammar should match** (extends the prior abort-vocabulary note beyond `HOST_PRESSURE_ABORT_EVENT` / `HOST_BUDGET_EXCEEDED_EVENT` at `fsm/executor.py:51-56`): `scripts/little_loops/fsm/host_guard.py:33-38` (`HOST_PRESSURE_EVENT`, `HOST_PRESSURE_RELIEVED_EVENT`, `HOST_PRESSURE_ABORT_EVENT`, `HOST_COOLDOWN_EVENT`, `HOST_SUBPROC_RSS_EVENT`, `HOST_BUDGET_EXCEEDED_EVENT`); `scripts/little_loops/fsm/executor.py:117-142` (`STALL_DETECTED_EVENT`, `WORKDIR_VANISHED_EVENT`, `RATE_LIMIT_EXHAUSTED_EVENT`, `RATE_LIMIT_STORM_EVENT`, `RATE_LIMIT_WAITING_EVENT`, `THROTTLE_WARN_EVENT`, `THROTTLE_HARD_EVENT`, `THROTTLE_STOP_EVENT`, `PROMPT_SIZE_WARN_EVENT`); `scripts/little_loops/fsm/communication_adapter.py:18-19` (`HUMAN_APPROVAL_REQUESTED_EVENT`, `HUMAN_RESPONSE_EVENT`). All are `<snake_case>_EVENT: str = "<name>"` constants exported in `__all__`. The directives grammar's keyword set must be a subset of these — Acceptance Criterion 6's "no script-only directives drift into the language surface" gate is met only by importing the constants and asserting on membership at parse time
- **`scripts/tests/spike/host_compose/` already exists with two divergent fakes** (`VerboseFakeRunner` accepting the full Protocol kwarg set + `MinimalFakeRunner` accepting only `prompt`/`model`, with deliberately distinct binary basenames `"fake-verbose-divergent"` and `"fake-minimal-divergent"` — `scripts/tests/spike/host_compose/fakes.py:36-38, :44-212`). These are **spike-local, NOT registered** in `_HOST_RUNNER_REGISTRY` (confirmed by the AST sniff guard at `scripts/tests/spike/host_compose/test_host_compose.py:299-326` walking `ast.parse(source)` and asserting no `ImportFrom` names `run_claude_command`, no `Import` aliases `subprocess_utils` at `:271-326`). FEAT-3454's `FakeHostRunner` is a distinct concern that must coexist with the spike fakes — registering `"fake"` in `_HOST_RUNNER_REGISTRY` does not affect the spike's local `type()`-built fakes, and the spike's AST isolation guard pattern is reusable to pin "no real subprocess path" on the registered fake
- **`CapturingRunner` was created specifically because `FakeRunner`'s `**_: object` kwarg absorption silently dropped `automation=`** (`scripts/tests/test_runner_spec.py:44-58`, comment at `:46-50`). The FEAT-3454 fake's `build_streaming`/`build_blocking_json` must declare the kwargs it accepts explicitly (or use a narrower `**kwargs` subset than `object`) so per-test capability/profile overrides flow through — silent kwarg drop is the failure mode `CapturingRunner` was extracted to defeat, and a registered fake that absorbs `automation=` silently would reproduce it
- **`MockActionRunner`'s two precedence modes** (`scripts/tests/test_fsm_executor.py:48-152`): `use_indexed_order=True` walks `results: list[tuple[str, dict]]` by call count (`:108-119`); `use_indexed_order=False` (default) pattern-matches each result against action text (`:122-132`). For FEAT-3454 the **indexed-order mode is the natural fit** — each directive in the prompt is consumed in order, no pattern matching needed. `set_result()` / `always_return()` (`test_fsm_executor.py:144-146`) are the API shapes to mirror for `parse_directives` if the directive count varies at runtime (e.g. a script with `loop 3: action_output …` block)
- **`scripts/tests/conformance/conftest.py:10-27`** defines the `--conformance-host` option + `isolated_env` fixture that gate the conformance suite locally. The fake's conformance tests should sit inside `scripts/tests/conformance/test_host_conformance.py` and inherit both — the registry-driven parametrize at `test_host_conformance.py:65` (`list(_HOST_RUNNER_REGISTRY.keys())`) auto-extends when `"fake"` is registered, so no manual list update needed; a `--conformance-host=fake` filter selects only the fake's tests in isolation
- **`scripts/tests/conftest.py:400-427` — `_fail_on_live_host_cli`** function-scoped enforcement runs alongside the session-scoped `_install_no_live_host_cli` at `:353-397`. The fake's conformance tests must NOT trigger this — `LL_HOST_CLI=fake` is the only env var they should set, and the fake's `detect()` must return `False` so it never auto-resolves in a test that does NOT pin `LL_HOST_CLI` (otherwise an un-set env would fall through to the registry and pick `"fake"` where a real host was expected)
- **`test_satisfies_host_runner_protocol` is the canonical one-liner shape** — 8 precedent sites at `scripts/tests/test_host_runner.py:679, 1024, 1105, 1163, 1303, 1484, 1676, 1862`. `TestFakeHostRunner` must end with this assertion as `assert isinstance(FakeHostRunner(), HostRunner)` (or equivalent via `runner_cls()`)
- **`hooks/__init__.py:_dispatch_table` carries the same "Built-ins shadow extensions on collision" precedence rule as `_HOST_RUNNER_REGISTRY`** (`:189-190`). The rule is consistent across both registries — registering `FakeHostRunner` as a built-in means a downstream extension that also names `"fake"` is silently shadowed, the same way `hooks/__init__.py` shadows extension-provided intents. Documenting this in the integration wiring prevents future "why isn't my override taking effect" confusion
- **SKIP-not-FAIL convention with `f"[{host}/{golden_path}] ..."` diagnostic strings** is the established posture for conformance tests (`scripts/tests/conformance/test_host_conformance.py:96-109` skips on `shutil.which(binary) is None` and `HostNotConfigured`). The fake is structurally exempt from both predicates (no real binary, doesn't raise `HostNotConfigured`), so its conformance tests run unconditionally — but should follow the same `f"[{host}/{golden_path}] ..."` diagnostic format on every assertion, mirroring `scripts/tests/test_streaming_cache_parity.py:182-186`
- **`cli/verify_host_map.py:_check_runtime_contradiction` is the exact function name** for the registry-vs-`HOST_CAPABILITIES` cross-validation (refs at `cli/verify_host_map.py:109, :116, :119`). To keep `ll-verify-host-map` clean without documenting the fake in `HOST_COMPATIBILITY.md`, add an explicit `"fake"` exclusion inside `_check_runtime_contradiction` — the fake's role as a test fixture is the carve-out, not its capability profile. (Mirror: `HOST_COMPATIBILITY.md`'s parity matrix has no precedent for test-fixture rows, so a documented caveat is a second-route alternative.)

## Impact

- **Priority justification (P2)**: blocks any behavior-level conformance coverage of orchestration paths — currently exercised only by live-host runs or not at all.
- **Effort**: medium — one fake runner, a small directives interpreter, plus a handful of conformance tests; the ~315-line referenced interpreter suggests the directive core is the bulk.
- **Risk**: low — fake is additive in the registry; nothing in the executor changes, and the live-host path stays untouched.
- **Benefit**: deterministic, model-free behavioral conformance in the default CI tier; unblocks testing of event-ordering, abort, and recovery paths.

## Status

**Open** | Created: 2026-09-11 | Priority: P2


## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md#little_loopshost_runner` | `HostRunner` protocol surface the fake must satisfy: `detect`, `build_streaming`, `build_blocking_json`, `build_version_check`, `build_detached`, `describe_capabilities` |
| `docs/ARCHITECTURE.md` (host abstraction) | Defines `_HOST_RUNNER_REGISTRY` membership and the test-double seam the fake registers into |
| `.claude/CLAUDE.md` § Host CLI Abstraction | `resolve_host()` is the only entry point for new host call sites; the fake registers here so `resolve_host("fake")` works |

## Session Log
- `/ll:refine-issue` - 2026-09-12T04:47:19 - `63ed2222-46d0-4175-b050-49b2a402d5c5.jsonl`
- `/ll:refine-issue` - 2026-09-12T04:06:04 - `b7b7f9e7-8f55-4db9-84ab-f495556f1242.jsonl`
- `/ll:format-issue` - 2026-09-12T03:49:49 - `8c6cc97d-774e-45fd-be34-14d7ed48d65c.jsonl`
