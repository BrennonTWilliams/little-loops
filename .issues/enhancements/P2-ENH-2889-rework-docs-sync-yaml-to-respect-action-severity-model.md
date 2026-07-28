---
id: ENH-2889
title: Rework docs-sync.yaml to respect action-severity model
type: ENH
parent: EPIC-2872
priority: P2
status: done
discovered_date: 2026-07-28
completed_at: '2026-07-28T09:40:57Z'
labels:
- verification
- ll-doctor
depends_on:
- ENH-2886
relates_to:
- ENH-2875
confidence_score: 98
outcome_confidence: 80
score_complexity: 20
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 20
---

# ENH-2889: Rework docs-sync.yaml to respect action-severity model

## Parent Issue
Decomposed from ENH-2875: Give drift findings an action-severity and a throttle, and forbid opportunistic repair

## Summary

`scripts/little_loops/loops/docs-sync.yaml` is the codebase's current instance of "opportunistic repair" — the pattern this issue's parent forbids. Its `route_results` state regex-matches the raw combined text output of `ll-verify-docs`/`ll-check-links`, and its `fix_docs` state dispatches a free-form LLM prompt that repairs everything unconditionally, with zero severity discrimination. Once ENH-2886 lands the `auto`/`mention`/`route` action-severity model, this loop must be reworked to restrict itself to `auto`-severity findings only.

## Impact

`docs-sync.yaml` is the codebase's live instance of the "opportunistic repair" anti-pattern its parent (ENH-2875) forbids: every run silently rewrites `mention`/`route`-severity documentation findings via a free-form LLM prompt, with no severity discrimination. Left unfixed, this is the one loop in the built-in catalog that violates the action-severity model ENH-2886 just introduced, undermining the guarantee that drift is reported, not auto-repaired, unless requested.

## Current Behavior

`scripts/little_loops/loops/docs-sync.yaml`'s `route_results` state regex-matches the *raw combined text output* of `ll-verify-docs`/`ll-check-links` for `"FAIL|ERROR|BROKEN|MISMATCH"` (`output_contains`), and its `fix_docs` state then dispatches a free-form LLM prompt ("Fix all documentation discrepancies... Update counts... Fix broken internal links...") with zero severity discrimination — repairing everything unconditionally, including what is now `mention`/`route`-severity findings (per ENH-2886).

`scripts/little_loops/loops/lib/cli.yaml` — `ll_check_links` fragment (line 70) is the shared action `docs-sync.yaml` invokes for `ll-check-links`; also has a raw-output string dependency that action-severity output changes may break.

## Expected Behavior

`docs-sync.yaml` is reworked to restrict itself to `auto`-severity findings (or gated through `--fix`, per ENH-2886) — it must never repair a `mention`/`route`-severity finding, satisfying the parent issue's hard rule: "Never repair drift as a side effect of a design task. A staleness finding is reported, not acted on, unless the user asks."

## Scope Boundaries

In scope: `docs-sync.yaml`'s `route_results`/`fix_docs` states and `loops/lib/cli.yaml`'s `ll_check_links` fragment's output-parsing dependency on action-severity. Out of scope: the action-severity field itself (ENH-2886, a prerequisite), `ll-doctor --full` aggregation (ENH-2887), the session-start hook (ENH-2888).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify
- `scripts/little_loops/loops/docs-sync.yaml` — `verify_docs` (lines 18-24), `route_results` (lines 31-39), `fix_docs` (lines 40-59) states
- `scripts/little_loops/loops/lib/cli.yaml` — `ll_check_links` fragment (lines 70-80), if its raw-text `evaluate: {type: exit_code}` needs to change shape
- `scripts/little_loops/loops/README.md` — line 53, `docs-sync` catalog row currently reads "Verify documentation matches the codebase and fix broken links" (inaccurate today: there is no auto-fix path for broken links at all)

#### Current State (exact mechanics)
- `verify_docs` (docs-sync.yaml:18-24) runs `ll-verify-docs 2>&1` via `fragment: shell_exit`; all three routes (`on_yes`/`on_no`/`on_error`) go unconditionally to `check_links` — exit code isn't actually branched on.
- `check_links` (docs-sync.yaml:25-30) runs `fragment: ll_check_links`; all three routes go unconditionally to `route_results`.
- `route_results` (docs-sync.yaml:31-39) uses `evaluate.type: output_contains` with `source: "${captured.verify_results.output}${captured.link_results.output}"` and `pattern: "FAIL\\|ERROR\\|BROKEN\\|MISMATCH"` (negated) — a raw regex over combined text with zero severity awareness. `on_no` (bad words found) routes to `fix_docs`.
- `fix_docs` (docs-sync.yaml:40-59) is `action_type: prompt` (timeout 600), a free-form LLM instruction to "Fix all documentation discrepancies" unconditionally, including link issues — even though no code path ever produces an `auto`-severity link finding.
- `docs-sync.yaml` has `category: meta`, so MR-1 (non-LLM evaluator required) applies to any reworked state.

#### ENH-2886 severity plumbing already in place (prerequisite, done)
- `doc_counts.py`: `CountResult.action_severity: Literal["auto","mention","route"]` (lines 38-59); `fix_counts()` (lines 423-486) already filters `if mismatch.action_severity != "auto": continue` (line 443) — so `ll-verify-docs --fix` (existing flag, `cli/docs.py:65-69`, wired at lines 101-105) **already only rewrites auto-severity mismatches**. No new CLI flag exists or is needed for this half; the severity gate lives inside `fix_counts`. Exit code (`cli/docs.py:108`) is `0 if result.all_match else 1` — still 1 after `--fix` if `mention`/`route` mismatches remain (correctly unfixed, but the exit code alone doesn't distinguish "some remain by design" from "fix failed").
- `link_checker.py`: `LinkResult.action_severity` (lines 61-91) — broken/unreachable/file-read-error links are always `"mention"` (lines 353, 395, 408); valid/internal/ignored links default to `"auto"`. **There is no `--fix` flag on `ll-check-links` at all** (confirmed against `main_check_links`, `cli/docs.py:313-444`) — link findings that aren't already benign are always `mention`, never auto-repairable.
- Both `doc_counts.format_result_json()` (lines 224-252, fields at 245-246) and `link_checker.format_result_json()` (lines 511-543, fields at 536-537) already emit `action_severity`/`route_owner` per finding in `--json` output — this is the schema available if the FSM needs structured per-finding severity instead of exit codes/regex.
- Test proof: `test_cli_docs.py::TestMainVerifyDocs::test_fix_flag_leaves_non_auto_mismatch_unwritten` (lines 194-234) confirms `--fix` silently no-ops on `mention` mismatches (file untouched, exit code still 1).

#### Similar Patterns
- `scripts/little_loops/loops/worktree-health.yaml:12-24` — simplest non-LLM `output_numeric` gate template: capture a count, route on the number rather than string matching.
- `scripts/little_loops/loops/oracles/code-run-gate.yaml:~209-249` — the "shell out, write JSON, `python3 -c "import json; ..."` to extract one field, feed into `capture`+`output_numeric`" convention already used elsewhere in this codebase's loop YAMLs; the same convention could parse `action_severity` counts from `--json` output.
- `scripts/little_loops/cli/doctor.py:_full_check_links_data()` (lines 771-812) — the closest existing consumer of `.action_severity`/`.route_owner`, though it imports `check_markdown_links()`/`verify_documentation()` directly rather than shelling out; useful as a reference for the two-axis model (`severity` vs `action_severity`) but not directly reusable from an FSM shell state.
- `scripts/little_loops/fsm/validation.py:1449-1483` — MR-1 enforcement: `NON_LLM_EVALUATOR_TYPES` (validation.py:88-91) excludes only `llm_structured`; any reworked `route_results`/`fix_docs` state must keep a non-LLM `evaluate` block (e.g. `output_contains` on a JSON severity string, or `output_numeric` on a derived auto-finding count).

### Tests
- `scripts/tests/test_cli_docs.py`, `test_doc_counts.py`, `test_link_checker.py` — already updated for ENH-2886's severity model (per current git diff); no docs-sync-specific test file exists yet.
- `scripts/tests/test_builtin_loops.py` and `scripts/tests/test_fsm_fragments.py` — validate built-in loops incl. `docs-sync` and fragment references incl. `ll_check_links`; will need to pass after the rework.

### Documentation
- `scripts/little_loops/loops/README.md:53` — catalog row needs updating (see Files to Modify above).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:1243-1256` — `### docs-sync — Documentation Sync` section states "verifies doc accuracy and fixes broken links" — stale under the rework (fix_docs becomes report-only; no free-form link repair exists today or after). [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:386` — catalog listing row mentions `docs-sync` alongside other code-quality loops; no behavior claim, low-priority consistency check only. [Agent 2 finding]

### Tests (additional)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:9654-9677` (`TestDocsSyncLoop`) — `test_required_states_exist` pins `{"verify_docs", "check_links", "route_results", "fix_docs", "commit", "done"}` as a subset check; safe if new states are added, but breaks if `route_results`/`fix_docs` are renamed or removed. No existing assertion covers `route_results`'s evaluate block or `fix_docs`'s action content, so there's no regression guard for the semantics being replaced — extend this class with a new test asserting the reworked `route_results` uses a non-LLM evaluator (`output_numeric`/`output_contains` on parsed JSON) and that `fix_docs` is report-only. Model the new test after `test_only_uses_non_llm_evaluators` (test_builtin_loops.py:10005-10038, code-run-gate oracle class) and `TestWorktreeHealthLoop` (test_builtin_loops.py:7934-7965). [Agent 3 finding]
- `scripts/tests/test_fsm_fragments.py:965-989` (`test_ll_check_links_resolves_with_action_override`) — extend with a variant asserting any new output-shape fields resolve/override correctly, if `ll_check_links` fragment's shape changes. [Agent 3 finding]

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Since `fix_counts()` already gates count-repair to `auto`-severity internally (doc_counts.py:443) and `ll-check-links` has no `--fix` path at all (every non-benign link finding is `mention`), the severity boundary for counts can be enforced by shelling out to the existing `--fix` flag directly, rather than routing through the free-form `fix_docs` LLM prompt:

- `verify_docs` (docs-sync.yaml:18-24): change action to `ll-verify-docs --fix --json 2>&1` so auto-severity count mismatches are rewritten deterministically in shell, without an LLM in the loop for that half.
- `route_results` (docs-sync.yaml:31-39): replace the raw `output_contains` regex over combined text with a check that only looks for **remaining, non-auto** findings — e.g. parse the `--json` output's `action_severity` field per mismatch/link-result (mirroring `code-run-gate.yaml`'s `python3 -c "import json; ..."` → `capture` → `output_numeric` convention) and route to a report-only state whenever any `mention`/`route` finding remains. This keeps a non-LLM evaluator (MR-1 compliant) while eliminating the false premise that a `FAIL`/`BROKEN` string match implies something is auto-repairable.
- `fix_docs` (docs-sync.yaml:40-59): since post-`--fix` there is nothing left for a free-form prompt to safely auto-repair (remaining `ll-verify-docs` mismatches are guaranteed `mention`/`route`, and all `ll-check-links` findings are always `mention`), this state should stop being an unconditional repair prompt. Rework it into a report-only state (e.g. surface remaining findings for a human, do not edit files) — this directly satisfies the acceptance criterion that `mention`/`route` findings are "reported, not repaired."
- `ll_check_links` fragment (`lib/cli.yaml:70-80`): no `--fix`/`--json` flag exists on `ll-check-links` and none needs to be added — the fragment can stay as-is for exit-code gating, but the state consuming its output must never route to a repair action, only to reporting.

## Acceptance Criteria

- `docs-sync.yaml`'s repair path applies only to `auto`-severity findings; `mention`/`route`-severity findings are reported, not repaired, by this loop.
- `loops/lib/cli.yaml`'s `ll_check_links` fragment is updated for any output-shape change from ENH-2886.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. Change `verify_docs` (docs-sync.yaml:18-24) action to `ll-verify-docs --fix --json 2>&1`, capturing structured JSON.
2. Rework `route_results` (docs-sync.yaml:31-39) to parse `action_severity` per remaining finding from the captured JSON (`doc_counts.py:format_result_json()` lines 224-252 / `link_checker.py:format_result_json()` lines 511-543) via a `python3 -c "import json; ..."` + `capture` + `output_numeric` pattern (model after `oracles/code-run-gate.yaml:~209-249`), routing to a report state only when non-`auto` findings remain — never to a repair prompt.
3. Rework `fix_docs` (docs-sync.yaml:40-59) into a report-only state (no file edits) that surfaces remaining `mention`/`route` findings, since `--fix` already resolved everything auto-repairable.
4. Confirm `ll_check_links` fragment (`lib/cli.yaml:70-80`) output shape is unaffected (no `--fix`/`--json` flag added there) or update it if a shape change is needed for parity with the new `route_results` JSON parsing.
5. Update `scripts/little_loops/loops/README.md:53`'s `docs-sync` catalog description to reflect the new "verify + auto-fix auto-severity findings + report the rest" behavior.
6. Run `ll-loop validate loops/docs-sync` and `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_fragments.py -v` to confirm the rework doesn't break FSM validation or fragment references.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/guides/LOOPS_REFERENCE.md:1243-1256`'s `docs-sync` section — remove the stale "fixes broken links" claim, describe the new "auto-fix auto-severity count mismatches + report the rest" behavior.
8. Extend `scripts/tests/test_builtin_loops.py`'s `TestDocsSyncLoop` (lines 9654-9677) with an assertion on the reworked `route_results` evaluator shape (non-LLM, per MR-1) and that `fix_docs` no longer performs unconditional repair — following the `test_only_uses_non_llm_evaluators` pattern (test_builtin_loops.py:10005-10038).

## Tests

- `ll-loop validate loops/docs-sync` passes after the rework.

## Documentation

- `scripts/little_loops/loops/README.md` — update the loop catalog listing, which describes `docs-sync.yaml`'s current unconditional-fix behavior.

## Session Log
- `/ll:manage-issue` - 2026-07-28T09:40:31 - `00041c0b-3526-41ec-b743-a686380c429a.jsonl`
- `/ll:ready-issue` - 2026-07-28T09:30:02 - `a9cd12f7-a86d-4a5b-97cc-54fd1273ad35.jsonl`
- `/ll:wire-issue` - 2026-07-28T09:27:46 - `2e0891a3-d6c8-4272-9cd2-2b2faea0eef6.jsonl`
- `/ll:refine-issue` - 2026-07-28T09:23:42 - `f1916af5-40a0-4c74-b7b6-a48d94628903.jsonl`
- `/ll:issue-size-review` - 2026-07-28T08:00:00 - `f26799df-de87-40c6-90ea-225f55ba976e.jsonl`

## Status

open
