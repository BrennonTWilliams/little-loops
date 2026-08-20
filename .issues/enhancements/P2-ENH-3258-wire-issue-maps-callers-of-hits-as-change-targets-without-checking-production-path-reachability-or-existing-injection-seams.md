---
id: ENH-3258
type: ENH
title: wire-issue maps callers-of hits as change targets without checking production-path
  reachability or existing injection seams
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-19'
captured_at: '2026-08-19T21:25:08Z'
status_note: shipped 2026-08-19; validated on a clean fixture, one clause added
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

Note the shape: **five of the eight hits are test callers.** A test caller is never a change
target, so the rule's enclosing-function read only ever applies to the production remainder.

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

Before the Wiring Phase emits an `Update <path>` instruction for a caller hit, the enclosing
function of the call site is read. If the call sits in a guard branch, or the enclosing function
already accepts the value as a parameter, no change instruction is emitted — the path is recorded
with the guard line or signature quoted, and with the reason stated.

The Integration Map keeps its current routing. The change is narrow and lands on one surface:
Phase 8b, which writes the `## Implementation Steps` bullets that `/ll:manage-issue` and the
`rn-*` loops actually execute.

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

**Scope decision — 2026-08-19: implement the simple version.** Six review rounds each found a
carrier/plumbing defect one hop further upstream than the last, and each round's correction
enlarged the surface for the next. That is one question answered incrementally, not six
discoveries. Root cause: this is a typed data-flow change specified in an untyped prose system
(skills are markdown prompts; `callers_to_add` is a bullet, not a schema), verified only by
inspection — which does not converge. More doctrine in an already-493-line prompt also does not
reliably increase LLM compliance.

**The change, verbatim. This is the whole of it:**

> Before emitting an `Update <path>` bullet in the Wiring Phase, read the enclosing function of
> the call site. If the call sits in a guard branch (`if x is None:`, `except`, a
> `--dry-run`-style guard), or the enclosing function already accepts the value as a parameter,
> do not emit the change instruction — record the path with the guard line or signature quoted,
> and say why instead. **When a parameter is the seam, emit an `Inject at <path>` Wiring Phase
> bullet naming it — redirect the touchpoint, never drop it.**

The bolded second sentence was **added 2026-08-19 after the step-4 fixture**, per § Deferred's
"one element for one observed failure" rule. Rationale in § Session Log; full procedure and worked
example in the companion.

It lands in one place: `skills/wire-issue/SKILL.md` § 8b, gating the `Update <path>` bullet, with
the procedure extracted to `skills/wire-issue/caller-suitability-gate.md` (the line budget in
§ Files to Modify forced the extraction — the inline rule sits at 6 lines and the file at exactly
500).

**The shared safety rules are not amended.** `docs/guides/GRAPH_DISCOVERY_GUIDE.md:82-92` stays
byte-unchanged. The three rules there govern *trust* — is this hit real? — and on the worked
example they worked correctly: the call really was at
`scripts/little_loops/issues/research_triage.py:212`. This is a *suitability* rule, and it belongs
to wire-issue alone: `/ll:refine-issue` consumes hits as research leads, where a hit sitting in a
fallback branch is still a perfectly good lead. The guide already sets that precedent with the
`/ll:verify-issues` carve-out at `:19-27`.

### Deferred — the elaborate mechanism

Rounds 2–6 specified a four-value classification enum (`test-only` / `target` / `fallback` /
`seam-above`), a capped one-hop `seam-above` walk with `Class::method` stripping and an
unresolved-fails-to-impact-only rule, a test-path prefilter, a file-level collapse rule, an
empty-suppression announcement, a Phase 4 Agent 1 return-contract widening, a Phase 5 carrier
widening, a Phase 7 count qualifier, `output-report.md` format growth, a `## Consumers` paragraph
in the shared guide, and a marker-phrase sync test. **All of it is deferred.** The research behind
it is preserved in § Codebase Research Findings and § Session Log.

Reopen it only on a concrete miss from the regression fixture (§ Implementation Steps step 4) —
and then add *one* element for *one* observed failure, not the whole enum.

**Exercised once, 2026-08-19.** The fixture surfaced exactly one failure: the rule was purely
subtractive. It suppressed the wrong `Update` bullet and emitted nothing in its place, leaving a
Wiring Phase with no injection touchpoint at all for an issue whose Implementation Steps said
"thread the config-sourced list from production call paths." One element was added — the
`Inject at <path>` clause in § Proposed Solution. The enum stays deferred; none of its other nine
elements were reopened.

## Program Design

N/A — `program_design_not_applicable: true`. This is a skill-doctrine (markdown prompt) change: no
types, no signatures, no runtime call path.

The one placement fact that matters (verified 2026-08-19): **Phase 8b (`SKILL.md:400-416`) is the
surface that emits the harmful instruction**, via the template bullet
``- Update `<caller>` — adjust calls to `changed_function()` ``. Phase 8a (`:346`) already routes
all callers to *Dependent Files* unconditionally — and `:356`'s *Files to Modify* path is for
registration/manifest files only — so there is no caller mis-routing to fix there.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` § **8b** (`:400-416`) — **the only edit.** Gate the `Update <path>`
  bullet on the enclosing-function check in § Proposed Solution.
- **Line budget**: `SKILL.md` is at **493 of the 500-line cap**
  (`scripts/tests/test_enh494_skill_companions.py:21`, `SKILL_LINE_LIMIT = 500`) — 7 lines of
  headroom. If the rule does not fit, **extract rather than trim it**: 8a's four fenced markdown
  templates (`:346-398`) are the obvious donor, moved to an ENH-494 companion under
  `skills/wire-issue/` and linked back in one line, exactly as `behavior-parity.md` is linked from
  `:384-388`. A companion must be registered in `EXPECTED_COMPANIONS`
  (`scripts/tests/test_enh494_skill_companions.py:24-35`) and linked from `SKILL.md`
  (`test_skill_links_to_companion:61`). Do not shrink the rule to fit; a truncated rule is the
  defect this issue is fixing.

### Dependent Files (Callers/Importers)
- `ll-adapt`-generated host mirrors — `.qwen/`, `.gemini/`, and `.kimi-code/` each mirror every
  file under `skills/wire-issue/` (all confirmed present 2026-08-19). Three hosts × each edited
  file, plus three more if a companion is created. Regenerate after the edits;
  `scripts/tests/test_adapters.py::test_companion_drift_is_repaired` (`:1943`) covers the repair
  path, but confirm rather than assume.

### Similar Patterns
- `skills/wire-issue/prose-dependency-gate.md`, `static-coupling-layer.md` — sibling confirmation
  layers. Neither reads enclosing function context today (see § Codebase Research Findings), so
  this is new logic rather than reuse of an established pattern.

### Tests
- The 500-line cap and companion registration are already covered by
  `scripts/tests/test_enh494_skill_companions.py:72-81`. **No new pytest is added by this issue** —
  a prompt-gating rule is not pytest-assertable. Treat the cap as a gate to satisfy rather than
  discovering it at commit time.
- **Regression fixture — not assertable from `scripts/tests/`.** `build_ref_index` is the natural
  case: 8 caller hits, 5 of them test files, and its two production hits
  (`scripts/little_loops/issues/research_triage.py:212` and `:317`) are both inside
  `if index is None:` guards, in functions that already accept `index: RefIndex | None`
  (`:191-195`, `:279-283`). Expected: the pass emits no `Update` instruction for that file, and
  says why instead. This requires executing an LLM skill; author it via `/ll:verify-issue-loop` or
  `/ll:create-eval-from-issues` if it needs to be repeatable.

### Documentation
- None. `docs/guides/GRAPH_DISCOVERY_GUIDE.md` is **not** modified — see § Proposed Solution.

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

- The Tests entry an earlier draft named — a "skills structure" test module under `scripts/tests/` — has no tracked file at that path in this repo (the literal filename is omitted here so `ll-issues format-check` does not flag it as a stale ref). The actual candidate test files for the drift-check named in this section are `scripts/tests/test_enh3098_refine_issue_graph_seeding.py` (`test_wire_issue_layer_delegates_rather_than_duplicates`, `test_states_safety_rule`) and `scripts/tests/test_enh494_skill_companions.py`, neither of which currently checks SKILL.md:142/graph-discovery-layer.md content sync (see the earlier findings block above). The new sync test belongs in one of these files, not in a new skills-structure module that would need to be created from scratch.
- Ambiguous file reference: bare `research_triage.py:212`/`:317` (used in Current Behavior and Proposed Solution) resolves to two distinct files in this repo — `scripts/little_loops/issues/research_triage.py` (the guard sites at :212/:317, per the worked example) and `scripts/little_loops/cli/issues/research_triage.py` (holds `triage_research_axes`'s sole production caller at :61, per Expected Behavior's "two hops up" point). Implementers should use the full disambiguated paths when citing these lines.

## Implementation Steps

1. Add the rule to `skills/wire-issue/SKILL.md` § 8b (`:400-416`), gating the `Update <path>`
   bullet. Watch the 7-line budget; extract 8a's fenced templates to an ENH-494 companion rather
   than trimming the rule if it does not fit (see § Files to Modify).
2. Regenerate the `.qwen/` / `.gemini/` / `.kimi-code/` mirrors via `ll-adapt` — three hosts ×
   each edited file under `skills/wire-issue/`.
3. `python -m pytest scripts/tests/` passes. **This is the completion gate.** It covers the
   500-line cap, companion registration, and the mirror-drift repair. It does **not** cover
   step 4, which is not a pytest step.
4. *(Post-merge validation, not a pytest gate.)* Run wire-issue against ENH-3000. Expected: it
   does **not** emit "Update `scripts/little_loops/issues/research_triage.py`" for the `:212` /
   `:317` hits. (Use full disambiguated paths — bare `research_triage.py` resolves to two files in
   this repo.)
5. If the fixture passes, close ENH-3258. Reopen the deferred mechanism only on a concrete miss —
   one element for one observed failure.

## Impact

- **Priority**: P2 — wiring output is executed unquestioned by `/ll:manage-issue` and the
  `rn-*` loops, and the defect is silent (the wrong change works). Matches the P2 of its
  doctrine siblings ENH-3045/3049/3050.
- **Effort**: Small — one gating rule in one section of one skill file, plus a mirror regen. No
  Python behavior change and no new test. Revised down from Small-Medium on 2026-08-19 when the
  elaborate mechanism was deferred.
- **Risk**: Low. The rule costs one enclosing-function read per caller hit that would otherwise
  have produced an `Update` bullet — strictly more than the per-hit line Grep it follows, so it
  partially erodes what ENH-2578 bought, but it is bounded by only firing on hits already headed
  for a change instruction. The opposite risk — an LLM under-applying a prose rule inside a
  493-line prompt — is exactly what the regression fixture checks.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: gating the `Update <path>` Wiring Phase bullet at **8b** — the surface that emits
  the executed instruction — on a read of the call site's enclosing function. Applies to every
  caller hit reaching 8b, whatever discovered it (graph-seeded, Agent-1-discovered, or on the
  `available: false` path).
- **Out of scope (deferred)**: the four-value classification enum and its machinery — see
  § Deferred under Proposed Solution. Nothing outside `skills/wire-issue/SKILL.md` § 8b is edited;
  Phases 4/5/7, 8a, `graph-discovery-layer.md`, `output-report.md`, and
  `docs/guides/GRAPH_DISCOVERY_GUIDE.md` are all untouched by this issue.
- **Out of scope**: the accuracy of `ll-code callers-of` itself — it was correct in the
  worked example. See BUG-3091 for a genuine `codegraph` resolution defect.
- **Out of scope**: assertions *about* cited symbols (reusable / unchanged / behaves-thus) —
  that is ENH-3045's claim-grounding half. This issue covers targets *derived from* symbols.
- **Out of scope**: fixing ENH-3000's wiring text — already corrected in that issue.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/GRAPH_DISCOVERY_GUIDE.md` | Canonical `ll-code` contract and the three safety rules. **Not modified** — they govern trust, this issue adds a suitability rule one consumer over |
| `skills/wire-issue/graph-discovery-layer.md` | Wire-issue's `confirm-before-map` gloss on those rules. **Not modified** — context for why 8b needed a second, different rule |
| `.claude/CLAUDE.md` | § Development Preferences — skills over agents; this is a skill-doctrine change |

## Session Log
- fixture validation (step 4) - 2026-08-19 - **ran in a fresh session, cold, as designed.** Two
  fixtures, because the first was contaminated:
  - **ENH-3000 (the specified fixture) — PASS, but weak evidence.** No `Update
    ...issues/research_triage.py` bullet was emitted for the `:212` / `:317` hits; both were
    recorded under Dependent Files with the `if index is None:` guard and the
    `index: RefIndex | None = None` signature quoted. **However the fixture is contaminated**: the
    ENH-3000 issue file already carries a `§ Config Threading` section and a struck-through Wiring
    Phase bullet stating verbatim that `:212`/`:317` are fallbacks and naming the `index=` seam.
    The correct answer was in the input, so this shows "did not regress", not "the rule fired".
    Step 4 as written did not anticipate that the fixture issue had been pre-corrected by the
    review round that discovered the defect.
  - **ENH-3300 (synthetic clean fixture) — PASS, and it fired on its own.** Constructed over real
    code: `get_untracked_files()` has exactly one production caller,
    `git_operations.py:413`, inside `if untracked_files is None:` (`:412`), whose enclosing
    `suggest_gitignore_patterns()` already accepts `untracked_files: list[str] | None = None` —
    both halves fire. The issue text said nothing about guards, fallbacks or seams. Run by a fresh
    agent with no access to this issue. It suppressed the `Update` bullet and quoted the guard
    line unprompted.
  - **The clean fixture also found the one failure** recorded in § Deferred: the Wiring Phase came
    back with only test and doc bullets and **no injection touchpoint at all**. Fix applied, then
    re-run on the same fixture: the cold agent emitted `Inject at
    scripts/little_loops/cli/gitignore.py:55 (main_gitignore())` — walking one hop up to the sole
    production caller of `suggest_gitignore_patterns()`, which never supplies `untracked_files` and
    so always falls through to the unfiltered call. Verified independently by grep; the claim is
    accurate.
  - Also observed: the Phase 4 locator agent returned four unconfirmed claims on the ENH-3000 run
    (`hooks/sweep_stale_refs.py` calling `classify_file_ref`, `issue_parser.py` reading the
    not-yet-existent config key, an `IssuesConfig.__post_init__`, `test_issue_parser.py` as a
    `RefStatus` consumer) — all four zero-hit on grep. The confirm-before-map rule caught every
    one. Noted as evidence that rule is load-bearing, not as a defect of this issue.
  - `python -m pytest scripts/tests/` → **19950 passed, 46 skipped**, exit 0.
- scope decision - 2026-08-19 - **descoped to the simple version; issue file reconciled from 880
  to ~395 lines.** After six review rounds each surfaced a carrier/plumbing defect one hop further
  upstream than the last (3.6 → Phase 5/8a → 8b → `new_impl_steps` retracted → `callers_to_add` is
  file-granular → Agent 1 returns paths only), the pattern was diagnosed as one question answered
  incrementally rather than six discoveries: a typed data-flow change specified in an untyped
  prose system, verified only by inspection. Another review round was explicitly rejected — each
  round added ~30 lines of correction that enlarged the surface for the next, and 15
  "corrected/retracted/an earlier draft" markers had accumulated. § Proposed Solution, § Program
  Design, § Integration Map, § Implementation Steps, § Impact and § Scope Boundaries were rewritten
  to the single 8b gating rule; the four-value enum and all its machinery moved to § Deferred. The
  prior rounds' findings below and § Codebase Research Findings are preserved verbatim as the
  record — **note they describe the deferred design, not the change now specified above.** Judged
  by the ENH-3000 / `build_ref_index` regression fixture rather than by another inspection pass.
- pre-implementation review - 2026-08-19 - **the carrier has no per-hit slot either, and the
  hop query does not round-trip method symbols.** Five changes, all verified against the current
  skill and against live `ll-code` output: (a) **`callers_to_add` is file-granular** — `:268`
  reads "[files from Agent 1 callers …]" and Phase 4 Agent 1's contract (`:174-180`) is "Return
  file paths grouped by:", i.e. **paths only, no line, no enclosing symbol, no guard evidence**.
  This is the same class of error as the previously-retracted `new_impl_steps` carrier: the issue
  attached a per-hit classification to a bucket with no per-hit slot, fed by an agent that
  produces nothing to classify from. **Phase 4 Agent 1 added as a fifth (and prerequisite) edit
  surface** — step 1b — widening the *Callers / consumers* return contract to per-call-site
  records; (b) **added the missing file-level collapse rule** — 8a/8b bullets are per-file and one
  file can hold hits of different classes (`research_triage.py` holds two), so: a file is a
  `target` iff *any* of its hits is `target`, and suppression applies only when *every* hit is
  non-target. Left unstated, an implementer would plausibly invert it and over-suppress;
  (c) **the `seam-above` hop's "no parsing" claim is false for methods** — `results[].symbol` is
  the qualified `Class::method` form, and `ll-code callers-of "Class::method"` returns
  **`results: []`, an empty success rather than an error** (run 2026-08-19). Strip the `Class::`
  prefix; treat an empty hop as `seam-above (unresolved)` per safety rule 3, never as "no callers
  ⇒ `target`"; (d) `scripts/tests/test_enh494_skill_companions.py` added to Files to Modify —
  `EXPECTED_COMPANIONS` (`:24-35`) is a hardcoded parametrize list, so an unregistered companion
  is silently uncovered; (e) the guide's `## Consumers` **table row** (`:16`) added to scope, and
  the line budget re-forecast from "at risk" to **expected to be exceeded** now that five sections
  need edits — 8a's fenced templates should be extracted as planned work, not as a contingency.
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

- **Status**: done
