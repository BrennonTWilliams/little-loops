---
id: ENH-3718
type: ENH
title: Live-evaluate reconcile-issue --from-verify-evidence DIRECTIVE_DRIFT repair
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T23:00:17Z'
parent: EPIC-3694
relates_to:
- BUG-3695
program_design_not_applicable: true
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 78
score_complexity: 17
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3718: Live-evaluate reconcile-issue --from-verify-evidence DIRECTIVE_DRIFT repair

## Summary

Split out of BUG-3695 (EPIC-3694 children review, 2026-10-03). BUG-3695 landed the `--from-verify-evidence` carve-out and proved routing with scripted FSM tests (`scripts/tests/test_bug3695_directive_drift_repair.py`); scripted slash effects are not model behavior, so model compliance and convergence are still unmeasured.

Evaluate three independent `refine-to-ready-issue` runs from an identical fresh fixture reproducing AC-only check-B6 drift (ENH-3678 has since changed, so build a new fixture), each with a fresh run_dir, unchanged code and the current one-reconcile budget (`check_reconcile_limit`, `target: 2`). Record findings, AC/Step edits, AC-checker output, verdicts and iteration counts reaching VALID/ready.

Also evaluate a fixture-only drift case (expects an Implementation Step, no invented AC) and an irrelevant Tests/Documentation inventory (must create no requirement).

Add one direct live `/ll:reconcile-issue <fixture> --from-verify-evidence` invocation with `verify_verdict: VALID` and nonempty leftover drift evidence. With no contradictory research finding, the model must leave ACs, Steps and Integration Map unchanged. Do not run the normal child first for this case: its clear/fresh-verify chain would erase the input being evaluated. The shared `ACCEPTANCE_CRITERIA` action can receive this flag/evidence combination, but the verdict makes it ineligible; scripted routing tests do not prove the model obeys that boundary.

Investigate any failed replay or file a focused follow-up; never automatically raise the reconcile budget.


## Current Behavior

BUG-3695's repair path is covered only by scripted FSM tests (routing, evidence lifecycle, one-attempt budget). No run has shown a real model, given the `/ll:reconcile-issue` flag `--from-verify-evidence` and a `DIRECTIVE_DRIFT` finding, adding an entailed AC/Step without inventing requirements, and converging within the one-reconcile budget.

## Expected Behavior

Three independent live runs from an identical AC-only drift fixture reach `VALID`/ready within the existing budget, or the failure is diagnosed. Fixture-only drift yields an Implementation Step with no invented AC, an irrelevant Tests/Documentation inventory yields no new requirement, and flagged reconciliation with a non-drift verdict ignores stale drift evidence.

## Motivation

Scripted effects cannot show model compliance, applicability churn, or incomplete first-pass B6 enumeration. Without live evidence, BUG-3695's "converges in one reconcile" claim is unproven and a failure would surface only as another 25-minute `GATE_UNMET` run.

## Proposed Solution

Build a fresh AC-only drift fixture (ENH-3678 has since changed), run `ll-loop run refine-to-ready-issue <fixture>` three times with a fresh run_dir each and unchanged code, then repeat once each for fixture-only drift and a context-only inventory. Add the direct ineligible-flag/stale-evidence invocation described above. Restore the full original issue bytes before each independent trial, including frontmatter, directives, research, scores and guard flags; a fresh run_dir alone does not undo a prior model's edits. Record the original fixture hash, chosen host/model, effective command source, per-run findings, AC/Step edits, `check-acceptance-criteria` output, verdicts, iteration counts and whether the `[GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE]` line fired. The host must load the updated command source from `8dbd00703` or later, rather than an older cached plugin. Record directive-section diffs for the negative invocation; permissible guard/session-log writes are not directive additions. Write results into this issue; do not raise `check_reconcile_limit`'s target.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **Fixture validity is a precondition, not an outcome.** Each fixture is a synthetic issue over real code, ID chosen from a never-allocated number gap, with frontmatter that opts out of unrelated gates (`testable: false`, `program_design_not_applicable: true`, `behavior_parity_not_applicable: true`) and a body that never mentions the missing AC/Step it is meant to elicit. A fixture that already carries the correct answer shows "did not regress", not "the repair fired" (contamination precedent: ENH-3258's session log). Before counting a run, confirm its first `verify_issue` persisted `DIRECTIVE_DRIFT` with the intended evidence kind; otherwise discard it as an invalid replay and say so.
- **Independence**: three runs from a byte-identical fixture copy, each in a fresh throwaway project (or at minimum a fresh fixture copy with a reset issue tree) so `run_dir`, counter files and prior Session Log entries cannot leak. Runs never stop early on a pass (same stance as the N-sample rule in `docs/guides/EVALUATION_GUIDE.md`), and the model, host CLI version and repo commit are pinned in the results block.
- **Results placement**: this repo's convention for evaluation issues is a short dated results block in the issue (verdict line, compact per-run table, caveats line naming n, single model family) with full run dirs and transcripts in the gitignored postmortems directory (precedents: FEAT-3686, FEAT-3596, ENH-3520); ENH-3258 instead recorded fixture validation in Session Log bullets. The two destinations disagree and either is in force. Because the postmortems directory is untracked, `ll-issues format-check` treats a backticked path into it as a stale file reference — cite it as a bare directory name in prose.
- **Failure handling**: a run ending in `[GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE]` is a finding, to be diagnosed (incomplete first-pass B6 enumeration, applicability churn, or an ineffective repair, per BUG-3695's budget notes) or filed as a focused follow-up against B6 or `commands/reconcile-issue.md`. `check_reconcile_limit`'s `target: 2` is not an adjustable variable in this evaluation.

## Integration Map

### Files to Modify
- None expected; findings are recorded in this issue. A failed replay may spawn a focused fix against `commands/verify-issues.md` (B6) or `commands/reconcile-issue.md`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `reconcile_issue`, `check_reconcile_limit`, `record_gate_unmet`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — states that run **before** the first drift route and can rewrite the fixture: `precheck_format` (may run `format_issue_pre`), `refine_issue` (`/ll:refine-issue --auto`), `wire_issue`, `normalize_structure` (`format-check --fix --apply`). They can add ACs/Integration Map entries that pre-empt the drift the fixture was built to elicit; `check_lifetime_limit` at `commands.max_refine_count` (default 5) diverts to `breakdown_issue`, which can decompose the fixture into new issue files [Agent 2 finding]
- `scripts/little_loops/cli/issues/next_obligation.py` — `_tier1_probe` yields the `VERIFY:DIRECTIVE_DRIFT` / `ACCEPTANCE_CRITERIA` tokens `route_pre_score_obligation` routes on; `scripts/little_loops/cli/issues/check_verify_verdict.py` (`--directive-drift`, exit 3 = verdict absent) and `clear_verify_verdict.py` (removes both `verify_verdict` and `verify_evidence`) back the evidence lifecycle the run is read from [Agent 1 finding]
- `scripts/little_loops/autodev_summary.py` — `_GATE_UNMET_SKIPPED_REASONS` and `preparation_policy.py` (`evidence_refs` pass-through) consume only the `gate_unmet` token, never the `DIRECTIVE_DRIFT_NON_CONVERGENCE` marker; the marker and `directive_drift_nonconvergence` ref have no consumer beyond tests and docs, so reading them out of `events.jsonl`/the run record is the only observation point [Agent 2 finding]
- `scripts/little_loops/session_store/db.py` — `_resolve_db_path` resolves `LL_HISTORY_DB`, then `history.db_path`, then `<project root>/.ll/history.db`: a throwaway project writes `loop_runs` rows to **its own** `.ll/history.db` unless `LL_HISTORY_DB` is exported (corrects the "shared history DB" assumption in Codebase Research Findings above) [Agent 2 finding]
- `scripts/little_loops/host_runner.py` — `resolve_host` precedence `LL_HOST_CLI` → `LL_HOOK_HOST` → `orchestration.host_cli`; an ambient value silently changes the model family under test. The harness's `run_refine_to_ready` strips these, a live `ll-loop run` does not [Agent 2 finding]
- `~/.claude/plugins/cache/little-loops/ll/1.166.0/commands/reconcile-issue.md` (and `verify-issues.md`) — **effective model-executed command source is the plugin cache, not this working tree.** The cached `reconcile-issue.md` has no `--from-verify-evidence`/`DIRECTIVE_DRIFT` carve-out (working tree: 5 hits) and the cached `verify-issues.md` lacks the `verify_evidence` persistence and updated B6. Editable install makes the Python CLIs live but not the slash-command prose, so unmodified, all three AC-only runs would exercise a command that cannot do the repair [Agent 2 finding]
- `.loops/.running/refine-to-ready-issue-20261003T182725.state.json` — a loop run with `input: ENH-3718` is recorded as `running` in the main tree (state `wire_issue`, last updated 2026-10-04T00:34Z); confirm it is dead before editing this file or counting any run [Agent 2 finding]
- `.issues/epics/P3-EPIC-3694-autodev-gate-and-citation-false-failure-hardening.md`, `.issues/bugs/P3-BUG-3695-refine-to-ready-issue-directive_drift-cannot-be-remedied-reconcile-issue-cannot-add-acceptance-criteria.md` — scope drift: EPIC-3694 describes ENH-3718 as "five isolated loop trials plus a direct live non-drift/stale-evidence eligibility case; restore pristine fixtures and verify the effective command source between trials", and BUG-3695 (acceptance bullet ~line 202, ~line 219) hands the VALID-with-stale-evidence refusal and the failed-clear/no-write limitation to ENH-3718. This issue's body has neither; reconcile before closing [Agent 2 finding]

### Similar Patterns
- `scripts/tests/test_bug3695_directive_drift_repair.py` — the scripted routing coverage this complements

### Tests
- None added; this is an evaluation issue.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/autodev_harness.py` — `_setup_project(root, scenario)` is the layout to copy for the throwaway project (`DEFAULT_CONFIG` + `.ll/ll-config.json`, `.issues/` type dirs, `write_issue`, `extra_issues`, `Scenario.project_files`, `.gitignore` with `.loops/`, `git init` + `init` commit). `run_refine_to_ready` is **not** reusable — it drives `ScriptedRunner`, not a model. `DEFAULT_CONFIG` omits `orchestration.host_cli`, `tdd_mode`, `analytics`, `events.transports`; set `host_cli` explicitly [Agent 2/3 finding]
- `scripts/tests/test_bug3695_directive_drift_repair.py` — `_drift(evidence)`, `_scenario(verify, reconcile)`, `AC_EVIDENCE`/`NEW_AC`, `FIXTURE_EVIDENCE`/`NEW_STEP` (ids `ac-only-drift`, `fixture-only-drift`, issue `ENH-9001`) are the scripted shapes the live fixtures mirror in evidence kind but must differ from in body: the live body must not already contain `NEW_AC`/`NEW_STEP`. `TestRecordGateUnmetSignalIsScoped._run` is the pattern for probing the `record_gate_unmet` action in real bash [Agent 3 finding]
- Pins that must still pass before and after the batch (unchanged-code evidence; none are expected to break): `max_steps == 113` (`test_builtin_loops.py:1884`, `test_autodev_proof_reentry.py::test_max_steps_raised`, `test_advise_ready_gate.py::TestMaxStepsRaised.test_max_steps_113`), `check_reconcile_limit` `target: 2` (`test_builtin_loops.py::test_check_reconcile_limit_state_routing`), flag only on `reconcile_issue` (`test_builtin_loops.py::test_reconcile_issue_state_routing`) [Agent 3 finding]
- `scripts/tests/test_caller_suitability_gate.py` — `TestFixtureLoopResidue.test_no_staged_fixture_residue` is the precedent for guarding a fixture ID against leaking into the real `.issues/` tree (ENH-288 + `.gitignore` entry). Real-tree sweeps read the working tree: `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo`, `test_symbol_cli_claim_sweep.py::test_symbol_and_cli_flag_claim_sweep_report_only` (ceilings 2 / 5), `test_research_triage.py::TestCorpusBaseline`. Keep all fixtures in the throwaway project; do not leave one under `.issues/` or `scripts/tests/fixtures/issues/` [Agent 3 finding]
- No existing test or fixture feeds a context-only Tests/Documentation inventory to a model; the live fixture is net-new (confirmed by search of `scripts/tests/` for `context-only`, `DIRECTIVE_DRIFT`, `from-verify-evidence`) [Agent 3 finding]

### Documentation
- None.

_Wiring pass added by `/ll:wire-issue`:_
- No doc edits needed (evaluation only). Docs describing the path under test, for reference/cross-check if a follow-up changes behavior: `docs/guides/LOOPS_REFERENCE.md` (`refine-to-ready-issue` entry, ~line 195: flagged reconcile, one-reconcile budget, `DIRECTIVE_DRIFT_NON_CONVERGENCE`, `directive_drift_nonconvergence`), `docs/reference/COMMANDS.md` (`reconcile-issue`, ~line 305), `docs/reference/CLI.md` (`check-verify-verdict --directive-drift`). Methodology reference for results: `docs/guides/EVALUATION_GUIDE.md` ("Reading the Signal": N-sample, no early stop) [Agent 1/2 finding]
- Results citation correction: `text_utils.classify_file_ref` returns `untracked_by_design` (not `stale`) for slash-qualified refs under `DEFAULT_UNTRACKED_BY_DESIGN` prefixes (`postmortems/`, `thoughts/`, `logs/`, `.loops/runs/`, `.loops/.history/`, `.loops/.running/`, `.loops/tmp/`, `.loops/diagnostics/`), and `check_format_gaps` only flags status `stale`. So backticked `postmortems/…` paths are safe under the default config; other untracked paths (e.g. other `.ll/` or `.loops/` subdirs) still raise blocking `stale_file_ref` [Agent 2 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `.ll/ll-config.json` (throwaway project, not this repo) — set `orchestration.host_cli` and `commands.confidence_gate.{readiness,outcome}_threshold` (needs readiness ≥ 85, outcome ≥ 65 after a reconcile rewrite clears scores) and `commands.max_refine_count`; a `history.db_path`/`LL_HISTORY_DB` choice decides whether `loop_runs` rows hit the shared DB [Agent 2 finding]
- Frontmatter opt-outs for fixtures: `program_design_not_applicable: true` (`issues/program_design.py`), `behavior_parity_not_applicable: true` (checked only when a `ref_index` exists, `issue_parser.py`), `testable: false` (advisory, `_ADVISORY_GAP_CLASSES`) [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **Repair path under test** (`scripts/little_loops/loops/refine-to-ready-issue.yaml`): `verify_issue` persists `verify_verdict` and `verify_evidence` to the issue's frontmatter; `route_pre_score_obligation` (via `ll-issues next-obligation`) maps `VERIFY:DIRECTIVE_DRIFT` and `ACCEPTANCE_CRITERIA` to `check_reconcile_limit`; `reconcile_issue` is the only state whose action carries `--from-verify-evidence`. There is no evidence file — the "evidence" is two frontmatter keys, cleared by `clear_verify_verdict` before every re-verify.
- **Budget semantics**: `check_reconcile_limit` increments `refine-to-ready-reconcile-attempts` (seeded to 0 by `resolve_issue` in `${context.run_dir}`) and tests `lt target: 2`, so exactly one reconcile is admitted per run. The counter is shared with the `ACCEPTANCE_CRITERIA` route, so an AC-obligation reconcile earlier in a run consumes the same budget. A second entry routes to `check_gate_refine_limit`, whose `refine-to-ready-refine-count` is shared with `check_refine_limit` and `check_hedge_refine_limit`; an earlier `refine_followup` therefore shortens the post-reconcile retry path.
- **Terminal signals to record**: success = `loop_complete` with `final_state: done` and `terminated_by: terminal`; failure = `final_state: failed` via `record_gate_unmet`, which echoes `[GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE]` only when the reconcile counter is >= 1 **and** `ll-issues check-verify-verdict <ID> --directive-drift` exits 0. The run record's legacy class stays `gate_unmet`; the marker lives in the echoed line and the record's `evidence_refs` (`directive_drift_nonconvergence`). Iteration count = `loop_complete.iterations` (global step count, `max_steps: 113`), not `iteration_count`.
- **Where artifacts land**: `<loops_dir>/runs/refine-to-ready-issue-<stamp>/` (per-run counters, `run-records/refine-to-ready-issue/<ID>.json`), live state in `<loops_dir>/.running/`, archive in `<loops_dir>/.history/<started_at>-refine-to-ready-issue/` (`state.json`, `events.jsonl`). The history-dir timestamp differs from the instance id by a timezone shift. `ll-loop history refine-to-ready-issue [run_id] --json` reads the archive.
- **Fixture constraints from B6** (`commands/verify-issues.md`, check B6): drift verdicts rank below `NON_VALID`, `EVIDENCE_UNVERIFIED`, `CLAIMS_OUTDATED` and `PROPOSAL_UNSOUND`, so a drift fixture must have every claim about current code true and a Proposed Solution that is neither TBD nor boilerplate (B6 is skipped otherwise). B6 is a judgment check, not a deterministic probe — the fixture can only make drift *likely*, so a run whose first verify does not yield `DIRECTIVE_DRIFT` is an invalid replay, not a pass or a fail.
- **Contract the live runs check** (`commands/reconcile-issue.md`, "Source extension — `--from-verify-evidence`"): eligibility requires the flag, `verify_verdict` exactly `DIRECTIVE_DRIFT`, and non-empty `verify_evidence`. When eligible, reconcile may add/rewrite ACs and Implementation Steps and correct existing Integration Map entries; it must not add Integration Map entries, edit other sections, edit the verdict/evidence keys, or append a parallel corrected block. Behavior/API drift maps to an AC, fixture/mock invalidation to an Implementation Step with no invented AC, and context-only Tests/Documentation inventory to no requirement. A rewrite also clears confidence scores, so `confidence_check` must regenerate them before `done`.
- **`ll-issues check-acceptance-criteria` is not a drift probe** (`scripts/little_loops/cli/issues/check_acceptance_criteria.py`): it only flags checkbox ACs matching a manual-verification phrase list (`temporarily`, `manually`, `by hand`, `verify by`, `visually confirm`, `check that … looks`), reads neither `verify_verdict` nor `verify_evidence`, and exits 0 on any AC set free of those phrases. The loop reaches it only through `next-obligation`, after the VERIFY tier. "AC-checker output" in this issue's acceptance criteria therefore means manual-phrase status; coverage/convergence is evidenced by the re-verify verdict and the final loop state.
- **Invocation and isolation**: `ll-loop run refine-to-ready-issue <ID>` accepts only `NNN`, `TYPE-NNN` or `P<n>-TYPE-NNN` — not a file path (`resolve_issue_path` in `scripts/little_loops/issue_parser.py`). All paths derive from the cwd, so a throwaway git project (`.ll/ll-config.json`, `.issues/{bugs,features,enhancements,epics}/`, an initial commit, `.loops/` gitignored — the shape built by `_setup_project` in `scripts/tests/autodev_harness.py`) isolates the issue tree and run state; the built-in loop resolves without installing it there. `loop_runs`/usage rows still go to the shared history DB.
- **Editable-install hazard**: every little-loops project here is `local-editable` against this checkout, so "unchanged code" means the main-tree working tree is not edited between the three runs; record the commit SHA and `git status` cleanliness once per batch. The harness helper `run_refine_to_ready` pins `PYTHONPATH` and strips `LL_AUTOMATION`, `LL_HOST_CLI` and `LL_HOOK_HOST`; a live run launched from an automation context inherits those ambient variables unless they are unset.
- **Scripted coverage this complements** (`scripts/tests/test_bug3695_directive_drift_repair.py`): pins `target: 2`, `max_steps == 113`, the single-reconcile state order, evidence clearing, and the non-convergence marker with the `ac-only-drift` and `fixture-only-drift` scenarios. No test or fixture anywhere feeds a context-only Tests/Documentation inventory to a model; the context-only case in this issue has no prior fixture to reuse.

## Implementation Steps

1. Create the fresh AC-only drift fixture, fixture-only/context-only variants, and a VALID-plus-stale-evidence fixture with no contradictory findings. Preserve each pristine fixture and record its hash, host/model and effective command source.
2. Run three independent live runs of the AC-only fixture; capture run dirs, verdicts, edits, AC-checker output and iteration counts.
3. Run the fixture-only and context-only variants once each.
4. Run the direct flagged reconcile against the ineligible VALID fixture; assert ACs/Steps/Integration Map remain unchanged despite the leftover evidence. Restore fixture bytes before every independent trial.
5. Record results and limitations here; investigate failures or capture focused follow-ups. Record separately whether a failure reflects model over-application, incomplete B6 enumeration or infrastructure freshness, rather than treating them as the same mechanism.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- Constraint on ordering: fixtures must be validated (first verify yields intended `DIRECTIVE_DRIFT` evidence) before any run is tabulated; the five runs themselves have no forced order, but the three AC-only runs must share one commit SHA and an unedited main tree.
- Outcome per AC-only run: final state, `loop_complete.iterations`, reconcile attempt count, the AC/Step diff reconcile produced (diffable against the fixture copy), the re-verify verdict, and whether a `[GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE]` line fired. Verification: every cell traces to `events.jsonl` in the run's archive or to the fixture diff.
- Outcome for the fixture-only run: the diff adds an Implementation Step addressing the fixture/mock invalidation and adds no AC. Outcome for the context-only run: the issue body is unchanged by reconcile (or the verify verdict is `VALID` without a reconcile) and no requirement derived from the inventory appears.
- Outcome: results block written per the placement convention above, with a caveats line (n = 3 same-fixture runs, one model family, B6 is judgment-based so one fixture does not generalise) and any follow-up issue linked via `ll-issues link`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the evaluation setup:_

- Verify the effective command source before any run: diff `~/.claude/plugins/cache/little-loops/ll/1.166.0/commands/reconcile-issue.md` and `verify-issues.md` against the working tree; if the cache lacks the `--from-verify-evidence` carve-out / B6 evidence persistence, refresh or point the plugin at this checkout and record the resolved path and `gitCommitSha` in the results block. Re-check between trials (EPIC-3694 requirement)
- Build every fixture in a throwaway git project (copy of `_setup_project` layout), committing the real source files the fixture cites (`Scenario.project_files` pattern) — `format-check` builds `ref_index` from `git ls-files`, so uncommitted/absent cited code classifies as `stale_file_ref` and sends `normalize_structure` to `format_issue_post`, spending the one format fallback
- Pre-flight each fixture so the loop's pre-verify rewrites cannot erase the drift: write the fixture with all `format-check` sections, `refine-status` satisfied (no Session Log `/ll:refine-issue` entries beyond what is intended — only `/ll:refine-issue:gap-analysis` is exempt), no `decision_needed`, no manual-verification phrases in ACs (`manually`, `verify by`, … would spend the shared `refine-to-ready-reconcile-attempts` budget on the `ACCEPTANCE_CRITERIA` route first), and no open questions/placeholders (hedge/refine budget is shared with `check_refine_limit`)
- Launch each run with a clean environment: `unset LL_AUTOMATION LL_HOST_CLI LL_HOOK_HOST` (or set deliberately), export `LL_HISTORY_DB` to a path inside the throwaway project, and record resolved model and host CLI version
- Record the commit SHA and `git status` cleanliness of the main tree once per batch; run the `max_steps == 113` / `target: 2` pins before and after to prove "unchanged code"
- Capture per run, from the archive (`ll-loop history refine-to-ready-issue <run_id> --json` and `<loops_dir>/.history/…/events.jsonl`) plus `<loops_dir>/runs/<instance>/refine-to-ready-reconcile-attempts` and `run-records/refine-to-ready-issue/<ID>.json` `evidence_refs`; diff the final issue against the byte-identical fixture copy; copy run dirs into the postmortems directory before deleting the throwaway project
- Add the two cases EPIC-3694/BUG-3695 assign to this issue, or explicitly move them to a follow-up and remove them from those issues: VALID verdict with stale `verify_evidence` (reconcile must refuse to add directives) and the failed-clear/no-write limitation
- Confirm no loop run on ENH-3718 is still `running` in the main tree's `.loops/.running/` before editing this file or tabulating runs

## Impact

- **Priority**: P4 - evidence for an already-landed fix, not a defect
- **Effort**: Small - five loop runs and one direct live negative invocation plus write-up
- **Risk**: Low - model edits are isolated to restored throwaway fixtures

## Acceptance Criteria

- [ ] Three live AC-only-drift runs are recorded with verdicts, edits, checker output and iteration counts
- [ ] Fixture-only drift adds a Step and no invented AC; a context-only inventory adds no requirement
- [ ] A live flagged reconciliation with VALID and stale drift evidence leaves ACs/Steps/Integration Map unchanged; fixture hashes and host/model/command source confirm independent trials use the landed command
- [ ] Any failed replay is investigated or has a focused follow-up; the reconcile budget is not raised

## Scope Boundaries

- Out of scope: changing `check_reconcile_limit`, adding a fallback budget, or a fail-closed clear/write protocol.
- Known infrastructure limitation: `clear_verify_verdict` suppresses failures with `|| true`; if it fails and verify writes nothing, stale verdict/evidence can survive. The negative case tests the model's non-drift eligibility boundary, not that clear/write failure path. If live evaluation reproduces stale evidence consumption after a failed clear, capture a focused freshness bug with its run evidence; do not absorb that infrastructure repair into this evaluation or BUG-3695.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-03 | Priority: P4

## Session Log
- `/ll:confidence-check` - 2026-10-04T00:45:05 - `1f4ee23d-eb5f-434e-8716-2e767906926a.jsonl`
- `/ll:wire-issue` - 2026-10-04T00:42:05 - `36756883-95b1-4883-8685-67496417190f.jsonl`
- Review - 2026-10-03 - Added Opus-recommended live ineligible-flag/stale-evidence case (confidence 0.80), pristine-fixture restoration and effective command-source verification; corrected the evaluation's read-only claim. Model compliance remains unmeasured until these trials run.
- `/ll:refine-issue` - 2026-10-04T00:33:49 - `f72c0733-ceb4-48d1-a8a7-ed6430bdb144.jsonl`
- `/ll:capture-issue` - 2026-10-03T23:00:35 - `c4c6a704-e666-48df-b6fe-37ff869c1bae.jsonl`
