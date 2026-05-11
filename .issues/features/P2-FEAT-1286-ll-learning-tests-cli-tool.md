---
id: FEAT-1286
type: FEAT
status: done
priority: P2
captured_at: '2026-04-25T00:00:00Z'
completed_at: '2026-05-11T21:19:22Z'
discovered_date: '2026-04-25'
discovered_by: issue-size-review
size: Small
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
parent: FEAT-1282
---

# FEAT-1286: ll-learning-tests CLI Tool

## Summary

Implement `ll-learning-tests` as a new CLI entry point that exposes the learning test registry to Bash-based callers (skills, loops, agents). Skills cannot call Python functions directly — they invoke CLI tools via `Bash`. Without this CLI surface, the `ll:explore-api` skill (FEAT-1287) and the FSM/lifecycle dependents (ENH-1283, ENH-1284) cannot query the registry.

## Parent Issue

Decomposed from FEAT-1282: Learning Test Registry and ll:explore-api Skill

## Current Behavior

There is no `ll-learning-tests` CLI entry point. The `LearnTestRecord` registry is accessible only as a Python module (`little_loops.learning_tests`). Skills, loops, and agents invoke tooling via `Bash` and cannot import Python modules directly, leaving the registry unreachable from non-Python callers.

## Expected Behavior

The `ll-learning-tests` CLI is installed as an entry point and provides:

- `ll-learning-tests check <target>` — prints record JSON to stdout; exits 1 with an error message if the target is not found
- `ll-learning-tests list` — prints all records as a JSON array
- `ll-learning-tests mark-stale <target>` — marks a record stale; exits 1 if not found
- `ll-learning-tests --help` — shows all subcommands

Skills, loops, and FSM evaluators can call `ll-learning-tests check <target>` via `Bash` to gate behavior on learning test coverage.

## Use Case

**Who**: Skill or loop developer implementing `ll:explore-api` (FEAT-1287) or a lifecycle hook (ENH-1283/ENH-1284) that must verify learning test coverage before proceeding.

**Context**: A skill or FSM evaluator needs to query the learning test registry at runtime via a `Bash` tool call — it cannot import Python directly.

**Goal**: Call `ll-learning-tests check "Anthropic SDK streaming"` in `Bash` to confirm a test record exists, then branch on exit code or parse the JSON output.

**Outcome**: All non-Python callers (skills, loops, agents) can query the `LearnTestRecord` registry without knowing Python module internals.

## Proposed Solution

### CLI surface

```
ll-learning-tests check <target>      # print record JSON; exit 1 if not found
ll-learning-tests list                # list all records as JSON array
ll-learning-tests mark-stale <target> # mark a record stale
```

The `check` subcommand is the key one — it is the callable surface for other skills and loops.

### Implementation

- `scripts/little_loops/cli/learning_tests.py` — implement `main_learning_tests` following conventions in existing CLI modules (e.g., `cli/sync.py`)
- Import `check_learning_test`, `list_records`, `mark_stale` from `little_loops.learning_tests`
- Register in `scripts/pyproject.toml:48-67` as `ll-learning-tests = "little_loops.cli:main_learning_tests"` (note: target is `little_loops.cli`, not the submodule directly — all entry points go through the re-export hub)
- Update `scripts/little_loops/cli/__init__.py` — add import and `__all__` entry (lines 23-65)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`learning_tests.py` module API (FEAT-1285, confirmed complete):**
- `check_learning_test(target, *, base_dir=None) -> LearnTestRecord | None` — accepts human-readable target name, slugifies internally; returns `None` if not found
- `list_records(*, base_dir=None) -> list[LearnTestRecord]` — returns all records
- `mark_stale(target_slug, *, base_dir=None) -> None` — accepts a slug (NOT a human-readable name); **is a no-op if the file does not exist**
- `LearnTestRecord.to_dict()` — returns a plain `dict` suitable for `json.dumps()`
- Storage path: `.ll/learning-tests/<slug>.md` (resolved in `_resolve_base()`)

**Critical implementation note for `mark-stale` subcommand:**
`mark_stale()` takes a slug and is a no-op if the file doesn't exist. To implement "exit 1 if not found" per the spec, the CLI must first call `check_learning_test(target)` to validate existence, then derive the slug before calling `mark_stale()`. The slug is not directly importable — derive it via a second call or reuse the `check_learning_test` check:
```python
record = check_learning_test(args.target)
if record is None:
    print(f"Error: no record found for {args.target!r}", file=sys.stderr)
    return 1
mark_stale(args.target, base_dir=...)  # mark_stale also accepts the target name if slugify is available
```
Check the `mark_stale` signature in `learning_tests.py` — the parameter is named `target_slug` but accepts whatever `_slug_path()` uses internally.

**`pyproject.toml` entry point format (confirmed):**
All entries use `ll-<name> = "little_loops.cli:main_<name>"` (re-export hub). The new line goes in `[project.scripts]` at `scripts/pyproject.toml:48-67`.

**`cli/__init__.py` three-step registration:**
1. Add `from little_loops.cli.learning_tests import main_learning_tests` to imports
2. Add `"main_learning_tests"` to `__all__`
3. Optionally add to module docstring's CLI tool list

### Documentation touchpoints

- `commands/help.md` — add `ll-learning-tests` entry to hardcoded CLI tools list (lines 216-234)
- `docs/reference/CLI.md` — add `### ll-learning-tests` reference section documenting all subcommands

## API/Interface

```bash
# CLI entry point (installed via pyproject.toml)
ll-learning-tests check <target>      # Exit 0 + JSON record; exit 1 + error message if not found
ll-learning-tests list                # Exit 0 + JSON array of all records
ll-learning-tests mark-stale <target> # Exit 0 on success; exit 1 if not found
ll-learning-tests --help              # Show subcommand help
```

```python
# Python entry point in scripts/little_loops/cli/learning_tests.py
def main_learning_tests() -> None:
    """CLI handler for ll-learning-tests subcommands."""
```

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/learning_tests.py` — **create** (new CLI handler)
- `scripts/little_loops/cli/__init__.py` — add import and `__all__` entry
- `scripts/pyproject.toml` — add `ll-learning-tests` entry point
- `commands/help.md` — add CLI tool entry
- `docs/reference/CLI.md` — add reference section
- `skills/init/SKILL.md` — add allow-list entry and CLAUDE.md boilerplate (owned by FEAT-1286)
- `skills/configure/areas.md` — increment count and add to tool enumeration (owned by FEAT-1286)

### Dependent Files (Callers/Importers)

- `skills/explore-api/SKILL.md` (FEAT-1287) — will call `ll-learning-tests check` via Bash
- FSM loop evaluators (ENH-1283, ENH-1284) — will gate on `ll-learning-tests check` exit code

_Wiring pass added by `/ll:wire-issue`:_
- `skills/init/SKILL.md` — add `"Bash(ll-learning-tests:*)"` to the hardcoded allow list JSON array; add `ll-learning-tests` to **both** CLAUDE.md boilerplate blocks (file-exists and create-new variants). Enforced by `test_ll_logs_wiring.py::TestInitSkillWiring` pattern. **Owned by FEAT-1286** — belongs with CLI tool creation; FEAT-1287 does not touch this file.
- `skills/configure/areas.md` — change "Authorize all 19" → "Authorize all 20" and insert `ll-learning-tests` into the tool enumeration string. Asserted by `test_create_extension_wiring.py::TestConfigureAreasWiring::test_count_updated_to_17` and `test_create_extension_wiring.py::TestFeat1229LlActionWiring::test_configure_areas_count_is_17` (see Corrected Count Values section for exact values). **Owned by FEAT-1286** — installing the CLI tool without this immediately fails wiring assertions; FEAT-1287 does not touch this file.

### Similar Patterns

- `scripts/little_loops/cli/sync.py` — follow module structure and argparse conventions
- Other `scripts/little_loops/cli/*.py` modules for consistent patterns

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/action.py:main_action()` — best reference for subcommands + JSON output; dispatches via `cmd_*` helper functions each returning `int`
- `scripts/little_loops/cli/output.py:print_json()` — use this utility for all JSON output (`print(json.dumps(data, indent=2))`); do NOT use `Logger` (sync.py pattern) for JSON-emitting subcommands
- `scripts/little_loops/cli/deps.py:main_deps()` — alternative reference using `--format json` flag with `import json as _json` (deferred import pattern)
- `scripts/little_loops/cli_args.py` — shared `add_config_arg()`, `add_quiet_arg()`, etc. available if needed

### Tests

- `scripts/tests/test_cli_learning_tests.py` — new test file for all CLI subcommands
- Install verification: `pip install -e "./scripts[dev]" && ll-learning-tests --help`
- `scripts/tests/test_learning_tests.py` — existing 28-test suite for the `learning_tests` module (no CLI tests; do not modify)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_learning_tests_wiring.py` (or inline in `test_cli_learning_tests.py`) — **new doc-wiring test** following the pattern in `test_ll_logs_wiring.py` and `test_create_extension_wiring.py`; assert `"ll-learning-tests"` is present in `commands/help.md` and in `docs/reference/CLI.md`. Without this, documentation gaps are undetected by CI. See `TestHelpMdWiring` and `TestFeat1229LlActionWiring` in those files for the exact pattern.
- **Import-failure risk**: Adding `from little_loops.cli.learning_tests import main_learning_tests` to `cli/__init__.py` means any syntax/import error in the new module will break collection of `test_issues_cli.py`, `test_issues_search.py`, `test_ll_loop_state.py`, `test_ll_loop_integration.py`, `test_doc_synthesis.py`, and `test_cli_e2e.py`. Run the full test suite immediately after creating `cli/learning_tests.py`.
- `scripts/tests/test_create_extension_wiring.py` — **4 existing assertions will break** when `areas.md` changes from "Authorize all 16" → "Authorize all 17": update `TestConfigureAreasWiring.test_count_updated_to_16` and `TestFeat1229LlActionWiring.test_configure_areas_count_is_16` (both: `"Authorize all 16"` → `"Authorize all 17"`); also update `TestFeat1045DocUpdates.test_readme_tool_count_is_17` and `TestFeat1229LlActionWiring.test_readme_tool_count_is_17` (both: `"17 CLI tools"` → `"18 CLI tools"` when README is updated). [Agent 2/3 finding]
- `scripts/tests/test_ll_logs_wiring.py` — **1 existing assertion will break**: `TestConfigureAreasWiring.test_authorize_all_count_is_16` asserts `"Authorize all 16"` — update to `"Authorize all 17"` atomically with `areas.md`. [Agent 2/3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Recommended test pattern** (from `test_cli_sync.py` + `test_issues_cli.py`):
- Use `patch("sys.argv", ["ll-learning-tests", "check", "some target"])` + direct `main_learning_tests()` call
- Use `capsys.readouterr()` to assert stdout JSON; parse with `json.loads()` to verify structure
- Fixture `temp_project_dir` from `conftest.py` provides an isolated `.ll/` dir; use `learning_tests_dir` pattern from `test_learning_tests.py` to set up `base_dir`
- One `Test*` class per subcommand: `TestMainLearningTestsNoAction`, `TestMainLearningTestsCheck`, `TestMainLearningTestsList`, `TestMainLearningTestsMarkStale`
- Patch `little_loops.cli.learning_tests.check_learning_test` / `list_records` / `mark_stale` for unit tests; use real module for integration-style tests with `temp_project_dir`

### Documentation

- `commands/help.md` — hardcoded CLI tools list (add entry)
- `docs/reference/CLI.md` — add `### ll-learning-tests` reference section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — soft coupling: the `## little_loops.cli` section enumerates individual `main_*` functions (`main_auto`, `main_loop`, `main_issues`); add `main_learning_tests` with its signature and subcommand table. Not test-enforced but is documentation hygiene.
- `README.md` — increment `"20 CLI tools"` → `"21 CLI tools"` (count only — no `### ll-` section; README is now a hero page, CLI docs go in `CLI.md`). The old test names `test_readme_tool_count_is_17` no longer exist; the current count assertion is `test_readme_tool_count_is_20` in `TestFeat1045DocUpdates` and `TestFeat1229LlActionWiring`. Update it to assert `"21 CLI tools"`. [wiring note updated 2026-05-10 after README rewrite]

### Configuration

- `scripts/pyproject.toml` — `[project.scripts]` entry point registration

## Implementation Steps

1. Implement `scripts/little_loops/cli/learning_tests.py` with `main_learning_tests() -> int` following `action.py:main_action()` pattern (subcommands + `print_json()` from `cli/output.py`)
2. Add `ll-learning-tests = "little_loops.cli:main_learning_tests"` to `[project.scripts]` in `scripts/pyproject.toml` (after line 67, matching existing format)
3. Update `scripts/little_loops/cli/__init__.py`: add `from little_loops.cli.learning_tests import main_learning_tests` import and `"main_learning_tests"` to `__all__`
4. Add `ll-learning-tests` to `commands/help.md` CLI tools block (lines 223-241, padded to ~18-char column width)
5. Add `### ll-learning-tests` reference section to `docs/reference/CLI.md`
6. Write `scripts/tests/test_cli_learning_tests.py` using `patch("sys.argv", ...)` + `capsys` pattern (see `test_cli_sync.py` and `test_issues_cli.py`)
7. Verify: `pip install -e "./scripts[dev]" && ll-learning-tests --help && ll-learning-tests list`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Add doc-wiring assertions to `scripts/tests/test_learning_tests_wiring.py` (or as a `TestDocWiring` class in `test_cli_learning_tests.py`) — assert `"ll-learning-tests"` is present in `commands/help.md` and `docs/reference/CLI.md`, following the pattern in `test_ll_logs_wiring.py::TestHelpMdWiring`
9. Update `skills/init/SKILL.md` — insert `"Bash(ll-learning-tests:*)"` into the JSON allow-list array; add `ll-learning-tests` to both CLAUDE.md boilerplate blocks (file-exists and create-new variants). Add a `TestInitSkillWiringLearningTests` class to `test_learning_tests_wiring.py` asserting both, following the `TestInitSkillWiring` pattern in `test_ll_logs_wiring.py`.
10. Update `skills/configure/areas.md` — change "Authorize all 19" → "Authorize all 20" and insert `ll-learning-tests` into the tool enumeration string (see Corrected Count Values section for exact test method names and current assertion values).
11. Update `docs/reference/API.md` — add `main_learning_tests` entry to the `## little_loops.cli` section (soft, documentation hygiene)
12. Update `scripts/tests/test_create_extension_wiring.py` — change `"Authorize all 16"` → `"Authorize all 17"` in `TestConfigureAreasWiring.test_count_updated_to_16` and `TestFeat1229LlActionWiring.test_configure_areas_count_is_16`; change `"17 CLI tools"` → `"18 CLI tools"` in `TestFeat1045DocUpdates.test_readme_tool_count_is_17` and `TestFeat1229LlActionWiring.test_readme_tool_count_is_17` (the latter two contingent on README being updated)
13. Update `scripts/tests/test_ll_logs_wiring.py` — change `"Authorize all 16"` → `"Authorize all 17"` in `TestConfigureAreasWiring.test_authorize_all_count_is_16`
14. Update `README.md` — see Corrected Count Values section for exact line numbers and new values; must change atomically with `skills/configure/areas.md` and the count-asserting tests in the same commit.

### Codebase Research Findings — Corrected Count Values (Refreshed 2026-05-11)

_Added by `/ll:refine-issue` — steps 12–14 above have stale count values; use these instead:_

**`skills/configure/areas.md` current value**: `"Authorize all 19"` (19 tools). After adding `ll-learning-tests`, update to **`"Authorize all 20"`**.

**Wiring test corrections** — referenced test names and assertion values in steps 12–13 are wrong:

| File | Actual method name | Current assertion | Change to |
|------|--------------------|-------------------|-----------|
| `test_create_extension_wiring.py` | `TestConfigureAreasWiring.test_count_updated_to_17` (line 55) | `"Authorize all 19"` | `"Authorize all 20"` |
| `test_create_extension_wiring.py` | `TestFeat1229LlActionWiring.test_configure_areas_count_is_17` (line 194) | `"Authorize all 19"` | `"Authorize all 20"` |
| `test_ll_logs_wiring.py` | `TestConfigureAreasWiring.test_authorize_all_count_is_17` (line 43) | `"Authorize all 18"` (**currently failing** — areas.md has 19, not 18) | `"Authorize all 20"` |

Methods `test_count_updated_to_16` and `test_authorize_all_count_is_16` (referenced in steps 12–13) **do not exist**. The actual method names are as shown above.

**README.md current situation** (step 14 references "line 90: '17 CLI tools'" — stale):
- Line 46: `"21 typed CLI tools"` → change to **`"22 typed CLI tools"`**
- Line 162: `"22 CLI tools"` → change to **`"23 CLI tools"`**
- Both `test_readme_tool_count_is_20` instances (lines 77 and 190 of `test_create_extension_wiring.py`) assert `"21 CLI tools"` — **currently failing** (neither README line contains the exact substring `"21 CLI tools"`). After updating README, change these assertions to `"22 CLI tools"` (to match the substring present in both `"22 typed CLI tools"` and `"22 CLI tools"` — pick the exact string that appears after your README change so the `in` check passes).

**Recommended atomic sequence for step 14**:
1. README line 46: `"21 typed CLI tools"` → `"22 typed CLI tools"`
2. README line 162: `"22 CLI tools"` → `"23 CLI tools"`
3. `test_create_extension_wiring.py` lines 79 and 192: `assert "21 CLI tools"` → `assert "22 CLI tools"` (matches the new line 46 substring)
4. Fix `test_ll_logs_wiring.py` line 45 in the same commit (18 → 20 atomically — combining the stale 18→19 gap fix with the new 19→20 increment).

## Acceptance Criteria

- `ll-learning-tests check "Anthropic SDK streaming"` prints record JSON or exits 1 with message if not found
- `ll-learning-tests list` prints all records as a JSON array
- `ll-learning-tests --help` shows all subcommands
- Entry point is registered and importable after `pip install -e`

## Impact

- **Priority**: P2 — Unblocks FEAT-1287 (`ll:explore-api` skill) and ENH-1283/ENH-1284 (FSM lifecycle hooks); the registry has no non-Python caller surface without this
- **Effort**: Small — New file (`cli/learning_tests.py`) following established patterns in `cli/sync.py`; thin wrapper only, no new logic required
- **Risk**: Low — Additive change; no modifications to existing code paths
- **Breaking Change**: No

## Dependencies

- FEAT-1285 (learning_tests module) must be complete first

## Blocks

- FEAT-1283

## Labels

`cli`, `new-feature`, `learning-tests`

---

**Open** | Created: 2026-04-25 | Priority: P2

## Verification Notes

**Verdict**: VALID — Verified 2026-04-26

- No `scripts/little_loops/cli/learning_tests.py` module ✓
- No `ll-learning-tests` entry point in `scripts/pyproject.toml` ✓
- No `check_learning_test`, `list_records`, `mark_stale` functions exist ✓
- Feature not yet implemented ✓

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-11_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- **Import chain blast radius**: Adding `from little_loops.cli.learning_tests import main_learning_tests` to `cli/__init__.py` will break collection of 6 test files on any syntax or import error in the new module. Run the full test suite immediately after creating `cli/learning_tests.py` before any other step.
- **3 pre-existing test failures must be fixed atomically**: `test_ll_logs_wiring.py::test_authorize_all_count_is_17` (asserts "Authorize all 18", areas.md has "19"), and both `test_readme_tool_count_is_20` instances (assert "21 CLI tools", README has neither). These are confirmed failing today; the Corrected Count Values section (2026-05-11) provides the exact fix values. Include all in the same commit as the areas.md and README changes.

_(Scope TBD for areas.md/init ownership — resolved 2026-05-11: both owned by FEAT-1286.)_

## Session Log
- `/ll:ready-issue` - 2026-05-11T21:08:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e415bd9-ddb5-4ea6-ae06-b4bb95085cc9.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7fd95d5-1e14-4e16-a7b4-1011718915cc.jsonl`
- `/ll:refine-issue` - 2026-05-11T20:38:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e0e03e2a-39f4-49de-8637-407748f778a5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:confidence-check` - 2026-05-07T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/66fedda1-ffa8-4033-891f-bc6637778822.jsonl`
- `/ll:wire-issue` - 2026-05-08T00:05:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00ae4f34-19a1-41bc-a2ee-c2457df0be7a.jsonl`
- `/ll:wire-issue` - 2026-05-07T23:55:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8e50c3a4-d3cc-4388-b3d9-ee92668c57b0.jsonl`
- `/ll:refine-issue` - 2026-05-07T23:49:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32f32bff-bc8b-4f34-ace6-57b3de5f60bd.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf03929d-b936-46f6-9fc6-0edf5cab2290.jsonl`
- `/ll:format-issue` - 2026-04-25T20:15:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c2dda3ac-5cb0-428a-8411-98d575600c2c.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): **CLI doc ownership split with FEAT-1287.** FEAT-1286 owns CLI-surface documentation: `commands/help.md` and `docs/reference/CLI.md`. FEAT-1287 owns narrative/architecture documentation: README skill table row, CONTRIBUTING skills tree, `.claude/CLAUDE.md`, and `docs/ARCHITECTURE.md`. Do not duplicate doc touchpoints across both issues — implement CLI docs here and leave narrative docs to FEAT-1287.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): FEAT-1286 owns the README.md CLI tool count increment (line 90: `"17 CLI tools"` → `"18 CLI tools"`). FEAT-1287 owns the skill count increment (27→28) in the README skill table row. These must be implemented atomically: both count changes in the same PR, or FEAT-1286 lands first and FEAT-1287 applies after. Do NOT increment the CLI count in FEAT-1287 — it belongs here. The wiring tests (`TestFeat1045DocUpdates.test_readme_tool_count_is_17`, `TestFeat1229LlActionWiring.test_readme_tool_count_is_17`) must be updated in the same commit as the README change.
