---
id: ENH-2215
title: create-loop wizard auto-insert assumption-firewall gate for external API loops
type: enhancement
priority: P3
status: done
parent: EPIC-2207
depends_on: ENH-2220
captured_at: '2026-06-18T15:38:06Z'
completed_at: '2026-06-19T14:34:51Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 72
score_complexity: 17
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 20
decision_needed: false
implementation_order_risk: true
---

# ENH-2215: create-loop wizard auto-insert assumption-firewall gate for external API loops

## Summary

The `/ll:create-loop` wizard generates loop templates based on the user's intent but does not ask whether the loop involves external APIs. Add a wizard question in the "Harness a skill" branch: "Does this loop invoke external packages or third-party APIs?" If yes, auto-insert a pre-wired `assumption-firewall` sub-loop call before the main implementation state, with a `targets` context variable placeholder.

## Motivation

Loop authors writing integration loops currently must manually wire assumption-firewall if they want proof-first gating. The wizard is the ideal place to shift this left: ask once, insert the boilerplate, and leave only the `targets` list for the author to fill in.

## Integration Map

### Files to Modify
- `skills/create-loop/loop-types.md` — Primary change surface: add Step H5 question to `## Harness Questions` section after H4 ("Does this loop call external packages or APIs?"); add conditional `assumption_gate` + `blocked` state block to the `## Generate Harness FSM YAML` section using `# include if external APIs selected` annotation style (matching H3's optional state pattern)
- `skills/create-loop/SKILL.md` — Update wizard overview if Step H5 needs to appear in the top-level step listing

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Heading reads `## Creating a Harness: The 4-Step Wizard` with TOC entries for H1–H4 only; adding H5 makes this guide's step count and `### Step H4: Iteration Budget` (implies H4 is final) inaccurate; also contains a `See Also` line-range reference to `loop-types.md` that will be stale after the file grows

### Similar Patterns
- `skills/create-eval-from-issues/SKILL.md` — Canonical pattern for conditional `learning_tests_required` check + YAML state injection (see "Proof-First Gate Config" and "Variant A — Proof-First Gates" sections): uses `learning_tests.enabled` config guard, `python3 -c` for `.ll/ll-config.json` read, then conditional state injection
- `skills/create-loop/loop-types.md:Step H3` — How `# include if <condition>` comments mark conditional states in generated YAML; how routing adapts when states are omitted
- `skills/create-loop/loop-types.md:Step S3.5` — How commented-out optional blocks preserve discoverability when user answers "no" (alternative approach for `assumption_gate`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/proof-first-task.yaml` — Shows correct `loop:` sub-loop invocation form with `with: {input: ...}` for calling `assumption-firewall`; the issue's current step 2 YAML uses an incorrect shell-action form

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/assumption-firewall.yaml` — The sub-loop invoked by the generated `assumption_gate` state; declares `context.input` (not `context.issue_file`) confirming the `loop:` + `with: {input: "${context.issue_file}"}` invocation form in the generated YAML

### Tests
- `scripts/tests/test_create_loop.py` — Add new test classes following the `TestEvalHarnessVariantAWithProofGates` / `TestEvalHarnessVariantAWithoutLearningTests` pattern from `scripts/tests/test_create_eval_from_issues.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_loop.py` — Add `TestHarnessVariantAWithAssumptionGate`: assert `assumption_gate` state exists, `assumption_gate.loop == "assumption-firewall"`, `assumption_gate.with.input == "${context.issue_file}"`, routes `on_failure`/`on_error` → `blocked`, `blocked.terminal == true`; validate via `load_and_validate` + `validate_fsm` from `little_loops.fsm.validation`
- `scripts/tests/test_create_loop.py` — Add `TestHarnessVariantAWithoutAssumptionGate`: regression — when H5 = "no" or `learning_tests.enabled=false`, assert `assumption_gate` and `blocked` states are absent and `initial` routes unchanged
- `scripts/tests/test_wiring_skills_and_commands.py` — Add 2 entries to `DOC_STRINGS_PRESENT` parametrized list: `("skills/create-loop/loop-types.md", "assumption_gate", "ENH-2215")` and `("skills/create-loop/loop-types.md", "assumption-firewall", "ENH-2215")`

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — May need update to mention wizard auto-insert behavior for external API loops

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `### /ll:create-loop` section describes the wizard flow (4 outer phases); does not mention the external-API question; advisory update if the section is meant to be comprehensive

### Configuration
- `.ll/ll-config.json` → `learning_tests.enabled` — Must be checked before the wizard question or auto-insert (matching `create-eval-from-issues` and `scope-epic` patterns)

## Implementation Steps

1. In the `/ll:create-loop` skill (wizard branch for "Harness a skill"), after the loop name/description questions, add: "Does this loop call external packages or APIs (e.g., Anthropic SDK, HTTP APIs, database drivers)? [y/n]"
2. If yes:
   - Inject an `assumption_gate` state before the first implementation state:
     ```yaml
     assumption_gate:
       type: shell
       action: "ll-loop run assumption-firewall --context issue_file=${context.issue_file}"
       on_exit:
         0: implement   # done
         1: blocked     # blocked
     blocked:
       type: terminal
       message: "External API assumptions unproven. Run /ll:explore-api for each dependency."
     ```
   - Set `context.issue_file` as a required context variable in the loop header comment.
3. Add to `create-loop` skill docs: "The assumption-firewall gate requires the issue file path in context (`issue_file`)."

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — rename `## Creating a Harness: The 4-Step Wizard` to `5-Step Wizard`, add `[Step H5: External API Gate](#step-h5-external-api-gate)` to the TOC, add `### Step H5: External API Gate` subsection, and update the `See Also` line-range reference to `loop-types.md`
5. Add to `scripts/tests/test_create_loop.py` — `TestHarnessVariantAWithAssumptionGate` and `TestHarnessVariantAWithoutAssumptionGate` classes (follow `TestEvalHarnessVariantAWithProofGates` / `TestEvalHarnessVariantAWithoutLearningTests` pattern from `test_create_eval_from_issues.py`; import `load_and_validate`, `validate_fsm` from `little_loops.fsm.validation`)
6. Add to `scripts/tests/test_wiring_skills_and_commands.py` — 2 `DOC_STRINGS_PRESENT` entries: `assumption_gate` and `assumption-firewall` in `skills/create-loop/loop-types.md`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correct `assumption_gate` YAML — use `loop:` sub-loop form, not shell action.** The issue's Step 2 shows `action: "ll-loop run assumption-firewall --context issue_file=..."` (shell-action form). The canonical pattern from `scripts/little_loops/loops/proof-first-task.yaml` (gate state) and `scripts/little_loops/loops/assumption-firewall.yaml` (which declares `context.input`, not `context.issue_file`) requires the `loop:` sub-loop form:

```yaml
assumption_gate:
  loop: assumption-firewall
  with:
    input: "${context.issue_file}"
  on_success: implement
  on_failure: blocked
  on_error: blocked
blocked:
  terminal: true
  message: "External API assumptions unproven. Run /ll:explore-api for each dependency."
```

The shell-action invocation with `--context issue_file=` would fail because `assumption-firewall` reads `context.input`, and FSM sub-loop calls must use `loop:` + `with:` — not a `shell` action.

**Config flag guard — required before wizard question.** Add a `learning_tests.enabled` check before the Step H5 question or auto-insert, matching `skills/create-eval-from-issues/SKILL.md` ("Proof-First Gate Config"):

```bash
LT_ENABLED=$(python3 -c "
import json, pathlib
p = pathlib.Path('.ll/ll-config.json')
cfg = json.loads(p.read_text()) if p.exists() else {}
print(str(cfg.get('learning_tests', {}).get('enabled', False)).lower())")
```

If `LT_ENABLED=false`, skip the H5 question entirely and do not inject the gate.

**`learning_tests_required` short-circuit check — resolved parsing decision.** The Scope Boundary note asked whether to use `ll-issues show --json | jq` or a shared Python helper. For the skill prose, use the inline `python3 -c` pattern (matching `scripts/little_loops/loops/autodev.yaml` and `scripts/little_loops/loops/rn-remediate.yaml`):

```bash
LT_TARGETS=$(ll-issues show "${ISSUE_ID}" --json 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
v = d.get('learning_tests_required')
print(v or '')" 2>/dev/null || true)
```

`show --json` returns `learning_tests_required` as a comma-joined string or `null` (see `scripts/little_loops/cli/issues/show.py:_parse_card_fields()` line ~299). A non-empty string means the field is populated — skip the wizard question and auto-insert without prompting. The "shared Python helper" alternative (`scripts/little_loops/cli/history_context.py:_get_issue_lt_targets()`) is only applicable to Python-based callers (e.g., ENH-2217); the skill should use the bash form.

**Test pattern to follow.** `scripts/tests/test_create_eval_from_issues.py:TestEvalHarnessVariantAWithProofGates` and `TestEvalHarnessVariantAWithoutLearningTests` show exactly how to structure "with gate / without gate" YAML-literal test classes. FSM validation uses `load_and_validate` + `validate_fsm` from `little_loops.fsm`. Two new test classes in `scripts/tests/test_create_loop.py` are needed: one asserting `assumption_gate` and `blocked` states exist (and route correctly), one asserting they are absent.

## Scope Boundaries

- **In scope**: Adding a question to the create-loop wizard's "Harness a skill" branch about external API usage; auto-inserting assumption-firewall gate state and blocked terminal state when answer is yes; documenting `issue_file` context variable requirement
- **Out of scope**: Changes to the assumption-firewall loop itself; modifications to other wizard branches; retroactive insertion of gates into existing loops; changes to how existing loops are stored or migrated

## Impact

- **Priority**: P3 - Medium priority; quality-of-life improvement for loop authors using external APIs
- **Effort**: Small - Single wizard question + conditional YAML injection in the create-loop skill
- **Risk**: Low - Non-breaking change; only affects generated output when user answers "yes"
- **Breaking Change**: No

## Acceptance Signals

- A loop created with "yes" to external APIs includes an `assumption_gate` state
- `ll-loop validate` passes on the generated YAML
- The `blocked` terminal state is reachable (MR-4 compliant — `on_no`/`on_partial` covered)
- A loop created with "no" to external APIs is unchanged from current output

## Labels

`enhancement`, `wizard`, `create-loop`, `assumption-firewall`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue coordinates with ENH-2220 (scope-epic). When the wizard is run from a sub-issue created by ENH-2220's scope-epic flow, it should read `learning_tests_required` from the issue's frontmatter (already populated by ENH-2220) rather than asking the user a duplicate "does this involve external APIs?" question. See [[ENH-2220]] for the scope-epic data pipeline.

**Note** (added by `/ll:audit-issue-conflicts`): The wizard must skip the "does this involve external APIs?" question whenever `learning_tests_required` is present and non-empty in the issue's frontmatter — regardless of which skill populated it. ENH-2220 (scope-epic) and ENH-2209 (refine-issue/wire-issue) are both valid sources. The prior scope note's "when the wizard is run from a sub-issue created by ENH-2220" phrasing is too narrow: a user who refines an issue via ENH-2209 and then runs create-loop would still be asked the redundant question. Check: if `learning_tests_required` is non-empty in frontmatter, auto-insert the assumption-firewall gate without prompting. See [[ENH-2209]].

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2215 and ENH-2217 both parse `learning_tests_required` from issue frontmatter independently. To prevent divergent field-name handling or fallback logic, both should use the same read mechanism: either `ll-issues show --json <ISSUE_ID> | jq '.learning_tests_required // []'` or a shared Python helper. Coordinate with [[ENH-2217]] to avoid two divergent parsing implementations.

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-19 (prior check: 2026-06-18)_

**Readiness Score**: 95/100 → PROCEED (↑ from 88)
**Outcome Confidence**: 72/100 → MODERATE (↑ from 70)

### Outcome Risk Factors
- **Test coverage gap**: `TestHarnessVariantAWithAssumptionGate` and `TestHarnessVariantAWithoutAssumptionGate` are co-deliverables — implement test classes alongside wizard changes to avoid leaving the assumption_gate injection path uncovered
- **Multi-file coordination surface**: 5 files across 3 subsystems; AUTOMATIC_HARNESSING_GUIDE.md doc update is advisory but user-facing — explicitly track it to avoid being skipped under time pressure

## Session Log
- `/ll:ready-issue` - 2026-06-19T14:22:35 - `220cccb1-6afc-448d-b998-fe9d27e4aec4.jsonl`
- `/ll:confidence-check` - 2026-06-19T00:00:00Z - `3611f651-efaa-4344-9ac6-5913120f04b7.jsonl`
- `/ll:wire-issue` - 2026-06-19T14:14:53 - `55c143d3-5a62-4f13-811c-f163a4f22338.jsonl`
- `/ll:refine-issue` - 2026-06-19T13:58:15 - `bda0b039-dde6-4f11-8ae3-4e6571f5be24.jsonl`
- `/ll:confidence-check` - 2026-06-18T00:00:00Z - `ba01ebda-9b55-48e3-a4d0-95c052e2a66f.jsonl`
- `/ll:decide-issue` - 2026-06-19T04:39:25 - `d5f66b54-9071-4911-b643-659288034a28.jsonl`
- `/ll:confidence-check` - 2026-06-18T00:00:00Z - `c6102fe7-10de-413b-a21c-9b13c3dce608.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T21:17:06 - `23eb26e5-163c-41e9-bc83-173b75524706.jsonl`
- `/ll:format-issue` - 2026-06-18T19:32:29 - `0ad50852-04aa-49ce-b1bf-d489adb4f465.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

**Done** | Created: 2026-06-18 | Priority: P3

## Resolution

Implemented Step H5 ("External API Gate") in the create-loop wizard's "Harness a skill" branch:

- **`skills/create-loop/loop-types.md`**: Added Step H5 with `learning_tests.enabled` config guard, `learning_tests_required` frontmatter check (auto-insert without asking), and `AskUserQuestion` flow. Updated Variant A and B `Generate Harness FSM YAML` sections with `assumption_gate` + `blocked` states using correct `loop:` sub-loop form.
- **`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`**: Renamed "4-Step Wizard" to "5-Step Wizard", added Step H5 to TOC and added `### Step H5: External API Gate` subsection.
- **`scripts/tests/test_create_loop.py`**: Added `TestHarnessVariantAWithAssumptionGate` (10 assertions + FSM validation) and `TestHarnessVariantAWithoutAssumptionGate` (regression).
- **`scripts/tests/test_wiring_skills_and_commands.py`**: Added 2 `DOC_STRINGS_PRESENT` entries for `assumption_gate` and `assumption-firewall` in `loop-types.md`.
