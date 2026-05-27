---
id: FEAT-1749
title: "Design-tokens loop wiring \u2014 pre-inject context into 6 built-in artifact\
  \ loops"
status: done
priority: P3
type: FEAT
parent: EPIC-1751
discovered_date: 2026-05-27
completed_at: 2026-05-27 22:40:45+00:00
discovered_by: issue-size-review
labels:
- feat
- loops
- design-system
relates_to:
- EPIC-1751
- FEAT-1747
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1749: Design-tokens loop wiring — pre-inject context into 6 built-in artifact loops

## Summary

Pre-inject `design_tokens_context` into `fsm.context` at `ll-loop run` and `ll-loop resume` entry points, then update the six built-in artifact-generating loops to reference `${context.design_tokens_context}` in their generation prompts. Depends on FEAT-1747 (loader must exist).

## Parent Issue
Decomposed from FEAT-1746: Design tokens config field with default palette, wired into built-in artifact-generating loops

## Current Behavior

`ll-loop run` and `ll-loop resume` do not inject `design_tokens_context` into `fsm.context`. The six built-in artifact loops (`hitl-compare`, `hitl-md`, `html-website-generator`, `html-anything`, `svg-image-generator`, `svg-textgrad`) have no design-token references in their generation prompts. Generated artifacts use no token-aware styling regardless of project configuration.

## Expected Behavior

`ll-loop run` pre-injects `design_tokens_context` into `fsm.context` at startup (guarded to allow CLI override). `ll-loop resume` applies the same injection. Each of the six built-in loops declares `design_tokens_context: ""` in its `context:` block and references `${context.design_tokens_context}` in at least one generation prompt. When tokens are enabled, generated artifacts reflect semantic token values. When disabled or missing, loops run without error with an empty context string.

## Motivation

- Activates the design-token system for end users: infra (FEAT-1747) and palette (FEAT-1748) have no visible effect on loop output until this wiring is in place
- The `if ... not in fsm.context:` guard follows the established `run_dir` injection pattern, enabling CLI override for testing custom palettes
- Empty `design_tokens_context` on disable/missing is a graceful no-op — no loop breakage

## Use Case

**Who**: A developer running `ll-loop run html-website-generator` on a project with design tokens configured

**Context**: Project has `.ll/design-tokens/` materialized and `design_tokens.enabled: true` in config

**Goal**: Have the generated HTML page automatically use the project's semantic color tokens without editing any loop YAML

**Outcome**: The loop receives `design_tokens_context` in `fsm.context`; the generation prompt includes resolved token values; the HTML output references `color.text.primary`, `color.surface.primary` etc. from the project's palette

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

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/__init__.py` — production dispatch; calls `cmd_run(args.loop, args, loops_dir, logger)` at the `"run"` branch and `cmd_resume(...)` at the `"resume"` branch in `main()`. No code change required but is the primary production call site for both injection points. [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**FEAT-1747 dependency confirmed** — `load_design_tokens` and `render_as_prompt_context` exist in `scripts/little_loops/design_tokens.py` (single module file, not a package):
```python
def load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None
def render_as_prompt_context(tokens: DesignTokens) -> str
```
Returns `None` when `design_tokens.enabled` is `False` or the configured path doesn't exist.

**Critical: injection placement in `run.py`** — The `run_dir` guard closes at line 162, but `BRConfig` is not instantiated until line 178 (as `_config`, not `config`). The design_tokens injection must be placed **after line 178**, reusing the existing `_config` variable:
```python
# Place AFTER line 178 where _config = BRConfig(Path.cwd()) is already set
if "design_tokens_context" not in fsm.context:
    tokens = load_design_tokens(_config)
    fsm.context["design_tokens_context"] = render_as_prompt_context(tokens) if tokens else ""
```
Do NOT instantiate a new `BRConfig(Path.cwd())` — `_config` already exists. Import at top of block: `from little_loops.design_tokens import load_design_tokens, render_as_prompt_context`.

**`lifecycle.py` placement confirmed** — `config = BRConfig(Path.cwd())` is at line 476 (variable `config`, consistent with issue). Run_dir re-injection is at lines 444–447, before BRConfig. Injection must go after line 476 using `config` (already correct in the Proposed Solution).

**Test fixture requires `design_tokens_context: ""`** — `TestCmdRunProgramMdInjection._make_loop()` writes a fixture YAML inline (lines 170–177 of `test_ll_loop_program_md.py`). The new `test_design_tokens_context_injected_into_context` test must either add `design_tokens_context: ""` to that shared fixture or write its own variant with the field declared.

**Confirmed test class locations in `test_builtin_loops.py`:**
- `TestHtmlWebsiteGeneratorLoop` — line 2640
- `TestSvgImageGeneratorLoop` — line 2713
- `TestSvgTextgradLoop` — line 2822
- `TestHtmlAnythingLoop` — line 3115
- `TestHitlCompareLoop` — line 3282
- `TestHitlMdLoop` — line 3442

**Confirmed loop YAML `context:` blocks** (all six loops; `design_tokens_context: ""` adds to each):
| Loop | Existing context keys |
|---|---|
| `html-website-generator.yaml` | `description: ""`, `pass_threshold: 6` |
| `svg-image-generator.yaml` | `description: ""`, `pass_threshold: 6` |
| `svg-textgrad.yaml` | `description: ""`, `pass_threshold: 6` |
| `html-anything.yaml` | `description: ""`, `pass_threshold: 7` |
| `hitl-compare.yaml` | `inputs: ""` |
| `hitl-md.yaml` | `input: ""` |

**`test_context_has_design_tokens_context` pattern** — mirrors `test_context_has_description` which exists in 4 of the 6 classes (at lines 2701, 2781, 2905, 3240). `TestHitlCompareLoop` and `TestHitlMdLoop` use `test_context_has_inputs`/`test_context_has_input` instead but follow identical structure. New test body:
```python
def test_context_has_design_tokens_context(self, data: dict) -> None:
    ctx = data.get("context", {})
    assert "design_tokens_context" in ctx
```

**Additional reference**: `test_ll_loop_commands.py:TestCmdRunContextInjection` (line 2577) — existing context-injection test class that may also need `design_tokens_context` coverage.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — Each of the six built-in loops has a context-variable table listing `run_dir` as `runner-injected`. After this issue, `design_tokens_context` becomes a second runner-injected variable and must appear in each table. Sections to update: `### html-anything` (~line 1021), `### hitl-compare` (~line 1096), `### hitl-md` (~line 1152), `### html-website-generator` (~line 1200), `### svg-image-generator` (~line 1254), `### svg-textgrad` (~line 1311). [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_lifecycle.py` — Covers `cmd_resume` exhaustively (`TestCmdResume`, `TestCmdResumeBackground`, etc.) but has zero `design_tokens` mentions. Acceptance criterion #2 ("design_tokens_context present in fsm.context after cmd_resume") has no backing test. A new test for the `cmd_resume` injection path must be added here, following the same pattern as `test_run_dir_injected_into_context` in `test_ll_loop_program_md.py`. [Agent 3 finding]
- `scripts/tests/test_cli_loop_worktree.py` — `TestCmdRunWorktree` patches `little_loops.config.BRConfig` as a bare `MagicMock` without configuring `.design_tokens`. After FEAT-1749 adds `load_design_tokens(_config)` in the injection block, this mock will pass a `MagicMock` to `load_design_tokens` instead of a real `BRConfig`; the function may return a truthy `MagicMock` and then call `render_as_prompt_context(mock)` with an invalid argument. **This test may break.** The mock needs `mock_cfg.return_value.design_tokens.enabled = False` or `load_design_tokens` must be patched at the module level in this test class. [Agent 3 finding]

## Acceptance Criteria

- [ ] `design_tokens_context` is present in `fsm.context` after `cmd_run` when tokens are enabled and path exists.
- [ ] `design_tokens_context` is present in `fsm.context` after `cmd_resume` when tokens are enabled.
- [ ] Each of the six loops' `context:` block declares `design_tokens_context: ""`.
- [ ] Each loop's generation prompt references `${context.design_tokens_context}`.
- [ ] All six loops run end-to-end without error when `design_tokens.enabled: false` or path is missing.
- [ ] `test_design_tokens_context_injected_into_context` passes in `test_ll_loop_program_md.py`.
- [ ] `test_context_has_design_tokens_context` passes for all 6 loop classes in `test_builtin_loops.py`.

## Implementation Steps

1. Add `design_tokens_context` injection guard in `cli/loop/run.py` (~line 162), after the `run_dir` injection block
2. Add identical injection guard in `cli/loop/lifecycle.py:cmd_resume` after line 476 where `BRConfig` is already instantiated
3. Update each of the six built-in loop YAMLs: add `design_tokens_context: ""` to `context:` block; add `${context.design_tokens_context}` to the primary generation prompt
4. Add `test_design_tokens_context_injected_into_context` to `TestCmdRunProgramMdInjection` in `test_ll_loop_program_md.py`, following the `test_run_dir_injected_into_context` pattern
5. Add `test_context_has_design_tokens_context` to all six loop test classes in `test_builtin_loops.py`; run full suite

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/guides/LOOPS_GUIDE.md` — add a `design_tokens_context | "" | runner-injected` row to the context-variable tables for all six built-in loops (six table edits total)
7. Add `test_design_tokens_context_injected_via_cmd_resume` to `test_cli_loop_lifecycle.py` — verifies acceptance criterion #2 (cmd_resume injection); follow the `test_run_dir_injected_into_context` pattern from `test_ll_loop_program_md.py`
8. Fix `TestCmdRunWorktree` in `test_cli_loop_worktree.py` — before adding the injection code, add `mock_cfg.return_value.design_tokens.enabled = False` (or patch `little_loops.design_tokens.load_design_tokens` at the module level) to prevent a MagicMock from being passed to `render_as_prompt_context`

## Impact

- **Priority**: P3 — depends on FEAT-1747; makes design tokens visible in actual loop output
- **Effort**: Medium — two Python injection sites, six YAML updates, two test files
- **Risk**: Low — guard pattern preserves existing behavior when tokens disabled/missing; no loop YAML changes affect existing runs
- **Breaking Change**: No

## Dependencies

- FEAT-1747 must be merged first (loader must exist for the injection sites to call it).

## Session Log
- `/ll:ready-issue` - 2026-05-27T22:27:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b372a37b-0b66-456e-af99-2cc6e5c0a993.jsonl`
- `/ll:wire-issue` - 2026-05-27T22:22:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4eb3a107-2ec1-41bd-8a12-54c4a785770a.jsonl`
- `/ll:refine-issue` - 2026-05-27T22:15:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc6064e1-5abc-4291-80e1-7166397af8e6.jsonl`
- `/ll:format-issue` - 2026-05-27T20:25:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/652005b7-b7e9-404a-9ee0-b21de41aeefa.jsonl`
- `/ll:issue-size-review` - 2026-05-27T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f94f108-c36b-4b4d-b486-f41734145a41.jsonl`
- `/ll:confidence-check` - 2026-05-27T22:45:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/26ce65c9-f604-4d07-ab8b-653b4eb3c1b0.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
