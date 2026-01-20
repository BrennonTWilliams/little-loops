---
discovered_commit: 8279174
discovered_branch: main
discovered_date: 2026-01-12T12:00:00Z
---

# FEAT-026: Workflow Pattern Analysis Agent

## Summary

Create `workflow-pattern-analyzer` agent (Step 1 of the workflow analysis pipeline) that categorizes user messages and identifies repeated patterns for downstream workflow analysis.

## Motivation

User message extraction (FEAT-011) provides raw data, but identifying actionable automation opportunities requires pattern analysis. This agent performs the first-pass analysis to:

- Categorize messages by action type (code modification, debugging, git operations, etc.)
- Detect repeated patterns that indicate automation opportunities
- Extract common phrases and tool references
- Prepare structured data for sequence analysis (FEAT-027)

This enables the full workflow analysis pipeline: Pattern Analysis → Sequence Analysis → Automation Proposals.

## Proposed Implementation

### 1. Agent Definition: `agents/workflow-pattern-analyzer.md`

```yaml
---
name: workflow-pattern-analyzer
description: |
  First-pass analysis agent that categorizes user messages and identifies repeated patterns.
  Used as Step 1 of the /ll:analyze-workflows pipeline.

  <example>
  Input: user-messages.jsonl with 200 messages
  → Categorize each message by action type
  → Identify repeated request patterns
  → Output step1-patterns.yaml
  </example>

allowed_tools:
  - Read
  - Write
  - Grep
  - Glob
model: sonnet
---
```

### 2. Category Taxonomy

The agent classifies each message into one of 15 categories:

| Category | Indicators |
|----------|------------|
| `code_modification` | add, fix, change, update, modify, refactor |
| `code_review` | review, check, validate, audit, lint |
| `file_search` | find, where is, locate, search for |
| `file_read` | read, show me, what's in, open |
| `file_write` | create, write, generate, save |
| `git_operation` | commit, push, pull, branch, merge, status |
| `debugging` | error, bug, fix, why, not working, issue |
| `explanation` | explain, what does, how does, why |
| `documentation` | document, README, comment, describe |
| `testing` | test, spec, coverage, mock, assert |
| `presentation` | slide, marp, presentation, PDF |
| `slash_command` | starts with "/" or mentions known command |
| `planning` | plan, design, architect, strategy |
| `content_creation` | write, draft, create content, module |
| `research` | research, find out, look up, investigate |

### 3. Pattern Detection Logic

```python
# Pseudocode for pattern detection

def detect_patterns(messages: list[UserMessage]) -> list[Pattern]:
    """Identify repeated request patterns."""

    # 1. Normalize messages (lowercase, remove punctuation)
    normalized = [normalize(m.content) for m in messages]

    # 2. Extract n-grams (2-4 words)
    ngrams = extract_ngrams(normalized, n_range=(2, 4))

    # 3. Count frequencies
    freq = Counter(ngrams)

    # 4. Filter to patterns with frequency >= 3
    patterns = [
        Pattern(text=text, frequency=count, category=categorize(text))
        for text, count in freq.items()
        if count >= 3
    ]

    return sorted(patterns, key=lambda p: p.frequency, reverse=True)
```

### 4. Output Schema: `step1-patterns.yaml`

```yaml
analysis_metadata:
  source_file: user-messages-20260112.jsonl
  message_count: 200
  analysis_timestamp: 2026-01-12T10:00:00Z
  agent: workflow-pattern-analyzer
  version: "1.0"

category_distribution:
  - category: code_modification
    count: 45
    percentage: 22.5
    example_messages:
      - uuid: "msg-001"
        content: "Add error handling to the login function"
      - uuid: "msg-015"
        content: "Fix the null pointer in checkout.py"
  - category: git_operation
    count: 32
    percentage: 16.0
    example_messages:
      - uuid: "msg-003"
        content: "Commit these changes"
  # ... more categories

repeated_patterns:
  - pattern: "run tests"
    frequency: 12
    category: testing
    example_messages: ["msg-002", "msg-018", "msg-045"]
  - pattern: "fix the"
    frequency: 8
    category: debugging
    example_messages: ["msg-007", "msg-022", "msg-089"]
  # ... more patterns

common_phrases:
  - phrase: "can you"
    count: 25
  - phrase: "help me"
    count: 18
  - phrase: "what does"
    count: 12
  # ... more phrases

tool_references:
  - tool: "/ll:commit"
    count: 15
    category: git_operation
  - tool: "/ll:run_tests"
    count: 8
    category: testing
  - tool: "grep"
    count: 6
    category: file_search
  # ... more tools

entity_inventory:
  files:
    - entity: "checkout.py"
      mentions: 8
      messages: ["msg-007", "msg-015", "msg-089"]
    - entity: "README.md"
      mentions: 5
      messages: ["msg-012", "msg-034"]
  commands:
    - entity: "/ll:commit"
      mentions: 15
    - entity: "/ll:run_tests"
      mentions: 8
  concepts:
    - entity: "authentication"
      mentions: 6
    - entity: "error handling"
      mentions: 5
```

### 5. Agent System Prompt

```markdown
# Workflow Pattern Analyzer

You are the first step in a 3-step workflow analysis pipeline. Your job is to analyze user messages and identify patterns.

## Input

You will be given a JSONL file containing user messages extracted from Claude Code sessions.

## Output

Write analysis results to `.claude/workflow-analysis/step1-patterns.yaml`

## Analysis Steps

1. **Read the input file** and parse all messages

2. **Categorize each message** using the category taxonomy:
   - Match keywords/phrases to categories
   - Each message gets exactly one primary category
   - Record confidence if uncertain

3. **Detect repeated patterns**:
   - Look for repeated 2-4 word phrases
   - Minimum frequency: 3 occurrences
   - Group by category

4. **Extract common phrases**:
   - Identify filler phrases ("can you", "help me", "please")
   - Track frequency

5. **Inventory tool references**:
   - Slash commands (/ll:*, etc.)
   - Tool names (grep, git, etc.)

6. **Build entity inventory**:
   - File paths mentioned
   - Commands referenced
   - Domain concepts

## Important Guidelines

- Be thorough but concise
- Include example message UUIDs for verification
- Calculate accurate percentages
- Sort results by frequency (descending)
- This output feeds into Step 2 (workflow-sequence-analyzer)
```

## Location

| Component | Path |
|-----------|------|
| Agent | `agents/workflow-pattern-analyzer.md` |
| Output | `.claude/workflow-analysis/step1-patterns.yaml` |

## Current Behavior

No pattern analysis agent exists. Users must manually review messages to identify patterns.

## Expected Behavior

```bash
# After running /ll:analyze-workflows, Step 1 produces:
$ cat .claude/workflow-analysis/step1-patterns.yaml

analysis_metadata:
  source_file: user-messages-20260112.jsonl
  message_count: 200
  ...

category_distribution:
  - category: code_modification
    count: 45
    percentage: 22.5
  ...

repeated_patterns:
  - pattern: "run tests"
    frequency: 12
  ...
```

## Impact

- **Severity**: Medium - Enables workflow analysis pipeline
- **Effort**: Medium - Requires taxonomy design and pattern detection logic
- **Risk**: Low - Read-only analysis, no modifications

## Dependencies

None external. Uses standard text processing.

## Blocked By

- FEAT-011: User Message History Extraction (provides input data)

## Blocks

- FEAT-027: Workflow Sequence Analyzer Module (consumes step1-patterns.yaml)
- FEAT-029: `/ll:analyze-workflows` Command (orchestrates this agent via Task tool)

## Labels

`feature`, `agent`, `workflow-analysis`, `pattern-detection`

---

## Status

**Open** | Created: 2026-01-12 | Priority: P2

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-12
- **Status**: Completed

### Changes Made
- `agents/workflow-pattern-analyzer.md`: Created new agent with 15-category taxonomy, pattern detection logic, and structured YAML output schema
- `thoughts/shared/plans/2026-01-12-FEAT-026-management.md`: Implementation plan

### Verification Results
- Tests: PASS (526 tests)
- Lint: PASS
- Types: PASS
