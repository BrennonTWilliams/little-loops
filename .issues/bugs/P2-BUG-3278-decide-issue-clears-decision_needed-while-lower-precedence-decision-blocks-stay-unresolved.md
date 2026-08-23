---
id: BUG-3278
type: BUG
title: decide-issue clears decision_needed while lower-precedence decision blocks
  stay unresolved
priority: P2
status: done
parent: EPIC-3290
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T15:45:13Z'
completed_at: '2026-08-23T03:55:32Z'
labels:
- decide-issue
- skills
- decision-needed
- pipeline
relates_to:
- BUG-3279
- BUG-3287
- ENH-3280
- ENH-3277
- BUG-3285
verify_verdict: VALID
size: Large
confidence_score: 90
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3278: decide-issue clears decision_needed while lower-precedence decision blocks stay unresolved

## Summary

`/ll:decide-issue` Phase 7b sets `decision_needed: false` unconditionally after annotating a
winner. When an issue contains more than one decision point, only the highest-precedence one is
ever extracted — the remaining decision blocks are invisible to the skill, yet the file-level flag
is cleared as if every decision were settled. Downstream `/ll:wire-issue`, `/ll:ready-issue`, and
`/ll:manage-issue` then treat the issue as decided.

The fix introduces a **decision group** model — one group per decision point, resolved as a unit —
and gates Phase 7b's clear on a residual-group probe.

## Current Behavior

`/ll:decide-issue` Phase 7b (`skills/decide-issue/SKILL.md:411-424`) sets `decision_needed: false`
with only an idempotency guard. Nothing between Phase 3's extraction and Phase 7b's write asks
whether the document still holds an undecided block. Phase 3 returns **at most one** block set —
`locate_enumerable_options` (`issue_parser.py:2209`) resolves exactly one section, then
`_locate_options_in_text` (`:2025`) returns on the **first** `_OPTION_PATTERNS` tier with a match
(`section_header` > `bold_label` > `numbered` > `bullet`, `:1949`). Every other decision point in
the file is invisible to the run that clears the flag.

**Phase 7b is not the only clearing site.** Phase 3b's lock-in path (`SKILL.md:313-321`) performs an
*independent* unconditional `decision_needed: false` write with its own inline `---` Edit, and its
step 6 then **skips Phases 4–7 entirely** — so on that path Phase 7b never runs at all. That is the
`AUTO_MODE`-only path taken by `ll-auto` / `autodev` / `resolve-decision.yaml`, i.e. the one most
likely to meet a multi-decision issue unattended. `docs/reference/COMMANDS.md:256` documents both
writes in a single "Frontmatter write-back" paragraph. Gating only Phase 7b leaves the defect fully
intact on the automated path; part 5 therefore gates **both** sites.

Three ways a second decision point survives the pass, all ending in a cleared flag:

1. **Lower tier loses precedence.** A `bullet`-tier `- (a) …` / `- (b) …` pair anywhere in the
   resolved section is dropped once `bold_label` fires. **This issue fixes case 1.**
2. **The block matches no tier at all.** `- **(a) Make the documented override real.**` — the
   idiomatic shape in this repo's issues — used to match **zero** of the four tiers.
   **Already fixed by BUG-3287 (landed `e16a0bd83`), re-measured 2026-08-23:** `_OPTION_PATTERNS[3]`
   is now `^[-*]\s+\*{0,2}(?:\([a-z0-9]\)\s*|Option\s+[A-Za-z0-9])`, and that shape returns
   <!-- ll-evidence-ok: re-measured function return value from running the fixed code, not a quote from BUG-3287's issue body -->
   `count 2, pattern bullet`. This issue's group iterator picks case 2 up at the `bullet` tier under
   `include_approximate_tiers=True` with no extra work. The only consequence left for this issue is
   fixture choice — use the bold-wrapped `- **(a) …**` shape, per the note under *Steps to
   Reproduce*.
3. **Prose directives are preempted.** `_locate_directive_alternatives` exists to catch a prose
   `pick one` / `must be decided` directive. In the shared chain this is **already fixed by
   BUG-3287**: `locate_enumerable_options` now runs the directive probe *alongside* every tier win
   and attaches the result as `LocatedOptions.residual_directive` rather than reaching it only when
   tiers 1–4 all miss (re-measured 2026-08-23 — a document with `**Option A/B**` plus a `pick one`
   directive returns
   <!-- ll-evidence-ok: re-measured function return value from running the fixed code, not a quote from BUG-3287's issue body -->
   `2, bold_label, residual_directive=provisional_e`). This issue's group
   iterator therefore does **not** need its own second call path: it reads `residual_directive`
   off the existing result. See part 3.

`locate_unresolved_options` (`:2341`) cannot serve as the missing detector as written: its block
iterator `_iter_option_blocks` / `_OPTION_HEADING_RE` (`:2281-2326`) deliberately recognizes only
Patterns 1–2, so cases 1–3 are invisible to it and to its two consumers,
`ll-issues check-open-questions` and `resolve-decision.yaml`'s `check_open_question_progress`.

**Evidence correction (2026-08-21).** This issue was originally filed against ENH-3277 with quoted
`- **(a) …**` bullets under a literal `**DECISION — pick one before step 4 touches this file:**`
directive at lines 265–278. Neither string exists in any committed revision of that file
(all revisions grepped); ENH-3277's second decision point is **prose**, and it now reads
`**DECIDED — (a), make the documented override real.**`. The live repro is gone and the original
tier attribution was wrong. The failure mode is real; only its mechanism is restated here.
Reproduce against the fixtures below, never against ENH-3277.

## Steps to Reproduce

Author `scripts/tests/fixtures/issues/BUG-3278-two-decision-points.md` with `decision_needed: true`
and, inside a single `## Proposed Solution`, both of:

- `**Option A** …` / `**Option B** …` / `**Option C** …` (`bold_label` tier — wins Phase 3 today)
- a second, independent decision point below them: `- **(a) …**` / `- **(b) …**` (`bullet` tier,
  case 1)

The co-location in one section is the point, not incidental — it is what exercises the single-group
restriction in part 1.

**Use the bold-wrapped `- **(a) …**` shape, not the bare `- (a) …` (revised 2026-08-23).** Round 4
downgraded this fixture to the bare form because the bold-wrapped shape was unreachable until
BUG-3287 landed. It has landed; both shapes now return `bullet`, and the bold-wrapped one is this
repo's idiomatic shape and the more valuable regression pin (it is the one that regressed).

Re-verified against the current tree (2026-08-23): the repro still holds exactly — step 1 returns
`count 3`, `pattern bold_label`, `residual_directive: null`, with no entry for the second decision
point. BUG-3287's `residual_directive` does not rescue this case, because the second decision point
is a tier match, not a prose directive.

Then:

1. `ll-issues locate-options BUG-3278-two-decision-points --json` → `count 3`, `pattern bold_label`;
   no entry for the second decision point.
2. Run `/ll:decide-issue` on the fixture.
3. Frontmatter reads `decision_needed: false`.
4. The second decision point is untouched and still undecided in the body.

## Expected Behavior

`decision_needed` is cleared only when no unresolved decision point remains in the file. If
lower-tier decision groups survive the pass, the flag stays `true` and the report names which
groups are still open.

## Motivation

`decision_needed` is the pipeline's gate between refinement and implementation. A falsely-cleared
flag does not surface as an error — it surfaces as `/ll:manage-issue` implementing an issue whose
body still says "pick one before step 4 touches this file". The failure is silent by construction,
and the more thoroughly an issue was refined (multiple decision points, mixed formatting tiers) the
more likely it is to trip.

## Proposed Solution

> **Selected:** Mechanism C — resolved-aware residual probe. Phase 7a's `> **Selected:**` callout
> already marks the decided block, so a resolution-filtered whole-document re-probe needs no span
> arithmetic and is the only candidate that detects the surviving cases in *Current Behavior*.

Widen the unresolved-decision detector to a **decision-group** model, expose it as a deterministic
CLI, and gate Phase 7b's write on it. Phase 3 sources its candidate group from the same detector so
repeated runs converge instead of stalling.

The unit of resolution is the **decision group**, not the option block. Phase 7a marks only the
*winning* option with `> **Selected:**`, so a per-block gate would read every loser as unresolved
and refuse to clear a correctly-decided single-decision issue — converting a silent false-ready
into a permanent stall on the common path. Group-aware resolution is the load-bearing part of this
fix, not an implementation detail.

### Part 1 — decision groups (`issue_parser.py`, new)

A *decision group* is one decision point: a maximal contiguous run of option blocks at the same
tier, or one Pattern E directive window.

- `DecisionGroup` dataclass — `heading: str | None`, `tier: str`, `options: list[LocatedOption]`,
  `start_line: int`, `end_line: int`
- `_iter_decision_groups(content, *, include_approximate_tiers=False) -> list[DecisionGroup]`
- `is_group_resolved(content, group) -> bool` — True when **any** member block carries a
  `> **Selected:**` callout, **or** the group's enclosing section carries a
  `### Decision Rationale` subsection **and that section holds exactly one decision group**.

> ⚠ **This contract does not cover `provisional_e` groups, and must say so (added 2026-08-21,
> epic review).** A directive group is retired by **suppressing the probe**, never by satisfying
> `is_group_resolved` — see part 5's marker-placement rule and its measurement. Written as an
> unqualified rule, the definition above tells an implementer to make a directive group resolvable
> by callout, which is not achievable: `_SELECTED_CALLOUT_RE` (`issue_parser.py:1361`) is
> **line-anchored** (`^\s*>\s+\*\*Selected:\*\*`), and the only marker placement that suppresses
> the directive is one appended to the directive line itself, which that regex cannot match.
> State the carve-out in the docstring: *tier groups resolve via marker or single-group section
> fallback; `provisional_e` groups are never emitted once marked, so `is_group_resolved` is never
> consulted for them.*

**The single-group restriction is load-bearing.** An unrestricted section-level check reproduces
this very bug through the fix: on the step-10 fixture both groups live under `## Proposed
Solution`, so run 1 deciding group A appends a `### Decision Rationale` to that section, group B
immediately reads resolved by side effect, the residual probe exits 0, and Phase 7b clears the
flag. Multi-group sections must resolve **per group, via a marker inside the group's own span**;
the section-level fallback exists only for markerless legacy shapes (like this issue's own file,
whose `> **Selected:**` sits at the top of `## Proposed Solution`, attached to no option block,
with no competing group) and must never fire when a section carries two or more groups.

**Do not reuse BUG-3279's `_DECISION_RATIONALE_SECTION_MARKER_RE` semantics.** That fix (landed
2026-08-21 as `f39a417e`) adds a section-scope resolution rule to `locate_unresolved_options` — *"a section containing a
`### Decision Rationale` heading anywhere counts every option block in that section as resolved"* —
and its own docstring names the tradeoff: *"a section with two independent option groups where only
one is decided reports fully resolved … corpus-measured as 0 live false negatives at fix time,
mitigated only by a pinned regression fixture, not narrowed scope."* That is precisely this issue's
failure mode, knowingly accepted at the per-block layer. It is acceptable there (that counter feeds
`check-open-questions` and the loop stall gate, both of which err conservative), and unacceptable
here, because `is_group_resolved` gates the flag itself. The regex may be reused as a *heading
matcher*; the unrestricted section-wide semantics must not be. Assertion (c2) is the guard.

The regex to reuse is `_DECISION_RATIONALE_SECTION_MARKER_RE` (`issue_parser.py:1326`,
`r"^\s*###\s+Decision Rationale\b"` — lenient, so decorated headings still match). Note that
`f39a417e` **deleted `_RESOLVED_OPTION_MARKER_RE` entirely** and reduced `_is_option_resolved`
(`:2328`) to a `> **Selected:**` callout test; any earlier reference in this document to that
constant is stale.

**Grouping rules.** A run breaks when the tier changes, when a Pattern E directive window
intervenes, or at a section boundary. Two same-tier runs separated by a `**DECISION — pick one:**`
directive are two groups; `**Option A/B/C**` followed by `- (a)/(b)` are two groups because the
tier differs.

**Span rule.** A `> **Selected:**` callout line, and the `### Decision Rationale` heading Phase 7a
writes, are *resolution markers*, not group terminators. The callout sits inside the group whose
option it marks and must not split that group in two; the `### Decision Rationale` H3 does
terminate the preceding group's span. Without this rule Phase 7a's own annotation write splits
group B on the next run.

### Part 2 — `locate_unresolved_decisions(content, *, include_approximate_tiers=False) -> list[DecisionGroup]`

Same section precedence as `locate_unresolved_options`, returning the part-1 groups that fail
`is_group_resolved`. Returns groups, **not** a flat `LocatedOptions` — that shape cannot express
"which decision point", only "which block", and the distinction is exactly what part 1 exists to
make.

`locate_unresolved_options` keeps its current per-block implementation and tuple contract
**unchanged** for `check_open_questions.py:59` and `resolve-decision.yaml:125-133`. It is not
reimplemented as a wrapper over the new function, because the two now count different things —
collapsing them would silently change the loop-gate counter.

### Part 3 — tier and directive widening, opt-in

Under `include_approximate_tiers=True` the group iterator recognizes the `numbered` and `bullet`
tiers, not only `_OPTION_HEADING_RE`'s Patterns 1–2, and probes the Pattern E directive **in
addition to** the tier scan rather than as a last-resort fallback (case 3). The default stays
`False` so `check-open-questions` and `check_open_question_progress` keep exactly today's
conservatism — the ENH-2446 comment is a deliberate choice, and silently widening it would change
loop-gate behavior out of scope.

**Source the directive from `LocatedOptions.residual_directive`, not a second call (revised
2026-08-23).** BUG-3287 already made `locate_enumerable_options` run `_locate_directive_alternatives`
alongside every tier win and attach the result as `residual_directive` (verified: `2, bold_label,
residual_directive=provisional_e`). Building a parallel `_locate_directive_alternatives` call inside
the group iterator would duplicate a probe the shared chain already performs, and the two could
drift. Read the existing field.

**At most one Pattern E group is detectable per document, and this is a hard limit of the existing
function.** `_locate_directive_alternatives` `return`s from inside its scan loop on the **first**
matching window, iterating `_DIRECTIVE_ALTERNATIVES_SECTIONS` in a fixed order — a **5-entry** list
since BUG-3293 added `Program Design`: `Scope Boundaries`, `Proposed Change`, `Proposed Solution`,
`Open Questions`, `Program Design`. Consequences the group model cannot paper over:

- two independent prose directives in the same section collapse into a single `provisional_e` group
- a directive in `Proposed Solution` masks one in `Open Questions` entirely
- a directive in any section outside that 5-entry list is invisible

So part 1's *"one group per decision point"* contract holds for the four tier-based shapes but is
**best-effort for Pattern E**.

> **Selected:** accept the limitation. The group iterator emits **at most one `provisional_e`
> group** per document. It still strictly improves on today (Pattern E is currently unreachable
> whenever any tier matches), and the alternative — refactoring
> `_locate_directive_alternatives`' scan loop to yield every non-overlapping window — is a change to
> the shared precedence chain that `check-decidable` and `locate_enumerable_options` also traverse,
> which is BUG-3287's blast radius, not this issue's.

The limitation must be **stated, not left implicit** — silently shipping the group model with a
Pattern E path that cannot express two decision points is how this issue's own failure mode returns.
Document it in `locate_unresolved_decisions`' docstring and in the CLI reference (steps 14–15).
Accepted residual risk: a second prose directive in the same document stays invisible and the flag
clears.

The rejected alternative, recorded for the follow-up: **`_iter_directive_alternatives(content) ->
list[LocatedOptions]`** — refactor the scan loop to yield every non-overlapping matching window
instead of returning the first, and reimplement `_locate_directive_alternatives` as
`next(iter(...), None)` so its existing callers (`locate_enumerable_options`'s last-resort path,
`check-decidable`) stay bit-identical. Delivers the stated contract; file as a follow-up on BUG-3287
if a second-directive case is ever observed live.

**The suppressors are per-window, not per-document — this is load-bearing for part 5.** Re-measured
against live `_locate_directive_alternatives` (**2026-08-23**), with the directive on line `D`:

| Marker placement | Result |
| --- | --- |
| `> **Selected:**` on the line **after** `D` | **still matches** `provisional_e`; the returned window does not contain the callout |
| `> **Selected:**` on the line **before** `D` | **still matches**; window does not contain the callout |
| directive reworded to `**DECIDED — (a); was: pick one …**` | **still matches** (`pick one` survives; there is no `DECIDED` alternative in `_RESOLVED_QUESTION_MARKER_RE`) |
| `**RESOLVED — the shim.**` prefixed to line `D` | **still matches** — ✗ **the form Rounds 5–6 prescribed does not work**; see below |
| `**RESOLVED:** the shim.` prefixed to line `D` | **still matches** ✗ |
| `> **Selected:**` appended **to line `D` itself** | `None` ✓ |
| `**RESOLVED**` prefixed **to line `D` itself** | `None` ✓ |
| `**RESOLVED** — the shim.` prefixed **to line `D` itself** | `None` ✓ ← **prescribed form** |

> ⚠ **Correction, round 7 (2026-08-23) — the bold run must close at `RESOLVED`.**
> `_RESOLVED_QUESTION_MARKER_RE` is
> `(?:✅|✔)\s*RESOLVED|>\s*\*\*RESOLVED\*\*|\*\*RESOLVED\*\*` — every alternative requires
> `RESOLVED` to be immediately followed by the closing `**`. Round 6 generalized from the bare
> `**RESOLVED**` row to a *decorated* `**RESOLVED — the shim.**`, which puts the em-dash and reason
> **inside** the bold run and therefore matches nothing. Measured: it is **not** suppressed. Shipping
> that form makes a `provisional_e` group unretirable — it re-emits on every run, the probe exits 1
> forever, and `decision_needed` can never clear. That is the permanent stall Round 6 §1 existed to
> prevent, reintroduced by the wording of its own fix.
>
> **Correct form: `**RESOLVED** — the shim.`** — bold closes at `RESOLVED`, reason follows outside
> it. Verified `None`.
>
> **Also correct the record on the two suppressing rows.** The appended `> **Selected:**` form
> *does* suppress (via `_PREFERENCE_MARKER_RE`'s `>\s*\*\*selected:\*\*` — windows are
> whitespace-normalized before matching, so a mid-line `>` still matches). Round 6's *reasons* for
> rejecting it stand and still decide the choice: it does not match `_SELECTED_CALLOUT_RE`
> (line-anchored — verified non-matching), so no callout consumer can see it, and a mid-line `>` is
> not valid blockquote syntax. The prefix form is prescribed on those grounds, not because the
> appended form fails to suppress.

The mechanism: the scan slides a window `lines[max(0, i-3) : min(len, i+4)]` over every `i` and
suppresses only the windows that contain a marker. A marker on a *neighbouring* line always leaves
at least one window (`i = D-3`, spanning `D-6..D`) that holds the imperative but not the marker, so
the match survives — and because that surviving window is the first match, its span excludes the
marker too, so a span-scoped `is_group_resolved` check fails as well. **Only a marker on the
directive line itself is contained by every window that contains the imperative.** Part 5's
placement rule is written against this measurement.

Note also that ENH-3277's decided prose does correctly return `None`, but *not* because `DECIDED`
is recognized — it dropped the `pick one` imperative outright. Do not generalize from it.

**The group iterator must compute its own block boundaries** rather than reusing
`_iter_option_blocks`: that iterator returns `(heading_line, block_body)` **strings with no
offsets**, so it cannot populate `DecisionGroup.start_line`/`end_line`. It should, however, **reuse
`_option_span_boundary`** — BUG-3279's shared, fence-aware boundary helper — rather than
reimplementing the rule, so all three span consumers stay consistent. `_iter_option_blocks` itself
stays as-is for its existing per-block callers.

That helper is **not** a one-argument convenience wrapper; its landed signature
(`issue_parser.py:1381`) is

```python
_option_span_boundary(
    text: str, search_start: int, max_depth: int, fences: list[tuple[int, int]]
) -> int | None
```

so the group iterator computes `fence_spans(text)` itself (function-local import from
`little_loops.text_utils`, per the file's existing convention) and selects `max_depth` per match —
**3** for a heading-shaped marker (`### Option X`, whose own `####` children must not cut the span)
and **6** otherwise. It returns the offset of the first fence-excluded qualifying heading at or after
`search_start`, or `None`. Callers combine it with the next-marker and end-of-text candidates via
`min(...)`.

**Boundary correctness is no longer the reason** (revised, round 4). Earlier revisions justified a
bespoke iterator on the grounds that `_iter_option_blocks`' final block ran to end-of-section and
swallowed the trailing `### Decision Rationale`. BUG-3279 (landed `f39a417e`) resolves that: each block
now ends at the next same-tier marker, the first qualifying fence-excluded heading, or the section
end, whichever comes first. The round-2 empirical claim that a decided three-option section reports
`1` unresolved rather than `2` no longer reproduces — under the BUG-3279 tree it reports `0`, for
the different reason in the note below. Offsets are the surviving justification.

### Part 4 — new CLI: `ll-issues check-unresolved-decisions ISSUE-ID [--json]`

- **exit 0** — no unresolved decision group remains
- **exit 1** — `UNRESOLVED_DECISIONS_REMAIN` on stderr, naming each surviving group's heading and
  line range
- **exit 2** — the issue ID does not resolve

Passes `include_approximate_tiers=True`.

Exit 2 for an unresolvable ID is required by the FSM `exit_code` evaluator's mapping — 0→`on_yes`,
1→`on_no`, 2+→`on_error` (`fsm/evaluators.py:255-259`) — because reusing 1 for "not found" would
make an unresolvable ID indistinguishable from a genuine residual and route it to `done` (part 6).
The command must also never exit **3** — `shell_exit` does not set `abstain_on_exit_3`, so 3 would
land on `on_error`.

**This is no longer a divergence (corrected 2026-08-23).** Earlier revisions framed exit 2 as a
deliberate departure from `check_open_questions.py`, which returned 1 for a missing issue. BUG-3294
landed (`cd57acab5`) and that command now returns 2 as well (confirmed at
`check_open_questions.py:56`), as does `check_decidable.py`. All three probes agree; do not repeat
the "divergence" framing in the CLI reference (step 15) — document exit 2 as the house convention.

`--json` emits `{"id", "unresolved": [DecisionGroup...]}`. Each group serializes `heading`, `tier`,
`start_line`, `end_line`, and its member options as **full `LocatedOption` dicts** (`label`, `text`,
`start_line`, `end_line` — `LocatedOption.to_dict()` already exists at `issue_parser.py:1974`).

It is **not** a drop-in substitute for `locate-options --json`: that payload carries `count` and
`pattern` at the top level, whereas these move *into* each group as `len(options)` and `tier`. Every
Phase 3 read must be re-pointed accordingly — Phase 4 still scores options from their `text`, and
Phase 3's Option Count Check still branches on the bullet tier, but now via the selected group's
`tier` rather than a document-level `pattern` (`SKILL.md:183`).

A group's `tier` uses the `_OPTION_PATTERN_NAMES` vocabulary
(`section_header`/`bold_label`/`numbered`/`bullet`) extended with `provisional_e` for a Pattern E
window **and `decision_rules_numbered` for a BUG-3293 Program Design block** (see the next
subsection); `_OPTION_PATTERN_NAMES` is a 4-tuple today and the other two are bare literals inside
`_locate_directive_alternatives` / `_locate_decision_rules_numbered`, so either extend the tuple or
document `tier` as a **6-value** union. Earlier revisions said 5 — that predates BUG-3293.

Deliberately **not** `check-open-questions`: that command also counts free-form open questions in
`## Edge Cases` / `## Confidence Check Notes`, which have nothing to do with whether a decision was
made — gating the flag on it would pin `decision_needed: true` on any issue with an open question
and stall every loop that branches on the flag.

### Part 4b — `decision_rules_numbered` is outside the group model, and that creates a new unearned clear (added 2026-08-23, round 7)

BUG-3293 added a sixth detection path, `_locate_decision_rules_numbered` — bold-numbered items under
`## Program Design` → `### Decision Rules`, reported as `pattern="decision_rules_numbered"`. It is
reachable from `locate_enumerable_options` and therefore from `check-decidable`, but it is **not** a
`_OPTION_PATTERNS` tier and **not** visible to `_OPTION_HEADING_RE` / `locate_unresolved_options`.
The group model as specified in parts 1–4 cannot see it either. Measured 2026-08-23 on a document
whose only decision surface is such a block:

| Probe | Result |
| --- | --- |
| `check-decidable` (`locate_enumerable_options`) | **exit 0** — `count 2`, `pattern decision_rules_numbered` |
| `locate_unresolved_options` | `(0, None)` |
| `check-unresolved-decisions` (this issue, as specified) | would report **zero groups → exit 0** |

Part 5's new Phase 2.5→3 handoff rule — *"zero unresolved groups with `decision_needed: true` falls
through to Phase 7b, which exits 0 and clears the flag"* — then fires. Phase 2.5 passed, Phase 3
found nothing, and the flag clears **with no option scored and no annotation written**. That is a
new instance of this issue's own failure mode, introduced by the fix, and it is strictly worse than
today: today Phase 3 sources `decision_rules_numbered` options from `locate-options`, routes them to
Phase 4 scoring, and at least *makes* a decision before clearing.

> **Selected:** do **not** emit `decision_rules_numbered` groups; narrow the Phase 3 fall-through
> instead.

**Why not emit them as groups.** Decision Rules items are not mutually exclusive alternatives — they
are the issue's own settled design rulings (`1. **Identifier shape.** …` / `2. **Title extent.** …`),
and "pick one" is meaningless over them. Emitting them as a decision group would make
`check-unresolved-decisions` exit 1 on essentially every refined issue in this repo, since none of
them carry a `> **Selected:**` callout on a Decision Rules item — a mass loop stall, and exactly the
over-firing hazard *Impact → Risk* names. BUG-3293's own comment already frames this probe as an
over-count-tolerant *pre-check*, not a decision surface.

**The narrowing.** Phase 3's zero-group fall-through clears only when the group probe reports zero
groups **and** the Phase 2.5 `locate-options` result is not a tier the group model declines to
model. Concretely: if `check-unresolved-decisions` returns zero groups but `locate-options` reports
`pattern == "decision_rules_numbered"` with `count >= 2`, Phase 3 keeps **today's** behavior —
source the options from `locate-options`, proceed to Phase 4 scoring, and reach Phase 7a/7b
normally. Phase 7b's probe then returns exit 0 (there genuinely are no groups) and the flag clears
*after* a real decision and annotation. No path is newly blocked and no path newly clears unearned.

State the exclusion in `locate_unresolved_decisions`' docstring alongside the Pattern E limitation:
*`decision_rules_numbered` blocks are deliberately not decision groups.* Assertion (c7) is the
guard.

### Part 5 — skill changes (`skills/decide-issue/`)

**Phase 2.5 → Phase 3 handoff.** Phase 2.5 (`SKILL.md:110-146`) gates decidability on
`ll-issues locate-options`; Phase 3 (`:160-190`) today calls "the same CLI used in Phase 2.5" and
now moves to the group probe. That framing breaks, and the divergence is not cosmetic: Phase 2.5
can pass (options exist) while `check-unresolved-decisions` returns **zero** groups because they
are all already resolved — a common shape after a prior run annotated 7a and died before the 7b
write, or after a human decided by hand. Phase 3 must define that branch explicitly: **zero
unresolved groups with `decision_needed: true` falls through to Phase 7b**, which exits 0 and
clears the flag. Without this the fix stalls on the already-decided path.

**That fall-through carries part 4b's carve-out.** It fires only when the Phase 2.5 `locate-options`
result is not `decision_rules_numbered`; on that tier Phase 3 keeps today's behavior and scores the
options rather than clearing on an empty group set. Without the carve-out the fall-through is itself
an unearned clear — see part 4b.

**Phase 3 sources its candidate group** from `check-unresolved-decisions` rather than
`locate_enumerable_options`'s raw winner, so already-resolved groups are skipped and repeated runs
advance. The `count == 1` branch (`SKILL.md:187`) now reads the selected group's option count.

> ⚠ **Carry-forward obligation from BUG-3287 (added 2026-08-21) — do not drop this at the rewrite.**
> BUG-3287 lands first and adds a `residual_directive is None` guard to that same `count == 1`
> branch, because under its recommended Option B a preempted directive collapses `count` to 1
> (measured on `BUG-3229`: `2, provisional_e` → `1, bullet`) and the branch clears
> `decision_needed` with the directive still open. This Phase 3 rewrite **replaces the sentence
> that guard lives on**, so the guard vanishes unless it is deliberately re-expressed.
>
> Re-express it in the group vocabulary: the branch may clear only when the selected group holds one
> option **and** `check-unresolved-decisions` reports no other unresolved group — which the group
> iterator already knows, since part 3 probes `_locate_directive_alternatives` in addition to tiers
> under `include_approximate_tiers=True`. So the obligation is discharged *by construction* here,
> not by copying BUG-3287's clause — but it must be **stated**, because "the group probe covers it"
> is exactly the reasoning that produces a silent regression when nobody checks.
>
> **Assertion:** extend assertion (a) with a fixture holding one bullet-tier option plus a preempted
> Pattern E directive — `check-unresolved-decisions` must exit **1**, and the Phase 3 phase-text
> assertion must show the `count == 1` branch cannot clear on it. BUG-3287's part 1c (Phase 3
> *reporting* prose) was deferred into this issue for the same reason; the reporting side is the
> Phase 9 line already specified in part 5.

**Phase 3 selects the *first* unresolved group in document order** (`unresolved[0]` — the CLI emits
groups sorted by `start_line`). State this explicitly in the skill prose. Without a pinned rule the
selection is model-discretionary, so two runs over the same file can pick different groups, and the
"one decision point per run, bounded" convergence argument below stops holding.

**Phase 7a's idempotency rule becomes per-group.** `SKILL.md:409` today reads *"if the issue
already contains a `### Decision Rationale` section, skip the annotation write"* — document-wide.
Once Phase 3 can select a second group, that rule silently suppresses the annotation for it: run 2
picks group B, writes no `> **Selected:**` callout, and B stays unresolved forever. Rephrase as:
skip only when **the selected group** is already resolved per `is_group_resolved`.

**The rationale heading text must stay exactly `### Decision Rationale` — do not suffix it.** When a
second group is decided and a `### Decision Rationale` already exists in the section, disambiguate in
the *body*, not the heading: the subsection's first line becomes
`**Decision point:** <group heading or first option label>`. A suffixed heading
(`### Decision Rationale — <label>`) reads fine to a human and still matches the lenient
`_DECISION_RATIONALE_SECTION_MARKER_RE` (`issue_parser.py:1326`, `^\s*###\s+Decision Rationale\b`),
but there is a **second, strict constant** that it silently breaks:

- `_DECISION_RATIONALE_HEADING_RE` (`issue_parser.py:1316`) is
  `r"^###\s+Decision Rationale\s*$"` — end-anchored, and its own comment at `:1318` says *"exact
  heading, no trailing text"*
- its consumer is `_unapplied_decision` (`:1449`, the `format-check` gate), at `:1466`:
  `dr_start = dr_match.start() if dr_match else len(proposed_body)`, feeding
  `scrub_start = min(dr_start, spans[-1][1])`

Under a suffixed heading that search misses, `dr_start` falls back to end-of-section, the self-scan
window widens, and every issue decided after this lands risks a new `unapplied_decision` false
positive. That function is also being actively changed by **BUG-3289**, so widening its regex here
would collide with in-flight work for a purely cosmetic gain. Keeping the heading literal leaves
`_unapplied_decision` untouched and out of this issue's blast radius entirely.

Two identical `### Decision Rationale` H3s in one section are acceptable under part 1 because the
section-level fallback in `is_group_resolved` only fires for **single-group** sections — a
multi-group section resolves per group via an in-span marker, so the duplicate heading is inert to
the detector. (The older `_RESOLVED_OPTION_MARKER_RE` this bullet used to cite no longer exists —
`f39a417e` deleted it.)

**Phase 7a needs a marker placement rule for every tier.** Today it inserts the callout
"immediately after the winning option's title line" — which is undefined for the two group shapes
this fix newly reaches:

- **`bullet` / `numbered` groups** — insert the callout immediately after the winning bullet's line,
  and rely on part 1's span rule so the callout does not split the group. (Phase 3b step 3's
  Pattern D branch already does exactly this — *"add a `> **Selected:** (x) — per the stated
  recommendation` callout on the recommended bullet"* — so the two paths agree by construction.)
- **`provisional_e` groups** — a directive window has no option title line, and **a callout on a
  neighbouring line does not work.** Per the measurement in part 3, `_locate_directive_alternatives`
  suppresses per sliding window, so a marker on the line before or after the directive always leaves
  the `i = D-3` window unsuppressed — the group re-emits forever, *and* the surviving window's span
  excludes the marker, so a span-scoped `is_group_resolved` check fails too. The marker must
  therefore go **on the directive line itself**. The prescribed form is a bare `**RESOLVED**` bold
  run, with the reason **outside** it:

  ```markdown
  **RESOLVED** — the shim. **DECISION — pick one before step 4: use the shim or rewrite the caller.**
  ```

  Verified `None` (2026-08-23). **The bold run must close immediately at `RESOLVED`** —
  `_RESOLVED_QUESTION_MARKER_RE`'s alternatives are `(?:✅|✔)\s*RESOLVED`, `>\s*\*\*RESOLVED\*\*`,
  and `\*\*RESOLVED\*\*`, all of which require the closing `**` right after the word. Decorating the
  bold run — `**RESOLVED — the shim.**`, `**RESOLVED:** the shim.` — matches **nothing** and leaves
  the group emitting forever (both measured; see part 3's table). A `**DECIDED — …**` rewording does
  **not** work either, because the `pick one` imperative survives it.
  Without this rule a Pattern E group co-located with any other group in the same section can never
  be retired (the section-level fallback is restricted to single-group sections) — a
  permanent stall, exactly what the per-group idempotency rule above exists to prevent.

  > ⚠ **Prescribed form changed twice — read both notes.** Round 6 (2026-08-21) moved from an
  > appended `> **Selected:**` callout to a `**RESOLVED**` prefix; **round 7 (2026-08-23) corrected
  > the prefix's shape**, because round 6 wrote it as `**RESOLVED — the shim.**`, which suppresses
  > nothing (measured). The bold run must close at `RESOLVED`: `**RESOLVED** — the shim.`
  >
  > Round 6's original reasoning, still valid for *why the prefix rather than the callout*: earlier
  > revisions specified appending `> **Selected:** the shim.` to the end of the directive line. Both
  > forms suppress `_locate_directive_alternatives` equally (both measured `None` — the appended
  > callout matches `_PREFERENCE_MARKER_RE`'s `>\s*\*\*selected:\*\*`, since windows are
  > whitespace-normalized before matching), but the appended form is wrong on two counts:
  >
  > 1. **It is not a callout to anything that reads callouts.** `_SELECTED_CALLOUT_RE`
  >    (`issue_parser.py:1361`) is `r"^\s*>\s+\*\*Selected:\*\*\s*(.+)$"` — line-anchored.
  >    Measured: the appended form does **not** match; the same text on its own line does. So the
  >    marker is invisible to `_selected_option_title`, `_unapplied_decision`'s selected-index
  >    resolution, and to `is_group_resolved` itself. Writing a `> **Selected:**` that no
  >    `> **Selected:**` consumer can see invites exactly the "the probe covers it" reasoning this
  >    issue keeps having to correct.
  > 2. **A mid-line `>` is not markdown.** Blockquote syntax is line-initial; the appended form
  >    renders as literal `> **Selected:** the shim.` text inside the directive sentence.
  >
  > The `**RESOLVED**` prefix has neither problem — *in its bare-bold-run form only*, per the
  > round-7 correction above. **The
  > retirement mechanism for a `provisional_e` group is probe suppression, not resolution** — the
  > group ceases to be emitted, so `locate_unresolved_decisions` returns it no more and the gate
  > passes. Say this in the skill prose rather than implying the callout path.

**Phase 7b** runs `ll-issues check-unresolved-decisions` *after* 7a's annotation write. Exit 0 →
clear as today. Exit 1 → leave `decision_needed: true`, make no frontmatter write, and carry the
surviving groups into Phase 9 as
`⚠ decision_needed remains true — N unresolved decision point(s): <heading:line-range>`. This
applies Phase 3b-i's existing principle — *"automation cannot clear a flag it did not earn"* — to
the multi-decision case. Frontmatter writes keep decide-issue's existing inline Edit-tool `---`
block convention (`SKILL.md:411-424`, reused at `:313-321`); do not introduce a CLI-mediated write
for this field.

**Phase 3b step 4 gets the same gate — this is not optional.** `SKILL.md:313-321` is a *second,
independent* clearing site, and its step 6 (`:323`) routes to Phase 8/9 *"skipping Phases 4–7"*, so
Phase 7b's new probe never executes on that path. It is `AUTO_MODE`-only, which makes it the path
`ll-auto` / `autodev` / `resolve-decision.yaml` actually take — gating only Phase 7b would leave the
reported defect fully live under automation while appearing fixed interactively. Rewrite step 4 as:

1. run `ll-issues check-unresolved-decisions <ID>` **after** step 3's lock-in edit;
2. **exit 0** → clear as today (unchanged wording, including the existing `Idempotency` line);
3. **exit 1** → make no frontmatter write, log
   `✗ Phase 3b: locked in [approach], but N unresolved decision point(s) remain — decision_needed remains true`,
   and carry the surviving groups into Phase 9 exactly as Phase 7b does;
4. **exit 2+** → treat as exit 1 (conservative: never clear on an unverifiable probe).

Step 5's success log line stays on the exit-0 branch only.

**Step 3's Patterns A–C branch must also write a resolution marker, or the gate stalls the auto
path.** Step 3 (`SKILL.md:300-303`) has two branches, and only one of them leaves a marker the new
probe can see:

- **Pattern D** — *"add a `> **Selected:** (x) — per the stated recommendation` callout on the
  recommended bullet."* That callout *is* a valid `bullet`-tier resolution marker under part 1, so
  this branch clears in one pass and is unchanged.
- **Patterns A–C** — *"remove the provisional qualifier (`e.g.,`/parenthetical wrapper, `TBD`,
  `must be replaced with`)"*. **No callout, no rationale heading.** And step 1 explicitly routes
  *already-structured* alternatives to step 3 as a no-op (*"If already structured, this step is a
  no-op: **clear winner** → step 3"*), so the file can still hold an intact, unmarked
  `**Option A**`/`**Option B**` `bold_label` group when step 4's probe runs. The probe returns
  exit 1, step 4 makes no write, and `decision_needed` never clears — a permanent stall on the
  `ll-auto` / `autodev` path, introduced *by this fix*, on the single-decision common case.

The fix: **step 3's A–C branch additionally writes a `> **Selected:** <approach> — per the locked-in
provisional resolution` callout on the winning option block whenever structured option blocks exist
under `## Proposed Solution`** (i.e. whenever step 1 found them already structured, or materialized
them). Marker placement follows the same per-tier rule as Phase 7a. When no structured blocks exist
— the qualifier-removal-only case, where the edit deletes the provisional shape outright and leaves
no group for the probe to find — no callout is needed and the probe returns exit 0 naturally.

This is the precise shape of the risk the *Impact → Risk* bullet names ("an over-firing probe
converts a silent false-ready into a loop stall"), so it is a required part of the change, not a
polish item. Assertion (c4) is its guard.

### Part 6 — loop integration (`loops/oracles/resolve-decision.yaml`)

`assert_decision_cleared` (`:185-204`) routes `on_yes` (flag still true) to `failed`. A
legitimately-residual decision would now be a hard oracle failure. Distinguish
*residual-by-design* from *silent no-op*, which is what that state was written for (BUG-2595):

- Insert a `check_residual_decision` state between them:
  `ll-issues check-unresolved-decisions ${context.issue_id}`, `fragment: shell_exit`.
- `assert_decision_cleared` `on_yes` → `check_residual_decision`.
- `check_residual_decision` `on_no` (**exit 1** — a real residual group survives) → `done`. The flag
  is *correctly* still set; the sub-loop's job is finished and the caller's `decision_needed` gate
  holds the issue for human review.
- `on_yes` (**exit 0** — the flag is set with nothing justifying it) → `failed`, preserving
  BUG-2595's silent-no-op detection exactly.
- `on_error` (**exit 2+**, including part 4's unresolvable-ID case) → `failed` — an unverifiable
  state stays conservative, matching the existing comment.

The branch polarity follows `fsm/evaluators.py:255-259` (0→yes, 1→no, 2+→error); assigning `on_yes`
to exit 1 inverts both branches, routing a legitimate residual to `failed` and a genuine no-op to
`done`.

**Do not route `on_yes` to `check_open_question_progress`.** That creates an unbounded cycle with
no exit: `progress → on_no → run_decide → assert → on_yes → progress → …`. The stall gate
(`open_question_stall_gate`, `common.yaml:211-231`, `max_stall: 2`) cannot break it, because
`check_open_question_progress` counts `count_unresolved_options + count_open_questions_in_sections`
at the **default** conservatism — by part 3 that counter cannot see the residual group, so it reads
flat and is not measuring the quantity being retried.

### Convergence is interactive-mode only

In interactive mode: run 1 decides A/B/C, run 2 decides (a)/(b), run 3 finds nothing residual and
clears — one decision point per run, bounded, and deterministic because Phase 3 always takes
`unresolved[0]`.

Under `--auto` this does **not** hold. Phase 3's existing auto-mode rule (`SKILL.md:183`) says that
when `pattern == "bullet"` and `AUTO_MODE = true`, options are **not** routed to Phase 4 scoring —
*"automation must not re-litigate an informal list the author may have already settled."* The
newly-reachable bullet groups are exactly that tier, so an auto run cannot resolve the residual it
just detected. Accepted, not worked around: a residual bullet-tier group under `--auto` is a
**human-review exit** — `decision_needed` stays `true`, Phase 9 names the group, and the run exits
0. The auto path converges by *stopping*, not by deciding, and part 6's routing must not treat that
as retryable. Widening the bullet-tier auto-mode exclusion is explicitly out of scope.

**Verified: the caller already bounds re-entry, so `check_residual_decision → done` cannot spin.**
`autodev.yaml`'s `decide_current` (`:611-628`) short-circuits on a write-once
`${context.run_dir}/autodev-decide-ran` marker (*"the flag is cleared per-issue at dequeue_next"*),
and the caller-side `record_decision_unresolved` state absorbs the still-set-flag outcome. So a
multi-decision issue under autodev gets exactly **one** decide pass per dequeue and then routes to
human review — which is the intended behavior, not an accident. Impact → Risk below asserts
bounded-ness; this is the mechanism it rests on.

### Rejected alternatives

- **Span-excluding re-scan** (the original proposal): excluding
  `options[0].start_line`–`options[-1].end_line` is unusable while BUG-3279 stands — on ENH-3277 the
  last option's span runs to line 435 against a section ending near 546, so the exclusion window
  swallows the region the surviving decision lives in. It also detects only case 1.
- **`--all-tiers` on `locate-options`**: returns all *matching* tiers, so it misses cases 2 and 3
  entirely, and adds a flag shape with no precedent in the CLI (every existing `--all*` widens
  *which issues* are processed, not how many matches one resolution returns).
- **Per-block resolution** (`_is_option_resolved` per block, the first-review spec): every loser
  option reads as unresolved, so a correctly-decided single-decision issue never clears. Verified
  against live `issue_parser.py`. This is what part 1 exists to correct.

Both span-based alternatives are dropped, which removes this issue's dependency on BUG-3279.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

**Anchor drift since last refine (2026-08-21 → now).** Three sibling issues landed after this
issue's last research pass — BUG-3287 (`e16a0bd83`), BUG-3285 (`c25d6c85f`), BUG-3289 (`e3ffd49ce`)
— and shifted `scripts/little_loops/issue_parser.py` line numbers throughout this document's Parts
1-6. Re-verify every citation at implementation time rather than trusting the numbers below the
table; confirmed current lines as of this pass:

| Symbol | Cited in this doc | Current actual line |
|---|---|---|
| `_SELECTED_CALLOUT_RE` | `:1361` | 1361 (unchanged) |
| `_DECISION_RATIONALE_HEADING_RE` | `:1316` | 1366 |
| `_DECISION_RATIONALE_SECTION_MARKER_RE` | `:1326` | 1376 |
| `_option_span_boundary` def | `:1381` | 1450 |
| `_unapplied_decision` def | `:1449` | 1518 |
| `_locate_directive_alternatives` def | `:2137` | 2264 |
| `LocatedOption` class | `:1966` | 2065 |
| `LocatedOptions` class | `:1984` | 2083 |
| `_OPTION_PATTERN_NAMES` | `:1962` | 2061 |
| `_locate_options_in_text` def | `:2025` | 2133 |
| `locate_enumerable_options` def | `:2209` | 2424 |
| ENH-2446 conservatism comment | `:2271-2275` | ~2513 |
| `_is_option_resolved` def | `:2328` | 2570 |
| `locate_unresolved_options` def | `:2341` | 2583 |
| `_OPTION_HEADING_RE` / `_iter_option_blocks` | `:2281-2326` | 2523 / 2529 |

`skills/decide-issue/SKILL.md` citations for Phase 7b (`:411-424`) and Phase 3b step 4
(`:313-321`) remain exact. Two smaller SKILL.md drifts: `## Phase 3: Extract Options` heading is
now at line 158, not 160 (content this doc cites at `:160-190` runs through line 188); Phase 3b
step 3 ("Lock in without scoring") is now at lines 308-312, not `:300-303` (that earlier range now
falls inside step 2, "Re-scan and route to full scoring").

**`_DIRECTIVE_ALTERNATIVES_SECTIONS` is now a 5-entry list, not 4.** BUG-3293 (landed since this
issue's last pass) added `"Program Design"` to the fixed section-order list `_locate_directive_alternatives`
scans (`issue_parser.py:2255-2261`: `Scope Boundaries`, `Proposed Change`, `Proposed Solution`,
`Open Questions`, `Program Design`). Part 3's "a directive in any section outside that 4-entry list
is invisible" consequence should read 5-entry; the "at most one Pattern E group per document" limit
itself is unaffected — confirmed still true (the function still `return`s on its first
matching window across the fixed list).

**The Part 4 "deliberate divergence from `check_open_questions.py:56`" premise no longer holds.**
BUG-3294 (Completed, landed since this issue's last pass) already changed `check_open_questions.py`
to `return 2` for a missing issue (confirmed at `check_open_questions.py:56`); `check_decidable.py`
already returned 2 there too. So `check-unresolved-decisions` returning exit 2 for an unresolvable
ID is no longer a divergence from `check_open_questions.py` — both probes already agree on 2. The
design decision itself (exit 2, not 1, per the `fsm/evaluators.py:255-259` on_error mapping) is
still correct and required; only the comparison used to justify it is now moot and should not be
repeated as a "divergence" at implementation time.

**The Part 5 "Carry-forward obligation from BUG-3287" is confirmed discharged, not merely
anticipated.** BUG-3287 has since landed (`e16a0bd83`) exactly as this doc's hedge assumed —
`locate_enumerable_options` (`issue_parser.py:2424`) attaches a preempted Pattern E directive as
`LocatedOptions.residual_directive` without replacing the winning tier result (Option B, as this
doc names it), and `skills/decide-issue/SKILL.md:187` already carries the `residual_directive is
non-null` guard on the `count == 1` branch, phrased in exactly the terms this doc anticipated. This
doc's Phase 3 rewrite (Part 5) still must re-express that guard in the new group vocabulary when it
replaces the sentence it lives on — the obligation is now against live code, not a future landing.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `DecisionGroup` / `_iter_decision_groups` /
  `is_group_resolved`, `locate_unresolved_decisions`, opt-in tier + directive coverage in the group
  iterator. `locate_unresolved_options`, `_iter_option_blocks`, and `_OPTION_PATTERNS` are left
  unchanged (the `_OPTION_PATTERNS[3]` widening is BUG-3287)
- `scripts/little_loops/cli/issues/check_unresolved_decisions.py` (new) and `cli/issues/__init__.py`
  (`:733-742` parser block, `:1021-1024` dispatch). `locate_options.py` is **not** touched
- `skills/decide-issue/SKILL.md` — Phase 2.5→3 handoff, Phase 3 group sourcing + first-in-document
  -order selection rule, **Phase 3b step 3 A–C callout write**, **Phase 3b step 4 gate
  (`:313-321`)**, Phase 7a per-group idempotency + per-tier marker placement (including the fenced
  `provisional_e` example), Phase 7b gate, Phase 9 report line
- `skills/decide-issue/reference.md` — Phase 9 Output Report Template (`:94`)

> ⚠ **Line budget — eight edits, five lines of headroom (re-measured 2026-08-23).**
> `skills/decide-issue/SKILL.md` is **495 lines** against a hard **500-line** cap enforced by
> `TestSkillLineLimit` (`scripts/tests/test_enh494_skill_companions.py:73-86`). The earlier
> "seven edits, seven lines" arithmetic was measured at 493 lines and before part 4b added the
> Phase 3 `decision_rules_numbered` carve-out. ENH-3280 and BUG-3296 also queue against this file
> (BUG-3287's edit has already landed). This is the **most numerous** of the queued edit sets and it
> includes a fenced markdown example, so it cannot land as pure in-place prose.
>
> **Land the `reference.md` extraction as its own preparatory commit before starting this issue.**
> With five lines of headroom there is no room to discover the cap mid-implementation.
>
> **Required shape:** the *rules* stay in `SKILL.md` as imperative one-liners on their existing
> phases; the *tables and examples* move to `skills/decide-issue/reference.md` behind a
> `See [reference.md](reference.md) for …` pointer — specifically the **per-tier marker-placement
> matrix** (including the `provisional_e` fenced example and the per-window suppressor
> measurement) and the **Phase 3b step 4 exit-code disposition table**. Both are reference material
> by nature and neither is executed inline. Target: **≤ 20 net lines** added to `SKILL.md`.
> See EPIC-3290 § *Shared constraint — the decide-issue SKILL.md line budget*; if the extraction
> lands as a standalone preparatory commit, this issue only needs the budget check.
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — new `check_residual_decision` state

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/check_open_questions.py:44-59` — calls
  `locate_unresolved_options` directly; unchanged by part 2's "leave it alone" decision, and the
  guard for that is assertion (e)
- `scripts/little_loops/cli/issues/check_decidable.py:19-52` — shares Phase 7b's single-tier blind
  spot for the same reason, but is **not** modified here (BUG-3287 covers the shared chain)
- `scripts/little_loops/issue_parser.py:1449` `_unapplied_decision` (the `format-check` gate) —
  **deliberately untouched.** It reads the *strict* `_DECISION_RATIONALE_HEADING_RE` (`:1316`,
  end-anchored) at `:1466`, so Phase 7a's rationale heading must stay literally
  `### Decision Rationale`; part 5 pins that, assertion (c5) guards it. BUG-3289 is changing this
  function concurrently — keeping the heading literal is what keeps the two changes disjoint
- `scripts/little_loops/loops/oracles/resolve-decision.yaml`:
  - `check_decision_decidable` (`:47-67`) — inherits `check-decidable`'s blind spot; unchanged here
  - `check_open_question_progress` (`:104-143`) — sums
    `count_unresolved_options + count_open_questions_in_sections` at default conservatism;
    deliberately untouched (part 3)
  - `assert_decision_cleared` (`:185-204`) — rerouted per part 6
- Confirmed FSM gate consumers of the `decision_needed` flag — the actual blast radius of a
  falsely-cleared flag. The fix only makes the flag *more* conservative, so no change is implied;
  listed for completeness:
  - `loops/rn-remediate.yaml:274-278` (`check_decision_needed`)
  - `loops/autodev.yaml:611-628` (`decide_current`), `:1281-1290`, `:1294-1311`
  - `loops/recursive-refine.yaml:571-578` (greps `decision_needed: true` directly)
  - `loops/refine-to-ready-issue.yaml:229-243`, `:583-589`
  - `loops/auto-refine-and-implement.yaml:229-238`, `:283-290`, `:588-597`

### Similar Patterns

- New `ll-issues` subcommand tests in this area reuse a shared `_cli()` / `temp_project_dir` /
  `_write_issue` / `_invoke` fixture quartet verbatim — `test_issues_locate_options.py`,
  `test_ll_issues_check_decidable.py`, `test_ll_issues_check_open_questions.py`
- `decide-issue` is tested structurally, not by live execution: `test_decide_issue_skill.py` reads
  `SKILL.md` text and asserts phrases within a bounded phase-text slice, because the skill is
  LLM-executed with no subprocess entry point. Follow that split — skill-prose assertions for the
  `SKILL.md` changes, subprocess CLI tests for the `issue_parser.py` layer

### Tests

- `scripts/tests/fixtures/issues/BUG-3278-two-decision-points.md` — new; both groups inside one
  `## Proposed Solution`. `FEAT-2339-mixed-resolved-unresolved.md` is the nearest existing fixture
  but both its options are already resolved
- `scripts/tests/fixtures/issues/BUG-3278-two-decision-points-first-decided.md` — new; the same
  document with group A carrying a `> **Selected:**` callout and the section carrying a
  `### Decision Rationale`
- `scripts/tests/fixtures/issues/BUG-3278-directive-only.md` and
  `BUG-3278-directive-resolved.md` — new; a prose `pick one` directive, and the same document with
  the bare `**RESOLVED**` prefix on the directive line. Assertion (c6)
- `scripts/tests/fixtures/issues/BUG-3278-decision-rules-only.md` — new; a `## Program Design` →
  `### Decision Rules` bold-numbered block as the document's only decision surface. Assertion (c7)
- `scripts/tests/test_issue_parser_unresolved.py` — new `TestDecisionGroups`, following the
  existing `class Test<Concept>` / `def test_<scenario>_<expectation>` convention alongside
  `TestLocatedOptionsDataclass`, `TestCountUnresolvedOptions`, `TestPatternEDirectiveAlternatives`
- `scripts/tests/test_ll_issues_check_unresolved_decisions.py` — new subprocess CLI tests
- `scripts/tests/test_decide_issue_skill.py` — phase-text assertions; the existing
  `TestDecisionNeededFrontmatterUpdate::test_decision_needed_false_update_documented` (line 192)
  asserts `"decision_needed: false"` appears in the Phase 7 slice and must keep passing on the
  clearing branch. `test_idempotency_rule_documented` (line 201) only asserts the substring
  `Idempotency`, so it survives the Phase 7a rewording unchanged — which is why a new, specific
  per-group assertion is needed
- `scripts/tests/test_issues_locate_options.py::TestLocateOptionsJsonFlag` — unaffected;
  `locate-options` is not touched

### Documentation

- `docs/reference/API.md` — add `DecisionGroup`, `_iter_decision_groups`, `is_group_resolved`,
  `locate_unresolved_decisions`
- `docs/reference/CLI.md` — new `#### ll-issues check-unresolved-decisions` beside
  `#### ll-issues locate-options` (lines 2021-2039)
- `docs/reference/COMMANDS.md:256` — "Sets `decision_needed: false` after annotating the winning
  option" is stated as an unconditional handshake; line 254's "the same call Phase 3 makes" framing
  also goes stale
- `docs/guides/DECISIONS_LOG_GUIDE.md:176-190, 196` — the pipeline diagram and prose both present
  clearing as unconditional

### Configuration

N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

**Test-line citation correction.** Implementation Step 9 cites
`test_decision_needed_not_cleared_on_no_actionable` at "line 310" — it is currently at line 334 in
`scripts/tests/test_decide_issue_skill.py`. The two other citations from the same test file,
`test_decision_needed_false_update_documented` (line 192) and `test_idempotency_rule_documented`
(line 201), are still exact.

**`skills/decide-issue/SKILL.md` is 495 lines today, not 493.** The Line Budget warning's "seven
edits, seven lines of headroom" arithmetic was measured against 493; current headroom against the
500-line `TestSkillLineLimit` cap is closer to 5 lines. Re-measure at implementation time — the gap
is small but the file has kept growing since this warning was written (`da8c1ad8e` previously
trimmed it under the cap once already).

**Two "Confirmed FSM gate consumers" line ranges could not be re-verified and may be stale.**
`loops/refine-to-ready-issue.yaml:229-243, :583-589` — a grep for `decision_needed` in that file
today lands near lines 232-245 and 574-618, not exactly the cited ranges; the actual
`check_decision_needed`-style state is at line 618. `loops/auto-refine-and-implement.yaml:229-238,
:283-290, :588-597` — only one incidental `decision_needed` hit (a comment at line 875) was found
by a direct grep; the three cited ranges did not resolve. Both files are listed as unchanged by this
issue ("no change is implied"), so this doesn't block the fix, but the citations should be
re-confirmed (or the search widened to `check-flag`/`check_decision`-prefixed state names) before
being relied on.

## Program Design

### Types

- `DecisionGroup` — new, `scripts/little_loops/issue_parser.py` — `heading: str | None`,
  `tier: str`, `options: list[LocatedOption]`, `start_line: int`, `end_line: int`
- `LocatedOption` — `scripts/little_loops/issue_parser.py:1966` — `label: str`, `text: str`,
  `start_line: int`, `end_line: int`; `to_dict()` at `:1974`
- `LocatedOptions` — `scripts/little_loops/issue_parser.py:1984` — `count: int`,
  `pattern: str | None`, `heading: str | None`, `options: list[LocatedOption]`,
  `residual_directive: LocatedOptions | None = None` (fifth field, added by BUG-3287 — the group
  iterator reads it instead of calling `_locate_directive_alternatives` itself, per part 3)

### Signatures

- `_iter_decision_groups(content: str, *, include_approximate_tiers: bool = False) -> list[DecisionGroup]` — new
- `is_group_resolved(content: str, group: DecisionGroup) -> bool` — new
- `locate_unresolved_decisions(content: str, *, include_approximate_tiers: bool = False) -> list[DecisionGroup]` — new
- `cmd_check_unresolved_decisions(config: BRConfig, args: argparse.Namespace) -> int` — new,
  `scripts/little_loops/cli/issues/check_unresolved_decisions.py`
- `locate_enumerable_options(content: str) -> LocatedOptions` —
  `scripts/little_loops/issue_parser.py:2209` — unchanged; still the winner-take-all mechanism the
  bug is about, and still what Phase 2.5 and `check-decidable` use
- `locate_unresolved_options(content: str) -> tuple[int, str | None]` —
  `scripts/little_loops/issue_parser.py:2341` — **unchanged**, per part 2
- `_locate_directive_alternatives(content: str) -> LocatedOptions | None` —
  `scripts/little_loops/issue_parser.py:2264` — unchanged, and **not called directly by the group
  iterator**: BUG-3287 already runs it alongside every tier win, so the iterator reads
  `LocatedOptions.residual_directive` instead (part 3). Returns on its **first** matching window,
  so it yields at most one Pattern E group per document
- `_locate_decision_rules_numbered(content: str) -> LocatedOptions | None` —
  `scripts/little_loops/issue_parser.py:2382` — unchanged, and **deliberately not a decision-group
  source**; its `decision_rules_numbered` result is handled by part 4b's Phase 3 carve-out, not by
  the group iterator
- `_option_span_boundary(text: str, search_start: int, max_depth: int, fences: list[tuple[int, int]]) -> int | None` —
  `scripts/little_loops/issue_parser.py:1381` — unchanged; reused by the group iterator (part 3)
- `_is_option_resolved(block_body: str) -> bool` —
  `scripts/little_loops/issue_parser.py:2328` — unchanged; post-`f39a417e` this is a
  `> **Selected:**` callout test only, **not** a model for `is_group_resolved`

### Call Path

Before: `/ll:decide-issue` Phase 7b (`SKILL.md:411-424`) -> `ll-issues locate-options ID --json` ->
`cmd_locate_options` (`cli/issues/locate_options.py:19`) -> `locate_enumerable_options`
(`issue_parser.py:2209`) -> `_locate_options_in_text` (`:2025`) -> first matching tier only ->
Phase 7b writes `decision_needed: false` unconditionally. Phase 3b step 4 (`SKILL.md:313-321`)
writes it unconditionally too, on a path that never reaches Phase 7b at all.

After: `/ll:decide-issue` Phase 7b **and Phase 3b step 4** ->
`ll-issues check-unresolved-decisions ID` ->
`cmd_check_unresolved_decisions` -> `locate_unresolved_decisions` -> `_iter_decision_groups` +
`is_group_resolved` -> exit 0/1/2 -> either site writes only on exit 0.
`resolve-decision.yaml` `assert_decision_cleared` -> `check_residual_decision` -> same CLI ->
`done` / `failed`.

### Decision Rules

N/A — the detection mechanism is pinned (Mechanism C); this fix corrects existing
frontmatter-clearing logic and introduces no new gap kind, gate, keyword list, or threshold.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

**`LocatedOptions`'s Types listing is missing a field BUG-3287 already added.** The live dataclass
(`issue_parser.py:2083-2100`) now carries a fifth field, `residual_directive: LocatedOptions | None
= None` (line 2095), landed by BUG-3287 after this section's Types list was last written. The
Proposed Solution prose elsewhere in this document already discusses `residual_directive` at
length and depends on it (Part 5's carry-forward obligation); only this Types subsection's field
list is out of sync with the live class.

## Implementation Steps

**Parser layer** (`scripts/little_loops/issue_parser.py`)

1. **Group-aware resolution first — everything else depends on it.** Add `DecisionGroup`,
   `_iter_decision_groups`, `is_group_resolved` per part 1, with the iterator computing its own
   block boundaries — reusing BUG-3279's `_option_span_boundary` helper for the rule itself, and
   adding the offsets `_iter_option_blocks` cannot supply — while honoring the span rule for
   resolution markers. `_iter_option_blocks` stays as-is. Unit tests in
   `test_issue_parser_unresolved.py::TestDecisionGroups`:
   - three `**Option A/B/C**` blocks with a `> **Selected:**` on A → **one** group, resolved (the
     case the per-block spec got wrong — B and C must not report as residual)
   - the same three blocks with no marker anywhere → one group, unresolved
   - a section-level `### Decision Rationale` with the callout at the top of `## Proposed Solution`
     rather than on an option line, **one group in the section** → resolved (this issue's own shape)
   - the same section-level `### Decision Rationale` with **two groups in the section** → only the
     group carrying a `> **Selected:**` inside its own span is resolved. This pins the single-group
     restriction; an unrestricted rule passes every other case here and still reproduces the bug
   - `**Option A/B/C**` plus a separate `- (a)/(b)` pair → **two** groups, independently resolvable
   - a tier run split by an intervening `**DECISION — pick one:**` directive → two groups
   - a `> **Selected:**` callout inserted mid-group does not split the group (span rule)
2. Add `locate_unresolved_decisions` over step 1's iterator with `locate_enumerable_options`'s
   section precedence. **Leave `locate_unresolved_options` exactly as it is** — assertion (e) is
   its guard.
3. Under `include_approximate_tiers=True`, extend the group iterator to the `numbered` and `bullet`
   tiers and fold the Pattern E directive in as an additional probe — sourced from
   `LocatedOptions.residual_directive` (BUG-3287 already runs it alongside tier wins), **not** from a
   fresh `_locate_directive_alternatives` call. Default `False` must reproduce today's group set
   over Patterns 1–2 only — the regression guard for the ENH-2446 conservatism comment. Emit **no**
   `decision_rules_numbered` groups at either setting, and say so in the docstring (part 4b).

**CLI layer**

4. Add `cli/issues/check_unresolved_decisions.py` plus subparser registration and dispatch in
   `cli/issues/__init__.py`. Model on `check_open_questions.py`, diverging on the exit codes and
   payload shape in part 4. Include a CLI test for the unresolvable-ID exit-2 case.
5. Subprocess CLI tests in `test_ll_issues_check_unresolved_decisions.py`, reusing the
   `_cli()` / `temp_project_dir` / `_write_issue` / `_invoke` quartet.

**Skill layer** (`skills/decide-issue/`)

6. Phase 2.5 → Phase 3 handoff: state the zero-unresolved-groups branch explicitly (fall through to
   Phase 7b, which clears) **and its part 4b carve-out** — the fall-through does not fire when
   `locate-options` reports `pattern == "decision_rules_numbered"`; that tier keeps today's
   score-then-clear path. Add a phase-text assertion for both halves.
7. Phase 3: source the candidate group from `check-unresolved-decisions`; state the auto-mode
   boundary (bullet-tier residual under `AUTO_MODE = true` is not scored — exit 0 leaving the flag
   `true`, group named in Phase 9). Add phase-text assertions for both.
8. Phase 7a: per-group idempotency, a literal (**unsuffixed**) `### Decision Rationale` heading with
   the decision point named on the subsection's first body line, and the per-tier marker placement
   rule including the `provisional_e` case — whose marker is a bare `**RESOLVED**` bold run prefixed
   to the directive line with the reason *outside* the bold run
   (`**RESOLVED** — the shim. **DECISION — pick one …**`); not an appended `> **Selected:**`
   callout, and **not** a decorated `**RESOLVED — the shim.**`, which suppresses nothing. Add a
   phase-text assertion for the
   per-group phrasing, one asserting the heading stays literal (the guard for
   `_unapplied_decision`'s strict `_DECISION_RATIONALE_HEADING_RE` at `issue_parser.py:1316`), and
   one asserting the `provisional_e` placement rule names the prefix form and states that the group
   is retired by suppression rather than by `is_group_resolved`.
9. Phase 7b: run `ll-issues check-unresolved-decisions` after 7a's annotation; clear only on exit
   0; on exit 1 make no frontmatter write. Keep the literal `decision_needed: false` in the
   clearing branch and phrase the new branch as `decision_needed remains true`, matching
   `test_decision_needed_not_cleared_on_no_actionable` (line 310).
    **Same step, second clearing site — Phase 3b step 4 (`SKILL.md:313-321`).** Apply the identical
    exit-0/1/2+ gate per part 5. Phase 3b's step 6 routes to Phase 8/9 *"skipping Phases 4–7"*, so
    Phase 7b's probe never runs there; without this the fix is inert on the `--auto` path that
    `ll-auto` / `autodev` actually take. Add a phase-text assertion that the Phase 3b slice contains
    both `check-unresolved-decisions` and `decision_needed remains true`.
    **Same step, step 3's Patterns A–C branch.** Add the `> **Selected:**` callout write for the
    structured-blocks case per part 5, or the new gate stalls the single-decision auto path it was
    supposed to leave alone. Add a phase-text assertion that the Phase 3b slice requires a
    `> **Selected:**` callout on the A–C branch, not only on Pattern D. Assertion (c4) is the
    deterministic half.

10. `reference.md` Phase 9 Output Report Template (`:94`) gains the unresolved-decisions line;
    `SKILL.md` Phase 9 (line 463) continues to defer to it.

**Loop integration**

11. `resolve-decision.yaml`: insert `check_residual_decision` per part 6. FSM tests: (i) the
    residual-group path reaches `done` without re-firing `run_decide`; (ii) the silent-no-op path
    still reaches `failed`; (iii) no path re-enters `check_open_question_progress` from
    `assert_decision_cleared`.

**Tests**

12. Author the two fixtures listed in *Integration Map → Tests*.
13. Assertions. `decide-issue` is LLM-executed with no subprocess entry point, so
    "leaves `decision_needed: true` after one `--auto` run" is not assertable by any test in this
    suite. Each behavioral claim splits into a **deterministic CLI/parser assertion** plus a
    **phase-text assertion**:
    - **(a)** two decision points, one decided → `check-unresolved-decisions` **exits 1** and names
      the surviving group; paired with a Phase 7b phase-text assertion that exit 1 means no
      frontmatter write and `decision_needed remains true`
    - **(b)** convergence — with **both** groups marked resolved, `check-unresolved-decisions`
      **exits 0**, so the second run's clear is reachable; paired with a Phase 3 phase-text
      assertion that resolved groups are skipped. The end-to-end "second interactive run clears the
      flag" claim stays prose-level by necessity. The `--auto` contract is phase-text only: flag
      stays `true`, exit 0, Phase 9 names the group
    - **(c)** **common-path regression guard** — a single-decision fixture with three options where
      one is decided reports zero unresolved groups (exit 0), so the flag still clears in one run.
      The per-block filter fails here: losing options B and C read as unresolved and the flag never
      clears
    - **(c2)** **single-group-restriction guard** — the two-group fixture *after* group A is
      decided: a `### Decision Rationale` now exists in `## Proposed Solution`, and
      `check-unresolved-decisions` must still exit 1 for group B. An unrestricted section-level rule
      passes (a) and (c) and fails only this one
    - **(c3)** **span-rule guard** — after 7a inserts a `> **Selected:**` callout into a bullet-tier
      group, that group still reports as one group, not two
    - **(c6)** **`provisional_e` retirement guard** (added 2026-08-21; **corrected 2026-08-23**) — a
      fixture holding a prose `pick one` directive reports **exit 1**; the same fixture with a bare
      `**RESOLVED**` prefix on the directive line (`**RESOLVED** — the shim. **DECISION — pick
      one …**`) reports **exit 0**, because the group is no longer emitted. Pair it with **two** unit
      assertions, each pinning a way the rule gets "simplified" back into a permanent stall:
      (i) `_locate_directive_alternatives` still **matches** when the prefix is decorated
      (`**RESOLVED — the shim.**`, `**RESOLVED:** the shim.`) — the bold run must close at
      `RESOLVED`; (ii) `_SELECTED_CALLOUT_RE` does **not** match a `> **Selected:**` appended to the
      end of a directive line, which is why the callout form is not prescribed even though it does
      suppress the probe.
      > ⚠ The version of (c6) written in round 6 asserted **exit 0** for the decorated
      > `**RESOLVED — …**` form. That assertion **fails** against the live tree (measured
      > 2026-08-23). Do not "fix" it by relaxing the test — the marker shape is what was wrong
    - **(c7)** **`decision_rules_numbered` carve-out guard** (added 2026-08-23) — a fixture whose
      only decision surface is a `## Program Design` → `### Decision Rules` bold-numbered block:
      `check-decidable` exits **0** (`count 2`, `pattern decision_rules_numbered`) while
      `check-unresolved-decisions` reports **zero groups / exit 0**. Paired with a Phase 3 phase-text
      assertion that the zero-group fall-through does **not** clear on that tier and routes to
      Phase 4 scoring instead. Without this pair the fix introduces a fresh unearned clear on a
      shape Phase 2.5 passes — see part 4b
    - **(c4)** **Phase 3b A–C stall guard** — a fixture holding intact, unmarked
      `**Option A**`/`**Option B**` blocks reports **exit 1**, proving the probe would block step
      4's clear; the same fixture with the callout step 3's A–C branch now writes reports **exit 0**.
      This is the deterministic half of the part-5 A–C requirement — without that skill change the
      first state is what `ll-auto` reaches and the flag never clears
    - **(c5)** **`_unapplied_decision` non-regression** — a fixture decided with a literal
      `### Decision Rationale` heading yields the same `_unapplied_decision` output before and after
      this diff, pinning the "do not suffix the heading" rule against
      `_DECISION_RATIONALE_HEADING_RE`'s end-anchor (`issue_parser.py:1316`). Coordinate the
      snapshot with BUG-3289, which is changing the same function.
      > ⚠ **BUG-3285 also perturbs this snapshot (added 2026-08-21) — coordinate with both.**
      > BUG-3285 tightens `_OPTION_HEADING_RE`, which feeds `_option_block_spans` (`:1405`), which
      > determines `_unapplied_decision`'s block set and therefore its `sel_ids` / `rej_ids`. Its
      > own *Codebase Research Findings* records the coupling explicitly: the BUG-3279 comment at
      > `issue_parser.py:1469-1475` names BUG-3285 as the tracked fix for `spans[-1]` resolving to
      > a phantom trailing block. So **three** issues move this function's output — BUG-3285
      > (block set), BUG-3289 (`discriminating`), and the snapshot must be taken against whichever
      > of them has already landed, never against a fixed baseline. Restate the baseline commit in
      > the test docstring
    - **(d)** an issue with a settled decision but open free-form questions still clears, proving
      the new probe is narrower than `check-open-questions`
    - **(e)** `locate_unresolved_options`' `(count, heading)` output is unchanged on every existing
      fixture — the guard for step 2's "leave it alone" decision. **Baseline is the tree this fix
      lands on, not pre-BUG-3279**: BUG-3279 deliberately changes that function's output (Rule 3
      section-scope resolution), so the assertion is "identical immediately before and after this
      issue's diff", captured as a snapshot at implementation time

**Docs**

14. `docs/reference/API.md` — the four new identifiers, with an explicit note that *group*
    resolution (any member marked, or a single-group section's `### Decision Rationale`) is
    deliberately different from `locate_unresolved_options`' per-block resolution, and that the two
    are not interchangeable.
15. `docs/reference/CLI.md` — new `#### ll-issues check-unresolved-decisions` section with exit
    codes (0 clean / 1 residual / 2 unresolvable ID — call out the deliberate divergence from
    `check-open-questions`) and the `--json` group shape.
16. `docs/reference/COMMANDS.md:254-256` — clearing becomes conditional; Phase 7b now makes its own
    residual-probe call.
17. `docs/guides/DECISIONS_LOG_GUIDE.md:176-190, 196` — the pipeline diagram and prose.

**Out of scope**

- The `_OPTION_PATTERNS[3]` widening and the Pattern E preemption in the shared
  `locate_enumerable_options` chain — **BUG-3287, landed `e16a0bd83`**. Cases 2 and 3 are fixed
  there; this issue consumes the result (the widened `bullet` tier, and `residual_directive`) rather
  than re-deriving it.
- Making `decision_rules_numbered` blocks decidable as decision groups — part 4b, deliberately
  excluded. If a live case ever needs it, file a follow-up; the exclusion is a semantic judgment
  ("design rulings are not mutually exclusive alternatives"), not an oversight.
- Broadening `check_open_questions.py` / `check_decidable.py` to decision *groups* — neither passes
  `include_approximate_tiers`, and step 2 leaves `locate_unresolved_options` untouched. Separate
  change with its own loop-gate blast radius; file as a follow-up if wanted.
- Widening Phase 3's auto-mode `bullet`-tier exclusion (`SKILL.md:183`). A residual bullet-tier
  group under `--auto` is a human-review exit by design.

## Impact

- **Priority**: P2 — silent false-ready into the implementation pipeline, but it needs a
  multi-decision issue to trigger, so it is not a blanket break of the common path
- **Effort**: Large (aligned with frontmatter `size: Large` 2026-08-21) — parser group model +
  new CLI + skill (**two** clearing sites, not
  one: Phase 7b and Phase 3b step 4) + one loop-oracle state.
  Decision-*group* detection is a new data model with its own grouping rules and test matrix, not a
  thin filter over existing blocks
- **Risk**: Medium. `autodev.yaml`, `refine-to-ready-issue.yaml`, `auto-refine-and-implement.yaml`,
  `rn-remediate.yaml`, and `recursive-refine.yaml` all *branch* on `decision_needed`, and
  `resolve-decision.yaml`'s `assert_decision_cleared` treats a still-set flag as a hard failure, so
  an over-firing probe converts a silent false-ready into a loop stall. Bounded by six things: the
  tier widening is opt-in; resolution is group-level so deciding one option settles its whole
  decision point without leaking to a co-located second group; Phase 3 skips resolved groups and
  Phase 7a annotates per group with a defined marker placement for every tier, so each interactive
  run makes progress; Phase 3 has a defined branch for the already-decided case; and
  `check_residual_decision` routes a legitimate residual to `done` rather than to `failed` or an
  unbounded retry cycle
- **Breaking Change**: No

## Root Cause

- **File**: `skills/decide-issue/SKILL.md`
- **Anchor**: `in Phase 7b (§ 7b: Update Frontmatter, :411-424)`
- **Cause**: Phase 7b performs an unconditional set-to-`false` with only an idempotency check ("if
  already `false`, skip the write"). There is no re-scan for surviving decision points, and the
  extraction that justified the clear (`locate_enumerable_options` via Phase 3) structurally returns
  at most one tier's worth of options.

- **Second site**: `§ Phase 3b step 4 (:313-321)` performs the same unconditional set-to-`false` on
  the `AUTO_MODE` lock-in path, and its step 6 skips Phases 4–7, so it never reaches Phase 7b's
  guard at all. Both sites must be gated — see Proposed Solution part 5.

The skill already establishes the correct principle elsewhere and simply does not apply it here —
Phase 3b-i (`SKILL.md:196-217`) refuses to clear the flag in the `NO_ACTIONABLE_DECISIONS` case with
the explicit rationale *"automation cannot clear a flag it did not earn"*. Phase 7b earns the flag
for one decision and clears it for all of them.

## Related Key Documentation

- `skills/decide-issue/SKILL.md` — Phase 3b-i states the "flag it did not earn" principle Phase 7b
  violates
- BUG-3287 — sibling split out of this issue; fixes cases 2 and 3 in the shared
  `locate_enumerable_options` precedence chain
- ENH-3277 — the issue where this was originally observed (see the *Evidence correction* note)

## Revision History

Three pre-implementation review rounds, each of which found a defect that would have shipped a
non-working fix. The spec above is the current state with all corrections applied; this log records
what changed and why so the reasoning is not lost.

- **Round 1 (2026-08-21)** — pinned Mechanism C over the span-excluding re-scan and `--all-tiers`
  alternatives.
- **Round 2 (2026-08-21)** — the unit of resolution was the option *block*, which is unimplementable
  as a flag gate: Phase 7a marks only the winner, so every loser reads unresolved and a
  correctly-decided single-decision issue would never clear. Introduced the decision-*group* model
  (part 1) and assertion (c).
- **Round 3 (2026-08-21)** — three further corrections: (i) the section-level resolution check must
  be restricted to single-group sections, or deciding group A resolves group B by side effect and
  reproduces the bug through the fix (assertion c2); (ii) Phase 7a's document-wide idempotency rule
  suppresses the annotation for every group after the first, stalling instead of converging;
  (iii) `check_residual_decision`'s `on_yes`/`on_no` were inverted against
  `fsm/evaluators.py:255-259`, which would route a legitimate residual to `failed` and a genuine
  silent no-op to `done`.
- **Round 4 (2026-08-21)** — the regex widening was split out to **BUG-3287** (it is a module-level
  change to the shared precedence chain, measured to alter output on 22 live issues, and shipping it
  alone introduces a new false-clear via Pattern E preemption). Two further corrections folded in:
  Phase 7a had no defined marker placement for `bullet` or `provisional_e` groups, so a directive
  group co-located with another could never be marked resolved; and Phase 3's move off
  `locate-options` left Phase 2.5 diverged from it, with no defined branch for the
  already-decided case. The step-10 fixture also changes from `- **(a) …**` to `- (a) …`, because
  the bold-wrapped shape is unreachable until BUG-3287 lands. This document was flattened from four
  layers of in-place revision into a single current-state spec at the same time.

  Round 4 also found **BUG-3279 in flight and uncommitted in the working tree** (it has since
  landed — see Round 5), which moves two of
  this issue's premises: (i) `_iter_option_blocks`' end-of-section over-consumption is fixed there,
  so boundary correctness is no longer the reason for a bespoke group iterator (offsets are), and
  the new shared `_option_span_boundary` helper should be reused; (ii) BUG-3279 adds an
  **unrestricted** section-scope resolution rule to `locate_unresolved_options`, knowingly accepting
  the partially-decided-multi-group hazard at the per-block layer. `is_group_resolved` must not
  inherit those semantics — see the note in part 1. Re-verify both against the tree state at
  implementation time; if BUG-3279's shape changed before landing, part 3 and assertion (e) are the
  paragraphs that move.

- **Round 5 (2026-08-21)** — pre-implementation review against the tree *after* BUG-3279 landed
  (`f39a417e`). Three spec corrections, each of which would have shipped a fix that does not fix
  the reported bug, plus a full citation refresh (`f39a417e` shifted every `issue_parser.py` anchor
  by +58 to +100 lines and **deleted `_RESOLVED_OPTION_MARKER_RE`**, which part 5 cited):
  1. **The fix gated only Phase 7b, but there is a second unconditional clearing site.**
     `SKILL.md:313-321` (Phase 3b step 4) writes `decision_needed: false` on its own and step 6
     skips Phases 4–7 entirely, so Phase 7b's new probe never executes there. That is the
     `AUTO_MODE`-only path `ll-auto` / `autodev` / `resolve-decision.yaml` take — the fix would have
     been inert exactly where the bug does the most damage. Part 5 and Implementation Step 9 now
     gate both sites.
  2. **Part 5's `provisional_e` marker placement could not work.** Measured against live
     `_locate_directive_alternatives`: the suppressors are evaluated per sliding window
     (`lines[max(0, i-3) : min(len, i+4)]`), so a `> **Selected:**` callout on the line *after* the
     directive leaves the `i = D-3` window unsuppressed and the group re-emits forever — and that
     surviving window's span excludes the callout, so a span-scoped `is_group_resolved` check fails
     too. Only a marker appended to the directive line itself is contained by every window that
     contains the imperative. A `**DECIDED — …**` rewording does **not** work (the `pick one`
     imperative survives it); ENH-3277's decided prose returns `None` only because it dropped the
     imperative outright, not because `DECIDED` is recognized.
  3. **Pattern E can only ever yield one group per document.**
     `_locate_directive_alternatives` returns from inside its scan loop on the first matching
     window, over a fixed 4-section list, so part 1's "one group per decision point" contract is
     best-effort for Pattern E. Part 3 now states the limitation and offers an explicit
     accept-vs-`_iter_directive_alternatives` choice rather than leaving it undiscovered.

  Three smaller corrections folded in: Phase 3 never said *which* group to select when several are
  unresolved (now pinned to `unresolved[0]`, document order, or the bounded-convergence argument
  does not hold); part 4 called the new `--json` payload a "drop-in substitute" for
  `locate-options --json` while also describing the incompatible reshape (top-level
  `count`/`pattern` → per-group `len(options)`/`tier`); and `_option_span_boundary`'s real
  four-argument signature is now recorded, since "reuse the shared helper" understated what the
  caller must supply. Confirmed correct and unchanged: the `fsm/evaluators.py:255-259` polarity and
  part 6's branch assignments, all `resolve-decision.yaml` state anchors, case 2 matching zero of
  four tiers, the quoted `locate_unresolved_options` docstring, and all four doc-update targets.
  One claim strengthened: `autodev.yaml`'s write-once `autodev-decide-ran` marker plus caller-side
  `record_decision_unresolved` is the mechanism that makes part 6's `done` routing provably
  non-spinning — Impact → Risk asserted bounded-ness without citing it.

- **Round 6 (2026-08-21)** — pre-implementation review. Three corrections:
  1. **The gate would have stalled the auto path it was written to protect.** Part 5 gated Phase 3b
     step 4 but accounted only for step 3's **Pattern D** branch. Step 3's **Patterns A–C** branch
     writes no resolution marker, and step 1 routes *already-structured* alternatives to it as a
     no-op, so an intact unmarked `bold_label` group survives to the probe → exit 1 → step 4 never
     writes → `decision_needed` never clears, on the single-decision common case under `ll-auto` /
     `autodev`. Part 5 now requires the A–C branch to write a `> **Selected:**` callout whenever
     structured blocks exist; Implementation Step 9 and assertion (c4) carry it.
  2. **The disambiguated rationale heading broke a second, stricter regex.** Round 3–5 specified
     `### Decision Rationale — <label>`, checked only against the lenient
     `_DECISION_RATIONALE_SECTION_MARKER_RE` (`:1326`). `_unapplied_decision` (`:1449`, the
     `format-check` gate) reads the **end-anchored** `_DECISION_RATIONALE_HEADING_RE` (`:1316`) at
     `:1466`; a suffix makes that search miss, `dr_start` falls back to end-of-section, the
     self-scan window widens, and decided issues risk new `unapplied_decision` false positives —
     while colliding with **BUG-3289**, which is changing that same function. The heading now stays
     literal and disambiguation moves into the subsection's first body line. Assertion (c5) guards
     it; the duplicate-H3 concern that motivated the suffix is inert to the detector, because
     part 1's section-level fallback fires only for single-group sections.
  3. **Part 3's (a)/(b) was itself an undecided decision point** — a literal `pick one` directive
     under `## Proposed Solution`, i.e. the `provisional_e` shape this issue is about, in a file
     with no `decision_needed` flag to gate it. Decided **(a)**: at most one `provisional_e` group
     per document, documented in the docstring and CLI reference. (b) is recorded as a follow-up on
     BUG-3287, whose shared-precedence-chain blast radius it belongs to.

- **Round 7 (2026-08-23)** — pre-implementation review against the tree *after* BUG-3287
  (`e16a0bd83`), BUG-3285 (`c25d6c85f`), BUG-3289 (`e3ffd49ce`), and BUG-3293 landed. Two
  ship-blocking corrections and four stale premises:
  1. **The prescribed `provisional_e` retirement marker did not suppress the probe.** Round 6
     specified `**RESOLVED — the shim.** **DECISION — pick one …**` and recorded it as verified
     `None`. Measured against the live tree: it still matches `provisional_e`.
     `_RESOLVED_QUESTION_MARKER_RE`'s three alternatives all require the bold run to **close
     immediately at `RESOLVED`**, and round 6 generalized from the measurement table's *bare*
     `**RESOLVED**` row to a decorated form that puts the em-dash and reason inside the bold run.
     Shipping it makes a `provisional_e` group unretirable — the exact permanent stall round 6 §1
     existed to prevent, reintroduced by the wording of its own fix. Corrected to
     `**RESOLVED** — the shim.` (verified `None`). Assertion (c6) was also wrong as written and
     would have failed, inviting a test-side "fix" that kept the broken marker. Also corrected for
     the record: the appended `> **Selected:**` form *does* suppress (via `_PREFERENCE_MARKER_RE`,
     windows being whitespace-normalized); round 6's reasons for rejecting it stand, but not the
     claim that only the prefix suppresses.
  2. **`decision_rules_numbered` (BUG-3293) is a sixth detection path outside the group model, and
     the new Phase 3 fall-through turned it into a fresh unearned clear.** Measured: on a document
     whose only decision surface is a Program Design → Decision Rules block, `check-decidable` exits
     0 (`count 2`) while `locate_unresolved_options` reports 0 and the group iterator would see
     nothing — so part 5's "zero unresolved groups → fall through to Phase 7b, which clears" fires
     and the flag clears with nothing scored and nothing annotated, which is strictly worse than
     today's behavior. New **part 4b** decides it: do not emit `decision_rules_numbered` groups
     (design rulings are not mutually exclusive alternatives, and emitting them would exit 1 on
     nearly every refined issue in this repo — a mass loop stall); narrow the Phase 3 fall-through
     instead. Assertion (c7) is the guard.
  3. **Case 2 is fixed.** BUG-3287 widened `_OPTION_PATTERNS[3]`; `- **(a) …**` now returns
     `count 2, bullet` (measured). The *Out of scope* "stays unfixed until it lands" line and round
     4's reason for downgrading the fixture to the bare `- (a) …` shape are both retired — the
     fixture goes back to the bold-wrapped shape.
  4. **Case 3's mechanism changed.** BUG-3287 made `locate_enumerable_options` run the directive
     probe alongside every tier win and attach `residual_directive`. The group iterator reads that
     field rather than building a second `_locate_directive_alternatives` call path.
  5. **BUG-3285's ordering conditional in *Scope Boundary* is moot** — it landed, and
     `_BOLD_OPTION_MARKER` is now shared between `_OPTION_PATTERNS[1]` and `_OPTION_HEADING_RE`. The
     phantom-block fixture is kept anyway, since the *grouping* rule is new code.
  6. **Three corrections that lived only in *Codebase Research Findings* are folded into the body**,
     where they will actually be read at implementation time: the exit-2 "deliberate divergence from
     `check_open_questions.py`" (BUG-3294 landed; all three probes now return 2), the 4-entry
     `_DIRECTIVE_ALTERNATIVES_SECTIONS` (5 entries since BUG-3293 added `Program Design`), and
     `LocatedOptions`' missing fifth field.

  Re-verified unchanged and still exact: the *Steps to Reproduce* repro (`count 3`, `bold_label`,
  `residual_directive: null`, no entry for the second decision point), `SKILL.md`'s Phase 7b
  (`:411-424`) and Phase 3b step 4 (`:313-321`) anchors, `assert_decision_cleared` at
  `resolve-decision.yaml:185`, the `fsm/evaluators.py:255-259` polarity, the Phase 3b A–C stall
  analysis (step 3 now at `:308-312` — A–C removes qualifiers and writes no marker; only Pattern D
  writes a callout), and `_SELECTED_CALLOUT_RE`'s line anchoring.

`confidence_score` and `outcome_confidence` in frontmatter predate round 7 — re-run
`/ll:confidence-check` before implementing rather than carrying them forward.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`; **updated 2026-08-23**): `_iter_decision_groups`'
default (`include_approximate_tiers=False`) mode reuses `_OPTION_HEADING_RE`-style matching for tier
grouping, which is the same mechanism [BUG-3285] documented as miscounting bold prose
(`**Option A evidence**:`) as a real option block.

**BUG-3285 has landed (`c25d6c85f`), so the ordering conditional is moot.** `_OPTION_HEADING_RE`'s
bold alternative and `_OPTION_PATTERNS[1]` now share one `_BOLD_OPTION_MARKER` fragment
(`issue_parser.py:2035`) encoding the rule "a bold run must close at the end of the option
identifier, not continue into prose", so the group iterator inherits the fix by construction.
**Keep the fixture anyway**: add a test combining real options with a bold-prose phantom block (the
ENH-2967/BUG-1484 shape) to confirm the group iterator's "maximal contiguous run of option blocks at
the same tier" rule does not merge a phantom into a real group — the shared fragment prevents the
*match*, but the grouping rule is new code and untested against that shape.

---

## Status

**Done** | Created: 2026-08-21 | Priority: P2

## Resolution

- **Action**: fix
- **Completed**: 2026-08-22
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_parser.py`: added `DecisionGroup`, `_iter_decision_groups`,
  `is_group_resolved`, `locate_unresolved_decisions` per Parts 1-3 — group-aware residual
  detection, opt-in `numbered`/`bullet` tier + Pattern E directive coverage
- `scripts/little_loops/cli/issues/check_unresolved_decisions.py` (new) +
  `cli/issues/__init__.py`: new `ll-issues check-unresolved-decisions` subcommand
  (exit 0/1/2 per Part 4)
- `skills/decide-issue/SKILL.md` + `reference.md`: Phase 3 sources `unresolved[0]` from the
  new probe with the `decision_rules_numbered` carve-out; Phase 3b step 3's A-C branch now
  writes a resolution callout and step 4 gates on the probe; Phase 7a idempotency is
  per-group with a per-tier marker-placement rule; Phase 7b gates the clear on the probe;
  Phase 9 reports residual groups. Extracted the Provisional Patterns A-D detail and the new
  marker-placement/exit-code tables into `reference.md` to stay under the 500-line cap
  (494 lines) — the "land the extraction as its own preparatory commit" note was folded into
  this same change instead, since the budget was only breached by this issue's own edits
- `scripts/little_loops/loops/oracles/resolve-decision.yaml`: new `check_residual_decision`
  state between `assert_decision_cleared` and the terminals, per Part 6
- `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/reference/COMMANDS.md`,
  `docs/guides/DECISIONS_LOG_GUIDE.md`: documented the new function/CLI and the now-conditional
  frontmatter clear
- `scripts/tests/test_issue_parser_unresolved.py::TestDecisionGroups` (17 tests),
  `scripts/tests/test_ll_issues_check_unresolved_decisions.py` (new, 8 subprocess tests),
  `scripts/tests/test_decide_issue_skill.py::TestBug3278DecisionGroupGating` (8 phase-text
  tests), `scripts/tests/test_builtin_loops.py::TestResolveDecisionOracle` (4 new FSM routing
  tests) — cover assertions (a), (b), (c), (c2), (c3), (c6), (c7), (d), (e) plus the
  provisional_e retirement/decorated-prefix/appended-callout guards and the
  Scope-Boundary phantom-block regression
- `scripts/tests/test_issue_parser.py`: re-anchored the pre-existing
  `TestPriorityRegexCompletenessAllowlist` line numbers (3335/3339/3360 → 3652/3656/3677),
  shifted by this issue's ~315-line parser insertion
- `.gemini/skills/decide-issue/`, `.kimi-code/skills/decide-issue/`,
  `.qwen/skills/decide-issue/`: regenerated via `ll-adapt --host <host> --apply` after the
  SKILL.md/reference.md edit

### Verification Results
- Tests: PASS (20174 passed, 20 skipped, full suite minus `-m "integration or conformance"`;
  one pre-existing, unrelated failure remains —
  `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` flags stale
  evidence citations in this issue's own `## Current Behavior` (lines 72/81, attributed to the
  already-landed BUG-3287) and in `P3-BUG-3296-...md`; reproduced identically with every change
  in this diff fully reverted, confirming it predates this fix and is out of this issue's scope)
- Lint: PASS (`ruff check` clean on all changed files)
- Format: PASS (`ruff format --diff` clean on all changed files)
- Types: PASS (`mypy scripts/little_loops/` clean)
- Loop validation: PASS (`ll-loop validate` on `resolve-decision.yaml`)
- TDD: Red confirmed retroactively — all 35 new tests fail against the pre-fix source
  (reverted via `git stash` and re-run), then pass after restoring the implementation



## Session Log
- `/ll:manage-issue` - 2026-08-23T03:55:00 - `f76f3255-c5a1-47a5-a256-fbcdf24c224e.jsonl`
- `/ll:confidence-check` - 2026-08-23T02:50:36 - `591b725f-a600-40d5-8bf6-26baeac94edd.jsonl`
- `/ll:confidence-check` - 2026-08-23T02:24:03 - `6e6bb8a8-074e-4384-a442-4dd63e0ec57e.jsonl`
- `/ll:refine-issue` - 2026-08-23T02:12:16 - `d4c69d5a-08a6-4fc3-8ad7-d7b1686ad66e.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-22T22:30:44 - `6b7204fa-1e9c-4b22-a304-4114c03357f8.jsonl`
- `/ll:format-issue` - 2026-08-22T20:15:07 - `918913f6-1ede-43d4-b1f7-bffea0db90c5.jsonl`
- `/ll:confidence-check` - 2026-08-21T19:12:09 - `e7bfa83a-61b5-42db-9234-b883edce75e7.jsonl`
- `/ll:confidence-check` - 2026-08-21T19:00:59 - `de2bc4f7-6272-4f52-a9cb-998af08752f1.jsonl`
- `/ll:confidence-check` - 2026-08-21T18:01:01 - `e8b100f2-1d69-4959-840b-2aa9aba3993f.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T17:52:59 - `f27d8342-f3ba-42ea-95ca-41ad79008fbf.jsonl`
- `/ll:confidence-check` - 2026-08-21T17:26:19 - `ce6fc8e8-cc01-4d82-ba15-c569a3c2657d.jsonl`
- `/ll:confidence-check` - 2026-08-21T16:52:46 - `91b7dacc-e5dd-41ec-9252-2284552631e6.jsonl`
- `/ll:verify-issues` - 2026-08-21T16:50:38 - `b6e0cd40-ff6f-484a-a070-a4c057b6b4f8.jsonl`
- `/ll:refine-issue` - 2026-08-21T16:48:30 - `fb9d04b2-a23d-41ad-9b4a-d9a452640591.jsonl`
- `/ll:verify-issues` - 2026-08-21T16:45:11 - `71fe2fbf-5037-422a-b792-43cf783f0126.jsonl`
- `/ll:wire-issue` - 2026-08-21T16:42:04 - `e1da28b6-9797-4d9b-9987-730277c774fa.jsonl`
- `/ll:refine-issue` - 2026-08-21T16:33:13 - `dbfc3839-1d83-4abb-b43c-9cdd5a2e4d6a.jsonl`
- `/ll:capture-issue` - 2026-08-21T15:46:43 - `da526826-2179-460f-b823-35695378ac55.jsonl`
