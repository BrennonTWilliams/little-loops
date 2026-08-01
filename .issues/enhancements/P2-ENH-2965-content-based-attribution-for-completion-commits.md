---
id: ENH-2965
title: Content-based attribution of dirty paths for callers with no pre-run snapshot
type: ENH
priority: P2
status: open
discovered_date: 2026-08-01
discovered_by: human
testable: true
relates_to:
- BUG-2963
- BUG-2421
- BUG-2424
labels:
- issue-lifecycle
- orchestration
---

# ENH-2965: Content-based attribution of dirty paths for callers with no pre-run snapshot

## Summary

BUG-2963 makes `_commit_issue_completion()` discriminate this run's deliverable
from pre-existing WIP using a **pre-run dirty snapshot** captured by the
orchestrator. A caller that supplies one gets precise behavior: run-window paths
are committed, pre-existing paths are left alone.

> **Precondition satisfied (2026-08-01, commit `709fa788`).** BUG-2963 is
> implemented: the pre-flight is wired into both closure entry points, and
> `ll-auto` (`issue_manager.py:624,949`) and `ll-parallel`
> (`orchestrator.py`, captured at construction) both supply real snapshots. So
> attribution is now genuinely the fallback for snapshot-less callers, not the
> primary path — which is what makes this issue's scope the narrow one it
> describes. See [Precondition history](#precondition-history-resolved).

Callers that **cannot** supply one pass `pre_run_dirty=None` and get BUG-2963's
conservative fallback: any non-noise dirty path means preserve-to-ref and
`NOT_CLOSED`. That is safe — nothing is destroyed and nothing is falsely
reported closed — but it is a blanket refusal. Every close from such a caller in
a tree with any unrelated WIP becomes a not-closed requeue.

This issue adds the second-tier discriminator for that case: attribute dirty
paths by matching them against the issue body's declared `## Integration Map`,
so a snapshot-less caller can still commit what is plausibly this issue's
deliverable instead of refusing outright.

**This is a precision improvement on a path that is already safe.** The
preservation ref and the `NOT_CLOSED` contract it sits on top of are now in
place, so a mis-attribution here can no longer silently destroy work — it
degrades precision, not safety.

## Precondition history (resolved)

Recorded because the analysis below shaped this issue's scope, and because the
corrected anchor is a trap worth keeping written down.

At `040e8c6b` (`wip(bugs): partial BUG-2963 ... [half-wired]`) BUG-2963's core
was defined but never called: `_completion_preflight()` and
`_abandon_and_stamp()` had zero callers, `close_issue()` discarded the
`CompletionResult`, nothing passed `pre_run_dirty`, and none of it was tested.
Attribution would therefore have become the *primary* discriminator for every
caller including `ll-auto` — a far wider blast radius than this issue's scope
assumes.

An earlier draft also cited `issue_manager.py:968-975` as `ll-auto`'s "Phase-2
baseline". That is ENH-2958's `_post_implement_snapshot`: captured at the *end*
of Phase 2 (the wrong side of the run window), scoped to
`tamper_guard_candidate_paths()` (test files + pytest config only), and stored
as content hashes rather than porcelain paths. A snapshot taken there already
contains the whole deliverable, which would classify the implementation as
pre-existing WIP and reproduce the incident.

Resolved in `709fa788`: the pre-flight is wired into `close_issue()` and
`complete_issue_lifecycle()`, `ll-auto` captures snapshots at
`issue_manager.py:624` (Phase-1 close) and `:949` (alongside `_baseline_sha`,
before `run_with_continuation()` — the correct anchor), `ll-parallel` captures
at orchestrator construction, and the teardown backstop preserves non-noise dirt
at all four `git worktree remove --force` sites. `pre_run_dirty=None` is now
reachable only by external API callers — which is exactly the population this
issue serves.

**Remaining sequence:** run the hit-rate measurement below, then implement.

## Pre-implementation measurement (gate)

The expected recovery rate is unvalidated and plausibly low.
`_filter_completion_noise` excludes `.issues/`, `thoughts/`, and `.ll/` — but
**not** `docs/`, `CHANGELOG.md`, or newly created test files. Nearly every real
run touches at least one file the Integration Map does not name, and the
partial-attribution guard (correctly) turns any such run into `mixed` →
`NOT_CLOSED`. Attributable-only therefore fires only when the deliverable set is
a subset of the declared set.

Before implementing, replay a corpus of recently completed issues: take each
issue's actual changed-file set (from its completion commit) and classify it
against its own Integration Map using the matching rule below. Count
attributable-only / unattributable-only / mixed.

- If attributable-only is **below ~20%**, do not implement. The honest answer is
  to invest the effort in BUG-2963's snapshot path, which is a strictly better
  discriminator, and close this issue as `cancelled`.
- Record the measured rate in this issue before proceeding.

## Motivation

BUG-2963's conservative fallback trades precision for safety. The cost lands on:

- `parallel/orchestrator.py`'s `close_issue()` gates (`:1071`, `:1490`), which
  have no equivalent of `ll-auto`'s Phase-2 baseline capture.
- Any future orchestrator or external caller of the public
  `close_issue()` / `complete_issue_lifecycle()` API
  (`scripts/little_loops/__init__.py:34-35`) that closes an issue without
  bracketing the run.
- Manual/CLI closes in a developer's dirty working tree.

For these, "refuse and requeue" is correct but noisy, and a requeued issue costs
a full re-run. Attribution recovers the common case where the dirty paths
obviously belong to the issue being closed.

## Current Behavior

After BUG-2963 lands: `pre_run_dirty=None` + any non-noise dirty path →
preserve to `refs/ll/abandoned/<ID>-<ts>` → `NOT_CLOSED` → issue requeued. No
inspection of *what* the dirty paths are.

## Expected Behavior

When no pre-run snapshot is available, classify each non-noise dirty path:

- **Attributable** — the path matches a write-target path declared by the issue
  body (see [Matching rule](#matching-rule) for the exact predicate).
- **Unattributable** — everything else.

Then:

- Attributable only → stage them with the issue file and commit. `COMMITTED`.
- Unattributable only → BUG-2421's original premise (a human's unrelated WIP in
  a shared tree). Warn, commit the issue file alone, `COMMITTED`.
- **Mixed set** → `NOT_CLOSED` (with BUG-2963's preservation). Rationale below.

### Partial-attribution guard

The mixed case must refuse, not commit the attributable subset. This path fires
after an abnormal subloop exit, so an *incomplete* deliverable is the expected
failure mode. In the observed BUG-2963 incident, `normalize.py` would have
matched the Integration Map while its test files — created during
implementation, never listed under `### Files to Modify` — would not. Committing
only the module would close the issue `done` with its tests destroyed:
the same hollow closure in weaker form.

## Scope Boundaries

**In scope:** the `pre_run_dirty is None` branch of BUG-2963's pre-flight
helper, `_triage_dirty_paths()` / `DirtyPathTriage`, the partial-attribution
guard, and (under option (b)) the `file_hints.py` section-pattern extension plus
re-verification of its four downstream consumers.

**Out of scope:** anything BUG-2963 owns — `CompletionResult`, the
preserve-to-`refs/ll/abandoned/*` mechanism, the caller gating in
`issue_manager.py` / `parallel/orchestrator.py`, the noise filter, and the
pre-run snapshot capture. No new `CompletionResult` or `_PreflightResult`
members are added here. The
snapshot-bearing path (`ll-auto`) is untouched: attribution never runs when a
snapshot is available, because the run window is a strictly better
discriminator.

**Explicitly not attempted:** inferring attribution from file mtimes, from the
subloop's transcript, or from `git log` heuristics. If the Integration Map does
not name it and no snapshot exists, the honest answer is `NOT_CLOSED`.

## Program Design

### Signatures

In `scripts/little_loops/issue_lifecycle.py`:

- `_triage_dirty_paths(info: IssueInfo, paths: frozenset[str]) -> DirtyPathTriage`

  Splits already-parsed, already-noise-filtered repo-relative paths into those
  this issue declares and those it does not. **Takes `_PreflightResult`-style
  parsed paths, not raw porcelain lines** — `_completion_preflight()` already
  holds exactly this set as its local `run_window` (`issue_lifecycle.py:518`);
  re-parsing porcelain here would be the fourth inline parser. The issue file
  itself is already excluded upstream by BUG-2963's resolved-path-equality check
  (`:510-516`).

  `IssueInfo` carries no body text, so this helper reads
  `info.path.read_text(encoding="utf-8")` itself. That is safe **only** because
  the pre-flight runs before any content mutation (Resolution section,
  `status: done`, `completed_at`, session-log append) — the declared-path set is
  read from the pristine issue body. Do not move the call after mutation.

- `DirtyPathTriage` — plain (non-frozen) `@dataclass`:

```python
@dataclass
class DirtyPathTriage:
    attributable: list[str] = field(default_factory=list)
    unattributable: list[str] = field(default_factory=list)
```

### Call Path

Reached only from BUG-2963's pre-flight helper `_completion_preflight()`
(`issue_lifecycle.py:461`), on the snapshot-less branch — i.e. replacing the
blanket refusal at `:520-526`:

```
close_issue() / complete_issue_lifecycle()
  → _completion_preflight() (BUG-2963)
      → pre_run_dirty is not None → run-window discrimination, return  [BUG-2963]
      → pre_run_dirty is None:
          → _triage_dirty_paths(info, run_window)   # already parsed + noise-filtered
              → attributable only    → stage set = [issue file] + attributable
              → unattributable only  → stage set = [issue file], warn  (BUG-2421)
              → mixed                → preserve to ref → NOT_CLOSED    [BUG-2963]
  → (on a proceed verdict) mutate issue file → _commit_issue_completion(stage set)
```

`_triage_dirty_paths()` obtains the declared-path set by calling
`extract_file_hints()` (`parallel/file_hints.py:337`), whose internal
`_extract_write_target_files()` (`:285`) is the function option (b) extends.
Both `close_issue()` (`issue_lifecycle.py:873`) and `complete_issue_lifecycle()`
(`issue_lifecycle.py:972`) reach this only through BUG-2963's pre-flight helper
`_completion_preflight()` (`:461`) — neither calls `_triage_dirty_paths()`
directly.

**The extractor is not scoped to `## Integration Map`.** An earlier draft of
this issue described it that way; in fact `_extract_write_target_files()` scopes
to `### Files to Modify` / `### Files Changed` headings *anywhere in the
document*, regardless of enclosing `##` section
(`file_hints.py:300-304`). Do not add Integration-Map scoping — the four other
`extract_file_hints()` consumers do not have it, and adding it here would fork
the utility's behavior.

### Matching rule

The predicate is **exact string equality between a repo-relative porcelain path
and a declared hint**, plus a declared-directory prefix test. Specifically, a
dirty path `p` is attributable iff either:

1. `p in hints.files`, or
2. some `d in hints.directories` satisfies `p.startswith(d)` (each `d` already
   ends in `/` — `DIR_PATH_PATTERN`, `file_hints.py:26-29`).

Both sides must be normalized to repo-root-relative POSIX form before
comparison: porcelain (`-z`) paths are already repo-root-relative, and
`_completion_preflight()` resolves against `repo_path`.

**No basename or suffix fallback.** `FILE_PATH_PATTERN`
(`file_hints.py:19-22`) does not require a `/`, so a bare `normalize.py` written
in prose is extracted as a hint. Under suffix matching that hint would attribute
*any* dirty `**/normalize.py`; under basename matching it would attribute across
unrelated packages. Both widen attribution in exactly the direction the
partial-attribution guard exists to prevent. A bare-basename hint therefore
simply never matches, and the issue is expected to declare full repo-relative
paths — which the standard Integration Map template already does.

Declared directories **are** in scope (rule 2). An issue declaring
`scripts/little_loops/cli/issues/` attributes dirty files beneath it. This is
the looser half of the rule; if the measurement gate shows it driving
false attribution, drop rule 2 rather than weakening rule 1.

There is no third rule. An earlier draft had a `sole_issue_in_tree` escape
hatch; BUG-2963's pre-run snapshot supersedes it, and it is listed in that
issue's Non-Goals.

### Accepted risk: pre-existing edits to a declared file

With no snapshot there is no way to tell a human's pre-existing uncommitted edit
to `foo.py` from this run's edit to `foo.py` when the issue declares `foo.py`.
Such an edit is attributed and swept into a commit whose message claims it
implements the issue. This is **accepted**: the content reaches git rather than
being destroyed (the BUG-2963 failure mode), and the file is one the issue
legitimately owns. It is a provenance/attribution error, not data loss. It is
also unavoidable without the snapshot — which is the argument for finishing
BUG-2963's wiring rather than leaning on this path.

## Proposed Solution

0. **Precondition** — BUG-2963's caller wiring is complete and the measurement
   gate above has been run and recorded. Do not start otherwise.
1. Add `_triage_dirty_paths(info: IssueInfo, paths: frozenset[str]) -> DirtyPathTriage`
   in `scripts/little_loops/issue_lifecycle.py`, invoked from
   `_completion_preflight()` only on the `pre_run_dirty is None` branch,
   replacing the blanket refusal at `issue_lifecycle.py:520-526`.
2. `DirtyPathTriage` — plain (non-frozen) `@dataclass` with
   `attributable: list[str]` and `unattributable: list[str]`, each
   `field(default_factory=list)`. Model on `FindingMatch`
   (`issue_discovery/matching.py:62-100`) and `FileHints`
   (`parallel/file_hints.py:58-83`). Not `frozen=True`: this codebase reserves
   that for value objects crossing a serialization boundary (`HostCapabilities`,
   `ToolDefinition`), and this is built fresh from porcelain output each call.
3. Reuse BUG-2963's noise filter (`_filter_completion_noise`,
   `issue_lifecycle.py:441`) and `porcelain_paths()`-based parsing; do not add a
   fourth inline porcelain parser. In practice this means consuming
   `_completion_preflight()`'s existing `run_window` local rather than
   re-deriving anything.
4. Express the three outcomes through BUG-2963's existing
   **`_PreflightResult(ok, run_window, dirty_count)`** — *not* `CompletionResult`
   (an earlier draft named the wrong type; `CompletionResult` is
   `_commit_issue_completion()`'s return, one layer down). The mapping:
   attributable-only → `ok=True, run_window=<attributable>`; unattributable-only
   → `ok=True, run_window=frozenset()` plus a warning log; mixed → `ok=False`,
   which the caller already turns into preserve + `NOT_CLOSED`. No new members
   on either type.

### Design decision: how to extract the Integration Map paths

An extractor already exists but is scoped to the wrong subsections.
`extract_file_hints()` (`parallel/file_hints.py:337`) /
`_extract_write_target_files()` (`:285-308`) pulls paths only from
`### Files to Modify` /
`### Files Changed` (regex-scoped via `FILE_PATH_PATTERN` / `_is_valid_path()`).
It does **not** recognize `### Files to Create` — and neither does the standard
Integration Map template
(`scripts/little_loops/templates/feat-sections.json:64-79`), which defines only
`### Files to Modify`, `### Dependent Files`, `### Similar Patterns`,
`### Tests`, `### Documentation`, `### Configuration`.

Two options — **pick one before implementing**:

- **(a) Reuse as-is.** Drop the `Files to Create` reference; attribute only
  against `### Files to Modify` / `### Files Changed`. Zero blast radius. Weaker
  attribution for new-file-heavy issues — which is the shape of the BUG-2963
  incident (`normalize.py`, `rename.py`, `cleanup.py` were all new files), so
  this option would have attributed nothing there.
- **(b) Extend `file_hints.py`'s section pattern** (`:300-304`) to recognize
  create-style headings. Note the pattern is **duplicated verbatim** in
  `_extract_write_target_directories()` (`:322-325`); both copies must be
  extended in lockstep or the matching rule's directory half (rule 2) silently
  diverges from its file half. Prefer hoisting the regex to a single
  module-level constant as part of this change. This is a shared-utility
  behavior change: the output of
  `extract_file_hints()` silently widens for three other callers —
  `dependency_graph.py:472,487` (wave-split contention detection),
  `parallel/overlap_detector.py:14,87,120` (live overlap tracking between
  concurrently-dispatched issues), and `cli/issues/fingerprint.py` /
  `cli/sprint/manage.py`. Each needs its tests re-checked.

If (b) is chosen, the heading regex must tolerate the variants actually present
in the corpus (verified present in `.issues/` on 2026-08-01), not just
`### Files to Create` — including `##`-level headings, which means widening the
leading `###` in the pattern as well as the title alternation:

```
## Files to Create               (P3-FEAT-2088)
### Files to Create             (P4-FEAT-1002, P4-FEAT-1003, P3-FEAT-1536)
### Files to Create/Modify      (P3-FEAT-792)
### New Files to Create         (P3-FEAT-1029)
### Files to Create (Deliverables)  (P4-FEAT-2263)
## Files to Create/Modify       (P2-FEAT-1285)
```

Recommendation: **(b)**, gated on adding the missing test coverage below —
option (a) fails the motivating incident.

## Integration Map

- `scripts/little_loops/issue_lifecycle.py:461-528` — `_triage_dirty_paths()`,
  `DirtyPathTriage`, and the `pre_run_dirty is None` branch of
  `_completion_preflight()` (replacing the blanket refusal at `:520-526`).
- `scripts/little_loops/parallel/file_hints.py:285-334` — section-pattern
  extension in **both** `_extract_write_target_files()` and
  `_extract_write_target_directories()`, **only if option (b)**.

### Dependent Files (Callers/Importers)

_Only relevant under option (b) — these consume `extract_file_hints()` and their
behavior widens silently:_

- `scripts/little_loops/dependency_graph.py:472,487` — wave-split contention
  detection.
- `scripts/little_loops/parallel/overlap_detector.py:14,87,120` — live overlap
  tracking between concurrently-dispatched issues.
- `scripts/little_loops/cli/issues/fingerprint.py`
- `scripts/little_loops/cli/sprint/manage.py`

### Documentation

- `docs/reference/API.md` — the `close_issue` / `complete_issue_lifecycle`
  "Returns" prose updated by BUG-2963 gains the attribution behavior for
  snapshot-less callers.
- `scripts/little_loops/templates/feat-sections.json:64-79` — consider adding a
  `### Files to Create` subsection to the standard Integration Map template, so
  future issues declare new files in a place attribution can find. Optional but
  it is what makes attribution reliable going forward.

### Tests

- `scripts/tests/test_issue_lifecycle.py::TestCommitIssueCompletionScoped`
  (line 316+, fixture `temp_git_repo`) — extend with the three triage
  outcomes: attributable-only commits, unattributable-only warns and commits the
  issue file alone, mixed refuses with preservation.
- **Matching-rule tests** (the predicate is the whole algorithm, so cover it
  directly): exact repo-relative equality attributes; a bare-basename hint
  (`normalize.py` in prose vs. dirty
  `scripts/little_loops/cli/issues/normalize.py`) does **not** attribute; a
  declared directory hint attributes a file beneath it (rule 2); a path outside
  every declared directory does not.
- **Precondition tests owned by BUG-2963, not this issue** — `_completion_preflight`,
  `_abandon_and_stamp`, `preserve_dirty_tree`, and `NOT_CLOSED` propagation to
  `close_issue()` / `complete_issue_lifecycle()` currently have **zero**
  coverage. Confirm they exist and pass before building on them.
- **Regression test for the incident shape**: an issue declaring a new module in
  its Integration Map, with both the module and an undeclared test file dirty →
  must yield `NOT_CLOSED`, not a partial commit.
- `scripts/tests/test_file_hints.py::TestExtractWriteTargetFiles`
  (line 152+) — currently recognizes only `### Files to Modify` /
  `### Files Changed`; no `test_extracts_from_files_to_create` case exists. Add
  it, plus cases for each heading variant listed above, **if option (b)**.
- Re-check the tests of the four `extract_file_hints()` consumers above under
  option (b).

## Impact

Reduces spurious not-closed requeues on snapshot-less close paths — **by an
amount not yet measured**, which is what the measurement gate exists to
establish. The partial-attribution guard means any run touching an undeclared
file (`docs/`, `CHANGELOG.md`, a new test file — none of which
`_filter_completion_noise` excludes) still refuses, so the recoverable
population may be small.

No data-loss exposure of its own — BUG-2963's preservation ref and `NOT_CLOSED`
contract are the safety floor this sits on top of, which is why the dependency
is hard. The one accepted correctness cost is the provenance error described
under [Accepted risk](#accepted-risk-pre-existing-edits-to-a-declared-file).

## Status

Open and unblocked — BUG-2963 landed in `709fa788`, so the `blocked_by` edge
was removed; the remaining gate is the hit-rate measurement, not a dependency.
Split out of BUG-2963 on 2026-08-01 to keep the P1
data-loss fix small: attribution is the part with real false-refusal and
shared-utility risk, and the original single-issue scope scored
`outcome_confidence: 56`.

**Reviewed 2026-08-01** against tree `040e8c6b`. Corrections applied: the
`ll-auto` pre-run-snapshot premise was false (BUG-2963 is unwired and
`issue_manager.py:968-975` is ENH-2958's post-implement tamper snapshot, not a
pre-run porcelain baseline); the matching rule was unspecified and is now
pinned; declared directories were unhandled; the `## Integration Map` scoping
description did not match `_extract_write_target_files()`'s actual
heading-scoped behavior; `_triage_dirty_paths()` took porcelain lines the
pre-flight had already parsed; the return type was named `CompletionResult`
instead of `_PreflightResult`. Added: the accepted-provenance-risk statement and
the hit-rate measurement gate.
