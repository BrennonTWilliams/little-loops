---
id: ENH-2020
title: "CLI.md introduction claims to cover 'all ll- tools' but mcp-call lacks the ll- prefix"
status: open
priority: P5
type: ENH
created: 2026-06-08
---

## Problem

`docs/reference/CLI.md` opens with language like "all `ll-` command-line tools," but `mcp-call` is documented in the Utilities section without the `ll-` prefix. The tool name is accurate, but the page framing is slightly misleading.

## Location

- File: `docs/reference/CLI.md`
- Section: Page introduction and `mcp-call` Utilities section

## Expected Outcome

The introduction text is updated to acknowledge that the page covers `ll-*` tools plus `mcp-call` (which does not use the `ll-` prefix), or `mcp-call` is moved to a clearly separated section.

## Source

Discovered during `/ll:audit-docs docs/reference` on 2026-06-08.
