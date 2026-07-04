---
id: ENH-2467
title: "/ll:manage-issue skill should not include .issues/-only commits in changelog"
type: ENH
priority: P3
status: done
captured_at: '2026-07-03T04:36:39Z'
discovered_date: '2026-07-02'
discovered_by: capture-issue
labels: []
---

# ENH-2467: `/ll:manage-issue` skill should not include `.issues/`-only commits in changelog

## Summary

The `/ll:manage-issue` skill produces conventional-commit-style messages that include the issue ID, and its commits land in the user's changelog even when the commit only touched `.issues/` files (issue creation, status flips, session log appends, no source-code changes). These `.issues/`-only commits should be excluded from the changelog so the release notes reflect user-visible changes only.

## Current Behavior

When `/ll:manage-issue` runs to completion it emits a commit (see `### 3. Commit All Changes` at `skills/manage-issue/SKILL.md:450`) with the standard `feat|fix|enh(scope): description` header and an `[ISSUE-ID]: title` trailer. If the commit's `git diff --name-only` only contains files under `.issues/` (e.g., a status flip from `in_progress` back to `open`, or appending a Session Log line) the changelog generation downstream still surfaces it as a release entry because the conventional-commit subject line looks legitimate.

Concretely: the skill's commit step at `skills/manage-issue/SKILL.md:454-465` does not gate on whether source files were changed — it commits unconditionally whenever the issue lifecycle is complete — so purely-meta commits (issue housekeeping) leak into the changelog as if they were shipped features/fixes.

## Expected Behavior

Commits produced by `/ll:manage-issue` that touch **only** files under `.issues/` (no source, no docs, no tests, no config) should be excluded from the changelog. The commit itself can still exist in git history (so the issue lifecycle is auditable), but the changelog generator should skip it. Either:

- (a) the skill detects `.issues/`-only diffs and either skips the commit or rewrites the subject to a `chore(issues):` prefix that the changelog aggregator already filters; or
- (b) the changelog aggregator (the consumer of `manage-release`) filters out any commit whose `git diff --name-only <prev-tag>..HEAD` set is entirely under `.issues/`.

Approach (a) keeps the policy at the producer; approach (b) keeps it at the consumer. Either is acceptable as long as `.issues/`-only commits no longer appear in user-facing release notes.

## Motivation

The changelog is a user-facing artifact — it's the contract between a release and the people consuming the plugin. A release entry that reads `feat(issues): capture ENH-2467 about changelog filtering` is misleading: nothing about the plugin's *capabilities* changed, only the project's internal issue tracker. This:

- pollutes release notes with internal housekeeping that downstream users cannot act on,
- dilutes the signal-to-noise ratio of "what changed in this release,"
- makes regression analysis harder (counting "real" feature commits requires manually filtering `.issues/`-only entries).

Quantified impact: looking at recent history, a typical release touches 3–10 user-visible commits and a comparable number of `.issues/`-only commits (status flips during implementation, post-completion session log appends, refinements). Roughly 30–50% of `manage-issue` commits per release are `.issues/`-only.

## Proposed Solution

### Option A: Skill-side gate (producer-side) — Recommended

In `skills/manage-issue/SKILL.md:450` ("Commit All Changes"), insert a guard before the `git commit` invocation:

1. Compute `CHANGED=$(git diff --cached --name-only)` after the `git add`.
2. If every line in `$CHANGED` matches the glob `.issues/**`, rewrite the commit subject to `chore(issues): <action> <ISSUE-ID> <slug>` and append a note in the body explaining it was demoted because no source files were touched.
3. If mixed (some source, some `.issues/`), keep the conventional-commit subject but include the `.issues/` files as a sub-section of the body, which is the existing behavior.

Anchor-based refs:
- The commit block to gate: `skills/manage-issue/SKILL.md:450-465` (heading "Commit All Changes").
- Conventional-commit header style precedent: `scripts/little_loops/release.py` (or whichever module the changelog aggregator lives in — `ll-issues` + `manage-release` per `FEAT-268`).
- Existing `chore(issues):` prefix precedent: `ENH-1717` ("Auto-commit hooks on Issue file CRUD operations") already proposed this as the demoted prefix.

### Option B: Aggregator-side filter (consumer-side)

In the changelog generation step (driven by `FEAT-268` `/ll:manage-release` and `scripts/little_loops/release.py`), add a pre-filter:

```bash
# Inside the changelog generator, after gathering candidate commits:
for sha in "${candidate_shas[@]}"; do
  files=$(git diff-tree --no-commit-id --name-only -r "$sha")
  if [[ "$files" == $'\n'.issues/* || "$files" == *.issues/* ]]; then
    # all paths under .issues/ — skip
    continue
  fi
  emit_changelog_entry "$sha"
done
```

Anchor-based refs:
- Changelog aggregation entry point: `scripts/little_loops/release.py` (verify exact module path during implementation).
- Precedent for `--name-only`-based filtering: any existing `--diff-filter` or `--name-only` consumer in the release toolchain.

### Decision Guidance

Either approach is correct. Option A keeps the policy close to the producer and means any future changelog consumer benefits automatically. Option B is simpler to ship in one PR and doesn't require touching the skill prompt (which is more brittle to LLM-driven drift). Pick whichever is easier to test end-to-end — verify by running `/ll:manage-release` on a branch with mixed commits and confirming `.issues/`-only entries disappear.

## Scope Boundaries

- **In scope**: filtering `.issues/**` only from user-facing changelogs; preserving the commit in git history.
- **Out of scope**: filtering `.thoughts/**`, `.loops/**`, `.ll/**`, or other meta directories (separate follow-up if noise from those becomes an issue).
- **Out of scope**: rewriting the commit message format used by `/ll:commit` for non-`manage-issue` flows.
- **Out of scope**: any change to the `manage-issue` lifecycle logic (status flips, file moves) — only the commit-subject step is touched.

## Implementation Steps

1. **Investigate the actual aggregator site** — confirm whether the changelog is generated from raw `git log` (consumer-side filter applies) or by a structured producer signal (producer-side filter applies). Likely path: `scripts/little_loops/release.py` (verify during implementation).
2. **Pick the approach** (Option A vs B above) and document the choice in the issue before implementing.
3. **Implement the filter** — either the skill-side gate at `skills/manage-issue/SKILL.md:450` or the aggregator-side filter in the release toolchain.
4. **Add a test** — fixture with a mixed-commit history; assert `.issues/`-only commits do not appear in the rendered changelog. If Option A: a skill-level test using `tests/test_skills.py` or similar. If Option B: a unit test on the aggregator function.
5. **Update `docs/reference/`** — whichever module is touched gets a docs change; add a short note in the `manage-issue` skill explanation that `.issues/`-only commits are demoted.

## Impact

- **Priority**: P3 — quality-of-life improvement for release notes; no functional break.
- **Effort**: Small — single function change (filter) or single skill-prompt insert (gate); < 1 day.
- **Risk**: Low — git history is preserved; only the changelog surface changes. Worst case: a legitimate-but-.issues/-only commit (rare) is hidden from release notes; easy to recover by inspecting `git log` directly.
- **Breaking Change**: No — only the *content* of the rendered changelog changes, not its format or the release flow.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` (Option A) — gate the commit step at line 450.
- `scripts/little_loops/release.py` or the relevant aggregator module (Option B) — add a pre-filter.
- Whichever docs file covers the changelog generation step.

### Dependent Files (Callers/Importers)
- `commands/manage-release.md` and `skills/manage-release/` (FEAT-268) — consumes the aggregator; verify the filter interacts correctly with their wave-pattern flow.
- `scripts/little_loops/issue_lifecycle.py` — produces some of the `.issues/`-only commits via automated paths; ensure those also flow through the new gate.

### Similar Patterns
- `ENH-1717` (auto-commit hooks on Issue file CRUD) — proposed the `chore(issues):` prefix as the demoted prefix; coordinate so the prefix conventions match.
- BUG-942 (manage-release shows 0 completed issues due to date filter) — different problem but in the same module; coordinate the fix to avoid double-patching the changelog generator.

### Tests
- `scripts/tests/test_release.py` or equivalent — add a fixture with mixed `.issues/`-only and source commits.
- If Option A: a skill-level test verifying the commit-subject rewriting path.

### Documentation
- `docs/reference/API.md` — note the changelog filter behavior next to the aggregator function.
- `docs/development/TROUBLESHOOTING.md` (optional) — short note explaining why some commits are absent from release notes.

### Configuration
- N/A — the filter is unconditional. If we later need to surface `.issues/`-only commits (e.g., for an internal changelog), add a `--include-meta` flag, but that is out of scope here.

## Related Key Documentation

- `docs/ARCHITECTURE.md` — release/changelog architecture (if documented).
- `docs/reference/API.md` — release aggregator API.

## Resolution

Implemented **Option A (producer-side gate)** plus a consumer-side
defense-in-depth filter:

- `skills/manage-issue/SKILL.md` § 3 "Commit All Changes": after `git add`, the
  staged set is checked (`git diff --cached --name-only`); if every path is under
  `.issues/`, the commit subject is demoted to `chore(issues): <action> <ID> <slug>`
  with a body note. Mixed/source commits keep the conventional subject.
- `commands/manage-release.md` (Agent 1, step 4): changelog generation skips
  `chore(issues):` commits entirely (including Maintenance) and, as
  defense-in-depth, any commit whose `git diff-tree --name-only` set is entirely
  under `.issues/`. (There is no `scripts/little_loops/release.py` — the
  aggregator is the manage-release command prompt.)
- `docs/development/TROUBLESHOOTING.md`: new "Commit missing from release
  changelog" entry.
- Tests: `scripts/tests/test_manage_issue_changelog_gate.py` (contract pins on
  both markdown files + real-git behavioral tests of the gate snippet).

## Status

Done | Implemented 2026-07-03 (Option A + aggregator filter)

## Session Log

- `/ll:capture-issue` - 2026-07-03T04:36:39Z