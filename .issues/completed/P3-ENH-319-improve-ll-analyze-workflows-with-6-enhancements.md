---
discovered_date: 2026-02-10
discovered_by: capture_issue
---

# ENH-319: Improve /ll:analyze-workflows with 6 enhancements

## Summary

Add focused capabilities to `/ll:analyze-workflows` to make it more efficient, interactive, and actionable. Currently, the command is a basic orchestrator that runs the 3-step analysis pipeline and generates a static report. This enhancement adds incremental analysis, smart caching, interactive refinement, auto-implementation, filtering, and trend tracking to transform it from a reporting tool into an actionable workflow automation engine.

## Context

Identified from conversation discussing improvements to `/ll:analyze-workflows`. User asked "how might we improve it?" and the following enhancements were proposed and prioritized based on value and feasibility.

## Current Behavior

`/ll:analyze-workflows`:
- Analyzes all messages every time (no incremental support)
- Auto-detects most recent user-messages file
- Runs 3-step pipeline sequentially
- Generates static YAML outputs and markdown summary
- No filtering or scoping options
- No comparison with previous runs
- No path to implement proposals

## Expected Behavior

Enhanced `/ll:analyze-workflows` should:
- Support incremental analysis (only new messages since last run)
- Smart caching and resumption from failed steps
- Allow filtering by date range, categories, patterns, frequency thresholds
- Offer interactive proposal refinement (let user select which to implement)
- Auto-implement small/high-priority proposals with user permission
- Track trends and compare with previous analysis runs
- Offer to create issues from proposals via existing `/ll:capture_issue`

## Proposed Solution

Implement 6 enhancements grouped into three categories:

### Category 1: Efficiency & Performance (P2)

1. **Incremental Analysis** (HIGH VALUE)
   - Track last analyzed message timestamp in metadata
   - Only process new messages since last run
   - Merge with previous analysis results
   - Add `--incremental` flag (default: true for repeat runs)
   - Add `--fresh` flag to force full re-analysis
   - Metadata format:
     ```yaml
     last_analysis:
       timestamp: "2026-02-10T10:30:00Z"
       messages_analyzed: 1-450
     incremental: true
     new_messages_analyzed: 451-520
     ```

2. **Smart Caching & Resumption**
   - Add `--resume` flag to continue from last successful step
   - Cache intermediate results (step1-patterns.yaml, step2-workflows.yaml)
   - Clear cache option: `--fresh`

### Category 2: Interactivity & Actionability (P2)

3. **Interactive Proposal Refinement** (QUICK WIN)
   - After generating proposals, use AskUserQuestion:
     - "Which proposals interest you?" (multi-select)
     - "What priority threshold to implement?" (HIGH only? MEDIUM+?)
     - "Auto-implement SMALL effort proposals?" (yes/no)
   - Offer to create issues from selected proposals via `/ll:capture_issue`

4. **Auto-Implementation Mode** (QUICK WIN)
   - For proposals with `effort: SMALL` and `priority: HIGH`:
     - Ask permission to implement automatically
     - Create command/hook/script files
     - Add to plugin.json if needed
     - Commit the changes
   - Add `--auto-implement` flag to enable
   - Add `--priority` and `--effort` filters

### Category 3: Analysis & Insights (P3)

5. **Filtering & Scoping**
   - Add arguments:
     - `--since YYYY-MM-DD`: Only analyze messages after date
     - `--until YYYY-MM-DD`: Only analyze messages before date
     - `--category CATEGORY`: Filter by message category
     - `--exclude PATTERN`: Exclude patterns matching regex
     - `--min-frequency N`: Only show patterns with frequency >= N
     - `--focus KEYWORD`: Focus analysis on specific topic

6. **Trend Tracking & Comparison**
   - Compare current analysis with previous runs
   - Show pattern evolution (frequency increases/decreases)
   - Identify likely causes of changes (e.g., new command implemented)
   - Add `--compare-with-previous` flag
   - Output format:
     ```markdown
     ## Trend Analysis
     - "create issue" pattern: 8 → 3 occurrences (-62%)
       ✓ Likely reduced by /ll:capture_issue implementation
     - "run tests" pattern: 12 → 15 occurrences (+25%)
       ⚠ Consider test automation improvements
     ```

## Motivation

Users must manually re-analyze entire message history every time, cannot filter or scope analysis, and cannot act on proposals without manual work. The command generates static reports that require significant manual effort to translate into actual improvements.

## Success Metrics

- **Time savings**: Incremental analysis reduces re-analysis time by 70-90% for large histories
- **Actionability**: 50%+ of high-priority proposals get implemented (vs current ~10%)
- **Adoption**: Users run analysis weekly instead of once (current behavior)

## Scope Boundaries

**In scope:**
- Enhancements 1-6 listed above
- Backward compatibility with existing output formats
- Config-driven customization

**Out of scope:**
- Changing the 3-step pipeline architecture (agent → CLI → skill)
- Modifying individual pipeline components (pattern-analyzer, sequence-analyzer, proposer)
- Real-time analysis (still batch-based on extracted messages)
- Cross-project analysis (single project only)
- Machine learning or AI-powered pattern detection

## Backwards Compatibility

All enhancements should be:
- **Opt-in**: Default behavior remains unchanged unless flags are used
- **Config-driven**: New features can be disabled in ll-config.json
- **Output-compatible**: Existing YAML schema preserved, new fields added
- **Command-compatible**: Existing usage `/ll:analyze-workflows` still works

## Impact

- **Priority**: P2 (High value improvements to existing feature)
- **Effort**: MEDIUM (6 enhancements, touches command + CLI + config)
- **Risk**: LOW (incremental improvements, backward compatible, opt-in features)

## Implementation Steps

### Phase 1: Quick Wins (Immediate Value)
1. Interactive proposal refinement (#3)
2. Auto-implementation mode (#4)
3. Smart caching & resumption (#2)

### Phase 2: Core Enhancements
4. Incremental analysis (#1)
5. Filtering & scoping (#5)
6. Trend tracking & comparison (#6)

## Integration Map

### Files to Modify
- `commands/analyze-workflows.md` - Add flags for incremental, filtering, auto-implement
- `agents/workflow-pattern-analyzer/AGENT.md` - Support incremental analysis
- `skills/workflow-automation-proposer/SKILL.md` - Add interactive refinement, auto-implementation

### Dependent Files (Callers/Importers)
- `scripts/little_loops/workflow_sequence_analyzer.py` - Pipeline Step 2

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — unit tests for incremental analysis, caching, filtering logic
- `scripts/tests/test_workflow_sequence_analyzer_integration.py` — integration test for end-to-end pipeline with --incremental, --fresh flags

### Documentation
- `docs/ARCHITECTURE.md` — update workflow analysis section with incremental/caching architecture
- `docs/COMMANDS.md` — document new flags (--incremental, --fresh, --since, --focus, --auto-implement)
- `.claude/CLAUDE.md` — update analyze-workflows description with new capabilities

### Configuration
- `.claude/ll-config.json` - Potential new workflow analysis settings

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Documents workflow-pattern-analyzer agent and workflow_sequence_analyzer.py module |
| architecture | docs/API.md | Detailed API reference for workflow_sequence_analyzer module (Step 2 of pipeline) |
| guidelines | .claude/CLAUDE.md | Overview of /ll:analyze-workflows command and plugin structure |

## Blocks

- ENH-366: add agents directory to plugin.json (shared plugin.json)
- BUG-364: marketplace JSON version mismatch (shared plugin.json)

## Labels

`enhancement`, `workflow-analysis`, `captured`, `meta-issue`

---

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID
- Conceptual enhancement describing planned improvements
- /ll:analyze-workflows command exists (workflow-automation-proposer skill)
- No implementation exists yet for the 6 described enhancements

---

## Tradeoff Review Note

**Reviewed**: 2026-02-10 by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | HIGH |
| Complexity added | HIGH |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first - 6 enhancements in one issue is too much. The issue already acknowledges this with a phased approach (Phase 1: Quick Wins, Phase 2: Core Enhancements), but all 6 are tracked together.

### Suggested Split
Consider splitting into smaller issues:
- **ENH-319a**: Interactive proposal refinement + Auto-implementation mode (the quick wins)
- **ENH-319b**: Smart caching & resumption
- **ENH-319c**: Incremental analysis
- **ENH-319d**: Filtering & scoping + Trend tracking

This allows incremental delivery and clearer progress tracking.

---

## Tradeoff Review Note (2026-02-11)

**Reviewed**: 2026-02-11 by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | HIGH |
| Complexity added | HIGH |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first - 6 enhancements in one issue is too broad. Decompose into smaller issues before implementation:
- **ENH-319a**: Interactive proposal refinement + Auto-implementation mode (quick wins)
- **ENH-319b**: Smart caching & resumption
- **ENH-319c**: Incremental analysis
- **ENH-319d**: Filtering & scoping + Trend tracking

---

## Tradeoff Review Note

**Reviewed**: 2026-02-12 by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | HIGH |
| Complexity added | HIGH |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first - Meta-issue tracking 6 separate enhancements that should be split into individual issues for incremental delivery. Consistent recommendation across three reviews to decompose before implementation.

---

## Status

**Closed (won't-fix)** | Created: 2026-02-10 | Closed: 2026-02-13 | Priority: P2

**Reason**: Over-engineered. Three separate tradeoff reviews unanimously rated HIGH effort, HIGH complexity, MEDIUM utility and recommended decomposition. More fundamentally, building incremental analysis, smart caching, auto-implementation, and trend tracking for an occasionally-run feature is premature. Individual pieces can be reopened as standalone issues if actual usage demonstrates the need.
