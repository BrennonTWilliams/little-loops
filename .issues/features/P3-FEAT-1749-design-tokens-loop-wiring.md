---
id: FEAT-1749
title: Design-tokens loop wiring — pre-inject context into 6 built-in artifact loops
status: open
priority: P3
type: FEAT
parent: FEAT-1746
discovered_date: 2026-05-27
discovered_by: issue-size-review
labels:
- feat
- loops
- design-system
relates_to:
- EPIC-1751
- FEAT-1747
---

# FEAT-1749: Design-tokens loop wiring — pre-inject context into 6 built-in artifact loops

## Summary

Pre-inject `design_tokens_context` into `fsm.context` at `ll-loop run` and `ll-loop resume` entry points, then update the six built-in artifact-generating loops to reference `${context.design_tokens_context}` in their generation prompts. Depends on FEAT-1747 (loader must exist).

## Parent Issue
Decomposed from FEAT-1746: Design tokens config field with default palette, wired into built-in artifact-generating loops

## Decision

**Option 3 (pre-inject into fsm.context)** was selected by `/ll:decide-issue` on 2026-05-27. Score 11/12, leading on Simplicity and Testability. Slots into the established `run_dir` injection pattern at `cli/loop/run.py:162`. No new setup state needed in loop YAMLs.

**Do NOT use `{{design_tokens_context}}` (Jinja-style) in loop prompts.** The FSM interpolator (`scripts/little_loops/fsm/interpolation.py:VARIABLE_PATTERN`) uses `${namespace.path}` syntax. Correct form: `${context.design_tokens_context}`.

## Proposed Solution

### 1. First injection site — `cli/loop/run.py`

At line ~162 (after `run_dir` is injected), add:

```python
from little_loops.design_tokens import load_design_tokens, render_as_prompt_context

if "design_tokens_context" not in fsm.context:
    config = BRConfig(Path.cwd())
    tokens = load_design_tokens(config)
    fsm.context["design_tokens_context"] = render_as_prompt_context(tokens) if tokens else ""
```

Use the `if ... not in fsm.context:` guard pattern (same as `run_dir`) so `--context design_tokens_context=<override>` from the CLI bypasses the injection.

### 2. Second injection site — `cli/loop/lifecycle.py:cmd_resume`

At lines 444–447, `cmd_resume()` re-injects `run_dir` for resumed loops. After line 476 where `config = BRConfig(Path.cwd())` is already instantiated, add the identical guard:

```python
if "design_tokens_context" not in fsm.context:
    tokens = load_design_tokens(config)
    fsm.context["design_tokens_context"] = render_as_prompt_context(tokens) if tokens else ""
```

Without this, `ll-loop resume` on a loop referencing `${context.design_tokens_context}` produces empty interpolation.

### 3. Loop YAML updates (6 loops)

Each loop needs:
1. A `design_tokens_context: ""` entry in its `context:` block (declares the slot so FSM pre-run context validation passes).
2. `${context.design_tokens_context}` reference in at least one generation prompt (HTML/SVG/MD generation state).

Loops to update:
- `scripts/little_loops/loops/hitl-compare.yaml`
- `scripts/little_loops/loops/hitl-md.yaml`
- `scripts/little_loops/loops/html-website-generator.yaml`
- `scripts/little_loops/loops/html-anything.yaml`
- `scripts/little_loops/loops/svg-image-generator.yaml`
- `scripts/little_loops/loops/svg-textgrad.yaml`

Example addition to a generation state prompt:

```yaml
generate_html:
  action_type: prompt
  action: |
    Generate an HTML page for the following brief.

    Design tokens — use these semantic names and resolved values; do not
    invent new colors:

    ${context.design_tokens_context}

    Brief: ${context.description}
    ...
```

When `design_tokens_context` is `""` (tokens disabled/missing), the section renders as an empty string with no visible effect on the prompt. Loops must not error on empty context.

### 4. Tests

**Update** `scripts/tests/test_ll_loop_program_md.py`:
- Add `test_design_tokens_context_injected_into_context` to `TestCmdRunProgramMdInjection`.
- Fixture loop YAML must declare `design_tokens_context: ""` in its `context:` block.
- Assert `fsm.context.get("design_tokens_context") is not None` after `cmd_run`.
- Follow the exact `test_run_dir_injected_into_context` pattern (lines 252+).

**Update** `scripts/tests/test_builtin_loops.py`:
- Add `test_context_has_design_tokens_context` to each of the 6 per-loop test classes:
  - `TestHtmlWebsiteGeneratorLoop`
  - `TestSvgImageGeneratorLoop`
  - `TestSvgTextgradLoop`
  - `TestHtmlAnythingLoop`
  - `TestHitlCompareLoop`
  - `TestHitlMdLoop`
- Assert `"design_tokens_context" in data.get("context", {})`, mirroring `test_context_has_description` at line 2701.

### 5. End-to-end verification

Run each updated loop on a fresh project with tokens enabled (FEAT-1748 palette present):
- Confirm output uses semantic token names/resolved values.

Run each with `design_tokens.enabled: false`:
- Confirm loop runs end-to-end with no errors.

**FSM evaluator note:** These are artifact-generating loops, not meta-loops — the meta-loop non-LLM-evaluator rule from CLAUDE.md does not apply here.

## Files to Modify

- `scripts/little_loops/cli/loop/run.py` — first injection site (~line 162)
- `scripts/little_loops/cli/loop/lifecycle.py` — second injection site (after line 476)
- `scripts/little_loops/loops/hitl-compare.yaml`
- `scripts/little_loops/loops/hitl-md.yaml`
- `scripts/little_loops/loops/html-website-generator.yaml`
- `scripts/little_loops/loops/html-anything.yaml`
- `scripts/little_loops/loops/svg-image-generator.yaml`
- `scripts/little_loops/loops/svg-textgrad.yaml`
- `scripts/tests/test_ll_loop_program_md.py`
- `scripts/tests/test_builtin_loops.py`

## Acceptance Criteria

- [ ] `design_tokens_context` is present in `fsm.context` after `cmd_run` when tokens are enabled and path exists.
- [ ] `design_tokens_context` is present in `fsm.context` after `cmd_resume` when tokens are enabled.
- [ ] Each of the six loops' `context:` block declares `design_tokens_context: ""`.
- [ ] Each loop's generation prompt references `${context.design_tokens_context}`.
- [ ] All six loops run end-to-end without error when `design_tokens.enabled: false` or path is missing.
- [ ] `test_design_tokens_context_injected_into_context` passes in `test_ll_loop_program_md.py`.
- [ ] `test_context_has_design_tokens_context` passes for all 6 loop classes in `test_builtin_loops.py`.

## Dependencies

- FEAT-1747 must be merged first (loader must exist for the injection sites to call it).

## Session Log
- `/ll:issue-size-review` - 2026-05-27T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f94f108-c36b-4b4d-b486-f41734145a41.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
