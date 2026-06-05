---
id: ENH-1963
type: ENH
priority: P2
status: open
captured_at: "2026-06-05T21:16:36Z"
discovered_date: 2026-06-05
discovered_by: capture-issue
labels:
  - test-quality
  - captured
decision_needed: true
parent: EPIC-1967
---

# ENH-1963: Audit and Consolidate Doc-Wiring Tests

## Summary

59 doc-wiring test files (23.4% of the test suite) verify that strings appear in `.md` documentation files. These tests exercise zero application code — they inflate the test count, create a false sense of thoroughness, and add maintenance burden. Consolidate them into ≤5 parametrized test files or replace them with a lint rule.

## Context

Identified during a comprehensive test suite audit conducted by 3 parallel Explore agents (test structure, coverage gaps, quality patterns) and synthesized by a Plan agent. The audit found that nearly a quarter of all test files are doc-wiring tests that don't exercise any application logic.

## Current Behavior

- 59 test files (confirmed) follow the `test_*_doc_wiring.py` (50 files) or `test_*_wiring.py` (9 additional) naming pattern — see Integration Map for complete inventory
- Each file uses string assertions (`content = PATH.read_text()` / `assert "string" in content`) to verify specific text appears in `.md` docs; estimated ~542 `read_text()` calls across all files
- These tests pass if a string is present, fail if someone rewords a doc — producing noisy failures unrelated to code correctness
- They count toward the test file count and runtime (≈23% of test files) but do NOT inflate `--cov=little_loops` coverage metrics: `scripts/pyproject.toml` `[tool.coverage.run]` already has `omit = ["*/tests/*"]`, and doc-wiring tests import zero application code (only `from pathlib import Path`)
- Zero shared fixtures or helpers between doc-wiring files — every file independently computes `PROJECT_ROOT = Path(__file__).parent.parent.parent` and its own path constants

## Expected Behavior

- Doc-wiring verification is consolidated into ≤5 parametrized test files (e.g., one per document category)
- OR replaced with a lint rule / markdown link checker that runs separately from the unit test suite
- Doc string verification does not inflate test counts or coverage metrics
- Real test coverage metrics are honest about application code coverage

## Motivation

Doc-wiring tests create two problems simultaneously: they add maintenance toil (updating string assertions when docs change) AND they mask real test gaps by inflating the test count. Teams see "9,968 tests passing" and assume comprehensive coverage, when nearly 1/4 of those tests don't exercise any application code.

- **Maintenance burden**: 59 files that break on any doc rewording create churn unrelated to code quality
- **False confidence**: 23.4% of the test suite verifying strings in docs creates an inflated sense of test thoroughness
- **Coverage dishonesty**: The 90% line coverage figure includes these tests, hiding real gaps in application code coverage
- **CI time**: Running 59 doc-wiring test files consumes CI minutes with zero code-quality signal

## Proposed Solution

Three options identified in the audit:

**Option A: Parametrize (recommended)**
Consolidate into ≤5 parametrized test files that use a data-driven approach — e.g., a single `test_doc_wiring.py` with `@pytest.mark.parametrize` across doc/code pairs.

**Option B: Lint rule replacement**
Replace most doc-wiring tests with a markdown link checker (`ll-check-links` already exists) plus a simple pattern checker. Keep only integration-critical doc assertions as tests.

**Option C: Separate test suite**
Move doc-wiring tests to a separate `tests/doc_wiring/` directory excluded from coverage and run them as a separate CI job.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Uniform pattern across all 59 files:**
- 100% uniform imports: only `from __future__ import annotations` and `from pathlib import Path` — zero `little_loops` imports
- 100% uniform project root resolution: `PROJECT_ROOT = Path(__file__).parent.parent.parent`
- 100% uniform assertion pattern: `content = PATH.read_text()` / `assert "string" in content` (80% simple; 20% region-extraction with `str.find` boundaries)
- Each file has 3–12 test methods, averaging ~10; estimated ~542 `read_text()` calls total
- No shared fixtures or helpers between doc-wiring files — every file independently computes its own path constants

**Coverage already excludes tests:** `scripts/pyproject.toml` `[tool.coverage.run]` has `omit = ["*/tests/*"]`, meaning doc-wiring tests (in `scripts/tests/`) do NOT contribute to `--cov=little_loops` metrics. The 90% coverage figure measures `little_loops/` application code only. The issue's claim that doc-wiring tests inflate coverage metrics is incorrect — they only inflate the raw test count and runtime.

**No CI exists:** Confirmed no `.github/workflows/`, `Makefile`, or `tox.ini` (per `docs/development/TESTING.md:921-927`). All testing is local-only via `pytest scripts/tests/`. This reduces Option C's urgency (no CI pipeline to separate).

**`ll-check-links` has a testable module API** (`scripts/little_loops/link_checker.py`):
- Pure functions: `extract_links_from_markdown()`, `is_internal_reference()`, `should_ignore_url()`, `format_result_text()`
- CLI wrapper at `scripts/little_loops/cli/docs.py:313` in `main_check_links()` — thin `argparse` wrapper
- Existing tests at `scripts/tests/test_link_checker.py` test the module API directly, not through CLI
- **Gap**: `ll-check-links` validates URL reachability, NOT arbitrary string presence. To replace doc-wiring string-presence assertions (Option B), a new check would need to be added (e.g., keyword/section presence verification)

**20 test files already use `@pytest.mark.parametrize`** — strong precedent for Option A:
- `test_frontmatter.py:34` — `@pytest.mark.parametrize("issue_type", ["BUG", "FEAT", "ENH", "EPIC"])` (simple value lists)
- `test_fsm_evaluators.py:54` — heavily parametrized evaluator tests (complex tuple data)
- `test_cli.py:47` — parametrized CLI flag tests (flag/value pairs)
- Consolidation pattern: define a data structure of `(doc_path, string, message)` tuples, iterate via `@pytest.mark.parametrize`

**Test directory is flat** — `scripts/tests/` has no subdirectories. All 59 wiring files are siblings to ~250 other test files. Creating a `tests/doc_wiring/` subdirectory (Option C) would be the first categorized subdirectory.

## Success Metrics

- **Before**: 59 doc-wiring test files, ~23% of test suite, ~542 `read_text()` calls, zero shared fixtures
- **Target**: ≤5 parametrized files or a lint rule, ≤5% of test suite, shared fixtures for doc path resolution
- **Coverage impact**: Minimal — `pyproject.toml` already excludes `*/tests/*` from `--cov=little_loops`; doc-wiring tests import zero application code. Any coverage metric change would be from removing side-effect coverage (if any), not direct test coverage.
- **Test execution time**: ≥30s reduction from eliminating ~542 redundant `Path.read_text()` calls (consolidated shared reads) and 59 file-discovery/import overheads

## Scope Boundaries

- **In scope**: All test files matching `*doc_wiring*` or `*_wiring*` patterns
- **In scope**: Updating coverage configuration to exclude doc-wiring from code coverage metrics
- **Out of scope**: Structural skill tests (separate concern, tracked as ENH-1745)
- **Out of scope**: Changing what documentation says — only how we verify it

## API/Interface

No public API changes. Internal changes limited to:
- Test file reorganization (consolidation)
- Possible new pytest fixtures/parametrization helpers
- Coverage configuration (`pyproject.toml` or `.coveragerc`)

## Integration Map

### Files to Modify

**Doc-wiring test files (50 files matching `*doc_wiring*`):**
All located in `scripts/tests/`:

| File | Focus Area |
|------|-----------|
| `test_enh1115_doc_wiring.py` | ENH-1115 documentation wiring |
| `test_enh1130_doc_wiring.py` | ENH-1130 scratch-pad path wiring |
| `test_enh1138_doc_wiring.py` | ENH-1138 documentation wiring |
| `test_enh1146_doc_wiring.py` | ENH-1146 documentation wiring |
| `test_enh1268_doc_wiring.py` | ENH-1268 documentation wiring |
| `test_enh1299_doc_wiring.py` | ENH-1299 documentation wiring |
| `test_enh1341_doc_wiring.py` | ENH-1341 documentation wiring |
| `test_enh1345_doc_wiring.py` | ENH-1345 documentation wiring |
| `test_enh1362_doc_wiring.py` | ENH-1362 documentation wiring |
| `test_enh1363_doc_wiring.py` | ENH-1363 documentation wiring |
| `test_enh1401_doc_wiring.py` | ENH-1401 documentation wiring |
| `test_enh1402_doc_wiring.py` | ENH-1402 documentation wiring |
| `test_enh1403_doc_wiring.py` | ENH-1403 documentation wiring |
| `test_enh1404_doc_wiring.py` | ENH-1404 documentation wiring |
| `test_enh1421_doc_wiring.py` | ENH-1421 documentation wiring |
| `test_enh1428_doc_wiring.py` | ENH-1428 documentation wiring |
| `test_enh1433_doc_wiring.py` | ENH-1433 documentation wiring |
| `test_enh1442_doc_wiring.py` | ENH-1442 documentation wiring |
| `test_enh1443_doc_wiring.py` | ENH-1443 documentation wiring |
| `test_enh1495_doc_wiring.py` | ENH-1495 documentation wiring |
| `test_enh1550_doc_wiring.py` | ENH-1550 documentation wiring |
| `test_enh1557_doc_wiring.py` | ENH-1557 documentation wiring |
| `test_enh1639_doc_wiring.py` | ENH-1639 documentation wiring |
| `test_enh1704_doc_wiring.py` | ENH-1704 documentation wiring |
| `test_enh1734_doc_wiring.py` | ENH-1734 documentation wiring |
| `test_enh1753_doc_wiring.py` | ENH-1753 documentation wiring |
| `test_enh1846_doc_wiring.py` | ENH-1846 documentation wiring |
| `test_enh1847_doc_wiring.py` | ENH-1847 documentation wiring |
| `test_enh1859_doc_wiring.py` | ENH-1859 documentation wiring |
| `test_enh1866_doc_wiring.py` | ENH-1866 documentation wiring |
| `test_enh1888_doc_wiring.py` | ENH-1888 documentation wiring |
| `test_enh1905_doc_wiring.py` | ENH-1905 documentation wiring |
| `test_enh1912_doc_wiring.py` | ENH-1912 documentation wiring |
| `test_enh1916_doc_wiring.py` | ENH-1916 documentation wiring |
| `test_bug1649_doc_wiring.py` | BUG-1649 documentation wiring |
| `test_circuit_breaker_doc_wiring.py` | Circuit breaker API/skill wiring |
| `test_feat1172_doc_wiring.py` | FEAT-1172 documentation wiring |
| `test_feat1287_doc_wiring.py` | FEAT-1287 documentation wiring |
| `test_feat1407_doc_wiring.py` | FEAT-1407 documentation wiring |
| `test_feat1447_doc_wiring.py` | FEAT-1447 documentation wiring |
| `test_feat1457_doc_wiring.py` | FEAT-1457 documentation wiring |
| `test_feat1459_doc_wiring.py` | FEAT-1459 documentation wiring |
| `test_feat1462_doc_wiring.py` | FEAT-1462 documentation wiring |
| `test_feat1483_doc_wiring.py` | FEAT-1483 documentation wiring |
| `test_feat1504_doc_wiring.py` | ll-doctor wiring (FEAT-1504) |
| `test_feat1532_doc_wiring.py` | FEAT-1532 documentation wiring |
| `test_feat1625_doc_wiring.py` | ll-ctx-stats wiring (FEAT-1625) |
| `test_feat1856_doc_wiring.py` | FEAT-1856 documentation wiring |
| `test_feat1857_doc_wiring.py` | FEAT-1857 documentation wiring |
| `test_feat1894_doc_wiring.py` | FEAT-1894 documentation wiring |

**Non-doc wiring files (9 files matching `*_wiring.py` but not `*doc_wiring*`):**

| File | Focus Area |
|------|-----------|
| `test_create_extension_wiring.py` | ll-create-extension wiring (369 lines, largest) |
| `test_enh1836_configure_scaffold_wiring.py` | ENH-1836 configure scaffold wiring |
| `test_enh1884_analytics_wiring.py` | ENH-1884 analytics wiring |
| `test_feat1743_configure_wiring.py` | FEAT-1743 learning-tests configure wiring |
| `test_feat1743_init_wiring.py` | FEAT-1743 learning-tests init wiring |
| `test_feat1756_init_wiring.py` | FEAT-1756 design tokens init wiring |
| `test_feat1757_configure_wiring.py` | FEAT-1757 design tokens configure wiring |
| `test_feat1758_docs_wiring.py` | FEAT-1758 design tokens docs wiring |
| `test_ll_logs_wiring.py` | ll-logs CLI tool wiring |

**Configuration files:**
- `scripts/pyproject.toml:57-79` — `[tool.coverage.run]` already excludes `*/tests/*` from coverage; `[tool.pytest.ini_options]` has `--cov=little_loops`; may need new `doc_wiring` marker registration

### Dependent Files (Callers/Importers)
- **No CI configuration exists** — no `.github/workflows/`, no `Makefile`, no `tox.ini` (confirmed: `docs/development/TESTING.md:921-927`). All testing is local-only.
- **No coverage dashboards or CI reporting scripts exist** — coverage run via `pytest --cov=little_loops` ad-hoc only
- Doc-wiring tests import nothing from `little_loops` — they have zero callers/importers within the application

### Similar Patterns
- **Existing parametrize patterns** (20 files use `@pytest.mark.parametrize`): `test_frontmatter.py:34` (`@pytest.mark.parametrize("issue_type", [...])`), `test_fsm_evaluators.py:54` (heavily parametrized evaluator tests), `test_cli.py:47` (parametrized CLI flag tests) — these demonstrate the pattern to follow for consolidation
- **Module/CLI separation pattern**: `scripts/little_loops/link_checker.py` (testable API with pure functions) + `scripts/little_loops/cli/docs.py` (thin `argparse` wrapper) — pattern for Option B if doc-wiring becomes a lint tool
- **doc_counts module**: `scripts/little_loops/doc_counts.py` — similar pattern: `verify_documentation()`, `check_skill_sizes()`, `check_skill_budget()` are pure Python APIs with CLI wrappers
- Structural skill tests (`test_skill_*.py`) — test application code (import from `little_loops`), fundamentally different from doc-wiring tests which exercise zero application code

### Tests
- Existing test infrastructure: 20 parametrize-using files, `conftest.py` fixtures (`fixtures_dir`, `temp_project_dir`, `temp_project`, `sample_config`), two registered markers (`integration`, `slow`)
- Test directory is flat (`scripts/tests/`) — no subdirectories exist; categorization is by file naming convention
- The consolidated test files themselves are the deliverable

### Documentation
- `CONTRIBUTING.md:346-361` — "Documentation wiring for new CLI tools" section describes which files to update and references `test_create_extension_wiring.py`
- `docs/development/TESTING.md:240-262` — documents parametrized testing patterns
- `.claude/CLAUDE.md` — update test conventions section
- `docs/reference/API.md` — `link_checker.py` module documented; may need updates if doc-wiring becomes a lint tool

### Configuration
- `scripts/pyproject.toml` — only coverage/config file; no `.coveragerc` exists
- `.mlc.config.json` — `ll-check-links` ignore patterns (19 patterns); relevant for Option B lint rule approach

## Implementation Steps

### Phase 1: Catalog and Categorize (research complete ✓)
1. ~~Inventory all 59 doc-wiring test files~~ — **Done** (see Integration Map above for complete inventory)
2. Categorize the 59 files by assertion type:
   - **String presence** (80%+ of assertions): verify a keyword/phrase appears in a doc — candidates for parametrized `(doc_path, string, message)` tuples
   - **String absence** (~10%): verify old/deprecated content is removed — parametrized with negative assertions
   - **Region/structural** (<10%): verify content within a specific section — needs `str.find` boundaries, may not parametrize cleanly; evaluate individually
   - **Count assertions** (rare): verify specific numbers (e.g., `TOTAL = 10`) — brittle, flag for conversion to lint rule or removal
3. Map each file to the documents it checks (CLAUDE.md, CLI.md, API.md, CONTRIBUTING.md, skill files, etc.) to identify consolidation groups

### Phase 2: Design Consolidation Structure
4. Choose consolidation approach (Option A recommended):
   - **Option A**: Create ≤5 parametrized test files grouped by document category. Follow existing parametrize patterns: `test_frontmatter.py:34` (simple value lists), `test_fsm_evaluators.py:54` (complex tuple data), `test_cli.py:47` (flag/value pairs). Each test file defines a data structure of `(doc_path: Path, expected_string: str, message: str)` tuples iterated via `@pytest.mark.parametrize`.
   - **Option B**: Extend `ll-check-links` (`scripts/little_loops/link_checker.py`) or create a new `ll-check-doc-strings` tool following the module/CLI separation pattern used by `check_markdown_links()` → `main_check_links()` in `scripts/little_loops/cli/docs.py:313`. Move string-presence checks to a lint rule, keep only integration-critical assertions as tests.
   - **Option C**: Move wiring files to `scripts/tests/doc_wiring/` subdirectory (first categorized subdirectory); register `wiring` marker in `scripts/pyproject.toml` `[tool.pytest.ini_options].markers`.
5. Register a new `wiring` pytest marker in `scripts/pyproject.toml` if using parametrized tests, or a `doc_wiring` marker for Option C — follow existing marker pattern at `pyproject.toml` markers list

### Phase 3: Implement and Validate
6. Implement consolidated test files. Use `conftest.py` fixtures (`fixtures_dir`, `temp_project_dir`) where applicable to reduce per-file boilerplate. Reference existing parametrize patterns from `test_fsm_evaluators.py` (heaviest parametrize user) and `test_cli.py` (cleanest simple parametrize).
7. Run the consolidated tests alongside existing wiring tests to verify identical coverage: `pytest scripts/tests/test_doc_wiring*.py scripts/tests/test_*_wiring.py -v`
8. Delete the 59 individual wiring test files
9. Update `CONTRIBUTING.md:346-361` ("Documentation wiring for new CLI tools" section) and `.claude/CLAUDE.md` to reflect the new doc-wiring test conventions
10. Run full test suite: `pytest scripts/tests/ -v --tb=short` to confirm no regressions
11. Run `ruff check scripts/tests/` and `mypy scripts/little_loops/` for code quality

## Backwards Compatibility

- No breaking changes to APIs or user-facing behavior
- Existing CI pipelines continue to pass
- Test count will decrease (by design), which may affect dashboards that track "total tests"

## Impact

- **Priority**: P2 — High maintenance burden + false confidence from inflated metrics
- **Effort**: Small — Straightforward consolidation with clear patterns; low technical risk
- **Risk**: Low — No production code changes; test-only refactoring
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Development setup and testing guidelines |
| [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | Test organization principles |

## Labels

`test-quality`, `captured`

## Session Log
- `/ll:refine-issue` - 2026-06-05T22:41:33 - `a406bdd2-0219-4061-a3b8-167631c8f688.jsonl`
- `/ll:format-issue` - 2026-06-05T22:11:03 - `c00441d3-195f-4810-a78d-949b98493d5c.jsonl`
- `/ll:capture-issue` - 2026-06-05T21:16:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5cc001a-5129-4d2d-807d-39a428af0331.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
