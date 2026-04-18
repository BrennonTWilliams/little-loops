---
id: 1182
type: BUG
priority: P2
captured_at: "2026-04-18T21:39:42Z"
discovered_date: "2026-04-18"
discovered_by: capture-issue
---

# BUG-1182: Score-state `PASS` pattern matches per-criterion annotations in loop evaluators

## Summary

Built-in FSM loop evaluators use `output_contains` with `pattern: "PASS"` to route between `on_yes` (done) and `on_no` (iterate). The scoring prompt also emits per-criterion annotations in the output body (e.g. `design_quality: 8/10 — PASS`), so the substring match fires on the annotation even when the overall verdict is `ITERATE`. The loop exits prematurely with failing criteria.

## Affected Files

- `scripts/little_loops/loops/html-website-generator.yaml` (lines 84–128)
- `scripts/little_loops/loops/svg-textgrad.yaml` (lines 98–143)
- `scripts/little_loops/loops/svg-image-generator.yaml` (line 148 — also has `pattern: "PASS"`; verify scoring prompt behavior matches)

## Root Cause

The `score` state's `evaluate.pattern` is the substring `"PASS"`. The LLM scoring prompt is free-form and includes `PASS` inside per-criterion annotations, so `output_contains` matches the annotation rather than the final verdict line.

File anchors:
- `scripts/little_loops/loops/html-website-generator.yaml:122` — `output exactly: PASS`
- `scripts/little_loops/loops/html-website-generator.yaml:126` — `pattern: "PASS"`
- `scripts/little_loops/loops/svg-textgrad.yaml:136` — `output exactly: PASS`
- `scripts/little_loops/loops/svg-textgrad.yaml:140` — `pattern: "PASS"`

## Reproduction

1. Run `ll-loop run html-website-generator` with a description.
2. Observe a score iteration where at least one criterion annotation contains `PASS` but the final verdict is `ITERATE`.
3. The loop routes to `done` instead of continuing to `generate`.

## Fix

Straight string substitution to a compound token (consistent with existing conventions like `CONVERGED`, `BOTTLENECK_BLOAT`, `PHASE1_PASS` in other built-in loops):

**html-website-generator.yaml**
- Line 122: `output exactly: PASS` → `output exactly: ALL_PASS`
- Line 126: `pattern: "PASS"` → `pattern: "ALL_PASS"`
- Line 87 comment: update `"PASS"` → `"ALL_PASS"`

**svg-textgrad.yaml**
- Line 136: `output exactly: PASS` → `output exactly: ALL_PASS`
- Line 140: `pattern: "PASS"` → `pattern: "ALL_PASS"`

**svg-image-generator.yaml** (verify and apply same substitution if the scoring prompt has the same shape)
- Line 148: `pattern: "PASS"` → `pattern: "ALL_PASS"`
- Update matching `output exactly: PASS` line in the scoring prompt.

No logic changes — evaluator routing semantics are preserved, only the token is disambiguated.

## Regression Guard

Add structural tests in `scripts/tests/test_builtin_loops.py` asserting that no `score` state in any built-in loop uses `pattern: "PASS"` as a bare token. Example shape:

```python
def test_score_evaluators_use_unambiguous_tokens():
    for loop in load_all_builtin_loops():
        for name, state in loop.states.items():
            if "score" in name or state.get("evaluate", {}).get("type") == "output_contains":
                pattern = state["evaluate"]["pattern"]
                assert pattern != "PASS", (
                    f"{loop.name}/{name} uses ambiguous 'PASS' token — "
                    "scoring output annotations will match"
                )
```

## Acceptance Criteria

- [ ] All three built-in loops use a compound token (e.g. `ALL_PASS`) instead of bare `PASS`.
- [ ] `evaluate.pattern` and the scoring prompt's final output instruction are in sync in every affected file.
- [ ] Structural guard test in `scripts/tests/test_builtin_loops.py` asserts the pattern is never `"PASS"` for `score`-state evaluators.
- [ ] Existing loop tests still pass.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM evaluator semantics (`output_contains` routing). |
| `.claude/CLAUDE.md` | Built-in loops live under `scripts/little_loops/loops/`. |

## Session Log
- `/ll:capture-issue` - 2026-04-18T21:39:42Z - user-provided direct mode
