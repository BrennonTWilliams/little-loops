---
id: EPIC-2370
title: "ll-issues clusters UX Improvements"
type: EPIC
priority: P3
status: open
captured_at: "2026-06-28T17:55:50Z"
discovered_date: 2026-06-28
discovered_by: create-epics-from-unparented
relates_to: [FEAT-2337, ENH-2335, ENH-2336]
---

# EPIC-2370: ll-issues clusters UX Improvements

## Summary

Group of 3 related issues improving the `ll-issues clusters` subcommand output quality and usability: contained output fixes (legend, palette, edge notation), scoping/compaction flags with richer cluster headers, and a full graph-aware layout replacement for hub/star dependency topologies. Includes: FEAT-2337 (replace linear box-stack with graph-aware layout), ENH-2335 (add legend, shared palette, unified edge notation), ENH-2336 (add scoping flags and richer per-cluster headers).

## Children

- **ENH-2335** — ll-issues clusters: add legend + filter/summary header, adopt shared palette, unify edge notation
- **ENH-2336** — ll-issues clusters: add scoping flags (--cluster/--limit/--compact) and richer per-cluster headers
- **FEAT-2337** — ll-issues clusters: replace linear box-stack with a graph-aware layout
