---
id: ENH-2821
type: ENH
priority: P3
status: done
captured_at: '2026-07-25T22:53:35Z'
completed_at: '2026-07-26T06:16:28Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels:
- issue-parser
- decision-gate
- observability
relates_to:
- BUG-2820
- ENH-2443
- ENH-2446
- ENH-2607
confidence_score: 98
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 20
---

# ENH-2821: Option-counting probes scan only three exact H2 headings — options elsewhere are silently inert

## Summary

`_section_body()` (`scripts/little_loops/issue_parser.py:115-127`) resolves a section by
`^##\s+{heading}\s*$` — H2 only, exact text — and the option probes scan just
`## Proposed Solution` plus `_OPTION_FALLBACK_SECTIONS = ("Codebase Research Findings",
"Implementation Status")` (`issue_parser.py:300`). A correctly-formatted `### Option A` /
`**Option B**` block anywhere else in the file counts as zero. `check-decidable` then reports
`OPTIONS_MISSING` — asserting the options do not exist, when in fact it never looked where they
are. This is the same silently-inert failure class the `policy_dims_scored_ok` lint exists to
catch for rubric dimensions.

## Current Behavior

Given FEAT-2817, whose options sit under `## Open Questions → ### Codebase Research Findings —
delegation architecture decision`:

```
count_enumerable_options(content)         -> 0
count_unresolved_options(content)         -> 0
```

despite the file containing a textbook `**Option A**: … **Option B**: … **Recommended**: Option A`
block. `ll-issues check-decidable` prints:

```
OPTIONS_MISSING: FEAT-2817 — decision_needed is true but ## Proposed Solution has no
                 enumerable alternatives; run /ll:refine-issue FEAT-2817 --auto
```

The message is doubly unhelpful: it names only `## Proposed Solution` (the probe actually also
checks two fallbacks), and its remedy is to re-run the very command that already deposited the
options. Nothing in the output distinguishes "no options were written" from "options were written
somewhere I don't read", so the operator has no path from the message to the cause.

Two failure modes stack:

1. **Section scope** — only three H2 headings are ever read; H3 subsections under any other H2
   are unreachable.
2. **Exact-match brittleness** — a heading decorated with a suffix (`## Codebase Research
   Findings — delegation architecture decision`) fails the match even at the right level.

## Expected Behavior

An enumerable-option block that a human would read as "here are the options" is countable
regardless of which section it was filed under, and when a probe fails it says something the
operator can act on:

- Section selection tolerates nesting (H3 under any H2) and heading-prefix matches.
- `check-decidable` failing reports whether *any* option-shaped block exists elsewhere in the
  file, and names the section it was found in.
- A whole-document fallback scan runs when the scoped scan yields zero, so "0 options" means the
  document genuinely has none.

## Motivation

BUG-2820 fixes the writer for one known path (refine-issue's decision-point deposit). This issue
fixes the reader, which closes the class: hand-authored issues, `/ll:capture-issue` output,
`scope-epic` child stubs, and any future generator can all place options in a reasonable-looking
section and hit the same wall. The probes gate `autodev`'s `check_decision_decidable`,
`rn-remediate`, and `/ll:decide-issue --validate-only` — a false `0` there defers a ready issue
with a misleading `decision_unresolved` reason, and the diagnostic actively points away from the
real cause.

Widening carries a false-positive risk (an "Option A" mentioned in passing inside `## Impact`
would newly count), which is why the conservative Pattern 1+2 matching in `_iter_option_blocks`
and the resolved-marker filter should be preserved as-is; only *where* it looks should change.

The concrete pain: an issue can be fully researched, carry a clearly-recommended option, and
still be deferred as "no actionable decision" — with a diagnostic that sends the operator back to
the tool that already did the work. Diagnosing it required reading `issue_parser.py` internals
and running the counting functions by hand against the file.

## Proposed Solution

Three changes, in increasing order of scope:

1. **Widen section resolution** — give `_section_body()` (or a variant used by the option probes)
   an option to match at any heading depth and by heading *prefix*, so
   `### Codebase Research Findings — delegation architecture decision` nested under any H2
   resolves. Keep the strict exact-H2 behavior for existing callers that depend on it.
2. **Whole-document fallback** — when the scoped scan returns 0, re-scan the full document with
   the same conservative Pattern 1+2 block matcher. Report the count *and* the section it came
   from.
3. **Actionable diagnostic** — `check-decidable`'s `OPTIONS_MISSING` message becomes:
   - options found outside the scanned sections → name the section and say to move them (or, if
     (1)+(2) land, accept them);
   - genuinely none → the current "run /ll:refine-issue" remedy, which is then correct.

Prefer landing (2)+(3) first: the fallback plus a truthful message resolves the operator-facing
problem with the least false-positive exposure, and (1) can follow once the fallback data shows
where options actually get filed in practice.

## Scope Boundaries

- **In scope**: `_section_body` section selection, `count_enumerable_options`,
  `count_unresolved_options`, `count_open_questions_in_sections`, `check-decidable` /
  `check-open-questions` messaging.
- **Out of scope**: the Pattern 1+2 heading regexes and the resolved-marker vocabulary — these
  are deliberately conservative and shared with `skills/decide-issue/SKILL.md`; changing them is
  a separate decision.
- **Out of scope**: writer-side placement (that is BUG-2820).

## Backwards Compatibility

`_section_body` is used well beyond the option probes (format-check, epic consistency). Add the
widened behavior as a new parameter or a separate helper rather than changing the default, so
existing exact-H2 callers are untouched. A widened count can newly flip `check-decidable` from
1 to 0 for existing issues — that is the intended correction, but it means `deferred` issues with
`decision_unresolved` should be re-triaged after this lands.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `_section_body` (115-127), `_OPTION_FALLBACK_SECTIONS`
  (300), `count_enumerable_options` (313-325), `count_unresolved_options` (370)
- `scripts/little_loops/cli/issues/check_decidable.py` — diagnostic message
- `scripts/little_loops/cli/issues/check_open_questions.py` — same treatment

### Tests
- Options under `## Open Questions → ### …` are counted (FEAT-2817 as the fixture).
- Heading-prefix match: `## Codebase Research Findings — <suffix>` resolves.
- Regression: existing exact-H2 callers (format-check, epic consistency) unchanged.
- `check-decidable` message names the containing section when options are found out-of-scope.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — `check_decision_decidable` state (~line 318-335) shells `ll-issues check-open-questions || ll-issues check-decidable`; a widened scan flips routing (`on_yes`/`on_no`) for previously-`no` issues [Agent 1/2 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` — parallel `check_decision_decidable` state (~line 277-298) with the same probe chain, plus an in-process Python snippet (~line 339-357) calling `count_open_questions_in_sections()`/`count_unresolved_options()` directly — check whether it needs a corresponding call-site update if widening is added behind a new non-default parameter [Agent 1/2 finding]
- `skills/decide-issue/SKILL.md` — Phase 3 "Extract Options" prose describes the current three-section scan as the human-facing mirror of `check-decidable`'s Python re-implementation; will describe a narrower algorithm than the code after this lands [Agent 1/2 finding]
- `commands/refine-issue.md` (lines 299-327, "Option-Count Detection") — references `count_enumerable_options()`/`count_unresolved_options()` scanning scope and the `ll-issues check-decidable` verification step [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `little_loops.issue_parser` section documents `count_enumerable_options`/`count_unresolved_options`/`count_open_questions_in_sections` scope as "Deterministic re-implementation of SKILL.md Phase 3" [Agent 2 finding]
- `docs/reference/CLI.md` — `check-decidable`/`check-open-questions` sections contain worked examples with literal exit-code/message expectations (e.g. `FEAT-398 # Exit 1 OPTIONS_MISSING`) that may flip once the scan widens [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — Phase 1.5 "Decidability Gate (ENH-2443, ENH-2446)" prose describing the `check_decision_decidable` probe chain [Agent 2 finding]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — "Escalation after low readiness scores" section describes the current "no enumerable options" behavior and `/ll:refine-issue --auto` remedy this issue's diagnostic revises [Agent 2 finding]
- `docs/guides/DECISIONS_LOG_GUIDE.md`, `docs/reference/COMMANDS.md` — mention `--validate-only`/`OPTIONS_MISSING` exit-1/message contract [Agent 2 finding]

### Tests (additional, beyond the four already listed above)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_check_open_questions.py` — dedicated subprocess test file for `check-open-questions` (mirrors `test_ll_issues_check_decidable.py`'s structure); check for the same exact-section-scope assumptions and `OPEN_QUESTIONS_REMAIN` message text [Agent 3 finding]
- `scripts/tests/test_issue_parser_unresolved.py` — has no direct unit tests for `_section_body` or `count_enumerable_options` today (only indirect subprocess coverage); add a `TestCountEnumerableOptions` class following its existing `TestCountUnresolvedOptions`/`TestCountOpenQuestionsInSections` fixture-string-in/value-out convention [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py::TestPolicyDimensionsScored` (lines 4344-4496) — the analogous test-shape to model the new diagnostic on: per-behavior methods, a private fixture-builder helper, an explicit suppression-flag test, and a "wired into the top-level validator" integration test [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::test_check_decision_decidable_state_exists_and_routes` / `test_check_decision_decidable_chains_coverage_probe` and `scripts/tests/test_rn_remediate.py::TestCheckDecisionDecidable*` — assert the literal shell invocation string/ordering in autodev.yaml/rn-remediate.yaml; stable unless a new CLI flag is added, but re-run to confirm [Agent 1/3 finding]
- `scripts/tests/fixtures/issues/FEAT-398-decide-empty-proposed.md` — literal true-negative fixture referenced by the `docs/reference/CLI.md` "Exit 1 OPTIONS_MISSING" example; verify it stays a true negative (no options anywhere in the doc) after widening [Agent 2/3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Backwards Compatibility correction**: `_section_body()`'s only callers are internal to
  `scripts/little_loops/issue_parser.py` itself — `check_format_gaps()` (line 262),
  `count_enumerable_options` (319, 322), `count_unresolved_options` (382), and
  `count_open_questions_in_sections` (451). There is **no** external caller in
  `epic_consistency.py` — a repo-wide grep shows that file's `_section_body`-looking hit is an
  unrelated local variable named `new_section_body` in a different function, not a call to this
  helper. `check_format_gaps` is the one real in-module consumer whose exact-H2 semantics must
  stay intact when widening is added (it matches literal canonical H2 template headings by
  construction, so a shared/default-changed `_section_body` would also change its behavior — this
  is exactly why the issue's own Backwards Compatibility section already says "new parameter or a
  separate helper," and this finding confirms that constraint rather than changing it).
- **Existing test will need updating, not just new tests added**: `test_ll_issues_check_decidable.py`
  already has `test_options_under_open_questions_exit_one` (lines 107-136) — a regression fixture
  for exactly the FEAT-2817-shaped scenario (options nested under
  `### Codebase Research Findings — <suffix>` inside `## Open Questions`) that currently asserts
  `returncode == 1` (NOT decidable). Once (1)+(2) land this test's expectation flips to
  `returncode == 0`; its docstring and assertions need updating in the same change, not just
  covered by new fixtures.
- **Analogous silently-inert-lint pattern to model the new diagnostic on**:
  `_validate_policy_dimensions_scored()` in `scripts/little_loops/fsm/validation.py:2431-2516` (the
  `policy_dims_scored_ok` lint this issue's Motivation section cites) unions two sources before
  declaring a dimension unscored — the declared `rubric_dimensions` set plus a regex scan
  (`rubric-dim-([\w-]+)\.txt`) over literal write sites — and its message names the specific inert
  predicate plus the runtime mechanism ("falls through to the catch-all"), not a generic
  "not found." The new `OPTIONS_MISSING`/`OPEN_QUESTIONS_REMAIN` messages in `check_decidable.py`
  (lines 39-44) and `check_open_questions.py` (lines 66-70) should follow the same shape: name the
  section where options were actually found (or state truthfully that none exist anywhere) rather
  than only naming the scanned section as today.
- **No existing prefix/depth-tolerant section helper to reuse**: confirmed no other helper in
  `issue_parser.py` does heading-depth-agnostic or prefix-tolerant matching —
  `_parse_section_items()` (`IssueParser` method, lines 1109-1145) is a separate, non-shared
  exact-H2 implementation used only for `Blocked By`/`Blocks` ID-list extraction. The widened
  resolver in Proposed Solution item (1) is genuinely new code, not a reuse of an existing helper.
  `_iter_option_blocks()` (346-362) and `_OPTION_HEADING_RE` (334-343) — the "Pattern 1+2" matcher
  that must stay unchanged per Scope Boundaries — already scan whatever text they're handed
  independent of section boundaries, so the whole-document fallback in item (2) can pass full
  `content` straight to the existing `_count_options_in_text()` / `_iter_option_blocks()` without
  modifying either.

## Implementation Steps

1. Add the whole-document fallback scan plus the section-aware diagnostic (2 + 3).
2. Add the widened/prefix section resolution behind a new parameter (1).
3. Add the four tests above; confirm no existing `_section_body` caller changes behavior.
4. Re-run `ll-issues deferred-triage` and re-check issues deferred as `decision_unresolved`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/tests/test_ll_issues_check_decidable.py::test_options_under_open_questions_exit_one` (lines 107-136) — flip the `returncode == 1`/`OPTIONS_MISSING` assertion and docstring to match the now-reachable option block; add a new negative-path fixture if a still-unreachable case is needed to preserve regression coverage.
6. Check `scripts/tests/test_ll_issues_check_open_questions.py` for the same exact-section-scope assumptions and update `OPEN_QUESTIONS_REMAIN` message assertions if the diagnostic text changes.
7. Add direct unit tests for `_section_body` and `count_enumerable_options` in `scripts/tests/test_issue_parser_unresolved.py` (new `TestCountEnumerableOptions` class), following that file's existing fixture-string-in/value-out convention — these functions currently have no unit coverage, only indirect subprocess coverage.
8. Verify `scripts/little_loops/loops/rn-remediate.yaml`'s in-process Python snippet (~line 339-357) that calls `count_open_questions_in_sections()`/`count_unresolved_options()` directly picks up the widened behavior (or needs an explicit opt-in argument).
9. Verify `scripts/tests/fixtures/issues/FEAT-398-decide-empty-proposed.md` stays a true-negative case after widening (referenced by the `docs/reference/CLI.md` "Exit 1 OPTIONS_MISSING" example).
10. Update `docs/reference/CLI.md`, `docs/guides/LOOPS_REFERENCE.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, and `skills/decide-issue/SKILL.md` Phase 3 prose if the widened scope or diagnostic message changes their documented examples/behavior description.

## Impact

- **Severity**: Medium — a correctness gap in a gate that silently defers ready work.
- **Scope**: `autodev`, `rn-remediate`, `/ll:decide-issue --validate-only`.
- **Benefit**: "0 enumerable options" becomes a statement about the document rather than about
  three headings.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` § Loop Authoring | `policy_dims_scored_ok` — the analogous silently-inert lint |
| `docs/reference/API.md` | `little_loops.issue_parser` section helpers |
| `skills/decide-issue/SKILL.md` | option/resolved-marker vocabulary the probes mirror |

## Resolution

Implemented (2)+(3) fully and (1) implicitly via a whole-document fallback scan in
`issue_parser.py`:

- `locate_enumerable_options()` / `locate_unresolved_options()` (new, alongside the
  existing `count_enumerable_options()` / `count_unresolved_options()`) try the scoped
  sections first (`## Proposed Solution`, then the fallback headings), then fall back to
  scanning every H2 section in the document — which, by construction, covers nested H3
  subsections and decorated/suffixed H2 headings without a separate depth/prefix
  resolver. Both return `(count, containing_heading)` for diagnostics.
- `check-decidable` / `check-open-questions` now name the section options were actually
  found in on success, and their failure messages state that the whole document was
  scanned (no longer implying only `## Proposed Solution` was checked).
- Flipped `test_options_under_open_questions_exit_one` → `test_options_under_open_questions_exit_zero`
  (FEAT-2817-shaped fixture now resolves as decidable) and added `TestCountEnumerableOptions`
  unit tests in `test_issue_parser_unresolved.py`.
- `_iter_option_blocks()`/`_OPTION_HEADING_RE` (Pattern 1+2) and `_section_body()`'s
  exact-H2 default were left untouched per Scope Boundaries; `check_format_gaps` (the one
  other `_section_body` in-module consumer) is unaffected.

## Session Log
- `/ll:ready-issue` - 2026-07-26T06:07:56 - `12e06889-14de-4bac-93c0-0271b15156c1.jsonl`
- `/ll:confidence-check` - 2026-07-26T00:00:00Z - `34e04778-f7ff-49f4-b11f-89ef0e9ac888.jsonl`
- `/ll:wire-issue` - 2026-07-26T06:05:48 - `0240cca2-661d-430e-8c4a-5a27bd1780f7.jsonl`
- `/ll:refine-issue` - 2026-07-26T06:00:06 - `d00ce073-12a9-4ac3-8b38-055e8a5baf8e.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:53:35Z - `ae9c212c-ff4e-4576-a5c4-7457be6284e5.jsonl`
- `/ll:manage-issue` - 2026-07-26T06:15:16Z - `788019e6-6863-44ae-93c1-a26d30e2d204.jsonl`

---

## Status

open
