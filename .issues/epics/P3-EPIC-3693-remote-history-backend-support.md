---
id: EPIC-3693
title: Remote History Backend Support
type: EPIC
priority: P3
status: open
captured_at: "2026-10-02T17:30:24Z"
discovered_date: 2026-10-02
discovered_by: link-epics
relates_to: []
---

# EPIC-3693: Remote History Backend Support

## Summary

Group of 10 related issues covering history readers, writers, and tests under a remote history backend: reader-CLI verdicts, hand-built `history.db` paths, strict-read infrastructure, shared test fixtures, derive-version rebuild gating, bounded lock waits, spooled context-monitor writes, budgeted prepatch reads, and serving `ll-history` and MCP/SFT readers from a remote store.

## Children

- **ENH-3657** — Give history reader CLIs a remote-backend verdict (refuse or degrade) (open)
- **ENH-3658** — Handle hand-built history.db paths under a remote history backend (open)
- **ENH-3668** — Build strict-read infrastructure for HistoryTarget-aware history readers (open)
- **ENH-3677** — Hoist the shared remote history-backend test fixture into conftest.py (open)
- **ENH-3678** — Gate the auto-spawned history rebuild on a derive version instead of SCHEMA_VERSION (open)
- **ENH-3679** — Bound cli_event_context lock waits with a short busy timeout and a drop counter (open)
- **ENH-3680** — Spool context-monitor.sh history writes instead of detached background writes (open)
- **ENH-3682** — Budget best-effort remote prepatch history reads (open)
- **ENH-3684** — Serve ll-history rework, quality, collisions, sessions, root from a remote history store (open)
- **ENH-3685** — Serve MCP history_search and batch sft-corpus enrich from a remote history store (open)
