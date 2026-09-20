---
id: ENH-3518
type: ENH
title: Make the ll-verify-evidence pre-commit hook visible and label the suite gate
  neutrally
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T23:23:49Z'
labels:
- enhancement
- verify-evidence
- pre-commit
parent: ENH-3515
blocks:
- ENH-3520
relates_to:
- BUG-3282
- BUG-3484
- BUG-3442
---

# ENH-3518: Make the ll-verify-evidence pre-commit hook visible and label the suite gate neutrally

## Summary

Two cheap, unconditional wins split out of ENH-3515: make the warn-only `ll-verify-evidence` pre-commit hook actually print its findings, and label the repo-wide suite gate so a failure reads as an issue-corpus evidence finding rather than a code regression.

## Current Behavior

- The `ll-verify-evidence` hook in `.pre-commit-config.yaml` is deliberately warn-only (BUG-3282) and its output is swallowed: the `|| true` makes the hook always pass, and pre-commit hides the output of passing hooks unless the hook sets `verbose: true`.
- `TestRepoGate.test_no_new_unverifiable_evidence` in `scripts/tests/test_verify_evidence.py` has two explicit `pytest.fail` sites (timeout, findings). Neither identifies itself as the issue-corpus gate. Observed 2026-09-19 (BUG-3484): the full suite reported 1 failed / 25068 passed; the single failure was an issue-file quote and the output read like a code regression.

## Expected Behavior

- An installed hook prints an invalid staged quote's finding even though the hook passes.
- All gate failure messages start with a neutral label and distinguish corpus findings, timeout, and verifier execution failure.

## Motivation

A warn-only hook whose warnings are hidden enforces nothing, and a gate failure that reads like a code regression sends whoever hits it debugging the wrong thing. Both fixes are small and unconditional, so they should not wait on the refine-time delta or the precision replay.

The `|| true` also hides verifier *crashes* (ImportError, argparse error, uncaught exception): today they pass the hook silently. `verbose: true` makes the traceback visible, so a broken verifier is no longer indistinguishable from a clean one.

## Proposed Solution

1. Add `verbose: true` to the `ll-verify-evidence` hook entry. The hook stays warn-only (`|| true` and the "(warn-only)" display name are unchanged here — flipping to blocking is the sibling replay issue). Update the BUG-3282 comment to say findings are now printed.
   - **Accepted noise**: with `verbose: true`, every commit touching an issue file prints the one-line `ll-verify-evidence: PASS — no unverifiable evidence spans` report, including the continuous issue-file commits from ll-auto / refine loops. This is accepted deliberately: the entry stays unchanged so the `|| true` policy derivation in the config tests stays simple, and an only-print-on-failure wrapper would also swallow the crash traceback's exit status. Do not rewrite the entry to suppress it.
   - A verifier crash now prints its traceback (no "N finding(s)" report header), which is how it is told apart from a finding.
2. Add `GATE_FAILURE_LABEL = "ISSUE-CORPUS EVIDENCE GATE"` in `scripts/tests/test_verify_evidence.py` and prefix the existing findings/timeout messages plus a new execution-failure branch in `test_no_new_unverifiable_evidence`. Validate the subprocess exit status and JSON schema before using the payload: accept clean only for exit 0 with a consistent clean payload, and findings only for exit 1 with a consistent non-empty findings payload. Unexpected exit codes, process-launch failure, malformed JSON, invalid field types, and inconsistent status/payload combinations receive the labelled execution-failure diagnosis with useful stderr context; they must neither pass nor escape as an unlabelled parsing exception. Distinguish unverifiable corpus findings from verifier timeout/execution failure. Preserve the timeout's possible performance-regression diagnosis and the findings' three remedies (fix quote, correct attribution, suppress a reviewed counter-example). Do not assert that the verifier cannot have a code regression or claim other tests passed.
   - **Payload contract** (from `_findings_to_json` in `little_loops.cli.verify_evidence`): `ok: bool`, `mode: str`, `count: int`, `findings: list` of objects with `file: str`, `line: int`, `section: str`, `span: str`, `artifact: str`. **Clean** = exit 0 and `ok is True` and `count == 0` and `findings == []`. **Findings** = exit 1 and `ok is False` and `count == len(findings) > 0`. Everything else is execution failure.
   - **Exit 1 is ambiguous**: an uncaught exception in the CLI also exits 1, with empty stdout and a traceback on stderr. It must classify as execution failure (stdout is not valid JSON), never as findings — test this case by name.
   - **Classification lives in a pure helper**, `_classify_gate_result(returncode, stdout, stderr)`, so the branches are unit-tested without patching `subprocess.run`. The test body keeps only the `subprocess.run` call and the `TimeoutExpired` / `OSError` (launch failure) handlers.
   - The findings message lists at most 20 findings; when truncated it must say so (`showing 20 of N`).
3. Make the labelled timeout branch reachable. `GATE_TIMEOUT` is 120 and the suite-wide `--timeout=120` (thread method, `scripts/pyproject.toml`) is also 120; the test has no `@pytest.mark.timeout`, and pytest's clock starts before the subprocess's, so pytest-timeout kills the xdist worker first — the labelled `TimeoutExpired` message never appears and the scan is orphaned, the exact failure the `GATE_TIMEOUT` comment says the cap exists to prevent. Add `@pytest.mark.timeout(GATE_TIMEOUT + 30)` to `test_no_new_unverifiable_evidence` (keep `GATE_TIMEOUT = 120`; its headroom rationale is documented) and extend the `GATE_TIMEOUT` comment to record the ordering requirement.

## Integration Map

### Files to Modify
- `.pre-commit-config.yaml` — `ll-verify-evidence` hook entry: add `verbose: true`; refresh the BUG-3282 comment
- `scripts/tests/test_verify_evidence.py` — `GATE_FAILURE_LABEL`; distinct findings/timeout/execution-failure messages; tests exercising all branches
- `scripts/tests/test_verify_evidence_pre_commit_gate.py` (new) — configuration checks and actual-hook subprocess tests

### Similar Patterns
- `scripts/tests/test_decisions_yaml_pre_commit_gate.py` — plumbing-test pattern for a hook entry

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_evidence.py` — `TestRepoGate.test_no_new_unverifiable_evidence` (both `pytest.fail` sites; shares `GATE_CLI`, `GATE_TIMEOUT`, `_fail_if_shallow_checkout`); no existing test asserts on the old message text, so relabeling breaks nothing. Use `pytest.raises(pytest.fail.Exception)` as in the precondition test near `test_..._must_fail_not_skip` (~line 1008) [Agent 3 finding]. **Do not blanket-monkeypatch `subprocess.run`**: `_fail_if_shallow_checkout` runs `git rev-parse --is-shallow-repository` through it first, so a global patch intercepts the precondition. Test the clean/findings/execution-failure branches through the pure `_classify_gate_result` helper; only the `TimeoutExpired` and `OSError` launch-failure branches need a patched `subprocess.run`, and that patch must dispatch on the command (delegate to the real `subprocess.run` unless `cmd[0]` is the gate CLI).
- `scripts/tests/test_decisions_yaml_pre_commit_gate.py` — asserts on `.pre-commit-config.yaml` as literal text (no YAML parse); new gate module should match, but read the real config rather than a copied one [Agent 3 finding]

- Exercise all `TestRepoGate.test_no_new_unverifiable_evidence` failure branches with controlled subprocess results, including malformed JSON, unexpected exit codes, and inconsistent payloads: assert the neutral prefix on the actual raised messages and distinct findings/timeout/execution-failure diagnoses, rather than merely checking that the constant exists.
- Unconditional hook configuration checks: entry exists, `verbose: true`, and entry / display name / comment agree on blocking behavior (derive the expected policy from whether the entry contains `|| true`, so the sibling replay issue can flip it without rewriting these tests). No `pre-commit` install required.
- Temporary-repository subprocess tests using the actual hook entry: stage an invalid quote and assert the finding appears in captured output and the exit status matches the configured policy; stage a valid quote as a clean control. Skip only the subprocess tests when `pre-commit` or the verifier is absent. Stage files explicitly because the hook uses `--added-only`.
  - **Mechanics**: run `pre-commit run ll-verify-evidence --config <REPO_ROOT>/.pre-commit-config.yaml --files .issues/bugs/<name>.md` with `cwd` = the temp repo, so the *real* hook entry executes. Do not copy the config the way `_write_config` in `test_decisions_yaml_pre_commit_gate.py` does — a copy can drift from the entry under test.
  - **Fixture**: `git init` a temp repo, commit the cited artifact (the verifier searches git history, so the artifact must be committed, not merely present), then write and `git add` an issue file under `.issues/` quoting it. The `repo` fixture and `_mkissues` in `test_verify_evidence.py` are the starting point. The invalid case quotes text absent from the artifact; the control quotes text present in it.
  - Give every `pre-commit` subprocess call `timeout=60` (well under the suite's 120s per-test cap).
  - Assert the crash case is distinguishable where practical: finding output contains the `finding(s)` report header; a traceback does not.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-verify-evidence` **Gates:** line ("pre-commit ... warn-only on first release") describes the hook; add that findings are now printed (`verbose: true`) [Agent 2 finding]
- `CONTRIBUTING.md` — has "Decisions YAML Validation (ll-verify-decisions)" hook section but none for `ll-verify-evidence`; **in scope**: add a short sibling section (activation via `pre-commit install`, warn-only + findings printed, `--no-verify` bypass covered by the suite gate) [Agent 2 finding]

## Program Design

### Signatures

- `TestRepoGate.test_no_new_unverifiable_evidence(self, gate_cli: str) -> None` — findings, timeout, and execution-failure messages prefixed with `GATE_FAILURE_LABEL`; carries `@pytest.mark.timeout(GATE_TIMEOUT + 30)`
- `_classify_gate_result(returncode: int, stdout: str, stderr: str) -> tuple[str, str]` — pure classifier returning (`"clean"` | `"findings"` | `"execution_failure"`, labelled message); module-level in `scripts/tests/test_verify_evidence.py`

### Call Path

`pre-commit` -> `ll-verify-evidence --added-only <changed-issue-files>` -> findings printed via `verbose: true`. `pytest` -> `TestRepoGate.test_no_new_unverifiable_evidence` -> labelled `pytest.fail`.

## Implementation Steps

1. Add `verbose: true` to the hook entry and refresh the BUG-3282 comment.
2. Add `GATE_FAILURE_LABEL` and the pure `_classify_gate_result` helper; validate return codes/payloads against the payload contract, distinguish findings, timeout, and execution-failure messages, note truncation (`showing 20 of N`), and exercise all branches in tests.
3. Add `@pytest.mark.timeout(GATE_TIMEOUT + 30)` to the gate test and record the ordering requirement in the `GATE_TIMEOUT` comment.
4. Add `test_verify_evidence_pre_commit_gate.py`: policy-derived configuration checks plus actual-hook subprocess tests (invalid quote visible, clean control) run against the real config via `--config`.
5. Update `docs/reference/CLI.md` Gates line and add the `CONTRIBUTING.md` hook section.
6. Run `python -m pytest scripts/tests/`, then `ruff check` and `python -m mypy` scoped to the touched test files.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/CLI.md` `### ll-verify-evidence` Gates line — note the hook now prints findings
- Update `scripts/tests/test_verify_evidence.py` — relabel both `pytest.fail` sites; add branch tests via patched `subprocess.run`

## Impact

- **Priority**: P3 — misleading red suites and invisible warnings; no data risk.
- **Effort**: Small.
- **Risk**: Low. `verbose: true` cannot block.

## Parent Issue

Decomposed from ENH-3515: Shift-left evidence verification to refine-time and make the pre-commit hook visible

## Acceptance Criteria

- [ ] `verbose: true` is set on the `ll-verify-evidence` hook; entry, display name and comment agree that it is warn-only.
- [ ] An installed hook prints an invalid staged quote's finding and exits 0; a valid staged quote is clean (subprocess test, skipped only when executables are absent).
- [ ] Hook configuration checks run without optional executables.
- [ ] All `TestRepoGate` findings, timeout, and execution-failure messages start with `GATE_FAILURE_LABEL` and are exercised in tests. Malformed JSON, unexpected exit codes, launch failures, invalid payload shapes, and inconsistent status/payload pairs cannot pass or escape unlabelled. Diagnoses remain distinct and make no unsupported claims about other tests or exclude verifier regressions.
- [ ] An uncaught verifier exception (exit 1, empty stdout) classifies as execution failure, not findings — covered by a named test.
- [ ] Gate classification is a pure helper tested without patching `subprocess.run`; any remaining `subprocess.run` patch dispatches on the command so `_fail_if_shallow_checkout` still reaches real git.
- [ ] `test_no_new_unverifiable_evidence` carries a per-test pytest timeout strictly greater than `GATE_TIMEOUT`, so the labelled `TimeoutExpired` branch fires before pytest-timeout kills the worker.
- [ ] A truncated findings list says so (`showing 20 of N`).
- [ ] The repo-wide gate still runs under the default `python -m pytest scripts/tests/` invocation.
- [ ] `docs/reference/CLI.md` `### ll-verify-evidence` **Gates:** line states that the hook now prints findings (`verbose: true`).
- [ ] `CONTRIBUTING.md` has an `ll-verify-evidence` hook section alongside the `ll-verify-decisions` one.

## Scope Boundaries

- **Non-goal: do not remove the repo-wide gate from the default suite or put it behind an excluded marker.** BUG-3442 showed this gate sitting structurally red in CI unnoticed; hooks can be bypassed or uninstalled; automation commits from worktrees. The suite is the only always-on enforcement.
- **Non-goal: flipping the hook to blocking** — sibling replay issue.
- **Non-goal: surfacing warn-only hook findings in ll-auto / ll-parallel run summaries.** No mechanism exists for it today.

## Related Key Documentation

- `docs/reference/CLI.md` — `### ll-verify-evidence` (Gates line, baseline vs verdict cache)
- `CONTRIBUTING.md` — pre-commit hook sections

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Verification Notes

Verdict at time of check: **PROPOSAL_UNSOUND** (AC-coverage gaps and missing backlink corrected in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

All referenced files, line numbers and code claims verified against the current tree; `ll-verify-evidence` reports no unverifiable quotes. Graph provider: codegraph (fresh) available; not needed.

- Backlink: ENH-3520 is `blocked_by: ENH-3518` but ENH-3518 lacked `blocks: [ENH-3520]` (MISSING_BACKLINK) — added.
- AC coverage: the `docs/reference/CLI.md` Gates-line update (Integration Map) had no acceptance criterion — added.

## Session Log
- `/ll:verify-issues` - 2026-09-20T01:36:17 - `58521fbd-d3a2-45c1-879f-6abf803572a3.jsonl`
- `/ll:wire-issue` - 2026-09-20T00:32:14 - `1b17328e-89d8-45f8-a318-abba67ffafef.jsonl`
- `/ll:refine-issue` - 2026-09-20T00:19:01 - `09e2af9d-eb90-432a-a570-962fb9c5f142.jsonl`
- `/ll:format-issue` - 2026-09-20T00:10:57 - `d0eb6446-04cf-4c6e-ada1-f1ab3056d581.jsonl`
