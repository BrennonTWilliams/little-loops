---
id: BUG-3293
type: BUG
title: Bold-numbered decision points under Program Design are invisible to both the
  tier scan and Pattern E
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
captured_at: '2026-08-22T20:14:20Z'
decision_needed: false
size: Medium
labels:
- issue-parser
- locate-options
- decide-issue
- pipeline
relates_to:
- EPIC-3290
- BUG-3287
- BUG-3285
- BUG-3278
---

# BUG-3293: Bold-numbered decision points under Program Design are invisible to both the tier scan and Pattern E

## Summary

A decision point written as **bold numbered items** under `## Program Design → ### Decision Rules`
is invisible to every branch of the option-location precedence chain: no `_OPTION_PATTERNS` tier
matches the shape, and `_locate_directive_alternatives` (Pattern E) never scans that section. The
document reports `count 0, pattern None` and `ll-issues check-decidable` exits 1 — "nothing to
decide" — on a file that holds a live, explicitly-refused-a-default decision.

This is the **third** distinct invisibility shape found in the option locator, after BUG-3287's two
(a tier match preempting Pattern E, and the `bullet` tier not seeing bold-wrapped markers). It was
discovered by EPIC-3290 using its own children as the corpus, and it is not hypothetical: it has
already cost work twice inside that epic's scope.

## Current Behavior

Two independent misses, both required for the shape to be invisible.

**1. No tier matches bold numbered items.** The relevant tier is `_OPTION_PATTERNS[2]`
(`numbered`), which is:

```python
r"^\d+\.\s+(?:\*\*Option|[A-Z][^.]*\bapproach\b)"   # MULTILINE
```

The bold alternative requires the run to begin with the literal `**Option`. A decision written as
`1. **Identifier shape.** …` / `2. **Title extent.** …` matches neither that nor the
`[A-Z]…\bapproach\b` alternative. Measured against live `_OPTION_PATTERNS` (2026-08-22):

```
"1. **Identifier shape.** The identifier is not `[A-Za-z0-9]+` alone"  -> tiers []
"2. **Title extent.** Whether a title may span more than one physical line" -> tiers []
```

**The shape is still unreachable after BUG-3287's part-2 widening.** That fix hoists `\*{0,2}` in
`_OPTION_PATTERNS[3]` (the `bullet` tier), which is dash-anchored (`^[-*]`) and cannot match a
numbered item at all. Verified against the widened regex directly — both shapes return `False`. So
this is **not** an instance of BUG-3287's defect 2 and is not fixed by it.

**2. Pattern E never scans the section.** `_DIRECTIVE_ALTERNATIVES_SECTIONS` is a four-entry tuple:

```python
("Scope Boundaries", "Proposed Change", "Proposed Solution", "Open Questions")
```

`Program Design` is not in it, so a prose decision directive there is never probed regardless of
its wording.

**The asymmetry that makes this a defect rather than a design choice:** the sibling constant
`_DECISION_DIRECTIVE_SECTIONS` — the list `_unapplied_decision` scans for decisions that were made
but not applied — is a **five**-entry tuple that **does** include `Program Design`:

```python
("Proposed Solution", "Program Design", "Implementation Steps", "Files to Modify", "Acceptance Criteria")
```

So the codebase already asserts that decisions live in `Program Design`. `format-check` will report
an *unapplied* decision there; the locator will not admit a decision *exists* there. Only the
locator disagrees with the rest of the module.

Live case (BUG-3285, measured 2026-08-22, pre-fix — see this issue's own Decision Rules section for
the post-fix re-measurement, which this defect is now closed against):
<!-- ll-evidence-ok: frozen pre-fix snapshot, deliberately superseded by this issue's own fix — BUG-3285 no longer returns count 0 as of the corpus differential in this issue's Decision Rules section -->
```
locate_enumerable_options(BUG-3285)   -> count 0, pattern None, heading None
_locate_directive_alternatives(BUG-3285) -> None
ll-issues check-decidable 3285        -> OPTIONS_MISSING: count 0, pattern None (exit 1)
```

BUG-3285's `### Decision Rules` at that moment held two decision points that its own text called
out as refusing a default (*"Pin one and pin it by test"*).

## Expected Behavior

A decision point written in a shape the repo's own issues use is reachable by the decidability
gate. Concretely: either the `numbered` tier admits a bold-label form that is not literally
`**Option X`, or `Program Design` is scanned for prose directives, or both — such that
`check-decidable` exits 0 on a document whose only decision point lives there, and
`/ll:decide-issue` can reach it.

Whichever route is taken, `_DIRECTIVE_ALTERNATIVES_SECTIONS` and `_DECISION_DIRECTIVE_SECTIONS`
should stop disagreeing about where decisions live, or the disagreement should be documented as
deliberate with its rationale.

## Motivation

`/ll:decide-issue` is the gate between a refined issue and an implementable one, and
`check-decidable` is the deterministic probe FSM loops route on
(`resolve-decision.yaml:47-67` → `refine` vs `decide`). A shape the gate cannot see is a decision
that silently never gets made — the issue proceeds through wire → ready → manage with an open
decision point in its body and nothing flagging it.

This has already happened twice, inside the epic that found it:

- **BUG-3285** — its three sub-decisions (identifier shape, title extent, regex convergence) had to
  be decided **by hand at epic review** because `/ll:decide-issue 3285` could not reach them.
- **BUG-3278** round 6 item 3 — found that its own part-3 `(a)`/`(b)` choice *"was itself an
  undecided decision point … in a file with no `decision_needed` flag to gate it."*

Both were caught by a human reading the file. Neither was caught by the gate that exists to catch
them. EPIC-3290 records this as its own dogfood datapoint three separate times.

## Proposed Solution

Two candidate routes; they are not exclusive and the choice needs a corpus differential before
either is committed to. **Both touch the shared precedence chain**, so this inherits BUG-3287's
blast-radius discipline: measure across all of `.issues/` before and after, pin every intended
change by ID, and assert no unpinned file's `count` or resolved `heading` moves.

**Route A — reconcile the two section lists.** Add `Program Design` (and possibly the rest of
`_DECISION_DIRECTIVE_SECTIONS`) to `_DIRECTIVE_ALTERNATIVES_SECTIONS`, so Pattern E probes the
section where the module already believes decisions live. Cheapest, and it fixes the *directive*
half without touching any regex. Blast radius is every document holding directive-shaped prose in
`Program Design` — unmeasured; that measurement is the first task.

**Route B — widen the `numbered` tier.** Let `_OPTION_PATTERNS[2]`'s bold alternative match a
bold-label numbered item generally, not only `**Option`. Higher risk: `^\d+\.\s+\*\*` is an
extremely common shape in this repo's issues (every bold-led numbered list in every
*Implementation Steps* section), so a naive widening would classify ordinary step lists as option
sets. Any encoding here needs a discriminator, and the corpus differential is mandatory rather than
advisory.

Route A is the more likely answer. Route B should not be attempted without first measuring how many
live files gain a spurious `numbered` match.

**Sequencing.** Land after BUG-3287, and re-measure against the post-BUG-3287 tree — that issue
moves 22 files' locator output and changes tier precedence, so any differential taken before it is
stale. This is a follow-up, not a blocker: nothing in EPIC-3290 depends on it.

### Part 3 — correct the diagnosis the probe prints (required under either route)

Independent of A vs B, and **required either way**: `cmd_check_decidable`
(`scripts/little_loops/cli/issues/check_decidable.py:42-52`) prints a *diagnosis* it cannot
support, and a remedy that follows from it:

```python
# ENH-2821: locate_enumerable_options() already scans the whole document
# (## Proposed Solution, the fallback sections, then every H2 section including
# nested H3s), so a count of 0 here means the document genuinely has none —
# not that the probe looked in the wrong place.
```
```
OPTIONS_MISSING: <ID> — decision_needed is true but no enumerable alternatives were
found anywhere in the document; run /ll:refine-issue <ID> --auto
```

**The comment is already factually wrong today**, before this issue's shape is considered — it
collapses two probes with different scopes into one claim about "the probe":

- The **tier** sweep *is* document-wide. `locate_enumerable_options` iterates `_iter_h2_sections`
  over every H2 (`issue_parser.py`, the `best`-selecting loop), so it does reach
  `## Program Design`. For tiers, "not that the probe looked in the wrong place" is true — it
  looked and matched nothing.
- The **directive** probe is *not*. `_locate_directive_alternatives` is bounded to the four
  sections in `_DIRECTIVE_ALTERNATIVES_SECTIONS`. For Pattern E, "the probe looked in the wrong
  place" is exactly what happened, and is this issue's defect 2.

**The category error outlives whichever route lands.** A probe observes an *absence*; it cannot
diagnose a *cause*. `count == 0` means "I found none" — indistinguishable from inside between
"none exist" and "some exist in a shape I don't parse." Fixing the shape in defects 1–2 removes
one known member of the second class; it does not empty the class, and the next unrecognized shape
reproduces this message verbatim.

Required changes:

1. **Correct the comment** to state the two probes' scopes separately, and drop the "genuinely has
   none" inference. This is a source-accuracy fix owed regardless of anything else here.
2. **Restate the message as an observation with both candidate causes**, e.g. *"no enumerable
   alternatives matched — either none are written, or they are in a shape the locator does not
   recognize (see BUG-3293)"*, keeping `/ll:refine-issue --auto` as the remedy for the first cause
   rather than as the unconditional instruction.

**Bounded severity, and be honest about it in review.** The FSM does **not** read this string:
`resolve-decision.yaml`'s `check_decision_decidable` (`:47-67`) routes `on_no → deposit_options`
and re-implements the same remedy itself, marker-bounded to one retry before falling through to
`run_decide`. So the cost of the wrong remedy today is one wasted refine pass, not a stall, and
this part is a correctness-of-reporting fix for humans and LLMs reading CLI output — not a
behavior fix. Do not let it expand into re-litigating `deposit_options`' premise, which is a
loop-gate change with its own blast radius.

**Not in scope here:** `cmd_check_decidable` also returns exit **1** for an unresolvable issue ID
(`:30-32`), conflating "not found" with "no options" — **filed as BUG-3294**, which found it is a
family-wide convention across all seven `check-*` probes, not specific to this one. Same file,
different defect; do not fold it in.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `_DIRECTIVE_ALTERNATIVES_SECTIONS` (route A) and/or
  `_OPTION_PATTERNS[2]`, the `numbered` tier (route B). Resolve both by symbol name, not line
  number — this file's anchors have drifted twice in a single day (`f39a417e`, `93270c37`).
- `scripts/little_loops/cli/issues/check_decidable.py` — the ENH-2821 comment (`:42-45`) and the
  `OPTIONS_MISSING` message (`:46-51`), per **part 3**. **Required under either route**, and the
  only part of this issue that is not conditional on the A/B decision. Promoted from *Dependent
  Files* — this is now an edited file, not just an affected consumer.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/check_decidable.py` — the `count >= 1` gate; a document going
  `0 → N` flips it to decidable
- `scripts/little_loops/cli/issues/locate_options.py` — `count`/`pattern`/`heading` move
- `scripts/little_loops/loops/oracles/resolve-decision.yaml:47-67` — live routing change
  (`refine` → `decide`) on any newly-visible file
- `/ll:decide-issue` Phase 2.5 — fewer `OPTIONS_MISSING` exits

### Tests

- A fixture whose only decision point is bold numbered items under
  `## Program Design → ### Decision Rules` — assert `check-decidable` exits 0 and
  `locate-options` reports it
- **Corpus differential (required):** `locate_enumerable_options` across `.issues/`, asserting no
  unpinned file's `count` decreases and no unpinned file's resolved `heading` changes. Scaffolding
  model: `TestUnappliedDecisionLiveCorpusSweep` in `scripts/tests/test_issue_parser.py`
  (skip-if-corpus-absent, `Path(__file__).resolve().parents[2]`, `rglob("*.md")`)
- **Route B specifically:** a negative control pinning that an ordinary bold-led numbered list in
  `## Implementation Steps` is **not** counted as an option set
- **Part 3:** extend `TestCheckDecidablePatternEDirective`
  (`scripts/tests/test_ll_issues_check_decidable.py:160-193`) — or add a sibling class — asserting
  the `OPTIONS_MISSING` stderr text names **both** candidate causes and no longer claims the
  document "genuinely has none". Assert on the observation-vs-diagnosis wording, not on the
  remedy substring alone: a message that still says `/ll:refine-issue` is fine, one that still
  asserts absence-as-cause is not

### Documentation

- `docs/reference/API.md` — `locate_enumerable_options` precedence prose
- `docs/reference/CLI.md` — `check-decidable` / `locate-options` coverage
- `docs/guides/DECISIONS_LOG_GUIDE.md` — Pattern E section coverage, if route A lands

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

- **`# BUG-NNNN:`/`# ENH-NNNN:` discriminator-comment convention confirmed landed, not just claimed.** Direct grep of `scripts/little_loops/issue_parser.py` confirms this pattern sits directly above changed constants at 8+ sites, including two immediately relevant ones: `# ENH-2443: deterministic (non-LLM) re-implementation…` directly above `_OPTION_PATTERNS` (`issue_parser.py:1993-1998`), and `# ENH-2936: Pattern E — un-preferenced decision directive…` directly above the Pattern E constants including `_DIRECTIVE_ALTERNATIVES_SECTIONS` (`issue_parser.py:2147-2153`). Other sites: `# BUG-3059` (`:1625`), `# BUG-3169` (`:2483`), `# BUG-3170` (`:2524-2525`), `# BUG-3279 Rule 3` (`:1367`). As of this research pass neither `_OPTION_PATTERNS` nor `_DIRECTIVE_ALTERNATIVES_SECTIONS` carries a `# BUG-3287:` comment yet — that issue is still `status: open`, so this issue inherits only the convention, not a landed comment to pattern-match against. `_DECISION_DIRECTIVE_SECTIONS` (the five-entry sibling this issue contrasts against) sits at `issue_parser.py:1347-1358` under `# ENH-3256: superset of _SUPERSEDED_DIRECTIVE_SECTIONS…`. Anchors are current as of this pass only — this file's anchors have drifted twice in one day per this issue's own note; resolve by symbol name for implementation.

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

- **Every prior tier/section-list change in `issue_parser.py` carries a `# BUG-NNNN:`/`# ENH-NNNN:` discriminator comment directly above the changed constant, explaining the new shape it discriminates** — evidence: `# BUG-3169:` above the hedge-regex alternative additions (`issue_parser.py:2483-2485`), `# ENH-2443:` above `_OPTION_PATTERNS` (`:1984-1998`), `# ENH-3256:` above `_DECISION_DIRECTIVE_SECTIONS` (explicitly framing it as a superset of `_SUPERSEDED_DIRECTIVE_SECTIONS`, `:1347-1358`), `# ENH-2936:` above the Pattern E constants including `_DIRECTIVE_ALTERNATIVES_SECTIONS` (`:2147-2153`). Neither of this bug's two target constants carries a `BUG-3287` comment yet (still open).
- **The four directive/section-list constants (`_DECISION_DIRECTIVE_SECTIONS`, `_DIRECTIVE_ALTERNATIVES_SECTIONS`, `_SUPERSEDED_DIRECTIVE_SECTIONS`, `_OPTION_FALLBACK_SECTIONS`) are independent bare `tuple[str, ...]` module-level constants with no shared base tuple or derivation** — evidence: `issue_parser.py:1344`, `:1352-1358`, `:2008`, `:2179-2184`. `_DECISION_DIRECTIVE_SECTIONS`'s comment documents its "superset" relationship to `_SUPERSEDED_DIRECTIVE_SECTIONS` in prose only, not in code — so Route A's proposed reconciliation would be introducing a first-of-its-kind coupling, not following an existing one.
- **Widening a regex tier in this module is done by adding a branch inside the same non-capturing group of the existing `re.compile(...)`, not by adding a new tier** — evidence: `_OPTION_PATTERNS[2]` already has this two-alternative shape (`r"^\d+\.\s+(?:\*\*Option|[A-Z][^.]*\bapproach\b)"`, `:2002`); `_DECIDE_IMPERATIVE_RE` (`:2154-2160`) and the Open-Question hedge regex (`:2509-2515`) follow the same additive-alternative style, each new alternative commented with the adding issue's ID (e.g. `# BUG-3169: item-leading declaration, numbered or not` at `:2511`).
- **`_OPTION_PATTERN_NAMES` is a parallel tuple zipped to `_OPTION_PATTERNS` with `zip(..., strict=True)`** (`:2093`) — any structural change to the tier count (as opposed to widening an existing tier's alternatives) requires `_OPTION_PATTERN_NAMES` (`:2012`) kept in lockstep or the zip raises.
- **Test shape for a new/changed tier**: one method per tier in `TestLocatedOptionsPatternNames` (`scripts/tests/test_issue_parser_unresolved.py:59-104`), asserting `located.pattern == "<tier_name>"` and `len(located.options)`. Notably, `test_numbered_pattern_name`'s existing positive fixture (`1. **Option A**: Do X.` / `2. **Option B**: Do Y.`) is itself the literal `**Option`-anchored shape this bug reports as too narrow.
- **Negative-control shape for "this shape must not be treated as decidable" exists in two house styles, not one**: a single `test_<shape>_not_<verb>` method (`test_out_of_scan_scope_section_not_matched`, `scripts/tests/test_issue_parser_unresolved.py:775-783`) and `@pytest.mark.parametrize` positive/negative pairs (`scripts/tests/test_issue_parser.py:4289-4313`).
- **Corpus-sweep precedent exists but only as a crash-safety check, never as a before/after diff**: `TestUnappliedDecisionLiveCorpusSweep.test_corpus_sweep_does_not_crash` (`scripts/tests/test_issue_parser.py:5399-5430`) only asserts `isinstance(reasons, list)`. No test in the suite currently asserts "no unpinned file's count/heading moves" — the diff shape this issue's Tests section calls for has no landed precedent to copy.
- **CLI-level fixture-pair precedent for a locator-shape change**: `TestCheckDecidablePatternEDirective` (`scripts/tests/test_ll_issues_check_decidable.py:160-193`) pairs a positive (`test_scope_boundaries_directive_exit_zero`) and negative (`test_bare_or_prose_without_imperative_marker_exit_one`) fixture using the shared `_write_issue()`/`_invoke()` subprocess helpers — the CLI-test shape to extend for the bold-numbered case.

### Tests — additional precedent (pattern-finder pass)

- **The corpus-differential scaffolding model exists and does exactly what this issue describes, no more.** `TestUnappliedDecisionLiveCorpusSweep` (`scripts/tests/test_issue_parser.py:5399`, method `test_corpus_sweep_does_not_crash` at `:5421`) skips via `pytest.skip` when `.issues/` is absent, resolves the corpus root via `Path(__file__).parent.parent.parent`, and walks it with `rglob("*.md")` — but its only assertion is `isinstance(reasons, list)` (crash-safety), not a before/after diff. The "no count decreases, no heading changes except pinned files" comparison this issue's Tests section calls for has **no landed precedent anywhere in the suite** — confirmed by reading the class, not inferred. `TestCorpusBaseline` (`scripts/tests/test_research_triage.py:540`) is the only other corpus-sweep shape in the codebase and is likewise single-pass (aggregate stats/thresholds), not a diff.
- **Direct precedent for the new bold-numbered-tier fixture**: `TestLocatedOptionsPatternNames` (`scripts/tests/test_issue_parser_unresolved.py:59-104`) is one test method per named tier, each building a minimal `content` string and asserting `located.pattern == "<tier_name>"` plus `len(located.options)` — e.g. `test_numbered_pattern_name`. This is the class shape to add the new fixture's assertion to.
- **Negative-control precedent for Route B** (an ordinary bold-led numbered list in `## Implementation Steps` must not count as an option set): two disagreeing styles coexist in the same two test files, with no single house convention — (a) `test_<shape>_not_<verb>` single-assertion methods, e.g. `test_out_of_scan_scope_section_not_matched` (`scripts/tests/test_issue_parser_unresolved.py:775`, itself a negative control on Pattern E's section scope), and (b) `@pytest.mark.parametrize` positive/negative fixture-pair methods (`scripts/tests/test_issue_parser.py:4289-4313`). Either is consistent with existing style.
- **CLI-layer precedent for Implementation Steps item 6** (verifying `check-decidable 3285`/`check-decidable 3293` stop reporting "nothing to decide"): `TestCheckDecidablePatternEDirective` (`scripts/tests/test_ll_issues_check_decidable.py:160`) already has a positive/negative fixture pair for Pattern E directives specifically — `test_scope_boundaries_directive_exit_zero` (`:164`) and `test_bare_or_prose_without_imperative_marker_exit_one` (`:190`) — using the shared `_write_issue()`/`_invoke()` subprocess-fixture helpers also used by `scripts/tests/test_issues_locate_options.py`'s `TestLocateOptionsJsonFlag` (`:65`). Extend this same shape for the bold-numbered case rather than introducing a new CLI-test pattern.

## Program Design

### Types

N/A — no new data structures. Route A edits a module-level tuple; route B edits a module-level
compiled pattern. `LocatedOptions` / `LocatedOption` are unchanged.

### Signatures

- `_OPTION_PATTERNS: tuple[re.Pattern[str], ...]` — `scripts/little_loops/issue_parser.py` — the
  four precedence tiers; element `[2]` is the `numbered` tier, the one route B widens
- `_DIRECTIVE_ALTERNATIVES_SECTIONS: tuple[str, ...]` — the four sections
  `_locate_directive_alternatives` scans; route A extends it
- `_DECISION_DIRECTIVE_SECTIONS: tuple[str, ...]` — the five sections `_unapplied_decision` scans;
  **unchanged**, and the reference point route A converges toward
- `_locate_directive_alternatives(content: str) -> LocatedOptions | None` — unchanged signature;
  route A changes only which sections it sees
- `locate_enumerable_options(content: str) -> LocatedOptions` — unchanged signature; the shared
  entry point whose output both routes move

All resolved by symbol name, not line number — this file's anchors drifted twice in one day
(`f39a417e`, then `93270c37`).

### Call Path

`ll-issues check-decidable` / `locate-options` → `cmd_check_decidable` / `cmd_locate_options` →
`locate_enumerable_options` → `_locate_options_in_text` (tiers 1–4, first-match-wins)
**and**, only when all tiers miss document-wide, `_locate_directive_alternatives` over
`_DIRECTIVE_ALTERNATIVES_SECTIONS`.

Under route A the directive probe's section list widens; under route B tier `[2]` starts matching
earlier in the chain, which also means it can **preempt** a Pattern E directive elsewhere in the
document — the BUG-3287 defect-1 interaction, and a reason to land after that issue rather than
before.

### Decision Rules

One decision, and it must be made before implementation: **route A (widen
`_DIRECTIVE_ALTERNATIVES_SECTIONS`) versus route B (widen the `numbered` tier) versus both.** The
two are not equivalent — A fixes the directive half and leaves the bold-numbered shape unmatched by
any tier; B fixes the tier half and leaves `Program Design` unscanned for prose directives. The
recommendation in *Proposed Solution* is A, on risk grounds, but it is a recommendation and not a
measurement: neither route has a corpus differential yet, and route B's spurious-match risk is the
open quantity that decides it.

**Decide it by measuring first**, in this order: (1) how many live files gain a Pattern E directive
under route A; (2) how many live files gain a spurious `numbered` match under route B. Then pick.

> **Corpus differential — measured 2026-08-22, full `.issues/` sweep (3197 files), via a scratch
> script monkeypatching `_DIRECTIVE_ALTERNATIVES_SECTIONS` / `_OPTION_PATTERNS[2]` in isolation and
> diffing `locate_enumerable_options()` output against baseline:**
>
> - **Route A** (`_DIRECTIVE_ALTERNATIVES_SECTIONS + ("Program Design",)`): **0 files gain a
>   directive**, corpus-wide. Zero risk, but also zero benefit as scoped — see the finding below.
> - **Route B** (`_OPTION_PATTERNS[2]` bold alternative widened from literal `\*\*Option` to any
>   bold-label run `\*\*[^*\n]+\*\*`): **1149 files (36% of the corpus) gain a `numbered` match**;
>   of those, **889 (77%) land on an ordinary non-decision heading** (`Implementation Steps`,
>   `Resolution`, `Root Cause`, `Impact`, `Summary`, etc.) — an ordinary bold-led numbered step is
>   this repo's dominant list convention, so a naive widening is a corpus-wide false-positive
>   generator, confirming the risk flagged in *Proposed Solution*. Only 260 (23%) land on a heading
>   that already plausibly holds real options (`Proposed Solution`, `Program Design`, `Decisions`,
>   `Options`).
>
> **New finding, not anticipated by either route as scoped: Route A does not fix either of this
> issue's own two motivating cases.** Verified directly: applying Route A to BUG-3293's own
> `Program Design → Decision Rules` text still returns `_locate_directive_alternatives() → None` —
> `_DECIDE_IMPERATIVE_RE` has zero matches (this section's prose is "must be made before
> implementation … versus … versus", not any of the five phrasings the regex requires: "decide
> before implementation", "must be decided", etc.) and `_INLINE_OR_RE` has zero matches (no literal
> "or" — the text uses "versus"). The same check against BUG-3285's already-resolved (by hand)
> `Decision Rules` prose also returns zero `_DECIDE_IMPERATIVE_RE` matches — Route A would not have
> made that decision visible either. **Route A alone, as scoped in *Proposed Solution*, is
> corpus-safe but does not close this bug**; closing it requires either widening
> `_DECIDE_IMPERATIVE_RE`/`_INLINE_OR_RE` alongside Route A, or a version of Route B narrow enough
> to avoid the 77% false-positive rate measured above (e.g. discriminating on section context or a
> label-then-period shape rather than "any bold run") — neither of which either route as currently
> written proposes. This choice is deferred back to a human: it is a scope decision (extend Pattern
> E's regex vocabulary vs. design a narrower tier-3 discriminator), not a risk measurement.

> **Follow-up measurement — a section-scoped Route B discriminator, measured 2026-08-22.** Restricted
> the widened bold-numbered-tier regex to fire only within specific sections (never via the
> whole-document H2 fallback that produced the 77% figure above), evaluated against the 2778
> baseline-`count==0` files:
>
> - Scoped to `## Program Design` (any subsection): **14 gains**. Inspecting all 14: only 1
>   (BUG-3285) is a genuine pending-alternative list; the other 13 are bold-numbered lists of
>   already-settled facts, findings, or rules (e.g. BUG-3232's "`--running` and `--status` are
>   declared as independent…", ENH-3261's "**RULING: kept indefinitely**") — a *different* use of
>   `### Decision Rules` and neighboring subsections that has nothing to do with pending choices.
> - Scoped to just `### Decision Rules` under `## Program Design`: **5 gains** (of 102 baseline-zero
>   files that even have this H3). Only 1 of 5 (BUG-3285) is genuine; the other 4
>   (BUG-3232, BUG-3286, ENH-3045, ENH-3261) are the same already-decided-rule shape, just narrower
>   in volume.
> - **Section scoping shrinks the absolute false-positive count (1149 → 14 → 5) but does not fix
>   precision** (1/14, 1/5): "bold-numbered items under Decision Rules" is used in this corpus for
>   two unrelated purposes — enumerating settled rules/rulings, and (rarely) presenting unresolved
>   alternatives — and no purely structural signal (regex shape, section, heading) tested so far
>   separates them.
> - **Neither genuine case trips Pattern E's own imperative vocabulary either**: verified against
>   BUG-3293's pristine original text and BUG-3285's resolved text — both return zero
>   `_DECIDE_IMPERATIVE_RE` matches. So "extend the imperative phrase list" is not a clean fix on its
>   own; it would need new phrasing curve-fit to these two examples, with no third example to
>   generalize from.
> - **Cost framing, per `_OPTION_PATTERNS`' own `# ENH-2443` comment** (`issue_parser.py:1993-1998`):
>   this checker is documented as a cheap, over-count-tolerant pre-check — "an under-count only
>   costs one harmless extra `/ll:refine-issue` detour... `decide` itself remains the source of
>   truth." Under that stated design contract, the `### Decision Rules`-scoped variant's absolute
>   volume (5 files, 0.16% of the corpus) may be an acceptable cost for closing a false-negative that
>   is otherwise silent forever — but that is a human call about how much of that stated tolerance to
>   spend, not something this measurement can settle by itself.

> **Dogfood note — measured on this file at creation (2026-08-22).** The decision above lives under
> `## Program Design → ### Decision Rules`, the exact region this issue reports as unreachable, so
> the two gates disagree about this very document:
>
> ```
> $ ll-issues check-flag 3293 decision_needed   →  exit 0   (a decision is declared)
> $ ll-issues check-decidable 3293              →  exit 1
>   OPTIONS_MISSING: 3293 — decision_needed is true but no enumerable alternatives
>   were found anywhere in the document; run /ll:refine-issue 3293 --auto
> ```
>
> The gate's own remedy is wrong here: `/ll:refine-issue` cannot make this decision visible,
> because the shape — not the content — is what the locator cannot see. **This divergence is the
> defect**, and it is the cheapest available acceptance check: when the fix lands,
> `check-decidable 3293` exits 0 without this file's body changing.

> **Selected — both, narrowly scoped (implemented 2026-08-22).** Per the follow-up measurement
> above, precision cannot be fixed by scoping alone, so the accepted design takes the small
> residual imprecision deliberately rather than chasing a discriminator that does not exist:
>
> - **Structural half** (closes BUG-3285-shaped cases): a new `decision_rules_numbered` tier
>   (`_locate_decision_rules_numbered`, wired into `locate_enumerable_options` after the
>   whole-document fallback, before Pattern E) matches 2+ bold-numbered items scoped to
>   `## Program Design → ### Decision Rules` specifically — not the unscoped `numbered` tier, which
>   stays untouched. The `>= 2` requirement is a precision refinement beyond what was measured above
>   (a single bold-numbered item is never itself a "pick one" decision): re-measured with it, the
>   `### Decision Rules`-scoped gains drop from 5 to 3 (BUG-3232, BUG-3285, ENH-3045), 1 genuine.
> - **Directive half** (closes BUG-3293's own case): `Program Design` added to
>   `_DIRECTIVE_ALTERNATIVES_SECTIONS`, plus two narrow regex additions —
>   `\bmust be made before implementation\b` on `_DECIDE_IMPERATIVE_RE` and `\bversus\b` on
>   `_INLINE_OR_RE` — the exact phrasing BUG-3293's own Decision Rules used, which the prior
>   five-phrase/"or"-only vocabulary could not see. Re-measured with the actual implementation
>   (not a monkeypatch): **exactly 1 corpus-wide gain (BUG-3293 itself), 0 spurious.**
> - **Combined real-implementation corpus differential** (full 3198-file sweep, actual landed code
>   vs. a git-stashed pristine baseline): **exactly 4 files changed, all `count: 0 → N`, zero
>   unpinned file's count decreased or heading changed** — BUG-3232 (3, spurious), BUG-3285 (3,
>   genuine), BUG-3293 (2, genuine), ENH-3045 (4, spurious). Pinned and asserted in
>   `TestBug3293DecisionRulesCorpusDifferential` (`scripts/tests/test_issue_parser.py`).
> - **Verified against this issue's own acceptance check**: `ll-issues check-decidable 3285` and
>   `check-decidable 3293` both now exit 0 (previously both exit 1 `OPTIONS_MISSING`).
> - **`_DIRECTIVE_ALTERNATIVES_SECTIONS` vs. `_DECISION_DIRECTIVE_SECTIONS` — deliberately left
>   otherwise unreconciled**, not widened to match 1:1: the sibling constant also covers
>   `Implementation Steps`/`Files to Modify`/`Acceptance Criteria`, which answer "was a decision
>   applied", a different question from "is there a pending choice" — see the `# BUG-3293:` comment
>   on `_DIRECTIVE_ALTERNATIVES_SECTIONS` (`issue_parser.py`).
>
> Full test suite (`python -m pytest scripts/tests/ -m "not integration and not conformance"`):
> 20050 passed, 20 skipped, 0 failed. `ruff check`/`ruff format`/`mypy` clean on all touched files.

## Implementation Steps

1. **Measure both routes before choosing.** Apply each candidate independently and diff
   `locate_enumerable_options` output across all of `.issues/`: count the files that gain a
   directive under route A, and the files that gain a spurious `numbered` match under route B.
   Record both. This measurement *is* the decision in § *Program Design → Decision Rules*.
2. **Land the corpus differential test first**, before either change, so it fails loudly on the
   regression classes a regex-level check cannot predict (count drops, tier flips, resolved-section
   moves). Pin any intended change by ID with expected before/after in the docstring.
3. Implement the chosen route with a `# BUG-3293:` comment above the changed constant explaining
   the discriminator added — the file-wide convention for a locator change.
4. Add the fixture whose only decision point is bold numbered items under
   `## Program Design → ### Decision Rules`; assert `check-decidable` exits 0 and `locate-options`
   reports it. Under route B, add the negative control pinning that an ordinary bold-led numbered
   list in `## Implementation Steps` is not counted as an option set.
5. Re-run the corpus differential against the post-BUG-3287 tree and confirm only pinned files move.
6. Verify on this epic's own dogfood cases: `ll-issues check-decidable 3285` and
   `check-decidable 3293` (this file) should both stop reporting "nothing to decide".
7. Update the documentation sites in *Integration Map → Documentation*; if route A lands, state in
   `DECISIONS_LOG_GUIDE.md` which sections Pattern E now covers and why the two section constants
   agree (or still deliberately differ).
8. **Part 3 — correct the printed diagnosis** (`check_decidable.py`): fix the ENH-2821 comment to
   state the tier and directive probes' scopes separately, and restate `OPTIONS_MISSING` as an
   observation naming both candidate causes. **Independent of the A/B decision — it can land
   first, and should, since it is the only part of this issue that needs no measurement.** Pair
   with the CLI assertion under *Tests*.

## Impact

- **Priority**: P3 — no live pipeline breakage is attributable to it today, and the two known
  instances were caught by human review. But it is a silent-miss class: by construction, the cases
  it costs are the ones nobody noticed
- **Effort**: Small-to-Medium under route A (one tuple, one differential); Medium-to-Large under
  route B, where the encoding is the hard part. **Part 3 is Small and unconditional** — a comment,
  a message string, and one CLI assertion, with no measurement owed; it can land ahead of the A/B
  decision
- **Risk**: Medium — module-level state on the shared precedence chain, same surface BUG-3287
  measured at 22 changed files. The corpus differential is the control
- **Breaking Change**: No — additive; documents that match today keep matching

## Steps to Reproduce

1. Author an issue whose only decision point is bold numbered items under
   `## Program Design` → `### Decision Rules`, e.g. `1. **Identifier shape.** …` /
   `2. **Title extent.** …`.
2. `ll-issues locate-options <ID> --json` → `count 0`, `pattern: null`.
3. `ll-issues check-decidable <ID>` → exit 1, `OPTIONS_MISSING`.
4. Run `/ll:decide-issue <ID>` — the interactive path exits "nothing to decide"; the `--auto` path
   parks the issue for human review without deciding.

Reproduces on committed files: `BUG-3285` is the case above.

## Root Cause

- **File**: `scripts/little_loops/issue_parser.py`
- **Anchor**: `_OPTION_PATTERNS[2]` (the `numbered` tier) and `_DIRECTIVE_ALTERNATIVES_SECTIONS`
- **Cause**: The `numbered` tier's bold alternative is anchored on the literal string `**Option`
  rather than on a bold run, so a bold-label numbered item that names the decision instead of
  labelling an option matches nothing. Independently, `_DIRECTIVE_ALTERNATIVES_SECTIONS` omits
  `Program Design`, which its sibling `_DECISION_DIRECTIVE_SECTIONS` includes — so the fallback
  that exists to catch prose decisions never runs on the section the module elsewhere treats as a
  decision-bearing section. Either miss alone would leave the shape reachable; together they make
  it invisible.

## Related Key Documentation

- **EPIC-3290** § *Follow-up owed an ID — the third invisibility shape* — where this was scoped;
  filed as a follow-up rather than a seventh child because it inherits BUG-3287's blast radius and
  that epic is already large
- **BUG-3287** — the first two invisibility shapes; the precedent for the corpus-differential
  discipline this issue must follow, and the issue whose part-2 widening does **not** cover this
  shape (verified)
- **BUG-3285** — the live case, and the issue whose design pass had to be done by hand because of
  this defect
- **BUG-3278** — round 6 item 3 hit the same defect on its own body
- **BUG-3294** — the exit-code conflation in the same file (`check_decidable.py`), scoped out of
  part 3 and filed separately once it turned out to be a family-wide convention across all seven
  `check-*` probes rather than a local slip

## Status

**Open** | Created: 2026-08-22 | Priority: P3


## Session Log
- `implement-decision-rules-numbered-and-pattern-e-widening` - 2026-08-22T21:27:23 - `bc6653b6-fcc0-4790-89ae-8782900fae6c.jsonl`
- `corpus-differential-measurement` - 2026-08-22T20:34:11 - `bc6653b6-fcc0-4790-89ae-8782900fae6c.jsonl`
- `/ll:decide-issue` - 2026-08-22T20:28:37 - `b02f6c42-b49b-49f2-ab1c-39c23a52f988.jsonl`
- `/ll:refine-issue` - 2026-08-22T20:27:35 - `bc6653b6-fcc0-4790-89ae-8782900fae6c.jsonl`
- `/ll:refine-issue` - 2026-08-22T20:23:38 - `ca69c598-e585-404a-8415-d204317f01e1.jsonl`
