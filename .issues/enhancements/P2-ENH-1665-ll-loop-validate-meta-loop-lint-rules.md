---
id: ENH-1665
type: ENH
status: done
priority: P2
discovered_date: 2026-05-23
completed_at: 2026-05-24T09:45:41Z
discovered_by: manual
labels:
- validation
- loops
- meta-loop
- harness
- shor
- lint
- ll-loop
parent: EPIC-1663
relates_to:
- ENH-1664
- ENH-1666
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1665: `ll-loop validate` meta-loop lint rules (MR-1 ERROR, MR-2 WARNING)

## Summary

Add two new validator checks to `scripts/little_loops/fsm/validation.py` that
fire when a loop is detected as a meta-loop (it writes other harness
artifacts) and either lacks a non-LLM evaluator (MR-1, ERROR) or lacks a
measure→propose→apply→re-measure spine (MR-2, WARNING).

This is the highest-leverage layer of EPIC-1663 — the only one humans and
LLMs can't forget to apply.

## Current Behavior

`ll-loop validate` performs structural and semantic checks on FSM loop YAML
files but has no rules specific to meta-loops — loops that write harness
artifacts (other loop YAML files, skills, agents, commands, or project
config). A meta-loop that grades its own harness updates using only LLM
evaluators passes validation without any warning, even though such
self-evaluation has 33–55% accuracy (SHOR Table 1).

## Expected Behavior

`ll-loop validate` fires two new checks on any loop classified as a
meta-loop by the detector heuristic:

- **MR-1 (ERROR)**: blocks validation when no `evaluate:` block in any state
  uses a non-LLM evaluator type (`exit_code`, `output_numeric`,
  `output_json`, `output_contains`, `convergence`, `diff_stall`,
  `harbor_scorer`, `mcp_result`).
- **MR-2 (WARNING)**: warns when no captured baseline value is referenced by
  a later evaluator (no measure→propose→apply→re-measure spine).

Both rules are suppressed by setting `meta_self_eval_ok: true` at the loop
top-level. The `FSMLoop` schema exposes this as a boolean field (default
`false`). `harness-optimize.yaml` continues to pass as a positive control.

## Motivation

SHOR Table 1 shows current SOTA optimizers self-evaluate their own harness
updates at 33–55% accuracy. The validator is the right place to enforce that
meta-loops carry at least one non-LLM gate because:

- `loop-specialist` already names this failure mode post-hoc; the validator
  prevents it pre-hoc.
- The CLAUDE.md rule (ENH-1664) and wizard refusal (ENH-1666) both depend on
  this check existing — the wizard generates YAML that satisfies it, and
  CLAUDE.md cites it.
- WARNING severity is insufficient — warnings get filtered out in any CI
  with volume. MR-1 fires as ERROR with a grep-able opt-out flag.

## Detector Heuristic

A loop is classified as **meta** if ANY of the following match:

1. Any `state.action` string matches one of these regexes:
   - `loops/[\w-]+\.yaml` (writes another loop YAML)
   - `skills/[\w-]+/SKILL\.md` (writes a skill definition)
   - `agents/[\w-]+\.md` (writes an agent definition)
   - `commands/[\w-]+\.md` (writes a command definition)
   - `\.claude/(CLAUDE\.md|settings)` (writes project config)
2. The loop's top-level `import:` list contains `lib/benchmark.yaml`
3. Any `state.action` references `yaml_state_editor` or `replace_action`

The heuristic was sanity-checked against the existing 80+ loops in
`scripts/little_loops/loops/` — it matches exactly `harness-optimize.yaml`
and `loop-specialist-eval.yaml`, the two known meta-loops, and nothing else.

## Rule MR-1: Meta-loop must have non-LLM evaluator (ERROR)

**Trigger**: Detector matches AND no state in the loop has an `evaluate:`
block whose `type` is one of: `exit_code`, `output_numeric`, `output_json`,
`output_contains`, `convergence`, `diff_stall`, `harbor_scorer`, or
`mcp_result`.

**Message**:
```
Loop modifies harness artifacts but has no non-LLM evaluator. LLM self-grades
on harness updates are unreliable (SHOR Table 1: 33–55% accuracy). Pair every
check_semantic state with at least one of: exit_code, output_numeric,
convergence, diff_stall, mcp_result. To suppress with justification, set
`meta_self_eval_ok: true` at the loop top-level.
```

**Severity**: ERROR (blocks validation)

**Escape hatch**: Top-level YAML field `meta_self_eval_ok: true` suppresses
MR-1. Flag-only — no reason field required (comments rot; the flag itself
is grep-able). Add a `meta_self_eval_ok: bool` field to `FSMLoop` in
`scripts/little_loops/fsm/schema.py`.

## Rule MR-2: Meta-loop should have measure-then-act spine (WARNING)

**Trigger**: Detector matches AND no `state.capture` name (e.g., `baseline`,
`baseline_score`, `prev_score`) appears as a source in a later state's
`evaluate.previous`, `evaluate.target`, or numeric comparison. In other
words: the loop modifies a harness artifact but never captures a measurable
baseline before the modification.

**Message**:
```
Meta-loop appears to lack a measure→propose→apply→re-measure spine: no
captured baseline value is referenced by a later evaluator. Meta-loops
should compare a post-change score against a pre-change baseline (see
loops/harness-optimize.yaml as reference template). To suppress, set
`meta_self_eval_ok: true`.
```

**Severity**: WARNING (does not block validation)

**Escape hatch**: Same `meta_self_eval_ok: true` flag suppresses both MR-1
and MR-2.

## Implementation Steps

1. **`scripts/little_loops/fsm/schema.py`**: Add `meta_self_eval_ok: bool = False`
   field to `FSMLoop` dataclass.
2. **`scripts/little_loops/fsm/validation.py`**: Add module-level constants
   for the detector regexes. Add helper `_is_meta_loop(fsm: FSMLoop) -> bool`.
   Add `_validate_meta_loop_evaluation(fsm: FSMLoop) -> list[ValidationError]`
   implementing MR-1 + MR-2. Wire into `validate_fsm` at line 686. Guard the
   whole function on `not fsm.meta_self_eval_ok`.
3. **`scripts/tests/test_fsm_validation.py`** (or equivalent): Add test cases:
   - `harness-optimize.yaml` validates clean (positive control — has external scorer)
   - Synthetic fixture `meta-loop-llm-only.yaml` triggers MR-1
   - Synthetic fixture `meta-loop-no-baseline.yaml` triggers MR-2 (not MR-1)
   - Same fixtures with `meta_self_eval_ok: true` validate clean
   - Non-meta loop with only `llm_structured` evaluator does NOT trigger either rule
4. **`scripts/little_loops/loops/loop-specialist-eval.yaml`**: Audit — if it
   currently fails MR-1, either add a non-LLM gate or set
   `meta_self_eval_ok: true` with a comment justifying the exception.
5. **`docs/reference/SCHEMA.md`** or `docs/guides/LOOPS_GUIDE.md`: Document
   `meta_self_eval_ok` field and MR-1/MR-2 rules.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — `schema.py` additions (three touch points, not one):**
- `FSMLoop` dataclass at line 885: append `meta_self_eval_ok: bool = False` after `circuit`
- `FSMLoop.from_dict` at line ~946: add `meta_self_eval_ok=data.get("meta_self_eval_ok", False)` following the `maintain=data.get("maintain", False)` pattern
- `FSMLoop.to_dict` at lines 887–943: add `if self.meta_self_eval_ok: result["meta_self_eval_ok"] = self.meta_self_eval_ok` following the `if self.maintain:` pattern

**Step 2 — `validation.py` additions (three touch points, not two):**
- `KNOWN_TOP_LEVEL_KEYS` frozenset (lines 78–108): add `"meta_self_eval_ok"` — omitting this causes a spurious "Unknown top-level keys" warning for any loop that sets the escape hatch
- New functions: `_is_meta_loop()` + `_validate_meta_loop_evaluation()` — model after `_validate_failure_terminal_action` (lines 640–683) for WARNING severity and `_validate_circuit` (lines 830–864) for early-return guard + ERROR severity
- Insertion point: `errors.extend(_validate_meta_loop_evaluation(fsm))` near line 823, **after** `errors.extend(_validate_failure_terminal_action(fsm))`, not at line 686 (which is the function signature)
- The non-LLM evaluator allow-list should derive from `set(EVALUATOR_REQUIRED_FIELDS.keys()) - {"llm_structured"}` (lines 62–72) rather than a hard-coded set, to stay in sync if new evaluator types are added

**Step 3 — test patterns (confirmed):**
- Use `_make_fsm()` factory method + `_write_yaml(tmp_path)` + inline YAML string pattern from `TestCircuitValidation` (lines 588–678 of `test_fsm_validation.py`)
- Use `make_state()` helper (lines 32–34 of `test_fsm_validation.py`) to build `StateConfig` objects
- Assertions use `any(... for e in errors)` scanning messages; filter by `[e for e in errors if e.severity == ValidationSeverity.ERROR]`
- For the harness-optimize positive control: use `load_and_validate(BUILTIN_LOOPS_DIR / "harness-optimize.yaml")` following the pattern in `test_audit_loop_run_skill.py:15` and `test_harness_optimize.py`

**Step 4 — loop-specialist-eval.yaml detector match is UNCERTAIN:**
- Research found that `loop-specialist-eval.yaml` does **not** clearly match any of the three detector conditions as written: its `execute` state writes to `.loops/diagnostics/` (not matching `loops/[\w-]+\.yaml`), it has no `import: lib/benchmark.yaml`, and neither `yaml_state_editor` nor `replace_action` appear in the file
- The issue's claim that the heuristic "matches exactly `harness-optimize.yaml` and `loop-specialist-eval.yaml`" needs verification; it may only match `harness-optimize.yaml` with the current regex set
- If loop-specialist-eval should be classified as meta, add a `.loops/diagnostics/` path pattern to condition 1, or add it to condition 3 allowances — or simply accept it doesn't require MR-1 (its evaluator is `llm_structured` only, but if it doesn't trigger the detector, MR-1 is moot)
- **Recommended**: run `grep -n "action:" scripts/little_loops/loops/loop-specialist-eval.yaml` before step 4 audit to confirm actual content

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Complete step 4 audit of `loop-specialist-eval.yaml` BEFORE running any builtin loop test sweep** — `test_builtin_loops.py:36 test_all_validate_as_valid_fsm()` and `test_fsm_flow.py:324 test_all_builtin_loops_still_load()` call `validate_fsm()` on all builtin loops; either add `meta_self_eval_ok: true` with a comment justifying the exception, or add a non-LLM gate; step 4 is a blocking prerequisite for a green test suite
7. **Add `meta_self_eval_ok` round-trip tests to `test_fsm_schema.py`** — one test asserting key is present in `to_dict()` when `True` (round-trips cleanly), one asserting key is absent when `False` (skip-if-default), following `TestCircuitConfig.test_fsm_loop_with_circuit_round_trip` (line 2724) as the template
8. **Update `docs/reference/API.md`** — add `meta_self_eval_ok: bool = False` to the `FSMLoop` class listing (line 3910); document MR-1 and MR-2 in the `#### validate_fsm` section (line 4504)
9. **Update `docs/reference/CLI.md`** — add MR-1 (ERROR blocks validation) and MR-2 (WARNING, does not block) descriptions to the `ll-loop validate` section (line 422)
10. **Update `skills/review-loop/reference.md`** — add MR-1 and MR-2 to the "First-Pass Checks (from `ll-loop validate`)" section so the `review-loop` skill surfaces them when reviewing meta-loops

## Verification

- `ll-loop validate harness-optimize` passes (positive control)
- `ll-loop validate loop-specialist-eval` either passes or has explicit opt-out
- Each MR-1/MR-2 fixture produces the documented message
- `pytest scripts/tests/test_fsm_validation.py -v` green

## Scope Boundaries

**In scope:**
- Detector function and two validation rules in `validation.py`
- New `meta_self_eval_ok` schema field
- Test fixtures and unit tests
- Schema doc update

**Out of scope:**
- The wizard branch (ENH-1666)
- CLAUDE.md prose (ENH-1664)
- Runtime telemetry (ENH-1667)
- Migrating existing meta-loops beyond the audit step

## Impact

- **Priority**: P2 — this is the gate with teeth; once it lands, ENH-1664
  and ENH-1666 can reference it as enforcement.
- **Effort**: Medium — ~150 LOC validator + ~100 LOC tests + 2 fixtures.
- **Risk**: Low-Medium — heuristic could false-positive on a loop with paths
  that look meta but aren't (e.g., a loop that reads but doesn't write meta
  files). Mitigation: detector only matches `action:` strings (where writes
  happen), not `capture:` or read-only references; escape hatch exists.
- **Breaking Change**: Yes — existing meta-loops that lack non-LLM evaluators
  will fail validation. Mitigation: audit step (4) above; only one known
  candidate (`loop-specialist-eval.yaml`).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `meta_self_eval_ok: bool = False` to `FSMLoop` (line 885); update `from_dict` (line ~946) with `data.get("meta_self_eval_ok", False)`; update `to_dict` (lines 887–943) with skip-if-default pattern `if self.meta_self_eval_ok: result["meta_self_eval_ok"] = ...`
- `scripts/little_loops/fsm/validation.py` — add `"meta_self_eval_ok"` to `KNOWN_TOP_LEVEL_KEYS` frozenset (lines 78–108); add detector constants, `_is_meta_loop()`, `_validate_meta_loop_evaluation()`; wire into `validate_fsm` near line 823 (after `errors.extend(_validate_failure_terminal_action(fsm))`, not at the function start at line 686)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runner.py` — calls `validate_fsm`; no changes needed but affected by new errors
- `scripts/little_loops/loops/loop-specialist-eval.yaml` — known meta-loop candidate; may need `meta_self_eval_ok: true` or a non-LLM gate added

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` is the **primary CLI handler** for `ll-loop validate`; calls `load_and_validate()` directly (line 21); new MR-1 errors surface as `ValueError` caught at line 31 and returned as exit code 1
- `scripts/little_loops/cli/loop/__init__.py` — dispatches to `cmd_validate()` at line 445; `"validate"` and `"val"` registered as known subcommands (lines 39–64)
- `scripts/little_loops/cli/loop/_helpers.py` — `load_loop()` and `load_loop_with_spec()` both call `load_and_validate()`; `cmd_run` callers will see new MR-1 errors at loop startup if a meta-loop lacks an escape hatch
- `scripts/little_loops/fsm/executor.py` — conditionally imports `load_and_validate` at runtime (line 481); same error propagation path

### Similar Patterns
- `scripts/little_loops/fsm/validation.py:32–58` — `ValidationSeverity` / `ValidationError` model; new rules follow the same pattern
- `scripts/little_loops/fsm/validation.py:640–683` — `_validate_failure_terminal_action()`: FSM-level WARNING helper; iterates `fsm.states.items()`, appends `ValidationError(severity=ValidationSeverity.WARNING)`, returns flat list — **closest structural template for `_validate_meta_loop_evaluation()`**
- `scripts/little_loops/fsm/validation.py:830–864` — `_validate_circuit()`: FSM-level ERROR helper with early-return guard `if fsm.circuit is None: return errors`; default severity=ERROR — template for the guard pattern
- Note: `_validate_evaluator_types` does NOT exist; do not reference it

### Tests
- `scripts/tests/test_fsm_validation.py` — add MR-1/MR-2 test cases and fixtures
- New fixture files: `scripts/tests/fixtures/meta-loop-llm-only.yaml`, `scripts/tests/fixtures/meta-loop-no-baseline.yaml`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py` — add `meta_self_eval_ok=True` round-trip test (key present in `to_dict()`) and default-omit test (key absent when `False`) following `TestCircuitConfig.test_fsm_loop_with_circuit_round_trip` pattern (line 2724)
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm()` (line 36) **will break** if any builtin loop triggers MR-1; step 4 audit of `loop-specialist-eval.yaml` must complete before the test suite runs; treat this as a pre-flight checkpoint, not an afterthought
- `scripts/tests/test_fsm_flow.py` — `TestBuiltinLoopRegression.test_all_builtin_loops_still_load()` (line 324) calls `load_and_validate()` on all builtin loops; same break risk as `test_builtin_loops.py`
- `scripts/tests/test_feat1544_loop_specialist_eval.py` — likely asserts `loop-specialist-eval.yaml` validates cleanly; will break if that loop triggers MR-1 without an escape hatch

### Documentation
- `docs/reference/SCHEMA.md` or `docs/guides/LOOPS_GUIDE.md` — document `meta_self_eval_ok` field and MR-1/MR-2 rules

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### FSMLoop` class listing (line 3910) needs `meta_self_eval_ok: bool = False` field entry; `#### validate_fsm` section (line 4504) needs MR-1 and MR-2 documented as named checks
- `docs/reference/CLI.md` — `ll-loop validate` section (line 422) needs MR-1 (ERROR) and MR-2 (WARNING) rule descriptions added

### Skills

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-loop/reference.md` — "First-Pass Checks (from `ll-loop validate`)" section (line 17); add MR-1 (ERROR) and MR-2 (WARNING) to the documented check categories so `review-loop` surfaces them correctly

### Configuration
- N/A

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/fsm/validation.py:686` | `validate_fsm` aggregator — insertion point |
| `scripts/little_loops/fsm/validation.py:32–58` | `ValidationSeverity` / `ValidationError` model |
| `scripts/little_loops/fsm/evaluators.py:1–22` | Evaluator tier list (Tier 1 deterministic = the allow-list) |
| `scripts/little_loops/loops/harness-optimize.yaml` | Positive control — passes MR-1 via `convergence` + scorer |
| `docs/research/Towards-Direct-Evaluation-of-Harness-Optimizers.md` | SHOR Table 1, §3 Analysis III |

## Labels

- validation
- loops
- meta-loop
- harness
- shor
- lint
- ll-loop

---

**Open** | Created: 2026-05-23 | Priority: P2


## Resolution

Implemented MR-1 (ERROR) and MR-2 (WARNING) meta-loop lint rules in `validate_fsm`.

- `scripts/little_loops/fsm/schema.py`: Added `meta_self_eval_ok: bool = False` and `imports: list[str]` fields to `FSMLoop`; updated `to_dict`/`from_dict`.
- `scripts/little_loops/fsm/validation.py`: Added `NON_LLM_EVALUATOR_TYPES`, `_META_LOOP_ACTION_PATTERNS`, `_is_meta_loop()`, `_has_baseline_reference()`, `_validate_meta_loop_evaluation()`; wired into `validate_fsm`; added `meta_self_eval_ok` to `KNOWN_TOP_LEVEL_KEYS`.
- `scripts/little_loops/loops/loop-specialist-eval.yaml`: Added `meta_self_eval_ok: true` with justification (detector false-positive on documentation reference).
- `scripts/tests/test_fsm_validation.py`: Added `TestMetaLoopValidation` (9 tests).
- `scripts/tests/test_fsm_schema.py`: Added `TestMetaSelfEvalOk` (3 round-trip tests).
- `docs/reference/CLI.md`, `docs/reference/API.md`, `skills/review-loop/reference.md`: Documented MR-1/MR-2 rules.

All 7586 tests pass.

## Session Log
- `/ll:ready-issue` - 2026-05-24T09:32:21 - `e3171e5b-9084-48da-b53c-0ca1d126b0a2.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00 - `bfebde01-7bc0-49bc-8e12-d4e6c03d3c1e.jsonl`
- `/ll:wire-issue` - 2026-05-24T08:03:16 - `da66cfd3-43bf-4f9f-ba92-ed5d1b062810.jsonl`
- `/ll:refine-issue` - 2026-05-24T07:55:15 - `23a63ac9-9129-474b-a23b-c63b3d6b122b.jsonl`
- `/ll:format-issue` - 2026-05-24T07:51:05 - `de7ac99b-79b2-4768-a911-b63a81fb1c58.jsonl`
