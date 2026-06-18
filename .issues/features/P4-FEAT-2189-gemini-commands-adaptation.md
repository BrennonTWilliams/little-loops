---
id: FEAT-2189
title: Commands adaptation — ll-adapt-commands-for-gemini converting .md to .gemini/commands/*.toml
type: feature
status: open
priority: P4
parent: EPIC-2178
depends_on: [FEAT-2179]
captured_at: "2026-06-15T00:00:00Z"
discovered_date: 2026-06-15
discovered_by: capture-issue
labels: [gemini, host-compat, commands, adaptation]
---

# FEAT-2189: Commands adaptation — ll-adapt-commands-for-gemini

## Summary

Add `ll-adapt-commands-for-gemini` CLI tool that converts ll `commands/*.md`
files into `.gemini/commands/*.toml` format for Gemini's command discovery surface.

From FEAT-2179: Gemini commands live at `.gemini/commands/*.toml` — **TOML format**,
not Markdown. A bridge/conversion script is needed (no native compatibility with
`commands/*.md`).

## Use Case

A Gemini user wants to invoke ll commands (e.g., `/ll:scan-codebase`) from within
Gemini CLI. Running `ll-adapt-commands-for-gemini` generates TOML command
definitions that Gemini CLI discovers.

## Decision Needed

Need to confirm the exact TOML schema Gemini expects for `.gemini/commands/*.toml`.
FEAT-2179 confirmed the surface exists but did not capture the full schema. This
issue should either (a) read the Gemini docs at
`~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/` during
implementation, or (b) file a sub-issue to capture the schema.

**Implementation note**: Implement the adapter as a template-based converter
(Markdown frontmatter → TOML fields), not a deep Markdown parser.

## Implementation Steps

1. Read Gemini command TOML schema from bundled docs or gemini-cli GitHub.
2. Create `scripts/little_loops/adapt_gemini_commands.py`:
   - Enumerate `commands/*.md`.
   - Parse YAML frontmatter for `description`, `args`, `examples`.
   - Generate TOML with Gemini-required fields.
   - Write to `.gemini/commands/ll-<name>.toml`.
3. Register as `ll-adapt-commands-for-gemini` entry point.
4. Add tests in `scripts/tests/test_adapt_gemini_commands.py`.
5. Document in `docs/reference/HOST_COMPATIBILITY.md` Gemini column.

## Acceptance Criteria

- `ll-adapt-commands-for-gemini` produces valid TOML for all `commands/*.md`.
- Generated TOMLs are discoverable by `gemini` (validated manually or by parsing).
- Existing `.gemini/commands/` entries not from ll are not modified.
- Tests pass.

## API/Interface

### New Files

- `scripts/little_loops/adapt_gemini_commands.py`
- `scripts/tests/test_adapt_gemini_commands.py`

### Files to Modify

- `scripts/pyproject.toml` — new entry point

## Research Notes (FEAT-2179)

Gemini command surface: `.gemini/commands/*.toml` — TOML format; needs bridge.

Codex analog: `ll-adapt-agents-for-codex` / `ll-adapt-skills-for-codex` in
`scripts/little_loops/`.

## Impact

- **Effort**: S–M (4–8 hours; TOML schema research adds time)
- **Risk**: Low-Medium — TOML schema not yet fully captured; risk of format mismatch
- **Breaking Change**: No

---

**Open** | Created: 2026-06-15 | Priority: P4

## Verification Notes

2026-06-18 (NEEDS_UPDATE): Prerequisite FEAT-2179 is `done` — Gemini CLI research confirmed that `.gemini/commands/*.toml` is the correct discovery surface. The "Decision Needed" flag about the exact TOML schema remains open: FEAT-2179 confirmed the surface path but did not capture the full schema field list. Resolve the schema either by reading `~/.npm-global/lib/node_modules/@google/gemini-cli/bundle/docs/` during implementation (Option a), or file a sub-issue (Option b). No `adapt_gemini_commands.py` or test file exists yet. Implementation can begin once schema is confirmed.
