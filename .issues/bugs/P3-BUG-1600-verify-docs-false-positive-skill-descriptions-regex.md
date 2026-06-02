---
id: BUG-1600
type: BUG
priority: P3
status: done
title: 'll-verify-docs false positive: ''0 skill descriptions dropped'' matched as
  skill count'
created: 2026-05-17
completed_at: 2026-05-18T07:22:03Z
relates_to: ENH-977
decision_needed: false
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

## Summary

`ll-verify-docs` reports a spurious mismatch:

```
skills: documented=0, actual=30
  at CONTRIBUTING.md:540
```

The line at CONTRIBUTING.md:540 reads:

```
Then run `/doctor` and verify "0 skill descriptions dropped".
```

The phrase `"0 skill descriptions dropped"` is quoting `/doctor` output, not documenting a skill count. However, the regex in `doc_counts.py` is too broad and matches it as a skills count.

## Current Behavior

`ll-verify-docs` exits with a skills mismatch error: `skills: documented=0, actual=30 at CONTRIBUTING.md:540`. The line at CONTRIBUTING.md:540 reads `verify "0 skill descriptions dropped"` — a quoted `/doctor` output string, not a skill count.

## Expected Behavior

`ll-verify-docs` exits 0 on the current codebase with no false-positive mismatch. The phrase `"0 skill descriptions dropped"` is not treated as a documented skill count.

## Steps to Reproduce

1. Run `ll-verify-docs` on the repository
2. Observe: `skills: documented=0, actual=30` mismatch reported at CONTRIBUTING.md:540
3. Note: CONTRIBUTING.md:540 contains `verify "0 skill descriptions dropped"` — this is quoting CLI output, not documenting a skill count

## Root Cause

In `scripts/little_loops/doc_counts.py`, the skills pattern is:

```python
pattern = r"(\d+)\s+\w*\s*skills?"
```

This matches `0 skill` in `"0 skill descriptions dropped"` because:
- `(\d+)` = `0`
- `\s+` = ` `
- `\w*` = `` (zero chars)
- `\s*` = `` (zero chars)
- `skills?` = `skill`

## Proposed Solution

Narrow the pattern to avoid matching when followed by ` descriptions` using a negative lookahead. Append `(?!\s+description)` after `skills?` at both affected sites:

- `extract_count_from_line()`: `r"(\d+)\s+\w*\s*skills?(?!\s+description)"`
- `fix_counts()`: `r"(\d+)(\s+\w*\s*skills?(?!\s+description))"`

Also add a test case to `scripts/tests/test_doc_counts.py` covering this edge case.

## Acceptance Criteria

- [ ] `ll-verify-docs` returns exit code 0 on the current codebase with no changes to CONTRIBUTING.md
- [ ] `"0 skill descriptions dropped"` no longer matches as a skills count in the regex
- [ ] New test covers this edge case in `test_doc_counts.py`

## Implementation Steps

1. Narrow skills regex in `scripts/little_loops/doc_counts.py:108` (`extract_count_from_line`) — add negative lookahead `(?!\s+description)` after `skills?`
2. Apply the same fix in `doc_counts.py:365` (`fix_counts`) — pattern `r"(\d+)(\s+\w*\s*skills?)"` → `r"(\d+)(\s+\w*\s*skills?(?!\s+description))"` to prevent `--fix` from rewriting the false-positive line
3. Add regression test in `scripts/tests/test_doc_counts.py` — class `TestExtractCountFromLine`, new method `test_no_match_skill_descriptions_phrase` asserting `extract_count_from_line('verify "0 skill descriptions dropped"', "skills") is None`
4. Run `ll-verify-docs` to confirm exit code 0 on the current codebase

## Integration Map

### Files to Modify
- `scripts/little_loops/doc_counts.py` — two sites need the same lookahead fix:
  - `extract_count_from_line()` at line 108: pattern `r"(\d+)\s+\w*\s*skills?"` → add `(?!\s+description)` after `skills?`
  - `fix_counts()` at line 365: pattern `r"(\d+)(\s+\w*\s*skills?)"` → add `(?!\s+description)` inside group 2, giving `r"(\d+)(\s+\w*\s*skills?(?!\s+description))"` — otherwise `fix_counts` would attempt to rewrite the false-positive line when `--fix` is passed

### Tests
- `scripts/tests/test_doc_counts.py` — class `TestExtractCountFromLine`; add a new method following the existing one-method-per-variant style:
  ```python
  def test_no_match_skill_descriptions_phrase(self) -> None:
      """Do not match '0 skill descriptions dropped' (quoted CLI output, not a count)."""
      count = extract_count_from_line('verify "0 skill descriptions dropped"', "skills")
      assert count is None
  ```
- `scripts/tests/test_cli_docs.py` — class `TestMainVerifyDocs`; patches `verify_documentation` and `fix_counts` at module level — all 8 methods are fully mocked and will not break due to the regex change; no update needed [Agent 1 + Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- **Optional**: add `TestFixCounts.test_fix_skills_count` to `scripts/tests/test_doc_counts.py` — the `fix_counts()` skills-category branch (`doc_counts.py:365`) has zero existing test coverage; a skills-path test would cover the second regex fix site [Agent 3 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — re-exports `main_verify_docs` and `main_verify_skill_budget` in `__all__`; no changes needed [Agent 1 finding]

### Entry Point / Data Flow
- `scripts/little_loops/cli/docs.py` — `main_verify_docs()` is the CLI entry point (registered in `scripts/pyproject.toml:59` as `ll-verify-docs`)
- Data flow: `main_verify_docs()` → `verify_documentation()` → `extract_count_from_line()` per line per category → mismatch recorded → exit code 1

### Documentation (no changes needed)
- `CONTRIBUTING.md:540` — triggering line; do **not** change it

### Side Effects

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/docs-sync.yaml` — invokes `ll-verify-docs 2>&1` as a shell action and routes on exit code; the bug fix is a behavioral change here: runs that previously false-positived (exit 1 → `fix_docs` state) will now exit 0 and reach `done` correctly; no YAML change needed [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`fix_counts()` also affected**: The parallel pattern in `fix_counts()` (`doc_counts.py:365`) shares the same false-positive surface. If a mismatch from `extract_count_from_line` is recorded and `--fix` is passed, `fix_counts` would attempt to rewrite the CONTRIBUTING.md line. Both patterns must be updated together.
- **No other category has this issue**: The `\w*` wildcard causes false positives for `skills` because the singular form `skill` is also matched (`skills?`). Other categories (`commands`, `agents`, `loops`) do not have a documented false-positive phrase in the three scanned doc files.
- **Existing true-positive lines** that must continue matching after the fix: `README.md:165` (`30 skills`), `CONTRIBUTING.md:123` (`30 skill definitions`), `docs/ARCHITECTURE.md:26` (`30 composable skills`), `docs/ARCHITECTURE.md:113` (`30 skill definitions`) — the negative lookahead only blocks matches followed by `\s+description`, so these are unaffected.

## Impact

- **Priority**: P3 — causes false-positive errors in CI/tooling without breaking core functionality
- **Effort**: Low — one-line regex change plus one test case
- **Risk**: Low — narrowing a regex; covered by new test
- **Breaking Change**: No

## Labels

`bug`, `doc-counts`, `verify-docs`, `regex`

## Verification Notes

**Verdict**: VALID — Verified 2026-05-17

- `scripts/little_loops/doc_counts.py:108` — `pattern = r"(\d+)\s+\w*\s*skills?"` confirmed; tested against `"0 skill descriptions dropped"` → matches `"0 skill"` ✓
- `CONTRIBUTING.md:540` — contains the triggering text `verify "0 skill descriptions dropped"` ✓
- No fix applied; regex still too broad.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-17): ENH-977 also modifies `scripts/little_loops/doc_counts.py` (adds `check_skill_sizes()` function). Implement this bug fix (narrowing the skills regex at line 108) **before** ENH-977 to avoid a merge conflict on the same file. Alternatively, include this fix directly in ENH-977's PR.

## Session Log
- `/ll:ready-issue` - 2026-05-18T07:20:44 - `27851837-687d-4413-ab7a-bf5b15c516ec.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `faa98c32-f874-4f71-8717-fd29fd021282.jsonl`
- `/ll:decide-issue` - 2026-05-18T07:17:36 - `06767c12-f209-4a28-9786-fea902b59483.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `4f4dbfca-d4ff-40ef-a840-91a7ad3c43cb.jsonl`
- `/ll:wire-issue` - 2026-05-18T07:13:14 - `60d6c813-e04e-431b-b96c-de1547be1411.jsonl`
- `/ll:refine-issue` - 2026-05-18T07:09:39 - `65a053f9-a36b-42c5-917a-55a8ed7240ed.jsonl`
- `/ll:format-issue` - 2026-05-18T05:16:02 - `fb7f2fc9-52f4-4d22-8182-c197fa8741c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-17T18:46:35 - `ebf7abce-1ef1-46c8-8cbc-56d9f857d730.jsonl`
- `/ll:verify-issues` - 2026-05-17T00:00:00 - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
