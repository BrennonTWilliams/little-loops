# Spike Plan: FEAT-3456 — Prove host-agnosticism with two divergent fakes

## Context

ENH-3456's `unproven_mechanism: true` frontmatter flag plus the `⚠ Unproven
mechanism — borrowed pattern has no confirming in-tree usage site` note in the
issue's `### Codebase Research Findings` (line 40) lower outcome confidence.
Two canonical drivers apply:

**(a) Zero precedent in the codebase.** No in-tree pattern composes two
deliberately divergent host-shaped fakes through a shared executor path to
prove the layer under test touches only an abstract interface. The closest
analog is `scripts/tests/test_cross_host_baseline.py`, but it drives real
hosts via subprocess rather than in-process fakes — a different proof
(target system parity, not interface-only access). The "two divergent
dummies asserting only-interface access" pattern the issue Design section
borrows from is external to this repo.

**(b) No existing test exercises the risky core.** Every existing host fake
(`test_action.py:25` `FakeRunner`, `test_runner_spec.py:36`,
`test_cli_harness.py:30`, `test_cli_doctor_install_checks.py:622-625`) is a
single-shape stub whose action vocabulary and capability surface match the
real runner it shadows. Single-shape fakes prove a layer *runs*; they cannot
prove it is *agnostic* because the fake's shapes may be silently baked into
the surface under test (e.g. a downstream consumer that switches on a
capability flag present on the fake but absent on a real second host).

The spike must rule out: a composition assertion that "passes" only because
both fakes happen to share the surface that the executor reads, leaving the
interface-only-access invariant unproven for any real second host.

## Approach

Build a `host_compose` library under `scripts/tests/spike/host_compose/`
that defines **two** `HostRunner`-shaped classes whose action vocabulary
(parameter lists on `build_*`) and capability surface (six `HostCapabilities`
flags) **deliberately disagree** — a "verbose" fake that consumes the full
`build_streaming(prompt, working_dir, resume, agent, tools, model,
automation, automation_profile, disable_background_tasks, workspace_root)`
surface and exposes all six `HostCapabilities` flags True, and a "minimal"
fake that accepts a slimmed parameter set (only `prompt`/`model`) and exposes
all six flags False. A `compose_through_executor(fakes)` driver threads both
`HostInvocation`s through an in-process executor shim that mirrors the
producer/consumer contract of `subprocess_utils.run_claude_command` (lines
516–680) — argv from `binary`/`args`, env merged from `env`, capabilities
read from the returned `HostInvocation.capabilities` only — and the test
class asserts the shim touched only the abstract `HostRunner` Protocol fields
(`binary`, `args`, `env`, `capabilities`) and never any concrete shape (no
attribute access beyond `HostInvocation`'s public surface, no `isinstance(x,
FakeVerboseRunner)` anywhere in the shim). The executor shim itself lives in
the spike library, NOT in production — the spike proves the *mechanism*
(two-divergent-fake composition asserting interface-only access), not the
production wiring, which is FEAT-3455's job.

What is faked: the `run_claude_command` selector machinery (replaced by an
in-process dict-of-dicts consumer that only reads `HostInvocation` public
fields). What is real: the `HostRunner` Protocol, `HostInvocation`,
`HostCapabilities`, and `CapabilityReport` dataclasses imported from
`scripts/little_loops/host_runner.py` (production code is read-only; the
spike imports but does not modify it — proves the spike cannot accrete
shape-specific dependencies on the production surface).

## Critical files

**Read-only production references** (the spike imports from but never
modifies these):
- `scripts/little_loops/host_runner.py:394` — `HostRunner` Protocol
  (`@runtime_checkable`); the abstract interface the composition test
  asserts against
- `scripts/little_loops/host_runner.py:288-313` — `HostCapabilities`
  frozen dataclass (six flags)
- `scripts/little_loops/host_runner.py:316-341` — `HostInvocation` frozen
  dataclass (the surface the executor shim reads)
- `scripts/little_loops/host_runner.py:379-391` — `CapabilityReport` and
  `CapabilityEntry` (`host_runner.py:366-376`)
- `scripts/little_loops/subprocess_utils.py:516-680` — `run_claude_command`
  selector machinery (the contract the executor shim mirrors; not imported,
  only inspected for the field-access pattern)

**New spike paths** (created in this skill):
- `scripts/tests/spike/host_compose/__init__.py`
- `scripts/tests/spike/host_compose/fakes.py` — `VerboseFakeRunner`,
  `MinimalFakeRunner`, divergent in shape and capability profile
- `scripts/tests/spike/host_compose/executor_shim.py` — in-process executor
  shim that reads only `HostInvocation` public fields
- `scripts/tests/spike/host_compose/test_host_compose.py` — AC test class

## Implementation

```
scripts/tests/spike/host_compose/
├── __init__.py
├── fakes.py                    # VerboseFakeRunner + MinimalFakeRunner
├── executor_shim.py            # in-process executor reading HostInvocation only
└── test_host_compose.py        # AC test class
```

**Public API sketch:**

```python
# fakes.py
class VerboseFakeRunner:
    """Fake that consumes the full build_streaming parameter surface."""
    name: str = "fake-verbose"
    def detect(self) -> bool: return False  # never claims PATH presence
    def build_streaming(self, *, prompt, working_dir=None, resume=False,
                        agent=None, tools=None, model=None,
                        automation=None, automation_profile=None,
                        disable_background_tasks=False, workspace_root=None
                        ) -> HostInvocation: ...
    def build_blocking_json(self, *, prompt, model=None, json_schema=None
                            ) -> HostInvocation: ...
    def build_version_check(self) -> HostInvocation: ...
    def build_detached(self, prompt) -> HostInvocation: ...
    def describe_capabilities(self) -> CapabilityReport: ...
    # All six HostCapabilities flags True

class MinimalFakeRunner:
    """Fake with deliberately slimmer action vocabulary and zero caps."""
    name: str = "fake-minimal"
    # Accepts only prompt + model on build_streaming; all caps False
    ...

# executor_shim.py
def execute_invocation(invocation: HostInvocation) -> dict[str, Any]:
    """In-process shim mirroring run_claude_command's field-access pattern.

    Reads ONLY HostInvocation public fields (binary, args, env,
    capabilities). Asserts (in test mode) that no concrete-class attribute
    is touched.
    """
    ...
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_verbose_fake_satisfies_host_runner_protocol` | Risk (a): protocol satisfaction for divergent shape | behavior |
| `test_minimal_fake_satisfies_host_runner_protocol` | Risk (a): protocol satisfaction for slimmer shape | behavior |
| `test_fakes_have_divergent_capabilities` | Risk (b): fakes disagree on all six caps flags | behavior |
| `test_fakes_have_divergent_action_vocabulary` | Risk (b): verbose accepts full kwarg set; minimal accepts only prompt/model | behavior |
| `test_compose_threads_both_fakes_through_same_executor` | Risk (a): one executor path serves both fakes | behavior |
| `test_executor_shim_touches_only_host_invocation_public_fields` | Risk (a): no concrete-class attribute access in executor | behavior |
| `test_executor_shim_touches_only_host_runner_protocol_attributes` | Risk (a): executor reads only HostRunner Protocol surface | behavior |
| `test_executor_returns_capabilities_from_host_invocation` | Risk (b): capability flags round-trip through executor for both fakes | behavior |
| `test_bad_concrete_class_runner_breaks_composition` | Risk (b): a runner that subclasses VerboseFakeRunner (introducing shape-specific access) fails the composition assertion — load-bearing regression guard | regression |
| `test_spike_does_not_import_subprocess_utils_run_claude_command` | Isolation guard: spike is in-process and does not depend on the production executor (proves the mechanism in isolation, not the integration) | regression |
| `test_spike_fakes_register_in_host_runner_registry` | Registry-driven parametrization: fake fakes show up in `_HOST_RUNNER_REGISTRY` so future FEAT-3455 conformance parametrization picks them up | behavior |

## Verification

All commands must exit 0 (foreground-blocking, never backgrounded):

```bash
python -m pytest scripts/tests/spike/host_compose/ -v
python -m pytest scripts/tests/test_host_runner.py -v
python -m pytest scripts/tests/conformance/test_host_conformance.py -v
```

The first command runs the spike's AC suite. The second confirms the spike's
two fakes (registered in `_HOST_RUNNER_REGISTRY`) do not break the
per-runner `test_satisfies_host_runner_protocol` family or any other
host_runner unit test. The third confirms the conformance suite's
parametrization over `_HOST_RUNNER_REGISTRY.keys()` still resolves correctly
when the registry gains two new fake entries (the parametrization list is
extended; no assertion is broken).

## Out of Scope

- Modifying `scripts/little_loops/host_runner.py` (read-only in this skill;
  FEAT-3454 lands the first fake there, FEAT-3455 rewrites the conformance
  suite — both blocked_by FEAT-3456 in this issue's `## Related Issues`)
- Modifying `scripts/little_loops/subprocess_utils.py` (the production
  executor path; the spike proves the mechanism with an in-process shim)
- Wiring the composition test into the production conformance suite
  (FEAT-3455's job; the spike lives under `scripts/tests/spike/` only)
- Any live-binary spawn — the spike is in-process throughout, both fakes
  return `detect() -> False` so they never claim PATH presence

## Promotion

On acceptance, promote the proven mechanism from
`scripts/tests/spike/host_compose/` to `scripts/little_loops/spike/host_compose/`
in a separate PR (mirrors the ENH-2565 spike-promotion pattern). The
promoted library is then wired into FEAT-3455's conformance rewrite as the
two-divergent-fake composition assertion the issue Design section calls for.