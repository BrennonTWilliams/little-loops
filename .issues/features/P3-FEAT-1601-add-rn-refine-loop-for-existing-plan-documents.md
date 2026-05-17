---
id: FEAT-1601
type: FEAT
priority: P3
status: done
discovered_date: 2026-05-17
discovered_by: capture-issue
captured_at: '2026-05-17T22:56:35Z'
completed_at: '2026-05-17T23:28:49Z'
relates_to:
- FEAT-1534
- FEAT-1536
confidence_score: 100
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1601: Add rn-refine loop for refining existing plan documents

## Summary

Create a new `rn-refine` FSM loop that accepts a path to an existing plan `.md` file and applies the same Recursive-N rubric-scoring refinement cycle used by `rn-plan` — but instead of starting from a blank slate, it preserves and improves the existing content. Fills the gap for users who have a plan already drafted (from a prior `rn-plan` run, a `thoughts/` document, or a manual draft) and want iterative rubric-driven improvement without discarding work.

## Current Behavior

`rn-plan` always starts from scratch, building a plan from a blank slate. There is no loop that accepts an existing plan document and applies rubric-driven refinement to it. Users who have existing plan files must either copy content manually into a new `rn-plan` run or forgo rubric-driven improvement entirely.

## Expected Behavior

A new `rn-refine` FSM loop accepts a path to an existing plan `.md` file, reads its current content, calibrates the 9-dimension scoring rubric to the plan's actual current state (not all-LOW), and then iteratively researches and refines the plan until all dimensions reach VERY-HIGH or `max_iterations` is exhausted.

## Motivation

`rn-plan` always starts from scratch. Users regularly have existing plan files and need to apply the same rubric refinement process to them. Without `rn-refine`, they must either copy content manually into a new run or forgo rubric-driven improvement entirely.

## Use Case

User has `thoughts/my-feature-plan.md` from an earlier session. They run:
```bash
ll-loop run rn-refine "thoughts/my-feature-plan.md"
```
The loop reads the existing plan, scores its current state across all 9 rubric dimensions (reflecting actual quality, not all-LOW), then iteratively researches and rewrites it until all dimensions reach VERY-HIGH.

## Acceptance Criteria

- [ ] `ll-loop list` shows `rn-refine` as a discoverable loop
- [ ] `ll-loop run rn-refine "path/to/plan.md"` reads the existing file and begins refinement without discarding content
- [ ] The `init` state copies the source file to `.loops/plans/<slug>/plan.md` (not a blank file)
- [ ] `assess_existing` produces rubric scores calibrated to the plan's actual current quality (not all-LOW)
- [ ] All states from `classify_research` onward behave identically to `rn-plan` counterparts
- [ ] `rn-plan` continues to function correctly with no regressions

## Implementation Steps

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact `init` state shell body** (slug from filename stem, file existence check, `cp` instead of blank init):

```yaml
init:
  action_type: shell
  action: |
    if [ ! -f "${context.plan_file}" ]; then
      echo "ERROR: Plan file not found: ${context.plan_file}"
      exit 1
    fi
    SLUG=$(basename "${context.plan_file}" .md | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\+/-/g; s/^-//; s/-$//')
    SLUG="${SLUG:-rn-refine-run}"
    DIR="${context.output_dir}/$SLUG"
    mkdir -p "$DIR"
    cp "${context.plan_file}" "$DIR/plan.md"
    : > "$DIR/plan-rubric.md"
    : > "$DIR/research.md"
    echo "$(pwd)/$DIR"
  capture: run_dir
  on_error: failed
  next: assess_existing
```

**9 rubric dimensions** (`assess_existing` must score these at their actual current level, not all LOW):
1. `breadth` — coverage of concerns, stakeholders, edge cases
2. `depth` — granularity and actionability of sub-steps
3. `complexity` — calibrated to task; neither over- nor under-engineered
4. `clarity` — unambiguous, specific language; no vague directives like "handle X"
5. `consistency` — non-contradictory steps; no concern resolved twice with conflicting advice
6. `logic_strategy` — sound ordering and approach for the specific task
7. `feasibility` — achievable given realistic constraints (time, resources, skills)
8. `testability` — clear success criteria and verification steps per phase
9. `risk_mitigation` — key risks identified with concrete contingencies

Scale: LOW (1) / MEDIUM (2) / HIGH (3) / VERY-HIGH (4). Convergence sentinel: `ALL_VERY_HIGH` (all 9 at level 4).

**`route_files` / `route_web` state structure**: pure router states with no `action` field — they use `evaluate: { source: "${captured.classification.output}" }` to dispatch on `classify_research`'s captured output without re-invoking the LLM. Both use `on_error: synthesize` (not `on_error: failed`), per `rn-plan.yaml` convention.

**`failed` terminal state**: bare `terminal: true` with no action (silent failure terminal). `done` is `terminal: true` with a prompt action that reports final rubric scores to the user before terminating.

**File initialization convention**: use `: > "$DIR/file.md"` (not `touch`), per `rn-plan.yaml` `init` state.

**Testing pattern** — for a new `scripts/tests/test_rn_refine.py`, follow `scripts/tests/test_loops_recursive_refine.py`: `_bash(script, tmp_path)` helper, class-per-state grouping, `tmp_path` as cwd. Key `init` test cases: slug derivation from filename stem, file-not-found exits with non-zero returncode, `cp` deposits source content into `$DIR/plan.md`.

## Integration Map

### Files to Create
- `scripts/little_loops/loops/rn-refine.yaml` — new FSM loop YAML; auto-discovered by `ll-loop list` and `ll-loop run` (no registration step required)

### Files to Modify
- `scripts/little_loops/loops/README.md` — add `## Planning` section with `rn-plan` and `rn-refine` rows (no Planning section exists yet; `rn-plan-apo` currently lives in the APO section)

### Reference Files (read-only; copy states verbatim)
- `scripts/little_loops/loops/rn-plan.yaml` — source of `classify_research`, `route_files`, `route_web`, `research_files`, `research_web`, `synthesize`, `score`, `done`, `failed` states

### Tests (model after; no modification required)
- `scripts/tests/test_loops_recursive_refine.py` — `_bash()` helper and class-per-state pattern; model `test_rn_refine.py` after this
- `scripts/tests/test_builtin_loops.py` — auto-discovers `rn-refine` by filename; no changes needed

### CLI / FSM Engine (no changes required)
- `scripts/little_loops/cli/loop/run.py:cmd_run` (~line 126) — injects positional arg into `fsm.context["plan_file"]` via `input_key: plan_file` through the `JSONDecodeError` branch
- `scripts/little_loops/fsm/schema.py:FSMLoop` (~line 809) — `input_key` field is fully supported; `plan_file` is a valid value
- `scripts/little_loops/fsm/executor.py` — `captured["run_dir"]["output"]` stores the absolute path; all states reference it as `${captured.run_dir.output}/filename`

## API/Interface

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

## Impact

- **Priority**: P3 - Enhancement to planning workflow; useful but not blocking current work
- **Effort**: Small - New YAML loop file + README section; no Python changes required
- **Risk**: Low - Purely additive (new file only); no modifications to existing `rn-plan` states
- **Breaking Change**: No

## Labels

`planning`, `loops`, `automation`

## Status

**Open** | Created: 2026-05-17 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-17T23:25:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b78a3a28-8255-41e0-b9aa-0dc05d78fc59.jsonl`
- `/ll:confidence-check` - 2026-05-17T23:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5892ebd5-b279-4ddf-bf1c-6f6c554954f4.jsonl`
- `/ll:refine-issue` - 2026-05-17T23:09:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/418811a5-5224-4509-94ed-1f9fefd1bb5a.jsonl`
- `/ll:format-issue` - 2026-05-17T23:01:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/97ee7205-a63b-47df-a039-f8f11773ce33.jsonl`
- `/ll:capture-issue` - 2026-05-17T22:56:35Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a4eb0d1-78ff-4d2e-bb80-81e2d70e2260.jsonl`
