---
id: BUG-2172
title: use_feature_branches "PR-ready" overstates behavior — no push, no PR
type: BUG
status: open
priority: P3
parent: EPIC-2171
captured_at: '2026-06-15T16:51:50Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [parallel, feature-branches, docs, workflow]
---

# BUG-2172: use_feature_branches "PR-ready" overstates behavior — no push, no PR

## Summary

The `parallel.use_feature_branches` flag documents itself as producing
"PR-ready" branches for "PR-based CI/CD workflows", but the feature-branch code
path never pushes the branch to a remote and never opens a PR. After a run, the
branch exists only locally (its worktree is removed, the branch ref survives in
the main repo). The user must manually `git push` and open a PR for every issue,
which contradicts the schema's framing.

The `parallel.remote_name` config field exists specifically for this path but is
unused in feature-branch mode.

## Current Behavior

- config-schema.json:377-381 describes `use_feature_branches`:
  > "When true, auto-merge to main is skipped and branches survive as PR-ready.
  > Use for PR-based CI/CD workflows."
- `orchestrator.py:951` (feature-branch branch of `_handle_worker_result`):
  - logs "feature branch ready — <branch_name>"
  - marks the issue completed
  - records the branch in `_pr_ready_branches`
  - **does not** push the branch or open a PR
- `grep -n "push" scripts/little_loops/parallel/orchestrator.py` → no `git push`
- `parallel.remote_name` (config-schema.json:382-386) is read into config but
  never referenced in the feature-branch path.
- End-of-run report (`orchestrator.py:1138`) lists branches as "PR-ready" even
  though they are local-only.

## Steps to Reproduce

1. Configure a project with `parallel.use_feature_branches: true` in `.ll/ll-config.json`
2. Run `ll-parallel` against one or more issues
3. After completion, read the end-of-run report — branches are listed as "PR-ready"
4. Run `git branch -v` in the main repo — branches exist locally only; no remote push occurred
5. Observe: `parallel.remote_name` is silently ignored; no PR was created

## Decision

**Option A (finish the loop) — DECIDED.** Enabling `use_feature_branches` should
produce a branch that is genuinely PR-ready: after a successful worker in
feature-branch mode, `git push <remote_name> <branch>` and (optionally, behind a
sub-flag) `gh pr create`, reporting the pushed branch / PR URL. The push/PR steps
are gated behind new sub-options (`push_feature_branches`,
`open_pr_for_feature_branches`) defaulting to `false`, so existing behavior is
preserved while the advertised workflow becomes achievable.

Option B (truthful docs only — rescope the schema/report to "local feature branch
retained" and drop the "PR-ready"/"CI/CD" framing) is **rejected**: it abandons
the EPIC's stated goal of a genuinely PR-based workflow.

## Expected Behavior

Enabling `use_feature_branches` produces a branch that is genuinely PR-ready:

- After a successful worker in feature-branch mode, when `push_feature_branches`
  is set, `git push <remote_name> <branch>` runs.
- When `open_pr_for_feature_branches` is also set and the branch was pushed,
  `gh pr create` opens a PR targeting the base branch and the PR URL is captured.
- The end-of-run report states actual state per branch: "pushed + PR opened",
  "pushed (PR skipped)", or "local-only branch retained".
- Schema/report text no longer claims "PR-ready" for a branch that was not pushed.

## Proposed Solution

Implement Option A with opt-in sub-flags to preserve existing behavior:

- Add `parallel.push_feature_branches` (bool, default `false`): when true, `_handle_worker_result()` in `orchestrator.py` calls `git push <remote_name> <branch>` after a successful feature-branch result
- Add `parallel.open_pr_for_feature_branches` (bool, default `false`): when true and branch was pushed, shells out to `gh pr create` and captures the PR URL
- Update the end-of-run report (`_print_pr_ready_report()` or equivalent in `orchestrator.py`) to report actual state: "pushed + PR opened", "pushed (local PR skipped)", or "local-only branch retained"
- Update `config-schema.json` description for `use_feature_branches` to accurately describe local-branch retention; wire `remote_name` into the push path or remove it with a deprecation note

## Root Cause

- **File**: `scripts/little_loops/parallel/orchestrator.py`
- **Anchor**: feature-branch branch of the worker-result handler (~line 951)
- **Cause**: the feature-branch path was implemented to *retain* the branch
  (skip auto-merge) but the push/PR completion steps were never added; the
  schema/docs were written to the intended end-state, creating a behavior↔docs
  gap. `remote_name` was added in anticipation of push support that never landed.

## Acceptance Criteria

1. The behavior and the schema/report text agree — no "PR-ready" claim without
   a pushed branch.
2. Feature-branch mode pushes to `parallel.remote_name` when
   `push_feature_branches` is set; PR creation is available behind the explicit
   opt-in `open_pr_for_feature_branches` sub-flag; the pushed branch / PR URL is
   reported. Push/PR failures are surfaced without failing the issue's
   implementation result.
3. The end-of-run report wording reflects actual per-branch state
   (local-only / pushed / pushed + PR'd), and the `use_feature_branches` schema
   description no longer overstates "PR-ready"; `remote_name` is wired into the
   push path.
4. Tests cover: push invoked with correct `remote_name`/branch; `gh pr create`
   shelled out only when `open_pr_for_feature_branches` is set; report wording
   reflects actual state.
5. **`gh` precondition**: if `open_pr_for_feature_branches` is set but the `gh`
   CLI is missing or unauthenticated, the run degrades gracefully to push-only
   (branch pushed, PR skipped) with a clear warning — it does not fail the issue's
   implementation result.
6. **PR target**: `gh pr create` targets the configured base branch (not a
   hardcoded `main`). Because `base_branch` is currently a runtime-only
   `ParallelConfig` field (`parallel/types.py:376`, default `"main"`) and is
   **not** in `config-schema.json`, this issue adds `parallel.base_branch` to the
   schema so the PR base is user-configurable (a matching `--base-branch` CLI
   override is a natural addition to ENH-2173's flag set, but not required here).
   PR title/body are derived from the issue (title + link); the PR may
   be opened as a draft (acceptable default — decide during impl).
7. **Idempotency**: re-running an issue whose `feature/<id>-<slug>` branch already
   exists and/or is already pushed does not error — push uses
   `--force-with-lease` (or a no-op when up to date), and an existing open PR is
   detected and reused rather than duplicated.

## Implementation Steps

1. Add a push step in the feature-branch branch of the worker-result handler
   using `parallel.remote_name`; thread the `open_pr_for_feature_branches`
   sub-flag to optionally shell out to `gh pr create`.
2. Wire the new sub-flags (`push_feature_branches`,
   `open_pr_for_feature_branches`) through the `ParallelConfig` dataclass in
   `parallel/types.py` (fields, defaults, **and** the `to_dict`/`from_dict`
   round-trip), `config/automation.py` `ParallelAutomationConfig`,
   `create_parallel_config` in `config/core.py`, and `config-schema.json`.
3. Add `parallel.base_branch` to `config-schema.json` (default `"main"`) so the
   PR base is configurable; resolve it in `create_parallel_config` like the other
   parallel fields.
4. Update the end-of-run "PR-ready" report to reflect actual state (pushed /
   PR'd / local-only).
5. Update config-schema.json description text to match behavior.
6. Add tests.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `_handle_worker_result()` feature-branch branch (~line 951, add push/PR step); end-of-run "PR-ready" report (~line 1138)
- `scripts/little_loops/parallel/types.py` — `ParallelConfig` dataclass (~line 304): add `push_feature_branches` / `open_pr_for_feature_branches` fields **and** include them in `to_dict()` (~line 448) / `from_dict()` (~line 491) so they survive serialization to workers. (`parallel/config.py` does **not** exist — `ParallelConfig` lives here.)
- `scripts/little_loops/config/automation.py` — `ParallelAutomationConfig` dataclass + `from_dict` (~lines 58–59, 90–91): add the new sub-flags
- `scripts/little_loops/config/core.py` — `create_parallel_config` (~line 415): accept and resolve the new sub-flags **and** `base_branch` (model after the `remote_name` resolution at ~line 494)
- `config-schema.json` — `use_feature_branches` description (~line 377); add `push_feature_branches` / `open_pr_for_feature_branches` entries; add `base_branch` (default `"main"`, currently runtime-only); wire `remote_name` into the push path (~line 382)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/ll_parallel.py` — entry-point that constructs and runs the orchestrator; may surface new sub-flags
- `scripts/little_loops/parallel/__init__.py` — re-exports `ParallelConfig`; update if new fields added
- `scripts/little_loops/parallel/worker_pool.py` / `merge_coordinator.py` — already consume `base_branch` / `remote_name`; verify no regression when `base_branch` becomes schema-driven

### Similar Patterns
- Auto-merge path in `_handle_worker_result()` (the `else` branch of the feature-branch check) — complementary pattern for completing worker results

### Tests
- `scripts/tests/test_parallel_orchestrator.py` (or equivalent) — add: push invoked with correct `remote_name`/branch args; PR creation shelled out when `open_pr_for_feature_branches=true`; report wording reflects actual state (local-only vs pushed vs PR'd)

### Documentation
- `config-schema.json` — `use_feature_branches` and `remote_name` description fields
- End-of-run console report in `orchestrator.py`

### Configuration
- `parallel.push_feature_branches` (new, default `false`)
- `parallel.open_pr_for_feature_branches` (new, default `false`)
- `parallel.base_branch` (new schema entry, default `"main"`) — promote the
  existing runtime-only `ParallelConfig.base_branch` to `config-schema.json` so
  the PR base is user-configurable
- `parallel.remote_name` — wire into push path (no longer unused)

## Impact

- **Priority**: P3 — misleading docs/UX; the flag underdelivers but does not
  corrupt data. Blocks the EPIC's "genuinely PR-ready" goal.
- **Effort**: Medium — Option A (push + opt-in PR) decided; spans schema, config
  wiring (types/automation/core), the push/PR step, and report text.
- **Risk**: Low — confined to the parallel feature-branch path; push/PR behind
  opt-in flags preserves current behavior.
- **Breaking Change**: No (new behavior opt-in).

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- decision - 2026-06-15 - Option A (push + opt-in PR) selected; Integration Map corrected (`parallel/types.py`, not `parallel/config.py`); `base_branch` promoted to schema.
- `/ll:format-issue` - 2026-06-15T16:57:14 - `c5ee10aa-e3ea-47f9-afcb-d5efd2450ef6.jsonl`
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`
