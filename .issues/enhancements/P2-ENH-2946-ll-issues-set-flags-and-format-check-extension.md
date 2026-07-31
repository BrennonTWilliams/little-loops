---
id: ENH-2946
title: "ll-issues set-flags --from-notes and format-check extension: phrase-scan mechanics out of confidence-check and format-issue"
type: ENH
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- issues
- gates
---

# ENH-2946: `ll-issues set-flags --from-notes` + extended `format-check`

## Summary

`skills/confidence-check/SKILL.md` (488 lines) ends with four flag-setting phases that are literal phrase-list scans; `skills/format-issue/SKILL.md` (457 lines) embeds file selection, a keyword-count `testable` inference, and a narrated check-mode. Move all of it into `ll-issues`; keep the skills' genuine code-reading judgment.

## Current Behavior

- confidence-check Phase 4.6 (L362–387): scan risk-factor text for an 11-phrase list ("open decision", "either/or", "Option A/B", …) → `decision_needed: true`. Phase 4.7 (L389–413): 6 phrases → `missing_artifacts: true`. Phase 4.9 (L415–435): 6 phrases → `implementation_order_risk: true`. Phase 4.10 (L437–463): 8 phrases + `score_test_coverage <= 10` → `spike_needed: true`. The in-file precedent already exists: L132–149 delegates the Program Design gate to `ll-issues format-check` with the note "Do **not** re-judge specificity yourself; the CLI is the single source of truth."
- format-issue: highest-priority-file selection via nested shell loops (L96–139), the `testable` doc-only keyword counter ("2+ distinct keyword matches", L170–181), check-mode counting with narrated exit codes (L388–400).

## Expected Behavior

- `ll-issues set-flags <id> --from-notes <file|-> [--dry-run] --json` — runs the phrase-list + numeric-gate rules over the skill's written findings and stamps `decision_needed` / `missing_artifacts` / `implementation_order_risk` / `spike_needed` frontmatter. Phrase lists live in Python (single source of truth).
- `ll-issues format-check` extended with: target selection (`--next` highest-priority open issue, matching format-issue's current selection rules) and the `testable` inference as a gap/annotation; its existing `--format json` + exit codes replace format-issue's narrated check-mode (EPIC convention).
- confidence-check keeps Phases 2/2b (readiness/outcome criteria against actual code) and writes its findings; format-issue keeps §3.5 content-quality analysis and §4.0 confidence filtering.

## Proposed Solution

Reuse `frontmatter.update_frontmatter`, `issue_parser.check_format_gaps`, `find_highest_priority_issue`, and the existing `format-check` subcommand plumbing. `set-flags` composes with existing `check-flag` gates (which FSM loops already consume).

## Implementation Steps

1. `set-flags --from-notes` with rules-as-data + tests per flag.
2. `format-check --next` + `testable` inference + tests.
3. Slim both skills (~100 lines from confidence-check, ~80 from format-issue).

## Program Design

### Types

- `FlagRule: dataclass`
  - `flag: str`
  - `phrases: tuple[str, ...]`
  - `numeric_gate: Callable[[IssueInfo], bool] | None`
- `FLAG_RULES: tuple[FlagRule, ...]` — the four rules (decision_needed, missing_artifacts, implementation_order_risk, spike_needed) as data
- `FlagResult: dataclass`
  - `id: str`
  - `set_flags: dict[str, bool]`
  - `matched_phrases: dict[str, list[str]]`

### Signatures

- `apply_flags_from_notes(issue_id: str, notes: str, dry_run: bool) -> FlagResult` — phrase scan + `score_test_coverage <= 10` gate; writes via `frontmatter.update_frontmatter`
- `select_next_issue(issues_dir: Path) -> Path` — `format-check --next` target selection via `issue_parser.find_highest_priority_issue`
- `infer_testable(issue: IssueInfo) -> bool` — doc-only keyword counter (2+ distinct matches)

### Call Path

- `apply_flags_from_notes()` -> `update_frontmatter()` (existing, `frontmatter.py`)
- `select_next_issue()` -> `find_highest_priority_issue()` (existing, `issue_parser.py`)
- `infer_testable()` extends `check_format_gaps()` (existing, `issue_parser.py`)

## Scope Boundaries

- In scope: `set-flags --from-notes`, `format-check --next` + `testable` inference; slimming confidence-check Phases 4.6–4.10 and format-issue's mechanical sections.
- Out of scope: confidence-check Phases 2/2b (code-reading judgment), format-issue §3.5/§4.0 content-quality analysis, changing flag semantics consumed by autodev.

## Impact

- **Priority**: P2 - Makes the flags autodev routes on (spike_needed, decision_needed, …) deterministic instead of model-recall-dependent
- **Effort**: Small-Medium - Rules-as-data + one selection helper
- **Risk**: Low - `--dry-run` supported; per-flag fixtures

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] All four flag rules produce identical results to the prose spec (fixture notes per phrase list)
- [ ] confidence-check contains no phrase lists; it pipes findings to `set-flags`
- [ ] format-issue's file selection/check-mode are CLI calls with deterministic exit codes
- [ ] pytest coverage in `scripts/tests/`
