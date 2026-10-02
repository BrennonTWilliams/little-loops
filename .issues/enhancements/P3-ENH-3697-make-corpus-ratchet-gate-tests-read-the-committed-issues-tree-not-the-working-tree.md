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

## Summary

Make the two repo-wide corpus-ratchet tests read the **committed** `.issues/` tree (`HEAD` / `git ls-files`) instead of the live working tree, so in-flight autodev edits to `.issues/` cannot turn them red. Supersedes ENH-3692 (baseline-aware gate), which was closed won't-do after review of EPIC-3694.

## Current Behavior

`scripts/tests/test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo` (sweeps every active issue via `check_format_gaps` over the real `.issues/` dir) and `scripts/tests/test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` (`ll-verify-evidence --all` over the repo corpus) both read the working tree. autodev mutates `.issues/` while it runs (BUG-3688's `<ID>.base-dirty` listed ~20 uncommitted `.issues` files). A gate run during that window sees transient drift and reports red even though `main` is clean: on BUG-3688 both failed in the gate, but both pass on `main` with `-n 0` (verified 2026-10-02).

## Expected Behavior

Both tests evaluate the committed tree only (e.g. materialize `HEAD:.issues/` into a tmp dir via `git archive` / `git ls-tree` + `git show`, or enumerate via `git ls-files` and read blobs from `HEAD`), so uncommitted `.issues/` edits cannot affect the verdict. Drift that really landed in a commit still fails them.

## Motivation

A false `quality_failed` verdict blocks an otherwise-correct implementation and is not re-gated on rerun (see BUG-3689). This removes the "2 pre-existing failures" class at its source instead of building baseline-aware gating (ENH-3692, closed).

## Proposed Solution

- Add a small helper (shared by both tests) that exports the committed `.issues/` (and whatever `check_format_gaps` / `ll-verify-evidence --all` need beside it) to a tmp dir and points the sweep at it. Precedent: `ENH-3639` pins a different corpus test to a frozen fixture; follow its approach where compatible.
- Keep the evidence baseline (`.ll/evidence-baseline.json`) comparison unchanged.
- Skip gracefully when not a git checkout / shallow clone (existing `_fail_if_shallow_checkout` behavior).

## Impact

- **Priority**: P3 - removes a transient false-failure class from the quality gate; `--context quality_gate=false` works around it meanwhile
- **Effort**: Small - one shared helper used by two tests
- **Risk**: Low - test-only; committed-tree reads can miss uncommitted drift by design
- **Breaking Change**: No

## Program Design

### Types

- `CommittedIssuesTree` — dataclass: `root: Path` (tmp dir or blob-reader root holding `HEAD:.issues/`), `head_sha: str`

### Signatures

- `committed_issues_tree(repo_root: Path) -> CommittedIssuesTree` — exports/reads `HEAD:.issues/` without touching the working tree; new helper in `scripts/tests/conftest.py`
- `test_no_prose_dependency_drift_in_repo() -> None` — `scripts/tests/test_prose_dep_sweep_gate.py`, sweeps the committed tree
- `test_no_new_unverifiable_evidence(gate_cli: str) -> None` — `TestRepoGate` in `scripts/tests/test_verify_evidence.py`, runs `ll-verify-evidence --all` against the committed tree

### Call Path

`test_no_prose_dependency_drift_in_repo` -> `committed_issues_tree` -> `check_format_gaps`; `test_no_new_unverifiable_evidence` -> `committed_issues_tree` -> `ll-verify-evidence --all`

## Acceptance Criteria

- With uncommitted edits to `.issues/*.md` that introduce prose-dependency drift or an unverifiable quote, both tests still pass.
- The same drift committed to `HEAD` makes them fail.
- Both tests still pass on a clean `main` under `python -m pytest -n 0` and complete within their existing timeouts.
- No new third-party dependencies.

## Risks

- Reading `HEAD` misses drift that autodev leaves uncommitted in its worktree unless autodev commits issue edits before the gate; the committed-tree gate is intentionally the authority.
- Materializing the corpus adds file-creation churn (cf. launchservicesd beachballs) — prefer reading blobs via `git show`/`git cat-file --batch` over writing thousands of files.

## Scope Boundaries

Out of scope: baseline-aware gating of `code-run-gate` (ENH-3692, cancelled); env/hermeticity fixes (BUG-3689).

## Status

**Open** | Created: 2026-10-02 | Priority: P3
