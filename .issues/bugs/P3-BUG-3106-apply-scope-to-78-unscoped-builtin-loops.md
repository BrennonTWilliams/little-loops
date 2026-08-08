---
id: BUG-3106
type: BUG
title: Apply explicit `scope:` to the 78 unscoped built-in loops per the completed
  classification table
priority: P3
status: done
completed_at: '2026-08-08T13:19:02Z'
parent: BUG-3088
captured_at: '2026-08-08T00:00:00Z'
discovered_date: 2026-08-08
discovered_by: issue-size-review
verify_verdict: VALID
reconcile_attempted: true
labels:
- fsm-concurrency
- loop-authoring
relates_to:
- BUG-3088
- BUG-2864
- BUG-3083
- BUG-3087
size: Large
confidence_score: 100
outcome_confidence: 66
score_complexity: 13
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 18
testable: true
---

# BUG-3106: Apply explicit `scope:` to the 78 unscoped built-in loops per the completed classification table

## Summary

This is Deliverable 1 of [BUG-3088](P3-BUG-3088-audit-unscoped-loops-and-warn-on-missing-scope.md).
The audit/classification is already complete and recorded in BUG-3088's
"Classification table (78 loops)" (52 narrow / 26 repo-wide). What remains is
the mechanical part: apply that classification to the actual loop YAML files
in `scripts/little_loops/loops/*.yaml` — a real `scope:` for narrow loops,
and an explicit `scope: ["."]` for genuinely repo-wide loops.

This is the only child of BUG-3088 that changes runtime behavior (which paths
each built-in loop's concurrency lock covers). The lint rule that guards
against regression ([[BUG-3107]]) depends on this landing first — see
BUG-3088's "Warning-ratchet decision" for why the order is a hard dependency.

## Current Behavior

78 of the 91 built-in loop YAML files under `scripts/little_loops/loops/`
declare no `scope:` key. `FSMLoop.scope` (`schema.py:1278`) defaults to `[]`
for these, and each of the three call sites that consume it
(`run.py:373`, `_helpers.py:1552`, `concurrency.py:163-164`) falls back to
`scope = ["."]` — a repo-root lock. `_paths_overlap()`
(`concurrency.py:398-423`) treats repo-root as an ancestor of every other
path, so any two loops running concurrently where at least one is unscoped
always reports a conflict, even when their real file-write footprints never
intersect. This is silent: nothing today (no error, warning, or
`ll-loop validate` finding) surfaces the fallback.

## Expected Behavior

Each of the 78 loops declares an explicit `scope:` matching BUG-3088's
completed classification table (52 narrow scopes, 26 repo-wide
`scope: ["."]`). `grep -L "^scope:" scripts/little_loops/loops/*.yaml`
returns empty (the 12 loops under `loops/oracles/` are an explicit,
documented exclusion — see "Scope boundary" below, not part of this table).
Narrow-scoped loops stop false-conflicting with unrelated concurrent loops.

## Steps to Reproduce

1. Run `grep -L "^scope:" scripts/little_loops/loops/*.yaml | wc -l` — returns
   `78` today.
2. Start any two of those unscoped loops concurrently whose real file
   footprints don't overlap (e.g. two loops under different subdirectories).
3. Observe `LockManager.find_conflict()` reports a conflict anyway, because
   both resolved to the repo-root fallback scope `["."]`.

## Parent Issue

Decomposed from [BUG-3088](P3-BUG-3088-audit-unscoped-loops-and-warn-on-missing-scope.md):
Audit unscoped loops and warn at validate time when `scope:` is missing.

## Proposed Solution

1. For each of the 78 loops in BUG-3088's classification table, add the
   proposed `scope:` value to the loop's YAML file under
   `scripts/little_loops/loops/`.
2. After editing, verify completeness with an explicit grep:
   `grep -L "^scope:" scripts/little_loops/loops/*.yaml` should return (at or
   near) zero files. Run this as a literal, checkable step — not just
   inferred from the edit count.
3. Verify `skills/simplify-loop/reference.md`'s collapse logic still
   round-trips the newly-declared `scope:` field for at least one narrow and
   one repo-wide loop (spot-check via `ll-loop` simplify-loop path or manual
   inspection), since it already lists `scope:` as a preserved field.
4. Run the full built-in loop test suite (`scripts/tests/test_builtin_loops.py`)
   to confirm no existing assertion breaks from the added `scope:` fields.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- No scripted/mechanical YAML-field-editor exists in this codebase for loop files: a grep for `yaml.safe_load`/`yaml.dump`/`ruamel` across `scripts/little_loops/` found only *readers* (`sprint.py`, `cli/doctor.py`, `cli/logs.py`, `doc_counts.py`, `cli/harness.py`, `cli/loop/info.py`, `cli/loop/config_cmds.py`) that load loop YAML for display/introspection, never round-trip-and-write. No `ruamel.yaml` dependency is pinned in `scripts/pyproject.toml`. Confirms all 13 existing `scope:` additions were hand-written, individually-reasoned edits — e.g. `issue-discovery-triage.yaml:10-12`, `prompt-across-issues.yaml:31-34` (3-line issue-citation comment before `scope:`), `ready-to-implement-gate.yaml:11-13` and `proof-first-task.yaml:9-11` (identical 2-line comment copied across sibling edits) — not a scripted sweep.
- No prior ".issues/" precedent exists for a "apply value to N files per a completed classification table" issue shape; the closest comparable prior work is BUG-3087 (a six-loop precursor to this 78-loop sweep, already resolved/archived — its own file was not found in `.issues/` to inspect for a stated convention).

### Files to Modify

The 78 target loop YAML files under `scripts/little_loops/loops/` (full per-file
`scope:` value and rationale is BUG-3088's classification table; not repeated
here — group summary only):
- `apo-*.yaml` (5: beam, textgrad, feedback-refinement, contrastive, opro)
- `rl-*.yaml` (4: bandit, policy, coding-agent, rlhf)
- `rn-*.yaml` (6: plan, build, implement, remediate, stepwise, plan-apo — `rn-decompose.yaml` also unscoped)
- `harness-*.yaml` (4: single-shot, multi-item, plan-research-implement-report, optimize)
- `rlhf-*.yaml` / `rlhf-svg-*.yaml` (4: animated-svg, svg-generate, svg-evaluate, svg-refine)
- generator loops (10: canvas-sketch, flux-image, p5js-sketch, svg-image, vega-viz, pixi-data-viz, pixi-generative-art, html-anything, html-website, openscad-model, interactive-component, generative-art, generative-art-derived `p5js-sketch-generator.yaml` via `from:`)
- remaining 39 loops individually named in BUG-3088's table (`adopt-third-party-api.yaml`, `adversarial-redesign.yaml`, `agent-eval-improve.yaml`, `apply-research.yaml`, `assumption-firewall.yaml`, `backlog-flow-optimizer.yaml`, `brainstorm.yaml`, `cli-anything-bootstrap.yaml`, `context-health-monitor.yaml`, `cua-agent-desktop.yaml`, `dataset-curation.yaml`, `deep-research.yaml`, `deep-research-arxiv.yaml`, `eval-driven-development.yaml`, `evaluation-quality.yaml`, `examples-miner.yaml`, `fix-quality-and-tests.yaml`, `goal-cluster.yaml`, `hitl-compare.yaml`, `hitl-md.yaml`, `incremental-refactor.yaml`, `integrate-sdk.yaml`, `learning-tests-audit.yaml`, `loop-composer.yaml`, `loop-composer-adaptive.yaml`, `loop-router.yaml`, `loop-specialist-eval.yaml`, `migrate-sdk-version.yaml`, `outer-loop-eval.yaml`, `policy-refine.yaml`, `prompt-regression-test.yaml`, `rubric-refine.yaml`, `scan-and-implement.yaml`, `sft-corpus.yaml`, `spike-gate.yaml`, `sprint-build-and-validate.yaml`, `test-coverage-improvement.yaml`, `workflow-generator.yaml`, `worktree-health.yaml`)

### Dependent Files (scope consumers, unchanged by this fix but define correctness)

- `scripts/little_loops/fsm/schema.py:1278,1544` — `FSMLoop.scope` field and `from_dict()` parse (`data.get("scope", [])`)
- `scripts/little_loops/fsm/concurrency.py:35` — `resolve_scope()`; `:163-164` — `LockManager.acquire()` fallback
- `scripts/little_loops/cli/loop/run.py:373` — foreground fallback call site
- `scripts/little_loops/cli/loop/_helpers.py:1552` — background pre-flight fallback call site
- `scripts/little_loops/cli/loop/info.py:1540-1541` — declared-scope display (`cmd_show()`, the `ll-loop show`/`ll-loop s` subcommand); once the 78 loops gain `scope:`, `ll-loop show` starts printing a `scope: ...` line for all of them for the first time (the `if fsm.scope:` gate at these lines is already presence-based, so no code change is needed — this is a pure display side effect of the data change)
- `scripts/little_loops/fsm/fsm-loop-schema.json:30-36` — JSON Schema `"scope"` property (plain `array` of `string`, no validation of path existence)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fragments.py:43-63` (`_deep_merge()`) and `:156-220` (`resolve_inheritance()`) — for `from:`-inheriting loops, list-typed fields (including `scope`) are fully overridden by the child's own value, never concatenated with the parent's (`_deep_merge`: "For all other value types (str, int, bool, list, None), the override value wins outright"). This resolves the only open question raised by the `from:` relationships below: adding a classified `scope:` directly to each child loop is sufficient — no risk of an unintended parent/child scope union. `scripts/little_loops/fsm/validation/structural_rules.py:1478,1578` and `scripts/little_loops/fsm/topology.py:125-128` call `resolve_inheritance()` on every loop load/validate, so this merge behavior is exercised well before runtime.
- `from:` relationships among the 78 target loops (the issue text above names only one — `p5js-sketch-generator.yaml` — the full set is 8 parent/child pairs across 4 parents): `lib/apo-base.yaml` (fragment, not itself a target) → `apo-beam.yaml`, `apo-textgrad.yaml`, `rn-plan-apo.yaml`, `lib/apo-shape-a.yaml`; `lib/apo-shape-a.yaml` (fragment) → `apo-contrastive.yaml`, `apo-feedback-refinement.yaml`; `generative-art.yaml` → `p5js-sketch-generator.yaml`, `pixi-generative-art.yaml`; `deep-research.yaml` → `deep-research-arxiv.yaml`. Every child in this list is independently classified in BUG-3088's table and gets its own `scope:` line, so (per the override-wins behavior above) each resolves correctly regardless of edit order.

### Conventions in Force

- Loops declare `scope:` as a top-level YAML block list placed after
  `name:`/`category:`/`description:`/`initial:` and before `import:`/
  `context:`/`max_steps:` — evidence: `docs-sync.yaml:1-16`,
  `issue-refinement.yaml:1-14`, `dead-code-cleanup.yaml:1-11`.
- The majority (9 of 13) use a 2-space-indented list item (`scope:\n  - "x"`);
  a minority (`autodev.yaml:26-27`, `rn-refine.yaml:31-32`) use a 0-indent
  list (`scope:\n- "x"`). Flow-style (`scope: ["x"]`) is never used as literal
  YAML in a loop file — it appears only in prose (README tables, the BUG-3088
  classification table).
- Each existing `scope:` addition carries a preceding comment citing the
  originating issue ID and, where relevant, sibling loops sharing the same
  reasoning — evidence: `proof-first-task.yaml:8-13` ("BUG-2864 ... mirrors
  autodev.yaml / prompt-across-issues.yaml"), `ready-to-implement-gate.yaml:10-15`.
- List values mix literal repo-relative paths (`".issues/"`, `"docs/"`,
  `"scripts/"`) and `${context.<var>}` templates (`"${context.run_dir}"`,
  `"${context.plan_file}"`) freely within the same list — evidence:
  `issue-refinement.yaml:12-13`.
- No prior bulk-edit script exists for this operation; all 13 existing
  `scope:` declarations were added as individually-reasoned, hand-written
  edits (one issue-cited comment or test per loop), not a scripted sweep.

### Tests

- `scripts/tests/test_builtin_loops.py` has one `test_scope_declared` /
  `test_scope_field_uses_run_dir_template` method **per already-scoped loop**
  (10 instances: lines 1243, 2271, 2946, 4046, 7193, 7643, 9906, 10131, 10715,
  10789), each asserting `scope is not None`, `isinstance(scope, list)`, then
  per-expected-value membership. There is **no generic/parametrized test**
  asserting `scope:` presence across all built-in loops today (unlike
  `test_all_have_description_field`, `test_builtin_loops.py:100-118`, which
  does iterate the full `builtin_loops` fixture) — adding `scope:` to the 78
  target loops will not be covered by an existing assertion; the parallel
  `test_all_have_scope_field` structural test named in BUG-3088/BUG-3106 does
  not yet exist and is not part of this issue's scope (BUG-3107 territory).

### Documentation

- `docs/guides/LOOPS_GUIDE.md:786-816` — "Scope-Based Concurrency" section;
  its own example blocks already use the 2-space-indented block-list form
  matching the majority convention above.

### Scope boundary: `loops/oracles/*.yaml` not covered

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/oracles/*.yaml` currently has 12 loops with no
  `scope:` (`code-run-gate.yaml`, `enumerate-and-prove.yaml`,
  `generator-evaluator-cli.yaml`, `generator-evaluator-flux.yaml`,
  `oracle-capture-issue.yaml`, `integrate-node.yaml`,
  `generator-evaluator.yaml`, `plan-node-refine.yaml`,
  `resolve-decision.yaml`, `research-coverage.yaml`,
  `plan-research-iteration.yaml`, `verify-confidence-scores.yaml`). Verified:
  `grep -L "^scope:" scripts/little_loops/loops/*.yaml | wc -l` returns exactly
  `78` (matching this issue's count), while the same grep against
  `scripts/little_loops/loops/oracles/*.yaml` returns these 12 additional
  files — the top-level-only glob in Implementation Steps' verification
  command does not recurse into `oracles/`. Loops under `loops/oracles/` are
  runnable (not fragments, unlike `loops/lib/`), so these are real unscoped
  loops outside BUG-3088's classification table. Not in this issue's stated
  scope (the table doesn't classify them) — flag as an explicit exclusion or
  file a follow-up rather than silently treating "0 unscoped top-level loops"
  as "0 unscoped runnable loops."

### Stale reference in this issue

- BUG-3088 (and this issue's Proposed Solution step 3 / Implementation Steps
  step 3) cite `skills/simplify-loop/reference.md`'s "collapse logic" as the
  place that preserves `scope:` during flow-collapse. That file has no such
  sentence — its only `scope`-labeled content is an unrelated
  "Scope-resolution table" at line 228 (loop *file location* convention,
  `.loops/<name>.yaml` vs `scripts/little_loops/loops/<name>.yaml` — not the
  FSM `scope:` concurrency field). The actual field-preservation bullet
  (`Preserve `initial:`, `import:`, `from:`, `parameters:`, `context:`,
  `scope:`.`) is in `skills/simplify-loop/SKILL.md:219`, a different file.
  Spot-check the round-trip against `SKILL.md`'s collapse procedure, not
  `reference.md`.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types

N/A — no new data shape. `FSMLoop.scope: list[str]` (`scripts/little_loops/fsm/schema.py:1278`) already exists; this issue only populates the field's value in 78 YAML files, it does not change the type.

### Signatures

- `resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]` — in `scripts/little_loops/fsm/concurrency.py:35`; substitutes `${context.<var>}` templates in each scope path. Unaffected by this issue, but is what turns the newly-added literal/templated `scope:` values into resolved lock paths.
- `LockManager.acquire(loop_name, scope, instance_id=None, singleton=False)` — in `concurrency.py:142-200`; the fallback `if not scope: scope = ["."]` at lines 163-164 stops firing for a given loop once that loop declares a non-empty `scope:`.
- `FSMLoop.from_dict(data: dict) -> FSMLoop` — in `schema.py:1544`; parses `scope=data.get("scope", [])`, the path each edited YAML file flows through.

### Call Path

`scripts/little_loops/loops/<name>.yaml` (`scope:` now present) → `FSMLoop.from_dict()` (`schema.py:1544`) → `fsm.scope` (non-empty list) → `cmd_run()` (`cli/loop/run.py:373`) / `run_background()` (`cli/loop/_helpers.py:1552`) → `resolve_scope(fsm.scope or ["."], context)` (now uses the declared value, not the `["."]` fallback) → `LockManager.acquire()` → `find_conflict()` → `_paths_overlap()` (`concurrency.py:398-423`) — narrow scopes stop overlapping with unrelated loops' scopes.

### Decision Rules

N/A — no new decision logic. This issue adds a `scope:` YAML field with a value per BUG-3088's pre-completed classification table; it introduces no new gate, threshold, or keyword-matching rule.

## Implementation Steps

1. Apply the classification table's `scope:` value to each of the 78 loop
   YAML files (see BUG-3088 for the full per-loop table and rationale).
2. Run `grep -L "^scope:" scripts/little_loops/loops/*.yaml` and confirm the
   result is empty; this top-level-only glob does not recurse into
   `loops/oracles/`, so its 12 unscoped loops are an explicit, documented
   exclusion (see "Scope boundary: `loops/oracles/*.yaml` not covered"), not a
   false "0 unscoped runnable loops repo-wide" reading.
3. Spot-check `skills/simplify-loop/SKILL.md:219`'s collapse round-trip
   ("Preserve `initial:`, `import:`, `from:`, `parameters:`, `context:`,
   `scope:`.") for `scope:` on a narrow and a repo-wide loop —
   `skills/simplify-loop/reference.md` has no such collapse-logic sentence.
4. Run `python -m pytest scripts/tests/test_builtin_loops.py` and confirm no
   regressions.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- For the 8 `from:` parent/child pairs among the 78 target loops (see
  Integration Map's "Dependent Files" wiring-pass addition), confirm each
  child's own classified `scope:` value — not the parent's — is what
  `resolve_inheritance()` produces, since `_deep_merge()` has override-wins
  (not concatenate) semantics for list fields; a one-loop spot check (e.g.
  `apo-beam.yaml`, `p5js-sketch-generator.yaml`) via `ll-loop show` is
  sufficient given the semantics are uniform.
- Explicitly note (in the PR description or a follow-up issue) that
  `scripts/little_loops/loops/oracles/*.yaml` (12 loops) remains unscoped and
  out of this issue's stated scope — do not let step 2's top-level-only glob
  read as "0 unscoped runnable loops repo-wide."

## Impact

- **Severity**: silent, non-deterministic loss of automated work for any of
  the 78 unscoped loops today (false repo-root lock conflicts).
- **Blast radius**: 78 one-line YAML edits, each validated by the existing
  builtin-loop test suite. No code changes.

## Status

open


## Session Log
- `/ll:ready-issue` - 2026-08-08T13:05:04 - `7a558cf6-3da0-4d21-b1c7-8486851b73f3.jsonl`
- `/ll:confidence-check` - 2026-08-08T13:02:51 - `87d02130-02c8-4c87-820d-6fafc2afb02f.jsonl`
- `/ll:reconcile-issue` - 2026-08-08T13:00:58 - `01ca22b4-bb24-4ad3-ad8a-99eeae15d0ad.jsonl`
- `/ll:refine-issue` - 2026-08-08T12:56:35 - `758e4d12-8e4a-40d6-b16a-dceb58e1c137.jsonl`
- `/ll:verify-issues` - 2026-08-08T12:54:05 - `35067987-589a-4b39-80f3-f452ad17a7bc.jsonl`
- `/ll:wire-issue` - 2026-08-08T12:52:46 - `c926880d-6110-411a-81ba-0eb8950a6c12.jsonl`
- `/ll:refine-issue` - 2026-08-08T12:37:49 - `4f2ad152-7155-4294-9eea-695338306c40.jsonl`
- `/ll:issue-size-review` - 2026-08-08T12:31:14 - `252cabd4-42b7-43f3-becc-2330b53bf3d0.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **File**: `scripts/little_loops/fsm/concurrency.py` — `resolve_scope()` (line 35), `LockManager.acquire()` (lines 142-200)
- **File**: `scripts/little_loops/cli/loop/run.py` — `cmd_run()` foreground fallback (line 373)
- **File**: `scripts/little_loops/cli/loop/_helpers.py` — `run_background()` pre-flight fallback (line 1552)
- **Cause**: `FSMLoop.scope` (`scripts/little_loops/fsm/schema.py:1278`) defaults to `[]` (not `None`) when a loop YAML has no `scope:` key. Three independent call sites each apply an `or ["."]` fallback on that empty list: `run.py:373` (`resolve_scope(fsm.scope or ["."], fsm.context)`), `_helpers.py:1552` (same pattern, for the background pre-flight conflict check), and `concurrency.py:163-164` inside `LockManager.acquire()` itself (`if not scope: scope = ["."]`, currently unreachable via the two CLI call sites since they already apply the fallback before calling `acquire()`). The resolved `["."]` becomes the loop's lock-file scope, and `_paths_overlap()` (`concurrency.py:398-423`) treats a repo-root path as an ancestor of every other path — so any two loops running concurrently where at least one is unscoped always reports a conflict, even when their real file-write footprints never intersect. This is silent: no error, warning, or `ll-loop validate` finding surfaces the fallback today (the missing-`scope:` lint is BUG-3107, not yet landed). `ll-loop show` also does not show the effective (fallback-resolved) scope for an unscoped loop — only a declared `scope:` prints (`scripts/little_loops/cli/loop/info.py:1540-1541`, `cmd_show()`); that gap is BUG-3109.
