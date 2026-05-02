---
id: ENH-1334
type: ENH
priority: P3
parent_issue: ENH-1326
---

# ENH-1334: `analyze-loop` and `assess-loop` Skill Updates for Sub-loop Visibility

## Summary

Update `skills/analyze-loop/SKILL.md` to use `ll-loop show --resolved --json`, walk `_subloop` keys in Step 3b goal alignment, and add a new `BUG — Sub-loop verdict discarded` signal for verdict laundering. Also update `skills/assess-loop/SKILL.md` for consistent sub-loop visibility, and update all relevant documentation.

## Parent Issue

Decomposed from ENH-1326: `/ll:analyze-loop` Should Resolve `from:`, Fragments, and Sub-loops Before Judging

## Dependency

**Requires ENH-1333 to be merged first** — the `--resolved` flag must exist in `ll-loop show` before this skill update goes live.

## Background

`/ll:analyze-loop` Step 2 currently calls `ll-loop show <loop> --json` and treats the output as authoritative. After ENH-1333, the `--resolved` flag is available and returns sub-loop state maps under `_subloop` keys. This child updates both analyze-loop and assess-loop skills to use the resolved output, classifying sub-loop states and detecting verdict laundering.

## Implementation Steps

1. **Update `skills/analyze-loop/SKILL.md` Step 2** — change the `ll-loop show <loop_name> --json` call to `ll-loop show <loop_name> --resolved --json`. Add a note that states with `_subloop` contain the child's resolved state map one level deep.

2. **Update Step 3b to walk `_subloop` entries** — when a parent state has `_subloop`, treat sub-loop states as separate counters (do not add to parent totals). Flag cross-boundary routing distinctly. Reference `skills/assess-loop/SKILL.md` Step 8 for the verdict-laundering check pattern already implemented for `assess-loop`.

3. **Add sub-loop verdict laundering signal** — when a state has `loop:`, check whether `on_yes == on_no` (parent routing). If identical, emit `BUG — Sub-loop verdict discarded` (P3). Reference the existing fixture at `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` which demonstrates the exact scenario.

4. **Update `skills/assess-loop/SKILL.md`** — Step 2 also uses `ll-loop show --json`; update to `--resolved` for consistent sub-loop visibility. This resolves the coupling risk noted in the confidence check: if deferred, the two skills have inconsistent sub-loop visibility.

5. **Update `docs/reference/COMMANDS.md`** — `/ll:analyze-loop` entry (around line 529): note that Step 2 uses `--resolved --json` and sub-loop states are now visible to signal detection.

6. **Update `docs/reference/COMMANDS.md`** — `/ll:assess-loop` entry (around line 577): reflect sub-loop laundering detection improvement.

7. **Add `CHANGELOG.md` entry** — add a new concrete version entry for the sub-loop resolution feature (do not add under `[Unreleased]`; promote to a concrete `## [X.Y.Z] - DATE` section).

## Integration Map

### Files to Modify
- `skills/analyze-loop/SKILL.md` — Step 2: use `--resolved --json`; Step 3b: walk `_subloop`; new laundering signal
- `skills/assess-loop/SKILL.md` — Step 2: use `--resolved --json` for consistent sub-loop visibility
- `docs/reference/COMMANDS.md` — analyze-loop and assess-loop entries

### Files to Create
- `CHANGELOG.md` entry (new version section)

### Similar Patterns
- `skills/assess-loop/SKILL.md` Step 8 — existing verdict-laundering check pattern to replicate in `analyze-loop`
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — existing fixture demonstrating the laundering scenario (`eval-driven-development.refine_issues` where `on_yes` and `on_no` may both route to `tradeoff_review`)

### Acceptance Target Loops
- `scripts/little_loops/loops/eval-driven-development.yaml` — two-level sub-loop chain: should now report the sub-loop verdict laundering at `refine_issues`
- `scripts/little_loops/loops/apo-textgrad.yaml` — uses `from:` + fragments: `analyze-loop` output unchanged (inheritance already resolved by `--resolved`)

## Acceptance Criteria

- [ ] `/ll:analyze-loop` on `eval-driven-development` reports `BUG — Sub-loop verdict discarded` at `refine_issues` (where `on_yes` and `on_no` route to the same downstream state).
- [ ] `/ll:analyze-loop` on `apo-textgrad` correctly classifies its `apply_gradient` and `compute_gradient` states (no regression).
- [ ] Existing `analyze-loop` tests pass (no regressions on loops without sub-loops).
- [ ] `skills/assess-loop/SKILL.md` uses `--resolved --json` (consistent sub-loop visibility).
- [ ] `docs/reference/COMMANDS.md` reflects the changes for both skills.
- [ ] `CHANGELOG.md` has a concrete version entry for this feature.

## Session Log
- `/ll:issue-size-review` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3504f81c-8403-4c3e-84f2-f27905b579d2.jsonl`
