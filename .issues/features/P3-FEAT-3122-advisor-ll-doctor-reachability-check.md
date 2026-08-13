---
id: FEAT-3122
title: ll-doctor advisor-reachability check
type: FEAT
parent: FEAT-3044
priority: P3
status: open
testable: true
discovered_date: 2026-08-08
depends_on:
- FEAT-3108
- FEAT-3120
labels:
- planning-hub
verify_verdict: NON_VALID
size: Large
reconcile_attempted: true
confidence_score: 50
outcome_confidence: 58
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 5
score_change_surface: 25
---

# FEAT-3122: ll-doctor advisor-reachability check

## Summary

Add `_advisor_check` to `cli/doctor.py`: report advisor host reachability
and warn (never fail) when the configured advisor model does not outrank
the main model. This is the third and last architecturally separable
concern of FEAT-3044's "ll-doctor check" subsection.

## Parent Issue

Decomposed from FEAT-3044: Advisor core - `ll-advise` CLI, capability
floor, and `ll-doctor` check. Builds on FEAT-3108 (done; `check_floor`,
`rank_model`) for the floor classification and FEAT-3120 (`consult`, the
advisor host-resolution/isolation pattern, and the CLI registration
lockstep surfaces this issue's own doc wiring follows) for the
established "resolve the advisor host without mutating `LL_HOST_CLI`"
convention.

## Current Behavior

No existing `@register_check` in `cli/doctor.py` pings a host CLI for
reachability. The closest analog, `_capability_check_results()`
(`doctor.py:98-113`), is deliberately *not* `@register_check`-registered
because it needs the resolved `HostRunner` at call time (comment at
`doctor.py:76-80`). `CheckResult.severity: Literal["error",
"informational"]` (`doctor.py:54-73`) is the existing mechanism for "warn
but don't fail" — `_exit_code_for` (`doctor.py:124-127`) only fails the
overall exit code on `severity == "error" and status == "unsupported"`.

A second, distinct "needs live state" category already exists and is
`@register_check`-decorated anyway: `_full_*_check()` functions
registered into a parallel `_FULL_CHECKS` list (`doctor.py:484-498`,
gated by `--full`) — these resolve their own dependencies internally
rather than receiving them from `main_doctor()`'s local scope.
`_advisor_check` cannot follow this second pattern as-is, since resolving
*the advisor's own host* (distinct from the main orchestration host
`main_doctor()` already resolves at `doctor.py:1051`) is exactly the kind
of call-scoped state the first (`_capability_check_results`) pattern
exists to keep out of the no-arg `_CHECKS` list.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Dependency-status discrepancy (critical for implementer)**: this issue's
  `depends_on: [FEAT-3108, FEAT-3120]` frontmatter treats FEAT-3120 as a
  satisfied prerequisite because it carries `status: done`. That status is
  misleading for dependency-resolution purposes: FEAT-3120's own
  `## Resolution` section reads `**Status**: Decomposed` — it was closed by
  splitting into FEAT-3120 and FEAT-3121, not by landing code. Both
  successors carry `status: deferred`. A full read of
  `scripts/little_loops/advisor.py` (113 lines, current `main`) confirms it
  contains only FEAT-3108's pieces (`MODEL_RANKS`, `FloorResult`,
  `rank_model`, `check_floor`); there is no `consult()` function,
  `AdvisorVerdict` dataclass, `ll-advise` CLI (`cli/advise.py` does not
  exist), or `/ll:advise` skill anywhere in the tree. The "established
  'resolve the advisor host without mutating `LL_HOST_CLI`' convention"
  this issue's Parent Issue section cites from FEAT-3120 does not exist in
  code — FEAT-3122 cannot follow it and would have to invent that
  resolution logic itself, or is genuinely blocked pending FEAT-3120.
- No production call site anywhere in the tree resolves a *second*,
  independent `HostRunner` distinct from the main orchestration host.
  Every call site that reaches `resolve_host()` (`host_runner.py:1574-1619`)
  — `doctor.py:1051`, `init/cli.py:172`, `init/install_check.py:77,143`,
  `cli/action.py:338` — calls it with zero arguments, relying on ambient
  `os.environ`/`LL_HOST_CLI`, optionally pre-seeded by
  `apply_host_cli_from_config()` (`host_runner.py:1622-1647`, which itself
  mutates `os.environ["LL_HOST_CLI"]`). `resolve_host(env: dict | None)`
  does accept an explicit `env` dict "for testability"
  (`host_runner.py:1587-1589`), but that parameter is used only in test
  files (`test_host_runner.py`, `test_host_conformance.py`) — never in
  production code to obtain an independent runner without touching global
  state.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- `main_doctor()` does not wrap its own `resolve_host()` call (`doctor.py:1051`) in a `try`/`except` — if `resolve_host()` raises `HostNotConfigured` there, it propagates uncaught out of `main_doctor()`. Only `_probe_version` (`doctor.py:912-932`) absorbs `HostNotConfigured`, and only for the version-string path built from the *already-resolved* runner it receives as a parameter — it is not a safety net for a second, independent advisor-host resolution.
- Severity threading across doctor.py's existing checks splits into four distinct, disagreeing shapes (not two): (1) `data["severity"]` with no default (`_decisions_store_check` `doctor.py:348`, `_history_db_check` `:393`, `_loop_validity_check` `:476`); (2) `data.get("severity", "error")` defaulted, used by four `_full_*_check()` functions (`doctor.py:630,753,792,867`); (3) no `severity=` kwarg at all, relying on `CheckResult`'s dataclass default of `"error"` (`_entry_points_check` `doctor.py:239-249`, `_skills_commands_check` `:274-277`); (4) an inline conditional keyed on a name-allowlist rather than a dict field (`_capability_check_results`, `doctor.py:110`: `severity="informational" if c.name in _ADVISORY_CAPABILITIES else "error"`). `_advisor_check` will introduce a fifth call site and should pick one of these four shapes deliberately rather than inventing a new one.
- A second, independent "warn but don't fail" vocabulary exists outside doctor.py: `ValidationSeverity` (`fsm/validation/_base.py:15-34`, `ERROR`/`WARNING` enum members on `ValidationError`), aggregated by an equality filter at `structural_rules.py:1667` (`error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]`) — structurally analogous to `_exit_code_for`'s `severity == "error" and status == "unsupported"` filter (`doctor.py:124-127`), but a separate closed vocabulary with no shared type or helper between the two modules. Not a reusable dependency for `_advisor_check`, but confirms the "warn but don't fail via an explicit severity filter" shape is an established codebase idiom, not a one-off.
- The tree-wide enumeration of zero-argument `resolve_host()` production call sites is larger than previously recorded: in addition to `doctor.py:1051`, `init/cli.py:172`, `init/install_check.py:77,143`, and `cli/action.py:338`, there are also `runner_spec.py:182,290`, `subprocess_utils.py:401`, `session_store/lifecycle.py:154,757`, `fsm/evaluators.py:1120,1314,1566`, `parallel/worker_pool.py:805`, `fsm/handoff_handler.py:117`, `cli/loop/_helpers.py:2072`, `cli/issues/decisions.py:797`, and `learning_tests/extractor.py:132`. All of them, without exception, call `resolve_host()` with zero arguments — none passes an explicit `env` dict. This strengthens rather than changes the issue's existing claim: there is no production precedent anywhere in the tree for resolving a second, independent `HostRunner`.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Dependency-chain re-check (2026-08-10 refine pass) — resolves the open
  Verification Notes concern below**: this issue's `depends_on: [FEAT-3108,
  FEAT-3120]` is now confirmed **accurate**, not stale. `FEAT-3120`
  (`.issues/features/P3-FEAT-3120-advisor-consult-core-and-ll-advise-cli.md`)
  is a real, currently `open` issue titled "Advisor consult() core and
  ll-advise CLI" — it matches the scope this issue's Parent Issue section
  describes (consult(), the ll-advise CLI, the host-resolution-isolation
  convention). `FEAT-3120` itself carries `depends_on: [FEAT-3042, FEAT-3043,
  FEAT-3108]`, and both `FEAT-3042`
  (`.issues/features/P3-FEAT-3042-advisor-shared-blocking-json-transport.md`)
  and `FEAT-3043`
  (`.issues/features/P3-FEAT-3043-advisor-config-block.md`) are real, open
  issues in the tracker (not the unrelated FEAT-3120/FEAT-3121
  worktree-state-inheritance IDs the earlier Verification Notes confused
  them with). `consult()`/`AdvisorVerdict`/the `ll-advise` CLI/`AdvisorConfig`
  still do not exist in `scripts/little_loops/advisor.py` (113 lines,
  unchanged) or `config-schema.json`/`config/core.py`/`config/orchestration.py`
  — the dependency is real and currently unsatisfied (FEAT-3120 is `open`,
  not `done`), but the frontmatter `depends_on` edge itself needs **no
  repointing**. The prior "Recommended action: repoint depends_on" notes
  below are now moot.

## Expected Behavior

- `ll-doctor` reports advisor host reachability.
- `ll-doctor` warns (does not fail) when the advisor model does not
  outrank the main model, per `check_floor`'s (FEAT-3108) `advisory`/
  `unknown` classifications.
- An advisory-only finding never affects `ll-doctor`'s overall exit code.

## Proposed Solution

`_advisor_check` should set `severity="informational"` for
`advisory`/`unknown` floor results, mirroring the existing
`_ADVISORY_CAPABILITIES = frozenset({"claude_md_suppression"})` pattern
(`doctor.py:95`). Follow the non-`@register_check` pattern used by
`_capability_check_results()` (fold its results into `main_doctor`'s
`results = _capability_check_results(report) + _run_registered_checks()`
at `doctor.py:1088`), or resolve the advisor host inside a thin
`@register_check` wrapper — either is acceptable, since the constraint is
"needs the resolved `HostRunner` at call time," not a specific mechanism.

## API/Interface

```python
# scripts/little_loops/cli/doctor.py
def _advisor_check() -> list[CheckResult]:
    """Advisor host reachability + capability-floor warning."""
```

Uses `little_loops.advisor.check_floor` (FEAT-3108) and
`HostRunner.build_version_check` for reachability.

## Program Design

### Call Path

`ll-doctor` -> `_run_registered_checks` (or `main_doctor` folding, per
the `_capability_check_results` precedent) -> `_advisor_check` ->
`check_floor` (FEAT-3108) / `HostRunner.build_version_check`

### Decision Rules

- `severity="informational"` for `advisory`/`unknown` floor results —
  `_exit_code_for` only fails on `severity == "error" and status ==
  "unsupported"`, so these never change the overall exit code.
- The advisor's own host resolution must not call
  `apply_host_cli_from_config()` and must not mutate `LL_HOST_CLI`,
  consistent with FEAT-3120's isolation requirement for `consult()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Signatures

- `check_floor(advisor_host: str, advisor_model: str, main_host: str, main_model: str) -> FloorResult` — `advisor.py:64-112`
- `FloorResult` (frozen dataclass, `advisor.py:39-51`): `status: Literal["ok", "violation", "advisory", "unknown"]`, `detail: str`
- `rank_model(host: str, model: str) -> int | None` — `advisor.py:54-61`; `MODEL_RANKS: dict[str, dict[str, int]]` (`advisor.py:23-36`) is populated only for `"claude-code"`; every other host key maps to `{}`
- `CheckResult` (`doctor.py:55-73`): `status: Literal["full", "partial", "unsupported"]`, `severity: Literal["error", "informational"] = "error"` (default) — this is a **different closed `Literal` from `FloorResult.status`**; the two do not share member names, so `_advisor_check` must translate one into the other. Existing code does not specify this mapping.
- `HostRunner.build_version_check() -> HostInvocation` — Protocol method, per-runner implementations at `host_runner.py:260,402,698,826,900,1071,1251,1450`
- `_probe_version(runner: HostRunner) -> str` (`doctor.py:912-932`) — the only existing host-reachability probe: checks `runner.detect()`, then `subprocess.run([invocation.binary, *invocation.args], capture_output=True, text=True, timeout=10)`, swallowing `TimeoutExpired`/`FileNotFoundError`/`OSError`/`HostNotConfigured` to `""`. It receives its `HostRunner` as a parameter rather than resolving one itself, and `main_doctor()` calls it with the *same* runner from `resolve_host()` at `doctor.py:1051` — i.e. today's only probe reuses the single resolved runner, it does not resolve a second one.
- `_exit_code_for(results: list[CheckResult]) -> int` (`doctor.py:124-127`): `has_error = any(r.severity == "error" and r.status == "unsupported" for r in results)`. This predicate keys on BOTH `severity == "error"` AND `status == "unsupported"` together — an advisory/unknown `CheckResult` is excluded by `severity` alone, regardless of what `status` value is chosen for it.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/doctor.py` — `_advisor_check`.

### Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — advisor host support matrix;
  explicit note that cross-host capability floors are **advisory, not
  enforced**.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (`### ll-doctor`, ~lines 249-259) — hardcodes
  both the check *count* ("5 default install-surface checks") and the
  `--json` key enumeration (`entry_points`, `skills_commands`,
  `decisions_store`, `history_db`, `loop_validity`); both need the new
  advisor check added. [Agent 2 finding]
- `docs/reference/API.md` — `describe_capabilities` section (~line 9266)
  duplicates the same `--json` key enumeration in prose and must stay in
  lockstep with CLI.md's copy; also has no `little_loops.advisor` module
  reference entry at all today (zero coverage for `check_floor`,
  `rank_model`, `MODEL_RANKS`, `FloorResult`). [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- **Blocking gap, not just a wiring touchpoint**: `_advisor_check` has no
  config surface to read an advisor host/model from.
  `scripts/little_loops/config-schema.json` has no `advisor` block (only
  `orchestration.host_cli`'s enum at line 1572-1576);
  `scripts/little_loops/config/core.py`,
  `scripts/little_loops/config/orchestration.py`, and
  `scripts/little_loops/config/__init__.py` have zero `advisor`
  references — no `AdvisorConfig` dataclass exists. Confirmed this is
  FEAT-3043's scope, which is not in this issue's `depends_on`.
  [Agent 2 finding]
- Also confirmed: `scripts/little_loops/host_runner.py` has no
  named-host resolution primitive independent of the ambient
  `resolve_host()` (`resolve_host_named()`/`consult()` do not exist) —
  this is FEAT-3042's scope, also not in `depends_on`. Without it,
  `_advisor_check` has no primitive to instantiate an advisor-specific
  `HostRunner` without either mutating `LL_HOST_CLI` (forbidden by this
  issue's own Decision Rules) or reaching into
  `_HOST_RUNNER_REGISTRY` directly as a stopgap. [Agent 2 finding]

### Tests

- `scripts/tests/test_cli_doctor.py` — model `_advisor_check`'s
  "informational severity never fails exit code" behavior after
  `test_exit_code_ignores_informational_unsupported` (~line 699), and use
  the save/clear/restore-`_CHECKS` isolation pattern from
  `test_register_check_appends_and_runs` (~line 682) /
  `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor`
  (~line 715) if `_advisor_check` needs a fake-check test double.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Stale line reference (2026-08-10 refine pass)**: the `describe_capabilities`
  section in `docs/reference/API.md` has moved — it is now at approximately
  lines 9454-9462, not ~line 9266 as the prior wiring-pass note above states.
  Still has zero `little_loops.advisor` module reference.
- **Sharper framing of the status-translation gap (2026-08-10 refine pass)**:
  `_capability_check_results()` (`doctor.py:98-113`) is not actually an
  example of remapping one status vocabulary into another — it copies
  `CapabilityEntry.status` straight through into `CheckResult.status`
  unchanged, and only derives the separate `severity` field via a
  set-membership check against `_ADVISORY_CAPABILITIES` (`doctor.py:95,110`).
  There is no existing dict-mapping or dispatch convention anywhere in the
  codebase that translates between two disjoint closed `Literal` status
  types — `_advisor_check` mapping `FloorResult.status` onto
  `CheckResult.status` would be a genuinely new pattern, not an application
  of an existing one.
- **No `side_effect=[...]` precedent for dual-host mocking exists anywhere in
  the suite (2026-08-10 refine pass, confirms prior wiring note)**: a
  suite-wide grep for `side_effect=[` returns exactly one hit,
  `test_issue_manager.py:403`, and it is an unrelated retry-flow mock, not a
  `resolve_host` mock. Every `resolve_host` patch across the entire test
  suite (not just `test_cli_doctor.py`) uses a single `return_value=`. A test
  asserting `_advisor_check` resolves an independent advisor host would be
  introducing this pattern for the first time in the codebase.

### Conventions in Force

- A check that needs a value only available inside `main_doctor()`'s body
  (like a resolved `HostRunner`) is folded directly into `main_doctor()`'s
  `results` list by hand, not `@register_check`-decorated — this is the
  entire rationale for `_capability_check_results()`
  (`doctor.py:98-113`, comment at `doctor.py:76-80`), the only existing
  precedent for this shape. `--full`'s `_full_*_check()` functions are a
  *different* axis (still no-arg, `@register_check`-decorated into a
  separate `_FULL_CHECKS` list, gated on the `--full` flag rather than on
  a call-time parameter) — not a substitute pattern.
- `severity="informational"` on a `CheckResult` is what keeps a finding out
  of `_exit_code_for`'s failure predicate (`doctor.py:124-127`), which
  checks `severity == "error" and status == "unsupported"` together.
  Existing informational usages split along an absent-vs-broken axis
  (`_decisions_store_data`, `_history_db_data`, `_loop_validity_data`) or an
  allowlist-by-name axis (`_ADVISORY_CAPABILITIES = frozenset({"claude_md_suppression"})`,
  `doctor.py:95,110`) — no single canonical shape, but every existing case
  ties `informational` to "this can't be helped right now", not to
  "this failed".
- Two disagreeing conventions exist for threading severity from a `_*_data()`
  helper into its `_*_check()` `CheckResult` constructor: some helpers
  return `severity` in their dict and the check reads `data["severity"]`
  (decisions store, history db, loop validity, several `_full_*` checks,
  the latter defaulting via `data.get("severity", "error")`); others omit
  `severity` entirely and rely on `CheckResult`'s dataclass default of
  `"error"` (`_entry_points_check`, `_skills_commands_check`, most
  `_full_*_check` functions).

### Dependent Files (Callers/Importers)

- `scripts/tests/test_cli_doctor_install_checks.py:7`, `test_cli_doctor_full.py:8`, `test_cli_doctor.py:12` — import `doctor.py`
- `scripts/little_loops/cli/__init__.py:64` — imports `main_doctor`
- Per code-graph query, current callers of `check_floor` and `build_version_check` are test-only (`test_advisor.py`, `test_host_runner.py`) — no production call site exists yet for either.

### Tests (confirmed structure, from `test_cli_doctor.py`)

- `test_register_check_appends_and_runs` (`:682-697`) — save/clear/restore
  `doctor._CHECKS` via the `doctor` module object (not the imported names
  directly): snapshot `list(doctor._CHECKS)`, `.clear()` inside `try`,
  restore with `.clear()` + `.extend(original)` inside `finally`.
- `test_exit_code_ignores_informational_unsupported` (`:699-707`) — calls
  `_exit_code_for()` directly with a hand-built `CheckResult` list, no
  fixture needed.
- `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor`
  (`:715-754`) — combines the `_CHECKS` save/clear/restore with a
  `main_doctor()` call under a fixed five-`patch()` block: `sys.argv`,
  `little_loops.host_runner.resolve_host` (patched at its *definition*
  module — `doctor.py` imports it locally inside the function body),
  `little_loops.host_runner.apply_host_cli_from_config`,
  `little_loops.config.BRConfig`, `builtins.print`.

_Wiring pass added by `/ll:wire-issue`:_
- **No two-runner mocking pattern exists anywhere in the test suite.**
  Every `resolve_host` patch in `test_cli_doctor.py` /
  `test_cli_doctor_full.py` (25+ occurrences) uses a single
  `return_value=runner` bound to *all* calls — main_doctor's own
  resolution and a hypothetical second `_advisor_check` resolution would
  collapse onto the same mock. A test asserting `_advisor_check` resolves
  an *independent* advisor host needs a new pattern:
  `patch(..., side_effect=[runner_main, runner_advisor])` (no
  `side_effect=[` usage exists yet in `test_host_runner.py` either), or a
  distinct patch target if `_advisor_check` calls resolution through its
  own module-level wrapper. [Agent 3 finding]
- `scripts/tests/test_cli_doctor_trim.py::TestExitCodeIsolation::test_trim_findings_do_not_affect_exit_code`
  (~lines 254-266) calls real `main_doctor()` / `main_doctor(["--trim"])`
  with **no** `resolve_host` mock. If `_advisor_check` is unconditionally
  registered in `_CHECKS`, this test's un-mocked environment must degrade
  gracefully (mirroring the existing `HostNotConfigured` → `"(unknown)"`
  fallback in `test_probe_host_not_configured_falls_back_to_unknown`,
  `test_cli_doctor.py:635-653`) rather than raising or changing the exit
  code. [Agent 3 finding]
- `scripts/tests/test_cli_doctor_full.py::TestFullSection::test_run_full_checks_returns_check_result_per_verifier`
  (`:275-294`) asserts an exact name-set for `_FULL_CHECKS` (the `--full`
  verifier family) — unaffected as long as `_advisor_check` is registered
  via `_CHECKS`/`register_check`, not folded into `_run_full_checks`.
  Flagged here so the implementer doesn't accidentally wire it into the
  wrong registry. [Agent 3 finding]

## Acceptance Criteria

1. `ll-doctor` reports advisor host reachability and emits a warning (not
   an error) when the floor is `advisory` or `unknown`; exit code is
   unaffected by an advisory-only finding.
2. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` all pass.

## Out of Scope (covered by sibling children of FEAT-3044)

- **FEAT-3108** — `check_floor`, `rank_model`, `MODEL_RANKS`; this issue
  only consumes `check_floor`.
- **FEAT-3120** — `consult()`, the `ll-advise` CLI, `/ll:advise` skill.

Also unresolved and deferred (from FEAT-3044, unchanged):

- **Cross-host auth** — a `codex`/`gemini` advisor needs that host
  authenticated. Headless/cron runs may lack interactive auth; this
  issue's reachability check is exactly where that surfaces.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

1. The advisor's own `HostRunner` is resolved independently of the main
   orchestration host (`resolve_host()` at `doctor.py:1051`), without
   mutating `os.environ["LL_HOST_CLI"]` and without calling
   `apply_host_cli_from_config()` — no existing helper does this today
   (see Current Behavior); `resolve_host(env=...)` accepts an explicit env
   dict but that path is currently test-only.
2. `FloorResult.status` (`ok`/`violation`/`advisory`/`unknown`,
   `advisor.py:39-51`) is mapped onto `CheckResult.status`
   (`full`/`partial`/`unsupported`, `doctor.py:55-73`) — the two are
   distinct closed `Literal`s with no shared members, and this mapping is
   not specified anywhere in existing code; `advisory`/`unknown` results
   carry `severity="informational"` so `_exit_code_for`
   (`doctor.py:124-127`) never fails on them.
3. Reachability uses the same shape as `_probe_version`
   (`doctor.py:912-932`): `runner.detect()` guard, then
   `runner.build_version_check()` shelled out via `subprocess.run(...,
   timeout=10)`, with `TimeoutExpired`/`FileNotFoundError`/`OSError`/
   `HostNotConfigured` swallowed rather than raised.
4. The resulting `list[CheckResult]` reaches `_exit_code_for` — either
   folded by hand into `main_doctor()`'s `results` alongside
   `_capability_check_results(report)` at `doctor.py:1088`, or via a thin
   `@register_check` wrapper that resolves the advisor host internally
   (either is acceptable per Proposed Solution).
5. `python -m pytest scripts/tests/test_cli_doctor.py -v` passes, with new
   coverage modeled on
   `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor`
   (`:715`) for the "informational severity never fails exit code"
   behavior, using the `doctor._CHECKS` save/clear/restore pattern from
   `test_register_check_appends_and_runs` (`:682`) if a fake-check test
   double is needed.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Blocking dependency check before starting**: confirm whether
  FEAT-3043 (`AdvisorConfig` in `config-schema.json` /
  `config/core.py` / `config/orchestration.py`) and FEAT-3042
  (a named-host resolution primitive in `host_runner.py` independent of
  ambient `resolve_host()`) have landed. Neither exists in the tree today
  and neither is in this issue's `depends_on` — `_advisor_check` has no
  config surface to read an advisor host/model from without one of them,
  or must invent equivalent scaffolding itself.
- Update `_print_report()` in `doctor.py` — add an `advisor` key to the
  `--json` payload dict and a matching `_print_advisor_section()` call in
  `main_doctor()`'s fixed section-print sequence; the exit-code path
  (`_run_registered_checks()` → `_exit_code_for`) does not automatically
  populate the JSON/text output paths.
- Update `docs/reference/CLI.md` (`### ll-doctor`) — bump the "5 default
  checks" count and add `advisor` to the `--json` key enumeration.
- Update `docs/reference/API.md` (`describe_capabilities` section) —
  mirror the same key enumeration; add a `little_loops.advisor` module
  reference entry (currently absent).
- Write a `main_doctor()` integration test establishing the new
  dual-`resolve_host` mock pattern (`side_effect=[...]` or a distinct
  patch target), since no existing test differentiates two independent
  `resolve_host()` calls.
- Verify `test_cli_doctor_trim.py::TestExitCodeIsolation::test_trim_findings_do_not_affect_exit_code`
  still passes unmocked once `_advisor_check` is registered — it must
  degrade gracefully with no advisor host configured, not raise or flip
  the exit code.

## Impact

- **Priority**: P3 — a capability gap, not a defect.
- **Effort**: Small — one new check function in an existing module,
  composing two already-shipped pieces (FEAT-3108, FEAT-3120).
- **Risk**: Low — informational-only, cannot regress `ll-doctor`'s exit
  code by construction (`_exit_code_for`'s existing rule).
- **Breaking Change**: No.

## Related Key Documentation

- `docs/reference/HOST_COMPATIBILITY.md#orchestration-cli` — host abstraction.

## Status

**Open** | Created: 2026-08-08 | Priority: P3

## Verification Notes

> **Provenance note — 2026-08-08.** This issue was authored as `FEAT-3110`
> inside a non-worktree sandbox directory whose stray `.ll/` shadowed the
> project root, so its IDs were minted against a shadow issue tree and were
> invisible to the canonical `.issues/`. It was salvaged and re-IDed to
> `FEAT-3122`; sibling `FEAT-3111`/`FEAT-3112` became `FEAT-3120`/`FEAT-3121`,
> and the redundant `FEAT-3109` grouping layer was collapsed into `FEAT-3044`
> (its scope now carried by `FEAT-3120`). **The verification history below
> predates that re-ID** and reasons about IDs that never existed canonically
> — treat its BROKEN_REF/DEP_ISSUES findings as historical, not current.
> This issue still needs a fresh `/ll:refine-issue` + `/ll:verify-issues`
> pass (it carries `verify_verdict: NON_VALID`, confidence 50/58).

_Added by `/ll:verify-issues` — 2026-08-08:_

Verdict: **DEP_ISSUES** (stale target, re-checked). The prior note below
(BROKEN_REF) is now out of date: `FEAT-3120` has since been filed
(`.issues/features/P3-FEAT-3120-advisor-consult-ll-advise-cli-and-skill.md`),
so the reference itself is no longer broken. But its `status: done` does
not mean the dependency is actually satisfied — `FEAT-3120`'s own
`## Resolution` reads `**Status**: Decomposed`, `**Decomposed into**:
FEAT-3120, FEAT-3121`, with the note "Work for FEAT-3120 is now carried by
its child issues; this parent was closed by rn-decompose." Both
`FEAT-3120` and `FEAT-3121` carry `status: deferred`. Per this repo's
dependency convention (only `done`/`cancelled` resolve `depends_on`
edges), `FEAT-3120` reads as a satisfied prerequisite even though none of
`consult()`, `AdvisorVerdict`, the `ll-advise` CLI, or the `/ll:advise`
skill exist in code — confirmed by searching every branch in the repo
(including `epic/epic-3041-host-agnostic-advisor`, the branch this work
would actually land on) for `def consult` in `advisor.py`: no match
anywhere. `scripts/little_loops/advisor.py` on that branch is still the
same 112-line FEAT-3108-only surface (`FloorResult`, `rank_model`,
`check_floor`); `cli/advise.py` does not exist on any branch.

**Recommended action**: repoint `depends_on` from `FEAT-3120` to
`FEAT-3120` (and `FEAT-3121` if the skill wrapper matters for this issue's
scope) — those are the actual open, unimplemented prerequisites; leaving
`FEAT-3120` in place will let dependency-resolution tooling treat this
issue as unblocked when the underlying `consult()`/`ll-advise` surface
still doesn't exist.

---

_Superseded note, kept for history — verified 2026-08-08 against a tree
state where `FEAT-3120` had not yet been filed:_

Verdict: **DEP_ISSUES** (BROKEN_REF). `depends_on: [FEAT-3108, FEAT-3120]`
names FEAT-3120, but no `FEAT-3120` issue file exists anywhere in the tree
(`grep -rl "^id: FEAT-3120$" .issues/` returns nothing). FEAT-3108 does
exist and is `status: done` (`.issues/features/P3-FEAT-3108-...md`), so
that half of the dependency is satisfied.

This issue's own "Dependency-status discrepancy" note (Codebase Research
Findings, above) describes FEAT-3120 as if it exists — `status: done`,
Resolution "Decomposed" into FEAT-3120/FEAT-3121, both `status: deferred`.
That description does not match the current backlog: `EPIC-3111` and
`BUG-3112` do exist, but they are unrelated worktree-state-inheritance
issues (from a different epic), not advisor successors. `FEAT-3120` is
referenced only in prose, by ID, across FEAT-3037, FEAT-3044, and
FEAT-3108, as the planned-but-never-filed issue for `consult()` /
`AdvisorVerdict` / the `ll-advise` CLI — it was apparently never created
as its own file. The epic (`EPIC-3041`) records FEAT-3037's actual
decomposition as FEAT-3042/FEAT-3043/FEAT-3044, not FEAT-3120.

Everything else checked out: `scripts/little_loops/advisor.py` (112
lines) matches the issue's description of FEAT-3108's shipped surface
(`FloorResult`, `rank_model`, `check_floor`, no `consult()`); `cli/doctor.py`
line numbers/content for `CheckResult`, `_capability_check_results`,
`_ADVISORY_CAPABILITIES`, `_run_registered_checks`, `_exit_code_for`,
`_probe_version`, and the `main_doctor()` call sequence all match current
code; `config-schema.json`/`config/core.py`/`config/orchestration.py`
confirmed to have zero `advisor` references; `host_runner.py` confirmed to
have no `resolve_host_named()`/`consult()`; `docs/reference/CLI.md`
confirmed still describing "5 default install-surface checks" with no
`advisor` key. No active required decisions-log rules to check (log has
no entries).

**Recommended action**: either file the missing `FEAT-3120` issue (if the
`consult()`/`ll-advise` work is still intended as a separate, blocking
prerequisite) or repoint `depends_on` to whatever issue currently owns
that scope — decide against `EPIC-3041`'s actual decomposition
(FEAT-3042/FEAT-3043/FEAT-3044), not the FEAT-3120/FEAT-3121 IDs cited in
this file's own research notes, which belong to an unrelated epic.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Confirmed via `codebase-locator`: `EPIC-3041`'s actual decomposition traces `FEAT-3037` (host-agnostic advisor) → `FEAT-3042` (`.issues/features/P3-FEAT-3042-advisor-shared-blocking-json-transport.md`, shared blocking-JSON transport / `resolve_host_named`) + `FEAT-3043` (`.issues/features/P3-FEAT-3043-advisor-config-block.md`, `AdvisorConfig` schema block) + `FEAT-3044` (`.issues/features/P3-FEAT-3044-advisor-core-cli-and-doctor-check.md`) → `FEAT-3044` further decomposed into `FEAT-3108` (done) + `FEAT-3120` (never filed) + this issue (`FEAT-3122`). This corroborates the existing recommendation below: if `_advisor_check` needs a config surface or a second-host resolution primitive, those are `FEAT-3043` and `FEAT-3042` respectively — not `FEAT-3120`, and not the unrelated `FEAT-3120`/`FEAT-3121` IDs.

### 2026-08-10 (`/ll:verify-issues`)

Verified 2026-08-10: doctor.py confirmed to have exactly 5 `@register_check` checks (matches CLI.md), no advisor check exists yet — core claim valid. However this issue's own `depends_on: [FEAT-3108, FEAT-3120]` is stale/contested per its extensive internal Verification Notes, which already flag it needs a fresh `/ll:refine-issue` pass to repoint dependencies to FEAT-3042/FEAT-3043. Re-running that refine pass is recommended before implementation.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-08_

**Readiness Score**: 50/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 58/100 → LOW

### Concerns
- Architecture choice deferred: doctor.py has 4 disagreeing severity-threading
  shapes and no canonical fold-vs-`@register_check` pattern; this issue
  explicitly leaves the choice open rather than deciding one.
- Two closed `Literal` types (`FloorResult.status` vs `CheckResult.status`)
  need a translation mapping that no existing code specifies.

### Gaps to Address
- `FEAT-3108` (`rank_model`/`check_floor`) is `done` on `main` but does not
  exist at all on `epic/epic-3041-host-agnostic-advisor` — the branch this
  work would actually land on has no `scripts/little_loops/advisor.py`.
  Land/merge FEAT-3108 onto that branch before starting.
- `FEAT-3120` as named in `depends_on` is not a real issue in the canonical
  (main) tracker — that ID belongs to an unrelated `BUG-3109` on `main`; it
  only exists in this epic-scoped worktree's local `.issues/` copy. Repoint
  `depends_on` against `main`'s issue tracker (not this worktree's stale
  copy) before treating it as resolved.
- `consult()`/`AdvisorVerdict`/the `ll-advise` CLI — the surface this
  issue's Parent Issue section cites as an "established host-resolution
  isolation convention" to follow — do not exist on any branch, confirmed
  by direct grep against both `main` and the epic branch.
- `AdvisorConfig` (FEAT-3043) landed on the epic branch (commit `6c29f69c`)
  but not on `main`, and is not in this issue's `depends_on` — confirm
  which branch state this issue targets; `_advisor_check` needs this
  config surface to read an advisor host/model from.
- A named-host resolution primitive (FEAT-3042, `resolve_host_named()`)
  does not exist on any branch — `_advisor_check` has no primitive to
  instantiate an independent advisor `HostRunner` without inventing that
  scaffolding itself.

### Escalation

- **Unresolved options (score_ambiguity ≤ 10)**: consider
  `/ll:decide-issue FEAT-3122` for the deferred severity-shape/fold-vs-wrapper
  choice — but the dominant blocker here is the dependency chain above, not
  a design decision; resolve those first.

### Outcome Risk Factors
- Moderate cross-module complexity: touches doctor.py's check registration,
  severity mapping, config resolution, and a second independent host
  resolution — more than a single contained function body.
- Ambiguity risk: 4 disagreeing severity-threading shapes in doctor.py with
  no canonical one chosen; implementer will need to pick one under judgment.

### 2026-08-12 (`/ll:verify-issues`)

Re-confirmed 2026-08-12, no new drift: `verify_verdict: NON_VALID` still
accurate — no `_advisor_check` in `cli/doctor.py`'s registered checks and
`scripts/little_loops/advisor.py` is still 112 lines (FEAT-3108's surface
only).

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:reconcile-issue` - 2026-08-10T18:26:44 - `7405995b-78ac-4bf8-8825-45f100c3421d.jsonl`
- `/ll:refine-issue` - 2026-08-10T16:35:42 - `8f3abfd3-6623-4955-b89f-579e5adefbdd.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:25 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:confidence-check` - 2026-08-08T21:00:42 - `33a02969-b861-45a0-9dfa-bda36f49c2f3.jsonl`
- `/ll:reconcile-issue` - 2026-08-08T20:57:33 - `4da796c5-b40f-4549-8b2d-ec7d06d66491.jsonl`
- `/ll:verify-issues` - 2026-08-08T20:55:22 - `cf0cb0be-6bdf-436b-b626-68fabe345e75.jsonl`
- `/ll:refine-issue` - 2026-08-08T20:50:51 - `c1759e30-2d73-4b40-b2ed-e8f1f54f1fce.jsonl`
- `/ll:verify-issues` - 2026-08-08T20:46:46 - `a2c9057e-841f-4d92-974f-4c2f92f6d2ef.jsonl`
- `/ll:verify-issues` - 2026-08-08T13:51:40 - `verify-check-auto-session`
- `/ll:wire-issue` - 2026-08-08T20:43:18 - `64c1d4cd-50b9-4634-8852-3b74b00359df.jsonl`
- `/ll:refine-issue` - 2026-08-08T20:37:10 - `a92555e8-6e42-42da-bbde-dbd82186b3b1.jsonl`
- `/ll:issue-size-review` - 2026-08-08T17:51:40 - `45d84ae4-d7b1-4342-a5e2-fb2f78de65a2.jsonl`
