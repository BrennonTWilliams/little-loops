---
status: open
discovered_date: 2026-05-30
discovered_by: capture-issue
captured_at: "2026-05-30T22:43:51Z"
labels: [validation, loop-authoring, harness, captured]
---

# P3-ENH-1819: Add validation warning for multimodal evaluator blind spot in harness loops

## Summary

Harness loops like `html-website-generator` use `action_type: prompt` states that read screenshots/images and output a text verdict gated by `output_contains`. The evaluator can verify the LLM wrote the pass string but cannot verify the LLM actually processed the image vs. silently falling back to text-only analysis. Add a `validate_fsm` WARNING when a harness-category loop has this pattern with routing directly to a terminal state.

## Current Behavior

`validate_fsm()` has MR-1 (ERROR) and MR-2 (WARNING) rules for meta-loops, ensuring LLM self-evaluation is paired with non-LLM verification. No equivalent rule exists for harness-category loops that use LLM multimodal evaluation (screenshot reading + text verdict) as the sole gate to a terminal state. The pattern is structurally valid and passes all current validators.

## Expected Behavior

A new validation function `_validate_harness_multimodal_evaluator_blind_spot` fires a WARNING when:

1. Loop has `category: harness` (or is classified as a harness loop)
2. A state uses `action_type: prompt`
3. The action text references reading a screenshot or image (matches patterns like `screenshot.png`, `Read the screenshot`, `view the generated website`)
4. The evaluate type is `output_contains` (text-based, cannot verify multimodal processing)
5. The state's `on_yes` routes to a terminal state (or all paths from `on_yes` lead to terminal without passing through a shell-action state)

The warning message suggests adding a non-LLM verification state (shell action with functional tests) between the scoring state and the terminal.

Suppressed by `meta_self_eval_ok: true` at the loop top-level (reusing the existing escape hatch, since the underlying concern — LLM self-evaluation bias — is the same).

## Motivation

The `/ll:debug-loop-run html-website-generator` analysis found that an artifact with functional defects passed the screenshot evaluator because the LLM fell back to source-only scoring when it couldn't read the screenshot. The `output_contains` evaluator faithfully reported "ALL_PASS" — it just couldn't detect that the verdict was based on incomplete information. This is the same class of failure as MR-1 (LLM self-grades on harness updates are ~33-55% accurate per SHOR Table 1) but applied to artifact evaluation rather than harness modification. Catching this at validation time prevents future harness loops from shipping with the same blind spot.

## Proposed Solution

Add `_validate_harness_multimodal_evaluator_blind_spot` to `scripts/little_loops/fsm/validation.py`:

```python
# Regex patterns for detecting multimodal evaluation in prompt actions
_MULTIMODAL_EVAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'Read the screenshot', re.IGNORECASE),
    re.compile(r'view the (generated )?(website|page|image)', re.IGNORECASE),
    re.compile(r'screenshot\.(png|jpg|jpeg|webp)'),
    re.compile(r'\.(png|jpg|jpeg|webp)\b.*\b(read|view|evaluate|score|judge)', re.IGNORECASE),
)

def _validate_harness_multimodal_evaluator_blind_spot(fsm: FSMLoop) -> list[ValidationError]:
    """Warn when harness loops use LLM multimodal eval as sole gate to terminal."""
    errors = []
    if fsm.meta_self_eval_ok or fsm.category != "harness":
        return errors

    terminal_states = fsm.get_terminal_states()

    for state_name, state in fsm.states.items():
        if state.action_type != "prompt" or not state.action:
            continue
        if state.evaluate is None or state.evaluate.type != "output_contains":
            continue
        if not any(p.search(state.action) for p in _MULTIMODAL_EVAL_PATTERNS):
            continue
        # Check if on_yes routes directly to a terminal
        if state.on_yes in terminal_states:
            errors.append(ValidationError(
                message=(
                    f"State '{state_name}' evaluates a screenshot/image via LLM prompt "
                    "and routes directly to a terminal on success. The output_contains "
                    "evaluator can verify the LLM wrote the pass string but not that the "
                    "LLM actually processed the image. Consider adding a shell-action "
                    "verification state (e.g., functional smoke test) between scoring "
                    "and the terminal."
                ),
                path=f"states.{state_name}",
                severity=ValidationSeverity.WARNING,
            ))

    return errors
```

Wire into `validate_fsm()` alongside the existing MR-1/MR-2/zero-retry-counter calls.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add `_MULTIMODAL_EVAL_PATTERNS`, `_validate_harness_multimodal_evaluator_blind_spot`, wire into `validate_fsm()`

### Dependent Files (Callers/Importers)
- `ll-loop validate` CLI — consumes `validate_fsm()` output (no changes needed)

### Tests
- `scripts/tests/test_fsm_validation.py` — add test class `TestHarnessMultimodalEvaluatorBlindSpot` with cases for: fires on matching pattern, does not fire on non-harness loops, does not fire when on_yes goes to non-terminal, does not fire when shell-action state intervenes, suppressed by `meta_self_eval_ok`

### Documentation
- N/A

### Configuration
- N/A

## API/Interface

N/A - no public API changes; new `_validate_harness_multimodal_evaluator_blind_spot()` is internal (called from existing `validate_fsm()`).

## Implementation Steps

1. Add `_MULTIMODAL_EVAL_PATTERNS` regex tuple to `validation.py`
2. Implement `_validate_harness_multimodal_evaluator_blind_spot`
3. Wire into `validate_fsm()` (add one line: `errors.extend(_validate_harness_multimodal_evaluator_blind_spot(fsm))`)
4. Add test class with positive and negative cases
5. Run `python -m pytest scripts/tests/test_fsm_validation.py -v` to confirm all pass
6. Run `ll-loop validate html-website-generator` — should emit the new WARNING (until ENH-1818 adds the smoke_test state)

## Success Metrics

- `ll-loop validate html-website-generator` emits the new WARNING (before ENH-1818 fix)
- Non-harness loops are not flagged
- `meta_self_eval_ok: true` suppresses the warning
- No existing tests break

## Scope Boundaries

- Only checks `category: harness` loops — does not apply to all loops
- Only checks `output_contains` evaluators — does not cover `llm_structured` or other evaluator types
- Only checks direct `on_yes` → terminal routing — does not trace multi-hop paths to terminal
- Does not auto-fix loops — informational warning only

## Impact

- **Priority**: P3 — preventive guardrail; the immediate blind spot is fixed by ENH-1818
- **Effort**: Small — ~40 lines of validation code + ~60 lines of tests
- **Risk**: Low — WARNING only, does not block loop execution; regex patterns may have false negatives but false positives are unlikely given the `category: harness` gate
- **Breaking Change**: No

## Related Key Documentation

- [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)
- [.claude/CLAUDE.md](../../.claude/CLAUDE.md) — Meta-loop design rules section

## Labels

`validation`, `loop-authoring`, `harness`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-30T22:47:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/161b9a00-98fc-4a06-9eec-25494c352734.jsonl`
- `/ll:capture-issue` - 2026-05-30T22:43:51Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a21d14e7-ea27-437a-b7be-dfdc28dd7d84.jsonl`

---

**Open** | Created: 2026-05-30 | Priority: P3
