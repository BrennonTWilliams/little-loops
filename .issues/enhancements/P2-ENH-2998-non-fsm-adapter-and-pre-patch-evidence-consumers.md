---
id: ENH-2998
title: Non-FSM adapter and pre-patch evidence consumers
type: ENH
priority: P2
status: open
discovered_date: 2026-08-02
epic: EPIC-2856
parent: ENH-2853
blocked_by:
- ENH-2997
labels:
- rework
- verification
testable: true
size: Large
---

# ENH-2998: Non-FSM adapter and pre-patch evidence consumers

## Summary

Give the pre-patch check coverage on the non-FSM orchestration paths
(`ll-auto`, `ll-parallel`) via an adapter in `work_verification.py`, and make
the evidence readable where humans and hand-run tooling look for it —
`cli/harness.py` and `skills/verify-issue-loop/`.

Both consumers read the persisted bundle; neither re-implements the check. The
adapter adds no check logic either, but it is not a one-liner: it requires a
`verify_work_was_done()` signature change and new `GitLock` plumbing (§ Design
Notes → "The adapter is not thin").

## Parent Issue

Decomposed from ENH-2853: Deterministic pre-patch test-failure check in
verification loops. Covers § Proposed Change step 5 (surfacing) and step 7, and
Integration Map Layer 3 plus the `work_verification.py` half of Layer 2.

## Current Behavior

After ENH-3142 (the core, shipped) and ENH-2997 (the FSM host), the check runs
only inside FSM loops. `ll-auto` and
`ll-parallel` reach verification through `work_verification.verify_work_was_done`,
which has no knowledge of it. `ll-harness` reports only a single-check
`HarnessEvalOutcome`, and `/ll:verify-issue-loop` generates only LLM-judged
states.

## Expected Behavior

`work_verification.py` resolves the base state and calls the same
`run_prepatch_check()` core, mirroring how ENH-2854's tamper guard reaches
`issue_manager.py` and `parallel/worker_pool.py`. `cli/harness.py` surfaces the
persisted `PrePatchEvidence` alongside its existing outcome by *reading* the
bundle. `skills/verify-issue-loop/SKILL.md` and `templates.md` document the
deterministic check and when it applies.

## Motivation

ENH-2853's original scope deferred `ll-auto`/`ll-parallel` coverage to a
follow-up issue, purely because the then-prescribed oracle-state host couldn't
reach those callers. ENH-2997's executor-hosted placement inherits ENH-2854's
non-FSM adapter shape, so the path is now a thin wrapper over the same core
rather than a second implementation — which is why that deferral was reversed.

The consumers matter for a different reason: an evidence bundle nobody reads is
not auditable. Surfacing it in `ll-harness` means the check can be inspected
without re-running it.

## Proposed Change

1. **Non-FSM adapter** — add pre-patch invocation to
   `scripts/little_loops/work_verification.py`, resolving `(base_sha, base_dirty)`
   the same way ENH-2997's FSM host does and calling `run_prepatch_check()`.
   Wire it from `issue_manager.py` and `parallel/worker_pool.py`, mirroring
   ENH-2854's existing wiring in those files. **This is not a one-line
   addition** — see § Design Notes → "The adapter is not thin": the shipped
   core needs a `GitLock`, a `worktree_base`, and a `base_branch` that
   `verify_work_was_done()` does not currently have, and its `-> bool` return
   cannot carry a `PrePatchEvidence` out.
2. **Harness consumer** — `cli/harness.py` reads the persisted bundle and reports
   it alongside `HarnessEvalOutcome` in `_evaluate_and_report()`. It does **not**
   call `run_prepatch_check()` itself. The bundle is an additive key set in
   `_evaluate_and_report()`'s JSON branch; mention it in the `--help` epilog.
   Re-locate all four sites by name at implementation time — the line numbers
   this issue originally cited are stale (see § Design Notes). **It reads the
   `.ll/history.db` row, not the run-dir file**: `ll-harness` is hand-run and
   has no `run_dir`, so the database is the only surface it can discover by
   issue ID. ENH-2997 writes both.
3. **Skill documentation** — `skills/verify-issue-loop/SKILL.md` (~L150-165)
   documents only `llm_structured` verify/probe states today. Add a bullet
   describing when the deterministic pre-patch check applies. The
   state-template example goes in `scripts/little_loops/cli/loop/scaffold_verify.py`
   (the generator), **not** `templates.md` — that file is now a stub redirecting
   to `ll-loop scaffold-verify` per FEAT-2948 and holds no hand-written
   templates to extend. This is additive documentation,
   not editing a prohibition: the "no deterministic state type" boundary text the
   original wiring pass cited at SKILL.md lines 211-219 no longer exists after
   the skill's restructuring (verified 2026-07-29; the skill is now 212 lines with
   no `check_invariants`/`check_stall`/`check_concrete` mention).

## Design Notes

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-08-02):_

- **`cli/harness.py` line citations in this issue are stale.** Current
  positions: `HarnessEvalOutcome` is a 3-field dataclass (`passed`, `verdict`,
  `eval_result`) at `harness.py:295-300`; `_evaluate_and_report()` is
  `harness.py:303-369`; its JSON-print branch is `harness.py:335-346`; `_report()`
  (error/timeout-only path, no evaluation outcome flows through it) is
  `harness.py:372-391`; the `--help` epilog is elsewhere in the file — re-locate
  by name rather than by the line numbers cited above/in Integration Map at
  implementation time.
- **Non-FSM baseline resolution today is git-local, not DB-backed.** Neither
  `issue_manager.py` (`_baseline_sha` at `:1022-1027`, a `git rev-parse HEAD`
  captured before Phase 2) nor `worker_pool.py` (`tamper_baseline_sha` at
  `:591`, `self._get_worktree_head_sha(worktree_path)` at `:1639`) currently
  calls `history_reader.read_base_sha()`. `read_base_sha(issue_id, *, run_id=None,
  db=DEFAULT_DB_PATH) -> str | None` exists at `history_reader.py:1816-1821` and
  never raises. ~~No `base_dirty` reader exists yet alongside it~~ — **stale as
  of 2026-08-12**: `read_base_dirty(issue_id, *, run_id=None, db=DEFAULT_DB_PATH)
  -> bool | None` shipped with ENH-3142 (`history_reader.py:1872-1918`), same
  never-raises contract, int→bool converted. Both readers are ready to use
  as-is; only the *call* from the non-FSM path is new.
- **The established FSM-vs-non-FSM split for this check's sibling (tamper
  guard) is: FSM hosts its own adapter directly; the two non-FSM orchestrators
  share one.** `fsm/executor.py:1336`'s `_check_tamper_guard` calls
  `test_tamper_guard.run_tamper_guard()` directly, bypassing
  `work_verification.py` entirely, while `issue_manager.py` and
  `worker_pool.py` both go through the single shared
  `work_verification.verify_work_was_done()` entry point (never the private
  `_run_non_fsm_tamper_guard()` helper at `work_verification.py:63` directly).
  This confirms the shape ENH-2997 (FSM host) and this issue (shared non-FSM
  adapter) already assume, and gives a concrete file (`work_verification.py:146-199`)
  showing where the `config is not None` gate conditionally invokes the
  adapter — the same conditional-gate shape a prepatch-check call would need.
- **Lazy-import discipline applies to any new `prepatch_check` import.**
  `_run_non_fsm_tamper_guard()` (`work_verification.py:96-104`) and
  `worker_pool.py:604-610` both import `test_tamper_guard` symbols
  function-locally, not at module top level, specifically to avoid a
  `test_tamper_guard -> config.core -> parallel.types -> parallel ->
  worker_pool` circular import (documented inline at `worker_pool.py:604-606`).
  Whether the new `prepatch_check` import needs the same treatment depends on
  its own dependency chain once ENH-2991 lands.
- **`skills/verify-issue-loop/templates.md` no longer holds hand-written
  templates.** Per FEAT-2948, the file is now a stub redirecting to
  `ll-loop scaffold-verify` (`scripts/little_loops/cli/loop/scaffold_verify.py`)
  — its own text states "there is nothing left here for an LLM to fill in or
  chain by hand." The Proposed Change/Integration Map's plan to add "a
  state-template example" to `templates.md` needs to target
  `scaffold_verify.py` instead (or `SKILL.md` only) — the concrete precedent
  for a deterministic-vs-`llm_structured` state pairing already exists in that
  file's generated output: the adversarial mode's `count_probes` state uses
  `EvaluateConfig(type="output_numeric", operator="ge", target=3)` chained
  after three `llm_structured` probe states (`scaffold_verify.py:130-145`).
  `skills/create-loop/loop-types.md:145-151` and `:777-808` are the codebase's
  existing convention for documenting an evaluator-type mapping in prose, if
  `SKILL.md`'s bullet follows that shape.
- **No conditional-JSON-key precedent exists in `cli/harness.py` itself.**
  Its JSON branch (`harness.py:335-346`) builds one fixed-key dict; the nearest
  precedent for an *optional* key in a JSON payload is `fsm/executor.py`'s
  `action_complete` event (`:1879-1917`), which does `if <condition>:
  payload["<key>"] = <value>` per optional field with an inline comment noting
  "additive field — existing consumers ... are unaffected" (ENH-2469 pattern).
- ~~**Off-switch shape for the new check is a contested convention**~~ —
  **settled as of ENH-3142 (2026-08-12).** The check ships a `BRConfig`-layer
  off-switch: `config.prepatch_check.enabled` (`config/features.py:1062-1076`,
  default **`False`**), and the core itself honors it by returning
  `PrePatchEvidence(verdict="skipped", skipped_reason=...)` rather than
  omitting the section (`prepatch_check.py:407-414`). The adapter **must not
  add a second off-switch** — it reuses this one, and the default means the
  non-FSM path is inert until a project opts in.
- **Shared skip-flag precedent orders config-gate before override-flag.** The
  learning-gate pattern this issue's Integration Map cites checks
  `if not <config>.enabled: return` first, then the CLI override flag second,
  in both `worker_pool.py:67-71` and `cli/sprint/run.py:215-220` — the same
  ordering, if a comparable skip flag is added for this check, would be the
  established convention to match.

- **Consumers read, never re-derive.** `cli/harness.py` reading the oracle's
  artifact rather than hosting the check is the whole point of the layering — a
  second implementation would drift from the first and the two would disagree on
  the same diff.
- **`_record_harness_event()`** (`harness.py:57-83`) persists a flat single-row
  event, not a multi-test table. The per-test bundle is new structure alongside
  it, not an extension of it.
- **The adapter adds no check logic** — it resolves the base and calls the core.
  Any logic belonging to the check itself belongs in `prepatch_check.py`
  (ENH-3142), where both hosts get it.
- **The adapter is not thin, though (revised 2026-08-12).** Verified against the
  shipped core, `verify_work_was_done()` cannot host this without a signature
  change. Its current shape is `verify_work_was_done(logger, changed_files=None,
  baseline_sha=None, config=None, repo_root=None, pre_step_snapshot=None) ->
  bool` (`work_verification.py:158-165`). Three gaps:
  - **No `GitLock`.** `run_prepatch_check()` requires one (and passes it to
    `setup_prepatch_worktree()`). `git_lock` appears **zero** times in both
    `work_verification.py` and `issue_manager.py` — `worker_pool.py` has one to
    thread through, but the `ll-auto` path would have to construct one. Decide
    and state which: threaded param vs. locally constructed.
  - **No `worktree_base` / `base_branch`.** Both are required by the core with
    no defaults. `worktree_base` must be a gitignored dir (`.worktrees/`);
    `base_branch` drives the merge-base fallback when `base_sha` is unstamped.
  - **The `-> bool` return cannot carry `PrePatchEvidence` out.** The tamper
    guard folds into the bool because its result *is* pass/fail; this check
    produces a bundle that must reach `.ll/history.db` for ENH-2998's own
    harness consumer to find it. Either widen the return type or have the
    adapter persist the bundle itself before returning. State which.
  This is why the Impact section's effort/risk was revised upward below.
- **Worktree teardown is ENH-2997's, and applies here too.** The core does not
  clean up its fork on the success path. ENH-2997 owns the `try/finally` +
  `cleanup_worktree(..., delete_branch=True)` contract and the reaper-predicate
  widening; this adapter must follow the same contract rather than inventing a
  second one, or `ll-auto`/`ll-parallel` runs leak a worktree per verification.
- **`docs/reference/API.md`** — `:88`'s module table entry for
  `little_loops.worktree_utils` names only ll-parallel/ll-sprint/ll-loop as
  consumers and does not mention the FSM executor as a fourth direct caller;
  `:3455-3473` documents `verify_epic_branch_before_merge` /
  `setup_worktree(..., checkout_existing=True)`'s call shape. Cross-reference the
  pre-patch variant here.
- **`docs/reference/CONFIGURATION.md`** — no change needed; the
  `project.test_patterns` row shipped with ENH-2973.
- `scripts/little_loops/parallel/merge_coordinator.py` (~`:1061`) has its own
  private `_cleanup_worktree` wrapper rather than calling
  `little_loops.worktree_utils.cleanup_worktree` directly; confirm during
  implementation whether it needs updating or is genuinely independent.

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/work_verification.py` — the non-FSM adapter over
  ENH-2991's core, mirroring how ENH-2854 reaches `issue_manager.py` and
  `parallel/worker_pool.py`. This is what gives `ll-auto` / `ll-parallel`
  coverage.
- `scripts/little_loops/issue_manager.py`, `scripts/little_loops/parallel/worker_pool.py`
  — call sites for the adapter, following ENH-2854's existing wiring in the same
  files.
- `scripts/little_loops/cli/harness.py` — surface the pre-patch evidence
  alongside `HarnessEvalOutcome` / `_evaluate_and_report()` by reading the
  persisted `.ll/history.db` row; additive JSON keys in the JSON-print branch;
  `--help` epilog. **Locate all sites by name, not by line number** — every
  numeric citation this issue originally carried for this file is stale (see
  § Design Notes).
- `skills/verify-issue-loop/SKILL.md` (~L150-165) — document the deterministic
  check.
- `scripts/little_loops/cli/loop/scaffold_verify.py` — the state-template
  example, since `templates.md` is a redirect stub (FEAT-2948). The existing
  deterministic-alongside-`llm_structured` precedent to mirror is the
  adversarial mode's `count_probes` state (`scaffold_verify.py:130-145`).
- `docs/reference/API.md` (`:88`, `:3455-3473`) — cross-reference the pre-patch
  worktree variant and the FSM executor as a `worktree_utils` consumer.

### Similar Patterns to Follow

- `scripts/little_loops/work_verification.py` as wired by ENH-2854 (landed
  2026-07-31) — the exact adapter shape and the `issue_manager.py` /
  `worker_pool.py` call-site pattern to mirror.
- The learning-test gate's shared-skip-flag pattern (`cli_args.py:214` →
  `issue_manager.py:880`, `worker_pool.py:64`, `cli/sprint/run.py:222`) — the
  precedent for one flag controlling a gate across multiple orchestrators.
- `scripts/little_loops/issue_history/models.py`'s `Gap`/`GapAnalysis`
  (`:259-302`) — the `to_dict()` convention the bundle already follows, for
  serializing into harness JSON output.

### Tests

- `scripts/tests/test_cli_harness.py` — extend for the new evidence bundle;
  assert `cli/harness.py` does **not** call `run_prepatch_check()` directly, and
  that its output is unchanged when no row exists for the issue.
- `scripts/tests/test_verify_issue_loop.py` — extend for the documented check.
- Non-FSM adapter coverage from `issue_manager.py` and `worker_pool.py`,
  following ENH-2854's existing tests for the same call sites.
- A test asserting the adapter reuses `config.prepatch_check.enabled` and adds
  no second off-switch, and that with the default `enabled: false` the non-FSM
  path is a recorded skip rather than a failure.
- A test asserting the adapter leaves no pre-patch worktree or branch behind.

### Related Issues

- `ENH-3142` (done) — the gate core this adapter calls; supersedes ENH-2991,
  which was decomposed and shipped no code.
- `ENH-3141` (done) — `setup_prepatch_worktree()`, called transitively.
- `ENH-2997` (blocking) — writes the bundle `cli/harness.py` reads, and owns the
  worktree-teardown contract this adapter follows.
- `ENH-2854` (peer) — the adapter shape and call sites this mirrors.

## Program Design

### Call Path

Non-FSM host: `work_verification.verify_work_was_done` -> `read_base_sha` /
`read_base_dirty` -> `run_prepatch_check` -> `collect_candidates` ->
`setup_prepatch_worktree` -> pytest (x2, initial + flake retry)

The adapter resolves `(base_sha, base_dirty)` and passes them in; the core is
database-free. It must also supply `repo_root`, a gitignored `worktree_base`,
`base_branch`, `logger`, and a `GitLock` — the shipped signature is keyword-only
with nine parameters and takes no `timeout_s` (the box comes from
`config.prepatch_check.timeout_s`). `_evaluate_and_report()` in `cli/harness.py`
reads the persisted bundle from `.ll/history.db` and surfaces it alongside the
existing `HarnessEvalOutcome` — it does not call `run_prepatch_check()` itself.

`PrePatchEvidence.to_dict()` (`prepatch_check.py:88-97`) already exists and
follows this codebase's nested-list-comprehension convention, so the harness
JSON surfacing needs no new serializer.

## Scope Boundaries

- **Not this issue**: the check itself (ENH-2991) or the FSM executor host
  (ENH-2997).
- **Not this issue**: making `ll-harness` an owner of the check. It was demoted
  to a consumer at the 2026-07-30 placement review because no orchestrator
  invokes it — a repo-wide grep for `ll-harness` across `scripts/little_loops/`
  returns only its own CLI, `runner_spec.py`, telemetry readers
  (`history_reader.py:2797+`), and a permission string in `init/writers.py:70`.
- **Not this issue**: making `/ll:verify-issue-loop` an owner. It is a generator;
  a check emitted there exists only inside per-issue YAML someone chose to
  generate, never in a standing path. It documents a delegation, not a check.
- **Not this issue**: replacing or removing the existing LLM-judged semantic
  criteria in verification loops.

## Acceptance Criteria

- [ ] A non-FSM adapter in `work_verification.py` reaches ENH-3142's core from `ll-auto` / `ll-parallel`, mirroring ENH-2854's `issue_manager.py` / `worker_pool.py` wiring.
- [ ] The adapter resolves `(base_sha, base_dirty)` via `read_base_sha` / `read_base_dirty` and supplies the core's six further required arguments (`repo_root`, gitignored `worktree_base`, `base_branch`, `logger`, `GitLock`, `config`); it does not duplicate any check logic that belongs in `prepatch_check.py`.
- [ ] The `GitLock` sourcing decision (threaded from the caller vs. constructed in the adapter) is made explicitly and applied consistently at both the `issue_manager.py` and `worker_pool.py` call sites.
- [ ] The `PrePatchEvidence` bundle escapes `verify_work_was_done()`'s `-> bool` return — either via a widened return type or by the adapter persisting to `.ll/history.db` before returning — so ENH-2998's own harness consumer can find it.
- [ ] The adapter reuses `config.prepatch_check.enabled` as its only off-switch; with the `false` default the non-FSM path is a recorded skip, not a failure. A test asserts no second off-switch was added.
- [ ] The adapter leaves no pre-patch worktree or branch behind, following ENH-2997's teardown contract; a test asserts it.
- [ ] `cli/harness.py` surfaces the pre-patch evidence by reading the persisted `.ll/history.db` row; a test asserts it does not call `run_prepatch_check()` and does not re-implement the check.
- [ ] The evidence appears as an additive key set in `_evaluate_and_report()`'s JSON output, and the `--help` epilog mentions it.
- [ ] `skills/verify-issue-loop/SKILL.md` documents when the deterministic pre-patch check applies, and `scaffold_verify.py` gains a state-template example showing the guard key. (`templates.md` is a redirect stub and is **not** modified.)
- [ ] `docs/reference/API.md` cross-references the pre-patch worktree variant and lists the FSM executor as a `worktree_utils` consumer.
- [ ] Existing `ll-harness` behavior is unchanged when no bundle is present (the evidence section is simply absent, not an error) — including the common case where `prepatch_check.enabled` was never turned on.

## Impact

- **Priority**: P2 — extends coverage to the non-FSM orchestrators and makes the
  evidence auditable without re-running the check.
- **Effort**: Medium-Large — revised upward 2026-08-12. The harness surfacing and
  documentation halves are genuinely small, but the adapter half requires a
  `verify_work_was_done()` signature change plus new `GitLock` plumbing at both
  orchestrator call sites (see § Design Notes → "The adapter is not thin").
- **Risk**: Medium — revised upward 2026-08-12. The harness half is additive and
  low-risk, but `verify_work_was_done()` is a shared entry point for both
  `ll-auto` and `ll-parallel`, so its signature change touches both
  orchestrators' verification path. The `enabled: false` default is what keeps
  the change inert for existing projects.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-08-02T15:27:49 - `4acf820d-02a8-4f47-a175-f1a0616e7195.jsonl`
- `/ll:issue-size-review` - 2026-08-02T13:48:44 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`

## Related Key Documentation

- `docs/reference/API.md` — documents `work_verification`, `cli/harness.py`'s module surface, and `worktree_utils`; this issue's non-FSM adapter and harness evidence-surfacing are additive changes to exactly those documented modules (and the issue itself calls out a needed API.md cross-reference update).
- `.claude/CLAUDE.md` — `ll-harness` is listed in the § CLI Tools catalog; this issue extends what it reports without changing its invocation surface.
