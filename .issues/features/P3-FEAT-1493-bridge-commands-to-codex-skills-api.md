---
id: FEAT-1493
type: FEAT
priority: P3
status: open
captured_at: "2026-05-16T13:04:12Z"
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
blocked_by: [ENH-1497]
relates_to: [FEAT-1486, FEAT-1487]
labels: [captured, codex, host-compat, skills-api]
---

# FEAT-1493: Bridge `commands/*.md` to Codex Skills API

## Summary

`ll-adapt-skills-for-codex` only adapts `skills/*/SKILL.md` — the markdown files under `commands/*.md` (where many `/ll:*` slash commands are defined) are not translated to Codex Skills API entries. From the Codex CLI, those commands are unreachable. Extend the adapter (or add a sibling tool) so command markdown is also exposed as `~/.codex/skills/<name>/SKILL.md` entries.

## Current Behavior

`scripts/little_loops/cli/adapt_skills_for_codex.py:158` walks `skills/*/SKILL.md` and emits `agents/openai.yaml` + Codex frontmatter additions for each. Files under `commands/` (e.g. `commands/scan-codebase.md`, `commands/check-code.md`) are not touched. A Codex user with `~/.codex/skills/` populated still cannot invoke `/ll:scan-codebase` style commands — only the 14 skills directory entries are discoverable.

## Expected Behavior

Running the Codex skills adapter exposes both `skills/*/SKILL.md` AND `commands/*.md` to Codex via the Skills API. After adaptation, `/ll:scan-codebase`, `/ll:check-code`, `/ll:commit`, etc. work identically in Codex and Claude Code (modulo skills with `disable-model-invocation: true`, which remain user-only — see ENH-1497).

## Motivation

This is the **biggest user-facing parity gap** identified by the Codex integration audit. EPIC-1463 originally asserted that the Skills API covers both commands and skills, but inspection shows the adapter only processes the `skills/` directory. Without this bridge, a Codex user is missing roughly half the `/ll:*` surface — including high-value commands like `scan-codebase`, `check-code`, `commit`, and `open-pr`.

## Proposed Solution

Two viable approaches:

1. **Extend `ll-adapt-skills-for-codex`** to also walk `commands/*.md`, treating each as a single-file skill: synthesize a `SKILL.md` wrapper, emit `agents/openai.yaml`, install under `~/.codex/skills/ll-<name>/`. Namespace prefix avoids collision with skills that share a name.
2. **New tool `ll-adapt-commands-for-codex`** with its own CLI entrypoint, sharing the frontmatter/yaml-emission helpers with the skills adapter. Cleaner separation but more code.

Recommend (1) — most of the logic is already in place; commands and skills have similar enough structure that one tool is simpler than two.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — extend walker to include `commands/`
- `docs/reference/HOST_COMPATIBILITY.md` — update the `[^cmds]` footnote (commands are now bridged)
- `.claude/CLAUDE.md` — update the `ll-adapt-skills-for-codex` description to mention commands

### Dependent Files (Callers/Importers)
- `scripts/tests/test_adapt_skills_for_codex.py` — extend fixtures and assertions for commands
- TBD — grep for `adapt_skills_for_codex` callers

### Similar Patterns
- `skills/*/SKILL.md` adaptation logic (existing reference implementation in same file)

### Tests
- Unit test: command markdown under fixtures produces `~/.codex/skills/ll-<name>/` entries
- Integration test: round-trip a real `commands/check-code.md` through the adapter and verify Codex can discover it

## Implementation Steps

1. Extend `adapt_skills_for_codex.py` to discover `commands/*.md` files in addition to `skills/*/SKILL.md`
2. Synthesize a SKILL.md wrapper for each command (lifting description/trigger keywords from frontmatter if present, falling back to the H1 heading)
3. Namespace installed directories as `ll-<command-name>` to avoid collision
4. Update test fixtures and add coverage in `test_adapt_skills_for_codex.py`
5. Update `HOST_COMPATIBILITY.md` to flip the `[^cmds]` row from ✗ to ✓ once shipped
6. Verify end-to-end by installing into a fresh `~/.codex/skills/` and discovering a bridged command from Codex

## Impact

- **Priority**: P3 — Largest single-surface parity gap for Codex users
- **Effort**: Medium — Adapter logic exists; needs extension + tests
- **Risk**: Low — Additive; existing skills adaptation unchanged
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Codex compatibility matrix; defines the gap |
| `.claude/CLAUDE.md` | Describes `ll-adapt-skills-for-codex` and CLI tools |


## Blocks

- ENH-1495
- FEAT-1496

## Labels

`feat`, `captured`, `codex`, `host-compat`, `skills-api`

## Status

**Open** | Created: 2026-05-16 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-16T13:04:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f112cdc-ed18-410c-85e1-0d7cc45aa863.jsonl`
