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

`find_project_root()` (`scripts/little_loops/issues/program_design.py:296`) resolves a project root as the *nearest ancestor containing a `.ll` directory*. When a stray `.ll/` sits between an issue file and the true repo root, the resolved root carries no `.ll/program-design-cutover.json` stamp, so `program_design_gate_active()` returns `False`, `_apply_program_design_gate()` drops `## Program Design` from the required set, and `check_format_gaps()` never grades the section at all — **the armed gate silently disables itself**. The same nearest-`.ll` rule also lets resolution escape *above* the repository entirely: a consuming project with no root `.ll` but a `~/.ll` present resolves to `$HOME`. ENH-2870 flagged the nearest-`.ll` rule as a latent trap and scoped the fix out; this is that follow-up.

## Current Behavior

`find_project_root(start)` walks `start` and its parents and returns the first candidate where `(candidate / ".ll").is_dir()`. Both call sites (`program_design.py:384`, `:406`) pass the **issue file's path**, so only ancestors of the issue file can shadow resolution — `.issues/.ll` or `.issues/bugs/.ll`, not a stray elsewhere in the tree.

Downstream of a shadowed root the gate turns *off*; it does not fail. The chain:
`read_cutover_stamp(<stray>)` → `None` → `program_design_gate_active()` → `False` → `SECTION_TITLE` removed from `required` (`issue_parser.py:87-89`) → `grade_issue_section()` never called (`issue_parser.py:358-361`). Reproduced on a scratch repo with a stamp at the root and an issue whose Program Design anchors are deliberately bogus: `active True` before, `active False` after `mkdir .issues/.ll`, same issue file, no diagnostic either way.

**Correction to the originally captured framing.** This issue was first written as "the gate mass-fails issues on *no call-path anchor resolves against the repo* regardless of design quality." That symptom is not reachable. Grading only runs when a stamp was found at the resolved root, so a wrong root always means "no stamp → no grading." Wrong-root under-resolution is real in isolation — `git_grep_resolver` passes `cwd=root` and `git grep` is limited to the cwd subtree, so a root of `scripts/` cannot see symbols in `hooks/` — but no code path reaches it. The defect is fail-open, not fail-closed, and that is the more dangerous shape for an armed gate.

Stray `.ll/` directories are created as a side effect of running certain `ll-*` commands and hooks from a subdirectory (this repo grew `scripts/.ll`, `scripts/little_loops/.ll`, `skills/.ll`, `hooks/adapters/opencode/.ll` within two days of a 50-dir cleanup on 2026-07-27). **None of those observed strays is an ancestor of an issue file**, so none has actually shadowed the gate yet. The generation-side root cause is ENH-2927.

Visibility differs by audience and both framings have been used loosely: *this* repo ignores nested strays via a `**/.ll/` pattern (`.gitignore:126-131`), so they accumulate silently here; a **consuming** project gets no such pattern from `ll-init` (`init/writers.py:17-23`), so strays there surface as untracked noise. ENH-2927 owns closing that half.

## Expected Behavior

Project-root resolution does not trust the nearest `.ll` blindly, and never resolves outside the repository.

**Selection rule:** walk ancestors nearest-out and return the first candidate that contains both `.ll` and `.git`; if no ancestor has both, fall back to the nearest `.ll`-only candidate seen during the same walk. **The walk terminates after examining the first candidate that contains `.git`** — candidates above the repository boundary are never considered, by either arm of the rule.

`.git` presence is checked with `.exists()`, NOT `is_dir()` — in git worktrees and submodules `.git` is a *file*, and this project runs heavily inside worktrees (`ll-parallel`, epic branches).

Consequences of the rule:

- A stray `.ll` in a plain subdirectory is skipped (repo root has both and wins).
- A monorepo subproject (`.git` only at repo root, legit `.ll` at `packages/foo/`) keeps resolving to `packages/foo` via the fallback.
- A worktree checkout with its own `.git` file and `.ll` resolves to itself (correct — it is a real project).
- A git repo with **no** `.ll` anywhere between the start path and the repo root returns `None` instead of an out-of-repo ancestor like `$HOME`. `None` is already a supported return; `program_design_gate_active()` treats it as gate-off (identical to today's `$HOME` outcome, which has no stamp either) and `grade_issue_section()` falls back to `Path.cwd()`.
- Non-git projects keep nearest-`.ll` semantics unchanged.

## Motivation

An armed gate that silently switches itself off is worse than one that fails loudly: issues ship without the design-specificity check and nothing reports it. The stamp is opt-in per project and every consuming project carries the same resolution rule, so the hole travels with the plugin — and the escape-above-the-repo case needs no stray at all to trigger.

Manual stray cleanup is a treadmill: the dirs regenerate by design of the CLIs and hooks, so fixing resolution removes the class instead of policing symptoms. It also gives ENH-2927 a single, correct rule to build `resolve_ll_dir()` on.

## Proposed Solution

**Move `find_project_root()` into a new core module `scripts/little_loops/paths.py`**, re-exporting it from `little_loops.issues.program_design` so existing imports keep working. Placement is load-bearing, not cosmetic: ENH-2927 builds `resolve_ll_dir()` on this rule and routes `session_store`, hook state files, and the queue DB through it. Those layers must not import from `little_loops.issues.program_design` — wrong dependency direction, and it drags issue-parsing imports into the hot PostToolUse hook path. Landing the module here means ENH-2927 *consumes* it instead of re-homing it a week later.

The rule, single pass over `(current, *current.parents)`:

1. If `(candidate / ".ll").is_dir() and (candidate / ".git").exists()` → return `candidate`.
2. Otherwise, if `(candidate / ".ll").is_dir()` and nothing is remembered yet → remember `candidate`.
3. If `(candidate / ".git").exists()` → stop the walk after this candidate (repository boundary).
4. On completion, return the remembered `.ll`-only candidate, else `None`.

Keep the function total and side-effect-free as today — it never raises, and `OSError` on `start.resolve()` returns `None`.

Alternative considered and rejected in ENH-2870: deleting stray dirs before arming (done manually, 2026-07-29) — treats symptoms; the dirs regenerate on the next mis-rooted invocation.

## Program Design

### Signatures

- `def find_project_root(start: Path) -> Path | None` — moved verbatim in signature to `little_loops.paths`; behavior per the rule above.

### Call Path

`check_format_gaps` -> `program_design_gate_active` -> `find_project_root` -> `read_cutover_stamp`

`check_format_gaps` -> `grade_issue_section` -> `find_project_root` -> `git_grep_resolver`

## Integration Map

### Files to Modify
- `scripts/little_loops/paths.py` — **new**; home for `find_project_root()` with the `.git`-aware rule
- `scripts/little_loops/issues/program_design.py` — delete the local definition (line 296), re-export from `little_loops.paths`

### Dependent Files (Callers/Importers)
- `program_design_gate_active()` and `grade_issue_section()` (`program_design.py:384`, `:406`) — the only in-repo callers; both inherit the fix with no signature change
- `git_grep_resolver()` — resolves against the returned root; wrong-root input is the failure being fixed
- ENH-2927's `resolve_ll_dir()` — future consumer; the reason for the `paths.py` placement

### Similar Patterns
- `_config_db_path()` (`scripts/little_loops/session_store/db.py:47`) anchors at `root = Path.cwd()` with no upward walk at all
- `BRConfig.__init__` (`scripts/little_loops/config/core.py:214`) takes `project_root` and every caller passes `Path.cwd()`; `resolve_config_path()` probes that one directory only

  Both are the same nearest-/no-upward-resolution assumption class. **Out of scope here** — they are creation-side and owned by ENH-2927 — but note them in the PR.

### Tests
- `scripts/tests/test_program_design_gate.py` — new cases:
  - (a) **the regression that matters**: stray `.ll` planted at `.issues/` inside a stamped `tmp_path` git repo, assert `program_design_gate_active()` is still `True` (not merely that `find_project_root` returns the repo root)
  - (b) stray `.ll` in a subdirectory of a `tmp_path` git repo still resolves to the repo root
  - (c) non-git fallback asserting nearest-`.ll` behavior is unchanged
  - (d) worktree-style root where `.git` is a *file* still wins over a stray `.ll` below it
  - (e) monorepo subproject (`.git` only at repo root, `.ll` only at `packages/foo/`) still resolves to `packages/foo`
  - (f) repository boundary: git repo with no `.ll` at or below the repo root and a `.ll` in an ancestor *above* it resolves to `None`, not the ancestor
- Import-surface check that `from little_loops.issues.program_design import find_project_root` still works after the move

### Documentation
- N/A — behavior-contract clarification only; the module docstring's fail-open contract is unchanged

### Configuration
- N/A

## Implementation Steps

1. Add the failing regression test (a): stray `.ll` at `.issues/` silently disables the gate in a stamped repo.
2. Create `scripts/little_loops/paths.py` with `find_project_root()` implementing the `.git`-preferring rule plus the repository-boundary stop.
3. Replace the definition in `program_design.py` with a re-export; verify both call sites are unchanged.
4. Add tests (b)–(f).
5. Run `scripts/tests/test_program_design_gate.py` and `scripts/tests/test_ll_issues_format_check.py`.

## Scope Boundaries

**In scope:** the `find_project_root()` selection rule, its relocation to `little_loops.paths` with a compatibility re-export, and regression coverage for its two callers.

**Out of scope:** changing `_config_db_path()` / `BRConfig` / any other cwd-anchored resolver beyond noting them in the PR; deleting existing stray `.ll` dirs automatically; stopping `ll-*` CLIs and hooks from *creating* stray `.ll/` dirs at cwd — that generation-side root cause is ENH-2927, which builds on `paths.py`; any change to the stamp, grandfathering, or fail-open grading semantics.

## Impact

- **Priority**: P2 — a fail-open hole in a gate that is armed in this repo (stamp dated 2026-07-30). Note honestly that **no currently-observed stray triggers it**: every stray this repo has grown lives outside `.issues/`, so the issue-file-ancestor path has not been hit. What *is* reachable today, in this repo and every consuming one, is the resolve-above-the-repo case (`~/.ll` with no root `.ll`). The recurring pollution itself is ENH-2927's to stop.
- **Effort**: Small — one function, one new module, six tests.
- **Risk**: Low — behavior changes only for repos with stray `.ll` dirs (currently mis-resolving anyway) and for the out-of-repo escape (which returns `None`, an already-handled value). Non-git projects keep today's semantics. Fail-open grading is untouched.
- **Breaking Change**: No — `find_project_root()`'s signature and `None` contract are unchanged, and the old import path is preserved by re-export.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | Documents `program_design_nonspecific` gap and the stamp/grandfathering contract this resolution feeds |
| `docs/reference/ISSUE_TEMPLATE.md` | Documents the Program Design section requirement gated on the stamp |

## Session Log
- `/ll:capture-issue` - 2026-07-30T02:42:00 - `ba37c1f1-3ebb-4deb-b221-37ec4088bdda.jsonl`
- review - 2026-07-30 - corrected inverted failure mode (fail-open, not mass-fail) after reproduction; added repository-boundary rule and `paths.py` placement

## Status

**Open** | Created: 2026-07-29 | Priority: P2
