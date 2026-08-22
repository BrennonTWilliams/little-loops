---
id: BUG-3295
type: BUG
title: unapplied_decision flags bare key mentions as discriminating identifiers
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
captured_at: '2026-08-22T21:27:39Z'
relates_to:
- BUG-3289
confidence_score: 99
outcome_confidence: 91
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 19
score_change_surface: 25
---

# BUG-3295: unapplied_decision flags bare key mentions as discriminating identifiers

## Summary

`_unapplied_decision()`'s decision-gap detector produces false-positive
`unapplied_decision` findings whenever a decision is about "what literal value
to assign to some field/key" and any option's prose mentions the bare key
name as its own backtick span. The root cause is structural, not a wording
quirk on any one issue: it will recur on any similarly-shaped decision.

## Current Behavior

`_decision_identifiers()` (`scripts/little_loops/issue_parser.py:1401-1403`,
regex `_DECISION_IDENTIFIER_RE = re.compile(r"`([^`\n]{3,})`")` at `:1379`)
extracts each backtick-delimited span as one opaque, atomic string. There is
no relationship between a bare identifier (e.g. `` `scope:` ``) and any
compound identifier that embeds it as a substring (e.g.
`` `scope: ["scripts/"]` ``, `` `scope: ["."]` ``).

In `_unapplied_decision()` (`:1499` onward, the `discriminating = rej_ids -
sel_ids` set-difference at `:1580`): if the selected option always writes
the full literal (`` `scope: ["."]` ``) but a rejected option happens to
mention the bare key alone anywhere in its own text (natural phrasing:
"...then change `` `scope:` `` to `` `["${context.src_dir}"]` ``"), the bare
key lands in `discriminating` even though both options are about the same
field, not competing identifiers. The second pass then greps every directive
section for that literal bare-backtick substring and fires on any narrative
mention of the field name — common, not rare, in this codebase's
issue-writing convention (heavily backtick-quoted, mechanism-explaining prose
from `/ll:refine-issue` and `/ll:wire-issue`).

**Reproduced on ENH-3292** (`.issues/enhancements/P3-ENH-3292-*.md`): Option A
(selected) writes `scope: ["scripts/"]` -> `scope: ["."]`; Option B (rejected)
contains the bare span `` `scope:` `` once. That bare `scope:` is not in
Option A's identifier set (which only has the compound literal spans), so it
is flagged as "discriminating," and then matches 27 separate bare `` `scope:`
`` mentions elsewhere in the issue's Program Design/Acceptance
Criteria/Motivation sections that are pure narrative explanation — producing
a spurious `unapplied_decision` gap that caps `/ll:confidence-check`'s
Ambiguity criterion at 10/25 for a fully-decided, well-specified issue.

## Steps to Reproduce

1. Open `.issues/enhancements/P3-ENH-3292-*.md`.
2. Note its decision block: Option A (selected) writes the compound literal
   `` `scope: ["scripts/"]` `` -> `` `scope: ["."]` ``; Option B (rejected)
   contains the bare span `` `scope:` `` once, as incidental phrasing.
3. Run `ll-issues format-check ENH-3292`.
4. Observe an `unapplied_decision` gap that treats bare `` `scope:` `` as a
   "discriminating" identifier and reports 27 separate narrative mentions of
   it in the Program Design/Acceptance Criteria/Motivation sections as
   unapplied — even though the decision is fully applied via the compound
   literal Option A already writes.

## Expected Behavior

A bare identifier that is a substring of / subsumed by a compound identifier
already present in the selected option's identifier set should not count as
"discriminating." `_decision_identifiers`/`_unapplied_decision` need a real
containment/equivalence relationship between backtick spans, not pure
atomic-string set difference.

## Motivation

This is not an isolated glitch — it is the same option-locator/decision-
identifier subsystem that already has two other false-negative/invisibility
bug reports on file:

- BUG-3287: two shapes of tier-match/bullet-tier misses
- BUG-3293: bold-numbered decision points invisible to tier scan and Pattern E

This is a fourth flavor of the same still-maturing heuristic family
(introduced by ENH-3256), and it will keep recurring on any "pick a literal
value for field X" decision issue unless the underlying identifier-
relationship gap is fixed — not just patched for this one field name.

## Proposed Solution

Modify `_unapplied_decision()`'s `discriminating = rej_ids - sel_ids`
computation (`scripts/little_loops/issue_parser.py:1580`) to exclude any
`rej_ids` member that is a substring of an identifier already present in
`sel_ids`, before the exact-match set difference:

```python
sel_ids = _decision_identifiers(block_texts[selected_index])
rej_ids = set()
for i, text in enumerate(block_texts):
    if i != selected_index:
        rej_ids |= _decision_identifiers(text)

subsumed = {r for r in rej_ids if any(r in s for s in sel_ids)}
discriminating = (rej_ids - subsumed) - sel_ids
```

A rejected-option identifier that is a substring of a selected-option
identifier (e.g. bare `` `scope:` `` inside compound `` `scope: ["."]` ``)
names the same field being decided, not a competing identifier, so it is
excluded from `discriminating` before the subtraction runs. An identifier
introduced only by a rejected option with no containment relationship to any
`sel_ids` member is unaffected and still fires (negative control — see
Implementation Steps #2). This composes with BUG-3289's
`_shared_subject_identifiers` subtraction on the same statement: both are
independent, order-insensitive exclusions applied around the same
`rej_ids - sel_ids` core.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

- No containment/subsumption idiom for backtick-delimited identifier strings exists anywhere in `issue_parser.py` today (confirmed by direct grep). The two nearest analogues in this codebase operate on different domains and are not directly reusable: `in_fence(start, end, spans)` / `fence_spans()` (`scripts/little_loops/text_utils.py:97`, `:64`) relate *offset spans*, not identifier text; `classify_file_ref()` / `suffix_match_candidates()` (`scripts/little_loops/text_utils.py:269`, `:333`) relate `/`-delimited *file paths* by suffix, with an explicit ambiguity tie-break rule (`suffix_match_candidates` docstring: "Ambiguous matches must not silently resolve"). Whichever containment rule this issue settles on (e.g. exact-substring, or a stricter "shares the same leading key token" match) needs its own tie-break precedent stated explicitly, the same way `suffix_match_candidates` does, rather than assuming plain substring containment is unambiguous — a bare identifier could in principle be a substring of more than one compound identifier in `sel_ids`.
- This function's own existing false-positive mitigations are all *region*-exclusions (masking or slicing out a span before scanning) — `_strip_codebase_research_findings()` (`issue_parser.py:1406-1428`), the `> **Selected:**` callout-line masking (`:1543-1560`), the final-block trailing-callout trim (`:1527-1541`), the self-scan `scrub_start` subtraction (`:1584-1596`) — never a vocabulary/identifier-relationship filter. A containment fix here is a new axis for this function, not an extension of an existing one.
- **Coordination constraint, not a blocker**: BUG-3289 (linked, `relates_to`) is an open, already-decided sibling fix targeting the identical `discriminating = rej_ids - sel_ids` statement (`issue_parser.py:1580`) for shared-subject vocabulary (an orthogonal axis — see Integration Map → Conventions in Force). The two fixes are independent and can land in either order, but both edit the same statement; whichever lands second must compose with the other's subtraction rather than clobber it.
- Established convention for landing a fix in this exact heuristic family (BUG-3293's landed fixes): document the corpus-measured effect (files gained/lost, zero-spurious count) in a `# BUG-NNNN:` comment directly above the changed regex/constant, and run a live sweep over `.issues/` at implementation time. Three different corpus-regression strengths already coexist for this specific detector (pinned-exact-match, crash-only, one-directional `new_reports == 0`) — see Integration Map → Tests; this fix should pick the strength that matches how precisely its containment rule's corpus effect can be bounded ahead of time.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `_decision_identifiers()` (`:1401-1403`) and/or `_unapplied_decision()`'s `discriminating = rej_ids - sel_ids` line (`:1580`, confirmed by direct read; this issue's Current Behavior/Root Cause anchors have been corrected in place to match). `sel_ids` is built at `:1574`, the `rej_ids` union loop at `:1575-1578`. `_DECISION_IDENTIFIER_RE` (`:1379`) is a candidate but likely unchanged — the regex controls what spans are captured, not their relationships.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py:1164` — `check_format_gaps()` calls `gaps.unapplied_decision.extend(_unapplied_decision(content))`; no change expected here, only in what `_unapplied_decision` returns.
- `scripts/little_loops/cli/issues/format_check.py:475-476, 493` — surfaces `unapplied_decision` gaps to `ll-issues format-check` output; consumes the list only, no code change expected.
- `scripts/little_loops/cli/issues/__init__.py:148` — lists `unapplied_decision` in the `format-check` subcommand help text.
- FSM `ensure_formatted` states shell out to `ll-issues format-check` and read only the exit code (per BUG-3289's Integration Map, same call path), so a strictly-narrowing fix can flip a gate from fail to pass but never the reverse.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/confidence-check/SKILL.md:198, 208` — `FC_JSON` shell parsing pulls `unapplied_decision` from `ll-issues format-check` JSON; this is the actual Criterion C consumer this bug's own Motivation/Impact sections describe as being capped by the false positive. No code/text change expected — the extraction mechanism is unaffected, only which issues populate the list shrinks favorably. [confirmed by codebase-analyzer, ll-code callers-of found no direct code-graph edge since this is a shell/JSON coupling, not a Python call]
- `skills/confidence-check/rubric.md:316, 324` — Criterion C scoring table caps score on any non-empty `unapplied_decision` gap list. No change expected — the cap mechanism is unaffected, only which issues trip it.
- `scripts/tests/test_confidence_check_skill.py:582, 593-594, 632-633` — asserts `SKILL.md`/`rubric.md` reference the `unapplied_decision` gap key by name; presence-only assertions, unaffected by this fix.
- `scripts/tests/test_ll_issues_format_check.py:369` — asserts JSON output includes an `"unapplied_decision": []` key; unaffected.

### Conventions in Force
- This codebase has no existing precedent for backtick-identifier containment/subsumption — a grep across `issue_parser.py` for substring/containment/longest-match logic between two extracted identifier strings finds none. The two nearest analogues operate on different domains: span-offset containment (`in_fence(start, end, spans)` / `fence_spans()`, `scripts/little_loops/text_utils.py:97`, `:64`) and file-path suffix matching with an explicit ambiguity tie-break (`classify_file_ref()` / `suffix_match_candidates()`, `scripts/little_loops/text_utils.py:269`, `:333`). Neither is identifier-string containment; both are cited only as this file's closest structural precedent for "one extracted unit relates to another by containment, with an explicit rule for what wins."
- Landed fixes to this same option-locator/decision-identifier family are documented inline with a `# BUG-NNNN:` comment stating the exact corpus-measured effect directly above the regex/constant changed — e.g. `_DECIDE_IMPERATIVE_RE` (`issue_parser.py:2154-2165`), `_INLINE_OR_RE` (`:2179-2184`), `_DECISION_RULES_NUMBERED_RE` (`:2278-2295`) — evidence: BUG-3293's landed fixes, corpus-measured before/after.
- Every existing false-positive mitigation already inside `_unapplied_decision()` itself is a *region*-exclusion (slice out a span before scanning), not a vocabulary or identifier-relationship filter: `_strip_codebase_research_findings()` (`:1406-1428`, drops `### Codebase Research Findings` blocks), the `> **Selected:**` callout-line masking (`:1543-1560`), the final-block trailing-callout trim (`:1527-1541`), and the self-scan `scrub_start`/`scrubbed_proposed` subtraction (`:1584-1596`). BUG-3289's own Integration Map (`.issues/bugs/P2-BUG-3289-*.md:260-265`) names this same taxonomy explicitly: "region-based ... vocabulary-based." BUG-3295's containment/equivalence question is neither axis as previously used in this function.
- **Sibling fix on the same statement, already decided, still open**: BUG-3289 (relates_to, linked) targets this exact `discriminating = rej_ids - sel_ids` line for a different, orthogonal defect — shared-subject vocabulary (identifiers named in the issue's own title/Summary before either option exists) rather than containment. Its already-decided design is a separate `_shared_subject_identifiers(content) -> set[str]` helper, subtracted once at the same call site. The two fixes are independent (containment relates two identifiers to each other; shared-subject relates an identifier to the issue's own preamble) and order-insensitive, but both edit the same statement — whichever lands second should compose with, not overwrite, the other's subtraction.

### Tests
- `scripts/tests/test_issue_parser.py::TestUnappliedDecision` (`:5093-5397`) — the fixture class to extend. Shared builder: `_issue(self, proposed_solution: str, **directive_sections: str) -> str` (`:5101-5106`). Existing tests assert either `== []` (no gap) or `any("<substr>" in r for r in reasons)` (a gap containing this substring fired). `test_winner_tail_narrows_sel_ids_promoting_shared_identifier_to_discriminating` (`:5340-5397`) already asserts directly on the intermediate `sel_ids`/`rej_ids` sets in addition to the end-to-end report list, and its docstring notes an assertion there is coupled to BUG-3289 landing — a precedent for isolating boundary-layer vs. report-layer assertions in a fixture for this same containment question.
- `scripts/tests/test_issue_parser.py::TestUnappliedDecisionLiveCorpusSweep` (`:5466-5497`) — crash-only sweep over the live `.issues/` corpus (`isinstance(reasons, list)`, no count pinning); its docstring states this detector fires on "roughly 40% of the ~307 issues carrying a `> **Selected:**` callout" as "a known precision limit of pure lexical identifier-diffing."
- `scripts/tests/test_issue_parser.py::TestBug3293DecisionRulesCorpusDifferential` (`:5399-5464`) — pinned-exact-match corpus regression (`_PINNED` dict of filename → `(pattern, count)`), used elsewhere in this same file family; asserts `unexpected == []` for newly-matched files outside the pinned set. BUG-3289's own Implementation Steps propose a third shape instead — record the report-total drop as an observation, assert `new_reports == 0` strictly (a subtraction can only remove reports). These three corpus-regression strengths coexist in this subsystem and are chosen per-detector, not by one codebase-wide rule. `TestBug3293DecisionRulesCorpusDifferential` targets `locate_enumerable_options`, a strictly-additive structural change — not directly reusable in shape here since BUG-3295 is strictly-narrowing through `_unapplied_decision`'s free-text `reasons` list. **Decided strength: BUG-3289's shape** — record the corpus report-total drop as an observation, assert `new_reports == 0` strictly. The fix is provably one-directional (a pre-subtraction exclusion can only shrink `discriminating`, so no issue can gain a report), which makes the strict zero-new-reports assertion achievable and strictly stronger than the crash-only sweep; the crash-only `TestUnappliedDecisionLiveCorpusSweep` still runs unchanged alongside it.

_Wiring pass added by `/ll:wire-issue`:_
- Model the new no-gap fixture after `test_empty_discriminating_set_is_inert` (`:5220-5230`) — the closest existing "REJ - SEL is empty" precedent, though it uses identical strings rather than containment. Model the negative-control fixture (Implementation Steps #2) after `test_negated_mention_still_fires` (`:5161-5174`), which asserts a disjoint identifier with no containment relationship still fires. Confirmed via full read: no existing fixture in `TestUnappliedDecision` currently relies on a bare-key-subsumed-by-compound-literal pattern to fire a gap, so this fix changes zero existing test outcomes — it is a pure addition, not an update. [codebase-pattern-finder finding]
- `_shared_subject_identifiers` (BUG-3289's proposed helper) is confirmed absent from `scripts/little_loops/issue_parser.py` as of this pass — BUG-3289 has not landed, so Implementation Steps #3's composition check has nothing to compose against yet. [codebase-pattern-finder + codebase-analyzer finding, cross-checked]

### Documentation
- `docs/reference/API.md:895, 920` — `check_format_gaps` docstring reproduction and the `**unapplied_decision** (ENH-3256)` gap description document the `REJ - SEL` rule this bug reports as flawed; update if the rule's description changes.
- `docs/reference/CLI.md:148` — `ll-issues format-check` subcommand's gap-kind list.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2065, 2257` — the `:148` citation above is a stale anchor (that line is inside an unrelated skills-capability JSON example, not the gap-kind list); the correct locations are `:2065` (gap-kind description prose for `unapplied_decision`) and `:2257` (`--format json` example line listing gap-kind keys). Both are stated at the semantic/outcome level and remain accurate after this narrowing fix — no text change required at either location. [confirmed by codebase-locator + codebase-analyzer]

### Configuration
- N/A

## Program Design

### Types

N/A — no new data structures. The fix operates on the existing `set[str]` values (`sel_ids`, `rej_ids`, `discriminating`) already flowing through `_unapplied_decision`.

### Signatures

- `_decision_identifiers(text: str) -> set[str]` — `scripts/little_loops/issue_parser.py:1401-1403`. Pure per-block extractor, no document-level context. Returns every backtick-delimited span (regex `_DECISION_IDENTIFIER_RE`, `:1379`) of length >= 3 as a flat string, no normalization.
- `_unapplied_decision(content: str) -> list[str]` — `scripts/little_loops/issue_parser.py:1499-1622`. `sel_ids = _decision_identifiers(block_texts[selected_index])` at `:1574`; `rej_ids` unioned across every non-selected block at `:1575-1578`; `discriminating = rej_ids - sel_ids` (plain `set.__sub__`, exact-string equality only) at `:1580`. This is the confirmed fix site (the issue's Current Behavior/Root Cause anchors now cite `:1580` as well).
- Downstream consumers of `discriminating` (unchanged by this fix, but must keep working against whatever `discriminating` contains after it): `needle = f"`{identifier}`"` (`:1610`) and the paragraph substring check `needle in paragraph` (`:1615`), for `identifier in sorted(discriminating)` (`:1609`).

### Call Path

`ll-issues format-check ID` -> `cmd_format_check` -> `check_format_gaps` (`issue_parser.py:1164`) -> `_unapplied_decision` (`:1499`) -> `_decision_identifiers` per block (`:1574`, `:1578`) -> `discriminating = rej_ids - sel_ids` (`:1580`, fix site) -> per-`identifier`-in-`discriminating` directive-section paragraph scan (`:1609-1621`) -> `reasons: list[str]`.

### Decision Rules

No new gap kind, gate, keyword list, or threshold — but the containment relation itself is a new rule and its precision boundary is decided here, not left to the implementer:

- **Containment rule (decided): plain substring, one-directional.** A rejected-option identifier `r` is excluded from `discriminating` iff `any(r in s for s in sel_ids)` — plain Python substring, no word-boundary or leading-key-token requirement. Rationale: a stricter boundary-aware rule (`\b`-based, or "shares the same leading key token") breaks on punctuation-heavy spans that are legitimate subsumptions — e.g. rejected `` `["."]` `` inside selected `` `scope: ["."]` `` is neither `\b`-delimited nor key-prefixed, yet plainly names the same decided value. Accepted trade-off: a short generic rejected span (the `_DECISION_IDENTIFIER_RE` floor is 3 chars, so e.g. `` `str` `` or `` `run` ``) can be coincidentally subsumed by an unrelated longer selected identifier. That failure direction is a false *negative* inside a strictly-narrowing filter — a missed gap, never a spurious one — which is the cheap direction for this detector. Do not "tighten" this to boundary matching later without re-examining the `` `["."]` `` case.
- **No tie-break needed.** Unlike `suffix_match_candidates` (which must resolve to a single winner and therefore states an explicit ambiguity rule), subsumption here is existential: containment by *any* `sel_ids` member excludes `r`. A bare key that is a substring of multiple compound selected identifiers is simply excluded — multiplicity is not ambiguity for this rule.
- **One-directional by design.** The reverse shape (a compound literal appearing only in a rejected option, e.g. `` `scope: ["foo"]` `` where the selected option mentions only bare `` `scope:` ``) stays discriminating: the rejected compound names a competing literal value and should still fire.

## Implementation Steps

1. `discriminating = rej_ids - sel_ids` (`issue_parser.py:1580`) must stop counting a bare identifier as discriminating when it is subsumed by a compound identifier already present in `sel_ids` — reproduced by a fixture mirroring the ENH-3292 shape (bare `` `scope:` `` in a rejected option; compound `` `scope: ["."]` ``/`` `scope: ["scripts/"]` `` in the selected option), asserting no `unapplied_decision` gap fires for that pair.
2. The same fixture set must include a negative control: an identifier introduced only by a rejected option, with no containment relationship to anything in `sel_ids`, must still land in `discriminating` and still fire — per the negative-control convention `TestUnappliedDecision` and BUG-3289's test plan both already follow (Integration Map → Tests).
3. Because BUG-3289 (linked, `relates_to`) is an open sibling fix on the identical `discriminating = rej_ids - sel_ids` statement for an orthogonal axis (shared-subject vocabulary), whichever of the two lands second must compose with the other's subtraction rather than replace it — verify both fixture sets pass together if BUG-3289 has landed by implementation time.
4. `python -m pytest scripts/tests/test_issue_parser.py -k UnappliedDecision -v` passes, including `TestUnappliedDecisionLiveCorpusSweep` (crash-only) and `TestBug3293DecisionRulesCorpusDifferential` (pinned corpus regression). Add a new corpus differential at BUG-3289's decided strength (Integration Map → Tests): assert `new_reports == 0` across the live `.issues/` corpus, recording the report-total drop as an observation.
5. Run the live sweep over `.issues/` at implementation time and document the corpus-measured effect (report-total before/after, zero new reports, and which issues lost their spurious gap — ENH-3292 expected among them) in a `# BUG-3295:` comment directly above the containment filter, per the landing convention for this heuristic family (Conventions in Force).

## Impact

- **Priority**: P3 - a fourth recurrence of the still-maturing
  option-locator/decision-identifier heuristic family (alongside BUG-3287,
  BUG-3289, BUG-3293); it produces spurious gaps that cap
  `/ll:confidence-check`'s Ambiguity score rather than causing data loss or
  a crash.
- **Effort**: Small - a single-statement fix (a containment filter added
  ahead of the existing `rej_ids - sel_ids` subtraction) plus fixture and
  corpus tests; Program Design confirms no new data structures are needed.
- **Risk**: Low - strictly narrowing: it can only remove false-positive
  `unapplied_decision` reports, never add new ones, so a passing gate stays
  passing and a failing gate can only start passing (per Integration Map ->
  Dependent Files, FSM `ensure_formatted` note).
- **Breaking Change**: No - an internal refinement to a heuristic gap
  detector's identifier-relationship logic, not a change to any public
  API/CLI contract.

## Root Cause

`scripts/little_loops/issue_parser.py:1379` (`_DECISION_IDENTIFIER_RE`) and
`:1401-1403` (`_decision_identifiers`) extract whole backtick spans as
opaque, unrelated strings. `_unapplied_decision`'s `discriminating = rej_ids
- sel_ids` (`:1580`) then treats a bare key span and a compound literal
containing that key as unrelated identifiers, so a rejected option's
incidental bare-key mention gets promoted to "discriminating" even when the
selected option's own text fully covers that key via a longer literal.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

- Anchor correction, confirmed by direct read of `scripts/little_loops/issue_parser.py`: `discriminating = rej_ids - sel_ids` is at `:1580` (the body's original `:1572` anchors have since been corrected in place; `:1572` resolves to `selected_index = matching[0]`). `sel_ids = _decision_identifiers(block_texts[selected_index])` is at `:1574`; the `rej_ids` union loop is at `:1575-1578`.
- Confirmed absence of containment logic: every callee in `_unapplied_decision`'s call path (`_section_body`, `_option_block_spans`, `_selected_option_title`, `_option_label`, `_heading_bodies`, `_strip_codebase_research_findings`, `_paragraph_spans`) was read in full. None performs substring/prefix/containment comparison between two backtick-span strings. `discriminating = rej_ids - sel_ids` is genuinely a Python `set.__sub__` — exact-string equality only. The only containment-style check anywhere in the function is downstream, at `:1615` (`needle in paragraph`), which checks an already-atomic `discriminating` member against a *paragraph*, not against another identifier — that is the amplification mechanism (one bare key fans out to every narrative mention), not the fix point.

## Scope Boundaries

**In scope**: fixing the identifier-relationship gap in
`_decision_identifiers`/`_unapplied_decision` so a bare key subsumed by a
compound literal in the selected option is not treated as discriminating.

**Out of scope**: a special case for `scope:` or for this specific issue's
wording — that would just be another one-off patch on the same brittle
detector, reproducing the exact pattern this bug exists to stop. Also out of
scope: BUG-3287 and BUG-3293's own (different) invisibility shapes in the
option-locator tier scan — those are separate, already-filed defects in a
different function (`_locate_directive_alternatives` / tier matching, not
`_decision_identifiers`).

## Related Key Documentation

- BUG-3287 — prior false-negative shapes in the same option-locator family
- BUG-3293 — bold-numbered decision points invisible to tier scan/Pattern E
- ENH-3256 — introduced `_unapplied_decision`
- ENH-3292 — where this false positive was discovered during
  `/ll:confidence-check`

## Status

**Open** | Created: 2026-08-22 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-22T22:13:28 - `c3fbea37-7e24-4852-97d2-937535e0fb6c.jsonl`
- `/ll:wire-issue` - 2026-08-22T21:56:32 - `9918c26d-d757-4f35-8afa-285147b946fc.jsonl`
- `/ll:format-issue` - 2026-08-22T21:42:26 - `323559a8-cc72-4bea-b01f-060c73d5598e.jsonl`
- `/ll:refine-issue` - 2026-08-22T21:37:48 - `42953cb7-ca2c-4d42-ad29-2d22ccf37f64.jsonl`
- `/ll:capture-issue` - 2026-08-22T21:27:47 - `1c97624b-6c5a-4655-8896-9cd12a9f503b.jsonl`
