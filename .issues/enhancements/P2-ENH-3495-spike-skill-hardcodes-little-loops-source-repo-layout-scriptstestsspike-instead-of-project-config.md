---
id: ENH-3495
type: ENH
title: spike skill hardcodes little-loops source-repo layout (scripts/tests/spike)
  instead of project config
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T00:15:03Z'
---

# ENH-3495: spike skill hardcodes little-loops source-repo layout (scripts/tests/spike) instead of project config

## Summary

`/ll:spike` hardcodes the little-loops source-repo layout. Its `allowed-tools` frontmatter grants `Write(scripts/tests/spike/**)` / `Edit(scripts/tests/spike/**)`, its plan template and SKILL.md body place every spike package under `scripts/tests/spike/<slug>/`, and the promotion step targets `scripts/little_loops/spike/<slug>/`. Neither path exists in a consuming project, so in any project other than little-loops itself the skill either writes into a directory the user never asked for or is blocked by its own permission glob.

## Context

Found 2026-09-16 during the docs-audience sweep (CONTRIBUTING.md § Documentation Audience). `docs/reference/COMMANDS.md` carries an `ll-audience-ok` suppression on the `/ll:spike` entry that should be removed when this lands. The skills-audience gate in `scripts/tests/test_docs_audience_gate.py` exempts `skills/spike/` by this issue ID; remove that exemption too.

## Current Behavior

- `skills/spike/SKILL.md` frontmatter: `Write(scripts/tests/spike/**)`, `Edit(scripts/tests/spike/**)`.
- SKILL.md body (Implementation, Spike location, Promotion, `--check` mode) and `skills/spike/plan-template.md` all name `scripts/tests/spike/<slug>/` and `scripts/little_loops/spike/<slug>/` literally.
- The regression-suite command `python -m pytest scripts/tests/<named-regression-suite>.py` assumes the source-repo test dir.

## Expected Behavior

Spike location derives from the consuming project's config: `project.test_dir` (or `tests/` when unset) joined with `spike/<slug>/`, and the promotion target derives from `project.src_dir`. `allowed-tools` must still fence writes to the spike directory only; since the frontmatter glob is static, either widen it to a config-independent shape (e.g. `Write(**/spike/**)`) or document that consuming projects override it via `.claude/settings` — decide during refinement. The skill must run unchanged in a project whose layout is `src/` + `tests/`.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] `skills/spike/SKILL.md` and `plan-template.md` contain no `scripts/tests` or `scripts/little_loops` literals.
- [ ] Spike dir and promotion target resolve from `project.test_dir` / `project.src_dir` with sensible defaults.
- [ ] `allowed-tools` still restricts writes to the spike directory in a `src/` + `tests/` project.
- [ ] The `skills/spike/` exemption in `test_docs_audience_gate.py` and the `ll-audience-ok` line in `docs/reference/COMMANDS.md` are removed.

## Status

**Open** | Created: 2026-09-17 | Priority: P2
