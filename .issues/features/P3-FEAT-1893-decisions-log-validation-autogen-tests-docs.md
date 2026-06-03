---
id: FEAT-1893
title: "Decisions Log \u2014 Validation Integration, Auto-generation, Tests, and Docs"
type: FEAT
priority: P3
status: done
labels:
- decisions-log
- validation
- tests
- docs
parent: FEAT-948
size: Large
discovered_date: 2026-06-02
completed_at: 2026-06-03 07:34:14+00:00
depends_on:
- FEAT-1891
decision_needed: false
confidence_score: 97
outcome_confidence: 80
score_complexity: 13
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 22
---

# FEAT-1893: Decisions Log — Validation Integration, Auto-generation, Tests, and Docs

## Summary

Integrate the decisions log into the validation pipeline (`ready-issue`, `verify-issues`, `format-issue`), implement auto-generation from completed issues, write comprehensive tests for graceful degradation and exception suppression, and update all documentation. Depends on FEAT-1891 (core CRUD layer); can be worked in parallel with FEAT-1892.

## Current Behavior

The decisions log (`generate_from_completed`) is a stub in both `decisions.py` and `cli/issues/decisions.py`. The validation pipeline (`ready-issue`, `verify-issues`, `format-issue`) has no decisions gate; no graceful degradation, exception suppression, or auto-generation tests exist; documentation is incomplete for the decisions log persistence layer.

## Expected Behavior

`generate_from_completed(config)` is fully implemented and wired into the CLI. The validation pipeline queries the decisions log (gracefully skipping when `.ll/decisions.yaml` is absent), surfaces rule violations, and suppresses false positives via exception entries. Tests cover graceful degradation, exception suppression, and auto-generation. Documentation reflects the decisions log as a first-class persistence layer.

## Parent Issue

Decomposed from FEAT-948: Rules and Decisions Log for Issue Compliance

## Integration Map

### Files to Modify

- `scripts/little_loops/decisions.py` — add `generate_from_completed(config)` function; current public API: `load_decisions`, `save_decisions`, `add_entry`, `list_entries`, `resolve_active`, `set_outcome`
- `scripts/little_loops/cli/issues/decisions.py` — replace stub `generate` implementation at lines 205–207 (currently prints `"generate: not yet implemented (see FEAT-1893)"` and returns 0) with a call to `generate_from_completed(config)`
- `commands/ready-issue.md` — add Decisions Gate check to Section 2 validation pipeline, after the Learning Test Gate block (currently ends around line 184); result rows go into the existing `## VALIDATION` table
- `commands/verify-issues.md` — add rule violation step; current verdict categories defined at lines 67–80 (`VALID`, `OUTDATED`, `RESOLVED`, `INVALID`, `NEEDS_UPDATE`, `REGRESSION_LIKELY`, `POSSIBLE_REGRESSION`, `DEP_ISSUES`) — no decisions category present
- `skills/format-issue/SKILL.md` — add decisions log query step (none exists in any of its process steps currently)
- `scripts/tests/test_decisions.py` — add `TestDecisionsGracefulDegradation`, `TestDecisionsExceptionSuppression`, `TestGenerateFromCompleted` classes
- `scripts/tests/test_cli_decisions.py` — expand `TestDecisionsCLIGenerate` beyond stub assertion (`assert "FEAT-1893" in stdout`) once real implementation lands
- `scripts/tests/test_create_extension_wiring.py` — append `TestFeat948DecisionsWiring` class at end of file
- `docs/ARCHITECTURE.md` — add decisions log as a persistence layer alongside `.ll/history.db` and issue files
- `.claude/CLAUDE.md` — update Key Directories (add `decisions.yaml`) and CLI Tools (add `ll-issues decisions` with subcommand list)
- `docs/reference/COMMANDS.md` — add guarded `**Decisions log:**` side-effect notes to `### /ll:decide-issue`, `### /ll:tradeoff-review-issues`, `### /ll:go-no-go`
- `docs/reference/API.md` — add `#### DecisionsConfig` subsection after `#### DesignTokensConfig`; BRConfig `decisions` row already present at line 120
- `docs/reference/CLI.md` — remove `(stub; see FEAT-1893)` from the `generate` row in the `#### ll-issues decisions` subcommand table at line 1268 [Agent 2 finding]

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_history/parsing.py:289` — `scan_completed_issues(issues_dir: Path, category_dirs: list[str] | None = None) -> list[CompletedIssue]`; used by `generate_from_completed`
- `scripts/little_loops/issue_history/parsing.py:351` — `scan_completed_issues_from_db(db_path: Path) -> list[CompletedIssue]`; preferred scanner when `.ll/history.db` exists; returns `[]` on failure (safe fallback)
- `scripts/little_loops/config/features.py:409` — `DecisionsConfig` dataclass (`enabled: bool`, `log_path: str`, `auto_generate: list[str]`); `auto_generate` is declared but not yet acted on anywhere
- `scripts/little_loops/config/core.py:207` — `BRConfig._decisions` instantiation; `decisions` property at line 275
- `scripts/little_loops/cli/issues/__init__.py:680` — `add_decisions_parser()` called; dispatch to `cmd_decisions(config, args)` at line 739–740
- `scripts/little_loops/decisions_sync.py` — imports `list_entries`, `resolve_active`, `_DEFAULT_LOG_PATH`, `RuleEntry` from `decisions.py`; invoked by `ll-issues decisions sync`; not affected by `generate_from_completed` addition but documents the dependency [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — line 1268 `generate` row in `#### ll-issues decisions` table carries `(stub; see FEAT-1893)` annotation; remove once implementation lands [Agent 2 finding]

### Already Complete (no changes needed)

- `docs/reference/CONFIGURATION.md` — `decisions` section (lines 625–634) and Full Configuration Example entry (lines 237–241) already present
- `config-schema.json` — `decisions` block already present (lines 511–533)
- `scripts/tests/test_feat1894_doc_wiring.py` — per-feature doc wiring for CLI subcommand already covers `commands/help.md`, `docs/reference/CLI.md`, `CONTRIBUTING.md`

### Tests

- `scripts/tests/test_decisions.py` — add to existing file (TestLoadDecisions through TestSyncToLocalMd already written)
- `scripts/tests/test_cli_decisions.py` — expand `TestDecisionsCLIGenerate` (file already has 6 test classes); **`test_generate_stub` will BREAK** — currently asserts `"FEAT-1893" in captured.out` at line 578; this assertion fails the moment the stub is replaced; must rename to `test_generate_from_completed_writes_entries` and assert on real output [Agent 3 finding]
- `scripts/tests/test_create_extension_wiring.py` — new `TestFeat948DecisionsWiring` class asserting 5 doc surfaces and COMMANDS.md side-effect notes on 3 commands

## Proposed Solution

### Step 8 — Auto-generation from Completed Issues

Add `generate_from_completed(config: BRConfig)` to `scripts/little_loops/decisions.py`:
- Check if `.ll/history.db` exists; if so, call `scan_completed_issues_from_db(Path(config.project_root) / ".ll/history.db")` from `scripts/little_loops/issue_history/parsing.py:351`; otherwise fall back to `scan_completed_issues(Path(config.issues_base_dir))` at line 289
- For each `CompletedIssue`, create a `DecisionEntry` and call `add_entry(entry, path)` to persist
- Return count of entries added
- Replace the stub in `scripts/little_loops/cli/issues/decisions.py:205-207` with a call to `generate_from_completed(config)`

> Auto-triggering from manage-issue requires detecting manage-issue invocation in the `issue-completion-log.sh` hook OR exposing this as a manual command only. The manual command path is sufficient for MVP.

### Step 9 — Validation Integration

> **Graceful degradation**: All integrations MUST gracefully skip decisions checks when `.ll/decisions.yaml` does not exist. The governance feature is opt-in — absence of the file is not an error condition. Use `ll-issues decisions list ... 2>/dev/null || true` in shell contexts; in Python, `load_decisions(path)` already returns `[]` when the file is absent.

**`commands/ready-issue.md`** — add Decisions Gate check to Section 2 after the Learning Test Gate block (currently ends around line 184):
- `ll-issues decisions list --type rule --active-only --format json 2>/dev/null || true`
- If output non-empty, check each rule against the issue under review
- Suppress violations where a matching `exception` entry with `rule_ref` exists (`ll-issues decisions list --type exception`)
- Surface results as rows in the existing `## VALIDATION` table (PASS/FAIL/SKIPPED)

**`commands/verify-issues.md`** — add query step for rule violations (current violation categories at lines 67–80):
- Surface active `required` rule violations as a new violation subtype
- Suppress false positives where an `exception` entry with matching `rule_ref` covers the issue

**`skills/format-issue/SKILL.md`** — add decisions log query step using identical graceful-skip pattern; none of the skill's current process steps reference decisions

### Steps 10-11 — Tests and Docs

**Test files (`scripts/tests/test_decisions.py` — add to existing file after `TestSyncToLocalMd`):**
- `TestDecisionsGracefulDegradation` — assert that `load_decisions(absent_path)` returns `[]` and that callers (`list_entries`, `resolve_active`) handle empty result without error; validates graceful skip contract
- `TestDecisionsExceptionSuppression` — write a `RuleEntry` + `ExceptionEntry(rule_ref=rule.id)` to a temp log, call `list_entries(path, type="exception")` and filter by `rule_ref`, assert the suppressor is found and the violation is hidden
- `TestGenerateFromCompleted` — mock `scan_completed_issues` returning 2 `CompletedIssue` instances, call `generate_from_completed(config)`, assert 2 entries written and `load_decisions()` returns them

**`scripts/tests/test_cli_decisions.py` — expand `TestDecisionsCLIGenerate`:**
- Current stub test only asserts `"FEAT-1893" in stdout`; when implementation lands, add assertion that entries appear in `ll-issues decisions list` output after running `generate --from=completed`

**Docs:**
- `docs/ARCHITECTURE.md` — document decisions log (`.ll/decisions.yaml`) as a persistence layer alongside `.ll/history.db` and `.issues/`
- `.claude/CLAUDE.md` — update Key Directories section (add `  decisions.yaml` entry) and CLI Tools section (add `ll-issues decisions` with subcommands: `list`, `add`, `outcome`, `sync`, `generate`)

### Wiring (included per TDD mode)

- Step 15: `docs/reference/CONFIGURATION.md` — already complete; `decisions` section and Full Configuration Example entry present (no changes needed)
- Step 16: `docs/reference/API.md` — add `#### DecisionsConfig` subsection after `#### DesignTokensConfig` using 4-column `Key | Type | Default | Description` table for `enabled`, `log_path`, `auto_generate`; `decisions: DecisionsConfig` row in BRConfig Properties table already present at line 120
- Step 21: Add `TestFeat948DecisionsWiring` class to `scripts/tests/test_create_extension_wiring.py` — assert `decisions` is documented in `commands/help.md`, `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md`, `.claude/CLAUDE.md`, and `CONTRIBUTING.md`; assert COMMANDS.md side-effect notes present on `decide-issue`, `tradeoff-review-issues`, `go-no-go`
- Step 22: `docs/reference/COMMANDS.md` — add `**Decisions log:**` note to `### /ll:decide-issue`, `### /ll:tradeoff-review-issues`, `### /ll:go-no-go` using the pattern: `**Decisions log:** When decisions log is enabled, appends a \`decision\` entry to \`.ll/decisions.yaml\`. Silently skipped if \`.ll/decisions.yaml\` is absent.`

## Implementation Steps

1. **`generate_from_completed`** — add function to `scripts/little_loops/decisions.py`; import `scan_completed_issues_from_db` and `scan_completed_issues` from `scripts/little_loops/issue_history/parsing.py`; use DB scanner when `.ll/history.db` exists, filesystem scanner as fallback
2. **Implement CLI stub** — in `scripts/little_loops/cli/issues/decisions.py:205-207`, replace the stub block with a call to `generate_from_completed(config)` and print entry count; also update the `gen_p = subsubs.add_parser(...)` help string at line 155 (currently `"Generate decisions log entries from completed issues (stub; see FEAT-1893)"`) to remove the `(stub; see FEAT-1893)` suffix
3. **ready-issue.md decisions gate** — after the Learning Test Gate block (around line 184 in `commands/ready-issue.md`), add a `#### Decisions Gate` step using `ll-issues decisions list --type rule --active-only --format json 2>/dev/null || true`; check each required rule; suppress via matching exception `rule_ref`; add PASS/FAIL rows to VALIDATION table; skip entirely if output is empty
4. **verify-issues.md decisions step** — add a rule violation subtype after the current verdict categories block (`commands/verify-issues.md:67-80`); use same `ll-issues decisions list` pattern with graceful skip
5. **format-issue/SKILL.md decisions step** — add a decisions log check step with identical graceful-skip pattern (`2>/dev/null || true`)
6. **Tests — `test_decisions.py`** — append `TestDecisionsGracefulDegradation`, `TestDecisionsExceptionSuppression`, `TestGenerateFromCompleted` classes after existing `TestSyncToLocalMd`
7. **Tests — `test_cli_decisions.py`** — expand `TestDecisionsCLIGenerate` beyond stub assertion to verify real output
8. **`TestFeat948DecisionsWiring`** — append class to `scripts/tests/test_create_extension_wiring.py` asserting 5 doc surfaces and COMMANDS.md side-effect notes on 3 commands; run `python -m pytest scripts/tests/test_create_extension_wiring.py -v` to verify
9. **docs/ARCHITECTURE.md** — add `.ll/decisions.yaml` to persistence layer section
10. **.claude/CLAUDE.md** — add `decisions.yaml` to Key Directories and `ll-issues decisions` to CLI Tools
11. **docs/reference/API.md** — add `#### DecisionsConfig` subsection after `#### DesignTokensConfig`
12. **docs/reference/COMMANDS.md** — add `**Decisions log:**` guarded note to `decide-issue`, `tradeoff-review-issues`, `go-no-go` sections
13. **Verify** — run `python -m pytest scripts/tests/test_decisions.py scripts/tests/test_cli_decisions.py scripts/tests/test_create_extension_wiring.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

14. Update `docs/reference/CLI.md:1268` — remove `(stub; see FEAT-1893)` suffix from the `generate` subcommand description in the `#### ll-issues decisions` table
15. Run `python -m pytest scripts/tests/test_feat1894_doc_wiring.py -v` — confirm the 4 wiring assertion classes still pass after CLAUDE.md and CLI.md are updated (they assert on the string `"decisions"`, which will survive; but verify no regressions)

## Use Case

**Compliance check**: A user runs `/ll:ready-issue 948`. The command queries the log, finds `NAMING-001` (enforcement: required), and confirms the issue filename matches `P[0-5]-TYPE-NNN-slug.md` — surfaces as a passing check, no manual cross-referencing needed.

**Exception suppression**: A user runs `/ll:verify-issues` after a hotfix is merged with a non-standard filename. With the log, it finds `exception` entry `NAMING-002` pointing `rule_ref: NAMING-001` for that issue, suppresses the false positive, and surfaces the exception note instead.

## Acceptance Criteria

- [ ] `generate_from_completed(config)` in `decisions.py` using `scan_completed_issues()` or `scan_completed_issues_from_db()`
- [ ] `commands/ready-issue.md` queries decisions log; suppresses violations with matching `exception` entry; gracefully skips when `decisions.yaml` absent
- [ ] `commands/verify-issues.md` surfaces rule violations; suppresses false positives via `exception` entries; gracefully skips when absent
- [ ] `skills/format-issue/SKILL.md` adds decisions log query step; gracefully skips when absent
- [ ] Graceful degradation exercised in tests (not just stated in spec)
- [ ] Exception suppression tested via `rule_ref` lookup
- [ ] `docs/ARCHITECTURE.md` documents decisions log as a persistence layer
- [ ] `.claude/CLAUDE.md` Key Directories and CLI Tools updated
- [ ] `docs/reference/CONFIGURATION.md` has `decisions` block in Full Configuration Example
- [ ] `docs/reference/API.md` has `decisions: DecisionsConfig` in BRConfig Properties table
- [ ] `TestFeat948DecisionsWiring` in `test_create_extension_wiring.py` passes
- [ ] `docs/reference/COMMANDS.md` has side-effect notes on `decide-issue`, `tradeoff-review-issues`, `go-no-go`

## Impact

- **Priority**: P3 — decisions log is an opt-in governance feature; blocking no critical paths
- **Effort**: Large — spans 4+ files, validation commands, tests, and docs
- **Risk**: Low — all integrations use graceful-skip (`2>/dev/null || true`); absent `decisions.yaml` is a no-op
- **Breaking Change**: No; stub replacement is additive; breaking test `test_generate_stub` must be renamed (see Proposed Solution)

## Status

**Open** | Created: 2026-06-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-03T07:19:46 - `9d21e717-1df5-4cf6-8b1e-69a5b345bd5b.jsonl`
- `/ll:refine-issue` - 2026-06-03T07:07:35 - `a17d50b9-ee44-407f-8e30-7c65a95dacfb.jsonl`
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:wire-issue` - 2026-06-03T00:00:00Z - ``
- `/ll:confidence-check` - 2026-06-03T00:00:00Z - `c618ce73-7ab1-4bd7-a3ed-76da43c124d3.jsonl`
