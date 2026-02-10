---
discovered_date: 2026-02-10
discovered_by: capture_issue
---

# ENH-319: Improve /ll:analyze-workflows with 12+ enhancements

## Summary

Add sophisticated capabilities to `/ll:analyze-workflows` to make it more efficient, interactive, and actionable. Currently, the command is a basic orchestrator that runs the 3-step analysis pipeline and generates a static report. This enhancement adds incremental analysis, interactive refinement, auto-implementation, filtering, trend tracking, and other improvements to transform it from a reporting tool into an actionable workflow automation engine.

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
- No feedback loop tracking

## Expected Behavior

Enhanced `/ll:analyze-workflows` should:
- Support incremental analysis (only new messages since last run)
- Allow filtering by date range, categories, patterns, frequency thresholds
- Offer interactive proposal refinement (let user select which to implement)
- Auto-implement small/high-priority proposals with user permission
- Track trends and compare with previous analysis runs
- Support custom pattern rules via config
- Integrate with issue management (create issues from proposals)
- Execute Step 1 and Step 2 in parallel where possible
- Provide progressive updates and visual indicators
- Track proposal implementation outcomes and impact
- Detect cross-session patterns and abandoned workflows
- Smart caching and resumption from failed steps

## Proposed Solution

Implement 12 enhancements grouped into three categories:

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

2. **Parallel Execution**
   - Run Step 1a (pattern categorization via agent) and Step 1b (basic statistics via CLI) in parallel
   - Merge results before proceeding to Step 2
   - Expected 30-40% faster execution

3. **Smart Caching & Resumption**
   - Add `--resume` flag to continue from last successful step
   - Cache intermediate results (step1-patterns.yaml, step2-workflows.yaml)
   - Clear cache option: `--fresh`

### Category 2: Interactivity & Actionability (P2)

4. **Interactive Proposal Refinement** (QUICK WIN)
   - After generating proposals, use AskUserQuestion:
     - "Which proposals interest you?" (multi-select)
     - "What priority threshold to implement?" (HIGH only? MEDIUM+?)
     - "Auto-implement SMALL effort proposals?" (yes/no)

5. **Auto-Implementation Mode** (QUICK WIN)
   - For proposals with `effort: SMALL` and `priority: HIGH`:
     - Ask permission to implement automatically
     - Create command/hook/script files
     - Add to plugin.json if needed
     - Commit the changes
   - Add `--auto-implement` flag to enable
   - Add `--priority` and `--effort` filters

6. **Integration with Issue Management**
   - Auto-create enhancement issues from HIGH priority proposals
   - Link proposals to existing issues that would be solved
   - Track which proposals have been implemented
   - Add `--create-issues` flag
   - Add `--label` option for issue tagging

### Category 3: Analysis & Insights (P3)

7. **Filtering & Scoping**
   - Add arguments:
     - `--since YYYY-MM-DD`: Only analyze messages after date
     - `--until YYYY-MM-DD`: Only analyze messages before date
     - `--category CATEGORY`: Filter by message category
     - `--exclude PATTERN`: Exclude patterns matching regex
     - `--min-frequency N`: Only show patterns with frequency >= N
     - `--focus KEYWORD`: Focus analysis on specific topic

8. **Trend Tracking & Comparison**
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

9. **Pattern Rule Customization**
   - Let users define custom patterns in ll-config.json:
     ```json
     {
       "workflow_analysis": {
         "custom_patterns": [
           {
             "name": "database_migration",
             "keywords": ["migrate", "schema", "alembic"],
             "min_frequency": 2,
             "suggest_type": "slash_command"
           }
         ]
       }
     }
     ```

10. **Cross-Session Pattern Detection**
    - Detect patterns spanning multiple days
    - Identify "morning routines" or "sprint rituals"
    - Find abandoned workflows (started but never finished)

11. **Feedback Loop Tracking**
    - Track proposal outcomes in metadata:
      ```yaml
      proposals:
        - id: prop-001
          status: implemented
          implemented_date: "2026-02-05"
          impact_metrics:
            usage_count: 23
            time_saved_estimate: "45 minutes"
            user_feedback: "Very helpful"
      ```

12. **Smarter Output & UX**
    - Progressive updates during analysis (show what's happening)
    - Collapsible sections in summary
    - Visual indicators (✓, ⚠, ●) for priority/status
    - Direct action links: `Run: /ll:implement-proposal prop-001`

## Current Pain Point

Users must manually re-analyze entire message history every time, cannot filter or scope analysis, cannot act on proposals without manual work, and have no visibility into whether implemented automations are actually helping. The command generates static reports that require significant manual effort to translate into actual improvements.

## Success Metrics

- **Time savings**: Incremental analysis reduces re-analysis time by 70-90% for large histories
- **Actionability**: 50%+ of high-priority proposals get implemented (vs current ~10%)
- **Adoption**: Users run analysis weekly instead of once (current behavior)
- **Feedback loop**: Track that implemented automations actually reduce pattern frequency

## Scope Boundaries

**In scope:**
- Enhancements 1-12 listed above
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
- **Effort**: LARGE (12 enhancements, touches command + CLI + config)
- **Risk**: LOW (incremental improvements, backward compatible, opt-in features)

## Proposed Implementation

### Phase 1: Quick Wins (Immediate Value)
1. Incremental analysis (ENH #1)
2. Interactive proposal refinement (ENH #4)
3. Auto-implementation mode (ENH #5)

### Phase 2: Analysis Enhancements
4. Filtering & scoping (ENH #7)
5. Trend tracking & comparison (ENH #8)
6. Smarter output & UX (ENH #12)

### Phase 3: Advanced Features
7. Pattern rule customization (ENH #9)
8. Issue management integration (ENH #6)
9. Feedback loop tracking (ENH #11)
10. Cross-session detection (ENH #10)
11. Parallel execution (ENH #2)
12. Smart caching (ENH #3)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Documents workflow-pattern-analyzer agent and workflow_sequence_analyzer.py module |
| architecture | docs/API.md | Detailed API reference for workflow_sequence_analyzer module (Step 2 of pipeline) |
| guidelines | .claude/CLAUDE.md | Overview of /ll:analyze-workflows command and plugin structure |

## Labels

`enhancement`, `workflow-analysis`, `captured`, `meta-issue`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2
