---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
id: FEAT-1220
priority: P2
parent_issue: FEAT-1214
discovered_date: "2026-04-21"
discovered_by: issue-size-review
size: Medium
confidence_score: 80
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1220: Update TESTING.md Fixture Count

## Summary

Update `docs/development/TESTING.md:115` from `# FSM YAML fixtures (8 files)` to `# FSM YAML fixtures (10 files)` to reflect the 9 existing fixtures plus `parallel-loop.yaml` added by FEAT-1213.

## Parent Issue

Decomposed from FEAT-1214: Parallel Validation, Fuzz, and Doc Tests

## Use Case

**Who**: Developer completing FEAT-1213 (`parallel-loop.yaml` fixture)

**Context**: TESTING.md line 115 currently reads `(8 files)` — it was already stale at 9 before FEAT-1213. Once FEAT-1213 adds `parallel-loop.yaml`, the count reaches 10.

**Goal**: Update one line in TESTING.md to keep the fixture count accurate.

**Outcome**: `docs/development/TESTING.md:115` reads `# FSM YAML fixtures (10 files)`.

## Proposed Solution

### docs/development/TESTING.md — Update fixture count

1. Verify fixture count: `ls scripts/tests/fixtures/fsm/*.yaml | wc -l` should show 10 after FEAT-1213 lands.
2. Update `docs/development/TESTING.md:115` from `(8 files)` → `(10 files)` in a single edit.

Note: Filesystem currently has **9** YAML fixtures (not 8). After FEAT-1213 adds `parallel-loop.yaml`, count will be **10**. This is a combined correction (9 actual + 1 incoming → corrects stale `8` directly to `10`).

## Integration Map

### Files to Modify
- `docs/development/TESTING.md:115` — Update fixture count from `(8 files)` to `(10 files)`

### Dependent Files
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — Created by FEAT-1213 (must be present before editing the docs)

### Build Artifacts (Derived — update automatically on `mkdocs build`)

_Wiring pass added by `/ll:wire-issue`:_
- `site/development/TESTING/index.html:2766` — committed MkDocs build output containing `"FSM YAML fixtures (8 files)"` verbatim; mirrors TESTING.md:115 and stays stale until `mkdocs build` is re-run
- `site/search/search_index.json` — full-text search corpus embedding the stale count; same rebuild dependency

Note: `site/` is not listed in `.gitignore` and is tracked in version control. If a `mkdocs build` step is not part of the commit workflow, these two files must be updated manually or the stale text will persist in the deployed site.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Single reference**: `grep -rn "fixtures/fsm\|FSM YAML fixtures" docs/ scripts/` returns only one hit — `docs/development/TESTING.md:115`. No other docs, READMEs, or source files reference the fixture count, so the fix is truly a one-line change.
- **Not covered by `ll-verify-docs`**: The verification tool at `scripts/little_loops/cli/docs.py:12` (`main_verify_docs`) and its backing module `scripts/little_loops/doc_counts.py` only track commands/agents/skills counts — `grep "fsm\|fixture" scripts/little_loops/doc_counts.py` returns nothing. This explains why the count drifted to `(8)` while filesystem held 9: no automation catches this count. Consider filing a follow-up ENH if staleness recurs.
- **Current filesystem state** (as of 2026-04-21, pre-FEAT-1213-landing): `ls scripts/tests/fixtures/fsm/*.yaml | wc -l` → **9**. Listed: `custom-on-routing.yaml`, `incomplete-loop.yaml`, `invalid-initial-state.yaml`, `invalid-yaml-syntax.yaml`, `loop-with-unreachable-state.yaml`, `missing-name.yaml`, `missing-states.yaml`, `non-dict-root.yaml`, `valid-loop.yaml`. `parallel-loop.yaml` is **not yet on disk** even though FEAT-1213's issue file is staged in `.issues/completed/` — the fixture must actually exist before this issue can satisfy its acceptance criterion.
- **Pattern for one-line doc edits**: Use the `Edit` tool with `old_string: "# FSM YAML fixtures (8 files)"` and `new_string: "# FSM YAML fixtures (10 files)"`. The surrounding context (lines 111–116 show a tree block) is stable and requires no other changes.

## Dependencies

- **FEAT-1217** must be complete (provides `scripts/tests/fixtures/fsm/parallel-loop.yaml`; needed to confirm the count reaches 10). FEAT-1213 was decomposed and FEAT-1215 was further decomposed, leaving FEAT-1217 as the remaining active issue that actually creates the fixture file on disk.

## Acceptance Criteria

- `docs/development/TESTING.md:115` updated to reflect 10 fixture files
- `ls scripts/tests/fixtures/fsm/*.yaml | wc -l` returns 10

## Labels

`fsm`, `parallel`, `docs`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 85/100 → HIGH CONFIDENCE

### Concerns
- `parallel-loop.yaml` does not exist on disk (current count: 9). FEAT-1213 was decomposed → FEAT-1215 was also decomposed → FEAT-1217 (Parallel Loop YAML Fixture and Fixture-Load Test) is still **active** in `.issues/features/`. That issue must land before the acceptance criterion (`wc -l` returns 10) can be satisfied.
- Do not update TESTING.md to `(10 files)` until FEAT-1217 is completed and `scripts/tests/fixtures/fsm/parallel-loop.yaml` exists on disk.

## Session Log
- `/ll:refine-issue` - 2026-04-21T08:48:31 - `93a6abff-9eef-42d5-906a-16129e2312ed.jsonl`
- `/ll:refine-issue` - 2026-04-21T08:41:22 - `24deddc4-b3ab-46e0-a086-402c756f420c.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `e25ed049-cee1-4c7f-a922-d725b2ff5c2f.jsonl`
- `/ll:wire-issue` - 2026-04-21T00:00:00 - `current-session.jsonl`
- `/ll:confidence-check` - 2026-04-21T09:00:00 - `1476711d-e434-42d7-959c-f6e895b60775.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `c93a99ef-f7be-473a-af0d-5ec933e75111.jsonl`
