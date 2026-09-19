---
id: ENH-3515
type: ENH
title: Shift-left evidence verification to refine-time and make the pre-commit hook
  visible
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:57:20Z'
---

# ENH-3515: Shift-left evidence verification to refine-time and make the pre-commit hook visible

## Summary

An unverifiable evidence quote written while refining an issue is only reported by the repo-wide pytest gate, minutes later, inside an unrelated full-suite run. Close the write-time and commit-time gaps so the suite gate becomes a rarely-firing backstop. Keep the suite gate where it is.

## Current Behavior

Three enforcement points exist for `ll-verify-evidence`, and only the last one is effective:

- **Write time**: only `/ll:capture-issue` verifies quoted spans before writing (ENH-3283). `/ll:refine-issue` authors new quoted evidence (its Codebase Research Findings, plus Root Cause / Current Behavior fills) with no check. `/ll:verify-issues` runs the CLI, but only when invoked separately.
- **Commit time**: the `ll-verify-evidence` hook in `.pre-commit-config.yaml` is deliberately warn-only (BUG-3282), and its output is swallowed: the `|| true` makes the hook always pass, and pre-commit hides the output of passing hooks unless the hook sets `verbose: true`. It also fires inside ll-auto / ll-parallel / refine-loop commits where nobody reads a warning.
- **Suite time**: `TestRepoGate.test_no_new_unverifiable_evidence` in `scripts/tests/test_verify_evidence.py` runs the CLI with `--all` against the baseline. This is where findings actually surface.

Observed 2026-09-19: BUG-3484's Root Cause quoted two pytest flags as one joined string, while `scripts/pyproject.toml` lists them on separate addopts lines. The full suite reported 1 failed / 25068 passed; the single failure was this issue-file quote, and the failure output reads like a code regression.

## Expected Behavior

- A fabricated or misattributed quote is reported next to the edit that introduced it: at refine time, or at commit time at the latest.
- The suite gate stays in the default suite as the always-on backstop and rarely fires.
- When the suite gate does fire, the message identifies the issue-corpus evidence gate and distinguishes findings from verifier execution failures, without ruling out a verifier regression or making claims about other tests.

## Motivation

Late feedback is the real defect: the error is made at write time and paid for in an unrelated 4-minute run, possibly by a different agent or session than the one that wrote the quote. Any refine run that writes a bad quote turns the next unrelated change red, and the same suite gates every push to main on the self-hosted runner.

## Proposed Solution

1. **Refine-time verification, delta-scoped (`/ll:refine-issue` only).** File mode (`ll-verify-evidence FILE`) is a whole-file scan with **no baseline**, and ~400 grandfathered spans exist, so a naive post-write check on an older issue would report quotes refine did not write. Therefore:
   - Before the first body mutation, snapshot findings with `ll-verify-evidence "$ISSUE_FILE" --json`. This must precede Step 5's `ll-issues fold-findings` writes, not merely Step 6's "Update Issue File". Retain the original snapshot throughout the pass.
   - After the last body-changing gate, run it again. Compare occurrence counts keyed by `(span, artifact)`, excluding line numbers: positive count differences are new findings. This tolerates shifted lines while detecting a newly added duplicate of an existing bad quote and a change of attribution. Preserve enough edit context to locate this pass's additions without changing earlier occurrences.
   - **On a new finding**: reuse capture-issue's on-miss contract (ENH-3283): re-read the artifact and correct the quote, or describe the evidence in prose. A reviewed genuine counter-example may use `<!-- ll-evidence-ok: reason -->`; never suppress merely to clear the check. Allow one correction pass and recheck. If findings remain, remove the newly introduced quote or convert it to accurate prose, then perform one final check. Do not retry indefinitely or declare success with unresolved findings.
   - **Preservation and modes**: explicitly allow correction/removal of this pass's additions in additive-only / `--gap-analysis` mode; preserve pre-existing content and findings. Cover default, `--auto`, `--gap-analysis`, and `--full-rewrite` paths. Under `--dry-run`, do not write, repair, or claim verification of unapplied additions; report verification as not run for the preview.
   - **Execution contract**: exit 0 with valid JSON means no findings; exit 1 with valid findings JSON is a successful scan that must be compared, not a command-execution failure. Missing CLI, unexpected exit status, malformed JSON, or timeout means **verification incomplete**, never clean. Note the reason and continue gracefully as check B7 does when unavailable. Without a valid initial snapshot, do not treat every later finding as new; report that delta verification could not be completed. If a later scan fails, retain the known findings in the report rather than claiming they cleared.
   - Add `Bash(ll-verify-evidence:*)` to `commands/refine-issue.md`'s `allowed-tools`; ensure any comparison mechanism is also usable under the command's tool permissions. Specify the count comparison concretely in the command and validate it with representative before/after payloads.
   - No new baseline-aware file mode: the before/after comparison belongs to the command. Its final report distinguishes clean delta, repaired delta, unresolved findings, incomplete verification, and dry-run.
2. **Make the pre-commit hook's findings visible.**
   - **Unconditional**: add `verbose: true` so findings print even though the hook passes. This ships regardless of the measurement below.
   - **Reproducible replay**: freeze and record the verifier revision and the 50 most recent commits touching `.issues/` at the measurement cutoff. For each commit, use an isolated repository with its parent as HEAD and the commit's tree staged and checked out; pass explicit changed issue filenames to `ll-verify-evidence --added-only`. Define first-parent handling for merges and deletion/rename handling. Do not mutate the developer's index or working tree. Simply checking out a commit produces no staged additions and is not a replay.
   - **Historical isolation**: the matcher uses `git log --all`. Restrict replay refs to history available at the parent, with the target commit's tree supplying the staged/working content; exclude later revisions and unrelated refs. A normal worktree sharing current refs is insufficient. Isolate verdict caches per replay repository so cached results do not leak across historical states.
   - **Evidence and coverage**: retain a replay report with cutoff, commit IDs, verifier revision, setup/reproduction instructions, changed files/added lines, eligible candidate counts, findings and their manual true/false-positive classifications, and execution errors. Confirm nonzero eligible coverage and use a deliberately invalid staged quote as a positive control. Zero findings on an empty or broken replay is not precision evidence. Store the report under `postmortems/` and cite its path, date, and summary in the hook comment.
   - **Conditional flip to blocking** (drop `|| true`): only after the complete, valid 50-commit replay has zero false positives and its coverage/control checks pass. Otherwise retain warn-only + verbose and record the false positives or why the measurement was inconclusive. `TestWholeCorpusPrecision` covers extraction only and cannot substitute for this replay. If blocking is enabled, also remove "(warn-only)" from the hook's display name.
3. **Label the suite gate neutrally.** Add `GATE_FAILURE_LABEL = "ISSUE-CORPUS EVIDENCE GATE"` in `scripts/tests/test_verify_evidence.py` and prefix both explicit `pytest.fail` messages in `test_no_new_unverifiable_evidence`. Distinguish unverifiable corpus findings from verifier timeout/execution failure. Preserve the timeout's possible performance-regression diagnosis and the findings' three remedies (fix quote, correct attribution, suppress a reviewed counter-example). Do not assert that the verifier cannot have a code regression or claim other tests passed.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — tool permissions; snapshot before Step 5 writes; occurrence-count delta after all body mutations; bounded repairs, mode/error handling, and final verification status
- `skills/ll-refine-issue/SKILL.md` and the other host mirrors — re-synced via `ll-adapt --host <host> --apply` (mirror gates trip otherwise)
- `.pre-commit-config.yaml` — `ll-verify-evidence` hook entry: add `verbose: true`; conditionally drop `|| true`; rewrite the BUG-3282 comment
- `scripts/tests/test_verify_evidence.py` — neutral `GATE_FAILURE_LABEL`; distinct findings/timeout messages and tests that exercise both branches
- `scripts/tests/test_verify_evidence_pre_commit_gate.py` (new) — unconditional configuration checks and actual-hook subprocess tests
- Refinement command contract tests — permissions, ordering, mode/error branches, and delta examples (follow the existing command-test layout)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/verify_evidence.py` — the CLI these steps invoke (no change; `IN_SCOPE_SECTIONS` determines which commands can introduce findings)

### Similar Patterns
- `skills/capture-issue/SKILL.md` — "Verify quoted evidence against the cited artifact" (ENH-3283), the on-miss contract to reuse
- `commands/verify-issues.md` — check B7 invokes `ll-verify-evidence "$ISSUE_FILE" --json`, lists `Bash(ll-verify-evidence:*)` in `allowed-tools`, and degrades gracefully when unavailable
- `scripts/tests/test_decisions_yaml_pre_commit_gate.py` — plumbing-test pattern for the hook entry

### Tests
- Exercise both `TestRepoGate.test_no_new_unverifiable_evidence` failure branches with controlled subprocess results: assert the neutral prefix on the actual raised messages and distinct findings/timeout diagnoses, rather than merely checking that the constant exists.
- Unconditional hook configuration checks: entry exists, `verbose: true`, and entry/display name/comment agree on blocking behavior. These checks do not require `pre-commit` to be installed.
- Temporary-repository subprocess tests using the actual hook entry: stage an invalid quote and assert the finding appears in captured output and the exit status matches the chosen blocking policy; stage a valid quote as a clean control. Skip only subprocess tests when `pre-commit` or the verifier is absent. Stage files explicitly because the hook uses `--added-only`.
- Refinement contract checks: allowed tools, snapshot before `fold-findings`, final check after body-changing gates, original-content preservation, bounded repairs, and explicit dry-run/incomplete states.
- Exercise the specified count comparison with representative payloads: unchanged old findings, line shifts, a new quote, an additional duplicate of an old bad quote, changed attribution, and repaired findings. Cover exit 1 with valid JSON versus malformed output / missing CLI / execution failure. Structural keyword checks alone do not establish the delta behavior.

### Documentation
- `docs/reference/CLI.md` — `ll-verify-evidence` entry, only if the hook flips to blocking

### Configuration
- `.pre-commit-config.yaml` (see Files to Modify)

## Program Design

### Signatures

- `TestRepoGate.test_no_new_unverifiable_evidence(self, gate_cli: str) -> None` — both `pytest.fail` messages prefixed with `GATE_FAILURE_LABEL`

### Call Path

`refine-issue` -> snapshot before Step 5 writes -> body edits / `fold-findings` / body-changing gates -> final scan -> positive occurrence-count delta on `(span, artifact)` -> bounded repair and explicit status. Both scans use `ll-verify-evidence <issue-file> --json`; exit 1 is findings data. `pre-commit` -> `ll-verify-evidence --added-only <changed-issue-files>` -> staged-line filtering and evidence verification.

## Implementation Steps

1. Add `verbose: true` to the hook entry (unconditional).
2. Perform and document the isolated 50-commit replay using the setup, historical-ref isolation, coverage, classification, and positive-control requirements above. Flip to blocking only if all conditions pass; otherwise retain warn-only. Update comment and display name consistently.
3. Add unconditional configuration checks plus actual-hook subprocess tests for visible invalid-quote findings and a clean control.
4. Update `commands/refine-issue.md` with permitted tooling, early snapshot, occurrence-count comparison, final check ordering, bounded repairs, preservation/mode rules, and incomplete-verification reporting. Validate the comparison examples and command contract.
5. Add the neutral `GATE_FAILURE_LABEL`, distinguish the findings and timeout messages, and exercise both actual failure branches in tests.
6. Re-sync host mirrors (`ll-adapt --host <host> --apply`) and run the relevant tests and mirror gates; the default full suite remains the authoritative gate.

## Impact

- **Priority**: P3 — workflow friction and misleading red suites, no data risk.
- **Effort**: Moderate; command and hook changes are small, but a valid historical replay, manual finding classification, and behavioral validation are substantive work.
- **Risk**: Low. `verbose: true` cannot block. A blocking hook with imperfect precision could stall automation commits — gated by the step 2 threshold.

## Scope Boundaries

- **Non-goal: do not remove the repo-wide gate from the default suite or put it behind an excluded marker.** BUG-3442 showed this gate sitting structurally red in CI unnoticed; hooks can be bypassed or uninstalled; automation commits from worktrees. The suite is the only always-on enforcement and matches the sibling `test_*_gate.py` pattern (docs-audience, decisions-yaml, program-design).
- **Non-goal (decided): no verification step in `/ll:reconcile-issue` or `/ll:format-issue`.** The verifier scans only `IN_SCOPE_SECTIONS` (Current Behavior, Steps to Reproduce, Root Cause, Motivation, Codebase Research Findings). Reconcile rewrites Implementation Steps, Acceptance Criteria and the Integration Map and explicitly preserves the in-scope sections; format-issue restructures rather than authors quotes. A check there could only re-report spans the command did not write.
- **Non-goal: surfacing warn-only hook findings in ll-auto / ll-parallel run summaries.** No mechanism exists for it today. Automation is covered at write time by the refine-issue step (which automation runs), and at commit time if the hook flips to blocking. Capture a follow-up only if the hook stays warn-only *and* automation-written findings keep reaching the suite gate.
- **Non-goal: a baseline-aware file mode for the CLI.** The delta is computed in the command.
- Out of scope, optional low-priority follow-up: verifier leniency for a span whose whitespace-split tokens all appear close together in the attributed file (the BUG-3484 shape). Arguably the joined quote was genuinely inaccurate.

## Acceptance Criteria

- [ ] Refinement snapshots before Step 5 / `fold-findings` can mutate the body and performs its final verification after every body-changing gate, across default, auto, gap-analysis, and full-rewrite paths.
- [ ] With successful scans, a newly written misattributed quote is reported and corrected, converted to accurate prose, removed, or suppressed only as a reviewed counter-example before completion. Repair attempts are bounded; unresolved findings cannot be reported as success.
- [ ] Pre-existing findings remain untouched and are excluded from the delta even when line numbers shift. Additional duplicate occurrences and changed attributions are detected by the count comparison.
- [ ] Additive-only mode permits repairing this pass's additions while preserving earlier content. Dry-run makes no issue edits and does not claim verification of unapplied additions.
- [ ] Exit 1 with valid findings JSON is processed as scan data. Missing CLI, unexpected exit, malformed JSON, or timeout produces an explicit incomplete-verification status; a failed snapshot is not treated as an empty baseline.
- [ ] `commands/refine-issue.md` allows `Bash(ll-verify-evidence:*)` and any tools needed for its comparison mechanism.
- [ ] An installed hook prints an invalid staged quote's finding even when warn-only; `verbose: true` is unconditional.
- [ ] Blocking is enabled only when the documented 50-commit replay is complete, uses staged changes and historically isolated refs/caches, demonstrates nonzero eligible coverage and a working positive control, and has zero manually classified false positives. Otherwise it remains warn-only. The hook comment records the date, result, and report path; its display name agrees with its behavior.
- [ ] Hook configuration checks run without optional executables. Actual-hook subprocess tests assert output and exit status for invalid and clean staged fixtures, skipping only when required executables are absent.
- [ ] Delta validation covers old findings, line shifts, new quotes, new duplicate occurrences, changed attribution, repairs, and scan failures.
- [ ] Both explicit `TestRepoGate` failure messages start with the neutral `GATE_FAILURE_LABEL` and are exercised in tests. Findings and timeout diagnoses remain distinct; neither makes unsupported claims about other tests or excludes verifier regressions.
- [ ] The repo-wide gate still runs under the default `python -m pytest scripts/tests/` invocation.
- [ ] Mirror gates pass after the command edit.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `verify-evidence`, `issue-refinement`, `pre-commit`

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-19T21:04:51 - `e76a6089-0241-4098-9983-3c93e7b1386d.jsonl`
- `/ll:capture-issue` - 2026-09-19T20:57:27 - `7ba3809c-e334-468e-81b6-cf0bbfd0f90c.jsonl`
