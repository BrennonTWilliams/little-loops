---
id: FEAT-3117
title: Wire confidence_gate consult trigger into the ll-auto readiness gate
type: FEAT
parent: FEAT-3038
priority: P3
status: open
testable: true
discovered_date: 2026-08-08
depends_on:
- FEAT-3116
- FEAT-3120
labels:
- planning-hub
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 95
score_complexity: 22
score_test_coverage: 24
score_ambiguity: 25
score_change_surface: 24
---

# FEAT-3117: Wire confidence_gate consult trigger into the ll-auto readiness gate

## Summary

Child 2 of 3 decomposed from FEAT-3038 (Advisor signal-gated auto-consults and
per-task budget). Wires the `confidence_gate` signal into the single Python
call site FEAT-3038's refinement scoped it to: `issue_manager.py`'s
pre-Phase-1 readiness gate. FEAT-3116 (now done) already delivered
`should_consult` and `consult_for_trigger`, which this issue calls.

## Parent Issue

Decomposed from FEAT-3038: Advisor signal-gated auto-consults and per-task
budget. See that issue's "Proposed Solution" → "Trigger dispatch" →
`confidence_gate` subsection and its Option A/B codebase research (2026-08-08)
for the full scoping rationale.

## Current Behavior

`scripts/little_loops/issue_manager.py:808-833` — the ll-auto pre-Phase-1
confidence gate — prints `CONFIDENCE_GATE_BLOCKED <id>` and
`PHASE1_NOT_STARTED <id> confidence_gate` on a sub-threshold readiness score,
then returns `below_readiness_threshold`. No consult happens on this path.

**Scope note (Option A, from FEAT-3038's refinement)**: five FSM loop YAMLs
(`autodev.yaml`, `rn-remediate.yaml`, `rn-implement.yaml`,
`refine-to-ready-issue.yaml`, `recursive-refine.yaml`) each compare against
the same `readiness_threshold` in their own shell/subprocess step via
`ll-issues check-readiness`, never through `issue_manager.py`'s
`readiness_status()`. This child intentionally does **not** wire those —
FEAT-3038's Acceptance Criteria #1 only requires the ll-auto Python call site,
and extending to `ll-issues check-readiness` itself would consult on every
invocation (including read-only/diagnostic ones), which is a larger,
separately-scoped change better suited to its own future issue.

## Expected Behavior

A sub-threshold `confidence-check` readiness score in the ll-auto pre-Phase-1
gate auto-consults the advisor with the gap analysis attached, signal
`confidence_gate`, without changing the existing blocking outcome. The
consult is skipped (not attempted) when `confidence_gate` is absent from
`advisor.triggers`, when `advisor.enabled` is `false`, or when the task's
`max_consults_per_task` budget is exhausted. A failed or timed-out consult
never blocks the gate — it completes with its original
`below_readiness_threshold` verdict and a logged warning.

## Proposed Solution

In `scripts/little_loops/issue_manager.py`'s sub-threshold branch (`:808-833`):
call `should_consult("confidence_gate", config)`; if `True`, call
`consult_for_trigger("confidence_gate", question=..., context=<gap analysis
from readiness_status()/ReadinessStatus>)` (both from FEAT-3116's
`advisor.py`) before returning `below_readiness_threshold`. The consult result
(when present) is logged/attached alongside the existing block output; the
return value and blocking behavior are unchanged either way.

## Acceptance Criteria

1. A `confidence-check` readiness score below
   `commands.confidence_gate.readiness_threshold`, evaluated through
   `issue_manager.py`'s pre-Phase-1 gate, triggers exactly one consult with
   signal `confidence_gate`, and the gap analysis from `readiness_status()` is
   in the consult context (FEAT-3038 AC #1).
2. `confidence_gate` absent from `advisor.triggers` fires no consult on this
   path; `advisor.enabled: false` fires none either (FEAT-3038 AC #3,
   confidence_gate half).
3. A failed or timed-out consult never blocks the gate — it completes with
   its original `below_readiness_threshold` verdict and a logged warning
   (FEAT-3038 AC #7, confidence_gate half).
4. The FSM-embedded readiness gates (`autodev.yaml` and the other four loop
   YAMLs) are unchanged by this issue — out of scope per Option A above.
5. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Tests

- `scripts/tests/test_issue_manager.py` (or nearest existing suite covering
  the pre-Phase-1 gate) — sub-threshold score triggers exactly one consult
  with signal `confidence_gate` and the gap analysis in context; trigger
  unlisted / advisor disabled fires none; a mocked consult failure leaves the
  gate's `below_readiness_threshold` return and logging unchanged.

## Documentation

- `skills/confidence-check/SKILL.md` — document that a sub-threshold score may
  now attach an advisor verdict.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/issue_manager.py` — wire `should_consult`/`consult_for_trigger` into the pre-Phase-1 confidence gate block inside `process_issue_inplace()` (gate spans lines 801-836; `readiness_status()` call at :805, gate condition at :806, markers at :824/:829, `return _stamped_result(...)` at :830). The consult call must complete before that return, without altering `gate_reason`/`was_gated=True`.

### Dependent Files (Callers/Importers)
- `scripts/tests/test_issue_manager.py:15` — imports `issue_manager`; existing `CONFIDENCE_GATE_BLOCKED` assertions at lines 5593 and 5688 will need a companion case for the consult-triggered path.
- `scripts/little_loops/cli/sprint/run.py:21`, `scripts/little_loops/cli/auto.py:23`, `scripts/little_loops/__init__.py:40` — importers of `issue_manager.py` (confirmed via code graph `importers-of`); none call the gate function directly, so none need changes.
- `scripts/little_loops/advisor.py:477` — `consult_for_trigger` itself re-invokes `should_consult` internally. Confirmed via code graph `callers-of`: today `should_consult`/`consult_for_trigger` have **no production call site** anywhere except `scripts/little_loops/cli/advise.py`'s `cmd_invoke()` (manual=True path) — every other caller is a unit test in `test_advisor.py`. This issue's wiring is the first `manual=False` (auto-trigger) call site in the codebase.

### Conventions in Force
- Fail-soft consult contract: `should_consult`/`consult_for_trigger` never raise — every skip path (disabled, trigger not in `advisor.triggers`, budget exhausted, consult failure/timeout via `AdvisorNotConfigured`/`CapabilityFloorViolation`/`HostNotConfigured`/`BlockingJsonError`) returns a defined sentinel (`False`, or `ConsultOutcome(verdict=None, skipped_reason=...)`) rather than propagating — evidence: `advisor.py:408-522`. No `try/except` is needed at the call site to preserve the gate's existing return.
- Two independent signal channels already coexist at the gate: `print(..., flush=True)` stable markers (`CONFIDENCE_GATE_BLOCKED` :824, `PHASE1_NOT_STARTED ... confidence_gate` :829) for FSM-loop consumers (`autodev.yaml`'s `check_impl_reached`), and `logger.warning(...)` (:819) for human/log-stream consumption — evidence: comments at issue_manager.py:820-823,825-828. A consult result should be logged via `logger`, not by replacing or duplicating either stdout marker.
- The only existing `consult_for_trigger` call site (`cli/advise.py:cmd_invoke`, lines 31-84) branches on `outcome.verdict is None`, falling back to `outcome.skipped_reason`/`outcome.error` via a `_SKIP_MESSAGES` dict (lines 18-28) for messaging. That branching shape is reusable for logging the consult outcome here, but the call itself is `manual=True` and bypasses the `enabled`/`triggers` checks — this issue's call must omit `manual=True` (default `False`) so `should_consult`'s auto-trigger gating actually applies.

_Wiring pass added by `/ll:wire-issue`:_
- `issue_manager.py` currently has **no** import of `little_loops.advisor` at all (confirmed via its import block, lines 26-69) — `should_consult`/`consult_for_trigger` are not referenced anywhere in this file yet. The implementation must add this import.
- All five out-of-scope FSM loop YAMLs (`autodev.yaml`, `rn-remediate.yaml`, `rn-implement.yaml`, `refine-to-ready-issue.yaml`, `recursive-refine.yaml`) were re-confirmed via direct grep for `CONFIDENCE_GATE_BLOCKED`/`ReadinessStatus`/`PHASE1_NOT_STARTED` — none parse or branch on these; they only read `commands.confidence_gate.{readiness,outcome}_threshold` from config for threshold seeding, which this issue does not touch. [Agent 1 finding]

### Tests
- `scripts/tests/test_issue_manager.py` — `TestConfidenceGatePreCheck` class (~5433-5713+) has `CONFIDENCE_GATE_BLOCKED` coverage (`test_sub_threshold_prints_confidence_gate_blocked_marker` :5574, `test_dry_run_does_not_gate_or_print_marker` :5672) to extend with a new test: sub-threshold + trigger listed → exactly one consult; trigger absent/`advisor.enabled=false` → no consult; mocked consult failure → gate's `below_readiness_threshold` return/logging unchanged. New test should follow `test_sub_threshold_score_skips_before_phase_1`'s (:5505) `_status(confidence=80, readiness_threshold=85)` setup and patch `little_loops.issue_manager.consult_for_trigger` (once imported there), mirroring `test_advisor.py`'s `test_maps_each_exception_to_skipped_reason` exception→`skipped_reason` mapping for the fail-soft case.

  _Wiring pass added by `/ll:wire-issue`:_ `TestConfidenceGatePreCheck`'s existing `mock_config = MagicMock(spec=BRConfig)` fixture (:5438) does **not** configure `.advisor` — confirmed this is safe, not a break risk: `MagicMock`'s default `__contains__` returns `False`, so `trigger not in config.advisor.triggers` evaluates `True` inside `should_consult()` and every existing sub-threshold test (:5505, :5525, :5552, :5574) will auto-skip the new consult call with zero added mocking. Only the new consult-triggered test needs to explicitly configure `config.advisor` (real `AdvisorConfig` or a configured `MagicMock`) to exercise the `True` path.
- `scripts/tests/test_advisor.py` — `TestShouldConsult`/`TestConsultForTrigger` already cover the underlying functions' contracts directly; no test yet exercises them from `issue_manager.py`'s gate.

### Documentation
- `docs/reference/API.md:10977` — documents the `should_consult`/`consult_for_trigger` gate predicate; may need a cross-reference to this call site once wired.
- `docs/reference/CLI.md:436` — documents the `CONFIDENCE_GATE_BLOCKED` marker.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` (~lines 1401-1417) — `### advisor` section documents `advisor.enabled`/`triggers`/`max_consults_per_task` and already uses `confidence_gate` as the worked example for `triggers`; low-risk read (no false "not yet wired" claim to fix), but worth a cross-reference once this issue makes `confidence_gate` the trigger's first real auto-call site. [Agent 2 finding]

### Configuration
- `scripts/little_loops/config-schema.json` — `advisor.triggers` (`:1801`) already documents a `confidence_gate` example (`:457`); `max_consults_per_task` (`:1803`) already exists from FEAT-3116. No schema changes needed for this issue.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

**Types**
- No new data types introduced. Consumes the existing `ReadinessStatus` (`scripts/little_loops/cli/issues/check_readiness.py:16`) — fields already in scope at the gate: `confidence`, `readiness_threshold`, `raw_confidence`, `enabled`, `meets_readiness` — and the existing `ConsultOutcome` (`advisor.py:314-335`, `task_key`/`verdict`/`skipped_reason`/`error`, exactly one of `verdict`/`skipped_reason` set).

### Signatures
- `should_consult(trigger: str, config: BRConfig, *, task_key: TaskKey | None = None, manual: bool = False) -> bool` — `advisor.py:408`
- `consult_for_trigger(trigger: str, *, question: str, context: str = "", config: BRConfig | None = None, main_host: str | None = None, main_model: str | None = None, manual: bool = False) -> ConsultOutcome` — `advisor.py:451`
- `readiness_status(config: BRConfig, issue_id: str) -> ReadinessStatus | None` — `check_readiness.py:55`, already called at `issue_manager.py:805`; no signature change needed. `ReadinessStatus` has no dedicated "gap analysis" field — the context to pass is assembled from `status.confidence`/`status.readiness_threshold`/`status.raw_confidence` plus the already-built `gate_message`/`gate_reason` strings (`issue_manager.py:807-818`).

### Call Path
`issue_manager.py:process_issue_inplace()` gate block (lines 801-830) → `should_consult("confidence_gate", config)` (`advisor.py:408`, new call, `manual` defaults to `False`) → if `True`: `consult_for_trigger("confidence_gate", question=gate_message, context=<gap analysis built from status.confidence/status.readiness_threshold/status.raw_confidence/gate_reason>, config=config)` (`advisor.py:451`, new call) → internally re-checks `should_consult` (`advisor.py:477`) → `record_consult(task_key)` → `consult(...)` (`advisor.py:183`) → returns `ConsultOutcome` → existing `return _stamped_result(..., was_gated=True, failure_reason=gate_reason)` (`issue_manager.py:830`) is reached unconditionally, regardless of `outcome.verdict`/`outcome.skipped_reason`.

### Decision Rules
N/A — no new decision logic. This issue calls two existing, already-tested gating functions (`should_consult`/`consult_for_trigger`) with the existing `"confidence_gate"` trigger name; it introduces no new gap kind, threshold, keyword list, or classification rule of its own.

## Impact

- **Priority**: P3 — matches parent FEAT-3038.
- **Effort**: Small — one call site, one branch; the hard budget/identity work
  is already available from FEAT-3116.
- **Risk**: Medium — adds a synchronous network call to a hot gating path;
  mitigated by fail-soft semantics and off-by-default triggers (unchanged from
  parent's risk assessment).
- **Breaking Change**: No — inert unless `advisor.triggers` lists
  `confidence_gate`.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1 (pair LLM judgment with a
  non-LLM signal).

## Status

**Open** | Created: 2026-08-08 | Priority: P3


## Verification Notes

### 2026-08-12 (`/ll:verify-issues`)

The `issue_manager.py` line citation for the pre-Phase-1 confidence gate had drifted from `:788-816` to `:808-833` — confirmed by grep (the sub-threshold branch now starts at the `action = config.get_category_action(...)` guard on `:807`/`:808` and returns at `:833`). Both citations in this issue (Current Behavior, Proposed Solution) were updated. The gate's shape and behavior are unchanged; only the line range moved.

### 2026-08-23 (manual staleness pass)

Leftover `verify_verdict: NON_VALID` frontmatter (stale since the 2026-08-12 anchor fix above) reset to `VALID`. Gate anchor re-confirmed: `CONFIDENCE_GATE_BLOCKED` prints at `issue_manager.py:817`, within the cited `:808-833` span. This issue already routes through `consult_for_trigger` and is unaffected by the consult()-exclusivity contract settled today (see FEAT-3116).

## Session Log
- `/ll:confidence-check` - 2026-08-23T23:26:11 - `fd937648-60a8-4f04-9d18-902b8ed3e35c.jsonl`
- `/ll:wire-issue` - 2026-08-23T23:18:09 - `f59dd85f-2874-4175-8e19-14065db141ec.jsonl`
- `/ll:refine-issue` - 2026-08-23T23:07:25 - `3925a429-4d69-4fac-9476-7e210db838ca.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:08:33 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:51:42 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:issue-size-review` - 2026-08-08T21:18:49 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`
