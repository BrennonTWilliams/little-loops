---
id: ENH-2966
title: "`testable` keyword inference fires on 62% of active issues"
type: ENH
priority: P3
status: open
captured_at: '2026-08-01T16:02:14Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2946
testable: true
decision_needed: true
labels:
- issues
- cli
---

# ENH-2966: `testable` keyword inference fires on 62% of active issues

## Summary

`check_format_gaps`'s `testable` advisory flags an issue as
documentation-only when 2+ distinct signal keywords appear anywhere in its
title or body. In this repo — whose subject matter *is* documentation, skills,
and doc tooling — that fires on 36 of 58 active issues. An advisory that
fires on the majority of the corpus carries no information.

## Current Behavior

`issue_parser.py`:

- `_TESTABLE_SIGNAL_KEYWORDS` (`L506-518`): `doc`, `docs`, `documentation`,
  `broken link`, `broken anchor`, `readme`, `changelog`, `spelling`, `typo`,
  `guide`, `fix link`.
- `_TESTABLE_KEYWORD_THRESHOLD = 2` (`L519`) — 2+ *distinct* matches.
- `check_format_gaps` (`L489-498`) scans `title + strip_frontmatter(content)`
  — the **entire issue body** — and appends a `testable` gap when no explicit
  `testable:` key is present.

Measured on the current backlog: **36 of 58 active issues** trip it; 19 had it
as their *only* gap.

The rule is behaving exactly as specified. The specification is the problem:

- The scan covers the whole body, so any issue that *discusses* documentation
  in its Integration Map, Scope Boundaries, or Documentation section matches —
  regardless of whether the work itself is doc-only.
- `doc` and `docs` are separate keywords, so a single sentence mentioning
  "the docs" alongside one "documentation" reaches the threshold on its own.
- Bare `doc`/`guide` are extremely common in a repo with `docs/guides/`,
  `LOOPS_GUIDE.md`, `HARNESS_OPTIMIZATION_GUIDE.md`, and a `## Related Key
  Documentation` section in the standard issue template.

Concrete false positive: ENH-2946 (a pure CLI-implementation issue) began
tripping the advisory only after prose about *documentation drift* was added
to its body. The issue's testability did not change.

## Expected Behavior

The advisory fires rarely enough that it is worth reading — it should identify
issues that are genuinely documentation-only, not issues that mention
documentation.

## Motivation

A gap class that fires on 62% of the corpus is indistinguishable from noise,
and the cost is not neutral:

- It trains readers to ignore `format-check` output, which also carries the
  ten real structural gap classes.
- The remedy the message suggests (`set an explicit testable:` key) makes the
  advisory disappear without anyone verifying the issue is actually testable —
  so the rule pushes toward reflexive frontmatter stamping rather than
  judgment.
- Every false positive is a non-zero exit from `format-check`, which is a
  gate other tooling consumes.

## Proposed Solution

Options, roughly in increasing order of effort:

**A. Narrow the scan surface.** Match against the title and `## Summary` only,
not the whole body. Most genuine doc-only issues announce themselves in the
title ("fix broken link in X", "update CHANGELOG"). This alone likely removes
most false positives, since the matches are usually in Integration
Map/Documentation sections.

**B. Tighten the keyword list.** Drop bare `doc`/`guide` (too common as
substrings of ordinary prose), keep the high-signal multiword phrases
(`broken link`, `broken anchor`, `fix link`, `typo`, `spelling`, `changelog`,
`readme`). Consider requiring at least one *action-shaped* phrase rather than
any two nouns.

**C. Raise the threshold** from 2 to 3+ distinct matches. Cheapest change, but
it only shifts the curve rather than fixing the surface problem — a long issue
that discusses docs will still reach any fixed count.

**D. Negative signals.** Suppress when the issue names code artifacts
(`.py` paths, `def `/`class `, a `## Program Design` section with real
signatures). A doc-only issue rarely has a populated Program Design.

Recommend **A + B together**, then re-measure against the backlog. The target
is a single-digit fire count, and the measurement is cheap:
`ll-issues format-check --all --format json` and count non-empty `testable`
arrays.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. The alternatives
above are restated here in the `**Option X**` heading form the
`check-decidable` probe (`locate_enumerable_options`,
`scripts/little_loops/issue_parser.py`) scans for — the `**A.**`-prefix form
above does not match its heading regex, so it was invisible to the decision
gate despite being a genuine 4-option decision point._

**Option A**: Narrow the scan surface. Match against the title and `##
Summary` only, not the whole body. Most genuine doc-only issues announce
themselves in the title ("fix broken link in X", "update CHANGELOG"). This
alone likely removes most false positives, since the matches are usually in
Integration Map/Documentation sections.

**Option B**: Tighten the keyword list. Drop bare `doc`/`guide` (too common as
substrings of ordinary prose), keep the high-signal multiword phrases
(`broken link`, `broken anchor`, `fix link`, `typo`, `spelling`, `changelog`,
`readme`). Consider requiring at least one *action-shaped* phrase rather than
any two nouns.

**Option C**: Raise the threshold from 2 to 3+ distinct matches. Cheapest
change, but it only shifts the curve rather than fixing the surface problem —
a long issue that discusses docs will still reach any fixed count.

**Option D**: Negative signals. Suppress when the issue names code artifacts
(`.py` paths, `def `/`class `, a `## Program Design` section with real
signatures). A doc-only issue rarely has a populated Program Design.

**Recommended**: Option A + Option B together, then re-measure against the
backlog. The target is a single-digit fire count, and the measurement is
cheap: `ll-issues format-check --all --format json` and count non-empty
`testable` arrays.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `_TESTABLE_SIGNAL_KEYWORDS`
  (`L506-518`), `_TESTABLE_KEYWORD_THRESHOLD` (`L519`),
  `_count_testable_keyword_matches` (`L522`), and the scan-surface
  construction in `check_format_gaps` (`L489-498`).
- `skills/format-issue/SKILL.md` — the "Testable Inference" section this logic
  was ported from verbatim (`~L170-181`); it must be updated in lockstep or
  the skill and the CLI will disagree.
- `skills/capture-issue/SKILL.md` — Phase 4 step 6 documents the same 11
  keywords and 2+ threshold for `testable: false` inference at capture time;
  same lockstep requirement.

### Dependent Files
- `scripts/tests/test_issue_parser.py:3951-3989` — `infer_testable`'s
  true/false unit tests; both fixtures will need revisiting against a changed
  keyword list.
- `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckTestableRendering`
  — its `_DOC_ONLY_BODY` fixture is deliberately doc-only and must keep
  tripping the rule after any tightening; it is the regression anchor for the
  rendering fix and should not be weakened to accommodate a new keyword list.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction to the section-extractor lead below**: `ll-issues sections`
  (`cmd_sections` in `scripts/little_loops/cli/issues/sections.py:16-48`) is
  **not** an issue-body section extractor — it prints/resolves the path of a
  static per-type template JSON (`{type}-sections.json`) used when
  *scaffolding a new issue*. It never reads an existing issue's markdown body.
  Following this reference would cost the implementer a dead-end.
- **The actual reusable helper** is `_section_body_with_offset(content,
  heading)` / `_section_body(content, heading)`
  (`scripts/little_loops/issue_parser.py:199-223`) — locates a `^## {heading}$`
  line and returns text up to the next `^## ` line. `check_format_gaps`
  **already calls this at `issue_parser.py:435`**
  (`body = _section_body(content, name)`) for its `empty`/`boilerplate`/
  `program_design_nonspecific` gap checks, so `_section_body(content,
  "Summary")` is the same-pattern call to reuse for Option A — no new regex,
  no new module.
- Two other section-splitting implementations exist elsewhere in the codebase
  (`issue_history/doc_synthesis.py:104-127`'s `_extract_section`, and
  `issue_parser.py:662-677`'s `_iter_h2_sections` for multi-section
  enumeration) but neither is what `check_format_gaps` itself already uses —
  `_section_body` is the one already in the same call path.
- **Pre-existing scope discrepancy** (independent of this issue, but relevant
  context): both `skills/format-issue/SKILL.md:174-176` and
  `skills/capture-issue/SKILL.md:261-263` already describe the scan surface
  as "title + description text," not "title + entire body" — the Python
  implementation (`scan_text = f"{title}\n{_strip_fm(content)}"`,
  `issue_parser.py:496`) already scans more than either skill's prose
  documents. The skills and the code disagree *today*, before any fix here.
- **Test coverage gap**: neither `test_issue_parser.py:3950-3989`
  (`TestInferTestable`) nor `test_ll_issues_format_check.py`'s `_DOC_ONLY_BODY`
  fixture (lines 960-991) places any keyword hits outside the title/`##
  Summary` — every existing assertion passes unchanged whether the scan
  surface is the whole body or just title+Summary. Applying Option A alone
  would not fail any current test, but no current test would catch a
  regression in the narrowing either; a new case (keyword hits only in a
  later section like Impact/Steps to Reproduce, with title+Summary
  keyword-free) is needed to actually pin the Option A behavior change.
- For Option D (negative signals), no `_has_code_signals`-shaped helper
  exists anywhere in the codebase today. The closest prior art `check_format_gaps`
  already imports from a sibling module for a similar purpose is
  `program_design.py`'s `grade_issue_section`/`DesignVerdict` (wired in at
  `issue_parser.py:446-451` for the `program_design_nonspecific` gap) and
  `text_utils.py:14-90`'s `extract_file_paths` (path detection, not `def
  `/`class ` keyword detection) — Option D would compose from these, not
  start from scratch.

## Program Design

### Types

**No new types.** This is a tuning change to two module-level constants and
one scan-surface expression; introducing a dataclass for it would be
over-structure.

### Signatures

Existing signatures are unchanged — `infer_testable(issue: IssueInfo) -> bool`
(`issue_parser.py:528`) and `_count_testable_keyword_matches(text: str) -> int`
(`L522`) keep their shapes. What changes is what they are fed and what they
match:

- `_TESTABLE_SIGNAL_KEYWORDS: tuple[str, ...]` — drop bare `doc`, `docs`,
  `guide`; keep the multiword/action-shaped phrases. Under option B the
  distinct-match count becomes meaningful because the surviving keywords are
  not near-synonyms of each other (today `doc`/`docs`/`documentation` are three
  separate "distinct" matches for what is one signal).
- The scan-surface expression in `check_format_gaps` (`L489-498`) — currently
  `f"{title}\n{_strip_fm(content)}"`. Under option A this becomes title +
  `## Summary` body only, which needs a section extractor;
  `issue_parser`'s existing section-splitting helper (the one `ll-issues
  sections` uses) should be reused rather than a new regex.

If option D (negative signals) is adopted, add
`_has_code_signals(text: str) -> bool` alongside the existing counter and
require `count >= threshold and not _has_code_signals(...)`.

### Call Path

Unchanged: `check_format_gaps` → `_count_testable_keyword_matches` →
`gaps.testable`; and independently `infer_testable` → same counter. **Both
call sites must see the same rule** — they are separate entry points into the
same inference and are currently kept in sync only by convention.

## Implementation Steps

1. Baseline: record the current fire count
   (`ll-issues format-check --all --format json`, count non-empty `testable`).
2. Apply A (narrow scan surface to title + Summary) and re-measure.
3. Apply B (tighten keyword list) and re-measure.
4. Sanity-check the survivors by hand — every remaining hit should be an issue
   a human agrees is doc-only.
5. Update `format-issue` and `capture-issue` SKILL.md in lockstep.
6. Update the two test fixtures; confirm `_DOC_ONLY_BODY` still trips.

## Scope Boundaries

**In scope:**
- The keyword list, threshold, and scan surface for the `testable` inference.
- Keeping `infer_testable` and `check_format_gaps` consistent with the two
  SKILL.md copies of the rule.

**Out of scope:**
- The `testable` frontmatter field's *semantics* (`False` skips TDD, `None`
  treated as testable) — unchanged.
- Whether `testable` should be a `format-check` gap class at all — it should;
  this is about precision, not existence.
- Other `format-check` gap classes.
- ENH-2946's outstanding work (`set-flags`, `format-check --next`, skill
  slimming).

## Impact

- **Priority**: P3 — noise, not breakage. The advisory is correct-by-spec and
  nothing downstream misbehaves; it just wastes attention and erodes trust in
  `format-check`'s output.
- **Effort**: Small — a keyword list, a threshold, and a scan-surface change,
  with a cheap measurable target.
- **Risk**: Low — but note the rule is duplicated in two SKILL.md files, so a
  change that misses those leaves the CLI and the skills disagreeing. That
  duplication is itself the kind of prose-reimplementation
  `ll-verify-skill-prose` (ENH-2951) exists to catch.
- **Breaking Change**: No — advisory only.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:refine-issue` - 2026-08-01T19:58:05 - `f7d70fe6-d3b1-4443-814c-32eee6e8b043.jsonl`
- `/ll:capture-issue` - 2026-08-01T16:04:25 - `f9ef973a-acd3-40a7-a313-5e7a001f9a16.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3
