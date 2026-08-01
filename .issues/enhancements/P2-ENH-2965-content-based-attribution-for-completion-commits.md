---
id: ENH-2965
title: Content-based attribution of dirty paths for callers with no pre-run snapshot
type: ENH
priority: P2
status: cancelled
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
confidence_score: 80
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
decision_needed: false
size: Very Large
reconcile_attempted: true
cancelled_reason: >-
  Pre-implementation measurement gate failed (2026-08-01): attributable-only
  10.6% (Option A) / 16.4% (Option B) against a n=574 commit corpus, below the
  ~20% threshold this issue set for itself. The measurement additionally
  invalidated the unattributable-only -> COMMITTED mapping as a hollow-closure
  risk. Effort redirected to BUG-2963's snapshot path.
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

### Measured result (2026-08-01, tree `674a52fa`) — GATE FAILS

Replayed against the repo's own history. Corpus: every commit whose subject
names exactly one issue ID that exists in `.issues/` (one commit ≈ one run
window), changed-file set noise-filtered through the real
`filter_ll_noise()`, classified against that issue's own declared hints using
this issue's Matching rule. n=574 commits.

| Verdict | Option A (as-is) | Option B (widened headings) |
|---|---|---|
| attributable-only | 61 (**10.6%**) | 94 (**16.4%**) |
| unattributable-only | 293 (51.0%) | 238 (41.5%) |
| mixed | 220 (38.3%) | 242 (42.2%) |

A coarser per-issue variant (union of all commits per issue, n=2300) gives
8.8% / 12.0% — worse, as expected from unioning follow-ups.

**Both options fall below the ~20% threshold**, and 16.4% is an *optimistic*
upper bound: hints are read from each issue's current body, which in some cases
had its Integration Map updated during or after implementation.

The predicted cause is confirmed. Undeclared paths forcing `mixed` under
Option B, by root: `scripts/` 717, `docs/` 240, `skills/` 104, `commands/` 25,
`hooks/` 13, `CHANGELOG.md` 11, `README.md` 11, `CONTRIBUTING.md` 11. Issues
routinely touch files their Integration Map never names — most often their own
new test files under `scripts/tests/` and doc updates.

### Design flaw surfaced by the measurement: unattributable-only is a hollow closure

The measurement also invalidates a premise the design rests on, independent of
the hit rate. Expected Behavior maps **unattributable-only → warn, commit the
issue file alone, `COMMITTED`**, on the reading that unattributable dirt is "a
human's unrelated WIP in a shared tree" (BUG-2421's premise).

At 41.5% of real runs, *nothing* in the changed set matches the issue's own
declared hints. In that population the unattributable dirt **is** the
deliverable, not a bystander's WIP — so the design would mark the issue `done`
while committing only the issue file, leaving the entire deliverable
uncommitted. That is the same hollow closure BUG-2963 exists to prevent, in a
stronger form than the `mixed` case the partial-attribution guard was written to
catch. BUG-2963's teardown backstop still preserves the tree to
`refs/ll/abandoned/*` at worktree-removal sites, so this is a false `done`
rather than data loss — but it converts today's *safe refusal* into a false
success for the single largest slice of the distribution.

The rule "unattributable ⇒ not this issue's work" is not supported by the data;
the base rate of an issue's own deliverable failing to match its declared hints
is too high for that inference to hold. Any revival of this issue must drop the
unattributable-only → `COMMITTED` mapping and refuse there too, which leaves
only the 16.4% attributable-only slice as the recoverable population.

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

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

This codebase already holds a convention for exactly the "hoist a duplicated
heading regex to a single module-level constant" step called for under option
(b): `_OPTION_HEADING_RE` (`scripts/little_loops/issue_parser.py:862-871`) is a
private, `re.compile`-d, module-level constant with a comment describing the
heading variants its alternation covers, threaded through one helper
(`_iter_option_blocks`) rather than being recompiled at each call site.
`file_hints.py`'s current two inline copies of the `Files to Modify|Files
Changed` section pattern (`:301-304`, `:327-330`) are the outlier relative to
that convention, not an instance of it — no separate precedent search is
needed to justify the hoist.

The `DirtyPathTriage` dataclass shape (plain, non-frozen, `list[str] =
field(default_factory=list)`) is likewise a well-established pattern beyond
just `FindingMatch`/`FileHints`: `WorkerResult` (`parallel/types.py:52-94`),
`RegressionEvidence` (`issue_discovery/matching.py:44-59`), `OverlapResult`
(`parallel/overlap_detector.py:24-39`), and `OrchestratorState`
(`parallel/types.py:232-256`) all follow the same shape.

There is no dedicated repo-relative POSIX path normalization utility in this
codebase for the matching-rule comparison — `FileHints`/`overlap_detector.py`
compare raw extracted strings as-is (`_directories_overlap()` /
`_file_in_directory()`, `file_hints.py:247-284`, do only an ad hoc
`.rstrip("/") + "/"`). The "normalized to repo-root-relative POSIX form"
premise this issue's Matching rule states holds because `porcelain_paths()`
(`git_operations.py:546`) already returns repo-root-relative POSIX strings by
construction, not because a shared normalizer is called — there is nothing to
add or call here, but an implementer should not go looking for one.

#### Codebase Research Findings — Option-Count Detection (`/ll:refine-issue`)

`decision_needed: true` is set in this issue's frontmatter, but
`ll-issues check-decidable ENH-2965` currently returns `OPTIONS_MISSING`: the
two alternatives above are written as `- **(a) ...**` / `- **(b) ...**`
bullets, a form the decidability probe does not recognize. Restating the same
alternatives (verbatim content, no new analysis) in the bold-label form the
probe scans for:

**Option A**: Reuse `extract_file_hints()` / `_extract_write_target_files()`
as-is. Drop the `Files to Create` reference; attribute only against
`### Files to Modify` / `### Files Changed`. Zero blast radius. Weaker
attribution for new-file-heavy issues — which is the shape of the BUG-2963
incident (`normalize.py`, `rename.py`, `cleanup.py` were all new files), so
this option would have attributed nothing there.

> **Selected:** Option B — extends the heading pattern to cover the
> motivating incident's shape; see Decision Rationale below.

**Option B**: Extend `file_hints.py`'s section pattern (`:300-304`,
duplicated at `:322-325`) to recognize create-style headings, hoisting the
duplicated regex to a single module-level constant as part of the change
(this codebase's established convention for this exact situation — see
`_OPTION_HEADING_RE`, `issue_parser.py:862-871`, confirmed by pattern-finder
research above). Widens `extract_file_hints()`'s output for its three other
consumers (`dependency_graph.py:472,487`, `overlap_detector.py:14,87,120`,
`cli/issues/fingerprint.py`, `cli/sprint/manage.py`); each needs its tests
re-checked.

**Recommended**: Option B — gated on adding the missing test coverage
described under Tests below; Option A fails the motivating incident.

### Decision Rationale

**Selected: Option B** (extend `file_hints.py`'s section-heading pattern to
recognize `### Files to Create`-style variants, hoisting the duplicated regex
to a single module-level constant).

**Reasoning**: Option A is cheaper and carries zero blast radius, but it
structurally cannot solve the problem this issue exists to fix — the BUG-2963
incident's own new files (`normalize.py`, `rename.py`, `cleanup.py`) were
declared only under `### Files to Create`-style headings, which
`_extract_write_target_files()` does not scan today (confirmed at
`file_hints.py:301-304`). An option that can't attribute the motivating case
isn't a real fallback, regardless of how safe it is. Option B has a clean,
already-established precedent for the exact refactor it requires
(`_OPTION_HEADING_RE`, `issue_parser.py:868-871` — module-level compiled
regex, heading alternation, single point of definition), and pattern-finder
research confirmed none of the four downstream `extract_file_hints()`
consumers (`dependency_graph.py`, `overlap_detector.py`, `fingerprint.py`,
`cli/sprint/manage.py`) have existing test fixtures using `Files to Create`
headings — so widening recognition doesn't flip any existing assertion, only
adds previously-inert paths to their input. The added complexity is real
(hoist + pattern widen, plus re-checking four consumer test suites) but
contained and precedented.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 0/3 — fails the motivating incident entirely | 3/3 — direct codebase precedent, satisfies the issue's stated purpose |
| Simplicity | 3/3 — zero code change | 2/3 — mechanical hoist + regex widen |
| Testability | 3/3 — no new coverage needed | 2/3 — new heading-variant tests + 4 consumer suites to re-check |
| Risk | 3/3 — zero blast radius | 2/3 — widens a shared utility across 4 consumers, but no existing test fixture uses `Files to Create` headings, so no assertion flips |
| **Total** | **9/12** | **9/12** |

Tied on total; Consistency is the tiebreaker per this skill's scoring rules,
and Option B wins decisively there (3 vs 0) since Option A cannot attribute
the exact new-file-heavy shape that motivated ENH-2965.

**Key evidence**:
- `file_hints.py:301-304`/`:327-330` — both extraction helpers scope to the
  identical regex `r"###\s*(?:Files to Modify|Files Changed)\s*\n..."`, with
  no `Files to Create` alternative.
- `.issues/` corpus: `### Files to Create`-style headings appear in ~130-153
  files (~7% of the corpus) — a real, non-trivial population, not an edge
  case.
- `scripts/tests/test_file_hints.py::TestExtractWriteTargetFiles` has zero
  coverage of `Files to Create` today (neither positive nor
  documented-gap-negative), and `test_dependency_graph.py` /
  `test_overlap_detector.py` / `test_ll_issues_fingerprint.py` /
  `test_sprint.py::TestSprintAnalyze` contain no `Files to Create` fixture
  text — confirming the widen is additive, not fixture-breaking.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/__init__.py` — re-exports `FileHints` and
  `extract_file_hints` in its own `__all__`, a second public surface (beyond
  the four call sites above) through which the widened heading-recognition
  behavior becomes externally visible under `little_loops.parallel`'s
  namespace. No code change needed, only relevant under option (b).

### Documentation

- `docs/reference/API.md` — the `close_issue` / `complete_issue_lifecycle`
  "Returns" prose updated by BUG-2963 gains the attribution behavior for
  snapshot-less callers.
- `scripts/little_loops/templates/feat-sections.json:64-79` — consider adding a
  `### Files to Create` subsection to the standard Integration Map template, so
  future issues declare new files in a place attribution can find. Optional but
  it is what makes attribution reliable going forward.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/git_operations.py::snapshot_dirty_paths()` docstring
  (~line 596-614) — describes the `pre_run_dirty` contract in
  `close_issue()`/`complete_issue_lifecycle()` subtraction terms but doesn't
  mention the new `pre_run_dirty is None` attribution fallback; a reader
  following this docstring alone would still believe the `None` case is a
  blanket refusal. Update alongside `docs/reference/API.md`.

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

  #### Codebase Research Findings

  _Added by `/ll:refine-issue` — based on codebase analysis (tree `f95a5e74`):_

  The "currently zero coverage" premise above is now stale — this precondition
  is satisfied, not open. `TestCommitIssueCompletionScoped`
  (`scripts/tests/test_issue_lifecycle.py:316+`) has direct, non-trivial
  coverage of every BUG-2963 mechanism named above:
  - `_completion_preflight`: `test_run_window_path_is_committed_with_the_issue_file`
    (`:450-478`), `test_pre_existing_wip_is_left_untouched` (`:480-504`),
    `test_no_snapshot_with_dirt_refuses` (`:506-521` — exercises exactly the
    `:520-526` refusal branch this issue targets; its own docstring at
    `:509-512` already flags itself as "the conservative branch ENH-2965 later
    replaces with content-based attribution"), `test_noise_paths_never_force_a_refusal`
    (`:523-535`), `test_issue_file_excluded_by_path_equality` (`:537-547`).
  - `_abandon_and_stamp` / `preserve_dirty_tree`: `test_abandon_preserves_tree_non_destructively`
    (`:549-572`), `test_deliverable_survives_worktree_removal` (`:637-672`, uses
    `git worktree remove --force` to pin the P1 recoverability guarantee).
  - `NOT_CLOSED` propagation end-to-end: `test_complete_issue_lifecycle_commits_the_deliverable`
    (`:574-607`), `test_complete_issue_lifecycle_refuses_without_snapshot`
    (`:609-635`), `test_commit_failure_rolls_back_and_preserves` (`:674+`).

  `porcelain_paths()`, `preserve_dirty_tree()`, and `filter_ll_noise()` (consumed
  by `_filter_completion_noise`, `issue_lifecycle.py:441`) live in
  `scripts/little_loops/git_operations.py`, not `issue_lifecycle.py`.
- **Regression test for the incident shape**: an issue declaring a new module in
  its Integration Map, with both the module and an undeclared test file dirty →
  must yield `NOT_CLOSED`, not a partial commit.
- `scripts/tests/test_file_hints.py::TestExtractWriteTargetFiles`
  (line 152+) — currently recognizes only `### Files to Modify` /
  `### Files Changed`; no `test_extracts_from_files_to_create` case exists. Add
  it, plus cases for each heading variant listed above, **if option (b)**.
- Re-check the tests of the four `extract_file_hints()` consumers above under
  option (b).

  #### Codebase Research Findings

  _Added by `/ll:refine-issue` — based on codebase analysis:_

  Located test files for the four consumers named above: `scripts/tests/test_dependency_graph.py`,
  `scripts/tests/test_overlap_detector.py`, `scripts/tests/test_ll_issues_fingerprint.py`,
  and `scripts/tests/test_manage_issue_changelog_gate.py` (covers
  `cli/sprint/manage.py`'s conflict analysis despite the name mismatch).

  > ⚠ Correction (`/ll:refine-issue`, gap-analysis pass, tree `f95a5e74`):
  > `test_manage_issue_changelog_gate.py` is unrelated — it covers the
  > changelog-gate staged-diff/skill checks, not sprint conflict analysis
  > (verified: no `sprint`/`analyze`/`hints` references in that file). The
  > actual coverage for `cli/sprint/manage.py`'s `_cmd_sprint_analyze()` (the
  > function that calls `extract_file_hints()`) is
  > `scripts/tests/test_sprint.py::TestSprintAnalyze` (`:1879+`);
  > `scripts/tests/test_cli_sprint.py` additionally covers the CLI
  > routing/flag-forwarding for the `analyze`/`a` subcommand
  > (`test_analyze_routes_to_handler`, `test_analyze_alias_a_routes_to_handler`,
  > `test_analyze_forwards_format_flag`).

_Wiring pass added by `/ll:wire-issue`:_
- **`test_no_snapshot_with_dirt_refuses` must be rewritten, not just left
  alongside new tests.** Its fixture issue body is
  `"---\nstatus: done\n---\n\n# BUG-001: Test Bug\n"` — no `## Integration
  Map` / `### Files to Modify` section at all — then dirties a bare
  `something.py` and asserts `preflight.ok is False` /
  `preflight.dirty_count == 1`. Under the new triage logic `something.py` is
  declared nowhere, so it lands in "unattributable only," which this issue's
  own design maps to `ok=True` (commit the issue file alone, warn) — the
  opposite of what the test currently asserts. The existing "extend with the
  three triage outcomes" framing above reads as additive; this one is a
  required rewrite of existing assertions.
- `scripts/tests/test_interceptor_extension.py:141,175` — imports and directly
  constructs `_PreflightResult` (`_PreflightResult(ok=True,
  run_window=frozenset())`) to patch `_completion_preflight`'s return value.
  Unaffected as long as no new `_PreflightResult` members are added (per this
  issue's own constraint), but re-check after implementation since it's a
  second existing consumer of that type's shape.
- No integration/e2e test currently exercises a `pre_run_dirty=None` close in
  a dirty tree at the `ll-auto`/`ll-parallel`/orchestrator level — every
  production caller there (`orchestrator.py:1097,1518`,
  `issue_manager.py:808,1145,1167`) always passes an explicit snapshot. This
  is consistent with the issue's stated scope (external API callers, not
  `ll-auto`), so no new test is required, but the only place the new triage
  logic is reachable in tests is the unit level in `test_issue_lifecycle.py`
  — worth confirming that's an accepted coverage boundary, not an oversight.
- `test_complete_issue_lifecycle_emits_event`
  (`scripts/tests/test_issue_lifecycle.py:1682-1689`) has an inline comment
  documenting today's blanket-refusal semantics ("a blanket `[main abc]
  commit` would be parsed as a dirty path and ... refuse the close") — a
  drive-by comment update once the branch changes, not a test-behavior risk
  (this test mocks `subprocess.run` wholesale, so `run_window` is always
  empty and it isn't exercised by the new logic).

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

**Cancelled 2026-08-01** — the pre-implementation gate was run and failed; see
[Measured result](#measured-result-2026-08-01-tree-674a52fa--gate-fails).
Attributable-only is 10.6% (Option A) / 16.4% (Option B), both under the ~20%
threshold this issue set for itself, and the measurement additionally
invalidated the unattributable-only → `COMMITTED` mapping as a hollow-closure
risk. Per Proposed Solution step 0 and the gate's own instruction, the effort is
redirected to BUG-2963's snapshot path, which is a strictly better
discriminator. Cancelled rather than deferred: this is a settled negative
result, not work waiting on a blocker.

The one piece worth carrying forward independently is the optional item under
[Documentation](#documentation) — adding a `### Files to Create` subsection to
the standard Integration Map template
(`scripts/little_loops/templates/feat-sections.json`). That is what would
actually move the hit rate for any future revival; the `file_hints.py` regex
widen alone does not.

Prior state: open and unblocked — BUG-2963 landed in `709fa788`, so the
`blocked_by` edge was removed; the remaining gate was the hit-rate measurement,
not a dependency. An automation pass had deferred it `readiness_stagnated` on
2026-08-01T20:35:17Z; that deferral is superseded by this cancellation.
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


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-01_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 63/100 → LOW

### Concerns
- The issue's own "Pre-implementation measurement (gate)" section has not been run: no attributable-only/unattributable-only/mixed hit rate is recorded anywhere in the file, and the Proposed Solution's step 0 says "Do not start otherwise." This is the single largest readiness gap — everything else in the issue (Program Design, matching rule, test plan) is unusually thorough and verified accurate against the current tree.
- The option (a) vs option (b) design decision for extracting `### Files to Create`-style paths is recommended (b) but not formally locked — no `decision_needed`-style resolution exists yet in the file itself (this check is setting the flag now).

### Outcome Risk Factors
- Open decision: option (a) (reuse `file_hints.py` as-is) vs option (b) (extend its section-pattern regex) is unresolved — either choice changes the blast radius (0 dependents under (a) vs 4 consumers — `dependency_graph.py`, `overlap_detector.py`, `fingerprint.py`, `manage.py` — plus a package re-export under (b)) and should be pinned before implementation starts.
- The unmeasured hit-rate gate could invalidate the entire issue: the issue's own text says if attributable-only comes in below ~20%, the correct outcome is to cancel this issue and invest in BUG-2963 instead, not to implement it. Implementation effort is contingent on data not yet collected.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-01_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- The "Pre-implementation measurement (gate)" section still has not been run: no attributable-only/unattributable-only/mixed hit rate is recorded anywhere in the file, and Proposed Solution step 0 still says "Do not start otherwise." This remains the single largest readiness gap; it is a precondition on whether to implement at all, not a design-time ambiguity, so it does not move the Ambiguity outcome score.
- The option (a) vs (b) decision that the previous confidence-check flagged as open is now resolved: `/ll:decide-issue` selected Option B, `decision_needed` is `false`, and the Program Design/Decision Rationale sections give it full weight — this materially improved outcome confidence (63 → 75) and readiness Criterion C (Ambiguity, 10 → 18) versus the prior run.
- Program Design gate (`ll-issues format-check --format json`) reports no `program_design_nonspecific` or missing/empty Program Design section — the gate is satisfied and does not block this issue.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-01_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- No change since the prior two confidence-check passes: HEAD (`f95a5e74`) is the exact tree the last reconcile pass verified against, and the "Pre-implementation measurement (gate)" hit-rate still has not been recorded anywhere in the file. Proposed Solution step 0 still reads "Do not start otherwise" — this remains the sole readiness gap (Dependencies Satisfied scores 0/20 for this reason alone; all four other readiness criteria are 20/20).
- Program Design gate (`ll-issues format-check --format json`) reports no `program_design_nonspecific` / missing / empty findings — the gate is satisfied and does not block this issue.

## Session Log
- `/ll:confidence-check` - 2026-08-01T20:34:49 - `b5ab73bb-1327-4a73-846d-c8deeb5e603d.jsonl`
- `/ll:reconcile-issue` - 2026-08-01T20:32:53 - `6b6e2e81-bd4d-4201-b5a3-baf1a83177eb.jsonl`
- `/ll:confidence-check` - 2026-08-01T20:30:08 - `ea89c7ad-c2c0-4853-8aba-bfc517aff062.jsonl`
- `/ll:decide-issue` - 2026-08-01T20:27:33 - `d6aa2bcf-d196-4e65-8a21-094773ffa839.jsonl`
- `/ll:refine-issue` - 2026-08-01T20:23:29 - `0ecc92e1-8533-47d1-bef7-5de9379cfd85.jsonl`
- `/ll:confidence-check` - 2026-08-01T20:18:11 - `9eb7d6fe-3829-43b4-ab8d-409028f0f007.jsonl`
- `/ll:wire-issue` - 2026-08-01T20:14:21 - `c5dcc62f-93fc-46c3-96d1-a487b53d3afa.jsonl`
- `/ll:refine-issue` - 2026-08-01T20:07:28 - `ceba2490-6537-4a6b-a502-5312eb3582d2.jsonl`
