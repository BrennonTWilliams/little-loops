---
id: ENH-3459
title: Second divergent fake host + composition test suite (TestCompositionThroughExecutor,
  TestExecutorTouchesOnlyAbstractInterface, TestRegressionGuard)
type: ENH
priority: P3
status: open
discovered_date: '2026-09-12'
labels: []
parent: ENH-3456
unproven_mechanism: true
spike_attempted: true
spike_completed: true
blocked_by: []
relates_to:
- ENH-3453
- ENH-3460
confidence_score: 80
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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

Decomposed from [ENH-3456](P3-ENH-3456-prove-host-agnosticism-with-two-deliberately-divergent-fakes-not-one.md):
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
  `HostInvocation(binary="ll-fake-host", args=["run", prompt], env={}, capabilities=all-False)`.
- `python -m pytest scripts/tests/conformance/test_host_composition.py` passes:
  the same directive script through `fake` and `fake-minimal` yields equal
  `Observed.kinds` / `result_seen` / `returncode`; the AST checks over the real
  executor sources pass; the synthetic regression snippets each fail the checker
  with a message naming the function and attribute/literal.
- `main` is green in the same commit: `TEST_ONLY_HOSTS == {"fake", "fake-minimal"}`,
  the `HOST_COMPATIBILITY.md` tier table has a `fake-minimal` row, `_HOST_BINARY`
  maps it to `ll-fake-host`, `_STREAM_SHAPE` has a `fake-minimal` row,
  `test_golden_path_behavior` runs it unconditionally (keyed on `TEST_ONLY_HOSTS`,
  not the `"fake"` literal), `scripts/tests/spike/host_compose/` no longer exists,
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
   - *Action vocabulary (argv)*: the landed `FakeHostRunner` already emits bare
     `[prompt]` (`host_runner.py:2098`, no `-p`, no flags — an earlier draft of this
     issue assumed `["-p", prompt, …]`, which never landed). `FakeMinimalHostRunner`
     therefore emits a subcommand-style `["run", prompt]` — a leading positional
     verb the fake executable ignores, prompt last so `main()`'s no-fence
     `argv[-1]` fallback still resolves it. Every non-prompt kwarg is ignored on
     the argv side. The divergence pinned by `TestFakesAreDivergent` is
     `args == [prompt]` vs `args == ["run", prompt]`.
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
   exception list**: `_structured_output_args` (`host_runner.py:2530-2548`) is the
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
- Four `build_*` methods (`build_streaming`, `build_blocking_json`,
  `build_version_check`, `build_detached` — the full Protocol set; `detect` and
  `describe_capabilities` are the other two members), full keyword-only Protocol
  signature, each returning
  `HostInvocation(binary="ll-fake-host", args=["run", prompt], env={}, capabilities=self.capabilities)`
  (`build_version_check` → `args=["--version"]`; `build_detached` → `["run", prompt]`;
  `build_blocking_json(prompt, model, json_schema)` → `["run", prompt]`, schema ignored —
  `_structured_output_args` appends `--json-schema` itself when the override sets
  `structured_output=True`).
- **Prompt-location contract with `ll-fake-host`.** `_structured_output_args`
  (`host_runner.py:2542`) appends `["--json-schema", <json>]` *after* the runner's
  args, so under `structured_output=True` the prompt is no longer `argv[-1]`. The
  `run_blocking_json` composition case below requires `main()` to locate the
  prompt as *the argv element containing the `@@fake` fence* (falling back to
  `argv[-1]` when no element does) — see FEAT-3454 Program Design, amended
  2026-09-12, and the Program Design § re-verification finding below confirming
  `fake_host.py:main()` already implements this rule. Without it the
  `run_blocking_json` composition case below feeds the schema JSON to the fake as
  its prompt, both fakes emit the default script, and the case raises
  `BlockingJsonError` identically on both — a vacuous "equal" that never reaches
  the parsed-dict assertion.
- `describe_capabilities()` → `CapabilityReport(host=self.name, binary="ll-fake-host",
  version="", capabilities=[])` — the exact shape the landed `FakeHostRunner`
  returns (`host_runner.py:2136`). No consumer reads a fake's entries; inventing a
  populated report here would be a second pattern for nothing. It must not raise:
  `TEST_ONLY_BINARIES` calls it at import time (`host_runner.py:2193-2195`).

### `scripts/tests/conformance/test_host_composition.py` (new; marker per class, not per module)

Imports FEAT-3455's `_run_and_capture`, `Observed`, `assert_event_kinds` from
`test_host_conformance.py`; `_FAKES = ("fake", "fake-minimal")`.

**Marker placement.** Only the two classes that spawn `ll-fake-host`
(`TestFakesAreDivergent` does not; `TestCompositionThroughExecutor` does) carry
`@pytest.mark.conformance` and the `shutil.which("ll-fake-host")` skip. The AST
classes (`TestExecutorTouchesOnlyAbstractInterface`, `TestRegressionGuard`) need no
subprocess and stay **unmarked** so they run in the default unit job
(`.github/workflows/ci.yml:128` deselects `-m "not integration and not conformance"`;
`test_host_conformance.py` marks itself whole-module via `pytestmark =
pytest.mark.conformance` at `:91`, not via the directory's `conftest.py`, and a
module-level mark does not follow helpers imported from that module — so
`test_host_composition.py` must carry its own marks per class). This is what the
Impact section's "fails in the unit suite, not in review" depends on.

- `TestFakesAreDivergent` — pins the divergence so a future edit cannot quietly make
  the fakes agree: argv of `build_streaming` differs (`fake` is exactly `[prompt]`,
  `fake-minimal` is exactly `["run", prompt]`); `invocation.env` differs under `automation=`; default
  `capabilities` differ on every flag; both share `binary`; both keys are in
  `TEST_ONLY_HOSTS`; `isinstance(cls(), HostRunner)` for both.
- `TestCompositionThroughExecutor` — for each of three directive scripts (happy path;
  `result error=`; `exit 2` before terminal), `_run_and_capture` on both fakes and
  assert `Observed.kinds`, `result_seen`, `completed.returncode` are **equal across
  fakes**. One case runs `run_blocking_json` on both with `capabilities=
  HostCapabilities(structured_output=True)` and asserts the same parsed dict.
- `TestExecutorTouchesOnlyAbstractInterface` — AST over the **module sources** of
  `host_runner.py` and `subprocess_utils.py` (not just
  `inspect.getsource(run_claude_command)` / `run_blocking_json`: the invocation
  reads actually happen in the helpers they call — `project_child_env` reads `env`
  and `env_allow`, `_structured_output_args` reads `args`/`capabilities`/`binary`).
  The unit of checking is *every `FunctionDef` in those two modules that binds a
  `HostInvocation` or `HostRunner`*, where "binds" is any of: (a) a parameter whose
  annotation **contains** the name `HostInvocation`/`HostRunner` — walk the
  annotation AST, because `project_child_env` is annotated `HostInvocation | None`
  (`host_runner.py:2274`) and a bare `ann.id ==` match misses it; (b) an
  un-annotated parameter named `invocation`/`runner`; (c) **a local `Assign`
  whose value is a `Call` to `resolve_host`/`resolve_host_named` (runner) or to
  a `.build_streaming`/`.build_blocking_json`/`.build_version_check`/
  `.build_detached` attribute (invocation)**. Rule (c) is not optional:
  `run_claude_command` takes neither type as a parameter — it binds
  `runner = resolve_host()` and `invocation = runner.build_streaming(...)` as
  locals (`subprocess_utils.py:516-517`), and a params-only checker walks
  `subprocess_utils.py` and finds **zero** functions (verified with a prototype
  against current sources, 2026-09-12). With (c) in place the executor chain is
  covered end to end, and the test asserts `run_claude_command`,
  `run_blocking_json`, `project_child_env`, and `_structured_output_args` are all
  among the checked functions:
  - attribute reads on each bound invocation name ⊆
    `_ALLOWED_INVOCATION_ATTRS = {"binary", "args", "env", "capabilities", "cleanup_paths", "env_allow"}`
    (the spike's set was missing the last two — `run_blocking_json` reads
    `cleanup_paths`, `project_child_env` reads `env_allow`).
    **A read is either an `ast.Attribute` whose value is the bound name, or a
    `getattr(<name>, "<str const>", ...)` call.** The `Attribute`-only form is
    near-tautological (a frozen dataclass raises on an unknown attribute at runtime
    anyway); `getattr` with a default is the one form that escapes silently, and
    `_structured_output_args` already uses it (`host_runner.py:2543`,
    `getattr(invocation, "binary", "")`), so the checker must see it. Baseline
    the checker must pass today (prototype output): `project_child_env` →
    `{env, env_allow}`; `_structured_output_args` → `{args, binary, capabilities}`;
    `run_blocking_json` → `{args, binary, cleanup_paths}`; `run_claude_command`
    → `{binary, args, env}` on the invocation and `{build_streaming}` on the runner;
  - attribute reads on the runner param ⊆ `HostRunner` Protocol members
    (promotes the spike's declared-but-unenforced `ALLOWED_RUNNER_PROTOCOL_ATTRS`);
    same `getattr` rule;
  - no `isinstance(_, <ConcreteRunner>)` in any checked function, where the
    concrete-runner name set is **derived** as
    `{cls.__name__ for cls in _HOST_RUNNER_REGISTRY.values()}`, not hand-listed;
  - across both module sources, every `Compare` whose left side is an
    attribute/name `binary` **or `name`** (the `HostRunner.name` Protocol member is
    the other host-identity string — `runner.name == "claude-code"` would pass the
    Protocol-member check above) against a `str` constant, **or whose operator is
    `In`/`NotIn` against a tuple/set/list of `str` constants**, sits inside a function in
    `_ALLOWED_BINARY_LITERAL_SITES = {"_structured_output_args": {"claude", "qwen"}}`
    and uses only the pinned literals.
- `TestRegressionGuard` — the same checker functions run over synthetic source
  snippets and must report: `invocation.session_id` read;
  `getattr(invocation, "session_id", None)` read; `isinstance(runner,
  FakeHostRunner)`; `if invocation.binary == "ll-fake-host":` in a function not in
  the allow-list; `if runner.name in ("claude-code", "qwen"):` outside the
  allow-list; a pinned function using an unpinned literal. Each failure message
  names function + attribute/literal.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- **Marker-placement precedent citation is inaccurate** — corrected: the Design
  section's "Marker placement" paragraph cites "`pytest.mark.conformance` is
  applied per test in `test_host_conformance.py:64`." Current code applies it
  via a **module-level `pytestmark = pytest.mark.conformance` at line 91**
  (preceded by a comment block at `:84-90` explaining the whole-module intent);
  line 64 is an unrelated import line. Two per-function
  `@pytest.mark.conformance` decorators also exist (`:318`, `:369`) but are
  redundant given the module-level `pytestmark`, not the primary mechanism.
  `scripts/tests/conformance/conftest.py` still has no marker logic (only
  `pytest_addoption` and `isolated_env`), so the "not by the directory's
  conftest.py" half of the original claim stands — only the "per test" half and
  the `:64` citation are wrong. The plan for `test_host_composition.py`
  (per-class marking, AST classes left unmarked) is unaffected — pytest permits
  per-class marks independent of a module lacking `pytestmark` — only the cited
  precedent needs re-anchoring, not the plan itself.
- **`live_conformance` location** — not defined in `test_host_conformance.py`
  itself; it is a fixture defined in the parent `scripts/tests/conftest.py`
  (`_live_conformance_allowed` predicate, fixture gating on
  `LL_HOST_CONFORMANCE_LIVE=1` plus the test's marker) and consumed in
  `test_host_conformance.py` at `:375`.
- **`_install_no_live_host_cli` anchor has drifted a second time** since the
  prior refine pass's correction (which cited `conftest.py:376-377`, body
  ending `:420`): current position is decorator `:390`, `def` `:391`, body
  (through the `finally`'s `mp.undo()`) ending `:434`.

## Program Design

### Types
- `FakeMinimalHostRunner` — class in `host_runner.py`; `name: str = "fake-minimal"`;
  `capabilities: HostCapabilities` (instance, defaults to `HostCapabilities()`).
- Test-module allow-lists (`test_host_composition.py`):
  `_ALLOWED_INVOCATION_ATTRS: frozenset[str]`, `_ALLOWED_RUNNER_ATTRS: frozenset[str]`
  (derived from `HostRunner.__protocol_attrs__` on Python ≥ 3.12 — verified present
  on the 3.12.10 interpreter that runs this suite — else from
  `typing._get_protocol_attrs(HostRunner)` on 3.11, the project floor; **never a
  hand-pinned fallback**, which would drift silently when the Protocol grows),
  `_ALLOWED_BINARY_LITERAL_SITES: dict[str, frozenset[str]]`,
  `_CONCRETE_RUNNER_NAMES: frozenset[str]` (derived from `_HOST_RUNNER_REGISTRY`).

### Signatures
- `FakeMinimalHostRunner.__init__(self, capabilities: HostCapabilities | None = None) -> None`
- `build_streaming(self, *, prompt: str, working_dir: Path | None = None, resume: bool = False, agent: str | None = None, tools: list[str] | None = None, model: str | None = None, automation: AutomationContext | None = None, automation_profile: str | None = None, disable_background_tasks: bool = False, workspace_root: Path | None = None) -> HostInvocation` — every kwarg except `prompt` ignored.
- `build_blocking_json(self, *, prompt: str, model: str | None = None, json_schema: dict[str, Any] | None = None) -> HostInvocation`
- `build_version_check(self) -> HostInvocation`; `build_detached(self, *, prompt: str) -> HostInvocation` — exactly the Protocol signature (`host_runner.py:486`); no `**kw` (decision 3: explicit kwargs, never a catch-all). Match FEAT-3454's `FakeHostRunner` signatures exactly.
- `describe_capabilities(self) -> CapabilityReport`
- `_checked_functions(module_src: str, annotation: str, fallback_param: str, binding_calls: frozenset[str]) -> list[tuple[str, str]]` — `(function_name, bound_name)` for every `FunctionDef` in the module that binds the type: a parameter whose annotation AST contains `Name(annotation)` (union/`Optional` included), an un-annotated parameter named `fallback_param`, or a local `Assign` to a single `Name` target whose value is a `Call` to a bare `Name` in `binding_calls` (`{"resolve_host", "resolve_host_named"}` for runners) or an `Attribute` whose `.attr` is in `binding_calls` (`{"build_streaming", "build_blocking_json", "build_version_check", "build_detached"}` for invocations). One function may yield several bound names.
- `_invocation_attr_reads(fn: ast.FunctionDef, name: str) -> set[str]` — attribute names read on `name`: AST `Attribute` whose value is `Name(name)`, **plus** `Call(func=Name("getattr"), args=[Name(name), Constant(str), ...])`.
- `_runner_attr_reads(fn: ast.FunctionDef, name: str) -> set[str]` — same rule.
- `_host_literal_compares(fn: ast.FunctionDef) -> list[tuple[str, str]]` — `(enclosing_function, literal)` for each `Compare` with `.binary`/`binary`/`.name`/`name` on the left and a `str` `Constant` on the right, or with `In`/`NotIn` against a tuple/set/list of `str` constants (one tuple per literal).
- `_isinstance_targets(fn: ast.FunctionDef) -> set[str]` — second-arg names of every `isinstance` call.

### Call Path
`resolve_host_named("fake-minimal")` → `FakeMinimalHostRunner.build_streaming(prompt=script)` → `HostInvocation(binary="ll-fake-host", args=["run", script], env={})` → `run_claude_command` → `subprocess.Popen` (guard carve-out via `TEST_ONLY_BINARIES`) → `ll-fake-host main()` → `parse_directives` → `emit` → consumer callbacks → `_run_and_capture` → `Observed` → compared against the `fake` run of the same script.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- **Anchor re-verification after FEAT-3454 landed** (2026-09-12): FEAT-3454 merged
  since this issue's last pass, shifting several cited line numbers. Verified against
  current `host_runner.py`:
  - `_structured_output_args`: was cited `:2365-2383` → now `:2530-2548` (def line
    2530, body ends at `return args` line 2548). Body content unchanged — still
    exactly two pinned binary-literal branches, `"claude"` and `"qwen"`, matching
    Decision 5's `_ALLOWED_BINARY_LITERAL_SITES` claim.
  - `OpenCodeRunner`: was cited `:1033`/`:1033-1042` → class now spans `:1317-1379`.
  - `HOST_BINARY_NAMES`: was cited `:2028-2030` → now defined `:2186-2188`.
  - `_install_no_live_host_cli`: was cited `conftest.py:353-397` → decorator/def now
    at `conftest.py:376-377`; body ends `conftest.py:420`.
  - `HostRunner` Protocol: was cited `:394-407` → `@runtime_checkable` at `:397`,
    `class HostRunner(Protocol):` at `:398`; body (through `describe_capabilities`)
    ends `:495`.
  - `_ALLOWED_CALLERS` (test_advisor.py): the dict literal itself is `:694-696`
    (issue's `:694-724` range includes the surrounding `TestConsultExclusivity`
    class body that uses it, not the literal) — minor, not a drift.
  - `test_host_tier_table_matches_runner_registry` (`test_wiring_guides_and_meta.py`):
    confirmed exact at `:381-392`, no drift.
  - `HostInvocation` dataclass fields confirmed exactly six, matching
    `_ALLOWED_INVOCATION_ATTRS` with no extra/missing member: `binary`, `args`,
    `env`, `capabilities`, `cleanup_paths`, `env_allow` (`host_runner.py:319-344`).
  - `_HOST_RUNNER_REGISTRY` confirmed at exactly 9 keys (8 real + `fake`),
    matching Current Behavior's "eight real runners plus one fake" framing.
- **`_structured_output_args` has a caller outside `run_blocking_json`**: also
  called from `scripts/little_loops/fsm/evaluators.py:1219` and `:1474` (imported
  there at `:46-52`). `TestExecutorTouchesOnlyAbstractInterface`'s scope already
  covers this per its own stated unit-of-checking ("every `FunctionDef` in
  `host_runner.py`/`subprocess_utils.py`"), but `fsm/evaluators.py` is a third
  module that also imports and calls it — outside the two modules the AST check
  walks. Not a defect in the design (the checker's stated scope is deliberately
  the executor chain, not every caller), but worth flagging: a future
  binary-literal branch added inside `fsm/evaluators.py` itself, rather than
  inside `_structured_output_args`, would not be caught by this issue's checker.
- **Prompt-location contract (blocking pre-check for step 1) — CONFIRMED SATISFIED**:
  `scripts/little_loops/fake_host.py:main()` (line 293) already implements the
  fence-locates-prompt rule this issue's `run_blocking_json` composition case
  depends on — docstring at `fake_host.py:296-299` states verbatim "The prompt is
  the argv element containing the `@@fake` fence, falling back to `argv[-1]` only
  when no element does". No fix-first action needed before step 1; the Design
  section's "re-check `main()` against this rule before step 3" caveat is cleared.

## Behavior Parity

Spike tests (`scripts/tests/spike/host_compose/test_host_compose.py`) → production
home, or dropped with reason:

| Spike test | Production |
|---|---|
| `TestProtocolSatisfaction::*` | `test_host_runner.py::TestFakeMinimalHostRunner::test_satisfies_host_runner_protocol` (the `fake` half is FEAT-3454's) |
| `TestFakesAreDivergent::test_fakes_have_divergent_capabilities` | `test_host_composition.py::TestFakesAreDivergent` — same assertion, against `fake` vs `fake-minimal` |
| `TestFakesAreDivergent::test_fakes_have_divergent_action_vocabulary` | `TestFakesAreDivergent` — argv-shape form (`[prompt]` vs `["run", prompt]`), since both accept the full kwarg set (decision 3) |
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
  (`HOST_BINARY_NAMES`, `host_runner.py:2186-2188`).
- `"fake-minimal"` in `TEST_ONLY_HOSTS` (`host_runner.py:2142`, a `frozenset`
  literal — edit the literal, don't rebind with `|=`) **in the same commit** as the
  registry entry — the remediation hint, guard carve-out, count-free binary tests,
  and ENH-3453's runtime-map parity check all key off it.
- `scripts/tests/conformance/test_host_conformance.py` gains a
  `_STREAM_SHAPE["fake-minimal"] = (True, "result")` row **in the same commit** —
  `test_stream_shape_covers_registry` (`:148-156`) asserts strict key equality
  with `_HOST_RUNNER_REGISTRY`. Same file: `test_golden_path_behavior`'s
  `if host != "fake":` (`:388`) becomes `if host not in TEST_ONLY_HOSTS:`, otherwise
  `fake-minimal` is treated as a live host and skipped rather than exercised.
- `docs/reference/HOST_COMPATIBILITY.md` `## Host tiers` gains a `fake-minimal` row
  **in the same commit** — `test_host_tier_table_matches_runner_registry`
  (`test_wiring_guides_and_meta.py:381-392`) asserts strict equality and would
  otherwise turn `main` red for every local-editable project.
- Composition tests use `_run_and_capture` (real Popen), never a patched executor.
- Composition tests skip with reason when `shutil.which("ll-fake-host") is None`
  (non-editable installs), matching FEAT-3455. The AST classes never skip and are
  never `conformance`-marked (see Design § marker placement).
- **ENH-3453 landing order.** ENH-3453 rewrites `_check_runtime_contradiction`
  (`cli/verify_host_map.py:100-128`) to strict key parity
  `set(RUNTIME_HOST_CAPABILITIES) == set(_HOST_RUNNER_REGISTRY)`. Test-only hosts
  have no runtime-map entry, so whichever of ENH-3453 / this issue lands second
  must subtract `TEST_ONLY_HOSTS` from the registry side (ENH-3453 step 4 now says
  so). If ENH-3453 is already on `main` when step 1 starts, add the subtraction
  here and a `fake-minimal`-excluded test in `test_verify_host_map.py`; otherwise
  `ll-verify-host-map` in step 6 goes red.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- **ENH-3453 landing order — resolved, no action needed.** ENH-3453 has landed
  (`status: done`). Its `_check_runtime_contradiction`
  (`scripts/little_loops/cli/verify_host_map.py:114-160`) already computes
  `registry_hosts = set(_HOST_RUNNER_REGISTRY) - test_only_hosts` (line 140),
  reading `TEST_ONLY_HOSTS` generically via `getattr(_host_runner_module,
  "TEST_ONLY_HOSTS", frozenset())` (line 136) — so any future `TEST_ONLY_HOSTS`
  member, including `fake-minimal`, is automatically exempted from strict key
  parity with no per-host-name change required. `test_verify_host_map.py`
  already has generic coverage for this exemption:
  `test_flags_test_only_hosts_exempt` (`:136-160`) patches `TEST_ONLY_HOSTS` and
  asserts the exemption holds — it is not hardcoded to `"fake"` only, so it
  does not need a `fake-minimal`-specific companion test. This issue's step 6
  can drop the "otherwise add the subtraction / a fake-minimal-excluded test"
  branch entirely; only the generic `ll-verify-host-map` run in step 6 still
  applies, as a regression check.

## Scope Boundaries

In:
- `FakeMinimalHostRunner` class, registry entry, `TEST_ONLY_HOSTS` entry, exports.
- `test_satisfies_host_runner_protocol` + `TestFakeMinimalHostRunner` argv/env/
  capability tests in `test_host_runner.py` (follow `TestFakeHostRunner`).
- `test_host_composition.py` with the four classes above.
- `test_host_conformance.py`: `_HOST_BINARY["fake-minimal"] = "ll-fake-host"`
  (matches FEAT-3454's `"fake"` entry; skip-not-fail on non-editable installs),
  `_STREAM_SHAPE["fake-minimal"] = (True, "result")` (gated), and
  `test_golden_path_behavior` keyed on `TEST_ONLY_HOSTS` instead of `"fake"`.
- `HOST_COMPATIBILITY.md` tier-table row (gated).
- Delete `scripts/tests/spike/host_compose/`; footer on `.ll/spikes/spike-FEAT-3456.md`.

Out (ENH-3460): un-gated prose — `ARCHITECTURE.md` Host Runner Layer row, `API.md`
concrete-runners row, `CONFORMANCE.md` section describing the composition suite,
`TESTING.md` note.

## Implementation Steps

1. `FakeMinimalHostRunner` in `host_runner.py`; registry entry; `"fake-minimal"`
   added to the `TEST_ONLY_HOSTS` literal; `__all__` + package re-export. Unit
   tests first (TDD): Protocol check, argv is exactly `["run", prompt]`, env empty
   under `automation=`, default capabilities all `False`, override propagates to
   all four `build_*`. (The fence-locates-prompt rule in `fake_host.py:main()` is
   confirmed landed — no pre-check needed.)
2. `HOST_COMPATIBILITY.md` tier-table row (test-only); `_STREAM_SHAPE` row and
   the `TEST_ONLY_HOSTS`-keyed skip in `test_host_conformance.py`. Run
   `python -m pytest scripts/tests/test_wiring_guides_and_meta.py scripts/tests/test_host_runner.py scripts/tests/test_conftest_cap.py scripts/tests/conformance/` — must be green before step 3.
3. `test_host_composition.py::TestFakesAreDivergent` and
   `TestCompositionThroughExecutor` against FEAT-3455's helpers; `_HOST_BINARY` entry.
4. AST checkers as module-level functions (`_checked_functions` with the
   local-binding rule, `_invocation_attr_reads(fn, name) -> set[str]` incl. `getattr`
   form, `_runner_attr_reads(fn, name)`, `_host_literal_compares(fn) -> list[(func, literal)]`
   covering `binary`/`name` and `in`-collections, `_isinstance_targets(fn)`);
   `TestExecutorTouchesOnlyAbstractInterface` over every `HostInvocation`/`HostRunner`-binding
   function in both module sources (unmarked), asserting `run_claude_command` is
   among them; `TestRegressionGuard` over synthetic snippets (unmarked), including
   one snippet where the only binding is a local `invocation = runner.build_streaming(...)`.
5. Delete the spike package; append the promotion footer to the spike plan. The
   footer must state that it supersedes the plan's existing `## Promotion` section
   (which still names `scripts/little_loops/spike/host_compose/` as the target —
   the path decision 4 rejected).
6. `python -m pytest scripts/tests/` (no `LiveHostCLISpawn` hits), `python -m pytest
   scripts/tests/conformance/ -v`, `ll-verify-host-map`, mypy, ruff.

## Conventions in Force

- `HostRunner` is `@runtime_checkable` (`host_runner.py:397-398`); conformance via
  `isinstance(x, HostRunner)`.
- `build_*` are keyword-only with explicit kwargs (FEAT-3454 Conventions;
  `CapturingRunner`, `test_runner_spec.py:44-58`).
- Registered-but-not-probed precedent: `OpenCodeRunner` (`host_runner.py:1317-1379`)
  and `FakeHostRunner` itself (`host_runner.py:2053-2137`).
- Live-spawn guard: `_install_no_live_host_cli` (`conftest.py:390-434`) keyed on
  `HOST_BINARY_NAMES`, carve-out from `TEST_ONLY_BINARIES` (FEAT-3454).
- AST allow-list precedent: `_ALLOWED_CALLERS` (`test_advisor.py:694-696`).
- Frozen dataclasses: `HostCapabilities`, `HostInvocation`, `CapabilityReport`,
  `CapabilityEntry`, `AutomationContext`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- `TestConsultExclusivity` (`test_advisor.py:694-724`) confirmed as the one in-tree
  precedent for AST-walk-plus-pinned-allow-list enforcement (a `dict[str, int]`
  keyed by module path, checked via whole-module `ast.walk` over `ast.Call` nodes) —
  matches this issue's Decision 5 framing exactly.
- No in-repo precedent exists yet for deriving an allow-list from a `Protocol` via
  `typing._get_protocol_attrs`/`__protocol_attrs__`, nor for
  `{cls.__name__ for cls in <registry>.values()}`-style registry-derived name sets
  (confirmed by repo-wide search: both patterns appear only inside this issue's own
  proposed text). This issue introduces both as new conventions rather than
  following an existing one — consistent with its own "never a hand-pinned
  fallback" requirement, just noting there is no prior art to check the derivation
  against if it needs debugging.
- `TestFakeHostRunner` (`test_host_runner.py:1110-1182`) is the exact test-class
  shape precedent for the issue's planned `TestFakeMinimalHostRunner`: naming
  `Test<RunnerClassName>`, one `test_satisfies_host_runner_protocol` per runner
  class, and `build_*` variants parametrized with lambdas rather than four
  near-duplicate test methods.

## Tests

- `scripts/tests/conformance/test_host_composition.py` (new) — four classes above.
- `scripts/tests/test_host_runner.py` — `TestFakeMinimalHostRunner` incl.
  `test_satisfies_host_runner_protocol` (mirrors the entries at `:679, 1024, 1105,
  1163, 1303, 1484, 1676, 1862` and FEAT-3454's `TestFakeHostRunner`).
- `scripts/tests/conformance/test_host_conformance.py` — `test_golden_path_invocation`
  auto-extends to `fake-minimal` via registry parametrization;
  `test_golden_path_behavior` does so only once its `"fake"` literal is replaced by
  the `TEST_ONLY_HOSTS` membership check (Key constraints).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- **Line-citation drift in the `TestFakeHostRunner` precedent list** (this
  section's second bullet, "mirrors the entries at `:679, 1024, 1105, 1163,
  1303, 1484, 1676, 1862`"): re-verified against current `test_host_runner.py`
  — corrected to `:680, 1025, 1106, 1239, 1379, 1560, 1752, 1938`. The first
  three were off by one line; the remaining five are off by a consistent +76
  lines, with the offset boundary at `TestFakeHostRunner` itself
  (`test_host_runner.py:1110-1185`, a 75-line class sitting between
  `TestOpenCodeRunner` and `TestPiRunner` in file order) — i.e. this citation
  list was not re-anchored in the same pass that fixed the other
  `host_runner.py`/`conftest.py` citations elsewhere in this issue.

## Files to Modify

- `scripts/little_loops/host_runner.py` — `FakeMinimalHostRunner`; `_HOST_RUNNER_REGISTRY`;
  `TEST_ONLY_HOSTS`; `__all__`
- `scripts/little_loops/__init__.py` — re-export
- `scripts/tests/test_host_runner.py` — `TestFakeMinimalHostRunner`
- `scripts/tests/conformance/test_host_composition.py` — new
- `scripts/tests/conformance/test_host_conformance.py` — `_HOST_BINARY` entry,
  `_STREAM_SHAPE` entry, `test_golden_path_behavior` skip keyed on `TEST_ONLY_HOSTS`
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

Open and **unblocked** (2026-09-12). FEAT-3454 and FEAT-3455 have both landed:
`FakeHostRunner`, `TEST_ONLY_HOSTS`/`TEST_ONLY_BINARIES`, the `ll-fake-host`
console script, the `fake` tier row, `_run_and_capture`/`Observed`/
`assert_event_kinds`, `_HOST_BINARY`, and `_STREAM_SHAPE` all exist on `main`.
`FakeMinimalHostRunner` / `fake-minimal` exist nowhere outside this issue and the
still-present spike package (`scripts/tests/spike/host_compose/`, four files) and
`.ll/spikes/spike-FEAT-3456.md`. All body anchors were re-verified against the
landed files in the 2026-09-12 manual review (third pass); `blocked_by` cleared.

## Related Issues (Dependencies)

- FEAT-3454 (done, P2) — `FakeHostRunner`, `ll-fake-host`, `TEST_ONLY_HOSTS` /
  `TEST_ONLY_BINARIES`, derived guard carve-out, count-free binary tests. Landed;
  no longer a block.
- FEAT-3455 (done, P2) — `_run_and_capture`, `Observed`, `assert_event_kinds`,
  `live_conformance`. Landed; no longer a block. Anchors re-verified against the
  landed file in this pass (see Design, Key constraints, Tests findings above).
- ENH-3460 (open, P3) — un-gated doc prose after this lands.
- ENH-3453 (done, P2) — declarative capability map; parallel, not a dependency.
  It landed first: its strict-parity `_check_runtime_contradiction` already
  subtracts `TEST_ONLY_HOSTS` (confirmed this pass — see Key constraints), so
  no action is needed here on that account. The class-level `capabilities`
  default question (should it come from the same source as the real runners')
  remains open as a design note, independent of landing order.
- FEAT-3454 (done, P2) — also owns the `main()` prompt-location rule this issue's
  `run_blocking_json` composition case depends on (fence-locates-prompt, fallback
  `argv[-1]`) — confirmed implemented (`fake_host.py:293-304`). Also the reason the
  argv divergence moved to `["run", prompt]`: FEAT-3454 landed `FakeHostRunner`
  with bare `[prompt]`, not the flagged form an earlier draft here assumed.

## Reference Documentation

- Parent `ENH-3456` — design rationale, Program Design findings (audit-wrapper
  novelty, carve-out inventory, `run_blocking_json` field-access inventory, missing
  `cleanup_paths`/`env_allow` in the spike allow-list).
- `.claude/CLAUDE.md` § Host CLI Abstraction.
- `docs/reference/API.md#little_loopshost_runner`.
- `.ll/spikes/spike-FEAT-3456.md` — spike plan; mechanism proven in-process, ported
  here to the real executor.

## Verification Notes

Historical record of the 2026-09-12T17:05 `/ll:verify-issues` pass (pre-FEAT-3454).
Its line citations and "does not yet exist" observations were true then and are
**superseded** by the body anchors re-verified in the third manual review; they are
kept only as the audit trail for the link fix below.

- Fixed: the "Parent Issue" link to ENH-3456 used `../P3-ENH-3456-...md`, which
  resolves outside `.issues/enhancements/` to a nonexistent path; ENH-3456 in
  fact lives in the same directory as this file. Corrected to a same-directory
  relative link.
- Checked `blocked_by: [FEAT-3454, FEAT-3455]` for a reciprocal backlink:
  neither target declares a `blocks:` field or `## Blocks` heading naming
  ENH-3459. Initially flagged as MISSING_BACKLINK, but this repo's current
  frontmatter-based dependency model treats a one-directional `blocked_by`
  declaration as valid on its own — `dependency_graph.py` auto-derives the
  reverse edge in memory for graph traversal/readiness checks
  (`scripts/little_loops/dependency_graph.py:121-133`), and `ll-issues link`
  only writes the reciprocal edge when `--reciprocal` is explicitly passed.
  The `## Blocked By` / `## Blocks` markdown-heading convention the
  verify-issues check describes is a legacy template pattern (still present
  on older issues, e.g. `FEAT-1462`) that this issue and its blockers don't
  use. Not a defect.
- `ll-verify-evidence` reported no unverifiable evidence spans (B7: clean).
- No `## Proposed Solution` section present (this issue uses `## Design` /
  `## Program Design` / `## Implementation Steps` instead), so the B6
  proposal-vs-code consequence check does not apply.
- Graph: provider=`codegraph` freshness=`fresh`; not used beyond corroborating
  the grep-verified line citations above (no negative/"never called" claims in
  this issue to check via `callers-of`/`references`).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-12_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Gaps to Address
- ~~`blocked_by: FEAT-3455` is still `open`~~ — **resolved**: FEAT-3455 landed
  (commit `00daed9e8`); the dependency hard-override no longer applies. The
  three defects found in the third manual review (argv divergence already gone,
  `run_claude_command` outside the checker's unit, missing `_STREAM_SHAPE` /
  `test_golden_path_behavior` gates) are fixed in the body above.

## Session Log
- Manual review - 2026-09-12 (third pass, post FEAT-3454/3455 landing) - argv divergence redefined as `[prompt]` vs `["run", prompt]` (landed `FakeHostRunner` already emits bare `[prompt]`); AST checker unit extended to local `resolve_host*()` / `.build_*()` bindings so `run_claude_command` is covered (prototype showed a params-only checker finds zero functions in `subprocess_utils.py`) and annotation matching walks unions; `_STREAM_SHAPE` row + `TEST_ONLY_HOSTS`-keyed `test_golden_path_behavior` skip added to scope; `describe_capabilities` mirrors landed shape; spike-plan footer must supersede its `## Promotion` section; body anchors re-verified; stale blocked/verification/confidence notes pruned; `blocked_by` cleared
- `/ll:refine-issue` - 2026-09-12T23:38:59 - `5aa15495-6226-4aaa-8c88-253c64012dde.jsonl`
- `/ll:confidence-check` - 2026-09-12T22:28:34 - `f4eb5fe2-ff23-41c6-a2f4-1f15f754e390.jsonl`
- `/ll:refine-issue` - 2026-09-12T21:47:26 - `185e59ee-6aae-4358-8b55-3ef95d63b372.jsonl`
- `/ll:confidence-check` - 2026-09-12T18:35:45 - `39734cb1-4330-4618-b589-c95b4733611a.jsonl`
- Manual review - 2026-09-12 (second pass) - fixed the `run_blocking_json` composition case (`--json-schema` lands after the prompt, so `argv[-1]` is the schema — FEAT-3454 `main()` amended to locate the prompt by fence); AST checks widened to every `HostInvocation`/`HostRunner`-taking function in both modules, `getattr` reads, `name` literals and `in`-collections, registry-derived concrete-runner names; `__protocol_attrs__` fallback pinned to `typing._get_protocol_attrs`; `conformance` marker per class so the AST gates run in the unit job; "five `build_*`" → four; dropped `**kw` from `build_detached`; ENH-3453 landing-order constraint recorded
- `/ll:verify-issues` - 2026-09-12T17:05:34 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- `/ll:issue-size-review` - 2026-09-12T06:09:06 - `a6c3ba7b-8baf-4ae7-b742-fb9d4cbad25c.jsonl`
- Manual review rewrite - 2026-09-12 - resolved six decisions (real-executable second fake sharing `ll-fake-host`, explicit kwargs, class in `host_runner.py`, AST-based interface check with pinned carve-out, port-not-move, gated doc row owned here); took the gated drift items back from ENH-3460
