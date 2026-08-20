---
id: ENH-3267
type: ENH
title: Inject the DESIGN.md prose body as design_guidance_context
priority: P2
status: open
depends_on:
- BUG-3266
- ENH-3264
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T21:10:34Z'
labels:
- enhancement
- design-tokens
- loops
---

# ENH-3267: Inject the DESIGN.md prose body as design_guidance_context

## Summary

Carry a DESIGN.md's **prose body** — not just its token values — into generator prompts as a new runner-injected FSM context variable, `design_guidance_context`, and consume it in `loops/html-website-generator.yaml`.

Today `design_tokens_context` carries values only. There is no channel for design *intent*: the "Do's and Don'ts", "Overview", and "Elevation & Depth" prose a project authors about its own visual identity.

## Current Behavior

`loops/html-website-generator.yaml:37-50` hand-rolls a generic design brief, and lines 46-48 / 74-76 hardcode a fixed anti-slop "anti-patterns to avoid" list — the same text for every project, with no way for a project to supply its own.

`design_tokens_context` (injected at `cli/loop/run.py:242-254`) carries resolved token values and nothing else.

## Expected Behavior

1. A project whose DESIGN.md has a prose body gets that body injected as `design_guidance_context` on both `ll-loop run` and `ll-loop resume`.
2. `html-website-generator.yaml` consumes it in the `plan` state's brief and in `run_gen_eval.generate_prompt`'s anti-slop clause, so a project's own "Do's and Don'ts" replaces (or augments) the hardcoded list.
3. `design_guidance_context` resolves to `""` when absent, so `${context.design_guidance_context}` never hard-fails interpolation for the other built-in loops.
4. `use_design_tokens: false` suppresses it alongside `design_tokens_context`.

## Motivation

Per ENH-3264's Motivation section, the prose body is **arguably the bigger win than the tokens**. A project's authored design intent is exactly the content the generator loop currently hardcodes generically, and there is no existing channel for it.

Filed as its own issue so this does not sit behind the DESIGN.md exporter landing.

## Proposed Solution

1. `DesignTokens` gains a `guidance: str = ""` field (default required — the dataclass is frozen with 5+ construction sites). Populated by ENH-3264's `_load_design_md()` from `strip_frontmatter()`; empty for profile-sourced projects.
2. Inject `design_guidance_context` through the **shared helper** introduced by the `cmd_resume` opt-out bug fix, so `cmd_run` and `cmd_resume` cannot diverge and the `use_design_tokens` gate covers both variables by construction.
3. Consume in `html-website-generator.yaml` only.

Optionally expose `render_body_as_prompt_context(body: str) -> str` if the body needs framing (a heading, a truncation bound) rather than raw pass-through — decide at implementation time.

## Integration Map

### Files to Modify
- `scripts/little_loops/design_tokens.py:26-34` — `DesignTokens.guidance: str = ""`
- `scripts/little_loops/cli/loop/run.py` + `scripts/little_loops/cli/loop/lifecycle.py` — via the shared injection helper, not two copies
- `scripts/little_loops/loops/html-website-generator.yaml` — `plan` (`:37-50`), `run_gen_eval.generate_prompt` (`:60-79`)

### Dependent Files
- The 14 other built-in loops under `scripts/little_loops/loops/*.yaml` (`svg-textgrad`, `svg-image-generator`, `rlhf-svg-refine`, `rlhf-svg-generate`, `rlhf-animated-svg`, `pixi-generative-art`, `pixi-data-viz`, `interactive-component-generator`, `html-anything`, `hitl-md`, `hitl-compare`, `generative-art`, `flux-image-generator`, `canvas-sketch-generator`) must keep receiving `design_tokens_context` unchanged and are **not** wired to the new variable in this issue.
- `scripts/tests/test_ll_loop_program_md.py:308` — the only `DesignTokens(...)` construction outside `design_tokens.py`; uses keyword args, so a defaulted new field is safe. Confirm at implementation time.

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py:921-948` and `:1397-1480` — `design_guidance_context` counterparts for the `cmd_resume` injection and the opt-out
- `scripts/tests/test_builtin_loops.py:8882` (`test_context_has_design_tokens_context`, class at `:8778`) — add `test_context_has_design_guidance_context`

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — add `design_guidance_context` to the `html-website-generator` row
- `docs/generalized-fsm-loop.md:1099` — global runner-injected-context table, with matching `use_design_tokens: false` opt-out semantics

## Implementation Steps

1. Add `guidance: str = ""` to `DesignTokens`.
2. Extend the shared injection helper to set `design_guidance_context` under the same `use_design_tokens` gate, defaulting to `""`.
3. Consume in `html-website-generator.yaml`'s `plan` brief and `generate_prompt` anti-slop clause.
4. Tests + docs.

## Impact

- **Scope**: `design_tokens.py` (one field), the shared injection helper, one loop YAML, tests, docs.
- **Compatibility**: additive. Absent a DESIGN.md, `guidance` is `""` and every loop behaves exactly as today.
- **Risk**: low once the shared helper exists — the risk this issue *avoids* is a second parallel copy of the injection block.

## Scope Boundaries

**In scope**
- The `guidance` field, the `design_guidance_context` injection on both run and resume, and consumption by `html-website-generator.yaml` only.

**Out of scope**
- Parsing DESIGN.md. That is ENH-3264; this issue consumes the `guidance` field it populates.
- Extending `design_guidance_context` to the other 14 built-in loops. Broader rollout is a follow-up once the prose channel proves out on one loop.
- Fixing the `cmd_resume` opt-out gap or extracting the shared helper — that is the companion BUG, a hard dependency.

## Acceptance Criteria

1. A DESIGN.md-sourced project's prose body reaches `html-website-generator.yaml`'s `plan` state as `design_guidance_context`.
2. `ll-loop resume` injects `design_guidance_context` identically to `ll-loop run`.
3. `use_design_tokens: false` suppresses **both** `design_tokens_context` and `design_guidance_context`, on **both** `ll-loop run` and `ll-loop resume`.
4. `design_guidance_context` resolves to `""` (not missing) for profile-sourced projects and for all 14 other built-in loops, so `${context.design_guidance_context}` never hard-fails interpolation.
5. All 14 other built-in loops still receive `design_tokens_context` unchanged.
6. `python -m pytest scripts/tests/` exits 0.

## API/Interface

- `little_loops.design_tokens.DesignTokens.guidance: str = ""` — new field
- FSM context: `design_guidance_context` — new, runner-injected, `""` when absent, gated by `use_design_tokens`

## Notes

Split out of ENH-3264. Depends on the shared injection helper from the companion `cmd_resume` opt-out BUG, and on ENH-3264 to populate `guidance` from a parsed DESIGN.md.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P2
