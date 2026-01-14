# Workflow Analysis System

Automated analysis of Claude Code user messages to identify patterns, workflows, and automation opportunities.

## Overview

The `/analyze-workflows` command analyzes your Claude Code session history to discover:

- **Repeated patterns** - Tasks you do frequently
- **Multi-step workflows** - Common sequences of actions
- **Friction points** - Where manual intervention slows you down
- **Automation opportunities** - Proposed commands, scripts, and hooks

## Quick Start

```bash
# Extract recent user messages (prerequisite)
python scripts/extract_user_messages.py -n 100

# Run the analysis
/analyze-workflows
```

## Architecture

```
~/.claude/projects/.../*.jsonl (Claude Code session logs)
        │
        ▼
┌─────────────────────────────────────────────────┐
│         Message Extraction Scripts              │
│  extract_user_messages.py | get_recent_user_messages.sh
└─────────────────────────────────────────────────┘
        │
        ▼
.claude/user-messages-{timestamp}.jsonl
        │
        ▼
┌─────────────────────────────────────────────────┐
│           /analyze-workflows Command            │
├─────────────────────────────────────────────────┤
│  Step 1: workflow-pattern-analyzer              │
│          ↓ step1-patterns.yaml                  │
│  Step 2: workflow-sequence-analyzer             │
│          ↓ step2-workflows.yaml                 │
│  Step 3: workflow-automation-proposer           │
│          ↓ step3-proposals.yaml                 │
└─────────────────────────────────────────────────┘
        │
        ▼
summary-{timestamp}.md (final report)
```

## Scripts

### `scripts/extract_user_messages.py`

Python script that extracts user messages from Claude Code's JSONL log files.

**Features:**

- Locates Claude Code project folders in `~/.claude/projects/`
- Parses JSONL session files to extract only user messages
- Filters out tool results and system messages
- Outputs timestamped JSONL files

**Usage:**

```bash
# Extract last 100 messages (default)
python scripts/extract_user_messages.py

# Extract last 50 messages
python scripts/extract_user_messages.py -n 50

# Messages since a specific date
python scripts/extract_user_messages.py --since 2026-01-01

# Custom output path
python scripts/extract_user_messages.py -o custom-output.jsonl

# Exclude agent session files
python scripts/extract_user_messages.py --exclude-agents

# Verbose mode
python scripts/extract_user_messages.py -v
```

**Output format (JSONL):**

```json
{
  "content": "the user's message text",
  "timestamp": "2026-01-12T10:30:00+00:00",
  "session_id": "uuid-of-session",
  "uuid": "unique-message-id",
  "cwd": "/path/to/working/directory",
  "git_branch": "main",
  "is_sidechain": false
}
```

### `scripts/get_recent_user_messages.sh`

Bash script with multiple output formats and enhanced project folder discovery.

**Features:**

- Multiple output formats (markdown, JSON, CSV)
- Cross-platform (macOS and Linux)
- Related project folder discovery
- Colored terminal output

**Usage:**

```bash
# Show all messages (markdown to stdout)
./scripts/get_recent_user_messages.sh

# Limit to 10 most recent
./scripts/get_recent_user_messages.sh --limit 10

# Save to JSON file
./scripts/get_recent_user_messages.sh --output file_json

# Save to CSV file
./scripts/get_recent_user_messages.sh --output file_csv

# Include related project directories
./scripts/get_recent_user_messages.sh --include-outside-directories

# Verbose debug output
./scripts/get_recent_user_messages.sh --verbose
```

**Output formats:**

| Format | Description |
|--------|-------------|
| `md` | Markdown to stdout (default) |
| `file_md` | Save to `{project}-recent-messages.md` |
| `file_json` | Save to `{project}-recent-messages.json` |
| `file_csv` | Save to `{project}-recent-messages.csv` |

## Sub-Agents

### Step 1: `workflow-pattern-analyzer`

First-pass analysis identifying patterns in user messages.

**Identifies:**

- Request categories (code_modification, file_search, debugging, etc.)
- Repeated patterns with frequency counts
- Common phrases and terms
- Tool and command references

**Output:** `step1-patterns.yaml`

**Category taxonomy:**

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

### Step 2: `workflow-sequence-analyzer`

Second-pass analysis identifying multi-step workflows.

**Identifies:**

- Session sequences (common request patterns within sessions)
- Process flows (e.g., edit → test → commit)
- Handoff points (where manual intervention needed)
- Temporal patterns (session start/end behaviors)

**Output:** `step2-workflows.yaml`

**Common workflow patterns:**

| Pattern | Description |
|---------|-------------|
| `explore → modify → verify` | Search/read, then change, then test/lint |
| `create → refine → finalize` | Initial creation, iteration, completion |
| `review → fix → commit` | Code review, apply fixes, commit changes |
| `plan → implement → verify` | Discussion/planning, coding, testing |
| `debug → fix → test` | Investigation, fix, verification |

### Step 3: `workflow-automation-proposer`

Final synthesis proposing concrete automation solutions.

**Proposes:**

- New slash commands
- Python or Bash scripts
- Enhancements to existing commands/agents
- Event-driven hooks (PreToolUse, PostToolUse, Stop)

**Output:** `step3-proposals.yaml`

**Priority levels:**

| Priority | Criteria |
|----------|----------|
| HIGH | 5+ occurrences, major friction, simple to implement |
| MEDIUM | 3-4 occurrences, moderate friction, moderate complexity |
| LOW | 1-2 occurrences, minor friction, or complex implementation |

**Effort estimates:**

| Effort | Criteria |
|--------|----------|
| SMALL | Single file, <100 lines, no external dependencies |
| MEDIUM | 2-3 files, 100-300 lines, uses existing patterns |
| LARGE | Multiple files, >300 lines, new patterns or dependencies |

## Output Files

All analysis outputs are written to `.claude/workflow-analysis/`:

| File | Description |
|------|-------------|
| `step1-patterns.yaml` | Pattern analysis from Step 1 |
| `step2-workflows.yaml` | Workflow analysis from Step 2 |
| `step3-proposals.yaml` | Automation proposals from Step 3 |
| `summary-{timestamp}.md` | Human-readable summary report |

## Command Reference

### `/analyze-workflows`

```bash
# Analyze most recent user-messages file (auto-detected)
/analyze-workflows

# Analyze specific file
/analyze-workflows .claude/user-messages-20260112-111551.jsonl

# Analyze aggregated/combined file
/analyze-workflows .claude/all-messages-combined.jsonl
```

## Example Workflow

1. **Extract messages** from your Claude Code history:

   ```bash
   python scripts/extract_user_messages.py -n 200
   ```

2. **Run analysis**:

   ```
   /analyze-workflows
   ```

3. **Review the summary** in `.claude/workflow-analysis/summary-{timestamp}.md`

4. **Implement high-priority proposals** from the recommendations

## Troubleshooting

### No user-messages file found

```
Error: Could not find user-messages file.
```

**Solution:** Run the extraction script first:

```bash
python scripts/extract_user_messages.py
```

### No Claude project folder found

```
Error: No Claude project folder found for: /path/to/project
```

**Solution:** Ensure you've used Claude Code in this project directory. The project folder is created automatically when you start a Claude Code session.

### Agent step fails

```
Error: Step [N] ([agent-name]) failed.
```

**Solution:** Check the partial outputs in `.claude/workflow-analysis/` for details. The analysis can be re-run after fixing any issues.

### Empty messages file

```
Note: The JSONL file contains 0 messages.
```

**Solution:** Either the file was just created, or try with a different date range:

```bash
python scripts/extract_user_messages.py --since 2026-01-01
```

## Dependencies

### Python script

- Python 3.10+
- No external dependencies (uses stdlib only)

### Bash script

- `jq` - JSON processor
  - macOS: `brew install jq`
  - Ubuntu/Debian: `sudo apt-get install jq`
  - RHEL/CentOS: `sudo yum install jq`

## Related Documentation

- Command definition: `.claude/commands/analyze-workflows.md`
- Pattern analyzer agent: `.claude/agents/workflow-pattern-analyzer.md`
- Sequence analyzer agent: `.claude/agents/workflow-sequence-analyzer.md`
- Automation proposer agent: `.claude/agents/workflow-automation-proposer.md`

---

*Last Updated: 2026-01-12*
