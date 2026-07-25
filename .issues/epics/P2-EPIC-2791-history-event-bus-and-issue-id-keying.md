---
id: EPIC-2791
title: History Event Bus and Issue Id Keying
type: EPIC
priority: P2
status: open
captured_at: "2026-07-25T02:35:31Z"
discovered_date: 2026-07-25
discovered_by: create-epics-from-unparented
relates_to: [BUG-2769, BUG-2770, ENH-2771, ENH-2783]
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
