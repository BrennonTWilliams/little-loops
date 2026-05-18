---
id: BUG-1602
type: BUG
priority: P2
title: "hitl-compare evaluate state routes to generate on Playwright failure — silent infinite cycle"
discovered_date: 2026-05-17
discovered_by: loop-audit
status: open
---

# BUG-1602: hitl-compare evaluate state routes to generate on Playwright failure — silent infinite cycle

## Summary

When Playwright is not installed, `hitl-compare`'s `evaluate` state routes `on_no: generate` and `on_error: generate`. Because `generate` routes unconditionally to `evaluate` via `next: evaluate`, the loop cycles silently between the two states until `max_iterations: 20` is exhausted — burning 20 LLM calls with no useful output and no diagnostic. The same bug exists in `html-anything.yaml` (same `on_no/on_error: generate` pattern, same unconditional `generate → evaluate` transition).

## Current Behavior

When Playwright is not installed, `evaluate` routes `on_no: generate` and `on_error: generate`. `generate` unconditionally routes back to `evaluate` via `next: evaluate`. The loop cycles silently between the two states until `max_iterations: 20` is exhausted with no diagnostic output. `ll-loop history` shows `final_state: evaluate`, which is indistinguishable from a normal mid-run snapshot.

## Expected Behavior

`evaluate` should route `on_no: score` and `on_error: score` so the loop degrades gracefully when Playwright is absent. The `score` state produces a diagnostic summary by reading `index.html` directly. `ll-loop history` reflects a meaningful terminal state with output.

## Steps to Reproduce

1. Ensure Playwright is not installed (`playwright` command returns not found or is not in PATH)
2. Run `ll-loop run hitl-compare` with a sample HTML task
3. Observe: loop runs all 20 iterations cycling between `evaluate` and `generate`
4. Run `ll-loop history hitl-compare` — observe `final_state: evaluate` with no diagnostic output

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

## Proposed Solution

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

## Implementation Steps

1. Fix `on_no`/`on_error` routing in `hitl-compare.yaml` `evaluate` state → route to `score`
2. Fix same routing in `html-anything.yaml` `evaluate` state → route to `score`
3. Add screenshot-or-HTML fallback preamble to the `score` action in both loops
4. Correct `docs/guides/LOOPS_GUIDE.md` lines 892 and 918 (FSM diagram + prose)
5. Verify: run `ll-loop run hitl-compare` without Playwright, confirm `score` state executes and produces output

## Impact

- **Priority**: P2 — affects any user without Playwright installed; failure is silent with no diagnostic
- **Effort**: Low — routing change in two YAML files + prose update in LOOPS_GUIDE.md
- **Risk**: Low — the `score` state already handles the case where `review.md` has no items; it just needs the screenshot-or-html fallback preamble
- **Breaking Change**: No

## Labels

`bug`, `loops`, `hitl-compare`, `html-anything`

---

**Priority**: P2 | **Created**: 2026-05-17

## Verification Notes

**Verdict**: OUTDATED — Re-verified 2026-05-17

- `scripts/little_loops/loops/hitl-compare.yaml` — `evaluate` state now routes `on_no: score` and `on_error: score` ✓ (fix applied)
- `scripts/little_loops/loops/html-anything.yaml:154–155` — still routes `on_no: generate` and `on_error: generate` ✗ (bug persists)
- `docs/guides/LOOPS_GUIDE.md:847` — new design rule added: "route on_no/on_error to score, never back to generate" ✓
- `docs/guides/LOOPS_GUIDE.md:892` — FSM diagram still shows `FAILED → generate (Playwright unavailable)` ✗ (inaccurate)
- `docs/guides/LOOPS_GUIDE.md:918` — prose still says "falls back to `generate`, which then proceeds to `score`" ✗ (inaccurate)
- Remaining scope: fix `html-anything.yaml` routing + correct LOOPS_GUIDE lines 892 and 918


## Session Log
- `/ll:format-issue` - 2026-05-18T05:16:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb7f2fc9-52f4-4d22-8182-c197fa8741c5.jsonl`
- `/ll:verify-issues` - 2026-05-18T04:53:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2807bd8b-4e79-4b76-994d-e6f6cae14245.jsonl`
