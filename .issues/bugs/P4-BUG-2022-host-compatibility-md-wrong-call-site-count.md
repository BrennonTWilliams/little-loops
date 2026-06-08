---
id: BUG-2022
title: "HOST_COMPATIBILITY.md footnote says 'seven call sites' but table has six rows"
status: open
priority: P4
type: BUG
created: 2026-06-08
---

## Problem

`docs/reference/HOST_COMPATIBILITY.md`, in the `## Orchestration CLI` section, contains a footnote `[^orch]` that reads "All seven call sites now route through `scripts/little_loops/host_runner.py`." The table directly above only has six rows: `ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, `ll-harness`, and `FSM evaluators / handoff`.

`ll-sprint` is listed in `CLAUDE.md` as using `host_runner` but is absent from the table. It is likely the missing seventh entry.

## Fix

Verify that `ll-sprint` routes through `host_runner.py`, then either:
1. Add `ll-sprint` as a row in the Orchestration CLI table (making the count accurate), or
2. If the count is wrong, update the footnote text to say "six."

## Location

- File: `docs/reference/HOST_COMPATIBILITY.md`
- Section: `## Orchestration CLI`, footnote `[^orch]`

## Source

Discovered during `/ll:audit-docs docs/reference` on 2026-06-08.
