---
id: 3456
title: Prove host-agnosticism with two deliberately divergent fakes, not one
type: ENH
priority: P3
status: open
discovered_date: '2026-09-11'
labels: []
unproven_mechanism: true
spike_attempted: true
spike_completed: true
blocked_by:
  - FEAT-3454
  - FEAT-3455
relates_to:
  - ENH-3453
---

## Summary

The fake host (FEAT-3454) and the behavioral conformance suite (FEAT-3455) both assume a single fake. A single fake proves the code runs; it cannot prove the code is agnostic, because that one fake's action and observation shapes may be silently baked into the surface under test. The assertion only becomes real with a second fake whose shapes deliberately disagree with the first — different action vocabulary, different observation structure — composed through the same abstract interface, with the test asserting the layer under test touches only that interface and never a concrete shape.

## Why now

This is timing-sensitive rather than large. It is cheap to add while the fake host is still being built and its shape has not hardened; it gets progressively more expensive once code accretes around a single fake's assumptions. Scope is one additional fake plus the composition test, not a redesign of either.

## Design

- One additional fake host whose action and observation shapes deliberately diverge from the first: different action vocabulary, different observation structure, a different capability profile.
- A composition test that drives both fakes through the same executor paths and asserts the multi-host layer touches only the abstract host interface — never a concrete shape.
- The proven pattern elsewhere is exactly this test: the framework it is borrowed from keeps its largest test file as a composition of two deliberately divergent dummies asserting only-interface access, because one fake proves a layer runs while two prove it is agnostic.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- The abstract host interface lives at `scripts/little_loops/host_runner.py:394` (`HostRunner` Protocol, `@runtime_checkable`); concrete runners structurally satisfy it without explicit inheritance — verified per-runner via `isinstance(runner, HostRunner)` at `test_host_runner.py:679, 1024, 1105, 1163, 1303, 1484, 1676, 1862`. The composition test asserts against this Protocol, not against concrete class names
- `_HOST_RUNNER_REGISTRY` (`host_runner.py:1995-2004`) currently has 8 entries (claude-code, codex, opencode, pi, gemini, omp, kimi-code, qwen); registering the second fake here makes it participate automatically in the registry-driven parametrization at `test_host_conformance.py:103`
- The "action vocabulary" today is the builder-method parameter list on `HostRunner` (`prompt`, `working_dir`, `resume`, `agent`, `tools`, `model`, `automation`, `automation_profile`, `disable_background_tasks`, `workspace_root`); the "observation structure" is the JSON-event stream consumed by `run_claude_command` (`subprocess_utils.py:516-680`) via `selectors.DefaultSelector`, switching on `event.get("type") ∈ {"system", "assistant", "result"}`. The two fakes must diverge along both axes — different parameter shapes AND different event-stream shapes — to make the composition test non-trivial
- The composition test's executor path is `run_claude_command` (`subprocess_utils.py:516`) for streaming or `run_blocking_json` (`host_runner.py:2434`) for blocking JSON. Both routes consume `HostInvocation` from `resolve_host()` and feed subprocess + selector machinery. These are the only integration surfaces today
- No existing in-tree precedent for "two divergent fakes composed through a shared executor to prove interface-only access"; the closest analog is `test_cross_host_baseline.py` (drives two hosts through the same loop via subprocess, not in-process fakes). The borrowed pattern referenced in the issue's Design section is external — see ⚠ Unproven mechanism marker below
- ⚠ Unproven mechanism — borrowed pattern has no confirming in-tree usage site

## Scope

Distinct from parity-testing generated artifacts against their declarations — a different axis. This is about whether the host surface itself is genuinely shape-independent.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

Files and conventions for ENH-3456's composition test (second fake + multi-host composition assertion).

### Files to Modify
- `scripts/tests/conformance/test_host_conformance.py` — the conformance suite FEAT-3455 rewrites and ENH-3456's composition test extends; currently `test_golden_path_invocation` at `:71` is parametrized over `_HOST_RUNNER_REGISTRY` (`:103`) and asserts only `HostInvocation` constructability
- `scripts/little_loops/host_runner.py:1995` — `_HOST_RUNNER_REGISTRY`; the second fake registers here so the registry-driven parametrization picks it up automatically
- `scripts/little_loops/host_runner.py:394` — `HostRunner` Protocol; the abstract interface the composition test asserts the multi-host layer touches exclusively (via `isinstance(invocation, HostRunner)`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:516` — `run_claude_command()` is the canonical streaming consumer; the executor path the composition test drives to prove host-agnosticism
- `scripts/little_loops/fsm/evaluators.py:1104, 1215, 1471` — `evaluate_*` judges call `resolve_host().build_blocking_json()`; another executor path the composition test can drive
- `scripts/little_loops/runner_spec.py:250, 425` — `run_foreground` and `cmd_run` paths route through `resolve_host().build_streaming()`
- `scripts/little_loops/fsm/handoff_handler.py:116` — `build_detached` for spawn-and-go handoffs
- `scripts/little_loops/cli/action.py:341` — `cmd_capabilities()` exposes `describe_capabilities()` over JSON
- `scripts/tests/test_host_runner.py:679, 1024, 1105, 1163, 1303, 1484, 1676, 1862` — `test_satisfies_host_runner_protocol` is the established pattern for asserting Protocol satisfaction; the second fake's conformance test follows this shape
- `scripts/tests/conformance/conftest.py:14, 21` — `--conformance-host` CLI filter and `isolated_env` fixture (clears `LL_HOST_CLI`/`LL_HOOK_HOST`); the existing pattern the composition test reuses

### Conventions in Force
- `HostRunner` is a `@runtime_checkable` Protocol (`host_runner.py:394-407`); conformance is asserted via `isinstance(x, HostRunner)` rather than via subclassing — evidence: per-runner `test_satisfies_host_runner_protocol` at `test_host_runner.py:679, 1024, 1105, 1163, 1303, 1484, 1676, 1862`
- Test doubles are local module-level classes named `FakeRunner`/`_FakeHostRunner`; there is no shared conftest helper for host fakes — evidence: `test_action.py:25-50`, `test_runner_spec.py:36-41`, `test_cli_harness.py:30-39`, `test_cli_doctor_install_checks.py:622-625`
- The conformance suite parametrizes over `_HOST_RUNNER_REGISTRY.keys()` (`test_host_conformance.py:103`); registering a fake in the registry automatically includes it in the parametrization — no hand-extension needed
- `_install_no_live_host_cli` (`scripts/tests/conftest.py:353-397`) is a session-scoped autouse guard that blocks `subprocess.run`/`Popen` on binary basenames in `HOST_BINARY_NAMES` (`host_runner.py:2028-2030`); only `<binary> --version` is exempt (`scripts/tests/conftest.py:237-255`). The second fake's `binary` field must NOT match any registered real-host binary, or downstream tests will trip the guard
- `HostCapabilities`, `HostInvocation`, `CapabilityReport`, `CapabilityEntry`, `AutomationContext` are all `@dataclass(frozen=True)` — evidence: `test_host_runner.py:1869-1879, 1893-1897, 1989-1992, 1994-1997`

### Tests
- `scripts/tests/conformance/test_host_conformance.py` — the suite FEAT-3455 rewrites; ENH-3456's composition test extends it
- `scripts/tests/test_host_runner.py` — per-runner conformance tests plus parametrized-across-runners parity tests (`TestAutomationProfileEnvAcrossRunners:64-99`, `TestProjectChildEnvCrossRunnerParity:274-292`, `TestDisableBackgroundTasksNoOpOnOtherRunners:347-378`)
- `scripts/tests/test_cross_host_baseline.py` — closest analog today (drives two hosts through the same loop via subprocess, not in-process fakes) — relevant for the composition test's mechanics

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:40` — authoritative parity matrix citing `_HOST_RUNNER_REGISTRY` as the source of truth
- `docs/ARCHITECTURE.md:847-910` — describes the host_runner abstraction layer
- `docs/reference/API.md:10252+` — API reference for `little_loops.host_runner`

### Configuration
- `LL_HOST_CLI` / `LL_HOOK_HOST` env vars; `orchestration.host_cli` config key — read by `apply_host_cli_from_config()` (`host_runner.py:2581`) and consumed by `resolve_host()` chain
- `LL_HOST_CONFORMANCE_LIVE` — referenced in FEAT-3455's design as the gate for running the suite against live binaries; not present in code yet

### Related Issues (Dependencies)
- FEAT-3454 (open, P2) — provides the first fake host; ENH-3456's mechanism cannot be exercised until FEAT-3454 lands. Blocked by FEAT-3454.
- FEAT-3455 (open, P2) — rewrites the conformance suite; the composition test from ENH-3456 lives in this rewrite. Blocked by FEAT-3455.
- ENH-3453 (open, P2) — collapses the runtime half of the host capability map onto a declarative source. Parallel work; not a strict dependency. Relates to ENH-3453.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

Types, signatures, and call path for ENH-3456's composition test and the second divergent fake.

### Types
- `HostRunner` (Protocol, `@runtime_checkable`) — `host_runner.py:394-407`; the abstract interface the composition test asserts against via `isinstance(x, HostRunner)`. Six-method Protocol: `detect`, `build_streaming`, `build_blocking_json`, `build_version_check`, `build_detached`, `describe_capabilities`. Five required attributes per Protocol docstring: `name`, `binary` (returned from `describe_capabilities()`), and the four capability fields
- `HostCapabilities` (frozen dataclass) — `host_runner.py:288-313`; six boolean flags: `streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output` (ENH-2627), `workspace_sandboxed` (FEAT-2878). The second fake declares a deliberately different profile against this
- `HostInvocation` (frozen dataclass) — `host_runner.py:316-341`; carries `binary: str`, `args: list[str]`, `env: dict[str,str]`, `capabilities: HostCapabilities`, `cleanup_paths: tuple[Path,...]`, `env_allow: frozenset[str] | None`. Established via `TestHostInvocation::test_host_invocation_is_frozen` (`test_host_runner.py:1869-1879`) as the frozen-dataclass convention for value objects
- `CapabilityReport` (frozen dataclass) — `host_runner.py:379-391`; returned by `describe_capabilities()`, with `host`, `binary`, `version`, `capabilities: list[CapabilityEntry]`
- `CapabilityEntry` (frozen dataclass) — `host_runner.py:366-376`; `name`, `status: Literal["full", "partial", "unsupported"]`, `note`
- `CapabilityNotSupported` (`UserWarning` subclass) — `host_runner.py:277-285`; lets tests route mismatches through `pytest.warns(...)` and `warnings.simplefilter("error", ...)`
- `_HOST_RUNNER_REGISTRY: dict[str, type[HostRunner]]` — `host_runner.py:1995-2004`; the registration point; eight current entries (claude-code, codex, opencode, pi, gemini, omp, kimi-code, qwen)

### Signatures
- `runner.detect() -> bool` — `host_runner.py:400`; used by `resolve_host()`'s `_PROBE_ORDER` PATH scan
- `runner.build_streaming(prompt: str, working_dir: Path | None, resume: bool, agent: str | None, tools: list[str] | None, model: str | None, automation: AutomationContext | None, automation_profile: str | None, disable_background_tasks: bool, workspace_root: Path | None) -> HostInvocation` — `host_runner.py:402`; the long-running orchestration path
- `runner.build_blocking_json(prompt: str, model: str | None, json_schema: dict | None) -> HostInvocation` — `host_runner.py:404`; one-shot blocking JSON; used by all `evaluate_*` paths
- `runner.build_version_check() -> HostInvocation` — `host_runner.py:406`; only exempt call shape for the live-spawn guard
- `runner.build_detached(prompt: str) -> HostInvocation` — `host_runner.py:407`; spawn-and-go handoffs
- `runner.describe_capabilities() -> CapabilityReport` — `host_runner.py:409`; exposes capabilities over JSON via `cmd_capabilities()` (`cli/action.py:341`)

### Call Path
`resolve_host("fake-A")` → `_HOST_RUNNER_REGISTRY["fake-A"].detect()` → `FakeARunner.build_streaming(prompt)` → `HostInvocation_A`
`resolve_host("fake-B")` → `_HOST_RUNNER_REGISTRY["fake-B"].detect()` → `FakeBRunner.build_streaming(prompt)` → `HostInvocation_B`
Composition test → drives both `HostInvocation_A` and `HostInvocation_B` through `run_claude_command()` (`subprocess_utils.py:516`) → asserts each `isinstance(invocation, HostInvocation)` AND asserts the executor path consumed only the abstract `HostRunner` interface (never concrete class names or shape-specific fields).

### Decision Rules
N/A — no new decision logic introduced. The composition test asserts existing structural properties (`isinstance(x, HostRunner)`, `HostCapabilities` field values); it does not introduce a new gap kind, gate, exit-code condition, keyword/phrase list, numeric threshold, or classification rule.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

1. The second fake must register in `_HOST_RUNNER_REGISTRY` (`host_runner.py:1995`); without registry membership, the existing conformance parametrization (`test_host_conformance.py:103` over `list(_HOST_RUNNER_REGISTRY.keys())`) does not pick it up automatically, and the composition test loses its "drives both through the same executor paths" structure. Verification: `assert "fake-B" in hr._HOST_RUNNER_REGISTRY`
2. The second fake's `binary` field must NOT match any name in `HOST_BINARY_NAMES` (`host_runner.py:2028`); the live-spawn guard (`scripts/tests/conftest.py:353-397`) blocks `subprocess.run`/`Popen` on registered binary basenames. A `binary` of `"fake-divergent"` (not in `HOST_BINARY_NAMES`) keeps the composition test in-process. Verification: `"fake-divergent" not in HOST_BINARY_NAMES`
3. The composition test must drive both fakes through the same executor path — `run_claude_command` (`subprocess_utils.py:516`) for streaming, or `run_blocking_json` (`host_runner.py:2434`) for blocking JSON — rather than only calling `build_*` on each fake separately. A test that only calls `build_*` on each fake does not exercise the "multi-host layer touches only the abstract host interface" assertion. Verification: the test invokes a downstream consumer, not just the builder
4. The composition test's "touches only the abstract host interface" assertion should use `isinstance(invocation, HostRunner)` (the established pattern at `test_host_runner.py:679, 1024, 1105, 1163, 1303, 1484, 1676, 1862`) rather than asserting on concrete class names; that way the assertion holds regardless of which fakes are registered. Verification: grep for `isinstance(... , HostRunner)` rather than `isinstance(... , FakeARunner)`
5. The composition test must coexist with the existing `_install_no_live_host_cli` autouse guard (`scripts/tests/conftest.py:353-397`); only `build_version_check()` (`<binary> --version`) is exempt today (`scripts/tests/conftest.py:237-255`). The second fake must either set its `binary` to a name not in `HOST_BINARY_NAMES`, or never have the test consume the resulting `HostInvocation` via `subprocess.run`/`Popen`. Verification: `python -m pytest scripts/tests/conformance/ -v` passes with no `LiveHostCLISpawned` errors
6. The second fake must satisfy `HostRunner` structurally (`@runtime_checkable` Protocol at `host_runner.py:394`); tests asserting satisfaction already exist for every concrete runner (`test_host_runner.py:679, 1024, 1105, 1163, 1303, 1484, 1676, 1862`). Verification: `assert isinstance(FakeBRunner(), HostRunner)` is true
7. The composition test, once landed, becomes a load-bearing regression guard for the host-agnostic property — a future host addition that violates the invariant (e.g. asserts on a concrete type rather than the abstract Protocol) must fail this test. Verification: a hypothetical `BadRunner` that subclasses one of the fakes (introducing shape-specific access) fails the composition test
8. The composition test must produce divergent `HostCapabilities` profiles between the two fakes — different flag combinations on the six-field dataclass at `host_runner.py:288-313`. Same-shapes fakes do not satisfy the issue's premise. Verification: `assert FakeARunner().capabilities != FakeBRunner().capabilities`


## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md#little_loopshost_runner` | `HostRunner` is a `@runtime_checkable` Protocol — the composition test asserts satisfaction structurally, not against concrete class names |
| `docs/ARCHITECTURE.md` (host abstraction) | Captures the host-agnostic invariant: downstream code touches only the abstract interface, never concrete host class names |
| `.claude/CLAUDE.md` § Host CLI Abstraction | Enforces the host-agnostic property at the call-site level via `resolve_host()` — the divergent-fakes composition test guards the same invariant at the registry level |

## Session Log
- `/ll:decide-issue` - 2026-09-12T04:44:10 - `3967c497-38bc-427e-bf31-231e65faeadf.jsonl`
- `/ll:spike` - 2026-09-12T04:42:54 - `2fe9d3e8-5ada-4b6e-ae89-95fe8d84fff1.jsonl`
- `/ll:refine-issue` - 2026-09-12T03:58:11 - `e3bfc610-fb65-4e08-98ec-8d101d5a459d.jsonl`

## Spike Results

_Added by `/ll:spike` on 2026-09-11_

**Retired risks**

| Risk (from Outcome Risk Factors) | Proven by | Result |
|----------------------------------|-----------|--------|
| (a) Zero precedent — composing two divergent fakes through one executor path to prove interface-only access | `TestCompositionThroughExecutor::test_compose_threads_both_fakes_through_same_executor` + `TestExecutorTouchesOnlyAbstractInterface::*` | ✓ pass |
| (b) No existing test — asserts the host layer is genuinely shape-independent | `TestFakesAreDivergent::test_fakes_have_divergent_capabilities` + `test_fakes_have_divergent_action_vocabulary` | ✓ pass |
| Load-bearing regression guard — concrete-class drift caught by composition assertion | `TestRegressionGuard::test_bad_concrete_class_runner_breaks_composition` | ✓ pass |
| Isolation guard — spike does not depend on production executor | `TestSpikeIsolation::test_spike_does_not_import_subprocess_utils_run_claude_command` | ✓ pass |

**Spike location**: `scripts/tests/spike/host_compose/`
**Verification**: 16 spike tests pass + 281 host_runner unit tests pass + 20 conformance tests pass across 3 commands.
**Promotion**: move to `scripts/little_loops/spike/host_compose/` in a separate PR; the composition assertion is wired into FEAT-3455's conformance rewrite as the two-divergent-fake composition test the issue Design section calls for.
