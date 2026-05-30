---
id: FEAT-1807
type: feature
priority: P3
status: open
parent: EPIC-1811
captured_at: "2026-05-30T05:25:35Z"
discovered_date: 2026-05-30
discovered_by: capture-issue
labels: [feat, captured, example-loop, demo, autofigure]
---

# FEAT-1807: Adversarial-Redesign Figure Loop with AutoFigure

## Summary

Add an example FSM loop, `adversarial-redesign`, that demonstrates the
**generator-vs-critic** pattern using [AutoFigure](https://github.com/ResearAI/AutoFigure)
as the artifact generator. A generator agent produces an SVG diagram from a
text concept; a critic agent returns structured complaints; the loop regenerates
addressing each complaint and exits on score-improvement-stall or SVG-diff
convergence. Every round is recorded so the back-and-forth itself is the demo.

The killer demo property: the *transcript* of generator/critic exchange is as
interesting as the final diagram. It plays well as a split-screen recording —
critic complaints scrolling on the left, the SVG morphing on the right.

## Current Behavior

The `loops/` directory ships several example loops that demonstrate eval-driven
refinement on text/code artifacts (e.g. `examples-miner.yaml`,
`eval-driven-development.yaml`), but none produce a **visual artifact** as
output. There is also no example of the explicit
*generator-vs-critic* pattern where two agents trade structured critique across
rounds, with both the per-round diff and the critique transcript surfaced for
inspection.

This leaves a gap in the demo reel: every loop we can show today produces
text/code, which is less visually compelling than watching a diagram morph
in response to critique.

## Expected Behavior

A new example loop file `loops/examples/adversarial-redesign.yaml` (or wherever
example loops live per project conventions) that:

1. Takes a `concept` input (any natural-language description).
2. Seeds an initial SVG via an AutoFigure wrapper.
3. Runs a critic agent that returns structured JSON complaints
   (`{complaints: [...], structural_score: int}`).
4. Gates progress on **two** signals (per project loop authoring rules):
   - **Non-LLM**: AutoFigure's own `final_score` must rise each round
     (`output_numeric` evaluator); bail on stall.
   - **LLM-semantic**: critic must produce zero new structural complaints.
5. Regenerates the figure addressing every complaint.
6. Exits on SVG diff < ε for 2 consecutive rounds (`check_convergence`)
   OR max_iterations reached.
7. Persists every iteration's SVG + critic transcript under
   `.loops/runs/<run_id>/iter-N/` so the full back-and-forth is replayable
   for demo recording.

## Motivation

- **Demo gap**: today's example loops produce text/code; no loop produces a
  visual artifact that morphs across iterations. Visual artifacts are
  meaningfully more compelling for showing FSM mechanics to new users in a
  short video or slide.
- **Pattern coverage**: the explicit generator-vs-critic shape (two adversarial
  agents, structured complaint protocol) is not represented in existing
  examples. It is a common pattern worth a reference implementation.
- **CLI-Anything onramp**: AutoFigure is a strong proof point that
  ll-loops can wrap *any* CLI-Anything-style creative generator. Shipping a
  polished example reduces friction for users who want to harness other
  generators (Inkscape, Manim, image models, etc.).

## Use Case

A user wants to demo the FSM-loop concept to a teammate in under a minute.
They run:

```bash
ll-loop run adversarial-redesign --input concept="how a transformer attends"
```

They watch the terminal stream `iter-1 → critic flagged 4 issues → iter-2 →
score 6.2 → 7.8 → critic flagged 1 issue → iter-3 → converged`. Afterwards,
`.loops/runs/<id>/` contains `iter-1.svg` through `iter-3.svg` plus a
`transcript.md` interleaving each critic complaint with the regeneration
prompt it produced. The user opens the SVGs side-by-side and the morph is
self-evidently the FSM doing useful work — no explanation needed.

## Acceptance Criteria

- [ ] `loops/examples/adversarial-redesign.yaml` exists and passes
      `ll-loop validate` (no MR-1 violations — the `check_semantic` critic
      MUST be paired with at least one of `output_numeric` /
      `check_convergence` / `exit_code`).
- [ ] A thin wrapper script (e.g. `scripts/autofigure_wrapper.py`) returns
      `{svg_path, final_score, iteration}` as JSON on stdout for one
      AutoFigure generation call, enabling `output_numeric` evaluators
      to read `.final_score` deterministically.
- [ ] `ll-loop run adversarial-redesign --input concept="<any text>"`
      completes successfully end-to-end on a developer machine with
      AutoFigure installed and an OpenRouter (or compatible) API key
      configured via env var.
- [ ] Every iteration writes:
      - `iter-N.svg` (the generated diagram)
      - `iter-N-critique.json` (structured critic output)
      - to a run-scoped directory under `.loops/runs/<run_id>/`.
- [ ] A `transcript.md` is written at run end that interleaves each
      iteration's critique with the regeneration prompt it produced.
- [ ] Loop exits on EITHER: (a) AutoFigure `final_score` failing to
      improve for 2 consecutive rounds, (b) SVG diff < ε for 2
      consecutive rounds, (c) max_iterations (default 5).
- [ ] README or example index lists the new loop with a one-line
      pitch and an example invocation.
- [ ] Loop is documented as requiring AutoFigure as an optional dependency
      (not installed by default — separate `pip install` step documented
      in the loop's preamble comment).

## API/Interface

```yaml
# loops/examples/adversarial-redesign.yaml (sketch)
name: adversarial-redesign
description: Generator-vs-critic figure refinement demo using AutoFigure
inputs:
  concept: { type: string, required: true }
  max_iterations: { type: int, default: 5 }

states:
  seed:
    action: shell
    cmd: python scripts/autofigure_wrapper.py --concept "${inputs.concept}"
    capture: seed
    next: critic

  critic:
    action: llm_structured
    schema: { complaints: list[str], structural_score: int }
    prompt_ref: prompts/adversarial-critic.md
    next: score_floor

  score_floor:
    action: check_numeric
    expr: "${captured.regen.final_score} > ${captured.previous.final_score}"
    on_yes: regen
    on_no: exit

  regen:
    action: shell
    cmd: python scripts/autofigure_wrapper.py --concept "${inputs.concept}"
                                              --critique "${captured.critic.complaints}"
    capture: regen
    next: convergence

  convergence:
    action: check_convergence
    field: regen.svg_path
    rounds: 2
    on_converged: exit
    on_diverged: critic
```

```python
# scripts/autofigure_wrapper.py (sketch)
# usage: python autofigure_wrapper.py --concept "..." [--critique "..."]
# emits: {"svg_path": "...", "final_score": 8, "iteration": 1}
```

## Proposed Solution

1. **Add wrapper script** `scripts/autofigure_wrapper.py` that calls
   `AutoFigureAgent.generate(...)` and prints a single JSON line to stdout.
   Critique input becomes a constraint suffix on the AutoFigure description.
2. **Author the loop YAML** using the standard 5-phase shape but with the
   explicit critic state surfaced by name (rather than baked into a
   monolithic `do_work` prompt) so the FSM diagram visibly shows the
   adversarial round-trip.
3. **Author the critic prompt** in `prompts/adversarial-critic.md` —
   should produce structured complaints (not freeform), e.g.
   `{node_unlabeled: [...], edge_direction_ambiguous: [...], layout_overlap: bool}`.
4. **Wire per-iteration artifact persistence** via the loop's existing
   `capture:` mechanism + a small `do_work` end-state that materializes
   `transcript.md`.
5. **Document the optional AutoFigure dependency** in the loop's preamble
   comment (`pip install -e ./AutoFigure` + `playwright install chromium`).

## Integration Map

### Files to Modify
- New: `loops/examples/adversarial-redesign.yaml` (or per project convention)
- New: `scripts/autofigure_wrapper.py`
- New: `prompts/adversarial-critic.md`

### Dependent Files (Callers/Importers)
- None at creation time; future demo scripts may invoke `ll-loop run adversarial-redesign`.

### Similar Patterns
- `scripts/little_loops/loops/examples-miner.yaml` — example of structured
  capture + child-loop dereference
- `scripts/little_loops/loops/eval-driven-development.yaml` — example of
  numeric eval gate paired with semantic check (the pattern this loop
  must follow per MR-1)

### Tests
- `scripts/tests/test_fsm_validation.py` — add a smoke test that the new
  loop YAML passes `ll-loop validate` (and specifically MR-1)
- Optional integration test: skipped by default (requires AutoFigure +
  API key); gated behind a marker like `@pytest.mark.requires_autofigure`

### Documentation
- README or `docs/` example-loop index needs the new loop listed
- Loop YAML's preamble comment must call out the optional dependency

### Configuration
- N/A — no `.ll/ll-config.json` changes required; the loop reads
  `AUTOFIGURE_API_KEY` (or equivalent) from env directly.

## Implementation Steps

1. Write `scripts/autofigure_wrapper.py` + a unit test stubbing the
   AutoFigure call so the wrapper's JSON contract is locked.
2. Draft `prompts/adversarial-critic.md` with a strict JSON schema.
3. Compose `loops/examples/adversarial-redesign.yaml` and iterate until
   `ll-loop validate` (including MR-1) passes.
4. Run the loop end-to-end against a real AutoFigure install on at least
   3 distinct concepts; verify the per-iteration artifacts + transcript
   are produced.
5. Add the loop to the example index/README with a one-line pitch and
   a screenshot or recording.
6. Add a validation-only smoke test to the existing FSM validation suite.

## Impact

- **Priority**: P3 — high *demo* value, no functional blocker. Useful as a
  reference example for the generator-vs-critic pattern.
- **Effort**: Small — leverages existing FSM primitives; only new code is
  a ~50-line wrapper script, one YAML, and one prompt file.
- **Risk**: Low — example loop, isolated from other harness code. Optional
  dependency on AutoFigure means failure to install does not affect any
  core flow.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Relevance |
| --- | --- |
| `.claude/CLAUDE.md` § Loop Authoring | Mandates non-LLM evaluator pairing with `check_semantic` (MR-1). This loop's `score_floor` + `convergence` states satisfy that rule. |
| `docs/ARCHITECTURE.md` | FSM executor contract that the loop YAML compiles against. |

## Session Log

- `/ll:capture-issue` — 2026-05-30T05:25:35Z — `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aebb9b72-3342-4acd-a90d-d77948da77a9.jsonl`

---

**Open** | Created: 2026-05-30 | Priority: P3
