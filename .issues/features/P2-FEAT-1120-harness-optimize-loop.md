---
discovered_date: "2026-04-16"
discovered_by: capture-issue
source: ~/.claude/plans/review-this-open-source-cosmic-galaxy.md
decision_needed: false
confidence_score: 99
outcome_confidence: 75
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 25
completed_at: 2026-04-24T20:46:21Z
status: done
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

**`lib/benchmark.yaml` fragment contract (verified — FEAT-1244 completed)**

`lib/benchmark.yaml` now exists. The actual fragment shape (from codebase):

```yaml
fragments:
  run_benchmark:
    description: "..."
    action_type: shell
    evaluate:
      type: harbor_scorer
```

`harbor_scorer` routes verdicts: `yes` (exit 0 + float stdout), `no` (exit non-zero), `error` (exit 0 + non-float stdout). The fragment does **not** have a built-in `action:` or `capture:`. The caller's `score` state must supply all three:

```yaml
score:
  fragment: run_benchmark
  action: "${context.scorer} ${context.tasks_dir}"
  capture: benchmark_score
  on_yes: gate
  on_no: revert_and_log
  on_error: revert_and_log
```

`${captured.benchmark_score.output}` then holds the bare float string for the `gate` convergence evaluator. The `harness-optimize` loop declares `import: [lib/benchmark.yaml]` and uses this pattern in its `score` state.

**Trajectory path correction**

The spec says `.ll/runs/harness-optimize/<run-id>/trajectory.jsonl`. The actual FSM persistence layer writes to `.loops/.running/` (runtime) and `.loops/.history/<run-id>-harness-optimize/` (archived) — NOT `.ll/runs/`.

**Decision**: Use `.loops/tmp/harness-optimize-trajectory.jsonl` — consistent with `dead-code-cleanup.yaml` and `dataset-curation.yaml`, lowest friction, no `mkdir -p` required. Have `commit_and_log` and `revert_and_log` append to this path via a prompt action (like `dataset-curation.yaml:103`).

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

**Corrections from codebase validation (Pass 3)**

_Added manually — resolving 11 gaps found in design review:_

**Decision: stop-on-first-stall, two trajectory states, single-file-per-iteration.**

**1. `apply` state shape (was: completely unspecified)**

`apply` is a prompt state that instructs the LLM to write the captured candidate to the single file it proposed:

```yaml
apply:
  action_type: prompt
  timeout: 120
  action: |
    Write the following revised contents to the file you proposed editing.
    Replace the entire file contents exactly — no preamble, no explanation.

    ${captured.candidate.output}

    Confirm the file has been updated.
  next: score
```

**2. `propose` state — single-file-per-iteration (was: implicitly multi-target)**

Add "Pick ONE file" instruction so `apply` always has a single unambiguous target:

```yaml
propose:
  action_type: prompt
  timeout: 300
  action: |
    Target files available: ${context.targets}
    Baseline score: ${captured.baseline.output}
    Last benchmark output: ${captured.benchmark_score.output}

    Pick ONE file from the target list to improve this iteration.
    Read it, then propose ONE targeted edit to raise the benchmark score.
    Output the complete revised file contents only —
    no preamble, no explanation, no markdown fences.
  capture: candidate
  on_blocked: done
  next: apply
```

**3. `revert_and_log` routing — stop on first stall**

`revert_and_log` transitions to `write_trajectory_rejected`, which terminates. It does NOT loop back to `propose`. The loop's retry budget is `max_iterations`, not stall retries:

```
gate: stall/error → revert_and_log → write_trajectory_rejected → done
gate: target/progress → commit_and_log → write_trajectory_accepted → capture_prev → propose
```

**4. Two `write_trajectory` states (was: single state with no accepted/rejected distinction)**

```yaml
write_trajectory_accepted:
  action_type: shell
  action: |
    echo '{"iter":${state.iteration},"score":${captured.benchmark_score.output},"accepted":true,"commit_sha":"${captured.last_commit.output}"}' \
      >> .loops/tmp/harness-optimize-trajectory.jsonl
  next: capture_prev

write_trajectory_rejected:
  action_type: shell
  action: |
    echo '{"iter":${state.iteration},"score":${captured.benchmark_score.output},"accepted":false,"commit_sha":""}' \
      >> .loops/tmp/harness-optimize-trajectory.jsonl
  next: done
```

`${state.iteration}` is a valid interpolation variable (confirmed: used in `svg-textgrad.yaml:153`).

**5. Full `context:` defaults block (was: only `target_score` specified)**

```yaml
context:
  targets: ""          # required — space-separated file paths, e.g. "skills/foo/SKILL.md"
  tasks_dir: ""        # required — path to Harbor task directory
  scorer: ""           # required — scorer command, e.g. "./scripts/score.sh"
  target_score: 1.0    # early-stop threshold; 1.0 means "never early-stop"
  max_iterations: 30   # hard budget ceiling
```

`targets`, `tasks_dir`, and `scorer` have no sensible defaults and must be supplied via `--context`.

**6. `baseline_score` routing (was: unspecified)**

```yaml
baseline_score:
  fragment: run_benchmark
  action: "${context.scorer} ${context.tasks_dir}"
  capture: baseline
  on_yes: init_prev
  on_no: done
  on_error: done
```

**7. `init_prev` state — required bootstrap (was: missing)**

Without this state, the first `gate` call has `previous=None`, causing the `convergence` evaluator to always return `progress` on the first iteration — committing a score-worsening mutation. `init_prev` seeds `prev_score` with the baseline so the first gate has a correct reference:

```yaml
init_prev:
  action_type: shell
  action: "echo '${captured.baseline.output}' | tail -1 | tr -d '[:space:]'"
  capture: prev_score
  next: propose
```

Full startup sequence: `load_directive → baseline_score → init_prev → propose → …`

Note: `captured.prev_score` being unset on the first gate call is safe — the executor catches `InterpolationError`/`ValueError` and falls back to `previous=None` — but `init_prev` is still needed to prevent the first-iteration always-progress bug.

**8. `tolerance` on gate evaluator (was: missing)**

Add `tolerance: 0.02` to prevent floating-point precision artifacts from triggering stall when score genuinely improved:

```yaml
gate:
  action_type: shell
  action: |
    echo "${captured.benchmark_score.output}" | tail -1 | tr -d '[:space:]'
  evaluate:
    type: convergence
    direction: maximize
    target: "${context.target_score}"
    previous: "${captured.prev_score.output}"
    tolerance: 0.02
  route:
    target: commit_and_log
    progress: commit_and_log
    stall: revert_and_log
    error: revert_and_log
```

**9. Implementation Step 1 correction (was: references undefined "FEAT-1119")**

Step 1 should read: "Both blockers are already resolved — FEAT-1244 (`lib/benchmark.yaml`) and FEAT-1245 (fragment wiring) are COMPLETED. No prerequisite work needed; proceed directly to Step 2."

**10. Corrected state graph**

```
load_directive
  → baseline_score
    → init_prev
      → propose
        → apply
          → score
            on_yes: gate
            on_no:  revert_and_log → write_trajectory_rejected → done
            on_error: revert_and_log → write_trajectory_rejected → done
            gate:
              target/progress: commit_and_log → write_trajectory_accepted → capture_prev → propose
              stall/error:     revert_and_log → write_trajectory_rejected → done
```

**Corrections from codebase validation (Pass 2)**

_Added by `/ll:refine-issue` — correcting three errors in the prior `gate` YAML snippet:_

1. `stall_window: 3` — not a field in `EvaluateConfig` (`schema.py:56-80`); would be silently ignored
2. `source:` — not a valid evaluator field; score must be extracted via the state's shell `action:`
3. `on_target/on_progress/on_stall` — invalid routing keys; must use a `route:` table

Correct `gate` shape (stop on first stall; `route.stall → revert_and_log`):

```yaml
gate:
  action_type: shell
  action: |
    echo "${captured.benchmark_score.output}" | tail -1 | tr -d '[:space:]'
  evaluate:
    type: convergence
    direction: maximize
    target: "${context.target_score}"
    previous: "${captured.prev_score.output}"
  route:
    target: commit_and_log
    progress: commit_and_log
    stall: revert_and_log
    error: revert_and_log
```

`target:` is required — `evaluators.py:832` raises `ValueError` without it. Default `target_score: 1.0` in loop `context:` so the run never stops early on "target reached" unless the user sets a lower threshold. The configurable form (`"${context.target_score}"`) lets power users supply an early-stop threshold.

**`previous:` wiring requires a `capture_prev` state**

Without an explicit `previous:` field, the `convergence` evaluator receives `previous=None` on every iteration and always emits `progress` (never `stall`). A dedicated shell state captures the current score as `prev_score` at the end of each cycle, so the next cycle's `gate` has the prior value:

```yaml
capture_prev:
  action_type: shell
  action: "echo '${captured.benchmark_score.output}' | tail -1 | tr -d '[:space:]'"
  capture: prev_score
  next: propose
```

Loop graph with `capture_prev`:
```
propose → apply → score → gate → commit_and_log → capture_prev → propose
                               → revert_and_log → capture_prev → propose
                               → (done on first stall via revert_and_log → capture_prev → propose → stall again → done)
```

Wait — with "stop on first stall" the `gate` routes `stall → revert_and_log`, then `revert_and_log` must route to a terminal `done` (or back to `propose` if a separate stall counter is used). The simplest terminal: `revert_and_log` writes the trajectory entry then transitions to `done`.

**Resumability: `load_directive` checkpoint pattern**

The FSM framework restores `current_state` on resume, not best state (`persistence.py:504-558`). `LoopState` has no `best_score` field. To satisfy the "resume at best-score HEAD" acceptance criterion, `load_directive` must read the trajectory on startup and check out the best-scoring accepted commit:

```yaml
load_directive:
  action_type: shell
  action: |
    TRAJ=.loops/tmp/harness-optimize-trajectory.jsonl
    if [ -f "$TRAJ" ]; then
      BEST=$(jq -r 'select(.accepted==true) | .commit_sha' "$TRAJ" | tail -1)
      [ -n "$BEST" ] && git checkout "$BEST" -- ${context.targets}
    fi
  capture: directive
  next: baseline_score
```

The `commit_and_log` state must record the commit SHA. After `git commit`, capture it:
```yaml
commit_and_log:
  action_type: shell
  action: |
    git add ${context.targets}
    git commit -m "harness-optimize: iter ${state.iteration}, score ${captured.benchmark_score.output}"
    git rev-parse HEAD
  capture: last_commit
  next: write_trajectory
```
Then `write_trajectory` includes `${captured.last_commit.output}` as `commit_sha` in the JSONL line.

**`propose` state — concrete prompt template (single state with failure context)**

Conditions on target contents, baseline, and last benchmark output (failure diagnosis inline):

```yaml
propose:
  action_type: prompt
  timeout: 300
  action: |
    Read the target file(s): ${context.targets}
    Baseline score: ${captured.baseline.output}
    Last benchmark output: ${captured.benchmark_score.output}

    Propose ONE targeted edit to improve the benchmark score.
    Output the complete revised file contents only —
    no preamble, no explanation, no markdown fences.
  capture: candidate
  on_blocked: done
  next: apply
```

**Multi-target invocation**

Pass space-separated paths in a single `--context` value; shell word-splitting handles expansion in `action:` strings:
```
ll-loop run harness-optimize \
  --context "targets=skills/foo/SKILL.md skills/bar/SKILL.md" \
  --context tasks_dir=./benchmarks/foo
```

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **No prerequisites** — FEAT-1244 (`lib/benchmark.yaml`) and FEAT-1245 (fragment wiring) are both COMPLETED. `lib/benchmark.yaml` exists and `run_benchmark` is verified. Proceed directly to Step 2.

2. **Create `scripts/little_loops/loops/harness-optimize.yaml`** with states following the shape in `apo-feedback-refinement.yaml`:
   - Declare `import: [lib/common.yaml, lib/benchmark.yaml]`
   - `load_directive` → reads `${context.targets}` and optional `.ll/program.md`
   - `baseline_score` → `fragment: run_benchmark`; `action: "${context.scorer} ${context.tasks_dir}"`; `capture: baseline`; `on_yes: init_prev`; `on_no: done`; `on_error: done`
   - `init_prev` → shell: `echo '${captured.baseline.output}' | tail -1 | tr -d '[:space:]'`; `capture: prev_score`; `next: propose` — seeds `prev_score` with baseline so the first `gate` call has a correct reference (without this, `previous=None` on iteration 1 always returns `progress`, committing score-worsening mutations)
   - `propose` → LLM prompt state; "Pick ONE file from `${context.targets}` to improve this iteration"; outputs complete revised file contents only; `capture: candidate`; `on_blocked: done`; `next: apply`
   - `apply` → prompt state: "Write the following revised contents to the file you proposed editing. Replace the entire file contents exactly.  ${captured.candidate.output}"; `next: score`
   - `score` → `fragment: run_benchmark`; `action: "${context.scorer} ${context.tasks_dir}"`; `capture: benchmark_score`; `on_yes: gate`; `on_no: revert_and_log`; `on_error: revert_and_log`
   - `gate` → shell: `echo "${captured.benchmark_score.output}" | tail -1 | tr -d '[:space:]'`; `convergence` evaluator with `direction: maximize`, `target: "${context.target_score}"`, `previous: "${captured.prev_score.output}"`, `tolerance: 0.02`; `route: target/progress → commit_and_log`; `route: stall/error → revert_and_log`
   - `commit_and_log` → shell: `git add ${context.targets} && git commit -m "harness-optimize: iter ${state.iteration}, score ${captured.benchmark_score.output}" && git rev-parse HEAD`; `capture: last_commit`; `next: write_trajectory_accepted`
   - `revert_and_log` → shell: `git restore ${context.targets}`; `next: write_trajectory_rejected`
   - `write_trajectory_accepted` → shell: append `{"iter":…,"score":…,"accepted":true,"commit_sha":"…"}` to `.loops/tmp/harness-optimize-trajectory.jsonl`; `next: capture_prev`
   - `write_trajectory_rejected` → shell: append `{"iter":…,"score":…,"accepted":false,"commit_sha":""}` to `.loops/tmp/harness-optimize-trajectory.jsonl`; `next: done`
   - `capture_prev` → shell: `echo '${captured.benchmark_score.output}' | tail -1 | tr -d '[:space:]'`; `capture: prev_score`; `next: propose`
   - **Stop on first stall**: `gate route.stall → revert_and_log → write_trajectory_rejected → done`; `max_iterations: 30` is the hard budget ceiling

3. **Trajectory JSONL**: Use two separate shell states — `write_trajectory_accepted` and `write_trajectory_rejected` — each appending one JSON line to `.loops/tmp/harness-optimize-trajectory.jsonl`. Fields: `iter` (`${state.iteration}`), `score` (`${captured.benchmark_score.output}`), `accepted` (true/false), `commit_sha` (`${captured.last_commit.output}` or `""`). See corrected YAML in Pass 3 above.

4. **Update `scripts/tests/test_builtin_loops.py`**: Add `"harness-optimize"` to the `expected` set in `test_expected_loops_exist()` (lines 48-91, add before the closing `}` at line 91)

5. **Add structural test** `scripts/tests/test_harness_optimize.py` following `test_outer_loop_eval.py:1-162` exactly:

```python
LOOP_FILE = BUILTIN_LOOPS_DIR / "harness-optimize.yaml"

class TestHarnessOptimizeFile:
    def test_file_exists(self) -> None: ...
    def test_parses_as_yaml(self, loop_data) -> None: ...
    def test_validates_as_fsm(self) -> None: ...
    def test_name(self, loop_data) -> None: assert loop_data.get("name") == "harness-optimize"
    def test_initial_state(self, loop_data) -> None: assert loop_data.get("initial") == "load_directive"
    def test_terminal_state(self, loop_data) -> None: assert states["done"].get("terminal") is True
    def test_context_defaults(self, loop_data) -> None:
        # targets/tasks_dir/scorer == "" (required, no defaults); target_score == 1.0; max_iterations == 30

class TestHarnessOptimizeStates:
    REQUIRED_STATES = {
        "load_directive", "baseline_score", "init_prev", "propose", "apply",
        "score", "gate", "commit_and_log", "revert_and_log",
        "write_trajectory_accepted", "write_trajectory_rejected", "capture_prev", "done",
    }

    def test_has_all_required_states(self, loop_data) -> None: ...
    def test_score_state_uses_run_benchmark_fragment(self, loop_data) -> None:
        state = loop_data["states"]["score"]
        assert state.get("fragment") == "run_benchmark"
        assert state.get("capture") == "benchmark_score"
        assert "context.scorer" in state.get("action", "")
        assert "context.tasks_dir" in state.get("action", "")
        assert state.get("on_yes") == "gate"
        assert state.get("on_no") == "revert_and_log"
        assert state.get("on_error") == "revert_and_log"
    def test_gate_has_convergence_evaluator(self, loop_data) -> None:
        evaluate = loop_data["states"]["gate"].get("evaluate", {})
        assert evaluate.get("type") == "convergence"
        assert evaluate.get("direction") == "maximize"
        assert "previous" in evaluate  # prevents always-progress bug; must reference captured.prev_score.output
        assert "target" in evaluate
        assert "tolerance" in evaluate
    def test_capture_prev_captures_prev_score(self, loop_data) -> None:
        assert loop_data["states"]["capture_prev"].get("capture") == "prev_score"
    def test_write_trajectory_accepted_routes_to_capture_prev(self, loop_data) -> None:
        assert loop_data["states"]["write_trajectory_accepted"].get("next") == "capture_prev"
    def test_write_trajectory_rejected_routes_to_done(self, loop_data) -> None:
        assert loop_data["states"]["write_trajectory_rejected"].get("next") == "done"
```

  Note: `test_all_validate_as_valid_fsm` in `test_builtin_loops.py:36-44` also picks up `harness-optimize.yaml` automatically — structural defects break that test first.

  **Confirmed from codebase (Pass 4):**
  - Insert `"harness-optimize"` after `"harness-multi-item"` (line 72) in the `expected` set — the set uses loose alphabetical grouping, harness-* entries cluster together.
  - Integration tests in `test_ll_loop_integration.py` use inline `write_text()` to create temporary loop YAML files — no fixture YAML files from `fixtures/fsm/` are used in integration tests.
  - `TestBenchmarkYamlFragments` at `test_fsm_fragments.py:1031-1120` ALREADY tests the `run_benchmark` fragment (description, action_type, harbor_scorer evaluator, full resolve round-trip). No new fragment test needed for this issue.
  - The `test_fsm_fragments.py:522-662` reference in the wiring section is the MODEL/PATTERN; the actual test that followed that model (`TestBenchmarkYamlFragments`) is already in the file.

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
- `scripts/tests/test_harness_optimize.py` — structural tests: follow `test_outer_loop_eval.py:1-154` pattern (`TestHarnessOptimizeFile` + `TestHarnessOptimizeStates` classes, `REQUIRED_STATES` set, `load_and_validate` + `validate_fsm` calls); assert `trajectory.jsonl` write path, `git restore` with scoped `context.targets`, `capture_prev` state has `capture: prev_score`, and `gate` evaluate block has `previous:` field — all gaps without existing test infra [Agent 3 + Pass 2 finding]
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

~~FEAT-1244: benchmark fragment core FSM fragment~~ — **COMPLETED** (2026-04-23).
~~FEAT-1245: benchmark fragment loop integration~~ — **COMPLETED** (2026-04-24).

No remaining hard blockers. `lib/benchmark.yaml` exists and `run_benchmark` fragment is integrated.

## Dependencies

No hard blockers. Prior blockers resolved:
- ~~FEAT-1244~~ (COMPLETED) — `lib/benchmark.yaml` delivered
- ~~FEAT-1245~~ (COMPLETED) — `run_benchmark` fragment wired into outer-loop-eval and agent-eval-improve

Related: FEAT-1121 (program.md convention) — nice-to-have entry point; not a hard blocker.
Related: ENH-1122 (frozen-boundary markers) — guardrail that becomes useful once this loop exists.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-24T20:46:37 - `f0fba88a-2c81-43e6-a5ae-62db66bcbacf.jsonl`
- `/ll:ready-issue` - 2026-04-24T20:37:34 - `acf4b7da-c497-4830-86b1-7e9c5a8f857f.jsonl`
- `/ll:confidence-check` - 2026-04-24T00:00:00 - `00728f59-db70-4cfa-8e4f-777d3b228f0d.jsonl`
- `/ll:refine-issue` - 2026-04-24T20:28:39 - `e7ed6f36-d7d3-48ef-81c1-7f05910e63b1.jsonl`
- `manual design review` - 2026-04-24T00:00:00 - Pass 3 corrections: `apply` state, `init_prev`, two trajectory states, `context:` defaults, `baseline_score` routing, stop-on-first-stall decision, `tolerance` on gate, Step 1 naming fix
- `/ll:ready-issue` - 2026-04-24T19:52:50 - `8fd6b77b-30ba-416d-9b65-f83eb1c8f249.jsonl`
- `/ll:confidence-check` - 2026-04-24T00:00:00 - `b62e23ea-a883-4713-8d17-abc2c3993dec.jsonl`
- `/ll:refine-issue` - 2026-04-24T19:42:31 - `178c621a-952b-461d-8ff0-0d865bd6d928.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:ready-issue` - 2026-04-22T02:14:27 - `2ed16b00-515e-4758-a2d9-74c23897b796.jsonl`
- `/ll:ready-issue` - 2026-04-22T01:59:25 - `1ce1718d-d54e-4865-8898-1a6b65a7f382.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `338c071f-3b53-4a00-b600-f0c19c9a42ba.jsonl`
- `/ll:refine-issue` - 2026-04-22T01:33:06 - `bdc49cbb-e9c2-4adc-a9db-bbbc98cdb724.jsonl`
- `/ll:ready-issue` - 2026-04-21T23:26:54 - `7c3c7599-51fd-4437-8dcc-1843715b82b7.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `ca7bea0a-41dc-42cd-8f16-e1a5bb35f04b.jsonl`
- `/ll:wire-issue` - 2026-04-21T00:00:00 - `current.jsonl`
- `/ll:refine-issue` - 2026-04-21T23:15:07 - `17a43e35-c912-41c4-b189-d47f33dc1242.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-19T01:16:14 - `9c7ed14d-9621-459d-9f93-384968b2e6f6.jsonl`
- `/ll:capture-issue` - 2026-04-16T00:00:00Z - `2fb1a4ee-5512-43ed-b858-2a21a4738fb8.jsonl`

---

## Verification Notes

**Verdict**: READY_TO_IMPLEMENT — Verified 2026-04-24

- `scripts/little_loops/loops/harness-optimize.yaml` does not exist ✓ (feature not yet implemented — expected)
- Both blockers COMPLETED: FEAT-1244 (`lib/benchmark.yaml`) and FEAT-1245 (fragment wiring into outer-loop-eval and agent-eval-improve)
- `lib/benchmark.yaml` confirmed present at `scripts/little_loops/loops/lib/benchmark.yaml` with correct `run_benchmark` fragment
- `TestBenchmarkYamlFragments` at `test_fsm_fragments.py:1031-1120` already covers the fragment — no new fragment test needed
- All design decisions verified against live codebase across 4 research passes (evaluators.py, schema.py, persistence.py, interpolation.py)

## Resolution

Implemented in commit. Created `scripts/little_loops/loops/harness-optimize.yaml` with the full score-gated hill-climbing state machine: `load_directive → baseline_score → init_prev → propose → apply → score → gate → commit_and_log/revert_and_log → write_trajectory_accepted/write_trajectory_rejected → capture_prev/done`. Added `scripts/tests/test_harness_optimize.py` with 19 structural tests (all passing). Updated `test_builtin_loops.py` expected set, README.md (43 FSM loops), CONTRIBUTING.md (43 YAML files), LOOPS_GUIDE.md Harness Examples table, and created `docs/reference/loops.md`.

## Status

Completed

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Default mutable-boundary policy is **mutable-all** — files without `<!-- ll:mutable -->` / `<!-- ll:frozen -->` markers (per ENH-1122) are fully mutable by this loop. The frozen-all safety mode is opt-in via loop config. This preserves current behavior and keeps harness-optimize low-friction while ENH-1122's boundary markers let authors explicitly protect regions.
