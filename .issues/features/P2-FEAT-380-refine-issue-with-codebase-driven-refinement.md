---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# FEAT-380: Create new refine_issue with codebase-driven refinement

## Summary

Create a new `/ll:refine_issue` command that performs substantive issue refinement by researching the codebase to identify and fill knowledge gaps needed for successful implementation. Unlike the current command (being renamed to `format_issue` in ENH-379), this command would read source code, analyze implementation context, and produce genuinely useful content — not template boilerplate.

## Current Behavior

No command currently investigates the codebase to fill knowledge gaps for implementation. The existing `refine_issue` (being renamed to `format_issue`) does template alignment. `ready_issue` does validation/gatekeeping. `verify_issues` checks claim accuracy. None of them research the codebase to enrich issue content with implementation-relevant findings.

## Expected Behavior

A new `/ll:refine_issue` that:
- **Reads the issue**, then **researches the codebase** to understand the problem space
- Identifies what information is missing for successful implementation (not which template sections are absent)
- In **interactive mode**: asks targeted clarifying questions informed by codebase findings
- In **`--auto` mode**: fills gaps with actual research findings (real file paths, actual function signatures, actual behavioral analysis)
- Template compliance is incidental — it writes good content that happens to land in the right sections

## Use Case

**Who**: A developer (human or AI agent) preparing an issue for implementation

**Context**: After capturing an issue and optionally formatting it, the issue has structural completeness but lacks the codebase-specific knowledge needed for implementation — e.g., which functions are involved, what the current code actually does, what patterns exist nearby, what the integration surface looks like.

**Goal**: Enrich the issue with research findings so an implementing agent can start coding without a separate investigation phase.

**Outcome**: Issue contains concrete file paths, function signatures, behavioral analysis, and integration context derived from actual codebase research — not placeholder text.

## Acceptance Criteria

- [ ] Command reads issue content and identifies knowledge gaps (not structural gaps)
- [ ] Command uses Grep/Glob/Read to research the codebase based on issue content
- [ ] Interactive mode asks clarifying questions informed by what was found in the code
- [ ] Auto mode fills gaps with actual codebase findings (file paths, function names, behavioral descriptions)
- [ ] Existing non-empty sections are preserved (same preservation rules as current refine_issue)
- [ ] Output clearly distinguishes researched content from placeholder content
- [ ] Pipeline position: runs after `format_issue`, before `ready_issue`

## API/Interface

```bash
# Interactive refinement with codebase research
/ll:refine_issue FEAT-225

# Auto-refine with codebase research (non-interactive)
/ll:refine_issue BUG-042 --auto

# Dry-run to preview what research would produce
/ll:refine_issue ENH-015 --auto --dry-run
```

## Motivation

- **Implementation quality**: Issues enriched with real codebase context lead to better first-attempt implementations
- **Reduced back-and-forth**: Implementing agents spend less time investigating and more time coding
- **Pipeline completeness**: Fills the gap between structural formatting and validation in the issue lifecycle
- **Automation readiness**: `--auto` mode enables fully automated issue enrichment in `ll-auto`/`ll-parallel`/`ll-sprint` pipelines

## Proposed Solution

The new command should follow a research-first approach:

1. **Read the issue** and extract key concepts (file paths, function names, error descriptions, feature descriptions)
2. **Research the codebase** using Grep/Glob/Read:
   - Find files mentioned or implied by the issue
   - Read relevant source code to understand current behavior
   - Identify related functions, callers, importers
   - Find similar patterns in the codebase
   - Check test coverage for affected areas
3. **Identify knowledge gaps** — what does an implementer need to know that isn't in the issue?
   - For BUGs: root cause, affected code paths, reproduction context
   - For FEATs: existing patterns to follow, integration points, test patterns
   - For ENHs: current implementation details, refactoring surface, consistency considerations
4. **Fill gaps** (auto) or **ask questions** (interactive) using research findings as context
5. **Update the issue** with enriched content

Key difference from current `refine_issue`: the gap analysis is driven by **implementation needs**, not **template structure**. A section can be "present" per the template but still lack the codebase-specific context an implementer needs.

## Integration Map

### Files to Modify
- `commands/refine_issue.md` — new file (after ENH-379 renames old one to `format_issue.md`)

### Dependent Files (Callers/Importers)
- `commands/ready_issue.md` — update integration/pipeline references
- `commands/format_issue.md` — update next-step references (post ENH-379)
- `commands/manage_issue.md` — update pipeline references
- `.claude/CLAUDE.md` — update command list and pipeline documentation

### Similar Patterns
- Current `refine_issue.md` — reuse issue-finding logic (step 1), flag parsing, session log appending
- `ready_issue.md --deep` — uses sub-agents for codebase verification; similar research pattern

### Tests
- TBD — identify if command tests exist

### Documentation
- `docs/ARCHITECTURE.md` — update issue pipeline documentation

### Configuration
- `.claude-plugin/plugin.json` — command registration

## Implementation Steps

1. Design the research-driven gap analysis logic (what to search for based on issue type and content)
2. Write the new `commands/refine_issue.md` command definition
3. Update pipeline references across other commands and docs
4. Test with representative BUG, FEAT, and ENH issues in both interactive and auto modes

## Impact

- **Priority**: P2 - Fills a significant gap in the issue lifecycle pipeline
- **Effort**: Medium - New command with codebase research logic; can reuse patterns from existing commands
- **Risk**: Low - New command, doesn't modify existing behavior
- **Breaking Change**: No - New command (old `refine_issue` already renamed by ENH-379)

## Blocked By

- ENH-379 (rename current `refine_issue` to `format_issue` to free the name)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Pipeline documentation and command listing |
| architecture | docs/ARCHITECTURE.md | Issue lifecycle and command architecture |

## Labels

`feature`, `commands`, `issue-pipeline`, `captured`

## Session Log
- `/ll:capture_issue` - 2026-02-12T12:00:00Z - `~/.claude/projects/<project>/d65a885a-6b92-4b2e-be03-ca8f0f08c767.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P2
