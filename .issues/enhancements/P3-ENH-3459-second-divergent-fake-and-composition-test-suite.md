---
id: 3459
title: Second divergent fake host + composition test suite (TestCompositionThroughExecutor, TestExecutorTouchesOnlyAbstractInterface, TestRegressionGuard)
type: ENH
priority: P3
status: open
discovered_date: '2026-09-12'
labels: []
parent: ENH-3456
unproven_mechanism: true
spike_attempted: true
spike_completed: true
blocked_by:
- FEAT-3454
- FEAT-3455
relates_to:
- ENH-3453
- ENH-3460
---

## Summary

Decomposed from ENH-3456. Lands the second divergent fake host (promoted from the
`scripts/tests/spike/host_compose/` spike) and ships the composition test suite that
proves the host layer is genuinely shape-independent: a second fake whose action
vocabulary and observation structure disagree with the first, composed through the
same executor paths, with the test asserting the multi-host layer touches only the
abstract `HostRunner` Protocol and never a concrete shape. Includes resolving the
`_structured_output_args` carve-out scoping choice (approach a vs b).

## Parent Issue

Decomposed from [ENH-3456](../P3-ENH-3456-prove-host-agnosticism-with-two-deliberately-divergent-fakes-not-one.md):
"Prove host-agnosticism with two deliberately divergent fakes, not one"

A single fake proves the code runs; it cannot prove the code is agnostic, because that
one fake's action and observation shapes may be silently baked into the surface under
test. The assertion only becomes real with a second fake whose shapes deliberately
disagree with the first.

This child ships the mechanism. ENH-3460 (sibling) ships the drift-gate touchups.

## Why now

Timing-sensitive. Cheap to add while the fake host is still being built and its shape
has not hardened; progressively more expensive once code accretes around a single
fake's assumptions. Scope is one additional fake plus the composition test, not a
redesign of either.

## Design

- Promote the spike at `scripts/tests/spike/host_compose/` to production location
  (`scripts/little_loops/spike/host_compose/` per the Spike Results promotion note).
- One additional fake host whose action and observation shapes deliberately diverge
  from the first (FEAT-3454's fake): different action vocabulary, different
  observation structure, a different `HostCapabilities` profile.
- Register the second fake in `_HOST_RUNNER_REGISTRY` (`host_runner.py:1995-2004`) so
  the registry-driven parametrization at `test_host_conformance.py:103` picks it up
  automatically.
- A composition test that drives both fakes through the same executor paths and asserts
  the multi-host layer touches only the abstract host interface — never a concrete
  shape. Three new test classes:
  - `TestCompositionThroughExecutor`
  - `TestExecutorTouchesOnlyAbstractInterface`
  - `TestRegressionGuard`
- Resolve the `_structured_output_args` carve-out scoping choice (Program Design
  finding): the spike's runtime `_wrap_invocation` proxy is a novel mechanism (no
  in-tree precedent). Production composition test must either (a) avoid the carve-out
  path entirely (never call `run_blocking_json(..., schema=...)` from the composition
  test — the spike's choice), or (b) pin an explicit exception list in the audit
  wrapper naming the carve-out's binary comparisons. Choice is the implementer's.

## Key constraints (must hold)

- **`detect() -> False`** on the second fake — keeps the live-spawn guard inert and
  means the fake never claims PATH presence. Evidence: `fakes.py:55-57, 153-157`;
  live-spawn guard at `conftest.py:353-397`.
- **`binary` field non-collision** with `HOST_BINARY_NAMES` (`host_runner.py:2028-2030`)
  — the live-spawn guard blocks `subprocess.run`/`Popen` on registered binary
  basenames; only `<binary> --version` is exempt (`conftest.py:237-255`). The fake's
  `binary` MUST NOT match any real-host basename.
- **`**_: object` absorber** on each `build_*` method (ENH-3097 AC13 convention) so
  signature additions don't break existing tests. Evidence: `test_action.py:25-50`,
  `test_runner_spec.py:36-41`, `test_cli_harness.py:30-39`,
  `test_cli_doctor_install_checks.py:622-625`.
- **Structural Protocol satisfaction** via `isinstance(x, HostRunner)`
  (`host_runner.py:394-407` — `@runtime_checkable`). Composition test asserts via the
  Protocol, not concrete class names.

## Scope

This child covers:
- Spike promotion (5 files: `__init__.py`, `fakes.py`, `executor_shim.py`,
  `test_host_compose.py`, `.ll/spikes/spike-FEAT-3456.md`)
- Second-fake class definition with divergent `HostCapabilities`
- Registry registration in `_HOST_RUNNER_REGISTRY`
- New `test_satisfies_host_runner_protocol` entry for the second fake (mirrors the
  eight existing entries at `test_host_runner.py:679, 1024, 1105, 1163, 1303, 1484,
  1676, 1862`)
- New composition test classes (`TestCompositionThroughExecutor`,
  `TestExecutorTouchesOnlyAbstractInterface`, `TestRegressionGuard`) extending
  `test_host_conformance.py`
- Carve-out scoping resolution (approach a or b)
- `_HOST_BINARY` mapping for the second fake's binary in
  `test_host_conformance.py:52-61` (only if `shutil.which`-based skip-gating is
  desired; otherwise leave absent and the conformance test runs against the fake
  regardless of PATH — both paths are valid)

NOT in this child (handled by ENH-3460):
- Drift-gate touchups (`HOST_COMPATIBILITY.md`, `ARCHITECTURE.md`, `_remediation_hint`,
  `verify_host_map.py`, `test_has_all_eight_known_binaries` rename,
  `test_adapters.py` registry-presence, `__all__` / package re-export).

## Implementation Steps

1. Promote `scripts/tests/spike/host_compose/` to
   `scripts/little_loops/spike/host_compose/`. Move all 5 files
   (`__init__.py`, `fakes.py`, `executor_shim.py`, `test_host_compose.py`, plus the
   spike plan `.ll/spikes/spike-FEAT-3456.md`).
2. Define the second fake class with: (a) `**_: object` absorber on every `build_*`
   method, (b) `detect() -> False`, (c) `binary` field outside `HOST_BINARY_NAMES`,
   (d) deliberately divergent `HostCapabilities` profile (different flag combinations
   on the six-field dataclass at `host_runner.py:288-313` — same-shape fakes do not
   satisfy the issue's premise).
3. Register the second fake in `_HOST_RUNNER_REGISTRY` (`host_runner.py:1995-2004`).
   Verification: `assert "<fake-key>" in hr._HOST_RUNNER_REGISTRY`.
4. Add `test_satisfies_host_runner_protocol` for the second fake, mirroring the eight
   existing entries at `test_host_runner.py:679, 1024, 1105, 1163, 1303, 1484, 1676,
   1862` — single-line body `assert isinstance(<FakeRunner>(), HostRunner)`. Evidence:
   `test_host_runner.py:679-681, 1024-1025, 1105-1106, 1163-1164, 1303-1304, 1484-1485,
   1676-1677, 1862-1863`.
5. Add the new composition test classes (`TestCompositionThroughExecutor`,
   `TestExecutorTouchesOnlyAbstractInterface`, `TestRegressionGuard`) extending
   `test_host_conformance.py`. Each must drive both fakes through the same executor
   path — `run_claude_command` (`subprocess_utils.py:516`) for streaming or
   `run_blocking_json` (`host_runner.py:2434`) for blocking JSON — not just call
   `build_*` on each fake separately. Assert `isinstance(invocation, HostRunner)`
   (the established Protocol-satisfaction pattern), not concrete class names.
6. Resolve the carve-out scoping choice (Program Design finding). Either:
   - (a) Avoid `run_blocking_json(..., schema=...)` from the composition test
     entirely — preserves the spike's scoping; document the carve-out as excluded
     from the assertion's scope.
   - (b) Pin an exception list in the audit wrapper naming the carve-out's binary
     comparisons (`binary == "claude"`, `binary == "qwen"` at
     `host_runner.py:2365-2383`) and asserting no further binary-name branches exist
     in the executor chain.
   Both are valid. Choose and document the choice.
7. Add `_HOST_BINARY` mapping for the second fake's binary in
   `test_host_conformance.py:52-61` only if `shutil.which`-based skip-gating is
   desired. Otherwise leave absent (`_HOST_BINARY.get(host)` returns `None` and the
   conformance test proceeds without skipping).
8. Verify `python -m pytest scripts/tests/ -v` passes with no `LiveHostCLISpawn`
   errors (`conftest.py:400-427`); verify `python -m pytest
   scripts/tests/conformance/ -v` passes (composition test classes are exercised);
   verify the composition test catches a hypothetical `BadRunner` subclass that
   introduces shape-specific access (regression guard).

## Conventions in Force

- `HostRunner` is `@runtime_checkable` (`host_runner.py:394-407`); conformance via
  `isinstance(x, HostRunner)`.
- Test doubles are local module-level classes; no shared conftest helper for host
  fakes.
- The conformance suite parametrizes over `_HOST_RUNNER_REGISTRY.keys()`
  (`test_host_conformance.py:103`); registering a fake in the registry includes it
  automatically — no hand-extension needed.
- `_install_no_live_host_cli` (`scripts/tests/conftest.py:353-397`) blocks
  `subprocess.run`/`Popen` on binary basenames in `HOST_BINARY_NAMES`
  (`host_runner.py:2028-2030`); only `<binary> --version` is exempt
  (`conftest.py:237-255`).
- `HostCapabilities`, `HostInvocation`, `CapabilityReport`, `CapabilityEntry`,
  `AutomationContext` are all `@dataclass(frozen=True)`.
- `apply_host_cli_from_config()` (`host_runner.py:2581-2606`) sets
  `os.environ["LL_HOST_CLI"]` only when not already set (explicit-env precedence).
  Tests can pin `LL_HOST_CLI=<fake-key>` either via env or via
  `resolve_host(env={"LL_HOST_CLI": ...})`.

## Tests

- `scripts/tests/conformance/test_host_conformance.py` — extended with the three new
  composition test classes.
- `scripts/tests/test_host_runner.py` — new `test_satisfies_host_runner_protocol`
  entry for the second fake (mirrors eight existing entries).
- `scripts/tests/spike/host_compose/test_host_compose.py` — promoted into the
  production location as the seed for the composition test classes.

## Files to Modify

- `scripts/tests/spike/host_compose/` (5 files) → `scripts/little_loops/spike/host_compose/`
  (promotion)
- `scripts/little_loops/host_runner.py:1995-2004` — `_HOST_RUNNER_REGISTRY` (add
  second fake entry)
- `scripts/tests/conformance/test_host_conformance.py` — extend with three new
  composition test classes; optionally add `_HOST_BINARY` mapping
- `scripts/tests/test_host_runner.py` — add `test_satisfies_host_runner_protocol`
  for the second fake

## Related Issues (Dependencies)

- FEAT-3454 (open, P2) — provides the first fake host. ENH-3456 (and this child) is
  blocked until FEAT-3454 lands.
- FEAT-3455 (open, P2) — rewrites the conformance suite. The composition test
  extends this rewrite. ENH-3456 (and this child) is blocked until FEAT-3455 lands.
- ENH-3453 (open, P2) — collapses the runtime half of the host capability map onto a
  declarative source. Parallel work; not a strict dependency.
- ENH-3460 (open, P3, this decomposition) — drift-gate sync. Lands after; the drift
  gates will fail CI until the registry entry from this child exists.

## Reference Documentation

- Parent: `ENH-3456` — full design rationale, Program Design findings (audit-wrapper
  novelty, `_structured_output_args` carve-out, run_blocking_json field-access
  inventory), wiring-pass findings, integration map.
- `.claude/CLAUDE.md` § Host CLI Abstraction — `resolve_host()` invariant.
- `docs/reference/API.md#little_loopshost_runner` — `HostRunner` Protocol reference.

## Session Log
- `/ll:issue-size-review` - 2026-09-12T06:09:06 - `a6c3ba7b-8baf-4ae7-b742-fb9d4cbad25c.jsonl`
