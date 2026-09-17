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

## Program Design

### Types

- `SPIKE_DIR: str` (bash var, `<test_dir>/spike/<slug>`)
- `PROMOTE_DIR: str` (bash var, `<src_dir>/spike/<slug>`)

### Signatures

- `BRConfig.resolve_variable(self, var_path: str) -> str | None` — existing,
  `scripts/little_loops/config/core.py:1108`; backs the `ll-config get
  project.test_dir` / `ll-config get project.src_dir` CLI already exercised
  from bash elsewhere (`scripts/little_loops/cli/config.py`)
- `BRConfig.get_src_path(self) -> Path` — existing,
  `scripts/little_loops/config/core.py:606`

### Call Path

`skills/spike/SKILL.md` Phase 3 (Plan) / Phase 4 (Implement) -> `ll-config get
project.test_dir` -> `BRConfig.resolve_variable("project.test_dir")` ->
`SPIKE_DIR="${TEST_DIR%/}/spike/<slug>"` (replaces the literal
`scripts/tests/spike/<slug>/`); Phase 6 (Promotion) -> `ll-config get
project.src_dir` -> `BRConfig.get_src_path` -> `PROMOTE_DIR="${SRC_DIR%/}/spike/<slug>"`
(replaces the literal `scripts/little_loops/spike/<slug>/`).
`skills/spike/plan-template.md` follows the same substitution for its
`Critical files`, `Implementation`, and `Promotion` sections. Note: this
repo's own `.ll/ll-config.json` does not set `project.test_dir`, so it
currently resolves to the schema default `"tests"`, not the actual
`scripts/tests/` root — implementation should confirm whether that also
needs setting here, or whether the skill falls back to a
`pytest.ini`/`pyproject.toml` probe when `project.test_dir` is absent.

## Scope Boundaries

- **In scope**: deriving the spike directory and promotion target from
  `project.test_dir`/`project.src_dir` in `skills/spike/SKILL.md` and
  `skills/spike/plan-template.md`; resolving the `allowed-tools` static-glob
  tension (widen to a config-independent shape or document a settings
  override); removing the `skills/spike/` exemption in
  `test_docs_audience_gate.py` and the `ll-audience-ok` suppression in
  `docs/reference/COMMANDS.md`.
- **Out of scope**: changing the spike plan's required section shape
  (`plan-template.md`'s Context/Approach/Acceptance Criteria structure);
  changes to `/ll:explore-api` (the external-API analogue); migrating any
  spike artifacts already committed under `scripts/tests/spike/` in this
  repo.

## Impact

- **Priority**: P2 - functional-correctness/portability bug (not a crash):
  `/ll:spike` is unusable as shipped in any consuming project whose layout
  isn't `scripts/`, so it blocks a whole skill outside the source repo.
- **Effort**: Small - text/template substitution in two files
  (`SKILL.md`, `plan-template.md`) plus removing two doc-audience
  exemptions; reuses the existing `ll-config get project.src_dir` /
  `project.test_dir` CLI pattern already used elsewhere in the codebase
  (`scripts/little_loops/cli/issues/decisions.py:650`), no new mechanism
  needed.
- **Risk**: Low - the spike directory stays isolated under
  `<test_dir>/spike/<slug>/` either way; the only behavior change is which
  literal path is written to, verified by re-running the skill in both the
  `scripts/`-layout source repo and a `src/`+`tests/` fixture project.
- **Breaking Change**: No - existing spike artifacts already committed under
  `scripts/tests/spike/` are untouched; only future `/ll:spike` invocations
  resolve their path dynamically.

## Acceptance Criteria

- [ ] `skills/spike/SKILL.md` and `plan-template.md` contain no `scripts/tests` or `scripts/little_loops` literals.
- [ ] Spike dir and promotion target resolve from `project.test_dir` / `project.src_dir` with sensible defaults.
- [ ] `allowed-tools` still restricts writes to the spike directory in a `src/` + `tests/` project.
- [ ] The `skills/spike/` exemption in `test_docs_audience_gate.py` and the `ll-audience-ok` line in `docs/reference/COMMANDS.md` are removed.

## Status

**Open** | Created: 2026-09-17 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-17T00:37:18 - `2b860fe0-3e33-4473-a957-2f06e4ff45f0.jsonl`
