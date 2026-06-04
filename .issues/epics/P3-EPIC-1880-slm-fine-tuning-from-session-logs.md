---
id: EPIC-1880
title: SLM Fine-Tuning from Session Logs
type: EPIC
priority: P3
status: open
captured_at: '2026-06-02T00:00:00Z'
discovered_date: '2026-06-02'
discovered_by: review-epic
relates_to: [FEAT-1826, ENH-1827, ENH-1885, ENH-1886, ENH-1941, ENH-1942, ENH-1943, ENH-1944]
labels:
  - epic
  - sft
  - fine-tuning
  - session-logs
  - history-db
  - slm
---

# EPIC-1880: SLM Fine-Tuning from Session Logs

## Summary

Build the tooling needed to turn Claude Code session data (stored in `history.db`, with raw `.jsonl` logs as graceful-degradation fallback) into curated SFT corpora ready for small-language-model fine-tuning. The pipeline uses `history.db` as the primary data source — ENH-1942 added the `assistant_messages` table (schema v11), `conversation_turns()` read API in `history_reader.py`, and DB-first delegation in `extract_conversation_turns()` — with JSONL parsing preserved as fallback.

| Child | Role | Status |
|---|---|---|
| ENH-1942 | Foundation: `history.db` schema v11 (`assistant_messages`), `conversation_turns()` read API, DB-first delegation | ✅ done |
| ENH-1827 | `ll-messages --sft-format` flag: one-off ingest and `--reader auto|db|jsonl` | ✅ done |
| ENH-1885 | PII detection utility (`little_loops.pii`) for `pii_action` filter | ✅ done |
| ENH-1886 | File-level mtime pre-filter for incremental harvesting | ✅ done |
| ENH-1941 | Integrate `history.db` session-quality signals into filtering → decomposed into ENH-1943 + ENH-1944 | ✅ done |
| ENH-1943 | `lookup_session_metadata()` helper in `history_reader.py` (grandchild of EPIC via ENH-1941) | ✅ done |
| ENH-1944 | `enrich` state + 4 quality predicates in `sft-corpus.yaml` (grandchild of EPIC via ENH-1941) | ✅ done |
| FEAT-1826 | `sft-corpus` FSM loop: full pipeline from staged transcripts to quality-gated corpus | 🔧 open (loop exists, issue outdated) |

## Motivation

`examples-miner` outputs prompt-optimization corpora (skill invocations, `tools_used`/`files_modified` JSON) and wraps `apo-textgrad` — wrong target and format for SLM fine-tuning. `dataset-curation` is a generic back-half pipeline with no JSONL log ingestion or SFT format conversion. A dedicated pipeline is needed that owns the full path from raw session logs through a publishable SFT corpus in standard formats (ChatML, Alpaca, ShareGPT).

## Children

- **ENH-1942** — Foundation: `history.db` schema v11 (`assistant_messages`), `conversation_turns()` in `history_reader.py`, DB-first delegation in `extract_conversation_turns()`, `--reader` flag on `ll-messages` ✅ done
- **ENH-1827** — `ll-messages --sft-format` flag: one-off ingest path and alternate input for the loop ✅ done
- **ENH-1885** — PII detection utility (`little_loops.pii`) to back `pii_action` filter in the loop ✅ done
- **ENH-1886** — File-level mtime pre-filter in `extract_conversation_turns()` for faster incremental harvest ✅ done
- **ENH-1941** — Integrate history.db session-quality signals into sft-corpus filtering → decomposed into ENH-1943 + ENH-1944 ✅ done
- **ENH-1943** — `lookup_session_metadata()` helper in `history_reader.py` (grandchild via ENH-1941) ✅ done
- **ENH-1944** — `enrich` state + 4 quality predicates in `sft-corpus.yaml` (grandchild via ENH-1941) ✅ done
- **FEAT-1826** — `sft-corpus` FSM loop: `stage → enrich → filter → publish` pipeline 🔧 open (loop exists at `scripts/little_loops/loops/sft-corpus.yaml`; issue outdated — see Verification Notes)

## Scope

### In Scope

- `scripts/little_loops/loops/sft-corpus.yaml` FSM loop (`stage → enrich → filter → publish`) with `history.db` quality-signal enrichment via `lookup_session_metadata()`
- `scripts/little_loops/history_reader.py` — `conversation_turns()` (DB-based turn-pair extraction) and `lookup_session_metadata()` (session-quality queries)
- `scripts/little_loops/session_store.py` — schema v11 (`assistant_messages` table) and `_backfill_assistant_messages()`
- `scripts/little_loops/user_messages.py` — DB-first delegation in `extract_conversation_turns()` with JSONL graceful-degradation fallback
- `--sft-format {chatml,alpaca,sharegpt}` and `--reader {auto,db,jsonl}` flags on the `ll-messages` CLI
- `SFTFormatter` class in `scripts/little_loops/` shared between the loop and the CLI
- `little_loops.pii` — PII detection utility for corpus filtering

### Out of Scope

- `dataset-curation` changes — reused as-is via `loop:` handoff
- Publishing to HuggingFace Hub or other registries — handled by `dataset-curation`'s publish state
- Training orchestration (Axolotl, LLaMA-Factory, torchtune) — out of scope; this epic produces the corpus only

## Acceptance Criteria

- [x] `ll-messages --sft-format chatml --stdout` emits valid JSON-lines in ChatML format. (ENH-1827)
- [x] `ll-messages --sft-format chatml --reader db` reads conversation turns from `history.db`; `--reader jsonl` uses raw JSONL; `--reader auto` does DB-first fallback. (ENH-1942)
- [x] `history_reader.conversation_turns()` returns turn-pair windows from `message_events JOIN assistant_messages`. (ENH-1942)
- [x] `history_reader.lookup_session_metadata()` returns quality signals (corrections, issue outcome, tool count, file modifications) per session. (ENH-1943)
- [x] Schema v11 (`assistant_messages` table) exists and backfill populates it. (ENH-1942)
- [x] `ll-loop validate sft-corpus` reports no ERRORs.
- [x] `sft-corpus` loop enriches staged transcripts with `history.db` quality metadata and filters on 4 opt-in predicates. (ENH-1944)
- [ ] `ll-loop run sft-corpus` completes end-to-end against `history.db`-backed data, producing `data/corpus/` with `manifest.json` and rejection tracking. (FEAT-1826 — loop exists but end-to-end integration testing not yet verified)

## Implementation Order

*Actual execution order (confirmed by git history and issue completion dates):*

1. **ENH-1827** — `ll-messages --sft-format` was the first building block (completed 2026-06-02)
2. **ENH-1885** — PII detection utility (completed 2026-06-03)
3. **ENH-1886** — mtime pre-filter (completed 2026-06-03)
4. **ENH-1942** — `history.db` migration: schema v11, `conversation_turns()`, DB-first delegation, `--reader` flag (completed 2026-06-04) — **foundational**; made `history.db` the primary data source
5. **ENH-1941** → decomposed into **ENH-1943** + **ENH-1944** (completed 2026-06-04) — quality-signal filtering on top of the ENH-1942 foundation
6. **FEAT-1826** — `sft-corpus` loop (exists, partially complete; see Verification Notes)

The remaining gap for FEAT-1826 is end-to-end integration validation: verifying the loop runs against real `history.db`-backed data and the `stage` state uses the DB-first `--reader auto` path instead of raw `cat *.jsonl`.

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

**Verdict: NEEDS_UPDATE** (reviewed 2026-06-04) — 6 of 7 children are `done`, plus both grandchildren of ENH-1941 (ENH-1943 + ENH-1944) are `done`. Only FEAT-1826 (sft-corpus FSM loop) remains `open`. Epic is ~90% complete.

**Code is well-aligned to `history.db`**: ENH-1942 successfully migrated the pipeline's data layer — `conversation_turns()` queries `message_events JOIN assistant_messages`, `lookup_session_metadata()` provides quality signals, `extract_conversation_turns()` uses DB-first fallback, and `ll-messages --reader` supports `auto|db|jsonl`. The `sft-corpus.yaml` loop uses `history.db` for all four quality predicates. JSONL parsing is preserved as graceful-degradation fallback only.

**Remaining gap — FEAT-1826**: The `sft-corpus` loop's `stage` state still cats raw JSONL (`cat "$DATA_DIR"/*.jsonl`) instead of using `ll-messages --sft-format --reader db`. The loop should be updated to use the DB-first path for content ingestion (not just metadata enrichment). The issue file itself is outdated — it claims no pipeline exists when the loop is at `scripts/little_loops/loops/sft-corpus.yaml` with functional `stage → enrich → filter → publish` states.

## Session Log
- `/ll:verify-issues` - 2026-06-04T04:22:07 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:review-epic` - 2026-06-02T00:00:00 - EPIC-1694 audit detached FEAT-1826 and ENH-1827 as off-theme; this EPIC created to house them
