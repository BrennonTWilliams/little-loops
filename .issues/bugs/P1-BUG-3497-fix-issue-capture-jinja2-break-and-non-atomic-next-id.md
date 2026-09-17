---
id: 3497
title: 'Fix issue capture: issue_capture jinja2 break and non-atomic next-id'
type: BUG
priority: P1
status: open
discovered_date: '2026-09-16'
labels:
- issue-capture
- concurrency
- hub
---

# Fix issue capture: issue_capture jinja2 break and non-atomic next-id

## Summary

Two defects make the issue-filing path unsafe, and together they have caused
two ID collisions in production use: on 2026-09-15 an operator filed three
issues by hand while concurrent automated processes allocated the same IDs
(the files had to be renumbered afterward), and on 2026-09-16 a second
collision occurred between two concurrent automated allocators, again forcing
renumbering.

1. **`issue_capture` is broken.** The atomic capture path returns
   `No module named 'jinja2'` and cannot run, forcing callers onto the manual
   `next-id` + write path.
2. **`ll-issues next-id` + manual write is non-atomic.** `next-id` reads the
   highest ID, but nothing locks or reserves that ID between the read and the
   file write. Concurrent automated processes (research mining, reconcile
   sweeps) allocate in the same window, so any gap is a collision window.

## Root cause (confirmed 2026-09-16)

- **jinja2:** `little_loops/cli/artifact/templatize.py` and `dashboard.py`
  import jinja2 and render the `.j2` templates under `little_loops/templates/`,
  but jinja2 is NOT declared in `pyproject.toml`. So `issue_capture` works where
  jinja2 is transitively present (the Hermes venv) and fails with
  `No module named 'jinja2'` in a leaner environment (the MCP server). Fix: add
  `jinja2` to the `pyproject.toml` dependencies.
- **next-id:** `little_loops/cli/issues/__init__.py` (the `ll-issues next-id`
  subcommand) reads the max ID with no lock or reservation before the file
  write. Fix: reserve-then-write under a lock, or an ID-reservation table, so
  two concurrent allocators can never hand out the same ID.

## Acceptance

- `issue_capture` files an issue with a fresh, unique ID end-to-end.
- Two concurrent captures (or a capture racing a manual write) can never produce
  the same ID.
- `next-id` is either atomic or clearly documented as a read-only hint.
