---
discovered_date: "2026-04-16"
discovered_by: capture-issue
source: ~/.claude/plans/review-this-open-source-cosmic-galaxy.md
decision_needed: false
confidence_score: 90
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1120: Harness-Optimize Loop (Score-Gated Hill-Climbing on Skills/Commands/CLAUDE.md)

## Summary

Add a new built-in loop `harness-optimize.yaml` that treats a configured target file set (e.g., an agent definition, a skill, a command prompt, or `CLAUDE.md`) as the mutable surface and iteratively improves it against a benchmark. Each iteration proposes an edit, runs a benchmark via `lib/benchmark.yaml` (FEAT-1119), accepts the change if score rises and reverts otherwise, and commits accepted mutations to a branch.

## Current Behavior

- little-loops has 45 FSM loops including `apo-textgrad`, `apo-beam`, `apo-opro`, `apo-contrastive`, `apo-feedback-refinement` — these optimize prompts.
- No loop mutates skills, commands, or `CLAUDE.md` and gates acceptance on a numeric benchmark score.
- No loop implements the "propose → score → accept-if-rise / revert-if-not" pattern over a declared mutable target set.

This is the gap autoagent fills with its `agent.py` + `program.md` core loop. little-loops has the pieces (apo mutation patterns, git integration, worktrees) but no loop that composes them into score-gated hill-climbing on harness artifacts.

## Expected Behavior

- `scripts/little_loops/loops/harness-optimize.yaml` runs the loop: read directive → propose mutation → run benchmark fragment → accept/revert → commit.
- Targets are declared via a `targets:` list (file paths or globs). Mutations only touch those files.
- Each iteration produces one git commit on a dedicated branch when accepted; rejected mutations leave no trace.
- Score trajectory persists to `.ll/runs/harness-optimize/<run-id>/trajectory.jsonl` so runs are resumable to best state, not last state.
- Reuses existing primitives: `apo-feedback-refinement.yaml` mutation pattern, `lib/benchmark.yaml` for scoring, worktree isolation for crash safety.

## Impact

Enables score-gated self-improvement on harness artifacts (skills, commands, CLAUDE.md) — the single capability that sets autoagent apart from little-loops today. Power users can run unattended overnight optimization runs that materially improve the prompts they ship, closing the gap between little-loops and dedicated APO tools.

## Labels

feature, loops, fsm, automation, optimization, apo

## Motivation

This feature would:
- Give little-loops the single capability that sets autoagent apart — score-gated self-improvement on harness artifacts. Without this, little-loops can optimize prompts but not skills/commands/CLAUDE.md.
- Reuse (not duplicate) the existing 45-loop library. Mutation proposal rides on `apo-feedback-refinement`; scoring rides on FEAT-1119; git revert rides on existing integration.
- Enable long-horizon overnight runs that materially improve the harness the user ships.

## Use Case

**Who**: Power user / maintainer improving a specific skill, agent, or CLAUDE.md against a held-out benchmark

**Context**: Has a task set (internal `.issues/completed/` reproduced as tasks, or external Harbor suite) and wants the harness tuned against it

**Goal**: Run `ll-loop run harness-optimize --targets skills/foo/SKILL.md --tasks-dir ./benchmarks/foo` and walk away

**Outcome**: A branch with N commits, each raising the score; a `trajectory.jsonl` showing accept/reject history; the best-scoring version at HEAD

## Proposed Solution

### New: `scripts/little_loops/loops/harness-optimize.yaml`

States:
- `load_directive` — read `.ll/program.md` if present (FEAT-1121) or CLI args
- `baseline_score` — run `lib/benchmark.yaml` on the pristine target set; store as baseline
- `propose` — invoke an LLM state (pattern from `apo-feedback-refinement`) to propose an edit to one target file, conditioned on the directive, current target contents, and last failure diagnosis
- `apply` — write the proposed edit (to worktree)
- `score` — run `lib/benchmark.yaml`
- `gate` — if `score > best_score`: commit, update `best_score`, write `trajectory.jsonl` entry (accepted); else: revert via `git restore`, write trajectory entry (rejected)
- `loop back to propose` until budget exhausted or score plateaus

### `scripts/little_loops/fsm/schema.py`

Likely no new schema — declare `targets:` via loop-level `context:` / parametrization. If follow-up shows a first-class `targets:` field is cleaner, add then.

### `scripts/little_loops/cli/loop.py`

Accept `--targets` and `--tasks-dir` pass-through for `harness-optimize` runs. If FEAT-1121 lands first, default these from `.ll/program.md`.

### Reuse

- Mutation proposal: copy the LLM-state shape from `loops/apo-feedback-refinement.yaml`
- Parallel proposal evaluation: reuse `parallel:` state (FEAT-1072 family) once available, for concurrent proposals
- Git integration: worktree-per-run, commit on accept, `git restore` on reject

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Score gate evaluator — use `convergence`, not bare `output_numeric`**

The `gate` state should use the `convergence` evaluator with `direction: maximize` (pattern from `agent-eval-improve.yaml:64-77`). This handles stall detection natively without requiring a manually-tracked `best_score` context variable. Verdicts: `target` (above threshold), `progress` (improving), `stall` (not improving → revert path).

```yaml
gate:
  evaluate:
    type: convergence
    source: "${captured.benchmark_score.output}"
    direction: maximize
    stall_window: 3
  on_target: commit_and_log
  on_progress: commit_and_log
  on_stall: revert_and_log
```

**`lib/benchmark.yaml` fragment contract (FEAT-1119 must implement)**

The fragment must `capture: benchmark_score` so the `gate` state reads `${captured.benchmark_score.output}`. Minimal viable shape:

```yaml
fragments:
  run_benchmark:
    action: "${context.scorer} ${context.tasks_dir}"
    action_type: shell
    capture: benchmark_score
    evaluate:
      type: exit_code
```

The `harness-optimize` loop declares `import: [lib/benchmark.yaml]` and uses `fragment: run_benchmark` in its `score` state.

**Trajectory path correction**

The spec says `.ll/runs/harness-optimize/<run-id>/trajectory.jsonl`. The actual FSM persistence layer writes to `.loops/.running/` (runtime) and `.loops/.history/<run-id>-harness-optimize/` (archived) — NOT `.ll/runs/`. Two implementation options for the custom trajectory:

1. **Use `.loops/tmp/`** (consistent with `dead-code-cleanup.yaml`, `dataset-curation.yaml`): Have the `commit_and_log` and `revert_and_log` states append to `.loops/tmp/harness-optimize-trajectory.jsonl` via a prompt action (like `dataset-curation.yaml:103`)
2. **Honor the spec path** `.ll/runs/harness-optimize/<run-id>/trajectory.jsonl`: Requires the `baseline_score` state to `mkdir -p` the directory (shell action) and subsequent states to append — needs `${loop.started_at}` for the run-id

Option 1 is lowest friction and consistent with existing patterns; Option 2 matches the spec exactly.

**`captured` namespace access**

After any state with `capture: key`, downstream states read via `${captured.key.output}`, `${captured.key.exit_code}`, `${captured.key.duration_ms}` — from `interpolation.py:80-81`. The `benchmark_score` capture output must be a bare float on stdout for the `convergence` evaluator to parse it.

**Revert mechanism**

Existing `incremental-refactor.yaml:27-59` uses `git checkout -- .`. For `harness-optimize`, scope the revert to the declared targets to avoid clobbering unrelated changes:

```yaml
revert_and_log:
  action: "git restore ${context.targets}"
  action_type: shell
  next: write_trajectory
```

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Verify FEAT-1119 is complete** — confirm `scripts/little_loops/loops/lib/benchmark.yaml` exists and exposes `fragment: run_benchmark` with `capture: benchmark_score`; if not, implement its fragment contract first (see Proposed Solution → Codebase Research Findings above)

2. **Create `scripts/little_loops/loops/harness-optimize.yaml`** with states following the shape in `apo-feedback-refinement.yaml`:
   - Declare `import: [lib/common.yaml, lib/benchmark.yaml]`
   - `load_directive` → reads `${context.targets}` and optional `.ll/program.md`
   - `baseline_score` → uses `fragment: run_benchmark`; stores initial score via `capture: baseline`
   - `propose` → LLM prompt state (copy shape from `apo-feedback-refinement.yaml:generate_candidate`), conditioned on `${context.targets}` contents and `${captured.eval_result.output}` from last rejection
   - `apply` → prompt state writing the proposed edit to `${context.targets}`
   - `score` → uses `fragment: run_benchmark`
   - `gate` → uses `convergence` evaluator with `direction: maximize` on `${captured.benchmark_score.output}` (see `agent-eval-improve.yaml:64-77`)
   - `commit_and_log` → shell: `git add ${context.targets} && git commit -m "harness-optimize: iter ${state.iteration}, score ${captured.benchmark_score.output}"`; then append trajectory JSONL
   - `revert_and_log` → shell: `git restore ${context.targets}`; then append trajectory JSONL
   - Loop `gate` back to `propose` until `max_iterations` or plateau budget

3. **Trajectory JSONL**: In `commit_and_log` and `revert_and_log`, instruct LLM (or shell) to append one JSON line to `.loops/tmp/harness-optimize-trajectory.jsonl` with fields: `iter`, `proposed_file`, `score`, `accepted`, `commit_sha` (model after `dataset-curation.yaml:103`)

4. **Update `scripts/tests/test_builtin_loops.py`**: Add `"harness-optimize"` to the `expected` set in `test_expected_loops_exist()` (~line 60)

5. **Add integration test** in `scripts/tests/test_harness_optimize.py`: use `monkeypatch.chdir(tmp_path)` + a mock scorer script that increments a counter file; assert score monotonically non-decreases across accepted iterations; assert rejected mutations leave `git status` clean (model after `scripts/tests/test_ll_loop_integration.py:90-113`)

6. **Run**: `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_harness_optimize.py -v`

7. **Docs**: Update `docs/reference/loops.md` and `scripts/little_loops/loops/README.md`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `README.md:91` — change `42 FSM loops` to `43 FSM loops`
9. Update `CONTRIBUTING.md:124` — correct directory loop count (already stale at 40; update to actual post-merge count)
10. Update `docs/guides/LOOPS_GUIDE.md:652-661` — add `harness-optimize` row to the "Harness Examples" reference table
11. Update `docs/guides/LOOPS_GUIDE.md:2045` — change "Two libraries" to "Three libraries"; add `lib/benchmark.yaml` to the built-in libraries table (coordinate with FEAT-1119)
12. Update `scripts/little_loops/loops/README.md:115-120` — add `lib/benchmark.yaml` row to the "Fragment Libraries" table (coordinate with FEAT-1119)
13. In `scripts/tests/test_harness_optimize.py` — add gap tests: (a) `trajectory.jsonl` JSONL append assertion; (b) `git restore` called with scoped `context.targets` on reject (not bare `git checkout -- .`)

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM executor, worktree isolation |
| `docs/reference/API.md` | Loop APIs, evaluator registration |
| `loops/apo-feedback-refinement.yaml` | Mutation proposal state pattern to reuse |

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Create
- `scripts/little_loops/loops/harness-optimize.yaml` — new built-in loop (primary deliverable)
- `scripts/little_loops/loops/lib/benchmark.yaml` — benchmark fragment (FEAT-1119 deliverable; this loop imports it via `import: [lib/benchmark.yaml]`)

### Files to Modify
- `scripts/tests/test_builtin_loops.py` — add `"harness-optimize"` to `test_expected_loops_exist()` expected set (line ~60)
- `docs/reference/loops.md` — CREATE (does not exist yet); add loop entry per acceptance criteria
- `scripts/little_loops/loops/README.md` — add entry to built-in loops catalog

_Wiring pass added by `/ll:wire-issue`:_
- `README.md:91` — `42 FSM loops` → `43 FSM loops` (count claim goes stale on loop addition) [Agent 2 finding]
- `CONTRIBUTING.md:124` — `40 YAML files` → `43 YAML files` (directory listing count, already stale) [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:652-661` — "Harness Examples" table missing `harness-optimize` row [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:2045` — "Two libraries" → "Three libraries"; add `lib/benchmark.yaml` row (when FEAT-1119 lands) [Agent 2 finding]
- `scripts/little_loops/loops/README.md:115-120` — "Fragment Libraries" table needs `lib/benchmark.yaml` row (when FEAT-1119 lands) [Agent 2 finding]

### No New CLI Code Needed
- `--targets` and `--tasks-dir` do **not** require new CLI flags. Existing `--context KEY=VALUE` at `scripts/little_loops/cli/loop/__init__.py:147` injects them as `context.targets` and `context.tasks_dir` via `scripts/little_loops/cli/loop/run.py:77-81`. Invocation: `ll-loop run harness-optimize --context targets=skills/foo/SKILL.md --context tasks_dir=./benchmarks/foo`

### Fragment Resolution
- `scripts/little_loops/fsm/fragments.py:38` resolves `import: [lib/benchmark.yaml]` relative to the loop file's directory first, then the built-in loops directory — no extra path config needed

### Similar Patterns (Reference Implementations)
- `scripts/little_loops/loops/apo-feedback-refinement.yaml` — mutation proposal state shape: `generate_candidate → evaluate_candidate → route_convergence → apply_candidate / refine`
- `scripts/little_loops/loops/incremental-refactor.yaml:27-59` — `verify → commit / revert` pattern; revert via `git checkout -- .`
- `scripts/little_loops/loops/agent-eval-improve.yaml:64-77` — `convergence` evaluator with `direction: maximize` for score-gated routing; reads `${captured.scores.output}`
- `scripts/little_loops/loops/apo-opro.yaml` — score history accumulation: overwrite same `capture:` key each iteration to accumulate history
- `scripts/little_loops/loops/lib/common.yaml` — `shell_exit` and `numeric_gate` fragments; import via `import: [lib/common.yaml]`
- `scripts/little_loops/loops/dataset-curation.yaml:103` — JSONL trajectory append pattern: prompt LLM to `Append ... to <path>/trajectory.jsonl with fields: iter, score, accepted, timestamp`

### Tests
- `scripts/tests/test_builtin_loops.py` — update `test_expected_loops_exist()` to include `"harness-optimize"`
- New: `scripts/tests/test_harness_optimize.py` — integration test with 3-task mock scorer fixture; model after `scripts/tests/test_ll_loop_integration.py:90-113`
- Fixture: `scripts/tests/fixtures/fsm/` — add a minimal mock scorer YAML for the harness-optimize integration test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:36-44` — `test_all_validate_as_valid_fsm` picks up `harness-optimize.yaml` automatically; any YAML structural defect breaks this test first [Agent 3 finding]
- `scripts/tests/test_harness_optimize.py` — structural tests: follow `test_outer_loop_eval.py:1-154` pattern (`TestHarnessOptimizeFile` + `TestHarnessOptimizeStates` classes, `REQUIRED_STATES` set, `load_and_validate` + `validate_fsm` calls); add assertions for `trajectory.jsonl` JSONL write path and `git restore` called with scoped targets — both are gaps with no existing test infrastructure [Agent 3 finding]
- `scripts/tests/test_fsm_fragments.py:522-662` — model for `lib/benchmark.yaml` fragment description test (follow `TestCommonYamlNewFragments` pattern to verify `run_benchmark` fragment has `description` field) [Agent 3 finding]

### Documentation
- `docs/reference/loops.md` — CREATE (does not exist yet); document the loop per acceptance criteria
- `scripts/little_loops/loops/README.md` — add entry to built-in loops catalog

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:652-661` — "Harness Examples" reference table; add row for `harness-optimize` [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:2045` — "Built-in Libraries" section; update "Two libraries" claim and add `lib/benchmark.yaml` row alongside `common.yaml` and `cli.yaml` (coordinate with FEAT-1119 landing) [Agent 2 finding]
- `README.md:91` — hard-coded loop count `42 FSM loops` will be stale after this lands [Agent 2 finding]
- `CONTRIBUTING.md:124` — directory listing `40 YAML files` is already stale; update to actual count [Agent 2 finding]

## Acceptance Criteria

- [ ] `loops/harness-optimize.yaml` parses, validates, and lists in `ll-loop list`
- [ ] Integration test: run against a 3-task fixture; assert score monotonically non-decreases across accepted iterations
- [ ] Rejected mutation leaves working tree clean (`git status` empty after revert)
- [ ] `trajectory.jsonl` written with one row per iteration (fields: iter, proposed_file, score, accepted, commit_sha)
- [ ] Resume: killing mid-run and re-running resumes at best-score HEAD, not last-attempted HEAD
- [ ] Docs: `docs/reference/loops.md` documents the loop; `/ll:help` includes it
- [ ] No regression: existing `apo-*` loops still pass

## Blocked By

- FEAT-1119: benchmark adapter fragment — the `score` state imports `lib/benchmark.yaml` which FEAT-1119 must deliver

## Dependencies

Blocked by: FEAT-1119 (benchmark adapter fragment) — this loop's `score` state depends on it.

Related: FEAT-1121 (program.md convention) — nice-to-have entry point; not a hard blocker.
Related: ENH-1122 (frozen-boundary markers) — guardrail that becomes useful once this loop exists.

## Session Log
- `/ll:ready-issue` - 2026-04-21T23:26:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c3c7599-51fd-4437-8dcc-1843715b82b7.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca7bea0a-41dc-42cd-8f16-e1a5bb35f04b.jsonl`
- `/ll:wire-issue` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:refine-issue` - 2026-04-21T23:15:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17a43e35-c912-41c4-b189-d47f33dc1242.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-19T01:16:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c7ed14d-9621-459d-9f93-384968b2e6f6.jsonl`
- `/ll:capture-issue` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2fb1a4ee-5512-43ed-b858-2a21a4738fb8.jsonl`

---

## Status

Open

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Default mutable-boundary policy is **mutable-all** — files without `<!-- ll:mutable -->` / `<!-- ll:frozen -->` markers (per ENH-1122) are fully mutable by this loop. The frozen-all safety mode is opt-in via loop config. This preserves current behavior and keeps harness-optimize low-friction while ENH-1122's boundary markers let authors explicitly protect regions.
