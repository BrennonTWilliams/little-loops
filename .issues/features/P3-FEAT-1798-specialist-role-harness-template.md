---
id: FEAT-1798
type: FEAT
title: Specialist-role harness template (Plan → Research → Implement → Report)
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
relates_to: [ENH-1796]
parent: EPIC-1694
decision_needed: false
blocked_by: [FEAT-1808]
decision: Option B — omit HITL gates, ship as autonomous pipeline (Plan → Research → Implement → Report without human gates). Simplest, works today. Include commented-out HITL block for future activation when FEAT-1794 lands. Upgrade to Option C after FEAT-1794.
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
| `skills/create-loop/loop-types.md` | Wizard implementation (lines 548–914 for Harness Questions) |
| `FEAT-1794` | HITL state type — preferred (not strictly required) for inter-role gates |
| `ENH-1796` | Shared message log — improves prompt quality across the role chain |

## Integration Map

### Files to Modify
- `skills/create-loop/SKILL.md` — Step 1 loop type selection (~line 136): add "Specialist role pipeline" option; update Step 2 delegation to reference new question flow
- `skills/create-loop/loop-types.md` — After Harness Questions section (after line 914): add `## Specialist Pipeline Questions` with S1-S5 question flow and Variant C FSM YAML template block
- `skills/create-loop/templates.md` — Add Variant C template entry if available in "Start from template" path (Step 0.1)
- `skills/create-loop/reference.md` — Add specialist pipeline state structure to "Loop Type State Structures" section

### Files to Create
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml` — Runnable annotated example (Variant C), matching `harness-single-shot.yaml` / `harness-multi-item.yaml` pattern with `# EXAMPLE:` comments

### Dependent Files (Documentation)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Add `### Variant C: Specialist-Role Pipeline` section after Variant B (after line ~561), plus entry in "Using the Example Files" table
- `scripts/little_loops/loops/README.md` — Add Variant C entry under "Harness / Templates" section

### Similar Patterns (Existing Code to Model After)
- `skills/create-loop/loop-types.md:700-857` — Variant A and B FSM YAML templates with conditional-phase comments — exact pattern to replicate
- `skills/create-loop/loop-types.md:548-694` — Harness Questions H1-H4 question flow (`AskUserQuestion` blocks) — structure to replicate for S1-S5
- `scripts/little_loops/loops/harness-single-shot.yaml` — Annotated example format with `# EXAMPLE:` block comments — format to follow
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — Existing plan → refine → gate → implement pipeline with `capture` handoff — structural precedent
- `scripts/little_loops/loops/rn-plan.yaml` — Plan → Research → Refine → Score pipeline — closest existing phase decomposition
- `scripts/little_loops/loops/deep-research.yaml` — Research → Synthesis pipeline with per-run artifact isolation (`capture: run_dir`)

### Tests
- `scripts/tests/test_builtin_loops.py:66` — `test_expected_loops_exist` — add new Variant C name to expected set
- `scripts/tests/test_builtin_loops.py:30,37,47` — `test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, `test_all_have_description_field` — auto-cover new YAML in loops dir
- `scripts/tests/test_create_loop.py` — Add YAML pattern validation for Variant C output following existing `TestLoopFileValidation` pattern

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

## Labels

`captured`, `create-loop`, `fsm`, `harness`, `loops`, `templates`

## Status

**Open** | Created: 2026-05-29 | Priority: P3

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-31T21:44:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:34:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/922ffae8-14ce-45e5-a71a-02187250e8c9.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:refine-issue` - 2026-05-30T04:07:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e590197b-2b0f-4699-acf6-c57e4d6cdbaf.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Variant C (the static Plan→Research→Implement→Report FSM template) and FEAT-1808's `loop-composer` serve distinct use cases and should not be conflated. Variant C is the right choice when the workflow phases are known in advance — "I want to ship this task with a planning phase, ship it now." FEAT-1808 is for when the workflow itself must be discovered at runtime from a natural-language goal. Once FEAT-1808 ships, Variant C's generated YAML should include a commented-out upgrade note pointing users toward `loop-composer` as the recommended upgrade path for goals too open-ended for a fixed template.
