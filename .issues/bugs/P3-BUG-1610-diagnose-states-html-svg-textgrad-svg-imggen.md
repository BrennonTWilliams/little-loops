---
id: BUG-1610
type: BUG
priority: P3
title: Add pre-terminal diagnose states to html-anything, svg-textgrad, svg-image-generator loops
status: open
parent: BUG-1606
size: Small
---

# BUG-1610: Add pre-terminal diagnose states to html-anything, svg-textgrad, svg-image-generator loops

## Summary

Add a pre-terminal `diagnose` state to `html-anything`, `svg-textgrad`, and `svg-image-generator` loop YAML files, and update the corresponding `test_builtin_loops.py` test class assertions that reference `"failed"` routing.

## Parent Issue

Decomposed from BUG-1606: Add pre-terminal diagnose states to 12 affected loop YAML files

## Background

`scripts/little_loops/fsm/executor.py` `FSMExecutor.run()` calls `return self._finish("terminal")` BEFORE executing any terminal state action. An `action:` field on a `failed` terminal never executes. The correct pattern is a separate non-terminal `diagnose` state that runs the diagnostic prompt and routes `next: failed`.

All three loops in this child share the same artifact pattern: `${captured.run_dir.output}/` output directory.

## Affected Loops

| Loop | File | Failed State Line | States routing to `failed` |
|------|------|-------------------|----------------------------|
| `html-anything` | `scripts/little_loops/loops/html-anything.yaml` | 221 | `score` → `on_error: failed` |
| `svg-textgrad` | `scripts/little_loops/loops/svg-textgrad.yaml` | 295 | `score` → `on_error: failed` |
| `svg-image-generator` | `scripts/little_loops/loops/svg-image-generator.yaml` | 169 | `score` → `on_error: failed` |

## Implementation Steps

### For each loop:

1. Read the loop YAML and identify all states routing to `failed`.

2. Add a `diagnose` state immediately before the `failed` terminal:

**`html-anything`** — artifacts: `brief.md`, `rubric.md`, `critique.md`:
```yaml
diagnose:
  action_type: prompt
  action: |
    The html-anything loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - If ${captured.run_dir.output}/critique.md exists, read it and summarize the last scores.
    - If ${captured.run_dir.output}/rubric.md exists, report the rubric dimensions that failed.
    - Identify the most likely failure cause (most commonly: LLM error in the score state).

    Write a one-paragraph diagnostic summary the operator can use to re-run or adjust inputs.
  next: failed

failed:
  terminal: true
```

**`svg-textgrad`** — artifacts: `critique.md`, `scores.md`, `image.svg`:
```yaml
diagnose:
  action_type: prompt
  action: |
    The svg-textgrad loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - If ${captured.run_dir.output}/scores.md exists, read it and report the last recorded scores.
    - If ${captured.run_dir.output}/critique.md exists, summarize the last evaluation notes.
    - Note whether ${captured.run_dir.output}/image.svg or best.svg exist as partial outputs.
    - Identify the most likely failure cause.

    Write a one-paragraph diagnostic summary the operator can use to re-run or adjust inputs.
  next: failed
```

**`svg-image-generator`** — artifacts: `critique.md`, `image.svg`:
```yaml
diagnose:
  action_type: prompt
  action: |
    The svg-image-generator loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - If ${captured.run_dir.output}/critique.md exists, read it and summarize the last evaluation scores.
    - Note whether ${captured.run_dir.output}/image.svg exists as a partial output.
    - Identify the most likely failure cause (most commonly: LLM error in the score state).

    Write a one-paragraph diagnostic summary the operator can use to re-run or adjust the image brief.
  next: failed
```

3. Update routing for each loop:
   - `html-anything`: `score.on_error: failed` → `score.on_error: diagnose`
   - `svg-textgrad`: `score.on_error: failed` → `score.on_error: diagnose`
   - `svg-image-generator`: `score.on_error: failed` → `score.on_error: diagnose`

4. Update `scripts/tests/test_builtin_loops.py`:
   - `TestHtmlAnythingLoop.test_score_on_error_routes_to_failed`: change `on_error` assert from `"failed"` → `"diagnose"`
   - `TestHtmlAnythingLoop.test_required_states_exist`: add `"diagnose"` to required set
   - `TestSvgTextgradLoop.test_score_on_error_routes_to_failed`: change `on_error` assert from `"failed"` → `"diagnose"`
   - `TestSvgTextgradLoop.test_required_states_exist`: add `"diagnose"` to required set
   - `TestSvgImageGeneratorLoop`: `"failed"` is not in its required set — add `test_diagnose_routes_to_failed` and `test_diagnose_is_not_terminal` following the pattern from BUG-1606:
     ```python
     def test_diagnose_routes_to_failed(self, data: dict) -> None:
         state = data["states"].get("diagnose", {})
         assert state.get("next") == "failed"

     def test_diagnose_is_not_terminal(self, data: dict) -> None:
         state = data["states"].get("diagnose", {})
         assert not state.get("terminal", False)
     ```

5. Run `python -m pytest scripts/tests/test_builtin_loops.py -k "HtmlAnything or SvgTextgrad or SvgImageGenerator" scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py -v` and confirm all pass.

**Note**: `test_builtin_loops.py` is also modified by BUG-1611 and BUG-1612 (different test classes). Run this child before those, or coordinate to avoid conflicts.

## Acceptance Criteria

- `html-anything.yaml`, `svg-textgrad.yaml`, `svg-image-generator.yaml` each have a `diagnose` state with `next: failed` before the `failed` terminal
- Each `diagnose` state names the loop's actual output artifacts in the action prompt
- `failed` terminal retains only `terminal: true`
- `test_builtin_loops.py` assertions updated for HtmlAnything and SvgTextgrad test classes; new diagnose tests added for SvgImageGenerator
- All listed tests pass

---

**Priority**: P3 | **Created**: 2026-05-18

## Session Log
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3772e425-1416-4cc8-baac-8e0f351122fa.jsonl`
