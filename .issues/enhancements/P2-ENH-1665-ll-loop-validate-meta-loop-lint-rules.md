---
id: ENH-1665
type: ENH
status: open
priority: P2
discovered_date: 2026-05-23
discovered_by: manual
labels: [validation, loops, meta-loop, harness, shor, lint, ll-loop]
parent: EPIC-1663
relates_to: [ENH-1664, ENH-1666]
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
- `scripts/little_loops/fsm/schema.py` — add `meta_self_eval_ok: bool = False` to `FSMLoop`
- `scripts/little_loops/fsm/validation.py` — add detector constants, `_is_meta_loop()`, `_validate_meta_loop_evaluation()`, wire into `validate_fsm` at line 686

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runner.py` — calls `validate_fsm`; no changes needed but affected by new errors
- `scripts/little_loops/loops/loop-specialist-eval.yaml` — known meta-loop candidate; may need `meta_self_eval_ok: true` or a non-LLM gate added

### Similar Patterns
- `scripts/little_loops/fsm/validation.py:32–58` — `ValidationSeverity` / `ValidationError` model; new rules follow the same pattern
- Existing rule functions in `validation.py` (e.g., `_validate_evaluator_types`) as structural templates

### Tests
- `scripts/tests/test_fsm_validation.py` — add MR-1/MR-2 test cases and fixtures
- New fixture files: `scripts/tests/fixtures/meta-loop-llm-only.yaml`, `scripts/tests/fixtures/meta-loop-no-baseline.yaml`

### Documentation
- `docs/reference/SCHEMA.md` or `docs/guides/LOOPS_GUIDE.md` — document `meta_self_eval_ok` field and MR-1/MR-2 rules

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


## Session Log
- `/ll:format-issue` - 2026-05-24T07:51:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de7ac99b-79b2-4768-a911-b63a81fb1c58.jsonl`
