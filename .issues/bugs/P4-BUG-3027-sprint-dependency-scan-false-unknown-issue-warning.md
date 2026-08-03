---
id: BUG-3027
status: done
captured_at: '2026-08-03T17:14:59Z'
discovered_date: 2026-08-03
discovered_by: capture-issue
testable: false
confidence_score: 75
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
size: Very Large
---

# ll-sprint prints "depends_on unknown issue" for a dependency that exists and is done

## Summary

At the very start of `ll-sprint run epic-3008`, before wave scheduling, the
runner printed `Issue ENH-3015 has depends_on unknown issue BUG-3009` — but
BUG-3009 existed on disk and was later confirmed `done` (its completion
correctly resolved the `depends_on: [BUG-3009]` blocker for ENH-3015 during
wave 6's `ready-issue` pass). The warning is spurious: the dependency wasn't
actually unknown, just excluded from the lookup set used at scan time.

The warning is emitted by `DependencyGraph.from_issues()` in
`scripts/little_loops/dependency_graph.py` (classmethod starting line 56),
at line 145 (analogous `blocked_by`/`blocks` warnings at lines 113 and 130).

## Current Behavior

Before `from_issues()` runs, callers build the `all_known_ids` set via
`gather_all_issue_ids()` in
`scripts/little_loops/dependency_mapper/operations.py:365-394`, which scans
`issues_dir/{bugs,features,enhancements,epics}` with a **non-recursive**
`d.glob("*.md")` (line 390) and extracts IDs via
`r"(BUG|FEAT|ENH|EPIC)-(\d+)"` (line 391). The three call sites —
`issue_manager.py:1471` (IssueManager `__init__`, the sprint-run path),
`sprint.py:381` (EPIC resolution), and `issue_parser.py:2126` — each wrap
the `gather_all_issue_ids()` call in a bare `try/except Exception` that
silently falls back to `all_known_ids = active_ids_set` (i.e., only
currently-active/open issues) if the call raises for any reason.

If `gather_all_issue_ids()` raised silently and the fallback engaged,
`all_known_ids` would be `active_ids_set` only — which excludes BUG-3009 if
it was already `done` (not "active") by the time the sprint kicked off,
producing exactly the observed "unknown issue" false positive for a
dependency that is real but already resolved.

## Expected Behavior

The dependency-known-ness check used for `depends_on`/`blocked_by`/`blocks`
validation should include done/cancelled issues, not just active ones — a
`depends_on` pointing at a `done` issue is a *satisfied* dependency, not an
unknown one, and should never trigger the "unknown issue" warning. If
`gather_all_issue_ids()` throws in the normal case (not just as a defensive
fallback), that exception should surface (or at least be logged), not be
silently swallowed and replaced with a much narrower active-only set.

## Motivation

This warning is currently harmless noise (the dependency resolved correctly
moments later), but it undermines trust in the dependency-scan output at
sprint kickoff — a real "unknown issue" (e.g. a typo'd ID with no matching
file at all) would look identical to this false positive, so operators
can't currently tell them apart from the log line alone.

## Steps to Reproduce

1. Have an issue `X` with `depends_on: [Y]` where `Y` is `status: done`.
2. Run `ll-sprint run <epic>` including issue `X`.
3. Observe `Issue X has depends_on unknown issue Y` printed at kickoff, even
   though `Y` exists and is done.

## Root Cause

- **File**: `scripts/little_loops/dependency_mapper/operations.py`
- **Anchor**: `in gather_all_issue_ids()`, lines 365-394 (non-recursive glob,
  line 390)
- **Cause**: Not yet confirmed between two candidate causes — needs a repro
  with instrumentation to distinguish them:
  1. The bare `try/except Exception` at each of the three call sites
     (`issue_manager.py:1471`, `sprint.py:381`, `issue_parser.py:2126`)
     silently swallowed a real exception from `gather_all_issue_ids()` and
     fell back to `active_ids_set`, which excludes BUG-3009 once it's
     `done`.
  2. Or `gather_all_issue_ids()`'s non-recursive `d.glob("*.md")` (line 390)
     missed BUG-3009's file because it lives in a nested subdirectory of
     `bugs/` that a non-recursive glob doesn't visit.
  Given the warning specifically says "unknown" for an issue that resolved
  correctly moments later once evaluated as `done`, (1) is the more likely
  explanation — the silent except-fallback directly explains why a
  known-but-done issue would drop out of the lookup set.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- **Confirmed root cause (sprint.py call site)**: candidate (1) — the `all_known_ids` set excluding done issues — was the actual mechanism, but not via a swallowed exception. Before this issue was captured, the *normal (non-exception) path* at `sprint.py:367` (pre-fix) passed `active_ids_set` (built at `sprint.py:350` from `find_issues(..., status_filter=_ACTIVE_STATUSES)`, which excludes `done`/`cancelled`/`deferred`) directly as `all_known_ids`, with no `gather_all_issue_ids()` call and no try/except at all at that time. BUG-3009 (`done`) was excluded from that set by construction — this triggered the warning at `dependency_graph.py:143-146` on the ordinary path, not a swallowed exception.
- **Candidate (2) refuted**: `gather_all_issue_ids()`'s non-recursive `d.glob("*.md")` (`dependency_mapper/operations.py:390`) cannot miss BUG-3009 — `.issues/{bugs,features,enhancements,epics}/` has no nested subdirectory level anywhere in this repo (confirmed via glob sweep), so a non-recursive scan finds every issue file directly under its type dir.
- **Already fixed for the sprint.py path**: commit `15152136` ("fix(sprint): warn only on truly dangling refs in resolve_epic", 2026-08-03) — closing `BUG-3024` (status: `done`, completed `2026-08-03T15:44:23Z`, captured *before* this issue) — replaced the `active_ids_set` argument at `sprint.py:367` with one derived from `gather_all_issue_ids()`, wrapped in `try/except Exception: all_known_ids = active_ids_set` (the fallback this issue's Root Cause candidate (1) describes now exists, but only as a defensive degrade-path, marked `# pragma: no cover - defensive, mirrors issue_parser`). Two regression tests already cover exactly this issue's repro and pass on `main` today: `test_sprint.py::TestSprintManagerLoadOrResolve::test_load_or_resolve_epic_depends_on_done_issue_no_warning` and `...::test_load_or_resolve_epic_depends_on_dangling_issue_still_warns` (both PASSED, verified 2026-08-03).
- **Remaining scope, if any**: two other call sites build `all_known_ids` the same way but degrade differently on exception — neither falls back to `active_ids_set`:
  - `issue_manager.py:1509-1521` (`AutoManager.__init__`) — leaves `all_known_ids = None` and logs at `debug` level only.
  - `issue_parser.py:2118-2126` (`find_issues()`'s `skip_blocked` branch) — leaves `all_known_ids = None` via a bare `except Exception: pass`, no logging at all.
  Per `dependency_graph.py`'s guard (`if all_known_ids is None or ... not in all_known_ids: warn`), `None` triggers warnings on *every* reference outside the graph — a stricter failure mode than `active_ids_set`, but reachable only if `gather_all_issue_ids()` itself raises (not on the normal path this issue's repro exercises). Neither branch is exercised by any existing test.

## Proposed Solution

TBD - requires investigation to confirm which of the two Root Cause
candidates applies, then:
1. If (1): either don't swallow the exception silently (log it at minimum),
   or scope the fallback's `all_known_ids` to include done/cancelled issues
   too, not just `active_ids_set`.
2. If (2): make `gather_all_issue_ids()`'s glob recursive, or confirm issue
   files are guaranteed to live directly under their type directory (no
   nesting) and this candidate is ruled out.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- **Candidate (1) confirmed, candidate (2) refuted** (see Root Cause) — no glob-to-rglob change is needed; nested subdirectories don't exist under `.issues/{bugs,features,enhancements,epics}/`.
- **The described repro is already fixed** on the sprint.py path by commit `15152136` / `BUG-3024` (status: done). If any further action is still wanted here, it is narrower than the original two-branch TBD above: decide whether the `issue_manager.py:1509-1521` and `issue_parser.py:2118-2126` exception-fallback branches (currently untested, and stricter than `active_ids_set` since they degrade to `None`) should also gain a `gather_all_issue_ids`-derived fallback for consistency with `sprint.py`'s post-fix shape, and/or gain regression tests exercising the exception path itself (none of the three call sites currently has one). This is a follow-on hardening question, not a reproduction of the originally reported symptom.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- **Logging-on-swallowed-exception convention (Q1)**: no single codebase-wide rule — at least three coexisting conventions, split roughly by call site:
  - Bare `except Exception: pass` (no log) is the *majority* pattern specifically at other `gather_all_issue_ids()` call sites not previously enumerated: `cli/issues/sequence.py:74-81`, `cli/issues/next_issues.py:57-64`, `cli/issues/next_issue.py:67-74`, `cli/issues/link.py:223-228`, and `issue_parser.py:2118-2126` (already cited).
  - `logger.debug(...)` with an explanatory message is used to frame the exception as "feature degrades gracefully": `issue_manager.py:1520-1521` (already cited), `sync.py:155-156`.
  - `logger.warning(...)` (often with `exc_info=True`) is the dominant convention elsewhere in the codebase for exceptions representing a real operational failure the user should notice — not used at any `gather_all_issue_ids()` site today: `git_operations.py:215-217`, `parallel/orchestrator.py:426-428,461-463,543-545,699-701,732-735`, `events.py:114-115,131-133,137-139`.
  - `sprint.py:378` (the already-fixed call site) additionally carries a `# pragma: no cover - defensive, mirrors issue_parser` comment marking the except-block as untested-by-design.
  No example in the codebase justifies choosing one convention over another for this exception specifically — the split is pre-existing, not something this bug's fix is expected to resolve.
- **Precedent for consolidating a duplicated try/except into one shared helper (Q2)**: `git_mv_with_fallback()` (`issue_lifecycle.py:1289-1328+`) is a prior instance of pulling a repeated rename-with-fallback try/except out of multiple call sites (`cli/issues/prioritize.py:117,143`, `cli/issues/normalize.py:444,465`, `issue_lifecycle.py:1372`) into one module-level function; its docstring names the callers that share it and the tracking issues (ENH-2944/ENH-2953). A related but distinct precedent, `find_issues_for_graph()` (`issue_parser.py:2156-2176`, called from `issue_manager.py:1513`), consolidates not a try/except but the correct-input-set preamble for `DependencyGraph` construction across callers, and its docstring explicitly documents the defect class (BUG-2897) the consolidation exists to prevent. Both precedents are module-level (not private/local) functions with a docstring naming their shared callers.
- **Idiom for testing a forced exception path via mock/patch (Q3)**: the two tests already cited in this issue (`test_issue_manager.py:613-626`, `test_issue_parser.py:1352-1394`) are integration tests against real files, not exception-mocking tests — no test in the codebase currently forces `gather_all_issue_ids()` itself to raise. Two mocking idioms coexist for forcing exceptions generally: (a) `unittest.mock.patch(..., side_effect=SomeError("msg"))` as a context manager (`test_issue_manager.py:3818-3821,4497-4500,5100`), and (b) `monkeypatch.setattr(target_string, named_raising_function)` where the raising function is defined locally in the test (`test_sprint.py:735-741,771-777,807-813`). Both target the function *as imported into the consuming module's namespace* (e.g. `little_loops.issue_manager.process_issue_inplace`), matching how `gather_all_issue_ids` is imported locally inside each function body at its various call sites. Separately, `gather_all_issue_ids` is already mocked for a *returned empty set* (not a raised exception) at `test_cli_sprint.py:864,1122`, patched at its defining module path (`little_loops.dependency_mapper.gather_all_issue_ids`) rather than each call site's local-import path.

### Files to Modify
- None required to reproduce this issue's own repro — the sprint.py path described in Steps to Reproduce is already fixed and regression-tested (see Root Cause). Remaining candidates, if the exception-fallback branches are judged in scope:
  - `scripts/little_loops/issue_manager.py:1509-1521` — `AutoManager.__init__`, the `except Exception: self.logger.debug(...)` branch leaving `all_known_ids = None`.
  - `scripts/little_loops/issue_parser.py:2118-2126` — `find_issues()`'s `skip_blocked` branch, the `except Exception: pass` leaving `all_known_ids = None`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/run.py` — calls `SprintManager.load_or_resolve()` (the already-fixed path) before wave scheduling.
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()` (lines 55-152) is the sole warning-emission point for `blocked_by` (line 113), `blocks` (line 130), and `depends_on` (line 145); all three call sites feed it `all_known_ids`.
- Seven other call sites already derive `all_known_ids` correctly via `gather_all_issue_ids()` and are unaffected: `cli/deps.py`, `cli/sprint/run.py`, `cli/sprint/manage.py`, `cli/sprint/show.py`, `cli/sprint/edit.py`, `cli/issues/link.py`, `cli/issues/sequence.py`.

### Dependent Files (Callers/Importers) — Corrections

_Wiring pass added by `/ll:wire-issue` — 2026-08-03:_

- **The "already correct and unaffected" claim above is wrong for 4 of the 7 named sites.** Confirmed by direct read (not just grep): `cli/sprint/run.py:499-502`, `cli/sprint/show.py:183-187`, `cli/sprint/manage.py:92-96`, and `cli/sprint/edit.py:105-114` each call `gather_all_issue_ids()` with **no try/except at all** around the call — an exception there is unhandled and crashes the CLI command outright (`ll-sprint run`/`show`/`manage`/`edit --revalidate`), a strictly worse failure mode than the `active_ids_set`/`None` degrade this issue discusses elsewhere. `cli/deps.py:385` has the same gap — the nearby `try/except` at lines 379-384 guards only the `BRConfig` construction, not the `gather_all_issue_ids()` call itself, so it's unguarded too.
- Only `cli/issues/link.py:223-228`, `cli/issues/sequence.py:74-81`, `cli/issues/next_issue.py:67-74`, and `cli/issues/next_issues.py:57-64` actually wrap the call in `try/except Exception: pass`/`all_known_ids = None` and were correctly described as protected — these 4 (not 7) are the ones genuinely unaffected by the crash risk.
- If this issue's scope is widened to harden all `all_known_ids` construction sites for consistency (see Proposed Solution), these 5 unguarded sites (`deps.py`, `sprint/run.py`, `sprint/show.py`, `sprint/manage.py`, `sprint/edit.py`) are the highest-severity gap in the family — an unhandled crash, not a log-noise false positive — and arguably warrant a follow-on issue of their own rather than folding into this P4 cosmetic bug, since "gather_all_issue_ids() raises and takes the CLI down with it" is a different failure class than "spurious unknown-issue warning."

### Conventions in Force
- Every `all_known_ids` call site follows the same three-line try/except shape around `gather_all_issue_ids(issues_dir, config=config)`, but the three fallback bodies already disagree: `sprint.py:378` (`all_known_ids = active_ids_set`, `# pragma: no cover - defensive, mirrors issue_parser`), `issue_manager.py:1520-1521` (`None` + `self.logger.debug(...)`), `issue_parser.py:2124-2126` (`None` + bare `pass`).
- `gather_all_issue_ids()` is deliberately filename-only and non-recursive by design, not by oversight — its own docstring (`dependency_mapper/operations.py:365-368`) states done/deferred issues stay in type dirs so a flat per-type-dir scan finds all known IDs; a prior issue, `BUG-2733` (done), considered widening it to also scan legacy `completed_dir`/`deferred_dir` and explicitly chose not to, naming this same sprint-ordering consumer as an acknowledged, deferred gap.
- Two competing "scan every issue dir" shapes coexist elsewhere with no consolidation: a per-category `dirs_to_scan` list of non-recursive `.glob()` calls (`issue_parser.py:get_next_issue_number()`, ~1217-1266) vs. a single `issues_dir.rglob("*.md")` (`recursive_finalize.py:_find_issue_file()`, 39-59).

### Tests
- `scripts/tests/test_sprint.py::TestSprintManagerLoadOrResolve` — `test_load_or_resolve_epic_depends_on_done_issue_no_warning` (2512-2549) and `test_load_or_resolve_epic_depends_on_dangling_issue_still_warns` (2551-2570) already reproduce and guard this issue's exact repro scenario; both PASS on `main` today.
- `scripts/tests/test_dependency_graph.py` — `test_depends_on_unknown_target_warns` (208-215) and `test_known_but_absent_target_no_warning` (217-224) cover the `all_known_ids` suppression contract directly.
- `scripts/tests/test_dependency_mapper.py::TestGatherAllIssueIds` (678-769), including `test_scans_type_dirs_including_done_issues` (741-769), covers `gather_all_issue_ids()` finding done-status issues in flat type dirs.
- No test forces `gather_all_issue_ids()` to raise at any of the three call sites — the `issue_manager.py` and `issue_parser.py` exception-fallback branches are untested.

### Tests — Gap Confirmation and Templates

_Wiring pass added by `/ll:wire-issue` — 2026-08-03:_

- Confirmed: no test anywhere in `scripts/tests/` monkeypatches/mocks `gather_all_issue_ids` to force the exception path at any of the three try/except call sites (`sprint.py`, `issue_manager.py`, `issue_parser.py`) — including the already-fixed `sprint.py` site, which also has no exception-path test despite its happy-path tests existing. No test asserts on the `self.logger.debug("Dependency mapping unavailable — skipping")` string (`issue_manager.py:1521`) or on `issue_parser.py`'s silent `except Exception: pass` — so a fix has free rein on post-exception behavior at both remaining sites.
- New test template for `AutoManager.__init__` (`issue_manager.py:1509-1521`): model after `TestDependencyAwareSequencing::test_dependency_graph_built_on_init` (`scripts/tests/test_issue_manager.py:613-626`) and its fixture `temp_project_with_deps` (`:568-611`); patch `little_loops.dependency_mapper.gather_all_issue_ids` to raise, construct `AutoManager` the same way, assert it doesn't crash and inspect the resulting `all_known_ids`/warning behavior.
- New test template for `find_issues(skip_blocked=True)` (`issue_parser.py:2118-2126`): model after `test_find_issues_skip_blocked_terminal_blocker_unblocks` / `test_find_issues_skip_blocked_deferred_blocker_still_blocks` (`scripts/tests/test_issue_parser.py:1352-1394`), same patch approach.
- Existing mock precedent for the pattern to follow: `scripts/tests/test_cli_sprint.py:864,1122` already does `patch("little_loops.dependency_mapper.gather_all_issue_ids", return_value=set())` — but only exercises a *returned empty set*, not a raised exception, and only for the `sprint.py` path.
- New test needed for the 5 newly-confirmed unguarded call sites (`cli/deps.py`, `cli/sprint/{run,show,manage,edit}.py`): a test that forces `gather_all_issue_ids` to raise and asserts the CLI command currently crashes (documenting the gap) — or, if those sites are hardened as part of this issue's scope, asserts graceful degradation instead.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

### Signatures
- `gather_all_issue_ids(issues_dir: Path, config: BRConfig | None = None) -> set[str]` — unchanged surface across all call sites, defined at `dependency_mapper/operations.py:362`.
- `DependencyGraph.from_issues(cls, issues: list[IssueInfo], completed_ids: set[str] | None = None, all_known_ids: set[str] | None = None) -> DependencyGraph` — defined at `dependency_graph.py:56-61`; `all_known_ids=None` means "warn on anything absent from the graph" (original behavior), `all_known_ids={ids}` means "only warn if absent from that set too."

### Call Path
`ll-sprint run <epic>` (`cli/sprint/run.py`) -> `SprintManager.load_or_resolve()` (`sprint.py`) -> `gather_all_issue_ids(issues_dir, config=self.config)` (already fixed, `sprint.py:367-371`) -> `DependencyGraph.from_issues(child_infos, all_known_ids=...)` -> three warn-guard branches (`dependency_graph.py:111` `blocked_by`, `:129` `blocks`, `:143` `depends_on`), each `if all_known_ids is None or <id> not in all_known_ids: logger.warning(...)`.

The two remaining call sites share the identical shape but degrade to `None` (not a fallback set) on exception: `AutoManager.__init__` (`issue_manager.py:1509-1521`) and `find_issues()`'s `skip_blocked` branch (`issue_parser.py:2118-2126`).

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included if this issue's scope is widened beyond the already-fixed `sprint.py` repro:_

- Decide, then fix consistently: `issue_manager.py:1509-1521` (`AutoManager.__init__`) and `issue_parser.py:2118-2126` (`find_issues`'s `skip_blocked` branch) — either log the swallowed exception or fall back to a `gather_all_issue_ids`-derived set instead of `None`.
- Add a test forcing the exception path for `AutoManager.__init__`, modeled on `test_dependency_graph_built_on_init` (`scripts/tests/test_issue_manager.py:613-626`) + `temp_project_with_deps` fixture (`:568-611`), patching `little_loops.dependency_mapper.gather_all_issue_ids`.
- Add a test forcing the exception path for `find_issues(skip_blocked=True)`, modeled on `scripts/tests/test_issue_parser.py:1352-1394`.
- Investigate and likely open a separate follow-on issue for the 5 confirmed **unguarded** call sites — `cli/deps.py:385`, `cli/sprint/run.py:499-502`, `cli/sprint/show.py:183-187`, `cli/sprint/manage.py:92-96`, `cli/sprint/edit.py:105-114` — which have no try/except around `gather_all_issue_ids()` at all and crash outright on exception, a different (and more severe) failure class than this issue's log-noise symptom.

## Impact

- **Priority**: P4 - Cosmetic/log-noise only in this occurrence; the actual
  dependency resolution worked correctly. Worth fixing so real "unknown
  issue" warnings (e.g. genuine typos) aren't drowned out by false
  positives from this same code path.
- **Effort**: Small - likely a scoping fix to `all_known_ids` construction
  or a `glob` -> `rglob` change, pending confirmation of the actual cause.
- **Risk**: Low - narrow, well-isolated code path.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-03 | Priority: P4

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-03_

**Readiness Score**: 75/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- The repro described in Summary/Steps to Reproduce is already fixed on the `sprint.py` path by commit `15152136` (closing `BUG-3024`), with two passing regression tests. What remains open is a scope decision, not a bug fix: whether to also harden the `issue_manager.py:1509-1521` and `issue_parser.py:2118-2126` exception-fallback branches for consistency, and whether to split the 5 newly-confirmed **unguarded** call sites (`cli/deps.py`, `cli/sprint/{run,show,manage,edit}.py` — no try/except at all, crash outright on exception) into a separate, higher-severity follow-on issue.
- Architecture compliance is muted (not a clean match) because the `/ll:wire-issue` and `/ll:refine-issue` research found three *disagreeing* existing fallback conventions (`active_ids_set`, `None`+`debug`, `None`+bare `pass`) with no single precedent to copy — the fix requires picking one, not following an established pattern.
- Ambiguity score is low (10/25) for the same scope-decision reason — implementation needs a judgment call before code is written.

### Outcome Risk Factors
- Scope ambiguity is the dominant risk: whichever branch is chosen (harden the 2 sites only vs. also split off the 5-site crash-risk issue as its own P-something bug) changes both the diff size and the test list. Resolving this via `/ll:decide-issue BUG-3027` (or explicitly narrowing "Implementation Steps" to one option) before coding would raise both scores.
- No test currently forces `gather_all_issue_ids()` to raise at any of the three try/except call sites (including the already-fixed `sprint.py` one) — the exception-path test templates are specified in "Tests — Gap Confirmation and Templates" but not yet written, so coverage of the actual fix branch is currently theoretical.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-03
- **Reason**: Issue too large for single session

### Decomposed Into
- BUG-3028: Harden `all_known_ids` exception-fallback branches in `AutoManager.__init__` and `find_issues(skip_blocked=True)`
- BUG-3029: Audit and fix unguarded `gather_all_issue_ids()` call sites that crash CLI commands on exception

## Session Log
- `/ll:issue-size-review` - 2026-08-03T18:23:43 - `13ce9106-a2bc-4289-afb9-7b03c8d5dfa8.jsonl`
- `/ll:confidence-check` - 2026-08-03T18:21:47 - `c23290d0-ae3c-48ce-b151-facca0d4b141.jsonl`
- `/ll:refine-issue` - 2026-08-03T18:19:21 - `e310f3f5-c184-45e3-9148-50a16ba13801.jsonl`
- `/ll:confidence-check` - 2026-08-03T18:15:29 - `915a7be1-8230-4e10-8de9-f4e9afc6cf04.jsonl`
- `/ll:wire-issue` - 2026-08-03T18:13:07 - `ad185e4a-4427-43f2-a333-c5fdf422f1f7.jsonl`
- `/ll:refine-issue` - 2026-08-03T18:03:49 - `4c89f571-15ab-416e-ac14-db34fc42c7af.jsonl`
- `/ll:capture-issue` - 2026-08-03T17:16:22 - `4ad49473-6f8b-44cc-afa6-91e971b86c04.jsonl`
