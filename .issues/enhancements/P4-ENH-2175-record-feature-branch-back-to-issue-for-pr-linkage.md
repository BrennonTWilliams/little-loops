---
id: ENH-2175
title: Record the feature branch (and PR URL) back to the issue for PR linkage
type: ENH
status: open
priority: P4
parent: EPIC-2171
captured_at: '2026-06-15T16:51:50Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [parallel, feature-branches, issues, traceability, open-pr]
blocked_by: [BUG-2172]
---

# ENH-2175: Record the feature branch (and PR URL) back to the issue for PR linkage

## Summary

When `ll-parallel` runs in feature-branch mode, each completed issue's branch name (and eventual PR URL) is written back to the issue frontmatter as `branch:` and `pr_url:`, enabling `/ll:open-pr` to find the implementing branch without manual lookup or git-ref guessing.

## Motivation

In feature-branch mode the branch name is derived from the issue title slug
(`feature/<id>-<slug>`, `worker_pool.py:248`) and tracked only in the
orchestrator's in-memory `_pr_ready_branches` map, which is printed once at the
end of the run and then discarded. Nothing is written back to the issue file,
so there is no durable link from an issue to the branch (or PR) that implemented
it, and no handoff to `/ll:open-pr`. After the run ends, recovering "which
branch implements ENH-123?" requires guessing the slug or grepping git refs.

## Current Behavior

- `worker_pool.py:248` computes `feature/<id>-<slug>`; the value lives on the
  `WorkerResult` and in `orchestrator._pr_ready_branches`.
- `orchestrator.py:1138` prints the branch list at end-of-run; it is not
  persisted to the issue.
- No frontmatter field records the branch; `/ll:open-pr` has no per-issue branch
  hint to consume.

## Expected Behavior

- After a feature-branch run, each completed issue's frontmatter contains `branch: feature/<id>-<slug>`.
- When BUG-2172 PR creation is enabled, `pr_url: <url>` is also written to the issue frontmatter.
- `/ll:open-pr` reads `branch:` from the issue and skips PR creation if `pr_url:` is already present.
- Issues processed in auto-merge mode (non-feature-branch) have no `branch:` or `pr_url:` field written.

## Proposed Solution

1. On successful completion in feature-branch mode, write the branch name back
   to the issue frontmatter (e.g. `branch: feature/enh-123-...`).
2. Once BUG-2172 adds push/PR, also record the PR URL (e.g. `pr_url:`) when a PR
   is created.
3. Have `/ll:open-pr` read the recorded `branch:` (and short-circuit if `pr_url:`
   already set) so the PR step is one command, not a manual lookup.

## API/Interface

- New optional issue frontmatter fields: `branch: <string>`, `pr_url: <string>`.
  Document in the issue file format / config schema as applicable.

## Acceptance Criteria

1. After a feature-branch run, each completed issue's frontmatter records the
   branch that implemented it.
2. If BUG-2172 PR creation is enabled, the PR URL is recorded too.
3. `/ll:open-pr` consumes the recorded branch for the issue (and skips if a PR
   URL is already present).
4. Issues processed in non-feature-branch (auto-merge) mode are unaffected — no
   `branch:` field is written.
5. **Idempotent on re-run**: re-running an issue updates `branch:` in place
   (no duplicate keys) and does **not** clobber an existing `pr_url:` — if a PR
   URL is already recorded, it is preserved unless a new PR was demonstrably
   created this run.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — feature-branch completion path: persist branch to issue frontmatter
- `commands/open-pr.md` (or `skills/open-pr/SKILL.md`) — read `branch:` / `pr_url:` from the issue
- `docs/` — document `branch:` and `pr_url:` frontmatter fields in issue format docs
- `config-schema.json` — add optional `branch` and `pr_url` fields to issue frontmatter schema

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` — computes branch name (`feature/<id>-<slug>`); result passed to orchestrator
- `scripts/little_loops/issue_utils.py` (or equivalent frontmatter writer) — called to persist branch to issue file

### Similar Patterns
- Existing frontmatter write-back in `orchestrator.py` (e.g. status updates, `completed_at`) — follow the same pattern for `branch:` / `pr_url:`

### Dependencies
- **BUG-2172** — `pr_url:` only meaningful once PR creation is implemented;
  `branch:` can land independently.

### Tests
- `scripts/tests/test_worker_pool.py` / `scripts/tests/test_parallel_orchestrator.py` — assert branch written to issue frontmatter in feature-branch mode and absent in auto-merge mode

### Documentation
- `docs/reference/API.md` — note new `branch:` / `pr_url:` frontmatter fields
- `.claude/CLAUDE.md` § Issue File Format — reference the new optional fields

### Configuration
- `config-schema.json` — extend issue frontmatter schema with `branch` and `pr_url` optional string fields

## Scope Boundaries

- `branch:` recording is gated to feature-branch mode only; auto-merge runs are unaffected.
- `pr_url:` recording depends on BUG-2172 being implemented first; this ENH covers `branch:` persistence independently.
- Retroactive backfill of `branch:` for previously completed issues is out of scope.
- Branch naming convention (`feature/<id>-<slug>`) is unchanged by this ENH.
- No changes to how `/ll:open-pr` creates PRs — only how it discovers the branch to use.

## Impact

- **Priority**: P4 — traceability/polish; depends on the workflow existing
  (BUG-2172) to be fully valuable, but `branch:` persistence is useful alone.
- **Effort**: Small–Medium.
- **Risk**: Low — additive frontmatter; gated to feature-branch mode.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P4

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-15T20:33:22 - `708f5540-fdfd-4ca1-92bc-72a7cb548730.jsonl`
- `/ll:format-issue` - 2026-06-15T16:58:05 - `bffefeb0-fbda-400c-89f6-f9e3c1696323.jsonl`
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`
