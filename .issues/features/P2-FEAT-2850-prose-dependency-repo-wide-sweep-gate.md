---
id: FEAT-2850
type: FEAT
priority: P2
status: done
parent: FEAT-2846
discovered_date: 2026-07-26
completed_at: '2026-07-27T04:01:22Z'
discovered_by: issue-size-review
blocked_by:
- FEAT-2849
labels:
- issues-cli
- dependency-graph
- linting
decision_needed: false
confidence_score: 96
outcome_confidence: 91
score_complexity: 24
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 22
---

# FEAT-2850: Repo-wide prose-dependency sweep gated in pytest

## Summary

Add a repo-wide sweep mode that reports every issue with prose-dependency
drift, gated in `python -m pytest scripts/tests/` per the project's
no-hosted-CI policy, and fix the 9 issues in this repo already known to
drift. Decomposed from FEAT-2846; built on FEAT-2849's extractor and gap
taxonomy.

## Parent Issue

Decomposed from FEAT-2846: Detect prose dependency claims that are missing
from frontmatter. Covers Implementation Steps 4 and 7 of the parent.

## Decision Needed

The parent issue left the sweep's entry-point route as an open decision.
Resolve this before implementation — it determines which of the two file
lists below applies.

**Option A**: New standalone `ll-verify-prose-deps` entry point following
the `ll-verify-*` family's conventions.

**Option B**: Extend `format-check` with an `--all` mode (no new command
surface, per the parent's stated preference — "Reusing the existing
taxonomy means no new command surface and free integration with every
consumer of format-check").

> **Selected:** Option B — extend `format-check` with `--all`, mirroring the
> existing `epic-consistency --all` precedent and touching zero
> pyproject.toml/cli-registry/permissions files.

### Decision Rationale

**Selected: Option B — `format-check --all` mode.**

`ll-issues` is a single wildcard-permitted console-script entry point
(`ll-issues = "little_loops.cli:main_issues"`, `pyproject.toml:74`) covering
all subcommands, so adding `--all` to `format_check.py` touches zero
pyproject.toml, `cli/__init__.py`, `doctor.py`, `writers._LL_PERMISSIONS`,
or `areas.md` entries — Option A's standalone-entry-point route would need
all five. `cli/issues/epic_consistency.py:244-297` already ships the exact
"positional ID becomes optional, add `--all` reusing the same `find_issues`
result set" shape this option needs, and `test_ll_issues_format_check.py`
already has a multi-category temp `.issues/` fixture to extend in place —
no new test file required. This also matches the parent issue's (FEAT-2846)
explicitly stated preference for no new command surface.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A: standalone `ll-verify-prose-deps` | 3 | 1 | 3 | 2 | 9/12 |
| B: `format-check --all` | 3 | 3 | 3 | 3 | **12/12** |

Key evidence:
- Option A: 10 existing `ll-verify-*` entry points share the pattern, but
  each requires pyproject.toml + `cli/__init__.py` + `writers._LL_PERMISSIONS`
  + `areas.md` touch points, plus an unenforced `doctor.py --full` adapter
  gap.
- Option B: `epic_consistency.py:254-299` is a direct in-family precedent;
  `anchor_sweep.py`'s `_ACTIVE_CATEGORIES`/per-file-`OSError` walk shape is
  copyable inline; zero new integration-surface files.

## Current Behavior

`format-check` only validates one issue at a time (a required positional
`issue_id`), so the `prose_dep_drift`/`stale_prose_dep` gap kinds FEAT-2849
added are never swept repo-wide. Nothing in `python -m pytest
scripts/tests/` fails when an issue's prose names an active dependency
that's absent from its `blocked_by`/`depends_on` frontmatter — drift is
only caught issue-by-issue when `/ll:ready-issue` or `/ll:refine-issue`
happens to run against that specific file.

## Use Case

A backlog owner wants confidence that no open issue silently depends on
another issue without that dependency being enforced in frontmatter (which
gates automation like `ll-auto`/`ll-parallel` scheduling). Running `python
-m pytest scripts/tests/` should fail loudly if any issue in `.issues/` has
drifted, the same way any other regression is caught, rather than relying
on ad-hoc per-issue checks.

## Expected Behavior

A sweep over the active issue categories (`bugs`, `features`,
`enhancements`, `epics`) that reports every `prose_dep_drift`/
`stale_prose_dep` gap found, wired into the pytest suite so it fails CI
(this repo's local suite) if any issue drifts. Once built, fix this repo's
9 currently-drifting issues so the gate passes clean:

```
EPIC-2149→ENH-2148   FEAT-2414→FEAT-2413   ENH-2580→ENH-2581
ENH-2582→ENH-2581    EPIC-2457→ENH-2581    EPIC-2575→FEAT-2576
EPIC-2765→ENH-2762   FEAT-2416→FEAT-2413   EPIC-2257→BUG-2266
```

## Integration Map

- `scripts/little_loops/cli/issues/format_check.py` — add an `--all` flag
  (make `issue_id` optional, mirroring
  `cli/issues/epic_consistency.py:254-299`'s `epic_id`/`--all` shape) that
  walks all active categories instead of a single issue path, reusing the
  `find_issues(config, status_filter=_ALL_STATUSES)` result set already
  computed on the single-issue path (`format_check.py:55-57`)
- `scripts/little_loops/issues/anchor_sweep.py:29,100-120` —
  `_ACTIVE_CATEGORIES` + per-file `OSError`-isolation walk shape to copy
  inline (not importable directly; `sweep_issues()` is hardwired to
  anchor-rewriting)
- No new entry point: no `pyproject.toml`, `cli/__init__.py`, `doctor.py`,
  `writers._LL_PERMISSIONS`, or `areas.md` changes — `ll-issues` is a
  single wildcard-permitted console script covering all subcommands

### Tests
- `scripts/tests/test_ll_issues_format_check.py` — extend in place; its
  existing `format_check_dir` fixture (lines 51-60) already builds a
  multi-category temp `.issues/` tree, so new `--all` cases (drift in
  some categories, per-file reporting) fit the existing file rather than
  needing a new test module

### Behavioral Side Effect
- `scripts/little_loops/loops/rn-remediate.yaml:98-113` — the
  `ensure_formatted` gate checks `check_format_gaps(...).has_gaps` via
  `exit_code` only (not per-category), so any issue with prose-dependency
  drift will start routing to `format_issue` remediation once the new gap
  kinds land (from FEAT-2849) — an intentional but repo-wide behavior
  change worth calling out in this issue's PR description, not a file to
  edit.

## Implementation Steps

1. Add `--all` to `format-check` following `epic-consistency --all`'s
   optional-ID shape, using `anchor_sweep.py`'s `_ACTIVE_CATEGORIES` +
   per-file `OSError`-isolation walk shape as the driver template.
2. Wire the sweep into `python -m pytest scripts/tests/` per the
   no-hosted-CI policy.
3. Fix this repo's 9 drifting issues so the gate passes.

## Acceptance Criteria

- [x] The repo-wide sweep runs under `python -m pytest scripts/tests/` and
      passes once this repo's 9 drifting issues are corrected.
- [x] No GitHub Actions workflow is added.

## Impact

- **Users**: backlog owners adopting this on an existing project get an
  upfront report of which issues drifted before the rule existed, instead
  of discovering them one mis-scheduled issue at a time.
- **Risk**: Low. Purely additive to the pytest suite.
- **Effort**: Small-Medium, once FEAT-2849 lands.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` § Testing & CI Policy | Gate belongs in the local pytest suite |
| `scripts/little_loops/issues/anchor_sweep.py` | Repo-wide walk driver shape to copy |
| `scripts/little_loops/cli/issues/epic_consistency.py` | `--all` mode precedent to follow |

## Context

Decomposed from FEAT-2846 by `/ll:issue-size-review` (score 11/11, Very
Large), split out from FEAT-2849 (extractor + gap taxonomy) since the sweep
is independently shippable once the gap kinds exist.

## Session Log
- `/ll:manage-issue` - 2026-07-27T04:00:14Z - `d17c4b30-0380-48ea-be95-6305fc9f01be.jsonl`
- `/ll:ready-issue` - 2026-07-27T03:47:03 - `61211a38-756e-43ca-b859-39a67cf269d0.jsonl`
- `/ll:decide-issue` - 2026-07-27T03:43:42 - `f76e76e0-9586-4069-85db-45f1e1d5091c.jsonl`
- `/ll:issue-size-review` - 2026-07-26T00:00:00 - `52f8c37a-8768-4813-8704-c3364dbd6e28.jsonl`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-07-27
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli/issues/format_check.py`: made `issue_id`
  optional, added `--all`/`-a` sweeping every active issue (default
  `find_issues` status filter — excludes done/cancelled/deferred) via
  `check_format_gaps`, text and JSON output for the aggregate report.
- `scripts/tests/test_ll_issues_format_check.py`: added
  `TestFormatCheckAll` (no-args error, clean sweep, gapped-issue-only
  reporting, JSON output).
- `scripts/tests/test_prose_dep_sweep_gate.py`: new pytest gate that
  sweeps this repo's real `.issues/` tree and fails if any active issue
  has `prose_dep_drift`/`stale_prose_dep`.
- Reworded prose in 9 issues to remove stale "Depends on"/"blocked by"
  phrasing pointing at now-done issues (`FEAT-2414`, `FEAT-2416`,
  `FEAT-2850`, `FEAT-2851`, `ENH-2847`, `EPIC-2457`, `EPIC-2575`,
  `EPIC-2765`, `EPIC-2257`), and added a `blocked_by: [ENH-2148]` edge to
  `EPIC-2149` for its one still-active prose dependency.

### Verification Results
- Tests: PASS (16487 passed, 42 skipped)
- Lint: not run (no source style changes beyond the new module)
- Types: not run
- Integration: PASS (`test_prose_dep_sweep_gate.py` passes clean against
  the live `.issues/` tree)

## Status

done
