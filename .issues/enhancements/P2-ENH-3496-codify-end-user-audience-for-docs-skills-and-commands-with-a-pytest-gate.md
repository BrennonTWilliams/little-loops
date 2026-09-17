---
id: ENH-3496
type: ENH
title: Codify end-user audience for docs, skills, and commands with a pytest gate
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T00:33:50Z'
completed_at: '2026-09-17T00:33:59Z'
---

# ENH-3496: Codify end-user audience for docs, skills, and commands with a pytest gate

## Summary

User-facing docs, skills, and commands framed the reader as a little-loops contributor working inside the source checkout. `docs/guides/HISTORY_SESSION_GUIDE.md` opened with "observability for your little-loops project"; a sweep found ~90 lines across 25 user docs and ~100 more across 36 skills/commands citing `scripts/tests/`, `python -m pytest scripts/tests/`, `ruff check scripts/`, "this repo", or `scripts/little_loops/<file>.py` paths that do not exist in a consuming project. This issue records the sweep, the codified audience rule, and the pytest gate that enforces it.

## Current Behavior

- `docs/guides/` and `docs/reference/` mixed end-user guidance with contributor content (regression-gate test paths, source-repo test/lint commands as examples, "this repo" self-references).
- `skills/**/*.md` and `commands/*.md` pointed the model at `scripts/little_loops/...` and `scripts/tests/...`, which are unreachable in a consuming project. Two were live bugs: `configure/areas.md` copied design-token profiles from a source-tree path, and `rename-loop` / `simplify-loop` ran `git mv` inside the packaged loops dir for `builtin` scope.
- No written rule and no gate distinguished the audiences, so the drift recurred.

## Expected Behavior

- `docs/guides/`, `docs/reference/`, `README.md` address the little-loops end user: a developer whose own project consumes little-loops via `pip install little-loops` + `ll-init`. Examples use reader shapes (`pytest`, `tests/`, `src/`); the source is named explicitly as "the little-loops source repository" only when it is genuinely the subject.
- `skills/` and `commands/` assume execution inside the consuming project: pointers into little-loops internals use the installed dotted module (`little_loops.fsm.executor`), test/lint commands come from `project.test_cmd` / `project.lint_cmd`.
- Contributor content lives in `CONTRIBUTING.md`, `.claude/CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/development/`.
- A pytest gate fails the suite on regression.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Implementation

Landed in commit `6b60913de` (57 files).

- **Rule**: `CONTRIBUTING.md` § Documentation Audience (three-audience table, five rules, suppression contract); short form in `.claude/CLAUDE.md` § Documentation Audience. Verified `ll-init` never copies this repo's CLAUDE.md — its block is rendered from `_LL_COMMANDS` in `little_loops.init.writers`.
- **Gate**: `scripts/tests/test_docs_audience_gate.py`. User scope (`docs/guides/`, `docs/reference/`, `README.md`) scans seven curated markers; harness scope (`skills/`, `commands/`) adds `scripts/little_loops/`. Suppress with `ll-audience-ok: <reason>` on the same or preceding line; a suppression before a code fence covers the whole block. `skills/spike/` is exempt pending ENH-3495.
- **Docs sweep**: 17 files, ~60 lines rewritten, 11 suppressed.
- **Harness sweep**: 36 files, ~90 lines rewritten, ~8 suppressed. `rename-loop`/`simplify-loop` `builtin` scope now copies the packaged loop into `.loops/` (project copy shadows by name per `little_loops.fsm.loop_paths.resolve_loop_path`). `configure/areas.md` locates design-token profiles via the installed package. `wire-issue/caller-suitability-gate.md` keeps its real-tree worked example under one suppression because `test_caller_suitability_gate.py` drift-guards the cited seam.
- **Skills**: `audit-docs` gained an Audience audit dimension; `update-docs` gained an audience rule for stubs it writes.
- **Tests updated**: `test_wiring_skills_and_commands.py` and `test_review_epic_skill.py` now pin dotted-module strings.
- Host mirrors regenerated with `ll-adapt --host gemini|kimi-code|qwen --apply`.

## Acceptance Criteria

- [x] `docs/guides/HISTORY_SESSION_GUIDE.md` no longer says "your little-loops project".
- [x] `CONTRIBUTING.md` and `.claude/CLAUDE.md` define the end-user vs. consuming-project vs. contributor audiences.
- [x] `scripts/tests/test_docs_audience_gate.py` passes over `docs/guides/`, `docs/reference/`, `README.md`, `skills/`, `commands/`.
- [x] `ll-init`'s CLAUDE.md block is unaffected by the new CLAUDE.md section.
- [x] Full unit suite green apart from the pre-existing `test_verify_evidence.py::TestRepoGate` failure on BUG-3484's issue file.

## Follow-ups

- ENH-3495: make `/ll:spike` layout config-driven, then drop its gate exemption and the `ll-audience-ok` line in `docs/reference/COMMANDS.md`.

## Status

**Open** | Created: 2026-09-17 | Priority: P2
