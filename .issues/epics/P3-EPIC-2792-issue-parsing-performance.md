---
id: EPIC-2792
title: Issue Parsing Performance
type: EPIC
priority: P3
status: open
captured_at: "2026-07-25T02:35:31Z"
discovered_date: 2026-07-25
discovered_by: create-epics-from-unparented
relates_to: [ENH-2780, ENH-2781, ENH-2782]
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
