---
id: ENH-1666
type: ENH
status: open
priority: P2
discovered_date: 2026-05-23
discovered_by: manual
labels: [create-loop, wizard, loops, meta-loop, harness, shor]
parent: EPIC-1663
relates_to: [ENH-1664, ENH-1665]
depends_on: [ENH-1665]
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

1. **`skills/create-loop/SKILL.md`**: Add new loop-type option to Step 1
   AskUserQuestion. Add type mapping `meta-optimize` → state list.
2. **`skills/create-loop/loop-types.md`**: Add new top-level section
   "## Optimize a Harness (Meta-Loop) Questions" after the existing
   "## Harness Questions" section (line ~549). Include the 5-question
   flow, the YAML template above, and a worked example.
3. **`skills/create-loop/templates.md`**: Add `meta-optimize-template`
   pointing to the same generated YAML for users who start from template.
4. **Smoke test** (manual): Invoke `/ll:create-loop`, select "Optimize a
   harness (meta-loop)", complete the question flow, and verify the
   generated YAML passes `ll-loop validate` (i.e., MR-1 from ENH-1665
   does not fire).
5. **Refusal test** (manual): Try to leave the scorer field empty and
   verify the wizard refuses to proceed.

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

## Labels

- create-loop
- wizard
- loops
- meta-loop
- harness
- shor
