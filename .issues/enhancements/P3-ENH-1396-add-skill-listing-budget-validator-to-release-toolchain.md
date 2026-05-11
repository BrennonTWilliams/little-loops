---
captured_at: "2026-05-09T20:48:12Z"
discovered_date: 2026-05-09
discovered_by: capture-issue
blocked_by: [ENH-1395]
---

# ENH-1396: Add Skill Listing Budget Validator to Release Toolchain

## Summary

Add an `ll-verify-skill-budget` CLI tool (or extend `ll-verify-skills`) that checks whether the total skill description token footprint stays within the Claude Code listing budget (default: 1% of context). Fails non-zero if over budget, closing the feedback loop that today requires manually running `/doctor` after every skill change.

## Current Behavior

The only way to detect skill listing truncation is to run `/doctor` interactively after a session starts. There is no automated pre-release or CI check. ENH-977 adds `ll-verify-skills` to check SKILL.md *file size* (500-line limit) but does not check *description token budget* — a different and orthogonal concern.

## Expected Behavior

- `ll-verify-skill-budget` scans all `skills/*/SKILL.md` files for `description` fields in frontmatter
- Estimates token count for each description (character-based approximation: chars / 4)
- Sums descriptions for skills that do NOT have `disable-model-invocation: true`
- Compares against configurable threshold (default: 1% of 200k = 2,000 tokens)
- Prints a per-skill breakdown sorted by token count
- Exits 0 if under budget; exits 1 if over, listing which skills are the top contributors
- Integrates into the release checklist alongside `ll-verify-docs` and `ll-check-links`

## Motivation

The listing budget problem is invisible until `/doctor` fires. By the time a developer notices, the truncation has already silently degraded session quality for some number of releases. A cheap pre-release check converts an invisible regression into a loud build failure at the right moment — when a skill is added or a description is lengthened.

This is distinct from ENH-977 (`ll-verify-skills` checks SKILL.md line count) and complements it. Both checks belong in CI.

## Proposed Solution

Extend `scripts/little_loops/doc_counts.py` with a `check_skill_budget()` function following the same patterns as `check_skill_sizes()` (ENH-977) and `count_files()`. Add CLI entry point in `scripts/little_loops/cli/docs.py` following `main_verify_docs()`.

Token estimation: `len(description) / 4` (conservative approximation; real tokenization not needed for a lint gate).

Threshold: Read from `.ll/ll-config.json` or default to 2000 tokens (1% of 200k context).

## Implementation Steps

1. Add `check_skill_budget(threshold_tokens: int = 2000) -> tuple[int, list[tuple[Path, str, int]]]` to `scripts/little_loops/doc_counts.py` — returns `(total_tokens, violations)` where violations are skills over a per-skill warning threshold (e.g., 200 tokens)
2. Add `main_verify_skill_budget()` entry point in `scripts/little_loops/cli/docs.py` — print per-skill token breakdown, total, threshold comparison; exit 1 if over budget
3. Register entry point in `scripts/pyproject.toml` — `ll-verify-skill-budget = "little_loops.cli:main_verify_skill_budget"`
4. Add tests: `TestMainVerifySkillBudget` class in `scripts/tests/test_cli_docs.py`
5. Register in all CLI tool listings: `commands/help.md`, `.claude/CLAUDE.md`, `docs/reference/CLI.md`; increment `"20 CLI tools"` count in `README.md` only — do NOT add a `### ll-` section there (README is a hero page; see CONTRIBUTING.md § "Documentation wiring for new CLI tools") [updated 2026-05-10]
6. Add to release checklist in `CONTRIBUTING.md`

## Integration Map

### Files to Modify
- `scripts/little_loops/doc_counts.py` — add `check_skill_budget()` function
- `scripts/little_loops/cli/docs.py` — add `main_verify_skill_budget()` entry point
- `scripts/pyproject.toml` — register CLI entry point
- `scripts/little_loops/cli/__init__.py` — add import and `__all__` entry
- `commands/help.md` — add to CLI TOOLS list
- `.claude/CLAUDE.md` — add to CLI Tools section
- `README.md` — add `ll-verify-skill-budget` subsection
- `docs/reference/CLI.md` — add reference section
- `CONTRIBUTING.md` — add to release checklist

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/docs.py:main_verify_docs()` — implementation pattern to follow
- `scripts/tests/test_cli_docs.py:TestMainVerifyDocs` — test pattern to follow

### Similar Patterns
- ENH-977 (`ll-verify-skills`) — nearly identical implementation pattern, different metric

### Tests
- `scripts/tests/test_cli_docs.py` — add `TestMainVerifySkillBudget`
- `scripts/tests/test_skill_budget_checker.py` — unit tests for `check_skill_budget()`

### Documentation
- `CONTRIBUTING.md` — release checklist
- `docs/reference/CLI.md` — tool reference

### Configuration
- `.ll/ll-config.json` — optional `skill_budget.threshold_tokens` override

## Impact

- **Priority**: P3 — closes the feedback loop for listing budget enforcement
- **Effort**: Low — follows well-established pattern (ENH-977, `ll-verify-docs`)
- **Risk**: Low — additive; no existing behavior changed
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `testing`, `skills`, `context-engineering`

## Status

**Open** | Created: 2026-05-09 | Priority: P3

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:48:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c428abc-6b67-47fc-b1a4-d2d8d176f6b7.jsonl`
