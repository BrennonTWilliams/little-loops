# FEAT-1287: ll:explore-api Skill — Implementation Plan

**Issue**: `.issues/features/P2-FEAT-1287-ll-explore-api-skill.md`
**Confidence**: 100 (from frontmatter)
**Size**: Medium

## Goal

Author `skills/explore-api/SKILL.md` (new 4-phase skill: Ingest → Hypothesize → Execute → Refine) and update the four doc files this issue owns plus `commands/help.md`. Add doc-wiring regression tests.

## Files to Change

| Path | Change |
|---|---|
| `skills/explore-api/SKILL.md` | **create** — full 4-phase skill |
| `README.md:161` | `28 skills` → `29 skills` |
| `CONTRIBUTING.md:122` | `28 skill definitions` → `29 skill definitions` |
| `CONTRIBUTING.md` skills tree (after `decide-issue/`) | insert `├── explore-api/  # Guided 4-phase external-API exploration with LearnTestRecord output` |
| `.claude/CLAUDE.md:38` | `(28 skills)` → `(29 skills)` |
| `.claude/CLAUDE.md` CLI list | add `ll-learning-tests` line before `ll-action`-adjacent block (insert alphabetically; co-locate near other registry/migration tools) |
| `docs/ARCHITECTURE.md` | new `## Learning Test Registry` section before `## Data Flow Summary` |
| `commands/help.md` | add `/ll:explore-api "<target>"` block under AUTOMATION & LOOPS; add `explore-api` to Quick Reference Table |
| `scripts/tests/test_feat1287_doc_wiring.py` | **create** — assert all of the above |

## SKILL.md outline

- Frontmatter: `description: "Use when..."`, `argument-hint: "<target> [--assume <claim>]..."`, `allowed-tools: [Read, Glob, Grep, Write, Bash(ll-learning-tests:*, mkdir:*, python:*, node:*)]`, `arguments` block (target required, --assume repeatable optional flag)
- Phase 1 — Ingest: `ll-learning-tests check "$TARGET"`; on exit 0 return prior record. Read docs/code samples.
- Phase 2 — Hypothesize: 3–7 falsifiable claims; pre-seed `--assume` claims as `result: untested`.
- Phase 3 — Execute: scaffold proof script to a temp path, run via Bash, capture stdout+stderr; `mkdir -p .ll/learning-tests/raw/`, move output to `.ll/learning-tests/raw/<slug>.txt`.
- Phase 4 — Refine: compute slug (lowercase, strip non-word, collapse hyphens — matches `little_loops.issue_parser.slugify`); emit `.ll/learning-tests/<slug>.md` via `Write` with the exact YAML frontmatter shape from `write_record()`; status = `proven` if any pass, else `refuted`.

## Verification

```bash
python -m pytest scripts/tests/test_feat1287_doc_wiring.py scripts/tests/test_learning_tests.py -v
ruff check scripts/
```
