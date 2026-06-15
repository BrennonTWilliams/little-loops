---
id: EPIC-2171
title: Complete the branch-based development workflow (use_feature_branches)
type: epic
status: open
priority: P3
captured_at: '2026-06-15T16:51:50Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [epic, parallel, sprint, feature-branches, workflow, dx]
relates_to: [BUG-2172, ENH-2173, ENH-2174, ENH-2175]
---

# EPIC-2171: Complete the branch-based development workflow (use_feature_branches)

## Summary

Umbrella tracking issue for finishing the `parallel.use_feature_branches`
feature flag so it actually delivers a **PR-based development workflow** rather
than a half-wired flag that stops at a local branch.

Today the flag (config-schema.json:377-381, default `false`) is honored in only
a narrow slice of the system:

- ✅ Branch naming in `worker_pool.py:245` (`feature/<id>-<slug>` vs `parallel/<id>-<ts>`)
- ✅ Auto-merge skip + PR-ready bookkeeping in `orchestrator.py:951`
- ✅ Branch survives worktree cleanup (`worker_pool.py:631` only deletes `parallel/` branches)
- ✅ Inherited by `ll-sprint` multi-issue waves via `create_parallel_config`

But the wiring is incomplete in ways that defeat the flag's stated purpose
("branches survive as PR-ready… Use for PR-based CI/CD workflows"):

1. **No push, no PR** — the feature-branch path never runs `git push` or
   `gh pr create`; `parallel.remote_name` is unused here. The user still
   pushes + opens a PR by hand for every issue. (BUG-2172)
2. **No per-run CLI override** — the flag is read only from the config file;
   there is no `--feature-branches` flag and `create_parallel_config()` does
   not accept the parameter, unlike every sibling parallel setting. (ENH-2173)
3. **Not discoverable** — absent from `/ll:configure`, init, and templates;
   hand-edit-only. (ENH-2174)
4. **No issue ↔ branch/PR linkage** — the branch name is a title slug, nothing
   is written back to the issue file, and there is no handoff to
   `/ll:open-pr`. (ENH-2175)

The goal of this EPIC is that turning on `use_feature_branches` produces a
branch that is genuinely "PR-ready" — pushed (optionally PR'd), discoverable
via config, selectable per-run, and traceable back to its originating issue.

## Goal / Definition of Done

- Enabling the flag (via config OR a CLI flag) yields, per issue, a feature
  branch that is pushed to the configured remote and optionally has a PR opened.
- The flag is selectable per-run without editing config.
- The flag is surfaced in `/ll:configure` and init.
- Each issue records the branch (and PR URL if created) that implemented it.
- Schema/docs describe the actual behavior — no overstated "PR-ready" claims.

## Children

- **BUG-2172** — `use_feature_branches` "PR-ready" overstates behavior: no push, no PR; `remote_name` unused.
- **ENH-2173** — Add `--feature-branches` CLI override to `ll-parallel` / `ll-sprint`.
- **ENH-2174** — Surface `use_feature_branches` in `/ll:configure` and init templates.
- **ENH-2175** — Record the feature branch (and PR URL) back to the issue file for PR linkage.

## Sequencing

1. **BUG-2172** first — it establishes the real end-state behavior (push +
   optional PR) that the rest depend on. Either finish the loop or rescope docs.
2. **ENH-2173** in parallel/after — makes the (now-real) workflow selectable per run.
3. **ENH-2175** after 2172 — branch/PR linkage only has something to record once
   2172 produces a pushed branch / PR URL.
4. **ENH-2174** last — capstone discoverability once the behavior is settled.

## Out of Scope

- Changing `ll-auto` (sequential, in-place) to adopt branch-per-issue. The flag
  lives under `parallel` by design; sequential branch-per-issue is a separate
  initiative if desired.
- The single-issue-sprint-wave bypass (single-issue waves run in-place via
  subprocess, not `ParallelOrchestrator`) — noted during analysis but not
  selected for this EPIC; capture separately if it proves painful.

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`
