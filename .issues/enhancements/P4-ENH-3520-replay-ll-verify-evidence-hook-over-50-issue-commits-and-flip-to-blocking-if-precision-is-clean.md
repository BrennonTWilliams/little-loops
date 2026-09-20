---
id: ENH-3520
type: ENH
title: Replay ll-verify-evidence hook over 50 issue commits and flip to blocking if
  precision is clean
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T23:24:10Z'
labels:
- enhancement
- verify-evidence
- pre-commit
relates_to:
- BUG-3282
- ENH-3518
blocked_by:
- ENH-3518
parent: ENH-3515
---

# ENH-3520: Replay ll-verify-evidence hook over 50 issue commits and flip to blocking if precision is clean

## Summary

Decide with evidence whether the warn-only `ll-verify-evidence` pre-commit hook can become blocking: replay it over the 50 most recent `.issues/` commits in historical isolation, classify every finding, and drop `|| true` only if there are zero false positives. Split out of ENH-3515.

## Current Behavior

The hook is warn-only (BUG-3282) because it fires inside ll-auto / ll-parallel / refine-loop commits, where a precision miss would block a commit mid-run. The BUG-3282 comment says to flip "once the whole-corpus precision smoke test has a stable ceiling", but `TestWholeCorpusPrecision` covers extraction only — no measurement of hook precision on real staged changes exists.

## Expected Behavior

A retained replay report either justifies blocking (hook flipped, comment and display name updated) or records why it stays warn-only.

## Motivation

The BUG-3282 comment defers blocking to a precision signal that does not exist, so the hook would otherwise stay warn-only indefinitely. A one-time, reproducible measurement turns that into a decision. Until then automation is covered at write time by the refine-time check and at suite time by the repo gate.

## Proposed Solution

- **Reproducible replay**: freeze and record the verifier revision and the 50 most recent commits touching `.issues/` at the measurement cutoff. For each commit, use an isolated repository with its parent as HEAD and the commit's tree staged and checked out; pass explicit changed issue filenames to `ll-verify-evidence --added-only`. Define first-parent handling for merges and deletion/rename handling. Do not mutate the developer's index or working tree. Simply checking out a commit produces no staged additions and is not a replay.
- **Historical isolation**: the matcher uses `git log --all`. Restrict replay refs to history available at the parent, with the target commit's tree supplying the staged/working content; exclude later revisions and unrelated refs. A normal worktree sharing current refs is insufficient. Isolate verdict caches per replay repository so cached results do not leak across historical states.
- **Evidence and coverage**: retain a replay report with cutoff, commit IDs, verifier revision, setup/reproduction instructions, changed files/added lines, eligible candidate counts, findings and their manual true/false-positive classifications, and execution errors. Confirm nonzero eligible coverage and use a deliberately invalid staged quote as a positive control. Zero findings on an empty or broken replay is not precision evidence. Store the report under `postmortems/` and cite its path, date, and summary in the hook comment.
- **Conditional flip to blocking** (drop `|| true`): only after the complete, valid 50-commit replay has zero false positives and its coverage/control checks pass. Otherwise retain warn-only + verbose and record the false positives or why the measurement was inconclusive. If blocking is enabled, also remove "(warn-only)" from the hook's display name.

## Integration Map

### Files to Modify
- `.pre-commit-config.yaml` — conditionally drop `|| true`; rewrite the BUG-3282 comment with the replay date, result and report path; display name
- `postmortems/` — the replay report (gitignored, source-repo-only)
- `docs/reference/CLI.md` — `ll-verify-evidence` entry, only if the hook flips to blocking

### Tests
- ENH-3518's new pre-commit gate test module (`test_verify_evidence_pre_commit_gate`, created by that issue) derives the expected exit status from the configured policy; after a flip it must assert a non-zero exit for the invalid staged quote with no test rewrite beyond that.

## Implementation Steps

1. Build the isolated replay harness (parent as HEAD, commit tree staged, refs restricted to the parent's history, per-replay verdict cache); validate it with the positive control.
2. Run the 50-commit replay; classify every finding; write the report under `postmortems/`.
3. Flip to blocking only if all conditions pass; otherwise keep warn-only. Update comment and display name consistently; update `docs/reference/CLI.md` only on a flip.
4. Run the hook gate tests and the full suite.

## Impact

- **Priority**: P4 — the suite gate remains the backstop either way.
- **Effort**: Moderate-Large — isolated historical replay plus manual classification.
- **Risk**: Low if gated as specified; a blocking hook with imperfect precision could stall automation commits.

## Parent Issue

Decomposed from ENH-3515: Shift-left evidence verification to refine-time and make the pre-commit hook visible

## Program Design

### Types

- None — no new code shapes; the replay harness is throwaway tooling recorded in the report.

### Signatures

- `main_verify_evidence(argv: list[str] | None = None) -> int` — invoked unchanged with `--added-only`
- `staged_added_lines(base_dir: Path, paths: list[Path]) -> dict[str, set[int]] | None` — why the replay must stage the commit's tree (a plain checkout yields no added lines)

### Call Path

replay harness -> isolated repo (parent as HEAD, commit tree staged) -> `main_verify_evidence` `--added-only` -> `staged_added_lines` -> findings -> manual classification -> report -> conditional `.pre-commit-config.yaml` edit

## Acceptance Criteria

- [ ] A replay report exists under `postmortems/` with the cutoff, the 50 commit IDs, verifier revision, reproduction steps, eligible candidate counts, per-finding manual classification, and execution errors.
- [ ] The replay used staged changes in isolated repositories with historically restricted refs and per-replay verdict caches; it shows nonzero eligible coverage and a working positive control.
- [ ] Blocking is enabled only if the replay is complete and has zero manually classified false positives; otherwise the hook stays warn-only and the reason is recorded.
- [ ] The hook comment records the date, result, and report path; display name and entry agree with the behavior; the hook gate tests pass under the resulting policy.

## Scope Boundaries

- **Non-goal: surfacing warn-only hook findings in ll-auto / ll-parallel run summaries.** Capture a follow-up only if the hook stays warn-only *and* automation-written findings keep reaching the suite gate.
- **Non-goal: changing verifier matching rules** to make the replay pass.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-19 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-09-20T00:10:58 - `d0eb6446-04cf-4c6e-ada1-f1ab3056d581.jsonl`
