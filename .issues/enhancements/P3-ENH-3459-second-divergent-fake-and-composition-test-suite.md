---
id: ENH-3459
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

Decomposed from ENH-3456. Adds a second test-only host runner whose action
vocabulary and capability profile deliberately disagree with FEAT-3454's
`FakeHostRunner`, drives both through the **unpatched production executor**
(`run_claude_command`, `run_blocking_json`) against the same directive script, and
asserts the executor produces the same observation for both. A second, AST-based
test pins that the executor reads only the abstract `HostRunner` / `HostInvocation`
surface, with the `_structured_output_args` binary-literal carve-out as the one
named exception. Ships every change needed to keep `main` green after the second
registry entry; ENH-3460 carries only the un-gated doc prose that follows.

## Parent Issue

Decomposed from [ENH-3456](../P3-ENH-3456-prove-host-agnosticism-with-two-deliberately-divergent-fakes-not-one.md):
"Prove host-agnosticism with two deliberately divergent fakes, not one"

A single fake proves the code runs; it cannot prove the code is agnostic, because
that one fake's shapes may be silently baked into the surface under test. The
assertion only becomes real with a second fake whose shapes disagree with the first.

## Why now

Timing-sensitive. Cheap while FEAT-3454's fake is fresh and FEAT-3455's helpers are
new; progressively more expensive once code accretes around a single fake's
assumptions. Scope is one runner class, one test module, one constant entry, and the
doc rows the gates demand.

## Current Behavior

After FEAT-3454 and FEAT-3455 land, the registry holds eight real runners plus one
fake (`fake`, binary `ll-fake-host`). The conformance suite drives the executor
against that single fake. Nothing asserts that `run_claude_command` /
`run_blocking_json` would behave identically for a runner with a different argv
vocabulary, empty env, and an all-`False` capability profile; nothing mechanically
pins which `HostInvocation` / `HostRunner` attributes the executor is allowed to
read, or that `_structured_output_args` is the only binary-literal branch. The
proof of both lives only in `scripts/tests/spike/host_compose/` against an
in-process shim that never touches the production executor.

## Expected Behavior

- `resolve_host_named("fake-minimal")` returns `FakeMinimalHostRunner`; its
  `build_streaming(prompt=…, working_dir=…, automation=…)` returns
  `HostInvocation(binary="ll-fake-host", args=[prompt], env={}, capabilities=all-False)`.
- `python -m pytest scripts/tests/conformance/test_host_composition.py` passes:
  the same directive script through `fake` and `fake-minimal` yields equal
  `Observed.kinds` / `result_seen` / `returncode`; the AST checks over the real
  executor sources pass; the synthetic regression snippets each fail the checker
  with a message naming the function and attribute/literal.
- `main` is green in the same commit: `TEST_ONLY_HOSTS == {"fake", "fake-minimal"}`,
  the `HOST_COMPATIBILITY.md` tier table has a `fake-minimal` row, `_HOST_BINARY`
  maps it to `ll-fake-host`, `scripts/tests/spike/host_compose/` no longer exists,
  and `.ll/spikes/spike-FEAT-3456.md` ends with a "Promoted by ENH-3459" footer
  naming `test_host_composition.py` as the production home of each spike test.

## Decisions (resolved 2026-09-12 review; do not reopen)

1. **The second fake is a real-executable runner, like the first.** FEAT-3454's
   design decision ("the fake must be a real executable") applies: the executor's
   only consumer path is `subprocess.Popen([invocation.binary, *invocation.args])`,
   so an in-process shim proves nothing about production. The spike's
   `executor_shim.py` and `_wrap_invocation` proxy are **retired, not promoted**.
2. **It reuses `ll-fake-host`.** `binary="ll-fake-host"` — the same console script
   FEAT-3454 ships. `main()` ignores every flag and takes the prompt as the last
   positional, so a divergent argv shape needs no second executable. Consequences:
   `HOST_BINARY_NAMES` is unchanged (no binary-count test edit), the live-spawn
   carve-out already covers it (it is derived from `TEST_ONLY_BINARIES`), and no
   `pyproject.toml` edit. Rejected: a second console script — a second entry point
   for zero extra coverage.
3. **Where it diverges** (relative to `FakeHostRunner`, not to the spike's other fake):
   - *Action vocabulary (argv)*: `FakeHostRunner` emits `["-p", prompt, …]` with
     model/agent/tools/output-format flags; `FakeMinimalHostRunner` emits `[prompt]`
     only — no `-p`, no flags, every non-prompt kwarg ignored on the argv side.
   - *Env*: does **not** call `_apply_automation_env`; `invocation.env == {}` always.
   - *Capabilities*: class default all six flags `False` (FEAT-3454's default is
     `streaming=True`); same `capabilities=` constructor override for symmetry.
   - *Observation structure* is **script-driven, not fake-driven**: both fakes forward
     the prompt verbatim, so the directive script decides the event stream. The
     parent's "different observation structure" is satisfied by feeding both fakes
     the same script and asserting identical `Observed` — the executor cannot be
     reading anything the fakes disagree on. Stream-dialect divergence (claude-style
     `result` vs codex-style `turn.completed` terminal) is FEAT-3455 Tier 2's job.
   - *Kwargs*: declared explicitly, keyword-only, full Protocol set — **not**
     `**_: object`. The production executor calls `build_streaming(prompt=, working_dir=,
     automation=, …)`; a slimmer signature would `TypeError` before Popen. The spike's
     "accepts only prompt/model" divergence only worked against the shim.
     (`CapturingRunner` precedent: `test_runner_spec.py:44-58`.)
4. **Class lives in `host_runner.py`** next to `FakeHostRunner`, registered as
   `"fake-minimal"`, added to `TEST_ONLY_HOSTS`, exported from `__all__` and
   `little_loops/__init__.py`. Rejected: `scripts/little_loops/spike/` — no such
   package exists, the cited ENH-2565 precedent promoted production code (not test
   doubles), hatch would ship `test_host_compose.py` in the wheel, and a registry
   literal importing from a module that imports `host_runner` is a circular import.
5. **"Touches only the abstract interface" is an AST check, not a runtime proxy.**
   In-tree precedent for consumer-surface enforcement is AST walk + pinned allow-list
   (`_ALLOWED_CALLERS`, `test_advisor.py:694-724`; `_ALLOWED_UNTOUCHED_SECTIONS`,
   `test_init_audit_fixes.py:1300-1331`). No runtime attribute-proxy exists anywhere
   in the repo, and a proxy on a frozen dataclass through a real Popen path is
   fragile. The carve-out scoping choice from the parent resolves as **(b) pinned
   exception list**: `_structured_output_args` (`host_runner.py:2365-2383`) is the
   one function allowed to compare `.binary` to string literals, and the allowed
   literals are pinned (`{"claude", "qwen"}`). Any new binary-name branch anywhere in
   the executor chain fails the test with the offending function and literal.
6. **Ported, not moved.** Spike classes are rewritten against FEAT-3455's helpers;
   `scripts/tests/spike/host_compose/` is deleted in this change and the spike plan
   gets a "Promoted by ENH-3459" footer. `TestSpikeIsolation` is dropped (it asserts
   the opposite of decision 1).

## Design

### `FakeMinimalHostRunner` (`host_runner.py`, after `FakeHostRunner`)

- `name = "fake-minimal"`; `capabilities = HostCapabilities()` (all `False`);
  `__init__(capabilities: HostCapabilities | None = None)` mirrors FEAT-3454.
- `detect() -> False`; not in `_PROBE_ORDER` (covered by FEAT-3454's
  `test_test_only_hosts_are_never_probed` once `"fake-minimal"` is in `TEST_ONLY_HOSTS`).
- Five `build_*` methods, full keyword-only Protocol signature, each returning
  `HostInvocation(binary="ll-fake-host", args=[prompt], env={}, capabilities=self.capabilities)`
  (`build_version_check` → `args=["--version"]`; `build_detached` → `[prompt]`;
  `build_blocking_json(prompt, model, json_schema)` → `[prompt]`, schema ignored —
  `_structured_output_args` appends `--json-schema` itself when the override sets
  `structured_output=True`).
- `describe_capabilities()` → `CapabilityReport(host="fake-minimal", binary="ll-fake-host",
  version="0.0.0-fake-minimal", …)` with all six entries `"unsupported"`.

### `scripts/tests/conformance/test_host_composition.py` (new, `conformance` marker)

Imports FEAT-3455's `_run_and_capture`, `Observed`, `assert_event_kinds` from
`test_host_conformance.py`; `_FAKES = ("fake", "fake-minimal")`.

- `TestFakesAreDivergent` — pins the divergence so a future edit cannot quietly make
  the fakes agree: argv of `build_streaming` differs (one contains `"-p"`, the other
  is exactly `[prompt]`); `invocation.env` differs under `automation=`; default
  `capabilities` differ on every flag; both share `binary`; both keys are in
  `TEST_ONLY_HOSTS`; `isinstance(cls(), HostRunner)` for both.
- `TestCompositionThroughExecutor` — for each of three directive scripts (happy path;
  `result error=`; `exit 2` before terminal), `_run_and_capture` on both fakes and
  assert `Observed.kinds`, `result_seen`, `completed.returncode` are **equal across
  fakes**. One case runs `run_blocking_json` on both with `capabilities=
  HostCapabilities(structured_output=True)` and asserts the same parsed dict.
- `TestExecutorTouchesOnlyAbstractInterface` — AST over
  `inspect.getsource(run_claude_command)` and `inspect.getsource(run_blocking_json)`:
  - attribute reads on the name bound to the invocation ⊆
    `_ALLOWED_INVOCATION_ATTRS = {"binary", "args", "env", "capabilities", "cleanup_paths", "env_allow"}`
    (the spike's set was missing the last two — parent finding, `host_runner.py:2500-2501`);
  - attribute reads on the name bound to the runner ⊆ `HostRunner` Protocol members
    (promotes the spike's declared-but-unenforced `ALLOWED_RUNNER_PROTOCOL_ATTRS`);
  - no `isinstance(_, <ConcreteRunner>)` in either function;
  - across `host_runner.py` and `subprocess_utils.py` module sources, every
    `Compare` whose left side is an attribute/name `binary` against a `str` constant
    sits inside a function in `_ALLOWED_BINARY_LITERAL_SITES = {"_structured_output_args": {"claude", "qwen"}}`
    and uses only the pinned literals.
- `TestRegressionGuard` — the same checker functions run over synthetic source
  snippets and must report: `invocation.session_id` read; `isinstance(runner,
  FakeHostRunner)`; `if invocation.binary == "ll-fake-host":` in a function not in
  the allow-list; a pinned function using an unpinned literal. Each failure message
  names function + attribute/literal.

## Program Design

### Types
- `FakeMinimalHostRunner` — class in `host_runner.py`; `name: str = "fake-minimal"`;
  `capabilities: HostCapabilities` (instance, defaults to `HostCapabilities()`).
- Test-module allow-lists (`test_host_composition.py`):
  `_ALLOWED_INVOCATION_ATTRS: frozenset[str]`, `_ALLOWED_RUNNER_ATTRS: frozenset[str]`
  (derived from `HostRunner.__protocol_attrs__` where available, else pinned),
  `_ALLOWED_BINARY_LITERAL_SITES: dict[str, frozenset[str]]`.

### Signatures
- `FakeMinimalHostRunner.__init__(self, capabilities: HostCapabilities | None = None) -> None`
- `build_streaming(self, *, prompt: str, working_dir: Path | None = None, resume: bool = False, agent: str | None = None, tools: list[str] | None = None, model: str | None = None, automation: AutomationContext | None = None, automation_profile: str | None = None, disable_background_tasks: bool = False, workspace_root: Path | None = None) -> HostInvocation` — every kwarg except `prompt` ignored.
- `build_blocking_json(self, *, prompt: str, model: str | None = None, json_schema: dict[str, Any] | None = None) -> HostInvocation`
- `build_version_check(self) -> HostInvocation`; `build_detached(self, *, prompt: str, **kw) -> HostInvocation` — match FEAT-3454's `FakeHostRunner` signatures exactly.
- `describe_capabilities(self) -> CapabilityReport`
- `_invocation_attr_reads(src: str, param: str = "invocation") -> set[str]` — attribute names read on `param` (AST `Attribute` whose value is `Name(param)`).
- `_runner_attr_reads(src: str, param: str = "runner") -> set[str]`
- `_binary_literal_compares(src: str) -> list[tuple[str, str]]` — `(enclosing_function, literal)` for each `Compare` with `.binary`/`binary` on the left and a `str` `Constant` on the right.
- `_isinstance_targets(src: str) -> set[str]` — second-arg names of every `isinstance` call.

### Call Path
`resolve_host_named("fake-minimal")` → `FakeMinimalHostRunner.build_streaming(prompt=script)` → `HostInvocation(binary="ll-fake-host", args=[script], env={})` → `run_claude_command` → `subprocess.Popen` (guard carve-out via `TEST_ONLY_BINARIES`) → `ll-fake-host main()` → `parse_directives` → `emit` → consumer callbacks → `_run_and_capture` → `Observed` → compared against the `fake` run of the same script.

## Behavior Parity

Spike tests (`scripts/tests/spike/host_compose/test_host_compose.py`) → production
home, or dropped with reason:

| Spike test | Production |
|---|---|
| `TestProtocolSatisfaction::*` | `test_host_runner.py::TestFakeMinimalHostRunner::test_satisfies_host_runner_protocol` (the `fake` half is FEAT-3454's) |
| `TestFakesAreDivergent::test_fakes_have_divergent_capabilities` | `test_host_composition.py::TestFakesAreDivergent` — same assertion, against `fake` vs `fake-minimal` |
| `TestFakesAreDivergent::test_fakes_have_divergent_action_vocabulary` | `TestFakesAreDivergent` — argv-shape form (`"-p"` present vs `[prompt]`), since both accept the full kwarg set (decision 3) |
| `TestFakesAreDivergent::test_fakes_have_distinct_binary_names` | **Dropped** — decision 2: the fakes share `ll-fake-host` on purpose; replaced by "both in `TEST_ONLY_HOSTS`, same binary" |
| `TestFakesAreDivergent::test_fake_binaries_are_not_in_host_binary_names` | **Inverted** — the binary *is* in `HOST_BINARY_NAMES` and carved out via `TEST_ONLY_BINARIES`; covered by FEAT-3454's guard tests |
| `TestCompositionThroughExecutor::test_compose_threads_both_fakes_through_same_executor` | `TestCompositionThroughExecutor` — real `run_claude_command` via `_run_and_capture`, equal `Observed` |
| `TestCompositionThroughExecutor::test_executor_returns_capabilities_from_host_invocation` | `TestCompositionThroughExecutor` `run_blocking_json` case with `structured_output=True` override |
| `TestExecutorTouchesOnlyAbstractInterface::*` (runtime proxy) | `TestExecutorTouchesOnlyAbstractInterface` — AST form over the real executor sources (decision 5) |
| `TestRegressionGuard::test_bad_concrete_class_runner_breaks_composition` | `TestRegressionGuard` — synthetic-snippet form; same intent (a shape-specific consumer is caught) |
| `TestSpikeIsolation::test_spike_does_not_import_subprocess_utils_run_claude_command` | **Dropped** — asserts the opposite of decision 1 |
| `TestSpikeIsolation::test_spike_fakes_register_in_host_runner_registry` | `TestFakesAreDivergent` — `"fake-minimal" in _HOST_RUNNER_REGISTRY` and in `TEST_ONLY_HOSTS` |
| `test_allowed_invocation_attrs_matches_host_invocation_public_fields` | `TestExecutorTouchesOnlyAbstractInterface` — `_ALLOWED_INVOCATION_ATTRS == {f.name for f in fields(HostInvocation)}` (now includes `cleanup_paths`, `env_allow`) |

`executor_shim.py` and `fakes.py` have no production counterpart by design; the
real executor and `host_runner.py` classes replace them.

## Key constraints (must hold)

- `binary` stays `"ll-fake-host"`; never `sys.executable`, never a real-host basename
  (`HOST_BINARY_NAMES`, `host_runner.py:2028-2030`).
- `"fake-minimal"` in `TEST_ONLY_HOSTS` **in the same commit** as the registry entry —
  the remediation hint, guard carve-out, and count-free binary tests from FEAT-3454
  all key off it.
- `docs/reference/HOST_COMPATIBILITY.md` `## Host tiers` gains a `fake-minimal` row
  **in the same commit** — `test_host_tier_table_matches_runner_registry`
  (`test_wiring_guides_and_meta.py:381-392`) asserts strict equality and would
  otherwise turn `main` red for every local-editable project.
- Composition tests use `_run_and_capture` (real Popen), never a patched executor.
- Composition tests skip with reason when `shutil.which("ll-fake-host") is None`
  (non-editable installs), matching FEAT-3455.

## Scope Boundaries

In:
- `FakeMinimalHostRunner` class, registry entry, `TEST_ONLY_HOSTS` entry, exports.
- `test_satisfies_host_runner_protocol` + `TestFakeMinimalHostRunner` argv/env/
  capability tests in `test_host_runner.py` (follow `TestFakeHostRunner`).
- `test_host_composition.py` with the four classes above.
- `_HOST_BINARY["fake-minimal"] = "ll-fake-host"` in `test_host_conformance.py`
  (matches FEAT-3454's `"fake"` entry; skip-not-fail on non-editable installs).
- `HOST_COMPATIBILITY.md` tier-table row (gated).
- Delete `scripts/tests/spike/host_compose/`; footer on `.ll/spikes/spike-FEAT-3456.md`.

Out (ENH-3460): un-gated prose — `ARCHITECTURE.md` Host Runner Layer row, `API.md`
concrete-runners row, `CONFORMANCE.md` section describing the composition suite,
`TESTING.md` note.

## Implementation Steps

1. `FakeMinimalHostRunner` in `host_runner.py`; registry entry; `TEST_ONLY_HOSTS |=
   {"fake-minimal"}`; `__all__` + package re-export. Unit tests first (TDD):
   Protocol check, argv is exactly `[prompt]`, env empty under `automation=`,
   default capabilities all `False`, override propagates to all five `build_*`.
2. `HOST_COMPATIBILITY.md` tier-table row (test-only). Run
   `python -m pytest scripts/tests/test_wiring_guides_and_meta.py scripts/tests/test_host_runner.py scripts/tests/test_conftest_cap.py` — must be green before step 3.
3. `test_host_composition.py::TestFakesAreDivergent` and
   `TestCompositionThroughExecutor` against FEAT-3455's helpers; `_HOST_BINARY` entry.
4. AST checkers as module-level functions (`_invocation_attr_reads(src) -> set[str]`,
   `_runner_attr_reads(src)`, `_binary_literal_compares(src) -> list[(func, literal)]`,
   `_isinstance_targets(src)`); `TestExecutorTouchesOnlyAbstractInterface` over the
   real sources; `TestRegressionGuard` over synthetic snippets.
5. Delete the spike package; append the promotion footer to the spike plan.
6. `python -m pytest scripts/tests/` (no `LiveHostCLISpawn` hits), `python -m pytest
   scripts/tests/conformance/ -v`, `ll-verify-host-map`, mypy, ruff.

## Conventions in Force

- `HostRunner` is `@runtime_checkable` (`host_runner.py:394-407`); conformance via
  `isinstance(x, HostRunner)`.
- `build_*` are keyword-only with explicit kwargs (FEAT-3454 Conventions;
  `CapturingRunner`, `test_runner_spec.py:44-58`).
- Registered-but-not-probed precedent: OpenCodeRunner (`host_runner.py:1033-1042`).
- Live-spawn guard: `_install_no_live_host_cli` (`conftest.py:353-397`) keyed on
  `HOST_BINARY_NAMES`, carve-out from `TEST_ONLY_BINARIES` (FEAT-3454).
- AST allow-list precedent: `_ALLOWED_CALLERS` (`test_advisor.py:694-724`).
- Frozen dataclasses: `HostCapabilities`, `HostInvocation`, `CapabilityReport`,
  `CapabilityEntry`, `AutomationContext`.

## Tests

- `scripts/tests/conformance/test_host_composition.py` (new) — four classes above.
- `scripts/tests/test_host_runner.py` — `TestFakeMinimalHostRunner` incl.
  `test_satisfies_host_runner_protocol` (mirrors the entries at `:679, 1024, 1105,
  1163, 1303, 1484, 1676, 1862` and FEAT-3454's `TestFakeHostRunner`).
- `scripts/tests/conformance/test_host_conformance.py` — constructability and Tier 1
  tests auto-extend to `fake-minimal` via registry parametrization.

## Files to Modify

- `scripts/little_loops/host_runner.py` — `FakeMinimalHostRunner`; `_HOST_RUNNER_REGISTRY`;
  `TEST_ONLY_HOSTS`; `__all__`
- `scripts/little_loops/__init__.py` — re-export
- `scripts/tests/test_host_runner.py` — `TestFakeMinimalHostRunner`
- `scripts/tests/conformance/test_host_composition.py` — new
- `scripts/tests/conformance/test_host_conformance.py` — `_HOST_BINARY` entry
- `docs/reference/HOST_COMPATIBILITY.md` — tier-table row
- `scripts/tests/spike/host_compose/` — delete; `.ll/spikes/spike-FEAT-3456.md` — footer

## Impact

- **Priority (P3)**: closes the "single fake proves it runs, not that it is agnostic"
  gap from the parent; first mechanical pin on the executor's read surface, so a
  future host port that adds `if invocation.binary == "newhost":` outside
  `_structured_output_args` fails in the unit suite, not in review.
- Zero user-facing change: `fake-minimal` is a `TEST_ONLY_HOSTS` member, absent from
  `_PROBE_ORDER` and from the remediation hint.
- Retires the spike package (≈600 lines) in favour of ≈150 lines of production
  runner + one test module.

## Status

Open. Blocked until FEAT-3454 and FEAT-3455 merge; re-anchor helper names and line
references against the landed files before starting step 1.

## Related Issues (Dependencies)

- FEAT-3454 (open, P2) — `FakeHostRunner`, `ll-fake-host`, `TEST_ONLY_HOSTS` /
  `TEST_ONLY_BINARIES`, derived guard carve-out, count-free binary tests. Hard block.
- FEAT-3455 (open, P2) — `_run_and_capture`, `Observed`, `assert_event_kinds`,
  `live_conformance`. Hard block; re-anchor helper names against the landed file.
- ENH-3460 (open, P3) — un-gated doc prose after this lands.
- ENH-3453 (open, P2) — declarative capability map; parallel, not a dependency. If
  it lands first, the class-level `capabilities` default here should come from the
  same source as the real runners'.

## Reference Documentation

- Parent `ENH-3456` — design rationale, Program Design findings (audit-wrapper
  novelty, carve-out inventory, `run_blocking_json` field-access inventory, missing
  `cleanup_paths`/`env_allow` in the spike allow-list).
- `.claude/CLAUDE.md` § Host CLI Abstraction.
- `docs/reference/API.md#little_loopshost_runner`.
- `.ll/spikes/spike-FEAT-3456.md` — spike plan; mechanism proven in-process, ported
  here to the real executor.

## Session Log
- `/ll:issue-size-review` - 2026-09-12T06:09:06 - `a6c3ba7b-8baf-4ae7-b742-fb9d4cbad25c.jsonl`
- Manual review rewrite - 2026-09-12 - resolved six decisions (real-executable second fake sharing `ll-fake-host`, explicit kwargs, class in `host_runner.py`, AST-based interface check with pinned carve-out, port-not-move, gated doc row owned here); took the gated drift items back from ENH-3460
