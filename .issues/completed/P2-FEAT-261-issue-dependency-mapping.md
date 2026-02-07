---
discovered_date: 2026-02-06
discovered_by: capture_issue
---

# FEAT-261: Issue Dependency Mapping — Automated Discovery and Integration

## Summary

Add automated cross-issue dependency discovery and mapping to the little-loops plugin. This combines a new `/ll:map_dependencies` skill for on-demand dependency analysis with lightweight integrations into existing skills (`verify_issues`, `create_sprint`, `scan_codebase`, `tradeoff_review_issues`, `ready_issue`) so dependency data flows naturally through workflows users already run.

## Context

The dependency **infrastructure** already exists (FEAT-030: `DependencyGraph`, `IssueInfo.blocked_by/blocks`, wave generation, cycle detection) and is used by `ll-sprint` and `ll-auto`. However, the only way to populate `## Blocked By` / `## Blocks` sections today is **manual authoring**. There is no automated analysis that discovers dependencies by examining file/component overlaps, architectural relationships, or semantic similarity across issues.

This gap means:
1. Dependencies are often missing, leading to parallel waves that contain conflicting issues
2. Sprint creation requires manual dependency curation
3. New issues from `/ll:scan_codebase` have no dependency context

## Proposed Solution

### Part A: New `/ll:map_dependencies` Skill

A dedicated skill that performs holistic cross-issue dependency analysis:

**Inputs**: All active issues (optionally filtered by type/priority/sprint)

**Analysis methods**:
- **File overlap detection**: Issues touching the same files → potential `blocked_by` (higher-priority or foundational issue first)
- **Component/module dependency**: Issue A modifies an interface/API that Issue B consumes → B blocked by A
- **Architectural layer ordering**: Infrastructure issues before feature issues that depend on them
- **Semantic similarity**: Issues with highly overlapping descriptions may be duplicates or dependent
- **Existing dependency validation**: Check for stale refs, missing backlinks, cycles

**Outputs**:
- Dependency report with proposed new relationships and rationale
- Mermaid diagram of the dependency graph
- Validation results (cycles, broken refs, missing backlinks)
- Interactive confirmation before writing changes to issue files

**User flow**:
1. Run `/ll:map_dependencies` (or `/ll:map_dependencies --sprint sprint-name`)
2. Review proposed dependency additions with rationale
3. Confirm which to apply (multi-select)
4. Skill writes `## Blocked By` / `## Blocks` sections to issue files
5. Optionally stage changes with git

### Part B: Integrations into Existing Skills

Lightweight hooks that leverage the dependency analysis engine or validate existing dependency data:

| Skill | Integration | Trigger |
|-------|-------------|---------|
| `/ll:verify_issues` | Add dependency validation pass: check refs exist, detect cycles, flag missing backlinks, report broken links | Runs automatically as part of verification |
| `/ll:create_sprint` | Show dependency graph for sprint issues, warn about missing deps within the sprint set, suggest wave structure | During sprint creation after issue selection |
| `/ll:scan_codebase` | Cross-reference new findings during synthesis (Step 3) to auto-suggest `blocked_by` when issues touch overlapping files | During issue deduplication/synthesis phase |
| `/ll:tradeoff_review_issues` | Factor "blocking bottleneck" into scoring — issues that block many others score higher utility | As additional scoring dimension |
| `/ll:ready_issue` | Check if `blocked_by` issues are completed before marking ready; warn if blockers are still open | During validation phase |

### Implementation Shape

```
New:
  skills/map_dependencies.md           # Skill definition
  scripts/little_loops/dependency_mapper.py  # Cross-issue analysis engine

Enhanced (light touches):
  commands/verify_issues.md            # Add dep validation pass
  commands/create_sprint.md            # Show dep graph + warnings
  commands/scan_codebase.md            # Cross-ref in synthesis
  commands/tradeoff_review_issues.md   # Bottleneck scoring
  commands/ready_issue.md              # Blocker-completion check
```

The Python module (`dependency_mapper.py`) sits alongside `dependency_graph.py`:
- `dependency_graph.py` = execution ordering (existing, unchanged)
- `dependency_mapper.py` = discovery and proposal of new relationships (new)

## Current Behavior

- Dependencies must be manually authored in issue files
- No automated discovery of cross-issue relationships
- `/ll:verify_issues` does not validate dependency references
- `/ll:create_sprint` does not warn about missing dependencies
- `/ll:scan_codebase` creates isolated issues with no dependency context
- `/ll:tradeoff_review_issues` does not consider blocking relationships in scoring
- `/ll:ready_issue` does not check if blockers are completed

## Expected Behavior

- `/ll:map_dependencies` analyzes all active issues and proposes dependency relationships
- Proposed dependencies include rationale (file overlap, component dependency, etc.)
- User confirms which dependencies to apply before any files are modified
- Dependency validation is part of `/ll:verify_issues`
- Sprint creation shows dependency graph and warns about gaps
- Codebase scanning cross-references findings for dependency suggestions
- Tradeoff reviews highlight blocking bottleneck issues
- Issue readiness checks include blocker completion status

## Impact

- **Priority**: P2
- **Effort**: Medium-Large — new skill + Python module + 5 integration touches
- **Risk**: Low — builds on existing FEAT-030 infrastructure, purely additive

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Dependency graph system design |
| guidelines | CONTRIBUTING.md | Development patterns for new skills |

## Builds On

- FEAT-030: Issue Dependency Parsing and Graph (completed — provides DependencyGraph infrastructure)
- ENH-016: Dependency-Aware Sequencing in ll-auto (completed — uses dependency data)
- ENH-144: Sprint Dependency-Aware Execution (completed — uses wave-based scheduling)

## Labels

`feature`, `dependency-management`, `skill`, `workflow-integration`

---

## Status

**Open** | Created: 2026-02-06 | Priority: P2

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-06
- **Status**: Completed

### Changes Made

**Part A: New Python Module + Skill**
- `scripts/little_loops/dependency_mapper.py` [CREATED]: Cross-issue dependency discovery engine with file overlap detection, dependency validation, report formatting, Mermaid diagram generation, and proposal application
- `skills/map-dependencies/SKILL.md` [CREATED]: 5-phase skill definition for interactive dependency mapping workflow
- `scripts/tests/test_dependency_mapper.py` [CREATED]: 42 tests covering all public functions
- `scripts/tests/fixtures/issues/feature-with-file-refs.md` [CREATED]: Test fixture
- `scripts/tests/fixtures/issues/enhancement-with-file-refs.md` [CREATED]: Test fixture

**Part B: Five Integration Touches**
- `commands/verify_issues.md` [MODIFIED]: Added dependency validation pass (Step E) with broken ref, missing backlink, and cycle detection
- `commands/ready_issue.md` [MODIFIED]: Added dependency status check warning for open blockers
- `commands/create_sprint.md` [MODIFIED]: Added Step 4.5 with dependency analysis, external blocker warnings, wave structure preview, and cycle check
- `commands/scan_codebase.md` [MODIFIED]: Added Step 5 cross-referencing new findings against existing issues for file overlap dependencies
- `commands/tradeoff_review_issues.md` [MODIFIED]: Added 6th "blocking bottleneck" scoring dimension with recommendation boost for high-blocking issues

### Verification Results
- Tests: PASS (42/42 new tests, 2525 total)
- Lint: PASS
- Types: PASS
