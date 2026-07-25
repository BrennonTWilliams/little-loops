---
id: ENH-2821
type: ENH
priority: P3
status: open
captured_at: "2026-07-25T22:53:35Z"
discovered_date: 2026-07-25
discovered_by: capture-issue
labels: [issue-parser, decision-gate, observability]
relates_to: [BUG-2820, ENH-2443, ENH-2446, ENH-2607]
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

## Implementation Steps

1. Add the whole-document fallback scan plus the section-aware diagnostic (2 + 3).
2. Add the widened/prefix section resolution behind a new parameter (1).
3. Add the four tests above; confirm no existing `_section_body` caller changes behavior.
4. Re-run `ll-issues deferred-triage` and re-check issues deferred as `decision_unresolved`.

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

## Session Log
- `/ll:capture-issue` - 2026-07-25T22:53:35Z - `ae9c212c-ff4e-4576-a5c4-7457be6284e5.jsonl`

---

## Status

open
