---
id: FEAT-3038
title: Advisor signal-gated auto-consults and per-task budget
type: FEAT
parent: EPIC-3041
priority: P3
testable: true
decision_needed: true
discovered_date: 2026-08-03
depends_on:
- FEAT-3044
labels:
- planning-hub
verify_verdict: VALID
size: Very Large
status: done
---

# FEAT-3038: Advisor signal-gated auto-consults and per-task budget

## Summary

Slice 2 of the host-agnostic advisor (FEAT-3037). Wire the first two automatic
consult triggers — `confidence_gate` and `pre_done` — to measurable signals the
harness already computes, and add the `max_consults_per_task` budget plus the
per-task counter that makes it enforceable.

This is the slice where the advisor stops being a manual tool and becomes the
signal-gated escalation the design argues for. FEAT-3037 ships the CLI with a
required `--signal` argument precisely so this slice has a contract to fill in.

## Current Behavior

After FEAT-3037:

- `ll-advise` exists and requires `--signal`, but every consult is
  user/model-invoked. `user_requested` is the only signal ever passed.
- `advisor.triggers` is accepted in config but nothing reads it.
- `max_consults_per_task` is deliberately absent from the schema — enforcement
  needs task identity, which does not exist yet.
- `commands.confidence_gate.readiness_threshold` (85) blocks on a sub-threshold
  score and stops there; there is no escalation path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Stale as of this pass (2026-08-08)**: the prior finding "the advisor stack is unimplemented" is now partially wrong. `scripts/little_loops/advisor.py` and `scripts/tests/test_advisor.py` were created by FEAT-3108 (commit `9dbe5943`, landed 2026-08-08) and already contain `MODEL_RANKS`, `FloorResult`, `rank_model()`, `check_floor()` — the capability-floor slice only. `consult()`, `AdvisorVerdict`, `AdvisorConfig`, `should_consult`, `resolve_task_key`, `record_consult`, `consult_for_trigger` still do not exist anywhere in the codebase; FEAT-3043 (`AdvisorConfig`) and FEAT-3044 (`consult()`/`AdvisorVerdict`) remain `open` and are still the direct prerequisites this issue's `depends_on: FEAT-3044` edge captures. Implementers should extend the existing `advisor.py`/`test_advisor.py`, not create them.

## Expected Behavior

- A sub-threshold `confidence-check` readiness score auto-consults the advisor
  with the gap analysis, signal `confidence_gate`, instead of only blocking.
- The `Stop` hook, on the final diff, auto-consults with signal `pre_done`
  before a task is declared done.
- Each trigger fires only when listed in `advisor.triggers`; an unlisted trigger
  is inert.
- `max_consults_per_task` caps consults per task; the cap being reached is
  logged and the consult skipped, never silently dropped or retried.
- No consult path exists that does not cite a signal.

## Use Case

An `autodev` run finishes implementing FEAT-2xxx and `confidence-check` returns
a readiness score of 71 against a threshold of 85, with the gap being "test
coverage for the error path is unclear." Today the gate blocks and the operator
reads the gap by hand. With this slice, the sub-threshold score auto-consults an
Opus advisor with the gap analysis attached; the verdict's `recommendation` and
`risks[]` land in the transcript alongside the block, so the next iteration
starts from a stronger read rather than the same model's re-grade.

## Proposed Solution

### Task identity (the prerequisite)

`max_consults_per_task` needs a stable task key. Reuse the existing notion
rather than inventing one: the issue ID when running under `ll-auto`/`ll-sprint`
/`ll-parallel`, the loop run ID under `ll-loop`, and the session ID otherwise.
A small `resolve_task_key()` resolver with that precedence, plus a counter
persisted under the run directory, keeps the cap correct across the subprocess
boundaries these runners cross.

### Trigger dispatch

A single `should_consult(trigger, config)` predicate — checks
`advisor.enabled`, membership in `advisor.triggers`, and the budget — called
from both wiring points so the gating logic has one implementation.

- **`confidence_gate`** — hook into the sub-threshold branch of the
  confidence-gate evaluation, passing the gap analysis as the consult context.
- **`pre_done`** — a `Stop` hook entry in `hooks/hooks.json` dispatching to a
  host-agnostic handler under `scripts/little_loops/hooks/`, consistent with the
  existing handler layout.

Both call `little_loops.advisor.consult()` with an explicit signal. Failures are
non-fatal: a failed consult logs and proceeds, never blocking the primary path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- Prerequisite reality: as of this refine (2026-08-06) the advisor stack is unimplemented — `scripts/little_loops/advisor.py`, `cli/advise.py`, `AdvisorConfig`, `test_advisor.py`, and the `ll-advise` entry point do not exist. The `Current Behavior` section describes the post-FEAT-3037 state, which lands via the still-open decomposition FEAT-3044 → {FEAT-3042, FEAT-3043}. FEAT-3038's `depends_on: FEAT-3044` is the direct edge; `AdvisorConfig` (enabled/triggers) ships in FEAT-3043, `consult()`/`AdvisorVerdict` in FEAT-3044.
- `resolve_task_key()` precedence resolves from existing primitives: issue ID via `_resolve_issue_id()` (`cli/issues/show.py:40-120`) / `IssueInfo.issue_id`; ll-loop `instance_id` = `f"{loop_name}-{YYYYmmddT%H%M%S}"` (`cli/loop/_helpers.py:1505-1507`) with run dir `loops_dir/runs/<instance_id>` = `${context.run_dir}` (`cli/loop/run.py:189-198`, `:572`); ll-auto/ll-sprint/ll-parallel `run_id` = `uuid4().hex` (`issue_manager.py:1580`, `parallel/orchestrator.py:123`); session ID via `get_current_session_id()` (`session_log.py:141-155`, `CLAUDE_SESSION_ID` env → JSONL-stem fallback) or `LLHookEvent.session_id`.
- Budget counter persistence location differs by runner: ll-loop → `${context.run_dir}` (precedent: `usage.jsonl`/`ab.json` written under run_dir at `cli/loop/_helpers.py:1892-1923`); ll-auto → `.ll/.auto-manage-state.json` (`config.automation.state_file`, resolved at `config/core.py:510`). Per-task counter-file idiom precedent: `rn-remediate.yaml:1008-1011` (`remediation_count_<ISSUE_ID>.txt`).
- Fail-soft contract is established in the hook layer: `hooks/__init__.py:40-43` (hook telemetry "never alters the handler's exit code or exception propagation") and every handler wraps in try/except returning exit 0 (`pre_compact.py:84-171`, `drift_check.py:113-157`). A `pre_done` consult failure follows the same shape — log and proceed, never block the primary path (AC #7).

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

The `confidence_gate` trigger's scope is underspecified: `readiness_status()`/`ReadinessStatus` has exactly one Python call site (`issue_manager.py:781-816`, the ll-auto pre-Phase-1 gate), but five FSM loop YAMLs (`autodev.yaml`, `rn-remediate.yaml`, `rn-implement.yaml`, `refine-to-ready-issue.yaml`, `recursive-refine.yaml`) each compare against the same `readiness_threshold` in their own shell/subprocess step, never through that function. A consult hook added only to `issue_manager.py` will not fire for any of those FSM-embedded gates.

**Option A**: Scope the `confidence_gate` consult to the single Python call site in `issue_manager.py`'s pre-Phase-1 gate only. Simplest to implement and test — one call site, one set of tests — but the FSM-embedded readiness gates get no consult coverage at all, even though they gate the same threshold for `ll-loop`-driven runs.

**Option B**: Also wire `should_consult`/`consult_for_trigger` into the FSM gates, e.g. by adding a consult path to `ll-issues check-readiness` itself (the shared subprocess every FSM gate already calls) so every readiness comparison benefits without touching five separate YAML files.

**Recommended**: Option A for this slice — Acceptance Criteria #1 only requires the ll-auto path ("A confidence-check readiness score below ... triggers exactly one consult"), which Option A satisfies exactly. Extending to `ll-issues check-readiness` itself is a larger, separately-scoped change (it would consult on every `check-readiness` invocation, including read-only/diagnostic ones, not just gating ones) better suited to its own issue.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Cross-reference: the Option A/B decision above concerns only the `confidence_gate` trigger's call-site scope; it does not affect the `pre_done` Stop-hook wiring or `resolve_task_key()` precedence described in the 2026-08-07 findings above.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- No existing standalone `should_X(trigger, config) -> bool` predicate, decoupled from a handler and called from two wiring points, exists anywhere in the codebase. Every current enabled+allowlist gate is inlined per-handler with the same two-level shape (`.enabled` check, then allowlist/mode membership check): `hooks/learning_tests_gate.py:gate()` (`:91-101`, `lt_config.enabled` then `disc.mode`) and `hooks/__init__.py:_hooks_telemetry_enabled()` (`:83-108`, `analytics.enabled` then `analytics.capture.hooks`) — the latter's docstring states "any config-read failure disables telemetry rather than raising... telemetry must never be the reason a hook fails" (`:89-92`), the same fail-soft shape AC #7 requires for `should_consult`.
- The closest structural precedent for `resolve_task_key(env: dict[str, str] | None = None) -> TaskKey` is `host_runner.py:resolve_host()` (`:1574-1619`) — the only other function in the codebase that resolves an identity by a numbered precedence order, is injectable via an `env` dict defaulting to `os.environ`, and documents each fallback tier in its docstring. No other multi-source identity-precedence resolver exists; the issue/loop-run/session sources this issue cites remain three unrelated, uncoordinated call sites. `resolve_host()`'s test shape — one test per precedence tier (`test_host_runner.py:test_resolve_host_picks_codex_via_env:268`, `:615`, `:659`, `:719`, `:861`, `:1042`), each asserting a given env-dict input resolves to the expected member via an `isolated_env` fixture — is the established pattern for testing a precedence resolver, distinct from the config from_dict triad cited elsewhere.
- Concrete instance of the config dataclass three-case test triad: `test_config.py:TestClusterConfig` (`:3382-3403`) — `test_from_dict_with_defaults`, `test_from_dict_with_all_fields`, `test_from_dict_partial_override`, where the partial-override case re-asserts every field (not just the one under test) to double as an "everything else still defaults" check. `AdvisorConfig.max_consults_per_task` tests should follow this same re-assert-every-field shape.
- Contested convention — `Stop` hook entry shape: existing `Stop` entries in `hooks/hooks.json:199-230` have no `"matcher"` key and route through bash-only scripts under `hooks/scripts/`, none Python-dispatched. The only other Python-dispatched adapters (`SubagentStart`/`SubagentStop`, `hooks/hooks.json:277-302`) use `"matcher": "*"` and route through `hooks/adapters/claude-code/*.sh` (two-line `INPUT=$(cat) | python3 -m little_loops.hooks <intent>` shape, e.g. `hooks/adapters/claude-code/precompact.sh`). A `pre_done` entry would be the first `Stop` entry to carry a matcher and route through `hooks/adapters/`, and the two existing `Stop` shapes disagree on which to follow.
- Contested convention — counter-persistence locking: alongside the three no-lock idioms already cited (`usage.jsonl` append, `remediation_count_<ID>.txt` read-modify-write, `.ll/.auto-manage-state.json` atomic-rename), `hooks/pre_compact.py` (`:158-168`) demonstrates a fourth, lock-attempting idiom — `acquire_lock(state_lock, timeout=3.0)` wrapping `atomic_write_json`, falling back to an unlocked write on `TimeoutError` rather than dropping the write. None of the four idioms is a demonstrated multi-writer-safe precedent for a counter that AC #5 requires be "correct across a subprocess boundary."
- Hook-intent registration requires three sites to move together, each independently confirmed: `_INTENT_EVENT_NAME` (`hooks/__init__.py:68-80`), `_USAGE` (`:111-116`), `_dispatch_table()` (`:134-165`), enforced by `test_hook_intents.py:test_dispatch_table_intent_event_name_usage_stay_consistent` (`:827-855`). Each dispatched intent also gets a happy-path and malformed-payload subprocess smoke test under `TestHooksMainModule` (e.g. `test_dispatch_subagent_start_happy_path:520-533` / `test_dispatch_subagent_start_malformed_payload:534-544`) — a `pre_done` handler needs both, not just the dispatch-table consistency test.

## Program Design

### Types

- `TaskKey: {kind: Literal["issue", "loop_run", "session"], value: str}`
- `ConsultBudget: {max_per_task: int, spent: int, task_key: TaskKey}`

### Signatures

- `resolve_task_key(env: dict[str, str] | None = None) -> TaskKey`
- `should_consult(trigger: str, config: BRConfig) -> bool`
- `record_consult(task_key: TaskKey) -> int` — returns the new count
- `consult_for_trigger(trigger: str, *, question: str, context: str) -> AdvisorVerdict | None`
- `AdvisorConfig.max_consults_per_task: int` (new field, default 3)

### Call Path

`confidence-gate evaluation` -> `should_consult("confidence_gate", ...)` -> `consult_for_trigger` -> `little_loops.advisor.consult`

`Stop hook` -> `main_hooks()` dispatch -> `pre_done handler` -> `should_consult("pre_done", ...)` -> `consult_for_trigger`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- Call-path anchors: the `confidence-gate evaluation` hop in the call path is concretely `issue_manager.py:788-816` (ll-auto pre-Phase-1 gate) and/or the FSM `${context.readiness_threshold}` shell gates (`loops/autodev.yaml:1553,1658-1666`), both thresholded against `ConfidenceGateConfig.readiness_threshold` (default 85). The `Stop hook` hop is `main_hooks()` (`hooks/__init__.py:168-226`) dispatching to a new `pre_done` handler.
- `consult_for_trigger(...) -> AdvisorVerdict | None` consumes the FEAT-3044 verdict shape: `AdvisorVerdict {recommendation: str, risks: list[str], confidence: float, dissent: str, signal: str, host: str, model: str}` (frozen dataclass in `advisor.py`).
- `should_consult(trigger, config: BRConfig)` reads `advisor.enabled` / `advisor.triggers` from `AdvisorConfig` (FEAT-3043): `{enabled, host, model, min_tier, timeout_seconds, triggers}`; `max_consults_per_task` (default 3) is the field this issue adds to that dataclass.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- FSM loop gates (`autodev.yaml`, `rn-remediate.yaml`, `rn-implement.yaml`, `refine-to-ready-issue.yaml`, `recursive-refine.yaml`) run each readiness comparison in its own shell/subprocess step — they call `ll-issues check-readiness` as a subprocess or re-derive the threshold inline in Python, never through `issue_manager.py`'s `readiness_status()` call in-process. A `confidence_gate` consult hook placed only in `issue_manager.py`'s branch (line 781-816) does not automatically reach any FSM-embedded gate; the two are architecturally parallel, not shared state. See the Option A/B decision added to Proposed Solution below.
- Counter-persistence idioms already in the codebase disagree on locking: the FSM's `usage.jsonl` append (`fsm/persistence.py:770-797`) and `rn-remediate.yaml`'s `remediation_count_<ID>.txt` read-modify-write (`:576-578`) both use no lock, relying on single-writer sequential execution; `.ll/.auto-manage-state.json` (`state.py:139-160`, via `StateManager.save()`) uses an atomic tempfile-rename with no lock either. Only the hook-layer state files (`pre_compact.py:161-165`, `drift_check.py:84-94`) use `acquire_lock()` + `atomic_write_json`, and that pattern guards single-writer atomicity, not multi-writer contention on a shared counter. None of the three demonstrated idioms is a multi-writer-safe precedent to copy verbatim for a consult counter that AC #5 requires be "correct across a subprocess boundary."
- `StateManager` (`state.py`) has no generic arbitrary-counter API — it is a fixed `ProcessingState` dataclass (current issue, completed/failed/skipped lists, timing, corrections). A `max_consults_per_task` counter under the ll-auto path cannot just add a field to an existing counter mechanism; it needs its own key or file.

## Integration Map

### Files to Modify

- `scripts/little_loops/advisor.py` — `should_consult`, `consult_for_trigger`,
  `record_consult`, `resolve_task_key`.
- `scripts/little_loops/config/orchestration.py` — add
  `AdvisorConfig.max_consults_per_task`.
- `scripts/little_loops/config-schema.json` — add `max_consults_per_task`
  (deferred out of FEAT-3037 on purpose).
- `hooks/hooks.json` — `Stop` entry for the pre-done consult.
- `scripts/little_loops/hooks/` — new pre-done handler, registered in the
  dispatch table; update the `_USAGE` intent list in `hooks/__init__.py`.
- Confidence-gate evaluation site — add the sub-threshold consult branch.

### Dependent Files (Callers/Importers)

- `skills/confidence-check/SKILL.md` — document that a sub-threshold score may
  now attach an advisor verdict.
- `scripts/little_loops/cli/advise.py` — reuse `should_consult` so the manual
  path is budget-counted too.

### Tests

- `scripts/tests/test_advisor.py` — `should_consult` false when disabled /
  trigger unlisted / budget exhausted; `resolve_task_key` precedence.
- `scripts/tests/test_hook_intents.py` — Stop-hook pre-done dispatch, including
  the no-op path when the trigger is unlisted.
- Budget persistence across a simulated subprocess boundary.

### Documentation

- `docs/reference/CLI.md`, `docs/reference/API.md`, `.claude/CLAUDE.md` hooks
  section.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- `scripts/little_loops/issue_manager.py:788-816` — the ll-auto pre-Phase-1 confidence gate: sub-threshold readiness prints `CONFIDENCE_GATE_BLOCKED <id>` and `PHASE1_NOT_STARTED <id> confidence_gate`, then returns `below_readiness_threshold`. A `confidence_gate` consult branch must hook the sub-threshold path without changing that blocking outcome.
- `scripts/little_loops/cli/issues/check_readiness.py` — `ReadinessStatus.meets_readiness` (`:33-35`) and `readiness_status()` (`:42-96`) own the threshold comparison (`confidence >= readiness_threshold`); `cmd_check_readiness` (`:99-125`) exits 0/1. The gap analysis this module produces is the consult context the confidence_gate trigger passes.
- FSM loop gates — `loops/autodev.yaml:1553` and `:1658-1666` (and `rn-remediate.yaml`, `rn-implement.yaml`, `refine-to-ready-issue.yaml`, `recursive-refine.yaml`) compare `int(cur) < ${context.readiness_threshold}` in shell; the context value is seeded by `seed_confidence_thresholds()` (`cli/loop/_helpers.py:1366-1392`) from `commands.confidence_gate.readiness_threshold` (default 85, `config/automation.py:143-159`).
- `hooks/hooks.json:199-230` — the `Stop` event currently runs three shell scripts (context-handoff-sentinel, session-cleanup, record-hook-event); none dispatch through `python -m little_loops.hooks`. A Python `pre_done` handler requires a new `Stop` entry plus an adapter following the SessionStart/SessionEnd pattern (`hooks/adapters/claude-code/` pipes stdin JSON to `python -m little_loops.hooks <intent>`).
- Adding a `pre_done` intent means touching all three dispatch sites in `hooks/__init__.py` — `_INTENT_EVENT_NAME` (`:68-80`), `_USAGE` (`:111-116`), `_dispatch_table()` (`:134-165`) — because `scripts/tests/test_hook_intents.py::test_dispatch_table_intent_event_name_usage_stay_consistent` (`:827-855`) asserts the three enumerate the identical intent set.
- `main_hooks()` (`hooks/__init__.py:168-226`) builds `LLHookEvent.session_id` from `payload.get("session_id")` (`:203`) — the hook-context session-ID source for `resolve_task_key()`.
- `scripts/tests/test_config.py` — `TestOrchestrationConfig` (`:3406`), `TestBRConfigOrchestration` (`:3476`), `test_to_dict_orchestration` (`:1012-1048`) hold the config round-trip pattern that `AdvisorConfig.max_consults_per_task` tests mirror (FEAT-3043 applies the same pattern).
- `scripts/tests/test_advisor.py` does not exist yet; FEAT-3044 defines its scope (consult/rank_model/check_floor) plus a separate `test_cli_advise.py` for `main_advise` argparse. FEAT-3038's `should_consult`/`resolve_task_key`/budget tests extend `test_advisor.py` per this issue's Tests section.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- `scripts/little_loops/config/core.py` — `AdvisorConfig` needs manual field-by-field wiring into `BRConfig.to_dict()` (`:784-801`, hand-rolled per block, no generic serializer — tracked as a known gap under BUG-3012, not something this issue should fix) and a `core.py:367-369`-style property exposing `config.advisor`. Nearest structural precedent for a block that ships inert config ahead of its consumer: `CodeQueryConfig` (`config/features.py:848-862`), aggregated at `core.py:268`.
- `scripts/little_loops/config/__init__.py` — needs `AdvisorConfig` added to imports/`__all__`, same as every other orchestration/automation config class.
- No `hooks/adapters/claude-code/stop.sh` (or equivalent) exists today — `Stop` in `hooks/hooks.json:199-230` runs three pure-bash scripts, none piping through `python -m little_loops.hooks`. A `pre_done` handler would be the *first* Python-dispatched `Stop` intent; the nearest template to copy the two-line `INPUT=$(cat) | python3 -m little_loops.hooks <intent>` shape from is `hooks/adapters/claude-code/precompact.sh`, not an existing Stop adapter.
- `scripts/tests/test_config_schema.py:1082` (`test_to_dict_emits_every_schema_section`) and `:1104` (`test_to_dict_emits_no_key_absent_from_schema`) — lockstep tests that fail if `advisor` is declared in `config-schema.json` but not emitted by `to_dict()`, or vice versa.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` and `docs/reference/CONFIGURATION.md` — not previously listed; both document exactly this kind of addition (a new hook intent, a new config block) and are missing from the original Documentation list.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Every dispatched hook intent gets an in-process subprocess smoke test under `TestHooksMainModule` in `scripts/tests/test_hook_intents.py` (e.g. `test_dispatch_drift_check_happy_path:485-501`, `test_dispatch_subagent_start_happy_path:520-532`, plus a malformed-payload variant) — a `pre_done` handler needs the same pair, not just the dispatch-table consistency test already listed.
- `TestClusterConfig`/`TestOrchestrationConfig` (`test_config.py:3382-3473`) demonstrate the three-case shape config-block tests follow: `from_dict({})` (all defaults), `from_dict({all fields})` (all overrides), `from_dict({one field})` (partial override, others still default) — `AdvisorConfig`'s tests should mirror this shape, not just the round-trip cases already listed.

## Acceptance Criteria

1. A `confidence-check` readiness score below
   `commands.confidence_gate.readiness_threshold` triggers exactly one consult
   with signal `confidence_gate`, and the gap analysis is in the consult context.
2. The `Stop` hook triggers exactly one consult with signal `pre_done` when
   `pre_done` is listed in `advisor.triggers`.
3. A trigger absent from `advisor.triggers` fires no consult; `advisor.enabled:
   false` fires none at all.
4. `max_consults_per_task` is enforced: the Nth+1 consult for the same task key
   is skipped with a logged reason, not attempted.
5. The counter is correct across a subprocess boundary (a consult from a child
   runner increments the same task's count).
6. `resolve_task_key` prefers issue ID, then loop run ID, then session ID.
7. A failed or timed-out consult never blocks the primary path — the gate/hook
   completes with its original verdict and a logged warning.
8. No code path invokes `consult()` without an explicit signal (asserted).
9. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Impact

- **Priority**: P3 — matches FEAT-3037. Without this slice the advisor is an
  ungated manual tool, which is the design's stated failure mode.
- **Effort**: Medium — trigger wiring is small, but task identity spanning the
  runner subprocess boundaries is the real work.
- **Risk**: Medium — adds a synchronous network call to the confidence gate and
  the Stop hook, two hot paths. Mitigated by fail-soft semantics and
  off-by-default triggers.
- **Breaking Change**: No — inert unless `advisor.triggers` lists a trigger.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1 (pair LLM judgment with a
  non-LLM signal).

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-08
- **Reason**: Issue scored 11/11 (Very Large) on `/ll:issue-size-review`;
  split into three independently shippable children — shared budget/identity
  infrastructure, then the two trigger wiring points that consume it.

### Decomposed Into
- FEAT-3116: Advisor consult budget and task-identity infrastructure
- FEAT-3117: Wire confidence_gate consult trigger into the ll-auto readiness gate
- FEAT-3118: Wire pre_done consult trigger into the Stop hook

## Status

**Done** | Created: 2026-08-03 | Priority: P3


## Session Log
- `/ll:issue-size-review` - 2026-08-08T21:18:50 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`
- `/ll:verify-issues` - 2026-08-08T21:15:56 - `c7f56cd0-0af0-4888-afb5-9244e302ca34.jsonl`
- `/ll:refine-issue` - 2026-08-08T21:14:39 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`
- `/ll:verify-issues` - 2026-08-08T21:11:31 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`
- `/ll:refine-issue` - 2026-08-08T21:08:17 - `29dcd8e6-5691-426f-91c4-b6457c12fffb.jsonl`
- `/ll:refine-issue` - 2026-08-07T01:01:06 - `398b6d9c-0dab-4222-b27d-682f375c74d7.jsonl`
- `/ll:verify-issues` - 2026-08-04T21:29:47 - `e72897bf-a708-4dcd-aeaa-907564ef9e34.jsonl`
