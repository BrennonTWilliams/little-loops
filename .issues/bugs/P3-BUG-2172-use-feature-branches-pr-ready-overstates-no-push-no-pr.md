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

## Expected Behavior

Enabling `use_feature_branches` should produce a branch that is genuinely
PR-ready. Choose one of:

- **Option A (finish the loop)**: after a successful worker in feature-branch
  mode, `git push <remote_name> <branch>` and (optionally, behind a sub-flag)
  `gh pr create`. Report the pushed branch / PR URL.
- **Option B (truthful docs)**: rescope the schema description and end-of-run
  report to say "local feature branch retained" and drop the "PR-ready" /
  "CI/CD" framing. Stop advertising a workflow the flag does not perform.

Recommended: Option A gated by new sub-options (e.g. `push_feature_branches`,
`open_pr_for_feature_branches`) defaulting to off, so existing behavior is
preserved while the advertised workflow becomes achievable.

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
   a pushed branch (or the claim is removed).
2. If Option A: feature-branch mode pushes to `parallel.remote_name`; PR creation
   is available behind an explicit opt-in sub-flag; pushed branch / PR URL is
   reported. Push/PR failures are surfaced without failing the issue's
   implementation result.
3. If Option B: schema description and end-of-run report wording updated to
   describe local-branch retention only; `remote_name` either wired or removed
   from the parallel schema with a note.
4. Tests cover the chosen path (push invoked with correct remote/branch, or
   report wording assertion).
5. **`gh` precondition (Option A)**: if `open_pr_for_feature_branches` is set but
   the `gh` CLI is missing or unauthenticated, the run degrades gracefully to
   push-only (branch pushed, PR skipped) with a clear warning — it does not fail
   the issue's implementation result.
6. **PR target (Option A)**: `gh pr create` targets `parallel.base_branch` (not a
   hardcoded `main`); PR title/body are derived from the issue (title + link),
   and the PR may be opened as a draft (acceptable default — decide during impl).
7. **Idempotency (Option A)**: re-running an issue whose `feature/<id>-<slug>`
   branch already exists and/or is already pushed does not error — push uses
   `--force-with-lease` (or a no-op when up to date), and an existing open PR is
   detected and reused rather than duplicated.

## Implementation Steps

1. Decide Option A vs B (recommend A with opt-in sub-flags).
2. (A) Add push step in the feature-branch branch of the worker-result handler
   using `parallel.remote_name`; thread a new `open_pr` sub-flag to optionally
   shell out to `gh pr create`.
3. Wire any new sub-flags through `ParallelConfig` / `create_parallel_config`
   and config schema.
4. Update the end-of-run "PR-ready" report to reflect actual state (pushed /
   PR'd / local-only).
5. Update config-schema.json description text to match behavior.
6. Add tests.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `_handle_worker_result()` feature-branch branch (add push/PR step); end-of-run report method (~line 1138)
- `scripts/little_loops/parallel/config.py` — `ParallelConfig` / `create_parallel_config` for new `push_feature_branches` and `open_pr_for_feature_branches` sub-flags
- `config-schema.json` — `use_feature_branches` description (~line 377); add new sub-flag entries; wire or remove `remote_name` (~line 382)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/ll_parallel.py` — entry-point that constructs and runs the orchestrator; may surface new sub-flags
- `scripts/little_loops/parallel/__init__.py` — re-exports `ParallelConfig`; update if new fields added

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
- `parallel.remote_name` — wire into push path or remove

## Impact

- **Priority**: P3 — misleading docs/UX; the flag underdelivers but does not
  corrupt data. Blocks the EPIC's "genuinely PR-ready" goal.
- **Effort**: Small–Medium depending on Option A vs B.
- **Risk**: Low — confined to the parallel feature-branch path; push/PR behind
  opt-in flags preserves current behavior.
- **Breaking Change**: No (new behavior opt-in).

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-06-15T16:57:14 - `c5ee10aa-e3ea-47f9-afcb-d5efd2450ef6.jsonl`
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`
