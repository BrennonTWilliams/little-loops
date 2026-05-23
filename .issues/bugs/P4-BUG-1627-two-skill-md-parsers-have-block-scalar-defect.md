---
captured_at: '2026-05-23T06:34:23Z'
completed_at: 2026-05-23T14:34:33Z
discovered_date: 2026-05-23
discovered_by: capture-issue
status: done
decision_needed: false
confidence_score: 100
outcome_confidence: 90
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1627: Two SKILL.md parsers in cli/ have block-scalar defect

## Summary

Two hand-rolled SKILL.md frontmatter parsers in `scripts/little_loops/cli/` exhibit the same block-scalar parsing defect that BUG-1616 fixed in `doc_counts.py`. For SKILL.md files whose frontmatter uses `description: |` (YAML block scalar), both parsers return the literal `"|"` string instead of the indented body content. This affects the same 6 bridge skills: `ll-loop-suggester`, `ll-manage-release`, `ll-open-pr`, `ll-review-sprint`, `ll-sync-issues`, `ll-tradeoff-review-issues`.

## Current Behavior

**Parser 1 — `scripts/little_loops/cli/action.py:31-46` `_read_skill_description()`**

```python
for line in frontmatter.splitlines():
    if line.startswith("description:"):
        return line[len("description:") :].strip().strip('"').strip("'")
return ""
```

For `description: |`, returns the literal `"|"`. Block-scalar body lines are never read. Affects `ll-action --list` output for the 6 skills above (description column shows `|`).

**Parser 2 — `scripts/little_loops/cli/generate_skill_descriptions.py:29-43` `_parse_frontmatter()`**

```python
for line in raw.splitlines():
    if ":" in line:
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip()
```

Character-for-character identical to the pre-fix defect in `doc_counts.py`. Downstream `_extract_trigger_keywords()` at line 46 then iterates `description.splitlines()` looking for `"Trigger keywords:"`. When `description = "|"`, no keywords are found and the LLM prompt is built with `Trigger keywords: (none)` — the regenerator silently drops the routing signal it was supposed to preserve.

## Steps to Reproduce

1. `ll-action --list` and observe the description column for `ll-loop-suggester` (and the other 5 bridge skills) — expect `|` instead of the real description.
2. Run `ll-generate-skill-descriptions --dry-run ll-tradeoff-review-issues` (or whatever the dry-run flag is) and inspect the prompt — `Trigger keywords:` will be `(none)` despite the file having a `Trigger keywords: ...` line in its block-scalar description body.

## Expected Behavior

Both parsers should resolve `description: |` to its multi-line string content, matching the behaviour of `_parse_skill_frontmatter()` in `scripts/little_loops/doc_counts.py:268-298` (fixed in BUG-1616) and `_extract_short_desc()` in `scripts/little_loops/cli/adapt_skills_for_codex.py:42-51`.

## Motivation

BUG-1616 fixed this defect class in one site (`doc_counts.py`) but deliberately scoped out the other two as Option C (rejected for diff size). Now that the fix pattern is established and proven, the remaining two sites should be brought in line so the codebase has one consistent way to read SKILL.md frontmatter. Leaving them broken means:

- `ll-action --list` shows garbage descriptions for 6 skills (cosmetic, but misleading to anyone using the listing).
- The next maintainer run of `ll-generate-skill-descriptions` will silently regenerate the 6 skills' descriptions without their trigger keywords — actively degrading the registry.

## Root Cause

- **File 1**: `scripts/little_loops/cli/action.py`
- **Anchor 1**: `function _read_skill_description()` (lines 31-46)
- **File 2**: `scripts/little_loops/cli/generate_skill_descriptions.py`
- **Anchor 2**: `function _parse_frontmatter()` (lines 29-43)
- **Cause**: hand-rolled line-based parsers that don't understand YAML block scalars (`|`, `>`).

## Proposed Solution

Consolidate the three sites (now two remaining + the already-fixed `doc_counts.py`) onto a single shared helper. Recommended location: extend `scripts/little_loops/frontmatter.py` with a new `parse_skill_frontmatter(text: str) -> dict[str, str]` function that mirrors the doc_counts implementation (yaml.safe_load with line-scan fallback for files with unquoted colons).

**Note on existing `frontmatter.py`**: the module already exports `parse_frontmatter()` (used by issue parsing) but that function deliberately drops block scalars (`scripts/little_loops/frontmatter.py:73-76` logs a warning and sets the value to `None`). It cannot be reused for skill frontmatter. A new, separate function is required — do not modify `parse_frontmatter()` behaviour or its callers will break on issue files containing block-scalar-looking content. Then:

- `scripts/little_loops/cli/action.py:31-46` — replace `_read_skill_description()` body with a call to the shared helper, return `fm.get("description", "")`.
- `scripts/little_loops/cli/generate_skill_descriptions.py:29-43` — replace `_parse_frontmatter()` with a call to the shared helper; preserve the `(fm, body)` return shape by computing body separately.
- `scripts/little_loops/doc_counts.py:268-298` — switch `_parse_skill_frontmatter` to delegate to the shared helper (optional cleanup; not required for the fix).

The consolidation approach is selected. The bug class has already proven it will recur (BUG-1616 fixed one site; leaving the others diverged invites the same drift). The Implementation Steps below assume this path.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/action.py` — `_read_skill_description()`
- `scripts/little_loops/cli/generate_skill_descriptions.py` — `_parse_frontmatter()`
- `scripts/little_loops/frontmatter.py` — add `parse_skill_frontmatter()` (if consolidating)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/action.py` — `_load_skills()` and the `ll-action --list` path consume `_read_skill_description()`.
- `scripts/little_loops/cli/generate_skill_descriptions.py` — `_extract_trigger_keywords()` (line 46), `_build_prompt()` (line 54), and the main regeneration loop consume `_parse_frontmatter()` output.

### Similar Patterns
- `scripts/little_loops/doc_counts.py:268-298` — reference implementation (yaml.safe_load + line-scan fallback).
- `scripts/little_loops/cli/adapt_skills_for_codex.py:42-51` — `_extract_short_desc()` (yaml.safe_load on the same fence layout).

### Tests
- `scripts/tests/test_action.py` — existing test module for `cli/action.py`; add a block-scalar SKILL.md fixture and assert `_read_skill_description()` (or `--list` output) returns the resolved body, not `|`.
- `scripts/tests/test_generate_skill_descriptions.py` — existing test module; add a block-scalar SKILL.md fixture and assert `_extract_trigger_keywords()` pulls the keyword line through `_parse_frontmatter()`.
- `scripts/tests/test_doc_counts.py` — reference for the existing block-scalar parsing tests on the `doc_counts._parse_skill_frontmatter` side (model new tests on these).
- `scripts/tests/test_frontmatter.py` — if `parse_skill_frontmatter()` lands in `frontmatter.py`, add unit tests here covering yaml.safe_load path, line-scan fallback, and block scalar resolution.

_Wiring pass added by `/ll:wire-issue`:_
- **BREAKAGE RISK** — `scripts/tests/test_generate_skill_descriptions.py` imports `_parse_frontmatter` directly at line 13 (`from little_loops.cli.generate_skill_descriptions import _parse_frontmatter`). `TestParseFrontmatter` (3 tests) will raise `ImportError` at collection time if `_parse_frontmatter` is deleted rather than kept as a thin wrapper. Implementation Step 3 must either (a) keep `_parse_frontmatter` as a delegating wrapper preserving the `(fm, body)` return shape, or (b) update the import in `test_generate_skill_descriptions.py` to use `parse_skill_frontmatter` directly.
- `scripts/tests/test_adapt_skills_for_codex.py` — reference pattern only; `_make_skill_block_scalar` fixture and `TestExtractShortDesc.test_block_scalar_returns_first_line` show a third established block-scalar SKILL.md test pattern to follow.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the "Public Functions" table under `## little_loops.frontmatter` lists only `parse_frontmatter`, `strip_frontmatter`, `update_frontmatter`. Adding `parse_skill_frontmatter()` as a new public export requires an entry in that table and a signature subsection (optional if treating as a private helper, but the function will be imported cross-module).

### Configuration
- N/A

## Implementation Steps

1. Add (or extend) `parse_skill_frontmatter()` in `scripts/little_loops/frontmatter.py` mirroring `doc_counts._parse_skill_frontmatter` (yaml.safe_load with line-scan fallback for unquoted-colon edge cases like `manage-issue`, `review-loop`, `update-docs`).
2. Replace `_read_skill_description()` in `cli/action.py` with a call to the shared helper.
3. Replace `_parse_frontmatter()` in `cli/generate_skill_descriptions.py` with a call to the shared helper (preserving the `(fm, body)` return shape).
4. Optionally update `doc_counts._parse_skill_frontmatter` to delegate to the shared helper for full deduplication.
5. Add block-scalar regression tests for both `cli/action.py` and `cli/generate_skill_descriptions.py`.
6. Run `python -m pytest scripts/tests/ -v` and `ll-verify-skill-budget`; manually run `ll-action --list` to confirm the 6 skills now show real descriptions.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Step 3 clarification** — When replacing `_parse_frontmatter()` in `generate_skill_descriptions.py`, keep the name as a delegating wrapper (do NOT delete it) to avoid breaking the 3 direct-import test methods in `TestParseFrontmatter`. The wrapper must preserve the `(fm, body)` tuple return shape:
   ```python
   def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
       from little_loops.frontmatter import parse_skill_frontmatter
       fm = parse_skill_frontmatter(text)
       body = text.split("---", 2)[-1] if text.startswith("---") else text
       return fm, body
   ```
8. Update `docs/reference/API.md` — add `parse_skill_frontmatter(text: str) -> dict[str, str]` to the public functions table under `## little_loops.frontmatter`.

## Impact

- **Priority**: P4 — `ll-action --list` is cosmetic; `ll-generate-skill-descriptions` is a release utility run rarely. Not blocking.
- **Effort**: Small — two functions to replace + tests.
- **Risk**: Low — pattern proven in BUG-1616; shared helper reduces future drift.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `skills`, `context-engineering`, `parsers`, `follow-up`

## Session Log
- `/ll:manage-issue` - 2026-05-23T14:34:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3fa20f09-bdfd-4103-86dd-897412e8c348.jsonl`
- `/ll:ready-issue` - 2026-05-23T14:28:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75c85691-6722-4398-b538-7e3fe5f57a86.jsonl`
- `/ll:confidence-check` - 2026-05-23T06:47:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/696d9d4f-8e3f-43ce-8b7c-609c2ae996dc.jsonl`
- `/ll:decide-issue` - 2026-05-23T14:25:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/884928f1-21ad-4802-bc1a-9e170897c271.jsonl`
- `/ll:confidence-check` - 2026-05-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0584b011-1fbb-4faf-bb4e-9923d2c17cc3.jsonl`
- `/ll:wire-issue` - 2026-05-23T14:21:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e2855714-fe05-485e-96a0-170725dc996a.jsonl`
- `/ll:refine-issue` - 2026-05-23T14:16:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a77c7853-c503-44be-ac01-cc84835fba0c.jsonl`
- `/ll:format-issue` - 2026-05-23T06:37:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/40f5dba3-2577-490a-b7d6-624533fd5680.jsonl`
- `/ll:capture-issue` - 2026-05-23T06:34:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/111182d8-94d8-4805-a59e-95797a4cc7e6.jsonl`

## Status

**Done** | Created: 2026-05-23 | Completed: 2026-05-23 | Priority: P4

## Resolution

Consolidated SKILL.md frontmatter parsing onto a new shared helper
`little_loops.frontmatter.parse_skill_frontmatter()` that mirrors the
post-BUG-1616 implementation in `doc_counts.py` (yaml.safe_load with
line-scan fallback for unquoted-colon edge cases).

- `scripts/little_loops/cli/action.py:31` — `_read_skill_description()`
  now delegates to the shared helper.
- `scripts/little_loops/cli/generate_skill_descriptions.py:29` —
  `_parse_frontmatter()` kept as a thin wrapper (preserving the
  `(fm, body)` return shape required by the 3 direct-import tests in
  `TestParseFrontmatter`).
- `scripts/little_loops/frontmatter.py` — new public
  `parse_skill_frontmatter()` function.
- `docs/reference/API.md` — added new function to the public-functions
  table under `## little_loops.frontmatter` with signature/example.
- Regression tests added in `test_frontmatter.py`,
  `test_action.py`, and `test_generate_skill_descriptions.py`
  asserting block-scalar resolution (and, for the generator path, that
  `_extract_trigger_keywords()` now finds the line through the wrapper).

Verification: `python -m pytest scripts/tests/` — 7372 passed.
`ruff check scripts/little_loops/frontmatter.py scripts/little_loops/cli/{action,generate_skill_descriptions}.py` — clean.
`ll-action list` confirms the 6 bridge skills
(`ll-loop-suggester`, `ll-manage-release`, `ll-open-pr`,
`ll-review-sprint`, `ll-sync-issues`, `ll-tradeoff-review-issues`)
now report real descriptions instead of the literal `"|"`.
`ll-verify-skill-budget` — under budget (1262/2000).

`doc_counts._parse_skill_frontmatter` left in place (optional cleanup,
not required for the fix; switching it to delegate would broaden the
diff without changing behaviour).
