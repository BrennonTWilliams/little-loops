---
discovered_commit: 99fd7bdaaa9bd05b09cba2b878c4d17a27ceaeb7
discovered_branch: main
discovered_date: 2026-04-12T00:00:00Z
discovered_by: audit-docs
doc_file: README.md
---

# ENH-1093: Document undocumented CLI entry points (ll-generate-schemas, mcp-call)

## Summary

Documentation issue found by `/ll:audit-docs`.

`pyproject.toml` registers 16 CLI entry points but README.md documents only 14, claiming "14 CLI tools". Two entry points are undocumented: `ll-generate-schemas` and `mcp-call`.

## Location

- **File**: `README.md`
- **Line(s)**: 90
- **Section**: What's Included

## Current Content

```markdown
**14 CLI tools** (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`, etc.) for autonomous and parallel issue processing
```

## Problem

Two entry points installed via `pip install little-loops` are documented in `docs/reference/CLI.md` (lines 1074 and 1096 respectively) but are absent from README.md's "What's Included" summary and the README CLI tools section:

- **`ll-generate-schemas`** — Regenerates JSON Schema files for all `LLEvent` types into `docs/reference/schemas/`. Developer/maintainer build tool used when the event schema changes.
- **`mcp-call`** — CLI wrapper for calling MCP tools: `mcp-call server/tool-name '{"param": "value"}'`. Debugging/testing utility for MCP integrations.

The tools are discoverable via `docs/reference/CLI.md` (linked from README), but the README "14 CLI tools" count and the CLI section do not surface them. The question is whether README should acknowledge them or whether omitting internal/debug tools from README is intentional.

## Expected Content

Decision required (see Options):

**Option A — Document `ll-generate-schemas` in CONTRIBUTING.md** (recommended): It's a maintainer tool, not end-user facing. Move documentation there, leave README count at 14.

**Option B — Document both in README CLI section**: Add brief sections for each, bump count to 16.

**Option C — Leave undocumented**: Both are internal utilities; current 14-count is correct for user-facing tools.

## Impact

- **Severity**: Low (tools still work; just undiscoverable for users who notice them)
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P4
