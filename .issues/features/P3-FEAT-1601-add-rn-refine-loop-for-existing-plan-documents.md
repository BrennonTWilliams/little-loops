---
id: FEAT-1601
type: FEAT
priority: P3
status: open
discovered_date: 2026-05-17
discovered_by: capture-issue
captured_at: '2026-05-17T22:56:35Z'
relates_to:
  - FEAT-1534
  - FEAT-1536
---

# FEAT-1601: Add rn-refine loop for refining existing plan documents

## Summary

Create a new `rn-refine` FSM loop that accepts a path to an existing plan `.md` file and applies the same Recursive-N rubric-scoring refinement cycle used by `rn-plan` — but instead of starting from a blank slate, it preserves and improves the existing content. Fills the gap for users who have a plan already drafted (from a prior `rn-plan` run, a `thoughts/` document, or a manual draft) and want iterative rubric-driven improvement without discarding work.

## Motivation

`rn-plan` always starts from scratch. Users regularly have existing plan files and need to apply the same rubric refinement process to them. Without `rn-refine`, they must either copy content manually into a new run or forgo rubric-driven improvement entirely.

## Use Case

User has `thoughts/my-feature-plan.md` from an earlier session. They run:
```bash
ll-loop run rn-refine "thoughts/my-feature-plan.md"
```
The loop reads the existing plan, scores its current state across all 9 rubric dimensions (reflecting actual quality, not all-LOW), then iteratively researches and rewrites it until all dimensions reach VERY-HIGH.

## Implementation Plan

### 1. New loop file: `scripts/little_loops/loops/rn-refine.yaml`

**Top-level config:**
```yaml
name: rn-refine
category: planning
input_key: plan_file
description: |
  Recursive-N refinement loop for an existing plan document. Accepts a path to
  a plan .md file, calibrates a 9-dimension scoring rubric to the plan's current
  state, then iteratively researches and refines until all dimensions reach
  VERY-HIGH or max_iterations is exhausted.
  Run as: ll-loop run rn-refine "path/to/plan.md"
initial: init
max_iterations: 50
timeout: 7200

context:
  plan_file: ""
  output_dir: ".loops/plans"
```

**State: `init`** (shell)
- Validate `${context.plan_file}` exists; `exit 1` → `on_error: failed`
- Derive slug from filename stem: `basename "${context.plan_file}" .md | tr ... slug`
- `mkdir -p ${context.output_dir}/$SLUG`
- `cp "${context.plan_file}" "$DIR/plan.md"` — preserves existing content
- Create empty `plan-rubric.md` and `research.md`
- `echo "$(pwd)/$DIR"` → captured as `run_dir`
- `next: assess_existing`

**State: `assess_existing`** (prompt) — replaces `generate_rubric`
- Reads the copied `plan.md`
- Infers task/goal from plan content (no user-supplied task string)
- Writes `plan-rubric.md` with 9 dimensions scored at their **actual current level** (not all LOW)
- Sets aggregate score and verdict
- `next: classify_research`

**Remaining states** (`classify_research`, `route_files`, `route_web`, `research_files`, `research_web`, `synthesize`, `score`, `done`, `failed`): copied verbatim from `rn-plan.yaml` — they operate on `${captured.run_dir.output}/plan.md` regardless of origin.

### 2. README update: `scripts/little_loops/loops/README.md`

Add a new `## Planning` section (before APO):

| Loop | Description | Primary Inputs |
|---|---|---|
| `rn-plan` | Recursive-N planning loop — builds plan from scratch | `task` |
| `rn-refine` | Recursive-N refinement loop — improves existing plan | `plan_file` (path to `.md`) |

Move `rn-plan-apo` out of APO into this Planning section (cosmetic README-only change).

## API / Interface Changes

- New loop discoverable via `ll-loop list` (auto-discovered from filename)
- New `input_key: plan_file` — populated from CLI positional arg
- No Python changes; pure YAML + README

## Verification

```bash
# 1. Confirm loop is discoverable
ll-loop list | grep rn-refine

# 2. Smoke test against an existing plan file
ll-loop run rn-refine "thoughts/some-existing-plan.md" --max-iterations 2

# 3. Verify init correctly copies the source file
ls .loops/plans/<slug>/plan.md

# 4. Verify assess_existing produces non-uniform rubric scores
cat .loops/plans/<slug>/plan-rubric.md

# 5. Confirm rn-plan still works (no regressions)
ll-loop run rn-plan "test task" --max-iterations 1
```

## Session Log
- `/ll:capture-issue` - 2026-05-17T22:56:35Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a4eb0d1-78ff-4d2e-bb80-81e2d70e2260.jsonl`
