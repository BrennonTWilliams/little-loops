---
id: ENH-2946
title: 'll-issues set-flags --from-notes and format-check extension: phrase-scan mechanics
  out of confidence-check and format-issue'
type: ENH
priority: P2
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-02T00:26:21Z'
parent: EPIC-2938
epic: EPIC-2938
testable: true
relates_to:
- ENH-2944
labels:
- cli
- issues
- gates
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# ENH-2946: `ll-issues set-flags --from-notes` + extended `format-check`

## Summary

`skills/confidence-check/SKILL.md` (488 lines) ends with four flag-setting phases that are literal phrase-list scans; `skills/format-issue/SKILL.md` (457 lines) embeds file selection, a keyword-count `testable` inference, and a narrated check-mode. Move all of it into `ll-issues`; keep the skills' genuine code-reading judgment.

## Implementation Status

_Implemented 2026-08-01 via `/ll:manage-issue`._

| Step | State | Evidence |
|------|-------|----------|
| 1. `set-flags --from-notes` | **Done** | `scripts/little_loops/cli/issues/set_flags.py` — `FlagRule`, `FLAG_RULES`, `FlagResult`, `apply_flags_from_notes()`; registered as `ll-issues set-flags` |
| 2a. `format-check --next` | **Done** | `format_check.py`'s `add_format_check_parser`/`cmd_format_check` gained `--next`, wired to `find_highest_priority_issue()`, three-way mutex with `issue_id`/`--all`, empty-backlog exit 1 |
| 2b. `testable` inference | **Done** | Already landed; added a direct unit test for `check_format_gaps`'s own `testable` population (`test_issue_parser.py::TestCheckFormatGapsTestablePopulation`) |
| 3. Slim both skills | **Done** | `skills/confidence-check/SKILL.md` Phases 4.6/4.7/4.9/4.10 replaced by a single "Phase 4.6: Flag Write-Back" delegating to `ll-issues set-flags` (491 → 404 lines); `skills/format-issue/SKILL.md`'s file-selection loop, testable keyword counter, and narrated check-mode replaced with CLI delegation |

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

### Documentation drift — already corrected; the remaining work is inverted

**Superseded 2026-08-01.** The drift described below **has been fixed**; the
instruction that followed it is now backwards and has been rewritten.

_Historical_: `.claude/CLAUDE.md`'s `ll-issues` entry documented **`set-flags`
and `format-check --next` as shipped**, with full flag lists
(`--from-notes <file|->`, `--dry-run`, `--depth-moderate-or-deep`, `--json`,
`--next resolves the highest-priority active issue with no type filter`).
Neither existed. That text was added by commit **`46969c7c`**, whose subject
and body are entirely about ENH-2949 (`ll-loop audit --json`) — documentation
running ahead of code, in a commit for a different issue. _(Same failure mode
as ENH-2944, reopened for the stripped `normalize` wiring in `3e76f972`.)_

_Current state_: `.claude/CLAUDE.md:252` now carries an explicit disclaimer —
*"Not yet shipped, despite prior entries here claiming otherwise: `normalize`
(ENH-2944 …) and `set-flags` (ENH-2946 — never implemented), plus
`format-check --next` (ENH-2946). Do not call these; check `ll-issues --help`
before adding a subcommand to this list."*

**Consequence for this issue**: landing steps 1 and 2a requires **removing**
this issue's clauses from that disclaimer, not adding a correction. The line
is **shared with ENH-2944**, which owns the `normalize` clause. Delete only
the `set-flags` / `format-check --next` clauses; remove the whole line only if
ENH-2944 has already landed and deleted its own. Then add the real flag
surface to the `ll-issues` bullet at line 251.

## Current Behavior

_Line numbers re-verified 2026-08-01 against the current 491-line file; the
ranges below had drifted by ~3 lines. Re-grep before editing._

- confidence-check Phase 4.6 (L365–391): scan risk-factor text for an 11-phrase list ("open decision", "either/or", "Option A/B", …) → `decision_needed: true`. Phase 4.7 (L389–413): 6 phrases → `missing_artifacts: true`. Phase 4.9 (L415–435): 6 phrases → `implementation_order_risk: true`. Phase 4.10 (L437–463): 8 phrases + `score_test_coverage <= 10` → `spike_needed: true`. The in-file precedent already exists: L132–149 delegates the Program Design gate to `ll-issues format-check` with the note "Do **not** re-judge specificity yourself; the CLI is the single source of truth."
- format-issue: highest-priority-file selection via nested shell loops (L96–139), the `testable` doc-only keyword counter ("2+ distinct keyword matches", L170–181), check-mode counting with narrated exit codes (L388–400).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-08-01):_

- Phase line ranges have drifted further since this section's own "re-verify before editing" note was written. Current content: Phase 4.5 Findings Write-Back `SKILL.md:331–363`, Phase 4.6 Decision-Needed `SKILL.md:365–390`, Phase 4.7 Missing-Artifacts `SKILL.md:392–416`, Phase 4.9 Implementation-Order-Risk `SKILL.md:418–438`, Phase 4.10 Spike-Needed `SKILL.md:440–466`. Re-grep before editing.
- The "composes with existing `check-flag` gates" claim in Proposed Solution is confirmed and locatable: `ll-issues check-flag` (alias `cf`) is a real, already-shipped read-only subcommand at `scripts/little_loops/cli/issues/check_flag.py:13-33` (`cmd_check_flag`), registered at `cli/issues/__init__.py:658-666`. It resolves the issue, parses frontmatter with `coerce_types=True`, and exits 0 iff `str(fm.get(args.field)).lower() == "true"`. It is already consumed by `autodev.yaml`, `rn-remediate.yaml`, `recursive-refine.yaml`, `refine-to-ready-issue.yaml`, and `spike-gate.yaml` to gate on the same four flags `set-flags` would write — the new writer and the existing reader target identical frontmatter keys.
- Phase 4.10's own text at `SKILL.md:464` already anticipates this port: it notes it is writing via the Edit tool "**not** a `set-flag` CLI verb, which does not exist" — the skill author already flagged this exact seam as a future extraction point.

## Expected Behavior

- `ll-issues set-flags <id> --from-notes <file|-> [--dry-run] --json` — runs the phrase-list + numeric-gate rules over the skill's written findings and stamps `decision_needed` / `missing_artifacts` / `implementation_order_risk` / `spike_needed` frontmatter. Phrase lists live in Python (single source of truth).
- `ll-issues format-check` extended with: target selection (`--next` highest-priority open issue, matching format-issue's current selection rules) and the `testable` inference as a gap/annotation; its existing `--format json` + exit codes replace format-issue's narrated check-mode (EPIC convention). **`format-check` already has a positional `issue_id` and an `--all` sweep flag** — `--next` is a third, mutually exclusive target selector (argparse mutual-exclusion group with `issue_id`/`--all`), and needs a defined exit code and message for the empty-backlog case where `find_highest_priority_issue()` returns `None`.
- confidence-check keeps Phases 2/2b (readiness/outcome criteria against actual code) and writes its findings; format-issue keeps §3.5 content-quality analysis and §4.0 confidence filtering.

## Proposed Solution

Reuse `frontmatter.update_frontmatter`, `issue_parser.check_format_gaps`, `find_highest_priority_issue`, and the existing `format-check` subcommand plumbing. `set-flags` composes with existing `check-flag` gates (which FSM loops already consume).

## Implementation Steps

_Status per step is tracked in "Implementation Status" above._

1. `set-flags --from-notes` with rules-as-data + tests per flag. **Done.**
2. `format-check --next` + `testable` inference + tests. **Done.**
   - 2a. `--next` target selection via `find_highest_priority_issue`
     (`issue_parser.py:2011`). **Done.**
   - 2b. `testable` inference. **Landed** (`dd057ef0`), text-mode rendering
     defect fixed 2026-08-01, and `check_format_gaps`'s population now has a
     direct unit test (`TestCheckFormatGapsTestablePopulation`). **Done.**
3. Slim both skills. **Done** — confidence-check's Phases 4.6/4.7/4.9/4.10
   collapsed into one delegating "Phase 4.6: Flag Write-Back" (491 → 404
   lines); format-issue's file-selection loop, testable counter, and
   check-mode narration replaced with CLI delegation.
4. **Remove this issue's clauses from `.claude/CLAUDE.md:252`'s not-yet-shipped
   disclaimer** and document the real flag surface at line 251. **Done** —
   the line carried only this issue's clauses (ENH-2944's `normalize` clause
   was already removed by that issue), so the whole disclaimer line was
   deleted and the real `format-check --next`/`set-flags` surface documented
   inline in the `ll-issues` bullet.

## Program Design

### Types

_Corrected 2026-08-01 — the earlier three-field `FlagRule` could not express
the rules it was meant to port. See Design Decisions below._

- `FlagRule: dataclass`
  - `flag: str`
  - `phrases: tuple[str, ...]`
  - `numeric_gate: Callable[[IssueInfo], bool] | None`
  - `precondition: Callable[[IssueInfo], bool] | None` — all four phases only
    have effect when Phase 4.5 produced Outcome Risk Factors, i.e.
    `outcome_confidence < commands.confidence_gate.outcome_threshold`
  - `suppressor: Callable[[str, IssueInfo], bool] | None` — Phase 4.7's
    co-deliverable check (the named file appears under
    `### Files to Create`), which blocks the write
  - `fires_on_suppression_of: str | None` — Phase 4.9 fires *because* 4.7 was
    suppressed; rules evaluate in declared order and later rules can read
    earlier rules' suppression outcomes
- `FLAG_RULES: tuple[FlagRule, ...]` — the four rules (decision_needed, missing_artifacts, implementation_order_risk, spike_needed) as data, **order-significant**
- `FlagResult: dataclass`
  - `id: str`
  - `set_flags: dict[str, bool]`
  - `matched_phrases: dict[str, list[str]]`
  - `suppressed: dict[str, str]` — flag → reason, so a suppressed 4.7 is visible in `--json` rather than indistinguishable from "no phrase matched"

### Signatures

- `apply_flags_from_notes(config: BRConfig, issue_id: str, notes: str | None, dry_run: bool) -> FlagResult` — phrase scan + `score_test_coverage <= 10` gate; writes via `frontmatter.update_frontmatter`. `notes=None` means "read the issue's own `## Confidence Check Notes` section" (see Design Decision 2). **Set-only**: never writes `false` (Design Decision 3).
- `select_next_issue(config: BRConfig) -> IssueInfo | None` — **corrected**: the real helper is `issue_parser.find_highest_priority_issue(config: BRConfig, category=None, skip_ids=None, only_ids=None, type_prefixes=None) -> IssueInfo | None` (`issue_parser.py:2011`). It takes a `BRConfig`, not a bare `issues_dir`, and returns `IssueInfo | None`, not `Path`. The earlier signature here matched no existing symbol.
- `infer_testable(issue: IssueInfo) -> bool` — doc-only keyword counter (2+ distinct matches). **Already landed** (`issue_parser.py:528`).

### Design Decisions

_Resolved during pre-implementation review (2026-08-01). Each was an unstated
gap that would have lost behavior on the port._

1. **The rules-as-data model needs three more fields.** Reading the actual
   phases rather than the summary: every phase is preconditioned on Phase 4.5
   having produced Outcome Risk Factors; Phase 4.7 has a *suppressor* (the
   co-deliverable check against `### Files to Create`, `SKILL.md:408`); and
   Phase 4.9 explicitly *"also fires when Phase 4.7's co-deliverable
   suppression blocked a `missing_artifacts` write"* (`SKILL.md:422`) — a
   rule-to-rule dependency. A flat `(flag, phrases, numeric_gate)` triple
   drops all three, and autodev routes on these flags.
2. **`--from-notes` defaults to the issue's own notes section.** Phase 4.5
   appends a `## Confidence Check Notes` section to the issue file
   (`SKILL.md:331-346`) — that is where the risk-factor text the phrase scan
   reads actually lives. Defaulting `--from-notes` to reading that section
   (via the existing `ll-issues sections` plumbing) makes `set-flags`
   independently runnable and FSM-callable instead of meaningful only inside a
   live confidence-check run; `<file|->` stays as an override for piping
   findings that have not been written back yet.
3. **`set-flags` is set-only; it never clears.** `confidence-check/SKILL.md:452`
   is explicit: *"leave `spike_needed` unchanged (never write `false` —
   absence is the negative)"*, and `decide-issue` is the only component
   licensed to clear a flag (`decide-issue/SKILL.md:210`: *"automation cannot
   clear a flag it did not earn"*). A `set-flags` that wrote `false` on a
   no-match re-run would clear flags a spike or decision had earned and break
   autodev routing. Absence remains the negative; add a test per flag.

### Call Path

- `apply_flags_from_notes()` -> `update_frontmatter()` (existing, `frontmatter.py`)
- `select_next_issue()` -> `find_highest_priority_issue()` (existing, `issue_parser.py`)
- `infer_testable()` extends `check_format_gaps()` (existing, `issue_parser.py`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-08-01):_

- **`update_frontmatter()` is not set-only.** Its actual behavior (`frontmatter.py:439-471`) is a plain `existing.update(updates)` dict merge — every key present in `updates` unconditionally overwrites the existing value, with no concept of "only write True" or "never write False." Design Decision 3's set-only guarantee is therefore something `apply_flags_from_notes()` must implement itself (e.g. by filtering `updates` down to only the flags that evaluated `True` before calling `update_frontmatter`), not a behavior inherited from the existing helper.
- **No code precedent for set-only writes exists yet** — the rule is currently prose-only (`confidence-check/SKILL.md:452`, `decide-issue/SKILL.md:210`, and `FEAT-2567`'s `spike_attempted`/`spike_completed` clause). The closest related-but-distinct precedent is `cmd_set_scores` (`scripts/little_loops/cli/issues/set_scores.py:13-56`), which builds `updates` from only the CLI flags the caller explicitly passed — omission-preserves-existing, not suppression-of-False. `apply_flags_from_notes` needs the additional False-suppression step on top of that pattern.
- **Subcommand registration convention**: every subcommand added in recent ENH/FEAT cycles (`normalize`, `format-check`, `link`, `size`, `decisions`) exports `add_<name>_parser(subs) -> argparse.ArgumentParser` from its own module under `scripts/little_loops/cli/issues/<name>.py`, imported once into `main_issues()` (`cli/issues/__init__.py`) alongside a matching `cmd_<name>`, with `p.set_defaults(command="<name>")` and a trailing `add_config_arg(p)`. `set-flags` fits this shape rather than the older inline-in-`main_issues()` shape some pre-existing subcommands (e.g. `set-scores`) still use.
- **Correction to Expected Behavior's stated mutex mechanism**: no subcommand in this CLI enforces positional-vs-flag exclusivity via `argparse.add_mutually_exclusive_group()` — that mechanism is used here only for flag-vs-flag groups (e.g. `add_corpus_target_args`'s `--project`/`--all`, `link.py`'s relation-type group). Every existing case where a bare positional competes with flags for target selection (`cmd_size`, `size.py:178-188`; `format-check`'s own current `issue_id`-vs-`--all` check, `format_check.py:176-178`) uses a manual runtime check instead — e.g. `cmd_size`'s `sum(bool(x) for x in (issue_id, all_mode, sprint_name)) != 1`. `format-check --next` should extend the existing manual check in `cmd_format_check` (`format_check.py:176-178`) to a three-way check rather than introduce an `add_mutually_exclusive_group` call, which would be the first of its kind for a positional argument in this CLI.
- **`check_format_gaps`'s `testable` population is a second, independent implementation, not a call to `infer_testable()`.** `check_format_gaps` (`issue_parser.py:308-500`) re-derives its own `scan_text` inline at `issue_parser.py:489-498` and calls `_count_testable_keyword_matches` directly, sharing only the keyword tuple and threshold constant with `infer_testable()` (`issue_parser.py:528-540`) — the two call sites do not share a call path. This confirms the open Acceptance Criterion ("`check_format_gaps`'s `testable` population has a direct unit test … not only CLI-level coverage") targets a genuinely separate code path from `TestInferTestable` (`test_issue_parser.py:3950-3989`).

## Integration Map

_Wiring pass added by `/ll:wire-issue` (2026-08-01):_

### Dependent Files (Callers/Importers)

- `.gemini/skills/confidence-check/SKILL.md`, `.kimi-code/skills/confidence-check/SKILL.md`, `.gemini/skills/format-issue/SKILL.md`, `.kimi-code/skills/format-issue/SKILL.md` — host-adapter mirrors generated by `ll-adapt`; will drift from the edited `skills/*/SKILL.md` sources once Step 3 (slimming) lands, until regenerated (`ll-adapt --host <gemini|kimi-code> --apply`) [Agent finding]
- `scripts/little_loops/loops/spike-gate.yaml:29` — stale comment: `# spike_needed is written by /ll:confidence-check Phase 4.10 when...`; the `action:` itself only reads the flag via `check-flag` so it's functionally unaffected, but the comment names the phase being removed [Agent finding]
- `scripts/little_loops/loops/autodev.yaml` — inline comments citing "Phase 4.10"/"Phase 4.7" by name near `check_spike_needed`/`check_missing_artifacts` (~L1154, L1229) describing flag provenance; the dozen+ `check-flag` call sites elsewhere in this file (L216-223, 475-478, 504-513, 601-622, 678-684, 737, 1123-1149, 1152-1179, 1359-1413, 1930) are the blast radius if `set-flags`' idempotency/string semantics diverge from confidence-check's current phrase-scan (must keep reading `decision_needed`/`missing_artifacts`/`spike_needed` with the same `"true"`/`"false"` string semantics) — no file change required there, but confirm at implementation time [Agent finding]

### Documentation

- `docs/reference/CLI.md` — `ll-issues format-check` section needs a `--next` flag row + example; `ll-issues check-flag` section could cross-reference `set-flags` as its write-side counterpart (currently one-directional) [Agent finding]
- `docs/reference/API.md` — `IssueInfo` dataclass field comments for `missing_artifacts`/`implementation_order_risk` cite "(Phase 4.7)"/"(Phase 4.9)" by name; goes stale once those phases are removed [Agent finding]
- `docs/reference/COMMANDS.md:335,337,339` — three `/ll:confidence-check` paragraphs (decision_needed / missing_artifacts / implementation_order_risk write-back) describe the phrase-scan phases by number; rewrite to describe `set-flags --from-notes`/`FLAG_RULES` instead [Agent finding]
- `docs/guides/LOOPS_REFERENCE.md:165,1051` — spike-gate loop-catalog row ("`spike_needed` (set by `/ll:confidence-check` Phase 4.10)") and autodev.yaml prose citing "Phase 4.10"/"Phase 4.7" by name [Agent finding]
- `docs/reference/ISSUE_TEMPLATE.md:904-906` — frontmatter field reference table rows for `missing_artifacts`/`implementation_order_risk`/`spike_needed` cite "(Phase 4.7)"/"(Phase 4.9)"/"(Phase 4.10)" [Agent finding]
- `commands/refine-issue.md:377` — direct dangling section reference to format-issue's **"2.5a. Testable Inference (doc-only detection)"** section, which Step 3 removes; must be repointed once that section is slimmed [Agent finding]

### Tests

- `scripts/tests/test_confidence_check_skill.py` — contains direct content-assertion tests on the exact phase headings Step 3 removes: `"### Phase 4.6: Decision-Needed Flag"` (L88-131), `"### Phase 4.7: Missing-Artifacts Flag"` (L136-181), `"### Phase 4.9: Implementation-Order Risk Flag"` (L186-225, plus a hardcoded-threshold regression check L254-261), `"### Phase 4.10: Spike-Needed Flag"` (L339-397). **These tests will fail outright once the phases are removed from `SKILL.md`** — they test prose, not behavior; rewrite them to test `apply_flags_from_notes`/`FLAG_RULES` directly instead of `content.index()`-scanning `SKILL.md` [Agent finding — breaking, not just missing]
- New test module for `set_flags.py`, modeled on `scripts/tests/test_set_scores_cli.py`'s `TestIssuesCLISetScores` pattern (in-process `patch.object(sys, "argv", ...)` + `main_issues()`, asserting raw frontmatter text — see `test_set_scores_writes_all_fields`, `test_set_scores_partial_update`, `test_set_scores_no_flags_returns_0_with_warning`). No existing test file references `set_flags`/`set-flags` yet [Agent finding]
- New CLI-level test for `ll-issues format-check --next` in `scripts/tests/test_ll_issues_format_check.py`, following its existing `_invoke()`/`format_check_dir` fixture pattern (L52-75); `TestFindHighestPriorityIssue` in `test_issue_parser.py` (~L1537-1583) already covers the wrapped helper directly and is unaffected [Agent finding]
- `scripts/tests/test_ll_issues_check_decidable.py` — nearest existing subprocess-level (not in-process) CLI-contract test pattern (`_cli()`/`_invoke()` via `subprocess.run`, `TestCliRegistration.test_subcommand_in_help`); use this shape instead of the in-process pattern above if a genuine subprocess integration test is wanted for `set-flags` [Agent finding, reference pattern]
- `scripts/tests/test_wiring_skills_and_commands.py` — blind string-presence wiring guard over both target `SKILL.md` files (pinned strings at L23,56,136-137,197,237,255-256). None of the pinned strings live inside the sections Step 3 removes (2.5a, Phase 4.6/4.7/4.9/4.10), so it should survive unmodified — but re-check it after slimming since it can't distinguish semantic changes from accidental deletions [Agent finding, advisory]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation, in addition to the four Implementation Steps above:_

5. **Done.** `scripts/tests/test_confidence_check_skill.py` — replaced the Phase 4.6/4.7/4.9/4.10 prose-content assertions with `TestFlagWriteBackDelegatesToSetFlags`/`TestFlagRulesMatchProseSpec` against `apply_flags_from_notes`/`FLAG_RULES`.
6. **Done.** Regenerated host-adapter mirrors (`.gemini/`, `.kimi-code/`) for `confidence-check` and `format-issue` via `ll-adapt --host gemini --apply` / `--host kimi-code --apply`.
7. **Done.** Updated the phase-number citations in `docs/reference/API.md`, `docs/reference/COMMANDS.md`, `docs/guides/LOOPS_REFERENCE.md`, and `docs/reference/ISSUE_TEMPLATE.md` to describe `set-flags`/`FLAG_RULES` instead of named phase numbers. Also updated `scripts/little_loops/loops/spike-gate.yaml`/`autodev.yaml` comments (Integration Map finding, not originally a numbered Wiring step).
8. **No action needed.** `commands/refine-issue.md:377` references format-issue's "2.5a. Testable Inference (doc-only detection)" **heading**, which was preserved (only its body content changed) — the reference is still valid.
9. **Done.** Added `--next` flag documentation to `docs/reference/CLI.md`'s `ll-issues format-check` section, plus a new `ll-issues set-flags` section and a cross-reference from `check-flag`.

## Scope Boundaries

- In scope: `set-flags --from-notes`, `format-check --next` + `testable` inference; slimming confidence-check Phases 4.6–4.10 and format-issue's mechanical sections.
- Also in scope (identified 2026-08-01, previously unaccounted): slimming these two skills clears three `ll-verify-skill-prose` findings — `skills/confidence-check/SKILL.md:138,140` and `skills/format-issue/SKILL.md:345`, all `[inline_python_computation]`. `BASELINE_COUNT` in `scripts/tests/test_verify_skill_prose.py:19` must be lowered by this issue's delta. **The constant is shared with ENH-2944 and ENH-2953, which lower it for their own targets — re-run `ll-verify-skill-prose` and count at land time rather than assuming a delta.** The tree reports 15 findings today (constant is 23, and the assert is a `<=` ceiling, so it cannot fail on a decrease — lowering it is hygiene, not a gate).
- Out of scope: confidence-check Phases 2/2b (code-reading judgment), format-issue §3.5/§4.0 content-quality analysis, changing flag semantics consumed by autodev.

## Impact

- **Priority**: P2 - Makes the flags autodev routes on (spike_needed, decision_needed, …) deterministic instead of model-recall-dependent
- **Effort**: Small-Medium - Rules-as-data + one selection helper
- **Risk**: Low - `--dry-run` supported; per-flag fixtures

## Resolution

- **Action**: improve
- **Completed**: 2026-08-01
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli/issues/set_flags.py`: new module — `FlagRule`/`FlagResult` dataclasses, `FLAG_RULES` data (decision_needed/missing_artifacts/implementation_order_risk/spike_needed), `apply_flags_from_notes()`, `cmd_set_flags`/`add_set_flags_parser`
- `scripts/little_loops/cli/issues/__init__.py`: registered `ll-issues set-flags`
- `scripts/little_loops/cli/issues/format_check.py`: added `--next` target selection via `find_highest_priority_issue`, three-way mutex with `issue_id`/`--all`
- `skills/confidence-check/SKILL.md`: Phases 4.6/4.7/4.9/4.10 collapsed into one delegating "Phase 4.6: Flag Write-Back" (491 → 404 lines)
- `skills/format-issue/SKILL.md`: file-selection loop, testable keyword counter, and check-mode narration replaced with CLI delegation
- `.gemini/skills/{confidence-check,format-issue}/SKILL.md`, `.kimi-code/skills/{confidence-check,format-issue}/SKILL.md`: regenerated via `ll-adapt --apply`
- `.claude/CLAUDE.md`: removed this issue's clauses from the not-yet-shipped disclaimer; documented `set-flags`/`format-check --next` in the `ll-issues` bullet
- `docs/reference/CLI.md`: `--next` flag row + new `ll-issues set-flags` section + `check-flag` cross-reference
- `docs/reference/API.md`, `docs/reference/COMMANDS.md`, `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/ISSUE_TEMPLATE.md`: repointed phase-number citations to `set-flags`/`FLAG_RULES`
- `scripts/little_loops/loops/spike-gate.yaml`, `scripts/little_loops/loops/autodev.yaml`: updated stale Phase 4.10 comments
- `scripts/tests/test_set_flags_cli.py`: new — `apply_flags_from_notes`/`FLAG_RULES` unit tests + CLI tests
- `scripts/tests/test_ll_issues_format_check.py`: `TestFormatCheckNext` — `--next` selection, mutex, empty-backlog exit
- `scripts/tests/test_issue_parser.py`: `TestCheckFormatGapsTestablePopulation` — direct unit test for `check_format_gaps`'s `testable` population
- `scripts/tests/test_confidence_check_skill.py`: replaced Phase 4.6/4.7/4.9/4.10 prose-content assertions with tests against `apply_flags_from_notes`/`FLAG_RULES`

### Deviations from Program Design
- **External-API suppression and the Depth-based OR score condition (Phase 4.10) were not ported to `FLAG_RULES`.** Depth is never persisted to frontmatter (only the combined `score_complexity` total is), so a stateless CLI call has nothing to read for it; `spike_needed`'s numeric gate is `score_test_coverage <= 10` only. External-API suppression requires judging whether a named entity is a third-party package vs. project-internal code — genuine code-reading judgment the issue's Summary says stays in the skill, not phrase matching. `set_flags.py`'s module docstring and `skills/confidence-check/SKILL.md`'s Phase 4.6 both document this explicitly.
- **`BASELINE_COUNT` in `test_verify_skill_prose.py` is unchanged (19).** The two findings this issue's Scope Boundaries predicted would clear from slimming turned out to live in unrelated sections (Phase 1.6's Program Design gate JSON extraction; format-issue's mandatory session-log-append block), not the prose this issue actually removed. Re-counted at land time per the issue's own instruction; delta is 0.

### Verification Results
- Tests: PASS (17687 passed, 42 skipped)
- Lint: PASS (`ruff check scripts/`)
- Types: PASS (`mypy` on changed modules)
- Docs: PASS (`ll-verify-docs`, `ll-verify-cli-allowlist`, `ll-verify-skill-prose`)
- Integration: PASS

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [x] All four flag rules produce identical results to the prose spec (fixture notes per phrase list), **including the non-phrase parts**: each rule's Phase-4.5 precondition, Phase 4.7's co-deliverable suppression against `### Files to Create`, and Phase 4.9 firing *because* 4.7 was suppressed
- [x] **`set-flags` never writes `false`** — a re-run whose notes no longer match leaves an existing `true` flag intact (one test per flag); clearing stays owned by `/ll:decide-issue`
- [x] `set-flags` with no `--from-notes` reads the issue's own `## Confidence Check Notes` section and produces the same result as piping that section on stdin
- [x] `--json` distinguishes "no phrase matched" from "matched but suppressed" (`suppressed` map populated)
- [x] `format-check --next` is mutually exclusive with the positional `issue_id` and `--all`, and has a defined exit code + message when the backlog is empty (`find_highest_priority_issue()` returns `None`)
- [x] confidence-check contains no phrase lists; it pipes findings to `set-flags`
- [x] format-issue's file selection/check-mode are CLI calls with deterministic exit codes
- [x] pytest coverage in `scripts/tests/`
- [x] `BASELINE_COUNT` in `test_verify_skill_prose.py:19` re-counted at land time: still 19 (no decrease). The two `[inline_python_computation]` findings this issue's Scope Boundaries predicted would clear (`skills/confidence-check/SKILL.md:138,140`, `skills/format-issue/SKILL.md:345`) turned out to sit in unrelated sections (Phase 1.6's Program Design gate JSON extraction; format-issue's mandatory session-log-append `python3 -c` block) — not the Phase 4.6-4.10/file-selection/testable/check-mode prose this issue actually slimmed. Delta is 0; `BASELINE_COUNT` is unchanged since it is a `<=` ceiling and nothing regressed.
- [x] `testable` inference exists and is reachable from `check_format_gaps`
      (`issue_parser.py:489-498`, `L528`)
- [x] Every `FormatGaps` class reaches **text** output, not just
      `--format json` — a class counted by `has_gaps` with no `_print_gaps`
      loop exits 1 with an empty report. Enforced by
      `test_ll_issues_format_check.py::TestFormatCheckTestableRendering::test_every_format_gaps_field_is_rendered`,
      which enumerates `dataclasses.fields(FormatGaps)`. _Added after the
      `testable` regression; applies to any class this issue adds._
- [x] `check_format_gaps`'s `testable` population has a direct unit test in
      `test_issue_parser.py`, not only CLI-level coverage
- [x] `.claude/CLAUDE.md`'s `ll-issues` entry names only shipped subcommands
      and flags — verified by invoking each documented one — **and this
      issue's clauses are removed from the line-252 not-yet-shipped
      disclaimer without disturbing ENH-2944's `normalize` clause**


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-01_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- Breadth: the change touches roughly 20 sites across core code, tests, docs, and host-adapter mirrors (`.gemini/`, `.kimi-code/`). The Integration Map is thorough, but a sweep this wide raises the chance a site slips through during implementation — particularly the four host-mirror regenerations and the two loop-YAML comment citations, which sit outside the core diff behind a separate `ll-adapt --apply` step.
- Test coverage: `set_flags.py` is a wholly new module with no existing test file to extend. `test_confidence_check_skill.py`'s prose-assertion tests will break the moment Step 3 removes the phases they assert on, so the rewrite (Wiring Step 5) needs to land in the same change as the removal or the suite goes red mid-implementation.
- The `FlagRule` design encodes an order-significant, cross-rule dependency (Phase 4.9's rule fires because Phase 4.7's rule was suppressed) — a shape not seen elsewhere in this codebase's rules-as-data modules. It is fully specified (types, signatures, and the resolved Design Decisions already document the shape), so this is a well-scoped implementation task rather than a proof-of-mechanism gap, but the cross-rule ordering logic is worth the one test-per-flag the Acceptance Criteria already call for.

## Session Log
- `/ll:manage-issue` - 2026-08-02T00:26:04 - `f987e26d-d7db-45bc-8a17-37251e0f4d3b.jsonl`
- `/ll:confidence-check` - 2026-08-01T23:52:01 - `5af741d8-f183-4568-b980-822497c8e0d4.jsonl`
- `/ll:wire-issue` - 2026-08-01T23:47:50 - `50932fef-3cb8-48c3-817d-c52854d093c6.jsonl`
- `/ll:refine-issue` - 2026-08-01T23:39:37 - `36118e03-b486-4fd8-bdce-33c07200425f.jsonl`
