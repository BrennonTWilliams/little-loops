---
id: BUG-2333
title: review-epic counts relates_to as children, diverging from epic-progress
type: BUG
priority: P2
status: open
captured_at: '2026-06-26T22:37:02Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- FEAT-2332
- ENH-2330
- BUG-2029
decision_ref:
- ARCHITECTURE-065
labels:
- captured
- epic
- issue-management
- review-epic
- parent-child
confidence_score: 100
outcome_confidence: 88
score_complexity: 23
score_test_coverage: 15
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2333: `review-epic` counts `relates_to` as children

## Summary

The `review-epic` skill resolves an EPIC's children as the **union** of its
`relates_to:` list and the `parent:` backrefs, while `epic-progress` counts
`parent:` only. The two readers therefore report different child sets — and
health/closure assessments — for the same EPIC. This re-introduces the exact
`relates_to`-inflation conflation that BUG-2029 fixed in `epic-progress`, just
in a different reader.

## Steps to Reproduce

1. Create (or pick) an EPIC whose `relates_to:` list includes at least one
   non-child cross-reference — a sibling EPIC, a prerequisite, or a sub-epic
   that does *not* carry `parent: <EPIC_ID>`.
2. Run `/ll:review-epic <EPIC>` and note the reported child count / membership.
3. Run `ll-issues epic-progress <EPIC>` and note its total.
4. Observe: the two counts diverge — `review-epic` includes the `relates_to`
   entry as a child while `epic-progress` does not.

## Current Behavior

`skills/review-epic/SKILL.md:75-79`:

```
forward_ids  = set of IDs from the EPIC's `relates_to` list
backward_ids = set of issue_ids where parent == EPIC_ID
child_ids    = forward_ids ∪ backward_ids
children     = [issue for issue in all_issues if issue.issue_id in child_ids]
```

Because `scope-epic` (Phase 5a) and `link-epics` (Phase 6b) write every child
into `relates_to`, the union *usually* matches — but as soon as `relates_to`
holds a non-child cross-reference (sibling EPIC, prerequisite, sub-epic) or a
child loses its `parent:`, `review-epic` over-counts membership relative to
`epic-progress`. The 2026-06-26 audit confirmed `relates_to` is overloaded
across the EPIC set.

`compute_epic_progress` deliberately excludes `relates_to`
(`scripts/little_loops/issue_progress.py:73-75`).

## Expected Behavior

Per ARCHITECTURE-065 (`parent:` is the single source of truth):

- `review-epic` child discovery = `parent:` backrefs **only** (same set as
  `epic-progress`).
- `relates_to:` entries are rendered in a separate **"Related (not children)"**
  section of the report, clearly distinct from the child rollup.

## Root Cause

- **File**: `skills/review-epic/SKILL.md`
- **Anchor**: child-resolution block (lines ~75-79)
- **Cause**: child discovery is defined as the union `forward_ids ∪ backward_ids`
  where `forward_ids` is drawn from the EPIC's `relates_to:` list. Because
  `relates_to:` is overloaded to carry non-membership cross-references (sibling
  EPICs, prerequisites, sub-epics), any such entry is miscounted as a child.
  `compute_epic_progress` deliberately excludes `relates_to`
  (`scripts/little_loops/issue_progress.py:73-75`), so the two readers diverge
  whenever `relates_to` and `parent:` backrefs disagree.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Precise anchor for the reference implementation**: the cited
  `issue_progress.py:73-75` is the *docstring* stating the intent; the executable
  parent:-only resolution is **`scripts/little_loops/issue_progress.py:87`**:
  `child_ids = {i.issue_id for i in all_issues if i.parent == epic_id}`. The
  function (`compute_epic_progress`, lines 67-123) uppercases `epic_id` (line 80)
  and is called with `find_issues(..., status_filter=_ALL_STATUSES)` so all
  statuses count.
- **The drift originates from a now-false comment**: `skills/review-epic/SKILL.md`
  lines 72-73 (just above the pseudocode) claim the block "mirrors
  `compute_epic_progress()`" — but the block adds `forward_ids` from `relates_to`,
  which `compute_epic_progress` never does. The comment must be corrected as part
  of the fix, not just the code.
- **Blast radius is wider than the count**: the divergent `children` union set
  (Step 2c) is not only displayed — it drives **Stalled children** (Step 4),
  **Scope drift** (Step 5), and **Missing coverage** (Step 6) in
  `skills/review-epic/SKILL.md`. A `relates_to`-only entry is therefore mis-analyzed
  as a stalled/drifting child, not merely mis-counted.
- **Full delegation is NOT a drop-in option**: Step 3 (line 103) already calls
  `ll-issues epic-progress` for *aggregates*, but `EpicProgress.to_dict()`
  (`scripts/little_loops/issue_progress.py:30-48`) omits the `children`
  list from JSON (emits only `total`, `by_status`, `percent_done`,
  `percent_blocked`, `oldest_open`). review-epic must keep resolving children
  locally; the fix is to mirror the parent:-only rule inline. (Extending the CLI
  to emit children for full delegation is larger scope and overlaps FEAT-2332.)

## Implementation Steps

1. **Fix child resolution** — `skills/review-epic/SKILL.md` Step 2c (lines 75-79):
   replace the `forward_ids ∪ backward_ids` union with parent:-only resolution
   mirroring `issue_progress.py:87` (`child_ids = {issue_id for issue in
   all_issues if issue.parent == EPIC_ID}`). Delete the `forward_ids`/`relates_to`
   line entirely (matches the BUG-2029 fix shape).
2. **Correct the preamble comment** — `skills/review-epic/SKILL.md` lines 72-73: the
   "mirrors `compute_epic_progress()`" claim is now accurate only after step 1;
   reword to state parent:-only resolution explicitly so the comment can't re-seed
   the drift.
3. **Render related-not-children** — `skills/review-epic/SKILL.md` Step 8 report
   (lines 208-269): add a distinct **"Related (not children)"** section listing the
   EPIC's `relates_to` entries, separated from the child rollup (natural insertion
   point: after the Closure recommendation block ~line 246, or after the Progress
   line ~215).
4. **Add the structural parity test** — create
   `scripts/tests/test_review_epic_skill.py` modeled on
   `scripts/tests/test_scope_epic_skill.py:TestScopeEpicSkillExists` (read
   `SKILL.md`, assert strings; no fixtures): assert the skill references
   parent:-only resolution and `epic-progress` parity, asserts a "Related (not
   children)" section exists, and asserts the union-with-`relates_to` phrasing is
   gone.
5. **Verify parity empirically** — against an EPIC whose `relates_to` holds a
   non-child reference, confirm `ll-issues epic-progress <EPIC>` total equals the
   child count review-epic reports.
6. **Run tests** — `python -m pytest scripts/tests/test_review_epic_skill.py
   scripts/tests/test_issue_progress.py -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation:_

7. **Update the command reference** — `docs/reference/COMMANDS.md`, the
   `### /ll:review-epic` **Output** description (~line 419): add "Related (not
   children)" to the enumerated section list so the doc matches the report rendered
   in Step 3. Leave the `### /ll:review-epic` heading and `| review-epic |` table row
   intact (those are wiring-test anchors).
8. **Confirm wiring tests pass** — run
   `python -m pytest scripts/tests/test_wiring_skills_and_commands.py
   scripts/tests/test_wiring_reference_docs.py -v` to verify the `--for-skill
   review-epic` assertion, the skill/openai.yaml file-existence checks, and the
   COMMANDS.md heading/table-row anchors all still pass after the edits.

## Acceptance Criteria

- `skills/review-epic/SKILL.md` child-resolution block (lines ~75-79) updated to
  use `parent:` backrefs only.
- The report gains a distinct "Related (not children)" section for `relates_to`.
- For any EPIC, the child count `review-epic` reports equals `ll-issues
  epic-progress <EPIC>`'s total.
- `skills/tests/` (or wherever review-epic structure is tested) asserts the
  parent:-only resolution and the separate related section.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The parity test belongs at **`scripts/tests/test_review_epic_skill.py`** — this
  file does **not** exist today (sibling skills are covered by
  `scripts/tests/test_scope_epic_skill.py` and
  `scripts/tests/test_link_epics_skill.py`; review-epic has only a wiring-registry
  reference in `test_wiring_skills_and_commands.py`). It must be created.
- review-epic is a prose/pseudocode `SKILL.md`, so the structural test asserts on
  the skill *text* (string assertions), not runtime behavior — model it on
  `test_scope_epic_skill.py:TestScopeEpicSkillExists`.
- Runtime parity is already locked in `scripts/tests/test_issue_progress.py`:
  `test_forward_resolution_via_relates_to` (a `relates_to` entry yields zero
  children) and `test_union_deduplication` are the canonical assertions the skill
  must now match.

## Integration Map

- `skills/review-epic/SKILL.md` (child resolution + report template).
- Cross-check against `scripts/little_loops/issue_progress.py` for parity.
- Relates to FEAT-2332 (shared parent:-only resolution) and ENH-2330 (stops
  `relates_to` from being written as a membership channel in the first place).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files to modify**
- `skills/review-epic/SKILL.md` — Step 2c block (lines 75-79, heading
  `### 2c. Resolve children`): swap union → parent:-only. Preamble comment
  (lines 72-73): correct the "mirrors `compute_epic_progress()`" claim. Step 8
  report (lines 208-269): add the "Related (not children)" section.

**Reference implementation (do not modify — mirror it)**
- `scripts/little_loops/issue_progress.py:87` — `compute_epic_progress`, the exact
  parent:-only expression to copy.
- `scripts/little_loops/issue_progress.py:30-48` — `EpicProgress.to_dict()`,
  proof the CLI JSON omits the child list (rules out full delegation).

**Tests**
- Create `scripts/tests/test_review_epic_skill.py` (none exists) — model on
  `scripts/tests/test_scope_epic_skill.py`.
- `scripts/tests/test_issue_progress.py:97-115` — existing parity assertions
  (`test_forward_resolution_via_relates_to`, `test_union_deduplication`).

**Decision reference**
- `.ll/decisions.yaml:2242-2266` — ARCHITECTURE-065 (`parent:` is the single
  source of truth for EPIC membership).

**Related divergence (out of scope here — FEAT-2332 territory)**
- `scripts/little_loops/sprint.py:321-330` and `scripts/little_loops/cli/deps.py:277`
  still use the pre-fix `forward_ids | backward_ids` union. Not part of this fix,
  but worth flagging: review-epic is the third reader of the same buggy shape.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — the `### /ll:review-epic` **Output** description
  (~line 419) enumerates the report's sections ("progress summary, stalled
  children, scope-drift findings, missing-coverage findings, and closure
  recommendation"). Step 3 of this fix adds a **"Related (not children)"** section
  to the rendered report, so this description goes stale unless the new section is
  added to the enumeration. Safe to edit: the only doc-wiring assertions on this
  file are the `### /ll:review-epic` heading and the `| review-epic |` table row
  (`scripts/tests/test_wiring_reference_docs.py:158-159`), both of which survive a
  prose edit to the Output paragraph. [Agent 2 finding]
- No other doc/name reference needs updating — `commands/help.md`, `CONTRIBUTING.md`,
  `docs/ARCHITECTURE.md`, `CHANGELOG.md`, and `skills/configure/*.md` reference
  `review-epic` by name only (no section enumeration). [Agent 2 finding]

### Tests (verify unaffected)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — content assertion
  `("skills/review-epic/SKILL.md", "--for-skill review-epic", "ENH-1909")` targets
  Step 4 (the `ll-history-context` call), which this fix does **not** touch, plus
  `DOC_FILES_MUST_EXIST` entries for the skill + `agents/openai.yaml`. Confirm these
  still pass after the edit — none should break. [Agent 3 finding]
- No existing test asserts on the current buggy `forward_ids ∪ backward_ids`
  pseudocode text, so nothing breaks; the new `test_review_epic_skill.py` (Step 4)
  is the only test that will assert on the corrected block. [Agent 3 finding]
- `skills/review-epic/agents/openai.yaml` verified: name/`short_description`
  metadata only — no child-resolution logic, so the Codex adapter needs no change.
  [wire-issue verification]

## Impact

- **Priority**: P2 - Two readers report different child sets for the same EPIC,
  producing inconsistent health/closure assessments. Not a crash, but a
  correctness defect in EPIC management tooling that re-introduces the
  `relates_to`-inflation conflation BUG-2029 already fixed elsewhere.
- **Effort**: Small - Localized to one resolution block + report template in
  `skills/review-epic/SKILL.md`, plus a parity test. `epic-progress` already
  provides the correct reference implementation.
- **Risk**: Low - Aligns `review-epic` with the already-correct, well-tested
  `epic-progress` behavior; the target set (`parent:` backrefs only) is
  unambiguous per ARCHITECTURE-065.
- **Breaking Change**: No

---

**Open** | Created: 2026-06-26 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-06-27T01:21:29 - `dd3156d9-e668-4509-bc13-e0d34e27bb9e.jsonl`
- `/ll:confidence-check` - 2026-06-26T23:45:00Z - `14bc42e7-76a4-4427-8347-44e5b2c9966b.jsonl`
- `/ll:wire-issue` - 2026-06-26T23:23:14 - `80f7e865-5668-4056-97f7-9794b7b8c70e.jsonl`
- `/ll:refine-issue` - 2026-06-26T23:09:00 - `abd8a5ef-13d7-492f-b92f-c138327f6bce.jsonl`
- `/ll:format-issue` - 2026-06-26T23:00:30 - `64adeb74-858e-4aba-8e05-0d67aa559f7c.jsonl`
