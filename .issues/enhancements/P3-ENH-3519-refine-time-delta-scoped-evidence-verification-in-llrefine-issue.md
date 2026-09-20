---
id: ENH-3519
type: ENH
title: Refine-time delta-scoped evidence verification in /ll:refine-issue
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T23:24:10Z'
labels:
- enhancement
- verify-evidence
- issue-refinement
relates_to:
- ENH-3283
- BUG-3282
- BUG-3484
- ENH-3518
parent: ENH-3515
---

# ENH-3519: Refine-time delta-scoped evidence verification in /ll:refine-issue

## Summary

`/ll:refine-issue` authors new quoted evidence with no verification, so a fabricated or misattributed quote only surfaces minutes later in the repo-wide pytest gate. Verify at refine time, scoped to the quotes this pass added. Split out of ENH-3515.

## Current Behavior

Only `/ll:capture-issue` verifies quoted spans before writing (ENH-3283). `/ll:refine-issue` authors new quoted evidence (its Codebase Research Findings, plus Root Cause / Current Behavior fills) with no check. `/ll:verify-issues` runs the CLI (check B7), but only when invoked separately. Observed 2026-09-19: BUG-3484's Root Cause quoted two pytest flags as one joined string while `scripts/pyproject.toml` lists them on separate addopts lines; it surfaced as the single failure in an unrelated full-suite run.

## Expected Behavior

A fabricated or misattributed quote is reported next to the refine edit that introduced it, and repaired before the command completes. Pre-existing (grandfathered) findings in the same file are neither reported as new nor touched.

## Motivation

Late feedback is the defect: the error is made at write time and paid for in an unrelated 4-minute run, possibly by a different agent or session. Automation (ll-auto / refine loops) runs refine-issue, so this is also the write-time coverage for automation.

## Proposed Solution

File mode (`ll-verify-evidence FILE`) is a whole-file scan with **no baseline**, and ~400 grandfathered spans exist, so a naive post-write check on an older issue would report quotes refine did not write. The check must be a before/after delta.

**Delta lives in code, not in command prose (decided — reverses ENH-3515's "comparison belongs to the command").** `commands/refine-issue.md` allows only `Read`, `Glob`, `Edit(.issues/**)`, `Task`, and `Bash(git:*, ll-issues:*, ll-history-context:*, ll-code:*)` — no `Write`, no python/jq, so the command can neither persist a snapshot nor compute an occurrence-count diff deterministically, and a prose-described comparison cannot be validated with representative payloads. Add two flags to `ll-verify-evidence` file mode:

- `--save-snapshot PATH` — atomically write a versioned snapshot envelope containing findings and scan identity to `PATH` (the CLI does the write; no extra tool permission). Publish a snapshot only after a successful scan, including exit 1 with valid findings; never publish an empty-success snapshot on an execution failure.
- `--delta-from PATH` — scan, then compare occurrence counts keyed by `(span, artifact)`, excluding line numbers, against the snapshot; report only positive count differences as `new_findings` (with current line numbers for locating them), plus `preexisting_count`. This tolerates shifted lines while detecting a newly added duplicate of an existing bad quote and a change of attribution. Exit 0 = no new findings, 1 = new findings, exit 2 = snapshot/input/compatibility failure (**verification incomplete**, never clean).

**Snapshot contract:** both flags require exactly one existing, readable issue file. They are mutually exclusive and incompatible with `--all`, `--update-baseline`, and `--added-only`. Reject missing/unreadable inputs rather than letting a skipped scan count as clean. The snapshot envelope records a schema version, canonical project root and issue path, verifier compatibility version, and effective scan options (including `max_revisions`). Validate the envelope and finding field types before comparison; reject unsupported versions, wrong project/file identity, and incompatible options with exit 2. Issue-body edits between scans are expected and must not invalidate identity. Reject a snapshot destination that aliases the issue file; write failures must be explicit and leave no partial snapshot usable as a baseline.

**Invocation isolation:** the refinement command supplies a fresh UUID-based snapshot path under its run/scratch directory for each invocation, including concurrent passes on the same issue. Never reuse a fixed issue-ID-only path or fall back to a snapshot from an earlier run. Retain that invocation's original snapshot across all repair checks; do not overwrite it with a post-edit scan. A failed creation marks verification incomplete even if another snapshot file exists.

This is a diff between two scans of one file, not a corpus baseline: `--all`/baseline behavior is untouched.

Command changes (`commands/refine-issue.md`):
- Add `Bash(ll-verify-evidence:*)` to `allowed-tools`.
- **Snapshot** before the first body mutation — it must precede Step 5's `ll-issues fold-findings` writes, not merely Step 6's "Update Issue File". Retain the original snapshot throughout the pass.
- **Final check** with `--delta-from` after the last body-changing gate (after Step 6.7).
- **On a new finding**: reuse capture-issue's on-miss contract (ENH-3283): re-read the artifact and correct the quote, or describe the evidence in prose. A reviewed genuine counter-example may use `<!-- ll-evidence-ok: reason -->`; never suppress merely to clear the check. Allow one correction pass and recheck. If findings remain, remove the newly introduced quote or convert it to accurate prose, then perform one final check. Do not retry indefinitely or declare success with unresolved findings.
- **Preservation and modes**: explicitly allow correction/removal of this pass's additions in additive-only / `--gap-analysis` mode; preserve pre-existing content and findings. Cover default, `--auto`, `--gap-analysis`, and `--full-rewrite` paths. Under `--dry-run`, do not write, repair, or claim verification of unapplied additions; report verification as not run for the preview.
- **Execution contract**: exit 1 with valid JSON is scan data, not a command failure. Missing CLI, unexpected exit status, malformed JSON, or timeout means **verification incomplete**, never clean; note the reason and continue gracefully as check B7 does. Without a valid initial snapshot, do not treat every later finding as new. If a later scan fails, retain the known findings in the report rather than claiming they cleared.
- Final report distinguishes clean delta, repaired delta, unresolved findings, incomplete verification, and dry-run.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/verify_evidence.py` — `--save-snapshot`, `--delta-from`, the `(span, artifact)` count comparison (findings JSON already carries `span` and `artifact`)
- `commands/refine-issue.md` — tool permission; snapshot before Step 5 writes; delta after all body mutations; bounded repairs, mode/error handling, final status
- `skills/ll-refine-issue/SKILL.md` and the other host mirrors — re-synced via `ll-adapt --host <host> --apply` (mirror gates trip otherwise)
- `docs/reference/CLI.md` — document the two new flags

### Similar Patterns
- `skills/capture-issue/SKILL.md` — "Verify quoted evidence against the cited artifact" (ENH-3283), the on-miss contract to reuse
- `commands/verify-issues.md` — check B7 invokes `ll-verify-evidence "$ISSUE_FILE" --json`, lists `Bash(ll-verify-evidence:*)`, degrades gracefully when unavailable

### Tests
- `scripts/tests/test_verify_evidence.py` — unit tests for the delta with representative payloads: unchanged old findings, line shifts, a new quote, an additional duplicate of an old bad quote, changed attribution, repaired findings; missing/malformed snapshot → incomplete exit code.
- `scripts/tests/test_refine_issue_command.py` — contract checks: allowed tools, snapshot before `fold-findings`, final check after body-changing gates, bounded repairs, explicit dry-run / incomplete states, additive-mode repair allowance.

## Program Design

### Signatures

- `compute_findings_delta(before: list[dict], after: list[dict]) -> list[dict]` — positive occurrence-count differences keyed by `(span, artifact)`

### Call Path

`refine-issue` -> `ll-verify-evidence <issue-file> --json --save-snapshot <path>` before Step 5 writes -> body edits / `fold-findings` / body-changing gates -> `ll-verify-evidence <issue-file> --json --delta-from <path>` -> `main_verify_evidence` -> `compute_findings_delta` -> bounded repair and explicit status.

## Implementation Steps

1. Add `--save-snapshot` / `--delta-from`, the validated snapshot envelope, atomic writes, and `compute_findings_delta` to `little_loops.cli.verify_evidence`; test payloads, identity/option checks, flag exclusions, input/write failures, and exit 2 (tests first — `tdd_mode`).
2. Update `commands/refine-issue.md`: tool permission, unique per-invocation snapshot path and original-snapshot retention, early snapshot, final delta ordering, bounded repairs, preservation/mode rules, incomplete-verification reporting.
3. Extend `test_refine_issue_command.py` contract checks; document the flags in `docs/reference/CLI.md`.
4. Re-sync host mirrors (`ll-adapt --host <host> --apply`); run the mirror gates and the full suite.

## Impact

- **Priority**: P3 — workflow friction; no data risk.
- **Effort**: Moderate — small CLI addition with unit tests, plus command/mirror edits.
- **Risk**: Low — additive flags; the command degrades to "verification incomplete" on any failure.

## Parent Issue

Decomposed from ENH-3515: Shift-left evidence verification to refine-time and make the pre-commit hook visible

## Acceptance Criteria

- [ ] `--delta-from` reports only positive `(span, artifact)` count differences; line shifts are ignored; new duplicates and changed attributions are detected (unit tests with the payload set above).
- [ ] Missing/malformed snapshots, unsupported schema or invalid finding types, wrong project/file identity, incompatible scan options, missing/unreadable issue files, incompatible flags, and multiple input files yield exit 2, never clean success (CLI tests).
- [ ] Snapshot writes are atomic; failed scans/writes leave no usable partial snapshot, and the issue file cannot be used as the snapshot destination. Exit 1 with valid findings still produces a valid snapshot (tests).
- [ ] Independent invocations use distinct snapshot paths, including for the same issue; failed creation never reuses an old snapshot. All repair checks retain the original snapshot. Tests cover invocation isolation and command path construction.
- [ ] `commands/refine-issue.md` allows `Bash(ll-verify-evidence:*)`, snapshots before Step 5 / `fold-findings`, and runs the delta after every body-changing gate across default, auto, gap-analysis, and full-rewrite paths (contract test).
- [ ] The command text bounds repairs (one correction pass, then remove/convert, then one final check) and forbids reporting success with unresolved findings; suppression is only for reviewed counter-examples.
- [ ] Additive-only mode permits repairing this pass's additions while preserving earlier content. Dry-run makes no issue edits and does not claim verification.
- [ ] A failed snapshot is not treated as an empty baseline; incomplete verification is reported explicitly.
- [ ] `--all` / baseline behavior and the repo-wide suite gate are unchanged.
- [ ] Mirror gates pass after the command edit; `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **Non-goal (decided): no verification step in `/ll:reconcile-issue` or `/ll:format-issue`.** The verifier scans only `IN_SCOPE_SECTIONS` (Current Behavior, Steps to Reproduce, Root Cause, Motivation, Codebase Research Findings). Reconcile rewrites other sections and preserves the in-scope ones; format-issue restructures rather than authors quotes.
- **Non-goal: a corpus-baseline-aware file mode.** `--delta-from` compares two scans of one file only.
- Out of scope, optional low-priority follow-up: verifier leniency for a span whose whitespace-split tokens all appear close together in the attributed file (the BUG-3484 shape). Arguably the joined quote was genuinely inaccurate.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-20T00:10:57 - `d0eb6446-04cf-4c6e-ada1-f1ab3056d581.jsonl`
