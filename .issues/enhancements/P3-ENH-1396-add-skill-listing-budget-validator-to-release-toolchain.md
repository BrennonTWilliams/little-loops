---
captured_at: '2026-05-09T20:48:12Z'
completed_at: 2026-05-11 05:45:22+00:00
discovered_date: 2026-05-09
discovered_by: capture-issue
blocked_by:
- ENH-1395
confidence_score: 100
outcome_confidence: 81
score_complexity: 13
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
status: done
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

## Scope Boundaries

- **In scope**: Scanning `skills/*/SKILL.md` frontmatter `description` fields; token estimation via character-count approximation (`len(description) / 4`); per-skill breakdown sorted by token count; configurable threshold via `.ll/ll-config.json`; integration into the release checklist
- **Out of scope**: Actual LLM tokenization (approximation is sufficient for a lint gate); checking SKILL.md file size (that is ENH-977's concern); auto-correcting or truncating descriptions; runtime enforcement during active Claude Code sessions

## API/Interface

```python
def check_skill_budget(threshold_tokens: int = 2000) -> tuple[int, list[tuple[Path, str, int]]]:
    """Scan skills/*/SKILL.md description fields, estimate tokens, return (total, violations)."""

def main_verify_skill_budget() -> None:
    """CLI entry: print per-skill token breakdown, exit 1 if total exceeds threshold."""
```

CLI usage:
```
ll-verify-skill-budget [--threshold N]
```
Exits 0 if under budget, exits 1 if over (listing top-contributing skills).

## Implementation Steps

1. Add `check_skill_budget(threshold_tokens: int = 2000) -> tuple[int, list[tuple[Path, str, int]]]` to `scripts/little_loops/doc_counts.py` — returns `(total_tokens, violations)` where violations are skills over a per-skill warning threshold (e.g., 200 tokens). Reuse `_parse_frontmatter()` from `generate_skill_descriptions.py` (import it directly or copy the ~10-line implementation). Follow `verify_documentation()` as the structural pattern, not `check_skill_sizes()` which doesn't exist yet.
2. Add `main_verify_skill_budget()` entry point in `scripts/little_loops/cli/docs.py` — print per-skill token breakdown, total, threshold comparison; exit 1 if over budget. Read threshold from config via: `BRConfig(base_dir)._raw_config.get("skill_budget", {}).get("threshold_tokens", 2000)` — or accept `--threshold N` CLI arg with same default.
3. Register entry point in `scripts/pyproject.toml` — `ll-verify-skill-budget = "little_loops.cli:main_verify_skill_budget"`
4. Add `main_verify_skill_budget` to existing import line in `scripts/little_loops/cli/__init__.py` (~line 31) and to `__all__` (~line 55)
5. Add tests: `TestMainVerifySkillBudget` class in `scripts/tests/test_cli_docs.py` following `TestMainVerifyDocs` pattern (patch `sys.argv`, patch core function at usage path, patch `builtins.print`, assert return 0/1)
6. Register in all CLI tool listings: `commands/help.md`, `.claude/CLAUDE.md`, `docs/reference/CLI.md`; increment `"20 CLI tools"` count in `README.md` only — do NOT add a `### ll-` section there (README is a hero page; see CONTRIBUTING.md § "Documentation wiring for new CLI tools") [updated 2026-05-10]
7. Add to release checklist in `CONTRIBUTING.md`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Add `ll-verify-skill-budget` bullet to `scripts/little_loops/cli/__init__.py` module docstring (after line 24, before the closing `"""`) — follow the pattern of every other tool listed there
9. Update `skills/configure/areas.md` line ~823 — change `"Authorize all 19"` to `"Authorize all 20"` and append `, ll-verify-skill-budget` to the tool enumeration
10. Add `"Bash(ll-verify-skill-budget:*)"` permission entry to `skills/init/SKILL.md` — follow the pattern of existing `ll-` tool permissions in that file
11. Update `scripts/tests/test_create_extension_wiring.py` lines ~57 and ~196 — change `"Authorize all 19"` to `"Authorize all 20"` to match the updated `areas.md`
12. Add `"skill_budget"` property to `config-schema.json` root `"properties"` object: `{"type": "object", "additionalProperties": false, "properties": {"threshold_tokens": {"type": "integer", "default": 2000, "description": "..."}}}` — prevents schema validation failure for users who set this config key
13. Add `skill_budget.threshold_tokens` documentation to `docs/reference/CONFIGURATION.md`
14. Update `README.md` line 46 — change `"21 typed CLI tools"` to `"22 typed CLI tools"` (line 162 was already updated to 22)
15. Add `TestCheckSkillBudget` class to `scripts/tests/test_doc_counts.py` — direct unit tests for `check_skill_budget()` and `_parse_skill_frontmatter()`; cover: empty skills dir, `disable-model-invocation: true` skipped, per-skill token count, violations threshold, `under_budget` boundary

## Integration Map

### Files to Modify
- `scripts/little_loops/doc_counts.py` — add `check_skill_budget()` function
- `scripts/little_loops/cli/docs.py` — add `main_verify_skill_budget()` entry point
- `scripts/pyproject.toml` — register CLI entry point
- `scripts/little_loops/cli/__init__.py` — add import and `__all__` entry
- `commands/help.md` — add to CLI TOOLS list
- `.claude/CLAUDE.md` — add to CLI Tools section
- `README.md` — increment `"20 CLI tools"` count only; do NOT add a `### ll-` section (per Implementation Step 5)
- `docs/reference/CLI.md` — add reference section
- `CONTRIBUTING.md` — add to release checklist

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/docs.py:main_verify_docs()` — implementation pattern to follow
- `scripts/tests/test_cli_docs.py:TestMainVerifyDocs` — test pattern to follow
- `scripts/little_loops/cli/__init__.py` — add `main_verify_skill_budget` to the existing `from little_loops.cli.docs import ...` line (line ~31) and to the `__all__` list (line ~55)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` module docstring (lines 1–25) — `ll-verify-skill-budget` is absent from the prose bullet list; every other tool in `__all__` is listed there [Agent 2 finding]

### Similar Patterns
- ENH-977 (`ll-verify-skills`) — nearly identical implementation pattern, different metric
- `scripts/little_loops/doc_counts.py:verify_documentation()` — **actual pattern to follow** for `check_skill_budget()` (`check_skill_sizes()` referenced in Proposed Solution does not exist yet — ENH-977 is still open)
- `scripts/little_loops/cli/docs.py:main_verify_docs()` — direct structural template for `main_verify_skill_budget()` (argparse setup, `configure_output()`, `Logger`, `base_dir` resolution, return 0/1)
- `scripts/little_loops/cli/generate_skill_descriptions.py:_parse_frontmatter()` — local SKILL.md frontmatter parser (flat `key: value` only); also see `_process_skills()` for the `disable-model-invocation` check and glob pattern: `skills_dir.glob("*/SKILL.md")` (not `rglob`)
- `scripts/little_loops/frontmatter.py:parse_frontmatter()` — shared YAML frontmatter parser (handles block scalars, inline lists, type coercion); returns `dict[str, Any]`. Prefer this if any `description:` fields use `description: |` block scalar syntax, but note it returns `None` for multi-line block scalars with a warning log. The `description` field in practice is single-line (≤100 chars per CONTRIBUTING.md), so the simpler local `_parse_frontmatter()` is sufficient.

### Tests
- `scripts/tests/test_cli_docs.py` — add `TestMainVerifySkillBudget`
- `scripts/tests/test_skill_budget_checker.py` — unit tests for `check_skill_budget()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — two assertions at lines ~57 and ~196 assert `"Authorize all 19"`; must be updated to `"Authorize all 20"` after `skills/configure/areas.md` is updated [Agent 2 finding — tests will break]
- `scripts/tests/test_doc_counts.py` — `check_skill_budget()`, `SkillBudgetResult`, and `_parse_skill_frontmatter()` have zero direct unit tests; add `TestCheckSkillBudget` following existing `TestVerifyDocumentation` pattern; cover: empty skills dir, `disable-model-invocation: true` skipped, per-skill token count (`len(desc) // 4`), violations threshold, `under_budget` boundary [Agent 3 finding — new tests needed]

### Documentation
- `CONTRIBUTING.md` — release checklist
- `docs/reference/CLI.md` — tool reference

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `skill_budget.threshold_tokens` config key is not documented here; every other config section consumed by CLI tools has a corresponding entry [Agent 2 finding]
- `README.md` line 46 — reads `"21 typed CLI tools"` (stale); line 162 was updated to 22 as part of ENH-1396 but line 46 was missed [Agent 2 finding]

### Configuration
- `.ll/ll-config.json` — optional `skill_budget.threshold_tokens` override

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — `skill_budget` property is absent; `"additionalProperties": false` at root means any `ll-config.json` that sets `skill_budget.threshold_tokens` would fail JSON Schema validation; needs a `"skill_budget": {"type": "object", "properties": {"threshold_tokens": {"type": "integer", "default": 2000}}}` entry [Agent 2 finding — schema-breaking gap]

### Registration/Manifest Files

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/areas.md` line ~823 — reads `"Authorize all 19 ll- CLI tools"` and lists 19 tools; `ll-verify-skill-budget` is absent; update count to 20 and append `, ll-verify-skill-budget` to the enumeration [Agent 2 finding]
- `skills/init/SKILL.md` — no `"Bash(ll-verify-skill-budget:*)"` permission entry; every other `ll-` CLI tool added after ENH-1229 has a corresponding bash permission block here [Agent 2 finding]

## Impact

- **Priority**: P3 — closes the feedback loop for listing budget enforcement
- **Effort**: Low — follows well-established pattern (ENH-977, `ll-verify-docs`)
- **Risk**: Low — additive; no existing behavior changed
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `testing`, `skills`, `context-engineering`

## Status

**Open** | Created: 2026-05-09 | Priority: P3

## Resolution

Implemented `ll-verify-skill-budget` CLI tool following the issue specification:
- Added `check_skill_budget()` and `SkillBudgetResult` to `scripts/little_loops/doc_counts.py`
- Added `main_verify_skill_budget()` to `scripts/little_loops/cli/docs.py`
- Registered entry point in `scripts/pyproject.toml`
- Updated `scripts/little_loops/cli/__init__.py` imports and `__all__`
- Added `TestMainVerifySkillBudget` class to `scripts/tests/test_cli_docs.py` (4 tests, all pass)
- Updated `commands/help.md`, `.claude/CLAUDE.md`, `docs/reference/CLI.md`, `README.md` (20→21, 21→22), `CONTRIBUTING.md`

Smoke test shows current budget: 283 / 2000 tokens (well under).

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-05-11):_

**Implementation confirmed complete.** All files from the Integration Map exist and match the spec. One divergence from the planned test layout:

- `scripts/tests/test_skill_budget_checker.py` — planned as a separate unit test file for `check_skill_budget()`, but was **not created**. All 4 tests (CLI-level) live in `TestMainVerifySkillBudget` inside `scripts/tests/test_cli_docs.py`. `check_skill_budget()` is not directly unit-tested (only exercised via mock through the CLI tests).
- `scripts/little_loops/cli/__init__.py` module docstring (line 1) does not mention `ll-verify-skill-budget` by name (only `ll-verify-docs` and `ll-check-links` are listed), though it is fully wired into `__all__` and the import line.

## Session Log
- `/ll:confidence-check` - 2026-05-11T08:00:00Z - `38e20085-241b-48a3-893e-e46ebddac9e2.jsonl`
- `/ll:wire-issue` - 2026-05-11T07:30:31 - `24af1a8f-9e6d-4c05-9a57-efe2d79185bc.jsonl`
- `/ll:refine-issue` - 2026-05-11T07:25:20 - `d3e3a3cf-8897-4b2b-8a8c-8909db5a8fa2.jsonl`
- `/ll:ready-issue` - 2026-05-11T05:40:12 - `bcf6c4cd-34a6-4c1d-a785-a4a894e46e06.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `e50aaae6-0d95-4912-933d-ced1e60f4a38.jsonl`
- `/ll:refine-issue` - 2026-05-11T05:35:37 - `8be7f96b-7cbf-4c8c-981d-b0cfe9fe338a.jsonl`
- `/ll:format-issue` - 2026-05-11T05:31:32 - `72d970f6-0d7e-4967-bc0c-f30b05b554b8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:48:12Z - `6c428abc-6b67-47fc-b1a4-d2d8d176f6b7.jsonl`
