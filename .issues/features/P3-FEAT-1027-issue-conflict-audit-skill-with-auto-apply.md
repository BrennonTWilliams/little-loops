---
discovered_date: 2026-04-10
discovered_by: capture-issue
---

# FEAT-1027: Issue Conflict Audit Skill with Auto-Apply

## Summary

Create a new `/ll:` skill/command (`audit-issue-conflicts`) that audits and analyzes open Issues in the user's project for conflicting requirements, objectives, and architecture. The skill synthesizes findings into recommended Issue changes, presents them for user approval in interactive mode, and supports an `--auto` flag to skip approval and auto-apply changes.

## Current Behavior

No tooling exists to detect when open issues have conflicting requirements, contradictory objectives, or architectural incompatibilities. Users must manually review issues for conflicts, which is tedious at scale and easy to miss.

## Expected Behavior

Running `/ll:audit-issue-conflicts` will:
1. Load and analyze all open issues (bugs/, features/, enhancements/)
2. Detect conflicts across: requirements, objectives, architectural decisions, and scope overlap
3. Synthesize findings into a conflict report with recommended changes (merge, close, update, reorder)
4. In interactive mode: present recommendations and ask for user approval before applying
5. With `--auto` flag: skip approval and directly apply all recommended changes

## Motivation

As issue backlogs grow, conflicting issues create implementation confusion and wasted effort. A developer implementing FEAT-A may unknowingly conflict with FEAT-B. Automated conflict detection surfaces these issues early, keeps the backlog coherent, and reduces rework. This is especially valuable for projects using `ll-parallel` or `ll-sprint` where multiple agents execute concurrently.

## Proposed Solution

TBD - requires investigation

Likely approach:
- Load all open issue files and extract key metadata (title, summary, objectives, architecture notes, integration maps)
- Use LLM-based pairwise or cluster comparison to identify conflict patterns:
  - **Requirement conflicts**: Issue A requires X, Issue B requires not-X
  - **Objective conflicts**: Two issues solve the same problem differently
  - **Architecture conflicts**: Incompatible technical approaches (e.g., sync vs async, different data models)
  - **Scope overlap**: Issues that partially duplicate each other
- Generate a ranked conflict report grouped by severity
- Recommended changes: merge, deprecate, split, add dependency, update scope
- Interactive approval loop (similar to `ready-issue`) or `--auto` bypass

## Integration Map

### Files to Modify
- TBD - new skill at `skills/audit-issue-conflicts/SKILL.md`

### Dependent Files (Callers/Importers)
- `commands/` - new command entry if wired as a slash command
- `.claude-plugin/plugin.json` - register skill
- `hooks/hooks.json` - optional hook integration
- `CLAUDE.md` - add to command list

### Similar Patterns
- `skills/audit-claude-config/` - audit pattern with report + recommendations
- `skills/tradeoff-review-issues/` - issue analysis with recommendations
- `skills/align-issues/` - multi-issue validation with document comparison
- `skills/ready-issue/` - interactive approval pattern

### Tests
- TBD - unit tests for conflict detection logic if implemented in Python
- Integration tests covering: no conflicts, single conflict, multiple conflicts, `--auto` mode

### Documentation
- `docs/ARCHITECTURE.md` - mention new skill
- `CLAUDE.md` - add to command list under Issue Refinement or Meta-Analysis

### Configuration
- N/A (no new config keys required; reads existing `issues.base_dir`)

## Implementation Steps

1. Define conflict taxonomy and detection heuristics (requirement, objective, architecture, scope)
2. Implement issue loader that extracts structured metadata from open issue files
3. Build conflict detection engine (LLM-assisted comparison with structured output)
4. Implement recommendation synthesizer (merge/deprecate/split/dependency suggestions)
5. Implement interactive approval loop with per-recommendation accept/reject
6. Implement `--auto` flag mode that applies all recommendations without prompting
7. Wire into plugin.json and CLAUDE.md
8. Write tests and documentation

## API/Interface

```python
# CLI invocation
/ll:audit-issue-conflicts          # interactive mode
/ll:audit-issue-conflicts --auto   # auto-apply all recommendations
/ll:audit-issue-conflicts --dry-run  # report only, no changes

# Recommendation object structure (conceptual)
{
  "conflict_type": "objective",  # requirement | objective | architecture | scope
  "severity": "medium",          # low | medium | high
  "issues": ["FEAT-100", "FEAT-200"],
  "description": "Both issues implement caching but use incompatible backends",
  "recommendation": "merge",     # merge | deprecate | split | add_dependency | update_scope
  "proposed_change": "Close FEAT-200, add its scope to FEAT-100"
}
```

## Impact

- **Priority**: P3 - Medium value; improves backlog hygiene but not blocking
- **Effort**: Medium - New skill with LLM-based analysis; similar to `audit-claude-config`
- **Risk**: Low - Read-heavy with optional write; `--auto` mode is the only risk surface
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `captured`, `issue-management`, `audit`

## Status

**Open** | Created: 2026-04-10 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f3d0cb5-182d-4d87-9949-f092df0ed97f.jsonl`
