---
id: BUG-1602
type: BUG
priority: P2
title: "hitl-compare evaluate state routes to generate on Playwright failure \u2014\
  \ silent infinite cycle"
discovered_date: 2026-05-17
discovered_by: loop-audit
status: done
completed_at: 2026-05-18T07:05:26Z
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/loops/html-anything.yaml:154–155` — change `on_no: generate` and `on_error: generate` to `on_no: score` and `on_error: score` in the `evaluate` state
- `scripts/little_loops/loops/html-anything.yaml:141–146` — update comment that currently describes routing to `generate` on failure (conflicts with the design rule at LOOPS_GUIDE line 847)
- `scripts/little_loops/loops/html-anything.yaml:169–170` — add screenshot-or-HTML fallback to `score` state action; currently reads `screenshot.png` unconditionally; model after `hitl-compare.yaml:206–207`
- `docs/guides/LOOPS_GUIDE.md:892` — FSM flow diagram entry: `└─ FAILED  → generate (Playwright unavailable — LLM-only scoring)` must change to `└─ FAILED  → score (Playwright unavailable — LLM-only scoring)`
- `docs/guides/LOOPS_GUIDE.md:918` — prose: "falls back to `generate`, which then proceeds to `score`" must become "falls back to `score` directly for LLM-only evaluation of the HTML source"
- `scripts/tests/test_builtin_loops.py:2936–2944` — `TestHtmlAnythingLoop.test_evaluate_routes_to_generate_on_no` and `test_evaluate_on_error_routes_to_generate` assert the buggy routing; update to assert `score`
- `scripts/tests/test_builtin_loops.py:3082–3090` — `TestHitlCompareLoop.test_evaluate_routes_to_generate_on_no` and `test_evaluate_on_error_routes_to_generate` assert the old buggy routing (already broken by the hitl-compare fix); update to assert `score`

**Similar Patterns**
- `scripts/little_loops/loops/hitl-compare.yaml:183–197` — already-fixed `evaluate` state; use its `on_no: score`, `on_error: score` routing and comment language as the model
- `scripts/little_loops/loops/hitl-compare.yaml:206–207` — screenshot-or-HTML fallback preamble ("If screenshot.png exists, read it … Otherwise read index.html directly") — copy this pattern to `html-anything.yaml` score state

**Tests**
- `scripts/tests/test_builtin_loops.py` — `TestHtmlAnythingLoop` (lines ~2870–3014) and `TestHitlCompareLoop` (lines ~3016–3173) both have stale routing assertions that must be updated alongside the YAML changes

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- No runtime callers or importers — loop YAML files are loaded by name at runtime; no Python code imports `html-anything` or `hitl-compare` by path

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — add `### Fixed` entry for BUG-1602 in the current release section (the existing `## [1.102.0]` `### Added` entries for these loops do not name routing targets and do not need retroactive revision)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestHtmlAnythingLoop` (lines 2936–2939) — `test_evaluate_routes_to_generate_on_no`: change `assert state.get("on_no") == "generate"` → `== "score"`; update docstring from "route back to generate when screenshot fails" to "route to score for LLM-only fallback when screenshot fails" [update]
- `scripts/tests/test_builtin_loops.py::TestHtmlAnythingLoop` (lines 2941–2944) — `test_evaluate_on_error_routes_to_generate`: change `assert state.get("on_error") == "generate"` → `== "score"`; update docstring [update]
- `scripts/tests/test_builtin_loops.py::TestHitlCompareLoop` (lines 3082–3085) — same: assert `"score"` and update docstring [update — currently **failing** because `hitl-compare.yaml` YAML already fixed but test still asserts `"generate"`]
- `scripts/tests/test_builtin_loops.py::TestHitlCompareLoop` (lines 3087–3090) — same [update — currently **failing**]
- `scripts/tests/test_builtin_loops.py::TestHtmlAnythingLoop` — `test_score_action_has_screenshot_or_html_fallback` — new test verifying the `score` state action preamble contains the `"screenshot.png exists"` / `"Otherwise read"` conditional added in step 4; follow `test_score_action_reads_rubric_dynamically` (line ~2997) as pattern [new]

## Implementation Steps

1. ~~Fix `on_no`/`on_error` routing in `hitl-compare.yaml` `evaluate` state~~ — **already done** (Verification Notes confirm `on_no: score`, `on_error: score`)
2. Fix `html-anything.yaml` `evaluate` state routing: change `on_no: generate` → `on_no: score` and `on_error: generate` → `on_error: score` (lines 154–155)
3. Update the `evaluate` state comment in `html-anything.yaml` (lines 141–146) to match `hitl-compare.yaml:183–187` language describing graceful degradation to `score`
4. Add screenshot-or-HTML fallback preamble to `html-anything.yaml` `score` action (lines 169–170), following `hitl-compare.yaml:206–207`: "If `screenshot.png` exists, read it; otherwise read `index.html` directly"
5. Fix `docs/guides/LOOPS_GUIDE.md:892` FSM diagram: `FAILED → generate` → `FAILED → score`
6. Fix `docs/guides/LOOPS_GUIDE.md:918` prose: remove "falls back to `generate`, which then proceeds to `score`" → "falls back to `score` directly for LLM-only evaluation of the HTML source"
7. Update `test_builtin_loops.py` `TestHtmlAnythingLoop` (lines 2936–2944): change `assert state.get("on_no") == "generate"` and `assert state.get("on_error") == "generate"` to assert `"score"`; update docstrings to match
8. Update `test_builtin_loops.py` `TestHitlCompareLoop` (lines 3082–3090): same update — assert `"score"` and update docstrings
9. Add `TestHtmlAnythingLoop.test_score_action_has_screenshot_or_html_fallback` verifying the new `score` state fallback preamble in `html-anything.yaml`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Add `### Fixed` entry to `CHANGELOG.md` for BUG-1602 in the current release section: "`hitl-compare`, `html-anything`: fix silent infinite cycle when Playwright is absent — `evaluate` now routes `on_no`/`on_error` to `score` for LLM-only graceful degradation"
11. Verify: `python -m pytest scripts/tests/test_builtin_loops.py -k "HtmlAnything or HitlCompare" -v` passes

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
- `/ll:ready-issue` - 2026-05-18T07:03:16 - `3eaf5bb8-b9eb-4860-af89-a4d4e17c30d7.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `465df8a0-34fa-4f6a-9580-366c97ce73f9.jsonl`
- `/ll:wire-issue` - 2026-05-18T07:00:23 - `b07556c9-586e-4e8b-91ec-d7ed97af867a.jsonl`
- `/ll:refine-issue` - 2026-05-18T06:56:27 - `550b1b65-bc06-425e-8792-8868b508cc92.jsonl`
- `/ll:format-issue` - 2026-05-18T05:16:02 - `fb7f2fc9-52f4-4d22-8182-c197fa8741c5.jsonl`
- `/ll:verify-issues` - 2026-05-18T04:53:51 - `2807bd8b-4e79-4b76-994d-e6f6cae14245.jsonl`
