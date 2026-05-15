---
id: FEAT-1486
type: FEAT
priority: P5
status: open
captured_at: '2026-05-15T23:00:00Z'
discovered_date: 2026-05-15
discovered_by: manage-issue
parent: EPIC-1463
decision_needed: false
---

# FEAT-1486: Adapt ll Skills for Codex Skills API

## Summary

The Codex CLI Skills API (`~/.codex/skills/<name>/SKILL.md`) is confirmed stable
(researched in FEAT-1483). ll's existing `skills/*/SKILL.md` frontmatter is
incompatible: the required `name:` field is absent, and the recommended
`metadata.short-description:` and `agents/openai.yaml` UI metadata are missing.
This issue implements the adaptation needed to make ll skills installable and
discoverable from a Codex CLI session.

## Current Behavior

ll skills live at `skills/*/SKILL.md`. Claude Code discovers them via the plugin
SDK. Codex users have no in-session access to ll skills — they must call
`ll-action` or `ll-auto` from a terminal.

## Expected Behavior

After this issue:
- Each `skills/*/SKILL.md` has the required `name:` frontmatter field.
- Each `skills/*/SKILL.md` has `metadata.short-description:` for the Codex TUI chip.
- Each skill directory has an `agents/openai.yaml` with `display_name` and
  `short_description`.
- ll skills can be installed into a Codex session via
  `codex plugin marketplace add BrennonTWilliams/little-loops --sparse skills`
  (or the built-in `skill-installer`).

## Acceptance Criteria

- [ ] All `skills/*/SKILL.md` files have `name:` frontmatter matching their
      directory slug (e.g., `skills/manage-issue/SKILL.md` → `name: manage-issue`)
- [ ] All `skills/*/SKILL.md` files have `metadata:\n  short-description:` (≤80 chars)
- [ ] Each `skills/*/` directory has `agents/openai.yaml` with `display_name`
      and `short_description`
- [ ] `docs/reference/HOST_COMPATIBILITY.md` Codex "Skill discovery" cell updated
      from `✗` to `✓` (or `(partial)` if only a subset of skills is adapted)
- [ ] `thoughts/research/codex-command-discovery.md` gating recommendation updated
      to reflect implementation status

## Research Notes

See `thoughts/research/codex-command-discovery.md` for the full Codex Skills API
spec (SKILL.md frontmatter format, `agents/openai.yaml` format, installation
methods, and compatibility gap analysis).

## Integration Map

### Files to Modify

- `skills/*/SKILL.md` — add `name:` and `metadata.short-description:` to frontmatter
- `docs/reference/HOST_COMPATIBILITY.md` — flip Codex "Skill discovery" cell from ✗ to ✓

### Files to Create

- `skills/*/agents/openai.yaml` — one per skill directory

## Labels

codex, skills, host-compat
