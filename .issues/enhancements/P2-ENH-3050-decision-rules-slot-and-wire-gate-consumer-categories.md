---
id: ENH-3050
title: Program Design gains a Decision Rules slot; wire gains gate-consumer and conditional-branch
  categories
type: ENH
priority: P3
status: open
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: '2026-08-04T22:10:00Z'
relates_to:
- ENH-3045
- ENH-3046
- ENH-3049
- FEAT-2942
labels:
- skills
- issues
- quality
testable: true
blocked_by:
- ENH-3047
---

# ENH-3050: Decision Rules slot + wire gate-consumer and conditional-branch categories

## Summary

Two narrow, unrelated-looking gaps with the same cause — the refine/wire templates have slots
shaped for *existing code that is certain*, and none for *new logic* or *conditional branches*:

1. **No slot for specifying new logic.** `## Program Design` emits Types / Signatures /
   Call Path, all of which describe code that already exists. An issue introducing a brand-new
   predicate or heuristic has nowhere to pin down its keyword list, thresholds, or escape hatch,
   so it passes every gate unspecified.
2. **Wire wires named files, not gate consumers or conditional branches.** An issue adding a new
   gap kind to `format-check` never gets `autodev.yaml` wired, even though autodev reads
   `format-check --format json` in a routing gate. An issue whose plan says "extract to a
   companion *if* it overflows" never gets the companion's mirror coverage checked.

Neither is covered by `ENH-3046` (detects intra-issue contradictions), `FEAT-3048` (verifies
symbol/flag claims against the codebase), or `ENH-3047` (feeds gap counts into scoring).

## Current Behavior

**Slot gap.** `commands/refine-issue.md:378-390` defines the Program Design template as exactly
three subsections — `### Types`, `### Signatures`, `### Call Path`. The
`program_design_nonspecific` gap kind and confidence-check's Phase 1.6 pre-fetch both check that
these carry signature-shaped lines with *resolving anchors* — i.e. that cited symbols exist.
Nothing checks that a **newly proposed** decision rule is specified at all.

Live example — `ENH-3045` proposes a `missing_behavior_parity` detection rule described only as
"`classify_issue_refs()` to find `resolved` file refs near rewrite/delete/delegate keywords."
No keyword list, no definition of "near", no scope limit, no escape hatch. It passed refine,
wire, and confidence-check (100/82). `format-check` returns 1 on any gap
(`cli/issues/format_check.py` `cmd_format_check` docstring) and `autodev.yaml:1538` reads its
JSON in a routing gate, so an under-specified fuzzy predicate here mis-routes real issues.

**Wiring gap.** `skills/wire-issue/SKILL.md:250-270` enumerates the `MISSING_WIRING` categories:
callers, importers, tests, registrations, docs, `cli_coupling`, `schema_coupling`,
`new_impl_steps`. All are "files that reference the thing being changed." Two shapes fall
outside every category:

- **Gate consumers.** A new `FormatGaps` field is read by `autodev.yaml` and `rn-remediate.yaml`
  through `ll-issues format-check --format json`, not by importing `issue_parser`. No grep for a
  symbol finds them; the coupling is through a CLI's JSON contract.
- **Conditional escape hatches.** `ENH-3045:109-111` says to extract to a companion file "if the
  addition overflows" the 500-line cap. Wire found and documented the host-mirror test for
  `SKILL.md` but never checked the conditional branch — where the mirrors carry `SKILL.md` only
  (`skills/wire-issue/prose-dependency-gate.md` has no `.gemini`/`.kimi-code` counterpart), so
  the fallback silently drops behavior on two hosts with no test to catch it.

## Expected Behavior

**A `### Decision Rules` subsection** under `## Program Design`, emitted by `/ll:refine-issue`
when the issue introduces a new predicate, gate, heuristic, or classification rule. Required
content per rule: exact inputs, the literal keyword/threshold values, the proximity or scoping
rule, and the dismissal/escape hatch that satisfies the gate without doing the work.

**Two new wire categories** in Phase 5's `MISSING_WIRING`:

- `gate_consumers` — when the change adds or alters a field in a CLI's JSON output or its exit
  code, trace who reads that output (loop YAMLs, hooks, skills), not just who imports the module.
- `conditional_branches` — when the plan states a conditional fallback ("if X overflows, do Y"),
  wire Y's touchpoints as first-class, since the branch is invisible to a file-reference diff.

## Motivation

Both gaps produce defects that survive all three passes and surface only during implementation
or, worse, in production routing. They are also cheap: one template subsection and two entries
in an existing enumeration. `ENH-3049` makes passes able to *retract* a claim; this issue
reduces the number of under-specified claims that get made.

## Proposed Solution

Keep both halves prose-only and bounded — no new Python, no new gap kind.

- Add `### Decision Rules` to the refine Program Design template with a trigger condition
  ("emit only when the issue proposes new decision logic"), so it does not appear on issues that
  merely modify existing code.
- Add the two categories to wire's Phase 5 list and one sentence each to the Agent 2
  (side-effect tracer) and Agent 1 (caller tracer) briefs.
- Optionally extend `skills/confidence-check/rubric.md` Criterion 4 with a deduction for an
  issue that proposes a new gate with no `### Decision Rules` section. Kept optional here
  deliberately — `ENH-3047` owns the rubric-deduction surface and should absorb it if it lands
  first.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — Program Design template (`:378-390`) and the Step 5a emission
  path; 987 lines today, no line cap on commands
- `skills/wire-issue/SKILL.md` — Phase 5 categories (`:250-270`), Agent 1 brief (`:145-182`),
  Agent 2 brief (`:184-214`); 455/500 lines — watch the cap alongside `ENH-3049`, which also
  adds to this file
- `docs/reference/COMMANDS.md` — wiring-categories bullet list for `/ll:wire-issue`
- `scripts/tests/test_wiring_skills_and_commands.py` — `DOC_STRINGS_PRESENT` entries for both

### Dependent Files (Callers/Importers)
- `scripts/tests/test_wiring_skills_and_commands.py::test_wire_issue_skill_mirror_matches_source`
  (`:336-346`) — same mirror-regeneration requirement as `ENH-3049`; if both land, sequence them
  so `ll-adapt --host gemini --apply && ll-adapt --host kimi --apply` runs once at the end
- `skills/confidence-check/rubric.md` — only if the optional Criterion 4 deduction is included

### Similar Patterns
- `ENH-2852` — the `program_design_nonspecific` gate this extends conceptually
- `ENH-494` — the companion-file pattern whose mirror gap this issue's second half exposes

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- **Template subsection convention** — new Program Design/Integration Map subsections (e.g. `### Behavior Parity` from ENH-3045) are added as a bare, exact `### Heading` line matched by `_heading_bodies()`'s anchored regex (`scripts/little_loops/issue_parser.py:677`); the emission trigger ("emit only when X") is stated as prose immediately below the heading in `commands/refine-issue.md`, not enforced by a dedicated gap function unless the issue explicitly adds one. `### Decision Rules` should follow this same shape rather than inventing new marker syntax.
- **Content always via fold-findings** — every example subsection added by a prior issue (Behavior Parity, Decision-Point Formatting options) is deposited through `ll-issues fold-findings [ID] --section "..."`, never hand-written; ENH-3050's own Call Path section already states this route applies to its `### Decision Rules` addition.
- **`MISSING_WIRING` category shape and Phase 8a emission gap** — existing categories (`skills/wire-issue/SKILL.md:265-274`) share a uniform `name: [source-agent, file-kind, exclusion clause]` shape, but Phase 8a (`:338-407`) does not give every category a dedicated output heading: `cli_coupling` folds into the existing "Documentation" example block (`:359-367`) and `schema_coupling` folds into "Configuration" (`:386-394`), while only `callers/importers`, `registrations`, `tests`, and `docs` get dedicated blocks, and `new_impl_steps` gets its own new `### Wiring Phase (added by /ll:wire-issue)` heading appended to `## Implementation Steps` (`:396-407`) with an explicit "do not continue parent numbering" rule. This issue's Implementation Steps do not yet say whether `gate_consumers`/`conditional_branches` get dedicated Phase 8a blocks or fold into an existing subsection (e.g. "Dependent Files") — that choice is currently unspecified.
- **`DOC_STRINGS_PRESENT` pattern** — prior additions pair each new string with a `(file, needle, issue_id)` tuple, comment-grouped by issue: `("skills/wire-issue/SKILL.md", "### Behavior Parity", "ENH-3045")`, `("commands/refine-issue.md", "### Behavior Parity", "ENH-3045")` (`scripts/tests/test_wiring_skills_and_commands.py:229-232`); ENH-3049 follows the same shape with multiple needles per file (`:210-225`).
- **Wire-issue mirror gate already exists and will fail on this edit** — `scripts/tests/test_wiring_skills_and_commands.py:351-371` (ENH-2996) asserts `skills/wire-issue/SKILL.md` is byte-identical (post-frontmatter) to `.gemini/skills/wire-issue/SKILL.md` and `.kimi-code/skills/wire-issue/SKILL.md`, failing with the exact remediation `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply`. Any edit to `SKILL.md` here trips this test until mirrors are regenerated — consistent with Implementation Step 4.
- **Multi-issue sequencing is convention only, not tooling-enforced** — the note to sequence ENH-3049 and ENH-3050's edits to `skills/wire-issue/SKILL.md` before one final mirror regeneration is documented in issue prose (this issue's own Integration Map), not enforced by any script or test.

## Program Design

### Types
_No new types — both halves are prose additions to markdown artifacts._

### Signatures
- `check_format_gaps(issue_path, templates_dir=None, issue_statuses=None, ref_index=None)
  -> FormatGaps` — `scripts/little_loops/issue_parser.py:342-347`. **Unchanged.** Named here to
  record that the `### Decision Rules` section is deliberately *not* gated mechanically in this
  issue; `program_design_nonspecific` continues to check only anchor resolution.
- `_heading_bodies(content: str, heading: str) -> list[str]` — `issue_parser.py:677-693`.
  If a future issue does gate on this section, note the regex is
  `^(#{2,3})\s+{re.escape(heading)}\s*$` — anchored, exact match, no suffix. The section must be
  emitted as a bare `### Decision Rules` heading for that to ever work.

### Decision Rules

_Self-applying this issue's own proposal:_

- **When refine emits `### Decision Rules`** — trigger when the issue's Proposed Solution or
  Expected Behavior introduces any of: a new gap kind, a new gate or exit-code condition, a
  keyword/phrase list, a numeric threshold, or a classification rule. Do not emit for issues that
  only modify existing logic. Escape hatch: a `### Decision Rules` section whose body is
  `N/A — no new decision logic` satisfies the requirement.
- **When wire emits `gate_consumers`** — trigger when the change adds or alters a field in any
  CLI's `--format json` output, or changes a CLI's exit-code condition. Search scope: loop YAMLs
  under `scripts/little_loops/loops/`, `hooks/`, and skill/command markdown, grepping the CLI
  invocation string rather than the Python symbol.
- **When wire emits `conditional_branches`** — trigger on conditional language in the
  Proposed Solution naming an alternate implementation target ("if … overflows", "if … exceeds",
  "otherwise extract to", "fall back to"). Wire the named alternate target's touchpoints.

### Call Path
- **refine**: Step 3 research (`commands/refine-issue.md:156-281`) → Step 4 gap identification
  (`:282-329`) gains "new decision logic present but unspecified" as a gap class → Step 5a
  emission (`:330-341`) writes the new subsection under `## Program Design` via
  `ll-issues fold-findings [ID] --section "Program Design"`, the same append-only,
  `--dry-run`-aware route used for the existing three subsections.
- **wire**: Phase 4 Agent 1/2 briefs (`skills/wire-issue/SKILL.md:145-214`) gain the two search
  instructions → the Phase 5 `MISSING_WIRING` block (`skills/wire-issue/SKILL.md:250-270`) gains
  two keys → Phase 8a (`skills/wire-issue/SKILL.md:330-380`) emits them into the existing
  `### Dependent Files (Callers/Importers)` subsection rather than a new heading, so
  `_heading_bodies` (`scripts/little_loops/issue_parser.py:677`) gains no new consumer and
  `check_format_gaps` (`scripts/little_loops/issue_parser.py:342`) is untouched.
- **gate-consumer search target**: the coupling being traced is a CLI JSON contract, so the
  search is for the invocation string — `ll-issues format-check` in
  `scripts/little_loops/loops/autodev.yaml:1538` and `scripts/little_loops/loops/rn-remediate.yaml`
  — not for an importer of `scripts/little_loops/cli/issues/format_check.py`.

## Implementation Steps

1. Add `### Decision Rules` to refine's Program Design template with its trigger and escape hatch.
2. Add the gap class to refine Step 4 so the section is emitted when warranted.
3. Add `gate_consumers` and `conditional_branches` to wire Phase 5 plus the two agent briefs.
4. Regenerate host mirrors after editing `skills/wire-issue/SKILL.md`.
5. `DOC_STRINGS_PRESENT` entries for both artifacts.
6. Validate against `ENH-3045`: a refine pass emits `### Decision Rules` specifying the
   `missing_behavior_parity` keyword list and escape hatch, and a wire pass surfaces
   `autodev.yaml` as a gate consumer and the companion-mirror gap as a conditional branch.

## Impact

- **Priority**: P3 — preventive rather than corrective; smaller blast radius than ENH-3049
- **Effort**: Low — prose additions to two artifacts, no Python
- **Risk**: Low — additive; worst case is a `N/A` Decision Rules section on issues that don't
  need one

## Scope Boundaries

- **No new gap kind and no Python change.** `### Decision Rules` is deliberately advisory here.
  Gating it mechanically is a separate decision, and `program_design_nonspecific` keeps checking
  only anchor resolution.
- **Rubric deductions belong to `ENH-3047`.** The optional Criterion 4 deduction is listed only
  so it is not lost; if 3047 lands first it should absorb it rather than both issues editing
  `skills/confidence-check/rubric.md`.
- **Not a general "wire everything conditional" mandate.** `conditional_branches` triggers only
  on conditional language naming an alternate *implementation target*, not on ordinary hedging.

## Related Key Documentation

- `docs/reference/COMMANDS.md` — `/ll:wire-issue` wiring categories
- `.claude/CLAUDE.md` § Automation — the `format-check` JSON contract that gate consumers read

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-05T02:40:05 - `01b1f21d-ee5c-46e4-9926-f894d6a85704.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-05T00:25:09 - `2f3f7bc8-367e-4fba-936b-eaf8049da3c4.jsonl`
