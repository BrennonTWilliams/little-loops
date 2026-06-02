---
discovered_date: "2026-04-24"
discovered_by: review
completed_at: 2026-04-26T19:19:29Z
decision_needed: false
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Very Large
status: done
---

# ENH-1280: `ll-issues` Atomic Writes via `tempfile` + `os.rename()`

## Summary

`ll-issues` file-writing operations use `pathlib.Path.write_text()` directly. On a crash or signal mid-write, this can leave a partially-written file that looks valid to subsequent readers. Switch to `tempfile.NamedTemporaryFile` + `os.rename()` so every write is atomic from the reader's perspective.

## Current Behavior

`pathlib.Path.write_text()` opens, truncates, and writes in a single call with no atomicity guarantee. A process killed between truncation and write completion leaves a zero-length or partial file at the target path.

## Expected Behavior

All `ll-issues` file writes use write-to-temp + rename:
1. Write content to a `NamedTemporaryFile` in the same directory as the target (same filesystem, so `os.rename()` is atomic)
2. `os.rename(tmp_path, target_path)` — atomic on POSIX

## Motivation

Switching to atomic writes protects against data corruption from process crashes or signals during file writes:
- **Reliability**: Eliminates zero-length or partial files caused by mid-write interrupts
- **Data integrity**: Every write is observable as either old-content or new-content, never a partial state
- **POSIX guarantee**: `os.rename()` is atomic on POSIX filesystems, making this a well-understood and low-risk fix

## Acceptance Criteria

- All `ll-issues` write paths go through the atomic-write helper
- A reader polling the target path never observes a partial file
- Unit test simulates interrupt between open and rename; target either has old content or new content, never partial

## Scope Boundaries

- **In scope**: `ll-issues` CLI write paths only (`scripts/little_loops/cli/issues/`)
- **Out of scope**: Other CLI tools (`ll-auto`, `ll-parallel`, `ll-loop`, etc.) — atomic writes not needed for their output patterns; config file writes outside `ll-issues`; read-only operations

## Integration Map

### Files to Modify

_Note: `scripts/little_loops/cli/issues/` itself contains **no** `write_text()` calls — all writes surface in the two helper modules below, called at dispatch time._

- `scripts/little_loops/session_log.py:128` — `issue_path.write_text(content)` in `append_session_log_entry()`; called by the `append-log` sub-command
- `scripts/little_loops/issue_lifecycle.py:898` — `original_path.write_text(content, encoding="utf-8")` in `skip_issue()` (git-mv timed out / failed path)
- `scripts/little_loops/issue_lifecycle.py:901` — `new_path.write_text(content, encoding="utf-8")` in `skip_issue()` (git-mv succeeded path)
- `scripts/little_loops/issue_lifecycle.py:904` — `original_path.write_text(content, encoding="utf-8")` in `skip_issue()` (file not git-tracked path)
- `scripts/tests/test_ll_issues_atomic_write.py` — new test file for atomic write verification (does not exist yet)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/append_log.py:26` — `cmd_append_log()` calls `append_session_log_entry()` in `session_log.py`
- `scripts/little_loops/cli/issues/skip.py:59` — `cmd_skip()` calls `skip_issue()` in `issue_lifecycle.py`
- `scripts/little_loops/cli/issues/__init__.py:469,478` — dispatches to `append-log` and `skip` sub-commands

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/orchestrator.py:1261` — calls `append_session_log_entry()` after issue completion (no signature change, no update required) [Agent 1 finding]
- `scripts/little_loops/issue_lifecycle.py:714` — `complete_issue_lifecycle()` also calls `append_session_log_entry()` (separate from the `skip_issue()` write_text call sites; no update required) [Agent 1 finding]

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

The codebase convention is `tempfile.mkstemp + os.replace` (not `NamedTemporaryFile + os.rename`):

- `scripts/little_loops/state.py:145-152` — canonical inline pattern with `os.unlink` cleanup on failure
- `scripts/little_loops/fsm/persistence.py:225-232` — same pattern in FSM state saves
- `scripts/little_loops/fsm/rate_limit_circuit.py:121-134` — named private helper `_write_atomic()` with `FileNotFoundError` guard in cleanup; closest model for a shared helper function
- `scripts/little_loops/parallel/orchestrator.py:605-612` — same inline pattern

No shared `file_utils.py` or `io_utils.py` exists; a new `atomic_write()` helper will need a home (e.g., a new `scripts/little_loops/file_utils.py`, or added to `scripts/little_loops/session_log.py` as a module-level function).

### Tests
- `scripts/tests/test_ll_issues_atomic_write.py` — new test file for atomic write verification (does not exist yet)
- `scripts/tests/test_issues_cli.py:2273` — `TestIssuesAppendLog.test_append_log_writes_entry` at line 2276 (existing; extend to assert `os.replace` is called)
- `scripts/tests/test_issues_cli.py:2830` — `TestIssuesSkip` (existing; extend to assert no `.tmp` orphans)
- `scripts/tests/test_state.py:557-620` — model test structure after this (covers: `os.replace` called once, no orphaned `.tmp` files, original preserved on rename failure)
- `scripts/tests/test_rate_limit_circuit.py:134-168` — model concurrency test after this (concurrent reader/writer; reader never sees partial file)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_log.py:56-151` — `TestAppendSessionLogEntry` class: **UPDATE** — directly tests `append_session_log_entry()` on real files; extend with `os.replace` call capture and no-`.tmp`-orphan assertion modeled after `test_state.py:557-620` [Agent 1 + 3 finding]
- `scripts/tests/test_refine_status.py:1273` — **UPDATE (minor)** — calls `append_session_log_entry()` directly on a real `tmp_path` file in test setup; add `.tmp` orphan guard [Agent 3 finding]
- `scripts/tests/test_issue_lifecycle.py:719` — **WATCH / RISK** — patches `Path.write_text` globally via `patch.object(Path, "write_text", side_effect=PermissionError(...))` for `create_issue_from_failure()` test; safe in this issue's scope (out-of-scope function), but if `atomic_write` is later applied to `create_issue_from_failure`, this mock must migrate to target `os.replace` instead [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue` — conditional on placement decision in Step 1:_
- `docs/reference/API.md:25-58` — **IF `file_utils.py` is created**: add module table row for `little_loops.file_utils` [Agent 2 finding]
- `docs/ARCHITECTURE.md:230-250` — **IF `file_utils.py` is created**: add `file_utils.py` to the `scripts/little_loops/` file tree listing [Agent 2 finding]
- `CONTRIBUTING.md:200-228` — **IF `file_utils.py` is created**: add `file_utils.py` to file tree listing [Agent 2 finding]
- _No documentation changes needed if `atomic_write()` is placed in `session_log.py` instead_ [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Implement `atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None` helper using `tempfile.mkstemp + os.replace` (matching codebase convention — see `state.py:145-152`); place it in a new `scripts/little_loops/file_utils.py` or at the top of `session_log.py`
2. Replace `issue_path.write_text(content)` at `session_log.py:128` with `atomic_write(issue_path, content)`
3. Replace the three `write_text()` calls in `issue_lifecycle.py:898`, `901`, `904` (`skip_issue()`) with `atomic_write(path, content, encoding="utf-8")`
4. Add test class to `scripts/tests/test_ll_issues_atomic_write.py` modeled on `test_state.py:557-620`:
   - Assert `os.replace` is called exactly once per write
   - Assert no orphaned `.tmp` files remain after success
   - Assert original file is preserved when `os.replace` raises `OSError`
5. Run `python -m pytest scripts/tests/test_ll_issues_atomic_write.py scripts/tests/test_issues_cli.py -v` to verify no regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_session_log.py` — extend `TestAppendSessionLogEntry` (lines 56–151) with `os.replace` call capture and no-`.tmp`-orphan assertion (modeled after `test_state.py:557-590`)
7. Update `scripts/tests/test_refine_status.py:1273` — add `.tmp` orphan guard after the direct `append_session_log_entry()` call (minor, one-liner)
8. If `file_utils.py` is created in Step 1: add module table row to `docs/reference/API.md:25-58` and file tree entries to `docs/ARCHITECTURE.md:230-250` and `CONTRIBUTING.md:200-228`
9. Expand Step 5 test run to: `python -m pytest scripts/tests/test_session_log.py scripts/tests/test_ll_issues_atomic_write.py scripts/tests/test_issues_cli.py -v`

## Impact

- **Priority**: P5 — Defensive hygiene; partial writes are rare in practice and `ll-issues` operations are short
- **Effort**: Trivial — a one-function refactor across a small number of call sites
- **Risk**: Very low
- **Breaking Change**: No

## Related Key Documentation

- **ENH-1198** — closed invalid; this issue extracted from it
- **ENH-1279** — `ll-issues validate-catalog` (companion issue)

## Labels

`cli`, `ll-issues`, `reliability`

---

**Open** | Created: 2026-04-24 | Priority: P5


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-26_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **File count breadth**: 6 mandatory files (6-10 complexity band). Each change is 1-3 lines, but coordinating across session_log.py, issue_lifecycle.py, file_utils.py (new), and three test files increases oversight risk. Mitigation: follow the 9-step plan in order; run tests after each pair of call sites is replaced.
- **Unresolved placement decision**: `atomic_write()` helper placement (new `file_utils.py` vs top of `session_log.py`) is still open. Conditional doc updates (API.md, ARCHITECTURE.md, CONTRIBUTING.md) depend on this choice. Decide at the start of Step 1 to avoid re-work.

## Session Log
- `/ll:ready-issue` - 2026-04-26T19:16:40 - `f710fa0b-5103-4227-b6b5-481b229473ec.jsonl`
- `/ll:confidence-check` - 2026-04-26T18:30:00 - `543e902c-e842-4902-bf7b-20373bd4ee5f.jsonl`
- `/ll:wire-issue` - 2026-04-26T18:10:10 - `3a9dffad-1333-4628-a6b0-01a2936c3e81.jsonl`
- `/ll:refine-issue` - 2026-04-26T18:04:54 - `ea84d70c-d9aa-47c1-90e8-7c4dcc625502.jsonl`
- `/ll:format-issue` - 2026-04-26T17:53:29 - `70712d29-8a54-4a5c-99f2-80dc1d4864ed.jsonl`
- `/ll:manage-issue` - 2026-04-26T19:19:29 - `f710fa0b-5103-4227-b6b5-481b229473ec.jsonl`

## Resolution

**Status**: Completed 2026-04-26

**Implementation**:
- Created `scripts/little_loops/file_utils.py` with `atomic_write(path, content, encoding)` helper using `tempfile.mkstemp + os.replace` (matching codebase convention in `state.py`, `fsm/rate_limit_circuit.py`)
- Placed `atomic_write()` in new `file_utils.py` (not `session_log.py`) to keep it reusable
- Replaced `issue_path.write_text(content)` in `session_log.py:append_session_log_entry()`
- Replaced three `write_text()` calls in `issue_lifecycle.py:skip_issue()` (git-mv failed path, git-mv succeeded path, not-tracked path)
- Updated docs: `docs/reference/API.md`, `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`
- New test file: `scripts/tests/test_ll_issues_atomic_write.py` (7 tests)
- Extended `test_session_log.py:TestAppendSessionLogEntry` with 2 atomic write assertions
- Extended `test_refine_status.py` with `.tmp` orphan guard

**Tests**: 81 tests pass (0 failures)
