---
id: ENH-1801
type: ENH
priority: P3
status: open
captured_at: "2026-05-29T20:55:00Z"
discovered_date: "2026-05-29"
discovered_by: capture-issue
labels: [enhancement, skills, audit-issue-conflicts]
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

## Implementation Steps

1. Define the fingerprint schema (issue id, files-to-modify set, key-term bag)
2. Add a Phase 2b section to `skills/audit-issue-conflicts/SKILL.md` that runs after Phase 2 completes
3. Implement fingerprint extraction either inline in the skill (awk over Integration Map) or as a helper in `ll-issues` (preferred — `ll-issues fingerprint <path>`)
4. Compute cross-batch overlap and dispatch targeted pairwise agents
5. Merge findings into Phase 3 dedupe step

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

### Dependent Files (Callers/Importers)
- TBD - use grep to find references to `audit-issue-conflicts` skill from loops, sprints, or automation workflows

### Similar Patterns
- `/ll:map-dependencies` does cross-issue graph analysis — review for shared fingerprint extraction
- `/ll:link-epics` clusters issues by parent EPIC — similar grouping primitive

### Tests
- `scripts/tests/test_skill_audit_issue_conflicts.py` — add a fixture with cross-theme overlap

### Documentation
- `skills/audit-issue-conflicts/SKILL.md` — document Phase 2b behavior, cost tradeoff, and `--cross-theme` flag if opt-in

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
- `/ll:format-issue` - 2026-05-29T21:11:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9f7876db-05fe-44b7-8207-daa880a4618f.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:55:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`

## Status

**Open** | Created: 2026-05-29 | Priority: P3
