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
relates_to: [BUG-2172, ENH-2173, ENH-2174, ENH-2175, ENH-2176, ENH-2177]
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
5. **Inconsistent coverage** — in `ll-sprint`, single-issue waves and contention
   sub-waves run in-place and never consult the flag, so toggling it silently
   no-ops for those issues. (ENH-2176)
6. **Docs/tests don't tie it together** — only the JSON schema text is assigned;
   the prose workflow guides and an end-to-end integration test are unowned.
   (ENH-2177)

The goal of this EPIC is that turning on `use_feature_branches` produces a
branch that is genuinely "PR-ready" — pushed (optionally PR'd), discoverable
via config, selectable per-run, traceable back to its originating issue, with
predictable coverage and behavior documented end-to-end.

## Goal / Definition of Done

- Enabling the flag (via config OR a CLI flag) yields, per issue, a feature
  branch that is pushed to the configured remote and optionally has a PR opened.
- The flag is selectable per-run without editing config.
- The flag is surfaced in `/ll:configure` and init.
- Each issue records the branch (and PR URL if created) that implemented it.
- The toggle behaves predictably wherever it is in scope, or its coverage
  boundary is explicitly documented at the toggle surface (no silent no-ops).
- Schema **and** prose docs describe the actual behavior — no overstated
  "PR-ready" claims — and an end-to-end test guards the composed workflow.

## Children

- **BUG-2172** — `use_feature_branches` "PR-ready" overstates behavior: no push, no PR; `remote_name` unused.
- **ENH-2173** — Add `--feature-branches` CLI override to `ll-parallel` / `ll-sprint`.
- **ENH-2174** — Surface `use_feature_branches` in `/ll:configure` and init templates.
- **ENH-2175** — Record the feature branch (and PR URL) back to the issue file for PR linkage.
- **ENH-2176** — Honor `use_feature_branches` in single-issue sprint waves (today the flag silently no-ops there).
- **ENH-2177** — Document the feature-branch workflow end-to-end and add an integration test.

## Sequencing

1. **BUG-2172** first — it establishes the real end-state behavior (push +
   optional PR) that the rest depend on. Either finish the loop or rescope docs.
   Now also owns the `gh` precondition, PR-base target, and push/PR idempotency.
2. **ENH-2173** in parallel/after — makes the (now-real) workflow selectable per run.
3. **ENH-2175** after 2172 — branch/PR linkage only has something to record once
   2172 produces a pushed branch / PR URL.
4. **ENH-2176** in parallel — closes the single-issue-wave coverage gap (or, at
   minimum, warns + documents it) so the toggle behaves predictably across sprints.
5. **ENH-2174** + **ENH-2177** last — capstone discoverability, prose docs, and
   the end-to-end test once the behavior is settled.

## Out of Scope

- Changing `ll-auto` (sequential, in-place) to adopt branch-per-issue. The flag
  lives under `parallel` by design; sequential branch-per-issue is a separate
  initiative if desired. (The coverage boundary is now *documented* at the toggle
  surface — see ENH-2174 AC#4 — rather than left implicit.)
- Note: the single-issue-sprint-wave bypass, previously deferred here, is now
  promoted to a tracked child (**ENH-2176**) because it directly undermines the
  "first-class toggle" goal.

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`
