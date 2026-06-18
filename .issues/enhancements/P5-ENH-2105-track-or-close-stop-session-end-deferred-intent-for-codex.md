---
id: ENH-2105
title: Track or close `stop/session_end` deferred intent for Codex adapter
type: ENH
priority: P5
status: open
captured_at: "2026-06-12T00:00:00Z"
discovered_date: 2026-06-12
discovered_by: review-epic
parent: EPIC-1463
relates_to: [FEAT-1719]
labels:
  - codex
  - hooks
  - host-compat
---

# ENH-2105: Track or close `stop/session_end` deferred intent for Codex adapter

## Summary

The `stop/session_end` hook intent shows `(deferred)` in the Codex column of
`docs/reference/HOST_COMPATIBILITY.md` with no footnote linking to a tracking
issue. Either wire the intent for Codex (following the FEAT-1719 handler
pattern) or formally close it as not-applicable with a tracking footnote.

## Motivation

EPIC-1463's success metric is that every deferred/✗ cell in the Codex
compatibility matrix links to a real issue. The epic scope explicitly tracks
`post_compact` (FEAT-1719) and `permission_request` (absorbed into FEAT-1719
after FEAT-1720's supersession) as deferred intents, but omits
`stop/session_end` — leaving an untracked gap that contradicts the epic's
own bookkeeping standard.

## Acceptance Criteria

- [ ] Decision recorded: wire `session_end` for Codex, or close as
  not-applicable (with the Codex CLI capability evidence either way)
- [ ] If wiring: handler follows the established adapter pattern
  (`hooks/adapters/codex/*.sh` + dispatch entry + tests), mirroring
  FEAT-1719's implementation
- [ ] If closing: `docs/reference/HOST_COMPATIBILITY.md` Codex
  `stop/session_end` cell gains a footnote linking to this issue with the
  rationale
- [ ] No remaining unannotated `(deferred)` cells in the Codex column

## Integration Map

### Files to Modify
- `docs/reference/HOST_COMPATIBILITY.md` — Codex column annotation
- (If wiring) `hooks/adapters/codex/` + `scripts/little_loops/hooks/` +
  `scripts/tests/test_codex_adapter.py`

### Similar Patterns
- FEAT-1719 — PostCompact intent wiring for Codex (same decision shape and
  handler pattern)

## Impact

- **Priority**: P5 — bookkeeping/parity tracking, matches sibling priorities
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Verification Notes

2026-06-18 (ACCURATE): `HOST_COMPATIBILITY.md` line 28 shows `(deferred)` in the Codex column for `stop → session_end`. No footnote links to ENH-2105. The issue's goal of annotating the cell with a tracking link is still unmet.

## Status

**Open** | Created: 2026-06-12 | Priority: P5
