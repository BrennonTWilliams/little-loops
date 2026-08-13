---
id: EPIC-2792
title: Issue Parsing Performance
type: EPIC
priority: P3
status: done
verify_verdict: NON_VALID
captured_at: "2026-07-25T02:35:31Z"
discovered_date: 2026-07-25
discovered_by: create-epics-from-unparented
relates_to:
- ENH-2780
- ENH-2781
- ENH-2782
---

# EPIC-2792: Issue Parsing Performance

## Summary

Group of 3 related issues concerning redundant full-directory issue-file parsing
across the CLI and backfill paths — parse once and share instead of re-walking
per call. Includes: ENH-2780 (`find_issues(skip_blocked=True)` re-parses the
entire issue directory), ENH-2781 (`next-issue`/`next-issues` invoke
`find_issues` 2-4 times per command), ENH-2782 (`session_store.backfill()` parses
every issue file's frontmatter twice).

## Children

- **ENH-2780** — `find_issues(skip_blocked=True)` re-parses the entire issue directory to build the dependency graph
- **ENH-2781** — `next-issue`/`next-issues` invoke `find_issues` 2-4 times per command; parse once and share
- **ENH-2782** — `session_store.backfill()` reads and parses every issue file's frontmatter twice

## Related Key Documentation

- `docs/reference/API.md` — documents `issue_parser` and `session_store`, the two modules whose redundant-parsing paths this epic's children fix.

## Verification Notes

2026-08-10 (`/ll:verify-issues`): Verified 2026-08-10: all 3 children (ENH-2780, ENH-2781, ENH-2782) are status: done. Epic is a strong candidate for closure — consider setting status: done in a follow-up pass.

## Resolution

2026-08-12: Re-verified via `ll-issues show EPIC-2792` — all 3 children (ENH-2780, ENH-2781, ENH-2782) confirmed `status: done`. Closing the epic; no outstanding work remains.

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:07:48 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:51 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
