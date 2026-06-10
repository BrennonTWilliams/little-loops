---
id: FEAT-2078
title: Add distill-traces skill to extract reusable loop fragments from history
type: FEAT
priority: P3
status: open
captured_at: '2026-06-10T18:12:09Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
confidence_score: 97
outcome_confidence: 70
score_complexity: 17
score_test_coverage: 12
score_ambiguity: 18
score_change_surface: 23
---

# FEAT-2078: Add distill-traces skill to extract reusable loop fragments from history

## Motivation

Successful loop execution traces already exist in `.ll/history.db` and ll-logs, but no skill mines them into reusable loop YAML fragments or Python helpers. Distilling behavioral traces into a small reference library — rather than documenting strategy in prose — gives future loop runs a concrete scaffold to build on.

## Use Case

A developer wants to reuse patterns from past successful runs of `rn-plan`. They invoke `/ll:distill-traces rn-plan --min-success 3` and receive YAML state templates and transition patterns in `loops/lib/rn-plan/`, along with a `primitives.md` summary they can reference when authoring or modifying the loop.

## Proposed Solution

Create a `ll:distill-traces` skill that:
1. Queries `ll-session` for successful runs of a named loop
2. Extracts the action sequences and shell primitives used across those runs
3. Writes reusable YAML fragments (state templates, common transition patterns) to `loops/lib/<loop-name>/`
4. Accepts a loop name and a minimum success count threshold
5. Produces a `primitives.md` summary alongside the YAML fragments
6. Optionally updates loop-suggester's context with the extracted patterns

## Implementation Steps

1. Create `skills/distill-traces/SKILL.md` with invocation spec and argument docs
2. Implement query logic against `ll-session search` / `ll-session recent` for successful loop runs
3. Parse action sequences from run transcripts to extract reusable state patterns
4. Write YAML fragment files to `loops/lib/<loop-name>/` with a `primitives.md` index
5. Add optional `--update-suggester` flag to push extracted patterns into loop-suggester context

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Reconcile skill count annotations — update `README.md`, `CONTRIBUTING.md`, and `docs/ARCHITECTURE.md` (mermaid node + tree comment) to the correct count now that `distill-traces/SKILL.md` is present on disk
7. Add CHANGELOG entry for `distill-traces` in the appropriate versioned release block
8. Update `scripts/tests/test_wiring_guides_and_meta.py` — bump the `DOC_STRINGS_PRESENT` entries that assert the old skill count so tests pass again; add a new entry asserting `"distill-traces"` is present in `docs/guides/LOOPS_GUIDE.md`

## Integration Map

### Files to Modify

- `skills/distill-traces/SKILL.md` — primary skill definition (invocation spec, argument docs, step-by-step logic)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `commands/loop-suggester.md` — references `distill-traces` as a keyword signal in the `loops-automation` workflow theme catalog [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

**Already updated (wired by FEAT-2089):**
- `.claude/CLAUDE.md` — `distill-traces`^ listed in Automation & Loops bullet [Agent 2 finding]
- `docs/reference/COMMANDS.md` — `/ll:distill-traces` subsection with argument spec and usage examples [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — "Reusable State Fragments" section references `distill-traces` and its three output paths [Agent 2 finding]
- `docs/ARCHITECTURE.md` — skills directory tree entry `distill-traces/` added [Agent 2 finding]

**Still needs updating (skill count annotation):**
- `README.md` — `**37 skills**` → `**38 skills**` (actual dir count: 65 including bridge skills; non-bridge count needs reconciliation) [Agent 2 finding]
- `CONTRIBUTING.md` — `# 37 skill definitions` in directory tree → bumped count [Agent 2 finding]
- `docs/ARCHITECTURE.md` — mermaid node `SKL[Skills<br/>37 composable skills]` and `# 37 skill definitions` comment → bumped count [Agent 2 finding]
- `CHANGELOG.md` — no entry exists for `distill-traces` in any versioned release block [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Existing coverage:**
- `scripts/tests/test_distill_traces_skill.py` — 17 structural keyword-presence assertions against `SKILL.md`; covers: loop_name arg, `--min-success`, `disable-model-invocation`, `state.json`/`events.jsonl` sources, fragment schema, `state-templates.yaml`/`transitions.yaml` outputs, `lib/` path, `primitives.md`, graceful degradation, default min-success of 3, `.loops/.history/` reference [Agent 1 finding]

**Tests that will break when skill count is updated:**
- `scripts/tests/test_wiring_guides_and_meta.py` — `DOC_STRINGS_PRESENT` entries at line 22 expects `"64 skills"` in `README.md`; must be bumped to match actual count when doc annotations are fixed [Agent 3 finding]
- `scripts/tests/test_doc_counts.py` — `verify_documentation()` scans `skills/*/SKILL.md` at runtime and compares against doc-embedded count; will report mismatch until doc count annotations are reconciled [Agent 3 finding]

**New tests to write:**
- `scripts/tests/test_wiring_guides_and_meta.py` — add `DOC_STRINGS_PRESENT` entry asserting `"distill-traces"` is present in `docs/guides/LOOPS_GUIDE.md` [Agent 3 finding]
- Behavioral fixture test: create synthetic `state.json` + `events.jsonl` in `tmp_path` and verify that the Step 3–4 extraction logic (aggregating `state_enter`/`route` events) produces correct fragment structure; follow pattern in `scripts/tests/test_fsm_persistence.py` using `list_run_history()`/`get_archived_events()` [Agent 3 finding]

## Acceptance Criteria

- [ ] `ll:distill-traces <loop-name>` queries history and outputs YAML fragments
- [ ] `loops/lib/<loop-name>/primitives.md` is created/updated with extracted patterns
- [ ] `--min-success N` threshold parameter filters runs
- [ ] Skill gracefully handles loops with no successful history

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-10_

**Readiness Score**: 97/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors

- **Structural-only test coverage**: All 17 tests assert keyword presence in `SKILL.md` but no test invokes the skill against real `.loops/.history/` data. Behavioral correctness of the Step 3 event-sequence extraction (aggregating `state_enter` / `route` events) and Step 4 fragment inference must be validated manually on first real invocation.

## Session Log
- `/ll:wire-issue` - 2026-06-10T23:31:54 - `20d6c357-b807-4649-87f0-e98fb94ab6bf.jsonl`
- `/ll:confidence-check` - 2026-06-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5554767c-b2ff-40bb-b645-1a85db3c31f7.jsonl`

## Status

open
