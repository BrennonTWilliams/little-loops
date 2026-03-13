---
discovered_date: 2026-03-12
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 93
---

# ENH-714: Stall Detection via Diff Comparison for FSM Loops

## Summary

Add a new `diff_stall` evaluator type (or reusable shell state pattern) that detects when consecutive FSM loop iterations produce no code changes, automatically transitioning to a skip/done state instead of retrying indefinitely. This complements the existing `convergence` evaluator (which tracks numeric metrics) by providing stall detection for non-numeric, prompt-based loop actions.

## Current Behavior

- The `convergence` evaluator (`evaluate_convergence()` in `evaluators.py`) detects stalls for numeric metrics by comparing current vs. previous values and emitting `stall` verdict
- Prompt-based actions (`action_type: prompt`) using `llm_structured` evaluation have no automatic stall detection
- If an LLM-as-judge evaluator keeps returning `failure` and the fix action produces no changes, the loop retries until `max_iterations` is exhausted
- No built-in mechanism to compare `git diff` between iterations

## Expected Behavior

Two implementation paths (can coexist):

**Path A: Reusable shell state template** (no runtime changes)
A documented pattern for `create-loop` to inject into generated harnesses:

```yaml
check_stall:
  action: |
    PREV="/tmp/ll-harness-${loop.name}-prev-diff"
    CURR="/tmp/ll-harness-${loop.name}-curr-diff"
    git diff --stat > "$CURR"
    if [ -f "$PREV" ] && diff -q "$PREV" "$CURR" > /dev/null 2>&1; then
      echo "STALLED"
    else
      cp "$CURR" "$PREV"
      echo "PROGRESS"
    fi
  action_type: shell
  evaluate:
    type: output_contains
    pattern: "PROGRESS"
  on_success: next_phase
  on_failure: skip_item  # or done
```

**Path B: Native `diff_stall` evaluator** (runtime addition)
A new evaluator type that automatically compares the working tree diff against the previous iteration's diff:

```yaml
states:
  execute:
    action: "/ll:refine-issue ${current_item}"
    evaluate:
      type: diff_stall
      scope: ["scripts/"]  # optional: limit diff to specific paths
      max_stall: 2          # transition after N consecutive no-change iterations
    on_success: evaluate_result
    on_failure: skip_item   # "failure" = stalled
```

## Motivation

Loops that use prompt-based actions (the majority of harness-style loops) can enter degenerate cycles where the LLM attempts the same fix repeatedly without making progress. The `convergence` evaluator only works for numeric metrics. Diff-based stall detection is universally applicable — if `git diff --stat` is identical between iterations, no progress was made regardless of what the evaluator thinks.

## Proposed Solution

**Recommended: Start with Path A (template), graduate to Path B if heavily used.**

Path A requires zero runtime changes — it's a documented pattern in `loop-types.md` that `create-loop` can inject into generated harnesses. This validates the concept with real usage before committing to a new evaluator type.

Path B would add a `DiffStallEvaluator` to `evaluators.py` that:
1. On first call, snapshots `git diff --stat [scope]` and returns `success`
2. On subsequent calls, compares current diff to previous snapshot
3. If identical for `max_stall` consecutive iterations, returns `failure` (stalled)
4. If different, updates snapshot and returns `success` (progress)

## API/Interface

**Path A — Shell state template** (no Python API changes):

```yaml
# New documented pattern for harness loop YAML
check_stall:
  action_type: shell
  evaluate:
    type: output_contains
    pattern: "PROGRESS"
  on_success: next_phase
  on_failure: skip_item
```

**Path B — `diff_stall` evaluator type** (new YAML config fields):

```yaml
evaluate:
  type: diff_stall        # new evaluator type key
  scope: ["scripts/"]    # optional list[str]; defaults to repo root
  max_stall: 2           # optional int; default 1 (one no-change iteration = stall)
```

**Path B — `DiffStallEvaluator` Python class** (new addition to `evaluators.py`):

```python
class DiffStallEvaluator:
    """Detects stalled iterations by comparing git diff --stat between runs."""
    def evaluate(self, scope: list[str] | None = None, max_stall: int = 1) -> EvaluationResult:
        ...  # returns verdict: "success" (progress) or "failure" (stalled)
```

New schema fields would be validated in `schema.py` and `validation.py`.

## Scope Boundaries

- **In scope**: Detecting no-change iterations via git diff comparison; configurable scope paths; configurable stall threshold
- **Out of scope**: Semantic diff analysis (detecting "same change reverted then reapplied"); non-git repos; stall detection for shell-only loops (they should use `convergence` evaluator)

## Success Metrics

- Harness loops (FEAT-712) terminate early on stall rather than exhausting `max_iterations` — at least 1 observed degenerate loop exits early via stall detection
- Zero regression on existing loops: all current `evaluators.py` unit tests continue to pass after Path B addition
- Path A: documented pattern usable in a generated harness loop with no runtime code changes

## Integration Map

### Files to Modify
- `skills/create-loop/loop-types.md` — Document stall detection pattern for harness type (Path A)

### Dependent Files (Callers/Importers)
- N/A for Path A (template only)
- For Path B: `scripts/little_loops/fsm/evaluators.py`, `scripts/little_loops/fsm/schema.py`, `scripts/little_loops/fsm/validation.py`

### Similar Patterns
- `evaluate_convergence()` in `evaluators.py` — `convergence` evaluator's stall detection (numeric equivalent)
- `check_commit` state in `loops/issue-refinement.yaml` — Counter-based state that could be enhanced with stall detection

### Tests
- For Path B: `scripts/tests/test_fsm_evaluators.py` — Add diff_stall evaluator tests

### Documentation
- `skills/create-loop/loop-types.md` — Pattern documentation
- `skills/create-loop/reference.md` — Evaluator reference if Path B

### Configuration
- N/A

## Implementation Steps

1. Document the `check_stall` shell state pattern in `loop-types.md` (Path A)
2. Integrate pattern into harness loop type generation (FEAT-712 dependency)
3. Monitor usage; if pattern is duplicated across many loops, implement native `DiffStallEvaluator` (Path B)
4. If Path B: add evaluator, schema fields, validation, and tests

## Impact

- **Priority**: P3 - Safety improvement; prevents wasted iterations but workaround (max_iterations) exists
- **Effort**: Small (Path A) / Medium (Path B) - Template documentation vs. new evaluator implementation
- **Risk**: Low - Additive; no impact on existing loops
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | FSM evaluator API reference |

## Labels

`fsm-loops`, `evaluators`, `safety`, `captured`

## Verification Notes

- 2026-03-13 (`/ll:verify-issues --auto`): **VALID** — All file references confirmed to exist. `evaluate_convergence()` verified in `scripts/little_loops/fsm/evaluators.py`. No `diff_stall` evaluator exists in `evaluators.py`, `schema.py`, or `validation.py`. `check_commit` state confirmed in `loops/issue-refinement.yaml`. `skills/create-loop/loop-types.md` covers only numeric `convergence` evaluator — diff-based stall detection gap is real and unimplemented.

## Session Log
- `/ll:capture-issue` - 2026-03-12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b28391f-b086-4d28-86cb-448201c8b40e.jsonl`
- `/ll:format-issue` - 2026-03-13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:verify-issues` - 2026-03-13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:confidence-check` - 2026-03-13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`

---

## Status

**Open** | Created: 2026-03-12 | Priority: P3
