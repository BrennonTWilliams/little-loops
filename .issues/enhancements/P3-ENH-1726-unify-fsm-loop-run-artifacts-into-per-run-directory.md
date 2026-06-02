---
id: ENH-1726
type: ENH
priority: P3
status: done
discovered_date: 2026-05-26
discovered_by: capture-issue
captured_at: '2026-05-26T20:24:33Z'
completed_at: '2026-05-27T05:21:06Z'
decision_needed: false
relates_to:
- ENH-1684
confidence_score: 100
outcome_confidence: 62
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-1726: Unify FSM loop run artifacts into a per-run directory under `.loops/runs/`

## Summary

Domain artifacts produced by FSM loops (research files, plans, generated content) are currently scattered across loop-specific subdirectories (`.loops/research/`, `.loops/plans/`, etc.) with no consistent naming or isolation across runs. Standardize all loop run artifact output into a unified per-run subdirectory — `.loops/runs/{loop-name}-{timestamp}/` — so every run's artifacts are co-located, comparable, and independently cleanable.

## Current Behavior

Each loop hardcodes its own `output_dir` in `context` (e.g., `context.output_dir: .loops/research`). Re-running the same loop deposits artifacts into the same directory, potentially overwriting prior runs (the immediate data-loss bug addressed by ENH-1684). There is no standard path or variable a loop author can use to get a fresh, isolated directory per invocation.

The FSM does already provide per-run isolation for its own internal state (`.loops/.running/` for live state and `.loops/.history/<run_id>-<loop_name>/` after archival), but domain artifacts are not co-located with that FSM state.

## Expected Behavior

- The `ll-loop` runner injects a `run_dir` template variable into every loop's context at startup, set to `.loops/runs/{loop-name}-{YYYYMMDDTHHMMSS}/`.
- Loop YAML authors use `${context.run_dir}` instead of a hardcoded `output_dir` to write their domain artifacts.
- Each invocation creates a new, isolated directory:
  ```
  .loops/runs/deep-research-20260526T143022/
    report.md
    knowledge-base.md
    coverage.md
    query-log.md
  .loops/runs/deep-research-20260526T150811/
    report.md
    ...
  ```
- Cleaning up one run is a single `rm -rf .loops/runs/deep-research-20260526T143022/`.
- Comparing two runs of the same loop is straightforward (`diff` or side-by-side).

## Motivation

- **Eliminates the ENH-1684 class of data-loss bugs** at the structural level: no loop can silently overwrite a prior run because every run lands in its own timestamped directory. ENH-1684 and `deep-research-arxiv.yaml` both require individual patches under the current model; the unified `run_dir` approach fixes all loops at once.
- **Discoverability**: all artifacts for a run are in one place — FSM `.history/` archives can optionally symlink or reference the corresponding `runs/` entry.
- **Cleanup ergonomics**: `ll-loop clean` can target a single run directory rather than hunting across multiple type-specific dirs.
- **Consistency**: loop authors no longer need to invent per-loop output path conventions.

## Proposed Solution

1. **Runner injects `run_dir`**: In `scripts/little_loops/fsm/` (likely `persistence.py` or the loop executor), generate a `run_dir` value of the form `.loops/runs/{loop_name}-{timestamp}` at run startup and inject it into the loop's template context as `context.run_dir`. Create the directory before the `init` state executes.

2. **Convention for loop YAML authors**: Document `${context.run_dir}` as the canonical way to reference the run's artifact directory. Loops that currently use `context.output_dir` migrate to `context.run_dir`.

3. **Migrate existing built-in loops**: Update `deep-research.yaml`, `deep-research-arxiv.yaml`, and any other built-in loops that use a custom `output_dir` to use `${context.run_dir}` instead.

4. **Scope exclusions**:
   - `.loops/tmp/` remains a shared, cross-run scratch space (rate-limit circuit breaker, session scratch files). Not per-run.
   - `.loops/.running/` and `.loops/.history/` (FSM internal state) are unaffected — this change is about domain artifacts only.
   - `context.output_dir` stays valid for loops that intentionally want a stable, non-timestamped output path (e.g., loops that accumulate data over time).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` or loop executor — inject `run_dir` into context at startup; also update module docstring `.loops/` directory layout diagram to include `runs/`
- `scripts/little_loops/loops/deep-research.yaml` — replace `output_dir`/`DIR` construction with `${context.run_dir}`
- `scripts/little_loops/loops/deep-research-arxiv.yaml` — same migration
- Any other built-in loops using custom output directories

_Wiring pass added by `/ll:wire-issue`:_
- `.gitignore` — add `.loops/runs/` entry; currently only `.loops/.running/`, `.loops/.history/`, `.loops/.queue/`, `.loops/tmp/`, `.loops/diagnostics/`, `.loops/reviews/` are present; the specific `.ll/runs/harness-optimize/` entry should be generalized to `.loops/runs/` [Agent 1 + 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — entrypoint that kicks off loop execution; likely where `run_dir` generation belongs
- `scripts/little_loops/cli/loop/next_loop.py` — may need access to `run_dir`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` bypasses `cmd_run()` and therefore bypasses `run_dir` injection; verify that `StatePersistence` serializes `fsm.context` (including `run_dir`) so resumed loops can access it — if not, add parallel injection in `cmd_resume()` [Agent 1 + 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Actual injection point (corrects above)**: `cmd_run()` in `scripts/little_loops/cli/loop/run.py` (~line 151) — after `--context` overrides are applied but before `run_foreground()` / `run_background()` is called. This is where all context merging already happens; `__init__.py` is just the package init and `next_loop.py` does not need changes.

**`run_id` reuse opportunity**: `scripts/little_loops/fsm/persistence.py:generate_run_id()` already generates `YYYYMMDDTHHMMSS_<8hex>`. The `StatePersistence` object is created in `_helpers.py` before the executor; `run_dir` can be derived from `persistence.run_id` for guaranteed uniqueness: `.loops/runs/{loop_name}-{persistence.run_id}/`.

**Template engine confirmation**: `scripts/little_loops/fsm/interpolation.py:InterpolationContext` resolves `${context.X}` from `loop.context` — no changes to `interpolation.py` needed; `${context.run_dir}` will work automatically once injected.

**Additional loops needing migration** (beyond deep-research.yaml / deep-research-arxiv.yaml):
- `scripts/little_loops/loops/rn-plan.yaml` — `context.output_dir: .loops/plans`
- `scripts/little_loops/loops/rn-plan-apo.yaml` — `context.output_dir: .loops/plans`
- `scripts/little_loops/loops/rn-refine.yaml` — references `.loops/plans`
- `scripts/little_loops/loops/svg-image-generator.yaml` — inline `DIR` derivation in init bash
- `scripts/little_loops/loops/svg-textgrad.yaml` — inline `DIR` derivation in init bash
- `scripts/little_loops/loops/html-anything.yaml` — `context.output_dir: .loops/html`
- `scripts/little_loops/loops/html-website-generator.yaml` — `context.output_dir: .loops/html`
- `scripts/little_loops/loops/hitl-md.yaml` — `context.output_dir: .loops/artifacts`
- `scripts/little_loops/loops/hitl-compare.yaml` — `context.output_dir: .loops/artifacts`
- `scripts/little_loops/loops/dataset-curation.yaml` — `context.output_dir: .loops/datasets`

**deep-research init state pattern**: Both deep-research loops use a `.current_dir` sentinel file to persist `DIR` across states (init writes the resolved path; subsequent states read it back). Migration replaces `DIR="${context.output_dir}/$SLUG"` with `DIR="${context.run_dir}"` — the sentinel file pattern can remain but points to the new per-run location.

### Similar Patterns
- ENH-1684 is the narrow per-loop patch this replaces at the structural level
- `.loops/.history/<run_id>-<loop_name>/` — existing per-run isolation model for FSM state; `runs/` mirrors this pattern for domain artifacts

### Tests
- `scripts/tests/test_deep_research.py` — update path assertions to match new `runs/` layout (asserts `loop.context["output_dir"] == ".loops/research"` ~line 97; update for `run_dir`)
- `scripts/tests/test_deep_research_arxiv.py` — same as above for arxiv variant
- `scripts/tests/test_rn_plan.py` — asserts on `.loops/plans` paths; update for `run_dir`
- `scripts/tests/test_rn_refine.py` — asserts on `.loops/plans` paths
- `scripts/tests/test_builtin_loops.py` — check for hardcoded path assertions
- `scripts/tests/test_ll_loop_state.py` — shows `.running/` fixture construction pattern to follow for new `run_dir` injection tests (`TestCmdStop`, `TestCmdResume`)
- `scripts/tests/test_ll_loop_commands.py` — shows `.history/` path construction pattern (`TestHistoryTailTruncation._write_events()`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` `TestSvgImageGeneratorLoop`, `TestSvgTextgradLoop`, `TestHtmlAnythingLoop`, `TestHitlCompareLoop`, `TestHitlMdLoop` — each asserts the exact `output_dir` value (e.g., `".loops/tmp/svg-image-generator"`); these specific test methods will break after migration and need updating [Agent 3 finding]
- `scripts/tests/test_rn_plan_apo.py` — analog of `test_rn_plan.py`; verify it asserts on `.loops/plans` paths and update accordingly [Agent 1 finding]
- `scripts/tests/test_cli_loop_background.py` `TestMakeInstanceId` — tests `_make_instance_id()` format and uniqueness; verify no artifact path assertions break; also the reference implementation pattern for the timestamp format used in `run_dir` [Agent 3 finding]
- `scripts/tests/test_ll_loop_program_md.py` `TestCmdRunProgramMdInjection` — **do not modify**; this test is the canonical pattern to follow when writing the new `run_dir` injection test (uses `cmd_run()` + `dry_run=True` + `load_and_validate` patch to inspect `fsm.context` after injection) [Agent 3 finding]
- **New test to write**: Add a test class (in `test_ll_loop_commands.py` or a new file) following the `TestCmdRunProgramMdInjection` pattern that verifies: (1) `fsm.context["run_dir"]` is set to `.loops/runs/{loop_name}-{timestamp}/` after `cmd_run()`, (2) the directory was created on disk at `tmp_path / ".loops" / "runs" / ...`, (3) the path format matches `{loop_name}-YYYYMMDDTHHMMSS` consistent with `_make_instance_id()` output [Agent 3 finding]

### Documentation
- `docs/ARCHITECTURE.md` — update `.loops/` directory structure diagram
- Loop authoring section of CLAUDE.md — document `${context.run_dir}` convention

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — 9 separate sections referencing `output_dir` tables and example artifact paths for `deep-research`, `rn-plan`, `rn-refine`, `html-anything`, `hitl-compare`, `hitl-md`, `html-website-generator`, `svg-image-generator`, `svg-textgrad` loops; each must replace the documented `output_dir` default with `run_dir` convention [Agent 2 finding]
- `docs/reference/loops.md` — 4 coupling points in the `deep-research` reference section: `--context output_dir=...` example invocation, context variables table `output_dir` row, init state graph comment, and output artifacts section; update all to `run_dir` [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — documents `output_dir` as a conventional context key with example YAML; add `run_dir` as runner-injected alternative and migration pattern [Agent 2 finding]

### Configuration
- N/A — no config file changes needed; `run_dir` is runtime-injected

## Implementation Steps

1. Add `run_dir` generation to the loop executor (compute `{loop_name}-{timestamp}`, mkdir, inject into context).
2. Update `deep-research.yaml` and `deep-research-arxiv.yaml` to use `${context.run_dir}`.
3. Audit remaining built-in loops for custom `output_dir` usage and migrate.
4. Update tests that assert on `.loops/research/` or other old artifact paths.
5. Document the `${context.run_dir}` convention in loop authoring docs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — Exact injection location and code pattern:**

`cmd_run()` in `scripts/little_loops/cli/loop/run.py` already mutates `fsm.context` before constructing the executor (context overrides from `--context` args are applied there). Add `run_dir` injection immediately after those overrides:

```python
# After applying --context overrides, before creating PersistentExecutor:
from pathlib import Path
run_dir = f".loops/runs/{_make_instance_id(loop.name)}/"
Path(run_dir).mkdir(parents=True, exist_ok=True)
fsm.context["run_dir"] = run_dir
```

`_make_instance_id()` in `scripts/little_loops/cli/loop/_helpers.py` already generates `{loop_name}-{YYYYMMDDTHHMMSS}` — reuse it directly. No new timestamp logic needed.

Also inject in `run_background()` in `_helpers.py` if it constructs a separate executor path (verify).

**Step 2 — deep-research migration detail:**

These loops use `capture: run_dir` in the init state (captures stdout as the resolved dir path) and reference it in subsequent states as `${captured.run_dir.output}` — NOT `${context.run_dir}`. The migration replaces the init state's shell computation:

```bash
# Before (init state shell command):
SLUG=$(echo "$TOPIC" | tr '[:upper:]' '[:lower:]' | ...)
DIR="${context.output_dir}/$SLUG"
mkdir -p "$DIR"
echo "$(pwd)/$DIR"   # captured as run_dir
```

```bash
# After (init state can use run_dir directly, no slug needed):
echo "$(pwd)/${context.run_dir}"   # or just remove the capture: if run_dir is sufficient
```

Alternatively: keep the `capture: run_dir` pattern but source it from `${context.run_dir}` instead of computing from `output_dir`; subsequent states remain unchanged.

**Step 3 — loops using `.loops/tmp/` do NOT need migration:**

`general-task.yaml`, `fix-quality-and-tests.yaml`, `scan-and-implement.yaml` and similar use `.loops/tmp/<loop-name>-<artifact>` paths — these are intentional shared/stateless scratch that must persist across runs. Do not migrate these.

**Step 4 — Test patterns to follow:**

`scripts/tests/test_ll_loop_state.py:TestCmdStop` shows how to construct `.running/` fixtures with `tmp_path`. Use the same pattern for new `run_dir` tests:

```python
loops_dir = tmp_path / ".loops"
runs_dir = loops_dir / "runs"
# After run: assert runs_dir children match f"{loop_name}-*" glob
```

**Step 5 — Context injection is transparent to the template engine:**

`FSMExecutor._build_context()` in `scripts/little_loops/fsm/executor.py` reads `self.fsm.context` by reference on every state. Any key added to `fsm.context` before executor construction is automatically available as `${context.KEY}` in all states — no changes to `interpolation.py` or `executor.py` needed.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Inject `run_dir` before the missing-keys validation scan** — `cmd_run()` in `run.py` validates required context keys at ~line 198; the injection must happen before this scan (not after `PersistentExecutor` construction) to avoid false "missing context variable" errors on loops that reference `${context.run_dir}`. The dry-run exit at line ~173 is fine to precede the injection if dry-run tests don't exercise loops using `${context.run_dir}`; otherwise inject before the dry-run exit as well.
7. **Handle `cmd_resume()` in `lifecycle.py`** — `cmd_resume()` builds a `PersistentExecutor` from the YAML (context is rehydrated from YAML, not persisted state). Without a parallel `run_dir` injection here, resumed loops will fail on `${context.run_dir}` references. Either add the same injection before `PersistentExecutor` construction in `cmd_resume()`, or verify and document that loops are expected to fall back to a stable `output_dir` on resume.
8. **Update `rn-plan-apo.yaml` `run_planner` and `score_plans` states** — the `run_planner` state currently invokes `ll-loop run rn-plan "$TASK" --context output_dir="$RUN_DIR/plans"` and `score_plans` reads from `${captured.plans.output}/plans/`. After `rn-plan` migrates to `${context.run_dir}`, this explicit `--context output_dir=...` override becomes inert and `score_plans` can no longer find plan outputs at the expected path. Update both states together with `rn-plan.yaml`. [Agent 2 finding]
9. **Add `.loops/runs/` to `.gitignore`** — the per-run artifact directories are runtime output and should not be committed. The current entry `.ll/runs/harness-optimize/` is a misplaced specific entry; replace with a generic `.loops/runs/` pattern.
10. **Update `docs/guides/LOOPS_GUIDE.md`** — 9 loop-specific sections reference `output_dir` defaults and artifact path examples; update each section to document `${context.run_dir}` convention and the new per-run artifact layout.
11. **Update `docs/reference/loops.md`** and **`docs/generalized-fsm-loop.md`** — remove or migrate `output_dir` examples to `run_dir`; add the runner-injected variable table.

## Scope Boundaries

- **In scope**: Built-in loops that use a hardcoded `output_dir` pointing to a loop-specific subdir under `.loops/` (`deep-research.yaml`, `deep-research-arxiv.yaml`, and any other built-in loops using custom output paths).
- **Out of scope**: `.loops/tmp/` — shared cross-run scratch space (rate-limit circuit breaker, session scratch files); remains global, not per-run.
- **Out of scope**: `.loops/.running/` and `.loops/.history/` — FSM internal state; unaffected by this change, which is domain artifacts only.
- **Out of scope**: Custom loops using `context.output_dir` for intentionally stable, non-timestamped paths (e.g., accumulation loops). `context.output_dir` remains valid; migration to `run_dir` is opt-in.

## Success Metrics

- All built-in loops write domain artifacts under `.loops/runs/{name}-{ts}/`, not the previous per-loop subdirectories.
- Re-running the same loop creates a distinct timestamped directory; no files from a prior run are overwritten.
- A single `rm -rf .loops/runs/{run-dir}/` removes exactly one run's artifacts without touching other runs.
- Loops that do not adopt `run_dir` continue to execute correctly (non-regression).

## API/Interface

New template variable injected by `ll-loop` runner into every loop's context at startup (before the `init` state), creating the directory before first use:

```
context.run_dir  →  ".loops/runs/{loop_name}-{YYYYMMDDTHHMMSS}/"
```

Existing `context.output_dir` remains valid and unmodified for loops that explicitly define it.

Migration pattern for loop YAML authors:

```yaml
# Before (hardcoded, shared across runs):
context:
  output_dir: .loops/research

# After (per-run, injected by runner):
# Remove output_dir; reference ${context.run_dir} in state prompts/commands
```

## Impact

- **Priority**: P3 — Meaningful quality-of-life and data-safety improvement; not blocking
- **Effort**: Medium — Runner change + migration of existing loops + test updates
- **Risk**: Low — Additive (new dirs under `runs/`); loops that don't use `run_dir` are unaffected; no breaking changes to the FSM state layer
- **Breaking Change**: No — `context.output_dir` remains valid; migration is opt-in for custom loops

## Labels

`loops`, `fsm`, `artifact-management`, `data-safety`

## Status

**Open** | Created: 2026-05-26 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-26_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 62/100 → MODERATE

### Outcome Risk Factors
- **Broad enumeration across 26 change sites** — even with mostly mechanical changes, the wide surface (12 YAML migrations + 6 test updates + 5 doc updates + 2 code files + .gitignore) increases chances of a missed site; a verification grep (`grep -r "output_dir" scripts/little_loops/loops/`) after migration would confirm completeness but is not specified in the issue
- **Open design decision in cmd_resume() handling** — either/or choice is unresolved: add parallel `run_dir` injection in `lifecycle.py:cmd_resume()` vs. rely on serialized context rehydration; resolve before starting to avoid a resume-path bug in the first loop that adopts `${context.run_dir}`
- **rn-plan-apo coordinated update** — `run_planner` state passes `--context output_dir=...` to a nested `ll-loop run rn-plan` call and `score_plans` reads from the resulting path; these two states must be updated together with `rn-plan.yaml` or the nested loop's outputs will be unreachable

### Decision Rationale

**Decision: Option A — inject `run_dir` in `cmd_resume()` (parallel to `cmd_run()`).**

`LoopState.to_dict()` (persistence.py:216) does not include `fsm.context`. `PersistentExecutor.resume()` (persistence.py:769) restores iteration/captured/prev_result etc. but never touches `fsm.context`. `cmd_resume()` loads `fsm` fresh from YAML via `load_loop()` (lifecycle.py:432) — `fsm.context` is populated only from the YAML definition plus `--context` CLI overrides. No `run_dir` is present after resume without explicit injection.

Option B (rely on serialized context) is incorrect because `fsm.context` is not serialized at all.

**Resume continuity**: On resume, inject the SAME `run_dir` as the original run by reconstructing it from the discovered `instance_id` (lifecycle.py:414 — already available as `resumable[0][0]`). Set `run_dir = f".loops/runs/{instance_id}/"` so artifacts from the resumed run continue into the same directory as the original run, not a new timestamped directory.

## Resolution

Implemented in commit `e352d4a6` (2026-05-26). All implementation steps completed:

1. `run_dir` injection added to `cmd_run()` in `scripts/little_loops/cli/loop/run.py` — pre-injected before the validation scan using `_make_instance_id()`; directory created before `PersistentExecutor` construction.
2. `cmd_resume()` in `lifecycle.py` injects the same `run_dir` from the existing `instance_id` for resume continuity.
3. All 10 built-in loops migrated to `${context.run_dir}`: `deep-research.yaml`, `deep-research-arxiv.yaml`, `rn-plan.yaml`, `rn-plan-apo.yaml`, `rn-refine.yaml`, `hitl-compare.yaml`, `hitl-md.yaml`, `html-anything.yaml`, `html-website-generator.yaml`, `svg-image-generator.yaml`, `svg-textgrad.yaml`.
4. Tests updated: `test_builtin_loops.py`, `test_deep_research.py`, `test_deep_research_arxiv.py`, `test_rn_plan.py`, `test_rn_refine.py`. New injection test added in `test_ll_loop_program_md.py`.
5. `.gitignore` updated: `.ll/runs/harness-optimize/` generalized to `.loops/runs/`.
6. 585 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-05-27T05:21:06Z - already implemented; status marked done
- `/ll:ready-issue` - 2026-05-27T05:19:07 - `f43bc75e-8b05-46bc-a8f7-1ca01eb0932d.jsonl`
- `/ll:confidence-check` - 2026-05-26T21:00:00 - `b1a1f3a0-45d3-40a9-a3c3-825b86f43731.jsonl`
- `/ll:wire-issue` - 2026-05-27T00:22:33 - `623b3ad3-472e-486a-b0ac-aa05e638d1f5.jsonl`
- `/ll:refine-issue` - 2026-05-27T00:12:48 - `fc1ae0a4-8512-4b9a-97b5-ed439fd238c7.jsonl`
- `/ll:format-issue` - 2026-05-26T20:29:56 - `47cef901-86e9-4bd2-b772-ff487dd8bdac.jsonl`
- `/ll:capture-issue` - 2026-05-26T20:24:33Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0a02e39e-0327-4fde-996c-a64d954c3e35.jsonl`
