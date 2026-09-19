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
- When the suite gate does fire, the message immediately identifies it as an issue-corpus evidence failure, not a code failure.

## Motivation

Late feedback is the real defect: the error is made at write time and paid for in an unrelated 4-minute run, possibly by a different agent or session than the one that wrote the quote. Any refine run that writes a bad quote turns the next unrelated change red, and the same suite gates every push to main on the self-hosted runner.

## Proposed Solution

1. **Refine-time verification, delta-scoped (`/ll:refine-issue` only).** File mode (`ll-verify-evidence FILE`) is a whole-file scan with **no baseline**, and ~400 grandfathered spans exist, so a naive post-write check on an older issue would report quotes refine did not write. Therefore:
   - Before the first body edit, snapshot findings: `ll-verify-evidence "$ISSUE_FILE" --json`.
   - After the body is written, run it again and report only findings absent from the snapshot (compare on span text + attributed artifact, not line number, since edits shift lines).
   - **On a new finding**: same contract as the capture-issue step (ENH-3283) — re-read the artifact and quote it correctly, or drop the quote and describe the evidence in prose; never leave the unverified span. A genuine counter-example gets the `ll-evidence-ok` suppression marker. Re-run until the delta is empty.
   - Degrade gracefully when the CLI is unavailable, as `commands/verify-issues.md` check B7 already does (note it and continue).
   - Add `Bash(ll-verify-evidence:*)` to the `allowed-tools` frontmatter of `commands/refine-issue.md`; without it the step is denied or prompts in automation.
   - No CLI change: the before/after diff is done in the command, not via a new baseline-aware file mode.
2. **Make the pre-commit hook's findings visible.**
   - **Unconditional**: add `verbose: true` to the hook entry so findings print even though the hook passes. Zero blocking risk; ships regardless of the measurement below.
   - **Conditional flip to blocking** (drop `|| true`): only if a replay of `--added-only` over the last 50 commits touching `.issues/` yields zero false positives. The BUG-3282 comment's stated condition points at `TestWholeCorpusPrecision`, which covers the extraction stage only, so it is not sufficient evidence by itself; rewrite the comment to cite the replay result and date. If the threshold is not met, stay warn-only + verbose and record the measured false positives in the comment.
3. **Label the suite failure.** Add a module-level constant in `scripts/tests/test_verify_evidence.py` (`GATE_FAILURE_LABEL = "ISSUE-CORPUS EVIDENCE FAILURE (not a code regression)"`) and prefix **both** `pytest.fail` calls in `test_no_new_unverifiable_evidence` with it (the findings failure and the timeout failure). The findings message additionally states that no code test failed because of it; the existing three remedies (fix the quote, correct the attribution, suppress a reviewed counter-example) stay as they are.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — `allowed-tools` entry; pre-edit snapshot + post-write delta `ll-verify-evidence` step
- `skills/ll-refine-issue/SKILL.md` and the other host mirrors — re-synced via `ll-adapt --host <host> --apply` (mirror gates trip otherwise)
- `.pre-commit-config.yaml` — `ll-verify-evidence` hook entry: add `verbose: true`; conditionally drop `|| true`; rewrite the BUG-3282 comment
- `scripts/tests/test_verify_evidence.py` — `GATE_FAILURE_LABEL` constant; both `pytest.fail` messages in `TestRepoGate.test_no_new_unverifiable_evidence`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/verify_evidence.py` — the CLI these steps invoke (no change; `IN_SCOPE_SECTIONS` determines which commands can introduce findings)

### Similar Patterns
- `skills/capture-issue/SKILL.md` — "Verify quoted evidence against the cited artifact" (ENH-3283), the on-miss contract to reuse
- `commands/verify-issues.md` — check B7 invokes `ll-verify-evidence "$ISSUE_FILE" --json`, lists `Bash(ll-verify-evidence:*)` in `allowed-tools`, and degrades gracefully when unavailable
- `scripts/tests/test_decisions_yaml_pre_commit_gate.py` — plumbing-test pattern for the hook entry

### Tests
- `scripts/tests/test_verify_evidence.py` — assert both failure messages start with `GATE_FAILURE_LABEL` (assert the constant, not prose)
- New pre-commit plumbing test modeled on `scripts/tests/test_decisions_yaml_pre_commit_gate.py` (skip when `pre-commit` absent): hook entry exists, has `verbose: true`, and its blocking/non-blocking state matches the comment
- Structural test that `commands/refine-issue.md` lists `Bash(ll-verify-evidence:*)` in `allowed-tools` and contains the snapshot + delta steps

### Documentation
- `docs/reference/CLI.md` — `ll-verify-evidence` entry, only if the hook flips to blocking

### Configuration
- `.pre-commit-config.yaml` (see Files to Modify)

## Program Design

### Signatures

- `TestRepoGate.test_no_new_unverifiable_evidence(self, gate_cli: str) -> None` — both `pytest.fail` messages prefixed with `GATE_FAILURE_LABEL`

### Call Path

`refine-issue` command -> `ll-verify-evidence <issue-file> --json` (pre-edit snapshot, post-write delta) -> `extract_candidate_spans`; `pre-commit` -> `ll-verify-evidence --added-only` -> `in_scope_sections`

## Implementation Steps

1. Add `verbose: true` to the hook entry (unconditional).
2. Replay `ll-verify-evidence --added-only` over the last 50 commits touching `.issues/`; flip to blocking only on zero false positives. Rewrite the BUG-3282 comment with the result either way.
3. Add the plumbing test following `scripts/tests/test_decisions_yaml_pre_commit_gate.py`.
4. Add `Bash(ll-verify-evidence:*)` plus the snapshot / delta / on-miss steps to `commands/refine-issue.md`; add the structural test.
5. Add `GATE_FAILURE_LABEL` and prefix both `TestRepoGate` failure messages; assert the constant.
6. Re-sync host mirrors (`ll-adapt --host <host> --apply`).

## Impact

- **Priority**: P3 — workflow friction and misleading red suites, no data risk.
- **Effort**: Small; one command-markdown edit, one hook change, two small tests, one message change.
- **Risk**: Low. `verbose: true` cannot block. A blocking hook with imperfect precision could stall automation commits — gated by the step 2 threshold.

## Scope Boundaries

- **Non-goal: do not remove the repo-wide gate from the default suite or put it behind an excluded marker.** BUG-3442 showed this gate sitting structurally red in CI unnoticed; hooks can be bypassed or uninstalled; automation commits from worktrees. The suite is the only always-on enforcement and matches the sibling `test_*_gate.py` pattern (docs-audience, decisions-yaml, program-design).
- **Non-goal (decided): no verification step in `/ll:reconcile-issue` or `/ll:format-issue`.** The verifier scans only `IN_SCOPE_SECTIONS` (Current Behavior, Steps to Reproduce, Root Cause, Motivation, Codebase Research Findings). Reconcile rewrites Implementation Steps, Acceptance Criteria and the Integration Map and explicitly preserves the in-scope sections; format-issue restructures rather than authors quotes. A check there could only re-report spans the command did not write.
- **Non-goal: surfacing warn-only hook findings in ll-auto / ll-parallel run summaries.** No mechanism exists for it today. Automation is covered at write time by the refine-issue step (which automation runs), and at commit time if the hook flips to blocking. Capture a follow-up only if the hook stays warn-only *and* automation-written findings keep reaching the suite gate.
- **Non-goal: a baseline-aware file mode for the CLI.** The delta is computed in the command.
- Out of scope, optional low-priority follow-up: verifier leniency for a span whose whitespace-split tokens all appear close together in the attributed file (the BUG-3484 shape). Arguably the joined quote was genuinely inaccurate.

## Acceptance Criteria

- [ ] `/ll:refine-issue` on an issue, ending in a state with a newly written misattributed quote, reports that span before the command finishes and does not leave it in the file.
- [ ] `/ll:refine-issue` on an issue with pre-existing (baselined) findings does not report them.
- [ ] `commands/refine-issue.md` lists `Bash(ll-verify-evidence:*)` in `allowed-tools`.
- [ ] An interactive `git commit` adding an unverifiable span prints the finding (hook has `verbose: true`).
- [ ] The hook is blocking if and only if the 50-commit `--added-only` replay found zero false positives; the hook comment records the result.
- [ ] A plumbing test covers the hook entry, skipping when `pre-commit` is absent.
- [ ] Both `TestRepoGate` failure messages start with `GATE_FAILURE_LABEL`.
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
