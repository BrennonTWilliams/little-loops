---
id: EPIC-3562
title: Multi-Host Token Usage and Telemetry
type: EPIC
priority: P2
status: open
captured_at: "2026-09-24T18:44:15Z"
discovered_date: 2026-09-24
discovered_by: link-epics
relates_to: []
---

# EPIC-3562: Multi-Host Token Usage and Telemetry

## Summary

Group of 9 related issues: token usage ingestion, provenance labeling, and runtime telemetry across hosts (Claude, Codex, Qwen, Gemini, OMP).

## Children

- **ENH-3528** — Label token provenance per observation in ll-ctx-stats and exports (open)
- **ENH-3532** — Ingest Codex historical rollout token usage into usage_events (open)
- **ENH-3534** — Token usage ingestion for Qwen, Gemini, OMP and remaining hosts (open)
- **ENH-3543** — Codex live identity plumbing and shared live-rollout coverage selection (open)
- **ENH-3544** — Typed runtime telemetry availability in the runtime host map (open)
- **ENH-3545** — Label context-hook occupancy estimates and measurement staleness (open)
- **ENH-3546** — Establish Claude usage producer contract and measured provenance (open)
- **ENH-3549** — Migrate ll-logs, ll-messages and ll-ctx-stats onto the session-watcher seam (open)
- **BUG-3542** — Raw-event backfill stamps the configured host instead of each handle's source host (open)
