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
---

# ENH-2924: find_project_root should prefer a .git ancestor over the nearest .ll directory

## Summary

`find_project_root()` (`scripts/little_loops/issues/program_design.py:296`) resolves a project root as the *nearest ancestor containing a `.ll` directory*. Any `ll-*` command invoked from a subdirectory creates a stray `.ll/` there, and from then on every issue beneath that directory resolves to the wrong root — `git_grep_resolver` runs `git grep` from the stray location, resolves nothing, and the Program Design gate mass-fails issues on "no call-path anchor resolves against the repo" regardless of design quality. ENH-2870 flagged this as a latent trap and scoped the fix out; this is that follow-up, now live because the gate is armed in this repo (stamp dated 2026-07-30).

## Current Behavior

`find_project_root(start)` walks `start` and its parents and returns the first candidate where `(candidate / ".ll").is_dir()`. Stray `.ll/` directories are created as a side effect of running `ll-*` commands from a subdirectory (this repo grew four new strays — `scripts/.ll`, `scripts/little_loops/.ll`, `skills/.ll`, `hooks/adapters/opencode/.ll` — within two days of a previous 50-dir cleanup on 2026-07-27). With the program-design gate armed, a stray `.ll` between an issue file and the true root makes `program_design_gate_active()`'s grader fail every Call Path anchor; ENH-2870 verified empirically that a perfectly specific section grades `is_specific=False` under a shadowed root. The dirs are unignored-by-default side effects, so the failure arrives silently and regenerates after every manual cleanup.

## Expected Behavior

Project-root resolution does not trust the nearest `.ll` blindly. When a `.git` ancestor exists above `start`, the root is the highest ancestor that still contains `.ll` (equivalently: the `.git` root when it also has `.ll`), and a nearer `.ll` without `.git` is treated as a stray and skipped — or, at minimum, resolution prefers the `.git` ancestor over a `.ll`-only ancestor when both exist. Non-git projects keep working exactly as today (nearest `.ll` wins when no `.git` ancestor exists). A regression test plants a stray `.ll` in a subdirectory of a real repo and asserts resolution still returns the repo root.

## Motivation

The gate's fail-open design exists to prevent mass-defer for reasons unrelated to design quality — a shadowed root reproduces exactly that failure mode *with the gate armed*, the moment anyone runs an `ll-*` command from the wrong working directory. Manual cleanup is a treadmill: the strays regenerate by design of the CLIs, and every consuming project (not just this repo) carries the same trap. Fixing resolution removes the class instead of policing its symptoms.

## Proposed Solution

In `find_project_root()`, collect all ancestors of `start` containing `.ll`; if any ancestor (up to the filesystem root or the first `.git`-bearing ancestor) contains `.git`, return the outermost `.ll`-bearing ancestor at or within the `.git` root. Concretely: prefer the candidate that also has a `.git` sibling entry; fall back to nearest `.ll` when no `.git` exists anywhere above (preserving behavior for non-git installs). Keep the function total and side-effect-free as today — it currently never raises, and `OSError` on `start.resolve()` returns `None`.

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
- `scripts/tests/test_program_design_gate.py` — new case: stray `.ll` in a subdirectory of a `tmp_path` git repo still resolves to the repo root; plus a non-git fallback case asserting nearest-`.ll` behavior is unchanged

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

**Out of scope:** auditing or changing other root-discovery helpers beyond noting them in the PR; deleting existing stray `.ll` dirs automatically (a separate hygiene question); any change to the stamp, grandfathering, or fail-open semantics.

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
