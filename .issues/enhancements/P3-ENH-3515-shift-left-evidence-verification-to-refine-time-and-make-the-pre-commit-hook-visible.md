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

- **Write time**: only `/ll:capture-issue` verifies quoted spans before writing (ENH-3283). `/ll:refine-issue`, `/ll:reconcile-issue` and `/ll:format-issue` rewrite issue bodies, including Root Cause sections that quote source files, with no check. `/ll:verify-issues` runs the CLI, but only when invoked separately.
- **Commit time**: the `ll-verify-evidence` hook in `.pre-commit-config.yaml` is deliberately warn-only (BUG-3282), and its output is swallowed. It fires inside ll-auto / ll-parallel / refine-loop commits where nobody reads a warning, so a finding is effectively silent.
- **Suite time**: `TestRepoGate.test_no_new_unverifiable_evidence` in `scripts/tests/test_verify_evidence.py` runs the CLI with `--all` against the baseline. This is where findings actually surface.

Observed 2026-09-19: BUG-3484's Root Cause quoted two pytest flags as one joined string, while `scripts/pyproject.toml` lists them on separate addopts lines. The full suite reported 1 failed / 25068 passed; the single failure was this issue-file quote, and the failure output reads like a code regression.

## Expected Behavior

- A fabricated or misattributed quote is reported next to the edit that introduced it, at refine/reconcile time or at commit time at the latest.
- The suite gate stays in the default suite as the always-on backstop and rarely fires.
- When the suite gate does fire, the message immediately identifies it as an issue-corpus evidence failure, not a code failure.

## Motivation

Late feedback is the real defect: the error is made at write time and paid for in an unrelated 4-minute run, possibly by a different agent or session than the one that wrote the quote. Any refine run that writes a bad quote turns the next unrelated change red, and the same suite gates every push to main on the self-hosted runner.

## Proposed Solution

1. **Refine-time verification.** Port the capture-issue step "Verify quoted evidence against the cited artifact" (ENH-3283, with its non-trigger list) into `commands/refine-issue.md` and the reconcile-issue command, run after the body is written. Prefer invoking the CLI on the written file (`ll-verify-evidence <issue-file> --json`) over re-describing the procedure in prose, and degrade gracefully when the CLI is unavailable, as `commands/verify-issues.md` already does. Decide during refinement whether `/ll:format-issue` needs it (it restructures rather than authors quotes).
2. **Make the pre-commit hook's findings visible.** Either flip the hook to blocking now that the whole-corpus gate has a stable baseline (the condition named in the hook's BUG-3282 comment), or keep it non-blocking but persist findings where automation surfaces them (e.g. a line in the run summary). Blocking must not wedge ll-auto / ll-parallel mid-run: evaluate precision on `--added-only` first.
3. **Label the suite failure.** Prefix the `pytest.fail` message in `TestRepoGate` so it states this is an issue-file evidence finding, that no code test failed because of it, and names the two remedies.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. Measure `--added-only` precision over recent `.issues/` commits to decide blocking vs. surfaced-warning for the hook.
2. Add the verification step to refine-issue and reconcile-issue; resolve the format-issue question.
3. Update the hook entry in `.pre-commit-config.yaml` and its BUG-3282 comment per step 1's outcome; add a plumbing test following `scripts/tests/test_decisions_yaml_pre_commit_gate.py`.
4. Reword the `TestRepoGate` failure message.
5. Re-sync host mirrors after the command/skill edits (`ll-adapt --host <host> --apply`).

## Impact

- **Priority**: P3 — workflow friction and misleading red suites, no data risk.
- **Effort**: Small–medium; mostly command-markdown edits, one hook change, one test.
- **Risk**: Low, except a blocking hook with imperfect precision could stall automation commits — gated by step 1.

## Scope Boundaries

- **Non-goal: do not remove the repo-wide gate from the default suite or put it behind an excluded marker.** BUG-3442 showed this gate sitting structurally red in CI unnoticed; hooks can be bypassed or uninstalled; automation commits from worktrees. The suite is the only always-on enforcement and matches the sibling `test_*_gate.py` pattern (docs-audience, decisions-yaml, program-design).
- Out of scope, optional low-priority follow-up: verifier leniency for a span whose whitespace-split tokens all appear close together in the attributed file (the BUG-3484 shape). Arguably the joined quote was genuinely inaccurate.

## Acceptance Criteria

- [ ] Refining an issue into a state with a misattributed quote reports the span before the command finishes.
- [ ] A commit adding an unverifiable span produces a finding that is visible to the committer or to the automation run summary (blocking or surfaced, per step 1).
- [ ] A plumbing test covers the hook entry, skipping when `pre-commit` is absent.
- [ ] The `TestRepoGate` failure message identifies itself as an issue-corpus evidence failure.
- [ ] The repo-wide gate still runs under the default `python -m pytest scripts/tests/` invocation.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `verify-evidence`, `issue-refinement`, `pre-commit`

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-19T20:57:27 - `7ba3809c-e334-468e-81b6-cf0bbfd0f90c.jsonl`
