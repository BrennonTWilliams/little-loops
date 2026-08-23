---
id: EPIC-3290
type: EPIC
title: decide-issue option location and decision propagation correctness
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T19:24:50Z'
labels:
- epic
- issue-parser
- decide-issue
- locate-options
- pipeline
---

# EPIC-3290: decide-issue option location and decision propagation correctness

## Summary

Six open issues — five of them filed on 2026-08-21, four split out of each other during a single
refinement session — all describe defects in one pipeline: how an issue's *enumerable options* are
located in markdown, and what `/ll:decide-issue` does with the selection once one is made. They
were unparented and cross-linked only by ad-hoc `relates_to` edges.

Five of the six touch `scripts/little_loops/issue_parser.py`; two touch
`skills/decide-issue/SKILL.md`. Scheduling them independently means repeatedly re-deriving the same
span/tier/marker semantics, and — as **BUG-3287** documents explicitly — risks **BUG-3278** growing
its own private copy of fixes that belong in the shared precedence chain.

The epic exists to make the shared boundary explicit and to fix the locator *before* the consumers
that misbehave because of it.

## Motivation

`/ll:decide-issue` is the gate between a refined issue and an implementable one. Every defect here
degrades it in a way that is invisible at the call site:

- Option spans that absorb trailing prose feed scoring agents analysis text as an option
  description (**BUG-3279**).
- Bold prose (`**Option A evidence**:`) is counted as a real option, inflating the option set with
  commentary about options (**BUG-3285**).
- The idiomatic option shape in this repo — `- **(a) Make the override real.**` — matches **zero**
  tiers, and any tier match anywhere in the section hides a co-located prose decision directive.
  Measured over the live corpus: **6 issues** are misparsed today with no code change required
  (**BUG-3287**).
- Shared subject vocabulary is treated as option-discriminating, firing `unapplied_decision`
  against ordinary terms — ~23 spurious reports on ENH-3277 alone (**BUG-3289**).
- `decision_needed: false` is written unconditionally even when only the highest-precedence
  decision point was ever extracted, so downstream `/ll:wire-issue`, `/ll:ready-issue`, and
  `/ll:manage-issue` treat a partly-decided issue as settled (**BUG-3278**).
- Prose recommending a *losing* option survives the decision verbatim, so the file ships with
  implementation steps for work that was decided against (**ENH-3280**).

The first four are locator defects; the last two are consumer defects that inherit them.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `locate_enumerable_options` (`:2209`),
  `_locate_directive_alternatives` (`:2137`), `_OPTION_PATTERNS` (`:1949`),
  `_option_block_spans` (`:1405`), `_iter_option_blocks` (`:2287`),
  `_decision_identifiers` (`:1351`), `_unapplied_decision` (`:1449`; its
  `discriminating = rej_ids - sel_ids` line is `:1530`), `LocatedOptions.to_dict()` (`:1997`).
  Shared by BUG-3279, BUG-3285, BUG-3287, BUG-3289, and read by BUG-3278.
  > Anchors refreshed 2026-08-21 post-`f39a417e`, which shifted every anchor in this file by
  > +58 to +100 lines. The pre-refresh values (`:2134`, `:2062`, `:1530`-as-function) were stale.
  >
  > **Drift recurred the same day** — `93270c37` (BUG-3286, outside this epic) shifted
  > `issue_parser.py` a further **+50** lines and `test_issue_parser.py` **+332**
  > (`locate_enumerable_options` 2209→2259, `TestUnappliedDecision` 4757→5089). **Do not
  > hand-refresh a third time.** Every citation in this epic and its children carries its symbol
  > name; treat all line numbers as as-of `f39a417e` and re-resolve by symbol at implementation
  > time.
- `scripts/little_loops/cli/issues/check_decidable.py` — the `located.count >= 1` gate at `:36`
  (BUG-3287 part 1b; required under its recommended return shape).
- `skills/decide-issue/SKILL.md` — Phases 2.5, 3, 3b, 4, 6, 7a, 7b (BUG-3278, BUG-3287, ENH-3280).
  > ⚠ **Shared line budget — 7 lines remain.** `SKILL.md` is **493 lines** against a hard **500-line
  > cap** enforced by `TestSkillLineLimit` (`scripts/tests/test_enh494_skill_companions.py:73-86`),
  > and three children write to it. See § *Shared constraint — the decide-issue SKILL.md line
  > budget* below; do not plan any of the three skill edits without reading it.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/` — `locate-options`, `check-decidable`, `format-check`
  entry points that surface the locator's output.
- `/ll:wire-issue`, `/ll:ready-issue`, `/ll:manage-issue` — downstream consumers of
  `decision_needed`.

### Tests
- `scripts/tests/test_issue_parser.py` — `TestUnappliedDecision` (`:4757`),
  `TestUnappliedDecisionLiveCorpusSweep` (`:5063`; its
  `test_corpus_sweep_does_not_crash` at `:5085`).
  > Corrected 2026-08-21: `:5005` was stale and is cited from **three** places — this table,
  > BUG-3285's *Tests* and *Codebase Research Findings*, and BUG-3287's *Codebase Research
  > Findings* — all of which name it as the scaffolding model for a **required new** corpus
  > differential. All four citations corrected.
- `scripts/tests/test_issue_parser_unresolved.py` — `TestLastOptionSpanBoundary` (`:817`).
- `scripts/tests/test_enh494_skill_companions.py` — `TestSkillLineLimit` (`:73`), the gate the
  three skill-touching children must budget against.

### Documentation
- `docs/reference/CLI.md` § `ll-issues locate-options` / `check-decidable` if the precedence
  chain's contract changes.

## Impact

- **Priority**: P2 — the highest child priority. Not user-facing breakage, but it corrupts the
  input to every decision the issue pipeline makes, with measured live misparses (6 issues for
  BUG-3287, ~23 spurious reports for BUG-3289).
- **Effort**: Large — five of six touch one file, which makes the chain serial. **Three** items are
  substantial, not two: BUG-3278 (`size: Large` — frontmatter set, Impact aligned 2026-08-21),
  ENH-3280 (`size: Large`), and **BUG-3287 (`size: Very Large`)** — two parser parts plus
  three mandatory consumer edits, a corpus differential, and five documentation sites.
  > Restated 2026-08-21. This bullet previously read *"each step small … BUG-3278 and ENH-3280 are
  > the two substantial items"*, which is contradicted by BUG-3287's own `size: Very Large`
  > frontmatter. BUG-3285 is nominally `size: Medium` but its Effort bullet was *"repriced upward"*
  > and it still owes a design pass (see § *Unscheduled work*), so treat that size as a floor.
- **Risk**: Medium — `issue_parser.py` is load-bearing for the whole `.issues/` corpus, and the
  span semantics have already been reopened once. The live-corpus sweep tests are the safety net.

## Children

Implementation order is bottom-up: locator primitives, then the decision model, then propagation.

- **BUG-3279** (P3) — ✅ **`done` 2026-08-21.** Last option's span ran to section end and absorbed
  trailing prose. Parser fix landed in `f39a417e`; the reopened test-only residual (ENH-2692
  new-report-direction fixture + three frozen corpus-invariant fixtures) closed with no source
  change. Its item 3 was split out as BUG-3289.
- **BUG-3285** (P3) — `bold_label` matches by prefix only, so `**Option A evidence**:` and
  `**Option B was already applied**:` are spanned as options. **Needs a design pass before
  implementation**: its sketch regex was measured against the full corpus on 2026-08-21 and drops
  two real *selected* options (`**Option A′ (SELECTED)**` in BUG-3177, `**Option C′ (selected)**`
  in BUG-3253), gains 3 matches by crossing newlines, flips 2 tiers, and moves 1 resolved section.
  Its stated acceptance bar is also unachievable — 21 of 26 repeated-letter issues repeat for a
  legitimate reason. See that issue's § *Corpus differential*. **Design pass resolved 2026-08-21
  (epic review)** — all three sub-decisions (identifier shape, title extent, regex convergence)
  are recorded with rationale in that issue's § *Decision Rules* and `decision_needed` is
  cleared. `/ll:decide-issue 3285` could not have made them — see § *Unscheduled work* below,
  corrected.
  > **Encoding settled and both differentials run 2026-08-22 (review pass).** The composed
  > encoding recorded at the design pass *also* dropped two real options (`FEAT-2339`'s
  > glob-bearing titles, ``` `parallel.epic_branches.*` ```) because its line-bounded title class
  > excluded the literal `*`; corrected to `(?:[^*\n]|\*(?!\*))*` and re-measured. Final:
  > **8 files change, 7 of them `done`/`cancelled`/`deferred`**, the one `open` file
  > (`FEAT-2186`) improves, no real option is lost, and 0 test fixtures break. Risk repriced
  > Medium-High → **Medium**. See that issue's § *Composed-encoding differential*, now the
  > baseline to implement against.
- **BUG-3296** (P3) — filed 2026-08-22. `_OPEN_QUESTION_SIGNAL_RE` counts a *citation of* an open
  question (`§ *Open question*`, `(see Open Question)`, `` `"open question"` `` in a code span) as
  an unresolved hedge. The unnumbered sibling of the already-done **BUG-3169**, which added the
  same discriminator for *numbered* citations only. Belongs to this epic because
  `ll-issues check-open-questions` exits 0 only when
  `unresolved_options == 0 **and** open_questions == 0` — so this defect and **BUG-3285** each own
  half of one gate feeding `resolve-decision.yaml:63`, `refine-to-ready-issue.yaml:404`, and
  `autodev.yaml`. Measured: **14 issues change, 0 counts rise (pure subtraction), 11 gate exit
  codes flip 1→0**; all 16 suppressed items hand-verified as citations. Independent of BUG-3285 —
  either order. **BUG-3278:346-349** diagnosed the conjunction first and routes around the command
  rather than fixing it, so the two are complementary, not overlapping.
- **BUG-3287** (P2) — two defects in the shared precedence chain: a tier match anywhere preempts
  the Pattern E directive heuristic, and the `bullet` tier cannot see a bold-wrapped marker.
  **Sequence before BUG-3278** — BUG-3278 otherwise re-fixes both inside its own new group
  iterator rather than consuming a corrected chain. Its recommended `residual_directive` return
  shape requires three consumer edits (`to_dict()`, `check_decidable.py`, Phase 3 reporting) or it
  changes no observable behavior; those are now parts 1a–1c of that issue.
  > ⚠ **Two corrections landed 2026-08-21, both in that issue.** (i) Option B does **not** prevent
  > the `count == 1` false-clear its *Ordering constraint* claims it prevents — verified on
  > BUG-3229. (ii) Part **1c** is dead on arrival if BUG-3278 lands next, because BUG-3278 part 5
  > re-points Phase 3 off `locate-options` entirely; part 1c is now **deferred to BUG-3278** while
  > parts 1a/1b stay required. Read that issue's *Decision Rules* before scheduling it.
- **BUG-3289** (P2 — raised from P3 2026-08-21, epic review: hard blocker of P2 ENH-3280) —
  `_decision_identifiers` extracts every backticked span >= 3 chars as
  option-discriminating, with no filter for the issue's shared vocabulary. Candidate rule already
  recorded: subtract identifiers appearing in the title/Summary or in any section preceding
  `## Proposed Solution`. **Now the `blocked_by` prerequisite for ENH-3280 — i.e. the head of this
  epic's critical path.** Its two scope questions refused a default and it carried
  `decision_needed: true`; **`/ll:decide-issue 3289` ran 2026-08-21 and both are now decided**
  (narrow title+Summary scope; a separate `_shared_subject_identifiers` helper), `decision_needed:
  false`. **Still owes refine → wire → verify before implementation** — it has had none of the
  three, and the decision was therefore made against unverified claims.
- **BUG-3278** (P2) — introduces the **decision group** model: one group per decision point,
  resolved as a unit, so `decision_needed` is cleared only when every group is settled. The first
  consumer-side fix, and the largest. Six pre-implementation review rounds; its round-5
  `provisional_e` suppression matrix was re-verified against the live parser on 2026-08-21 and
  reproduces exactly.
- **ENH-3280** (P2, `blocked_by: BUG-3289`, `depends_on: BUG-3278`) — reconcile the rest of the
  document against the selection instead of writing only the three existing markers. Genuinely
  last.

### Dependency edges (revised 2026-08-21)

Declared in frontmatter: `BUG-3289 -> ENH-3280`, `BUG-3278 -> ENH-3280`.

Two edges were corrected after review:

- **`BUG-3279 -> ENH-3280` re-pointed to `BUG-3289 -> ENH-3280`.** ENH-3280's Phase 7c drives its
  prose rewrites off `_unapplied_decision`'s report list, and its own Motivation makes a quiet
  detector the prerequisite. BUG-3279 fixed the *span* layer of that noise and is now `done`; the
  surviving noise (~23 reports on ENH-3277, 2 new on ENH-2692) is BUG-3289's. The old edge gated a
  P2 on test-only work while leaving the real dependency undeclared.
- **`BUG-3285 -> BUG-3289` demoted to `relates_to`.** BUG-3285 makes BUG-3289's corpus measurement
  cleaner but is not a correctness dependency — BUG-3289's guard (`new_reports == 0` against the
  tree it lands on) is self-contained, and its report-total drop is already declared an observation
  rather than an assertion. A hard block would hold BUG-3289 behind BUG-3285's redesign for no gain.

The BUG-3287-before-BUG-3278 ordering remains a *design* preference recorded in BUG-3287's own body,
not a hard block.

> ⚠ **The independence measurement below covers `_OPTION_PATTERNS` only (added 2026-08-21, epic
> review).** BUG-3285 edits **two** regexes — its convergence decision hoists the bold-marker
> sub-pattern into a constant shared with `_OPTION_HEADING_RE`, whose consumers
> (`_option_block_spans` → `_unapplied_decision` → `format-check`/`check-design`;
> `_iter_option_blocks` → `count_unresolved_options` → `check-open-questions` →
> `resolve-decision.yaml`, `refine-to-ready-issue.yaml`, `autodev.yaml`) are disjoint from
> `locate_enumerable_options`' and **invisible to a `count`/`heading` differential**. BUG-3287 does
> not touch that regex, so the two issues remain independent in fact — but the evidence below does
> not reach that surface, and BUG-3285 now owes a **second** corpus differential for it (that
> issue, § *Second blast radius*). That differential is also where BUG-3285, BUG-3289, and
> BUG-3278's assertion (c5) collide: all three move `_unapplied_decision`'s output, so whichever
> lands later re-baselines rather than asserting against a fixed commit.

**BUG-3285 and BUG-3287 are measured independent.** Both edit `_OPTION_PATTERNS` (element `[1]` and
element `[3]` respectively) and neither declares an edge to the other. Running
`locate_enumerable_options` over all of `.issues/` in four configurations (baseline / each alone /
both) on 2026-08-21: 10 files change under BUG-3285, 22 under BUG-3287, 32 under both — with **0
overlapping files, 0 composition surprises, and no `count` drop appearing only when both land.**
They may land in either order. This is corpus-dependent, not structural: whichever lands second
re-runs its own differential against the post-first tree.
- **BUG-3296** — check-open-questions counts citations of an open question as unresolved hedges (open)


## Goal

`/ll:decide-issue` sees exactly the options an author wrote — no absorbed prose, no commentary
counted as an option, no idiomatic shape unreachable, no directive preempted — and a decision it
records is complete and propagated through the whole document.

## Scope

In scope: the six children above; the option-location precedence chain and its span semantics; the
decision-group model and its propagation into the issue body.

Out of scope: the priority-source drift in `IssueParser` (**BUG-3286**, independent); evidence-quote
validation (**BUG-3282** / **ENH-3283**); `blocked_by` promotion in refine-issue (**ENH-3284**); any
change to how issues are *scored* once options are correctly located.

### Accepted divergence — three detectors, three answers (recorded 2026-08-21)

No child owns this, and each scopes it out defensibly, so it is recorded here as an epic-level
accepted outcome rather than left undiscovered:

| Probe | Sees, after this epic |
| --- | --- |
| `ll-issues check-decidable` | `_OPTION_PATTERNS` tiers 1–4 (with `[3]` widened) **+** `residual_directive` |
| `ll-issues check-open-questions` | `_OPTION_HEADING_RE` Patterns 1–2 only — no bullet tier, no directives |
| `check-unresolved-decisions` (proposed by BUG-3278; does not exist yet) | tiers 1–4 **+** directives, under `include_approximate_tiers=True` |

Three different answers to "does this document still hold an undecided decision point?", and
`resolve-decision.yaml:47-67` chains two of them (`check-open-questions || check-decidable`). The
scope-outs are individually sound — BUG-3287 leaves `_iter_option_blocks` alone because widening its
conservatism is a loop-gate change with its own blast radius (the ENH-2446 comment at `:2271-2275`
is deliberate), and BUG-3278 part 2 leaves `locate_unresolved_options` untouched because it and the
new group probe count different things. The divergence nonetheless **widens** as a result of this
epic: `check-decidable` learns the `- **(a) …**` shape and directives while `check-open-questions`
does not.

Accepted for now. File as this epic's follow-up if a gate misroute is observed live; do not fold it
into any child.

### Follow-up — the third invisibility shape → **filed as BUG-3293** (2026-08-22)

> ✅ **Filed 2026-08-22 as BUG-3293** (P3, `relates_to` this epic — deliberately **not** a seventh
> child; see the closing paragraph). It carries `decision_needed: true` for its route A/B choice.
> The scoping below is retained as the record of why it exists; BUG-3293 is now the authority on
> its contents.

This epic recorded the same finding three times (§ *Unscheduled work*, § *Undeclared decision
points*, and BUG-3285 § *Program Design → Decision Rules*) without giving it an issue number, so
it would not have survived epic closure. It is not a candidate — it has already cost work twice
inside this epic's own scope:

- BUG-3285's design pass had to be done by hand at epic review because `/ll:decide-issue 3285`
  could not see its decision points;
- BUG-3278 round 6 item 3 found its own part-3 decision point unreachable for the same reason.

The shape: **bold *numbered* items under `## Program Design → ### Decision Rules`**. No
`_OPTION_PATTERNS` tier matches it — including after BUG-3287's part-2 widening, verified against
the widened regex — and Pattern E never scans that section, because
`_DIRECTIVE_ALTERNATIVES_SECTIONS` is a 4-entry list (`Scope Boundaries`, `Proposed Change`,
`Proposed Solution`, `Open Questions`) that excludes `Program Design` entirely. Note the asymmetry
this exposes, which is the likely fix surface: `_DECISION_DIRECTIVE_SECTIONS` — the list
`_unapplied_decision` scans for *unapplied* decisions — is a **5**-entry list that **does** include
`Program Design`. So the codebase already asserts that decisions live in `Program Design`; only the
locator disagrees.

Scope it as: reconcile the two section lists, and/or add a tier for the bold-numbered shape. Both
touch the shared precedence chain, so it inherits BUG-3287's blast-radius discipline (corpus
differential, pinned exceptions) — which is the reason it is a follow-up rather than a seventh
child of an epic that is already large.

This is a direct restatement of this epic's own Goal (*"no idiomatic shape unreachable"*), on a
shape the epic proved unreachable using its own children as the corpus.

### Shared constraint — the decide-issue SKILL.md line budget (added 2026-08-21)

`skills/decide-issue/SKILL.md` is **493 lines**. `TestSkillLineLimit`
(`scripts/tests/test_enh494_skill_companions.py:73-86`) fails the suite for any `SKILL.md` over
**500**. That leaves **7 lines** of headroom, and three children spend it:

| Child | SKILL.md edits |
| --- | --- |
| BUG-3287 | part 1c — Phase 3 `residual_directive` reporting rule |
| BUG-3278 | part 5 — Phase 2.5→3 handoff, Phase 3 group sourcing + `unresolved[0]` rule, Phase 3b step 3 A–C callout, step 4 gate, Phase 7a per-group idempotency + per-tier marker placement (**including a fenced markdown example**), Phase 7b gate, Phase 9 line |
| ENH-3280 | Phase 7c in full — four rewrite categories, bounded-scope statement, idempotency rule |

Combined that is well over 100 lines against a 7-line budget. **No child mentions the cap**, and
`skills/wire-issue/SKILL.md` is already sitting at exactly 500, so there is no slack elsewhere and
no precedent for raising the limit.

**Epic-level rule, binding on all three children:** overflow extracts into
`skills/decide-issue/reference.md` (144 lines today, already the Phase 9 Output Report Template's
home) following the ENH-494 companion pattern — `SKILL.md` keeps the imperative phase steps and a
`See [reference.md](reference.md) for …` pointer at the extraction point;
`reference.md` takes the tables, worked examples, marker-placement matrices, and rewrite-category
catalogues. `test_enh494_skill_companions.py::test_skill_links_to_companion` enforces the pointer.

Each child must state its own line delta and, if it exceeds its share, name what it extracts.
**Whichever lands first should perform the extraction pass**, so the two that follow inherit
headroom rather than each re-litigating it. On current sequencing that is BUG-3287 — the smallest
of the three edits, which makes it a poor place to absorb the refactor.

> **Ownership pinned 2026-08-21 (epic review):** the extraction lands as a **standalone
> preparatory commit** owned by **BUG-3287 Implementation Step 0** (target: `SKILL.md` ≤ 460
> lines, no behavior change, verified by `test_enh494_skill_companions.py`). It executes before
> any child's SKILL.md edit; BUG-3278 and ENH-3280 then only need their budget checks. This
> closes the same described-but-unscheduled gap this epic called out for BUG-3285's design pass.
>
> ⚠ **That verification is insufficient (added 2026-08-21, same review).**
> `scripts/tests/test_decide_issue_skill.py` holds **77** `test_*` methods that slice `SKILL.md` by
> phase heading and assert on its prose — moving text out is exactly what breaks them, and
> `TestSkillLineLimit` cannot see it. **Step 0's gate is both files.** Rule: any string asserted in
> `test_decide_issue_skill.py` stays in `SKILL.md`, or its assertion moves to `reference.md` in the
> same commit. Extract reference material (tables, matrices, fenced examples) in preference to
> imperative phase prose, since the assertions target the latter.

### Unscheduled work — BUG-3285's design pass (added 2026-08-21; resolved same day)

BUG-3285's sketch regex failed its own corpus differential on four counts, and its *Program
Design → Decision Rules* named two sub-rules it explicitly refused to default (identifier shape;
title extent — *"Pin one and pin it by test"*), plus an unanswered *"should the two regexes
converge?"* open question.

**Resolved 2026-08-21 (epic review) by deciding all three by hand.** The `/ll:decide-issue 3285`
route originally prescribed here was measured unworkable: the decision points live under
`## Program Design → ### Decision Rules` as bold *numbered* items — a shape no `_OPTION_PATTERNS`
tier matches even after BUG-3287's part-2 widening (verified against the widened regex), in a
section outside `_locate_directive_alternatives`' 4-section scan list, so Pattern E never sees
them either. The skill's interactive path exits "nothing to decide"; its auto path parks for
human review without deciding. The decisions and their rationale are recorded in BUG-3285
§ *Decision Rules*; Epic Success Criterion 5 (previously miscited here as Criterion 4) is their
acceptance guard.

### Undeclared decision points on this epic's own children (added 2026-08-21)

Three children carry unresolved decision points with no `decision_needed: true` — the exact defect
class this epic exists to fix, on the epic's own files. Measured 2026-08-21:

```
ll-issues check-decidable 3289  →  Decidable: 2 enumerable option(s), provisional_e, §Proposed Solution
ll-issues check-decidable 3287  →  Decidable: 2 enumerable option(s), bold_label,    §Program Design
ll-issues check-decidable 3285  →  OPTIONS_MISSING: count 0, pattern None
```

> ⚠ **Read these as a *visibility* probe, not a decidedness oracle (corrected 2026-08-21).**
> `check-decidable` reports whether options can be located, not whether they have been resolved:
> re-run after BUG-3289's decide pass, `check-decidable 3289` **still** exits 0 with
> `2 enumerable option(s)` (verified). So a hit here is evidence the gate *can see* a decision
> point, and a miss is evidence it cannot — neither is evidence about whether a decision was made.
> Treating the two as the same thing is precisely BUG-3278's subject, and this section leaned on
> the conflation while making the epic's own dogfood argument.

- **BUG-3289** explicitly refused a default (*"pick one scope per bullet, do not leave
  unaddressed"*) and carried `decision_needed: true`. Its decision points **are** visible to the
  gate (the `provisional_e` pair above), so `/ll:decide-issue 3289` worked — **and ran, on
  2026-08-21.** Both scope questions are decided with recorded rationale and `decision_needed` is
  `false`.
  > Corrected 2026-08-21: this bullet read *"must run before implementation"* after the pass had
  > already run. What **is** still owed on BUG-3289 is refine → wire → verify — see the Children
  > entry above. Its own body carried the same stale instruction and has been corrected too.
- **BUG-3285**'s refusals (*"Pin one and pin it by test"*) were decided by hand at epic review
  (2026-08-21) and its `decision_needed` is cleared — see § *Unscheduled work* above for why
  `/ll:decide-issue` could not reach them.
- **BUG-3287** and **BUG-3278** record recommendations, so they are treated as settled — with the
  correction in BUG-3287's *Decision Rules* (its Option B does not, as written, prevent the
  false-clear it claims to; see that issue).
- **BUG-3287 and BUG-3278 each carry a spec defect found at this review; both are corrected in
  their own bodies and neither changes this epic's shape.** (i) BUG-3287 typed
  `residual_directive` as a singular `LocatedOption`, but `_locate_directive_alternatives` returns
  `LocatedOptions` — corrected to the container type, with a `--json` shape assertion added.
  (ii) BUG-3278 prescribed retiring a `provisional_e` group by appending
  `> **Selected:**` to the directive line; measured, `_SELECTED_CALLOUT_RE` is line-anchored and
  does **not** match that form, so the marker is invisible to every callout consumer including
  `is_group_resolved`. The prescribed form is now the `**RESOLVED — …**` prefix, and the retirement
  mechanism is stated as probe suppression rather than resolution.
- BUG-3285's sub-rules are invisible to the locator entirely (`count 0`) — but **not** as an
  instance of BUG-3287's defect 2 (claim corrected 2026-08-21, epic review). They are bold
  *numbered* items under `## Program Design → ### Decision Rules`: no tier matches that shape
  even after BUG-3287's widening, and Pattern E never scans that section. A **third**
  invisibility shape — kept as the epic's dogfood datapoint, and **filed 2026-08-22 as BUG-3293**
  (see § *Follow-up — the third invisibility shape*). The divergence recorded in § *Accepted
  divergence* remains unfiled and is a separate question.

## Success Criteria

- [ ] All six children are `done` or `cancelled`. *(BUG-3279 done 2026-08-21; five remain.)*
      > Unchecked 2026-08-21 — this box was marked `[x]` while five of six children were open, with
      > a parenthetical saying so on the same line.
- [ ] `- **(a) …**` bullet options resolve on the live `.issues/` corpus, and a document whose only
      decision point is a tier-preempted Pattern E directive reports **exit 0** from
      `ll-issues check-decidable`. **Stated at the consumer, not the dataclass** — BUG-3287's
      recommended `residual_directive` shape leaves `locate-options` output byte-identical for all
      six preempted issues unless its parts 1a–1c land, so "the directive is represented" is not
      evidence the defect is fixed.
- [ ] `_unapplied_decision`'s corpus report set **strictly decreases** with `new_reports == 0`, and
      the ENH-2692 `final_score` reports no longer fire.
      > **Restated 2026-08-21.** This criterion previously read *"fires no report attributable to
      > shared subject vocabulary across the live corpus"* — an absolute that BUG-3279 warns against
      > twice (*"Do not assert zero — this fix cannot reach zero"*) and that BUG-3289 cannot promise:
      > its two scope options (title+Summary only vs. everything above `## Proposed Solution`) have
      > materially different reach, and it deliberately refuses a default. Assert the relation
      > BUG-3289 actually commits to; record the report-total drop as an observation.
- [ ] An issue with two decision points retains `decision_needed: true` until both groups resolve,
      on **both** clearing paths — Phase 7b and Phase 3b step 4 (the `AUTO_MODE` path).
- [ ] No real option is lost from the live corpus: `BUG-3177` and `BUG-3253` keep their current
      `count`, and no file's resolved `heading` changes **except changes a child pins as
      intended** (ENH-3264 moves to §`Proposed Solution` under BUG-3287's part 2). *(BUG-3285's
      guard — the class of regression its sketch regex was measured to produce.)*
      > Exception clause added 2026-08-21 (epic review): the unscoped form was falsified by
      > BUG-3287's own pinned, declared-intended ENH-3264 heading move.
- [ ] **A document whose only decision point is a preempted directive does not hit Phase 3's
      `count == 1` clear branch.** Measured on `BUG-3229`: today `count 2 / provisional_e`; with
      BUG-3287 part 2 applied, `count 1 / bullet`. Under BUG-3287's *recommended* Option B, part 1
      leaves `count` byte-identical to the tier result, so the collapse survives part 1 and
      `SKILL.md:187` still clears `decision_needed`. Assert the **branch**, not the field's
      existence — see BUG-3287 § *Ordering constraint*, corrected 2026-08-21.
- [ ] **Bold prose is no longer counted as an option**: `ENH-2967` reports `count 2` (not 4) and
      `BUG-1484` reports `count 2` (not 4), pinned by ID. *(Added 2026-08-21, epic review —
      BUG-3285's positive criterion. Criterion 5 above is only its **non**-regression guard: every
      other criterion this epic states for BUG-3285 asserts that real options survive, and nothing
      asserted that the defect it exists to fix is actually fixed. A do-nothing implementation
      passed the criteria set as written.)*
- [ ] **`residual_directive` carries the directive's heading and every alternative** — the
      `locate-options --json` payload for a preempted issue shows a nested
      `{count, pattern: "provisional_e", heading, options}` object with `len(options) == 2` on a
      two-alternative directive. *(Added 2026-08-21, epic review: BUG-3287 specified the field as a
      singular `LocatedOption`, which cannot hold a heading and drops the second alternative. The
      end-to-end guard in Criterion 2 passes on the truncated shape.)*
- [ ] `skills/decide-issue/SKILL.md` is **≤ 500 lines** after all three skill-touching children have
      landed — `test_enh494_skill_companions.py::TestSkillLineLimit` passes, **and
      `scripts/tests/test_decide_issue_skill.py` (77 phase-text assertions against `SKILL.md`
      prose) still passes.** See § *Shared constraint — the decide-issue SKILL.md line budget*.
      > Second clause added 2026-08-21 (epic review): the line-limit test cannot detect the
      > extraction pass moving an asserted phrase out of `SKILL.md`, which is the failure mode the
      > extraction actually has.
- [ ] `python -m pytest scripts/tests/` passes.

## Related Key Documentation

- `.claude/CLAUDE.md` § Issue File Format — status/supersession semantics the decision model writes into.
- `docs/reference/CLI.md` § `ll-issues locate-options` — the locator's documented contract.

## Status

**Open** | Created: 2026-08-21 | Priority: P2