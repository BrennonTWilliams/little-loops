---
id: FEAT-2188
title: Skills adaptation — ll-adapt-skills-for-gemini copying skills to .gemini/skills/
type: feature
status: open
priority: P4
parent: EPIC-2178
depends_on: [FEAT-2179]
captured_at: "2026-06-15T00:00:00Z"
discovered_date: 2026-06-15
discovered_by: capture-issue
labels: [gemini, host-compat, skills, adaptation]
---

# FEAT-2188: Skills adaptation — ll-adapt-skills-for-gemini

## Summary

Add `ll-adapt-skills-for-gemini` CLI tool (analogous to `ll-adapt-skills-for-codex`)
that copies ll skills to `.gemini/skills/<name>/SKILL.md` with any minor adaptations
needed for Gemini's skill discovery surface.

From FEAT-2179: Gemini's skill surface is `.gemini/skills/<name>/SKILL.md` —
**same format as Claude Code**, minor adaptation only (confirm `name:` frontmatter
is present; no deep rewrite needed).

## Use Case

A Gemini user wants to invoke ll skills from within Gemini CLI. Running
`ll-adapt-skills-for-gemini` populates `.gemini/skills/` so Gemini discovers
and offers ll skills.

## Implementation Steps

1. Create `scripts/little_loops/adapt_gemini_skills.py` (or add a subcommand
   to an existing adapt module).
2. Implementation:
   - Enumerate `skills/*/SKILL.md`.
   - For each skill, ensure `name:` frontmatter field is present (add if missing).
   - Copy to `.gemini/skills/<name>/SKILL.md`, creating the directory.
   - Log any skills skipped due to Gemini-incompatible metadata.
3. Register as `ll-adapt-skills-for-gemini` entry point in `pyproject.toml`.
4. Add tests in `scripts/tests/test_adapt_gemini_skills.py`.
5. Document in `docs/reference/HOST_COMPATIBILITY.md` Gemini column.

## Acceptance Criteria

- `ll-adapt-skills-for-gemini` runs without error on the current skill set.
- All skills with a `name:` field appear under `.gemini/skills/`.
- Skills missing `name:` get it synthesized from the directory name.
- Existing `.gemini/skills/` entries not from ll are not modified.
- Tests pass.

## API/Interface

### New Files

- `scripts/little_loops/adapt_gemini_skills.py` (or similar)
- `scripts/tests/test_adapt_gemini_skills.py`

### Files to Modify

- `scripts/pyproject.toml` — new entry point

## Research Notes (FEAT-2179)

Gemini skill surface: `.gemini/skills/<name>/SKILL.md` — compatible format with
Claude Code; only `name:` frontmatter field may need to be ensured.

Codex analog: `ll-adapt-skills-for-codex` in `scripts/little_loops/adapt_skills_codex.py`.

## Impact

- **Effort**: S (2–4 hours)
- **Risk**: Low — additive; does not modify source skills
- **Breaking Change**: No

---

**Open** | Created: 2026-06-15 | Priority: P4
