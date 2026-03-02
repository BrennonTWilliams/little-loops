# ENH-500: CLI Tool Consolidation Audit — Implementation Plan

**Date**: 2026-03-01
**Issue**: P3-ENH-500-cli-tool-consolidation-audit.md
**Action**: implement

## Audit Summary

### One-Sentence Unique Use Case per Tool

| # | Tool | Unique Goal | Distinct? |
|---|------|-------------|-----------|
| 1 | `ll-auto` | Process the entire issue backlog one-at-a-time in priority order | Needs sharpening vs ll-sprint |
| 2 | `ll-parallel` | Process issues concurrently in isolated git worktrees | Yes |
| 3 | `ll-sprint` | Define, manage, and execute a curated set of issues with dependency-aware wave ordering | Needs sharpening vs ll-auto |
| 4 | `ll-loop` | Run repeating YAML-defined FSM automation loops | Yes |
| 5 | `ll-workflows` | Cluster user messages into multi-step workflow patterns (analysis pipeline step 2) | Yes, but description is opaque |
| 6 | `ll-messages` | Extract user messages from Claude Code session logs | Yes |
| 7 | `ll-history` | Display statistics and trend analysis for completed issues | Yes |
| 8 | `ll-sync` | Sync local .issues/ files with GitHub Issues | Yes |
| 9 | `ll-deps` | Discover and validate cross-issue dependencies | Yes |
| 10 | `ll-issues` | Unified issue management: list, show, sequence, impact-effort | Yes |
| 11 | `ll-next-id` | Print next globally unique issue number | Redundant (also in ll-issues) |
| 12 | `ll-verify-docs` | Verify documented counts match actual file counts | Yes |
| 13 | `ll-check-links` | Check markdown documentation for broken links | Yes |

### Consolidation Test Results

**Overlap 1: ll-auto vs ll-sprint**
- Both process issues, but selection model differs fundamentally
- ll-auto: dynamic selection (entire backlog, priority-ordered, filtered at runtime)
- ll-sprint: explicit selection (curated YAML list, dependency-wave ordered, managed lifecycle)
- **Verdict**: NOT redundant — descriptions need sharpening to make the distinction clear

**Overlap 2: ll-loop vs ll-workflows**
- Despite both containing "workflow" in their domain, they are completely different
- ll-loop: executes FSM YAML definitions (automation runner)
- ll-workflows: analyzes JSONL message logs to find patterns (data analysis)
- **Verdict**: NOT redundant — no description change needed for differentiation

**Overlap 3: ll-next-id vs ll-issues next-id**
- Genuinely redundant — both call `get_next_issue_number()` and print the result
- ll-next-id already notes this in its epilog
- **Verdict**: Genuine redundancy, but low-impact. Propose deprecation in a separate issue.

### Tool Count Assessment

- **Total CLI tools**: 13
- **Recommended range**: 10–20
- **Assessment**: Within recommended range. No tools need removal.

## Implementation Phases

### Phase 1: Sharpen argparse descriptions (4 tools)

Only tools with ambiguous or unclear descriptions need changes:

1. **ll-auto** (`cli/auto.py:22`):
   - Current: `"Automated sequential issue management with Claude CLI"`
   - New: `"Process all backlog issues sequentially in priority order"`
   - Module docstring: `"ll-auto: Process all backlog issues sequentially in priority order."`

2. **ll-parallel** (`cli/parallel.py:34`):
   - Current: `"Parallel issue management with git worktrees"`
   - New: `"Process issues concurrently using isolated git worktrees"`
   - Module docstring: `"ll-parallel: Process issues concurrently using isolated git worktrees."`

3. **ll-sprint** (`cli/sprint/__init__.py:70`):
   - Current: `"Manage and execute sprint/sequence definitions"`
   - New: `"Define and execute curated issue sets with dependency-aware ordering"`
   - Module docstring: `"ll-sprint: Define and execute curated issue sets with dependency-aware ordering."`

4. **ll-workflows** (`workflow_sequence_analyzer.py:816`):
   - Current: `"Workflow Sequence Analyzer - Step 2 of workflow analysis pipeline"`
   - New: `"Identify multi-step workflow patterns from user message history"`
   - Module docstring update at top of file

### Phase 2: Update CLAUDE.md CLI tool descriptions

Update the CLI Tools section to use crisp, differentiated descriptions.

### Phase 3: Update README.md section headers

Update section header text for ll-auto, ll-parallel, ll-sprint, ll-workflows to match new descriptions.

### Phase 4: Add CLI Quick Reference to help.md

Add a CLI TOOLS section to `commands/help.md` output that lists all 13 tools with one-line descriptions, so `/ll:help` surfaces CLI tools prominently.

### Phase 5: Document consolidation proposals

Note the ll-next-id / ll-issues overlap in the issue resolution, recommending a separate deprecation issue.

## Success Criteria

- [x] Each tool has a unique, unambiguous one-sentence description
- [ ] Argparse descriptions updated for 4 tools
- [ ] Module docstrings updated for 4 tools
- [ ] CLAUDE.md updated with sharpened descriptions
- [ ] README.md updated with sharpened section headers
- [ ] help.md includes CLI tools listing
- [ ] Consolidation proposals documented
- [ ] All tests pass
- [ ] Lint/type checks pass
