---
id: FEAT-1755
title: ll-workflows propose subcommand as CLI fallback for Step 3 automation proposals
type: FEAT
status: open
priority: P3
captured_at: '2026-05-27T21:20:05Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
relates_to: [BUG-1754]
---

# FEAT-1755: ll-workflows propose subcommand as CLI fallback for Step 3 automation proposals

## Summary

Add a `propose` subcommand to `ll-workflows` that runs the Step 3 automation proposal logic directly from the CLI. Currently Step 3 is only accessible via the `workflow-automation-proposer` skill invoked from `commands/analyze-workflows.md`. A CLI-native `propose` subcommand provides a robust fallback when the skill invocation is unavailable (e.g., BUG-1754: `disable-model-invocation` breakage) and makes the full 3-step pipeline scriptable end-to-end.

## Use Case

A developer wants to run the full workflow analysis pipeline non-interactively:

```bash
# Step 1: extract messages
ll-messages --output .ll/workflow-analysis/messages.jsonl

# Step 2: analyze patterns (exists today)
ll-workflows analyze --input .ll/workflow-analysis/messages.jsonl \
  --patterns .ll/workflow-analysis/step1-patterns.yaml \
  --output .ll/workflow-analysis/step2-workflows.yaml

# Step 3: propose automations (NEW — currently only works via skill)
ll-workflows propose \
  --patterns .ll/workflow-analysis/step1-patterns.yaml \
  --workflows .ll/workflow-analysis/step2-workflows.yaml \
  --output .ll/workflow-analysis/step3-proposals.yaml
```

Without the `propose` subcommand, Step 3 requires an interactive Claude Code session and the skill to be invocable — both preconditions that may fail (BUG-1754).

## Expected Behavior

`ll-workflows propose` reads the Step 1 patterns and Step 2 workflow YAML, calls the same proposal logic used by `workflow-automation-proposer`, and writes the proposals to an output file (default: `.ll/workflow-analysis/step3-proposals.yaml`). Supports `--format json` to match existing `analyze` flag parity.

## API/Interface

```
usage: ll-workflows propose [-h] -p PATTERNS -w WORKFLOWS [-o OUTPUT] [--format {yaml,json}]

positional arguments:
  propose               Run Step 3 automation proposals from workflow analysis output

options:
  -p, --patterns PATH   Step 1 patterns YAML (from ll-messages or workflow-pattern-analyzer)
  -w, --workflows PATH  Step 2 workflows YAML (from ll-workflows analyze)
  -o, --output PATH     Output path (default: .ll/workflow-analysis/step3-proposals.yaml)
  --format {yaml,json}  Output format (default: yaml)
```

## Implementation Notes

- Entry point: `scripts/little_loops/cli/workflows.py` — add `propose` as a sibling to `analyze` in the subparsers
- Core logic lives in (or should be extracted to) the same module that `workflow-automation-proposer` uses; avoid duplicating proposal logic — the skill should call through to the same Python function
- The `workflow-automation-proposer` skill's prompt instructions describe a 3-step agent pipeline; distill the deterministic parts (loop YAML generation, proposal formatting) into a Python function callable from both the skill and the CLI
- If the proposal step requires LLM output (e.g., generating natural language summaries), use `anthropic` SDK directly in the CLI handler — consistent with how `ll-action` shells out to Claude

## Related Issues

- BUG-1754: workflow-automation-proposer disable-model-invocation breaks workflow analysis pipeline (direct motivator)
- FEAT-028: workflow-automation-proposer skill (existing skill this CLI mirrors)
- FEAT-557: Add `--format json` to `ll-workflows` (done — parity reference for output flags)

## Session Log
- `/ll:capture-issue` - 2026-05-27T21:20:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d76f6684-f28b-48e1-8feb-af054e035afe.jsonl`

---

## Status

`open`
