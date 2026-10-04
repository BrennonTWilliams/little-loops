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
confidence_score: 95
outcome_confidence: 78
score_complexity: 17
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3718: Live-evaluate reconcile-issue --from-verify-evidence DIRECTIVE_DRIFT repair

## Summary

Split out of BUG-3695 (EPIC-3694 children review, 2026-10-03). BUG-3695 landed the `--from-verify-evidence` carve-out (commit `8dbd00703`) and proved routing with scripted FSM tests (`scripts/tests/test_bug3695_directive_drift_repair.py`); scripted slash effects are not model behavior, so model compliance and convergence are still unmeasured.

This issue runs the repair path against a real model: three end-to-end `refine-to-ready-issue` loop runs on an AC-only drift fixture, plus direct `/ll:reconcile-issue --from-verify-evidence` calls for the fixture-only, context-only and VALID-with-stale-evidence boundary cases. It changes no production code. Never raise the reconcile budget (`check_reconcile_limit`, `target: 2`); investigate a failed replay or file a focused follow-up.

## Current Behavior

BUG-3695's repair path is covered only by scripted FSM tests (routing, evidence lifecycle, one-attempt budget). No run has shown a real model, given `--from-verify-evidence` and a `DIRECTIVE_DRIFT` finding, adding an entailed AC/Step without inventing requirements and converging within the one-reconcile budget.

## Expected Behavior

- Three independent live AC-only runs reach `VALID`/ready **because of the reconcile**, within the existing budget, or the failure is diagnosed.
- Fixture-only drift yields an Implementation Step and no invented AC.
- A context-only Tests/Documentation inventory yields no new requirement.
- A flagged reconcile with `verify_verdict: VALID` and stale drift evidence leaves ACs, Steps and the Integration Map unchanged.

## Motivation

Scripted effects cannot show model compliance, applicability churn, or incomplete first-pass B6 enumeration. Without live evidence BUG-3695's "converges in one reconcile" claim is unproven, and a failure would surface only as another 25-minute `GATE_UNMET` run.

## Proposed Solution

### Trial matrix

| ID | Mode | Fixture | Pass condition |
|----|------|---------|----------------|
| L1–L3 | `ll-loop run refine-to-ready-issue <ID>` (end-to-end) | AC-only drift, byte-identical copies | Attributed convergence (below), no invented requirement |
| D1–D2 | Direct flagged `/ll:reconcile-issue <ID> --from-verify-evidence` | Fixture-only drift with a frozen, real persisted `verify_evidence` | Adds an Implementation Step, no AC |
| D3–D4 | Direct flagged reconcile | Context-only Tests/Documentation inventory with frozen real evidence | Issue body unchanged, no requirement derived from the inventory |
| N1–N2 | Direct flagged reconcile | `verify_verdict: VALID` plus nonempty leftover `verify_evidence`, no contradictory research finding | ACs, Steps and Integration Map byte-unchanged (directive-section diff only; guard/session-log writes are not directive additions) |

Rationale for the direct-call decomposition: a context-only loop run never reaches reconcile if B6 is correct, so it measures B6 false positives, not model over-application. Do not run the normal child loop before N1–N2: its `clear_verify_verdict`/fresh-verify chain erases the input being evaluated. Optionally add one context-only *loop* run and report it separately as a B6 false-positive observation.

Frozen evidence for D/N cases: run the first `verify` once per fixture (through the pinned command source below), validity-gate it, then copy the persisted `verify_verdict`/`verify_evidence` into the pristine fixture bytes.

### Command-source guarantee (P0)

The effective model-executed command source is the **plugin cache**, not the working tree: `ll@little-loops` (user scope) points at `~/.claude/plugins/cache/little-loops/ll/1.166.0`, whose `reconcile-issue.md` has no `--from-verify-evidence` carve-out (working tree: 16 hits) and whose `verify-issues.md` lacks the updated B6/evidence persistence (2 vs 15 hits). The cached and working-tree `plugin.json` both say 1.166.0, so a version check cannot detect staleness.

Do **not** overwrite or symlink the shared cache (global mutation; every local-editable project is affected and a plugin update silently reverts it), do not add a `host_runner` hook (production code), and do not rely on project-level commands (wrong namespace). Recipe:

1. Build an immutable snapshot of the checkout at the batch SHA (>= `8dbd00703`) with `git archive` into the trial scratch area.
2. Put a trial-only `claude` shim first on `PATH` (`host_runner` resolves bare `claude` via PATH and passes no `--setting-sources`). The shim `exec`s the real CLI with `--plugin-dir <snapshot>`, and logs argv, snapshot SHA and `sha256(commands/reconcile-issue.md)` for every spawn; it also snapshots the issue file before and after each `/ll:` call.
3. In the throwaway project's project-scope Claude settings file set `{"enabledPlugins": {"ll@little-loops": false}}` so the cached plugin does not shadow the override.
4. **Preflight probe (load-bearing, not yet empirically tested):** run one trivial command through the shim and confirm the reconcile session loads the snapshot copy (a post-`8dbd00703`-only marker in the transcript, no `plugins/cache/little-loops` path). Abort the batch if the override does not take; fallback is a throwaway `CLAUDE_CONFIG_DIR` (auth/keychain caveats).
5. Per trial verify: the shim log covers every spawn and shows the snapshot hash; main-tree `HEAD` and `git status --porcelain` are unchanged for the batch (the loop YAML and `ll-issues` still come from the editable live tree, so "unchanged code" means no main-tree edits between trials). Run the `max_steps == 113` / `target: 2` pins before and after.

### Launch hygiene

- Launch with `env -i` and an explicit allowlist. A Claude session leaks `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PROJECT_DIR`, `CLAUDE_CONFIG_DIR`, `LL_AUTOMATION`, `LL_HOST_CLI`, `LL_HOOK_HOST` and `LL_HISTORY_DB` into descendants; an ambient `LL_HOST_CLI` silently changes the model family under test. Set `orchestration.host_cli` explicitly in the throwaway config.
- Create each throwaway project **outside** the repo (`mktemp -d`) so it cannot shadow `find_project_root`/git root. Layout follows `_setup_project` in `scripts/tests/autodev_harness.py` (`.ll/ll-config.json`, `.issues/` type dirs, `.gitignore` with `.loops/`, `git init` + initial commit). `run_refine_to_ready` is not reusable (it drives `ScriptedRunner`, not a model).
- Run detached (loop runs of ~20 iterations exceed the 10-minute Bash tool cap). Do not leave any fixture under `.issues/` or `scripts/tests/fixtures/issues/`.
- Without `LL_HISTORY_DB`, a throwaway project writes `loop_runs` rows to its own `.ll/history.db`; export `LL_HISTORY_DB` to a path inside the project to keep that explicit.
- Record the host CLI version, resolved model, batch SHA, and original fixture hash.

### Fixture hygiene

Each fixture is a synthetic issue over real code (cited source files committed in the throwaway project: `format-check` builds `ref_index` from `git ls-files`, so uncommitted cited files become `stale_file_ref` and spend the one format fallback). ID from a never-allocated number gap. Frontmatter opts out of unrelated gates: `testable: false`, `program_design_not_applicable: true`, `behavior_parity_not_applicable: true`. The body must never mention the missing AC/Step it is meant to elicit (contamination precedent: ENH-3258's session log).

Pre-flight so pre-verify states (`precheck_format`/`format_issue_pre`, `refine_issue`, `wire_issue`, `normalize_structure`) cannot repair or erase the drift:

- All `format-check` sections present; `refine-status` satisfied with **no `/ll:refine-issue` Session Log entries** beyond what is intended (only `/ll:refine-issue:gap-analysis` is exempt); no `decision_needed`, spike triggers, open questions or placeholders.
- No manual-verification phrases in ACs (`manually`, `by hand`, `verify by`, `visually confirm`): they would route `ACCEPTANCE_CRITERIA` first and spend the shared `refine-to-ready-reconcile-attempts` budget.
- Every claim about current code true and a Proposed Solution that is neither TBD nor boilerplate (B6 is skipped otherwise; drift verdicts rank below `NON_VALID`, `EVIDENCE_UNVERIFIED`, `CLAIMS_OUTDATED`, `PROPOSAL_UNSOUND`).
- Advisor disabled; confidence thresholds pinned (readiness 85, outcome 65): a reconcile rewrite clears scores, so `confidence_check` must regenerate them before `done`. `commands.max_refine_count` pinned; at the lifetime limit `check_lifetime_limit` diverts to `breakdown_issue`, which can decompose the fixture.
- Restore the full original fixture bytes (frontmatter, directives, research, scores, guard flags) before every independent trial; a fresh `run_dir` does not undo a prior model's edits.

### Validity gate (applies before any run is tabulated)

B6 is a judgment check, so a fixture only makes drift *likely*. A run counts only if all three hold:

1. Its first `verify_issue` persisted `DIRECTIVE_DRIFT` with the intended evidence kind (behavior/API drift for AC-only, fixture/mock invalidation for fixture-only).
2. The pre-verify snapshot (after `refine_issue`/`wire_issue`/`normalize_structure`) still lacks the entailed AC/Step. The wire-done marker is per `run_dir`, so each run repeats these states.
3. The refine budget (`refine-to-ready-refine-count`, shared by `check_refine_limit`, `check_hedge_refine_limit`, `check_gate_refine_limit`) was not consumed before the reconcile.

Otherwise discard as an invalid replay, say so in the results, and replace it; cap replacement replays at 3.

### Success definition and decision rule (pre-registered)

- **Attributed convergence (L runs):** success = the first verify after `reconcile_issue` returns no `DIRECTIVE_DRIFT` **and** no `refine_followup` ran after the reconcile. After the one-reconcile budget is spent, drift routes `check_gate_refine_limit` -> `refine_followup`, so a bare `final_state: done` may be refine's repair, not reconcile's.
- Terminal signals: `loop_complete` with `final_state: done`/`terminated_by: terminal` (success); `final_state: failed` via `record_gate_unmet`, echoing `[GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE]` only when the reconcile counter >= 1 and `ll-issues check-verify-verdict <ID> --directive-drift` exits 0 (failure). Iteration count = `loop_complete.iterations` (global step count, `max_steps: 113`).
- **Decision rule:** any invented requirement (AC/Step not entailed by the evidence, Integration Map addition, edit outside the permitted sections, or any directive change in N cases) = FAIL, zero tolerance. L runs: 3/3 attributed convergence = pass; 2/3 = conditional pass plus a focused follow-up; <= 1/3 = fail plus a focused follow-up bug. Never raise `target: 2`. n = 3 is a smoke test, not a rate estimate. Runs never stop early on a pass (N-sample stance, `docs/guides/EVALUATION_GUIDE.md`).
- **Failure classification** (record each separately, never as one mechanism): model over-application, incomplete first-pass B6 enumeration, applicability churn, infrastructure freshness (stale command source, failed clear), and downstream gate failures (`confidence_check`, proof, advise, decision, `breakdown_issue` diversion) that are unrelated to reconcile.

### Observation points and results placement

- Per-run artifacts: `<loops_dir>/runs/refine-to-ready-issue-<stamp>/` (`refine-to-ready-reconcile-attempts` counter, `run-records/refine-to-ready-issue/<ID>.json` with `evidence_refs` incl. `directive_drift_nonconvergence`), archive `<loops_dir>/.history/<started_at>-refine-to-ready-issue/` (`state.json`, `events.jsonl`; timestamp differs from the instance id by a timezone shift), `ll-loop history refine-to-ready-issue <run_id> --json`. The non-convergence marker has no consumer beyond tests and docs (`autodev_summary.py`/`preparation_policy.py` read only the `gate_unmet` token), so events/run record is the only observation point.
- Per L run record: final state, `loop_complete.iterations`, reconcile attempt count, the AC/Step diff against the pristine fixture, the re-verify verdict, whether the non-convergence line fired. Every cell traces to `events.jsonl` or the fixture diff.
- `ll-issues check-acceptance-criteria` is **not** a drift probe: it flags only manual-verification phrases and reads neither `verify_verdict` nor `verify_evidence`. Record its output as manual-phrase status only; coverage/convergence evidence is the re-verify verdict and final loop state.
- Results go into this issue as a short dated results block (verdict line, compact per-run table, caveats line naming n, single model family, judgment-based B6). Full run dirs and transcripts go into the gitignored postmortems directory (precedents: FEAT-3686, FEAT-3596, ENH-3520); `classify_file_ref` treats `postmortems/` as `untracked_by_design`, so backticked paths into it are safe. Copy run dirs there before deleting a throwaway project. Link any follow-up with `ll-issues link`.

Results block template:

```
### Results — <date> (batch SHA <sha>, host <cli version>, model <id>, command source <snapshot sha256>)
Verdict: <pass | conditional pass | fail>. Invalid replays discarded: <n>.
| Run | Fixture hash | First-verify evidence kind | Reconcile edits | Re-verify verdict | refine_followup after reconcile | Final state / iterations | Marker fired |
Caveats: n=3 same-fixture, one model family, B6 judgment-based.
```

## Integration Map

### Files to Modify
- None expected; findings are recorded in this issue. A failed replay may spawn a focused fix against `commands/verify-issues.md` (B6) or `commands/reconcile-issue.md`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `reconcile_issue` (only state carrying `--from-verify-evidence`), `check_reconcile_limit` (counter shared with the `ACCEPTANCE_CRITERIA` route), `check_gate_refine_limit`/`refine_followup`, `record_gate_unmet`; pre-verify states that can rewrite a fixture: `precheck_format`, `refine_issue`, `wire_issue`, `normalize_structure`; `check_lifetime_limit` -> `breakdown_issue`.
- `scripts/little_loops/cli/issues/next_obligation.py` — `_tier1_probe` yields `VERIFY:DIRECTIVE_DRIFT`/`ACCEPTANCE_CRITERIA` tokens; `check_verify_verdict.py` (`--directive-drift`, exit 3 = verdict absent) and `clear_verify_verdict.py` (removes `verify_verdict` and `verify_evidence`) back the evidence lifecycle. There is no evidence file: "evidence" is two frontmatter keys cleared before every re-verify.
- `scripts/little_loops/host_runner.py` — `resolve_host` precedence `LL_HOST_CLI` -> `LL_HOOK_HOST` -> `orchestration.host_cli`; no `--plugin-dir`/extra-args hook.
- `scripts/little_loops/session_store/db.py` — `_resolve_db_path`: `LL_HISTORY_DB`, then `history.db_path`, then `<project root>/.ll/history.db`.
- `~/.claude/plugins/cache/little-loops/ll/1.166.0/commands/` — the stale effective command source (see Command-source guarantee).

### Similar Patterns
- `scripts/tests/test_bug3695_directive_drift_repair.py` — scripted coverage this complements: pins `target: 2`, `max_steps == 113`, single-reconcile state order, evidence clearing and the non-convergence marker; `_drift`, `_scenario`, `AC_EVIDENCE`/`NEW_AC`, `FIXTURE_EVIDENCE`/`NEW_STEP` (ids `ac-only-drift`, `fixture-only-drift`, `ENH-9001`) are the scripted shapes the live fixtures mirror in evidence kind but must differ from in body. No existing test or fixture feeds a context-only inventory to a model.
- `scripts/tests/autodev_harness.py` — `_setup_project` layout; `DEFAULT_CONFIG` omits `orchestration.host_cli`, `tdd_mode`, `analytics`, `events.transports`.

### Tests
- None added; evaluation issue. Pins that must still pass before and after the batch: `max_steps == 113` (`test_builtin_loops.py`, `test_autodev_proof_reentry.py::test_max_steps_raised`, `test_advise_ready_gate.py::TestMaxStepsRaised.test_max_steps_113`), `check_reconcile_limit` `target: 2` (`test_builtin_loops.py::test_check_reconcile_limit_state_routing`), flag only on `reconcile_issue` (`test_builtin_loops.py::test_reconcile_issue_state_routing`).
- Real-tree sweeps read the working tree (`test_prose_dep_sweep_gate.py`, `test_symbol_cli_claim_sweep.py`, `test_research_triage.py::TestCorpusBaseline`, `test_caller_suitability_gate.py::TestFixtureLoopResidue`): keep all fixtures in the throwaway project.

### Documentation
- No doc edits needed. Cross-check references if a follow-up changes behavior: `docs/guides/LOOPS_REFERENCE.md` (`refine-to-ready-issue` entry), `docs/reference/COMMANDS.md` (`reconcile-issue`), `docs/reference/CLI.md` (`check-verify-verdict --directive-drift`), `docs/guides/EVALUATION_GUIDE.md` ("Reading the Signal").

### Contract under test
`commands/reconcile-issue.md`, "Source extension — `--from-verify-evidence`": eligibility requires the flag, `verify_verdict` exactly `DIRECTIVE_DRIFT`, and non-empty `verify_evidence`. When eligible, reconcile may add/rewrite ACs and Implementation Steps and correct existing Integration Map entries; it must not add Integration Map entries, edit other sections, edit the verdict/evidence keys, or append a parallel corrected block. Behavior/API drift maps to an AC, fixture/mock invalidation to an Implementation Step with no invented AC, context-only Tests/Documentation inventory to no requirement. The shared `ACCEPTANCE_CRITERIA` action can receive the flag with a VALID verdict, which makes it ineligible; that refusal is what N1–N2 measure.

## Implementation Steps

1. Build the throwaway-project scaffolding, the command-source shim and snapshot, and run the preflight probe; abort if the override does not load the snapshot command.
2. Author the AC-only, fixture-only, context-only and VALID-plus-stale fixtures per Fixture hygiene; preserve each pristine copy and record its hash.
3. Validity-gate each fixture's first verify; freeze the real persisted evidence for the D/N fixtures. Discard and replace invalid replays (max 3).
4. Run L1–L3, then D1–D4, then N1–N2, restoring pristine fixture bytes and rechecking the command source before every trial.
5. Apply the decision rule, classify any failure by mechanism, write the results block here, copy run dirs to postmortems, and file focused follow-ups for failures (never raise `check_reconcile_limit`).

## Impact

- **Priority**: P4 - evidence for an already-landed fix, not a defect
- **Effort**: Medium - shim/snapshot setup and preflight, four fixtures, three loop runs (~20 iterations each) plus six direct reconcile calls, validity gating and write-up; model cost is nondeterministic, budget for replay replacements (cap 3)
- **Risk**: Low - model edits are isolated to restored throwaway fixtures; the shim leaves the shared plugin cache untouched

## Acceptance Criteria

- [ ] Command-source preflight passes and every trial's shim log shows the post-`8dbd00703` snapshot hash; main-tree HEAD/porcelain unchanged across the batch
- [ ] Three validity-gated live AC-only runs recorded with verdicts, edits, iteration counts and attributed convergence (no `refine_followup` after the reconcile), judged under the pre-registered decision rule
- [ ] Fixture-only direct calls add a Step and no invented AC; context-only direct calls add no requirement
- [ ] Live flagged reconcile with VALID and stale drift evidence leaves ACs/Steps/Integration Map unchanged
- [ ] Any failed or invalid replay is classified by mechanism, investigated or given a focused follow-up; the reconcile budget is not raised

## Scope Boundaries

- Out of scope: changing `check_reconcile_limit`, adding a fallback budget, a fail-closed clear/write protocol, any `host_runner` change, and modifying the shared plugin cache.
- Known infrastructure limitation: `clear_verify_verdict` suppresses failures with `|| true`; if it fails and verify writes nothing, stale verdict/evidence can survive. N1–N2 test the model's non-drift eligibility boundary, not that path. ENH-3718 records the limitation only; if live evaluation reproduces stale-evidence consumption after a failed clear, capture a focused freshness bug with its run evidence rather than absorbing the repair here or into BUG-3695.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-03 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-10-04T01:22:45 - `f2e174fa-5ec3-4454-9200-0aad0174f7ba.jsonl`
- `/ll:confidence-check` - 2026-10-04T01:15:00 - `1c366066-f38d-406f-a03b-834e727c34ea.jsonl`
- Review - 2026-10-04 - `/ll:advise` with Opus (confidence 0.80): NO-GO as written, GO after doc-only edits. Added the command-source shim/snapshot recipe with preflight, attributed-convergence success definition and pre-registered decision rule, three-part validity gate with replay cap, direct-call redesign of fixture-only/context-only/stale-evidence cases, launch/fixture hygiene; consolidated the stacked research/wiring blocks (kept wiring corrections for history DB and postmortems paths; dropped the stale `.running` claim, which is `completed`), narrowed the BUG-3695 handoff, effort Small -> Medium.
- `/ll:confidence-check` - 2026-10-04T00:45:05 - `1f4ee23d-eb5f-434e-8716-2e767906926a.jsonl`
- `/ll:wire-issue` - 2026-10-04T00:42:05 - `36756883-95b1-4883-8685-67496417190f.jsonl`
- Review - 2026-10-03 - Added Opus-recommended live ineligible-flag/stale-evidence case (confidence 0.80), pristine-fixture restoration and effective command-source verification; corrected the evaluation's read-only claim. Model compliance remains unmeasured until these trials run.
- `/ll:refine-issue` - 2026-10-04T00:33:49 - `f72c0733-ceb4-48d1-a8a7-ed6430bdb144.jsonl`
- `/ll:capture-issue` - 2026-10-03T23:00:35 - `c4c6a704-e666-48df-b6fe-37ff869c1bae.jsonl`
