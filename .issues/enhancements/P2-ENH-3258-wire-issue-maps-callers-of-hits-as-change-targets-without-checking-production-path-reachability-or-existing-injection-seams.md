---
id: ENH-3258
type: ENH
title: wire-issue maps callers-of hits as change targets without checking production-path
  reachability or existing injection seams
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-19'
captured_at: '2026-08-19T21:25:08Z'
relates_to:
- ENH-2578
- ENH-3045
- ENH-3000
testable: true
program_design_not_applicable: true
confidence_score: 100
outcome_confidence: 77
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 20
---

# ENH-3258: wire-issue maps callers-of hits as change targets without checking production-path reachability or existing injection seams

## Summary

`/ll:wire-issue`'s graph-accelerated discovery layer (ENH-2578) seeds Integration Map
candidates from `ll-code callers-of <symbol>` and confirms each with one targeted Grep at
its `path:line`. That confirmation establishes only that the call *exists*. It does not
establish that the call site is the right place to make the change, and the skill's three
safety rules do not ask.

Result: confident, precisely-cited wiring instructions whose citations are real but whose
conclusions do not survive reading the surrounding twenty lines. The precise line numbers
make the output read as verified when only the coordinates were.

## Current Behavior

`skills/wire-issue/SKILL.md:142` states the three safety rules verbatim: **(1) silent
fallback** on `available: false`, **(2) confirm-before-map** — "every positive hit is a hint,
verified by one Grep before it enters the Integration Map", **(3) never trust negatives**.
`skills/wire-issue/graph-discovery-layer.md:19-21` restates it: "`ll-code` seeds are hints,
not verdicts. Every candidate is confirmed at its `path:line` before it enters the
Integration Map."

All three rules govern **trust** — is this hit real? None governs **suitability** — is this
the right place to change? And a `path:line` Grep cannot answer suitability by construction:
it does not see the enclosing branch two lines up, or the function signature forty lines up.

### Worked example (ENH-3000, caught in pre-implementation review 2026-08-19)

ENH-3000 threads a new config-sourced `untracked_by_design` prefix list into
`build_ref_index()`. Its Wiring Phase instructed:

> Thread the config-sourced `untracked_by_design` prefix list through all three production
> `build_ref_index()` call sites — `research_triage.py:212`, `research_triage.py:317`, and
> `format_check.py:553`

The seed query returns exactly that:

```
$ ll-code callers-of build_ref_index
  scripts/little_loops/issues/research_triage.py:212  qualified_ref_count    (exact, call)
  scripts/little_loops/issues/research_triage.py:317  triage_research_axes   (exact, call)
  scripts/little_loops/cli/issues/format_check.py:553 cmd_format_check       (exact, call)
```

The tool is correct and each `path:line` Grep confirms. The *instruction* is still wrong:

1. **Not on the production path.** `:212` and `:317` are both inside `if index is None:`
   guards — fallbacks for callers that omit the index, not the primary path.
2. **An injection seam already exists.** Both enclosing functions already accept
   `index: RefIndex | None` (`research_triage.py:191-195`, `:279-283`). The value can be
   injected without touching either line.
3. **The enclosing module cannot do what was asked.** The config type lives at
   `scripts/little_loops/config/core.py:235` and is imported nowhere in
   `scripts/little_loops/issues/research_triage.py`, which takes a bare `root: Path` and has
   no config surface at all. "Thread the config-sourced list through :212" silently mandates
   a new config dependency in a module deliberately kept free of one.
4. **The right target was two hops up.** `scripts/little_loops/cli/issues/research_triage.py:61` — the sole
   production caller of `triage_research_axes` — already holds `config`. `callers-of` is a
   one-hop query; the answer was a caller of the caller.

Following the instruction literally yields a larger, worse change than the correct one.

## Expected Behavior

Before a `callers-of` hit enters the Integration Map as a **change target** (as opposed to an
impact-only entry), the confirmation step answers two additional questions:

- **Reachability**: is this call on the production path, or inside a fallback / guard /
  `except` / test-only branch? Fallback sites are recorded as such, not as targets.
- **Seam**: does the enclosing function already expose a parameter that carries the value,
  making injection from above the smaller change? If so, walk one hop up (`callers-of` on the
  *enclosing* function) and evaluate that caller as the target instead.

The Integration Map distinguishes "this call site changes" from "this call site is affected".

## Motivation

Wiring instructions are consumed by `/ll:manage-issue` and by the `rn-*` autonomous loops,
which follow them without re-deriving them — that is the point of the pass. A wrong-but-cited
touchpoint is therefore executed, not questioned. The failure is also **silent**: threading
config into `research_triage.py` would have worked, passed tests, and left a config import in
a module that had none, with the real seam unused.

Severity comes from the shape, not the frequency: the output is maximally credible (exact
`path:line`, tool-confirmed) exactly where it is least verified. This is the same class
ENH-3045's claim-grounding half addresses for *assertions about* symbols; this issue covers
*targets derived from* symbols.

## Proposed Solution

**The shared safety rules are not amended.** The new requirement lands as a wire-issue-local
stricter rule, following the precedent the canonical guide already sets for
`/ll:verify-issues` — see § Decision Rationale immediately below, which resolves
Implementation Step 1.

Add, as a **wire-issue-local rule** in `skills/wire-issue/graph-discovery-layer.md`: every
positive hit is confirmed by reading its enclosing function — not just its line — and
classified before it enters the Integration Map:

- `target` — on the production path, no upstream seam; wire it here.
- `fallback` — inside `if x is None:` / `except` / a `--dry-run`-style guard. Record under
  Dependent Files with the branch quoted; do not instruct a change.
- `seam-above` — the enclosing function already takes the value as a parameter. Run
  `ll-code callers-of <enclosing function>` and evaluate *those* as targets. Cap the walk at
  one extra hop to bound cost; if it does not resolve in one hop, emit `target` with a
  flagged note rather than recursing.

**Output contract**: a change-target entry must quote the enclosing signature or branch line
that justifies its classification, mirroring ENH-3045's "quote the line that makes it true".
An entry that cannot be justified that way is downgraded to impact-only.

Cost control: this is a read of one function per confirmed hit, replacing a one-line Grep.
ENH-2578's premise is that graph seeding buys enough budget to spend it on confirmation; this
spends some of that surplus on the half that was skipped. Measure against ENH-2578's own
before/after token methodology.

### Decision Rationale — consumer-local rule, not a shared-contract amendment

**Resolves Implementation Step 1 (decided 2026-08-19).** The three shared safety rules in
`docs/guides/GRAPH_DISCOVERY_GUIDE.md:82-92` are left **byte-unchanged**. The new requirement
is added as a wire-issue-local stricter rule.

**The guide already solved this exact problem one consumer over.**
`GRAPH_DISCOVERY_GUIDE.md:19-27` carries a per-consumer carve-out:

> `/ll:verify-issues` follows the same procedure and safety rules as the other two consumers,
> **but under a stricter local rule**: it mutates issue state (verdicts, `status`), so a graph
> result there may only corroborate or correct a verdict, never originate one.

ENH-3258 is the same shape. The three consumers differ not in how much they trust a hit, but
in **what they do with a confirmed one**:

| Consumer | A confirmed hit becomes | Local rule |
|---|---|---|
| `/ll:refine-issue` § 3.05 | a research lead | none — shared rules suffice |
| `/ll:verify-issues` § 2B.0 | a verdict input | may corroborate, never originate (exists today) |
| `/ll:wire-issue` § 3.6 | **an executed change target** | may nominate, never designate without reachability + seam justification (**new, this issue**) |

**Shared rule 2 is not the rule that failed.** Canonically it is named
**"Confirm-before-use"** (`GRAPH_DISCOVERY_GUIDE.md:87-89`) — "every positive hit is a lead,
not a verdict. Confirm it with one Grep at its `path:line` before it is written down or handed
to an agent as an established fact." That is a **trust** rule, and on the ENH-3000 instance it
worked correctly: the call really was at
`scripts/little_loops/issues/research_triage.py:212`. Wire-issue's local gloss renames it
**"confirm-before-map"** (`graph-discovery-layer.md:26-28`), silently re-purposing a trust
rule as a target-selection rule. **That rename is the actual defect.** Rule 2 needs no change;
wire-issue needs a *second* rule it never had.

**Why not amend the shared rule anyway:**

- The rules are marked "encode verbatim" (`GRAPH_DISCOVERY_GUIDE.md:82`) and are mirrored into
  `.qwen/`, `.gemini/`, and `.kimi-code/`. Amending them churns three consumers and every host
  mirror to fix a defect only one consumer has.
- `/ll:refine-issue` should inherit nothing here. A lead that turns out to sit in a fallback
  branch is still a perfectly good research lead — suitability only matters when the output is
  an *instruction*. Widening the rule would impose per-hit enclosing-function reads on a phase
  that gains nothing from them, which is precisely the ENH-2578 token surplus this issue is
  already spending down.
- The guide's own structure mandates this split: "Consumers keep only their own phase-specific
  procedure and link here — one place to fix when the contract moves"
  (`GRAPH_DISCOVERY_GUIDE.md:7-10`). Target selection *is* wire-issue's phase-specific
  procedure.

**Consequences for this issue's scope:**

- `docs/guides/GRAPH_DISCOVERY_GUIDE.md` moves from a rule-2 edit to a **`## Consumers`
  addition only** — one short paragraph for wire-issue mirroring the verify-issues one at
  :19-27. It stays in Files to Modify, but for a different and much smaller edit.
- `/ll:refine-issue` § 3.05 and `commands/refine-issue.md` drop out of scope entirely.
- The mechanism (`target`/`fallback`/`seam-above`, the one-hop walk, the justifying quote)
  lives wholly in `skills/wire-issue/graph-discovery-layer.md`.

**Do not add a fifth restatement.** Per the research finding above, rule 2 already exists in
four independently-worded, non-byte-identical copies. The wire-issue-local rule is *new text*
about a *different* question, so it does not add to that pile — but the sync test in
Implementation Step 4 should pin canonical → wire-issue-layer to stop the existing drift
widening.

## Program Design

### Types
N/A — this is a skill-doctrine (markdown instruction) change, not a Python code change; no new data types.

### Signatures
N/A — no new Python function/class signatures.

### Call Path
No runtime call path — this is a skill-doctrine change. The doctrine-read path an
implementing agent follows is: `skills/wire-issue/SKILL.md:142` (Phase 3.6 compressed
restatement) -> `skills/wire-issue/graph-discovery-layer.md:26-28` (`confirm-before-map`,
the rule being amended) -> `skills/wire-issue/output-report.md:32-42` (Integration Map
entry format the classification/quote fields must extend) -> `docs/guides/GRAPH_DISCOVERY_GUIDE.md:87-89`
(canonical rule 2, shared with `/ll:refine-issue` Step 3.05 per
`graph-discovery-layer.md:5-8`).

### Decision Rules

- **Input**: a `callers-of`-confirmed hit (`path:line`) plus a read of its enclosing function body.
- **Values**: exactly one of `target` / `fallback` / `seam-above`.
- **`fallback`**: the hit sits inside an `if x is None:` / `except` / `--dry-run`-style guard branch — record under Dependent Files with the guarding branch line quoted; never emit as a change instruction.
- **`seam-above`**: the enclosing function already accepts the value as a parameter — run `ll-code callers-of <enclosing function>` and evaluate *that* hit instead of the original.
- **`target`**: the hit is on the production path (not `fallback`) and the enclosing function does not already expose the value as a parameter (not `seam-above`).
- **Hop cap**: the `seam-above` walk is capped at exactly one extra hop. If the one-hop walk does not resolve to a clean `target`/`fallback`, the hit is emitted as `target` with a flagged note — it does not recurse further.
- **Output/escape hatch**: a `target` entry must quote the enclosing signature or guard line that justifies the classification. An entry that cannot be justified that way is downgraded to impact-only (Dependent Files, not Files to Modify).

## Integration Map

### Files to Modify
- `skills/wire-issue/graph-discovery-layer.md` — the "Wire-issue specifics" bullets (lines
  23-33), specifically `confirm-before-map` (:26-28); add the three-way classification as a
  **wire-issue-local rule**. Also amend :15-16, which currently disclaims exactly the output
  change this issue makes ("The written output (Integration Map) is format-identical to today;
  only how candidates are found changes")
- `docs/guides/GRAPH_DISCOVERY_GUIDE.md` — **`## Consumers` section only** (per § Decision
  Rationale). Add one wire-issue paragraph mirroring the verify-issues carve-out at :19-27.
  The three safety rules at :82-92 stay byte-unchanged
- `skills/wire-issue/SKILL.md:142` — the compressed three-safety-rules restatement, which is
  marked "verbatim" and so must stay in sync with the file above
- `skills/wire-issue/output-report.md:32-42` — the Integration Map entry format is four fixed
  subsections of flat `` `path` — description `` bullets with no field for a classification or
  a justifying quote; that format must grow both

### Dependent Files (Callers/Importers)
- `.qwen/skills/wire-issue/graph-discovery-layer.md`,
  `.gemini/skills/wire-issue/graph-discovery-layer.md`,
  `.kimi-code/skills/wire-issue/graph-discovery-layer.md` — `ll-adapt`-generated host mirrors
  of the edited file. Regenerate after the edit;
  `scripts/tests/test_adapters.py::test_companion_drift_is_repaired` covers the repair path,
  but confirm rather than assume
- ~~`commands/refine-issue.md` § 3.05~~ — **out of scope** per § Decision Rationale.
  refine-issue consumes hits as research leads, not change targets, and inherits no local rule

### Similar Patterns
- `skills/wire-issue/prose-dependency-gate.md`, `static-coupling-layer.md` — sibling
  confirmation layers; check whether either already reads enclosing context and can be
  reused rather than duplicating the rule

### Tests
- `scripts/tests/test_enh3098_refine_issue_graph_seeding.py` — assert the `SKILL.md:142`
  verbatim block still matches `graph-discovery-layer.md`, since the drift between the two is
  what would silently un-fix this. This file already holds the adjacent
  `test_wire_issue_layer_delegates_rather_than_duplicates` (:136-144) and
  `test_states_safety_rule` (:119-127), so the sync test belongs beside them.
  (An earlier draft of this issue named a skills-structure test module that does not exist in
  this repo — do not create one; use the file named above.)
- Same file — assert `GRAPH_DISCOVERY_GUIDE.md`'s three safety rules (:82-92) are unchanged by
  this issue, pinning the § Decision Rationale boundary so a later pass does not "simplify"
  the wire-issue-local rule back into the shared contract
- Regression fixture: a symbol whose only `callers-of` hits are inside `if x is None:`
  branches of functions that already expose the value as a parameter — assert the pass emits
  `seam-above` / `fallback`, not `target`. `build_ref_index` is the natural fixture; it is a
  real, stable instance of exactly this shape

### Documentation
- `docs/guides/GRAPH_DISCOVERY_GUIDE.md` — `## Consumers` carve-out paragraph (listed under
  Files to Modify above). Safety rule 2's definition is **not** touched

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-19 — based on codebase analysis:_

- `skills/wire-issue/graph-discovery-layer.md:15-16` currently states "The written output (Integration Map) is format-identical to today; only how candidates are found changes" — this line must also be amended as part of this issue's scope, since the proposed target/fallback/seam-above field and justifying-quote requirement are exactly the output-format change this line disclaims.
- Confirm-before-map's rule 2 already exists in **four**, not two, independently-worded restatements: canonical `docs/guides/GRAPH_DISCOVERY_GUIDE.md:87-89`, `skills/wire-issue/graph-discovery-layer.md:19-21`, `skills/wire-issue/graph-discovery-layer.md:26-28` (the wire-issue-specific "confirm-before-map" gloss this issue targets), and `skills/wire-issue/SKILL.md:142`. None is byte-identical to another despite `SKILL.md:142` calling itself "verbatim" — this drift predates ENH-3258 and should be resolved by Implementation Step 4's sync test, not left as a fourth inconsistent restatement.
- Neither sibling confirmation layer named under Similar Patterns reads enclosing function context today: `skills/wire-issue/prose-dependency-gate.md` only runs `ll-issues format-check` and inspects prose-dependency phrasing; `skills/wire-issue/static-coupling-layer.md` only reads the decisions log (`ll-issues decisions list --type=coupling`) and globs `if_changed`/`then_check` paths. The seam-above/fallback enclosing-function read is new logic, not reuse of an established pattern.
- `skills/wire-issue/output-report.md:32-42`'s Integration Map format is four fixed subsections (`Added to Dependent Files` / `Added to Files to Modify` / `Added to Documentation` / `Added to Tests`), each a flat `` `path` — description `` bullet. No field exists today for a target/fallback/seam-above classification or a justifying quoted line — this is what output-report.md's format must grow.
- No test today asserts `SKILL.md:142` stays in sync with `graph-discovery-layer.md`'s rule 2 text, confirming this issue's own Tests-section claim. `scripts/tests/test_enh3098_refine_issue_graph_seeding.py::test_wire_issue_layer_delegates_rather_than_duplicates` (lines 136-144) checks only that `graph-discovery-layer.md` links out to the canonical doc and doesn't restate the exit-codes contract; `::test_states_safety_rule` (lines 119-127) checks only that the three rule *labels* appear in `GRAPH_DISCOVERY_GUIDE.md`. `scripts/tests/test_enh494_skill_companions.py` only checks line-count/registration for `graph-discovery-layer.md`, not content sync.

_Added by `/ll:refine-issue` — 2026-08-19 — based on codebase analysis:_

- The Tests entry `scripts/tests/test_skills_structure.py` has no tracked file at that path in this repo. The actual candidate test files for the drift-check named in this section are `scripts/tests/test_enh3098_refine_issue_graph_seeding.py` (`test_wire_issue_layer_delegates_rather_than_duplicates`, `test_states_safety_rule`) and `scripts/tests/test_enh494_skill_companions.py`, neither of which currently checks SKILL.md:142/graph-discovery-layer.md content sync (see the earlier findings block above). The new sync test belongs in one of these files, not in a `test_skills_structure.py` that would need to be created from scratch.
- Ambiguous file reference: bare `research_triage.py:212`/`:317` (used in Current Behavior and Proposed Solution) resolves to two distinct files in this repo — `scripts/little_loops/issues/research_triage.py` (the guard sites at :212/:317, per the worked example) and `scripts/little_loops/cli/issues/research_triage.py` (holds `triage_research_axes`'s sole production caller at :61, per Expected Behavior's "two hops up" point). Implementers should use the full disambiguated paths when citing these lines.

## Implementation Steps

1. ~~Decide the scope question first~~ — **done** (2026-08-19): consumer-local rule, shared
   safety rules unchanged. See § Decision Rationale.
2. Add the wire-issue-local classification rule and the justifying-quote requirement to
   `graph-discovery-layer.md`, and grow `output-report.md:32-42`'s entry format to carry both.
   Amend `graph-discovery-layer.md:15-16`'s "format-identical to today" disclaimer.
3. Add the one-hop `seam-above` walk with its explicit hop cap.
4. Add the wire-issue carve-out paragraph to `GRAPH_DISCOVERY_GUIDE.md`'s `## Consumers`,
   mirroring the verify-issues one at :19-27. Verify the three safety rules at :82-92 are
   byte-unchanged.
5. Add the sync test pinning canonical rule 2 → `graph-discovery-layer.md` →
   `SKILL.md:142`, plus the `build_ref_index`-shaped regression fixture. Put it in
   `scripts/tests/test_enh3098_refine_issue_graph_seeding.py` (alongside
   `test_wire_issue_layer_delegates_rather_than_duplicates`) — **not** in a
   a skills-structure test module, which does not exist in this repo.
6. Regenerate the `.qwen/`/`.gemini/`/`.kimi-code/` mirrors of
   `skills/wire-issue/graph-discovery-layer.md` via `ll-adapt`.
7. Re-run wire-issue against ENH-3000 as an end-to-end check: it should classify
   `scripts/little_loops/issues/research_triage.py:212`/`:317` as `fallback` + `seam-above`
   and surface `scripts/little_loops/cli/issues/research_triage.py:61` as the target.
   (Use the full disambiguated paths — bare `research_triage.py` resolves to two files.)
8. `python -m pytest scripts/tests/` passes.

## Impact

- **Priority**: P2 — wiring output is executed unquestioned by `/ll:manage-issue` and the
  `rn-*` loops, and the defect is silent (the wrong change works). Matches the P2 of its
  doctrine siblings ENH-3045/3049/3050.
- **Effort**: Small — skill-doctrine edits plus two tests and a mirror regen. No Python
  behavior change. The step-1 scope decision is now closed, and it shrank the blast radius:
  the shared contract takes a `## Consumers` paragraph rather than a rule amendment, and
  refine-issue drops out of scope.
- **Risk**: Low-Medium. The real risk is cost: a per-hit enclosing-function read is strictly
  more expensive than a per-hit line Grep, partially eroding what ENH-2578 bought. Measure
  with ENH-2578's own before/after token methodology rather than assuming the surplus covers
  it.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: how `callers-of` hits are classified before entering the Integration Map as
  change targets.
- **Out of scope**: the accuracy of `ll-code callers-of` itself — it was correct in the
  worked example. See BUG-3091 for a genuine `codegraph` resolution defect.
- **Out of scope**: assertions *about* cited symbols (reusable / unchanged / behaves-thus) —
  that is ENH-3045's claim-grounding half. This issue covers targets *derived from* symbols.
- **Out of scope**: fixing ENH-3000's wiring text — already corrected in that issue.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/GRAPH_DISCOVERY_GUIDE.md` | Canonical `ll-code` contract and the three safety rules being amended; shared with refine-issue |
| `skills/wire-issue/graph-discovery-layer.md` | The confirm-before-map rule this issue changes |
| `.claude/CLAUDE.md` | § Development Preferences — skills over agents; this is a skill-doctrine change |

## Session Log
- `/ll:confidence-check` - 2026-08-19T21:42:28 - `f937caf1-9ab2-43cc-9ff4-a31b61f43564.jsonl`
- scope decision - 2026-08-19 - resolved Implementation Step 1: the new requirement lands as
  a wire-issue-local stricter rule, not an amendment to the shared safety rules, following the
  `/ll:verify-issues` carve-out precedent at `GRAPH_DISCOVERY_GUIDE.md:19-27`. Shared rule 2
  ("Confirm-before-use") is a trust rule that worked correctly on the ENH-3000 instance;
  wire-issue's "confirm-before-map" rename re-purposed it as a target-selection rule, which is
  the actual defect. refine-issue drops out of scope; host-mirror regeneration added
- `/ll:refine-issue` - 2026-08-19T21:30:05 - `5c491ecb-85ee-4e96-982b-ddd1e098374d.jsonl`
- `/ll:capture-issue` - 2026-08-19T21:26:24 - `993e1c72-3d56-4566-b0f4-c5d8631d62de.jsonl`
- `/ll:capture-issue` - 2026-08-19

## Status

- **Status**: open
