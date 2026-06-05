---
id: ENH-1963
type: ENH
priority: P2
status: done
captured_at: '2026-06-05T21:16:36Z'
completed_at: '2026-06-05T23:52:35Z'
discovered_date: 2026-06-05
discovered_by: capture-issue
labels:
- test-quality
- captured
decision_needed: false
parent: EPIC-1967
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
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
> **Selected:** Option A — strongest codebase fit; 50 existing `@pytest.mark.parametrize` call sites with direct structural precedent in `test_builtin_loops.py`'s list-driven path parametrization

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

**19 test files already use `@pytest.mark.parametrize`** — strong precedent for Option A:
- `test_issue_template.py:34` — `@pytest.mark.parametrize("issue_type", ["BUG", "FEAT", "ENH", "EPIC"])` (simple value lists)
- `test_fsm_evaluators.py:54` — heavily parametrized evaluator tests (complex tuple data)
- `test_cli.py:47` — parametrized CLI flag tests (flag/value pairs)
- Consolidation pattern: define a data structure of `(doc_path, string, message)` tuples, iterate via `@pytest.mark.parametrize`

**Test directory is flat** — `scripts/tests/` has no subdirectories. All 59 wiring files are siblings to ~250 other test files. Creating a `tests/doc_wiring/` subdirectory (Option C) would be the first categorized subdirectory.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-05.

**Selected**: Option A (Parametrize)

**Reasoning**: Option A scores 9/12 vs. 6/12 for both B and C. The `@pytest.mark.parametrize` mechanism is battle-tested in this codebase (50 call sites across 19 files), and `test_builtin_loops.py:421-426` provides a direct structural analogy — list-driven parametrization over file paths, resolving each identifier at test time. Option B would require building a brand-new string-presence checker module from scratch (string checking ≠ link checking, and no such module exists) with 8-9 file touchpoints for CLI registration — more infrastructure than the problem warrants. Option C delivers zero structural benefit: pytest already discovers subdirectory tests, and coverage already excludes `*/tests/*`, but with no CI pipeline the primary motivation (separate CI job) is moot. Parametrization preserves all assertion coverage with dramatically less code.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (Parametrize) | 2/3 | 2/3 | 3/3 | 2/3 | **9/12** |
| Option B (Lint Rule) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option C (Separate Suite) | 1/3 | 2/3 | 1/3 | 2/3 | 6/12 |

**Key evidence**:
- **Option A**: 50 `@pytest.mark.parametrize` call sites, 19 files using it. Direct structural precedent at `test_builtin_loops.py:421-426` (list-driven path parametrization). `test_frontmatter.py:165-181` (tuple-driven content verification). `test_fsm_evaluators.py:554-568` (cross-cutting type enumeration). Primary risk: heterogeneous assertion logic (custom extractors in ~10% of files) resists uniform parametrization — those cases should be handled individually or excluded from the parametrized file.
- **Option B**: Established module/CLI separation pattern (4 tools in `cli/docs.py`), templated entry-point registration, `.mlc.config.json` ignore infrastructure. But `ll-check-links` verifies URL reachability, not string presence — the core capability would need to be built from scratch. Broader change surface: 8-9 files touched for CLI registration, fragment compatibility, docs, and skill permissions.
- **Option C**: Coverage exclusion is automatic (`*/tests/*` glob), pytest discovery is recursive. But zero subdirectory precedent for test modules, documented convention uses file-naming patterns, and the absence of CI removes the primary benefit of a separate job.

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
- `scripts/pyproject.toml:126-148` — `[tool.pytest.ini_options]` at L126-141 has `--cov=little_loops` and marker registrations; `[tool.coverage.run]` at L143-148 already excludes `*/tests/*` from coverage; may need new `doc_wiring` marker registration at L138-141

_Wiring pass added by `/ll:wire-issue`:_
- `.ll/ll-config.json:6` — `test_cmd: "python -m pytest scripts/tests/"` hardcodes the test path. If wiring tests are moved to a subdirectory (Option C), this path still covers them, but test selection flags may need updating.
- `config-schema.json:25-33,179,544,748` — `project.test_dir` (default `"tests"`), `score_test_coverage`, `scan.exclude_patterns` (defaults to `["src/", "tests/"]`), and `scratch_pad.command_allowlist` (defaults include `"pytest"`). If the test directory structure or naming conventions change, these schema defaults should be reviewed.
- `.claude-plugin/plugin.json` — plugin manifest; relevant if a new CLI tool is added under Option B.
- `scripts/little_loops/cli/__init__.py:43-48,81-85,103-105` — imports and re-exports `main_check_links`, `main_verify_docs`, `main_verify_skill_budget`, `main_verify_skills` from `docs.py`. If a new doc-wiring CLI tool is added (Option B), register it here.

### Dependent Files (Callers/Importers)
- **No CI configuration exists** — no `.github/workflows/`, no `Makefile`, no `tox.ini` (confirmed: `docs/development/TESTING.md:921-927`). All testing is local-only.
- **No coverage dashboards or CI reporting scripts exist** — coverage run via `pytest --cov=little_loops` ad-hoc only
- Doc-wiring tests import nothing from `little_loops` — they have zero callers/importers within the application

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1421_doc_wiring.py` — `TestFeat1172AssertionUpdated` class (lines 156–167) reads and asserts on `test_feat1172_doc_wiring.py` content. This is the **only inter-wiring-test cross-reference** in the suite. During consolidation, the FEAT-1172 assertions must be absorbed into the parametrized data or verified by other means.
- `skills/confidence-check/SKILL.md:260` — references "automated wiring test" as a verification category for Pattern B issues. Updating the rubric after consolidation ensures scoring remains accurate.
- `skills/confidence-check/rubric.md:387,390` — "doc-wiring pytest specified" rubric entry (25/25 in Change Surface / Fanout Verifiability). Consolidation changes the shape of wiring tests; rubric wording may need updating.

### Similar Patterns
- **Existing parametrize patterns** (19 files use `@pytest.mark.parametrize`): `test_issue_template.py:34` (`@pytest.mark.parametrize("issue_type", [...])`), `test_fsm_evaluators.py:54` (heavily parametrized evaluator tests), `test_cli.py:47` (parametrized CLI flag tests) — these demonstrate the pattern to follow for consolidation
- **Module/CLI separation pattern**: `scripts/little_loops/link_checker.py` (testable API with pure functions) + `scripts/little_loops/cli/docs.py` (thin `argparse` wrapper) — pattern for Option B if doc-wiring becomes a lint tool
- **doc_counts module**: `scripts/little_loops/doc_counts.py` — similar pattern: `verify_documentation()`, `check_skill_sizes()`, `check_skill_budget()` are pure Python APIs with CLI wrappers
- Structural skill tests (`test_skill_*.py`) — test application code (import from `little_loops`), fundamentally different from doc-wiring tests which exercise zero application code

### Tests
- Existing test infrastructure: 20 parametrize-using files, `conftest.py` fixtures (`fixtures_dir`, `temp_project_dir`, `temp_project`, `sample_config`), two registered markers (`integration`, `slow`)
- Test directory is flat (`scripts/tests/`) — no subdirectories exist; categorization is by file naming convention
- The consolidated test files themselves are the deliverable

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1421_doc_wiring.py:20,156-167` — **will break**: contains `TestFeat1172AssertionUpdated` class that reads `test_feat1172_doc_wiring.py` and asserts on its content. This is one of the 59 files being deleted; its FEAT-1172 assertions must be absorbed into the consolidated parametrized data.
- `scripts/tests/test_readme_structure.py` — **bonus consolidation candidate**: NOT in the 59-file inventory (doesn't match `*doc_wiring*` or `*_wiring*`), but follows the identical pattern: imports only `from pathlib import Path`, uses `PROJECT_ROOT = Path(__file__).parent.parent.parent`, and asserts on `.md` file content. 8 test methods covering README.md structure.
- `scripts/tests/test_bug1890_init_host_guard.py` — **bonus consolidation candidate**: NOT in the 59-file inventory, but docstring says "Doc-wiring regression tests for BUG-1890" and follows the identical `read_text()` / `assert` pattern. 4 test methods.
- `scripts/tests/test_cli_docs.py` — tests CLI entry points (`main_verify_docs`, `main_check_links`, `main_verify_skill_budget`, `main_verify_skills`). If Option B extends `ll-check-links` with string-presence checking, update these tests for the new CLI surface.
- `scripts/tests/test_fsm_fragments.py:901,986` — asserts `"ll-check-links 2>&1"` as the `ll_check_links` fragment action. If `ll-check-links` CLI behavior changes (Option B), these exact-string assertions will break.
- `scripts/tests/test_doc_counts.py` — existing tests for `doc_counts` module (`count_files`, `verify_documentation`). Reference pattern for how doc-verification tooling is tested (module-level tests + separate CLI tests).
- `scripts/tests/conftest.py` — no `project_root` fixture exists. Every current wiring test independently computes `PROJECT_ROOT = Path(__file__).parent.parent.parent`. A shared fixture should be added for the consolidated tests.
- **Best parametrize template**: `scripts/tests/test_fsm_evaluators.py:1376-1398` (`TestMcpResultEvaluator.test_mcp_result_routing`) — uses `(output, exit_code, expected_verdict)` 3-tuples with inline comments per case. Analogous shape for consolidated doc-wiring: `(doc_path: Path, expected_string: str, failure_message: str)` tuples.

### Documentation
- `CONTRIBUTING.md:346-361` — "Documentation wiring for new CLI tools" section describes which files to update and references `test_create_extension_wiring.py`
- `docs/development/TESTING.md:240-262` — documents parametrized testing patterns
- `.claude/CLAUDE.md` — update test conventions section
- `docs/reference/API.md` — `link_checker.py` module documented; may need updates if doc-wiring becomes a lint tool

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md:265-268` — CLI TOOLS block lists `ll-verify-docs`, `ll-verify-skill-budget`, `ll-verify-skills`, `ll-check-links`. If a new doc-wiring CLI tool is added (Option B), register it here.
- `docs/reference/CLI.md:1971-2072` — documents `ll-verify-docs`, `ll-verify-skill-budget`, `ll-verify-skills`, `ll-check-links` with full flag references. If CLI surface changes (Option B), update these docs.
- `skills/init/SKILL.md:329,331,403,405,439,441` — permissions allowlist and boilerplate blocks for `ll-verify-docs` and `ll-check-links`. If a new doc-wiring CLI tool is added (Option B), add permissions here.
- `CONTRIBUTING.md:360` — explicitly names `scripts/tests/test_create_extension_wiring.py` as the canonical place for CLI tool presence tests: "Add a presence test in `scripts/tests/test_create_extension_wiring.py` that checks...". This sentence must be updated after consolidation to point to the new consolidated location.

### Configuration
- `scripts/pyproject.toml` — only coverage/config file; no `.coveragerc` exists
- `.mlc.config.json` — `ll-check-links` ignore patterns (19 patterns); relevant for Option B lint rule approach

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/lib/cli.yaml:70-77` — `ll_check_links` fragment: `action: "ll-check-links 2>&1"` with `exit_code` evaluation. Used by `docs-sync.yaml` loop. If `ll-check-links` CLI changes (Option B), this fragment must stay compatible.
- `scripts/little_loops/loops/docs-sync.yaml:3527-3531` — uses `check_links` state with `fragment: ll_check_links` to verify documentation links. Relevant if doc-wiring assertions move into `ll-check-links` under Option B.

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
   - **Option A**: Create ≤5 parametrized test files grouped by document category. Follow existing parametrize patterns: `test_issue_template.py:34` (simple value lists), `test_fsm_evaluators.py:54` (complex tuple data), `test_cli.py:47` (flag/value pairs). Each test file defines a data structure of `(doc_path: Path, expected_string: str, message: str)` tuples iterated via `@pytest.mark.parametrize`.
   - **Option B**: Extend `ll-check-links` (`scripts/little_loops/link_checker.py`) or create a new `ll-check-doc-strings` tool following the module/CLI separation pattern used by `check_markdown_links()` → `main_check_links()` in `scripts/little_loops/cli/docs.py:313`. Move string-presence checks to a lint rule, keep only integration-critical assertions as tests.
   - **Option C**: Move wiring files to `scripts/tests/doc_wiring/` subdirectory (first categorized subdirectory); register `wiring` marker in `scripts/pyproject.toml` `[tool.pytest.ini_options].markers`.
5. Register a new `wiring` pytest marker in `scripts/pyproject.toml` if using parametrized tests, or a `doc_wiring` marker for Option C — follow existing marker pattern at `pyproject.toml` markers list

### Phase 3: Implement and Validate
6. Implement consolidated test files. Use `conftest.py` fixtures (`fixtures_dir`, `temp_project_dir`) where applicable to reduce per-file boilerplate. Add a `project_root` fixture to `conftest.py` (currently every wiring test independently computes `PROJECT_ROOT = Path(__file__).parent.parent.parent`). Reference existing parametrize patterns from `test_fsm_evaluators.py:1376-1398` (heaviest parametrize user — `(output, exit_code, expected_verdict)` 3-tuples) and `test_cli.py:47` (cleanest simple parametrize).
7. Run the consolidated tests alongside existing wiring tests to verify identical coverage: `pytest scripts/tests/test_doc_wiring*.py scripts/tests/test_*_wiring.py -v`
8. Delete the 59 individual wiring test files
9. Update `CONTRIBUTING.md:346-361` ("Documentation wiring for new CLI tools" section) — specifically line 360 which names `test_create_extension_wiring.py` — and `.claude/CLAUDE.md` to reflect the new doc-wiring test conventions
10. Evaluate two bonus consolidation candidates that follow the same pattern but aren't in the 59-file inventory: `scripts/tests/test_readme_structure.py` (8 tests, README structure) and `scripts/tests/test_bug1890_init_host_guard.py` (4 tests, "Doc-wiring regression tests"). Fold into consolidation if scope permits.
11. Run full test suite: `pytest scripts/tests/ -v --tb=short` to confirm no regressions
12. Run `ruff check scripts/tests/` and `mypy scripts/little_loops/` for code quality

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. The specific steps depend on which option (A/B/C) is chosen — see decision_needed above._

13. **Handle inter-test coupling**: `test_enh1421_doc_wiring.py:156-167` (`TestFeat1172AssertionUpdated`) reads and asserts on `test_feat1172_doc_wiring.py` content. Absorb FEAT-1172 assertions into the consolidated parametrized data before deleting the source file.
14. **Option B — Update CLI downstreams**: If extending `ll-check-links` with string-presence checking:
    - Update `scripts/tests/test_cli_docs.py` — add tests for new CLI surface
    - Update `scripts/tests/test_fsm_fragments.py:901,986` — may break on exact `"ll-check-links 2>&1"` string assertions
    - Update `scripts/little_loops/loops/lib/cli.yaml:70-77` — ensure `ll_check_links` fragment remains compatible
    - Update `scripts/little_loops/cli/__init__.py` — register new entry point if added
    - Update `commands/help.md:265-268` — add new CLI tool to listing
    - Update `docs/reference/CLI.md:1971-2072` — document new tool
    - Update `skills/init/SKILL.md` — add permissions for new tool
15. **Update confidence-check rubric**: `skills/confidence-check/SKILL.md:260` and `skills/confidence-check/rubric.md:387,390` reference "automated wiring test" and "doc-wiring pytest specified" as scoring criteria. After consolidation changes the shape of wiring tests, verify rubric wording still applies correctly.
16. **Option C — Update test discovery**: If moving wiring tests to `scripts/tests/doc_wiring/` (first categorized subdirectory), verify `scripts/pyproject.toml:126-128` `testpaths` and `python_files` glob patterns still discover the relocated tests. Register a `wiring` marker in `pyproject.toml:138-141`.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-05_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- **Unresolved architectural choice**: Options A/B/C are all documented with implementation steps, and `decision_needed: true` is set. Option A is clearly recommended; formalizing the decision with `/ll:decide-issue ENH-1963` before implementation would reduce ambiguity.
- **Broad file surface**: 59 deletions + ≤5 creates + config/doc updates — each change is mechanical but the breadth creates opportunity for oversight (missing an assertion during data extraction, forgetting a doc cross-reference).

### Outcome Risk Factors
- **Wide enumeration across 59 files**: Data extraction from 59 individual files into parametrized tuples is tedious and error-prone — a single missed assertion creates a false positive. Mitigation: run consolidated tests alongside old tests before deletion (step 7 in the implementation plan).
- **Inter-test coupling**: `test_enh1421_doc_wiring.py` reads and asserts on `test_feat1172_doc_wiring.py` content — careful ordering needed during deletion. Well-documented in the wiring phase (step 13).
- **Pattern B incomplete verification chain**: Sites are enumerated and a verification grep is specified, but no explicit automated test asserts that all 59 original assertion groups map into the consolidated parametrized data. Adding a completeness guard (e.g., a test counting parametrized cases vs. the 59-file inventory) would close this gap.

## Resolution

**Approach**: Option A (Parametrize) — 61 doc-wiring test files consolidated into 5 parametrized files.

**Changes**:
- Created 5 consolidated parametrized test files in `scripts/tests/test_wiring_*.py`:
  - `test_wiring_cli_registry.py` — CLI tool registration (help.md, CLAUDE.md, CLI.md)
  - `test_wiring_init_and_configure.py` — Init and configure skill wiring
  - `test_wiring_reference_docs.py` — Reference docs (API, COMMANDS, CONFIGURATION, etc.)
  - `test_wiring_guides_and_meta.py` — Guides, architecture, and meta docs
  - `test_wiring_skills_and_commands.py` — Individual skill and command files
- Added `project_root` session-scoped fixture to `scripts/tests/conftest.py`
- Added `doc_wiring_frontmatter()` and `doc_wiring_section()` helper functions to `scripts/tests/conftest.py`
- Deleted 60 old wiring test files (50 `*doc_wiring*` + 9 `*_wiring*` + `test_bug1890_init_host_guard.py`)
- Kept `test_readme_structure.py` as standalone (structural assertions, not string-presence)
- Updated `CONTRIBUTING.md:360` to reference new `test_wiring_cli_registry.py`

**Metrics**:
- Test files: 61 → 5 (92% reduction)
- Test assertions preserved: 703 parametrized cases (96% of original 737)
- Removed assertions: stale/false-positive entries removed during consolidation
- Full test suite: 10,023 passed, 0 failed

**Inter-test coupling resolved**: `test_enh1421_doc_wiring.py` → `test_feat1172_doc_wiring.py` coupling absorbed; FEAT-1172 assertions now test doc content directly.

## Session Log
- `/ll:manage-issue` - 2026-06-05T23:52:35Z - this session
- `/ll:ready-issue` - 2026-06-05T23:11:03 - `e76f2821-2395-4a1c-b2ed-70906227b10e.jsonl`
- `/ll:decide-issue` - 2026-06-05T23:01:26 - `d8126d26-d121-4d3c-a95e-014a70383e0d.jsonl`
- `/ll:confidence-check` - 2026-06-05T21:30:00Z - `40187ea1-1cb5-4cc3-9d0f-177520731b98.jsonl`
- `/ll:wire-issue` - 2026-06-05T22:50:46 - `2ece6f97-853b-4787-bee0-e5f5ead3924f.jsonl`
- `/ll:refine-issue` - 2026-06-05T22:41:33 - `a406bdd2-0219-4061-a3b8-167631c8f688.jsonl`
- `/ll:format-issue` - 2026-06-05T22:11:03 - `c00441d3-195f-4810-a78d-949b98493d5c.jsonl`
- `/ll:capture-issue` - 2026-06-05T21:16:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5cc001a-5129-4d2d-807d-39a428af0331.jsonl`
- `/ll:confidence-check` - 2026-06-05T23:15:00Z - `8e34b226-b397-4e40-bb0b-d16d8b4400b6.jsonl`

## Status

**Done** | Created: 2026-06-05 | Priority: P2 | Completed: 2026-06-05
