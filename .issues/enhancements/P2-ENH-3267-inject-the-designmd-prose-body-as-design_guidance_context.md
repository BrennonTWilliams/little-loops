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
confidence_score: 100
outcome_confidence: 93
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 23
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

**Consumption convention confirmed** (from every other `design_tokens_context`-consuming loop, e.g. `canvas-sketch-generator.yaml`, `pixi-data-viz.yaml`, `flux-image-generator.yaml`, `svg-textgrad.yaml`): the FSM has no conditional-interpolation syntax. Every consumer uses a two-part pattern — (1) a bare `${context.<var>}` interpolation alone on its own line (degrades to a blank line when `""`), and (2) a separate prose bullet elsewhere in the prompt phrased "If design tokens are provided above, ..." that carries the "only meaningful when non-empty" semantics. `html-website-generator.yaml`'s existing `design_tokens_context` bullet at lines 77-78 ("If design tokens are provided above, use their semantic names...") is this project's own instance of that convention. `design_guidance_context` should follow the identical two-part shape: a bare interpolation line plus a matching "If design guidance is provided above, ..." bullet — not a template conditional.

**YAML `context:` block declaration is cosmetic, not functional**: `inject_design_context()` mutates `fsm.context` unconditionally (`context[...] = ...` or `context.setdefault(...)`) regardless of whether the loop's own YAML pre-declares the key. Every existing consumer loop still declares `design_tokens_context: ""` in its own `context:` block anyway, purely for self-documentation and to guard any interpolation that might run before injection (e.g. an execution-plan dry-run print). Declaring `design_guidance_context: ""` in `html-website-generator.yaml`'s `context:` block (alongside line 27) is optional for correctness but matches the established convention followed by all 12 other consumer loops — do it for consistency.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_program_md.py:283-337` (`test_design_tokens_context_injected_into_context`) — third site (beyond `test_cli_loop_lifecycle.py` and `test_builtin_loops.py`) exercising `inject_design_context` via `cmd_run`'s dry-run path against a synthetic `test-loop.yaml`; add a `design_guidance_context` counterpart asserting `fsm.context.get("design_guidance_context")` is populated from a mocked `DesignTokens.guidance` the same way `:334` asserts `design_tokens_context` [Agent 2 finding]
- `scripts/tests/test_ll_loop_program_md.py` fixture context blocks at `:178`, `:350`, `:413` (`_make_loop`, synthetic loop YAML) declare `design_tokens_context: ""` but not `design_guidance_context: ""` — add the sibling declaration for consistency with the established per-loop convention [Agent 2 finding]

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — add `design_guidance_context` to the `html-website-generator` row
- `docs/generalized-fsm-loop.md:1099` — global runner-injected-context table, with matching `use_design_tokens: false` opt-out semantics

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:757` — the "Per-loop opt-out (ENH-3099)" paragraph names `context.design_tokens_context` explicitly as the variable the opt-out sets to `""`; extend it to also name `design_guidance_context` now that both are gated by `use_design_tokens` [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Proposed Solution step 1 is already done.** `DesignTokens.guidance: str = ""` already exists at `scripts/little_loops/design_tokens.py:39`, populated at all construction sites (`:407` empty for profile-sourced, `:456`/`:473`/`:483` = prose for design_md-sourced, including degraded paths) by the already-completed dependency ENH-3264. This issue's remaining work is purely the injection (`design_guidance_context`) and consumption sides — no `DesignTokens` field change needed.
- **Stale path/line references corrected**: the shared injection helper (`inject_design_context`) lives at `scripts/little_loops/cli/loop/_helpers.py:1397-1426`, not in `cli/loop/run.py` or `cli/loop/lifecycle.py` as originally stated — those two files only *call* it (`run.py:244`, `lifecycle.py:717`), via `from ...import inject_design_context`. It already exists (landed by the completed dependency BUG-3266) and gates both `design_tokens_context` and (once added) `design_guidance_context` under the same `use_design_tokens` flag.
- `render_as_prompt_context(tokens: DesignTokens) -> str` (`design_tokens.py:545`) renders only `tokens.resolved` — it never touches `tokens.guidance`. Confirmed via full read; no change to this function is needed or implied.
- `loops/html-website-generator.yaml` real path is `scripts/little_loops/loops/html-website-generator.yaml`. Corrected line ranges: `context:` block is lines 24-27 (`design_tokens_context: ""` at line 27); `plan` state prompt body is lines 37-50 (anti-patterns bullet at 47-48, matches original); `run_gen_eval.generate_prompt` is lines 60-79, with `${context.design_tokens_context}` interpolation at line 68 and the anti-slop bullet at lines 74-76 (not 74-78 — line 78 is the following, separate token-usage bullet).
- Test line references corrected: `scripts/tests/test_builtin_loops.py`'s `test_context_has_design_tokens_context` for `html-website-generator` is at line 9041 (class `TestHtmlWebsiteGeneratorLoop` at line 8937), not `:8882`/class at `:8778` as originally cited — the file has grown from other loops' test churn since this issue was filed.
- `docs/generalized-fsm-loop.md`'s "Runner-injected context variables" table spans lines 1094-1101, with the `design_tokens_context` opt-out paragraph at line 1103 (not exactly `:1099` as cited, but the same table/location).
- `docs/guides/LOOPS_REFERENCE.md`'s `html-website-generator` context-variables table (the row to extend) is at lines 1668-1673, specifically the `design_tokens_context` row at line 1672.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

Types, signatures, and the call path for the `design_guidance_context` injection, mirroring the existing `design_tokens_context` mechanism:

### Types

No new data type. `DesignTokens.guidance: str = ""` (`design_tokens.py:39`) already exists and is already populated end-to-end by `load_design_tokens()` — every non-`None` return path sets it (`""` for profile-sourced, prose for design_md-sourced including degraded paths).

### Signatures

- `inject_design_context(context: dict[str, Any], config: BRConfig | None = None) -> None` — existing shared helper (`scripts/little_loops/cli/loop/_helpers.py:1397`); extend in place, do not add a second call site.
- `render_as_prompt_context(tokens: DesignTokens) -> str` — not touched (`design_tokens.py:545`); guidance is passed through raw, never rendered by this function.

`inject_design_context`'s current body:
```python
_use_tokens = context.get("use_design_tokens", True)
if isinstance(_use_tokens, str):
    _use_tokens = _use_tokens.strip().lower() not in ("", "0", "false", "no", "off")
if _use_tokens and not context.get("design_tokens_context"):
    _tokens = load_design_tokens(config)
    context["design_tokens_context"] = render_as_prompt_context(_tokens) if _tokens else ""
else:
    context.setdefault("design_tokens_context", "")
```
`_tokens` (a `DesignTokens | None`) is already in scope inside the `if` branch — `context["design_guidance_context"] = _tokens.guidance if _tokens else ""` reuses it with no second `load_design_tokens()` call. The `else` branch's `context.setdefault("design_tokens_context", "")` needs a sibling `context.setdefault("design_guidance_context", "")` for the opt-out/already-populated path.

### Call Path

`cmd_run` (`cli/loop/run.py:244`) / `cmd_resume` (`cli/loop/lifecycle.py:717`) -> `inject_design_context()` (`_helpers.py:1397`) -> `load_design_tokens()` (`design_tokens.py:354`) -> `context["design_guidance_context"]` set on the mutated `fsm.context` dict -> `${context.design_guidance_context}` interpolated in `html-website-generator.yaml`'s `plan` state prompt and `run_gen_eval.generate_prompt`.

### Decision Rules

N/A — no new gap kind, gate, keyword list, or threshold. This is a value pass-through mirroring the existing `design_tokens_context` mechanism exactly (same `use_design_tokens` gate, same `""`-default guarantee); it introduces no new decision logic of its own.

### Existing Convention Confirmed (single guard caveat)

The existing `if _use_tokens and not context.get("design_tokens_context"):` guard checks only `design_tokens_context`'s truthiness. Mirroring it exactly means `design_guidance_context` inherits the same short-circuit: if a caller pre-populates `design_tokens_context` but not `design_guidance_context`, the `if` branch is skipped and only `setdefault("design_guidance_context", "")` runs in the `else` branch — guidance would resolve to `""` even though tokens were pre-supplied. This is the same behavior the existing single-variable guard already has for any future third variable; no wider gate refactor is in scope for this issue (Scope Boundaries excludes touching the opt-out mechanism itself, that is BUG-3266's territory).

## Implementation Steps

1. Add `guidance: str = ""` to `DesignTokens`.
2. Extend the shared injection helper to set `design_guidance_context` under the same `use_design_tokens` gate, defaulting to `""`.
3. Consume in `html-website-generator.yaml`'s `plan` brief and `generate_prompt` anti-slop clause.
4. Tests + docs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

**Corrected/confirmed test targets** (line numbers in the original Integration Map were stale due to churn in `test_builtin_loops.py` since this issue was filed):
- `scripts/tests/test_cli_loop_lifecycle.py:921-948` (`test_design_tokens_context_injected_via_cmd_resume`) and `:1396-1569` (class `TestDesignTokensOptOut`) — confirmed current; add `design_guidance_context` counterparts asserting the same behavior across both `cmd_run` and `cmd_resume`, including the falsy-string-parametrized opt-out variants.
- `scripts/tests/test_builtin_loops.py:9031-9034` (`test_context_has_design_tokens_context`, class `TestHtmlWebsiteGeneratorLoop` starting at line 8937) — add a sibling `test_context_has_design_guidance_context` asserting `"design_guidance_context" in ctx`.
- Step 3 ("Consume in `html-website-generator.yaml`'s `plan` brief and `generate_prompt` anti-slop clause") should follow the two-part convention confirmed in Proposed Solution: a bare `${context.design_guidance_context}` interpolation line plus a separate "If design guidance is provided above, ..." prose bullet — not a structural conditional.

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


## Session Log
- `/ll:confidence-check` - 2026-08-21T14:28:57 - `08bd38ec-d985-4ff9-b92f-3e3223f35d2e.jsonl`
- `/ll:confidence-check` - 2026-08-21T14:00:15 - `72ec3b4b-10e6-496a-b571-6c6eeff6d6e3.jsonl`
- `/ll:wire-issue` - 2026-08-21T13:57:14 - `d9f3ea69-ab5f-4f68-bd22-6d65aebf22d7.jsonl`
- `/ll:refine-issue` - 2026-08-21T13:41:36 - `644f2c06-0c3c-414e-b6e8-cd05189797bb.jsonl`
