---
captured_at: '2026-05-01T17:33:26Z'
discovered_date: 2026-05-01
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
decision_needed: true
size: Very Large
status: done
---

# FEAT-1310: verify-issue-loop skill (FSM loop generator from issue acceptance criteria)

## Summary

Create a new skill `/ll:verify-issue-loop` that mirrors `/ll:create-eval-from-issues` but emits an FSM loop YAML instead of an eval harness. Given an issue ID, the skill reads its acceptance criteria and synthesizes a custom loop where each criterion becomes a dedicated verify-state.

## Motivation

`/ll:create-eval-from-issues` generates eval harnesses (which exercise a feature as a user would and judge the quality of the experience). There is no parallel command for generating an FSM loop that *verifies* the implementation by stepping through each acceptance criterion. Today, authors of verification loops have to hand-build YAML, copy boilerplate, and manually decompose acceptance criteria into checks — losing the structured, criterion-by-criterion traceability that issue files already encode.

A `verify-issue-loop` skill closes that gap: one issue ID in, one ready-to-run verification loop out, with one verify-state per criterion.

## Current Behavior

There is no skill that generates an FSM verification loop from an issue's acceptance criteria. `/ll:create-eval-from-issues` produces eval harnesses (which exercise a feature as a user would), but verification loops must be hand-built — authors copy YAML boilerplate and manually decompose criteria into checks, losing the structured per-criterion traceability the issue file already encodes.

## Use Case

Author has just finished implementing FEAT-1234 with five acceptance criteria. They run:

```
/ll:verify-issue-loop FEAT-1234
```

The skill resolves the issue, extracts the five acceptance criteria, and writes `.loops/verify-FEAT-1234-<slug>.yaml`. The generated loop contains:

- One `verify-criterion-N` state per criterion, each with a focused prompt scoped to that single criterion and a structured pass/fail evaluator.
- Linear or fan-out transitions between verify-states (linear by default).
- A terminal `done` state when all verify-states pass; a terminal `failed` state when any criterion fails (with a captured reason).

The author then runs `ll-loop run .loops/verify-FEAT-1234-<slug>.yaml` and gets a per-criterion verification report.

## Expected Behavior

- Argument: `<issue-id>` (single ID for v1; multi-issue support deferred).
- Resolves the issue file via `ll-issues show <ID> --json`. Accepts open or completed issues.
- Reads the issue file and parses the Acceptance Criteria section into discrete criterion strings (e.g., bullet/numbered items).
- For each criterion, synthesizes:
  - A verify-state name (`verify-criterion-1`, `verify-criterion-2`, …).
  - A focused natural-language prompt that describes *how to confirm this specific criterion* against the current codebase / runtime.
  - An `llm_structured` evaluator with pass/fail (and a short reason) scoped to just that criterion.
- Wires verify-states sequentially: state N transitions to state N+1 on pass, to a shared `failed` state on fail. Final pass transitions to `done`.
- Writes the loop YAML to `.loops/verify-<ISSUE-ID>-<slug>.yaml`.
- Validates the generated file with `ll-loop validate` and reports the result, mirroring the create-eval-from-issues UX.
- If the issue has no Acceptance Criteria section (or it is empty), fail clearly with guidance to run `/ll:refine-issue` or `/ll:format-issue` first.

## API/Interface

New skill: `skills/verify-issue-loop/SKILL.md`

```
/ll:verify-issue-loop <issue-id>
```

- `argument-hint: "<issue-id>"`
- `allowed-tools`: `Bash(ll-issues:*, ll-loop:*, mkdir:*)`, `Read`, `Write`
- Output file path: `.loops/verify-<ISSUE-ID>-<slug>.yaml`
- Help/registry entry added to `/ll:help` index in CLAUDE.md (Automation & Loops group).

## Implementation Steps

1. Scaffold `skills/verify-issue-loop/SKILL.md` by copying `skills/create-eval-from-issues/SKILL.md` as a starting point.
2. Replace harness-generation logic with FSM loop generation:
   - Reuse the issue resolution + parsing block (`ll-issues show ... --json`, then read file).
   - Extract Acceptance Criteria into a list (handle `- `, `* `, and `1.` styles).
   - Synthesize verify-state nodes: name, prompt, `llm_structured` evaluator.
   - Wire transitions (linear pass-chain, shared `failed` terminal, `done` terminal).
3. Use existing FSM loop schema (see other YAMLs under `.loops/` and `loops/` for shape — states, transitions, evaluators).
4. Write the YAML, then run `ll-loop validate <path>` and surface validation output.
5. Add registration: append the skill to `.claude/CLAUDE.md` "Automation & Loops" line and ensure `/ll:help` discovers it (skills are auto-discovered via `skills/*/SKILL.md` glob — verify no extra wiring needed).
6. Tests: add a unit/integration test in `scripts/tests/` that runs the skill against a fixture issue with N acceptance criteria and asserts the generated YAML has N verify-states + `done` + `failed`, and passes `ll-loop validate`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `commands/help.md` — add `verify-issue-loop` stanza to the "AUTOMATION & LOOPS" verbose block (parallel to `create-eval-from-issues`) and append `verify-issue-loop` to the `Automation & Loops:` quick-reference comma list. **Note**: `/ll:help` does NOT auto-discover skills — `commands/help.md` is a fully static file; the assumption in step 5 ("skills are auto-discovered — verify no extra wiring needed") was incorrect for the `/ll:help` output.
8. Update skill count from `29` to `30` in: `README.md` (`` `29 skills` `` line), `CONTRIBUTING.md` (`29 skill definitions` line), and `docs/ARCHITECTURE.md` (Mermaid node `SKL[Skills<br/>29 composable skills]` and directory tree). All four spans are enforced by `ll-verify-docs` via `verify_documentation()` — the CI check will fail after the new skill is added if these are not updated.
9. Insert `verify-issue-loop/` entry into `CONTRIBUTING.md`'s explicit alphabetical skill directory tree (between `wire-issue/` and `workflow-automation-proposer/`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Acceptance Criteria parsing is LLM-driven, not Python-driven.** The sibling skill `skills/create-eval-from-issues/SKILL.md` (Step 2) instructs the executing agent to Read the issue file directly and extract `## Acceptance Criteria` by markdown heading. No reusable Python parser exists for freeform AC bullet text: `scripts/little_loops/issue_parser.py::IssueParser._parse_section_items()` only extracts issue-ID references (regex `^[-*]\s+\*{0,2}([A-Z]+-\d+)`), which is unsuitable for criterion strings. Implementation should mirror the SKILL-embedded LLM extraction pattern, not introduce a new parser.
- **YAML emission is template-string Write, not a YAML library.** The sibling skill authors YAML as a literal template inside the SKILL.md, filled in by the LLM and written via the `Write` tool. Do the same — one `verify-criterion-N` block per criterion, then a single `failed:` and `done:` terminal block at the end.
- **`action_type: prompt` is the right shape** for verify states (no shell action needed). See `scripts/little_loops/loops/fix-quality-and-tests.yaml:13-25`. Each verify state should set `action: "Verify that <criterion>"`, `action_type: prompt`, and `evaluate.type: llm_structured` with a yes/no prompt scoped to that criterion.
- **Routing convention**: use `on_yes: verify-criterion-<N+1>` and `on_no: failed` for each verify state. The final verify state uses `on_yes: done`. Both `done` and `failed` are `terminal: true`. Pattern confirmed across `harness-single-shot.yaml`, `refine-to-ready-issue.yaml`, and `eval-driven-development.yaml`.
- **Validation library import**: tests should `from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm`. CLI validation goes through `scripts/little_loops/cli/loop/info.py` (the `ll-loop validate` subcommand).
- **Output directory clarification**: write to `.loops/verify-<ISSUE-ID>-<slug>.yaml` (project-local user-generated). Bundled loops live at `scripts/little_loops/loops/*.yaml` — do not write there.
- **FEAT-1308 status**: completed (file `.issues/completed/P3-FEAT-1308-loop-yaml-template-inheritance-via-from-field.md`). The Scope Boundary note about `from: verify-issue-base` is now actionable rather than deferred — though the issue still allows a standalone-YAML first pass; verify whether using `from:` from day one is feasible before scaffolding.

## Integration Map

### Files to Modify
- `skills/verify-issue-loop/SKILL.md` — New skill file to create (scaffold from `skills/create-eval-from-issues/SKILL.md`)
- `.claude/CLAUDE.md` — Append skill name to the "Automation & Loops" line in the Commands & Skills section (around line 56 of CLAUDE.md)

### Dependent Files (Callers/Importers)
- None — this is a new top-level skill. Skills are discovered automatically via the `skills/*/SKILL.md` glob and invoked by user as `/ll:verify-issue-loop`. No code imports or callers to update.

### Similar Patterns
- `skills/create-eval-from-issues/SKILL.md` — **Primary template**. Mirror its structure end-to-end: frontmatter (allowed-tools `Bash(ll-issues:*, ll-loop:*, mkdir:*)`, `Read`, `Write`), `## Arguments` shell-snippet parser, `## Step 1: Resolve Issue Files` (`ll-issues show "$ID" --json` → use `.path`), `## Step 2: Extract Evaluation Context` (LLM reads file, extracts `## Acceptance Criteria`), `## Step 5: Generate Harness YAML` (template-string Write), `## Step 6: Write and Validate` (`ll-loop validate <name>`).
- `scripts/little_loops/loops/harness-single-shot.yaml` (lines 113–131) — Canonical `llm_structured` evaluator with `on_yes` / `on_no` / `on_partial` routing. Line 148–149 shows `done: terminal: true`. Use this as the structural template for each `verify-criterion-N` state.
- `scripts/little_loops/loops/fix-quality-and-tests.yaml` (lines 13–25) — `action_type: prompt` with embedded `llm_structured` evaluator (no shell action), which is the right shape for verify states since they only need to ask "did the implementation satisfy this criterion?".
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (lines 196–258, terminal at 337) — Linear pass-chain with shared `failed` terminal: each state routes `on_yes: <next>` and `on_no: failed`. Exact shape needed for FEAT-1310's verify chain.
- `scripts/little_loops/loops/eval-driven-development.yaml` (line 79) — Confirms the shared `failed: terminal: true` convention.

### Tests
- `scripts/tests/test_create_eval_from_issues.py` — **Test template**. Mirror its assertion patterns:
  - State presence: `assert "verify-criterion-1" in states` (lines 159–171 for the analog)
  - Evaluator shape: `assert evaluate.get("type") == "llm_structured"` and `len(prompt) > 20` (lines 173–181)
  - Routing: `assert state.get("on_yes") == "verify-criterion-N+1"` and `assert state.get("on_no") == "failed"` (lines 183–189)
  - Terminal: `assert states["done"].get("terminal") is True` and same for `failed` (lines 191–194)
  - FSM validation via library: `fsm, _ = load_and_validate(path)` then `errors = validate_fsm(fsm)`; assert no `ValidationSeverity.ERROR` (lines 339–342). Import from `little_loops.fsm.validation`.
  - CLI validation: invoke `ll-loop validate` via `mp.setattr(sys, "argv", [...])` and assert exit code 0 (lines 356–367).
- Fixture issue: create a synthetic issue with N=3 acceptance criteria under a tmp dir; assert generated YAML has exactly 3 `verify-criterion-*` states + `done` + `failed`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_issue_loop.py` — new test file to create, mirroring `test_create_eval_from_issues.py`; use inline YAML constants (no AC fixture file exists in `scripts/tests/fixtures/issues/`); should contain `TestVerifyLoopSingleIssue` (state presence, transition routing, evaluator shape) and `TestVerifyLoopValidation` (library path via `load_and_validate` + `validate_fsm`, and CLI path via `sys.argv` injection calling `main_loop()` expecting exit 0) [Agent 3 finding]

### Documentation
- N/A — Skills are auto-discovered via `skills/*/SKILL.md` glob; no doc updates required beyond the one CLAUDE.md line.

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — static skill catalog (NOT auto-generated); two locations require manual update: (1) "AUTOMATION & LOOPS" verbose block — add a stanza parallel to `create-eval-from-issues`; (2) "Quick Reference Table" `Automation & Loops:` comma-delimited list — append `verify-issue-loop` [Agent 2 finding]
- `README.md` — hardcoded `` `29 skills` `` count enforced by `ll-verify-docs` / `verify_documentation()` — update to `30` [Agent 2 finding]
- `CONTRIBUTING.md` — hardcoded `29 skill definitions` count (same enforcement) AND an explicit alphabetical skill directory tree listing — update count to `30` and insert `verify-issue-loop/` entry between `wire-issue/` and `workflow-automation-proposer/` [Agent 2 finding]
- `docs/ARCHITECTURE.md` — two occurrences of `29` (Mermaid node `SKL[Skills<br/>29 composable skills]` and directory tree) — update both to `30` [Agent 2 finding]

### Configuration
- N/A — No config changes needed.

## Acceptance Criteria

- [ ] `skills/verify-issue-loop/SKILL.md` exists with frontmatter, description, trigger keywords, and argument-hint mirroring `create-eval-from-issues`.
- [ ] Running `/ll:verify-issue-loop <ID>` against an issue with N acceptance criteria writes a YAML with exactly N verify-states.
- [ ] Each verify-state has a prompt scoped to one criterion and an `llm_structured` pass/fail evaluator.
- [ ] Verify-states transition linearly on pass; any failure transitions to a shared `failed` terminal state with reason captured.
- [ ] Final verify-state transitions to `done` on pass.
- [ ] Generated YAML passes `ll-loop validate` without errors.
- [ ] Issue with no Acceptance Criteria section produces a clear error referencing `/ll:refine-issue` / `/ll:format-issue`, and writes no file.
- [ ] Skill is listed in `/ll:help` output and CLAUDE.md "Automation & Loops" group.
- [ ] Test in `scripts/tests/` covers a multi-criterion fixture and asserts state count, transitions, and `ll-loop validate` success.

## Impact

- **Priority**: P3 - Reduces friction for verification authoring; nice-to-have, not blocking.
- **Effort**: Medium - New skill scaffold mirroring `create-eval-from-issues` + criterion parser + FSM emitter + `ll-loop validate` integration + fixture-based test.
- **Risk**: Low - Generates a new YAML file; does not modify existing skills or runtime behavior.
- **Breaking Change**: No - Purely additive.

## Labels

feature, skill, verification, fsm, loops, learning-testing, captured

## Related Key Documentation

| Document | Relevance |
|---|---|
| `skills/create-eval-from-issues/SKILL.md` | Sibling skill to mirror — argument parsing, issue resolution, YAML emission, `ll-loop validate` UX |
| `docs/ARCHITECTURE.md` | FSM loop architecture and state/transition model |
| `.claude/CLAUDE.md` | Skill registration / Automation & Loops grouping |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-11 (re-run after `/ll:decide-issue`)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- **Low pre-implementation test coverage**: `scripts/tests/test_verify_issue_loop.py` is itself a deliverable — the implementation phase has no automated catch for regressions in generated YAML shape or routing until the test is written alongside the skill.
- **Open decision — `from:` inheritance vs standalone YAML**: `decision_needed: true` is still set in frontmatter despite `/ll:decide-issue` having run. FEAT-1308 is complete and `apo-beam.yaml` demonstrates the `from:` pattern. Resolve this before writing the first line of SKILL.md — check `scripts/little_loops/fsm/fragments.py` or a FEAT-1308 completed loop YAML to confirm `from:` is viable.

## Session Log
- `/ll:issue-size-review` - 2026-05-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/03785380-ad15-4700-be73-f3d5f0c746ce.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adfe3ad7-7b51-4cab-883a-1b34cd1d982f.jsonl`
- `/ll:decide-issue` - 2026-05-11T23:06:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/acff6b8e-720e-493f-ac80-47e74f906b77.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c72b779c-abe8-4a10-a8ec-4d5c63f48a8e.jsonl`
- `/ll:wire-issue` - 2026-05-11T23:00:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1726baf4-57db-44d2-8634-da26718af849.jsonl`
- `/ll:refine-issue` - 2026-05-11T22:56:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7bc7ca3f-067f-4222-a0a9-dc00eb0dc50a.jsonl`
- `/ll:format-issue` - 2026-05-11T20:30:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a07d6155-3a77-4261-82da-bcebc9ff9d11.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:format-issue` - 2026-05-01T17:38:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1483ec77-4cf9-4aca-8312-065f15a52a5f.jsonl`
- `/ll:capture-issue` - 2026-05-01T17:33:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a6d2d86-ddb4-4191-bb20-7505a1373a52.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-11
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1446: verify-issue-loop — core skill implementation
- FEAT-1447: verify-issue-loop — wiring & doc count updates

---

## Status
- **Status**: Done
- **Discovered**: 2026-05-01
- **Discovered by**: capture-issue

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, 2026-05-01): Once FEAT-1308 (loop YAML `from:` template inheritance) lands, the YAML emitted by this skill SHOULD use `from: verify-issue-base` (or similar shared base loop) and override only the per-criterion verify states, instead of emitting fully-expanded ~100-line YAML each time. If FEAT-1310 ships before FEAT-1308, the initial implementation may emit standalone YAML, but a follow-up should refactor the emitter to use inheritance. Do not block FEAT-1310 on FEAT-1308.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): `verify-criterion-N` states generated by this skill are standard FSM states using existing state constructs — they introduce NO new `type:` enum value. This is intentionally distinct from the `type: learning` FSM state type introduced by FEAT-1283. If a `type: verify` FSM state type is ever proposed in the future, its naming must be coordinated with FEAT-1283's `type: learning` convention to avoid ambiguity in the FSM schema.
