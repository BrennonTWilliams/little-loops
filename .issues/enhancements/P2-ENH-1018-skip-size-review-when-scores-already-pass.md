---
discovered_date: 2026-04-09
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-1018: Skip size-review when scores already pass thresholds in recursive-refine

## Summary

In `recursive-refine.yaml`, when the `refine-to-ready-issue` sub-loop fails or errors, the flow goes to `detect_children` → `size_review_snap` → `run_size_review` without ever checking whether the issue's confidence/outcome scores already meet project thresholds. This causes `/ll:issue-size-review` to run unnecessarily on issues that are already ready (e.g., scoring 100 readiness, 91 outcome).

## Context

**Direct mode**: User description: "add a score check before size_review_snap so it bails out early when thresholds are already met"

Running `recursive-refine` on another project showed `/ll:issue-size-review` firing on an issue that scored 100 confidence and 91 outcome — well above the configured thresholds (90 readiness, 75 outcome by default). The sub-loop had failed for unrelated reasons, but the issue's scores were already passing.

## Motivation

The `size_review_snap` → `run_size_review` path is reached whenever the sub-loop fails/errors and no children were detected. But failure in the sub-loop doesn't mean the issue's scores are insufficient — it could fail for other reasons (max iterations, action errors). Running size-review on an already-ready issue wastes a full LLM cycle and can decompose issues that don't need it.

## Current Behavior

The flow from `run_refine` is:

```
run_refine
  on_success → check_passed → (if pass) dequeue_next
                           → (if fail) detect_children → (if children) enqueue_children
                                                       → (no children) size_review_snap → run_size_review
  on_failure → detect_children → (no children) size_review_snap → run_size_review  ← bypasses check_passed
  on_error   → detect_children → (no children) size_review_snap → run_size_review  ← bypasses check_passed
```

When the sub-loop fails/errors, `check_passed` is never reached, so scores are never evaluated before `size_review_snap`.

## Proposed Solution

Add a new state (e.g., `recheck_scores`) between `size_review_snap` and `run_size_review` (or as a gate before `size_review_snap`) that:

1. Reads the issue's current `confidence` and `outcome` scores via `ll-issues show --json`
2. Compares against the project's `readiness_threshold` and `outcome_threshold` (from `ll-config.json` with context defaults as fallback)
3. If both thresholds are met → record the issue as passed and go to `dequeue_next`
4. If not met → proceed to `run_size_review`

This reuses the same scoring logic already in `check_passed` (lines 104-136).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — add `recheck_scores` state; update `size_review_snap` transitions

### Exact Edit Points
- `recursive-refine.yaml:198` — `next: run_size_review` → `next: recheck_scores`
- `recursive-refine.yaml:199` — `on_error: run_size_review` → `on_error: recheck_scores`
- Insert `recheck_scores` block between `size_review_snap` (line 188) and `run_size_review` (line 201)

### State Predecessors
- `recursive-refine.yaml:168` — `detect_children.on_no: size_review_snap` — the failure/error path that reaches `size_review_snap`, which will then pass through `recheck_scores`

### Patterns to Follow
- `recursive-refine.yaml:99-140` — `check_passed`: exact same Python logic and `fragment: shell_exit` structure; also writes to `.loops/tmp/recursive-refine-passed.txt` on pass
- `refine-to-ready-issue.yaml:110-141` — `check_scores`: identical Python body in sibling loop (no file write side-effect)
- `loops/lib/common.yaml:17-20` — `shell_exit` fragment: expands to `action_type: shell` + `evaluate: {type: exit_code}`

### Tests
- `scripts/tests/test_builtin_loops.py:800-815` — `test_required_states_exist`: add `recheck_scores` to the required states set
- `scripts/tests/test_builtin_loops.py:886` — `test_context_thresholds_defined`: no change needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py:836` — `test_builtin_loops_load_after_migration`: calls `load_and_validate("recursive-refine.yaml")`; will catch malformed `recheck_scores` wiring as a `ValueError` — no update needed, passive coverage
- `scripts/tests/test_builtin_loops.py` (new methods in `TestRecursiveRefineLoop`) — add routing assertions following the `check_scores` pattern from `TestRefineToReadyIssueSubLoop:506-538`:
  - `test_recheck_scores_routes_to_dequeue_next` — assert `recheck_scores.on_yes == "dequeue_next"`
  - `test_recheck_scores_on_no_routes_to_run_size_review` — assert `recheck_scores.on_no == "run_size_review"`
  - `test_recheck_scores_on_error_routes_to_run_size_review` — assert `recheck_scores.on_error == "run_size_review"`
  - `test_size_review_snap_routes_to_recheck_scores` — assert `size_review_snap.next == "recheck_scores"` (transition currently untested)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:363` — literal `size_review_snap → run_size_review` in ASCII FSM flow diagram; becomes stale after the change — update to show `size_review_snap → recheck_scores → [pass?] → dequeue_next / run_size_review`
- `docs/guides/LOOPS_GUIDE.md:326` — prose "If the sub-loop exits without meeting thresholds, the loop runs `/ll:issue-size-review`…" becomes incomplete (doesn't mention early-exit path) — consider a one-line addition about the score gate

### New `recheck_scores` State (exact YAML pattern)

```yaml
  recheck_scores:
    # Gate before size-review: if the issue already meets thresholds, skip size-review.
    # Scores can pass even when the sub-loop failed/errored (e.g., max-iterations hit
    # while the issue was already ready). Mirrors check_passed logic exactly.
    action: |
      python3 << 'PYEOF'
      import json, sys, subprocess
      from pathlib import Path

      issue_id = '${captured.input.output}'

      p = Path('.ll/ll-config.json')
      cg = {}
      if p.exists():
          try:
              cg = json.loads(p.read_text()).get('commands', {}).get('confidence_gate', {})
          except Exception:
              pass
      readiness = cg.get('readiness_threshold', ${context.readiness_threshold})
      outcome = cg.get('outcome_threshold', ${context.outcome_threshold})

      r = subprocess.run(
          ['ll-issues', 'show', issue_id, '--json'],
          capture_output=True, text=True
      )
      try:
          d = json.loads(r.stdout)
      except Exception:
          sys.exit(1)

      passed = (int(d.get('confidence') or 0) >= readiness
                and int(d.get('outcome') or 0) >= outcome)
      if passed:
          with open('.loops/tmp/recursive-refine-passed.txt', 'a') as f:
              f.write(issue_id + '\n')
      sys.exit(0 if passed else 1)
      PYEOF
    fragment: shell_exit
    on_yes: dequeue_next
    on_no: run_size_review
    on_error: run_size_review
```

## Implementation Steps

1. In `recursive-refine.yaml:198-199`, change `size_review_snap`'s `next` and `on_error` from `run_size_review` to `recheck_scores`
2. Insert the `recheck_scores` state block (see Integration Map above) after `size_review_snap` and before `run_size_review` — use the `check_passed` state at lines 99-140 as the exact template; the only differences are `on_no: run_size_review` and `on_error: run_size_review` instead of `detect_children`
3. In `scripts/tests/test_builtin_loops.py:802-815`, add `"recheck_scores"` to the `required` states set for `recursive-refine`
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` to verify

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/guides/LOOPS_GUIDE.md:363` — replace the literal `size_review_snap → run_size_review` in the ASCII FSM flow diagram with `size_review_snap → recheck_scores → [pass?] → dequeue_next / run_size_review`
6. Add four routing assertion tests in `TestRecursiveRefineLoop` (`scripts/tests/test_builtin_loops.py`) following the `check_scores` pattern from `TestRefineToReadyIssueSubLoop:506-538` — see Tests section above for the specific methods

## API/Interface

No public API changes. Internal FSM state additions only.

## Files

- `scripts/little_loops/loops/recursive-refine.yaml` — add `recheck_scores` state, update `size_review_snap` transitions (lines 198-199)
- `scripts/tests/test_builtin_loops.py` — add `recheck_scores` to required states set (lines 800-815)

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md` — loop authoring guide; documents `recursive-refine`, `check_passed`, `size_review_snap`, and threshold config keys
- `docs/generalized-fsm-loop.md` — FSM loop architecture; documents threshold config pattern
- `docs/reference/CONFIGURATION.md` — documents `readiness_threshold` and `outcome_threshold` config keys

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:refine-issue` - 2026-04-10T20:31:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/900e505a-d87a-4ad9-aa90-d4b0345226d2.jsonl`
- `/ll:wire-issue` - 2026-04-10T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/900e505a-d87a-4ad9-aa90-d4b0345226d2.jsonl`
- `/ll:confidence-check` - 2026-04-10T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f66535a9-97f7-4f0b-9fee-c1fe9f2acdf1.jsonl`

---

## Status

**Open** | Created: 2026-04-09 | Priority: P2
