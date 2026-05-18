---
discovered_date: 2026-05-17
discovered_by: loop-audit
status: open
---

# BUG-1602: hitl-compare evaluate state routes to generate on Playwright failure — silent infinite cycle

## Summary

When Playwright is not installed, `hitl-compare`'s `evaluate` state routes `on_no: generate` and `on_error: generate`. Because `generate` routes unconditionally to `evaluate` via `next: evaluate`, the loop cycles silently between the two states until `max_iterations: 20` is exhausted — burning 20 LLM calls with no useful output and no diagnostic. The same bug exists in `html-anything.yaml` (same `on_no/on_error: generate` pattern, same unconditional `generate → evaluate` transition).

## Root Cause

`hitl-compare.yaml`, `evaluate` state (line 181–182):

```yaml
    on_yes: score
    on_no: generate    # BUG: routes back into the cycle
    on_error: generate # BUG: routes back into the cycle
```

`generate` state (line 165):
```yaml
    next: evaluate     # unconditional — always returns to evaluate
```

When Playwright is absent, `evaluate` fires `on_no: generate`. `generate` re-renders the same HTML (no `critique.md` exists on first iteration), then `evaluate` fails again. No progress is made. The loop exhausts `max_iterations` silently with `final_state: evaluate`, which is indistinguishable from a normal mid-run snapshot in `ll-loop history`.

This is the **infinite-cycle** failure mode in the loop-specialist taxonomy. The loop-specialist agent's failure detection would catch this via oscillation, but the loop itself has no guard.

## Affected Loops

| Loop | File | Affected Lines |
|------|------|---------------|
| `hitl-compare` | `scripts/little_loops/loops/hitl-compare.yaml` | 181–182 |
| `html-anything` | `scripts/little_loops/loops/html-anything.yaml` | 154–155 |

## Fix

Route `on_no` and `on_error` to `score` in the `evaluate` state. The `score` state's action should be updated to read `index.html` directly when `screenshot.png` is absent:

```yaml
  evaluate:
    on_yes: score
    on_no: score    # Playwright absent → LLM evaluates HTML source directly
    on_error: score
```

`score` action preamble (updated):
```
If ${captured.run_dir.output}/screenshot.png exists, read it to view the rendered review page.
Otherwise read ${captured.run_dir.output}/index.html directly to evaluate the HTML source.
```

## LOOPS_GUIDE Documentation

The guide at line 957 and 970 already documents the *intended* degradation behavior (LLM-only scoring) but the prose at line 916/970 incorrectly states `on_error: generate` "falls back to `generate`, which then proceeds to `score`" — which is false. The FSM flow diagram also shows `FAILED → generate` where it should show `FAILED → score`. Both must be corrected alongside the YAML fix.

## Impact

- **Priority**: P2 — affects any user without Playwright installed; failure is silent with no diagnostic
- **Effort**: Low — routing change in two YAML files + prose update in LOOPS_GUIDE.md
- **Risk**: Low — the `score` state already handles the case where `review.md` has no items; it just needs the screenshot-or-html fallback preamble

---

**Priority**: P2 | **Created**: 2026-05-17
