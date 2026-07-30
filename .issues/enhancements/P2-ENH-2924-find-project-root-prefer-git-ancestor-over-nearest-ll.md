---
id: ENH-2924
title: find_project_root should prefer a .git ancestor over the nearest .ll directory
type: ENH
status: done
priority: P2
captured_at: '2026-07-30T02:42:00Z'
completed_at: '2026-07-30T22:39:38Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- robustness
- program-design-gate
relates_to:
- ENH-2852
- ENH-2870
- ENH-2927
confidence_score: 96
outcome_confidence: 87
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Direct precedent for the module-relocation + re-export shim**: `scripts/little_loops/fsm/loop_paths.py` was relocated from `cli/loop/_helpers.py` under ENH-2773 for the identical reason cited here — so lower-level modules (`fsm/validation.py`, `fsm/executor.py`, `fsm/fragments.py`) could resolve paths without a `cli -> fsm -> cli` import cycle. `cli/loop/_helpers.py` re-exports the names for backward compatibility (`from little_loops.fsm.loop_paths import get_builtin_loops_dir, resolve_loop_path`), and its docstring documents the move — the exact shape to follow for `paths.py`. Other same-shape shims: `issue_discovery/matching.py:11-13` and `git_operations.py:15-19`, both `# noqa: F401` re-exports with a one-line "promoted to X" comment.
- **`.exists()` over `.is_dir()` for `.git` is already established elsewhere**, backing the issue's stated worktree-safety rationale: `session_store/lifecycle.py:1051` (`(repo_root / ".git").exists()`), and `pytest_history_plugin.py:54-58` explicitly comments *"A linked git worktree has a .git *file* pointing at the parent repo"* before checking `git_marker.is_file()`. `host_runner.py:355-362` (and `:648`, `:974`) reads the worktree `.git` file's `gitdir:` pointer directly.
- **Dependency-free core-module precedent** for where `paths.py` should sit: `text_utils.py`, `file_utils.py`, and `frontmatter.py` all live directly under `scripts/little_loops/` with no imports from `issues/` or other subsystems — the same tier `paths.py` is proposed for.

## Program Design

### Signatures

- `def find_project_root(start: Path) -> Path | None`

Moved verbatim (signature unchanged) to `little_loops.paths`; behavior per the rule above.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `issue_parser.py:_gate_program_design()` (line 73) is the intermediate caller between `check_format_gaps()` and `program_design_gate_active()`/`grade_issue_section()`, not named in the Call Path above — it dispatches to both and is the actual site `ll-issues format-check` (`cli/issues/format_check.py`) reaches through. No fix is needed there; noted for completeness since it's the full chain an implementer would trace.
- Confirmed via `Glob "**/paths.py"`: no `scripts/little_loops/paths.py` exists yet, so the proposed new module has no naming collision.
- Repo-wide grep for `find_project_root` confirms it has exactly the two in-repo callers already listed — no other module imports or calls it today.

### Similar Patterns
- `_config_db_path()` (`scripts/little_loops/session_store/db.py:47`) anchors at `root = Path.cwd()` with no upward walk at all
- `BRConfig.__init__` (`scripts/little_loops/config/core.py:214`) takes `project_root` and every caller passes `Path.cwd()`; `resolve_config_path()` probes that one directory only

  Both are the same nearest-/no-upward-resolution assumption class. **Out of scope here** — they are creation-side and owned by ENH-2927 — but note them in the PR.

_Wiring pass added by `/ll:wire-issue`:_
- **Re-export shim shape**: use the `issue_discovery/matching.py:11-13` / `git_operations.py:15-19` convention — `from little_loops.paths import find_project_root  # noqa: F401` plus a one-line "moved to little_loops.paths (ENH-2924)" comment — not `fsm/loop_paths.py`'s docstring-only framing. `loop_paths.py`'s actual downstream consumer (`cli/loop/_helpers.py:27`) re-imports plainly with no `noqa`/comment because nothing external still imports through `_helpers.py`; this issue's own AC requires `from little_loops.issues.program_design import find_project_root` to keep working, which is the `matching.py`/`git_operations.py` shape, not `_helpers.py`'s.

### Tests
- `scripts/tests/test_program_design_gate.py` — new cases:
  - (a) **the regression that matters**: stray `.ll` planted at `.issues/` inside a stamped `tmp_path` git repo, assert `program_design_gate_active()` is still `True` (not merely that `find_project_root` returns the repo root)
  - (b) stray `.ll` in a subdirectory of a `tmp_path` git repo still resolves to the repo root
  - (c) non-git fallback asserting nearest-`.ll` behavior is unchanged
  - (d) worktree-style root where `.git` is a *file* still wins over a stray `.ll` below it
  - (e) monorepo subproject (`.git` only at repo root, `.ll` only at `packages/foo/`) still resolves to `packages/foo`
  - (f) repository boundary: git repo with no `.ll` at or below the repo root and a `.ll` in an ancestor *above* it resolves to `None`, not the ancestor
- Import-surface check that `from little_loops.issues.program_design import find_project_root` still works after the move

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `test_program_design_gate.py` already has the building blocks for cases (a)-(c): `_init_repo()`/`_commit_all()` (lines 94-103, real `git init` + config) and `_make_project()` (lines 106-127, builds `.issues/bugs/<file>` plus an optional `.ll/program-design-cutover.json` stamp) already compose a "stamped repo + issue file" fixture — case (a) only needs a stray `.ll` dir added under `.issues/` on top of the existing helper output.
- Case (d) (worktree-style `.git` file) has **no existing fixture to reuse** — every current `git worktree add` usage in the test suite (`test_cli_loop_worktree.py:51-77`, `test_worker_pool.py:642-664`) mocks the subprocess call rather than running real git. Build it either via a real `git worktree add` off `tests/helpers.py:copy_git_template()`, or a hand-written `.git` file (`(path / ".git").write_text("gitdir: ...")`), matching the read-side pattern at `host_runner.py:356-360`.
- `tests/helpers.py:copy_git_template()` is a faster, cached alternative to `_init_repo()` for a plain (non-worktree) git repo fixture if per-test `git init` overhead matters — used by `test_merge_coordinator.py`'s `temp_git_repo` fixture and `test_worktree_utils.py:_init_repo`.

_Wiring pass added by `/ll:wire-issue`:_
- **Import-surface check pattern**: follow `test_fsm_loop_paths.py:57-61` (`test_cli_helpers_reexports_resolve_loop_path_and_builtin_dir`) or `test_config.py:2929-2933` (`test_reexported_from_config_package`) — both use `is` identity comparison (`from little_loops.paths import find_project_root as _new; from little_loops.issues.program_design import find_project_root as _old; assert _old is _new`), not just "import doesn't raise". This is the established convention for module-relocation-with-reexport tests in this suite.
- **Second worktree `.git`-file precedent** for case (d), independent of `test_worktree_utils.py:_init_repo`: `test_pytest_history_plugin.py:164-169` (`TestEnvLabel.test_worktree_detection`) plants `(tmp_path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n")` in a `tmp_path` with no real git repo — a lighter-weight fixture than a real `git worktree add` if that's preferred.
- **Regression-watch, not expected to break**: `test_ll_issues_format_check.py::TestFormatCheckProgramDesign` (already covered by Implementation Steps step 5's test run) exercises the gate via CLI subprocess using the shared `temp_project_dir` fixture (`conftest.py:238-245`, `.ll`-only, no `.git`) — stays on the unchanged nearest-`.ll` fallback branch under the new rule.

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

## Confidence Check Notes

**Readiness Score**: 96/100 | **Outcome Confidence**: 87/100 | **Recommendation**: STOP — ADDRESS GAPS (Program Design hard override)

### Gaps to Address

- Program Design: no signature-shaped line found in Types/Signatures. The deterministic linter (`parse_signature_lines` / `_SIG_CALL` in `scripts/little_loops/issues/program_design.py`) requires a signature-shaped line to end at the closing backtick (plus only trailing punctuation) — see `_TAIL` (line 60). This issue's `### Signatures` line is:
  `` - `def find_project_root(start: Path) -> Path | None` — moved verbatim in signature to `little_loops.paths`; behavior per the rule above. ``
  The trailing em-dash commentary after the closing backtick keeps the whole line from matching `_SIG_CALL`, so `program_design_nonspecific` fires even though the section is substantively specific. Remedy: put the bare signature on its own line/bullet (e.g. `` `def find_project_root(start: Path) -> Path | None` `` with the commentary moved to a following sentence or a separate bullet), then re-run `ll-issues format-check ENH-2924 --format json` to confirm `program_design_nonspecific` clears.

## Resolution

Implemented per the Program Design section with no deviations. `find_project_root()`
moved to a new `scripts/little_loops/paths.py` (dependency-free core module) with the
`.git`-preferring rule plus repository-boundary stop; `little_loops/issues/program_design.py`
now re-exports it (`# moved to little_loops.paths (ENH-2924)`) so the existing import
path keeps working. Added the regression test (stray `.ll` under `.issues/` no longer
disables the gate) plus the five selection-rule cases (subdirectory stray, non-git
fallback, worktree `.git` file, monorepo subproject, repository-boundary escape) and an
identity re-export check, all in `scripts/tests/test_program_design_gate.py`. Also fixed
the issue's own `### Signatures` line (flagged by `/ll:confidence-check`'s Program
Design gap) so `program_design_nonspecific` clears under `ll-issues format-check`.

Verified: `python -m pytest scripts/tests/` (17201 passed, 42 skipped), `ruff check
scripts/`, `mypy` on the two touched modules, and `ll-issues format-check ENH-2924`
all clean.

## Session Log
- `/ll:manage-issue` - 2026-07-30T22:39:08 - `4369e7a5-639c-4313-9dd7-2a38bb64f8a5.jsonl`
- `/ll:ready-issue` - 2026-07-30T22:31:13 - `9492e353-092b-4d57-ae58-7ab8bc275aea.jsonl`
- `/ll:confidence-check` - 2026-07-30T22:29:46 - `78dbb450-d82d-4a20-b0f8-1a839a614161.jsonl`
- `/ll:wire-issue` - 2026-07-30T22:26:54 - `c345b710-b333-4ed6-8c27-a96125529df7.jsonl`
- `/ll:refine-issue` - 2026-07-30T22:20:11 - `b1c6841f-d169-4ac2-bf72-a16ff2f50955.jsonl`
- `/ll:capture-issue` - 2026-07-30T02:42:00 - `ba37c1f1-3ebb-4deb-b221-37ec4088bdda.jsonl`
- review - 2026-07-30 - corrected inverted failure mode (fail-open, not mass-fail) after reproduction; added repository-boundary rule and `paths.py` placement

## Status

**Open** | Created: 2026-07-29 | Priority: P2
