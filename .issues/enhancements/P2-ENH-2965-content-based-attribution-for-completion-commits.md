---
id: ENH-2965
title: Content-based attribution of dirty paths for callers with no pre-run snapshot
type: ENH
priority: P2
status: open
discovered_date: 2026-08-01
discovered_by: human
testable: true
blocked_by:
- BUG-2963
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
orchestrator. Callers that can supply one (`ll-auto`, which already captures a
Phase-2 baseline at `issue_manager.py:968-975`) get precise behavior: run-window
paths are committed, pre-existing paths are left alone.

Callers that **cannot** supply one pass `pre_run_dirty=None` and get BUG-2963's
conservative fallback: any non-noise dirty path means preserve-to-ref and
`NOT_CLOSED`. That is safe — nothing is destroyed and nothing is falsely
reported closed — but it is a blanket refusal. Every close from such a caller in
a tree with any unrelated WIP becomes a not-closed requeue.

This issue adds the second-tier discriminator for that case: attribute dirty
paths by matching them against the issue body's declared `## Integration Map`,
so a snapshot-less caller can still commit what is plausibly this issue's
deliverable instead of refusing outright.

**This is a precision improvement on a path that is already safe.** It must not
be implemented before BUG-2963 — without the preservation ref and the
`NOT_CLOSED` contract underneath it, a mis-attribution silently destroys work
again.

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

- **Attributable** — the path appears in the issue body's `## Integration Map`
  (including a `### Files to Create` subsection, if that extension is chosen).
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
pre-run snapshot capture. No new `CompletionResult` members are added here. The
snapshot-bearing path (`ll-auto`) is untouched: attribution never runs when a
snapshot is available, because the run window is a strictly better
discriminator.

**Explicitly not attempted:** inferring attribution from file mtimes, from the
subloop's transcript, or from `git log` heuristics. If the Integration Map does
not name it and no snapshot exists, the honest answer is `NOT_CLOSED`.

## Program Design

### Signatures

In `scripts/little_loops/issue_lifecycle.py`:

- `_triage_dirty_paths(info: IssueInfo, porcelain_lines: list[str]) -> DirtyPathTriage`

  Splits noise-filtered porcelain lines into paths this issue declares and paths
  it does not. The issue file itself is already excluded upstream by BUG-2963's
  resolved-path-equality check.

- `DirtyPathTriage` — plain (non-frozen) `@dataclass`:

```python
@dataclass
class DirtyPathTriage:
    attributable: list[str] = field(default_factory=list)
    unattributable: list[str] = field(default_factory=list)
```

### Call Path

Reached only from BUG-2963's pre-flight helper, on the snapshot-less branch:

```
close_issue() / complete_issue_lifecycle()
  → pre-flight helper (BUG-2963)
      → pre_run_dirty is not None → run-window discrimination, return  [BUG-2963]
      → pre_run_dirty is None:
          → _triage_dirty_paths(info, noise_filtered_lines)
              → attributable only    → stage set = [issue file] + attributable
              → unattributable only  → stage set = [issue file], warn  (BUG-2421)
              → mixed                → preserve to ref → NOT_CLOSED    [BUG-2963]
  → (on a proceed verdict) mutate issue file → _commit_issue_completion(stage set)
```

`_triage_dirty_paths()` obtains the declared-path set by calling
`extract_file_hints()` (`parallel/file_hints.py:287`), whose internal
`_extract_write_target_files()` is the function option (b) extends. Both
`close_issue()` (`issue_lifecycle.py:650`) and `complete_issue_lifecycle()`
(`issue_lifecycle.py:749`) reach this only through BUG-2963's pre-flight helper
— neither calls `_triage_dirty_paths()` directly.

Attribution rule, in precedence order:

1. Path appears in the issue body's `## Integration Map` (including its
   create-style subsections, if option (b)) → attributable.
2. Otherwise → unattributable.

There is no third rule. An earlier draft had a `sole_issue_in_tree` escape
hatch; BUG-2963's pre-run snapshot supersedes it, and it is listed in that
issue's Non-Goals.

## Proposed Solution

1. Add `_triage_dirty_paths(info: IssueInfo, porcelain_lines: list[str]) -> DirtyPathTriage`
   in `scripts/little_loops/issue_lifecycle.py`, invoked from BUG-2963's
   pre-flight helper only on the `pre_run_dirty is None` branch.
2. `DirtyPathTriage` — plain (non-frozen) `@dataclass` with
   `attributable: list[str]` and `unattributable: list[str]`, each
   `field(default_factory=list)`. Model on `FindingMatch`
   (`issue_discovery/matching.py:62-100`) and `FileHints`
   (`parallel/file_hints.py:58-83`). Not `frozen=True`: this codebase reserves
   that for value objects crossing a serialization boundary (`HostCapabilities`,
   `ToolDefinition`), and this is built fresh from porcelain output each call.
3. Reuse BUG-2963's noise filter and `_porcelain_paths()`-based parsing; do not
   add a fourth inline porcelain parser.
4. Wire the three outcomes into BUG-2963's existing `CompletionResult` return —
   no new result values.

### Design decision: how to extract the Integration Map paths

An extractor already exists but is scoped to the wrong subsections.
`extract_file_hints()` / `_extract_write_target_files()`
(`parallel/file_hints.py:287-365`) pulls paths only from `### Files to Modify` /
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
- **(b) Extend `file_hints.py`'s section pattern** (`:301-304`) to recognize
  create-style headings. This is a shared-utility behavior change: the output of
  `extract_file_hints()` silently widens for three other callers —
  `dependency_graph.py:472,487` (wave-split contention detection),
  `parallel/overlap_detector.py:14,87,120` (live overlap tracking between
  concurrently-dispatched issues), and `cli/issues/fingerprint.py` /
  `cli/sprint/manage.py`. Each needs its tests re-checked.

If (b) is chosen, the heading regex must tolerate the variants actually present
in the corpus, not just `### Files to Create`:

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

- `scripts/little_loops/issue_lifecycle.py` — `_triage_dirty_paths()`,
  `DirtyPathTriage`, and the `pre_run_dirty is None` branch of BUG-2963's
  pre-flight helper.
- `scripts/little_loops/parallel/file_hints.py:287-365` — section-pattern
  extension, **only if option (b)**.

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
  (lines 316-413+, fixture `temp_git_repo`) — extend with the three triage
  outcomes: attributable-only commits, unattributable-only warns and commits the
  issue file alone, mixed refuses with preservation.
- **Regression test for the incident shape**: an issue declaring a new module in
  its Integration Map, with both the module and an undeclared test file dirty →
  must yield `NOT_CLOSED`, not a partial commit.
- `scripts/tests/test_file_hints.py::TestExtractWriteTargetFiles`
  (lines 152-224) — currently recognizes only `### Files to Modify` /
  `### Files Changed`; no `test_extracts_from_files_to_create` case exists. Add
  it, plus cases for each heading variant listed above, **if option (b)**.
- Re-check the tests of the four `extract_file_hints()` consumers above under
  option (b).

## Impact

Reduces spurious not-closed requeues on snapshot-less close paths. No data-loss
exposure of its own — BUG-2963's preservation ref and `NOT_CLOSED` contract are
the safety floor this sits on top of, which is why the dependency is hard.

## Status

Open, blocked by BUG-2963. Split out of BUG-2963 on 2026-08-01 to keep the P1
data-loss fix small: attribution is the part with real false-refusal and
shared-utility risk, and the original single-issue scope scored
`outcome_confidence: 56`.
