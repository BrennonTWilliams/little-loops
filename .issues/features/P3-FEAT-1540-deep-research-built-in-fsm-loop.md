---
id: FEAT-1540
type: FEAT
priority: P3
status: open
discovered_date: 2026-05-16
discovered_by: capture-issue
captured_at: '2026-05-17T04:33:09Z'
---

# FEAT-1540: Add deep-research built-in FSM loop for iterative web research synthesis

## Summary

Add a new built-in FSM loop `deep-research` that accepts a research topic or question, iteratively performs web searches, evaluates sources, identifies knowledge gaps, and synthesizes findings into a structured research report. Modeled on how deep research tools (Perplexity, ChatGPT deep research, Gemini deep research) work but as an ll automation loop.

## Current Behavior

No built-in loop exists for structured, iterative web research. Users must manually issue search queries, evaluate results, track coverage, and synthesize findings — a tedious and often incomplete process with no automated gap-identification or convergence criterion.

## Expected Behavior

Users can run:

```bash
ll-loop run deep-research --topic "What are the trade-offs of CRDT vs OT for collaborative editing?" --depth 3
```

or trigger via Claude Code:

```
/ll:create-loop deep-research
```

The loop:
1. Generates an initial set of search queries from the topic
2. Executes web searches and scores source relevance and credibility
3. Extracts key claims and synthesizes a running knowledge base
4. Identifies coverage gaps and generates follow-up queries
5. Iterates until coverage score meets threshold or `max_iterations` exhausted
6. Outputs a structured Markdown research report with citations

## Motivation

Deep research is one of the most common use cases Claude users perform manually and repetitively. An FSM-based loop that automates query generation, source evaluation, and gap-detection would:
- Reduce manual overhead for research-heavy workflows
- Produce consistently structured, cited outputs
- Complement the existing `rn-plan` loop (FEAT-1534) — deep-research feeds into planning
- Demonstrate ll's capability as a general automation platform beyond code tasks

## Proposed Solution

TBD - requires investigation

**Candidate FSM states:**
- `init` → parse topic, generate initial query set, create output file
- `search` → execute one batch of queries via WebSearch tool
- `evaluate` → score source relevance, extract claims, update knowledge base
- `gap_detect` → compare knowledge base against topic facets, score coverage
- `plan_next` → if coverage < threshold and iterations remain, generate follow-up queries → `search`
- `synthesize` → consolidate knowledge base into structured report
- `done` → write final report, exit

**Key design questions:**
- Coverage scoring model (keyword overlap vs embedding similarity vs LLM judge)
- Citation format and deduplication strategy
- Whether to persist intermediate knowledge base across sessions (resumable)
- Integration with `rn-plan` as a research sub-step

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- `.loops/built-in/` — existing built-in loop definitions to follow
- `FEAT-1534` (`rn-plan` loop) — sibling built-in loop, reference for structure
- `scripts/little_loops/loop_runner.py` — FSM execution engine

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. **Design FSM YAML** — define states, transitions, prompts, and convergence criterion for `deep-research.yaml` in `.loops/built-in/`
2. **Coverage scoring** — design a lightweight coverage model (likely LLM-as-judge comparing topic facets to accumulated claims)
3. **Output format** — define the structured Markdown report schema (executive summary, key findings, source table, gaps, conclusion)
4. **Integration hooks** — optionally wire as a sub-loop callable from `rn-plan`
5. **Tests** — add unit tests for state transitions and integration test with mocked WebSearch
6. **Docs** — add to the built-in loops guide and README

## Impact

- **Priority**: P3 - High-value user workflow, no existing workaround, complements rn-plan
- **Effort**: Large - new FSM design, coverage scoring, report templating
- **Risk**: Medium - WebSearch rate limits and quality variance; coverage scoring may need tuning
- **Breaking Change**: No

## API/Interface

```yaml
# .loops/built-in/deep-research.yaml (sketch)
name: deep-research
description: Iterative web research synthesis loop
inputs:
  topic: str          # Research question or topic
  depth: int          # Max search rounds (default: 5)
  coverage_threshold: float  # Stop when coverage score >= this (default: 0.85)
  max_iterations: int  # Hard cap (default: 30)
outputs:
  report_path: str    # Path to generated Markdown report
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loops`, `built-in-loop`, `research`, `captured`

## Status

**Open** | Created: 2026-05-16 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-17T04:33:09Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/314d8cca-9d5a-4567-8a16-87fa357d45fb.jsonl`
