---
parent: ENH-1123
depends_on: ENH-1125
discovered_date: 2026-04-16
discovered_by: issue-size-review
size: Medium
confidence_score: 80
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1126: Tests and Documentation for Configurable next-issue Selection

## Summary

Write tests for `NextIssueConfig` and the sort-key resolver, update existing sort-order tests that will break after ENH-1125, and update documentation to describe the new config block.

## Parent Issue

Decomposed from ENH-1123: Configurable ll-issues next-issue Selection Behavior

## Proposed Solution

### Tests

1. **Existing sort tests — verify pass unchanged under `confidence_first` default**:
   - `scripts/tests/test_next_issue.py:58-197` (`TestNextIssueSorting`, 4 tests — `test_returns_highest_outcome_confidence`, `test_tiebreak_by_confidence_score`, `test_tiebreak_by_priority`, `test_unscored_issues_rank_last`): all use **winner-only assertions** (`assert "FEAT-XXX" in out`). Since `confidence_first` is byte-identical to the current lambda (per ENH-1125 spec), no assertion text changes needed — run the suite to confirm.
   - `scripts/tests/test_next_issues.py:58-143` (`TestNextIssuesRankedOrder`, 2 tests): uses **full-list positional assertions** (`assert lines[0] == "FEAT-002"` etc.); same conclusion — no text changes needed if the None-sentinel stays at `-1` (ENH-1125 chose `-1`). Verify on green run.
   - **Add one regression test per file**: `test_priority_first_strategy_overrides_default` — write config with `"next_issue": {"strategy": "priority_first"}`, assert a lower-priority but higher-confidence issue loses to a higher-priority one.

2. **Add `TestNextIssueConfig` to `scripts/tests/test_config.py`** (mirror `TestDuplicateDetectionConfig` at lines 172-225), placed directly after that class (after line 225). 6 methods required:
   - `test_defaults` — `NextIssueConfig()` → `strategy == "confidence_first"`, `sort_keys is None`
   - `test_from_dict_with_strategy` — `NextIssueConfig.from_dict({"strategy": "priority_first"})`
   - `test_from_dict_with_empty_dict` — `NextIssueConfig.from_dict({})` → defaults
   - `test_unknown_strategy_raises` — `pytest.raises(ValueError, match="Unknown strategy")` (pattern from `scripts/tests/test_issue_template.py:151-160`, not from `TestDuplicateDetectionConfig` which has no `raises` assertions)
   - `test_unknown_sort_key_raises` — `pytest.raises(ValueError, match="Unknown sort key")` on `{"sort_keys": [{"key": "nonexistent", "direction": "asc"}]}`
   - `test_issues_config_parses_next_issue` — mirror `test_issues_config_parses_duplicate_detection` at line 195: `IssuesConfig.from_dict({"next_issue": {"strategy": "priority_first"}})`
   - **Import addition required at `test_config.py` line 24**: add `NextIssueConfig` to the existing `from little_loops.config import (...)` tuple alongside `DuplicateDetectionConfig`.

3. **Update `TestIssuesConfig.test_from_dict_with_defaults`** (`test_config.py:154-169`) — append one line: `assert config.next_issue.strategy == "confidence_first"`. Called out separately because it's an edit to an existing test outside the new class.

4. **Add `TestBuildSortKey` to `scripts/tests/test_issues_search.py`** (new class for the resolver itself; referenced in ENH-1125 wiring as the natural home). **Do not** use `TestSearchSorting` (lines 639-724) as template — it exercises full CLI via `main_issues()`. Instead model after `scripts/tests/test_fsm_evaluators.py:404-483` (`TestEvaluateDispatcher`): construct config dataclass, call function, assert on return value. No fixtures, no filesystem, no `sys.argv` patching. Required tests:
   - `confidence_first` preset returns byte-identical tuple to current lambda
   - `priority_first` preset returns `(priority_int, ...)` tuple
   - Custom `sort_keys` overrides `strategy`
   - None handling: `None` score with `direction: desc` → sentinel `1`; with `direction: asc` → sentinel `9999` (per ENH-1125 resolution)

5. **Add schema test in `scripts/tests/test_config_schema.py`** — new method in existing `TestConfigSchema` class. **Note: `jsonschema` is not a dependency** — no runtime validator exists. Follow the existing structural-assertion pattern (see `test_extensions_in_properties` at line 19):
   ```python
   def test_issues_next_issue_in_schema(self) -> None:
       data = json.loads(CONFIG_SCHEMA.read_text())
       issues_props = data["properties"]["issues"]["properties"]
       assert "next_issue" in issues_props
       strategy = issues_props["next_issue"]["properties"]["strategy"]
       assert "enum" in strategy
       assert "confidence_first" in strategy["enum"]
       assert "priority_first" in strategy["enum"]
       assert "bogus" not in strategy["enum"]  # sentinel guard, not real validation
   ```

6. **Test harness pattern for CLI-level tests**:
   - `temp_project_dir` is a fixture at `scripts/tests/conftest.py:55-62` (**not** 55-121) — yields a `Path` with `.ll/` subdir created.
   - `_write_config` is **not** a conftest fixture — it's a module-level helper at `test_next_issue.py:14-16` and `test_next_issues.py:14-16` (copy-pasted verbatim between the two files). Takes `(temp_project_dir, sample_config)`, writes `json.dumps(sample_config)` to `.ll/ll-config.json`.
   - CLI invocation: `patch.object(sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)])` then lazy-import `from little_loops.cli import main_issues; main_issues()` inside the `with` block.

### Documentation

7. **`docs/reference/CLI.md:526` and `:541`** — both contain the identical verbatim line: `**Sort order:** \`outcome_confidence\` (desc), \`confidence_score\` (desc), \`priority\` (asc). Issues without scores are ranked below all scored issues.` Replace with: `**Sort order:** Config-driven via \`issues.next_issue.strategy\` (default: \`confidence_first\` — \`outcome_confidence\` desc, \`confidence_score\` desc, \`priority\` asc). Issues without scores are ranked below all scored issues.`
   - Bonus fix: `--config` flag appears in `next-issue` flag table at `CLI.md:535` but is absent from the `next-issues` flag table (`CLI.md:545-550`). Add it for consistency.

8. **`docs/reference/API.md:2957-3015`** — `next-issue` section is 2957-2985, `next-issues` is 2987-3015. Two locations (lines 2975 and 3005) hardcode the sort tuple `-(outcome_confidence or -1), -(confidence_score or -1), priority_int`. Insert a `**Strategy**:` line immediately above each, and add a `**Configuration**:` block with a `priority_first` JSON example below each `**FSM loop use:**` note.

9. **`docs/reference/API.md:326-337`** — `IssuesConfig` dataclass block. Add `next_issue: NextIssueConfig` field below `duplicate_detection` (line 337). Follow with a new `### NextIssueConfig` section immediately after the existing `### DuplicateDetectionConfig` section (~line 339) mirroring its structure.

10. **`docs/reference/CONFIGURATION.md:25-41`** — full `issues` JSON example. Append `"next_issue": { "strategy": "confidence_first" }` inside the `issues` object before its closing brace (after line 40).

11. **`docs/reference/CONFIGURATION.md:247-248`** — issues config options table currently lists `duplicate_detection.*` rows; add `next_issue.strategy` and `next_issue.sort_keys` rows following the same format.

12. **`docs/reference/CONFIGURATION.md`** — add new `### \`issues.next_issue\`` subsection after `### \`dependency_mapping\`` (after line 519). Follow the pattern of `### \`refine_status\`` (line 483) and `### \`dependency_mapping\`` (line 502): key-name heading with backticks, one-sentence intro, options table, and a `**Example**` block.

13. **`docs/guides/LOOPS_GUIDE.md:2052`** — fragment row currently reads `| \`ll_issues_next_issue\` | \`ll-issues next-issue\` | Get next-priority issue file path. |`. Append to the Description column: `Selection order is config-driven via \`issues.next_issue.strategy\` (default: \`confidence_first\`).`

## Integration Map

### Files to Modify

**Tests:**
- `scripts/tests/test_config.py:24` — add `NextIssueConfig` to `from little_loops.config import (...)` tuple
- `scripts/tests/test_config.py:154-169` — append one-line assertion to `test_from_dict_with_defaults`
- `scripts/tests/test_config.py:226+` — insert new `TestNextIssueConfig` class (6 methods) after `TestDuplicateDetectionConfig`
- `scripts/tests/test_config_schema.py:26+` — insert new `test_issues_next_issue_in_schema` method inside existing `TestConfigSchema` class
- `scripts/tests/test_issues_search.py` — insert new `TestBuildSortKey` class (co-located with `TestSearchSorting` but structurally distinct — no shared fixtures)
- `scripts/tests/test_next_issue.py:58-197` — verify pass unchanged; add one `test_priority_first_strategy_overrides_default` regression
- `scripts/tests/test_next_issues.py:58-143` — same

**Documentation:**
- `docs/reference/CLI.md:526, :541` — update sort order descriptions
- `docs/reference/CLI.md:545-550` — add `--config` flag to `next-issues` table (consistency fix)
- `docs/reference/API.md:2975, :3005` — update hardcoded sort tuple references
- `docs/reference/API.md:2985, :3015` — insert `**Configuration**:` block with `priority_first` example
- `docs/reference/API.md:326-337` — add `next_issue` field to `IssuesConfig` dataclass block
- `docs/reference/API.md:~339` — add new `### NextIssueConfig` subsection after `### DuplicateDetectionConfig`
- `docs/reference/CONFIGURATION.md:25-41` — add `next_issue` to full `issues` example
- `docs/reference/CONFIGURATION.md:247-248` — add `next_issue.*` rows to issues options table
- `docs/reference/CONFIGURATION.md:~520` — add new `### \`issues.next_issue\`` subsection after `### \`dependency_mapping\``
- `docs/guides/LOOPS_GUIDE.md:2052` — extend `ll_issues_next_issue` fragment description

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py:35,63` — **ENH-1124 prerequisite**: `NextIssueConfig` must be added to the `from little_loops.config.features import (...)` block and `__all__` here; ENH-1126's `test_config.py:24` imports `NextIssueConfig` from `little_loops.config` and will fail at collection time if this export is absent
- `scripts/little_loops/cli/issues/next_issue.py:33-39` — **ENH-1125 prerequisite**: `test_priority_first_strategy_overrides_default` only exercises meaningful behavior after ENH-1125 replaces the hardcoded lambda with `build_sort_key(config.issues.next_issue)`; tests may pass vacuously with wrong behavior if ENH-1125 hasn't landed
- `scripts/little_loops/cli/issues/next_issues.py:31-37` — same ENH-1125 prerequisite as above

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py:597-611` — `test_to_dict`: calls `json.dumps(result)` on the full `BRConfig.to_dict()` output; will break if ENH-1124 serializes `next_issue` as a raw `NextIssueConfig` object instead of a `dict` — verify that `to_dict()` either omits `next_issue` (for consistency with `duplicate_detection`) or serializes it as a plain `dict`

### Corrections Discovered

_Wiring pass added by `/ll:wire-issue`:_
- **Step 7 (`CLI.md:545-550`) is a no-op**: the `--config` flag is already present at `CLI.md:550` in the current `next-issues` flag table. Implementer should verify the current file state before inserting — the "add for consistency" step in the issue may be pre-satisfied.
- **`sample_config` fixture (`conftest.py:66-113`) has no `next_issue` key**: the new `test_priority_first_strategy_overrides_default` regression tests cannot use the `config_file` fixture — they must use `_write_config` (module-level helper at `test_next_issue.py:14-16`) with an inline modified dict: `{**sample_config, "issues": {**sample_config["issues"], "next_issue": {"strategy": "priority_first"}}}`

### Similar Patterns
- `scripts/tests/test_config.py:172-225` — `TestDuplicateDetectionConfig` is the structural template for `TestNextIssueConfig` (but has no `pytest.raises` — borrow that from elsewhere)
- `scripts/tests/test_issue_template.py:151-160` — `pytest.raises(ValueError, match="Unknown creation variant")` pattern; source for the `ValueError`-assertion tests
- `scripts/tests/test_fsm_evaluators.py:404-483` — `TestEvaluateDispatcher` is the template for `TestBuildSortKey` (pure-function dispatch, no CLI harness)
- `scripts/tests/test_config_schema.py:19` — `test_extensions_in_properties` is the pattern for structural schema assertions
- `docs/reference/CONFIGURATION.md:483` and `:502` — `### \`refine_status\`` and `### \`dependency_mapping\`` subsections are the style template

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrections to original draft:**

- `_write_config` is a module-level helper (not a conftest fixture) duplicated at `test_next_issue.py:14-16` and `test_next_issues.py:14-16`. The conftest range at `55-121` actually contains: `temp_project_dir` (55-62), `sample_config` (66-113), `config_file` (116-121). The `sample_config` dict has no `next_issue` key — correct for `confidence_first` default testing.

- `jsonschema` is **not a dependency** (confirmed absent from `pyproject.toml` runtime and dev extras). `test_config_schema.py` uses only structural JSON-key assertions. The "unknown strategy fails" requirement translates to `assert "<invalid>" not in strategy["enum"]` — a sentinel guard, not a runtime validation call.

- The existing sort tests will **not break** under ENH-1125's resolver if `confidence_first` is byte-identical to the current lambda (per ENH-1125 spec). Winner-only assertions (`test_next_issue.py`) and full-list assertions (`test_next_issues.py`) both continue to hold. The original "must update" framing overstated the scope — what's required is a green run + additive regression tests for `priority_first`.

**Strategic scope addition:**

- `TestBuildSortKey` was not explicitly called out in the original draft but is referenced by ENH-1125's wiring pass at `test_issues_search.py` as the resolver's home for unit coverage. Adding it here closes the gap between "validates config shape" (test_config.py) and "validates CLI integration" (test_next_issue.py / test_next_issues.py) — without it, the resolver's `priority_first` preset, custom `sort_keys`, and None-handling have no direct unit test.

**Validation convention precedent:**

- `NextIssueConfig.from_dict` is the first validating `from_dict` in the config package — every existing `from_dict` silently accepts unknown values. Tests must explicitly lock this new convention in with `pytest.raises(ValueError, match=...)`; otherwise future contributors will regress it to silent defaults.

**Documentation consistency gap discovered:**

- `--config` flag is documented for `next-issue` at `CLI.md:535` but missing from `next-issues` flag table (`CLI.md:545-550`). Unrelated to the core feature but discovered during line-by-line verification — fix alongside since both sections are being edited.

### Verification Findings (2nd refinement pass — 2026-04-16)

_Second pass added by `/ll:refine-issue --auto` after line-by-line verification of all claimed file:line references:_

**Prerequisites status confirmed:**
- `grep -r "NextIssueConfig\|build_sort_key" scripts/little_loops/` returns zero matches — neither ENH-1124 nor ENH-1125 has landed. CLI files still use the raw inline lambda. The hardcoded sort tuple at `next_issue.py:33-39` matches the issue's claim verbatim: `-(i.outcome_confidence if i.outcome_confidence is not None else -1), -(i.confidence_score if i.confidence_score is not None else -1), i.priority_int`.

**"Bonus fix" contradiction resolved — Step 7 IS a no-op:**
- The Proposed Solution at step 7 (line 72) says `--config` is "absent from the `next-issues` flag table" and proposes adding it. The later "Corrections Discovered" note (line 126) says it's already there. Direct inspection of `docs/reference/CLI.md:550` confirms `| \`--config\` | Path to project root |` is present. **Treat step 7's bonus-fix clause as superseded by the "Corrections Discovered" note — skip the add.** Only the sort-order line replacements at `:526` and `:541` are active.

**Downstream consumers of `ll-issues next-issue` (FSM loops) — CLI surface stable, no code changes:**
- `scripts/little_loops/loops/lib/cli.yaml:50-55` — shared `ll_issues_next_issue` fragment: `action: "ll-issues next-issue"`. Consumed by downstream loops.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:26` — consumes fragment
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (lines 21, 23, 31, 33, 72-73, 88-89, 103) — consumes fragment
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` (lines 11, 22, 81-82, 97-98, 110) — consumes fragment
- Since ENH-1125 preserves the `confidence_first` default (byte-identical to current lambda) and does NOT change the CLI invocation syntax, these consumers stay correct. **No code changes needed in loop YAMLs** — but verify after ENH-1125 lands that `ll-issues next-issue` still emits the same stdout format for exit_code evaluation.

**README.md next-issue references — no update needed:**
- `README.md:426-427` lists `ll-issues next-issue` and `ll-issues next-issues` in the CLI usage block with short descriptions ("Highest-confidence issue ID (for FSM loop use)", "All active issues in ranked order"). Descriptions remain accurate under `confidence_first` default — no change required.

**Minor line-number nits (implementer will see these — not blocking):**
- `conftest.py:65` is the `@pytest.fixture` decorator for `sample_config`; line 66 is the `def` line. The issue body says "66-113" — functionally correct (the body) but the fixture boundary starts at 65.
- `test_config.py:24` points at `DuplicateDetectionConfig` mid-tuple, not the start. The import block spans lines 9-35. Adding `NextIssueConfig` alongside `DuplicateDetectionConfig` remains correct guidance; the exact insertion line is anywhere within the tuple.

**Additional test files referencing `next-issue` but NOT requiring updates under ENH-1126:**
- `scripts/tests/test_issues_cli.py`, `test_builtin_loops.py`, `test_next_action.py`, `test_issue_parser.py`, `test_hooks_integration.py` — all reference `next-issue`/`next-issues`/`duplicate_detection` but cover orthogonal surfaces (CLI argparse, built-in loop definitions, hooks integration, next-*action* parallel command). No sort-order assertions. Verify on green run that none break under the `confidence_first` default.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. **Before writing any tests**, verify `scripts/little_loops/config/__init__.py` exports `NextIssueConfig` (ENH-1124 prerequisite) — if missing, all new `test_config.py` tests will fail at collection with `ImportError`
2. **Before writing `test_priority_first_strategy_overrides_default`**, verify that ENH-1125 has replaced the hardcoded sort lambda in `next_issue.py` and `next_issues.py` with `build_sort_key(config.issues.next_issue)` — otherwise the test may pass vacuously
3. **Verify `CLI.md:545-550` before executing step 7** — confirm whether `--config` is already present in the `next-issues` flag table; if it is, skip that step
4. **Verify `test_config.py:597-611` (`test_to_dict`)** — after ENH-1124 lands, check whether `to_dict()` serializes `next_issue`; if so, ensure it returns a `dict`, not a `NextIssueConfig` object (the `json.dumps(result)` call will catch any non-serializable value)
5. **For `test_priority_first_strategy_overrides_default`**: use `_write_config(temp_project_dir, {**sample_config, "issues": {**sample_config["issues"], "next_issue": {"strategy": "priority_first"}}})` — do NOT use the `config_file` fixture, which does not contain a `next_issue` key

## Acceptance Criteria

- `python -m pytest scripts/tests/test_next_issue.py scripts/tests/test_next_issues.py scripts/tests/test_config.py scripts/tests/test_config_schema.py scripts/tests/test_issues_search.py -v` passes with no failures
- `ruff check scripts/` passes
- All documentation files updated with accurate descriptions of the new config block
- No existing test is deleted; assertion text in existing sort tests preserved unless `confidence_first` preset diverges from today's hardcoded lambda
- New `TestBuildSortKey` class covers `confidence_first`, `priority_first`, custom `sort_keys`, and both None-sentinel paths (`1` for desc, `9999` for asc)
- `TestNextIssueConfig` covers `ValueError` on unknown strategy and unknown sort key (first validating `from_dict` in the config package — locked in by test)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-16_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- ENH-1124 (NextIssueConfig dataclass) must be complete before implementation: `NextIssueConfig` is absent from `little_loops.config` exports — all new `test_config.py` tests will fail at collection with `ImportError`
- ENH-1125 (sort resolver + CLI wiring) must be complete before implementation: `build_sort_key` doesn't exist; `test_priority_first_strategy_overrides_default` would pass vacuously without it
- Both are structural prerequisites — ENH-1126 can be planned now but cannot begin implementation until ENH-1124 + ENH-1125 are in `completed/`

## Resolution

- **Tests added**:
  - `TestNextIssueConfig` in `scripts/tests/test_config.py` (6 methods): defaults, `from_dict` strategy/empty, `pytest.raises` on unknown strategy and unknown sort key, `IssuesConfig` parse-through. Plus one-line assertion in `test_from_dict_with_defaults` and `NextIssueConfig` added to the module-level import.
  - `test_issues_next_issue_in_schema` in `test_config_schema.py`: structural assertions on `issues.next_issue.strategy.enum` (sentinel guard — `jsonschema` is not a dependency).
  - `TestBuildSortKey` in `test_issues_search.py` (6 methods): `confidence_first` byte-parity, `priority_first` preset, custom `sort_keys` override, None-sentinel paths (`1` for desc, `9999` for asc), `ValueError` on unknown strategy via direct instantiation bypass.
  - `test_priority_first_strategy_overrides_default` in both `test_next_issue.py` and `test_next_issues.py`: end-to-end CLI regression proving the strategy knob is wired (uses inline `{**sample_config, "issues": {**sample_config["issues"], "next_issue": {"strategy": "priority_first"}}}` since the `config_file` fixture has no `next_issue` key).
- **Existing regression guards held**: `TestNextIssueSorting` (4 tests) and `TestNextIssuesRankedOrder` (2 tests) pass unchanged — `confidence_first` is byte-identical to the legacy lambda as promised.
- **Docs updated**:
  - `docs/reference/CLI.md:526,:541` — sort-order lines now reference `issues.next_issue.strategy` with `confidence_first` default. `--config` flag in `next-issues` table was already present (pre-satisfied, skipped).
  - `docs/reference/API.md` — added `next_issue: NextIssueConfig` field to the `IssuesConfig` block; new `### NextIssueConfig` section after `### DuplicateDetectionConfig`; `**Strategy**:` + `**Configuration**:` blocks inserted into both `next-issue` and `next-issues` CLI sections.
  - `docs/reference/CONFIGURATION.md` — added `next_issue` to the full `issues` example, two rows in the options table, and a new `### issues.next_issue` subsection with two JSON examples.
  - `docs/guides/LOOPS_GUIDE.md:2080` — extended `ll_issues_next_issue` fragment description.
- **Verification**: `python -m pytest scripts/tests/` → 4949 passed, 5 skipped; `ruff check scripts/` → All checks passed.

## Session Log
- `/ll:manage-issue` - 2026-04-17T19:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9dea2f7-a026-41f0-8819-fee1d6b41b64.jsonl`
- `/ll:ready-issue` - 2026-04-17T18:47:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e3524e92-3759-4e68-9b5a-0d8957383583.jsonl`
- `/ll:refine-issue` - 2026-04-16T20:22:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e18081d-8068-4ea1-96f9-98b4dd8ce46c.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/418956b8-6e25-4bef-a5bf-3bbf5a213336.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/360a9ca9-1f29-487b-ada1-c4e4af3801ba.jsonl`
- `/ll:wire-issue` - 2026-04-16T20:16:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8280dfb9-0ddb-4195-8bf5-f7bc2d5e0fe1.jsonl`
- `/ll:refine-issue` - 2026-04-16T20:11:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4793dc2b-5be1-4184-9eca-bb2c45f10d62.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed68bd1a-5a6f-4d92-94fd-8ff3a80f7d09.jsonl`

---

**Open** | Created: 2026-04-16 | Priority: P3
