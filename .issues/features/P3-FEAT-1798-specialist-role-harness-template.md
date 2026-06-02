---
id: FEAT-1798
type: FEAT
title: "Specialist-role harness template (Plan \u2192 Research \u2192 Implement \u2192\
  \ Report)"
priority: P3
status: open
captured_at: '2026-05-29T20:37:23Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
- captured
- fsm
- harness
- loops
- templates
- create-loop
relates_to:
- ENH-1796
- FEAT-1808
parent: EPIC-1773
decision_needed: false
blocked_by: []
decision: "Option B \u2014 omit HITL gates, ship as autonomous pipeline (Plan \u2192\
  \ Research \u2192 Implement \u2192 Report without human gates). Simplest, works\
  \ today. Include commented-out HITL block for future activation when FEAT-1794 lands.\
  \ Upgrade to Option C after FEAT-1794."
confidence_score: 90
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1798: Specialist-role harness template (Plan → Research → Implement → Report)

## Summary

Add a third harness variant to the `/ll:create-loop` wizard — **Variant
C: specialist-role pipeline** — that mirrors DeerFlow v1's
coordinator/planner/researcher/coder/reporter topology as a fixed FSM
template. Today the wizard offers only Variant A (single-shot) and
Variant B (multi-item), both of which collapse all "work" into one
`execute` step. Many real tasks (deep refactors, multi-file features,
cross-cutting refactors) benefit from explicit Plan → Research →
Implement → Report decomposition with HITL gates between stages.

## Current Behavior

- Wizard branches on H1 (target skill) and H2 (work-item mode) into
  Variants A and B.
- Both variants have a single `execute` state followed by evaluation
  gates.
- A user who wants a planning step today has to either:
  - Hand-author the FSM (30–60 min) per the loops reference, or
  - Chain `/ll:iterate-plan` and `/ll:manage-issue` outside any loop.
- No pre-built pattern reflects the multi-role architecture that has
  become a de-facto standard (DeerFlow, GPT-Researcher,
  langgraph-supervisor, etc.).

## Expected Behavior

A new wizard branch generating an FSM like:

```yaml
name: "harness-plan-research-implement-report"
initial: plan
max_iterations: 50
states:
  plan:
    action: /ll:iterate-plan ${args.task}
    action_type: slash_command
    capture: plan
    next: review_plan       # HITL gate (FEAT-1794 dependency)
  review_plan:
    action_type: human_approval   # depends on FEAT-1794
    prompt: "Review the plan: ${captured.plan.output}"
    on_yes: research
    on_no: plan
  research:
    action: "<background investigation skill>"
    action_type: prompt
    capture: research
    next: implement
  implement:
    action: /ll:manage-issue ${captured.plan.output}
    action_type: slash_command
    next: check_concrete
  check_concrete: { ... }          # existing phase chain
  check_semantic: { ... }
  check_invariants: { ... }
  report:
    action: /ll:describe-pr
    action_type: slash_command
    next: done
  done: { terminal: true }
```

Wizard additions:
- New H1 / H2 option set, or a new top-level "Workflow type" question.
- Sensible defaults for each role (configurable per-skill).
- Generated YAML lives under `scripts/little_loops/loops/` as a runnable
  annotated example, matching the `harness-single-shot.yaml` /
  `harness-multi-item.yaml` pattern.
- Documentation entry in `AUTOMATIC_HARNESSING_GUIDE.md` § Generated
  FSM Structure as "Variant C".

## Use Case

**Who**: A developer authoring automation loops with the `/ll:create-loop` wizard

**Context**: When building a task that benefits from explicit phase decomposition — deep refactors, multi-file features, or cross-cutting changes — where a single `execute` state is too coarse-grained

**Goal**: Generate a ready-to-run Variant C FSM YAML (Plan → Research → Implement → Report) without hand-authoring the full state machine (30–60 min saved)

**Outcome**: A validated YAML file is created under `scripts/little_loops/loops/` that passes `ll-loop validate` and includes annotated comments for optional HITL gates

## Acceptance Criteria

- [ ] `/ll:create-loop` wizard presents a "Specialist role pipeline" option at the loop type selection step (`SKILL.md` ~line 136)
- [ ] Wizard generates a Variant C FSM YAML with `plan`, `research`, `implement`, and `report` states routed consecutively
- [ ] Generated YAML is written to `scripts/little_loops/loops/harness-plan-research-implement-report.yaml` and passes `ll-loop validate` without errors
- [ ] `harness-plan-research-implement-report` is added to the expected loops set in `test_expected_loops_exist` (`test_builtin_loops.py:66`)
- [ ] `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` includes a `### Variant C: Specialist-Role Pipeline` section after Variant B
- [ ] Generated YAML includes a `# EXAMPLE:` commented HITL block showing the FEAT-1794 activation pattern

## Impact

- **Priority**: P3 — Net-new template; existing variants still cover
  the common case. Highest value once FEAT-1794 (HITL) lands, since
  the role boundaries are where human gates belong.
- **Effort**: Medium — wizard logic, generated YAML, annotated example,
  docs. Dependencies on FEAT-1794 and (nice-to-have) ENH-1796 for
  cross-role context sharing.
- **Risk**: Low — opt-in third variant; doesn't affect A or B.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Generated FSM Structure | Variants A/B documented here; this adds C |
| `skills/create-loop/loop-types.md` | Wizard implementation (lines 549–1065 for Harness Questions, next H2 at line 1067) |
| `FEAT-1794` | HITL state type — preferred (not strictly required) for inter-role gates |
| `ENH-1796` | Shared message log — improves prompt quality across the role chain |

## Integration Map

### Files to Modify
- `skills/create-loop/SKILL.md` — Step 1 loop type selection (~line 136): add "Specialist role pipeline" option; update Step 2 delegation to reference new question flow
- `skills/create-loop/loop-types.md` — Insert `## Specialist Pipeline Questions` section before line 1067 (`## Optimize a Harness (Meta-Loop) Questions`), after the `---` at line 1065; also update line 700 "Two structural variants" text to "Three structural variants"
- `skills/create-loop/templates.md` — Add Variant C template entry if available in "Start from template" path (Step 0.1)
- `skills/create-loop/reference.md` — Add specialist pipeline state structure to "Loop Type State Structures" section
- `scripts/little_loops/loops/greenfield-builder.yaml` — `harness_planning` state action text hard-codes "two harness variants" and lists only `ll-loop install harness-single-shot` / `harness-multi-item`; expand to include Variant C option [Wiring pass]

### Files to Create
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml` — Runnable annotated example (Variant C), matching `harness-single-shot.yaml` / `harness-multi-item.yaml` pattern with `# EXAMPLE:` comments

### Dependent Files (Documentation)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Add `### Variant C: Specialist-Role Pipeline` section after Variant B (after line ~713, before `## Using the Example Files` at line 715); update Table of Contents lines 26–29 to add Variant C entry; update line 717 "Two annotated" → "Three annotated"; add Variant C row to example files table; also update `## See Also`
- `scripts/little_loops/loops/README.md` — Add Variant C entry under "Harness / Templates" section
- `docs/guides/LOOPS_GUIDE.md` — **Harness Examples** table under the built-in loops catalog lists only `harness-single-shot` and `harness-multi-item`; add `harness-plan-research-implement-report` row [Wiring pass]

### Similar Patterns (Existing Code to Model After)
- `skills/create-loop/loop-types.md:700-857` — Variant A and B FSM YAML templates with conditional-phase comments — exact pattern to replicate
- `skills/create-loop/loop-types.md:548-694` — Harness Questions H1-H4 question flow (`AskUserQuestion` blocks) — structure to replicate for S1-S5
- `scripts/little_loops/loops/harness-single-shot.yaml` — Annotated example format with `# EXAMPLE:` block comments — format to follow
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — Existing plan → refine → gate → implement pipeline with `capture` handoff — structural precedent
- `scripts/little_loops/loops/rn-plan.yaml` — Plan → Research → Refine → Score pipeline — closest existing phase decomposition
- `scripts/little_loops/loops/deep-research.yaml` — Research → Synthesis pipeline with per-run artifact isolation (`capture: run_dir`)

### Tests
- `scripts/tests/test_builtin_loops.py:66` — `test_expected_loops_exist` — add `"harness-plan-research-implement-report"` to the `expected` set alongside the three existing harness names at lines 92–94 (exact equality check; will fail without this)
- `scripts/tests/test_builtin_loops.py:30,37,47` — `test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, `test_all_have_description_field` — auto-cover new YAML in loops dir; new YAML **must** have a non-empty `description:` field
- `scripts/tests/test_create_loop.py` — Add YAML pattern validation for Variant C output following existing `TestLoopFileValidation` pattern

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_loop.py` — Add `TestHarnessPlanResearchImplementReport` class: module-level YAML constant for Variant C scaffold, per-field assertions for required states (`plan`, `research`, `implement`, `report`, `done`), `initial == "plan"`, phase sequencing, and terminal state — follow `TestEvalHarnessVariantA`/`B` shape in `scripts/tests/test_create_eval_from_issues.py:142`
- `scripts/tests/test_builtin_loops.py:1031` — `TestHarnessCapture.HARNESS_FILES`: add `"harness-plan-research-implement-report.yaml"` **only if** Variant C YAML includes `execute`, `check_semantic`, and `check_stall` states (topology-dependent; skip if using `plan→research→implement→report` chain without canonical harness states)
- `scripts/tests/test_fsm_fragments.py` — `TestBuiltinLoopMigration.migration_targets` at line ~998: add new YAML filename if it uses `fragment: shell_exit` states (optional but conventional)
- **Constraint**: editing `skills/create-loop/loop-types.md` or `skills/create-loop/reference.md` must preserve `circuit_breaker_enabled` and `circuit_breaker_path` tokens (`test_circuit_breaker_doc_wiring.py` checks these)
- **Constraint**: editing `skills/create-loop/loop-types.md` or `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` must preserve `timeout: 1500` and `MCP calls` tokens (`test_enh1639_doc_wiring.py` checks these)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrected state name in `greenfield-builder.yaml`**: The state that mentions "two harness variants" is named `harness_planning` (lines 90–111), not `plan_harness`. The exact text to replace: line 95 `"for the two harness variants (single-shot and multi-item)."` → three variants; line 102 add a third `ll-loop install harness-plan-research-implement-report` option as item 3 in the numbered list.

**`loop-types.md` exact insert point for `## Specialist Pipeline Questions`**: The `## Harness Questions` section extends to line ~1065 (the full worked example and `diff_stall_gate` reference block), followed by `---` at line 1065. The next major H2 is `## Optimize a Harness (Meta-Loop) Questions` at line 1067. Insert `## Specialist Pipeline Questions` between lines 1065–1067, not at line 914 (which is inside the `## Harness Questions` section mid-content). The "Two structural variants" text at line 700 also needs updating to say "Three structural variants" once Variant C is added.

**`AUTOMATIC_HARNESSING_GUIDE.md` exact insert points**: Variant B ends at line ~713 (`---` separator). `## Using the Example Files` starts at line 715 with "Two annotated example harness loops" (line 717). Insert `### Variant C: Specialist-Role Pipeline` section between lines 713–715. Also update: (a) Table of Contents (lines 26–29) — add `  - [Variant C: Specialist-Role Pipeline](#variant-c-specialist-role-pipeline)` after Variant B entry; (b) line 717 — "Two annotated" → "Three annotated"; (c) the example files table at line 719 — add a Variant C row.

**`skills/create-loop/SKILL.md` Type Mapping section** (lines 148–157): In addition to adding the wizard option label, the Type Mapping block that follows at lines 148–157 needs a new entry: `"Specialist role pipeline" -> specialist-pipeline type (states: plan, research, implement, report, done)`. Without this, Step 2 delegation logic won't route to the new `## Specialist Pipeline Questions` section in loop-types.md.

### Key Architectural Insight

**The create-loop wizard is entirely prompt-based, not Python code.** The AI reads Markdown instruction files (`skills/create-loop/*.md`) and generates FSM YAML directly — there is no Python code that transforms wizard answers into YAML. This means Variant C requires changes ONLY to Markdown files, not Python. The Python layer (`scripts/little_loops/fsm/schema.py:309` `StateConfig`, `validation.py:711` `validate_fsm()`) already supports all FSM features Variant C needs (`action_type: prompt`, `action_type: slash_command`, `capture`, route states via `evaluate` blocks).

### HITL Gate Status (FEAT-1794 Dependency)

There is NO `action_type: human_approval` in the current FSM schema (`StateConfig` at `scripts/little_loops/fsm/schema.py:309-393`). The proposed template in Expected Behavior uses `action_type: human_approval` which does not yet exist. Until FEAT-1794 lands, any HITL gates must use the existing workaround pattern from `scripts/little_loops/loops/loop-router.yaml` (a `prompt` state that asks the user, then routes via `output_contains`).

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Three implementation options identified based on HITL gate handling:

**Option A: Include HITL gates via workaround pattern (no FEAT-1794 dependency)**
- Use `action_type: prompt` + `output_contains` evaluator pattern from `scripts/little_loops/loops/loop-router.yaml` to implement `review_plan` as an interactive gate
- Plan → [HITL review via prompt gate] → Research → Implement → [evaluation phases] → Report
- Works today, no dependency on FEAT-1794
- Gate prompt: "Review the plan: ${captured.plan.output}. Reply APPROVE to proceed or REVISE to re-plan."

**Option B: Omit HITL gates (simplest, always works)**
- Route plan → research → implement → [evaluation phases] → report consecutively without human gates
- Follows the `rn-plan.yaml` pattern (continuous autonomous pipeline)
- Evaluate plan quality via `check_semantic` (LLM-as-judge) or `check_concrete` (exit code from tool run) instead of human gate
- Simpler FSM, no HITL workaround needed

**Option C: Wait for FEAT-1794, then use `action_type: human_approval`**
- Cleanest implementation once `action_type: human_approval` exists in FSM schema
- Matches the Expected Behavior YAML in this issue exactly
- Blocks on FEAT-1794 landing first

**Recommendation**: Ship Option B first (simplest, unblocks the template immediately), then upgrade to Option C when FEAT-1794 lands. The Variant C template should include both the autonomous path and a commented-out HITL block showing the FEAT-1794 pattern for future activation.

## Implementation Steps

1. **Add question flow to `loop-types.md`** (after line 914): Create `## Specialist Pipeline Questions` section with S1-S5 sub-steps following the H1-H4 pattern:
   - S1: Role selection — which roles are active (Plan, Research, Implement, Report — multi-select, all pre-selected)
   - S2: Target task — what is being planned/implemented (free-text, becomes `${args.task}` or context variable)
   - S3: Work item discovery — same as H2 question for multi-item support, or default to single-shot
   - S4: Evaluation phases — same as H3 question (tool gates, stall detection, LLM-as-judge, diff invariants)
   - S5: Iteration budget — same as H4 question

2. **Add Variant C FSM YAML template** in `loop-types.md`: Create `### Generate Specialist Pipeline FSM YAML` subsection with annotated template following the conditional-comment pattern at lines 700-857. Base structure:
   - `plan` state: `action_type: prompt` or `/ll:iterate-plan ${args.task}`
   - `research` state: `action_type: prompt` (file/web research using Read/Grep/WebSearch tools)
   - `implement` state: `action_type: prompt` or `/ll:manage-issue ${captured.plan.output}`
   - Optional evaluation chain: `check_concrete`, `check_semantic`, `check_invariants`
   - `report` state: `action_type: prompt` (summarize what was done) → `done`
   - Add `# EXAMPLE:` commented HITL block showing the FEAT-1794 pattern

3. **Update `SKILL.md`**: Add "Specialist role pipeline" option to Step 1 loop type selection question (~line 136)

4. **Create runnable example**: Write `scripts/little_loops/loops/harness-plan-research-implement-report.yaml` following the annotated example format of `harness-single-shot.yaml` (all phases visible, optional ones as `# EXAMPLE:` comments)

5. **Update documentation**: Add Variant C section to `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` after Variant B, plus entry in "Using the Example Files" table

6. **Update tests**: Add Variant C name to `test_expected_loops_exist` in `scripts/tests/test_builtin_loops.py:66`; add Variant C pattern test in `test_create_loop.py` following `TestLoopFileValidation` pattern

7. **Validate**: Run `ll-loop validate harness-plan-research-implement-report` and `python -m pytest scripts/tests/test_builtin_loops.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/guides/LOOPS_GUIDE.md` — add `harness-plan-research-implement-report` row to the **Harness Examples** table under the built-in loops catalog
9. Update `scripts/little_loops/loops/greenfield-builder.yaml` — `harness_planning` state action: expand "two harness variants" guidance to list Variant C as a third option (`ll-loop install harness-plan-research-implement-report`)
10. Write `TestHarnessPlanResearchImplementReport` class in `scripts/tests/test_create_loop.py` — structural assertions: `initial == "plan"`, required state names (`plan`, `research`, `implement`, `report`, `done`), phase sequencing chain, non-empty `description:` field
11. When editing `loop-types.md` or `reference.md`, verify `circuit_breaker_enabled` and `circuit_breaker_path` tokens are preserved
12. When editing `loop-types.md` or `AUTOMATIC_HARNESSING_GUIDE.md`, verify `timeout: 1500` and `MCP calls` tokens are preserved

## Labels

`captured`, `create-loop`, `fsm`, `harness`, `loops`, `templates`

## Status

**Open** | Created: 2026-05-29 | Priority: P3

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-02_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- **Test coverage gap on wizard files**: Edits to `skills/create-loop/loop-types.md` and `SKILL.md` have no behavioral unit tests — wizard flow failures only surface at runtime; the only automated guards are token-presence constraints (`circuit_breaker_enabled`, `timeout: 1500`, `MCP calls`). Run constraint tests after each loop-types.md edit: `python -m pytest scripts/tests/test_circuit_breaker_doc_wiring.py scripts/tests/test_enh1639_doc_wiring.py -v`.
- **S1-S5 question authoring**: The question flow is specified at outline level; exact question text, option labels, and defaults must be authored during implementation. Pattern is clear (H1-H4 in loop-types.md:548-694), but expect ~30-60 min of careful authoring to produce well-integrated questions.

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-02 — verdict: **NEEDS_UPDATE** (corrected inline)_

**Stale line numbers in Integration Map / Similar Patterns sections:**
- `scripts/little_loops/fsm/schema.py:309` → actual `StateConfig` at **line 337**
- `scripts/little_loops/fsm/validation.py:711` → actual `validate_fsm()` at **line 775**
- `skills/create-loop/loop-types.md:700-857` (Variant A/B templates) → Variant B extends to **~928** (next `##` section starts at 929); the 857 upper bound is ~71 lines short

**Corrected in this pass:**
- `blocked_by: [FEAT-1808]` removed — contradicted the explicit Option B decision ("works today, no dependency on FEAT-1808"); FEAT-1808 is a future upgrade path, not a blocker.

**Confirmed accurate:** All referenced files exist; related issues FEAT-1794, FEAT-1808, ENH-1796, EPIC-1773 all open; `harness-plan-research-implement-report.yaml` not yet created (expected — it's the artifact to create); `action_type: human_approval` absent from FSM schema as described; test function line numbers off by 1 (within tolerance).

## Session Log
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `65f77860-d771-4c40-9ba9-2bc9f9139bfe.jsonl`
- `/ll:refine-issue` - 2026-06-02T23:34:29 - `dbfa4553-bb50-4095-a28a-7fd0414252fb.jsonl`
- `/ll:verify-issues` - 2026-06-02T23:28:18 - `f1eb338d-104c-4e7d-b1d5-f987c7de0b61.jsonl`
- `/ll:verify-issues` - 2026-06-02T00:00:00Z - `.ll/history.db`
- `/ll:confidence-check` - 2026-06-02T23:45:00Z - `b12eb9b4-ce17-4eda-910b-3ad3e507ab53.jsonl`
- `/ll:wire-issue` - 2026-06-02T23:30:00 - `3b0a90a1-2b16-41b1-bc9f-bda420fe11ad.jsonl`
- `/ll:format-issue` - 2026-06-02T23:08:59 - `d869663f-6cbd-441f-aa25-5bb3a2dafe09.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:42 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:58 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:44:01 - `6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:34:34 - `922ffae8-14ce-45e5-a71a-02187250e8c9.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:refine-issue` - 2026-05-30T04:07:39 - `e590197b-2b0f-4699-acf6-c57e4d6cdbaf.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Variant C (the static Plan→Research→Implement→Report FSM template) and FEAT-1808's `loop-composer` serve distinct use cases and should not be conflated. Variant C is the right choice when the workflow phases are known in advance — "I want to ship this task with a planning phase, ship it now." FEAT-1808 is for when the workflow itself must be discovered at runtime from a natural-language goal. Once FEAT-1808 ships, Variant C's generated YAML should include a commented-out upgrade note pointing users toward `loop-composer` as the recommended upgrade path for goals too open-ended for a fixed template.
