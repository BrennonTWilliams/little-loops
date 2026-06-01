---
id: FEAT-1852
type: FEAT
title: "ll-harness CLI \u2014 doc, wiring, and count correction sweep"
priority: P2
status: done
parent: FEAT-1689
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1852: ll-harness CLI — doc, wiring, and count correction sweep

## Summary

Update all documentation surfaces, plugin permissions, orchestration CLI tables, count assertions, and wiring verification tests for `ll-harness`. Requires FEAT-1851 (core implementation) to be merged first. This is a strict doc/config/test sweep — no implementation logic changes.

## Parent Issue

Decomposed from FEAT-1689: add ll-harness CLI for one-shot runner evaluation

## Prerequisite

**FEAT-1851 must be merged before this issue is worked.** Wiring tests (step 9, 13) verify presence of `ll-harness` in config files that step 7 modifies. E2E test (step 10) requires the binary to be installed.

## Implementation Steps

Implements steps 6, 7, 8, 9, 10, 11, 12, and 13 from the parent issue.

### Step 6: Doc-wiring sweep

Per the CONTRIBUTING.md checklist (lines 341-355):
- `docs/reference/CLI.md` — add full `### ll-harness` section
- `commands/help.md` — add one-line `ll-harness` entry in CLI TOOLS block (after line 273)
- `.claude/CLAUDE.md` — add `ll-harness` to CLI Tools list (currently lists 28 tools)
- `docs/ARCHITECTURE.md` — add `harness.py` to `cli/` directory tree listing (line ~201)
- `CONTRIBUTING.md` — add `harness.py` to project structure tree (line ~186); follow checklist at lines 338-353 ("Documentation wiring for new CLI tools")
- `README.md` — `"30 typed CLI tools"` count (lines 46, 162) is **already current** — no increment needed

### Step 7: Permissions and init wiring

- `skills/init/SKILL.md` — add `"Bash(ll-harness:*)"` to permissions block (after line 551) and both CLAUDE.md boilerplate blocks (lines ~600, ~633)
- `skills/configure/areas.md` — add `ll-harness` to allowed-tools enumeration (line 825) **AND** change `"Authorize all 27"` → `"Authorize all 28"` (see step 12 for count correction)

### Step 8: Orchestration CLI registration

- `docs/reference/HOST_COMPATIBILITY.md` — add `ll-harness` row to Orchestration CLI table (after line 141; table currently has 5 entries: ll-auto, ll-parallel, ll-action, ll-loop, FSM evaluators); update footnote count from "six" to "seven"
- `docs/codex/README.md` — add `ll-harness` to orchestration CLIs list (line 28)
- `docs/codex/usage.md` — add `ll-harness` to orchestration tools parenthetical (line 7)

### Step 9: Wiring test

Add `TestFeat1689LlHarnessWiring` class to `scripts/tests/test_create_extension_wiring.py` verifying `ll-harness` presence in:
- `CLI_REFERENCE` (docs/reference/CLI.md)
- `HELP_MD` (commands/help.md)
- `CLAUDE_MD` (.claude/CLAUDE.md)
- `CONFIGURE_AREAS` (skills/configure/areas.md)
- `INIT_SKILL` (skills/init/SKILL.md)

Include INIT_SKILL assertions per the established pattern (`TestFeat1229LlActionWiring`, `TestFeat1526LlAdaptAgentsWiring`):
- `assert '"Bash(ll-harness:*)"' in INIT_SKILL.read_text()`
- `assert INIT_SKILL.read_text().count("ll-harness") >= 3`

### Step 10: E2E smoke test (optional, `@pytest.mark.integration`)

Add `ll-harness cmd "echo hello" --exit-code 0` to `scripts/tests/test_cli_e2e.py` following the `E2ETestFixture` pattern (base class at line 24).

### Step 11: Changelog

Add FEAT-1689 entry to `CHANGELOG.md` under the next release section.

### Step 12: Count assertion corrections

- `skills/configure/areas.md` line 825: change `"Authorize all 27"` → `"Authorize all 28"` AND append `ll-harness` to the named enumeration (coordinate with step 7)
- `scripts/tests/test_create_extension_wiring.py` lines 57 and 196: update assertion string `"Authorize all 27"` → `"Authorize all 28"`
- `scripts/tests/test_enh1846_doc_wiring.py` line 46: same update `"Authorize all 27"` → `"Authorize all 28"`

Note: `"30 typed CLI tools"` in `README.md` and test assertions (`test_create_extension_wiring.py` lines 79, 192; `test_enh1846_doc_wiring.py` line 66) do **not** need bumping — `ll-harness` was pre-counted when "30" was set.

### Step 13: Complete TestFeat1689LlHarnessWiring (wiring verification test)

The test class in step 9 must also include `test_enh1846_doc_wiring.py` coverage verification and the module docstring bullet (in `cli/__init__.py`, lines 1–33 — add `ll-harness` bullet; this is a distinct edit from the import after line 43 and the `__all__` entry at lines 68–102, both of which are done in FEAT-1851).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

14. Fix `scripts/tests/test_ll_logs_wiring.py:45` — update `"Authorize all 26"` → `"Authorize all 28"` in `TestConfigureAreasWiring.test_authorize_all_count_is_26` (currently failing)
15. Fix `scripts/tests/test_feat1504_doc_wiring.py:49` — same stale assertion update (currently failing)
16. Fix `scripts/tests/test_feat1625_doc_wiring.py:53` — same stale assertion update (currently failing)
17. Add 4 missing test methods to `TestFeat1689LlHarnessWiring` following `TestFeat1526LlAdaptAgentsWiring` pattern: `test_contributing_md_has_harness_py`, `test_codex_readme_lists_ll_harness`, `test_codex_usage_lists_ll_harness`, `test_host_compatibility_has_ll_harness`
18. Add `### main_harness` subsection to `docs/reference/API.md` under `## little_loops.cli` section, following the same pattern as `### main_action` and other `main_*` entries

## Files to Modify

- `commands/help.md` — add `ll-harness` one-line entry
- `.claude/CLAUDE.md` — add `ll-harness` to CLI Tools list
- `docs/reference/CLI.md` — add `### ll-harness` section
- `docs/reference/HOST_COMPATIBILITY.md` — add `ll-harness` row + update footnote count
- `docs/codex/README.md` — add `ll-harness` to orchestration list
- `docs/codex/usage.md` — add `ll-harness` to orchestration tools
- `docs/ARCHITECTURE.md` — add `harness.py` to `cli/` tree
- `CONTRIBUTING.md` — add `harness.py` to project structure tree
- `CHANGELOG.md` — add FEAT-1689 entry
- `skills/init/SKILL.md` — add `"Bash(ll-harness:*)"` to permissions and boilerplate blocks
- `skills/configure/areas.md` — add `ll-harness` + change count to `"Authorize all 28"`
- `scripts/tests/test_create_extension_wiring.py` — add `TestFeat1689LlHarnessWiring`; update count assertions to `"Authorize all 28"`
- `scripts/tests/test_enh1846_doc_wiring.py` — update count assertion to `"Authorize all 28"`
- `scripts/tests/test_cli_e2e.py` — add `ll-harness cmd "echo hello"` E2E test (optional)
- `scripts/little_loops/cli/__init__.py` — add `ll-harness` bullet to module docstring (lines 1–33); this is the third distinct edit in this file (FEAT-1851 handles the import after line 43 and `__all__` at lines 68–102)

## Integration Map

### Files to Modify (with Anchors)

| File | Change | Anchor / Line |
|------|--------|---------------|
| `docs/reference/CLI.md` | Added `### ll-harness` section with runners table, evaluator flags, exit codes, examples | Line 111 |
| `commands/help.md` | Added one-line entry for `ll-harness` in CLI TOOLS block | Line 246 |
| `.claude/CLAUDE.md` | Added `ll-harness` to CLI Tools list | Line 163 |
| `docs/ARCHITECTURE.md` | Added `harness.py` to `cli/` directory tree | — |
| `CONTRIBUTING.md` | Added `harness.py` to project structure tree | — |
| `skills/init/SKILL.md` | Added `"Bash(ll-harness:*)"` to permissions block; added `ll-harness` to both CLAUDE.md boilerplate blocks | Lines ~553, ~603, ~637 |
| `skills/configure/areas.md` | Added `ll-harness` to enumeration; changed count to `"Authorize all 28"` | Line 825 |
| `docs/reference/HOST_COMPATIBILITY.md` | Added `ll-harness` row to Orchestration CLI table; updated footnote count to seven | Line 144 |
| `docs/codex/README.md` | Added `ll-harness` to orchestration CLIs list | Line ~28 |
| `docs/codex/usage.md` | Added `ll-harness` to orchestration tools parenthetical | Line ~7 |
| `scripts/tests/test_create_extension_wiring.py` | Added `TestFeat1689LlHarnessWiring` (7 tests); updated `"Authorize all 28"` count assertions | Lines 356–395 |
| `scripts/tests/test_enh1846_doc_wiring.py` | Updated count assertion to `"Authorize all 28"` | Line ~44 |
| `scripts/little_loops/cli/__init__.py` | Added `ll-harness` bullet to module docstring | Line 4 |
| `CHANGELOG.md` | Added FEAT-1689 entry under release section | — |

### Dependent Files (Read-Only References)
- `scripts/little_loops/cli/harness.py` — `main_harness()` at line 352; `_build_harness_parser()` at line 34; package entry point registered in `scripts/pyproject.toml:51`
- `scripts/little_loops/cli/__init__.py` — import at line 37; `__all__` at line 72

### Tests
- `scripts/tests/test_create_extension_wiring.py:356` — `TestFeat1689LlHarnessWiring` (7 assertion methods)
- `scripts/tests/test_enh1846_doc_wiring.py:44` — count assertion `"Authorize all 28"`
- `scripts/tests/test_cli_e2e.py` — optional `ll-harness cmd "echo hello"` E2E test (`@pytest.mark.integration`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs_wiring.py:45` — `TestConfigureAreasWiring.test_authorize_all_count_is_26` asserts stale `"Authorize all 26"` → **currently failing**; update to `"Authorize all 28"` [Agent 2 finding]
- `scripts/tests/test_feat1504_doc_wiring.py:49` — `TestConfigureAreasWiring.test_authorize_all_count_is_26` asserts stale `"Authorize all 26"` → **currently failing**; update to `"Authorize all 28"` [Agent 2 finding]
- `scripts/tests/test_feat1625_doc_wiring.py:53` — `TestConfigureAreasWiring.test_authorize_all_count_is_26` asserts stale `"Authorize all 26"` → **currently failing**; update to `"Authorize all 28"` [Agent 2 finding]
- `scripts/tests/test_create_extension_wiring.py` — `TestFeat1689LlHarnessWiring` missing 4 test methods vs. `TestFeat1526LlAdaptAgentsWiring` pattern: `test_contributing_md_has_harness_py`, `test_codex_readme_lists_ll_harness`, `test_codex_usage_lists_ll_harness`, `test_host_compatibility_has_ll_harness` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `## little_loops.cli` section has `### main_action`, `### main_auto`, etc. for every other entry in `__all__`, but has no `### main_harness` subsection; follows the same established pattern [Agent 2 finding]

### Similar Patterns Referenced
- `test_create_extension_wiring.py:175` — `TestFeat1229LlActionWiring` (structural template followed)
- `test_create_extension_wiring.py:305` — `TestFeat1526LlAdaptAgentsWiring` (codex doc assertions)
- `docs/reference/CLI.md:35` — `### ll-action` section structure used as doc template

## Acceptance Criteria

- `"ll-harness"` present in `commands/help.md` (verified by `test_help_md_lists_ll_harness`)
- `"ll-harness"` present in `docs/reference/CLI.md` (verified by `test_cli_reference_has_ll_harness_section`)
- `"ll-harness"` present in `.claude/CLAUDE.md` (verified by `test_claude_md_lists_ll_harness`)
- `"Authorize all 28"` present in `skills/configure/areas.md` (verified by `test_configure_areas_count_updated_to_28`)
- `"ll-harness"` present in `skills/configure/areas.md` enumeration (verified by `test_configure_areas_lists_ll_harness`)
- `'"Bash(ll-harness:*)"'` exact string present in `skills/init/SKILL.md` (verified by `test_init_skill_has_ll_harness_bash_permission`)
- `skills/init/SKILL.md` contains `"ll-harness"` at least 3 times (verified by `test_init_skill_boilerplate_has_ll_harness`)
- `ll-harness` row present in `docs/reference/HOST_COMPATIBILITY.md` Orchestration CLI table
- `main_harness` listed in `cli/__init__.py` module docstring, imports, and `__all__`
- FEAT-1689 entry present in `CHANGELOG.md`

## Session Log
- `/ll:ready-issue` - 2026-06-01T16:04:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/78d6fbf0-559a-4bea-b86c-53cc66116f46.jsonl`
- `/ll:refine-issue` - 2026-06-01T15:53:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c2b53b1-0bfa-4803-b7c7-263ddc2ff9bb.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1ebc34f-6a74-4ed8-b570-856978fc59ce.jsonl`
- `/ll:wire-issue` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1ebc34f-6a74-4ed8-b570-856978fc59ce.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/66000302-6aca-4dad-9383-1e0068c604bb.jsonl`

---

**Done** | Created: 2026-06-01 | Priority: P2
