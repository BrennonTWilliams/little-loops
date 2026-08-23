---
id: FEAT-3116
title: Advisor consult budget and task-identity infrastructure
type: FEAT
parent: FEAT-3038
priority: P3
status: done
testable: true
discovered_date: 2026-08-08
completed_at: '2026-08-23T22:49:46Z'
depends_on:
- FEAT-3120
- FEAT-3043
labels:
- planning-hub
verify_verdict: VALID
confidence_score: 98
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 24
score_ambiguity: 19
score_change_surface: 22
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

`scripts/little_loops/advisor.py` has `MODEL_RANKS`, `FloorResult`,
`rank_model()`, `check_floor()` (FEAT-3108) and `consult()`/`AdvisorVerdict`
(FEAT-3120, done). There is no task-identity resolver, no consult
budget/counter, and no gating predicate. `AdvisorConfig` (FEAT-3043, done)
has `enabled`, `host`, `model`, `min_tier`, `timeout_seconds`, `triggers` —
no `max_consults_per_task` field. Both `depends_on` entries are done; this
issue is unblocked.

No environment variable carries the current issue ID, orchestrator run ID, or
loop run ID into spawned host sessions today (repo-wide grep of `"LL_*"`
literals: `LL_HOST_CLI`, `LL_AUTOMATION`, `LL_NON_INTERACTIVE`,
`LL_HOOK_HOST`, `LL_STATE_DIR`, ... — nothing task-identifying). The values
the resolver needs (`AutoManager.run_id`, the current issue's `IssueInfo`,
ll-loop's `instance_id`) exist only in-process in the parent orchestrator.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

`consult()` (`scripts/little_loops/advisor.py:183`) today: `consult(question: str, signal: str, context: str = "", config: BRConfig | None = None, main_host: str | None = None, main_model: str | None = None) -> AdvisorVerdict`. `signal` is required with no default (`test_advisor.py` asserts `TypeError` when omitted). It defaults `config` to `BRConfig(Path.cwd())`, raises `AdvisorNotConfigured` if `config.advisor.host` is falsy, raises `CapabilityFloorViolation` on a same-host rank violation from `check_floor()`, and otherwise performs a live host consult unconditionally — no call counting, no task-identity resolution, and no gating predicate exist anywhere in this function or file today. Confirmed absent repo-wide (grep, zero matches): `TaskKey`, `ConsultBudget`, `resolve_task_key`, `record_consult`, `should_consult`, `consult_for_trigger`.

## Expected Behavior

- `resolve_task_key()` resolves a stable `TaskKey` with precedence: issue ID
  (when running under `ll-auto`/`ll-sprint`/`ll-parallel`) → loop run ID (under
  `ll-loop`) → session ID (otherwise). Identity reaches child processes via
  an explicit env contract (see Proposed Solution: `LL_ISSUE_ID`,
  `LL_LOOP_RUN_ID`) that the orchestrators export when spawning host
  sessions; without the export, the resolver degrades to the session tier.
- `record_consult(task_key)` persists and increments a per-task counter that
  stays correct across a subprocess boundary (a consult from a child runner
  increments the same task's count).
- `should_consult(trigger, config, *, task_key=None)` returns `False` when
  `advisor.enabled` is `False`, when `trigger` is not in `advisor.triggers`,
  or when the budget for the task key is exhausted (logging the reason in
  the exhausted case); otherwise `True`.
- `consult_for_trigger(trigger, *, question, context, ...)` is the single
  place that calls `little_loops.advisor.consult()` — no other call site
  does, so no consult can happen without an explicit signal. It returns a
  `ConsultOutcome` (verdict or a typed skip/failure reason), never raises,
  and never returns bare `None` — callers and telemetry (FEAT-3300) can
  distinguish "budget exhausted" from "host not on PATH".
- `AdvisorConfig.max_consults_per_task` (default 3) exists in
  `config/orchestration.py`, `config-schema.json`, and is round-tripped by
  `BRConfig.to_dict()`.
- `cli/advise.py`'s manual `ll-advise` path is **retargeted onto
  `consult_for_trigger`** (it lands in FEAT-3120 calling `consult()`
  directly, before this issue exists — migrating it is in this issue's
  scope). Manual consults pass the user-supplied `--signal` as the trigger
  and are budget-counted; they bypass the `advisor.enabled` master switch
  **and** the `advisor.triggers` allowlist (both gate *auto*-consults; an
  explicit user request is neither), via `manual=True`. `ll-advise` therefore
  keeps working on a fresh install where `enabled` defaults to `False`
  (`ll-init` already grants `Bash(ll-advise:*)`, `init/writers.py:89`), and
  the existing CLI.md `:197` sentence stays true.

## Use Case

An `ll-loop` FSM state calls `should_consult("confidence_gate", config)` on its
third pass through the same run. The advisor has already been consulted twice
for this loop run (`LL_LOOP_RUN_ID` resolves the task key), so
`max_consults_per_task` (3) has one slot left; the check returns `True`, the
gated caller (FEAT-3117, wired separately) proceeds to call
`consult_for_trigger`, and the budget file at
`.ll/advisor-budget/loop_run-<id>.json` increments to 3. A fourth attempt in
the same run returns `False` and logs "budget exhausted" instead of spawning
another host session — bounding advisor spend per task without the caller
needing to track counts itself.

## Proposed Solution

Implement in `scripts/little_loops/advisor.py`:

- `TaskKey: {kind: Literal["issue", "loop_run", "session"], value: str}`
- `ConsultBudget: {max_per_task: int, spent: int, task_key: TaskKey}`
- `ConsultOutcome: {verdict: AdvisorVerdict | None, skipped_reason:
  Literal["disabled", "trigger_not_allowed", "budget_exhausted",
  "not_configured", "floor_violation", "failed", "timeout"] | None,
  error: str | None, task_key: TaskKey}` — frozen dataclass; exactly one of
  `verdict`/`skipped_reason` is set. The reason vocabulary is chosen to map
  1:1 onto FEAT-3300's `AdvisorConsultRow.outcome` enum so the telemetry
  writer can consume it without translation.
- **Task-identity env contract** (new — nothing carries these today):
  - `LL_ISSUE_ID` — exported by ll-auto (`AutoManager`, `issue_manager.py`),
    ll-sprint, and ll-parallel (`parallel/worker_pool.py`) for each host
    session they spawn, set to the issue being processed. Go through
    `project_child_env(extra=...)` / `HostInvocation.env`
    (`host_runner.py:1838`) — the single task-path spawn chokepoint.
  - `LL_LOOP_RUN_ID` — exported by ll-loop (`cli/loop/_helpers.py`, where
    `LL_HOST_CLI` is already added via `extra=`) set to `instance_id`
    (`_make_instance_id()`, `:1543`).
  - Session tier reads `CLAUDE_SESSION_ID` from the injected `env` (not
    `os.environ`) and only then falls back to
    `get_current_session_id()` (`session_log.py:192-206`, most-recently-
    modified JSONL — best-effort and nondeterministic; document as such).
- `resolve_task_key(env: dict[str, str] | None = None) -> TaskKey` — mirrors
  the precedence-resolver shape of `host_runner.py:resolve_host()`
  (`:1960-2005`): injectable `env` dict defaulting to `dict(os.environ)`,
  one docstring-documented tier per source: `LL_ISSUE_ID` → `LL_LOOP_RUN_ID`
  → session ID. Pure env lookup — it does **not** call `_resolve_issue_id()`
  or read orchestrator state; those values only reach it via the env
  contract above.
- `record_consult(task_key: TaskKey) -> int` — returns the new count.
  **Single store, decided:** one JSON file per key at
  `.ll/advisor-budget/<kind>-<value>.json` (`{"spent": N}`), read-modify-
  write under `file_utils.acquire_lock()` + `atomic_write_json()`
  (`file_utils.py:87,35`) — the only multi-writer-safe idiom in the repo.
  Not `${context.run_dir}` and not `.auto-manage-state.json`
  (`StateManager` is a fixed `ProcessingState` dataclass with no counter
  API). Gitignored under `.ll/`. Migrates to a `SELECT COUNT(*)` over
  FEAT-3300's `advisor_consults` table once that lands.
- **Reserve-before-consult:** `consult_for_trigger` calls `record_consult`
  *before* the host call, so a timed-out or failed consult still spends
  budget — otherwise a hung advisor (`timeout_seconds=180`) is retried
  unboundedly.
- `should_consult(trigger: str, config: BRConfig, *, task_key: TaskKey |
  None = None, manual: bool = False) -> bool` — resolves `task_key` via
  `resolve_task_key()` when not supplied (callers pass it so the check and
  `record_consult` use one resolution; tests pass it to avoid patching).
  The two-level enabled-then-allowlist shape has two precedents to follow:
  `hooks/learning_tests_gate.py:gate()` (`:90-100`) and
  `hooks/__init__.py:_hooks_telemetry_enabled()` (`:83-108`, fail-soft:
  "any config-read failure disables telemetry rather than raising").
  `should_consult` must be fail-soft the same way.
- `consult_for_trigger(trigger: str, *, question: str, context: str = "",
  config: BRConfig | None = None, main_host: str | None = None,
  main_model: str | None = None, manual: bool = False) -> ConsultOutcome` —
  calls `little_loops.advisor.consult()` with the trigger as the signal,
  passing `config`/`main_host`/`main_model` through unchanged (required:
  `cmd_invoke` mutates `config.advisor.host/model` from `--host`/`--model`
  and passes `--main-host`/`--main-model`; without these pass-throughs the
  retarget breaks four CLI flags). Never raises: `AdvisorNotConfigured`,
  `CapabilityFloorViolation`, `HostNotConfigured`, and `BlockingJsonError`
  (timeout vs other distinguished via its detail) each map to a
  `skipped_reason` with `error=str(exc)`, logged at warning level.
  `manual=True` (the `ll-advise` path only) skips the `advisor.enabled` and
  `trigger in advisor.triggers` checks while keeping the budget check — a
  user-requested consult is not an auto-consult, but still spends budget.
- `AdvisorConfig.max_consults_per_task: int = 3` in `config/orchestration.py`;
  add to `config-schema.json`; wire into `BRConfig.to_dict()`
  (`config/core.py:784-801`, hand-rolled per block — no generic serializer,
  tracked separately under BUG-3012) and a `core.py:367-369`-style
  `config.advisor` property; add `AdvisorConfig` to
  `config/__init__.py` imports/`__all__`.
- `cli/advise.py` — retarget `main_advise`'s consult call from `consult()`
  (how FEAT-3120 ships it) onto `consult_for_trigger(args.signal,
  question=..., context=..., config=config, main_host=args.main_host,
  main_model=args.main_model, manual=True)`, so the budget counter is shared
  between manual and auto-triggered paths and the AC #5 exclusivity
  assertion holds tree-wide. `cmd_invoke` maps `outcome.skipped_reason` to
  the existing per-reason error messages and exit `2`, replacing its four
  `except` clauses; `budget_exhausted` is a new exit-`2` case in the CLI.md
  exit-codes table. Intended and acknowledged: an explicit `ll-advise` can
  be refused because auto-consults already spent the task's budget — the
  budget is per task, not per path.

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

1. `resolve_task_key` prefers `LL_ISSUE_ID`, then `LL_LOOP_RUN_ID`, then
   session ID (FEAT-3038 AC #6); ll-auto, ll-sprint, ll-parallel export
   `LL_ISSUE_ID` and ll-loop exports `LL_LOOP_RUN_ID` into every spawned
   host session via `project_child_env`/`HostInvocation.env` (asserted on
   the built invocation, not a live spawn).
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
6. A failed or timed-out consult inside `consult_for_trigger` returns a
   `ConsultOutcome` with `verdict=None` and a typed `skipped_reason`
   (`failed`/`timeout`/`not_configured`/`floor_violation`) and logs a
   warning rather than raising (the general fail-soft contract FEAT-3038
   AC #7 depends on; per-caller "primary path completes normally" is
   verified in FEAT-3117/FEAT-3118). Budget is spent before the host call.
7. `ll-advise`'s manual consult path routes through `consult_for_trigger`
   with `manual=True`: it is budget-counted but is blocked by neither
   `advisor.enabled: false` nor the trigger allowlist (a `--signal` value
   absent from `advisor.triggers` still consults; a fresh install with the
   default `enabled: false` still consults). `ll-advise` keeps its existing
   per-reason error messages and exit `2`, adding a `budget_exhausted` case.
8. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Tests

- `scripts/tests/test_advisor.py` — `resolve_task_key` precedence (one test
  per tier, `isolated_env`-style fixture per `test_host_runner.py`'s
  `resolve_host` tests, hermetic — no `os.environ` reads); `should_consult`
  false when disabled / trigger unlisted / budget exhausted, and `manual=True`
  ignoring the first two; `record_consult` counter correctness across a real
  subprocess boundary (`subprocess.run([sys.executable, "-c", ...])`
  incrementing the same `tmp_path` store, `.ll/advisor-budget/` rooted via a
  patched project root); `consult_for_trigger` returning each
  `skipped_reason` on a mocked `consult()` raising each exception class, and
  pass-through of `config`/`main_host`/`main_model`; reserve-before-consult
  (count increments even when `consult()` raises); a static assertion that
  `consult()` is called only from `consult_for_trigger`.
- `scripts/tests/test_issue_manager.py`, `test_worker_pool.py`,
  `test_loop_helpers.py` (or nearest existing spawn tests) — the built
  `HostInvocation.env`/`project_child_env` result carries `LL_ISSUE_ID` /
  `LL_LOOP_RUN_ID` with the expected value.
- `scripts/tests/test_config.py` — `AdvisorConfig.max_consults_per_task`
  three-case shape per `TestClusterConfig`/`TestOrchestrationConfig`
  (`:3382-3473`): `from_dict({})` defaults, `from_dict({all fields})`
  overrides, `from_dict({one field})` partial override re-asserting every
  other field still defaults.
- `scripts/tests/test_config_schema.py` — `advisor.max_consults_per_task`
  round-trips through `test_to_dict_emits_every_schema_section` /
  `test_to_dict_emits_no_key_absent_from_schema`.

## Documentation

- `docs/reference/API.md` — `TaskKey`, `ConsultBudget`, `ConsultOutcome`,
  `resolve_task_key`, `should_consult`, `consult_for_trigger`,
  `record_consult`, and the `LL_ISSUE_ID`/`LL_LOOP_RUN_ID` env contract.
- `docs/reference/CONFIGURATION.md` — `advisor.max_consults_per_task`.
- `docs/reference/CLI.md` — `ll-advise` exit-codes table gains
  `budget_exhausted`; the `:197` `advisor.enabled` sentence stays as-is
  (manual path bypasses `enabled`) — extend it to mention the budget.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/advisor.py` — add `TaskKey`, `ConsultBudget`, `resolve_task_key()`, `record_consult()`, `should_consult()`, `consult_for_trigger()`. Confirmed today it has only `MODEL_RANKS` (:43), `FloorResult` (:60), `rank_model()` (:74), `check_floor()` (:84), `AdvisorVerdict` (:155), `consult()` (:183) — none of this issue's new symbols exist yet.
- `scripts/little_loops/config/orchestration.py` — add `max_consults_per_task: int = 3` to `AdvisorConfig` (:109) and its `from_dict()` (:128).
- `scripts/little_loops/config/core.py` — `to_dict()`'s `advisor` block (:879) needs the new key; `self._advisor = AdvisorConfig.from_dict(...)` construction is at `:335`; the `config.advisor` property is at `:466`.
- `scripts/little_loops/config-schema.json` — `advisor` object schema (`:1767-1801`) needs a `max_consults_per_task` property.
- `scripts/little_loops/cli/advise.py` — inside `cmd_invoke()` (`:24`), retarget the direct `consult(...)` call at `:40` onto `consult_for_trigger(args.signal, ..., manual=True)`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/advise.py:40` — `cmd_invoke()` calls `consult()` directly today; this is the call site AC #5/#7 require retargeting.
- `scripts/tests/test_advisor.py:128,147,162,184,202,225,241` — `TestConsult` calls `consult()` directly across 7 sites.
- `scripts/little_loops/config/__init__.py:83,93` — imports and re-exports `AdvisorConfig`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py:51,108` — imports `main_advise` from `cli/advise.py` and re-exports it in `__all__`; the console-script dispatch chokepoint into the retargeted `cmd_invoke()` [Agent 1 finding]
- `scripts/pyproject.toml:69` — `ll-advise = "little_loops.cli:main_advise"` console-script registration resolving through `cli/__init__.py` into `advise.py` [Agent 1 finding]

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_advise.py` (`TestMainAdvise`) — up to 5 of 6 tests (`test_success_prints_exact_json_keys` `:44`, `test_advisor_host_env_independent_of_orchestration_host_cli` `:144`, `test_capability_floor_violation_exits_nonzero_no_consult` `:117`, `test_unwired_host_fails_soft_no_traceback` `:82`, `test_no_advisor_configured_fails_soft` `:107`) never set `config.advisor.enabled = True`; once `cmd_invoke` retargets onto `consult_for_trigger` (which per AC #7 preserves the `enabled` gate), these tests will short-circuit on the disabled-gate before reaching the code path their names claim to exercise. Needs `config.advisor.enabled = True` added to setup, or an explicit new test asserting the disabled-skip behavior [Agent 2 finding]
- `scripts/tests/test_wiring_reference_docs.py:23,25,184` — wiring-conformance test asserting `docs/reference/API.md` documents `little_loops.advisor`/`consult`; will need matching entries added for `TaskKey`/`ConsultBudget`/`resolve_task_key`/`record_consult`/`should_consult`/`consult_for_trigger` to keep passing [Agent 1 finding]
- `scripts/tests/test_wiring_cli_registry.py:23` — wiring-conformance test asserting `docs/reference/CLI.md` documents `ll-advise`; verify it still passes after the CLI.md rewrite below [Agent 1 finding]
- AC #5's static exclusivity assertion ("no code path other than `consult_for_trigger` calls `consult()`") should follow `scripts/tests/test_enh3184_spawn_site_guard.py`'s `TestSpawnSiteGuard` pattern: AST-based (`ast.parse` + `ast.NodeVisitor` over `ast.Call` nodes), not grep-based, with a pinned per-module call-site table, scoped to production modules only (`advisor.py`, `cli/advise.py`) — excluding `scripts/tests/*`, so `TestConsult`'s 7 direct `consult()` calls in `test_advisor.py` remain valid low-level unit coverage and are not in conflict with AC #5 [Agent 3 finding]
- `resolve_task_key`'s precedence tests should follow `test_host_runner.py`'s `isolated_env` fixture (`:51-56`) and `TestResolveHost` (`:249`) shape exactly: one test method per precedence tier, the fixture declared as a parameter (not called inline), including a "both set → higher tier wins" case and a terminal "none set → fallback/raise" case [Agent 3 finding]
- No existing fixture in `test_usage_journal.py` / `test_ab_writer.py` / `test_usage_reporter.py` / `test_cross_host_baseline.py` exercises a counter surviving an actual subprocess boundary (all are single-process `tmp_path` read/write-cycle tests) — AC #3's `record_consult` subprocess-boundary test needs a new pattern (e.g. two separate in-test invocations reading/writing the same counter file), not a reusable existing fixture [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — `## little_loops.advisor` (`:10841`) documents `consult()`/`AdvisorVerdict`/`FloorResult`/`check_floor`; no `resolve_task_key`/`should_consult`/`consult_for_trigger`/`record_consult` entries yet.
- `docs/reference/CONFIGURATION.md` — `### \`advisor\`` (`:1401`) field table (`:1411-1416`) has no `max_consults_per_task` row yet.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (`### ll-advise`, `:178-205`) — line `:197` currently states `advisor.enabled: false` (the default) "does not block an explicit `ll-advise` invocation; it only gates the FEAT-3038/FEAT-3039 auto-consult paths." This directly contradicts this issue's own AC #7: once `cmd_invoke` retargets onto `consult_for_trigger` (which preserves the `enabled` gate), `advisor.enabled: false` **will** block a manual `ll-advise` call. Must be rewritten. The exit-codes table (`:199`) also has no entry for the new budget-exhausted/disabled-skip case (`consult_for_trigger` returning `None`) [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md:399` — lists `ll-advise` in the host-support matrix; verify still accurate after the retarget [Agent 1 finding]
- `skills/configure/areas.md:389,849` — references advisor-related config in the `/ll:configure` skill's area listing; check whether `max_consults_per_task` needs a mention here [Agent 1 finding]

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

**Types**
- `TaskKey: {kind: Literal["issue", "loop_run", "session"], value: str}`
- `ConsultBudget: {max_per_task: int, spent: int, task_key: TaskKey}`
- Confirmed absent from `scripts/little_loops/advisor.py` today (repo-wide grep, zero matches): `TaskKey`, `ConsultBudget`, `resolve_task_key`, `record_consult`, `should_consult`, `consult_for_trigger`.

### Signatures
- `resolve_task_key(env: dict[str, str] | None = None) -> TaskKey` — mirrors `resolve_host(env: dict[str, str] | None = None) -> HostRunner` (`scripts/little_loops/host_runner.py:1960-2005`; `env` defaults to `dict(os.environ)`); tiers: `LL_ISSUE_ID` → `LL_LOOP_RUN_ID` → `CLAUDE_SESSION_ID`/`get_current_session_id()`.
- `record_consult(task_key: TaskKey) -> int` — returns the new count; store `.ll/advisor-budget/<kind>-<value>.json` under `acquire_lock` + `atomic_write_json`.
- `should_consult(trigger: str, config: BRConfig, *, task_key: TaskKey | None = None, manual: bool = False) -> bool`.
- `consult_for_trigger(trigger: str, *, question: str, context: str = "", config: BRConfig | None = None, main_host: str | None = None, main_model: str | None = None, manual: bool = False) -> ConsultOutcome`.
- `ConsultOutcome` frozen dataclass — see Proposed Solution; `skipped_reason` enum maps 1:1 onto FEAT-3300's `AdvisorConsultRow.outcome`.
- `consult(question: str, signal: str, context: str = "", config: BRConfig | None = None, main_host: str | None = None, main_model: str | None = None) -> AdvisorVerdict` (`scripts/little_loops/advisor.py:183`) — the existing target `consult_for_trigger` wraps. `signal` has no default (`test_advisor.py` asserts `TypeError` when omitted, e.g. `test_missing_signal_raises_typeerror` around line 236) — `consult_for_trigger` must keep supplying `signal=trigger` on every call.
- `AdvisorConfig.max_consults_per_task: int = 3` — new field on the dataclass at `scripts/little_loops/config/orchestration.py:109` (current fields: `enabled`, `host`, `model`, `min_tier`, `timeout_seconds`, `triggers`); wire into `from_dict()` (`:128`), `BRConfig._advisor` construction (`config/core.py:335`), the `config.advisor` property (`config/core.py:466` — not `:367-369`, which is the `parallel` property), and `to_dict()`'s `advisor` block (`config/core.py:879`).

### Call Path
`scripts/little_loops/cli/advise.py:cmd_invoke` (`:24`, current `consult()` call at `:40`) → `consult_for_trigger(args.signal, question=args.question, context=context, config=config, main_host=args.main_host, main_model=args.main_model, manual=True)` → `task_key = resolve_task_key()` → `should_consult(trigger, config, task_key=task_key, manual=True)` → `record_consult(task_key)` → `consult(question=..., signal=trigger, context=..., config=config, main_host=main_host, main_model=main_model)` (`scripts/little_loops/advisor.py:183`) → `ConsultOutcome`.

### Decision Rules
- `should_consult` returns `False` when `config.advisor.enabled` is `False` (auto-consult master switch, mirroring `hooks/learning_tests_gate.py:gate()` :90-96's `if not lt_config.enabled: return ...`), or when `trigger not in config.advisor.triggers` — both checks are skipped when `manual=True` (the `ll-advise` path); the budget check always applies.
- `should_consult` returns `False` when the task key's `record_consult` count has already reached `config.advisor.max_consults_per_task` (default 3), logging the reason.
- `should_consult` is fail-soft: any config-read failure inside it is caught and treated as "do not consult" rather than raised — mirrors `hooks/__init__.py:_hooks_telemetry_enabled()` (`:83-108`, whole body wrapped in `try/except Exception: return False`).
- `consult_for_trigger` spends budget (`record_consult`) before calling `consult()`; it catches `AdvisorNotConfigured` / `CapabilityFloorViolation` / `HostNotConfigured` / `BlockingJsonError`, logs a warning, and returns a `ConsultOutcome` with the matching `skipped_reason` rather than raising or propagating. It never returns bare `None`.
- `resolve_task_key` is a pure env lookup; orchestrators are responsible for exporting `LL_ISSUE_ID` / `LL_LOOP_RUN_ID` at their spawn sites.

### Deviations

_Added during implementation — 2026-08-23:_

- **`LL_LOOP_RUN_ID` export mechanism**: the Proposed Solution specified threading `LL_LOOP_RUN_ID` through `project_child_env(extra=...)` at ll-loop's spawn site(s) in `cli/loop/_helpers.py`, mirroring the `LL_HOST_CLI` `extra=` precedent at that file's line ~2143. Implemented instead as a process-wide `os.environ["LL_LOOP_RUN_ID"] = instance_id` set once in `run_foreground()` (`cli/loop/_helpers.py`) when `instance_id` is known. Reason: an FSM loop run's host-CLI spawns are scattered across `fsm/evaluators.py` (x2), `fsm/runners.py`, and `fsm/handoff_handler.py` — threading `extra=` through every one of those call sites would touch four modules for one env var, whereas `project_child_env()`'s documented default behavior (full `os.environ` inheritance, merged with `invocation.env` then `extra`) picks up a process-wide env var automatically at every one of those sites with a single-line change. Functionally equivalent for AC #1 (every spawned host session under this loop run inherits `LL_LOOP_RUN_ID`); `LL_ISSUE_ID` for ll-auto/ll-sprint/ll-parallel still threads through `extra_env`/`project_child_env(extra=...)` as specified, since those have a single well-defined per-issue spawn chokepoint (`subprocess_utils.run_claude_command`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/CLI.md` — the `:197` sentence (`advisor.enabled: false` doesn't block manual `ll-advise`) remains true under the revised AC #7; extend it to say the manual path *is* budget-counted, and add a `budget_exhausted` case to the `:199` exit-codes table.
- `scripts/tests/test_cli_advise.py` — no `enabled = True` churn needed (manual path bypasses `enabled`); add one test for the `budget_exhausted` exit-2 path and one asserting `enabled: false` still consults.
- Add `LL_ISSUE_ID` export at the ll-auto / ll-sprint / ll-parallel spawn sites and `LL_LOOP_RUN_ID` at ll-loop's, all through `project_child_env(extra=...)` / `HostInvocation.env` — grep the `LL_HOST_CLI` `extra=` site in `cli/loop/_helpers.py` for the pattern.
- Write the AC #5 static exclusivity assertion using `test_enh3184_spawn_site_guard.py`'s AST-based, pinned-per-module-table pattern, scoped to production modules only (`advisor.py`, `cli/advise.py`).
- Confirm `scripts/little_loops/cli/__init__.py` (`main_advise` import/re-export, `:51,108`) and `scripts/pyproject.toml:69` (`ll-advise` console-script entry) still resolve correctly through the retargeted `cmd_invoke()` — no functional change expected, verify only.

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

The open call-site-contract conflict (this issue's AC #5 vs FEAT-3120's and FEAT-3039's direct `consult()` call paths) is settled: **`consult_for_trigger` is the sole caller of `consult()` from the moment this issue lands.** FEAT-3120 (landing first) ships `main_advise -> consult()`; retargeting it onto `consult_for_trigger(..., manual=True)` is added to this issue's scope; FEAT-3039 routes through `consult_for_trigger` from the start. Manual-path semantics: budget-counted, but exempt from both `advisor.enabled` and the `advisor.triggers` allowlist (an explicit `--signal` from the user is not an auto-trigger). `consult_for_trigger` gains the `manual: bool = False` parameter to express this (revised 2026-08-23 review: `manual` also bypasses `advisor.enabled`). Scope Boundary notes here and in FEAT-3120/FEAT-3039 updated to match.

### 2026-08-23 (pre-implementation review)

Revised after a code-level review: (1) added the `LL_ISSUE_ID`/`LL_LOOP_RUN_ID` env contract — no task-identifying env var existed, so the resolver had no production input; (2) `consult_for_trigger` gains `config`/`main_host`/`main_model` pass-throughs (the `ll-advise` retarget was otherwise dropping four CLI flags) and returns a typed `ConsultOutcome` instead of bare `None` (preserves `ll-advise`'s per-reason errors, feeds FEAT-3300's outcome enum); (3) `enforce_trigger_allowlist=False` → `manual=True`, which bypasses `advisor.enabled` as well — otherwise `ll-advise` is dead on a fresh install where `enabled` defaults to `False`; (4) counter store fixed to `.ll/advisor-budget/` + `acquire_lock`/`atomic_write_json` (one store, not three), reserve-before-consult; (5) FEAT-3040 refs redirected to FEAT-3300/3301; `depends_on` entries both done.

## Session Log
- `/ll:manage-issue` - 2026-08-23T22:49:18 - `7bda0207-9380-42da-8921-b7a6588dcc63.jsonl`
- `/ll:ready-issue` - 2026-08-23T22:26:54 - `7b309cd7-ab10-4f69-9aa1-683307b82bbe.jsonl`
- `/ll:confidence-check` - 2026-08-23T22:22:13 - `7305c635-3f60-4956-8ef1-9628802d3e9a.jsonl`
- `/ll:confidence-check` - 2026-08-23T21:57:01 - `e5565711-67bf-4342-999d-ec26553c5ca2.jsonl`
- `/ll:wire-issue` - 2026-08-23T21:54:15 - `eba8b56c-d064-4da7-b7b3-4b41a03187b8.jsonl`
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
  `consult_for_trigger(args.signal, ..., manual=True)`
  is in **this issue's scope** (see Proposed Solution), so the static
  assertion holds tree-wide from the moment this issue lands. FEAT-3039's
  evaluator (which lands after this issue) routes through
  `consult_for_trigger` with its state-derived signal from the start —
  its Call Path has been updated to match.
- **Telemetry skip instrumentation (vs FEAT-3300)**: FEAT-3040 is `done` as
  a decomposition marker only (commit `3e492b26a`); its work is FEAT-3300
  (schema/writer/reader, open) and FEAT-3301 (ctx-stats, deferred).
  FEAT-3300 requires `advisor_consults` rows for skipped consults; budget
  skips short-circuit in `consult_for_trigger` here and never reach
  `consult()`. `ConsultOutcome.skipped_reason` is the skip-recording API —
  its enum is aligned to `AdvisorConsultRow.outcome` so FEAT-3300's writer
  hooks `consult_for_trigger`'s return, not `consult()`. FEAT-3300 should
  add FEAT-3116 to its `depends_on`.
- **Counter storage migration (vs FEAT-3300)**: `.ll/advisor-budget/` is the
  interim store; once `advisor_consults` lands, `record_consult`/the budget
  check become a `COUNT(*)` over that table and the directory is retired.
