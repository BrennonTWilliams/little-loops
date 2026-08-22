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
decision_needed: true
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

Live case (BUG-3285, measured 2026-08-22):

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

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `_DIRECTIVE_ALTERNATIVES_SECTIONS` (route A) and/or
  `_OPTION_PATTERNS[2]`, the `numbered` tier (route B). Resolve both by symbol name, not line
  number — this file's anchors have drifted twice in a single day (`f39a417e`, `93270c37`).

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

### Documentation

- `docs/reference/API.md` — `locate_enumerable_options` precedence prose
- `docs/reference/CLI.md` — `check-decidable` / `locate-options` coverage
- `docs/guides/DECISIONS_LOG_GUIDE.md` — Pattern E section coverage, if route A lands

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

## Impact

- **Priority**: P3 — no live pipeline breakage is attributable to it today, and the two known
  instances were caught by human review. But it is a silent-miss class: by construction, the cases
  it costs are the ones nobody noticed
- **Effort**: Small-to-Medium under route A (one tuple, one differential); Medium-to-Large under
  route B, where the encoding is the hard part
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

## Status

**Open** | Created: 2026-08-22 | Priority: P3
