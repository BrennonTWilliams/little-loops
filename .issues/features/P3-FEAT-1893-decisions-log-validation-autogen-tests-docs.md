---
id: FEAT-1893
title: "Decisions Log — Validation Integration, Auto-generation, Tests, and Docs"
type: FEAT
priority: P3
parent: FEAT-948
size: Large
discovered_date: 2026-06-02
depends_on: [FEAT-1891]
---

# FEAT-1893: Decisions Log — Validation Integration, Auto-generation, Tests, and Docs

## Summary

Integrate the decisions log into the validation pipeline (`ready-issue`, `verify-issues`, `format-issue`), implement auto-generation from completed issues, write comprehensive tests for graceful degradation and exception suppression, and update all documentation. Depends on FEAT-1891 (core CRUD layer); can be worked in parallel with FEAT-1892.

## Parent Issue

Decomposed from FEAT-948: Rules and Decisions Log for Issue Compliance

## Proposed Solution

### Step 8 — Auto-generation from Completed Issues

Add `generate_from_completed(config)` to `scripts/little_loops/decisions.py`:
- Use `scan_completed_issues(issues_dir: Path, ...)` from `scripts/little_loops/issue_history/parsing.py:289` (or `scan_completed_issues_from_db(db_path: Path)` at line 351 when `.ll/history.db` is available)
- Exposes as `ll-issues decisions generate --from=completed` (stub registered in FEAT-1892's CLI; full implementation here)

> Auto-triggering from manage-issue requires detecting manage-issue invocation in the `issue-completion-log.sh` hook OR exposing this as a manual command only. The manual command path is sufficient for MVP.

### Step 9 — Validation Integration

> **Graceful degradation**: All integrations MUST gracefully skip decisions checks when `.ll/decisions.yaml` does not exist. The governance feature is opt-in — absence of the file is not an error condition.

**`commands/ready-issue.md`** — add decisions log query step to Section 2 (lines 139-183):
- Load active `required` rules from `.ll/decisions.yaml` (if file exists)
- Check each rule against the issue under review
- Suppress violations where a matching `exception` entry with `rule_ref` exists

**`commands/verify-issues.md`** — add query step for rule violations (current violation categories at lines 67-80):
- Surface active `required` rule violations
- Suppress false positives where an `exception` entry with matching `rule_ref` covers the issue

**`skills/format-issue/SKILL.md`** — add decisions log query step alongside ready-issue and verify-issues as a log reader

### Steps 10-11 — Tests and Docs

**Test files:**
- `scripts/tests/test_decisions.py` — any remaining coverage not written in FEAT-1891:
  - Graceful degradation: validation commands skip decisions checks when `decisions.yaml` absent
  - Exception suppression: `rule_ref` lookup correctly suppresses `verify-issues` violations
  - `generate --from=completed` stub integration
- `scripts/tests/test_cli_decisions.py` — any `generate` CLI coverage deferred from FEAT-1892

**Docs:**
- `docs/ARCHITECTURE.md` — document new log as a persistence layer
- `.claude/CLAUDE.md` — update Key Directories and CLI Tools sections (add `ll-issues decisions` to CLI Tools, `decisions.yaml` to Key Directories)

### Wiring (included per TDD mode)

- Step 15: Update `docs/reference/CONFIGURATION.md` — add `decisions` config block to Full Configuration Example and a table row in Configuration Sections
- Step 16: Update `docs/reference/API.md` — add `decisions: DecisionsConfig` row to the `BRConfig` Properties table
- Step 21: Add `TestFeat948DecisionsWiring` class to `scripts/tests/test_create_extension_wiring.py` — assert `decisions` is documented in `commands/help.md`, `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md`, `.claude/CLAUDE.md`, and `CONTRIBUTING.md`
- Step 22: Update `docs/reference/COMMANDS.md` — add side-effect note to `/ll:decide-issue`, `/ll:tradeoff-review-issues`, and `/ll:go-no-go` description rows stating each appends a `decision` entry to `.ll/decisions.yaml` (guarded: silently skipped if file absent)

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

## Session Log
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
