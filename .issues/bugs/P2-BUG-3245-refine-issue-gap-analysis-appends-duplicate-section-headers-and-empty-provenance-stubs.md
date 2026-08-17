---
id: BUG-3245
type: BUG
title: refine-issue gap-analysis appends duplicate section headers and empty provenance
  stubs
priority: P2
status: done
completed_at: '2026-08-17T21:58:46Z'
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:14:11Z'
relates_to:
- ENH-3244
- ENH-3238
- ENH-3247
confidence_score: 100
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3245: refine-issue gap-analysis appends duplicate section headers and empty provenance stubs

## Summary

`/ll:refine-issue --auto --gap-analysis` is not idempotent with respect to section headers. A second
pass re-emits `### Call Path`, `### Dependent Files (Callers/Importers)`, and the
`_Added by /ll:refine-issue_` provenance stub without checking whether an identical heading already
exists, producing duplicate headings and consecutive empty stubs in the issue file.

## Steps to Reproduce

Observed, not synthesized — on the `refine-to-ready-issue` run over ENH-3238
(`.loops/.history/2026-08-17T183652-refine-to-ready-issue/events.jsonl`).

1. Run `ll-loop run refine-to-ready-issue <ISSUE-ID>` on an issue whose first-pass result trips a
   gate, so `check_refine_limit` routes to `refine_followup`.
2. The run executes `refine_issue` (`--auto`), then `wire_issue`, then `refine_followup`
   (`--auto --gap-analysis`) — confirmed by the run's route trace:
   `refine_issue → wire_issue → verify_issue → check_hedges NO → check_refine_limit → refine_followup`.
3. Read the resulting issue file.

**This issue's own file is a live specimen.** It carries two
`### Dependent Files (Callers/Importers)` headings under `## Integration Map`, and
`ll-issues format-check BUG-3245` reports "structurally compliant" today. Leave them in place —
they are ENH-3247's real-world duplicate-heading fixture. Do not clean them until that issue's
detection lands and can be demonstrated against them.

## Current Behavior

After one `refine_issue` + one `wire_issue` + one `refine_followup` pass, ENH-3238's file contained:

```markdown
## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Call Path
```

Three consecutive identical provenance stubs with **no content between them** — each pass emitted
its header and then deposited nothing under it.

Separately, the file carried two `### Call Path` headings (one under `## Program Design` with a bare
symbol arrow, one further down with a different expanded path) and two
`### Dependent Files (Callers/Importers)` headings in different parent sections with different
content.

The duplicate headings were **created by** the retry pass, not merely left unfixed by it —
`refine_followup` ran additively and re-emitted headers without checking for an existing identical
one.

## Expected Behavior

`/ll:refine-issue` is idempotent with respect to section structure:

- The `_Added by_` provenance stub is emitted **only when the pass actually deposits at least one
  finding bullet under it**. A pass with no new findings emits nothing.
- A `### Call Path` / `### Dependent Files (Callers/Importers)` heading that already exists in the
  target section is **merged into**, not duplicated as a sibling.

Running the same refine pass N times over an unchanged codebase produces the same file as running it
once.

## Impact

- **Priority**: P2 - Degrades every issue that takes a retry path, which is the common case for any
  issue that trips a gate. Not P1: the damage is readability and downstream-parser ambiguity, not
  incorrect content.
- **Effort**: Small - a non-empty gate in `_batch()` plus a containment check before each header
  emission. Split across one Python file and one prose file.
- **Risk**: Low - both changes only suppress emissions; neither deletes existing content, so no
  widening of `refine-issue`'s deletion rights is needed. The `_batch()` gate has exactly one caller
  (`cmd_fold_findings`), which already rejects empty input, so the gate is unreachable in normal
  operation and cannot regress the happy path.
- **Breaking Change**: No

## Root Cause

`commands/refine-issue.md` operates under a **"never remove existing content"** rule, with exactly
one narrow carve-out — the "Bounded marker-removal right" for `⚠ Superseded` markers, which
`commands/reconcile-issue.md:60-72` cites as its own precedent. Under that rule the only safe
primitive is *append*, so each pass appends its section scaffold unconditionally rather than
checking for an existing one.

The rule itself is correct and is not what needs changing. What is missing is a **containment check
before emission** — appending nothing is not removing anything, so idempotent emission is fully
compatible with the never-remove rule and needs no new deletion right.

### Empty-stub half: fold-shaped, but the routed path is guarded

The empty-stub case is a **separate defect with a different locus**, and the original "emitted
eagerly instead of lazily by the prose rules" framing is not supported by the evidence:

- The observed shape is **one** `### Codebase Research Findings` heading carrying **three adjacent
  markers**. That is the signature of `fold_research_findings()`, which collapses N>1 heading
  occurrences into one and appends a marker per call. A hand-`Edit` would almost certainly have
  duplicated the heading alongside the marker, as it demonstrably did for the two headings in the
  other half of this bug.
- Reproduced directly: three successive `fold_research_findings(content, "Program Design", <blank>)`
  calls yield exactly one heading and three consecutive markers with nothing between them.
  `_batch()` (`scripts/little_loops/issues/fold_research_findings.py:151-153`) is
  `f"{marker}\n\n{new_content.strip(chr(10))}"` — **no non-empty gate at all**.
- But the only caller, `cmd_fold_findings`, *does* guard empty input
  (`scripts/little_loops/cli/issues/fold_findings.py:107-112` —
  `if not payload.strip(): return 1`). So a purely empty payload cannot reach `_batch()` through the
  CLI. The reproduction bypassed that guard by calling the library directly.

Two explanations therefore survive, and this issue does not need to pick between them because the
same fix closes both:

1. A hand-`Edit` violating `commands/refine-issue.md:588-592`, which already states
   `ll-issues fold-findings` is the only route and that the `_Added by …_` line must never be
   hand-written.
2. A later pass stripping the bullets out from under markers a fold had legitimately written,
   leaving the markers adjacent.

The fix is therefore **defense in depth**: gate the primitive (so the library cannot produce a
content-free stub regardless of caller) *and* restate the prose rule. See the Open Question below
for the diagnostic that would settle which one occurred.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- The `### Call Path` / `### Dependent Files (Callers/Importers)` headings this bug names are emitted via direct `Edit` against the "Enrichment Rules" template block (`commands/refine-issue.md:399-431`, `:464-482`), never through `ll-issues fold-findings` — confirmed by tracing `fold_research_findings.py`'s containment logic, which is scoped to exactly one hardcoded sub-heading (`SUB_HEADING = "Codebase Research Findings"`) and is never invoked with `sub_heading` overridden for either heading this bug names.
- The provenance-stub emptiness defect is not fully explained by the hand-`Edit` path: `fold_research_findings()`'s internal `_batch()` helper (`scripts/little_loops/issues/fold_research_findings.py`) concatenates the marker with `new_content` unconditionally, with no check that `new_content` carries an actual bullet — an empty-looking stub can occur even through the routed `fold-findings` path if the payload is non-empty on `cmd_fold_findings`'s empty-stdin guard but content-free after folding.
- Existing containment-check precedent for markdown emission at the prose level (non-Python): the `⚠ Superseded` idempotency rule at `commands/refine-issue.md:662-664` — "skip the insertion if the line immediately below already contains the substring `⚠ Superseded`" — uses substring containment on a stable prefix, not exact-text equality, for the same reason (a trailing variable clause). The Python precedent for "find existing heading, insert beneath the last one instead of creating a new one" is `append_session_log_entry()` (`scripts/little_loops/session_log.py:307-324`), which `fold_research_findings.py`'s own module docstring names as its precedent.

## Proposed Solution

1. **Gate the primitive (Python).** In `_batch()`
   (`scripts/little_loops/issues/fold_research_findings.py:151-153`), return `""` when
   `new_content.strip()` is empty, and have `fold_research_findings()` treat a no-op batch as
   contributing nothing — no marker, no blank-line churn. This makes a content-free stub
   unrepresentable at the library level, independent of which caller or explanation produced the
   observed one.
2. **Restate the prose rule (`commands/refine-issue.md`).** Keep the existing "fold-findings is the
   only route" rule at `:588-592` and make its lazy-emission consequence explicit: a pass with no
   findings runs no fold call at all. This is a restatement for the LLM's benefit; step 1 is what
   actually enforces it.
3. **Containment check before heading emission (prose-only).** Before writing `### Call Path` or
   `### Dependent Files (Callers/Importers)`, check whether that heading already exists **within the
   same parent section**; if so, append under it rather than emitting a sibling. Verified correct as
   a prose-only change: both headings are hand-emitted from the "Enrichment Rules" template blocks
   (`commands/refine-issue.md:409`, `:474`) with no fold routing, so there is no Python site to gate.
4. Do **not** add a deletion right. Existing duplicates already in the backlog are cleaned by
   **ENH-3247** (`ll-issues format-check --fix --apply`, which owns deterministic structural repair)
   — out of scope here. This issue stops new debris being created; ENH-3247 removes what exists.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- `find_subsections()`/`fold_research_findings()` (`scripts/little_loops/issues/fold_research_findings.py:104`, `:156`) already take `sub_heading` as a parameter for reuse against a different heading — the module docstring names `/ll:wire-issue`'s marker as the intended next caller, so the containment/fold logic this bug needs does not require new implementation, only routing the two named headings through it (or an equivalent).
- Test precedent for the idempotency invariant: `test_heading_count_invariant_across_n_calls` (`scripts/tests/test_fold_research_findings.py:185-192`) asserts heading count stays at 1 across N repeated calls while bullet content is allowed to repeat — the shape this bug's own idempotency tests should follow. Its Python analogue is `test_duplicate_session_log_headers_only_inserts_once` (`scripts/tests/test_session_log.py:238-251`).
- `commands/refine-issue.md` is an LLM-instruction file with no direct Python entry point; its own test conventions are prose-conformance assertions against known section slices (`scripts/tests/test_refine_issue_command.py`, e.g. `_preservation_rule_text()` sliced between two heading strings, then `assert phrase in text` checks) rather than executing the command. Tests for this bug's prose changes should follow that same slice-and-assert shape, in addition to the idempotency tests on the underlying Python fold logic.

## Program Design

### Types
N/A — no new data shape introduced; this is a control-flow fix to markdown emission logic.

### Signatures
- `find_subsections(content: str, parent_heading: str, sub_heading: str = SUB_HEADING) -> list[Span]` — `scripts/little_loops/issues/fold_research_findings.py:104` — returns every occurrence of a given `###` heading within a given `##` slice, in document order. Already parameterized by `sub_heading` for exactly this kind of reuse.
- `fold_research_findings(content: str, parent_heading: str, new_content: str, sub_heading: str = SUB_HEADING, marker: str = DEFAULT_MARKER) -> str` — `scripts/little_loops/issues/fold_research_findings.py:156` — the containment-check-and-collapse transform: 0 spans creates the heading once, 1 span appends beneath it, N>1 spans collapses into the first span's position before appending.
- `dated_marker(day: date | None = None) -> str` — supplies the `_Added by ... :_` provenance line; always generated by the module, never hand-assembled by a caller.
- `append_session_log_entry(issue_path, command, session_jsonl=None)` — `scripts/little_loops/session_log.py:307` — finds the last existing `## Session Log` heading and inserts beneath it rather than emitting a new one; the closest non-fold Python precedent for "check before emitting a heading."

### Call Path
Unrouted path that produces the duplication (what this bug reports):
`commands/refine-issue.md` § 5a "Enrichment Rules" template (`:399-431`, `:464-482`) -> direct `Edit` -> raw issue file — no containment check, no fold primitive involved.

Routed path that already exists and is idempotent, for comparison:
`commands/refine-issue.md` § "Writing Findings Blocks" -> `ll-issues fold-findings <ID> --section <H2>` -> `cmd_fold_findings()` (`scripts/little_loops/cli/issues/fold_findings.py:85`) -> `ensure_section()` -> `fold_research_findings()` (`scripts/little_loops/issues/fold_research_findings.py:156`, containment-checked via `find_subsections()`) -> `dated_marker()` -> `atomic_write()`.

### Decision Rules
- **Fix locus confirmed**: `### Call Path` and `### Dependent Files (Callers/Importers)` are emitted by direct `Edit` against the "Enrichment Rules" template, never through `ll-issues fold-findings`. `fold_research_findings.py`'s containment/fold logic is scoped to exactly one hardcoded sub-heading (`SUB_HEADING = "Codebase Research Findings"`); nothing in the codebase currently calls it with `sub_heading` overridden to either heading this bug names.
- **Reuse, not reimplementation**: `find_subsections()`/`fold_research_findings()` already accept `sub_heading` as a parameter specifically so other headings can reuse the same fold primitive — the module docstring names `/ll:wire-issue`'s `_Wiring pass added by …_` marker as the intended next caller. A separate, purely prose-level containment precedent already exists too: the `⚠ Superseded` idempotency rule at `commands/refine-issue.md:662-664` checks substring containment on a stable prefix rather than exact-text equality, for the same reason (a trailing variable clause).
- **Provenance-stub laziness gap is broader than hand-Edit**: `fold_research_findings()`'s internal `_batch()` helper concatenates the marker with `new_content` unconditionally at call time — it has no "only emit if `new_content` carries an actual bullet" gate. The empty-stub defect can therefore occur even through the routed `fold-findings` path, if invoked with a payload that is non-empty on `cmd_fold_findings`'s empty-stdin guard but content-free after folding. Lazy emission needs to gate at the call site (only invoke the write when there is at least one bullet), since `_batch()` does not perform this check today.
- **No dedup on the write path is by design, not a gap**: `fold_research_findings()` is documented and tested as NOT deduping bullet content across repeated calls (`test_heading_count_invariant_across_n_calls` — heading count stays at 1, but repeated bullet text is the expected contract). This bug's scope is heading-count and stub-emission idempotency, not bullet-content dedup.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/fold_research_findings.py:151-153` — `_batch()` gains the
  non-empty gate; `fold_research_findings()` drops no-op batches without emitting a marker or
  leaving blank-line churn. This is the enforcing change for the empty-stub half.
- `commands/refine-issue.md` — the emission rules: the containment check before the two hand-emitted
  headings (`:409`, `:474`), and the restated lazy-emission consequence of the existing
  fold-findings-only rule (`:588-592`).
- Generated host mirrors are regenerated, never hand-edited — `ll-adapt --host <gemini|qwen|kimi-code>
  --apply`. (See ENH-3238's Integration Map for why the "no DO NOT EDIT banner" test is not evidence
  of hand-authorship.)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:177-191` — `refine_followup`, the state that
  runs the additive `--gap-analysis` pass and therefore triggers this.
- `scripts/little_loops/issues/program_design.py` — the Program Design gate keys on `### Call Path`;
  a duplicated heading makes "which one is current" ambiguous to it and to any other consumer.

### Similar Patterns
- `commands/reconcile-issue.md` — holds the in-place-rewrite mandate and the precedent for how a
  narrow exception to the never-remove rule is authorized. This issue deliberately does not need one.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/wire-issue/SKILL.md` §8a (`:342-397`) already has the read-before-write containment shape
  this bug proposes adding to refine-issue (Phase 3 extracts `known_callers` from any existing
  heading before Phase 8 ever edits) — a working precedent to model the fix's wording after, not a
  file this bug needs to change. Its own provenance marker (`_Wiring pass added by ...:_`) has a
  narrower, lower-probability variant of the same empty-stub defect (no explicit per-category "skip
  stub if this category is empty" rule), out of scope here but worth a follow-up issue if it
  recurs. [Agent 1 + Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml:822-826,1879-1883` — two `run_refine_additive` states also
  invoke `/ll:refine-issue --gap-analysis`, an additional trigger site for this bug beyond
  `refine-to-ready-issue.yaml`'s `refine_followup`. [Agent 1 finding]
- `scripts/little_loops/loops/rn-remediate.yaml:674-679` — `patch_gaps` state, a third
  `--gap-analysis` trigger site in the iterative remediation sub-loop. [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_program_design_gate.py` — add a regression-safety test confirming
  `extract_call_path_anchors()` (`scripts/little_loops/issues/program_design.py:254-280`) still
  resolves anchors correctly when `### Call Path` appears twice in one `## Program Design` slice
  (today it unions both occurrences' text rather than breaking — confirmed by Agent 2 tracing
  `_subsection_body()` at `:198-209`); pin this as intentional so the fix doesn't need to touch that
  behavior. [Agent 2 finding]
- `scripts/tests/test_refine_issue_command.py` — new test class (e.g. `TestGapAnalysisEmissionIdempotency`)
  following the existing `_xxx_text()` slice-and-assert idiom (see `TestSupersededDirectiveMarker`,
  `:228-273`), sliced across `#### Enrichment Rules` (`:399`) through `#### Preservation Rule`
  (`:578`), asserting the new containment-check and lazy-stub prose is present. No existing test
  slices this block today. [Agent 3 finding]
- `scripts/tests/test_fold_research_findings.py` — if the fix routes `### Call Path` /
  `### Dependent Files (Callers/Importers)` through `fold_research_findings(sub_heading=...)` rather
  than staying prose-only, add a new test class parameterizing `sub_heading` to each of the two
  headings (mirrors `test_heading_count_invariant_across_n_calls`, `:185-192`, without editing it).
  Not needed if the fix stays prose-only. [Agent 3 finding]
- `scripts/tests/test_fold_research_findings.py` — **required by the step-1 gate** (not conditional
  on a routing decision, unlike the `sub_heading` parameterization noted above): N successive calls
  with a whitespace-only payload add zero markers and leave the content byte-identical; a mixed
  sequence (content → empty → content) yields exactly two markers with no adjacent pair. These
  assert the primitive can no longer represent a content-free stub.
- `scripts/tests/test_epic_consistency.py::TestEpicConsistencyIdempotency.test_fix_is_idempotent`
  (`:517-549`) — an additional byte-identical-after-second-run idempotency idiom precedent, alongside
  the two already cited. [Agent 3 finding]

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Gate `_batch()` on non-empty content and drop no-op batches in `fold_research_findings()`.
2. Add the empty-payload tests in `scripts/tests/test_fold_research_findings.py`; confirm they fail
   before step 1 and pass after.
3. Add the same-parent-section containment check before emitting `### Call Path` and
   `### Dependent Files (Callers/Importers)`, plus the restated lazy-emission rule, in
   `commands/refine-issue.md`.
4. Regenerate the three host mirrors with `ll-adapt --host <gemini|qwen|kimi-code> --apply`.
5. Add the prose-conformance and heading-idempotency tests.
6. `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Note that `autodev.yaml`'s `run_refine_additive` states (`:822-826`, `:1879-1883`) and
  `rn-remediate.yaml`'s `patch_gaps` state (`:674-679`) also trigger `--gap-analysis` — verify the
  fix is exercised by all four trigger sites, not just `refine-to-ready-issue.yaml`'s
  `refine_followup`.
- Add `TestGapAnalysisEmissionIdempotency` to `scripts/tests/test_refine_issue_command.py`, sliced
  over `#### Enrichment Rules` through `#### Preservation Rule`.
- Add a regression-safety test in `scripts/tests/test_program_design_gate.py` pinning that
  `extract_call_path_anchors()` unions duplicate `### Call Path` occurrences rather than breaking.

## Open Questions

- **Which of the two surviving explanations produced the observed stubs?** (See Root Cause §
  "Empty-stub half".) **Not a blocker** — the step-1 gate closes both, and implementation may proceed
  without an answer. Resolving it only tells us whether a *second*, separate follow-up is warranted
  (a rule-violating hand-`Edit` would be; a later pass stripping bullets would be).
  **Diagnostic**: the run's `events.jsonl`
  (`.loops/.history/2026-08-17T183652-refine-to-ready-issue/`) is a summarized narration stream and
  carries no tool-call payloads — it has one mention of `fold-findings` and zero of `_Added by`, so
  it cannot settle this. The decisive artifact is the refine session transcript jsonl: search it for
  an `Edit` tool call whose `new_string` contains `_Added by`. If one exists, explanation (1) holds.
  Note the pre-cleanup ENH-3238 file itself is unrecoverable — no committed revision carries the
  debris (see ENH-3247 § Tests).

## Related Issues

- ENH-3247 — owns cleanup of duplicate headings and empty stubs already in the backlog via
  `format-check --fix --apply`. Strict division: this issue stops creation, ENH-3247 removes what
  exists. Both are needed; neither blocks the other.
- ENH-3244 — proposes detecting the empty `_Added by_` stubs this bug produces as a structural gap.
- ENH-3238 — the issue whose refine run exhibited this.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- ENH-3244

## Status

**Done** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-17T21:33:47 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
- `/ll:confidence-check` - 2026-08-17T20:31:12 - `e97f4c03-b671-421e-ac95-ea56a86f3a4e.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:54 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:confidence-check` - 2026-08-17T20:10:26 - `37e075a7-49b8-44db-b567-e15852c40c0b.jsonl`
- `/ll:wire-issue` - 2026-08-17T19:59:57 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
- `/ll:refine-issue` - 2026-08-17T19:49:50 - `91301036-37cc-4bb2-8a07-a3ddf3c555b7.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:29:38 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:16:20 - `33a98a0f-5403-4525-92db-f7737c5401c4.jsonl`
