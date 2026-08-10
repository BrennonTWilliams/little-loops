---
id: ENH-3114
title: worktree_copy_files silently skips directory entries while .claude/ gets a
  full copytree
type: ENH
priority: P4
status: done
parent: EPIC-3111
captured_at: '2026-08-08T20:32:03Z'
completed_at: '2026-08-10T05:03:40Z'
discovered_date: 2026-08-08
discovered_by: capture-issue
labels:
- worktree
- config
- dx
decision_needed: false
confidence_score: 96
outcome_confidence: 89
verify_verdict: VALID
score_complexity: 23
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 23
---

# ENH-3114: `worktree_copy_files` silently skips directory entries

## Summary

`setup_worktree` copies `.claude/` with a full `shutil.copytree`, but any
directory listed in `parallel.worktree_copy_files` is skipped with a log
warning. The config surface gives no hint that entries must be files, so a user
who lists a directory gets a worktree missing state they believe they configured
— visible only in the log.

## Current Behavior

`scripts/little_loops/worktree_utils.py:251-256`:

```python
if src.is_dir():
    logger.warning(
        f"Skipping '{file_path}' in copy_files: "
        "is a directory (use symlinks or copytree for directories)"
    )
    continue
```

Meanwhile `:236-243` unconditionally `copytree`s `.claude/`. So the module
plainly knows how to copy a directory into a worktree — it just refuses to do it
for user-configured entries. The warning's advice ("use symlinks or copytree")
is not actionable from a JSON config file.

The schema description at `config-schema.json:360` does not state the
files-only constraint.

## Expected Behavior

Either directories in `worktree_copy_files` are copied (matching the `.claude/`
treatment), or the constraint is enforced and explained where the user sets the
value — at config-validation time, not in a runtime log line.

## Motivation

This is a small inconsistency, but it's the kind that costs an afternoon: the
configured value is accepted, the run proceeds, and the missing directory
surfaces as a confusing downstream failure inside an autonomous worktree run
where nobody is reading the log.

## Proposed Solution

Preferred: **support directories** by branching on `src.is_dir()` and calling
`shutil.copytree(src, dest, dirs_exist_ok=True)`, mirroring the `.claude/` path.
This makes the config surface uniform and removes a special case rather than
documenting one.

Alternative, if directory copying is undesirable (cost, surprise on large
trees): validate `worktree_copy_files` entries against the schema/config loader
and reject or warn at config-load time, and state the files-only constraint in
`config-schema.json:360`.

Either way, keep the existing `.claude/` special case intact — the `startswith(".claude/")`
skip at `:247-248` prevents double work and should remain.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

**Prior art on this exact question**: this same field's directory-vs-file gap
was already decided once, in `.issues/bugs/P2-BUG-438-worktree-copy-files-crashes-on-directories.md`
(status: done). Before that fix, a directory entry in `worktree_copy_files`
hit `shutil.copy2()` directly and crashed the whole run with
`IsADirectoryError`. BUG-438 proposed two approaches: "Approach 1 (minimal
fix)" — an `is_dir()` guard that warns and skips — and "Approach 2 (full
feature)" — a separate `worktree_link_dirs` config field that symlinks
directories in. Only Approach 1 shipped; `worktree_link_dirs` was never
added. The `is_dir()`-skip-with-warning block this issue is about
(`worktree_utils.py:251-256`) is that exact fix, unchanged since. Whichever
path this issue takes should account for why the fuller feature (directory
support) was not chosen the first time this gap was visible.

**Existing tests encode today's warn-and-skip contract and will need
updating under either fix path**:
- `scripts/tests/test_cli_loop_worktree.py::TestSetupWorktree::test_copy_files_directory_skipped_with_warning` (`:317-352`)
- `scripts/tests/test_worker_pool.py::test_setup_worktree_skips_directory_entries` (`:916`, docstring references BUG-438)

Both create a real directory on disk, patch `shutil.copy2`/`shutil.copytree`
with recording side effects, and assert the directory is *not* copied and a
warning *is* logged. Under the "support directories" path these assertions
invert; under the "validate at config load" path they may need to move to a
config-loader test instead.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

> **Selected:** Option A — support directories via `copytree`, mirroring the `.claude/` path; scores higher on codebase-evidence fit than Option B (8/12 vs 5/12).

**Option A**: Support directories — branch on `src.is_dir()` and call
`shutil.copytree(src, dest, dirs_exist_ok=True)`, mirroring the `.claude/`
path. This makes the config surface uniform and removes a special case
rather than documenting one.

**Option B**: Validate and reject at config load — validate
`worktree_copy_files` entries against the schema/config loader and reject or
warn at config-load time, and state the files-only constraint in
`config-schema.json:360`. Either way, keep the existing `.claude/` special
case intact — the `startswith(".claude/")` skip at `:247-248` prevents
double work and should remain.

**Recommended**: Option A — makes the config surface uniform and removes a
special case rather than documenting one. Note the BUG-438 precedent above
cuts the other way: the codebase already chose "warn and skip" (closer to
Option B) once before, when a fuller directory-support feature
(`worktree_link_dirs`) was proposed and not built — worth weighing before
finalizing.

### Decision Rationale

_Added by `/ll:decide-issue` — 2026-08-08:_

**Selected: Option A** — support directories by branching on `src.is_dir()`
and calling `shutil.copytree(src, dest, dirs_exist_ok=True)`.

**Reasoning**: Option A directly mirrors the adjacent `.claude/` `copytree`
pattern already in `setup_worktree` (`worktree_utils.py:236-243`), keeping
the change small and self-contained with test impact isolated to two
already-identified tests. Option B has no precedent anywhere in
`scripts/little_loops/config/` for filesystem checks at load time — the
directly analogous `ScanConfig.focus_dirs` field is also loaded with zero
validation — and would require new plumbing to thread `project_root` into
the currently path-agnostic `ParallelAutomationConfig.from_dict()`, plus it
introduces environment-dependent config validity (a committed config could
pass on one machine and fail on another depending on what exists on disk).
Both options carry a residual risk: Option A reopens the BUG-438 cost
tradeoff (unbounded `copytree` vs. the shelved `worktree_link_dirs` symlink
approach) without a size guard; Option B leaves the `.claude/`-vs-user-entries
asymmetry unresolved, only documented.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2 | 1 |
| Simplicity | 2 | 1 |
| Testability | 3 | 2 |
| Risk | 1 | 1 |
| **Total** | **8/12** | **5/12** |

**Key evidence**:
- `.claude/` copytree precedent: `worktree_utils.py:236-243`
- `dirs_exist_ok=True` idiom already used elsewhere in the repo: `scripts/tests/helpers.py:68`
- No filesystem-validation precedent in `scripts/little_loops/config/`; `ScanConfig.focus_dirs` (`config/features.py:308,318`) is the closest analogous field and also validates nothing at load time
- BUG-438 (done) shipped only the warn-and-skip minimal fix; `worktree_link_dirs` (full directory-support feature) was proposed but never built — motivating case was `node_modules`-sized trees, which is the risk this option still carries without a size guard

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

Re-confirmed post-`e90dd5f6` (2026-08-09) — that commit touched only config defaults/schema/docs, not `worktree_utils.py`'s copy logic itself, so the design below is unchanged in substance; only line numbers shifted.

**Current implementation (re-verified):**
- `.claude/` copytree, `worktree_utils.py:246-253` — dest-exists strategy is still `shutil.rmtree(dest)` then plain `shutil.copytree(src, dest)` (replace, not merge) — `dirs_exist_ok=True` is still unused anywhere in this file.
- `copy_files` loop, `worktree_utils.py:255-272`; `is_dir()` warn-and-skip branch at `:261-266`, unchanged logic.
- `dirs_exist_ok=True` precedent re-confirmed still at `scripts/tests/helpers.py:68`; no other production use anywhere in `scripts/little_loops/`.

**Call sites re-confirmed accurate** (all pass user-configured `worktree_copy_files` through to `setup_worktree`'s `copy_files` param, so all are exposed to whichever fix path is chosen):
- `scripts/little_loops/fsm/executor.py:942,946`
- `scripts/little_loops/cli/loop/run.py:455,459,484,488`
- `scripts/little_loops/parallel/worker_pool.py:402,762,774,778`
- `scripts/little_loops/worktree_utils.py:381,451,455` (`verify_epic_branch_before_merge`) — always passes `copy_files=[]`, unaffected regardless of fix path.

**Risk-profile note**: `e90dd5f6` added `.ll/ll.local.md` as a third default `worktree_copy_files` entry. It is a file in every reference (`config/automation.py`, `parallel/types.py`, `config-schema.json`), so it goes through the existing `shutil.copy2` file branch and does not itself trigger the directory-skip bug. It does not change this issue's urgency directly, but it is evidence the config surface is actively growing, and it points users toward `.ll/` as a directory they may plausibly want to reference wholesale in future entries.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

Re-confirmed 2026-08-09 (post-`e90dd5f6`): current line numbers verified unchanged —
`.claude/` copytree block `worktree_utils.py:246-253`, `copy_files` loop `:255-272`,
`is_dir()` warn-and-skip branch `:261-266`. `dirs_exist_ok=True` is confirmed unused
anywhere in `worktree_utils.py` (grep returns zero matches); the `.claude/` dest-exists
strategy is `rmtree` then plain `copytree`, not merge-via-`dirs_exist_ok`.

Newly confirmed edge cases not previously documented, relevant to Implementation Steps:
- Neither the `.claude/` block nor the `copy_files` loop wraps `shutil.copytree`/`copy2`
  in a try/except — a permissions error during either copy raises uncaught.
- Neither block special-cases symlinks beyond Python's normal path-resolution semantics.
- A `copy_files` entry whose `src` does not exist at all is skipped silently at `logger.debug`
  level (`worktree_utils.py:270-272`), distinct from the `is_dir()` case's `logger.warning`.
  Whichever fix path is chosen should decide whether the new directory-copy branch should
  raise, warn, or stay silent on these same failure modes, since today's file-only path
  is silent on missing-src and unguarded on permissions/symlinks.

### Types
N/A — no new data types; this changes control flow inside the existing
`copy_files` loop, not any data shape.

### Signatures
- `setup_worktree(repo_path: Path, worktree_path: Path, branch_name: str, copy_files: list[str], logger: Logger, git_lock: GitLock, base_branch: str | None = None, checkout_existing: bool = False) -> None` — `scripts/little_loops/worktree_utils.py:157-166` — existing
  signature, unchanged shape under either fix path.
- Directory-skip branch (current behavior): `worktree_utils.py:251-256`
  (`if src.is_dir(): logger.warning(...); continue`).
- `.claude/` copytree precedent: `worktree_utils.py:236-243` — `shutil.copytree(claude_dir, dest_claude_dir)`,
  preceded by `shutil.rmtree(dest_claude_dir)` when the destination already
  exists (not `dirs_exist_ok=True` — that flag is unused anywhere in this
  file or module).
- Config plumbing: `ParallelAutomationConfig.from_dict()` —
  `scripts/little_loops/config/automation.py:91,130` — reads
  `worktree_copy_files` via bare `data.get(...)` with no shape or filesystem
  validation. Confirmed: no dataclass under `scripts/little_loops/config/`
  validates array-entry shape/existence at load time — `is_dir()`/`is_file()`
  checks against these entries happen only at `setup_worktree()` call time,
  after the worktree already exists.

### Call Path
`cmd_run` (`cli/loop/run.py:484`) / `WorkerPool::_setup_worktree`
(`parallel/worker_pool.py:774`) / `verify_epic_branch_before_merge`
(`worktree_utils.py:441`) → `setup_worktree()` (`worktree_utils.py:157`) →
copy_files loop (`worktree_utils.py:246-262`) → `src.is_dir()` branch (251)
[directory: warned and skipped today] or `shutil.copy2()` (260) [file:
copied].

### Decision Rules
N/A — no new gate, threshold, or keyword list; this changes existing
copy-loop control flow (copy vs. skip vs. reject a directory entry), not new
decision logic.

## Implementation Steps

1. Decide: copy directories, or validate-and-reject at config load.
2. If copying: branch on `is_dir()` → `copytree(..., dirs_exist_ok=True)`;
   consider whether to follow symlinks and whether to guard against very large
   trees.
3. Update `config-schema.json:360` to describe the accepted entry forms.
4. Test: a directory entry in `worktree_copy_files` lands in the worktree with
   its contents (or fails loudly at config load, per the chosen path).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Decide the dest-exists strategy for the new directory branch: the `.claude/` precedent does `rmtree` then `copytree` (`worktree_utils.py:240-243`), which is a different merge strategy than `dirs_exist_ok=True` (which merges into an existing destination rather than replacing it). Pick one deliberately rather than inheriting `dirs_exist_ok=True` by default.
- Update `scripts/tests/test_cli_loop_worktree.py::test_copy_files_directory_skipped_with_warning` (:317-352) — invert assertions per the Tests subsection above.
- Update `scripts/tests/test_worker_pool.py::test_setup_worktree_skips_directory_entries` (:916-962) — invert assertions per the Tests subsection above.
- Confirm `scripts/little_loops/fsm/executor.py` (:942-949) and `scripts/little_loops/worktree_utils.py:441-449` (`verify_epic_branch_before_merge`, always `copy_files=[]`) need no code change — behavior-inherited only.

## Integration Map

### Files to Modify
- `scripts/little_loops/worktree_utils.py` (:246-262)
- `scripts/little_loops/config-schema.json` (:360)
- `scripts/little_loops/config/automation.py` (:91) — if validation is added

### Dependent Files (Callers/Importers)
- All four `setup_worktree` call sites inherit the behavior change
- `scripts/little_loops/init/tui.py` (:395-430) — prompts for these entries

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` (:942-949, `_attach_sub_loop_to_new_worktree`) — the 4th `setup_worktree` call site; not enumerated in the issue's "all four" claim above. Passes `cfg.parallel.worktree_copy_files` straight through, so it inherits the behavior change with no code change of its own.
- `scripts/little_loops/cli/loop/run.py` (:456-491, `cmd_run`) — reads `_main_config.parallel.worktree_copy_files` and forwards it to `setup_worktree` (:484); no code change needed, confirms inheritance.
- `scripts/little_loops/parallel/worker_pool.py` (:762-781, `_setup_worktree`; called from `_process_issue` at :402) — thin delegating wrapper around `setup_worktree`; no directory logic of its own.
- `scripts/little_loops/worktree_utils.py` (:441-449, `verify_epic_branch_before_merge`) — always passes `copy_files=[]`; confirmed unaffected by this change regardless of which option is chosen.
- `scripts/little_loops/parallel/types.py` (:416-418) — a second dataclass (`ParallelConfig.worktree_copy_files`) mirrors `ParallelAutomationConfig`'s field and default (`[".claude/settings.local.json", ".env"]`) but was absent from "Files to Modify"; no code change is needed (it holds no directory-vs-file logic), but note it when updating the schema description so both mirrored fields stay in sync conceptually.

### Similar Patterns
- The `.claude/` `copytree` at `worktree_utils.py:236-243`

### Tests
- `scripts/tests/` — worktree_utils copy_files coverage

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_worktree.py::TestSetupWorktree::test_copy_files_directory_skipped_with_warning` (:317-352) — invert: patch `shutil.copytree` with a `side_effect` that captures `(src, dst, **kw)` (both tests currently leave `copytree` as a bare unrecorded `MagicMock`), then assert the directory entry's src appears in a captured call with `dirs_exist_ok=True`, and that `logger.warning` is *not* called for this path.
- `scripts/tests/test_worker_pool.py::TestWorkerPool::test_setup_worktree_skips_directory_entries` (:916-962, BUG-438 regression test) — invert: add a `shutil.copytree` side-effect capture; assert `node_modules` now goes through `copytree(dirs_exist_ok=True)` while `.env` still goes through `copy2`.
- Pattern to follow for both inversions: `scripts/tests/test_cli_loop_worktree.py::TestSetupWorktree::test_copies_claude_directory` (:105-135) — existing `.claude/` copytree test already captures `(src, dst)` via `side_effect`; extend it to also assert `dirs_exist_ok=True` in `**kw`, since today it doesn't check that kwarg.
- New test: nested-directory-contents correctness — none of the current mocked tests verify files *inside* a copied directory land correctly (e.g., `subdir/nested/file.txt`), since `copytree`/`copy2` are mocked in all existing coverage.
- New test: `dirs_exist_ok=True` merge behavior when the destination directory already exists — the `.claude/` block does `rmtree` then `copytree` (`worktree_utils.py:240-243`), a different dest-exists strategy than the new branch's merge-via-`dirs_exist_ok=True`. Worth a note in Implementation Steps (below) since it's an unaddressed design detail, not just a test gap.

### Documentation
- Worktree copy-semantics reference (ENH-3115)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (:535) and `docs/reference/CONFIGURATION.md` (:390) — both describe `worktree_copy_files` with generic "files" phrasing. Not factually broken by this change (no files-only claim to invalidate) and not test-gated, but optionally broaden to "files and directories" for completeness.

_Wiring pass added by `/ll:wire-issue` — 2026-08-09:_
- `scripts/little_loops/init/summary.py` (:83-85) — `/ll:init` summary row labels `worktree_copy_files` as `"Worktree files"`; once directories are supported the label is slightly imprecise. Cosmetic only, not test-gated, optional.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

Post-`e90dd5f6` (2026-08-09, "improve(worktree): copy .ll/ll.local.md into worktrees by default") line-number refresh — that commit did not touch `worktree_utils.py`'s copy logic, only config defaults/schema/docs, but shifted `worktree_utils.py` line numbers by ~+10:
- `.claude/` copytree block: now `worktree_utils.py:246-253` (was `:236-243`)
- `copy_files` loop: now `worktree_utils.py:255-272` (was `:246-262`)
- `is_dir()` warn-and-skip branch: now `worktree_utils.py:261-266` (was `:251-256`)
- `worktree_copy_files` schema entry: now `config-schema.json:360-367` (was `:360`); description now also mentions `.ll/ll.local.md`, still does not state a files-only constraint
- `config/automation.py`: field default `:91-93`, `from_dict()` fallback `:130-132` (both now default to `[".claude/settings.local.json", ".env", ".ll/ll.local.md"]`)
- `parallel/types.py`: field default `:416-418` (same three-entry default)
- Test line numbers: `test_cli_loop_worktree.py::test_copy_files_directory_skipped_with_warning` now `:351-386`; `test_worker_pool.py::test_setup_worktree_skips_directory_entries` now `:916-962`

Additional documentation sites not previously listed, now referencing `worktree_copy_files` post-`e90dd5f6` (none state a files-only constraint; all use generic "files" phrasing, so none are factually broken by either fix path):
- `docs/reference/API.md:528` (`ParallelAutomationConfig` field list), `:539` ("Files copied from main repo to each worktree"), `:3776` (`ParallelConfig` field list)
- `docs/reference/CONFIGURATION.md:66` (JSON example showing the three-entry default), `:390` (table entry, "Files to copy to worktrees")
- `docs/development/TROUBLESHOOTING.md:196` (references the default list including `.ll/ll.local.md`)

`.ll/ll.local.md` (the new default entry added by `e90dd5f6`) is a plain file in every reference — it goes through the existing `shutil.copy2` file branch and does not itself trigger the directory-skip bug this issue is about.

## Impact

- **Priority**: P4 - Papercut; affects only users who configure a directory entry
- **Effort**: Small - A branch in one loop plus a schema description
- **Risk**: Low - Additive, and the `.claude/` path proves the mechanism
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Scope Boundaries

**In scope:**
- The `copy_files` loop's `is_dir()` branch in `setup_worktree`
  (`worktree_utils.py:255-272`) — either add `copytree` support or reject
  directory entries at config-load time (per the selected Option A: support
  directories).
- `config-schema.json:360-367`'s `worktree_copy_files` description.
- The two existing tests that encode today's warn-and-skip contract
  (`test_cli_loop_worktree.py::test_copy_files_directory_skipped_with_warning`,
  `test_worker_pool.py::test_setup_worktree_skips_directory_entries`).

**Out of scope:**
- The `.claude/` directory copytree block (`worktree_utils.py:246-253`) —
  its `rmtree`-then-`copytree` dest-exists strategy stays as-is; this issue
  does not unify it with the new directory branch's `dirs_exist_ok=True`
  merge strategy.
- Building `worktree_link_dirs` (BUG-438's shelved symlink-based full
  feature) — Option A supersedes that path rather than reviving it.
- Adding filesystem-existence validation to `ParallelAutomationConfig` or
  any other config dataclass at load time (that's Option B, not selected).
- Worktree copy-semantics documentation (tracked separately as ENH-3115).

## Session Log
- `/ll:manage-issue` - 2026-08-10T05:03:20 - `0192a3f1-7768-4f04-9f28-d474919e03bf.jsonl`
- `/ll:ready-issue` - 2026-08-10T04:31:04 - `ef98cf35-0321-4be1-97c0-fcc88f4d772b.jsonl`
- `/ll:verify-issues` - 2026-08-10T04:26:05 - `898e24f1-f69b-4320-9ba3-5b57835c1c33.jsonl`
- `/ll:refine-issue` - 2026-08-10T04:23:54 - `ad74f91d-1816-4298-b5e5-53e59f11f056.jsonl`
- `/ll:verify-issues` - 2026-08-10T04:21:36 - `de51be75-90fc-46e3-9aed-637c7a015ced.jsonl`
- `/ll:wire-issue` - 2026-08-10T04:20:02 - `2b006bc7-530a-4604-8aa0-09cba0da2cd4.jsonl`
- `/ll:refine-issue` - 2026-08-10T04:14:14 - `90bbe8a8-e8eb-4150-97fe-093aad8f50fe.jsonl`
- `/ll:confidence-check` - 2026-08-08T22:20:09 - `a2db820a-06be-4e62-8550-037413f4d50e.jsonl`
- `/ll:wire-issue` - 2026-08-08T21:41:53 - `5c29eabe-8674-4e2a-8f5b-4edb546e0270.jsonl`
- `/ll:decide-issue` - 2026-08-08T21:25:16 - `b38ce9a8-ea1d-4784-ba74-81f9cf6e4c56.jsonl`
- `/ll:refine-issue` - 2026-08-08T21:09:24 - `cdcf6f30-aaa0-4734-8a99-4fc908013419.jsonl`
- `/ll:refine-issue` - 2026-08-08T21:03:31 - `cdcf6f30-aaa0-4734-8a99-4fc908013419.jsonl`
- `/ll:capture-issue` - 2026-08-08T20:35:50 - `cf0cb0be-6bdf-436b-b626-68fabe345e75.jsonl`

---

## Status

**Open** | Created: 2026-08-08 | Priority: P4
