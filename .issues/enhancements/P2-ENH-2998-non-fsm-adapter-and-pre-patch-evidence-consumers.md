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
- ENH-2991
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
(`ll-auto`, `ll-parallel`) via a thin adapter in `work_verification.py`, and make
the evidence readable where humans and hand-run tooling look for it —
`cli/harness.py` and `skills/verify-issue-loop/`.

Both consumers read the persisted bundle; neither re-implements the check.

## Parent Issue

Decomposed from ENH-2853: Deterministic pre-patch test-failure check in
verification loops. Covers § Proposed Change step 5 (surfacing) and step 7, and
Integration Map Layer 3 plus the `work_verification.py` half of Layer 2.

## Current Behavior

After ENH-2991 and ENH-2997, the check runs only inside FSM loops. `ll-auto` and
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
   ENH-2854's existing wiring in those files.
2. **Harness consumer** — `cli/harness.py` reads the persisted bundle and reports
   it alongside `HarnessEvalOutcome` (`:242-248`) in `_evaluate_and_report()`
   (`:251-317`). It does **not** call `run_prepatch_check()` itself. The bundle is
   an additive key set in `_evaluate_and_report()` (`:283-294`) and `_report()`
   (`:320-339`); mention it in the `--help` epilog (`:117-128`).
3. **Skill documentation** — `skills/verify-issue-loop/SKILL.md` (~L150-165) and
   `templates.md` document only `llm_structured` verify/probe states today. Add a
   bullet describing when the deterministic pre-patch check applies and a
   state-template example showing the guard key. This is additive documentation,
   not editing a prohibition: the "no deterministic state type" boundary text the
   original wiring pass cited at SKILL.md lines 211-219 no longer exists after
   the skill's restructuring (verified 2026-07-29; the skill is now 212 lines with
   no `check_invariants`/`check_stall`/`check_concrete` mention).

## Design Notes

- **Consumers read, never re-derive.** `cli/harness.py` reading the oracle's
  artifact rather than hosting the check is the whole point of the layering — a
  second implementation would drift from the first and the two would disagree on
  the same diff.
- **`_record_harness_event()`** (`harness.py:57-83`) persists a flat single-row
  event, not a multi-test table. The per-test bundle is new structure alongside
  it, not an extension of it.
- **The adapter is thin.** It resolves the base and calls the core. Any logic
  that belongs to the check itself belongs in ENH-2991's `prepatch_check.py`,
  where both hosts get it.
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
  alongside `HarnessEvalOutcome` (`:242`) / `_evaluate_and_report()` (`:251`) by
  reading the persisted bundle; additive JSON keys at `:283-294` and `:320-339`;
  `--help` epilog at `:117-128`.
- `skills/verify-issue-loop/SKILL.md` (~L150-165) and
  `skills/verify-issue-loop/templates.md` — document the deterministic check and
  add a state-template example.
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
  assert `cli/harness.py` does **not** call `run_prepatch_check()` directly.
- `scripts/tests/test_verify_issue_loop.py` — extend for the documented check.
- Non-FSM adapter coverage from `issue_manager.py` and `worker_pool.py`,
  following ENH-2854's existing tests for the same call sites.

### Related Issues

- `ENH-2991` (blocking) — the gate core this adapter calls.
- `ENH-2997` (blocking) — writes the bundle `cli/harness.py` reads.
- `ENH-2854` (peer) — the adapter shape and call sites this mirrors.

## Program Design

### Call Path

Non-FSM host: `work_verification.verify_work_was_done` -> `read_base_sha` -> `run_prepatch_check` -> `collect_candidate_nodeids` -> `filter_test_files`

The adapter resolves `(base_sha, base_dirty)` and passes them in; the core is
database-free. `_evaluate_and_report()` in `cli/harness.py` reads the persisted
bundle and surfaces it alongside the existing `HarnessEvalOutcome` — it does not
call `run_prepatch_check()` itself.

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

- [ ] A non-FSM adapter in `work_verification.py` reaches ENH-2991's core from `ll-auto` / `ll-parallel`, mirroring ENH-2854's `issue_manager.py` / `worker_pool.py` wiring.
- [ ] The adapter resolves `(base_sha, base_dirty)` and passes them in; it does not duplicate any check logic that belongs in `prepatch_check.py`.
- [ ] `cli/harness.py` surfaces the pre-patch evidence by reading the persisted bundle; a test asserts it does not call `run_prepatch_check()` and does not re-implement the check.
- [ ] The evidence appears as an additive key set in `_evaluate_and_report()` / `_report()` JSON output, and the `--help` epilog mentions it.
- [ ] `skills/verify-issue-loop/SKILL.md` documents when the deterministic pre-patch check applies, and `templates.md` gains a state-template example showing the guard key.
- [ ] `docs/reference/API.md` cross-references the pre-patch worktree variant and lists the FSM executor as a `worktree_utils` consumer.
- [ ] Existing `ll-harness` behavior is unchanged when no bundle is present (the evidence section is simply absent, not an error).

## Impact

- **Priority**: P2 — extends coverage to the non-FSM orchestrators and makes the
  evidence auditable without re-running the check.
- **Effort**: Medium — a thin adapter plus read-only surfacing and documentation.
- **Risk**: Low — additive keys and an adapter over an existing core; no
  signature changes.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-08-02T13:48:44 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`
