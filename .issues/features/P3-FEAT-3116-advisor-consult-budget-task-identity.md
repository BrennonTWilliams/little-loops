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
- `cli/advise.py`'s manual `ll-advise` path reuses `should_consult` so
  manually-triggered consults are budget-counted too.

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
- `consult_for_trigger(trigger: str, *, question: str, context: str) ->
  AdvisorVerdict | None` — calls `little_loops.advisor.consult()` with the
  trigger as the signal; a failed or timed-out consult logs and returns
  `None` rather than raising (the fail-soft contract this issue's callers
  depend on).
- `AdvisorConfig.max_consults_per_task: int = 3` in `config/orchestration.py`;
  add to `config-schema.json`; wire into `BRConfig.to_dict()`
  (`config/core.py:784-801`, hand-rolled per block — no generic serializer,
  tracked separately under BUG-3012) and a `core.py:367-369`-style
  `config.advisor` property; add `AdvisorConfig` to
  `config/__init__.py` imports/`__all__`.
- `cli/advise.py` — call `should_consult` before the manual consult so the
  budget counter is shared between manual and auto-triggered paths.

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
6. A failed or timed-out consult inside `consult_for_trigger` returns `None`
   and logs a warning rather than raising (the general fail-soft contract
   FEAT-3038 AC #7 depends on; per-caller "primary path completes normally"
   is verified in FEAT-3117/FEAT-3118).
7. `ll-advise`'s manual consult path is budget-counted via `should_consult`.
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

## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-13T22:00:51 - `e21c16b3-391d-4ef2-80c4-decd2dced91f.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:08:32 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:51:42 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:issue-size-review` - 2026-08-08T21:18:49 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`):

- **consult() call-site contract (vs FEAT-3120, FEAT-3039)**: AC #5 asserts no
  code path other than `consult_for_trigger` calls
  `little_loops.advisor.consult()` directly, but FEAT-3120's `ll-advise` CLI
  (`main_advise -> consult`) and FEAT-3039's `advisor_consult` evaluator
  (`evaluate_advisor_consult -> should_consult -> little_loops.advisor.consult`)
  both call `consult()` directly. Settle one contract before implementation:
  either route all consult call sites (the manual `ll-advise` path with signal
  `user_requested`, the FSM evaluator with its state-derived signal) through
  `consult_for_trigger`, or qualify AC #5's exclusivity assertion to
  auto-trigger call sites only, naming the exempted paths.
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
