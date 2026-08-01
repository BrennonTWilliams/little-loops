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
testable: true
labels:
- cli
- issues
- gates
---

# ENH-2946: `ll-issues set-flags --from-notes` + extended `format-check`

## Summary

`skills/confidence-check/SKILL.md` (488 lines) ends with four flag-setting phases that are literal phrase-list scans; `skills/format-issue/SKILL.md` (457 lines) embeds file selection, a keyword-count `testable` inference, and a narrated check-mode. Move all of it into `ll-issues`; keep the skills' genuine code-reading judgment.

## Implementation Status

_Audited against the code 2026-08-01. **One of three steps is partially
landed; the issue is correctly still `open`.** Read this before starting —
`.claude/CLAUDE.md` currently describes more of this issue as shipped than
actually is._

| Step | State | Evidence |
|------|-------|----------|
| 1. `set-flags --from-notes` | **Not started** | No `set-flags` subcommand (`ll-issues` rejects it as an invalid choice); no `FlagRule`, `FLAG_RULES`, `FlagResult`, or `apply_flags_from_notes` anywhere in `scripts/little_loops/` |
| 2a. `format-check --next` | **Not started** | `format-check --help` has no `--next`; `select_next_issue` does not exist. The intended helper `find_highest_priority_issue` **does** (`issue_parser.py:2011`) |
| 2b. `testable` inference | **Landed, was incomplete** | `infer_testable` (`issue_parser.py:528`), `_TESTABLE_SIGNAL_KEYWORDS`/`_TESTABLE_KEYWORD_THRESHOLD` (`L506-519`), `check_format_gaps` populating `gaps.testable` (`L489-498`), `FormatGaps.testable` field + `has_gaps` + `to_dict` |
| 3. Slim both skills | **Not started** | `skills/confidence-check/SKILL.md` is 491 lines (up from the 488 this issue recorded); `skills/format-issue/SKILL.md` is 457, unchanged. Phrase lists still present in the skill body |

### How 2b landed, and the defect it shipped with

The `testable` work was committed inside **`dd057ef0` — a fallback commit for
FEAT-2948** (`"Automated fallback commit - command exited before
completion."`), an unrelated issue about `ll-loop scaffold-eval`. It landed
the dataclass field, the `has_gaps` clause, and the `to_dict` key, but **not**
the renderer: `_print_gaps` (`cli/issues/format_check.py`) had no `testable`
loop.

Consequence: in text mode — the default — an issue whose only gap was
`testable` printed a header, printed nothing, and exited 1. Across the active
backlog that was **19 of 58 issues rendering blank**, including BUG-2963,
which is itself about scoped-completion commits closing issues without their
implementation. No test caught it; `test_ll_issues_format_check.py` only
asserted `"testable": []` inside a `to_dict` check, and
`test_issue_parser.py:3951-3989` covers `infer_testable` in isolation, never
`check_format_gaps`'s use of it.

**Fixed 2026-08-01** (separate commit, outside this issue): the `_print_gaps`
loop, the subparser `help=` and `cmd_format_check` docstring class lists,
`cli/issues/__init__.py:109`'s usage banner, and three regression tests in
`TestFormatCheckTestableRendering` — including a structural guard that
enumerates `dataclasses.fields(FormatGaps)` and asserts every class renders,
so a future class cannot repeat this.

### Documentation drift to correct as part of this issue

`.claude/CLAUDE.md`'s `ll-issues` entry documents **`set-flags` and
`format-check --next` as shipped**, with full flag lists
(`--from-notes <file|->`, `--dry-run`, `--depth-moderate-or-deep`, `--json`,
`--next resolves the highest-priority active issue with no type filter`).
Neither exists. That text was added by commit **`46969c7c`**, whose subject
and body are entirely about ENH-2949 (`ll-loop audit --json`) — documentation
running ahead of code, in a commit for a different issue.

Because CLAUDE.md is loaded into every session's context, this actively
causes callers to invoke commands that do not exist. Either correct the
CLAUDE.md entry now to describe only what ships, or land steps 1 and 2a so the
entry becomes true. Do not close this issue with the entry still inaccurate.
_(Same failure mode as ENH-2944, reopened for the stripped `normalize`
wiring in `3e76f972`.)_

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

_Status per step is tracked in "Implementation Status" above._

1. `set-flags --from-notes` with rules-as-data + tests per flag. **Not
   started.**
2. `format-check --next` + `testable` inference + tests.
   - 2a. `--next` target selection via `find_highest_priority_issue`
     (`issue_parser.py:2011`). **Not started.**
   - 2b. `testable` inference. **Landed** (`dd057ef0`), and its text-mode
     rendering defect fixed 2026-08-01. Remaining gap: `check_format_gaps`'s
     population of `gaps.testable` still has no direct unit test —
     `test_issue_parser.py:3951-3989` tests `infer_testable` standalone, and
     the new `TestFormatCheckTestableRendering` tests reach it only through
     the CLI. Add one when finishing this step.
3. Slim both skills (~100 lines from confidence-check, ~80 from format-issue).
   **Not started** — neither skill has shrunk; confidence-check has grown to
   491 lines.
4. **Correct `.claude/CLAUDE.md`'s `ll-issues` entry** so it describes only
   shipped surface — or land steps 1/2a first and leave it. See
   "Documentation drift" above. Required either way before closing.

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
- [x] `testable` inference exists and is reachable from `check_format_gaps`
      (`issue_parser.py:489-498`, `L528`)
- [x] Every `FormatGaps` class reaches **text** output, not just
      `--format json` — a class counted by `has_gaps` with no `_print_gaps`
      loop exits 1 with an empty report. Enforced by
      `test_ll_issues_format_check.py::TestFormatCheckTestableRendering::test_every_format_gaps_field_is_rendered`,
      which enumerates `dataclasses.fields(FormatGaps)`. _Added after the
      `testable` regression; applies to any class this issue adds._
- [ ] `check_format_gaps`'s `testable` population has a direct unit test in
      `test_issue_parser.py`, not only CLI-level coverage
- [ ] `.claude/CLAUDE.md`'s `ll-issues` entry names only shipped subcommands
      and flags — verified by invoking each documented one
