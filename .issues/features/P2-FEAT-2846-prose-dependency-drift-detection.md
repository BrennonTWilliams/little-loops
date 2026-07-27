---
id: FEAT-2846
type: FEAT
priority: P2
status: open
discovered_date: 2026-07-26
discovered_by: manual-review
labels:
- issues-cli
- dependency-graph
- linting
blocks:
- ENH-2847
relates_to:
- FEAT-2842
- BUG-2848
---

# FEAT-2846: Detect prose dependency claims that are missing from frontmatter

## Summary

Issue bodies routinely state dependencies in prose ("Depends on FEAT-109") that
never reach the `blocked_by:` frontmatter the dependency graph reads. The
sequencer has no way to know the edge exists, so it reports the issue as
unblocked. Add a shared prose-dependency extractor, surface drift as a
`format-check` gap, and provide a repo-wide sweep gated in the test suite.

## Current Behavior

`DependencyGraph.from_issues()` (`dependency_graph.py:56-146`) reads only the
structured frontmatter fields. It never parses issue bodies — correctly; the
graph algorithm is not the defect. The failure is upstream: nothing ensures a
prose dependency claim is mirrored into `blocked_by:`.

Observed in the `sketch-storyboards` project: `ll-issues sequence` placed
FEAT-110 first with rationale `[P2, no blockers]`. FEAT-110's body says
"Depends on FEAT-109 (recovery + crash matrix)"; FEAT-109 is `status: open`.
FEAT-110 has no `blocked_by`, `blocks`, or `depends_on` key at all, so its
in-degree is 0 and Kahn's algorithm schedules it immediately.

**This repo has the same drift.** A probe over the 50 active issues in
`.issues/` found 9 (18%) with a prose dependency ID absent from both
`blocked_by` and `depends_on`:

```
EPIC-2149→ENH-2148   FEAT-2414→FEAT-2413   ENH-2580→ENH-2581
ENH-2582→ENH-2581    EPIC-2457→ENH-2581    EPIC-2575→FEAT-2576
EPIC-2765→ENH-2762   FEAT-2416→FEAT-2413   EPIC-2257→BUG-2266
```

Nothing detects this at authoring time or at read time.

The converse case also exists and must not become a false positive: an issue
whose prose "Blocked By" section names an issue that has since shipped. Parsing
prose without a status check would start reporting those as active blockers.

## Expected Behavior

Three layers, one extractor:

1. **`little_loops/issues/prose_deps.py`** — `extract_prose_deps(body) -> set[str]`.
   Frontmatter- and code-fence-aware (reuse the fence-skipping logic in
   `issues/anchor_sweep.py`). Canonical phrasings only: `Depends on <ID>`,
   `Blocked by <ID>`, `## Blocked By` section bodies, `Requires <ID>`. Strips
   `P\d-` prefixes and normalizes case. Deliberately conservative — recall
   matters less than not crying wolf.
2. **A `format-check` gap.** `check_format_gaps()` already has a taxonomy
   (`missing` / `renamed` / `empty` / `boilerplate` / `malformed_id`) that
   `ll-issues format-check` reports and the refine/ready skills consume. Add:
   - `prose_dep_drift` — prose names an **active** issue absent from
     `blocked_by`/`depends_on`.
   - `stale_prose_dep` — prose names a `done`/`cancelled` issue. Distinct code;
     the remedy is deleting stale text, not adding an edge.
   Reusing the existing taxonomy means no new command surface and free
   integration with every consumer of `format-check`.
3. **A repo-wide sweep**, gated in `python -m pytest scripts/tests/` per the
   project's no-hosted-CI policy. Not `ll-verify-docs` — that verifies
   documented counts; this belongs either as a `--all` mode on `format-check` or
   as a new `ll-verify-*` entry point following that family's conventions.

Skills enforce by **calling** layer 2, not by reading prose themselves:
`/ll:refine-issue`, `/ll:ready-issue`, and `/ll:wire-issue` treat
`prose_dep_drift` as a blocking gap. That puts a deterministic oracle behind an
LLM-driven check.

An opt-in `--fix` that backfills `blocked_by:` from confidently-matched prose is
worth having for the 9 issues above, but should stage a reviewable diff rather
than write silently — the `anchor-sweep --dry-run` posture. It should write via
`ll-issues link` (FEAT-2842) rather than editing frontmatter directly.

## Root Cause

Issue templates and authoring skills accept prose dependency statements without
requiring the structured mirror, and no read path reconciles the two. The
invariant "a prose dependency claim implies a frontmatter edge" was never
written down or enforced.

## Implementation Steps

1. Write `prose_deps.py` with the extractor and a test corpus covering: fenced
   code containing `Depends on FEAT-1`, `P2-FEAT-109` prefix forms, `## Blocked
   By` sections, self-references, and IDs inside link targets.
2. Extend `check_format_gaps()` with the two new gap kinds; thread the referenced
   issues' statuses in (needs a lookup — check whether `check_format_gaps` has
   backlog access today or needs a new parameter).
3. Extend `ll-issues format-check` text and `--json` output.
4. Add the repo-wide sweep mode plus its pytest gate.
5. Update `/ll:refine-issue`, `/ll:ready-issue`, `/ll:wire-issue` to call it and
   treat `prose_dep_drift` as blocking.
6. Optional `--fix`, dry-run by default, writing via `ll-issues link`.
7. Fix the 9 drifting issues in this repo.

## Use Case

As someone planning the next work item, I run `ll-issues sequence` and trust
that an issue shown as unblocked really is — because any issue whose body claims
a dependency it never recorded was caught by `format-check` during refinement
and either wired up or corrected. As a backlog owner adopting this on an
existing project, the repo-wide sweep tells me up front which issues drifted
before the rule existed, instead of discovering them one mis-scheduled issue at
a time.

## Acceptance Criteria

- [ ] `extract_prose_deps()` ignores IDs inside fenced code blocks and inside
      frontmatter.
- [ ] An issue with `Depends on FEAT-109` in prose and no `blocked_by` reports
      `prose_dep_drift` from `ll-issues format-check`.
- [ ] An issue whose prose names a `done` issue reports `stale_prose_dep`, not
      `prose_dep_drift`.
- [ ] The repo-wide sweep runs under `python -m pytest scripts/tests/` and
      passes once this repo's 9 drifting issues are corrected.
- [ ] No GitHub Actions workflow is added.

## Impact

- **Users**: `ll-issues sequence`, `next-issue`, and wave planning stop
  scheduling work whose prerequisites are unfinished. The current failure is
  silent and indistinguishable from a correct answer.
- **Risk**: Low-Medium. The extractor will have false positives; keeping it a
  reported gap (with `--fix` opt-in and dry-run) rather than an ordering input
  bounds the blast radius.
- **Effort**: Medium.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/issues/anchor_sweep.py` | Fence-skipping body scanner to reuse |
| `scripts/little_loops/issue_parser.py` — `check_format_gaps` | Gap taxonomy to extend |
| `scripts/little_loops/dependency_graph.py:56-146` | Why prose is invisible today |
| `.claude/CLAUDE.md` § Testing & CI Policy | Gate belongs in the local pytest suite |

## Context

Traced from a `sketch-storyboards` `ll-issues sequence` run that reported a
blocked issue as `[P2, no blockers]`; the same drift was then confirmed in this
repo's own backlog.

---

## Status

open
