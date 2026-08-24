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
- FEAT-3043
- FEAT-3042
labels:
- planning-hub
verify_verdict: VALID
size: Medium
reconcile_attempted: true
confidence_score: 90
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
decision_needed: false
---

# FEAT-3122: ll-doctor advisor-reachability check

## Summary

Add `_advisor_check` to `cli/doctor.py`: report advisor host reachability
and warn (never fail) when the configured advisor model does not outrank
the main model. This is the third and last architecturally separable
concern of FEAT-3044's "ll-doctor check" subsection.

## Use Case

A maintainer turns on the advisor (`advisor.enabled: true`, `advisor.host:
codex`) and expects `/ll:advise` and the `pre_done` consult trigger to work.
Today the first sign that the advisor host isn't authenticated, isn't
installed, or isn't on PATH is a *failed consult mid-loop* — the automation is
already running, the context is already spent, and the error surfaces as a
transport failure rather than a configuration one. Cross-host auth is the
common case: a `codex` or `gemini` advisor needs that host separately
authenticated, and headless/cron runs frequently lack the interactive auth a
developer's laptop has.

`ll-doctor` is where a maintainer already goes to answer "is my install
healthy?", and it already probes the *main* host's binary and version. This
issue extends that same one-command check to cover the advisor host, so a
broken advisor is caught before a loop depends on it — and reports it as a
warning rather than a failure, because an unconfigured or cross-host advisor
is a deliberate configuration, not a broken install.

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

- **Dependency status** (original 2026-08-08 note superseded by the
  2026-08-10 re-check below; condensed 2026-08-23): `depends_on` now reads
  `[FEAT-3108, FEAT-3120, FEAT-3043, FEAT-3042]` — FEAT-3108 is `done`, the
  other three are real, open, canonical issues. `scripts/little_loops/advisor.py`
  (112 lines on `main`) contains only FEAT-3108's pieces (`MODEL_RANKS`,
  `FloorResult`, `rank_model`, `check_floor`); `consult()`, `AdvisorVerdict`,
  the `ll-advise` CLI, and the "resolve the advisor host without mutating
  `LL_HOST_CLI`" convention all arrive with FEAT-3042/FEAT-3120 — this issue
  is genuinely blocked until they land.
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

_2026-08-10 refine pass (condensed 2026-08-23 — its "these symbols do not
exist yet" inventory is superseded by the note directly below):_

- **Dependency-chain re-check**: `depends_on` needs **no repointing**.
  FEAT-3120, FEAT-3042, and FEAT-3043 are all real, canonical tracker issues
  — not the unrelated worktree-state-inheritance IDs the earlier Verification
  Notes confused them with. The prior "Recommended action: repoint
  depends_on" notes are moot.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **Dependency chain now fully resolved (2026-08-23 refine pass)**: `FEAT-3108`, `FEAT-3120`, `FEAT-3043`, and `FEAT-3042` — every ID in this issue's `depends_on` — are all `status: done`. `scripts/little_loops/advisor.py` is now 522 lines and contains `consult()`, `AdvisorVerdict`, `resolve_task_key`, `should_consult`, `consult_for_trigger` in addition to FEAT-3108's `check_floor`/`rank_model`/`MODEL_RANKS`. `resolve_host_named(name: str) -> HostRunner` exists at `host_runner.py:2008-2016` (`return resolve_host({"LL_HOST_CLI": name})`) — the exact "resolve without mutating `LL_HOST_CLI`" primitive this issue's Decision Rules require, and it is not test-only: `consult()` is its one production caller (`advisor.py:265`). `config.advisor` (`AdvisorConfig`, `config/orchestration.py:108-140`) exists with `enabled`/`host`/`model`/`min_tier`/`timeout_seconds`/`triggers`/`max_consults_per_task` fields, exposed via `BRConfig.advisor` (`config/core.py:465-468`). This issue is no longer blocked by any missing primitive.
- **`cli/doctor.py` now registers 6 default checks, not 5** (`docs/reference/CLI.md:319` — a "Schema Drift" check, `_schema_drift_data`/`_print_schema_drift_section`/`_schema_drift_check` at `doctor.py:398-523`, was added by ENH-3242 since this issue was last refined). No `_advisor_check`/`_advisor_data`/`_print_advisor_section` symbol exists in `doctor.py` — confirmed by grep.
- **The four disagreeing severity-threading shapes have not converged into one, but the two newest checks agree**: `_schema_drift_check` and `_loop_validity_check` both thread `severity` through their own `_xxx_data()` dict (`data["severity"]`, no default) — the same shape #1 this issue's prior research already identified, now with a second, more recent instance following it.

## Expected Behavior

- `ll-doctor` reports advisor host reachability.
- `ll-doctor` warns (does not fail) about the capability-floor result for
  **all four** `check_floor` (FEAT-3108) classifications — `ok`,
  `advisory`, `unknown`, **and `violation`**. A misconfigured advisor is
  not a broken install, so no floor result is error-tier here (this is a
  deliberate divergence from `consult()`, which *raises*
  `CapabilityFloorViolation` on `violation` because it is about to spend a
  real consult on a weaker model; `ll-doctor` only reports).
- No advisor finding — floor or reachability — ever affects `ll-doctor`'s
  overall exit code.
- The advisor check surfaces in **all three** output paths: the exit-code
  path (via `@register_check`), the `--json` payload (`advisor` key), and
  the text-mode section list.

## Proposed Solution

`_advisor_check` sets `severity="informational"` on **every** result it
emits — both floor results (all four `FloorResult.status` values) and the
reachability result — mirroring the existing `_ADVISORY_CAPABILITIES =
frozenset({"claude_md_suppression"})` pattern (`doctor.py:95`), where
`informational` means "reported but never fails the run". Per the
Decision Rationale below, `_advisor_check` is a
self-resolving `@register_check` function (Option B): it takes no
arguments, resolves the advisor's `config.advisor.host`/`.model` and
`HostRunner` internally, and registers into `_CHECKS` like every other
default check — not the `_capability_check_results()` fold pattern.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

**Option A**: Fold pattern, mirroring `_capability_check_results()` (`doctor.py:76-113`). `main_doctor()` resolves the advisor's `HostRunner` via `resolve_host_named(config.advisor.host)` and calls a plain `_advisor_check(runner, config)` function by hand — not `@register_check`-registered — concatenating its results into `results` the same way `_capability_check_results(report) + _run_registered_checks()` (`doctor.py:1219`) already does. This is the only pattern precedent for a check needing call-time state from outside its own body, but every existing dual-host resolution (`consult()`, `advisor.py:256,265`) is self-contained and does not depend on anything `main_doctor()` has already resolved — the advisor's own host and config are independently resolvable, so the "needs a value only available inside `main_doctor()`'s body" rationale that motivates the fold pattern does not strictly apply here.

**Option B**: Self-resolving `@register_check`, following the `_schema_drift_check`/`_loop_validity_check` triad shape (`doctor.py:398-523`, `:526-606`) and severity shape 1 (`data["severity"]`, no default — the shape both of the two most recently added checks use). `_advisor_check()` takes no arguments, resolves `config.advisor.host`/`.model` internally (e.g. via `BRConfig()`), calls `resolve_host_named(config.advisor.host)` itself, and registers into `_CHECKS` via `@register_check` like every other default check. No existing `@register_check` function resolves a `HostRunner` today (confirmed by grep — only `_capability_check_results`, which is unregistered, and `_probe_version`, which receives its runner as a parameter, touch host resolution), so this would be the first, but it keeps `_advisor_check` participating automatically in the exit-code path via the same mechanism as every other default check, and avoids introducing a second unregistered-check code path alongside the existing single `_capability_check_results` special case.

> **Selected:** Option B — matches the two most recently established check triads exactly and integrates with the exit-code path via the existing registry, with zero special-casing.

### Decision Rationale

**Selected**: Option B — self-resolving `@register_check`, following the `_schema_drift_check`/`_loop_validity_check` triad shape and severity shape 1.

**Reasoning**: Option B reuses the exact `_xxx_data()`/`_print_xxx_section()`/`@register_check def _xxx_check()` triad and `data["severity"]` (no default) convention already established twice by the two most recently added checks (`_schema_drift_check`, `_loop_validity_check`), and reuses `resolve_host_named(config.advisor.host)` exactly as `advisor.py:consult()` already does. It requires zero changes to `main_doctor()`'s registry plumbing — `register_check()` accepts any no-arg `Callable[[], list[CheckResult]]`, so `_advisor_check` participates in `_run_registered_checks()`/`_exit_code_for()` automatically, the same as every other default check. Option A instead extends `_capability_check_results()`, the codebase's one explicitly-acknowledged exception to the registry convention (comment at `doctor.py:76-80` states new checks should register against `_CHECKS`), compounding that special case with a second hand-concatenated, unregistered function at `main_doctor()`'s `results = ...` line. A guard for the unconfigured-advisor case (mirroring `_schema_drift_data`/`_loop_validity_data`'s "prerequisite absent → informational" branch, and `consult()`'s `AdvisorNotConfigured` handling) is required regardless of option, so it is not a differentiator.

**Scoring Summary**:

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — Fold pattern | 1 | 1 | 1 | 1 | 4/12 |
| B — Self-resolving `@register_check` | 3 | 2 | 3 | 2 | **10/12** |

**Key evidence**:
- `register_check()`/`_CHECKS` (`doctor.py:81-87`) accept any no-arg check with zero registry changes; `_run_registered_checks()`/`_exit_code_for()` (`:116-127`) already iterate `_CHECKS` uniformly — Option B needs none of `main_doctor()`'s manual concatenation.
- `_schema_drift_data`/`_loop_validity_data` (`doctor.py:398-523`, `:526-606`) both guard an absent prerequisite by returning `{"status": "unsupported", "severity": "informational", ...}` — the exact shape an unconfigured-advisor guard needs.
- `_capability_check_results()`'s own comment (`doctor.py:76-80`) states it is deliberately *not* registered and that new checks should use the registry — Option A works against its own cited precedent's stated intent.
- `test_cli_doctor_install_checks.py::TestSchemaDrift` (~`:227`) is a direct testability precedent for Option B: bare `_data()`-level assertions, no `main_doctor()`/host mocking required.

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

`ll-doctor` -> `_run_registered_checks` -> `_advisor_check` ->
`check_floor` (FEAT-3108) / `HostRunner.build_version_check`

### Decision Rules

- `severity="informational"` on **every** emitted `CheckResult`, floor
  status irrelevant — `_exit_code_for` only fails on `severity == "error"
  and status == "unsupported"`, so `informational` alone is sufficient to
  guarantee the exit code is untouched regardless of which `status` value
  is chosen.
- The advisor's own host resolution must not call
  `apply_host_cli_from_config()` and must not mutate `LL_HOST_CLI`,
  consistent with FEAT-3120's isolation requirement for `consult()`.
- **Main host/model source** (previously unspecified — resolved here):
  `ll-doctor` has no notion of a "main model", so `_advisor_data()`
  mirrors `consult()`'s fallbacks verbatim (`advisor.py:256-257`):
  `main_host = resolve_host().name`, `main_model = DEFAULT_LLM_MODEL`
  (`fsm/schema.py:24`, currently `"sonnet"`). Import
  `DEFAULT_LLM_MODEL` from `little_loops.fsm.schema` inside the function
  body, as `consult()` does.
  - Consequence to expect, not to debug: with stock config
    (`advisor.model="opus"`, `advisor.host="claude-code"`, main
    `claude-code`/`sonnet`) `check_floor` returns `"ok"`. The floor check
    is near-vacuous until someone configures a cross-host advisor or a
    weaker advisor model — that is correct behavior, not a broken mapping.
- **`HostNotConfigured` must be caught by `_advisor_data()` itself.**
  `resolve_host()` (main host) and `resolve_host_named()` (advisor host)
  both raise `HostNotConfigured` when nothing is on PATH / the name is
  unregistered, and `_run_registered_checks()` (`doctor.py:116-122`) has
  no `try`/`except` — an uncaught raise there takes down all of
  `ll-doctor`. `_probe_version` swallows it, but only *after* it already
  holds a runner, so it is not a safety net for either resolution call.
  Wrap both in `except HostNotConfigured` → the standard
  `{"status": "unsupported", "severity": "informational", "note": ...}`
  early return.
  - Mitigating fact: `AdvisorConfig.enabled` defaults to `False`, so
    AC2's guard short-circuits before either resolution in any default
    project. `test_cli_doctor_trim.py::TestExitCodeIsolation` is
    therefore safe by construction, not by luck — but the guard above is
    still required for the `enabled: true` + absent-binary case.
- **Two `CheckResult`s, not one** (previously unspecified): emit
  `advisor_host` (reachability) and `advisor_floor` (capability floor) as
  separate named results, so each carries its own `note` and a consumer
  can tell "advisor binary missing" from "advisor model is weaker".
  - Reachability status mapping: `_probe_version(...)` returning a
    non-empty string → `status="full"`; empty string → `status="unsupported"`
    (still `severity="informational"`, so the exit code is unaffected).
  - Floor status mapping: `FloorResult.status == "ok"` → `status="full"`;
    `"advisory"` / `"unknown"` / `"violation"` → `status="partial"`.
    `FloorResult.detail` carries straight through into `CheckResult.note`.
- **`rank_model` normalizes model aliases** through `resolve_model_alias()`
  (`advisor.py:81-88`), so `"opus"` and `"claude-opus-5"` rank identically.
  Tests must not assume raw-string comparison of model names.

### Codebase Research Findings

_Refine-pass findings, consolidated 2026-08-23 (two empty/duplicate date
headers removed):_

- **`AdvisorConfig` exact fields** (`config/orchestration.py:108-140`): `enabled: bool = False`, `host: str | None = None`, `model: str = "opus"`, `min_tier: str | None = None`, `timeout_seconds: int = 180`, `triggers: list[str] = field(default_factory=list)`, `max_consults_per_task: int = 3`. `enabled`/`host`/`model` are sufficient for `_advisor_check` — no new config surface is needed (this issue's earlier "config surface doesn't exist" concern no longer applies).
- **`check_floor` classification order** (`advisor.py:91-139`): (1) `advisor_host != main_host` -> `"advisory"` (checked before any rank lookup, cross-host ranks are incomparable); (2) same host, either model unrankable via `rank_model()` -> `"unknown"`; (3) same host, `advisor_rank < main_rank` -> `"violation"`; (4) same host, `advisor_rank >= main_rank` -> `"ok"`. `rank_model()` only has a populated table for `"claude-code"` (haiku=1, sonnet=2, opus=3, fable=4); every other host maps every model to `None`.
- **`resolve_host_named` mechanics confirmed**: `resolve_host_named(name)` calls `resolve_host({"LL_HOST_CLI": name})` — an explicit one-key env dict, so ambient `os.environ`/`LL_HOST_CLI` is never read or mutated. An unregistered host name raises `HostNotConfigured` immediately (no PATH-probe fallback). `consult()` demonstrates the exact dual-host pattern this issue needs: ambient `resolve_host().name` for the main host (`advisor.py:256`) alongside named `resolve_host_named(advisor_host)` for the advisor host (`advisor.py:265`).
- **`cli/doctor.py` has converged on a three-function triad for every default-registered check**, confirmed across `_schema_drift_data`/`_print_schema_drift_section`/`_schema_drift_check` (`doctor.py:398-523`, the newest and cleanest exemplar) and `_loop_validity_data`/`_print_loop_validity_section`/`_loop_validity_check` (`doctor.py:526-606`): a pure `_xxx_data() -> dict` (never touches `CheckResult`, returns at minimum `status`/`severity`/`note`), a `_print_xxx_section() -> None` (renders the dict in text mode), and an `@register_check def _xxx_check() -> list[CheckResult]` (wraps the dict into `CheckResult`(s)). `_advisor_check` fits this triad directly.
- **Reachability probe can reuse `_probe_version` verbatim**: `_probe_version(runner: HostRunner) -> str` (`doctor.py:1040-1061`) already does `runner.detect()` guard + `runner.build_version_check()` + `subprocess.run(..., timeout=10)`, swallowing `(subprocess.TimeoutExpired, FileNotFoundError, OSError, HostNotConfigured)` to `""`. Calling `_probe_version(resolve_host_named(advisor_host))` reuses this without modification.
- **No existing dict-mapping/dispatch translates `FloorResult.status` into `CheckResult`'s vocabulary anywhere in the codebase** (confirmed by grep across doctor.py/advisor.py/host_runner.py) — `consult()`'s own handling of `FloorResult.status` (raise on `"violation"`, print-to-stderr on `"advisory"`/`"unknown"`) is the only existing consumer, and it does not produce a `CheckResult`. This translation is still net-new, as the issue's Decision Rules already state.
- **Two hand-enumerated call sites still need a line added, not just `@register_check`**: `main_doctor()`'s text-mode print sequence (`doctor.py:1201-1213`, one `_print_xxx_section()` call per check) and `_print_report`'s JSON dict assembly (`doctor.py:1064-1101`, one key per check's `_data()` output) are both hand-enumerated rather than derived from `_CHECKS` — `@register_check` alone makes `_advisor_check` participate in the exit-code path but not in either output path.

- **`_probe_version` is not a safety net for host *resolution*.** It swallows
  `HostNotConfigured`, but only inside its own body — i.e. only once it
  already holds a `HostRunner`. The `resolve_host()` / `resolve_host_named()`
  calls that *produce* that runner are outside it and raise freely; see
  Decision Rules for the required guard.
- `advisor.consult()`'s own `FloorResult.status` handling (`advisor.py:259-263`) is a plain `if`/`elif` chain (`if floor.status == "violation": raise ...`; `if floor.status in ("advisory", "unknown"): print(...)`), not a dict/dispatch mapping — confirms no Literal-to-Literal status-translation convention exists anywhere in the tree (grepped `doctor.py`, `advisor.py`, `host_runner.py`, `fsm/schema.py`, `observability/schema.py`, `learning_tests/`). `_advisor_check`'s `FloorResult.status` → `CheckResult.status`/`severity` mapping remains new work with only a branching-style precedent to draw on, not a structural one to copy.
- `consult()`'s dual-host resolution is order-dependent, not simultaneous: the main host resolves unconditionally near the top (`resolved_main_host = main_host or resolve_host().name`, `advisor.py:256`), the floor check runs against it (`:259`), and the advisor host resolves via `resolve_host_named(advisor_host)` only afterward, gated on the floor check not having raised (`:265`). `_advisor_check` is not required to mirror this ordering (it never raises), but it is the only concrete precedent in the tree for sequencing two host resolutions.
- Every "prerequisite absent → informational, non-failing" guard in `doctor.py` shares one exact shape: an early return of `{"status": "unsupported", "severity": "informational", "note": "<short reason>"}` via a cheap existence check (`Path.exists()`/`Path.is_dir()`) performed before any I/O that could create the resource — confirmed at `_decisions_store_data` (`doctor.py:291-296`, "not configured (optional)"), `_history_db_data` (`:361-362`, "not yet created"), `_schema_drift_data` (`:425-426`, "not yet created"), `_loop_validity_data` (`:549-556`, "no loops found"), and the `--full`-gated `_full_triggers_data`/`_full_design_tokens_data`/`_full_des_audit_data` (`:725-729`, `:852-857`, `:892-897`). The unconfigured-advisor guard in `_advisor_data` should follow this exact shape.

### Signatures

_Line numbers below re-verified against `main` on 2026-08-23; the earlier
values in this section (`advisor.py:64-112`, `:54-61`, `:39-51`,
`doctor.py:912-932`) were stale and are corrected here._

- `check_floor(advisor_host: str, advisor_model: str, main_host: str, main_model: str) -> FloorResult` — `advisor.py:91-139`
- `FloorResult` (frozen dataclass, `advisor.py:67`): `status: Literal["ok", "violation", "advisory", "unknown"]`, `detail: str`
- `rank_model(host: str, model: str) -> int | None` — `advisor.py:81-88`; `MODEL_RANKS: dict[str, dict[str, int]]` (`advisor.py:23-36`) is populated only for `"claude-code"`; every other host key maps to `{}`
- `resolve_host_named(name: str) -> HostRunner` — `host_runner.py:2008-2016`; `resolve_host(env: dict | None = None) -> HostRunner` — `host_runner.py:1574-1619`. **Both raise `HostNotConfigured`**; see Decision Rules.
- `DEFAULT_LLM_MODEL: str = "sonnet"` — `fsm/schema.py:24`
- `AdvisorConfig` — `config/orchestration.py:108-140`, reachable as `BRConfig(...).advisor` (`config/core.py:465-468`). Fields used here: `enabled: bool = False`, `host: str | None = None`, `model: str = "opus"`.
- `CheckResult` (`doctor.py:55-73`): `status: Literal["full", "partial", "unsupported"]`, `severity: Literal["error", "informational"] = "error"` (default) — this is a **different closed `Literal` from `FloorResult.status`**; the two do not share member names, so `_advisor_check` must translate one into the other. That mapping is now specified in Decision Rules above.
- `HostRunner.build_version_check() -> HostInvocation` — Protocol method, per-runner implementations at `host_runner.py:260,402,698,826,900,1071,1251,1450`
- `_probe_version(runner: HostRunner) -> str` (`doctor.py:1040-1061`) — the only existing host-reachability probe: checks `runner.detect()`, then `subprocess.run([invocation.binary, *invocation.args], capture_output=True, text=True, timeout=10)`, swallowing `TimeoutExpired`/`FileNotFoundError`/`OSError`/`HostNotConfigured` to `""`. It receives its `HostRunner` as a parameter rather than resolving one itself, and `main_doctor()` calls it with the *same* runner from `resolve_host()` at `doctor.py:1051` — i.e. today's only probe reuses the single resolved runner, it does not resolve a second one.
- `_exit_code_for(results: list[CheckResult]) -> int` (`doctor.py:124-127`): `has_error = any(r.severity == "error" and r.status == "unsupported" for r in results)`. This predicate keys on BOTH `severity == "error"` AND `status == "unsupported"` together — an advisory/unknown `CheckResult` is excluded by `severity` alone, regardless of what `status` value is chosen for it.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/doctor.py` — add the `_advisor_data()`/
  `_print_advisor_section()`/`@register_check def _advisor_check()` triad
  (model: `_schema_drift_data`/`_print_schema_drift_section`/
  `_schema_drift_check`, `doctor.py:398-523`); add one line to
  `main_doctor()`'s text print sequence (`doctor.py:1201-1213`) and one
  key to `_print_report`'s JSON dict (`doctor.py:1064-1101`).

### Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — advisor host support matrix;
  explicit note that cross-host capability floors are **advisory, not
  enforced**.

_Wiring pass added by `/ll:wire-issue`, corrected 2026-08-23:_
- `docs/reference/CLI.md` (`### ll-doctor`, line ~319) — hardcodes both the
  check *count* and the `--json` key enumeration; both need `advisor` added.
  **The count now reads "6", not "5"** (ENH-3242's Schema Drift landed after
  this note was written) — bump it to **7**.
- `docs/reference/API.md` — `describe_capabilities` (line ~9708) duplicates
  the same `--json` key enumeration in prose and must stay in lockstep with
  CLI.md's copy; it is currently missing both `advisor` and `schema_drift`.
  **A `## little_loops.advisor` module-reference section already exists**
  (line ~10842, covering `rank_model`/`check_floor`/`consult`/
  `AdvisorVerdict`/`record_consult`/`should_consult`) — this note's original
  "zero coverage" claim is stale; no new module section is needed.
- `docs/reference/HOST_COMPATIBILITY.md` (line ~568) — its default-check
  enumeration is missing Schema Drift already; add both it and `Advisor`.

_Wiring pass added by `/ll:wire-issue`, 2026-08-24:_
- `docs/ARCHITECTURE.md:850` — the `CapabilityReport` table row states in
  prose that `ll-doctor --json`'s payload is a superset of `CapabilityReport`
  and enumerates the extra install-surface keys (`entry_points`,
  `skills_commands`, `decisions_store`, `history_db`, `loop_validity`). This
  enumeration is already stale independent of this issue (missing
  `schema_drift`, an ENH-3242 drift) — add both `schema_drift` and `advisor`
  while touching this line. [Agent 2 finding]
- `CHANGELOG.md:182-183` — an existing unreleased `### Added` entry reads
  "**Advisor core.** `ll-advise` CLI, a capability floor, and an `ll-doctor`
  check ship together (FEAT-3044)." Since this issue's `ll-doctor` check is
  FEAT-3122's own deliverable landing separately from FEAT-3044/3120/3108,
  either add a standalone FEAT-3122 changelog line when this check lands, or
  correct the existing FEAT-3044 entry's scope so it stops claiming the
  `ll-doctor` check shipped with it. [Agent 2 finding]

### Configuration

**No new config surface is required — this issue reads existing fields only.**

_The `/ll:wire-issue` pass originally flagged two blocking gaps here
(no `AdvisorConfig`, no named-host primitive). **Both are closed** as of the
2026-08-23 epic merge; the original text is in git history._

- `AdvisorConfig` exists at `config/orchestration.py:108-140`, reachable as
  `BRConfig(...).advisor` (`config/core.py:465-468`), with an `advisor` block
  in `config-schema.json`. `_advisor_check` reads `enabled` / `host` / `model`
  and adds no fields of its own. (`min_tier` is explicitly out of scope — see
  Out of Scope.)
- `resolve_host_named()` exists at `host_runner.py:2008-2016` and is the
  sanctioned primitive for an advisor-specific `HostRunner`. Reaching into
  `_HOST_RUNNER_REGISTRY` directly, or mutating `LL_HOST_CLI`, remains
  forbidden by this issue's Decision Rules.

### Tests

- `scripts/tests/test_cli_doctor.py` — model `_advisor_check`'s
  "informational severity never fails exit code" behavior after
  `test_exit_code_ignores_informational_unsupported` (`:716`), and use
  the save/clear/restore-`_CHECKS` isolation pattern from
  `test_register_check_appends_and_runs` (`:699`) /
  `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor`
  (`:732`) if `_advisor_check` needs a fake-check test double.
- `scripts/tests/test_cli_doctor_install_checks.py::TestSchemaDrift`
  (~`:227`) is a lighter-weight alternative: call the bare `_advisor_data()`
  helper directly (no `main_doctor()`, no host mocking) and assert on its
  `status`/`severity`/`note` keys.
- `scripts/tests/test_advisor.py::TestConsult::test_cross_host_advisory_proceeds`
  (`:181-201`) / `::test_capability_floor_violation_refuses_consult`
  (`:164-179`) are the closest existing dual-host/floor-status analogs.

**Minimum new coverage** (one test per specified behavior, so the
first-of-kind decisions above are pinned rather than re-derived later):

1. `advisor.enabled=False` → both results present, `severity="informational"`,
   note names "not configured"; **no** host resolution attempted (assert the
   `resolve_host*` mocks were never called).
2. `advisor.enabled=True`, `host` unset → same non-failing shape as (1).
3. Floor `violation` → `severity="informational"`, `status="partial"`, and
   `_exit_code_for([...])` still returns `0`. This is the AC-1 divergence from
   `consult()` and is the single most important regression guard here.
4. `HostNotConfigured` raised from `resolve_host()` **and** from
   `resolve_host_named()` (two cases) → `_advisor_data()` returns the
   informational-unsupported dict; nothing propagates out of
   `_run_registered_checks()`.
5. Advisor binary absent (`_probe_version` → `""`) → `advisor_host` result is
   `status="unsupported"`, `severity="informational"`.
6. Independent main-vs-advisor resolution: assert `check_floor` received the
   advisor host/model from config and the main host from `resolve_host().name`,
   not the same runner twice. **This is the first `side_effect=[...]`-style
   dual-host mock in the suite** — introduce it deliberately (or give
   `_advisor_data()` distinct patch targets for the two calls, which is the
   lighter option and avoids ordering coupling).
7. `ll-doctor --json` payload contains an `advisor` key; text mode prints the
   Advisor section (guards the two hand-enumerated output paths, which
   `@register_check` does not cover).
8. Regression: `test_cli_doctor_trim.py::TestExitCodeIsolation::test_trim_findings_do_not_affect_exit_code`
   still passes unmocked (safe by construction via `enabled=False`, but assert
   it rather than assume it).

_Wiring pass added by `/ll:wire-issue`, 2026-08-24:_
- **Concrete regression risk, not just a missing test**: ~27 sites across
  `test_cli_doctor.py` and `test_cli_doctor_full.py` patch
  `little_loops.config.BRConfig` with a bare `MagicMock()` (directly, e.g.
  `:80,101,132,165,191,210,232,251,278,305,763`, or via the `_json_safe_config()`
  helper `:44-54`, or a locally built `mock_config = MagicMock()` at
  `:407-414,444-448,471-475,497-503,526-531`) and never set `.advisor.host`.
  `MagicMock` auto-attributes are truthy, so `mock_config.advisor.host`
  evaluates truthy even though nothing was configured — if `_advisor_data()`
  guards on `if config.advisor.host:` before calling `resolve_host_named`, all
  ~27 unmocked `main_doctor()` call sites (concretely: `test_json_output_flag`
  `:313`, `test_json_short_flag` `:344`, `test_json_version_fallback_to_unknown`
  `:362`, `test_json_unsupported_capability_still_returns_exit_one` `:380`,
  `test_json_output_includes_analytics_capture_and_issues_sections` `:401`,
  `test_analytics_capture_section_all_enabled` `:438`,
  `test_analytics_capture_section_file_events_disabled` `:465`,
  `test_issues_auto_commit_section_enabled` `:491`,
  `test_issues_auto_commit_section_disabled` `:520`, and the 5 tests in
  `TestVersionProbe` `:550-670`) will attempt `resolve_host_named(<MagicMock
  instance>)` unmocked, which raises (no matching registry key), and none of
  these tests has a `pytest.raises` for it. Implementation must guard on
  `isinstance(config.advisor.host, str)` (or equivalent explicit type check),
  not truthiness alone, to stay safe against MagicMock auto-attributes — this
  is a real implementation constraint, not just a test-authoring note.
  [Agent 3 finding]
- New test class: add a `TestAdvisor` class to
  `test_cli_doctor_install_checks.py` (sibling to `TestSchemaDrift` `:227`)
  covering `_advisor_data()` directly — not configured, cross-host advisory,
  same-host violation, same-host ok — the lightest-weight home for items 1-3
  of the Minimum new coverage list above. [Agent 3 finding]

### Codebase Research Findings

_Refine-pass findings, consolidated 2026-08-23. Three near-duplicate blocks
(2026-08-08 empty, 2026-08-10, and two 2026-08-24 passes) were merged; the
repeated "no status-translation convention" and "no `side_effect=[...]`
precedent" findings are now stated once each, and superseded API.md line
numbers (`~9266`, `~9454-9462`) are dropped in favor of the current values._

- **Status-translation gap (single canonical statement)**: no dict-mapping or
  dispatch convention anywhere in the tree translates one closed `Literal`
  status type into another — confirmed by grep across `doctor.py`,
  `advisor.py`, `host_runner.py`, `fsm/schema.py`, `observability/schema.py`,
  `learning_tests/`. `_capability_check_results()` (`doctor.py:98-113`) only
  *looks* like a precedent: it copies `CapabilityEntry.status` straight
  through into `CheckResult.status` unchanged and derives only the separate
  `severity` field via set-membership against `_ADVISORY_CAPABILITIES`
  (`doctor.py:95,110`). `consult()`'s handling (`advisor.py:259-263`) is a
  plain `if`/`elif` chain, a branching-style precedent at best. The mapping is
  net-new work — and is now fully specified in Decision Rules, so the
  implementer is not choosing it under judgment.
- **No `side_effect=[...]` dual-host mocking precedent (single canonical
  statement)**: a suite-wide grep for `side_effect=[` returns exactly one hit,
  `test_issue_manager.py:403`, an unrelated retry-flow mock. Every
  `resolve_host` / `resolve_host_named` patch in the suite uses a single
  `return_value=`. The closest dual-host scenario,
  `test_cli_advise.py::test_advisor_host_env_independent_of_orchestration_host_cli`
  (`:153`), sidesteps the problem by passing `--main-host`/`--main-model` as
  explicit CLI args so `consult()`'s `resolve_host()` fallback never runs —
  only `resolve_host_named` is patched (`:179`). A `_advisor_check` test
  asserting *independent* main + advisor resolution introduces this pattern
  for the first time in the codebase.
- **Files to Modify, current anchors**: `scripts/little_loops/cli/doctor.py` — add an `_advisor_data()`/`_print_advisor_section()`/`@register_check def _advisor_check()` triad (model on `_schema_drift_data`/`_print_schema_drift_section`/`_schema_drift_check`, `doctor.py:398-523`); add one line to the text-mode print sequence in `main_doctor()` (`doctor.py:1201-1213`) and one key to `_print_report`'s JSON dict assembly (`doctor.py:1064-1101`) — `@register_check` alone wires the exit-code path but not either output path.
- **Conventions in Force — dual-host resolution**: `resolve_host_named(name)` (`host_runner.py:2008-2016`) is the codebase's only host-resolution primitive that never reads or mutates ambient `os.environ`/`LL_HOST_CLI`; `consult()` (`advisor.py:256,265`) is the only production caller and the only existing dual-host pattern (ambient `resolve_host()` for main, named `resolve_host_named()` for advisor) — `_advisor_check` would be the second.
- **Tests, current line numbers (2026-08-23 re-check)**: `test_cli_doctor.py` — `test_register_check_appends_and_runs` (`:699`), `test_exit_code_ignores_informational_unsupported` (`:716`), `test_exit_code_flips_on_error_unsupported` (`:726`), `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor` (`:732`). `test_cli_doctor_install_checks.py::TestSchemaDrift` (~`:227`) is the newest `_data()`-level test convention: `monkeypatch.chdir(tmp_path)`, call the bare `_data()` helper directly (no `main_doctor()`, no host mocking), assert on the returned dict's `status`/`severity`/`note` keys — a lighter-weight template than the full `main_doctor()` integration test.
- **Tests — dual-host/floor-status precedent**: `test_advisor.py::TestConsult::test_cross_host_advisory_proceeds` (`:181-201`) and `::test_capability_floor_violation_refuses_consult` (`:164-179`) are the closest existing analogs — both call `consult()` with distinct `main_host`/`main_model` vs `AdvisorConfig(host=..., model=...)` pairs and patch `little_loops.advisor.resolve_host_named` with a single `return_value=`.
- **Doc anchors, current values (2026-08-23)**:
  - `docs/reference/CLI.md:319` already reads "**6** default install-surface
    checks" (Schema Drift included) — bump to **7**, and add `advisor` to the
    `--json` key list (line ~322).
  - `docs/reference/API.md` — `describe_capabilities` is now at line ~9708;
    its `--json` key enumeration is missing both `advisor` and `schema_drift`
    (line ~9718). A `## little_loops.advisor` module-reference section
    **already exists** at line ~10842 (`rank_model` :10865, `check_floor`
    :10873, `consult`/`AdvisorVerdict` :10897/:10902,
    `record_consult`/`should_consult` :10965/:10973) — earlier claims of "zero
    `little_loops.advisor` reference" are stale.
  - `docs/reference/HOST_COMPATIBILITY.md:568` enumerates the default checks
    as "Entry Points, Skills & Commands, Decisions Store, History DB, and FSM
    Loop Validity" — already missing Schema Drift (pre-existing ENH-3242
    drift); add both `Schema Drift` and `Advisor`.
  - All three files' line numbers have drifted repeatedly across refine
    passes; re-grep rather than trusting these anchors if the tree has moved.

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
  - **Decided for this issue**: shape 1 — `_advisor_data()` returns
    `severity` in its dict and `_advisor_check()` reads `data["severity"]`
    with **no** `.get()` default. This matches the two most recently added
    checks (`_schema_drift_check`, `_loop_validity_check`) and makes the
    "never error-tier" guarantee auditable in one place. Do not rely on the
    `CheckResult` dataclass default here — its default is `"error"`, the
    opposite of what this check needs.

### Dependent Files (Callers/Importers)

- `scripts/tests/test_cli_doctor_install_checks.py:7`, `test_cli_doctor_full.py:8`, `test_cli_doctor.py:12` — import `doctor.py`
- `scripts/little_loops/cli/__init__.py:64` — imports `main_doctor`
- Per code-graph query, current callers of `check_floor` and `build_version_check` are test-only (`test_advisor.py`, `test_host_runner.py`) — no production call site exists yet for either.

### Tests (confirmed structure, from `test_cli_doctor.py`)

- `test_register_check_appends_and_runs` (`:699`) — save/clear/restore
  `doctor._CHECKS` via the `doctor` module object (not the imported names
  directly): snapshot `list(doctor._CHECKS)`, `.clear()` inside `try`,
  restore with `.clear()` + `.extend(original)` inside `finally`.
- `test_exit_code_ignores_informational_unsupported` (`:716`) /
  `test_exit_code_flips_on_error_unsupported` (`:726`) — call
  `_exit_code_for()` directly with a hand-built `CheckResult` list, no
  fixture needed.
- `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor`
  (`:732`) — combines the `_CHECKS` save/clear/restore with a
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
   an error) for **every** floor classification — `ok`, `advisory`,
   `unknown`, and `violation`. `ll-doctor`'s exit code is unchanged by any
   advisor finding, including a `violation`.
2. When `config.advisor.enabled` is false or `.host` is unset, `ll-doctor`
   reports a non-failing "advisor not configured" result instead of
   attempting resolution.
3. When the advisor is enabled but neither host can be resolved
   (`HostNotConfigured` from `resolve_host()` or `resolve_host_named()`),
   `ll-doctor` still completes and exits on its other checks' merits — it
   does not propagate the exception out of `_run_registered_checks()`.
4. `ll-doctor --json` includes an `advisor` key in its payload, and text
   mode prints a matching Advisor section — `@register_check` wires only
   the exit-code path, so both output paths need their own line.
5. `docs/reference/CLI.md`, `docs/reference/API.md`, and
   `docs/reference/HOST_COMPATIBILITY.md` are updated in lockstep (see
   Documentation / Wiring Phase).
6. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` all pass.

## Out of Scope (covered by sibling children of FEAT-3044)

- **FEAT-3108** — `check_floor`, `rank_model`, `MODEL_RANKS`; this issue
  only consumes `check_floor`.
- **FEAT-3120** — `consult()`, the `ll-advise` CLI, `/ll:advise` skill.
- **`AdvisorConfig.min_tier`** — the field exists
  (`config/orchestration.py:108-140`) and is plausibly floor-related, but
  `check_floor` does not read it and no consumer does today. This issue
  deliberately does not surface or validate it; wire it in a follow-up if
  it ever gains a consumer.

Also unresolved and deferred (from FEAT-3044, unchanged):

- **Cross-host auth** — a `codex`/`gemini` advisor needs that host
  authenticated. Headless/cron runs may lack interactive auth; this
  issue's reachability check is exactly where that surfaces.

## Implementation Steps

1. All four `depends_on` issues (FEAT-3108, FEAT-3120, FEAT-3043, FEAT-3042) are `done` on `main` as of 2026-08-23 — no further dependency landing is required before starting.
2. Resolve the advisor's own `HostRunner` via `resolve_host_named(config.advisor.host)` (`host_runner.py:2008-2016`) — never mutating `os.environ["LL_HOST_CLI"]` and never calling `apply_host_cli_from_config()`. `_advisor_check` reads `config.advisor.enabled`/`.host`/`.model` (`config/orchestration.py:108-140` via `config/core.py:465-468`); when `enabled` is false or `host` is unset, report a non-failing "advisor not configured" result rather than attempting resolution (mirrors `AdvisorNotConfigured` handling in `consult()`, `advisor.py:251-254`).
3. Reachability reuses `_probe_version(resolve_host_named(config.advisor.host))` (`doctor.py:1040-1061`, `host_runner.py:2008-2016`) — same swallowed-exception tuple `(subprocess.TimeoutExpired, FileNotFoundError, OSError, HostNotConfigured)` as the existing main-host probe.
4. `check_floor(advisor_host, advisor_model, main_host, main_model)` (`advisor.py:91-139`) result maps to `CheckResult` with `severity="informational"` unconditionally (all four `FloorResult.status` values — `ok`/`violation`/`advisory`/`unknown` — must warn, never fail, per AC #1). Source the two `main_*` arguments as `resolve_host().name` / `DEFAULT_LLM_MODEL` (`fsm/schema.py:24`), mirroring `consult()` (`advisor.py:256-257`) — `ll-doctor` has no main-model concept of its own. Emit two results (`advisor_host`, `advisor_floor`) using the status mappings fixed in Decision Rules above; that translation is net-new work with no structural precedent in the tree.
5. Follow the `_schema_drift_data`/`_print_schema_drift_section`/`_schema_drift_check` triad shape (`doctor.py:398-523`) for the new `_advisor_data`/`_print_advisor_section`/`_advisor_check` functions; add the new check to `main_doctor()`'s hand-enumerated text print sequence (`doctor.py:1201-1213`) and `_print_report`'s JSON dict (`doctor.py:1064-1101`) — `@register_check` registration alone does not populate either output path.
6. Add the eight-case minimum coverage enumerated under Integration Map → Tests, modeled on `test_cli_doctor_install_checks.py::TestSchemaDrift` (bare `_data()`-level assertions) and `test_advisor.py::TestConsult::test_cross_host_advisory_proceeds`/`test_capability_floor_violation_refuses_consult` (dual main/advisor host + floor-status assertions). The dual-host mock is new to the suite — introduce it deliberately, not copied from an existing test. Then run `python -m pytest scripts/tests/test_cli_doctor.py scripts/tests/test_cli_doctor_trim.py scripts/tests/test_advisor.py -v`, and the full suite / `ruff` / `mypy` per AC 6.
7. Update the three doc surfaces per AC 5 (CLI.md count + `--json` keys, API.md `describe_capabilities` keys, HOST_COMPATIBILITY.md check enumeration) — re-grep their line numbers rather than trusting this file's anchors.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

> **Correction (2026-08-23).** Three directives in this section were
> written before FEAT-3042/FEAT-3043 landed and before ENH-3242 added the
> Schema Drift check. They are corrected in place below; do not act on the
> pre-correction wording preserved in git history.

- ~~**Blocking dependency check before starting**~~ — **no longer
  applicable.** FEAT-3042 and FEAT-3043 both landed via the epic merge on
  2026-08-23: `AdvisorConfig` exists at `config/orchestration.py:108-140`
  (exposed as `BRConfig.advisor`, `config/core.py:465-468`) and
  `resolve_host_named()` at `host_runner.py:2008-2016`. Every `depends_on`
  ID is `done`; nothing gates the start of this work.
- Update `_print_report()` in `doctor.py` — add an `advisor` key to the
  `--json` payload dict (`doctor.py:1064-1101`) and a matching
  `_print_advisor_section()` call in `main_doctor()`'s fixed section-print
  sequence (`doctor.py:1201-1213`); the exit-code path
  (`_run_registered_checks()` → `_exit_code_for`) does not automatically
  populate the JSON/text output paths.
- Update `docs/reference/CLI.md` (`### ll-doctor`, line ~319) — the count
  there already reads **"6 default install-surface checks"** (Schema Drift
  included), *not* "5" as this note originally said; bump it to **7** and
  add `advisor` to the `--json` key enumeration (line ~322).
- Update `docs/reference/API.md` — add the `advisor` key to the
  `describe_capabilities` / `ll-doctor --json` key enumeration (now at
  line ~9708; the `schema_drift` key is missing there too — fix both while
  in the file). A `## little_loops.advisor` module-reference section
  **already exists** at line ~10842 (documenting `rank_model`,
  `check_floor`, `consult`, `AdvisorVerdict`, `record_consult`,
  `should_consult`) — this note's original "currently absent" claim is
  stale; no new module section is needed.
- Update `docs/reference/HOST_COMPATIBILITY.md` (line ~568) — its default-check
  enumeration ("Entry Points, Skills & Commands, Decisions Store, History
  DB, and FSM Loop Validity") is already missing **Schema Drift**
  (pre-existing drift from ENH-3242, unrelated to this issue). Add both
  `Schema Drift` and `Advisor` while editing that sentence.
- Write a `main_doctor()` integration test establishing the new
  dual-`resolve_host` mock pattern (`side_effect=[...]` or a distinct
  patch target), since no existing test differentiates two independent
  `resolve_host()` calls.
- Verify `test_cli_doctor_trim.py::TestExitCodeIsolation::test_trim_findings_do_not_affect_exit_code`
  still passes unmocked once `_advisor_check` is registered — it must
  degrade gracefully with no advisor host configured, not raise or flip
  the exit code.

_Wiring pass added by `/ll:wire-issue`, 2026-08-24:_
- Update `docs/ARCHITECTURE.md:850` — the `CapabilityReport` table row's
  prose enumeration of `ll-doctor --json`'s install-surface keys is missing
  both `schema_drift` (pre-existing ENH-3242 drift) and `advisor`; add both.
- Update or add a `CHANGELOG.md` entry — the existing unreleased line
  (`:182-183`, "Advisor core. `ll-advise` CLI, a capability floor, and an
  `ll-doctor` check ship together (FEAT-3044)") is inaccurate once this
  check lands separately from FEAT-3044/3120/3108: either add a standalone
  FEAT-3122 line or correct that entry's scope.
- **Implementation must guard the advisor-host check with a type check, not
  truthiness**: `isinstance(config.advisor.host, str)` (or equivalent)
  before calling `resolve_host_named`. ~27 existing tests in
  `test_cli_doctor.py`/`test_cli_doctor_full.py` patch `BRConfig` with a bare
  `MagicMock()` that never sets `.advisor.host`; `MagicMock` auto-attributes
  are truthy, so a plain `if config.advisor.host:` guard would attempt
  `resolve_host_named(<MagicMock>)` unmocked in all of them and raise. See
  Integration Map → Tests for the concrete site list.
- Add a `TestAdvisor` class to `test_cli_doctor_install_checks.py` (sibling
  to `TestSchemaDrift` `:227`) for the bare `_advisor_data()`-level cases —
  the lightest-weight home for the "not configured" / "cross-host advisory"
  / "same-host violation" / "same-host ok" coverage.

## Impact

- **Priority**: P3 — a capability gap, not a defect.
- **Effort**: Small–Medium (`size: Medium`) — one new check triad in an
  existing module composing already-shipped pieces (FEAT-3108, FEAT-3120,
  FEAT-3042, FEAT-3043), plus two hand-enumerated output-path lines, three
  doc updates, and a first-of-kind dual-host test mock.
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
> (its scope now carried by `FEAT-3120`). The pre-re-ID verification history
> that used to follow this note was condensed on 2026-08-23 (see below);
> its BROKEN_REF/DEP_ISSUES findings were historical artifacts of the
> shadow-tree incident, not current defects.

_Condensed history (2026-08-23; full text in git history of this file):_

Two 2026-08-08 `/ll:verify-issues` passes (verdicts BROKEN_REF, then
DEP_ISSUES) plus a corroborating refine-pass research note reasoned about
dependency IDs minted in a shadow issue tree during the FEAT-3110/3111/3112
provenance incident, and recommended repointing `depends_on`. All of it is
superseded: the 2026-08-10 refine pass (see Current Behavior → Codebase
Research Findings) confirmed `depends_on` needs no repointing — FEAT-3042,
FEAT-3043, and FEAT-3120 are real, open, canonical issues, and FEAT-3042 /
FEAT-3043 were subsequently added to this issue's `depends_on` directly.
Still-valid facts carried forward from those passes: `advisor.py` is the
112-line FEAT-3108-only surface; `cli/doctor.py` anchors for `CheckResult`,
`_capability_check_results`, `_exit_code_for`, and `_probe_version` match
current code; no `advisor` references exist in the config modules; CLI.md
still describes "5 default install-surface checks".

_Condensed history (2026-08-23; full text in git history of this file):_

The 2026-08-10 and 2026-08-12 `/ll:verify-issues` passes and the 2026-08-08
`/ll:confidence-check` (Readiness 50/100 → STOP) are **fully superseded** and
were removed to stop them contradicting the current state. Every gap they
raised is resolved: `depends_on` needed no repointing (confirmed 2026-08-10);
FEAT-3042/FEAT-3043/FEAT-3120 all landed on `main` via the 2026-08-23 epic
merge; `advisor.py` is 522 lines with `consult()`/`AdvisorVerdict`;
`resolve_host_named()` exists at `host_runner.py:2008-2016`; `AdvisorConfig`
exists at `config/orchestration.py:108-140`; the fold-vs-`@register_check`
choice was decided (Option B, see Decision Rationale); the
`FloorResult.status` → `CheckResult` mapping is now specified in Decision
Rules. Their `verify_verdict: NON_VALID` and the "re-run `/ll:refine-issue`
to repoint dependencies" recommendation are both obsolete — frontmatter now
reads `VALID`, and the current confidence check (2026-08-23) reads 85/86.
The epic branch those notes reference (`epic/epic-3041-host-agnostic-advisor`)
is ~448 commits stale and slated for retirement: **target `main`.**

- 2026-08-16: Core claim still solid — no `_advisor_check` in `cli/doctor.py`; `depends_on` IDs are all valid and correctly reflect current status. The file body contains multiple stale/superseded Verification Notes blocks about a since-resolved ID-confusion incident (FEAT-3120 provenance mix-up) that now read as contradictory to a reader; flagging for a future pruning/consolidation pass rather than deleting here. Verdict: NEEDS_UPDATE.

### 2026-08-23 (manual staleness pass)

Performed the pruning/consolidation the 2026-08-16 pass requested: the two superseded 2026-08-08 verification blocks and their corroborating research note are condensed into the summary above (full text in git history); the shadow-tree "Dependency-status discrepancy" research note is condensed in place; the two wiring-pass claims that FEAT-3042/FEAT-3043 were "not in this issue's `depends_on`" are corrected (both were added to `depends_on` after those notes were written). `verify_verdict` reset `NON_VALID` → `VALID`: the core claim (no `_advisor_check`; genuinely gated by FEAT-3120 (since done) — FEAT-3042 and FEAT-3043 landed via the epic merge 2026-08-23) was already re-confirmed 2026-08-16 and the NEEDS_UPDATE consolidation is now done. Note: the epic branch this file's confidence-check notes reference (`epic/epic-3041-host-agnostic-advisor`) is ~448 commits behind `main` and slated for retirement — target `main`'s tree state, not that branch's.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-23_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- `stale_symbol_ref` flags `_advisor_check` (claimed in `doctor.py`) since the
  symbol doesn't exist yet — expected for forward-looking implementation work,
  but this caps Criterion 4 (Issue Well-Specified) at 10/20 per the rubric's
  Parity/Claim/Structure cap.
- ~~Proposed Solution leaves the fold-vs-`@register_check` architecture choice
  explicitly open~~ — **resolved 2026-08-23**: Option B (self-resolving
  `@register_check`) is selected with a scoring table; see Decision Rationale.
- The `FloorResult.status` → `CheckResult.status`/`severity` translation and the
  dual-`resolve_host_named` test-mocking pattern are both genuinely new to the
  codebase (no existing precedent to copy verbatim) — first-of-kind work, but
  both are now fully specified in Decision Rules rather than left to judgment.

## Session Log
- `/ll:confidence-check` - 2026-08-24T03:18:13 - `d2cc1ea2-75e9-4d1e-b4a0-3a77ec9f999f.jsonl`
- `/ll:verify-issues` - 2026-08-24T03:11:53 - `d889ca3b-8283-4446-b128-5166bb5b2c8b.jsonl`
- `/ll:wire-issue` - 2026-08-24T03:10:09 - `db62efbd-ccc9-4880-90d1-21e1837ca316.jsonl`
- `/ll:refine-issue` - 2026-08-24T02:48:51 - `9abc72d4-6fec-4dd7-b8b5-0bb4825d634b.jsonl`
- `/ll:refine-issue` - 2026-08-24T02:48:42 - `03ebcc71-7137-47c3-bc7d-18563310dad8.jsonl`
- `/ll:decide-issue` - 2026-08-24T01:18:56 - `7df0ca0e-4499-4040-a086-85c39d5f9acd.jsonl`
- `/ll:refine-issue` - 2026-08-24T01:15:16 - `7df0ca0e-4499-4040-a086-85c39d5f9acd.jsonl`
- `/ll:confidence-check` - 2026-08-24T01:11:19 - `4aa588b6-d571-428b-abc0-116ac8a698f4.jsonl`
- `/ll:reconcile-issue` - 2026-08-24T00:47:50 - `5bab6687-c2bc-4078-8ae9-3de7877b2157.jsonl`
- `/ll:refine-issue` - 2026-08-24T00:26:43 - `5d705364-6b23-4e84-9557-2084c10e8caf.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:24 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-13T22:00:51 - `e21c16b3-391d-4ef2-80c4-decd2dced91f.jsonl`
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
