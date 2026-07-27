---
id: 2855
title: Track codebase maintainability trend as an observability dimension
type: FEAT
priority: P3
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
---

# FEAT-2855: Track codebase maintainability trend as an observability dimension

Origin: ll-product #FEAT-053

## Summary

Existing agent-quality observability measures agent *outcome* quality — success rate, retries, corrections, cost, regressions with model attribution. Nothing measures whether the repo itself is getting harder to change under sustained agent activity.

Derive a maintainability trend from repo-history signals (change coupling, shotgun-surgery spread, churn concentration) joined against `.ll/history.db` runs, so degradation attributable to agent batches becomes visible.

## Motivation

Coding agents are good at closing a task and indifferent to what that task does to the codebase's long-term shape. The cost of poor structure is paid over months; nothing in a per-issue success signal can see it. A project can therefore show a rising fix-rate and a falling cost-per-issue while steadily becoming more expensive to work in — and the existing metrics will report that as improvement.

This is distinct from quality-regression detection, which attributes regressions in *agent outcomes* to models or host versions. Here the subject is the repository, and the question is whether it is getting worse.

## Proposed Change

Compute a small set of structural signals over repo history, sampled at intervals, and join them to the `.ll/history.db` run record so a trend can be attributed to periods of agent activity.

Candidate signals (all derivable from `git log` alone, no LLM):

- **Change coupling** — pairs of files that repeatedly change together despite not being obviously related. Rising coupling means edits are spreading.
- **Shotgun-surgery spread** — files touched per logical change, trended. A rising median means single changes require more places.
- **Churn concentration** — share of total churn landing in the top-N hottest files. Rising concentration flags files becoming change magnets.
- **Change-set entropy** — how scattered a typical commit's touched paths are across the directory tree.

Output:

1. A command that reports each signal as a time series across sampling points, over any repo with history.
2. A join against `.ll/history.db` so sampling windows can be labeled by the agent runs that occurred in them.
3. A summary verdict per signal: improving / flat / degrading, with the magnitude and the window compared.

## Design Notes

- Everything must be computable from `git log` plus `.ll/history.db`. No language-specific static analysis in the first cut — that would restrict the feature to one ecosystem and is not where the signal is.
- These signals are noisy on small histories. Define and enforce a minimum-history threshold and refuse to report a trend below it rather than emitting a confident-looking number from three commits.
- Attribution is *correlational*, and the output must say so. A window labeled with agent runs is not a claim those runs caused the trend. Overclaiming here would make the whole metric family untrustworthy.
- Reuse the existing history/report substrate rather than building a parallel one — concretely, home the command under the existing `ll-history` CLI (a `trend`/`maintainability` subcommand) rather than adding a new top-level entry point.
- **Define the unit of "logical change".** A raw commit is a bad unit — squash vs. granular commit styles skew shotgun-surgery spread arbitrarily. Since `.ll/history.db` links commits to issues, the unit is the *issue* (all commits attributed to one issue = one logical change), falling back to per-commit for unattributed history, and the report labels which unit each window used.
- **Rename detection is required.** Compute file identity with git rename detection (`-M`/`--follow` semantics); without it, churn concentration and change coupling degrade to noise after any refactor that moves files.
- Read-only against every source, including `.ll/history.db`.

## Acceptance Criteria

- [ ] A command computes each structural signal as a time series over an arbitrary git repo's history.
- [ ] Signals are derived from `git log` and `.ll/history.db` only — no language-specific static analysis, no LLM calls.
- [ ] Sampling windows are joinable to the agent runs recorded in `.ll/history.db`.
- [ ] The command ships as an `ll-history` subcommand, not a new top-level CLI.
- [ ] The logical-change unit is the issue where `.ll/history.db` attribution exists, per-commit otherwise, and the output labels which unit applied.
- [ ] File identity survives renames (git rename detection); a synthetic-repo test with a renamed hot file shows continuity.
- [ ] Each signal reports a verdict (improving / flat / degrading) with magnitude and comparison window.
- [ ] A repo below the minimum-history threshold gets an explicit "insufficient history" result, not a computed trend.
- [ ] Output states that agent-run attribution is correlational.
- [ ] All source data is opened read-only; no source DB or repo state is mutated.
- [ ] Tests cover: a synthetic repo with injected degradation, one with injected improvement, a flat repo, and a repo below the history threshold.
