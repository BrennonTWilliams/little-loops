---
id: BUG-3753
type: BUG
title: verify-issues --from-evidence re-introduces the stale claim it corrects via
  a verbatim Verification Notes quote
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-06'
captured_at: '2026-10-06T01:01:37Z'
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3753: verify-issues --from-evidence re-introduces the stale claim it corrects via a verbatim Verification Notes quote

## Summary

`/ll:verify-issues --from-evidence` (the `correct_claims` state of `refine-to-ready-issue`) repairs a stale claim in place, then writes a `## Verification Notes` entry that quotes the stale token verbatim. `ll-issues format-check` scans that note, so the follow-up `--check` flags the same finding again. The one-attempt claim-correction budget is already spent, so the loop routes to `record_gate_unmet` and fails.

## Current Behavior

Observed in run `refine-to-ready-issue-20261005T180418` on ENH-3742 (23 iterations, failed):

1. First `--check` returned `CLAIMS_OUTDATED`: a slash-joined shorthand for several file names in a Tests bullet was read as a nonexistent path (`stale_file_ref`).
2. `correct_claims` rewrote the bullet correctly, then wrote a Verification Notes entry that quoted the original slash-joined token verbatim.
3. The second `--check` flagged that note as the same `stale_file_ref`; its `verify_evidence` named the Verification Notes quote.
4. `check_claim_correction_budget` (counter `lt 2`, one attempt per run) was exhausted, so the run ended `failed` with `gate_unmet`.

## Expected Behavior

A correction pass never leaves behind a note that re-triggers the finding it fixed: notes paraphrase stale citations, and the pass confirms `ll-issues format-check <ID>` is clean of findings it introduced before finishing.

## Steps to Reproduce

1. Take an issue whose Tests bullet uses a slash-joined shorthand for several file names (ENH-3742 at the time of the run).
2. Run `ll-loop run refine-to-ready-issue` on it; the first `--check` returns `CLAIMS_OUTDATED` (`stale_file_ref`).
3. `correct_claims` runs `/ll:verify-issues --from-evidence`, rewrites the bullet, and writes a `## Verification Notes` entry quoting the original token.
4. The second `--check` flags that note with the same `stale_file_ref`; `check_claim_correction_budget` is exhausted and the loop ends `failed` / `gate_unmet`.

## Motivation

A single self-inflicted finding is terminal for the whole `refine-to-ready-issue` run: the claim-correction budget allows one attempt, so a 23-iteration run is lost to a note the correction pass itself wrote. The failure depends on model compliance with an unwritten rule, which is the kind of defect that recurs silently across every consuming project that runs the loop.

## Proposed Solution

Already applied in the working tree (uncommitted):

- `commands/verify-issues.md`: new paragraph "Verification Notes must not re-introduce the finding" before §4.1 (paraphrase, never quote; post-write `format-check`, reword and re-run until clean, also under `--from-evidence`), plus a clarifying comment at the `FROM_EVIDENCE` flag parse.
- Host mirrors regenerated with `ll-adapt --host <gemini|kimi-code|qwen> --apply`.
- ENH-3742's offending note reworded by hand and its stale verdict cleared.

Optional follow-ups:

- Loop- or CLI-level guard so this cannot depend on model compliance: a deterministic `format-check` state after `correct_claims`, or have `format-check` ignore or limit citation tokens inside `## Verification Notes`.
- Regression test asserting the verify-issues command text contains the paraphrase and post-write-check rule.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- Status correction: the command-text rule is no longer uncommitted — it landed in `310db44bb` (`docs(verify-issues): clarify verification notes must not re-introduce findings`), and the paragraph is present at `commands/verify-issues.md:567` and in the gemini/qwen/kimi-code mirrors. The remaining open work is the regression test (AC 2) and the optional deterministic guard; AC 1/3 depend on the guard decision.
- Constraint on the guard choice: the rule currently depends on model compliance, and `normalize_structure` cannot catch a regression because it reads only `directive_gaps` from `format-check --format json`, not `stale_file_ref`. Whichever route is taken (a post-`correct_claims` probe state, or narrowing `check_format_gaps`), it must let a genuinely stale citation outside `## Verification Notes` still block, and the claim-correction budget (one attempt per run) must not be spent by a note the pass itself wrote.

## Integration Map

### Files to Modify
- `commands/verify-issues.md` - paraphrase-not-quote rule and post-write `format-check` (already applied, commit 310db44bb)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` - optional deterministic `format-check` state after `correct_claims`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — if the loop-guard option is taken: `correct_claims` (`next: normalize_structure`, `on_error: normalize_structure`) is the only edge to re-route, and the new state's own `on_yes`/`on_no`/`on_error` must route to `normalize_structure` or `clear_verify_verdict`; also update the header routing comment (`VERIFY:CLAIMS_OUTDATED` bullet) and the `max_steps` history comment [Agent 2 finding]
- `scripts/little_loops/issue_parser.py` — if the scan-scoping option is taken: add the section filter inside `check_format_gaps` at the `classify_issue_refs(content, ref_index)` call (`:1297`, whole-file legacy `stale_file_ref` scan), not inside the shared `classify_issue_refs`/`extract_file_paths` in `text_utils.py`; `## Verification Notes` appears nowhere under `scripts/little_loops/` today, so there is no existing carve-out to adjust [Agent 1, 2, 3 findings]
- `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`, `.kimi-code/skills/ll-verify-issues/SKILL.md` — host mirrors already carry the paragraph from `310db44bb`; re-run `ll-adapt --host <gemini|kimi-code|qwen|codex> --apply` after any further `commands/verify-issues.md` edit (codex bridge `skills/ll-verify-issues/SKILL.md` only changes if the description does) [Agent 1, 2 findings]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` - `correct_claims` and `check_claim_correction_budget` states invoke the command
- `scripts/little_loops/issue_parser.py` - `check_format_gaps` scans `## Verification Notes` for citation tokens

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_parser.py` — correction to the line above: the blocking `stale_file_ref` comes from the whole-file `classify_issue_refs` scan in `check_format_gaps` (`:1297`), not a Verification Notes–specific scan; `citations.py:_regions` (`_CURRENT_STATE_H2`, `_ADVISORY_H2`) does not cover that section [Agent 1, 2 findings]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `normalize_structure` (runs after `correct_claims`) already calls `ll-issues format-check <ID> --format json` but reads only `directive_gaps`, so it is blind to `stale_file_ref`; a guard state needs its own probe on `stale_file_ref` [Agent 2 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` — `ensure_formatted` runs `ll-issues format-check` with `evaluate: exit_code`; blocking `stale_file_ref` already routes to `format_issue` there, and a scan-scope change alters its behavior [Agent 2 finding]
- `scripts/little_loops/cli/issues/format_check.py` — `format-check` CLI (`stale_file_ref` rendering, `examined_refs` collector, exit code `1 if gaps.has_blocking_gaps`); consumer of any `check_format_gaps` scoping change [Agent 1, 2 findings]
- `commands/verify-issues.md` — check B8 (`8. **Citation findings via format-check`) consumes the same `format-check` output and is skipped under `--from-evidence` [Agent 2 finding]

### Similar Patterns
- `scripts/tests/test_bug3708_verify_issues_b8.py` - contract tests asserting verify-issues command structure (model for the regression test)

### Tests
- `scripts/tests/test_bug3708_verify_issues_b8.py` - extend or add a sibling asserting the paraphrase and post-write-check rule

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — closest existing home for the new contract test: `TestClaimsOutdatedVerdict` (`:128`, e.g. `test_section_4_has_in_place_correction_rule` `:180`) already slices `### 4. Update Issue Files` → `### 4.1`; slice from `**Verification Notes must not re-introduce the finding.**` (`commands/verify-issues.md:567`) to `### 4.1`, assert on whitespace-flattened text ("paraphrase", "ll-issues format-check", "--from-evidence"). Alternatively a new `test_bug3753_*.py` using `VERIFY_CMD`/`_body()`/`_flat()` from `test_bug3708_verify_issues_b8.py` (`:27`, `:38`, `:43`). No test currently pins the rule or mentions `Verification Notes` [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py` — `test_host_artifacts_are_not_stale` (`:489`, gemini/kimi-code/qwen/codex/omp) fails until `ll-adapt --apply` is re-run after any `commands/verify-issues.md` edit; this file also pins verify-issues strings (`[ -f .ll/decisions.yaml ]`, `Bash(ll-code:*)`, `Causal / identity claims`) that rewording must keep [Agent 2, 3 findings]
- `scripts/tests/test_builtin_loops.py` — `TestRefineToReadyDispatch` (`PRE_TABLE["VERIFY:CLAIMS_OUTDATED"]`) and `test_all_validate_as_valid_fsm` (`:77`) validate any new state's reachability and routing; no test asserts `correct_claims` fields (`next`, `on_error`, `action` containing `--from-evidence`) — add a routing test if a guard state is added [Agent 3 finding]
- `scripts/tests/test_format_probe_routing.py` — `_run(state, tmp_path, payload, counter)` runs a state's real shell action with a fake `ll-issues`; model for a behavioral test of a new guard state [Agent 2, 3 findings]
- `scripts/tests/test_bug3695_directive_drift_repair.py` — `run_refine_to_ready` (via `autodev_harness.py`) drives the loop end-to-end and asserts exact state order for the `reconcile_issue` path; model for an end-to-end `correct_claims` path test [Agent 3 finding]
- `max_steps == 113` pins — break only if the guard state bumps the budget; update all four together: `scripts/tests/test_builtin_loops.py:1884`, `scripts/tests/test_bug3695_directive_drift_repair.py:292`, `scripts/tests/test_autodev_proof_reentry.py:131`, `scripts/tests/test_advise_ready_gate.py:216` [Agent 3 finding]
- `scripts/tests/test_ll_issues_format_check.py::TestStaleFileRef` (`:696`), `scripts/tests/test_citation_checks.py`, `scripts/tests/test_head_corpus.py` and the `scripts/tests/fixtures/issues/bug32*_corpus/` fixtures — may break only if `check_format_gaps` scoping is changed; a scoping change needs a case with a stale path under `## Verification Notes` plus a control case in `## Current Behavior` proving the filter is narrow [Agent 3 finding]

### Documentation
- N/A - rule is internal to the command text; host mirrors regenerated via `ll-adapt`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — "Claim-verification gate chain (ENH-3031, ENH-3604)" `VERIFY:CLAIMS_OUTDATED` row and the `normalize_structure` re-entry paragraph name `check_claim_correction_budget` → `correct_claims` → `record_gate_unmet`; update only if a guard state is added [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-issues format-check` section (`stale_file_ref` paragraph; "`/ll:verify-issues` check B8 consumes this output", pinned by `test_bug3708_verify_issues_b8.py::TestCliDocNamesConsumer`); update only if `check_format_gaps` scoping changes. The class-list strings in `cli/issues/format_check.py` and `cli/issues/__init__.py` (`format-check` usage line) move with it [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- Re-verified at HEAD (`3dffa9e11`): every `path:line` citation in this section and the Wiring-pass additions still resolves (`issue_parser.py:1297` `classify_issue_refs(content, ref_index)`, `commands/verify-issues.md:567`, `test_enh3250…:128/:180`, the four `max_steps == 113` pins, `test_wiring_skills_and_commands.py:489`). The recent `cli/issues/__init__.py` change (`--parent/--reparent`) did not touch the `format-check` usage line (`:184`).
- Consumers and writers the Map above omits: `scripts/little_loops/cli/issues/check_verify_verdict.py` (`CLAIMS_OUTDATED` verdict consumer — `check_claim_correction_budget` routes on it), `clear_verify_verdict.py` and `arm_proposal_revision.py` (read/clear `verify_evidence`), `scripts/little_loops/cli/verify_evidence.py`; `commands/ready-issue.md:378` also appends verification notes (does not write the `## Verification Notes` heading, so is outside this bug's trigger); `commands/reconcile-issue.md:126` mentions `--from-evidence` but does not invoke the correction pass.
- Only `refine-to-ready-issue.yaml:658` (`correct_claims`, `--auto --from-evidence`) invokes the correction pass; the other `verify-issues` call is `--check --auto` at `:552`. No other loop is exposed to this failure.
- The stale-quote trigger is also covered by existing fixtures that carry a `## Verification Notes` heading (`scripts/tests/fixtures/issues/bug3293_corpus/BUG-3293.md`, `bug3295_corpus/{BUG-1616,FEAT-3308}.md`, `bug3285_corpus/{FEAT-2186,ENH-2967}.md`); any `check_format_gaps` scoping change must keep `test_head_corpus.py` expectations on these stable or update them deliberately.
- Further tests that load `refine-to-ready-issue.yaml` and can break on a new state or routing change: `test_autodev_loop.py`, `test_autodev_scores_freshness.py`, `test_autodev_decision_gate.py`, `test_autodev_characterization.py`, `test_spike_verdict_routing.py`, `test_prepare_issue.py`, `test_concurrency.py`, plus `test_ll_issues_next_obligation.py` / `test_ll_issues_check_verify_verdict.py` for `CLAIMS_OUTDATED`. `docs/reference/API.md` (`stale_file_ref`, 5 hits) and `scripts/little_loops/loops/README.md` also describe `format-check` and move with a scoping change.
- Invariant for any `check_format_gaps` scoping: `test_symbol_claims.py` and `test_citation_checks.py` also exercise `stale_file_ref`; a section-level exemption must stay narrow to `## Verification Notes` so a genuinely stale path elsewhere still blocks.

## Implementation Steps

1. Confirm the command-text rule landed (commit 310db44bb) and host mirrors are in sync.
2. Add a contract test pinning the paraphrase rule and the post-write `ll-issues format-check` step, including under `--from-evidence`.
3. Optionally add a deterministic `format-check` state after `correct_claims` in `refine-to-ready-issue`, or limit citation scanning inside `## Verification Notes`.
4. Re-run the ENH-3742 reproduction through `refine-to-ready-issue` and confirm it passes the claim-correction gate.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add the contract test in `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` (`TestClaimsOutdatedVerdict`) or a sibling `test_bug3753_*.py`, following the `VERIFY_CMD`/`_body()`/`_flat()` slice pattern of `test_bug3708_verify_issues_b8.py`
- If `commands/verify-issues.md` is edited again, run `ll-adapt --host <gemini|kimi-code|qwen|codex> --apply` so `test_host_artifacts_are_not_stale` passes, and keep the strings pinned by `test_wiring_skills_and_commands.py`
- If adding a guard state after `correct_claims` in `refine-to-ready-issue.yaml`: probe `ll-issues format-check <ID> --format json` for `stale_file_ref` (not `directive_gaps`, which `normalize_structure` reads), route `correct_claims.next`/`on_error` through it, satisfy MR-7/9/10/11 and `${context.run_dir}` artifacts, and update the header routing/`max_steps` comments
- If the guard state bumps `max_steps`, update the four `== 113` pins (`test_builtin_loops.py:1884`, `test_bug3695_directive_drift_repair.py:292`, `test_autodev_proof_reentry.py:131`, `test_advise_ready_gate.py:216`)
- If adding the guard state, add a routing test for `correct_claims` and a behavioral test in the `test_format_probe_routing.py` `_run()` style; update `docs/guides/LOOPS_REFERENCE.md` gate-chain table
- If instead scoping `check_format_gaps`: filter inside `check_format_gaps` (not `classify_issue_refs`/`extract_file_paths`, shared with `test_dependency_mapper.py`/`test_text_utils.py`); add narrow/control cases to `test_ll_issues_format_check.py::TestStaleFileRef`; update `docs/reference/CLI.md` `format-check` section

## Program Design

### Types

- `VERIFY_CMD: Path` — `commands/verify-issues.md`, read by the contract test

### Signatures

- `test_verification_notes_paraphrase_rule_present() -> None` — asserts the body contains the paraphrase-not-quote rule and the post-write `ll-issues format-check` instruction
- `test_post_write_check_applies_under_from_evidence() -> None` — asserts the rule text states it holds even though check B8 is skipped under `--from-evidence`

### Call Path

`correct_claims` -> `/ll:verify-issues --from-evidence` -> `check_format_gaps` -> `check_claim_correction_budget`

## Impact

- **Priority**: P3 - burns a full refine-to-ready run, but only when a correction note quotes a stale citation; the command-text fix is already in place
- **Effort**: Small - one regression test, plus an optional loop state
- **Risk**: Low - test-only change; the optional loop guard is additive
- **Breaking Change**: No

## Root Cause

- `commands/verify-issues.md` §4 / §4.1 instruct the pass to record what was wrong, with no rule against quoting path, symbol or line citations verbatim.
- Check B8 (format-check citations) is skipped under `--from-evidence`, so the pass never re-runs `ll-issues format-check` after writing its own note.
- `normalize_structure` runs `format-check --fix`, but `stale_file_ref` is not auto-fixable, so nothing repairs the note afterwards.
- `check_claim_correction_budget` allows exactly one correction per run, so one self-inflicted failure is terminal.

## Acceptance Criteria

- [ ] After `correct_claims`, a Verification Notes entry never contains a path or symbol citation that `ll-issues format-check` flags.
- [ ] A regression test covers the rule (command text or a deterministic guard).
- [ ] The ENH-3742 reproduction passes `refine-to-ready-issue` past the claim-correction gate.

## Related

BUG-3637 (introduced `correct_claims`), ENH-3690, BUG-3695.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-06 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-10-06T02:18:10 - `e2600ce5-ae49-45dd-9f4d-c7454cd772ad.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-06T02:14:49 - `dd470030-53a4-4ea7-a28e-a42612652be7.jsonl`
- `/ll:wire-issue` - 2026-10-06T02:10:41 - `f07bd331-c0c6-4aed-ba28-ade85ff49455.jsonl`
- `/ll:refine-issue` - 2026-10-06T02:02:43 - `a1b406f4-aba7-4d6b-9fb6-614b0249f344.jsonl`
- `/ll:format-issue` - 2026-10-06T02:01:35 - `7fee41a9-247a-46a6-853e-97ee7190a531.jsonl`
- `/ll:capture-issue` - 2026-10-06T01:01:57 - `89b97fde-6836-4bf2-b412-cd83564e6b38.jsonl`
