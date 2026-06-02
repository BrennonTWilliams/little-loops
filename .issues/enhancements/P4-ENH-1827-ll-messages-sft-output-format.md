---
id: ENH-1827
title: "Add --sft-format flag to ll-messages CLI"
type: ENH
priority: P4
status: open
captured_at: "2026-05-31T22:00:59Z"
discovered_date: "2026-05-31"
discovered_by: capture-issue
parent: EPIC-1694
---

# ENH-1827: Add --sft-format flag to ll-messages CLI

## Summary

Extend `ll-messages` with an `--sft-format` flag that emits conversation turns in standard SFT training formats (ChatML, Alpaca, ShareGPT) rather than the current `--examples-format` prompt-optimization output.

## Motivation

`ll-messages` currently supports `--examples-format`, which outputs `(input, expected)` pairs scoped to a specific skill's invocation pattern — useful for apo-textgrad but not for SLM fine-tuning. An `--sft-format` flag would let the `sft-corpus` loop (FEAT-1826) use `ll-messages` as its ingest stage, or allow one-off corpus extraction without running the full loop.

## Implementation Steps

1. Add `--sft-format` argument to `ll-messages` CLI: `--sft-format {chatml,alpaca,sharegpt}`
2. Implement a `SFTFormatter` class (or module-level functions) in `scripts/little_loops/` that takes a sequence of `(role, content)` turns and emits the target format:
   - **chatml**: `{"messages": [{"role": "...", "content": "..."}]}`
   - **alpaca**: `{"instruction": "...", "input": "", "output": "..."}`
   - **sharegpt**: `{"conversations": [{"from": "human"|"gpt", "value": "..."}]}`
3. Wire into the existing `ll-messages extract` output path; `--sft-format` and `--examples-format` are mutually exclusive
4. Respect `--context-window N` for windowing; emit one JSON-lines object per window

## API / Interface

```bash
# Emit all conversations in ChatML format
ll-messages --sft-format chatml --stdout

# Emit windowed (3-turn) conversations in ShareGPT format since last harvest
ll-messages --sft-format sharegpt --context-window 3 --since 2026-05-01 --stdout

# Write to file
ll-messages --sft-format alpaca --output data/sft/raw.jsonl
```

## Related

- FEAT-1826 — `sft-corpus` loop (primary consumer of this flag)
- `scripts/little_loops/` — `ll-messages` implementation lives here

## Session Log
- `/ll:capture-issue` - 2026-05-31T22:00:59Z - `109abe71-e47d-4222-b37d-c17fd7d98dee.jsonl`

---
## Status

`open`
