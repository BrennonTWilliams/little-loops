---
id: ENH-3222
type: ENH
title: Validator rule for judged gates with no abstention route and no error route
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:28:45Z'
parent: EPIC-3217
---

# ENH-3222: Validator rule for judged gates with no abstention route and no error route

## Summary

`ll-loop validate` has no rule covering the condition that terminates a run on abstention: an LLM-judged gate declaring neither `on_cannot_judge` nor `on_error`. The condition is entirely statically detectable, and it currently holds for 13 gates across the built-in loops.

## Current Behavior

`scripts/little_loops/fsm/validation/` contains no reference to `cannot_judge` or abstention. The MR-1..MR-14 rule set predates ENH-3185.

A loop author writing a `check_semantic` gate with `on_yes`/`on_no` and no error route gets a clean validate, and the abstention run-termination surfaces only at runtime, after `_ABSTENTION_HOLD_CAP = 2` holds have re-run the state's action twice.

## Expected Behavior

`ll-loop validate` emits a diagnostic for any state whose evaluator can produce the full verdict grammar (`evaluate.type: llm_structured`, and states resolving to it via the `llm_gate` fragment) when the state declares neither a `cannot_judge` route — `on_cannot_judge` or a `cannot_judge` key in `route:` — nor an error route (`on_error` or `route.error`).

The message should name the runtime consequence ("abstention terminates the run via 'No valid transition' after N holds") rather than just the missing key, matching the explanatory style of the existing MR-8 evidence-contract warning.

## Motivation

The sibling issues in this EPIC fix the 13 known instances. Without a rule, the next judged gate someone writes reintroduces the shape — and the failure only appears in production runs, at the cost of two re-executions of the gate's action.

## Proposed Solution

Add the rule to `scripts/little_loops/fsm/validation/`. Two decisions for the implementer:

**Severity.** WARNING is the safer default: ERROR would fail `ll-loop validate` on 13 shipped loops until the sibling issues land, and would break any consuming project's existing loops on upgrade. If ERROR is wanted eventually, sequence it after the retrofit.

**Detection scope.** Resolving `llm_gate`-fragment states requires fragment expansion; confirm whether the validation pass runs pre- or post-expansion and detect accordingly, since two of the affected gates (`learning-tests-audit`, `migrate-sdk-version`) reach `llm_structured` only through the fragment. Note that `fsm/validation`'s MR-8 lint operates on FSM YAML `evaluate.prompt` text only — this rule operates on routing keys, so it is a structural rule rather than an evaluator-prompt rule and belongs with the structural rules accordingly.

Per project policy, enforce via the local pytest suite; no hosted CI.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/fsm/validation/structural_rules.py` — houses `validate_fsm()`'s dispatch sequence (~lines 909-1115, a flat list of `errors.extend(_validate_XXX(fsm))` calls); the new rule's function and its dispatch call belong here per the issue's own instruction that this is a structural (routing-key) rule, not an evaluator-prompt rule
- `scripts/little_loops/fsm/validation/_base.py` — `KNOWN_TOP_LEVEL_KEYS` (lines 79-140) needs an entry for a new suppression flag (following `partial_route_ok`, `evidence_contract_ok`); `_is_llm_judged()` (lines 167-183) is the existing predicate to reuse for judged-gate detection
- `scripts/little_loops/fsm/validation/__init__.py` — re-export wiring: new rule function added to the import block (lines 62-153) and `__all__` (lines 156-259), per this package's convention of re-exporting every rule for test access
- `scripts/little_loops/fsm/schema.py` — `FSMLoop` needs the new boolean suppression-flag field (mirrors `partial_route_ok`/`evidence_contract_ok`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_exact_route_declared()` (2681-2686), `_abstention_declared()` (2660-2679), `_abstention_fallback()` (2688-2700), `_ABSTENTION_HOLD_CAP = 2` (2658) are the authoritative runtime semantics this static rule must mirror; the fallback never uses `route.default`/implicit `on_no` (explicit comment, 2691-2693), so a `None` return from routing dead-ends the loop — this is the consequence the new message should name
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` (14-94) surfaces WARNING vs ERROR differently: WARNING-only violations don't raise `ValueError`, don't flip `valid` to `false` in `--json` mode, and don't change `ll-loop validate`'s exit code (`has_errors` check at line 73, exit code at line 84) — confirms WARNING severity is low-blast-radius for the 13 currently-affected loops

### Conventions in Force
- New MR-style rule functions take `fsm: FSMLoop`, return `list[ValidationError]`, and are guarded by an early suppression-flag return — evidence: `_validate_partial_route_dead_end` (`meta_rules.py:224-265`, `if fsm.partial_route_ok: return []`), `_validate_llm_evidence_contract` (`evaluator_rules.py:478-517`, `if fsm.evidence_contract_ok: return []`)
- Diagnostic messages follow a fixed shape: `[state: {name}] <condition>; <runtime consequence stated as fact>. <remediation>. Set \`<flag>_ok: true\` to suppress. (<issue-id>)` — evidence: `meta_rules.py:251-264`, `evaluator_rules.py:503-516`
- Rule placement by subject matter is not unified by file name: MR-4 (`_validate_partial_route_dead_end`) is the closest existing analog in subject matter (LLM-judged-state routing gaps) and operates on routing keys, yet it is filed in `meta_rules.py`, not `structural_rules.py` — both filings exist as precedent, so where exactly this new rule lands is not fully dictated by the "structural rule" label alone
- Suppression flags require both a `schema.py` `FSMLoop` field and a `_base.py` `KNOWN_TOP_LEVEL_KEYS` entry, or `load_and_validate()`'s unknown-top-level-key check will itself warn on the new flag
- Fragment expansion happens before `validate_fsm()` runs: `load_and_validate()` calls `resolve_fragments()` (~line 1650) then `FSMLoop.from_dict()` (~line 1653) then `validate_fsm(fsm)` (~line 1661) — confirmed via `common.yaml`'s `llm_gate` fragment (lines 47-72), which sets `evaluate.type: llm_structured` directly in the fragment body, so `learning-tests-audit.yaml`/`migrate-sdk-version.yaml`'s fragment-based gates are already resolved to `llm_structured` StateConfig objects by the time any `_validate_*(fsm)` rule runs — no fragment-aware logic is needed in the new rule
- Tests follow a fixed per-rule shape: `_simple_fsm()`/`make_state()` builders, no YAML fixtures; `test_mrN_fires_for_X` / `test_mrN_does_not_fire_when_X` / `test_mrN_suppressed_by_flag` / `test_mrN_fires_end_to_end_via_validate_fsm` — evidence: `TestLLMEvidenceContractValidation` (`test_fsm_validation_evaluator_rules.py:260-403`)

### Tests
- `scripts/tests/test_fsm_validation_evaluator_rules.py` — `TestLLMEvidenceContractValidation` (260-403) is the model test class to follow
- `scripts/tests/test_builtin_loops.py` — validates all built-in loops; will surface the new rule firing on the 13 currently-affected gates until the sibling BUG-3226/3227/3228 retrofits land

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` § The Design Rules — MR-1..MR-14 table; whether this rule gets an MR number is an open question since it applies to any judged gate, not just meta-loops (the existing MR series is meta-loop/harness-optimization scoped per the package docstring)
- `docs/reference/API.md` `little_loops.fsm.validation` section

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Types
N/A — no new data type. The rule reuses `ValidationError`/`ValidationSeverity` (`scripts/little_loops/fsm/validation/_base.py:15-41`).

### Signatures
- `_validate_<name>(fsm: FSMLoop) -> list[ValidationError]` — new rule function following the MR-4/MR-8 shape; see `meta_rules.py:224-265` and `evaluator_rules.py:478-517`
- `_is_llm_judged(state) -> bool` — existing judged-gate predicate to reuse; `validation/_base.py:167-183`, checks `state.evaluate.type in ("llm_structured", "check_semantic")` or prompt/slash_command action heuristics

Detection reads already-parsed `StateConfig` fields (`schema.py:656,659,689`) and `RouteConfig` fields (`schema.py:230-263`): `state.route`, `state.extra_routes`, `state.on_error`, `RouteConfig.routes`, `RouteConfig.error`.

### Call Path
`load_and_validate()` (`structural_rules.py`) → `resolve_fragments()` (pre-parse, ~line 1650) → `FSMLoop.from_dict()` (post-expansion parse, ~line 1653) → `validate_fsm(fsm)` (~line 1661) → new rule dispatched via `errors.extend(_validate_<name>(fsm))` alongside existing MR-4/MR-8 calls → per state: `_is_llm_judged(state)` filter → check `"cannot_judge" not in state.extra_routes and (state.route is None or "cannot_judge" not in state.route.routes)` AND `state.on_error is None and (state.route is None or state.route.error is None)` → `ValidationError(severity=WARNING, path=f"states.{state_name}")` appended → surfaced via `cmd_validate()` (`cli/loop/config_cmds.py:14-94`) as a non-exit-code-flipping warning in both text and `--json` output

### Decision Rules
- New gap kind: a WARNING-severity diagnostic fires when BOTH conditions hold for an LLM-judged state: no cannot_judge route declared (neither `state.extra_routes["cannot_judge"]` nor `state.route.routes["cannot_judge"]`) AND no error route declared (neither `state.on_error` nor `state.route.error`)
- Exact inputs: state must satisfy `_is_llm_judged(state)`; detection runs post-fragment-expansion, so `llm_gate`-fragment states are already resolved to `evaluate.type == "llm_structured"` by the time this rule runs — no separate fragment-aware branch needed
- Escape hatch: a new top-level suppression flag (exact name is an implementer decision, following the `partial_route_ok`/`evidence_contract_ok` naming convention) set to `true` at the loop level skips the rule for that loop; must be registered in both `schema.py` (`FSMLoop` field) and `validation/_base.py`'s `KNOWN_TOP_LEVEL_KEYS`, or the flag itself triggers an "unknown top-level key" warning
- Severity: WARNING (per the issue's own Proposed Solution) — confirmed low-blast-radius by `cmd_validate()`'s severity handling: WARNING-only violations don't raise `ValueError`, don't flip `valid` to `false` in `--json` mode, and don't change `ll-loop validate`'s exit code

## Implementation Steps

1. A new validation rule fires a WARNING-severity `ValidationError` for any LLM-judged state (`_is_llm_judged()`, `scripts/little_loops/fsm/validation/_base.py:167-183`) that declares neither a `cannot_judge` route (`state.extra_routes`/`state.route.routes`) nor an error route (`state.on_error`/`state.route.error`); the message names the runtime consequence, citing `_ABSTENTION_HOLD_CAP = 2` (`executor.py:2658`) and `_abstention_fallback()`'s dead-end behavior (`executor.py:2688-2700`)
2. The rule is dispatched from `validate_fsm()` (`structural_rules.py`) and exercises cleanly against the 13 currently-affected built-in loops without flipping `ll-loop validate`'s exit code (WARNING-only, per `cmd_validate()`'s severity handling, `cli/loop/config_cmds.py:14-94`)
3. A suppression flag, registered in both `FSMLoop` (`schema.py`) and `KNOWN_TOP_LEVEL_KEYS` (`validation/_base.py:79-140`), lets an intentional case opt out
4. Tests follow the `TestLLMEvidenceContractValidation` shape (`test_fsm_validation_evaluator_rules.py:260-403`): fires / does-not-fire / suppressed-by-flag / fires-end-to-end-via-`validate_fsm` cases
5. `python -m pytest scripts/tests/test_fsm_validation_evaluator_rules.py scripts/tests/test_fsm_validation_structural.py scripts/tests/test_builtin_loops.py -v` passes

## Impact

Prevents recurrence of the 13-gate defect class. Adds one warning per affected loop until the retrofit lands.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.validation` section — existing
  MR-4/MR-8/MR-14 rule patterns to model the new rule after

## Status

**Open** | Created: 2026-08-16 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-17T06:06:13 - `86eb12f1-b126-4db7-a22d-252ffa585d1f.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
