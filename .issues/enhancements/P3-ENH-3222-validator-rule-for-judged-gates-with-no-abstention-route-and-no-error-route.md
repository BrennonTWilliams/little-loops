---
id: ENH-3222
type: ENH
title: Validator rule for judged gates with no abstention route and no error route
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:28:45Z'
completed_at: '2026-08-17T17:15:33Z'
parent: EPIC-3217
decision_needed: false
testable: true
confidence_score: 96
outcome_confidence: 93
score_complexity: 23
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 23
---

# ENH-3222: Validator rule for judged gates with no abstention route and no error route

## Summary

`ll-loop validate` has no rule covering the condition that terminates a run on abstention: an abstention-capable gate declaring neither `on_cannot_judge` nor `on_error`. The condition is entirely statically detectable.

**The detection scope drove this issue and is now decided: narrow scope, WARNING severity** — see [Decision: Detection Scope](#decision-detection-scope). Measured against the 103 non-`lib/` built-in loop files post-fragment-expansion, the narrow reading fires **0** times and the broad reading fires **199** times across **66 of 103** loop files. The original "13 gates" figure is obsolete: BUG-3226 (11 gates / 9 files), BUG-3227 (2 gates), and BUG-3228 are all `done`, and every explicit `llm_structured` state in the repo now carries a `cannot_judge` or error route.

## Current Behavior

`scripts/little_loops/fsm/validation/` contains no reference to `cannot_judge` or abstention. The MR-1..MR-14 rule set predates ENH-3185.

A loop author writing a judged gate with `on_yes`/`on_no` and no error route gets a clean validate, and the abstention run-termination surfaces only at runtime, after `_ABSTENTION_HOLD_CAP = 2` holds have re-run the state's action twice.

## Expected Behavior

`ll-loop validate` emits a diagnostic for any **abstention-capable** state that declares neither a `cannot_judge` route — `on_cannot_judge` or a `cannot_judge` key in `route:` — nor an error route (`on_error` or `route.error`).

"Abstention-capable" is not a synonym for "LLM-judged" and must not be implemented as one — see [Predicate: abstention-capable, not LLM-judged](#predicate-abstention-capable-not-llm-judged).

The message should name the runtime consequence ("abstention terminates the run via 'No valid transition' after N holds") rather than just the missing key, matching the explanatory style of the existing MR-8 evidence-contract warning.

## Motivation

The sibling issues in this EPIC fixed the known explicit-`llm_structured` instances. Without a rule, the next judged gate someone writes reintroduces the shape — and the failure only appears in production runs, at the cost of two re-executions of the gate's action.

## Decision: Detection Scope

**DECIDED 2026-08-17: narrow scope, WARNING severity.** Rationale in the severity
subsection below; the measurement that backs it is reproduced verbatim below and was
re-confirmed on 2026-08-17 against the current corpus (103 non-`lib/` loop files:
narrow 0, broad 199 / 66 files, `route.default` rescues none of the 199).

_Measured 2026-08-17 by instrumenting the proposed predicate against every non-`lib/` loop under `scripts/little_loops/loops/`, loaded via `load_and_validate()` so fragments are expanded._

| Scope | Predicate | Gates firing | Loop files affected |
|---|---|---|---|
| **Narrow** | `state.evaluate.type == "llm_structured"` (incl. `llm_gate`-fragment states) | **0** of 38 such states | 0 |
| **Broad** | `_is_llm_judged(state)` — adds implicit-judge prompt states with no `evaluate:` block | **199** | **66 of 103** |

Both readings appear in this issue's own text: the original Expected Behavior described the narrow one, the original Program Design specified `_is_llm_judged()` (broad). They are not interchangeable.

**The 199 broad hits are genuine, not false positives.** `executor.py:2593` routes any prompt-mode state with no `evaluate:` block through `evaluate_llm_structured()` with `DEFAULT_LLM_SCHEMA`, which carries the full `cannot_judge` grammar (`fsm/verdicts.py:16`). Those states really can abstain and really do dead-end.

**Severity inverts with scope**, which is why the original "WARNING is the safer default" reasoning no longer holds — it was calibrated for 13 hits:

- Narrow scope: ERROR *looks* free — zero built-in loops violate it. **It is not.** `load_and_validate()` raises `ValueError` on any ERROR (`structural_rules.py:1676-1678`), and `ll-loop run` loads through that same entry point (`cli/loop/_helpers.py:1423,1447`). An ERROR therefore makes a violating loop **unrunnable**, not merely noisy — and the zero-violation measurement covers *built-in* loops only. Every consuming project's own loops are unmeasured, so ERROR risks hard-breaking working loops on upgrade with no warning period. This is the argument that settles the severity call.
- Broad scope: even WARNING is too loud. 199 diagnostics across 58% of built-in loops bury the existing MR-8 and MR-12 warnings, and every consuming project's loops light up on upgrade with no retrofit path staged.

**Decision — two-tier, ship tier 1 here:**

1. **This issue:** **WARNING** on the narrow set — explicit `evaluate.type: llm_structured` and fragment-resolved equivalents, i.e. gates where the author opted into the judge deliberately. Zero current violations, so `test_builtin_loops.py` stays green on landing, and consuming projects get a diagnostic rather than a broken `ll-loop run`. Escalation to ERROR is a deliberate follow-up, taken once the out-of-repo corpus is known clean — not a call to make here.
2. **Separate follow-up issue:** the implicit-prompt-state population. It needs its own counting pass, its own retrofit plan for the 199, and its own severity call — it is a backlog of real defects, not a lint-rule detail, and folding it in here would block this rule indefinitely.

An implementer choosing broad scope instead must pair it with the retrofit, not ship the warnings bare.

## Predicate: abstention-capable, not LLM-judged

**ENH-3224 has landed (`status: done`) — the flag is real and named.** It is
`abstain_on_exit_3`, a **per-state field on `evaluate:`** (`schema.py:113`, documented
at `schema.py:65-67`, consumed at `evaluators.py:2048`) — *not* a loop-level flag.
`_is_llm_judged()` — purely about *LLM* judging — therefore no longer identifies the set
of abstention-capable gates. An `evaluate: {type: exit_code, abstain_on_exit_3: true}`
state with no `on_cannot_judge` is exactly the defect this rule exists to catch.

Write the predicate as **abstention-capable**:

```python
_is_llm_judged(state)  # subject to the scope decision above
or (
    state.evaluate is not None
    and state.evaluate.type == "exit_code"
    and state.evaluate.abstain_on_exit_3
)
```

No sequencing constraint remains — ENH-3224 is done, so write this arm directly rather
than leaving a seam. Zero built-in loops currently set `abstain_on_exit_3`, so this arm
adds no diagnostics today; it exists so the first author who uses the flag is covered.

**`uncertain_suffix` is NOT a third arm.** It looks like one, but it applies only to
`llm_structured` evaluation (`executor.py:2057`; threaded only through
`evaluate_llm_structured` at `evaluators.py:2048`), so any state it affects is already
caught by the `_is_llm_judged()` arm. No branch needed — noted here so it need not be
re-derived.

**Also note:** `_is_llm_judged()` tests `state.evaluate.type in ("llm_structured", "check_semantic")` (`validation/_base.py:183`), but `check_semantic` is **not** a member of `EvaluateConfig.type`'s `Literal` (`schema.py:86-100`) — that branch is dead and cannot match a loadable loop. Earlier revisions of this issue cited `check_semantic` as live coverage in several places; do not rely on it, and consider deleting the dead branch as a drive-by.

## Declared-route check: mirror `_exact_route_declared` exactly

The "has a cannot_judge route" test must be the literal-key lookup the runtime uses
(`executor.py:2681-2686`): `"cannot_judge" in state.extra_routes` or
`state.route.routes`. Two asymmetries make the obvious "helpful" generalizations wrong:

- **Do not accept `route.default` or an implicit `on_no`.** `_abstention_fallback()`
  never consults either (explicit comment, `executor.py:2691-2693`), so a state with a
  `default:` still dead-ends. Confirmed empirically: none of the 199 broad-scope hits are
  rescued by `route.default`.
- **Do not accept `cannot_judge_uncertain` as satisfying `cannot_judge`.** BUG-3228's
  fallback is **one-directional**: a declared base `cannot_judge` covers the
  `_uncertain`-suffixed verdict (`_abstention_declared`, `executor.py:2672-2678`), but
  the reverse is not true. A state declaring only `on_cannot_judge_uncertain` still
  dead-ends on a bare `cannot_judge` and **must still fire**. Match the base key only.

## Overlap with MR-4 is expected and acceptable

A state with `on_yes` only, no `next:`/`route:`, and no error route satisfies both
MR-4 (`_validate_partial_route_dead_end`, `meta_rules.py:224-265`) and this rule; both
diagnostics fire. They report different defects — MR-4 covers an unrouted `no`/`partial`
verdict, this rule covers an unrouted abstention — so the duplication is informative, not
a bug. Zero states in the current corpus hit both (measured), but the shape is reachable.
**Do not write a test asserting exactly one diagnostic for such a state.**

## Proposed Solution

Add the rule to `scripts/little_loops/fsm/validation/`, at narrow scope and WARNING severity per [Decision: Detection Scope](#decision-detection-scope), with the predicate written per [Predicate: abstention-capable, not LLM-judged](#predicate-abstention-capable-not-llm-judged).

Note that `fsm/validation`'s MR-8 lint operates on FSM YAML `evaluate.prompt` text only — this rule operates on routing keys, so it is a structural rule rather than an evaluator-prompt rule and belongs with the structural rules accordingly.

Fragment expansion is **confirmed** to precede `validate_fsm()` (verified 2026-08-17 by instrumented run: `llm_gate`-fragment states resolve to `evaluate.type == "llm_structured"` with no fragment-aware logic in the rule). The original open question about pre- vs post-expansion is closed.

Per project policy, enforce via the local pytest suite; no hosted CI.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/fsm/validation/structural_rules.py` — houses `validate_fsm()`'s dispatch sequence (~lines 909-1115, a flat list of `errors.extend(_validate_XXX(fsm))` calls); the new rule's function and its dispatch call belong here per the issue's own instruction that this is a structural (routing-key) rule, not an evaluator-prompt rule
- `scripts/little_loops/fsm/validation/_base.py` — `KNOWN_TOP_LEVEL_KEYS` (lines 79-140) needs an entry for a new suppression flag (following `partial_route_ok`, `evidence_contract_ok`); `_is_llm_judged()` (lines 167-183) is the existing predicate to reuse for judged-gate detection
- `scripts/little_loops/fsm/validation/__init__.py` — re-export wiring: new rule function added to the import block (lines 62-153) and `__all__` (lines 156-259), per this package's convention of re-exporting every rule for test access
- `scripts/little_loops/fsm/schema.py` — `FSMLoop` needs the new boolean suppression-flag field (mirrors `partial_route_ok`/`evidence_contract_ok`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_exact_route_declared()` (2681-2686), `_abstention_declared()` (2660-2679), `_abstention_fallback()` (2688-2700), `_ABSTENTION_HOLD_CAP = 2` (2658) are the authoritative runtime semantics this static rule must mirror; the fallback never uses `route.default`/implicit `on_no` (explicit comment, 2691-2693), so a `None` return from routing dead-ends the loop — this is the consequence the new message should name
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` (14-94) surfaces WARNING vs ERROR differently: WARNING-only violations don't raise `ValueError`, don't flip `valid` to `false` in `--json` mode, and don't change `ll-loop validate`'s exit code (`has_errors` check at line 73, exit code at line 84) — confirms WARNING severity is low-blast-radius
- `scripts/little_loops/cli/loop/_helpers.py` — lines 1423/1447 load loops for `ll-loop run` through `load_and_validate`, which raises `ValueError` on any ERROR (`structural_rules.py:1676-1678`); this is why the severity decision is WARNING, not ERROR

### Conventions in Force
- New MR-style rule functions take `fsm: FSMLoop`, return `list[ValidationError]`, and are guarded by an early suppression-flag return — evidence: `_validate_partial_route_dead_end` (`meta_rules.py:224-265`, `if fsm.partial_route_ok: return []`), `_validate_llm_evidence_contract` (`evaluator_rules.py:478-517`, `if fsm.evidence_contract_ok: return []`)
- Diagnostic messages follow a fixed shape: `[state: {name}] <condition>; <runtime consequence stated as fact>. <remediation>. Set \`<flag>_ok: true\` to suppress. (<issue-id>)` — evidence: `meta_rules.py:251-264`, `evaluator_rules.py:503-516`
- Rule placement by subject matter is not unified by file name: MR-4 (`_validate_partial_route_dead_end`) is the closest existing analog in subject matter (LLM-judged-state routing gaps) and operates on routing keys, yet it is filed in `meta_rules.py`, not `structural_rules.py` — both filings exist as precedent, so where exactly this new rule lands is not fully dictated by the "structural rule" label alone
- Suppression flags require both a `schema.py` `FSMLoop` field and a `_base.py` `KNOWN_TOP_LEVEL_KEYS` entry, or `load_and_validate()`'s unknown-top-level-key check will itself warn on the new flag
- Fragment expansion happens before `validate_fsm()` runs: `load_and_validate()` calls `resolve_fragments()` (~line 1650) then `FSMLoop.from_dict()` (~line 1653) then `validate_fsm(fsm)` (~line 1661) — confirmed via `common.yaml`'s `llm_gate` fragment (lines 47-72), which sets `evaluate.type: llm_structured` directly in the fragment body, so `learning-tests-audit.yaml`/`migrate-sdk-version.yaml`'s fragment-based gates are already resolved to `llm_structured` StateConfig objects by the time any `_validate_*(fsm)` rule runs — no fragment-aware logic is needed in the new rule
- Tests follow a fixed per-rule shape: `_simple_fsm()`/`make_state()` builders, no YAML fixtures; `test_mrN_fires_for_X` / `test_mrN_does_not_fire_when_X` / `test_mrN_suppressed_by_flag` / `test_mrN_fires_end_to_end_via_validate_fsm` — evidence: `TestLLMEvidenceContractValidation` (`test_fsm_validation_evaluator_rules.py:260-403`)

### Tests
- `scripts/tests/test_fsm_validation_evaluator_rules.py` — `TestLLMEvidenceContractValidation` (260-403) is the model test class to follow
- `scripts/tests/test_builtin_loops.py` — validates all built-in loops. **Superseded note:** an earlier revision expected this to surface 13 firings until BUG-3226/3227/3228 landed; those are all `done`, so under narrow scope this file stays green with zero new diagnostics. Under broad scope it would surface 199 across 66 files — treat a non-zero count here as the signal that the scope decision was made broad without the paired retrofit.

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
- `_is_llm_judged(state) -> bool` — existing predicate; `validation/_base.py:167-183`, checks `state.evaluate.type in ("llm_structured", "check_semantic")` or prompt/slash_command action heuristics. **Reuse it as one input, not as the whole predicate** — it is narrower than "abstention-capable" now that ENH-3224 has landed, and its `check_semantic` arm is dead. See [Predicate: abstention-capable, not LLM-judged](#predicate-abstention-capable-not-llm-judged).

Detection reads already-parsed `StateConfig` fields (`schema.py:656,659,689`) and `RouteConfig` fields (`schema.py:230-263`): `state.route`, `state.extra_routes`, `state.on_error`, `RouteConfig.routes`, `RouteConfig.error`.

### Call Path
`load_and_validate()` (`structural_rules.py`) → `resolve_fragments()` (pre-parse, ~line 1650) → `FSMLoop.from_dict()` (post-expansion parse, ~line 1653) → `validate_fsm(fsm)` (~line 1661) → new rule dispatched via `errors.extend(_validate_<name>(fsm))` alongside existing MR-4/MR-8 calls → per state: `_is_llm_judged(state)` filter → check `"cannot_judge" not in state.extra_routes and (state.route is None or "cannot_judge" not in state.route.routes)` AND `state.on_error is None and (state.route is None or state.route.error is None)` → `ValidationError(severity=WARNING, path=f"states.{state_name}")` appended → surfaced via `cmd_validate()` (`cli/loop/config_cmds.py:14-94`) as a non-exit-code-flipping warning in both text and `--json` output

### Decision Rules
- New gap kind: a diagnostic fires when BOTH conditions hold for an abstention-capable state: no cannot_judge route declared (neither `state.extra_routes["cannot_judge"]` nor `state.route.routes["cannot_judge"]`) AND no error route declared (neither `state.on_error` nor `state.route.error`)
- Exact inputs: state must be abstention-capable — scope per [Decision: Detection Scope](#decision-detection-scope), predicate per [Predicate: abstention-capable, not LLM-judged](#predicate-abstention-capable-not-llm-judged). Detection runs post-fragment-expansion (confirmed empirically), so `llm_gate`-fragment states are already resolved to `evaluate.type == "llm_structured"` by the time this rule runs — no separate fragment-aware branch needed
- Escape hatch: a new top-level suppression flag (exact name is an implementer decision, following the `partial_route_ok`/`evidence_contract_ok` naming convention) set to `true` at the loop level skips the rule for that loop; must be registered in both `schema.py` (`FSMLoop` field) and `validation/_base.py`'s `KNOWN_TOP_LEVEL_KEYS`, or the flag itself triggers an "unknown top-level key" warning
- Severity: **DECIDED — WARNING** ([Decision: Detection Scope](#decision-detection-scope)). Not because ERROR would be noisy on the built-in corpus (it fires 0 times there) but because ERROR makes a violating loop *unrunnable*: `load_and_validate()` raises `ValueError` on ERROR (`structural_rules.py:1676-1678`) and `ll-loop run` loads through it (`cli/loop/_helpers.py:1423,1447`), while consuming projects' loops are outside the measured corpus. WARNING-only violations don't raise, don't flip `valid` to `false` in `--json` mode, and don't change `ll-loop validate`'s exit code (`cli/loop/config_cmds.py:14-94`).

## Implementation Steps

0. Scope and severity are **decided — narrow + WARNING** ([Decision: Detection Scope](#decision-detection-scope)); no decision work remains. Do re-run the count before implementing rather than trusting the 2026-08-17 measurement, since the corpus moves — a non-zero narrow count means something regressed since BUG-3226/3227/3228.
1. A new validation rule fires a `ValidationError` at WARNING severity for any abstention-capable state that declares neither a `cannot_judge` route (`state.extra_routes`/`state.route.routes`) nor an error route (`state.on_error`/`state.route.error`); the message names the runtime consequence, citing `_ABSTENTION_HOLD_CAP = 2` (`executor.py:2658`) and `_abstention_fallback()`'s dead-end behavior (`executor.py:2688-2700`)
2. The predicate covers `evaluate.abstain_on_exit_3` states (ENH-3224, landed) alongside LLM-judged ones ([Predicate](#predicate-abstention-capable-not-llm-judged)), and the declared-route check matches the base `cannot_judge` key only, never `route.default` or the `_uncertain` form ([Declared-route check](#declared-route-check-mirror-_exact_route_declared-exactly)).
3. The rule is dispatched from `validate_fsm()` (`structural_rules.py`) and `test_builtin_loops.py` stays green — under narrow scope that means zero new diagnostics, since BUG-3226/3227/3228 already retired the known instances
4. A suppression flag, registered in both `FSMLoop` (`schema.py`) and `KNOWN_TOP_LEVEL_KEYS` (`validation/_base.py:79-140`), lets an intentional case opt out
5. Tests follow the `TestLLMEvidenceContractValidation` shape (`test_fsm_validation_evaluator_rules.py:260-403`): fires / does-not-fire / suppressed-by-flag / fires-end-to-end-via-`validate_fsm` cases. Include an `evaluate: {type: exit_code, abstain_on_exit_3: true}` fires case, and a does-not-fire case for the same state *without* the flag. Do not assert a single-diagnostic count on an `on_yes`-only state — MR-4 also fires there ([Overlap with MR-4](#overlap-with-mr-4-is-expected-and-acceptable)).
6. `python -m pytest scripts/tests/test_fsm_validation_evaluator_rules.py scripts/tests/test_fsm_validation_structural.py scripts/tests/test_builtin_loops.py -v` passes

## Scope Boundaries

**In scope**
- One new validation rule in `scripts/little_loops/fsm/validation/`, its dispatch from `validate_fsm()`, its suppression flag, and its tests
- The predicate covering ENH-3224's `evaluate.abstain_on_exit_3` states alongside LLM-judged ones

**Out of scope**
- **Retrofitting the 199 implicit-judge prompt states.** That is a separate follow-up issue with its own retrofit plan; this issue ships a rule, not a corpus fix.
- Changing any runtime abstention behavior — `_ABSTENTION_HOLD_CAP`, `_abstention_fallback()`, and the hold/route machinery are the semantics this rule *mirrors statically*, not semantics it modifies
- Assigning the rule an MR number. The MR series is meta-loop/harness-optimization scoped per the validation package docstring, and this rule applies to any judged gate; whether it joins the series is a documentation decision that need not block the code.
- The `check_semantic` dead-branch cleanup in `_is_llm_judged()` — noted as a drive-by, not a requirement

## Impact

Prevents recurrence of the abstention dead-end defect class. Under the recommended narrow scope, zero new diagnostics on the current built-in corpus. Under broad scope, 199 diagnostics across 66 of 103 loop files — which is why that scope needs a paired retrofit issue rather than a bare rule landing.

## Dependencies

- **ENH-3224 — satisfied (`status: done`).** Its `evaluate.abstain_on_exit_3` flag (`schema.py:113`) is in the tree, so this rule's predicate can cover flag-gated `exit_code` abstention directly. No blocking dependency remains. See [Predicate](#predicate-abstention-capable-not-llm-judged).
- Follow-up issue (not yet filed) for the 199 implicit-judge prompt states, if the scope decision goes narrow.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.validation` section — existing
  MR-4/MR-8/MR-14 rule patterns to model the new rule after

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-17_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- ~~`decision_needed: true` is still set even though the issue carries a strong, data-backed recommendation (narrow scope, tier-1 ship). Severity (WARNING vs ERROR) and the suppression-flag name remain explicit implementer choices rather than closed decisions.~~ **Resolved 2026-08-17:** scope and severity closed as narrow + WARNING; `decision_needed: false`. The suppression-flag *name* remains an implementer choice, which is a naming detail, not a decision gate.
- ~~ENH-3224 has not landed yet...~~ **Resolved 2026-08-17:** ENH-3224 is `done`; the flag is `EvaluateConfig.abstain_on_exit_3` (`schema.py:113`) and the predicate now names it directly.

### Review Pass — 2026-08-17

_Re-measured against the current tree; the issue's own numbers reproduce exactly
(narrow 0, broad 199 across 66 files, `route.default` rescues none of the 199), and
`fsm/validation/` still contains no `cannot_judge` reference of any kind._

Scores raised to 94 / 92 on the strength of: the ENH-3224 dependency resolving, the
severity decision closing on the `ll-loop run`-unrunnable argument, and three
implementation ambiguities being pinned down (the `uncertain_suffix` non-arm, the
one-directional `_uncertain` route fallback, and the expected MR-4 double-diagnostic).

## Status

**Open** | Created: 2026-08-16 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-08-17T17:15:11 - `874f81b5-d638-4302-8b4b-3679eae19140.jsonl`
- `/ll:confidence-check` - 2026-08-17T16:54:33 - `8ff1a8ea-9c16-4537-b2ba-58cd77df4fae.jsonl`
- `/ll:confidence-check` - 2026-08-17T16:17:47 - `c786d9ca-0348-4ed5-812d-bc2de7a34350.jsonl`
- `/ll:refine-issue` - 2026-08-17T06:06:13 - `86eb12f1-b126-4db7-a22d-252ffa585d1f.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
