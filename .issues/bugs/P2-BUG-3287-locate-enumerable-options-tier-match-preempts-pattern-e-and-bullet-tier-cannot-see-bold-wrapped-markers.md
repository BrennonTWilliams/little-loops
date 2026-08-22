---
id: BUG-3287
type: BUG
title: locate_enumerable_options lets a tier match preempt Pattern E, and its bullet
  tier cannot see bold-wrapped markers
priority: P2
status: open
parent: EPIC-3290
discovered_by: bug-3278-pre-implementation-review
discovered_date: '2026-08-21'
captured_at: '2026-08-21T19:30:00Z'
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
---

# BUG-3287: locate_enumerable_options lets a tier match preempt Pattern E, and its bullet tier cannot see bold-wrapped markers

## Summary

`locate_enumerable_options` (`issue_parser.py:2209`) resolves a document to **one** option set by
running `_OPTION_PATTERNS` tiers 1–4 first and falling back to the Pattern E directive heuristic
`_locate_directive_alternatives` (`:2137`) only when **all four tiers miss document-wide**. Two
defects follow from that chain:

1. **Pattern E preemption (live today).** Any tier match anywhere in the resolved section hides a
   co-located prose decision directive. Measured over the live `.issues/` corpus: **6 issues** carry
   a Pattern E directive that a tier match preempts right now, with no code change required.
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
`_OPTION_FALLBACK_SECTIONS`, then a whole-document H2 sweep), handing each section body to
`_locate_options_in_text` (`:2025`), which **returns on the first `_OPTION_PATTERNS` tier with
≥1 match**. `_locate_directive_alternatives` is reached only after every section and every tier
has missed.

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

Six live issues, e.g.:

| Issue | Reported | Hidden directive |
|---|---|---|
| BUG-1183 | `count 2`, `bold_label` | `## Proposed Solution`, line 55 |
| ENH-2446 | `count 2`, `bullet` | `## Proposed Solution`, line 123 |
| ENH-2873 | `count 2`, `bold_label` | `## Proposed Change`, line 84 |
| ENH-2239 | `count 2`, `bold_label` | `## Scope Boundaries`, line 49 |
| ENH-3275 | `count 2`, `section_header` | `## Proposed Solution`, line 73 |
| FEAT-2339 | `count 2`, `bold_label` | `## Proposed Solution`, line 128 |

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
  > recommended Option B — see § *Ordering constraint*. Stating it as an absolute is what let the
  > required corpus differential be specified with an assertion that fails on landing.

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
both. Two viable shapes; pin one during implementation:

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
> Verified 2026-08-21: `cmd_check_decidable` (`cli/issues/check_decidable.py:35`) reads only
> `located.count`, and `LocatedOptions.to_dict()` (`issue_parser.py:1997-2003`) serializes only
> `count` / `pattern` / `heading` / `options`. A `residual_directive` field that no consumer reads
> and `--json` does not emit leaves the output for all six preempted issues **byte-identical**, so
> defect 1 would be *made available* rather than fixed and this issue's own *Expected Behavior*
> ("A Pattern E directive is reported even when a tier also matches") would be met by nothing.
> Option A does not have this problem — it moves `count`, which every consumer already reads — which
> is the honest cost of preferring Option B. Parts 1a–1c below are what make Option B equivalent.

### Part 1a — serialize the field

Add `"residual_directive": self.residual_directive.to_dict() if self.residual_directive else None`
to `LocatedOptions.to_dict()` (`issue_parser.py:1997`). This is a **new top-level key** in
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
> returns **`LocatedOptions | None`** (`issue_parser.py:2187`), a container carrying the
> directive's `heading` *and* every alternative it found. Measured on a directive document:
> `(count 2, pattern 'provisional_e', heading 'Proposed Solution')`. Assigning that to a singular
> `LocatedOption` discards two things this issue's own parts depend on:
>
> - the **heading**, which part 1b requires in order to "report the directive in the success
>   line" — `LocatedOption` has no `heading` field at all (`label`/`text`/`start_line`/`end_line`,
>   `issue_parser.py:2016-2030`);
> - the **second alternative** — a Pattern E window is by construction a *choice between*
>   alternatives, so keeping only `options[0]` reports that a decision exists while hiding what
>   it is between.
>
> The corpus script in § *Current Behavior* already reads the probe as a container
> (`d.heading`, `d.options[0].start_line`); the dataclass field must match it.

### Part 1b — teach `check-decidable` to see it

`cmd_check_decidable` (`cli/issues/check_decidable.py:19-52`) gates on `located.count >= 1`. Change
to `located.count >= 1 or located.residual_directive is not None`, and report the directive in the
success line when it is the only thing found. Without this, the six live preempted issues stay
`decidable` for the wrong reason (their tier options) and a document whose *only* decision point is a
preempted directive still routes `resolve-decision.yaml:47-67` to `refine`.

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
>    is **493 lines** against a hard 500-line cap (`TestSkillLineLimit`,
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
output: **22 of the live corpus change**. Two change in ways a regex-level superset check does not
predict, because tier precedence and *section* precedence both shift:

| Issue | Before | After | Why it matters |
|---|---|---|---|
| BUG-3229 | `2`, `provisional_e` | `1`, `bullet` | count **drops**; hits the `count == 1` clear branch. **Part 1 does not prevent this under Option B** — see § *Ordering constraint*; the `residual_directive is None` guard on that branch is what prevents it |
| ENH-3264 | `1`, `numbered`, §Confidence Check Notes | `2`, `bullet`, §**Proposed Solution** | the winning **section** changes, not just the tier |

The remaining 20 are `count 0 → N`, `pattern null → bullet` — the intended correction.

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

Note the last four newly-matching rows come from the `\s+`→`\s*` relaxation, not the bold
widening. A bare `- (a)` in unrelated prose is now a `bullet`-tier match — intended (a marker-only
bullet is still an option label), but it is why the corpus differential below is a required test,
not an optional one.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `locate_enumerable_options` directive-probe ordering
  (+ `LocatedOptions.residual_directive: LocatedOptions | None` if the recommended shape is taken —
  **plural**, see part 1a's type correction), `_OPTION_PATTERNS[3]`
- `scripts/little_loops/issue_parser.py` — `LocatedOptions.to_dict()` (`:1997-2003`), which must
  emit `residual_directive` or the field is invisible to `locate-options --json` (part 1a).
  **Required under Option B, not optional**
- `scripts/little_loops/cli/issues/check_decidable.py` — the `located.count >= 1` gate at `:35`
  gains `or located.residual_directive is not None` (part 1b). **Required under Option B**; without
  it none of the six preempted issues changes observable behavior
- `skills/decide-issue/SKILL.md` — Phase 3's `count == 1` branch (`:187`) gains the
  `residual_directive is None` guard. **Required under Option B** — it is what closes the
  ordering-constraint hole; see § *Decision Rules → Cost correction 2*.
  > ⚠ **Rescoped 2026-08-21.** Previously *"Phase 3 must report a `residual_directive` it does not
  > score (part 1c, surface-only shape)"*. Part 1c is **deferred to BUG-3278**; only the one-line
  > branch guard stays here.
  >
  > **Line budget.** `SKILL.md` is **493 lines** against a hard **500-line** cap enforced by
  > `TestSkillLineLimit` (`scripts/tests/test_enh494_skill_companions.py:73-86`), and BUG-3278 and
  > ENH-3280 also write to this file. This issue's share is **≤ 2 lines** — a condition appended to
  > an existing sentence, not a new paragraph. If the edit does not fit in two lines, extract to
  > `skills/decide-issue/reference.md` per EPIC-3290 § *Shared constraint — the decide-issue
  > SKILL.md line budget* rather than spending the shared headroom.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/check_decidable.py:19-52` — `count >= 1` gate
  > ⚠ Promoted to *Files to Modify* under Option B — see part 1b
- `scripts/little_loops/cli/issues/locate_options.py:19-51` — `--json` payload
- `scripts/little_loops/issues/fold_research_findings.py:178` — prose reference to
  `count_enumerable_options`
- `scripts/little_loops/loops/oracles/resolve-decision.yaml:47-67` (`check_decision_decidable`)
- `skills/decide-issue/SKILL.md:110-146` (Phase 2.5), `:160-190` (Phase 3 extraction + the
  `count == 1` branch at `:187`)
- `commands/refine-issue.md:524` — cites `count_enumerable_options()`/`count_unresolved_options()`

### Similar Patterns

- `locate_unresolved_options` (`issue_parser.py:2240`) mirrors the same *section* precedence but
  its own block iterator; it does **not** read `_OPTION_PATTERNS` and is unaffected by part 2

### Tests

- `scripts/tests/test_issue_parser_unresolved.py` — the match matrix above as a table-driven case;
  a new `TestDirectiveNotPreempted` covering a document with both a tier match and a directive
- **Corpus differential (required):** a test that applies `locate_enumerable_options` across
  `.issues/` and asserts no file's `count` decreases and no file's resolved `heading` changes,
  **except for files pinned as intended changes.** This is the only check that would have caught
  BUG-3229 and ENH-3264; the 14-shape regex matrix passes both.
  > ⚠ **Escape hatch added 2026-08-21 — without it this test fails on the two files this issue
  > already documents as changing.** Under Option B + part 2, `BUG-3229` decreases `count` 2 → 1
  > (measured) and `ENH-3264`'s resolved `heading` moves §`Confidence Check Notes` →
  > §`Proposed Solution`. Both are declared intended in § *Blast radius*, so the assertion must
  > carry a pinned-exception list the way BUG-3285's version of the same test does
  > (*"no file's `count` moves except those pinned as intended"*). Pin exactly these two, by ID,
  > with the expected before/after in the test docstring — a bare `!=` allowance would let the
  > next regression through silently.
  > Scaffolding model: `TestUnappliedDecisionLiveCorpusSweep`
  > (`scripts/tests/test_issue_parser.py:5063`, `test_corpus_sweep_does_not_crash` at `:5085`) —
  > skip-if-corpus-absent, `Path(__file__).resolve().parents[2]`, `rglob("*.md")`.
- `scripts/tests/test_issues_locate_options.py` — a case asserting `- **(a) …**` reports
  `pattern: "bullet"`
- `scripts/tests/test_ll_issues_check_decidable.py` — a case asserting the same document is
  decidable, and one asserting a tier+directive document still reports the directive
- **Option B end-to-end guard (required):** a document whose *only* decision point is a
  tier-preempted directive — assert `ll-issues check-decidable` **exits 0**. This is the assertion
  that fails if parts 1a/1b are skipped, and it is the only one that distinguishes "the field
  exists" from "the defect is fixed." Pair it with a `locate-options --json` case asserting
  `residual_directive` is present and non-null on one of the six live preempted shapes
- **Directive-shape guard (required, added 2026-08-21 with the type correction):** on that same
  `--json` case, assert the serialized `residual_directive` is the **nested container** shape —
  `pattern == "provisional_e"`, a non-null `heading`, and `len(options) == 2` on a two-alternative
  directive. A singular-`LocatedOption` implementation passes the "present and non-null" assertion
  above and fails this one; without it the type regression ships silently
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

- `docs/reference/API.md:987-1032` — `locate_enumerable_options` precedence prose and the
  documented `bullet` shape; `count_enumerable_options` wrapper note
- `docs/reference/CLI.md:1945` (`check-decidable` Pattern E coverage sentence), `:2023`
  (`locate-options` precedence framing and worked example)
- `docs/guides/DECISIONS_LOG_GUIDE.md:198` — states Pattern E is reached when formal option blocks
  are absent; becomes false under part 1

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:254` — prose states the pattern precedence is "section headers, bold
  labels, numbered/bullet items, then the un-preferenced-directive heuristic," describing the
  directive as a strict last-resort fallback; becomes stale under part 1 (directive is probed
  alongside tiers, not only after all miss). The same sentence's `locate-options --json` /
  `pattern: "provisional_e"` example should also note `residual_directive` when both a tier and a
  directive match, under the recommended Option B shape.

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
    (`scripts/tests/test_issue_parser.py:5063`; `test_corpus_sweep_does_not_crash` at `:5085`) —
    asserts only that the function doesn't raise on real content, no value comparison.
    > Anchor corrected 2026-08-21 — `:5005-5036` was stale (the same `f39a417e` drift that moved
    > the `issue_parser.py` anchors). Also cited stale in EPIC-3290 and twice in BUG-3285.
  - Threshold/statistical: `TestCorpusBaseline` (`scripts/tests/test_research_triage.py:538-606`,
    `@pytest.mark.timeout(600)` + `@pytest.mark.slow`, skip if corpus < 100 issues, `lru_cache`-
    memoized sweep) — asserts aggregate statistics computed within one pass, not a diff.
  - Shared scaffolding worth reusing: skip-if-corpus-absent, `.issues` resolution via
    `Path(__file__).resolve().parents[2]`, `rglob("*.md")`, `@pytest.mark.slow`/`timeout` markers.

## Program Design

### Types

- `LocatedOptions.residual_directive: LocatedOptions | None` — new optional field (recommended
  shape), default `None` so every existing constructor call and `to_dict()` consumer is unaffected.
  **Self-referential by design**: the value is whatever `_locate_directive_alternatives` returned,
  which is a `LocatedOptions` (`issue_parser.py:2187`) carrying the directive's `heading`, its
  `pattern` (`"provisional_e"`), and all of its alternatives. It is **not** a singular
  `LocatedOption` — that type has no `heading` field (`:2016-2030`) and would collapse a
  two-alternative directive to one entry. See § *Proposed Solution → Part 1a* for the correction
  and its consequences for the `--json` payload.
  > Consumers test it with `located.residual_directive is not None`, matching this module's
  > direct-attribute-access convention (§ *Codebase Research Findings*); the nested object's own
  > `residual_directive` is always `None`.

### Signatures

- `locate_enumerable_options(content: str) -> LocatedOptions` —
  `scripts/little_loops/issue_parser.py:2209` — unchanged signature; the directive probe moves from
  terminal fallback to an additional probe
- `_locate_directive_alternatives(content: str) -> LocatedOptions | None` —
  `scripts/little_loops/issue_parser.py:2137` — unchanged
- `_locate_options_in_text(content: str, body: str, body_offset: int) -> LocatedOptions | None` —
  `scripts/little_loops/issue_parser.py:2025` — unchanged; still first-tier-wins within a section
- `_OPTION_PATTERNS: tuple[re.Pattern, ...]` — `scripts/little_loops/issue_parser.py:1949` —
  element 3 widened

### Call Path

`ll-issues check-decidable` / `ll-issues locate-options` -> `cmd_check_decidable`
(`cli/issues/check_decidable.py:34`) / `cmd_locate_options` (`cli/issues/locate_options.py:38`) ->
`locate_enumerable_options` (`issue_parser.py:2209`) -> `_locate_options_in_text` (`:2025`) **and**
`_locate_directive_alternatives` (`:2137`) -> `LocatedOptions`

### Decision Rules

One decision remains, scoped and enumerable — the return shape for part 1:

**Option A — merge into `count`/`options`.** Append the directive's `LocatedOption`; increment
`count`. Simplest diff, no dataclass change. Costs: `pattern` misdescribes one entry, and `count`
moves for the 6 live preemption cases — which perturbs Phase 3's `count == 1` branch and
`check-decidable`'s threshold on documents that are not otherwise changing.

**Option B — `residual_directive` field.** Leave `count`/`pattern`/`options` byte-identical;
surface the directive on a new optional field. Costs: one dataclass field, a `to_dict()` entry, an
explicit `or residual_directive` clause in `check-decidable`, and a Phase 3 reporting rule —
**four edits, not one.** Consumers must opt in to see it, so the field alone changes nothing.

Recommendation: **Option B**, because `count` is load-bearing for a branch that clears
`decision_needed` outright, and Option A moves it on documents this issue is not otherwise
touching.

**Cost correction (2026-08-21).** This section previously framed the consumer opt-in as a footnote
("`check-decidable` needs an explicit `or residual_directive` clause to benefit"). Verified against
the tree, it is the whole delta: `cmd_check_decidable` (`cli/issues/check_decidable.py:35`) reads
only `located.count`, and `LocatedOptions.to_dict()` (`:1997-2003`) emits only
`count`/`pattern`/`heading`/`options`. Ship the dataclass field alone and **all six preempted issues
produce byte-identical output** — the defect is unfixed and the *Expected Behavior* above is unmet.
Parts 1a–1c in *Proposed Solution* are the mandatory remainder of Option B, and the Option-B
end-to-end guard under *Tests* is what pins it. This does not overturn the recommendation — moving
`count` is still the higher-risk shape — but Option B's advantage is a smaller *blast radius*, not a
smaller diff.

**Cost correction 2 (2026-08-21) — Option B does not preserve `count` where it matters most.**
The correction above still understated it. Option B's stated advantage is that `count`/`pattern`
stay byte-identical for existing consumers — but *that is exactly what breaks the ordering
constraint*, because the constraint's whole mechanism is a `count` collapse. Measured on BUG-3229:
`count 2 → 1` under part 2, and Option B's part 1 does nothing to it (verified live; see
§ *Ordering constraint*). Option A would have moved `count` back to 2 and closed the hole
incidentally.

The recommendation **stands at Option B**, but only with the guard attached:

> Phase 3's `count == 1` branch (`SKILL.md:187`) must additionally require
> `residual_directive is None` before clearing `decision_needed`.

Without that guard, Option B is strictly worse than Option A on this issue's own headline defect,
and the *Expected Behavior* clause *"the precedence chain must not silently pick one"* is unmet on
the one shape where picking wrong clears the pipeline gate. The guard is a condition on an existing
sentence — roughly one line of SKILL.md — which is what keeps Option B affordable against the
line budget in the *Files to Modify* note below. Assertion: the Option-B end-to-end guard under
*Tests*, extended to a `count 1 + residual_directive` document.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- `to_dict()` on every dataclass in `issue_parser.py` (`LocatedOptions.to_dict()` at `:1997-2003`,
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
   until `SKILL.md` is at or under **460 lines** (493 today; the three children add roughly
   ≤2 + ≤20 + ≤15 net lines against the 500-line cap). Land it as its own no-behavior-change
   commit, verified by `test_enh494_skill_companions.py` (line limit + companion-pointer test).
   Ownership sits here because this issue lands first — not because its own ≤2-line edit needs
   the headroom; BUG-3278 and ENH-3280 inherit it.

   > ⚠ **`test_enh494_skill_companions.py` is not sufficient verification (added 2026-08-21, epic
   > review).** `scripts/tests/test_decide_issue_skill.py` holds **77** `test_*` methods that
   > slice `SKILL.md` by phase heading and assert on its prose (`SKILL_FILE` at `:14`; the
   > `_phase_text()` slice-and-assert idiom runs through every phase class). Moving tables and
   > worked examples out of `SKILL.md` is precisely the edit that breaks them, and the line-limit
   > test cannot see it. **Run `test_decide_issue_skill.py` as part of Step 0's gate**, under the
   > rule: *any string asserted there stays in `SKILL.md`, or its assertion moves to
   > `reference.md` in the same commit.* Extract reference material (tables, matrices, fenced
   > examples) preferentially over imperative phase prose, since the assertions target the latter.

1. **Part 1 first.** Restructure `locate_enumerable_options` so `_locate_directive_alternatives`
   runs in addition to the tier scan; pin the return shape per *Decision Rules*. Add
   `TestDirectiveNotPreempted` and assert the six live corpus cases now surface their directive.
2. **Parts 1a–1b — the consumer edits that make Option B observable.** Serialize
   `residual_directive` in `LocatedOptions.to_dict()` (`:1997`); add `or located.residual_directive
   is not None` to `cmd_check_decidable` (`check_decidable.py:35`); add the
   `residual_directive is None` guard to Phase 3's `count == 1` branch
   (`skills/decide-issue/SKILL.md:187`). **Do not defer these to a follow-up** — steps 1 and 2
   together are the fix for defect 1; step 1 alone changes no observable output. Land the Option B
   end-to-end guard (*Tests*) here, and confirm it fails against step 1 alone. Extend that guard
   with a `count 1 + residual_directive` document asserting the clear branch does **not** fire.
   > ⚠ **Part 1c (Phase 3 reporting prose) is deferred to BUG-3278** — see § *Proposed Solution →
   > Part 1c*. What remains in this step is the one-line branch guard, not a reporting rule.
3. Land the corpus differential test (no `count` decreases, no `heading` changes, with the
   pinned-exception list for BUG-3229 and ENH-3264 — see *Tests*) **before** part 2, so it fails
   loudly if part 2 regresses a file.
4. **Part 2.** Widen `_OPTION_PATTERNS[3]`. Add the 14-shape match matrix as a table-driven test.
5. Add the `locate-options` and `check-decidable` cases pinning the newly-reachable
   `- **(a) …**` shape as `bullet`/decidable — these are behavior changes to existing consumers
   and must be pinned by test, not left implicit.
6. Re-run the corpus differential; confirm the two pinned intended changes land exactly as
   measured — BUG-3229 `count 2 / provisional_e` → `count 1 / bullet` with `residual_directive`
   non-null, and ENH-3264's resolved section moving §`Confidence Check Notes` →
   §`Proposed Solution` — and that no *unpinned* file's `count` decreases or resolved `heading`
   changes.
   > ⚠ **Corrected 2026-08-21 (epic review).** This step previously asserted BUG-3229 "holds at
   > `count 2`" and ENH-3264's resolved section "is stable" — both contradict the amended
   > *Expected Behavior*, § *Blast radius*, and the corpus differential's pinned-exception list,
   > all of which declare exactly those two changes intended under Option B + part 2. The step
   > predated those amendments and was never updated.
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

**Out of scope**: `locate_unresolved_options` (`:2341`) and `_iter_option_blocks` (`:2287`) — they do
not read `_OPTION_PATTERNS`, and widening their conservatism is a loop-gate change with its own
blast radius (the ENH-2446 comment at `:2273-2277` is a deliberate choice). BUG-3278 covers the
decision-group layer built over them.
> Anchors corrected 2026-08-21: `:2210-2240` and `:2225` were stale — `:2210` is inside
> `locate_enumerable_options`, not the block iterator. BUG-3278 cites this same comment correctly
> as `:2271-2275`.

## Impact

- **Priority**: P2 — defect 1 is live on six committed issues and silently hides a decision point;
  defect 2 makes the repo's own idiomatic option shape invisible to the decidability gate. Neither
  is a common-path break, which is what keeps it off P1.
- **Effort**: Medium — two small, well-bounded edits to `issue_parser.py` plus, under the
  recommended Option B, three mandatory consumer edits (`to_dict()`, `check_decidable.py`, Phase 3
  reporting — parts 1a–1c). The test burden is real: a corpus differential, the Option B end-to-end
  guard, and pinning tests for three existing consumers.
- **Risk**: Medium. `_OPTION_PATTERNS` is module-level state on the shared precedence chain; 22
  live issues change output, and two of them change in ways the obvious regex-superset check does
  not predict. Bounded by the ordering constraint (part 1 before part 2) and the corpus
  differential, which is the only test that catches the count-drop and section-shift classes.
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
- `docs/reference/CLI.md:1945` — documents `check-decidable`'s Pattern E coverage
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

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-08-21T20:20:13 - `63b58074-9350-43f0-9772-feffb6fc0ffe.jsonl`
- `/ll:refine-issue` - 2026-08-21T20:17:18 - `05b36e3e-cf1c-4269-a1c6-018fbadd4f92.jsonl`
- `/ll:verify-issues` - 2026-08-21T20:15:35 - `a2289dde-4d3d-4b79-aeb5-674049d28ccd.jsonl`
- `/ll:wire-issue` - 2026-08-21T20:08:28 - `323952ee-6da2-4c4d-9f9d-ddb206a14824.jsonl`
- `/ll:refine-issue` - 2026-08-21T19:52:58 - `3e6f73b9-57ce-496a-8cf5-9227a47117bc.jsonl`
