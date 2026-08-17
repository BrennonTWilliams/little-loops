---
id: BUG-3245
type: BUG
title: refine-issue gap-analysis appends duplicate section headers and empty provenance
  stubs
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:14:11Z'
relates_to:
- ENH-3244
- ENH-3238
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
- **Effort**: Small - a containment check before each header emission, plus deferring the provenance
  stub until a bullet exists.
- **Risk**: Low - the change only suppresses emissions; it never deletes existing content, so it
  needs no widening of `refine-issue`'s deletion rights.
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

The empty-stub case is a second, simpler defect: the provenance stub is emitted eagerly (before the
pass knows whether it has findings) instead of lazily (on first bullet).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- The `### Call Path` / `### Dependent Files (Callers/Importers)` headings this bug names are emitted via direct `Edit` against the "Enrichment Rules" template block (`commands/refine-issue.md:399-431`, `:464-482`), never through `ll-issues fold-findings` — confirmed by tracing `fold_research_findings.py`'s containment logic, which is scoped to exactly one hardcoded sub-heading (`SUB_HEADING = "Codebase Research Findings"`) and is never invoked with `sub_heading` overridden for either heading this bug names.
- The provenance-stub emptiness defect is not fully explained by the hand-`Edit` path: `fold_research_findings()`'s internal `_batch()` helper (`scripts/little_loops/issues/fold_research_findings.py`) concatenates the marker with `new_content` unconditionally, with no check that `new_content` carries an actual bullet — an empty-looking stub can occur even through the routed `fold-findings` path if the payload is non-empty on `cmd_fold_findings`'s empty-stdin guard but content-free after folding.
- Existing containment-check precedent for markdown emission at the prose level (non-Python): the `⚠ Superseded` idempotency rule at `commands/refine-issue.md:662-664` — "skip the insertion if the line immediately below already contains the substring `⚠ Superseded`" — uses substring containment on a stable prefix, not exact-text equality, for the same reason (a trailing variable clause). The Python precedent for "find existing heading, insert beneath the last one instead of creating a new one" is `append_session_log_entry()` (`scripts/little_loops/session_log.py:307-324`), which `fold_research_findings.py`'s own module docstring names as its precedent.

## Proposed Solution

1. **Lazy provenance stub.** Emit `_Added by \`/ll:refine-issue\` — <date> — based on codebase
   analysis:_` only immediately before the first finding bullet the pass actually writes. No
   findings → no stub.
2. **Containment check before heading emission.** Before writing `### Call Path` or
   `### Dependent Files (Callers/Importers)`, check whether that heading already exists **within the
   same parent section**; if so, append under it rather than emitting a sibling.
3. Do **not** add a deletion right. Existing duplicates already in the backlog are cleaned by
   `/ll:reconcile-issue` (which holds an in-place rewrite mandate over `### Files to Modify` and the
   directive sections) or by hand — out of scope here.

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
- `commands/refine-issue.md` — the emission rules for the provenance stub and the two headings.
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
- `scripts/tests/test_epic_consistency.py::TestEpicConsistencyIdempotency.test_fix_is_idempotent`
  (`:517-549`) — an additional byte-identical-after-second-run idempotency idiom precedent, alongside
  the two already cited. [Agent 3 finding]

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Make the provenance stub lazy (emit on first bullet, not before the pass).
2. Add the same-parent-section containment check before emitting `### Call Path` and
   `### Dependent Files (Callers/Importers)`.
3. Regenerate the three host mirrors with `ll-adapt`.
4. Add the idempotency and empty-stub tests.
5. `python -m pytest scripts/tests/` exits 0.

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

## Related Issues

- ENH-3244 — proposes detecting the empty `_Added by_` stubs this bug produces as a structural gap.
- ENH-3238 — the issue whose refine run exhibited this.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-08-17T19:59:57 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
- `/ll:refine-issue` - 2026-08-17T19:49:50 - `91301036-37cc-4bb2-8a07-a3ddf3c555b7.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:29:38 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:16:20 - `33a98a0f-5403-4525-92db-f7737c5401c4.jsonl`
