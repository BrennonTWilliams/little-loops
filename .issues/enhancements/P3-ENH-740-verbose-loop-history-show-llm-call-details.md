---
id: ENH-740
priority: P3
type: ENH
status: active
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 93
outcome_confidence: 86
---

# ENH-740: Verbose loop history should show full LLM call details

## Summary

`ll-loop history issue-refinement --verbose` provides insufficient detail. It should expose each LLM call's input prompt and output response so users can understand and debug the loop's decision-making.

## Motivation

When debugging a loop run or understanding why a state transitioned in a particular way, users need to see the full context of each LLM call — what was sent in and what came back. Currently `--verbose` output is too high-level to be actionable for diagnosis.

## Current Behavior

`--verbose` shows a summary-level view of loop history without exposing the details of individual LLM calls made during execution.

## Expected Behavior

`ll-loop history <loop-name> --verbose` should display for each LLM call:
- The full input prompt sent to the model (or a clearly truncated version with a `--full` flag to show everything)
- The raw model output / response text
- Metadata: model used, token counts, latency, state name, transition result
- Possibly: tool calls made and their results if the LLM used tools

The output should be structured and readable (e.g., collapsible sections in rich output, or clearly delimited blocks in plain text).

## Scope Boundaries

- **In scope**: Enhanced `--verbose` output for `ll-loop history` showing LLM call inputs/outputs, token counts, latency, and metadata; optional `--full` flag for untruncated prompt display
- **Out of scope**: Changes to core loop execution or FSM state machine logic; changes to other `ll-loop` subcommands; real-time streaming of LLM calls during execution; changes to log retention or rotation policy; changes to non-loop CLI tools (`ll-auto`, `ll-parallel`, etc.)

## Implementation Steps

1. Locate where loop history is stored — identify the JSONL/log format used by `ll-loop`
2. Determine what LLM call data is currently persisted (prompts, responses, metadata)
3. If LLM call inputs/outputs are not stored, add persistence to the loop execution path
4. Update the `history` subcommand's `--verbose` rendering to include LLM call blocks
5. Consider a `--full` flag for untruncated output vs `--verbose` for summarized-but-detailed output
6. Add tests for the new verbose rendering path

## API/Interface

```bash
# Current
ll-loop history issue-refinement --verbose

# Enhanced output per state transition:
# [STATE: analyze] → success
#   LLM Call #1
#     Input:  "You are reviewing issue ENH-123..."
#     Output: "The issue is ready for implementation."
#     Model:  claude-sonnet-4-6 | Tokens: 512 in / 48 out | Latency: 1.2s
```

## Related Key Documentation

- `docs/ARCHITECTURE.md` — loop execution architecture
- `scripts/little_loops/` — Python package with loop implementation

## Impact

- **Priority**: P3 - Debugging/diagnostic tooling improvement; valuable for loop authors and maintainers but not blocking core workflows
- **Effort**: Medium - Requires investigating existing JSONL log format, potentially adding LLM call persistence to the loop execution path, and updating `--verbose` rendering logic
- **Risk**: Low - Purely additive change to `--verbose` output; no impact on core loop execution or state transitions
- **Breaking Change**: No

## Labels

`enhancement`, `loop-history`, `verbose`, `debugging`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c96e34f-66f6-47a9-8e06-75aea65c7264.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3777c8ff-1714-43df-b4e3-5fada0728038.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3777c8ff-1714-43df-b4e3-5fada0728038.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d69664f2-c580-4a55-b04c-9cddea5b7fc0.jsonl`

---

## Status

Active — not yet started.
