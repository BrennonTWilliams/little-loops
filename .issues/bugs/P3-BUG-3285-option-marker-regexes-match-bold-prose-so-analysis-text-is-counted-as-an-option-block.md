---
id: BUG-3285
type: BUG
title: Option-marker regexes match bold prose, so analysis text is counted as an option
  block
priority: P3
status: open
parent: EPIC-3290
discovered_by: manual-review
discovered_date: '2026-08-21'
captured_at: '2026-08-21T18:55:00Z'
labels:
- issue-parser
- locate-options
- decide-issue
- false-positive
relates_to:
- BUG-3279
- BUG-3278
size: Medium
verify_verdict: VALID
---

# BUG-3285: Option-marker regexes match bold prose, so analysis text is counted as an option block

## Summary

The `bold_label` option marker is matched by prefix only: any line beginning `**Option <X>` is
treated as the start of an enumerable option block, regardless of what follows on that line.
Refinement prose routinely opens lines with `**Option A evidence**:`, `**Option B was already
applied**:`, `**Option A implementation spec**` — commentary *about* an option, not an option — and
every one of those is counted and spanned as if it were a fifth, sixth, seventh option.

## Current Behavior

Two regexes carry the defect independently:

- `_OPTION_PATTERNS[1]` (`scripts/little_loops/issue_parser.py:1893`) —
  `r"^\*\*Option\s+[A-Za-z0-9]+.*?\*\*"`, the `bold_label` tier, backing
  `locate_enumerable_options` → `ll-issues locate-options` / `ll-issues check-decidable`.
- `_OPTION_HEADING_RE` (`:2210`) — `r"^(?:###\s+Option\s+[A-Za-z0-9]|\*\*Option\s+[A-Za-z0-9]+)"`,
  backing `_option_block_spans` → `_unapplied_decision`, and `_iter_option_blocks` →
  `locate_unresolved_options` / `count_unresolved_options` / `ll-issues check-open-questions`.

Neither requires the bold run to *end* after the option identifier, so `**Option A evidence**` is
indistinguishable from `**Option A**` to both.

Live, via the public API (2026-08-21):

```
$ python -c "from little_loops.issue_parser import locate_enumerable_options; ..."
ENH-2967  count=4  pattern=bold_label
  Option A (preferred): a dedicated exit-code check     ← real
  Option B: a derived field on the JSON payload         ← real
  Option A evidence                                     ← prose
  Option B evidence against                             ← prose

BUG-1484  count=4  pattern=bold_label
  Option A                                              ← real
  Option B                                              ← real
  Option A implementation spec                          ← prose
  Option B was already applied                          ← prose
```

Corpus scale: of **362** issues under `.issues/` with ≥2 located options, **31** have a repeated
option letter — the signature of a phantom block, since a genuine option list does not reuse a
letter. (A handful of those 31 are legitimate two-decision issues — FEAT-3078, FEAT-2878 — so 31 is
an upper bound on affected issues, not a count of confirmed phantoms.)

## Steps to Reproduce

1. `python -c "import sys; sys.path.insert(0,'scripts'); from little_loops.issue_parser import
   locate_enumerable_options; import pathlib;
   r=locate_enumerable_options(pathlib.Path('.issues/enhancements/P3-ENH-2967-autodev-redderives-design-fail-predicate-in-three-blocks.md').read_text());
   print(r.count, [o.label for o in r.options])"`
2. Observe `count=4` with two of the four labels being `Option A evidence` / `Option B evidence
   against`.
3. Confirm ENH-2967's `## Proposed Solution` presents exactly **two** options; the other two lines
   are the refinement pass's evidence commentary.

## Expected Behavior

An option marker is a line whose bold run *is* the option — `**Option A**`, `**Option A: <title>**`,
`**Option A (preferred): <title>**`. A line whose bold run continues into commentary about an
option (`**Option A evidence**`, `**Option B was already applied**`) is prose and starts no block.

## Motivation

Three consumers degrade, in increasing order of consequence:

1. **`ll-issues check-decidable` over-counts.** An over-count skips a `/ll:refine-issue` detour that
   would otherwise run — the docstring at `:1885-1890` explicitly accepts approximate matching here,
   so this is the mildest effect and arguably within the stated tolerance.
2. **`/ll:decide-issue` Phase 4 scores phantom options.** Extraction hands the scoring agent a
   block whose "option" is an evidence note, so the agent scores commentary as a candidate.
3. **`ll-issues check-open-questions` reports phantom unresolved options.** A phantom block carries
   no `> **Selected:**` callout, so it counts as unresolved forever. This flips the exit code of the
   first probe in `resolve-decision.yaml`'s gate (`:63`), which can re-enter `decide` on an issue
   that is fully decided.

There is also a measurement interaction with **BUG-3279**: that issue's 151-issue corpus flip is
computed over a block set that includes these phantoms, so its blast-radius numbers partly reflect
this defect rather than the boundary change alone. BUG-3279's Rule 3 (section-scope
`### Decision Rationale`) incidentally neutralizes consequence 3 for decided issues, but does
nothing for consequences 1 and 2 or for undecided issues.

## Proposed Solution

Require the bold run to terminate at the end of the option identifier. Sketch — tighten both
regexes so the closing `**` may be preceded only by an optional title separated by `:` or a
parenthetical qualifier, e.g.

```
\*\*Option\s+[A-Za-z0-9]+(?:\s*\([^)]*\))?(?:\s*[:—-][^*]*)?\*\*
```

The load-bearing change is that `evidence`, `implementation spec`, `was already applied` — bare
words following the identifier with no `:` / `—` separator — no longer match.

**Validate the tightening against the corpus before committing to a pattern.** The two regexes are
matched by a wide range of real formatting in `.issues/`; the acceptance bar is that the 31
repeated-letter issues above lose their phantom blocks while no issue loses a real option. That is
directly measurable — run `locate_enumerable_options` over all of `.issues/` before and after and
diff the label lists.

### Open question — should the two regexes converge?

`_OPTION_PATTERNS[1]` and `_OPTION_HEADING_RE` encode the same intent with different text and are
fixed independently today. BUG-3279 already argues that parallel implementations of one rule are
why its defect recurred after ENH-3256. Worth deciding here whether the bold-marker sub-pattern
becomes a shared module-level constant, following the existing hoisting convention
(`_H3_HEADING_RE` `:1196`, `_OPTION_HEADING_RE` `:2210`, `_DECISION_RATIONALE_HEADING_RE` `:1316`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- Corpus validation of the proposed regex `\*\*Option\s+[A-Za-z0-9]+(?:\s*\([^)]*\))?(?:\s*[:—-][^*]*)?\*\*` against sampled `.issues/*.md` shapes (2026-08-21): `**Option A**`, `**Option A: title**`, and `**Option A (preferred): title**` (e.g. `P3-BUG-2289`, `P3-ENH-2967`) all match, as does an em-dash variant `**Option A (preferred) — use the existing FSM \`config:\` block.**` (`P2-BUG-2767`). Both live false positives cited in this issue — `**Option A evidence**`/`**Option B evidence against**` (`P3-ENH-2967`) and `**Option A implementation spec**`/`**Option B was already applied**` (`BUG-1484`) — are correctly excluded: after the identifier, a bare word with no `(`, `:`, `—`, or `-` immediately following causes the required closing `\*\*` to fail to match. No corpus counter-example (a real marker using a separator other than `:`/`—`/`-`, or nesting a literal `*` before the closing `**`) was found in the sampled files.
- No existing test in `scripts/tests/` exercises a `**Option A evidence**:`-shaped non-match case; all current bold-label test fixtures (`test_issues_locate_options.py:68`, `test_issue_parser_unresolved.py:70,134-135,238,241,286,883,925`, `test_issue_parser.py:70-76`) cover only well-formed accepted markers.

On the Open Question (should the two regexes converge):
- This codebase's existing hoisting convention (`_H3_HEADING_RE` `issue_parser.py:1196`, `_DECISION_RATIONALE_HEADING_RE` `:1316`, `_OPTION_HEADING_RE` `:2281`) is "one regex, one or more call sites" — no existing precedent shows two independently-authored regexes for the same rule converging into one shared sub-pattern constant referenced by both. Converging `_OPTION_PATTERNS[1]` and `_OPTION_HEADING_RE`'s bold-marker sub-pattern would be a new instance of this convention, not an extension of an existing one.
- The one prior regex-tightening precedent in this file, BUG-3279 (`_iter_option_blocks` boundary rule, `issue_parser.py:2293-2299`), landed via a `# BUG-XXXX:` comment above the changed logic, fixture-based unit tests pinning before/after shapes (`test_issue_parser.py:4967-5002`), and a corpus before/after diff run manually and recorded in the issue/commit message — later formalized as an automated sweep (`test_issue_parser.py:5005-5036`, `test_corpus_sweep_does_not_crash` idiom: skips if `.issues/` is absent, asserts only `isinstance(reasons, list)` rather than pinning exact counts).

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- The proposed regex `\*\*Option\s+[A-Za-z0-9]+(?:\s*\([^)]*\))?(?:\s*[:—-][^*]*)?\*\*` was executed (not just traced) against all 8 corpus shapes named in this issue: `**Option A**`, `**Option A: title**`, `**Option A (preferred): title**`, and the em-dash variant all match; `**Option A evidence**:`, `**Option B was already applied**:`, `**Option A implementation spec**`, `**Option B evidence against**` all fail to match. This corroborates the prior pass's corpus-validation finding above with a direct execution rather than sampling.
- A closer shape-precedent than BUG-3279 exists for this exact defect class (a regex over-matching prose that merely *contains* a marker phrase, tightened by adding a positional/structural discriminator rather than being loosened or replaced): BUG-3169's `_OPEN_QUESTION_SIGNAL_RE` (`issue_parser.py:2433-2469`). Its comment documents the same shape of fix — "POSITION plus a declaration boundary, not the mere presence of" the triggering token — with explicit before/after examples of what still counts vs. what's suppressed, and its regression tests (`TestNumberedOpenQuestionCitations`, `test_issue_parser_unresolved.py:485-583`) pair "no longer matches" methods with "still matches" safety-net methods in one test class. BUG-3279 remains the closer precedent for the two-independently-authored-regexes-fixed-together shape, but BUG-3169 is the closer precedent for the bold-prose-over-match shape itself.
- This codebase's convention for landing a narrowing fix in `issue_parser.py` is a `# BUG-NNNN:` comment directly above the changed regex/logic explaining the discriminator added — confirmed at 8+ sites beyond BUG-3279 (`:950` BUG-3059, `:1317-1326` BUG-3279 Rule 3, `:2433-2456` BUG-3169, `:2461-2464` BUG-3169, `:200` BUG-3229, `:237-265` BUG-2806/BUG-2003, `:2475` BUG-3170) — this is a file-wide convention, not specific to the one prior precedent already cited.
- On the Open Question (should the two regexes converge): three more hoisted single-or-multi-call-site module-level regex constants exist beyond `_H3_HEADING_RE`/`_DECISION_RATIONALE_HEADING_RE` already cited — `_SELECTED_CALLOUT_RE` (`:1311`, 4 call sites: `:1341`, `:1487`, `:1505`, `:2338`), `_OPTION_LABEL_RE` (`:1315`, 1 call site `:1347`), `_DECISION_IDENTIFIER_RE` (`:1329`, 1 call site, comment ties it explicitly to "Program Design › Decision Rules, Identifier extraction"). Hoisting in this file is not gated on call-site count — single-call-site and multi-call-site hoisted constants coexist — but the premise still holds: no existing hoisted constant is shared between two independently-matched regex *tuples/sites* the way converging `_OPTION_PATTERNS[1]` and `_OPTION_HEADING_RE`'s bold-marker sub-pattern would require.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `_OPTION_PATTERNS[1]` (`:1893`) and `_OPTION_HEADING_RE`
  (`:2210`)
  > ⚠ Superseded — line numbers stale; see § Codebase Research Findings under Program Design

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/locate_options.py`, `check_decidable.py`,
  `check_open_questions.py` — consume the fixed functions' output; no code change expected
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` (`:63`) — reads only exit codes; no
  code change, but its gate behavior changes on issues that currently carry phantom blocks

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `check_hedges` state (`:374`, `ll-issues
  check-open-questions`) and `check_design` state (`:447`, `ll-issues check-design`) — both gate on
  exit code only; no code change, but gate behavior shifts on issues carrying phantom
  `_OPTION_HEADING_RE` blocks [Agent 1/2 finding]
- `scripts/little_loops/loops/autodev.yaml` — three `ll-issues check-design "$ID"` gate sites
  (`:1267`, `:1273`, `:1799`, `:2026`) — same transitive `_unapplied_decision`/`_OPTION_HEADING_RE`
  dependency via `check_format_gaps`; exit-code only, no code change [Agent 1/2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (`:987-1051`) — describes `locate_enumerable_options`,
  `count_enumerable_options`, `count_unresolved_options` matching semantics; cited examples
  (`**Option A**`, `**Option A: title**`) already close the bold run immediately, so no textual
  edit is required, but verify against the final regex once landed [Agent 2 finding]
- `docs/reference/CLI.md` (`:1943-2047`) — `ll-issues check-decidable` / `locate-options` /
  `check-open-questions` sections describe the same precedence chain; same verify-only status as
  API.md [Agent 2 finding]
- `docs/guides/DECISIONS_LOG_GUIDE.md` (`:198`) — states "The pattern precedence for both CLIs... is
  defined exactly once, in `issue_parser.locate_enumerable_options()`" — this claim depends on both
  `_OPTION_PATTERNS[1]` and `_OPTION_HEADING_RE` being tightened identically (per this issue's Open
  Question); if only one regex is fixed, this doc's "defined once" claim goes stale in spirit
  [Agent 2 finding]
- `docs/reference/COMMANDS.md` (`:254`) — `/ll:decide-issue` "Decidability gate (ENH-2443)" paragraph
  documents the same shared-precedence claim; verify-only, no textual edit expected [Agent 2 finding]
- `skills/decide-issue/SKILL.md` (`:116`, `:164`, `:169`, `:260`, `:286`, `:302`, `:488`) — Phase 3 /
  Phase 3b consume `ll-issues locate-options --json` directly and materialize `**Option A**:
  ...`/`**Option B**: ...` blocks that must re-match `bold_label` on immediate re-scan (step 2); the
  materialized shape already closes the bold run at the identifier, so it is compatible with the
  tightened regex, but this is the one consumption site where a regression would silently break the
  `--auto` decide flow rather than just under-count [Agent 2 finding]
- `commands/refine-issue.md` (`:538-543`) — "Option-Count Detection" rule documents the same bold
  `**Option A**` shape it generates for `decide-issue` to re-parse; verify-only [Agent 2 finding]

### Tests

- A fixture whose Proposed Solution has two real `**Option A/B: …**` markers plus
  `**Option A evidence**:` and `**Option B was already applied**:` prose lines — assert `count == 2`
  and that neither prose line appears as a label
- Preserve the accepted real shapes: `**Option A**`, `**Option A: title**`,
  `**Option A (preferred): title**` — assert each still matches
- A corpus-level guard mirroring the acceptance bar: assert no issue in `.issues/` reports a
  repeated option letter from a single option group

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser_properties.py`, `scripts/tests/test_issue_parser_fuzz.py` —
  property-based and fuzz tests exercising `issue_parser.py` broadly; no `**Option`-shaped fixture
  found in either, but both should be re-run after the tightening since they generate structured
  input the hand-written fixtures don't cover [Agent 3 finding]
- No existing fixture in `scripts/tests/` (including `test_ll_issues_check_open_questions.py`,
  `test_ll_issues_format_check.py`, `test_ll_issues_check_design.py`,
  `test_fold_research_findings.py`, `test_ll_issues_fold_findings.py`, `test_decide_issue_skill.py`,
  `test_refine_issue_command.py`) contains a bare-word-after-identifier bold line — confirmed none of
  these will break [Agent 3 finding]
- A parallel fixture in `test_issue_parser.py`'s `TestUnappliedDecision` class (or
  `test_issue_parser_unresolved.py`) exercising a bold-prose line inside/around an option block via
  `_OPTION_HEADING_RE` — this path is structurally separate from the `locate_enumerable_options`
  tests above even though it encodes the same rule, so needs its own case [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- Current line numbers differ from those cited in this issue (verified 2026-08-21): `_OPTION_PATTERNS[1]` is now at `scripts/little_loops/issue_parser.py:1951` (issue cites `:1893`); `_OPTION_HEADING_RE` is now at `:2281` (cites `:2210`); `LocatedOption`/`LocatedOptions` are at `:1966`/`:1984` (cites `:1907`/`:1925`); `locate_enumerable_options` is at `:2209` (cites `:2134`); `locate_unresolved_options` is at `:2341` (cites `:2249`); `_unapplied_decision` is at `:1449` (cites `:1392`). The regex text and call-path relationships are otherwise unchanged from what the issue describes.
- Additional dependent files not previously listed: `scripts/little_loops/cli/issues/format_check.py` calls `check_format_gaps` directly and backs `ll-issues format-check`. `scripts/little_loops/cli/issues/check_design.py:cmd_check_design` calls `check_format_gaps` (`:38`) as part of the Program Design gate backing `ll-issues check-design` — transitively depends on `_unapplied_decision`/`_OPTION_HEADING_RE` and was not previously named anywhere in this issue.
- `scripts/little_loops/issues/fold_research_findings.py:178` references `count_enumerable_options()` in a docstring describing an invariant that `fold_research_findings` must preserve `**Option A**`/`**Option B**` text verbatim — not a runtime call, but a documented dependency on marker recognition staying stable for well-formed markers.
- `_count_options_in_text` (`issue_parser.py:2006`) also iterates `_OPTION_PATTERNS` in precedence order but has no call sites in the current codebase (dead-but-present); it inherits the tightened tier `[1]` regex automatically with no extra wiring.
- Boundary-span logic (`_option_span_boundary`, `:1381`) is orthogonal to this fix: the tightening changes which lines qualify as marker starts, not how an accepted marker's span ends once matched.

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- Test-fixture convention for a regex-boundary fix: a dedicated test class named after the fix (not the function under test), docstring citing the bug ID, with individual `test_*` methods pairing "no longer matches" cases against at least one "still matches" survivor case so the narrowing can't be shown to over-suppress. Examples: `TestNumberedOpenQuestionCitations` (BUG-3169, `test_issue_parser_unresolved.py:485-583`), `TestLastOptionSpanBoundary` (BUG-3279, `test_issue_parser_unresolved.py:817-930+`).
- `_OPTION_HEADING_RE` has zero test references by name anywhere in `scripts/tests/` (grep-confirmed) — it is exercised only indirectly through `locate_unresolved_options`/`count_unresolved_options`/`_iter_option_blocks`/`_unapplied_decision` call sites. A fixture targeting `_OPTION_HEADING_RE`'s tightening needs its own case via one of those call sites; there is no existing direct-import test to extend.
- The "corpus before/after diff" this issue's Proposed Solution calls for has no existing reusable test helper to run it through: `TestUnappliedDecisionLiveCorpusSweep.test_corpus_sweep_does_not_crash` (`test_issue_parser.py:5005-5036`) is the one corpus-sweep test in this area, and it only asserts `isinstance(reasons, list)` (skips if `.issues/` is absent) — it does not diff match counts before/after a change. The corpus validation this issue's Proposed Solution describes would be a manual, ad hoc step, not an automated gate, matching how BUG-3279's own corpus diff was performed (per that class's docstring narrative, not a checked-in diff script).

## Program Design

### Types

No new or changed types. `LocatedOption` / `LocatedOptions`
(`scripts/little_loops/issue_parser.py:1907`, `:1925`) keep their current fields; only how many
`LocatedOption`s a document yields changes.

### Signatures

No signature changes. The edit is confined to two module-level regex constants:

- `_OPTION_PATTERNS: tuple[re.Pattern[str], ...]` — the four precedence tiers; element `[1]` is the
  `bold_label` tier and is the one tightened (`scripts/little_loops/issue_parser.py:1891-1898`).
- `_OPTION_HEADING_RE: re.Pattern[str]` — the shared `### Option X` / `**Option X` marker used by
  the two span-iterating siblings, whose bold alternative is tightened identically
  (`scripts/little_loops/issue_parser.py:2210`).

Consumers whose behavior shifts without changing shape:

- `locate_enumerable_options(content: str) -> LocatedOptions` — returns a lower `count` on affected
  issues (`scripts/little_loops/issue_parser.py:2134`).
- `locate_unresolved_options(content: str) -> tuple[int, str | None]` — stops counting phantom
  blocks as permanently unresolved (`scripts/little_loops/issue_parser.py:2249`).
- `_unapplied_decision(content: str) -> list[str]` — stops treating evidence prose as a rejected
  option block (`scripts/little_loops/issue_parser.py:1392`).

### Call Path

`_OPTION_PATTERNS[1]` → `_locate_options_in_text` → `locate_enumerable_options` →
`ll-issues locate-options` / `ll-issues check-decidable` / `/ll:decide-issue` Phase 3.

`_OPTION_HEADING_RE` → `_option_block_spans` → `_unapplied_decision` → `ll-issues format-check`;
and `_OPTION_HEADING_RE` → `_iter_option_blocks` → `locate_unresolved_options` →
`count_unresolved_options` → `ll-issues check-open-questions` → `resolve-decision.yaml` gate
(`:63`).

### Decision Rules

One rule, applied identically in both regexes: a bold option marker matches only when the bold run
closes at the end of the option identifier, optionally preceded by a parenthetical qualifier and/or
a separator-introduced title (`:` / `—` / `-`). A bold run continuing into bare words after the
identifier is prose and starts no block. No new gate, threshold, or keyword list.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- Every anchor cited in this section's own prose (`:1907`, `:1925`, `:1891-1898`, `:2210`, `:2134`, `:2249`, `:1392`) is stale — confirmed unchanged since the prior pass's line-drift finding (filed under Integration Map → Tests, not here): `LocatedOption` is now at `issue_parser.py:1966`, `LocatedOptions` at `:1984`, `_OPTION_PATTERNS` (all 4 tiers) at `:1949-1956` with tier `[1]` (`bold_label`) at `:1951`, `_OPTION_HEADING_RE` at `:2281`, `locate_enumerable_options` at `:2209`, `locate_unresolved_options` at `:2341`, `_unapplied_decision` at `:1449`. No further drift since that pass — this finding only corrects that the prior pass's numbers were never propagated into this section's own text.
- `_unapplied_decision` (`issue_parser.py:1449-1572`) has a fourth degradation path not listed above: a comment the BUG-3279 fix left in place (`issue_parser.py:1469-1475`, commit `f39a417e`) states verbatim that `dr_start` is retained as a second consumer, `scrub_start = min(dr_start, spans[-1][1])`, "the cap on the Proposed Solution self-scan, which still needs it for the phantom-trailing-block case tracked separately as BUG-3285." A bold-prose false positive (e.g. `**Option A evidence**:` appearing after the real options) is matched by `_OPTION_HEADING_RE` and becomes a new trailing entry in `_option_block_spans`'s `spans` list, so `spans[-1]` — used both for the trailing-callout trim (`:1486-1490`) and for `scrub_start` (`:1538`) — resolves to the phantom block instead of the true last real option. This is the same root cause as the other three consumers in `## Motivation`, reached through `_OPTION_HEADING_RE` rather than `_OPTION_PATTERNS[1]`, and the comment's own cross-reference confirms this bug (BUG-3285) is the tracked fix for it.

## Sequencing

Independent of **BUG-3279** — different regexes, different failure mode — but landing this **first**
makes BUG-3279's corpus regression check readable, since its before/after counts stop moving for
phantom-block reasons. Not a hard dependency in either direction.

## Impact

- **Priority**: P3 — real false positives with a live path to re-deciding decided issues, but the
  most consequential effect (consequence 3) is partially masked today by BUG-3279's absorption bug
  and would be further masked by that issue's Rule 3
- **Effort**: Medium — two regexes and a corpus validation pass; the work is in proving the
  tightening doesn't drop real options, not in writing it
- **Risk**: Medium — over-tightening silently drops genuine options, which is worse than the current
  over-count. The corpus before/after diff is the control
- **Breaking Change**: No — `count` falls on affected issues; no output shape changes

## Root Cause

Both option-marker regexes anchor on a prefix (`**Option <X>`) and never constrain what follows
before the closing `**`, so bold *commentary about* an option is structurally identical to an option
marker.

## Status

**Open** | Created: 2026-08-21 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-21T19:38:51 - `7a16a3a6-404c-4906-af8c-04f2c6a84451.jsonl`
- `/ll:verify-issues` - 2026-08-21T19:30:24 - `bd2411ca-ba9b-4390-bc28-a400fd2e7ad1.jsonl`
- `/ll:wire-issue` - 2026-08-21T19:27:19 - `eae61f16-add8-4659-bd44-04cb88cf7241.jsonl`
- `/ll:refine-issue` - 2026-08-21T19:21:07 - `bc62da4a-c398-499d-b656-61818f561aff.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T19:06:56 - `8c9f6596-f570-42d1-a2a2-c4e750b706f8.jsonl`
