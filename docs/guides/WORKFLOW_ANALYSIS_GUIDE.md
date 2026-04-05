# Workflow Analysis Guide

## Table of Contents

- [What Is Workflow Analysis?](#what-is-workflow-analysis)
- [The Pipeline at a Glance](#the-pipeline-at-a-glance)
- [Prerequisites: Extracting Messages (`ll-messages`)](#prerequisites-extracting-messages-ll-messages)
- [Running the Full Pipeline: `/ll:analyze-workflows`](#running-the-full-pipeline-llanalyze-workflows)
- [Understanding the Outputs](#understanding-the-outputs)
  - [Key fields in `step1-patterns.yaml`](#key-fields-in-step1-patternsyaml)
  - [Key fields in `step2-workflows.yaml`](#key-fields-in-step2-workflowsyaml)
  - [Key fields in `step3-proposals.yaml`](#key-fields-in-step3-proposalsyaml)
- [CLI Deep Dive: `ll-workflows`](#cli-deep-dive-ll-workflows)
  - [Argument Reference](#argument-reference)
  - [How the Analysis Works](#how-the-analysis-works)
- [The Automation Proposer: `/ll:workflow-automation-proposer`](#the-automation-proposer-llworkflow-automation-proposer)
  - [What It Looks For](#what-it-looks-for)
  - [The 9 Automation Types](#the-9-automation-types)
  - [Priority Scoring](#priority-scoring)
  - [Effort Estimation](#effort-estimation)
  - [The Implementation Roadmap](#the-implementation-roadmap)
- [Common Recipes](#common-recipes)
  - [Weekly automation review](#weekly-automation-review)
  - [Quick pattern check (Step 1 patterns only)](#quick-pattern-check-step-1-patterns-only)
  - [Fresh proposals from existing data](#fresh-proposals-from-existing-data)
  - [Extract only recent messages](#extract-only-recent-messages)
  - [Filter messages by type (`--skip-cli` / `--commands-only`)](#filter-messages-by-type---skip-cli----commands-only)
- [See Also](#see-also)

## What Is Workflow Analysis?

LLMs are stateless. Each session starts fresh with no memory of what you did last week, which multi-step processes you repeat most, or where you waste time on manual steps. The workflow analysis system closes that gap by mining your message history for patterns and turning them into concrete automation proposals.

What it discovers:

- **Repeated sequences** — the same 3-step process you run every Friday
- **Multi-session workflows** — tasks that span multiple Claude sessions and need continuity
- **Friction points** — debug → fix → test cycles where you're retrying the same thing
- **Automation candidates** — workflows that already have, or could have, a `/ll:*` command

What you get at the end: a prioritized list of hooks, commands, scripts, and FSM loops — each with rationale, effort estimate, and implementation sketch.

## The Pipeline at a Glance

```
ll-messages       →   Step 1 (Agent)        →   Step 2 (CLI)           →   Step 3 (Skill)              →   summary.md
─────────────────     ────────────────────      ─────────────────────      ──────────────────────────      ───────────
Extract user          workflow-pattern-         ll-workflows analyze       workflow-automation-            Human-readable
messages from         analyzer categorizes      links sessions,            proposer synthesizes            report with top
Claude logs into      messages, detects         clusters entities,         patterns into proposals         patterns, detected
.jsonl file           patterns, inventories     detects workflows           with priority + effort          workflows, and
                      tools                                                 estimates                       proposals
        │                 │                          │                          │                               │
        ▼                 ▼                          ▼                          ▼                               ▼
msgs-*.jsonl      step1-patterns.yaml       step2-workflows.yaml      step3-proposals.yaml            summary-*.md
```

Each step's output is the next step's input. Partial results are always preserved — if Step 2 fails, Step 1's output remains in `.ll/workflow-analysis/`.

## Prerequisites: Extracting Messages (`ll-messages`)

Before running the analysis pipeline, you need a JSONL file of your user messages. `ll-messages` extracts these from your Claude Code session logs.

```bash
# Last 100 messages (default)
ll-messages

# Last 200 messages
ll-messages -n 200

# Messages since a specific date
ll-messages --since 2026-01-01

# Write to a custom file
ll-messages -o my-messages.jsonl

# Print to terminal instead of a file (for quick inspection)
ll-messages --stdout

# Include metadata: tools used, files modified
ll-messages --include-response-context
```

The output is a JSONL file (one JSON object per line) at `.ll/user-messages-{timestamp}.jsonl`. Each line has at minimum a `content` field with the message text and a `timestamp` field.

Key flags reference:

| Flag | Short | Description |
|------|-------|-------------|
| `--limit N` | `-n N` | Max messages to extract (default: 100) |
| `--since DATE` | `-S` | Only messages after this date (YYYY-MM-DD or ISO) |
| `--output FILE` | `-o FILE` | Output file path |
| `--stdout` | | Print to terminal instead of file |
| `--verbose` | `-v` | Show progress information |
| `--include-response-context` | | Include tools used and files modified per message |
| `--skip-cli` | | Exclude CLI commands from output |
| `--commands-only` | | Extract only CLI commands, no prose messages |

## Running the Full Pipeline: `/ll:analyze-workflows`

The simplest way to run all three steps is the single orchestrating command:

```bash
# Auto-detect most recent messages file in .claude/
/ll:analyze-workflows

# Use a specific file
/ll:analyze-workflows .ll/user-messages-20260112-111551.jsonl
```

The command creates a todo list, runs each step in sequence, and displays a formatted summary when done.

**What happens at each step:**

1. **Input detection** — finds (or validates) the messages JSONL file
2. **Output directory** — creates `.ll/workflow-analysis/` if it doesn't exist
3. **Step 1** — spawns the `workflow-pattern-analyzer` agent to write `step1-patterns.yaml`
4. **Step 2** — runs `ll-workflows analyze` CLI to write `step2-workflows.yaml`
5. **Step 3** — invokes the `workflow-automation-proposer` skill to write `step3-proposals.yaml`
6. **Summary** — generates `summary-{timestamp}.md` from all three outputs

If no messages file is found, the command tells you to run `ll-messages` first.

## Understanding the Outputs

All outputs are written to `.ll/workflow-analysis/`:

| File | Produced by | Contents |
|------|-------------|----------|
| `step1-patterns.yaml` | workflow-pattern-analyzer agent | Category distribution, repeated phrases, tool references, entity inventory |
| `step2-workflows.yaml` | `ll-workflows analyze` CLI | Session links, entity clusters, workflow boundaries, detected workflows |
| `step3-proposals.yaml` | workflow-automation-proposer skill | Automation proposals with priority, effort, and implementation sketches |
| `summary-{timestamp}.md` | `/ll:analyze-workflows` command | Human-readable report (tables of top patterns, workflows, proposals) |

### Key fields in `step1-patterns.yaml`

- `category_distribution` — how messages break down by type (e.g., "code review", "debugging", "issue management")
- `repeated_patterns` — 2-4 word phrases with frequency ≥ 3, sorted by count
- `tool_references` — slash commands and tools mentioned in messages
- `entity_inventory` — files, commands, and concepts referenced across messages

Here's what a typical pattern entry looks like:

```yaml
# Example entry from step1-patterns.yaml
- pattern: run_tests_after_edit
  category: code_quality
  frequency: 7
  examples:
    - "run the tests after making this change"
    - "check if tests still pass"
  confidence: 0.85
```

### Key fields in `step2-workflows.yaml`

- `session_links` — cross-session continuations (same entity worked on across multiple sessions)
- `entity_clusters` — groups of messages that operate on the same files or topics
- `workflow_boundaries` — detected transitions between distinct workflows
- `workflows` — named multi-step workflow patterns, each with a `pattern_confidence` score (0.0–1.0) and session count

**`pattern_confidence`** reflects how consistent the sequence is across observed instances. A score above 0.7 is strong; below 0.4 means the pattern is loosely structured and harder to automate reliably.

**`cohesion_score`** appears on entity clusters. It measures how tightly the messages in a cluster relate to each other (0.0–1.0). High cohesion (≥ 0.7) means messages are clearly about one thing; low cohesion means the cluster is loosely connected.

### Key fields in `step3-proposals.yaml`

- `proposals` — the main list; each entry has `id`, `type` (see [The 9 Automation Types](#the-9-automation-types)), `priority`, `effort`, `rationale`, and `implementation_sketch`
- `existing_command_suggestions` — patterns that already have a `/ll:*` command you may not be using
- `implementation_roadmap` — proposals grouped into `immediate`, `short_term`, and `future` buckets

## CLI Deep Dive: `ll-workflows`

You can run Step 2 independently — useful if you've run Step 1 manually or want to re-analyze with updated patterns.

```bash
# Shortest form — assumes step1-patterns.yaml already exists from a prior Step 1 agent run;
# sets the --input path to the default so ll-workflows can find it automatically
ll-messages --output .ll/workflow-analysis/user-messages.jsonl
ll-workflows analyze --patterns .ll/workflow-analysis/step1-patterns.yaml

# Explicit input
ll-workflows analyze \
  --input .ll/user-messages-20260112.jsonl \
  --patterns .ll/workflow-analysis/step1-patterns.yaml \
  --output .ll/workflow-analysis/step2-workflows.yaml
```

### Argument Reference

| Flag | Short | Required | Description |
|------|-------|----------|-------------|
| `--input FILE` | `-i FILE` | No | Input JSONL file with user messages (default: `.ll/workflow-analysis/step1-patterns.jsonl`) |
| `--patterns FILE` | `-p FILE` | Yes | Step 1 output YAML (from workflow-pattern-analyzer) |
| `--output FILE` | `-o FILE` | No | Output YAML (default: `.ll/workflow-analysis/step2-workflows.yaml`) |
| `--verbose` | `-v` | No | Print detailed progress |
| `--format` | `-f` | No | Output format: `yaml` or `json` (default: `yaml`) |
| `--overlap-threshold` | | No | Minimum entity overlap to cluster messages (default: `0.3`) |
| `--boundary-threshold` | | No | Minimum boundary score to split workflow segments (default: `0.6`) |

### How the Analysis Works

The CLI performs four analyses on your messages:

1. **Session linking** — identifies when a message in one session continues work from a prior session (by matching entity names, file paths, or explicit references). Links are scored by entity overlap.

2. **Entity clustering** — groups messages that reference the same files, commands, or named concepts. A cluster becomes a workflow candidate if it has ≥ 3 messages and a cohesion score above the threshold.

3. **Boundary detection** — finds transitions between distinct workflows by looking for topic shifts, time gaps between sessions, and changes in entity sets. These boundaries separate one workflow from the next.

4. **Template matching** — compares detected workflows against known patterns (e.g., "issue management cycle", "code review and fix", "test-fix-lint loop", "PR preparation") and scores each match. High-confidence matches get labeled with the template name.

## The Automation Proposer: `/ll:workflow-automation-proposer`

This skill reads Step 1 and Step 2 outputs and writes `step3-proposals.yaml`. Run it standalone when you already have the YAML files and want fresh proposals — for example, after manually editing `step2-workflows.yaml` or when you want to re-run proposals with a different focus.

```bash
# Auto-detect inputs in .ll/workflow-analysis/
/ll:workflow-automation-proposer

# Explicit paths
/ll:workflow-automation-proposer .ll/workflow-analysis/step1-patterns.yaml .ll/workflow-analysis/step2-workflows.yaml
```

### What It Looks For

The skill targets high-value automation candidates:

- **Frequency ≥ 5** — patterns repeated enough to be worth automating
- **Multi-session workflows** — complex processes that span multiple Claude sessions
- **Friction and retry cycles** — debug → fix → test loops that show repeated manual effort
- **Multi-step workflows with ≥ 3 occurrences** — candidates for slash commands

It also checks for existing `/ll:*` commands before proposing new ones. If your pattern already has a solution, it appears in `existing_command_suggestions` rather than as a new proposal.

### The 9 Automation Types

| Type | Use Case | Example |
|------|----------|---------|
| `slash_command` | Multi-step workflow with 3+ occurrences | `/ll:cleanup-refs` for repeated reference removal |
| `script_python` | Complex logic, data processing, external APIs | Entity extraction script with argparse |
| `script_bash` | Simple file operations, tool chains | Batch rename script |
| `hook_pre_tool` | Prevent unwanted tool usage | Block `rm -rf` patterns before they run |
| `hook_post_tool` | React to tool completions | Auto-lint after every Edit |
| `hook_stop` | Session-end automation | Commit reminder when session ends |
| `agent_enhancement` | Extend an existing agent's capabilities | Add entity extraction to the pattern analyzer |
| `fsm_loop` | Repeated multi-step CLI workflows | `ll-loop` config for a test → fix → lint cycle |
| `existing_command` | User should adopt an existing command | Suggest `/ll:commit` for repeated commit requests |

### Priority Scoring

```
Priority = (frequency × 0.4) + (workflow_count × 0.3) + (friction_score × 0.3)

HIGH:   score ≥ 8   →  5+ occurrences, major friction
MEDIUM: score ≥ 4   →  3-4 occurrences, moderate friction
LOW:    score < 4   →  1-2 occurrences, minor friction
```

> **Note:** Frequency ≥ 5 is the threshold for *high-priority* automation. Lower-frequency
> patterns can still appear in the output — they'll be scored as LOW or MEDIUM priority.

Variable definitions:

| Variable | Range | Meaning |
|----------|-------|---------|
| `frequency` | 1–20+ (raw count) | Number of times the pattern appears in the message history |
| `workflow_count` | 1–10 (raw count) | Number of distinct detected workflows that include this pattern |
| `friction_score` | 0–10 (computed) | Friction intensity: debug/fix/test cycles, retry keywords, error context, multi-session spans |

Friction indicators: debug/fix/test cycles, multiple session spans, retry keywords in messages, error keywords in context.

> **Note on LOW priority proposals**: LOW priority items (score < 4) are generated for patterns with 1–2 occurrences that still show friction or workflow involvement. The "Frequency ≥ 5" target in [What It Looks For](#what-it-looks-for) is the threshold for emphasis during analysis — patterns below it may still appear as LOW priority proposals when friction or workflow signals are present.

### Effort Estimation

| Level | Criteria | Example |
|-------|----------|---------|
| `SMALL` | Single file, < 100 lines, no new dependencies | Simple slash command |
| `MEDIUM` | 2-3 files, 100-300 lines, uses existing patterns | Agent + command combo |
| `LARGE` | Multiple files, > 300 lines, new patterns or dependencies | Full pipeline feature |
| `NONE` | Existing command already handles this | Suggest an existing solution |

### The Implementation Roadmap

Proposals are organized into three buckets:

- **Immediate** — `NONE` effort (existing commands) + `SMALL` effort with `HIGH` priority
- **Short-term** — `MEDIUM` effort with `HIGH` or `MEDIUM` priority
- **Future** — `LARGE` effort or `LOW` priority items

Start with `immediate` — these are the highest-return actions that require the least work.

## Common Recipes

### Weekly automation review

Full pipeline from extract to proposals:

```bash
ll-messages -n 200                    # Extract recent messages
/ll:analyze-workflows                 # Run full pipeline (auto-detects file)
# Review: .ll/workflow-analysis/summary-*.md
```

### Quick pattern check (Step 1 patterns only)

Run only Step 1 to get a fast category breakdown without the full pipeline. In Claude Code, run `/ll:analyze-workflows` to execute the full pipeline, or ask Claude to 'use the workflow-pattern-analyzer agent' to run Step 1 on its own.

```bash
ll-messages                           # Extract messages to .ll/user-messages-{ts}.jsonl
# Then in Claude: spawn workflow-pattern-analyzer with the JSONL file path
# Review: .ll/workflow-analysis/step1-patterns.yaml
```

> **Note**: `/ll:analyze-workflows` always runs all three steps — there is no built-in mid-pipeline stop. To limit analysis to Step 1, invoke the `workflow-pattern-analyzer` agent directly or read `step1-patterns.yaml` before the remaining steps complete.

### Fresh proposals from existing data

Re-run only Step 3 when you already have `step1-patterns.yaml` and `step2-workflows.yaml`:

```bash
/ll:workflow-automation-proposer
# Reads existing files, writes new step3-proposals.yaml
```

Useful after manually editing `step2-workflows.yaml` to correct a detected workflow, or when you want to experiment with re-running proposals.

### Extract only recent messages

Use `--since` to analyze just the last sprint or time window:

```bash
ll-messages --since 2026-02-01 -n 500   # Since Feb 1, up to 500 messages
/ll:analyze-workflows                    # Run pipeline on auto-detected file
```

Combine with `-n` to limit volume while keeping the date filter as the primary boundary.

### Filter messages by type (`--skip-cli` / `--commands-only`)

Use these flags to narrow the message set before running the pipeline:

```bash
# Exclude CLI commands — analyze only prose messages (questions, descriptions, requests)
ll-messages --skip-cli
/ll:analyze-workflows

# Extract only CLI commands — useful for identifying repeated shell workflows
ll-messages --commands-only
/ll:analyze-workflows
```

`--skip-cli` is useful when your history is dominated by CLI invocations and you want to focus on conversational patterns. `--commands-only` is useful when you want to discover command-line workflow automation opportunities specifically.

## See Also

- [Loops Guide](LOOPS_GUIDE.md) — implement FSM loop proposals generated by the automation proposer
- [Automate Workflows with Hooks](../claude-code/automate-workflows-with-hooks.md) — implement hook proposals (`hook_pre_tool`, `hook_post_tool`, `hook_stop`)
- [Command Reference](../reference/COMMANDS.md) — full reference for all `/ll:*` commands
