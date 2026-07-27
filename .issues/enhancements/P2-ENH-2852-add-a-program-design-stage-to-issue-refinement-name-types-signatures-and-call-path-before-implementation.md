---
id: 2852
title: Add a program-design stage to issue refinement naming types, signatures, and call path
type: ENH
priority: P2
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
---

# ENH-2852: Add a program-design stage to issue refinement naming types, signatures, and call path

Origin: ll-product #ENH-050

## Summary

The refinement chain (`/ll:refine-issue` → `/ll:wire-issue` → `/ll:confidence-check`) researches the codebase and identifies integration points, but never requires an issue to state the concrete **types, method signatures, and call path** the change will follow. That leaves the most rework-prone decisions to be made mid-implementation by `ll-auto` / `ll-parallel` / `ll-sprint`, where no human reviews the plan before code exists.

Add a program-design stage that makes an issue name its intended shape at the signature level before it is eligible for batch processing, and gate `/ll:confidence-check` on that section being present and specific.

## Motivation

Architecture-level refinement (which components, which files, which integration points) is already covered. Program design is the level below it and is the one currently skipped:

- What new or changed **types** does this introduce, and what are their fields?
- What are the **function/method signatures** being added or modified — names, parameters, return types?
- What is the **call path**: which caller reaches the new code, through what, and what does it do with the result?

An issue that answers these three questions has had its rework-prone decisions made under review. An issue that doesn't hands them to an agent mid-implementation, which is exactly where they are most expensive to get wrong and least visible when they are.

This is deliberately *not* a design doc stage. It is a short, concrete section — a handful of signatures and one call path — not prose about approach.

## Proposed Change

1. **Issue template** — add a `## Program Design` section with three required subsections: `Types`, `Signatures`, `Call Path`.
2. **Refinement** — extend the refinement chain to populate that section from codebase research: read the actual call sites and existing type definitions, then name the concrete shapes rather than describing them abstractly. A call-graph sketch (caller → callee → callee) is the expected form for `Call Path`.
3. **Gate** — `/ll:confidence-check` fails an issue whose `## Program Design` section is missing, empty, or non-specific (prose with no identifiers). Specificity check should be mechanical where possible: require at least one identifier that resolves against the repo, and at least one signature-shaped line.
4. **Batch eligibility** — `ll-auto` / `ll-parallel` / `ll-sprint` treat a failing confidence gate as they do today; no new blocking mechanism is needed if the gate is wired.

## Design Notes

- Keep the gate cheap and mostly deterministic. A grep/parse for identifiers that exist in the repo carries more signal than asking a model whether a section is "specific enough".
- **New identifiers cannot resolve against the repo by definition.** The repo-resolution requirement targets the *call-path anchors* — the existing callers, modules, and types the new code hooks into. The new names being introduced only need to be signature-*shaped* (parseable `name(params) -> ret` / dataclass-field lines), not resolvable. Conflating these would make the gate unpassable for any issue that adds code.
- **The mechanical check lives in a CLI, not in skill prose.** Implement it `ll-verify-*`-style (or as an `ll-issues format-check` extension) that `/ll:confidence-check` shells out to — matching the project's deterministic-CLI-plus-skill pattern and making it independently testable.
- Small mechanical issues (a one-line config change, a docs fix) should be able to satisfy the section trivially or declare it not applicable — the gate must not become a tax on trivial work. Provide an explicit escape hatch and make it visible in the issue rather than silent.
- **Amendment path, not a prohibition.** The section is written during refinement, but a hard "the implementing agent must not rewrite it" rule contradicts existing machinery (`/ll:reconcile-issue` rewrites directive sections by design) and ignores queue-latency staleness — a design fixed at refine time can be invalidated by codebase changes before implementation starts. Instead: the implementing agent may deviate, but the deviation is *recorded* in the issue (a `Deviations` note under the section stating what changed and why), never silently rewritten over the original.
- **Rollout for the existing backlog.** Every currently open issue lacks the section; a hard gate would mass-defer the backlog on day one. Grandfather issues refined before the gate ships (gate on `discovered_date`/refine timestamp), or bulk-populate via a one-off loop — pick one explicitly in the implementation, don't leave it to chance.

## Acceptance Criteria

- [ ] The issue template includes a `## Program Design` section with `Types`, `Signatures`, and `Call Path` subsections.
- [ ] The refinement chain populates that section with identifiers drawn from the actual codebase, not placeholders.
- [ ] `/ll:confidence-check` fails an issue with a missing or empty `## Program Design` section.
- [ ] `/ll:confidence-check` fails an issue whose section contains only prose with no repo-resolvable call-path anchors or signature-shaped lines.
- [ ] `/ll:confidence-check` passes an issue naming concrete types, signatures, and a call path — where repo-resolution is required only of call-path anchors, and new identifiers need only be signature-shaped.
- [ ] The specificity check is implemented as a deterministic CLI (`ll-verify-*` style or `ll-issues` subcommand) that the skill shells out to, testable without an LLM.
- [ ] An explicit not-applicable escape hatch exists for trivial issues and is recorded in the issue body when used.
- [ ] Implementation-time deviations from the design are recorded in the issue as a visible `Deviations` note rather than overwriting the original section.
- [ ] A rollout decision for pre-existing issues (grandfathering or bulk-populate) is implemented, so shipping the gate does not mass-defer the current backlog.
- [ ] Tests cover: missing section, prose-only section, valid section (including unresolvable-but-signature-shaped new identifiers), and the escape hatch.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): EPIC-2856 requires a one-off pre-intervention baseline sample of FEAT-2855's maintainability signals — captured manually under `thoughts/` — *before* this issue's gate ships, so "did any of this work" is answerable against a pre-intervention reference. FEAT-2855 is scheduled last in the EPIC and does not own producing that snapshot. Capturing it is a prerequisite of this issue, not part of FEAT-2855's scope.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-27T15:59:42 - `29cf17b6-04b4-4b01-9444-64f1bfdbdaa5.jsonl`
