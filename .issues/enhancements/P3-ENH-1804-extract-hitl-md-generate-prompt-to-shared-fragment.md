---
id: ENH-1804
type: ENH
priority: P3
status: done
captured_at: '2026-05-29T21:57:08Z'
completed_at: '2026-05-29T22:40:00Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1804: Extract hitl-md 16KB generate prompt to shared file fragment

## Summary

The `generate` state action in `loops/hitl-md.yaml` is 16,272 characters — by far the largest action in any built-in loop. Extract the design specification portion (HTML/CSS/JS requirements for the interactive review page) to a shared prompt file under `prompts/` or a loop fragment. This reduces FSM definition size, makes the prompt independently iterable, and aligns with the fragment-extraction direction in ENH-1775.

## Current Behavior

The `generate` state inlines the entire design specification (document rendering rules, inline segment markers, saliency highlighting, popover affordances, all 6 ENH-1770 sensemaking features, cross-feature requirements) as a single 16KB YAML string. This makes the loop YAML unreadable and increases the probability of template interpolation errors or token-limit failures.

## Expected Behavior

The generate state references a shared prompt file:

```yaml
generate:
  action: |
    Read ${captured.run_dir.output}/segments.json for the ordered segment list.
    If ${captured.run_dir.output}/critique.md exists, read it and address all issues.
    ${context.design_tokens_context}
    Read prompts/hitl-md-generate.md for the full design specification.
    Write a single self-contained HTML file to ${captured.run_dir.output}/index.html
    following every requirement in the design specification.
  action_type: prompt
  next: evaluate
  on_error: failed
```

The design spec lives in `prompts/hitl-md-generate.md` and can be iterated independently.

## Motivation

The 16KB action size likely contributed to the `2026-05-29T213409` run failure (terminated with error at generate state entry). Extracting the prompt reduces FSM definition bloat, improves debuggability, and creates a reusable fragment that other HITL loops (hitl-compare, html-anything) could reference. This also enables independent prompt iteration without touching the loop YAML.

## Proposed Solution

1. Move the design specification portion of the generate action to `prompts/hitl-md-generate.md`
2. Replace the inlined spec in the generate action with a reference to read the file
3. The loop YAML keeps only the file-path references and context wiring

## Success Metrics

- **File size**: `loops/hitl-md.yaml` generate action reduces from ~16KB to <1KB reference
- **Loop reliability**: `ll-loop run hitl-md` completes generate state without template interpolation errors
- **Maintainability**: Design specification can be iterated independently without touching loop YAML

## Scope Boundaries

- **In scope**: Extracting the design specification from `hitl-md.yaml` generate action to a shared prompt file
- **In scope**: Updating the generate state to reference the external file
- **In scope**: Adding `on_error: failed` to generate state (see BUG-1803)
- **Out of scope**: Changing the design specification content itself
- **Out of scope**: Modifying other loops (hitl-compare, html-anything) to use the shared fragment
- **Out of scope**: General loop YAML refactoring beyond generate state

## API/Interface

N/A - No public API changes. Internal loop refactoring only.

## Integration Map

### Files to Modify
- `loops/hitl-md.yaml` — replace inlined 16KB action with file reference
- `prompts/hitl-md-generate.md` (new) — extracted design specification

### Dependent Files (Callers/Importers)
- `loops/hitl-compare.yaml` — may benefit from shared fragment
- `loops/html-anything.yaml` — may benefit from shared fragment

### Similar Patterns
- ENH-1775 (Wave 2) — extracting generator-evaluator sub-loop and `parse_tagged_json` fragment
- ENH-1774 (Wave 1) — adding `ll-commit` and Playwright screenshot as shared fragments
- `scripts/little_loops/loops/lib/common.yaml:14` — YAML-level fragment library (`shell_exit`, `llm_gate`, `retry_counter`) — a different extraction approach (YAML state config reuse vs. prompt text extraction)
- `hooks/prompts/optimize-prompt-hook.md` — analogous prompt-file extraction pattern using `{{HOOK_VARIABLE}}` template syntax

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **FSM Interpolation**: `scripts/little_loops/fsm/interpolation.py:169` — `interpolate()` resolves `${namespace.path}` patterns at runtime. `InterpolationContext.resolve()` (line 65) handles `context`, `captured`, `prev`, `result`, `state`, `loop`, `env` namespaces. Context variables like `${context.design_tokens_context}` stay in the YAML action text; the extracted prompt file contains only static instruction text.
- **Executor on_error routing**: `scripts/little_loops/fsm/executor.py:1295` — `_run_action_or_route()` catches exceptions and routes to `state.on_error` if configured. Without it, exceptions propagate to `run()` line 491 which calls `_finish("error")` — hard termination.
- **Runner context injection**: `scripts/little_loops/cli/loop/run.py:176-183` — `design_tokens_context` is injected at startup by `load_design_tokens()` / `render_as_prompt_context()` from `scripts/little_loops/design_tokens.py:136/201`.
- **Test pattern**: `scripts/tests/test_builtin_loops.py:3478` — `generate_spec` fixture concatenates the YAML action text with `prompts/hitl-md-generate.md` content, so requirement tests (e.g., staged highlighting, density slider) search across both files.
- **Prompt execution flow**: `action_type: prompt` states dispatch through `FSMExecutor._run_action()` (executor.py:943) → interpolate → `DefaultActionRunner.run()` (runners.py:56) → `run_claude_command()` which invokes the host CLI as a subprocess. The LLM reads `prompts/hitl-md-generate.md` using its standard file-reading tool during prompt execution.

### Tests
- Re-run `ll-loop run hitl-md --input "PRD-Hermes-Integration-v3.md"` to verify no regression
- Verify the generate prompt reads the external file correctly via template resolution
- `scripts/tests/test_builtin_loops.py:3467` — `TestHitlMdLoop` class verifies structural integrity; `generate_spec` fixture (line 3478) concatenates YAML action + `prompts/hitl-md-generate.md` for cross-file requirement tests
- `scripts/tests/test_builtin_loops.py:3598` — `test_generate_on_error_routes_to_failed` verifies the BUG-1803 `on_error: failed` fix
- `scripts/tests/test_builtin_loops.py:3625` — `test_generate_action_writes_index_html` verifies generate action references `index.html`
- `scripts/tests/test_fsm_executor.py:2730` — `test_interpolation_error_routes_to_on_error_when_set` verifies the executor-level on_error routing

### Documentation
- `docs/development/sensemaking-hitl-md.md` — documents the 8 sensemaking patterns implemented in the generate spec
- `docs/guides/LOOPS_GUIDE.md:2832` — fragment definitions and template inheritance patterns

### Configuration
- N/A

## Implementation Steps

1. Create `prompts/hitl-md-generate.md` with the extracted design specification
2. Update `loops/hitl-md.yaml` generate state to reference the file
3. Add `on_error: failed` to generate state (see BUG-1803)
4. Validate: `ll-loop validate hitl-md`
5. Re-run the failing invocation to confirm fix

### Verification (Post-Implementation)

_Added by `/ll:refine-issue` — codebase research confirms implementation is complete:_

- `prompts/hitl-md-generate.md` exists at 274 lines — the full design specification extracted from the YAML
- `scripts/little_loops/loops/hitl-md.yaml:166` — generate action includes `Read prompts/hitl-md-generate.md for the full design specification.`
- `scripts/little_loops/loops/hitl-md.yaml:170` — `on_error: failed` is present on generate state
- `scripts/tests/test_builtin_loops.py:3598` — `test_generate_on_error_routes_to_failed` passes, confirming the BUG-1803 fix
- `scripts/tests/test_builtin_loops.py:3478` — `generate_spec` fixture verifies both YAML action and prompt file exist and concatenate correctly
- Commit `9adc0f5a` — "refine(ENH-1804): extract hitl-md generate design spec to shared prompt file"

## Impact

- **Priority**: P3 — Reduces fragility and improves maintainability; not blocking
- **Effort**: Medium — Requires careful extraction to preserve all design spec details
- **Risk**: Low — The generate action is self-contained; extraction doesn't change behavior
- **Breaking Change**: No

## Related Key Documentation

- `docs/development/sensemaking-hitl-md.md` — documents the 8 sensemaking patterns (ENH-1770) whose requirements live in the extracted prompt file
- `docs/guides/LOOPS_GUIDE.md` — loop authoring guide with fragment definitions and template inheritance patterns
- `docs/generalized-fsm-loop.md` — general FSM loop design document
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — harness authoring guide referencing similar patterns

## Labels

`enhancement`, `loop-fragment`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-29T22:00:03 - `c276e230-d4ed-4934-9b72-d81b4c8c08a1.jsonl`

- `/ll:capture-issue` — 2026-05-29T21:57:08Z — `64ba091c-1c65-464a-81b6-237b5a702007.jsonl`
- `/ll:manage-issue` — 2026-05-29T22:40:00Z — (implementation)
- `/ll:confidence-check` - 2026-05-29 - `61594731-05cd-4053-a702-bd2146f328e1.jsonl`

---

**Done** | Created: 2026-05-29 | Priority: P3
