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

Add an `_advisor_data()` / `_print_advisor_section()` / `@register_check def
_advisor_check()` triad to `cli/doctor.py`: report advisor host reachability
and the capability-floor result, always as warnings that never affect
`ll-doctor`'s exit code. Third and last architecturally separable concern of
FEAT-3044's "ll-doctor check" subsection.

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
issue extends that one-command check to cover the advisor host — reported as a
warning, because an unconfigured or cross-host advisor is a deliberate
configuration, not a broken install.

## Current Behavior

No `_advisor_data`/`_print_advisor_section`/`_advisor_check` symbol exists in
`cli/doctor.py` (confirmed by grep). `ll-doctor` registers 6 default checks
(entry points, skills & commands, decisions store, history DB, schema drift,
FSM loop validity); none of them probes a host CLI for reachability. The only
existing host probe, `_probe_version` (`doctor.py:1040-1061`), receives its
already-resolved `HostRunner` as a parameter from `main_doctor()`
(`doctor.py:1181-1183`) — no check resolves a host itself.

## Expected Behavior

- `ll-doctor` reports advisor host reachability.
- `ll-doctor` warns (never fails) for **all four** `check_floor`
  classifications — `ok`, `advisory`, `unknown`, **and `violation`**. This is a
  deliberate divergence from `consult()`, which *raises*
  `CapabilityFloorViolation` on `violation` because it is about to spend a real
  consult on a weaker model; `ll-doctor` only reports.
- No advisor finding ever affects `ll-doctor`'s overall exit code.
- The advisor check surfaces in **all three** output paths: the exit-code path
  (via `@register_check`), the `--json` payload (`advisor` key), and the
  text-mode section list. The latter two are hand-enumerated and need their own
  line each.

## Proposed Solution

Option B (selected — see Decision Rationale): a self-resolving
`@register_check` triad modeled on `_schema_drift_*` (`doctor.py:398-523`) for
the function shape and on `_entry_points_*` (`doctor.py:185-249`) for the
multi-row data shape. `_advisor_data()` takes no arguments — `register_check()`
types its argument as `Callable[[], list[CheckResult]]` (`doctor.py:81,84`), so
**do not add a `config` parameter**. It sources config itself with a
function-body import, exactly as `main_doctor()` does at `doctor.py:1127,1179`:

```python
from little_loops.config import BRConfig
cfg = BRConfig(Path.cwd())
```

This is a *second* `BRConfig` construction, independent of `main_doctor()`'s
own `cfg` — accepted for self-containment, and it is what makes the ~28
`patch("little_loops.config.BRConfig", ...)` sites reach this function (D3).
It then reads `cfg.advisor.enabled`/`.host`/`.model`, resolves the advisor's
own `HostRunner` via `resolve_host_named()`, and returns two rows.
`severity="informational"` on **every** emitted `CheckResult`, mirroring
`_ADVISORY_CAPABILITIES` (`doctor.py:95,110`) where `informational` means
"reported but never fails the run".

### Decision Rationale

**Selected**: Option B — self-resolving `@register_check`, severity shape 1
(`data["severity"]`, no `.get()` default).

**Option A** (rejected): fold pattern mirroring `_capability_check_results()`
(`doctor.py:98-113`), where `main_doctor()` resolves the runner and calls a
plain unregistered function by hand. That pattern exists only because a check
needs a value available solely inside `main_doctor()`'s body — but the
advisor's own host and config are independently resolvable, so the rationale
doesn't apply. `_capability_check_results()`'s own comment
(`doctor.py:76-80`) states new checks should register against `_CHECKS`.

**Reasoning**: Option B reuses the triad and `data["severity"]` convention
established by the two most recently added checks (`_schema_drift_check`,
`_loop_validity_check`), and reuses `resolve_host_named(config.advisor.host)`
exactly as `advisor.py:consult()` (`:265`) already does. `register_check()`
accepts any no-arg `Callable[[], list[CheckResult]]`, so `_advisor_check`
participates in `_run_registered_checks()`/`_exit_code_for()` with zero
registry changes.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — Fold pattern | 1 | 1 | 1 | 1 | 4/12 |
| B — Self-resolving `@register_check` | 3 | 2 | 3 | 2 | **10/12** |

## Program Design

### Call Path

`ll-doctor` → `_run_registered_checks` → `_advisor_check` → `_advisor_data` →
`check_floor` / `_probe_version(resolve_host_named(...))`

### Decision Rules

**D1 — Data shape: a list of two rows, not a flat dict.** `_advisor_data() ->
list[dict]` returning exactly two rows, each `{"name", "status", "severity",
"note"}`. Model on `_entry_points_data()` (`doctor.py:185-221`) — the only
existing multi-result check — **not** on `_schema_drift_data()`'s single flat
dict, which cannot carry two results. `_advisor_check()` maps one
`CheckResult` per row via `data["severity"]` (no `.get()` default; the
`CheckResult` dataclass default is `"error"`, the opposite of what this check
needs). Row names: `advisor_host` (reachability) and `advisor_floor`
(capability floor), so a consumer can tell "advisor binary missing" from
"advisor model is weaker". The `--json` `advisor` key carries the list
verbatim; `_print_advisor_section()` prints one `_STATUS_SYMBOLS` line per row.
The "not configured" guard returns **both** rows, not one, each with
`status="unsupported"`, `severity="informational"`, and
`note="not configured (optional)"` — the established optional-absent shape
(`_decisions_store_data` `:291-296`, `_history_db_data` `:361-362`). Pin the
status value explicitly: `_STATUS_SYMBOLS` has no "not applicable" member, so
because `advisor.enabled` defaults to `False`, *every* existing install grows
two `✗` rows on its next `ll-doctor`. That matches how the other opt-in
subsystems already render, and the `(optional)` in the note is what carries the
"deliberate, not broken" signal — keep it verbatim.

**D2 — Memoize the *probe*, keyed by host name — not `_advisor_data()`
itself.** Every `_xxx_data()` is invoked twice per `ll-doctor` run: once by the
output path (`_print_report`'s JSON dict `doctor.py:1093`, or
`_print_xxx_section()` `:1208`) and again by its `_xxx_check()` (`:518`). For
every existing default check that is a `Path.exists()` plus a local read; this
is the first default-registered check to pay subprocess cost at all.

*Scale of the cost, stated accurately.* `_probe_version` short-circuits on
`runner.detect()`, which is `shutil.which(...)` (`host_runner.py:350,596`) — so
an advisor host that is **not installed** costs ~0ms and never reaches
`subprocess.run`. The `timeout=10` only bites an installed-but-hung binary. The
real saving is one redundant `--version` subprocess (~100–500ms) on the common
installed path, not the 20s a naive reading suggests. Memoize, but do not
over-engineer around a latency cliff that only exists for a wedged binary.

*Shape.* Cache a **keyed** helper, e.g.
`@lru_cache def _probe_advisor_version(host: str) -> str` wrapping
`_probe_version(resolve_host_named(host))`. Do **not** put `@lru_cache` on the
no-arg `_advisor_data()`: it would be keyed on nothing while its result depends
on `Path.cwd()` and on whichever `BRConfig` patch is active, so it leaks across
every test that `monkeypatch.chdir(tmp_path)` and across the ~28 patched-config
sites — a cross-test-pollution bug, not a cache.

*Invalidation is part of this rule.* An `lru_cache` is process-global and
pytest runs many cases per process. Ship an autouse fixture in the doctor test
modules that calls `_probe_advisor_version.cache_clear()` before each test, and
pin it (test 7a below).

**D3 — Type-check the config guard, do not test truthiness.** Guard with
`isinstance(cfg.advisor.host, str)` **and** `cfg.advisor.enabled is True`
before any resolution — identity, not truthiness, on `enabled` too. `enabled`
is declared `bool = False` (`config/orchestration.py`), so `is True` is exact
for real config and closes the same MagicMock hole the `isinstance` closes;
a bare `if cfg.advisor.enabled` leaves half the guard open. ~28 sites in
`test_cli_doctor.py` /
`test_cli_doctor_full.py` patch `little_loops.config.BRConfig` with a bare
`MagicMock()` and never set `.advisor` — MagicMock auto-attributes are truthy,
so **both** `config.advisor.enabled` and `config.advisor.host` evaluate truthy
there. A plain `if not enabled or not host:` guard would fall through and call
`resolve_host_named(<MagicMock>)` unmocked in all of them, raising
`HostNotConfigured` in tests that have no `pytest.raises`. This is an
implementation constraint, not a test-authoring note.

**D4 — Main host/model source: resolve explicitly from config, do not inherit
ambient env.** `ll-doctor` has no notion of a "main model", so take
`main_model = DEFAULT_LLM_MODEL` (`fsm/schema.py:24`, currently `"sonnet"`)
exactly as `consult()` does (`advisor.py:256-257`), importing it inside the
function body.

For `main_host`, **diverge from `consult()`'s bare `resolve_host()`**:

```python
main_host = (
    resolve_host_named(cfg.orchestration.host_cli)
    if isinstance(cfg.orchestration.host_cli, str)
    else resolve_host()
).name
```

- *Why not the bare `resolve_host()`.* `main_doctor()` calls
  `apply_host_cli_from_config(cfg)` (`doctor.py:1180`, definition
  `host_runner.py:2250`) — which mutates `os.environ["LL_HOST_CLI"]` — *before*
  `resolve_host()`. Inside `main_doctor()`, a bare `resolve_host()` inherits
  that mutation; called standalone (the `_data()`-level tests below) it falls
  through to `resolve_host()`'s PATH probe (`host_runner.py:1985-2004`) and can
  resolve a **different** main host, so the floor result would differ between
  test and production. Reading `cfg.orchestration.host_cli` (`str | None`,
  `config/orchestration.py:90`) *removes* that divergence instead of pinning a
  known-divergent behavior with a test, and keeps `_advisor_data()`
  self-contained and deterministic — consistent with D5's isolation rule, which
  already forbids reading or mutating ambient `LL_HOST_CLI` for the advisor
  side. The `resolve_host()` fallback covers the unset case only.
- This is a deliberate, documented divergence from `consult()`. Do not
  "fix" it back to a bare `resolve_host()` for symmetry.
- Consequence to expect: with stock config (`advisor.model="opus"`,
  `advisor.host="claude-code"`, main `claude-code`/`sonnet`) `check_floor`
  returns `"ok"`. The floor check is near-vacuous until someone configures a
  cross-host advisor or a weaker advisor model — correct behavior, not a broken
  mapping.

**D5 — Advisor host resolution must stay isolated.** Use
`resolve_host_named(config.advisor.host)` (`host_runner.py:2008-2016`, which
calls `resolve_host({"LL_HOST_CLI": name})` — an explicit one-key env dict, so
ambient env is never read or mutated). Never call
`apply_host_cli_from_config()`, never mutate `LL_HOST_CLI`, never reach into
`_HOST_RUNNER_REGISTRY`. Consistent with FEAT-3120's isolation requirement for
`consult()`.

**D6 — Catch `HostNotConfigured` inside `_advisor_data()`.** Both
`resolve_host()` (`host_runner.py:1960-2005`) and `resolve_host_named()`
(`:2008-2016`) raise it, and `_run_registered_checks()` (`doctor.py:116-121`)
has no `try`/`except` — an uncaught raise takes down all of `ll-doctor`.
`_probe_version` swallows it, but only *after* it already holds a runner, so it
is not a safety net for either resolution call. Wrap both; on failure return
the two-row informational-unsupported shape.

**D7 — Status mapping (net-new; no structural precedent in the tree).**
- Reachability: `_probe_version(...)` non-empty → `status="full"`; empty →
  `status="unsupported"` (still `severity="informational"`, so the exit code is
  unaffected — `_exit_code_for` `doctor.py:124-127` requires `severity ==
  "error" AND status == "unsupported"` together).
- Floor: `FloorResult.status == "ok"` → `status="full"`; `"advisory"` /
  `"unknown"` / `"violation"` → `status="partial"`. `FloorResult.detail`
  carries straight through into `note`.
- **Also carry the raw `FloorResult.status` as a `floor_status` key** on the
  `advisor_floor` row and in the JSON payload. The three-way collapse into
  `"partial"` otherwise discards the only signal this check produces — a
  consumer could not distinguish "advisor is weaker than main" from "cross-host,
  ranks incomparable" without regexing prose.
- **Both rows carry the key; the `advisor_host` row sets it to `None`.** A
  heterogeneous row schema (key present on one row, absent on the other) forces
  every JSON consumer into `.get()` guards and breaks the
  `list[dict[str, str]]` annotation `_entry_points_data()` uses
  (`doctor.py:185`). Annotate `_advisor_data() -> list[dict[str, Any]]` and
  emit all four keys plus `floor_status` on **both** rows, `None` on
  `advisor_host` and in the "not configured" / `HostNotConfigured` guards.

**D8 — `rank_model` normalizes model aliases** through `resolve_model_alias()`
(`advisor.py:81-88`), so `"opus"` and `"claude-opus-5"` rank identically. Tests
must not assume raw-string comparison of model names.

### Signatures

_Line numbers verified against `main` 2026-08-23. Anchors have drifted
repeatedly across refine passes — re-grep rather than trusting them._

- `check_floor(advisor_host, advisor_model, main_host, main_model) -> FloorResult` — `advisor.py:91-139`. Classification order: cross-host → `"advisory"` (before any rank lookup); same host + either model unrankable → `"unknown"`; same host + `advisor_rank < main_rank` → `"violation"`; else `"ok"`.
- `FloorResult` (frozen dataclass, `advisor.py:67`): `status: Literal["ok", "violation", "advisory", "unknown"]`, `detail: str`
- `rank_model(host, model) -> int | None` — `advisor.py:81-88`; `MODEL_RANKS` (`advisor.py:23-36`) is populated only for `"claude-code"` (haiku=1, sonnet=2, opus=3, fable=4); every other host maps every model to `None`
- `resolve_host_named(name: str) -> HostRunner` — `host_runner.py:2008-2016`; `resolve_host(env: dict | None = None) -> HostRunner` — `host_runner.py:1960-2005`. **Both raise `HostNotConfigured`**; see D6.
- `apply_host_cli_from_config(config) -> None` — `host_runner.py:2250`; see D4.
- `DEFAULT_LLM_MODEL: str = "sonnet"` — `fsm/schema.py:24`
- `AdvisorConfig` — `config/orchestration.py:109-140`, reachable as `BRConfig(...).advisor` (`config/core.py:465-468`). Fields used: `enabled: bool = False`, `host: str | None = None`, `model: str = "opus"`. No new config surface is required.
- `CheckResult` (`doctor.py:54-73`): `status: Literal["full", "partial", "unsupported"]`, `severity: Literal["error", "informational"] = "error"` — a **different closed `Literal`** from `FloorResult.status`; the two share no member names, hence D7's translation.
- `_probe_version(runner: HostRunner) -> str` (`doctor.py:1040-1061`) — checks `runner.detect()`, then `subprocess.run([...], capture_output=True, text=True, timeout=10)`, swallowing `TimeoutExpired`/`FileNotFoundError`/`OSError`/`HostNotConfigured` to `""`. Reusable verbatim as `_probe_version(resolve_host_named(advisor_host))`.
- `_exit_code_for(results) -> int` (`doctor.py:124-127`): `any(r.severity == "error" and r.status == "unsupported")`.

### Conventions in Force

- The triad is the established shape for every default-registered check:
  a pure `_xxx_data()` (never touches `CheckResult`), a `_print_xxx_section()`,
  and an `@register_check def _xxx_check()`. Confirmed on `_schema_drift_*`
  (`doctor.py:398-523`), `_loop_validity_*` (`:526-606`), `_entry_points_*`
  (`:185-249`).
- Every "prerequisite absent → informational, non-failing" guard in `doctor.py`
  shares one shape: an early return of `{"status": "unsupported", "severity":
  "informational", "note": "<short reason>"}` from a cheap existence check
  before any I/O — `_decisions_store_data` (`:291-296`), `_history_db_data`
  (`:361-362`), `_schema_drift_data` (`:425-426`), `_loop_validity_data`
  (`:549-556`). The unconfigured-advisor guard follows it, per-row (D1).
- `consult()` (`advisor.py:256,265`) is the only existing dual-host pattern
  (ambient `resolve_host()` for main, named `resolve_host_named()` for advisor)
  and the only production caller of `resolve_host_named`. `_advisor_data` is
  the second.
- No dict-mapping or dispatch convention translating one closed `Literal`
  status into another exists anywhere in the tree (grepped `doctor.py`,
  `advisor.py`, `host_runner.py`, `fsm/schema.py`, `observability/schema.py`,
  `learning_tests/`). `_capability_check_results()` only *looks* like one — it
  copies `status` through unchanged and derives only `severity` by set
  membership. D7 is net-new work, now fully specified.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/doctor.py` — add the `_advisor_data()` /
  `_print_advisor_section()` / `@register_check def _advisor_check()` triad;
  add one `_print_advisor_section()` line to `main_doctor()`'s text print
  sequence (`doctor.py:1201-1213`) and one `"advisor"` key to `_print_report`'s
  JSON dict (`doctor.py:1064-1101`). `@register_check` wires the exit-code path
  only — neither output path is derived from `_CHECKS`.

### Documentation

All five surfaces below are gated by AC5.

- `docs/reference/CLI.md:319` — reads "6 default install-surface checks"; bump
  to **7** and add the Advisor check to the enumeration. Add `advisor` to the
  `--json` key list (`:322`).
- `docs/reference/API.md` — `describe_capabilities` (~`:9708`) duplicates the
  `--json` key enumeration in prose and must stay in lockstep with CLI.md; it
  is missing both `advisor` and `schema_drift`. A `## little_loops.advisor`
  module-reference section **already exists** (~`:10842`) — no new section
  needed.
- `docs/reference/HOST_COMPATIBILITY.md:568` — default-check enumeration reads
  "Entry Points, Skills & Commands, Decisions Store, History DB, and FSM Loop
  Validity"; add both `Schema Drift` and `Advisor`. Also note that cross-host
  capability floors are **advisory, not enforced**.
- `docs/ARCHITECTURE.md:850` — the `CapabilityReport` row enumerates
  `ll-doctor --json`'s install-surface keys (`entry_points`, `skills_commands`,
  `decisions_store`, `history_db`, `loop_validity`); add `schema_drift` and
  `advisor`.
- `CHANGELOG.md:181-182` — **two separate edits; the entry is *released*, not
  unreleased.** The "**Advisor core.** `ll-advise` CLI, a capability floor, and
  an `ll-doctor` check ship together (FEAT-3044)" text sits inside
  `## [1.156.0] - 2026-08-16`, a shipped section. So:
  1. Narrow the 1.156.0 entry — drop "and an `ll-doctor` check" — it over-claims
     something that did not ship in 1.156.0. Do not fold FEAT-3122 into it
     retroactively.
  2. Add a standalone FEAT-3122 line under the **current in-progress version
     section** (`## [1.157.0] - 2026-08-23` or its successor, whichever is open
     at implementation time). Per project convention, do **not** route it
     through an `[Unreleased]` heading.

> **Pre-existing drift, not this issue's regression.** CLI.md is current, but
> HOST_COMPATIBILITY.md:568, ARCHITECTURE.md:850, and API.md's
> `describe_capabilities` are **all** missing `schema_drift` from ENH-3242,
> independent of this work. Fixing them here is opportunistic; don't read the
> diff as a FEAT-3122 side effect.

### Configuration

**None.** `AdvisorConfig` already exists (`config/orchestration.py:109-140`,
`BRConfig.advisor` at `config/core.py:465-468`) with an `advisor` block in
`config-schema.json`. This check reads `enabled`/`host`/`model` and adds no
fields. `min_tier` is explicitly out of scope.

### Tests

**Home**: add a `TestAdvisor` class to
`scripts/tests/test_cli_doctor_install_checks.py`, sibling to `TestSchemaDrift`
(`:227`) — the lightest-weight convention: `monkeypatch.chdir(tmp_path)`, call
the bare `_advisor_data()` directly (no `main_doctor()`), assert on the
returned rows.

> **The "no mocking" part of that convention only covers the guard cases.**
> `test_cli_doctor_install_checks.py` currently has **zero**
> `patch("little_loops.config.BRConfig", ...)` sites, because every check there
> reads the filesystem, not config. Cases 1, 2, and 8 below genuinely need no
> mocks — a real `BRConfig` on an empty `tmp_path` has `advisor.enabled=False`
> and trips the guard. Cases 3, 5, and 6 need **both** a `BRConfig` patch (to
> set `enabled`/`host`/`model`) **and** `resolve_host` / `resolve_host_named` /
> `_probe_advisor_version` patches. Introduce that patching into this module
> deliberately; don't assume the sibling classes model it.

Exit-code and output-path cases belong in
`test_cli_doctor.py` near `test_exit_code_ignores_informational_unsupported`
(`:716`), using the `_CHECKS` save/clear/restore isolation from
`test_register_check_appends_and_runs` (`:699`).

**Minimum new coverage** — one test per specified behavior, so the
first-of-kind decisions are pinned rather than re-derived later:

1. `advisor.enabled=False` → **two** rows present, both
   `severity="informational"`, note names "not configured"; assert the
   `resolve_host*` mocks were never called.
2. `advisor.enabled=True`, `host` unset → same two-row non-failing shape.
3. Floor `violation` → `severity="informational"`, `status="partial"`,
   `floor_status="violation"`, and `_exit_code_for([...])` still returns `0`.
   This is the AC1 divergence from `consult()` and the single most important
   regression guard here.
4. `HostNotConfigured` raised from `resolve_host()` **and** from
   `resolve_host_named()` (two cases) → two informational-unsupported rows;
   nothing propagates out of `_run_registered_checks()`.
5. Advisor binary absent (`_probe_version` → `""`) → `advisor_host` row is
   `status="unsupported"`, `severity="informational"`.
6. Independent main-vs-advisor resolution: assert `check_floor` received the
   advisor host/model from `cfg.advisor` and the main host from
   `cfg.orchestration.host_cli` (D4), not the same runner twice. Include one
   case with `orchestration.host_cli=None` exercising the `resolve_host()`
   fallback. **First `side_effect=[...]`-style dual-host mock
   in the suite** — a suite-wide grep for `side_effect=[` returns exactly one
   unrelated hit (`test_issue_manager.py:403`); every `resolve_host` /
   `resolve_host_named` patch uses a single `return_value=`. Prefer giving
   `_advisor_data()` distinct patch targets for the two calls (lighter, avoids
   ordering coupling) over `side_effect=[...]`.
7. **D2 memoization**: one `main_doctor()` run performs exactly **one**
   advisor-host probe (assert call count on the wrapped `_probe_version`), as
   two separate cases — text mode and `--json` mode — since the two output
   paths reach `_advisor_data()` differently.
7a. **D2 invalidation**: the autouse `_probe_advisor_version.cache_clear()`
   fixture is present and effective — two tests in the same module with
   *different* advisor hosts each get their own probe result, not the first
   one's cached value. Without this the memoization silently poisons the suite.
8. **D3 guard**: `_advisor_data()` with a bare `MagicMock()` config attempts no
   host resolution — directly pins the ~27-site regression risk.
9. `ll-doctor --json` payload contains an `advisor` key holding two rows; text
   mode prints the Advisor section. Guards the two hand-enumerated output paths
   that `@register_check` does not cover.
10. Regression: `test_cli_doctor_trim.py::TestExitCodeIsolation::test_trim_findings_do_not_affect_exit_code`
    (`:257-266`) still passes unmocked. It calls real `main_doctor()` with no
    `resolve_host` mock; safe by construction via `enabled=False`, but assert
    it rather than assume it.

**Do not** wire `_advisor_check` into `_run_full_checks`/`_FULL_CHECKS` —
`test_cli_doctor_full.py::TestFullSection::test_run_full_checks_returns_check_result_per_verifier`
(`:275-294`) asserts an exact name-set for that family.

### Dependent Files (Callers/Importers)

- `scripts/tests/test_cli_doctor_install_checks.py:7`, `test_cli_doctor_full.py:8`, `test_cli_doctor.py:12` — import `doctor.py`
- `scripts/little_loops/cli/__init__.py:64` — imports `main_doctor`

## Acceptance Criteria

1. `ll-doctor` reports advisor host reachability and emits a warning (not an
   error) for **every** floor classification — `ok`, `advisory`, `unknown`, and
   `violation`. The exit code is unchanged by any advisor finding, including a
   `violation`.
2. When `cfg.advisor.enabled is not True` or `.host` is not a `str`,
   `ll-doctor` reports a non-failing `status="unsupported"`,
   `severity="informational"`, `note="not configured (optional)"` result for
   **both** rows instead of attempting resolution (see D3 — both halves of the
   guard are identity/type checks, not truthiness tests).
3. When the advisor is enabled but neither host can be resolved
   (`HostNotConfigured` from `resolve_host()` or `resolve_host_named()`),
   `ll-doctor` still completes and exits on its other checks' merits — the
   exception does not propagate out of `_run_registered_checks()`.
4. `ll-doctor --json` includes an `advisor` key carrying both rows, and text
   mode prints a matching Advisor section — `@register_check` wires only the
   exit-code path, so both output paths need their own line.
5. All five doc surfaces updated in lockstep: `docs/reference/CLI.md`,
   `docs/reference/API.md`, `docs/reference/HOST_COMPATIBILITY.md`,
   `docs/ARCHITECTURE.md`, and `CHANGELOG.md` (see Documentation).
6. A single `main_doctor()` run probes the advisor host at most once — in
   **both** text and `--json` mode — via a host-keyed memoized probe helper,
   not an `@lru_cache` on `_advisor_data()` itself, and the doctor test modules
   carry an autouse `cache_clear()` fixture so the cache cannot leak across
   tests (D2).
7. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` all pass.

## Out of Scope (covered by sibling children of FEAT-3044)

- **FEAT-3108** — `check_floor`, `rank_model`, `MODEL_RANKS`; this issue only
  consumes `check_floor`.
- **FEAT-3120** — `consult()`, the `ll-advise` CLI, `/ll:advise` skill.
- **`AdvisorConfig.min_tier`** — the field exists but `check_floor` does not
  read it and no consumer does today. Wire it in a follow-up if it ever gains
  one.
- **Cross-host auth** (deferred from FEAT-3044) — a `codex`/`gemini` advisor
  needs that host authenticated; headless/cron runs may lack interactive auth.
  This issue's reachability check is exactly where that surfaces.

## Implementation Steps

1. No dependency gating: FEAT-3108, FEAT-3120, FEAT-3043, FEAT-3042 are all
   `done` on `main` as of 2026-08-23. Target `main`, **not** the
   `epic/epic-3041-host-agnostic-advisor` branch (~448 commits stale, slated
   for retirement).
2. Write `_advisor_data() -> list[dict[str, Any]]` per D1 — no-arg, sourcing
   its own `BRConfig(Path.cwd())` via a function-body import: guard first (D3),
   then main host/model from `cfg.orchestration.host_cli` (D4), `check_floor`
   (D7, including `floor_status` on both rows), advisor probe (D5), all wrapped
   per D6.
2a. Add the host-keyed `@lru_cache def _probe_advisor_version(host: str) -> str`
   helper per D2, and the autouse `cache_clear()` fixture in the doctor test
   modules alongside it.
3. Write `_print_advisor_section()` (one `_STATUS_SYMBOLS` line per row) and
   `@register_check def _advisor_check()` (one `CheckResult` per row, severity
   from `data["severity"]` with no default).
4. Add the `_print_advisor_section()` call to `main_doctor()`'s print sequence
   (`doctor.py:1201-1213`) and the `"advisor"` key to `_print_report`'s JSON
   dict (`doctor.py:1064-1101`).
5. Add the eleven-case coverage above. The dual-host mock and the
   `FloorResult`→`CheckResult` translation are both new to the codebase —
   introduce them deliberately, not copied.
6. Update the five doc surfaces per AC5; re-grep their line numbers rather than
   trusting this file's anchors.
7. Run `python -m pytest scripts/tests/test_cli_doctor.py
   scripts/tests/test_cli_doctor_install_checks.py
   scripts/tests/test_cli_doctor_trim.py scripts/tests/test_advisor.py -v`,
   then the full suite / `ruff` / `mypy` per AC7.

## Impact

- **Priority**: P3 — a capability gap, not a defect.
- **Effort**: Small–Medium (`size: Medium`) — one check triad composing
  already-shipped pieces, two hand-enumerated output-path lines, five doc
  updates, and a first-of-kind dual-host test mock.
- **Risk**: Low — informational-only, cannot regress `ll-doctor`'s exit code by
  construction (`_exit_code_for`'s existing rule). The one non-obvious risk is
  latency (D2) and the MagicMock guard (D3), both now specified.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/reference/HOST_COMPATIBILITY.md#orchestration-cli` — host abstraction.

## Status

**Open** | Created: 2026-08-08 | Priority: P3

## Verification Notes

> **Provenance note — 2026-08-08.** Authored as `FEAT-3110` inside a
> non-worktree sandbox whose stray `.ll/` shadowed the project root, so its IDs
> were minted against a shadow issue tree. Salvaged and re-IDed to `FEAT-3122`;
> siblings `FEAT-3111`/`FEAT-3112` became `FEAT-3120`/`FEAT-3121`, and the
> redundant `FEAT-3109` layer collapsed into `FEAT-3044`. All BROKEN_REF /
> DEP_ISSUES verdicts from 2026-08-08 through 2026-08-12 were artifacts of that
> incident and are superseded — `depends_on` needs no repointing (confirmed
> 2026-08-10), and every ID in it is `done` (confirmed 2026-08-23). Full
> verification history in this file's git log.

**2026-08-23 (manual staleness pass)**: condensed the superseded verification
blocks and corrected the wiring-pass claims that FEAT-3042/FEAT-3043 were
absent from `depends_on`. `verify_verdict` reset `NON_VALID` → `VALID`.

**2026-08-23 (pre-implementation review)**: full re-verification against `main`.
Design confirmed sound; six defects fixed in place — (1) `_advisor_data()`'s
return shape was unspecified and contradictory (two `CheckResult`s vs
`_schema_drift_data`'s single flat dict) → now D1, modeled on
`_entry_points_data`; (2) the twice-per-run `_xxx_data()` invocation would have
run the subprocess probe twice, adding up to 20s → now D2; (3) `resolve_host`
was cited at the stale `host_runner.py:1574-1619` (actual `:1960-2005`) and
`apply_host_cli_from_config` at `:1622-1647` (actual `:2250`) → corrected; (4)
the `apply_host_cli_from_config` ordering divergence between production and
`_data()`-level tests was unrecorded → now D4; (5) the three-way floor collapse
into `"partial"` discarded the check's only signal → `floor_status` added in
D7; (6) AC5 omitted `docs/ARCHITECTURE.md` and `CHANGELOG.md` → both added.
File condensed 823 → ~330 lines; superseded research archaeology dropped (git
history retains it).

**2026-08-23 (second pre-implementation review)**: re-verified against `main`;
design still sound, no structural change. Nine defects fixed in place — (1)
`_advisor_data()`'s config source was never stated (it must self-construct
`BRConfig(Path.cwd())`; a `config` param would break `register_check`'s no-arg
contract) → now spelled out in Proposed Solution; (2) D2 prescribed an
unkeyed cache on a no-arg, cwd-dependent function, which would leak across
`monkeypatch.chdir` and the ~28 patched-config tests → now a host-keyed
`_probe_advisor_version` helper; (3) D2 had no invalidation contract for a
process-global `lru_cache` → autouse `cache_clear()` fixture added, pinned by
new test 7a; (4) D2's "up to 20s" was factually wrong — `_probe_version`
short-circuits on `runner.detect()` = `shutil.which` (`host_runner.py:350`), so
a missing binary costs ~0ms and the 10s timeout only bites a hung one → wording
corrected so the fix isn't over-engineered; (5) D4 left a live either/or
decision despite `decision_needed: false` → resolved to explicit
`cfg.orchestration.host_cli` resolution, which removes the production-vs-test
divergence instead of pinning it; (6) `CHANGELOG.md:182` was described as an
*unreleased* entry but sits inside the shipped `## [1.156.0]` section → split
into two edits (narrow 1.156.0's over-claim; add FEAT-3122 to the open version
section); (7) the test home said "no host mocking" while prescribing three
cases that require both config and host mocks, in a module with zero existing
`BRConfig` patches → split explicitly; (8) the "not configured" guard never
pinned a `status` value → `"unsupported"` + `note="not configured (optional)"`,
with the two-`✗`-rows-on-every-install consequence stated; (9) `floor_status`
made the two row dicts heterogeneous → now present on both rows, `None` on
`advisor_host`, with the annotation widened to `dict[str, Any]`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-23_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns

- `stale_symbol_ref` flags `_advisor_check` since the symbol doesn't exist yet
  — expected for forward-looking work, but caps Criterion 4 at 10/20.
- The `FloorResult.status` → `CheckResult` translation and the dual-host test
  mock are genuinely new to the codebase (no precedent to copy verbatim), but
  both are now fully specified in Decision Rules rather than left to judgment.

## Session Log
- `/ll:confidence-check` - 2026-08-24T03:31:44 - `092141f3-2c2e-43df-bd96-552d482c1a40.jsonl`
- `/ll:confidence-check` - 2026-08-24T03:18:13 - `d2cc1ea2-75e9-4d1e-b4a0-3a77ec9f999f.jsonl`
- `/ll:verify-issues` - 2026-08-24T03:11:53 - `d889ca3b-8283-4446-b128-5166bb5b2c8b.jsonl`
- `/ll:wire-issue` - 2026-08-24T03:10:09 - `db62efbd-ccc9-4880-90d1-21e1837ca316.jsonl`
- `/ll:refine-issue` - 2026-08-24T02:48:51 - `9abc72d4-6fec-4dd7-b8b5-0bb4825d634b.jsonl`
- `/ll:decide-issue` - 2026-08-24T01:18:56 - `7df0ca0e-4499-4040-a086-85c39d5f9acd.jsonl`
- `/ll:confidence-check` - 2026-08-24T01:11:19 - `4aa588b6-d571-428b-abc0-116ac8a698f4.jsonl`
- `/ll:reconcile-issue` - 2026-08-24T00:47:50 - `5bab6687-c2bc-4078-8ae9-3de7877b2157.jsonl`
- `/ll:refine-issue` - 2026-08-24T00:26:43 - `5d705364-6b23-4e84-9557-2084c10e8caf.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:24 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-13T22:00:51 - `e21c16b3-391d-4ef2-80c4-decd2dced91f.jsonl`
- `/ll:reconcile-issue` - 2026-08-10T18:26:44 - `7405995b-78ac-4bf8-8825-45f100c3421d.jsonl`
- `/ll:refine-issue` - 2026-08-10T16:35:42 - `8f3abfd3-6623-4955-b89f-579e5adefbdd.jsonl`
- `/ll:confidence-check` - 2026-08-08T21:00:42 - `33a02969-b861-45a0-9dfa-bda36f49c2f3.jsonl`
- `/ll:wire-issue` - 2026-08-08T20:43:18 - `64c1d4cd-50b9-4634-8852-3b74b00359df.jsonl`
- `/ll:refine-issue` - 2026-08-08T20:37:10 - `a92555e8-6e42-42da-bbde-dbd82186b3b1.jsonl`
- `/ll:issue-size-review` - 2026-08-08T17:51:40 - `45d84ae4-d7b1-4342-a5e2-fb2f78de65a2.jsonl`
