---
id: BUG-2985
title: _section_body returns the first matching heading, not the most recent, on issues
  with stacked repeat sections
type: BUG
priority: P3
captured_at: '2026-08-02T01:30:00Z'
completed_at: '2026-08-02T03:32:59Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
labels:
- issue-parser
- set-flags
- confidence-check
confidence_score: 96
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 20
status: done
---

# BUG-2985: _section_body returns the first matching heading, not the most recent, on issues with stacked repeat sections

## Summary

`_section_body_with_offset()` (`scripts/little_loops/issue_parser.py:199-214`)
locates a `## heading` section with a single `re.search()` call, which always
returns the **first** match in the document. Most `## heading` names are
unique per file, so this is harmless — but `## Confidence Check Notes` is
appended fresh by every `/ll:confidence-check` run without removing prior
occurrences (see `commands`/`skills/confidence-check` Phase 4.5), so an issue
that has been through multiple confidence-check passes accumulates several
stacked `## Confidence Check Notes` sections. Any reader of that heading gets
the **oldest, most stale** occurrence instead of the current one.

## Steps to Reproduce

1. Take an issue that has been through `/ll:confidence-check` multiple times,
   so its body has several stacked `## Confidence Check Notes` sections (e.g.
   `ENH-2866`, which has five).
2. Ensure the oldest such section contains phrasing that would trigger a
   `FLAG_RULES` match (e.g. "open decision"), while the most recent section
   does not.
3. Run `ll-issues set-flags <ID>` (no `--from-notes`).
4. Observe `decision_needed: true` gets (re)set from the stale, oldest
   section's phrasing, even though the current/most-recent notes contain no
   open decision.

## Current Behavior

`ll-issues set-flags <ID>` (no `--from-notes`) calls
`apply_flags_from_notes()` (`scripts/little_loops/cli/issues/set_flags.py:238`),
which does:

```python
notes = _section_body(content, "Confidence Check Notes") or ""
```

`_section_body` → `_section_body_with_offset` (`issue_parser.py:207-213`) runs
`re.search(r"^##\s+Confidence Check Notes\s*$", content, re.MULTILINE)` — the
**first** regex match — then bounds the body at the next `^##\s` line. On an
issue with several stacked `## Confidence Check Notes` sections (one per
historical confidence-check run), this returns the body of the **first**
(oldest) one, not the most recently appended one.

Reproduced live on `ENH-2866`
(`.issues/enhancements/P2-ENH-2866-record-dequeue-time-commit-sha-at-orchestrator-dequeue-and-worktree-creation.md`),
which has five stacked `## Confidence Check Notes` sections. Its oldest
section (from 2026-07-30) contains the phrase "open decision" describing a
scope question that was fully resolved in a later pass (with decision
fragments `61df2043`/`4f66ef35` recorded and `decision_needed` cleared). Every
subsequent `/ll:confidence-check` run whose own (current, no-open-decisions)
notes should leave `decision_needed` untouched instead re-triggers the
`decision_needed: true` flag by matching stale phrasing several sections
above the current one. This has now recurred at least twice on this same
issue (2026-08-01 and 2026-08-02), each requiring a manual frontmatter
correction, per its own `## Session Log`.

## Expected Behavior

`_section_body`/`_section_body_with_offset`, and any caller that expects "the
current state of this section" (`apply_flags_from_notes` being the clearest
example), should resolve the **last** occurrence of a repeatable heading, not
the first. For headings that only ever appear once (the common case), this is
a no-op change in behavior.

## Root Cause

`issue_parser.py:208`:

```python
match = re.search(pattern, content, re.MULTILINE)
```

`re.search` returns the first match. There is no `finditer`/loop to find the
last match, and no caller passes an intent flag distinguishing "first
occurrence" from "most recent occurrence" semantics. `## Confidence Check
Notes` is the one common heading in this codebase's issue template that is
designed to be appended repeatedly (Phase 4.5 of `skills/confidence-check`
always inserts a fresh section rather than replacing the existing one), which
makes it the heading most exposed to this defect.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Confirmed against current file state: the `re.search(pattern, content,
  re.MULTILINE)` call now sits at `issue_parser.py:209` (the whole function is
  `:200-215`, shifted by one line from this section's `:208` reference —
  harmless drift, same logic). The body-start/body-end bounding logic
  (`start = match.end()` then a second `re.search(r"^##\s", ...)` for the next
  `##` line) is unchanged and matches this section's description exactly.

## Proposed Solution

Change `_section_body_with_offset` to find the **last** match of the heading
pattern before computing the body span, e.g. iterate `re.finditer(...)` and
keep the final match, then apply the existing next-`##`-line bounding logic
from that match's end. This fixes every caller uniformly (`set_flags.py:273`,
plus the other `_section_body`/`_section_body_with_offset` call sites at
`issue_parser.py:435`, `:744`, `:812`, `:821`) without needing per-caller
opt-in, since "most recent occurrence" is the correct read for every existing
caller — none of them currently rely on first-match semantics for a
multi-occurrence heading (only `## Confidence Check Notes` triggers the
distinction in practice today).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The last-match idiom this fix needs already has an established, unconditional
  precedent in this codebase**: `parse_session_log()`
  (`scripts/little_loops/session_log.py:24-40`) resolves the identical
  problem — a repeatable `## Session Log` heading appended by every session —
  via `matches = list(_SESSION_LOG_SECTION_RE.finditer(content)); ...
  matches[-1]`, with no opt-in flag; the function's contract simply *is*
  last-match. `scripts/little_loops/fsm/evaluators.py:255-279` states the same
  rule explicitly in its docstring ("When multiple matches exist, the last one
  wins.") and implements it via `re.findall(...)[-1]`. Neither uses a
  `find_last=True`-style parameter — the fix here should follow that
  unconditional-last-match convention rather than adding an opt-in flag.
- **A same-file helper already walks every H2 occurrence in document order**:
  `_iter_h2_sections()` (`issue_parser.py:688-703`) returns
  `list[tuple[heading_text, start, end]]` for *all* H2 sections via
  `list(re.finditer(r"^##\s+(.+?)\s*$", content, re.MULTILINE))`. It is not
  currently called by `_section_body_with_offset`, but it already produces the
  ordered match list the fix needs (filter by heading text, take the last
  tuple) — an alternative to hand-rolling a second `finditer` walk inline.
  Note: three independent H2-heading-walking implementations exist in this
  codebase (`_section_body_with_offset`, `_iter_h2_sections`,
  `cli/doctor_trim.py:_split_h2_sections` at lines 165-189) — none share code,
  so reuse here is opportunistic, not an established requirement.
- **Existing tests for other last-match fixes follow a consistent fixture
  shape** worth mirroring for the new regression test: construct content with
  a decoy occurrence early (often inside a fenced code block) and the real
  occurrence later, assert only the later one is used. See
  `scripts/tests/test_session_log.py:318-340`
  (`test_ignores_fake_session_log_heading_in_code_block`),
  `scripts/tests/test_issues_search.py:625-642`
  (`test_updated_uses_last_session_log_entry`), and
  `scripts/tests/test_output_parsing.py:1076-1083`
  (`test_uses_last_matching_line`) — each docstring states the "last one wins"
  contract directly.

## Program Design

### Signatures

- `_section_body_with_offset(content: str, heading: str) -> tuple[str, int] | None`
  (`scripts/little_loops/issue_parser.py:199`) — change the match-selection
  from first-match (`re.search`) to last-match (iterate `re.finditer` and take
  the final result), keeping the same next-`##`-line bounding logic and return
  contract.

### Call Path

`ll-issues set-flags` → `apply_flags_from_notes()`
(`cli/issues/set_flags.py:238`) → `_section_body(content, "Confidence Check Notes")`
(`issue_parser.py:217`) → `_section_body_with_offset()` (`issue_parser.py:199`, fixed here)

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `_section_body_with_offset()`

### Dependent Files (Callers)
- `scripts/little_loops/cli/issues/set_flags.py:273` — the caller that
  surfaced this bug
- `scripts/little_loops/issue_parser.py:435`, `:744`, `:821` — other
  `_section_body`/`_section_body_with_offset` callers; verify none depend on
  first-match semantics for a repeatable heading (none currently do, since no
  other common heading is appended repeatedly)

_Wiring pass added by `/ll:wire-issue`:_
- **No files require code changes beyond `issue_parser.py`** — confirmed via
  3 parallel wiring-research agents (locator, analyzer, pattern-finder). One
  agent-surfaced lead (`cli/issues/sequence.py:find_section()`) was checked
  directly and confirmed to be an unrelated function, not a consumer of
  `_section_body`/`_section_body_with_offset` — no change needed there.
- **Downstream CLI commands whose output shifts transitively, with no code
  change required** (blast-radius awareness, not an implementation task):
  `scripts/little_loops/cli/issues/check_decidable.py` (via
  `locate_enumerable_options`), `cli/issues/locate_options.py` (via
  `locate_enumerable_options`), `cli/issues/check_open_questions.py` (via
  `count_open_questions_in_sections`), `cli/issues/format_check.py` (via the
  format-gap computation that calls `_section_body` at `:454`). Each of these
  commands will start reading the last occurrence of a stacked heading
  instead of the first once the fix lands — same fix, no separate work. This
  is a materially wider surface than the issue's Impact section states (see
  note there).
- **Docs confirmed to need no updates**: `skills/confidence-check/SKILL.md`
  (Phases 4.5/4.6), `docs/reference/CLI.md`, `docs/reference/API.md`,
  `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/ISSUE_TEMPLATE.md` — none
  assert first-match or last-match semantics explicitly, so none require
  wording changes.
- **Additional test files confirmed to need no updates** (checked directly,
  none construct a stacked/duplicate `##` heading fixture, so none will
  break and none require new assertions beyond the two tests already listed
  above): `test_issue_parser_unresolved.py`, `test_issue_parser_fuzz.py`,
  `test_issue_parser_properties.py`, `test_ll_issues_format_check.py`,
  `test_ll_issues_check_open_questions.py`,
  `test_ll_issues_check_decidable.py`, `test_ll_issues_sections.py`,
  `test_program_design_gate.py`, `test_prose_dep_sweep_gate.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The line numbers above have drifted from current file state** (this issue
  predates later commits that shifted the file). Verified current locations:
  `_section_body_with_offset` is `issue_parser.py:200-215` (not `199-214`),
  `_section_body` is `issue_parser.py:218-224`. The full current call-site
  list for `_section_body`/`_section_body_with_offset` is:
  `issue_parser.py:223` (internal, `_section_body`'s own wrapper call),
  `:454`, `:770`, `:838`, `:847`, `:946`, `:1047`,
  `cli/issues/set_flags.py:273`, `cli/issues/size.py:85`,
  `cli/issues/normalize.py:207`.
- **A second in-repo consumer scans `## Confidence Check Notes` by name and is
  exposed to the same defect, undocumented above**:
  `count_open_questions_in_sections()` (`issue_parser.py:1047`) iterates
  `_OPEN_QUESTION_SECTIONS = ("Edge Cases", "Confidence Check Notes", "Open
  Questions")` (declared `issue_parser.py:1012`) and feeds
  `count_unresolved_items_in_text()` for open-question scoring. Like
  `set_flags.py:273`, on a stacked-heading issue it currently reads the
  oldest `## Confidence Check Notes` section instead of the most recent —
  the fix in `_section_body_with_offset` corrects this call site too, with no
  separate change needed, since the fix is centralized in the shared helper.
- **Every other call site iterates a singleton-by-convention template
  heading** (`issue_parser.py:454` — required-section format-gap scan;
  `:770`/`:838`/`:847` — Proposed Solution / directive-alternatives option
  scanning; `:946` — `locate_unresolved_options`'s `Proposed Solution` +
  `_OPTION_FALLBACK_SECTIONS` scan; `cli/issues/size.py:85` —
  `_SOLUTION_HEADINGS`; `cli/issues/normalize.py:207` —
  `_CLASSIFY_SECTIONS`), so first-match vs. last-match is not an observable
  behavior difference for them today — confirms the Proposed Solution's claim
  that no caller currently relies on first-match semantics.

### Tests
- `scripts/tests/test_issue_parser.py` — add a case with two stacked
  identical `## Confidence Check Notes` (or any other) headings, asserting
  `_section_body`/`_section_body_with_offset` returns the **last** one's body
- `scripts/tests/test_set_flags_cli.py` (where `apply_flags_from_notes` is
  tested) — add a regression case modeled on `ENH-2866`: an issue with two
  stacked `## Confidence Check Notes` sections where only the first contains
  decision-flag-triggering phrasing; assert `set-flags` does NOT set the flag

### Codebase Research Findings (Tests)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The actual test file is `scripts/tests/test_set_flags_cli.py`** (no
  `test_set_flags.py` exists in this repo) — `apply_flags_from_notes()` is
  tested there. Its `_write_issue()` fixture helper (lines 14-31) appends at
  most one `## Confidence Check Notes` section per test issue
  (`body += f"\n## Confidence Check Notes\n\n{notes}\n"`, line 30, called once
  per test), so no existing test in that file constructs a stacked-heading
  issue or encodes first-match semantics — the regression test described
  above is purely additive; no existing assertion needs updating.
- **No direct unit test currently exists for `_section_body` /
  `_section_body_with_offset` themselves** anywhere in `scripts/tests/` —
  confirmed by search; only indirect coverage through callers. A grep-based
  search for tests asserting first-match behavior on any
  `_section_body`/`_section_body_with_offset` call site found none, so the
  fix is additive from a test-coverage standpoint across every location
  checked (`test_set_flags_cli.py`, `test_issue_parser_unresolved.py`,
  `test_prose_deps.py`).

## Impact

Small code change (one function) but the behavior surface is wider than
"only one heading type currently exposed" suggests: `/ll:wire-issue`
confirmed the fix also silently changes the output of `ll-issues
check-decidable`, `locate-options`, `check-open-questions`, and
`format-check` on any issue with a stacked heading in their respective
sections (`## Proposed Solution` / option-fallback headings, `## Edge
Cases`/`## Open Questions`, and required-section format-gap scanning) — see
the "Wiring pass added by `/ll:wire-issue`" note under Dependent Files above.
No extra code is needed for those commands (the fix is centralized in
`_section_body_with_offset`), but their output will change post-fix and
should be expected, not treated as a regression. The most acute case remains
`## Confidence Check Notes`: this directly undermines the "set-only, CLI is
the source of truth" contract `/ll:confidence-check` Phase 4.6 relies on — a
false positive here forces a manual frontmatter correction every time an
issue with a long confidence-check history gets re-checked, which is exactly
the kind of silent drift the CLI-as-source-of-truth design was meant to
prevent.

## Status

**Open** | Created: 2026-08-02 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-08-02T03:32:35 - `bb8a2013-cbce-486d-b2ff-e76d2ae7aaed.jsonl`
- `/ll:ready-issue` - 2026-08-02T03:26:43 - `3aed3356-0946-4110-bf48-7a02558be1cf.jsonl`
- `/ll:confidence-check` - 2026-08-02T03:24:14 - `cfdc3cc6-da35-4a51-9c7e-e77995b7ea2b.jsonl`
- `/ll:wire-issue` - 2026-08-02T03:22:24 - `acd5ae37-c1e8-48e2-9275-ef734433252a.jsonl`
- `/ll:refine-issue` - 2026-08-02T03:16:45 - `a1fd48cb-6c6a-455a-af45-870d6ae10ba9.jsonl`
- `/ll:capture-issue` - 2026-08-02T01:26:17 - `b10f0b3a-574a-4cd1-aefd-c6a613922849.jsonl`
