---
id: ENH-3743
title: Redact secrets at write time on every history.db raw_events insert path, with a backfill of stored rows [promoted]
status: open
priority: P0
type: ENH
discovered_date: 2026-09-15
discovered_by: research-apply
labels: []
research_source: https://github.com/pacifio/atlas
execution_target: little-loops
parent: EPIC-3744-redaction-pipeline
goals:
- 7
captured_at: "2026-10-05T00:00:00Z"
source_issue: ll-product/ENH-464 (promoted 2026-10-05)
---

# ENH-3743: Redact secrets at write time on every history.db raw_events insert path, with a backfill of stored rows [promoted]

## Summary

Promoted 2026-10-05 → little-loops #ENH-3743.

little-loops persists full transcripts into .ll/history.db today, and goal 6 turns that store into shipped fine-tuning datasets — a credential that survives to disk propagates into every downstream consumer of the export. The corpus covers this everywhere except the storage layer: EPIC-352 keeps credentials out of declared environments, ENH-340 scans subject output as a verification check, ENH-385 gates telemetry fields, ENH-346 keeps durable history plain data. The missing half is redaction on write, before persistence, on every path that lands in history.db or an export: a pure string-in/string-out redactor (entropy heuristics plus rule families — provider key prefixes, bearer tokens, credentialed URIs) applied identically to transcript writes and export emission. Purity means no I/O, which makes the redaction verdict itself property-testable in the EPIC-396 style.

## Source Doc

- docs/research/2026-09-15-atlas-agent-workbench-architecture.md

## Scope addition (2026-10-05)

Per `docs/plans/2026-10-05-backlog-audit-decisions.md` §1, the exposure is already live, not only on future write paths:

- `raw_events.raw_line` stores host log lines verbatim. little-loops' own history.db (spoke `c08c79b89`) has 34,212 Claude Code rows with `thinking` blocks, 15,410 of them with non-empty plaintext reasoning: the content class Panfilov et al. 2026 found carrying credentials absent from visible history.
- `pii.py`'s redactor exists (used by the `sft-corpus` filter, `cli/logs.py`, and the `cli/loop/evidence.py` scanner), but no `raw_events` insert calls it.
- `_REMOTE_RAW_INSERT` ships `raw_line` to a shared remote store when one is configured (none is today).

The deliverable therefore includes (1) redaction of `raw_line` on ingest, before insert and before any remote push, and (2) a one-time redaction pass over rows already stored. This issue is now the prerequisite (`blocked_by`) of ENH-478 and ENH-479.

**Re-prioritized 2026-10-05 (P2→P0):** Spoke gap verified against little-loops main 07377cdc9: `pii.redact_pii()` (pii.py:140) exists but none of the three `raw_events` inserts call it — session_store/lifecycle.py:873 (local), :777/:840 (remote push), :1581 (refresh_usage_source). **Promotion scope:** redaction at ingest on those three paths, plus the one-time pass over stored rows; extend the rule families (bearer tokens, credentialed URIs, entropy) as part of it. Exports beyond ingest are follow-on work, not this unit. Correction: the redactor's consumers are the sft-corpus filter, `cli/logs.py:1864`, and the `cli/loop/evidence.py:28` scanner, not sft-corpus alone. See `docs/plans/2026-10-05-backlog-audit-decisions.md` §5.

## Status

**Promoted** | Created: 2026-09-15 | Promoted: 2026-10-05 → little-loops #ENH-3743
