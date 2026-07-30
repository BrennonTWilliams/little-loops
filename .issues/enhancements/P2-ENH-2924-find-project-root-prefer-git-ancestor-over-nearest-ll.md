---
id: ENH-2924
title: find_project_root should prefer a .git ancestor over the nearest .ll directory
type: ENH
status: open
priority: P2
captured_at: '2026-07-30T02:42:00Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- robustness
- program-design-gate
relates_to:
- ENH-2852
- ENH-2870
- ENH-2927
---

# ENH-2924: find_project_root should prefer a .git ancestor over the nearest .ll directory

## Summary

`find_project_root()` (`scripts/little_loops/issues/program_design.py:296`) resolves a project root as the *nearest ancestor containing a `.ll` directory*. Any `ll-*` command invoked from a subdirectory creates a stray `.ll/` there, and from then on every issue beneath that directory resolves to the wrong root — `git_grep_resolver` runs `git grep` from the stray location, resolves nothing, and the Program Design gate mass-fails issues on "no call-path anchor resolves against the repo" regardless of design quality. ENH-2870 flagged this as a latent trap and scoped the fix out; this is that follow-up, now live because the gate is armed in this repo (stamp dated 2026-07-30).

## Current Behavior

`find_project_root(start)` walks `start` and its parents and returns the first candidate where `(candidate / ".ll").is_dir()`. Stray `.ll/` directories are created as a side effect of running `ll-*` commands from a subdirectory (this repo grew four new strays — `scripts/.ll`, `scripts/little_loops/.ll`, `skills/.ll`, `hooks/adapters/opencode/.ll` — within two days of a previous 50-dir cleanup on 2026-07-27). With the program-design gate armed, a stray `.ll` between an issue file and the true root makes `program_design_gate_active()`'s grader fail every Call Path anchor; ENH-2870 verified empirically that a perfectly specific section grades `is_specific=False` under a shadowed root. The dirs are unignored-by-default side effects, so the failure arrives silently and regenerates after every manual cleanup.

## Expected Behavior

Project-root resolution does not trust the nearest `.ll` blindly. The selection rule, precisely: **walk ancestors nearest-out and return the first candidate that contains both `.ll` and `.git`; if no ancestor has both, fall back to today's nearest-`.ll` behavior.** `.git` presence is checked with `.exists()`, NOT `is_dir()` — in git worktrees and submodules `.git` is a *file*, and this project runs heavily inside worktrees (`ll-parallel`, epic branches). Consequences of the rule: a stray `.ll` in a plain subdirectory is skipped (repo root has both and wins); a monorepo subproject (`.git` only at repo root, legit `.ll` at `packages/foo/`) keeps resolving to `packages/foo` via the fallback; a worktree checkout with its own `.git` file and `.ll` resolves to itself (correct — it is a real project); non-git projects keep nearest-`.ll` semantics unchanged. A regression test plants a stray `.ll` in a subdirectory of a real repo and asserts resolution still returns the repo root.

## Motivation

The gate's fail-open design exists to prevent mass-defer for reasons unrelated to design quality — a shadowed root reproduces exactly that failure mode *with the gate armed*, the moment anyone runs an `ll-*` command from the wrong working directory. Manual cleanup is a treadmill: the strays regenerate by design of the CLIs, and every consuming project (not just this repo) carries the same trap. Fixing resolution removes the class instead of policing its symptoms.

## Proposed Solution

In `find_project_root()`, walk `(current, *current.parents)` as today, but return the first candidate where `(candidate / ".ll").is_dir() and (candidate / ".git").exists()` (`.exists()`, not `is_dir()` — worktree/submodule `.git` is a file). Remember the first `.ll`-only candidate seen during the same walk; if the walk completes with no both-bearing ancestor, return that remembered nearest-`.ll` candidate (preserving behavior for non-git installs and monorepo subprojects). Single pass, keep the function total and side-effect-free as today — it currently never raises, and `OSError` on `start.resolve()` returns `None`.

Alternative considered and rejected in ENH-2870: deleting stray dirs before arming (done manually, 2026-07-29) — treats symptoms; the dirs regenerate on the next mis-rooted invocation.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/program_design.py` — `find_project_root()` (line 296)

### Dependent Files (Callers/Importers)
- `program_design_gate_active()` and `grade_issue_section()` (same module) — the only in-repo callers; both inherit the fix with no signature change
- `git_grep_resolver()` — resolves against the returned root; wrong-root input is the failure being fixed

### Similar Patterns
- Other root-finding helpers in the codebase (e.g. config/history discovery) should be checked for the same nearest-`.ll` assumption during implementation — scope the fix to `find_project_root` but note siblings in the PR

### Tests
- `scripts/tests/test_program_design_gate.py` — new cases: (a) stray `.ll` in a subdirectory of a `tmp_path` git repo still resolves to the repo root; (b) non-git fallback asserting nearest-`.ll` behavior is unchanged; (c) worktree-style root where `.git` is a *file* still wins over a stray `.ll` below it; (d) monorepo subproject (`.git` only at repo root, `.ll` only at `packages/foo/`) still resolves to `packages/foo`

### Documentation
- N/A — behavior-contract clarification only; the module docstring's fail-open contract is unchanged

### Configuration
- N/A

## Implementation Steps

1. Add the failing regression test (stray `.ll` shadows root inside a git repo).
2. Rework `find_project_root()` to prefer the `.git`-anchored root as above.
3. Add the non-git fallback test.
4. Run `scripts/tests/test_program_design_gate.py` and `test_ll_issues_format_check.py`.

## Scope Boundaries

**In scope:** `find_project_root()` root-selection logic and its two callers' regression coverage.

**Out of scope:** auditing or changing other root-discovery helpers beyond noting them in the PR; deleting existing stray `.ll` dirs automatically (a separate hygiene question); stopping `ll-*` CLIs from *creating* stray `.ll/` dirs at cwd in the first place — that generation-side root cause is captured separately as ENH-2927; any change to the stamp, grandfathering, or fail-open semantics.

## Impact

- **Priority**: P2 - the trap is live in this repo now that the gate is armed (stamp dated 2026-07-30); any subdirectory `ll-*` run can silently mass-fail newly-gated issues until the stray is noticed and removed.
- **Effort**: Small - one function plus two tests.
- **Risk**: Low - behavior changes only for repos with stray `.ll` dirs (currently broken anyway); non-git projects keep today's semantics. Fail-open grading is untouched.
- **Breaking Change**: No - `find_project_root()`'s signature and `None` contract are unchanged.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | Documents `program_design_nonspecific` gap and the stamp/grandfathering contract this resolution feeds |
| `docs/reference/ISSUE_TEMPLATE.md` | Documents the Program Design section requirement gated on the stamp |

## Session Log
- `/ll:capture-issue` - 2026-07-30T02:42:00 - `ba37c1f1-3ebb-4deb-b221-37ec4088bdda.jsonl`

## Status

**Open** | Created: 2026-07-29 | Priority: P2
