---
id: ENH-1795
type: ENH
title: Action-level loop detection (complement to diff_stall)
priority: P3
status: open
captured_at: '2026-05-29T20:37:23Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
  - captured
  - fsm
  - stall-detector
  - loops
  - harness
relates_to: [BUG-1767, BUG-1766]
parent: EPIC-1663
---

# ENH-1795: Action-level loop detection (complement to `diff_stall`)

## Summary

Add a second stall-detection mode to the harness that fires when the
**same action string** or **same captured output** repeats for N
consecutive iterations, regardless of git diff state. Today `check_stall`
(`diff_stall` evaluator) only catches "no file changes" stalls; it misses
the symmetric failure where a skill *does* mutate files but keeps
executing the identical no-op action (or the same skill invocation
producing the same output text).

## Motivation

This enhancement would:
- Prevent silent exhaustion of `max_iterations` when a loop has converged
  to a fixed point that `diff_stall` can't detect because the skill mutates
  files on each pass
- Reduce wasted LLM token costs from repeated identical action executions
  in loops that have already reached their effective output
- Complement existing `diff_stall` to provide robust stall-detection
  coverage across both "no changes" and "identical changes" failure modes

## Current Behavior

- `check_stall.evaluate.type: diff_stall` records `git diff --stat`
  output and fingerprints `progress_paths`; if the fingerprint changes,
  the deque resets and the stall window restarts (per BUG-1674 / -1767).
- A loop that keeps calling, say, `/ll:refine-issue ${captured.current_item.output}`
  and gets back the identical "already refined" output for 10 cycles
  produces no `diff_stall` signal as long as anything in the working
  tree changes.
- The harness silently exhausts `max_iterations` even though the loop
  has visibly converged to a fixed point.

DeerFlow's `LoopDetectionMiddleware` hard-stops on repeated tool-call
patterns; we have nothing analogous at the action / output level.

## Expected Behavior

A new evaluator (working name `action_stall` or `output_repeat`) that:

1. Records a hash of (state, expanded action string, captured output)
   per iteration.
2. Fires `no` after `max_repeat` consecutive identical hashes (default
   `2`).
3. Composes with `diff_stall` — either evaluator can short-circuit the
   chain; both are cheap.
4. Reports the repeated payload in the `LLEvent` so the operator can
   see *what* repeated.

Example:

```yaml
check_action_stall:
  action_type: shell
  action: "echo 'probe'"
  evaluate:
    type: action_stall
    track: ["action", "captured.execute.output"]
    max_repeat: 2
  on_yes: check_concrete
  on_no: advance
```

## Proposed Solution

Add a new `action_stall` evaluator class alongside the existing `diff_stall`
evaluator, following the same pattern:

- **New file**: `scripts/little_loops/evaluators/action_stall.py`
- **Class**: `ActionStallEvaluator` — hashes (state, expanded action string,
  captured output) per iteration; maintains a bounded deque; fires `no` when
  `max_repeat` consecutive identical hashes detected
- **Runner wiring**: register in `scripts/little_loops/runner.py` so it
  participates in the routing chain identically to `diff_stall`
- **Validator**: add `action_stall` as a known evaluator type in
  `ll-loop validate`
- **LLEvent payload**: include the repeated payload hash and iteration
  indices so the operator can see *what* repeated

The evaluator composes with `diff_stall` — both sit in the routing chain and
either can short-circuit to `advance` when their respective stall condition
is met.

## Success Metrics

- Loops with output-repeat stalls: detected within `max_repeat` (default 2)
  iterations vs exhausting `max_iterations` (current behavior)
- False positive rate: 0% on loops with genuine iterative progress where
  actions repeat but captured output differs
- Per-iteration overhead: <1ms for hash computation and deque comparison
- Adoption: existing loops can opt in with a 4-line YAML block

## Scope Boundaries

- **In scope**:
  - New `action_stall` evaluator class in `scripts/little_loops/evaluators/`
  - Runner wiring to invoke the evaluator as part of the routing chain
  - Validator support in `ll-loop validate`
  - `LLEvent` payload reporting of repeated content hash and iteration indices
  - Configuration via `track` field (list of capture keys to hash) and
    `max_repeat` threshold (default 2)
  - Composition with existing `diff_stall` evaluator (both in routing chain)
- **Out of scope**:
  - Replacing or modifying existing `diff_stall` evaluator behavior
  - Auto-detecting which actions to track (user configures via YAML)
  - ML-based or fuzzy detection of "near-repeat" patterns
  - Integration with DeerFlow or other external loop detection systems

## API/Interface

New evaluator class:

```python
class ActionStallEvaluator:
    """Detect repeated action/output patterns that indicate stalled loops."""
    def evaluate(self, track: list[str], max_repeat: int = 2) -> bool: ...
```

YAML configuration interface (per-loop, in loop YAML):

```yaml
evaluate:
  type: action_stall
  track: ["action", "captured.execute.output"]
  max_repeat: 2
```

No changes to existing evaluator interfaces or public CLI surface.

## Integration Map

### Files to Modify
- `scripts/little_loops/evaluators/action_stall.py` — New evaluator class
- `scripts/little_loops/evaluators/__init__.py` — Register new evaluator
- `scripts/little_loops/runner.py` — Wire evaluator into routing chain
- `scripts/little_loops/validators/loop_validator.py` — Add `action_stall`
  to known evaluator types
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Document stall detection
  options

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "diff_stall" scripts/`
- TBD - use grep to find references: `grep -r "check_stall" loops/`

### Similar Patterns
- `scripts/little_loops/evaluators/diff_stall.py` — Existing stall
  evaluator to follow as implementation pattern
- `scripts/little_loops/evaluators/convergence.py` — Another numeric
  evaluator with deque-based tracking

### Tests
- `scripts/tests/test_action_stall.py` — New test file

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Add action_stall entry
  to § Stall Detection

### Configuration
- N/A — Evaluator is configured per-loop in loop YAML; no global config
  changes needed

## Implementation Steps

1. Study existing `diff_stall` evaluator as reference pattern
2. Implement `ActionStallEvaluator` class with hash tracking, bounded
   deque, and `max_repeat` threshold
3. Register evaluator in runner routing chain alongside `diff_stall`
4. Add validator support in `ll-loop validate` (known evaluator types list)
5. Wire `action_stall` result into `LLEvent` payload for operator visibility
6. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Stall Detection
   with action_stall entry and composition guidance
7. Write tests for hash tracking, reset-on-change behavior, and composition
   with `diff_stall`

## Impact

- **Priority**: P3 — high-utility second guard; doesn't block existing
  loops but materially improves cost behavior of prompt-based skills.
- **Effort**: Small-to-Medium — new evaluator class, runner wiring,
  validator entry, docs.
- **Risk**: Low — opt-in; default behavior unchanged.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Stall Detection | Phase ordering and decision guide need a second entry |
| `BUG-1767` | Documents the related blind spot in progress_paths fingerprinting |

## Labels

`captured`, `fsm`, `harness`, `loops`, `stall-detector`

## Status

**Open** | Created: 2026-05-29 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-05-29T21:13:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04006cb6-ee11-466d-86cf-3f1e99cff482.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`
