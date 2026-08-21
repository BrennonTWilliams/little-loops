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
verify_verdict: NON_VALID
size: Large
---

# BUG-3279: locate_enumerable_options gives the final option every remaining line of its section

## Summary

Option spans produced by `issue_parser.locate_enumerable_options` end at the next option's start
or, for the last option, at the end of the containing section. In a refined issue the prose that
follows the option list — analysis subsections, research findings, tables, and any
`### Decision Rationale` already appended — is therefore absorbed into the final option's `text`.
`/ll:decide-issue` Phase 4 hands that text to a scoring agent as the option's description.

## Current Behavior

`ll-issues locate-options ENH-3277 --json` (2026-08-21):

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
3. Compare the last option's `end_line` (404) against the line where its prose actually stops
   (~188) and against the next subheading (`### Hard prerequisite …`, line 205).
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

The fix proposed below — terminate at the next heading of any depth — subsumes both existing
clamps and repairs this consumer too. **Fix both functions, or factor the boundary rule into one
helper they share**; two independent span implementations with the same bug is the reason this
recurred after ENH-3256 supposedly closed it.

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
- the next markdown heading at any depth after the option's start
- the section end (current behavior, now the fallback rather than the rule)

The heading boundary is what resolves the observed case: the first `###` after Option C's start is
`### Hard prerequisite — pick a §2b row per site before writing any shell` at line 205, bounding
Option C to `172-204` instead of `172-404`.

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
  issue already proposes would naturally cover it. [Agent 2 finding]

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

1. Add the heading boundary to span termination in `locate_enumerable_options`, keeping section
   end as the fallback.
2. Confirm the boundary does not truncate legitimately-subheaded options — a `### Option A`
   (`section_header` tier) block whose body contains a `####` subheading must not stop there.
   This is the one shape where the fix could over-trim.
3. Verify: `ll-issues locate-options ENH-3277 --json` bounds Option C at `172-204` rather than
   `172-404`, and no option's `text` contains `### Decision Rationale`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Decide explicitly whether `_iter_option_blocks` (`issue_parser.py:2216`) — the third sibling
  span function backing `ll-issues check-open-questions`, tried before `check-decidable` in
  `resolve-decision.yaml`'s gate — is in scope for this fix or an accepted gap; if in scope,
  fold it into the shared boundary helper
- Add a subprocess-level fixture to `scripts/tests/test_issues_locate_options.py` with a trailing
  `###` subsection after the last option, mirroring the ENH-3277 live case
- No changes needed in `scripts/little_loops/cli/issues/check_decidable.py`,
  `scripts/little_loops/cli/issues/locate_options.py`, or `resolve-decision.yaml` themselves —
  they consume the fixed function's output without code changes, confirmed above

## Impact

- **Priority**: P2 — degrades decision quality on the issues that matter most, but does not
  corrupt files or block the pipeline
- **Effort**: Small — one span-termination rule plus fixtures
- **Risk**: Medium — `locate_enumerable_options` is shared by `/ll:decide-issue`,
  `ll-issues check-decidable`, and the FSM pre-`decide` gate, so a too-aggressive boundary
  could shrink options that legitimately contain subheadings (see step 2)
- **Breaking Change**: No — spans narrow, `count` and `pattern` are unaffected

## Root Cause

`scripts/little_loops/issue_parser.py`, `locate_enumerable_options` — the last option's
`end_line` is set to the section end with no intervening boundary check. The bug is invisible for
short unrefined issues (where the option list *is* the tail of the section) and grows with the
amount of post-option analysis a refined issue accumulates, so it surfaces exactly on the issues
where the decision matters most.

## Related Key Documentation

- `skills/decide-issue/SKILL.md` — Phase 3 (extraction contract), Phase 4 (consumer), Phase 7a
  (the appended block this bug re-consumes)

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-08-21T17:13:31 - `99f6c71e-f475-4121-a410-ed5319e99e15.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:11:12 - `125e158d-3f91-476d-a1f8-8948c119463c.jsonl`
- `/ll:verify-issues` - 2026-08-21T17:08:09 - `30039977-bd37-407d-b1f7-a908c1d5229a.jsonl`
- `/ll:wire-issue` - 2026-08-21T17:04:54 - `629cd76b-9b9d-43eb-b533-f3f6d22e241f.jsonl`
- `/ll:refine-issue` - 2026-08-21T16:58:08 - `5cf4fcb6-3c57-44e4-b058-cd6b81dee14a.jsonl`
- `/ll:capture-issue` - 2026-08-21T15:46:43 - `da526826-2179-460f-b823-35695378ac55.jsonl`
