---
id: BUG-3279
type: BUG
title: locate_enumerable_options gives the final option every remaining line of its
  section
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T15:45:38Z'
labels:
- decide-issue
- issue-parser
- locate-options
- scoring
relates_to:
- BUG-3278
- ENH-3280
- ENH-3277
- BUG-3285
size: Large
confidence_score: 96
outcome_confidence: 76
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 19
---

# BUG-3279: locate_enumerable_options gives the final option every remaining line of its section

## Summary

Option spans produced by `issue_parser.locate_enumerable_options` end at the next option's start
or, for the last option, at the end of the containing section. In a refined issue the prose that
follows the option list — analysis subsections, research findings, tables, and any
`### Decision Rationale` already appended — is therefore absorbed into the final option's `text`.
`/ll:decide-issue` Phase 4 hands that text to a scoring agent as the option's description.

## Current Behavior

`ll-issues locate-options ENH-3277 --json`, **as first captured at 2026-08-21T15:45Z**:

```
count 3  pattern bold_label  heading "Proposed Solution"
 - Option A — permanently exempt both.    160-165   (6 lines)
 - Option B — accept the guess.           166-171   (6 lines)
 - Option C — add a no-default read mode. 172-404   (232 lines)
```

`## Proposed Solution` spans 109–404, ending at `## Integration Map` on 405. Option C's real
description is roughly `172-188`. The remaining ~215 lines are unrelated content that belongs to
no option: the *Hard prerequisite* §2b table, *Dead site*, *Pinning `dead-code-cleanup`'s skip
edge*, *The three `harness-*` sites*, *Precedence*, *Codebase Research Findings*, and the
`### Decision Rationale` block.

> **Line numbers here are a snapshot, not an invariant.** ENH-3277 is an actively-refined issue
> and keeps growing, which is the *mechanism* of this bug — the absorbed span widens with every
> refine pass. Re-measured at 2026-08-21T18:20Z, the same command reports Option C at **`200-667`
> (467 lines)**, and `_unapplied_decision` emits **113** false reports rather than the ~40 recorded
> below. Verify against *relative* facts (last option's `end_line` == section end; its `text`
> contains `### Decision Rationale`), never against these absolute numbers.

Two consequences:

1. **Scoring reads the wrong text.** The Phase 4 `ll:codebase-pattern-finder` agent for Option C
   was given 232 lines of mostly-unrelated material as that option's description. Option C lost
   here anyway, so the outcome held — but the input was not the option.
2. **Re-running is not idempotent in effect.** `/ll:decide-issue` appends `### Decision Rationale`
   at the end of Proposed Solution (Phase 7a). On a second run that block falls inside the last
   option's span, so the previous decision's rationale and scoring table are fed back in as part
   of the final option's description. Phase 7a's idempotency rule skips the *write* but does not
   prevent the *extraction* from having already consumed it.

## Steps to Reproduce

1. Take any issue whose `## Proposed Solution` continues with `###` analysis subsections after the
   last option — ENH-3277 as it stood at commit-time is the live case.
2. Run `ll-issues locate-options ENH-3277 --json`.
3. Compare the last option's `end_line` against the line where its prose actually stops and
   against the next `###` subheading. (Snapshot values at capture time were 404 / ~188 / 205; see
   the drift note in Current Behavior — assert the *relation*, not the numbers.)
4. Inspect `options[-1].text` — it contains the §2b table, *Dead site*, *Pinning*, *Precedence*,
   *Codebase Research Findings*, and `### Decision Rationale`, none of which describe that option.

### Second consumer, same defect — `_unapplied_decision` (verified 2026-08-21)

`issue_parser._unapplied_decision` (`:1392`) does not call `locate_enumerable_options`; it uses a
sibling span function, `_option_block_spans`. It has the identical last-block absorption bug, and
`ll-issues format-check ENH-3277` shows it firing:

```
unapplied_decision: Proposed Solution still specifies `pytest` (rejected option)
unapplied_decision: Proposed Solution still specifies `lint_cmd` (rejected option)
unapplied_decision: Proposed Solution still specifies `ll-config get` (rejected option)
... ~40 more
```

None of those are rejected-option identifiers. They are ordinary vocabulary from the ~230 lines of
analysis prose that the last option block absorbed, reported as things the rejected option
"specifies".

**Its existing mitigations are the right idea and insufficient.** ENH-3256 already hardened this
function against exactly this failure with two clamps, both documented in its docstring: clamp the
final block at `### Decision Rationale`, and trim it at the end of its own `> **Selected:**`
callout line. Neither helps here — the last block is a *rejected* option (no callout to trim at),
and the `### Decision Rationale` boundary still leaves every intervening `###` subsection inside
the span.

The fix proposed below — terminate at the next qualifying heading — subsumes the
`### Decision Rationale` clamp and repairs this consumer too. It does **not** subsume the
`> **Selected:**` callout trim, which handles *unheaded* rationale prose no heading boundary can
see; see Implementation Step 3. **Fix both functions, or factor the boundary rule into one helper
they share**; two independent span implementations with the same bug is the reason this recurred
after ENH-3256 supposedly closed it.

## Expected Behavior

An option's span ends at the first structural boundary after it — the next option, the next
subheading (`###`/`####`), or the section end — whichever comes first. Trailing analysis prose
belongs to no option and is excluded from every option's `text`.

## Motivation

Option text is the sole input to Phase 4/5 scoring — the agents never read the issue themselves,
they read the span. A span that is 93% unrelated content makes the resulting scores unearned, and
because the extra content is *plausible* issue prose there is no signal that anything went wrong.
The distortion also scales the wrong way: it is worst on heavily-refined issues, which are exactly
the ones whose decisions carry the most downstream weight.

## Proposed Solution

Terminate each option span at the earliest of:

- the next extracted option's `start_line`
- the next **qualifying** markdown heading after the option's start (see the two rules below)
- the section end (current behavior, now the fallback rather than the rule)

The heading boundary is what resolves the observed case: the first `###` after Option C's start is
`### Hard prerequisite — pick a §2b row per site before writing any shell`, bounding Option C to
end there instead of at the section end.

### Rule 1 — the boundary must be fence-aware (mandatory, not optional)

`^#{1,6}\s` matches **shell comments inside fenced code blocks**, and option blocks in this repo
routinely contain fenced bash/python. A fence-blind boundary trades this bug for its mirror image:
silently *over*-trimming short, unrefined options at a fake heading.

Measured across all of `.issues/` (re-measured 2026-08-21, fence-aware): **36 live option blocks**
have their first heading-like line inside a fence and would be truncated there by a fence-blind
regex. (An earlier pass in this issue recorded 14; that undercounted — the correct figure is 36.)
Live examples:

| Issue | Option | Fake boundary the naive regex hits |
| --- | --- | --- |
| FEAT-1755 | Option A | `# Build the slash-command string exactly as l…` |
| FEAT-949 | Option B | `# Default CLAUDE.md resolution…` |
| FEAT-1452 | Option A / Option B | `# scripts/little_loops/extension.py…` |
| FEAT-1466 | Option B | `# scripts/tests/test_feat1462_doc_wiring…` |
| FEAT-1826 | Option B | `# in sft-corpus.yaml…` |
| BUG-2069 | Option A | `# in main_issues(), before `args = par…` |
| BUG-903 | Option A | `# scripts/little_loops/fsm/evaluators.py…` |
| BUG-1760 | Option C | `# Option A — add to autodev.yaml…` |

Use `little_loops.text_utils.fence_spans` / `in_fence` to skip heading matches inside fences —
imported function-locally, matching the existing precedent in `_duplicate_heading_groups` (`:1215`)
and `_empty_provenance_stub_matches` (`:1253`).

### Rule 2 — heading depth is tier-dependent

"Next heading at any depth" is wrong for the `section_header` tier, where the option **is itself**
an `### Option X` heading: a `####` subheading that is legitimate option content would cut the
span. The rule:

- **`section_header` tier** — boundary is the next heading at depth **≤ the option's own heading
  depth** (i.e. `###` or `##`, never its own `####` children).
- **`bold_label` / `numbered` / `bullet` tiers** — the option marker is not a heading, so any
  heading (`#{1,6}`) is a boundary.

**"The option's own depth" is a constant — do not build machinery to compute it.** The
`section_header` regex is `^###\s+Option\s+[A-Za-z0-9]` (`_OPTION_PATTERNS[0]`, `:1892`), anchored
at exactly three hashes; it can never match an option at any other depth. So the rule is two static
regexes, not a dynamic depth calculation:

- heading-shaped option → boundary `r"^#{1,3}\s"`
- non-heading-shaped option → boundary `r"^#{1,6}\s"`

**Tier is not available in the two sibling functions — decide depth per match, not per function.**
`_locate_options_in_text` picks exactly one `_OPTION_PATTERNS` tier per call, so "the option's own
tier" is well-defined there. `_option_block_spans` (`:1371`) and `_iter_option_blocks` (`:2216`) do
not have tiers: they share a single regex, `_OPTION_HEADING_RE` (`:2210`), whose alternation matches
**both** shapes in one pass —

```python
r"^(?:###\s+Option\s+[A-Za-z0-9]|\*\*Option\s+[A-Za-z0-9]+)"
```

— so one document can yield `###`-shaped and `**`-shaped blocks in the same `matches` list. In those
two functions the depth rule must be derived from each match's own text (heading-shaped match →
boundary at depth ≤ 3; bold-shaped match → boundary at any depth), not chosen once for the call.
Without this, Implementation Steps 3 and 4 have no implementable depth rule.

Blast radius, measured across all of `.issues/`: only **22** non-final options would truncate at
all under the naive any-depth rule, and all but ~3 of those truncations are *desired* (they cut at
`### Decision Rationale` / `### Codebase Research Findings`). The ~3 genuine over-trims are
`#### Decision 2 — …` subheadings inside an option body (FEAT-2478 Option B, FEAT-2598 Option B,
FEAT-1712 Option B) — exactly the shape Rule 2 protects. The rule is cheap insurance, and it turns
Implementation Step 2 from an exploratory "confirm nothing broke" into an assertable invariant.

### Rule 3 — `_iter_option_blocks` needs `_is_option_resolved` changed with it (blocker)

This is **not** a scope question to defer. Applying the boundary to `_iter_option_blocks` *without*
this change is a regression.

`_is_option_resolved` (`issue_parser.py:2242`) marks a block resolved if it contains
`> **Selected:**` **or** `### Decision Rationale`. Bounding blocks at the next heading means
`### Decision Rationale` can never fall inside a block again — the marker becomes dead code, and
every option it used to resolve flips back to unresolved.

Simulated across all of `.issues/` (2026-08-21) by substituting a heading-bounded
`_iter_option_blocks` and re-running `locate_unresolved_options`:

```
151 issues change their unresolved-option count
FEAT-2259  0 → 1     FEAT-1285  0 → 1     FEAT-1283  1 → 2
FEAT-3078  1 → 3     FEAT-1540  0 → 1     FEAT-2338  0 → 1    ...
```

The `0 → 1` flips are **already-decided issues newly reported as still having unresolved options**.
That flips the exit code of `ll-issues check-open-questions`, which is the *first* probe in
`resolve-decision.yaml`'s gate (`:63`) — so the loop would re-enter `decide` on issues that are
already decided.

Required with the boundary change: move the `### Decision Rationale` test from **block scope to
section scope** — if the section contains a `### Decision Rationale` heading anywhere, every option
block in that section is resolved. The `> **Selected:**` callout stays per-block (it lives inside
the winning option and is unaffected by the new boundary).

#### Net corpus effect — Rule 3 also moves 119 issues the *other* way

The 151-issue figure above is the boundary change **in isolation**. Simulating Rule 3 *as
specified* (fence-aware boundary + section-scope rationale) across all of `.issues/` (2026-08-21):

```
boundary alone:              151 gain,   0 lose
Rule 3 as specified:           0 gain, 119 lose
```

Rule 3 fully neutralizes the regression (0 gains — this is the invariant to assert). But it also
drops **119 issues to 0 unresolved options**. Those are decided issues whose winning option was
*not* the last one: today the appended `### Decision Rationale` only resolves the block that
absorbed it, so the middle non-winning options read as unresolved. Section-scope resolution fixes
that too.

This is a **second real bug fixed for free**, but it is still a gate-behavior change: for those 119
issues `ll-issues check-open-questions` flips nonzero → 0, so `resolve-decision.yaml` stops
re-entering `decide` on them. Both directions must be asserted at verification time (see
Implementation Step 5) — an implementer who sees a 119-issue diff and reads it as a regression will
"fix" it back and reintroduce the absorption dependency.

#### Known hazard — partially-decided multi-decision sections

Section scope means one `### Decision Rationale` anywhere in `## Proposed Solution` resolves
*every* option block in it. FEAT-2478 shows the shape at risk: two `#### Decision N` groups, four
option blocks, two independent `> **Selected:**` callouts. Decide only Decision 1, and all four
blocks read resolved — `check-open-questions` goes quiet on a genuinely open decision.

Measured across `.issues/` (2026-08-21): only **2** issues have 2+ `#### Decision N` groups in
Proposed Solution, and **0** are currently in the partially-decided state. Accept the rule as
specified rather than narrowing scope to the decision group — but record the hazard in
`_is_option_resolved`'s docstring and add the fixture named under Tests, so the next reader finds
it deliberate rather than undiscovered.

**Define "section" for both of `locate_unresolved_options`'s paths.** That function reaches
`_iter_option_blocks` two different ways and the section-scope test must be evaluated against the
same text the blocks came from, in each:

- **Named-section path** (`:2255`) — blocks come from `_section_body(content, heading)` for
  `Proposed Solution` then each `_OPTION_FALLBACK_SECTIONS` entry. Scope = that section body.
  Note this path accumulates across *all* named sections, so the test is per-section, not once
  per document.
- **Whole-document fallback** (`:2272`) — blocks come from `content[start:end]` for each
  `_iter_h2_sections` span. Scope = that H2 span, **not** the whole document.

**Caveat — section scope is deliberately blunt.** A single section holding *two* option groups
where only one is decided would be reported fully resolved. Measured across `.issues/`
(2026-08-21): five issues have two option groups under one `### Decision Rationale` — FEAT-3078,
FEAT-2878, BUG-1484, ENH-2888, ENH-2967 — and none is a live false negative (each is either fully
decided, or its second "group" is phantom blocks from the `_OPTION_HEADING_RE` prose-matching
defect tracked as **BUG-3285** — which also means the 151-issue flip measured above is computed
over a block set containing phantoms, so treat that number as an upper bound on this change's own
blast radius). Accepted as-is, because the alternative (associating a
`### Decision Rationale` with a specific option group) needs grouping logic this issue does not
introduce. Add a fixture pinning the shape so the trade-off is visible if it ever bites: two option
groups + one `### Decision Rationale`, asserting the known-blunt result rather than the ideal one.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- The codebase's one existing precedent for two near-duplicate span functions sharing a boundary
  rule is `_option_block_spans` (`:1371`) itself, whose docstring states it is an "offset-carrying
  sibling of `_iter_option_blocks` (`:2216`), built on the same `_OPTION_HEADING_RE` boundary
  rule" — i.e. this codebase's existing pattern for this situation is a shared boundary constant
  plus per-function iteration logic, not a single shared span-computing function.
- `_iter_option_blocks`'s docstring (`:2219`) already claims "Boundary = next `###`, `##`, or
  `**Option` line," but the actual `_OPTION_HEADING_RE` regex does not include a bare `###`/`##`
  alternative — the docstring is aspirational for the behavior this issue asks for, not a
  description of current behavior.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `locate_enumerable_options` span termination, and
  `_option_block_spans` / `_unapplied_decision` (`:1392`), which carry the same bug independently.
  Prefer a shared boundary helper over two parallel fixes
- `scripts/little_loops/issue_parser.py` — `_iter_option_blocks` (`:2216`), a **third** sibling
  span function with the identical unbounded-last-span defect (`end = matches[i + 1].start() if i
  + 1 < len(matches) else len(text)` at `:2229`). It backs `locate_unresolved_options` /
  `count_unresolved_options` / `ll-issues check-open-questions`, which `resolve-decision.yaml`'s
  gate tries *before* `check-decidable` (see Dependent Files below). If left unfixed, the primary
  decidability probe keeps the old absorption behavior while the fallback probe gets the fix —
  decide explicitly whether this is in scope or an accepted gap; the shared-helper approach this
  issue already proposes would naturally cover it. [Agent 2 finding] **Resolved: in scope — see
  Proposed Solution Rule 3, and note the coupled `_is_option_resolved` change below.**
- `scripts/little_loops/issue_parser.py` — `_is_option_resolved` (`:2242`) and
  `_RESOLVED_OPTION_MARKER_RE` (`:2204`). The `### Decision Rationale` alternative must move from
  block scope to section scope in the same change as `_iter_option_blocks`, or 151 issues in this
  repo alone gain phantom unresolved options (Rule 3)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/locate_options.py` — `cmd_locate_options` (`:38`) calls
  `locate_enumerable_options` and prints `option.start_line`/`option.end_line` directly in text
  mode and via `LocatedOptions.to_dict()` in `--json` mode; this is the CLI-visible edge of the
  span-length change (documented behavior change, not new coupling) [Agent 1/2 finding]
- `scripts/little_loops/cli/issues/check_decidable.py` — `cmd_check_decidable` (`:34`) calls
  `locate_enumerable_options` but reads only `.count`/`.heading`, never `.text`/`.end_line` —
  confirmed unaffected by the fix [Agent 1/2 finding]
- `scripts/little_loops/cli/issues/check_open_questions.py` — calls
  `little_loops.issue_parser.locate_unresolved_options`, built on `_iter_option_blocks` (see the
  new Files to Modify entry above) — affected only if that sibling function is also fixed [Agent 2
  finding]
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — `check_decision_decidable` state
  (`:63`) shells out `ll-issues check-open-questions ${context.issue_id} || ll-issues
  check-decidable ${context.issue_id}`; `check-open-questions` (untouched `_iter_option_blocks`
  path) is tried first, `check-decidable` (fixed `locate_enumerable_options` path) is the fallback
  — only the exit code is read, so this is a scope/ordering note, not a code change [Agent 1/2
  finding]

### Tests

- A fixture with a trailing `###` subsection after the last option: assert the last option's
  `end_line` stops at the subheading, not the section end
- A fixture whose option list *is* the section tail: assert the span still runs to section end
  (fallback preserved)
- A fixture containing a prior `### Decision Rationale` block: assert it appears in no option's
  `text`
- **Fence-awareness (Rule 1)**: a fixture whose option body contains a fenced block with a `# shell
  comment` first line — assert the span does **not** stop at it. Mirror the live FEAT-1755 Option A
  shape (` ```bash ` + `# Build the slash-command string …`)
- **Tier-dependent depth (Rule 2)**: a `section_header`-tier fixture (`### Option A`) whose body
  contains a `#### Decision 2 — …` subheading — assert the `####` is retained; and a matching
  `bold_label`-tier fixture where a `###` after the option marker *is* a boundary
- **Section-scope resolution (Rule 3)**: a decided fixture (options + a trailing
  `### Decision Rationale`) — assert `count_unresolved_options` is 0 both before and after the
  boundary change. This is the regression guard for the 151-issue flip measured above
- **Non-last winner (Rule 3, the 119-issue direction)**: a decided fixture whose `> **Selected:**`
  callout sits on the **first** of three options, with `### Decision Rationale` trailing the third —
  assert `count_unresolved_options` is 0 *after* the change (it is 2 today). This pins the
  second bug Rule 3 fixes, and stops a later reader from "restoring" the old counts
- **Mixed-shape depth (Rule 2, sibling functions)**: a fixture whose Proposed Solution holds both a
  `### Option A` block and a `**Option B: …**` block — assert the `###` block keeps a `####`
  subheading in its body while the `**`-shaped block terminates at a `###`. This is the direct test
  of per-match (not per-call) depth in `_option_block_spans` / `_iter_option_blocks`
- **Whole-document fallback scope (Rule 3)**: a fixture with no `## Proposed Solution` whose options
  sit under an unrelated H2 alongside a `### Decision Rationale`, plus a *second* H2 carrying
  undecided options — assert only the first H2's blocks are resolved, i.e. scope is the H2 span and
  not the document
- **Callout trim survives (Step 3)**: a fixture whose last option carries a `> **Selected:**`
  callout followed by *unheaded* rationale prose naming other identifiers — assert
  `_unapplied_decision` still reports nothing. Guards against deleting the trim as "redundant"
- **Two-group bluntness (Rule 3 caveat)**: two option groups under one `### Decision Rationale` —
  assert the known-blunt result (all resolved), pinning the accepted trade-off. Build it in the
  **partially-decided** shape, mirroring FEAT-2478: `#### Decision 1` with its options and a
  `> **Selected:**` callout, `#### Decision 2` with options and **no** callout, one trailing
  `### Decision Rationale` covering only Decision 1. Assert `count_unresolved_options == 0` and
  name in the test docstring that this is the accepted false negative — Decision 2 is open and the
  gate will not say so. A both-decided fixture does not exercise the hazard

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_locate_options.py` — no existing fixture places a trailing `###`
  subsection after the last option (all end their option section at an H2 boundary already
  excluded by current code); add a subprocess-level fixture mirroring the ENH-3277 live case to
  close the CLI-level gap alongside the unit-level one [Agent 3 finding]
- Confirmed no update needed: `scripts/tests/test_issue_parser_unresolved.py`,
  `scripts/tests/test_issue_parser.py` (`TestUnappliedDecision`), `scripts/tests/test_ll_issues_check_decidable.py`,
  `scripts/tests/test_decide_issue_skill.py`, `scripts/tests/test_program_design_gate.py` — none
  assert exact span/`end_line`/`text` values tied to the current buggy absorption behavior, so
  none will break [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- `scripts/tests/test_issue_parser_unresolved.py` — `TestLocatedOptionsDataclass` (`:19`),
  `TestLocatedOptionsPatternNames` (`:59`, one test per `_OPTION_PATTERNS` tier), and
  `TestCountEnumerableOptions` (`:106`) are the existing `locate_enumerable_options` coverage;
  none of them constructs a fixture with content trailing the last option, and none asserts
  `start_line`/`end_line` values directly.
- `scripts/tests/test_issue_parser.py` — `TestUnappliedDecision` (`:4757`), whose members build
  fixtures via a local `_issue(self, proposed_solution: str, **directive_sections: str) -> str`
  helper rather than a file fixture. `test_final_option_block_does_not_absorb_later_sections`
  (`:4931`) is the closest existing regression test to this bug's shape, but it covers
  cross-H2-section absorption (already excluded by `_section_body_with_offset`'s `##` boundary),
  not the trailing-`###`-inside-the-same-section case this issue is about, and it asserts the
  absence of a false-positive report rather than a specific span.

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Boundary idiom is inline `min()`, not shared**: this codebase's existing heading-boundary
  searches combine "next sibling boundary" and "next heading" candidates via a locally-computed
  `boundary = min(candidateA, candidateB)`, not a shared helper — evidence: `_empty_provenance_stub_matches`
  (`issue_parser.py:1268`), `_duplicate_heading_groups` (`:1227-1228`), `_strip_codebase_research_findings`
  (`:1365-1366`). No existing function spans all three sibling span functions this issue targets
  (`_locate_options_in_text`, `_option_block_spans`, `_iter_option_blocks`) — they currently share
  only the idiom, and only two of the three (`_option_block_spans`/`_iter_option_blocks`) share the
  `_OPTION_HEADING_RE` constant. [pattern-finder finding]
- **Multi-site heading regexes are hoisted to module-level `_UPPER_SNAKE_RE` constants** with a
  comment citing the introducing issue — evidence: `_H3_HEADING_RE` (`:1196`, `# ENH-3247:` comment
  `:1192-1195`), `_OPTION_HEADING_RE` (`:2210`), `_DECISION_RATIONALE_HEADING_RE` (`:1316`). The one
  existing "any-depth" heading regex is a counterexample that stays local rather than module-level:
  `_empty_provenance_stub_matches`'s `heading_re = re.compile(r"^#{1,6}\s", re.MULTILINE)` (`:1261`).
  [pattern-finder finding]
- **Contested precedent — heading depth**: two heading-depth regexes exist in this file —
  `r"^#{1,6}\s"` (any depth, `_empty_provenance_stub_matches:1261`) vs. `r"^#{1,3}\s"` (H1-H3 only,
  `_duplicate_heading_groups`, `_strip_codebase_research_findings`). This issue's Proposed Solution
  asks for "any depth," which only the first precedent matches directly. [pattern-finder finding]
- **Fence-awareness precedent**: `little_loops.text_utils.fence_spans`/`in_fence`, imported
  function-locally (not at module top) in both existing heading-boundary examples
  (`_duplicate_heading_groups:1215`, `_empty_provenance_stub_matches:1253`) — relevant if the new
  boundary logic must ignore headings that appear inside code fences. [pattern-finder finding]
- **Test fixture conventions for this consumer set**:
  `test_issue_parser_unresolved.py::TestCountEnumerableOptions` (`:106-155`) builds fixtures as bare
  inline markdown strings and asserts only `.count`/`.heading`, never `start_line`/`end_line`/`text`.
  `test_issue_parser.py::TestUnappliedDecision` (`:4757`) uses a local builder helper `_issue(self,
  proposed_solution, **directive_sections)` (`:4765-4770`); its closest existing regression test,
  `test_final_option_block_does_not_absorb_later_sections` (`:4931`), asserts absence of a
  false-positive report rather than a specific span, and covers cross-H2 absorption (already
  excluded by `_section_body_with_offset`'s `##` boundary) rather than the same-section
  trailing-`###` case this issue is about. `test_issues_locate_options.py` uses shared
  `_write_issue()` (`:38-50`) and `_invoke()` (`:53-62`) subprocess helpers, and its JSON-shape
  assertions check `set(option) == {"label", "text", "start_line", "end_line"}` (`:94`); no existing
  fixture there places a trailing `###` after the last option. [pattern-finder finding]

## Program Design

### Types

- `LocatedOption` (`scripts/little_loops/issue_parser.py:1907`) — dataclass fields `label: str`,
  `text: str`, `start_line: int`, `end_line: int`. `text`/`end_line` are what the fix changes for
  the last option in a section.
- `LocatedOptions` (`scripts/little_loops/issue_parser.py:1925`) — dataclass fields `count: int`,
  `pattern: str`, `heading: str`, `options: list[LocatedOption]`.

### Signatures

- `_locate_options_in_text(body: str, ...) -> list[LocatedOption]`
  (`scripts/little_loops/issue_parser.py:1967`) — computes each option's span; for all but the
  last match, `block_end = body.rfind("\n", 0, matches[i + 1].start()) + 1` (bounded by the next
  same-tier option marker); for the last match, `block_end = len(body)` unconditionally
  (`:1981-1984`) — the defect site.
- `locate_enumerable_options(content: str) -> LocatedOptions`
  (`scripts/little_loops/issue_parser.py:2134`) — sources `body` from
  `_section_body_with_offset(content, "Proposed Solution")` (`:2154`), the
  `_OPTION_FALLBACK_SECTIONS` sections (`:2162`), each `_iter_h2_sections(content)` span
  (`:2172`), or `_locate_directive_alternatives(content)` (`:2180`). Every `body` is
  H2-section-bounded (next `^##\s` line or EOF, per `_section_body_with_offset`,
  `scripts/little_loops/issue_parser.py:427`), never bounded at an interior `###`/`####`.
- `_option_block_spans(...)` (`scripts/little_loops/issue_parser.py:1371`) — sibling
  implementation, spans bounded by `_OPTION_HEADING_RE` (`:2210`, matches only `### Option X` /
  `**Option X` lines), with the same "last span runs to `len(text)`" defect.
- `_unapplied_decision(content: str) -> list[str]` (`scripts/little_loops/issue_parser.py:1392`)
  — consumes `_option_block_spans`, then applies two ENH-3256 clamps to the last span only: the
  `_DECISION_RATIONALE_HEADING_RE` clamp (`:1409-1417`, fires only on a literal
  `### Decision Rationale` heading) and the `> **Selected:**` callout trim (`:1419-1433`, fires
  only when that callout line is present). Neither clamp reacts to any other heading, table, or
  un-callout-marked prose.
- `_is_option_resolved(block_body: str) -> bool` (`scripts/little_loops/issue_parser.py:2242`) —
  returns `bool(_RESOLVED_OPTION_MARKER_RE.search(block_body))`, where the regex (`:2204`) is
  `> **Selected:**` OR `### Decision Rationale`. Consumed by `locate_unresolved_options` (`:2249`)
  → `count_unresolved_options` → `ll-issues check-open-questions`. The `### Decision Rationale`
  alternative only ever matches today *because* of the absorption bug this issue fixes — it is
  written at section end by `/ll:decide-issue` Phase 7a and lands inside the last option's block.
  Bounding the block kills the marker; hence the section-scope change in Rule 3.
- Existing "next heading at any depth" precedent (not currently reused by either option-span
  function): `_empty_provenance_stub_matches` (`scripts/little_loops/issue_parser.py:1241`) computes
  `heading_re = re.compile(r"^#{1,6}\s", re.MULTILINE)` and combines it with a sibling boundary via
  `boundary = min(next_stub_start, heading_start)` (`:1264-1269`), each candidate defaulting to
  `len(content)` when absent. `_duplicate_heading_groups` (`:1199`) and
  `_strip_codebase_research_findings`'s inner loop (`:1346`, boundary at `:1365`) use the narrower
  `r"^#{1,3}\s"` variant of the same idiom.

### Call Path

`locate_enumerable_options` → `_section_body_with_offset` / `_iter_h2_sections` (H2-only boundary)
→ `_locate_options_in_text` → last option's `block_end = len(body)` (defect).

`_unapplied_decision` → `_option_block_spans` (bounded by `_OPTION_HEADING_RE` only) →
`_DECISION_RATIONALE_HEADING_RE` clamp → `> **Selected:**` callout trim → `_decision_identifiers`
(`:1341`) reads whatever prose remains in the unclamped tail as the rejected option's content.

### Decision Rules

N/A — no new decision logic. This is a span-termination boundary fix, not a new gap kind, gate,
keyword list, or threshold.

## Implementation Steps

1. Add the heading boundary to span termination in **`_locate_options_in_text` (`:1967`)** — the
   actual defect site; `locate_enumerable_options` (`:2134`) is the public wrapper and needs no
   change. Keep section end as the fallback. The boundary must be **fence-aware** (Rule 1) —
   heading matches inside `fence_spans` are skipped, not treated as boundaries. (This helper is
   the one place tier *is* known per call, which is what makes Rule 2 directly implementable here;
   see Rule 2's per-match note for the sibling functions.)
2. Apply the tier-dependent depth rule (Rule 2): `section_header` options terminate only at a
   heading of depth ≤ their own; the other three tiers terminate at any depth. Assert directly
   that a `### Option A` block containing a `####` subheading keeps it.
3. Fix `_option_block_spans` / `_unapplied_decision` with the same boundary — **fence-aware, same
   as Step 1.** Rule 1 is written against `_locate_options_in_text`, but it applies identically
   here, and with an extra wrinkle: `_OPTION_HEADING_RE` (`:2210`) is **not** fence-aware today, so
   a `**Option A` line inside a fenced block already registers as an option marker. Apply
   `fence_spans` / `in_fence` to *both* the option markers and the new heading boundary in these two
   functions. The two ENH-3256
   clamps are **not** equally redundant — treat them separately:
   - `_DECISION_RATIONALE_HEADING_RE` clamp (`:1409-1417`) — subsumed, because
     `### Decision Rationale` *is* a heading and the new boundary stops there anyway. Delete it.
   - `> **Selected:**` callout trim (`:1419-1433`) — **keep it.** Its documented job (`:1424-1432`)
     is dropping *unheaded* free-form rationale prose that follows the callout line before the
     section end. No heading boundary can catch unheaded prose, so deleting this one reintroduces
     the exact false reports ENH-3256 fixed.

   Update the docstring either way. Leaving a docstring that advertises clamps as the mechanism is
   how this bug recurred after ENH-3256; the next reader must see the boundary as the rule and the
   callout trim as the one residual clamp.
4. Fix `_iter_option_blocks` **together with** the section-scope `### Decision Rationale` change in
   `_is_option_resolved` (Rule 3) — also fence-aware, per Step 3 (this function shares
   `_OPTION_HEADING_RE`). These land in one commit — the boundary alone is a regression. Record the
   partially-decided multi-decision hazard (Rule 3's second note) in `_is_option_resolved`'s
   docstring while changing it.
5. Verify, in order:
   - `ll-issues locate-options ENH-3277 --json` bounds the last option at the first `###` after its
     start rather than at the section end, and no option's `text` contains `### Decision Rationale`.
     **State this as `end_line == boundary_line - 1`, not "ends at the heading."** `_locate_options_in_text`
     sets `abs_end = block_end - 1` (`:1987`) while `text` is `rstrip`ped, so a bounded option's
     `end_line` lands on the last line *before* the boundary heading — commonly a blank line, and
     one line past the last line of `text`. This is existing behavior for every non-last option; the
     fix makes the last option match it. Assert the relation, not "no trailing blank."
   - `ll-issues format-check ENH-3277` no longer emits `unapplied_decision` reports for ordinary
     analysis vocabulary (was 113 at 2026-08-21T18:20Z).
   - **Corpus regression check — assert BOTH directions.** Re-run `locate_unresolved_options` over
     all of `.issues/` before and after. The expected result is not "unchanged":

     | Direction | Expected | Meaning |
     | --- | --- | --- |
     | issues *gaining* unresolved options | **0** | Rule 3's regression guard. Any gain = the section-scope change is missing or mis-scoped |
     | issues *losing* unresolved options | **~119** | Expected and correct — decided issues whose winner wasn't the last option (see Rule 3's net-effect note) |

     A one-directional check cannot distinguish success from regression here. In particular, do
     **not** treat the ~119 drops as a defect and "fix" them back — doing so reintroduces the
     dependency on the absorption bug this issue removes. The drop count is corpus-dependent; assert
     `gains == 0` strictly and record the drop count as an observation.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Decide explicitly whether `_iter_option_blocks` (`issue_parser.py:2216`) … is in scope for this
  fix or an accepted gap~~ — **resolved: in scope, and it carries a blocker.** See Proposed
  Solution Rule 3. It must be fixed together with a section-scope `### Decision Rationale` test in
  `_is_option_resolved`; the boundary alone flips 151 issues' unresolved counts and makes
  `resolve-decision.yaml`'s gate re-decide already-decided issues
- Add a subprocess-level fixture to `scripts/tests/test_issues_locate_options.py` with a trailing
  `###` subsection after the last option, mirroring the ENH-3277 live case
- No changes needed in `scripts/little_loops/cli/issues/check_decidable.py`,
  `scripts/little_loops/cli/issues/locate_options.py`, or `resolve-decision.yaml` themselves —
  they consume the fixed function's output without code changes, confirmed above

## Impact

- **Priority**: P2 — degrades decision quality on the issues that matter most, but does not
  corrupt files or block the pipeline
- **Effort**: Large (matches frontmatter `size`) — not "one span-termination rule." Three sibling
  span functions, a coupled change to `_is_option_resolved`, fence-awareness, a tier-dependent
  depth rule, and a corpus-level regression check
- **Risk**: Medium-High — `locate_enumerable_options` is shared by `/ll:decide-issue`,
  `ll-issues check-decidable`, and the FSM pre-`decide` gate. Two distinct over-trim hazards were
  measured, not hypothesized: 36 option blocks truncatable at an in-fence `#` comment (Rule 1) and
  ~3 at a legitimate `####` inside a `section_header` option (Rule 2). The gate-behavior change in
  Rule 3 is the highest-consequence path
- **Breaking Change**: Not for the span API — spans narrow, and `count` / `pattern` are unaffected.
  **But `ll-issues check-open-questions` changes exit code for ~119 issues** (nonzero → 0), which
  changes what `resolve-decision.yaml`'s gate does on each of them. That is intended (they are
  decided issues that were falsely reported open — see Rule 3's net-effect note), and no consumer
  reads anything but the exit code, so nothing downstream breaks. Called out here because "spans
  only narrow" understates the blast radius: the resolution *semantics* change too

## Root Cause

`scripts/little_loops/issue_parser.py`, `_locate_options_in_text` (`:1967`, reached via the
`locate_enumerable_options` wrapper) — the last option's `block_end` is set to `len(body)`
(`:1981-1984`), i.e. the section end, with no intervening boundary check. The bug is invisible for
short unrefined issues (where the option list *is* the tail of the section) and grows with the
amount of post-option analysis a refined issue accumulates, so it surfaces exactly on the issues
where the decision matters most.

## Related Key Documentation

- `skills/decide-issue/SKILL.md` — Phase 3 (extraction contract), Phase 4 (consumer), Phase 7a
  (the appended block this bug re-consumes)

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-21T17:30:27 - `08ddfd12-c4b5-4b15-9c96-41356558ea91.jsonl`
- `/ll:verify-issues` - 2026-08-21T17:13:31 - `99f6c71e-f475-4121-a410-ed5319e99e15.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:11:12 - `125e158d-3f91-476d-a1f8-8948c119463c.jsonl`
- `/ll:verify-issues` - 2026-08-21T17:08:09 - `30039977-bd37-407d-b1f7-a908c1d5229a.jsonl`
- `/ll:wire-issue` - 2026-08-21T17:04:54 - `629cd76b-9b9d-43eb-b533-f3f6d22e241f.jsonl`
- `/ll:refine-issue` - 2026-08-21T16:58:08 - `5cf4fcb6-3c57-44e4-b058-cd6b81dee14a.jsonl`
- `/ll:capture-issue` - 2026-08-21T15:46:43 - `da526826-2179-460f-b823-35695378ac55.jsonl`
