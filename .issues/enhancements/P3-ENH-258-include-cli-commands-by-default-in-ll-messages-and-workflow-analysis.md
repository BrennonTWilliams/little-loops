---
discovered_date: 2026-02-06
discovered_by: capture_issue
---

# ENH-258: Include CLI commands by default in ll-messages and workflow analysis

## Summary

Change `ll-messages` to include CLI commands in output by default (currently opt-in via `--include-commands`), with a new `--skip-cli` flag to exclude them. Also update `/ll:analyze-workflows` and its pipeline to incorporate CLI command data into workflow pattern detection and `ll-loop` configuration suggestions.

## Context

**Direct mode**: User description: "Enhance our `ll-messages` CLI command to also include CLI commands executed (with timestamps & other available metadata that overlaps with the messages from the claude jsonl files), in addition to the user-sent claude code messages. Include these CLI commands in the output of `ll-messages` unless overridden by a `--skip-cli` flag. The `/ll:analyze-workflows` slash command/skill should also be updated to include CLI commands in its workflow analysis, and in the suggested workflows for `ll-loop`."

FEAT-221 previously added `--include-commands` as an opt-in flag. This enhancement flips the default so CLI commands are always included, making the combined output the standard behavior. It also extends the workflow analysis pipeline to leverage CLI command data for richer pattern detection and more accurate loop suggestions.

## Current Behavior

- `ll-messages` outputs only user messages by default
- CLI commands require explicit `--include-commands` flag
- `/ll:analyze-workflows` pipeline (pattern analyzer, sequence analyzer, automation proposer) operates only on user messages
- `ll-loop` suggestions from the pipeline don't incorporate actual CLI commands executed

## Expected Behavior

### ll-messages changes

```bash
# Default: includes both user messages AND CLI commands
$ ll-messages

# Opt-out of CLI commands
$ ll-messages --skip-cli

# Existing flags still work
$ ll-messages --commands-only
$ ll-messages --tools Bash,Read
```

The `--include-commands` flag should be removed entirely. The new `--skip-cli` flag excludes CLI commands from output.

### /ll:analyze-workflows changes

The workflow analysis pipeline should:
1. **Step 1 (Pattern Analyzer agent)**: Analyze both user messages and CLI commands to identify richer patterns (e.g., "user asks to run tests" → "pytest executed" → "user asks to fix errors")
2. **Step 2 (Sequence Analyzer - ll-workflows)**: Detect workflows that include CLI command sequences, not just user prompts
3. **Step 3 (Automation Proposer skill)**: Generate `ll-loop` configurations that incorporate the actual CLI commands discovered in the analysis

### ll-loop suggestions

Loop suggestions should include specific CLI commands as step actions, e.g.:
```yaml
steps:
  - name: run_tests
    action: "python -m pytest scripts/tests/ -v"
    on_success: check_lint
    on_failure: fix_errors
```

## Proposed Solution

### 1. ll-messages CLI changes (`scripts/little_loops/cli.py`)

- Remove `--include-commands` flag entirely (commands included by default now)
- Add `--skip-cli` flag that excludes CLI commands from output
- Update help text to reflect new defaults

### 2. user_messages.py changes (`scripts/little_loops/user_messages.py`)

- Update the main extraction entry point to include commands by default
- Add parameter to opt out of commands (for `--skip-cli` support)

### 3. Workflow analysis pipeline updates

- **`commands/analyze-workflows.md`**: Pass combined user+command data to all pipeline steps
- **`agents/workflow-pattern-analyzer.md`**: Update agent instructions to analyze CLI command patterns alongside user messages
- **`skills/workflow-automation-proposer/SKILL.md`**: Update skill to generate loop configs with CLI command steps
- **`scripts/little_loops/workflow_sequence_analyzer.py`**: Update sequence detection to recognize command-inclusive workflows

### 4. Tests

- Update existing `ll-messages` tests for new default behavior
- Add tests for `--skip-cli` flag
- Remove existing tests for `--include-commands` flag
- Update workflow analysis tests to verify CLI command inclusion

## Impact

- **Priority**: P3
- **Effort**: Medium - Multiple components need updating (CLI, pipeline, agents, skills)
- **Risk**: Low - Breaking change to `--include-commands` flag, but it was recently added and unlikely to have external consumers

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Pipeline architecture and CLI tools |
| guidelines | CONTRIBUTING.md | Testing and code style requirements |

## Related Issues

- **FEAT-221** (completed): Originally added `--include-commands` opt-in flag
- **FEAT-029** (completed): Created `/ll:analyze-workflows` command
- **FEAT-027** (completed): Workflow sequence analyzer module
- **FEAT-028** (completed): Workflow automation proposer skill

## Labels

`enhancement`, `cli-tool`, `ll-messages`, `workflow-analysis`, `ll-loop`, `captured`

---

## Status

**Open** | Created: 2026-02-06 | Priority: P3
