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
- ENH-2965
labels:
- issue-lifecycle
- orchestration
- data-loss
testable: true
confidence_score: 100
outcome_confidence: 53
score_complexity: 10
score_test_coverage: 15
score_ambiguity: 18
score_change_surface: 10
decision_needed: false
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

**Scope of this issue (split from the original BUG-2963, 2026-08-01):** this
issue covers the *run-window* fix — discriminating "appeared during this run"
from "was already dirty," committing the former, never destroying anything, and
never reporting `closed` when the deliverable is not in a commit. Content-based
attribution (matching dirty paths against the issue's `## Integration Map`) for
callers that cannot supply a pre-run snapshot is split out to **ENH-2965**,
which depends on this issue. See Non-Goals.

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

### Verified delegation chain (corrects the original analysis)

The incident's closing caller is **`ll-auto`**, not a bespoke FSM path:

```
ll-loop run sprint-refine-and-implement <EPIC>
  → auto-refine-and-implement.yaml
    → autodev.yaml
      → `ll-auto --only <ID>`            (autodev.yaml:7, 29)
        → issue_manager.py:1125  verify_work_was_done(...)  → True
        → issue_manager.py:1133  complete_issue_lifecycle(...) → hollow commit
```

`scripts/little_loops/loops/sprint-refine-and-implement.yaml` contains no direct
`issue_lifecycle` call; it forwards to `auto-refine-and-implement`, which
forwards to `autodev`, whose `implement_current` state shells out to
`ll-auto --only`. This matters for the design: an earlier draft of this issue
asserted the incident run was a multi-issue shared-branch caller where
content-based attribution would be load-bearing. It was not.

## Expected Behavior

A completion commit must never close an issue whose implementation is not in the
commit, and must never leave that implementation in a state where teardown
destroys it. Given dirty paths at close time:

- **Paths that appeared during this run** are this issue's deliverable: stage
  and commit them alongside the issue file.
- **Paths that were already dirty before the run began** are unrelated WIP
  (BUG-2421's actual premise): leave them alone, warn, commit the issue file.
- **When the deliverable cannot be committed** (staging failure, commit
  failure, or no pre-run snapshot available so the two sets cannot be
  separated): preserve the working tree to a durable git ref, do **not** write
  `done`, and return a distinct not-closed result.

- **Paths orphaned before this run began, by anyone**, are outside the
  run-window discriminator's reach (see Proposed Solution #8) but must still
  not be destroyed: teardown preserves any non-noise dirt to a durable ref
  before removing a worktree.

Silently committing the bookkeeping and discarding the deliverable is the one
outcome that must not happen. At minimum the verdict must not read `closed`,
and in no path may work be destroyed. Note that the run-window discriminator
alone does **not** satisfy the second clause — the per-issue snapshot makes one
issue's orphan the next issue's "pre-existing WIP" — which is why the teardown
backstop is load-bearing rather than defensive.

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

### The upstream gate already exists and asks the wrong question

`ll-auto`'s completion path is already guarded — `issue_manager.py:1125` calls
`verify_work_was_done()` and refuses to close when it returns False
(`:1146-1160`, the `REFUSING to mark ... as completed` branch). The gate checks
whether work **exists**; it never checks whether the work was **committed**.
Uncommitted work passes the gate, and `complete_issue_lifecycle()` then commits
only the issue file.

This reframes the fix: it is a tightening of an existing exists→committed gate,
not a new subsystem. It also supplies the noise-filtering primitive the fix
needs (see Program Design → Noise filtering).

## Non-Goals

Deliberately **out of scope**, split to ENH-2965:

- Content-based attribution: matching dirty paths against the issue body's
  `## Integration Map` / `### Files to Create`.
- Extending `extract_file_hints()` (`parallel/file_hints.py:287-365`) to
  recognize `### Files to Create`, and the shared-utility blast radius that
  implies for `dependency_graph.py`, `parallel/overlap_detector.py`, and
  `cli/issues/fingerprint.py` / `cli/sprint/manage.py`.
- A `DirtyPathTriage` attributable/unattributable dataclass.
- A `sole_issue_in_tree` flag. (Superseded here by the pre-run snapshot, which
  is a per-invocation fact rather than a static per-caller constant. An earlier
  draft made this a caller constant; that is wrong — it was true at ENH-2943's
  close and false at ENH-2944's, precisely *because* ENH-2943's files leaked.)

Also out of scope: `defer_issue()` / `undefer_issue()` status rewrites — see
Scope carve-out.

## Proposed Solution

1. **Capture a pre-run dirty snapshot.** Capture it alongside the Phase-2
   `_baseline_sha` (`issue_manager.py:922-927`), **before**
   `run_with_continuation()` fires: `frozenset` of `git status --porcelain`
   paths. Thread it into `_commit_issue_completion()` as a keyword.

   **Anchor warning (corrected 2026-08-01):** do *not* capture at
   `issue_manager.py:967-975` next to `_post_implement_snapshot` — that is the
   ENH-2958 *end-of-Phase-2* tamper bracket, taken after the implementation
   subprocess returns. A snapshot taken there already contains every file the
   implementation wrote, so step 2 would classify the entire deliverable as
   pre-existing WIP and reproduce the incident — while unit tests that seed
   dirt manually before calling the function would still pass. An earlier
   draft cited that anchor; it is wrong.

   The `close_issue()` site at `issue_manager.py:789` is in Phase 1 (the
   ready-issue CLOSE branch), before Phase 2 exists — for that site capture
   the snapshot at the top of `process_issue_inplace()`. Semantically fine: a
   Phase-1 close has no deliverable by construction, so everything dirty is
   pre-existing WIP.
2. **Discriminate by run window, not by content.** At close time, re-read
   porcelain. Paths **not** in the pre-run snapshot, after noise filtering, are
   this run's deliverable. Paths **in** the snapshot are pre-existing WIP.
3. **Commit the deliverable.** Stage the issue file plus the run-window paths
   and commit them together. This keeps BUG-2421's guarantee (no blind
   `git add -A`) while preserving the work — the pre-existing WIP is still
   never swept in.
4. **Never destroy on refusal.** Before returning `NOT_CLOSED` for any reason,
   preserve the working tree to a durable ref
   `refs/ll/abandoned/<ID>-<timestamp>`. Worktrees share the object database
   and ref store with the main repo, so a ref written from inside a worktree
   survives `git worktree remove --force` (`worktree_utils.py:300`,
   `parallel/merge_coordinator.py:1098`, `parallel/orchestrator.py:349,644` —
   all unconditional `--force`). Log the ref name at `error` level. **Without
   this step, refusing to close makes the loss honest but does not prevent
   it.**

   **The preservation must be non-destructive — `git stash push -u` is
   forbidden.** An earlier draft offered stash as an alternative; that is
   wrong. In the `ll-auto` case there is no worktree at all: the tree being
   preserved is the user's own working tree, and stash *removes* the changes
   from it — including the pre-existing WIP that BUG-2421's guarantee exists
   to leave untouched. Build the snapshot through a throwaway index instead,
   leaving the working tree and the real index byte-identical:

   ```
   GIT_INDEX_FILE=<tmp> git add -A
   GIT_INDEX_FILE=<tmp> git write-tree          → <tree>
   git commit-tree <tree> -p HEAD -m "ll: abandoned work for <ID>"  → <sha>
   git update-ref refs/ll/abandoned/<ID>-<ts> <sha>
   ```

   Objects rooted under `refs/` are reachable, so `git gc` cannot reap them.
   Gitignored paths are correctly omitted (`add -A` honors `.gitignore`),
   which is why `.loops/runs/` and `.loops/tmp/` need no special handling.
5. **Return a real result and gate the callers on it.** `NOT_CLOSED` means the
   deliverable is not in a commit; the caller leaves/writes `status:
   in_progress`, increments `not_closed`, and lets the issue be requeued.
6. **Make the loss legible without reading the log.** Stamp
   `uncommitted_paths: <N>` and `abandoned_ref: <ref>` into the issue's
   frontmatter on `NOT_CLOSED`. Note this stamp is written to an *uncommitted*
   file, so in a worktree that is about to be pruned it evaporates — the
   durable signal is the ref from step 4 plus the `not_closed` counter, and the
   frontmatter stamp is a convenience for shared-tree (`ll-auto`) runs only. An
   earlier draft relied on the frontmatter stamp alone; that fails in exactly
   the incident scenario.
7. **Audit `_stage_and_commit_issue_scoped()`** in `parallel/orchestrator.py`.
   **Confirmed conclusion: no code change.** Its docstring premise was verified
   against the callers — the worker's code diff is already merged and committed
   before this frontmatter-only follow-up, so its skip-and-return-`True` is not
   a hollow-closure risk of the same class. Document that rather than forcing
   symmetry. (Its caller at `:1160`, `_on_worker_complete()`, checks only
   `returncode != 0` and not `None`; harmless under the same premise, worth a
   comment.)
8. **Teardown backstop — the step that actually makes the P1 unreachable.**
   Steps 1-3 rescue only the *first* orphan. `pre_run_dirty` is captured inside
   `process_issue_inplace()` (`issue_manager.py:922-975`), which is
   **per-issue, not per-run**. So an orphaned deliverable that survives one
   issue's close is present in the *next* issue's pre-run snapshot, is
   therefore classified as pre-existing WIP by step 2, is left alone with a
   warning by design, and is destroyed at teardown exactly as it is today. The
   run-window discriminator cannot see it, because from that issue's
   perspective it is indistinguishable from genuine unrelated WIP.

   Close it at the other end: immediately before any `git worktree remove
   --force`, if the tree holds non-noise dirty paths, preserve them to
   `refs/ll/abandoned/worktree-<branch>-<timestamp>` using the same
   non-destructive mechanism as step 4, and log at `error` level. Sites (all
   unconditional `--force`): `worktree_utils.py:300`,
   `parallel/merge_coordinator.py:1098`, `parallel/orchestrator.py:349,644` —
   factor a single `preserve_dirty_tree()` helper rather than repeating it.

   This is a smaller and more universal guarantee than steps 1-3: it holds for
   orphans from prior runs, from callers that never snapshot, and from paths no
   issue ever claimed. Without it, the Expected Behavior sentence "in no path
   may work be destroyed" is not satisfied by this design.
9. **Every in-repo caller must supply a snapshot; `None` must not become the
   common case.** With `pre_run_dirty=None` specified as "any non-noise dirty
   path yields preserve + `NOT_CLOSED`", the two `close_issue()` gates in
   `parallel/orchestrator.py:1071,1490` would refuse on *any* incidental dirt
   if they pass `None` — flipping `ll-parallel` from always-closes to
   rarely-closes. ENH-2965 is the stated remedy for snapshot-less callers, but
   it **depends on this issue**, so the regression window is real and lands on
   the default path.

   Thread a snapshot at all in-repo sites in *this* issue
   (`issue_manager.py:789,1118,1133` and both orchestrator gates); `None` is
   then reachable only by external API callers, where the conservative refusal
   is the right default. If threading the orchestrator gates proves impractical
   within this scope, the fallback is that `None` means preserve-to-ref **and
   close** — never-destroy without the mass refusal — but that is a deliberate
   choice to record, not a silent one.
10. **Account for the new commit-failure surface.** Staging the deliverable
    means the completion commit now carries real source through
    `.git/hooks/pre-commit` (present in this repo, gating `ll-verify-decisions`
    per ENH-2590). Issue-file-only commits nearly always pass that hook;
    commits carrying implementation can fail it, converting closes that succeed
    today into `NOT_CLOSED`. This is correct behavior — the work is preserved
    and the issue requeues — but it must be an expected, tested path.
    **Do not reach for `--no-verify`**: bypassing the hook is what would let a
    broken deliverable land under a `done` frontmatter, the same class of
    defect this issue exists to fix.

**Scope carve-out (defer/undefer):** only `close_issue()` and
`complete_issue_lifecycle()` — the "this work is delivered" claims — get the
`NOT_CLOSED` contract. `defer_issue()` / `undefer_issue()` keep the current
issue-file-only commit + warn: deferral is not a claim that work was delivered,
and mapping `NOT_CLOSED` to `status: in_progress` there would silently un-defer
an issue and fight the autodev deferral policy (`deferred_by` /
`deferred_reason` codes). They may adopt `CompletionResult` as a return type for
uniformity, but must never rewrite their terminal status on `NOT_CLOSED`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — resolving the `.ll/` noise-filter decision named
under Program Design → Noise filtering:_

**Option A**: Add `.ll/` to the existing shared `EXCLUDED_DIRECTORIES`
(`work_verification.py:20-45`), reusing the same constant `verify_work_was_done()`
already consumes.

**Option B**: Introduce a new, adjacent `.ll/`-only exclusion set scoped
exclusively to the new pre-flight noise filter in `issue_lifecycle.py`, leaving
`EXCLUDED_DIRECTORIES` and `verify_work_was_done()` untouched.

> **Selected:** Option B — a separate `.ll/`-only set avoids entangling the
> completion-commit noise filter with `verify_work_was_done()`'s unrelated
> "was real work done" gate.

**Recommended**: Option B. `verify_work_was_done()` (`work_verification.py:146-199`)
delegates to `_detect_meaningful_changes()` (`:202-302`), which calls
`filter_excluded_files()` against every candidate diff source; if all three
filter to empty, the gate returns `False` (`:191,297`) *before* `ll-auto`'s
completion path even runs. Widening `EXCLUDED_DIRECTORIES` to include `.ll/`
would make that gate report "no meaningful changes" for any issue whose sole
deliverable is itself a `.ll/`-scoped change (e.g. a decisions-log entry),
newly blocking a legitimate close it allows today. The only other consumers of
the constant (`git_operations.py:15-19`, a re-export; `worker_pool.py:38,1294`,
a diagnostic-message use) have no independent gating logic, so option B's new
set has no wiring cost beyond `issue_lifecycle.py` itself. ENH-240 previously
consolidated a divergent pair of this same constant precisely because
diverging per-consumer copies was a defect — but that precedent is about one
constant serving one *purpose* (was real work done) reused correctly by two
callers; it does not extend to entangling a second, genuinely different
question (is this dirty path noise for the completion-commit check) into the
same tuple.

### Decision Rationale

_Added by `/ll:decide-issue`:_

**Selected:** Option B — a new, adjacent `.ll/`-only exclusion set scoped to
the completion-commit noise filter in `issue_lifecycle.py`.

**Reasoning:** `verify_work_was_done()` and the new noise filter answer
different questions ("was any real work done" vs. "is this dirty path this
issue's own deliverable"), and they currently share no code path —
`issue_lifecycle.py` does not import `EXCLUDED_DIRECTORIES` today. Widening
the shared constant would make the "was real work done" gate newly reject any
issue whose sole deliverable is itself a `.ll/`-scoped change (e.g. a
decisions-log entry), turning a legitimate close into a false block. A
separate set costs one new tuple with no other consumers to keep in sync.

| Dimension | Option A (widen shared set) | Option B (adjacent `.ll/`-only set) |
|---|---|---|
| Consistency | 1/3 | 3/3 |
| Simplicity | 3/3 | 2/3 |
| Testability | 2/3 | 2/3 |
| Risk | 0/3 | 3/3 |
| **Total** | **6/12** | **10/12** |

**Key evidence:** `verify_work_was_done()` (`work_verification.py:146-199`) →
`_detect_meaningful_changes()` (`:202-302`) → `filter_excluded_files()`
returning empty across all three diff sources short-circuits the gate to
`False` at `:191,297`, before `ll-auto`'s completion path runs. The only other
consumers of `EXCLUDED_DIRECTORIES` (`git_operations.py:15-19` re-export,
`worker_pool.py:38,1294` diagnostic string) have no independent gating logic,
so Option B adds no cross-module coupling.

## Acceptance Criteria

`Acceptance Criteria` is not a required BUG section in this repo
(`templates/bug-sections.json` scopes it to FEAT), and `ll-loop
scaffold-verify` falls back to `## Expected Behavior` bullets when it is
absent — so this section is additive, not a template fix. It exists because the
solution now spans ten coordinated steps with two deliberate-choice branches
(#9's snapshot-vs-close fallback, #7's no-change conclusion), and prose
Expected Behavior does not give those individual pass/fail edges.

1. A close whose deliverable appeared during the run produces **one commit
   containing both the issue file and the deliverable**; `git show --stat` on
   the completion commit lists more than the `.md`.
2. A close whose tree holds only *pre-run* dirty paths commits the issue file
   alone and leaves those paths untouched — BUG-2421's guarantee is preserved
   verbatim, and no `git add -A` appears on any path.
3. When the deliverable cannot be committed (staging failure, commit failure,
   or `pre_run_dirty=None` with non-noise dirt), the function returns
   `CompletionResult.NOT_CLOSED`, the issue frontmatter is **not** `done`, and
   no `## Resolution` section or `completed_at` is left behind.
4. Every `NOT_CLOSED` return is preceded by a durable ref under
   `refs/ll/abandoned/` whose tree contains the abandoned content.
5. Preservation is non-destructive: the working tree and index are
   byte-identical before and after. No code path invokes `git stash`.
6. Content abandoned in a worktree is recoverable **after** `git worktree
   remove --force` — the test that pins the P1.
7. Non-noise dirt present at worktree teardown is preserved to a ref and logged
   at `error`, independent of whether any issue closed (Proposed Solution #8).
   Verified by the A-orphans-then-B-closes scenario, which the per-issue
   snapshot cannot catch.
8. `.ll/` paths (`decisions.d/*.json`, `stray-quarantine-*/`) and `.issues/`
   paths never by themselves force a refusal; `EXCLUDED_DIRECTORIES` is
   unmodified and `verify_work_was_done()` still counts a `.ll/`-only change as
   real work (Option B).
9. Issue-file exclusion is resolved-path equality against `info.path`, not
   substring containment; porcelain rename and quoted-path lines parse
   correctly.
10. A pre-commit hook rejection yields `NOT_CLOSED` + preserved ref + requeue,
    never a `--no-verify` bypass.
11. `closed` / `not_closed` counters in `auto-refine-and-implement.yaml` and
    `autodev.yaml` become correct with **no YAML edit** — confirmed by running
    the existing `test_builtin_loops.py` coverage, not assumed.
12. `python -m pytest scripts/tests/` exits 0, including the three rewritten
    `True`-contract tests.

## Program Design

### Signatures

In `scripts/little_loops/issue_lifecycle.py`:

- `_commit_issue_completion(info: IssueInfo, commit_prefix: str, commit_body: str, logger: Logger, *, pre_run_dirty: frozenset[str] | None = None) -> CompletionResult`

  `pre_run_dirty` is keyword-only. `None` (the conservative default) means the
  caller could not snapshot the tree: the two sets cannot be separated, so any
  non-noise dirty path yields preserve + `NOT_CLOSED`. ENH-2965 is what gives
  those callers a content-based fallback instead of a blanket refusal.

- `CompletionResult` — plain `Enum` with string values, placed in a
  `# ===...===` banner section near the top of the file alongside the existing
  `DeferReason` (`:51-81`) and `FailureType` (`:89-104`). Not `StrEnum`: a
  repo-wide grep found zero `StrEnum` usages in `scripts/little_loops/`.

```python
class CompletionResult(Enum):
    COMMITTED = "committed"    # issue file + this run's dirty paths are in a commit
    NOT_CLOSED = "not_closed"  # deliverable not in a commit: no snapshot available,
                               # staging failure, or `git commit` failure (hook
                               # rejection, index lock, timeout). Working tree was
                               # preserved to `abandoned_ref` before returning.
```

The "nothing to commit — already committed" case maps to `COMMITTED` (the
deliverable is in a commit, just an earlier one).

### Call Path

**Run the check before any file mutation.** The callers do more than write
`status:` — `_prepare_issue_content()` injects a `## Resolution` section,
`update_frontmatter` adds `completed_at`, and `complete_issue_lifecycle()` also
calls `append_session_log_entry()`. Reverting only `status: → in_progress` on
refusal would leave a false Resolution section and a bogus `completed_at` in the
file, which the *next* close would silently commit.

So the pre-flight check is hoisted out of `_commit_issue_completion()` into a
separate call made **before** the content mutation. It does not need the mutated
file — the issue file is excluded from the check either way:

```
close_issue / complete_issue_lifecycle
  → pre-flight: read porcelain, subtract pre_run_dirty, apply noise filter
      → cannot proceed → preserve to ref → return NOT_CLOSED   (nothing written,
                                                                nothing to revert)
      → proceed with run-window path set P
  → mutate issue file (Resolution + status: done + completed_at + session log)
  → _commit_issue_completion(..., stage = [issue file] + P)
      → git add -- <issue file> <P...>
      → git commit → COMMITTED
      → staging/commit failure → preserve to ref → NOT_CLOSED
```

Only the staging/commit-failure branch has anything to roll back, and there the
`done` write is rolled back to `in_progress` explicitly (with the Resolution
section and `completed_at` removed). The rollback must also **unstage** what the
failed commit left staged — `git reset -- <issue file> <P...>` — or the next git
operation in a shared tree (`ll-auto`) inherits a dirty index; and note
`append_session_log_entry()` has already appended by this point — either remove
the entry on rollback or accept the stale log line as a deliberate, documented
leftover (it is informational, not status-bearing).

### Noise filtering

Reuse `work_verification.filter_excluded_files()` /
`EXCLUDED_DIRECTORIES` (`work_verification.py:20-45`), which already covers
`.issues/`, `issues/`, `.speckit/`, `thoughts/`, `.worktrees/`, `.auto-manage`.

**`.ll/` must be added** (or handled via a separate benign-noise set — decide
explicitly, since `EXCLUDED_DIRECTORIES` also feeds `verify_work_was_done`'s
"was any real work done" question and widening it there has its own
consequences). See Proposed Solution → Codebase Research Findings for the
resolved decision (Option B: a new, adjacent `.ll/`-only set). Without it,
these routinely-dirty paths would each force a refusal:

- `.ll/decisions.d/*.json` fragments — the incident's own `c9f2681c` committed
  one, so they demonstrably appear mid-run.
- `.ll/stray-quarantine-*/` — present untracked in the current tree.

`.loops/runs/` and `.loops/tmp/` need no handling: both are gitignored
(`.gitignore:79-80`), so `git status --porcelain` omits them.

Note that `.issues/` being excluded also resolves the other-issue-dirt problem:
an epic/sprint run dirties sibling issue `.md` files by design (refine/wire
write to them), and those must not trigger a refusal.

### Issue-file exclusion must be path equality, not substring

Both existing implementations filter with `filename not in ln`
(`issue_lifecycle.py:459`, `parallel/orchestrator.py:1696`). Any dirty path whose
string merely *contains* the issue filename is silently treated as the issue
file. Today that is a cosmetic warning defect; under this fix it decides whether
to refuse a close, so it becomes load-bearing.

Spec it as resolved-path equality against `info.path`, and handle porcelain
rename lines (`R  old -> new`). This is the argument for reusing
`_porcelain_paths()` (`codequery/codegraph.py:106-121`), which already handles
the plain `XY path` form, the rename form, and quoted paths — and is more
complete than the inline parsing duplicated three times in
`parallel/worker_pool.py` and `parallel/merge_coordinator.py`. It has **zero
existing unit tests**, so adopting it means adding them (see Tests).

Note the current helper's quoted-path handling is quote-*stripping* only — it
does not decode git's C-style octal escapes, so non-ASCII filenames come out as
literal `\303\251`-style bytes. Prefer having the promoted helper consume
`git status --porcelain -z` (NUL-delimited: no quoting, no rename-arrow
ambiguity) over deepening the quote parser; otherwise pin the escape limitation
explicitly in its new tests.

**Promote it out of `codequery/` first.** `_porcelain_paths()` is a private
helper of a subpackage whose concern is structural code queries; its only two
references today are inside `codegraph.py` itself (`:106`, `:282`). Importing
it into `issue_lifecycle.py` — and, per Proposed Solution #8, into the worktree
teardown paths — would invert the layering and make a lifecycle-critical
refusal decision depend on a codequery internal. Move it to
`git_operations.py` as a public `porcelain_paths()` alongside the other shared
git primitives, leave a thin re-export or update the two `codegraph.py` call
sites, and put its new tests next to it. This is not scope creep: the helper
needs tests regardless, and doing it as a move costs one extra file touch.

## Integration Map

- `scripts/little_loops/issue_lifecycle.py` — `_commit_issue_completion()`
  (lines 414-498) plus the new pre-flight helper and `CompletionResult`; the
  fix site.
- `scripts/little_loops/issue_manager.py` — capture `pre_run_dirty` next to the
  Phase-2 `_baseline_sha` (`:922-927`, **before** `run_with_continuation()` —
  not the post-implement snapshot at `:967-975`; see Proposed Solution #1's
  anchor warning); thread it through the `complete_issue_lifecycle()` calls at
  `:1118`, `:1133` and the Phase-1 `close_issue()` call at `:789` (snapshot at
  top of `process_issue_inplace()` for that site); translate `NOT_CLOSED` into
  `IssueProcessingResult(success=False)`.
- `scripts/little_loops/work_verification.py` — noise-filter reuse. Resolved:
  `EXCLUDED_DIRECTORIES` is **unmodified**; the `.ll/`-only set is new and
  adjacent (Option B).
- `scripts/little_loops/parallel/orchestrator.py` — `close_issue()` gates at
  `:1071`, `:1490` translate `NOT_CLOSED` into `mark_failed(...)` rather than
  `mark_completed(...)`, and supply `pre_run_dirty` per Proposed Solution #9;
  `_stage_and_commit_issue_scoped()` audit (no change expected, per Proposed
  Solution #7).
- `scripts/little_loops/git_operations.py` — new home for the promoted
  `porcelain_paths()` (moved out of `codequery/codegraph.py:106-121`) and for
  the shared non-destructive `preserve_dirty_tree()` helper that both the
  refusal path (#4) and the teardown backstop (#8) call.
- `scripts/little_loops/codequery/codegraph.py` — update the two call sites
  (`:106` definition, `:282` use) to the promoted helper.
- **Worktree teardown sites** (Proposed Solution #8) — `worktree_utils.py:300`,
  `parallel/merge_coordinator.py:1098`, `parallel/orchestrator.py:349,644`: all
  unconditional `git worktree remove --force`; each preserves non-noise dirt
  before removing.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/auto-refine-and-implement.yaml:768-961` — builds
  `closed`/`not_closed` from **on-disk frontmatter status**, not from any
  function's return value (a `$P-closed-union.txt` set of issues whose
  frontmatter is literally `done`, with `not_closed` as `comm -23` against the
  dispatched set). Fixing the premature `status: done` writes therefore makes
  these counters correct with **no YAML edit**. Confirm, do not assume.
- `scripts/little_loops/loops/autodev.yaml:1941-2074` — `finalize_done` state
  builds the same frontmatter-derived counters (shells to `ll-issues show "$ID"
  --json`, buckets by `status`, emits at `:2072`). Same conclusion, same
  requirement to confirm.
- `scripts/little_loops/__init__.py:34-35,128-129` — re-exports `close_issue`
  and `complete_issue_lifecycle`; return-type change is public API.

### Documentation

- `docs/reference/API.md:2594-2722` — hand-maintained signature + "Returns"
  prose for `close_issue` / `complete_issue_lifecycle` / `defer_issue` /
  `undefer_issue`. Add the not-closed-due-to-uncommitted-deliverable failure
  mode and the `abandoned_ref` preservation behavior.
- `docs/ARCHITECTURE.md:639` — one-line responsibility summary for
  `issue_lifecycle.py`; also documents the `_maybe_auto_commit()`
  (`hooks/post_tool_use.py:1440-1443`) idiom both scoped-staging paths cite as
  precedent.
- `docs/reference/EVENT-SCHEMA.md:926` — references `undefer_issue()` for the
  `issue.started` event; semantics stay accurate, emission moves under
  `CompletionResult` gating.
- `skills/audit-loop-run/SKILL.md:266-277` — documents the `closed`/`implemented`
  claimed-success-counter convention; second doc surface naming `closed`
  semantics.
- **New**: document `refs/ll/abandoned/*` — where it is written, how to recover
  (`git log refs/ll/abandoned/<ID>-<ts>`, `git checkout`), and that nothing
  prunes it automatically.
- `CHANGELOG.md` — new entry. Do **not** amend the existing BUG-2421/BUG-2424
  entry at line 1161; this corrects a gap in that guarantee, it does not rewrite
  it.

### Tests

- `scripts/tests/test_issue_lifecycle.py::TestCommitIssueCompletion`
  (lines 234-299) — **breaks under the new return type**.
  `test_successful_commit` (254), `test_nothing_to_commit` (282) and
  `test_commit_failure` (298, comment reads "Still returns True to continue
  flow") all assert `result is True`. The last one's contract is retired: a
  plain commit failure now returns `NOT_CLOSED`.
- `scripts/tests/test_issue_lifecycle.py::TestCommitIssueCompletionScoped`
  (lines 316-413+, fixture `temp_git_repo` via `copy_git_template()` in
  `scripts/tests/helpers.py:44-76`) — extend here rather than building new
  scaffolding. New cases: run-window path gets committed; pre-run dirty path
  does not; `pre_run_dirty=None` + non-noise dirt yields `NOT_CLOSED`; the
  preservation ref exists and contains the abandoned content after refusal.
- **Preservation-survives-teardown test** — create a real worktree, refuse a
  close, `git worktree remove --force`, then assert the content is still
  reachable via `refs/ll/abandoned/*`. This is the test that actually pins the
  P1.
- `scripts/tests/test_issue_manager.py` — six
  `patch("little_loops.issue_manager.complete_issue_lifecycle", ...)` sites
  (lines 2667, 2746, 2789, 2843, 2955, 3001) plus a `close_issue`
  mock-return-value test (~2409-2419) mock the lifecycle wholesale, so they stay
  green regardless of this fix. There is **no existing integration test driving
  `complete_issue_lifecycle()` end-to-end through a live git repo from the
  `ll-auto` path** — add the `NOT_CLOSED`-and-requeue coverage here.
- `scripts/tests/test_orchestrator.py::test_complete_lifecycle_commit_excludes_unrelated_dirty_file`
  (lines 3984-4007) — asserts `result is True` (4001) though the commit was
  skipped and frontmatter was still written. Re-examine; expected to stand under
  Proposed Solution #7's no-change conclusion, but assert that deliberately.
- `_porcelain_paths()` (`codequery/codegraph.py:106-121`) has **zero unit
  tests** anywhere in the suite (only two references, both inside
  `codegraph.py`). Per Program Design it moves to `git_operations.py`; add
  coverage for rename lines (`R  old -> new`) and quoted paths in
  `scripts/tests/test_git_operations.py` before depending on it for a refusal
  decision, and keep `test_codequery_codegraph.py` green across the move.
- **Teardown-backstop test** (Proposed Solution #8) — process issue A so it
  orphans a file, then process issue B in the same tree and confirm B does
  *not* sweep A's file into its commit (run-window discrimination holds) *and*
  that A's file is still recoverable from a ref after `git worktree remove
  --force`. This is the case the per-issue snapshot cannot catch on its own.
- **Pre-commit-hook rejection test** (Proposed Solution #10) — install a
  failing hook in the fixture repo, attempt a close carrying a deliverable, and
  assert `NOT_CLOSED` + preserved ref + no `done` frontmatter, rather than a
  `--no-verify` bypass.
- **Non-destructive preservation test** (Proposed Solution #4) — assert the
  working tree and index are byte-identical before and after preservation, the
  regression guard against a `git stash` implementation.
- `scripts/tests/test_builtin_loops.py` (~lines 3035-3159, 3482-3495,
  4902-4958) — existing regression coverage for both loop YAMLs'
  frontmatter-derived counters; verifies "no wiring change expected" holds.

## Impact

**Severity: P1.** Silent, unrecoverable loss of completed implementation work,
combined with a false success signal. Any `ll-auto` / `ll-parallel` /
`ll-sprint` / FSM run that hits the safety-net path is exposed. Recovery is
currently impossible once the worktree is pruned — there is no stash, no branch,
no dangling object. Proposed Solution #4 is what makes recovery possible at all.

## Status

Open. Discovered while auditing run
`.loops/runs/sprint-refine-and-implement-20260731T235717/` (EPIC-2938).
ENH-2943, ENH-2944, and ENH-2952 were reopened; the dangling CLI wiring the
partial commits left behind was stripped in 3e76f972.

Split on 2026-08-01: content-based attribution moved to ENH-2965. (An
unrelated capture briefly also claimed the ID ENH-2965; it was renumbered to
ENH-2970 on 2026-08-01, so all ENH-2965 references in this file unambiguously
mean the attribution split.)

Second pre-implementation review, 2026-08-01: corrected the `pre_run_dirty`
capture anchor from `issue_manager.py:968-975` (the ENH-2958 *post*-implement
snapshot — capturing there would classify the deliverable as pre-existing WIP
and neuter the fix) to `:922-927` alongside `_baseline_sha`; specified index
unstaging + session-log handling on the commit-failure rollback; recommended
`--porcelain -z` for the promoted `porcelain_paths()`.

Pre-implementation review, 2026-08-01 (manual): added Proposed Solution #8-#10,
an `## Acceptance Criteria` section, the non-destructive preservation spec
(#4), and the `porcelain_paths()` promotion. **The `confidence_score: 100` /
`outcome_confidence: 60` frontmatter predates this review and is now stale** —
the change surface grew by the teardown backstop, a shared-helper move, and
snapshot threading at two more call sites. Re-run `/ll:confidence-check` before
dispatching; expect outcome confidence to move down, not up.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-01; re-run after the manual
pre-implementation review added Proposed Solution #8-#10 (teardown backstop,
`porcelain_paths()` promotion, expanded snapshot threading). Findings
re-verified against current tree (`issue_lifecycle.py:414-498`,
`work_verification.py:20-45`, `codequery/codegraph.py:106-121`,
`issue_manager.py:960-980,1110-1165`) — all cited line numbers and behavior
still match._

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 53/100 → LOW (down from 60, as the issue's own prior
note anticipated: the teardown backstop, the `porcelain_paths()` promotion,
and snapshot threading at more call sites widened the change surface since
that score was recorded)

### Outcome Risk Factors
- The change surface has grown to ~8 files across four subsystems:
  `issue_lifecycle.py` (pre-flight helper + `CompletionResult`),
  `issue_manager.py` (snapshot capture + two lifecycle callers),
  `parallel/orchestrator.py` (two `close_issue()` gates), `git_operations.py`
  (new home for `porcelain_paths()` and `preserve_dirty_tree()`),
  `codequery/codegraph.py` (call-site update), plus three unconditional
  `git worktree remove --force` teardown sites (`worktree_utils.py`,
  `parallel/merge_coordinator.py`, `parallel/orchestrator.py`) that all need
  the same preservation helper wired in.
- `_commit_issue_completion()`'s return type changes from `bool` to
  `CompletionResult`, and `close_issue`/`complete_issue_lifecycle` are
  re-exported from `little_loops/__init__.py` — this is a public API
  contract change, not a contained function-body edit.
- Three existing tests (`test_successful_commit`, `test_nothing_to_commit`,
  `test_commit_failure`) assert the current unconditional `True` contract and
  must be rewritten; `_porcelain_paths()` is being promoted into
  `git_operations.py` with zero existing unit test coverage for its
  rename-line and quoted-path handling. Several newly-specified tests
  (teardown-backstop, pre-commit-hook rejection, non-destructive
  preservation) have no existing scaffolding to extend.

## Session Log
- `/ll:confidence-check` - 2026-08-01T16:49:29 - `e664e52a-8464-4540-89e2-6466b8edb359.jsonl`
- `/ll:confidence-check` - 2026-08-01T16:33:29 - `bdc3763a-d563-49bc-9770-c94f54d36615.jsonl`
- `/ll:decide-issue` - 2026-08-01T16:20:02 - `afc4adb0-0a95-4165-88c3-800e01745af6.jsonl`
- `/ll:refine-issue` - 2026-08-01T16:18:51 - `afc4adb0-0a95-4165-88c3-800e01745af6.jsonl`
- `/ll:confidence-check` - 2026-08-01T16:13:17 - `838515db-449f-47b8-a059-4aafd4f03741.jsonl`
- `/ll:confidence-check` - 2026-08-01T15:38:02 - `b4f9b5bc-a25f-4e33-9cac-4183ae2ea1d2.jsonl`
- `/ll:wire-issue` - 2026-08-01T15:35:08 - `a19f79ec-bdc4-4712-a077-60fd1c5b8ba2.jsonl`
- `/ll:refine-issue` - 2026-08-01T15:27:25 - `ace400b0-49a5-450b-9100-27780a9235cb.jsonl`
