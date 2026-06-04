---
id: BUG-1947
title: Design tokens context empty placeholder blocks injection
status: done
priority: P2
type: BUG
captured_at: '2026-06-04T19:27:13Z'
completed_at: '2026-06-04T19:47:57Z'
discovered_date: 2026-06-04
discovered_by: capture-issue
labels:
- bug
- loop-runner
- design-tokens
- captured
confidence_score: 98
outcome_confidence: 87
score_complexity: 25
score_test_coverage: 15
score_ambiguity: 24
score_change_surface: 23
---

# BUG-1947: Design tokens context empty placeholder blocks injection

## Summary

The loop runner guard that decides whether to inject design tokens into `fsm.context` checks key **existence** (`"design_tokens_context" not in fsm.context`) instead of value **truthiness**. When a loop YAML declares `design_tokens_context: ""` (as all built-in artifact loops do), the empty placeholder blocks `load_design_tokens()` from being called, and the LLM receives no token context despite design tokens being enabled and available on disk.

## Current Behavior

`ll-loop run` and `ll-loop resume` silently skip design token injection when a loop YAML declares `design_tokens_context: ""` in its `context:` block. The guard at `run.py:181` and `lifecycle.py:496` evaluates `False` because the key exists (value `""`), so `load_design_tokens()` is never called. The empty string passes through to the LLM, which reports "No design tokens were provided explicitly."

## Expected Behavior

When `design_tokens_context` is absent OR empty/falsy in `fsm.context`, the runner and lifecycle resume paths should call `load_design_tokens()` and populate the context with rendered token context. The guard should only skip injection when the key holds a non-empty string (already injected).

## Motivation

This bug silently disables design token injection for **every built-in artifact loop** (9 loops) and any user-authored loop that declares `design_tokens_context: ""` as a placeholder. Design tokens are a core visual-consistency feature — when enabled and configured, they should always reach the LLM. The silent nature of this failure means users have no indication tokens are missing; the LLM just produces unstyled output.

## Steps to Reproduce

1. Configure a project with `design_tokens.enabled: true` and an active profile (e.g., `warm-paper`)
2. Verify token files exist at `.ll/design-tokens/profiles/<profile>/`
3. Run any built-in artifact loop: `ll-loop run svg-image-generator --max-iterations 1`
4. Observe in the LLM output: "No design tokens were provided explicitly"
5. Verify that calling `load_design_tokens()` + `render_as_prompt_context()` directly produces correct ~2,366-char context

## Root Cause

- **File**: `scripts/little_loops/cli/loop/run.py`
- **Anchor**: in function `cmd_run()`
- **Cause**: Guard at line 181 checks key existence, not value truthiness

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: in function `cmd_resume()`
- **Cause**: Same pattern at line 496

The guard pattern:

```python
# Broken: checks key existence — empty string blocks injection
if "design_tokens_context" not in fsm.context:
    _tokens = load_design_tokens(_config)
    fsm.context["design_tokens_context"] = render_as_prompt_context(_tokens) if _tokens else ""
```

When a loop YAML defines `design_tokens_context: ""` in its context block, the key exists with a falsy value. The `not in` check evaluates `False`, and the injection block is skipped entirely.

## Proposed Solution

Change both guards from existence-check to truthiness-check:

```python
# Fixed: checks truthiness — absent or empty triggers injection
if not fsm.context.get("design_tokens_context"):
    _tokens = load_design_tokens(_config)
    fsm.context["design_tokens_context"] = render_as_prompt_context(_tokens) if _tokens else ""
```

This handles all cases:
- Key absent → `None` → truthy → injection runs
- Key present with `""` → falsy → injection runs
- Key present with populated string → truthy → injection skipped (already injected)

### Files to change

| File | Line | Change |
|---|---|---|
| `scripts/little_loops/cli/loop/run.py` | 181 | `not in` → `.get()` truthiness |
| `scripts/little_loops/cli/loop/lifecycle.py` | 496 | `not in` → `.get()` truthiness |

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` guard condition
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` guard condition

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` imports from same module; no callers to update beyond the two guarded sites

### Similar Patterns
- No other `not in fsm.context` guards for other context keys; this pattern is unique to `design_tokens_context`

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py` — `test_design_tokens_context_injected_via_cmd_resume`
- `scripts/tests/test_ll_loop_program_md.py` — `test_design_tokens_context_injected_into_context`
- Both tests assert key existence, not value population; may need updates to verify non-empty content when tokens are configured

### Documentation
- N/A (no docs reference the guard implementation detail)

### Configuration
- N/A

## Implementation Steps

1. Fix the guard in `scripts/little_loops/cli/loop/run.py:181` — change `"design_tokens_context" not in fsm.context` to `not fsm.context.get("design_tokens_context")`
2. Apply the identical fix to `scripts/little_loops/cli/loop/lifecycle.py:496`
3. Update existing tests to verify value truthiness, not just key existence, when design tokens are configured
4. Run `python -m pytest scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_ll_loop_program_md.py -x -q` to verify
5. Manually verify with `ll-loop run svg-image-generator --dry-run` to confirm design tokens appear in context

## Impact

- **Priority**: P2 — Affects all design-token-enabled loops; silent failure with no user-visible error; core visual-consistency feature is non-functional for artifact generation
- **Effort**: Small — Two identical one-line fixes in adjacent guard conditions plus test updates
- **Risk**: Low — Change is a strictly more permissive guard (injects when key absent OR empty, instead of only when absent); no existing behavior relies on empty-string blocking
- **Breaking Change**: No

## Resolution

**Root cause**: Both `cmd_run()` (run.py:181) and `cmd_resume()` (lifecycle.py:496) used `"design_tokens_context" not in fsm.context` (key-existence check) instead of `not fsm.context.get("design_tokens_context")` (truthiness check). When a loop YAML declares `design_tokens_context: ""` as a placeholder, the key exists with an empty (falsy) value, so the guard silently skipped injection.

**Fix**: Changed both guards from key-existence to truthiness check (`not fsm.context.get("design_tokens_context")`). This triggers injection when the key is absent OR empty.

**Files changed**:
- `scripts/little_loops/cli/loop/run.py:181` — `not in` → `.get()` truthiness
- `scripts/little_loops/cli/loop/lifecycle.py:496` — identical fix
- `scripts/tests/test_ll_loop_program_md.py:282-313` — updated test to mock `DesignTokens` with resolved values and assert populated content (previously only checked `is not None`, which passed for empty string)

**Verification**: 3212 tests passed. Lint clean. Design tokens now populate in `fsm.context` when loop YAML declares empty placeholder.

## Session Log
- `/ll:manage-issue` — 2026-06-04T19:47:57Z — `d108443a-ed61-4ba9-90b7-4f4436eedc57.jsonl`
- `/ll:ready-issue` - 2026-06-04T19:43:11 - `822d0634-f7b8-4ecf-b681-7e977f1efd91.jsonl`
- `/ll:confidence-check` - 2026-06-04T19:33:00Z - `~/.../fadecd00-e4da-4850-b02d-2cbaa7f00dda.jsonl`
- `/ll:format-issue` - 2026-06-04T19:30:34 - `df78385a-9cc2-4216-80a0-d3a6661b1a81.jsonl`
- `/ll:capture-issue` — 2026-06-04T19:27:13Z — `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

**Done** | Created: 2026-06-04 | Completed: 2026-06-04 | Priority: P2
