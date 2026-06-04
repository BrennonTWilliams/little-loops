---
id: EPIC-1880
title: SLM Fine-Tuning from Session Logs
type: EPIC
priority: P3
status: open
captured_at: '2026-06-02T00:00:00Z'
discovered_date: '2026-06-02'
discovered_by: review-epic
relates_to: [FEAT-1826, ENH-1827, ENH-1885, ENH-1886, ENH-1941, ENH-1942]
labels:
  - epic
  - sft
  - fine-tuning
  - session-logs
  - slm
---

# EPIC-1880: SLM Fine-Tuning from Session Logs

## Summary

Build the tooling needed to turn Claude Code session logs (`.jsonl` files under `~/.claude/projects/`) into curated SFT corpora ready for small-language-model fine-tuning. Two deliverables form the surface:

| Child | Role |
|---|---|
| `sft-corpus` (FEAT-1826) | FSM loop: ingest → convert → filter → dedup → split → publish |
| `ll-messages --sft-format` (ENH-1827) | CLI flag for one-off extraction without running the full loop |

## Motivation

`examples-miner` outputs prompt-optimization corpora (skill invocations, `tools_used`/`files_modified` JSON) and wraps `apo-textgrad` — wrong target and format for SLM fine-tuning. `dataset-curation` is a generic back-half pipeline with no JSONL log ingestion or SFT format conversion. A dedicated pipeline is needed that owns the full path from raw session logs through a publishable SFT corpus in standard formats (ChatML, Alpaca, ShareGPT).

## Children

- **FEAT-1826** — `sft-corpus` FSM loop: full pipeline from raw `.jsonl` session logs to train/val/test split
- **ENH-1827** — `ll-messages --sft-format` flag: one-off ingest path and alternate input for the loop
- **ENH-1885** — PII detection utility (`little_loops.pii`) to back `pii_action` filter in the loop
- **ENH-1886** — File-level mtime pre-filter in `extract_conversation_turns()` for faster incremental harvest
- **ENH-1941** — Integrate history.db session-quality signals into sft-corpus filtering

## Scope

### In Scope

- `scripts/little_loops/loops/sft-corpus.yaml` FSM loop with `loop:` handoff to `dataset-curation` for the back-half
- `--sft-format {chatml,alpaca,sharegpt}` flag on the existing `ll-messages` CLI
- `SFTFormatter` class in `scripts/little_loops/` shared between the loop and the CLI

### Out of Scope

- `dataset-curation` changes — reused as-is via `loop:` handoff
- Publishing to HuggingFace Hub or other registries — handled by `dataset-curation`'s publish state
- Training orchestration (Axolotl, LLaMA-Factory, torchtune) — out of scope; this epic produces the corpus only

## Acceptance Criteria

- `ll-loop run sft-corpus` completes end-to-end against a real `~/.claude/projects/` directory, producing a `data/sft/` directory with `train.jsonl`, `val.jsonl`, `test.jsonl`, and a manifest.
- `ll-messages --sft-format chatml --stdout` emits valid JSON-lines in ChatML format.
- `ll-loop validate sft-corpus` reports no ERRORs.

## Implementation Order

1. **ENH-1827** first — `ll-messages --sft-format` is the ingest building block; once it exists, the loop's ingest state can delegate to it.
2. **FEAT-1826** — `sft-corpus` loop consumes the flag and wires the full pipeline.

## Related

- `scripts/little_loops/loops/examples-miner.yaml` — prompt-optimization corpus mining (different purpose)
- `scripts/little_loops/loops/dataset-curation.yaml` — back-half reused via `loop:` handoff
- [[EPIC-1918]] — sibling epic consuming the same `ll-logs` data layer for
  telemetry. ENH-1919 (n-gram extraction) may enrich SFT corpora; FEAT-1920
  (eval-export) could validate corpus quality. ENH-1885 (PII) is a shared
  dependency both epics benefit from.

---

**Open** | Created: 2026-06-02 | Priority: P3

## Verification Notes

**Verdict: NEEDS_UPDATE** — 3 of 4 children are done: ENH-1827 (ll-messages --sft-format), ENH-1885 (pii.py), ENH-1886 (mtime prefilter). Only FEAT-1826 (sft-corpus FSM loop) remains open. Epic is ~75% complete.

## Session Log
- `/ll:verify-issues` - 2026-06-04T04:22:07 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:review-epic` - 2026-06-02T00:00:00 - EPIC-1694 audit detached FEAT-1826 and ENH-1827 as off-theme; this EPIC created to house them
