---
id: ENH-2299
title: Add policy-router branch to create-loop wizard
type: ENH
priority: P3
status: done
discovered_date: 2026-06-26
discovered_by: capture-issue
captured_at: '2026-06-26T00:04:42Z'
completed_at: '2026-06-26T01:15:25Z'
relates_to:
- FEAT-2301
decision_needed: false
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# ENH-2299: Add policy-router branch to create-loop wizard

## Summary

Add a "Policy router (decision table)" loop type to `/ll:create-loop` so users can generate policy-routed FSM loops without hand-authoring the YAML. The wizard branch should wire `lib/policy-router.yaml` (and optionally `lib/rubric-router.yaml`), scaffold the three-state `score → parse_scores → policy_dispatch` pipeline, and let the user define their `context.policy_rules` decision table interactively.

## Current Behavior

`/ll:create-loop` offers no wizard path for the policy-router pattern. Users who want a decision-table-based loop (multi-dimensional score routing via `lib/policy-router.yaml`) must hand-author the FSM YAML, copy `policy-refine.yaml` as a starting point, and manually configure `context.policy_rules`, the `route:` dispatch map, and the fragment imports. The guide (`docs/guides/POLICY_ROUTER_GUIDE.md`) documents the pattern, but there is no guided scaffolding.

## Expected Behavior

A new wizard branch — "Policy router (decision table)" — appears in the Step 1 type-selection prompt. When selected, the wizard:

1. **Asks for the scoring source**: LLM rubric scorer (`lib/rubric-router.yaml`) or custom shell scorer that writes `rubric-dim-<name>.txt` files.
2. **Asks for the scored dimensions**: comma-separated list (e.g. `clarity,completeness,feasibility,security`).
3. **Asks for the subject artifact**: path or context variable to score (e.g. `artifact.md` or `${context.subject}`).
4. **Collects decision rules interactively**: presents an editable table (inline markdown grid) and writes them as `context.policy_rules`.
5. **Generates the FSM YAML** with the correct fragment imports, `score → parse_scores → policy_dispatch` pipeline, and a `route:` map that covers all action states plus `_:` and `_error:` catch-alls.
6. **Suggests `ll-loop edit-routes <name>`** in the completion message so users know they can re-edit the decision table after creation.

## Motivation

The policy-router pattern is the recommended approach for any loop that needs to branch on a combination of scores (e.g. "ship only if both confidence and security are high"). The guide and fragment library already exist; the wizard is the missing step that makes the pattern discoverable and prevents authoring errors (missing catch-alls, unmatched `route:` keys, MR-4 dead-ends) from the start.

## Scope Boundaries

- **In scope**: Adding the `policy-router` wizard branch to `/ll:create-loop` (Step 1 type selection, question flow, YAML template generation)
- **Out of scope**: Modifying `lib/policy-router.yaml` or `lib/rubric-router.yaml` fragments (no changes to runtime logic)
- **Out of scope**: Automated migration or detection of existing hand-authored policy-router loops
- **Out of scope**: Nested or chained policy tables; the wizard produces a flat `context.policy_rules` table only
- **Out of scope**: Visual/GUI policy editor — users re-edit the decision table via `ll-loop edit-routes` after creation

## Proposed Solution

### Wizard Branch Parameters

| Parameter | Question | Default |
|-----------|----------|---------|
| Scoring source | LLM rubric or custom shell scorer? | LLM rubric |
| Dimensions | Comma-separated scored dimensions | `quality,feasibility,security` |
| Subject artifact | Path or context variable | `${context.subject}` |
| Initial policy rules | Inline decision table (editable) | catch-all `* -> repair` |
| Action states | Comma-separated target states | `done,repair,escalate` |
| Max iterations | Integer | 10 |

### Generated YAML Shape

```yaml
import:
  - lib/rubric-router.yaml      # or omitted for custom scorer
  - lib/policy-router.yaml

context:
  subject: "<artifact>"
  rubric_dimensions: "<dim1>|<dim2>|..."
  policy_rules: |
    <dim>:<op><val> -> <state>
    * -> repair

initial: score

states:
  score:
    fragment: rubric_score
    capture: scores
    next: parse_scores

  parse_scores:
    fragment: policy_parse_scores
    next: policy_dispatch

  policy_dispatch:
    fragment: policy_table_dispatch
    route:
      done: done
      repair: repair
      escalate: escalate
      _: repair
      _error: done

  repair:
    action_type: prompt
    action: "Repair {{context.subject}} based on rubric feedback."
    next: score

  escalate:
    terminal: true

  done:
    terminal: true
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on analysis of `policy-refine.yaml` and `lib/rubric-router.yaml`:_

The YAML shape above is missing `threshold_high` and `threshold_medium`. The canonical reference loop (`policy-refine.yaml`) includes them when importing `lib/rubric-router.yaml`, because `rubric-router.yaml`'s `rubric_parse_scores` fragment consumes them (defaults: 85 / 65). They are technically unused in the policy-router path (which uses `policy_parse_scores` instead), but are present in the reference loop for completeness. Include them when using the LLM rubric scorer so callers can override thresholds without patching the generated YAML:

```yaml
context:
  subject: "<artifact>"
  rubric_dimensions: "<dim1>|<dim2>|..."
  threshold_high: "85"    # consumed by rubric-router fragments; default 85
  threshold_medium: "65"  # consumed by rubric-router fragments; default 65
  policy_rules: |
    ...
```

**Import order is strict**: `lib/rubric-router.yaml` must appear before `lib/policy-router.yaml` in the `import:` list, because `rubric_score` (rubric-router) must be resolved before `policy_parse_scores` (policy-router) can consume its output.

**Custom shell scorer path generates different YAML**: When the user selects a custom shell scorer (instead of LLM rubric), the `import:` list omits `lib/rubric-router.yaml`, the `score` state is a `shell` action that writes `rubric-dim-<name>.txt` files directly to `${context.run_dir}/`, and the `parse_scores` state may be omitted entirely (the shell scorer writes score files directly, bypassing `policy_parse_scores`). The wizard generates two distinct YAML shapes depending on the scorer selection.

## Integration Map

### Files to Modify
- `skills/create-loop/SKILL.md` — (1) add new keyword inference entries in Step -1; (2) add "Policy router (decision table)" option in Step 1 `AskUserQuestion`; (3) add type-mapping entry
- `skills/create-loop/loop-types.md` — add full `## Policy Router Questions` section: sub-steps for scoring source / dimensions / subject / policy rules / action states / max iterations, plus `### Generate Policy Router FSM YAML` block with both LLM-rubric and custom-scorer variants
- `skills/create-loop/templates.md` — (1) add "Policy router (decision table)" option to Step 0.1 type-selection `AskUserQuestion`; (2) add `### Template: policy-router` block with `{{token}}` substitutions; (3) add `### For "Policy router (decision table)"` section in Step 0.2 with customization questions

_Note_: The wizard question flow and YAML generation belong in `loop-types.md` (Step 2, custom/wizard path). `templates.md` serves the "Start from template" path (Step 0.1–0.2) only — it contains pre-built `{{token}}`-substituted YAML templates, not wizard question flows.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/lib/policy-router.yaml` — fragment library consumed by generated loops (`policy_parse_scores`, `policy_table_dispatch`); no changes needed
- `scripts/little_loops/loops/lib/rubric-router.yaml` — optional fragment for LLM scoring (`rubric_score`); no changes needed
- `scripts/little_loops/loops/policy-refine.yaml` — canonical reference loop; use as the template for wizard-generated YAML
- `scripts/little_loops/fsm/policy_rules.py` — rule grammar engine (`parse_rules`, `evaluate_rules`); imported by `policy_table_dispatch` fragment; confirms rule syntax documented in the issue is correct
- `scripts/little_loops/fsm/route_table.py` — route-table rendering for `ll-loop edit-routes`; used after loop creation to re-edit the decision table
- `scripts/little_loops/cli/loop/edit_routes.py` — `ll-loop edit-routes` CLI command; already implemented and working — reference it in the completion message tip

### Similar Patterns
- `## Optimize a Harness (Meta-Loop) Questions` in `skills/create-loop/loop-types.md` — closest structural analog: gathers context variables interactively (Steps M1–M5), uses a refusal guard for required fields, and generates YAML with a `context:` block; follow this pattern for policy-router steps
- `## RL Policy Questions` in `skills/create-loop/loop-types.md` — cleanest minimal example of the `### Step X#: Title` + `AskUserQuestion` block + `#### Generate ... YAML` structure
- `class TestHarnessPlanResearchImplementReport` in `scripts/tests/test_create_loop.py` — existing test class that validates wizard-generated YAML structure; use as the test pattern (not `test_builtin_loops.py`)

### Tests
- `scripts/tests/test_create_loop.py` — add `TestPolicyRouterWizardYAML` class following the `TestHarnessPlanResearchImplementReport` pattern: define the expected YAML as a module-level string, parse with `yaml.safe_load`, and assert required fields (`import` list contains both fragment libs, `context.policy_rules` is present, `policy_dispatch.route` contains `_:` and `_error:`, required states exist)
- `scripts/tests/test_builtin_loops.py` — `test_expected_loops_exist` at line 74 already covers `policy-refine`; no new entry needed unless a new builtin loop file is added (the wizard does not add a builtin loop)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — `DOC_STRINGS_PRESENT` parametrized list currently asserts ENH-1912 strings (`"Orch: Router (dynamic dispatch)"`, `"orch-router"`) in `SKILL.md`, `templates.md`, and `loop-types.md`; add parallel ENH-2299 entries: `("skills/create-loop/SKILL.md", "Policy router (decision table)", "ENH-2299")`, `("skills/create-loop/loop-types.md", "## Policy Router Questions", "ENH-2299")`, `("skills/create-loop/templates.md", "policy-router", "ENH-2299")`, `("docs/reference/COMMANDS.md", "policy-router", "ENH-2299")` [Agent 1 + Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue`:_

- **Keyword collision**: "policy" in the Step -1 inference table already routes to `rl-policy`. Add unambiguous phrases only: `"decision table"`, `"policy rules"`, `"policy router"`, `"multi-score routing"`, `"rubric route"`.
- **`ll-loop edit-routes` confirmed**: The command exists at `scripts/little_loops/cli/loop/edit_routes.py` and uses `route_table.py` for round-trip editing of policy-router decision tables. Reference it in the wizard completion message: `Tip: Run ll-loop edit-routes <name> to re-edit the decision table.`

### Documentation
- `docs/guides/POLICY_ROUTER_GUIDE.md` — add a "Using the Wizard" section cross-linking to `/ll:create-loop`
- `docs/guides/LOOPS_GUIDE.md` — update type list to include policy-router

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `/ll:create-loop` entry under `## Automation Loops` contains a hardcoded parenthetical type list `(fix-until-clean, ..., orch-router)`; add `policy-router` to keep it current [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Add `policy-router` type to the Step 1 `AskUserQuestion` options in `skills/create-loop/SKILL.md` and `templates.md`.
2. Add keyword mappings (`"decision table"`, `"multi-score"`, `"policy router"`, `"rubric route"`) to the type-inference block in `SKILL.md`.
3. Write the wizard question flow for `policy-router` in `loop-types.md` (parameters: scoring source, dimensions, subject, initial rules, action states, max iterations).
4. Write the `policy-router` YAML template in `templates.md` with substitution tokens for all wizard-collected values; ensure `route:` map always includes `_:` and `_error:` entries.
5. Add validation: reject empty dimension list, require at least one non-catch-all rule before generating YAML.
6. Emit `ll-loop edit-routes <name>` suggestion in the completion message.
7. Add `TestPolicyRouterWizardYAML` class in `test_create_loop.py` (not `test_builtin_loops.py`) following the `TestHarnessPlanResearchImplementReport` pattern: define the representative YAML as a module-level string constant, parse with `yaml.safe_load`, and assert: `import` list contains both `lib/rubric-router.yaml` and `lib/policy-router.yaml`, `context.policy_rules` is present, `policy_dispatch.route` contains `_:` and `_error:` keys, and required states (`score`, `parse_scores`, `policy_dispatch`, `done`) all exist.
8. Update `POLICY_ROUTER_GUIDE.md` with a "Using the Wizard" section.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `docs/reference/COMMANDS.md` — add `policy-router` to the hardcoded parenthetical type list in the `/ll:create-loop` workflow step description
10. Update `scripts/tests/test_wiring_skills_and_commands.py` — add four new `DOC_STRINGS_PRESENT` entries: `("skills/create-loop/SKILL.md", "Policy router (decision table)", "ENH-2299")`, `("skills/create-loop/loop-types.md", "## Policy Router Questions", "ENH-2299")`, `("skills/create-loop/templates.md", "policy-router", "ENH-2299")`, `("docs/reference/COMMANDS.md", "policy-router", "ENH-2299")`

## Impact

- **Priority**: P3 — Discoverability improvement; the policy-router pattern already works but requires manual YAML authoring, no urgent unblock
- **Effort**: Medium — Changes span 3 skill files (`SKILL.md`, `loop-types.md`, `templates.md`), 1 test file, 2 doc files; no runtime code changes
- **Risk**: Low — Purely additive; existing wizard paths and FSM runtime are untouched
- **Breaking Change**: No

## Labels

`enhancement`, `create-loop`, `loops`, `wizard`

## Status

**Open** | Created: 2026-06-26 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-25_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **8-site breadth across wizard, tests, and docs** — Changes touch SKILL.md, loop-types.md, templates.md, two test files, and three doc files; risk is missing a sync across the doc surface (LOOPS_GUIDE.md, POLICY_ROUTER_GUIDE.md, COMMANDS.md) since they don't have automated coverage
- **Custom scorer YAML shape specified in prose only** — The custom shell scorer path differs materially from the LLM rubric path (no rubric import, no `parse_scores` state) but is described in prose rather than shown as an explicit template; implementer must derive it carefully to avoid subtle structural errors
- **Wizard section authoring is the high-effort core** — Writing the `## Policy Router Questions` section in loop-types.md (multi-step question flow + two conditional YAML shapes) is the largest single-file change; following the RL Policy section pattern closely will reduce risk

## Resolution

Implemented all 10 steps from the implementation plan:

1. Added `policy-router` type to Step 1 `AskUserQuestion` in `skills/create-loop/SKILL.md`
2. Added keyword mappings (`decision table`, `policy rules`, `policy router`, `multi-score routing`, `rubric route`) to Step -1 inference block
3. Wrote `## Policy Router Questions` wizard flow (Steps PR1–PR6) in `loop-types.md` — covers scoring source, dimensions, subject, policy rules, action states, max iterations
4. Wrote two YAML generation paths (LLM rubric / custom shell scorer) with correct import order, `threshold_high`/`threshold_medium`, and `_:`/`_error:` catch-alls
5. Added catch-all validation warning in wizard question flow
6. Added `ll-loop edit-routes` suggestion in completion message
7. Added `TestPolicyRouterWizardYAML` class in `test_create_loop.py` with 9 structural assertions
8. Updated `POLICY_ROUTER_GUIDE.md` with "Using the Wizard" section
9. Updated `docs/reference/COMMANDS.md` type list to include `policy-router`
10. Added 4 new `DOC_STRINGS_PRESENT` entries in `test_wiring_skills_and_commands.py`

All 216 tests in `test_create_loop.py` and `test_wiring_skills_and_commands.py` pass. No regressions.

## Session Log
- `/ll:ready-issue` - 2026-06-26T01:06:48 - `af4f04b2-3757-49a5-9070-5c5e2e83f4f3.jsonl`
- `/ll:confidence-check` - 2026-06-25T00:00:00Z - `86b1c53c-f74c-432c-ba26-627fc7b5814b.jsonl`
- `/ll:wire-issue` - 2026-06-26T00:56:31 - `206cefe7-3625-47fe-8d68-9becc11a2e20.jsonl`
- `/ll:refine-issue` - 2026-06-26T00:48:30 - `dace4845-a459-498c-a40e-691d358094f6.jsonl`
- `/ll:format-issue` - 2026-06-26T00:08:40 - `84c784f6-8af8-4e01-af14-823702d77101.jsonl`
- `/ll:capture-issue` - 2026-06-26T00:04:42Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52c7663b-99b0-4ea2-9984-865b6cd49e08.jsonl`
