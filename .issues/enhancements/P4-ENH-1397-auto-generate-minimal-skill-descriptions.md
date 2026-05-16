---
captured_at: "2026-05-09T20:48:12Z"
discovered_date: 2026-05-09
discovered_by: capture-issue
status: done
completed_at: 2026-05-09T00:00:00Z
---

# ENH-1397: Auto-Generate Minimal Skill Descriptions from SKILL.md Content

## Summary

Add a script (or extend `ll-issues`) that reads each skill's `SKILL.md`, uses Claude to generate the shortest description still sufficient for LLM routing, and writes it back to the frontmatter. This keeps descriptions in sync with skill content and eliminates manual authoring of descriptions that drift over time.

## Current Behavior

Skill descriptions are written manually and never updated unless someone explicitly edits them. They tend to grow (added context, examples) and drift from the skill's actual trigger conditions. There is no tooling to regenerate or validate them against SKILL.md content.

## Expected Behavior

A command `ll-generate-skill-descriptions` (or a flag on an existing tool) reads each SKILL.md, extracts trigger keywords and the skill's purpose, calls the Claude API to generate a description of ≤ 100 characters that covers the key trigger phrases, and writes the result back to the `description` frontmatter field. Runs in dry-run mode by default (prints proposed changes without writing).

## Motivation

Manual description maintenance is a low-value task that doesn't scale. As new skills are added and existing ones evolve, descriptions become stale. A generation script converts description quality from a manual discipline into an automated invariant, and can be run as part of the release workflow.

## Proposed Solution

New CLI tool `ll-generate-skill-descriptions`:

```python
# For each skills/*/SKILL.md:
# 1. Parse frontmatter to get current description and disable-model-invocation
# 2. If disable-model-invocation: true → skip (no description needed in budget)
# 3. Extract trigger keywords section and first 500 chars of skill body
# 4. Call Claude API: "Generate a skill description ≤ 100 chars covering these triggers: ..."
# 5. Print proposed change (or write with --apply flag)
```

Uses `ll-action` infrastructure or direct Anthropic SDK call.

## Implementation Steps

1. Add `ll-generate-skill-descriptions` CLI in `scripts/little_loops/cli/`
2. Read each `skills/*/SKILL.md`, skip `disable-model-invocation: true` skills
3. Extract trigger keywords from frontmatter and first 500 chars of body
4. Call Claude API (claude-haiku-4-5 — cheap, fast, sufficient for description generation)
5. Validate output ≤ 100 chars, no bullet points
6. Dry-run by default; `--apply` writes to frontmatter
7. Register CLI entry point, add to `ll-verify-skill-budget` integration

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/` — new CLI module
- `scripts/pyproject.toml` — register entry point
- `CONTRIBUTING.md` — mention as optional release utility

### Dependent Files (Callers/Importers)
- Anthropic SDK — requires `pip install anthropic` (already a dependency)
- `skills/*/SKILL.md` — read input, optionally written output

### Similar Patterns
- `ll-action` — one-shot Claude invocation pattern

### Tests
- Unit tests for frontmatter parsing and description validation
- Integration test with mocked Claude API response

### Documentation
- `docs/reference/CLI.md` — tool reference

### Configuration
- N/A — uses default Anthropic API key from environment

## Impact

- **Priority**: P4 — quality-of-life tooling; not blocking
- **Effort**: Medium — requires Claude API integration and frontmatter read/write
- **Risk**: Low — dry-run default means no accidental writes
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `skills`, `context-engineering`, `ai-assisted`

## Status

**Open** | Created: 2026-05-09 | Priority: P4

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:48:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c428abc-6b67-47fc-b1a4-d2d8d176f6b7.jsonl`

---

## Resolution

- **Status**: Closed - Superseded
- **Completed**: 2026-05-09
- **Reason**: Superseded by ENH-1395 via conflict resolution audit
- **Proposed change**: Auto-generation tooling scope merged into ENH-1395's "New Skill Checklist" policy framework to avoid parallel duplicate efforts addressing the same description-bloat problem. ENH-1395 now owns both the manual policy documentation and the `ll-generate-skill-descriptions` CLI tool.
