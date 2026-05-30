# Built-in FSM Loop Audit: Per-Run Artifact Isolation

**Date:** 2026-05-30
**Scope:** All runnable loops in `scripts/little_loops/loops/` (62 top-level + 1 oracle, excluding `loops/lib/` fragments).
**Convention under audit:** Loop intermediate artifacts (queues, checkpoints, generated files) should be written under the runner-injected `${context.run_dir}/` (resolving to `.loops/runs/<loop>-<timestamp>/`), not shared `.loops/tmp/` — concurrent runs of the same loop under `ll-parallel` or re-entry would otherwise corrupt each other's state.

## TL;DR

| Category | Count | Notes |
|---|---|---|
| Per-run (correctly use `${context.run_dir}`) | 15 | Reference template loops |
| Shared-tmp violators | 18 | Subject to new MR-3 WARNING |
| Stateless (no shell-action writes) | 30 | Out of scope |
| External-legitimate (`.issues/`, `.loops/diagnostics/`, etc.) | — | Not flagged by MR-3 |

The new validator rule **MR-3** (`scripts/little_loops/fsm/validation.py`, severity WARNING) surfaces these 18 violators on every `ll-loop validate` run; this report enumerates them and proposes the per-violator migration path. Migration itself is out of scope for the rule-introduction change.

## Methodology

For each YAML in `scripts/little_loops/loops/` (recursive, excluding `loops/lib/`):

1. **Per-run detection** — `grep -l 'context\.run_dir'` identifies loops that reference the runner-injected per-run path.
2. **Shared-tmp detection** — `grep -oE '\.loops/tmp/[a-zA-Z0-9._/-]+'` counts per-file occurrences. Matches `.loops/tmp/<file>` regardless of whether the prefix is `"${env.PWD}/.loops/tmp/..."` or bare.
3. **Stateless classification** — loops with no shell-action writes (no `>` redirects to artifact paths) and no `context.run_dir` references; typically sub-loop dispatchers or skill-wrapper loops.

**Known limitation:** Static scan only inspects `state.action` strings. Prompts (action_type=prompt) that instruct the LLM to `Write` to a path are out of reach — the prompt text is in `action`, so paths it references *are* detected, but whether the LLM actually obeys cannot be checked statically. Conversely, a sub-loop that writes via its own runner-injected `run_dir` is fine; the parent loop never sees those paths.

## Per-run loops (15)

These loops correctly use `${context.run_dir}` for their intermediate artifacts. They are the reference templates for new loop authoring.

| Loop | Notes |
|---|---|
| `cli-anything-bootstrap` | Context-relative paths only |
| `deep-research` | Reference template |
| `deep-research-arxiv` | Reference template |
| `hitl-compare` | Per-run scratch + HITL artifacts |
| `hitl-md` | Mostly per-run (1 stray `.loops/tmp/` write — see violators) |
| `html-anything` | Per-run generated output |
| `html-website-generator` | Per-run generated output |
| `p5js-sketch-generator` | Per-run generated sketches |
| `pixi-data-viz` | Per-run generated visualizations |
| `pixi-generative-art` | Per-run generated art |
| `rn-plan` | Reference template (recursive-rn family) |
| `rn-plan-apo` | Per-run + APO scratch |
| `rn-refine` | Reference template (standalone recursive-refine path; see `project_recursive_refine_standalone` memory) |
| `svg-image-generator` | Per-run generated SVGs |
| `svg-textgrad` | Per-run + TextGrad scratch |

## Shared-tmp violators (18)

Ordered by occurrence count (number of distinct `.loops/tmp/<path>` matches found in the YAML's `action` blocks). Higher counts indicate deeper entanglement with shared state and a larger migration surface.

| # | Loop | Occurrences | Migration recommendation |
|---|---|---|---|
| 1 | `recursive-refine` | 127 | Highest priority. Per-run is conceptually correct: each invocation has its own work queue, depth map, attempt counter, etc. Migrate `.loops/tmp/recursive-refine-*` → `${context.run_dir}/<stem>` mechanically (single sed sweep) — the file *roles* are already per-run, just the *paths* are wrong. |
| 2 | `autodev` | 69 | Per-run is correct (work queue + per-issue tracking). Same mechanical migration as #1. |
| 3 | `general-task` | 32 | Per-run is correct (plan, DoD, step list, checkpoint counter are all single-invocation artifacts). Files all named `.loops/tmp/general-task-*` — straightforward rename. |
| 4 | `loop-router` | 23 | Per-run is correct (router catalog, choice, and dispatch input are scoped to a single routing decision). Mechanical migration. |
| 5 | `harness-optimize` | 16 | Per-run is correct (candidate actions, state queue per optimization run). Already uses `meta_self_eval_ok` for MR-1; should add per-run paths. |
| 6 | `auto-refine-and-implement` | 12 | Per-run is correct (skip list, refinement queue scoped to one run). |
| 7 | `prompt-across-issues` | 10 | Per-run is correct (pending-issues queue, prompt template state). |
| 8 | `test-coverage-improvement` | 9 | Per-run is correct (coverage gaps, test results scoped to one run). |
| 9 | `sprint-refine-and-implement` | 9 | Mirrors `auto-refine-and-implement` (#6). |
| 10 | `scan-and-implement` | 7 | Per-run is correct (scan queue + implementation tracking). |
| 11 | `refine-to-ready-issue` | 7 | Per-run is correct (refine count, wire state, broke-down flag scoped to a single issue's refinement pass). |
| 12 | `dead-code-cleanup` | 7 | Per-run is correct (dead-code candidates list scoped to one cleanup pass). |
| 13 | `issue-refinement` | 5 | Per-run is correct. |
| 14 | `fix-quality-and-tests` | 2 | Per-run is correct. |
| 15 | `evaluation-quality` | 2 | Per-run is correct. |
| 16 | `prompt-regression-test` | 1 | Per-run is correct. |
| 17 | `hitl-md` | 1 | Stray write; mostly already per-run. One-line fix. |
| 18 | `harness-multi-item` | 1 | Per-run is correct. |

**Observation:** Every violator's intermediate state is *conceptually* per-run — none of them legitimately need cross-invocation sharing. This means the migration is mostly mechanical (sed-style renames from `.loops/tmp/<loop>-*` → `${context.run_dir}/<stem>`) rather than requiring redesign. The `shared_state_ok: true` escape hatch is unlikely to be needed for any of these.

**Sample violation pattern** (from `scripts/little_loops/loops/general-task.yaml:19-20`):

```yaml
context:
  plan_path: "${env.PWD}/.loops/tmp/general-task-plan.md"
  dod_path: "${env.PWD}/.loops/tmp/general-task-dod.md"
```

**Suggested fix:**

```yaml
context:
  plan_path: "${context.run_dir}/plan.md"
  dod_path: "${context.run_dir}/dod.md"
```

## External-legitimate writes (not violations)

These paths are *intentionally* shared across runs and are not matched by MR-3's regex (`.loops/tmp/` only):

- `.issues/` — issue-discovery loops (`scan-codebase`, `capture-issue`, `recursive-refine`, `scan-and-implement`, etc.) write here because issues are the durable artifact. Cross-run sharing is the point.
- `.loops/diagnostics/` — `loop-specialist-eval` writes diagnoses here for longitudinal review.
- `thoughts/`, `docs/` — research and documentation outputs persist across runs.

No action required for these.

## Stateless loops (30, sampled)

Most remaining loops either delegate everything to sub-loops or to `/ll:*` skills that handle their own artifacts. Examples: `adopt-third-party-api`, `apo-*`, `assumption-firewall`, `backlog-flow-optimizer`, `context-health-monitor`, `docs-sync`, `examples-miner`, `greenfield-builder`, etc. These do not appear in either grep (no `context.run_dir`, no `.loops/tmp/`) — they're transparent to the artifact-isolation rule.

## Follow-up backlog

This audit defines the migration scope but does not perform it. Suggested order:

1. **Quick wins** (single-line fixes): `prompt-regression-test`, `hitl-md`, `harness-multi-item`, `evaluation-quality`, `fix-quality-and-tests`.
2. **Medium**: `issue-refinement`, `dead-code-cleanup`, `refine-to-ready-issue`, `scan-and-implement`, `sprint-refine-and-implement`, `test-coverage-improvement`, `prompt-across-issues`, `auto-refine-and-implement`, `harness-optimize`.
3. **Heavy** (large diff, but mechanical): `loop-router`, `general-task`, `autodev`, `recursive-refine`.

Each migration is a separate issue/PR. The `ll-loop validate` warning emitted on every routine validation run keeps these on the radar without breaking CI (MR-3 is WARNING severity by design — see plan rationale).

## Verification commands

```bash
# 1. Run the new rule's tests
python -m pytest scripts/tests/test_fsm_validation.py::TestArtifactIsolation \
                 scripts/tests/test_fsm_schema.py::TestSharedStateOk -v

# 2. Confirm all built-in loops still pass (WARNINGs are non-blocking)
python -m pytest scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_all_validate_as_valid_fsm -v

# 3. Spot-check a clean loop vs. a violator
ll-loop validate rn-plan            # no MR-3 warnings
ll-loop validate recursive-refine   # ~30+ MR-3 warnings

# 4. Reproduce the per-loop occurrence count
for f in scripts/little_loops/loops/*.yaml scripts/little_loops/loops/oracles/*.yaml; do
  name=$(basename "$f" .yaml)
  count=$(grep -oE '\.loops/tmp/[a-zA-Z0-9._/-]+' "$f" 2>/dev/null | wc -l | tr -d ' ')
  [ "$count" -gt 0 ] && echo "$count $name"
done | sort -rn
```
