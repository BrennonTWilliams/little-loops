---
id: FEAT-1826
title: "sft-corpus FSM loop for SLM fine-tuning from session logs"
type: FEAT
priority: P3
status: open
captured_at: "2026-05-31T22:00:59Z"
discovered_date: "2026-05-31"
discovered_by: capture-issue
parent: EPIC-1694
---

# FEAT-1826: sft-corpus FSM loop for SLM fine-tuning from session logs

## Summary

New FSM loop that extracts multi-turn conversations from Claude Code `.jsonl` session logs, converts them into SFT training format (ChatML / Alpaca / ShareGPT), applies quality filtering and deduplication, and produces a train/val/test split ready for fine-tuning a small language model.

## Motivation

Neither `examples-miner` nor `dataset-curation` fits the SLM fine-tuning use case:
- `examples-miner` outputs prompt-optimization corpora (skill invocations, `tools_used`/`files_modified` JSON) and wraps `apo-textgrad` — wrong target and format
- `dataset-curation` is a generic back-half pipeline (quality gate → distribute → publish) but has no JSONL log ingestion or SFT format conversion
- A new loop is needed that owns the full pipeline from raw session logs through a publishable SFT corpus

## Use Case

A practitioner wants to fine-tune an SLM on Claude Code session data. They have `.jsonl` logs under `~/.claude/projects/` and want a curated, formatted dataset they can pass directly to a fine-tuning trainer (e.g., Axolotl, LLaMA-Factory, torchtune).

## Implementation Steps

1. **ingest** — walk `~/.claude/projects/` (or a configured `log_dir`), enumerate `.jsonl` files newer than a harvest sentinel, extract multi-turn conversation windows (not just skill invocations)
2. **convert** — transform each conversation window into the target SFT format via `context.sft_format` (`chatml` / `alpaca` / `sharegpt`); emit one JSON object per example
3. **filter** — quality-gate: token length budget check, turn coherence, task completion signal, PII heuristic (flag/redact)
4. **dedup** — near-duplicate removal by conversation fingerprint (hash of normalized turn sequence)
5. **split** — stratified train/val/test split by source session, write separate output files
6. **publish** — write final corpus files + manifest; update harvest sentinel

### Child loop handoff
Pipe the curated back-half (filter → dedup → split) through `dataset-curation` via a `loop:` handoff, reusing its quality/distribution/validate/publish states rather than reimplementing them.

## API / Interface

Context keys (`.ll/ll-config.json` or loop `context:` block):

```yaml
context:
  log_dir: "~/.claude/projects"
  sft_format: "chatml"          # chatml | alpaca | sharegpt
  output_dir: "data/sft"
  max_turns: 20                 # max turns per conversation window
  min_tokens: 50                # discard very short exchanges
  max_tokens: 4096              # discard context-overflow examples
  pii_action: "flag"            # flag | redact | discard
  val_ratio: 0.1
  test_ratio: 0.1
```

## Related

- `scripts/little_loops/loops/examples-miner.yaml` — prompt-optimization corpus mining (different target)
- `scripts/little_loops/loops/dataset-curation.yaml` — candidate back-half via `loop:` handoff
- ENH-1827 — add `--sft-format` to `ll-messages` CLI (alternate ingest path)

## Session Log
- `/ll:capture-issue` - 2026-05-31T22:00:59Z - `109abe71-e47d-4222-b37d-c17fd7d98dee.jsonl`

---
## Status

`open`
