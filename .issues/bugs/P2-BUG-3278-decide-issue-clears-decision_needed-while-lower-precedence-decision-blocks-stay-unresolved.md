---
id: BUG-3278
type: BUG
title: decide-issue clears decision_needed while lower-precedence decision blocks
  stay unresolved
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T15:45:13Z'
labels:
- decide-issue
- skills
- decision-needed
- pipeline
relates_to:
- BUG-3279
- ENH-3280
- ENH-3277
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3278: decide-issue clears decision_needed while lower-precedence decision blocks stay unresolved

## Summary

`/ll:decide-issue` Phase 7b sets `decision_needed: false` unconditionally after annotating a
winner. When an issue contains more than one decision point expressed at *different*
`locate_enumerable_options` precedence tiers, only the highest tier is ever extracted — the
remaining decision blocks are invisible to the skill, yet the file-level flag is cleared as
if every decision were settled. Downstream `/ll:wire-issue`, `/ll:ready-issue`, and
`/ll:manage-issue` then treat the issue as decided.

## Current Behavior

`/ll:decide-issue` Phase 7b (`skills/decide-issue/SKILL.md:411-424`) sets `decision_needed: false`
with only an idempotency guard. Nothing between Phase 3's extraction and Phase 7b's write asks
whether the document still holds an undecided block. Phase 3 returns **at most one** block set —
`locate_enumerable_options` (`issue_parser.py:2134`) resolves exactly one section, then
`_locate_options_in_text` (`:1967`) returns on the **first** `_OPTION_PATTERNS` tier with a match
(`section_header` > `bold_label` > `numbered` > `bullet`, `:1891`). Every other decision point in
the file — whatever tier it is written at, or no tier at all — is invisible to the run that clears
the flag.

Three distinct ways a second decision point survives the pass, all ending in a cleared flag:

1. **Lower tier loses precedence.** A `bullet`-tier `- (a) ...` / `- (b) ...` pair anywhere in the
   resolved section is dropped once `bold_label` fires.
2. **The block matches no tier at all.** The bullet regex (`_OPTION_PATTERNS[3]`) requires the
   `(a)` marker to sit immediately after the dash: `^[-*]\s+(?:\([a-z0-9]\)\s+|\*{0,2}Option\s+…)`.
   A bold-wrapped label — `- **(a) Make the documented override real.**`, the idiomatic shape in
   this repo's issues — matches **zero** of the four tiers (verified). It is not out-competed; it
   is unreachable.
3. **Prose directives are preempted.** The Pattern E heuristic `_locate_directive_alternatives`
   (`:2062`) exists to catch a prose `pick one` / `must be decided` directive with `X or Y`
   alternatives, but `locate_enumerable_options` only reaches it when tiers 1–4 **all** miss
   document-wide. A prose decision directive coexisting with any tier match is never probed.

`locate_unresolved_options` (`:2240`) cannot serve as the missing detector as written: its block
iterator `_iter_option_blocks` / `_OPTION_HEADING_RE` (`:2210-2232`) deliberately recognizes only
Patterns 1–2, so cases 1–3 are all invisible to it too — and to its two consumers,
`ll-issues check-open-questions` and `resolve-decision.yaml`'s `check_open_question_progress`.

**Evidence correction (2026-08-21).** This issue was originally filed against ENH-3277 with quoted
`- **(a) …**` bullets under a literal `**DECISION — pick one before step 4 touches this file:**`
directive at lines 265–278. Neither string exists in any committed revision of that file
(all revisions grepped); ENH-3277's second decision point is **prose**, and it now reads
`**DECIDED — (a), make the documented override real.**`. The live repro is gone and the original
tier attribution was wrong — case 1 was reported, cases 2 and 3 are what that file actually
exhibits. The failure mode is real; only its mechanism is restated here. Reproduce against the
fixture below, never against ENH-3277.

## Steps to Reproduce

Author `scripts/tests/fixtures/issues/BUG-3278-two-decision-points.md` with `decision_needed: true`
and, inside `## Proposed Solution`, both of:

- `**Option A** …` / `**Option B** …` / `**Option C** …` (`bold_label` tier — wins Phase 3 today)
- a second, independent decision point below them, in the shape being tested:
  `- **(a) …**` / `- **(b) …**` (case 2, matches no tier), and/or a prose
  `**DECISION — pick one before step 4:** … X or Y` directive (case 3, Pattern E preempted)

Then:

1. `ll-issues locate-options BUG-3278-two-decision-points --json` → `count 3`, `pattern bold_label`;
   no entry for the second decision point.
2. Run `/ll:decide-issue` on the fixture.
3. Frontmatter reads `decision_needed: false`.
4. The second decision point is untouched and still undecided in the body.

Confirming the tier gap directly (no fixture needed):

```python
from little_loops.issue_parser import _OPTION_PATTERNS
s = "- **(a) Make the documented override real.**"
[i for i, p in enumerate(_OPTION_PATTERNS) if p.search(s)]   # -> []  (no tier matches)
```

## Expected Behavior

`decision_needed` is cleared only when no unresolved decision point remains in the file. If
lower-tier decision blocks survive the pass, the flag stays `true` and the report names which
blocks are still open.

## Motivation

`decision_needed` is the pipeline's gate between refinement and implementation. A falsely-cleared
flag does not surface as an error — it surfaces as `/ll:manage-issue` implementing an issue whose
body still says "pick one before step 4 touches this file". The failure is silent by construction,
and the more thoroughly an issue was refined (multiple decision points, mixed formatting tiers)
the more likely it is to trip.

## Proposed Solution

> **Selected:** Mechanism C — resolved-aware residual probe — Phase 7a's `> **Selected:**` callout
> already marks the decided block, so a resolution-filtered whole-document re-probe needs no span
> arithmetic and is the only candidate that detects all three cases in *Current Behavior*.

**Pinned 2026-08-21.** Widen the existing unresolved-block detector to every tier plus prose
directives, expose it as a deterministic CLI, and gate Phase 7b's write on it. Phase 3 sources its
candidate block from the same detector so repeated runs converge instead of stalling.

Five parts, all required:

1. **`locate_unresolved_options_detailed(content, *, include_approximate_tiers=False) ->
   LocatedOptions`** (`issue_parser.py`, new) — same section precedence as
   `locate_unresolved_options`, returning per-block spans instead of a bare count, filtered by
   `_is_option_resolved` (`:2234`). `locate_unresolved_options` becomes a thin
   `(len(result.options), result.heading)` wrapper, preserving its tuple contract for
   `check_open_questions.py:59` and `resolve-decision.yaml:125-133`.
2. **Tier widening, opt-in.** Under `include_approximate_tiers=True` the block iterator recognizes
   the `numbered` and `bullet` tiers, not only `_OPTION_HEADING_RE`'s Patterns 1–2. The default
   stays `False` so `check-open-questions` and `check_open_question_progress` keep exactly today's
   conservatism — the ENH-2446 comment at `:2225` is a deliberate choice, not an oversight, and
   silently widening it would change loop-gate behavior out of scope.
3. **Bullet-tier regex fix** (`_OPTION_PATTERNS[3]`, `:1896`) — admit a bold-wrapped marker, which
   today matches nothing (case 2). Verified strict superset of current matches:
   ```python
   r"^[-*]\s+\*{0,2}(?:\([a-z0-9]\)\s*|Option\s+[A-Za-z0-9])"
   ```
4. **Residual directive probe.** Call `_locate_directive_alternatives` (`:2062`) *in addition to*
   the tier scan inside the detailed probe, not only as the last-resort fallback it is today
   (case 3). Its existing `_PREFERENCE_MARKER_RE` / `_RESOLVED_QUESTION_MARKER_RE` suppressors
   already make it resolution-aware — confirmed against ENH-3277's decided prose, which correctly
   returns `None`.
5. **New CLI: `ll-issues check-unresolved-options ISSUE-ID [--json]`** — exit 0 when no unresolved
   decision block remains, 1 with `UNRESOLVED_DECISIONS_REMAIN` and the surviving blocks'
   headings/line refs otherwise. Passes `include_approximate_tiers=True`. Deliberately **not**
   `check-open-questions`: that command also counts free-form open questions in
   `## Edge Cases` / `## Confidence Check Notes`, which have nothing to do with whether a decision
   was made — gating the flag on it would pin `decision_needed: true` on any issue with an open
   question and stall every loop that branches on the flag.

Then in the skill:

- **Phase 7b** runs `ll-issues check-unresolved-options` *after* 7a's annotation write. Exit 0 →
  clear as today. Exit 1 → leave `decision_needed: true`, make no frontmatter write, and carry the
  surviving blocks into Phase 9 as
  `⚠ decision_needed remains true — N unresolved decision point(s): <heading:line-range>`.
  This applies Phase 3b-i's existing principle — *"automation cannot clear a flag it did not
  earn"* — to the multi-decision case.
- **Phase 3** selects its candidate block from the same detailed probe rather than from
  `locate_enumerable_options`'s raw winner, so an already-annotated block is skipped. Without this
  the fix is a permanent stall: Phase 7a's idempotency rule ("if a `### Decision Rationale` exists,
  skip the annotation write") means a second run would re-extract the same decided block, decide
  nothing, and re-observe the same residual forever. With it, run 1 decides A/B/C, run 2 decides
  (a)/(b), run 3 finds nothing residual and clears — bounded convergence, one decision per run.

**Rejected alternatives.** *Span-excluding re-scan* (the original proposal): excluding
`options[0].start_line`–`options[-1].end_line` is unusable while BUG-3279 stands — on ENH-3277 the
last option's span runs to line 435 against a section ending near 546, so the exclusion window
swallows the very region the surviving decision lives in. It also detects only case 1. *`--all-tiers`
on `locate-options`*: returns all *matching* tiers, so it misses cases 2 and 3 entirely — the
motivating failure would survive the fix — and it adds a flag shape with no precedent in the CLI
(every existing `--all*` widens *which issues* are processed). Both are dropped; the pin removes
this issue's dependency on BUG-3279.

## Integration Map

### Files to Modify

- `skills/decide-issue/SKILL.md` — Phase 3 sources its candidate from the residual probe; Phase 7b
  gates the clear on `ll-issues check-unresolved-options`; Phase 9 report gains the
  unresolved-decisions line
- `scripts/little_loops/issue_parser.py` — `_OPTION_PATTERNS[3]` widening,
  `locate_unresolved_options_detailed`, opt-in tier/directive coverage in the block iterator
- `scripts/little_loops/cli/issues/check_unresolved_options.py` (new) and `cli/issues/__init__.py`
  — subparser + dispatch. `locate_options.py` is **not** touched: the pinned mechanism adds no
  `--all-tiers` flag
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — `assert_decision_cleared` `on_yes`
  reroute, so a residual decision retries under the existing stall gate instead of failing

### Tests

- An issue fixture with two decision points at different tiers: assert `decision_needed` survives
  as `true` after a `--auto` run
- Single-decision fixture: assert the flag still clears (no regression on the common path)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/fixtures/issues/` — no existing fixture has two unresolved decision points at
  different precedence tiers; `FEAT-2339-mixed-resolved-unresolved.md` is the nearest match but
  both its options are already *resolved* (`> **Selected:**` markers present). A fresh fixture must
  be authored: `## Proposed Solution` with `**Option A**`/`**Option B**`/`**Option C**` (bold_label
  tier, wins today) plus a separate `- **(a) ...**` / `- **(b) ...**` bullet pair under a literal
  `**DECISION — pick one before step X:**` directive (bullet tier, currently unreachable) — the
  shape this issue itself describes, not ENH-3277's live file [Agent 3 finding]
- `scripts/tests/test_issue_parser_unresolved.py` — existing pure-Python coverage
  (`TestLocatedOptionsDataclass`, `TestLocatedOptionsPatternNames`, `TestCountEnumerableOptions`,
  `TestCountUnresolvedOptions`, `TestPatternEDirectiveAlternatives`); any new re-scan helper in
  `issue_parser.py` should get unit tests here following the same `class Test<Concept>` /
  `def test_<scenario>_<expectation>` convention [Agent 3 finding]
- `scripts/tests/test_issues_locate_options.py::TestLocateOptionsJsonFlag` — asserts the exact
  `--json` shape (`{id, count, pattern, heading, options}`); unaffected by the default path but
  unaffected by the pinned mechanism, which leaves `locate-options` alone — no new test class
  needed there [Agent 3 finding, resolved by the 2026-08-21 pin]
- `scripts/tests/test_decide_issue_skill.py::TestDecisionNeededFrontmatterUpdate::test_decision_needed_false_update_documented`
  (line 192) — asserts `"decision_needed: false"` appears in the Phase 7 text slice; the
  conditional re-scan should keep this phrase in the "still clears" branch and add a companion
  assertion for the new "leave true" branch, reusing the phrasing already established by
  `test_decision_needed_not_cleared_on_no_actionable` (line 310: `"decision_needed remains true"`)
  [Agent 3 finding]

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/check_decidable.py:19-52` (`cmd_check_decidable`) — calls
  `locate_enumerable_options` once and only checks `located.count >= 1`; shares Phase 7b's
  single-tier blind spot for the same reason
- `scripts/little_loops/loops/oracles/resolve-decision.yaml`:
  - `check_decision_decidable` state (lines 47-67) shells to `ll-issues check-open-questions ||
    ll-issues check-decidable`, inheriting `check-decidable`'s blind spot directly
  - `check_open_question_progress` state (lines 104-143) sums
    `count_unresolved_options(c) + count_open_questions_in_sections(c)`; `count_unresolved_options`
    wraps `locate_unresolved_options` (`issue_parser.py:2240-2279`), whose block iterator only
    recognizes `section_header`/`bold_label` headings — a `bullet`-tier block is invisible here too
  - `assert_decision_cleared` state (lines 185-204) only re-checks the frontmatter flag via
    `ll-issues check-flag ... decision_needed` after `/ll:decide-issue` runs — it does not
    independently re-run `locate-options`, so it cannot catch this bug's exact failure mode once
    Phase 7b has already cleared the flag incorrectly

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/check_open_questions.py:44-59` (`cmd_check_open_questions`) —
  calls `locate_unresolved_options` directly (not via `check_decidable.py`); inherits the exact
  same `bullet`-tier blind spot already named in this issue's Program Design section, via a second,
  independent call site not currently in this Integration Map [Agent 1 finding, confirmed by read]
- Confirmed FSM gate consumers of the `decision_needed` frontmatter flag — these loops branch to a
  `resolve_decision`-style state when the flag reads `true`, so they are the actual blast radius of
  a falsely-cleared flag (the fix only makes the flag *more* conservative, so no code change is
  implied here — listed for completeness, not as a required edit) [Agent 1 finding]:
  - `scripts/little_loops/loops/rn-remediate.yaml:274-278` (`check_decision_needed`)
  - `scripts/little_loops/loops/autodev.yaml:611-628` (`decide_current`), `:1281-1290`
    (defense-in-depth gate), `:1294-1311` (`triage_outcome_failure`, inline Python check)
  - `scripts/little_loops/loops/recursive-refine.yaml:571-578` (`check_decision_needed`, greps
    `decision_needed: true` directly rather than via `ll-issues check-flag`)
  - `scripts/little_loops/loops/refine-to-ready-issue.yaml:229-243`
    (`check_decision_at_dequeue`), `:583-589` (`check_decision_after_refine`)
  - `scripts/little_loops/loops/auto-refine-and-implement.yaml:229-238`
    (`check_decision_mid_refine`), `:283-290` (`check_decision_mid_wire`), `:588-597`
    (`check_decision_needed`, pre-breakdown)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` § `#### locate_enumerable_options` (lines 987-1022) and
  § `#### count_enumerable_options` (lines 1024-1032) — document the current signature and
  precedence-tier list; the `bullet` tier's documented shape changes with the
  `_OPTION_PATTERNS[3]` widening, and `locate_unresolved_options_detailed` needs a new entry
  [Agent 2 finding]
- `docs/reference/CLI.md` § `#### ll-issues locate-options` (lines 2021-2039) — documents the
  `count`/`pattern`/`heading`/`options` JSON shape, the worked example, and all `pattern` values;
  `locate-options` itself is unchanged under the pin, but the new
  `#### ll-issues check-unresolved-options` section is sited alongside it [Agent 2 finding]
- `docs/reference/COMMANDS.md` § `### /ll:decide-issue` — line 256 states "Sets `decision_needed:
  false` after annotating the winning option" as an unconditional handshake; this line becomes
  false the moment Phase 7b's re-scan ships and must be reworded to state the condition. Line 254's
  "the same call Phase 3 makes" framing also needs a note that Phase 7b now makes its own
  re-scan call [Agent 2 finding]
- `docs/guides/DECISIONS_LOG_GUIDE.md` — the ASCII pipeline diagram (lines 176-190) shows `→ sets
  decision_needed: false` as decide-issue's unconditional terminal step, and line 196 states
  "`decide-issue` clears it after selecting an option" with no condition; both go stale once
  clearing becomes conditional [Agent 2 finding]
- `skills/decide-issue/reference.md` — the Phase 9 Output Report Template (line ~128:
  `- decision_needed: [set to false | already false — no change]`) is exactly what Implementation
  Step 3 says to extend with the unresolved-decisions report line; SKILL.md's own Phase 9 section
  (line 463) defers to this file rather than inlining the template [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- This skill already states the exact principle Phase 7b needs to apply: `skills/decide-issue/SKILL.md:196-217` (Phase 3b-i) refuses to clear `decision_needed` unless the check that justifies clearing it actually ran, with the explicit rationale "automation cannot clear a flag it did not earn" — cited by this issue's own Root Cause section as the precedent Phase 7b violates.
- Frontmatter writes for `decision_needed` in this skill use an inline Edit-tool `---`-block rewrite (`skills/decide-issue/SKILL.md:411-424`, reused verbatim at Phase 3b step 4, `:313-321`) rather than a CLI-mediated write. This is a per-field choice, not a codebase-wide rule: `skills/confidence-check/SKILL.md:387-409` writes its frontmatter fields via `ll-issues set-scores` and explicitly forbids the Edit tool for that field ("the CLI is the single source of truth for score persistence"). Any implementation should keep decide-issue's existing Edit-tool convention rather than introducing a second mechanism for the same field.
- New `ll-issues` subcommand tests in this area reuse a shared `_cli()` / `temp_project_dir` / `_write_issue` / `_invoke` fixture quartet verbatim — evidence: `scripts/tests/test_issues_locate_options.py`, `scripts/tests/test_ll_issues_check_decidable.py`, and `scripts/tests/test_ll_issues_check_open_questions.py` each document in their own docstring which sibling file they mirror.
- `decide-issue` itself is tested structurally, not by live execution: `scripts/tests/test_decide_issue_skill.py` reads `SKILL.md` text and asserts phrases/sections are present, because the skill is LLM-executed with no subprocess entry point. The deterministic Python layer it calls into (`issue_parser.py` functions, exposed via `ll-issues locate-options`/`check-decidable`) gets real subprocess CLI tests instead — a fix here should follow that same split: skill-prose assertions for the `SKILL.md` phase change, subprocess CLI tests for any `issue_parser.py`/`locate-options` change.
- No existing `ll-issues` flag broadens a single-winning-match extraction into "all matches within one document" — the codebase's existing `--all`/`--all-*` flags (`cli/issues/size.py:168`, `cli/issues/epic_consistency.py:278`, `cli/loop/__init__.py:372`, `cli/sync.py:90,111`) all widen *which issues* are processed, not *how many matches* a single resolution returns. An `--all-tiers` flag, if taken, would be new surface, not an extension of an established flag shape.

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- No existing "scan once, consume a match, re-scan the remainder" pattern exists anywhere in the codebase (checked `issue_parser.py` and the broader `scripts/little_loops/` tree) — `locate_enumerable_options` (`issue_parser.py:2134`) and its sibling `_unapplied_decision` (`issue_parser.py:1392`) are both single-pass, winner-take-all [pattern-finder finding]. _Superseded by the 2026-08-21 pin: the selected mechanism uses resolution-marker filtering, not span consumption, so no such pattern is introduced._
- `locate_enumerable_options`/`_unapplied_decision` carry a separately-tracked sibling span-boundary defect: BUG-3279 (`locate_enumerable_options` over-consumes the final option's span to the end of its section) [pattern-finder finding]. _Verified 2026-08-21 on ENH-3277: last option span ends at line 435, section ends near 546 — which is what disqualifies the span-excluding alternative. The pinned mechanism does not read `start_line`/`end_line` for exclusion, so this issue is **not** blocked by BUG-3279; the two fixes stay independent._
- `decide-issue`'s own test file asserts phase-prose conditionals via a bounded phase-text slice (`content.index("## Phase N: ...")` to the next phase heading), never live execution, since the skill is LLM-executed with no subprocess entry point — `scripts/tests/test_decide_issue_skill.py::TestPhase3bResolvedFilter::test_decision_needed_not_cleared_on_no_actionable` (line 310) and `::test_no_file_edit_on_no_actionable` (line 320) are the paired "flag stays true" + "no write happened" assertions a new Phase 7b "leave true" test should mirror in structure [pattern-finder finding].

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- `LocatedOptions` dataclass — `scripts/little_loops/issue_parser.py:1926` — fields `count: int`, `pattern: str | None`, `heading: str | None`, `options: list[LocatedOption]`
- `LocatedOption` dataclass — `scripts/little_loops/issue_parser.py:1908` — fields `label: str`, `text: str`, `start_line: int`, `end_line: int` (both line fields are populated today, computed at `issue_parser.py:1988-1989` and `:2115-2116` — confirms the span-excluding re-scan the Proposed Solution describes is viable against the real return shape without further data-model changes)

### Signatures

- `locate_enumerable_options(content: str) -> LocatedOptions` — `scripts/little_loops/issue_parser.py:2134` — resolves a section (`## Proposed Solution`, then `_OPTION_FALLBACK_SECTIONS` at `issue_parser.py:1900`, then a whole-document H2 sweep, then the Pattern E heuristic `_locate_directive_alternatives` at `:2062`), then hands the section body to:
- `_locate_options_in_text(...)` — `scripts/little_loops/issue_parser.py:1967` — tries `_OPTION_PATTERNS` (`:1891`, precedence `section_header > bold_label > numbered > bullet`, names in `_OPTION_PATTERN_NAMES` at `:1904`) in order and **returns on the first tier with ≥1 match** — this is the exact winner-take-all mechanism the bug is about
- `locate_unresolved_options(content: str) -> tuple[int, str | None]` — `scripts/little_loops/issue_parser.py:2240-2279` — mirrors the same section precedence but its block iterator `_iter_option_blocks`/`_OPTION_HEADING_RE` (`:2210-2232`) only recognizes Patterns 1-2 (`section_header`, `bold_label`) — it does not see `bullet`-tier `(a)/(b)` blocks, so it cannot serve as-is as the "remaining decision point" detector without modification
- `cmd_locate_options` — `scripts/little_loops/cli/issues/locate_options.py:19` — calls `locate_enumerable_options` exactly once; the CLI parser (`scripts/little_loops/cli/issues/__init__.py:733-740`) exposes only positional `issue_id` and `--json` today — no tier-selection flag exists yet, so an `--all-tiers` addition would be new surface, not a widened existing flag

### Call Path

`/ll:decide-issue` Phase 7b (`skills/decide-issue/SKILL.md:411-424`) -> `ll-issues locate-options
ISSUE-ID --json` -> `cmd_locate_options` (`scripts/little_loops/cli/issues/locate_options.py:19`)
-> `locate_enumerable_options` (`scripts/little_loops/issue_parser.py:2134`) ->
`_locate_options_in_text` (`:1967`) -> returns on the first matching `_OPTION_PATTERNS` tier only
-> Phase 7b writes `decision_needed: false` unconditionally, with no re-scan of the remaining
document for a lower-tier block.

### Decision Rules

N/A — no new decision logic; this fix corrects existing frontmatter-clearing logic, it does not introduce a new gap kind, gate, keyword list, or threshold.

## Implementation Steps

The detection mechanism is pinned (Mechanism C, see *Proposed Solution*) — no decision remains.

**Parser layer** (`scripts/little_loops/issue_parser.py`)

1. Widen `_OPTION_PATTERNS[3]` (`:1896`) to `r"^[-*]\s+\*{0,2}(?:\([a-z0-9]\)\s*|Option\s+[A-Za-z0-9])"`.
   Unit-test in `scripts/tests/test_issue_parser_unresolved.py` that `- **(a) …**` now matches
   `bullet` and that every previously-matching shape still matches (strict superset).
2. Add `locate_unresolved_options_detailed(content, *, include_approximate_tiers=False) ->
   LocatedOptions`; reimplement `locate_unresolved_options` (`:2240`) as a
   `(len(options), heading)` wrapper over it. Assert the tuple contract is byte-identical on the
   existing fixtures so `check-open-questions` and `resolve-decision.yaml` are untouched.
3. Under `include_approximate_tiers=True`, extend the block iterator (`_iter_option_blocks` /
   `_OPTION_HEADING_RE`, `:2210-2232`) to the `numbered` and `bullet` tiers, and fold
   `_locate_directive_alternatives` (`:2062`) in as a residual probe. Default `False` must
   reproduce today's counts exactly — that is the regression guard for the ENH-2446 conservatism
   comment at `:2225`.

**CLI layer**

4. Add `scripts/little_loops/cli/issues/check_unresolved_options.py` (`cmd_check_unresolved_options`)
   plus the subparser registration and dispatch entry in `cli/issues/__init__.py` (`:733-740` for
   the parser block, `:1015-1029` for dispatch). Model it on `check_open_questions.py` — exit 0
   clean, exit 1 with an `UNRESOLVED_DECISIONS_REMAIN` stderr token naming each surviving block's
   heading and line range; `--json` emits the `LocatedOptions` shape.
5. Subprocess CLI tests in a new `scripts/tests/test_ll_issues_check_unresolved_options.py`, reusing
   the `_cli()` / `temp_project_dir` / `_write_issue` / `_invoke` fixture quartet that
   `test_issues_locate_options.py` and `test_ll_issues_check_open_questions.py` share verbatim.

**Skill layer** (`skills/decide-issue/`)

6. Phase 3: source the candidate block from the detailed probe rather than
   `locate_enumerable_options`'s raw winner, so already-annotated blocks are skipped and repeated
   runs advance. Without this step the fix stalls the pipeline rather than fixing it.
7. Phase 7b (`SKILL.md:411-424`): run `ll-issues check-unresolved-options` after 7a's annotation;
   clear only on exit 0. On exit 1, make no frontmatter write and leave the flag `true`. Keep the
   literal phrase `decision_needed: false` in the clearing branch —
   `test_decide_issue_skill.py::TestDecisionNeededFrontmatterUpdate::test_decision_needed_false_update_documented`
   (line 192) asserts it — and phrase the new branch as `decision_needed remains true`, matching
   `test_decision_needed_not_cleared_on_no_actionable` (line 310).
8. `reference.md` Phase 9 Output Report Template (line ~128) gains the unresolved-decisions line;
   `SKILL.md`'s Phase 9 (line 463) continues to defer to it.

**Loop integration**

9. `scripts/little_loops/loops/oracles/resolve-decision.yaml` `assert_decision_cleared`
   (`:185-204`): `on_yes` (flag still true) currently routes to `failed`. A legitimately-residual
   decision would now be a hard oracle failure. Route `on_yes` to `check_open_question_progress`
   instead, so the existing progress-gated stall detector re-fires `decide` while the unresolved
   count is falling and fails only when it plateaus. Add an FSM test covering the
   decide-twice-then-clear path.

**Tests**

10. `scripts/tests/fixtures/issues/BUG-3278-two-decision-points.md` — new; the shape in *Steps to
    Reproduce*. `FEAT-2339-mixed-resolved-unresolved.md` is the nearest existing fixture but both
    its options are already resolved, so it cannot exercise this path.
11. Assertions: (a) two-decision fixture leaves `decision_needed: true` after one `--auto` run;
    (b) the same fixture clears after the second run resolves the residual block (convergence, not
    just conservatism); (c) single-decision fixture still clears in one run — no regression on the
    common path; (d) an issue with a settled decision but open free-form questions still clears,
    proving the new probe is narrower than `check-open-questions`.

**Docs**

12. `docs/reference/API.md` — add `locate_unresolved_options_detailed`; note the new
    `_OPTION_PATTERNS` bullet shape under `#### locate_enumerable_options` (lines 987-1022).
13. `docs/reference/CLI.md` — new `#### ll-issues check-unresolved-options` section with the exit
    codes and `--json` shape, sited beside `#### ll-issues locate-options` (lines 2021-2039). No
    change to `locate-options` itself — the pinned mechanism adds no flag there.
14. `docs/reference/COMMANDS.md:256` — "Sets `decision_needed: false` after annotating the winning
    option" becomes conditional; line 254's "the same call Phase 3 makes" framing needs a note that
    Phase 7b now makes its own residual-probe call.
15. `docs/guides/DECISIONS_LOG_GUIDE.md` — the pipeline diagram (lines 176-190) and line 196 both
    present clearing as unconditional and go stale.

**Out of scope** — `check_open_questions.py` and `check_decidable.py` keep today's behavior by
construction (the widening is opt-in, and neither passes the flag). Broadening those probes is a
separate change with its own loop-gate blast radius; file it as a follow-up if wanted.

## Impact

- **Priority**: P2 — silent false-ready into the implementation pipeline, but it needs a
  multi-decision issue to trigger, so it is not a blanket break of the common path
- **Effort**: Medium — parser + new CLI + skill + one loop-oracle edge, per the pinned mechanism
- **Risk**: Medium, not Low. The naive framing ("worst case is a flag left true that a human
  clears") does not hold: `autodev.yaml`, `refine-to-ready-issue.yaml`,
  `auto-refine-and-implement.yaml`, `rn-remediate.yaml`, and `recursive-refine.yaml` all *branch*
  on `decision_needed`, and `resolve-decision.yaml`'s `assert_decision_cleared` treats a still-set
  flag as a hard failure. An over-firing probe converts a silent false-ready into a loop stall.
  Bounded by three things: the tier widening is opt-in (`include_approximate_tiers`), Phase 3 skips
  already-annotated blocks so each run makes progress, and the `assert_decision_cleared` reroute
  puts residual decisions under the existing progress-gated stall detector rather than `failed`
- **Breaking Change**: No

## Root Cause

`skills/decide-issue/SKILL.md` Phase 7b (§ *7b: Update Frontmatter*) performs an unconditional
set-to-`false` with only an idempotency check ("if already `false`, skip the write"). There is no
re-scan for surviving decision points.

The skill already establishes the correct principle elsewhere and simply does not apply it here —
Phase 3b-i refuses to clear the flag in the `NO_ACTIONABLE_DECISIONS` case with the explicit
rationale *"automation cannot clear a flag it did not earn"*. Phase 7b earns the flag for one
decision and clears it for all of them.

## Related Key Documentation

- `skills/decide-issue/SKILL.md` — Phase 3b-i states the "flag it did not earn" principle Phase 7b
  violates
- ENH-3277 — the issue where this was observed

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-21T17:26:19 - `ce6fc8e8-cc01-4d82-ba15-c569a3c2657d.jsonl`
- `/ll:confidence-check` - 2026-08-21T16:52:46 - `91b7dacc-e5dd-41ec-9252-2284552631e6.jsonl`
- `/ll:verify-issues` - 2026-08-21T16:50:38 - `b6e0cd40-ff6f-484a-a070-a4c057b6b4f8.jsonl`
- `/ll:refine-issue` - 2026-08-21T16:48:30 - `fb9d04b2-a23d-41ad-9b4a-d9a452640591.jsonl`
- `/ll:verify-issues` - 2026-08-21T16:45:11 - `71fe2fbf-5037-422a-b792-43cf783f0126.jsonl`
- `/ll:wire-issue` - 2026-08-21T16:42:04 - `e1da28b6-9797-4d9b-9987-730277c774fa.jsonl`
- `/ll:refine-issue` - 2026-08-21T16:33:13 - `dbfc3839-1d83-4abb-b43c-9cdd5a2e4d6a.jsonl`
- `/ll:capture-issue` - 2026-08-21T15:46:43 - `da526826-2179-460f-b823-35695378ac55.jsonl`
