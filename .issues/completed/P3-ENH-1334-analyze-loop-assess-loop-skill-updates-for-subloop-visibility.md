---
id: ENH-1334
type: ENH
priority: P3
parent_issue: ENH-1326
decision_needed: false
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-02T22:11:40Z
---

# ENH-1334: `analyze-loop` and `assess-loop` Skill Updates for Sub-loop Visibility

## Summary

Update `skills/analyze-loop/SKILL.md` to use `ll-loop show --resolved --json`, walk `_subloop` keys in Step 3b goal alignment, and add a new `BUG — Sub-loop verdict discarded` signal for verdict laundering. Also update `skills/assess-loop/SKILL.md` for consistent sub-loop visibility, and update all relevant documentation.

## Current Behavior

Both `/ll:analyze-loop` and `/ll:assess-loop` call `ll-loop show <loop_name> --json` without the `--resolved` flag. Sub-loop state maps (under `_subloop` keys) are never present in the output, so child loop states are invisible to signal detection. Verdict laundering — where `on_yes` and `on_no` on a sub-loop state route to the same destination — goes undetected.

## Expected Behavior

Both skills call `ll-loop show <loop_name> --resolved --json`. Sub-loop states appear under `_subloop` keys in the output. `analyze-loop` Step 3b walks these entries as separate counters and emits `BUG — Sub-loop verdict discarded` (P3) when `on_yes == on_no` on any state with a `loop:` key. Both skills provide consistent sub-loop visibility.

## Current Pain Point

Sub-loop verdict laundering is structurally undetectable with the current `--json` output. The `eval-driven-development` loop has a real laundering bug at `refine_issues` (`on_yes == on_no == "tradeoff_review"`) that both skills silently miss today.

## Impact

Medium — improves correctness of loop analysis for any loop with sub-loops; surfaces a real production laundering bug in `eval-driven-development`; prevents future laundering bugs from going undetected.

## Scope Boundaries

Out of scope: multi-level sub-loop traversal beyond one level deep (the `--resolved` output is one level only); changes to the FSM executor or `ll-loop show` CLI (covered by ENH-1333); new FSM state types.

## Labels

`enhancement`, `loops`, `analyze-loop`, `assess-loop`, `subloop-visibility`

## Status

Completed

## Resolution

Updated `skills/analyze-loop/SKILL.md` to use `--resolved --json` in Step 2, added `BUG — Sub-loop verdict discarded` (P3) signal in Step 3, and extended Step 3b-3 goal alignment to treat `_subloop` states as a separate execution scope. Updated `skills/assess-loop/SKILL.md` Step 2 to use `--resolved --json`. Updated `docs/reference/COMMANDS.md` for both skills, added CHANGELOG `[1.94.0]` entry, and added tests covering the `--resolved` flag assertions and verdict-laundering discriminators.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/tests/test_enh1268_doc_wiring.py` — add test methods to `TestAnalyzeLoopCommandsWiring` (assert `"--resolved"` and `"Sub-loop verdict discarded"` in the analyze-loop COMMANDS.md section) and `TestAssessLoopCommandsWiring` (assert `"--resolved"` in the assess-loop COMMANDS.md section); follow the existing pattern of `content.index` + string-in-section assertion
9. Update `scripts/tests/test_assess_loop_skill.py` — add `assert "--resolved" in content` to the skill-existence checks in `TestAssessLoopSkill` (alongside the existing `"--tail"` and `"--no-rubric-audit"` assertions)

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

### Tests
- `scripts/tests/test_analyze_loop_synthesis.py` — existing analyze-loop skill tests (`TestAnalyzeLoopSynthesis`); add a new test group for the verdict-laundering signal mirroring the structure in `test_assess_loop_skill.py:TestAssessLoopSkill` (lines 249–287)
- `scripts/tests/test_assess_loop_skill.py` — reference: `TestAssessLoopSkill` laundering discriminator tests (lines 249–287) as pattern to mirror; uses `_load_fixture()` + `_happy_path()` helpers
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — can be reused in `test_analyze_loop_synthesis.py`; demonstrates `on_yes == on_no == "report_done"` on `run_eval` state (with `loop: inner-eval`)
- `scripts/tests/fixtures/fsm/inner-eval.yaml` — companion child loop fixture for the laundering scenario

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1268_doc_wiring.py` — update `TestAnalyzeLoopCommandsWiring` and `TestAssessLoopCommandsWiring` to add assertions that `--resolved` and `BUG — Sub-loop verdict discarded` appear in the respective COMMANDS.md sections; without these, no automated guard exists that the Step 5–6 COMMANDS.md edits were actually made [Agent 2/3 finding]
- `scripts/tests/test_assess_loop_skill.py` — add a `--resolved` string assertion (alongside existing `--tail` and `--no-rubric-audit` checks in `TestAssessLoopSkill`) to verify the Step 4 `--resolved` update was applied to `assess-loop` SKILL.md [Agent 3 finding]

### Acceptance Target Loops
- `scripts/little_loops/loops/eval-driven-development.yaml` — two-level sub-loop chain: should now report the sub-loop verdict laundering at `refine_issues`
- `scripts/little_loops/loops/apo-textgrad.yaml` — uses `from:` + fragments: `analyze-loop` output unchanged (inheritance already resolved by `--resolved`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Current `ll-loop show` call in `skills/analyze-loop/SKILL.md` Step 2** (line 94): `ll-loop show <loop_name> --json 2>/dev/null` — no `--resolved` flag; `_subloop` keys are never present in the output today
- **Current `ll-loop show` call in `skills/assess-loop/SKILL.md` Step 2**: `ll-loop show <loop_name> --json` — same gap; Step 8 laundering check reads `on_yes`/`on_no` from the parent state dict but never inspects child states via `_subloop`
- **`_subloop` output format** (`scripts/little_loops/cli/loop/info.py:cmd_show()` lines 644–655): a flat `dict[str, Any]` of child state name → child state config, injected into the parent state dict under the `"_subloop"` key; one level deep only; silently omitted if child loop file not found
- **Laundering signal condition** (exact check to implement, mirroring `skills/assess-loop/SKILL.md` Step 8): `state.on_yes == state.on_no` for any state with a `"loop"` key; flag as `BUG — Sub-loop verdict discarded` (P3) with state name, child loop name, and shared next state
- **Real-world laundering site** in `scripts/little_loops/loops/eval-driven-development.yaml` `refine_issues` state (lines 84–88): `loop: issue-refinement`, `on_yes: tradeoff_review`, `on_no: tradeoff_review` — both route identically
- **CHANGELOG**: latest version is `[1.93.0] - 2026-05-02`; new entry for this feature should be `[1.94.0] - <date>` under `### Changed` (do not use `[Unreleased]`)

## Acceptance Criteria

- [ ] `/ll:analyze-loop` on `eval-driven-development` reports `BUG — Sub-loop verdict discarded` at `refine_issues` (where `on_yes` and `on_no` route to the same downstream state).
- [ ] `/ll:analyze-loop` on `apo-textgrad` correctly classifies its `apply_gradient` and `compute_gradient` states (no regression).
- [ ] Existing `analyze-loop` tests pass (no regressions on loops without sub-loops).
- [ ] `skills/assess-loop/SKILL.md` uses `--resolved --json` (consistent sub-loop visibility).
- [ ] `docs/reference/COMMANDS.md` reflects the changes for both skills.
- [ ] `CHANGELOG.md` has a concrete version entry for this feature.

## Session Log
- `/ll:ready-issue` - 2026-05-02T22:06:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fdd4212-fc02-43a9-9e94-752f1aa7978d.jsonl`
- `/ll:wire-issue` - 2026-05-02T22:00:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27f9da25-a1d2-499c-84b9-e83590563a74.jsonl`
- `/ll:refine-issue` - 2026-05-02T21:53:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dbbd92dc-73ed-4451-aa3a-17cbb48f088e.jsonl`
- `/ll:issue-size-review` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3504f81c-8403-4c3e-84f2-f27905b579d2.jsonl`
- `/ll:confidence-check` - 2026-05-02T22:15:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c51ea87-f6f1-4bd7-b5b7-ebc3d2b8ed8f.jsonl`
