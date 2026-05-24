---
id: ENH-1666
type: ENH
status: open
priority: P2
discovered_date: 2026-05-23
discovered_by: manual
labels:
- create-loop
- wizard
- loops
- meta-loop
- harness
- shor
parent: EPIC-1663
relates_to:
- ENH-1664
- ENH-1665
depends_on:
- ENH-1665
decision_needed: false
confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1666: `create-loop` wizard branch — "Optimize a harness (meta-loop)"

## Summary

Add a new loop-type branch to the `create-loop` wizard that generates a
diagnosis-first, scorer-required, non-LLM-gated meta-loop template. The
generated YAML satisfies ENH-1665's MR-1 lint rule by construction.

This is the generation layer of EPIC-1663 — it ensures that loops created
through the wizard (the recommended path) never need to hit the validator
error in the first place.

## Motivation

SHOR §6.2 Finding 2: "Good agent harnesses are not necessarily good
optimizer harnesses." The current wizard generates the same 5-phase pipeline
regardless of whether the inner skill operates on data or on harness
artifacts. SHOR §7.1 prescribes a diagnosis-first shape: optimizers
benefit from decoupling priority identification from update actions
("the optimizer first identifies the component requiring the most prioritized
attention before committing to an update"). The wizard should encode this
shape as a template.

`harness-optimize.yaml` is the canonical positive example — it uses a numeric
scorer + `convergence` gate with no `check_semantic`. This branch generates a
standalone variant of that pattern (NOT inherited via `from:` — decision
locked in EPIC-1663).

## Wizard Flow

### Step 1 — Add to loop-type selection

In `skills/create-loop/SKILL.md` Step 1 (line ~73), add a new option to the
loop-type AskUserQuestion:

```yaml
- label: "Optimize a harness (meta-loop)"
  description: "Iteratively improve a loop YAML, skill, agent, or command using an external scorer. Generates diagnosis-first scaffolding required for meta-loops (SHOR-compliant)."
```

Map to type: `meta-optimize` → states: `diagnose, baseline, propose, apply, score, gate, commit_or_revert, done`.

### Step 2 — Type-specific questions (new section in `loop-types.md`)

Five required questions:

1. **What harness artifact(s) will this loop modify?**
   - Loop YAML(s) (under `loops/` or `scripts/little_loops/loops/`)
   - Skill (`skills/<name>/SKILL.md`)
   - Agent (`agents/<name>.md`)
   - Command (`commands/<name>.md`)
   - Custom paths (via Other)

   Captured as the `targets` context variable.

2. **What scorer command produces a numeric quality signal?** (REQUIRED — no
   default; refuse to proceed without one. Mirrors the wizard's existing
   refusal to omit `discover` in multi-item mode.)

   Captured as the `scorer` context variable. Example placeholders shown:
   - `./scripts/score.sh` (custom script)
   - `pytest scripts/tests/test_meta.py -q --tb=no` (test-as-scorer)
   - `python -m little_loops.bench.score` (Python entry point)

3. **What is the score target / early-stop threshold?** Default 1.0 (never
   early-stop; only commit on improvement).

4. **Where is the task / benchmark directory?** Captured as `tasks_dir`.
   Validated to exist if not empty.

5. **What is the diagnose action?** (Required.) A shell command or prompt
   that surfaces what is currently wrong with the harness artifact —
   typically: read recent runs from `.loops/runs/`, list current failure
   modes, summarize what would benefit most from being changed. Output is
   captured as `diagnosis` and consumed by the `propose` state. This is the
   SHOR §7.1 priority-identification step.

### Step 3 — Generated YAML template (standalone, no `from:`)

```yaml
name: <loop-name>
description: |
  <user-provided description>
initial: diagnose
max_iterations: 30
timeout: 7200
context:
  targets: "<user-provided>"
  tasks_dir: "<user-provided>"
  scorer: "<user-provided>"
  target_score: <user-provided>

states:
  diagnose:
    action_type: <shell|prompt>
    action: |
      <user-provided diagnose action>
    capture: diagnosis
    next: baseline

  baseline:
    action_type: shell
    action: "${context.scorer} ${context.tasks_dir}"
    capture: baseline_score
    evaluate:
      type: exit_code
    on_yes: propose
    on_no: done
    on_error: done

  propose:
    action_type: prompt
    timeout: 300
    action: |
      Current harness artifact: ${context.targets}
      Diagnosis from previous step: ${captured.diagnosis.output}
      Baseline score: ${captured.baseline_score.output}

      Propose ONE targeted edit to ${context.targets} that addresses the
      highest-priority issue identified in the diagnosis. Output the revised
      content only — no preamble, no markdown fences.
    capture: candidate
    next: apply

  apply:
    action_type: prompt
    timeout: 120
    action: |
      Apply this proposed change to ${context.targets}:
      ${captured.candidate.output}
      Confirm the change has been applied.
    next: score

  score:
    action_type: shell
    action: "${context.scorer} ${context.tasks_dir}"
    capture: new_score
    evaluate:
      type: exit_code
    on_yes: gate
    on_no: revert
    on_error: revert

  gate:
    action_type: shell
    action: |
      echo "${captured.new_score.output}" | tail -1 | tr -d '[:space:]'
    evaluate:
      type: convergence
      direction: maximize
      target: "${context.target_score}"
      previous: "${captured.baseline_score.output}"
      tolerance: 0.02
    route:
      target: commit
      progress: commit
      stall: revert
      error: revert

  commit:
    action_type: shell
    action: |
      git add ${context.targets}
      git commit -m "${loop.name}: iter ${state.iteration}, score ${captured.new_score.output}"
    next: diagnose

  revert:
    action_type: shell
    action: "git restore ${context.targets}"
    next: done

  done:
    terminal: true
```

Notable properties:
- **Diagnose state is initial** — implements SHOR §7.1.
- **No `check_semantic`** — non-LLM `convergence` gate is the success
  signal. Generated YAML passes ENH-1665 MR-1 by construction.
- **Standalone, not inherited** — per EPIC-1663 design decision 3.
- **Re-enters at `diagnose`** after a successful commit so each iteration
  re-prioritizes against the new baseline.

### Step 4 — Refusal logic

If the user tries to skip the scorer question or provide an empty value,
the wizard refuses to proceed and explains why (mirror of how the wizard
already refuses to omit `discover` in multi-item harness mode).

## Implementation Steps

1. **`skills/create-loop/SKILL.md` lines 72–91**: In `### Step 1: Loop
   Type Selection (Custom Mode Only)`, add a new `options:` entry to the
   AskUserQuestion block after the last RL option. Then add a new `->` line
   to the `**Type Mapping:**` block (lines 82–90):
   `"Optimize a harness (meta-loop)" -> meta-optimize type (states: diagnose, baseline, propose, apply, score, gate, commit_or_revert, done)`

2. **`skills/create-loop/loop-types.md` after line ~1029**: The
   "## Harness Questions" section spans lines 549–1029. Insert the new
   "## Optimize a Harness (Meta-Loop) Questions" section **after** the
   Harness section ends (after the last worked example) and **before**
   `## Sub-Loop Composition`. Include the 5-question flow, the YAML
   template above, a worked example, and the scorer refusal guard.
   Model the structure on the Harness section (Steps H1–H4 + Generate
   YAML subsection). Use the abort pattern from
   `skills/rename-loop/SKILL.md:57–73` for the scorer refusal message.

3. **`skills/create-loop/templates.md`**: Add `meta-optimize` to:
   - `## Step 0.1` AskUserQuestion options list (one new option)
   - `## Template Definitions` — new `### Template: meta-optimize` subsection
     with `{{targets}}`, `{{scorer}}`, `{{target_score}}`, `{{tasks_dir}}`,
     `{{diagnose_action}}`, `{{max_iterations}}` placeholders
   - `## Step 0.2` — new `### For "Optimize a harness (meta-loop)"` customization
     question flow mirroring the harness template flow (lines 243–277)

4. **Smoke test** (manual): Invoke `/ll:create-loop`, select "Optimize a
   harness (meta-loop)", complete the 5-question flow, and verify the
   generated YAML passes `ll-loop validate` (MR-1 from ENH-1665 must not
   fire). Expected: clean validation with `convergence` gate satisfying
   `NON_LLM_EVALUATOR_TYPES` in `scripts/little_loops/fsm/validation.py:76–94`.

5. **Refusal test** (manual): Attempt to leave the scorer field empty and
   verify the wizard refuses to proceed with an error message following the
   abort pattern: `Error: scorer is required for meta-optimize loops. ...`

## Verification

- Generated YAML for a meta-loop validates clean under ENH-1665's MR-1.
- The wizard refuses to proceed without a scorer command.
- A worked example (e.g., "optimize the docs-sync loop") produces a
  runnable YAML.

## Scope Boundaries

**In scope:**
- New wizard branch in `create-loop` SKILL.md, loop-types.md, templates.md
- Standalone YAML template (no inheritance)
- Required scorer + diagnose-state refusal logic

**Out of scope:**
- Modifying existing wizard branches
- The validator rule itself (ENH-1665)
- Documentation of `meta_self_eval_ok` field (covered in ENH-1665)
- Auto-generating scorer scripts

## Impact

- **Priority**: P2 — the recommended creation path for meta-loops; pairs
  with ENH-1665 to make the design rule discoverable + enforceable.
- **Effort**: Medium — wizard prose + question flow + YAML template + smoke test.
- **Risk**: Low — additive; existing branches unaffected.
- **Breaking Change**: No
- **Depends on**: ENH-1665 (validator must exist so the generated YAML can
  be verified to pass it).

## Related Documentation

| Document | Relevance |
|----------|-----------|
| `skills/create-loop/SKILL.md:73` | Loop type selection — insertion point |
| `skills/create-loop/loop-types.md:549` | "Harness Questions" section — model for new section |
| `skills/create-loop/templates.md` | Template registry |
| `scripts/little_loops/loops/harness-optimize.yaml` | Positive template that the wizard branch mirrors |
| `docs/research/Towards-Direct-Evaluation-of-Harness-Optimizers.md` | SHOR §6.2 Finding 2, §7.1 |

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify

- `skills/create-loop/SKILL.md:72–91` — Step 1 AskUserQuestion options list and Type Mapping block; add one option entry and one `->` mapping line
- `skills/create-loop/loop-types.md:~1030` — insert new `## Optimize a Harness (Meta-Loop) Questions` section after the Harness section ends (line ~1029) and before `## Sub-Loop Composition`
- `skills/create-loop/templates.md` — add option to Step 0.1, new template in `## Template Definitions`, and new customization flow in `## Step 0.2`

### Reference Files (No Changes)

- `scripts/little_loops/loops/harness-optimize.yaml` — canonical meta-loop; the generated standalone template mirrors its diagnose → baseline → propose → apply → score → gate → commit/revert shape
- `scripts/little_loops/fsm/validation.py:76–94` — `NON_LLM_EVALUATOR_TYPES` frozenset and `_validate_meta_loop_evaluation()` (MR-1/MR-2 rules); the generated `convergence` gate satisfies MR-1 by construction
- `scripts/little_loops/fsm/schema.py:890` — `FSMLoop.meta_self_eval_ok: bool = False` field (added by ENH-1665)

### Abort Pattern Reference

- `skills/rename-loop/SKILL.md:57–73` — canonical abort-with-error text pattern to mirror for scorer refusal guard

### Tests (No New Tests Required — Smoke and Refusal Are Manual)

- `scripts/tests/test_create_loop.py` — existing create-loop tests; review for any structure tests that cover loop-type options
- `scripts/tests/test_harness_optimize.py` — positive control that validates `harness-optimize.yaml` structure; use as model for any automated structural test of generated output
- `scripts/tests/test_fsm_validation.py` — `TestMetaLoopValidation` class (9 tests); generated YAML should pass all MR-1/MR-2 checks without needing `meta_self_eval_ok: true`

## Labels

- create-loop
- wizard
- loops
- meta-loop
- harness
- shor

## Verification Notes

_Verified 2026-05-24 by `/ll:verify-issues`:_ Soft-blocked on ENH-1665. The
generated YAML's "satisfies MR-1 by construction" claim cannot be checked
until ENH-1665 lands MR-1 in `scripts/little_loops/fsm/validation.py` and
`meta_self_eval_ok: bool` is added to `FSMLoop` (`scripts/little_loops/fsm/schema.py:844`).
All other anchors verified: `skills/create-loop/SKILL.md:73` (loop-type
AskUserQuestion), `skills/create-loop/loop-types.md:549` ("Harness Questions"
insertion point), and `scripts/little_loops/loops/harness-optimize.yaml`
(positive template) all exist as referenced.

_Updated 2026-05-24 by `/ll:refine-issue`:_ ENH-1665 is now `done` — the
soft-block is resolved. `_validate_meta_loop_evaluation()`,
`_is_meta_loop()`, and `NON_LLM_EVALUATOR_TYPES` are present in
`scripts/little_loops/fsm/validation.py:76–94`, and `meta_self_eval_ok:
bool = False` is at `scripts/little_loops/fsm/schema.py:890`. The loop-types.md
insertion point is after line ~1029 (end of the Harness Questions section),
not line ~549 (the section start) — the new section must go before
`## Sub-Loop Composition`. Loop type selection in SKILL.md is lines 72–91
(`### Step 1: Loop Type Selection (Custom Mode Only)` + `**Type Mapping:**`
block). Ready to implement.


## Session Log
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c74fe13-a75b-4713-911f-502cf9b5e015.jsonl`
- `/ll:refine-issue` - 2026-05-24T13:49:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/28bd77b9-9805-4ea8-8f7b-b71214070553.jsonl`
- `/ll:verify-issues` - 2026-05-24T07:01:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08ba673b-967b-4af4-a548-692288b5485d.jsonl`
- `/ll:confidence-check` - 2026-05-24T14:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/68308df8-d2af-4e2a-9ef6-be8a8320ae61.jsonl`
