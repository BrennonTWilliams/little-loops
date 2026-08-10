---
id: EPIC-2791
title: History Event Bus and Issue Id Keying
type: EPIC
priority: P2
status: done
captured_at: '2026-07-25T02:35:31Z'
discovered_date: 2026-07-25
discovered_by: create-epics-from-unparented
relates_to:
- BUG-2769
- BUG-2770
- ENH-2771
- ENH-2783
blocked_by:
- EPIC-2457
---

# EPIC-2791: History Event Bus and Issue Id Keying

## Summary

Group of 4 related issues concerning how issue identity and lifecycle events
reach the history store — malformed or mutable ids mis-keying rows, and status
transitions that never emit an event. Includes: BUG-2769 (Issue-id ingest trusts
malformed frontmatter id), BUG-2770 (set-status writes a snapshot but no
issue_event), ENH-2771 (Key history tables on the stable numeric issue id),
ENH-2783 (Parallel/sprint issue-close events are not live-written to the history
event bus).

## Children

- **BUG-2769** — Issue-id ingest trusts malformed frontmatter id, silently mis-keying history rows
- **BUG-2770** — set-status writes a snapshot but no issue_event, silently breaking session lookup
- **ENH-2771** — Key history tables on the stable numeric issue id, not the mutable TYPE-NNN string
- **ENH-2783** — Parallel/sprint issue-close events are not live-written to the history event bus

## Related Key Documentation

- `docs/reference/API.md` — documents `issue_parser`, `session_store`, and
  `events`, the modules whose id-keying and event-emission correctness this
  EPIC's children fix.
- `.claude/CLAUDE.md` — documents the issue-file id/status conventions
  (`ll-issues`, status values) that malformed-id ingest (BUG-2769) and
  `set-status` event emission (BUG-2770) must stay consistent with.

## Verification Notes

- Verified 2026-08-10 via /ll:verify-issues: all child issues confirmed done — closing epic.

## Session Log
- `/ll:verify-issues` - 2026-08-10T16:25:23 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-05T00:25:07 - `2f3f7bc8-367e-4fba-936b-eaf8049da3c4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:46 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
