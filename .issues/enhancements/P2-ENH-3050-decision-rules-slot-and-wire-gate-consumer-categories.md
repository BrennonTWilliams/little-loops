---
id: ENH-3050
title: Program Design gains a Decision Rules slot; wire gains gate-consumer and conditional-branch
  categories
type: ENH
priority: P2
status: open
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: '2026-08-04T22:10:00Z'
relates_to:
- ENH-3045
- ENH-3046
- ENH-3049
- FEAT-2942
- ENH-3047
labels:
- skills
- issues
- quality
testable: true
blocked_by: []
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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

**Slot gap.** `commands/refine-issue.md:405-415` defines the Program Design template as exactly
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

**Wiring gap.** `skills/wire-issue/SKILL.md:265-274` enumerates the `MISSING_WIRING` categories:
callers, importers, tests, registrations, docs, `cli_coupling`, `schema_coupling`,
`new_impl_steps`. All are "files that reference the thing being changed." Two shapes fall
outside every category:

- **Gate consumers.** A new `FormatGaps` field is read through `ll-issues format-check
  --format json`, not by importing `issue_parser`. No grep for a symbol finds them; the coupling
  is through a CLI's JSON contract. The surface is wider than the two loop YAMLs usually cited:
  a grep for `format-check` across `scripts/little_loops/loops/`, `hooks/`, `skills/`,
  `commands/`, and `docs/` returns **15** files — two loop YAMLs (`autodev.yaml`,
  `rn-remediate.yaml`), six skill/command markdown consumers (`skills/confidence-check/SKILL.md`,
  `skills/decide-issue/SKILL.md`, `skills/format-issue/SKILL.md`,
  `skills/wire-issue/prose-dependency-gate.md`, `commands/reconcile-issue.md`,
  `commands/ready-issue.md`, `commands/refine-issue.md`), and the rest documentation. A
  symbol-based wiring pass surfaces none of them.
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
- ~~Optionally extend `skills/confidence-check/rubric.md` Criterion 4 with a deduction for an
  issue that proposes a new gate with no `### Decision Rules` section.~~ **Dropped 2026-08-05.**
  `ENH-3047` has landed (`48b881a2`) and Criterion 4's cap is now gap-driven: Phase 1.8 sets
  `PARITY_GAP`/`CLAIM_GAP` from the `missing_behavior_parity`, `stale_symbol_ref`, and
  `stale_cli_flag` gap kinds (`skills/confidence-check/rubric.md:246-251`). A "proposes a new
  gate with no `### Decision Rules`" deduction has no gap kind to fire on, and this issue's
  Scope Boundaries forbid adding one — so the rubric edit is unimplementable as scoped, not
  merely optional. Gating the section is a follow-up issue (new gap kind → Phase 1.8 wiring →
  rubric row), not a bullet here.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — Program Design template (`:405-415`), the three knowledge-gap
  tables (`:300`, `:310`, `:320` — BUG/FEAT/ENH), and the Step 5a emission path; **1041 lines**
  today, no line cap on commands
- `skills/wire-issue/SKILL.md` — Phase 5 `MISSING_WIRING` block (`:265-274`), Agent 1 brief
  (`:151-185`), Agent 2 brief (`:186-214`); **489/500 lines** — 11 lines of headroom, see the
  budget rule in Implementation Step 3
- `docs/reference/COMMANDS.md` — wiring-categories bullet list for `/ll:wire-issue`
- `scripts/tests/test_wiring_skills_and_commands.py` — `DOC_STRINGS_PRESENT` entries (exact
  needles listed in Implementation Step 5)

_All line anchors in this section re-verified 2026-08-05. The previously recorded values
(`refine-issue.md:378-390`, `987` lines; `SKILL.md:250-270`, `455/500`) were stale — `ENH-3049`
and `ENH-3045` both grew these files after this issue's first refine pass._

### Dependent Files (Callers/Importers)
- `scripts/tests/test_wiring_skills_and_commands.py::test_wire_issue_skill_mirror_matches_source`
  (`:351-372`) — trips on any `SKILL.md` edit until mirrors are regenerated. `ENH-3049` is now
  `done` and the three copies are in sync, so the earlier "sequence both issues before one
  regeneration" note no longer applies: this issue runs the regeneration itself, once, as
  Implementation Step 4. The remediation string the test prints is
  `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply` — note `kimi-code`,
  not `kimi`
- ~~`skills/confidence-check/rubric.md`~~ — no longer touched; see the dropped bullet under
  **Proposed Solution**

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_issue_command.py::TestProgramDesignGapTaxonomy::test_all_three_gap_tables_name_types_signatures_call_path`
  (`:390-396`) — asserts `text.count("Types/signatures/call path") == 3` scoped to
  `commands/refine-issue.md`'s BUG/FEAT/ENH gap tables; the new "new decision logic present but
  unspecified" gap row (Implementation Step 2) must not reuse this literal string or the count
  assertion breaks [Agent 3 finding]
- `scripts/tests/test_refine_issue_command.py::TestProgramDesignEnrichmentRule::test_program_design_enrichment_block_present`
  (`:408-415`) — presence-only check for `### Types`/`### Signatures`/`### Call Path` between the
  Step 5a and 5b headings; adding `### Decision Rules` in that range won't break the assertion,
  but its own message text ("the template's three subheadings") goes stale [Agent 3 finding]
- `scripts/tests/test_enh494_skill_companions.py::TestSkillLineLimit::test_all_skills_within_limit`
  (`:74-84`) — `skills/wire-issue/SKILL.md` is **489/500** lines as of 2026-08-05 (re-counted;
  the `455/500` and `490/500` figures previously recorded in this issue were both wrong). That
  leaves **11 lines** of headroom before the cap breaks and the ENH-494 companion-extraction
  remedy is required — a budget this issue's edit must fit inside, not discover at the end.
  See Implementation Step 3 for the pre-committed budget [Agent 2 finding, re-verified]
- `.gemini/commands/refine-issue.toml` — embeds `commands/refine-issue.md`'s full body verbatim in
  its `prompt` field, but unlike `skills/wire-issue/SKILL.md` there is no committed drift test
  comparing them; the `### Decision Rules` addition can go stale in this mirror silently
  [Agent 2 finding]

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

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- **`MISSING_WIRING` category shape has a split convention, not a uniform one** (`skills/wire-issue/SKILL.md:265-275`): five categories (`callers_to_add`, `importers_to_add`, `tests_to_add`, `registrations_to_add`, `docs_to_add`) carry an explicit exclusion clause ("not in known_X" / "not in files_to_modify"); four (`cli_coupling`, `schema_coupling`, `tests_to_update`, `new_impl_steps`) do not. **Resolved**: `gate_consumers`/`conditional_branches` omit an exclusion clause, matching their nearest analogs `cli_coupling`/`schema_coupling` rather than the majority pattern. The exclusion clause exists to avoid re-listing hits already caught by a symbol/import search (already in `known_callers`, `files_to_modify`); these two categories search a different way entirely — grepping CLI invocation strings and conditional-language phrases — with no natural "already known" set to exclude against.
- **Phase 8a fold-vs-dedicated-heading split confirmed by direct inspection**: `cli_coupling` has no dedicated Phase 8a heading of its own (closest existing match is `### Documentation`, since CLI-coupling findings are command/doc files); `schema_coupling` folds explicitly into `### Configuration` (`skills/wire-issue/SKILL.md:386-394`); `new_impl_steps` is the only category with its own dedicated heading, `### Wiring Phase (added by /ll:wire-issue)` under `## Implementation Steps` (`SKILL.md:396-412`), with an explicit "do not continue parent numbering" rule. This matches what this issue's Call Path section already states (Phase 8a folds the two new categories into the existing `### Dependent Files (Callers/Importers)` subsection) — confirmed consistent with current SKILL.md structure, no correction needed.
- **Host mirror test currently passing, not stale**: `test_wire_issue_skill_mirror_matches_source` (`scripts/tests/test_wiring_skills_and_commands.py:351-372`) compares `skills/wire-issue/SKILL.md` against `.gemini/skills/wire-issue/SKILL.md` and `.kimi-code/skills/wire-issue/SKILL.md` post-frontmatter — as of this research pass the three are in sync, so Implementation Step 4 (regenerate mirrors) is a forward-looking requirement of *this* issue's own edit, not a pre-existing failure to fix first.
- **No drift test exists anywhere for `.gemini/commands/*.toml` mirrors** (re-confirmed): a repo-wide search for a test comparing any `commands/*.md` body against its `.gemini/commands/*.toml` counterpart found none. The only structurally similar precedent is `test_wire_issue_skill_mirror_matches_source` itself (ENH-2996), which is scoped to `skills/wire-issue/SKILL.md` only and does not generalize to command/TOML mirrors — there is no existing harness this issue's manual-sync step could plug into.

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

  _Why an escape hatch for an ungated section:_ nothing enforces it today (see Scope
  Boundaries), so the literal is a convention, not a check. It is specified now so that a
  future gate is a one-line `_heading_bodies("Decision Rules")` presence test plus a
  string comparison — rather than a retrofit that has to reconcile whatever ad-hoc
  "not applicable" phrasings accumulated in the interim. Same reasoning as
  `program_design_not_applicable`, minus the frontmatter flag.
- **When wire emits `gate_consumers`** — trigger when the change adds or alters a field in any
  CLI's `--format json` output, or changes a CLI's exit-code condition. Search scope: loop YAMLs
  under `scripts/little_loops/loops/`, `hooks/`, `skills/`, `commands/`, and `docs/`, grepping
  the CLI invocation string rather than the Python symbol. Scope calibration: `format-check`
  alone has 15 such consumers (see Current Behavior), of which only 2 are loop YAMLs — a search
  restricted to `loops/` misses the majority.
- **When wire emits `conditional_branches`** — trigger on conditional language in the
  Proposed Solution naming an alternate implementation target ("if … overflows", "if … exceeds",
  "otherwise extract to", "fall back to"). Wire the named alternate target's touchpoints.

### Call Path
- **refine**: Step 3 research (`commands/refine-issue.md:156-281`) → Step 4 knowledge-gap
  identification (`:284-329`) gains "new decision logic present but unspecified" as a **prose
  gap row** in each of the three per-type tables (`:300` BUG, `:310` FEAT, `:320` ENH) → Step 5a
  emission (`:332-341`) writes the new subsection under `## Program Design` via
  `ll-issues fold-findings [ID] --section "Program Design"`, the same append-only,
  `--dry-run`-aware route used for the existing three subsections.
- **wire**: Phase 4 Agent 1/2 briefs (`skills/wire-issue/SKILL.md:151-214`) gain the two search
  instructions → the Phase 5 `MISSING_WIRING` block (`skills/wire-issue/SKILL.md:265-274`) gains
  two keys → Phase 8a (`skills/wire-issue/SKILL.md:338-395`, heading `### 8a: Integration Map
  Updates`) emits them into the existing
  `### Dependent Files (Callers/Importers)` subsection rather than a new heading, so
  `_heading_bodies` (`scripts/little_loops/issue_parser.py:677`) gains no new consumer and
  `check_format_gaps` (`scripts/little_loops/issue_parser.py:342`) is untouched.
- **gate-consumer search target**: the coupling being traced is a CLI JSON contract, so the
  search is for the invocation string — `ll-issues format-check` in
  `scripts/little_loops/loops/autodev.yaml:1538` and `scripts/little_loops/loops/rn-remediate.yaml`
  — not for an importer of `scripts/little_loops/cli/issues/format_check.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- **Anchor drift since last refine (2026-08-05T02:40:05)**: `check_format_gaps()` has moved to `scripts/little_loops/issue_parser.py:359-366` (was cited above as `342-347`) — the shift is caused by an unrelated `QuestionGaps` dataclass (ENH-2446) now occupying `issue_parser.py:336-357`. `_heading_bodies()` has moved to `issue_parser.py:911-927` (was cited above as `677-693`); its regex is unchanged (`^(#{2,3})\s+{re.escape(heading)}\s*$`, `issue_parser.py:921`), still matching both `##` and `###` levels — the "must be a bare `### Decision Rules` heading" requirement above still holds, only the line numbers need correction at implementation time.
- **`DESIGN_SUBSECTIONS` inertness re-confirmed**: `scripts/little_loops/issues/program_design.py:64` is unchanged — still `("types", "signatures", "call path")`. `_evidence_body()` (`program_design.py:196-214`) walks `## Program Design` by subsection heading and drops any body whose normalized heading isn't in that tuple, exactly as the existing `Deviations` subsection (ENH-2871) is already dropped. A `### Decision Rules` subsection would be architecturally identical — invisible to `parse_signature_lines()` and `extract_call_path_anchors()`, confirming this issue's "deliberately advisory, not gated" design holds against current code.
- **`autodev.yaml:1538` citation re-confirmed accurate** — the `ll-issues format-check --format json` invocation this issue cites as the gate-consumer example is still at that exact line, inside `check_reconcile_needed`'s action block, feeding a `markers` count (from `superseded_marker_count`) into a three-term routing predicate (ENH-2992).
- **`format_check.py` exit-code contract unchanged, gap taxonomy grew**: `cmd_format_check` still returns 1 on any `FormatGaps`/`has_gaps` condition across all modes (single-issue text/JSON, `--all` sweep, not-found). Since this issue's last refine, the file added `stale_symbol_ref`/`stale_cli_flag` gap classes (FEAT-3048) and now builds a shared `cli_index`/`ref_index` once per invocation (ENH-2983) — additive metadata, no change to the exit-code contract this issue's Current Behavior section describes.

## Implementation Steps

1. Add `### Decision Rules` to refine's Program Design template
   (`commands/refine-issue.md:405-415`) with its trigger and escape hatch, following the
   `### Behavior Parity` shape — bare heading, trigger stated as prose immediately below.
2. Add a **prose gap row** to refine's Step 4 knowledge-gap tables so the section is emitted when
   warranted. This is **three rows, not one** — the tables are per-type and duplicated at
   `:300` (BUG), `:310` (FEAT), `:320` (ENH). The row must **not** reuse the literal string
   `"Types/signatures/call path"`, which `test_all_three_gap_tables_name_types_signatures_call_path`
   asserts appears exactly three times. Terminology note: "gap row" here means a row in refine's
   prose research table — **not** a `FormatGaps` gap kind, which Scope Boundaries excludes.
3. Add `gate_consumers` and `conditional_branches` to wire Phase 5 (`SKILL.md:265-274`) plus one
   sentence each to the Agent 1 and Agent 2 briefs. Neither category carries an exclusion
   clause — see Codebase Research Findings for why.
   **Line budget (pre-committed, not discovered at the end):** `SKILL.md` is 489/500. The edit
   gets **≤8 lines**: 2 for the `MISSING_WIRING` keys (one line each, matching the existing
   one-line-per-key block shape) and ≤3 per agent brief. If the change cannot fit in 8 lines,
   extract the two category *definitions* into a 4th companion file per the ENH-494 pattern
   (`learning-targets.md`, `static-coupling-layer.md`, `graph-discovery-layer.md`) — do not
   trim existing Phase 5 or agent-brief prose to make room.
4. Regenerate host mirrors after editing `skills/wire-issue/SKILL.md`:
   `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply` (single run; `ENH-3049`
   is already landed and merged, so no cross-issue sequencing is needed).
5. Add `DOC_STRINGS_PRESENT` entries to `scripts/tests/test_wiring_skills_and_commands.py`,
   comment-grouped by issue per the ENH-3045/ENH-3049 convention, with these exact needles:
   - `("commands/refine-issue.md", "### Decision Rules", "ENH-3050")`
   - `("skills/wire-issue/SKILL.md", "gate_consumers", "ENH-3050")`
   - `("skills/wire-issue/SKILL.md", "conditional_branches", "ENH-3050")`
   - `("docs/reference/COMMANDS.md", "gate_consumers", "ENH-3050")`

   If Step 3 takes the companion-file branch, the two `SKILL.md` needles move to that
   companion's path instead.
6. Manually sync `.gemini/commands/refine-issue.toml`'s embedded `prompt` body (no drift test
   covers command/TOML mirrors — see Codebase Research Findings).
7. Validate against `ENH-3045`: a refine pass emits `### Decision Rules` specifying the
   `missing_behavior_parity` keyword list and escape hatch, and a wire pass surfaces
   `autodev.yaml` as a gate consumer and the companion-mirror gap as a conditional branch.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Verify `scripts/tests/test_refine_issue_command.py::test_all_three_gap_tables_name_types_signatures_call_path`
  still passes after Step 2's three new gap rows — folded into Implementation Step 2
- Line-cap budget for `skills/wire-issue/SKILL.md` (489/500, 11 lines of headroom) — folded into
  Implementation Step 3
- `.gemini/commands/refine-issue.toml` manual sync — folded into Implementation Step 6
- Optional new test in `scripts/tests/test_program_design_gate.py`, mirroring the existing
  `test_deviations_subsection_is_inert` (`:304-332`), locking in that `### Decision Rules` falls
  through `DESIGN_SUBSECTIONS` (`program_design.py:64`) as inert grading evidence. _Suggested
  name only — do not treat as an existing symbol; naming it as a bare identifier previously
  tripped `format-check`'s `stale_symbol_ref` claim check (FEAT-3048), which made this issue
  exit 1 against its own gate._

## Acceptance Criteria

1. `commands/refine-issue.md` contains a bare `### Decision Rules` heading inside the
   `## Program Design` template block (between the Step 5a and 5b headings), with its trigger
   condition and the literal escape-hatch string `N/A — no new decision logic` stated as prose
   immediately below it.
2. All three of refine's per-type knowledge-gap tables (BUG, FEAT, ENH) carry a row for
   unspecified new decision logic, and
   `test_all_three_gap_tables_name_types_signatures_call_path` still passes.
3. `skills/wire-issue/SKILL.md`'s Phase 5 `MISSING_WIRING` block contains `gate_consumers` and
   `conditional_branches` keys, neither carrying an exclusion clause, and Phase 8a routes both
   into the existing `### Dependent Files (Callers/Importers)` subsection with no new heading.
4. Agent 1's and Agent 2's Phase 4 briefs each name their respective new search instruction
   (Agent 2: CLI-invocation-string grep for JSON/exit-code consumers; Agent 1: conditional
   fallback language naming an alternate implementation target).
5. `skills/wire-issue/SKILL.md` is ≤500 lines, or the two category definitions live in a new
   ENH-494-pattern companion file; `test_all_skills_within_limit` passes either way.
6. `skills/wire-issue/SKILL.md` is byte-identical (post-frontmatter) to its `.gemini` and
   `.kimi-code` mirrors; `test_wire_issue_skill_mirror_matches_source` passes.
7. `docs/reference/COMMANDS.md`'s `/ll:wire-issue` wiring-categories list names both new
   categories.
8. All four `DOC_STRINGS_PRESENT` needles from Implementation Step 5 are present and
   `python -m pytest scripts/tests/test_wiring_skills_and_commands.py` passes.
9. `.gemini/commands/refine-issue.toml`'s embedded `prompt` body contains the same
   `### Decision Rules` template text as `commands/refine-issue.md`.
10. `ll-issues format-check ENH-3050` exits 0 (no `stale_symbol_ref` from this issue's own
    prose), and `python -m pytest scripts/tests/` exits 0.
11. **Behavioral validation against `ENH-3045`** (Implementation Step 7): a `/ll:refine-issue`
    pass on an ENH-3045-shaped issue emits `### Decision Rules` naming the keyword list,
    proximity rule, and escape hatch; a `/ll:wire-issue` pass surfaces `autodev.yaml` under
    `gate_consumers` and the `SKILL.md`-only companion mirror under `conditional_branches`.
    Recorded as a session-log observation, not an automated test.
12. **No Python changed.** `git diff --stat` touches no file under `scripts/little_loops/`;
    `check_format_gaps` and `DESIGN_SUBSECTIONS` are byte-unchanged.

## Impact

- **Priority**: P2 — preventive rather than corrective; smaller blast radius than ENH-3049
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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-04_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (hard override, dependency)
**Outcome Confidence**: 84/100 → HIGH CONFIDENCE

### Gaps to Address
- ~~`blocked_by: ENH-3047` is still `open`...~~ **Resolved 2026-08-05**: ENH-3047 is now `done` and `blocked_by` has been cleared to `[]`; the Dependencies Hard Override (BUG-3051) no longer applies. Re-run `/ll:confidence-check` before implementation to get a current readiness score — the 80/100 above predates this resolution.

_Review pass — 2026-08-05._ Added `## Acceptance Criteria` (the issue had none despite
`testable: true`); dropped the Criterion 4 rubric bullet as unimplementable under this issue's
own Scope Boundaries now that ENH-3047 has landed gap-driven; re-verified every line anchor and
file line count (three were stale, two mutually contradictory); disambiguated "gap class" from
`FormatGaps` gap kind in Step 2 and made its three-table scope explicit; pre-committed the
`SKILL.md` line budget rather than leaving the overflow branch to implementation time; named the
`DOC_STRINGS_PRESENT` needles literally; and reworded the optional-test bullet that was tripping
this issue's own `format-check` gate. Scores above are stale — re-run `/ll:confidence-check`.

## Status

**Open** | Created: 2026-08-04 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-05T19:36:35 - `e0e49ae6-ed56-4fa1-80cb-14d5247f10d2.jsonl`
- `/ll:refine-issue` - 2026-08-05T19:13:58 - `23b61c90-9b56-4c15-a6b7-6abf15bff76e.jsonl`
- `/ll:confidence-check` - 2026-08-05T02:56:02 - `4535f4d4-f14b-460b-89bd-b88362861660.jsonl`
- `/ll:wire-issue` - 2026-08-05T02:53:04 - `a1d9a3c9-2fcc-4cb1-9a96-631cffa38e74.jsonl`
- `/ll:refine-issue` - 2026-08-05T02:40:05 - `01b1f21d-ee5c-46e4-9926-f894d6a85704.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-05T00:25:09 - `2f3f7bc8-367e-4fba-936b-eaf8049da3c4.jsonl`
