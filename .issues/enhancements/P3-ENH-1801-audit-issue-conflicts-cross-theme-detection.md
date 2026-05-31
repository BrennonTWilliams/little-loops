---
id: ENH-1801
title: audit-issue-conflicts intra-batch design misses cross-theme conflicts at scale
type: ENH
priority: P3
status: done
captured_at: '2026-05-29T20:55:00Z'
completed_at: '2026-05-31T21:08:46Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
labels:
- enhancement
- skills
- audit-issue-conflicts
parent: EPIC-1745
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1801: audit-issue-conflicts intra-batch design misses cross-theme conflicts at scale

## Summary

`skills/audit-issue-conflicts/SKILL.md` Phase 2 batches issues 3–5 per parallel agent and detects conflicts only within each batch. With 50+ active issues, real cross-theme conflicts (e.g., a refine-issue change vs an FSM evaluator change that share a CLI surface) become invisible because the related issues end up in different batches.

## Motivation

In the 2026-05-29 audit run on 54 active issues, I had to hand-cluster issues into 13 thematic batches to get useful conflict signal. Even so, this only catches conflicts whose endpoints I already suspected belonged in the same theme. The skill cannot detect surprise conflicts that span thematic boundaries — exactly the conflicts that are most valuable to surface, because adjacent-theme conflicts are usually already known to the author.

## Current Behavior

Phase 2 instructions: "Batch issues 3–5 per Task call. Spawn all batch Task calls in a single message (parallel). … For EACH pair of issues in this batch, determine if a conflict exists."

Conflict detection is therefore O(batches × batch_size²) — quadratic only within each batch, linear in the number of batches. No cross-batch pair is ever evaluated.

## Expected Behavior

The skill detects conflicts that span thematic groups, either by:
1. **Pre-clustering pass**: use embedding similarity (or simple TF-IDF over title + Integration Map) to cluster issues, then batch by cluster rather than by linear chunking — so likely-conflicting issues land in the same batch even if their type/path differs.
2. **Cross-batch pass**: after the intra-batch sweep, run a smaller second pass that compares the "summary fingerprint" (Files to Modify, key terms) of every issue against every other, flagging only file-path or symbol overlaps for deeper LLM review.
3. **Bipartite cross-pass**: pair high-priority issues from each batch with one issue from each other batch in a single Task call, scaling linearly with priority-issue count.

## Proposed Solution

Add a Phase 2b cross-theme sweep that:
1. Extracts a structured fingerprint per issue (frontmatter `id`, `parent`, files mentioned in Integration Map, key terms from Summary) — non-LLM, fast.
2. Computes pairwise overlap between fingerprints across all batches.
3. For any pair with file/symbol overlap above a threshold, dispatches a single-pair conflict-detection Task agent.

Phase 3 aggregation then dedupes against intra-batch findings.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

All three fingerprint extraction primitives already exist — no re-implementation needed:
- `files_to_modify` set: `extract_file_hints()` in `scripts/little_loops/parallel/file_hints.py` already extracts file paths scoped to `### Files to Modify` sections via regex
- `key_terms` bag: `extract_words()` in `scripts/little_loops/text_utils.py` already provides stop-word-filtered token sets; `calculate_word_overlap()` computes Jaccard directly
- Pairwise loop: `find_file_overlaps()` in `scripts/little_loops/dependency_mapper/analysis.py` already implements the n*(n-1)/2 upper-triangle iteration with configurable `min_files`/`min_ratio` thresholds

This also answers Open Question 2: non-LLM fingerprint extraction is proven stable — `extract_file_hints()` and `extract_words()` are already used in production paths (`ll-parallel`, `ll-deps`).

Phase 2b insertion point: after "Wait for all batch agents to complete" at the end of the Phase 2 block in `skills/audit-issue-conflicts/SKILL.md`, before the Phase 3 header.

## Implementation Steps

1. Define the fingerprint schema (issue id, files-to-modify set, key-term bag)
2. Add a Phase 2b section to `skills/audit-issue-conflicts/SKILL.md` that runs after Phase 2 completes
3. Implement fingerprint extraction either inline in the skill (awk over Integration Map) or as a helper in `ll-issues` (preferred — `ll-issues fingerprint <path>`)
4. Compute cross-batch overlap and dispatch targeted pairwise agents
5. Merge findings into Phase 3 dedupe step

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1** (fingerprint schema): define `IssueFingerprint(issue_id, files_to_modify, key_terms)` dataclass in `scripts/little_loops/dependency_mapper/models.py` alongside `DependencyProposal`; or reuse `FileHints` from `file_hints.py` directly
- **Step 2** (Phase 2b insertion): edit `skills/audit-issue-conflicts/SKILL.md` after the "Wait for all batch agents to complete" sentence at end of Phase 2, before the `## Phase 3: Synthesize Report` header
- **Step 3** (fingerprint subcommand): create `scripts/little_loops/cli/issues/fingerprint.py` exporting `cmd_fingerprint(config, args) -> int`; register in `scripts/little_loops/cli/issues/__init__.py:main_issues()` following `anchor_sweep.py:cmd_anchor_sweep()` pattern (lines 588–607 / 674)
- **Step 4** (pairwise overlap): adapt `find_file_overlaps()` from `scripts/little_loops/dependency_mapper/analysis.py`; reuse `min_files`/`min_ratio` threshold pattern
- **Step 5** (merge into Phase 3): Phase 3 "Deduplicate" sub-step already merges by `issues` pair membership — cross-theme findings feed in identically to intra-batch findings
- **Tests**: add cross-theme synthetic fixture to `scripts/tests/test_audit_issue_conflicts_skill.py`; follow `TestSectionAwareOverlapDetection` pattern in `scripts/tests/test_file_hints.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/little_loops/cli/issues/__init__.py` epilog Sub-commands list and Examples block — add `fingerprint` entry alongside `anchor-sweep`
7. Update `.claude/CLAUDE.md` "CLI Tools" section — add `fingerprint` to the parenthetical `ll-issues` subcommand list
8. Update `commands/help.md` `ll-issues` line — add `fingerprint` to the parenthetical subcommand list
9. Update `skills/init/SKILL.md` — two template blocks that enumerate `ll-issues` subcommands (search `anchor-sweep`; add `fingerprint` alongside it in both blocks)
10. Update `docs/reference/API.md` `main_issues` Sub-commands table — add a `fingerprint` row
11. Update `docs/reference/CLI.md` `## ll-issues` section — add `#### ll-issues fingerprint` subsection and examples after the `anchor-sweep` subsection
12. Update `docs/ARCHITECTURE.md` `issues/` package file tree — add `fingerprint.py` entry
13. Write `scripts/tests/test_ll_issues_fingerprint.py` — CLI dispatch tests for `cmd_fingerprint`; follow `TestIssuesCLISetScores` pattern in `test_set_scores_cli.py` (sys.argv patch, capsys, config fixture)
14. Update `scripts/tests/test_dependency_mapper.py` `TestFindFileOverlaps` — add cross-theme cases (N > 2 batches, file overlap in non-adjacent batch windows); follow `TestFindFileOverlapsSemanticAnalysis.test_parallel_safe_different_sections` pattern
15. If `--cross-theme` is opt-in flag: update `scripts/little_loops/loops/sprint-build-and-validate.yaml` `audit_conflicts` state to pass `--cross-theme`; also update `docs/guides/LOOPS_GUIDE.md` sprint loop table entry

## Scope Boundaries

- **In scope**: Cross-theme conflict detection via pairwise fingerprint overlap; structured fingerprint extraction (id, files, key terms); dispatch of targeted single-pair conflict-detection agents for pairs above overlap threshold; dedup against existing Phase 3 aggregation
- **Out of scope**: Full semantic conflict understanding (LLM judges overlap scores, not meaning); replacing Phase 2 intra-batch design (this is additive); real-time or continuous conflict detection; automatic resolution of detected conflicts

## Success Metrics

- Cross-theme conflicts surfaced per run: 0 → ≥1 for known cross-theme cases (synthetic test fixture with two issues in different batches modifying the same file)
- Agent count overhead: +0% → ≤+30% vs intra-batch baseline (Phase 2b agents / Phase 2 agents)
- No regression: intra-batch detection rate unchanged (Phase 2 output identical before/after)

## API/Interface

```bash
# New optional subcommand for fingerprint extraction
ll-issues fingerprint <issue-path>
# Outputs JSON with id, files_to_modify (set), key_terms (bag)
```

## Acceptance Criteria

- A synthetic test where two issues in different thematic batches both modify the same file produces a conflict finding
- Cross-theme pass adds ≤30% to total agent count vs intra-batch baseline (cost bound)
- Documented runtime cost in the skill body so users understand the tradeoff

## Integration Map

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md` — add Phase 2b
- `scripts/little_loops/cli/ll_issues.py` — optional `fingerprint` subcommand

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Path correction**: `scripts/little_loops/cli/ll_issues.py` does not exist as a single file; the `ll-issues` CLI is a package. Correct targets: `scripts/little_loops/cli/issues/__init__.py` (register subcommand in `main_issues()`) and a new file `scripts/little_loops/cli/issues/fingerprint.py` (implementation, following `anchor_sweep.py` pattern)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/sprint-build-and-validate.yaml:93-99` — invokes `/ll:audit-issue-conflicts --auto` as a phase in the sprint orchestration loop

### Similar Patterns
- `/ll:map-dependencies` does cross-issue graph analysis — review for shared fingerprint extraction
- `/ll:link-epics` clusters issues by parent EPIC — similar grouping primitive

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/parallel/file_hints.py` — `extract_file_hints()` + `FileHints` dataclass: extracts `files_to_modify` set from `### Files to Modify` sections via regex (no LLM, section-scoped); directly reusable for fingerprint extraction
- `scripts/little_loops/text_utils.py` — `extract_words()` + `calculate_word_overlap()`: Jaccard key-term overlap already implemented with stop-word filtering; reusable for `key_terms` overlap check
- `scripts/little_loops/dependency_mapper/analysis.py` — `find_file_overlaps()`: pairwise n*(n-1)/2 overlap loop with configurable `min_files`/`min_ratio` thresholds; `compute_conflict_score()`: three-signal weighted scoring (semantic targets, section mentions, modification type)
- `scripts/little_loops/dependency_mapper/models.py` — `DependencyProposal`, `DependencyReport` dataclasses: model pattern for `IssueFingerprint` and `CrossThemePair` result types
- `scripts/little_loops/cli/issues/anchor_sweep.py` — `cmd_anchor_sweep()`: argparse registration + thin wrapper pattern to follow for `ll-issues fingerprint` subcommand

### Tests
- `scripts/tests/test_skill_audit_issue_conflicts.py` — add a fixture with cross-theme overlap

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Filename correction**: actual file is `scripts/tests/test_audit_issue_conflicts_skill.py` (not `test_skill_audit_issue_conflicts.py`)
- `scripts/tests/test_file_hints.py` — `TestSectionAwareOverlapDetection`: pairwise overlap test with two inline issue strings; template for cross-theme synthetic fixture
- `scripts/tests/test_overlap_detector.py` — `make_issue()`: `Mock(spec=Path)` helper for constructing `IssueInfo` objects without filesystem access
- `scripts/tests/test_text_utils.py` — patterns for `extract_words` + `calculate_word_overlap` edge cases (empty input, stop-word filtering)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_fingerprint.py` — NEW test file for `cmd_fingerprint` CLI dispatch; follow `TestIssuesCLISetScores` pattern in `test_set_scores_cli.py` (sys.argv patch + capsys + config fixture) [Agent 3 finding]
- `scripts/tests/test_dependency_mapper.py` — UPDATE `TestFindFileOverlaps` with cross-theme cases: N > 2 batches, file overlap in non-adjacent windows; follow `TestFindFileOverlapsSemanticAnalysis.test_parallel_safe_different_sections` pattern [Agent 3 finding]
- `scripts/tests/test_audit_issue_conflicts_skill.py` — also ADD Phase 2b string-presence assertions (Phase 2b header text, `ll-issues fingerprint` call); existing string assertions are not broken by Phase 2b insertion [Agent 3 finding]

### Documentation
- `skills/audit-issue-conflicts/SKILL.md` — document Phase 2b behavior, cost tradeoff, and `--cross-theme` flag if opt-in

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — "CLI Tools" section, `ll-issues` parenthetical subcommand list — add `fingerprint` [Agent 2 finding]
- `commands/help.md` — `ll-issues` line in CLI tools table — add `fingerprint` to subcommand list (same pattern as when `anchor-sweep` was added in ENH-1300) [Agent 2 finding]
- `skills/init/SKILL.md` — two template blocks (update-existing and create-new) that hard-code the `ll-issues` subcommand list — add `fingerprint` in both [Agent 2 finding]
- `docs/reference/API.md` — `main_issues` section Sub-commands table — add a `fingerprint` row [Agent 2 finding]
- `docs/reference/CLI.md` — `## ll-issues` section — add `#### ll-issues fingerprint` subsection and examples after the `anchor-sweep` subsection [Agent 2 finding]
- `docs/ARCHITECTURE.md` — `issues/` package file tree listing `scripts/little_loops/cli/issues/` files — add `fingerprint.py` entry [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — sprint-build-and-validate loop table entry for `audit_conflicts` state — update if `--cross-theme` is added to the sprint invocation [Agent 2 finding, conditional]

### Configuration
- N/A

## Impact

- **Priority**: P3 — capability gap, not a defect; current skill still useful for in-theme conflicts
- **Effort**: Medium — new phase + fingerprint primitive
- **Risk**: Low-medium — could materially raise per-run token cost; gate behind a `--cross-theme` flag if needed
- **Breaking Change**: No

## Open Questions

- Should cross-theme be opt-in (`--cross-theme` flag) or default? Default is more correct but more expensive.
- Is fingerprint extraction stable enough without an LLM (TF-IDF vs embedding)?

## Session Log
- `/ll:ready-issue` - 2026-05-31T20:53:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf581b66-96e8-4c83-ba66-89f686b12efc.jsonl`
- `/ll:confidence-check` - 2026-05-31T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c66a399b-a087-496d-a49a-4d67bd2d86e8.jsonl`
- `/ll:wire-issue` - 2026-05-31T20:48:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/531ec7f7-1448-4d6e-ba53-afe5c4ef0322.jsonl`
- `/ll:refine-issue` - 2026-05-31T20:43:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81e2ee88-285d-4fe2-9057-76f78da601d4.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T21:11:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9f7876db-05fe-44b7-8207-daa880a4618f.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:55:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`

## Status

**Open** | Created: 2026-05-29 | Priority: P3
