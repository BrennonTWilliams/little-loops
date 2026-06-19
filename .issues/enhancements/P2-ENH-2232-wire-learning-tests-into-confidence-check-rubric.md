---
id: ENH-2232
title: Wire learning tests into confidence-check rubric
type: ENH
status: done
priority: P2
captured_at: '2026-06-19T21:33:27Z'
completed_at: '2026-06-19T22:48:17Z'
discovered_date: 2026-06-19
discovered_by: capture-issue
labels:
- enhancement
- skill
- confidence-check
- learning-tests
decision_needed: false
confidence_score: 98
outcome_confidence: 82
score_complexity: 19
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 20
---

# ENH-2232: Wire learning tests into confidence-check rubric

## Summary

Add a learning test pre-fetch step to `/ll:confidence-check` (parallel to the existing `go-no-go` Step 3a.5) so that unproven `learning_tests_required` targets surface as a Readiness Score penalty and STOP signal before implementation begins.

## Current Behavior

`/ll:confidence-check` does not read `learning_tests_required` from issue frontmatter and performs no learning test status checks. Unproven external API assumptions silently pass through the readiness gate when users invoke `confidence-check` instead of `go-no-go`.

## Expected Behavior

After this enhancement, `/ll:confidence-check` reads `learning_tests_required`, runs `ll-learning-tests check "<target>"` per declared target, builds a **Learning Test Context** block, and injects it into Phase 2. Missing or refuted targets apply a −10 point penalty and force a **STOP — ADDRESS GAPS** recommendation regardless of aggregate score; stale targets apply −5 points. Issues without `learning_tests_required` are unaffected.

## Motivation

`/ll:go-no-go` already fetches learning test status and injects a **Learning Test Context** block into its adversarial agents (Step 3a.5 in `skills/go-no-go/SKILL.md`). `/ll:confidence-check` — the gate users explicitly invoke before implementation — has zero references to learning tests. This parity gap means unproven external API assumptions can silently bypass the feature when a user runs `confidence-check` instead of `go-no-go`. Since `confidence-check` is the lighter-weight, more frequently invoked gate, closing this gap has the widest reach.

## Acceptance Criteria

- [ ] After Phase 1 context gathering, `confidence-check` reads the issue's `learning_tests_required` frontmatter field
- [ ] For each declared target, `ll-learning-tests check "<target>"` is executed and results are collected
- [ ] A **Learning Test Context** block (matching the `go-no-go` format) is built when `learning_tests_required` is present and non-empty
- [ ] The block is injected into Phase 2 assessment context
- [ ] Any `missing` or `refuted` target applies a −10 point penalty to the Readiness Score (Criterion 1: preconditions not met)
- [ ] Any `stale` target applies a −5 point penalty to the Readiness Score
- [ ] If any target is `missing` or `refuted`, the final recommendation is forced to **STOP — ADDRESS GAPS** regardless of other scores
- [ ] When `learning_tests_required` is absent or empty, the block is omitted entirely (no placeholder)
- [ ] `Bash(ll-learning-tests:*)` is added to the skill's `allowed-tools` frontmatter

## Scope Boundaries

- **In scope**: Modifying `skills/confidence-check/SKILL.md` (Phase 1.5 addition, Phase 2 Criterion 1 update, Phase 3 STOP override) and `skills/confidence-check/rubric.md` (Learning Test Status scoring row)
- **Out of scope**: Modifying `go-no-go` (already has this feature), `ll-learning-tests` CLI behavior, `ll:ready-issue`, or any other gate that does not use the confidence-check rubric

## Success Metrics

- Running `/ll:confidence-check` on an issue with a `missing` learning test target produces **STOP — ADDRESS GAPS** (was: score unaffected, no STOP forced)
- Running `/ll:confidence-check` on an issue with a `stale` target shows a −5 point deduction on the Readiness Score
- Running `/ll:confidence-check` on an issue without `learning_tests_required` produces unchanged behavior (regression-free)

## Implementation Steps

1. **Add `Bash(ll-learning-tests:*)` to `skills/confidence-check/SKILL.md` frontmatter** `allowed-tools` list
2. **Insert Phase 1.5 in `SKILL.md`** — after the `HIST` fetch (line ~113), add a `### Phase 1.5: Pre-Fetch Learning Test Context` step mirroring `go-no-go` Step 3a.5:
   - Read `learning_tests_required` from issue frontmatter (use `ll-issues show` or grep frontmatter)
   - Run `ll-learning-tests check "<target>"` per target
   - Assemble the Learning Test Context block table
3. **Update Phase 2 Criterion 1 in `SKILL.md`** — document that unproven/missing/refuted targets count as "preconditions not met" and specify the penalty values
4. **Update `skills/confidence-check/rubric.md`** — add a **Learning Test Status** row to the Criterion 1 scoring table with: proven=0, stale=−5, missing/refuted=−10 (forces STOP)
5. **Update Phase 3 recommendation logic in `SKILL.md`** — add a hard override: if any target is `missing` or `refuted`, output is `STOP — ADDRESS GAPS` regardless of aggregate score

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

0. **Check SKILL.md line count before inserting Phase 1.5** — run `wc -l skills/confidence-check/SKILL.md`; the file is currently at 499 lines (1 line of headroom before the 500-line limit enforced by `test_enh494_skill_companions.py::TestSkillLineLimit`). Phase 1.5 prose will almost certainly exceed the limit; place the verbose bash patterns and table in `rubric.md` and reference them from SKILL.md with a one-liner (`See rubric.md § Phase 1.5`).
6. **Write `TestConfidenceCheckLearningTestPrefetch` test class** in `scripts/tests/test_confidence_check_skill.py` — verify Phase 1.5 heading, `learning_tests_required` read, `ll-learning-tests check` call, `## Learning Test Context` table, and STOP override prose in Phase 3; mirror `TestConfidenceCheckHistoryContextInjection._phase_text()` pattern
7. **Write `TestConfidenceCheckRubricLearningTestStatus` test class** in `scripts/tests/test_confidence_check_skill.py` — read `skills/confidence-check/rubric.md` and assert `−10` and `−5` penalty rows appear
8. **Update `docs/reference/API.md` line 625** — add `confidence-check` alongside `ready-issue` as a consumer of `learning_tests_required`

## API / Interface

No public API changes. Skill behavior change: `confidence-check` now requires `Bash(ll-learning-tests:*)` and will produce STOP recommendations for issues with unproven external API assumptions.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 1.5 addition, Phase 2 Criterion 1 update, Phase 3 STOP override logic
- `skills/confidence-check/rubric.md` — add Learning Test Status row to Criterion 1 scoring table

### Dependent Files (Callers/Importers)
- `skills/go-no-go/SKILL.md` — reference implementation (read-only; mirror its Step 3a.5 pattern)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml` — invokes `/ll:confidence-check` in `assess` (line 76) and `re_assess` (line 431) states; reads `confidence_score`/`outcome_confidence` from frontmatter via `ll-issues show --json` (not text output); new −10 penalty may lower a previously-passing score below the 70 threshold [Agent 1]
- `scripts/little_loops/loops/autodev.yaml` — invokes `/ll:confidence-check` in `rerun_confidence_after_decide` and `rerun_confidence_after_wire` states; same frontmatter-score routing, text output is display-only [Agent 1]
- `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — oracle sub-loop that fires `/ll:confidence-check` and verifies `confidence` + `outcome` frontmatter keys via `verify_scores_persisted` shell state; STOP text does not affect routing [Agent 1]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — delegates confidence-check to the `verify-confidence-scores` oracle sub-loop; same score-only routing [Agent 1]
- `skills/manage-issue/SKILL.md` — invokes confidence-check in Phase 2 and gates on `readiness score >= 70`; new −10 penalty from a missing learning target can now push a previously-passing score below this gate [Agent 1, Agent 2]

### Similar Patterns
- `skills/go-no-go/SKILL.md` Step 3a.5 — identical learning test pre-fetch pattern to replicate

### Tests
- `scripts/tests/test_confidence_check_skill.py` — existing test suite for confidence-check skill; run for regression validation after changes
- Manual validation: run `/ll:confidence-check` on an issue with `learning_tests_required` containing a missing target to verify STOP behavior

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh494_skill_companions.py::TestSkillLineLimit.test_all_skills_within_limit` — **CRITICAL CONSTRAINT**: enforces 500-line limit on all `SKILL.md` files; `skills/confidence-check/SKILL.md` is currently 499 lines — inserting Phase 1.5 will exceed the limit and fail this test unless content is placed in `rubric.md` or existing SKILL.md prose is trimmed [Agent 2]
- `scripts/tests/test_confidence_check_skill.py::TestConfidenceCheckHistoryContextInjection._phase_text` — Phase 1 section boundary will shift from `### Phase 2` to `### Phase 1.5` when the new heading is inserted; existing tests (`test_ll_history_context_command_present`, `test_hist_variable_present`) still pass because the checked strings remain in Phase 1 before the new heading [Agent 2]
- New test class to write: `TestConfidenceCheckLearningTestPrefetch` in `test_confidence_check_skill.py` — assert Phase 1.5 heading exists, `learning_tests_required` read logic is present, `ll-learning-tests check` call appears, `## Learning Test Context` table header is present, STOP override prose appears in Phase 3; mirror `TestConfidenceCheckHistoryContextInjection`'s `_phase_text()` heading-slice pattern [Agent 3]
- New test class to write: `TestConfidenceCheckRubricLearningTestStatus` in `test_confidence_check_skill.py` — read `skills/confidence-check/rubric.md` and assert the `−10` (missing/refuted) and `−5` (stale) penalty rows appear in the Learning Test Status scoring block [Agent 3]

### Documentation
- N/A — no external documentation references confidence-check learning test behavior

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` line 625 — `learning_tests_required` is documented as consumed only by `/ll:ready-issue`; after ENH-2232, confidence-check is also a consumer and this entry needs updating [Agent 2]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` ~line 372 — describes confidence-check recommendation tiers without a learning-test-forced STOP path; advisory update to document the new override path [Agent 2]

### Configuration
- N/A — no config changes required; `Bash(ll-learning-tests:*)` added only to `allowed-tools` frontmatter

## Impact

- **Priority**: P2 — Closes a silent parity gap where users invoking the lighter-weight gate bypass the learning test check entirely
- **Effort**: Small — Skill file edits only; mirrors an existing pattern from `go-no-go` Step 3a.5 with no new Python code
- **Risk**: Low — Skill-file-only change; issues without `learning_tests_required` frontmatter are completely unaffected
- **Breaking Change**: No

## Related Key Documentation

- `skills/go-no-go/SKILL.md` — reference implementation of Step 3a.5 (learning test pre-fetch pattern to mirror)
- `skills/confidence-check/SKILL.md` — file to modify (Phase 1, Phase 2 Criterion 1, Phase 3)
- `skills/confidence-check/rubric.md` — scoring tables to update

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact insertion points in `skills/confidence-check/SKILL.md`:**
- `allowed-tools` block is at lines 6–13; append `Bash(ll-learning-tests:*)` as a new line after the existing `Bash(ll-history-context:*)` entry
- Phase 1 ends at line 118 (the line `If invoked within manage-issue: use the research findings already gathered in Phase 1.5.`); insert Phase 1.5 between line 118 and the `### Phase 2` heading (~line 120)
- Phase 3 (`### Phase 3: Score and Recommend`) starts at line 268; insert the hard STOP override gate before the `See [rubric.md]` delegation line so it fires before the score-to-tier table lookup

**`skills/confidence-check/rubric.md` Criterion 1 scoring table** ends at line 117; the Learning Test Status modifier rows append after this table as a separate block under the same `### Criterion 1` heading.

**`ll-learning-tests check` CLI behavior (critical nuance):**
- Exit 0 + JSON stdout → record found; `status` field will be `"proven"`, `"stale"`, or `"refuted"`
- Exit 1 + error on stderr + no stdout → record not found ("missing")
- There is no `status: "missing"` in the JSON — missing is signaled by exit code + empty stdout only
- Run **without** `--stale-aware` to read all three states from the JSON `status` field; `--stale-aware` collapses stale+missing into a single exit 1 and loses the distinction needed for differential scoring

**Bash pattern for reading `learning_tests_required` from issue frontmatter** (established pattern from `.issues/enhancements/P3-ENH-2215-create-loop-wizard-auto-insert-assumption-firewall.md`):
```bash
LT_TARGETS=$(ll-issues show "${issue_id}" --json 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
v = d.get('learning_tests_required')
print(v or '')" 2>/dev/null || true)
```
`ll-issues show --json` serializes `learning_tests_required` as a comma-joined string or `null`.

**Exact Learning Test Context block format** to mirror from `skills/go-no-go/SKILL.md` Step 3a.5:
```markdown
## Learning Test Context

The following external API assumptions are declared in this issue's frontmatter:

| Target | Status | Notes |
|--------|--------|-------|
| "<target>" | proven/stale/refuted/missing | [refutation summary if refuted] |
```

**STOP override approach differs from go-no-go:** `go-no-go` expresses the STOP signal as a judge-agent dimension prompt ("hard signal against GO"). For `confidence-check`, the issue calls for an explicit hard gate in Phase 3 prose — inject a conditional check *before* the rubric table delegation: if any target status is `missing` or `refuted`, output `STOP — ADDRESS GAPS` regardless of aggregate score.

**Note:** `skills/go-no-go/SKILL.md` currently also lacks `Bash(ll-learning-tests:*)` in its `allowed-tools` frontmatter (parity gap, out of scope for this issue).

## Session Log
- `/ll:ready-issue` - 2026-06-19T22:32:29 - `3e72939f-3636-4182-aff7-6a1b424e9a9b.jsonl`
- `/ll:confidence-check` - 2026-06-19T22:30:00Z - `6f338ef8-c597-4d44-9a7b-545477d1aa47.jsonl`
- `/ll:wire-issue` - 2026-06-19T22:00:58 - `8f311cd3-965b-4f21-b040-a28df4e62321.jsonl`
- `/ll:refine-issue` - 2026-06-19T21:51:47 - `78b3360f-c8c1-4047-a7a6-869d669dd581.jsonl`
- `/ll:format-issue` - 2026-06-19T21:38:32 - `7ad4c299-a78e-4069-93e8-64dd478cf18b.jsonl`
- `/ll:capture-issue` - 2026-06-19T21:33:27Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

---

## Status

**Open** | Created: 2026-06-19 | Priority: P2
