---
captured_at: "2026-04-25T19:14:09Z"
completed_at: 2026-04-26T19:10:04Z
discovered_date: 2026-04-25
discovered_by: capture-issue
decision_needed: false
blocked_by: [ENH-1290]
confidence_score: 90
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
status: done
---

# ENH-1291: Autodev `triage_outcome_failure` missing-artifact routing branch

## Summary

`triage_outcome_failure` (ENH-1288) routes issues to `run_decide` when `score_ambiguity ≤ 10` and to `detect_children` otherwise. A third root cause — absent files or unwired components — also lowers `outcome_confidence` but needs routing to `wire-issue`/`refine-issue`, not size-review. This branch is absent and the right signal to detect it is an open design question.

## Current Behavior

After ENH-1288, `triage_outcome_failure` handles two cases:
- `score_ambiguity ≤ 10` → `run_decide` (unresolved design decision)
- Otherwise → `detect_children` (size-review path)

Issues where `outcome_confidence` is low because a referenced file is absent (`ExtensionSection.jsx` absent, unwired component, missing artifact) fall through to `detect_children`. Size-review then scores them as Large due to thorough documentation and proposes decomposition, which is the wrong fix — the actual blocker is a wiring gap, not scope bigness.

## Expected Behavior

`triage_outcome_failure` should have a third branch:
- Artifact/wiring bottleneck → `run_wire` or `run_refine` (whichever is appropriate)

The challenge is the signal. `score_complexity` is ambiguous: low `score_complexity` can mean either "this issue references absent files" or "this issue has narrow scope." Routing to `wire-issue` on a genuinely small-scope issue would be incorrect. A dedicated signal — a field written by `confidence-check` specifically for the artifact case — is needed.

## Motivation

This is the third leg of ENH-1288's own Expected Behavior table:

| Bottleneck | Signal | Right intervention |
|---|---|---|
| Structural bigness | `score_complexity` low (many files, broad scope) | `issue-size-review` |
| Unresolved design | `score_ambiguity` low (≤10) | `decide-issue` |
| **Missing artifacts/wiring** | **?** | **`wire-issue` / `refine-issue`** |

ENH-1288 deliberately scoped this out because `score_complexity` alone cannot distinguish the two artifact-case interpretations. Without this branch, a subset of wiring-blocked issues will continue to reach size-review and risk spurious decomposition (partially mitigated by ENH-1290's guard, but not fully prevented).

## Success Metrics

- Artifact-blocked issues (genuine wiring/reference gap) route to `run_wire` or `run_refine`, not `detect_children`
- Decision-blocked issues (`score_ambiguity ≤ 10`) still route to `run_decide` — no regression
- Scope-big issues (genuinely large scope) still route to `detect_children` — no regression
- Chosen signal field set only when genuine artifact absence detected (minimal false positives)

## Proposed Solution

TBD — requires a design decision on the signal. Two candidate approaches:

**Option A**: Add a `missing_artifacts: true` field to confidence-check Phase 4.x write-back, set when `outcome_confidence` is low and specific signal phrases indicate absent files or wiring gaps (e.g., "absent", "not yet created", "does not exist", "needs wiring"). `triage_outcome_failure` reads this field directly.

> **Selected:** Option A (`missing_artifacts: true`) — exact parallel to the existing `decision_needed: true` mechanism in Phase 4.6; all infrastructure (signal-phrase scan → boolean write → `d.get()` read in triage) already exists.

**Option B**: Add a `wire_status: incomplete` field to confidence-check write-back using the existing wiring-gap detection in Phase 4.5. `triage_outcome_failure` checks `wire_status == "incomplete"` before falling through to `detect_children`.

Option A is more explicit and self-documenting in the issue frontmatter. Option B reuses a concept that may already be tracked elsewhere. The decision should consider whether `wire-issue` or `refine-issue` is the right target (they overlap: `wire-issue` is for integration points, `refine-issue` for missing codebase context).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-04-26.

**Selected**: Option A (`missing_artifacts: true`)

**Reasoning**: Option A is a direct clone of the Phase 4.6 `decision_needed` mechanism — scan Outcome Risk Factors for signal phrases, write a boolean frontmatter field, read it in `triage_outcome_failure` via `d.get()`. The entire pattern (signal-phrase list, Edit-tool frontmatter write, `ll-issues show --json` + Python exit-code routing in `autodev.yaml:386-411`) already exists and can be copied verbatim. Option B (`wire_status: incomplete`) has no codebase precedent — the field does not exist anywhere, Phase 4.5 has no dedicated wiring-gap detection, and a string-enum routing check would introduce a new pattern type inconsistent with the boolean-flag convention.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (`missing_artifacts: true`) | 3/3 | 3/3 | 3/3 | 3/3 | **12/12** |
| Option B (`wire_status: incomplete`) | 1/3 | 1/3 | 2/3 | 1/3 | **5/12** |

**Key evidence**:
- Option A: `decision_needed: true` set by Phase 4.6 (confidence-check SKILL.md:509-513), read by `triage_outcome_failure` at autodev.yaml:380 — identical pattern ready to reuse. `missing_artifacts: true` already appears in the issue's own test fixture (line 73), confirming author intent.
- Option B: `wire_status` confirmed absent from entire codebase (grep across .md/.yaml/.json/.py); Phase 4.5 writes generic risk factors only — no wiring-specific detection code exists; string-valued field would also risk semantic collision if `wire-issue` later writes the same field.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 4.x write-back: add artifact signal field
- `scripts/little_loops/loops/autodev.yaml` — `triage_outcome_failure` state: add third branch
- `scripts/little_loops/issue_parser.py` — add `missing_artifacts: bool | None = None` field (clone `decision_needed` at lines 248, 284, 313, 414–422)
- `scripts/little_loops/cli/issues/show.py` — add `missing_artifacts` extraction + serialization (clone `decision_needed` at lines 157, 248–250)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — `run_wire` and `run_refine` states **do not exist yet** and must be added (clone `run_decide` at lines 190–199 using `/ll:wire-issue` and `/ll:refine-issue` respectively)
- `scripts/little_loops/loops/autodev.yaml` — a new `check_missing_artifacts` intermediate state is needed (same pattern as `check_decision_before_size_review` at lines 361–384); `triage_outcome_failure`'s `on_no` routes to `check_missing_artifacts` instead of directly to `detect_children`

### Similar Patterns
- `check_decision_before_size_review` (autodev.yaml:361–384) — exact template: `shell_exit` + `ll-issues show --json` + `d.get('field') == 'true'` → exit 0/1 → `on_yes`/`on_no` routing
- `triage_outcome_failure` (autodev.yaml:386–411) — current two-branch state; `on_no` needs to point to `check_missing_artifacts` instead of `detect_children`
- `run_decide` (autodev.yaml:190–199) — `fragment: with_rate_limit_handling` + `action_type: slash_command` — template for both `run_wire` and `run_refine` new states
- Phase 4.6 in `skills/confidence-check/SKILL.md:497–515` — signal-phrase scan → boolean frontmatter write-back — exact mechanism to clone

### Tests
- `scripts/tests/test_builtin_loops.py:1405–1431` — extend existing `triage_outcome_failure` test class; add tests for updated `on_no` → `check_missing_artifacts` and new state routing
- `scripts/tests/test_builtin_loops.py:1380–1403` — `check_decision_before_size_review` test class — template for new `check_missing_artifacts` test class
- `scripts/tests/test_confidence_check_skill.py:56–97` — `TestDecisionNeededFlagWriteBack` — template for new `TestMissingArtifactsFlagWriteBack` class
- `scripts/tests/test_issue_parser.py:1567–1695` — `TestIssueInfoDecisionNeeded` — template for new `TestIssueInfoMissingArtifacts` class
- `scripts/tests/test_issues_cli.py:1778–1806` — `test_show_json_includes_decision_needed` — template for new `missing_artifacts` show --json test
- Fixture: issue with `outcome_confidence: 64`, `score_ambiguity: 20` (not a decision), `missing_artifacts: true`
- Expected: routes to `run_wire` / `run_refine`, not `detect_children`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:1419–1424` — **WILL BREAK**: `test_triage_outcome_failure_on_no_routes_to_detect_children` asserts `on_no == "detect_children"`; must be changed to assert `on_no == "check_missing_artifacts"` after step 8 [Agent 2/3 finding]
- `scripts/tests/test_builtin_loops.py:1426–1431` — `test_triage_outcome_failure_on_error_routes_to_detect_children` — verify whether `on_error` also changes to `check_missing_artifacts`; update assertion to match [Agent 2/3 finding]
- `scripts/tests/test_builtin_loops.py:1026–1051` — `test_required_states_exist` — add `"check_missing_artifacts"`, `"run_wire"`, `"run_refine"` to the required states set; these new states are currently absent and not validated [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:447–471` — autodev ASCII state-transition diagram shows `triage_outcome_failure.on_no → detect_children` directly; update to show new `check_missing_artifacts` gate with two branches (`run_wire`/`run_refine` vs. `detect_children`) [Agent 2 finding]
- `docs/reference/API.md:572` — `IssueInfo` field reference table documents `decision_needed`; add parallel `missing_artifacts: bool | None = None` entry with write-by (`/ll:confidence-check`) context [Agent 2 finding]
- `docs/reference/ISSUE_TEMPLATE.md:884–887` — frontmatter field reference table; add `missing_artifacts` row with semantics and who sets it [Agent 2 finding]
- `CHANGELOG.md` — add ENH-1291 entry under the current release version block [Agent 2 finding]

### Configuration
- N/A — no new config required; new field written by confidence-check

## API/Interface

New frontmatter field written by `confidence-check` Phase 4.x write-back (Option A selected):

- **Field**: `missing_artifacts: true` — boolean, written to issue frontmatter YAML `---` block
- **Written by**: `skills/confidence-check/SKILL.md` Phase 4.x (new sub-phase, clone of Phase 4.6 at lines 497–515)
- **Signal phrases** (scan Outcome Risk Factors text from Phase 4.5): `"not yet created"`, `"does not exist"`, `"needs wiring"`, `"missing artifact"`, `"absent"`, `"unwired component"`
- **Idempotency**: skip write if `missing_artifacts` is already `true`
- **CHECK_MODE guard**: skip write in check mode
- **Serialized by**: `show.py` as lowercase string `"true"` (same pattern as `decision_needed` at lines 248–250)
- **Read by**: new `check_missing_artifacts` state in `autodev.yaml` via `d.get('missing_artifacts') == 'true'`
- **Routing**: `on_yes` → `run_wire`, `on_no` → `detect_children`
- **`IssueInfo` dataclass**: add `missing_artifacts: bool | None = None` to `issue_parser.py:248` (clone `decision_needed` field at lines 248, 284, 313, 414–422)

## Implementation Steps

1. **Decide** ✓ Done (Option A selected by `/ll:decide-issue`)
2. Add `missing_artifacts: bool | None = None` to `IssueInfo` in `issue_parser.py:248` and wire parsing at lines 284, 313, 414–422 (clone `decision_needed` field verbatim)
3. Add `missing_artifacts` extraction + serialization to `show.py` (clone `decision_needed` extraction at lines 157 and 248–250 in `_parse_card_fields()`)
4. Add Phase 4.x to `skills/confidence-check/SKILL.md` after Phase 4.6 (lines 497–515) — clone Phase 4.6 structure; signal phrases: `"not yet created"`, `"does not exist"`, `"needs wiring"`, `"missing artifact"`, `"absent"`, `"unwired component"`; writes `missing_artifacts: true`
5. Add `run_wire` state to `autodev.yaml` after `run_decide` (lines 190–199) — clone pattern using `fragment: with_rate_limit_handling` + `action_type: slash_command` + `/ll:wire-issue ${captured.input.output} --auto`; `next: enqueue_or_skip`, `on_error: enqueue_or_skip`
6. Add `run_refine` state to `autodev.yaml` similarly — clone `run_wire`, using `/ll:refine-issue ${captured.input.output} --auto`
7. Add `check_missing_artifacts` state to `autodev.yaml` (clone `check_decision_before_size_review` at lines 361–384) — reads `d.get('missing_artifacts') == 'true'`; `on_yes: run_wire`, `on_no: detect_children`
8. Update `triage_outcome_failure` `on_no` in `autodev.yaml:408-411` from `detect_children` to `check_missing_artifacts`
9. Add tests: extend `TestAutodevLoop` in `test_builtin_loops.py:1405–1431` for new `on_no` routing and `check_missing_artifacts` state; add `TestMissingArtifactsFlagWriteBack` to `test_confidence_check_skill.py:56–97` (clone `TestDecisionNeededFlagWriteBack`); add `TestIssueInfoMissingArtifacts` to `test_issue_parser.py:1567–1695`; add show --json fixture test to `test_issues_cli.py:1778–1806`
10. Run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_confidence_check_skill.py scripts/tests/test_issue_parser.py scripts/tests/test_issues_cli.py -v` to verify all routing branches

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `scripts/tests/test_builtin_loops.py:1419–1424` — change `test_triage_outcome_failure_on_no_routes_to_detect_children` to assert `on_no == "check_missing_artifacts"` (this test WILL fail after step 8; update it in the same commit)
12. Update `scripts/tests/test_builtin_loops.py:1026–1051` — add `"check_missing_artifacts"`, `"run_wire"`, `"run_refine"` to the `required` states set in `test_required_states_exist`
13. Update `docs/guides/LOOPS_GUIDE.md:447–471` — update autodev state-transition diagram to replace the `triage_outcome_failure.on_no → detect_children` direct arrow with a `check_missing_artifacts` gate
14. Update `docs/reference/API.md:572` — add `missing_artifacts: bool | None = None` entry to the `IssueInfo` field table (parallel to `decision_needed`)
15. Update `docs/reference/ISSUE_TEMPLATE.md:884–887` — add `missing_artifacts` row to frontmatter field reference table
16. Add `CHANGELOG.md` entry under the current release version block for ENH-1291

## Impact

- **Priority**: P3 — partial mitigation already provided by ENH-1290's size-review guard; this closes the root-cause gap
- **Effort**: Small-Medium — confidence-check write-back change + one state branch; complexity depends on signal design choice
- **Risk**: Low-Medium — additive routing branch; risk is in the signal accuracy (false positives route to wire-issue unnecessarily)
- **Breaking Change**: No

## Scope Boundaries

- Depends on ENH-1288 landing first (adds `triage_outcome_failure` state)
- Does not change scoring heuristics in `confidence-check` Phase 4.5
- Does not affect interactive mode of `issue-size-review`
- The signal field choice (Option A vs B) is a prerequisite decision, not in-scope for this issue

## Labels

`enhancement`, `autodev`, `confidence-gate`, `decision-needed`, `captured`

## Session Log
- `/ll:manage-issue` - 2026-04-26T19:10:04Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d211d4f-f1d8-4a29-9f50-85adebe7732d.jsonl`
- `/ll:ready-issue` - 2026-04-26T19:00:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b325675f-b3ae-444d-b2b4-88d7c1ad5ecb.jsonl`
- `/ll:confidence-check` - 2026-04-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/84ed300f-c8c4-4b7c-bf98-d91ef8d41d22.jsonl`
- `/ll:wire-issue` - 2026-04-26T17:57:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53f29de7-a495-4436-a6ba-875a61a2fb9e.jsonl`
- `/ll:refine-issue` - 2026-04-26T17:51:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e3cd439-de9c-48bd-8022-1bd9294bc1c2.jsonl`
- `/ll:decide-issue` - 2026-04-26T17:24:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42fabf89-9803-43b2-ae07-b91aa0889500.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T17:22:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83033e3d-e46b-42e3-9b93-f788f6f5fee1.jsonl`
- `/ll:format-issue` - 2026-04-26T17:20:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ca7be1e-da8b-4aa2-922c-a8891aadd970.jsonl`
- `/ll:capture-issue` - 2026-04-25T19:14:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d254d7af-8d9d-458c-aec5-e845416d235d.jsonl`

## Resolution

Implemented Option A (`missing_artifacts: true`) as selected by `/ll:decide-issue`.

**Changes made**:
- `scripts/little_loops/issue_parser.py` — added `missing_artifacts: bool | None = None` field to `IssueInfo` dataclass with full parsing, serialization, and deserialization (cloned `decision_needed` pattern at lines 248, 284, 313, 414–422)
- `scripts/little_loops/cli/issues/show.py` — added `missing_artifacts` extraction and lowercase-string serialization in `_parse_card_fields()` (cloned `decision_needed` pattern)
- `skills/confidence-check/SKILL.md` — added Phase 4.7 (Missing-Artifacts Flag) after Phase 4.6; signal phrases: "not yet created", "does not exist", "needs wiring", "missing artifact", "absent", "unwired component"
- `scripts/little_loops/loops/autodev.yaml` — added `run_wire`, `run_refine`, `check_missing_artifacts` states; updated `triage_outcome_failure.on_no` from `detect_children` to `check_missing_artifacts`
- `docs/guides/LOOPS_GUIDE.md` — updated state-transition diagram and narrative
- `docs/reference/API.md` — added `missing_artifacts` field to `IssueInfo` reference table
- `docs/reference/ISSUE_TEMPLATE.md` — added `missing_artifacts` row to frontmatter field reference table
- `CHANGELOG.md` — added ENH-1291 entry

**Tests**: 24 new tests across 4 test files; 534 total passed, 0 failures.

---

**Completed** | Created: 2026-04-25 | Completed: 2026-04-26 | Priority: P3
