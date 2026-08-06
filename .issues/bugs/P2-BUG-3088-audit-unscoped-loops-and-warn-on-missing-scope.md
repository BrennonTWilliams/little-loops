---
id: BUG-3088
type: BUG
title: Audit unscoped loops and warn at validate time when `scope:` is missing
priority: P2
status: open
parent: BUG-3083
captured_at: '2026-08-06T16:17:02Z'
discovered_date: 2026-08-06
discovered_by: capture-issue
labels:
- fsm-concurrency
- learning-gate
- ll-auto
- loop-authoring
relates_to:
- BUG-2864
- BUG-3083
- BUG-3087
- BUG-3085
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 55
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
size: Medium
decision_needed: false
---

# BUG-3088: Audit unscoped loops and warn at validate time when `scope:` is missing

## Summary

This is the durable-fix half of BUG-3083 ("Unscoped issue-management loops
lock the whole repo, false-conflicting every narrowly-scoped loop"). Giving
individual loops real scopes ([[BUG-3087]]) fixed the six loops we knew about
then; **78 of the 91 built-in loops still declare no `scope:`** and therefore
silently acquire a repo-root lock via `cmd_run()`'s
`scope = resolve_scope(fsm.scope or ["."], fsm.context)` (`run.py:363`).

**Scope of this issue, per the Option A decision below**: the runtime `["."]`
fallback is deliberately **left in place**. What changes is (1) the built-in
loops that should be narrow get an explicit `scope:`, and (2) `ll-loop validate`
warns on a missing `scope:` so future loops don't regrow the problem. The
runtime fallback remaining is an accepted outcome, not an oversight — see
Decision Rationale.

Do not treat `--queue` as the fix. It converts a hard failure into a long
wait and is orthogonal to loops over-claiming scope (see BUG-3085).

> **Title note**: this issue was originally titled "Stop silently defaulting
> unscoped loops' lock to the repo root." That described Option B. Option A was
> selected, which does *not* stop the runtime default, so the title and Expected
> Behavior were narrowed to match what will actually ship. If the runtime
> fallback should still change, that is a new issue, not this one.

## Parent Issue

Decomposed from [BUG-3083](P2-BUG-3083-unscoped-loops-lock-whole-repo-false-gate-conflicts.md):
Unscoped issue-management loops lock the whole repo, false-conflicting every
narrowly-scoped loop.

> **Note**: BUG-3083 is already `status: done` while this child is open. Either
> the parent was closed on BUG-3087's landing alone (deliberate split — the
> durable half tracked here), or it was closed prematurely. Confirm before
> closing this issue so the epic/parent rollup is accurate.

## Root Cause

`little_loops.cli.loop.run.cmd_run` — `scope = resolve_scope(fsm.scope or ["."], fsm.context)`
(`run.py:363`). The `or ["."]` fallback means "loop author did not think
about scope" is silently promoted to "this loop owns the entire repository."
The same fallback is independently duplicated in `run_background()`
(`cli/loop/_helpers.py:1552`) and defensively again in
`LockManager.acquire()` (`fsm/concurrency.py:163-164`).

Under Option A these three sites are **not modified**. They are documented here
because they are what makes the missing-`scope:` lint worth having.

## Current Behavior

78 of the 91 built-in loops declare no `scope:` and therefore lock the repo
root at runtime (verified 2026-08-06, post-BUG-3087: `13` declare `scope:`,
`78` do not). `cmd_info`'s loop-detail display only prints a `scope:` line
when `fsm.scope` is truthy, so an unscoped loop is shown as having no scope
even though it locks the repo root — there's no visibility into the effective
behavior.

## Expected Behavior

1. Every built-in loop declares a `scope:` that reflects what it actually
   mutates. Loops that genuinely mutate the whole repo declare `scope: ["."]`
   **explicitly** — that is the opt-in form, and it satisfies the new lint.
2. `ll-loop validate` emits a WARNING when a loop declares no `scope:`, so a
   newly authored loop cannot silently reacquire a repo-root lock.

The runtime `["."]` fallback is unchanged and remains the behavior for any
loop that still omits `scope:`.

## Proposed Solution

Two deliverables, in this order. **The order is a hard dependency, not a
preference** — see Implementation Steps for why.

### Deliverable 1 (primary): audit and scope the 78 unscoped built-in loops

This is the only part of this issue that changes runtime behavior. Classify
each of the 78 as genuinely repo-wide vs. should-be-narrow, then:

- should-be-narrow → add the real `scope:`;
- genuinely repo-wide (e.g. `fix-quality-and-tests.yaml`,
  `incremental-refactor.yaml`) → add an explicit `scope: ["."]`.

Record the classification in this issue before editing. After this deliverable,
the count of loops with no `scope:` should be at or near zero.

#### Classification table (78 loops, produced by `/ll:confidence-check` 2026-08-06)

Each row was determined by reading the loop's states/actions for actual file
writes (not inferred from the filename). **52 narrow / 26 repo-wide.**
Proposed `scope:` values reuse the conventions already in use by the 13
loops that declare `scope:` today (`.issues/`, `${context.run_dir}`,
`scripts/`, `docs/`, `${context.plan_file}`) where applicable; several loops
introduce new, equally concrete conventions (`${context.prompt_file}`,
`.ll/learning-tests/`, `${context.scaffold_dir}`, etc.) documented in the
Rationale column.

| Loop | Classification | Proposed `scope:` | Rationale |
|------|----------------|--------------------|-----------|
| `adopt-third-party-api.yaml` | narrow | `["docs/"]` | Writes only `docs/docs-<domain>/*.md` (via `/scrape-docs`) and `docs/integration-<domain>.md`. |
| `adversarial-redesign.yaml` | narrow | `["${context.run_dir}"]` | All states write only under `${captured.run_dir.output}`. |
| `agent-eval-improve.yaml` | narrow | `["evals/", "${context.agent_config}"]` | `run_eval` writes to `evals/results/`; `refine_config` edits `${context.agent_config}` (default `agent.yaml`). |
| `apo-beam.yaml` | narrow | `["${context.prompt_file}"]` | `select_best` overwrites `${context.prompt_file}` with the winning variant. |
| `apo-contrastive.yaml` | narrow | `["${context.prompt_file}"]` | `score_and_select` writes the winning variant to `${context.prompt_file}`. |
| `apo-feedback-refinement.yaml` | narrow | `["${context.prompt_file}"]` | `apply_candidate`/`refine` both write to `${context.prompt_file}`. |
| `apo-opro.yaml` | narrow | `["${context.prompt_file}"]` | Only mutates `${context.prompt_file}` (default `system.md`). |
| `apo-textgrad.yaml` | narrow | `["${context.prompt_file}"]` | `apply_gradient` overwrites `${context.prompt_file}`. |
| `apply-research.yaml` | narrow | `["${context.run_dir}", ".issues/"]` | Scratch state under `run_dir`; `capture_issues` writes under `.issues/`. |
| `assumption-firewall.yaml` | narrow | `[".ll/learning-tests/"]` | `record_untestable` records untestable claims to the Learning-Test Registry. |
| `backlog-flow-optimizer.yaml` | narrow | `[".issues/"]` | All remediation states (`tradeoff-review-issues`, `issue-size-review`, ...) mutate only `.issues/`. |
| `brainstorm.yaml` | narrow | `["${context.run_dir}", ".issues/", "${context.output_path}"]` | Core states write `run_dir`; `sink_issue`/`sink_file` optionally write `.issues/` or a templated output path. |
| `canvas-sketch-generator.yaml` | narrow | `["${context.run_dir}"]` | All states write only under `${captured.run_dir.output}`. |
| `cli-anything-bootstrap.yaml` | narrow | `[".loops/cli-anything", ".loops/generated", "${context.run_dir}"]` | Writes only to `context.cache_dir`, `context.generated_dir`, and `run_dir`. |
| `context-health-monitor.yaml` | narrow | `["${context.scratch_dir}", ".loops/archive/"]` | Compacts `context.scratch_dir` (default `.loops/tmp`) and archives to `.loops/archive/`. |
| `cua-agent-desktop.yaml` | narrow | `["${context.run_dir}"]` | All file writes (snapshots, logs, diagnostics) target paths derived from `run_dir`; otherwise drives an external app, not repo files. |
| `dataset-curation.yaml` | narrow | `["${context.data_dir}", "${context.output_dir}"]` | Reads `data/raw`, writes curated output + manifest to `data/curated`; no `run_dir` used. |
| `deep-research-arxiv.yaml` | narrow | `["${context.run_dir}"]` | Inherits `deep-research`'s FSM, which writes only under `run_dir`. |
| `deep-research.yaml` | narrow | `["${context.run_dir}"]` | `init` creates `report.md`/`knowledge-base.md`/etc. all under `run_dir`. |
| `eval-driven-development.yaml` | repo-wide | `["."]` | `implement` runs `ll-auto --priority P1,P2` — implements arbitrary viable issues anywhere in the tree. |
| `evaluation-quality.yaml` | repo-wide | `["."]` | Runs `ruff check scripts/` + the full test suite, then dispatches `fix-quality-and-tests`/`issue-refinement`/`backlog-flow-optimizer` remediation. |
| `examples-miner.yaml` | narrow | `["${context.examples_file}", "${context.corpus_state_file}", "${context.prompt_file}"]` | Writes corpus to `context.examples_file` (default `examples.json`); `.issues/completed/` is read-only here. |
| `fix-quality-and-tests.yaml` | repo-wide | `["."]` | `fix-lint-format`/`fix-type-errors`/`fix-tests` edit arbitrary source files wherever failures are found; named as a repo-wide example in this issue's Summary. |
| `flux-image-generator.yaml` | narrow | `["${context.run_dir}"]` | All artifacts written under `run_dir`. |
| `general-task.yaml` | repo-wide | `["."]` | General-purpose implementation loop — executes whatever the DoD requires and runs the full project test suite; named as a repo-wide example in this issue's Summary. |
| `generative-art.yaml` | narrow | `["${context.run_dir}"]` | `brief.md`/`index.html`/`frame_*.png`/`critique.md` all written under `run_dir`. |
| `goal-cluster.yaml` | repo-wide | `["."]` | `dispatch_cluster` runs arbitrary caller-selected sub-loops (e.g. `rn-implement`, `loop-router`) in-process; parent lock must cover their combined write surface. |
| `harness-multi-item.yaml` | narrow | `[".issues/", "${context.run_dir}"]` | `execute` runs `/ll:refine-issue` (issue-file mutation only); `check_concrete` writes test output under `run_dir`. |
| `harness-optimize.yaml` | repo-wide | `["."]` | `propose`/`apply` edit whatever path(s) are named in caller-supplied `context.targets` (skills, commands, or `.claude/CLAUDE.md`). |
| `harness-plan-research-implement-report.yaml` | repo-wide | `["."]` | `implement`'s action is a free-form "implement the plan" prompt with no fixed path restriction. |
| `harness-single-shot.yaml` | repo-wide | `["."]` | `execute` runs `/ll:manage-issue` to implement the next open feature, touching arbitrary source files. |
| `hitl-compare.yaml` | narrow | `["${context.run_dir}"]` | All writes under `run_dir`. |
| `hitl-md.yaml` | narrow | `["${context.run_dir}", "hitl-md-review.html"]` | Build artifacts under `run_dir`; `finalize` additionally copies the result to `./hitl-md-review.html`. |
| `html-anything.yaml` | narrow | `["${context.run_dir}"]` | `brief.md`/`rubric.md`/`index.html`/`critique.md`/`screenshot.png` all under `run_dir`. |
| `html-website-generator.yaml` | narrow | `["${context.run_dir}"]` | Same generator/evaluator pattern, all writes under `run_dir`. |
| `incremental-refactor.yaml` | repo-wide | `["."]` | `execute_step` applies arbitrary edits repo-wide for `context.refactor_goal`; `commit_step`/`revert` run `git commit`/`git checkout -- .`; named as a repo-wide example in this issue's Summary. |
| `integrate-sdk.yaml` | narrow | `["${context.scaffold_dir}", ".ll/learning-tests/", ".loops/runs/integrate-sdk/"]` | `scaffold_integration` writes under `context.scaffold_dir` (default `src/integrations/`); diagnosis under `.loops/runs/integrate-sdk/`. |
| `interactive-component-generator.yaml` | narrow | `["${context.run_dir}"]` | All writes scoped under `run_dir`. |
| `learning-tests-audit.yaml` | narrow | `[".ll/learning-tests/", "${context.run_dir}"]` | `mark_stale_candidates` mutates the Learning-Test Registry; `build_report` writes under `run_dir`. |
| `loop-composer-adaptive.yaml` | narrow | `["${context.run_dir}"]` | All plan/execution state written under `run_dir`; dispatches sub-loops but never edits loop YAMLs itself. |
| `loop-composer.yaml` | narrow | `["${context.run_dir}"]` | Same write pattern as `loop-composer-adaptive.yaml`. |
| `loop-router.yaml` | repo-wide | `["."]` | `propose_new_loop` → `invoke_create_loop` runs `/ll:create-loop`, which can author a new loop YAML at an unpredictable path. |
| `loop-specialist-eval.yaml` | narrow | `[".loops/diagnostics/", "scripts/tests/fixtures/fsm/broken-verify-loop.yaml"]` | `execute` writes diagnosis artifacts to `.loops/diagnostics/` and patches the fixed fixture path. |
| `migrate-sdk-version.yaml` | narrow | `[".ll/learning-tests/", "${context.run_dir}"]` | `apply_update`/`reprove_next` write Learning-Test Registry records; report under `run_dir`. |
| `openscad-model-generator.yaml` | narrow | `["${context.run_dir}"]` | `brief.md`/`model.scad`/`views/*.png`/`critique.md`/`model.stl` all under `run_dir`. |
| `outer-loop-eval.yaml` | repo-wide | `["."]` | `run_sub_loop` dispatches an arbitrary caller-supplied loop by name; unpredictable target/blast radius. |
| `p5js-sketch-generator.yaml` | narrow | `["${context.run_dir}"]` | Inherits `generative-art`'s FSM (`from:`), which writes only under `run_dir`. |
| `pixi-data-viz.yaml` | narrow | `["${context.run_dir}"]` | All writes under `run_dir`. |
| `pixi-generative-art.yaml` | narrow | `["${context.run_dir}"]` | Same generator/evaluator pattern, all writes under `run_dir`. |
| `policy-refine.yaml` | narrow | `["${context.subject}"]` | All repair states target the single templated `context.subject` (default `artifact.md`) — same pattern as the existing `${context.plan_file}` convention. |
| `prompt-regression-test.yaml` | narrow | `["prompts/", ".loops/tmp/prompt-baseline.json"]` | `run_suite` reads `context.prompt_suite` (default `prompts/`); `report`/`update_baseline` write `context.baseline_file`. |
| `rl-bandit.yaml` | repo-wide | `["."]` | `explore`/`exploit` are explicit fill-in-the-blank template states with no fixed writes as shipped. |
| `rl-coding-agent.yaml` | repo-wide | `["."]` | `act`'s stated purpose covers `context.target_files:default=<all changed files>` — unbounded override. |
| `rl-policy.yaml` | repo-wide | `["."]` | Generic policy-iteration stub; `act`/`improve` are explicit placeholders with no path constraint. |
| `rl-rlhf.yaml` | repo-wide | `["."]` | Generic RLHF stub; `generate`/`refine` are placeholders for arbitrary content-generation logic. |
| `rlhf-animated-svg.yaml` | narrow | `["${context.run_dir}"]` | All states read/write under `run_dir`; delegates work to the `rlhf-svg-*` loops via `with: run_dir`. |
| `rlhf-svg-evaluate.yaml` | narrow | `["${context.run_dir}"]` | Context declares `run_dir` as required; all writes derive from it. |
| `rlhf-svg-generate.yaml` | narrow | `["${context.run_dir}"]` | Produces `output.html` in `run_dir`; no other path touched. |
| `rlhf-svg-refine.yaml` | narrow | `["${context.run_dir}"]` | Refinement pipeline operates entirely on artifacts under `run_dir`. |
| `rn-build.yaml` | repo-wide | `["."]` | Capstone pipeline: commits design docs, scopes a whole EPIC, and dispatches `rn-implement`, which edits arbitrary source. |
| `rn-decompose.yaml` | narrow | `["${context.run_dir}", ".issues/"]` | Shell states write only `run_dir`-derived scratch files; `finalize_parent` mutates `.issues/` via `ll-issues finalize-decomposition`. |
| `rn-implement.yaml` | repo-wide | `["."]` | Queue orchestrator delegating per-issue implementation to `rn-remediate` (runs `ll-auto --only`) — target varies per issue. |
| `rn-plan-apo.yaml` | narrow | `["${context.run_dir}", ".ll/prompts/"]` | `run_planner` writes under `run_dir`; `apply_gradient` overwrites `context.plan_prompt_file` (default `.ll/prompts/rn-plan-planning.md`). |
| `rn-plan.yaml` | narrow | `["${context.run_dir}", ".ll/prompts/"]` | `init` writes plan/rubric/research files under `run_dir`; seeds the same `.ll/prompts/` file as `rn-plan-apo.yaml`. |
| `rn-remediate.yaml` | repo-wide | `["."]` | `implement` runs `ll-auto --only "$ID"` — full automated issue implementation across arbitrary source files. |
| `rn-stepwise.yaml` | repo-wide | `["."]` | Thin entry point fully delegating to `rn-refine` (`stepwise: 1`), whose `implement_leaf` writes code anywhere the decomposed plan targets. |
| `rubric-refine.yaml` | repo-wide | `["."]` | `light_repair`/`deep_repair` edit `context.subject`, a caller-supplied path/description with no fixed directory. |
| `scan-and-implement.yaml` | repo-wide | `["."]` | `discover` loops into `issue-discovery-triage`; `implement` loops into `autodev`, implementing discovered issues across arbitrary source. |
| `sft-corpus.yaml` | narrow | `["data/", "${context.run_dir}", "sft-corpus.last_harvested"]` | Writes under `data_dir`/`output_dir` (both under `data/`), scratch under `run_dir`, plus a repo-root harvest sentinel file. |
| `spike-gate.yaml` | repo-wide | `["."]` | `run_impl` delegates to `loop: "${context.impl_loop}"` (default `general-task`) — caller-parameterized, unbounded by design. |
| `sprint-build-and-validate.yaml` | repo-wide | `["."]` | Beyond `.sprints/`/`.issues/`, `run_sprint` executes `ll-sprint run`, implementing the sprint's issues across arbitrary source in parallel waves. |
| `sprint-refine-and-implement.yaml` | repo-wide | `["."]` | `delegate` loops into `auto-refine-and-implement` to implement an entire sprint/EPIC's issues. |
| `svg-image-generator.yaml` | narrow | `["${context.run_dir}"]` | All writes under `run_dir`. |
| `svg-textgrad.yaml` | narrow | `["${context.run_dir}"]` | All writes under `run_dir`. |
| `test-coverage-improvement.yaml` | repo-wide | `["."]` | `write_tests`/`fix_tests` target arbitrary source paths wherever a coverage gap or exposed bug lives. |
| `vega-viz.yaml` | narrow | `["${context.run_dir}"]` | All generated/scored artifacts under `run_dir`; `data_path` is read-only. |
| `workflow-generator.yaml` | narrow | `["${context.run_dir}", "${context.loops_dir}"]` | Lowering-pass artifacts under `run_dir`; `promote` (gated behind `auto_promote`) copies the result into `context.loops_dir` (default `.ll/loops`). |
| `worktree-health.yaml` | repo-wide | `["."]` | `cleanup_worktrees`/`prune_branches` mutate shared `.git` worktree/branch state at the repo root, no fixed subdirectory. |

### Deliverable 2 (regression guard): the missing-`scope:` lint

`ll-loop validate` warns when a loop declares no `scope:` (mirrors the
MR-1..MR-14 lint surface). Follow the shape of
`_validate_input_key_without_guard` (`fsm/validation/structural_rules.py:1195-1217`)
— single-condition early-return, one
`ValidationError(severity=ValidationSeverity.WARNING)`, actionable message.
The message must name `scope: ["."]` as the explicit opt-in for repo-wide
loops, otherwise the remedy is undefined and the rule reads as un-silenceable.

### Warning-ratchet decision (must be made before implementing)

`scripts/tests/test_builtin_loops.py:13293` (`_collect_findings` /
`test_deterministic_warning_categories_do_not_regrow`) ratchets builtin-loop
WARNINGs by category. Decide explicitly:

- **Does the new no-scope rule join a ratcheted category?** If yes, and
  Deliverable 1 has not landed, it introduces 78 findings at once and either
  trips the ratchet or requires a 78-entry allowlist.
- **Recommended**: land Deliverable 1 first so the finding count is ~0, then add
  the rule *and* enroll it in the ratchet — the ratchet then does exactly the
  regression-guarding job this issue wants, with no allowlist.

Independently: with 78 loops unscoped, shipping the lint first also floods
`ll-loop validate`'s plain-text output for anyone running it today.

### Not applicable under Option A

The following were scoped against Option B and are **out of scope** unless the
runtime fallback is revisited in a future issue:

- Changing the fallback at `run.py:363`, `_helpers.py:1552`, or
  `concurrency.py:163-164`.
- The four break-risk tests that assert the current `["."]` fallback
  (`test_cli_loop_background.py::test_scope_conflict_returns_1` /
  `test_no_lock_bypasses_scope_conflict` / `test_queue_bypasses_preflight_check`;
  `test_concurrency.py::TestLockManager::test_empty_scope_defaults_to_project`).
  None of these break under Option A.
- `cli/sprint/run.py::_run_learning_gate_preflight()` and
  `parallel/worker_pool.py::_run_per_worktree_proof_first_gate()` comment
  additions.

`cli/loop/info.py`'s effective-scope display is **optional** under Option A —
it is a real visibility gap (an unscoped loop shows no scope while locking the
repo root), but it is independent of both deliverables. Do it or split it out;
do not let it hold up Deliverable 1.

### Decision Rationale

_Added by `/ll:decide-issue`:_

**Selected: Option A — lint warning.** `ll-loop validate` warns when a loop
declares no `scope:`, following the exact shape of
`_validate_input_key_without_guard` (`fsm/validation/structural_rules.py:1195-1217`):
single-condition early-return guard, one
`ValidationError(severity=ValidationSeverity.WARNING)`, wired into
`validate_fsm()` and exported from `fsm/validation/__init__.py`'s `__all__`.

**Reasoning**: Option A reuses an existing, proven validation pattern with no
new abstraction and carries zero runtime risk — codebase evidence confirmed
`ll-loop validate` never gates `ll-loop run` (neither `run.py`'s foreground
path nor `_helpers.py`'s `run_background()` calls `validate_fsm`/`cmd_validate`),
so adding the rule cannot regress any of the three fallback sites or any
currently-passing test. Option B, by contrast, carries real, evidenced
breakage risk: the issue's own named repo-wide loops
(`fix-quality-and-tests.yaml`, `incremental-refactor.yaml`) declare no
`scope:` today and would silently narrow to `run_dir` under a changed default
absent the not-yet-completed audit (Deliverable 1); evidence
also found a template-resolution reliability gap where `run.py` injects
`fsm.context["run_dir"]` before calling `resolve_scope()` but
`_helpers.py`'s `run_background()` does not, so its pre-flight scope check
could diverge from the actual lock acquired by the spawned child. Since the
loop audit must happen regardless of which option is chosen — and will add
explicit `scope:` declarations to loops that need narrowing — Option A's lint
then guards against future regressions without taking on Option B's
transitional breakage window.

**Accepted consequence**: the same evidence that makes Option A zero-risk
(`ll-loop validate` does not gate `ll-loop run`) also means Option A has **zero
runtime effect**. The `["."]` fallback survives for any loop that still omits
`scope:`. Option A's protection is entirely at authoring time, and its value is
therefore conditional on Deliverable 1 actually landing. This is why the audit
is now the primary deliverable rather than a prerequisite bullet.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:-----------:|:-----------:|:----:|:-----:|
| A — lint warning | 3 | 3 | 3 | 3 | **12/12** |
| B — narrow default | 1 | 1 | 1 | 0 | 3/12 |

**Key evidence**:
- Option A: `_validate_input_key_without_guard` sibling pattern is a ~20-25
  line copy-shape change; grep confirmed zero existing rules touch
  `fsm.scope`, so this is net-new logic but reuses all scaffolding
  (`ValidationError`, `ValidationSeverity`, `validate_fsm()` wiring, `__all__`
  export).
- Option B: only 13 of 91 built-in loop YAMLs currently declare `scope:` at
  all; `resolve_scope()` leaves unresolved `${context.var}` templates as
  literal strings, so `run_background()`'s pre-flight check (which never
  injects `run_dir` into its context) would resolve `${context.run_dir}`
  literally rather than to a real path — a divergence unique to Option B that
  the current `["."]` fallback does not have.

## Integration Map

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/loops/*.yaml` | 78 loops with no `scope:` | **Deliverable 1** — add a real `scope:`, or explicit `scope: ["."]` for genuinely repo-wide loops |
| `scripts/little_loops/fsm/validation/structural_rules.py` | new rule, pattern of `_validate_input_key_without_guard` (lines 1195-1217) | **Deliverable 2** — no-scope WARNING lint rule |
| `scripts/little_loops/fsm/validation/__init__.py` | `__all__` | Export the new rule |
| `scripts/tests/test_builtin_loops.py` | `_collect_findings` / `test_deterministic_warning_categories_do_not_regrow` (line 13293) | Enroll the new rule in the warning ratchet (see Warning-ratchet decision) |
| `scripts/little_loops/cli/loop/config_cmds.py` | `cmd_validate()`, line 12 | The `ll-loop validate` CLI dispatch: calls `load_and_validate()` -> `validate_fsm()` and prints/JSON-serializes returned warnings. The new WARNING surfaces here in both the `--json` `violations` list and the plain-text `for w in warnings: print(f"  ⚠ {w}")` loop — verify, no code change expected |
| `scripts/little_loops/cli/loop/info.py` | lines 1540-1541 | **Optional** — reflect the resolved effective scope, not just the declared one |

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` (line 12) is the `ll-loop validate` entry point; must reflect the new WARNING. [Agent 1 finding, confirmed via direct read]
- `scripts/tests/test_cli_loop_queue.py` — mocks `little_loops.fsm.concurrency.LockManager` and exercises `cmd_run()`'s `--queue` path (e.g. `test_exits_when_scope_never_becomes_available` line 116, the no-`--queue` scope-conflict test at line 140, and further `LockManager` mocks at lines 568/598/626/650). Documented as a fourth call path through the `cmd_run()` fallback; **not break-risk under Option A** (the fallback is unchanged). [Agent 1 + Agent 3 findings, confirmed via grep]

### Documentation

- `docs/guides/LOOPS_GUIDE.md:786-816,848-849` — "Scope-Based Concurrency"
  section documents `scope:` mechanics but has no mention of the current
  `["."]` default-when-absent behavior; the "Notes" bullet at line 849
  ("Loops with non-overlapping scopes run concurrently") is inaccurate for
  any unscoped loop today. Document the fallback explicitly and point at
  `scope: ["."]` as the way to declare repo-wide intent.
- `docs/development/TROUBLESHOOTING.md:812-827,1285` — existing
  "Scope conflict" troubleshooting entries describe stale-lock symptoms
  only, not the false-conflict-from-unscoped-loop mechanism.
- `docs/reference/CLI.md:789-812` — enumerates every `ll-loop validate`
  structural/meta-loop lint rule in a fixed format (severity, trigger,
  rationale, suppression flag); add the new no-scope WARNING rule here in the
  same format.
- `docs/reference/API.md:5179,6162-6207` — mirrors `FSMLoop.scope` field
  docstring and the `LockManager`/`resolve_scope` reference block. No change
  expected under Option A (the fallback's shape is unchanged); listed so a
  reviewer can confirm that.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/reference.md:566-575,631` — the primary loop-authoring
  doc for the `scope` field, documenting the exact behavior at issue: line 575
  states "An empty `scope` (or omitting it) is treated as the whole project — it
  will conflict with any other scoped loop," and line 631 tells authors "Most
  users can omit this field... Single-loop use cases do not require scope
  declaration." Line 575 is accurate and should stay; **line 631's advice
  directly contradicts the new lint and must be rewritten** to tell authors to
  always declare `scope:`, using `["."]` for genuinely repo-wide loops. [Agent 2
  finding, confirmed via direct read]
- `skills/create-loop/loop-types.md:986` (reference table: `scope | list[str] |
  *(entire repo)* | ...`) and inline YAML-template comments at lines 159, 274,
  388, 498 (`# scope: ["src/"]  # Optional: declare paths...`) — reinforces the
  same "omit by default" authoring pattern. Un-comment the `scope:` line in the
  four templates and drop "Optional" from the comment, so scaffolded loops start
  lint-clean. [Agent 2 finding, confirmed via direct read]

### Tests

- `scripts/tests/test_fsm_validation_structural.py::TestRequiredInputsValidation`
  (line 1539) — pattern to follow for the new rule: `_make_fsm()` helper,
  direct-call trigger/non-trigger tests, plus `..._wired_into_validate_fsm`
  variants asserting dispatch from `validate_fsm()`. Include a non-trigger case
  for `scope: ["."]` specifically, pinning that explicit repo-wide declaration
  satisfies the rule.
- `scripts/tests/test_builtin_loops.py:13293` — after Deliverable 1, the ratchet
  should show ~0 no-scope findings. If any loop is intentionally left unscoped,
  it needs an allowlist entry with a stated reason.
- **New test gap (optional, tied to the optional `info.py` change)**: no test
  asserts on `cli/loop/info.py:1540-1541`'s scope display
  (`if fsm.scope: config_parts.append(...)`). Add coverage only if the `info.py`
  update is done. [Agent 3 finding]

_Superseded by the Option A decision_: the previously-listed break-risk tests
(`test_cli_loop_background.py` ×3, `test_concurrency.py::test_empty_scope_defaults_to_project`)
and the proposed `cmd_run()`-foreground-fallback test all target the runtime
fallback, which Option A does not change. Retained in git history; see "Not
applicable under Option A" above.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Types
- `FSMLoop.scope: list[str] = field(default_factory=list)` (`fsm/schema.py:1278`) — not `Optional`; defaults to `[]`, not `None`. The new lint rule must therefore test `if fsm.scope:` (empty-list falsy), not `is None`.
- `resolve_scope() -> list[str]` — pure function; applies no fallback logic of its own.
- `LockManager.acquire()`'s `scope: list[str]` parameter — non-`Optional`.
- `ScopeLock.scope: list[str]` (`fsm/concurrency.py:91`) — dataclass field, no default, always populated at construction.

### Signatures
- `resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]` (`fsm/concurrency.py:35`) — resolves `${context.<var>}` templates via `_CONTEXT_VAR_RE`; unresolved templates pass through literally.
- `LockManager.acquire(self, loop_name: str, scope: list[str], instance_id: str | None = None, *, singleton: bool = False) -> bool` (`fsm/concurrency.py:142-149`). Its own fallback sits at `concurrency.py:163-164`: `if not scope: scope = ["."]`, followed by `scope = [self._normalize_path(p) for p in scope]` (line 165). This runs *after* both CLI-layer fallbacks apply, so for the two known callers it is currently a dead/defensive branch — but it is independently reachable by any future direct caller of `acquire()` that passes an empty/falsy scope.
- `cmd_run()` (`cli/loop/run.py:92`): `lock_manager = LockManager(loops_dir)` (line 362) -> `scope = resolve_scope(fsm.scope or ["."], fsm.context)` (line 363, fallback site #1) -> `lock_manager.acquire(fsm.name, scope, instance_id=instance_id, singleton=fsm.singleton)` (line 371).
- `run_background()` (`cli/loop/_helpers.py:1510`): `lock_manager = LockManager(loops_dir)` (line 1544) -> `scope_context` merged from `fsm.context` plus `--context` CLI overrides (lines 1548-1551) -> `scope = resolve_scope(fsm.scope or ["."], scope_context)` (line 1552, fallback site #2) -> `lock_manager.find_conflict(scope, caller_loop_name=fsm.name, caller_singleton=fsm.singleton)` (line 1553) — a pre-flight check only; this path never calls `acquire()` in the parent process.
- The new rule's pattern reference, `_validate_input_key_without_guard(fsm: FSMLoop) -> list[ValidationError]` (`fsm/validation/structural_rules.py:1195-1217`): one or more early-return `if ...: return []` guards, then a single-element list return constructing `ValidationError(message=..., path=..., severity=ValidationSeverity.WARNING)`. Wired into `validate_fsm()` via `errors.extend(...)` at `structural_rules.py:1063`, re-exported from `fsm/validation/__init__.py:138,231` (`__all__`). `ValidationError` is a dataclass (`fsm/validation/_base.py:22-34`): `message: str`, `path: str | None = None`, `severity: ValidationSeverity = ValidationSeverity.ERROR`; `ValidationSeverity` is an `Enum` with `ERROR`/`WARNING` members (`_base.py:15-19`).

### Call Path
- Foreground: `main_loop()` (`cli/loop/__init__.py:20`) -> `cmd_run(args.loop, args, loops_dir, logger)` (`__init__.py:1027`) -> `cmd_run()` loads/validates via `load_and_validate(path)` (`run.py:116`) -> (no `--background`, checked at `run.py:333`) -> `run.py:362-371` (fallback site #1, then `LockManager.acquire()` whose own internal fallback at `concurrency.py:163-164` is a no-op here since site #1 already populated `["."]`).
- Background (`--background`): `cmd_run()` detects `args.background` at `run.py:333` and returns `run_background(...)` (`run.py:340`) *before* reaching `run.py:362-371` — fallback site #1 is skipped in the parent process for this branch. `run_background()` (`_helpers.py:1510`) independently loads the FSM via `load_loop()` (`_helpers.py:1539`), builds its own `LockManager` (line 1544), and evaluates fallback site #2 at `_helpers.py:1552`, then only pre-flight-checks via `find_conflict()` (line 1553) — no `acquire()` call in the parent. If no conflict, it re-execs a detached child process (`_helpers.py:1570-1665`, `subprocess.Popen(..., start_new_session=True)`) with `--foreground-internal`, which re-enters `main_loop()` -> `cmd_run()` from scratch and follows the foreground path above. So a single `--background` run evaluates all three fallback sites: #2 once in the parent (pre-flight only), then #1 and #3 in the child (actual lock acquisition).
- Lint path (unrelated to the above, and that is the point): `ll-loop validate` -> `cmd_validate()` (`cli/loop/config_cmds.py:12`) -> `load_and_validate()` -> `validate_fsm()`. Neither `cmd_run()` nor `run_background()` is on this path, which is why the new rule cannot affect a running loop.

### Decision Rules
- **A loop satisfies the new rule iff `fsm.scope` is non-empty.** `scope: ["."]` is the explicit repo-wide declaration and passes; omitting `scope:` fails with a WARNING. There is no separate "repo-wide is allowed" carve-out — making repo-wide intent explicit *is* the point of the rule.

## Implementation Steps

1. **Deliverable 1** — Audit the 78 `scope:`-less loops and classify each as
   genuinely repo-wide vs. should-be-narrow. Record the classification in this
   issue before editing.
2. **Deliverable 1** — Apply the classification: real `scope:` for narrow loops,
   explicit `scope: ["."]` for repo-wide ones.
3. Decide the warning-ratchet question (see Proposed Solution). Recommended:
   enroll the new rule in the ratchet, which is only viable after step 2.
4. **Deliverable 2** — Add the no-scope WARNING rule in
   `fsm/validation/structural_rules.py`, wire into `validate_fsm()`, export from
   `fsm/validation/__init__.py`'s `__all__`, and add
   `test_fsm_validation_structural.py` coverage (trigger, non-trigger,
   `scope: ["."]` non-trigger, wired-into-`validate_fsm`).
5. Verify `cmd_validate()` surfaces the WARNING in both plain-text and `--json`
   output.
6. Update authoring docs so scaffolded loops start lint-clean:
   `skills/create-loop/reference.md:631`, `skills/create-loop/loop-types.md:986`
   and the four commented `scope:` template lines (159/274/388/498).
7. Update `LOOPS_GUIDE.md`, `TROUBLESHOOTING.md`, and `CLI.md`.
8. **Optional / splittable** — `cli/loop/info.py`'s effective-scope display plus
   a test for it.

## Impact

- **Severity**: silent, non-deterministic loss of automated work for any
  unscoped loop. Deliverable 1 removes this for the 78 known loops; Deliverable 2
  prevents it regrowing.
- **Blast radius**: Deliverable 1 touches 78 loop YAMLs but each edit is a
  one-line declaration validated by the existing builtin-loop test suite.
  Deliverable 2 is a ~25-line lint rule plus tests. No runtime code paths change.
- **Residual risk (accepted)**: the `["."]` fallback remains at all three sites.
  A loop authored outside `scripts/little_loops/loops/` that omits `scope:` and
  is never run through `ll-loop validate` still locks the repo root silently.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM concurrency / scope-lock design |
| `.claude/CLAUDE.md` § Loop Authoring | Where a `scope:` authoring rule would live |

## Status

open


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-06_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 45/100 → LOW

### Outcome Risk Factors
- Deliverable 1 (the 78-loop audit) is not yet enumerated in the issue — no
  per-file classification table exists, so the change surface is still an
  unbounded sweep by the rubric's own definition. Each loop needs a judgment
  call about what it actually mutates, and a wrong narrow scope introduces a
  *new* failure mode (a loop that can't lock what it writes) rather than the
  current false-conflict. Mitigate by producing the classification table
  first (per Implementation Step 1) and verifying each entry against the
  loop's actual write targets before applying `scope:`, not by inferring from
  the loop name alone.
- The 78 YAML edits plus the lint rule, its tests, the ratchet enrollment, and
  4 reference/skill docs add up to 16+ distinct change sites (Criterion A
  Breadth: 0/12), even though each individual edit is mechanical once
  classified (Depth: Local, 9/13 — the audit judgment call, not the edit
  itself, is what keeps this from being pure mechanical substitution).
  Mitigate by landing and verifying Deliverable 1 in batches against
  `test_builtin_loops.py`'s ratchet rather than as one large sweep.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-06_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 55/100 → LOW

### Outcome Risk Factors
- The 78-loop audit plus the lint rule, its tests, ratchet enrollment, and
  4+ reference/skill docs remain 16+ distinct change sites (Criterion A
  Breadth: 0/12); per-site depth is Local (9/13) since the audit judgment
  call — not the one-line `scope:` edit itself — is what keeps this from
  pure mechanical substitution. Mitigate by landing Deliverable 1 in
  batches against `test_builtin_loops.py`'s ratchet rather than as one
  large sweep.
- The classification table (78 rows) is now fully enumerated in this issue,
  resolving the prior run's "not yet enumerated" risk — but no explicit
  verification grep (e.g. `grep -L "^scope:" scripts/little_loops/loops/*.yaml`)
  or automated completeness test exists yet (Criterion D: 10/25, "sites
  enumerated, no verification command"). The ratchet enrollment planned for
  Deliverable 2 will supply that automated check once it lands, but only
  after Deliverable 1 is applied — add the verification grep to the issue
  or Implementation Steps so completeness is checkable before Deliverable 2
  ships.

## Session Log
- `/ll:confidence-check` - 2026-08-06T20:12:06 - `2295520d-0eb9-4e41-987f-c967b29af520.jsonl`
- `/ll:confidence-check` - 2026-08-06T20:06:54 - `b2fe9345-7f70-473b-93a8-546c18ea8b20.jsonl`
- `/ll:confidence-check` - 2026-08-06T19:57:14 - `b2fe9345-7f70-473b-93a8-546c18ea8b20.jsonl`
- `/ll:decide-issue` - 2026-08-06T19:42:24 - `911d93c2-f8de-430f-b4cb-94af701d0b8d.jsonl`
- `/ll:decide-issue` - 2026-08-06T19:40:41 - `f93a879a-a567-4f26-94f8-118ca1876f77.jsonl`
- `/ll:decide-issue` - 2026-08-06T19:36:41 - `6539e50d-3e51-42e1-bbc0-e1420a206a6f.jsonl`
- `/ll:confidence-check` - 2026-08-06T19:29:41 - `4a168bcb-93b0-4553-9a0f-b24e921a51b9.jsonl`
- `/ll:verify-issues` - 2026-08-06T19:27:20 - `c54728e6-430a-4402-a5f7-e4b98e685fdf.jsonl`
- `/ll:wire-issue` - 2026-08-06T19:25:48 - `0ab6d6dc-88e6-4b36-8faa-d04b2587178f.jsonl`
- `/ll:refine-issue` - 2026-08-06T19:19:39 - `babf35ec-8de3-454b-8555-f68113d877be.jsonl`
- `/ll:issue-size-review` - 2026-08-06T16:59:24 - `23212449-a121-4dca-9bc5-bc0a0164c75f.jsonl`
