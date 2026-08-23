---
id: BUG-3287
type: BUG
title: locate_enumerable_options lets a tier match preempt Pattern E, and its bullet
  tier cannot see bold-wrapped markers
priority: P2
status: done
parent: EPIC-3290
discovered_by: bug-3278-pre-implementation-review
discovered_date: '2026-08-21'
captured_at: '2026-08-21T19:30:00Z'
completed_at: '2026-08-23T00:57:43Z'
verify_verdict: VALID
labels:
- issue-parser
- decide-issue
- decision-needed
- pipeline
relates_to:
- BUG-3278
- BUG-3279
- BUG-3285
size: Very Large
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# BUG-3287: locate_enumerable_options lets a tier match preempt Pattern E, and its bullet tier cannot see bold-wrapped markers

## Summary

`locate_enumerable_options` (`issue_parser.py:2391`) resolves a document to **one** option set by
running `_OPTION_PATTERNS` tiers 1–4 first, then the `decision_rules_numbered` structural heuristic,
and falling back to the Pattern E directive heuristic `_locate_directive_alternatives` (`:2231`)
only when **every earlier stage misses document-wide**. Two defects follow from that chain:

1. **Pattern E preemption (live today).** Any tier match anywhere in the resolved section hides a
   co-located prose decision directive. Measured over the live `.issues/` corpus: **7 issues** carry
   a Pattern E directive that a tier match preempts right now, with no code change required.

> ⚠ **Restated 2026-08-22 — the chain has five stages, not four.** BUG-3293 landed
> `_locate_decision_rules_numbered` (`issue_parser.py:2349`, `pattern: "decision_rules_numbered"`)
> between the whole-document H2 sweep and the directive probe (`:2440-2446`) *after* this issue was
> written. Every "all four tiers miss" phrasing in the original body was stale and is corrected
> throughout. Measured impact on this issue: **none forced** — 3 corpus files resolve to
> `decision_rules_numbered`, **0** are preempted by a tier, and **0** preempt a directive. See
> § *Scope boundary — `decision_rules_numbered`*.
2. **The `bullet` tier cannot match a bold-wrapped marker.** `_OPTION_PATTERNS[3]` requires the
   `(a)` marker to sit immediately after the dash, so `- **(a) Make the override real.**` — the
   idiomatic option shape in this repo's issues — matches **zero** tiers. It is not out-competed;
   it is unreachable.

Split out of BUG-3278 at pre-implementation review. BUG-3278 fixes both defects *inside its own
new group iterator* (which probes directives in addition to tiers, under
`include_approximate_tiers=True`); this issue fixes them in the shared precedence chain that
`check-decidable`, `locate-options`, `count_enumerable_options`, and `/ll:decide-issue` Phase 2.5
all sit on. The two are independent — neither blocks the other.

## Current Behavior

`locate_enumerable_options` walks sections in precedence order (`## Proposed Solution`, then
`_OPTION_FALLBACK_SECTIONS`, then a whole-document H2 sweep keeping the highest-count section),
handing each section body to `_locate_options_in_text` (`:2100`), which **returns on the first
`_OPTION_PATTERNS` tier with ≥1 match**. Only when all of that misses does the chain try
`_locate_decision_rules_numbered` (`:2349`, BUG-3293), and only when *that* also misses does it
reach `_locate_directive_alternatives` (`:2231`).

### Defect 1 — a tier match preempts a Pattern E directive

Because the directive probe is a *fallback* rather than an *additional* probe, a document holding
both an enumerated option set and a separate prose decision directive reports only the former.
Reproduced over the live corpus:

```python
import pathlib
from little_loops.issue_parser import locate_enumerable_options, _locate_directive_alternatives
for p in pathlib.Path('.issues').rglob('*.md'):
    c = p.read_text()
    loc, d = locate_enumerable_options(c), _locate_directive_alternatives(c)
    if d is not None and loc.pattern not in (None, 'provisional_e'):
        print(p.name, loc.count, loc.pattern, '| hidden directive in', d.heading, 'line', d.options[0].start_line)
```

Seven live issues (re-measured 2026-08-22):

| Issue | Reported | Hidden directive |
|---|---|---|
| BUG-1183 | `count 2`, `bold_label` | `## Proposed Solution`, line 56 |
| ENH-2446 | `count 2`, `bullet` | `## Proposed Solution`, line 123 |
| ENH-2873 | `count 2`, `bold_label` | `## Proposed Change`, line 84 |
| **ENH-3277** | `count 3`, `bold_label` | `## Proposed Solution`, line 378 |
| ENH-2239 | `count 2`, `bold_label` | `## Scope Boundaries`, line 49 |
| ENH-3275 | `count 2`, `section_header` | `## Proposed Solution`, line 73 |
| FEAT-2339 | `count 2`, `bold_label` | `## Proposed Solution`, line 128 |

> ⚠ **Re-measured 2026-08-22 — six became seven.** `ENH-3277` is new since this issue was written
> and BUG-1183's directive moved line 55 → 56. **The set is live corpus state, not a fixture**: do
> not encode the cardinality in a test. Pin by ID and assert the known set is a *subset* of what the
> probe reports — see § *Tests*.

`/ll:decide-issue` Phase 3 scores the tier options, Phase 7b clears `decision_needed`, and the
directive is never surfaced.

### Defect 2 — the bullet tier cannot see a bold-wrapped marker

```python
from little_loops.issue_parser import _OPTION_PATTERNS
s = "- **(a) Make the documented override real.**"
[i for i, p in enumerate(_OPTION_PATTERNS) if p.search(s)]   # -> []  (no tier matches)
```

`_OPTION_PATTERNS[3]` is `r"^[-*]\s+(?:\([a-z0-9]\)\s+|\*{0,2}Option\s+[A-Za-z0-9])"` — the
`\*{0,2}` bold-tolerance applies only to the `Option X` alternative, never to the `(a)` marker,
and the marker alternative additionally requires `\s+` after the closing paren.

Consequence: `check-decidable` reports such a document as having nothing to decide, routing
`resolve-decision.yaml`'s `check_decision_decidable` (`:47-67`) to `refine` instead of `decide`.

## Steps to Reproduce

**Defect 1** (no fixture needed — reproduces on committed files):

1. Run the corpus script above against `.issues/`.
2. Observe six issues where `_locate_directive_alternatives` finds a directive that
   `locate_enumerable_options` does not report.
3. `ll-issues locate-options ENH-2446 --json` → `pattern: "bullet"`, no mention of the
   `## Proposed Solution` directive at line 123.

**Defect 2**:

1. Author an issue whose `## Proposed Solution` holds only `- **(a) …**` / `- **(b) …**` bullets.
2. `ll-issues locate-options <ID> --json` → `count 0`, `pattern: null`.
3. `ll-issues check-decidable <ID>` → exit 1 ("nothing to decide"), despite a decision being
   plainly present.

## Expected Behavior

- A Pattern E directive is reported even when a tier also matches — the document holds two decision
  points and the precedence chain must not silently pick one.
- A bold-wrapped `- **(a) …**` marker matches the `bullet` tier.
- No document that matches a tier today stops matching, and no document's reported `count` drops
  **except `BUG-3229`**, whose `provisional_e` result is superseded by a `bullet`-tier match
  (`2 → 1`) while the directive it held moves to `residual_directive`. That drop is intended and
  pinned; what must not happen is the drop reaching Phase 3's `count == 1` clear branch.
  > ⚠ **Amended 2026-08-21.** The unqualified form of this clause was measurably false under the
  > settled Option B — see § *Ordering constraint*. Stating it as an absolute is what let the
  > required corpus differential be specified with an assertion that fails on landing.
- Three further documents keep their `count` but change their **resolved section**: ENH-3264,
  ENH-2164, ENH-2358. Intended and pinned — see § *Blast radius*.
  > ⚠ **Added 2026-08-22.** The `heading`-stability half of this contract was never stated here,
  > only the `count` half, which is why two of the three section-movers went unnoticed until the
  > corpus was re-measured.

## Motivation

Both defects hide decision points from the deterministic layer that FSM loops gate on. Defect 1 is
live on six committed issues; defect 2 makes the repo's own idiomatic option shape invisible to
`check-decidable`, so a decidable issue takes a pointless `/ll:refine-issue` detour and, in the
worst case, has `decision_needed` cleared against an option set that was never seen.

This is also the precondition for BUG-3278's coverage to be complete: BUG-3278's group iterator
fixes both defects for its own new probe, but leaves the shared chain — and therefore
`check-decidable`, Phase 2.5, and `count_enumerable_options` — untouched.

## Proposed Solution

Two parts. **Part 1 must land with or before part 2** — part 2 materially widens part 1's blast
radius, and shipping part 2 alone introduces a new false-clear (see *Ordering constraint*).

### Part 1 — probe directives in addition to tiers

In `locate_enumerable_options`, call `_locate_directive_alternatives` alongside the tier scan
rather than only after it. When both produce a result, the returned `LocatedOptions` must express
both. Two viable shapes; pin one during implementation (**settled: Option B** — see
§ *Decision Rules*):

- **Merge** — return the tier result with the directive's `LocatedOption` appended and
  `pattern` set to the tier name, `count` incremented. Cheapest, but `pattern` then lies about one
  of the entries.
- **Precedence-preserving with a flag** — return the tier result unchanged plus a new
  `residual_directive: LocatedOptions | None` field on `LocatedOptions`. Keeps `count`/`pattern`
  contracts byte-identical for every existing consumer, and gives Phase 3 / `check-decidable`
  something explicit to branch on. **Recommended** — the `count` field feeds
  `/ll:decide-issue` Phase 3's `count == 1` branch (which clears `decision_needed` outright), so
  mutating `count` is the higher-risk shape.

> **Option B is inert without the consumer edits below — this is not optional polish.**
> Verified 2026-08-21, re-verified 2026-08-22: `cmd_check_decidable`
> (`cli/issues/check_decidable.py:36`) reads only
> `located.count`, and `LocatedOptions.to_dict()` (`issue_parser.py:2072-2078`) serializes only
> `count` / `pattern` / `heading` / `options`. A `residual_directive` field that no consumer reads
> and `--json` does not emit leaves the output for all six preempted issues **byte-identical**, so
> defect 1 would be *made available* rather than fixed and this issue's own *Expected Behavior*
> ("A Pattern E directive is reported even when a tier also matches") would be met by nothing.
> Option A does not have this problem — it moves `count`, which every consumer already reads — which
> is the honest cost of preferring Option B. Parts 1a–1c below are what make Option B equivalent.

### Part 1a — serialize the field

Add `"residual_directive": self.residual_directive.to_dict() if self.residual_directive else None`
to `LocatedOptions.to_dict()` (`issue_parser.py:2072`). This is a **new top-level key** in
`ll-issues locate-options --json`. `test_issues_locate_options.py:94` asserts exact key sets only
per-*option* (`{"label", "text", "start_line", "end_line"}`), which is unchanged, so no existing
assertion breaks — but re-check before landing.

Because the field is a `LocatedOptions` (see the type correction below), the serialized value is a
**nested `count`/`pattern`/`heading`/`options` object** — not a bare option dict — with `pattern`
always `"provisional_e"`. `LocatedOptions.to_dict()` therefore recurses into itself one level;
guard against unbounded nesting by leaving `residual_directive` unset on the directive result
itself (it is constructed by `_locate_directive_alternatives`, which never populates the field).
`docs/reference/CLI.md`'s `locate-options` payload description must show the nested shape.

> ⚠ **Type corrected 2026-08-21 (epic review) — the field is `LocatedOptions | None`, not
> `LocatedOption | None`.** Every earlier statement of this field in this issue said
> `LocatedOption` (singular). That is wrong at the source: `_locate_directive_alternatives`
> returns **`LocatedOptions | None`** (`issue_parser.py:2231`), a container carrying the
> directive's `heading` and `count`. Measured on a directive document:
> `(count 2, pattern 'provisional_e', heading 'Proposed Solution')`. Assigning that to a singular
> `LocatedOption` discards the **heading**, which part 1b requires in order to name the directive
> in `check-decidable`'s output — `LocatedOption` has no `heading` field at all
> (`label`/`text`/`start_line`/`end_line`, `issue_parser.py:2041-2055`). The corpus script in
> § *Current Behavior* already reads the probe as a container (`d.heading`,
> `d.options[0].start_line`); the dataclass field must match it.
>
> ⚠ **Second stated reason retracted 2026-08-22.** This note previously also claimed the container
> preserves "the **second alternative** … keeping only `options[0]` reports that a decision exists
> while hiding what it is between." **That is false.** `_locate_directive_alternatives` returns
> `count=2` with **exactly one** `LocatedOption` — the matched window — and never separates the
> alternatives; this is explicit in its own docstring (`issue_parser.py:2246-2252`: *"`options`
> holds a single `LocatedOption` spanning the matched window — the individual 'X' / 'Y'
> alternatives are not separated out"*). Measured across the corpus: **all 18** directive matches
> are `(count == 2, len(options) == 1)`. The conclusion (use `LocatedOptions`) stands on the
> `heading` argument alone. This retraction matters because a test was written against the false
> reason — see § *Tests → Directive-shape guard*.

### Part 1b — teach `check-decidable` to *report* it

`cmd_check_decidable` (`cli/issues/check_decidable.py:19-61`) gates on `located.count >= 1` at
`:36`. **Leave the gate alone.** Append the residual directive to the success line when one is
present, e.g.:

```
Decidable: ENH-2446 has 2 enumerable option(s) in 'Proposed Solution'
  + residual decision directive in 'Proposed Solution' (line 123) — not counted
```

> ⚠ **Rescoped 2026-08-22 — the originally specified gate change is unreachable dead code.**
> This part previously read: *"Change to `located.count >= 1 or located.residual_directive is not
> None` … without this, a document whose only decision point is a preempted directive still routes
> `resolve-decision.yaml:47-67` to `refine`."* Both halves are wrong, structurally:
>
> Under Option B, `residual_directive` is populated **only when a tier already fired** — that is the
> shape's defining property. So `count >= 1` is *always* true wherever `residual_directive` is
> non-null, and the `or` clause can never change an exit code. Measured over `.issues/` against a
> prototype of part 1: **7** documents receive a `residual_directive`, **0** of them with
> `count == 0`. There is no such thing as "a document whose only decision point is a preempted
> directive that `check-decidable` rejects" — if the directive is preempted, the preempting tier
> match is itself ≥1 option, and the document is already `decidable` today.
>
> The reporting change is what makes the field observable at this CLI, and it is not dead. The
> consequence for verification is larger and is handled in § *Tests*: the "Option B end-to-end
> guard" specified there **passes unmodified against today's tree** and proves nothing.

### Part 1c — state what Phase 2.5 / Phase 3 do with it

`skills/decide-issue/SKILL.md` Phase 2.5 (`:110-146`) and Phase 3 (`:160-190`) consume
`locate-options --json`. Minimum viable change: Phase 3 must **not** silently drop a
`residual_directive` when the tier options are scored. Pin one of:

- **surface-only** — Phase 3 scores the tier options as today and Phase 9 reports
  `⚠ residual decision directive at <heading>:<line> — not scored this run`. Cheapest, keeps this
  issue out of the decision-model layer.
- **defer to BUG-3278** — the decision-*group* model there already represents "two decision points
  in one document" properly, and its `check-unresolved-decisions` probe would hold
  `decision_needed: true` until both resolve.

~~**Recommended: surface-only**, with the group model as the real fix.~~ Scoring a directive
alongside tier options is BUG-3278's problem, and duplicating it here would be the
private-copy-of-the-fix failure this issue was split out to prevent. But *silence* is not
acceptable: a directive that `check-decidable` now counts as decidable and Phase 3 never mentions
is a worse state than today, because `decision_needed` gets cleared with the directive still open
and nothing in the report says so.

> ⚠ **Recommendation flipped to `defer to BUG-3278` — 2026-08-21.** Two reasons, neither available
> when surface-only was chosen:
>
> 1. **Surface-only is dead on arrival.** BUG-3278 part 5 re-points Phase 3 off
>    `locate-options --json` onto `check-unresolved-decisions`, whose group iterator already probes
>    `_locate_directive_alternatives` *in addition to* tiers under `include_approximate_tiers=True`.
>    Once that lands, `residual_directive` has exactly one remaining consumer — `check-decidable`
>    (part 1b) — and any Phase 3 prose written here is orphaned. On the epic's sequencing
>    (BUG-3287 → BUG-3278) that is one issue's lifetime.
> 2. **It cannot pay for itself against the SKILL.md line budget.** `skills/decide-issue/SKILL.md`
>    is **495 lines** against a hard 500-line cap (`TestSkillLineLimit`,
>    `scripts/tests/test_enh494_skill_companions.py:73-86`), and three children write to it. Spending
>    part of a 7-line budget on a rule with a one-issue lifetime is the worst available trade. See
>    EPIC-3290 § *Shared constraint — the decide-issue SKILL.md line budget*.
>
> **What this issue still owes**, since "defer" must not mean "drop" — silence is the failure mode
> named in the paragraph above:
>
> - **Parts 1a and 1b remain required and unchanged.** They are what make the defect observably
>   fixed; deferring 1c does not weaken the Option B end-to-end guard under *Tests*.
> - **One line, not a phase**: add to Phase 3's existing `count == 1` branch the guard
>   `residual_directive is None`, so the branch cannot clear `decision_needed` on a document that
>   still holds a preempted directive. This is the *Ordering constraint* correction above, and it is
>   a condition on an existing sentence rather than new prose — it fits the budget.
> - **BUG-3278 inherits the reporting obligation.** Recorded in that issue's part 5 as a required
>   carry-forward; without that note the rule is silently dropped at the Phase 3 rewrite rather than
>   deliberately deferred.

### Part 2 — widen `_OPTION_PATTERNS[3]`

```python
r"^[-*]\s+\*{0,2}(?:\([a-z0-9]\)\s*|Option\s+[A-Za-z0-9])"   # MULTILINE | IGNORECASE
```

Hoists `\*{0,2}` out of the `Option` alternative so it covers the `(a)` marker too, and relaxes
the post-marker `\s+` to `\s*`.

> ⚠ **Added 2026-08-22 (pre-implementation review 2) — widen `_extract_option_label` in the same
> step.** The label-stripping regex (`issue_parser.py:2094`,
> `^[-*]\s*(?:\([a-z0-9]\)\s*)?`) does not tolerate a bold wrapper before the marker, so the
> newly-reachable shapes get asymmetric labels. Measured: `- (a) foo` → `label ''` today, while
> `- **(a) foo**` → `label '(a)'` after part 2 — the `**` blocks the marker-stripping group, and
> the later `strip("*")` removes only the asterisks, leaving the marker. Cosmetic, but it surfaces
> in `locate-options --json` `options[].label`. Apply the same hoist there —
> `^[-*]\s*\*{0,2}(?:\([a-z0-9]\)\s*)?` — and pin both shapes' labels in the part 2 tests.

### Ordering constraint

Part 2 without part 1 **introduces a new false-clear**. Verified against BUG-3229:

| | `count` | `pattern` | section |
|---|---|---|---|
| today | 2 | `provisional_e` | Proposed Solution |
| part 2 alone | **1** | `bullet` (label `(i)`) | Proposed Solution |

A stray `- (i)` bullet becomes a tier-4 match, preempts the real 2-alternative directive, and
collapses the result to `count 1` — which is `/ll:decide-issue` Phase 3's *"Only one option present
— no decision required. Clearing `decision_needed` if set"* branch (`SKILL.md:187`).

> ⚠ **Corrected 2026-08-21 — this paragraph previously ended *"Part 1 keeps the directive visible,
> so the count does not collapse."* That is true of Option A only, and this issue recommends
> Option B.** Re-measured live:
>
> ```
> BUG-3229 today:       count 2, provisional_e, §Proposed Solution
> BUG-3229 + part 2:    count 1, bullet,        §Proposed Solution
> directive still found: count 2, §Proposed Solution
> ```
>
> Under **Option B** part 1 leaves `count`/`pattern` *byte-identical to the tier result* by
> construction — that is the entire point of the shape — so `count` still collapses **2 → 1** and
> the directive lands on a separate field the branch does not read. Phase 3 still takes the
> `count == 1` clear branch, and `decision_needed` is still cleared with the directive open.
> Part 1 as specified does **not** discharge the ordering constraint.
>
> **Two consequences, both now folded into this issue:**
>
> 1. **Part 1c's surface-only shape is insufficient** — a Phase 9 warning does not stop a Phase 3
>    write. The `count == 1` branch must additionally gate on `residual_directive is None`, or the
>    return shape must be Option A. See § *Decision Rules → Cost correction 2*.
> 2. **The required corpus differential fails as written** — its assertion is *"no file's `count`
>    decreases"*, and BUG-3229 decreases 2 → 1 under Option B + part 2. It needs BUG-3285's escape
>    hatch (*"except those pinned as intended"*). See § *Tests*.

### Blast radius

Measured by applying part 2 to every file in `.issues/` and diffing `locate_enumerable_options`
output: **22 of the live corpus change** (re-measured 2026-08-22 — total unchanged, breakdown
corrected). **Six** have a non-zero baseline, and **four** of those change in ways a regex-level
superset check does not predict, because tier precedence and *section* precedence both shift:

| Issue | Before | After | Why it matters |
|---|---|---|---|
| BUG-3229 | `2`, `provisional_e`, §Proposed Solution | `1`, `bullet`, §Proposed Solution | count **drops**; hits the `count == 1` clear branch. **Part 1 does not prevent this under Option B** — see § *Ordering constraint*; the `residual_directive is None` guard on that branch is what prevents it |
| ENH-3264 | `1`, `numbered`, §Confidence Check Notes | `2`, `bullet`, §**Proposed Solution** | the winning **section** changes, not just the tier |
| **ENH-2164** | `1`, `numbered`, §Reopened | `3`, `bullet`, §**Relationship to ENH-2165, rn-remediate, and Conjunctive Rules** | section change; the winning H2 is not even a canonical options section |
| **ENH-2358** | `2`, `numbered`, §Implementation Steps | `3`, `bullet`, §**Expected Behavior** | section change |
| FEAT-2332 | `3`, `bullet`, §Proposed Solution | `6`, `bullet`, §Proposed Solution | count rises, section stable — benign |
| FEAT-2447 | `1`, `bullet`, §Integration Map | `4`, `bullet`, §Integration Map | count rises, section stable — benign |

The remaining **16** are `count 0 → N`, `pattern null → bullet` — the intended correction.

> ⚠ **Corrected 2026-08-22 — the original breakdown was wrong in two ways.** It named only
> BUG-3229 and ENH-3264 as unpredicted, and said *"the remaining 20 are `count 0 → N`"*. Re-measured:
> **ENH-2164** and **ENH-2358** also change their resolved `heading`, and the `0 → N` group is
> **16**, not 20. This is not cosmetic: § *Tests* pins the corpus differential's exception list to
> the documented set, so as written the required test **fails on two files this issue never named**.
> All four heading-movers must be pinned. FEAT-2332 and FEAT-2447 need no pin — a `count` *increase*
> with a stable heading is exactly what the assertion permits.

Affected consumers:

- `ll-issues check-decidable` (`cli/issues/check_decidable.py:19-52`) — only tests `count >= 1`, so
  `0 → N` flips it to decidable and `2 → 1` is inert. Live routing change in
  `resolve-decision.yaml:47-67` (`refine` → `decide`).
- `ll-issues locate-options` — `count`/`pattern`/`heading` all move on the 22.
- `count_enumerable_options` — scoring/gap heuristics; "no options" documents become "has options".
- `/ll:decide-issue` Phase 2.5 (`SKILL.md:110-146`) — fewer `OPTIONS_MISSING` exits.

### Verified match matrix (part 2)

Strict superset at the regex level — every previously-matching shape still matches:

| Shape | today | after |
|---|---|---|
| `- (a) foo` | ✓ | ✓ |
| `* Option B: x` | ✓ | ✓ |
| `- **Option B** x` | ✓ | ✓ |
| `- **(a) foo**` | ✗ | **✓** |
| `- *(a)* foo` | ✗ | **✓** |
| `- (a)foo` | ✗ | **✓** |
| `- (a): text` | ✗ | **✓** |
| `- (a)` | ✗ | **✓** |
| `- some bullet` | ✗ | ✗ |
| `- optional extras` | ✗ | ✗ |
| `- **Options** are` | ✗ | ✗ |
| `1. (a) foo` | ✗ | ✗ |
| `  - (a) indented` | ✗ | ✗ |
| `-(a) foo` | ✗ | ✗ |
| `- ***(a)*** foo` | ✗ | ✗ |

Note the last four newly-matching rows come from the `\s+`→`\s*` relaxation, not the bold
widening. A bare `- (a)` in unrelated prose is now a `bullet`-tier match — intended (a marker-only
bullet is still an option label), but it is why the corpus differential below is a required test,
not an optional one.

> **Matrix re-verified 2026-08-22: 14/14 rows exact, no corrections.** The final row
> (`- ***(a)*** foo`, bold-italic) is **added as an explicit non-goal** — `\*{0,2}` caps at two
> asterisks, so a triple-marker bullet still misses. Pinning it as ✗/✗ keeps a later reader from
> "fixing" it into `\*{0,3}` without re-running the corpus differential.

### Scope boundary — `decision_rules_numbered`

Part 1 makes the directive an *additional* probe alongside the four `_OPTION_PATTERNS` tiers. It
does **not** do the same for `_locate_decision_rules_numbered` (BUG-3293, the fifth stage), and the
directive probe is **not** attached to a `decision_rules_numbered` result. Justification, measured
2026-08-22 over the full `.issues/` corpus:

- files resolving to `decision_rules_numbered`: **3**
- files where a tier match preempts an available `decision_rules_numbered` match: **0**
- files where a `decision_rules_numbered` result preempts an available directive: **0**
- files where part 2 changes a `decision_rules_numbered` resolution: **0**

So the symmetric widening has no live effect and is deferred. **Implementation requirement**: the
restructured `locate_enumerable_options` must set `residual_directive = None` on a
`decision_rules_numbered` result explicitly, not by omission, so the choice is legible at the call
site rather than an accident of control flow.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `locate_enumerable_options` directive-probe ordering
  (+ `LocatedOptions.residual_directive: LocatedOptions | None` if the recommended shape is taken —
  **plural**, see part 1a's type correction), `_OPTION_PATTERNS[3]`
- `scripts/little_loops/issue_parser.py` — `LocatedOptions.to_dict()` (`:2072-2078`), which must
  emit `residual_directive` or the field is invisible to `locate-options --json` (part 1a).
  **Required under Option B, not optional** — this is now the *only* edit that makes the field
  externally observable
- `scripts/little_loops/issue_parser.py` — `_extract_option_label` (`:2090-2097`) gains the same
  `\*{0,2}` hoist so bold-wrapped markers strip to the same labels as plain ones (added 2026-08-22,
  pre-implementation review 2 — see § *Part 2*)
- `scripts/little_loops/cli/issues/locate_options.py` — one human-readable line naming the
  residual directive when present, for parity with part 1b's `check-decidable` line; without it
  the non-`--json` path silently omits what the JSON payload carries (added 2026-08-22; promoted
  from *Dependent Files*)
- `scripts/little_loops/cli/issues/check_decidable.py` — the success-line `print(` at `:37-40`
  gains a residual-directive line (part 1b). **The `located.count >= 1` gate at `:36` is
  unchanged.**
  > ⚠ **Rescoped 2026-08-22.** Previously *"the gate at `:35` gains `or
  > located.residual_directive is not None`"*. That clause is unreachable — see § *Part 1b*. Two
  > anchor corrections in the same line: the gate is at **`:36`**, not `:35`, and the file now
  > returns **2** for an unresolvable issue ID (BUG-3294), so it is no longer the two-outcome gate
  > this issue described.
- `skills/decide-issue/SKILL.md` — Phase 3's `count == 1` branch (`:187`) gains the
  `residual_directive is None` guard. **Required under Option B** — it is what closes the
  ordering-constraint hole; see § *Decision Rules → Cost correction 2*.
  > ⚠ **Rescoped 2026-08-21.** Previously *"Phase 3 must report a `residual_directive` it does not
  > score (part 1c, surface-only shape)"*. Part 1c is **deferred to BUG-3278**; only the one-line
  > branch guard stays here.
  >
  > **Line budget.** `SKILL.md` is **495 lines** against a hard **500-line** cap enforced by
  > `TestSkillLineLimit` (`scripts/tests/test_enh494_skill_companions.py:73-86`), and BUG-3278 and
  > ENH-3280 also write to this file. This issue's share is **≤ 2 lines** — a condition appended to
  > an existing sentence, not a new paragraph. If the edit does not fit in two lines, extract to
  > `skills/decide-issue/reference.md` per EPIC-3290 § *Shared constraint — the decide-issue
  > SKILL.md line budget* rather than spending the shared headroom.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/check_decidable.py:19-61` — `count >= 1` gate at `:36`
  > ⚠ Promoted to *Files to Modify* under Option B — see part 1b (reporting only; the gate itself
  > does not change). Range corrected `:19-52` → `:19-61` (BUG-3294 grew the function).
- `scripts/little_loops/cli/issues/locate_options.py:19-51` — `--json` payload
  > ⚠ Promoted to *Files to Modify* 2026-08-22 — gains a human-readable residual-directive parity
  > line (pre-implementation review 2)
- `scripts/little_loops/issues/fold_research_findings.py:178` — prose reference to
  `count_enumerable_options`
- `scripts/little_loops/loops/oracles/resolve-decision.yaml:47-67` (`check_decision_decidable`)
- `skills/decide-issue/SKILL.md:110-146` (Phase 2.5), `:160-190` (Phase 3 extraction + the
  `count == 1` branch at `:187`)
- `commands/refine-issue.md:524` — cites `count_enumerable_options()`/`count_unresolved_options()`

### Similar Patterns

- `locate_unresolved_options` (`issue_parser.py:2532`) mirrors the same *section* precedence but
  its own block iterator; it does **not** read `_OPTION_PATTERNS` and is unaffected by part 2
  (anchor `:2240` corrected 2026-08-22)

### Tests

- `scripts/tests/test_issue_parser_unresolved.py` — the match matrix above as a table-driven case;
  a new `TestDirectiveNotPreempted` covering a document with both a tier match and a directive
- **Corpus differential (required):** a test that applies `locate_enumerable_options` across
  `.issues/` and asserts no file's `count` decreases and no file's resolved `heading` changes,
  **except for files pinned as intended changes.** This is the only check that would have caught
  BUG-3229, ENH-3264, ENH-2164 and ENH-2358; the 14-shape regex matrix passes all four.
  > ⚠ **Escape hatch added 2026-08-21; pinned list corrected 2026-08-22 — it named two of the four
  > files that actually move.** Pin exactly these **four**, by ID, with the expected before/after in
  > the test docstring — a bare `!=` allowance would let the next regression through silently:
  >
  > | ID | Pinned change |
  > |---|---|
  > | BUG-3229 | `count` 2 → 1, `provisional_e` → `bullet`, §Proposed Solution (stable) |
  > | ENH-3264 | `heading` §Confidence Check Notes → §Proposed Solution |
  > | ENH-2164 | `heading` §Reopened → §Relationship to ENH-2165, rn-remediate, and Conjunctive Rules |
  > | ENH-2358 | `heading` §Implementation Steps → §Expected Behavior |
  >
  > FEAT-2332 (`3 → 6`) and FEAT-2447 (`1 → 4`) are **not** pinned — a `count` increase with a
  > stable heading is what the assertion already permits. Follow BUG-3285's phrasing of the same
  > test (*"no file's `count` moves except those pinned as intended"*).
  > Scaffolding model: `TestUnappliedDecisionLiveCorpusSweep`
  > (`scripts/tests/test_issue_parser.py:5563`, `test_corpus_sweep_does_not_crash` at `:5585`) —
  > skip-if-corpus-absent, `Path(__file__).resolve().parents[2]`, `rglob("*.md")`.
  > (Anchors re-corrected 2026-08-22 from `:5063`/`:5085`.)
  >
  > ⚠ **Mechanism + persistence specified 2026-08-22 (pre-implementation review 2).** Two things
  > this bullet left open:
  >
  > 1. **The "before" side needs an explicit mechanism** — no stored baseline exists (per
  >    § *Codebase Research Findings*, neither corpus-sweep precedent diffs against a prior run).
  >    The only in-run form is: keep the **old tier-3 regex as a literal in the test**, monkeypatch
  >    it into `_OPTION_PATTERNS[3]`, sweep the corpus, then sweep again with the live code, and
  >    diff per file. State this in the test docstring so the literal isn't later "cleaned up" into
  >    a reference to the live pattern — which would make the test vacuously self-comparing.
  > 2. **The live-corpus form is a landing gate, not a permanent suite member.** Any future issue
  >    file whose shape makes it a new mover (a stray `- (a)` bullet outranking a numbered list)
  >    would fail the suite on an unrelated commit, and the four pinned files are live documents
  >    this very pipeline edits. Run the live-corpus differential at Implementation Steps 3/6 to
  >    certify the landing; persist the regression on **frozen fixture copies** (the four movers,
  >    2–3 of the preempted seven, one `0 → N` sample) under `scripts/tests/`, and keep any
  >    permanent live-corpus sweep to content-independent invariants (crash safety; the directive
  >    `(count 2, len(options) 1)` shape) per the codebase's existing corpus-test style.
- `scripts/tests/test_issues_locate_options.py` — a case asserting `- **(a) …**` reports
  `pattern: "bullet"`
- `scripts/tests/test_ll_issues_check_decidable.py` — a case asserting the same document is
  decidable, and one asserting a tier+directive document still reports the directive
- **Observability guard (required) — replaces the "Option B end-to-end guard":** a
  `locate-options --json` case over a document holding both a tier match and a directive, asserting
  the payload carries a non-null top-level `residual_directive`. Plus a `check-decidable` case
  asserting the success line **names** the residual directive. These two are what fail if part 1a /
  part 1b are skipped.
  > ⚠ **Replaced 2026-08-22 — the guard as originally specified is vacuous.** It read: *"a document
  > whose only decision point is a tier-preempted directive — assert `ll-issues check-decidable`
  > **exits 0** … the assertion that fails if parts 1a/1b are skipped, and the only one that
  > distinguishes 'the field exists' from 'the defect is fixed.'"* **That test passes against
  > today's unmodified tree.** A preempted directive means a tier fired, a fired tier means
  > `count >= 1`, and `count >= 1` already exits 0. It cannot fail before the change, so it cannot
  > witness the change. Implementation Step 2's instruction to *"confirm it fails against step 1
  > alone"* was unsatisfiable. See § *Part 1b* for the structural argument and the 7/0 measurement.
- **Directive-shape guard (required, added 2026-08-21; assertion corrected 2026-08-22):** on that
  same `--json` case, assert the serialized `residual_directive` is the **nested container**
  shape — `pattern == "provisional_e"`, a non-null `heading`, and **`count == 2` with
  `len(options) == 1`**. A singular-`LocatedOption` implementation passes the "present and non-null"
  assertion above and fails this one; without it the type regression ships silently.
  > ⚠ **Corrected 2026-08-22 — this assertion previously read `len(options) == 2` and would fail
  > against every correct implementation.** `_locate_directive_alternatives` returns `count=2` with
  > exactly **one** span by design (`issue_parser.py:2246-2252`); measured, all **18** corpus
  > directive matches are `(2, 1)`. The `2` is a floor Phase 4 scoring requires, not a span count.
  > The bad assertion came from the retracted half of the type correction — see § *Part 1a*.
- `scripts/tests/test_decide_issue_skill.py` — a phase-text assertion that the Phase 3 slice's
  `count == 1` branch is conditioned on `residual_directive is None`.
  > ⚠ **Restated 2026-08-21.** Previously *"asserts the Phase 3 slice mentions `residual_directive`
  > and states it is reported rather than scored (part 1c)"*. Part 1c is deferred to BUG-3278; what
  > survives here is the one-line guard on the existing clear branch, which is the assertion that
  > actually distinguishes "the directive is visible" from "the flag can no longer be falsely
  > cleared." A mention-only assertion passes even when the branch still clears.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser_unresolved.py:35-49`
  (`TestLocatedOptionsDataclass::test_located_options_to_dict_nests_options`) — **will break**
  once `LocatedOptions.to_dict()` serializes `residual_directive` (part 1a): the test asserts
  `located.to_dict() ==` a literal 4-key dict (`count`/`pattern`/`heading`/`options`); the real
  dict gains a 5th key and this exact-equality assertion fails. Update the expected dict to
  include `"residual_directive": None`. No other `.to_dict() ==` exact-equality call on
  `LocatedOptions` exists in the suite, so this is the only mechanical break. `TestLocatedOptionsDataclass`
  (`:19-56`) is also the closer same-dataclass-family precedent for the new field's own tests
  (construction + `to_dict()`-includes-the-key + defaults-to-`None`-when-absent) — a better model
  than the `IssueInfo.parent`/`base_branch` frontmatter-parsing precedent cited in Program Design,
  since `LocatedOptions` is built by direct construction inside `locate_enumerable_options`, not
  parsed from YAML frontmatter.

### Documentation

- `docs/reference/API.md:989-1045` — `locate_enumerable_options` precedence prose and the
  documented `bullet` shape; `count_enumerable_options` wrapper note (anchor `987-1032` → `989-1045`)
- `docs/reference/CLI.md:1957` (`check-decidable` Pattern E coverage sentence), `:2035`
  (`locate-options` precedence framing and worked example) — anchors `1945`/`2023` corrected
  2026-08-22
- `docs/guides/DECISIONS_LOG_GUIDE.md:198` — states Pattern E is reached when formal option blocks
  are absent; becomes false under part 1
- **In-code docs (added 2026-08-22, pre-implementation review 2 — the list above covered external
  docs only):** `locate_enumerable_options`'s docstring (`issue_parser.py:2392-2412`) spells out
  the four-stage "when (3) also finds nothing" precedence, and the BUG-3293 comment in
  `check_decidable.py:43-53` frames the directive probe as chain-fallback; both go stale under
  part 1 and must be updated in the same commit

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:254` — prose states the pattern precedence is "section headers, bold
  labels, numbered/bullet items, then the un-preferenced-directive heuristic," describing the
  directive as a strict last-resort fallback; becomes stale under part 1 (directive is probed
  alongside tiers, not only after all miss). The same sentence's `locate-options --json` /
  `pattern: "provisional_e"` example should also note `residual_directive` when both a tier and a
  directive match, under the settled Option B shape.
  > ⚠ **This sentence is *already* stale, independently of this issue (found 2026-08-22).** Its
  > precedence list omits BUG-3293's `decision_rules_numbered` stage entirely. Fix both defects in
  > the one doc pass — and check `docs/reference/API.md` and `docs/guides/DECISIONS_LOG_GUIDE.md:198`
  > for the same omission while there, rather than leaving a half-corrected precedence description
  > across three files.

### Configuration

N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- Test structure for `_OPTION_PATTERNS`-adjacent cases follows two coexisting, disagreeing styles
  in the exact two files this issue already cites — the "table-driven case" language doesn't pin
  which one:
  - One test method per named tier/shape, grouped under a `class Test<Concept>` —
    `TestLocatedOptionsPatternNames` (`scripts/tests/test_issue_parser_unresolved.py:59-104`).
  - A manual `for` loop over a tuple of shapes with an inline assertion message (not
    `pytest.mark.parametrize`) — `test_declaration_boundary_variants_counted`
    (`scripts/tests/test_issue_parser_unresolved.py:581-592`), the closer structural match to the
    proposed 14-shape match matrix.
  - `pytest.mark.parametrize` is also established in the same module family
    (`scripts/tests/test_issue_parser.py:4199-4232`).
  - `scripts/tests/test_issues_locate_options.py` asserts at the CLI `--json` layer
    (`class Test<Shape>JsonShape`, `_write_issue()` + `_invoke(..., "--json")`, checking
    `data["count"]`/`data["pattern"]`/`data["heading"]` and `set(option) == {"label", "text",
    "start_line", "end_line"}`) — a new `residual_directive` key would need a parallel
    `set(option)`-style shape assertion at this layer if surfaced through `--json`.
- Corpus-wide sweeps over `.issues/` exist in two shapes, both checked **within a single run** —
  neither loads a stored prior-run baseline to diff against, so the "no count decreases, no
  heading changes" before/after comparison this issue proposes has no direct precedent to follow:
  - Crash-safety-only: `TestUnappliedDecisionLiveCorpusSweep`
    (`scripts/tests/test_issue_parser.py:5563`; `test_corpus_sweep_does_not_crash` at `:5585`) —
    asserts only that the function doesn't raise on real content, no value comparison.
    > Anchor corrected 2026-08-21 (`:5005-5036` → `:5063`/`:5085`) and **re-corrected 2026-08-22**
    > (`:5063`/`:5085` → `:5563`/`:5585`). Also cited stale in EPIC-3290 and twice in BUG-3285 —
    > those citations are now wrong by ~500 lines and should be refreshed when each is next touched.
  - Threshold/statistical: `TestCorpusBaseline` (`scripts/tests/test_research_triage.py:538-606`,
    `@pytest.mark.timeout(600)` + `@pytest.mark.slow`, skip if corpus < 100 issues, `lru_cache`-
    memoized sweep) — asserts aggregate statistics computed within one pass, not a diff.
  - Shared scaffolding worth reusing: skip-if-corpus-absent, `.issues` resolution via
    `Path(__file__).resolve().parents[2]`, `rglob("*.md")`, `@pytest.mark.slow`/`timeout` markers.

## Program Design

### Types

- `LocatedOptions.residual_directive: LocatedOptions | None` — new optional field (settled shape),
  default `None` so every existing constructor call and `to_dict()` consumer is unaffected.
  **Self-referential by design**: the value is whatever `_locate_directive_alternatives` returned,
  which is a `LocatedOptions` (`issue_parser.py:2231`) carrying the directive's `heading`, its
  `pattern` (`"provisional_e"`), its `count` (always 2), and a single window span. It is **not** a
  singular `LocatedOption` — that type has no `heading` field (`:2029-2043`), and `heading` is what
  part 1b's report line needs. See § *Proposed Solution → Part 1a* for the correction, the retracted
  second rationale, and the consequences for the `--json` payload.
  > Consumers test it with `located.residual_directive is not None`, matching this module's
  > direct-attribute-access convention (§ *Codebase Research Findings*); the nested object's own
  > `residual_directive` is always `None`.

### Signatures

- `locate_enumerable_options(content: str) -> LocatedOptions` —
  `scripts/little_loops/issue_parser.py:2391` — unchanged signature; the directive probe moves from
  terminal fallback to an additional probe
- `_locate_directive_alternatives(content: str) -> LocatedOptions | None` —
  `scripts/little_loops/issue_parser.py:2231` — unchanged
- `_locate_decision_rules_numbered(content: str) -> LocatedOptions | None` —
  `scripts/little_loops/issue_parser.py:2349` — unchanged; BUG-3293's fifth stage, left as a
  terminal fallback (§ *Scope boundary — `decision_rules_numbered`*)
- `_locate_options_in_text(content: str, body: str, body_offset: int) -> LocatedOptions | None` —
  `scripts/little_loops/issue_parser.py:2100` — unchanged; still first-tier-wins within a section
- `_OPTION_PATTERNS: tuple[re.Pattern, ...]` — `scripts/little_loops/issue_parser.py:2024` —
  element 3 (`:2028-2030`) widened

> ⚠ **All `issue_parser.py` anchors re-corrected 2026-08-22 (`/ll:ready-issue`)** — a further +12
> lines since the same-day pre-implementation review 2 pass, from two subsequent commits touching
> this region (`c25d6c85f`, `64c4159e7`). Previous values (pre-implementation review 2):
> `locate_enumerable_options` 2379, `_locate_directive_alternatives` 2219,
> `_locate_decision_rules_numbered` 2337, `_locate_options_in_text` 2088, `_OPTION_PATTERNS` 2012,
> `LocatedOptions.to_dict()` 2060-2066, `_extract_option_label` 2078-2085,
> `LocatedOption` 2029-2043, `locate_unresolved_options` 2518. **Re-derive with `grep -n` before
> implementing** — this region has now drifted on nearly every review pass; do not trust any of
> these numbers as more than a starting point.

### Call Path

`ll-issues check-decidable` / `ll-issues locate-options` -> `cmd_check_decidable`
(`cli/issues/check_decidable.py:19`) / `cmd_locate_options` (`cli/issues/locate_options.py:38`) ->
`locate_enumerable_options` (`issue_parser.py:2391`) -> `_locate_options_in_text` (`:2100`) **and**
`_locate_directive_alternatives` (`:2231`), with `_locate_decision_rules_numbered` (`:2349`)
remaining a terminal fallback -> `LocatedOptions`

### Decision Rules

> **SETTLED 2026-08-22 — Option B with a mandatory guard. No open decision remains here.** The
> three rounds of Option A/B argument this section accumulated (original recommendation, "Cost
> correction", "Cost correction 2") reached a stable answer and then kept restating it, with the
> later rounds contradicting the earlier ones. Collapsed below to the settled result and the
> reasoning that survives. History is in git; nothing actionable was dropped.

**The shape: Option B — a `residual_directive: LocatedOptions | None` field**, leaving
`count`/`pattern`/`options` byte-identical to the tier result. The rejected alternative (Option A)
was to merge the directive into `count`/`options`.

**Why B over A.** `count` is load-bearing for a branch that clears `decision_needed` outright
(`SKILL.md:187`). Option A moves `count` on all 7 live preemption cases — documents this issue is
not otherwise touching — and makes `pattern` misdescribe one entry. B's advantage is a smaller
*blast radius*, not a smaller diff. It is also the only shape with codebase precedent: no result
type in this module merges two probes' outputs into one field (§ *Codebase Research Findings*).

**What B costs — three edits, not one.** The field alone changes nothing observable:
`cmd_check_decidable` reads only `located.count` (`check_decidable.py:36`) and
`LocatedOptions.to_dict()` emits only `count`/`pattern`/`heading`/`options` (`:2060-2066`). Ship the
dataclass field by itself and all 7 preempted issues produce byte-identical output. The mandatory
remainder is: **part 1a** (serialize it), **part 1b** (report it in `check-decidable`'s success
line), and the guard below.

**The guard — non-negotiable, and the one place B is weaker than A:**

> Phase 3's `count == 1` branch (`SKILL.md:187`) must additionally require
> `residual_directive is None` before clearing `decision_needed`.

B's defining property — `count` stays byte-identical — is exactly what leaves the ordering
constraint open, because that constraint's mechanism *is* a `count` collapse (BUG-3229, `2 → 1`
under part 2; measured). Option A would have closed it incidentally by moving `count` back to 2.
Without this guard B is strictly worse than A on this issue's headline defect. It is a condition
appended to an existing sentence — ~1 line of SKILL.md — which is what keeps B affordable against
the line budget. Pinned by the `test_decide_issue_skill.py` assertion under § *Tests*.

> ⚠ **Reachability note added 2026-08-22 (pre-implementation review 2) — the guarded branch is
> interactive-mode-only for the bullet collapse.** Phase 3's auto-mode bullet carve-out
> (`SKILL.md:183`) precedes the `count == 1` branch: with `pattern == "bullet"` and
> `AUTO_MODE = true`, `OPTIONS` is treated as empty and flow routes to Phase 3b (whose own
> Pattern E scan can still find the directive). So BUG-3229's post-part-2 `count 1, bullet` result
> never reaches the clear branch under automation; the false-clear the ordering constraint
> describes runs through **interactive** mode. The guard is still required — but place it on the
> `count == 1` line itself (`:187`), after the carve-out, and do not let the interactive-only
> reachability argue it away.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- `to_dict()` on every dataclass in `issue_parser.py` (`LocatedOptions.to_dict()` at `:2060-2066`,
  `IssueInfo.to_dict()` at `:2770-2807`, `FormatGaps.to_dict()` at `:567-595`,
  `QuestionGaps.to_dict()` at `:631-635`) always includes every field explicitly, never omitting a
  `None`/empty value — a new optional field appears as a dict key on every call regardless of
  whether it fired.
- New optional fields on these dataclasses follow `field_name: Type | None = None`, appended after
  existing non-default fields (`IssueInfo`'s `parent: str | None = None` at `:2732`,
  `base_branch: str | None = None` at `:2733`), each documented with a one-line description and
  provenance note in the class docstring's `Attributes:` block (`:2691-2723`).
- Consumers of this module's own dataclasses read a possibly-unset field via direct attribute
  access + `is not None`, never `getattr` — `cli/issues/locate_options.py:45-48`
  (`if located.pattern is not None:`, `if located.heading is not None:`). `getattr(obj, "attr",
  default)` is reserved in this codebase for duck-typed/external objects (`argparse.Namespace`,
  SDK response objects) whose shape isn't guaranteed by a local `@dataclass` — e.g.
  `locate_options.py:40`, `host_runner.py:2246,2263-2264`. No dataclass result in this module
  family is ever consumed via `getattr`.
- No example in this codebase merges two probes' outputs into the same result field (the shape
  Option A proposes). Every existing multi-probe result keeps each probe on its own field:
  `FormatGaps` (`issue_parser.py:490-522`, body `:638`) computes ~24 independent gap categories
  each into its own list field with no probe suppressing another; `QuestionGaps` (`:615-635`) is
  the two-field version; `triage_research_axes` (`issues/research_triage.py:279-339`) runs every
  axis probe unconditionally into a tuple before any conditional overwrite. This is one-sided
  evidence for Option B's shape, not a contested convention — no precedent in the codebase argues
  for Option A's merge-into-one-field approach.

## Implementation Steps

0. **Shared SKILL.md extraction — standalone preparatory commit (owned here; added 2026-08-21,
   epic review).** Before any of this epic's `skills/decide-issue/SKILL.md` edits land, perform
   the extraction pass from EPIC-3290 § *Shared constraint — the decide-issue SKILL.md line
   budget*: move reference material from `SKILL.md` into `skills/decide-issue/reference.md`
   until `SKILL.md` is at or under **460 lines**. Land it as its own no-behavior-change
   commit, verified by `test_enh494_skill_companions.py` (line limit + companion-pointer test).
   Ownership sits here because this issue lands first — not because its own ≤2-line edit needs
   the headroom; BUG-3278 and ENH-3280 inherit it.

   > ⚠ **Numbers refreshed 2026-08-22.** `SKILL.md` is **495** lines, not 493 — **5** lines of
   > headroom against the 500 cap, not 7. `skills/decide-issue/reference.md` **already exists**
   > (144 lines, extracted under ENH-494 and referenced from Phases 3b/4/6/9 + Integration), so
   > this step **extends an existing companion**; it does not create one. The ≤460 target still
   > holds arithmetically: 495 + 2 (this issue) + ~20 (BUG-3278) + ~15 (ENH-3280) = **532 > 500**.

   > ⚠ **`test_enh494_skill_companions.py` is not sufficient verification (added 2026-08-21, epic
   > review).** `scripts/tests/test_decide_issue_skill.py` holds **77** `test_*` methods that
   > slice `SKILL.md` by phase heading and assert on its prose (`SKILL_FILE` at `:14`; the
   > `_phase_text()` slice-and-assert idiom runs through every phase class). Moving tables and
   > worked examples out of `SKILL.md` is precisely the edit that breaks them, and the line-limit
   > test cannot see it. **Run `test_decide_issue_skill.py` as part of Step 0's gate**, under the
   > rule: *any string asserted there stays in `SKILL.md`, or its assertion moves to
   > `reference.md` in the same commit.* Extract reference material (tables, matrices, fenced
   > examples) preferentially over imperative phase prose, since the assertions target the latter.

1. **Part 1 first.** Restructure `locate_enumerable_options` (`:2379`) so
   `_locate_directive_alternatives` runs in addition to the tier scan, per the settled Option B
   shape in *Decision Rules*. Set `residual_directive = None` explicitly on the
   `decision_rules_numbered` path (§ *Scope boundary*). Add `TestDirectiveNotPreempted` and assert
   the live preempted issues now surface their directive — **pin by ID as a subset check**
   (BUG-1183, ENH-2446, ENH-2873, ENH-3277, ENH-2239, ENH-3275, FEAT-2339), never by cardinality:
   the set was 6 when this issue was written and is 7 today.
   > ⚠ **Fixture the permanent pins — added 2026-08-22 (pre-implementation review 2).** The seven
   > preempted issues are all open `decision_needed` documents in exactly the pipeline this epic
   > feeds: running `/ll:decide-issue` on ENH-2446 edits the very directive text a live-corpus pin
   > asserts. Copy 2–3 of them into test fixtures for the committed `TestDirectiveNotPreempted`
   > cases; keep the seven-ID live subset check as a landing-time verification, not a committed
   > assertion the backlog's normal churn can break. Same rationale as the corpus differential's
   > fixture split — see § *Tests*.
2. **Parts 1a–1b — the consumer edits that make Option B observable.** Serialize
   `residual_directive` in `LocatedOptions.to_dict()` (`:2060`); add the residual-directive report
   line to `cmd_check_decidable`'s success output (`check_decidable.py:37-40`, **gate at `:36`
   unchanged**); add the `residual_directive is None` guard to Phase 3's `count == 1` branch
   (`skills/decide-issue/SKILL.md:187`). **Do not defer these to a follow-up** — steps 1 and 2
   together are the fix for defect 1; step 1 alone changes no observable output. Land the
   observability guard and the directive-shape guard (*Tests*) here, and confirm the `--json`
   assertion fails against step 1 alone.
   > ⚠ **Corrected 2026-08-22.** This step previously said to add `or located.residual_directive is
   > not None` to the gate and to *"confirm [the end-to-end guard] fails against step 1 alone."*
   > The gate clause is unreachable (§ *Part 1b*) and the end-to-end guard passes on today's tree
   > (§ *Tests*), so that confirmation was unsatisfiable. The `--json` `residual_directive`
   > assertion is the check that genuinely fails before part 1a lands.
   > ⚠ **Part 1c (Phase 3 reporting prose) is deferred to BUG-3278** — see § *Proposed Solution →
   > Part 1c*. What remains in this step is the one-line branch guard, not a reporting rule.
3. Land the corpus differential test (no `count` decreases, no `heading` changes, with the
   four-file pinned-exception list — BUG-3229, ENH-3264, ENH-2164, ENH-2358; see *Tests*)
   **before** part 2, so it fails loudly if part 2 regresses a file.
4. **Part 2.** Widen `_OPTION_PATTERNS[3]`. Add the 14-shape match matrix as a table-driven test.
5. Add the `locate-options` and `check-decidable` cases pinning the newly-reachable
   `- **(a) …**` shape as `bullet`/decidable — these are behavior changes to existing consumers
   and must be pinned by test, not left implicit.
6. Re-run the corpus differential; confirm the **four** pinned intended changes land exactly as
   measured — BUG-3229 `count 2 / provisional_e` → `count 1 / bullet` with `residual_directive`
   non-null, ENH-3264 §`Confidence Check Notes` → §`Proposed Solution`, ENH-2164 §`Reopened` →
   §`Relationship to ENH-2165, rn-remediate, and Conjunctive Rules`, and ENH-2358
   §`Implementation Steps` → §`Expected Behavior` — and that no *unpinned* file's `count` decreases
   or resolved `heading` changes.
   > ⚠ **Corrected 2026-08-21 (epic review).** This step previously asserted BUG-3229 "holds at
   > `count 2`" and ENH-3264's resolved section "is stable" — both contradict the amended
   > *Expected Behavior*, § *Blast radius*, and the corpus differential's pinned-exception list,
   > all of which declare exactly those two changes intended under Option B + part 2. The step
   > predated those amendments and was never updated.
   > ⚠ **Extended 2026-08-22** — ENH-2164 and ENH-2358 added; the pinned set is four, not two.
   >
   > **Re-measure, do not reuse.** These four are today's corpus state. Per § *Relationship to
   > BUG-3285*, whichever `_OPTION_PATTERNS` issue lands second must re-derive its own differential
   > against the post-first-issue tree rather than trusting the numbers recorded here — the set has
   > already moved once (6 → 7 preempted, 2 → 4 heading-movers) between refinement and now.
7. Update the four documentation sites in *Integration Map → Documentation*. Under Option B,
   `docs/reference/CLI.md`'s `locate-options` section also gains the new top-level
   `residual_directive` key in its `--json` payload description.
   > ⚠ Superseded — five sites now, `/ll:wire-issue` added `docs/reference/COMMANDS.md:254`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_issue_parser_unresolved.py:35-49`
  (`test_located_options_to_dict_nests_options`) — add `"residual_directive": None` to the
  expected dict once part 1a lands, or the existing exact-equality assertion fails
- Update `docs/reference/COMMANDS.md:254` — the pattern-precedence sentence describes the
  directive as a strict last-resort fallback; correct alongside the other documentation sites in
  step 7

### Relationship to BUG-3285 — measured independent (2026-08-21)

Both issues edit `_OPTION_PATTERNS` (this one widens element `[3]`, BUG-3285 tightens element `[1]`)
and neither declared an edge to the other. Measured directly by running
`locate_enumerable_options` over all of `.issues/` in four configurations — baseline, tier-1
tightened, tier-3 widened, and both:

| Configuration | files changed vs baseline |
| --- | --- |
| BUG-3285 alone (tier 1 tighten) | 10 |
| BUG-3287 alone (tier 3 widen) | 22 |
| both applied together | 32 |

**0 files are changed by both issues; 0 composition surprises** (every file's both-applied result
equals its single-issue result); **no `count` drop appears only when both land.** The two are
additive on today's corpus and may land in either order without a joint re-derivation.

Caveat: this is a corpus-dependent measurement, not a structural guarantee — tier precedence means a
document that stops matching tier 1 can fall through to tier 3. Whichever issue lands **second** must
re-run its own corpus differential against the post-first-issue tree rather than reusing the numbers
recorded in its body.

**Out of scope**: `locate_unresolved_options` (`:2532`) and `_iter_option_blocks` (`:2478`) — they do
not read `_OPTION_PATTERNS`, and widening their conservatism is a loop-gate change with its own
blast radius (the ENH-2446 comment at `:2462-2467` is a deliberate choice). BUG-3278 covers the
decision-group layer built over them.
> Anchors corrected 2026-08-21 (`:2210-2240`/`:2225` → `:2341`/`:2287`/`:2273-2277`) and
> re-corrected 2026-08-22 (`:2341`/`:2287`/`:2273-2277` → `:2518`/`:2464`/`:2450-2455`), then
> **re-corrected again 2026-08-22 (`/ll:ready-issue`)** (`:2518`/`:2464`/`:2450-2455` →
> `:2532`/`:2478`/`:2462-2467`). This region has now drifted three times in two days; re-derive
> with `grep -n`, do not trust these on read.

## Impact

- **Priority**: P2 — defect 1 is live on six committed issues and silently hides a decision point;
  defect 2 makes the repo's own idiomatic option shape invisible to the decidability gate. Neither
  is a common-path break, which is what keeps it off P1.
- **Effort**: Medium — two small, well-bounded edits to `issue_parser.py` plus three mandatory
  consumer edits under the settled Option B (`to_dict()`, `check_decidable.py`'s success line, the
  one-line Phase 3 guard). The test burden is where the weight actually sits: a corpus differential
  with a four-file pinned-exception list, the observability + directive-shape guards, and pinning
  tests for three existing consumers.
  > ⚠ **Size re-check 2026-08-22.** Frontmatter says `size: Very Large`. With part 1c deferred to
  > BUG-3278 and part 1b reduced to a report line, the production delta is a dataclass field, a
  > `to_dict()` entry, a regex, a `print`, and one SKILL.md clause. **Large** is the honest size;
  > the tests and the Step 0 extraction are what keep it off Medium. Re-run
  > `/ll:issue-size-review` before scheduling rather than inheriting the estimate.
- **Risk**: Medium. `_OPTION_PATTERNS` is module-level state on the shared precedence chain; 22
  live issues change output, and **four** of them change in ways the obvious regex-superset check
  does not predict (not two, as originally recorded). Bounded by the ordering constraint (part 1
  before part 2) and the corpus differential, which is the only test that catches the count-drop
  and section-shift classes.
- **Breaking Change**: No — no signature changes, and no *existing* CLI contract changes, under the
  recommended shape. Note that Option B does **add** a top-level `residual_directive` key to
  `ll-issues locate-options --json` (part 1a); that is additive, and `test_issues_locate_options.py`
  asserts exact key sets only per-*option*, not on the top-level payload (verified `:94`).

## Root Cause

- **File**: `scripts/little_loops/issue_parser.py`
- **Anchor**: `in function locate_enumerable_options()` and `_OPTION_PATTERNS[3]`
- **Cause**: The precedence chain treats `_locate_directive_alternatives` as a terminal fallback
  reached only when every tier misses document-wide, so a tier match masks a co-located prose
  directive. Separately, `_OPTION_PATTERNS[3]`'s `\*{0,2}` bold-tolerance was scoped to the
  `Option X` alternative only, leaving `- **(a) …**` unreachable by any tier.

## Related Key Documentation

- `docs/guides/DECISIONS_LOG_GUIDE.md:198` — documents the Pattern E fallback semantics this
  issue changes
- `docs/reference/CLI.md:1957` — documents `check-decidable`'s Pattern E coverage
- BUG-3278 — the sibling this was split out of; fixes the same two defects inside its own new
  decision-group iterator, leaving the shared chain to this issue

## Verification Notes

_Verified 2026-08-21 via `/ll:verify-issues --check --auto`:_

- **Both defects reproduce exactly as described.** Defect 2's snippet
  (`_OPTION_PATTERNS` against `- **(a) Make the documented override real.**`) still returns `[]`.
  Defect 1's corpus script still finds the same 6 issues (BUG-1183, ENH-2446, ENH-2873, ENH-2239,
  ENH-3275, FEAT-2339) with matching lines. `residual_directive` does not exist anywhere in the
  tree — the proposal is unimplemented, as described.
- **`issue_parser.py` line citations had drifted 58–75 lines** (concurrent edits to sibling issues
  BUG-3285/BUG-3289 touch the same region) and are corrected in place above:
  `locate_enumerable_options` 2134→2209, `_locate_directive_alternatives` 2062→2137,
  `_locate_options_in_text` 1967→2025, `_OPTION_PATTERNS` 1891→1949 (tuple opens 1949; element `[3]`
  at 1953-1955).
- **`check_decidable.py:36` was off by one** — the `located.count >= 1` gate is at line 35, not 36
  (36 is the following `print(`). Corrected in the four citing spots. The `:19-52` function-range
  citations were already accurate and untouched.
- **`locate_options.py:19-38` corrected to `19-51`** — `cmd_locate_options` runs to the file's last
  line (51), not 38.
- `LocatedOptions.to_dict()` (`:1997-2003`), `test_issue_parser_unresolved.py:35-49`, dependency
  refs (`EPIC-3290`, `BUG-3278`, `BUG-3279` all resolve; no `## Blocked By` section), and the
  decisions log (no active required rules) all confirmed exact, no changes needed.

_Pre-implementation review — 2026-08-22 — all figures re-measured against the live tree:_

- **Both defects still reproduce.** Defect 2's snippet returns `[]` unchanged; `residual_directive`
  still does not exist anywhere in the tree.
- **Five findings changed the spec**, each amended in place above with a dated ⚠ note:
  1. **Part 1b was unreachable dead code** — `residual_directive` implies a tier fired implies
     `count >= 1`, so the proposed `or` clause can never flip an exit code (7 documents receive the
     field; 0 with `count == 0`). Rescoped to reporting.
  2. **The "Option B end-to-end guard" passed on the unmodified tree** — it could not witness the
     change it was designated to prove. Replaced with a `--json` observability guard.
  3. **The directive-shape guard asserted `len(options) == 2`**, which fails against every correct
     implementation (all 18 corpus directive matches are `count == 2, len(options) == 1`). The
     retracted half of the 2026-08-21 type correction is where it came from.
  4. **BUG-3293 added a fifth precedence stage** (`decision_rules_numbered`) after this issue was
     written; measured 0/0 impact, now recorded as an explicit scope boundary.
  5. **The corpus differential's pinned list was half the real set** — ENH-2164 and ENH-2358 also
     move their resolved `heading`; the `0 → N` group is 16, not 20.
- **Unchanged and re-confirmed**: the 14-shape match matrix (14/14 exact), the 22-file blast-radius
  total, BUG-3229's `2 → 1` collapse, the ordering constraint, and the Option B recommendation.
- **Anchor drift, second pass in two days** — every `issue_parser.py` citation moved a further
  +60 to +170 lines (BUG-3293, BUG-3295); `check_decidable.py`'s gate moved `:35` → `:36` and the
  file now returns 2 for unresolvable IDs (BUG-3294); the corpus-sweep test moved `:5063` → `:5563`;
  CLI.md `1945`/`2023` → `1957`/`2035`; API.md `987` → `989`. All corrected in place. Still exact:
  `SKILL.md:187`, `COMMANDS.md:254`, `DECISIONS_LOG_GUIDE.md:198`, `resolve-decision.yaml:47-67`,
  `test_issue_parser_unresolved.py:44`, `test_issues_locate_options.py:94`.
- **Line budget**: `SKILL.md` is 495 lines (not 493) and `skills/decide-issue/reference.md` already
  exists at 144 lines; `test_decide_issue_skill.py` confirmed at 77 test methods.

_Pre-implementation review 2 — 2026-08-22 — independent re-measurement:_

- **Every empirical claim reproduces exactly**: 7 preempted issues (IDs, headings, lines all
  match), 22-file blast radius with exactly the four pinned movers, 15/15 match matrix (including
  the `- ***(a)*** foo` non-goal row), directive shape `(2, 1)` across all 18 corpus matches, and
  all code/test anchors exact (`:2012`/`:2060`/`:2088`/`:2219`/`:2337`/`:2379`; gate at `:36`;
  SKILL.md 495 lines with the clear branch at `:187`; single exact-equality `to_dict()` assertion
  at `test_issue_parser_unresolved.py:44`). Only `_locate_options_in_text` reads
  `_OPTION_PATTERNS`, confirming the blast-radius boundary.
- **Five additions folded in above**, each with a dated ⚠ note:
  1. The corpus differential's "before" baseline mechanism (old-regex-literal monkeypatch) and
     its landing-gate vs frozen-fixture split (§ *Tests*).
  2. Live-corpus pin fragility for `TestDirectiveNotPreempted` — fixture 2–3 of the seven
     (Implementation Step 1).
  3. `_extract_option_label` widened alongside the tier regex; label asymmetry measured
     (`''` vs `'(a)'`) (§ *Part 2*, *Files to Modify*).
  4. In-code doc sites (the `locate_enumerable_options` docstring, `check_decidable.py:43-53`
     comment) plus a human-readable `locate-options` parity line (§ *Documentation*,
     *Files to Modify*).
  5. The Phase 3 guard's `count == 1` branch is interactive-mode-only reachable for the bullet
     collapse — the auto-mode bullet carve-out at `SKILL.md:183` precedes it; guard still
     required, placement clarified (§ *Decision Rules*).

## Resolution

- **Action**: fix
- **Completed**: 2026-08-22
- **Status**: Completed
- **Solution**: Both parts implemented per the settled Decision Rules (Option B, `residual_directive: LocatedOptions | None`). Step 0 (the preparatory SKILL.md extraction to ≤460 lines) was scoped out — it exists solely to bank headroom for sibling issues BUG-3278/ENH-3280, not because this issue's own ≤2-line SKILL.md edit needs it (495 → 495 lines, still under the 500-line cap); left for whichever of those lands first to perform.

### Changes Made
- `scripts/little_loops/issue_parser.py`: `LocatedOptions.residual_directive: LocatedOptions | None` field (+ `to_dict()` serialization); `locate_enumerable_options` now probes `_locate_directive_alternatives` alongside the tier/H2-scan result instead of only as a terminal fallback, attaching a co-located directive as `residual_directive` (`count`/`pattern`/`heading` stay byte-identical to the tier-only result); `decision_rules_numbered` explicitly sets `residual_directive = None` (scope boundary); `_OPTION_PATTERNS[3]` widened (`\*{0,2}` hoisted to cover the `(a)` marker, `\s+` relaxed to `\s*`); `_extract_option_label` gains the same hoist for label symmetry
- `scripts/little_loops/cli/issues/check_decidable.py`: success line now names a residual directive when present (`located.count >= 1` gate at unchanged); in-code comment updated
- `scripts/little_loops/cli/issues/locate_options.py`: human-readable output gains a parity `+ residual decision directive ...` line
- `skills/decide-issue/SKILL.md` (+ regenerated `.gemini`/`.kimi-code`/`.qwen` mirrors via `ll-adapt`): Phase 3's `count == 1` branch now additionally requires `residual_directive is None` before clearing `decision_needed`
- Tests: `test_issue_parser_unresolved.py` (`TestDirectiveNotPreempted`, frozen fixture `BUG-9301-tier-match-preempts-directive.md`), `test_issues_locate_options.py` / `test_ll_issues_check_decidable.py` (observability + directive-shape guards, bold-wrapped-bullet pin), `test_decide_issue_skill.py` (Phase 3 guard text), `test_bug_3287_option_patterns_widening.py` (15-shape match matrix, label symmetry, frozen 7-file corpus differential under `fixtures/issues/bug3287_corpus/`, content-independent live-corpus crash-safety sweep), `test_issue_parser.py` (priority-regex allowlist anchors re-derived after the docstring grew)
- Docs: `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/reference/COMMANDS.md`, `docs/guides/DECISIONS_LOG_GUIDE.md`

### Verification Results
- Tests: PASS (20,839 passed, 40 skipped, 1 pre-existing unrelated failure confirmed via `git stash` against unmodified `main` — `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence`, an evidence-quote gate on BUG-3296/BUG-3285, untouched by this issue)
- Lint: PASS (`ruff check`, `ruff format`)
- Types: PASS (`mypy`)
- Live-corpus landing gate (Implementation Steps 3/6): 22 files changed, exactly 1 count decrease (BUG-3229, `2 → 1`, pinned/intended) and exactly the 4 documented heading movers (BUG-3229 stable, ENH-3264, ENH-2164, ENH-2358) — matches the issue's blast-radius table exactly. All 7 preempted-directive issues (BUG-1183, ENH-2446, ENH-2873, ENH-3277, ENH-2239, ENH-3275, FEAT-2339) now surface `residual_directive`.

## Status

**Completed** | Created: 2026-08-21 | Completed: 2026-08-22 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-23T00:57:19 - `ea6bb832-590f-44d5-a451-a82d39ec0a6c.jsonl`
- `/ll:ready-issue` - 2026-08-23T00:26:42 - `c42eb52e-6723-400e-b7d9-3ebaee9c8346.jsonl`
- `/ll:confidence-check` - 2026-08-22T23:55:04 - `ce409b47-4f21-485c-93e6-b694fe8d8170.jsonl`
- `/ll:confidence-check` - 2026-08-22T23:39:28 - `f148b0fe-9006-4283-9e7f-18566ca40d9e.jsonl`
- `/ll:verify-issues` - 2026-08-21T20:20:13 - `63b58074-9350-43f0-9772-feffb6fc0ffe.jsonl`
- `/ll:refine-issue` - 2026-08-21T20:17:18 - `05b36e3e-cf1c-4269-a1c6-018fbadd4f92.jsonl`
- `/ll:verify-issues` - 2026-08-21T20:15:35 - `a2289dde-4d3d-4b79-aeb5-674049d28ccd.jsonl`
- `/ll:wire-issue` - 2026-08-21T20:08:28 - `323952ee-6da2-4c4d-9f9d-ddb206a14824.jsonl`
- `/ll:refine-issue` - 2026-08-21T19:52:58 - `3e6f73b9-57ce-496a-8cf5-9227a47117bc.jsonl`
