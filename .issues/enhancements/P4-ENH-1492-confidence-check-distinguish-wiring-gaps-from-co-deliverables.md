---
id: ENH-1492
type: ENH
priority: P4
status: done
captured_at: '2026-05-16T04:06:13Z'
completed_at: '2026-05-16T05:22:00Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
relates_to: BUG-1490
decision_needed: false
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1492: Confidence-check should distinguish wiring gaps from co-deliverable test files when setting `missing_artifacts`

## Summary

The `confidence-check` skill sets `missing_artifacts: true` when it detects absent files
in risk factors — but it conflates two semantically different cases:

1. **Pre-implementation wiring gaps**: configuration files, prerequisite issues, or
   integration wiring that must exist *before* the feature can be implemented
2. **Co-deliverable files**: test files or scripts that are *part of the feature delivery*
   and are expected to be absent before implementation starts

Setting `missing_artifacts: true` for case 2 misfires the `run_wire` repair path in
`autodev` (which resolves case 1), wastes a wire+refine cycle on an already-complete
issue, and can trigger unnecessary size-review via BUG-1490.

## Current Behavior

In FEAT-1486 (2026-05-16), `confidence-check` set `missing_artifacts: true` because
`test_adapt_skills_for_codex.py` does not exist. That file is a deliverable of FEAT-1486
itself — its absence is expected and correct for an unimplemented FEAT.

The risk factor text was: "Tests are co-deliverables: ... implement the tests first so
the adaptation script has automated validation before it touches real files." This is
**implementation-order advice**, not a wiring gap.

## Expected Behavior

`missing_artifacts: true` should only be set when absent files represent **pre-conditions
for implementation** — things that must exist before the feature work can start. Absent
files that are themselves the deliverable (scripts, test files, config stubs that the
issue will create) should NOT set this flag.

The implementation-order advice ("write tests first") belongs in the Implementation Steps
body text, where it already appears after the wire pass.

## Motivation

The `missing_artifacts` flag is a routing signal for FSM loops. Mis-setting it causes:
- `run_wire` to run on already-wired issues (wasted LLM call)
- BUG-1490: size-review on well-specified issues when the sub-loop lacks the gate
- Potential silent skips via BUG-1491 when the repair path finds nothing to fix

## Implementation Steps

1. **Define the distinction** in `skills/confidence-check/SKILL.md` or its prompt:
   - `missing_artifacts: true` ← absent pre-condition files (wiring, config, prerequisites)
   - `missing_artifacts: false` ← absent deliverable files (what the issue will create)
2. **Add detection heuristics** to the confidence-check evaluation logic:
   - If the absent file is listed in "files_to_create" in the Integration Map → co-deliverable → do NOT set flag
   - If the absent file is a prerequisite (must exist for the feature to work) → set flag
3. **Add a new optional flag** (e.g., `implementation_order_risk: true`) to capture
   ordering concerns that should not trigger the wiring repair path
4. **Update confidence-check prompt** to explicitly document the distinction

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/little_loops/issue_parser.py:IssueInfo` — add `implementation_order_risk: bool | None = None` field; update `to_dict()` with `"implementation_order_risk": self.implementation_order_risk` and `from_dict()` with `implementation_order_risk=data.get("implementation_order_risk")`; add parse block in `parse_file()` after the `missing_artifacts` block at lines ~464–472
6. Update `scripts/little_loops/cli/issues/show.py:_parse_card_fields()` — read `implementation_order_risk_raw` from frontmatter and serialize in JSON output block alongside `missing_artifacts_raw` (lines ~158–159); otherwise `ll-issues show --json` won't emit the key and loop states can't branch on it
7. Update `scripts/tests/test_confidence_check_skill.py` — add `TestImplementationOrderRiskFlagWriteBack` class; review `TestMissingArtifactsFlagWriteBack.test_signal_phrases_documented` (line 151) for breakage if Phase 4.7 prose changes
8. Update `scripts/tests/test_issue_parser.py` — add `TestIssueInfoImplementationOrderRisk` class (8 test methods)
9. Update `scripts/tests/test_issues_cli.py` — add `test_show_json_includes_implementation_order_risk` following the pattern of `test_show_json_includes_missing_artifacts` (line 2073)
10. Update `scripts/tests/test_builtin_loops.py` — if new gate states are inserted in autodev.yaml or refine-to-ready-issue.yaml, update routing assertions in `TestRefineToReadyIssueSubLoop` and `TestAutodevLoop.test_required_states_exist`
11. Update `docs/reference/ISSUE_TEMPLATE.md` — add `implementation_order_risk` row to frontmatter fields table
12. Update `docs/reference/API.md` — add `implementation_order_risk: bool | None` to `IssueInfo` field listing
13. Update `docs/reference/COMMANDS.md` — add Phase 4.8 write-back description paragraph under `/ll:confidence-check`
14. Update `docs/guides/LOOPS_GUIDE.md` — update flow diagrams if new loop gate states are added (conditional)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 anchor**: `skills/confidence-check/SKILL.md`, section `### Phase 4.7: Missing-Artifacts Flag` — this is the exact section to update; the current signal phrases (`"not yet created"`, `"does not exist"`, `"absent"`, etc.) fire regardless of whether the absent file is a deliverable
- **Step 2 anchor**: Phase 4.7 scans its own prior output (Phase 4.5 prose) for signal phrases — the heuristic fix is to instruct the LLM to first check the issue's `### Files to Create` Integration Map subsection before writing any risk phrase that would trigger Phase 4.7; alternatively, add a post-scan suppression step in Phase 4.7 that reads `### Files to Create` from the current issue and clears the flag if the absent file appears there
- **Step 3 anchor**: Follow `### Phase 4.6: Decision-Needed Flag` in the same SKILL.md as the template; add a `### Phase 4.8: Implementation-Order Risk Flag` block with signal phrases such as `"implement tests first"`, `"write tests before"`, `"test-first"`, `"co-deliverable"`; wire it to `implementation_order_risk: true` in frontmatter using the same idempotency pattern
- **Step 3 parser**: Add `implementation_order_risk: bool | None = None` to `IssueInfo` dataclass (pattern: `scripts/little_loops/issue_parser.py:IssueInfo`, line ~269); add parse block in `IssueParser.parse_file()` immediately after the `missing_artifacts` block at lines ~464–472 (copy the `decision_needed` block at lines ~454–462 verbatim and replace field name)
- **Step 4 test anchor**: Model new tests after `TestMissingArtifactsFlagWriteBack` in `scripts/tests/test_confidence_check_skill.py` (line 130) for the skill tests, and `TestIssueInfoMissingArtifacts` in `scripts/tests/test_issue_parser.py` (line 2042) for parser round-trip tests

## Acceptance Criteria

- [ ] `missing_artifacts: true` is NOT set for files listed under `files_to_create` in
      the issue's Integration Map
- [ ] Test files that are co-deliverables of a FEAT/ENH do not trigger `missing_artifacts`
- [ ] Implementation-order risk (e.g., "write tests before running script") is captured
      separately or as body text, not as the `missing_artifacts` flag
- [ ] A FEAT with all wiring complete and only co-deliverable files absent gets
      `missing_artifacts: false`

## Scope Boundaries

- **In scope**: `confidence-check` skill logic for setting `missing_artifacts: true/false`; adding `implementation_order_risk` flag; updating skill documentation and prompt
- **Out of scope**: Changing how `autodev` or FSM loops consume `missing_artifacts` (handled by BUG-1490/1491); altering the wire repair path logic itself; redesigning the full risk-factor schema

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — update `missing_artifacts` detection logic; add `implementation_order_risk` flag definition

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py:IssueParser.parse_file()` (lines ~464–472) — parses `missing_artifacts` from frontmatter using string-coerce pattern; add `implementation_order_risk` with identical parse block; also update `IssueInfo` dataclass (~line 269) and `to_dict()`/`from_dict()` methods to include the new field
- `scripts/little_loops/cli/issues/show.py:_parse_card_fields()` (line ~159) — extracts `missing_artifacts_raw` for `--json` output; add `implementation_order_risk_raw` in the same block if surfacing in CLI output is desired
- `scripts/little_loops/cli/issues/check_flag.py:cmd_check_flag()` — generic flag routing CLI; no changes needed — already reads any frontmatter key by name
- `scripts/little_loops/loops/autodev.yaml` — `check_missing_artifacts` state (line ~431) routes `on_yes` → `run_wire`; no changes needed — the fix is upstream (what sets the flag), not how loops consume it
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `check_missing_artifacts` state (line ~271) routes `on_yes` → `done`; no changes needed for the same reason

### Similar Patterns
- `skills/confidence-check/SKILL.md` — Phase 4.6 (`### Phase 4.6: Decision-Needed Flag`) is the exact template for a new Phase 4.8 `implementation_order_risk` flag: same `CHECK_MODE` guard, signal-phrase scan on Phase 4.5 output, idempotency check, and terminal log pattern
- `scripts/little_loops/issue_parser.py:IssueInfo` — `decision_needed: bool | None = None` is the declaration pattern; `parse_file()` string-coerce block at lines ~454–462 (`decision_needed_raw`) is the exact template for the new field's parse block
- `scripts/tests/test_confidence_check_skill.py:TestDecisionNeededFlagWriteBack` (line 86) — 6-test class to model the new `TestImplementationOrderRiskFlagWriteBack` class after
- `scripts/tests/test_issue_parser.py:TestIssueInfoDecisionNeeded` (line 1911) — 8-test class template for `TestIssueInfoImplementationOrderRisk` covering default-None, True, False, to_dict, from_dict, and parse_file integration

### Tests
- `scripts/tests/test_confidence_check_skill.py` — add cases for co-deliverable files vs. pre-condition files; add new class `TestImplementationOrderRiskFlagWriteBack` mirroring `TestMissingArtifactsFlagWriteBack` (line 130) — `_phase_text()` helper + 6 assertion methods anchored on Phase 4.8 heading; note `TestMissingArtifactsFlagWriteBack.test_signal_phrases_documented` (line 151) may break if Phase 4.7 prose is rewritten to add the wiring-gap/co-deliverable distinction
- `scripts/tests/test_issue_parser.py` — add `implementation_order_risk` to parser round-trip test; add class `TestIssueInfoImplementationOrderRisk` mirroring `TestIssueInfoMissingArtifacts` (line 2042) with 8 methods: default-None, True, False, to_dict, from_dict missing key, from_dict False, parse_file roundtrip True, parse_file roundtrip absent
- `scripts/tests/test_builtin_loops.py` — verify routing logic isn't broken by new flag; `TestRefineToReadyIssueSubLoop` (line 533) assertion `test_check_missing_artifacts_on_no_routes_to_breakdown_issue` will break if a new `check_implementation_order_risk` gate is inserted between those states; `TestAutodevLoop.test_required_states_exist` (line 1165) must include any new state added to autodev.yaml

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py` — contains template tests `test_show_json_includes_missing_artifacts` (line 2073) and `test_show_json_includes_decision_needed` (line 2043); add `test_show_json_includes_implementation_order_risk` following the same pattern — write frontmatter with `implementation_order_risk: true`, invoke `ll-issues show --json`, assert `data.get("implementation_order_risk") == "true"` [Agent 2 + Agent 3 finding]
- `scripts/tests/test_issue_parser_properties.py` — Hypothesis roundtrip test `test_issueinfo_roundtrip` (line 104) does not include optional boolean flags; new field won't break it but the roundtrip won't cover `implementation_order_risk` unless explicitly added to the strategy [Agent 3 finding — low priority]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md` — frontmatter fields table (lines ~886–895) lists `missing_artifacts` with its source phase and signal phrases; add parallel row for `implementation_order_risk` with Phase 4.8 description [Agent 2 finding]
- `docs/reference/API.md` — `IssueInfo` class field listing (lines ~577–586) enumerates every field; add `implementation_order_risk: bool | None` with attribution comment (who sets it, when) [Agent 2 finding]
- `docs/reference/COMMANDS.md` — `/ll:confidence-check` section has a `decision_needed` write-back paragraph; add parallel paragraph documenting when Phase 4.8 fires and what it sets [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — autodev and refine-to-ready-issue flow diagrams (lines ~482–484); if a `check_implementation_order_risk` gate state is inserted into either loop, update the diagram to show the new state and its routing [Agent 2 finding — conditional on whether new loop states are added]

### Configuration
- N/A

## Impact

- **Priority**: P4 — Reduces wasted wire+refine cycles in automation, but workaround is manual issue review
- **Effort**: Small — Changes confined to `skills/confidence-check/SKILL.md` and prompt; parser may need minor schema update
- **Risk**: Low — Additive change; new `implementation_order_risk` flag is opt-in; existing `missing_artifacts: true` behavior for real pre-conditions is unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `confidence-check`, `autodev`, `routing`

## Status

**Open** | Created: 2026-05-16 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-05-16T05:13:01 - `50eabc75-ee51-4761-beca-592ae8e51906.jsonl`
- `/ll:confidence-check` - 2026-05-16T06:00:00Z - `d3e382e6-b768-4a9c-bbfe-14b5f694b283.jsonl`
- `/ll:wire-issue` - 2026-05-16T05:09:02 - `67c91818-9ccc-4187-a351-cb9ed1328145.jsonl`
- `/ll:refine-issue` - 2026-05-16T05:03:19 - `23553eb2-56eb-4adc-bc4d-5d1072c6beb2.jsonl`
- `/ll:format-issue` - 2026-05-16T04:10:25 - `bdf87445-2e6f-4176-b4f9-271ef09487e4.jsonl`
- `/ll:capture-issue` - 2026-05-16T04:06:13Z - `ffbdb77c-d0c6-43e0-a45d-2fb26e8e53b6.jsonl`
