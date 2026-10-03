---
id: ENH-3697
type: ENH
title: Make corpus-ratchet gate tests read the committed .issues tree, not the working
  tree
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:48:04Z'
parent: EPIC-3694
supersedes:
- ENH-3692
relates_to:
- BUG-3689
- ENH-3639
---

# ENH-3697: Make corpus-ratchet gate tests read the committed .issues tree, not the working tree

## Decision (2026-10-03, EPIC-3694 children review)

- **Premise verified.** The pre-existing-dirt file `<ID>.base-dirty` is written by `autodev.yaml` `implement_current` *before* `ll-auto` runs, and `route_quality_gate` subtracts it from the changed set as "the operator's WIP". It records dirt already in the shared checkout when autodev started (concurrent sessions / operator edits), not autodev's own mutation. So the ~20 uncommitted `.issues` files seen on BUG-3688 were someone else's in-flight work, and the false red is a shared-checkout isolation problem, not an autodev write problem.
- **Clean-checkout `code-run-gate`: rejected.** `run_test` evaluates the implementation, which may still be uncommitted when the gate runs (`route_quality_gate` gates the committed diff *plus* uncommitted changes), so a HEAD checkout would test none of the uncommitted deliverable. It would also create thousands of files per gate run (launchservicesd churn) and re-open the editable-install shadowing hazard (BUG-2629), where the worktree imports the main tree's package.
- **Chosen: narrowed HEAD-read of the `.issues` corpus, test-only.** The implementation stays tested from the working tree; only the repo-wide issue-corpus ratchet reads committed text.
- **Coverage tradeoff accepted.** `run_quality_gate` runs after `ll-auto --only` returns, so close-out `.issues/` edits that `ll-auto` committed are visible at HEAD. Drift left *uncommitted* is not seen by the gate by design; it still surfaces for contributors via the working-tree default.
- **Scope.** Only `test_no_prose_dependency_drift_in_repo` changes. `TestRepoGate::test_no_new_unverifiable_evidence` is deferred (it walks git history and loads `.ll/evidence-baseline.json` relative to the root); if it is later needed, give `ll-verify-evidence` an `--at-ref HEAD` blob-read mode rather than exporting files.
- **Class, not instance.** Other tests are dirty-tree sensitive too (host-mirror staleness, docs-audience gate, README loop count). This issue fixes the one repo-wide corpus ratchet; it does not claim to close the class.

## Summary

Make the repo-wide prose-dependency corpus ratchet read the **committed** `.issues/` tree (`HEAD`) instead of the live working tree, only when run inside `code-run-gate`, so another session's uncommitted `.issues/` edits cannot turn the quality gate red. Supersedes ENH-3692 (baseline-aware gate), which was closed won't-do after review of EPIC-3694.

## Current Behavior

`scripts/tests/test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo` sweeps every active issue via `check_format_gaps` over the real `.issues/` dir, so it reads the working tree. `scripts/tests/test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` (`ll-verify-evidence --all` over the repo corpus) does the same. When the shared checkout carries uncommitted `.issues/` edits (BUG-3688's `<ID>.base-dirty` listed ~20), a gate run sees that drift and reports red even though `main` is clean: on BUG-3688 both failed in the gate, but both pass on `main` with `-n 0` (verified 2026-10-02).

## Expected Behavior

Inside `code-run-gate`, `test_no_prose_dependency_drift_in_repo` evaluates the committed tree only, so uncommitted `.issues/` edits cannot affect the verdict, and drift that really landed in a commit still fails it. Outside the gate (contributors, pre-commit) behavior is unchanged: the working tree is swept.

## Motivation

A false `quality_failed` verdict blocks an otherwise-correct implementation and is not re-gated on rerun (see BUG-3689). This removes the "pre-existing failure" class for the prose-dependency ratchet at its source instead of building baseline-aware gating (ENH-3692, closed).

## Proposed Solution

- Add a new test-support module, head_corpus.py, in the tests directory: list tracked issue files with `git ls-tree -r HEAD --name-only` over each category dir, read their blobs in one `git cat-file --batch` pass (no tmp export, no file creation), and expose them through two duck-typed adapters: `HeadIssueParser` (an `IssueParser` subclass overriding `_read_content`) and `BlobPath` (supplies `name`, `read_text`, `read_bytes` — the only members `check_format_gaps` uses on its path argument).
- In `test_no_prose_dependency_drift_in_repo`, when `LL_CORPUS_GATE_AT_HEAD` is truthy, build `issue_statuses` and the active-issue list from `HeadIssueParser` over the HEAD blobs instead of `find_issues`; otherwise keep the current code path byte-for-byte.
- In `code-run-gate.yaml`'s test-run state, `export LL_CORPUS_GATE_AT_HEAD=1` immediately after the existing `unset LL_PYTHON COLUMNS LINES` line (BUG-3689 scrubs inherited env first, so the flag must be set after that line). Explicit assignments inside `test_cmd` still win.
- `check_format_gaps` is called today without `ref_index`/`project_root`, so tracked-file and line-bound checks already fail open; HEAD mode does not change that.
- Not a git checkout / shallow clone / no `HEAD`: fall back to the working-tree path rather than skip.

## Integration Map

### Files to Modify
- `scripts/tests/test_prose_dep_sweep_gate.py` - branch on the env flag; HEAD-read path via the new helper
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` - test-run state exports the flag after the env scrub
- `scripts/tests/test_builtin_loops.py` - pin that the oracle's test-run state sets the flag after the scrub line

### New Files
- head_corpus.py (tests dir) - HEAD blob reader, `HeadIssueParser`, `BlobPath`
- test_head_corpus.py (tests dir) - unit tests for the helper

### Similar Patterns
- ENH-3639 pins a different corpus test to a frozen fixture
- `_fail_if_shallow_checkout` in `scripts/tests/test_verify_evidence.py` for the shallow-clone guard shape

### Documentation
- `docs/reference/CONFIGURATION.md` or the code-run-gate section of `docs/guides/LOOPS_REFERENCE.md`: one line noting the oracle sets `LL_CORPUS_GATE_AT_HEAD` for the test run (check which carries the oracle's env notes before editing; keep to the end-user audience rule)

## Implementation Steps

1. Write head_corpus.py and test_head_corpus.py first (red), using a throwaway `git init` repo fixture with a committed issue and an uncommitted drifting one.
2. Wire the flag branch into `test_no_prose_dependency_drift_in_repo`; confirm the default (flag unset) path is unchanged.
3. Add the `export` to `code-run-gate.yaml` and the pin in `test_builtin_loops.py`.
4. Run the affected tests and `ll-loop validate oracles/code-run-gate`; then the full suite.
5. Add the one-line doc note; no mirror regeneration is needed unless `commands/` or `skills/` change.

## Tests

- Flag set, uncommitted `.issues` edit introducing prose-dependency drift: the sweep passes.
- Flag set, the same drift committed: the sweep fails and names the issue.
- Flag unset, uncommitted drift: the sweep fails (contributor behavior preserved).
- `HeadIssueParser` yields statuses identical to `find_issues` on a clean tree (parity on the real repo's HEAD).
- No `HEAD` / not a git repo: falls back to the working-tree path without raising.
- The oracle's test-run action text sets the flag after `unset LL_PYTHON COLUMNS LINES`.

## Impact

- **Priority**: P3 - removes a transient false-failure class from the quality gate; `--context quality_gate=false` works around it meanwhile
- **Effort**: Small - one helper, one test branch, one YAML line
- **Risk**: Low - test-only plus one env export; committed-tree reads can miss uncommitted drift by design
- **Breaking Change**: No

## Program Design

### Types

- `BlobPath` — dataclass: `name: str`, `content: bytes`; duck-types the path argument of `check_format_gaps` (`read_text`, `read_bytes`, `name`)

### Signatures

- `head_issue_blobs(repo_root: Path) -> dict[str, bytes] | None` — reads every tracked issue file at HEAD in one `git cat-file --batch` pass; returns `None` when there is no usable HEAD; new helper in head_corpus.py (tests dir)
- `HeadIssueParser(config: BRConfig, blobs: dict[str, bytes])` — `IssueParser` subclass whose `_read_content` serves HEAD blobs; head_corpus.py (tests dir)
- `test_no_prose_dependency_drift_in_repo() -> None` — sweeps HEAD blobs when `LL_CORPUS_GATE_AT_HEAD` is set, else the working tree; test_prose_dep_sweep_gate.py (tests dir)

### Call Path

`test_no_prose_dependency_drift_in_repo` -> `head_issue_blobs` -> `HeadIssueParser` -> `check_format_gaps`; `code-run-gate` test run -> sets `LL_CORPUS_GATE_AT_HEAD` -> `test_no_prose_dependency_drift_in_repo`

## Acceptance Criteria

- [ ] With the flag set and uncommitted edits to `.issues/*.md` that introduce prose-dependency drift, `test_no_prose_dependency_drift_in_repo` passes.
- [ ] With the flag set, the same drift committed to `HEAD` makes it fail.
- [ ] With the flag unset, behavior is unchanged: uncommitted drift fails the test.
- [ ] `code-run-gate`'s test-run state sets the flag after the env scrub; pinned in `test_builtin_loops.py`.
- [ ] Both paths pass on a clean `main` under `python -m pytest -n 0` within the existing timeouts.
- [ ] No new third-party dependencies and no production-module changes outside `code-run-gate.yaml`.

## Risks

- Reading `HEAD` misses drift left uncommitted; the committed-tree gate is intentionally the authority inside the gate.
- Reading blobs (not exporting files) keeps the gate free of file-creation churn (cf. launchservicesd beachballs).
- An ambient `LL_CORPUS_GATE_AT_HEAD` in a contributor's shell would silently switch their run to HEAD mode; the name is gate-specific and opt-in, and the flag is documented.

## Scope Boundaries

Out of scope: `test_no_new_unverifiable_evidence` (deferred, see Decision); baseline-aware gating of `code-run-gate` (ENH-3692, cancelled); env/hermeticity fixes (BUG-3689); a clean-checkout gate (rejected, see Decision).

## Status

**Open** | Created: 2026-10-02 | Priority: P3
