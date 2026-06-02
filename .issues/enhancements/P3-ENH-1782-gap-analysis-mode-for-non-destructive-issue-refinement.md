---
id: ENH-1782
title: Gap-analysis mode for non-destructive issue refinement
type: enh
status: done
priority: P3
captured_at: '2026-05-29T02:23:45Z'
completed_at: '2026-06-01T09:37:16Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
- issues
- refinement
- captured
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1782: Gap-analysis mode for non-destructive issue refinement

## Summary

Add a non-destructive, additive-only gap-analysis mode to `/ll:refine-issue` that inventories current coverage, identifies gaps, reports them with priorities, and applies only additive changes — never removing existing content. Modeled after CLI-Anything's `/refine` command.

## Current Behavior

`/ll:refine-issue` rewrites issues with codebase-driven research, which can lose valuable human-written content, acceptance criteria, or implementation notes that were already in the issue. There's no "fill gaps only" mode.

## Expected Behavior

A gap-analysis refinement mode that:
1. **Inventories** current coverage — what sections, criteria, and implementation details already exist
2. **Analyzes** the codebase for what's missing (missing files in Integration Map, missing edge cases in acceptance criteria, stale anchor references)
3. **Presents** a prioritized gap report to the user
4. **Applies** only additive changes with user confirmation — fills gaps, never removes content
5. **Verifies** existing tests still pass / existing content is preserved

Core contract: "Refine never removes existing content — it only adds or enhances."

## Motivation

CLI-Anything's `/refine` command demonstrates that additive-only refinement builds user trust — the user knows running refinement won't destroy their work. Current `/ll:refine-issue` carries risk of content loss, which discourages iterative refinement. A gap-analysis mode makes refinement safe to run repeatedly, steadily improving issue quality over time.

## Success Metrics

- Zero content loss during gap-analysis refinement (existing sections preserved verbatim)
- Gap reports are actionable: ≥80% of reported gaps are resolved by the user or auto-fill
- Users run refinement iteratively (≥2 refinement passes on the same issue) without reported data loss

## Scope Boundaries

- **In scope**: Gap inventory and reporting; additive-only content application; stale reference detection (missing files, broken anchors); edge case coverage analysis; `--gap-analysis` flag and routing
- **Out of scope**: Full-rewrite refinement (existing behavior, preserved behind `--full-rewrite` flag); modifying issue structure beyond identified gaps; changing sections the user didn't approve; removing any existing content under any circumstance

## Proposed Solution

Add a `--gap-analysis` flag to `/ll:refine-issue` (or make it the default behavior, with `--full-rewrite` for the legacy mode). The gap-analysis flow:

1. **Parse** the existing issue into a section map
2. **Check** each section against codebase reality:
   - Integration Map: are there referenced files that don't exist? Missing callers?
   - Proposed Solution: are anchor references (function/class names) still valid?
   - Implementation Steps: do they cover all files identified in Integration Map?
   - Acceptance Criteria: are edge cases covered based on code paths?
3. **Score** each gap by impact (critical / high / medium / low)
4. **Report** findings to user with specific suggestions
5. **Apply** approved additions via Edit (append-only)

## API/Interface

N/A — This is a skill instruction change, not a Python API change. The `--gap-analysis` flag is a CLI argument consumed by the skill's argument parser, not a new public Python interface.

## Integration Map

### Files to Modify
- `skills/refine-issue/SKILL.md` — add gap-analysis flow instructions
- `scripts/little_loops/issue_ops/` — gap analysis logic if implemented in Python

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — `/ll:refine-issue` entry in ISSUE REFINEMENT section has `Flags: --auto, --dry-run`; must add `--gap-analysis` and `--full-rewrite` [Agent 2 finding]
- `docs/reference/COMMANDS.md` — `### /ll:refine-issue` section `Arguments` list and `## Flag Conventions` table need entries for new flags [Agent 2 finding]
- `skills/ll-refine-issue/SKILL.md` — `args:` frontmatter currently `"ISSUE_ID [--auto] [--dry-run]"`; consumed by `ll-action list` / `_load_skills()` in `scripts/little_loops/cli/action.py` — must add `[--gap-analysis] [--full-rewrite]` [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `ll-auto`, `ll-parallel`, `ll-sprint` — orchestrators that invoke refinement

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — invokes `/ll:refine-issue ${captured.issue_id.output} --auto` in `refine_issue` state; if `--gap-analysis` becomes the new default, this loop will silently switch modes — must add explicit `--full-rewrite` [Agent 1 finding]
- `scripts/little_loops/loops/autodev.yaml` — invokes `/ll:refine-issue ${captured.input.output} --auto` in `run_refine` state; same silent-mode-change exposure [Agent 1 finding]

### Similar Patterns
- CLI-Anything `commands/refine.md` — the reference implementation for gap-analysis flow

### Tests
- `scripts/tests/test_refine_issue.py` — test that gap-analysis preserves existing content, only appends

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_issue_command.py` — 6 tests in `TestOptionCountDetectionInCommand` use `.index("### 5b. Interactive Refinement")` as upper slice bound; inserting `### 5c` **before** `### 5b` will cause all 6 to raise `ValueError` — must insert 5c **after** 5b [Agent 3 finding]
- New `TestGapAnalysisMode` class needed in `scripts/tests/test_refine_issue_command.py` — assert `--gap-analysis` and `--full-rewrite` appear in Step 0 Parse Flags section, assert `### 5c` heading present, assert additive-only contract documented; follow Pattern B from `test_decide_issue_skill.py` (`content.index(heading_a)` to `content.index(heading_b)` slicing) [Agent 3 finding]

### Documentation
- Update `/ll:refine-issue` skill description

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — section `### Enriching with Codebase Research` describes current full-rewrite behavior; must update if `--gap-analysis` becomes the new default [Agent 2 finding]
- `skills/issue-workflow/SKILL.md` — `### 2. Refinement Phase` describes `refine-issue` as "Enrich issue with codebase research findings"; needs a note about additive mode if characterization changes [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — `## Worked Example: Harness refine-issue` uses `--auto`-only invocations in `execute` state examples; must show correct mode flag after the change [Agent 2 finding]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — same worked example section uses `--auto`-only invocations [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-action list` example JSON shows `"args":"ISSUE_ID [--auto] [--dry-run]"` for `refine-issue`; needs new flags appended [Agent 2 finding]

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — `max_refine_count` description string treats all `refine-issue` calls identically; if gap-analysis runs should not count against the cap (they're cheaper, non-destructive), the description must clarify which modes are counted [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `max_refine_count` row in `commands` table has same ambiguity; update if gap-analysis calls are excluded from the count [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrections to Files to Modify:**
- `commands/refine-issue.md` — the real command file (all flow logic lives here); `skills/refine-issue/SKILL.md` is a Codex bridge stub with minimal content — it is NOT the file to modify
- `scripts/little_loops/issue_ops/` does not exist — no new Python module is required for a skill-only approach; gap-analysis flow adds a new step (5c) to `commands/refine-issue.md` only
- Python utilities already available (no new modules needed): `scripts/little_loops/issues/anchor_sweep.py` (`sweep_issues()`, `_sweep_file()`) for stale anchor detection; `scripts/little_loops/issue_history/doc_synthesis.py` (`_extract_section()`) for H2 section extraction

**Corrections to Dependent Files (Callers/Importers):**
- `ll-auto`, `ll-parallel`, `ll-sprint` do **NOT** invoke `refine-issue` — they invoke `ready-issue`, `decide-issue`, and `manage-issue` via `process_issue_inplace()` in `scripts/little_loops/issue_manager.py`; `refine-issue` is user-invoked only, not part of the automation pipeline
- No callers of `refine-issue` in the automation stack; this change requires no orchestrator updates

**Corrections to Similar Patterns:**
- `CLI-Anything commands/refine.md` does not exist in this codebase; the in-codebase analogs are:
  - `skills/format-issue/SKILL.md` — structural gap inventory table + auto/interactive routing (closest pattern)
  - `skills/update-docs/SKILL.md` — gap report + additive apply (`--fix` flag) flow (same shape as ENH-1782)
  - `commands/ready-issue.md` — claim vs. reality checks with `--deep` sub-agent spawning (integration map staleness analog)

**Corrections to Tests:**
- `scripts/tests/test_refine_issue_command.py` is the actual test file (not `test_refine_issue.py`)

**Existing Python abstractions available (no new code needed):**
- `scripts/little_loops/issue_history/doc_synthesis.py` — `_extract_section(content, heading)` — canonical H2 section extraction
- `scripts/little_loops/issue_parser.py` — `is_formatted()` — checks required H2 headings via `re.findall(r"^##\s+(.+)$", ...)`
- `scripts/little_loops/dependency_mapper/operations.py` — `_add_to_section()` — additive section insert (append-only pattern)
- `scripts/little_loops/issues/anchor_sweep.py` — `sweep_issues()` / `_sweep_file()` — stale `file:N` reference detection; returns `skipped_refs` for unresolvable anchors
- `scripts/little_loops/issue_history/models.py` — `TestGap` dataclass (`priority: str` = `"critical"/"high"/"medium"/"low"`, `gap_score`) — gap prioritization data model

## Implementation Steps

1. Study CLI-Anything's `/refine` command for the gap-analysis flow pattern
2. Design the section-map data structure for parsing existing issues
3. Update `/ll:refine-issue` SKILL.md with the gap-analysis flow
4. Add `--gap-analysis` flag detection and routing
5. Implement gap checks: integration map staleness, anchor reference validity, edge case coverage
6. Add tests verifying content preservation and additive-only changes

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Add `--gap-analysis` and `--full-rewrite` flags** to `### 0. Parse Flags` in `commands/refine-issue.md` — follow the exact flag-detection pattern from `skills/format-issue/SKILL.md:### 0. Parse Flags` (bash `[[ "$FLAGS" == *"--gap-analysis"* ]]` pattern; auto-enable via `DANGEROUSLY_SKIP_PERMISSIONS`)
2. **Add section inventory step** using `_extract_section()` pattern from `scripts/little_loops/issue_history/doc_synthesis.py` (H2 extraction: `re.search(r"^##\s+heading", content, re.MULTILINE)` then slice to next `##`) — builds the section map for gap scoring
3. **Reuse stale anchor detection** from `scripts/little_loops/issues/anchor_sweep.py` (`_sweep_file()` → `skipped_refs`) instead of implementing from scratch — already handles code-fence exclusion and unresolvable reference classification
4. **Gap scoring**: adopt `"critical"/"high"/"medium"/"low"` priority model from `scripts/little_loops/issue_history/models.py:TestGap`; Integration Map missing files = high, stale anchors = medium, missing edge cases = low
5. **Add `### 5c. Gap-Analysis Mode`** step to `commands/refine-issue.md` (after existing 5a/5b): inventory → check → score → report gap table → apply additive-only (following `skills/update-docs/SKILL.md` report+apply shape)
6. **Tests**: add to `scripts/tests/test_refine_issue_command.py` — verify that `--gap-analysis` on an issue with existing content produces appended content only (no section removals) and that `--full-rewrite` retains previous behavior

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/loops/refine-to-ready-issue.yaml` — if `--gap-analysis` becomes the new default, add explicit `--full-rewrite` to the `refine_issue` state `action:` to preserve current loop behavior
8. Update `scripts/little_loops/loops/autodev.yaml` — same: add explicit `--full-rewrite` to `run_refine` state `action:` 
9. Update `commands/help.md` — add `--gap-analysis` and `--full-rewrite` to the `/ll:refine-issue` `Flags:` line in the ISSUE REFINEMENT section
10. Update `docs/reference/COMMANDS.md` — add new flags to `### /ll:refine-issue` `Arguments` list and `## Flag Conventions` table
11. Update `skills/ll-refine-issue/SKILL.md` — update `args:` frontmatter to `"ISSUE_ID [--auto] [--dry-run] [--gap-analysis] [--full-rewrite]"`
12. Insert `### 5c. Gap-Analysis Mode` in `commands/refine-issue.md` **after** `### 5b` (not before) — inserting before 5b breaks 6 existing `TestOptionCountDetectionInCommand` tests that use `### 5b` as a slice boundary
13. Add `TestGapAnalysisMode` class to `scripts/tests/test_refine_issue_command.py` following Pattern B from `test_decide_issue_skill.py`
14. Decide and document whether gap-analysis calls count against `max_refine_count`; update `config-schema.json` and `docs/reference/CONFIGURATION.md` accordingly

## Impact

- **Priority**: P3 — Not blocking, but improves refinement safety and encourages iterative use
- **Effort**: Medium — New flow design + implementation in skill instructions and/or Python
- **Risk**: Low — Additive mode is opt-in (via flag); existing refinement behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `issues`, `refinement`, `captured`

## Resolution

Implemented `--gap-analysis` and `--full-rewrite` flags for `/ll:refine-issue`:

- **`commands/refine-issue.md`**: Added flag parsing in Step 0, new `### 5c. Gap-Analysis Mode` section (after 5b), updated Arguments and Examples
- **`skills/ll-refine-issue/SKILL.md`**: Updated `args:` frontmatter with new flags
- **Loop preservation**: Added `--full-rewrite` to `refine-to-ready-issue.yaml` and `autodev.yaml` to prevent silent mode-change
- **`commands/help.md`**: Added new flags to refine-issue entry
- **`docs/reference/COMMANDS.md`**: Updated Arguments and Flag Conventions table
- **`config-schema.json` + `docs/reference/CONFIGURATION.md`**: Documented gap-analysis exemption from `max_refine_count`
- **`scripts/tests/test_refine_issue_command.py`**: Added `TestGapAnalysisMode` class (8 new tests)

All 19 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-06-01T09:37:34 - `b2efb830-4854-4151-a0c3-d9a6d059e94b.jsonl`
- `/ll:ready-issue` - 2026-06-01T09:30:54 - `67704e56-d96b-49a6-9408-6e9b08818cd0.jsonl`
- `/ll:confidence-check` - 2026-06-01T10:00:00 - `78783dd6-1522-455b-a408-30d2de12f191.jsonl`
- `/ll:wire-issue` - 2026-06-01T09:25:51 - `dcbbf1df-4329-4f24-9d74-a7a36f256cda.jsonl`
- `/ll:refine-issue` - 2026-06-01T09:19:30 - `213c7e7b-bd87-4beb-a4d4-034a514f707c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:58 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:15 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:format-issue` - 2026-05-29T02:28:33 - `9e23d1bf-3385-43d7-80c9-602fafbaf867.jsonl`
- `/ll:capture-issue` - 2026-05-29T02:23:45Z - `8b24cba6-684e-4420-9519-de98c8b4822b.jsonl`

---

**Open** | Created: 2026-05-29 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): After ENH-1775 (Wave 2) restructures the 5 harness loops into thin wrappers (moving rubric scoring states to `loops/oracles/generator-evaluator.yaml`), this issue's Integration Map staleness check may generate false-positive stale-reference reports for issues that reference the pre-Wave-2 file layout (inline rubric states in the 5 parent loops). The gap-analysis staleness detector should distinguish between "file does not exist" (true gap) and "file exists but the referenced state/section was restructured" (post-refactor drift). As a practical mitigation, gap-analysis reports should be re-run after each epic wave completes to clear wave-induced drift rather than treating restructuring events as persistent gaps.
