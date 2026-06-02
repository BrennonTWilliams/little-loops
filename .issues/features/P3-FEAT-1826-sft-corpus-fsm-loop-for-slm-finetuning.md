---
id: FEAT-1826
title: "sft-corpus FSM loop for SLM fine-tuning from session logs"
type: FEAT
priority: P3
status: open
captured_at: "2026-05-31T22:00:59Z"
discovered_date: "2026-05-31"
discovered_by: capture-issue
parent: EPIC-1880
---

# FEAT-1826: sft-corpus FSM loop for SLM fine-tuning from session logs

## Summary

New FSM loop that extracts multi-turn conversations from Claude Code `.jsonl` session logs, converts them into SFT training format (ChatML / Alpaca / ShareGPT), applies quality filtering and deduplication, and produces a train/val/test split ready for fine-tuning a small language model.

## Current Behavior

No dedicated pipeline exists for extracting SFT training data from Claude Code session logs. Practitioners must manually extract `.jsonl` logs, write custom conversion scripts for each target format (ChatML/Alpaca/ShareGPT), implement quality filtering and deduplication, and handle train/val/test splits — a multi-step process with no ll-native tooling.

## Expected Behavior

A runnable `sft-corpus` FSM loop handles the full pipeline from raw `.jsonl` session logs to a publishable SFT corpus, respecting all configured context keys (`sft_format`, `output_dir`, `max_turns`, `min_tokens`, `max_tokens`, `pii_action`, `val_ratio`, `test_ratio`). The back-half (filter → dedup → split → publish) delegates to `dataset-curation` via a `loop:` handoff.

## Motivation

Neither `examples-miner` nor `dataset-curation` fits the SLM fine-tuning use case:
- `examples-miner` outputs prompt-optimization corpora (skill invocations, `tools_used`/`files_modified` JSON) and wraps `apo-textgrad` — wrong target and format
- `dataset-curation` is a generic back-half pipeline (quality gate → distribute → publish) but has no JSONL log ingestion or SFT format conversion
- A new loop is needed that owns the full pipeline from raw session logs through a publishable SFT corpus

## Use Case

A practitioner wants to fine-tune an SLM on Claude Code session data. They have `.jsonl` logs under `~/.claude/projects/` and want a curated, formatted dataset they can pass directly to a fine-tuning trainer (e.g., Axolotl, LLaMA-Factory, torchtune).

## Acceptance Criteria

- [ ] `ll-loop run sft-corpus` ingests `.jsonl` files from `log_dir` and produces at least one output example
- [ ] Output is valid for the configured `sft_format` (`chatml`, `alpaca`, or `sharegpt`)
- [ ] Examples outside `[min_tokens, max_tokens]` token range are discarded by the `filter` state
- [ ] Near-duplicate conversations (same fingerprint) produce only one output example after `dedup`
- [ ] `split` state writes separate `train`/`val`/`test` files at configured ratios
- [ ] Back-half delegates to `dataset-curation` loop via `loop:` handoff (no reimplementation of quality/distribute/validate/publish)
- [ ] Harvest sentinel is updated after each successful `publish` run, enabling incremental re-runs

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

## Integration Map

### Files to Modify
- N/A — no existing files modified

### New Files
- `scripts/little_loops/loops/sft-corpus.yaml` — primary deliverable (new FSM loop)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/dataset-curation.yaml` — invoked as back-half via `loop:` handoff

### Similar Patterns
- `scripts/little_loops/loops/examples-miner.yaml` — reference for log ingestion and harvest-sentinel patterns

### Tests
- TBD — add integration test in `scripts/tests/` verifying loop produces valid output files

### Documentation
- TBD — consider a loop guide entry in `docs/guides/`

### Configuration
- `.ll/ll-config.json` — optional `sft_corpus` section for context key overrides

## Impact

- **Priority**: P3 — Useful for SLM practitioners; not blocking core ll workflows
- **Effort**: Large — New 6-phase FSM loop with format conversion, PII handling, and `dataset-curation` handoff
- **Risk**: Low — New YAML artifact only; no changes to existing scripts, loops, or APIs
- **Breaking Change**: No

## Related

- `scripts/little_loops/loops/examples-miner.yaml` — prompt-optimization corpus mining (different target)
- `scripts/little_loops/loops/dataset-curation.yaml` — candidate back-half via `loop:` handoff
- ENH-1827 — add `--sft-format` to `ll-messages` CLI (alternate ingest path)

## Labels

`loop`, `sft`, `fine-tuning`, `new-feature`

## Session Log
- `/ll:format-issue` - 2026-06-02T23:15:08 - `0d29889f-5db4-42d2-b354-e9615aee84a2.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:43 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:capture-issue` - 2026-05-31T22:00:59Z - `109abe71-e47d-4222-b37d-c17fd7d98dee.jsonl`

---
## Status

`open`
