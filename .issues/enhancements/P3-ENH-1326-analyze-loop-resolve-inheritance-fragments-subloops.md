---
id: ENH-1326
type: ENH
priority: P3
captured_at: "2026-05-02T19:05:00Z"
discovered_date: "2026-05-02"
discovered_by: capture-issue
---

# ENH-1326: `/ll:analyze-loop` Should Resolve `from:`, Fragments, and Sub-loops Before Judging

## Summary

`/ll:analyze-loop` Step 2 currently calls `ll-loop show <loop> --json` once and treats the resulting state map as authoritative. That output reflects only the literal YAML file. It does not merge `from:` inheritance, expand `fragment:` references against `lib/*.yaml`, or follow `loop:` sub-loop refs. Loops that depend on those mechanisms are effectively invisible to the analyzer's signal classifier and to Step 3b goal alignment.

## Motivation

Concrete loops the current resolver fails on:

- **`apo-textgrad`** extends `lib/apo-base.yaml` via `from:` — its real state graph isn't visible in `ll-loop show` output without the merge.
- **`eval-driven-development`** has `loop: issue-refinement` on `refine_issues`; `issue-refinement` itself has `loop: refine-to-ready-issue`. The actual work happens two levels down. Current analyzer can't see whether the child's verdict was discarded.
- **Any loop using `with_rate_limit_handling`, `shell_exit`, `llm_gate`, `numeric_gate`, `run_benchmark`** — the `evaluate` semantics live in the fragment, not the calling state. Step 3 signal rules need the resolved evaluator type to apply correctly.
- **Sub-loop verdict laundering** (`eval-driven-development.refine_issues` mapping `on_yes` and `on_no` to the same downstream state) is a real category of bug that's only detectable across the loop boundary.

## Current Behavior

`SKILL.md:91-97` calls:

```bash
ll-loop show <loop_name> --json
```

and parses `"states"` directly. Inheritance, fragments, and sub-loops are not followed.

## Expected Behavior

Step 2 (or a new Step 2b inserted before classification) produces a **resolved state map**:

1. If the loop has `from: <parent>`, recursively load and deep-merge the parent first (state-level merge, child wins on key conflict).
2. For any state with `fragment: <name>`, look up `<name>` in the imported `lib/*.yaml` (per the `import:` declarations) and merge fragment fields underneath state-local fields.
3. For any state with `loop: <child>`, parse the child YAML one level deep and attach its resolved state map under a `_subloop` key on the parent state.
4. Classification (Step 3) and goal alignment (Step 3b) operate on the resolved map.

## Implementation Steps

1. Add a helper (likely in `little_loops/loops/resolver.py` or extend an existing parser) that performs the three merges. The fragment merger already exists for the runtime — reuse rather than duplicate.
2. Surface a new CLI flag `ll-loop show <name> --resolved --json` that returns the fully resolved state map. Skill consumes this.
3. Update `skills/analyze-loop/SKILL.md` Step 2 to call `--resolved`; document that all subsequent steps see the merged graph.
4. Update Step 3b to walk `_subloop` entries when computing dominant-state and goal-alignment signals (decide: do sub-loop iterations count toward parent's totals, or stay separate? Recommend separate, with the cross-boundary signal flagged distinctly).
5. Add a sub-loop-verdict-laundering signal: when a state has `loop:`, check whether `on_success` and `on_failure` route to different downstream states. If identical, emit BUG signal.

## API/Interface

- New: `ll-loop show <name> --resolved --json`
- Skill change: `analyze-loop` Step 2 uses `--resolved` and parses `_subloop` keys.
- New signal: `BUG — Sub-loop verdict discarded` (P3) when child's terminal verdict doesn't differentiate parent routing.

## Acceptance Criteria

- [ ] `ll-loop show --resolved --json` returns a merged state map for loops using `from:`, `fragment:`, and `loop:`.
- [ ] `/ll:analyze-loop` on `apo-textgrad` correctly classifies its `apply_gradient` and `compute_gradient` states (which depend on `lib/apo-base` inheritance).
- [ ] `/ll:analyze-loop` on `eval-driven-development` reports the sub-loop verdict laundering at `refine_issues` (where `on_yes` and `on_no` may both route to `tradeoff_review`).
- [ ] Existing tests for `/ll:analyze-loop` still pass (no regressions on loops without inheritance/fragments/sub-loops).

## Labels

`enhancement`, `loops`, `analysis`, `captured`

## Status

**Open** | Created: 2026-05-02 | Priority: P3
