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

The seed query returns exactly that (real output, 2026-08-19):

```
$ ll-code callers-of build_ref_index
  scripts/tests/test_text_utils.py:527       TestBuildRefIndex::test_indexes_tracked_files_by_basename  (exact, call)
  scripts/tests/test_text_utils.py:536       TestBuildRefIndex::test_calls_git_ls_files_exactly_once    (exact, call)
  scripts/tests/test_text_utils.py:541       TestBuildRefIndex::test_git_unavailable_returns_empty_index (exact, call)
  scripts/little_loops/issues/research_triage.py:212  qualified_ref_count    (exact, call)
  scripts/little_loops/issues/research_triage.py:317  triage_research_axes   (exact, call)
  scripts/tests/test_research_triage.py:282  TestReferenceFiltering::test_ambiguous_ref_is_denominator_eligible_but_not_covering (exact, call)
  scripts/tests/test_research_triage.py:495  _corpus_ref_index      (exact, call)
  scripts/little_loops/cli/issues/format_check.py:553 cmd_format_check       (exact, call)
```

Note the shape: **five of the eight hits are test callers** — see § Test-path prefilter
under Proposed Solution.

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

- **Reachability**: is this call on the production path at all? Test-file callers are
  separated by path up front; of what remains, calls inside a fallback / guard / `except`
  branch are recorded as such, not as targets.
- **Seam**: does the enclosing function already expose a parameter that carries the value,
  making injection from above the smaller change? If so, walk one hop up (`callers-of` on the
  *enclosing* function) and evaluate that caller as the target instead.

The Integration Map distinguishes "this call site changes" from "this call site is affected" —
and, decisively, the **Wiring Phase appended to `## Implementation Steps` (Phase 8b) emits an
`Update <path>` instruction only for hits classified `target`.** That is the surface
`/ll:manage-issue` and the `rn-*` loops actually execute.

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

### Where the rule lives — Phase 5 / 8a / **8b**, not Phase 3.6 (decided 2026-08-19; 8b added 2026-08-19)

**The classification must be applied where all caller hits converge, which is not Phase 3.6.**
Verified against the current skill:

- Phase 3.6's confirmed candidates never enter the Integration Map directly. They feed
  **Phase 4 Agent 1's seed slots** (`SKILL.md:142`; `graph-discovery-layer.md:29-31`).
- The Integration Map is written in **Phase 8a** (`SKILL.md:342-398`) from `MISSING_WIRING`,
  computed in **Phase 5** (`SKILL.md:260-279`) by merging all three agents' findings.
- The **Wiring Phase appended to `## Implementation Steps`** is written in **Phase 8b**
  (`SKILL.md:400-416`) from `MISSING_WIRING.new_impl_steps` (`SKILL.md:278`).
- A classification assigned at 3.6 has no carrier through Phase 4/5 to reach any of them.

#### 8b is the surface that actually emits the harmful instruction (corrected 2026-08-19)

**An earlier draft of this issue located the fix at "the *Files to Modify* vs *Dependent Files*
routing at `SKILL.md:346-361`". That premise is wrong, verified against the current skill:**

- `SKILL.md:346` routes **all** `callers_to_add` / `importers_to_add` hits to *Dependent Files*,
  unconditionally. `:356`'s *Files to Modify* path is for **registration / manifest files only**.
  A caller hit therefore never becomes a *Files to Modify* entry today, and 8a already draws the
  "changes vs affected" line this issue's § Expected Behavior asks for.
- The executed instruction comes from **8b's Wiring Phase template** (`SKILL.md:400-416`), whose
  bullet form is literally `- Update `<caller>` — adjust calls to `changed_function()``.
  ENH-3000's harmful text — "Thread the config-sourced list through all three production
  `build_ref_index()` call sites" — is that shape, not an Integration Map bullet.
- `/ll:manage-issue` and the `rn-*` loops execute `## Implementation Steps`. A classification
  that reaches 8a but not 8b relabels a Dependent-Files bullet while still emitting
  "Update `scripts/little_loops/issues/research_triage.py`" into the Wiring Phase — i.e. **it
  would not fix this issue's own worked example.**

So 8b is the **primary** edit. The 8a edit remains in scope but for a smaller reason: it
adds the classification label and justifying quote to the Dependent-Files bullets, and skips the
enclosing-function read for `test-only`.

##### `new_impl_steps` is a gate, not a per-hit carrier (corrected 2026-08-19)

**An earlier draft named `new_impl_steps` (`:278`) a "second required carrier" alongside
`callers_to_add` (`:268`). That is a mechanism error, verified against the current skill:**

- Phase 5 defines the bucket as `[phases that should be added to Implementation Steps based on
  missing files]` (`:278`) — a list of *phases*, not of hits. It has no per-hit slot to carry a
  classification on.
- 8b uses it only as an emptiness gate: "If `new_impl_steps` is non-empty, append a
  wiring-specific phase" (`:400`). The `- Update <path>` bullets that follow are rendered from
  the **file** buckets — `callers_to_add`, `tests_to_add`, `registrations_to_add`, `docs_to_add`
  — which is why the template shows a caller, a test, a `plugin.json`, and a doc bullet.

So the classification has exactly **one** carrier, `callers_to_add`, and 8b's rule reads: *render
an `Update <path>` bullet only for `callers_to_add` entries classified `target`.* No change to
`new_impl_steps` is needed or possible. An implementer told to "carry the classification on
`new_impl_steps`" will look for a per-hit field that does not exist.

#### Mechanical precedent — follow ENH-3050

`SKILL.md:346` already reads: "`gate_consumers` and `conditional_branches` (ENH-3050) also route
here, not to a new heading." That is exactly this change's shape — a new Phase 5 bucket carried
to 8a and routed without inventing a heading. Follow it rather than designing a new carrier.

Two further consequences of a 3.6-only placement, both fatal:

1. **Safety rule 1 deletes the rule.** On `available: false` or exit `2`, Phase 3.6 is skipped
   *entirely* and the normal Phase 4 flow runs — taking the reachability/seam requirement with
   it. The rule would be absent exactly where no graph provider exists.
2. **Agent-discovered callers bypass it.** Agent 1 traces callers by Grep regardless of
   `ll-code`. Those hits never pass through 3.6 at all. The ENH-3000 failure mode is a property
   of *any* caller hit becoming a change target, not of graph-seeded ones.

So the split is:

| Lives in | What |
|---|---|
| `SKILL.md` § Phase 5 | The four-value classification carried on `callers_to_add` (`:268`) — the sole carrier — applied to **every** caller hit in `MISSING_WIRING`, whatever discovered it. `importers_to_add` is **not** classified (see § Importers below) |
| `SKILL.md` § 8b | **Primary.** Emit an `Update <path>` Wiring Phase bullet only for `target`; suppress for `fallback` / `test-only`, or emit with the classification and justifying quote attached |
| `SKILL.md` § 8a | The classification label and justifying quote on Dependent-Files bullets; `test-only` reuses existing Tests routing |
| `skills/wire-issue/graph-discovery-layer.md` | The graph-specific parts only: the test-path prefilter over `results[]`, and the one-hop `seam-above` walk keyed off `results[].symbol` |

This keeps the change consumer-local (no shared-contract amendment) at the same edit budget,
while covering the fallback and agent-discovery paths that a 3.6-only rule leaves open.

### The classification

Every positive caller hit is confirmed by reading its enclosing function — not just its line —
and classified before it enters the Integration Map:

- `test-only` — the hit's `path` is under a test root (`scripts/tests/`, `**/test_*.py`,
  `**/*_test.py`, `**/tests/**`). Record under the Integration Map's **Tests** subsection;
  never Files to Modify. Assigned by the prefilter below, without an enclosing-function read.
  **Note the routing here is not new** — Phase 5 already funnels test files to the Tests
  subsection via `tests_to_add` (`SKILL.md:270`). The genuinely new behavior is *skipping the
  enclosing-function read* for these hits. Do not build a second routing path alongside
  `tests_to_add`; reuse it.
- `target` — on the production path, no upstream seam; wire it here.
- `fallback` — inside `if x is None:` / `except` / a `--dry-run`-style guard. Record under
  Dependent Files with the branch quoted; do not instruct a change.
- `seam-above` — the enclosing function already takes the value as a parameter. Run
  `ll-code callers-of <enclosing symbol>` and evaluate *those* as targets. Cap the walk at
  one extra hop to bound cost; if it does not resolve in one hop, emit `target` with a
  flagged note rather than recursing. **The hop's results are themselves classified by the
  same rules, with `seam-above` disabled** — a one-hop result is `test-only`, `fallback`, or
  `target`, never a second hop. This matters on the worked example: `callers-of
  triage_research_axes` returns test callers alongside the real production one, and the test
  callers must land as `test-only`, not as targets promoted by the hop.

**The enclosing symbol is already in the payload — do not re-derive it.** Each
`ll-code --json callers-of` result carries `results[].symbol`, which *is* the enclosing
function/method of the call site (`qualified_ref_count`, `triage_research_axes`,
`cmd_format_check` in the output above; verified 2026-08-19). The `seam-above` hop is
therefore literally `ll-code callers-of <results[].symbol>` — no lookup, no parsing, no
"identify the enclosing function" step. The enclosing-function *read* is still required, but
only to inspect the signature and guard branches, not to find the name.

#### The hop needs a no-graph path — and unresolved must fail to impact-only (added 2026-08-19)

The `seam-above` hop is *literally* `ll-code callers-of <symbol>`. It therefore cannot run in the
two cases this issue elsewhere claims to cover:

1. **`available: false` / exit `2`** (safety rule 1). The classification itself survives — it is a
   Phase 5 rule over hits, not a graph rule — but its `seam-above` *resolution* does not.
2. **Agent-1-discovered hits**, which have no `results[].symbol` payload at all.

In both cases: read the enclosing function (already required), and if its signature exposes the
value as a parameter, classify `seam-above` and **stop there** — do not attempt a Grep
reconstruction of the caller set, which is the exhaustive search ENH-2578 exists to avoid.

**An unresolved `seam-above` fails to impact-only, not to `target`.** An earlier draft had the
hop cap emit "`target` with a flagged note"; that default re-emits the exact instruction this
issue exists to suppress — on the worked example it would have produced "Update
`scripts/little_loops/issues/research_triage.py`" again. The correct fail-safe: an unresolved
`seam-above` hit gets its Dependent-Files bullet with the enclosing signature quoted and a
`seam-above (unresolved)` label, and **no `Update <path>` bullet in 8b**. The seam is known to
exist; where to inject from is not. Emitting nothing is recoverable, emitting the wrong target is
not.

#### Suppression must be announced, never silent (added 2026-08-19)

If suppression removes *every* caller bullet from 8b's Wiring Phase — all hits `fallback`,
`test-only`, or unresolved `seam-above` — the Wiring Phase must still emit one line:

```markdown
- **No direct caller change target identified** — N caller hits classified
  `fallback` / `seam-above (unresolved)`; the value must be injected from above.
  Verify manually before implementing.
```

Without this, the fix converts a confidently-wrong instruction into a *silently absent* one, and
`/ll:manage-issue` proceeds as though wiring found nothing to do. That is a different failure with
the same root cause — credible output where none was verified.

#### Importers are out of scope for classification (added 2026-08-19)

The four values are exhaustive over **caller** hits only. `importers_to_add` (`SKILL.md:269`) is
not classified: an import is module-level, so it has no enclosing guard branch and no parameter
seam — the two conditions the classification tests for do not apply. Importer hits keep their
current unconditional Dependent-Files routing at `:346`. Stated explicitly because § The
classification calls the value set "exhaustive", which otherwise reads as covering both buckets.

**Output contract**: a change-target entry must quote the enclosing signature or branch line
that justifies its classification, mirroring ENH-3045's "quote the line that makes it true".
An entry that cannot be justified that way is downgraded to impact-only.

### Test-path prefilter (the cost control)

Classify `test-only` **first, by path, before any enclosing-function read.** This is what pays
for the rest of the rule: on the `build_ref_index` fixture above it removes 5 of 8 hits, so
the enclosing-function reads drop from 8 to 3 — a ~60% reduction against the naive
"read one function per confirmed hit" cost. The residual cost is a read of one function per
*production* hit, replacing a one-line Grep. ENH-2578's premise is that graph seeding buys
enough budget to spend it on confirmation; this spends some of that surplus on the half that
was skipped, and the prefilter keeps the spend proportional to the production surface rather
than the total caller count. Measure against ENH-2578's own before/after token methodology.

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
- The mechanism splits per § *Where the rule lives* above: the classification, routing, and
  justifying quote land in `skills/wire-issue/SKILL.md` §§ Phase 5 / 8a (where every caller hit
  converges); the test-path prefilter and the one-hop `seam-above` walk land in
  `skills/wire-issue/graph-discovery-layer.md` (they operate on the `ll-code` payload and only
  exist when a provider does).

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
No runtime call path — this is a skill-doctrine change. The **candidate-flow path** the rule
must attach to (verified 2026-08-19) is what determines placement:

```
Phase 3.6  SKILL.md:142 / graph-discovery-layer.md
             ll-code --json callers-of -> confirm at path:line
             -> [prefilter + seam-above hop land HERE]
             -> written into Phase 4 Agent 1 seed slots (NOT the Integration Map)
Phase 4    SKILL.md:147-259  three agents; Agent 1 also finds callers by Grep
             independently of ll-code
Phase 5    SKILL.md:260-287  MISSING_WIRING buckets — all three agents' findings merge
             -> [classification + justifying quote land HERE, on BOTH
                 callers_to_add (:268) and new_impl_steps (:278)]
Phase 7    SKILL.md:302-316  interactive per-category counts shown before approval
             -> [counts must not silently include fallback/test-only hits]
Phase 8a   SKILL.md:342-398  Integration Map written. NOTE: :346 routes ALL callers to
             "Dependent Files" unconditionally; :356's "Files to Modify" is
             registrations/manifests only — callers never land there today.
             -> [classification label + justifying quote on the bullets]
Phase 8b   SKILL.md:400-416  Wiring Phase appended to ## Implementation Steps from
             new_impl_steps. Template bullet: "- Update `<caller>` — ...".
             THIS is the instruction /ll:manage-issue and the rn-* loops execute.
             -> [PRIMARY: emit `Update <path>` only for `target`]
Phase 10   output-report.md:32-42  terminal run report only — emitted verbatim,
             mirrors what 8a/8b already wrote; not the writer
```

The doctrine-read path an implementing agent follows is:
`skills/wire-issue/SKILL.md:142` (Phase 3.6 compressed restatement) ->
`skills/wire-issue/graph-discovery-layer.md:26-28` (`confirm-before-map`, the rule whose scope
is being corrected) -> `SKILL.md:260-279` + `:342-398` (Phase 5/8a, where the classification
and routing are added) -> `skills/wire-issue/output-report.md:32-42` (report format the
classification/quote fields must extend) -> `docs/guides/GRAPH_DISCOVERY_GUIDE.md:87-89`
(canonical rule 2, shared with `/ll:refine-issue` Step 3.05 per
`graph-discovery-layer.md:5-8`).

### Decision Rules

- **Input**: any caller hit reaching Phase 5's `callers_to_add` (`path`, `line`, and — when it came from `ll-code` — `symbol`) plus, for non-test hits only, a read of its enclosing function body. **Not restricted to graph-seeded hits**: Agent-1-discovered callers and every hit on the `available: false` path are classified by the same rules. When `symbol` is absent (agent-discovered hit), the enclosing function is read from the file rather than taken from the payload — the read is required either way, so only the `seam-above` hop's zero-derivation shortcut is lost.
- **Values**: exactly one of `test-only` / `target` / `fallback` / `seam-above`. The set is exhaustive **over caller hits**; `importers_to_add` is not classified (see § Importers are out of scope).
- **Carrier**: `callers_to_add` (`SKILL.md:268`) only. `new_impl_steps` (`:278`) is a list of phases and an emptiness gate for 8b, not a per-hit carrier — do not attach the classification to it.
- **Order**: `test-only` is decided first, by path alone. The remaining three are decided from the enclosing-function read, in the order `fallback` → `seam-above` → `target`.
- **`test-only`**: the hit's `path` matches a test root (`scripts/tests/`, `**/tests/**`, `**/test_*.py`, `**/*_test.py`) — record under the Integration Map's Tests subsection. No enclosing-function read is performed, and it is never a change target.
- **`fallback`**: the hit sits inside an `if x is None:` / `except` / `--dry-run`-style guard branch — record under Dependent Files with the guarding branch line quoted; never emit as a change instruction.
- **`seam-above`**: the enclosing function already accepts the value as a parameter — run `ll-code callers-of <symbol>` (the hit's own `results[].symbol`, which is the enclosing function) and evaluate *that* hit instead of the original.
- **`target`**: the hit is not `test-only`, is on the production path (not `fallback`), and the enclosing function does not already expose the value as a parameter (not `seam-above`).
- **Hop cap**: the `seam-above` walk is capped at exactly one extra hop and does not recurse. If it does not resolve to a clean `target`/`fallback`, the hit is labelled `seam-above (unresolved)` and emitted **impact-only** — Dependent-Files bullet with the enclosing signature quoted, **no `Update <path>` bullet in 8b**. It is never promoted to `target`; that default would re-emit the instruction this issue exists to suppress.
- **No-graph degradation**: the hop cannot run when `ll-code` reports `available: false` / exits `2`, or when the hit is agent-discovered and carries no `symbol`. In both cases classify `seam-above` from the enclosing signature and stop — do **not** reconstruct the caller set by Grep. The result is `seam-above (unresolved)` and follows the impact-only rule above.
- **Empty-suppression announcement**: if suppression leaves 8b's Wiring Phase with no caller bullet at all, emit the "No direct caller change target identified — N hits classified …" line instead. Silent absence is not an acceptable output.
- **Hop-result classification**: the one-hop walk's own results are classified by these same rules with `seam-above` disabled — each resolves to `test-only`, `fallback`, or `target`, never a second hop. The `test-only` prefilter applies to them first, as it does to the original hits.
- **Output/escape hatch**: a `target` entry must quote the enclosing signature or guard line that justifies the classification. An entry that cannot be justified that way is downgraded to impact-only — it keeps its Dependent Files bullet but **does not get an `Update <path>` bullet in 8b's Wiring Phase**. (Downgrading "to Dependent Files, not Files to Modify" is a no-op at 8a, where callers already route to Dependent Files unconditionally; the effective downgrade is the suppressed 8b instruction.)

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` § **8b** (`:400-416`) — **the primary edit.** The Wiring Phase
  template emits `- Update `<caller>` — adjust calls to `changed_function()`` for every
  entry in `new_impl_steps`, with no notion of suitability. Gate the `Update <path>` form on
  `target`; `fallback` and `test-only` hits must not produce a change instruction here. This is
  the surface `/ll:manage-issue` and the `rn-*` loops execute — see § *8b is the surface that
  actually emits the harmful instruction*
- `skills/wire-issue/SKILL.md` § **Phase 5** (`:260-287`) — `callers_to_add` (`:268`) carries the
  classification. **It is the sole carrier** — `new_impl_steps` (`:278`) is a list of phases and
  8b's emptiness gate, with no per-hit slot (see § `new_impl_steps` is a gate, not a per-hit
  carrier). This is where every caller hit converges — graph-seeded, agent-discovered, and
  `available: false` alike. Follow the ENH-3050 `gate_consumers` / `conditional_branches`
  precedent for adding a carried bucket. `importers_to_add` (`:269`) is left unclassified
- `skills/wire-issue/SKILL.md` § **8a** (`:342-398`) — the Integration Map writer. **Correction:
  `:346` already routes all callers to `Dependent Files` unconditionally and `:356`'s `Files to
  Modify` is registrations-only**, so there is no caller mis-routing to fix here. The 8a edit is
  the smaller one: add the classification label and the justifying-quote field to the bullet
  formats; `test-only` reuses the existing Tests routing at `:373-382`
- `skills/wire-issue/SKILL.md` § **Phase 7** (`:302-316`) — the interactive pre-approval summary
  prints "Callers/importers missing from Integration Map: N". Post-change that N includes
  `fallback` / `test-only` hits, so the user approves a change list larger than what 8b will
  instruct. Split or qualify the count (one line)
- **`SKILL.md` line budget**: the file is at **493 of the 500-line cap**
  (`scripts/tests/test_enh494_skill_companions.py:21`, `SKILL_LINE_LIMIT = 500`) — 7 lines of
  headroom. Editing `:142` in place is safe (it is a single long line), but the Phase 5/8a
  additions will not fit. Use the ENH-494 companion-file pattern: put the classification
  procedure in a flat companion under `skills/wire-issue/` (e.g. `caller-classification.md`)
  and link to it from Phase 5/8a in one line each, exactly as `behavior-parity.md` is linked
  from `:384-388`. Register the companion so `test_enh494_skill_companions.py` sees it.
  **Budget the four edits concretely: net `SKILL.md` growth must be ≤ 7 lines.** Even with the
  companion, the four sections each need at least a link or a gating clause (Phase 5 bucket
  annotation, 8b `target` gate + the empty-suppression line, 8a label/quote fields, Phase 7 count
  split) — that is realistically 6–10 lines. If the budget is exceeded, **extract rather than
  trim the rule**: the four fenced markdown templates in 8a (`:346-398`) are the obvious donor —
  they are pure format examples, the exact category ENH-494 companions exist for. Do not shrink
  the new rule to fit; a truncated rule is the defect this issue is fixing
- `skills/wire-issue/graph-discovery-layer.md` — the **graph-specific half only**: the
  test-path prefilter over `results[]` and the one-hop `seam-above` walk keyed off
  `results[].symbol`. Correct the `confirm-before-map` gloss (:26-28) to stop reading as a
  target-selection rule, and point it at the Phase 5/8a classification. Also amend :15-16,
  which currently disclaims exactly the output change this issue makes ("The written output
  (Integration Map) is format-identical to today; only how candidates are found changes").
  **Existing test constraint on this file**:
  `test_enh3098_refine_issue_graph_seeding.py::test_wire_issue_layer_delegates_rather_than_duplicates`
  (`:136-144`) asserts `"Exit codes" not in text`. The new prose about the degraded (`available:
  false` / exit `2`) hop must therefore reference the shared guide rather than restating the
  exit-code contract — describe the *behavior* ("when the graph is unavailable, classify from the
  signature and stop") and link out for the codes
- `docs/guides/GRAPH_DISCOVERY_GUIDE.md` — **`## Consumers` section only** (per § Decision
  Rationale). Add one wire-issue paragraph mirroring the verify-issues carve-out at :19-27.
  The three safety rules at :82-92 stay byte-unchanged
- `skills/wire-issue/SKILL.md:142` — the compressed three-safety-rules restatement, which is
  marked "verbatim" and so must stay in sync with the file above
- `skills/wire-issue/output-report.md:32-42` — the **terminal run report** (emitted verbatim
  per `:3`), which mirrors what 8a wrote; it is not the writer, so it follows 8a rather than
  defining the format. Its `## INTEGRATION MAP CHANGES` block is four fixed subsections of flat
  `` `path` — description `` bullets with no field for a classification or a justifying quote;
  that format must grow both. Note the four existing subsections already
  supply the routing targets for three of the four classification values — `target` →
  *Added to Files to Modify*, `fallback` → *Added to Dependent Files*, `test-only` →
  *Added to Tests* — so only the classification label and justifying quote are genuinely new
  fields. `seam-above` is not itself an output value: it re-points the walk, and the resolved
  one-hop result is what gets emitted. Also: the `## MISSING WIRING FOUND` table (`:22-30`) has
  fixed category rows and no home for a `fallback`-classified hit — either add a row or fold
  them into `Callers/Importers` with the count qualified

### Dependent Files (Callers/Importers)
- **Nine** `ll-adapt`-generated host mirrors, not three — every file under Files to Modify that
  lives in `skills/wire-issue/` is mirrored into all three hosts, and this issue edits three of
  them (`graph-discovery-layer.md`, `SKILL.md`, `output-report.md`). All nine paths confirmed
  present 2026-08-19:
  - `.qwen/skills/wire-issue/{graph-discovery-layer,SKILL,output-report}.md`
  - `.gemini/skills/wire-issue/{graph-discovery-layer,SKILL,output-report}.md`
  - `.kimi-code/skills/wire-issue/{graph-discovery-layer,SKILL,output-report}.md`

  **Plus three more if the ENH-494 companion file is added** (see the `SKILL.md` line-budget
  entry under Files to Modify): a new companion under `skills/wire-issue/` is mirrored
  into all three hosts too, taking the total to **twelve**. Regenerate all of them after the edits;
  `scripts/tests/test_adapters.py::test_companion_drift_is_repaired` (:1943) covers the repair
  path, but confirm rather than assume
- ~~`commands/refine-issue.md` § 3.05~~ — **out of scope** per § Decision Rationale.
  refine-issue consumes hits as research leads, not change targets, and inherits no local rule

### Similar Patterns
- `skills/wire-issue/prose-dependency-gate.md`, `static-coupling-layer.md` — sibling
  confirmation layers; check whether either already reads enclosing context and can be
  reused rather than duplicating the rule

### Tests
- `scripts/tests/test_enh3098_refine_issue_graph_seeding.py` — assert the `SKILL.md:142`
  block still carries rule 2 in sync with `graph-discovery-layer.md`, since drift between the
  two is what would silently un-fix this. This file already holds the adjacent
  `test_wire_issue_layer_delegates_rather_than_duplicates` (:136-144) and
  `test_states_safety_rule` (:119-127), so the sync test belongs beside them.
  (An earlier draft of this issue named a skills-structure test module that does not exist in
  this repo — do not create one; use the file named above.)

  **This is a substring assertion, not a byte-equality one — decided 2026-08-19.** Per the
  Codebase Research Findings below, the four restatements of rule 2 are *already*
  non-byte-identical and always have been; a byte-sync test would fail on the first commit and
  reconciling all four is scope this issue does not budget. Follow the existing
  `test_states_safety_rule` (:119-127) style: assert that each of the required marker phrases
  is **present in** each file's text, not that the surrounding prose matches. Concretely,
  assert `"confirm-before-map"` and each classification value (`test-only`, `target`,
  `fallback`, `seam-above`) appear in both `skills/wire-issue/SKILL.md` and
  `skills/wire-issue/graph-discovery-layer.md`. That pins the contract's *content* against
  silent removal — the actual failure mode — while tolerating the wording drift that already
  exists
- Same file — assert `GRAPH_DISCOVERY_GUIDE.md`'s three safety rules (:82-92) are unchanged by
  this issue, pinning the § Decision Rationale boundary so a later pass does not "simplify"
  the wire-issue-local rule back into the shared contract
- Assert `skills/wire-issue/SKILL.md` stays **at or under the 500-line cap** — already covered
  by `scripts/tests/test_enh494_skill_companions.py:72-81`, so no new test is needed; it is
  named here so the implementer treats it as a gate rather than discovering it at commit time.
  If a companion file is added, its registration assertion in the same module applies too
- **Not assertable from `scripts/tests/`** — the two entries below exercise an LLM skill end to
  end and cannot be checked by pytest. They belong in `/ll:verify-issue-loop` or
  `/ll:create-eval-from-issues`. **Implementation Step 8 (`pytest` passes) does not gate on
  them**, and Step 7 is not a pytest step:
- Regression fixture: a symbol whose production `callers-of` hits are inside `if x is None:`
  branches of functions that already expose the value as a parameter — assert the pass emits
  `seam-above` / `fallback`, not `target`, and that its five test-file hits land as
  `test-only`. `build_ref_index` is the natural fixture; it is a real, stable instance of
  exactly this shape, and its 8-hit / 5-test-hit split (quoted verbatim under § Worked example)
  exercises the prefilter and the classifier in one case

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
2. Add the wire-issue-local classification rule (four values: `test-only` / `fallback` /
   `seam-above` / `target`, decided in that order, with `test-only` assigned by path before any
   enclosing-function read) and the justifying-quote requirement to **`SKILL.md` §§ Phase 5, 8b,
   and 8a** — not to `graph-discovery-layer.md` — so it covers agent-discovered hits and the
   `available: false` path. Carry the classification on `callers_to_add` (`:268`) **only** —
   `new_impl_steps` (`:278`) is a phase list and 8b's emptiness gate, not a per-hit carrier —
   following the ENH-3050 `gate_consumers` precedent noted at `:346`. Leave `importers_to_add`
   (`:269`) unclassified.
   Include the two fail-safe rules: an unresolved `seam-above` is **impact-only, never promoted
   to `target`**, and the degraded no-graph path classifies from the signature and stops.
   **Check the 500-line cap first** (`SKILL.md` is at 493): put the procedure in an ENH-494
   companion file and link it from Phase 5/8a/8b in one line each, following the
   `behavior-parity.md` precedent at `:384-388`. Registration means adding the companion path to
   `EXPECTED_COMPANIONS` (`scripts/tests/test_enh494_skill_companions.py:24`); note
   `test_skill_links_to_companion` (`:61`) additionally requires a link from `SKILL.md`.
2b. **Gate 8b's `Update <path>` bullet on `target`** (`SKILL.md:400-416`). This is the step that
   actually fixes the worked example — a `fallback`, `test-only`, or `seam-above (unresolved)` hit
   must not produce a Wiring Phase change instruction. Mechanically: 8b already renders its bullets
   from the file buckets, so this is a filter on `callers_to_add`, not a change to
   `new_impl_steps`'s non-empty gate at `:400`. **Add the empty-suppression line** so that
   suppressing every caller bullet emits "No direct caller change target identified — N hits
   classified …" rather than nothing. Do this before the 8a and output-report edits, which follow
   it.
2c. Qualify Phase 7's caller count (`SKILL.md:302-316`) so the interactive approval prompt does
   not present `fallback` / `test-only` hits as pending changes.
3. Add the **graph-specific half** to `graph-discovery-layer.md`: the test-path prefilter over
   `results[]` and the one-hop `seam-above` walk with its explicit hop cap, keyed off the hit's
   own `results[].symbol` (already the enclosing function — no derivation step). Classify the
   hop's own results by the same rules with `seam-above` disabled. Correct the
   `confirm-before-map` gloss (:26-28) so it stops reading as a target-selection rule, and
   amend :15-16's "format-identical to today" disclaimer.
4. Grow `output-report.md:32-42`'s entry format to carry the classification label and the
   justifying quote, and give `fallback` a home in the `## MISSING WIRING FOUND` table
   (`:22-30`). This mirrors what 8a writes; do it after step 2, not before.
5. Add the wire-issue carve-out paragraph to `GRAPH_DISCOVERY_GUIDE.md`'s `## Consumers`,
   mirroring the verify-issues one at :19-27. Verify the three safety rules at :82-92 are
   byte-unchanged.
6. Add the sync test pinning canonical rule 2 → `graph-discovery-layer.md` →
   `SKILL.md:142`. Put it in
   `scripts/tests/test_enh3098_refine_issue_graph_seeding.py` (alongside
   `test_wire_issue_layer_delegates_rather_than_duplicates`) — **not** in a
   a skills-structure test module, which does not exist in this repo.
   Write it as a **substring/marker-phrase assertion** in the style of the adjacent
   `test_states_safety_rule` (:119-127) — never byte-equality. See the Tests section for the
   exact markers and the rationale; the four restatements are already non-byte-identical, so a
   byte-sync test fails immediately and reconciling them is out of scope here.
7. Regenerate the `.qwen/`/`.gemini/`/`.kimi-code/` mirrors via `ll-adapt` — three hosts ×
   every edited file under `skills/wire-issue/` (`graph-discovery-layer.md`, `SKILL.md`,
   `output-report.md`, **plus the new companion file if step 2 adds one**), not just
   `graph-discovery-layer.md`. Nine files, or twelve with the companion.
8. `python -m pytest scripts/tests/` passes. **This is the completion gate.** It covers the
   sync test (step 6), the 500-line cap and companion registration
   (`test_enh494_skill_companions.py`), and the mirror-drift repair
   (`test_adapters.py::test_companion_drift_is_repaired`). It does **not** cover step 9, which
   is not a pytest step.
9. *(Post-merge validation, not a pytest gate.)* Re-run wire-issue against ENH-3000 as an
   end-to-end check: it should classify `scripts/little_loops/issues/research_triage.py:212`/
   `:317` as `fallback` + `seam-above`, route the five `scripts/tests/` hits to `test-only`,
   and surface `scripts/little_loops/cli/issues/research_triage.py:61` as the target.
   (Use the full disambiguated paths — bare `research_triage.py` resolves to two files.)
   This and the `build_ref_index` regression fixture require executing an LLM skill; author
   them via `/ll:verify-issue-loop` or `/ll:create-eval-from-issues`, not in `scripts/tests/`.

## Impact

- **Priority**: P2 — wiring output is executed unquestioned by `/ll:manage-issue` and the
  `rn-*` loops, and the defect is silent (the wrong change works). Matches the P2 of its
  doctrine siblings ENH-3045/3049/3050.
- **Effort**: Small-Medium — skill-doctrine edits plus one sync test and a nine-to-twelve-file
  mirror regen. No Python behavior change. Revised up from Small: the rule now lands in
  `SKILL.md` §§ Phase 5/8a rather than only `graph-discovery-layer.md`, and `SKILL.md` is at
  493/500 lines, so an ENH-494 companion file is almost certainly required (one more file, one
  more registration, three more mirrors), and the rule now also lands in §§ 8b and Phase 7 — four
  sections of `SKILL.md`, not two. The step-1 scope decision is closed, and it shrank the
  blast radius: the shared contract takes a `## Consumers` paragraph rather than a rule amendment,
  and refine-issue drops out of scope.
- **Risk**: Low-Medium. The real risk is cost: a per-hit enclosing-function read is strictly
  more expensive than a per-hit line Grep, partially eroding what ENH-2578 bought. The
  test-path prefilter is the mitigation — it drops the read count to the production callers
  only (8 → 3 on the `build_ref_index` fixture, ~60%). **The 8 → 3 figure is the prefilter in
  isolation and understates the true cost**: each `seam-above` hit adds one more `ll-code`
  query plus an enclosing-function read per non-test result of that hop. On the worked example
  the two `seam-above` hits at `:212`/`:317` add a `callers-of triage_research_axes` query whose
  production result needs its own read, so the realistic count is 3 reads + 1–2 hop queries +
  1–2 hop reads — still well under the naive 8, but not 60% off. Measure with ENH-2578's own
  before/after token methodology rather than quoting the prefilter figure as the net.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: how caller hits are classified before they become change instructions — at
  Phase 5 (both carriers), **8b** (the emitting surface), 8a, and Phase 7, covering graph-seeded
  hits, Agent-1-discovered hits, and the `available: false` path alike (per § Where the rule
  lives).
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
- `/ll:confidence-check` - 2026-08-19T22:54:07 - `d0dc85a4-ecd6-4389-bee2-0558872d4de1.jsonl`
- pre-implementation review - 2026-08-19 - **fail-safe direction corrected and the second
  carrier retracted.** Seven changes, all verified against the current skill: (a) **`new_impl_steps`
  is not a carrier** — `:278` is a list of *phases* and 8b uses it only as an emptiness gate at
  `:400`; the `Update <path>` bullets render from the file buckets, so `callers_to_add` (`:268`)
  is the sole carrier and the prior review's "second required carrier" would have sent the
  implementer looking for a per-hit field that does not exist; (b) **the hop cap defaulted to the
  wrong side** — "unresolved → emit `target` with a flagged note" re-emits the exact ENH-3000
  instruction; unresolved now fails to impact-only, `seam-above (unresolved)`, with no 8b bullet;
  (c) **added the missing no-graph path for the hop** — the walk *is* `ll-code callers-of`, so it
  cannot run under safety rule 1 or for agent-discovered hits with no `symbol`, despite the issue
  claiming coverage of both; classify from the signature and stop, no Grep reconstruction;
  (d) **added the empty-suppression announcement** — suppressing every caller bullet otherwise
  turns a confidently-wrong instruction into a silently-absent one; (e) **`importers_to_add`
  declared out of scope** for classification (module-level imports have no guard branch and no
  parameter seam), since the enum was called "exhaustive" over every hit; (f) **line budget made
  concrete** — ≤ 7 lines net, with 8a's four fenced templates (`:346-398`) named as the extraction
  donor, and an explicit "extract, do not trim the rule"; (g) **flagged the existing
  `"Exit codes" not in text` assertion** (`test_enh3098_…:136-144`) that Step 3's degraded-hop
  prose can trip. Also corrected the § Impact cost claim: 8 → 3 is the prefilter in isolation and
  excludes the hop's own query and reads.
- pre-implementation review - 2026-08-19 - **8b added as the primary edit; the `:346-361`
  routing premise corrected.** Verified against the current skill that (a) `SKILL.md:346` routes
  *all* callers to Dependent Files unconditionally and `:356`'s Files to Modify is
  registrations/manifests only — so the "Files to Modify vs Dependent Files" mis-routing this
  issue claimed to fix does not exist, and 8a already draws that line; (b) the instruction that
  caused the ENH-3000 failure is emitted by **Phase 8b's Wiring Phase template**
  (`SKILL.md:400-416`, `- Update `<caller>` — …`) from `MISSING_WIRING.new_impl_steps`
  (`:278`) — a bucket the issue never mentioned, and the surface `/ll:manage-issue` and the
  `rn-*` loops actually execute. As written the issue would not have fixed its own worked
  example. Changes: 8b added to § Where the rule lives, the Call Path, Files to Modify, and
  Implementation Steps (new step 2b); `new_impl_steps` added as a second required Phase 5
  carrier; the escape-hatch downgrade restated as "suppress the 8b instruction" rather than the
  no-op "route to Dependent Files"; ENH-3050's `gate_consumers` carried-bucket pattern
  (`SKILL.md:346`) cited as the mechanical precedent; Phase 7's pre-approval count
  (`:302-316`) added as a fifth surface (step 2c); companion registration pinned to
  `EXPECTED_COMPANIONS` (`test_enh494_skill_companions.py:24`) plus the
  `test_skill_links_to_companion` link requirement (`:61`). Re-confirmed unchanged: `SKILL.md`
  at 493 lines, `:142` is the three-safety-rules restatement, guide `## Consumers` at `:19-27`
  and the three rules at `:82-92`.
- `/ll:confidence-check` - 2026-08-19T22:12:42 - `c3e6a7c8-5adc-45bf-befc-6299d0df70e8.jsonl`
- pre-implementation review - 2026-08-19 - **placement corrected: the rule moves from Phase 3.6
  to Phase 5/8a.** Verified against the current skill that Phase 3.6's confirmed candidates
  feed Phase 4 Agent 1's *seed slots*, not the Integration Map — which is written at Phase 8a
  (`SKILL.md:342-398`) from `MISSING_WIRING` computed at Phase 5 (`:260-279`). A classification
  assigned at 3.6 had no carrier to reach the routing decision it exists to change. Two further
  holes closed by the move: safety rule 1 (`available: false` → skip 3.6 entirely) would have
  deleted the rule outright, and Agent-1-discovered callers never pass through 3.6 at all — the
  ENH-3000 failure mode is a property of any caller hit, not of graph-seeded ones.
  `graph-discovery-layer.md` keeps only the graph-specific half (test-path prefilter, one-hop
  `seam-above` walk). Also: (a) flagged `SKILL.md` at **493 of the 500-line cap**
  (`test_enh494_skill_companions.py:21`) — an ENH-494 companion file is the escape hatch and
  raises the mirror count to twelve; (b) added the missing rule for classifying the
  `seam-above` hop's *own* results (same rules, `seam-above` disabled); (c) noted `test-only`
  routing already exists via Phase 5's `tests_to_add` (`:270`) — only the skipped
  enclosing-function read is new; (d) folded the prior review's still-open note into the body:
  Step 9 and the regression fixture are not pytest-assertable, and Step 8 is the completion
  gate. Renumbered Implementation Steps (a duplicate `5.` is fixed) and reordered so the
  `output-report.md` edit follows 8a rather than defining the format.
- `/ll:confidence-check` - 2026-08-19T21:55:18 - `9989268f-716e-48be-a048-f308fd3538aa.jsonl`
- pre-implementation review - 2026-08-19 - five changes applied against verified codebase
  state: (a) added a fourth classification value `test-only` — the enum was declared
  exhaustive but had no bucket for test callers, which are 5 of the 8 real
  `callers-of build_ref_index` hits; (b) made the test-path prefilter the named cost control
  for the § Impact risk (8 → 3 enclosing-function reads on the fixture); (c) recorded that
  `results[].symbol` already *is* the enclosing function, so the `seam-above` hop needs no
  derivation step; (d) corrected the mirror count from three files to nine (`SKILL.md` and
  `output-report.md` are mirrored too, and both are edited); (e) pinned Step 5's sync test to a
  substring/marker-phrase assertion — byte-equality would fail on commit one, since the four
  rule-2 restatements are already non-byte-identical per this issue's own research findings.
  **Still open**: the Tests §3 regression fixture and Step 7 both require executing an LLM
  skill and cannot be asserted from `scripts/tests/` — they belong in
  `/ll:verify-issue-loop` or `/ll:create-eval-from-issues`, and Step 8 should not be read as
  gating on them.
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
