---
id: BUG-2963
title: Scoped completion commit closes an issue while leaving its implementation uncommitted
type: BUG
priority: P1
status: open
discovered_date: 2026-08-01
discovered_by: human
relates_to:
- BUG-2421
- BUG-2424
labels:
- issue-lifecycle
- orchestration
- data-loss
confidence_score: 100
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
---

# BUG-2963: Scoped completion commit closes an issue while leaving its implementation uncommitted

## Summary

`_commit_issue_completion()` stages **only the issue file**, commits it with an
`implement(<type>): implement <ID>` message, and marks the issue `done` — while
the issue's actual implementation sits in the working tree as unstaged and
untracked files. When the run finishes and the worktree is removed, that code is
destroyed. The issue is recorded as complete and no artifact of the work
survives.

This is the intended BUG-2421 behavior (never `git add -A`) applied to the wrong
case. BUG-2421 correctly assumed the dirty paths were *unrelated* WIP from other
issues. In practice the dirty paths are usually *this issue's own deliverable*,
because the safety-net path fires precisely when the subloop died before
committing its own work.

## Steps to Reproduce

1. Run an orchestrator that closes issues via `issue_lifecycle` (e.g.
   `ll-loop run sprint-refine-and-implement <EPIC>` in a worktree-isolated
   epic branch).
2. Let a subloop write implementation files but exit abnormally (crash, timeout,
   context exhaustion) before committing them.
3. The safety-net path runs `_commit_issue_completion()`.
4. Observe: a commit touching only `.issues/.../P?-<TYPE>-<ID>-*.md`, the issue's
   `status: done`, and a `logger.warning` listing the abandoned paths.
5. When the worktree is removed, the listed paths are gone.

## Current Behavior

Observed in run `sprint-refine-and-implement-20260731T235717` (EPIC-2938):

- `462900cc implement ENH-2943` — 1 file changed (the issue `.md`). Neither
  `cli/loop/rename.py` nor `cleanup.py` was ever committed.
- `affb584f implement ENH-2944` — 1 file changed. `cli/issues/normalize.py` was
  never committed.
- `c9f2681c implement ENH-2952` — issue file plus a decisions fragment only.

The warning at `scripts/little_loops/issue_lifecycle.py:465-469` fired and listed
~65 dirty paths, including `?? scripts/little_loops/cli/issues/normalize.py`,
`?? scripts/little_loops/cli/loop/rename.py`, `?? cleanup.py`, and their four
test files. All three issues were reported closed. The run's `summary.json` read
`{"verdict":"partial","closed":9,"not_closed":0}` — the 3 hollow closures counted
as successes.

The damage is not confined to the lost work: subcommand *wiring* for the missing
modules was committed as collateral in sibling issues' commits, so merging the
branch left `ll-issues` and `ll-loop` raising `ModuleNotFoundError` on import at
`cli/issues/__init__.py:67` and `cli/loop/__init__.py:38,42`. Repaired in
3e76f972.

## Expected Behavior

A completion commit must never close an issue whose implementation is not in the
commit. Given dirty paths at close time, one of:

- **Commit them under this issue** when they are plausibly this issue's
  deliverable (path overlaps the issue's `## Integration Map` / `Files to
  Create`, or the issue is the only one in flight in this worktree), or
- **Refuse to close**: leave `status: in_progress`, emit an explicit failure, and
  let the issue be requeued — the loop's `not_closed`/`abandoned` counters exist
  for exactly this.

Silently committing the bookkeeping and discarding the deliverable is the one
outcome that must not happen. At minimum the verdict must not read `closed`.

## Motivation

Three issues' worth of implementation was destroyed in a single 4.5-hour,
$13.85 run, and the loss was invisible: `summary.json` reported them closed, the
issue frontmatter said `done`, and the only signal was a `logger.warning` inside
a 10K-line log. Any orchestrator using this path can silently lose work.

## Root Cause

`scripts/little_loops/issue_lifecycle.py:414-498`, `_commit_issue_completion()`.

The BUG-2421 comment block at lines 431-440 states the reasoning: stage only the
issue file "but still commits the issue file (per AC #5), only warning about the
dirty paths it leaves behind rather than skipping." The gap is that no branch
distinguishes *unrelated* dirty paths (BUG-2421's premise) from *this issue's
own implementation*, and the closure proceeds unconditionally either way.

The sibling parallel path `_stage_and_commit_issue_scoped()`
(`parallel/orchestrator.py`, BUG-2424) needs the same audit.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Every caller discards the return value and writes `status:` before the
  commit is attempted**, not just after — this is a second defect the fix
  must also close:
  - `close_issue()` (`issue_lifecycle.py:650-746`) writes `status: "done"` via
    `update_frontmatter` at lines 713-717, *then* calls
    `_commit_issue_completion()` at line 727 and discards its result.
  - `complete_issue_lifecycle()` (`issue_lifecycle.py:749-819`) writes
    `status: "done"` at lines 786-790, then calls at line 801, same discard.
  - `defer_issue()` (`:851-913`) and `undefer_issue()` (`:1004-1065`) write
    `status: "deferred"`/`"open"` before their own completion-commit calls
    (lines 888 / 1046), same pattern — **but these two are carved out of the
    new contract** (see Proposed Solution → Scope carve-out): deferral is not
    a claim of delivered work, and rewriting `deferred` → `in_progress` on
    `NOT_CLOSED` would silently un-defer the issue.
  - Introducing `CompletionResult.NOT_CLOSED` requires making these
    frontmatter writes conditional on the result — but they **cannot** simply
    move to *after* a successful commit: the completion commit must *contain*
    the issue file with `status: done`, so committing first would bake
    `in_progress` into the commit and leave the `done` write permanently
    dirty. See Program Design → Call Path for the canonical ordering (triage
    refuses before anything is staged; the caller reverts `done` →
    `in_progress` on `NOT_CLOSED`).
- **`_stage_and_commit_issue_scoped()` (`parallel/orchestrator.py:1671-1704`)
  already refuses to commit when any non-issue-file dirty path exists** — it
  returns `None` instead of committing anyway (unlike the
  `issue_lifecycle.py` path, which commits regardless). But it has the same
  false-success shape via a different mechanism: its caller,
  `_complete_issue_lifecycle_if_needed()` (`:1706-1824`), writes
  `status: done`/`in_progress` frontmatter at lines 1766-1770 — **before**
  calling `_stage_and_commit_issue_scoped()` at line 1801 — and when the
  helper returns `None` (commit skipped), still `return True` (line 1806).
  It also does no attributable/unattributable classification at all; *any*
  other dirty path skips the commit, which is stricter than needed and would
  itself lose attributable work if adopted as-is for the lifecycle path.
- **No existing `sole_issue_in_tree`-style primitive exists anywhere in the
  codebase** (confirmed via repo-wide search) — this is new territory, not a
  concept to reuse. Contextually: `ll-auto` (`issue_manager.py`) processes
  issues sequentially in one shared working tree (single issue's dirty state
  present at a time — closest to `sole_issue_in_tree=True`), while
  `ll-parallel` (`parallel/orchestrator.py`) isolates each issue in its own
  git worktree, so the "sole issue" question there is per-worktree. Neither
  path currently threads such a boolean into `issue_lifecycle.py`.

## Proposed Solution

1. In `_commit_issue_completion()`, classify the non-issue-file dirty paths
   *before staging anything* (triage is a pre-flight refusal gate, not a
   post-commit check — see Program Design → Call Path for ordering). A path is
   *attributable* to this issue when it matches the issue's declared
   `## Integration Map` / `### Files to Create` entries, or when
   no other issue is in flight in this working tree.
2. If attributable paths exist and no unattributable ones do: stage them
   alongside the issue file. This keeps BUG-2421's guarantee (no blind
   `git add -A`) while preserving the work.
3. If *only* unattributable paths exist (no attributable ones): keep the
   current warn-and-commit-issue-file-only behavior, unchanged — this is
   BUG-2421's original premise (a human's unrelated WIP in a shared tree)
   and refusing here would block routine closes in dirty dev trees.
4. If attributable paths could not be committed, **or** the triage found a
   *mixed* set (attributable paths alongside unattributable ones — see the
   partial-attribution guard in Program Design), do not close: return a
   distinct failure so the caller writes `status: in_progress` and increments
   `not_closed` rather than `closed`. A plain `git commit` failure (hook
   rejection, index lock, timeout) maps to the same failure — any outcome
   where the deliverable is not in a commit must not read `closed`.
5. Make the loss legible without reading the log. There is no direct channel
   from `_commit_issue_completion()` to `summary.json` — the counters are
   derived by loop-YAML shell states from on-disk frontmatter (see Research
   Findings below) — so stamp `uncommitted_paths: <N>` into the issue's
   frontmatter on any `NOT_CLOSED` return. The existing frontmatter-derivation
   states then surface it with no YAML edits.
6. Audit `_stage_and_commit_issue_scoped()` in `parallel/orchestrator.py` for
   the same defect. **Expected conclusion: no code change** — its docstring
   premise is that the worker's code diff is already merged and committed
   *before* this frontmatter-only follow-up, so its skip-and-return-True is
   not a hollow-closure risk of the same class. Confirm and document that,
   rather than forcing symmetry with the lifecycle path.

**Scope carve-out (defer/undefer):** only `close_issue()` and
`complete_issue_lifecycle()` — the "this work is delivered" claims — get the
triage + `NOT_CLOSED` contract. `defer_issue()` / `undefer_issue()` keep the
current issue-file-only commit + warn: deferral is not a claim that work was
delivered, and mapping `NOT_CLOSED` to `status: in_progress` there would
silently un-defer an issue and fight the autodev deferral policy
(`deferred_by` / `deferred_reason` codes). They may adopt `CompletionResult`
as a return type for uniformity, but must never rewrite their terminal status
on `NOT_CLOSED`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

7. Confirm `loops/autodev.yaml`'s `finalize_done` state (lines 1941-2074) also
   derives correct `closed`/`not_closed` counters after the fix — same
   frontmatter-derivation pattern as `auto-refine-and-implement.yaml`, not
   previously named in this issue.
8. Update `docs/reference/API.md`'s "Returns" prose (lines 2594-2722) for
   `close_issue`/`complete_issue_lifecycle`/`defer_issue`/`undefer_issue` to
   describe the new not-closed-due-to-uncommitted-paths failure mode.
9. Add or update tests: `test_issue_lifecycle.py::TestCommitIssueCompletion`
   (currently asserts unconditional `True`, will break), a live-git-repo
   `NOT_CLOSED`-and-requeue integration test through `issue_manager.py`'s
   `complete_issue_lifecycle()` path (currently only mock-based coverage
   exists there), and re-examine
   `test_orchestrator.py::test_complete_lifecycle_commit_excludes_unrelated_dirty_file`.
10. **Design-decision-dependent**: if the attribution rule extends
    `extract_file_hints()` (`parallel/file_hints.py:287-365`) to recognize a
    `### Files to Create` section rather than reusing the helper as-is, that
    is a shared-utility behavior change affecting three other callers whose
    output would silently widen: `dependency_graph.py:472,487` (wave-split
    contention detection), `parallel/overlap_detector.py:14,87,120` (live
    overlap tracking between concurrently-dispatched issues), and
    `cli/issues/fingerprint.py` / `cli/sprint/manage.py`. Add
    `test_file_hints.py::test_extracts_from_files_to_create` and re-check
    those three callers' tests if this path is chosen. Not applicable if the
    "reuse as-is, drop the Files to Create reference" alternative is chosen
    instead.

## Program Design

### Signatures

New helper and result type in `scripts/little_loops/issue_lifecycle.py`:

- `_triage_dirty_paths(info: IssueInfo, porcelain_lines: list[str], sole_issue_in_tree: bool) -> DirtyPathTriage`

  Splits `git status --porcelain` lines into paths this issue owns and paths it
  does not.

- `DirtyPathTriage` — plain (non-frozen) dataclass with
  `attributable: list[str]` (this issue's deliverable, must be committed) and
  `unattributable: list[str]` (unrelated WIP, left alone per BUG-2421's
  premise). Non-frozen per Research Findings below — this codebase reserves
  `frozen=True` for serialization-boundary value objects.

- `_commit_issue_completion(info: IssueInfo, commit_prefix: str, commit_body: str, logger: Logger, *, sole_issue_in_tree: bool = False) -> CompletionResult`

  Return type replaces the current unconditional `bool` `True`.
  `CompletionResult` is a plain `Enum` (see Research Findings) of `COMMITTED`
  (issue file plus all attributable paths staged) and `NOT_CLOSED` (the
  deliverable did not land in a commit — triage refusal, staging failure, or
  plain commit failure).

  **`sole_issue_in_tree` threading** (previously unspecified): keyword-only
  with a conservative `False` default, plumbed through `close_issue()` /
  `complete_issue_lifecycle()` as the same keyword. `ll-auto`
  (`issue_manager.py`) passes `True` — sequential processing, one issue's
  dirty state at a time. `ll-parallel` workers pass `True` per isolated
  worktree. Any caller that cannot prove isolation (FSM/sprint epic branches
  with multiple issues in flight on one shared branch — the incident shape)
  takes the `False` default. Note the incident run itself would have been
  `False`, so Integration Map matching plus the partial-attribution guard
  below is the load-bearing protection there.

### Call Path

**Canonical ordering.** The completion commit must *contain* the issue file
with `status: done`, so the frontmatter write cannot move to after the commit.
Instead, triage runs as a pre-flight refusal gate *before anything is staged*,
and the caller reverts its status write on refusal:

`close_issue` writes `status: done` (as today) -> `_commit_issue_completion`
-> `_triage_dirty_paths` (pre-flight; the issue file itself is excluded from
triage) -> on refusal: return `NOT_CLOSED` **without staging or committing
anything**; the caller rewrites `status: in_progress` (left uncommitted, so
the issue is requeued) and increments `not_closed` -> on pass:
`git add -- <issue file> <attributable>` -> `git commit` -> `COMMITTED`.
`logger.warning` now reports only `DirtyPathTriage.unattributable`.

Attribution rule, in precedence order:

1. Path appears in the issue body's `## Integration Map` (including its
   `### Files to Create` subsection) → attributable.
2. `sole_issue_in_tree` is True (worktree-isolated run, one issue in flight) →
   every dirty path is attributable.
3. Otherwise → unattributable.

**Partial-attribution guard.** This path fires only after an abnormal subloop
exit, so an *incomplete* deliverable is the expected failure mode. When triage
yields a non-empty attributable set **and** unattributable paths also remain
(a mixed set), return `NOT_CLOSED` rather than committing the partial set. In
the observed incident, `normalize.py` would have matched the Integration Map
while its test files (implementation-created, never listed under `### Files to
Modify`) would not — committing only the module would close the issue `done`
with its tests destroyed, reproducing the hollow closure in weaker form.
`sole_issue_in_tree=True` renders the guard moot (everything is attributable);
a purely-unattributable set (rule 3 only, no attributable paths) keeps the
BUG-2421 warn-and-commit-issue-file-only behavior per Proposed Solution #3.

`_commit_issue_completion()` gains a return type carrying the outcome instead of
its current unconditional `True`:

```python
class CompletionResult(Enum):
    COMMITTED = "committed"    # issue file + all attributable paths staged and committed
    NOT_CLOSED = "not_closed"  # deliverable not in a commit: triage refusal (mixed
                               # set), staging failure, or plain `git commit` failure
                               # (hook rejection, index lock, timeout)
```

The "nothing to commit — already committed" case maps to `COMMITTED` (the
deliverable is in a commit, just an earlier one). Callers map `NOT_CLOSED` to
`status: in_progress` plus the `not_closed` counter rather than
`done`/`closed`, and stamp `uncommitted_paths: <N>` frontmatter (Proposed
Solution #5). The `logger.warning` stays for the unattributable list only.
`defer_issue()`/`undefer_issue()` are exempt from the `NOT_CLOSED` → status
rewrite (Scope carve-out above). The `test_commit_failure` test's current
"still returns True to continue flow" contract is retired: a plain commit
failure now returns `NOT_CLOSED`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Use a plain `Enum` with string values, not `StrEnum`.** A repo-wide grep
  found zero existing `StrEnum` usages in `scripts/little_loops/` — the
  established convention is `class X(Enum): MEMBER = "value"`, e.g.
  `LinkOutcome` (`link_checker.py:60-75`), `MatchClassification`
  (`issue_discovery/matching.py:24-35`), and — most locally relevant —
  `FailureType`/`DeferReason` already defined in `issue_lifecycle.py:89-104`
  and `:51-81`. `CompletionResult` should follow that same local precedent
  (placement in a `# ===...===` banner section near the top of the file,
  each member documented) rather than introducing the codebase's first
  `StrEnum`.
- **`DirtyPathTriage` should follow the `FindingMatch`
  (`issue_discovery/matching.py:62-100`) / `FileHints`
  (`parallel/file_hints.py:58-83`) shape** — plain (non-frozen) `@dataclass`
  with `field(default_factory=list)` buckets — rather than `frozen=True`.
  This codebase reserves `frozen=True` for value objects crossing a
  serialization boundary (e.g. `HostCapabilities`, `ToolDefinition`); a
  triage result built fresh from parsing porcelain output each call doesn't
  fit that pattern.
- **A reusable porcelain-line parser already exists**:
  `_porcelain_paths()` in `codequery/codegraph.py:106-121` handles both the
  plain `XY path` and rename `XY old -> new` formats plus quoted paths, and
  is more complete than the inline parsing currently duplicated three times
  in `parallel/worker_pool.py` and `parallel/merge_coordinator.py`. Prefer
  reusing/promoting this over writing a fourth inline parser inside
  `_triage_dirty_paths()`.
- **An Integration Map file-path extractor already exists but is scoped to
  the wrong subsections for this fix**: `extract_file_hints()` /
  `_extract_write_target_files()` in `parallel/file_hints.py:287-365`
  extracts paths only from `### Files to Modify` / `### Files Changed`
  subsections (regex-scoped, see `FILE_PATH_PATTERN`/`_is_valid_path()`).
  **It does not currently recognize `### Files to Create`**, which is the
  subsection this issue's attribution rule names. Confirmed the standard
  Integration Map template
  (`scripts/little_loops/templates/feat-sections.json:64-79`) also has no
  `### Files to Create` heading — only `### Files to Modify`, `### Dependent
  Files`, `### Similar Patterns`, `### Tests`, `### Documentation`,
  `### Configuration`. `_triage_dirty_paths()` should either reuse
  `extract_file_hints()` as-is (dropping the `Files to Create` reference) or
  extend `file_hints.py`'s section pattern to include it — not duplicate the
  extraction logic inline.
- **Existing test scaffolding to model new coverage after**: both
  `test_issue_lifecycle.py`'s `TestCommitIssueCompletionScoped`
  (lines 316-413+, fixture `temp_git_repo`) and `test_orchestrator.py`'s
  sibling `TestScopedCompletionStaging` (line 3955+, fixture
  `real_git_orchestrator`) already use a real temp git repo via the shared
  `copy_git_template()` helper (`scripts/tests/helpers.py:44-76`), seed an
  "unrelated dirty file," and assert via `git show --name-only`/`git status
  --porcelain`. New tests for attributable-path commits and `NOT_CLOSED`
  routing should extend these same classes/fixtures rather than building new
  scaffolding.

## Integration Map

- `scripts/little_loops/issue_lifecycle.py` — `_commit_issue_completion()`
  (lines 414-498), the fix site.
- `scripts/little_loops/parallel/orchestrator.py` —
  `_stage_and_commit_issue_scoped()`, sibling path to audit.
- `scripts/little_loops/loops/*.yaml` — states that count `closed` in
  `summary.json`; must respect the new not-closed signal.
- `scripts/tests/test_issue_lifecycle.py` — new coverage: dirty attributable
  paths get committed; unattributable ones do not; a blocked attributable path
  yields not-closed rather than closed.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — `finalize_done` state
  (lines 1941-2074) builds the same frontmatter-derived `closed`/`not_closed`
  summary counters as `auto-refine-and-implement.yaml` (shells to `ll-issues
  show "$ID" --json`, buckets by `status`, emits at line 2072). Not named in
  the issue's original Integration Map, which only cites
  `auto-refine-and-implement.yaml`. Same conclusion applies — fixing the
  premature `status:` writes should make this loop's counters correct with no
  direct YAML edit — but confirm it, don't assume by extension.
- `scripts/tests/test_builtin_loops.py` (~lines 3035-3159, 3482-3495,
  4902-4958) — existing regression coverage for both loop YAMLs'
  frontmatter-derived counters; the check that "no wiring change expected"
  holds after the fix lands.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (lines 2594-2722) — hand-maintained signature +
  "Returns" prose for `close_issue`, `complete_issue_lifecycle`, `defer_issue`,
  `undefer_issue`. Signatures stay accurate (external contracts unchanged per
  Program Design), but "Returns" prose ("True if successful, False otherwise")
  needs a third failure cause added: not-closed due to uncommitted
  attributable paths.
- `docs/ARCHITECTURE.md:639` — one-line responsibility summary for
  `issue_lifecycle.py`; also documents the `_maybe_auto_commit()`
  (`hooks/post_tool_use.py:1440-1443`) idiom that both `_commit_issue_completion()`
  and `_stage_and_commit_issue_scoped()` cite as their scoped-staging design
  precedent.
- `docs/reference/EVENT-SCHEMA.md:926` — references `undefer_issue()` for the
  `issue.started` event description; semantics stay accurate, but emission
  moves under the same conditional-on-`CompletionResult` gating.
- `skills/audit-loop-run/SKILL.md:266-277` — documents the `closed`/`implemented`
  claimed-success-counter convention generically across loops; a second doc
  surface (besides ARCHITECTURE.md) naming the `closed` counter semantics.
- `CHANGELOG.md` — needs its own new entry once this lands (do not amend the
  existing BUG-2421/BUG-2424 entry at line 1161 — this fix corrects a gap in
  that same guarantee, it doesn't rewrite it).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_lifecycle.py::TestCommitIssueCompletion`
  (lines 234-299) — **will break under the new return-type contract**, not
  previously named in the issue (only the sibling `TestCommitIssueCompletionScoped`
  was). `test_successful_commit` (254), `test_nothing_to_commit` (282), and
  `test_commit_failure` (298, comment literally reads "Still returns True to
  continue flow") all assert `result is True`.
- `scripts/tests/test_orchestrator.py::test_complete_lifecycle_commit_excludes_unrelated_dirty_file`
  (lines 3984-4007) — asserts `result is True` (4001) even though the commit
  was skipped and frontmatter `status:` was still written. Nearest regression
  risk on the orchestrator side; re-examine once `_triage_dirty_paths()` lands.
- `scripts/tests/test_issue_manager.py` — six `patch("little_loops.issue_manager.complete_issue_lifecycle", ...)`
  sites (lines 2667, 2746, 2789, 2843, 2955, 3001) plus a `close_issue`
  mock-return-value test (~2409-2419) mock the lifecycle functions wholesale
  rather than exercising real triage/commit logic — they stay green regardless
  of this fix, which means there is **no existing integration test driving
  `complete_issue_lifecycle()` end-to-end through a live git repo from the
  `ll-auto` path**. New `NOT_CLOSED`-and-requeue integration coverage belongs
  here, not just in `test_issue_lifecycle.py`.
- `scripts/tests/test_file_hints.py::TestExtractWriteTargetFiles`
  (lines 152-224) — only recognizes `"### Files to Modify"` / `"### Files
  Changed"` section headers; **no `test_extracts_from_files_to_create` case
  exists**. If the fix extends `extract_file_hints()`'s section pattern
  (`file_hints.py:301-304`) to recognize `### Files to Create` rather than
  reusing the helper as-is, this is the test class to extend.
- `scripts/tests/test_codequery_codegraph.py` — `_porcelain_paths()`
  (`codequery/codegraph.py:106-121`) has **zero existing unit tests** anywhere
  in the suite. If `_triage_dirty_paths()` reuses it as proposed, it would be
  adopting an untested porcelain parser (rename-line and quoted-path handling
  asserted nowhere).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Callers to update** (all in `issue_lifecycle.py`, all currently write
  `status:` before calling the completion function and discard its return
  value):
  - `close_issue()` (`:650-746`) — `status: "done"` at 713-717, calls at 727.
  - `complete_issue_lifecycle()` (`:749-819`) — `status: "done"` at 786-790,
    calls at 801.
  - `defer_issue()` (`:851-913`) — `status: "deferred"` at 888.
  - `undefer_issue()` (`:1004-1065`) — `status: "open"` at 1046.
  - Upstream, `close_issue()`/`complete_issue_lifecycle()` are called from
    `issue_manager.py:788,1102,1114` (sequential `ll-auto` path, gates
    `IssueProcessingResult(success=...)`) and
    `parallel/orchestrator.py:1071,1490` (gates
    `self.queue.mark_completed(...)` vs `mark_failed(...)`) — these gate
    points need to translate `NOT_CLOSED` into a failure/requeue outcome.
- **`_stage_and_commit_issue_scoped()` sibling audit, concrete findings**:
  defined at `parallel/orchestrator.py:1671`, signature
  `(self, issue_id: str, issue_path: Path, commit_msg: str) ->
  subprocess.CompletedProcess[str] | None`. Its sole caller for the
  completion path, `_complete_issue_lifecycle_if_needed()` (`:1706-1824`),
  writes frontmatter at lines 1766-1770 *before* calling it at line 1801 and
  treats a `None` return (commit skipped) as success at lines 1803-1806. A
  second caller at line 1160 (`_on_worker_complete()`, feature-branch
  frontmatter fallback) only checks `returncode != 0`, not `None`.
- **`closed`/`not_closed` counters in `summary.json` are derived from
  on-disk frontmatter status, not from any function's return value** —
  confirmed in `loops/auto-refine-and-implement.yaml:768-961`: a
  `$P-closed-union.txt` set is built from issues whose frontmatter is
  literally `done`, and `not_closed` is `comm -23` against the
  dispatched/passed set. This means fixing the premature `status: done`
  writes above should make the existing loop counters correct **without**
  any direct YAML edits — the "audit `loops/*.yaml`" action item in this
  issue's Proposed Solution can be satisfied by confirming this derivation
  (no wiring change expected), rather than assuming new counter plumbing is
  needed.
- Test files with existing scaffolding to extend (see Proposed Solution →
  Codebase Research Findings for fixture details):
  `scripts/tests/test_issue_lifecycle.py` (`TestCommitIssueCompletionScoped`,
  lines 316-413+) and `scripts/tests/test_orchestrator.py`
  (`TestScopedCompletionStaging`, line 3955+).

## Impact

**Severity: P1.** Silent, unrecoverable loss of completed implementation work,
combined with a false success signal. Any `ll-auto` / `ll-parallel` /
`ll-sprint` / FSM run that hits the safety-net path is exposed. Recovery is
impossible once the worktree is pruned — there is no stash, no branch, no
dangling object.

## Status

Open. Discovered while auditing run
`.loops/runs/sprint-refine-and-implement-20260731T235717/` (EPIC-2938).
ENH-2943, ENH-2944, and ENH-2952 were reopened; the dangling CLI wiring the
partial commits left behind was stripped in 3e76f972.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-01_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 56/100 → LOW

### Outcome Risk Factors
- Fix requires coordinated changes across ~9 call sites beyond the two new
  primitives: 4 lifecycle callers (`close_issue`, `complete_issue_lifecycle`,
  `defer_issue`, `undefer_issue`) must move their `status:` frontmatter writes
  to occur only after a successful commit, plus 3 upstream gates in
  `issue_manager.py` and 2 in `parallel/orchestrator.py` that currently discard
  the return value and need to translate `NOT_CLOSED` into a failure/requeue
  outcome — broad enumeration across many coordinated sites raises regression
  risk versus the isolated single-function fix the summary suggests.
- Whether `_triage_dirty_paths()` reuses `extract_file_hints()` as-is or
  extends it to recognize `### Files to Create` is left as an implementation
  choice (Program Design notes both are viable, with reuse-as-is as the
  simpler default). Choosing to extend it widens shared-utility behavior for
  three other unrelated callers (`dependency_graph.py`, `overlap_detector.py`,
  `fingerprint.py`/`manage.py`) and would need its own test coverage
  (`test_extracts_from_files_to_create`) plus a re-check of those callers.
- Three existing tests assert the current unconditional `True` contract
  (`test_successful_commit`, `test_nothing_to_commit`, `test_commit_failure`)
  and will need rewriting under the new `CompletionResult` enum return type;
  the reused porcelain-line parser `_porcelain_paths()`
  (`codequery/codegraph.py:106-121`) has no existing unit tests of its own,
  so its rename-line/quoted-path handling would be adopted untested unless
  new coverage is added alongside this fix.

## Session Log
- `/ll:confidence-check` - 2026-08-01T15:38:02 - `b4f9b5bc-a25f-4e33-9cac-4183ae2ea1d2.jsonl`
- `/ll:wire-issue` - 2026-08-01T15:35:08 - `a19f79ec-bdc4-4712-a077-60fd1c5b8ba2.jsonl`
- `/ll:refine-issue` - 2026-08-01T15:27:25 - `ace400b0-49a5-450b-9100-27780a9235cb.jsonl`
