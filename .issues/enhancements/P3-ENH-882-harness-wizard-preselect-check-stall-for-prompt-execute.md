---
id: ENH-882
type: ENH
priority: P3
status: open
discovered_date: 2026-03-24
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 82
---

# ENH-882: Harness wizard should pre-select `check_stall` when `execute` uses `action_type: prompt`

## Summary

Harness wizard Step H3 (evaluation phase selection) omits `check_stall` (diff_stall evaluator) as an option. When an `execute` state uses `action_type: prompt` or `slash_command`, silent no-ops can pass all other evaluators (`check_semantic`, `check_invariants`), consuming the entire `max_iterations` budget with zero progress and no diagnostic signal. Pre-selecting stall detection for prompt-based executes closes this failure mode.

## Current Behavior

Wizard Step H3 presents 4 evaluation phase options (Tool-based gates, LLM-as-judge, Diff invariants, Skill-based evaluation). `check_stall` (diff_stall evaluator) is absent from the multi-select list. Users must manually discover it in post-template prose at `skills/create-loop/loop-types.md:814` or in the low-visibility `## Stall Detection` section of `AUTOMATIC_HARNESSING_GUIDE.md` (line 505, after "Generated FSM Structure" — not alongside the other evaluation phase descriptions).

## Expected Behavior

Wizard Step H3 includes a 5th multi-select option: "Stall detection (Recommended for prompt-based skills)". For H1 choices that produce `action_type: prompt`, this option is pre-selected by default. When selected, the generated YAML includes a `check_stall` state between `execute` and `check_concrete`. The `## Stall Detection` guide section appears within `## Evaluation Phases Explained` for co-located discovery alongside the other evaluation phase descriptions.

## Motivation

When a harness `execute` state uses `action_type: prompt` (or `slash_command`), the skill may silently no-op — returning "already done" or making no changes. This is a known failure mode documented in the guide. Without `check_stall`, such a no-op will:

1. Pass `check_semantic` — the evaluator has no evidence either way (see BUG-880), and defaults toward YES
2. Pass `check_invariants` — 0 diff lines < 50 is a passing condition
3. Advance to the next item, having done nothing

The result is a loop that consumes its entire `max_iterations` budget while making zero progress, with no diagnostic signal.

`check_stall` (`diff_stall` evaluator) is the correct guard: it detects when the git diff hasn't changed between iterations and skips the item. Currently it is:
- **Absent from wizard Step H3** — not listed at all; only described in a post-template prose block (`skills/create-loop/loop-types.md:814`)
- Documented in `AUTOMATIC_HARNESSING_GUIDE.md` in a `## Stall Detection` section at line 505 — after "Generated FSM Structure" and before "Using the Example Files" (low visibility, not alongside the other evaluation phases)

## Scope Boundaries

- **In scope**: Step H3 multi-select option addition; Variant A and Variant B YAML template updates; `## Stall Detection` section relocation within `## Evaluation Phases Explained`
- **Out of scope**: Other wizard steps (H1, H2, H4+); modifying existing loop YAML files; changing stall detection evaluation behavior; `check_stall` state implementation (already exists in canonical loops)

## Success Metrics

- Wizard Step H3 shows 5 evaluation phase options (currently 4)
- Stall detection is pre-selected when H1 choice produces `action_type: prompt`
- New harnesses generated with prompt-based skills include `check_stall` state in the evaluation chain
- `scripts/tests/test_create_loop.py` passes with no regressions

## Implementation Steps

1. **`skills/create-loop/loop-types.md:603-630` (Step H3)** — Add a 5th multi-select option for stall detection. All H1 choices (named skill + "Custom prompt") produce `action_type: prompt`, so this option should be pre-selected by default. Follow the existing pattern: prose detection instruction before the YAML block (as done for Tool-based gates at line 605) + `# Show only if` inline comment (line 615 pattern). Label: `"Stall detection (Recommended for prompt-based skills)"`.

2. **`skills/create-loop/loop-types.md:669-785`** — Update both Variant A (lines 669–719) and Variant B (lines 721–785) YAML templates to include a `check_stall` state when the stall detection phase is selected. Placement: between `execute` and `check_concrete`, exactly as in the canonical `loops/harness-multi-item.yaml:60-78` and `loops/harness-single-shot.yaml:26-49`. The `action` field should be `"echo 'checking stall'"` with `action_type: shell`. **Routing differs by variant** (confirmed against canonical files): Variant A (single-shot) uses `on_no: done` (no `advance` state); Variant B (multi-item) uses `on_no: advance` (skip stuck item, return to discover). Both use `on_yes: check_concrete` and `on_error: check_concrete`.

3. **`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:505-547`** — Move the `## Stall Detection` section (currently at line 505, ToC position 26 after "Generated FSM Structure") to appear within or immediately after the `## Evaluation Phases Explained` section (lines 97–264), so it is co-located with the other evaluation phase descriptions. **Also update the adjacent reference blocks at lines 243–261** that immediately precede the section break (`---`): (a) add `check_stall` to the "Full 5-phase ordering" list (`diff_stall` evaluator, placement: between `execute` and `check_concrete`), and (b) add a row to the "Decision guide" table — `check_stall (diff_stall) | The action is prompt-based and may no-op silently`.

4. Run existing wizard tests: `python -m pytest scripts/tests/test_create_loop.py -v`

## API/Interface

Wizard Step H3 UI change:

```
Which evaluation phases should be included? (multi-select)
  ☑ Tool-based gates (Recommended)   — Shell checks using test/lint/type commands
  ☑ Stall detection (Recommended for prompt-based skills) — Detects no-op iterations
  ☑ LLM-as-judge                     — Claude assesses output against skill description
  ☑ Diff invariants                  — git diff --stat line count < 50
  ○ Skill-based evaluation (Optional) — Invoke a skill to exercise and verify the feature
```

## Integration Map

### Files to Modify
- `skills/create-loop/loop-types.md` — Step H3 (lines 603–630): add stall detection as 5th multi-select option; Variant A template (lines 669–719) and Variant B template (lines 721–785): add `check_stall` state to evaluation chain when phase selected
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Move `## Stall Detection` section (lines 505–547) earlier into `## Evaluation Phases Explained` (lines 97–264)

### Reference Implementations (no changes needed)
- `loops/harness-multi-item.yaml:60-78` — canonical `execute (prompt) → check_stall → check_concrete` pattern to copy from
- `loops/harness-single-shot.yaml:26-49` — same pairing in single-shot variant

### Similar Patterns to Follow
- `skills/create-loop/loop-types.md:605-615` — prose detection instruction + `# Show only if` comment pattern for **config-conditional** phases (Tool-based gates: shown only if `test_cmd`/`lint_cmd`/`type_cmd` configured). **Note**: stall detection is NOT config-conditional — it is always shown. Use a different inline comment: `# Pre-selected by default: all H1 choices produce prompt-based execution` instead of `# Show only if`.
- `skills/create-loop/loop-types.md:64-72` — `(Recommended for X)` label suffix convention: implemented as `"Exit code (Recommended for {tool})"` where `{tool}` is matched from the tool pattern table. Stall detection should follow the same convention: `"Stall detection (Recommended for prompt-based skills)"`.

### Tests
- `scripts/tests/test_create_loop.py` — existing wizard tests; review for any Step H3 coverage
- `scripts/tests/test_fsm_evaluators.py` — tests for `evaluate_diff_stall()` (no changes expected)

### Documentation
- `loop-catalog.md` — already correctly shows `execute (prompt) → check_stall` in state tables; no changes needed

## Impact

- **Priority**: P3 - Prevents silent no-op loops in common harness configurations; high-value guardrail that doesn't require urgent remediation
- **Effort**: Small - Additive wizard option, two YAML template updates, one doc section move
- **Risk**: Low - No behavior changes to existing loops; YAML template changes only affect newly generated loops
- **Breaking Change**: No

## Labels

`enhancement`, `wizard`, `harness`, `stall-detection`

## Session Log
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80e15269-8cb1-400c-bfab-f3ed9eab7c73.jsonl`
- `/ll:refine-issue` - 2026-03-25T02:05:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2efc34df-45f4-4127-ac70-33a748d33768.jsonl`
- `/ll:format-issue` - 2026-03-25T01:57:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c4c4f281-2969-4dd6-85c0-25be3fb48a6e.jsonl`
- `/ll:confidence-check` - 2026-03-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/556f7371-7835-47ca-a34d-204ed0fd9aed.jsonl`
- `/ll:refine-issue` - 2026-03-25T00:45:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62553ed0-a6a8-48a9-af6f-3ab4cdac1a47.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3df6195-41d1-442e-a5ec-89e21c18fa59.jsonl`

## Status

**Open** | Created: 2026-03-24 | Priority: P3
