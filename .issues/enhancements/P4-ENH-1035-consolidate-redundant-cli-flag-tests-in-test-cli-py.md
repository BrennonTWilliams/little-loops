---
discovered_date: 2026-04-11
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# ENH-1035: Consolidate Redundant CLI Flag Tests in test_cli.py

## Summary

`test_cli.py` has ~24 redundant test pairs where every CLI flag is tested twice — once as `test_<flag>_flag_long` and once as `test_<flag>_flag_short`. Argparse handles both forms identically; testing both adds no value. Consolidate these pairs using `@pytest.mark.parametrize` or remove the `_short` variants.

## Current Behavior

Every CLI flag has two nearly identical test functions:
- `test_<flag>_flag_long` — tests `--flag`
- `test_<flag>_flag_short` — tests `-f`

Argparse maps both forms to the same attribute; neither test exercises custom logic.

## Expected Behavior

Each flag tested once (or via a single parametrized test covering both forms). ~24 tests reduced to ~12, with no loss of behavioral coverage.

## Motivation

These tests inflate the test count without exercising any real logic. They test Python's argparse library, not our code. Removing them makes the suite faster and easier to reason about.

## Proposed Solution

Option A (preferred): Convert pairs to a single `@pytest.mark.parametrize("flag", ["--verbose", "-v"])` test.
Option B: Delete the `_short` variant (keeping `_long` which is more readable) for each pair.

## Integration Map

### Files to Modify
- `scripts/tests/test_cli.py`

### Dependent Files (Callers/Importers)
- N/A — test-only change

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_cli.py` — the file being modified

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/test-quality-audit.md:9-13` — test count table (`~4,061` total, `87` files) becomes stale; this issue removes ~12 tests from `test_cli.py` [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact pairs to consolidate (12 pairs across 2 test classes):**

`class TestAutoArgumentParsing` (ll-auto parser):
- L47 `test_resume_flag_long` / L52 `test_resume_flag_short` → `["--resume", "-r"]`
- L57 `test_dry_run_flag_long` / L62 `test_dry_run_flag_short` → `["--dry-run", "-n"]`
- L67 `test_max_issues_long` / L72 `test_max_issues_short` → `["--max-issues", "-m"]`
- L77 `test_category_filter_long` / L82 `test_category_filter_short` → `["--category", "-c"]`

`class TestParallelArgumentParsing` (ll-parallel parser):
- L157 `test_workers_long` / L162 `test_workers_short` → `["--workers", "-w"]`
- L167 `test_priority_filter_long` / L172 `test_priority_filter_short` → `["--priority", "-p"]`
- L177 `test_max_issues_long` / L182 `test_max_issues_short` → `["--max-issues", "-m"]`
- L192 `test_dry_run_flag_long` / L197 `test_dry_run_flag_short` → `["--dry-run", "-n"]`
- L202 `test_resume_flag_long` / L207 `test_resume_flag_short` → `["--resume", "-r"]`
- L212 `test_timeout_long` / L217 `test_timeout_short` → `["--timeout", "-t"]`
- L222 `test_quiet_flag_long` / L227 `test_quiet_flag_short` → `["--quiet", "-q"]`
- L232 `test_cleanup_flag_long` / L237 `test_cleanup_flag_short` → `["--cleanup", "-c"]`

**Tests to preserve (not pairs, exercise real behavior or combinations):**
- L38 `test_default_args`, L92 `test_combined_args`, L112 `test_combined_short_args` (TestAuto)
- L87 `test_config_path` (TestAuto) — single flag, no short form
- L141 `test_default_args`, L257 `test_combined_args` (TestParallel)
- L187 `test_worktree_base`, L242 `test_stream_output_flag`, L247 `test_show_model_flag`, L252 `test_config_path` (TestParallel) — flags without short aliases

## Implementation Steps

1. Identify all `test_<flag>_flag_long` / `test_<flag>_flag_short` pairs (~12 pairs)
2. For each pair, replace with a single parametrized test covering both flag forms
3. Run `python -m pytest scripts/tests/test_cli.py -v --tb=short` and confirm all pass
4. Verify test count drops by ~12

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete parametrize template for the actual test code:_

For boolean flags (e.g. `--resume`/`-r` in `TestAutoArgumentParsing`):
```python
@pytest.mark.parametrize("flag", ["--resume", "-r"])
def test_resume_flag(self, flag: str) -> None:
    """--resume / -r sets resume=True."""
    args = self._parse_auto_args([flag])
    assert args.resume is True
```

For value-taking flags (e.g. `--max-issues`/`-m` in `TestAutoArgumentParsing`):
```python
@pytest.mark.parametrize("flag,value,expected", [("--max-issues", "5", 5), ("-m", "10", 10)])
def test_max_issues(self, flag: str, value: str, expected: int) -> None:
    """--max-issues / -m sets issue limit."""
    args = self._parse_auto_args([flag, value])
    assert args.max_issues == expected
```

Apply the same pattern within `TestParallelArgumentParsing` for its 8 pairs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/test-quality-audit.md:9-13` — decrement the total test count by ~12 to reflect removal of consolidated pairs

## Scope Boundaries

- **In scope**: Consolidating `test_<flag>_flag_long` / `test_<flag>_flag_short` pairs in `scripts/tests/test_cli.py` using `@pytest.mark.parametrize`
- **Out of scope**: Changes to production code, changes to other test files, removing any flag tests that exercise custom argparse logic beyond default behavior

## Impact

- **Priority**: P4 - Test quality cleanup, no behavioral change
- **Effort**: Small - Mechanical refactor within one file
- **Risk**: Low - Tests only; no production code changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`test-quality`, `test_cli`, `captured`

## Status

**Open** | Created: 2026-04-11 | Priority: P4

---

## Session Log
- `/ll:wire-issue` - 2026-04-11T20:12:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a526cc2e-06c1-44e3-add0-5ba3cb7b1190.jsonl`
- `/ll:refine-issue` - 2026-04-11T20:08:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2f0bc40-5233-4c1b-a17d-6bd5566483a9.jsonl`
- `/ll:format-issue` - 2026-04-11T20:03:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da64ad23-684f-4724-8a57-4063931ce01c.jsonl`
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9439fb7-57cc-417c-9114-6eea87ed8705.jsonl`
- `/ll:confidence-check` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c5c369e-95b9-4fe0-a53f-b4bd65093912.jsonl`
