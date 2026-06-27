---
id: FEAT-2354
title: "Built-in FSM loop that generates reusable Claude Code workflows"
type: FEAT
priority: P3
status: open
captured_at: "2026-06-27T22:11:29Z"
discovered_date: 2026-06-27
discovered_by: capture-issue
labels: [loops, meta-loop, codegen, harness]
---

# FEAT-2354: Built-in FSM loop that generates reusable Claude Code workflows

## Summary

Add a new built-in FSM loop — in the same family as our artifact-generator loops
(`html-website-generator`, `svg-image-generator`, `generative-art`, `p5js-sketch-generator`,
etc.) — that, instead of emitting an HTML/SVG/visual artifact, emits a **reusable Claude Code
workflow script** that automates a repeatable piece of work.

The recommended design (from the source brainstorm) is a **staged "compiler-lowering" loop**:
the workflow is generated through sequential FSM passes, each specializing in one semantic
"lowering" rather than producing the entire workflow in a single prompt. This is a **meta-loop**
(it generates harness artifacts), so it must follow the stricter meta-loop design rules in
`.claude/CLAUDE.md` § Loop Authoring (MR-1 through MR-6) — most importantly, every
`check_semantic`/`llm_structured` state must be paired with a non-LLM evaluator.

## Motivation

Today little-loops can generate visual/interactive artifacts via a whole family of generator
loops, but there is no built-in path to generate the *automation* artifact itself — a runnable
workflow that captures repeatable work. Users who want to automate a recurring multi-step task
must hand-author workflow scripts (or FSM YAML) directly. A generator loop closes that gap and
makes the harness self-extending: describe the repeatable work, get back a validated, minimal,
reusable workflow.

The "compiler-lowering" framing is the decisive design choice: it diagnoses *why* single-prompt
workflow generation fails (it conflates intent, structure, evaluation, and routing into one
intractable sub-problem) and fixes it structurally. Because each lowering pass maps onto an
existing non-LLM evaluator type already in the harness (`ll-loop validate` exit-code, schema
check, diff-stall), the meta-loop MR-1 requirement is satisfied **by architecture, not
convention** — and the generation trace is deterministic and debuggable rather than a single
opaque "the workflow doesn't behave correctly" verdict.

## Current Behavior

- Artifact-generator loops exist for visual/interactive outputs only:
  `scripts/little_loops/loops/{html-website-generator,svg-image-generator,generative-art,
  p5js-sketch-generator,canvas-sketch-generator,openscad-model-generator,pixi-generative-art,
  rlhf-svg-generate}.yaml`.
- No built-in loop emits a reusable Claude Code workflow. To create one, a user invokes
  `/ll:create-loop` (interactive wizard for FSM YAML) or hand-writes a Workflow script.
- `/ll:create-loop`'s "Optimize a harness" branch produces meta-loop scaffolding, but there is
  no generator loop whose *output artifact* is itself a reusable workflow.

## Expected Behavior

A new built-in loop (working name: `workflow-generator`) that:

1. Takes a generative brief (prose task description, and/or a mined session pattern) as input.
2. Runs sequential FSM lowering passes:
   - **Intent capture** — distill the brief into a structured intent spec.
   - **State-graph sketch** — propose the workflow's state graph. *(Diversity-injection point —
     see Proposed Solution.)*
   - **Evaluator attachment** — attach a non-LLM discriminator to each generated state.
   - **Routing-table resolution** — resolve transitions / route completeness.
   - **YAML (or Workflow-script) emission** — emit the artifact.
   - **Adversarial minimum-coupling shrink** — probe with edge-case inputs and excise any state
     whose removal does not change an outcome, producing the *smallest* workflow that passes all
     probes rather than the most complete one.
3. Validates the emitted artifact with `ll-loop validate` (non-LLM, exit-code) at the pass
   boundaries where it applies.
4. Writes per-iteration artifacts under `${context.run_dir}/` (MR-3) and snapshots each
   iteration's output (MR-5), since this is an iterative generate→evaluate cycle.

## Proposed Solution

TBD — requires investigation. Direction from the brainstorm (ranked shortlist):

- **Rank 1 — Compiler lowering (core).** Stage the generation as the FSM passes above; each pass
  is a tractable sub-problem with a non-LLM discriminator, satisfying MR-1 structurally.
- **Rank 2 — Scoped genetic graft (state-graph pass only).** At the single most-uncertain
  decision (the state-graph sketch), generate N candidate sketches in parallel and select the
  best by `ll-loop validate` exit-code before continuing. Scope recombination to this one pass to
  get global exploration where the design space is widest while keeping lowering deterministic
  and auditable everywhere else.
- **Rank 3 — Adversarial minimum-coupling shrink (final pass).** Operationalize "reusability is a
  property of minimum coupling, not completeness": remove a state, re-run the probe set, and keep
  the removal if no outcome changed. External, repeatable, binary — a sound non-LLM evaluator.

These three address orthogonal failure modes (conflation, local convergence, over-specification)
and compose into a single six-pass FSM without redundancy.

**Open design questions:**
- Output target: emit FSM-loop YAML, a Workflow JS script, or selectable? (The brainstorm spans
  both; the generator family currently emits artifacts, and the Workflow tool emits JS scripts.)
- Whether to support the "mine observed behavior" input mode (generate from `.ll/history.db` /
  session traces) in v1 or defer to a follow-on.
- How the shrink pass's "probe set" is defined for a non-executable-by-default workflow.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/workflow-generator.yaml` — new built-in loop (NEW).
- Loop registry / packaging that enumerates built-in loops (TBD — confirm how
  `scripts/little_loops/loops/*.yaml` are registered/listed by `ll-loop list`).

### Dependent Files (Callers/Importers)
- TBD — grep for how the generator-family loops are referenced/tested.

### Similar Patterns
- `scripts/little_loops/loops/html-website-generator.yaml` and sibling generator loops — model
  the new loop's structure on these.
- `scripts/little_loops/loops/harness-optimize.yaml` — meta-loop reference for MR-1..MR-6 shape.

### Tests
- `scripts/tests/test_builtin_loops.py` — add coverage that the new loop validates
  (`ll-loop validate`) and conforms to meta-loop rules (MR-1 paired evaluators, MR-3 run_dir
  isolation, MR-5 artifact versioning).

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` and/or `AUTOMATIC_HARNESSING_GUIDE.md` — document
  the new generator loop.
- `.claude/CLAUDE.md` Automation & Loops listing if user-facing.

### Configuration
- N/A (uses existing `loops.run_defaults`; per-run artifacts under `${context.run_dir}/`).

## Use Case

A user has just finished a tedious, repeatable multi-step task (e.g., "triage a new bug report:
read it, grep for the offending code, confirm repro, draft a fix plan, open a PR"). They run the
new generator loop with a one-paragraph description of that work and get back a validated,
minimal, reusable Claude Code workflow they can re-invoke on the next bug — without writing any
FSM/YAML by hand.

## Source

Captured from brainstorm: `.loops/runs/brainstorm-20260627T164631/brainstorm.md`.

## Session Log
- `/ll:capture-issue` - 2026-06-27T22:11:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e61208ac-a505-4f00-9646-b676ce7f4f5f.jsonl`

---

## Status

**Current Status**: open
