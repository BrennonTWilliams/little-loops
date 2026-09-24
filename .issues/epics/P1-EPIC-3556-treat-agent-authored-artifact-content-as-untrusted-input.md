---
id: EPIC-3556
type: EPIC
title: Treat agent-authored artifact content as untrusted input
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:30:10Z'
supersedes:
- ENH-3540
---

# EPIC-3556: Treat agent-authored artifact content as untrusted input

## Summary

`ll-artifact` emits single-file HTML pages that embed agent-influenced strings (model/tool output, skill catalog text, loop/branch/model names). Rendering them as markup turns prompt injection into stored XSS against whoever opens the artifact. Make escaping the default at every render boundary, pin it with hostile-payload tests, and route artifact writes through the symlink-safe atomic writer. Supersedes ENH-3540, split into four independently shippable children.

## Motivation

A shared artifact is opened by people other than the one who ran the session, so an injected payload executes against a different victim. Today's dashboard is safe by construction of one page, not by a rule.

## Integration Map

### Files to Modify
- `scripts/little_loops/artifact_templates.py`, `cli/artifact/{dashboard,policy_builder,render,extract,design_md}.py`, `file_utils.py`, `templates/policy-router-builder.html.tmpl` (see ENH-3540 for line-level detail)

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Tests
- TBD - identify shared test infrastructure

### Documentation
- TBD - docs that need updates

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Goal

Every `ll-artifact` generator treats agent-influenced strings as untrusted where they enter emitted HTML; `render_template` bytes stay unchanged (FEAT-3308 round trips).

## Scope

In: script-context JSON, single-pass placeholders, `escape_data` ingest escaping, atomic symlink-safe writes, builder DOM sinks. Out: templatize region-context tagging (ENH-3554), changing the frozen render env. Cancelled ENH-3540 holds the full original spec; carry its Scope/AC text into each child.

## Children
- **ENH-3557** — Script-context-safe JSON and single-pass placeholder substitution (open)
- **ENH-3558** — Escape-by-default ingest for template data and extract output (open)
- **ENH-3559** — Symlink-safe artifact writes and umask-preserving atomic_write (open)
- **ENH-3560** — Remove interpolated innerHTML sinks from policy builder (open)





## Success Metrics

## Session Log
- `/ll:scope-epic` - 2026-09-24T18:30:39 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
