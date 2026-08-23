---
id: FEAT-3116
title: Advisor consult budget and task-identity infrastructure
type: FEAT
parent: FEAT-3038
priority: P3
status: open
testable: true
discovered_date: 2026-08-08
depends_on:
- FEAT-3120
- FEAT-3043
labels:
- planning-hub
verify_verdict: VALID
---

# FEAT-3116: Advisor consult budget and task-identity infrastructure

## Summary

Child 1 of 3 decomposed from FEAT-3038 (Advisor signal-gated auto-consults and
per-task budget). Ships the shared infrastructure both trigger wiring points
(`confidence_gate` in FEAT-3117, `pre_done` in FEAT-3118) depend on: task
identity resolution, the per-task consult budget/counter, the `should_consult`
gating predicate, and the `consult_for_trigger` wrapper that enforces an
explicit signal on every consult.

## Parent Issue

Decomposed from FEAT-3038: Advisor signal-gated auto-consults and per-task
budget. See that issue for the full design rationale, `Program Design`, and
codebase research findings — this child implements the "Task identity (the
prerequisite)" subsection of its Proposed Solution plus the shared half of
"Trigger dispatch" (the `should_consult` predicate and the signal-enforcing
`consult_for_trigger` wrapper, decoupled from either call site).

## Current Behavior

`scripts/little_loops/advisor.py` (FEAT-3108, commit `9dbe5943`) has
`MODEL_RANKS`, `FloorResult`, `rank_model()`, `check_floor()` only. There is no
task-identity resolver, no consult budget/counter, and no gating predicate.
`AdvisorConfig` (landing separately in FEAT-3043) will not yet have a
`max_consults_per_task` field.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

`consult()` (`scripts/little_loops/advisor.py:183`) today: `consult(question: str, signal: str, context: str = "", config: BRConfig | None = None, main_host: str | None = None, main_model: str | None = None) -> AdvisorVerdict`. `signal` is required with no default (`test_advisor.py` asserts `TypeError` when omitted). It defaults `config` to `BRConfig(Path.cwd())`, raises `AdvisorNotConfigured` if `config.advisor.host` is falsy, raises `CapabilityFloorViolation` on a same-host rank violation from `check_floor()`, and otherwise performs a live host consult unconditionally — no call counting, no task-identity resolution, and no gating predicate exist anywhere in this function or file today. Confirmed absent repo-wide (grep, zero matches): `TaskKey`, `ConsultBudget`, `resolve_task_key`, `record_consult`, `should_consult`, `consult_for_trigger`.

## Expected Behavior

- `resolve_task_key()` resolves a stable `TaskKey` with precedence: issue ID
  (when running under `ll-auto`/`ll-sprint`/`ll-parallel`) → loop run ID (under
  `ll-loop`) → session ID (otherwise).
- `record_consult(task_key)` persists and increments a per-task counter that
  stays correct across a subprocess boundary (a consult from a child runner
  increments the same task's count).
- `should_consult(trigger, config)` returns `False` when `advisor.enabled` is
  `False`, when `trigger` is not in `advisor.triggers`, or when the budget for
  the resolved task key is exhausted (logging the reason in the exhausted
  case); otherwise `True`.
- `consult_for_trigger(trigger, *, question, context)` is the single place
  that calls `little_loops.advisor.consult()` — no other call site does, so no
  consult can happen without an explicit signal.
- `AdvisorConfig.max_consults_per_task` (default 3) exists in
  `config/orchestration.py`, `config-schema.json`, and is round-tripped by
  `BRConfig.to_dict()`.
- `cli/advise.py`'s manual `ll-advise` path is **retargeted onto
  `consult_for_trigger`** (it lands in FEAT-3120 calling `consult()`
  directly, before this issue exists — migrating it is in this issue's
  scope). Manual consults pass the user-supplied `--signal` as the trigger
  and are budget-counted; they bypass only the `advisor.triggers` allowlist
  check (an explicit user request is not an auto-trigger), via
  `enforce_trigger_allowlist=False`.

## Proposed Solution

Implement in `scripts/little_loops/advisor.py`:

- `TaskKey: {kind: Literal["issue", "loop_run", "session"], value: str}`
- `ConsultBudget: {max_per_task: int, spent: int, task_key: TaskKey}`
- `resolve_task_key(env: dict[str, str] | None = None) -> TaskKey` — mirrors
  the precedence-resolver shape of `host_runner.py:resolve_host()`
  (`:1574-1619`): injectable `env` dict defaulting to `os.environ`, one
  docstring-documented fallback tier per source. Sources: issue ID via
  `_resolve_issue_id()` (`cli/issues/show.py:40-120`) / `IssueInfo.issue_id`;
  ll-loop `instance_id` (`cli/loop/_helpers.py:1505-1507`) with counter file
  under `${context.run_dir}` (precedent: `usage.jsonl`/`ab.json` at
  `cli/loop/_helpers.py:1892-1923`); ll-auto/ll-sprint/ll-parallel `run_id`
  (`issue_manager.py:1580`, `parallel/orchestrator.py:123`) with counter
  persisted via `.ll/.auto-manage-state.json`
  (`config.automation.state_file`, `config/core.py:510`); session ID via
  `get_current_session_id()` (`session_log.py:141-155`) otherwise.
- `record_consult(task_key: TaskKey) -> int` — returns the new count. No
  existing counter-persistence idiom in the codebase is demonstrated
  multi-writer-safe (see FEAT-3038's codebase research on the four disagreeing
  idioms); pick one explicitly and document the choice, since AC #5 requires
  correctness across a subprocess boundary specifically, not general
  concurrent-writer safety.
- `should_consult(trigger: str, config: BRConfig) -> bool` — the two-level
  enabled-then-allowlist shape has two precedents to follow:
  `hooks/learning_tests_gate.py:gate()` (`:91-101`) and
  `hooks/__init__.py:_hooks_telemetry_enabled()` (`:83-108`, fail-soft:
  "any config-read failure disables telemetry rather than raising").
  `should_consult` must be fail-soft the same way.
- `consult_for_trigger(trigger: str, *, question: str, context: str,
  enforce_trigger_allowlist: bool = True) -> AdvisorVerdict | None` — calls
  `little_loops.advisor.consult()` with the trigger as the signal; a failed
  or timed-out consult logs and returns `None` rather than raising (the
  fail-soft contract this issue's callers depend on).
  `enforce_trigger_allowlist=False` (the manual `ll-advise` path only)
  skips the `trigger in advisor.triggers` membership check while keeping
  the `advisor.enabled` and budget checks — a user-requested consult must
  not be blocked by the auto-trigger allowlist, but still spends budget.
- `AdvisorConfig.max_consults_per_task: int = 3` in `config/orchestration.py`;
  add to `config-schema.json`; wire into `BRConfig.to_dict()`
  (`config/core.py:784-801`, hand-rolled per block — no generic serializer,
  tracked separately under BUG-3012) and a `core.py:367-369`-style
  `config.advisor` property; add `AdvisorConfig` to
  `config/__init__.py` imports/`__all__`.
- `cli/advise.py` — retarget `main_advise`'s consult call from `consult()`
  (how FEAT-3120 ships it) onto
  `consult_for_trigger(args.signal, ..., enforce_trigger_allowlist=False)`,
  so the budget counter is shared between manual and auto-triggered paths
  and the AC #5 exclusivity assertion holds tree-wide.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

Anchor staleness check (line numbers below have drifted from current code; the cited functions/classes themselves are still present and correct unless noted):
- `host_runner.py:1574-1619` (`resolve_host`) → actual `host_runner.py:1960-2005`.
- `cli/loop/_helpers.py` instance_id at `~1505-1507` → actual `_make_instance_id()` at `:1543`.
- `cli/loop/_helpers.py` usage.jsonl/ab.json counter precedent at `~1892-1923` → actual `:1934-1956`.
- `issue_manager.py:1580` (cited for ll-auto/ll-sprint `run_id`) → actual `run_id or uuid4().hex` is at `AutoManager.__init__` `:1652`; `:1580` is an unrelated `_stamped_result` return.
- `config/core.py:784-801` (cited for `BRConfig.to_dict()`) → `to_dict()` itself starts at `:724`; the `advisor` block specifically is at `:879`.
- `config/core.py` advisor property cited at `:367-369` → actual `:466` (`:367-369` is the `parallel` property).

Confirmed accurate as cited: `hooks/learning_tests_gate.py:gate()` (`:91-101`, off by ~1 line from actual `:90-100`), `hooks/__init__.py:_hooks_telemetry_enabled()` (`:83-108`, exact), `parallel/orchestrator.py:123` (exact), `session_log.py:get_current_session_id()` (cited `:141-155`, actual `:192-206`, shape unchanged).

## Acceptance Criteria

1. `resolve_task_key` prefers issue ID, then loop run ID, then session ID
   (FEAT-3038 AC #6).
2. `max_consults_per_task` is enforced: the Nth+1 consult for the same task
   key is skipped with a logged reason, not attempted (FEAT-3038 AC #4).
3. The counter is correct across a subprocess boundary — a consult from a
   child runner increments the same task's count (FEAT-3038 AC #5).
4. `should_consult` returns `False` when `advisor.enabled: false`, and when
   the given trigger is absent from `advisor.triggers` (the general predicate
   behavior underlying FEAT-3038 AC #3; the two trigger-specific integration
   cases are verified in FEAT-3117/FEAT-3118).
5. No code path other than `consult_for_trigger` calls
   `little_loops.advisor.consult()` directly (asserted) (FEAT-3038 AC #8).
   This includes `cli/advise.py`, whose FEAT-3120-era direct `consult()`
   call is retargeted by this issue; future call sites (FEAT-3039's
   evaluator) route through `consult_for_trigger` from the start.
6. A failed or timed-out consult inside `consult_for_trigger` returns `None`
   and logs a warning rather than raising (the general fail-soft contract
   FEAT-3038 AC #7 depends on; per-caller "primary path completes normally"
   is verified in FEAT-3117/FEAT-3118).
7. `ll-advise`'s manual consult path routes through `consult_for_trigger`
   with `enforce_trigger_allowlist=False`: it is budget-counted and
   respects `advisor.enabled`, but is not blocked by the trigger allowlist
   (a `--signal` value absent from `advisor.triggers` still consults).
8. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Tests

- `scripts/tests/test_advisor.py` — `resolve_task_key` precedence (one test
  per tier, `isolated_env`-style fixture per `test_host_runner.py`'s
  `resolve_host` tests); `should_consult` false when disabled / trigger
  unlisted / budget exhausted; `record_consult` counter correctness across a
  simulated subprocess boundary; `consult_for_trigger` fail-soft on a mocked
  `consult()` failure/timeout; a static assertion that `consult()` is called
  only from `consult_for_trigger`.
- `scripts/tests/test_config.py` — `AdvisorConfig.max_consults_per_task`
  three-case shape per `TestClusterConfig`/`TestOrchestrationConfig`
  (`:3382-3473`): `from_dict({})` defaults, `from_dict({all fields})`
  overrides, `from_dict({one field})` partial override re-asserting every
  other field still defaults.
- `scripts/tests/test_config_schema.py` — `advisor.max_consults_per_task`
  round-trips through `test_to_dict_emits_every_schema_section` /
  `test_to_dict_emits_no_key_absent_from_schema`.

## Documentation

- `docs/reference/API.md` — `resolve_task_key`, `should_consult`,
  `consult_for_trigger`, `record_consult`.
- `docs/reference/CONFIGURATION.md` — `advisor.max_consults_per_task`.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/advisor.py` — add `TaskKey`, `ConsultBudget`, `resolve_task_key()`, `record_consult()`, `should_consult()`, `consult_for_trigger()`. Confirmed today it has only `MODEL_RANKS` (:43), `FloorResult` (:60), `rank_model()` (:74), `check_floor()` (:84), `AdvisorVerdict` (:155), `consult()` (:183) — none of this issue's new symbols exist yet.
- `scripts/little_loops/config/orchestration.py` — add `max_consults_per_task: int = 3` to `AdvisorConfig` (:109) and its `from_dict()` (:128).
- `scripts/little_loops/config/core.py` — `to_dict()`'s `advisor` block (:879) needs the new key; `self._advisor = AdvisorConfig.from_dict(...)` construction is at `:335`; the `config.advisor` property is at `:466`.
- `scripts/little_loops/config-schema.json` — `advisor` object schema (`:1767-1801`) needs a `max_consults_per_task` property.
- `scripts/little_loops/cli/advise.py` — inside `cmd_invoke()` (`:24`), retarget the direct `consult(...)` call at `:40` onto `consult_for_trigger(args.signal, ..., enforce_trigger_allowlist=False)`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/advise.py:40` — `cmd_invoke()` calls `consult()` directly today; this is the call site AC #5/#7 require retargeting.
- `scripts/tests/test_advisor.py:128,147,162,184,202,225,241` — `TestConsult` calls `consult()` directly across 7 sites.
- `scripts/little_loops/config/__init__.py:83,93` — imports and re-exports `AdvisorConfig`.

### Conventions in Force
- Precedence resolvers take an injectable `env: dict[str, str] | None = None` defaulting to `dict(os.environ)`, one fallback tier per source — evidence: `resolve_host()` (`scripts/little_loops/host_runner.py:1960-2005`).
- Enabled-flag-then-finer-grained-check gating, checked in that order before any work happens — evidence: `hooks/learning_tests_gate.py:gate()` (`:90-100`, master `enabled` flag then `discoverability.mode`).
- Config/telemetry helper functions fail soft: any read failure is caught and treated as "disabled" rather than raised — evidence: `hooks/__init__.py:_hooks_telemetry_enabled()` (`:83-108`).
- Per-run counters/artifacts are written as small files directly under `${context.run_dir}` — evidence: `cli/loop/_helpers.py:1934-1956` (`usage.jsonl`, `ab.json`).
- Run-scoped identifiers use `run_id or uuid4().hex` — evidence: `issue_manager.py:1652` (`AutoManager.__init__`) and `parallel/orchestrator.py:123` (`Orchestrator.__init__`), identical in both.

### Tests
- `scripts/tests/test_advisor.py` — has `TestModelRanks`, `TestRankModel`, `TestCheckFloor`, `TestConsult` (`:113`, 7 call sites of `consult()`: `:128,147,162,184,202,225,241`); no `TestResolveTaskKey`/`TestShouldConsult`/`TestRecordConsult`/`TestConsultForTrigger` classes yet.
- `scripts/tests/test_config.py` — `TestAdvisorConfig` (`:3745`) covers `from_dict({})`/override/`BRConfig.advisor`; no `max_consults_per_task` case yet. `TestClusterConfig` (`:3570`)/`TestOrchestrationConfig` (`:3594`) are the three-case shape this issue's Tests section already cites.
- `scripts/tests/test_config_schema.py` — has `test_advisor_host_enum_matches_orchestration_host_cli` (`:872-887`) and an `advisor.host`/`advisor.min_tier` schema-key list (`:1200-1201`); no `advisor.max_consults_per_task` entry yet.

### Documentation
- `docs/reference/API.md` — `## little_loops.advisor` (`:10841`) documents `consult()`/`AdvisorVerdict`/`FloorResult`/`check_floor`; no `resolve_task_key`/`should_consult`/`consult_for_trigger`/`record_consult` entries yet.
- `docs/reference/CONFIGURATION.md` — `### \`advisor\`` (`:1401`) field table (`:1411-1416`) has no `max_consults_per_task` row yet.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

**Types**
- `TaskKey: {kind: Literal["issue", "loop_run", "session"], value: str}`
- `ConsultBudget: {max_per_task: int, spent: int, task_key: TaskKey}`
- Confirmed absent from `scripts/little_loops/advisor.py` today (repo-wide grep, zero matches): `TaskKey`, `ConsultBudget`, `resolve_task_key`, `record_consult`, `should_consult`, `consult_for_trigger`.

### Signatures
- `resolve_task_key(env: dict[str, str] | None = None) -> TaskKey` — mirrors `resolve_host(env: dict[str, str] | None = None) -> HostRunner` (`scripts/little_loops/host_runner.py:1960-2005`; `env` defaults to `dict(os.environ)`, one fallback tier per source: explicit override → probe → raise).
- `record_consult(task_key: TaskKey) -> int` — returns the new count.
- `should_consult(trigger: str, config: BRConfig) -> bool`.
- `consult_for_trigger(trigger: str, *, question: str, context: str, enforce_trigger_allowlist: bool = True) -> AdvisorVerdict | None`.
- `consult(question: str, signal: str, context: str = "", config: BRConfig | None = None, main_host: str | None = None, main_model: str | None = None) -> AdvisorVerdict` (`scripts/little_loops/advisor.py:183`) — the existing target `consult_for_trigger` wraps. `signal` has no default (`test_advisor.py` asserts `TypeError` when omitted, e.g. `test_missing_signal_raises_typeerror` around line 236) — `consult_for_trigger` must keep supplying `signal=trigger` on every call.
- `AdvisorConfig.max_consults_per_task: int = 3` — new field on the dataclass at `scripts/little_loops/config/orchestration.py:109` (current fields: `enabled`, `host`, `model`, `min_tier`, `timeout_seconds`, `triggers`); wire into `from_dict()` (`:128`), `BRConfig._advisor` construction (`config/core.py:335`), the `config.advisor` property (`config/core.py:466` — not `:367-369`, which is the `parallel` property), and `to_dict()`'s `advisor` block (`config/core.py:879`).

### Call Path
`scripts/little_loops/cli/advise.py:cmd_invoke` (`:24`, current `consult()` call at `:40`) → `consult_for_trigger(args.signal, question=args.question, context=context, enforce_trigger_allowlist=False)` → `should_consult(trigger, config)` → `consult(question=..., signal=trigger, context=..., config=..., main_host=..., main_model=...)` (`scripts/little_loops/advisor.py:183`).

### Decision Rules
- `should_consult` returns `False` when `config.advisor.enabled` is `False` (master switch, mirroring `hooks/learning_tests_gate.py:gate()` :90-96's `if not lt_config.enabled: return ...`), or when `trigger not in config.advisor.triggers` — except when invoked via `consult_for_trigger(..., enforce_trigger_allowlist=False)` (the manual `ll-advise` path), which skips only the triggers-membership check while keeping the `enabled` and budget checks.
- `should_consult` returns `False` when the resolved task key's `record_consult` count has already reached `config.advisor.max_consults_per_task` (default 3), logging the reason.
- `should_consult` is fail-soft: any config-read failure inside it is caught and treated as "do not consult" rather than raised — mirrors `hooks/__init__.py:_hooks_telemetry_enabled()` (`:83-108`, whole body wrapped in `try/except Exception: return False`).
- `consult_for_trigger` catches a failed or timed-out `consult()` call, logs a warning, and returns `None` rather than raising or propagating.

## Impact

- **Priority**: P3 — matches parent FEAT-3038.
- **Effort**: Medium — the budget/task-identity work is the bulk of the
  parent issue's stated complexity.
- **Risk**: Low on its own — this child ships infrastructure with no live
  call sites until FEAT-3117/FEAT-3118 wire them in.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1 (pair LLM judgment with a
  non-LLM signal).

## Status

**Open** | Created: 2026-08-08 | Priority: P3


## Verification Notes

### 2026-08-12 (`/ll:verify-issues`)

Removed `FEAT-3044` from `depends_on`: FEAT-3044 was decomposed into FEAT-3108/3120/3121/3122 on 2026-08-10, and this issue already separately lists its successor `FEAT-3120` in the same field — keeping both was redundant. `depends_on` now reads `[FEAT-3120, FEAT-3043]`.

### 2026-08-23 (consult() exclusivity contract settled)

The open call-site-contract conflict (this issue's AC #5 vs FEAT-3120's and FEAT-3039's direct `consult()` call paths) is settled: **`consult_for_trigger` is the sole caller of `consult()` from the moment this issue lands.** FEAT-3120 (landing first) ships `main_advise -> consult()`; retargeting it onto `consult_for_trigger(..., enforce_trigger_allowlist=False)` is added to this issue's scope; FEAT-3039 routes through `consult_for_trigger` from the start. Manual-path semantics: budget-counted and `advisor.enabled`-gated, but exempt from the `advisor.triggers` allowlist (an explicit `--signal` from the user is not an auto-trigger). `consult_for_trigger` gains the `enforce_trigger_allowlist: bool = True` parameter to express this. Scope Boundary notes here and in FEAT-3120/FEAT-3039 updated to match.

## Session Log
- `/ll:refine-issue` - 2026-08-23T21:44:07 - `f1b87a61-ab8b-49e0-a903-dea5edc06efd.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-13T22:00:51 - `e21c16b3-391d-4ef2-80c4-decd2dced91f.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:08:32 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:51:42 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:issue-size-review` - 2026-08-08T21:18:49 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`):

- **consult() call-site contract (vs FEAT-3120, FEAT-3039)** — **SETTLED
  2026-08-23**: all consult call sites route through `consult_for_trigger`;
  AC #5's exclusivity assertion stands unqualified. Landing-order
  accommodation: FEAT-3120 lands before this issue and ships
  `main_advise -> consult()` directly; retargeting that call onto
  `consult_for_trigger(args.signal, ..., enforce_trigger_allowlist=False)`
  is in **this issue's scope** (see Proposed Solution), so the static
  assertion holds tree-wide from the moment this issue lands. FEAT-3039's
  evaluator (which lands after this issue) routes through
  `consult_for_trigger` with its state-derived signal from the start —
  its Call Path has been updated to match.
- **Telemetry skip instrumentation (vs FEAT-3040)**: FEAT-3040 AC #1 requires
  `advisor_consults` rows for budget-skipped consults, but budget skips
  short-circuit in `should_consult`/`consult_for_trigger` here — they never
  reach `consult()`, which is FEAT-3040's write point. FEAT-3040 must
  instrument this skip surface; coordinate the skip-recording API when
  implementing either issue.
- **Counter storage migration (vs FEAT-3040)**: the counter-persistence
  mechanism chosen here (AC #3 subprocess-boundary correctness) should be
  migratable to a history.db-derived count — FEAT-3040 proposes collapsing the
  two counters into the `advisor_consults` table as one source of truth.
